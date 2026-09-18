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
# Version: 0.6.0
#   0.6.0 (F04-05): REVISION_DERIVADA_REQUERIDA (F04-D022) y
#   REAPERTURA_NO_PERMITIDA (F04-D024).
# Version: 0.5.0
#   0.5.0 (F04-05): errores de reglas, previsiones y materializacion.
#   IMPORTE_NO_POSITIVO ya existia de F04-03 y se reutiliza tal cual: el
#   concepto es el mismo y duplicarlo crearia dos codigos para un solo caso.
# Version: 0.4.0
#   0.4.0 (F04-04): errores de posicion financiera. Se conserva
#   EXCEDE_SALDO_DEL_DERECHO como codigo canonico de OP-14 y se anade
#   EXCEDE_SALDO_POSICION para la reduccion generica: no se unifican porque la
#   operacion intentada es parte de la informacion.
# Version: 0.3.0
#   0.3.0 (F04-03): errores canonicos de OP-06 a OP-09. `SIGNO_INCOMPATIBLE` se
#   reutiliza en OP-09 con el mismo significado que en F04-02 —un importe que no
#   hereda el signo de su referencia—, de modo que no se duplica el concepto.
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

    # --- OP-06 ------------------------------------------------------------
    IMPORTE_NO_POSITIVO = "IMPORTE_NO_POSITIVO"
    CRITERIO_INVALIDO = "CRITERIO_INVALIDO"

    # --- OP-06 / OP-07 ----------------------------------------------------
    # Una aportacion financia una SALIDA. Vincularla a una entrada convertiria
    # "quien pago" en "quien cobro", que son dimensiones distintas.
    USO_EN_COBRO_NO_PERMITIDO = "USO_EN_COBRO_NO_PERMITIDO"

    # --- OP-07 ------------------------------------------------------------
    CONCILIACION_DE_OTRO_HECHO = "CONCILIACION_DE_OTRO_HECHO"
    SUMA_EXCEDE_PORCION = "SUMA_EXCEDE_PORCION"
    VINCULO_NO_CORRESPONDE_A_ESA_SALIDA = "VINCULO_NO_CORRESPONDE_A_ESA_SALIDA"

    # --- OP-08 ------------------------------------------------------------
    IMPORTE_CERO = "IMPORTE_CERO"
    CUENTA_DESCONOCIDA = "CUENTA_DESCONOCIDA"

    # --- OP-09 ------------------------------------------------------------
    EXCEDE_IMPORTE_MOVIMIENTO = "EXCEDE_IMPORTE_MOVIMIENTO"
    MOVIMIENTO_ANULADO = "MOVIMIENTO_ANULADO"
    YA_CONCILIADO = "YA_CONCILIADO"

    # --- F04-04 · alta y ciclo de vida de posicion -------------------------
    # Una posicion NUNCA nace de una diferencia calculada (INV-04): exige
    # declaracion explicita del llamante.
    POSICION_SIN_JUSTIFICACION = "POSICION_SIN_JUSTIFICACION"
    CONTRAPARTE_REQUERIDA = "CONTRAPARTE_REQUERIDA"
    CONTRAPARTE_SELF_NO_PERMITIDA = "CONTRAPARTE_SELF_NO_PERMITIDA"
    NATURALEZA_INCOMPATIBLE = "NATURALEZA_INCOMPATIBLE"
    APERTURA_INCONSISTENTE = "APERTURA_INCONSISTENTE"
    CIERRE_SIN_MOTIVO = "CIERRE_SIN_MOTIVO"
    POSICION_CERRADA = "POSICION_CERRADA"

    # --- F04-04 · reduccion de saldo --------------------------------------
    # Dos codigos distintos a proposito: EXCEDE_SALDO_DEL_DERECHO es el
    # canonico de OP-14 y se conserva tal cual; EXCEDE_SALDO_POSICION cubre la
    # reduccion generica de una obligacion. Unificarlos perderia la traza de
    # que operacion se intento.
    EXCEDE_SALDO_DEL_DERECHO = "EXCEDE_SALDO_DEL_DERECHO"
    EXCEDE_SALDO_POSICION = "EXCEDE_SALDO_POSICION"
    SIN_DERECHO_PREVIO = "SIN_DERECHO_PREVIO"

    # --- F04-04 · fronteras economicas ------------------------------------
    INGRESO_NO_PERMITIDO = "INGRESO_NO_PERMITIDO"
    GASTO_DUPLICADO = "GASTO_DUPLICADO"
    CONDONACION_OBLIGACION_NO_SOPORTADA = "CONDONACION_OBLIGACION_NO_SOPORTADA"

    # --- F04-05 · reglas y versionado -------------------------------------
    REGLA_NO_ENCONTRADA = "REGLA_NO_ENCONTRADA"
    VERSION_REGLA_SOLAPADA = "VERSION_REGLA_SOLAPADA"
    CADENCIA_INVALIDA = "CADENCIA_INVALIDA"
    ANCLAJE_INVALIDO = "ANCLAJE_INVALIDO"
    CALENDARIO_ENTIDAD_NO_SOPORTADO = "CALENDARIO_ENTIDAD_NO_SOPORTADO"

    # --- F04-05 · cadena RODANTE e identidad de ocurrencia ----------------
    # CABEZA_RODANTE_DUPLICADA no deberia poder emitirse nunca: existe para que
    # el motor falle cerrado si el lock de regla no llego a actuar. No hay
    # UNIQUE fisico que lo impida.
    CABEZA_RODANTE_BLOQUEADA = "CABEZA_RODANTE_BLOQUEADA"
    CABEZA_RODANTE_DUPLICADA = "CABEZA_RODANTE_DUPLICADA"
    OCURRENCIA_CANCELADA = "OCURRENCIA_CANCELADA"
    OCURRENCIA_OMITIDA = "OCURRENCIA_OMITIDA"

    # --- F04-05 · lifecycle de previsiones --------------------------------
    PREVISION_BLOQUEADA = "PREVISION_BLOQUEADA"
    # F04-D022. La operacion no puede propagar la correccion sin inventar
    # semantica: falla cerrada y la revision se expone por lectura derivada.
    REVISION_DERIVADA_REQUERIDA = "REVISION_DERIVADA_REQUERIDA"
    # F04-D024. CANCELADA es tombstone permanente y no se reabre.
    REAPERTURA_NO_PERMITIDA = "REAPERTURA_NO_PERMITIDA"
    REALIZACION_SIN_HECHO_ACTIVO = "REALIZACION_SIN_HECHO_ACTIVO"
    ESTADO_PREVISION_INCOMPATIBLE = "ESTADO_PREVISION_INCOMPATIBLE"

    # --- F04-05 · importe y materializacion -------------------------------
    ASIGNACION_MULTIDIVISA_NO_DEMOSTRADA = "ASIGNACION_MULTIDIVISA_NO_DEMOSTRADA"
    RESULTADO_SALDO_OBJETIVO_INCOMPATIBLE = "RESULTADO_SALDO_OBJETIVO_INCOMPATIBLE"
    CORRECCION_VINCULO_NO_REPRESENTABLE = "CORRECCION_VINCULO_NO_REPRESENTABLE"

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
