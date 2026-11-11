#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: huellas_d111.py
# Ruta: scripts/gates/huellas_d111.py
# Descripcion: Huellas D-111 de una base frente a HUELLAS_D111_POR_HEAD[head] del runner de ESTE arbol
#   (scripts/postgres/run_clean_room.py y huellas_d111.sql), para usarlo como paso de verificacion del lanzador
#   (scripts/gates/lanzador_gate.py) sobre la copia inmutable. Sustituye al huellas.py de las carpetas de evidencia,
#   que apuntaba a un worktree fijo. La DSN se lee de una variable de entorno (por nombre) y nunca se imprime.
#   Salida: JSON con observada/referencia/igual por huella y el recuento; codigo 0 si todas coinciden, 1 si no,
#   2 si falla la conexion o el head no tiene referencia.
# Uso: python scripts/gates/huellas_d111.py --dsn-var GAPTO_TEST_DATABASE_URL --head 0352 [--salida f.json]
# Version: 0.1.0 (F03 · N1 de 0352, Paso 0)
# ============================================================
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn-var", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--salida")
    a = ap.parse_args(argv)
    dsn = os.environ.get(a.dsn_var)
    if not dsn:
        print(f"falta la variable {a.dsn_var}", file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location("rcr", RAIZ / "scripts" / "postgres" / "run_clean_room.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if a.head not in m.HUELLAS_D111_POR_HEAD:
        print(f"sin referencia de huellas para el head {a.head}", file=sys.stderr)
        return 2
    import psycopg
    try:
        with psycopg.connect(dsn) as c:
            cur = c.execute((RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8"))
            obs = dict(zip([d.name for d in cur.description], cur.fetchone()))
            base = c.execute("select current_database()").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        print(f"conexion o consulta fallida: {type(exc).__name__}", file=sys.stderr)
        return 2
    ref = m.HUELLAS_D111_POR_HEAD[a.head]
    det = {k: {"observada": obs.get(k), "referencia": ref[k], "igual": obs.get(k) == ref[k]} for k in ref}
    iguales = sum(1 for v in det.values() if v["igual"])
    res = {"base": base, "head": a.head, "iguales": f"{iguales}/{len(ref)}", "detalle": det}
    texto = json.dumps(res, ensure_ascii=False, indent=1)
    print(texto)
    if a.salida:
        pathlib.Path(a.salida).write_text(texto, encoding="utf-8")
    return 0 if iguales == len(ref) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
