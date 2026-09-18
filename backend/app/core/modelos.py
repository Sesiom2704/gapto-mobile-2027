# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos.py
# Ruta: backend/app/core/modelos.py
# Descripcion: DTO internos de las operaciones OP-01, OP-02 y OP-03.
#
#   Pieza clave: el centinela SIN_CAMBIO. En una correccion, `concepto=None`
#   significa "pon el concepto a NULL" y la AUSENCIA del campo significa "no lo
#   toques". Sin un centinela ambas cosas colapsan en `None` y el motor acaba
#   borrando datos que nadie pidio borrar, o dejando de aplicar un borrado
#   solicitado. Es el principio "dato desconocido = NULL, nunca cero ni valor
#   inventado" llevado al contrato de entrada.
#
#   Estos DTO son internos de F04-01. No constituyen contrato HTTP: F04-01 no
#   crea transporte (el mandato lo excluye expresamente).
# Version: 0.2.0
#   0.2.0 (F04-05): ResultadoHecho expone el impacto DERIVADO de F04-D022
#   —requiere_revision, motivo_revision, previsiones_afectadas y
#   previsiones_propagadas— para que OP-02 y OP-03 puedan confirmar la realidad
#   sin rollback y sin persistir ninguna marca. Los DTO de entrada no cambian.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

from app.core.errores import CodigoError, ErrorMotor

ESTADO_ACTIVO: Final = "ACTIVO"
ESTADO_ANULADO: Final = "ANULADO"

LOCALIZACION_CONOCIDA: Final = "CONOCIDA"
LOCALIZACION_DESCONOCIDA: Final = "DESCONOCIDA"
LOCALIZACION_NO_APLICA: Final = "NO_APLICA"

ESTADOS_LOCALIZACION: Final = frozenset(
    {LOCALIZACION_CONOCIDA, LOCALIZACION_DESCONOCIDA, LOCALIZACION_NO_APLICA}
)


class _SinCambio:
    """Centinela: el campo no se ha solicitado modificar."""

    _instancia: "_SinCambio | None" = None

    def __new__(cls) -> "_SinCambio":
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
        return cls._instancia

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuracion
        return "SIN_CAMBIO"

    def __bool__(self) -> bool:
        return False


SIN_CAMBIO: Final = _SinCambio()


@dataclass(frozen=True, slots=True)
class DatosCreacionHecho:
    """Entrada de OP-01.

    `hecho_id` se reserva ANTES del primer intento transaccional y se reutiliza
    en cualquier retry: es la identidad estable que hace segura la repeticion.

    No existe `owner_user_id`: el tenant llega por ContextoOperacion y lo impone
    RLS. Aceptarlo aqui seria un parametro falsificable.
    """

    hecho_id: uuid.UUID
    fecha_hecho: dt.date | None
    moneda: str | None
    presupuestable: bool | None
    estado_localizacion: str | None
    tipo_hecho_codigo: str | None = None
    tipo_hecho_id: uuid.UUID | None = None
    localidad_id: uuid.UUID | None = None
    concepto: str | None = None
    importe_total: decimal.Decimal | None = None
    numero_participantes_total: int | None = None
    notas: str | None = None


# Campos que OP-02 puede corregir.
CAMPOS_CORREGIBLES: Final = (
    "tipo_hecho_id",
    "fecha_hecho",
    "concepto",
    "importe_total",
    "numero_participantes_total",
    "moneda",
    "localidad_id",
    "estado_localizacion",
    "presupuestable",
    "notas",
)

# Cambiar cualquiera de estos NO es corregir un dato que nunca fue cierto: es
# afirmar una realidad distinta. Pertenece a OP-03 o a operaciones de F04-06.
CAMPOS_DE_REALIDAD_POSTERIOR: Final = frozenset(
    {"estado", "anulado_at", "motivo_anulacion"}
)

# Identidad y metadatos que el write-path gestiona, nunca el llamante.
CAMPOS_INMUTABLES: Final = frozenset(
    {"id", "hecho_id", "owner_user_id", "row_version", "created_at", "updated_at"}
)


@dataclass(slots=True)
class CamposCorreccion:
    """Campos solicitados en OP-02. Ausencia = SIN_CAMBIO."""

    tipo_hecho_id: Any = SIN_CAMBIO
    fecha_hecho: Any = SIN_CAMBIO
    concepto: Any = SIN_CAMBIO
    importe_total: Any = SIN_CAMBIO
    numero_participantes_total: Any = SIN_CAMBIO
    moneda: Any = SIN_CAMBIO
    localidad_id: Any = SIN_CAMBIO
    estado_localizacion: Any = SIN_CAMBIO
    presupuestable: Any = SIN_CAMBIO
    notas: Any = SIN_CAMBIO

    def solicitados(self) -> dict[str, Any]:
        """Campos realmente solicitados, conservando los puestos a NULL."""
        return {
            nombre: getattr(self, nombre)
            for nombre in CAMPOS_CORREGIBLES
            if getattr(self, nombre) is not SIN_CAMBIO
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "CamposCorreccion":
        """Construye la correccion desde un diccionario de entrada.

        Es aqui donde se rechaza lo que OP-02 no puede hacer, con errores
        distintos segun el motivo, porque el motivo importa: intentar mover
        `estado` no es un error de tipado, es usar la correccion de captura
        para representar un acontecimiento posterior.
        """
        for clave in datos:
            if clave in CAMPOS_DE_REALIDAD_POSTERIOR:
                raise ErrorMotor(
                    CodigoError.CORRECCION_IMPROCEDENTE_ES_REALIDAD_NUEVA,
                    f"'{clave}' no se corrige: representa una realidad "
                    "posterior, no un error de captura.",
                )
            if clave in CAMPOS_INMUTABLES:
                raise ErrorMotor(
                    CodigoError.CAMPO_INMUTABLE,
                    f"'{clave}' no es modificable por el llamante.",
                )
            if clave not in CAMPOS_CORREGIBLES:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    f"'{clave}' no es un campo corregible de hechos_financieros.",
                )
        return cls(**datos)


@dataclass(frozen=True, slots=True)
class ResultadoHecho:
    """Salida comun de OP-01, OP-02 y OP-03."""

    hecho_id: uuid.UUID
    row_version: int
    estado: str
    idempotente: bool = False
    snapshot: dict[str, Any] = field(default_factory=dict)
    # F04-D022. La realidad manda: OP-02 y OP-03 confirman aunque la cadena
    # RODANTE no pueda propagarse. Cuando no puede, el resultado es EXITOSO y
    # expone el impacto DERIVADO. Nada de esto se persiste: es conclusion de
    # aplicacion, calculada desde hechos ACTIVOS, estado de previsiones y
    # estructura del tramo.
    requiere_revision: bool = False
    motivo_revision: str | None = None
    previsiones_afectadas: tuple[uuid.UUID, ...] = ()
    previsiones_propagadas: tuple[uuid.UUID, ...] = ()
