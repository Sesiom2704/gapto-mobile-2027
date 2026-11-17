# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas.py
# Ruta: backend/app/hipotecas/rutas.py
# Descripcion: Rutas HTTP de la hipoteca (F06-01H; contrato v0.4 §3.1, §3.3 y §7; API DE INTEGRACION, PENDIENTE
#   DE CONSOLIDACION F10), registradas por `create_app` con una sola llamada:
#     POST /v1/hipotecas/cuadro                 W-HIP-00 vista previa del cuadro. SIN ESCRITURA: no abre
#                                               transaccion ni toca la base (POST sin escritura en test_215).
#     GET  /v1/propiedades/{propiedad_id}/hipoteca   L-HIP lectura (UnidadDeTrabajo, gapto_runtime con RLS).
#   Rechazos con el formato vigente ({codigo, mensaje, reintentable, detalle}) y, cuando hay motivo, `motivo`
#   tambien en el nivel superior (contrato §7.2): CONDICIONES_INCOMPLETAS 422 con motivo SISTEMA_NO_SOPORTADO,
#   PERIODICIDAD_NO_SOPORTADA o VALORES_FUERA_DE_RANGO. CUADRO_NO_CUADRA es un defecto: sale como
#   VIOLACION_INVARIANTE_FISICA 500 (traduccion vigente de errores_http) y se registra en el log; en W-HIP-00 no
#   hay transaccion que deshacer ni auditoria que escribir.
#   L-HIP: propiedad no visible para el owner (inexistente o de otro owner) -> 404 AGREGADO_NO_ENCONTRADO,
#   indistinguibles (G9); propiedad visible sin hipoteca -> 200 {"hipoteca": null} (forma del contrato §3.3).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 6): POST /v1/hipotecas/{financiacion_id}/cuotas/{numero}/pago
#   (W-HIP-02, servicio propio pago.py) con sus rechazos (contrato v0.4 §7.3).
# Version: 0.3.0 (F06 T3-F06 bloque 2 F06-01H, paso 7): POST /v1/hipotecas/{financiacion_id}/revision (W-HIP-03/04,
#   servicio propio revision.py): REVISION_SOBRE_CUOTA_PAGADA y SIN_CUOTAS_FUTURAS 409, FECHA_REVISION_INCOHERENTE
#   422; CUADRO_NO_CUADRA -> log, ErrorMotor VIOLACION_INVARIANTE_FISICA (500) y ROLLBACK (revision.py).
# ============================================================

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any, Callable

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.api import errores_http as eh
from app.comun.fecha_funcional import hoy_owner
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError
from app.hipotecas import calculadora as calc
from app.hipotecas import lecturas
from app.hipotecas import pago as serv_pago
from app.hipotecas import revision as serv_revision
from app.hipotecas.dto import CuadroPrevio, PagoCuota, RevisionTipo
from app.patrimonio.completitud import Rechazo
from app.propiedades import repositorio as repo_prop

_LOG = logging.getLogger(__name__)

#: codigo -> (status, mensaje de usuario)
RECHAZOS: dict[str, tuple[int, str]] = {
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    calc.CONDICIONES_INCOMPLETAS: (422, "Revisa las condiciones de la hipoteca."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "OPERACION_NO_PERMITIDA_EN_ESTADO": (409, "La hipoteca no está activa."),
    "SALDO_PRINCIPAL_INDETERMINADO": (409, "No se conoce lo que quedaba por pagar de esta hipoteca: no se puede pagar ni revisar."),
    "CUOTA_NO_PENDIENTE": (409, "Esta cuota ya no está pendiente."),
    "VERSION_DESFASADA": (409, "La hipoteca ha cambiado desde que la abriste. Vuelve a cargarla."),
    "CUOTA_ANTERIOR_PENDIENTE": (409, "Hay una cuota anterior sin pagar."),
    "FECHA_PAGO_INCOHERENTE": (422, "La fecha del cargo no puede ser futura."),
    "EXCEDE_SALDO_POSICION": (409, "El capital supera lo que queda por pagar."),
    "CUENTA_DESCONOCIDA": (422, "Esa cuenta no se puede usar para pagar en esa fecha."),
    "ATRIBUCION_PROPUESTA_DESFASADA": (409, "La titularidad del préstamo ha cambiado. Revisa el reparto de los intereses."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
    "SUMA_NO_CUADRA": (422, "El reparto no suma el 100 %."),
    "REVISION_SOBRE_CUOTA_PAGADA": (409, "La revisión afecta a una cuota que ya no está pendiente."),
    "SIN_CUOTAS_FUTURAS": (409, "No quedan cuotas desde esa fecha."),
    "FECHA_REVISION_INCOHERENTE": (422, "La fecha de la revisión debe ser posterior a la de las condiciones vigentes."),
}


def rechazo(codigo: str, motivo: str | None = None) -> JSONResponse:
    status, mensaje = RECHAZOS[codigo]
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if motivo is not None:
        cuerpo["motivo"] = motivo
        cuerpo["detalle"] = {"motivo": motivo}
    return JSONResponse(cuerpo, status_code=status)


def _texto(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _texto(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor]
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def vista_previa(c: CuadroPrevio) -> dict[str, Any]:
    """W-HIP-00: cuadro calculado sin tocar la base (contrato §3.1)."""
    filas = calc.cuadro_frances(c.capital, c.tasa_anual, c.numero_cuotas, c.primera_cuota, sistema=c.sistema,
                                periodicidad=c.periodicidad)
    sumas = calc.resumen(filas)
    return _texto({
        "sistema": calc.SISTEMA, "periodicidad": calc.PERIODICIDAD, "convencion": calc.CONVENCION,
        "capital": calc.r2(c.capital), "tasa_anual": format(c.tasa_anual.normalize(), "f"),
        "numero_cuotas": c.numero_cuotas, **sumas,
        "cuotas": [{"n": f.numero, "vencimiento": f.vencimiento, "cuota": f.cuota, "interes": f.interes,
                    "capital": f.capital, "comision": f.comision, "pendiente": f.pendiente} for f in filas],
    })


def registrar(app: FastAPI, *, unidad, contexto: Callable[[], ContextoOperacion], autorizar, reloj) -> None:
    dep = [Depends(autorizar)]

    @app.post("/v1/hipotecas/cuadro", dependencies=dep)
    def cuadro_previo(c: CuadroPrevio):
        try:
            return vista_previa(c)
        except calc.CondicionesIncompletas as exc:
            return rechazo(exc.codigo, exc.motivo)
        except calc.CuadroNoCuadra as exc:
            _LOG.error("CUADRO_NO_CUADRA en W-HIP-00: %s", exc.motivo)
            status, cuerpo = eh.traducir_error_motor(CodigoError.VIOLACION_INVARIANTE_FISICA)
            return JSONResponse(cuerpo, status_code=status)

    @app.get("/v1/propiedades/{propiedad_id}/hipoteca", dependencies=dep)
    def hipoteca_de_propiedad(propiedad_id: uuid.UUID):
        def leer_hipoteca(s):
            if repo_prop.leer(s, propiedad_id) is None:
                return None
            return {"hipoteca": lecturas.leer_de_propiedad(s, propiedad_id, hoy_owner(s, reloj))}
        salida = unidad.ejecutar(contexto(), leer_hipoteca, nombre="F06-01H L-HIP")
        if salida is None:
            return rechazo("AGREGADO_NO_ENCONTRADO")
        return _texto(salida)

    @app.post("/v1/hipotecas/{financiacion_id}/cuotas/{numero}/pago", dependencies=dep)
    def pagar_cuota(financiacion_id: uuid.UUID, numero: int, c: PagoCuota):
        peticion = c.model_dump()
        ctx = contexto()
        ctx = ContextoOperacion.de_usuario(ctx.owner_user_id, request_id=c.intencion_id)
        salida = unidad.ejecutar(ctx, lambda s: serv_pago.pagar(s, financiacion_id=financiacion_id, numero=numero,
                                                                  peticion=peticion, reloj=reloj),
                                 nombre="F06-01H W-HIP-02")
        if isinstance(salida, Rechazo):
            return rechazo(salida.codigo)
        return _texto(salida)

    @app.post("/v1/hipotecas/{financiacion_id}/revision", dependencies=dep)
    def revisar_tipo(financiacion_id: uuid.UUID, c: RevisionTipo):
        peticion = c.model_dump()
        ctx = contexto()
        ctx = ContextoOperacion.de_usuario(ctx.owner_user_id, request_id=c.intencion_id)
        salida = unidad.ejecutar(ctx, lambda s: serv_revision.revisar(s, financiacion_id=financiacion_id,
                                                                      peticion=peticion, reloj=reloj),
                                 nombre="F06-01H W-HIP-03/04")
        if isinstance(salida, Rechazo):
            return rechazo(salida.codigo, (salida.detalle or {}).get("motivo"))
        return _texto(salida)
