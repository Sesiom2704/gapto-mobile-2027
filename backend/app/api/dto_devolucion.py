# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_devolucion.py
# Ruta: backend/app/api/dto_devolucion.py
# Descripcion: DTO HTTP de la devolucion contextual D-194 (F05-06 M2; F05
#   §14, §51.2; lamina DEV v0.1, F09 §12.105). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#
#   - IntencionDevolucion: POST /v1/hechos/{origen_id}/devoluciones. Sin
#     naturaleza ni tipo en el wire: una devolucion de un gasto es SIEMPRE un
#     GASTO de signo contrario (INV-05); cualquier campo extra (p. ej.
#     «tipo»: «INGRESO») es 422 por `extra="forbid"`. Sin categoria en el
#     wire: es la del efecto del origen («De la compra», D-DEV-02), que el
#     adaptador lee bajo el lock del origen. El abono es una decision aparte
#     (D-DEV-03): PENDIENTE (sin movimiento ni liquidez) o COBRADO con cuenta y
#     fecha reales.
#   - IntencionAbono: POST /v1/hechos/{devolucion_id}/abono («Registrar
#     abono», D-DEV-07, P-DEV-04): cuenta y fecha reales; el importe es el de
#     la devolucion (un importe distinto no es este abono, DAY-RULE-03).
#   - Lectura del contexto de devolucion de un origen (A4).
# Version: 0.1.0 (F05-06 M2-A §A2-§A4)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal, Union

from pydantic import Field

from app.api.dto_registro import AtribucionRegistro, _ConNota, _Estricto


class AbonoPendiente(_Estricto):
    """«Todavía no»: la devolucion existe; no hay movimiento ni liquidez."""

    estado: Literal["PENDIENTE"]


class AbonoCobrado(_Estricto):
    """«Ya cobrado» en `cuenta_id` el `fecha` (P-DEV-02: propuesta la cuenta
    de la compra, editable). OP-08 + OP-09 en la misma transaccion."""

    estado: Literal["COBRADO"]
    cuenta_id: uuid.UUID
    fecha: dt.date


Abono = Annotated[Union[AbonoPendiente, AbonoCobrado], Field(discriminator="estado")]


class IntencionDevolucion(_ConNota):
    intencion_id: uuid.UUID
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    fecha_hecho: dt.date  # fecha de la devolucion (el mes en que reduce el gasto)
    atribucion: AtribucionRegistro  # SOLO_MIO solo si el origen lo demuestra (P-DEV-01)
    abono: Abono


class IntencionAbono(_Estricto):
    intencion_id: uuid.UUID
    cuenta_id: uuid.UUID
    fecha: dt.date


class ResultadoDevolucionHttp(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    origen_id: uuid.UUID
    idempotente: bool
    importe: str
    moneda: str
    estado_atribucion: Literal["COMPLETA", "NO_DISPONIBLE"]
    abono: Literal["PENDIENTE", "COBRADO"]
    devuelto: str
    queda: str
    aviso: str


class ResultadoAbonoHttp(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    movimiento_id: uuid.UUID
    idempotente: bool
    importe: str
    abono: Literal["COBRADO"]
    aviso: str


# ------------------------------------------------------------------ lecturas (A4)
class DevolucionDeOrigen(_Estricto):
    hecho_id: uuid.UUID
    fecha_hecho: dt.date
    importe: str
    abono: Literal["PENDIENTE", "COBRADO"]


class CuentaPropuesta(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str


class ContextoDevolucion(_Estricto):
    """Lo que el formulario necesita del origen (D-DEV-02) y si se puede
    registrar una devolucion (P-DEV-05/06), con el motivo si no."""

    origen_id: uuid.UUID
    fecha_hecho: dt.date
    nota: str | None
    tercero: str | None
    categoria_id: uuid.UUID | None
    categoria: str | None
    importe_total: str
    devuelto: str
    queda: str
    neto: str  # derivado, no se guarda (D-DEV-05)
    devoluciones: list[DevolucionDeOrigen]
    disponible: bool
    motivo: str | None
    atribucion_propuesta: AtribucionRegistro
    tuya_disponible: bool
    cuenta_compra: CuentaPropuesta | None
