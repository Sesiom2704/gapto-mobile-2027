# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m3.py
# Ruta: scripts/dev/e2e_f05_06_m3.py
# Descripcion: E2E web de F05-06 M3 (mandato §B3; lamina REP v0.2; F05
#   §49.16.3 GD-3, §51.4 M3, §57): GD-3 «peluqueria + cena» de principio a
#   fin DESDE LA UI y comparado con su oraculo fisico.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). Preparacion por los writers publicos: categorias
#   «Cuidado personal» y «Restaurantes», terceros «Peluquería Lola» y «La
#   Tagliatella» (EMPRESA) y «Tania» (PERSONA); cuentas «Tarjeta BBVA»
#   (CREDITO), «Cuenta nómina» (CORRIENTE) y «Efectivo» (EFECTIVO) como
#   gapto_owner (sin writer de alta, igual que e2e_j2j3). «Carlos» se crea
#   desde la UI (E7).
#
#   Escenario (prioritarias automatizadas del acta, P1-P9):
#     P1/A1+A2  peluqueria 15,00 €: registro -> «Otra persona» -> Tania ->
#               «Sí, le debo 15,00 €» -> revision en cuatro bloques -> OP-22.
#               BD: GASTO 15 COMPLETA mio, aportacion de Tania, sin
#               movimiento, una OBLIGACION_PAGO con Tania;
#     P2/B1-B4  cena 44,50 €: «Repartir» -> Tania y Carlos (alta en el
#               momento, E7) -> «A partes iguales» (14,83/14,83/14,84) ->
#               14,50/15/15 -> Tarjeta BBVA -> «¿Te deben su parte?» Tania
#               sí, Carlos invitado -> revision -> OP-22. BD: GASTO 44,50
#               COMPLETA (14,50/15/15), aportacion mia, movimiento -44,50 en
#               la tarjeta, un DERECHO_COBRO con Tania y nada con Carlos;
#     P3/C1+D2  «Pendiente con Tania» desde el detalle: te debe 15, le debes
#               15, neto 0,00 € que no salda nada (claro y oscuro); BD: las
#               dos posiciones siguen ACTIVAS (sin extincion);
#     P4/E5     Ajustes › Terceros › Tania: «Pendiente con Tania» encima de
#               «Ver sus registros»; Carlos (invitado) sin fila;
#     P5/E6     «Corregir reparto» de la cena: excluidos atenuados con su
#               motivo; yo 9,50 y Tania 20,00; revision de impacto; motivo.
#               BD: atribuciones 9,50/20/15, derecho 20, total, aportacion y
#               movimiento intactos;
#     P6/C2+C3  cobro parcial de 5,00 € en la nomina: movimiento +5; sigue
#               pendiente 15;
#     P7/E8     pago de la peluqueria con Efectivo (sin «Lo pagó otra
#               persona»): movimiento -15; obligacion CERRADA;
#     P8        perdonar los 15 que quedan: sin movimiento; derecho CERRADO;
#     P9        «Pendiente con Tania» sin nada pendiente; E5 desaparece.
#   C4 («Sin determinar») exige una posicion con apertura indeterminada (V3):
#   no se crea desde la UI; lo cubren jest y test_199 (acta: con script).
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M3 §B3)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import uuid
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


def oraculo(dsn: str, owner: str, hecho: str) -> dict:
    """Estado fisico del hecho: efectos, atribuciones, aportaciones, movimientos y posiciones."""
    q = lambda sql: _sql(dsn, owner, "gapto_runtime", sql, (hecho,))  # noqa: E731
    nombre = ("COALESCE((SELECT t.nombre FROM gapto.actores_financieros a JOIN gapto.terceros t ON t.id = a.tercero_id "
              "WHERE a.id = {c}), 'YO')")
    return {
        "hecho": [[a, str(b)] for a, b in q("SELECT t.codigo, h.importe_total FROM gapto.hechos_financieros h "
                                            "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id = %s")],
        "efectos": sorted([a, str(b), c] for a, b, c in q(
            "SELECT tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos WHERE hecho_id = %s")),
        "atribuciones": sorted([a, str(b)] for a, b in q(
            f"SELECT {nombre.format(c='x.actor_id')}, x.importe_atribuido FROM gapto.efecto_atribuciones x "
            "JOIN gapto.hecho_efectos e ON e.id = x.efecto_id WHERE e.hecho_id = %s AND e.tipo_efecto = 'GASTO'")),
        "aportaciones": sorted([a, str(b)] for a, b in q(
            f"SELECT {nombre.format(c='p.actor_id')}, p.importe FROM gapto.hecho_aportaciones_pago p WHERE p.hecho_id = %s")),
        "movimientos": sorted([a, str(b)] for a, b in q(
            "SELECT c.nombre, m.importe FROM gapto.hecho_movimientos_tesoreria hm JOIN gapto.movimientos_tesoreria m "
            "ON m.id = hm.movimiento_tesoreria_id JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE hm.hecho_id = %s")),
        "posiciones": sorted([a, b, c, str(d)] for a, b, c, d in q(
            f"SELECT p.tipo, {nombre.format(c='p.contraparte_actor_id')}, p.estado, e.importe_delta "
            "FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras p ON p.entidad_id = v.entidad_id "
            "JOIN gapto.hecho_efectos e ON e.id = v.efecto_id WHERE v.hecho_id = %s")),
    }


def posiciones_con(dsn: str, owner: str, tercero: str) -> list:
    """Todas las posiciones con la persona (estado y motivo de cierre)."""
    return sorted([a, b, c] for a, b, c in _sql(dsn, owner, "gapto_runtime",
        "SELECT p.tipo, p.estado, COALESCE(p.motivo_cierre, '') FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.actores_financieros a ON a.id = p.contraparte_actor_id WHERE a.tercero_id = %s", (tercero,)))


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

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta BBVA", "CREDITO", "PASIVO")
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    efectivo = crear_cuenta(dsn, owner, "Efectivo", "EFECTIVO", "ACTIVO")
    cuidado, rest = str(uuid.uuid4()), str(uuid.uuid4())
    lola, tagli, tania = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for cid, nom in ((cuidado, "Cuidado personal"), (rest, "Restaurantes")):
        api(a.api, "POST", "/v1/categorias", {"id": cid, "nombre": nom, "parent_id": None, "ambito": "GASTO",
                                              "presupuestable_default": True, "icon_key": None})
    for tid, nom, nat in ((lola, "Peluquería Lola", "EMPRESA"), (tagli, "La Tagliatella", "EMPRESA"), (tania, "Tania", "PERSONA")):
        api(a.api, "POST", "/v1/terceros", {"id": tid, "nombre": nom, "naturaleza": nat})

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy),
                 "cuentas": {"tarjeta": tarjeta, "nomina": nomina, "efectivo": efectivo},
                 "terceros": {"lola": lola, "tagliatella": tagli, "tania": tania}}
    consola: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M3_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def texto() -> str:
            return page.locator("body").inner_text()

        def post(ruta_final: str, testid: str) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(ruta_final), timeout=20000) as resp:
                t(testid).click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == 200, f"{ruta_final}: HTTP {resp.value.status} {cuerpo.get('codigo')}")
            return cuerpo

        def comun(importe: str, categoria: str, comercio: str) -> None:
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").fill(importe)
            t("campo-categoria").click()
            t(f"cat-{categoria}").click()
            t("presupuestable-true").click()
            t("campo-tercero").click()
            t(f"tercero-{comercio}").click()

        def a_dia() -> None:
            t("tab-DIA").click()
            t("actividad-periodo").click()
            t("periodo-ESTE_MES").click()

        t("accion-registrar").wait_for(timeout=30000)

        # ------------------------------------------------------------ P1 / A1 + A2 peluqueria
        comun("15", cuidado, lola)
        t("otra-persona").click()
        t("compartido-base").wait_for(timeout=15000)
        comprobar("15,00 €" in t("compartido-base").inner_text() and "Peluquería Lola" in t("compartido-base").inner_text(), "P1: base")
        t("pagador-persona").click()
        t("selector-persona").wait_for()
        comprobar(t(f"persona-{lola}").count() == 0 and t(f"persona-{tagli}").count() == 0, "P1: empresas en el selector")
        shot("P1_E7_selector_personas")
        t(f"persona-{tania}").click()
        t("le-debo-si").wait_for()
        comprobar(t("le-debo-si").inner_text().endswith("Sí, le debo 15,00 €"), f"P1: {t('le-debo-si').inner_text()}")
        t("le-debo-si").click()
        shot("P1_A1_pagado_por_tania")
        oscuro("P1_A1_pagado_por_tania")
        t("compartido-revisar").click()
        t("compartido-revision").wait_for()
        res["P1_revision"] = t("compartido-revision").inner_text()
        for frag in ("Total del hecho", "Solo tuyo", "Pagó Tania", "No sale dinero de tus cuentas", "Le debes a Tania", "Nueva obligación"):
            comprobar(frag in res["P1_revision"], f"P1: falta «{frag}»")
        shot("P1_A2_revision")
        p1 = post("/v1/intenciones/gasto-compartido", "registrar-compartido")
        pelu = p1["hecho_id"]
        t("compartido-exito").wait_for()
        shot("P1_exito")
        res["P1_bd"] = oraculo(dsn, owner, pelu)
        b = res["P1_bd"]
        comprobar(b["hecho"] == [["GASTO", "15.0000"]], f"P1: {b}")
        comprobar(["GASTO", "15.0000", "COMPLETA"] in b["efectos"], f"P1: {b}")
        comprobar(b["atribuciones"] == [["YO", "15.0000"]], f"P1: {b}")
        comprobar(b["aportaciones"] == [["Tania", "15.0000"]], f"P1: {b}")
        comprobar(b["movimientos"] == [], f"P1: {b}")
        comprobar([p[:3] for p in b["posiciones"]] == [["OBLIGACION_PAGO", "Tania", "ACTIVA"]], f"P1: {b}")
        t("compartido-hecho").click()

        # ------------------------------------------------------------ P2 / B1-B4 cena
        comun("44,50", rest, tagli)
        t("repartir").click()
        t("compartido-reparto").wait_for(timeout=15000)
        t("reparto-anadir").click()
        t(f"persona-{tania}").click()
        t(f"reparto-fila-{tania}").wait_for()
        t("reparto-anadir").click()
        t("selector-persona-buscar").fill("Carlos")
        t("selector-persona-crear").click()
        carlos = None
        for _ in range(50):
            filas = page.locator('[data-testid^="reparto-fila-"]:visible')
            ids = [filas.nth(i).get_attribute("data-testid")[len("reparto-fila-"):] for i in range(filas.count())]
            nuevos = [x for x in ids if x not in ("yo", tania)]
            if nuevos:
                carlos = nuevos[0]
                break
            page.wait_for_timeout(200)
        comprobar(carlos is not None, "P2: Carlos no se creo desde el selector")
        res["terceros"]["carlos"] = carlos
        comprobar(_sql(dsn, owner, "gapto_runtime", "SELECT naturaleza FROM gapto.terceros WHERE id = %s", (carlos,)) == [("PERSONA",)], "P2: Carlos no es PERSONA")
        t("reparto-iguales").click()
        iguales = [t(f"reparto-importe-{x}").input_value() for x in ("yo", tania, carlos)]
        res["P2_iguales"] = iguales
        comprobar(iguales == ["14,83", "14,83", "14,84"], f"P2: {iguales}")
        shot("P2_B2_partes_iguales")
        t("reparto-importe-yo").fill("14,50")
        t(f"reparto-importe-{tania}").fill("15")
        t(f"reparto-importe-{carlos}").fill("")
        comprobar(t("reparto-falta").inner_text() == "15,00 € · sin indicar", f"P2: {t('reparto-falta').inner_text()}")
        oscuro("P2_D1_reparto_incompleto")
        t(f"reparto-importe-{carlos}").fill("15")
        comprobar(t("reparto-falta").inner_text() == "0,00 €", "P2: falta por repartir")
        shot("P2_B2_reparto")
        t("reparto-listo").click()
        t("modo-repartir-resumen").wait_for()
        comprobar(t("modo-repartir-resumen").inner_text().startswith("3 personas · tú 14,50 €"), "P2: B1")
        t(f"compartido-cuenta-{tarjeta}").click()
        shot("P2_B1_formulario")
        t("compartido-revisar").click()
        t("compartido-te-deben").wait_for()
        t(f"te-debe-{tania}-si").click()
        t(f"te-debe-{carlos}-no").click()
        shot("P2_B3_te_deben")
        t("te-deben-revisar").click()
        t("compartido-revision").wait_for()
        res["P2_revision"] = t("compartido-revision").inner_text()
        for frag in ("44,50 €", "14,50 €", "Tarjeta BBVA", "−44,50 €", "Tania te debe", "Nuevo derecho de cobro"):
            comprobar(frag in res["P2_revision"], f"P2: falta «{frag}»")
        comprobar("Carlos te debe" not in res["P2_revision"], "P2: Carlos debe")
        shot("P2_B4_revision")
        oscuro("P2_B4_revision")
        cena = post("/v1/intenciones/gasto-compartido", "registrar-compartido")["hecho_id"]
        t("compartido-exito").wait_for()
        res["P2_bd"] = oraculo(dsn, owner, cena)
        b = res["P2_bd"]
        comprobar(b["hecho"] == [["GASTO", "44.5000"]], f"P2: {b}")
        comprobar(["GASTO", "44.5000", "COMPLETA"] in b["efectos"], f"P2: {b}")
        comprobar(b["atribuciones"] == [["Carlos", "15.0000"], ["Tania", "15.0000"], ["YO", "14.5000"]], f"P2: {b}")
        comprobar(b["aportaciones"] == [["YO", "44.5000"]], f"P2: {b}")
        comprobar(b["movimientos"] == [["Tarjeta BBVA", "-44.5000"]], f"P2: {b}")
        comprobar([p[:3] for p in b["posiciones"]] == [["DERECHO_COBRO", "Tania", "ACTIVA"]], f"P2: {b}")
        comprobar(posiciones_con(dsn, owner, carlos) == [], "P2: posicion con Carlos (invitado)")
        t("compartido-hecho").click()

        # ------------------------------------------------------------ P3 / C1 + D2
        a_dia()
        t(f"fila-{cena}").wait_for(timeout=20000)
        t(f"fila-{cena}").click()
        t(f"detalle-pendiente-{tania}").wait_for(timeout=15000)
        comprobar(t(f"detalle-pendiente-{carlos}").count() == 0, "P3: Carlos con pendiente")
        t("detalle-corregir-reparto").wait_for()
        shot("P3_detalle_cena")
        t(f"detalle-pendiente-{tania}").click()
        t("pendiente-lista-te-debe").wait_for(timeout=15000)
        res["P3"] = t("pendiente-con").inner_text()
        comprobar(t("pendiente-te-debe").inner_text() == "15,00 €" and t("pendiente-le-debes").inner_text() == "15,00 €", f"P3: {res['P3']}")
        comprobar(t("pendiente-neto").inner_text().startswith("Neto: 0,00 €. Es un cálculo: no salda nada"), f"P3: {res['P3']}")
        comprobar("Compensar" not in texto(), "P3: «Compensar»")
        shot("P3_C1_pendiente_con_tania")
        oscuro("P3_D2_pendiente_con_tania")
        res["P3_bd"] = posiciones_con(dsn, owner, tania)
        comprobar(res["P3_bd"] == [["DERECHO_COBRO", "ACTIVA", ""], ["OBLIGACION_PAGO", "ACTIVA", ""]], f"P3: {res['P3_bd']}")
        t("pendiente-atras").click()

        # ------------------------------------------------------------ P4 / E5
        t("tab-MAS").click()
        if t("mas-ajustes").count():
            t("mas-ajustes").click()
        t("ajustes-terceros").click()
        t(f"ajter-fila-{tania}").click()
        t("ajter-pendiente").wait_for(timeout=15000)
        res["P4"] = t("ajter-pendiente").inner_text()
        comprobar("Te debe 15,00 € · Le debes 15,00 €" in res["P4"], f"P4: {res['P4']}")
        shot("P4_E5_ficha_tania")
        if t("ajter-cancelar").count():
            t("ajter-cancelar").click()
        t(f"ajter-fila-{carlos}").click()
        t("ajter-ver-registros").wait_for(timeout=15000)
        page.wait_for_timeout(800)
        comprobar(t("ajter-pendiente").count() == 0, "P4: Carlos con «Pendiente con»")
        if t("ajter-cancelar").count():
            t("ajter-cancelar").click()

        # ------------------------------------------------------------ P5 / E6 corregir reparto
        a_dia()
        t(f"fila-{cena}").click()
        t("detalle-corregir-reparto").wait_for(timeout=15000)
        t("detalle-corregir-reparto").click()
        t("corregir-form").wait_for(timeout=15000)
        atenuadas = page.locator('[data-testid^="corregir-"][aria-disabled="true"]:visible').count()
        res["P5_atenuadas"] = atenuadas
        for frag in ("Todavía no se puede añadir", "Todavía no se puede sacar", "estaba invitado", "usa «Perdonar»"):
            comprobar(frag in texto(), f"P5: falta el motivo «{frag}»")
        shot("P5_E6_corregir_atenuados")
        oscuro("P5_E6_corregir_atenuados")
        ids = {p["nombre"]: p["atribucion_id"] for p in api(a.api, "GET", f"/v1/hechos/{cena}/reparto")["partes"]}
        t(f"corregir-importe-{ids['Tú']}").fill("9,50")
        t(f"corregir-importe-{ids['Tania']}").fill("20")
        t("corregir-revisar").click()
        t("corregir-revision").wait_for()
        res["P5_revision"] = t("corregir-revision").inner_text()
        for frag in ("14,50 € → 9,50 €", "Lo que Tania te debe: 15,00 € → 20,00 €", "−5,00 €", "44,50 €"):
            comprobar(frag in res["P5_revision"], f"P5: falta «{frag}»")
        t("corregir-motivo-0").click()
        shot("P5_E6_revision_impacto")
        post(f"/v1/hechos/{cena}/reparto", "corregir-guardar")
        t("corregir-exito").wait_for()
        res["P5_bd"] = oraculo(dsn, owner, cena)
        b = res["P5_bd"]
        comprobar(b["atribuciones"] == [["Carlos", "15.0000"], ["Tania", "20.0000"], ["YO", "9.5000"]], f"P5: {b}")
        comprobar(b["aportaciones"] == [["YO", "44.5000"]] and b["movimientos"] == [["Tarjeta BBVA", "-44.5000"]], f"P5: {b}")
        comprobar(b["hecho"] == [["GASTO", "44.5000"]], f"P5: {b}")
        comprobar([p[:3] for p in b["posiciones"]] == [["DERECHO_COBRO", "Tania", "ACTIVA"]] and abs(float(b["posiciones"][0][3])) == 20.0, f"P5: {b}")
        t("corregir-hecho").click()

        # ------------------------------------------------------------ P6 / C2 + C3 cobro parcial
        page.wait_for_timeout(800)  # la raiz reabre el detalle de la cena tras corregir (ida y vuelta)
        if t("hoja-detalle").count() == 0:
            t(f"fila-{cena}").click()
        t(f"detalle-pendiente-{tania}").wait_for(timeout=15000)
        t(f"detalle-pendiente-{tania}").click()
        t("pendiente-lista-te-debe").wait_for(timeout=15000)
        comprobar(t("pendiente-te-debe").inner_text() == "20,00 €", "P6: el derecho no refleja la correccion")
        derecho = page.locator('[data-testid="pendiente-lista-te-debe"] [data-testid^="posicion-"]:visible').first.get_attribute("data-testid")[len("posicion-"):]
        obligacion = page.locator('[data-testid="pendiente-lista-le-debes"] [data-testid^="posicion-"]:visible').first.get_attribute("data-testid")[len("posicion-"):]
        t(f"posicion-{derecho}").click()
        t("posicion-cobrar").wait_for()
        shot("P6_C2_acciones")
        t("posicion-cobrar").click()
        t("accion-cobro").wait_for()
        t("accion-importe").fill("5")
        t(f"accion-cuenta-{nomina}").wait_for(timeout=15000)
        comprobar(t(f"accion-cuenta-{tarjeta}").count() == 0, "P6: la tarjeta (sin RECIBIR_INGRESO) se ofrece para cobrar")
        t(f"accion-cuenta-{nomina}").click()
        comprobar("No es un ingreso" in t("accion-explicacion").inner_text(), "P6: texto C3")
        shot("P6_C3_cobro")
        r6 = post(f"/v1/posiciones/{derecho}/cobro", "accion-enviar")
        comprobar(r6["saldo"] == "15.00", f"P6: {r6}")
        t("posicion-exito").wait_for()
        res["P6_bd"] = oraculo(dsn, owner, r6["hecho_id"])
        comprobar(res["P6_bd"]["movimientos"] == [["Cuenta nómina", "5.0000"]], f"P6: {res['P6_bd']}")
        t("posicion-exito-volver").click()

        # ------------------------------------------------------------ P7 / E8 pago
        t(f"posicion-{obligacion}").wait_for(timeout=15000)
        t(f"posicion-{obligacion}").click()
        t("posicion-pagar").click()
        t("accion-pago").wait_for()
        comprobar("no está disponible en esta versión" in t("accion-sin-tercero").inner_text(), "P7: E8")
        t(f"accion-cuenta-{efectivo}").wait_for(timeout=15000)
        t(f"accion-cuenta-{efectivo}").click()
        shot("P7_E8_pago")
        r7 = post(f"/v1/posiciones/{obligacion}/pago", "accion-enviar")
        comprobar(r7["estado"] == "CERRADA", f"P7: {r7}")
        t("posicion-exito").wait_for()
        res["P7_bd"] = oraculo(dsn, owner, r7["hecho_id"])
        comprobar(res["P7_bd"]["movimientos"] == [["Efectivo", "-15.0000"]], f"P7: {res['P7_bd']}")
        t("posicion-exito-volver").click()

        # ------------------------------------------------------------ P8 perdon
        t(f"posicion-{derecho}").wait_for(timeout=15000)
        t(f"posicion-{derecho}").click()
        t("posicion-perdonar").click()
        t("accion-perdon").wait_for()
        comprobar(t(f"accion-cuenta-{nomina}").count() == 0, "P8: el perdon pide cuenta")
        comprobar(t("accion-importe").input_value() == "15,00", "P8: importe propuesto")
        shot("P8_perdon")
        r8 = post(f"/v1/posiciones/{derecho}/perdon", "accion-enviar")
        comprobar(r8["estado"] == "CERRADA", f"P8: {r8}")
        t("posicion-exito").wait_for()
        res["P8_bd"] = oraculo(dsn, owner, r8["hecho_id"])
        comprobar(res["P8_bd"]["movimientos"] == [], f"P8: {res['P8_bd']}")
        t("posicion-exito-volver").click()

        # ------------------------------------------------------------ P9 nada pendiente
        t("pendiente-nada").wait_for(timeout=15000)
        shot("P9_nada_pendiente")
        res["P9_bd"] = posiciones_con(dsn, owner, tania)
        comprobar([p[:2] for p in res["P9_bd"]] == [["DERECHO_COBRO", "CERRADA"], ["OBLIGACION_PAGO", "CERRADA"]], f"P9: {res['P9_bd']}")
        t("pendiente-atras").click()
        t("tab-MAS").click()
        t(f"ajter-fila-{tania}").click()
        t("ajter-ver-registros").wait_for(timeout=15000)
        page.wait_for_timeout(800)
        comprobar(t("ajter-pendiente").count() == 0, "P9: E5 sigue con nada pendiente")
        nav.close()

    res["hechos"] = {"peluqueria": pelu, "cena": cena}
    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"M3_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
