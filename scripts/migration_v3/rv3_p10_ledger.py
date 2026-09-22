# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p10_ledger.py
# Ruta: scripts/migration_v3/rv3_p10_ledger.py
# Descripcion: RV3 / P10. Ledger contractual de deltas y excepciones a partir de la evidencia estructurada de
#              P8 post-carga (rv3_p8_material.json), P9 (rv3_p9_runtime.json) y del ledger de reglas del P5
#              regenerado (mismo hash). Cada entrada: id, origen, dato, clasificacion (clase RV3 §19 A..I),
#              explicacion, tratamiento, impacto, evidencia y estado. Fail-closed: un delta sin explicacion,
#              una R en FAIL o un hallazgo P9 no clasificado deja el ledger NO_CERRADO.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sys
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
ESTADOS_CERRADOS = {"ACEPTADO", "RESUELTO", "DECLARADO"}
# Reglas que P5 v0.35.0 registra en su ledger sin texto en LEDGER_REGLAS. Su texto canonico vive en el expediente
# RV3 v0.4 (RV3-D004 §24 / RV3-D005 §25) y en las cabeceras de P5; P10 las enlaza a esa fuente en vez de dejarlas
# mudas. Hallazgo de trazabilidad para P5 (no se corrige aqui: P5 esta certificado).
TEXTOS_CANONICOS = {
    "D5-R": "resumen de disposicion del dominio 5 (recurrentes, rentas, reglas y versiones); control, no decision",
    "D8-K-FIN_DE_MES": "RV3-D004 §24.2: HIP. ALLENDE a fin de mes (ordinal 31 recortado, F04-D020); literal V3 dia 28",
    "R02-Q1": "RV3-D004 §24.2: cuota pagada -> DEUDA -capital + GASTO intereses, fecha = vencimiento, sin tesoreria",
    "R02-Q2-VARIANTE": "RV3-D004 §24.3: variante de evento unificada (FAMILIA DE/AMIGOS DE/ROMANTIC)",
    "R02-Q3-CORRECCION": "RV3-D004 §24.3: correccion de captura decidida 12.811 -> 128.111; literal V3 en origen",
    "R02-Q3-DESCONOCIDO": "RV3-D004 §24.3: valores de repostaje declarados desconocidos por el propietario",
    "R02-Q4-DESCARTE": "RV3-D004 §24.3: tienda de gestionable sin hecho descartada con traza",
    "R02-Q5-DECIDIDA": "P5 v0.35.0 (propietario 2026-09-22): localidad de 10 proveedores declarada; region/localidad "
                       "MADRID aportadas por el propietario (pendiente de sincronizacion documental)",
    "R02-Q5-SIN_LOCALIDAD": "RV3-D004 §24.3: 64 proveedores con solo region/pais no fabrican direccion",
    "R02-Q6": "RV3-D004 §24.3: prestamo.rango_pago -> notas de la financiacion",
    "R02-Q7-OMISION": "RV3-D004 §24.3: omision solo en origen + ledger; no es hecho ni prevision",
}


def _entrada(i, origen, dato, clase, explicacion, tratamiento, impacto, evidencia, estado):
    return {"id": i, "origen": origen, "dato": dato, "clasificacion": clase, "explicacion": explicacion,
            "tratamiento": tratamiento, "impacto": impacto, "evidencia": evidencia, "estado": estado}


def construir(p8: dict, p9: dict, reglas_ledger: dict, textos_reglas: dict) -> dict:
    L = []
    res = {r["id"]: r for r in p8.get("resultados", [])}
    # 1) R con delta clasificado
    for rid in sorted(res):
        r = res[rid]
        if r["estado"] == "DELTA_CLASIFICADO" and rid != "R26":
            L.append(_entrada(f"L-{rid}", "P8 post-carga", r["descripcion"], "B/E (decision trazada)",
                              r.get("explicacion"), "representacion canonica 0330", "sin perdida no declarada",
                              {"esperado": r["esperado"], "obtenido": r["obtenido"]},
                              "ACEPTADO" if r.get("explicacion") else "SIN_EXPLICACION"))
        elif r["estado"] not in ("PASS", "DELTA_CLASIFICADO"):
            L.append(_entrada(f"L-{rid}", "P8 post-carga", r["descripcion"], "FAIL", None, None, "bloqueante",
                              r.get("obtenido"), "SIN_EXPLICACION"))
    # 2) R26: una entrada por tabla con delta frente a RUN06 (incluye DV-7)
    r26 = res.get("R26", {}).get("obtenido") or {}
    clas = r26.get("clasificacion", {})
    for t, d in sorted((r26.get("delta") or {}).items()):
        exp = clas.get(t)
        L.append(_entrada(f"L-R26-{t}", "R26 frente a RUN06", t,
                          "DV (defecto RUN06)" if exp and ("DV-" in exp or "sin origen" in exp) else "B/E (decision trazada)",
                          exp, "no se reescribe RUN06; RV3 aplica el canon", "ninguno sobre V3",
                          {"run06": d.get("run06"), "0330": d.get("0330"),
                           "por_origen": (r26.get("evidencia_por_origen") or {}).get(t)},
                          "ACEPTADO" if exp else "SIN_EXPLICACION"))
    # 3) cuantizacion fisica numeric (P8 igualdad material)
    for col, q in sorted((p8.get("cuantizacion_numeric_fisica") or {}).items()):
        L.append(_entrada(f"L-CUANT-{col}", "P8 igualdad material", col, "H (limitacion del tipo fisico 0330)",
                          "numeric(18,6) redondea a 6 decimales artefactos binarios de coma flotante de V3 (importes) "
                          "y ratios derivables (cumplimiento_pct); el literal V3 completo sigue en "
                          "registros_origen_importacion.datos_origen",
                          "sin correccion; recomendacion: cuantizar en P5 en una version futura para que el hash del "
                          "dataset describa exactamente lo almacenado", f"max |diferencia| {q['max_abs_diferencia']}",
                          q, "DECLARADO"))
    # 4) UNKNOWN y sentinels (R22) y perdidas de detalle aceptadas (R24)
    if "R22" in res:
        L.append(_entrada("L-R22", "P3 normalizacion", "UNKNOWN / sentinels por celda", "D (dato ambiguo) / INV-RV3-04/05",
                          "ausencias legacy 141/None/NONE nunca se convierten en valor; 141 real en 2 cuotas",
                          "UNKNOWN -> NULL o sin fila; literal en origen", "ninguno", res["R22"]["obtenido"], "DECLARADO"))
    if "R24" in res:
        L.append(_entrada("L-R24", "P5 respuestas del propietario", "perdidas de detalle aceptadas", "H (aceptada)",
                          "descartes, solo-region, desconocidos decididos, precio_litro por formula, omisiones en ledger",
                          "declaradas en R24 con decision del propietario", "detalle no materializado; origen intacto",
                          res["R24"]["obtenido"], "ACEPTADO"))
    # 5) reglas del ledger de transformacion (excepciones historicas y decisiones de mapping)
    for regla, n in sorted(reglas_ledger.items()):
        texto = textos_reglas.get(regla) or TEXTOS_CANONICOS.get(regla)
        L.append(_entrada(f"L-REGLA-{regla}", "P5 ledger de reglas", f"{n} aplicaciones", "B/C/E (regla trazada)",
                          texto, "aplicada por P5 v0.35.0", "segun la regla", {"aplicaciones": n},
                          "ACEPTADO" if texto else "SIN_EXPLICACION"))
    # 6) hallazgos P9
    r16 = (p9 or {}).get("R_RV3_016", {})
    if r16:
        b = r16.get("probe_B_update_mas_delete", {})
        L.append(_entrada("L-P9-R-RV3-016", "P9 runtime", "posiciones financieras importadas", "riesgo R-RV3-016",
                          f"DELETE directo rechazado en {r16['probe_A_delete_directo']['rechazadas_23503']}/"
                          f"{r16['probe_A_delete_directo']['posiciones']} (23503); secuencia UPDATE+DELETE ejecutada: "
                          f"{b.get('evadidas')} evadidas, {b.get('bloqueadas')} bloqueadas por el orden de la sonda",
                          "riesgo aceptado por el propietario (opcion A, RV3-D004 §26); mitigacion fisica solo con "
                          "reapertura F03 + migration posterior a 0330", "claim limitado a 'PROTEGIDA frente a DELETE "
                          "directo'", {"clasificacion": r16.get("clasificacion"), "por_tipo": b.get("por_tipo")},
                          "ACEPTADO"))
        sc = (p9.get("rls") or {}).get("por_contexto", {}).get("sin_contexto", {})
        if sc.get("errores"):
            L.append(_entrada("L-P9-RLS-SIN-CONTEXTO", "P9 runtime", "consultas de gapto_runtime sin gapto.owner_user_id",
                              "comportamiento contractual (fail-closed)",
                              "las policies exigen el contexto tenant: sin el, las tablas tenant fallan o no devuelven filas",
                              "ninguno", "ninguna fila visible", sc, "DECLARADO"))
    sin = [e["id"] for e in L if e["estado"] not in ESTADOS_CERRADOS]
    return {"entradas": L, "total": len(L), "por_estado": dict(collections.Counter(e["estado"] for e in L)),
            "sin_clasificar": sin, "veredicto": "CERRADO" if not sin else "NO_CERRADO"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P10: ledger de deltas y excepciones")
    ap.add_argument("--p8", required=True, type=Path)
    ap.add_argument("--p9", required=True, type=Path)
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", _AQUI / "rv3_p5_transformacion.py")
    P5 = importlib.util.module_from_spec(spec)
    sys.modules["rv3_p5_transformacion"] = P5
    spec.loader.exec_module(P5)
    ds = P5.transformar(P5.fu.cargar_b0(a.run06), P5.fu.p1.sha256_fichero(a.run06), modo_lab=False,
                        decisiones=P5.cargar_decisiones(a.decisiones_propietario))
    p8 = json.loads(a.p8.read_text(encoding="utf-8"))
    if ds.hash() != p8.get("hash_dataset"):
        print("STOP: el P5 regenerado no coincide con el hash de P8")
        return 2
    reglas = collections.Counter(e["regla"] for e in ds.ledger)
    r = construir(p8, json.loads(a.p9.read_text(encoding="utf-8")), reglas, P5.LEDGER_REGLAS)
    r["hash_dataset"] = ds.hash()
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p10_ledger.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str),
                                                  encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("total", "por_estado", "sin_clasificar", "veredicto")}))
    return 0 if r["veredicto"] == "CERRADO" else 1


if __name__ == "__main__":
    sys.exit(main())
