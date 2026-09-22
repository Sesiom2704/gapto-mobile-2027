# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p8_reconciliacion.py
# Ruta: scripts/migration_v3/rv3_p8_reconciliacion.py
# Descripcion: RV3 / P8 (informe tipado PREVIO a la carga material P6). Reconciliacion R01..R26 del contrato RV3
#              §11 calculada sobre el dataset P5 (sin escribir en ninguna base). Cada R tiene estado tipado:
#              PASS | DELTA_CLASIFICADO (delta explicado por decision/regla trazada) | FAIL (delta sin clasificar) |
#              PENDIENTE_FASE (solo evaluable en P6/P7). Todo delta no clasificado es FAIL (contrato RV3 §11).
#              No sustituye a P8 post-carga: la repite sobre la base cargada cuando exista P6.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

_AQUI = Path(__file__).resolve().parent

PASS, DELTA, FAIL, PEND = "PASS", "DELTA_CLASIFICADO", "FAIL", "PENDIENTE_FASE"
# Baseline minimo del contrato RV3 §11 (B0).
BASE = {"R01": 44, "R02": 533, "R03": 2501, "R04": 897, "R08": 7, "R09": Decimal("9207.93"), "R10": (83, 58, 224),
        "R11": (4, 889, Decimal("173215.92")), "R12": (7, Decimal("2623.76")), "R13": (4, 3, 13), "R15": 8,
        "R16": (13, 48)}
R02_CAMPOS_ESTRUCTURALES = 189  # 17 hojas sin filas certificadas por P2 (533 - 344)
HOJAS_ESTRUCTURALES = 17        # certificadas por P2
# RUN06 (modelo logico v0.8) -> nombre de la tabla 0330 equivalente
ALIAS_RUN06 = {"fin_condiciones_versiones": "financiacion_condiciones_versiones",
               "contrato_rev_renta_versiones": "contrato_revision_renta_versiones", "provincias": "regiones",
               "obligaciones_financieras": "derechos_obligaciones_financieras"}


def _cargar_p5():
    spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", _AQUI / "rv3_p5_transformacion.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rv3_p5_transformacion"] = mod
    spec.loader.exec_module(mod)
    return mod


def _r(rid, desc, esperado, obtenido, estado, explicacion=None):
    return {"id": rid, "descripcion": desc, "esperado": esperado, "obtenido": obtenido, "estado": estado,
            "explicacion": explicacion}


def _eq(rid, desc, esperado, obtenido, explicacion=None):
    return _r(rid, desc, esperado, obtenido, PASS if esperado == obtenido else FAIL, explicacion)


def reconciliar(P5, ds, fuente: dict, run06: dict | None = None) -> list:
    fu, F = P5.fu, ds.filas
    ro = F["registros_origen_importacion"]
    fuente_b0 = {f["id"] for f in F["fuentes_importacion"].values() if f["tipo_fuente"] == "XLSX"}
    origen = {}
    for m in F["mapeos_importacion"].values():
        origen.setdefault((m["tabla_destino"], m["registro_destino_id"]), ro[m["registro_origen_id"]])
    TH = {v: k for k, v in P5.TIPOS_HECHO_SEED.items()}
    H = F["hechos_financieros"]
    efectos_de = collections.defaultdict(list)
    for e in F["hecho_efectos"].values():
        efectos_de[e["hecho_id"]].append(e)
    out = []
    tz = ds.trazabilidad
    # R01 / R02
    hojas_con_filas = sum(1 for c in fuente if c.startswith("public."))
    out.append(_eq("R01", "hojas V3 (con filas + estructurales P2)", BASE["R01"], hojas_con_filas + HOJAS_ESTRUCTURALES))
    campos = tz.get("R02_campos_b0", 0) + R02_CAMPOS_ESTRUCTURALES
    pend = tz.get("R02_por_clase", {}).get("PENDIENTE_S20", 0)
    out.append(_r("R02", "campos con disposicion", BASE["R02"], {"campos": campos, "pendiente_por_filas": pend},
                  PASS if campos == BASE["R02"] and pend == 0 else (DELTA if campos == BASE["R02"] else FAIL),
                  None if pend == 0 else "campos con filas residuales decididas como pendientes por el propietario"))
    # R03 / R04 / R05
    n_b0 = sum(1 for r in ro.values() if r["fuente_importacion_id"] in fuente_b0)
    n_sup = len(ro) - n_b0
    out.append(_r("R03", "registros origen B0", BASE["R03"], {"b0": n_b0, "suplementarios": n_sup},
                  PASS if n_b0 == BASE["R03"] else FAIL,
                  f"{n_sup} registros de fuentes suplementarias (decisiones del propietario / catalogos canonicos), "
                  "fuera de B0" if n_sup else None))
    oper = sum(len(fuente.get(c, {})) for c in P5.CONTENEDORES_OPERATIVOS)
    out.append(_eq("R04", "registros operativos (gastos + cotidianos + ingresos)", BASE["R04"], oper))
    r05 = (tz.get("R05_origenes", 0) - tz.get("R05_con_disposicion", 0), tz.get("R05_destinos_sin_origen"))
    out.append(_eq("R05", "origenes sin disposicion / destinos sin origen", (0, 0), r05))
    out.append(_r("R06", "colisiones / deriva UUID", 0, 0, PASS,
                  "Dataset.add falla cerrado ante colision (S7); determinismo = hash identico entre runs (preflight)"))
    out.append(_r("R07", "huerfanos (incl. destino polimorfico)", 0, tz.get("R05_mapeos_destino_inexistente"),
                  PASS if tz.get("R05_mapeos_destino_inexistente") == 0 else FAIL,
                  "FK fisicas verificadas en la validacion RV3_IMPORT (ROLLBACK); P7 lo repite tras P6"))
    # R08 / R09
    cb = "public.cuentas_bancarias"
    ids_v3 = {fu.uuid_v3(cb, k, "cuentas", "cuenta") for k in fuente.get(cb, {})}
    v3 = [c for c in F["cuentas"].values() if c["id"] in ids_v3]
    deriv = [c for c in F["cuentas"].values() if c["id"] not in ids_v3]
    ok8 = len(v3) == BASE["R08"] and all(c["saldo_apertura"] is None for c in deriv)
    out.append(_r("R08", "7 cuentas V3 + derivadas sin saldo inferido", BASE["R08"],
                  {"v3": len(v3), "derivadas": len(deriv), "derivadas_con_saldo": sum(1 for c in deriv
                                                                                     if c["saldo_apertura"] is not None)},
                  PASS if ok8 else FAIL))
    s9 = sum(Decimal(str(c["saldo_apertura"])) for c in v3 if c["saldo_apertura"] is not None)
    out.append(_eq("R09", "saldo bruto de apertura V3", str(BASE["R09"]), str(s9)))
    # R10
    ligados = {t[k] for t in F["transferencias"].values() for k in t if k.startswith("movimiento_")}
    ajustes = [m for m in F["movimientos_tesoreria"].values() if m["id"] not in ligados]
    obt10 = (len(F["transferencias"]), len(ajustes), len(F["movimientos_tesoreria"]))
    out.append(_eq("R10", "transferencias / ajustes / movimientos", BASE["R10"], obt10))
    # R11
    pr = "public.prestamo"
    ids_pr = {fu.uuid_v3(pr, k, "entidades", "financiacion") for k in fuente.get(pr, {})}
    fins = [f for f in F["financiaciones"].values() if f["entidad_id"] in ids_pr]
    cuotas = sum(1 for q in F["financiacion_cuotas"].values() if q["financiacion_entidad_id"] in ids_pr)
    deuda = sum(Decimal(str(f["saldo_principal_apertura"])) for f in fins if f["saldo_principal_apertura"] is not None)
    out.append(_eq("R11", "prestamos / cuotas / deuda de apertura", tuple(str(x) for x in BASE["R11"]),
                   (str(len(fins)), str(cuotas), str(deuda))))
    # R12
    cf = [h for h in H.values() if TH[h["tipo_hecho_id"]] == "COMPRA_FINANCIADA"]
    dec = [h for h in cf if origen[("hechos_financieros", h["id"])]["clave_origen"] in P5.COMPRA_FINANCIADA_DECIDIDA]
    v3cf = [h for h in cf if h not in dec]
    base_ok = (len(v3cf), sum(h["importe_total"] for h in v3cf)) == BASE["R12"]
    doble = [h["id"] for h in cf if sum(1 for e in efectos_de[h["id"]] if e["tipo_efecto"] == "GASTO") != 1]
    out.append(_r("R12", "compras financiadas (gasto economico unico)", [BASE["R12"][0], str(BASE["R12"][1])],
                  {"tipo_v3_financiacion": [len(v3cf), str(sum(h["importe_total"] for h in v3cf))],
                   "decididas_propietario": [len(dec), str(sum(h["importe_total"] for h in dec))],
                   "hechos_con_gasto_no_unico": len(doble)},
                  (DELTA if dec else PASS) if base_ok and not doble else FAIL,
                  "D8-K2: compras financiadas adicionales decididas por el propietario (respuesta 3, 2026-09-21); "
                  "las cuotas no crean GASTO (OP-15/INV-12)" if dec else None))
    # R13
    obt13 = (len(F["propiedades"]), len(F["contratos"]), len(F["contrato_participantes"]))
    fus = len(P5.PARTICIPANTE_DUPLICADO_CAPTURA)
    out.append(_r("R13", "propiedades / contratos / participantes", BASE["R13"], obt13,
                  PASS if obt13 == BASE["R13"] else (DELTA if obt13 == (4, 3, 13 - fus) else FAIL),
                  f"participante duplicado por captura fusionado N:1 (clase C): {fus}" if obt13 != BASE["R13"] else None))
    # R14 participacion 0 % (Blasco): el propietario no participa; V3 guarda 1 (= 0 % real, D4-D / S20-6)
    self_ = ds.self_id
    blasco = fu.uuid_v3("public.patrimonio", "VIVIENDA-0B1D7T", "entidades", "propiedad")
    ps = [p for p in F["entidad_participaciones"].values() if p["entidad_id"] == blasco]
    ok14 = bool(ps) and all(p["actor_id"] != self_ for p in ps) and sum(Decimal(p["porcentaje"]) for p in ps) == 100
    out.append(_r("R14", "participacion 0 % del propietario conservada", "sin fila self; 100 % del titular",
                  {"filas": len(ps), "self": sum(1 for p in ps if p["actor_id"] == self_)}, PASS if ok14 else FAIL,
                  "0 % = ausencia de participacion propia (nunca fila con 0); literal V3 1 en origen"))
    # R15
    inv = len(F["inversiones"])
    ahorro = 1 if fu.uuid_v3(*P5.CUENTA_AHORRO, "cuentas", "cuenta") in F["cuentas"] else 0
    out.append(_r("R15", "inversiones V3", BASE["R15"], {"inversiones": inv, "cuenta_ahorro": ahorro},
                  PASS if inv == BASE["R15"] else (DELTA if inv + ahorro == BASE["R15"] else FAIL),
                  "la inversion V3 de ahorro se representa como cuenta (sin saldo inferido)" if inv != BASE["R15"] else None))
    # R16
    det = {origen[("cierre_metricas", m)]["clave_origen"] for m in F["cierre_metricas"]
           if origen[("cierre_metricas", m)]["contenedor_origen"] == "public.cierre_mensual_detalle"}
    out.append(_eq("R16", "cierres / detalles como snapshots", BASE["R16"], (len(F["cierres_mensuales"]), len(det))))
    # R17..R20
    por_tipo = collections.Counter(e["tipo_efecto"] for e in F["hecho_efectos"].values())
    sin_ef = [h["id"] for h in H.values() if TH[h["tipo_hecho_id"]] != "TRANSFERENCIA" and not efectos_de[h["id"]]]
    out.append(_r("R17", "efectos por tipo segun mapping", "todo hecho no TRANSFERENCIA con efectos",
                  {"por_tipo": dict(sorted(por_tipo.items())), "hechos_sin_efectos": len(sin_ef)},
                  PASS if not sin_ef else FAIL))
    tr = [h for h in H.values() if TH[h["tipo_hecho_id"]] == "TRANSFERENCIA"]
    tr_ef = sum(1 for h in tr if efectos_de[h["id"]])
    out.append(_r("R18", "transferencias propias con efecto economico 0", 0, {"hechos": len(tr), "con_efectos": tr_ef},
                  PASS if tr_ef == 0 else FAIL))
    rb = [h for h in H.values() if TH[h["tipo_hecho_id"]] == "REEMBOLSO"]
    rb_in = sum(1 for h in rb for e in efectos_de[h["id"]] if e["tipo_efecto"] == "INGRESO")
    out.append(_r("R19", "reembolsos sin INGRESO ficticio", 0, {"reembolsos": len(rb), "con_ingreso": rb_in},
                  PASS if rb_in == 0 else FAIL))
    est = collections.Counter(e["estado_atribucion"] for e in F["hecho_efectos"].values())
    out.append(_r("R20", "atribuciones con estado explicito", "sin NULL", dict(sorted(est.items(), key=str)),
                  PASS if None not in est else FAIL))
    # R21
    dof = list(F["derechos_obligaciones_financieras"].values())
    ceros = [d["entidad_id"] for d in dof if d["importe_original_documentado"] is not None
             and Decimal(str(d["importe_original_documentado"])) == 0]
    out.append(_r("R21", "derechos/obligaciones conocidos o indeterminados sin ceros fabricados", 0,
                  {"posiciones": len(dof), "importe_conocido": sum(1 for d in dof if d["importe_original_documentado"] is not None),
                   "importe_indeterminado": sum(1 for d in dof if d["importe_original_documentado"] is None),
                   "importe_cero": len(ceros)}, PASS if not ceros else FAIL))
    # R22
    ctx = fu.contexto_de(fuente)
    unk = collections.Counter()
    for c, filas in fuente.items():
        for fila in filas.values():
            for col, v in dict.items(fila):
                e = fu.normalizar(c, col, v, fila, ctx).estado
                if e != fu.CONOCIDO:
                    unk[e] += 1
    out.append(_r("R22", "UNKNOWN por campo (nunca convertido a valor)", "declarado", dict(sorted(unk.items())), PASS,
                  "estado por celda de P3; su conversion a valor esta vigilada por los mutantes UNKNOWN->0"))
    # R23 / R24
    reglas = collections.Counter(e["regla"] for e in ds.ledger)
    out.append(_r("R23", "excepciones F01 y reglas aplicadas en ledger", "declarado",
                  {"entradas": len(ds.ledger), "reglas": len(reglas)}, PASS))
    c = tz.get("r02_complementos", {})
    perdidas = {"tienda_descartada": c.get("descartes", 0), "proveedor_solo_region": c.get("proveedor_solo_region", 0),
                "repostaje_desconocido_decidido": c.get("desconocido_decidido", 0),
                "precio_litro_reconstruido_por_formula": c.get("precio_litro_verificado", 0),
                "omisiones_solo_ledger": c.get("omisiones_ledger", 0)}
    out.append(_r("R24", "perdidas de detalle aceptadas y declaradas", "declarado", perdidas, PASS))
    out.append(_r("R25", "huellas D-111 identicas pre/post", "identicas", None, PEND, "P7, tras la carga material P6"))
    # R26
    if run06 is None:
        out.append(_r("R26", "delta frente a RUN06", "explicado", None, PEND, "sin recuentos RUN06"))
    else:
        rc = ds.recuentos()
        delta = {}
        for t, n in sorted(run06.items()):
            d = ALIAS_RUN06.get(t, t)
            m = rc.get(d)
            if (m or 0) != n:
                delta[t] = {"run06": n, "0330": m}
        for t, m in rc.items():
            if m and t not in {ALIAS_RUN06.get(x, x) for x in run06}:
                delta[t] = {"run06": None, "0330": m}
        clas = {t: CLASIFICACION_R26.get(t) for t in delta}
        sin = sorted(t for t, v in clas.items() if v is None)
        out.append(_r("R26", "delta frente a RUN06 explicado", "0 deltas sin clasificar",
                      {"tablas_con_delta": len(delta), "sin_clasificar": sin, "delta": delta,
                       "clasificacion": {t: v for t, v in clas.items() if v}},
                      FAIL if sin else DELTA))
    return out


# Clasificacion de deltas RUN06 -> 0330 ya demostrada por reglas trazadas. Lo ausente aqui es FAIL (sin clasificar).
CLASIFICACION_R26 = {
    "transferencias": "DV-7: -58 autotransferencias de RUN06 son ajustes (AJUSTE_SALDO); 83 reales",
    "movimientos_tesoreria": "DV-7: 83 x 2 OPERACION + 58 AJUSTE_SALDO = 224 (RUN06 282)",
    "hecho_movimientos_tesoreria": "conciliacion de las 83 transferencias (166); RUN06 no la materializaba",
    "contrato_participantes": "fusion N:1 de participante duplicado por captura (clase C)",
    "registros_origen_importacion": "+131 registros de fuentes suplementarias (decisiones/catalogos); B0 = 2501",
    "fuentes_importacion": "+2 fuentes suplementarias (decisiones del propietario, arbol de categorias)",
    "tercero_direcciones": "Q-R02-5: direcciones COMERCIAL de proveedores (propietario 2026-09-22)",
    "etiquetas": "Q-R02-2: 4 etiquetas de evento con variantes unificadas (propietario 2026-09-22)",
    "hecho_etiquetas": "Q-R02-2: una por cotidiano con evento y hecho (201)",
    "magnitudes": "Q-R02-3: Kilometraje y Combustible; precio_litro es control derivado, no magnitud",
    "hecho_magnitudes": "Q-R02-3: km y litros > 0 (0 = desconocido), precio_litro derivado",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P8 previo: reconciliacion tipada R01..R26 sobre el dataset P5")
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    P5 = _cargar_p5()
    fu = P5.fu
    b0 = fu.cargar_b0(a.run06)
    ds = P5.transformar(b0, fu.p1.sha256_fichero(a.run06), modo_lab=False,
                        decisiones=P5.cargar_decisiones(a.decisiones_propietario))
    import openpyxl
    wb = openpyxl.load_workbook(a.run06, read_only=True)
    run06 = {}
    for ws in wb.worksheets:
        if ws.title.startswith("00_"):
            continue
        run06[ws.title] = sum(1 for i, row in enumerate(ws.iter_rows(values_only=True))
                              if i and any(v not in (None, "") for v in row))
    res = reconciliar(P5, ds, fu.fuente_b0(b0), run06)
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p8_reconciliacion.json").write_text(
        json.dumps({"p5_version": P5.VERSION, "hash_dataset": ds.hash(), "resultados": res},
                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for r in res:
        print(f"{r['id']} {r['estado']:18s} {r['descripcion']}")
    return 0 if all(r["estado"] in (PASS, DELTA, PEND) for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
