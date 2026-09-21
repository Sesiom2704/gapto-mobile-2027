#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p2b_oraculo.py
# Ruta: scripts/migration_v3/rv3_p2b_oraculo.py
# Descripcion: RV3 / P2b. Auditoria del oraculo RUN06 (modelo logico v0.8)
#              frente al contrato fisico 0330 leido del catalogo de una base
#              PostgreSQL con la cadena 0001..0330 aplicada.
#
#   Produce, sin valores personales:
#     - por tabla RUN06 con filas: tabla 0330 equivalente, columnas que solo
#       existen en RUN06 y columnas 0330 NOT NULL sin DEFAULT que RUN06 no
#       informa (trabajo obligatorio de la transformacion P5);
#     - tablas 0330 sin equivalente en RUN06;
#     - DV-7: transferencias RUN06 con cuenta origen = cuenta destino.
#   RUN06 es oraculo subordinado a las reglas canonicas (RV3-D001/D002).
#
# USO:
#   set GAPTO_RV3_CATALOGO_URL=<dsn de una base 0330 desechable>
#   python scripts/migration_v3/rv3_p2b_oraculo.py --run06 RUTA --salida DIR_FUERA_DEL_REPO
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

VERSION = "0.1.0"
_AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("rv3_p1_equivalencia", _AQUI / "rv3_p1_equivalencia.py")
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)

ALIAS_RUN06_A_0330 = {
    "fin_condiciones_versiones": "financiacion_condiciones_versiones",
    "inv_asignaciones_aportacion": "inversion_asignaciones_efecto",
    "contrato_rev_renta_versiones": "contrato_revision_renta_versiones",
    "obligaciones_financieras": "derechos_obligaciones_financieras",
    "provincias": "regiones",
}
DV7_ESPERADO = {"transferencias": 141, "movimientos": 282, "misma_cuenta": 58}


def catalogo(dsn: str) -> dict:
    import psycopg
    cols = defaultdict(dict)
    with psycopg.connect(dsn) as c:
        for t, col, nn, dflt in c.execute(
                "SELECT c.table_name, c.column_name, c.is_nullable, c.column_default "
                "FROM information_schema.columns c JOIN pg_tables p "
                "ON p.schemaname = c.table_schema AND p.tablename = c.table_name "
                "WHERE c.table_schema = 'gapto' ORDER BY 1, c.ordinal_position"):
            cols[t][col] = {"nullable": nn == "YES", "default": dflt is not None}
    return cols


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    args = ap.parse_args(argv)
    dsn = os.environ.get("GAPTO_RV3_CATALOGO_URL")
    if not dsn:
        print("ERROR: falta GAPTO_RV3_CATALOGO_URL", file=sys.stderr)
        return 2
    if p1.dentro_de(args.salida, _AQUI.parents[1]):
        print("ERROR: la salida debe quedar FUERA del repositorio", file=sys.stderr)
        return 2
    if p1.sha256_fichero(args.run06) != p1.SHA256_RUN06:
        print("STOP S3: RUN06 no canonico")
        return 3
    import openpyxl
    print(f"[{dt.datetime.now():%H:%M:%S}] [paso 1/3] Leyendo catalogo 0330 y RUN06", flush=True)
    cols = catalogo(dsn)
    wb = openpyxl.load_workbook(args.run06, read_only=True, data_only=True)
    tablas, filas_run06 = [], {}
    print(f"[{dt.datetime.now():%H:%M:%S}] [paso 2/3] Comparando tablas", flush=True)
    for n in wb.sheetnames:
        if n.startswith("00_"):
            continue
        cab, filas = p1.leer_hoja(wb, n)
        filas_run06[n] = filas
        destino = ALIAS_RUN06_A_0330.get(n, n)
        info = {"run06": n, "filas": len(filas), "tabla_0330": destino if destino in cols else None}
        if destino in cols:
            cab_set = {c for c in cab if c}
            info["solo_run06"] = sorted(cab_set - set(cols[destino]))
            info["obligatorias_0330_no_informadas"] = sorted(
                k for k, v in cols[destino].items() if not v["nullable"] and not v["default"] and k not in cab_set)
        tablas.append(info)
    sin_equiv = sorted(set(cols) - {ALIAS_RUN06_A_0330.get(t["run06"], t["run06"]) for t in tablas})

    cab_m, fm = p1.leer_hoja(wb, "movimientos_tesoreria")
    mov = {dict(zip(cab_m, r))["id"]: dict(zip(cab_m, r)) for r in fm}
    cab_t, ft = p1.leer_hoja(wb, "transferencias")
    misma = sum(1 for r in ft if mov[dict(zip(cab_t, r))["movimiento_salida_id"]]["cuenta_id"] ==
                mov[dict(zip(cab_t, r))["movimiento_entrada_id"]]["cuenta_id"])
    dv7 = {"transferencias": len(ft), "movimientos": len(mov), "misma_cuenta": misma}
    veredicto = "P2B_OK" if dv7 == DV7_ESPERADO else "STOP_S9"
    informe = {"herramienta": "scripts/migration_v3/rv3_p2b_oraculo.py", "version": VERSION,
               "ejecutado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "veredicto": veredicto, "dv7": dv7, "dv7_esperado": DV7_ESPERADO,
               "tablas": tablas, "tablas_0330_sin_equivalente_run06": sin_equiv,
               "filas_run06_total": sum(len(v) for v in filas_run06.values())}
    marca = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.salida.mkdir(parents=True, exist_ok=True)
    out = args.salida / f"rv3_p2b_oraculo_{marca}.json"
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[{dt.datetime.now():%H:%M:%S}] [paso 3/3] Veredicto: {veredicto}  DV-7: {dv7}")
    print(f"      tablas RUN06 con filas: {sum(1 for t in tablas if t['filas'])}  "
          f"sin tabla 0330: {[t['run06'] for t in tablas if t['filas'] and not t['tabla_0330']]}")
    print(f"      tablas 0330 sin equivalente RUN06: {sin_equiv}")
    print(f"      informe: {out.name}  sha256={p1.sha256_fichero(out)}")
    return 0 if veredicto == "P2B_OK" else 3


if __name__ == "__main__":
    sys.exit(main())
