# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p8_material.py
# Ruta: scripts/migration_v3/rv3_p8_material.py
# Descripcion: RV3 / P8 post-carga. Reconciliacion R01..R26 sobre la REALIDAD MATERIAL de la BD cargada (P6):
#              1) lee todas las tablas del dataset desde PostgreSQL en una transaccion READ ONLY (rol de auditoria
#                 sin RLS) y construye el Dataset material; 2) regenera P5 desde las mismas fuentes y exige el hash
#                 autorizado; 3) compara celda a celda BD vs dataset P5 (igualdad material, tipos normalizados);
#              4) ejecuta reconciliar() de rv3_p8_reconciliacion sobre el Dataset MATERIAL. Las metricas de proceso
#              que no viven en la BD (R02 disposicion de campos, R23 ledger, R24 perdidas declaradas) se toman del
#              P5 regenerado con el mismo hash y se declaran como tales. R25 se toma de la certificacion P7.
#              Fail-closed: hash distinto, celda distinta o cualquier FAIL -> NO_SUPERADO.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import importlib.util
import json
import sys
import uuid
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
SEMILLAS = {"metricas_definicion": ("AHORRO_NETO_PYL", "APORTACION_INVERSION_NETA", "TRANSFERENCIA_AHORRO_NETA")}


def _cargar(nombre, fichero):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / fichero)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


def normalizar(v):
    """Valor comparable independiente del tipo fisico: uuid/fecha -> texto, numerico -> Decimal exacto."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, _dt.datetime):
        return v.astimezone(_dt.timezone.utc).isoformat() if v.tzinfo else v.isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, (int, float, decimal.Decimal)):
        return decimal.Decimal(str(v)).normalize()
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(v, str):
        try:  # marca temporal textual del dataset -> misma forma que la de la BD
            if len(v) >= 19 and v[4] == "-" and v[10] in "T ":
                d = _dt.datetime.fromisoformat(v)
                return d.astimezone(_dt.timezone.utc).isoformat() if d.tzinfo else d.isoformat()
        except ValueError:
            pass
        return v
    return v


def leer_material(P5, c) -> dict:
    """tabla -> {pk: fila} con los valores normalizados, excluidas las semillas contractuales."""
    out = {}
    for t in P5.ORDEN_TABLAS:
        pk = P5.PK.get(t, "id")
        cur = c.execute(f"SELECT * FROM gapto.{t}")
        cols = [d.name for d in cur.description]
        filas = {}
        for r in cur.fetchall():
            f = dict(zip(cols, r))
            if t in SEMILLAS and f.get("codigo") in SEMILLAS[t]:
                continue
            filas[str(f[pk])] = f
        out[t] = filas
    return out


def cuantizado_fisico(v_dataset, v_bd) -> bool:
    """numeric(p,s) de PostgreSQL redondea la entrada a su escala (mitades lejos de cero). Es la unica diferencia
    admitida: el valor del dataset, redondeado a la escala fisica devuelta por la BD, es exactamente el de la BD."""
    if not isinstance(v_bd, decimal.Decimal) or isinstance(v_dataset, bool) or v_dataset is None:
        return False
    try:
        d = decimal.Decimal(str(v_dataset))
    except decimal.InvalidOperation:
        return False
    return d.quantize(decimal.Decimal(1).scaleb(v_bd.as_tuple().exponent), rounding=decimal.ROUND_HALF_UP) == v_bd


def comparar_celdas(P5, material: dict, ds, cuantizaciones: dict | None = None) -> dict:
    """Igualdad material: mismas PK y, en cada fila, mismo valor en cada columna del dataset. Las celdas que solo
    difieren por el redondeo de numeric a su escala fisica se registran aparte en `cuantizaciones` (no se ocultan)."""
    dif = {}
    for t in P5.ORDEN_TABLAS:
        m, d = material[t], ds.filas[t]
        faltan, sobran = set(d) - set(m), set(m) - set(d)
        celdas = 0
        for k in set(d) & set(m):
            for col, v in d[k].items():
                if col not in m[k]:
                    celdas += 1
                elif normalizar(v) != normalizar(m[k][col]):
                    if cuantizaciones is not None and cuantizado_fisico(v, m[k][col]):
                        q = cuantizaciones.setdefault(f"{t}.{col}", {"celdas": 0, "max_abs_diferencia": "0"})
                        q["celdas"] += 1
                        diff = abs(decimal.Decimal(str(v)) - m[k][col])
                        q["max_abs_diferencia"] = str(max(decimal.Decimal(q["max_abs_diferencia"]), diff))
                    else:
                        celdas += 1
        if faltan or sobran or celdas:
            dif[t] = {"faltan": len(faltan), "sobran": len(sobran), "celdas_distintas": celdas}
    return dif


def dataset_material(P5, material: dict, ds_p5):
    """Dataset con las FILAS de la BD (tipos normalizados a los del dataset) y los metadatos de proceso de P5."""
    dm = P5.Dataset(owner=ds_p5.owner)
    for t in P5.ORDEN_TABLAS:
        dm.filas[t] = {k: {col: (str(v) if isinstance(v, uuid.UUID) else v) for col, v in f.items()}
                       for k, f in material[t].items()}
    dm.self_id = ds_p5.self_id
    dm.trazabilidad = dict(ds_p5.trazabilidad)  # R02/R24: metricas del proceso de transformacion (mismo hash)
    dm.ledger = list(ds_p5.ledger)              # R23: ledger del proceso (mismo hash)
    tz = dm.trazabilidad                         # R05 se RECALCULA sobre la BD
    ro = set(dm.filas["registros_origen_importacion"])
    con = {m["registro_origen_id"] for m in dm.filas["mapeos_importacion"].values()}
    destinos = {(m["tabla_destino"], m["registro_destino_id"]) for m in dm.filas["mapeos_importacion"].values()}
    exentas = {"fuentes_importacion", "registros_origen_importacion", "mapeos_importacion"}
    sin_origen = sum(1 for t in P5.ORDEN_TABLAS if t not in exentas for k in dm.filas[t] if (t, k) not in destinos)
    tz.update({"R05_origenes": len(ro), "R05_con_disposicion": len(ro & con), "R05_destinos_sin_origen": sin_origen,
               "R05_mapeos_destino_inexistente": sum(1 for (t, k) in destinos if t and k not in dm.filas.get(t, {}))})
    return dm


def ejecutar(dsn: str, run06: Path, decisiones: Path, hash_autorizado: str, r25: dict | None) -> dict:
    import psycopg
    P8 = _cargar("rv3_p8_reconciliacion", "rv3_p8_reconciliacion.py")
    P5 = P8._cargar_p5()
    b0 = P5.fu.cargar_b0(run06)
    ds = P5.transformar(b0, P5.fu.p1.sha256_fichero(run06), modo_lab=False,
                        decisiones=P5.cargar_decisiones(decisiones))
    ev = {"p5_version": P5.VERSION, "hash_dataset": ds.hash(), "hash_autorizado": hash_autorizado}
    if ev["hash_dataset"] != hash_autorizado:
        ev.update(veredicto="NO_SUPERADO", motivo="S7_HASH_DATASET_DISTINTO")
        return ev
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        material = leer_material(P5, c)
        ev["xid_asignado"] = c.execute("SELECT pg_current_xact_id_if_assigned()").fetchone()[0]
        c.rollback()
    ev["filas_materiales"] = sum(len(v) for v in material.values())
    cuant = {}
    ev["igualdad_material"] = comparar_celdas(P5, material, ds, cuant)
    ev["cuantizacion_numeric_fisica"] = cuant  # delta clasificado: redondeo del tipo fisico, dato origen intacto
    dm = dataset_material(P5, material, ds)
    import openpyxl
    wb = openpyxl.load_workbook(run06, read_only=True)
    conteo = {ws.title: sum(1 for i, row in enumerate(ws.iter_rows(values_only=True))
                            if i and any(v not in (None, "") for v in row))
              for ws in wb.worksheets if not ws.title.startswith("00_")}
    res = P8.reconciliar(P5, dm, P5.fu.fuente_b0(b0), conteo)
    r26 = next(r for r in res if r["id"] == "R26")
    if isinstance(r26.get("obtenido"), dict):
        r26["obtenido"]["evidencia_por_origen"] = P8._por_origen(wb, dm)
    if r25 is not None:  # R25 = certificacion P7 (huellas D-111 post-carga)
        i = next(n for n, r in enumerate(res) if r["id"] == "R25")
        res[i] = P8._r("R25", "huellas D-111 identicas pre/post", "identicas", r25,
                       P8.PASS if not r25.get("diferencias") else P8.FAIL, "certificado por P7 sobre la carga P6")
    ev["resultados"] = res
    ev["resumen"] = {e: sum(1 for r in res if r["estado"] == e) for e in (P8.PASS, P8.DELTA, P8.FAIL, P8.PEND)}
    ok = (not ev["igualdad_material"] and ev["xid_asignado"] is None and ev["resumen"][P8.FAIL] == 0
          and ev["resumen"][P8.PEND] == 0)
    ev["veredicto"] = "SUPERADO" if ok else "NO_SUPERADO"
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P8 post-carga: R01..R26 sobre la BD material")
    ap.add_argument("--dsn-auditoria", required=True)
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--hash-autorizado", required=True)
    ap.add_argument("--p7", required=True, type=Path, help="evidencia JSON de P7 (R25)")
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    p7 = json.loads(a.p7.read_text(encoding="utf-8"))
    ev = ejecutar(a.dsn_auditoria, a.run06, a.decisiones_propietario, a.hash_autorizado, p7.get("R25"))
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p8_material.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str),
                                                   encoding="utf-8")
    for r in ev.get("resultados", []):
        print(f"{r['id']} {r['estado']:18s} {r['descripcion']}")
    print(json.dumps({"veredicto": ev["veredicto"], "igualdad_material": ev.get("igualdad_material"),
                      "resumen": ev.get("resumen")}, default=str))
    return 0 if ev["veredicto"] == "SUPERADO" else 1


if __name__ == "__main__":
    sys.exit(main())
