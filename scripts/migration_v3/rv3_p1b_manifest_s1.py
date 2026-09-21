#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p1b_manifest_s1.py
# Ruta: scripts/migration_v3/rv3_p1b_manifest_s1.py
# Descripcion: RV3 / P1b (RV3-D002-A, mandato RV3-E001-R1 §2). Fija el estado
#              semantico S1 de la Google Sheet V3 mediante un manifest sin PII
#              y un hash semantico determinista (RV3_S1_SEMHASH_V1), y reejecuta
#              P1 exigiendo los recuentos de delta aprobados.
#
#   Serializacion RV3_S1_SEMHASH_V1 (independiente de los bytes del XLSX):
#     - hojas ordenadas por nombre (orden de code points);
#     - campos de cada hoja ordenados por nombre;
#     - filas identificadas por su clave origen canonica (canon_clave de P1),
#       ordenadas por esa clave; NO interviene el numero de fila fisico;
#     - cada celda se convierte en un token tipado:
#         null            -> ["null"]           (None o cadena vacia)
#         bool            -> ["bool", "true"|"false"]
#         numero          -> ["num", decimal canonico]   (1 == 1.0 == 1.00)
#         fecha/hora      -> ["ts", ISO 8601]
#         texto           -> ["str", texto exacto]
#     - documento JSON con claves ordenadas, sin espacios, UTF-8, sin escapar
#       no-ASCII; hash = SHA-256 de esos bytes.
#   No dependen del hash: timestamp del export, metadatos XLSX, orden de
#   diccionarios, orden fisico de filas o columnas, formato binario de Google.
#
#   Veredictos:
#     S1_FIJADO -> exit 0 (P1b superado; S3 levantado operativamente)
#     STOP_S3   -> exit 3 (clave ausente/duplicada o recuentos P1 distintos)
#     ERROR     -> exit 2
#
# USO:
#   python scripts/migration_v3/rv3_p1b_manifest_s1.py \
#       --sheet RUTA/sheet_actual.xlsx --run06 RUTA/GaptoMobile_2027_DB_RUN06_v08.xlsx \
#       --sheet-id ID --modified-time RFC3339 --salida DIRECTORIO_FUERA_DEL_REPO
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import sys
import time
from decimal import Decimal
from pathlib import Path

VERSION = "0.1.0"
ALGORITMO = "RV3_S1_SEMHASH_V1"
CLAVE_POR_DEFECTO = "id"
CLAVES_ESPECIALES = {"public.patrimonio_compra": "patrimonio_id"}
RECUENTOS_P1_APROBADOS = {"EQUIVALENTE": 2474, "MODIFICADA": 26, "SOLO_SHEET": 38, "SOLO_SNAPSHOT": 1}
FILAS_S1_ESPERADAS = 2538

_AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("rv3_p1_equivalencia", _AQUI / "rv3_p1_equivalencia.py")
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)

_T0 = time.monotonic()


def log(paso: int, total: int, msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] [paso {paso}/{total}] {msg}", flush=True)


class ErrorClave(Exception):
    pass


def _decimal_canonico(v) -> str:
    d = Decimal(repr(float(v))) if isinstance(v, float) else Decimal(int(v))
    if d == 0:
        return "0"
    s = format(d.normalize(), "f")
    return s


def token(v) -> list:
    if v is None or (isinstance(v, str) and v == ""):
        return ["null"]
    if isinstance(v, bool):
        return ["bool", "true" if v else "false"]
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return ["str", repr(v)]
        return ["num", _decimal_canonico(v)]
    if isinstance(v, dt.datetime):
        return ["ts", v.isoformat()]
    if isinstance(v, dt.date):
        return ["ts", v.isoformat()]
    return ["str", str(v)]


def columna_clave(hoja: str, cabecera: list) -> str:
    col = CLAVES_ESPECIALES.get(hoja, CLAVE_POR_DEFECTO)
    if col not in cabecera:
        raise ErrorClave(f"{hoja}: falta la columna clave '{col}'")
    return col


def estado_semantico(wb) -> dict:
    """Estructura canonica de todo el libro: {hoja: {campos, claves, filas}}."""
    estado = {}
    for hoja in sorted(wb.sheetnames):
        cab, filas = p1.leer_hoja(wb, hoja)
        campos = sorted(c for c in cab if c)
        registros = {}
        if filas:
            kc = columna_clave(hoja, cab)
            for r in filas:
                reg = dict(zip(cab, r))
                k = p1.canon_clave(reg.get(kc))
                if k == "":
                    raise ErrorClave(f"{hoja}: fila sin clave")
                if k in registros:
                    raise ErrorClave(f"{hoja}: clave duplicada {k}")
                registros[k] = {c: token(reg.get(c)) for c in campos}
        estado[hoja] = {"campos": campos, "filas": registros}
    return estado


def serializar(estado: dict) -> bytes:
    doc = {"algoritmo": ALGORITMO, "hojas": [
        {"nombre": h, "campos": e["campos"],
         "filas": [[k, e["filas"][k]] for k in sorted(e["filas"])]}
        for h, e in sorted(estado.items())]}
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_semantico(estado: dict) -> str:
    return hashlib.sha256(serializar(estado)).hexdigest()


def hash_hoja(nombre: str, e: dict) -> str:
    return hash_semantico({nombre: e})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P1b: manifest y hash semantico de S1")
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--modified-time", required=True, help="modifiedTime de Drive (declarado)")
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--sha-run06", default=p1.SHA256_RUN06)
    args = ap.parse_args(argv)
    total = 5
    try:
        import openpyxl
    except ImportError:
        print("ERROR: falta openpyxl", file=sys.stderr)
        return 2
    repo = _AQUI.parents[1]
    if p1.dentro_de(args.salida, repo):
        print("ERROR: la salida debe quedar FUERA del repositorio (WM §12C.11)", file=sys.stderr)
        return 2
    args.salida.mkdir(parents=True, exist_ok=True)

    log(1, total, "Reejecutando P1 (Sheet vs snapshot B0)")
    rc_p1 = p1.main(["--sheet", str(args.sheet), "--run06", str(args.run06),
                     "--salida", str(args.salida), "--sha-run06", args.sha_run06])
    if rc_p1 not in (0, 3):
        return 2
    informe_p1 = sorted(args.salida.glob("rv3_p1_equivalencia_*.json"))[-1]
    p1_json = json.loads(informe_p1.read_text(encoding="utf-8"))
    recuentos = {k: p1_json["filas"].get(k, 0) for k in RECUENTOS_P1_APROBADOS}

    log(2, total, "Construyendo estado semantico S1")
    wb = openpyxl.load_workbook(args.sheet, read_only=True, data_only=True)
    try:
        estado = estado_semantico(wb)
    except ErrorClave as e:
        print(f"STOP S3: {e}")
        return 3

    log(3, total, f"Calculando hash {ALGORITMO}")
    semhash = hash_semantico(estado)
    filas_total = sum(len(e["filas"]) for e in estado.values())
    campos_total = sum(len(e["campos"]) for e in estado.values())

    log(4, total, "Evaluando veredicto")
    problemas = []
    if recuentos != RECUENTOS_P1_APROBADOS:
        problemas.append(f"recuentos P1 {recuentos} != aprobados {RECUENTOS_P1_APROBADOS}")
    if filas_total != FILAS_S1_ESPERADAS:
        problemas.append(f"filas S1 {filas_total} != {FILAS_S1_ESPERADAS}")
    if len(estado) != p1.ESPERADO["hojas"] or campos_total != p1.ESPERADO["campos"]:
        problemas.append(f"estructura {len(estado)} hojas / {campos_total} campos")
    veredicto = "S1_FIJADO" if not problemas else "STOP_S3"

    manifest = {
        "herramienta": "scripts/migration_v3/rv3_p1b_manifest_s1.py",
        "version": VERSION,
        "algoritmo": ALGORITMO,
        "ejecutado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "veredicto": veredicto,
        "problemas": problemas,
        "s1": {
            "sheet_id": args.sheet_id,
            "modified_time_declarado": args.modified_time,
            "hash_semantico": semhash,
            "hojas": len(estado),
            "campos": campos_total,
            "filas": filas_total,
            "por_hoja": {h: {"campos": len(e["campos"]), "filas": len(e["filas"]),
                             "claves": sorted(e["filas"]), "hash": hash_hoja(h, e)}
                         for h, e in estado.items()},
            "corroboracion_export_xlsx_sha256": p1.sha256_fichero(args.sheet),
            "nota": "El SHA del XLSX solo corrobora esta descarga; la identidad de S1 es hash_semantico.",
        },
        "b0": {"run06_sha256": p1_json["entradas"]["run06_sha256"],
               "run06_sha256_canonico": p1_json["entradas"]["run06_sha256_canonico"]},
        "p1": {"informe": informe_p1.name, "recuentos": recuentos,
               "recuentos_aprobados": RECUENTOS_P1_APROBADOS,
               "deltas_por_contenedor": p1_json["deltas_no_explicados_por_contenedor"]},
    }
    marca = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    salida = args.salida / f"rv3_p1b_manifest_s1_{marca}.json"
    salida.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    log(5, total, f"Veredicto: {veredicto}")
    print(f"      hash semantico S1 ({ALGORITMO}): {semhash}")
    print(f"      S1: {len(estado)} hojas / {campos_total} campos / {filas_total} filas")
    print(f"      P1: {recuentos}")
    for pr in problemas:
        print(f"      PROBLEMA: {pr}")
    print(f"      manifest: {salida.name}  sha256={p1.sha256_fichero(salida)}")
    print(f"      duracion: {time.monotonic() - _T0:.1f} s")
    return 0 if veredicto == "S1_FIJADO" else 3


if __name__ == "__main__":
    sys.exit(main())
