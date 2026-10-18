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
# ============================================================

from __future__ import annotations

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
