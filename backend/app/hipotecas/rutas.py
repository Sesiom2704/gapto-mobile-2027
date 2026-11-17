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
from app.hipotecas.dto import CuadroPrevio
from app.propiedades import repositorio as repo_prop

_LOG = logging.getLogger(__name__)

#: codigo -> (status, mensaje de usuario)
RECHAZOS: dict[str, tuple[int, str]] = {
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    calc.CONDICIONES_INCOMPLETAS: (422, "Revisa las condiciones de la hipoteca."),
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
