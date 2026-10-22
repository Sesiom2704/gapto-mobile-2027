# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_edicion.py
# Ruta: backend/app/api/dto_edicion.py
# Descripcion: DTOs de F05-06 M1 (CONTRATO_M1 v0.1 §1-§2; F05 §61.2
#   F05-D047; lamina EDIT-HECHO v0.1). Todos `extra="forbid"`: un campo que
#   no es de la operacion se rechaza con 422 (nada de reparto, categoria ni
#   efectos por estas rutas).
#   - IntencionCorregirPago (OP-21P): importe, fecha y cuenta de un gasto
#     pagado simple; `error_de_registro` explicito (INV-07: solo datos que
#     nunca fueron ciertos); version del hecho y del movimiento leidas.
#   - IntencionCorregirTransferencia (OP-21T): importe, fecha y cuentas;
#     version de CADA pata.
#   - IntencionAnularDuplicado (OP-03P): `duplicado_declarado` explicito,
#     sin defecto («Este registro está repetido; el cargo no ocurrió dos
#     veces»); version del hecho y de cada movimiento.
#   `intencion_id` es el request_id de la operacion: un reintento con la
#   MISMA intencion es idempotente en el motor; con otros datos,
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. El motivo lo exige el motor
#   (MOTIVO_AUSENTE).
#   EdicionHecho: elegibilidad visible (actividad/edicion.py), informativa.
# Version: 0.1.0 (F05-06 M1)
# Version: 0.2.0 (F05-06 M1 v1.1; Q9 opcion (a)): IntencionCorregirCategoriaV3,
#   la LISTA BLANCA del wire de «Corregir categoria» de V3: version, motivo y
#   `categoria_id` (obligatoria, sin «Sin categoria»). Cualquier otro campo
#   (importe, fecha, cuenta, pagador, descripcion, concepto, notas, tipo,
#   atribucion, efecto...) es 422 antes de llegar al adaptador. EdicionHecho
#   anade `categoria` y `acciones.corregir_categoria`, ambos None fuera de V3.
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

LONGITUD_MOTIVO = 200


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("motivo", mode="before", check_fields=False)
    @classmethod
    def _motivo(cls, valor):
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


class IntencionCorregirPago(_Estricto):
    intencion_id: uuid.UUID
    row_version: int = Field(ge=1)
    movimiento_row_version: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    error_de_registro: StrictBool
    importe: decimal.Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    fecha: dt.date | None = None
    cuenta_id: uuid.UUID | None = None


class IntencionCorregirTransferencia(_Estricto):
    intencion_id: uuid.UUID
    row_version: int = Field(ge=1)
    movimientos_row_version: dict[uuid.UUID, int]
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    error_de_registro: StrictBool
    importe: decimal.Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    fecha: dt.date | None = None
    cuenta_origen_id: uuid.UUID | None = None
    cuenta_destino_id: uuid.UUID | None = None


class IntencionAnularDuplicado(_Estricto):
    intencion_id: uuid.UUID
    row_version: int = Field(ge=1)
    movimientos_row_version: dict[uuid.UUID, int]
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    duplicado_declarado: StrictBool  # sin defecto: declaracion explicita


class IntencionCorregirCategoriaV3(_Estricto):
    intencion_id: uuid.UUID
    row_version: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    categoria_id: uuid.UUID


class AccionEdicion(BaseModel):
    disponible: bool
    codigo: str | None
    motivo: str | None


class CuentaEdicion(BaseModel):
    id: uuid.UUID
    nombre: str | None


class MovimientoEdicion(BaseModel):
    movimiento_id: uuid.UUID
    row_version: int
    pata: Literal["SALIDA", "ENTRADA"]
    cuenta: CuentaEdicion
    importe: str | None
    fecha: dt.date


class AnuladoEdicion(BaseModel):
    fecha: dt.date | None
    motivo: str | None


class AccionesEdicion(BaseModel):
    corregir: AccionEdicion
    anular_duplicado: AccionEdicion
    corregir_categoria: AccionEdicion | None = None


class CategoriaEdicion(BaseModel):
    efecto_id: uuid.UUID
    naturaleza: Literal["GASTO", "INGRESO"]
    categoria_id: uuid.UUID | None
    nombre: str | None


class EdicionHecho(BaseModel):
    hecho_id: uuid.UUID
    row_version: int
    estado: str
    tipo: str
    importe: str | None
    fecha: dt.date
    moneda: str
    origen_v3: bool
    anulado: AnuladoEdicion | None
    movimientos: list[MovimientoEdicion]
    categoria: CategoriaEdicion | None = None
    acciones: AccionesEdicion


class ResultadoEdicion(BaseModel):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    row_version: int
    estado: str
    idempotente: bool
