# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas_categoria.py
# Ruta: backend/app/comun/rutas_categoria.py
# Descripcion: Catalogo de categorias del owner con su ruta legible
#   (F05-05 K2 §1.2/§1.3/§1.5; F05 §49.4 A1, A2, A7). Solo lectura, sin
#   locks, gapto_runtime con RLS del tenant. Lo usan las senales, las
#   afinidades y la Actividad para mostrar «Padre › Hija» sin persistir nada.
#   - `ruta`: nombres desde la raiz hasta el nodo, en orden; con un ciclo
#     imposible (la base lo impide: trigger aciclico) se corta al detectarlo.
#   - `clave_orden`: (nombre normalizado C06, id) para desempates
#     deterministas (F05 §49.5 R6).
# Version: 0.1.0 (F05-05 K2 §1.2)
# Version: 0.2.0 (F05-06 K-7, F05 §51.8): el catalogo trae tambien `icon_key`
#   (aditivo, misma lectura) para el icono de la categoria en la Actividad.
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.categorias.normalizacion import normalizar
from app.core.unidad_trabajo import SesionMotor

SEPARADOR_RUTA = " › "


def catalogo(sesion: SesionMotor) -> dict[uuid.UUID, dict[str, Any]]:
    """Todas las categorias del owner (habilitadas o no) con `ruta`."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, parent_id, nombre, ambito, enabled, icon_key FROM gapto.categorias_financieras "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
        )
        nodos = {f[0]: {"id": f[0], "parent_id": f[1], "nombre": f[2], "ambito": f[3], "enabled": f[4],
                       "icon_key": f[5]}
                 for f in cur.fetchall()}
    for nodo in nodos.values():
        nombres, vistos, actual = [], set(), nodo
        while actual is not None and actual["id"] not in vistos:
            vistos.add(actual["id"])
            nombres.append(actual["nombre"])
            actual = nodos.get(actual["parent_id"]) if actual["parent_id"] else None
        nodo["ruta"] = list(reversed(nombres))
    return nodos


def ruta_texto(nodo: dict[str, Any]) -> str:
    return SEPARADOR_RUTA.join(nodo["ruta"])


def clave_orden(nodo: dict[str, Any]) -> tuple[str, str]:
    return normalizar(nodo["nombre"]), str(nodo["id"])
