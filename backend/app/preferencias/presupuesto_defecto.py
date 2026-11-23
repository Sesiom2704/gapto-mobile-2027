# ============================================================
# GAPTO MOBILE 2027
# Fichero: presupuesto_defecto.py
# Ruta: backend/app/preferencias/presupuesto_defecto.py
# Descripcion: Presupuesto «Si» por defecto (F06 T6 S4, N1; dictamen 1 Q1/A2; DF-04, DF-06,
#   DF-12; F09 0.55 §12.107.3). Lectura PURA, aditiva y opcional: no escribe, no toca la
#   propuesta de hoy (`/v1/preferencias/propuesta`, `/v1/registro/propuesta`, E1 intacta para
#   quien no la pide), ni el sellado, ni la idempotencia, ni los historicos. El registro sigue
#   exigiendo `presupuestable` explicito en el wire: el valor por defecto solo se PROPONE al
#   cliente para una operacion nueva, que lo muestra con su origen y lo sella como cualquier
#   valor visible.
#
#   Precedencia (de mayor a menor; ausencia, false y true se distinguen con `is None`):
#     1. valor explicito del usuario: lo aplica el cliente (nunca pide esta lectura si ya lo
#        eligio); el de una plantilla que el usuario aplica se devuelve como EXPLICITO;
#     2. preferencia aplicable (la de hoy, D-DYN-12) -> PREFERENCIA;
#     3. `presupuestable_default` de la categoria efectiva (NOT NULL y explicito desde el alta),
#        incluido false -> CATEGORIA;
#     4. true como ultimo recurso -> POR_DEFECTO.
#   Contrato completo: evidencia T6 `P9_s4/S4_CONTRATO.md`.
# Version: 0.1.0 (F06 T6 · S4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.plantillas.propuesta import CAPA_PLANTILLA, propuesta_registro

ORIGEN_EXPLICITO = "EXPLICITO"
ORIGEN_PREFERENCIA = "PREFERENCIA"
ORIGEN_CATEGORIA = "CATEGORIA"
ORIGEN_POR_DEFECTO = "POR_DEFECTO"
ORIGENES = (ORIGEN_EXPLICITO, ORIGEN_PREFERENCIA, ORIGEN_CATEGORIA, ORIGEN_POR_DEFECTO)


def precedencia(propuesto: dict[str, Any] | None, categoria_default: bool | None) -> dict[str, Any]:
    """Valor y origen del presupuesto. `propuesto` es el campo `presupuestable` de la propuesta por tipo
    (None = sin propuesta); `categoria_default`, el de la categoria efectiva (None = sin categoria)."""
    if propuesto is not None and propuesto.get("valor") is not None:
        capa = (propuesto.get("origen") or {}).get("capa")
        return {"valor": bool(propuesto["valor"]),
                "origen": ORIGEN_EXPLICITO if capa == CAPA_PLANTILLA else ORIGEN_PREFERENCIA}
    if categoria_default is not None:
        return {"valor": bool(categoria_default), "origen": ORIGEN_CATEGORIA}
    return {"valor": True, "origen": ORIGEN_POR_DEFECTO}


def _categoria_default(sesion: SesionMotor, categoria_id: Any) -> bool | None:
    fila = sesion.uno(
        "SELECT presupuestable_default FROM gapto.categorias_financieras WHERE id = %s"
        " AND owner_user_id = current_setting('gapto.owner_user_id')::uuid",
        (categoria_id,),
    )
    return None if fila is None else fila[0]


def presupuesto_propuesto(
    sesion: SesionMotor,
    *,
    tipo: str,
    fecha: dt.date,
    plantilla_id: uuid.UUID | None = None,
    categoria_id: uuid.UUID | None = None,
    sin_categoria: bool = False,
    tercero_id: uuid.UUID | None = None,
    sin_tercero: bool = False,
) -> dict[str, Any] | str:
    """Presupuesto propuesto con su origen, o el codigo de rechazo de la propuesta por tipo (categoria no elegible)."""
    p = propuesta_registro(sesion, tipo=tipo, fecha=fecha, plantilla_id=plantilla_id, categoria_id=categoria_id,
                           sin_categoria=sin_categoria, tercero_id=tercero_id, sin_tercero=sin_tercero)
    if isinstance(p, str):
        return p
    campos = p["campos"]
    efectiva = None if sin_categoria else (categoria_id if categoria_id is not None else (campos["categoria"] or {}).get("valor"))
    return precedencia(campos["presupuestable"], _categoria_default(sesion, efectiva) if efectiva is not None else None)
