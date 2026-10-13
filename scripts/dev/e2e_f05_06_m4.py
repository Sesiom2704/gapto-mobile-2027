# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m4.py
# Ruta: scripts/dev/e2e_f05_06_m4.py
# Descripcion: E2E web de F05-06 M4 (mandato §4.6; F09 §12.105 CAP; lamina
#   CAP v0.1 A1-A4, B1-B4, C1/C2): capacidades de cuenta en Ajustes y su
#   efecto en el registro.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). Preparacion: las cuentas no tienen writer de alta y se
#   crean como gapto_owner (igual que e2e_j2j3); a dos se les quitan las filas
#   de capacidad (sin configurar) y a una se le pone un mapeo RV3 sintetico
#   (origen_v3, PD-4). Categorias, plantilla y preferencia por los writers
#   publicos. Todo cambio de capacidad se hace por la UI o por
#   /v1/cuentas/.../capacidades (el writer unico).
#
#   Escenario (claro; A1, B1, A2 y A4 tambien en oscuro):
#     A1  lista: «Sin configurar» (Cuenta ING «De V3 · …», Hucha neutra) y
#         «Tus cuentas» con su resumen;
#     B1  Cuenta ING: todo apagado, aviso de V3 y «Gapto no lo deduce…»;
#     A3  permitir «Recibir ingresos» en Cuenta ING (hoja, confirmar; fila y
#         auditoria en la BD);
#     A4  dejar de «Pagar gastos» con Cuenta nómina: la hoja lista la
#         plantilla «Alquiler» y la preferencia «Gastos de Hogar → …» antes
#         de confirmar; tras confirmar, la plantilla queda «No disponible» y
#         sigue apuntando a la misma cuenta;
#     B4  historial de Cuenta nómina;
#     B2  «¿Falta una cuenta? 1 sin configurar ›» en «Pagado con»: abre
#         Cuentas y al volver el importe sigue escrito;
#     B3  ingreso con Cuenta ING; se retira RECIBIR_INGRESO por la API; al
#         registrar, CUENTA_SIN_CAPACIDAD con el texto de B3, la cuenta ya no
#         esta y el importe se conserva; ningun hecho persistido.
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD. Los 409
#   esperados de B3 se anotan aparte de los errores de consola.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M4 F3)
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
MSG_B3 = ("Cuenta ING ya no puede recibir ingresos. Se cambió mientras registrabas. "
          "El ingreso no se ha guardado: elige otra cuenta.")


def sin_capacidades(dsn: str, owner: str, cuenta: str) -> None:
    _sql(dsn, owner, "gapto_owner", "DELETE FROM gapto.cuenta_capacidades WHERE cuenta_id = %s", (cuenta,))


def mapeo_v3(dsn: str, owner: str, cuenta: str) -> None:
    """Procedencia RV3 sintetica (mapeos_importacion, tabla_destino 'cuentas')."""
    fuente, origen = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
                                    "VALUES (%s, %s, 'DB', 'V3 sintetica E2E')", (fuente, owner))
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, "
                                    "contenedor_origen, clave_origen, datos_origen) VALUES (%s, %s, 'public.cuentas_bancarias', "
                                    "'e2e', '{}'::jsonb)", (origen, fuente))
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.mapeos_importacion (registro_origen_id, tabla_destino, "
                                    "registro_destino_id, tipo_mapping, confianza) VALUES (%s, 'cuentas', %s, 'CREADO', 'ALTA')",
         (origen, cuenta))


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

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    previas = {str(f[0]) for f in _sql(dsn, owner, "gapto_runtime", "SELECT id FROM gapto.cuentas")}
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta BBVA", "CREDITO", "PASIVO")
    ing = crear_cuenta(dsn, owner, "Cuenta ING", "CORRIENTE", "ACTIVO")
    hucha = crear_cuenta(dsn, owner, "Hucha", "EFECTIVO", "ACTIVO")
    sin_capacidades(dsn, owner, ing)
    sin_capacidades(dsn, owner, hucha)
    mapeo_v3(dsn, owner, ing)
    tipos = api(a.api, "GET", "/v1/preferencias")["tipos"]
    hogar, nom = str(uuid.uuid4()), str(uuid.uuid4())
    api(a.api, "POST", "/v1/categorias", {"id": hogar, "nombre": "Hogar", "parent_id": None, "ambito": "GASTO",
                                          "presupuestable_default": True, "icon_key": "hogar.casa"})
    api(a.api, "POST", "/v1/categorias", {"id": nom, "nombre": "Nómina", "parent_id": None, "ambito": "INGRESO",
                                          "presupuestable_default": False, "icon_key": "finanzas.dinero"})
    alquiler = str(uuid.uuid4())
    api(a.api, "POST", "/v1/plantillas", {"id": alquiler, "nombre": "Alquiler", "tipo_hecho_id": tipos["GASTO"],
                                          "cuenta_default_id": nomina})
    pref = str(uuid.uuid4())
    api(a.api, "POST", "/v1/preferencias", {"id": pref, "tipo_hecho_id": tipos["GASTO"], "categoria_id": hogar,
                                            "cuenta_default_id": nomina})

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "cuentas_previas_bootstrap": sorted(previas),
                 "cuentas": {"nomina": nomina, "tarjeta": tarjeta, "ing": ing, "hucha": hucha}}
    consola: list[str] = []
    esperados_409: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")

        def en_consola(m) -> None:
            if m.type != "error":
                return
            (esperados_409 if "409" in m.text else consola).append(m.text)

        page.on("console", en_consola)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M4_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def interruptor(cap: str) -> None:
            t(f"cap-{cap}-interruptor").click()

        t("accion-registrar").wait_for(timeout=30000)
        # ------------------------------------------------------------ A1
        t("tab-MAS").click()
        t("mas-ajustes").click()
        t("ajustes-cuentas").click()
        t("cap-grupo-sin-configurar").wait_for(timeout=15000)
        res["A1"] = {"ing": t(f"cap-fila-{ing}-detalle").inner_text(), "hucha": t(f"cap-fila-{hucha}-detalle").inner_text(),
                     "nomina": t(f"cap-fila-{nomina}-detalle").inner_text()}
        comprobar(res["A1"]["ing"] == "De V3 · aún no puede hacer nada", f"A1 ING: {res['A1']}")
        comprobar(res["A1"]["hucha"] == "Aún no puede hacer nada", f"A1 Hucha: {res['A1']}")
        comprobar(t("cap-grupo-sin-configurar").locator(f'[data-testid="cap-fila-{nomina}"]').count() == 0, "A1: nómina en «Sin configurar»")
        shot("A1_lista")
        oscuro("A1_lista")

        # ------------------------------------------------------------ B1 + A3
        t(f"cap-fila-{ing}").click()
        t("cap-sin-configurar").wait_for(timeout=15000)
        comprobar("viene de V3" in t("cap-sin-configurar").inner_text(), "B1: sin aviso de V3")
        comprobar(t("cap-no-deduce").inner_text() == "Todo empieza desactivado: Gapto no lo deduce del tipo de cuenta.", "B1: no-deduce")
        texto = page.locator("body").inner_text().lower()
        comprobar(not any(x in texto for x in ("suger", "recomend")), "B1: aparece una sugerencia")
        shot("B1_cuenta_v3")
        oscuro("B1_cuenta_v3")
        interruptor("RECIBIR_INGRESO")
        t("cap-hoja-activar").wait_for()
        comprobar("Lo ya registrado no cambia." in t("cap-hoja-consecuencia").inner_text(), "A3: falta «Lo ya registrado no cambia»")
        shot("A3_activar")
        t("cap-hoja-confirmar").click()
        t("cap-hoja-activar").wait_for(state="detached")
        res["A3_bd"] = {"caps": [f[0] for f in _sql(dsn, owner, "gapto_runtime", "SELECT capacidad_codigo FROM gapto.cuenta_capacidades WHERE cuenta_id = %s", (ing,))],
                        "auditoria": [list(map(str, f)) for f in _sql(dsn, owner, "gapto_runtime", "SELECT accion, motivo FROM gapto.auditoria WHERE tabla = 'cuentas' AND registro_id = %s", (ing,))]}
        comprobar(res["A3_bd"]["caps"] == ["RECIBIR_INGRESO"], f"A3: BD {res['A3_bd']}")
        comprobar(res["A3_bd"]["auditoria"] == [["ACTUALIZAR", "F05-06 CAPACIDAD ACTIVAR"]], f"A3: auditoria {res['A3_bd']}")
        t("cap-detalle-atras").click()

        # ------------------------------------------------------------ A2 + A4 + B4
        t(f"cap-fila-{nomina}").click()
        t("cap-registro").wait_for(timeout=15000)
        shot("A2_detalle")
        oscuro("A2_detalle")
        interruptor("PAGAR_GASTO")
        t("cap-impacto").wait_for(timeout=15000)
        res["A4_lineas"] = [t(f"cap-impacto-{i}").inner_text() for i in range(2)]
        comprobar(res["A4_lineas"] == ["· Plantilla «Alquiler»", "· Preferencia «Gastos de Hogar → Cuenta nómina»"], f"A4: {res['A4_lineas']}")
        shot("A4_desactivar")
        oscuro("A4_desactivar")
        t("cap-hoja-confirmar").click()
        t("cap-hoja-desactivar").wait_for(state="detached")
        plt = next(p for p in api(a.api, "GET", "/v1/plantillas")["plantillas"] if p["id"] == alquiler)
        prf = next(p for p in api(a.api, "GET", "/v1/preferencias")["preferencias"] if p["id"] == pref)
        res["A4_despues"] = {"plantilla": {"cuenta": plt["cuenta_default_id"], "avisos": plt["avisos"]},
                             "preferencia": {"cuenta": prf["cuenta_default_id"], "disponible": prf["cuenta_disponible_hoy"]}}
        comprobar(plt["cuenta_default_id"] == nomina and {"campo": "cuenta", "motivo": "NO_ELEGIBLE"} in plt["avisos"], f"A4: plantilla {res['A4_despues']}")
        comprobar(prf["cuenta_default_id"] == nomina and prf["cuenta_disponible_hoy"] is False, f"A4: preferencia {res['A4_despues']}")
        t("cap-abrir-historial").click()
        t("cap-historial-lista").wait_for(timeout=15000)
        res["B4"] = t("cap-historial-lista").inner_text()
        comprobar("Ya no permitido: Pagar gastos" in res["B4"], f"B4: {res['B4']}")
        shot("B4_historial")
        t("cap-historial-atras").click()
        t("cap-detalle-atras").click()
        t("cap-atras").click()

        # ------------------------------------------------------------ B2
        t("tab-INICIO").click()
        t("accion-registrar").click()
        t("tipo-GASTO").click()
        t("campo-importe").fill("23,40")
        t("falta-cuenta").wait_for(timeout=15000)
        res["B2"] = t("falta-cuenta").inner_text()
        comprobar(res["B2"] == "¿Falta una cuenta? 1 sin configurar ›", f"B2: {res['B2']}")
        shot("B2_aviso_pagado_con")
        t("falta-cuenta").click()
        t("panel-cuentas").wait_for()
        shot("B2_cuentas_desde_registro")
        t("cap-atras").click()
        t("panel-cuentas").wait_for(state="detached")
        comprobar(t("campo-importe").input_value() == "23,40", "B2: el importe no se conserva")
        t("cancelar").click()
        if t("descartar").count():
            t("descartar").click()

        # ------------------------------------------------------------ B3
        t("accion-registrar").click()
        t("tipo-INGRESO").click()
        t("campo-importe").fill("1500")
        t("campo-categoria").click()
        t(f"cat-{nom}").click()
        if t("presupuestable-false").count():
            t("presupuestable-false").click()
        t(f"cuenta-{ing}").wait_for(timeout=15000)
        t(f"cuenta-{ing}").click()
        rv = api(a.api, "GET", f"/v1/cuentas/{ing}/capacidades")["row_version"]
        api(a.api, "POST", f"/v1/cuentas/{ing}/capacidades/RECIBIR_INGRESO/desactivar", {"row_version": rv})
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/intenciones/ingreso-cobrado"), timeout=20000) as resp:
            t("registrar").click()
        res["B3_http"] = [resp.value.status, resp.value.json()]
        comprobar(resp.value.status == 409 and resp.value.json()["codigo"] == "CUENTA_SIN_CAPACIDAD", f"B3: {res['B3_http']}")
        t("error-dominio").wait_for()
        res["B3_ui"] = t("error-dominio").inner_text()
        comprobar(res["B3_ui"] == f"{MSG_B3} El resto del formulario se conserva.", f"B3: texto {res['B3_ui']}")
        page.wait_for_timeout(800)
        comprobar(t(f"cuenta-{ing}").count() == 0, "B3: la cuenta sigue disponible")
        comprobar(t("campo-importe").input_value() == "1500", "B3: el importe no se conserva")
        shot("B3_conflicto")
        oscuro("B3_conflicto")
        res["B3_hechos"] = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros")[0][0]
        comprobar(res["B3_hechos"] == 0, f"B3: hechos persistidos {res['B3_hechos']}")
        nav.close()

    res["capturas"] = capturas
    res["errores_consola"] = consola
    res["errores_409_esperados_B3"] = esperados_409
    (salida / f"M4_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
