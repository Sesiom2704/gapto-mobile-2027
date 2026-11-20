# ============================================================
# GAPTO MOBILE 2027
# Fichero: base_limpia_mutante.py
# Ruta: scripts/dev/base_limpia_mutante.py
# Descripcion: MANT N1 arneses, AJ-03 del 19-11 (dictamen de cierre del bloque 2, 969db763…; reevaluacion AJ-REE-03;
#   decision 3 del 2026-11-20; enmienda 01 del mandato MANT RT + arneses): base limpia e independencia por mutante, y
#   clasificacion de la muerte. Decorador `por_llamada` para la funcion `correr` de los arneses scripts/dev/mutantes_*.py:
#   - Base limpia: en CADA llamada (el preflight y cada mutante, y cada repeticion) crea una base NUEVA con
#     `CREATE DATABASE … TEMPLATE <plantilla>`, donde la plantilla es la base de GAPTO_TEST_DATABASE_URL (desechable, con
#     la cadena vigente); apunta GAPTO_TEST_DATABASE_URL a la base nueva solo durante la llamada (los subprocesos pytest
#     la heredan) y la elimina al terminar (DROP … WITH (FORCE)). Ningun mutante ve filas, secuencias ni estadisticas
#     dejadas por otro; la plantilla nunca se conecta desde los discriminantes. Sin GAPTO_TEST_DATABASE_URL (arneses o
#     llamadas solo de Jest) no hay base: cada mutante corre en un proceso Jest nuevo sobre los ficheros restaurados por
#     SHA (aislamiento equivalente del cliente).
#   - Fail-closed: solo bases en loopback (127.0.0.1, localhost, ::1); otro host -> STOP (nunca Neon ni Supabase).
#     Nombres «<plantilla>__ml_<pid>_<n>», que `limpiar_restos` elimina si una ejecucion se corto.
#   - Clasificacion de la muerte (requisitos del cierre B3 v1.1, punto 4): durante cada llamada se capturan las salidas de
#     pytest y Jest que lanza el arnes y se clasifica la llamada en VERDE, MUERTE_POR_DISCRIMINANTE (fallo de asercion en
#     un nodo declarado del mutante), MUERTE_POR_DISCRIMINANTE_EN_FIXTURE (ERROR en la fixture de un nodo declarado,
#     sin patron de infraestructura: se revisa una a una) o FALLO_INFRA_PREPARACION_EJECUCION (error de
#     coleccion,
#     OperationalError/BD_NO_DISPONIBLE/error 487, SyntaxError/ImportError, «Test suite failed to run», nada ejecutado,
#     fallo fuera de los nodos declarados). Una linea JSON por llamada en el fichero de GAPTO_MUTANTES_CLASIFICACION (si
#     esta definido). El arnes no cambia su veredicto: la clasificacion se cruza despues con sus veredictos (orden de
#     llamadas: preflight(s) y luego un mutante por llamada).
#   No cambia oraculos, discriminantes, mutaciones ni la restauracion por SHA de cada arnes.
# Version: 0.1.0 (F06 T3 · MANT N1 arneses, AJ-03 del 19-11): base limpia por llamada.
# Version: 0.2.0 (F06 T3 · MANT N1 arneses, enmienda 01 §3; requisitos B3 v1.1 punto 4): clasificacion de la muerte.
# ============================================================
from __future__ import annotations

import contextlib
import functools
import itertools
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

ENV = "GAPTO_TEST_DATABASE_URL"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SUFIJO = "__ml_"
_contador = itertools.count(1)
_N_CALL = itertools.count(0)
#: registro de las bases creadas en esta ejecucion (para la evidencia): (nombre, plantilla)
CREADAS: list[tuple[str, str]] = []

INFRA = re.compile(r"OperationalError|BD_NO_DISPONIBLE|could not reserve shared memory|could not connect|connection refused|"
                   r"server closed the connection|too many clients|INTERNALERROR|ERROR collecting|ModuleNotFoundError|"
                   r"ImportError|SyntaxError|IndentationError|Test suite failed to run|Cannot find module|no tests ran|"
                   r"PermissionError|MemoryError", re.I)
_NODO_FALLIDO = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - (.*))?$", re.M)
_JEST_FALLIDO = re.compile(r"^\s*● (.+)$", re.M)


def _partes(url: str):
    p = urlsplit(url)
    if p.scheme not in ("postgresql", "postgres"):
        sys.exit(f"STOP base limpia: {ENV} debe ir en formato URL postgresql://… (es {p.scheme or 'clave=valor'})")
    if (p.hostname or "") not in LOOPBACK:
        sys.exit(f"STOP base limpia: la plantilla no esta en loopback ({p.hostname}); solo bases locales desechables")
    db = p.path.lstrip("/")
    if not db or SUFIJO in db:
        sys.exit(f"STOP base limpia: nombre de plantilla no valido ({db!r})")
    return p, db


def _admin(p):
    import psycopg
    return psycopg.connect(urlunsplit(p._replace(path="/postgres", query="")), autocommit=True)


def _ident(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


@contextlib.contextmanager
def base_nueva(url: str):
    """Crea <plantilla>__ml_<pid>_<n> desde la plantilla, la entrega como URL y la elimina al salir."""
    p, plantilla = _partes(url)
    nombre = f"{plantilla[:40]}{SUFIJO}{os.getpid()}_{next(_contador)}"
    with _admin(p) as c:
        c.execute(f"CREATE DATABASE {_ident(nombre)} TEMPLATE {_ident(plantilla)}")
    CREADAS.append((nombre, plantilla))
    try:
        yield urlunsplit(p._replace(path="/" + nombre))
    finally:
        with _admin(p) as c:
            c.execute(f"DROP DATABASE IF EXISTS {_ident(nombre)} WITH (FORCE)")


def _texto(x) -> str:
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, (bytes, bytearray)) else str(x)


def _es_declarado(nodo: str, declarados: list[str]) -> bool:
    n = nodo.replace("\\", "/")
    base = n.split("[")[0]
    for d in declarados:
        d = d.replace("\\", "/")
        if n == d or base == d or n.startswith(d + "::") or n.startswith(d + "[") or d.endswith(base) or \
                (("::" not in d) and n.startswith(d)):
            return True
    return False


def clasificar(tests: list[str], ejecuciones: list[dict]) -> dict:
    """VERDE | MUERTE_POR_DISCRIMINANTE | FALLO_INFRA_PREPARACION_EJECUCION, con la causa."""
    fallos = [e for e in ejecuciones if e["rc"] != 0]
    if isinstance(tests, str):          # arneses por suite (mutantes_vs01): toda la suite es el discriminante
        tests = []
    if not ejecuciones:
        return {"clase": "FALLO_INFRA_PREPARACION_EJECUCION", "causa": "ningun subproceso pytest/jest"}
    if not fallos:
        return {"clase": "VERDE", "causa": None}
    declarados = [t.split("jest:", 1)[-1] for t in tests]
    causas = []
    en_fixture = False
    for e in fallos:
        salida = e["salida"]
        m = INFRA.search(salida)
        if m:
            return {"clase": "FALLO_INFRA_PREPARACION_EJECUCION", "causa": m.group(0), "cmd": e["cmd"][:200]}
        if e["tipo"] == "pytest":
            nodos = _NODO_FALLIDO.findall(salida)
            if not nodos:
                return {"clase": "FALLO_INFRA_PREPARACION_EJECUCION", "causa": f"pytest rc={e['rc']} sin nodo FAILED",
                        "cmd": e["cmd"][:200]}
            for tipo, nodo, msg in nodos:
                if declarados and not _es_declarado(nodo, declarados):
                    return {"clase": "FALLO_INFRA_PREPARACION_EJECUCION",
                            "causa": f"{tipo} fuera de lo previsto: {nodo} {msg or ''}"[:300]}
                if tipo == "ERROR":
                    en_fixture = True
                causas.append(f"{tipo} {nodo} - {msg or ''}"[:240])
        else:
            fallidos = _JEST_FALLIDO.findall(salida)
            if not fallidos:
                return {"clase": "FALLO_INFRA_PREPARACION_EJECUCION", "causa": f"jest rc={e['rc']} sin test fallido",
                        "cmd": e["cmd"][:200]}
            causas += [x[:240] for x in fallidos[:3]]
    # un ERROR (no FAILED) en un nodo DECLARADO sin patron de infraestructura: el discriminante cae en su fixture por el
    # codigo mutado (precedente: scripts/mutantes/f06_01_b2.py 0.1.1, M-CO-09); clase propia para revisarla una a una
    return {"clase": "MUERTE_POR_DISCRIMINANTE_EN_FIXTURE" if en_fixture else "MUERTE_POR_DISCRIMINANTE", "causa": causas[:4]}


@contextlib.contextmanager
def _capturar(ejecuciones: list[dict]):
    original = subprocess.run

    def run(cmd, *a, **kw):
        r = original(cmd, *a, **kw)
        txt = " ".join(map(str, cmd)) if isinstance(cmd, (list, tuple)) else str(cmd)
        tipo = "jest" if "jest" in txt else ("pytest" if "pytest" in txt else None)
        if tipo:
            ejecuciones.append({"tipo": tipo, "cmd": txt, "rc": r.returncode,
                                "salida": _texto(getattr(r, "stdout", None)) + "\n" + _texto(getattr(r, "stderr", None))})
        return r
    subprocess.run = run
    try:
        yield
    finally:
        subprocess.run = original


def _anotar(tests, resultado, base, ejecuciones) -> None:
    ruta = os.environ.get("GAPTO_MUTANTES_CLASIFICACION")
    if not ruta:
        return
    rc = resultado if isinstance(resultado, int) else (resultado[0] if isinstance(resultado, tuple) else None)
    tl = [tests] if isinstance(tests, str) else list(tests)
    fila = {"llamada": next(_N_CALL), "base": base, "tests": tl, "rc_arnes": rc,
            **clasificar(tests if isinstance(tests, str) else tl, ejecuciones),
            "rc_subprocesos": [e["rc"] for e in ejecuciones]}
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def por_llamada(correr):
    """Decorador: cada llamada a `correr` usa una base nueva clonada de la plantilla de GAPTO_TEST_DATABASE_URL (si esta
    definida) y su resultado se clasifica (GAPTO_MUTANTES_CLASIFICACION)."""
    @functools.wraps(correr)
    def envoltura(*a, **kw):
        # los nodos discriminantes son el primer argumento si existe (lista/tupla de nodos o nombre de suite); sin
        # argumentos (arneses con una suite fija) cualquier fallo de la suite cuenta como discriminante
        tests = a[0] if a and isinstance(a[0], (list, tuple, str)) else []
        url = os.environ.get(ENV)
        ejecuciones: list[dict] = []
        if not url:
            with _capturar(ejecuciones):
                r = correr(*a, **kw)
            _anotar(tests, r, None, ejecuciones)
            return r
        with base_nueva(url) as nueva:
            os.environ[ENV] = nueva
            try:
                with _capturar(ejecuciones):
                    r = correr(*a, **kw)
            finally:
                os.environ[ENV] = url
        _anotar(tests, r, nueva.rsplit("/", 1)[-1], ejecuciones)
        return r
    return envoltura


def por_llamada_base(indice: int):
    """Variante para arneses cuya `correr` recibe la base como argumento posicional (`indice`), no por el entorno
    (mutantes_mant_pre_gate_t187.py): ese argumento, si es una URL en loopback, es la plantilla de una base nueva."""
    def deco(correr):
        @functools.wraps(correr)
        def envoltura(*a, **kw):
            a = list(a)
            url = a[indice] if len(a) > indice else None
            ejecuciones: list[dict] = []
            if not url or not str(url).startswith(("postgresql://", "postgres://")):
                with _capturar(ejecuciones):
                    r = correr(*a, **kw)
                _anotar(a[0], r, None, ejecuciones)
                return r
            with base_nueva(url) as nueva:
                a[indice] = nueva
                with _capturar(ejecuciones):
                    r = correr(*a, **kw)
            _anotar(a[0], r, nueva.rsplit("/", 1)[-1], ejecuciones)
            return r
        return envoltura
    return deco


def limpiar_restos(url: str | None = None) -> list[str]:
    """Elimina las bases <plantilla>__ml_* que hubiera dejado una ejecucion cortada. Devuelve sus nombres."""
    url = url or os.environ.get(ENV)
    if not url:
        return []
    p, plantilla = _partes(url)
    with _admin(p) as c:
        restos = [r[0] for r in c.execute("SELECT datname FROM pg_database WHERE datname LIKE %s",
                                          (plantilla[:40].replace("_", r"\_") + r"\_\_ml\_%",)).fetchall()]
        for r in restos:
            c.execute(f"DROP DATABASE IF EXISTS {_ident(r)} WITH (FORCE)")
    return restos
