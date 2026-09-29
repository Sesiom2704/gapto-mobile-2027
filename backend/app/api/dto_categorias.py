# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_categorias.py
# Ruta: backend/app/api/dto_categorias.py
# Descripcion: DTO HTTP de las lecturas del arbol de categorias (F05-01, S3).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-04).
#   Se devuelven tambien las categorias deshabilitadas (D-198); `icon_key`
#   NULL significa fallback neutro (C08).
#
#   v0.2.0 (F05-01, S4; diseno S4 v0.2): DTO de los comandos de gestion del
#   arbol (C06). Sin icon_key (Q4) ni presupuestable_default editable (Q6).
#   `presupuestable_default` es obligatorio en el alta y sin default.
#
#   v0.3.0 (F05-01, S6-C07; AJ-C07-08): el arbol (GET /v1/categorias) usa
#   `CategoriaNodoArbol`, que amplia el nodo con sus magnitudes, `capturable`
#   y `motivo_no_capturable`. Los comandos C06 siguen devolviendo
#   `CategoriaNodo` sin cambios. Lectura: nunca autoridad de persistencia.
#
#   v0.4.0 (F05-01 S6-ICONO (F05-D013)): `IconoCategoria` para
#   POST /v1/categorias/{id}/icono, con `icon_key` OBLIGATORIO en el cuerpo
#   (clave o null; campo ausente -> 422 estructural). `AltaCategoria` admite
#   `icon_key` opcional (Q6: omitido o null -> NULL). El DTO solo decide la
#   forma: la pertenencia a la biblioteca v1 la decide el servicio.
# Version: 0.4.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class MagnitudCategoria(_Estricto):
    magnitud_id: uuid.UUID
    nombre: str
    obligatoria: bool
    orden: int
    enabled: bool
    unidad_default: str
    precision_decimales: int
    row_version: int


class CategoriaNodoArbol(CategoriaNodo):
    magnitudes: list[MagnitudCategoria]
    capturable: bool
    motivo_no_capturable: Literal["MAGNITUD_OBLIGATORIA_NO_DISPONIBLE"] | None


class ArbolCategorias(_Estricto):
    categorias: list[CategoriaNodoArbol]


class UsoCategoria(_Estricto):
    categoria_id: uuid.UUID
    ambito: Literal["GASTO", "INGRESO", "AMBOS"]
    efectos_activos: dict[str, int]


AmbitoCategoria = Literal["GASTO", "INGRESO", "AMBOS"]


class AltaCategoria(_Estricto):
    id: uuid.UUID
    nombre: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None
    ambito: AmbitoCategoria
    presupuestable_default: bool
    icon_key: str | None = None


class _ConVersion(_Estricto):
    row_version: int = Field(ge=1)


class RenombrarCategoria(_ConVersion):
    nombre: str = Field(min_length=1, max_length=200)


class MoverCategoria(_ConVersion):
    parent_id: uuid.UUID | None


class DesactivarCategoria(_ConVersion):
    modo: Literal["RAMA", "SOLO_SI_SIN_HIJOS_ACTIVOS"]


class ReactivarCategoria(_ConVersion):
    pass


class OrdenCategoria(_ConVersion):
    orden: int


class AmbitoCambio(_ConVersion):
    ambito: AmbitoCategoria
    confirmacion_uso: dict[str, int]


class IconoCategoria(_ConVersion):
    # Sin default: la clave debe venir; null es un valor valido (sin icono).
    icon_key: str | None


class ResultadoComandoCategoria(_Estricto):
    categoria: CategoriaNodo
    idempotente: bool
    modificadas: list[uuid.UUID]
