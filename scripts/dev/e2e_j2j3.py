# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_j2j3.py
# Ruta: scripts/dev/e2e_j2j3.py
# Descripcion: E2E web de F05-03/F05-04 J2+J3 (mandato §2.8): los tres tipos de
#   registro, plantilla y acceso rapido, tercero nuevo y duplicado inactivo,
#   contexto, «No lo sé», «Guardar como plantilla» y «Guardar como
#   preferencia», Ajustes (Plantillas, Terceros, Contextos, Preferencias),
#   onboarding de categorias, marca de Inicio (AJUSTE A1) y corte de Concepto.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Datos con NOMBRES LEGIBLES: cuentas «Cuenta nómina» (CORRIENTE), «Tarjeta»
#   (CREDITO, PASIVO) y «Ahorro» (AHORRO), con sus capacidades sinteticas;
#   tercero inactivo «Mercadona» por la API publica; el resto se crea DESDE LA
#   UI. El id de ejecucion no aparece en ningun texto visible (solo en el
#   manifest y en el nombre de las capturas). Exige una base dev local RECIEN
#   RECREADA (bootstrap_dev_db --recrear, sin --seed-categorias): sin
#   categorias, plantillas, terceros, contextos ni preferencias; si no, falla
#   con un error claro. Cada hecho se localiza en la BD por su UUID
#   (intencion_id del POST; hecho_id de la respuesta), nunca por concepto.
#
#   Escenario (claro; Inicio, registro y Ajustes tambien en oscuro):
#     O    Ajustes › Categorias sin categorias: O01 -> «Empezar con categorias
#          sugeridas» -> O02 -> «Crear estas categorias» (23 grupos en la BD).
#     T    Ajustes › Terceros: «Mercadona» con el inactivo homonimo -> P02 ->
#          «Reactivar» (misma fila, enabled); alta de «Panadería Rosa».
#     C    Ajustes › Contextos: «Finde Cartagena» (Viaje, 10–12 oct).
#     P    Ajustes › Plantillas: «Súper semanal» (Gasto, Supermercados,
#          Tarjeta, presupuesto Sí, en Inicio como «Súper»).
#     F    Ajustes › Preferencias: «Todos los ingresos» -> cobrar en «Cuenta
#          nómina».
#     H    Inicio: marca (un elemento «GaptoMobile»), acceso «Súper».
#     G    Gasto desde el acceso: chip de plantilla y origen; tercero
#          Mercadona; contexto; SIN nota (concepto y descripcion NULL) ->
#          titulo «Mercadona · Supermercados» -> «Guardar como preferencia»
#          para Mercadona.
#     N    Gasto con «No lo sé» (Movilidad › Combustible con magnitud
#          obligatoria «Litros» creada por la API): sin fila de magnitud.
#     I    Ingreso: «De» con alta minima de «ACME Servicios», Nómina, cuenta
#          propuesta por la preferencia de ingresos, nota «Nómina octubre» ->
#          «Guardar como plantilla…» «Nómina».
#     X    Entre cuentas: Cuenta nómina -> Ahorro; misma cuenta bloqueada.
#     K    Cambio de tipo T02 (Gasto -> Ingreso) con su aviso, sin registrar.
#   Capturas 393x852 @3x y manifest JSON con el estado de la BD por UUID.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-03/F05-04 J2+J3 §2.8)
# Version: 0.1.1 (§5): SQL estatico en exigir_base_recreada (inventario I6) y esperas a la carga
#   de Plantillas/Preferencias y a los accesos de Inicio.
# ============================================================

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

import psycopg
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capacidades_sinteticas import capacidades_de  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"
SERVIDOR_WEB = pathlib.Path(__file__).resolve().parent / "servir_web_e2e.py"
NOMINA_CTA, TARJETA, AHORRO = "Cuenta nómina", "Tarjeta", "Ahorro"


@contextlib.contextmanager
def servidor_web(dist: str | None, web: str):
    if not dist:
        yield
        return
    puerto = urllib.parse.urlsplit(web).port or 8081
    proc = subprocess.Popen([sys.executable, str(SERVIDOR_WEB), dist, str(puerto)])
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(web, timeout=2).read()
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise SystemExit("FALLO: el servidor web del E2E no responde")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _exigir_local(dsn: str) -> None:
    host = psycopg.conninfo.conninfo_to_dict(dsn).get("host", "")
    if host not in ("", "localhost", "127.0.0.1"):
        raise SystemExit("FALLO: el E2E solo se ejecuta contra PostgreSQL LOCAL")


def _sql(dsn: str, owner: str, rol: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute(f"SET LOCAL ROLE {rol}")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def crear_cuenta(dsn: str, owner: str, nombre: str, tipo: str, naturaleza: str) -> str:
    """Cuenta EUR con sus capacidades sinteticas y participacion 100 % del actor self."""
    cid = str(uuid.uuid4())
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_owner")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")
        actor = cur.fetchone()[0]
        cur.execute("INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, computa_liquidez, "
                    "computa_patrimonio, permite_negativo) VALUES (%s, %s, %s, %s, %s, 'EUR', true, true, false)",
                    (cid, owner, nombre, tipo, naturaleza))
        for capacidad in capacidades_de(tipo):
            cur.execute("INSERT INTO gapto.cuenta_capacidades (cuenta_id, capacidad_codigo) VALUES (%s, %s)", (cid, capacidad))
        cur.execute("INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, vigente_desde) "
                    "VALUES (%s, %s, 100, DATE '2026-01-01')", (cid, actor))
    return cid


def api(base: str, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(f"{base}{ruta}", data=datos, method=metodo, headers={
        "Authorization": f"Bearer {os.environ['GAPTO_DEV_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def comprobar(cond: bool, mensaje: str) -> None:
    if not cond:
        raise SystemExit(f"FALLO: {mensaje}")


def exigir_base_recreada(dsn: str, owner: str) -> None:
    consultas = {  # SQL estatico (sin nombres de tabla dinamicos)
        "categorias_financieras": "SELECT 1 FROM gapto.categorias_financieras LIMIT 1",
        "plantillas_registro": "SELECT 1 FROM gapto.plantillas_registro LIMIT 1",
        "preferencias_registro": "SELECT 1 FROM gapto.preferencias_registro LIMIT 1",
        "terceros": "SELECT 1 FROM gapto.terceros LIMIT 1",
    }
    for tabla, sql in consultas.items():
        if _sql(dsn, owner, "gapto_runtime", sql):
            raise SystemExit(f"FALLO: la base dev ya tiene filas en {tabla}. Recreala con "
                             "scripts/dev/bootstrap_dev_db.py --recrear (sin --seed-categorias) antes del E2E.")
    if _sql(dsn, owner, "gapto_runtime", "SELECT 1 FROM gapto.entidades WHERE tipo_entidad = 'CONTEXTO' LIMIT 1"):
        raise SystemExit("FALLO: la base dev ya tiene contextos. Recreala con bootstrap_dev_db.py --recrear.")


def hecho(dsn: str, owner: str, hecho_id: str) -> dict:
    """Estado del hecho por su UUID: tipo, concepto, descripcion del movimiento, tercero, contexto, categoria y magnitudes."""
    f = _sql(dsn, owner, "gapto_runtime",
             "SELECT t.codigo, h.importe_total, h.concepto, h.presupuestable FROM gapto.hechos_financieros h "
             "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id = %s", (hecho_id,))
    if not f:
        return {}
    movs = _sql(dsn, owner, "gapto_runtime",
                "SELECT m.cuenta_id, m.importe, m.descripcion FROM gapto.movimientos_tesoreria m "
                "JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id = m.id WHERE c.hecho_id = %s "
                "ORDER BY m.importe", (hecho_id,))
    efectos = _sql(dsn, owner, "gapto_runtime", "SELECT tipo_efecto, categoria_id FROM gapto.hecho_efectos WHERE hecho_id = %s", (hecho_id,))
    mags = _sql(dsn, owner, "gapto_runtime", "SELECT magnitud_id FROM gapto.hecho_magnitudes WHERE hecho_id = %s", (hecho_id,))
    vinculos = _sql(dsn, owner, "gapto_runtime",
                    "SELECT 'TERCERO', tercero_id FROM gapto.hecho_terceros WHERE hecho_id = %s "
                    "UNION ALL SELECT 'CONTEXTO', entidad_id FROM gapto.hecho_entidades WHERE hecho_id = %s", (hecho_id, hecho_id))
    return {
        "tipo": f[0][0], "importe": str(f[0][1]), "concepto": f[0][2], "presupuestable": f[0][3],
        "movimientos": [[str(c), str(i), d] for c, i, d in movs],
        "efectos": [[t, None if cat is None else str(cat)] for t, cat in efectos],
        "magnitudes": [str(m[0]) for m in mags],
        "vinculos": sorted([[k, str(v)] for k, v in vinculos]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5468")
    ap.add_argument("--api", default="http://127.0.0.1:5467")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    dsn, owner = os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"]
    _exigir_local(dsn)
    run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- preparacion
    exigir_base_recreada(dsn, owner)
    nomina_cta = crear_cuenta(dsn, owner, NOMINA_CTA, "CORRIENTE", "ACTIVO")
    tarjeta = crear_cuenta(dsn, owner, TARJETA, "CREDITO", "PASIVO")
    ahorro = crear_cuenta(dsn, owner, AHORRO, "AHORRO", "ACTIVO")
    merc = str(uuid.uuid4())
    api(a.api, "POST", "/v1/terceros", {"id": merc, "nombre": "Mercadona", "naturaleza": "EMPRESA"})
    rv = api(a.api, "GET", "/v1/terceros")["terceros"][0]["row_version"]
    api(a.api, "POST", f"/v1/terceros/{merc}/desactivar", {"row_version": rv})

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run}
    hechos: dict[str, str] = {}

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        consola: list[str] = []
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        intenciones: list[tuple[str, str]] = []
        page.on("request", lambda r: intenciones.append((urllib.parse.urlsplit(r.url).path, json.loads(r.post_data)["intencion_id"]))
                if r.method == "POST" and "/v1/intenciones/" in r.url and r.post_data else None)
        page.goto(a.web)
        t = page.get_by_test_id

        def shot(nombre: str) -> None:
            f = salida / f"J2J3_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def ajustes(seccion: str) -> None:
            t("tab-MAS").click()
            if t("mas-ajustes").count():
                t("mas-ajustes").click()
            t(f"ajustes-{seccion}").click()

        def a_ajustes(atras: str) -> None:
            t(atras).click()  # vuelve a la lista de Ajustes

        def registrar(ruta: str, clave: str) -> dict:
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(ruta), timeout=20000) as resp:
                t("registrar").click()
            cuerpo = resp.value.json()
            comprobar(resp.value.status == 200, f"{clave}: registro HTTP {resp.value.status} {cuerpo.get('codigo')}")
            hechos[clave] = cuerpo["hecho_id"]
            return cuerpo

        t("accion-registrar").wait_for(timeout=30000)
        # ------------------------------------------------------------ H (marca, antes de datos)
        marca = t("marca-inicio")
        comprobar(marca.get_attribute("aria-label") == "GaptoMobile", "la marca no es un elemento «GaptoMobile»")
        comprobar("2027" not in page.locator("body").inner_text(), "Inicio muestra «2027»")
        shot("H01_inicio_sin_accesos")
        oscuro("H01_inicio_sin_accesos")

        # ------------------------------------------------------------ O onboarding
        ajustes("categorias")
        t("onboarding-oferta").wait_for()
        shot("O01_oferta")
        t("onboarding-sugeridas").click()
        t("onboarding-resumen").wait_for()
        comprobar(t("onboarding-resumen").inner_text().startswith("23 grupos."), "O02 no anuncia 23 grupos")
        shot("O02_sugeridas")
        t("onboarding-crear").click()
        t("nueva-categoria").wait_for()
        page.wait_for_timeout(800)
        shot("O03_arbol_creado")
        arbol = api(a.api, "GET", "/v1/categorias")["categorias"]
        res["onboarding"] = {"categorias": len(arbol), "grupos": sum(1 for c in arbol if c["parent_id"] is None)}
        comprobar(res["onboarding"] == {"categorias": 93, "grupos": 23}, f"onboarding inesperado: {res['onboarding']}")
        por_nombre = {(c["nombre"], c["parent_id"]): c["id"] for c in arbol}
        raiz = lambda n: por_nombre[(n, None)]  # noqa: E731
        hija = lambda n, padre: por_nombre[(n, padre)]  # noqa: E731
        sup = raiz("Supermercados")
        ing_lab = raiz("Ingresos laborales")
        nomina = hija("Nómina", ing_lab)
        movilidad = raiz("Movilidad")
        combustible = hija("Combustible", movilidad)
        litros = str(uuid.uuid4())
        api(a.api, "POST", f"/v1/categorias/{combustible}/magnitudes", {"origen": "NUEVA", "obligatoria": True, "magnitud": {
            "magnitud_id": litros, "nombre": "Litros", "unidad_default": "l", "precision_decimales": 2}})
        t("categorias-atras").click() if t("categorias-atras").count() else page.go_back()

        # ------------------------------------------------------------ T terceros
        t("tab-INICIO").click()
        ajustes("terceros")
        t("pantalla-terceros").wait_for()
        t("ajter-nuevo").click()
        t("ajter-nombre").fill("Mercadona")
        t("ajter-nat-EMPRESA").click()
        t("ajter-guardar").click()
        t("ajter-duplicado").wait_for()
        shot("T01_duplicado_inactivo")
        t("ajter-reactivar-candidato").click()
        t("ajter-aviso-ok").wait_for()
        filas = _sql(dsn, owner, "gapto_runtime", "SELECT id, enabled FROM gapto.terceros WHERE nombre = 'Mercadona'")
        res["T_mercadona"] = [[str(i), e] for i, e in filas]
        comprobar(res["T_mercadona"] == [[merc, True]], f"Mercadona no reactivado (o duplicado): {res['T_mercadona']}")
        t("ajter-cancelar").click()
        t("ajter-nuevo").click()
        t("ajter-nombre").fill("Panadería Rosa")
        t("ajter-guardar").click()
        t("pantalla-terceros").wait_for()
        shot("T02_lista")
        oscuro("T02_lista")
        t("ajter-atras").click()

        # ------------------------------------------------------------ C contextos
        t("ajustes-contextos").click()
        t("pantalla-contextos").wait_for()
        t("ajctx-nuevo").click()
        t("ctx-nombre").fill("Finde Cartagena")
        t("ctx-tipo-VIAJE").click()
        t("ctx-desde").fill("10/10/2026")
        t("ctx-hasta").fill("12/10/2026")
        shot("C01_nuevo_contexto")
        t("ctx-guardar").click()
        t("pantalla-contextos").wait_for()
        shot("C02_lista")
        ctx_id = str(_sql(dsn, owner, "gapto_runtime", "SELECT id FROM gapto.entidades WHERE nombre = 'Finde Cartagena'")[0][0])
        t("ajctx-atras").click()

        # ------------------------------------------------------------ P plantillas
        t("ajustes-plantillas").click()
        t("pantalla-plantillas").wait_for()
        t("ajplt-cargando").wait_for(state="detached")  # «+» opera con los datos cargados
        t("ajplt-nueva").click()
        t("ajplt-nombre").fill("Súper semanal")
        t("ajplt-tipo-GASTO").click()
        t("ajplt-categoria").click()
        t(f"cat-{sup}").click()
        t(f"ajplt-cuenta-{tarjeta}").click()
        t("ajplt-presu-true").click()
        t("ajplt-inicio-true").click()
        t("ajplt-nombre-corto").fill("Súper")
        shot("P01_nueva_plantilla")
        t("ajplt-guardar").click()
        t("ajplt-detalle").wait_for()
        shot("P02_detalle")
        t("ajplt-detalle-atras").click()
        shot("P03_lista")
        oscuro("P03_lista")
        t("ajplt-atras").click()

        # ------------------------------------------------------------ F preferencias
        t("ajustes-preferencias").click()
        t("pantalla-preferencias").wait_for()
        t("ajpref-cargando").wait_for(state="detached")
        (t("ajpref-vacio-nueva") if t("ajpref-vacio-nueva").count() else t("ajpref-nueva")).click()
        t("ajpref-ambito-INGRESOS").click()
        t(f"ajpref-cuenta-{nomina_cta}").click()
        shot("F01_nueva_preferencia_ingresos")
        t("ajpref-guardar").click()
        t("ajpref-detalle").wait_for()
        t("ajpref-detalle-atras").click()
        shot("F02_lista")
        t("ajpref-atras").click()

        # ------------------------------------------------------------ G gasto desde el acceso
        t("tab-INICIO").click()
        page.reload()
        t("accion-registrar").wait_for(timeout=30000)
        acceso = page.locator("[data-testid^=acceso-]").filter(has_text="Súper")
        acceso.first.wait_for(timeout=15000)  # los accesos llegan con su propia lectura
        comprobar(acceso.count() == 1, "Inicio no muestra el acceso «Súper»")
        shot("H02_inicio_con_acceso")
        acceso.first.click()
        t("chip-plantilla").wait_for()
        t("origen-categoria").wait_for()
        comprobar(t("origen-categoria").inner_text() == "De tu plantilla Súper semanal.", "origen de la categoría distinto")
        t("campo-importe").fill("42,18")
        t("campo-tercero").click()
        t(f"tercero-{merc}").click()
        t("abrir-mas-detalles").click()
        t("campo-contexto").click()
        t(f"contexto-{ctx_id}").click()
        page.wait_for_timeout(600)
        shot("G01_gasto_plantilla")
        oscuro("G01_gasto_plantilla")
        registrar("/v1/intenciones/gasto-pagado", "G")
        t("registro-exito").wait_for()
        comprobar(t("exito-titulo").inner_text() == "Mercadona · Supermercados", f"título calculado: {t('exito-titulo').inner_text()}")
        shot("G02_exito")
        if t("pref-ambito-TERCERO").count():
            t("pref-ambito-TERCERO").click()
            t("pref-guardar").click()
            t("pref-guardada").wait_for()
            shot("G03_preferencia_tercero")
        t("volver-inicio").click()

        # ------------------------------------------------------------ N «No lo sé»
        t("accion-registrar").click()
        t("tipo-GASTO").click()
        t("campo-importe").fill("60")
        t("campo-categoria").click()
        t(f"cat-{movilidad}").click()
        t(f"cat-{combustible}").click()
        t("presupuestable-true").click()
        t(f"cuenta-{tarjeta}").click()
        t(f"no-lo-se-{litros}").click()
        shot("N01_no_lo_se")
        registrar("/v1/intenciones/gasto-pagado", "N")
        t("registro-exito").wait_for()
        t("volver-inicio").click()

        # ------------------------------------------------------------ I ingreso
        t("accion-registrar").click()
        t("tipo-INGRESO").click()
        t("campo-importe").fill("1500")
        t("campo-tercero").click()
        t("tercero-filtro").fill("ACME Servicios")
        t("tercero-crear").click()
        page.wait_for_timeout(600)
        t("campo-categoria").click()
        t(f"cat-{ing_lab}").click()
        t(f"cat-{nomina}").click()
        t("presupuestable-true").click()
        page.wait_for_timeout(800)
        t("abrir-mas-detalles").click()
        t("campo-nota").fill("Nómina octubre")
        shot("I01_ingreso")
        oscuro("I01_ingreso")
        res["I_origen_cuenta"] = t("origen-cuenta").inner_text() if t("origen-cuenta").count() else None
        registrar("/v1/intenciones/ingreso-cobrado", "I")
        t("registro-exito").wait_for()
        shot("I02_exito")
        t("guardar-como-plantilla").click()
        t("plantilla-nombre").fill("Nómina")
        t("plantilla-guardar").click()
        t("plantilla-aviso-ok").wait_for()
        shot("I03_guardar_como_plantilla")
        t("plantilla-cerrar").click()
        t("volver-inicio").click()

        # ------------------------------------------------------------ X entre cuentas
        t("accion-registrar").click()
        t("tipo-TRANSFERENCIA").click()
        t(f"desde-{nomina_cta}").click()
        t(f"a-{nomina_cta}").click()
        t("a-misma").wait_for()
        shot("X01_misma_cuenta")
        t(f"a-{ahorro}").click()
        t("campo-importe").fill("200")
        registrar("/v1/intenciones/transferencia", "X")
        t("transferencia-exito").wait_for()
        shot("X02_exito")
        t("volver-inicio").click()

        # ------------------------------------------------------------ K cambio de tipo
        t("accion-registrar").click()
        t("tipo-GASTO").click()
        t("campo-importe").fill("12,50")
        t("campo-categoria").click()
        t(f"cat-{sup}").click()
        t(f"cuenta-{tarjeta}").click()
        t("cambiar-tipo").click()
        t("tipo-INGRESO").click()
        t("avisos-registro").wait_for()
        res["K_aviso"] = t("avisos-registro").inner_text()
        shot("K01_cambio_de_tipo")
        t("cancelar").click()
        if t("descartar").count():
            t("descartar").click()
        nav.close()

    # ---------------------------------------------------------------- BD por UUID
    ids_post = {ruta: iid for ruta, iid in intenciones}
    res["intenciones"] = intenciones
    res["hechos"] = {k: hecho(dsn, owner, v) for k, v in hechos.items()}
    g, n, i, x = (res["hechos"][k] for k in "GNIX")
    comprobar(g["concepto"] is None and all(m[2] is None for m in g["movimientos"]), f"G: concepto/descripcion no NULL: {g}")
    comprobar(["TERCERO", merc] in g["vinculos"] and ["CONTEXTO", ctx_id] in g["vinculos"], f"G: vínculos: {g['vinculos']}")
    comprobar(g["efectos"] == [["GASTO", sup]], f"G: categoría: {g['efectos']}")
    comprobar(n["magnitudes"] == [] and n["efectos"] == [["GASTO", combustible]], f"N: «No lo sé»: {n}")
    comprobar(i["tipo"] == "INGRESO" and i["concepto"] == "Nómina octubre" and i["efectos"][0][1] == nomina, f"I: {i}")
    comprobar(x["tipo"] == "TRANSFERENCIA" and len(x["movimientos"]) == 2, f"X: {x}")
    res["plantillas"] = [[str(a_), b_] for a_, b_ in _sql(dsn, owner, "gapto_runtime", "SELECT nombre, enabled FROM gapto.plantillas_registro ORDER BY nombre")]
    res["preferencias"] = [[str(a_) for a_ in f] for f in _sql(dsn, owner, "gapto_runtime",
        "SELECT t.codigo, p.categoria_id, p.tercero_id, p.cuenta_default_id FROM gapto.preferencias_registro p "
        "JOIN gapto.tipos_hecho t ON t.id = p.tipo_hecho_id ORDER BY t.codigo, p.created_at")]
    res["errores_consola"] = consola
    res["capturas"] = capturas
    res["ids_post"] = ids_post
    (salida / f"J2J3_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
