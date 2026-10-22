# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m5_swipe.py
# Ruta: scripts/dev/e2e_f05_06_m5_swipe.py (derivado de scripts/dev/e2e_f05_06_m5.py)
# Descripcion: E2E web de F05-06 M5 (mandato, cuerpo §B3; laminas PREV v0.2 y
#   HOME-01 v0.4; F05 §59): confirmacion de previsiones DESDE LA UI, con su
#   oraculo fisico en cada paso.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear).
#   Preparacion: cuentas «Cuenta nómina» (CORRIENTE) y «Ahorro» (AHORRO) como
#   gapto_owner (sin writer de alta, como e2e_j2j3) y las previsiones con
#   scripts/dev/siembra_previsiones_m5.py (solo por servicio, DSN permitido).
#   Los gastos previos de «Ya lo registré» se registran por la API publica.
#   Escenario:
#     P0  Inicio: campana «3» junto al perfil, «Requiere atención» con dos
#         asuntos y «Ver todos ›»; claro y oscuro;
#     P1  fallo de la lectura del bloque: «No se pudieron cargar los
#         pendientes · Reintentar» y campana «!»; Reintentar lo recupera;
#     P2  campana -> «Pendientes»: «Por pagar» y «Por cobrar» separados;
#     P3  G2 luz 74 -> 81,37 con «Sí» desde el formulario; oraculo: GASTO
#         81,37, movimiento -81,37, vinculo 81,37, REALIZADA y Resultado del
#         mes -81,37 respecto de la base;
#     P4  parcial: seguro 40/120 + 50 con «No» -> ABIERTA, cubierto 90;
#     P5  ingreso desde la prevision: la nómina desde «Requiere atención» ->
#         «Registrar cobro» con «Sí»; INGRESO 2.100 y REALIZADA. El GESTO de
#         swipe no se reproduce en RN-web (ni raton ni toque CDP): la hoja del
#         swipe la cubren Jest (accion accesible) y el acta del iPhone (P7);
#         aqui se comprueba que la fila ofrece la accion «Cobrado»;
#     P6  rechazo por porcion: el registro elegido se consume por otra via
#         antes de «Enlazar» -> rechazo en llano, sin vinculo, lista releida;
#     P7  «Ya lo registré» con «Buscar en más fechas» (40 dias antes): toda
#         la porcion libre y REALIZADA;
#     P8  «No hubo este mes» del alquiler con motivo: OMITIDA sin hecho;
#     P9  transferencia desde la prevision: dos movimientos, sin efectos,
#         vinculo 500, REALIZADA y Resultado del mes identico.
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M5 §B3)
# Version: 0.2.0 (F05-06 M5 SWIPE): P5 cubre la nómina por la ACCION ACCESIBLE del
#   swipe (la misma funcion que el gesto; RN-web no expone accessibilityActions, se
#   invoca el manejador onAccessibilityAction de la fila por su fibra React):
#   P5a «Deshacer» -> 0 peticiones en 8 s y la fila vuelve; P5b aviso «Nómina
#   cobrada · Deshacer», el POST sale a los >=4,5 s, UNA sola vez; INGRESO 2.100,
#   REALIZADA con su vinculo y Resultado del mes +2.100,00 una sola vez.
# Version: 0.3.0 (F05-06 M5 SWIPE2; lamina SWIPE-01 v0.2): accion accesible «derecha»
#   (antes «swipe»); el aviso lleva el importe. P10 «Repetir hoy» del gasto de P6
#   en la Actividad: un solo POST a los >=4,5 s, GASTO NUEVO 23,10 con fecha de hoy y
#   Resultado -23,10 una vez. P11 «Desactivar» Iberdrola (izquierda) en Ajustes ›
#   Terceros: «Deshacer» -> 0 peticiones; despues, un solo POST y enabled=false.
# Version: 0.4.0 (F05-06 M5 SWIPE3; lamina SWIPE-01 v0.3): lados invertidos; la
#   accion accesible de la principal se llama «izquierda» y la de la alternativa
#   «derecha» (P5 y P10 «izquierda», P11 «derecha»).
# Version: 0.5.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): pasa de la evidencia a scripts/dev/
#   (antes e2e_f05_06_m5_swipe{,2,3}.py); importa los helpers de su propia carpeta.
#   Uso: como e2e_f05_06_m5.py (--web, --api, --dist, --salida; API con CORS, base
#   dev LOCAL recien recreada, GAPTO_DATABASE_URL, GAPTO_DEV_OWNER_USER_ID, GAPTO_DEV_TOKEN).
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
from siembra_previsiones_m5 import sembrar  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"
D = decimal.Decimal


def prevision(dsn: str, owner: str, pid: str) -> dict:
    q = lambda sql: _sql(dsn, owner, "gapto_runtime", sql, (pid,))  # noqa: E731
    estado = q("SELECT estado, row_version FROM gapto.previsiones WHERE id = %s")[0]
    vinculos = sorted([str(a), str(b)] for a, b in q(
        "SELECT hecho_id, importe_asignado FROM gapto.prevision_hechos WHERE prevision_id = %s"))
    return {"estado": estado[0], "row_version": estado[1], "vinculos": vinculos}


def hecho(dsn: str, owner: str, hid: str) -> dict:
    q = lambda sql: _sql(dsn, owner, "gapto_runtime", sql, (hid,))  # noqa: E731
    return {
        "hecho": [[a, str(b)] for a, b in q("SELECT t.codigo, h.importe_total FROM gapto.hechos_financieros h "
                                            "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id = %s")],
        "efectos": sorted([a, str(b)] for a, b in q("SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s")),
        "movimientos": sorted([a, str(b)] for a, b in q(
            "SELECT c.nombre, m.importe FROM gapto.hecho_movimientos_tesoreria hm JOIN gapto.movimientos_tesoreria m "
            "ON m.id = hm.movimiento_tesoreria_id JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE hm.hecho_id = %s")),
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

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    nomina = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    ahorro = crear_cuenta(dsn, owner, "Ahorro", "AHORRO", "ACTIVO")
    siembra = sembrar(dsn, uuid.UUID(owner), rol_runtime="gapto_runtime", hoy=hoy,
                      cuentas={"nomina": uuid.UUID(nomina), "ahorro": uuid.UUID(ahorro)})
    ids = {r["fixture"].split(".", 1)[1]: r["uuid"] for r in siembra if r["fixture"].startswith(("prevision.", "tercero."))}
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "cuentas": {"nomina": nomina, "ahorro": ahorro},
                 "siembra": siembra, "pasos": {}}
    capturas: list[str] = []
    consola: list[str] = []

    def resultado_mes() -> dict:
        return api(a.api, "GET", f"/v1/inicio/resultado-mes?fecha={hoy.isoformat()}")

    def gasto_api(importe: str, fecha: dt.date, tercero: str) -> str:
        iid = str(uuid.uuid4())
        api(a.api, "POST", "/v1/intenciones/gasto-pagado", {
            "intencion_id": iid, "importe": importe, "moneda": "EUR", "fecha_hecho": fecha.isoformat(), "cuenta_id": nomina,
            "presupuestable": True, "atribucion": "SOLO_MIO", "categoria": {"estado": "SIN_CATEGORIA"}, "tercero_id": tercero,
            "financiacion": {"estado": "PROPUESTA_ACEPTADA", "actor": "SELF", "criterio": "PARTICIPACION_CUENTA",
                             "porcentaje": "100", "importe": importe}})
        return iid

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M5_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def post(ruta_final: str, testid: str, estado: int = 200) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(ruta_final), timeout=20000) as resp:
                t(testid).click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == estado, f"{ruta_final}: HTTP {resp.value.status} {cuerpo.get('codigo')}")
            return cuerpo

        def a_inicio() -> None:
            page.goto(a.web)
            t("accion-registrar").wait_for(timeout=30000)

        t("accion-registrar").wait_for(timeout=30000)

        # ------------------------------------------------------------ P0 Inicio
        t("campana-contador").wait_for(timeout=15000)
        comprobar(t("campana-contador").inner_text() == "3", f"P0: campana {t('campana-contador').inner_text()}")
        bloque = t("bloque-atencion").inner_text()
        comprobar("Ver todos" in bloque and "Por pagar" not in bloque and "Por cobrar" not in bloque, "P0: bloque sin importes sumados")
        comprobar(t(f"atencion-{ids['nomina']}").count() == 1 and t(f"atencion-{ids['luz']}").count() == 1, "P0: dos primeras (vencidas)")
        comprobar(t(f"atencion-{ids['seguro']}").count() == 0, "P0: el parcial esta en la lista, no en Inicio")
        comprobar("+2.100,00 €" in t(f"atencion-{ids['nomina']}").inner_text(), "P0: cobro con «+»")
        comprobar("Presupuesto de gasto" not in page.locator("body").inner_text(), "P0: sin presupuesto (F08)")
        shot("P0_I01_inicio")
        oscuro("P0_I02_inicio")
        res["pasos"]["P0"] = {"campana": "3"}

        # ------------------------------------------------------------ P1 fallo del bloque
        page.route("**/v1/inicio/previsiones", lambda ruta: ruta.abort())
        page.reload()
        t("atencion-error").wait_for(timeout=15000)
        comprobar(t("campana-contador").inner_text() == "!", "P1: campana «!»")
        comprobar("No se pudieron cargar los pendientes" in t("bloque-atencion").inner_text(), "P1: texto de fallo")
        shot("P1_I05_fallo")
        page.unroute("**/v1/inicio/previsiones")
        t("atencion-reintentar").click()
        t(f"atencion-{ids['luz']}").wait_for(timeout=15000)
        comprobar(t("campana-contador").inner_text() == "3", "P1: recuperado")
        res["pasos"]["P1"] = "OK"

        # ------------------------------------------------------------ P2 Pendientes
        t("campana-pendientes").click()
        t("por-pagar").wait_for(timeout=15000)
        por_pagar, por_cobrar = t("por-pagar").inner_text(), t("por-cobrar").inner_text()
        comprobar(por_pagar == "~154,00 €" and por_cobrar == "+2.100,00 €", f"P2: {por_pagar} / {por_cobrar}")
        comprobar(t(f"pendiente-{ids['seguro']}").count() == 1, "P2: el parcial en la lista")
        shot("P2_I04_pendientes")
        oscuro("P2_I04_pendientes")
        res["pasos"]["P2"] = {"por_pagar": por_pagar, "por_cobrar": por_cobrar}

        # ------------------------------------------------------------ P3 G2 luz
        antes = resultado_mes()
        t(f"pendiente-{ids['luz']}").click()
        t("prevision-accion-registrar").wait_for(timeout=15000)
        shot("P3_A2_detalle_luz")
        t("prevision-accion-registrar").click()
        t(f"prevision-cuenta-{nomina}").wait_for(timeout=15000)
        comprobar("De la previsión" in t(f"prevision-cuenta-{nomina}").inner_text(), "P3: cuenta de la previsión")
        comprobar(t("prevision-revisar").is_disabled() or "¿queda cubierta?" in t("prevision-falta").inner_text(), "P3: sin respuesta")
        t("prevision-importe").fill("81,37")
        t("cubierta-si").click()
        shot("P3_A3_formulario")
        t("prevision-revisar").click()
        t("revision-se-registra").wait_for()
        shot("P3_A4_revision")
        oscuro("P3_C2_revision")
        cuerpo = post("/v1/intenciones/gasto-pagado", "prevision-registrar")
        t("prevision-registro-listo").click()
        h3 = hecho(dsn, owner, cuerpo["hecho_id"])
        p3 = prevision(dsn, owner, ids["luz"])
        despues = resultado_mes()
        comprobar(h3["hecho"] == [["GASTO", "81.3700"]] and h3["efectos"] == [["GASTO", "81.3700"]], f"P3: {h3}")
        comprobar(h3["movimientos"] == [["Cuenta nómina", "-81.3700"]], f"P3: {h3['movimientos']}")
        comprobar(p3["estado"] == "REALIZADA" and p3["vinculos"] == [[cuerpo["hecho_id"], "81.3700"]], f"P3: {p3}")
        dif = {k: str(D(despues[k]) - D(antes[k])) for k in ("ingresos_propios", "gastos_propios", "resultado")}
        comprobar(dif == {"ingresos_propios": "0.00", "gastos_propios": "81.37", "resultado": "-81.37"}, f"P3: resultado {dif}")
        res["pasos"]["P3"] = {"hecho": h3, "prevision": p3, "resultado_dif": dif}

        # ------------------------------------------------------------ P4 parcial
        a_inicio()
        t("campana-pendientes").click()
        t(f"pendiente-{ids['seguro']}").click()
        t("detalle-cubrir-resto").wait_for(timeout=15000)
        comprobar(t("prevision-accion-omitir").is_disabled(), "P4: omitir no disponible")
        comprobar("ya tiene un pago enlazado" in t("prevision-accion-omitir-motivo").inner_text(), "P4: motivo")
        shot("P4_B5_parcial")
        t("prevision-accion-registrar").click()
        t(f"prevision-cuenta-{nomina}").wait_for(timeout=15000)
        t("prevision-importe").fill("50")
        t("cubierta-no").click()
        t("prevision-revisar").click()
        post("/v1/intenciones/gasto-pagado", "prevision-registrar")
        t("prevision-registro-listo").click()
        det = api(a.api, "GET", f"/v1/previsiones/{ids['seguro']}")
        comprobar(det["estado"] == "ABIERTA" and det["cubierto"] == "90.00" and det["queda"] == "30.00", f"P4: {det['cubierto']} {det['queda']}")
        res["pasos"]["P4"] = {"estado": det["estado"], "cubierto": det["cubierto"], "queda": det["queda"]}

        # ------------------------------------------------------------ P5 nómina por la accion accesible del swipe
        posts: list[tuple[float, str]] = []
        page.on("request", lambda r: posts.append((dt.datetime.now().timestamp(), r.url)) if r.method == "POST" else None)

        def accion_accesible(testid: str, nombre: str) -> None:
            hecho = page.evaluate("""([tid, nombre]) => {
              // Arbol React VIGENTE desde la raiz (root.current): la fibra cacheada en el nodo DOM puede ser la obsoleta.
              const cont = document.getElementById('root');
              const k = Object.keys(cont).find((x) => x.startsWith('__reactContainer$'));
              const pila = [cont[k].stateNode.current];
              while (pila.length) {
                const f = pila.pop();
                const pr = f.memoizedProps;
                if (pr && pr.testID === tid && pr.onAccessibilityAction) {
                  pr.onAccessibilityAction({ nativeEvent: { actionName: nombre } });
                  return true;
                }
                if (f.sibling) pila.push(f.sibling);
                if (f.child) pila.push(f.child);
              }
              return false;
            }""", [testid, nombre])
            comprobar(hecho, f"accion accesible no encontrada en {testid}")

        a_inicio()
        fila_n = f"atencion-{ids['nomina']}"
        t(fila_n).wait_for(timeout=15000)
        page.wait_for_timeout(1500)  # capacidades de hoy leidas con la lista
        antes5 = resultado_mes()
        ingresos_antes = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t "
                              "ON t.id = h.tipo_hecho_id WHERE t.codigo = 'INGRESO'", ())[0][0]
        # P5a «Deshacer»: nada sale
        n0 = len(posts)
        caps = api(a.api, "GET", f"/v1/cuentas/elegibles?operacion=INGRESO&fecha={hoy.isoformat()}")
        res["diagnostico_elegibles_ingreso"] = caps
        accion_accesible(fila_n, "izquierda")
        try:
            t(f"aviso-rapida-{ids['nomina']}-texto").wait_for(timeout=5000)
        except Exception:
            shot("P5a_DIAGNOSTICO")
            (salida / "diagnostico_p5a.json").write_text(json.dumps({"hoja_swipe": t("hoja-swipe").count(), "elegibles": caps,
                                                                     "nomina": nomina}, ensure_ascii=False, indent=1), encoding="utf-8")
            raise
        comprobar(t(f"aviso-rapida-{ids['nomina']}-texto").inner_text() == "Nómina cobrada · 2.100,00 €", "P5a: texto del aviso")
        comprobar(t(fila_n).count() == 0, "P5a: la fila sale")
        shot("P5a_aviso_deshacer")
        oscuro("P5a_aviso_deshacer")
        t(f"aviso-rapida-{ids['nomina']}-deshacer").click()
        t(fila_n).wait_for(timeout=5000)
        page.wait_for_timeout(8000)
        comprobar(len(posts) == n0, f"P5a: peticiones tras Deshacer {posts[n0:]}")
        comprobar(t(fila_n).count() == 1, "P5a: la fila vuelve")
        # P5b accion rapida: el POST sale a los 5 s, una sola vez
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/intenciones/ingreso-cobrado"), timeout=15000) as resp:
            t0 = dt.datetime.now().timestamp()
            accion_accesible(fila_n, "izquierda")
            t(f"aviso-rapida-{ids['nomina']}").wait_for(timeout=5000)
        espera = round(dt.datetime.now().timestamp() - t0, 2)
        cuerpo = resp.value.json()
        comprobar(resp.value.status == 200, f"P5b: HTTP {resp.value.status} {cuerpo.get('codigo')}")
        comprobar(espera >= 4.5, f"P5b: el POST salio a los {espera} s")
        t(f"aviso-rapida-{ids['nomina']}").wait_for(state="detached", timeout=15000)
        page.wait_for_timeout(1500)
        envios = [u for _, u in posts if u.endswith("/v1/intenciones/ingreso-cobrado")]
        comprobar(len(envios) == 1, f"P5b: {len(envios)} envios")
        comprobar(t(fila_n).count() == 0, "P5b: la nómina ya no esta pendiente")
        shot("P5b_tras_accion_rapida")
        h5 = hecho(dsn, owner, cuerpo["hecho_id"])
        p5 = prevision(dsn, owner, ids["nomina"])
        despues5 = resultado_mes()
        ingresos_despues = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t "
                                "ON t.id = h.tipo_hecho_id WHERE t.codigo = 'INGRESO'", ())[0][0]
        comprobar(h5["hecho"] == [["INGRESO", "2100.0000"]] and h5["movimientos"] == [["Cuenta nómina", "2100.0000"]], f"P5: {h5}")
        comprobar(p5["estado"] == "REALIZADA" and p5["vinculos"] == [[cuerpo["hecho_id"], "2100.0000"]], f"P5: {p5}")
        comprobar(ingresos_despues - ingresos_antes == 1, f"P5: ingresos {ingresos_antes} -> {ingresos_despues}")
        dif5 = {k: str(D(despues5[k]) - D(antes5[k])) for k in ("ingresos_propios", "gastos_propios", "resultado")}
        comprobar(dif5 == {"ingresos_propios": "2100.00", "gastos_propios": "0.00", "resultado": "2100.00"}, f"P5: resultado {dif5}")
        res["pasos"]["P5"] = {"deshacer_peticiones": 0, "espera_s": espera, "envios": len(envios), "hecho": h5, "prevision": p5,
                              "ingresos": [ingresos_antes, ingresos_despues], "resultado_dif": dif5}

        # ------------------------------------------------------------ P6 rechazo por porcion
        h6 = gasto_api("23.10", hoy - dt.timedelta(days=1), ids["emasesa"])
        a_inicio()
        t(f"proximo-{ids['agua']}").click()
        t("prevision-accion-ya").wait_for(timeout=15000)
        comprobar(t("detalle-esperado").inner_text() == "Desconocido", "P6: Desconocido")
        shot("P6_B4_desconocido")
        t("prevision-accion-ya").click()
        t(f"candidato-{h6}").wait_for(timeout=15000)
        comprobar(t("ya-enlazar").is_disabled(), "P6: sin preseleccion")
        t(f"candidato-{h6}").click()
        comprobar("Se vinculará 23,10 € de este registro" in t("ya-se-vinculara").inner_text(), "P6: se vinculara")
        shot("P6_B2_ya_lo_registre")
        # Otro enlace consume la porcion antes de «Enlazar» (por la API publica).
        v_lav = api(a.api, "GET", f"/v1/previsiones/{ids['lavadora']}")
        api(a.api, "POST", f"/v1/previsiones/{ids['lavadora']}/vincular", {
            "intencion_id": str(uuid.uuid4()), "row_version": v_lav["row_version"], "hecho_id": h6,
            "importe_a_vincular": "23.10", "marcar_realizada": False})
        t("ya-cubierta-si").click()
        rechazo = post(f"/v1/previsiones/{ids['agua']}/vincular", "ya-enlazar", estado=409)
        t("ya-error").wait_for()
        comprobar(rechazo["codigo"] == "PORCION_DE_REALIDAD_EXCEDIDA", f"P6: {rechazo['codigo']}")
        page.wait_for_timeout(800)
        comprobar(t(f"candidato-{h6}").count() == 0, "P6: lista releida sin el registro consumido")
        shot("P6_rechazo_porcion")
        p6 = prevision(dsn, owner, ids["agua"])
        comprobar(p6["vinculos"] == [] and p6["estado"] == "ABIERTA", f"P6: {p6}")
        res["pasos"]["P6"] = {"rechazo": rechazo["codigo"], "prevision": p6}

        # ------------------------------------------------------------ P7 «Buscar en más fechas»
        h7 = gasto_api("23.10", hoy - dt.timedelta(days=40), ids["emasesa"])
        t("ya-atras").click()
        t("prevision-accion-ya").wait_for(timeout=15000)
        t("prevision-accion-ya").click()
        page.wait_for_timeout(800)
        comprobar(t(f"candidato-{h7}").count() == 0, "P7: fuera de ±15")
        t("ya-mas-fechas").click()
        t(f"candidato-{h7}").wait_for(timeout=15000)
        t(f"candidato-{h7}").click()
        t("ya-cubierta-si").click()
        shot("P7_mas_fechas")
        post(f"/v1/previsiones/{ids['agua']}/vincular", "ya-enlazar")
        p7 = prevision(dsn, owner, ids["agua"])
        comprobar(p7["estado"] == "REALIZADA" and p7["vinculos"] == [[h7, "23.1000"]], f"P7: {p7}")
        res["pasos"]["P7"] = {"prevision": p7}

        # ------------------------------------------------------------ P8 omitir
        a_inicio()
        t(f"proximo-{ids['alquiler']}").click()
        t("prevision-accion-omitir").wait_for(timeout=15000)
        t("prevision-accion-omitir").click()
        t("omitir-motivo").fill("Pagado por adelantado")
        shot("P8_B3_omitir")
        hechos_antes = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros")[0][0]
        post(f"/v1/previsiones/{ids['alquiler']}/omitir", "omitir-confirmar")
        p8 = prevision(dsn, owner, ids["alquiler"])
        hechos_despues = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros")[0][0]
        comprobar(p8["estado"] == "OMITIDA" and hechos_despues == hechos_antes, f"P8: {p8}")
        res["pasos"]["P8"] = {"prevision": p8, "hechos": [hechos_antes, hechos_despues]}

        # ------------------------------------------------------------ P9 transferencia desde la prevision
        antes = resultado_mes()
        a_inicio()
        t(f"proximo-{ids['traspaso']}").click()
        t("prevision-accion-registrar").wait_for(timeout=15000)
        t("prevision-accion-registrar").click()
        t(f"prevision-destino-{ahorro}").wait_for(timeout=15000)
        t("cubierta-si").click()
        shot("P9_D1_transferencia")
        t("prevision-revisar").click()
        t("revision-sin-doble").wait_for()
        shot("P9_D2_revision")
        oscuro("P9_D2_revision")
        cuerpo = post("/v1/intenciones/transferencia", "prevision-registrar")
        h9 = hecho(dsn, owner, cuerpo["hecho_id"])
        p9 = prevision(dsn, owner, ids["traspaso"])
        comprobar(h9["efectos"] == [] and h9["movimientos"] == [["Ahorro", "500.0000"], ["Cuenta nómina", "-500.0000"]], f"P9: {h9}")
        comprobar(p9["estado"] == "REALIZADA" and p9["vinculos"] == [[cuerpo["hecho_id"], "500.0000"]], f"P9: {p9}")
        comprobar(resultado_mes() == antes, "P9: el Resultado del mes no cambia")
        res["pasos"]["P9"] = {"hecho": h9, "prevision": p9}

        # ------------------------------------------------------------ P10 «Repetir hoy» en la Actividad (accion accesible derecha)
        gastos_antes = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t "
                            "ON t.id = h.tipo_hecho_id WHERE t.codigo = 'GASTO'", ())[0][0]
        antes10 = resultado_mes()
        a_inicio()
        t("tab-DIA").click()
        t(f"fila-{h6}").wait_for(timeout=15000)
        n10 = len(posts)
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/intenciones/gasto-pagado"), timeout=20000) as resp10:
            t0 = dt.datetime.now().timestamp()
            accion_accesible(f"fila-{h6}", "izquierda")
            t(f"aviso-rapida-repetir-{h6}-texto").wait_for(timeout=8000)
            texto10 = t(f"aviso-rapida-repetir-{h6}-texto").inner_text()
            shot("P10_repetir_hoy_aviso")
        espera10 = round(dt.datetime.now().timestamp() - t0, 2)
        cuerpo10 = resp10.value.json()
        comprobar(resp10.value.status == 200, f"P10: HTTP {resp10.value.status} {cuerpo10.get('codigo')}")
        comprobar(espera10 >= 4.5, f"P10: el POST salio a los {espera10} s")
        comprobar(texto10.startswith("Repetido hoy:") and "23,10" in texto10, f"P10: aviso {texto10}")
        page.wait_for_timeout(1500)
        envios10 = [u for _, u in posts[n10:] if u.endswith("/v1/intenciones/gasto-pagado")]
        comprobar(len(envios10) == 1, f"P10: {len(envios10)} envios")
        h10 = hecho(dsn, owner, cuerpo10["hecho_id"])
        fecha10 = str(_sql(dsn, owner, "gapto_runtime", "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s", (cuerpo10["hecho_id"],))[0][0])
        gastos_despues = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t "
                              "ON t.id = h.tipo_hecho_id WHERE t.codigo = 'GASTO'", ())[0][0]
        despues10 = resultado_mes()
        dif10 = {k: str(D(despues10[k]) - D(antes10[k])) for k in ("ingresos_propios", "gastos_propios", "resultado")}
        comprobar(cuerpo10["hecho_id"] != h6 and h10["hecho"] == [["GASTO", "23.1000"]] and fecha10 == str(hoy), f"P10: {h10} {fecha10}")
        comprobar(gastos_despues - gastos_antes == 1, f"P10: gastos {gastos_antes} -> {gastos_despues}")
        comprobar(dif10 == {"ingresos_propios": "0.00", "gastos_propios": "23.10", "resultado": "-23.10"}, f"P10: resultado {dif10}")
        shot("P10_repetir_hoy_hecho")
        res["pasos"]["P10"] = {"espera_s": espera10, "envios": len(envios10), "hecho": h10, "fecha": fecha10, "gastos": [gastos_antes, gastos_despues], "resultado_dif": dif10}

        # ------------------------------------------------------------ P11 «Desactivar» un tercero (accion accesible izquierda)
        t("tab-MAS").click()
        if t("mas-ajustes").count():
            t("mas-ajustes").click()
        t("ajustes-terceros").click()
        fila11 = f"ajter-fila-{ids['iberdrola']}"
        t(fila11).wait_for(timeout=15000)
        n11 = len(posts)
        accion_accesible(fila11, "derecha")
        t(f"aviso-rapida-{ids['iberdrola']}-texto").wait_for(timeout=5000)
        comprobar(t(f"aviso-rapida-{ids['iberdrola']}-texto").inner_text() == "Iberdrola desactivado", "P11: texto del aviso")
        shot("P11_desactivar_tercero")
        oscuro("P11_desactivar_tercero")
        t(f"aviso-rapida-{ids['iberdrola']}-deshacer").click()
        page.wait_for_timeout(7000)
        comprobar(len(posts) == n11, f"P11: peticiones tras Deshacer {posts[n11:]}")
        accion_accesible(fila11, "derecha")
        t(f"aviso-rapida-{ids['iberdrola']}").wait_for(state="detached", timeout=15000)
        page.wait_for_timeout(1500)
        envios11 = [u for _, u in posts[n11:] if u.endswith("/desactivar")]
        ter = {x["id"]: x for x in api(a.api, "GET", "/v1/terceros")["terceros"]}
        comprobar(len(envios11) == 1 and ter[ids["iberdrola"]]["enabled"] is False, f"P11: {envios11} {ter[ids['iberdrola']]}")
        res["pasos"]["P11"] = {"deshacer_peticiones": 0, "envios": len(envios11), "enabled": ter[ids["iberdrola"]]["enabled"]}

        nav.close()

    res["capturas"] = capturas
    # Excluidos: el aborto provocado de P1 y el 409 ESPERADO de P6 (un solo rechazo por porcion).
    esperados_409 = [c for c in consola if "status of 409" in c]
    comprobar(len(esperados_409) <= 1, f"409 inesperados: {esperados_409}")
    res["consola_409_esperado_P6"] = esperados_409
    res["consola_errores"] = [c for c in consola if "net::ERR_FAILED" not in c and "Failed to fetch" not in c
                              and "status of 409" not in c]
    (salida / f"M5_{run}_manifest.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    comprobar(not res["consola_errores"], f"errores de consola: {res['consola_errores'][:3]}")
    print(f"E2E M5 PASS ({len(capturas)} capturas, {ETIQUETA})")


if __name__ == "__main__":
    main()
