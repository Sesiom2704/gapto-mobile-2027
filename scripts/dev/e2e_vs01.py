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
#   v0.2.0 (F05-D003): espera y registra la linea de financiacion visible,
#   comprueba que el bloque «Este mes» no muestra importes (la cifra real va
#   en la tarjeta parcial separada) y anade al manifest la financiacion y la
#   fecha comun gasto/pago persistidas.
#   v0.3.0 (F05 — VS-01 · Alineacion visual, A2/SPEC-08): comprueba que
#   «Registrar gasto» esta DESACTIVADO (aria-disabled) al abrir el formulario y
#   la indicacion visible de lo que falta, que pulsarlo no crea ningun hecho y
#   que se habilita al completar las decisiones bloqueantes; captura Home y
#   formulario tambien en esquema oscuro (emulacion prefers-color-scheme).
#   v0.4.0 (F05-01 S6-WIRE+UI (este mandato)): la categoria es obligatoria en el
#   wire (S6-WIRE). El flujo base de VS-01 elige «Sin categoria» en el selector
#   como DECISION EXPLICITA (una decision y dos toques mas), comprueba que la
#   categoria pendiente figura en «faltan» al abrir y registra en el manifest
#   la categoria elegida y el categoria_id persistido (NULL). Los escenarios con
#   categoria y magnitudes viven en e2e_regcat.py.
#   Con --dist <export web> arranca el servidor estatico versionado
#   scripts/dev/servir_web_e2e.py (loopback, HTTP/1.1) y lo detiene al terminar.
# Version: 0.4.0
# ============================================================

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

import psycopg
from playwright.sync_api import sync_playwright

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


#: Servidor estatico versionado (solo loopback), localizado junto a este script.
SERVIDOR_WEB = pathlib.Path(__file__).resolve().parent / "servir_web_e2e.py"


@contextlib.contextmanager
def servidor_web(dist: str | None, web: str):
    """Con --dist, arranca scripts/dev/servir_web_e2e.py sobre el export web y lo
    detiene al terminar; sin --dist se usa un cliente web ya levantado en --web."""
    if not dist:
        yield
        return
    puerto = urllib.parse.urlsplit(web).port or 8081
    proc = subprocess.Popen([sys.executable, str(SERVIDOR_WEB), dist, str(puerto)])
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(web, timeout=2).read()
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise SystemExit("FALLO: el servidor web del E2E no responde")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def contar_hechos(dsn: str, owner: str, concepto: str) -> int:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT count(*) FROM gapto.hechos_financieros WHERE concepto=%s", (concepto,))
        return cur.fetchone()[0]


def leer_bd(dsn: str, owner: str, concepto: str) -> dict:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT id, importe_total, presupuestable, estado_localizacion, fecha_hecho FROM gapto.hechos_financieros WHERE concepto=%s", (concepto,))
        hechos = cur.fetchall()
        hid = hechos[0][0]
        def uno(sql):
            cur.execute(sql, (hid,)); return cur.fetchall()
        return {
            "hechos": len(hechos),
            "hecho": [str(x) for x in hechos[0]],
            "efectos": [list(map(str, r)) for r in uno("SELECT tipo_efecto, importe_delta, estado_atribucion, categoria_id FROM gapto.hecho_efectos WHERE hecho_id=%s")],
            "atribuciones": [list(map(str, r)) for r in uno("SELECT a.importe_atribuido, a.criterio_atribucion FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id=a.efecto_id WHERE e.hecho_id=%s")],
            "movimientos": [list(map(str, r)) for r in uno("SELECT m.importe, c.importe_asignado, m.fecha_movimiento FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id=m.id WHERE c.hecho_id=%s")],
            "aportaciones": [list(map(str, r)) for r in uno("SELECT importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s")],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:8081")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--concepto", default="Café")
    ap.add_argument("--importe", default="3,50")
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    with servidor_web(a.dist, a.web):
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
            page.get_by_test_id("financiacion").wait_for()
            financiacion_visible = page.get_by_test_id("financiacion-texto").inner_text()
            page.wait_for_timeout(500)
            desbordes = page.evaluate("[...document.querySelectorAll('*')].filter(e => e.scrollLeft > 0 || e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible').map(e => e.getAttribute('data-testid') || e.tagName)")
            metricas["desbordes_horizontales_formulario"] = desbordes
            if desbordes:
                raise SystemExit(f"FALLO LAYOUT: desbordamiento horizontal en {desbordes}")
            # SPEC-08: desactivado al abrir, con indicacion visible; pulsarlo no escribe.
            boton = page.get_by_test_id("registrar")
            spec08 = {"disabled_al_abrir": boton.get_attribute("aria-disabled"),
                      "faltan_al_abrir": page.get_by_test_id("faltan").inner_text()}
            if spec08["disabled_al_abrir"] != "true":
                raise SystemExit("FALLO SPEC-08: «Registrar gasto» no esta desactivado con decisiones pendientes")
            boton.click(force=True)
            page.wait_for_timeout(800)
            spec08["hechos_tras_pulsar_desactivado"] = contar_hechos(os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"], a.concepto)
            if spec08["hechos_tras_pulsar_desactivado"] != 0 or page.get_by_test_id("registro-exito").count():
                raise SystemExit("FALLO SPEC-08: pulsar el boton desactivado ha producido un registro")
            shot(page, "02a_formulario_vacio")
            page.get_by_test_id("campo-importe").fill(a.importe); metricas["campos_escritos"] += 1
            page.get_by_test_id("campo-concepto").click(); metricas["taps"] += 1
            page.get_by_test_id("campo-concepto").fill(a.concepto); metricas["campos_escritos"] += 1
            page.get_by_test_id("presupuestable-true").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            page.get_by_test_id("solo-mio").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            if "categoría" not in spec08["faltan_al_abrir"]:
                raise SystemExit("FALLO S6-WIRE: «faltan» no nombra la categoria pendiente al abrir")
            page.get_by_test_id("campo-categoria").click(); metricas["taps"] += 1
            page.get_by_test_id("selector-sin-categoria").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            page.wait_for_timeout(300)
            spec08["disabled_completo"] = boton.get_attribute("aria-disabled")
            spec08["faltan_completo"] = page.get_by_test_id("faltan").count()
            if spec08["disabled_completo"] == "true" or spec08["faltan_completo"]:
                raise SystemExit("FALLO SPEC-08: el boton sigue desactivado con el formulario completo")
            shot(page, "02_formulario")
            page.get_by_test_id("registrar").click(); metricas["taps"] += 1
            page.get_by_test_id("registro-exito").wait_for(timeout=15000)
            metricas["taps_hasta_confirmacion"] = metricas["taps"]
            metricas["segundos_automatizados_hasta_confirmacion"] = round(time.monotonic() - t0, 2)
            shot(page, "03_exito")
            page.get_by_test_id("volver-inicio").click(); metricas["taps"] += 1
            page.wait_for_function("(a) => { const e=document.querySelector('[data-testid=gastos-valor]'); return e && e.innerText !== a; }", arg=antes, timeout=15000)
            despues = page.get_by_test_id("gastos-valor").inner_text()
            importes_en_mes = page.get_by_test_id("bloque-mes").inner_text().count("€")
            if importes_en_mes:
                raise SystemExit("FALLO F05-D003 §16.6: el bloque «Este mes» muestra importes")
            page.wait_for_timeout(300)
            shot(page, "04_home_refrescada")
            # Esquema oscuro (mismos tokens DS-01 Dark): solo capturas de revision visual.
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(500)
            shot(page, "05_home_dark")
            page.get_by_test_id("accion-gasto").click()
            page.get_by_test_id("financiacion").wait_for()
            page.wait_for_timeout(500)
            shot(page, "06_formulario_dark")
            nav.close()

        bd = leer_bd(os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"], a.concepto)
        manifest = {"etiqueta": ETIQUETA, "run_id": run, "categoria_elegida": "SIN_CATEGORIA (decision explicita)",
                    "gastos_home_antes": antes, "gastos_home_despues": despues,
                    "financiacion_visible": financiacion_visible, "importes_en_bloque_mes": importes_en_mes, "spec08": spec08,
                    "bd": bd, "metricas": metricas, "errores_consola": len(consola), "capturas": capturas}
        (salida / f"VS01_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
