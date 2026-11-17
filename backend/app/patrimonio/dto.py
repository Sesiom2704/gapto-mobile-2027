# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto.py
# Ruta: backend/app/patrimonio/dto.py
# Descripcion: DTO estrictos de B2 (extra=forbid; R1 v0.8 §1.1 y Parte II, v0.9 y v0.9.5 §II.1):
#   RegistrarCompra (C-COMPRA-01, sin hipoteca: un campo de hipoteca es 422 por extra=forbid), GastoCompraPosterior
#   (C-COMPRA-03) y DeclararCompletitud (C-PROP-05). Importes EUR > 0 con 2 decimales y porcentajes con 4 como
#   texto exacto o numero decimal; nunca float en las respuestas.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 5; reapertura de B2 v1.1; contrato v0.4 §3.2.1): bloque
#   `hipoteca` (BloqueHipoteca) habilitado en RegistrarCompra. Sus campos llegan opcionales y sin rango en el DTO:
#   la falta, el rango y la modalidad no representable (fecha_desembolso, pago_directo_vendedor, tramos,
#   importe_ingresado, comision_retenida) se rechazan con CONDICIONES_INCOMPLETAS y su motivo en el servicio
#   (hipotecas/alta.forma), no como 422 generico. Cualquier otro campo sigue siendo 422 (extra=forbid).
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt

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


class Financiador(_Estricto):
    tercero_id: uuid.UUID


class BloqueHipoteca(_Estricto):
    financiador: Financiador | None = None
    importe_prestamo: decimal.Decimal | None = None
    cuenta_desembolso_id: uuid.UUID | None = None
    titularidad: Atribucion | None = None
    tipo_interes: str | None = Field(default=None, max_length=20)
    tasa_anual_pct: decimal.Decimal | None = None
    indice_referencia: str | None = Field(default=None, max_length=50)
    diferencial_pct: decimal.Decimal | None = None
    numero_cuotas: StrictInt | None = None
    fecha_primera_cuota: dt.date | None = None
    cuenta_cargo_id: uuid.UUID | None = None
    sistema: str | None = Field(default=None, max_length=30)
    periodicidad: str | None = Field(default=None, max_length=20)
    # Modalidad no representable en v1 (contrato §3.2.7-7/8): solo para rechazarla con su motivo.
    fecha_desembolso: dt.date | None = None
    pago_directo_vendedor: StrictBool | None = None
    tramos: list[dict] | None = Field(default=None, max_length=20)
    importe_ingresado: decimal.Decimal | None = None
    comision_retenida: decimal.Decimal | None = None


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
    hipoteca: BloqueHipoteca | None = None


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
