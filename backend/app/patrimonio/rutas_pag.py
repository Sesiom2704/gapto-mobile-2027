# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas_pag.py
# Ruta: backend/app/patrimonio/rutas_pag.py
# Descripcion: T2-F06 PAG · rutas HTTP de lectura nuevas de F06 (API DE INTEGRACION, PENDIENTE DE CONSOLIDACION
#   F10), registradas por `create_app` con una sola llamada; ninguna ruta existente cambia:
#     GET /v1/patrimonio/invertido-mes?fecha=                       «Invertido en viviendas este mes» (Q-VP-02)
#     GET /v1/cuentas/{cuenta_id}/movimientos?pagina=&limite=       L-MOV-CUENTA (L-09), sin punteo
#   Solo lectura (GET): ninguna expone OP-21 ni OP-03 ni escribe. Una transaccion de UnidadDeTrabajo por lectura,
#   como gapto_runtime con RLS. Una cuenta ajena o inexistente -> 404 AGREGADO_NO_ENCONTRADO (sin eco del id).
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Callable

from fastapi import Depends, FastAPI, Query

from app.core.contexto import ContextoOperacion
from app.patrimonio import lecturas_pag
from app.patrimonio.rutas import _texto
from app.patrimonio.rutas_b3 import rechazo


def registrar(app: FastAPI, *, unidad, contexto: Callable[[], ContextoOperacion], autorizar) -> None:
    dep = [Depends(autorizar)]

    def _lectura(nombre: str, operacion) -> Any:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F06 PAG {nombre}")
        if salida is None:
            return rechazo("AGREGADO_NO_ENCONTRADO")
        return _texto(salida)

    @app.get("/v1/patrimonio/invertido-mes", dependencies=dep)
    def invertido_en_viviendas_mes(fecha: dt.date):
        return _lectura("invertido-mes", lambda s: lecturas_pag.invertido_mes(s, fecha))

    @app.get("/v1/cuentas/{cuenta_id}/movimientos", dependencies=dep)
    def movimientos_de_la_cuenta(cuenta_id: uuid.UUID, pagina: int = Query(default=0, ge=0, le=100000),
                                 limite: int = Query(default=50, ge=1, le=lecturas_pag.LIMITE_MAXIMO)):
        return _lectura("L-MOV-CUENTA", lambda s: lecturas_pag.movimientos_cuenta(
            s, cuenta_id, pagina=pagina, limite=limite))
