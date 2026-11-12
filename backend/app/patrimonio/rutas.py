# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas.py
# Ruta: backend/app/patrimonio/rutas.py
# Descripcion: Rutas HTTP de B2 (API DE INTEGRACION, PENDIENTE DE CONSOLIDACION F10), registradas por
#   `create_app` con una sola llamada:
#     POST /v1/propiedades/{id}/compra                C-COMPRA-01
#     POST /v1/propiedades/{id}/compra/gastos         C-COMPRA-03
#     GET  /v1/propiedades/{id}/titularidad-en-fecha?fecha=  titularidad vigente en una fecha (P-H2-03,
#                                                     adelantada a B2; sin fecha, hoy del owner)
#     GET  /v1/propiedades/{id}/coste?a_fecha=        L-COSTE (sin la declaracion mientras 0352 no este
#                                                     certificada)
#     POST /v1/propiedades/{id}/completitud           C-PROP-05: 404 FUNCION_NO_HABILITADA mientras
#                                                     habilitacion.CONSUMIDORES_0352_HABILITADOS sea False (O10.29)
#   Una transaccion de UnidadDeTrabajo por comando, con request_id = intencion_id (identidad de la auditoria).
#   Rechazos con su mapa propio (patron _RECHAZOS_PROPIEDAD de B1); los codigos existentes conservan su status.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Callable

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.comun.fecha_funcional import hoy_owner
from app.core.contexto import ContextoOperacion
from app.patrimonio import atribucion as m2
from app.patrimonio import compra, completitud, coste, habilitacion
from app.patrimonio.dto import DeclararCompletitud, GastoCompraPosterior, RegistrarCompra
from app.propiedades import repositorio as repo

#: codigo -> (status, mensaje de usuario)
RECHAZOS: dict[str, tuple[int, str]] = {
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    habilitacion.FUNCION_NO_HABILITADA: (404, "No disponible."),
    "VERSION_DESFASADA": (409, "La propiedad ha cambiado desde que la abriste. Vuelve a cargarla."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
    "SUMA_NO_CUADRA": (422, "Los importes no cuadran con el total."),
    "PARTICIPANTE_DUPLICADO": (422, "Hay una persona repetida en el reparto."),
    "COMPRA_YA_REGISTRADA": (409, "Esta propiedad ya tiene su compra registrada."),
    "COMPRA_NO_REGISTRADA": (409, "Primero registra la compra de esta propiedad."),
    "FECHA_PAGO_INCOHERENTE": (422, "Las arras no pueden ser posteriores a la escritura y el pago de la firma va en la fecha de escritura."),
    "PROPIEDAD_NO_DISPONIBLE": (409, "Esta propiedad no está disponible."),
    "OPERACION_NO_PERMITIDA_EN_ESTADO": (422, "No se puede hacer en el estado actual de la propiedad."),
    "CUENTA_DESCONOCIDA": (422, "Esa cuenta no se puede usar para pagar en esa fecha."),
    "TITULARIDAD_NO_DISPONIBLE_EN_FECHA": (422, "No hay titularidad registrada en esa fecha. Elige otro reparto o «No lo sé»."),
    "ATRIBUCION_PROPUESTA_DESFASADA": (409, "La titularidad ha cambiado. Revisa de quién es el coste."),
    "COMPLETITUD_VISTA_DESFASADA": (409, "El coste ha cambiado desde que lo viste. Vuelve a cargarlo."),
    "COMPLETITUD_SIN_COMPONENTES": (422, "No hay ningún coste de compra hasta esa fecha."),
    "COMPLETITUD_SIN_FECHA_DE_CORTE": (422, "Revisa la fecha: no puede ser futura ni anterior a la compra."),
}


def rechazo(codigo: str, detalle: dict | None = None) -> JSONResponse:
    status, mensaje = RECHAZOS[codigo]
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if detalle:
        cuerpo["detalle"] = detalle
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
    if hasattr(valor, "as_tuple"):     # Decimal: texto exacto (v0.8 §1.2)
        return str(valor)
    return valor


def registrar(app: FastAPI, *, unidad, owner: Callable[[], uuid.UUID], contexto: Callable[[], ContextoOperacion],
              autorizar, reloj) -> None:
    dep = [Depends(autorizar)]

    def _comando(nombre: str, intencion_id: uuid.UUID, operacion) -> Any:
        ctx = ContextoOperacion.de_usuario(owner(), request_id=intencion_id)
        salida = unidad.ejecutar(ctx, operacion, nombre=f"F06-01 B2 {nombre}")
        if isinstance(salida, completitud.Rechazo):
            return rechazo(salida.codigo, salida.detalle)
        if isinstance(salida, completitud.Resultado):
            return _texto({"propiedad": salida.propiedad, "idempotente": salida.idempotente,
                           "modificadas": list(salida.modificadas)})
        return _texto(salida)

    @app.post("/v1/propiedades/{propiedad_id}/compra", dependencies=dep)
    def registrar_compra(propiedad_id: uuid.UUID, c: RegistrarCompra):
        peticion = c.model_dump()
        return _comando("compra", c.intencion_id, lambda s: compra.registrar_compra(
            s, propiedad_id=propiedad_id, peticion=peticion, reloj=reloj))

    @app.post("/v1/propiedades/{propiedad_id}/compra/gastos", dependencies=dep)
    def gasto_de_la_compra(propiedad_id: uuid.UUID, c: GastoCompraPosterior):
        peticion = c.model_dump()
        return _comando("compra03", c.intencion_id, lambda s: compra.gasto_posterior(
            s, propiedad_id=propiedad_id, peticion=peticion, reloj=reloj))

    @app.post("/v1/propiedades/{propiedad_id}/completitud", dependencies=dep)
    def declarar_completitud(propiedad_id: uuid.UUID, c: DeclararCompletitud):
        if not habilitacion.consumidores_0352_habilitados():          # O10.29: ruta inaccesible
            return rechazo(habilitacion.FUNCION_NO_HABILITADA)
        return _comando("completitud", c.intencion_id, lambda s: completitud.declarar(
            s, propiedad_id=propiedad_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            ambito=c.ambito, completo=c.completo, fecha_corte=c.fecha_corte, huella_vista=c.huella_conjunto_vista,
            reloj=reloj))

    @app.get("/v1/propiedades/{propiedad_id}/coste", dependencies=dep)
    def coste_propiedad(propiedad_id: uuid.UUID, a_fecha: dt.date | None = None):
        salida = unidad.ejecutar(contexto(), lambda s: coste.leer(s, propiedad_id, a_fecha or hoy_owner(s, reloj)),
                                 nombre="F06-01 B2 L-COSTE")
        if salida is None:
            return rechazo("AGREGADO_NO_ENCONTRADO")
        return {"coste": salida}

    @app.get("/v1/propiedades/{propiedad_id}/titularidad-en-fecha", dependencies=dep)
    def titularidad_en_fecha(propiedad_id: uuid.UUID, fecha: dt.date | None = None):
        def leer(s):
            if repo.leer(s, propiedad_id) is None:
                return None
            dia = fecha or hoy_owner(s, reloj)
            return dia, m2.titularidad_en_fecha(s, propiedad_id, dia)
        salida = unidad.ejecutar(contexto(), leer, nombre="F06-01 B2 titularidad en fecha")
        if salida is None:
            return rechazo("AGREGADO_NO_ENCONTRADO")
        return _texto({"fecha": salida[0], "partes": salida[1]})
