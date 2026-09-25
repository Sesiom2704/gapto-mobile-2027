# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_vs01.py
# Ruta: backend/app/api/dto_vs01.py
# Descripcion: DTO HTTP del vertical slice VS-01 (gasto cotidiano ya ocurrido
#   y pagado). API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10.
#
#   Lo que el DTO NO admite, deliberadamente:
#     - tenant / owner / actor: salen del contexto del servidor (§15);
#     - defaults ocultos: `presupuestable` y `atribucion` son OBLIGATORIOS y
#       sin valor por defecto. `atribucion=SIN_INDICAR` es la respuesta
#       explicita "no lo indico ahora" (F05-00-A A01 -> NO_DISPONIBLE), no un
#       default del servidor;
#     - campos extra: `extra="forbid"` rechaza, p. ej., un `owner_user_id`
#       colado en el payload en vez de ignorarlo en silencio.
#   El importe es MAGNITUD positiva: el signo (GASTO +X / tesoreria -X) lo
#   pone el traductor, nunca el cliente.
#
#   v0.2.0 (F05-D003): la financiacion es una dimension EXPLICITA de la
#   intencion sellada (PROPUESTA_ACEPTADA self 100 % / NO_DETERMINADA, §16.4);
#   la fecha es la fecha COMUN de gasto y pago y no puede ser futura (§16.3).
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal, Union
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AtribucionVs01 = Literal["SOLO_MIO", "SIN_INDICAR"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Zona de referencia para "hoy" (F03-00-B02: default Europe/Madrid). Solo se
# usa para rechazar fechas futuras; la fecha enviada no se convierte.
ZONA_HOY = ZoneInfo("Europe/Madrid")


def hoy_referencia() -> dt.date:
    return dt.datetime.now(ZONA_HOY).date()


class FinanciacionPropuestaAceptada(_Estricto):
    """Propuesta visible aceptada al confirmar (§16.4). En VS-01 solo existe
    para cuenta con participacion unica del self al 100 %. El actor se expresa
    como el literal SELF: el cliente nunca envia UUID de actor."""

    estado: Literal["PROPUESTA_ACEPTADA"]
    actor: Literal["SELF"]
    criterio: Literal["PARTICIPACION_CUENTA"]
    porcentaje: Literal["100"]
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class FinanciacionNoDeterminada(_Estricto):
    """Decision funcional explicita: la financiacion real no se ha
    determinado. No equivale a cero ni a lista vacia accidental."""

    estado: Literal["NO_DETERMINADA"]


FinanciacionVs01 = Annotated[
    Union[FinanciacionPropuestaAceptada, FinanciacionNoDeterminada],
    Field(discriminator="estado"),
]


class IntencionGastoPagado(_Estricto):
    intencion_id: uuid.UUID
    concepto: str = Field(min_length=1, max_length=200)
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    # Fecha COMUN del gasto y del pago en VS-01 (regla expresa §16.3):
    # fecha_hecho = fecha_movimiento. La vigencia de la participacion se
    # evalua en esta fecha, que es la del pago.
    fecha_hecho: dt.date
    cuenta_id: uuid.UUID
    presupuestable: bool
    atribucion: AtribucionVs01
    financiacion: FinanciacionVs01

    @field_validator("fecha_hecho")
    @classmethod
    def _fecha_no_futura(cls, valor: dt.date) -> dt.date:
        if valor > hoy_referencia():
            raise ValueError("fecha futura: VS-01 registra gastos ya ocurridos")
        return valor

    @model_validator(mode="after")
    def _importe_financiacion(self) -> "IntencionGastoPagado":
        if (
            isinstance(self.financiacion, FinanciacionPropuestaAceptada)
            and self.financiacion.importe != self.importe
        ):
            raise ValueError("financiacion.importe debe igualar el importe del gasto")
        return self

    @field_validator("concepto")
    @classmethod
    def _concepto_no_blanco(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("concepto vacio")
        return limpio


class ResultadoGastoPagado(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    idempotente: bool
    importe: str
    moneda: str
    estado_atribucion: str
    aportacion_criterio: str | None
    financiacion: Literal["PROPUESTA_ACEPTADA", "NO_DETERMINADA"]
    aviso: str


class CuentaPago(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str
    moneda: str
    # Propuesta para la fecha consultada (§16.4): SELF_100 permite la
    # aceptacion implicita visible; cualquier otro estado es NO_DETERMINADA.
    propuesta_financiacion: Literal["SELF_100", "NO_DETERMINADA"]


class ListaCuentasPago(_Estricto):
    cuentas: list[CuentaPago]


class GastoMesVs01(_Estricto):
    """Lectura ESTRECHA VS-01. Candidata a sustitucion por F08 (F08-07).

    `estado` sigue DS-RULE-39/40: CONFIRMADO solo si todo lo del periodo es
    calculable; PARCIAL si hay gastos sin reparto conocido o en otra moneda
    (que NO se convierten ni se suman como cero).
    """

    mes: str
    moneda: Literal["EUR"]
    gasto_atribuible: str
    estado: Literal["CONFIRMADO", "PARCIAL"]
    gastos_sin_reparto: int
    gastos_otra_moneda: int
    contrato: str


class ErrorApi(_Estricto):
    codigo: str
    mensaje: str
    reintentable: bool
