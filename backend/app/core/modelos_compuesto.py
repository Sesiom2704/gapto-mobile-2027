# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_compuesto.py
# Ruta: backend/app/core/modelos_compuesto.py
# Descripcion: F04-D048 R3 (A17 + A18). Entradas y resultados de:
#
#   - las cuatro dimensiones contextuales del hecho (`hecho_terceros`,
#     `hecho_entidades`, `hecho_magnitudes`, `hecho_etiquetas`), usadas por el
#     alta dentro de OP-22, por el enriquecimiento posterior y por OP-21;
#   - OP-22 «Registrar hecho compuesto», orquestador atomico que REUTILIZA las
#     entradas certificadas de OP-01, OP-04, OP-06, OP-08, OP-09, OP-12, OP-17
#     y OP-18 sin redefinirlas.
#
#   REGLAS DE LOS DTO (pronunciamiento R3-01..04):
#   - `principal` es OBLIGATORIO en terceros y entidades: sin valor por
#     defecto. El DEFAULT false fisico de 0330 no es un default de dominio.
#   - Magnitud desconocida = AUSENCIA de fila. `valor` no admite None: quien no
#     conoce el valor no envia la magnitud; nunca se convierte en cero.
#   - `marcar_realizada` de la prevision es OBLIGATORIO: REALIZADA solo nace de
#     una decision explicita (ni True ni False por defecto).
#   - Toda fila nueva lleva UUID reservado por el llamante, que es la identidad
#     estable de la idempotencia y de los reintentos.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Final, Sequence

from app.core.modelos import DatosCreacionHecho
from app.core.modelos_posicion import DatosAltaPosicion
from app.core.modelos_suplemento import DatosSuplemento
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento

# ----------------------------------------------------------------------
# Vocabulario (0330 + pronunciamiento R3-01)
# ----------------------------------------------------------------------
ROLES_TERCERO: Final = frozenset(
    {"VENDEDOR", "EMPLEADOR", "FINANCIADOR", "REEMBOLSADOR", "BENEFICIARIO", "OTRO"}
)
#: Relaciones contextuales R3. GENERADO_POR (posiciones) y REPERCUTIBLE_A
#: quedan reservadas y el writer contextual las rechaza.
RELACIONES_CONTEXTUALES: Final = frozenset({"AFECTA_A", "RELACIONADO_CON"})
RELACIONES_RESERVADAS: Final = frozenset({"GENERADO_POR", "REPERCUTIBLE_A"})

TIPO_ENTIDAD_POSICION: Final = "DERECHO_OBLIGACION"
TIPO_ENTIDAD_INVERSION: Final = "INVERSION"
TIPO_ENTIDAD_FINANCIACION: Final = "FINANCIACION"
#: Tipos que admiten vinculo contextual a nivel de hecho Y de efecto.
TIPOS_ENTIDAD_CONTEXTO_LIBRE: Final = frozenset(
    {"PROPIEDAD", "CONTRATO", "SERVICIO", "CONTEXTO"}
)


# ----------------------------------------------------------------------
# Dimensiones contextuales (A18)
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DatosTerceroHecho:
    """Relacion contextual hecho <-> tercero. NO es pagador, aportacion,
    atribucion ni contraparte de posicion."""

    registro_id: uuid.UUID
    tercero_id: uuid.UUID
    rol_en_hecho: str
    principal: bool  # obligatorio (R3-04): sin default


@dataclass(frozen=True, slots=True)
class DatosEntidadHecho:
    """Relacion contextual hecho/efecto <-> entidad (matriz R3-01)."""

    registro_id: uuid.UUID
    entidad_id: uuid.UUID
    tipo_relacion: str
    principal: bool  # obligatorio (R3-04): sin default
    efecto_id: uuid.UUID | None = None  # None = vinculo a nivel de hecho


@dataclass(frozen=True, slots=True)
class DatosMagnitudHecho:
    """Valor conocido de una magnitud. Desconocido = no enviar la fila.

    `unidad` es el snapshot historico del dato. Si el llamante no la aporta se
    toma `magnitudes.unidad_default`, que DB Schema define como default de
    CAPTURA; una vez escrita, cambiar el default no la reinterpreta.
    """

    registro_id: uuid.UUID
    magnitud_id: uuid.UUID
    valor: decimal.Decimal
    unidad: str | None = None


@dataclass(frozen=True, slots=True)
class DatosEtiquetaHecho:
    registro_id: uuid.UUID
    etiqueta_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class DatosContextoHecho:
    """Conocimiento contextual del hecho. Se usa en el alta dentro de OP-22 y
    en el ENRIQUECIMIENTO posterior (el dato faltaba y ahora se conoce)."""

    terceros: Sequence[DatosTerceroHecho] = ()
    entidades: Sequence[DatosEntidadHecho] = ()
    magnitudes: Sequence[DatosMagnitudHecho] = ()
    etiquetas: Sequence[DatosEtiquetaHecho] = ()

    @property
    def vacio(self) -> bool:
        return not (self.terceros or self.entidades or self.magnitudes or self.etiquetas)

    def identidades(self) -> list[uuid.UUID]:
        return [
            d.registro_id
            for grupo in (self.terceros, self.entidades, self.magnitudes, self.etiquetas)
            for d in grupo
        ]


@dataclass(frozen=True, slots=True)
class ResultadoContexto:
    hecho_id: uuid.UUID
    hecho_row_version: int
    terceros_creados: int = 0
    entidades_creadas: int = 0
    magnitudes_creadas: int = 0
    etiquetas_creadas: int = 0
    idempotente: bool = False


# ----------------------------------------------------------------------
# OP-22 · Registrar hecho compuesto (A17)
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DatosPagoCompuesto:
    """Movimiento real y su conciliacion con el hecho de OP-22 (OP-08 + OP-09).

    Viajan juntos por la misma razon que en OP-19: un movimiento sin conciliar
    no dice nada del hecho, y una conciliacion sin movimiento no existe.
    """

    movimiento: DatosMovimiento
    conciliacion: DatosConciliacion


@dataclass(frozen=True, slots=True)
class DatosPrevisionCompuesta:
    """Vinculo OP-17 entre el hecho de OP-22 y una prevision ABIERTA.

    `marcar_realizada` es OBLIGATORIO: la realizacion es una decision
    explicita del llamante y nunca un efecto por defecto del vinculo. El
    vinculo sigue siendo N:N conforme al contrato de OP-17.
    """

    prevision_id: uuid.UUID
    prevision_row_version_esperada: int
    vinculo_id: uuid.UUID
    importe_asignado: decimal.Decimal
    marcar_realizada: bool
    equivalencia_declarada: bool = False
    uuid_sucesor: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DatosHechoCompuesto:
    """Entrada de OP-22. Todo lo aportado se confirma entero o nada.

    La raiz es EXACTAMENTE una de:
      - `hecho`: hecho nuevo creado por OP-01;
      - `suplemento`: realidad suplementaria creada por OP-18 adscrito
        (F04-D048 Q02: OP-18 no se amplia con tesoreria; el pago se compone
        aqui).

    Los componentes reutilizan las entradas certificadas. Las posiciones son
    altas OP-12 EXPLICITAS enganchadas a la raiz (`hecho_id` = raiz y
    `hecho_row_version_esperada` = None: la version la encadena el
    orquestador). Ninguna posicion nace por diferencia.
    """

    hecho: DatosCreacionHecho | None = None
    suplemento: DatosSuplemento | None = None
    efectos: Sequence[DatosEfecto] = ()
    participantes: Sequence[object] = ()  # DatosParticipante (OP-19/F04-07)
    posiciones: Sequence[DatosAltaPosicion] = ()
    pagos: Sequence[DatosPagoCompuesto] = ()
    aportaciones: Sequence[DatosAportacion] = ()
    contexto: DatosContextoHecho = field(default_factory=DatosContextoHecho)
    prevision: DatosPrevisionCompuesta | None = None

    @property
    def hecho_id(self) -> uuid.UUID | None:
        if self.hecho is not None:
            return self.hecho.hecho_id
        if self.suplemento is not None:
            return self.suplemento.hecho_id
        return None


@dataclass(frozen=True, slots=True)
class ResultadoHechoCompuesto:
    hecho_id: uuid.UUID
    hecho_row_version: int
    idempotente: bool = False
    movimientos: dict[uuid.UUID, int] = field(default_factory=dict)
    posiciones: dict[uuid.UUID, int] = field(default_factory=dict)
    prevision_row_version: int | None = None
    efectos_creados: int = 0
    atribuciones_creadas: int = 0
    participantes_creados: int = 0
    aportaciones_creadas: int = 0
    conciliaciones_creadas: int = 0
    contexto_creado: int = 0
