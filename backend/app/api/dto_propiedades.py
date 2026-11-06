# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_propiedades.py
# Ruta: backend/app/api/dto_propiedades.py
# Descripcion: DTOs de B1 · Propiedad (F06-01; contratos R1 v0.8 §1.1 y
#   Parte I; contrato HTTP de B1 del lote 12). Todos `extra="forbid"`: un
#   campo no listado (direccion, hipoteca, enabled, titularidad en /editar...)
#   es 422 antes de llegar al servicio.
#   Los porcentajes, importes y superficies llegan como Decimal SIN
#   restricciones de rango en el DTO: las reglas (> 0, maximo, decimales)
#   las aplica el servicio para que cada codigo de dominio sea alcanzable
#   (PARTICIPACION_NO_POSITIVA, ENTRADA_INVALIDA) y la precedencia sea la del
#   contrato. En /editar, campo omitido = no cambia y null
#   explicito = borrar (solo donde se admite); la presencia se lee de
#   `model_fields_set`.
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

TipoPropiedad = Literal["VIVIENDA", "LOCAL", "GARAJE", "TERRENO", "OTRO"]
ModoTitularidad = Literal["SOLO_MIA", "COMPARTIDA", "DE_OTROS", "DESCONOCIDA"]
MetodoValoracion = Literal["COMPRA", "MERCADO", "TASACION", "MANUAL", "FISCAL_REFERENCIA"]
LONGITUD_NOMBRE = 160
LONGITUD_MOTIVO = 200


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ParteTitularidad(_Estricto):
    yo: StrictBool = False
    tercero_id: uuid.UUID | None = None
    porcentaje: decimal.Decimal


class Titularidad(_Estricto):
    modo: ModoTitularidad
    desde: dt.date | None = None
    partes: list[ParteTitularidad] | None = Field(default=None, max_length=50)


class AltaPropiedad(_Estricto):
    intencion_id: uuid.UUID
    nombre: str = Field(max_length=LONGITUD_NOMBRE * 2)
    tipo_propiedad: TipoPropiedad
    fecha_adquisicion: dt.date | None = None
    superficie_m2: decimal.Decimal | None = None
    superficie_construida_m2: decimal.Decimal | None = None
    habitaciones: int | None = None
    banos: int | None = None
    tiene_garaje: StrictBool | None = None
    tiene_trastero: StrictBool | None = None
    referencia_catastral: str | None = None
    notas: str | None = Field(default=None, max_length=4000)
    titularidad: Titularidad


class EditarPropiedad(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    nombre: str | None = Field(default=None, max_length=LONGITUD_NOMBRE * 2)
    tipo_propiedad: TipoPropiedad | None = None
    fecha_adquisicion: dt.date | None = None
    superficie_m2: decimal.Decimal | None = None
    superficie_construida_m2: decimal.Decimal | None = None
    habitaciones: int | None = None
    banos: int | None = None
    tiene_garaje: StrictBool | None = None
    tiene_trastero: StrictBool | None = None
    referencia_catastral: str | None = None
    incluir_en_rentabilidad: StrictBool | None = None
    notas: str | None = Field(default=None, max_length=4000)


class ParteVista(_Estricto):
    actor_id: uuid.UUID
    porcentaje: decimal.Decimal


class CambioTitularidad(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    modo: ModoTitularidad
    desde: dt.date
    partes: list[ParteTitularidad] | None = Field(default=None, max_length=50)
    titularidad_vista: list[ParteVista] = Field(max_length=50)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)


class AltaValoracion(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    valor_total: decimal.Decimal
    fecha_valoracion: dt.date
    metodo: MetodoValoracion
    fuente: str | None = None
    notas: str | None = Field(default=None, max_length=4000)


#: Campos de dominio de cada DTO de edicion (los demas son de control).
CAMPOS_EDITAR = ("nombre", "tipo_propiedad", "fecha_adquisicion", "superficie_m2", "superficie_construida_m2",
                 "habitaciones", "banos", "tiene_garaje", "tiene_trastero", "referencia_catastral",
                 "incluir_en_rentabilidad", "notas")


def presentes(c: BaseModel, campos: tuple[str, ...]) -> dict:
    """Solo los campos que la peticion trae (omitido = no cambia)."""
    return {n: v for n, v in c.model_dump().items() if n in campos and n in c.model_fields_set}
