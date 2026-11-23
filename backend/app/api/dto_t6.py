# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_t6.py
# Ruta: backend/app/api/dto_t6.py
# Descripcion: Wire aditivo del tren T6 «UX agil». API DE INTEGRACION F05, rutas /v1 internas y
#   provisionales, PENDIENTE DE CONSOLIDACION F10.
#   - `PresupuestoPropuesto` (S4): respuesta de `GET /v1/registro/presupuesto-propuesto`: valor y
#     origen visible (EXPLICITO | PREFERENCIA | CATEGORIA | POR_DEFECTO). Solo lectura.
# Version: 0.1.0 (F06 T6 · S4)
# ============================================================

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PresupuestoPropuesto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor: bool
    origen: Literal["EXPLICITO", "PREFERENCIA", "CATEGORIA", "POR_DEFECTO"]
