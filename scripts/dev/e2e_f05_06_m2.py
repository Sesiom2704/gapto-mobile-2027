# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m2.py
# Ruta: scripts/dev/e2e_f05_06_m2.py
# Descripcion: E2E web de F05-06 M2-B (mandato §B3; F09 §12.105 DEV; lamina
#   DEV v0.1 A1-A4, B1-B4, C1/C2): devolucion contextual desde la compra.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). Preparacion por los writers publicos: categoria
#   «Ropa» y «Restaurantes», tercero «Zara», cuentas «Tarjeta BBVA»
#   (CREDITO) y «Cuenta nómina» (CORRIENTE) como gapto_owner (sin writer de
#   alta, igual que e2e_j2j3), compra «Abrigo» 120,00 € 100 % tuya con la
#   tarjeta y «Cena con amigos» 44,50 € con el reparto sin indicar.
#
#   Escenario (prioritarias automatizadas del acta, P1-P8):
#     P1/A3  detalle de la compra con «Registrar devolución»;
#     P2/A1  formulario: origen fijo, «De la compra», «Tuya» propuesta,
#            «Sí, en Tarjeta BBVA»; nunca «Ingreso» (claro y oscuro);
#     P3/A2  revision y registro de 40,00 € con «Ya cobrado» en la tarjeta;
#            confirmacion con «Devolución de Abrigo · <fecha>»; BD: GASTO
#            -40, atribucion propia, relacion DEVOLUCION_DE, movimiento +40
#            conciliado en la tarjeta;
#     P4/B3  importe 95,00 € (> 80,00 que quedan): aviso y «Revisar»
#            deshabilitado;
#     P5/C1+C2  devolucion de 30,00 € «Todavía no» (oscuro): sin movimiento;
#     P6/B1  Actividad: filas sin «+» ni «−», «Devolución» / «Abono
#            pendiente» (claro y oscuro);
#     P7/A4  ida y vuelta: detalle de la compra (devoluciones y neto 50,00)
#            -> devolucion -> «Devolución de» vuelve a la compra;
#     P8/B2  «Registrar abono» de la pendiente: hoja con la tarjeta
#            propuesta; confirmar; BD con el movimiento; y devolucion
#            pendiente de la cena (B4, «Sin indicar») con el contenedor del
#            swipe «Cobrado»: el gesto emulado en navegador no lo toma el
#            responder de RN web (NO_AUTOMATIZABLE en web, se registra en el
#            manifest); se exige que el gesto nunca registre el abono solo.
#            El gesto lo cubren jest (contenedor real) y la pasada en iPhone.
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M2-B §B3)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import decimal
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
D = decimal.Decimal


def compra(base: str, cuenta: str, categoria: str, tercero: str | None, *, importe: str, concepto: str, fecha: str,
           atribucion: str) -> str:
    iid = str(uuid.uuid4())
    cuerpo = {"intencion_id": iid, "concepto": concepto, "importe": importe, "moneda": "EUR", "fecha_hecho": fecha,
              "cuenta_id": cuenta, "presupuestable": True, "atribucion": atribucion,
              "financiacion": {"estado": "NO_DETERMINADA"}, "categoria": {"estado": "CATEGORIA", "categoria_id": categoria}}
    if tercero:
        cuerpo["tercero_id"] = tercero
    api(base, "POST", "/v1/intenciones/gasto-pagado", cuerpo)
    return iid


def estado_devolucion(dsn: str, owner: str, dev: str) -> dict:
    ef = _sql(dsn, owner, "gapto_runtime", "SELECT tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos "
                                           "WHERE hecho_id = %s", (dev,))
    rel = _sql(dsn, owner, "gapto_runtime", "SELECT hecho_destino_id::text, tipo_relacion, importe_relacionado "
                                            "FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s", (dev,))
    mov = _sql(dsn, owner, "gapto_runtime", "SELECT m.cuenta_id::text, m.importe, hm.importe_asignado "
                                            "FROM gapto.hecho_movimientos_tesoreria hm JOIN gapto.movimientos_tesoreria m "
                                            "ON m.id = hm.movimiento_tesoreria_id WHERE hm.hecho_id = %s", (dev,))
    return {"efectos": [[a, str(b), c] for a, b, c in ef], "relaciones": [[a, b, str(c)] for a, b, c in rel],
            "movimientos": [[a, str(b), str(c)] for a, b, c in mov]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5467")
    ap.add_argument("--api", default="http://127.0.0.1:5466")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
    _exigir_local(dsn)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    hoy = dt.datetime.now(ZoneInfo("Europe/Madrid")).date()
    fecha_compra = str(hoy - dt.timedelta(days=3))

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta BBVA", "CREDITO", "PASIVO")
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    ropa, rest, zara = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    api(a.api, "POST", "/v1/categorias", {"id": ropa, "nombre": "Ropa", "parent_id": None, "ambito": "GASTO",
                                          "presupuestable_default": True, "icon_key": None})
    api(a.api, "POST", "/v1/categorias", {"id": rest, "nombre": "Restaurantes", "parent_id": None, "ambito": "GASTO",
                                          "presupuestable_default": True, "icon_key": None})
    api(a.api, "POST", "/v1/terceros", {"id": zara, "nombre": "Zara", "naturaleza": "EMPRESA"})
    abrigo = compra(a.api, tarjeta, ropa, zara, importe="120.00", concepto="Abrigo", fecha=fecha_compra, atribucion="SOLO_MIO")
    cena = compra(a.api, tarjeta, rest, None, importe="44.50", concepto="Cena con amigos", fecha=fecha_compra, atribucion="SIN_INDICAR")

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy),
                 "cuentas": {"tarjeta": tarjeta, "nomina": nomina}, "compras": {"abrigo": abrigo, "cena": cena}}
    consola: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M2_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def sin_ingreso(paso: str) -> None:
            texto = page.locator("body").inner_text()
            comprobar("ingreso" not in texto.lower(), f"{paso}: aparece «Ingreso»")

        t("accion-registrar").wait_for(timeout=30000)
        t("tab-DIA").click()
        t("actividad-periodo").click()
        t("periodo-ESTE_MES").click()
        if fecha_compra[:7] != str(hoy)[:7]:
            t("actividad-periodo").click()
            t("periodo-MES_ANTERIOR").click()

        # ------------------------------------------------------------ P1 / A3
        t(f"fila-{abrigo}").wait_for(timeout=20000)
        t(f"fila-{abrigo}").click()
        t("detalle-registrar-devolucion").wait_for(timeout=15000)
        shot("P1_A3_detalle_compra")
        t("detalle-registrar-devolucion").click()

        # ------------------------------------------------------------ P2 / A1
        t("devolucion-origen").wait_for(timeout=15000)
        res["P2"] = {"origen": t("devolucion-origen").inner_text(), "categoria": t("devolucion-categoria").inner_text()}
        comprobar("Abrigo · Zara" in res["P2"]["origen"] and "120,00 €" in res["P2"]["origen"], f"P2: {res['P2']}")
        comprobar("De la compra" in res["P2"]["categoria"], f"P2: {res['P2']}")
        comprobar(t("atribucion-tuya").inner_text().startswith("✓") or t("atribucion-tuya").get_attribute("aria-checked") == "true",
                  "P2: «Tuya» no propuesta")
        t("campo-importe").fill("40")
        t("abono-compra").wait_for(timeout=15000)
        comprobar(t("abono-compra").inner_text() == "Sí, en Tarjeta BBVA", "P2: propuesta de cuenta")
        t("abono-compra").click()
        sin_ingreso("P2")
        shot("P2_A1_formulario")
        oscuro("P2_A1_formulario")

        # ------------------------------------------------------------ P3 / A2
        t("revisar").click()
        t("devolucion-revision").wait_for()
        res["P3_revision"] = t("devolucion-revision").inner_text()
        comprobar("Abono en Tarjeta BBVA" in res["P3_revision"] and "80,00 €" in res["P3_revision"], f"P3: {res['P3_revision']}")
        sin_ingreso("P3")
        shot("P3_A2_revision")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/hechos/{abrigo}/devoluciones"), timeout=20000) as resp:
            t("registrar-devolucion").click()
        comprobar(resp.value.status == 200, f"P3: HTTP {resp.value.status}")
        dev1 = resp.value.json()["hecho_id"]
        t("devolucion-exito-relacion").wait_for()
        res["P3_confirmacion"] = t("devolucion-exito-relacion").inner_text()
        comprobar(res["P3_confirmacion"].startswith("Devolución de Abrigo · "), f"P3: {res['P3_confirmacion']}")
        shot("P3_confirmacion")
        res["P3_bd"] = estado_devolucion(dsn, owner, dev1)
        comprobar(res["P3_bd"]["efectos"] == [["GASTO", "-40.0000", "COMPLETA"]], f"P3: {res['P3_bd']}")
        comprobar(res["P3_bd"]["relaciones"] == [[abrigo, "DEVOLUCION_DE", "40.0000"]], f"P3: {res['P3_bd']}")
        comprobar(res["P3_bd"]["movimientos"] == [[tarjeta, "40.0000", "40.0000"]], f"P3: {res['P3_bd']}")
        t("devolucion-hecho").click()

        # ------------------------------------------------------------ P4 / B3
        t(f"fila-{abrigo}").click()
        t("detalle-registrar-devolucion").click()
        t("devolucion-origen").wait_for(timeout=15000)
        t("campo-importe").fill("95")
        t("devolucion-supera").wait_for()
        res["P4"] = t("devolucion-supera").inner_text()
        comprobar("80,00 €" in res["P4"], f"P4: {res['P4']}")
        comprobar(t("revisar").get_attribute("aria-disabled") == "true", "P4: «Revisar» habilitado")
        shot("P4_B3_limite")

        # ------------------------------------------------------------ P5 / C1 + C2
        t("campo-importe").fill("30")
        t("abono-todavia-no").click()
        oscuro("P5_C1_todavia_no")
        t("revisar").click()
        t("devolucion-revision").wait_for()
        comprobar("Pendiente: no cuenta como dinero disponible" in t("revision-abono").inner_text(), "P5: abono no pendiente")
        oscuro("P5_C2_revision_pendiente")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/hechos/{abrigo}/devoluciones"), timeout=20000) as resp:
            t("registrar-devolucion").click()
        dev2 = resp.value.json()["hecho_id"]
        t("devolucion-exito").wait_for()
        res["P5_bd"] = estado_devolucion(dsn, owner, dev2)
        comprobar(res["P5_bd"]["movimientos"] == [], f"P5: {res['P5_bd']}")

        # ------------------------------------------------------------ P7 / A4 (ida y vuelta)
        t("devolucion-ver-compra").click()
        t("detalle-devoluciones").wait_for(timeout=15000)
        res["P7_compra"] = t("detalle-devoluciones").inner_text()
        comprobar("50,00 €" in t("detalle-neto").inner_text(), f"P7: {res['P7_compra']}")
        shot("P7_A3_compra_con_devoluciones")
        t(f"detalle-devolucion-{dev1}").click()
        t("detalle-devolucion-de").wait_for(timeout=15000)
        comprobar("Recibido en Tarjeta BBVA" in t("kv-Abono").inner_text(), "P7: abono de la primera")
        shot("P7_A4_detalle_devolucion")
        oscuro("P7_A4_detalle_devolucion")
        t("detalle-devolucion-de").click()
        t("detalle-devoluciones").wait_for(timeout=15000)
        t("detalle-cerrar").click()

        # ------------------------------------------------------------ P6 / B1
        t(f"fila-{dev2}").wait_for(timeout=15000)
        res["P6"] = {"dev1": t(f"fila-{dev1}").inner_text(), "dev2": t(f"fila-{dev2}").inner_text()}
        comprobar("Devolución · Abrigo" in res["P6"]["dev2"] and "Abono pendiente" in res["P6"]["dev2"], f"P6: {res['P6']}")
        comprobar("+" not in res["P6"]["dev1"] + res["P6"]["dev2"] and "−" not in res["P6"]["dev1"] + res["P6"]["dev2"], f"P6: {res['P6']}")
        shot("P6_B1_actividad")
        oscuro("P6_B1_actividad")

        # ------------------------------------------------------------ P8 / B2
        t(f"fila-{dev2}").click()
        t("detalle-registrar-abono").wait_for(timeout=15000)
        t("detalle-registrar-abono").click()
        t("hoja-abono").wait_for()
        t("abono-cuenta-compra").wait_for(timeout=15000)
        shot("P8_B2_abono")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/hechos/{dev2}/abono"), timeout=20000) as resp:
            t("abono-confirmar").click()
        comprobar(resp.value.status == 200, f"P8: HTTP {resp.value.status}")
        res["P8_bd"] = estado_devolucion(dsn, owner, dev2)
        comprobar(res["P8_bd"]["movimientos"] == [[tarjeta, "30.0000", "30.0000"]], f"P8: {res['P8_bd']}")
        t("detalle-cerrar").click()
        # Swipe «Cobrado» sobre una devolucion pendiente de la cena (B4: «Sin indicar»).
        t(f"fila-{cena}").click()
        t("detalle-registrar-devolucion").click()
        t("devolucion-origen").wait_for(timeout=15000)
        comprobar(t("atribucion-sin-indicar").count() == 1 and t("atribucion-todo-mio-no-disponible").count() == 1, "P8: B4")
        shot("P8_B4_sin_reparto")
        t("campo-importe").fill("8,90")
        t("abono-todavia-no").click()
        t("revisar").click()
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/hechos/{cena}/devoluciones"), timeout=20000) as resp:
            t("registrar-devolucion").click()
        dev3 = resp.value.json()["hecho_id"]
        comprobar(resp.value.json()["estado_atribucion"] == "NO_DISPONIBLE", "P8: atribucion de la cena")
        t("devolucion-hecho").click()
        fila = t(f"fila-{dev3}")
        fila.wait_for(timeout=15000)
        fila.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        comprobar(t(f"fila-swipe-{dev3}").count() == 1, "P8: la fila pendiente no admite el swipe")
        caja = fila.bounding_box()
        x0, y0 = caja["x"] + caja["width"] - 20, caja["y"] + caja["height"] / 2
        page.mouse.move(x0, y0)
        page.mouse.down()
        page.mouse.move(x0 - 120, y0, steps=12)
        page.mouse.up()
        # El responder de RN web no toma el gesto emulado (raton) y lo resuelve como toque: el swipe en navegador es
        # NO_AUTOMATIZABLE (acta). Lo que si se comprueba: el gesto nunca registra el abono por si solo.
        try:
            t("hoja-abono").wait_for(timeout=3000)
            res["P8_swipe_web"] = "abre_hoja"
            shot("P8_B2_swipe_cobrado")
            t("abono-cancelar").click()
        except Exception:
            res["P8_swipe_web"] = "NO_AUTOMATIZABLE (el gesto emulado se resuelve como toque)"
            shot("P8_B2_swipe_web_no_reproducible")
            if t("detalle-cerrar").count():
                t("detalle-cerrar").click()
        comprobar(estado_devolucion(dsn, owner, dev3)["movimientos"] == [], "P8: el swipe registro solo")
        nav.close()

    res["devoluciones"] = {"dev1": dev1, "dev2": dev2, "dev3": dev3}
    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"M2_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
