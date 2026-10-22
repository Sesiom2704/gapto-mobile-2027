# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m1.py
# Ruta: scripts/dev/e2e_f05_06_m1.py
# Descripcion: E2E web de F05-06 M1 (lamina EDIT-HECHO v0.1; CONTRATO_M1 v0.1;
#   F05 §61.2): corregir y anular DESDE LA UI, con su oraculo fisico en cada
#   paso.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear).
#   Preparacion: cuentas «Cuenta nómina» y «Ahorro» como gapto_owner (como
#   e2e_j2j3); los registros por la API publica; el registro «de V3» se marca
#   con un mapeo de importacion sintetico (como f05_06_m2_helpers.marcar_v3).
#   Escenario:
#     P1  gasto 48,72 -> Día a día › detalle › «Más» › «Corregir» -> 47,82 con
#         «Editado», revision (movimiento y Resultado) y motivo; oraculo: hecho,
#         efecto y movimiento a 47,82 y auditoria con el motivo;
#     P2  duplicado 4,00 -> «Más» › «Anular por duplicado»: confirmar exige la
#         declaracion y el motivo; oraculo: hecho y movimiento ANULADO;
#     P3  transferencia 500 -> «Más» › «Corregir» -> 450; oraculo: dos patas a
#         450 y sin efectos;
#     P4  registro de V3 -> «Más»: las dos acciones atenuadas con su motivo y
#         sin envio (ningun POST).
#   Capturas 393x852 @3x (claro y oscuro) y manifest JSON con el estado.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M1)
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


def gasto(base: str, cuenta: str, importe: str, concepto: str, fecha: str) -> str:
    iid = str(uuid.uuid4())
    api(base, "POST", "/v1/intenciones/gasto-pagado", {
        "intencion_id": iid, "concepto": concepto, "importe": importe, "moneda": "EUR", "fecha_hecho": fecha,
        "cuenta_id": cuenta, "presupuestable": True, "atribucion": "SOLO_MIO",
        "financiacion": {"estado": "NO_DETERMINADA"}, "categoria": {"estado": "SIN_CATEGORIA"}})
    return iid


def marcar_v3(dsn: str, owner: str, hecho_id: str) -> None:
    fuente, origen = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
                                    "VALUES (%s, %s, 'DB', 'V3 sintetica')", (fuente, owner))
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, "
                                    "contenedor_origen, clave_origen, datos_origen) VALUES (%s, %s, 'public.gastos', %s, "
                                    "'{}'::jsonb)", (origen, fuente, hecho_id))
    _sql(dsn, owner, "gapto_owner", "INSERT INTO gapto.mapeos_importacion (registro_origen_id, tabla_destino, "
                                    "registro_destino_id, tipo_mapping, confianza) VALUES (%s, 'hechos_financieros', %s, "
                                    "'CREADO', 'ALTA')", (origen, hecho_id))


def estado(dsn: str, owner: str, hid: str) -> dict:
    q = lambda sql: _sql(dsn, owner, "gapto_runtime", sql, (hid,))  # noqa: E731
    return {
        "hecho": [[a, str(b)] for a, b in q("SELECT estado, importe_total FROM gapto.hechos_financieros WHERE id = %s")],
        "efectos": sorted(str(a) for (a,) in q("SELECT importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s")),
        "movimientos": sorted([a, str(b)] for a, b in q(
            "SELECT m.estado, m.importe FROM gapto.hecho_movimientos_tesoreria hm JOIN gapto.movimientos_tesoreria m "
            "ON m.id = hm.movimiento_tesoreria_id WHERE hm.hecho_id = %s")),
        "motivos": sorted({str(a) for (a,) in q("SELECT motivo FROM gapto.auditoria WHERE registro_id = %s AND motivo IS NOT NULL")}),
    }


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
    ayer = str(hoy - dt.timedelta(days=1))

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    ahorro = crear_cuenta(dsn, owner, "Ahorro", "AHORRO", "ACTIVO")
    compra = gasto(a.api, nomina, "48.72", "Compra semanal", ayer)
    cafe = gasto(a.api, nomina, "4.00", "Café", ayer)
    duplicado = gasto(a.api, nomina, "4.00", "Café", ayer)
    v3 = gasto(a.api, nomina, "65.00", "FONTANERO BAÑO", ayer)
    marcar_v3(dsn, owner, v3)
    transf = str(uuid.uuid4())
    api(a.api, "POST", "/v1/intenciones/transferencia", {
        "intencion_id": transf, "importe": "500.00", "moneda": "EUR", "fecha_hecho": ayer,
        "cuenta_origen_id": nomina, "cuenta_destino_id": ahorro, "nota": "Nómina → Ahorro"})
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "cuentas": {"nomina": nomina, "ahorro": ahorro},
                 "hechos": {"compra": compra, "cafe": cafe, "duplicado": duplicado, "v3": v3, "transferencia": transf},
                 "pasos": {}}
    capturas: list[str] = []
    consola: list[str] = []
    posts: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M1_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def post(ruta_final: str, testid: str, codigo: int = 200) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(ruta_final), timeout=20000) as resp:
                t(testid).click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == codigo, f"{ruta_final}: HTTP {resp.value.status} {cuerpo.get('codigo')}")
            return cuerpo

        def abrir_mas(hid: str, texto: str) -> None:
            # Tras corregir, la app reabre el detalle del registro corregido: se espera a que no quede ninguno.
            page.wait_for_timeout(800)
            if t("detalle-cerrar").count():
                t("detalle-cerrar").click()
            t(f"fila-{hid}").wait_for(timeout=20000)
            t(f"fila-{hid}").click()
            t("detalle-mas").wait_for(timeout=15000)
            comprobar(texto in t("hoja-detalle").inner_text(), f"detalle de {texto}")
            t("detalle-mas").click()
            t("hoja-mas-hecho").wait_for(timeout=15000)

        def pasos(t, page, shot, oscuro, post, abrir_mas, res, posts) -> None:
            # ------------------------------------------------------------ P1 corregir el importe de un pago
            abrir_mas(compra, "Compra semanal")
            shot("P1_A1_mas")
            oscuro("P1_A1_mas")
            t("mas-corregir").click()
            t("corregir-hecho-importe").wait_for(timeout=15000)
            comprobar("nunca fueron ciertos" in t("corregir-hecho-solo-errores").inner_text(), "P1: aviso INV-07")
            t("corregir-hecho-importe").fill("47,82")
            comprobar("antes 48,72" in t("corregir-hecho-editado-importe").inner_text(), "P1: «Editado» con el anterior")
            shot("P1_A2_formulario")
            t("corregir-hecho-revisar").click()
            comprobar("48,72 € → 47,82 €" in t("corregir-hecho-cambio-importe").inner_text(), "P1: revision del cambio")
            comprobar("−0,90" in t("corregir-hecho-impacto-resultado").inner_text(), "P1: Resultado del mes")
            comprobar(t("corregir-hecho-guardar").is_disabled(), "P1: sin motivo no se guarda")
            t("corregir-hecho-motivo-0").click()
            shot("P1_A3_revision")
            oscuro("P1_A3_revision")
            r = post(f"/v1/hechos/{compra}/corregir-pago", "corregir-hecho-guardar")
            t("corregir-hecho-listo").wait_for(timeout=15000)
            shot("P1_A4_corregido")
            e = estado(dsn, owner, compra)
            comprobar(e["hecho"] == [["ACTIVO", "47.8200"]] and e["efectos"] == ["47.8200"]
                      and e["movimientos"] == [["ACTIVO", "-47.8200"]], f"P1: oraculo {e}")
            comprobar("Importe mal tecleado" in e["motivos"], f"P1: auditoria {e['motivos']}")
            res["pasos"]["P1"] = {"respuesta": r, "estado": e}
            t("corregir-hecho-listo").click()
            t("detalle-cerrar").wait_for(timeout=15000)
            t("detalle-cerrar").click()

            # ------------------------------------------------------------ P2 anular por duplicado
            movs = [m["movimiento_id"] for m in api(a.api, "GET", f"/v1/hechos/{duplicado}/edicion")["movimientos"]]
            abrir_mas(duplicado, "Café")
            t("mas-anular").click()
            t("hoja-anular-duplicado").wait_for(timeout=15000)
            comprobar(t("anular-confirmar").is_disabled(), "P2: sin declaracion ni motivo")
            t("anular-motivo-0").click()
            comprobar(t("anular-confirmar").is_disabled(), "P2: falta la declaracion")
            shot("P2_B1_sin_declaracion")
            t("anular-declaracion").click()
            oscuro("P2_B1_anular")
            r = post(f"/v1/hechos/{duplicado}/anular-duplicado", "anular-confirmar")
            t("anulado-texto").wait_for(timeout=15000)
            shot("P2_B1_anulado")
            e = estado(dsn, owner, duplicado)
            comprobar(e["hecho"] == [["ANULADO", "4.0000"]], f"P2: oraculo {e}")
            estados_mov = [x for (x,) in _sql(dsn, owner, "gapto_runtime",
                                              "SELECT estado FROM gapto.movimientos_tesoreria WHERE id = ANY(%s::uuid[])", (movs,))]
            comprobar(estados_mov == ["ANULADO"], f"P2: movimiento {estados_mov}")
            e["movimiento_estado"] = estados_mov
            comprobar(estado(dsn, owner, cafe)["hecho"] == [["ACTIVO", "4.0000"]], "P2: el original sigue")
            res["pasos"]["P2"] = {"respuesta": r, "estado": e}
            t("anulado-cerrar").click()

            # ------------------------------------------------------------ P3 corregir una transferencia
            abrir_mas(transf, "Ahorro")
            t("mas-corregir").click()
            t("corregir-hecho-importe").wait_for(timeout=15000)
            t("corregir-hecho-importe").fill("450")
            t("corregir-hecho-revisar").click()
            comprobar(t("corregir-hecho-impacto-resultado").count() == 0, "P3: sin Resultado")
            t("corregir-hecho-motivo-0").click()
            shot("P3_B4_revision_transferencia")
            r = post(f"/v1/transferencias/{transf}/corregir", "corregir-hecho-guardar")
            t("corregir-hecho-listo").wait_for(timeout=15000)
            e = estado(dsn, owner, transf)
            comprobar(e["efectos"] == [] and e["movimientos"] == [["ACTIVO", "-450.0000"], ["ACTIVO", "450.0000"]], f"P3: oraculo {e}")
            res["pasos"]["P3"] = {"respuesta": r, "estado": e}
            t("corregir-hecho-listo").click()
            t("detalle-cerrar").wait_for(timeout=15000)
            t("detalle-cerrar").click()

            # ------------------------------------------------------------ P4 registro de V3
            n_posts = len(posts)
            abrir_mas(v3, "FONTANERO")
            for i in ("mas-corregir", "mas-anular"):
                comprobar(t(i).is_disabled(), f"P4: {i} atenuada")
                comprobar("V3" in t(f"{i}-motivo").inner_text(), f"P4: motivo de {i}")
            shot("P4_C3_v3")
            oscuro("P4_C3_v3")
            t("mas-corregir").click(force=True)
            page.wait_for_timeout(500)
            comprobar(len(posts) == n_posts, "P4: ningun POST")
            comprobar(estado(dsn, owner, v3)["hecho"] == [["ACTIVO", "65.0000"]], "P4: V3 intacto")
            res["pasos"]["P4"] = "OK"

        t("accion-registrar").wait_for(timeout=30000)
        t("tab-DIA").click()
        try:
            pasos(t, page, shot, oscuro, post, abrir_mas, res, posts)
        except BaseException:
            page.screenshot(path=str(salida / f"M1_{run}_FALLO.png"))
            (salida / f"M1_{run}_FALLO.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
            raise
        nav.close()


    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"M1_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
