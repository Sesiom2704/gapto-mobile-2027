# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/contextos/repositorio.py
# Descripcion: Acceso a datos de los contextos del registro (F05-04 J2 §1.4;
#   F05-D031; F05-D032 C2). Un contexto es una entidad de tipo CONTEXTO
#   (gapto.entidades) con su subtipo en gapto.contextos (PK = entidad_id).
#   UNICO escritor runtime de ambas tablas para CONTEXTO en la frontera F05:
#   solo INSERT y UPDATE; ningun DELETE (lifecycle por entidades.enabled).
#   - row_version y updated_at viven en entidades; contextos no tiene version
#     propia: cualquier cambio de un contexto sube la version de su entidad.
#   - Nunca escribe entidades.tipo_entidad tras el alta: el trigger D-080
#     (trg_entidades__d080_subtipo, AFTER UPDATE OF tipo_entidad) no se
#     dispara y el writer no toma el advisory INVERSIONES (C2).
#   - El owner nunca es parametro (GUC); la RLS de entidades y la de contextos
#     (EXISTS sobre la entidad del owner) garantizan el ownership (D-032.2).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.4)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

COLUMNAS = ("id", "nombre", "tipo_contexto", "fecha_inicio", "fecha_fin", "enabled", "row_version")
_SELECT = (
    "SELECT e.id, e.nombre, c.tipo_contexto, c.fecha_inicio, c.fecha_fin, e.enabled, e.row_version "
    "FROM gapto.entidades e JOIN gapto.contextos c ON c.entidad_id = e.id "
    "WHERE e.owner_user_id = current_setting('gapto.owner_user_id')::uuid AND e.tipo_entidad = 'CONTEXTO'"
)
_SNAPSHOT = (
    "SELECT json_build_object('entidad', row_to_json(e), 'contexto', row_to_json(c))::text "
    "FROM gapto.entidades e JOIN gapto.contextos c ON c.entidad_id = e.id WHERE e.id = %s"
)

COLUMNAS_ENTIDAD = frozenset({"nombre", "enabled"})
COLUMNAS_CONTEXTO = frozenset({"tipo_contexto", "fecha_inicio", "fecha_fin"})


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory transaccional (CONTEXTOS, owner), C2. Nunca INVERSIONES."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:CONTEXTOS'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def _fila(f: tuple) -> dict[str, Any]:
    return dict(zip(COLUMNAS, f))


def leer(sesion: SesionMotor, contexto_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    """Lee el contexto; con `bloquear`, FOR NO KEY UPDATE de la ENTIDAD (raiz
    del agregado) y luego de la fila de contextos, en ese orden."""
    if bloquear:
        if sesion.uno(
            "SELECT id FROM gapto.entidades WHERE id = %s AND tipo_entidad = 'CONTEXTO' "
            "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE",
            (contexto_id,),
        ) is None:
            return None
        sesion.uno("SELECT entidad_id FROM gapto.contextos WHERE entidad_id = %s FOR NO KEY UPDATE", (contexto_id,))
    fila = sesion.uno(_SELECT + " AND e.id = %s", (contexto_id,))
    return None if fila is None else _fila(fila)


def existe_entidad(sesion: SesionMotor, entidad_id: uuid.UUID) -> bool:
    """Entidad visible del owner con ese id (de cualquier tipo)."""
    return sesion.uno(
        "SELECT 1 FROM gapto.entidades WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (entidad_id,)
    ) is not None


def snapshot(sesion: SesionMotor, contexto_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (contexto_id,))
    assert fila is not None
    return fila[0]


def insertar_contexto(sesion: SesionMotor, *, contexto_id: uuid.UUID, nombre: str, tipo_contexto: str,
                      fecha_inicio, fecha_fin) -> None:
    """Alta: entidad CONTEXTO y su subtipo, en la transaccion del comando (el
    trigger diferido de subtipo unico valida el par al COMMIT)."""
    sesion.uno(
        "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, 'CONTEXTO', %s) RETURNING id",
        (contexto_id, nombre),
    )
    sesion.uno(
        "INSERT INTO gapto.contextos (entidad_id, tipo_contexto, fecha_inicio, fecha_fin) "
        "VALUES (%s, %s, %s, %s) RETURNING entidad_id",
        (contexto_id, tipo_contexto, fecha_inicio, fecha_fin),
    )


def actualizar_contexto(sesion: SesionMotor, contexto_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE de la entidad (row_version + 1, updated_at SIEMPRE) y, si hay
    cambios de subtipo, de contextos; filas ya bloqueadas por el servicio."""
    if not cambios or not set(cambios) <= COLUMNAS_ENTIDAD | COLUMNAS_CONTEXTO:
        raise ValueError(f"columnas no editables: {sorted(set(cambios) - COLUMNAS_ENTIDAD - COLUMNAS_CONTEXTO)}")
    de_entidad = sorted(set(cambios) & COLUMNAS_ENTIDAD)
    de_contexto = sorted(set(cambios) & COLUMNAS_CONTEXTO)
    asignaciones = "".join(f"{c} = %s, " for c in de_entidad)
    sesion.uno(
        f"UPDATE gapto.entidades SET {asignaciones}row_version = row_version + 1, updated_at = now() "
        "WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in de_entidad) + (contexto_id,),
    )
    if de_contexto:
        sesion.uno(
            "UPDATE gapto.contextos SET " + ", ".join(f"{c} = %s" for c in de_contexto)
            + " WHERE entidad_id = %s RETURNING entidad_id",
            tuple(cambios[c] for c in de_contexto) + (contexto_id,),
        )


def todos(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY e.id")
        return [_fila(f) for f in cur.fetchall()]
