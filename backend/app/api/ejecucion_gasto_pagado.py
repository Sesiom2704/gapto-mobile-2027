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
#
#   v0.3.0 (F05-01, F05-D009 §23.3 C-a): guarda de elegibilidad categorial.
#   Solo para intencion NUEVA con {estado: CATEGORIA}, despues de reconocer la
#   identidad y ANTES de componer OP-22 (paso 3b):
#     cuenta (FOR NO KEY UPDATE) -> identidad -> categoria (FOR SHARE) ->
#     relectura owner/enabled/ambito -> OP-22.
#   Un reintento de una intencion ya materializada NO revalida la categoria
#   (un hecho valido no se rechaza porque su categoria se desactivara
#   despues). SIN_CATEGORIA no invoca la guarda.
#   Orden de locks resultante: cuenta -> categoria -> raiz -> movimiento. La
#   gestion del catalogo no bloquea cuentas, asi que no se crea un ciclo; VS-01
#   no escribe hecho_entidades, de modo que el advisory INVERSIONES no entra
#   (F05-01-R11: cualquier slice que lo haga exige auditar antes el grafo).
#   Los rechazos son valores de capa F05 (sin escritura previa).
#
#   v0.4.0 (F05-01, S6-C07; F05-D014 §28.2): C07 con el servidor como
#   autoridad. Solo para intencion NUEVA con {estado: CATEGORIA}, DESPUES de
#   la guarda C-a y ANTES de componer (paso 3c):
#     cuenta -> identidad -> categoria (FOR SHARE) -> categoria_magnitudes
#     (FOR SHARE, por id) -> magnitudes (FOR SHARE, por id) -> OP-22.
#   Un reintento de una intencion ya materializada no revalida magnitudes
#   (AJ-C07-04): OP-22 decide idempotencia o IDENTIDAD_REUTILIZADA por
#   igualdad exacta del agregado, incluidas las filas de hecho_magnitudes.
#   Orden de locks resultante: cuenta -> categoria -> categoria_magnitudes ->
#   magnitudes -> raiz -> movimiento. Hoy no existe writer runtime de
#   magnitudes ni de categoria_magnitudes (gate F05-01-R16).
#
#   v0.5.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03): la intencion
#   trae SIEMPRE un estado categorial resuelto (CATEGORIA o SIN_CATEGORIA):
#   se retira el estado de compatibilidad derivado de la ausencia del campo.
#   Sin cambios de logica: CATEGORIA pasa por C-a y C07; SIN_CATEGORIA
#   persiste NULL sin invocar la guarda.
#
#   v0.6.0 (F05-03/F05-04 J2 §1.1; F05 §46.4 R1/R2, §46.5 E1; F05-D032 C1):
#   la relectura de la cuenta bajo el lock (paso 3) usa el contrato unico
#   comun/elegibilidad_cuentas.py (operacion GASTO: PAGAR_GASTO, EUR, ledger,
#   cierre, habilitada) en la fecha del pago. Se retira el filtro ACTIVO: una
#   cuenta PASIVO con PAGAR_GASTO paga el gasto (un efecto GASTO y un
#   movimiento en la cuenta de credito; ningun efecto de deuda). Motivo MONEDA
#   -> MONEDA_INVALIDA (como antes); cualquier otro -> CUENTA_DESCONOCIDA.
# Version: 0.6.0
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

from app.api.captura_magnitudes import validar_magnitudes
from app.api.dto_vs01 import IntencionGastoPagado
from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.api.traductor_gasto_pagado import componer, leer_actor_self, participacion_self_100
from app.comun.elegibilidad_cuentas import MONEDA, motivo_cuenta
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
    """Regla unica R1 (GASTO) bajo el lock de la cuenta, en la fecha del pago."""
    motivo = motivo_cuenta(sesion, intencion.cuenta_id, "GASTO", intencion.fecha_hecho)
    if motivo == MONEDA:
        # VS-01 solo cubre hecho y cuenta en la misma moneda; multidivisa no se
        # simula ni se convierte (D-169/D-170 quedan para slices posteriores).
        raise ErrorMotor(
            CodigoError.MONEDA_INVALIDA,
            "VS-01 solo admite pagar desde una cuenta en la misma moneda del gasto.",
        )
    if motivo is not None:
        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta no existe o no esta disponible.")


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
            # 3b. Guarda categorial C-a, solo para seleccion nueva explicita.
            if intencion.categoria_id is not None:
                rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, "GASTO")
                if rechazo is not None:
                    return RechazoIntegracion(rechazo)
                # 3c. C07: magnitudes de la categoria elegida (servidor autoridad).
                rechazo = validar_magnitudes(sesion, intencion.categoria_id, intencion.magnitudes)
                if rechazo is not None:
                    return RechazoIntegracion(rechazo)

        # 5. OP-22 adscrito a esta transaccion. La composicion sale SOLO del
        #    payload sellado; si la raiz existe, OP-22 exige igualdad EXACTA
        #    del agregado (F04-D050/F04-D051): la capa F05 no la duplica.
        datos = componer(intencion, actor)
        op22 = HechosCompuestosService(
            UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla
        )
        return Registrado(resultado=op22.registrar_hecho_compuesto(contexto, datos), datos=datos)

    return unidad.ejecutar(contexto, operacion, nombre="VS01 gasto_pagado (lock cuenta + OP-22)")
