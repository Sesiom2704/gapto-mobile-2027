# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_t6.py
# Ruta: backend/app/api/dto_t6.py
# Descripcion: Wire aditivo del tren T6 «UX agil». API DE INTEGRACION F05, rutas /v1 internas y
#   provisionales, PENDIENTE DE CONSOLIDACION F10.
#   - `PresupuestoPropuesto` (S4): respuesta de `GET /v1/registro/presupuesto-propuesto`: valor y
#     origen visible (EXPLICITO | PREFERENCIA | CATEGORIA | POR_DEFECTO). Solo lectura.
#   - `PeticionAmbos` / `ResultadoAmbos` (S5): `POST /v1/preferencias/ambos`, una o dos operaciones
#     (ALTA o EDITAR) de ambitos distintos (TERCERO, CATEGORIA), atomicas.
# Version: 0.1.0 (F06 T6 · S4)
# Version: 0.2.0 (F06 T6 · S5): wire de «Ambos».
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.dto_preferencias import PreferenciaNodo


class PresupuestoPropuesto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor: bool
    origen: Literal["EXPLICITO", "PREFERENCIA", "CATEGORIA", "POR_DEFECTO"]


class ContenidoAmbos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_hecho_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    entidad_id: uuid.UUID | None = None
    cuenta_default_id: uuid.UUID | None = None
    presupuestable_default: bool | None = None
    prioridad: int = 100


class OperacionAmbos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambito: Literal["TERCERO", "CATEGORIA"]
    accion: Literal["ALTA", "EDITAR"]
    id: uuid.UUID
    row_version: int | None = Field(None, ge=1)
    contenido: ContenidoAmbos


class PeticionAmbos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operaciones: list[OperacionAmbos] = Field(min_length=1, max_length=2)


class ResultadoAmbosItem(BaseModel):
    ambito: Literal["TERCERO", "CATEGORIA"]
    preferencia: PreferenciaNodo
    idempotente: bool


class ResultadoAmbos(BaseModel):
    resultados: list[ResultadoAmbosItem]
