# ============================================================
# GAPTO MOBILE 2027
# Fichero: verificar_cierre_f05_02_b1.py
# Ruta: scripts/dev/verificar_cierre_f05_02_b1.py
# Descripcion: Verificacion de cierre del bloque F05-02 B1 sobre un RANGO de
#   commits explicito (F05-02 B1-C, AJ-B1-05/06). Contiene las comprobaciones
#   que dependen de una base concreta y que por eso NO forman parte de la
#   suite permanente (salieron de test_170 v0.1.0):
#     C1 el diff base..head no anade ningun writer de terceros
#        (terceros, tercero_*, hecho_terceros, actores_financieros) en
#        backend/ ni scripts/ (AJ-D025-11, CC-02-6);
#     C2 el diff de test_154 es SOLO aditivo: ninguna funcion previa cambia
#        salvo I3 (que admite PREFERENCIA); solo se sustituyen las cuatro
#        lineas autorizadas por su version ampliada; ninguna entrada previa de
#        REGISTRO ni de EXCLUIDOS cambia; las nuevas son de los ficheros del
#        bloque (mandato B1 v0.2 §2, opcion A del STOP);
#     C3 las funciones de I13 de test_154 son identicas (AST) en base y head;
#     C4 sin DDL: migrations/ sin cambios en el rango (CC-02-7);
#     C5 rutas prohibidas por el mandato B1 sin cambios en el rango.
#   Ambos extremos se leen de git (git show / git diff base head), nunca del
#   arbol de trabajo. Imprime un informe y termina con rc != 0 si falla
#   alguna comprobacion o si base/head no se resuelven.
#
#   Uso: python scripts/dev/verificar_cierre_f05_02_b1.py --base <commit> --head <commit>
#   (base = merge-base con origin/main; head = HEAD final del bloque).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
EXCLUIDOS_DIFF = {"scripts/dev/mutantes_f05_02.py", "scripts/dev/verificar_cierre_f05_02_b1.py"}
FICHEROS_BLOQUE = {"backend/app/api/app.py", "backend/app/api/dto_preferencias.py"}
PREFIJO_BLOQUE = "backend/app/preferencias/"
RUTAS_PROHIBIDAS = (
    "migrations/", "backend/app/services/", "backend/app/core/", "backend/app/repositories/",
    "backend/app/categorias/", "backend/app/magnitudes/", "backend/app/api/ejecucion_gasto_pagado.py",
    "backend/app/api/traductor_gasto_pagado.py", "mobile/",
)
ESCRITURA_TERCEROS = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
    r"(terceros|tercero_\w+|hecho_terceros|actores_financieros)\b",
    re.IGNORECASE,
)
#: Lineas de test_154 que el bloque sustituye por su version ampliada.
SUSTITUCIONES_T154 = {
    "# Version: 0.8.1": "# Version: 0.9.0",
    'FRONTERA = ("backend/app/api/", "backend/app/categorias/", "backend/app/magnitudes/")':
        'FRONTERA = ("backend/app/api/", "backend/app/categorias/", "backend/app/magnitudes/", '
        '"backend/app/preferencias/")',
    'CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO", "SEED_DEV"}':
        'CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO", "SEED_DEV", "PREFERENCIA"}',
    '            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO"}, (ruta, qual, clase)':
        '            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO", "PREFERENCIA"}, (ruta, qual, clase)',
}
FUNCION_I3 = "test_i3_frontera_solo_r_guarda_o_a_frontera"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def funciones(texto: str) -> dict[str, str]:
    return {n.name: ast.dump(n) for n in ast.parse(texto).body if isinstance(n, ast.FunctionDef)}


def registro(texto: str) -> tuple[dict, dict]:
    espacio: dict = {"__name__": "t154_version", "__file__": str(RAIZ / T154)}
    exec(compile(texto, T154, "exec"), espacio)
    return espacio["REGISTRO"], espacio["EXCLUIDOS"]


def c1_sin_writer_de_terceros(base: str, head: str) -> list[str]:
    diff = git("diff", base, head, "--", "backend", "scripts")
    fallos, fichero = [], None
    for linea in diff.splitlines():
        if linea.startswith("+++ "):
            fichero = linea[6:] if linea.startswith("+++ b/") else None
        elif linea.startswith("+") and fichero not in EXCLUIDOS_DIFF and ESCRITURA_TERCEROS.search(linea[1:]):
            fallos.append(f"{fichero}: {linea[1:].strip()}")
    return fallos


def c2_test_154_solo_aditivo(base: str, head: str) -> list[str]:
    antes, despues = git("show", f"{base}:{T154}"), git("show", f"{head}:{T154}")
    fallos = []
    f_antes, f_despues = funciones(antes), funciones(despues)
    fallos += [f"funcion retirada: {n}" for n in sorted(set(f_antes) - set(f_despues))]
    fallos += [f"funcion modificada: {n}" for n in sorted(f_antes)
               if n in f_despues and f_antes[n] != f_despues[n] and n != FUNCION_I3]
    diff = git("diff", "-U0", base, head, "--", T154)
    quitadas = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    puestas = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    for vieja in quitadas:
        if vieja not in SUSTITUCIONES_T154:
            fallos.append(f"linea eliminada no autorizada: {vieja.strip()}")
        elif SUSTITUCIONES_T154[vieja] not in puestas:
            fallos.append(f"linea sustituida sin su version ampliada: {vieja.strip()}")
    r_antes, e_antes = registro(antes)
    r_despues, e_despues = registro(despues)
    fallos += [f"entrada previa de REGISTRO modificada o retirada: {k}" for k, v in r_antes.items()
               if r_despues.get(k) != v]
    for k in sorted(set(r_despues) - set(r_antes)):
        if not (k[0] in FICHEROS_BLOQUE or k[0].startswith(PREFIJO_BLOQUE)):
            fallos.append(f"entrada nueva fuera de los ficheros del bloque: {k}")
        elif r_despues[k][0] not in {"PREFERENCIA", "R"}:
            fallos.append(f"entrada nueva con clase no autorizada: {k} -> {r_despues[k][0]}")
    fallos += [f"EXCLUIDOS previo modificado: {k}" for k, v in e_antes.items() if e_despues.get(k) != v]
    nuevas = set(e_despues) - set(e_antes)
    if not nuevas <= {"scripts/dev/mutantes_f05_02.py"}:
        fallos.append(f"EXCLUIDOS nuevos no autorizados: {sorted(nuevas)}")
    return fallos


def c3_i13_sin_cambios(base: str, head: str) -> list[str]:
    f_antes = funciones(git("show", f"{base}:{T154}"))
    f_despues = funciones(git("show", f"{head}:{T154}"))
    i13 = sorted(n for n in f_antes if n.startswith("test_i13"))
    if not i13:
        return ["la base no contiene funciones test_i13*"]
    return [f"I13 cambiada o retirada: {n}" for n in i13 if f_despues.get(n) != f_antes[n]]


def c4_c5_rutas_intactas(base: str, head: str) -> list[str]:
    cambiados = git("diff", "--name-only", base, head).split()
    return [f"ruta prohibida modificada: {f}" for f in cambiados if f.startswith(RUTAS_PROHIBIDAS)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="merge-base con origin/main")
    ap.add_argument("--head", required=True, help="HEAD final del bloque")
    a = ap.parse_args()
    try:
        base = git("rev-parse", "--verify", f"{a.base}^{{commit}}").strip()
        head = git("rev-parse", "--verify", f"{a.head}^{{commit}}").strip()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 2
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, head], cwd=RAIZ).returncode != 0:
        print(f"ERROR: la base {base} no es ancestro de head {head}")
        return 2
    print("F05-02 B1 - verificacion de cierre")
    print(f"base {base}")
    print(f"head {head}")
    comprobaciones = [
        ("C1 sin writer de terceros en el diff (backend/, scripts/)", c1_sin_writer_de_terceros),
        ("C2 test_154 solo aditivo", c2_test_154_solo_aditivo),
        ("C3 funciones I13 de test_154 identicas (AST)", c3_i13_sin_cambios),
        ("C4/C5 migrations/ y rutas prohibidas sin cambios", c4_c5_rutas_intactas),
    ]
    rc = 0
    for nombre, fn in comprobaciones:
        fallos = fn(base, head)
        print(f"{'OK  ' if not fallos else 'FALLA'} {nombre}")
        for f in fallos:
            print(f"      - {f}")
        rc = rc or (1 if fallos else 0)
    print("RESULTADO:", "PASS" if rc == 0 else "FAIL")
    return rc


if __name__ == "__main__":
    sys.exit(main())
