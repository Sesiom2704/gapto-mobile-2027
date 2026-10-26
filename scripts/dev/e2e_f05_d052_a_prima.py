# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_d052_a_prima.py
# Ruta: scripts/dev/e2e_f05_d052_a_prima.py
# Descripcion: E2E web de A′ (F05-D052 paso 3; D-F0507L-07; lamina F05-07
#   v0.3 A′1/A′2): la magnitud justo despues de la categoria.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (en web no hay barra
#   «Hecho» sobre el teclado: «Hecho» es la tecla Intro, que dispara el mismo
#   manejador que la barra de iOS; la barra y VoiceOver se cubren en Jest y en
#   la pasada G5 del iPhone).
#
#   Exige la base dev RECIEN RECREADA con el catalogo sintetico del seed
#   (bootstrap_dev_db.py --recrear y --seed-categorias: Transporte › Combustible
#   con Litros obligatoria y Kilometros opcional; Transporte publico con
#   Kilometros opcional). Escenario:
#     A1  Combustible: al volver del selector el foco esta en Litros; Intro con
#         41,5 cierra el campo y la pantalla sube hasta «¿Cuenta para el
#         presupuesto?», que sigue sin marcar, igual que la cuenta
#         (D-F0507L-02). Se registra: el POST lleva solo Litros = 41.5.
#     A2  Kilometros pasa a obligatoria en Combustible (comando de Ajustes por la
#         API): el foco va a Litros (orden 0), Intro pasa a Kilometros e Intro
#         cierra; cerrar el teclado tocando fuera conserva el valor; cambiar a
#         Transporte publico conserva Kilometros (comun) y, tras confirmar,
#         Litros desaparece y no se envia (POST con solo Kilometros); con solo
#         una opcional no se abre el teclado.
#   Oraculo: payload capturado del POST y respuesta 200; hechos y magnitudes
#   leidos en la BD como gapto_runtime (solo lectura).
#   Capturas 393x852 @3x (claro y oscuro) y manifest JSON.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-D052 paso 3 · A′)
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
RUTA_REGISTRO = "/v1/intenciones/gasto-pagado"
ACTIVO_JS = "() => document.activeElement && document.activeElement.getAttribute('data-testid')"


def magnitudes_del_hecho(dsn: str, owner: str, hecho: str) -> dict:
    """{magnitud_id: valor} del hecho, leido como gapto_runtime (solo lectura)."""
    return {str(m): format(v.normalize(), "f") for m, v in _sql(dsn, owner, "gapto_runtime",
            "SELECT magnitud_id, valor FROM gapto.hecho_magnitudes WHERE hecho_id = %s", (hecho,))}


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

    transporte, comb, publico = (str(seed.id_categoria(x)) for x in ("transporte", "combustible", "transporte_publico"))
    litros, km = str(seed.id_magnitud("litros")), str(seed.id_magnitud("kilometros"))
    arbol = {x["id"]: x for x in api(a.api, "GET", "/v1/categorias")["categorias"]}
    if not {transporte, comb, publico} <= set(arbol):
        raise SystemExit("FALLO PRECONDICION: falta el catalogo sintetico del seed (bootstrap_dev_db.py --seed-categorias)")
    asoc = {m["magnitud_id"]: m for m in arbol[comb]["magnitudes"]}
    comprobar(asoc[litros]["obligatoria"] and not asoc[km]["obligatoria"], f"prep: Combustible del seed {asoc}")
    comprobar(not _sql(dsn, owner, "gapto_runtime", "SELECT 1 FROM gapto.hechos_financieros LIMIT 1"), "prep: la base dev ya tiene hechos")

    # Segunda cuenta: con dos y sin preferencias no hay propuesta de cuenta (la cuenta unica se propone, F05-02).
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta BBVA", "CORRIENTE", "ACTIVO")
    capturas: list[str] = []
    consola: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "categorias": {"combustible": comb, "transporte_publico": publico},
                 "magnitudes": {"litros": litros, "kilometros": km}}
    enviados: list[dict] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: enviados.append(json.loads(r.post_data))
                if r.method == "POST" and r.url.endswith(RUTA_REGISTRO) and r.post_data else None)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731
        activo = lambda: page.evaluate(ACTIVO_JS)  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"AP_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def abrir(importe: str) -> None:
            for _ in range(5):  # la descarga del bundle en loopback se corta a veces (ver e2e_regcat)
                page.goto(a.web)
                try:
                    t("accion-registrar").wait_for(timeout=12000)
                    break
                except Exception:
                    continue
            else:
                raise SystemExit("FALLO: la app web no carga tras 5 intentos")
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("financiacion").count()  # sin espera: puede no haber propuesta
            t("campo-importe").wait_for(timeout=15000)
            t("campo-importe").fill(importe)

        def elegir(hoja: str) -> None:
            t("campo-categoria").click()
            t(f"cat-{transporte}").click()
            t(f"cat-{hoja}").click()
            t("selector-categorias").wait_for(state="detached", timeout=10000)
            page.wait_for_timeout(300)

        def presupuesto_visible() -> bool:
            caja = t("bloque-presupuestable").bounding_box()
            return caja is not None and 0 <= caja["y"] and caja["y"] + 40 <= 852

        def marcado(el) -> str:
            """Como e2e_preferencias: aria-checked si existe; en un segmento (radio), su superficie propia."""
            if el.get_attribute("aria-checked") is not None:
                return el.get_attribute("aria-checked")
            if el.get_attribute("role") == "radio":
                return str(el.evaluate("e => getComputedStyle(e).backgroundColor !== 'rgba(0, 0, 0, 0)'")).lower()
            return str(el.inner_text().startswith("✓")).lower()

        def sin_marcar() -> dict:
            return {"presupuestable": [marcado(t(f"presupuestable-{v}")) for v in ("true", "false")],
                    "cuentas": [marcado(x) for x in page.locator('[data-testid^="cuenta-"]:visible').all()],
                    "origen_cuenta": t("origen-cuenta").count()}

        def registrar() -> dict:
            with page.expect_response(lambda x: x.request.method == "POST" and x.url.endswith(RUTA_REGISTRO), timeout=20000) as r:
                t("registrar").click()
            comprobar(r.value.status == 200, f"registro: HTTP {r.value.status}")
            t("registro-exito").wait_for(timeout=15000)
            return r.value.json()

        # ------------------------------------------------------------ A1 Combustible: Litros y presupuesto
        abrir("60")
        elegir(comb)
        res["A1_foco_tras_categoria"] = activo()
        comprobar(res["A1_foco_tras_categoria"] == f"magnitud-{litros}", f"A1: foco tras la categoria {res['A1_foco_tras_categoria']}")
        shot("A1_litros_con_foco")
        page.keyboard.type("41,5")
        page.keyboard.press("Enter")
        page.wait_for_timeout(700)
        res["A1_foco_tras_hecho"] = activo()
        comprobar(res["A1_foco_tras_hecho"] != f"magnitud-{litros}", "A1: Litros sigue con el foco tras «Hecho»")
        comprobar(presupuesto_visible(), "A1: «¿Cuenta para el presupuesto?» no queda a la vista")
        res["A1_sin_marcar"] = sin_marcar()
        comprobar(res["A1_sin_marcar"]["presupuestable"] == ["false", "false"], f"A1: presupuesto marcado {res['A1_sin_marcar']}")
        comprobar(len(res["A1_sin_marcar"]["cuentas"]) == 2 and all(x != "true" for x in res["A1_sin_marcar"]["cuentas"])
                  and res["A1_sin_marcar"]["origen_cuenta"] == 0, f"A1: cuenta marcada {res['A1_sin_marcar']}")
        comprobar(t(f"magnitud-{litros}").input_value() == "41,5", "A1: Litros perdio el valor")
        shot("A2_tras_hecho")
        oscuro("A2_tras_hecho")
        t("presupuestable-true").click()
        t(f"cuenta-{tarjeta}").click()
        r1 = registrar()
        p1 = enviados[-1]
        res["A1_payload_categoria"] = p1["categoria"]
        comprobar(p1["categoria"] == {"estado": "CATEGORIA", "categoria_id": comb, "magnitudes": [{"magnitud_id": litros, "valor": "41.5"}]},
                  f"A1: payload {p1['categoria']}")
        res["A1_bd"] = magnitudes_del_hecho(dsn, owner, r1["hecho_id"])
        comprobar(res["A1_bd"] == {litros: "41.5"}, f"A1: BD {res['A1_bd']}")

        # ------------------------------------------------------------ A2 varias magnitudes y cambio de categoria
        api(a.api, "POST", f"/v1/categorias/{comb}/magnitudes/{asoc[km]['asociacion_id']}/obligatoria",
            {"magnitud_id": km, "obligatoria_actual": False, "obligatoria": True})
        abrir("45")
        elegir(comb)
        res["A2_foco_1"] = activo()
        comprobar(res["A2_foco_1"] == f"magnitud-{litros}", f"A2: foco inicial {res['A2_foco_1']}")
        page.keyboard.type("30")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        res["A2_foco_2"] = activo()
        comprobar(res["A2_foco_2"] == f"magnitud-{km}", f"A2: «Hecho» no pasa a Kilometros ({res['A2_foco_2']})")
        page.keyboard.type("420")
        shot("A3_dos_magnitudes")
        # Cerrar el teclado tocando fuera (la cabecera de la tarea): el valor se conserva.
        page.mouse.click(196, 40)
        page.wait_for_timeout(300)
        comprobar(activo() != f"magnitud-{km}", "A2: tocar fuera no quita el foco")
        comprobar(t(f"magnitud-{km}").input_value() == "420", "A2: Kilometros perdio el valor al tocar fuera")
        t(f"magnitud-{km}").click()
        page.keyboard.press("Enter")
        page.wait_for_timeout(700)
        comprobar(activo() not in (f"magnitud-{km}", f"magnitud-{litros}"), "A2: «Hecho» en la ultima no cierra")
        comprobar(presupuesto_visible(), "A2: «¿Cuenta para el presupuesto?» no queda a la vista")
        # Cambio a Transporte publico: Kilometros (comun) se conserva; Litros se descarta con confirmacion.
        t("campo-categoria").click()
        t(f"cat-{transporte}").click()
        t(f"cat-{publico}").click()
        t("confirmar-descarte").wait_for(timeout=10000)
        comprobar(t(f"descarte-{litros}").count() == 1 and t(f"descarte-{km}").count() == 0, "A2: la confirmacion no lista solo Litros")
        shot("A4_confirmar_descarte")
        t("descarte-confirmar").click()
        page.wait_for_timeout(500)
        comprobar(t(f"magnitud-{litros}").count() == 0, "A2: Litros sigue visible tras cambiar de categoria")
        comprobar(t(f"magnitud-{km}").input_value() == "420", "A2: Kilometros no se conserva")
        res["A2_foco_tras_opcional"] = activo()
        comprobar(res["A2_foco_tras_opcional"] != f"magnitud-{km}", "A2: una opcional abre el teclado")
        shot("A5_transporte_publico")
        oscuro("A5_transporte_publico")
        t("presupuestable-false").click()
        t(f"cuenta-{tarjeta}").click()
        r2 = registrar()
        p2 = enviados[-1]
        res["A2_payload_categoria"] = p2["categoria"]
        comprobar(p2["categoria"] == {"estado": "CATEGORIA", "categoria_id": publico, "magnitudes": [{"magnitud_id": km, "valor": "420"}]},
                  f"A2: payload {p2['categoria']}")
        res["A2_bd"] = magnitudes_del_hecho(dsn, owner, r2["hecho_id"])
        comprobar(res["A2_bd"] == {km: "420"}, f"A2: BD {res['A2_bd']}")
        nav.close()

    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"AP_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
