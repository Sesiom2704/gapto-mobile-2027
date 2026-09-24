# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_posicion.py
# Ruta: backend/app/core/modelos_posicion.py
# Descripcion: DTO internos de F04-04: alta de posicion, reduccion, reembolso,
#   condonacion y cierre.
#
#   La pieza central de este modulo es `Saldo`. Un saldo puede ser CONOCIDO o
#   INDETERMINADO, y son estados distintos, no un numero y su ausencia:
#
#     - CONOCIDO      saldo_apertura + suma de deltas ACTIVOS compatibles.
#     - INDETERMINADO saldo_apertura IS NULL. Sigue siendo indeterminado
#                     AUNQUE existan deltas posteriores.
#
#   Por eso el saldo no se representa con `Decimal | None`: con esa forma, un
#   `None` acaba tarde o temprano en una resta y se convierte en cero. Una
#   posicion historica desconocida sobre la que se observa un reembolso de 20
#   NO vale -20: vale INDETERMINADO. `Saldo.importe` solo es accesible cuando
#   `conocido` es True, y pedirlo en otro caso levanta error en vez de devolver
#   un numero inventado (INV-17).
#
#   `importe_original_documentado` NO es saldo. Es lo que decia el documento de
#   origen y puede no tener ninguna relacion con lo que queda vivo.
#
#   Todas las identidades llegan reservadas por el llamante, antes del primer
#   intento: es lo que permite reintentar una operacion compuesta —hecho,
#   efecto, vinculo, movimiento, conciliacion, relacion— sin duplicar realidad.
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 §8 + E01, SOLO `DatosCondonacion`): cuando
#   la condonacion declara el GASTO soportado, el hecho resultante contiene
#   GASTO y deja de ser puramente posicional. Se anaden `presupuestable`,
#   `estado_localizacion` y `localidad_id` para que el llamante exprese la
#   decision historica y la localizacion, en vez de heredar los valores fijos
#   de posicion (`false` / `NO_APLICA`). Ningun otro DTO cambia.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Final

CERO: Final = decimal.Decimal("0")

TIPO_DERECHO: Final = "DERECHO_COBRO"
TIPO_OBLIGACION: Final = "OBLIGACION_PAGO"
TIPOS_POSICION: Final = frozenset({TIPO_DERECHO, TIPO_OBLIGACION})

# Compatibilidad de naturaleza (seccion 9 del mandato). Es regla de SERVICIO:
# PostgreSQL no la garantiza, de modo que sin esta tabla un derecho podria
# alimentarse de efectos DEUDA y el saldo dejaria de significar nada.
EFECTO_DE_POSICION: Final = {
    TIPO_DERECHO: "DERECHO_COBRO",
    TIPO_OBLIGACION: "DEUDA",
}

JUSTIFICACION_DECISION: Final = "DECISION_EXPLICITA"
JUSTIFICACION_REGLA: Final = "REGLA"
JUSTIFICACION_CONTRATO: Final = "CONTRATO"
JUSTIFICACIONES: Final = frozenset(
    {JUSTIFICACION_DECISION, JUSTIFICACION_REGLA, JUSTIFICACION_CONTRATO}
)

ESTADO_ACTIVA: Final = "ACTIVA"
ESTADO_CERRADA: Final = "CERRADA"

MOTIVO_LIQUIDADA: Final = "LIQUIDADA"
MOTIVO_CONDONADA: Final = "CONDONADA"
MOTIVO_CANCELADA: Final = "CANCELADA"
MOTIVO_OTRO: Final = "OTRO"
MOTIVOS_CIERRE: Final = frozenset(
    {MOTIVO_LIQUIDADA, MOTIVO_CONDONADA, MOTIVO_CANCELADA, MOTIVO_OTRO}
)

TIPO_ENTIDAD_POSICION: Final = "DERECHO_OBLIGACION"
RELACION_ENTIDAD_GENERADO_POR: Final = "GENERADO_POR"
RELACION_HECHO_REEMBOLSO_DE: Final = "REEMBOLSO_DE"

TIPO_HECHO_POSICION: Final = "GENERACION_DERECHO_OBLIGACION"
TIPO_HECHO_REEMBOLSO: Final = "REEMBOLSO"


class SaldoIndeterminado(Exception):
    """Se pidio el importe de un saldo que no se conoce.

    Es una excepcion interna del motor, no un error de dominio: significa que
    una rama del codigo intento operar con un numero donde no lo hay. Si
    aparece hacia el llamante, hay un fallo de programacion, no un caso de uso.
    """


@dataclass(frozen=True, slots=True)
class Saldo:
    """Saldo de una posicion: conocido con importe, o indeterminado."""

    conocido: bool
    _importe: decimal.Decimal | None = None

    @classmethod
    def de(cls, importe: decimal.Decimal) -> "Saldo":
        return cls(True, decimal.Decimal(importe))

    @classmethod
    def indeterminado(cls) -> "Saldo":
        return cls(False, None)

    @property
    def importe(self) -> decimal.Decimal:
        if not self.conocido or self._importe is None:
            raise SaldoIndeterminado(
                "El saldo de esta posicion es indeterminado: no admite "
                "aritmetica. Tratarlo como cero falsearia el historico."
            )
        return self._importe

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuracion
        return f"Saldo({self._importe})" if self.conocido else "Saldo(INDETERMINADO)"


@dataclass(frozen=True, slots=True)
class DatosAltaPosicion:
    """Entrada de OP-12A.

    `saldo_apertura=0` con `fecha_inicio_seguimiento` es el alta ordinaria de
    una posicion con seguimiento completo. `saldo_apertura=None` queda
    reservado a historicos y migraciones: el flujo runtime no debe producirlo
    por descuido, y por eso no es el valor por defecto de nada.
    """

    entidad_id: uuid.UUID
    nombre: str | None
    tipo: str | None
    contraparte_actor_id: uuid.UUID | None
    moneda: str | None
    justificacion: str | None
    fecha_inicio_seguimiento: dt.date | None
    saldo_apertura: decimal.Decimal | None
    # Causa: o se engancha a un hecho existente, o se crea uno propio.
    hecho_id: uuid.UUID | None = None
    hecho_row_version_esperada: int | None = None
    fecha_hecho: dt.date | None = None
    concepto: str | None = None
    # Identidades reservadas de los artefactos creados.
    efecto_id: uuid.UUID | None = None
    vinculo_id: uuid.UUID | None = None
    importe_inicial: decimal.Decimal | None = None
    importe_original_documentado: decimal.Decimal | None = None
    notas: str | None = None


@dataclass(frozen=True, slots=True)
class DatosCierre:
    """Declaracion explicita de cierre. Nunca se deduce de que el saldo sea 0."""

    motivo_cierre: str
    fecha_cierre: dt.date


@dataclass(frozen=True, slots=True)
class DatosDeltaPosicion:
    """Entrada comun de un movimiento explicito de posicion.

    `importe` es SIEMPRE magnitud positiva. El signo lo pone el write-path
    segun la operacion, porque el significado financiero vive en el efecto
    firmado y no en lo que teclee el llamante.
    """

    hecho_id: uuid.UUID
    efecto_id: uuid.UUID
    vinculo_id: uuid.UUID
    importe: decimal.Decimal | None
    fecha_hecho: dt.date | None
    concepto: str | None = None
    motivo: str | None = None
    cierre: DatosCierre | None = None


@dataclass(frozen=True, slots=True)
class DatosTesoreriaReembolso:
    """Tesoreria del reembolso: crear movimiento, o consumir uno existente.

    Nunca se elige el movimiento automaticamente por importe, fecha, cuenta o
    contraparte: la decision es del llamante. Y si el cobro ocurrio fuera de
    cuentas registradas, simplemente no hay movimiento.
    """

    conciliacion_id: uuid.UUID
    movimiento_id: uuid.UUID
    # None = consumir el movimiento existente identificado por movimiento_id.
    cuenta_id: uuid.UUID | None = None
    fecha_movimiento: dt.date | None = None
    descripcion: str | None = None
    movimiento_row_version_esperada: int | None = None

    @property
    def crea_movimiento(self) -> bool:
        return self.cuenta_id is not None


@dataclass(frozen=True, slots=True)
class DatosReembolso:
    """Entrada de OP-14."""

    delta: DatosDeltaPosicion
    tesoreria: DatosTesoreriaReembolso | None = None
    # Hecho causal del derecho, cuando se conoce. Si no, NO se inventa
    # relacion: la reduccion sigue siendo valida sin ella.
    hecho_causal_id: uuid.UUID | None = None
    relacion_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DatosCondonacion:
    """Entrada de la condonacion de un DERECHO_COBRO (F04-D015).

    El GASTO por la porcion condonada NO es automatico. Solo existe si el
    llamante declara ambas cosas: que esa porcion pasa a soportarla
    economicamente el usuario, y que ese coste no estaba ya reconocido.
    """

    delta: DatosDeltaPosicion
    declara_gasto_soportado: bool = False
    declara_coste_no_reconocido: bool = False
    efecto_gasto_id: uuid.UUID | None = None
    # Mandato F04 R1+R2 v0.3 §8 / E01. Solo con GASTO declarado: decision
    # presupuestaria explicita (sin default) y localizacion (sin dato ->
    # DESCONOCIDA; NO_APLICA invalido). Sin GASTO deben quedar vacios.
    presupuestable: bool | None = None
    estado_localizacion: str | None = None
    localidad_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ResultadoPosicion:
    entidad_id: uuid.UUID
    entidad_row_version: int
    tipo: str
    estado: str
    saldo: Saldo
    hecho_id: uuid.UUID | None = None
    hecho_row_version: int | None = None
    movimiento_id: uuid.UUID | None = None
    movimiento_row_version: int | None = None
    idempotente: bool = False
