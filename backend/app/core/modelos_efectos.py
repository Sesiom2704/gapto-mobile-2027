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
#      F06-D002 (B0): desde 0351 el acontecimiento declarado SI se persiste,
#      en `hecho_efectos.causa_valor_activo` (`DatosEfecto.causa_valor_activo`
#      lo deriva; no hay segundo campo que pueda discrepar). La guarda
#      `exigir_causa_valor_activo` la aplica el unico INSERT de efectos.
#
#   2) Identidades reservadas. Tanto los efectos como las atribuciones traen su
#      UUID desde el llamante, antes del primer intento. Es lo que permite que
#      un retry tras un COMMIT de resultado desconocido no duplique realidad
#      (INV-20), y por eso no hay `default_factory=uuid4` en ningun sitio: un
#      UUID generado dentro de la operacion se regeneraria en cada intento.
# Version: 0.2.0
#   0.2.0 (F06-01 B0, F06-D002; AJ-B0-03): `DatosEfecto.causa_valor_activo`
#   y `exigir_causa_valor_activo`, guarda de escritura compartida por todos
#   los caminos que insertan efectos. Ningun campo existente cambia.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

from app.core.errores import CodigoError, ErrorMotor

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

    @property
    def causa_valor_activo(self) -> str | None:
        """F06-D002: la causa persistida ES el acontecimiento declarado.

        Se deriva en lugar de duplicarse para que causa y acontecimiento no
        puedan discrepar. Admisibilidad: `exigir_causa_valor_activo`.
        """
        return self.acontecimiento


def exigir_causa_valor_activo(tipo_efecto: str, causa: str | None) -> None:
    """F06-D002 (B0) · guarda de escritura de `causa_valor_activo`.

    Obligatoria y del dominio cerrado si el efecto es VALOR_ACTIVO; prohibida
    en cualquier otro tipo. La invoca el INSERT de efectos, de modo que cubre
    OP-04, OP-22 (via OP-04), las altas de OP-21 y las escrituras directas de
    los demas servicios. No sustituye a los CHECK de 0351: son defensas
    independientes (PB0-03).
    """
    if tipo_efecto == TIPO_VALOR_ACTIVO:
        if causa not in ACONTECIMIENTOS_VALOR_ACTIVO:
            raise ErrorMotor(
                CodigoError.CAUSA_VALOR_ACTIVO_REQUERIDA,
                "Un efecto VALOR_ACTIVO exige una causa del conjunto cerrado.",
            )
    elif causa is not None:
        raise ErrorMotor(
            CodigoError.CAUSA_VALOR_ACTIVO_NO_ADMITIDA,
            "Solo un efecto VALOR_ACTIVO admite causa.",
        )


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
