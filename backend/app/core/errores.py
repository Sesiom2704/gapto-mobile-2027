# ============================================================
# GAPTO MOBILE 2027
# Fichero: errores.py
# Ruta: backend/app/core/errores.py
# Descripcion: Taxonomia de errores funcionales del motor financiero (F04-01).
#
#   Contrato: el dominio NUNCA expone SQLSTATE, texto de PostgreSQL, nombres de
#   constraint ni SQL hacia una capa cliente. `CodigoError` es el contrato
#   semantico; la causa tecnica original se conserva en `causa`/`sqlstate`
#   exclusivamente para diagnostico interno y no se serializa.
#
#   CONFLICTO_CONCURRENCIA y OPERACION_NO_PERMITIDA_EN_ESTADO se mantienen
#   separados deliberadamente: el primero significa "nada se ha persistido,
#   puede reintentarse"; el segundo significa "el estado actual impide la
#   operacion y reintentar no la hara posible". Fusionarlos haria que la UX
#   reintentase indefinidamente algo imposible, o que abandonase algo que solo
#   necesitaba otro intento.
# Version: 0.2.0
#   0.2.0 (F04-02): se anaden los errores canonicos de OP-04 y OP-05 y el error
#   estable de F04-D004. Se RETIRA `DECISION_DIFERIDA_F04_02`, que era
#   transitorio: ningun camino vigente puede emitirlo y conservarlo invitaria a
#   leer una frontera ya aprobada como una decision todavia pendiente.
# ============================================================

from __future__ import annotations

import enum
from typing import Any


class CodigoError(str, enum.Enum):
    """Conjunto cerrado de errores funcionales del motor.

    Cerrado quiere decir cerrado: anadir un valor es un cambio del contrato de
    la API interna y pertenece al expediente F04, no a un caso de uso concreto.
    """

    # --- Comunes del motor (mandato F04-01, seccion 10) ------------------
    TENANT_AUSENTE = "TENANT_AUSENTE"
    AGREGADO_NO_ENCONTRADO = "AGREGADO_NO_ENCONTRADO"
    VERSION_DESFASADA = "VERSION_DESFASADA"
    CONFLICTO_CONCURRENCIA = "CONFLICTO_CONCURRENCIA"
    VIOLACION_INVARIANTE_FISICA = "VIOLACION_INVARIANTE_FISICA"
    OPERACION_NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"

    # --- OP-01 ------------------------------------------------------------
    TIPO_HECHO_DESCONOCIDO = "TIPO_HECHO_DESCONOCIDO"
    MONEDA_INVALIDA = "MONEDA_INVALIDA"
    FECHA_ECONOMICA_AUSENTE = "FECHA_ECONOMICA_AUSENTE"
    IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"

    # --- OP-02 ------------------------------------------------------------
    CORRECCION_IMPROCEDENTE_ES_REALIDAD_NUEVA = "CORRECCION_IMPROCEDENTE_ES_REALIDAD_NUEVA"
    MOTIVO_AUSENTE = "MOTIVO_AUSENTE"
    CAMPO_INMUTABLE = "CAMPO_INMUTABLE"

    # --- F04-D004 ---------------------------------------------------------
    # Sustituye al transitorio DECISION_DIFERIDA_F04_02. La frontera dejo de
    # ser una decision pendiente y es una regla aprobada: corregir el tipo de
    # un hecho con efectos exige correccion agregada explicita (F04-06).
    CORRECCION_AGREGADA_REQUERIDA = "CORRECCION_AGREGADA_REQUERIDA"

    # --- OP-03 ------------------------------------------------------------
    HECHO_CON_REALIDAD_ASOCIADA = "HECHO_CON_REALIDAD_ASOCIADA"

    # --- OP-04 ------------------------------------------------------------
    DELTA_CERO = "DELTA_CERO"
    NATURALEZA_INVALIDA = "NATURALEZA_INVALIDA"
    VALOR_ACTIVO_SIN_ACONTECIMIENTO = "VALOR_ACTIVO_SIN_ACONTECIMIENTO"

    # --- OP-05 ------------------------------------------------------------
    SUMA_NO_CUADRA = "SUMA_NO_CUADRA"
    SIGNO_INCOMPATIBLE = "SIGNO_INCOMPATIBLE"
    NO_DISPONIBLE_CON_FILAS = "NO_DISPONIBLE_CON_FILAS"
    ACTOR_DESCONOCIDO = "ACTOR_DESCONOCIDO"

    # --- Transversales ----------------------------------------------------
    ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
    BD_NO_DISPONIBLE = "BD_NO_DISPONIBLE"
    INTERNO = "INTERNO"


class ErrorMotor(Exception):
    """Error funcional del motor financiero.

    `mensaje` se redacta para el dominio y no se construye concatenando el
    texto del error de PostgreSQL: ese texto puede revelar nombres internos,
    constraints o datos de otro tenant.
    """

    __slots__ = ("codigo", "mensaje", "causa", "sqlstate", "contexto_extra")

    def __init__(
        self,
        codigo: CodigoError,
        mensaje: str,
        *,
        causa: BaseException | None = None,
        sqlstate: str | None = None,
        contexto_extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{codigo.value}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje
        self.causa = causa
        self.sqlstate = sqlstate
        self.contexto_extra = dict(contexto_extra or {})

    def diagnostico_interno(self) -> dict[str, Any]:
        """Datos para log interno. NO forma parte del contrato hacia cliente."""
        datos: dict[str, Any] = {
            "codigo": self.codigo.value,
            "mensaje": self.mensaje,
            "sqlstate": self.sqlstate,
            "causa": None if self.causa is None else repr(self.causa),
        }
        datos.update(self.contexto_extra)
        return datos

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuracion
        return f"ErrorMotor({self.codigo.value})"
