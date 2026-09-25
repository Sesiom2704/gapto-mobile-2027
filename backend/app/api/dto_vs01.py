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
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AtribucionVs01 = Literal["SOLO_MIO", "SIN_INDICAR"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntencionGastoPagado(_Estricto):
    intencion_id: uuid.UUID
    concepto: str = Field(min_length=1, max_length=200)
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    fecha_hecho: dt.date
    cuenta_id: uuid.UUID
    presupuestable: bool
    atribucion: AtribucionVs01

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
    aviso: str


class CuentaPago(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str
    moneda: str
    financiacion_derivable: bool


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
