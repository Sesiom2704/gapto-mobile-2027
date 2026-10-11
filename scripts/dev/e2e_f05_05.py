# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_05.py
# Ruta: scripts/dev/e2e_f05_05.py
# Descripcion: E2E web de F05-05 K3 (mandato §2.11; F05 §49.4 A1-A13;
#   lamina SRCH-ACT-AFI v0.2): sugerencias y chips, busqueda de categorias y
#   de terceros (con «garcía»), recordar afinidad y su gestion en Ajustes,
#   Actividad (lista, periodo, busqueda, filtros, detalle, vacio y error
#   simulado) e Inicio con Resultado y «Sin indicar».
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Datos con NOMBRES LEGIBLES. Exige una base dev local RECIEN RECREADA
#   (bootstrap_dev_db --recrear, sin --seed-categorias). La preparacion usa
#   SOLO los writers publicos (/v1/categorias, /v1/terceros,
#   /v1/intenciones/*); las cuentas, que no tienen writer, se crean como
#   gapto_owner igual que e2e_j2j3. Fechas relativas al dia de hoy (Madrid),
#   dentro del mes en curso. El id de ejecucion solo aparece en el manifest y
#   en el nombre de las capturas.
#
#   Escenario (claro; Inicio, Actividad y Ajustes tambien en oscuro):
#     E    Inicio: «Hola, <nombre>», Ingresos/Gastos/Resultado iguales a
#          GET /v1/inicio/resultado-mes y la linea «Sin indicar».
#     S    Gasto: «Recientes» en el selector de tercero; busqueda de servidor
#          «garcía» encuentra «Frutería García»; se elige ALDI; chips bajo
#          «Categoría» (nada elegido hasta tocar); chip -> Supermercados
#          («Elegida por ti.»); registro; «¿Recordar…?» -> «Recordar» (fila
#          en tercero_afinidades).
#     B    Gasto: «Sugeridas» en el selector y busqueda «drog» -> Droguería
#          (resultado con ruta); registro con Frutería García.
#     F    Ajustes › Terceros › ALDI: «Uso en Gapto», habitual Supermercados,
#          «Según tu historial» Droguería -> «Guardar» (segunda afinidad);
#          «Ver sus registros» -> Actividad del tercero; «Limpiar».
#     A    Día a día: lista; detalle de un gasto; busqueda por importe
#          «48,72» en todo el historial y «Cancelar»; filtro Tipo Gasto;
#          «Mes anterior» vacio; error simulado (la peticion se aborta) con
#          «Reintentar».
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-05 K3 §2.11)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


def eur(v: str | Decimal, signo: bool = False) -> str:
    """Formato es-ES del cliente: «1.234,56 €»; con signo, «+» o «−» (U+2212)."""
    d = Decimal(str(v))
    entero, dec = f"{abs(d):.2f}".split(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    texto = ".".join([entero, *grupos]) + f",{dec} €"
    if signo and d != 0:
        return ("+" if d > 0 else "−") + texto
    return texto


def propuesta(importe: str) -> dict:
    return {"estado": "PROPUESTA_ACEPTADA", "actor": "SELF", "criterio": "PARTICIPACION_CUENTA", "porcentaje": "100", "importe": importe}


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
    dia = lambda k: str(max(hoy.replace(day=1), hoy - dt.timedelta(days=k)))  # noqa: E731  (dentro del mes)

    # ---------------------------------------------------------------- preparacion (writers publicos)
    exigir_base_recreada(dsn, owner)
    nomina_cta = crear_cuenta(dsn, owner, "Cuenta nómina", "CORRIENTE", "ACTIVO")
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta", "CREDITO", "PASIVO")
    ids: dict[str, str] = {}

    def categoria(clave: str, nombre: str, padre: str | None, ambito: str = "GASTO", icono: str = "compras.carrito") -> str:
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

    def tercero(nombre: str) -> str:
        tid = str(uuid.uuid4())
        api(a.api, "POST", "/v1/terceros", {"id": tid, "nombre": nombre, "naturaleza": "EMPRESA"})
        return tid

    aldi, garcia, empresa = tercero("ALDI"), tercero("Frutería García"), tercero("Empresa Servicios SL")

    def gasto(fecha: str, importe: str, cat: str | None, ter: str | None, nota: str | None = None, atrib: str = "SOLO_MIO") -> None:
        c = {"intencion_id": str(uuid.uuid4()), "concepto": nota, "importe": importe, "moneda": "EUR", "fecha_hecho": fecha,
             "cuenta_id": tarjeta, "presupuestable": True, "atribucion": atrib, "financiacion": propuesta(importe),
             "categoria": {"estado": "CATEGORIA", "categoria_id": cat} if cat else {"estado": "SIN_CATEGORIA"}}
        if ter:
            c["tercero_id"] = ter
        api(a.api, "POST", "/v1/intenciones/gasto-pagado", c)

    for k, imp in enumerate(["48.72", "31.15", "52.30", "27.80"]):
        gasto(dia(k + 1), imp, sup, aldi, "Compra semanal" if k == 0 else None)
    gasto(dia(2), "6.45", drog, aldi)
    gasto(dia(3), "9.60", fru, garcia)
    gasto(dia(1), "44.50", rest, None, "Cena con amigos", "SIN_INDICAR")
    api(a.api, "POST", "/v1/intenciones/ingreso-cobrado", {
        "intencion_id": str(uuid.uuid4()), "importe": "2100.00", "moneda": "EUR", "fecha_hecho": dia(4), "cuenta_id": nomina_cta,
        "presupuestable": True, "atribucion": "SOLO_MIO", "categoria": {"estado": "CATEGORIA", "categoria_id": nomina},
        "nota": None, "tercero_id": empresa})

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy)}

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        consola: list[str] = []
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.goto(a.web)
        # Los destinos persistentes siguen montados (ocultos): se actua solo sobre lo visible.
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"F0505_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def registrar(clave: str) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/intenciones/gasto-pagado"), timeout=20000) as resp:
                t("registrar").click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == 200, f"{clave}: registro HTTP {resp.value.status} {cuerpo.get('codigo')}")
            res.setdefault("hechos", {})[clave] = cuerpo["hecho_id"]
            return cuerpo

        def ajustes_terceros() -> None:
            t("tab-MAS").click()
            if t("mas-ajustes").count():
                t("mas-ajustes").click()
            t("ajustes-terceros").click()
            t("pantalla-terceros").wait_for()

        t("accion-registrar").wait_for(timeout=30000)
        # ------------------------------------------------------------ E Inicio
        rm = api(a.api, "GET", f"/v1/inicio/resultado-mes?fecha={hoy}")
        yo = api(a.api, "GET", "/v1/yo")
        t("mes-resultado").wait_for(timeout=15000)
        res["E"] = {"api": rm, "yo": yo, "ui": {k: t(f"mes-{k}").inner_text() for k in ("ingresos", "gastos", "resultado", "sin-indicar")}}
        comprobar(res["E"]["ui"]["ingresos"] == eur(rm["ingresos_propios"]), f"E: ingresos {res['E']['ui']}")
        comprobar(res["E"]["ui"]["gastos"] == eur(rm["gastos_propios"]), f"E: gastos {res['E']['ui']}")
        comprobar(res["E"]["ui"]["resultado"] == eur(rm["resultado"], signo=True), f"E: resultado {res['E']['ui']}")
        si = rm["sin_indicar"]["gastos"]
        comprobar(si["n"] == 1 and Decimal(si["importe"]) == Decimal("44.50"), f"E: sin indicar API {rm['sin_indicar']}")
        comprobar(f"1 gasto ({eur('44.50')})" in res["E"]["ui"]["sin-indicar"], f"E: línea «Sin indicar»: {res['E']['ui']['sin-indicar']}")
        if yo.get("nombre"):
            comprobar(t("hola").inner_text() == f"Hola, {yo['nombre']}", "E: saludo")
        shot("E01_inicio_resultado")
        oscuro("E01_inicio_resultado")

        # ------------------------------------------------------------ S sugerencias, chips y recordar
        t("accion-registrar").click()
        t("tipo-GASTO").click()
        t("campo-importe").fill("23,40")
        t("campo-tercero").click()
        t("terceros-recientes").wait_for(timeout=15000)
        comprobar(t(f"reciente-{aldi}").count() == 1, "S: ALDI no está en «Recientes»")
        shot("S01_terceros_recientes")
        t("tercero-filtro").fill("garcía")
        t(f"tercero-{garcia}").wait_for(timeout=10000)
        res["S_busqueda_garcia"] = t(f"tercero-{garcia}").inner_text()
        shot("S02_busqueda_garcia")
        t("tercero-filtro").fill("")
        t(f"reciente-{aldi}").wait_for(timeout=10000)
        t(f"reciente-{aldi}").click()
        t("chips-sugeridas").wait_for(timeout=15000)
        comprobar(t(f"chip-sugerida-{sup}").count() == 1, "S: falta el chip Supermercados")
        comprobar(t("categoria-valor").count() == 0 or "Supermercados" not in t("categoria-valor").inner_text(), "S: categoría preseleccionada por una señal")
        comprobar(t("registrar").is_disabled() or t("faltan").count() == 1, "S: «Registrar» habilitado sin categoría")
        shot("S03_chips_sugeridas")
        t(f"chip-sugerida-{sup}").click()
        t("origen-categoria-usuario").wait_for()
        comprobar(t("origen-categoria-usuario").inner_text() == "Elegida por ti.", "S: origen de la categoría")
        if t(f"cuenta-{tarjeta}").count():
            t(f"cuenta-{tarjeta}").click()
        if t("presupuestable-true").count():
            t("presupuestable-true").click()
        page.wait_for_timeout(600)
        shot("S04_chip_elegido")
        registrar("S")
        t("registro-exito").wait_for()
        t("recordar-afinidad").wait_for(timeout=15000)
        shot("S05_recordar")
        t("recordar").click()
        t("recordar-hecho").wait_for(timeout=15000)
        shot("S06_recordada")
        af = _sql(dsn, owner, "gapto_runtime", "SELECT tercero_id, categoria_id FROM gapto.tercero_afinidades")
        res["S_afinidades"] = [[str(x), str(y)] for x, y in af]
        comprobar(res["S_afinidades"] == [[aldi, sup]], f"S: afinidad: {res['S_afinidades']}")
        t("volver-inicio").click()

        # ------------------------------------------------------------ B busqueda de categorias
        t("accion-registrar").click()
        t("tipo-GASTO").click()
        t("campo-importe").fill("3,95")
        t("campo-categoria").click()
        t("selector-sugeridas").wait_for(timeout=15000)
        shot("B01_selector_sugeridas")
        t("selector-busqueda").fill("drog")
        t(f"resultado-{drog}").wait_for(timeout=10000)
        res["B_resultado"] = t(f"resultado-{drog}").inner_text()
        comprobar("Hogar" in res["B_resultado"], f"B: el resultado no muestra la ruta: {res['B_resultado']}")
        shot("B02_busqueda_drog")
        t(f"resultado-{drog}").click()
        t("categoria-valor").wait_for()
        comprobar("Droguería" in t("categoria-valor").inner_text(), "B: categoría elegida")
        t("campo-tercero").click()
        t("tercero-filtro").fill("garcía")
        t(f"tercero-{garcia}").wait_for(timeout=10000)
        t(f"tercero-{garcia}").click()
        if t(f"cuenta-{tarjeta}").count():
            t(f"cuenta-{tarjeta}").click()
        if t("presupuestable-true").count():
            t("presupuestable-true").click()
        page.wait_for_timeout(600)
        registrar("B")
        t("registro-exito").wait_for()
        t("volver-inicio").click()

        # ------------------------------------------------------------ F Ajustes › Terceros (C1–C4)
        ajustes_terceros()
        t(f"ajter-fila-{aldi}").click()
        t(f"habitual-{sup}").wait_for(timeout=15000)
        res["F_uso"] = t("ajter-uso-texto").inner_text()
        comprobar(t(f"historial-guardar-{drog}").count() == 1, "F: Droguería no está en «Según tu historial»")
        shot("F01_tercero_habituales")
        oscuro("F01_tercero_habituales")
        t(f"historial-guardar-{drog}").click()
        t(f"habitual-{drog}").wait_for(timeout=15000)
        shot("F02_guardada_del_historial")
        af = _sql(dsn, owner, "gapto_runtime", "SELECT categoria_id FROM gapto.tercero_afinidades WHERE tercero_id = %s", (aldi,))
        res["F_afinidades"] = sorted(str(x[0]) for x in af)
        comprobar(res["F_afinidades"] == sorted([sup, drog]), f"F: afinidades: {res['F_afinidades']}")
        t("ajter-ver-registros").click()
        t("pantalla-actividad").wait_for(timeout=15000)
        t(f"fila-{res['hechos']['S']}").wait_for(timeout=15000)
        comprobar(t("actividad-periodo").get_attribute("aria-label") == "Periodo: Todo el historial", "F: periodo del tercero")
        shot("F03_registros_de_aldi")
        t("actividad-limpiar").click()
        t("pestana-actividad").wait_for(timeout=15000)

        # ------------------------------------------------------------ A Actividad
        t("tab-DIA").click()
        t("actividad-lista").wait_for(timeout=15000)
        filas = page.locator("[data-testid^=fila-]:visible")
        filas.first.wait_for(timeout=15000)
        res["A_filas"] = filas.count()
        comprobar(res["A_filas"] == 10, f"A: filas del mes: {res['A_filas']}")
        shot("A01_lista")
        oscuro("A01_lista")
        t(f"fila-{res['hechos']['S']}").click()
        t("detalle-contenido").wait_for(timeout=15000)
        shot("A02_detalle")
        t("detalle-cerrar").click()
        t("actividad-buscar").click()
        t("actividad-busqueda").fill("48,72")
        t("actividad-alcance").wait_for(timeout=15000)
        page.wait_for_timeout(700)
        res["A_alcance"] = t("actividad-alcance").inner_text()
        comprobar(page.locator("[data-testid^=fila-]:visible").count() == 1, "A: búsqueda por importe")
        shot("A03_busqueda_importe")
        t("actividad-cancelar-busqueda").click()
        page.wait_for_timeout(700)
        t("actividad-filtros").click()
        t("filtro-tipo-GASTO").click()
        t("filtros-ver").click()
        t("actividad-linea-filtros").wait_for(timeout=15000)
        page.wait_for_timeout(700)
        res["A_filtro_gasto"] = page.locator("[data-testid^=fila-]:visible").count()
        comprobar(res["A_filtro_gasto"] == 9, f"A: filtro Gasto: {res['A_filtro_gasto']}")
        shot("A04_filtro_gasto")
        t("actividad-limpiar").click()
        t("actividad-periodo").click()
        t("periodo-MES_ANTERIOR").click()
        t("actividad-vacio").wait_for(timeout=15000)
        shot("A05_mes_anterior_vacio")
        page.route("**/v1/actividad?**", lambda r: r.abort())
        t("actividad-periodo").click()
        t("periodo-ESTE_MES").click()
        t("actividad-error").wait_for(timeout=15000)
        comprobar(t("actividad-vacio").count() == 0, "A: error presentado como vacío")
        shot("A06_error_simulado")
        page.unroute("**/v1/actividad?**")
        t("actividad-reintentar").click()
        t(f"fila-{res['hechos']['S']}").wait_for(timeout=15000)
        shot("A07_reintentado")
        nav.close()

    # Errores de consola esperados: solo las peticiones abortadas a proposito en A06.
    res["errores_consola"] = consola
    inesperados = [m for m in consola if "ERR_FAILED" not in m and "Failed to fetch" not in m and "net::" not in m]
    res["capturas"] = capturas
    (salida / f"F0505_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not inesperados, f"errores de consola: {inesperados[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
