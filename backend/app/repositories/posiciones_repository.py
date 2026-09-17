# ============================================================
# GAPTO MOBILE 2027
# Fichero: posiciones_repository.py
# Ruta: backend/app/repositories/posiciones_repository.py
# Descripcion: Acceso SQL a gapto.entidades, gapto.derechos_obligaciones_financieras,
#   gapto.hecho_entidades y gapto.hecho_relaciones.
#
#   Mantiene las decisiones de F04-01..F04-03: el owner no viaja como parametro
#   de negocio, los snapshots viajan como TEXTO JSON generado y consumido por
#   PostgreSQL —numeric(18,4) no cruza un float— y la comparacion de intencion
#   se hace con jsonb EN SQL.
#
#   `tocar_entidad` es la tercera guarda de version del motor, junto a
#   `hechos_repository.tocar_raiz` y `tesoreria_repository.tocar_movimiento`.
#   La posicion no tiene `row_version` propia: su raiz es `entidades`, porque
#   `derechos_obligaciones_financieras` es un subtipo 1:1 con
#   PRIMARY KEY (entidad_id). La guarda vive en el WHERE, no en Python.
#
#   EL SALDO NO SE PERSISTE. `saldo_deltas` suma los efectos ACTIVOS de la
#   naturaleza compatible vinculados a la entidad. Los hechos ANULADO quedan
#   fuera por el propio WHERE, no por un filtro posterior que alguien pueda
#   olvidar.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_ENTIDADES = "entidades"
TABLA_POSICIONES = "derechos_obligaciones_financieras"
TABLA_VINCULOS = "hecho_entidades"
TABLA_RELACIONES = "hecho_relaciones"

TIPOS_SQL_ENTIDAD: dict[str, str] = {
    "id": "uuid",
    "tipo_entidad": "varchar",
    "nombre": "varchar",
    "enabled": "boolean",
}

TIPOS_SQL_POSICION: dict[str, str] = {
    "entidad_id": "uuid",
    "tipo": "varchar",
    "contraparte_actor_id": "uuid",
    "moneda": "varchar",
    "importe_original_documentado": "numeric",
    "saldo_apertura": "numeric",
    "fecha_inicio_seguimiento": "date",
    "fecha_vencimiento_final": "date",
    "estado": "varchar",
    "motivo_cierre": "varchar",
    "fecha_cierre": "date",
    "notas": "text",
}

TIPOS_SQL_VINCULO: dict[str, str] = {
    "id": "uuid",
    "hecho_id": "uuid",
    "efecto_id": "uuid",
    "entidad_id": "uuid",
    "tipo_relacion": "varchar",
    "principal": "boolean",
}

TIPOS_SQL_RELACION: dict[str, str] = {
    "id": "uuid",
    "hecho_origen_id": "uuid",
    "hecho_destino_id": "uuid",
    "tipo_relacion": "varchar",
    "importe_relacionado": "numeric",
}


def _snapshot(alias: str, columnas: dict[str, str]) -> sql.Composed:
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
# Entidad y subtipo
# ==================================================================

def insertar_entidad_si_no_existe(
    sesion: SesionMotor, *, entidad_id: uuid.UUID, tipo_entidad: str, nombre: str
) -> tuple[int, str] | None:
    """(row_version, snapshot_json) o None si el UUID ya estaba ocupado."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre)
        VALUES (%s::uuid, current_setting('gapto.owner_user_id')::uuid,
                %s::varchar, %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_version, ({})::text
        """
    ).format(_snapshot("entidades", TIPOS_SQL_ENTIDAD))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (entidad_id, tipo_entidad, nombre))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def insertar_posicion(sesion: SesionMotor, valores: dict[str, Any]) -> str | None:
    """Subtipo 1:1. Se crea en la MISMA transaccion que la entidad.

    El constraint trigger diferido `fn_check_entidad_subtipo_unico` existe
    justamente para permitirlo sin confirmar un estado intermedio en el que la
    entidad no tuviese subtipo.
    """
    consulta = sql.SQL(
        """
        INSERT INTO gapto.derechos_obligaciones_financieras (
            entidad_id, tipo, contraparte_actor_id, moneda,
            importe_original_documentado, saldo_apertura,
            fecha_inicio_seguimiento, notas)
        VALUES (%s::uuid, %s::varchar, %s::uuid, %s::varchar, %s::numeric,
                %s::numeric, %s::date, %s::text)
        ON CONFLICT (entidad_id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot("derechos_obligaciones_financieras", TIPOS_SQL_POSICION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                valores["entidad_id"],
                valores["tipo"],
                valores["contraparte_actor_id"],
                valores["moneda"],
                valores["importe_original_documentado"],
                valores["saldo_apertura"],
                valores["fecha_inicio_seguimiento"],
                valores["notas"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_posicion(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    """Estado completo de la posicion, o None si no existe o es de otro tenant."""
    consulta = sql.SQL(
        """
        SELECT e.row_version, p.tipo, p.moneda, p.estado, p.saldo_apertura,
               p.fecha_inicio_seguimiento, p.contraparte_actor_id,
               p.importe_original_documentado, ({})::text AS snap_posicion
          FROM gapto.derechos_obligaciones_financieras p
          JOIN gapto.entidades e ON e.id = p.entidad_id
         WHERE p.entidad_id = %s::uuid
        """
    ).format(_snapshot("p", TIPOS_SQL_POSICION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (entidad_id,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    return {
        "row_version": fila[0],
        "tipo": fila[1],
        "moneda": fila[2],
        "estado": fila[3],
        "saldo_apertura": fila[4],
        "fecha_inicio_seguimiento": fila[5],
        "contraparte_actor_id": fila[6],
        "importe_original_documentado": fila[7],
        "snapshot": fila[8],
    }


def tocar_entidad(
    sesion: SesionMotor, entidad_id: uuid.UUID, row_version_esperada: int
) -> int | None:
    """Incrementa UNA vez la version de la raiz de la posicion.

    Devuelve None si la version ya fue consumida. Es la unica proteccion frente
    a dos reducciones concurrentes: no existe constraint fisico agregado que
    impida que dos reembolsos de 70 sobre un derecho de 100 confirmen los dos.
    """
    fila = sesion.uno(
        """
        UPDATE gapto.entidades AS e
           SET updated_at = CURRENT_TIMESTAMP,
               row_version = e.row_version + 1
         WHERE e.id = %s::uuid
           AND e.row_version = %s
        RETURNING e.row_version
        """,
        (entidad_id, row_version_esperada),
    )
    return None if fila is None else fila[0]


def cerrar_posicion(
    sesion: SesionMotor,
    entidad_id: uuid.UUID,
    motivo_cierre: str,
    fecha_cierre: Any,
) -> str | None:
    """Cierre EXPLICITO. Nunca se deduce de que el saldo llegue a cero."""
    consulta = sql.SQL(
        """
        UPDATE gapto.derechos_obligaciones_financieras AS p
           SET estado = 'CERRADA',
               motivo_cierre = %s::varchar,
               fecha_cierre = %s::date
         WHERE p.entidad_id = %s::uuid
           AND p.estado = 'ACTIVA'
        RETURNING ({})::text
        """
    ).format(_snapshot("p", TIPOS_SQL_POSICION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (motivo_cierre, fecha_cierre, entidad_id))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


# ==================================================================
# Saldo derivado
# ==================================================================

def saldo_deltas(
    sesion: SesionMotor, entidad_id: uuid.UUID, tipo_efecto: str
) -> Any:
    """Suma de los deltas ACTIVOS de la naturaleza compatible.

    Los hechos ANULADO quedan excluidos por el propio WHERE. Filtrarlos despues
    seria un paso que alguien puede olvidar; aqui no hay "despues".
    """
    fila = sesion.uno(
        """
        SELECT COALESCE(sum(ef.importe_delta), 0)
          FROM gapto.hecho_entidades v
          JOIN gapto.hecho_efectos ef ON ef.id = v.efecto_id
          JOIN gapto.hechos_financieros h ON h.id = ef.hecho_id
         WHERE v.entidad_id = %s::uuid
           AND v.efecto_id IS NOT NULL
           AND ef.tipo_efecto = %s::varchar
           AND h.estado = 'ACTIVO'
        """,
        (entidad_id, tipo_efecto),
    )
    return 0 if fila is None else fila[0]


def existe_gasto_vinculado(sesion: SesionMotor, entidad_id: uuid.UUID) -> bool:
    """True si la posicion ya tiene un efecto GASTO vinculado.

    Se busca por HECHO, no por efecto vinculado: el GASTO de una condonacion
    cuelga del mismo hecho que el delta del derecho y no lleva vinculo propio.
    Buscarlo por `v.efecto_id` no lo encontraria nunca y el doble conteo se
    colaria (INV-12).
    """
    fila = sesion.uno(
        """
        SELECT EXISTS (
            SELECT 1
              FROM gapto.hecho_entidades v
              JOIN gapto.hecho_efectos ef ON ef.hecho_id = v.hecho_id
              JOIN gapto.hechos_financieros h ON h.id = ef.hecho_id
             WHERE v.entidad_id = %s::uuid
               AND ef.tipo_efecto = 'GASTO'
               AND h.estado = 'ACTIVO')
        """,
        (entidad_id,),
    )
    return bool(fila and fila[0])


# ==================================================================
# Vinculos hecho <-> entidad
# ==================================================================

def insertar_vinculo_si_no_existe(
    sesion: SesionMotor, valores: dict[str, Any]
) -> str | None:
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_entidades (
            id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal,
            owner_user_id)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::varchar,
                %s::boolean, current_setting('gapto.owner_user_id')::uuid)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot("hecho_entidades", TIPOS_SQL_VINCULO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                valores["id"],
                valores["hecho_id"],
                valores["efecto_id"],
                valores["entidad_id"],
                valores["tipo_relacion"],
                valores["principal"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_vinculo(sesion: SesionMotor, vinculo_id: uuid.UUID) -> str | None:
    consulta = sql.SQL(
        "SELECT ({})::text FROM gapto.hecho_entidades v WHERE v.id = %s::uuid"
    ).format(_snapshot("v", TIPOS_SQL_VINCULO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (vinculo_id,))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


# ==================================================================
# Relaciones entre hechos
# ==================================================================

def insertar_relacion_si_no_existe(
    sesion: SesionMotor, valores: dict[str, Any]
) -> str | None:
    """REEMBOLSO_DE y equivalentes. Solo cuando el origen causal se CONOCE."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_relaciones (
            id, hecho_origen_id, hecho_destino_id, tipo_relacion,
            importe_relacionado)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::varchar, %s::numeric)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot("hecho_relaciones", TIPOS_SQL_RELACION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                valores["id"],
                valores["hecho_origen_id"],
                valores["hecho_destino_id"],
                valores["tipo_relacion"],
                valores["importe_relacionado"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_relacion(sesion: SesionMotor, relacion_id: uuid.UUID) -> str | None:
    consulta = sql.SQL(
        "SELECT ({})::text FROM gapto.hecho_relaciones r WHERE r.id = %s::uuid"
    ).format(_snapshot("r", TIPOS_SQL_RELACION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (relacion_id,))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


# ==================================================================
# Comparacion de intencion (idempotencia)
# ==================================================================

def creacion_previa_coincide(
    sesion: SesionMotor,
    tabla: str,
    registro_id: uuid.UUID,
    valores: dict[str, Any],
    columnas: dict[str, str],
) -> bool:
    """Compara la intencion contra el snapshot DE CREACION auditado.

    Contra el snapshot de creacion y no contra el estado actual: una posicion
    puede haber recibido deltas o haberse cerrado despues, y un reintento
    tardio del alta seguiria siendo el mismo alta.
    """
    snapshot_sql, params = _jsonb_desde_valores(valores, columnas)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues @> ({})
          FROM gapto.auditoria a
         WHERE a.tabla = %s
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, tabla, registro_id))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def actor_es_self(sesion: SesionMotor, actor_id: uuid.UUID) -> bool:
    """True si el actor es el propio titular (tercero_id NULL).

    Una posicion contra uno mismo no es una posicion: es un apunte interno sin
    contraparte, y no debe crearse.
    """
    fila = sesion.uno(
        "SELECT (tercero_id IS NULL) FROM gapto.actores_financieros "
        "WHERE id = %s::uuid",
        (actor_id,),
    )
    return bool(fila and fila[0])


TABLAS_CON_ID: dict[str, str] = {
    "entidades": "id",
    "derechos_obligaciones_financieras": "entidad_id",
    "hechos_financieros": "id",
    "hecho_efectos": "id",
    "hecho_entidades": "id",
    "hecho_relaciones": "id",
    "movimientos_tesoreria": "id",
    "hecho_movimientos_tesoreria": "id",
}


def existe_registro(sesion: SesionMotor, tabla: str, registro_id: uuid.UUID) -> bool:
    """Existencia de un artefacto por su identidad reservada.

    La lista blanca `TABLAS_CON_ID` evita componer el nombre de tabla desde
    una cadena arbitraria. "No existe" incluye "es de otro tenant": RLS lo
    oculta y el motor no intenta distinguirlo.
    """
    columna = TABLAS_CON_ID[tabla]
    consulta = sql.SQL("SELECT 1 FROM gapto.{} WHERE {} = %s::uuid").format(
        sql.Identifier(tabla), sql.Identifier(columna)
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (registro_id,))
        return cursor.fetchone() is not None
