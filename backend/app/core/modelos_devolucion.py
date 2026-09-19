# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_devolucion.py
# Ruta: backend/app/core/modelos_devolucion.py
# Descripcion: F04-06 / B3. DTO de entrada y salida de OP-13.
#
#   UNA DEVOLUCION ES UN HECHO NUEVO. No es una correccion del original ni una
#   reversion de tesoreria: es una realidad economica posterior que reduce un
#   efecto del hecho original. Por eso la entrada reserva identidad para el
#   hecho, su efecto y la relacion, y opcionalmente para el movimiento y su
#   conciliacion cuando ademas hay caja.
#
#   LA CAJA ES OPCIONAL. El efecto economico puede ocurrir antes que el dinero,
#   igual que un gasto no exige conciliacion inmediata. Si no se declara
#   movimiento, no se fabrica ninguno.
#
#   EL IMPORTE ES UNA MAGNITUD POSITIVA. El signo contrario lo deriva el motor
#   de la naturaleza que se devuelve. Pedirselo al llamante permitiria declarar
#   una devolucion con el mismo signo que el original, que no reduce nada.
#
#   `tipo_efecto_devolucion` existe SOLO para poder rechazarlo. Una devolucion
#   conserva la naturaleza del original (INV-05): devolver un GASTO produce un
#   GASTO negativo, jamas un INGRESO. El campo permite devolver un error de
#   dominio legible a quien lo intente, en vez de ignorarlo en silencio.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Final

CERO: Final = decimal.Decimal("0")

TIPO_RELACION_DEVOLUCION: Final = "DEVOLUCION_DE"

# Naturalezas sobre las que F04-06 admite devolucion. INVERSION y VALOR_ACTIVO
# quedan fuera: su reduccion pertenece al dominio patrimonial y tiene sus
# propias operaciones, no se resuelve creando un efecto de signo contrario.
NATURALEZAS_DEVOLUBLES: Final = frozenset(
    {"GASTO", "INGRESO", "DEUDA", "DERECHO_COBRO"}
)


@dataclass(frozen=True, slots=True)
class DatosDevolucion:
    """Entrada de OP-13.

    `tipo_efecto` es la NATURALEZA que se devuelve, no un efecto concreto. La
    relacion es fact-level y el modelo no conserva trazabilidad efecto a
    efecto, de modo que la capacidad se agrega por naturaleza (F04-D030).
    """

    hecho_id: uuid.UUID
    efecto_id: uuid.UUID
    relacion_id: uuid.UUID
    hecho_original_id: uuid.UUID

    tipo_efecto: str | None
    importe: decimal.Decimal | None
    fecha_hecho: dt.date | None
    moneda: str | None

    concepto: str | None = None
    categoria_id: uuid.UUID | None = None
    estado_atribucion: str = "NO_DISPONIBLE"
    notas: str | None = None

    # Caja opcional. Las tres viajan juntas o no viaja ninguna.
    movimiento_id: uuid.UUID | None = None
    conciliacion_id: uuid.UUID | None = None
    cuenta_id: uuid.UUID | None = None
    fecha_movimiento: dt.date | None = None

    # Multidivisa: sin declaracion explicita no se compara nominalmente.
    equivalencia_declarada: bool = False

    # Solo para rechazar: una devolucion conserva la naturaleza del original.
    tipo_efecto_devolucion: str | None = None

    @property
    def con_caja(self) -> bool:
        return self.movimiento_id is not None


@dataclass(frozen=True, slots=True)
class ResultadoDevolucion:
    """Salida de OP-13.

    `capacidad`, `devuelto_acumulado` y `pendiente` son conclusiones DERIVADAS:
    se calculan dentro del lock y se devuelven, pero no se persiste ninguna.

    `previsiones_del_original` informa de cuantas previsiones materializa el
    hecho original. OP-13 NO las toca (F04-D033): que el original satisficiera
    una expectativa sigue siendo cierto despues de la devolucion.
    """

    hecho_id: uuid.UUID
    hecho_row_version: int
    efecto_id: uuid.UUID
    relacion_id: uuid.UUID
    tipo_efecto: str
    importe_delta: decimal.Decimal
    capacidad: decimal.Decimal
    devuelto_acumulado: decimal.Decimal
    pendiente: decimal.Decimal
    previsiones_del_original: int = 0
    movimiento_id: uuid.UUID | None = None
    idempotente: bool = False
