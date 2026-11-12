# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto.py
# Ruta: backend/app/patrimonio/dto.py
# Descripcion: DTO estrictos de B2 (extra=forbid; R1 v0.8 §1.1 y Parte II, v0.9 y v0.9.5 §II.1):
#   RegistrarCompra (C-COMPRA-01, sin hipoteca: un campo de hipoteca es 422 por extra=forbid), GastoCompraPosterior
#   (C-COMPRA-03) y DeclararCompletitud (C-PROP-05). Importes EUR > 0 con 2 decimales y porcentajes con 4 como
#   texto exacto o numero decimal; nunca float en las respuestas.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool

Concepto = Literal["ITP", "IVA_AJD", "NOTARIA_REGISTRO_GESTORIA", "AGENCIA", "OTRO"]
Rol = Literal["ARRAS", "FIRMA", "OTRO"]
Modo = Literal["SEGUN_TITULARIDAD_ACEPTADA", "MANUAL", "NO_LO_SE"]
Criterio = Literal["TITULARIDAD_EN_FECHA_ESCRITURA", "TITULARIDAD_EN_FECHA_ECONOMICA"]
Ambito = Literal["ADQUISICION", "MEJORAS"]


def _importe(v: decimal.Decimal) -> decimal.Decimal:
    if not v.is_finite() or v <= 0 or v >= decimal.Decimal("100000000000000"):
        raise ValueError("importe fuera de rango")
    if v != v.quantize(decimal.Decimal("0.01")):
        raise ValueError("importe con mas de 2 decimales")
    return v


Importe = Annotated[decimal.Decimal, AfterValidator(_importe)]


def _nota(v: str | None) -> str | None:
    if v is not None and not v.strip():
        raise ValueError("nota vacia")
    return v


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Parte(_Estricto):
    actor_id: uuid.UUID
    porcentaje: decimal.Decimal


class PropuestaVista(_Estricto):
    criterio: Criterio
    fecha_referencia: dt.date
    partes: list[Parte] = Field(min_length=1, max_length=50)


class Atribucion(_Estricto):
    modo: Modo
    partes: list[Parte] | None = Field(default=None, max_length=50)
    propuesta_vista: PropuestaVista | None = None


class Completitud(_Estricto):
    completo: StrictBool
    fecha_corte: dt.date | None = None


class PagoPropio(_Estricto):
    linea_id: uuid.UUID
    rol: Rol
    cuenta_id: uuid.UUID
    fecha_pago: dt.date
    importe: Importe


class LineaGastoCompra(_Estricto):
    linea_id: uuid.UUID
    concepto: Concepto
    cuenta_id: uuid.UUID
    fecha_economica: dt.date
    fecha_pago: dt.date
    importe: Importe
    nota: Annotated[str | None, AfterValidator(_nota)] = Field(default=None, max_length=200)


class RegistrarCompra(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    fecha_escritura: dt.date
    precio: Importe
    valor_referencia: Importe | None = None
    pagos_propios: list[PagoPropio] = Field(min_length=1, max_length=20)
    gastos: list[LineaGastoCompra] = Field(max_length=30)
    atribucion: Atribucion
    completitud_adquisicion: Completitud | None = None


class GastoCompraPosterior(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    linea: LineaGastoCompra
    atribucion: Atribucion
    completitud_adquisicion: Completitud | None = None
    huella_conjunto_vista: str | None = Field(default=None, min_length=64, max_length=64)


class DeclararCompletitud(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    ambito: Ambito
    completo: StrictBool
    fecha_corte: dt.date | None = None
    huella_conjunto_vista: str | None = Field(default=None, min_length=64, max_length=64)
