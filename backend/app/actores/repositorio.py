# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/actores/repositorio.py
# Descripcion: Acceso a datos del writer de actor de tercero (F05-06 M3 §A3;
#   F05-D043 §57.1.4; M3-PRE2 P1/P2). SQL puro; el owner nunca es parametro de
#   negocio: se lee de la GUC del tenant y la RLS (FORCE, WITH CHECK owner y
#   tercero del owner, 0120) es la garantia de ownership.
#   - El tercero se relee FOR SHARE (no FNKU): serializa frente a desactivar o
#     editar el tercero (FNKU de terceros/servicio.py) sin chocar con el
#     registro F05, que toma el mismo FOR SHARE.
#   - La identidad la serializa la UNIQUE fisica
#     `uq_actores_financieros__owner_tercero` (0080, NULLS NOT DISTINCT): el
#     INSERT ... ON CONFLICT DO NOTHING espera a la transaccion que inserto el
#     mismo par y, tras su COMMIT, no inserta; la relectura (READ COMMITTED,
#     instantanea nueva por sentencia) ve el actor ya confirmado. Nunca se
#     bloquea una fila inexistente.
# Version: 0.1.0 (F05-06 M3 §A3)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

TABLA = "actores_financieros"
NATURALEZA_PERSONA = "PERSONA"


def leer_tercero_compartido(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any] | None:
    """Tercero del owner, FOR SHARE. None si no existe o no es visible."""
    fila = sesion.uno(
        "SELECT id, naturaleza, enabled FROM gapto.terceros WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE",
        (tercero_id,),
    )
    if fila is None:
        return None
    return {"id": fila[0], "naturaleza": fila[1], "enabled": fila[2]}


def insertar_si_no_existe(sesion: SesionMotor, tercero_id: uuid.UUID) -> tuple[uuid.UUID, str] | None:
    """Alta del actor del par (owner, tercero). (id, foto) si se inserto; None
    si el par ya existia (o lo inserto antes otra transaccion ya confirmada)."""
    fila = sesion.uno(
        "INSERT INTO gapto.actores_financieros (owner_user_id, tercero_id) "
        "VALUES (current_setting('gapto.owner_user_id')::uuid, %s) "
        "ON CONFLICT ON CONSTRAINT uq_actores_financieros__owner_tercero DO NOTHING "
        "RETURNING id, row_to_json(actores_financieros)::text",
        (tercero_id,),
    )
    return None if fila is None else (fila[0], fila[1])


def leer_actor_de_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> uuid.UUID | None:
    fila = sesion.uno(
        "SELECT id FROM gapto.actores_financieros WHERE tercero_id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid",
        (tercero_id,),
    )
    return None if fila is None else fila[0]


def tercero_de_actor(sesion: SesionMotor, actor_id: uuid.UUID) -> uuid.UUID | None:
    fila = sesion.uno("SELECT tercero_id FROM gapto.actores_financieros WHERE id = %s", (actor_id,))
    return None if fila is None else fila[0]
