# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_mant_pre_gate_t187.py
# Ruta: scripts/dev/mutantes_mant_pre_gate_t187.py
# Descripcion: Arnes de mutacion de MANT-PRE-GATE para test_187 caso 9
#   (DEU-T187-LATENCIA, AJ-05) y test_206 (DEU-T206-LOOPBACK, AJ-06) (F05-D050
#   §64.3; «un mutante por guarda nueva o modificada»). Integra y SUSTITUYE a los
#   arneses historicos fuera del repo (HUECO-05)
#     C:/DEV/evidencia_mant_k5/mutantes_k5.py        (K5-A, K5-B)
#     C:/DEV/evidencia_mant_k5_aj/mutantes_k5_aj.py  (K5-A, K5-B, K5-C)
#   adaptados al oraculo fijado del caso 9 (servidor por EXPLAIN ANALYZE +
#   aplicacion; guarda del numero de sentencias; 9b diagnostica):
#     T187-M1  consulta lenta (pg_sleep en el SQL de la busqueda)  -> 9a falla
#     T187-M1b logica de aplicacion lenta (antes K5-A)             -> 9a falla
#     T187-M2  sentencia adicional en la busqueda                  -> guarda de sentencias falla
#     T187-M3  cambio de via de conexion (antes K5-C)              -> guarda de via falla
#     T187-C1  CONTROL: apertura de conexion lenta (antes K5-B)    -> 9a y 9b pasan
#              (EQUIVALENTE por diseno: la magnitud de 9a excluye la apertura)
#     T206-M1  skipif contextual anulado (destino no loopback)     -> la siembra deja de omitirse
#     T206-M2  skipif contextual siempre activo (destino loopback) -> la siembra deja de ejecutarse
#   Motor (D-192, WM 12C.2): sustitucion de texto exacto (UNA ocurrencia) desde
#   el repositorio, sin sustituciones en memoria; journal durable ANTES de tocar
#   el primer byte (si al arrancar hay uno pendiente: restaura, verifica SHA-256
#   y aborta); preflight con los resultados de referencia declarados; resultado
#   por nodo leido del junit XML; tras cada mutante se restaura y se verifica la
#   identidad byte a byte; veredicto escrito a disco en cuanto se conoce.
#   Veredicto: MUERTO (todos los nodos objetivo cambian respecto del
#   preflight) | EQUIVALENTE (control declarado sin cambios) | VIVO |
#   NO_CLASIFICABLE.
#   Uso: GAPTO_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:<puerto>/<base desechable>
#        python scripts/dev/mutantes_mant_pre_gate_t187.py [--solo ID,ID] [--salida fichero]
#        [--evidencia carpeta]   (sin --evidencia: carpeta temporal, nunca el arbol)
#   El destino de no loopback de T206 es SIMULADO (`.invalid`, RFC 6761): nunca
#   resuelve. No ejecutar en paralelo con otro arnes ni con la suite sobre el
#   mismo arbol.
# Version: 0.1.0 (F05-07/GATE adenda 2, MANT-PRE-GATE test_187/test_206; F05-D050 §64.3)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from psycopg import conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_mant_pre_gate_t187.journal.json"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
NO_LOOPBACK_SIMULADO = "postgresql://u@db.gapto.invalid:5432/ct_simulada"

LEC = "backend/app/terceros/lecturas.py"
APP = "backend/app/api/app.py"
T206F = "tests/api/test_206_f05_06_m5_siembra.py"
T187 = "tests/api/test_187_f05_05_busqueda.py::"
T206 = T206F + "::"
N9A = T187 + "test_caso9a_busqueda_con_tres_mil_terceros_por_debajo_de_50_ms"
NSENT = T187 + "test_caso9a_guarda_numero_de_sentencias"
N9B = T187 + "test_caso9b_peticion_http_diagnostica"
NVIA = T187 + "test_caso9b_guarda_via_de_conexion"
NS1 = T206 + "test_siembra_idempotente_y_manifiesto"
NS2 = T206 + "test_siembra_entre_dias_juego_nuevo_sin_tocar_el_anterior"

#: resultado de referencia por entorno (lo exige el preflight)
REFERENCIA = {
    "loopback": {N9A: "passed", NSENT: "passed", N9B: "passed", NVIA: "passed", NS1: "passed", NS2: "passed"},
    "no_loopback": {NS1: "skipped", NS2: "skipped"},
}

_BUSQ = "        cur.execute(_SELECT + _FILTRO_BUSQUEDA, (patron, patron))\n"
_SKIP = "solo_loopback = pytest.mark.skipif(_MOTIVO is not None, "

#: (id, descripcion, [(fichero, texto, sustituto)], entorno, nodos objetivo, equivalencia o None)
MUTANTES = [
    ("T187-M1", "consulta lenta: pg_sleep(0.06) en el predicado de la busqueda (guarda 9a)",
     [(LEC, '_FILTRO_BUSQUEDA = " AND (t.nombre ILIKE %s OR t.nombre_legal ILIKE %s)"\n',
       '_FILTRO_BUSQUEDA = " AND (t.nombre ILIKE %s OR t.nombre_legal ILIKE %s) AND (SELECT pg_sleep(0.06)) IS NOT NULL"'
       '  # MUTANTE T187-M1\n')],
     "loopback", [N9A], None),
    ("T187-M1b", "logica de aplicacion lenta: time.sleep(0.06) tras la consulta (antes K5-A; guarda 9a)",
     [(LEC, _BUSQ, _BUSQ + "        __import__('time').sleep(0.060)  # MUTANTE T187-M1b\n")],
     "loopback", [N9A], None),
    ("T187-M2", "sentencia adicional en la busqueda (guarda del numero de sentencias)",
     [(LEC, _BUSQ, "        cur.execute(\"SELECT 1\")  # MUTANTE T187-M2\n" + _BUSQ)],
     "loopback", [NSENT], None),
    ("T187-M3", "cambio de via de conexion: create_app sin _proveedor_por_defecto (antes K5-C; guarda de via)",
     [(APP, "    proveedor = proveedor_conexion or _proveedor_por_defecto(cfg.dsn)\n",
       "    proveedor = proveedor_conexion or (lambda: __import__('contextlib').closing(psycopg.connect(cfg.dsn)))"
       "  # MUTANTE T187-M3\n")],
     "loopback", [NVIA], None),
    ("T187-C1", "CONTROL: apertura de conexion 60 ms mas lenta (antes K5-B)",
     [(APP, "        with psycopg.connect(dsn, connect_timeout=5) as conexion:\n",
       "        with psycopg.connect(dsn, connect_timeout=5) as conexion:\n"
       "            __import__('time').sleep(0.060)  # MUTANTE T187-C1\n")],
     "loopback", [N9A, N9B],
     "la magnitud de 9a es servidor + aplicacion y excluye la apertura de conexion por definicion (F05-D050 §64.3); "
     "9b solo afirma coherencia"),
    ("T206-M1", "skipif contextual anulado: con destino no loopback la siembra se ejecuta (guarda AJ-06)",
     [(T206F, _SKIP, "solo_loopback = pytest.mark.skipif(False, ")],
     "no_loopback", [NS1, NS2], None),
    ("T206-M2", "skipif contextual siempre activo: con destino loopback la siembra se omite (guarda AJ-06)",
     [(T206F, _SKIP, "solo_loopback = pytest.mark.skipif(True, ")],
     "loopback", [NS1, NS2], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def resultados(xml: pathlib.Path) -> dict[str, str]:
    """nodeid -> passed | failed | skipped, leido del junit XML de pytest."""
    salida = {}
    for caso in ET.parse(xml).getroot().iter("testcase"):
        modulo = caso.get("classname", "").split(".")[-1]
        nodo = f"tests/api/{modulo}.py::{caso.get('name')}"
        estado = "passed"
        for hijo in caso:
            if hijo.tag in ("failure", "error"):
                estado = "failed"
            elif hijo.tag == "skipped" and estado == "passed":
                estado = "skipped"
        salida[nodo] = estado
    return salida


def correr(nodos: list[str], entorno: str, base: str, ev: pathlib.Path, etiqueta: str) -> dict[str, str]:
    xml = ev / f"{etiqueta}.xml"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", GAPTO_K5_EVIDENCIA=str(ev / f"{etiqueta}_k5"))
    if entorno == "no_loopback":
        env["GAPTO_TEST_DATABASE_URL"] = NO_LOOPBACK_SIMULADO
        env.pop("PGHOST", None)
    else:
        env["GAPTO_TEST_DATABASE_URL"] = base
    cmd = [sys.executable, "-m", "pytest", *nodos, "-q", "-rA", "-p", "no:cacheprovider", "--rootdir=tests/api",
           f"--junitxml={xml}"]
    r = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (ev / f"{etiqueta}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    obtenidos = resultados(xml) if xml.exists() else {}
    return {n: obtenidos.get(n, "ausente") for n in nodos}


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def main() -> None:
    base = os.getenv("GAPTO_TEST_DATABASE_URL")
    if not base:
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if conninfo.conninfo_to_dict(base).get("host") not in LOOPBACK:
        sys.exit("GAPTO_TEST_DATABASE_URL debe ser loopback (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = set(sys.argv[sys.argv.index("--solo") + 1].split(",")) if "--solo" in sys.argv else None
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    ev = pathlib.Path(sys.argv[sys.argv.index("--evidencia") + 1]) if "--evidencia" in sys.argv \
        else pathlib.Path(tempfile.mkdtemp(prefix="mutantes_t187_"))
    ev.mkdir(parents=True, exist_ok=True)
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]

    # Preflight: cada entorno usado, con los resultados de referencia declarados.
    for entorno in sorted({mu[3] for mu in elegidos}):
        nodos = sorted({n for mu in elegidos if mu[3] == entorno for n in mu[4]})
        obtenido = correr(nodos, entorno, base, ev, f"preflight_{entorno}")
        esperado = {n: REFERENCIA[entorno][n] for n in nodos}
        anotar(salida, f"PREFLIGHT {entorno} | {json.dumps(obtenido, ensure_ascii=False)}")
        if obtenido != esperado:
            sys.exit(f"PREFLIGHT ROJO ({entorno}): no se muta nada. Esperado {esperado}")

    veredictos = []
    for mid, desc, cambios, entorno, objetivo, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto, sustituto in cambios:
            if textos[f].count(texto) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto, sustituto)
        if not aplicable:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        obtenido = {}
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            obtenido = correr(objetivo, entorno, base, ev, mid)
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        referencia = {n: REFERENCIA[entorno][n] for n in objetivo}
        cambian = [n for n in objetivo if obtenido.get(n) != referencia[n]]
        if not ok:
            resultado = "NO_CLASIFICABLE"
        elif equivalencia is not None:
            resultado = "EQUIVALENTE" if not cambian else "NO_CLASIFICABLE"
        elif "ausente" in obtenido.values():
            resultado = "NO_CLASIFICABLE"
        else:
            resultado = "MUERTO" if len(cambian) == len(objetivo) else "VIVO"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        v = (mid, resultado, json.dumps({n.split("::")[1]: s for n, s in obtenido.items()}, ensure_ascii=False), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
