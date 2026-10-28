# ============================================================
# GAPTO MOBILE 2027
# Fichero: g4_rlocale.py
# Ruta: scripts/dev/g4_rlocale.py
# Descripcion: Excepcion cerrada R-LOCALE de G4 (F05-D055, F05 §69.1, P-1;
#   AJ-F0507G6-02..06) y preflight de lc_messages (F05 §68.2, AJ-F0507G5-07).
#   Lo invoca g4_runner.ps1 0.4.0; tambien se usa suelto en las pruebas del
#   runner. Lista cerrada: g4_rlocale_catalogo.json (mismo directorio), con
#   los SIETE node IDs, su motivo exacto de SKIP, el lc_messages autorizado
#   en Neon y el SHA-256 de la evidencia de compatibilidad (F05-D054 paso 2).
#   Subcomandos:
#     preflight     valor efectivo de lc_messages en una conexion (SQL) y
#                   evidencia de compatibilidad presente con su SHA-256.
#                   STOP (rc 3) si no puede comprobarse o difiere.
#     sonda         plugin de pytest (-p g4_rlocale) que registra el
#                   lc_messages efectivo en CADA conexion de las suites
#                   (§68.1 req. 3); la verifica «validar-neon --sonda».
#     validar-neon  JUnit de la ventana Neon: los siete son SKIP con el motivo
#                   exacto; ningun otro SKIP; ningun FAIL, ERROR ni XFAIL.
#     validar-local JUnit local C y es_ES contra la ventana Neon: los siete
#                   PASS en ambos; ningun SKIP, FAIL, ERROR ni XFAIL; misma
#                   coleccion en las tres ejecuciones; misma identidad (SHA de
#                   producto, de tests, del runner y de los catalogos).
#   Codigos de salida: 0 conforme; 2 FAIL; 3 STOP. Nunca se llama PASS a un
#   SKIP: los recuentos PASS, FAIL, ERROR, SKIP y XFAIL van por separado.
#   Ninguna DSN se imprime ni se escribe (se toma de la variable --env).
#   Sin rutas absolutas (test_rv3_000).
# Version: 0.1.0 (F05-D055 paso 1, runner G4 0.4.0)
# ============================================================

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CATALOGO = Path(__file__).with_name("g4_rlocale_catalogo.json")
CONFORME, FAIL, STOP = 0, 2, 3


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cargar_catalogo(ruta: Path = CATALOGO) -> dict:
    cat = json.loads(ruta.read_text(encoding="utf-8"))
    casos = cat["casos"]
    if len(casos) != 7 or len(set(casos)) != 7:
        raise SystemExit(f"STOP catalogo R-LOCALE: se esperaban 7 casos distintos y hay {len(casos)}")
    return cat


def clave_junit(nodeid: str) -> str:
    """tests/api/test_x.py::caso[p] -> test_x::caso[p] (classname de JUnit con --rootdir=tests/api)."""
    fichero, caso = nodeid.split("::", 1)
    return f"{Path(fichero).stem}::{caso}"


# ------------------------------------------------------------------ JUnit
def leer_junit(rutas: list[Path]) -> dict[str, dict]:
    """Resultado por caso: PASS, FAIL, ERROR, SKIP o XFAIL, con el mensaje del SKIP."""
    casos: dict[str, dict] = {}
    duplicados = []
    for ruta in rutas:
        for tc in ET.parse(ruta).getroot().iter("testcase"):
            clave = f"{tc.get('classname', '').split('.')[-1]}::{tc.get('name')}"
            sk, fa, er = tc.find("skipped"), tc.find("failure"), tc.find("error")
            if er is not None:
                r, m = "ERROR", er.get("message", "")
            elif fa is not None:
                r, m = "FAIL", fa.get("message", "")
            elif sk is not None:
                r = "XFAIL" if sk.get("type") == "pytest.xfail" else "SKIP"
                m = sk.get("message", "")
            else:
                r, m = "PASS", ""
            if clave in casos:
                duplicados.append(clave)
            casos[clave] = {"resultado": r, "mensaje": m, "junit": ruta.name}
    if duplicados:
        casos["__duplicados__"] = {"resultado": "DUPLICADO", "mensaje": ",".join(sorted(set(duplicados))), "junit": ""}
    return casos


def recuentos(casos: dict[str, dict]) -> dict[str, int]:
    c = collections.Counter(v["resultado"] for k, v in casos.items() if not k.startswith("__"))
    return {k: c.get(k, 0) for k in ("PASS", "FAIL", "ERROR", "SKIP", "XFAIL")}


def huella_coleccion(casos: dict[str, dict]) -> str:
    claves = sorted(k for k in casos if not k.startswith("__"))
    return hashlib.sha256("\n".join(claves).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ comprobaciones
def comprobar_neon(casos: dict[str, dict], cat: dict) -> list[str]:
    errores = []
    if "__duplicados__" in casos:
        errores.append(f"identificadores duplicados: {casos['__duplicados__']['mensaje']}")
    autorizados = {clave_junit(n) for n in cat["casos"]}
    for n in cat["casos"]:
        k = clave_junit(n)
        v = casos.get(k)
        if v is None:
            errores.append(f"caso R-LOCALE ausente: {n}")
        elif v["resultado"] != "SKIP":
            errores.append(f"caso R-LOCALE no es SKIP en Neon ({v['resultado']}): {n}")
        elif v["mensaje"] != cat["motivo_skip"]:
            errores.append(f"motivo de SKIP distinto en {n}: {v['mensaje']!r}")
    for k, v in sorted(casos.items()):
        if k.startswith("__") or k in autorizados:
            continue
        if v["resultado"] in ("SKIP", "XFAIL", "FAIL", "ERROR"):
            errores.append(f"{v['resultado']} no contemplado: {k} ({v['mensaje'][:120]!r})")
    return errores


def comprobar_local(casos: dict[str, dict], cat: dict, etiqueta: str) -> list[str]:
    errores = []
    if "__duplicados__" in casos:
        errores.append(f"{etiqueta}: identificadores duplicados: {casos['__duplicados__']['mensaje']}")
    for n in cat["casos"]:
        v = casos.get(clave_junit(n))
        if v is None:
            errores.append(f"{etiqueta}: caso R-LOCALE ausente: {n}")
        elif v["resultado"] != "PASS":
            errores.append(f"{etiqueta}: caso R-LOCALE no es PASS ({v['resultado']}): {n}")
    autorizados = {clave_junit(n) for n in cat["casos"]}
    for k, v in sorted(casos.items()):
        if not k.startswith("__") and v["resultado"] != "PASS" and k not in autorizados:
            errores.append(f"{etiqueta}: {v['resultado']} no contemplado: {k}")
    return errores


def leer_identidad(ruta: Path) -> dict[str, str]:
    """identidad.txt del runner: clave=valor (head, tests, runner, rlocale, catalogo_rlocale, catalogos)."""
    if not ruta.exists():
        return {}
    return dict(l.split("=", 1) for l in ruta.read_text(encoding="utf-8-sig").splitlines() if "=" in l)


CLAVES_IDENTIDAD = ("head", "tests", "runner", "rlocale", "catalogo_rlocale", "catalogos")


def comprobar_identidad(neon: dict, local: dict) -> list[str]:
    errores = []
    for k in CLAVES_IDENTIDAD:
        if not neon.get(k) or not local.get(k):
            errores.append(f"identidad incompleta: falta {k}")
        elif neon[k] != local[k]:
            errores.append(f"identidad distinta entre ventanas en {k}: neon={neon[k][:12]} local={local[k][:12]}")
    return errores


# ------------------------------------------------------------------ informe
def escribir(salida: Path, titulo: str, lineas: list[str], errores: list[str], rc: int) -> int:
    veredicto = {CONFORME: "CONFORME", FAIL: "FAIL", STOP: "STOP"}[rc]
    texto = [f"{titulo}: {veredicto}"] + lineas + [f"  ERROR {e}" for e in errores]
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("a", encoding="utf-8") as f:
        f.write("\n".join(texto) + "\n")
    print("\n".join(texto))
    return rc


def cmd_preflight(a) -> int:
    cat = cargar_catalogo(Path(a.catalogo))
    autorizado = a.ensayo_lc or cat["lc_messages_autorizado_neon"]
    errores, lineas = [], [f"  lc_messages autorizado: {autorizado}" + (" (ENSAYO local: no certifica proveedor)" if a.ensayo_lc else "")]
    # Evidencia de compatibilidad (F05 §68.1 req. 2): presente y con el SHA-256 congelado.
    for clave, e in cat["compatibilidad"].items():
        p = Path(a.compatibilidad) / e["fichero"]
        if not p.exists():
            errores.append(f"falta la evidencia de compatibilidad {e['fichero']}")
        elif sha256(p) != e["sha256"]:
            errores.append(f"evidencia de compatibilidad {e['fichero']} con SHA distinto ({sha256(p)})")
        else:
            lineas.append(f"  compatibilidad {clave}: {e['fichero']} {e['sha256']}")
    # Valor efectivo por SQL en una conexion del destino (sin PGOPTIONS: las suites no fijan el idioma).
    if os.environ.get("PGOPTIONS"):
        errores.append("PGOPTIONS definido: las suites no deben fijar lc_messages")
    try:
        import psycopg
        dsn = os.environ[a.env]
        with psycopg.connect(dsn, connect_timeout=30, autocommit=True) as c:
            lc = c.execute("SHOW lc_messages").fetchone()[0]
            col, ctype = c.execute("SELECT datcollate, datctype FROM pg_database WHERE datname = current_database()").fetchone()
        lineas += [f"  lc_messages efectivo: {lc}", f"  LC_COLLATE={col} LC_CTYPE={ctype} (no se confunden con lc_messages)"]
        if lc != autorizado:
            errores.append(f"lc_messages efectivo {lc!r} distinto del autorizado {autorizado!r}")
    except Exception as e:  # noqa: BLE001 - solo la clase: nunca la DSN
        errores.append(f"no se puede comprobar lc_messages (clase={type(e).__name__})")
    return escribir(Path(a.salida), "PREFLIGHT lc_messages", lineas, errores, STOP if errores else CONFORME)


def comprobar_sonda(ruta: Path, autorizado: str) -> list[str]:
    if not ruta.exists():
        return [f"no existe la sonda {ruta.name}: lc_messages de las suites no comprobado"]
    s = json.loads(ruta.read_text(encoding="utf-8"))
    errores = [f"error de la sonda: {e}" for e in s.get("errores_sonda", [])]
    por_lc = s.get("conexiones_por_lc_messages", {})
    if not por_lc:
        errores.append("la sonda no registro ninguna conexion")
    otros = {k: v for k, v in por_lc.items() if k != autorizado}
    if otros:
        errores.append(f"conexiones de las suites con lc_messages distinto del autorizado: {otros}")
    return errores


def cmd_validar_neon(a) -> int:
    cat = cargar_catalogo(Path(a.catalogo))
    casos = leer_junit([Path(j) for j in a.junit])
    errores = comprobar_neon(casos, cat)
    r = recuentos(casos)
    lineas = [f"  recuentos: {json.dumps(r)}", f"  coleccion: {len(casos)} casos sha256={huella_coleccion(casos)}",
              f"  matriz: {cat['matriz']}",
              f"  literal: Neon {r['PASS']} PASS y {r['SKIP']} SKIP contractuales (un SKIP nunca es PASS)"]
    rc = FAIL if errores else CONFORME
    if a.sonda:
        es = comprobar_sonda(Path(a.sonda), a.ensayo_lc or cat["lc_messages_autorizado_neon"])
        if es:
            errores += es; rc = STOP
        else:
            lineas.append("  sonda: todas las conexiones de las suites con el lc_messages autorizado")
    if a.coleccion:
        Path(a.coleccion).write_text("\n".join(sorted(k for k in casos if not k.startswith("__"))) + "\n", encoding="utf-8")
    return escribir(Path(a.salida), "VALIDACION NEON R-LOCALE", lineas, errores, rc)


def cmd_validar_local(a) -> int:
    cat = cargar_catalogo(Path(a.catalogo))
    neon = leer_junit([Path(j) for j in a.neon])
    loc = {"local C": leer_junit([Path(j) for j in a.c]), "local es_ES": leer_junit([Path(j) for j in a.es])}
    lineas = [f"  Neon: {json.dumps(recuentos(neon))} coleccion sha256={huella_coleccion(neon)}"]
    if a.ensayo:
        errores = []
        lineas.append("  Neon R-LOCALE: NO EJECUTADO (ENSAYO: la hija local puede fijar lc_messages)")
    else:
        errores = comprobar_neon(neon, cat)
    col_neon = {k for k in neon if not k.startswith("__")}
    for etq, casos in loc.items():
        errores += comprobar_local(casos, cat, etq)
        lineas.append(f"  {etq}: {json.dumps(recuentos(casos))} coleccion sha256={huella_coleccion(casos)}")
        col = {k for k in casos if not k.startswith("__")}
        if col != col_neon:
            faltan, sobran = sorted(col_neon - col), sorted(col - col_neon)
            errores.append(f"coleccion modificada en {etq}: {len(faltan)} casos de Neon ausentes {faltan[:5]}, "
                           f"{len(sobran)} casos nuevos {sobran[:5]}")
    errores += comprobar_identidad(leer_identidad(Path(a.identidad_neon)), leer_identidad(Path(a.identidad_local)))
    lineas.append(f"  matriz: {cat['matriz']}")
    return escribir(Path(a.salida), "VALIDACION LOCAL R-LOCALE", lineas, errores, FAIL if errores else CONFORME)


# ------------------------------------------------------------------ sonda (plugin de pytest: -p g4_rlocale)
_cuenta: collections.Counter = collections.Counter()
_errores_sonda: list[str] = []


def pytest_configure(config):  # pragma: no cover - solo bajo pytest con -p g4_rlocale
    if not os.environ.get("G4_SONDA_LC_SALIDA"):
        return
    import psycopg
    from psycopg.rows import tuple_row
    original = psycopg.Connection.connect.__func__

    @classmethod
    def conectar(cls, *a, **k):
        conn = original(cls, *a, **k)
        try:
            v = conn.cursor(row_factory=tuple_row).execute("SHOW lc_messages").fetchone()[0]
            if not conn.autocommit:
                conn.rollback()
            _cuenta[v] += 1
        except Exception as e:  # noqa: BLE001
            _errores_sonda.append(type(e).__name__)
        return conn

    psycopg.Connection.connect = conectar
    psycopg.connect = psycopg.Connection.connect


def pytest_unconfigure(config):  # pragma: no cover
    salida = os.environ.get("G4_SONDA_LC_SALIDA")
    if salida:
        Path(salida).write_text(json.dumps({"conexiones_por_lc_messages": dict(_cuenta), "errores_sonda": _errores_sonda,
                                            "PGOPTIONS": os.environ.get("PGOPTIONS")}, indent=1), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalogo", default=str(CATALOGO))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("preflight")
    s.add_argument("--env", required=True); s.add_argument("--compatibilidad", required=True)
    s.add_argument("--salida", required=True); s.add_argument("--ensayo-lc", default="")
    s = sub.add_parser("validar-neon")
    s.add_argument("--junit", action="append", required=True); s.add_argument("--salida", required=True)
    s.add_argument("--sonda", default=""); s.add_argument("--ensayo-lc", default=""); s.add_argument("--coleccion", default="")
    s = sub.add_parser("validar-local")
    s.add_argument("--neon", action="append", required=True); s.add_argument("--c", action="append", required=True)
    s.add_argument("--es", action="append", required=True); s.add_argument("--identidad-neon", required=True)
    s.add_argument("--identidad-local", required=True); s.add_argument("--salida", required=True)
    s.add_argument("--ensayo", action="store_true")
    a = p.parse_args(argv)
    return {"preflight": cmd_preflight, "validar-neon": cmd_validar_neon, "validar-local": cmd_validar_local}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
