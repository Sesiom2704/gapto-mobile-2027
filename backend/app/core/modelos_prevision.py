# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_prevision.py
# Ruta: backend/app/core/modelos_prevision.py
# Descripcion: DTO y vocabulario de F04-05: reglas financieras, versiones,
#   excepciones, previsiones y vinculos previsión ↔ realidad.
#
#   INV-16 · PREVISION != REALIDAD. Una previsión es una expectativa. No es un
#   hecho, ni un gasto, ni una deuda, ni un movimiento, ni liquidez. Este
#   módulo no comparte ningún tipo con los DTO de hechos, efectos, tesorería o
#   posiciones a propósito: mientras los vocabularios estén separados, un
#   descuido no puede convertir una cosa en la otra.
#
#   IDENTIDAD CANONICA DE OCURRENCIA. Es `regla_id + fecha_objetivo_regla`.
#   `fecha_objetivo_regla` es INMUTABLE: no la mueve la fecha real, ni un
#   override, ni un recálculo, ni una corrección del hecho ancla, ni una nueva
#   versión de regla. Es lo que permite reconocer la misma ocurrencia a lo
#   largo del tiempo, y por eso ningún DTO de este módulo la expone como campo
#   editable.
#
#   AVISO SOBRE EL CONTRATO FISICO. No existe UNIQUE sobre
#   (regla_id, fecha_objetivo_regla) en `previsiones`. La unicidad de la
#   identidad lógica es responsabilidad ENTERA del servicio, bajo lock de
#   `reglas_financieras`. Si alguien calcula el candidato antes del lock,
#   nacen dos ocurrencias y nada en la base lo impide.
#
#   ESTADO_INDETERMINADO. `importe_esperado = None` significa DESCONOCIDO,
#   nunca cero. El CHECK físico ya exige `> 0` cuando no es NULL, de modo que
#   un cero jamás llega a la base; lo que este módulo protege es que nadie
#   convierta el NULL en 0 antes de llegar.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass, field
from typing import Final

CERO: Final = decimal.Decimal("0")

# --- Cadencia ---------------------------------------------------------
DIARIA: Final = "DIARIA"
SEMANAL: Final = "SEMANAL"
MENSUAL: Final = "MENSUAL"
ANUAL: Final = "ANUAL"
PERIODICIDADES: Final = frozenset({DIARIA, SEMANAL, MENSUAL, ANUAL})

CALENDARIO: Final = "CALENDARIO"
RODANTE: Final = "RODANTE"
ANCLAJES: Final = frozenset({CALENDARIO, RODANTE})

# --- Modo de fecha ----------------------------------------------------
FECHA_ANCLA: Final = "ANCLA"
FECHA_VENTANA: Final = "VENTANA"
FECHA_CALENDARIO_ENTIDAD: Final = "CALENDARIO_ENTIDAD"
FECHA_MODOS: Final = frozenset(
    {FECHA_ANCLA, FECHA_VENTANA, FECHA_CALENDARIO_ENTIDAD}
)

# --- Modo de importe --------------------------------------------------
IMPORTE_FIJO: Final = "FIJO"
IMPORTE_MEDIA: Final = "MEDIA_HISTORICA"
IMPORTE_MEDIANA: Final = "MEDIANA_HISTORICA"
IMPORTE_ULTIMO: Final = "ULTIMO_REAL"
IMPORTE_MANUAL: Final = "MANUAL"
IMPORTE_SALDO_OBJETIVO: Final = "SALDO_OBJETIVO"
IMPORTE_CALENDARIO_ENTIDAD: Final = "CALENDARIO_ENTIDAD"
IMPORTE_MODOS: Final = frozenset(
    {
        IMPORTE_FIJO,
        IMPORTE_MEDIA,
        IMPORTE_MEDIANA,
        IMPORTE_ULTIMO,
        IMPORTE_MANUAL,
        IMPORTE_SALDO_OBJETIVO,
        IMPORTE_CALENDARIO_ENTIDAD,
    }
)

# Modos que se estiman a partir de ocurrencias anteriores de la MISMA regla.
IMPORTE_MODOS_HISTORICOS: Final = frozenset(
    {IMPORTE_MEDIA, IMPORTE_MEDIANA, IMPORTE_ULTIMO}
)

# --- Flujo ------------------------------------------------------------
FLUJO_SALIDA: Final = "SALIDA"
FLUJO_ENTRADA: Final = "ENTRADA"
FLUJO_TRANSFERENCIA: Final = "TRANSFERENCIA"
FLUJO_SIN_MOVIMIENTO: Final = "SIN_MOVIMIENTO"
FLUJOS: Final = frozenset(
    {FLUJO_SALIDA, FLUJO_ENTRADA, FLUJO_TRANSFERENCIA, FLUJO_SIN_MOVIMIENTO}
)

# --- Estados de previsión --------------------------------------------
# Los cuatro del contrato físico y NINGUNO más. PARCIAL y VENCIDA son
# conclusiones de lectura, no estados persistidos: una previsión de 1.000 con
# 400 realizados sigue siendo ABIERTA.
ABIERTA: Final = "ABIERTA"
REALIZADA: Final = "REALIZADA"
OMITIDA: Final = "OMITIDA"
CANCELADA: Final = "CANCELADA"
ESTADOS_PREVISION: Final = frozenset({ABIERTA, REALIZADA, OMITIDA, CANCELADA})
ESTADOS_TERMINALES: Final = frozenset({REALIZADA, OMITIDA, CANCELADA})

# Etiqueta DERIVADA de AMB-009 (F04-D018). No se persiste: el estado sigue
# siendo REALIZADA y la cadena RODANTE queda bloqueada para revisión.
REALIZADA_SIN_REALIDAD_ACTIVA: Final = "REALIZADA_SIN_REALIDAD_ACTIVA"

# Etiqueta DERIVADA de F04-D022. Tampoco se persiste: una previsión requiere
# revision cuando su estado actual y su realidad vinculada ya no son
# coherentes, y eso se CALCULA. `motivo_ajuste` es texto descriptivo y ningun
# read-model lo parsea como fuente de dominio.
REQUIERE_REVISION: Final = "REQUIERE_REVISION"

# Motivo estable de la omisión determinista cuando SALDO_OBJETIVO ya se cumple.
MOTIVO_SALDO_OBJETIVO_CUMPLIDO: Final = "SALDO_OBJETIVO_CUMPLIDO"


@dataclass(frozen=True, slots=True)
class Cadencia:
    """Periodicidad + intervalo + anclaje.

    El contrato físico ata los tres: `periodicidad IS NULL` equivale a
    `anclaje_recurrencia IS NULL`, e `intervalo >= 1` es obligatorio en cuanto
    hay periodicidad. Una versión sin cadencia es una regla no recurrente.
    """

    periodicidad: str | None
    intervalo: int | None
    anclaje: str | None

    @property
    def recurrente(self) -> bool:
        return self.periodicidad is not None

    def misma_cadencia(self, otra: "Cadencia") -> bool:
        """True si comparten periodicidad, intervalo y anclaje.

        Es lo que decide si dos versiones contiguas siguen en el MISMO
        segmento: cambiar importe, categoría o tercero no rompe el calendario;
        cambiar la cadencia sí.
        """
        return (
            self.periodicidad == otra.periodicidad
            and self.intervalo == otra.intervalo
            and self.anclaje == otra.anclaje
        )


@dataclass(frozen=True, slots=True)
class DatosRegla:
    """Alta de `reglas_financieras`. Identidad durable, sin lifecycle propio.

    Una regla está operativa cuando existe una versión vigente; no hay campo
    `enabled`. Y no se crea una regla solo para una previsión puntual: eso es
    una previsión manual.
    """

    regla_id: uuid.UUID
    nombre: str | None
    entidad_origen_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DatosVersionRegla:
    """Una versión de regla: toda la condición funcional vive aquí.

    La vigencia es INCLUSIVA en los dos extremos y el EXCLUDE físico impide el
    solapamiento. Continuidad significa que A termina el 30/06 y B empieza el
    01/07: sin solape y sin hueco.
    """

    version_id: uuid.UUID
    vigente_desde: dt.date | None
    vigente_hasta: dt.date | None
    tipo_hecho_codigo: str | None
    flujo_tesoreria_esperado: str | None
    moneda: str | None
    fecha_modo: str | None
    importe_modo: str | None
    presupuestable: bool | None
    cadencia: Cadencia = Cadencia(None, None, None)
    categoria_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    entidad_id: uuid.UUID | None = None
    cuenta_salida_esperada_id: uuid.UUID | None = None
    cuenta_entrada_esperada_id: uuid.UUID | None = None
    importe_referencia_lado: str | None = None
    dia_desde: int | None = None
    dia_hasta: int | None = None
    importe_fijo: decimal.Decimal | None = None
    cuenta_calculo_id: uuid.UUID | None = None
    saldo_objetivo: decimal.Decimal | None = None
    meses_historico: int | None = None


@dataclass(frozen=True, slots=True)
class DatosExcepcion:
    """Excepción por ocurrencia, identificada por regla + fecha_objetivo.

    `omitida=True` hace irrelevantes los overrides: si la ocurrencia no existe,
    no hay importe ni fecha que ajustar.
    """

    excepcion_id: uuid.UUID
    fecha_objetivo: dt.date | None
    omitida: bool = False
    importe_override: decimal.Decimal | None = None
    fecha_override: dt.date | None = None
    motivo: str | None = None

    @property
    def tiene_overrides(self) -> bool:
        return self.importe_override is not None or self.fecha_override is not None


@dataclass(frozen=True, slots=True)
class DatosPrevisionManual:
    """Previsión manual: sin regla y fuera de toda cadena.

    `regla_version_id` y `fecha_objetivo_regla` son NULL,
    `recalculo_automatico` es False y nunca entra en CALENDARIO ni en RODANTE.
    """

    prevision_id: uuid.UUID
    concepto: str | None
    tipo_hecho_codigo: str | None
    fecha_esperada_desde: dt.date | None
    fecha_esperada_hasta: dt.date | None
    flujo_tesoreria_esperado: str | None
    moneda: str | None
    presupuestable: bool | None
    categoria_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    entidad_id: uuid.UUID | None = None
    cuenta_salida_esperada_id: uuid.UUID | None = None
    cuenta_entrada_esperada_id: uuid.UUID | None = None
    importe_esperado: decimal.Decimal | None = None
    importe_referencia_lado: str | None = None


@dataclass(frozen=True, slots=True)
class Ventana:
    """Ventana esperada de una ocurrencia. En modo ANCLA desde == hasta."""

    desde: dt.date
    hasta: dt.date


@dataclass(frozen=True, slots=True)
class Ocurrencia:
    """Una ocurrencia calculada, antes de persistirse.

    `fecha_objetivo` es la identidad canónica y NO se ve afectada por
    `ventana`: un override desplaza la ventana y deja el objetivo intacto.
    """

    fecha_objetivo: dt.date
    ventana: Ventana
    indice: int = 0


@dataclass(frozen=True, slots=True)
class DatosVinculo:
    """Entrada de OP-17.

    `importe_asignado` es la porción de la realidad que satisface esta
    previsión, siempre positiva y siempre en moneda de la PREVISION. No tiene
    que igualar el importe del hecho, ni los efectos, ni la tesorería, ni el
    importe esperado: la diferencia es desviación, no error.

    `marcar_realizada` es una declaración explícita. El primer vínculo NO
    cambia el estado por sí solo.
    """

    vinculo_id: uuid.UUID
    hecho_id: uuid.UUID
    importe_asignado: decimal.Decimal | None
    marcar_realizada: bool = False
    # Solo cuando la moneda del hecho difiere de la de la previsión: el
    # llamante declara que conoce la equivalencia. Sin esto, se rechaza; no se
    # consulta FX, no se inventa tipo y no se copia el nominal.
    equivalencia_declarada: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoRegla:
    regla_id: uuid.UUID
    regla_row_version: int
    version_id: uuid.UUID | None = None
    idempotente: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoPrevision:
    prevision_id: uuid.UUID
    row_version: int
    estado: str
    estado_derivado: str | None = None
    fecha_objetivo_regla: dt.date | None = None
    importe_esperado: decimal.Decimal | None = None
    recalculo_automatico: bool = False
    idempotente: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoGeneracion:
    """Salida de una generación. `creadas` y `existentes` se distinguen para
    que una repetición del mismo horizonte se vea como cero filas nuevas."""

    regla_id: uuid.UUID
    creadas: tuple[uuid.UUID, ...] = ()
    existentes: tuple[uuid.UUID, ...] = ()
    omitidas_por_excepcion: tuple[dt.date, ...] = ()
    canceladas_encontradas: tuple[dt.date, ...] = ()

    @property
    def total_creadas(self) -> int:
        return len(self.creadas)


@dataclass(frozen=True, slots=True)
class ResultadoRecalculo:
    """Salida del recalculo tras una nueva version de regla.

    Las cuatro listas son deliberadamente separadas: regobernar, respetar una
    expectativa congelada, cancelar una identidad que ya no pertenece al
    calendario y senalar una que exige revision son cuatro desenlaces
    distintos, y agruparlos haria invisible el mas delicado.
    """

    regla_id: uuid.UUID
    regobernadas: tuple[uuid.UUID, ...] = ()
    congeladas_respetadas: tuple[uuid.UUID, ...] = ()
    canceladas_fuera_de_segmento: tuple[uuid.UUID, ...] = ()
    requieren_revision: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class OcurrenciaHistorica:
    """Ocurrencia anterior elegible para estimar importe.

    Elegible significa: REALIZADA, con al menos un hecho ACTIVO, con
    `fecha_objetivo_regla` anterior a la candidata, en moneda compatible y
    fuera de AMB-009. El importe real es la suma de `importe_asignado` de sus
    vínculos sobre hechos ACTIVOS; nunca `hechos_financieros.importe_total`,
    ni movimientos, ni efectos, ni el importe esperado.
    """

    fecha_objetivo: dt.date
    importe_real: decimal.Decimal
    moneda: str


@dataclass(frozen=True, slots=True)
class EstadoCabezaRodante:
    """Cabeza operativa de una cadena RODANTE.

    Solo puede haber UNA ABIERTA. Lo garantiza el lock de regla, no el
    contrato físico.
    """

    prevision_id: uuid.UUID
    fecha_objetivo: dt.date
    estado: str
    hechos_activos: int
    fecha_real_maxima: dt.date | None
    recalculo_automatico: bool
    row_version: int
    bloqueada: bool = False
    motivo_bloqueo: str | None = None
