# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r3.py
# Ruta: scripts/dev/mutantes_f04_r3.py
# Descripcion: Arnes de mutacion de F04-R3 `il1b` (F05-D050 §64.4.3; adenda 2
#   §D: «un mutante por guarda nueva o modificada»; resultado MUERTO o
#   EQUIVALENTE documentado). Mismo motor que mutantes_f04_r2c.py (D-181,
#   D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest; los de tests/api se lanzan con --rootdir=tests/api);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: el advisory POR RAIZ de OP-22 (M1 quitarlo, M2 tomarlo despues de
#   leer la identidad) y el mismo advisory como primer recurso de cada
#   adaptador que compone OP-22 (M3 gasto pagado, M4 ingreso cobrado, M5 gasto
#   compartido).
#   C2-H1 (F05-D051 paso 1, §65.4; AJ-F0507G2-07): la guarda del terminal
#   posterior de «Reabrir» (`_sucesor_reabrible`): M6 omite la busqueda del
#   terminal INTERMEDIO cuando hay cabeza abierta posterior (comportamiento
#   anterior a C2-H1); M7 desactiva el rechazo por terminal posterior. Sus
#   discriminantes son las pruebas ordinarias C2-H1 de test_214, la serie C2b
#   B-primero (vuelta v000) y test_113 (terminal posterior sin cabeza).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F04R3_CONCURRENCIA=1
#        python scripts/dev/mutantes_f04_r3.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.2.0 (F05-D051 paso 1: mutantes M6 y M7 de la guarda C2-H1)
# Version: 0.1.0 (F04-R3 il1b)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r3.journal.json"
SVC = "backend/app/services/compuesto_service.py"
GP = "backend/app/api/ejecucion_gasto_pagado.py"
REG = "backend/app/api/ejecucion_registro.py"
REP = "backend/app/api/ejecucion_reparto.py"
T14K = "tests/backend/test_14k_f04_r3_il1b_advisory_serial.py::test_il1b_advisory_por_raiz_serializa_op22"
T213 = "tests/api/test_213_f04_r3_il1b_adaptadores_serial.py::test_il1b_advisory_por_raiz_es_el_primer_recurso_del_adaptador"
LOCK_OP22 = "            repo_comp.tomar_advisory_raiz(sesion, raiz)\n"
LOCK_ADAPTADOR = "        repo_comp.tomar_advisory_raiz(sesion, intencion.intencion_id)\n"
PRV = "backend/app/services/previsiones_service.py"
T214 = "tests/api/test_214_f04_r3_c2_reabrir_serial.py::"
T113 = "tests/backend/test_113_rodante_y_materializacion.py::"
BUSCA_TERMINAL = "        posterior = repo_prev.terminal_posterior(sesion, regla_id, fecha_objetivo)\n"
RECHAZA_TERMINAL = "        if posterior is not None:\n            raise ErrorMotor(\n"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("M1", "OP-22 sin el advisory por raiz",
     [(SVC, LOCK_OP22, "")],
     [T14K + "[misma]", T14K + "[otra]"], None),
    ("M2", "OP-22 toma el advisory por raiz DESPUES de leer la identidad",
     [(SVC, LOCK_OP22, ""),
      (SVC, "            if repo_hechos.leer_estado(sesion, raiz) is not None:\n",
       "            existe = repo_hechos.leer_estado(sesion, raiz) is not None\n"
       "            repo_comp.tomar_advisory_raiz(sesion, raiz)\n"
       "            if existe:\n")],
     [T14K + "[misma]", T14K + "[otra]"], None),
    ("M3", "gasto pagado: el advisory por raiz deja de ser su primer recurso (solo el de OP-22)",
     [(GP, LOCK_ADAPTADOR, "")],
     [T213 + "[gasto_pagado]"], None),
    ("M4", "ingreso cobrado: el advisory por raiz deja de ser su primer recurso (solo el de OP-22)",
     [(REG, LOCK_ADAPTADOR, "")],
     [T213 + "[ingreso_cobrado]"], None),
    ("M5", "gasto compartido: el advisory por raiz deja de ser su primer recurso (solo el de OP-22)",
     [(REP, LOCK_ADAPTADOR, "")],
     [T213 + "[gasto_compartido]"], None),
    ("M6", "C2-H1: «Reabrir» omite la busqueda del terminal INTERMEDIO cuando hay cabeza abierta posterior",
     [(PRV, BUSCA_TERMINAL,
       "        posterior = None if hay_cabeza_posterior else repo_prev.terminal_posterior(\n"
       "            sesion, regla_id, fecha_objetivo)\n")],
     [T214 + "test_c2_h1_reabrir_con_un_tramo_posterior_realizado",
      T214 + "test_c2_h1_reabrir_con_un_tramo_posterior_omitido",
      T214 + "test_c2_h1_cadena_de_tres_terminales_solo_reabre_el_ultimo",
      T214 + "test_c2_h1_por_http_409_sin_cambios",
      T214 + "test_c2b_reabrir_frente_a_op22_realizando_el_sucesor[B-primero-v000]"], None),
    ("M7", "C2-H1: el terminal posterior encontrado no rechaza «Reabrir»",
     [(PRV, RECHAZA_TERMINAL, "        if False:\n            raise ErrorMotor(\n")],
     [T214 + "test_c2_h1_reabrir_con_un_tramo_posterior_realizado",
      T113 + "test_d024_sucesor_terminal_posterior_tambien_rechaza"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Ejecuta los nodeids: los de tests/backend y los de tests/api (con su
    --rootdir) por separado. rc != 0 si alguno falla."""
    rc = 0
    for grupo, extra in (("tests/backend/", []), ("tests/api/", ["--rootdir=tests/api"])):
        ids = [t for t in tests if t.startswith(grupo)]
        if ids:
            cmd = [sys.executable, "-m", "pytest", *ids, "-q", "-x", "-p", "no:cacheprovider", *extra]
            rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    return rc


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
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if os.getenv("GAPTO_F04R3_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_F04R3_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
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
        resultado = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            resultado = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        v = (mid, resultado if ok else "NO_CLASIFICABLE",
             ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
