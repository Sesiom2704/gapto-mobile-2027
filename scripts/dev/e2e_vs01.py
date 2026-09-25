# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_vs01.py
# Ruta: scripts/dev/e2e_vs01.py
# Descripcion: E2E del vertical slice VS-01 sobre el cliente REAL exportado a
#   web (react-native-web) + adaptador FastAPI + PostgreSQL LOCAL de
#   desarrollo. Recorre Home -> accion rapida Gasto -> formulario -> OP-22 ->
#   persistencia -> lectura -> Home, contrasta la UI con la BD y captura
#   pantallas en viewport 393x852 (@3x).
#
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***
#
#   Requiere (ya levantados): cliente web en --web, API en --api y
#   GAPTO_DATABASE_URL (solo lectura de verificacion) + GAPTO_DEV_OWNER_USER_ID.
#   Escribe las capturas y un manifest JSON en --salida (fuera del repo).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import time
import uuid

import psycopg
from playwright.sync_api import sync_playwright

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


def leer_bd(dsn: str, owner: str, concepto: str) -> dict:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT id, importe_total, presupuestable, estado_localizacion FROM gapto.hechos_financieros WHERE concepto=%s", (concepto,))
        hechos = cur.fetchall()
        hid = hechos[0][0]
        def uno(sql):
            cur.execute(sql, (hid,)); return cur.fetchall()
        return {
            "hechos": len(hechos),
            "hecho": [str(x) for x in hechos[0]],
            "efectos": [list(map(str, r)) for r in uno("SELECT tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos WHERE hecho_id=%s")],
            "atribuciones": [list(map(str, r)) for r in uno("SELECT a.importe_atribuido, a.criterio_atribucion FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id=a.efecto_id WHERE e.hecho_id=%s")],
            "movimientos": [list(map(str, r)) for r in uno("SELECT m.importe, c.importe_asignado FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id=m.id WHERE c.hecho_id=%s")],
            "aportaciones": [list(map(str, r)) for r in uno("SELECT importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s")],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:8081")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--concepto", default="Café")
    ap.add_argument("--importe", default="3,50")
    a = ap.parse_args()
    salida = pathlib.Path(a.salida); salida.mkdir(parents=True, exist_ok=True)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    metricas: dict = {"taps": 0, "campos_escritos": 0, "decisiones_explicitas": 0}
    capturas = []

    def shot(page, nombre):
        f = salida / f"VS01_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
        page.screenshot(path=str(f)); capturas.append(f.name)

    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.goto(a.web)
        consola = []
        page.on("console", lambda m: consola.append(m.type) if m.type == "error" else None)
        g = page.get_by_test_id("gastos-valor")
        g.wait_for(timeout=30000)
        antes = g.inner_text()
        page.wait_for_timeout(500)
        shot(page, "01_home_antes")

        t0 = time.monotonic()
        page.get_by_test_id("accion-gasto").click(); metricas["taps"] += 1
        metricas["taps_home_a_formulario"] = 1
        page.get_by_test_id("origen-cuenta").wait_for()
        page.wait_for_timeout(500)
        desbordes = page.evaluate("[...document.querySelectorAll('*')].filter(e => e.scrollLeft > 0 || e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible').map(e => e.getAttribute('data-testid') || e.tagName)")
        metricas["desbordes_horizontales_formulario"] = desbordes
        if desbordes:
            raise SystemExit(f"FALLO LAYOUT: desbordamiento horizontal en {desbordes}")
        page.get_by_test_id("campo-importe").fill(a.importe); metricas["campos_escritos"] += 1
        page.get_by_test_id("campo-concepto").click(); metricas["taps"] += 1
        page.get_by_test_id("campo-concepto").fill(a.concepto); metricas["campos_escritos"] += 1
        page.get_by_test_id("presupuestable-true").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
        page.get_by_test_id("solo-mio").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
        page.wait_for_timeout(300)
        shot(page, "02_formulario")
        page.get_by_test_id("registrar").click(); metricas["taps"] += 1
        page.get_by_test_id("registro-exito").wait_for(timeout=15000)
        metricas["taps_hasta_confirmacion"] = metricas["taps"]
        metricas["segundos_automatizados_hasta_confirmacion"] = round(time.monotonic() - t0, 2)
        shot(page, "03_exito")
        page.get_by_test_id("volver-inicio").click(); metricas["taps"] += 1
        page.wait_for_function("(a) => { const e=document.querySelector('[data-testid=gastos-valor]'); return e && e.innerText !== a; }", arg=antes, timeout=15000)
        despues = page.get_by_test_id("gastos-valor").inner_text()
        page.wait_for_timeout(300)
        shot(page, "04_home_refrescada")
        nav.close()

    bd = leer_bd(os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"], a.concepto)
    manifest = {"etiqueta": ETIQUETA, "run_id": run, "gastos_home_antes": antes, "gastos_home_despues": despues,
                "bd": bd, "metricas": metricas, "errores_consola": len(consola), "capturas": capturas}
    (salida / f"VS01_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
