# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_s1_suplementario.py
# Ruta: scripts/migration_v3/rv3_s1_suplementario.py
# Descripcion: RV3 / escenario S1 (RV3-D002-A, mandatos 2026-09-22). Recupera S1 de la Sheet exportada, exige su
#              hash semantico contractual (RV3_S1_SEMHASH_V1), reproduce el delta B0<->S1 y construye la fuente
#              efectiva S1 = filas equivalentes con su literal B0 + filas MODIFICADAS (solo las columnas DISTINTO)
#              + altas SOLO_SHEET, sin la baja. P3-S1 (G2): normalizacion representacional del export (float entero
#              -> entero, '' -> ausencia, fechas ISO), sin inferencia semantica y sin tocar la regla del 141.
#              P4-S1: identidad UUIDv5 por (contenedor, clave); una fila modificada conserva su identidad. P5-S1:
#              transformacion con la MISMA semantica de P5 (las decisiones S1 viven en P5 y solo se activan con sus
#              filas), ejecutada dos veces exigiendo el mismo hash, con la fuente de importacion reetiquetada como
#              S1. P5b-S1: auditoria R-F04-015 sobre el dataset S1. Fail-closed: hash S1 distinto, delta distinto
#              del contrato o dataset no determinista -> STOP.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import importlib.util
import json
import sys
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
S1_SEMHASH_CONTRACTUAL = "0a180ec40f525b30d9a4e3a42dc9ef078347aca74d0f5a4d8bc4862bde2ef665"
DELTA_CONTRACTUAL = {"EQUIVALENTE": 2474, "MODIFICADA": 26, "SOLO_SHEET": 38, "SOLO_SNAPSHOT": 1}
NOMBRE_FUENTE_S1 = "S1 estado semantico de la Sheet V3 (RV3-D002-A)"


class StopS1(Exception):
    def __init__(self, codigo: str, detalle: str):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo


def _mod(nombre, fichero):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / fichero)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    spec.loader.exec_module(m)
    return m


def normalizar_export(v):
    """P3-S1 (G2): representacion del export de la Sheet -> representacion B0. Sin inferencia semantica."""
    if isinstance(v, str) and v.strip() == "":
        return None                                   # ausencia -> NULL/UNKNOWN
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)                                 # float matematicamente entero -> entero
    if isinstance(v, decimal.Decimal) and v == v.to_integral_value():
        return int(v)
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()                          # fechas -> ISO contractual
    return v


def fijar_s1(P1B, p1, sheet: Path, run06: Path, sheet_id: str, modified: str, salida: Path) -> dict:
    """Ejecuta P1b: manifest + hash semantico; exige el hash contractual."""
    rc = P1B.main(["--sheet", str(sheet), "--run06", str(run06), "--sheet-id", sheet_id,
                   "--modified-time", modified, "--salida", str(salida), "--sha-run06", p1.sha256_fichero(run06)])
    man = sorted(salida.glob("rv3_p1b_manifest_s1_*.json"))[-1]
    doc = json.loads(man.read_text(encoding="utf-8"))
    obtenido = doc["s1"]["hash_semantico"] if isinstance(doc.get("s1"), dict) and "hash_semantico" in doc["s1"] \
        else doc.get("hash_semantico")
    if rc != 0 or obtenido != S1_SEMHASH_CONTRACTUAL:
        raise StopS1("S3_S1_NO_REPRODUCIBLE", f"rc={rc} hash={obtenido}")
    return {"manifest": man.name, "hash_semantico": obtenido, "sheet_id": sheet_id, "modified_time": modified}


def delta_b0_s1(p1, sheet: Path, run06: Path) -> list:
    import openpyxl
    snap = p1.cargar_snapshot(openpyxl.load_workbook(run06, read_only=True, data_only=True))
    res = p1.comparar(openpyxl.load_workbook(sheet, read_only=True, data_only=True),
                      snap[0] if isinstance(snap, tuple) else snap)
    deltas = [x for x in (res if isinstance(res, tuple) else [res]) if isinstance(x, list)][0]
    # los EQUIVALENTE no producen entrada de delta; su recuento lo verifica P1b (S1_FIJADO) contra el contrato
    esperado = {k: v for k, v in DELTA_CONTRACTUAL.items() if k != "EQUIVALENTE"}
    cuenta = {k: sum(1 for d in deltas if d["tipo"] == k) for k in esperado}
    if cuenta != esperado:
        raise StopS1("S3_DELTA_DISTINTO_DEL_CONTRATO", json.dumps(cuenta))
    return deltas


def fuente_efectiva(fu, b0: dict, s1: dict, deltas: list) -> tuple[dict, dict]:
    """B0 para las equivalentes (literal lexico), S1 para las 64 no equivalentes, sin la baja."""
    comb = {c: dict(regs) for c, regs in b0.items()}
    s1f = fu.fuente_s1(s1)
    clases = {"MODIFICADA": [], "SOLO_SHEET": [], "SOLO_SNAPSHOT": []}
    for d in deltas:
        c, k, t = d["contenedor"], d["clave"], d["tipo"]
        if t not in clases:
            continue
        clases[t].append(f"{c}/{k}")
        if t == "SOLO_SNAPSHOT":
            comb[c].pop(k, None)
            continue
        base = dict(b0[c][k].datos) if t == "MODIFICADA" else {}
        fila = s1f[c][k]
        cols = [x if isinstance(x, str) else x.get("columna") for x in d["columnas"]] if t == "MODIFICADA" else list(fila)
        for col in cols:
            base[col] = normalizar_export(fila.get(col))
        texto = json.dumps(base, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        comb.setdefault(c, {})[k] = fu.RegistroB0(c, k, base, texto, fu.hash_registro(texto), None, None)
    return comb, clases


def etiquetar_fuente_s1(ds, sha_b0: str, semhash: str) -> None:
    for f in ds.filas["fuentes_importacion"].values():
        if f.get("sha256") == sha_b0:
            f.update(nombre_fuente=NOMBRE_FUENTE_S1, version_fuente="S1", sha256=semhash,
                     notas="equivalentes con el literal lexico de B0; 64 filas no equivalentes desde la Sheet "
                           "(P3-S1/G2); hash = RV3_S1_SEMHASH_V1")


def transformar_s1(P5, comb: dict, semhash: str, sha_b0: str, decisiones, ausentes: frozenset):
    ds = P5.transformar(comb, sha_b0, modo_lab=False, decisiones=decisiones, ausentes_s1=ausentes)
    etiquetar_fuente_s1(ds, sha_b0, semhash)
    return ds




def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 S1: reconstruccion, transformacion y dataset suplementario")
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--modified-time", required=True)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--dsn-import", default=None, help="laboratorio S1 nuevo (perfil RV3_IMPORT)")
    ap.add_argument("--dsn-auditoria", default=None)
    ap.add_argument("--commit", action="store_true", help="COMMIT real de la validacion fisica S1")
    a = ap.parse_args(argv)
    a.salida.mkdir(parents=True, exist_ok=True)
    P5 = _mod("rv3_p5_transformacion", "rv3_p5_transformacion.py")
    P1B = _mod("rv3_p1b_manifest_s1", "rv3_p1b_manifest_s1.py")
    P5B = _mod("rv3_p5b_rf04015", "rv3_p5b_rf04015.py")
    fu, p1 = P5.fu, P5.fu.p1
    ev = {"inicio_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(), "p5_version": P5.VERSION}
    try:
        ev["s1"] = fijar_s1(P1B, p1, a.sheet, a.run06, a.sheet_id, a.modified_time, a.salida)
        sha_b0 = p1.sha256_fichero(a.run06)
        b0 = fu.cargar_b0(a.run06, sha_b0)
        s1 = fu.cargar_s1(a.sheet)
        deltas = delta_b0_s1(p1, a.sheet, a.run06)
        ev["delta"] = DELTA_CONTRACTUAL
        comb, clases = fuente_efectiva(fu, b0, s1, deltas)
        ev["filas_s1"] = {k: len(v) for k, v in clases.items()}
        ev["claves_no_equivalentes"] = sorted(clases["MODIFICADA"] + clases["SOLO_SHEET"])
        ev["baja_b0"] = clases["SOLO_SNAPSHOT"]
        dec = P5.cargar_decisiones(a.decisiones_propietario)
        ausentes = frozenset(clases["SOLO_SNAPSHOT"])
        ds = transformar_s1(P5, comb, ev["s1"]["hash_semantico"], sha_b0, dec, ausentes)
        h1 = ds.hash()
        h2 = transformar_s1(P5, comb, ev["s1"]["hash_semantico"], sha_b0, dec, ausentes).hash()
        if h1 != h2:
            raise StopS1("S7_DATASET_S1_NO_DETERMINISTA", f"{h1} != {h2}")
        ev.update(hash_dataset_s1=h1, pendientes=ds.pendientes, recuentos=ds.recuentos())
        if ds.pendientes:
            raise StopS1("S20_PENDIENTES_S1", str(len(ds.pendientes)))
        # disposicion: toda fila no equivalente con destino o con traza explicita
        sin = []
        for clave in ev["claves_no_equivalentes"]:
            co, cl = clave.split("/", 1)
            oid = fu.uuid_origen(co, cl)
            if not any(m["registro_origen_id"] == oid for m in ds.filas["mapeos_importacion"].values()):
                sin.append(clave)
        ev["s1_sin_disposicion"] = sin
        if sin:
            raise StopS1("S8_S1_SIN_DISPOSICION", json.dumps(sin))
        ev["p5b"] = {k: v for k, v in P5B.auditar(ds).items() if k != "detalle"}
        if a.dsn_import:  # validacion fisica S1 en laboratorio nuevo (P6-S1)
            P6 = _mod("rv3_p6_carga", "rv3_p6_carga.py")
            ev["carga_fisica"] = P6.ejecutar(P5, ds, a.dsn_import, a.commit, a.dsn_auditoria)
        ev["ledger_s1"] = {r: sum(1 for e in ds.ledger if e["regla"] == r)
                           for r in ("D10-L", "D10-M", "D10-N", "D5-S1R", "D8B-S1", "NO_APLICA_S1_FILA_AUSENTE")}
        ev["veredicto"] = "S1_TRANSFORMADO"
    except StopS1 as e:
        ev.update(stop={"codigo": e.codigo, "detalle": str(e)}, veredicto="STOP")
    except Exception as e:  # noqa: BLE001 - se entrega el discriminante, no se repara
        ev.update(error={"tipo": type(e).__name__, "detalle": str(e)[:2000]}, veredicto="STOP")
    (a.salida / "rv3_s1_suplementario.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str),
                                                        encoding="utf-8")
    carga = ev.get("carga_fisica") or {}
    print(json.dumps({k: ev.get(k) for k in ("veredicto", "hash_dataset_s1", "filas_s1", "stop", "error",
                                             "ledger_s1")} |
                     {"carga": {k: carga.get(k) for k in ("txid", "commit", "txid_confirmado", "filas_insertadas")}},
                     default=str))
    return 0 if ev["veredicto"] == "S1_TRANSFORMADO" else 2


if __name__ == "__main__":
    sys.exit(main())
