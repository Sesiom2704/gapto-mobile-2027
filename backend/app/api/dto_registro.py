# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_registro.py
# Ruta: backend/app/api/dto_registro.py
# Descripcion: DTO HTTP del registro por tipo de F05-04 (J2 §1.7; F05 §46.3
#   A3/A4/A5/A6/A8/A9, §46.4 R1/R3): «Ingreso cobrado» (C-14 via OP-22) y
#   «Entre cuentas» (OP-10). API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10. El gasto sigue en dto_vs01.IntencionGastoPagado,
#   ampliada de forma aditiva con tercero, contexto y «No lo sé».
#
#   Comun a todas las intenciones (R3):
#     - UUID propio de la intencion; el tipo queda sellado por la ruta: un
#       UUID ya usado con otro tipo choca con
#       IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (OP-22 u OP-10 comparan el
#       agregado);
#     - `extra="forbid"`: origenes, plantilla, instantanea u owner colados en
#       el payload -> 422 (no forman parte de la identidad);
#     - importe MAGNITUD positiva (el signo lo pone el traductor); EUR v1;
#     - nota OPCIONAL: omitida, null, "" o solo espacios -> None (ausencia
#       canonica, A8); recortada; max 200 (la columna de concepto).
#   La fecha futura no la decide el DTO: depende del «hoy» del owner y la
#   rechaza la ejecucion con FECHA_FUTURA (F05-D032 C6).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.7)
#   v0.2.0 (F05-03/F05-04 J3 §2.7; CNC-18): la nota se canonicaliza ANTES de
#   `max_length` (validador `before`), que mide el valor normalizado: una
#   cadena de espacios larga es ausencia (None), no 422.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.dto_vs01 import CategoriaVs01, CategoriaSeleccionada

AtribucionRegistro = Literal["SOLO_MIO", "SIN_INDICAR"]
LONGITUD_NOTA = 200


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def nota_canonica(valor: str | None) -> str | None:
    """Ausencia canonica (A8): None, "" o solo espacios -> None; si no, recortada."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


class _ConNota(_Estricto):
    nota: str | None = Field(default=None, max_length=LONGITUD_NOTA)

    @field_validator("nota", mode="before")
    @classmethod
    def _nota(cls, valor):
        # CNC-18: canonica antes de max_length; un tipo no textual -> 422 por tipo.
        return nota_canonica(valor) if isinstance(valor, str) else valor


class IntencionIngresoCobrado(_ConNota):
    """Ingreso ya cobrado (A3): la fecha del ingreso es la del cobro."""

    intencion_id: uuid.UUID
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    fecha_hecho: dt.date
    cuenta_id: uuid.UUID  # «Cobrado en», obligatoria (F04-D052)
    presupuestable: bool  # decision explicita (E1 de F05-D026 por tipo)
    atribucion: AtribucionRegistro  # A01: «Solo mio» o NO_DISPONIBLE
    categoria: CategoriaVs01
    tercero_id: uuid.UUID | None = None  # «De», opcional
    contexto_id: uuid.UUID | None = None  # «Mas detalles», opcional

    @property
    def categoria_id(self) -> uuid.UUID | None:
        return self.categoria.categoria_id if isinstance(self.categoria, CategoriaSeleccionada) else None

    @property
    def magnitudes(self):
        return self.categoria.magnitudes if isinstance(self.categoria, CategoriaSeleccionada) else ()

    @property
    def magnitudes_desconocidas(self):
        return self.categoria.desconocidas if isinstance(self.categoria, CategoriaSeleccionada) else ()


class IntencionTransferencia(_ConNota):
    """Entre cuentas (A4, OP-10): sin categoria, presupuesto, atribucion ni tercero."""

    intencion_id: uuid.UUID
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    fecha_hecho: dt.date
    cuenta_origen_id: uuid.UUID
    cuenta_destino_id: uuid.UUID

    # La misma cuenta se rechaza con MISMA_CUENTA en la ejecucion (campo «A»).


class ResultadoRegistro(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    idempotente: bool
    tipo: Literal["GASTO", "INGRESO", "TRANSFERENCIA"]
    importe: str
    moneda: str
    estado_atribucion: str | None
    estado_categorial: Literal["CATEGORIA", "SIN_CATEGORIA"] | None
    aviso: str
