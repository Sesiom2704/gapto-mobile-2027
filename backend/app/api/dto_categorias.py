# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_categorias.py
# Ruta: backend/app/api/dto_categorias.py
# Descripcion: DTO HTTP de las lecturas del arbol de categorias (F05-01, S3).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-04).
#   Se devuelven tambien las categorias deshabilitadas (D-198); `icon_key`
#   NULL significa fallback neutro (C08).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CategoriaNodo(_Estricto):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    nombre: str
    codigo: str | None
    ambito: Literal["GASTO", "INGRESO", "AMBOS"]
    enabled: bool
    orden: int
    icon_key: str | None
    presupuestable_default: bool
    row_version: int


class ArbolCategorias(_Estricto):
    categorias: list[CategoriaNodo]


class UsoCategoria(_Estricto):
    categoria_id: uuid.UUID
    ambito: Literal["GASTO", "INGRESO", "AMBOS"]
    efectos_activos: dict[str, int]
