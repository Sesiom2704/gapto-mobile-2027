# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_suplemento.py
# Ruta: backend/app/core/modelos_suplemento.py
# Descripcion: F04-06 / B4. DTO de entrada y salida de OP-18.
#
#   REALIDAD SUPLEMENTARIA NO ES CORRECCION. Un hecho que se descubre mas
#   tarde no corrige el anterior si el anterior era verdadero: crea su propia
#   realidad, con su propia fecha economica. Lo que NUNCA fue cierto se edita
#   con OP-02 y no produce hecho nuevo.
#
#   LA FRONTERA NO TIENE RED FISICA. PostgreSQL no puede distinguir una
#   revision de alquiler descubierta en junio de un importe mal tecleado en
#   enero: ambas producen filas perfectamente validas. La distincion la
#   sostiene el servicio, y por eso la entrada obliga a DECLARAR lo que el
#   motor no puede deducir.
#
#   `fecha_demostrada` es esa declaracion. No es burocracia: sin ella, OP-18 se
#   convierte en una puerta para retrodatar cualquier cosa, y el mandato
#   prohibe expresamente inventar retroactividad.
# Version: 0.2.0
#   0.2.0 (F04-D046 R2 · A20/A08-bis): el suplemento recibe su propia decision
#   historica `presupuestable` y su localizacion. OP-18 ya no fija `false` ni
#   `NO_APLICA` ni hereda del hecho ajustado. Con GASTO o INGRESO
#   `presupuestable` es obligatorio y sin default; con DEUDA o DERECHO_COBRO se
#   deriva `false` (declarar `true` se rechaza). Localizacion aplicable sin
#   dato -> DESCONOCIDA; NO_APLICA solo si el llamante lo declara.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Final

CERO: Final = decimal.Decimal("0")

TIPO_RELACION_CORRIGE: Final = "CORRIGE_A"

NATURALEZAS_SUPLEMENTABLES: Final = frozenset(
    {"GASTO", "INGRESO", "DEUDA", "DERECHO_COBRO"}
)


@dataclass(frozen=True, slots=True)
class DatosSuplemento:
    """Entrada de OP-18.

    `hecho_ajustado_id` es OPCIONAL. Una realidad suplementaria autonoma —un
    recargo que aparece solo— no necesita relacionarse con nada. CORRIGE_A se
    emite unicamente cuando existe un hecho anterior identificable al que este
    ajusta de verdad.

    `editar_original` existe SOLO para rechazarlo. Quien intente usar OP-18
    para modificar una realidad anterior recibe un error de dominio legible en
    vez de un hecho nuevo que enmascara un error de captura.
    """

    hecho_id: uuid.UUID
    efecto_id: uuid.UUID
    tipo_efecto: str | None
    importe_delta: decimal.Decimal | None
    fecha_hecho: dt.date | None
    moneda: str | None

    # Declaracion explicita: el motor no puede deducirla.
    fecha_demostrada: bool = False

    concepto: str | None = None
    categoria_id: uuid.UUID | None = None
    estado_atribucion: str = "NO_DISPONIBLE"
    tipo_hecho_codigo: str = "GASTO"

    # Relacion opcional con el hecho que ajusta.
    relacion_id: uuid.UUID | None = None
    hecho_ajustado_id: uuid.UUID | None = None
    notas: str | None = None

    # Periodo cerrado: la politica no se inventa dentro de F04-06.
    periodo_cerrado: bool = False
    politica_periodo_cerrado: str | None = None

    # Solo para rechazar.
    editar_original: bool = False
    # F04-D046 R2. Decision historica propia del suplemento. Sin default.
    presupuestable: bool | None = None
    # F04-D046 R2. Localizacion analitica. Sin dato -> DESCONOCIDA.
    estado_localizacion: str | None = None
    localidad_id: uuid.UUID | None = None

    @property
    def con_relacion(self) -> bool:
        return self.hecho_ajustado_id is not None


@dataclass(frozen=True, slots=True)
class ResultadoSuplemento:
    """Salida de OP-18."""

    hecho_id: uuid.UUID
    hecho_row_version: int
    efecto_id: uuid.UUID
    tipo_efecto: str
    importe_delta: decimal.Decimal
    fecha_hecho: dt.date
    relacion_id: uuid.UUID | None = None
    idempotente: bool = False
