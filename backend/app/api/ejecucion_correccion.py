# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_correccion.py
# Ruta: backend/app/api/ejecucion_correccion.py
# Descripcion: F04-R2 R2-B (contrato F04-R2 v0.8 §2.1.5, §6.7.1; mandato
#   F04-R2B v1.0 §2.4). Adaptador INTERNO de la frontera F05 para OP-21P y
#   OP-21T: valida la CAPACIDAD de cada cuenta nueva (PAGAR_GASTO,
#   TRANSFERIR_SALIDA, TRANSFERIR_ENTRADA) y llama al motor en la MISMA
#   transaccion. SIN RUTA HTTP: la ruta y la UI son de F05-06 M1.
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   UNA transaccion (UnidadDeTrabajo, retry completo ante 40P01/40001) con el
#   mismo orden que el motor y que el registro F05 (candidato C de R2-B-PRE):
#     [advisory INVERSIONES, si OP-21P corrige el importe]
#     -> cuentas NUEVAS FOR NO KEY UPDATE en ORDER BY id (bloquear_cuentas)
#     -> capacidad bajo ese lock: motivo_cuenta(..., bloquear=True) toma FOR
#        SHARE de la fila de cuenta_capacidades (cuenta -> capacidad)
#     -> motor (UnidadDeTrabajoAdscrita): vuelve a pedir lo ya poseido y
#        sigue con hecho -> posiciones -> reglas/previsiones -> movimientos.
#   Solo el motivo SIN_CAPACIDAD es de esta capa: CUENTA_SIN_CAPACIDAD (409,
#   sin escritura, como el registro desde M4). Los demas motivos de la cuenta
#   (deshabilitada, cerrada, ledger, moneda, no visible) los decide el motor
#   bajo el mismo lock con sus codigos (§2.1.5, §9). La cuenta ACTUAL de un
#   movimiento no se valida: corregir su importe o su fecha se admite aunque
#   hoy no tenga la capacidad (R-10).
#   Frontera I3 (test_154): excepcion NOMINAL y acotada a este fichero; solo
#   alcanza el motor por CorreccionTesoreriaService.corregir_pago /
#   corregir_transferencia.
# Version: 0.1.0 (F04-R2 R2-B)
# Version: 0.2.0 (F05-06 M1; F05 §61.2; CONTRATO_M1 v0.1 §1): entradas HTTP
#   corregir_pago_http y corregir_transferencia_http: traducen el DTO a los
#   datos de OP-21P / OP-21T sin anadir ni quitar nada y llaman a las mismas
#   funciones (mismo orden de locks, misma revalidacion en el motor). Ni la
#   excepcion I3 ni los metodos alcanzados cambian.
# ============================================================

from __future__ import annotations

from typing import Any

from app.api.dto_edicion import IntencionCorregirPago, IntencionCorregirTransferencia
from app.api.ejecucion_registro import (
    CuentaSinCapacidad,
    RechazoRegistro,
    bloquear_cuentas,
    con_rechazo_capacidad,
    detalle_sin_capacidad,
    tomar_inversiones,
)
from app.comun.elegibilidad_cuentas import SIN_CAPACIDAD, motivo_cuenta
from app.core.contexto import ContextoOperacion
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.services.correccion_tesoreria_service import (
    CorreccionTesoreriaService,
    DatosCorreccionPago,
    DatosCorreccionTransferencia,
    PlanCuentas,
    ResultadoCorreccionTesoreria,
    plan_cuentas_pago,
    plan_cuentas_transferencia,
)
from app.services.previsiones_service import (
    conjunto_impacto_correccion_ancla,
    impacto_correccion_ancla,
)


def _motor(sesion: SesionMotor) -> CorreccionTesoreriaService:
    return CorreccionTesoreriaService(
        UnidadDeTrabajoAdscrita(sesion),
        impacto_ancla=impacto_correccion_ancla,
        conjunto_impacto=conjunto_impacto_correccion_ancla,
    )


def _capacidad_bajo_lock(sesion: SesionMotor, plan: PlanCuentas) -> None:
    """Advisory (si procede) -> cuentas nuevas por UUID -> capacidad de cada una."""
    if plan.advisory:
        tomar_inversiones(sesion)
    if not plan.cuentas_nuevas:
        return
    bloquear_cuentas(sesion, *plan.cuentas_nuevas)
    for cuenta_id in sorted(plan.cuentas_nuevas, key=str):
        operacion = plan.cuentas_nuevas[cuenta_id]
        if plan.fecha is None:
            continue  # hecho no visible: el motor responde AGREGADO_NO_ENCONTRADO
        if motivo_cuenta(sesion, cuenta_id, operacion, plan.fecha, bloquear=True) == SIN_CAPACIDAD:
            raise CuentaSinCapacidad(detalle_sin_capacidad(sesion, cuenta_id, operacion))


def corregir_pago(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                  datos: DatosCorreccionPago) -> ResultadoCorreccionTesoreria | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Any:
        _capacidad_bajo_lock(sesion, plan_cuentas_pago(sesion, datos))
        return _motor(sesion).corregir_pago(contexto, datos)

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),
                           nombre="F04-R2 OP-21P (capacidad + motor)")


def corregir_transferencia(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                           datos: DatosCorreccionTransferencia) -> ResultadoCorreccionTesoreria | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Any:
        _capacidad_bajo_lock(sesion, plan_cuentas_transferencia(sesion, datos))
        return _motor(sesion).corregir_transferencia(contexto, datos)

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),
                           nombre="F04-R2 OP-21T (capacidad + motor)")


# ------------------------------------------------------------------ F05-06 M1: entradas HTTP
def corregir_pago_http(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, hecho_id: Any,
                       intencion: IntencionCorregirPago) -> ResultadoCorreccionTesoreria | RechazoRegistro:
    return corregir_pago(unidad, contexto, DatosCorreccionPago(
        hecho_id=hecho_id, row_version_esperada=intencion.row_version,
        movimiento_row_version_esperada=intencion.movimiento_row_version, motivo=intencion.motivo,
        error_de_registro=intencion.error_de_registro, importe=intencion.importe, fecha=intencion.fecha,
        cuenta_id=intencion.cuenta_id))


def corregir_transferencia_http(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, hecho_id: Any,
                                intencion: IntencionCorregirTransferencia
                                ) -> ResultadoCorreccionTesoreria | RechazoRegistro:
    return corregir_transferencia(unidad, contexto, DatosCorreccionTransferencia(
        hecho_id=hecho_id, row_version_esperada=intencion.row_version,
        movimientos_row_version_esperadas=dict(intencion.movimientos_row_version), motivo=intencion.motivo,
        error_de_registro=intencion.error_de_registro, importe=intencion.importe, fecha=intencion.fecha,
        cuenta_origen_id=intencion.cuenta_origen_id, cuenta_destino_id=intencion.cuenta_destino_id))
