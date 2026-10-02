# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_magnitudes.py
# Ruta: backend/app/api/dto_magnitudes.py
# Descripcion: DTO HTTP de S7-MAG (F05-01; F05-D020, expediente F05 §34).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-03/04).
#
#   Lectura del arbol (GET /v1/categorias): cada magnitud asociada anade
#   `asociacion_id` (PK de categoria_magnitudes), la identidad estable que
#   exigen los comandos de asociaciones (D-MAG-04). Campo ADITIVO: el resto
#   del nodo es exactamente CategoriaNodoArbol de dto_categorias.py, que no se
#   modifica (decision de ejecucion D29 del mandato S7-MAG backend: el modelo
#   ampliado vive aqui y app.py lo usa como response_model).
#
#   Comandos (POST por accion, extra="forbid"): la FORMA se decide aqui (422
#   ENTRADA_INVALIDA estructural); la semantica (identidad, unicidad, locks,
#   impacto) la decide magnitudes/servicio.py (409 sin escritura previa).
#     - nombre de magnitud: 1..80 caracteres visibles tras NFKC + recorte +
#       colapso (nombre_magnitud_valido); unidad 1..20 visibles; precision
#       0..6 entera estricta; obligatoria booleana estricta.
#     - alta/asociacion: union discriminada por `origen` (EXISTENTE | NUEVA).
#     - reordenar: conjunto completo 1..32768, sin asociacion_id repetidos,
#       orden 0..32767 (smallint).
#     - deshabilitar: `confirmacion_impacto` OBLIGATORIO en el cuerpo (lista
#       de categoria_id sin repetidos o null).
#   Lectura del catalogo (GET /v1/magnitudes): CatalogoMagnitudes.
# Version: 0.1.0 (F05-01 S7-MAG, commit 1: lectura con asociacion_id)
# Version: 0.2.0 (F05-01 S7-MAG, commit 2: DTO de comandos y catalogo)
# ============================================================

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Union

from pydantic import Field, StrictBool, field_validator

from app.api.dto_categorias import CategoriaNodoArbol, MagnitudCategoria, _Estricto
from app.magnitudes.normalizacion import nombre_magnitud_valido, unidad_valida

#: Precision entera estricta 0..6 (CHECK de 0020); un bool o un float no valen.
Precision = Annotated[int, Field(strict=True, ge=0, le=6)]
#: Posicion smallint 0..32767.
Orden = Annotated[int, Field(strict=True, ge=0, le=32767)]


class MagnitudAsociada(MagnitudCategoria):
    asociacion_id: uuid.UUID


class CategoriaNodoArbolMagnitudes(CategoriaNodoArbol):
    magnitudes: list[MagnitudAsociada]


class ArbolCategoriasMagnitudes(_Estricto):
    categorias: list[CategoriaNodoArbolMagnitudes]


# ------------------------------------------------------------------ comandos
def _nombre(v: str) -> str:
    if not nombre_magnitud_valido(v):
        raise ValueError("nombre de magnitud: 1..80 caracteres visibles")
    return v


def _sin_repetidos(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(ids)) != len(ids):
        raise ValueError("ids repetidos")
    return ids


class NuevaMagnitud(_Estricto):
    magnitud_id: uuid.UUID
    nombre: str = Field(max_length=400)
    unidad_default: str = Field(max_length=100)
    precision_decimales: Precision

    @field_validator("nombre")
    @classmethod
    def _v_nombre(cls, v: str) -> str:
        return _nombre(v)

    @field_validator("unidad_default")
    @classmethod
    def _unidad(cls, v: str) -> str:
        if not unidad_valida(v):
            raise ValueError("unidad: 1..20 caracteres visibles")
        return v


class AsociarExistente(_Estricto):
    origen: Literal["EXISTENTE"]
    magnitud_id: uuid.UUID
    obligatoria: StrictBool


class AsociarNueva(_Estricto):
    origen: Literal["NUEVA"]
    magnitud: NuevaMagnitud
    obligatoria: StrictBool


AsociarMagnitud = Annotated[Union[AsociarExistente, AsociarNueva], Field(discriminator="origen")]


class ObligatoriaAsociacion(_Estricto):
    magnitud_id: uuid.UUID
    obligatoria_actual: StrictBool
    obligatoria: StrictBool


class RetirarAsociacion(_Estricto):
    magnitud_id: uuid.UUID
    obligatoria_actual: StrictBool


class ElementoOrdenMagnitud(_Estricto):
    asociacion_id: uuid.UUID
    magnitud_id: uuid.UUID
    orden: Orden
    obligatoria: StrictBool


class ReordenarMagnitudes(_Estricto):
    # Conjunto completo; 32768 = posiciones 0..32767 (orden smallint).
    asociaciones: list[ElementoOrdenMagnitud] = Field(min_length=1, max_length=32768)

    @field_validator("asociaciones")
    @classmethod
    def _unicas(cls, v: list[ElementoOrdenMagnitud]) -> list[ElementoOrdenMagnitud]:
        _sin_repetidos([a.asociacion_id for a in v])
        return v


class _ConVersion(_Estricto):
    row_version: int = Field(strict=True, ge=1)


class RenombrarMagnitud(_ConVersion):
    nombre: str = Field(max_length=400)

    @field_validator("nombre")
    @classmethod
    def _v_nombre(cls, v: str) -> str:
        return _nombre(v)


class DeshabilitarMagnitud(_ConVersion):
    # Sin default: debe venir; null = sin confirmacion.
    confirmacion_impacto: list[uuid.UUID] | None

    @field_validator("confirmacion_impacto")
    @classmethod
    def _unicas(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        return None if v is None else _sin_repetidos(v)


class RehabilitarMagnitud(_ConVersion):
    pass


# ------------------------------------------------------------------ respuestas
class FichaMagnitud(_Estricto):
    id: uuid.UUID
    nombre: str
    unidad_default: str
    precision_decimales: int
    enabled: bool
    row_version: int


class AsociacionMagnitud(_Estricto):
    asociacion_id: uuid.UUID
    magnitud_id: uuid.UUID
    obligatoria: bool
    orden: int


class ResultadoAsociacionMagnitud(_Estricto):
    categoria_id: uuid.UUID
    asociacion: AsociacionMagnitud
    magnitud: FichaMagnitud
    idempotente: bool
    modificadas: list[uuid.UUID]


class ResultadoAsociacionesMagnitud(_Estricto):
    categoria_id: uuid.UUID
    asociaciones: list[AsociacionMagnitud]
    idempotente: bool
    modificadas: list[uuid.UUID]


class ResultadoComandoMagnitud(_Estricto):
    magnitud: FichaMagnitud
    idempotente: bool
    modificadas: list[uuid.UUID]


class CategoriaDeMagnitud(_Estricto):
    categoria_id: uuid.UUID
    nombre: str
    obligatoria: bool
    categoria_enabled: bool


class MagnitudCatalogo(FichaMagnitud):
    categorias: list[CategoriaDeMagnitud]
    n_hechos: int


class CatalogoMagnitudes(_Estricto):
    magnitudes: list[MagnitudCatalogo]
