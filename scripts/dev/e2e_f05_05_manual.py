# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_05_manual.py
# Ruta: scripts/dev/e2e_f05_05_manual.py
# Descripcion: K4-A2 de F05-05 (ENCADENADO_NOCTURNO_3 v1.0): automatizacion en
#   navegador de las PRIORITARIAS P1-P16 de PRUEBA_MANUAL_K4_v1.0.md. Una
#   funcion por prueba, aislada: un fallo se anota como KO con su mensaje y
#   captura, y se sigue con la siguiente (no se repara nada aqui).
#   Resultado por prueba: OK_AUTOMATIZADA | KO | NO_AUTOMATIZABLE (con motivo).
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (VoiceOver, Dynamic Type,
#   gestos nativos y rendimiento percibido quedan para la pasada en iPhone).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias) y API y web levantadas como en e2e_f05_05.py. Datos con
#   nombres legibles por los writers publicos; las cuentas, como gapto_owner
#   (igual que e2e_j2j3). Fechas relativas al dia de hoy (Madrid).
#   Capturas 393x852 @3x (claro; P3, P9, P15 y P16 tambien en oscuro) y
#   manifest JSON con el resultado de cada prueba.
# Version: 0.1.0 (F05-05 K4-A2)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import traceback
import urllib.parse
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_f05_05 import eur, propuesta  # noqa: E402
from e2e_j2j3 import _exigir_local, _sql, api, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


class Fallo(Exception):
    pass


def exigir(cond: bool, mensaje: str) -> None:
    if not cond:
        raise Fallo(mensaje)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5491")
    ap.add_argument("--api", default="http://127.0.0.1:5490")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
    _exigir_local(dsn)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    hoy = dt.datetime.now(ZoneInfo("Europe/Madrid")).date()
    dia = lambda k: str(max(hoy.replace(day=1), hoy - dt.timedelta(days=k)))  # noqa: E731
    mes_anterior = str((hoy.replace(day=1) - dt.timedelta(days=1)).replace(day=10))

    # ---------------------------------------------------------------- preparacion (writers publicos)
    exigir_base_recreada(dsn, owner)
    nomina_cta = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta", "CREDITO", "PASIVO")
    ahorro = crear_cuenta(dsn, owner, "Ahorro", "AHORRO", "ACTIVO")
    ids: dict[str, str] = {}

    def categoria(clave, nombre, padre, ambito="GASTO", icono="compras.carrito"):
        ids[clave] = str(uuid.uuid4())
        api(a.api, "POST", "/v1/categorias", {"id": ids[clave], "nombre": nombre, "parent_id": None if padre is None else ids[padre],
                                              "ambito": ambito, "presupuestable_default": ambito == "GASTO", "icon_key": icono})
        return ids[clave]

    categoria("alim", "Alimentación", None)
    sup = categoria("sup", "Supermercados", "alim")
    fru = categoria("fru", "Fruta y verdura", "alim")
    categoria("hogar", "Hogar", None)
    drog = categoria("drog", "Droguería", "hogar")
    categoria("ocio", "Ocio", None)
    rest = categoria("rest", "Restaurantes", "ocio")
    categoria("inglab", "Ingresos laborales", None, "INGRESO", "finanzas.dinero")
    nomina = categoria("nom", "Nómina", "inglab", "INGRESO", "finanzas.dinero")

    def tercero(nombre):
        tid = str(uuid.uuid4())
        api(a.api, "POST", "/v1/terceros", {"id": tid, "nombre": nombre, "naturaleza": "EMPRESA"})
        return tid

    aldi, garcia, talleres, empresa = tercero("ALDI"), tercero("Frutería García"), tercero("Talleres García"), tercero("Empresa Servicios SL")
    rv = next(t for t in api(a.api, "GET", "/v1/terceros")["terceros"] if t["id"] == talleres)["row_version"]
    api(a.api, "POST", f"/v1/terceros/{talleres}/desactivar", {"row_version": rv})

    def gasto(fecha, importe, cat, ter, nota=None, atrib="SOLO_MIO", cuenta=None):
        c = {"intencion_id": str(uuid.uuid4()), "concepto": nota, "importe": importe, "moneda": "EUR", "fecha_hecho": fecha,
             "cuenta_id": cuenta or tarjeta, "presupuestable": True, "atribucion": atrib, "financiacion": propuesta(importe),
             "categoria": {"estado": "CATEGORIA", "categoria_id": cat} if cat else {"estado": "SIN_CATEGORIA"}}
        if ter:
            c["tercero_id"] = ter
        api(a.api, "POST", "/v1/intenciones/gasto-pagado", c)
        return c["intencion_id"]

    g_4872 = gasto(dia(1), "48.72", sup, aldi, "Compra semanal")
    for k, imp in enumerate(["31.15", "52.30", "27.80"]):
        gasto(dia(k + 2), imp, sup, aldi)
    gasto(dia(2), "6.45", drog, aldi)
    gasto(dia(3), "9.60", fru, garcia)
    g_sin = gasto(dia(1), "44.50", rest, None, "Cena con amigos", "SIN_INDICAR")
    for k in range(18):  # relleno para que la lista se pueda desplazar (P12)
        gasto(dia(k % 9), f"{3 + k}.10", rest, None, cuenta=nomina_cta)
    gasto(mes_anterior, "12.00", rest, None)
    i_nom = str(uuid.uuid4())
    api(a.api, "POST", "/v1/intenciones/ingreso-cobrado", {
        "intencion_id": i_nom, "importe": "2100.00", "moneda": "EUR", "fecha_hecho": dia(4), "cuenta_id": nomina_cta,
        "presupuestable": True, "atribucion": "SOLO_MIO", "categoria": {"estado": "CATEGORIA", "categoria_id": nomina},
        "nota": None, "tercero_id": empresa})
    t_500 = str(uuid.uuid4())
    api(a.api, "POST", "/v1/intenciones/transferencia", {"intencion_id": t_500, "importe": "500.00", "moneda": "EUR",
                                                        "fecha_hecho": dia(2), "cuenta_origen_id": nomina_cta,
                                                        "cuenta_destino_id": ahorro, "nota": None})

    resultados: list[dict] = []
    capturas: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        peticiones: list[str] = []
        page.on("request", lambda r: peticiones.append(r.url))
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731  (destinos persistentes ocultos)

        def shot(nombre, oscuro=False):
            f = salida / f"K4A2_{run}_{nombre}{'_oscuro' if oscuro else ''}_WEB-VIEWPORT-393x852.png"
            if oscuro:
                page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            if oscuro:
                page.emulate_media(color_scheme="light")
            capturas.append(f.name)
            return f.name

        def inicio():
            page.goto(a.web)
            t("accion-registrar").wait_for(timeout=30000)

        def nuevo_gasto():
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").wait_for()

        def con_senales_de_aldi(accion):
            """Los chips sin tercero ya existen al abrir el formulario: se espera la respuesta de las senales
            CON el tercero (y un pintado) antes de mirar chips o sugeridas."""
            with page.expect_response(lambda r: "/v1/senales/categorias" in r.url and f"tercero_id={aldi}" in r.url, timeout=15000):
                accion()
            page.wait_for_timeout(500)

        def elegir_aldi():
            t("campo-tercero").click()
            t(f"reciente-{aldi}").wait_for(timeout=15000)
            con_senales_de_aldi(lambda: t(f"reciente-{aldi}").click())
            t("chips-sugeridas").wait_for(timeout=15000)

        def basicos(importe="23,40"):
            t("campo-importe").fill(importe)
            if t("presupuestable-true").count():
                t("presupuestable-true").click()
            t(f"cuenta-{tarjeta}").click()

        def color(i):
            return t(i).evaluate("e => getComputedStyle(e).color")

        def prueba(pid, titulo, fn):
            reg = {"prueba": pid, "titulo": titulo}
            try:
                fn(reg)
                reg.setdefault("resultado", "OK_AUTOMATIZADA")
            except Exception as exc:  # KO: se anota y se sigue
                reg["resultado"] = "KO"
                reg["detalle"] = f"{type(exc).__name__}: {exc}".splitlines()[0][:400]
                reg["traza"] = traceback.format_exc().splitlines()[-3:]
                try:
                    reg.setdefault("capturas", []).append(shot(f"{pid}_KO"))
                except Exception:
                    pass
            resultados.append(reg)
            print(pid, reg["resultado"], reg.get("detalle", ""), flush=True)

        # ------------------------------------------------------------ P1
        def p1(reg):
            inicio()
            nuevo_gasto()
            t("campo-tercero").click()
            t("terceros-recientes").wait_for(timeout=15000)
            etiqueta = t(f"reciente-{aldi}").get_attribute("aria-label") or t(f"reciente-{aldi}").inner_text()
            reg["observado"] = etiqueta
            exigir("ALDI" in etiqueta and ("Usado" in etiqueta or "Frecuente en tus gastos" in etiqueta), f"«Recientes» sin ALDI o sin motivo: {etiqueta}")
            reg["capturas"] = [shot("P1_recientes")]

        # ------------------------------------------------------------ P2
        def p2(reg):
            antes = len(peticiones)
            t("tercero-filtro").fill("g")
            page.wait_for_timeout(800)
            buscadas = [u for u in peticiones[antes:] if "/v1/terceros?" in u and "q=" in u]
            exigir(not buscadas, f"con 1 carácter se buscó en el servidor: {buscadas}")
            t("tercero-filtro").fill("garcía")
            t(f"tercero-{garcia}").wait_for(timeout=10000)
            exigir(any("/v1/terceros?" in u and "q=garc" in u for u in peticiones[antes:]), "con «garcía» no se consultó el servidor")
            exigir(t(f"tercero-inactivo-{talleres}").count() == 1 and t(f"reactivar-{talleres}").count() == 1, "el inactivo «Talleres García» no sale con «Reactivar»")
            reg["capturas"] = [shot("P2_busqueda_garcia")]
            t("tercero-filtro").fill("")

        # ------------------------------------------------------------ P3
        def p3(reg):
            t(f"reciente-{aldi}").wait_for(timeout=10000)
            con_senales_de_aldi(lambda: t(f"reciente-{aldi}").click())
            t("chips-sugeridas").wait_for(timeout=15000)
            chips = page.locator('[data-testid^="chip-sugerida-"]:visible')
            orden = [chips.nth(i).get_attribute("data-testid") for i in range(chips.count())]
            reg["chips"] = orden
            exigir(0 < len(orden) <= 3 and orden[0] == f"chip-sugerida-{sup}", f"chips: {orden}")
            texto = t("chips-texto").inner_text()
            reg["texto"] = texto
            exigir(texto.startswith("Sugeridas: Supermercados") and "ALDI" in texto and texto.endswith("Toca una para elegirla."), f"línea de sugeridas: {texto}")
            exigir(t("categoria-valor").inner_text() == "Elige categoría", "la categoría no está en «Elige categoría»")
            reg["capturas"] = [shot("P3_chips"), shot("P3_chips", oscuro=True)]

        # ------------------------------------------------------------ P4
        def p4(reg):
            basicos()
            page.wait_for_timeout(500)
            exigir(t("registrar").get_attribute("aria-disabled") == "true" or t("registrar").is_disabled(), "«Registrar» habilitado sin categoría")
            exigir(t("faltan").inner_text() == "Para registrar falta: categoría.", f"faltan: {t('faltan').inner_text()}")
            reg["capturas"] = [shot("P4_registrar_deshabilitado")]

        # ------------------------------------------------------------ P5
        def p5(reg):
            t(f"chip-sugerida-{sup}").click()
            t("origen-categoria-usuario").wait_for()
            exigir(t("origen-categoria-usuario").inner_text() == "Elegida por ti.", "sin «Elegida por ti.»")
            exigir(t("chips-sugeridas").count() == 0, "los chips siguen visibles")
            exigir("Supermercados" in t("categoria-valor").inner_text(), "categoría no elegida")
            reg["capturas"] = [shot("P5_chip_elegido")]

        # ------------------------------------------------------------ P6 / P7 (gasto nuevo, sin tocar el anterior)
        def p6(reg):
            inicio()
            nuevo_gasto()
            elegir_aldi()
            t("campo-categoria").click()
            t("selector-sugeridas").wait_for(timeout=15000)
            fila = t(f"sugerida-{sup}")
            etiqueta = fila.get_attribute("aria-label") or ""
            reg["observado"] = etiqueta
            exigir("Alimentación › Supermercados" in etiqueta and "ALDI" in etiqueta, f"sugerida sin ruta o sin motivo: {etiqueta}")
            exigir(fila.get_attribute("aria-selected") != "true", "una sugerida aparece seleccionada")
            reg["capturas"] = [shot("P6_sugeridas")]

        def p7(reg):
            for q in ("super", "súper"):
                t("selector-busqueda").fill(q)
                t(f"resultado-{sup}").wait_for(timeout=10000)
                texto = t(f"resultado-{sup}").get_attribute("aria-label") or t(f"resultado-{sup}").inner_text()
                exigir("Supermercados" in texto and "Alimentación" in texto, f"«{q}»: {texto}")
                reg.setdefault("observado", []).append(texto)
            reg["capturas"] = [shot("P7_busqueda_super")]
            t("selector-cerrar").click()

        # ------------------------------------------------------------ P8
        def p8(reg):
            inicio()
            nuevo_gasto()
            elegir_aldi()
            t(f"chip-sugerida-{sup}").click()
            basicos()
            t("registrar").click()
            t("registro-exito").wait_for(timeout=20000)
            t("recordar-afinidad").wait_for(timeout=15000)
            reg["texto_tarjeta"] = t("recordar-afinidad").inner_text().splitlines()[0]
            exigir("Recordar Supermercados para ALDI" in t("recordar-afinidad").inner_text(), f"tarjeta: {reg['texto_tarjeta']}")
            t("recordar").click()
            t("recordar-hecho").wait_for(timeout=15000)
            capt = [shot("P8_recordada")]
            t("volver-inicio").click()
            nuevo_gasto()
            elegir_aldi()
            t(f"chip-sugerida-{sup}").click()
            basicos("5,00")
            t("registrar").click()
            t("registro-exito").wait_for(timeout=20000)
            page.wait_for_timeout(2500)
            exigir(t("recordar-afinidad").count() == 0, "se vuelve a ofrecer «Recordar» con el par ya guardado")
            n = _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.tercero_afinidades WHERE tercero_id=%s AND categoria_id=%s", (aldi, sup))[0][0]
            exigir(n == 1, f"afinidades del par: {n}")
            capt.append(shot("P8_sin_tarjeta"))
            reg["capturas"] = capt
            t("volver-inicio").click()

        # ------------------------------------------------------------ P9 / P10 / P11
        def p9(reg):
            inicio()
            t("tab-DIA").click()
            t(f"fila-{g_4872}").wait_for(timeout=15000)
            exigir(page.locator('[data-testid^="grupo-"]:visible').first.inner_text().startswith("Hoy · ") or
                   any(page.locator('[data-testid^="grupo-"]:visible').nth(i).inner_text().startswith(("Hoy · ", "Ayer · ")) for i in range(2)),
                   "sin grupos «Hoy · …» / «Ayer · …»")
            et = {k: t(f"fila-{v}").get_attribute("aria-label") for k, v in (("gasto", g_4872), ("ingreso", i_nom), ("transferencia", t_500), ("sin_indicar", g_sin))}
            reg["etiquetas"] = et
            exigir("−48,72 €" in et["gasto"], f"gasto sin «−»: {et['gasto']}")
            exigir("+2.100,00 €" in et["ingreso"], f"ingreso sin «+»: {et['ingreso']}")
            exigir("Cuenta nómina → Ahorro" in et["transferencia"] and "500,00 €" in et["transferencia"] and "−500" not in et["transferencia"] and "+500" not in et["transferencia"], f"transferencia: {et['transferencia']}")
            exigir("Total · reparto sin indicar" in et["sin_indicar"], f"sin indicar: {et['sin_indicar']}")
            reg["capturas"] = [shot("P9_actividad"), shot("P9_actividad", oscuro=True)]

        def p10(reg):
            capt = []
            for nombre, hid in (("gasto", g_4872), ("ingreso", i_nom), ("transferencia", t_500)):
                t(f"fila-{hid}").click()
                t("detalle-contenido").wait_for(timeout=15000)
                txt = t("detalle-contenido").inner_text()
                if nombre == "transferencia":
                    exigir(t("kv-Tu parte").count() == 0, "la transferencia muestra «Tu parte»")
                    exigir("No es un gasto ni un ingreso" in txt, "falta el texto de la transferencia")
                else:
                    exigir(t("kv-Tu parte").count() == 1 and t("kv-Total del hecho").count() == 1, f"{nombre}: falta «Tu parte» o «Total del hecho»")
                capt.append(shot(f"P10_detalle_{nombre}"))
                t("detalle-cerrar").click()
            reg["capturas"] = capt

        def p11(reg):
            t("actividad-buscar").click()
            for q in ("48,72", "48.72"):
                t("actividad-busqueda").fill(q)
                page.wait_for_timeout(900)
                t("actividad-alcance").wait_for(timeout=15000)
                alc = t("actividad-alcance").inner_text()
                reg.setdefault("alcance", []).append(alc)
                exigir("Buscando en todo el historial · importe exacto · 1 resultado" == alc, f"«{q}»: {alc}")
                exigir(t(f"fila-{g_4872}").count() == 1, f"«{q}»: no aparece el registro de 48,72")
            reg["capturas"] = [shot("P11_busqueda_importe")]
            t("actividad-cancelar-busqueda").click()

        # ------------------------------------------------------------ P12
        def p12(reg):
            inicio()
            t("tab-DIA").click()
            t(f"fila-{g_4872}").wait_for(timeout=15000)
            # (a) periodo restaurado
            t("actividad-periodo").click()
            t("periodo-MES_ANTERIOR").click()
            page.wait_for_timeout(800)
            t("actividad-buscar").click()
            t("actividad-busqueda").fill("aldi")
            page.wait_for_timeout(900)
            t("actividad-cancelar-busqueda").click()
            page.wait_for_timeout(800)
            exigir(t("actividad-periodo").get_attribute("aria-label") == "Periodo: Mes anterior", "no se restaura «Mes anterior»")
            t("actividad-periodo").click()
            t("periodo-ESTE_MES").click()
            t(f"fila-{g_4872}").wait_for(timeout=15000)
            # (b) filtros y desplazamiento restaurados
            t("actividad-filtros").click()
            t("filtro-tipo-GASTO").click()
            t("filtros-ver").click()
            t("actividad-linea-filtros").wait_for(timeout=15000)
            page.wait_for_timeout(800)
            desplazable = page.evaluate("""() => {
                const lista = [...document.querySelectorAll('[data-testid="actividad-lista"]')].find(e => e.offsetParent !== null);
                let e = lista; while (e && !(e.scrollHeight > e.clientHeight + 10 && ['auto','scroll'].includes(getComputedStyle(e).overflowY))) e = e.parentElement;
                if (!e) { const d = lista && lista.querySelector('*'); }
                if (!e) return null;
                e.setAttribute('data-k4a2-scroll', '1');
                e.scrollTop = Math.floor((e.scrollHeight - e.clientHeight) / 2);
                return [e.scrollTop, e.scrollHeight, e.clientHeight];
            }""")
            reg["desplazable"] = desplazable
            if not desplazable or desplazable[0] <= 0:
                reg["resultado"] = "NO_AUTOMATIZABLE"
                reg["detalle"] = f"no se encontró un contenedor desplazable en web ({desplazable}); periodo restaurado OK; filtros y scroll a iPhone"
                return
            page.wait_for_timeout(600)
            antes = page.evaluate("() => document.querySelector('[data-k4a2-scroll]').scrollTop")
            t("actividad-buscar").click()
            t("actividad-busqueda").fill("aldi")
            page.wait_for_timeout(900)
            t("actividad-cancelar-busqueda").click()
            page.wait_for_timeout(1200)
            despues = page.evaluate("() => { const e = document.querySelector('[data-k4a2-scroll]'); return e ? e.scrollTop : null; }")
            reg["scroll"] = {"antes": antes, "despues": despues}
            exigir(t("actividad-linea-filtros").count() == 1, "no se restauran los filtros")
            exigir(despues is not None and abs(despues - antes) <= 4, f"scroll no restaurado: antes {antes}, después {despues}")
            reg["capturas"] = [shot("P12_restaurado")]
            t("actividad-limpiar").click()

        # ------------------------------------------------------------ P13
        def p13(reg):
            inicio()
            t("tab-DIA").click()
            t(f"fila-{g_4872}").wait_for(timeout=15000)
            t("actividad-filtros").click()
            t("filtro-tipo-GASTO").click()
            t("filtro-cuenta").click()
            t(f"lista-{tarjeta}").wait_for(timeout=10000)
            t(f"lista-{tarjeta}").click()
            ver = t("filtros-ver").inner_text()
            reg["boton"] = ver
            exigir(ver.startswith("Ver ") and "resultado" in ver, f"botón: {ver}")
            t("filtros-ver").click()
            t("actividad-linea-filtros").wait_for(timeout=15000)
            exigir("Filtros · 2" in t("actividad-filtros").inner_text(), f"botón de filtros: {t('actividad-filtros').inner_text()}")
            exigir("Gasto · Tarjeta" in t("actividad-linea-filtros").inner_text(), f"línea: {t('actividad-linea-filtros').inner_text()}")
            reg["capturas"] = [shot("P13_filtros")]
            t("actividad-limpiar").click()
            page.wait_for_timeout(800)
            exigir(t("actividad-linea-filtros").count() == 0, "«Limpiar» no quita la línea de filtros")

        # ------------------------------------------------------------ P14
        def p14(reg):
            page.route("**/v1/actividad?**", lambda r: r.abort())
            t("actividad-periodo").click()
            t("periodo-MES_ANTERIOR").click()
            t("actividad-error").wait_for(timeout=15000)
            exigir(t("actividad-vacio").count() == 0, "el fallo se presenta como «No hay registros»")
            exigir("No se ha podido cargar la actividad" in t("actividad-error").inner_text(), "texto de error distinto")
            capt = [shot("P14_error")]
            page.unroute("**/v1/actividad?**")
            t("actividad-reintentar").click()
            page.wait_for_timeout(1500)
            exigir(t("actividad-error").count() == 0, "tras «Reintentar» sigue el error")
            reg["capturas"] = capt + [shot("P14_reintentado")]

        # ------------------------------------------------------------ P15
        def p15(reg):
            inicio()
            t("mes-resultado").wait_for(timeout=15000)
            yo = api(a.api, "GET", "/v1/yo")
            rm = api(a.api, "GET", f"/v1/inicio/resultado-mes?fecha={hoy}")
            reg["api"] = rm
            if yo.get("nombre"):
                exigir(t("hola").inner_text() == f"Hola, {yo['nombre']}", f"saludo: {t('hola').inner_text()}")
            exigir(t("mes-ingresos").inner_text() == eur(rm["ingresos_propios"]) and t("mes-gastos").inner_text() == eur(rm["gastos_propios"]), "Ingresos/Gastos distintos de la API")
            exigir(t("mes-resultado").inner_text() == eur(rm["resultado"], signo=True), "Resultado distinto de la API")
            ci, cg, cr = color("mes-ingresos"), color("mes-gastos"), color("mes-resultado")
            reg["colores"] = {"ingresos": ci, "gastos": cg, "resultado": cr}
            exigir(ci == cg and cr != cg, f"color solo en Resultado: {reg['colores']}")
            linea = t("mes-sin-indicar").inner_text()
            reg["linea"] = linea
            g = rm["sin_indicar"]["gastos"]  # P8 deja dos gastos mas «Sin indicar» (registro por la UI sin «Solo mío»)
            esperado = f"Solo lo que es tuyo. Sin indicar: {g['n']} {'gasto' if g['n'] == 1 else 'gastos'} ({eur(g['importe'])})"
            exigir(g["n"] >= 1 and linea.startswith(esperado), f"línea «Sin indicar»: {linea} (esperado {esperado})")
            exigir(Decimal(rm["resultado"]) > 0, "el escenario esperaba Resultado positivo (verde)")
            reg["capturas"] = [shot("P15_inicio"), shot("P15_inicio", oscuro=True)]

        # ------------------------------------------------------------ P16
        def p16(reg):
            inicio()
            t("tab-MAS").click()
            if t("mas-ajustes").count():
                t("mas-ajustes").click()
            t("ajustes-terceros").click()
            t(f"ajter-fila-{aldi}").click()
            t(f"habitual-{sup}").wait_for(timeout=15000)
            uso = t("ajter-uso-texto").inner_text()
            reg["uso"] = uso
            exigir(" registros · último " in uso, f"«Uso en Gapto»: {uso}")
            capt = [shot("P16_tercero"), shot("P16_tercero", oscuro=True)]
            t(f"habitual-quitar-{sup}").click()
            exigir(page.get_by_text("¿Quitar Supermercados de ALDI?").count() >= 1, "sin confirmación de «Quitar»")
            capt.append(shot("P16_confirmar_quitar"))
            t("ajter-quitar-cancelar").click()
            t(f"historial-guardar-{drog}").click()
            t(f"habitual-{drog}").wait_for(timeout=15000)
            t("ajter-anadir-categoria").click()
            t("cat-" + ids["alim"]).click()
            et = t(f"cat-{sup}").get_attribute("aria-label") or ""
            exigir("Ya es habitual" in et, f"«+ Añadir categoría» no marca la habitual: {et}")
            capt.append(shot("P16_ya_es_habitual"))
            t("selector-cerrar").click()
            t("ajter-ver-registros").click()
            t("pantalla-actividad").wait_for(timeout=15000)
            page.wait_for_timeout(800)
            exigir(t("actividad-periodo").get_attribute("aria-label") == "Periodo: Todo el historial", "«Ver sus registros» sin «Todo el historial»")
            capt.append(shot("P16_registros_de_aldi"))
            t("actividad-limpiar").click()
            t("pestana-actividad").wait_for(timeout=15000)
            reg["capturas"] = capt

        for pid, titulo, fn in (
            ("P1", "«Recientes» con ALDI y su motivo", p1), ("P2", "búsqueda «g» local y «garcía» en el servidor con inactivo y «Reactivar»", p2),
            ("P3", "chips (máx. 3, Supermercados primero) y línea de sugeridas; categoría sin elegir", p3),
            ("P4", "«Registrar» deshabilitado y «Para registrar falta: categoría.»", p4), ("P5", "chip → «Elegida por ti.», chips fuera", p5),
            ("P6", "«Sugeridas» en el selector con ruta y motivo, nada marcado", p6), ("P7", "«super» y «súper» → Supermercados con ruta", p7),
            ("P8", "«¿Recordar…?» → «Recordar»; segundo registro sin tarjeta", p8), ("P9", "Actividad: grupos, signos, transferencia neutra, sin indicar", p9),
            ("P10", "detalle de gasto, ingreso y transferencia", p10), ("P11", "búsqueda por importe «48,72» y «48.72»", p11),
            ("P12", "«Cancelar» restaura periodo, filtros y desplazamiento", p12), ("P13", "filtros Gasto + cuenta, «Filtros · 2», «Limpiar»", p13),
            ("P14", "sin red: error con «Reintentar», nunca vacío", p14), ("P15", "Inicio: «Hola», cifras, color solo en Resultado, «Sin indicar»", p15),
            ("P16", "Ajustes › Terceros › ALDI (uso, Quitar, Guardar, Ya es habitual, Ver sus registros, Limpiar)", p16),
        ):
            prueba(pid, titulo, fn)
        nav.close()

    manifest = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "resultados": resultados, "capturas": capturas}
    (salida / f"K4A2_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    resumen = {}
    for r in resultados:
        resumen[r["resultado"]] = resumen.get(r["resultado"], 0) + 1
    print(f"RESUMEN {run}: {resumen}")


if __name__ == "__main__":
    main()
