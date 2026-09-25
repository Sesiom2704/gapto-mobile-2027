# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_gasto_pagado.py
# Ruta: backend/app/api/ejecucion_gasto_pagado.py
# Descripcion: Ejecucion transaccional de la intencion VS-01 "gasto pagado"
#   (F05-D003 §16.5). API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION
#   F10.
#
#   UNA sola transaccion del adaptador (UnidadDeTrabajo, retry completo ante
#   40P01/40001, D-171) con este orden fijo:
#     1. lock FOR NO KEY UPDATE sobre la fila de la cuenta: el mismo root que
#        toman los validadores de cuenta_participaciones (DB Schema, F03-02).
#        Serializa frente a cualquier cambio de participacion de esa cuenta y
#        no bloquea altas de movimientos (la FK toma FOR KEY SHARE,
#        compatible; D-114);
#     2. reconocimiento de IDENTIDAD: si la intencion ya esta materializada se
#        delega en OP-22, que responde idempotente o
#        IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, SIN revalidar el contexto
#        actual (un hecho valido no se rechaza retrospectivamente);
#     3. intencion nueva: relectura de cuenta, actor self y participacion
#        vigente en la fecha del pago, ya bajo el lock;
#     4. revalidacion de la propuesta sellada; si no se sostiene ->
#        PROPUESTA_FINANCIACION_OBSOLETA (rechazo definitivo; ni se sustituye
#        por NO_DETERMINADA ni se recalcula otro actor);
#     5. OP-22 ADSCRITO a esta misma transaccion (UnidadDeTrabajoAdscrita), sin
#        tocar su codigo certificado.
#
#   Por que el lock va ANTES de la identidad: dos envios identicos solapados
#   se serializan en la cuenta; el segundo, tras el COMMIT del primero, ve la
#   raiz y responde idempotente en vez de revalidar contra un contexto que
#   pudo cambiar despues.
#
#   Orden de locks resultante: cuenta -> raiz hechos_financieros -> movimiento.
#   Hecho y movimiento nacen en esta transaccion, asi que ninguna otra puede
#   tenerlos bloqueados: no se introduce un ciclo nuevo.
#
#   PROPUESTA_FINANCIACION_OBSOLETA es un codigo de la capa F05 (§16.5), no de
#   la taxonomia F04. Se devuelve como valor (no excepcion) porque en ese punto
#   la transaccion no ha escrito nada: el COMMIT vacio solo libera el lock.
#
#   v0.2.0 (F05 §18, tras F04-D051): se retira la guarda transitoria
#   `_agregado_sin_extras`; la igualdad exacta del agregado en el
#   reconocimiento de identidad la impone OP-22 recertificado.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

from app.api.dto_vs01 import IntencionGastoPagado
from app.api.traductor_gasto_pagado import componer, leer_actor_self, participacion_self_100
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_compuesto import DatosHechoCompuesto, ResultadoHechoCompuesto
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import hechos_repository as repo_hechos
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla

CODIGO_PROPUESTA_OBSOLETA = "PROPUESTA_FINANCIACION_OBSOLETA"


@dataclass(frozen=True, slots=True)
class Registrado:
    resultado: ResultadoHechoCompuesto
    datos: DatosHechoCompuesto


@dataclass(frozen=True, slots=True)
class RechazoIntegracion:
    codigo: str


def bloquear_cuenta(sesion: SesionMotor, cuenta_id) -> None:
    """Lock contractual de la cuenta. Si no es visible (inexistente u otro
    tenant) no hay fila que bloquear; la validacion de intencion nueva lo
    rechaza despues."""
    sesion.uno(
        "SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE",
        (cuenta_id,),
    )


def _validar_cuenta_nueva(sesion: SesionMotor, intencion: IntencionGastoPagado) -> None:
    fila = sesion.uno(
        "SELECT moneda, enabled, naturaleza, fecha_cierre FROM gapto.cuentas WHERE id = %s",
        (intencion.cuenta_id,),
    )
    if fila is None or not fila[1] or fila[2] != "ACTIVO" or (
        fila[3] is not None and fila[3] <= intencion.fecha_hecho
    ):
        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta no existe o no esta disponible.")
    if fila[0] != intencion.moneda:
        # VS-01 solo cubre hecho y cuenta en la misma moneda; multidivisa no se
        # simula ni se convierte (D-169/D-170 quedan para slices posteriores).
        raise ErrorMotor(
            CodigoError.MONEDA_INVALIDA,
            "VS-01 solo admite pagar desde una cuenta en la misma moneda del gasto.",
        )


def registrar_gasto_pagado(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, intencion: IntencionGastoPagado
) -> Registrado | RechazoIntegracion:
    def operacion(sesion: SesionMotor) -> Registrado | RechazoIntegracion:
        # 1. Lock contractual de la cuenta.
        bloquear_cuenta(sesion, intencion.cuenta_id)
        actor = leer_actor_self(sesion)

        # 2. Identidad antes que cualquier revalidacion contextual.
        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None

        if not ya_materializada:
            # 3. Intencion nueva: relectura bajo el lock.
            _validar_cuenta_nueva(sesion, intencion)
            # 4. Revalidacion de la propuesta sellada, en la fecha del pago.
            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not participacion_self_100(
                sesion, intencion.cuenta_id, actor, intencion.fecha_hecho
            ):
                return RechazoIntegracion(CODIGO_PROPUESTA_OBSOLETA)

        # 5. OP-22 adscrito a esta transaccion. La composicion sale SOLO del
        #    payload sellado; si la raiz existe, OP-22 exige igualdad EXACTA
        #    del agregado (F04-D050/F04-D051): la capa F05 no la duplica.
        datos = componer(intencion, actor)
        op22 = HechosCompuestosService(
            UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla
        )
        return Registrado(resultado=op22.registrar_hecho_compuesto(contexto, datos), datos=datos)

    return unidad.ejecutar(contexto, operacion, nombre="VS01 gasto_pagado (lock cuenta + OP-22)")
