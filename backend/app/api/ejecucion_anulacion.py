# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_anulacion.py
# Ruta: backend/app/api/ejecucion_anulacion.py
# Descripcion: F04-R2 R2-C (contrato F04-R2 v0.9 §2.3.10; mandato F04-R2C
#   v1.0 §1). Adaptador INTERNO de la frontera F05 para OP-03P «anular un
#   registro pagado por duplicado». SIN RUTA HTTP: las rutas, el detalle de un
#   anulado, la elegibilidad visible y la declaracion explicita son de F05-06
#   M1. API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   UNA transaccion (UnidadDeTrabajo, retry completo ante 40P01/40001). OP-03P
#   no cambia de cuenta: no hay capacidad que validar en esta capa ni cuentas
#   que bloquear (§6.6: OP-03P no adquiere el nivel 2 ni el 2 bis). El orden lo
#   fija el motor: hecho -> posiciones -> reglas/previsiones -> movimientos.
#   Frontera I3 (test_154): excepcion NOMINAL y acotada a este fichero; solo
#   alcanza el motor por AnulacionTesoreriaService.anular_registro.
# Version: 0.1.0 (F04-R2 R2-C)
# Version: 0.2.0 (F05-06 M1; F05 §61.2; CONTRATO_M1 v0.1 §1, §2.4): entrada
#   HTTP anular_duplicado_http: la declaracion explicita del DTO
#   (`duplicado_declarado`) es la unica via a `movimiento_en_banco = false`;
#   sin ella el motor recibe None y rechaza. Misma funcion, mismo motor.
# Version: 0.3.0 (F05-D052 paso 2; F05 §66.A.9, AJ-F0507G3-04): la entrada HTTP
#   rechaza un hecho ACTIVO con posiciones vinculadas con la guarda vigente
#   POSICIONES (HECHO_CON_REALIDAD_ASOCIADA, motivo POSICIONES; 409), antes de
#   llamar al motor y sin escribir nada: antes de cobrar, tras un cobro parcial
#   y tras el total. Los vinculos GENERADO_POR solo nacen con el hecho (OP-22),
#   asi que leerlos sin lock no tiene carrera. Un hecho ya ANULADO lo decide el
#   motor (replay idempotente). anular_registro (frontera R2-C) no cambia.
# ============================================================

from __future__ import annotations

from app.api.dto_edicion import IntencionAnularDuplicado
from app.actividad.edicion import con_posiciones
from app.core.errores import CodigoError, ErrorMotor
from app.core.contexto import ContextoOperacion
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.services.anulacion_tesoreria_service import (
    AnulacionTesoreriaService,
    DatosAnulacionRegistro,
    ResultadoAnulacionRegistro,
)
from app.services.previsiones_service import adquirir_impacto_ancla, aplicar_impacto_ancla


def motor(unidad: UnidadDeTrabajo) -> AnulacionTesoreriaService:
    return AnulacionTesoreriaService(unidad, adquirir_impacto=adquirir_impacto_ancla,
                                     aplicar_impacto=aplicar_impacto_ancla)


def anular_registro(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                    datos: DatosAnulacionRegistro) -> ResultadoAnulacionRegistro:
    def operacion(sesion: SesionMotor) -> ResultadoAnulacionRegistro:
        return motor(UnidadDeTrabajoAdscrita(sesion)).anular_registro(contexto, datos)

    return unidad.ejecutar(contexto, operacion, nombre="F04-R2 OP-03P (adaptador F05)")


# ------------------------------------------------------------------ F05-06 M1: entrada HTTP
def anular_duplicado_http(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, hecho_id,
                          intencion: IntencionAnularDuplicado) -> ResultadoAnulacionRegistro:
    """«Anular por duplicado»: solo con la declaracion explicita el motor recibe
    `movimiento_en_banco = false`; sin ella recibe None y rechaza (§2.3.3).
    §66.A.9: un hecho ACTIVO con posiciones vinculadas no se anula por esta via."""
    datos = DatosAnulacionRegistro(
        hecho_id=hecho_id, row_version_esperada=intencion.row_version,
        movimientos_row_version_esperadas=dict(intencion.movimientos_row_version), motivo=intencion.motivo,
        movimiento_en_banco=False if intencion.duplicado_declarado is True else None)

    def operacion(sesion: SesionMotor) -> ResultadoAnulacionRegistro:
        activo = sesion.uno("SELECT estado = 'ACTIVO' FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))
        if activo is not None and activo[0] and con_posiciones(sesion, hecho_id):
            raise ErrorMotor(CodigoError.HECHO_CON_REALIDAD_ASOCIADA,
                             "El hecho tiene posiciones vinculadas: no se anula por esta via.",
                             contexto_extra={"motivo": "POSICIONES"})
        return motor(UnidadDeTrabajoAdscrita(sesion)).anular_registro(contexto, datos)

    return unidad.ejecutar(contexto, operacion, nombre="F05-D052 OP-03P HTTP (guarda POSICIONES + motor)")
