# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/terceros/repositorio.py
# Descripcion: Acceso a datos de los terceros del registro (F05-04 J2 §1.3;
#   F05 §46.4 R5; F05-D032 C2). Es el UNICO escritor runtime de gapto.terceros
#   en la frontera F05 (A7): solo INSERT y UPDATE; ningun DELETE (lifecycle por
#   `enabled`). Todas las escrituras las invoca servicio.py DESPUES de
#   `tomar_advisory`.
#   - row_version y updated_at los mantiene esta capa.
#   - El owner nunca es parametro: GUC del tenant. La RLS (FORCE, WITH CHECK
#     owner) es la garantia de ownership (D-032.2, D-099).
#   - Solo se escriben `nombre`, `naturaleza` y `enabled`: los datos fiscales,
#     de contacto y notas quedan fuera del alcance del registro.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.3)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

COLUMNAS = ("id", "nombre", "naturaleza", "enabled", "row_version")
_SELECT = (
    "SELECT id, nombre, naturaleza, enabled, row_version FROM gapto.terceros "
    "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_SNAPSHOT = "SELECT row_to_json(t)::text FROM gapto.terceros t WHERE t.id = %s"

#: Columnas que los comandos pueden modificar. Nunca id ni owner.
COLUMNAS_EDITABLES = frozenset({"nombre", "naturaleza", "enabled"})


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory transaccional (TERCEROS, owner): serializa por owner los
    writers de terceros (C2). Orden: advisory -> fila del tercero."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:TERCEROS'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def _fila(f: tuple) -> dict[str, Any]:
    return dict(zip(COLUMNAS, f))


def leer(sesion: SesionMotor, tercero_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    sql = _SELECT + " AND id = %s"
    if bloquear:
        sql += " FOR NO KEY UPDATE"
    fila = sesion.uno(sql, (tercero_id,))
    return None if fila is None else _fila(fila)


def todos(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY id")
        return [_fila(f) for f in cur.fetchall()]


def snapshot(sesion: SesionMotor, tercero_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (tercero_id,))
    assert fila is not None
    return fila[0]


def insertar_tercero(sesion: SesionMotor, *, tercero_id: uuid.UUID, nombre: str, naturaleza: str | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, %s, %s) RETURNING id",
        (tercero_id, nombre, naturaleza),
    )


def actualizar_tercero(sesion: SesionMotor, tercero_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE con row_version + 1 y updated_at, sobre la fila ya bloqueada."""
    if not cambios or not set(cambios) <= COLUMNAS_EDITABLES:
        raise ValueError(f"columnas no editables por los comandos: {sorted(set(cambios) - COLUMNAS_EDITABLES)}")
    columnas = sorted(cambios)
    asignaciones = ", ".join(f"{c} = %s" for c in columnas)
    sesion.uno(
        f"UPDATE gapto.terceros SET {asignaciones}, "
        "row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (tercero_id,),
    )
