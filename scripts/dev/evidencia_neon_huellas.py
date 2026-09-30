# ============================================================
# GAPTO MOBILE 2027
# Fichero: evidencia_neon_huellas.py
# Ruta: scripts/dev/evidencia_neon_huellas.py
# Descripcion: Huellas D-111 de una base frente a la referencia aprobada
#   HUELLAS_D111_POR_HEAD[<head>] de scripts/postgres/run_clean_room.py
#   (leida por AST, sin importar ni duplicar el runner) y la consulta
#   versionada scripts/postgres/huellas_d111.sql. Versionado por
#   R-EVID-RUNNER (AJ-RLOCALE-02, F05 §31.5): sustituye al auxiliar no
#   versionado neon_huellas.py.
#   Anade un bloque al fichero de salida (se usa tras el replay y tras la
#   suite). Solo lectura. DSN desde la variable de entorno indicada por --env
#   (en Windows, si el proceso no la hereda, del valor de usuario en
#   HKCU\Environment); nunca se imprime. Codigo de salida 0 solo si las nueve
#   huellas coinciden.
#   Uso:
#     python scripts/dev/evidencia_neon_huellas.py --env GAPTO_CLEANROOM_URL \
#       --salida <carpeta>/huellas_d111.txt --head 0340 --momento "tras el replay"
# Version: 0.1.0 (F05-01 R-EVID-RUNNER, AJ-RLOCALE-02)
# ============================================================

from __future__ import annotations

import argparse
import ast
import datetime
import os
import pathlib
import sys

import psycopg

RAIZ = pathlib.Path(__file__).resolve().parents[2]
RUNNER = RAIZ / "scripts" / "postgres" / "run_clean_room.py"
CONSULTA = RAIZ / "scripts" / "postgres" / "huellas_d111.sql"


def dsn_desde_entorno(variable: str) -> str:
    valor = os.environ.get(variable)
    if not valor and sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                valor = winreg.QueryValueEx(k, variable)[0]
        except OSError:
            valor = None
    if not valor:
        sys.exit(f"Falta la variable de entorno {variable}.")
    return valor


def referencia(head: str) -> dict:
    arbol = ast.parse(RUNNER.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "HUELLAS_D111_POR_HEAD" for t in n.targets):
            tabla = ast.literal_eval(n.value)
            if tabla.get(head) is None:
                sys.exit(f"HUELLAS_D111_POR_HEAD no declara referencia para el head {head}.")
            return tabla[head]
    sys.exit("HUELLAS_D111_POR_HEAD no encontrado en run_clean_room.py.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--head", required=True, help="head declarado, p. ej. 0340")
    p.add_argument("--momento", required=True, help="p. ej. 'tras el replay' o 'tras la suite'")
    a = p.parse_args()

    ref = referencia(a.head)
    with psycopg.connect(dsn_desde_entorno(a.env), autocommit=True) as c, c.cursor() as cur:
        cur.execute(CONSULTA.read_text(encoding="utf-8"))
        fila = cur.fetchone()
        obtenidas = dict(zip([d.name for d in cur.description], fila))
        base = c.execute("SELECT current_database()").fetchone()[0]
    ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lineas = [f"Huellas D-111 ({a.momento}; {ahora}): observadas en {base} frente a HUELLAS_D111_POR_HEAD['{a.head}']"]
    iguales = 0
    for k, v in ref.items():
        ok = str(obtenidas.get(k)) == str(v)
        iguales += ok
        lineas.append(f"  {'ok  ' if ok else 'DIF '}  {k}: observada={obtenidas.get(k)} referencia={v}")
    lineas.append(f"RESULTADO: {'IGUALES' if iguales == len(ref) else 'DISTINTAS'} ({iguales}/{len(ref)})")
    with open(a.salida, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lineas) + "\n\n")
    print(lineas[-1])
    return 0 if iguales == len(ref) else 1


if __name__ == "__main__":
    sys.exit(main())
