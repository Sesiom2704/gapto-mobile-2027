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
#     GET  /v1/vs01/cuentas-pago?hoy=     -> lectura estrecha VS-01
#     GET  /v1/vs01/gasto-mes?mes=        -> lectura estrecha VS-01 (candidata F08)
#     GET  /v1/salud                      -> diagnostico de desarrollo
#   Todas exigen `Authorization: Bearer <GAPTO_DEV_TOKEN>`.
#
#   Arranque: `create_app()` falla (fail-closed) si la configuracion no es de
#   desarrollo o si la base conectada no esta en la lista blanca.
#   Ejecucion: uvicorn "app.api.app:create_app_desde_entorno" --factory --host 127.0.0.1
# Version: 0.1.0
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
from fastapi import Depends, FastAPI, Query, Request
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
from app.api.dto_vs01 import (
    GastoMesVs01,
    IntencionGastoPagado,
    ListaCuentasPago,
    ResultadoGastoPagado,
)
from app.api.traductor_gasto_pagado import componer, leer_derivacion
from app.core.contexto import ContextoOperacion
from app.core.errores import ErrorMotor
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla

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
    def cuentas_pago(hoy: dt.date = Query(...)) -> dict:
        filas = unidad.ejecutar(contexto(), lambda s: lect.cuentas_pago(s, hoy), nombre="VS01 cuentas_pago")
        return {"cuentas": filas}

    @app.get("/v1/vs01/gasto-mes", response_model=GastoMesVs01, dependencies=[Depends(autorizar)])
    def gasto_mes(mes: str = Query(...)) -> dict:
        if not _MES.match(mes):
            return JSONResponse(
                {"codigo": "ENTRADA_INVALIDA", "mensaje": "Revisa los datos: mes", "reintentable": False},
                status_code=422,
            )
        return unidad.ejecutar(contexto(), lambda s: lect.gasto_mes(s, mes), nombre="VS01 gasto_mes")

    @app.post(
        "/v1/intenciones/gasto-pagado",
        response_model=ResultadoGastoPagado,
        dependencies=[Depends(autorizar)],
    )
    def gasto_pagado(intencion: IntencionGastoPagado) -> dict:
        ctx = contexto()
        deriv = unidad.ejecutar(ctx, lambda s: leer_derivacion(s, intencion), nombre="VS01 derivacion")
        datos = componer(intencion, deriv)
        op22 = HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla)
        r = op22.registrar_hecho_compuesto(ctx, datos)
        return {
            "intencion_id": intencion.intencion_id,
            "hecho_id": r.hecho_id,
            "idempotente": r.idempotente,
            "importe": str(intencion.importe.quantize(_CENT)),
            "moneda": intencion.moneda,
            "estado_atribucion": datos.efectos[0].estado_atribucion,
            "aportacion_criterio": datos.aportaciones[0].criterio_aportacion if datos.aportaciones else None,
            "aviso": "API de integracion F05-00-B, pendiente de consolidacion F10",
        }

    return app


def create_app_desde_entorno() -> FastAPI:
    """Punto de entrada uvicorn --factory. CORS solo por variable explicita."""
    import os

    origenes = tuple(o for o in os.environ.get("GAPTO_DEV_CORS_ORIGINS", "").split(",") if o)
    return create_app(origenes_cors=origenes)
