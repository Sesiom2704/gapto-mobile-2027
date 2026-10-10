# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_vs01.py
# Ruta: backend/app/api/dto_vs01.py
# Descripcion: DTO HTTP del vertical slice VS-01 (gasto cotidiano ya ocurrido
#   y pagado). API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10.
#
#   Lo que el DTO NO admite, deliberadamente:
#     - tenant / owner / actor: salen del contexto del servidor (§15);
#     - defaults ocultos: `presupuestable` y `atribucion` son OBLIGATORIOS y
#       sin valor por defecto. `atribucion=SIN_INDICAR` es la respuesta
#       explicita "no lo indico ahora" (F05-00-A A01 -> NO_DISPONIBLE), no un
#       default del servidor;
#     - campos extra: `extra="forbid"` rechaza, p. ej., un `owner_user_id`
#       colado en el payload en vez de ignorarlo en silencio.
#   El importe es MAGNITUD positiva: el signo (GASTO +X / tesoreria -X) lo
#   pone el traductor, nunca el cliente.
#
#   v0.2.0 (F05-D003): la financiacion es una dimension EXPLICITA de la
#   intencion sellada (PROPUESTA_ACEPTADA self 100 % / NO_DETERMINADA, §16.4);
#   la fecha es la fecha COMUN de gasto y pago y no puede ser futura (§16.3).
#
#   v0.3.0 (F05-01, mandato backend v0.2, F05-D009): dimension CATEGORIAL de la
#   intencion sellada (C01, AJ-01): CATEGORIA(id) pasa por la guarda C-a;
#   SIN_CATEGORIA es decision explicita y persiste NULL; un tercer estado de
#   compatibilidad se derivaba de la AUSENCIA del campo (retirado en v0.5.0).
#
#   v0.4.0 (F05-01, S6-C07; F05-D014 §28.2, AJ-C07-02): solo la variante
#   CATEGORIA admite `magnitudes: [{magnitud_id, valor}]`. Reglas ESTRUCTURALES
#   (422, sin tocar la base):
#     - lista ausente = lista vacia; `magnitudes: null` -> 422;
#     - `magnitud_id` repetida -> 422 (el orden del array no es identidad);
#     - campo `unidad` -> 422 (la unidad nunca viaja en el wire, AJ-C07-05;
#       lo garantiza `extra="forbid"`);
#     - cualquier magnitud dentro de SIN_CATEGORIA -> 422 (idem);
#     - `valor` es TEXTO decimal canonico con punto: sin exponente, coma,
#       signo `+`, NaN, infinitos, ceros a la izquierda ni forma negativa del
#       cero; nunca un numero JSON (StrictStr).
#   La admisibilidad de cada magnitud (asociacion, `enabled`, precision,
#   capacidad numeric(18,6)) la decide el servidor dentro de la transaccion
#   (captura_magnitudes.py), nunca este DTO. Ausencia de una magnitud =
#   desconocido, nunca cero.
#
#   v0.4.1 (auditoria S6-C07, AJ-S6C07-01; D2 RECHAZADA): se retira el
#   limite de 40 caracteres de `valor`. Convertia en 422 valores canonicos
#   fuera de rango, que §28.2 clasifica como 409 MAGNITUD_VALOR_NO_VALIDO, y
#   rechazaba valores numericamente validos con ceros decimales de cola
#   (AJ-C07-06). El DTO solo decide la FORMA; precision y capacidad son de C07.
#
#   v0.5.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03, §28.3): corte
#   atomico del wire categorial. `categoria` es OBLIGATORIA y sin default:
#   ausente -> 422; `null` -> 422 (por tipo: ni CATEGORIA ni SIN_CATEGORIA).
#   Se retira el estado de compatibilidad derivado de la ausencia: el estado
#   categorial es siempre `categoria.estado` (CATEGORIA | SIN_CATEGORIA). La
#   union discriminada y las reglas de magnitudes de §28.2 no cambian. La
#   historia NULL existente no se reinterpreta (sin cambios en lecturas ni OP-22).
#
#   v0.6.0 (F05-03/F05-04 J2 §1.1; F05 §46.4 R1): DTO de lectura
#   ListaCuentasElegibles (GET /v1/cuentas/elegibles). La intencion no cambia.
#
#   v0.7.0 (F05-03/F05-04 J2 §1.2; F05-D032 C6): se RETIRAN hoy_referencia()
#   y la validacion de fecha futura del DTO: el «hoy» es el del OWNER
#   (gapto.usuarios.timezone, fallback Europe/Madrid) y el DTO no conoce al
#   owner. La intencion NUEVA con fecha posterior a hoy_owner la rechaza la
#   ejecucion con FECHA_FUTURA (comun/fecha_funcional.py).
# Version: 0.7.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

AtribucionVs01 = Literal["SOLO_MIO", "SIN_INDICAR"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FinanciacionPropuestaAceptada(_Estricto):
    """Propuesta visible aceptada al confirmar (§16.4). En VS-01 solo existe
    para cuenta con participacion unica del self al 100 %. El actor se expresa
    como el literal SELF: el cliente nunca envia UUID de actor."""

    estado: Literal["PROPUESTA_ACEPTADA"]
    actor: Literal["SELF"]
    criterio: Literal["PARTICIPACION_CUENTA"]
    porcentaje: Literal["100"]
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class FinanciacionNoDeterminada(_Estricto):
    """Decision funcional explicita: la financiacion real no se ha
    determinado. No equivale a cero ni a lista vacia accidental."""

    estado: Literal["NO_DETERMINADA"]


FinanciacionVs01 = Annotated[
    Union[FinanciacionPropuestaAceptada, FinanciacionNoDeterminada],
    Field(discriminator="estado"),
]


#: Sintaxis canonica del valor de una magnitud (AJ-C07-02): entero sin ceros
#: a la izquierda, signo menos opcional y parte decimal opcional con punto.
#: Sin limite de longitud propio: un texto canonico largo es FORMA valida y
#: C07 decide precision y capacidad (409), nunca el DTO.
VALOR_CANONICO = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


class MagnitudCapturada(_Estricto):
    """Valor CONOCIDO de una magnitud de la categoria elegida. Desconocido =
    no enviar la magnitud. Sin `unidad` (la toma el writer F04 como snapshot
    de `magnitudes.unidad_default`) y sin UUID de fila (lo deriva el
    adaptador, AJ-C07-03)."""

    magnitud_id: uuid.UUID
    valor: StrictStr = Field(min_length=1)

    @field_validator("valor")
    @classmethod
    def _valor_canonico(cls, valor: str) -> str:
        if VALOR_CANONICO.fullmatch(valor) is None:
            raise ValueError("valor debe ser texto decimal canonico con punto (p. ej. 12.5)")
        if valor.startswith("-") and decimal.Decimal(valor) == 0:
            raise ValueError("valor: el cero no lleva signo")
        return valor


class CategoriaSeleccionada(_Estricto):
    """Seleccion explicita de una categoria (C01). Su elegibilidad la decide
    la guarda C-a dentro de la transaccion, nunca este DTO. Solo esta variante
    admite magnitudes (C07, AJ-C07-02)."""

    estado: Literal["CATEGORIA"]
    categoria_id: uuid.UUID
    # Lista ausente = lista vacia. `null` no es una tupla: 422 por tipo.
    magnitudes: tuple[MagnitudCapturada, ...] = ()

    @model_validator(mode="after")
    def _sin_magnitud_repetida(self) -> "CategoriaSeleccionada":
        ids = [m.magnitud_id for m in self.magnitudes]
        if len(ids) != len(set(ids)):
            raise ValueError("magnitud_id repetida en la peticion")
        return self


class SinCategoria(_Estricto):
    """Decision explicita del usuario: «Sin categoría». Persiste NULL."""

    estado: Literal["SIN_CATEGORIA"]


CategoriaVs01 = Annotated[
    Union[CategoriaSeleccionada, SinCategoria],
    Field(discriminator="estado"),
]

class IntencionGastoPagado(_Estricto):
    intencion_id: uuid.UUID
    concepto: str = Field(min_length=1, max_length=200)
    importe: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    moneda: Literal["EUR"]
    # Fecha COMUN del gasto y del pago en VS-01 (regla expresa §16.3):
    # fecha_hecho = fecha_movimiento. La vigencia de la participacion se
    # evalua en esta fecha, que es la del pago.
    fecha_hecho: dt.date
    cuenta_id: uuid.UUID
    presupuestable: bool
    atribucion: AtribucionVs01
    financiacion: FinanciacionVs01
    # S6-WIRE (AJ-03): estado categorial resuelto OBLIGATORIO (C01). Ausente
    # -> 422 (campo requerido); `null` -> 422 (no es ninguna variante).
    categoria: CategoriaVs01

    @property
    def estado_categorial(self) -> str:
        return self.categoria.estado

    @property
    def categoria_id(self) -> uuid.UUID | None:
        if isinstance(self.categoria, CategoriaSeleccionada):
            return self.categoria.categoria_id
        return None

    @property
    def magnitudes(self) -> tuple[MagnitudCapturada, ...]:
        """Magnitudes selladas; solo existen con estado CATEGORIA."""
        if isinstance(self.categoria, CategoriaSeleccionada):
            return self.categoria.magnitudes
        return ()

    @model_validator(mode="after")
    def _importe_financiacion(self) -> "IntencionGastoPagado":
        if (
            isinstance(self.financiacion, FinanciacionPropuestaAceptada)
            and self.financiacion.importe != self.importe
        ):
            raise ValueError("financiacion.importe debe igualar el importe del gasto")
        return self

    @field_validator("concepto")
    @classmethod
    def _concepto_no_blanco(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("concepto vacio")
        return limpio


class ResultadoGastoPagado(_Estricto):
    intencion_id: uuid.UUID
    hecho_id: uuid.UUID
    idempotente: bool
    importe: str
    moneda: str
    estado_atribucion: str
    aportacion_criterio: str | None
    financiacion: Literal["PROPUESTA_ACEPTADA", "NO_DETERMINADA"]
    estado_categorial: Literal["CATEGORIA", "SIN_CATEGORIA"]
    aviso: str


class CuentaPago(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str
    moneda: str
    # Propuesta para la fecha consultada (§16.4): SELF_100 permite la
    # aceptacion implicita visible; cualquier otro estado es NO_DETERMINADA.
    propuesta_financiacion: Literal["SELF_100", "NO_DETERMINADA"]


class ListaCuentasPago(_Estricto):
    cuentas: list[CuentaPago]


class CuentaElegible(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str
    moneda: str


class ListaCuentasElegibles(_Estricto):
    """Cuentas elegibles para una operacion del registro (J2 §1.1, R1)."""

    operacion: Literal["GASTO", "INGRESO", "TRANSFERENCIA_ORIGEN", "TRANSFERENCIA_DESTINO"]
    cuentas: list[CuentaElegible]


class GastoMesVs01(_Estricto):
    """Lectura ESTRECHA VS-01. Candidata a sustitucion por F08 (F08-07).

    `estado` sigue DS-RULE-39/40: CONFIRMADO solo si todo lo del periodo es
    calculable; PARCIAL si hay gastos sin reparto conocido o en otra moneda
    (que NO se convierten ni se suman como cero).
    """

    mes: str
    moneda: Literal["EUR"]
    gasto_atribuible: str
    estado: Literal["CONFIRMADO", "PARCIAL"]
    gastos_sin_reparto: int
    gastos_otra_moneda: int
    contrato: str


class ErrorApi(_Estricto):
    codigo: str
    mensaje: str
    reintentable: bool
