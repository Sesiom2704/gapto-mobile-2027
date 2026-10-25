# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_vs01.py
# Ruta: scripts/dev/e2e_vs01.py
# Descripcion: E2E del vertical slice VS-01 sobre el cliente REAL exportado a
#   web (react-native-web) + adaptador FastAPI + PostgreSQL LOCAL de
#   desarrollo. Recorre Home -> accion rapida Gasto -> formulario -> OP-22 ->
#   persistencia -> lectura -> Home, contrasta la UI con la BD y captura
#   pantallas en viewport 393x852 (@3x).
#
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***
#
#   Requiere (ya levantados): cliente web en --web, API en --api y
#   GAPTO_DATABASE_URL (solo lectura de verificacion) + GAPTO_DEV_OWNER_USER_ID.
#   Escribe las capturas y un manifest JSON en --salida (fuera del repo).
#   v0.2.0 (F05-D003): espera y registra la linea de financiacion visible,
#   comprueba que el bloque «Este mes» no muestra importes (la cifra real va
#   en la tarjeta parcial separada) y anade al manifest la financiacion y la
#   fecha comun gasto/pago persistidas.
#   v0.3.0 (F05 — VS-01 · Alineacion visual, A2/SPEC-08): comprueba que
#   «Registrar gasto» esta DESACTIVADO (aria-disabled) al abrir el formulario y
#   la indicacion visible de lo que falta, que pulsarlo no crea ningun hecho y
#   que se habilita al completar las decisiones bloqueantes; captura Home y
#   formulario tambien en esquema oscuro (emulacion prefers-color-scheme).
#   v0.4.0 (F05-01 S6-WIRE+UI (este mandato)): la categoria es obligatoria en el
#   wire (S6-WIRE). El flujo base de VS-01 elige «Sin categoria» en el selector
#   como DECISION EXPLICITA (una decision y dos toques mas), comprueba que la
#   categoria pendiente figura en «faltan» al abrir y registra en el manifest
#   la categoria elegida y el categoria_id persistido (NULL). Los escenarios con
#   categoria y magnitudes viven en e2e_regcat.py.
#   Con --dist <export web> arranca el servidor estatico versionado
#   scripts/dev/servir_web_e2e.py (loopback, HTTP/1.1) y lo detiene al terminar.
#   v0.5.0 (F05-03/F05-04 J3 §2.1/§2.2): «Registrar» + hoja de tipos
#   (accion-registrar, tipo-GASTO); taps de Inicio al formulario: 2 (antes 1).
#   v0.6.0 (F05-03/F05-04 J3 §2.7; CORTE DE CONCEPTO): la nota opcional
#   (`--concepto`, ahora «Nota») se escribe en «Más detalles» (campo-nota); el
#   hecho se localiza por su UUID (intencion_id del POST; hecho_id =
#   intencion_id), nunca por concepto. «faltan» al abrir ya no nombra concepto.
#   v0.7.0 (F05-05 K3 §2.11; F05 §49.4 A9): «Este mes» tiene ya su read model
#   (Resultado del mes), que sustituye en ESE bloque el «sin cifras» de
#   F05-D003 §16.6. Se conserva la propiedad de VS-01: la cifra PARCIAL de
#   gasto-mes va en su tarjeta y nunca aparece en «Este mes».
#   v0.7.1 (F05-07/GATE adenda 2, MANT-PRE-GATE C/e2e; DEF-E2E-VS01-LAYOUT):
#   el detector de desbordamiento horizontal (DESBORDES_JS) excluye los textos
#   recortados con elipsis (`text-overflow: ellipsis`, lo que react-native-web
#   genera para numberOfLines={1}): ese recorte es deliberado y no desborda (la
#   pagina no tiene scroll horizontal). Daba un falso positivo con «Hola,
#   <nombre>» de la cabecera de Inicio (HomeScreen.tsx, F05-05 K3 §2.7), que
#   sigue en el DOM bajo el formulario superpuesto y, con el nombre sintetico
#   «Usuario sintetico VS-01», se recorta («Hola, Usuario si…»). Ademas exige
#   que el documento no tenga scroll horizontal y registra en el manifest los
#   textos truncados (truncados_elipsis_formulario).
# Version: 0.8.0 (F05-D051 paso 3; F05 §65.3, AJ-F0507G2-05/12): detector de
#   layout ACOTADO (evaluar_layout / LAYOUT_JS), que sustituye a DESBORDES_JS y
#   TRUNCADOS_JS: (1) la excepcion de elipsis deja de ser generica: solo los
#   data-testid de la lista blanca EXPLICITA ELIPSIS_AUTORIZADA (el saludo
#   «hola») pueden recortarse; cualquier otro texto truncado (elipsis horizontal
#   o line-clamp vertical) hace FALLAR; (2) inventario de truncados por momento
#   (autorizado o no, critico o no) exportado en VS01_<run>_inventario_layout.json
#   (se reescribe tras cada medida, tambien si la ejecucion falla) y en el
#   manifest; (3) falla ante scroll horizontal del documento, desbordamiento de
#   un contenedor, texto o control visible que cruza el borde del viewport y
#   texto o control recortado horizontalmente por un ancestro (perdida de
#   informacion necesaria para actuar: importes, botones, etiquetas de accion).
#   Se mide en los siete momentos del recorrido (Inicio, formulario vacio y
#   completo, exito, Inicio refrescado, Inicio y formulario en oscuro), no solo
#   en el formulario; los fallos de layout se reunen y fallan al final, con el
#   manifest ya escrito.
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

#: F05 §65.3 (AJ-F0507G2-05): lista blanca EXPLICITA de los elementos (data-testid exacto) cuyo recorte
#: con elipsis esta autorizado. Solo el saludo «Hola, <nombre>» de la cabecera de Inicio (HomeScreen,
#: numberOfLines={1}): con un nombre largo se recorta a proposito. Cualquier otro truncado hace fallar.
ELIPSIS_AUTORIZADA = ("hola",)

#: Medida de layout (un objeto por momento). Para cada elemento visible del body:
#:   truncados      texto recortado con elipsis (horizontal) o line-clamp (vertical), con su contexto;
#:   desbordes      contenedor con contenido mas ancho que su caja y overflow-x no visible, o desplazado;
#:   fuera_viewport texto o control visible que cruza el borde izquierdo o derecho del viewport;
#:   recortes       texto o control recortado horizontalmente por un ancestro con overflow-x no visible.
#: Lo que queda entero fuera del viewport o entero oculto por un ancestro no se ve: no cuenta.
#: «critico»: dentro de un control (boton, enlace, campo...) o bajo un data-testid de importe.
LAYOUT_JS = r"""(autorizados) => {
  const de = document.documentElement, vw = de.clientWidth;
  const CONTROL = '[role=button],[role=link],[role=tab],[role=switch],[role=checkbox],[role=radio],[role=menuitem],button,a[href],input,select,textarea';
  const CRIT = /(valor|importe|resultado|saldo|total|^mes-)/;
  const ident = (e) => { const t = e.getAttribute('data-testid'); if (t) return t;
    const a = e.parentElement && e.parentElement.closest('[data-testid]');
    return (a ? a.getAttribute('data-testid') + '>' : '') + e.tagName; };
  const texto = (e) => ((e.innerText !== undefined ? e.innerText : '') || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 80);
  const critico = (e) => { if (e.closest(CONTROL)) return true; const a = e.closest('[data-testid]');
    return !!a && CRIT.test(a.getAttribute('data-testid')); };
  const conTexto = (e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || e.matches(CONTROL);
  const r2 = (x) => Math.round(x * 10) / 10;
  const res = { viewport: vw, documento: { ancho_contenido: de.scrollWidth, ancho_visible: de.clientWidth },
    truncados: [], desbordes: [], fuera_viewport: [], recortes: [] };
  for (const e of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const elipsis = cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1;
    const clamp = !!cs.webkitLineClamp && cs.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1;
    if (elipsis || clamp) {
      const testid = e.getAttribute('data-testid');
      res.truncados.push({ id: ident(e), texto: texto(e), eje: elipsis ? 'horizontal' : 'vertical',
        contenido: elipsis ? e.scrollWidth : e.scrollHeight, caja: elipsis ? e.clientWidth : e.clientHeight,
        critico: critico(e), autorizado: !!testid && autorizados.includes(testid) });
      continue;
    }
    if (e.scrollLeft > 0 || (e.scrollWidth > e.clientWidth + 1 && cs.overflowX !== 'visible'))
      res.desbordes.push({ id: ident(e), texto: texto(e), contenido: e.scrollWidth, caja: e.clientWidth, critico: critico(e) });
    if (!conTexto(e)) continue;
    let izq = r.left, der = r.right;
    for (let a = e.parentElement; a && a !== de; a = a.parentElement) {
      if (getComputedStyle(a).overflowX === 'visible') continue;
      const ra = a.getBoundingClientRect();
      izq = Math.max(izq, ra.left); der = Math.min(der, ra.right);
    }
    if (der - izq <= 0.5 || der <= 0 || izq >= vw) continue;
    const item = { id: ident(e), texto: texto(e), izquierda: r2(r.left), derecha: r2(r.right),
      visible_izquierda: r2(izq), visible_derecha: r2(der), critico: critico(e) };
    if (izq < -1 || der > vw + 1) res.fuera_viewport.push(item);
    else if (izq > r.left + 1 || der < r.right - 1) res.recortes.push(item);
  }
  return res;
}"""


def fallos_layout(medida: dict) -> list[str]:
    """Fallos de una medida de LAYOUT_JS (F05 §65.3). Los truncados de la lista blanca no fallan."""
    fallos = []
    doc = medida["documento"]
    if doc["ancho_contenido"] > doc["ancho_visible"] + 1:
        fallos.append(f"DOCUMENTO con scroll horizontal ({doc['ancho_contenido']} > {doc['ancho_visible']})")
    fallos += [f"truncado no autorizado ({t['eje']}{', critico' if t['critico'] else ''}): {t['id']} «{t['texto']}»"
               for t in medida["truncados"] if not t["autorizado"]]
    fallos += [f"desbordamiento horizontal: {d['id']} ({d['contenido']} > {d['caja']})" for d in medida["desbordes"]]
    fallos += [f"fuera del viewport{' (critico)' if x['critico'] else ''}: {x['id']} «{x['texto']}» "
               f"[{x['izquierda']}, {x['derecha']}]" for x in medida["fuera_viewport"]]
    fallos += [f"recortado por un ancestro{' (critico)' if x['critico'] else ''}: {x['id']} «{x['texto']}» "
               f"[{x['izquierda']}, {x['derecha']}] visible [{x['visible_izquierda']}, {x['visible_derecha']}]"
               for x in medida["recortes"]]
    return fallos


def evaluar_layout(page, momento: str, inventario: list, fichero: pathlib.Path | None = None) -> list[str]:
    """Mide el layout en `momento`, lo anade al inventario (y lo reescribe en `fichero` si se da) y
    devuelve sus fallos. No lanza: el llamador decide cuando fallar."""
    medida = page.evaluate(LAYOUT_JS, list(ELIPSIS_AUTORIZADA))
    medida = {"momento": momento, **medida}
    medida["fallos"] = fallos_layout(medida)
    inventario.append(medida)
    if fichero is not None:
        fichero.write_text(json.dumps({"etiqueta": ETIQUETA, "elipsis_autorizada": list(ELIPSIS_AUTORIZADA),
                                       "medidas": inventario}, ensure_ascii=False, indent=2), encoding="utf-8")
    return medida["fallos"]


ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


#: Servidor estatico versionado (solo loopback), localizado junto a este script.
SERVIDOR_WEB = pathlib.Path(__file__).resolve().parent / "servir_web_e2e.py"


@contextlib.contextmanager
def servidor_web(dist: str | None, web: str):
    """Con --dist, arranca scripts/dev/servir_web_e2e.py sobre el export web y lo
    detiene al terminar; sin --dist se usa un cliente web ya levantado en --web."""
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


def contar_hechos(dsn: str, owner: str, ids: list[str]) -> int:
    """Hechos con esos UUID (intenciones enviadas), nunca por concepto (§2.7)."""
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT count(*) FROM gapto.hechos_financieros WHERE id = ANY(%s::uuid[])", (list(ids),))
        return cur.fetchone()[0]


def leer_bd(dsn: str, owner: str, hecho_id: str) -> dict:
    with psycopg.connect(dsn) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_runtime")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        cur.execute("SELECT id, importe_total, presupuestable, estado_localizacion, fecha_hecho, concepto FROM gapto.hechos_financieros WHERE id=%s", (hecho_id,))
        hechos = cur.fetchall()
        hid = hechos[0][0]
        def uno(sql):
            cur.execute(sql, (hid,)); return cur.fetchall()
        return {
            "hechos": len(hechos),
            "hecho": [str(x) for x in hechos[0]],
            "efectos": [list(map(str, r)) for r in uno("SELECT tipo_efecto, importe_delta, estado_atribucion, categoria_id FROM gapto.hecho_efectos WHERE hecho_id=%s")],
            "atribuciones": [list(map(str, r)) for r in uno("SELECT a.importe_atribuido, a.criterio_atribucion FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id=a.efecto_id WHERE e.hecho_id=%s")],
            "movimientos": [list(map(str, r)) for r in uno("SELECT m.importe, c.importe_asignado, m.fecha_movimiento FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id=m.id WHERE c.hecho_id=%s")],
            "aportaciones": [list(map(str, r)) for r in uno("SELECT importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s")],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:8081")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--concepto", default="Café")
    ap.add_argument("--importe", default="3,50")
    ap.add_argument("--dist", help="carpeta del export web: arranca scripts/dev/servir_web_e2e.py")
    a = ap.parse_args()
    with servidor_web(a.dist, a.web):
        salida = pathlib.Path(a.salida); salida.mkdir(parents=True, exist_ok=True)
        run = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
        metricas: dict = {"taps": 0, "campos_escritos": 0, "decisiones_explicitas": 0}
        capturas = []
        # F05 §65.3: inventario de layout por momento (se reescribe tras cada medida) y fallos reunidos.
        inventario: list = []
        fichero_inventario = salida / f"VS01_{run}_inventario_layout.json"
        fallos_de_layout: list[str] = []

        def shot(page, nombre):
            f = salida / f"VS01_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.screenshot(path=str(f)); capturas.append(f.name)

        def layout(page, momento):
            fallos_de_layout.extend(f"[{momento}] {x}" for x in evaluar_layout(page, momento, inventario, fichero_inventario))

        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
            page.goto(a.web)
            consola = []
            page.on("console", lambda m: consola.append(m.type) if m.type == "error" else None)
            # §2.7: UUID de cada intencion enviada (el hecho se localiza por el, nunca por concepto).
            intenciones: list[str] = []
            page.on("request", lambda r: intenciones.append(json.loads(r.post_data)["intencion_id"])
                    if r.method == "POST" and r.url.endswith("/v1/intenciones/gasto-pagado") and r.post_data else None)
            g = page.get_by_test_id("gastos-valor")
            g.wait_for(timeout=30000)
            antes = g.inner_text()
            page.get_by_test_id("hola").wait_for(timeout=15000)
            page.wait_for_timeout(500)
            shot(page, "01_home_antes")
            layout(page, "01_home_antes")

            t0 = time.monotonic()
            # F05-04 §2.2: «Registrar» abre la hoja de tipos (sin preselección) y luego «Gasto».
            page.get_by_test_id("accion-registrar").click(); metricas["taps"] += 1
            page.get_by_test_id("tipo-GASTO").click(); metricas["taps"] += 1
            metricas["taps_home_a_formulario"] = 2
            page.get_by_test_id("origen-cuenta").wait_for()
            page.get_by_test_id("financiacion").wait_for()
            financiacion_visible = page.get_by_test_id("financiacion-texto").inner_text()
            page.wait_for_timeout(500)
            layout(page, "02a_formulario_vacio")
            # SPEC-08: desactivado al abrir, con indicacion visible; pulsarlo no escribe.
            boton = page.get_by_test_id("registrar")
            spec08 = {"disabled_al_abrir": boton.get_attribute("aria-disabled"),
                      "faltan_al_abrir": page.get_by_test_id("faltan").inner_text()}
            if spec08["disabled_al_abrir"] != "true":
                raise SystemExit("FALLO SPEC-08: «Registrar gasto» no esta desactivado con decisiones pendientes")
            boton.click(force=True)
            page.wait_for_timeout(800)
            spec08["hechos_tras_pulsar_desactivado"] = len(intenciones) + contar_hechos(os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"], intenciones)
            if spec08["hechos_tras_pulsar_desactivado"] != 0 or page.get_by_test_id("registro-exito").count():
                raise SystemExit("FALLO SPEC-08: pulsar el boton desactivado ha producido un registro")
            shot(page, "02a_formulario_vacio")
            page.get_by_test_id("campo-importe").fill(a.importe); metricas["campos_escritos"] += 1
            page.get_by_test_id("abrir-mas-detalles").click(); metricas["taps"] += 1  # §2.7: nota opcional
            page.get_by_test_id("campo-nota").click(); metricas["taps"] += 1
            page.get_by_test_id("campo-nota").fill(a.concepto); metricas["campos_escritos"] += 1
            page.get_by_test_id("presupuestable-true").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            page.get_by_test_id("solo-mio").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            if "categoría" not in spec08["faltan_al_abrir"]:
                raise SystemExit("FALLO S6-WIRE: «faltan» no nombra la categoria pendiente al abrir")
            page.get_by_test_id("campo-categoria").click(); metricas["taps"] += 1
            page.get_by_test_id("selector-sin-categoria").click(); metricas["taps"] += 1; metricas["decisiones_explicitas"] += 1
            page.wait_for_timeout(300)
            spec08["disabled_completo"] = boton.get_attribute("aria-disabled")
            spec08["faltan_completo"] = page.get_by_test_id("faltan").count()
            if spec08["disabled_completo"] == "true" or spec08["faltan_completo"]:
                raise SystemExit("FALLO SPEC-08: el boton sigue desactivado con el formulario completo")
            shot(page, "02_formulario")
            layout(page, "02_formulario_completo")
            page.get_by_test_id("registrar").click(); metricas["taps"] += 1
            page.get_by_test_id("registro-exito").wait_for(timeout=15000)
            metricas["taps_hasta_confirmacion"] = metricas["taps"]
            metricas["segundos_automatizados_hasta_confirmacion"] = round(time.monotonic() - t0, 2)
            shot(page, "03_exito")
            layout(page, "03_exito")
            page.get_by_test_id("volver-inicio").click(); metricas["taps"] += 1
            page.wait_for_function("(a) => { const e=document.querySelector('[data-testid=gastos-valor]'); return e && e.innerText !== a; }", arg=antes, timeout=15000)
            despues = page.get_by_test_id("gastos-valor").inner_text()
            # F05-05 A9: «Este mes» muestra el Resultado del mes; nunca la cifra PARCIAL de gasto-mes.
            # (la cifra puede coincidir con «Gastos» del Resultado; lo que se exige es que no viva en ese bloque)
            parcial_en_mes = page.locator("[data-testid=bloque-mes] [data-testid=gastos-valor]").count()
            if parcial_en_mes or not page.get_by_test_id("mes-gastos").count():
                raise SystemExit("FALLO F05-D003 §16.6: el bloque «Este mes» muestra la cifra parcial de gasto-mes")
            page.wait_for_timeout(300)
            shot(page, "04_home_refrescada")
            layout(page, "04_home_refrescada")
            # Esquema oscuro (mismos tokens DS-01 Dark): solo capturas de revision visual.
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(500)
            shot(page, "05_home_dark")
            layout(page, "05_home_dark")
            page.get_by_test_id("accion-registrar").click()
            page.get_by_test_id("tipo-GASTO").click()
            page.get_by_test_id("financiacion").wait_for()
            page.wait_for_timeout(500)
            shot(page, "06_formulario_dark")
            layout(page, "06_formulario_dark")
            nav.close()

        if len(intenciones) != 1:
            raise SystemExit(f"FALLO: se esperaba exactamente un POST de registro y hubo {len(intenciones)}")
        bd = leer_bd(os.environ["GAPTO_DATABASE_URL"], os.environ["GAPTO_DEV_OWNER_USER_ID"], intenciones[0])
        manifest = {"etiqueta": ETIQUETA, "run_id": run, "categoria_elegida": "SIN_CATEGORIA (decision explicita)",
                    "gastos_home_antes": antes, "gastos_home_despues": despues,
                    "financiacion_visible": financiacion_visible, "parcial_en_bloque_mes": parcial_en_mes, "spec08": spec08,
                    "bd": bd, "metricas": metricas, "errores_consola": len(consola), "capturas": capturas,
                    "layout": {"elipsis_autorizada": list(ELIPSIS_AUTORIZADA), "fallos": fallos_de_layout,
                               "truncados": [{"momento": m["momento"], **x} for m in inventario for x in m["truncados"]],
                               "inventario": fichero_inventario.name}}
        (salida / f"VS01_{run}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        if fallos_de_layout:
            raise SystemExit("FALLO LAYOUT (F05 §65.3): " + " | ".join(fallos_de_layout))


if __name__ == "__main__":
    main()
