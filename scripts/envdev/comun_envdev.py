# ============================================================
# GAPTO MOBILE 2027
# Fichero: comun_envdev.py
# Ruta: scripts/envdev/comun_envdev.py
# Descripcion: Utilidades comunes de los scripts versionados de datos de
#   ENV-DEV (F05-03/F05-04 J2 §1.0; D-196 / F05-D006; F05-D032 D-032.5).
#   - `exigir_envdev`: el DSN debe ser EXACTAMENTE el de ENV-DEV (loopback,
#     puerto 5434, base gapto2027_dev). Cualquier otro host, puerto o base
#     (Neon, Supabase, clusters locales de test) se rechaza ANTES de conectar.
#     El DSN no lleva contrasena en el repositorio ni en la evidencia.
#   - `unidad`: UnidadDeTrabajo del backend con SET LOCAL ROLE gapto_runtime
#     (el login de ENV-DEV solo asume gapto_runtime, D-196): las escrituras
#     pasan por RLS y la auditoria por fn_registrar_auditoria.
#   - `escribir_json`: estado previo/posterior en la carpeta de evidencia.
#   Codigo de salida 3 = STOP (estado previo distinto del esperado, §6).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.0)
# ============================================================

from __future__ import annotations

import json
import pathlib
import sys
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict

RAIZ = pathlib.Path(__file__).resolve().parents[2]
for _ruta in (RAIZ / "backend", RAIZ / "scripts" / "dev"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

DSN_ENVDEV = "host=127.0.0.1 port=5434 dbname=gapto2027_dev user=app_dev"
HOSTS = {"127.0.0.1", "localhost", "::1"}
PUERTO = "5434"
BASE = "gapto2027_dev"
SALIDA_STOP = 3


class NoEsEnvdev(Exception):
    pass


def exigir_envdev(dsn: str) -> None:
    partes = conninfo_to_dict(dsn)
    if partes.get("host") not in HOSTS or str(partes.get("port")) != PUERTO or partes.get("dbname") != BASE:
        raise NoEsEnvdev(
            f"DSN rechazado: solo ENV-DEV (host loopback, puerto {PUERTO}, base {BASE}); "
            f"recibido host={partes.get('host')!r} port={partes.get('port')!r} dbname={partes.get('dbname')!r}"
        )


def unidad(dsn: str):
    from app.core.unidad_trabajo import UnidadDeTrabajo

    @contextmanager
    def _abrir():
        with psycopg.connect(dsn, connect_timeout=5) as conexion:
            yield conexion

    return UnidadDeTrabajo(_abrir, rol_runtime="gapto_runtime")


def escribir_json(carpeta: pathlib.Path, nombre: str, datos) -> pathlib.Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n",
                    encoding="utf-8")
    return ruta
