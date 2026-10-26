# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_reembolsable.py
# Ruta: backend/app/api/dto_reembolsable.py
# Descripcion: DTO del gasto propio reembolsable C-03 «Mío, pero me lo
#   reembolsan» (F05 §66.A, contrato C-03 v1.0; F05-D052). API DE INTEGRACION
#   F05, PENDIENTE DE CONSOLIDACION F10.
#   - Campos comunes con el gasto pagado (VS-01, §66.A.2): MISMOS nombres de
#     wire, tipos, reglas y obligatoriedad que IntencionGastoPagado (la tabla
#     campo por campo esta en la evidencia del bloque). Sin defaults
#     financieros nuevos: `presupuestable`, `financiacion` y `categoria` son
#     obligatorios como hoy. `tercero_id` es el comercio del gasto (VENDEDOR),
#     como en VS-01 y en el gasto compartido.
#   - No existen `atribucion` (la fija la ruta: tuya por el total) ni
#     `prevision` (DEU-C03-PREVISION): con `extra="forbid"` cualquiera de los
#     dos es 422.
#   - `reembolso` OBLIGATORIO: quien te lo debe (`tercero_id`) y cuanto
#     (`importe`, 0,01 <= importe <= total, sin valor por defecto).
#   Validaciones estructurales con codigo ESTABLE (PydanticCustomError: el
#   adaptador HTTP lo devuelve como `codigo`, 422):
#     REEMBOLSO_EXCEDE_TOTAL   importe recuperable mayor que el total;
#     CONTRAPARTE_ES_COMERCIO  quien lo debe es el mismo tercero que el
#                              comercio (restriccion de producto, §66.A.3; no
#                              se reclasifica nada).
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.2, §66.A.3, §66.A.7)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.api.dto_registro import LONGITUD_NOTA, _Estricto, nota_canonica
from app.api.dto_vs01 import (
    CategoriaSeleccionada,
    CategoriaVs01,
    FinanciacionPropuestaAceptada,
    FinanciacionVs01,
)

Importe = Annotated[decimal.Decimal, Field(gt=0, max_digits=14, decimal_places=2)]

REEMBOLSO_EXCEDE_TOTAL = "REEMBOLSO_EXCEDE_TOTAL"
CONTRAPARTE_ES_COMERCIO = "CONTRAPARTE_ES_COMERCIO"


class BloqueReembolso(_Estricto):
    """Derecho de cobro declarado (§66.A.2): quien te lo debe y cuanto."""

    tercero_id: uuid.UUID
    importe: Importe


class IntencionGastoReembolsable(_Estricto):
    intencion_id: uuid.UUID
    # Nota opcional del gasto (A8, como `concepto` de VS-01): ausencia canonica None.
    concepto: str | None = Field(default=None, max_length=LONGITUD_NOTA)
    importe: Importe
    moneda: Literal["EUR"]
    fecha_hecho: dt.date  # fecha comun del gasto y del pago (§16.3)
    cuenta_id: uuid.UUID  # cuenta pagadora, obligatoria
    presupuestable: bool
    financiacion: FinanciacionVs01
    categoria: CategoriaVs01
    tercero_id: uuid.UUID | None = None  # el comercio (VENDEDOR)
    contexto_id: uuid.UUID | None = None
    reembolso: BloqueReembolso

    @property
    def categoria_id(self) -> uuid.UUID | None:
        return self.categoria.categoria_id if isinstance(self.categoria, CategoriaSeleccionada) else None

    @property
    def magnitudes(self):
        return self.categoria.magnitudes if isinstance(self.categoria, CategoriaSeleccionada) else ()

    @property
    def magnitudes_desconocidas(self):
        return self.categoria.desconocidas if isinstance(self.categoria, CategoriaSeleccionada) else ()

    @field_validator("concepto", mode="before")
    @classmethod
    def _concepto_canonico(cls, valor):
        # CNC-18: se normaliza ANTES de max_length; un tipo no textual -> 422 por tipo.
        return nota_canonica(valor) if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def _coherencia(self) -> "IntencionGastoReembolsable":
        if isinstance(self.financiacion, FinanciacionPropuestaAceptada) and self.financiacion.importe != self.importe:
            raise ValueError("financiacion.importe debe igualar el importe del gasto")
        if self.reembolso.importe > self.importe:
            raise PydanticCustomError(REEMBOLSO_EXCEDE_TOTAL, "El importe recuperable supera el total del gasto.")
        if self.tercero_id is not None and self.reembolso.tercero_id == self.tercero_id:
            raise PydanticCustomError(CONTRAPARTE_ES_COMERCIO, "Quien te lo debe no puede ser el comercio del gasto.")
        return self


class MovimientoReembolsableHttp(_Estricto):
    movimiento_id: uuid.UUID
    cuenta_id: uuid.UUID
    importe: str  # -total: el pago real sale de la cuenta pagadora


class PosicionReembolsoHttp(_Estricto):
    entidad_id: uuid.UUID
    tipo: Literal["DERECHO_COBRO"]
    contraparte_tercero_id: uuid.UUID
    nombre: str
    importe: str  # importe recuperable declarado
    saldo: str | None  # None = «Sin determinar»
    estado: Literal["ACTIVA", "CERRADA"]  # ACTIVA al registrar; un replay posterior a un cobro total la ve CERRADA
    apertura_indeterminada: bool  # F04-D055 A4: siempre False en C-03 (apertura 0)


class ResultadoGastoReembolsableHttp(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    idempotente: bool
    importe: str
    moneda: str
    estado_atribucion: Literal["COMPLETA"]
    tu_parte: str  # = total: la atribucion propia es el gasto entero (§66.1)
    movimiento: MovimientoReembolsableHttp
    posiciones: list[PosicionReembolsoHttp]
    aviso: str
