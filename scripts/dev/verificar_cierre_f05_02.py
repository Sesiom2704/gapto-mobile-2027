# ============================================================
# GAPTO MOBILE 2027
# Fichero: verificar_cierre_f05_02.py
# Ruta: scripts/dev/verificar_cierre_f05_02.py
# Descripcion: Verificacion de cierre de la subfase F05-02, generalizada por
#   bloque (F05-02 B4, AJ-B2-03; F05-D028 §43.5). Sustituye en el cierre al
#   script de B1 (verificar_cierre_f05_02_b1.py), que se conserva sin tocar.
#   Mismo principio: gate N1 reproducible sobre un RANGO de commits explicito,
#   ambos extremos leidos de git (git show / git diff base head), nunca del
#   arbol de trabajo. No es una dependencia del runtime ni sustituye a las
#   suites, la concurrencia o los mutantes (R-B1C-06).
#
#   Una funcion por condicion (sin agrupar):
#     C1 el diff base..head no anade ningun writer de terceros (terceros,
#        tercero_*, hecho_terceros, actores_financieros) en backend/ ni
#        scripts/ (AJ-D025-11, CC-02-6). Solo se excluye este mismo fichero
#        (contiene el patron como texto).
#     C2 el fichero de --inventario es SOLO aditivo: ninguna linea retirada
#        salvo, como excepcion UNICA y explicita, la linea `# Version: X` de la
#        cabecera (Working Method §11), y solo si se sustituye por otra
#        `# Version: Y`; ninguna funcion previa cambia (AST); ninguna clave
#        previa de un diccionario de nivel de modulo cambia de valor ni se
#        redefine (un alta no puede pisar una entrada previa).
#     C3 las funciones I13 de test_154 son identicas (AST) en base y head.
#     C4 sin DDL: migrations/ sin cambios en el rango (CC-02-7).
#     C5 las rutas de --rutas-prohibidas (lista del bloque, separada por
#        comas; prefijo de directorio terminado en «/» o fichero exacto) sin
#        cambios en el rango.
#   Imprime un informe y termina con rc 0 (PASS), 1 (FAIL) o 2 (error de uso:
#   base/head no resolubles o base que no es ancestro de head).
#
#   Uso: python scripts/dev/verificar_cierre_f05_02.py --base <merge-base>
#          --head <HEAD> --rutas-prohibidas migrations/,backend/app/services/,...
#          [--inventario tests/api/test_154_f05_01_inventario_categorias.py]
#   Pruebas negativas: scripts/dev/mutantes_cierre_f05_02.py.
# Version: 0.1.0 (F05-02 B4, AJ-B2-03)
# ============================================================

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ESTE = "scripts/dev/verificar_cierre_f05_02.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
ESCRITURA_TERCEROS = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
    r"(terceros|tercero_\w+|hecho_terceros|actores_financieros)\b",
    re.IGNORECASE,
)
#: Excepcion UNICA de C2: la linea de version de la cabecera.
LINEA_VERSION = re.compile(r"^# Version: \S+$")
FIN_CABECERA = "# ============================================================"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def cambiados(base: str, head: str) -> list[str]:
    return git("diff", "--name-only", "--no-renames", base, head).split("\n")[:-1]


def funciones(texto: str) -> dict[str, str]:
    return {n.name: ast.dump(n) for n in ast.parse(texto).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def diccionarios(texto: str) -> dict[str, list[tuple[str, str]]]:
    """Diccionarios literales de nivel de modulo: nombre -> [(clave, valor)] en orden (con repeticiones)."""
    res: dict[str, list[tuple[str, str]]] = {}
    for n in ast.parse(texto).body:
        objetivo = n.targets[0] if isinstance(n, ast.Assign) and len(n.targets) == 1 else getattr(n, "target", None)
        valor = getattr(n, "value", None)
        if isinstance(objetivo, ast.Name) and isinstance(valor, ast.Dict):
            # Un desempaquetado `**expr` se identifica por su expresion (no es una clave).
            res[objetivo.id] = [(ast.unparse(k) if k is not None else f"**{ast.unparse(v)}", ast.dump(v))
                                for k, v in zip(valor.keys, valor.values)]
    return res


def linea_fin_cabecera(texto: str) -> int:
    """Numero (1..n) de la linea que cierra la cabecera (segunda linea de «=»)."""
    marcas = [i for i, l in enumerate(texto.splitlines(), 1) if l == FIN_CABECERA]
    return marcas[1] if len(marcas) >= 2 else 0


# ------------------------------------------------------------------ condiciones
def c1_sin_writer_de_terceros(base: str, head: str, _a: argparse.Namespace) -> list[str]:
    diff = git("diff", base, head, "--", "backend", "scripts")
    fallos, fichero = [], None
    for linea in diff.splitlines():
        if linea.startswith("+++ "):
            fichero = linea[6:] if linea.startswith("+++ b/") else None
        elif linea.startswith("+") and fichero != ESTE and ESCRITURA_TERCEROS.search(linea[1:]):
            fallos.append(f"{fichero}: {linea[1:].strip()}")
    return fallos


def c2_inventario_solo_aditivo(base: str, head: str, a: argparse.Namespace) -> list[str]:
    inv = a.inventario
    try:
        antes = git("show", f"{base}:{inv}")
    except RuntimeError:
        return [f"el inventario no existe en la base: {inv}"]
    try:
        despues = git("show", f"{head}:{inv}")
    except RuntimeError:
        return [f"inventario retirado: {inv}"]
    fallos: list[str] = []
    # (a) Lineas retiradas: solo la `# Version:` de la cabecera, sustituida por otra.
    fin = linea_fin_cabecera(antes)
    quitadas, puestas = [], []
    for linea in git("diff", "-U0", base, head, "--", inv).splitlines():
        if linea.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? ", linea)
            num = int(m.group(1))
        elif linea.startswith("-") and not linea.startswith("---"):
            quitadas.append((num, linea[1:]))
            num += 1
        elif linea.startswith("+") and not linea.startswith("+++"):
            puestas.append(linea[1:])
    version = [(n, l) for n, l in quitadas if LINEA_VERSION.match(l) and n < fin]
    for n, l in quitadas:
        if (n, l) not in version[:1]:
            fallos.append(f"linea {n} retirada no autorizada: {l.strip()}")
    if version and not any(LINEA_VERSION.match(l) for l in puestas):
        fallos.append(f"linea de version retirada sin su sustituta: {version[0][1].strip()}")
    # (b) Ninguna funcion previa cambia (AST).
    f_antes, f_despues = funciones(antes), funciones(despues)
    fallos += [f"funcion retirada: {n}" for n in sorted(set(f_antes) - set(f_despues))]
    fallos += [f"funcion modificada: {n}" for n in sorted(f_antes) if n in f_despues and f_antes[n] != f_despues[n]]
    # (c) Ninguna clave previa de un diccionario de modulo cambia ni se redefine.
    d_antes, d_despues = diccionarios(antes), diccionarios(despues)
    for nombre, pares in d_antes.items():
        if nombre not in d_despues:
            fallos.append(f"diccionario retirado: {nombre}")
            continue
        nuevo = d_despues[nombre]
        claves_nuevas = [k for k, _ in nuevo]
        for k, v in pares:
            if claves_nuevas.count(k) != 1:
                fallos.append(f"{nombre}: clave previa redefinida o retirada: {k[:100]}")
            elif dict(nuevo)[k] != v:
                fallos.append(f"{nombre}: valor previo modificado: {k[:100]}")
    return fallos


def c3_i13_sin_cambios(base: str, head: str, _a: argparse.Namespace) -> list[str]:
    f_antes = funciones(git("show", f"{base}:{T154}"))
    try:
        f_despues = funciones(git("show", f"{head}:{T154}"))
    except RuntimeError:
        return [f"test_154 retirado: {T154}"]
    i13 = sorted(n for n in f_antes if n.startswith("test_i13"))
    if not i13:
        return ["la base no contiene funciones test_i13*"]
    return [f"I13 cambiada o retirada: {n}" for n in i13 if f_despues.get(n) != f_antes[n]]


def c4_sin_ddl(base: str, head: str, _a: argparse.Namespace) -> list[str]:
    return [f"migrations/ modificada: {f}" for f in cambiados(base, head) if f.startswith("migrations/")]


def c5_rutas_prohibidas(base: str, head: str, a: argparse.Namespace) -> list[str]:
    rutas = a.rutas
    return [
        f"ruta prohibida modificada: {f}" for f in cambiados(base, head)
        if any(f.startswith(r) if r.endswith("/") else f == r for r in rutas)
    ]


COMPROBACIONES = [
    ("C1 sin writer de terceros en el diff (backend/, scripts/)", c1_sin_writer_de_terceros),
    ("C2 inventario solo aditivo (excepcion unica: # Version: de cabecera)", c2_inventario_solo_aditivo),
    ("C3 funciones I13 de test_154 identicas (AST)", c3_i13_sin_cambios),
    ("C4 migrations/ sin cambios (sin DDL)", c4_sin_ddl),
    ("C5 rutas prohibidas del bloque sin cambios", c5_rutas_prohibidas),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verificacion de cierre F05-02 (generalizada)")
    ap.add_argument("--base", required=True, help="merge-base con origin/main")
    ap.add_argument("--head", required=True, help="HEAD final del bloque")
    ap.add_argument("--rutas-prohibidas", required=True, help="lista separada por comas (dir/ o fichero)")
    ap.add_argument("--inventario", default=T154, help="fichero cuyo diff debe ser solo aditivo")
    a = ap.parse_args(argv)
    a.rutas = tuple(r.strip() for r in a.rutas_prohibidas.split(",") if r.strip())
    if not a.rutas:
        print("ERROR: --rutas-prohibidas vacia")
        return 2
    try:
        base = git("rev-parse", "--verify", f"{a.base}^{{commit}}").strip()
        head = git("rev-parse", "--verify", f"{a.head}^{{commit}}").strip()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 2
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, head], cwd=RAIZ).returncode != 0:
        print(f"ERROR: la base {base} no es ancestro de head {head}")
        return 2
    print("F05-02 - verificacion de cierre (generalizada)")
    print(f"base {base}")
    print(f"head {head}")
    print(f"inventario {a.inventario}")
    print(f"rutas prohibidas {','.join(a.rutas)}")
    rc = 0
    for nombre, fn in COMPROBACIONES:
        fallos = fn(base, head, a)
        print(f"{'OK  ' if not fallos else 'FALLA'} {nombre}")
        for f in fallos:
            print(f"      - {f}")
        rc = rc or (1 if fallos else 0)
    print("RESULTADO:", "PASS" if rc == 0 else "FAIL")
    return rc


if __name__ == "__main__":
    sys.exit(main())
