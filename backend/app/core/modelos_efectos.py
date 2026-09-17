# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_efectos.py
# Ruta: backend/app/core/modelos_efectos.py
# Descripcion: DTO internos de OP-04 (registrar efectos) y OP-05 (atribuir).
#
#   Dos piezas merecen explicacion:
#
#   1) `acontecimiento` en DatosEfecto. INV-09 exige que `VALOR_ACTIVO`
#      represente un acontecimiento real sobre un activo y nunca una
#      valoracion. 0310 no tiene columna donde persistir esa distincion y el
#      mandato prohibe inventarla, asi que la evidencia de intencion vive en el
#      DTO: sin acontecimiento declarado, la operacion falla cerrada. Es una
#      guarda de frontera de API, no una garantia historica: un llamante que
#      declare un acontecimiento falso no queda desmentido por nada persistido.
#      La limitacion se documenta en el handoff como riesgo residual.
#
#   2) Identidades reservadas. Tanto los efectos como las atribuciones traen su
#      UUID desde el llamante, antes del primer intento. Es lo que permite que
#      un retry tras un COMMIT de resultado desconocido no duplique realidad
#      (INV-20), y por eso no hay `default_factory=uuid4` en ningun sitio: un
#      UUID generado dentro de la operacion se regeneraria en cada intento.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

TIPO_GASTO: Final = "GASTO"
TIPO_INGRESO: Final = "INGRESO"
TIPO_DEUDA: Final = "DEUDA"
TIPO_DERECHO_COBRO: Final = "DERECHO_COBRO"
TIPO_INVERSION: Final = "INVERSION"
TIPO_VALOR_ACTIVO: Final = "VALOR_ACTIVO"

TIPOS_EFECTO: Final = frozenset(
    {
        TIPO_GASTO,
        TIPO_INGRESO,
        TIPO_DEUDA,
        TIPO_DERECHO_COBRO,
        TIPO_INVERSION,
        TIPO_VALOR_ACTIVO,
    }
)

ATRIBUCION_COMPLETA: Final = "COMPLETA"
ATRIBUCION_PARCIAL: Final = "PARCIAL"
ATRIBUCION_NO_DISPONIBLE: Final = "NO_DISPONIBLE"

ESTADOS_ATRIBUCION: Final = frozenset(
    {ATRIBUCION_COMPLETA, ATRIBUCION_PARCIAL, ATRIBUCION_NO_DISPONIBLE}
)

# Orden de enriquecimiento permitido. Solo se avanza.
RANGO_ESTADO: Final = {
    ATRIBUCION_NO_DISPONIBLE: 0,
    ATRIBUCION_PARCIAL: 1,
    ATRIBUCION_COMPLETA: 2,
}

CRITERIOS_ATRIBUCION: Final = frozenset(
    {"MANUAL", "PARTES_IGUALES", "PARTICIPACION_ENTIDAD", "REGLA", "SEGUN_PAGO"}
)

# Acontecimientos reales admitidos para VALOR_ACTIVO (INV-09). La lista NO
# incluye tasacion, valor de mercado, apreciacion, inflacion ni valoracion
# periodica: esos no son acontecimientos, son observaciones de precio.
ACONTECIMIENTOS_VALOR_ACTIVO: Final = frozenset(
    {
        "ADQUISICION",
        "BAJA_TOTAL",
        "BAJA_PARCIAL",
        "TRANSFORMACION_CAPITALIZABLE",
        "REDUCCION_ESTRUCTURAL",
    }
)


@dataclass(frozen=True, slots=True)
class DatosAtribucion:
    """Una fila de `efecto_atribuciones`.

    `importe_atribuido` de 0,00 es dato CONOCIDO y no equivale a ausencia de
    fila: significa que ese actor soporta cero, no que se ignore su parte.
    """

    atribucion_id: uuid.UUID
    actor_id: uuid.UUID
    importe_atribuido: decimal.Decimal
    criterio_atribucion: str
    porcentaje_aplicado: decimal.Decimal | None = None


@dataclass(frozen=True, slots=True)
class DatosEfecto:
    """Un efecto economico y, opcionalmente, su reparto inicial.

    El reparto inicial viaja aqui a proposito: crear el efecto y sus
    atribuciones en transacciones distintas obligaria a confirmar un estado
    intermedio que no es cierto (por ejemplo un COMPLETA sin filas), y los
    constraint triggers diferidos de 0310 existen precisamente para permitir
    construir el estado final dentro de una sola transaccion.
    """

    efecto_id: uuid.UUID
    tipo_efecto: str
    importe_delta: decimal.Decimal
    estado_atribucion: str
    categoria_id: uuid.UUID | None = None
    descripcion: str | None = None
    acontecimiento: str | None = None
    atribuciones: tuple[DatosAtribucion, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoEfecto:
    efecto_id: uuid.UUID
    tipo_efecto: str
    estado_atribucion: str
    idempotente: bool
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoOperacionEfectos:
    """Salida de OP-04 y OP-05.

    `row_version` es la del hecho raiz, que es el token de concurrencia del
    agregado: `hecho_efectos` y `efecto_atribuciones` no tienen el suyo propio
    (INV-20).
    """

    hecho_id: uuid.UUID
    row_version: int
    efectos: tuple[ResultadoEfecto, ...] = ()
    atribuciones_creadas: int = 0
    idempotente: bool = False
