# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_d052_c03.py
# Ruta: scripts/dev/e2e_f05_d052_c03.py
# Descripcion: E2E web de C-03 «gasto propio reembolsable» (F05-D052 paso 2;
#   F05 §66.2 y anexo §66.A; lamina F05-07 v0.3 C1–C4; CONTRATO_API_C03).
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***
#
#   Exige la base dev RECIEN RECREADA con el catalogo sintetico del seed
#   (bootstrap_dev_db.py --recrear y --seed-categorias) y la API de una rama con
#   la ruta POST /v1/intenciones/gasto-reembolsable. Preparacion por la API
#   publica: terceros «Empresa SL» (EMPRESA), «Tania» (PERSONA), «Repsol»
#   (EMPRESA, comercio) y «Ayuntamiento» (ORGANISMO); segunda cuenta «Cuenta
#   nómina» como gapto_owner (igual que e2e_j2j3). Escenario desde la UI:
#     R1  60,00 € Combustible (Litros 41,5), comercio Repsol, «Mío, pero me lo
#         reembolsan»: en C2 nada marcado y «Hecho» deshabilitado; el selector
#         ofrece Empresa SL y Tania y no Repsol ni Ayuntamiento; Empresa SL,
#         «Otra cantidad» 70 (no deja) y 40; C3 con «Cuenta en tu Resultado
#         60,00 €» y «Te debe Empresa SL 40,00 €».
#     R2  30,00 € sin comercio, Tania, «Todo» (PERSONA, recuperacion total).
#     R3  25,00 €, Empresa SL, «Todo» (segundo derecho con la misma empresa).
#     C4  Dia a dia › detalle de R1 › «Pendiente con Empresa SL» (entidad de
#         R1) › «Registrar cobro»: deshabilitado sin cuenta; cobro de 15 →
#         «Cobro registrado · quedan 25,00 €»; cobro de 25 → «Saldado · no
#         cuenta como ingreso». El derecho de R3 no cambia.
#     D   Detalle de R1 › «Registrar devolucion»: no disponible, con su motivo.
#   Oraculo: POST capturados y sus respuestas; GET /v1/hechos/{id}/reparto
#   (posiciones_vinculadas: saldo y estado por entidad); BD como gapto_runtime
#   (solo lectura): ningun hecho INGRESO ni devolucion creados.
#   Capturas 393x852 @3x (claro y oscuro) y manifest JSON.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-D052 paso 2 · C-03 UI)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import pathlib
import sys
import uuid

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, servidor_web  # noqa: E402

_spec = importlib.util.spec_from_file_location("bootstrap_dev_db", pathlib.Path(__file__).with_name("bootstrap_dev_db.py"))
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"
RUTA = "/v1/intenciones/gasto-reembolsable"


def vinculadas(base: str, hecho: str) -> dict:
    """{entidad_id: [saldo, estado]} de las posiciones vinculadas del hecho (lectura HTTP)."""
    return {x["entidad_id"]: [x["saldo"], x["estado"]] for x in api(base, "GET", f"/v1/hechos/{hecho}/reparto").get("posiciones_vinculadas", [])}


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

    transporte, comb = str(seed.id_categoria("transporte")), str(seed.id_categoria("combustible"))
    litros = str(seed.id_magnitud("litros"))
    if not {transporte, comb} <= {x["id"] for x in api(a.api, "GET", "/v1/categorias")["categorias"]}:
        raise SystemExit("FALLO PRECONDICION: falta el catalogo sintetico del seed (bootstrap_dev_db.py --seed-categorias)")
    comprobar(not _sql(dsn, owner, "gapto_runtime", "SELECT 1 FROM gapto.hechos_financieros LIMIT 1"), "prep: la base dev ya tiene hechos")
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    ter = {k: str(uuid.uuid4()) for k in ("empresa", "tania", "repsol", "ayto")}
    for k, nom, nat in (("empresa", "Empresa SL", "EMPRESA"), ("tania", "Tania", "PERSONA"), ("repsol", "Repsol", "EMPRESA"), ("ayto", "Ayuntamiento", "ORGANISMO")):
        api(a.api, "POST", "/v1/terceros", {"id": ter[k], "nombre": nom, "naturaleza": nat})

    capturas: list[str] = []
    consola: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "terceros": ter}
    respuestas: list[dict] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"C03_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def inicio() -> None:
            for _ in range(5):  # la descarga del bundle en loopback se corta a veces (ver e2e_regcat)
                page.goto(a.web)
                try:
                    t("accion-registrar").wait_for(timeout=12000)
                    return
                except Exception:
                    continue
            raise SystemExit("FALLO: la app web no carga tras 5 intentos")

        def deshabilitado(i: str) -> bool:
            return t(i).get_attribute("aria-disabled") == "true"

        def gasto(importe: str, comercio: str | None, quien: str, otra: str | None, nombre: str) -> dict:
            inicio()
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").wait_for(timeout=15000)
            t("campo-importe").fill(importe)
            if comercio:
                t("campo-tercero").click()
                t(f"tercero-{comercio}").click()
            t("campo-categoria").click()
            t(f"cat-{transporte}").click()
            t(f"cat-{comb}").click()
            t(f"magnitud-{litros}").fill("41,5")
            t("presupuestable-true").click()
            t(f"cuenta-{nomina}").click()
            t("reembolsable").click()
            t("reembolso").wait_for(timeout=10000)
            if nombre == "R1":
                res["R1_c2_hecho_deshabilitado_al_abrir"] = deshabilitado("reembolso-hecho")
                comprobar(res["R1_c2_hecho_deshabilitado_al_abrir"], "R1: «Hecho» activo sin elegir nada")
                comprobar(t("reembolso-faltan").inner_text() == "Falta: quién te lo debe y cuánto te deben.", "R1: faltan de C2")
                shot("C2_vacio")
            t("reembolso-quien").click()
            t("selector-persona").wait_for(timeout=10000)
            if nombre == "R1":
                ofrecidos = sorted(x.get_attribute("data-testid") for x in page.locator('[data-testid^="persona-"]:visible').all())
                res["R1_selector"] = ofrecidos
                comprobar(f"persona-{ter['empresa']}" in ofrecidos and f"persona-{ter['tania']}" in ofrecidos, f"R1: selector {ofrecidos}")
                comprobar(f"persona-{ter['repsol']}" not in ofrecidos, "R1: el comercio aparece como quien te lo debe")
                comprobar(f"persona-{ter['ayto']}" not in ofrecidos, "R1: un ORGANISMO aparece como quien te lo debe")
                shot("C2_selector")
            t(f"persona-{ter[quien]}").click()
            if otra:
                t("reembolso-otra").click()
                t("reembolso-importe").fill("70")
                comprobar(deshabilitado("reembolso-hecho"), f"{nombre}: «Hecho» activo con 70 > total")
                t("reembolso-importe").fill(otra)
            else:
                t("reembolso-todo").click()
            comprobar(not deshabilitado("reembolso-hecho"), f"{nombre}: «Hecho» deshabilitado con todo elegido")
            if nombre == "R1":
                shot("C2_completo")
                oscuro("D1_C2_completo")
            t("reembolso-hecho").click()
            t("reembolso-resumen").wait_for(timeout=10000)
            if nombre == "R1":
                shot("C1_formulario_con_reembolso")
            with page.expect_response(lambda x: x.request.method == "POST" and x.url.endswith(RUTA), timeout=20000) as r:
                t("registrar").click()
            comprobar(r.value.status == 200, f"{nombre}: HTTP {r.value.status} {r.value.text()[:200]}")
            cuerpo = json.loads(r.value.request.post_data)
            comprobar("atribucion" not in cuerpo, f"{nombre}: el payload lleva atribucion")
            respuesta = r.value.json()
            respuestas.append({"caso": nombre, "payload_reembolso": cuerpo["reembolso"], "respuesta": respuesta})
            t("registro-exito").wait_for(timeout=15000)
            return respuesta

        # ------------------------------------------------------------ R1 empresa, parcial
        r1 = gasto("60", ter["repsol"], "empresa", "40", "R1")
        d1 = r1["posiciones"][0]
        comprobar([r1["tu_parte"], r1["movimiento"]["importe"], d1["tipo"], d1["contraparte_tercero_id"], d1["importe"], d1["saldo"], d1["estado"]]
                  == ["60.00", "-60.00", "DERECHO_COBRO", ter["empresa"], "40.00", "40.00", "ACTIVA"], f"R1: respuesta {r1}")
        comprobar(t("exito-resultado").inner_text().split("\n") == ["Cuenta en tu Resultado", "60,00 €"], f"R1: C3 {t('exito-resultado').inner_text()}")
        comprobar(t(f"exito-te-debe-{d1['entidad_id']}").inner_text().split("\n") == ["Te debe Empresa SL", "40,00 €"], "R1: C3 te debe")
        shot("C3_exito")
        oscuro("C3_exito")
        # ------------------------------------------------------------ R2 persona, total; R3 segundo derecho de la empresa
        r2 = gasto("30", None, "tania", None, "R2")
        comprobar([r2["posiciones"][0]["importe"], r2["posiciones"][0]["contraparte_tercero_id"]] == ["30.00", ter["tania"]], f"R2: {r2}")
        r3 = gasto("25", None, "empresa", None, "R3")
        d3 = r3["posiciones"][0]
        comprobar(d3["importe"] == "25.00" and d3["entidad_id"] != d1["entidad_id"], f"R3: {r3}")

        # ------------------------------------------------------------ C4 cobro del derecho elegido
        def detalle_r1() -> None:
            inicio()
            t("tab-DIA").click()
            t("actividad-periodo").click()
            t("periodo-ESTE_MES").click()
            t(f"fila-{r1['hecho_id']}").wait_for(timeout=20000)
            t(f"fila-{r1['hecho_id']}").click()
            t("detalle-contenido").wait_for(timeout=15000)

        detalle_r1()
        t(f"detalle-vinculada-{d1['entidad_id']}").wait_for(timeout=15000)
        comprobar(t(f"detalle-vinculada-{d1['entidad_id']}").inner_text() == "Pendiente con Empresa SL", "C4: boton del detalle")
        shot("C4_detalle_gasto")
        t(f"detalle-vinculada-{d1['entidad_id']}").click()
        t("posicion-acciones").wait_for(timeout=15000)
        comprobar("Empresa SL te debe 40,00 €" in t("posicion-acciones").inner_text(), "C4: no abre el derecho de R1")
        t("posicion-cobrar").click()
        t("accion-cobro").wait_for()
        comprobar(t("accion-origen").inner_text() == "Empresa SL · Pendiente de cobro · Combustible · te debe 40,00 €", f"C4: {t('accion-origen').inner_text()}")
        comprobar(t("accion-explicacion").inner_text() == "No es un ingreso: solo salda lo que te deben. Tu Resultado no cambia.", "C4: explicacion")
        t(f"accion-cuenta-{nomina}").wait_for(timeout=15000)
        comprobar(deshabilitado("accion-enviar"), "C4: «Registrar cobro» activo sin cuenta")
        shot("C4_registrar_cobro_sin_cuenta")
        t("accion-importe").fill("15")
        t(f"accion-cuenta-{nomina}").click()
        comprobar(not deshabilitado("accion-enviar"), "C4: «Registrar cobro» deshabilitado con cuenta")
        with page.expect_response(lambda x: x.request.method == "POST" and "/cobro" in x.url, timeout=20000) as rc:
            t("accion-enviar").click()
        comprobar(rc.value.url.endswith(f"/v1/posiciones/{d1['entidad_id']}/cobro"), f"C4: cobro a otra entidad {rc.value.url}")
        t("posicion-exito").wait_for()
        res["C4_parcial"] = t("posicion-exito-titulo").inner_text()
        comprobar(res["C4_parcial"] == "Cobro registrado · quedan 25,00 €", f"C4: {res['C4_parcial']}")
        shot("C4_cobro_parcial")
        t("posicion-exito-volver").click()
        t(f"posicion-{d1['entidad_id']}").click()
        t("posicion-cobrar").click()
        t(f"accion-cuenta-{nomina}").wait_for(timeout=15000)
        t(f"accion-cuenta-{nomina}").click()
        with page.expect_response(lambda x: x.request.method == "POST" and "/cobro" in x.url, timeout=20000) as rc2:
            t("accion-enviar").click()
        comprobar(rc2.value.json()["estado"] == "CERRADA", f"C4: {rc2.value.json()}")
        t("posicion-exito").wait_for()
        res["C4_total"] = t("posicion-exito-titulo").inner_text()
        comprobar(res["C4_total"] == "Saldado · no cuenta como ingreso", f"C4: {res['C4_total']}")
        shot("C4_saldado")
        oscuro("C4_saldado")

        # ------------------------------------------------------------ D devolucion bloqueada
        detalle_r1()
        t("detalle-registrar-devolucion").click()
        t("devolucion-no-disponible").wait_for(timeout=15000)
        res["D_motivo"] = t("devolucion-no-disponible").inner_text()
        comprobar("pendiente de cobro" in res["D_motivo"], f"D: {res['D_motivo']}")
        shot("D_devolucion_no_disponible")
        nav.close()

    # ---------------------------------------------------------------- oraculo final
    res["final_r1"] = vinculadas(a.api, r1["hecho_id"])
    res["final_r3"] = vinculadas(a.api, r3["hecho_id"])
    comprobar(res["final_r1"] == {d1["entidad_id"]: ["0.00", "CERRADA"]}, f"final R1: {res['final_r1']}")
    comprobar(res["final_r3"] == {d3["entidad_id"]: ["25.00", "ACTIVA"]}, f"final R3 (no debe cambiar): {res['final_r3']}")
    res["ingresos_bd"] = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t "
                              "ON t.id = h.tipo_hecho_id WHERE t.codigo = 'INGRESO'")[0][0]
    comprobar(res["ingresos_bd"] == 0, f"final: el cobro creo {res['ingresos_bd']} INGRESO")
    res["respuestas"] = respuestas
    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"C03_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
