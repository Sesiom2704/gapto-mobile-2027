#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p2_p3_inventario.py
# Ruta: scripts/migration_v3/rv3_p2_p3_inventario.py
# Descripcion: RV3 / P2 (inventario B0), P3 (normalizacion B0 y S1) y
#              continuidad de identidad P4 para registros origen.
#
#   Comprueba contra el canon (Migration V3 v0.40, expediente RV3 v0.2):
#     - 44 hojas / 533 campos / 2.501 filas / 27 con filas / 17 estructurales;
#     - 897 operativos (gastos + gastos_cotidianos + ingresos);
#     - dominios: 7 cuentas, 141 movimientos = 83 transferencias + 58 ajustes,
#       4 prestamos / 889 cuotas, 4 propiedades / 3 compras, 3 contratos /
#       13 participantes, 8 inversiones, 13 cierres / 48 detalles;
#     - regla contextual 141 (RV3-D002-C): 9.287 sentinels + 2 valores reales;
#     - secuencia 1..N de cuotas por prestamo (reconciliacion de 889 cuotas);
#     - identidad: uuid_origen reproduce los 2.501 ids de RUN06;
#     - RV3_SOURCE_JSONCELL_V1 sobre las 2.501 cadenas B0.
#   Mutante contractual TODO_141_A_NULL (en memoria, sin tocar ficheros):
#     transformacion = todo 141 -> desconocido; garantia = 141 contextual;
#     discriminante = reconciliacion 1..N de las 889 cuotas. Debe MORIR.
#
#   Veredictos: P2_P3_OK (exit 0) | STOP (exit 3, S9/S17/S19) | ERROR (exit 2).
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

VERSION = "0.1.0"
_AQUI = Path(__file__).resolve().parent


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


F = _cargar("rv3_fuente")
p1 = F.p1

CANON = {
    "hojas": 44, "campos": 533, "filas_b0": 2501, "hojas_con_filas": 27, "hojas_estructurales": 17,
    "operativos": 897, "cuentas": 7, "movimientos": 141, "transferencias_reales": 83, "ajustes": 58,
    "prestamos": 4, "cuotas": 889, "propiedades": 4, "compras_patrimonio": 3, "contratos": 3,
    "participantes_contrato": 13, "inversiones": 8, "cierres": 13, "detalles_cierre": 48,
    "sentinels_141": 9287, "reales_141": 2,
}
_T0 = time.monotonic()


def log(n, t, m):
    print(f"[{dt.datetime.now():%H:%M:%S}] [paso {n}/{t}] {m}", flush=True)


def reconciliar_cuotas(normalizada: dict) -> dict:
    """R11 (parte cuotas): por prestamo, num_cuota conocido y secuencia exacta 1..N."""
    por_prestamo = {}
    for fila in normalizada.get("public.prestamo_cuota", {}).values():
        pid = str(fila["prestamo_id"].literal)
        por_prestamo.setdefault(pid, []).append(fila["num_cuota"].valor)
    resultado = {}
    for pid, nums in por_prestamo.items():
        try:
            ok = sorted(int(float(x)) for x in nums) == list(range(1, len(nums) + 1))
        except (TypeError, ValueError):
            ok = False
        resultado[pid] = {"cuotas": len(nums), "secuencia_1_N": ok}
    total = sum(v["cuotas"] for v in resultado.values())
    return {"prestamos": resultado, "total": total,
            "ok": total == CANON["cuotas"] and all(v["secuencia_1_N"] for v in resultado.values())}


def inventario(b0: dict, s1: dict) -> dict:
    fb0 = F.fuente_b0(b0)
    estructurales = sorted(h for h, e in s1.items() if not e["filas"] and h not in fb0)
    campos = sum(len(next(iter(t.values())).keys()) for t in fb0.values()) + \
        sum(len(s1[h]["campos"]) for h in estructurales)
    mc = fb0["public.movimientos_cuenta"]
    ajustes = sum(1 for d in mc.values() if str(d.get("cuenta_origen_id")) == str(d.get("cuenta_destino_id")))
    n = lambda c: len(fb0.get(c, {}))  # noqa: E731
    return {
        "hojas": len(fb0) + len(estructurales), "campos": campos,
        "filas_b0": sum(len(t) for t in fb0.values()),
        "hojas_con_filas": len(fb0), "hojas_estructurales": len(estructurales),
        "operativos": n("public.gastos") + n("public.gastos_cotidianos") + n("public.ingresos"),
        "cuentas": n("public.cuentas_bancarias"), "movimientos": len(mc),
        "transferencias_reales": len(mc) - ajustes, "ajustes": ajustes,
        "prestamos": n("public.prestamo"), "cuotas": n("public.prestamo_cuota"),
        "propiedades": n("public.patrimonio"), "compras_patrimonio": n("public.patrimonio_compra"),
        "contratos": n("public.contratos"), "participantes_contrato": n("public.contratos_participantes"),
        "inversiones": n("public.inversion"), "cierres": n("public.cierre_mensual"),
        "detalles_cierre": n("public.cierre_mensual_detalle"),
    }


def estados(normalizada: dict) -> Counter:
    return Counter(c.estado for t in normalizada.values() for f in t.values() for c in f.values())


def mutante_todo_141_a_null(fuente: dict) -> dict:
    original = F._141_es_real
    try:
        F._141_es_real = lambda *a, **k: False
        return reconciliar_cuotas(F.normalizar_fuente(fuente))
    finally:
        F._141_es_real = original


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P2/P3: inventario B0, normalizacion B0/S1")
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    args = ap.parse_args(argv)
    if p1.dentro_de(args.salida, _AQUI.parents[1]):
        print("ERROR: la salida debe quedar FUERA del repositorio", file=sys.stderr)
        return 2
    args.salida.mkdir(parents=True, exist_ok=True)
    T = 6
    log(1, T, "Cargando B0 (RUN06 canonico) y S1 (Sheet)")
    b0 = F.cargar_b0(args.run06)
    s1 = F.cargar_s1(args.sheet)
    fb0, fs1 = F.fuente_b0(b0), F.fuente_s1(s1)

    log(2, T, "P2 inventario B0")
    inv = inventario(b0, s1)
    fallos = [f"{k}: canon {CANON[k]} / obtenido {v}" for k, v in inv.items() if CANON.get(k) != v]

    log(3, T, "P3 normalizacion B0 y S1")
    nb0, ns1 = F.normalizar_fuente(fb0), F.normalizar_fuente(fs1)
    est_b0, est_s1 = estados(nb0), estados(ns1)
    if est_b0[F.AUSENCIA_141] != CANON["sentinels_141"]:
        fallos.append(f"sentinels_141 B0: {est_b0[F.AUSENCIA_141]}")
    if est_b0[F.REAL_141] != CANON["reales_141"] or est_s1[F.REAL_141] != CANON["reales_141"]:
        fallos.append(f"reales_141 B0/S1: {est_b0[F.REAL_141]}/{est_s1[F.REAL_141]}")
    cuotas_b0, cuotas_s1 = reconciliar_cuotas(nb0), reconciliar_cuotas(ns1)
    if not cuotas_b0["ok"]:
        fallos.append("reconciliacion de cuotas B0")
    if not cuotas_s1["ok"]:
        fallos.append("reconciliacion de cuotas S1")

    log(4, T, "P4 continuidad de identidad y RV3_SOURCE_JSONCELL_V1")
    ids_ok = sum(1 for c, t in b0.items() for k, r in t.items() if r.id_run06 == F.uuid_origen(c, k))
    if ids_ok != CANON["filas_b0"]:
        fallos.append(f"uuid_origen reproduce {ids_ok}/{CANON['filas_b0']} ids RUN06")
    hashes = sorted(r.sha256_registro for t in b0.values() for r in t.values())
    colisiones = len(hashes) - len(set(hashes))

    log(5, T, "Mutante TODO_141_A_NULL")
    mut = mutante_todo_141_a_null(fb0)
    veredicto_mut = "MUERTO" if not mut["ok"] else "SUPERVIVIENTE"
    if veredicto_mut != "MUERTO":
        fallos.append("S19: mutante TODO_141_A_NULL sobrevive")

    veredicto = "P2_P3_OK" if not fallos else "STOP"
    informe = {
        "herramienta": "scripts/migration_v3/rv3_p2_p3_inventario.py", "version": VERSION,
        "ejecutado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "veredicto": veredicto, "fallos": fallos, "inventario_b0": inv, "canon": CANON,
        "normalizacion": {"B0": dict(est_b0), "S1": dict(est_s1)},
        "cuotas": {"B0": cuotas_b0, "S1": cuotas_s1},
        "identidad": {"uuid_origen_reproduce_ids_run06": ids_ok,
                      "algoritmo_hash_registro": F.ALGORITMO_HASH_REGISTRO,
                      "semantica_texto": F.SEMANTICA_TEXTO, "colisiones_sha256_registro": colisiones},
        "mutantes": [{"id": "TODO_141_A_NULL", "transformacion": "todo literal 141 -> desconocido",
                      "garantia": "regla contextual 141 (RV3-D002-C)",
                      "discriminante": "reconciliacion 1..N de 889 cuotas", "resultado": veredicto_mut}],
    }
    marca = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.salida / f"rv3_p2_p3_{marca}.json"
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    log(6, T, f"Veredicto: {veredicto}")
    print(f"      inventario: {inv}")
    print(f"      B0: {dict(est_b0)}")
    print(f"      S1: {dict(est_s1)}")
    print(f"      cuotas B0/S1 ok: {cuotas_b0['ok']}/{cuotas_s1['ok']}  mutante TODO_141_A_NULL: {veredicto_mut}")
    for f in fallos:
        print(f"      FALLO: {f}")
    print(f"      informe: {out.name}  sha256={p1.sha256_fichero(out)}  duracion {time.monotonic() - _T0:.1f} s")
    return 0 if veredicto == "P2_P3_OK" else 3


if __name__ == "__main__":
    sys.exit(main())
