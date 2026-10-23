# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_gate_g2.py
# Ruta: scripts/dev/e2e_f05_gate_g2.py
# Descripcion: F05-GATE G2 (F05 §49.16.2; F05-D050 §64.7): bateria web de
#   casos complejos registrados DE PRINCIPIO A FIN DESDE LA UI y comparados
#   con su oraculo fisico (hechos, efectos, atribucion, movimientos,
#   posiciones y relaciones).
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). La PREPARACION (cuentas como gapto_owner, categorias y
#   terceros por los writers publicos) no es parte del caso; cada caso se
#   registra solo con la UI.
#
#   Grupo (a) de esta bateria (los otros dos de (a) se ejecutan con sus E2E:
#   peluqueria + cena -> e2e_f05_06_m3.py P1/P2; previsión confirmada de la
#   luz -> e2e_f05_06_m5.py P3):
#     A2  compra con tarjeta de credito (120,00) y su liquidacion (transferencia
#         Cuenta nómina -> Tarjeta 120,00): GASTO -120 en la tarjeta una vez;
#         la liquidacion no es gasto ni ingreso (-120 / +120);
#     A3  transferencia propia 500 Cuenta nómina -> Ahorro: -500/+500, sin
#         efectos de gasto ni de ingreso;
#     A4  ingreso con categoria AMBOS («Alquileres», alquiler cobrado 750,00):
#         efecto INGRESO con esa categoria y ningun GASTO;
#     A5  devolucion contextual D-194 (Ropa 120,00 / 40,00 «Ya cobrado»), con
#         la COMPRA tambien registrada desde la UI: dos hechos, GASTO -40
#         con DEVOLUCION_DE y neto 80,00;
#     A6  gasoil reembolsable: gasto 60,00 «Repartir» con la persona que lo
#         reembolsa (tu parte 0, «te debe» Si) -> DERECHO_COBRO 60; cobro
#         60,00 -> REEMBOLSO (nunca INGRESO) y posicion CERRADA. La variante
#         con una EMPRESA como deudora no tiene camino en la UI de F05 (el
#         reparto solo admite PERSONA): NO EJECUTABLE, con su motivo;
#     A7  Preply: cargo 46,65 y devolucion 41,28 -> dos hechos conservados,
#         neto 5,37.
#   Grupo (b), solo captura y frontera (hipoteca, alquiler con IPC, compra
#   financiada): se comprueba que F05 no ofrece camino que oculte la
#   semantica (tipos del registro = GASTO, INGRESO y TRANSFERENCIA; sin
#   cuotas, financiacion, capital/intereses ni reglas en la UI) y que un
#   registro simple no infiere posiciones. Nunca se convierte en PASS lo
#   que no tiene camino: se marca NO EJECUTABLE / FRONTERA con su motivo.
#
#   Un caso que falla no detiene la bateria: queda FALLO con su detalle.
#   Capturas 393x852 @3x y manifest JSON (estado de la BD por caso).
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-07/GATE tirada nocturna, paso 6)
#   (intento 1 descartado en desarrollo: «Solo mío» en los registros personales
#   y captura de SystemExit por caso)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import traceback
import uuid
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_f05_06_m3 import oraculo, posiciones_con  # noqa: E402
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


def relaciones(dsn: str, owner: str, hecho: str) -> list:
    return sorted([a, b, str(c)] for a, b, c in _sql(
        dsn, owner, "gapto_runtime",
        "SELECT hecho_destino_id::text, tipo_relacion, importe_relacionado FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s",
        (hecho,)))


def categoria_de_efectos(dsn: str, owner: str, hecho: str) -> list:
    return sorted([a, str(b)] for a, b in _sql(
        dsn, owner, "gapto_runtime",
        "SELECT e.tipo_efecto, coalesce(c.nombre, '') FROM gapto.hecho_efectos e LEFT JOIN gapto.categorias_financieras c "
        "ON c.id = e.categoria_id WHERE e.hecho_id = %s", (hecho,)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5469")
    ap.add_argument("--api", default="http://127.0.0.1:5468")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
    _exigir_local(dsn)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    hoy = dt.datetime.now(ZoneInfo("Europe/Madrid")).date()

    # ---------------------------------------------------------------- preparacion (no es parte de los casos)
    exigir_base_recreada(dsn, owner)
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta", "CREDITO", "PASIVO")
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    ahorro = crear_cuenta(dsn, owner, "Ahorro", "AHORRO", "ACTIVO")
    cat = {k: str(uuid.uuid4()) for k in ("ropa", "electronica", "alquileres", "combustible", "formacion")}
    for k, nom, amb in (("ropa", "Ropa", "GASTO"), ("electronica", "Electrónica", "GASTO"), ("alquileres", "Alquileres", "AMBOS"),
                        ("combustible", "Combustible", "GASTO"), ("formacion", "Formación", "GASTO")):
        api(a.api, "POST", "/v1/categorias", {"id": cat[k], "nombre": nom, "parent_id": None, "ambito": amb,
                                              "presupuestable_default": True, "icon_key": None})
    ter = {k: str(uuid.uuid4()) for k in ("zara", "mediamarkt", "inquilino", "preply", "marta", "repsol")}
    for k, nom, nat in (("zara", "Zara", "EMPRESA"), ("mediamarkt", "MediaMarkt", "EMPRESA"), ("inquilino", "Inquilino Pérez", "PERSONA"),
                        ("preply", "Preply", "EMPRESA"), ("marta", "Marta (reembolsa el gasoil)", "PERSONA"),
                        ("repsol", "Repsol", "EMPRESA")):
        api(a.api, "POST", "/v1/terceros", {"id": ter[k], "nombre": nom, "naturaleza": nat})

    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy),
                 "cuentas": {"tarjeta": tarjeta, "nomina": nomina, "ahorro": ahorro}, "categorias": cat, "terceros": ter,
                 "casos": {}}
    capturas: list[str] = []
    consola: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"G2_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def inicio() -> None:
            page.goto(a.web)
            t("accion-registrar").wait_for(timeout=30000)
            page.wait_for_timeout(400)

        def faltan() -> str:
            return t("faltan").first.inner_text().strip().lower() if t("faltan").count() else ""

        def registrar(ruta: str, exito: str) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(ruta), timeout=20000) as resp:
                t("registrar").click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == 200, f"{ruta}: HTTP {resp.value.status} {cuerpo.get('codigo')}")
            t(exito).wait_for(timeout=15000)
            return cuerpo

        def gasto_ui(importe: str, categoria: str, tercero: str | None, cuenta: str, nombre: str) -> str:
            inicio()
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").fill(importe)
            if tercero:
                t("campo-tercero").click()
                t(f"tercero-{tercero}").click()
                page.wait_for_timeout(500)
            t("campo-categoria").click()
            t(f"cat-{categoria}").click()
            page.wait_for_timeout(400)
            if "presupuest" in faltan():
                t("presupuestable-true").click()
            if "cuenta" in faltan():
                t(f"cuenta-{cuenta}").click()
            elif t(f"cuenta-{cuenta}").count():
                t(f"cuenta-{cuenta}").click()
            t("solo-mio").click()  # compra personal: «Solo mío» (por defecto el reparto llega «Sin indicar»)
            shot(f"{nombre}_formulario")
            return registrar("/v1/intenciones/gasto-pagado", "registro-exito")["hecho_id"]

        def transferencia_ui(desde: str, hacia: str, importe: str, nombre: str) -> str:
            inicio()
            t("accion-registrar").click()
            t("tipo-TRANSFERENCIA").click()
            t(f"desde-{desde}").click()
            t(f"a-{hacia}").click()
            t("campo-importe").fill(importe)
            shot(f"{nombre}_formulario")
            return registrar("/v1/intenciones/transferencia", "transferencia-exito")["hecho_id"]

        def a_dia_detalle(hecho: str) -> None:
            inicio()
            t("tab-DIA").click()
            t("actividad-periodo").click()
            t("periodo-ESTE_MES").click()
            t(f"fila-{hecho}").wait_for(timeout=20000)
            t(f"fila-{hecho}").click()

        def devolucion_ui(compra: str, importe: str, nombre: str) -> tuple[str, str]:
            a_dia_detalle(compra)
            t("detalle-registrar-devolucion").wait_for(timeout=15000)
            t("detalle-registrar-devolucion").click()
            t("devolucion-origen").wait_for(timeout=15000)
            t("campo-importe").fill(importe)
            t("abono-compra").wait_for(timeout=15000)
            t("abono-compra").click()
            shot(f"{nombre}_devolucion")
            t("revisar").click()
            t("devolucion-revision").wait_for()
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/hechos/{compra}/devoluciones"),
                                      timeout=20000) as resp:
                t("registrar-devolucion").click()
            comprobar(resp.value.status == 200, f"{nombre}: HTTP {resp.value.status}")
            dev = resp.value.json()["hecho_id"]
            t("devolucion-exito").wait_for(timeout=15000)
            t("devolucion-ver-compra").click()
            t("detalle-neto").wait_for(timeout=15000)
            neto = t("detalle-neto").inner_text()
            shot(f"{nombre}_compra_con_devolucion")
            return dev, neto

        def caso(clave: str, nombre: str, fn) -> None:
            try:
                r = fn()
                res["casos"][clave] = {"nombre": nombre, "resultado": r.pop("resultado", "PASS"), **r}
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - `comprobar` sale con SystemExit; un caso no oculta los demas
                shot(f"{clave}_fallo")
                res["casos"][clave] = {"nombre": nombre, "resultado": "FALLO", "detalle": f"{type(exc).__name__}: {str(exc)[:500]}",
                                       "traza": traceback.format_exc()[-1500:]}

        page.goto(a.web)
        t("accion-registrar").wait_for(timeout=30000)

        # ------------------------------------------------------------ A2 tarjeta + liquidacion
        def a2():
            compra = gasto_ui("120", cat["electronica"], ter["mediamarkt"], tarjeta, "A2_compra")
            liq = transferencia_ui(nomina, tarjeta, "120", "A2_liquidacion")
            b1, b2 = oraculo(dsn, owner, compra), oraculo(dsn, owner, liq)
            comprobar(b1["hecho"] == [["GASTO", "120.0000"]] and ["GASTO", "120.0000", "COMPLETA"] in b1["efectos"], f"A2 compra {b1}")
            comprobar(b1["movimientos"] == [["Tarjeta", "-120.0000"]], f"A2 compra {b1}")
            comprobar(b1["posiciones"] == [], f"A2 compra: posiciones inferidas {b1}")
            comprobar(not any(e[0] in ("GASTO", "INGRESO") for e in b2["efectos"]), f"A2 liquidación con efectos {b2}")
            comprobar(b2["movimientos"] == [["Cuenta nómina", "-120.0000"], ["Tarjeta", "120.0000"]], f"A2 liquidación {b2}")
            gastos = _sql(dsn, owner, "gapto_runtime", "SELECT coalesce(sum(importe_delta), 0) FROM gapto.hecho_efectos "
                          "WHERE tipo_efecto = 'GASTO' AND hecho_id IN (%s, %s)", (compra, liq))[0][0]
            comprobar(str(gastos) == "120.0000", f"A2: gasto total {gastos}")
            return {"hechos": {"compra": compra, "liquidacion": liq}, "bd": {"compra": b1, "liquidacion": b2}}
        caso("A2", "Compra con tarjeta de crédito y su liquidación", a2)

        # ------------------------------------------------------------ A3 transferencia propia
        def a3():
            h = transferencia_ui(nomina, ahorro, "500", "A3_transferencia")
            b = oraculo(dsn, owner, h)
            comprobar(not any(e[0] in ("GASTO", "INGRESO") for e in b["efectos"]), f"A3 con efectos {b}")
            comprobar(b["movimientos"] == [["Ahorro", "500.0000"], ["Cuenta nómina", "-500.0000"]], f"A3 {b}")
            return {"hecho": h, "bd": b}
        caso("A3", "Transferencia propia (Nómina -> Ahorro 500)", a3)

        # ------------------------------------------------------------ A4 ingreso AMBOS
        def a4():
            inicio()
            t("accion-registrar").click()
            t("tipo-INGRESO").click()
            t("campo-importe").fill("750")
            t("campo-tercero").click()
            t(f"tercero-{ter['inquilino']}").click()
            t("campo-categoria").click()
            t(f"cat-{cat['alquileres']}").click()
            page.wait_for_timeout(500)
            if "presupuest" in faltan():
                t("presupuestable-true").click()
            if t(f"cuenta-{nomina}").count():
                t(f"cuenta-{nomina}").click()
            t("solo-mio").click()
            shot("A4_formulario")
            h = registrar("/v1/intenciones/ingreso-cobrado", "registro-exito")["hecho_id"]
            b = oraculo(dsn, owner, h)
            cats = categoria_de_efectos(dsn, owner, h)
            comprobar(b["hecho"] == [["INGRESO", "750.0000"]], f"A4 {b}")
            comprobar(cats == [["INGRESO", "Alquileres"]], f"A4 categorías {cats}")
            comprobar(b["movimientos"] == [["Cuenta nómina", "750.0000"]], f"A4 {b}")
            return {"hecho": h, "bd": b, "efectos_categoria": cats}
        caso("A4", "Ingreso con categoría AMBOS (alquiler cobrado)", a4)

        # ------------------------------------------------------------ A5 Ropa 120 / 40
        def a5():
            compra = gasto_ui("120", cat["ropa"], ter["zara"], tarjeta, "A5_compra")
            dev, neto = devolucion_ui(compra, "40", "A5")
            b, bd = oraculo(dsn, owner, compra), oraculo(dsn, owner, dev)
            comprobar(b["hecho"] == [["GASTO", "120.0000"]], f"A5 compra {b}")
            comprobar(["GASTO", "-40.0000", "COMPLETA"] in bd["efectos"], f"A5 devolución {bd}")
            comprobar(relaciones(dsn, owner, dev) == [[compra, "DEVOLUCION_DE", "40.0000"]], "A5 relación")
            comprobar(bd["movimientos"] == [["Tarjeta", "40.0000"]], f"A5 abono {bd}")
            comprobar("80,00 €" in neto, f"A5 neto {neto}")
            return {"hechos": {"compra": compra, "devolucion": dev}, "neto_visible": neto, "bd": {"compra": b, "devolucion": bd}}
        caso("A5", "Devolución contextual D-194 (Ropa 120 / 40)", a5)

        # ------------------------------------------------------------ A6 gasoil reembolsable
        def a6():
            inicio()
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").fill("60")
            t("campo-categoria").click()
            t(f"cat-{cat['combustible']}").click()
            page.wait_for_timeout(400)
            if "presupuest" in faltan():
                t("presupuestable-true").click()
            t("campo-tercero").click()
            t(f"tercero-{ter['repsol']}").click()
            t("repartir").click()
            t("compartido-reparto").wait_for(timeout=15000)
            t("reparto-anadir").click()
            persona_visible = t(f"persona-{ter['marta']}").count() > 0
            empresa_visible = t(f"persona-{ter['repsol']}").count() > 0
            t(f"persona-{ter['marta']}").click()
            t(f"reparto-fila-{ter['marta']}").wait_for()
            t(f"reparto-importe-{ter['marta']}").fill("60")
            intentos = {}
            for valor in ("0", ""):  # tu parte 0 y, si no vale, tu parte vacia
                t("reparto-importe-yo").fill(valor)
                shot(f"A6_reparto_tu_parte_{valor or 'vacia'}")
                t("reparto-listo").click()
                t(f"compartido-cuenta-{tarjeta}").click()
                habilitado = t("compartido-revisar").get_attribute("aria-disabled") != "true"
                aviso = page.locator("body").inner_text()
                intentos[valor or "vacia"] = {"revisar_habilitado": habilitado,
                                              "aviso": next((l for l in aviso.splitlines() if "falta" in l.lower()), "")}
                if habilitado:
                    break
                t("modo-repartir-resumen").click()
                t("compartido-reparto").wait_for(timeout=15000)
            if not any(v["revisar_habilitado"] for v in intentos.values()):
                shot("A6_no_ejecutable")
                return {"resultado": "NO EJECUTABLE", "intentos": intentos,
                        "motivo": "la UI no permite registrar un gasto pagado por ti y reembolsable al 100 %: en «Repartir» "
                                  "tu parte 0 o vacía deja «Revisar» deshabilitado («importes válidos en el reparto»); "
                                  "la variante con una EMPRESA tampoco tiene camino (el reparto solo admite PERSONA)",
                        "variante_empresa": {"resultado": "NO EJECUTABLE", "empresa_visible_en_selector": empresa_visible},
                        "persona_visible_en_selector": persona_visible}
            t("compartido-revisar").click()
            t("compartido-te-deben").wait_for()
            t(f"te-debe-{ter['marta']}-si").click()
            t("te-deben-revisar").click()
            t("compartido-revision").wait_for()
            shot("A6_revision")
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/intenciones/gasto-compartido"),
                                      timeout=20000) as resp:
                t("registrar-compartido").click()
            if resp.value.status != 200:
                cuerpo = resp.value.json()
                page.wait_for_timeout(800)
                shot("A6_rechazo_servidor")
                visible = page.locator("body").inner_text()
                escritos = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hecho_terceros WHERE tercero_id = %s",
                                (ter["repsol"],))[0][0]
                pos = posiciones_con(dsn, owner, ter["marta"])
                comprobar(escritos == 0 and pos == [], f"A6: el rechazo dejo escrituras ({escritos}, {pos})")
                return {"resultado": "NO EJECUTABLE (DEFECTO DOCUMENTADO, sin corregir)", "intentos": intentos,
                        "defecto": {"id": "DEF-G2-A6", "http": resp.value.status, "codigo": cuerpo.get("codigo"),
                                    "reproduccion": "Gasto 60 Combustible (Repsol, Tarjeta) -> Repartir -> añadir persona Marta 60 "
                                                    "-> tu parte 0: «Revisar» deshabilitado («importes válidos»); tu parte vacía: "
                                                    "«Revisar» habilitado, revisión «Tu parte: Sin indicar» + «Marta te debe», "
                                                    "«Registrar gasto» activo -> servidor 422 SUMA_NO_CUADRA",
                                    "texto_visible_tras_rechazo": [l for l in visible.splitlines() if l.strip()][:12],
                                    "fisico_tras_rechazo": {"hechos_con_repsol": escritos, "posiciones_con_marta": pos}},
                        "motivo": "un gasto pagado por ti y reembolsable al 100 % no se puede registrar desde la UI: la UI no "
                                  "admite tu parte 0 y, con tu parte vacía, deja llegar a «Registrar» una combinación que el "
                                  "servidor rechaza; la variante EMPRESA no tiene camino (el reparto solo admite PERSONA)",
                        "variante_empresa": {"resultado": "NO EJECUTABLE", "empresa_visible_en_selector": empresa_visible}}
            g = resp.value.json()["hecho_id"]
            t("compartido-exito").wait_for()
            bg = oraculo(dsn, owner, g)
            comprobar(bg["movimientos"] == [["Tarjeta", "-60.0000"]], f"A6 gasto {bg}")
            comprobar([p[:3] for p in bg["posiciones"]] == [["DERECHO_COBRO", "Marta (reembolsa el gasoil)", "ACTIVA"]], f"A6 {bg}")
            comprobar(["Marta (reembolsa el gasoil)", "60.0000"] in bg["atribuciones"], f"A6 atribución {bg}")
            # cobro del reembolso desde «Pendiente con»
            a_dia_detalle(g)
            t(f"detalle-pendiente-{ter['marta']}").wait_for(timeout=15000)
            t(f"detalle-pendiente-{ter['marta']}").click()
            t("pendiente-lista-te-debe").wait_for(timeout=15000)
            derecho = page.locator('[data-testid="pendiente-lista-te-debe"] [data-testid^="posicion-"]:visible').first \
                .get_attribute("data-testid")[len("posicion-"):]
            t(f"posicion-{derecho}").click()
            t("posicion-cobrar").click()
            t("accion-cobro").wait_for()
            t("accion-importe").fill("60")
            t(f"accion-cuenta-{nomina}").click()
            explicacion = t("accion-explicacion").inner_text()
            shot("A6_cobro")
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/posiciones/{derecho}/cobro"),
                                      timeout=20000) as resp:
                t("accion-enviar").click()
            comprobar(resp.value.status == 200, f"A6 cobro: HTTP {resp.value.status}")
            r = resp.value.json()
            t("posicion-exito").wait_for()
            bc = oraculo(dsn, owner, r["hecho_id"])
            comprobar(bc["hecho"][0][0] == "REEMBOLSO", f"A6: el reembolso no es REEMBOLSO {bc}")
            comprobar(not any(e[0] == "INGRESO" for e in bc["efectos"]), f"A6: reembolso con INGRESO {bc}")
            comprobar(bc["movimientos"] == [["Cuenta nómina", "60.0000"]], f"A6 cobro {bc}")
            comprobar((r["saldo"], r["estado"]) == ("0.00", "CERRADA"), f"A6 {r}")
            comprobar("No es un ingreso" in explicacion, f"A6: texto {explicacion}")
            return {"variante": "PERSONA", "intentos": intentos, "hechos": {"gasto": g, "reembolso": r["hecho_id"]}, "bd": {"gasto": bg, "reembolso": bc},
                    "posiciones": posiciones_con(dsn, owner, ter["marta"]),
                    "variante_empresa": {"resultado": "NO EJECUTABLE",
                                         "motivo": "el reparto de F05-06 M3 solo admite PERSONA como contraparte "
                                                   "(selector de personas; empresa visible en el selector: "
                                                   f"{empresa_visible}); no hay camino en la UI para un derecho de cobro "
                                                   "frente a una EMPRESA"},
                    "persona_visible_en_selector": persona_visible}
        caso("A6", "Gasoil reembolsable (pago + derecho de cobro; reembolso no es ingreso)", a6)

        # ------------------------------------------------------------ A7 Preply
        def a7():
            cargo = gasto_ui("46,65", cat["formacion"], ter["preply"], tarjeta, "A7_cargo")
            dev, neto = devolucion_ui(cargo, "41,28", "A7")
            b, bd = oraculo(dsn, owner, cargo), oraculo(dsn, owner, dev)
            comprobar(b["hecho"] == [["GASTO", "46.6500"]], f"A7 cargo {b}")
            comprobar(["GASTO", "-41.2800", "COMPLETA"] in bd["efectos"], f"A7 devolución {bd}")
            comprobar(relaciones(dsn, owner, dev) == [[cargo, "DEVOLUCION_DE", "41.2800"]], "A7 relación")
            comprobar("5,37 €" in neto, f"A7 neto {neto}")
            hechos = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros WHERE id IN (%s, %s) "
                          "AND estado = 'ACTIVO'", (cargo, dev))[0][0]
            comprobar(hechos == 2, f"A7: hechos conservados {hechos}")
            return {"hechos": {"cargo": cargo, "devolucion": dev}, "neto_visible": neto, "bd": {"cargo": b, "devolucion": bd}}
        caso("A7", "Preply (46,65 + devolución 41,28 = 5,37)", a7)

        # ------------------------------------------------------------ (b) captura y frontera
        def grupo_b():
            inicio()
            t("accion-registrar").click()
            tipos = sorted(x.get_attribute("data-testid") for x in page.locator('[data-testid^="tipo-"]:visible').all())
            shot("B_hoja_tipos")
            t("tipo-GASTO").click()
            t("campo-importe").wait_for()
            texto = page.locator("body").inner_text().lower()
            prohibidos = [p for p in ("cuota", "financ", "hipoteca", "capital", "intereses", "ipc", "préstamo") if p in texto]
            shot("B_formulario_gasto")
            inicio()
            t("tab-MAS").click()
            if t("mas-ajustes").count():
                t("mas-ajustes").click()
            ajustes = sorted(x.get_attribute("data-testid") for x in page.locator('[data-testid^="ajustes-"]:visible').all())
            reglas = [s for s in ajustes if re.search(r"regla|recurren|contrato", s)]
            shot("B_ajustes")
            comprobar(tipos == ["tipo-GASTO", "tipo-INGRESO", "tipo-TRANSFERENCIA"], f"B: tipos {tipos}")
            comprobar(prohibidos == [], f"B: el formulario ofrece {prohibidos}")
            pos = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
                       "JOIN gapto.actores_financieros a ON a.id = p.contraparte_actor_id WHERE a.tercero_id IS NOT NULL "
                       "AND a.tercero_id NOT IN (%s)", (ter["marta"],))[0][0]
            comprobar(pos == 0, f"B: posiciones inferidas por registros simples {pos}")
            return {"resultado": "FRONTERA VERIFICADA (captura no disponible en F05)", "tipos_registro": tipos,
                    "ajustes": ajustes, "ajustes_reglas": reglas, "posiciones_fuera_de_A6": pos,
                    "casos": {"hipoteca": "sin camino en F05 (capital/intereses y deuda: F06/F07); no se registra para no ocultar semántica",
                              "alquiler_con_IPC": "sin UI de reglas ni versiones en F05 (550 -> 561: F06); la confirmación de previsiones (M5) no versiona reglas",
                              "compra_financiada": "F-D03 asignada a F07 (F05 §46.10); sin cuotas ni financiación en el formulario"}}
        caso("B", "Grupo (b): captura y frontera (hipoteca, alquiler con IPC, compra financiada)", grupo_b)
        nav.close()

    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"G2_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    resumen = {k: v["resultado"] for k, v in res["casos"].items()}
    print(f"FIN {run}: {json.dumps(resumen, ensure_ascii=False)}")
    if any(v == "FALLO" for v in resumen.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
