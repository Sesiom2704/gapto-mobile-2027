# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_prevision.py
# Ruta: backend/app/api/dto_prevision.py
# Descripcion: DTO de F05-06 M5 · Confirmacion de previsiones (F05 §59
#   F05-D044; D-M5-03..07, D-M5-15; lamina PREV v0.2 y HOME-01 v0.4). API DE
#   INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   WHITELIST PROPIA (AJ de Q1): cada modelo enumera sus campos con
#   `extra="forbid"`, independiente de lo que exporten lecturas.py o el motor.
#   Ninguna entrada crea, cancela, corrige, retira ni recalcula previsiones.
#
#   - BloquePrevision: viaja OPCIONAL en gasto, ingreso, transferencia y gasto
#     compartido. `marcar_realizada` es OBLIGATORIO y estricto, sin defecto
#     (falta o no booleano -> 422; D-M5-04).
#   - IntencionVincular («Ya lo registre», OP-17 suelto): `importe_a_vincular`
#     es el que el usuario vio en la confirmacion (AJ-M5-DEC-05).
#   - IntencionOmitir («No hubo este mes»): motivo opcional.
#   Estos tres no dependen de dto_registro ni de dto_vs01 (que los importan).
# Version: 0.1.0 (F05-06 M5 §A3-§A5)
# Version: 0.2.0 (F05-06 M5-B; F05-D047 §61.1; F04-D065): IntencionDarPorCubierta y
#   IntencionReabrir (motivo obligatorio en el motor; reabrir con la version
#   del sucesor RODANTE cuando la lectura lo devuelve) y ResultadoTransicion.
#   El detalle anade `pendiente` (esperado - registrado ACTIVO, con signo;
#   derivado, nunca persistido), `recalculable` (Q4, informativo: la UI no lo
#   ofrece), `sucesor` (id y row_version del sucesor RODANTE ABIERTO) y las
#   acciones `dar_por_cubierta` y `reabrir`.
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


class BloquePrevision(_Estricto):
    """Registro desde la prevision (OP-22 u OP-10 + OP-17)."""

    prevision_id: uuid.UUID
    row_version: int = Field(ge=1)
    marcar_realizada: StrictBool  # sin defecto: siempre una decision explicita


class IntencionVincular(_Estricto):
    intencion_id: uuid.UUID  # = vinculo_id (D-M5-06)
    row_version: int = Field(ge=1)
    hecho_id: uuid.UUID
    importe_a_vincular: decimal.Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    marcar_realizada: StrictBool


class IntencionDarPorCubierta(_Estricto):
    intencion_id: uuid.UUID  # solo para el uuid del sucesor RODANTE (sin replay de exito, como omitir)
    row_version: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)  # obligatorio: lo exige el motor

    @field_validator("motivo", mode="before")
    @classmethod
    def _motivo(cls, valor):
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


class IntencionReabrir(_Estricto):
    intencion_id: uuid.UUID
    row_version: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)  # obligatorio: lo exige el motor
    sucesor_row_version: int | None = Field(default=None, ge=1)

    @field_validator("motivo", mode="before")
    @classmethod
    def _motivo(cls, valor):
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


class IntencionOmitir(_Estricto):
    intencion_id: uuid.UUID  # solo para el uuid del sucesor RODANTE (no hay replay de exito)
    row_version: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)

    @field_validator("motivo", mode="before")
    @classmethod
    def _motivo(cls, valor):
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


# ------------------------------------------------------------------ lecturas
Tipo = Literal["GASTO", "INGRESO", "TRANSFERENCIA"]
Naturaleza = Literal["POR_PAGAR", "POR_COBRAR", "ENTRE_CUENTAS"]


class Ref(_Estricto):
    id: uuid.UUID
    nombre: str


class RefCategoria(_Estricto):
    id: uuid.UUID
    nombre: str
    ruta: str


class FilaPrevision(_Estricto):
    id: uuid.UUID
    row_version: int
    estado: str
    tipo: str
    naturaleza: Naturaleza | None
    concepto: str
    tercero: Ref | None
    categoria: RefCategoria | None
    fecha_desde: dt.date | None
    fecha_hasta: dt.date | None
    moneda: str
    importe_esperado: str | None  # None = «Desconocido», nunca 0
    cubierto: str
    queda: str | None
    desviacion: str | None
    con_realidad: bool
    pagos: int
    vencida: bool
    cuenta_salida: Ref | None
    cuenta_entrada: Ref | None
    origen: Literal["MANUAL", "REGLA", "V3"]
    presupuestable: bool  # propuesta «De la prevision» del registro


class RequiereAtencion(_Estricto):
    n: int
    primeras: list[FilaPrevision]


class InicioPrevisiones(_Estricto):
    hoy: dt.date
    requiere_atencion: RequiereAtencion
    proximos: list[FilaPrevision]
    aviso: str


class ImportePorNaturaleza(_Estricto):
    importe: str | None  # None si todas tienen el esperado desconocido (nunca 0)
    n: int
    desconocidos: int


class Secciones(_Estricto):
    vencidas: list[FilaPrevision]
    con_pago_parcial: list[FilaPrevision]
    sin_fecha: list[FilaPrevision]


class PendientesPrevisiones(_Estricto):
    hoy: dt.date
    n: int
    por_pagar: ImportePorNaturaleza
    por_cobrar: ImportePorNaturaleza
    secciones: Secciones
    aviso: str


class Accion(_Estricto):
    disponible: bool
    motivo: str | None


class Acciones(_Estricto):
    registrar: Accion
    ya_lo_registre: Accion
    omitir: Accion
    swipe: Accion
    dar_por_cubierta: Accion
    reabrir: Accion


class Sucesor(_Estricto):
    id: uuid.UUID
    row_version: int


class VinculoActivo(_Estricto):
    vinculo_id: uuid.UUID
    hecho_id: uuid.UUID
    importe_asignado: str
    fecha_hecho: dt.date
    concepto: str | None
    importe_total: str | None


class DetallePrevision(FilaPrevision):
    estado_derivado: Literal["REALIZADA_SIN_REALIDAD_ACTIVA", "REQUIERE_REVISION"] | None
    vinculos: list[VinculoActivo]
    acciones: Acciones
    pendiente: str | None
    recalculable: bool
    sucesor: Sucesor | None
    aviso: str


class Candidato(_Estricto):
    hecho_id: uuid.UUID
    fecha_hecho: dt.date
    concepto: str | None
    tercero: str | None
    categoria: str | None
    cuenta: str | None
    importe_total: str
    porcion_disponible: str  # lo que se vinculara (toda la porcion libre)


class CandidatosPrevision(_Estricto):
    prevision_id: uuid.UUID
    ampliado: bool
    ventana_dias: int
    mensaje: str | None
    candidatos: list[Candidato]
    aviso: str


# ------------------------------------------------------------------ resultados de escritura
class ResultadoVinculo(_Estricto):
    intencion_id: uuid.UUID
    prevision_id: uuid.UUID
    hecho_id: uuid.UUID
    importe_vinculado: str
    estado: str
    row_version: int
    idempotente: bool
    aviso: str


class ResultadoTransicion(_Estricto):
    intencion_id: uuid.UUID
    prevision_id: uuid.UUID
    estado: str
    row_version: int
    aviso: str


class ResultadoOmitir(_Estricto):
    intencion_id: uuid.UUID
    prevision_id: uuid.UUID
    estado: str
    row_version: int
    aviso: str
