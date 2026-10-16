# ============================================================
# GAPTO MOBILE 2027
# Fichero: correccion_tesoreria_repository.py
# Ruta: backend/app/repositories/correccion_tesoreria_repository.py
# Descripcion: F04-R2 R2-B (contrato F04-R2 v0.8 §2.1, §2.2, §2.5, §5, §6,
#   §8.1). SQL de la correccion EN SITIO del pago de un gasto (OP-21P) y de
#   una transferencia propia (OP-21T).
#
#   WRITERS NUEVOS (inventario, contrato §10.6): UPDATE de
#   `hechos_financieros` (importe_total, fecha_hecho), `movimientos_tesoreria`
#   (importe, fecha_movimiento, cuenta_id), `hecho_movimientos_tesoreria`
#   (importe_asignado) y `hecho_aportaciones_pago` (importe). Todos conservan
#   el `id` de la fila (§2.1.3: corregir en sitio, nunca sustituir), llevan la
#   pertenencia al hecho raiz en el propio WHERE (§7.2) y devuelven la foto
#   anterior y la posterior para la auditoria fila a fila (§8.1). Hecho y
#   movimiento incluyen `row_version` en las dos fotos (§8.1: la version
#   anterior y la nueva quedan dentro de las fotos). Ningun DELETE, ningun
#   INSERT, ningun paso a ANULADO: R2-B no anula movimientos (§10.3).
#
#   Locks: `bloquear_cuentas` y `bloquear_movimientos` toman FOR NO KEY UPDATE
#   en ORDER BY id (niveles 2 bis y 6 de §6.1). El hecho lo bloquea
#   `integridad_posicion.adquirir_raiz` (nivel 3). El orden lo impone el
#   servicio; este modulo no decide cuando se llama a cada uno.
#
#   El owner nunca es parametro: RLS con la GUC del tenant. Una cuenta, un
#   hecho o un movimiento de otro owner simplemente no existen aqui.
# Version: 0.1.0 (F04-R2 R2-B)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Any, Iterable

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor
from app.repositories import hechos_repository as repo_hechos
from app.repositories import tesoreria_repository as repo_tes

TABLA_HECHOS = repo_hechos.TABLA
TABLA_MOVIMIENTOS = repo_tes.TABLA_MOVIMIENTOS
TABLA_CONCILIACIONES = repo_tes.TABLA_CONCILIACIONES
TABLA_APORTACIONES = repo_tes.TABLA_APORTACIONES

#: Columnas corregibles por tabla (lista CERRADA: cualquier otra columna seria
#: reescribir identidad o estado, que no es corregir un dato falso).
CORREGIBLES_HECHO = ("importe_total", "fecha_hecho")
CORREGIBLES_MOVIMIENTO = ("importe", "fecha_movimiento", "cuenta_id")


def _foto_hecho(alias: str) -> sql.Composed:
    return sql.SQL("({}) || jsonb_build_object('row_version', {}.row_version)").format(
        repo_hechos._snapshot_desde_fila(alias), sql.Identifier(alias)
    )


def _foto_movimiento(alias: str) -> sql.Composed:
    return sql.SQL("({}) || jsonb_build_object('row_version', {}.row_version)").format(
        repo_tes._snapshot_desde_fila(alias, repo_tes.TIPOS_SQL_MOVIMIENTO),
        sql.Identifier(alias),
    )


# ==================================================================
# Lecturas (sin lock: el servicio las repite bajo la raiz cuando autorizan)
# ==================================================================
def leer_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        """
        SELECT h.row_version, h.estado, t.codigo, h.importe_total, h.fecha_hecho, h.moneda
          FROM gapto.hechos_financieros h
          JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id
         WHERE h.id = %s::uuid
        """,
        (hecho_id,),
    )
    if fila is None:
        return None
    return {
        "row_version": fila[0], "estado": fila[1], "tipo": fila[2],
        "importe_total": fila[3], "fecha": fila[4], "moneda": fila[5],
    }


def efectos(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, tipo_efecto, importe_delta, estado_atribucion "
            "FROM gapto.hecho_efectos WHERE hecho_id = %s::uuid ORDER BY id",
            (hecho_id,),
        )
        return [
            {"id": f[0], "tipo_efecto": f[1], "importe_delta": f[2], "estado_atribucion": f[3]}
            for f in cur.fetchall()
        ]


def atribuciones(sesion: SesionMotor, efecto_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, importe_atribuido, porcentaje_aplicado "
            "FROM gapto.efecto_atribuciones WHERE efecto_id = %s::uuid ORDER BY id",
            (efecto_id,),
        )
        return [
            {"id": f[0], "importe": f[1], "porcentaje": f[2]} for f in cur.fetchall()
        ]


def conciliaciones(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, movimiento_tesoreria_id, importe_asignado "
            "FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s::uuid ORDER BY id",
            (hecho_id,),
        )
        return [
            {"id": f[0], "movimiento_id": f[1], "importe": f[2]} for f in cur.fetchall()
        ]


def aportaciones(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, hecho_movimiento_tesoreria_id, criterio_aportacion, "
            "porcentaje_aplicado, importe "
            "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s::uuid ORDER BY id",
            (hecho_id,),
        )
        return [
            {"id": f[0], "conciliacion_id": f[1], "criterio": f[2], "porcentaje": f[3], "importe": f[4]}
            for f in cur.fetchall()
        ]


def leer_movimiento(sesion: SesionMotor, movimiento_id: uuid.UUID) -> dict[str, Any] | None:
    """Estado del movimiento y la evidencia que decide su elegibilidad:
    reversiones en CUALQUIER estado (E-4), conciliaciones con otros hechos
    (E-3) y transferencia en la que participa (E-4 / T-1)."""
    fila = sesion.uno(
        """
        SELECT m.row_version, m.estado, m.cuenta_id, m.fecha_movimiento, m.importe,
               m.clase_movimiento, m.reversion_de_movimiento_id,
               (SELECT count(*) FROM gapto.movimientos_tesoreria r
                 WHERE r.reversion_de_movimiento_id = m.id) AS reversiones,
               (SELECT t.id FROM gapto.transferencias t
                 WHERE t.movimiento_salida_id = m.id OR t.movimiento_entrada_id = m.id
                 LIMIT 1) AS transferencia_id
          FROM gapto.movimientos_tesoreria m
         WHERE m.id = %s::uuid
        """,
        (movimiento_id,),
    )
    if fila is None:
        return None
    return {
        "id": movimiento_id, "row_version": fila[0], "estado": fila[1], "cuenta_id": fila[2],
        "fecha": fila[3], "importe": fila[4], "clase": fila[5], "reversion_de": fila[6],
        "reversiones": fila[7], "transferencia_id": fila[8],
    }


def hechos_conciliados(sesion: SesionMotor, movimiento_id: uuid.UUID) -> list[uuid.UUID]:
    """Hechos (visibles) conciliados con el movimiento, por id."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT hecho_id FROM gapto.hecho_movimientos_tesoreria "
            "WHERE movimiento_tesoreria_id = %s::uuid ORDER BY hecho_id",
            (movimiento_id,),
        )
        return [f[0] for f in cur.fetchall()]


def leer_transferencia(sesion: SesionMotor, transferencia_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT movimiento_salida_id, movimiento_entrada_id FROM gapto.transferencias WHERE id = %s::uuid",
        (transferencia_id,),
    )
    return None if fila is None else {"salida": fila[0], "entrada": fila[1]}


def leer_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID) -> dict[str, Any] | None:
    """Cuenta visible (owner por RLS) con lo que valida §2.1.5."""
    fila = sesion.uno(
        "SELECT moneda, enabled, fecha_cierre, fecha_inicio_ledger "
        "FROM gapto.cuentas WHERE id = %s::uuid",
        (cuenta_id,),
    )
    if fila is None:
        return None
    return {"moneda": fila[0], "enabled": fila[1], "fecha_cierre": fila[2], "inicio_ledger": fila[3]}


def es_origen_de_devolucion(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.hecho_relaciones "
        "WHERE hecho_origen_id = %s::uuid AND tipo_relacion = 'DEVOLUCION_DE')",
        (hecho_id,),
    )
    return bool(fila and fila[0])


def tiene_entidad_de_inversion(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.hecho_entidades he "
        "JOIN gapto.entidades e ON e.id = he.entidad_id "
        "WHERE he.hecho_id = %s::uuid AND e.tipo_entidad = 'INVERSION')",
        (hecho_id,),
    )
    return bool(fila and fila[0])


def importado(sesion: SesionMotor, destinos: Iterable[tuple[str, uuid.UUID]]) -> bool:
    """§2.5 fila 1: algun registro procede de una importacion (V3 u otra)."""
    pares = list(destinos)
    if not pares:
        return False
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.mapeos_importacion m "
        "JOIN unnest(%s::text[], %s::uuid[]) AS d(tabla, id) "
        "ON m.tabla_destino = d.tabla AND m.registro_destino_id = d.id)",
        ([p[0] for p in pares], [p[1] for p in pares]),
    )
    return bool(fila and fila[0])


def periodo_cerrado(sesion: SesionMotor, fechas: Iterable[dt.date]) -> bool:
    """§5.1: alguna fecha cae en un periodo cuyo cierre VIGENTE (la ultima
    version del periodo) esta CERRADO. Una ultima version REABIERTO deja el
    periodo abierto; versiones anteriores no cuentan. No se reescribe nada."""
    lista = sorted(set(fechas))
    if not lista:
        return False
    fila = sesion.uno(
        """
        SELECT EXISTS (
            SELECT 1
              FROM gapto.cierres_mensuales c
              JOIN unnest(%s::date[]) AS f(fecha)
                ON f.fecha BETWEEN c.periodo_desde AND c.periodo_hasta
             WHERE c.estado = 'CERRADO'
               AND c.version_cierre = (
                   SELECT max(u.version_cierre) FROM gapto.cierres_mensuales u
                    WHERE u.owner_user_id = c.owner_user_id
                      AND u.periodo_desde = c.periodo_desde
                      AND u.periodo_hasta = c.periodo_hasta)
        )
        """,
        (lista,),
    )
    return bool(fila and fila[0])


def _json(texto: str | None) -> dict[str, Any]:
    """jsonb leido como texto: numeric -> Decimal, sin pasar por float."""
    return {} if texto is None else json.loads(texto, parse_float=decimal.Decimal)


def auditorias_de_peticion(sesion: SesionMotor, request_id: uuid.UUID) -> list[dict[str, Any]]:
    """Auditoria visible escrita con ese request_id (§6.4)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT tabla, registro_id, accion, datos_antes::text, datos_despues::text, motivo FROM gapto.auditoria "
            "WHERE request_id = %s::uuid ORDER BY created_at, id",
            (request_id,),
        )
        return [
            {"tabla": f[0], "registro_id": f[1], "accion": f[2], "antes": _json(f[3]),
             "despues": _json(f[4]), "motivo": f[5]}
            for f in cur.fetchall()
        ]


# ==================================================================
# Locks (el orden lo decide el servicio)
# ==================================================================
def bloquear_cuentas(sesion: SesionMotor, cuentas: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Nivel 2 bis: FOR NO KEY UPDATE en ORDER BY id. Devuelve las visibles."""
    ids = sorted(set(cuentas), key=str)
    if not ids:
        return set()
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id FROM gapto.cuentas WHERE id = ANY(%s::uuid[]) ORDER BY id FOR NO KEY UPDATE",
            (ids,),
        )
        return {f[0] for f in cur.fetchall()}


def bloquear_movimientos(sesion: SesionMotor, movimientos: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Nivel 6: FOR NO KEY UPDATE en ORDER BY id. Devuelve los visibles."""
    ids = sorted(set(movimientos), key=str)
    if not ids:
        return set()
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id FROM gapto.movimientos_tesoreria WHERE id = ANY(%s::uuid[]) "
            "ORDER BY id FOR NO KEY UPDATE",
            (ids,),
        )
        return {f[0] for f in cur.fetchall()}


# ==================================================================
# Writers en sitio (una sola escritura por fila y operacion, §8.1)
# ==================================================================
def actualizar_hecho(
    sesion: SesionMotor, hecho_id: uuid.UUID, row_version_esperada: int, cambios: dict[str, Any]
) -> tuple[int, str, str] | None:
    """UPDATE con guarda de version y de estado. (version nueva, antes, despues).

    Sin campos (solo cambia la cuenta del movimiento) es el incremento de
    version de la raiz, que tambien se audita: la fila muta (row_version)."""
    columnas = [c for c in CORREGIBLES_HECHO if c in cambios]
    asignaciones = sql.SQL(", ").join(
        [sql.SQL("{} = %s::{}").format(sql.Identifier(c), sql.SQL(repo_hechos.TIPOS_SQL[c]))
         for c in columnas]
        + [sql.SQL("updated_at = CURRENT_TIMESTAMP"), sql.SQL("row_version = h.row_version + 1")]
    )
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.hechos_financieros h WHERE h.id = %s::uuid
        )
        UPDATE gapto.hechos_financieros AS h
           SET {}
          FROM antes
         WHERE h.id = %s::uuid AND h.row_version = %s AND h.estado = 'ACTIVO'
        RETURNING h.row_version, antes.foto, ({})::text
        """
    ).format(_foto_hecho("h"), asignaciones, _foto_hecho("h"))
    fila = sesion.uno(
        consulta, (hecho_id, *[cambios[c] for c in columnas], hecho_id, row_version_esperada)
    )
    return None if fila is None else (fila[0], fila[1], fila[2])


def actualizar_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID, row_version_esperada: int, cambios: dict[str, Any]
) -> tuple[int, str, str] | None:
    """UPDATE en sitio (mismo id) con guarda de version y de estado ACTIVO."""
    columnas = [c for c in CORREGIBLES_MOVIMIENTO if c in cambios]
    asignaciones = sql.SQL(", ").join(
        sql.SQL("{} = %s::{}").format(sql.Identifier(c), sql.SQL(repo_tes.TIPOS_SQL_MOVIMIENTO[c]))
        for c in columnas
    )
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.movimientos_tesoreria m WHERE m.id = %s::uuid
        )
        UPDATE gapto.movimientos_tesoreria AS m
           SET {}, updated_at = CURRENT_TIMESTAMP, row_version = m.row_version + 1
          FROM antes
         WHERE m.id = %s::uuid AND m.row_version = %s AND m.estado = 'ACTIVO'
        RETURNING m.row_version, antes.foto, ({})::text
        """
    ).format(_foto_movimiento("m"), asignaciones, _foto_movimiento("m"))
    fila = sesion.uno(
        consulta, (movimiento_id, *[cambios[c] for c in columnas], movimiento_id, row_version_esperada)
    )
    return None if fila is None else (fila[0], fila[1], fila[2])


def actualizar_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID, hecho_id: uuid.UUID, importe: Any
) -> tuple[str, str] | None:
    """importe_asignado en sitio; solo una conciliacion DEL HECHO RAIZ (§7.2)."""
    foto = repo_tes._snapshot_desde_fila("r", repo_tes.TIPOS_SQL_CONCILIACION)
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.hecho_movimientos_tesoreria r WHERE r.id = %s::uuid
        )
        UPDATE gapto.hecho_movimientos_tesoreria AS r
           SET importe_asignado = %s::numeric
          FROM antes
         WHERE r.id = %s::uuid AND r.hecho_id = %s::uuid
        RETURNING antes.foto, ({})::text
        """
    ).format(foto, foto)
    fila = sesion.uno(consulta, (conciliacion_id, importe, conciliacion_id, hecho_id))
    return None if fila is None else (fila[0], fila[1])


def actualizar_aportacion(
    sesion: SesionMotor, aportacion_id: uuid.UUID, hecho_id: uuid.UUID, importe: Any
) -> tuple[str, str] | None:
    """importe en sitio; solo una aportacion DEL HECHO RAIZ (§7.2)."""
    foto = repo_tes._snapshot_desde_fila("a", repo_tes.TIPOS_SQL_APORTACION)
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.hecho_aportaciones_pago a WHERE a.id = %s::uuid
        )
        UPDATE gapto.hecho_aportaciones_pago AS a
           SET importe = %s::numeric
          FROM antes
         WHERE a.id = %s::uuid AND a.hecho_id = %s::uuid
        RETURNING antes.foto, ({})::text
        """
    ).format(foto, foto)
    fila = sesion.uno(consulta, (aportacion_id, importe, aportacion_id, hecho_id))
    return None if fila is None else (fila[0], fila[1])


def saldo_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID) -> Any:
    """Suma de movimientos ACTIVOS de la cuenta (oraculo de §10.2)."""
    fila = sesion.uno(
        "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
        "WHERE cuenta_id = %s::uuid AND estado = 'ACTIVO'",
        (cuenta_id,),
    )
    return 0 if fila is None else fila[0]
