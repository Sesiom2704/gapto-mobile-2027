# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_regcat.py
# Ruta: scripts/dev/e2e_regcat.py
# Descripcion: E2E de REG-CAT (F09 §12.97.1-12.97.3; F05 §28.2, §26.2 AJ-03) y
#   capturas de SET-CAT sobre el cliente REAL exportado a web
#   (react-native-web) + adaptador FastAPI + PostgreSQL LOCAL de desarrollo
#   con el catalogo del seed (bootstrap_dev_db.py --seed-categorias).
#
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***  (corroboracion, no
#   certificacion de proveedor)
#
#   Escenarios:
#     (a) registro con «Hogar › Luz» y la magnitud obligatoria informada
#         («12,5» kWh) -> hecho con categoria_id = Luz y UNA fila de
#         hecho_magnitudes con valor 12.5 y unidad snapshot kWh;
#     (b) registro «Sin categoria» -> categoria_id NULL y 0 filas de
#         hecho_magnitudes;
#     (c) categoria desactivada por API entre la carga y la confirmacion ->
#         CATEGORIA_NO_ELEGIBLE, ningun hecho, recuperacion visible (categoria
#         marcada y nueva eleccion) y el segundo registro usa un intencion_id
#         DISTINTO. Usa una categoria creada por el propio E2E (desactivar una
#         del seed romperia su idempotencia AJ-S4-05).
#   Capturas 393x852 @3x en Light y Dark: REG-CAT (campo, selector, nivel,
#   magnitudes, recuperacion) y SET-CAT (lista, nivel, detalle, selector de
#   iconos, alta). Manifest JSON con los resultados y las filas leidas de la BD.
#
#   Requiere (ya levantados): cliente web en --web, API en --api con CORS para
#   ese origen, GAPTO_DATABASE_URL (solo lectura de verificacion; base LOCAL),
#   GAPTO_DEV_OWNER_USER_ID y GAPTO_DEV_TOKEN (solo para preparar y desactivar
#   la categoria del escenario c; nunca se imprime). Escribe en --salida (fuera
#   del repo).
#   Con --dist <export web> arranca el servidor estatico versionado
#   scripts/dev/servir_web_e2e.py (loopback, HTTP/1.1) y lo detiene al terminar.
# Version: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
# Version: 0.1.1 (F05-01 S6-WIRE+UI, correctivo AJ-S6WIREUI-05): en (c) el 409
#   CATEGORIA_NO_ELEGIBLE se registra en el manifest como `rechazo_esperado`
#   con la peticion que lo origina (metodo, ruta, intencion_id) y el error de
#   consola que provoca; cualquier otro error de consola hace fallar el E2E.
# Version: 0.2.0 (F05-01 P7 · N2, AJ-P7BAT-02/03): escenarios nuevos sobre
#   datos sinteticos «P7-<run_id> …» creados por la API publica (ids uuid5 por
#   run_id: preparar dos veces es idempotente). Solo base LOCAL desechable,
#   nunca ENV-DEV.
#     (d) C07: categoria GASTO «P7-<run_id> E2E» con magnitud NUEVA
#         obligatoria «P7-<run_id> Km» (km, 1 decimal); registro desde la UI
#         informando «12,5»; verificacion READ ONLY bajo gapto_runtime de
#         hechos_financieros, hecho_efectos (categoria_id) y hecho_magnitudes
#         (valor, unidad); la respuesta HTTP queda como evidencia auxiliar.
#     (e) microcopy N3 (Moises D-P7-05): «P7-<run_id> Sin uso» (INGRESO) con
#         la hija «P7-<run_id> Bloqueada» (GASTO) cuya magnitud obligatoria
#         «P7-<run_id> Dato» se deshabilita confirmando su impacto
#         (usables(padre) = false), y «P7-<run_id> Con uso» (INGRESO) con
#         «P7-<run_id> Usable» (GASTO) (usables(padre) = true). Se entra en
#         cada padre desde el selector del registro y se afirma el literal
#         exacto del aviso de nivel y del subtitulo de fila.
#   Ambos en Light y Dark. Nuevo argumento obligatorio --run-p7.
# Version: 0.3.0 (F05-03/F05-04 J3 §2.1/§2.2): Inicio abre el gasto con
#   «Registrar» + hoja de tipos (accion-registrar, tipo-GASTO).
# Version: 0.4.0 (F05-03/F05-04 J3 §2.7; CORTE DE CONCEPTO): la nota opcional se
#   escribe en «Más detalles» (campo-nota) y CADA hecho se localiza en la BD por
#   su UUID (intencion_id del POST capturado; en VS-01 hecho_id = intencion_id),
#   nunca por su concepto.
# ============================================================

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import psycopg
from playwright.sync_api import sync_playwright

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"
RUTA_REGISTRO = "/v1/intenciones/gasto-pagado"


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
_spec = importlib.util.spec_from_file_location("bootstrap_dev_db", pathlib.Path(__file__).with_name("bootstrap_dev_db.py"))
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _leer(dsn: str, owner: str, sql: str, params: tuple) -> list[tuple]:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute(sql, params)
        return cur.fetchall()


def hechos_de(dsn: str, owner: str, ids: list[str]) -> list[dict]:
    """Hechos por UUID (intencion_id de los POST del escenario), nunca por concepto (§2.7)."""
    filas = _leer(dsn, owner, "SELECT id FROM gapto.hechos_financieros WHERE id = ANY(%s::uuid[]) ORDER BY id", (list(ids),))
    res = []
    for (hid,) in filas:
        efectos = _leer(dsn, owner, "SELECT tipo_efecto, categoria_id FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,))
        mags = _leer(dsn, owner, "SELECT magnitud_id, valor, unidad FROM gapto.hecho_magnitudes WHERE hecho_id = %s", (hid,))
        res.append({"hecho_id": str(hid), "efectos": [[t, None if c is None else str(c)] for t, c in efectos],
                    "hecho_magnitudes": [[str(m), str(v), u] for m, v, u in mags]})
    return res


def api(base: str, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(f"{base}{ruta}", data=datos, method=metodo, headers={
        "Authorization": f"Bearer {os.environ['GAPTO_DEV_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def api_estado(base: str, metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[int, dict]:
    """Como `api`, pero devuelve (status, cuerpo) tambien ante un 4xx esperado."""
    try:
        return 200, api(base, metodo, ruta, cuerpo)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


#: Literales de N3 (Moises D-P7-05), identicos a los del componente, regcat y U17.
NEGATIVO_N3 = "Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría."
SUBTITULO_N3 = "sus subcategorías tampoco se pueden usar"


def preparar_p7(base: str, run_p7: str) -> dict[str, str]:
    """Fixture P7 de (d) y (e) por la API publica. Ids uuid5 por run_id: idempotente."""
    ns = uuid.uuid5(uuid.NAMESPACE_URL, f"gapto.p7bat.{run_p7}")
    p = f"P7-{run_p7}"
    ids: dict[str, str] = {}

    def alta(clave: str, nombre: str, padre: str | None, ambito: str) -> None:
        ids[clave] = str(uuid.uuid5(ns, clave))
        status, r = api_estado(base, "POST", "/v1/categorias", {"id": ids[clave], "nombre": nombre, "parent_id": padre,
                                                                  "ambito": ambito, "presupuestable_default": False})
        if status != 200:
            raise SystemExit(f"FALLO: alta {clave}: HTTP {status} {r.get('codigo', '')}")

    def nueva(clave: str, categoria: str, nombre: str, unidad: str, precision: int) -> None:
        ids[clave] = str(uuid.uuid5(ns, clave))
        # Existencia, no estado (como D33 del seed): una magnitud ya creada por su uuid5 no se vuelve
        # a dar de alta (tras deshabilitarla, repetir el alta seria IDENTIDAD_REUTILIZADA).
        if any(m["id"] == ids[clave] for m in api(base, "GET", "/v1/magnitudes")["magnitudes"]):
            return
        status, r = api_estado(base, "POST", f"/v1/categorias/{categoria}/magnitudes", {
            "origen": "NUEVA", "obligatoria": True, "magnitud": {
                "magnitud_id": ids[clave], "nombre": nombre, "unidad_default": unidad, "precision_decimales": precision}})
        if status != 200:
            raise SystemExit(f"FALLO: magnitud {clave}: HTTP {status} {r.get('codigo', '')}")

    alta("e2e", f"{p} E2E", None, "GASTO")
    nueva("e2e_km", ids["e2e"], f"{p} Km", "km", 1)
    alta("sin_uso", f"{p} Sin uso", None, "INGRESO")
    alta("bloqueada", f"{p} Bloqueada", ids["sin_uso"], "GASTO")
    alta("con_uso", f"{p} Con uso", None, "INGRESO")
    alta("usable", f"{p} Usable", ids["con_uso"], "GASTO")
    nueva("dato", ids["bloqueada"], f"{p} Dato", "ud", 0)
    ficha = next(m for m in api(base, "GET", "/v1/magnitudes")["magnitudes"] if m["id"] == ids["dato"])
    if ficha["enabled"]:
        ruta = f"/v1/magnitudes/{ids['dato']}/deshabilitar"
        status, r = api_estado(base, "POST", ruta, {"row_version": ficha["row_version"], "confirmacion_impacto": None})
        if status == 409 and r.get("codigo") == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION":
            impacto = [c["categoria_id"] for c in r["detalle"]["categorias_no_capturables"]]
            status, r = api_estado(base, "POST", ruta, {"row_version": ficha["row_version"], "confirmacion_impacto": impacto})
        if status != 200:
            raise SystemExit(f"FALLO: deshabilitar Dato: HTTP {status} {r.get('codigo', '')}")
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:8081")
    ap.add_argument("--api", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    ap.add_argument("--run-p7", required=True, help="run_id del bloque P7 para los datos sinteticos «P7-<run_id> …»")
    a = ap.parse_args()
    with servidor_web(a.dist, a.web):
        dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
        salida = pathlib.Path(a.salida)
        salida.mkdir(parents=True, exist_ok=True)
        run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
        capturas: list[str] = []
        fallos: list[str] = []
        resultado: dict = {}
        hogar, luz = str(seed.id_categoria("hogar")), str(seed.id_categoria("luz"))
        kwh = str(seed.id_magnitud("consumo_electrico"))
        p7 = preparar_p7(a.api, a.run_p7)
        pref = f"P7-{a.run_p7}"
        respuestas_d: list[dict] = []

        # Categoria propia del escenario (c): hoja GASTO en la raiz.
        cat_c = str(uuid.uuid4())
        api(a.api, "POST", "/v1/categorias", {"id": cat_c, "nombre": f"E2E desactivable {run[-6:]}", "parent_id": None,
                                              "ambito": "GASTO", "presupuestable_default": True, "icon_key": None})

        def comprobar(cond: bool, msg: str) -> None:
            if not cond:
                fallos.append(msg)

        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
            intenciones: list[str] = []
            page.on("request", lambda r: intenciones.append(json.loads(r.post_data)["intencion_id"])
                    if r.method == "POST" and r.url.endswith("/v1/intenciones/gasto-pagado") and r.post_data else None)
            errores_consola: list[dict] = []
            page.on("console", lambda m: errores_consola.append({"texto": m.text, "url": (m.location or {}).get("url", "")})
                    if m.type == "error" else None)
            rechazos_esperados: list[dict] = []

            def shot(nombre: str) -> None:
                f = salida / f"REGCAT_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
                page.wait_for_timeout(350)
                page.screenshot(path=str(f))
                capturas.append(f.name)

            def desbordes() -> list:
                return page.evaluate("[...document.querySelectorAll('*')].filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible').map(e => e.getAttribute('data-testid') || e.tagName)")

            recargas = {"n": 0}

            def cargar_app(testid: str) -> None:
                # La descarga del bundle en loopback se corta de forma intermitente en este equipo
                # (ERR_CONNECTION_RESET): se recarga hasta 5 veces y se registra en el manifest.
                for intento in range(5):
                    page.goto(a.web)
                    try:
                        page.get_by_test_id(testid).wait_for(timeout=12000)
                        # La fuente de Ionicons tambien puede cortarse: sin ella los iconos salen como cuadros.
                        page.wait_for_function("document.fonts.check('16px ionicons')", timeout=8000)
                        return
                    except Exception:
                        recargas["n"] += 1
                raise SystemExit("FALLO: la app web no carga tras 5 intentos")

            def abrir_formulario(nota: str, importe: str) -> int:
                """Abre el gasto y escribe importe y nota; devuelve cuántas intenciones había (para su UUID)."""
                cargar_app("accion-registrar")
                page.get_by_test_id("accion-registrar").click()  # F05-04 §2.2: hoja de tipos
                page.get_by_test_id("tipo-GASTO").click()
                page.get_by_test_id("financiacion").wait_for(timeout=15000)
                page.get_by_test_id("campo-importe").fill(importe)
                page.get_by_test_id("abrir-mas-detalles").click()  # F05-04 §2.7: nota opcional
                page.get_by_test_id("campo-nota").fill(nota)
                page.get_by_test_id("presupuestable-true").click()
                cuenta_unica = page.get_by_test_id("origen-cuenta").count()
                if not cuenta_unica:
                    page.locator("[data-testid^=cuenta-]").first.click()
                return len(intenciones)

            for esquema in ("light", "dark"):
                page.emulate_media(color_scheme=esquema)
                sufijo = "L" if esquema == "light" else "D"
                # ---------------------------------------------------------- (a) Hogar › Luz
                concepto_a = f"E2E luz {run[-6:]} {sufijo}"
                n_a = abrir_formulario(concepto_a, "61,87")
                comprobar(page.get_by_test_id("categoria-valor").inner_text() == "Elige categoría", "(a) categoría no está Pendiente al abrir")
                comprobar(page.get_by_test_id("registrar").get_attribute("aria-disabled") == "true", "(a) botón activo con categoría Pendiente")
                faltan = page.get_by_test_id("faltan").inner_text()
                comprobar("categoría" in faltan, f"(a) faltan no nombra la categoría: {faltan}")
                shot(f"{sufijo}01_campo_pendiente")
                page.get_by_test_id("campo-categoria").click()
                page.get_by_test_id("selector-sin-categoria").wait_for()
                comprobar(page.get_by_test_id(f"cat-{seed.id_categoria('viajes_2025')}").count() == 0, "(a) una desactivada aparece en el registro")
                comprobar(page.get_by_test_id(f"cat-{seed.id_categoria('trabajo')}").count() == 1, "(a) Trabajo (con hijo GASTO) no aparece")
                shot(f"{sufijo}02_selector_raiz")
                page.get_by_test_id(f"cat-{hogar}").click()
                page.get_by_test_id("selector-usar").wait_for()
                gas = page.get_by_test_id(f"cat-{seed.id_categoria('gas')}")
                comprobar(gas.count() == 1 and "Requiere un dato no disponible" in gas.inner_text(), "(a) Gas no se ve con su motivo")
                comprobar(gas.get_attribute("aria-disabled") == "true", "(a) Gas no capturable es seleccionable")
                shot(f"{sufijo}03_selector_hogar")
                page.get_by_test_id(f"cat-{luz}").click()
                page.get_by_test_id("datos-categoria").wait_for()
                comprobar(page.get_by_test_id(f"magnitud-{kwh}").input_value() == "", "(a) la magnitud trae valor por defecto")
                comprobar(page.get_by_test_id("registrar").get_attribute("aria-disabled") == "true", "(a) obligatoria vacía no bloquea")
                shot(f"{sufijo}04_magnitudes_vacia")
                page.get_by_test_id(f"magnitud-{kwh}").fill("12,5")
                comprobar(page.get_by_test_id("registrar").get_attribute("aria-disabled") != "true", "(a) botón sigue desactivado con todo completo")
                d = desbordes()
                comprobar(not d, f"(a) desbordamiento horizontal: {d}")
                shot(f"{sufijo}05_magnitudes_informada")
                page.get_by_test_id("registrar").click()
                page.get_by_test_id("registro-exito").wait_for(timeout=15000)
                shot(f"{sufijo}06_exito")
                bd_a = hechos_de(dsn, owner, intenciones[n_a:])
                comprobar(len(bd_a) == 1, f"(a) hechos != 1: {bd_a}")
                if bd_a:
                    comprobar(bd_a[0]["efectos"][0][1] == luz, f"(a) categoria_id no es Luz: {bd_a[0]['efectos']}")
                    comprobar(bd_a[0]["hecho_magnitudes"] == [[kwh, "12.500000", "kWh"]] or
                              (len(bd_a[0]["hecho_magnitudes"]) == 1 and bd_a[0]["hecho_magnitudes"][0][0] == kwh
                               and float(bd_a[0]["hecho_magnitudes"][0][1]) == 12.5 and bd_a[0]["hecho_magnitudes"][0][2] == "kWh"),
                              f"(a) hecho_magnitudes inesperado: {bd_a[0]['hecho_magnitudes']}")
                resultado[f"a_{esquema}"] = bd_a

                # ---------------------------------------------------------- (b) Sin categoría
                concepto_b = f"E2E sin categoria {run[-6:]} {sufijo}"
                n_b = abrir_formulario(concepto_b, "3,50")
                page.get_by_test_id("campo-categoria").click()
                page.get_by_test_id("selector-sin-categoria").click()
                comprobar(page.get_by_test_id("categoria-valor").inner_text() == "Sin categoría", "(b) no queda «Sin categoría»")
                comprobar(page.get_by_test_id("datos-categoria").count() == 0, "(b) aparece sección de datos")
                page.get_by_test_id("registrar").click()
                page.get_by_test_id("registro-exito").wait_for(timeout=15000)
                bd_b = hechos_de(dsn, owner, intenciones[n_b:])
                comprobar(len(bd_b) == 1 and bd_b[0]["efectos"][0][1] is None and bd_b[0]["hecho_magnitudes"] == [],
                          f"(b) persistencia inesperada: {bd_b}")
                resultado[f"b_{esquema}"] = bd_b

                # ---------------------------------------------------------- (d) C07 con fixture P7 por API
                concepto_d = f"E2E P7 C07 {a.run_p7} {run[-6:]} {sufijo}"
                n_d = abrir_formulario(concepto_d, "8,90")
                page.get_by_test_id("campo-categoria").click()
                page.get_by_test_id(f"cat-{p7['e2e']}").click()
                page.get_by_test_id("datos-categoria").wait_for()
                comprobar(page.get_by_test_id(f"magnitud-{p7['e2e_km']}").input_value() == "", "(d) la magnitud trae valor por defecto")
                comprobar(page.get_by_test_id("registrar").get_attribute("aria-disabled") == "true", "(d) obligatoria vacía no bloquea")
                page.get_by_test_id(f"magnitud-{p7['e2e_km']}").fill("12,5")
                shot(f"{sufijo}08_p7_c07_informada")
                with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(RUTA_REGISTRO)) as resp_d:
                    page.get_by_test_id("registrar").click()
                respuestas_d.append({"esquema": esquema, "status": resp_d.value.status, "cuerpo": resp_d.value.json()})
                page.get_by_test_id("registro-exito").wait_for(timeout=15000)
                shot(f"{sufijo}09_p7_c07_exito")
                bd_d = hechos_de(dsn, owner, intenciones[n_d:])
                comprobar(len(bd_d) == 1, f"(d) hechos != 1: {bd_d}")
                if bd_d:
                    comprobar(bd_d[0]["efectos"][0][1] == p7["e2e"], f"(d) categoria_id inesperado: {bd_d[0]['efectos']}")
                    comprobar(bd_d[0]["hecho_magnitudes"] == [[p7["e2e_km"], "12.500000", "km"]],
                              f"(d) hecho_magnitudes inesperado: {bd_d[0]['hecho_magnitudes']}")
                resultado[f"d_{esquema}"] = bd_d

                # ---------------------------------------------------------- (e) microcopy N3 (literal exacto)
                abrir_formulario(f"E2E P7 N3 {a.run_p7} {sufijo}", "1,00")
                page.get_by_test_id("campo-categoria").click()
                page.get_by_test_id("selector-sin-categoria").wait_for()
                textos_e: dict[str, str] = {}
                for clave, subtitulo in (("sin_uso", f"Solo ingresos · {SUBTITULO_N3}"),
                                         ("con_uso", "Solo ingresos · tiene subcategorías que sí puedes usar")):
                    fila = page.get_by_test_id(f"cat-{p7[clave]}")
                    fila.scroll_into_view_if_needed()
                    textos_e[f"fila_{clave}"] = fila.inner_text()
                    comprobar(subtitulo in fila.inner_text(), f"(e) subtítulo de {clave} inesperado: {fila.inner_text()!r}")
                shot(f"{sufijo}10_p7_n3_filas")
                esperados = {
                    "sin_uso": f"{pref} Sin uso no se puede elegir (solo ingresos). {NEGATIVO_N3}",
                    "con_uso": f"{pref} Con uso no se puede elegir (solo ingresos). Sus subcategorías sí.",
                }
                for n, clave in enumerate(("sin_uso", "con_uso")):
                    page.get_by_test_id(f"cat-{p7[clave]}").click()
                    aviso = page.get_by_test_id("selector-aviso-nivel")
                    aviso.wait_for()
                    # El aviso es [icono, texto]: la primera linea es el glifo de Ionicons (uso privado).
                    icono, _, texto_aviso = aviso.inner_text().strip().partition("\n")
                    comprobar(len(icono) == 1 and "\ue000" <= icono <= "\uf8ff", f"(e) aviso sin el icono esperado: {icono!r}")
                    textos_e[f"aviso_{clave}"] = texto_aviso.strip()
                    comprobar(textos_e[f"aviso_{clave}"] == esperados[clave],
                              f"(e) aviso de {clave} inesperado: {textos_e[f'aviso_{clave}']!r}")
                    if clave == "sin_uso":
                        bloq = page.get_by_test_id(f"cat-{p7['bloqueada']}")
                        textos_e["fila_bloqueada"] = bloq.inner_text()
                        comprobar("Requiere un dato no disponible" in bloq.inner_text() and bloq.get_attribute("aria-disabled") == "true",
                                  f"(e) «Bloqueada» sin su motivo o seleccionable: {bloq.inner_text()!r}")
                    shot(f"{sufijo}{11 + n}_p7_n3_aviso_{clave}")
                    page.get_by_test_id("selector-miga-todas").click()
                resultado[f"e_{esquema}"] = textos_e

            # -------------------------------------------------------------- (c) desactivada entre carga y confirmación (Light)
            page.emulate_media(color_scheme="light")
            concepto_c = f"E2E rechazo {run[-6:]}"
            abrir_formulario(concepto_c, "23,40")  # n_antes se toma justo antes de registrar
            page.get_by_test_id("campo-categoria").click()
            page.get_by_test_id(f"cat-{cat_c}").click()
            arbol = api(a.api, "GET", "/v1/categorias")["categorias"]
            rv = next(c["row_version"] for c in arbol if c["id"] == cat_c)
            api(a.api, "POST", f"/v1/categorias/{cat_c}/desactivar", {"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS", "row_version": rv})
            n_antes = len(intenciones)
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(RUTA_REGISTRO)) as resp_c:
                page.get_by_test_id("registrar").click()
            r409 = resp_c.value
            cuerpo_409 = r409.json()
            rechazos_esperados.append({"status": r409.status, "codigo": cuerpo_409.get("codigo"), "metodo": r409.request.method,
                                       "ruta": urllib.parse.urlsplit(r409.url).path,
                                       "intencion_id": json.loads(r409.request.post_data)["intencion_id"]})
            comprobar(r409.status == 409 and cuerpo_409.get("codigo") == "CATEGORIA_NO_ELEGIBLE",
                      f"(c) respuesta distinta del rechazo esperado: {r409.status} {cuerpo_409.get('codigo')}")
            page.get_by_test_id("categoria-invalida").wait_for(timeout=15000)
            comprobar(page.get_by_test_id("error-dominio").count() == 1, "(c) sin aviso de rechazo")
            comprobar(page.get_by_test_id("categoria-valor").inner_text() == "Elige otra categoría", "(c) la categoría no queda marcada")
            comprobar(hechos_de(dsn, owner, intenciones[n_antes:]) == [], "(c) se creó un hecho con la categoría desactivada")
            comprobar(page.get_by_test_id("campo-importe").input_value() == "23,40", "(c) no se conservan las decisiones")
            shot("L07_recuperacion_rechazo")
            page.get_by_test_id("campo-categoria").click()
            comprobar(page.get_by_test_id(f"cat-{cat_c}").count() == 0, "(c) la desactivada sigue ofreciéndose tras recargar")
            page.get_by_test_id("selector-sin-categoria").click()
            page.get_by_test_id("registrar").click()
            page.get_by_test_id("registro-exito").wait_for(timeout=15000)
            ids_c = intenciones[n_antes:]
            comprobar(len(ids_c) == 2 and ids_c[0] != ids_c[1], f"(c) el segundo registro no usa identidad nueva: {ids_c}")
            bd_c = hechos_de(dsn, owner, ids_c)
            comprobar(len(bd_c) == 1 and bd_c[0]["efectos"][0][1] is None, f"(c) persistencia final inesperada: {bd_c}")
            resultado["c"] = {"intenciones": ids_c, "bd": bd_c}

            # -------------------------------------------------------------- SET-CAT: capturas Light y Dark
            for esquema in ("light", "dark"):
                page.emulate_media(color_scheme=esquema)
                sufijo = "L" if esquema == "light" else "D"
                cargar_app("tab-MAS")
                page.get_by_test_id("tab-MAS").click()
                page.get_by_test_id("mas-ajustes").click()
                shot(f"S{sufijo}01_ajustes")
                page.get_by_test_id("ajustes-categorias").click()
                page.get_by_test_id(f"fila-{hogar}").wait_for(timeout=15000)
                shot(f"S{sufijo}02_lista_activas")
                page.get_by_test_id("filtro-TODAS").click()
                shot(f"S{sufijo}03_lista_todas")
                page.get_by_test_id(f"fila-{hogar}").click()
                shot(f"S{sufijo}04_nivel_hogar")
                page.get_by_test_id(f"fila-{luz}").click()
                page.get_by_test_id("detalle-categoria").wait_for()
                shot(f"S{sufijo}05_detalle_luz")
                page.get_by_test_id("detalle-icono").click()
                page.get_by_test_id("selector-iconos").wait_for()
                shot(f"S{sufijo}06_selector_iconos")
                page.get_by_test_id("iconos-cerrar").click()
                page.get_by_test_id("detalle-atras").click()
                page.get_by_test_id("nueva-categoria").click()
                page.get_by_test_id("nueva-categoria-pantalla").wait_for()
                shot(f"S{sufijo}07_alta_con_padre")
                page.get_by_test_id("alta-cancelar").click()
            nav.close()

        # AJ-S6WIREUI-05: cada 409 esperado de (c) explica como mucho UN error de consola del navegador
        # («Failed to load resource ... 409») sobre la ruta del registro; cualquier otro error falla el E2E.
        pendientes = [r for r in rechazos_esperados if r["status"] == 409]
        no_esperados: list[dict] = []
        for e in errores_consola:
            if pendientes and "409" in e["texto"] and urllib.parse.urlsplit(e["url"]).path == RUTA_REGISTRO:
                pendientes.pop(0)["error_consola"] = e
            else:
                no_esperados.append(e)
        comprobar(not no_esperados, f"(consola) errores no esperados: {no_esperados}")
        manifest = {"etiqueta": ETIQUETA, "run_id": run, "run_p7": a.run_p7, "fixture_p7": p7, "respuestas_d": respuestas_d,
                    "web": a.web, "resultado": resultado, "fallos": fallos,
                    "recargas_por_descarga_cortada": recargas["n"], "rechazo_esperado": rechazos_esperados,
                    "errores_consola": errores_consola, "errores_consola_no_esperados": no_esperados, "capturas": capturas}
        (salida / f"REGCAT_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"etiqueta": ETIQUETA, "run_id": run, "fallos": fallos, "capturas": len(capturas),
                          "errores_consola": len(errores_consola), "rechazos_esperados": len(rechazos_esperados),
                          "errores_consola_no_esperados": len(no_esperados)}, ensure_ascii=False))
        sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
