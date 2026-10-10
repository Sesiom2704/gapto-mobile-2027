# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/preferencias/repositorio.py
# Descripcion: Acceso a datos de las preferencias de registro (F05-02,
#   F05-D026 §41.3). Es el UNICO escritor runtime de
#   gapto.preferencias_registro (inventario test_170 y test_154 I1): solo
#   INSERT y UPDATE; ningun DELETE (lifecycle por `enabled`, DB Schema §20).
#   Todas las escrituras las invoca servicio.py DESPUES de `tomar_advisory`.
#
#   - row_version y updated_at los mantiene esta capa: no hay trigger de
#     version sobre la tabla.
#   - El owner nunca se pasa como parametro: se lee de la GUC del tenant.
#   - La RLS (WITH CHECK de 0120) impide referenciar categoria o cuenta de otro
#     owner; aqui solo se leen datos para dar el error de dominio antes.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

COLUMNAS = (
    "id", "tipo_hecho_id", "categoria_id", "tercero_id", "entidad_id",
    "cuenta_default_id", "presupuestable_default", "prioridad", "enabled", "row_version",
)
_SELECT = (
    "SELECT id, tipo_hecho_id, categoria_id, tercero_id, entidad_id, cuenta_default_id, "
    "presupuestable_default, prioridad, enabled, row_version FROM gapto.preferencias_registro "
    "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_SNAPSHOT = "SELECT row_to_json(p)::text FROM gapto.preferencias_registro p WHERE p.id = %s"

#: Columnas que los comandos pueden modificar. Nunca id ni owner.
COLUMNAS_EDITABLES = frozenset({
    "tipo_hecho_id", "categoria_id", "tercero_id", "cuenta_default_id", "presupuestable_default", "enabled",
})


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory transaccional (PREFERENCIAS, owner): serializa por owner toda
    modificacion del conjunto (F03-00-G-C; §41.3). Orden: advisory -> filas.
    El registro (REG-01) nunca lo toma (§41.4)."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:PREFERENCIAS'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def _fila(f: tuple) -> dict[str, Any]:
    return dict(zip(COLUMNAS, f))


def leer(sesion: SesionMotor, preferencia_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    sql = _SELECT + " AND id = %s"
    if bloquear:
        sql += " FOR NO KEY UPDATE"
    fila = sesion.uno(sql, (preferencia_id,))
    return None if fila is None else _fila(fila)


def todas(sesion: SesionMotor) -> list[dict[str, Any]]:
    """Todas las preferencias del owner (habilitadas o no), en orden estable."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY created_at, id")
        return [_fila(f) for f in cur.fetchall()]


def habilitadas(sesion: SesionMotor) -> list[dict[str, Any]]:
    """Preferencias habilitadas del owner, ordenadas por id (determinista)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " AND enabled ORDER BY id")
        return [_fila(f) for f in cur.fetchall()]


def sin_tipo_bloqueadas(sesion: SesionMotor) -> list[dict[str, Any]]:
    """Preferencias del owner (habilitadas o no) con tipo_hecho_id NULL, con
    FOR NO KEY UPDATE en orden determinista por id (conversion C4)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " AND tipo_hecho_id IS NULL ORDER BY id FOR NO KEY UPDATE")
        return [_fila(f) for f in cur.fetchall()]


def snapshot(sesion: SesionMotor, preferencia_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (preferencia_id,))
    assert fila is not None
    return fila[0]


def insertar_preferencia(
    sesion: SesionMotor,
    *,
    preferencia_id: uuid.UUID,
    tipo_hecho_id: uuid.UUID | None,
    categoria_id: uuid.UUID | None,
    tercero_id: uuid.UUID | None,
    cuenta_default_id: uuid.UUID | None,
    presupuestable_default: bool | None,
) -> None:
    """Alta. entidad_id queda NULL (DIFERIDA) y prioridad toma su DEFAULT 100
    (AJ-D026-04): esta primitiva no los admite. tercero_id es operativo (E2)."""
    sesion.uno(
        "INSERT INTO gapto.preferencias_registro (id, owner_user_id, tipo_hecho_id, categoria_id, "
        "tercero_id, cuenta_default_id, presupuestable_default) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, %s, %s, %s, %s, %s) RETURNING id",
        (preferencia_id, tipo_hecho_id, categoria_id, tercero_id, cuenta_default_id, presupuestable_default),
    )


def actualizar_preferencia(sesion: SesionMotor, preferencia_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE con row_version + 1 y updated_at. El control de version del
    cliente lo hace el servicio sobre la fila ya bloqueada."""
    if not cambios or not set(cambios) <= COLUMNAS_EDITABLES:
        raise ValueError(f"columnas no editables por los comandos: {sorted(set(cambios) - COLUMNAS_EDITABLES)}")
    columnas = sorted(cambios)
    asignaciones = ", ".join(f"{c} = %s" for c in columnas)
    sesion.uno(
        f"UPDATE gapto.preferencias_registro SET {asignaciones}, "
        "row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (preferencia_id,),
    )
