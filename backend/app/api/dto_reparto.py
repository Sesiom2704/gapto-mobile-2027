# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_reparto.py
# Ruta: backend/app/api/dto_reparto.py
# Descripcion: DTO de F05-06 M3 · Reparto, pagador real y posiciones (lamina
#   REP v0.2; F05 §51.2 fila M3, §57 F05-D043). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#   - Gasto compartido de UNA sola llamada (OP-22): reparto por personas,
#     pagador real (una cuenta Gapto o «Otra persona») y posiciones SOLO con
#     un «Sí» explicito (INV-04, D-REP-02/05). Nada se deduce: ni la deuda por
#     pagar por otro, ni el derecho por haber pagado de mas.
#   - G3: lo que no se conoce queda «sin indicar» (PARCIAL); nunca se rellena
#     a cero ni se completa solo.
#   - Cobro (OP-14), pago (OP-12B) y perdon (condonacion) de una posicion.
#   - «Corregir reparto» (§57.1.1, opcion A): WHITELIST estricta, solo nuevos
#     importes de atribuciones existentes (AJ-M3-DEC-09).
#   extra="forbid" en todo: un campo fuera de contrato es 422.
# Version: 0.1.0 (F05-06 M3 §A2, §A4, §A5)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from app.api.dto_registro import _ConNota, _Estricto
from app.api.dto_vs01 import CategoriaSeleccionada, CategoriaVs01

Importe = Annotated[decimal.Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


# ------------------------------------------------------------------ pagador
class PagadoConCuenta(_Estricto):
    """D-REP-01: pague yo, desde una cuenta Gapto (movimiento real)."""

    tipo: Literal["CUENTA"]
    cuenta_id: uuid.UUID


class PagadoPorPersona(_Estricto):
    """D-REP-01/02: «Otra persona» pago; no sale dinero de mis cuentas. La
    deuda solo nace con «SI» (INV-04); «NO_LO_SE» no la crea (P-REP-01)."""

    tipo: Literal["PERSONA"]
    tercero_id: uuid.UUID
    le_debo: Literal["SI", "NO", "NO_LO_SE"]


Pagador = Annotated[Union[PagadoConCuenta, PagadoPorPersona], Field(discriminator="tipo")]


# ------------------------------------------------------------------ reparto
class RepartoSoloMio(_Estricto):
    modo: Literal["SOLO_MIO"]


class ParteDePersona(_Estricto):
    """Parte de una persona (P-REP-05: tercero PERSONA). `importe` None = sin
    indicar (G3). `me_debe` solo cuando pague yo: «SI» crea el derecho de cobro
    (D-REP-05); «NO» es invitado."""

    tercero_id: uuid.UUID
    importe: Importe | None = None
    me_debe: Literal["SI", "NO"] | None = None


class RepartoEntrePersonas(_Estricto):
    modo: Literal["REPARTIR"]
    mi_parte: Importe | None = None
    partes: list[ParteDePersona] = Field(min_length=1, max_length=20)


Reparto = Annotated[Union[RepartoSoloMio, RepartoEntrePersonas], Field(discriminator="modo")]


class IntencionGastoCompartido(_ConNota):
    intencion_id: uuid.UUID
    importe: Importe
    moneda: Literal["EUR"]
    fecha_hecho: dt.date
    presupuestable: bool
    categoria: CategoriaVs01
    tercero_id: uuid.UUID | None = None  # el comercio («Peluqueria Lola», VENDEDOR)
    pagado_por: Pagador
    reparto: Reparto

    @property
    def categoria_id(self) -> uuid.UUID | None:
        return self.categoria.categoria_id if isinstance(self.categoria, CategoriaSeleccionada) else None

    @property
    def magnitudes(self):
        return self.categoria.magnitudes if isinstance(self.categoria, CategoriaSeleccionada) else ()

    @property
    def magnitudes_desconocidas(self):
        return self.categoria.desconocidas if isinstance(self.categoria, CategoriaSeleccionada) else ()

    @property
    def partes(self) -> list[ParteDePersona]:
        return self.reparto.partes if isinstance(self.reparto, RepartoEntrePersonas) else []

    @property
    def mi_parte(self) -> decimal.Decimal | None:
        if isinstance(self.reparto, RepartoSoloMio):
            return self.importe
        return self.reparto.mi_parte

    @model_validator(mode="after")
    def _coherencia(self) -> "IntencionGastoCompartido":
        terceros = [p.tercero_id for p in self.partes]
        if len(set(terceros)) != len(terceros):
            raise ValueError("Una persona aparece dos veces en el reparto.")
        if self.tercero_id is not None and self.tercero_id in terceros:
            raise ValueError("El comercio del gasto no puede ser una persona del reparto.")
        conocidas = [p.importe for p in self.partes if p.importe is not None]
        if isinstance(self.reparto, RepartoEntrePersonas) and self.reparto.mi_parte is not None:
            conocidas.append(self.reparto.mi_parte)
        if sum(conocidas, decimal.Decimal(0)) > self.importe:
            raise ValueError("El reparto supera el total del gasto.")
        paga_persona = isinstance(self.pagado_por, PagadoPorPersona)
        for parte in self.partes:
            if parte.me_debe is not None and paga_persona:
                raise ValueError("«Te deben su parte» solo aplica si pagaste tú.")
            if parte.me_debe == "SI" and parte.importe is None:
                raise ValueError("Para que te deban su parte hay que indicar cuánto es.")
        if paga_persona and self.pagado_por.le_debo == "SI" and self.mi_parte is None:
            raise ValueError("Para deberle tu parte hay que indicar cuánto es.")
        return self


class PosicionCreadaHttp(_Estricto):
    entidad_id: uuid.UUID
    tipo: Literal["DERECHO_COBRO", "OBLIGACION_PAGO"]
    tercero_id: uuid.UUID
    importe: str


class ResultadoGastoCompartidoHttp(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    idempotente: bool
    importe: str
    moneda: str
    estado_atribucion: Literal["COMPLETA", "PARCIAL", "NO_DISPONIBLE"]
    tu_parte: str | None
    movimiento: str | None  # movimiento real de tus cuentas; None si pago otra persona
    posiciones: list[PosicionCreadaHttp]
    aviso: str


# ------------------------------------------------------------------ cobro, pago y perdon
class IntencionCobroPago(_Estricto):
    """Cobro de un derecho (OP-14) o pago de una obligacion (OP-12B): cuenta
    Gapto obligatoria, Efectivo incluido (F04-D052); parcial permitido."""

    intencion_id: uuid.UUID
    importe: Importe
    cuenta_id: uuid.UUID
    fecha: dt.date


class IntencionPerdon(_Estricto):
    """Perdon (condonacion) de una posicion: no mueve dinero (F04-D052)."""

    intencion_id: uuid.UUID
    importe: Importe
    fecha: dt.date


class ResultadoPosicionHttp(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    entidad_id: uuid.UUID
    idempotente: bool
    importe: str
    saldo: str | None  # None = «Sin determinar» (D-REP-09)
    estado: Literal["ACTIVA", "CERRADA"]
    aviso: str


# ------------------------------------------------------------------ Pendiente con <persona>
class PosicionPendiente(_Estricto):
    entidad_id: uuid.UUID
    entidad_row_version: int
    tipo: Literal["DERECHO_COBRO", "OBLIGACION_PAGO"]
    nombre: str | None
    saldo: str | None  # None = «Sin determinar»
    estado: Literal["ACTIVA", "CERRADA"]
    origen_hecho_id: uuid.UUID | None
    origen_fecha: dt.date | None
    origen_concepto: str | None
    origen_tercero: str | None = None  # comercio del gasto de origen (lamina C1)


class PendienteConPersona(_Estricto):
    """D-REP-07/09; OP-20: el neto es una LECTURA informativa que no salda
    nada; con algun saldo desconocido es «Sin determinar», nunca 0."""

    tercero_id: uuid.UUID
    nombre: str
    te_debe: str | None
    le_debes: str | None
    neto: str | None
    neto_estado: Literal["DETERMINADO", "INDETERMINADO", "SIN_POSICIONES"]
    posiciones: list[PosicionPendiente]
    aviso: str


# ------------------------------------------------------------------ Corregir reparto (§57.1.1)
class NuevaParte(_Estricto):
    atribucion_id: uuid.UUID
    importe: Importe  # nunca cero: quitar a alguien es una baja, fuera de v1


class IntencionCorregirReparto(_Estricto):
    """Solo importes de atribuciones que ya existen (AJ-M3-DEC-09). Altas,
    bajas, invitado -> deudor y reasignaciones quedan fuera (§57.1.1)."""

    row_version: int = Field(ge=1)
    motivo: str = Field(min_length=1, max_length=500)
    partes: list[NuevaParte] = Field(min_length=1, max_length=21)

    @model_validator(mode="after")
    def _sin_repetidas(self) -> "IntencionCorregirReparto":
        ids = [p.atribucion_id for p in self.partes]
        if len(set(ids)) != len(ids):
            raise ValueError("Una parte aparece dos veces.")
        if not self.motivo.strip():
            raise ValueError("El motivo es obligatorio.")
        return self


class ResultadoCorreccionRepartoHttp(_Estricto):
    hecho_id: uuid.UUID
    row_version: int
    tu_parte: str | None
    posiciones: list[PosicionCreadaHttp]
    aviso: str


class PosicionDeParteHttp(_Estricto):
    entidad_id: uuid.UUID
    tipo: Literal["DERECHO_COBRO", "OBLIGACION_PAGO"]
    saldo: str | None  # None = «Sin determinar»


class ParteDeHechoHttp(_Estricto):
    atribucion_id: uuid.UUID
    es_yo: bool
    tercero_id: uuid.UUID | None
    nombre: str
    importe: str
    posicion: PosicionDeParteHttp | None


class RepartoDeHecho(_Estricto):
    """Lectura sin locks para «Corregir reparto» (E6). `corregible` solo
    sirve para mostrar; la correccion revalida la whitelist bajo lock."""

    hecho_id: uuid.UUID
    row_version: int
    importe: str
    estado_atribucion: Literal["COMPLETA", "PARCIAL", "NO_DISPONIBLE"]
    corregible: bool
    motivo: Literal["TIPO_NO_ADMITIDO", "ORIGEN_IMPORTADO", "NO_ACTIVO", "SIN_REPARTO"] | None
    partes: list[ParteDeHechoHttp]


# ------------------------------------------------------------------ Elegibilidad de anulacion (iii)
class ElegibilidadAnulacion(_Estricto):
    """Lectura sin escritura ni locks (AJ-M3-DEC-04): la UI solo ofrece lo
    que el motor considera elegible. La operacion revalida bajo lock."""

    hecho_id: uuid.UUID
    elegible: bool
    motivos: list[Literal["TESORERIA", "DEPENDENCIAS_ACTIVAS", "POSICIONES", "NO_ACTIVO", "ORIGEN_IMPORTADO"]]
