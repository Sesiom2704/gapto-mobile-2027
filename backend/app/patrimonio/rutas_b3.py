# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas_b3.py
# Ruta: backend/app/patrimonio/rutas_b3.py
# Descripcion: Rutas HTTP de B3 (API DE INTEGRACION, PENDIENTE DE CONSOLIDACION F10), registradas por
#   `create_app` con una sola llamada (las de B2 no cambian):
#     POST /v1/intenciones/gasto-propiedad                       C-MEJ-01 (ruta unica con C-GPROP-01)
#     POST /v1/propiedades/{id}/mejoras-historicas               C-MEJ-02
#     GET  /v1/propiedades/{id}/propuesta-gasto?fecha=&cuenta_id= propuesta de reparto en la fecha del hecho
#                                                                (P-H2-03; titularidad de la PROPIEDAD)
#     GET  /v1/propiedades/{id}/gastos                           lista de gastos y mejoras de la propiedad
#     GET  /v1/propiedades/{id}/gastos/{hecho_id}                L-GASTO-PROPIEDAD (intencion_correccion_id, HF-21)
#     GET  /v1/propiedades/{id}/gastos/{hecho_id}/impacto-correccion?clase_nueva=&presupuestable=
#                                                                comparacion del §III.3.5 (lo que ve el usuario)
#     POST /v1/propiedades/{id}/gastos/{hecho_id}/corregir-clase C-MEJ-03
#   Ninguna ruta expone OP-21 ni OP-03 sobre PROPIEDAD ni sobre H0/Hk (Parte IV-bis; O10.23). Una transaccion de
#   UnidadDeTrabajo por comando, con request_id = intencion_id. Rechazos con el mapa propio de B3.
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Callable, Literal

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.core.contexto import ContextoOperacion
from app.patrimonio import correccion_clase, gasto_propiedad
from app.patrimonio.completitud import Rechazo
from app.patrimonio.dto_b3 import CorregirClase, GastoPropiedad, MejoraHistorica
from app.patrimonio.rutas import RECHAZOS as RECHAZOS_B2
from app.patrimonio.rutas import _texto

#: codigo -> (status, mensaje de usuario). Hereda los de B2 y anade los de B3.
RECHAZOS: dict[str, tuple[int, str]] = {
    **RECHAZOS_B2,
    "CLASE_GASTO_PROPIEDAD_AUSENTE": (422, "Elige si es una mejora, una reparación o un gasto corriente."),
    "FECHA_FUTURA": (422, "La fecha no puede ser futura."),
    "CATEGORIA_NO_ELEGIBLE": (409, "Esa categoría no se puede usar para este gasto."),
    "CORRECCION_NATURALEZA_NO_ADMITIDA": (422, "Este gasto no admite corregir la clase."),
    "INTENCION_CORRECCION_NO_VIGENTE": (409, "El gasto ha cambiado desde que lo abriste. Vuelve a cargarlo."),
    "IMPACTO_CORRECCION_DESFASADO": (409, "Los datos han cambiado; revisa el impacto."),
    "PERIODO_CERRADO_SIN_POLITICA": (422, "Ese mes está cerrado."),
    "MOTIVO_AUSENTE": (422, "Indica el motivo de la corrección."),
}


def rechazo(codigo: str, detalle: dict | None = None) -> JSONResponse:
    status, mensaje = RECHAZOS.get(codigo, (409, "No se ha podido guardar."))
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if detalle:
        cuerpo["detalle"] = detalle
    return JSONResponse(cuerpo, status_code=status)


def registrar(app: FastAPI, *, unidad, owner: Callable[[], uuid.UUID], contexto: Callable[[], ContextoOperacion],
              autorizar, reloj) -> None:
    dep = [Depends(autorizar)]

    def _comando(nombre: str, intencion_id: uuid.UUID, operacion) -> Any:
        ctx = ContextoOperacion.de_usuario(owner(), request_id=intencion_id)
        salida = unidad.ejecutar(ctx, operacion, nombre=f"F06-01 B3 {nombre}")
        if isinstance(salida, Rechazo):
            return rechazo(salida.codigo, salida.detalle)
        return _texto(salida)

    def _lectura(nombre: str, operacion) -> Any:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F06-01 B3 {nombre}")
        if salida is None:
            return rechazo("AGREGADO_NO_ENCONTRADO")
        return _texto(salida)

    @app.post("/v1/intenciones/gasto-propiedad", dependencies=dep)
    def gasto_de_propiedad(c: GastoPropiedad):
        peticion = c.model_dump()
        return _comando("C-MEJ-01", c.intencion_id, lambda s: gasto_propiedad.registrar_gasto(
            s, peticion=peticion, reloj=reloj))

    @app.post("/v1/propiedades/{propiedad_id}/mejoras-historicas", dependencies=dep)
    def mejora_historica(propiedad_id: uuid.UUID, c: MejoraHistorica):
        peticion = c.model_dump()
        return _comando("C-MEJ-02", c.intencion_id, lambda s: gasto_propiedad.registrar_mejora_historica(
            s, propiedad_id=propiedad_id, peticion=peticion, reloj=reloj))

    @app.post("/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/corregir-clase", dependencies=dep)
    def corregir_clase(propiedad_id: uuid.UUID, hecho_id: uuid.UUID, c: CorregirClase):
        peticion = c.model_dump()
        return _comando("C-MEJ-03", c.intencion_id, lambda s: correccion_clase.corregir_naturaleza_patrimonial(
            s, propiedad_id=propiedad_id, hecho_id=hecho_id, peticion=peticion, reloj=reloj))

    @app.get("/v1/propiedades/{propiedad_id}/propuesta-gasto", dependencies=dep)
    def propuesta_gasto(propiedad_id: uuid.UUID, fecha: dt.date, cuenta_id: uuid.UUID | None = None):
        return _lectura("propuesta", lambda s: gasto_propiedad.propuesta(s, propiedad_id, fecha, cuenta_id))

    @app.get("/v1/propiedades/{propiedad_id}/gastos", dependencies=dep)
    def gastos_de_propiedad(propiedad_id: uuid.UUID):
        def leer(s):
            lista = gasto_propiedad.listar_gastos(s, propiedad_id)
            return None if lista is None else {"gastos": lista}
        return _lectura("gastos", leer)

    @app.get("/v1/propiedades/{propiedad_id}/gastos/{hecho_id}", dependencies=dep)
    def gasto_de_la_propiedad(propiedad_id: uuid.UUID, hecho_id: uuid.UUID):
        return _lectura("L-GASTO-PROPIEDAD", lambda s: gasto_propiedad.leer_gasto(s, propiedad_id, hecho_id))

    @app.get("/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/impacto-correccion", dependencies=dep)
    def impacto_correccion(propiedad_id: uuid.UUID, hecho_id: uuid.UUID,
                           clase_nueva: Literal["MEJORA", "REPARACION", "GASTO_CORRIENTE"],
                           presupuestable: bool | None = None):
        def leer(s):
            c = gasto_propiedad.impacto(s, propiedad_id, hecho_id, clase_nueva, presupuestable)
            return None if c is None else {"comparacion": c}
        return _lectura("impacto", leer)
