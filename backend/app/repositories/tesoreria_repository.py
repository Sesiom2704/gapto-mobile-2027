# ============================================================
# GAPTO MOBILE 2027
# Fichero: tesoreria_repository.py
# Ruta: backend/app/repositories/tesoreria_repository.py
# Descripcion: Acceso SQL a gapto.hecho_aportaciones_pago,
#   gapto.movimientos_tesoreria y gapto.hecho_movimientos_tesoreria.
#
#   Mantiene las decisiones de F04-01/F04-02 por las mismas razones: el owner
#   nunca viaja como parametro (aqui RLS lo deriva del hecho o de la cuenta),
#   los snapshots viajan como TEXTO JSON generado y consumido por PostgreSQL
#   —numeric(18,4) no cruza un float— y la comparacion de intencion se hace con
#   jsonb EN SQL, que iguala numeros por valor.
#
#   `tocar_movimiento` es el gemelo de `hechos_repository.tocar_raiz` para la
#   SEGUNDA raiz. OP-09 necesita las dos porque modifica los dos agregados
#   (F04-D010), y ambas guardas viven en el WHERE, no en Python.
#
#   Nota sobre D-169: la comparacion agregada aportaciones-vs-porcion la impone
#   el constraint trigger diferido de 0310, SOLO cuando moneda del hecho y
#   moneda de la cuenta coinciden. Este repositorio expone la lectura necesaria
#   para dar un error legible por anticipado, pero la garantia concurrente
#   sigue siendo la fisica: una prevalidacion mejora el mensaje, no sustituye
#   al trigger.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_APORTACIONES = "hecho_aportaciones_pago"
TABLA_MOVIMIENTOS = "movimientos_tesoreria"
TABLA_CONCILIACIONES = "hecho_movimientos_tesoreria"

TIPOS_SQL_APORTACION: dict[str, str] = {
    "id": "uuid",
    "hecho_id": "uuid",
    "actor_id": "uuid",
    "importe": "numeric",
    "porcentaje_aplicado": "numeric",
    "criterio_aportacion": "varchar",
    "medio_pago_codigo": "varchar",
    "hecho_movimiento_tesoreria_id": "uuid",
}

TIPOS_SQL_MOVIMIENTO: dict[str, str] = {
    "id": "uuid",
    "cuenta_id": "uuid",
    "fecha_movimiento": "date",
    "importe": "numeric",
    "descripcion": "varchar",
    "confirmado_at": "timestamptz",
    "clase_movimiento": "varchar",
    "estado": "varchar",
    "anulado_at": "timestamptz",
    "motivo_anulacion": "text",
    "reversion_de_movimiento_id": "uuid",
}

TIPOS_SQL_CONCILIACION: dict[str, str] = {
    "id": "uuid",
    "hecho_id": "uuid",
    "movimiento_tesoreria_id": "uuid",
    "importe_asignado": "numeric",
}


def _snapshot_desde_fila(alias: str, columnas: dict[str, str]) -> sql.Composed:
    partes = [
        sql.SQL("{}, {}.{}").format(
            sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
        )
        for columna in columnas
    ]
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def _jsonb_desde_valores(
    valores: dict[str, Any], columnas: dict[str, str]
) -> tuple[sql.Composed, list[Any]]:
    partes: list[sql.Composed] = []
    params: list[Any] = []
    for columna, valor in valores.items():
        partes.append(
            sql.SQL("{}, %s::{}").format(
                sql.Literal(columna), sql.SQL(columnas[columna])
            )
        )
        params.append(valor)
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes)), params


# ==================================================================
# Cuentas
# ==================================================================

def leer_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID) -> tuple[str, bool] | None:
    """(moneda, enabled) o None si no existe o es de otro tenant."""
    fila = sesion.uno(
        "SELECT moneda, enabled FROM gapto.cuentas WHERE id = %s::uuid",
        (cuenta_id,),
    )
    return None if fila is None else (fila[0], fila[1])


# ==================================================================
# OP-08 — movimientos
# ==================================================================

def insertar_movimiento_si_no_existe(
    sesion: SesionMotor,
    *,
    movimiento_id: uuid.UUID,
    cuenta_id: uuid.UUID,
    fecha_movimiento: Any,
    importe: Any,
    clase_movimiento: str,
    descripcion: str | None,
    confirmado_at: Any,
) -> tuple[int, str] | None:
    """(row_version, snapshot_json) si se creo aqui; None si el UUID ya existia."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.movimientos_tesoreria (
            id, cuenta_id, fecha_movimiento, importe, descripcion,
            confirmado_at, clase_movimiento)
        VALUES (%s::uuid, %s::uuid, %s::date, %s::numeric, %s::varchar,
                COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_version, ({})::text
        """
    ).format(_snapshot_desde_fila("movimientos_tesoreria", TIPOS_SQL_MOVIMIENTO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                movimiento_id,
                cuenta_id,
                fecha_movimiento,
                importe,
                descripcion,
                confirmado_at,
                clase_movimiento,
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def leer_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID
) -> tuple[int, str, Any, uuid.UUID, str] | None:
    """(row_version, estado, importe, cuenta_id, snapshot_json)."""
    consulta = sql.SQL(
        """
        SELECT m.row_version, m.estado, m.importe, m.cuenta_id, ({})::text
          FROM gapto.movimientos_tesoreria m
         WHERE m.id = %s::uuid
        """
    ).format(_snapshot_desde_fila("m", TIPOS_SQL_MOVIMIENTO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (movimiento_id,))
        fila = cursor.fetchone()
    return None if fila is None else tuple(fila)  # type: ignore[return-value]


def tocar_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID, row_version_esperada: int
) -> int | None:
    """Incrementa la version de la SEGUNDA raiz, con la guarda en SQL.

    Igual que `tocar_raiz` para el hecho: entre leer y escribir cabe otra
    transaccion, y solo la clausula del WHERE impide la perdida de
    actualizacion. Devuelve None si la version ya fue consumida o el
    movimiento no esta ACTIVO.
    """
    fila = sesion.uno(
        """
        UPDATE gapto.movimientos_tesoreria AS m
           SET updated_at = CURRENT_TIMESTAMP,
               row_version = m.row_version + 1
         WHERE m.id = %s::uuid
           AND m.row_version = %s
           AND m.estado = 'ACTIVO'
        RETURNING m.row_version
        """,
        (movimiento_id, row_version_esperada),
    )
    return None if fila is None else fila[0]


def creacion_movimiento_previa_coincide(
    sesion: SesionMotor, valores: dict[str, Any]
) -> bool:
    """Compara la intencion contra el snapshot DE CREACION auditado.

    `confirmado_at` se excluye de la comparacion cuando el llamante no lo
    aporto: en ese caso lo fijo el reloj de la transaccion y un reintento
    posterior produciria otro instante, convirtiendo un retry legitimo en
    conflicto falso.
    """
    snapshot_sql, params = _jsonb_desde_valores(valores, TIPOS_SQL_MOVIMIENTO)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues @> ({})
          FROM gapto.auditoria a
         WHERE a.tabla = 'movimientos_tesoreria'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, valores["id"]))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


# ==================================================================
# OP-09 — conciliaciones
# ==================================================================

def insertar_conciliacion_si_no_existe(
    sesion: SesionMotor, datos: dict[str, Any]
) -> str | None:
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_movimientos_tesoreria (
            id, hecho_id, movimiento_tesoreria_id, importe_asignado)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::numeric)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(
        _snapshot_desde_fila("hecho_movimientos_tesoreria", TIPOS_SQL_CONCILIACION)
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                datos["id"],
                datos["hecho_id"],
                datos["movimiento_tesoreria_id"],
                datos["importe_asignado"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, Any, str] | None:
    """(hecho_id, movimiento_tesoreria_id, importe_asignado, snapshot_json)."""
    consulta = sql.SQL(
        """
        SELECT r.hecho_id, r.movimiento_tesoreria_id, r.importe_asignado, ({})::text
          FROM gapto.hecho_movimientos_tesoreria r
         WHERE r.id = %s::uuid
        """
    ).format(_snapshot_desde_fila("r", TIPOS_SQL_CONCILIACION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (conciliacion_id,))
        fila = cursor.fetchone()
    return None if fila is None else tuple(fila)  # type: ignore[return-value]


def conciliacion_de_pareja(
    sesion: SesionMotor, hecho_id: uuid.UUID, movimiento_id: uuid.UUID
) -> tuple[uuid.UUID, Any] | None:
    """(id, importe_asignado) de la conciliacion ya existente para esa pareja.

    Existe UNIQUE (hecho_id, movimiento_tesoreria_id): la pareja es unica por
    contrato fisico. Leerla antes permite devolver YA_CONCILIADO con sentido en
    vez de traducir una violacion de UNIQUE.
    """
    fila = sesion.uno(
        "SELECT id, importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "WHERE hecho_id = %s::uuid AND movimiento_tesoreria_id = %s::uuid",
        (hecho_id, movimiento_id),
    )
    return None if fila is None else (fila[0], fila[1])


def suma_conciliada_del_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID, excluir: uuid.UUID | None = None
) -> Any:
    fila = sesion.uno(
        "SELECT COALESCE(sum(importe_asignado), 0) "
        "FROM gapto.hecho_movimientos_tesoreria "
        "WHERE movimiento_tesoreria_id = %s::uuid AND (%s::uuid IS NULL OR id <> %s::uuid)",
        (movimiento_id, excluir, excluir),
    )
    return 0 if fila is None else fila[0]


def creacion_conciliacion_previa_coincide(
    sesion: SesionMotor, valores: dict[str, Any]
) -> bool:
    snapshot_sql, params = _jsonb_desde_valores(valores, TIPOS_SQL_CONCILIACION)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues = ({})
          FROM gapto.auditoria a
         WHERE a.tabla = 'hecho_movimientos_tesoreria'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, valores["id"]))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


# ==================================================================
# OP-06 / OP-07 — aportaciones
# ==================================================================

def insertar_aportacion_si_no_existe(
    sesion: SesionMotor, datos: dict[str, Any]
) -> str | None:
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_aportaciones_pago (
            id, hecho_id, actor_id, importe, porcentaje_aplicado,
            criterio_aportacion, medio_pago_codigo, hecho_movimiento_tesoreria_id)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::numeric, %s::numeric,
                %s::varchar, %s::varchar, %s::uuid)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(
        _snapshot_desde_fila("hecho_aportaciones_pago", TIPOS_SQL_APORTACION)
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                datos["id"],
                datos["hecho_id"],
                datos["actor_id"],
                datos["importe"],
                datos["porcentaje_aplicado"],
                datos["criterio_aportacion"],
                datos["medio_pago_codigo"],
                datos["hecho_movimiento_tesoreria_id"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_aportacion(
    sesion: SesionMotor, aportacion_id: uuid.UUID
) -> tuple[uuid.UUID, Any, uuid.UUID | None, str] | None:
    """(hecho_id, importe, hecho_movimiento_tesoreria_id, snapshot_json)."""
    consulta = sql.SQL(
        """
        SELECT a.hecho_id, a.importe, a.hecho_movimiento_tesoreria_id, ({})::text
          FROM gapto.hecho_aportaciones_pago a
         WHERE a.id = %s::uuid
        """
    ).format(_snapshot_desde_fila("a", TIPOS_SQL_APORTACION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (aportacion_id,))
        fila = cursor.fetchone()
    return None if fila is None else tuple(fila)  # type: ignore[return-value]


def actualizar_vinculo(
    sesion: SesionMotor,
    aportacion_id: uuid.UUID,
    destino: uuid.UUID | None,
) -> str | None:
    """UPDATE del vinculo. Nunca DELETE + INSERT: la fila es la misma realidad
    y su identidad se conserva para que la auditoria sea trazable."""
    consulta = sql.SQL(
        """
        UPDATE gapto.hecho_aportaciones_pago AS a
           SET hecho_movimiento_tesoreria_id = %s::uuid
         WHERE a.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila("a", TIPOS_SQL_APORTACION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (destino, aportacion_id))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def creacion_aportacion_previa_coincide(
    sesion: SesionMotor, valores: dict[str, Any]
) -> bool:
    snapshot_sql, params = _jsonb_desde_valores(valores, TIPOS_SQL_APORTACION)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues = ({})
          FROM gapto.auditoria a
         WHERE a.tabla = 'hecho_aportaciones_pago'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, valores["id"]))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def monedas_comparables(
    sesion: SesionMotor, conciliacion_id: uuid.UUID
) -> tuple[bool, Any, Any] | None:
    """(comparables, porcion_absoluta, suma_ya_vinculada) de una conciliacion.

    `comparables` es True solo cuando la moneda del hecho coincide con la de la
    cuenta del movimiento. Es EXACTAMENTE la condicion que usa D-169 en 0310.
    En multidivisa devuelve False y el servicio NO compara nominalmente: no hay
    FX, y no se inventa ninguno.
    """
    fila = sesion.uno(
        """
        SELECT (h.moneda = c.moneda) AS comparables,
               abs(r.importe_asignado) AS porcion,
               COALESCE((SELECT sum(ap.importe)
                           FROM gapto.hecho_aportaciones_pago ap
                          WHERE ap.hecho_movimiento_tesoreria_id = r.id), 0) AS vinculada
          FROM gapto.hecho_movimientos_tesoreria r
          JOIN gapto.hechos_financieros h ON h.id = r.hecho_id
          JOIN gapto.movimientos_tesoreria m ON m.id = r.movimiento_tesoreria_id
          JOIN gapto.cuentas c ON c.id = m.cuenta_id
         WHERE r.id = %s::uuid
        """,
        (conciliacion_id,),
    )
    return None if fila is None else (fila[0], fila[1], fila[2])


def movimiento_de_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID
) -> tuple[Any, str] | None:
    """(importe del movimiento, estado del movimiento) de una conciliacion."""
    fila = sesion.uno(
        """
        SELECT m.importe, m.estado
          FROM gapto.hecho_movimientos_tesoreria r
          JOIN gapto.movimientos_tesoreria m ON m.id = r.movimiento_tesoreria_id
         WHERE r.id = %s::uuid
        """,
        (conciliacion_id,),
    )
    return None if fila is None else (fila[0], fila[1])
