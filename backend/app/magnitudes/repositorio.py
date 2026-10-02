# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/magnitudes/repositorio.py
# Descripcion: Acceso a datos de S7-MAG (F05-D020). Es el UNICO escritor
#   runtime de gapto.magnitudes (INSERT/UPDATE; ningun DELETE) y de
#   gapto.categoria_magnitudes (INSERT/UPDATE/DELETE de una asociacion
#   concreta por su PK), inventario fail-closed I9 de test_154 (D-MAG-08).
#   Todas las escrituras las invoca magnitudes/servicio.py DESPUES de tomar
#   el advisory (CATEGORIAS, owner) y dentro del savepoint de alcance de
#   comando (D-MAG-10).
#
#   - row_version y updated_at de `magnitudes` los mantiene esta capa (0340
#     no tiene trigger de version). `categoria_magnitudes` no tiene version
#     (F2, D-MAG-07): su identidad estable es la PK (D-MAG-04).
#   - COLUMNAS_EDITABLES_MAGNITUD excluye unidad_default y
#     precision_decimales (R17: fuera de v1) e identidad.
#   - El mismo owner categoria <-> magnitud solo lo garantiza la RLS WITH
#     CHECK de 0120 (F5): el servicio prevalida ambas referencias antes de
#     escribir.
#   - Ninguna funcion de este modulo escribe categorias_financieras: la
#     categoria solo se LEE bloqueada con categorias/repositorio.py.
# Version: 0.1.0 (F05-01 S7-MAG)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

_CAMPOS_MAGNITUD = ("id", "nombre", "unidad_default", "precision_decimales", "enabled", "row_version")
_CAMPOS_ASOCIACION = ("asociacion_id", "magnitud_id", "obligatoria", "orden")

#: Columnas de `magnitudes` que los comandos pueden modificar (R17).
COLUMNAS_EDITABLES_MAGNITUD = frozenset({"nombre", "enabled"})
#: Columnas de `categoria_magnitudes` que los comandos pueden modificar.
COLUMNAS_EDITABLES_ASOCIACION = frozenset({"obligatoria", "orden"})


# ------------------------------------------------------------------ lecturas
def leer_magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    sql = (
        "SELECT id, nombre, unidad_default, precision_decimales, enabled, row_version FROM gapto.magnitudes "
        "WHERE id = %s AND owner_user_id = current_setting('gapto.owner_user_id')::uuid"
    )
    if bloquear:
        sql += " FOR NO KEY UPDATE"
    fila = sesion.uno(sql, (magnitud_id,))
    return None if fila is None else dict(zip(_CAMPOS_MAGNITUD, fila))


def bloquear_magnitudes(sesion: SesionMotor, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """FOR NO KEY UPDATE de varias magnitudes del owner en orden determinista por id (D-MAG-03)."""
    if not ids:
        return {}
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, nombre, unidad_default, precision_decimales, enabled, row_version FROM gapto.magnitudes "
            "WHERE id = ANY(%s) AND owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "ORDER BY id FOR NO KEY UPDATE",
            (sorted(set(ids)),),
        )
        return {f[0]: dict(zip(_CAMPOS_MAGNITUD, f)) for f in cur.fetchall()}


def nombres(sesion: SesionMotor) -> list[tuple[uuid.UUID, str, bool]]:
    """TODAS las magnitudes del owner, habilitadas o no (la UNIQUE de 0080 no es parcial)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, nombre, enabled FROM gapto.magnitudes "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
        )
        return list(cur.fetchall())


def asociaciones(sesion: SesionMotor, categoria_id: uuid.UUID) -> list[dict[str, Any]]:
    """Asociaciones de una categoria en su orden persistido (orden, id). Se leen
    con la categoria ya bloqueada FOR NO KEY UPDATE: ningun otro escritor del
    catalogo (advisory) ni C07 (FOR SHARE de la categoria) las cambia o lee a la vez."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, magnitud_id, obligatoria, orden FROM gapto.categoria_magnitudes "
            "WHERE categoria_id = %s ORDER BY orden, id",
            (categoria_id,),
        )
        return [dict(zip(_CAMPOS_ASOCIACION, f)) for f in cur.fetchall()]


def categorias_obligatorias_habilitadas(sesion: SesionMotor, magnitud_id: uuid.UUID) -> list[dict[str, Any]]:
    """Categorias HABILITADAS del owner con asociacion OBLIGATORIA a la magnitud
    (las que dejarian de ser capturables al deshabilitarla), por id. Se leen bajo
    el lock de la magnitud, sin bloquear las categorias (D-MAG-03)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.nombre, cm.obligatoria FROM gapto.categoria_magnitudes cm "
            "JOIN gapto.categorias_financieras c ON c.id = cm.categoria_id "
            "WHERE cm.magnitud_id = %s AND cm.obligatoria AND c.enabled "
            "AND c.owner_user_id = current_setting('gapto.owner_user_id')::uuid ORDER BY c.id",
            (magnitud_id,),
        )
        return [{"categoria_id": i, "nombre": n, "obligatoria": o} for i, n, o in cur.fetchall()]


def snapshot_magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID) -> str:
    fila = sesion.uno("SELECT row_to_json(m)::text FROM gapto.magnitudes m WHERE m.id = %s", (magnitud_id,))
    assert fila is not None
    return fila[0]


def snapshot_asociacion(sesion: SesionMotor, asociacion_id: uuid.UUID) -> str:
    fila = sesion.uno(
        "SELECT row_to_json(cm)::text FROM gapto.categoria_magnitudes cm WHERE cm.id = %s", (asociacion_id,)
    )
    assert fila is not None
    return fila[0]


# ------------------------------------------------------------------ escrituras
def insertar_magnitud(sesion: SesionMotor, *, magnitud_id: uuid.UUID, nombre: str, unidad_default: str,
                      precision_decimales: int) -> None:
    sesion.uno(
        "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
        "VALUES (%s, current_setting('gapto.owner_user_id')::uuid, %s, %s, %s) RETURNING id",
        (magnitud_id, nombre, unidad_default, precision_decimales),
    )


def actualizar_magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE con row_version + 1 y updated_at. El control de version del
    cliente lo hace el servicio sobre la fila ya bloqueada."""
    if not cambios or not set(cambios) <= COLUMNAS_EDITABLES_MAGNITUD:
        raise ValueError(f"columnas no editables: {sorted(set(cambios) - COLUMNAS_EDITABLES_MAGNITUD)}")
    columnas = sorted(cambios)
    asignaciones = ", ".join(f"{c} = %s" for c in columnas)
    sesion.uno(
        f"UPDATE gapto.magnitudes SET {asignaciones}, "
        "row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (magnitud_id,),
    )


def insertar_asociacion(sesion: SesionMotor, *, asociacion_id: uuid.UUID, categoria_id: uuid.UUID,
                        magnitud_id: uuid.UUID, obligatoria: bool, orden: int) -> None:
    sesion.uno(
        "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (asociacion_id, categoria_id, magnitud_id, obligatoria, orden),
    )


def actualizar_asociacion(sesion: SesionMotor, asociacion_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    if not cambios or not set(cambios) <= COLUMNAS_EDITABLES_ASOCIACION:
        raise ValueError(f"columnas no editables: {sorted(set(cambios) - COLUMNAS_EDITABLES_ASOCIACION)}")
    columnas = sorted(cambios)
    asignaciones = ", ".join(f"{c} = %s" for c in columnas)
    sesion.uno(
        f"UPDATE gapto.categoria_magnitudes SET {asignaciones} WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (asociacion_id,),
    )


def eliminar_asociacion(sesion: SesionMotor, asociacion_id: uuid.UUID) -> None:
    """DELETE legitimo de UNA asociacion por su PK (DB Schema §19; D-MAG-01).
    Nunca borra magnitudes (I9: DELETE runtime de magnitudes = 0)."""
    fila = sesion.uno("DELETE FROM gapto.categoria_magnitudes WHERE id = %s RETURNING id", (asociacion_id,))
    if fila is None:
        raise LookupError("asociacion no encontrada al eliminar")
