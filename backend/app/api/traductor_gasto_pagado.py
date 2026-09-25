# ============================================================
# GAPTO MOBILE 2027
# Fichero: traductor_gasto_pagado.py
# Ruta: backend/app/api/traductor_gasto_pagado.py
# Descripcion: Traduce la intencion UX VS-01 "gasto cotidiano ya ocurrido y
#   pagado" al contrato OP-22 (DatosHechoCompuesto). NO reimplementa reglas
#   financieras: solo compone la entrada y deja que OP-22 valide y confirme de
#   forma atomica. API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10.
#
#   Composicion (§7 del mandato VS-01):
#     hecho GASTO (OP-01)  fecha_hecho, concepto, importe_total=X, EUR,
#                          presupuestable = decision EXPLICITA del usuario,
#                          estado_localizacion = DESCONOCIDA (aplicable pero
#                          no conocida; nunca NO_APLICA, nunca inventada);
#     efecto GASTO +X      SOLO_MIO    -> COMPLETA, 1 atribucion self MANUAL;
#                          SIN_INDICAR -> NO_DISPONIBLE, sin filas (A01);
#     movimiento -X        en la cuenta elegida, fecha = fecha_hecho
#                          (definicion del caso VS-01: pagado el mismo dia);
#     conciliacion -X      hecho <-> movimiento (signo del movimiento, OP-09);
#     aportacion X         SOLO si la financiacion real es derivable de forma
#                          autorizada: la cuenta tiene en fecha_hecho una unica
#                          participacion vigente, del actor self, al 100 %
#                          -> criterio PARTICIPACION_CUENTA. En otro caso no se
#                          crea (Q01: explicita y opcional; nunca se inventa).
#
#   Identidad: hecho_id = intencion_id y el resto de UUID se derivan con
#   uuid5(intencion_id, <rol>). Un retry de la MISMA intencion reproduce el
#   mismo agregado (OP-22 responde idempotente); la misma intencion con otro
#   contenido choca con IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#
#   Riesgo residual declarado: la participacion de cuenta y el actor self se
#   leen en una transaccion previa a la de OP-22 (TOCTOU). Un cambio de
#   participacion concurrente entre ambas es un caso de desarrollo sin impacto
#   en VS-01; F10 debera decidir si la derivacion entra en la misma unidad.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass

from app.api.dto_vs01 import IntencionGastoPagado
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPagoCompuesto
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.core.unidad_trabajo import SesionMotor

CIEN = decimal.Decimal("100")
ESCALA = decimal.Decimal("0.0001")


def _id(intencion: uuid.UUID, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion, f"gapto.vs01.gasto_pagado.{rol}")


@dataclass(frozen=True, slots=True)
class ContextoDerivacion:
    actor_self_id: uuid.UUID
    cuenta_moneda: str
    financiacion_self_100: bool


def leer_actor_self(sesion: SesionMotor) -> uuid.UUID:
    fila = sesion.uno(
        "SELECT id FROM gapto.actores_financieros "
        "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid "
        "AND tercero_id IS NULL"
    )
    if fila is None:
        raise ErrorMotor(CodigoError.ACTOR_DESCONOCIDO, "El tenant no tiene actor self.")
    return fila[0]


def financiacion_derivable(
    sesion: SesionMotor, cuenta_id: uuid.UUID, actor_self: uuid.UUID, fecha
) -> bool:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT actor_id, porcentaje FROM gapto.cuenta_participaciones "
            "WHERE cuenta_id = %s AND vigente_desde <= %s "
            "AND (vigente_hasta IS NULL OR vigente_hasta >= %s)",
            (cuenta_id, fecha, fecha),
        )
        filas = cur.fetchall()
    return len(filas) == 1 and filas[0][0] == actor_self and filas[0][1] == CIEN


def leer_derivacion(sesion: SesionMotor, intencion: IntencionGastoPagado) -> ContextoDerivacion:
    actor = leer_actor_self(sesion)
    cuenta = sesion.uno(
        "SELECT moneda, enabled FROM gapto.cuentas WHERE id = %s", (intencion.cuenta_id,)
    )
    if cuenta is None or not cuenta[1]:
        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta no existe o no esta disponible.")
    return ContextoDerivacion(
        actor_self_id=actor,
        cuenta_moneda=cuenta[0],
        financiacion_self_100=financiacion_derivable(
            sesion, intencion.cuenta_id, actor, intencion.fecha_hecho
        ),
    )


def componer(intencion: IntencionGastoPagado, deriv: ContextoDerivacion) -> DatosHechoCompuesto:
    if deriv.cuenta_moneda != intencion.moneda:
        # VS-01 solo cubre hecho y cuenta en la misma moneda. Multidivisa no se
        # simula ni se convierte (D-169/D-170 quedan para slices posteriores).
        raise ErrorMotor(
            CodigoError.MONEDA_INVALIDA,
            "VS-01 solo admite pagar desde una cuenta en la misma moneda del gasto.",
        )

    x = intencion.importe.quantize(ESCALA)
    iid = intencion.intencion_id
    hecho_id = iid

    hecho = DatosCreacionHecho(
        hecho_id=hecho_id,
        fecha_hecho=intencion.fecha_hecho,
        moneda=intencion.moneda,
        presupuestable=intencion.presupuestable,
        estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="GASTO",
        concepto=intencion.concepto,
        importe_total=x,
    )

    if intencion.atribucion == "SOLO_MIO":
        efecto = DatosEfecto(
            efecto_id=_id(iid, "efecto"),
            tipo_efecto="GASTO",
            importe_delta=x,
            estado_atribucion="COMPLETA",
            atribuciones=(
                DatosAtribucion(
                    atribucion_id=_id(iid, "atribucion.self"),
                    actor_id=deriv.actor_self_id,
                    importe_atribuido=x,
                    criterio_atribucion="MANUAL",
                    porcentaje_aplicado=CIEN,
                ),
            ),
        )
    else:  # SIN_INDICAR: respuesta explicita "ahora no" -> NO_DISPONIBLE (A01)
        efecto = DatosEfecto(
            efecto_id=_id(iid, "efecto"),
            tipo_efecto="GASTO",
            importe_delta=x,
            estado_atribucion="NO_DISPONIBLE",
        )

    movimiento = DatosMovimiento(
        movimiento_id=_id(iid, "movimiento"),
        cuenta_id=intencion.cuenta_id,
        fecha_movimiento=intencion.fecha_hecho,
        importe=-x,
        clase_movimiento="OPERACION",
        descripcion=intencion.concepto,
    )
    conciliacion = DatosConciliacion(
        conciliacion_id=_id(iid, "conciliacion"),
        hecho_id=hecho_id,
        movimiento_tesoreria_id=movimiento.movimiento_id,
        # La porcion conciliada lleva el SIGNO DEL MOVIMIENTO (salida -> -X):
        # contrato OP-09, no una eleccion del adaptador.
        importe_asignado=-x,
    )
    aportaciones = ()
    if deriv.financiacion_self_100:
        aportaciones = (
            DatosAportacion(
                aportacion_id=_id(iid, "aportacion.self"),
                importe=x,
                criterio_aportacion="PARTICIPACION_CUENTA",
                actor_id=deriv.actor_self_id,
                porcentaje_aplicado=CIEN,
                hecho_movimiento_tesoreria_id=conciliacion.conciliacion_id,
            ),
        )

    return DatosHechoCompuesto(
        hecho=hecho,
        efectos=[efecto],
        pagos=[DatosPagoCompuesto(movimiento=movimiento, conciliacion=conciliacion)],
        aportaciones=list(aportaciones),
    )
