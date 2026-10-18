# ============================================================
# GAPTO MOBILE 2027
# Fichero: anulacion_tesoreria_repository.py
# Ruta: backend/app/repositories/anulacion_tesoreria_repository.py
# Descripcion: F04-R2 R2-C (contrato F04-R2 v0.9 §2.3, §2.3.2 bis, §7.2, §8.1,
#   §8.3). SQL de OP-03P «anular un registro pagado por duplicado»: lecturas del
#   conjunto C, locks de los movimientos y las escrituras W1-W5, una por fila y
#   con su foto completa para la auditoria.
#
#   QUE NO ES. Nunca borra hechos ni movimientos: solo los pasa a ANULADO. Los
#   DELETE se limitan a filas de ENLACE (aportaciones, conciliaciones y la fila
#   de `transferencias`), concedidos por 0320, y llevan la pertenencia al hecho
#   raiz en el propio DELETE (§7.2): `WHERE id = ... AND hecho_id = ...`.
#   Sin DDL, sin GRANT, sin trigger nuevo (§8.3).
#
#   FOTOS (§8.1). Hecho y movimiento llevan `row_version` dentro de la foto,
#   antes y despues; las filas de enlace, su foto completa previa (DELETE:
#   accion ELIMINAR, sin foto posterior). El orden de las llamadas lo decide el
#   servicio (anulacion_tesoreria_service.py).
# Version: 0.1.0 (F04-R2 R2-C)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any, Iterable

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor
from app.repositories import hechos_repository as repo_hechos
from app.repositories import tesoreria_repository as repo_tes
from app.repositories import transferencias_repository as repo_transf

TABLA_HECHOS = repo_hechos.TABLA
TABLA_MOVIMIENTOS = repo_tes.TABLA_MOVIMIENTOS
TABLA_CONCILIACIONES = repo_tes.TABLA_CONCILIACIONES
TABLA_APORTACIONES = repo_tes.TABLA_APORTACIONES
TABLA_TRANSFERENCIAS = "transferencias"

#: §8.1: un DELETE se audita como ELIMINAR (ck_auditoria__accion lo admite, 0070).
ACCION_ELIMINAR = "ELIMINAR"


def _foto_hecho(alias: str) -> sql.Composed:
    return sql.SQL("({}) || jsonb_build_object('row_version', {}.row_version)").format(
        repo_hechos._snapshot_desde_fila(alias), sql.Identifier(alias)
    )


def _foto_movimiento(alias: str) -> sql.Composed:
    return sql.SQL(
        "({}) || jsonb_build_object('row_version', {a}.row_version, 'estado', {a}.estado, "
        "'anulado_at', {a}.anulado_at, 'motivo_anulacion', {a}.motivo_anulacion)"
    ).format(repo_tes._snapshot_desde_fila(alias, repo_tes.TIPOS_SQL_MOVIMIENTO), a=sql.Identifier(alias))


# ==================================================================
# Lecturas del conjunto C (sin lock: L1 solo fija el conjunto)
# ==================================================================
def transferencias_de(sesion: SesionMotor, movimientos: Iterable[uuid.UUID]) -> list[dict[str, Any]]:
    """Filas de `transferencias` en las que participa alguno de los movimientos."""
    ids = sorted(set(movimientos), key=str)
    if not ids:
        return []
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, movimiento_salida_id, movimiento_entrada_id FROM gapto.transferencias "
            "WHERE movimiento_salida_id = ANY(%s::uuid[]) OR movimiento_entrada_id = ANY(%s::uuid[]) "
            "ORDER BY id",
            (ids, ids),
        )
        return [{"id": f[0], "salida": f[1], "entrada": f[2]} for f in cur.fetchall()]


def fechas_e_inicio_ledger(sesion: SesionMotor, movimientos: Iterable[uuid.UUID]) -> list[tuple[Any, Any]]:
    """(fecha_movimiento, fecha_inicio_ledger de su cuenta) de cada movimiento (§2.5, §5.2)."""
    ids = sorted(set(movimientos), key=str)
    if not ids:
        return []
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT m.fecha_movimiento, c.fecha_inicio_ledger FROM gapto.movimientos_tesoreria m "
            "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE m.id = ANY(%s::uuid[]) ORDER BY m.id",
            (ids,),
        )
        return [(f[0], f[1]) for f in cur.fetchall()]


# ==================================================================
# Escrituras W1-W5 (una por fila; pertenencia en el propio SQL)
# ==================================================================
def eliminar_aportacion(sesion: SesionMotor, aportacion_id: uuid.UUID, hecho_id: uuid.UUID) -> str | None:
    """W1: DELETE de una aportacion DEL HECHO RAIZ. Foto previa o None."""
    consulta = sql.SQL(
        "DELETE FROM gapto.hecho_aportaciones_pago a WHERE a.id = %s::uuid AND a.hecho_id = %s::uuid "
        "RETURNING ({})::text"
    ).format(repo_tes._snapshot_desde_fila("a", repo_tes.TIPOS_SQL_APORTACION))
    fila = sesion.uno(consulta, (aportacion_id, hecho_id))
    return None if fila is None else fila[0]


def eliminar_conciliacion(sesion: SesionMotor, conciliacion_id: uuid.UUID, hecho_id: uuid.UUID) -> str | None:
    """W2: DELETE de una conciliacion DEL HECHO RAIZ. Foto previa o None."""
    consulta = sql.SQL(
        "DELETE FROM gapto.hecho_movimientos_tesoreria r WHERE r.id = %s::uuid AND r.hecho_id = %s::uuid "
        "RETURNING ({})::text"
    ).format(repo_tes._snapshot_desde_fila("r", repo_tes.TIPOS_SQL_CONCILIACION))
    fila = sesion.uno(consulta, (conciliacion_id, hecho_id))
    return None if fila is None else fila[0]


def eliminar_transferencia(
    sesion: SesionMotor, transferencia_id: uuid.UUID, salida: uuid.UUID, entrada: uuid.UUID
) -> str | None:
    """W3: DELETE de la fila de `transferencias` del hecho (sus dos patas
    exactas, releidas bajo lock). Foto previa o None."""
    consulta = sql.SQL(
        "DELETE FROM gapto.transferencias t WHERE t.id = %s::uuid "
        "AND t.movimiento_salida_id = %s::uuid AND t.movimiento_entrada_id = %s::uuid "
        "RETURNING ({})::text"
    ).format(repo_transf._snapshot_desde_fila("t"))
    fila = sesion.uno(consulta, (transferencia_id, salida, entrada))
    return None if fila is None else fila[0]


def anular_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID, row_version_esperada: int, motivo: str
) -> tuple[int, str, str] | None:
    """W4: ACTIVO -> ANULADO con `anulado_at`, motivo y row_version + 1.
    (version nueva, foto antes, foto despues) o None (version o estado)."""
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.movimientos_tesoreria m WHERE m.id = %s::uuid
        )
        UPDATE gapto.movimientos_tesoreria AS m
           SET estado = 'ANULADO', anulado_at = CURRENT_TIMESTAMP, motivo_anulacion = %s::text,
               updated_at = CURRENT_TIMESTAMP, row_version = m.row_version + 1
          FROM antes
         WHERE m.id = %s::uuid AND m.row_version = %s AND m.estado = 'ACTIVO'
        RETURNING m.row_version, antes.foto, ({})::text
        """
    ).format(_foto_movimiento("m"), _foto_movimiento("m"))
    fila = sesion.uno(consulta, (movimiento_id, motivo, movimiento_id, row_version_esperada))
    return None if fila is None else (fila[0], fila[1], fila[2])


def anular_hecho(
    sesion: SesionMotor, hecho_id: uuid.UUID, row_version_esperada: int, motivo: str
) -> tuple[int, str, str] | None:
    """W5: ACTIVO -> ANULADO (mismo SQL que OP-03) con la foto completa antes y
    despues, row_version incluida. (version nueva, antes, despues) o None."""
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS foto FROM gapto.hechos_financieros h WHERE h.id = %s::uuid
        )
        UPDATE gapto.hechos_financieros AS h
           SET estado = 'ANULADO', anulado_at = CURRENT_TIMESTAMP, motivo_anulacion = %s::text,
               updated_at = CURRENT_TIMESTAMP, row_version = h.row_version + 1
          FROM antes
         WHERE h.id = %s::uuid AND h.row_version = %s AND h.estado = 'ACTIVO'
        RETURNING h.row_version, antes.foto, ({})::text
        """
    ).format(_foto_hecho("h"), _foto_hecho("h"))
    fila = sesion.uno(consulta, (hecho_id, motivo, hecho_id, row_version_esperada))
    return None if fila is None else (fila[0], fila[1], fila[2])
