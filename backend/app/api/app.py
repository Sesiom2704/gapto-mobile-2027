# ============================================================
# GAPTO MOBILE 2027
# Fichero: app.py
# Ruta: backend/app/api/app.py
# Descripcion: Adaptador HTTP FastAPI del vertical slice VS-01.
#   API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10.
#   *** IDENTIDAD DE DESARROLLO: NO ES AUTENTICACION DE PRODUCCION (F10-01) ***
#
#   Rutas:
#     POST /v1/intenciones/gasto-pagado  -> OP-22 (unica escritura)
#     GET  /v1/vs01/cuentas-pago?fecha=   -> cuentas elegibles + propuesta de financiacion
#     GET  /v1/vs01/gasto-mes?mes=        -> lectura estrecha VS-01 (candidata F08)
#     GET  /v1/categorias                 -> arbol del owner (F05-01, S3)
#     GET  /v1/categorias/{id}/uso        -> uso historico por naturaleza (C06)
#     GET  /v1/salud                      -> diagnostico de desarrollo
#   Todas exigen `Authorization: Bearer <GAPTO_DEV_TOKEN>`.
#
#   Arranque: `create_app()` falla (fail-closed) si la configuracion no es de
#   desarrollo o si la base conectada no esta en la lista blanca.
#   Ejecucion: uvicorn "app.api.app:create_app_desde_entorno" --factory --host 127.0.0.1
#
#   v0.2.0 (F05-D003): la escritura se ejecuta en UNA transaccion del
#   adaptador (lock de cuenta -> identidad -> revalidacion -> OP-22 adscrito,
#   ejecucion_gasto_pagado.py); cuentas-pago recibe la fecha del pago.
#
#   v0.3.0 (F05-01, F05-D009): la intencion admite la dimension categorial
#   (CATEGORIA / SIN_CATEGORIA; la ausencia derivaba entonces un estado de
#   compatibilidad, retirado en v0.7.0) y la respuesta informa
#   `estado_categorial`. Lecturas del arbol de categorias.
#
#   v0.4.0 (F05-01, S4): comandos de gestion del arbol (C06), uno por ruta,
#   cada uno en una transaccion de la unidad de trabajo. Sin DELETE ni
#   escritura de icon_key.
#
#   v0.5.0 (F05-01 S6-ICONO (F05-D013)): POST /v1/categorias/{id}/icono
#   (cambiar_icono) y `icon_key` opcional en el alta. Sin DELETE; sin
#   lectura de la biblioteca de iconos (queda para el mandato de UI).
#
#   v0.6.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): POST /v1/categorias/reordenar
#   (reordenar hermanos, atomico, una transaccion de la UdT). El comando por
#   nodo POST /v1/categorias/{id}/orden (S4) se CONSERVA sin cambios; la
#   prohibicion de §26.3 (reordenar con N llamadas por nodo) rige para la UI,
#   que solo usara /reordenar (D-ORD-08).
#
#   v0.7.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03): la intencion
#   exige `categoria` (ausente o null -> 422); `estado_categorial` es siempre
#   CATEGORIA o SIN_CATEGORIA. Sin rutas nuevas.
#
#   v0.8.0 (F05-01 S7-MAG (F05-D020 D-MAG-04), commit 1): GET /v1/categorias
#   responde con ArbolCategoriasMagnitudes (dto_magnitudes.py): cada magnitud
#   asociada anade `asociacion_id`. Campo aditivo; sin rutas nuevas.
#
#   v0.9.0 (F05-01 S7-MAG (F05-D020), commit 2): rutas de magnitudes, cada
#   comando en UNA transaccion de la unidad de trabajo (magnitudes/servicio.py):
#     POST /v1/categorias/{id}/magnitudes                       asociar (EXISTENTE | NUEVA)
#     POST /v1/categorias/{id}/magnitudes/{asociacion}/obligatoria
#     POST /v1/categorias/{id}/magnitudes/{asociacion}/retirar
#     POST /v1/categorias/{id}/magnitudes/reordenar
#     POST /v1/magnitudes/{id}/renombrar | deshabilitar | rehabilitar
#     GET  /v1/magnitudes                                       catalogo del owner
#   Sin DELETE HTTP: retirar una asociacion es un POST por accion. Sin cambio
#   de unidad ni precision (R17).
# Version: 0.9.0
# ============================================================

from __future__ import annotations

import datetime as dt
import hmac
import logging
import re
import uuid
from contextlib import contextmanager
from typing import Callable, Iterator

import psycopg
from fastapi import Body, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import errores_http as eh
from app.api import lecturas_vs01 as lect
from app.api.configuracion import (
    AVISO_IDENTIDAD,
    ConfiguracionApi,
    cargar_desde_entorno,
    verificar_base_permitida,
)
from app.api.dto_categorias import (
    AltaCategoria,
    AmbitoCambio,
    CategoriaNodo,
    DesactivarCategoria,
    IconoCategoria,
    MoverCategoria,
    OrdenCategoria,
    ReactivarCategoria,
    RenombrarCategoria,
    ReordenarHermanos,
    ResultadoComandoCategoria,
    ResultadoReordenar,
    UsoCategoria,
)
from app.api.dto_magnitudes import (
    ArbolCategoriasMagnitudes,
    AsociarMagnitud,
    AsociarNueva,
    CatalogoMagnitudes,
    DeshabilitarMagnitud,
    ObligatoriaAsociacion,
    RehabilitarMagnitud,
    RenombrarMagnitud,
    ReordenarMagnitudes,
    ResultadoAsociacionesMagnitud,
    ResultadoAsociacionMagnitud,
    ResultadoComandoMagnitud,
    RetirarAsociacion,
)
from app.api.dto_vs01 import (
    GastoMesVs01,
    IntencionGastoPagado,
    ListaCuentasPago,
    ResultadoGastoPagado,
)
from app.api.ejecucion_gasto_pagado import RechazoIntegracion, registrar_gasto_pagado
from app.categorias import lecturas as lect_cat
from app.categorias import servicio as serv_cat
from app.magnitudes import lecturas as lect_mag
from app.magnitudes import servicio as serv_mag
from app.core.contexto import ContextoOperacion
from app.core.errores import ErrorMotor
from app.core.unidad_trabajo import UnidadDeTrabajo

_LOG = logging.getLogger("gapto.api.f05_00_b")
import decimal
_CENT = decimal.Decimal("0.01")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class _NoAutorizado(Exception):
    pass


def _proveedor_por_defecto(dsn: str) -> Callable[[], object]:
    @contextmanager
    def _abrir() -> Iterator[psycopg.Connection]:
        with psycopg.connect(dsn, connect_timeout=5) as conexion:
            yield conexion

    return _abrir


def create_app(
    cfg: ConfiguracionApi | None = None,
    *,
    proveedor_conexion: Callable[[], object] | None = None,
    origenes_cors: tuple[str, ...] = (),
) -> FastAPI:
    cfg = cfg or cargar_desde_entorno()
    proveedor = proveedor_conexion or _proveedor_por_defecto(cfg.dsn)

    # Fail-closed: la base real conectada debe ser de desarrollo.
    with proveedor() as conexion:
        nombre = conexion.execute("SELECT current_database()").fetchone()[0]
    verificar_base_permitida(nombre, cfg)

    unidad = UnidadDeTrabajo(proveedor, rol_runtime=cfg.rol_runtime)
    app = FastAPI(
        title="GaptoMobile 2027 — API de integracion F05-00-B",
        description=f"Pendiente de consolidacion F10. {AVISO_IDENTIDAD}.",
        version="0.1.0",
    )
    if origenes_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origenes_cors),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    def contexto() -> ContextoOperacion:
        # El owner NO procede de la peticion: es configuracion del servidor.
        return ContextoOperacion.de_usuario(cfg.owner_user_id, request_id=uuid.uuid4())

    def autorizar(request: Request) -> None:
        cabecera = request.headers.get("authorization", "")
        esperado = f"Bearer {cfg.token_desarrollo}"
        if not hmac.compare_digest(cabecera.encode(), esperado.encode()):
            raise _NoAutorizado()

    @app.exception_handler(_NoAutorizado)
    def _h_auth(_: Request, __: _NoAutorizado) -> JSONResponse:
        status, cuerpo = eh.no_autorizado()
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(ErrorMotor)
    def _h_motor(_: Request, exc: ErrorMotor) -> JSONResponse:
        _LOG.warning("error de motor", extra=exc.diagnostico_interno())
        status, cuerpo = eh.traducir_error_motor(exc.codigo)
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(psycopg.OperationalError)
    def _h_bd(_: Request, exc: psycopg.OperationalError) -> JSONResponse:
        _LOG.warning("BD no disponible: %s", type(exc).__name__)
        status, cuerpo = eh.backend_no_disponible()
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(RequestValidationError)
    def _h_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        campos = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) for e in exc.errors()})
        return JSONResponse(
            {
                "codigo": "ENTRADA_INVALIDA",
                "mensaje": "Revisa los datos: " + ", ".join(c for c in campos if c),
                "reintentable": False,
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    def _h_interno(_: Request, exc: Exception) -> JSONResponse:
        _LOG.error("error no clasificado: %s", type(exc).__name__)
        status, cuerpo = eh.interno()
        return JSONResponse(cuerpo, status_code=status)

    @app.get("/v1/salud", dependencies=[Depends(autorizar)])
    def salud() -> dict:
        return {"estado": "OK", "entorno": cfg.entorno, "aviso": AVISO_IDENTIDAD, "base": nombre}

    @app.get("/v1/vs01/cuentas-pago", response_model=ListaCuentasPago, dependencies=[Depends(autorizar)])
    def cuentas_pago(fecha: dt.date = Query(...)) -> dict:
        # `fecha` es la fecha comun de gasto y pago elegida en el formulario:
        # la propuesta de financiacion se evalua en esa fecha (§16.4).
        filas = unidad.ejecutar(contexto(), lambda s: lect.cuentas_pago(s, fecha), nombre="VS01 cuentas_pago")
        return {"cuentas": filas}

    @app.get("/v1/vs01/gasto-mes", response_model=GastoMesVs01, dependencies=[Depends(autorizar)])
    def gasto_mes(mes: str = Query(...)) -> dict:
        if not _MES.match(mes):
            return JSONResponse(
                {"codigo": "ENTRADA_INVALIDA", "mensaje": "Revisa los datos: mes", "reintentable": False},
                status_code=422,
            )
        return unidad.ejecutar(contexto(), lambda s: lect.gasto_mes(s, mes), nombre="VS01 gasto_mes")

    @app.get("/v1/categorias", response_model=ArbolCategoriasMagnitudes, dependencies=[Depends(autorizar)])
    def categorias() -> dict:
        filas = unidad.ejecutar(contexto(), lect_cat.arbol, nombre="F05-01 arbol_categorias")
        return {"categorias": filas}

    @app.get(
        "/v1/categorias/{categoria_id}/uso",
        response_model=UsoCategoria,
        dependencies=[Depends(autorizar)],
    )
    def uso_categoria(categoria_id: uuid.UUID) -> dict:
        return unidad.ejecutar(
            contexto(), lambda s: lect_cat.uso_por_naturaleza(s, categoria_id), nombre="F05-01 uso_categoria"
        )

    def _comando(nombre_op: str, operacion) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-01 {nombre_op}")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_categoria(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        campos = CategoriaNodo.model_fields
        return {
            "categoria": {k: v for k, v in salida.categoria.items() if k in campos},
            "idempotente": salida.idempotente,
            "modificadas": list(salida.modificadas),
        }

    _R = {"response_model": ResultadoComandoCategoria, "dependencies": [Depends(autorizar)]}

    @app.post("/v1/categorias", **_R)
    def alta_categoria(c: AltaCategoria):
        return _comando("alta", lambda s: serv_cat.alta(
            s, categoria_id=c.id, nombre=c.nombre, parent_id=c.parent_id, ambito=c.ambito,
            presupuestable_default=c.presupuestable_default, icon_key=c.icon_key))

    @app.post("/v1/categorias/{categoria_id}/renombrar", **_R)
    def renombrar_categoria(categoria_id: uuid.UUID, c: RenombrarCategoria):
        return _comando("renombrar", lambda s: serv_cat.renombrar(
            s, categoria_id=categoria_id, nombre=c.nombre, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/mover", **_R)
    def mover_categoria(categoria_id: uuid.UUID, c: MoverCategoria):
        return _comando("mover", lambda s: serv_cat.mover(
            s, categoria_id=categoria_id, parent_id=c.parent_id, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/desactivar", **_R)
    def desactivar_categoria(categoria_id: uuid.UUID, c: DesactivarCategoria):
        return _comando("desactivar", lambda s: serv_cat.desactivar(
            s, categoria_id=categoria_id, modo=c.modo, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/reactivar", **_R)
    def reactivar_categoria(categoria_id: uuid.UUID, c: ReactivarCategoria):
        return _comando("reactivar", lambda s: serv_cat.reactivar(
            s, categoria_id=categoria_id, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/orden", **_R)
    def ordenar_categoria(categoria_id: uuid.UUID, c: OrdenCategoria):
        return _comando("orden", lambda s: serv_cat.ordenar(
            s, categoria_id=categoria_id, orden=c.orden, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/ambito", **_R)
    def ambito_categoria(categoria_id: uuid.UUID, c: AmbitoCambio):
        return _comando("ambito", lambda s: serv_cat.cambiar_ambito(
            s, categoria_id=categoria_id, ambito=c.ambito, confirmacion_uso=c.confirmacion_uso,
            row_version=c.row_version))

    @app.post("/v1/categorias/reordenar", response_model=ResultadoReordenar, dependencies=[Depends(autorizar)])
    def reordenar_categorias(c: ReordenarHermanos):
        salida = unidad.ejecutar(contexto(), lambda s: serv_cat.reordenar(
            s, parent_id=c.parent_id, hermanos=[(h.id, h.row_version) for h in c.hermanos]),
            nombre="F05-01 reordenar")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_categoria(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        campos = CategoriaNodo.model_fields
        return {
            "hermanos": [{k: v for k, v in n.items() if k in campos} for n in salida.hermanos],
            "idempotente": salida.idempotente,
            "modificadas": list(salida.modificadas),
        }

    @app.post("/v1/categorias/{categoria_id}/icono", **_R)
    def icono_categoria(categoria_id: uuid.UUID, c: IconoCategoria):
        return _comando("icono", lambda s: serv_cat.cambiar_icono(
            s, categoria_id=categoria_id, icon_key=c.icon_key, row_version=c.row_version))

    # ------------------------------------------------------------ S7-MAG
    def _comando_magnitudes(nombre_op: str, operacion, convertir) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-01 {nombre_op}")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_magnitud(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {**convertir(salida), "idempotente": salida.idempotente, "modificadas": list(salida.modificadas)}

    def _asociacion(r: serv_mag.ResultadoAsociacion) -> dict:
        return {"categoria_id": r.categoria_id, "asociacion": r.asociacion, "magnitud": r.magnitud}

    def _asociaciones(r: serv_mag.ResultadoAsociaciones) -> dict:
        return {"categoria_id": r.categoria_id, "asociaciones": list(r.asociaciones)}

    def _ficha(r: serv_mag.ResultadoMagnitud) -> dict:
        return {"magnitud": r.magnitud}

    _RA = {"response_model": ResultadoAsociacionMagnitud, "dependencies": [Depends(autorizar)]}
    _RL = {"response_model": ResultadoAsociacionesMagnitud, "dependencies": [Depends(autorizar)]}
    _RM = {"response_model": ResultadoComandoMagnitud, "dependencies": [Depends(autorizar)]}

    @app.get("/v1/magnitudes", response_model=CatalogoMagnitudes, dependencies=[Depends(autorizar)])
    def magnitudes() -> dict:
        return {"magnitudes": unidad.ejecutar(contexto(), lect_mag.catalogo, nombre="F05-01 catalogo_magnitudes")}

    @app.post("/v1/categorias/{categoria_id}/magnitudes", **_RA)
    def asociar_magnitud(categoria_id: uuid.UUID, c: AsociarMagnitud = Body(...)):
        if isinstance(c, AsociarNueva):
            nueva = {"magnitud_id": c.magnitud.magnitud_id, "nombre": c.magnitud.nombre,
                     "unidad_default": c.magnitud.unidad_default,
                     "precision_decimales": c.magnitud.precision_decimales}
            op = lambda s: serv_mag.asociar(s, categoria_id=categoria_id, obligatoria=c.obligatoria,  # noqa: E731
                                            nueva=nueva)
        else:
            op = lambda s: serv_mag.asociar(s, categoria_id=categoria_id, obligatoria=c.obligatoria,  # noqa: E731
                                            magnitud_id=c.magnitud_id)
        return _comando_magnitudes("mag_asociar", op, _asociacion)

    # Ruta literal antes de la parametrizada: /reordenar no es un asociacion_id.
    @app.post("/v1/categorias/{categoria_id}/magnitudes/reordenar", **_RL)
    def reordenar_magnitudes(categoria_id: uuid.UUID, c: ReordenarMagnitudes):
        return _comando_magnitudes("mag_reordenar", lambda s: serv_mag.reordenar(
            s, categoria_id=categoria_id,
            asociaciones=[(a.asociacion_id, a.magnitud_id, a.orden, a.obligatoria) for a in c.asociaciones]),
            _asociaciones)

    @app.post("/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/obligatoria", **_RA)
    def obligatoria_magnitud(categoria_id: uuid.UUID, asociacion_id: uuid.UUID, c: ObligatoriaAsociacion):
        return _comando_magnitudes("mag_obligatoria", lambda s: serv_mag.cambiar_obligatoria(
            s, categoria_id=categoria_id, asociacion_id=asociacion_id, magnitud_id=c.magnitud_id,
            obligatoria_actual=c.obligatoria_actual, obligatoria=c.obligatoria), _asociacion)

    @app.post("/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/retirar", **_RL)
    def retirar_magnitud(categoria_id: uuid.UUID, asociacion_id: uuid.UUID, c: RetirarAsociacion):
        return _comando_magnitudes("mag_retirar", lambda s: serv_mag.retirar(
            s, categoria_id=categoria_id, asociacion_id=asociacion_id, magnitud_id=c.magnitud_id,
            obligatoria_actual=c.obligatoria_actual), _asociaciones)

    @app.post("/v1/magnitudes/{magnitud_id}/renombrar", **_RM)
    def renombrar_magnitud(magnitud_id: uuid.UUID, c: RenombrarMagnitud):
        return _comando_magnitudes("mag_renombrar", lambda s: serv_mag.renombrar(
            s, magnitud_id=magnitud_id, nombre=c.nombre, row_version=c.row_version), _ficha)

    @app.post("/v1/magnitudes/{magnitud_id}/deshabilitar", **_RM)
    def deshabilitar_magnitud(magnitud_id: uuid.UUID, c: DeshabilitarMagnitud):
        return _comando_magnitudes("mag_deshabilitar", lambda s: serv_mag.deshabilitar(
            s, magnitud_id=magnitud_id, row_version=c.row_version,
            confirmacion_impacto=c.confirmacion_impacto), _ficha)

    @app.post("/v1/magnitudes/{magnitud_id}/rehabilitar", **_RM)
    def rehabilitar_magnitud(magnitud_id: uuid.UUID, c: RehabilitarMagnitud):
        return _comando_magnitudes("mag_rehabilitar", lambda s: serv_mag.rehabilitar(
            s, magnitud_id=magnitud_id, row_version=c.row_version), _ficha)

    @app.post(
        "/v1/intenciones/gasto-pagado",
        response_model=ResultadoGastoPagado,
        dependencies=[Depends(autorizar)],
    )
    def gasto_pagado(intencion: IntencionGastoPagado) -> dict:
        salida = registrar_gasto_pagado(unidad, contexto(), intencion)
        if isinstance(salida, RechazoIntegracion):
            status, cuerpo = eh.rechazo_integracion(salida.codigo)
            return JSONResponse(cuerpo, status_code=status)
        r, datos = salida.resultado, salida.datos
        return {
            "intencion_id": intencion.intencion_id,
            "hecho_id": r.hecho_id,
            "idempotente": r.idempotente,
            "importe": str(intencion.importe.quantize(_CENT)),
            "moneda": intencion.moneda,
            "estado_atribucion": datos.efectos[0].estado_atribucion,
            "aportacion_criterio": datos.aportaciones[0].criterio_aportacion if datos.aportaciones else None,
            "financiacion": intencion.financiacion.estado,
            "estado_categorial": intencion.estado_categorial,
            "aviso": "API de integracion F05-00-B, pendiente de consolidacion F10",
        }

    return app


def create_app_desde_entorno() -> FastAPI:
    """Punto de entrada uvicorn --factory. CORS solo por variable explicita."""
    import os

    origenes = tuple(o for o in os.environ.get("GAPTO_DEV_CORS_ORIGINS", "").split(",") if o)
    return create_app(origenes_cors=origenes)
