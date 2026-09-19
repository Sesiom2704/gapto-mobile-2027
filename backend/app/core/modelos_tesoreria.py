# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_tesoreria.py
# Ruta: backend/app/core/modelos_tesoreria.py
# Descripcion: DTO internos de OP-06 (aportaciones reales), OP-07 (vinculo
#   aportacion-conciliacion), OP-08 (movimiento real) y OP-09 (conciliacion).
#
#   Tres separaciones que el vocabulario de estos DTO mantiene a proposito,
#   porque colapsarlas es el error clasico de un motor financiero:
#
#   - APORTACION responde "quien financio realmente esta salida". No dice quien
#     soporta el gasto (eso es atribucion, F04-02), ni de quien es la cuenta
#     (participacion), ni crea deuda entre actores (F04-04).
#   - MOVIMIENTO responde "que dinero entro o salio de una cuenta". Conserva el
#     100 % bancario y no se reparte por participacion jamas.
#   - CONCILIACION responde "que porcion de ese movimiento corresponde a este
#     hecho". No obliga a cuadrar con importe_total, ni con efectos, ni con
#     aportaciones: cada dimension conserva su propio significado.
#
#   `actor_id=None` en una aportacion significa APORTANTE REAL DESCONOCIDO.
#   Nunca se convierte en el usuario por defecto: inventar el aportante seria
#   fabricar realidad financiera.
#
#   En OP-07 no hace falta centinela: la operacion es explicitamente "vincula a
#   esta conciliacion" o "desvincula", de modo que `destino=None` significa
#   desvincular sin ambiguedad. Tener ademas un DESVINCULAR seria dar dos
#   formas de decir lo mismo.
#   0.2.0 (F04-06 B2): DatosReversion y ResultadoReversion para OP-11. El
#   importe se declara como magnitud; el signo contrario lo pone el motor.
# Version: 0.2.0
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Any, Final

CRITERIO_PARTICIPACION_CUENTA: Final = "PARTICIPACION_CUENTA"
CRITERIO_MANUAL: Final = "MANUAL"
CRITERIO_REGLA: Final = "REGLA"
CRITERIO_EXTERNA: Final = "EXTERNA"

CRITERIOS_APORTACION: Final = frozenset(
    {
        CRITERIO_PARTICIPACION_CUENTA,
        CRITERIO_MANUAL,
        CRITERIO_REGLA,
        CRITERIO_EXTERNA,
    }
)

CLASE_OPERACION: Final = "OPERACION"
CLASE_AJUSTE_SALDO: Final = "AJUSTE_SALDO"
CLASES_MOVIMIENTO: Final = frozenset({CLASE_OPERACION, CLASE_AJUSTE_SALDO})

MOVIMIENTO_ACTIVO: Final = "ACTIVO"
MOVIMIENTO_ANULADO: Final = "ANULADO"

CERO: Final = decimal.Decimal("0")


@dataclass(frozen=True, slots=True)
class DatosAportacion:
    """Una fila de `hecho_aportaciones_pago`.

    `porcentaje_aplicado` es EXPLICATIVO: documenta como se propuso el reparto,
    no lo sustituye. El importe materializado es el autoritativo y no se
    recalcula nunca a partir del porcentaje, ni cuando cambie la participacion
    de la cuenta en el futuro.
    """

    aportacion_id: uuid.UUID
    importe: decimal.Decimal
    criterio_aportacion: str
    actor_id: uuid.UUID | None = None
    porcentaje_aplicado: decimal.Decimal | None = None
    medio_pago_codigo: str | None = None
    hecho_movimiento_tesoreria_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DatosMovimiento:
    """Una fila de `movimientos_tesoreria`.

    `confirmado_at` es NOT NULL en el contrato fisico. Si el llamante lo
    aporta se preserva tal cual; si no, se usa el instante transaccional. Lo
    que NO se hace nunca es derivarlo de `fecha_movimiento`: la fecha valor del
    banco y el momento en que se confirma el apunte son cosas distintas.
    """

    movimiento_id: uuid.UUID
    cuenta_id: uuid.UUID
    fecha_movimiento: dt.date | None
    importe: decimal.Decimal | None
    clase_movimiento: str | None
    descripcion: str | None = None
    confirmado_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class DatosConciliacion:
    """Una fila de `hecho_movimientos_tesoreria`."""

    conciliacion_id: uuid.UUID
    hecho_id: uuid.UUID
    movimiento_tesoreria_id: uuid.UUID
    importe_asignado: decimal.Decimal


@dataclass(frozen=True, slots=True)
class ResultadoAportaciones:
    hecho_id: uuid.UUID
    hecho_row_version: int
    aportaciones_creadas: int = 0
    idempotente: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoVinculo:
    aportacion_id: uuid.UUID
    hecho_row_version: int
    vinculada_a: uuid.UUID | None
    sin_cambios: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoMovimiento:
    movimiento_id: uuid.UUID
    row_version: int
    idempotente: bool = False
    snapshot: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResultadoConciliacion:
    """Salida de OP-09. Devuelve AMBAS versiones porque la operacion toca dos
    raices y el llamante necesita las dos para su siguiente paso (F04-D010)."""

    conciliacion_id: uuid.UUID
    hecho_row_version: int
    movimiento_row_version: int
    idempotente: bool = False


@dataclass(frozen=True, slots=True)
class DatosReversion:
    """Entrada de OP-11.

    `importe` es una MAGNITUD POSITIVA: el signo contrario lo pone el motor a
    partir del original. Pedirselo al llamante delegaria en el una invariante
    que PostgreSQL ya impone, y un signo igual al original acabaria en un
    rechazo tecnico en vez de un error de dominio.

    `cuenta_id` se exige aunque sea deducible del original. No es redundancia:
    es la declaracion del llamante sobre DONDE cree que ocurre la reversion, y
    permite devolver CUENTA_DISTINTA en vez de aceptar en silencio una cuenta
    que el no pretendia. La FK compuesta de 0220 lo impediria igualmente, pero
    con un error que no es contrato.
    """

    reversion_id: uuid.UUID
    movimiento_original_id: uuid.UUID
    cuenta_id: uuid.UUID
    fecha_movimiento: dt.date | None
    importe: decimal.Decimal | None
    descripcion: str | None = None
    confirmado_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class ResultadoReversion:
    """Salida de OP-11.

    `revertido_acumulado` y `pendiente` son conclusiones DERIVADAS que se
    calculan y se devuelven; no se persiste ninguna de las dos.
    """

    reversion_id: uuid.UUID
    movimiento_original_id: uuid.UUID
    row_version: int
    importe: decimal.Decimal
    revertido_acumulado: decimal.Decimal
    pendiente: decimal.Decimal | None
    idempotente: bool = False
