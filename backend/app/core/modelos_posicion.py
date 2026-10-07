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
# Version: 0.4.0
#   0.4.0 (F04-D055 B1): A2, `MOTIVOS_CIERRE_RUNTIME` = {LIQUIDADA,
#   CONDONADA}; CANCELADA y OTRO siguen en `MOTIVOS_CIERRE` solo como datos
#   legacy legibles. A4, `ResultadoPosicion.apertura_indeterminada`: indicador
#   contractual separado del saldo (no viaja por `saldo.importe`).
# Version: 0.3.0
#   0.3.0 (F04-D052 B2): causa de reduccion obligatoria. `CausaReduccion`
#   {PAGO, COBRO, CONDONACION} sustituye al antiguo `motivo` libre de
#   `DatosDeltaPosicion`, que ningun write-path leia (R-F04-037). La causa NO
#   se persiste: la determinan arquetipo y movimiento, y en lectura se
#   reconstruye con `CAUSA_NO_DETERMINABLE` para las reducciones con
#   `GENERACION_DERECHO_OBLIGACION` (historicas o migradas). Nuevos
#   `TIPO_HECHO_CONDONACION` (D-201) y `DatosCondonacionObligacion` (INGRESO
#   solo declarado, F04-D052).
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
import enum
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
# F04-D055 A2. Los cierres de runtime solo escriben estos dos. CANCELADA y
# OTRO no tienen semantica canonica: quedan legibles como legacy y no se
# escriben nunca mas.
MOTIVOS_CIERRE_RUNTIME: Final = frozenset({MOTIVO_LIQUIDADA, MOTIVO_CONDONADA})

TIPO_ENTIDAD_POSICION: Final = "DERECHO_OBLIGACION"
RELACION_ENTIDAD_GENERADO_POR: Final = "GENERADO_POR"
RELACION_HECHO_REEMBOLSO_DE: Final = "REEMBOLSO_DE"

TIPO_HECHO_POSICION: Final = "GENERACION_DERECHO_OBLIGACION"
TIPO_HECHO_REEMBOLSO: Final = "REEMBOLSO"
# D-201 (migration 0350). Solo lo escriben las condonaciones posteriores a
# F04-D052: ningun dato anterior ni migrado puede tenerlo.
TIPO_HECHO_CONDONACION: Final = "CONDONACION"


class CausaReduccion(str, enum.Enum):
    """Vocabulario CERRADO de causas de reduccion (F04-D052).

    Cada causa tiene una sola forma fisica:
      PAGO        obligacion -> REEMBOLSO + movimiento en cuenta Gapto
      COBRO       derecho    -> REEMBOLSO + movimiento en cuenta Gapto
      CONDONACION ambos      -> CONDONACION sin movimiento
    Cada operacion acepta solo la suya. No hay causa mixta: pago y
    condonacion de una misma realidad son operaciones separadas.
    """

    PAGO = "PAGO"
    COBRO = "COBRO"
    CONDONACION = "CONDONACION"


# Lectura (F04-D052, CC4). Una reduccion con GENERACION_DERECHO_OBLIGACION se
# lee asi. Es una condicion de LECTURA: no se persiste en ningun sitio y no se
# usan la fecha ni la procedencia de importacion para afinarla.
CAUSA_NO_DETERMINABLE: Final = "NO_DETERMINABLE"


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

    `causa` es obligatoria (F04-D052): sin ella, o con una que no sea la de
    la operacion, el motor rechaza antes de escribir. No tiene valor por
    defecto util a proposito: None significa "no declarada" y es STOP.
    """

    hecho_id: uuid.UUID
    efecto_id: uuid.UUID
    vinculo_id: uuid.UUID
    importe: decimal.Decimal | None
    fecha_hecho: dt.date | None
    concepto: str | None = None
    causa: CausaReduccion | None = None
    cierre: DatosCierre | None = None


@dataclass(frozen=True, slots=True)
class DatosTesoreriaReembolso:
    """Tesoreria de un pago (OP-12B) o cobro (OP-14) propio: crear el
    movimiento en una cuenta Gapto, o consumir uno ACTIVO existente.

    Nunca se elige el movimiento automaticamente por importe, fecha, cuenta o
    contraparte: la decision es del llamante. Desde F04-D052 un pago o cobro
    propio sin cuenta Gapto ya no se admite (EFECTIVO es una cuenta valida):
    la rama "fuera de cuentas registradas" de F04-D015 §4 queda superada para
    operaciones nuevas y el motor no fabrica movimientos.
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
class DatosCondonacionObligacion:
    """Entrada de la condonacion de una OBLIGACION_PAGO (F04-D052).

    Arquetipo CONDONACION y sin tesoreria. INGRESO por defecto CERO: solo
    existe si el llamante declara `importe_ingreso` en ESTA misma operacion,
    mayor que cero y no superior a lo condonado. Como maximo uno por hecho de
    condonacion; no hay via para anadirlo despues. Con INGRESO el hecho deja
    de ser puramente posicional y rige el mismo contrato que el GASTO
    declarado de `DatosCondonacion` (R1+R2 v0.3 §8 + E01): `presupuestable`
    explicito y localizacion aplicable (NO_APLICA invalido).
    """

    delta: DatosDeltaPosicion
    importe_ingreso: decimal.Decimal | None = None
    efecto_ingreso_id: uuid.UUID | None = None
    presupuestable: bool | None = None
    estado_localizacion: str | None = None
    localidad_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CausaLeida:
    """Causa reconstruida en lectura de una reduccion de posicion.

    `causa` es un valor de `CausaReduccion` o `CAUSA_NO_DETERMINABLE`. Nunca
    se persiste: sale de arquetipo + presencia de movimiento.
    """

    hecho_id: uuid.UUID
    tipo_hecho: str
    con_movimiento: bool
    causa: str


@dataclass(frozen=True, slots=True)
class ResultadoPosicion:
    """Lectura de una posicion (F04-D055 A4).

    `saldo` es el saldo de LECTURA: en una ACTIVA es el canonico (conocido o
    INDETERMINADO, INV-17); en una CERRADA es siempre conocido 0, tambien en
    una legacy con residual, sin reinterpretar sus deltas.

    `apertura_indeterminada` es True solo si estado = CERRADA y
    saldo_apertura IS NULL: el 0 actual no es conocimiento del saldo
    historico. Es False en una ACTIVA, donde la indeterminacion ya la expresa
    `saldo`. Ningun validador lee este DTO.
    """

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
    apertura_indeterminada: bool = False
