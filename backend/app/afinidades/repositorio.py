# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/afinidades/repositorio.py
# Descripcion: Acceso a datos de `tercero_afinidades` (F05 §49.4 A5, §49.5
#   R9; DB Schema §16). UNICO escritor runtime de la tabla: INSERT y DELETE
#   (la afinidad no tiene ciclo de vida por `enabled`; quitarla es borrarla).
#   Todas las escrituras las invoca servicio.py DESPUES de `tomar_advisory`.
#   - El advisory es el de los terceros (TERCEROS, owner): la afinidad cuelga
#     del tercero (RLS por EXISTS sobre el tercero, FK CASCADE) y su writer se
#     serializa con los de terceros (C2). Se delega en terceros/repositorio.
#   - La categoria se lee FOR SHARE (nunca FOR NO KEY UPDATE: R9 prohibe la
#     variante «R16 literal», que da 40P01 frente a la desactivacion).
#   - Sin owner como parametro: GUC del tenant; la RLS (FORCE, WITH CHECK
#     tercero y categoria del owner) es la garantia de ownership.
#   - prioridad_manual siempre NULL en v1 (PA-3).
# Version: 0.1.0 (F05-05 K2 §1.3)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.terceros import repositorio as repo_ter

COLUMNAS = ("id", "tercero_id", "categoria_id")
_SNAPSHOT = "SELECT row_to_json(a)::text FROM gapto.tercero_afinidades a WHERE a.id = %s"


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory (TERCEROS, owner): el mismo que los writers de terceros."""
    repo_ter.tomar_advisory(sesion)


def leer(sesion: SesionMotor, afinidad_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT id, tercero_id, categoria_id FROM gapto.tercero_afinidades WHERE id = %s", (afinidad_id,))
    return None if fila is None else dict(zip(COLUMNAS, fila))


def leer_par(sesion: SesionMotor, tercero_id: uuid.UUID, categoria_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT id, tercero_id, categoria_id FROM gapto.tercero_afinidades "
        "WHERE tercero_id = %s AND categoria_id = %s", (tercero_id, categoria_id))
    return None if fila is None else dict(zip(COLUMNAS, fila))


def leer_categoria_compartida(sesion: SesionMotor, categoria_id: uuid.UUID) -> dict[str, Any] | None:
    """FOR SHARE de UNA categoria (R9); relee owner, enabled y ambito."""
    fila = sesion.uno(
        "SELECT owner_user_id, enabled, ambito FROM gapto.categorias_financieras WHERE id = %s FOR SHARE",
        (categoria_id,))
    return None if fila is None else {"owner_user_id": fila[0], "enabled": fila[1], "ambito": fila[2]}


def snapshot(sesion: SesionMotor, afinidad_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (afinidad_id,))
    assert fila is not None
    return fila[0]


def insertar_afinidad(sesion: SesionMotor, *, afinidad_id: uuid.UUID, tercero_id: uuid.UUID,
                      categoria_id: uuid.UUID) -> None:
    sesion.uno(
        "INSERT INTO gapto.tercero_afinidades (id, tercero_id, categoria_id, prioridad_manual) "
        "VALUES (%s, %s, %s, NULL) RETURNING id",
        (afinidad_id, tercero_id, categoria_id),
    )


def borrar_afinidad(sesion: SesionMotor, afinidad_id: uuid.UUID) -> None:
    sesion.uno("DELETE FROM gapto.tercero_afinidades WHERE id = %s RETURNING id", (afinidad_id,))
