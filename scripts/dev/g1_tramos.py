# ============================================================
# GAPTO MOBILE 2027
# Fichero: g1_tramos.py
# Ruta: scripts/dev/g1_tramos.py
# Descripcion: Parser de ejemplo de las lineas [G1] v2 (instrumentacion por
#   paso, solo __DEV__, de mobile/src/dev/g1.ts). Fuera del producto: lee la
#   salida de Metro (fichero o stdin), agrupa por ensayo (sesion, seq) y saca,
#   por ensayo, el tiempo de cada tramo (desde el hito anterior hasta el hito
#   del tramo, en orden cronologico), el tiempo dentro del selector, las
#   interrupciones (app en segundo plano o inactiva), el tiempo con teclado,
#   los desplazamientos, el D1 observado y el numero de pantallas.
#   D1 observado = decisiones tocadas en el ensayo, con la misma regla que el
#   D1 del guion G1: acceso de plantilla (1), cada eleccion de tipo, de
#   tercero, de presupuesto y de cuenta (tambien desde/a de una
#   transferencia), y en categoria cada nivel en el que se entra mas la
#   eleccion final (Movilidad > Combustible = 2; chip o «Sin categoria» = 1).
#   No cuenta el importe, las magnitudes, «No lo se» ni «Registrar». Las
#   correcciones (elegir dos veces) cuentan: es lo observado, no lo previsto.
#   Las lineas v1 (sin pasos) se aceptan con los tramos vacios.
#   Uso: python scripts/dev/g1_tramos.py lineas_metro.txt [--csv salida.csv] [--md salida.md]
#        python scripts/dev/g1_tramos.py --autoprueba
# Version: 0.1.0 (F05-D051 paso 9.1 · G1 v2, instrumentacion por paso)
# ============================================================

from __future__ import annotations

import csv
import io
import json
import re
import sys

LINEA = re.compile(r"\[G1\] (\{.*\})\s*$")

#: hito -> nombre del tramo que termina en el (el ultimo evento de cada tipo manda).
HITOS = (
    ("importe", ("importe_ult_cambio", "importe_1er_cambio")),
    ("tercero", ("tercero_elegido", "tercero_ninguno")),
    ("categoria", ("categoria_elegida",)),
    ("magnitud", ("magnitud_ult_cambio", "magnitud_1er_cambio", "no_lo_se")),
    ("presupuesto", ("presupuesto_elegido",)),
    ("cuenta", ("cuenta_elegida", "cuenta_desde_elegida", "cuenta_a_elegida")),
    ("registrar", ("registrar_pulsado",)),
)
DECISIONES = ("tercero_elegido", "tercero_ninguno", "selector_nivel", "categoria_elegida",
              "presupuesto_elegido", "cuenta_elegida", "cuenta_desde_elegida", "cuenta_a_elegida")
PANTALLAS = ("hoja_tipos", "selector_abierto", "tercero_abierto")
COLUMNAS = ["sesion", "seq", "origen", "resultado", "ruta", "hecho_id", "ms_total", "ms_neto",
            "form_montado", "carga"] + [f"tramo_{n}" for n, _ in HITOS] + [
            "respuesta", "dentro_selector", "via_categoria", "niveles_categoria", "interrupciones",
            "ms_interrumpido", "ms_teclado", "scroll_n", "scroll_ms", "d1_observado", "pantallas",
            "pasos", "pasos_omitidos"]


def leer(texto: str) -> list[dict]:
    """Ensayos en el orden de las lineas. Se ignora todo lo que no es una linea [G1]."""
    out = []
    for linea in texto.splitlines():
        m = LINEA.search(linea)
        if m:
            out.append(json.loads(m[1]))
    return out


def _ultimo(pasos: list[dict], nombres: tuple[str, ...]) -> float | None:
    ms = [p["ms"] for p in pasos if p["e"] in nombres]
    return max(ms) if ms else None


def _intervalos(pasos: list[dict], abre, cierra, fin: float) -> tuple[int, float]:
    """Numero y suma de intervalos [abre, cierra); uno abierto al final se cierra en `fin`."""
    n, total, desde = 0, 0.0, None
    for p in pasos:
        if desde is None and abre(p["e"]):
            desde = p["ms"]
            n += 1
        elif desde is not None and cierra(p["e"]):
            total += p["ms"] - desde
            desde = None
    if desde is not None:
        total += fin - desde
    return n, round(total, 1)


def tramos(ensayo: dict) -> dict:
    pasos = sorted(ensayo.get("pasos") or [], key=lambda p: p["ms"])
    fin = ensayo.get("ms")
    r = {k: ensayo.get(k) for k in ("sesion", "seq", "origen", "resultado", "ruta", "hecho_id")}
    r["ms_total"] = fin
    r["pasos"] = len(pasos)
    r["pasos_omitidos"] = ensayo.get("pasos_omitidos", 0)
    if not pasos:
        return r
    form = _ultimo(pasos, ("form_montado",))
    r["form_montado"] = form
    cargas = [_ultimo(pasos, (e,)) for e in ("arbol_ok", "cuentas_ok")]
    cargas = [x for x in cargas if x is not None]
    if form is not None and cargas:
        r["carga"] = round(max(cargas) - form, 1)
    # Tramos: hitos en orden cronologico; cada uno mide desde el anterior (o desde form_montado / t0).
    hitos = sorted(((n, t) for n, ev in HITOS if (t := _ultimo(pasos, ev)) is not None), key=lambda x: x[1])
    previo = form if form is not None else 0.0
    for nombre, t in hitos:
        r[f"tramo_{nombre}"] = round(t - previo, 1)
        previo = t
    reg = _ultimo(pasos, ("registrar_pulsado",))
    if reg is not None and fin is not None and ensayo.get("resultado") != "ABANDONADO":
        r["respuesta"] = round(fin - reg, 1)
    fin_ref = fin if fin is not None else pasos[-1]["ms"]
    _, r["dentro_selector"] = _intervalos(pasos, lambda e: e == "selector_abierto",
                                          lambda e: e in ("categoria_elegida", "selector_cerrado"), fin_ref)
    elegidas = [p for p in pasos if p["e"] == "categoria_elegida"]
    if elegidas:
        r["via_categoria"] = elegidas[-1].get("via")
        r["niveles_categoria"] = elegidas[-1].get("n")
    r["interrupciones"], r["ms_interrumpido"] = _intervalos(
        pasos, lambda e: e in ("app_estado:background", "app_estado:inactive"), lambda e: e == "app_estado:active", fin_ref)
    _, r["ms_teclado"] = _intervalos(pasos, lambda e: e == "teclado_on", lambda e: e == "teclado_off", fin_ref)
    r["scroll_n"], r["scroll_ms"] = _intervalos(pasos, lambda e: e == "scroll_ini", lambda e: e == "scroll_fin", fin_ref)
    if fin is not None:
        r["ms_neto"] = round(fin - r["ms_interrumpido"], 1)
    d1 = 1 if ensayo.get("origen") == "inicio:plantilla" else 0
    d1 += sum(1 for p in pasos if p["e"].startswith("tipo:") or p["e"] in DECISIONES)
    r["d1_observado"] = d1
    r["pantallas"] = 1 + sum(1 for p in pasos if p["e"] in PANTALLAS)
    return r


def a_csv(filas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNAS, lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow({k: ("" if f.get(k) is None else f.get(k)) for k in COLUMNAS})
    return buf.getvalue()


def a_md(filas: list[dict]) -> str:
    cols = ["seq", "origen", "resultado", "ms_total", "ms_neto", "carga"] + [f"tramo_{n}" for n, _ in HITOS] + [
        "respuesta", "dentro_selector", "via_categoria", "interrupciones", "ms_interrumpido", "d1_observado", "pantallas"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for f in filas:
        out.append("| " + " | ".join("" if f.get(k) is None else str(f.get(k)) for k in cols) + " |")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ autoprueba (lineas sinteticas)
def _linea(d: dict) -> str:
    return " LOG  [G1] " + json.dumps(d, ensure_ascii=False)


SINTETICAS = "\n".join([
    "ruido de Metro sin marca",
    # Caso 5: Registrar > Gasto > importe > Movilidad > Combustible > Litros > Presupuesto > Cuenta, con una
    # interrupcion (app en segundo plano 30 s) y teclado.
    _linea({"v": 2, "sesion": 1792918000000, "seq": 1, "origen": "inicio:registrar", "ruta": "/v1/intenciones/gasto-pagado",
            "status": 200, "ok": True, "intencion_id": "i-1", "hecho_id": "h-1", "resultado": "CONFIRMADO", "ms": 60000.0,
            "pasos": [
                {"e": "hoja_tipos", "ms": 5.0}, {"e": "tipo:GASTO", "ms": 900.0},
                {"e": "form_montado", "ms": 1000.0, "via": "GASTO"}, {"e": "teclado_on", "ms": 1100.0},
                {"e": "arbol_ok", "ms": 1400.0}, {"e": "cuentas_ok", "ms": 1600.0, "n": 2},
                {"e": "importe_1er_cambio", "ms": 2000.0}, {"e": "importe_ult_cambio", "ms": 3000.0},
                {"e": "selector_abierto", "ms": 4000.0}, {"e": "teclado_off", "ms": 4100.0},
                {"e": "selector_nivel", "ms": 5000.0, "n": 1},
                {"e": "categoria_elegida", "ms": 6000.0, "via": "arbol", "n": 2},
                {"e": "magnitudes_visibles", "ms": 6100.0, "n": 1},
                {"e": "app_estado:inactive", "ms": 7000.0}, {"e": "app_estado:background", "ms": 7100.0},
                {"e": "app_estado:active", "ms": 37000.0},
                {"e": "scroll_ini", "ms": 38000.0}, {"e": "scroll_fin", "ms": 38500.0},
                {"e": "presupuesto_elegido", "ms": 40000.0}, {"e": "cuenta_elegida", "ms": 42000.0},
                {"e": "scroll_ini", "ms": 43000.0}, {"e": "scroll_fin", "ms": 43400.0},
                {"e": "magnitud_1er_cambio", "ms": 45000.0}, {"e": "magnitud_ult_cambio", "ms": 46000.0},
                {"e": "registrar_pulsado", "ms": 59500.0}],
            "epoch_ms": 1792918060000}),
    # Plantilla: D1 = 1 (el acceso), sin categoria elegida.
    _linea({"v": 2, "sesion": 1792918000000, "seq": 2, "origen": "inicio:plantilla", "ruta": "/v1/intenciones/gasto-pagado",
            "status": 200, "ok": True, "intencion_id": "i-2", "hecho_id": "h-2", "resultado": "CONFIRMADO", "ms": 7000.0,
            "pasos": [{"e": "form_montado", "ms": 300.0, "via": "GASTO"}, {"e": "arbol_ok", "ms": 600.0},
                      {"e": "cuentas_ok", "ms": 700.0, "n": 1}, {"e": "importe_1er_cambio", "ms": 2000.0},
                      {"e": "importe_ult_cambio", "ms": 4000.0}, {"e": "registrar_pulsado", "ms": 6500.0}],
            "epoch_ms": 1792918070000}),
    # Transferencia: D1 = 3 (tipo, desde, a); abandonado y luego repetido.
    _linea({"v": 2, "sesion": 1792918000000, "seq": 3, "origen": "inicio:registrar", "resultado": "ABANDONADO", "ms": 9000.0,
            "pasos": [{"e": "hoja_tipos", "ms": 2.0}, {"e": "tipo:TRANSFERENCIA", "ms": 800.0}],
            "epoch_ms": 1792918080000}),
    _linea({"v": 2, "sesion": 1792918000000, "seq": 4, "origen": "inicio:registrar", "ruta": "/v1/intenciones/transferencia",
            "status": 200, "ok": True, "intencion_id": "i-4", "hecho_id": "h-4", "resultado": "CONFIRMADO", "ms": 12000.0,
            "pasos": [{"e": "hoja_tipos", "ms": 3.0}, {"e": "tipo:TRANSFERENCIA", "ms": 700.0},
                      {"e": "form_montado", "ms": 800.0, "via": "TRANSFERENCIA"}, {"e": "cuentas_ok", "ms": 1000.0},
                      {"e": "importe_1er_cambio", "ms": 2000.0}, {"e": "cuenta_desde_elegida", "ms": 5000.0},
                      {"e": "cuenta_a_elegida", "ms": 7000.0}, {"e": "registrar_pulsado", "ms": 11500.0}],
            "epoch_ms": 1792918090000}),
    # Tras recargar la app: misma seq 1, otra sesion; caso 6 con «Sin categoria» y chip no.
    _linea({"v": 2, "sesion": 1792918999999, "seq": 1, "origen": "inicio:registrar", "ruta": "/v1/intenciones/gasto-pagado",
            "status": 200, "ok": True, "intencion_id": "i-5", "hecho_id": "h-5", "resultado": "CONFIRMADO", "ms": 11000.0,
            "pasos": [{"e": "hoja_tipos", "ms": 1.0}, {"e": "tipo:GASTO", "ms": 600.0}, {"e": "form_montado", "ms": 700.0},
                      {"e": "selector_abierto", "ms": 3000.0},
                      {"e": "categoria_elegida", "ms": 3500.0, "via": "sin_categoria", "n": 0},
                      {"e": "presupuesto_elegido", "ms": 5000.0}, {"e": "cuenta_elegida", "ms": 6000.0},
                      {"e": "registrar_pulsado", "ms": 10600.0}],
            "epoch_ms": 1792919100000}),
    # Linea v1 (sin pasos): se acepta, sin tramos.
    ' LOG  [G1] {"v":1,"seq":9,"origen":"inicio:registrar","ruta":"/v1/intenciones/gasto-pagado","status":200,"ok":true,'
    '"intencion_id":"i-9","hecho_id":"h-9","resultado":"CONFIRMADO","ms":5000.0,"epoch_ms":1792918131674}',
])


def autoprueba() -> int:
    filas = [tramos(e) for e in leer(SINTETICAS)]
    fallos: list[str] = []

    def esperar(i: int, clave: str, valor) -> None:
        if filas[i].get(clave) != valor:
            fallos.append(f"ensayo {i}: {clave} = {filas[i].get(clave)!r}, se esperaba {valor!r}")

    if len(filas) != 6:
        fallos.append(f"ensayos = {len(filas)}, se esperaban 6")
    # caso 5
    for clave, valor in (("d1_observado", 5), ("pantallas", 3), ("form_montado", 1000.0), ("carga", 600.0),
                         ("tramo_importe", 2000.0), ("tramo_categoria", 3000.0), ("tramo_presupuesto", 34000.0),
                         ("tramo_cuenta", 2000.0), ("tramo_magnitud", 4000.0), ("tramo_registrar", 13500.0),
                         ("respuesta", 500.0), ("dentro_selector", 2000.0), ("via_categoria", "arbol"),
                         ("niveles_categoria", 2), ("interrupciones", 1), ("ms_interrumpido", 30000.0),
                         ("ms_neto", 30000.0), ("ms_teclado", 3000.0), ("scroll_n", 2), ("scroll_ms", 900.0)):
        esperar(0, clave, valor)
    esperar(1, "d1_observado", 1)
    esperar(1, "tramo_importe", 3700.0)
    esperar(1, "respuesta", 500.0)
    esperar(2, "resultado", "ABANDONADO")
    esperar(2, "respuesta", None)
    esperar(3, "d1_observado", 3)
    esperar(3, "tramo_cuenta", 5000.0)
    esperar(4, "d1_observado", 4)
    esperar(4, "via_categoria", "sin_categoria")
    esperar(4, "sesion", 1792918999999)
    esperar(4, "seq", 1)
    esperar(5, "pasos", 0)
    esperar(5, "d1_observado", None)
    if (filas[0]["sesion"], filas[0]["seq"]) == (filas[4]["sesion"], filas[4]["seq"]):
        fallos.append("dos ensayos con la misma (sesion, seq)")
    texto_csv = a_csv(filas)
    if texto_csv.count("\n") != 7 or not texto_csv.startswith("sesion,seq,"):
        fallos.append("CSV mal formado")
    print(a_md(filas))
    for f in fallos:
        print("FALLO", f)
    print("AUTOPRUEBA", "PASS" if not fallos else "FAIL", f"({len(fallos)} fallos)")
    return 0 if not fallos else 1


def main() -> int:
    args = sys.argv[1:]
    if "--autoprueba" in args:
        return autoprueba()
    salida_csv = args[args.index("--csv") + 1] if "--csv" in args else None
    salida_md = args[args.index("--md") + 1] if "--md" in args else None
    entradas = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--csv", "--md"))]
    texto = "".join(open(f, encoding="utf-8").read() for f in entradas) if entradas else sys.stdin.read()
    filas = [tramos(e) for e in leer(texto)]
    if salida_csv:
        with open(salida_csv, "w", encoding="utf-8", newline="") as f:
            f.write(a_csv(filas))
    if salida_md:
        with open(salida_md, "w", encoding="utf-8", newline="") as f:
            f.write(a_md(filas))
    if not salida_csv and not salida_md:
        sys.stdout.write(a_csv(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
