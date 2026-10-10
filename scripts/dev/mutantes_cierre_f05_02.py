# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_cierre_f05_02.py
# Ruta: scripts/dev/mutantes_cierre_f05_02.py
# Descripcion: Pruebas negativas del script de cierre generalizado
#   (scripts/dev/verificar_cierre_f05_02.py; F05-02 B4, AJ-B2-03): un mutante
#   por condicion C1..C5, y para C2 uno por cada parte de la regla (linea
#   retirada, version sin sustituta, funcion modificada por adicion, clave de
#   diccionario redefinida por adicion), sin relajar ningun control.
#   Cada mutante es un COMMIT DESECHABLE creado con fontaneria de git sobre
#   --head (indice temporal GIT_INDEX_FILE + hash-object + write-tree +
#   commit-tree): no toca el arbol de trabajo ni el indice real, no crea rama
#   ni referencia y nunca se publica (queda como objeto suelto que git gc
#   recoge). Sobre cada uno se ejecuta el script de cierre del arbol de trabajo
#   con --base y las rutas prohibidas oficiales de B3+B4; el mutante esta
#   MUERTO si el script termina con rc 1 y su condicion objetivo aparece como
#   FALLA. Preflight: --head debe dar PASS (rc 0).
#
#   Uso: python scripts/dev/mutantes_cierre_f05_02.py --base <merge-base> [--head HEAD]
#          [--rutas-prohibidas ...] [--writers-terceros-autorizados ...]
#          [--funciones-enmendadas ...]
# Version: 0.1.0 (F05-02 B4, AJ-B2-03)
# Version: 0.2.0 (F05-03/F05-04 J2 §1.10): parametrizado por bloque. Las
#   rutas prohibidas y los dos parametros declarados del script 0.2.0 se
#   pasan tal cual al script (por defecto, los de B3+B4). MC2b localiza la
#   linea `# Version:` vigente del inventario (no una version fija) y MC5
#   modifica el primer fichero existente bajo la primera ruta prohibida. MC1
#   anade el writer en un fichero NO autorizado. Mismos 8 mutantes; ninguno
#   se relaja: los parametros declarados nunca cubren el fichero o la
#   funcion que muta cada uno.
# ============================================================

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "dev" / "verificar_cierre_f05_02.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
RUTAS_B3B4 = (
    "migrations/,backend/app/services/,backend/app/core/,backend/app/repositories/,backend/app/categorias/,"
    "backend/app/magnitudes/,backend/app/preferencias/resolver.py,backend/app/preferencias/servicio.py,"
    "backend/app/preferencias/repositorio.py"
)


def git(*args: str, entrada: bytes | None = None, env: dict | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, input=entrada, capture_output=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8")


def leer(commit: str, ruta: str) -> str:
    return git("show", f"{commit}:{ruta}")


def una_vez(texto: str, a: str, b: str) -> str:
    if texto.count(a) != 1:
        raise RuntimeError(f"ancla no unica ({texto.count(a)}): {a[:60]!r}")
    return texto.replace(a, b)


def commit_desechable(head: str, mid: str, cambios: dict[str, str]) -> str:
    """Commit sin referencia: head + cambios (ruta -> contenido nuevo)."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(tmp) / "index")}
        git("read-tree", head, env=env)
        for ruta, contenido in cambios.items():
            blob = git("hash-object", "-w", "--stdin", entrada=contenido.encode("utf-8")).strip()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{ruta}", env=env)
        arbol = git("write-tree", env=env).strip()
    return git("commit-tree", arbol, "-p", head, "-m", f"MUTANTE {mid} (desechable, no se publica)").strip()


def _version(t154: str) -> str:
    import re

    lineas = re.findall(r"^# Version: [^\n]*\n", t154, flags=re.MULTILINE)
    if len(lineas) != 1:
        raise RuntimeError(f"el inventario debe tener UNA linea # Version: ({len(lineas)})")
    return lineas[0]


def _prohibido(head: str, rutas: str) -> str:
    primera = rutas.split(",")[0].strip()
    if not primera.endswith("/"):
        return primera
    ficheros = git("ls-tree", "-r", "--name-only", head, "--", primera).split("\n")
    return next(f for f in ficheros if f and not f.endswith(".sql")) if not primera.startswith("migrations") \
        else next(f for f in ficheros if f)


def mutantes(head: str, rutas: str = "") -> list[tuple[str, str, str, dict[str, str]]]:
    """(id, condicion objetivo, descripcion, cambios)."""
    t154 = leer(head, T154)
    lect = leer(head, "backend/app/api/lecturas_vs01.py")
    prohibido = _prohibido(head, (rutas or RUTAS_B3B4).replace("migrations/,", ""))
    resolver = leer(head, prohibido)
    return [
        ("MC1", "C1", "writer de terceros anadido en backend/ (fuera de las rutas prohibidas)",
         # El literal se parte para que este arnes no sea, el mismo, un falso positivo de C1.
         {"backend/app/api/lecturas_vs01.py": lect + '\n_MUTANTE = "INSERT INTO gapto.' + 'terceros (id) VALUES (%s)"\n'}),
        ("MC2a", "C2", "linea de comentario retirada del inventario (no es la de version)",
         {T154: una_vez(t154, "#: Herramientas de test dentro de scripts/dev que NO se ejecutan en runtime y\n", "")}),
        ("MC2b", "C2", "linea # Version: retirada sin sustituta",
         {T154: una_vez(t154, _version(t154), "")}),
        ("MC2c", "C2", "funcion previa modificada SOLO por adicion de una linea",
         {T154: una_vez(t154, "def test_i7_cliente_movil_sin_menciones_sin_registrar():\n",
                        "def test_i7_cliente_movil_sin_menciones_sin_registrar():\n    assert True\n")}),
        ("MC2d", "C2", "clave previa de un diccionario redefinida SOLO por adicion",
         {T154: una_vez(t154, '    "mobile/src/screens/PreferenciasAjustesScreen.tsx":',
                        '    "mobile/src/domain/intencion.ts": "redefinida por un alta",\n'
                        '    "mobile/src/screens/PreferenciasAjustesScreen.tsx":')}),
        ("MC3", "C3", "funcion I13 modificada",
         {T154: una_vez(t154, "def test_i13_c_orden_autoritativo_de_la_api_sin_reordenacion_en_el_cliente():\n",
                        "def test_i13_c_orden_autoritativo_de_la_api_sin_reordenacion_en_el_cliente():\n    return\n")}),
        ("MC4", "C4", "migration nueva (DDL)",
         {"migrations/9999_mutante_cierre.sql": "-- mutante desechable: no se aplica ni se publica\nSELECT 1;\n"}),
        ("MC5", "C5", f"fichero prohibido modificado ({prohibido})",
         {prohibido: resolver + "# mutante desechable\n"}),
    ]


def ejecutar(base: str, head: str, extra: tuple[str, ...] = ("--rutas-prohibidas", RUTAS_B3B4)) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--head", head, *extra],
        cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
    )
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description="Pruebas negativas del script de cierre F05-02")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--rutas-prohibidas", default=RUTAS_B3B4)
    ap.add_argument("--writers-terceros-autorizados", default="")
    ap.add_argument("--funciones-enmendadas", default="")
    a = ap.parse_args()
    extra = ("--rutas-prohibidas", a.rutas_prohibidas, "--writers-terceros-autorizados",
             a.writers_terceros_autorizados, "--funciones-enmendadas", a.funciones_enmendadas)
    base = git("rev-parse", "--verify", f"{a.base}^{{commit}}").strip()
    head = git("rev-parse", "--verify", f"{a.head}^{{commit}}").strip()
    print(f"base {base}\nhead {head}")
    rc, salida = ejecutar(base, head, extra)
    print(f"PREFLIGHT head: rc={rc}")
    if rc != 0:
        print(salida)
        print("PREFLIGHT ROJO: no se muta nada.")
        return 1
    veredictos = []
    for mid, cond, desc, cambios in mutantes(head, a.rutas_prohibidas):
        commit = commit_desechable(head, mid, cambios)
        rc, salida = ejecutar(base, commit, extra)
        falla = any(l.startswith(f"FALLA {cond} ") for l in salida.splitlines())
        v = "MUERTO" if rc == 1 and falla else "VIVO"
        veredictos.append((mid, v))
        print(f"{mid} {v} objetivo={cond} rc={rc} commit={commit} :: {desc}")
        for l in salida.splitlines():
            if l.startswith(("FALLA", "      - ")):
                print(f"    {l.strip()}")
    muertos = sum(1 for _, v in veredictos if v == "MUERTO")
    print("RESUMEN", muertos, "/", len(veredictos), "muertos")
    return 0 if muertos == len(veredictos) else 1


if __name__ == "__main__":
    sys.exit(main())
