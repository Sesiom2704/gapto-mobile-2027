# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_preferencias.py
# Ruta: scripts/dev/e2e_preferencias.py
# Descripcion: E2E de las preferencias de registro en «Nuevo gasto» (F05-02
#   B2; F05-D026 §41.3; lamina SET-PREF / REG-PREF v0.1 R01-R07) sobre el
#   cliente REAL exportado a web (react-native-web) + adaptador FastAPI +
#   PostgreSQL LOCAL desechable. Mismo patron que e2e_vs01.py.
#
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***  (corroboracion de
#   desarrollo, no certificacion de proveedor)
#
#   Escenario (datos sinteticos «P-<run_id>», creados por el propio E2E: dos
#   cuentas EUR por SQL como gapto_owner y una categoria por la API publica):
#     R01  formulario sin preferencia aplicable: varias cuentas, ninguna
#          preseleccionada ni presupuesto preseleccionado;
#     R05  gasto con la categoria, cuenta y presupuesto ELEGIDOS por el
#          usuario -> exito -> «¿Recordarlo para <categoria>?» con ambas
#          casillas marcadas -> «Guardar preferencia» -> «Preferencia
#          guardada»; la BD tiene UNA preferencia habilitada con esos valores;
#     R02  gasto nuevo con la misma categoria: cuenta y presupuesto propuestos
#          con «Propuesta: tu preferencia para <categoria>.»; se registra sin
#          tocarlos y la BD sella esos valores;
#     R03  gasto nuevo: el usuario cambia la cuenta («Elegida por ti.»);
#     R07  tras registrarlo, la tarjeta marca solo la cuenta; «Guardar» abre
#          «Ya tienes una preferencia para <categoria>» -> «Sustituir»: la MISMA
#          preferencia pasa a la nueva cuenta, conserva el presupuesto (estado
#          completo, E05) y row_version 2; sigue habiendo UNA.
#     R07p (DERIVADO, no presente en la lamina; B2-V §5.10) gasto nuevo con el
#          presupuesto cambiado a «No»: la tarjeta marca solo el presupuesto;
#          «Guardar» abre la hoja con el texto de presupuesto y «Mantener la
#          actual» -> «Mantener» no escribe (misma fila y row_version).
#   Capturas 393x852 @3x (claro; R02, R07 y R07p tambien en oscuro) y manifest JSON.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL; preparacion y lectura),
#   GAPTO_DEV_OWNER_USER_ID y GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-02 B2)
#          0.2.0 (F05-02 B2-V paso 5): escenario R07p (texto R07 del presupuesto y
#                «Mantener la actual», derivados) con captura clara y oscura.
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
SERVIDOR_WEB = pathlib.Path(__file__).resolve().parent / "servir_web_e2e.py"


@contextlib.contextmanager
def servidor_web(dist: str | None, web: str):
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


def _exigir_local(dsn: str) -> None:
    host = psycopg.conninfo.conninfo_to_dict(dsn).get("host", "")
    if host not in ("", "localhost", "127.0.0.1"):
        raise SystemExit("FALLO: el E2E solo se ejecuta contra PostgreSQL LOCAL")


def _sql(dsn: str, owner: str, rol: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute(f"SET LOCAL ROLE {rol}")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def crear_cuenta(dsn: str, owner: str, nombre: str) -> str:
    """Cuenta EUR con participacion 100 % del actor self (una transaccion)."""
    cid = str(uuid.uuid4())
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_owner")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")
        actor = cur.fetchone()[0]
        cur.execute("INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, computa_liquidez, "
                    "computa_patrimonio, permite_negativo) VALUES (%s, %s, %s, 'CORRIENTE', 'ACTIVO', 'EUR', true, true, false)",
                    (cid, owner, nombre))
        cur.execute("INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, vigente_desde) "
                    "VALUES (%s, %s, 100, DATE '2026-01-01')", (cid, actor))
    return cid


def api(base: str, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(f"{base}{ruta}", data=datos, method=metodo, headers={
        "Authorization": f"Bearer {os.environ['GAPTO_DEV_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def preferencias(dsn: str, owner: str) -> list[list[str]]:
    filas = _sql(dsn, owner, "gapto_runtime", "SELECT id, cuenta_default_id, presupuestable_default, enabled, row_version "
                                              "FROM gapto.preferencias_registro ORDER BY created_at, id")
    return [[str(x) for x in f] for f in filas]


def hecho(dsn: str, owner: str, concepto: str) -> list[list[str]]:
    filas = _sql(dsn, owner, "gapto_runtime",
                 "SELECT h.presupuestable, m.cuenta_id FROM gapto.hechos_financieros h "
                 "JOIN gapto.hecho_movimientos_tesoreria hm ON hm.hecho_id = h.id "
                 "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id WHERE h.concepto = %s",
                 (concepto,))
    return [[str(x) for x in f] for f in filas]


def comprobar(cond: bool, mensaje: str) -> None:
    if not cond:
        raise SystemExit(f"FALLO: {mensaje}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5468")
    ap.add_argument("--api", default="http://127.0.0.1:5467")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
    _exigir_local(dsn)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)

    # Preparacion: dos cuentas EUR mas (con la del seed, varias elegibles) y una categoria.
    tarjeta = crear_cuenta(dsn, owner, f"Tarjeta P-{run[-6:]}")
    efectivo = crear_cuenta(dsn, owner, f"Efectivo P-{run[-6:]}")
    nombre_cat = f"Super P-{run[-6:]}"
    cid = str(uuid.uuid4())
    api(a.api, "POST", "/v1/categorias", {"id": cid, "nombre": nombre_cat, "parent_id": None, "ambito": "GASTO",
                                          "presupuestable_default": True, "icon_key": None})
    previas = preferencias(dsn, owner)
    capturas: list[str] = []
    res: dict = {}

    def shot(page, nombre):
        f = salida / f"PREF_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
        page.screenshot(path=str(f))
        capturas.append(f.name)

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES",
                            timezone_id="Europe/Madrid")
        consola: list[str] = []
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.goto(a.web)
        t = page.get_by_test_id

        def abrir_formulario():
            t("accion-gasto").click()
            t("registro-form").wait_for()
            t(f"cuenta-{tarjeta}").wait_for()
            page.wait_for_timeout(600)

        def basicos(concepto: str):
            t("campo-importe").fill("42,18")
            t("campo-concepto").fill(concepto)
            t("campo-categoria").click()
            t(f"cat-{cid}").click()
            page.wait_for_timeout(800)

        def marcado(testid: str) -> str | None:
            """Estado visible: aria-checked (casillas) o, en chips y segmentos de Basicos (react-native-web
            no traduce accessibilityState), el «✓ » del chip o el borde de seleccion del segmento."""
            el = t(testid)
            if el.get_attribute("aria-checked") is not None:
                return el.get_attribute("aria-checked")
            if el.get_attribute("role") == "radio":
                # El segmento seleccionado tiene superficie propia; los demas, fondo transparente.
                return str(el.evaluate("e => getComputedStyle(e).backgroundColor !== 'rgba(0, 0, 0, 0)'")).lower()
            return str(el.inner_text().startswith("✓")).lower()

        # ---------------------------------------------------- R01 + R05
        t("accion-gasto").wait_for(timeout=30000)
        abrir_formulario()
        res["r01"] = {"cuentas_marcadas": [x for x in (tarjeta, efectivo) if marcado(f"cuenta-{x}") == "true"],
                      "origen_cuenta": t("origen-cuenta").count(), "presupuesto_si": marcado("presupuestable-true")}
        comprobar(not res["r01"]["cuentas_marcadas"] and res["r01"]["origen_cuenta"] == 0, "R01 con preseleccion")
        shot(page, "01_R01_sin_propuesta")
        basicos(f"PrefA-{run}")
        t(f"cuenta-{tarjeta}").click()
        t("presupuestable-true").click()
        res["r05_origen_cuenta"] = t("origen-cuenta").inner_text()
        comprobar(res["r05_origen_cuenta"] == "Elegida por ti.", "origen de la cuenta elegida")
        t("registrar").click()
        t("registro-exito").wait_for(timeout=15000)
        t("pref-tarjeta").wait_for()
        res["r05"] = {"titulo_visible": page.get_by_text(f"¿Recordarlo para {nombre_cat}?").count(),
                      "casilla_cuenta": marcado("pref-casilla-cuenta"),
                      "casilla_presupuesto": marcado("pref-casilla-presupuestable")}
        comprobar(res["r05"] == {"titulo_visible": 1, "casilla_cuenta": "true", "casilla_presupuesto": "true"},
                  f"R05 tarjeta {res['r05']}")
        shot(page, "02_R05_tarjeta")
        t("pref-guardar").click()
        t("pref-guardada").wait_for(timeout=15000)
        shot(page, "03_R06_preferencia_guardada")
        tras_alta = preferencias(dsn, owner)
        nuevas = [p for p in tras_alta if p not in previas]
        res["bd_tras_alta"] = nuevas
        comprobar(len(nuevas) == 1 and nuevas[0][1:] == [tarjeta, "True", "True", "1"], f"alta en BD {nuevas}")
        pid = nuevas[0][0]
        t("volver-inicio").click()

        # ---------------------------------------------------- R02
        abrir_formulario()
        basicos(f"PrefB-{run}")
        t("origen-cuenta").wait_for()
        res["r02"] = {"cuenta_marcada": marcado(f"cuenta-{tarjeta}"), "origen_cuenta": t("origen-cuenta").inner_text(),
                      "presupuesto_si": marcado("presupuestable-true"),
                      "origen_presupuesto": t("origen-presupuestable").inner_text(),
                      "financiacion": t("financiacion-texto").inner_text()}
        esperado = f"Propuesta: tu preferencia para {nombre_cat}."
        comprobar(res["r02"]["cuenta_marcada"] == "true" and res["r02"]["origen_cuenta"] == esperado
                  and res["r02"]["presupuesto_si"] == "true" and res["r02"]["origen_presupuesto"] == esperado,
                  f"R02 {res['r02']}")
        shot(page, "04_R02_propuesta")
        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(400)
        shot(page, "05_R02_propuesta_dark")
        page.emulate_media(color_scheme="light")
        t("registrar").click()
        t("registro-exito").wait_for(timeout=15000)
        res["r02_tarjeta_tras_registro"] = t("pref-tarjeta").count()  # nada que recordar: oculta
        comprobar(res["r02_tarjeta_tras_registro"] == 0, "tarjeta visible sin nada que recordar")
        res["bd_hecho_r02"] = hecho(dsn, owner, f"PrefB-{run}")
        comprobar(res["bd_hecho_r02"] == [["True", tarjeta]], f"R02 sellado {res['bd_hecho_r02']}")
        t("volver-inicio").click()

        # ---------------------------------------------------- R03 + R07
        abrir_formulario()
        basicos(f"PrefC-{run}")
        t("origen-cuenta").wait_for()
        t(f"cuenta-{efectivo}").click()
        res["r03_origen_cuenta"] = t("origen-cuenta").inner_text()
        comprobar(res["r03_origen_cuenta"] == "Elegida por ti.", "R03 cuenta elegida")
        shot(page, "06_R03_elegida")
        t("registrar").click()
        t("registro-exito").wait_for(timeout=15000)
        t("pref-tarjeta").wait_for()
        res["r07_casillas"] = [marcado("pref-casilla-cuenta"), marcado("pref-casilla-presupuestable")]
        comprobar(res["r07_casillas"] == ["true", "false"], f"casillas R07 {res['r07_casillas']}")
        t("pref-guardar").click()
        t("pref-conflicto").wait_for(timeout=15000)
        res["r07_texto"] = t("pref-conflicto-texto").inner_text()
        comprobar(res["r07_texto"] == f"Ahora propone pagar con Tarjeta P-{run[-6:]}. ¿Quieres que proponga "
                                      f"Efectivo P-{run[-6:]} a partir de ahora?", f"texto R07 {res['r07_texto']}")
        shot(page, "07_R07_conflicto")
        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(400)
        shot(page, "08_R07_conflicto_dark")
        page.emulate_media(color_scheme="light")
        t("pref-sustituir").click()
        t("pref-guardada").wait_for(timeout=15000)
        shot(page, "09_R07_sustituida")
        res["bd_tras_sustituir"] = [p for p in preferencias(dsn, owner) if p not in previas or p[0] == pid]
        t("volver-inicio").click()

        # ---------------------------------------------------- R07 de presupuesto (DERIVADO, no presente en la lamina)
        abrir_formulario()
        basicos(f"PrefD-{run}")
        t("origen-presupuestable").wait_for()
        t("presupuestable-false").click()
        t("registrar").click()
        t("registro-exito").wait_for(timeout=15000)
        t("pref-tarjeta").wait_for()
        res["r07p_casillas"] = [marcado("pref-casilla-cuenta"), marcado("pref-casilla-presupuestable")]
        comprobar(res["r07p_casillas"] == ["false", "true"], f"casillas R07 presupuesto {res['r07p_casillas']}")
        t("pref-guardar").click()
        t("pref-conflicto").wait_for(timeout=15000)
        res["r07p_texto"] = t("pref-conflicto-texto").inner_text()
        res["r07p_mantener"] = t("pref-mantener").inner_text()
        comprobar(res["r07p_texto"] == "Ahora propone que cuenta para el presupuesto: Sí. ¿Quieres que proponga que "
                                       "cuenta para el presupuesto: No a partir de ahora?", f"texto R07p {res['r07p_texto']}")
        comprobar(res["r07p_mantener"] == "Mantener la actual", f"boton R07p {res['r07p_mantener']}")
        shot(page, "10_R07_presupuesto_DERIVADO")
        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(400)
        shot(page, "11_R07_presupuesto_DERIVADO_dark")
        page.emulate_media(color_scheme="light")
        t("pref-mantener").click()
        t("pref-conflicto").wait_for(state="detached", timeout=15000)
        shot(page, "12_R07_presupuesto_mantenida")
        nav.close()

    finales = [p for p in preferencias(dsn, owner) if p not in previas or p[0] == pid]
    comprobar(res["bd_tras_sustituir"] == [[pid, efectivo, "True", "True", "2"]], f"sustituir en BD {res['bd_tras_sustituir']}")
    res["bd_tras_mantener"] = finales  # «Mantener» no escribe: misma fila y misma row_version
    comprobar(finales == res["bd_tras_sustituir"], f"mantener en BD {finales}")
    res["bd_hecho_r07"] = hecho(dsn, owner, f"PrefC-{run}")
    comprobar(res["bd_hecho_r07"] == [["True", efectivo]], f"R07 hecho {res['bd_hecho_r07']}")
    res["bd_hecho_r07p"] = hecho(dsn, owner, f"PrefD-{run}")
    comprobar(res["bd_hecho_r07p"] == [["False", efectivo]], f"R07p hecho {res['bd_hecho_r07p']}")
    comprobar(not consola, f"errores de consola: {consola}")
    manifest = {"etiqueta": ETIQUETA, "run_id": run, "categoria": nombre_cat, "cuentas": {"tarjeta": tarjeta,
                "efectivo": efectivo}, "resultados": res, "errores_consola": consola, "capturas": capturas}
    (salida / f"PREF_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print("RESULTADO: PASS")


if __name__ == "__main__":
    main()
