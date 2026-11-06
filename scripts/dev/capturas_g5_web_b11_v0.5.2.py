# HERRAMIENTA CONGELADA — variante B11 (oscuro + Dynamic Type emulado) de capturas_g5_web.py — F06-M1
# Version congelada: 0.5.2-B11 (2026-11-06, MANT-TOKENS-RUTAS). Sustituye a 0.5.1-B11
#   (SHA-256 fa5df9eb25374b0e8882d9d0bcc99cdd53a4a02c8fa835a5661846f49d7f87f9, publicada en d12ea3b y
#   recuperable con `git show d12ea3b:scripts/dev/capturas_g5_web_b11_v0.5.1.py`), que es la version con la que
#   se tomaron las 182 capturas de Tokens; su evidencia no cambia.
# Unico cambio sobre 0.5.1: sin rutas absolutas de la maquina. Las rutas llegan por argumento o por variable de
#   entorno, con valor por defecto relativo al repositorio (ver main y el LEEME). Recetas, detector, variantes,
#   estados, nombres de fichero y JSON de salida no cambian.
# Congelada = no se edita: cualquier cambio exige nueva version con su SHA. Depende de scripts/dev/e2e_vs01.py
#   (LAYOUT_JS, fallos_layout, ELIPSIS_AUTORIZADA, servidor_web) y de Playwright. No sustituye a la herramienta de G5.
# PRUEBA WEB — NO EVIDENCIA iOS; el DT emulado no acredita Dynamic Type nativo.
# ====» en adelante; solo cambia este bloque de cabecera.
# Congelada = no se edita: cualquier cambio exige nueva version con su SHA. Depende de wt_v25_mpg\scripts\dev\e2e_vs01.py
#   (LAYOUT_JS, fallos_layout, ELIPSIS_AUTORIZADA, servidor_web) y de Playwright. No sustituye a la herramienta de G5.
# PRUEBA WEB — NO EVIDENCIA iOS; el DT emulado no acredita Dynamic Type nativo.
# ============================================================
# GAPTO MOBILE 2027
# Fichero: capturas_g5_web_b11_v0.5.2.py
# Ruta: scripts/dev/capturas_g5_web_b11_v0.5.2.py
# Descripcion: PRUEBA WEB de las 51 pantallas G5 (PANTALLAS_51.json) en tres
#   variantes: CLARO (color_scheme='light'), OSCURO (color_scheme='dark') y
#   Dynamic Type GRANDE EMULADO (x1.35 de font-size y line-height por script
#   inyectado; claro). La emulacion NO acredita Dynamic Type nativo.
#   Detector por captura: LAYOUT_JS / fallos_layout / ELIPSIS_AUTORIZADA de
#   scripts/dev/e2e_vs01.py (reutilizados SIN copiar) + objetivos
#   tactiles < 44x44 px CSS, texto con elipsis o recortado y SOLAPAMIENTOS
#   (interseccion de cajas de texto/controles visibles sin relacion de
#   ancestro). Cada captura acredita el contenido alcanzado (testID esperado
#   visible). Captura ausente, ruta no alcanzada o fallo del detector =
#   PENDIENTE.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***
#   Requiere (ya levantados): API en --api (owner sintetico g2-bu) y el export
#   web (lo sirve este script en --web con servidor_web de e2e_vs01). El token
#   se lee de --token-fichero y NUNCA se imprime ni se escribe.
# Version: 0.1.0 (F05-07 G15 pre_final, tarea nocturna 2026-10-30/31)
# Version: 0.2.0 (MANDATO_NOCHE_3010 y dictamen 16, AJ-F0507G16-03: variante
#   claro, solapamientos, acreditacion por testID, nombres G5-xx_<variante>_<estado>,
#   PENDIENTE en lugar de NO CAPTURADA)
# Version: 0.3.0 (humo previo a la ejecucion, inventario congelado v2): solapamientos
#   sobre la caja RECORTADA por los ancestros con overflow no visible (lo que pasa
#   bajo una cabecera fija al desplazar no es solape); g2-bu sin jerarquia ni
#   magnitudes: G5-08 solo usa un padre real, G5-38..40 crean por la UI dos
#   magnitudes sinteticas si no hay ninguna; datos redescubiertos tras escribir
#   (G5-28); criterio de gasto con reparto ampliado)
# Version: 0.4.0 (humo 2 con v0.3.0: el parche 0.3 dejo la inicializacion de
#   Ctx dentro de redescubrir (AttributeError 'n'); G5-26 elige un gasto
#   anulable por GET /v1/hechos/{id}/anulacion y captura tambien el bloqueo;
#   G5-06 siembra por la API publica una plantilla y su acceso si g2-bu no tiene)
# Version: 0.5.0 (humo 3 con v0.4.0): GET /v1/actividad trata `hasta` como
#   exclusivo (los hechos de hoy no salian): hasta = hoy + 1; elegibilidad real
#   por GET /v1/hechos/{id}/edicion (corregir / anular_duplicado) y
#   /v1/hechos/{id}/devoluciones (disponible); G5-30 «Más» solo si existe (una
#   prevision abierta no lo tiene); G5-31 acredita el fondo con el primer testID
#   visible; G5-40 acepta cualquiera de las dos hojas de deshabilitar)
# Version: 0.5.1-B11 (F06-M1 Tokens, 2026-11-04): variante oscuro_dt (ver LEEME)
# Version: 0.5.2-B11 (F06 MANT-TOKENS-RUTAS, 2026-11-06): sin rutas absolutas;
#   --dist, --token-fichero, --pantallas y --salida por argumento o variable
#   GAPTO_CAPTURAS_*; e2e_vs01 desde este mismo directorio o GAPTO_CAPTURAS_E2E_DIR
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True  # el worktree es SOLO LECTURA: sin __pycache__
DIR_SCRIPT = pathlib.Path(__file__).resolve().parent
REPO = DIR_SCRIPT.parents[1]
sys.path.insert(0, os.environ.get("GAPTO_CAPTURAS_E2E_DIR") or str(DIR_SCRIPT))
from e2e_vs01 import ELIPSIS_AUTORIZADA, LAYOUT_JS, fallos_layout, servidor_web  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ETIQUETA = "PRUEBA WEB (EVIDENCIA WEB/VIEWPORT) — NO EVIDENCIA iOS; DT EMULADO, NO ACREDITA DYNAMIC TYPE NATIVO"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
FACTOR_DT = 1.35

# ---------------------------------------------------------------- Dynamic Type emulado
DT_JS = r"""(() => {
  const F = %s;
  const conTexto = (el) => el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ||
    [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  function escalar(el) {
    if (!(el instanceof HTMLElement) || !conTexto(el)) return;
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize);
    if (!fs) return;
    const obj = parseFloat(el.dataset.dtObj || '0');
    if (obj && Math.abs(fs - obj) < 0.25) return;            // ya escalado
    const pa = el.parentElement;                               // hereda del padre ya escalado
    if (pa && pa.dataset.dtObj && Math.abs(fs - parseFloat(pa.dataset.dtObj)) < 0.25) return;
    const lh = cs.lineHeight;
    el.style.setProperty('font-size', (fs * F) + 'px', 'important');
    if (lh && lh !== 'normal') { const l = parseFloat(lh); if (l) el.style.setProperty('line-height', (l * F) + 'px', 'important'); }
    el.dataset.dtObj = String(fs * F);
  }
  let pendiente = false;
  function todo() { pendiente = false; if (!document.body) return 0; let n = 0;
    for (const el of document.body.querySelectorAll('*')) { escalar(el); if (el.dataset.dtObj) n++; } return n; }
  function programar() { if (pendiente) return; pendiente = true; setTimeout(todo, 60); }
  window.__dtAplicar = todo;
  window.__dtFactor = F;
  const arrancar = () => {
    new MutationObserver(programar).observe(document.documentElement,
      { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['style', 'class'] });
    todo();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrancar); else arrancar();
  setInterval(todo, 500);
})();""" % FACTOR_DT

# ---------------------------------------------------------------- detector adicional
DETECTOR_JS = r"""(autorizados) => {
  const de = document.documentElement, vw = de.clientWidth, vh = de.clientHeight;
  const SEL = '[role=button],[role=link],[role=switch],[role=tab],[role=checkbox],[role=radio],[role=menuitem],button,a[href],input,select,textarea,[onclick]';
  const ident = (e) => { const t = e.getAttribute('data-testid'); if (t) return t;
    const a = e.parentElement && e.parentElement.closest('[data-testid]');
    return (a ? a.getAttribute('data-testid') + '>' : '') + e.tagName; };
  const texto = (e) => ((e.innerText !== undefined ? e.innerText : '') || e.value || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const r1 = (x) => Math.round(x * 10) / 10;
  const visible = (e, r) => {
    const env = r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw;
    if (!env) return { en_viewport: false, oculto: null };
    const x = Math.min(Math.max(r.left + r.width / 2, 0), vw - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), vh - 1);
    const h = document.elementFromPoint(x, y);
    const oculto = !(h && (h === e || e.contains(h) || h.contains(e)));
    return { en_viewport: true, oculto };
  };
  const tactiles = [], recortes = [];
  for (const e of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const pa = e.parentElement;
    const interactivo = e.matches(SEL) || (cs.cursor === 'pointer' && !(pa && getComputedStyle(pa).cursor === 'pointer'));
    if (interactivo && (r.width < 44 || r.height < 44) && !(e.tagName === 'INPUT' && e.type === 'hidden')) {
      const anc = pa && pa.closest(SEL);
      const ra = anc ? anc.getBoundingClientRect() : null;
      tactiles.push({ id: ident(e), texto: texto(e), rol: e.getAttribute('role') || e.tagName.toLowerCase(),
        ancho: r1(r.width), alto: r1(r.height), ...visible(e, r),
        deshabilitado: e.getAttribute('aria-disabled') === 'true' || e.disabled === true,
        dentro_de_control: anc ? { id: ident(anc), ancho: r1(ra.width), alto: r1(ra.height) } : null });
    }
    const directo = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (directo) {
      const elipsis = cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1;
      const clamp = !!cs.webkitLineClamp && cs.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1;
      const cortaX = cs.overflowX !== 'visible' && e.scrollWidth > e.clientWidth + 1;
      const cortaY = cs.overflowY !== 'visible' && e.scrollHeight > e.clientHeight + 1;
      if (elipsis || clamp || cortaX || cortaY) {
        const tid = e.getAttribute('data-testid');
        const horiz = elipsis || (!clamp && cortaX);
        recortes.push({ id: ident(e), texto: texto(e),
          tipo: elipsis ? 'elipsis' : clamp ? 'line-clamp' : cortaX ? 'recorte-horizontal' : 'recorte-vertical',
          contenido: horiz ? e.scrollWidth : e.scrollHeight, caja: horiz ? e.clientWidth : e.clientHeight,
          autorizado: !!tid && autorizados.includes(tid), ...visible(e, r) });
      }
    }
  }
  // solapamientos: cajas de texto/controles visibles (en viewport, no tapados) sin relacion de ancestro
  const cajas = [];
  for (const e of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    const esCtl = e.matches(SEL);
    const esTxt = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!esCtl && !esTxt) continue;
    const r0 = e.getBoundingClientRect();
    if (r0.width < 1 || r0.height < 1) continue;
    const v = visible(e, r0);
    if (!v.en_viewport || v.oculto) continue;
    let l = r0.left, t = r0.top, d = r0.right, b = r0.bottom;
    for (let a = e.parentElement; a && a !== de; a = a.parentElement) {
      const ca = getComputedStyle(a);
      if (ca.overflowX === 'visible' && ca.overflowY === 'visible') continue;
      const ra = a.getBoundingClientRect();
      if (ca.overflowX !== 'visible') { l = Math.max(l, ra.left); d = Math.min(d, ra.right); }
      if (ca.overflowY !== 'visible') { t = Math.max(t, ra.top); b = Math.min(b, ra.bottom); }
    }
    if (d - l < 1 || b - t < 1) continue;
    cajas.push({ e, r: { left: l, top: t, right: d, bottom: b }, ctl: esCtl });
  }
  const solapes = [];
  for (let i = 0; i < cajas.length && solapes.length < 60; i++) for (let j = i + 1; j < cajas.length; j++) {
    const a = cajas[i], b = cajas[j];
    if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
    const ix = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
    const iy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (ix >= 2 && iy >= 2) solapes.push({ a: ident(a.e), texto_a: texto(a.e).slice(0, 40), b: ident(b.e), texto_b: texto(b.e).slice(0, 40),
      ancho: r1(ix), alto: r1(iy), hermanos: a.e.parentElement === b.e.parentElement, controles: a.ctl || b.ctl });
  }
  return { viewport: { ancho: vw, alto: vh }, tactiles, recortes_texto: recortes, solapamientos: solapes,
           dt_elementos_escalados: window.__dtFactor ? document.querySelectorAll('[data-dt-obj]').length : null };
}"""

IDS_JS = r"""([patron]) => { const re = new RegExp(patron); const out = [];
  for (const e of document.querySelectorAll('[data-testid]')) { const t = e.getAttribute('data-testid');
    if (!re.test(t)) continue; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if (r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !out.includes(t)) out.push(t); }
  return out; }"""

SCROLL_JS = r"""([frac]) => { const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  let h = document.elementFromPoint(vw / 2, vh / 2);
  for (; h && h !== document.documentElement; h = h.parentElement) {
    const cs = getComputedStyle(h);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && h.scrollHeight > h.clientHeight + 2) {
      h.scrollTop = frac * (h.scrollHeight - h.clientHeight); return true; } }
  return false; }"""

#: Acreditacion: algun elemento con ese testID tiene parte dentro del viewport y no esta tapado
#: (elementFromPoint en el centro de su parte visible cae en el o en un descendiente).
ACREDITA_JS = r"""([tid]) => { const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  for (const e of document.querySelectorAll(`[data-testid="${tid}"]`)) {
    const r = e.getBoundingClientRect(); if (r.width <= 0 || r.height <= 0) continue;
    const l = Math.max(r.left, 0), t = Math.max(r.top, 0), d = Math.min(r.right, vw), b = Math.min(r.bottom, vh);
    if (d - l < 1 || b - t < 1) continue;
    const h = document.elementFromPoint((l + d) / 2, (t + b) / 2);
    if (h && (h === e || e.contains(h) || h.contains(e))) return true; }
  return false; }"""

ACCION_ACCESIBLE_JS = r"""([tid, nombre]) => {
  const cont = document.getElementById('root');
  const k = Object.keys(cont).find((x) => x.startsWith('__reactContainer$'));
  const pila = [cont[k].stateNode.current];
  while (pila.length) { const f = pila.pop(); const pr = f.memoizedProps;
    if (pr && pr.testID === tid && pr.onAccessibilityAction) { pr.onAccessibilityAction({ nativeEvent: { actionName: nombre } }); return true; }
    if (f.sibling) pila.push(f.sibling); if (f.child) pila.push(f.child); }
  return false; }"""


class NoCapturada(Exception):
    """La receta no puede alcanzar la pantalla de forma fiable (motivo concreto)."""


# ---------------------------------------------------------------- API (lectura para elegir datos)
class Api:
    def __init__(self, base: str, token: str) -> None:
        self.base, self._token = base, token

    def get(self, ruta: str):
        req = urllib.request.Request(self.base + ruta, headers={"Authorization": f"Bearer {self._token}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, ruta: str, cuerpo: dict):
        req = urllib.request.Request(self.base + ruta, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))


def descubrir(api: Api, hoy: dt.date) -> dict:
    """Elige datos de g2-bu para las recetas (solo lectura de la API; nada se exporta)."""
    d: dict = {"hoy": str(hoy)}
    ini_mes = hoy.replace(day=1)
    ini_ant = (ini_mes - dt.timedelta(days=1)).replace(day=1)
    filas: list = []
    cursor = None
    for _ in range(10):
        ruta = f"/v1/actividad?desde={ini_ant}&hasta={hoy + dt.timedelta(days=1)}&limite=100" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        try:
            pag = api.get(ruta)
        except urllib.error.HTTPError:
            pag = api.get(f"/v1/actividad?desde={ini_ant}&hasta={hoy + dt.timedelta(days=1)}" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""))
        filas += pag.get("filas", [])
        cursor = pag.get("siguiente")
        if not cursor:
            break

    def mes(f):
        return "ESTE_MES" if f["fecha_hecho"] >= str(ini_mes) else "MES_ANTERIOR"

    def elegir(pred):
        cands = [f for f in filas if pred(f)]
        cands.sort(key=lambda f: (mes(f) != "ESTE_MES",))
        return {"id": cands[0]["id"], "mes": mes(cands[0])} if cands else None

    simple = lambda f: (f["tipo"] == "GASTO" and f.get("estado_reparto") == "COMPLETA" and not f.get("pendiente")  # noqa: E731
                        and not f.get("devolucion_de") and not f.get("abono") and not f.get("maestros_desactivados")
                        and f.get("importe_total"))
    d["n_filas"] = len(filas)
    d["gasto_simple"] = elegir(simple)
    d["gasto_simple_tercero"] = elegir(lambda f: simple(f) and f.get("tercero") and f.get("categoria")) or d["gasto_simple"]
    d["gasto_reparto"] = elegir(lambda f: f["tipo"] == "GASTO" and not f.get("devolucion_de") and (
        f.get("pendiente") or f.get("estado_reparto") == "PARCIAL"
        or (f.get("tu_parte") and f.get("importe_total") and f["tu_parte"] != f["importe_total"])))
    d["abono_pendiente"] = elegir(lambda f: f.get("abono") == "PENDIENTE")
    for k in ("gasto_anulable", "gasto_no_anulable", "gasto_corregible", "gasto_devolucion"):
        d[k] = None
    gastos = [x for x in filas if x["tipo"] == "GASTO" and not x.get("devolucion_de")]
    gastos.sort(key=lambda f: mes(f) != "ESTE_MES")
    for f in gastos[:40]:
        ref = {"id": f["id"], "mes": mes(f)}
        try:
            acc = api.get(f"/v1/hechos/{f['id']}/edicion").get("acciones") or {}
            disp = lambda k: bool((acc.get(k) or {}).get("disponible"))  # noqa: E731
            if disp("anular_duplicado") and not d["gasto_anulable"]:
                d["gasto_anulable"] = ref
            if not disp("anular_duplicado") and not d["gasto_no_anulable"]:
                d["gasto_no_anulable"] = ref
            if disp("corregir") and not d["gasto_corregible"]:
                d["gasto_corregible"] = ref
            if not d["gasto_devolucion"] and api.get(f"/v1/hechos/{f['id']}/devoluciones").get("disponible"):
                d["gasto_devolucion"] = ref
        except Exception:  # noqa: BLE001
            continue
        if all(d[k] for k in ("gasto_anulable", "gasto_no_anulable", "gasto_corregible", "gasto_devolucion")):
            break
    d["fixture_ab2d40a4"] = elegir(lambda f: f["id"].startswith("ab2d40a4"))
    # terceros con posiciones
    terceros = api.get("/v1/terceros").get("terceros", [])
    d["n_terceros"] = len(terceros)
    pend = []
    for t in terceros[:80]:
        try:
            p = api.get(f"/v1/terceros/{t['id']}/pendiente")
        except Exception:  # noqa: BLE001
            continue
        pos = p.get("posiciones", [])
        if pos:
            pend.append({"id": t["id"], "nombre": t["nombre"], "neto_estado": p.get("neto_estado"),
                         "der": sum(1 for x in pos if x["tipo"] == "DERECHO_COBRO"),
                         "obl": sum(1 for x in pos if x["tipo"] == "OBLIGACION_PAGO"),
                         "sin_det": any(x.get("saldo") is None for x in pos),
                         "ab2": any(str(x.get("entidad_id", "")).startswith("ab2d40a4") or str(x.get("origen_hecho_id") or "").startswith("ab2d40a4") for x in pos)})
    d["n_terceros_con_posiciones"] = len(pend)
    sel = lambda xs: {"id": xs[0]["id"], "nombre": xs[0]["nombre"]} if xs else None  # noqa: E731
    d["t_derechos"] = sel(sorted([x for x in pend if x["der"]], key=lambda x: -x["der"]))
    d["t_mixto"] = sel([x for x in pend if x["der"] and x["obl"]]) or sel([x for x in pend if x["obl"]])
    d["t_indet"] = sel([x for x in pend if x["neto_estado"] == "INDETERMINADO" or x["sin_det"]]) or sel(pend)
    d["t_ab2"] = sel([x for x in pend if x["ab2"]])
    # categorias
    cats = api.get("/v1/categorias").get("categorias", [])
    por_id = {c["id"]: c for c in cats}
    hijos = {c["parent_id"] for c in cats if c["parent_id"]}

    def cadena(cid):
        out = []
        c = por_id[cid]
        while c["parent_id"]:
            out.insert(0, c["parent_id"])
            c = por_id[c["parent_id"]]
        return out

    def cat(pred):
        xs = [c for c in cats if pred(c)]
        return {"id": xs[0]["id"], "ancestros": cadena(xs[0]["id"]), "hoja": xs[0]["id"] not in hijos} if xs else None

    d["n_categorias"] = len(cats)
    d["cat_magnitudes"] = cat(lambda c: c["enabled"] and c["magnitudes"] and c["id"] not in hijos) or cat(lambda c: c["enabled"] and c["magnitudes"])
    d["cat_hoja"] = (cat(lambda c: c["enabled"] and c["id"] not in hijos and c["parent_id"])
                     or cat(lambda c: c["enabled"] and c["id"] not in hijos and c["ambito"] in ("GASTO", "AMBOS")))
    d["cat_padre"] = cat(lambda c: c["enabled"] and c["id"] in hijos and c["ambito"] in ("GASTO", "AMBOS"))
    d["cat_registro"] = cat(lambda c: c["enabled"] and c["id"] not in hijos and c["ambito"] in ("GASTO", "AMBOS")
                            and c.get("capturable", True) and not any(m["obligatoria"] for m in c["magnitudes"]))
    return d


# ---------------------------------------------------------------- recetas
class Ctx:
    def __init__(self, page, web: str, salida: pathlib.Path, variante: str, datos: dict, registro: dict, api=None, hoy=None) -> None:
        self.page, self.web, self.salida, self.variante, self.d, self.reg = page, web, salida, variante, datos, registro
        self.api, self.hoy = api, hoy
        self.fila = ""
        self.n = 0
        self.esperado = "accion-registrar"
        self.nombres: set[str] = set()

    def redescubrir(self) -> None:
        """Vuelve a elegir datos tras una escritura de la propia receta (actualiza el dict compartido)."""
        nuevo = descubrir(self.api, self.hoy)
        nuevo["_owner_vacio"] = self.d.get("_owner_vacio", False)
        self.d.clear()
        self.d.update(nuevo)

    # localizadores
    def t(self, i: str):
        return self.page.locator(f'[data-testid="{i}"]:visible')

    def vis(self, i: str) -> bool:
        return self.t(i).count() > 0

    def clic(self, i: str, timeout: int = 10000) -> None:
        self.t(i).first.click(timeout=timeout)
        self.page.wait_for_timeout(250)

    def clic_si(self, i: str) -> bool:
        if self.vis(i):
            self.clic(i)
            return True
        return False

    def esperar(self, i: str, timeout: int = 15000) -> None:
        self.t(i).first.wait_for(timeout=timeout)
        self.esperado = i

    def ids(self, patron: str) -> list[str]:
        return self.page.evaluate(IDS_JS, [patron])

    def primero(self, patron: str, motivo: str) -> str:
        xs = self.ids(patron)
        if not xs:
            raise NoCapturada(motivo)
        return xs[0]

    def scroll(self, frac: float = 1.0) -> bool:
        r = self.page.evaluate(SCROLL_JS, [frac])
        self.page.wait_for_timeout(350)
        return r

    # capturas y detector
    def cap(self, nombre: str, esperado: str | None = None) -> None:
        self.n += 1
        if self.variante in ("dt", "oscuro_dt"):
            self.page.evaluate("() => window.__dtAplicar && window.__dtAplicar()")
        self.page.wait_for_timeout(500)
        base = f"{self.fila}_{self.variante}_{nombre}"
        k = 2
        while base in self.nombres:
            base = f"{self.fila}_{self.variante}_{nombre}_{k}"
            k += 1
        self.nombres.add(base)
        f = base + ".png"
        self.page.screenshot(path=str(self.salida / f))
        tid = esperado or self.esperado
        entrada = {"momento": nombre, "orden": self.n, "captura": f,
                   "acreditacion": {"testid_esperado": tid, "visible": self.page.evaluate(ACREDITA_JS, [tid])}}
        try:
            medida = self.page.evaluate(LAYOUT_JS, list(ELIPSIS_AUTORIZADA))
            extra = self.page.evaluate(DETECTOR_JS, list(ELIPSIS_AUTORIZADA))
            entrada.update({"layout": {**medida, "fallos": fallos_layout(medida)}, **extra, "detector_ok": True})
        except Exception as exc:  # noqa: BLE001 - fallo del detector = PENDIENTE
            entrada.update({"detector_ok": False, "detector_error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        self.reg["capturas"].append(entrada)

    # navegacion comun
    def inicio(self) -> None:
        self.page.goto(self.web)
        self.esperar("accion-registrar", 30000)
        self.page.wait_for_timeout(900)

    def ajustes(self, seccion: str | None = None) -> None:
        self.inicio()
        self.clic("tab-MAS")
        self.esperar("mas-ajustes")
        self.clic("mas-ajustes")
        self.esperar("pantalla-ajustes")
        if seccion:
            self.clic(f"ajustes-{seccion}")
            self.page.wait_for_timeout(900)

    def registro(self, tipo: str = "GASTO") -> None:
        self.inicio()
        self.clic("accion-registrar")
        self.esperar("hoja-tipos")
        self.clic(f"tipo-{tipo}")
        self.esperar("campo-importe")
        self.page.wait_for_timeout(700)

    def sin_categoria(self) -> None:
        self.clic("campo-categoria")
        self.esperar("selector-sin-categoria")
        self.clic("selector-sin-categoria")

    def elegir_categoria(self) -> bool:
        c = self.d.get("cat_registro")
        if not c:
            return False
        self.clic("campo-categoria")
        self.page.wait_for_timeout(600)
        for a in c["ancestros"]:
            if self.vis(f"cat-{a}"):
                self.clic(f"cat-{a}")
                self.page.wait_for_timeout(400)
        if not self.vis(f"cat-{c['id']}"):
            self.clic_si("selector-cerrar")
            return False
        self.clic(f"cat-{c['id']}")
        self.page.wait_for_timeout(500)
        self.clic_si("selector-usar")
        return True

    def elegir_tercero(self) -> bool:
        self.clic("campo-tercero")
        self.esperar("selector-tercero")
        self.page.wait_for_timeout(700)
        xs = self.ids(f"^(reciente|tercero)-{UUID}$")
        if not xs:
            self.clic_si("tercero-cerrar")
            return False
        self.clic(xs[0])
        return True

    def completar(self, importe: str, sin_cat: bool = True) -> None:
        self.t("campo-importe").first.fill(importe)
        if sin_cat and self.vis("campo-categoria"):
            self.sin_categoria()
        self.clic_si("presupuestable-true")
        self.clic_si("solo-mio")
        if self.t("registrar").first.get_attribute("aria-disabled") == "true":
            cuentas = self.ids(f"^cuenta-{UUID}$")
            if cuentas:
                self.clic(cuentas[0])
        self.page.wait_for_timeout(300)

    def registrar_y_exito(self) -> None:
        if self.t("registrar").first.get_attribute("aria-disabled") == "true":
            faltan = self.t("faltan").first.inner_text() if self.vis("faltan") else "?"
            raise NoCapturada(f"«Registrar» sigue desactivado: {faltan}")
        self.clic("registrar")
        self.esperar("registro-exito", 20000)
        self.page.wait_for_timeout(600)

    def actividad(self, mes: str = "ESTE_MES") -> None:
        self.inicio()
        self.clic("tab-DIA")
        self.esperar("pantalla-actividad")
        if mes != "ESTE_MES":
            self.clic("actividad-periodo")
            self.clic(f"periodo-{mes}")
        self.page.wait_for_timeout(1200)

    def abrir_hecho(self, ref: dict | None, motivo: str) -> None:
        if not ref:
            raise NoCapturada(motivo)
        self.actividad(ref["mes"])
        fid = f"fila-{ref['id']}"
        for _ in range(15):
            if self.vis(fid):
                self.t(fid).first.scroll_into_view_if_needed()
                self.clic(fid)
                self.esperar("detalle-contenido")
                self.page.wait_for_timeout(800)
                return
            if self.vis("actividad-mas"):
                self.clic("actividad-mas")
                self.page.wait_for_timeout(1000)
            else:
                break
        raise NoCapturada(f"la fila {ref['id'][:8]} no aparece en Día a día ({ref['mes']})")

    def pendiente_con(self, ter: dict | None, motivo: str) -> None:
        if not ter:
            raise NoCapturada(motivo)
        self.ajustes("terceros")
        self.esperar("pantalla-terceros")
        if self.vis("ajter-buscar"):
            self.t("ajter-buscar").first.fill(ter["nombre"])
            self.page.wait_for_timeout(700)
        self.clic(f"ajter-fila-{ter['id']}")
        self.esperar("ajter-pendiente")
        self.clic("ajter-pendiente")
        self.esperar("pendiente-con")
        self.page.wait_for_timeout(900)

    def posiciones(self) -> list[str]:
        return self.ids(f"^posicion-{UUID}$")

    def detalle_categoria(self, c: dict | None, motivo: str) -> None:
        if not c:
            raise NoCapturada(motivo)
        self.ajustes("categorias")
        self.esperar("pantalla-categorias")
        self.page.wait_for_timeout(600)
        for a in c["ancestros"]:
            self.clic(f"fila-{a}")
            self.page.wait_for_timeout(500)
        self.clic(f"fila-{c['id']}")
        self.page.wait_for_timeout(700)
        if not self.vis("detalle-categoria"):
            self.clic("ver-detalle-nivel")
        self.esperar("detalle-categoria")
        self.page.wait_for_timeout(600)

    def magnitudes_expandidas(self) -> None:
        self.t("seccion-magnitudes").first.scroll_into_view_if_needed()
        if not self.vis("magnitudes-anadir") and self.vis("magnitudes-cabecera"):
            self.clic("magnitudes-cabecera")
        self.page.wait_for_timeout(600)

    def accion_accesible(self, tid: str, nombre: str) -> bool:
        return self.page.evaluate(ACCION_ACCESIBLE_JS, [tid, nombre])


def r01(c: Ctx):
    c.inicio(); c.cap("inicio")
    c.scroll(1.0); c.cap("inicio_fondo", "home")


def r02(c: Ctx):
    c.inicio()
    c.clic("accion-registrar"); c.esperar("hoja-tipos"); c.cap("hoja_tipos")
    c.clic("tipos-cancelar"); c.clic("tab-DIA"); c.page.wait_for_timeout(800); c.cap("barra_inferior_dia", "pantalla-actividad")


def r03(c: Ctx, tipo: str = "GASTO"):
    c.registro(tipo); c.cap("captura_vacia")
    c.completar("0,03"); c.cap("captura_completa", "registro-form")
    c.registrar_y_exito(); c.cap("exito")


def r04(c: Ctx):
    r03(c, "INGRESO")


def r05(c: Ctx):
    c.inicio(); c.clic("accion-registrar"); c.esperar("hoja-tipos"); c.clic("tipo-TRANSFERENCIA")
    c.esperar("transferencia-form"); c.page.wait_for_timeout(800); c.cap("captura_vacia")
    c.t("campo-importe").first.fill("0,02")
    desde = c.ids(f"^desde-{UUID}$")
    if not desde:
        raise NoCapturada("sin cuentas de origen elegibles")
    c.clic(desde[0])
    hacia = [x for x in c.ids(f"^a-{UUID}$") if x[2:] != desde[0][6:]]
    if not hacia:
        raise NoCapturada("sin segunda cuenta de destino")
    c.clic(hacia[0]); c.cap("captura_completa", "transferencia-form")
    if c.t("registrar").first.get_attribute("aria-disabled") == "true":
        raise NoCapturada("«Registrar» desactivado en transferencia")
    c.clic("registrar"); c.esperar("transferencia-exito", 20000); c.cap("exito")


def r06(c: Ctx):
    c.inicio()
    acc = c.ids(f"^acceso-{UUID}$")
    if not acc and c.api:
        import uuid as _uuid
        tipos = c.api.get("/v1/preferencias").get("tipos", {})
        pid, aid = str(_uuid.uuid4()), str(_uuid.uuid4())
        c.api.post("/v1/plantillas", {"id": pid, "nombre": "Prueba web", "tipo_hecho_id": tipos["GASTO"], "presupuestable_default": True})
        c.api.post("/v1/acciones-rapidas", {"id": aid, "plantilla_registro_id": pid, "nombre": "Prueba web"})
        c.reg["notas"].append("g2-bu no tenía accesos: sembrada por la API pública una plantilla y su acceso «Prueba web» (base desechable)")
        c.inicio()
        acc = c.ids(f"^acceso-{UUID}$")
    if not acc:
        raise NoCapturada("g2-bu no tiene accesos de plantilla en Inicio")
    c.clic(acc[0]); c.esperar("chip-plantilla"); c.page.wait_for_timeout(700); c.cap("plantilla_aplicada")
    c.clic("quitar-plantilla"); c.cap("plantilla_quitada", "registro-form")


def r08(c: Ctx):
    c.registro("GASTO")
    c.clic("campo-categoria"); c.page.wait_for_timeout(900); c.cap("selector_raiz", "selector-cerrar")
    padre = c.d.get("cat_padre")
    if padre and not padre["ancestros"] and c.vis(f"cat-{padre['id']}"):
        c.clic(f"cat-{padre['id']}"); c.page.wait_for_timeout(600); c.cap("selector_nivel", "selector-cerrar")
    else:
        c.reg["notas"].append("g2-bu no tiene categorías con subcategorías: no hay nivel de jerarquía que capturar")
    if c.vis("selector-miga-todas"):
        c.clic("selector-miga-todas")
    if c.vis("selector-busqueda"):
        c.t("selector-busqueda").first.fill("a"); c.page.wait_for_timeout(800); c.cap("selector_busqueda", "selector-busqueda")


def r09(c: Ctx):
    c.registro("GASTO")
    c.clic("campo-tercero"); c.esperar("selector-tercero"); c.page.wait_for_timeout(800); c.cap("selector_recientes")
    c.t("tercero-filtro").first.fill("Zzz Tercero Nuevo"); c.page.wait_for_timeout(900); c.cap("busqueda_y_alta", "tercero-crear")


def r10(c: Ctx):
    c.registro("GASTO")
    if not c.vis("campo-contexto"):
        c.clic("abrir-mas-detalles")
    c.clic("campo-contexto"); c.esperar("selector-contexto"); c.page.wait_for_timeout(700); c.cap("selector_contexto")
    c.clic("contexto-nuevo"); c.page.wait_for_timeout(700); c.cap("alta_contexto", "ctx-nombre")


def r11(c: Ctx):
    c.registro("GASTO")
    c.t("campo-importe").first.fill("0,04")
    ter = c.elegir_tercero()
    cat = c.elegir_categoria()
    if not cat:
        c.sin_categoria()
    c.completar("0,04", sin_cat=False); c.cap("captura", "registro-form")
    c.registrar_y_exito()
    c.cap("exito_preferencia_afinidad")
    c.reg["notas"].append(f"tercero elegido={ter}; categoria elegida={cat}; recordar-afinidad visible={c.vis('recordar-afinidad')}; "
                          f"pref-tarjeta visible={c.vis('pref-tarjeta')}")
    c.scroll(1.0); c.cap("exito_fondo")


def r12(c: Ctx):
    c.registro("GASTO"); c.completar("0,05"); c.registrar_y_exito()
    c.t("guardar-como-plantilla").first.scroll_into_view_if_needed()
    c.clic("guardar-como-plantilla"); c.esperar("guardar-plantilla"); c.page.wait_for_timeout(600); c.cap("guardar_plantilla")


def r13(c: Ctx):
    c.registro("GASTO"); c.completar("1,00")
    c.t("reembolsable").first.scroll_into_view_if_needed(); c.page.wait_for_timeout(300); c.cap("eleccion_reparto", "reembolsable")


def _c03_hasta_c2(c: Ctx, importe: str):
    c.registro("GASTO"); c.completar(importe)
    c.clic("reembolsable"); c.esperar("reembolso"); c.page.wait_for_timeout(500)


def r14(c: Ctx):
    _c03_hasta_c2(c, "1,00"); c.cap("c2_vacio")
    c.clic("reembolso-quien"); c.esperar("selector-persona"); c.page.wait_for_timeout(900); c.cap("c2_selector_persona_empresa")
    p = c.ids(f"^persona-{UUID}$")
    if not p:
        raise NoCapturada("selector sin personas/empresas")
    c.clic(p[0]); c.page.wait_for_timeout(500)
    c.clic("reembolso-otra"); c.t("reembolso-importe").first.fill("5"); c.page.wait_for_timeout(500); c.cap("c2_parcial_validacion", "reembolso-importe")
    c.clic("reembolso-todo"); c.cap("c2_total", "reembolso-todo")


def r15(c: Ctx):
    _c03_hasta_c2(c, "1,00")
    c.clic("reembolso-quien"); c.esperar("selector-persona"); c.page.wait_for_timeout(900)
    p = c.ids(f"^persona-{UUID}$")
    if not p:
        raise NoCapturada("selector sin personas/empresas")
    c.clic(p[0]); c.clic("reembolso-todo"); c.clic("reembolso-hecho"); c.esperar("reembolso-resumen")
    c.registrar_y_exito(); c.cap("c3_exito")
    c.actividad()
    filas = c.ids(f"^fila-{UUID}$")
    if not filas:
        raise NoCapturada("Día a día sin filas tras registrar")
    c.clic(filas[0]); c.esperar("detalle-contenido"); c.page.wait_for_timeout(900); c.cap("c3_detalle_derecho")
    c.scroll(1.0); c.cap("c3_detalle_fondo")


def r16(c: Ctx):
    c.pendiente_con(c.d.get("t_derechos"), "ningún tercero con derechos de cobro")
    c.cap("c4_lista_derechos")
    ps = c.posiciones()
    if not ps:
        raise NoCapturada("sin posiciones visibles")
    c.clic(ps[0]); c.esperar("posicion-acciones"); c.cap("c4_seleccion_derecho")
    if not c.vis("posicion-cobrar"):
        raise NoCapturada("la primera posición no es un derecho de cobro")
    c.clic("posicion-cobrar"); c.esperar("accion-enviar"); c.page.wait_for_timeout(600); c.cap("c4_cobro_formulario", "accion-importe")
    if c.vis("accion-importe"):
        c.t("accion-importe").first.fill("0,01"); c.page.wait_for_timeout(400); c.cap("c4_cobro_parcial", "accion-importe")


def r17(c: Ctx):
    c.registro("GASTO"); c.completar("2,00")
    c.clic("repartir"); c.esperar("compartido-reparto"); c.page.wait_for_timeout(700); c.cap("reparto")
    c.clic("reparto-anadir"); c.esperar("selector-persona"); c.page.wait_for_timeout(800); c.cap("selector_persona")
    p = c.ids(f"^persona-{UUID}$")
    if not p:
        raise NoCapturada("selector sin personas")
    c.clic(p[0]); c.clic_si("reparto-iguales"); c.page.wait_for_timeout(500); c.cap("reparto_iguales", "compartido-reparto")
    c.registro("GASTO"); c.completar("2,00")
    c.clic("otra-persona"); c.esperar("compartido-base"); c.page.wait_for_timeout(600); c.cap("pagador_otra_persona")


def r18(c: Ctx):
    c.registro("GASTO"); c.completar("2,00")
    c.clic("repartir"); c.esperar("compartido-reparto")
    c.clic("reparto-anadir"); c.esperar("selector-persona"); c.page.wait_for_timeout(800)
    p = c.ids(f"^persona-{UUID}$")
    if not p:
        raise NoCapturada("selector sin personas")
    c.clic(p[0]); c.clic_si("reparto-iguales"); c.clic("reparto-listo"); c.page.wait_for_timeout(600)
    cuentas = c.ids(f"^compartido-cuenta-{UUID}$")
    if cuentas:
        c.clic(cuentas[0])
    c.cap("formulario_resumen", "compartido-form")
    c.clic("compartido-revisar"); c.page.wait_for_timeout(800)
    if c.vis("compartido-te-deben"):
        c.cap("te_deben", "compartido-te-deben")
        for x in c.ids(f"^te-debe-{UUID}-si$"):
            c.clic(x)
        c.clic("te-deben-revisar")
    c.esperar("compartido-revision"); c.page.wait_for_timeout(600); c.cap("revision")
    c.clic("registrar-compartido"); c.esperar("compartido-exito", 20000); c.page.wait_for_timeout(600); c.cap("exito")


def r19(c: Ctx):
    c.pendiente_con(c.d.get("t_indet"), "ningún tercero con posiciones")
    c.cap("pendiente_con"); c.scroll(1.0); c.cap("pendiente_con_fondo")


def r20(c: Ctx):
    c.pendiente_con(c.d.get("t_mixto"), "ningún tercero con obligación de pago")
    c.cap("lista")
    ps = c.posiciones()
    if not ps:
        raise NoCapturada("sin posiciones visibles")
    hecho_cobro = hecho_pago = False
    for pid in ps[:6]:
        c.clic(pid); c.esperar("posicion-acciones")
        if c.vis("posicion-pagar") and not hecho_pago:
            c.cap("obligacion_acciones"); c.clic("posicion-pagar"); c.esperar("accion-enviar"); c.cap("pago_formulario", "accion-importe")
            hecho_pago = True; c.clic("accion-cancelar"); c.page.wait_for_timeout(400)
        elif c.vis("posicion-cobrar") and not hecho_cobro:
            c.clic("posicion-cobrar"); c.esperar("accion-enviar"); c.cap("cobro_formulario", "accion-importe")
            hecho_cobro = True; c.clic("accion-cancelar"); c.page.wait_for_timeout(400)
        if c.vis("posicion-perdonar") and not c.reg.get("_perdon"):
            c.clic("posicion-perdonar"); c.esperar("accion-enviar"); c.cap("perdon_formulario", "accion-importe"); c.reg["_perdon"] = True
            c.clic("accion-cancelar"); c.page.wait_for_timeout(400)
        if c.vis("posicion-atras"):
            c.clic("posicion-atras"); c.page.wait_for_timeout(400)
        if hecho_cobro and hecho_pago:
            break
    c.reg.pop("_perdon", None)
    c.reg["notas"].append(f"cobro capturado={hecho_cobro}; pago capturado={hecho_pago}")


def r21(c: Ctx):
    c.abrir_hecho(c.d.get("gasto_reparto"), "ningún gasto con reparto y posiciones en los dos últimos meses")
    if not c.vis("detalle-corregir-reparto"):
        c.scroll(1.0)
    c.clic("detalle-corregir-reparto"); c.esperar("corregir-form"); c.page.wait_for_timeout(700); c.cap("formulario")
    imp = c.ids(f"^corregir-importe-{UUID}$")
    if imp:
        c.t(imp[0]).first.fill("0,01"); c.page.wait_for_timeout(500); c.cap("formulario_editado_validacion", "corregir-form")
    if c.t("corregir-revisar").first.get_attribute("aria-disabled") != "true":
        c.clic("corregir-revisar"); c.page.wait_for_timeout(700); c.cap("revision_motivo", "corregir-revision")


def r22(c: Ctx):
    ref = c.d.get("fixture_ab2d40a4")
    if ref:
        c.abrir_hecho(ref, "")
        c.cap("detalle_fixture"); c.scroll(1.0); c.cap("detalle_fixture_fondo")
        pend = c.ids(f"^detalle-pendiente-{UUID}$")
        if pend:
            c.clic(pend[0]); c.esperar("pendiente-con"); c.page.wait_for_timeout(800); c.cap("pendiente_con")
        return
    if c.d.get("t_ab2"):
        c.pendiente_con(c.d["t_ab2"], ""); c.cap("pendiente_con"); return
    raise NoCapturada("fixture ab2d40a4… (lote S3-L01) no existe en el dump de cierre de S2: se creó en S3a; sin posición saldada ni apertura desconocida sintética en g2-bu")


def r23(c: Ctx):
    c.actividad(); c.cap("lista")
    c.clic("actividad-periodo"); c.esperar("hoja-periodo"); c.cap("periodo"); c.clic("periodo-cerrar")
    c.clic("actividad-filtros"); c.esperar("hoja-filtros"); c.page.wait_for_timeout(500); c.cap("filtros")
    c.page.keyboard.press("Escape"); c.actividad()
    c.clic("actividad-buscar"); c.page.wait_for_timeout(400)
    c.t("actividad-busqueda").first.fill("a"); c.page.wait_for_timeout(1200); c.cap("busqueda", "actividad-busqueda")
    c.actividad(); c.scroll(1.0); c.cap("fondo_cargar_mas", "pantalla-actividad")


def r24(c: Ctx):
    c.abrir_hecho(c.d.get("gasto_reparto") or c.d.get("gasto_simple_tercero"), "sin gastos en los dos últimos meses")
    c.cap("detalle"); c.scroll(1.0); c.cap("detalle_atribucion_posiciones")


def r25(c: Ctx):
    c.abrir_hecho(c.d.get("gasto_corregible"), "ningún gasto corregible según GET /v1/hechos/{id}/edicion")
    c.clic("detalle-mas"); c.esperar("hoja-mas-hecho"); c.cap("mas_elegibilidad")
    c.clic("mas-corregir"); c.esperar("corregir-hecho-form"); c.page.wait_for_timeout(700); c.cap("formulario")
    c.t("corregir-hecho-importe").first.fill("0,07"); c.page.wait_for_timeout(400)
    c.clic("corregir-hecho-revisar"); c.page.wait_for_timeout(800); c.cap("revision", "corregir-hecho-revision")


def r26(c: Ctx):
    if c.d.get("gasto_no_anulable"):
        c.abrir_hecho(c.d["gasto_no_anulable"], "")
        c.clic("detalle-mas"); c.esperar("hoja-mas-hecho")
        c.cap("anular_no_elegible_bloqueo", "mas-anular")
    c.abrir_hecho(c.d.get("gasto_anulable"), "ningún gasto anulable según GET /v1/hechos/{id}/edicion")
    c.clic("detalle-mas"); c.esperar("hoja-mas-hecho")
    c.clic("mas-anular"); c.esperar("hoja-anular-duplicado"); c.page.wait_for_timeout(600); c.cap("anular_motivo")
    c.clic_si("anular-motivo-0"); c.cap("anular_confirmacion")


def r27(c: Ctx):
    c.abrir_hecho(c.d.get("gasto_devolucion"), "ningún gasto con devolución disponible según GET /v1/hechos/{id}/devoluciones")
    c.clic("detalle-registrar-devolucion"); c.esperar("devolucion-form"); c.page.wait_for_timeout(800); c.cap("formulario_origen")
    c.t("campo-importe").first.fill("0,01"); c.page.wait_for_timeout(400)
    c.clic_si("abono-todavia-no"); c.cap("importe_categoria_abono", "devolucion-form")
    c.scroll(1.0); c.cap("formulario_fondo")
    c.clic("revisar"); c.esperar("devolucion-revision"); c.page.wait_for_timeout(500); c.cap("revision")
    c.clic("registrar-devolucion"); c.esperar("devolucion-exito", 20000); c.page.wait_for_timeout(500); c.cap("exito")


def r28(c: Ctx):
    ref = c.d.get("abono_pendiente")
    if not ref:
        c.redescubrir()
        ref = c.d.get("abono_pendiente")
    if not ref:
        raise NoCapturada("ninguna devolución con abono pendiente (G5-27 no la dejó creada)")
    c.abrir_hecho(ref, "")
    if not c.vis("detalle-registrar-abono"):
        c.scroll(1.0)
    c.clic("detalle-registrar-abono"); c.esperar("hoja-abono"); c.page.wait_for_timeout(600); c.cap("abono_inmediato")
    if c.vis("abono-otra-cuenta"):
        c.clic("abono-otra-cuenta"); c.cap("abono_otra_cuenta")


def _pendientes(c: Ctx):
    c.inicio()
    if not c.vis("campana-pendientes"):
        if c.vis("atencion-ver-todos"):
            c.clic("atencion-ver-todos")
        else:
            raise NoCapturada("sin campana de pendientes en Inicio (g2-bu sin previsiones pendientes)")
    else:
        c.clic("campana-pendientes")
    c.esperar("pendientes"); c.page.wait_for_timeout(1500)


def r29(c: Ctx):
    _pendientes(c); c.cap("pendientes")
    if c.vis("resueltas-cabecera"):
        c.t("resueltas-cabecera").first.scroll_into_view_if_needed(); c.clic("resueltas-cabecera"); c.page.wait_for_timeout(800)
        c.cap("resueltas_desplegadas", "resueltas-cabecera")
    else:
        c.scroll(1.0); c.cap("pendientes_fondo")
        c.reg["notas"].append("«Resueltas este mes» no visible")


def _abrir_prevision(c: Ctx):
    _pendientes(c)
    xs = c.ids(f"^pendiente-{UUID}$")
    if not xs:
        raise NoCapturada("lista Pendientes sin filas")
    c.clic(xs[0]); c.esperar("prevision-detalle"); c.page.wait_for_timeout(900)


def r30(c: Ctx):
    _abrir_prevision(c); c.cap("detalle")
    if c.vis("prevision-mas"):
        c.clic("prevision-mas"); c.page.wait_for_timeout(500); c.cap("mas", "hoja-mas")
        c.clic_si("mas-cancelar")
    else:
        c.reg["notas"].append("previsión abierta sin «Más» (solo las resueltas lo tienen)")
    if c.vis("prevision-accion-omitir"):
        c.clic("prevision-accion-omitir"); c.esperar("hoja-omitir"); c.cap("omitir"); c.clic_si("omitir-cancelar")
    _pendientes(c)
    if c.vis("resueltas-cabecera"):
        c.clic("resueltas-cabecera"); c.page.wait_for_timeout(700)
        rs = c.ids(f"^resuelta-{UUID}$")
        if rs:
            c.clic(rs[0]); c.esperar("prevision-mas"); c.clic("prevision-mas"); c.page.wait_for_timeout(400)
            if c.vis("mas-reabrir"):
                c.clic("mas-reabrir"); c.esperar("hoja-reabrir"); c.cap("reabrir")


def r31(c: Ctx):
    _abrir_prevision(c)
    if not c.vis("prevision-accion-registrar"):
        c.scroll(1.0)
    c.clic("prevision-accion-registrar"); c.page.wait_for_timeout(1000); c.cap("registrar", "prevision-importe")
    c.scroll(1.0)
    fondo = next((x for x in ("prevision-registrar", "prevision-revisar", "prevision-falta", "prevision-fecha-hoy", "prevision-importe")
                  if c.page.evaluate(ACREDITA_JS, [x])), "prevision-registrar")
    c.cap("registrar_fondo", fondo)
    _abrir_prevision(c)
    if c.vis("prevision-accion-ya") or c.scroll(1.0):
        if c.vis("prevision-accion-ya"):
            c.clic("prevision-accion-ya"); c.esperar("ya-lo-registre"); c.page.wait_for_timeout(1000); c.cap("ya_lo_registre")


def r32(c: Ctx):
    _pendientes(c)
    xs = c.ids(f"^pendiente-{UUID}$")
    if not xs:
        raise NoCapturada("lista Pendientes sin filas")
    c.cap("lista_swipe")
    hecho = c.accion_accesible(xs[0], "derecha")
    c.page.wait_for_timeout(700)
    if not hecho:
        raise NoCapturada("acción accesible del swipe no encontrada (RN-web no reproduce el gesto)")
    c.cap("tras_swipe_derecha_aviso_deshacer", "pendientes")
    des = c.ids(r"^aviso-rapida-.*-deshacer$")
    if des:
        c.clic(des[0]); c.page.wait_for_timeout(800); c.cap("deshecho", "pendientes")
    c.reg["notas"].append("swipe ejecutado por la acción accesible (misma función que el gesto); el arrastre no se reproduce en web")


def r33(c: Ctx):
    c.inicio(); c.clic("tab-MAS"); c.esperar("pantalla-mas"); c.page.wait_for_timeout(500); c.cap("mas")
    c.clic("mas-ajustes"); c.esperar("pantalla-ajustes"); c.page.wait_for_timeout(500); c.cap("ajustes")
    c.scroll(1.0); c.cap("ajustes_fondo")


def r34(c: Ctx):
    c.ajustes("categorias"); c.esperar("pantalla-categorias"); c.page.wait_for_timeout(700); c.cap("lista")
    c.scroll(1.0); c.cap("lista_fondo")
    cdat = c.d.get("cat_hoja")
    c.detalle_categoria(cdat, "sin subcategorías"); c.cap("detalle_estado")


def r35(c: Ctx):
    c.ajustes("categorias"); c.esperar("pantalla-categorias")
    c.clic("nueva-categoria"); c.esperar("nueva-categoria-pantalla"); c.page.wait_for_timeout(500); c.cap("nueva")
    c.clic("alta-icono"); c.esperar("selector-iconos"); c.page.wait_for_timeout(600); c.cap("iconos")


def r36(c: Ctx):
    cdat = c.d.get("cat_hoja")
    c.detalle_categoria(cdat, "sin subcategoría para las hojas")
    c.clic("accion-mover"); c.esperar("selector-mover"); c.page.wait_for_timeout(600); c.cap("mover")
    c.detalle_categoria(cdat, "")
    c.clic("accion-ambito"); c.esperar("hoja-ambito"); c.page.wait_for_timeout(1500); c.cap("ambito_impacto")
    c.clic_si("ambito-cancelar")
    c.detalle_categoria(cdat, "")
    if c.vis("accion-desactivar"):
        c.clic("accion-desactivar"); c.esperar("hoja-desactivar"); c.page.wait_for_timeout(800); c.cap("desactivar")
    elif c.vis("accion-reactivar"):
        c.clic("accion-reactivar"); c.esperar("hoja-reactivar"); c.cap("reactivar")


def r37(c: Ctx):
    c.ajustes("categorias"); c.esperar("pantalla-categorias")
    c.clic("editar-orden-abrir"); c.esperar("editar-orden"); c.page.wait_for_timeout(600); c.cap("editar_orden")


def asegurar_magnitudes(c: Ctx) -> None:
    """g2-bu no trae magnitudes: crea por la UI dos sinteticas en una categoria hoja (base desechable)."""
    if c.d.get("cat_magnitudes"):
        return
    cat = c.d.get("cat_hoja")
    for nombre, unidad, dec in (("Horas prueba web", "h", 1), ("Sesiones prueba web", "uds", 0)):
        c.detalle_categoria(cat, "sin categoría hoja donde asociar magnitudes")
        c.magnitudes_expandidas()
        c.clic("magnitudes-anadir"); c.esperar("selector-magnitudes"); c.page.wait_for_timeout(600)
        c.clic("selmag-nueva"); c.esperar("nueva-magnitud")
        c.t("nuevamag-nombre").first.fill(nombre); c.t("nuevamag-unidad").first.fill(unidad)
        c.clic_si(f"nuevamag-decimales-{dec}"); c.clic_si("nuevamag-obligatoria-false")
        c.clic("nuevamag-crear"); c.esperar("seccion-magnitudes"); c.page.wait_for_timeout(1000)
    c.redescubrir()
    c.reg["notas"].append("creadas por la UI dos magnitudes sintéticas («Horas prueba web», «Sesiones prueba web») en la base desechable")
    if not c.d.get("cat_magnitudes"):
        raise NoCapturada("no se pudieron crear magnitudes por la UI")


def r38(c: Ctx):
    asegurar_magnitudes(c)
    c.detalle_categoria(c.d.get("cat_magnitudes"), "ninguna categoría con magnitudes")
    c.magnitudes_expandidas(); c.cap("seccion_magnitudes", "seccion-magnitudes")
    if c.vis("magnitudes-editar-orden"):
        c.clic("magnitudes-editar-orden"); c.esperar("orden-magnitudes"); c.page.wait_for_timeout(500); c.cap("orden_magnitudes")


def r39(c: Ctx):
    asegurar_magnitudes(c)
    c.detalle_categoria(c.d.get("cat_magnitudes"), "ninguna categoría con magnitudes")
    c.magnitudes_expandidas()
    c.clic("magnitudes-anadir"); c.esperar("selector-magnitudes"); c.page.wait_for_timeout(800); c.cap("selector")
    c.clic("selmag-nueva"); c.esperar("nueva-magnitud"); c.page.wait_for_timeout(500); c.cap("alta")
    c.detalle_categoria(c.d.get("cat_magnitudes"), ""); c.magnitudes_expandidas()
    fs = c.ids(f"^magnitud-fila-{UUID}$")
    if not fs:
        raise NoCapturada("sin filas de magnitud en la sección")
    c.clic(fs[0]); c.esperar("ficha-magnitud"); c.page.wait_for_timeout(900); c.cap("ficha")


def r40(c: Ctx):
    asegurar_magnitudes(c)
    c.detalle_categoria(c.d.get("cat_magnitudes"), "ninguna categoría con magnitudes"); c.magnitudes_expandidas()
    fs = c.ids(f"^magnitud-fila-{UUID}$")
    if not fs:
        raise NoCapturada("sin filas de magnitud en la sección")
    c.clic(fs[0]); c.esperar("ficha-magnitud"); c.page.wait_for_timeout(900)
    c.clic("bloque-renombrar"); c.esperar("hoja-renombrar-magnitud"); c.cap("editar"); c.clic_si("renmag-cancelar")
    c.page.wait_for_timeout(400)
    if c.vis("bloque-deshabilitar"):
        c.clic("bloque-deshabilitar"); c.page.wait_for_timeout(1500)
        hoja = next((x for x in ("hoja-deshabilitar", "hoja-confirmar-deshabilitar") if c.vis(x)), None)
        if not hoja:
            raise NoCapturada("tras «Deshabilitar» no aparece ninguna hoja de confirmación")
        c.cap("deshabilitar_impacto", hoja)


def r41(c: Ctx):
    if not c.d.get("_owner_vacio"):
        raise NoCapturada("requiere la API con el owner g5-vacio (ronda aparte)")
    c.ajustes("categorias"); c.page.wait_for_timeout(900); c.cap("oferta", "onboarding-oferta")
    c.clic("onboarding-sugeridas"); c.esperar("onboarding-sugeridas-pantalla"); c.page.wait_for_timeout(900); c.cap("sugeridas")
    c.scroll(1.0); c.cap("sugeridas_fondo")


def r42(c: Ctx):
    c.ajustes("preferencias"); c.esperar("pantalla-preferencias"); c.page.wait_for_timeout(800); c.cap("lista")
    fs = c.ids(f"^ajpref-fila-{UUID}$")
    if fs:
        c.clic(fs[0]); c.esperar("ajpref-detalle"); c.page.wait_for_timeout(600); c.cap("detalle_habilitacion")
        c.ajustes("preferencias"); c.esperar("pantalla-preferencias")
    c.clic("ajpref-nueva"); c.page.wait_for_timeout(800); c.cap("alta", "ajpref-form")


def r43(c: Ctx):
    c.ajustes("plantillas"); c.esperar("pantalla-plantillas"); c.page.wait_for_timeout(800); c.cap("lista_accesos_inicio")
    fs = c.ids(f"^ajplt-fila-{UUID}$")
    if fs:
        c.clic(fs[0]); c.esperar("ajplt-detalle"); c.page.wait_for_timeout(600); c.cap("detalle")
        if c.vis("ajplt-editar"):
            c.clic("ajplt-editar"); c.esperar("ajplt-form"); c.page.wait_for_timeout(500); c.cap("editar")
        c.ajustes("plantillas"); c.esperar("pantalla-plantillas")
    c.clic("ajplt-nueva"); c.esperar("ajplt-form"); c.page.wait_for_timeout(600); c.cap("alta")


def r44(c: Ctx):
    c.ajustes("terceros"); c.esperar("pantalla-terceros"); c.page.wait_for_timeout(800); c.cap("lista")
    fs = c.ids(f"^ajter-fila-{UUID}$")
    if fs:
        c.clic(fs[0]); c.esperar("ajter-form"); c.page.wait_for_timeout(800); c.cap("ficha_editar")
        c.clic("ajter-cancelar")
    c.clic("ajter-nuevo"); c.esperar("ajter-form")
    nombre = c.d.get("t_derechos", {}) or {}
    c.t("ajter-nombre").first.fill(nombre.get("nombre", "Tania")); c.page.wait_for_timeout(1500); c.cap("alta_duplicados")


def r45(c: Ctx):
    ter = c.d.get("t_derechos") or c.d.get("t_mixto")
    c.ajustes("terceros"); c.esperar("pantalla-terceros")
    if ter and c.vis("ajter-buscar"):
        c.t("ajter-buscar").first.fill(ter["nombre"]); c.page.wait_for_timeout(700)
    fs = [f"ajter-fila-{ter['id']}"] if ter else c.ids(f"^ajter-fila-{UUID}$")
    if not fs or not c.vis(fs[0]):
        fs = c.ids(f"^ajter-fila-{UUID}$")
    if not fs:
        raise NoCapturada("sin terceros")
    c.clic(fs[0]); c.esperar("ajter-form"); c.page.wait_for_timeout(800)
    c.scroll(1.0); c.cap("ficha_desactivar_registros")
    if c.vis("ajter-ver-registros"):
        c.clic("ajter-ver-registros"); c.page.wait_for_timeout(1500); c.cap("registros_del_tercero", "pantalla-actividad")


def r46(c: Ctx):
    c.ajustes("contextos"); c.esperar("pantalla-contextos"); c.page.wait_for_timeout(800); c.cap("lista")
    fs = c.ids(f"^ajctx-fila-{UUID}$")
    if fs:
        c.clic(fs[0]); c.esperar("ajctx-form"); c.page.wait_for_timeout(500); c.cap("editar_estado")
        c.ajustes("contextos"); c.esperar("pantalla-contextos")
    c.clic("ajctx-nuevo"); c.esperar("ajctx-form"); c.page.wait_for_timeout(500); c.cap("alta")


def r47(c: Ctx):
    c.ajustes("cuentas"); c.esperar("pantalla-cuentas"); c.page.wait_for_timeout(1000); c.cap("lista")
    fs = c.ids(f"^cap-fila-{UUID}$")
    if not fs:
        raise NoCapturada("sin cuentas en Ajustes › Cuentas")
    c.clic(fs[0]); c.esperar("cap-detalle"); c.page.wait_for_timeout(1000); c.cap("capacidades")
    c.scroll(1.0); c.cap("capacidades_fondo")
    if c.vis("cap-abrir-historial"):
        c.clic("cap-abrir-historial"); c.esperar("cap-historial"); c.page.wait_for_timeout(1000); c.cap("historial")


def r48(c: Ctx):
    c.registro("GASTO")
    c.clic("fecha-otra"); c.page.wait_for_timeout(400)
    campo = c.t("campo-fecha").first
    campo.fill("31/02/2026"); c.page.keyboard.press("Tab"); c.page.wait_for_timeout(500); c.cap("fecha_imposible", "campo-fecha")
    campo.fill("15/12/2030"); c.page.keyboard.press("Tab"); c.page.wait_for_timeout(500); c.cap("fecha_futura", "campo-fecha")
    campo.fill("15/10/2026"); c.page.keyboard.press("Tab"); c.page.wait_for_timeout(400)
    c.clic("campo-categoria"); c.page.wait_for_timeout(500); c.clic_si("selector-cerrar"); c.page.wait_for_timeout(500)
    c.cap("conservada_tras_selector", "campo-fecha")
    c.reg["notas"].append(f"valor de campo-fecha tras volver del selector: {c.t('campo-fecha').first.input_value() if c.vis('campo-fecha') else 'no visible'}")


def r49(c: Ctx):
    c.registro("GASTO"); c.t("campo-importe").first.fill("9")
    c.clic("cancelar"); c.esperar("confirmar-salida"); c.page.wait_for_timeout(400); c.cap("descartar")
    c.clic("seguir"); c.page.wait_for_timeout(400); c.cap("cancelar_sigue_formulario", "registro-form")


def r50(c: Ctx):
    patron = "**/v1/**"
    c.page.route(patron, lambda ruta: ruta.abort())
    try:
        c.page.goto(c.web); c.page.wait_for_timeout(4000); c.cap("inicio_error_red", "home")
        c.clic("tab-DIA"); c.page.wait_for_timeout(2500); c.cap("dia_error_red", "actividad-error")
    finally:
        c.page.unroute(patron)
    if c.vis("actividad-reintentar"):
        c.clic("actividad-reintentar"); c.page.wait_for_timeout(2000); c.cap("dia_reintento", "pantalla-actividad")
    c.page.context.set_offline(True)
    try:
        c.clic("tab-INICIO"); c.page.wait_for_timeout(300)
        c.clic("accion-registrar"); c.clic("tipo-GASTO"); c.esperar("campo-importe"); c.page.wait_for_timeout(1500)
        c.cap("registro_modo_avion")
    finally:
        c.page.context.set_offline(False)
    c.reg["notas"].append("error simulado con page.route(abort) y modo avión con context.set_offline(True)")


RECETAS = {
    "G5-01": r01, "G5-02": r02, "G5-03": r03, "G5-04": r04, "G5-05": r05, "G5-06": r06, "G5-08": r08, "G5-09": r09,
    "G5-10": r10, "G5-11": r11, "G5-12": r12, "G5-13": r13, "G5-14": r14, "G5-15": r15, "G5-16": r16, "G5-17": r17,
    "G5-18": r18, "G5-19": r19, "G5-20": r20, "G5-21": r21, "G5-22": r22, "G5-23": r23, "G5-24": r24, "G5-25": r25,
    "G5-26": r26, "G5-27": r27, "G5-28": r28, "G5-29": r29, "G5-30": r30, "G5-31": r31, "G5-32": r32, "G5-33": r33,
    "G5-34": r34, "G5-35": r35, "G5-36": r36, "G5-37": r37, "G5-38": r38, "G5-39": r39, "G5-40": r40, "G5-41": r41,
    "G5-42": r42, "G5-43": r43, "G5-44": r44, "G5-45": r45, "G5-46": r46, "G5-47": r47, "G5-48": r48, "G5-49": r49,
    "G5-50": r50,
}
NO_APLICA = {"G5-07": "NO APLICA (decisión D3: no se ejecuta)", "G5-51": "NO APLICA (decisión D4: no se ejecuta)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:5469")
    ap.add_argument("--api", default="http://127.0.0.1:5468")
    # sin rutas de la maquina: argumento > variable GAPTO_CAPTURAS_* > defecto relativo al repositorio
    ap.add_argument("--dist", default=os.environ.get("GAPTO_CAPTURAS_DIST") or str(REPO / "mobile" / "dist"))
    # el token no vive en el repositorio: sin defecto
    ap.add_argument("--token-fichero", default=os.environ.get("GAPTO_CAPTURAS_TOKEN_FICHERO"))
    ap.add_argument("--pantallas", default=os.environ.get("GAPTO_CAPTURAS_PANTALLAS")
                    or str(DIR_SCRIPT / "capturas_g5_PANTALLAS_51.json"))
    # la salida (PNG y export con token) queda FUERA del repositorio, junto a el
    ap.add_argument("--salida", default=os.environ.get("GAPTO_CAPTURAS_SALIDA")
                    or str(REPO.parent / "evidencia_capturas_g5" / "web"))
    ap.add_argument("--variantes", default="claro,oscuro,dt")
    ap.add_argument("--filas", default="", help="lista de filas (vacio = todas)")
    ap.add_argument("--owner-vacio", action="store_true", help="la API corre con el owner g5-vacio: solo G5-41")
    ap.add_argument("--json", default="detector.json")
    a = ap.parse_args()
    if not a.token_fichero:
        ap.error("falta --token-fichero (o GAPTO_CAPTURAS_TOKEN_FICHERO)")
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    pantallas = json.loads(pathlib.Path(a.pantallas).read_text(encoding="utf-8"))
    filas_pedidas = [x for x in a.filas.split(",") if x]
    token = pathlib.Path(a.token_fichero).read_text(encoding="utf-8").strip()
    api = Api(a.api, token)
    fichero_json = salida / a.json
    res = json.loads(fichero_json.read_text(encoding="utf-8")) if fichero_json.exists() else {
        "etiqueta": ETIQUETA, "version_script": "0.5.0", "elipsis_autorizada": list(ELIPSIS_AUTORIZADA), "factor_dt": FACTOR_DT, "filas": {}, "ejecuciones": []}
    hoy = dt.datetime.now().date()

    def guardar():
        fichero_json.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        for variante in [v for v in a.variantes.split(",") if v]:
            t0 = time.time()
            datos = descubrir(api, hoy) if not a.owner_vacio else {"_owner_vacio": True}
            datos["_owner_vacio"] = a.owner_vacio
            res["ejecuciones"].append({"variante": variante, "inicio": dt.datetime.now().isoformat(timespec="seconds"),
                                       "owner_vacio": a.owner_vacio,
                                       "datos_elegidos": {k: (bool(v) if isinstance(v, dict) else v) for k, v in datos.items()}})
            ctx = nav.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES",
                                  timezone_id="Europe/Madrid", color_scheme="dark" if variante in ("oscuro", "oscuro_dt") else "light")
            if variante in ("dt", "oscuro_dt"):
                ctx.add_init_script(DT_JS)
            page = ctx.new_page()
            page.set_default_timeout(10000)
            consola: list[str] = []
            page.on("console", lambda m: consola.append(m.text[:200]) if m.type == "error" else None)
            for p in pantallas:
                fila = p["fila"]
                if filas_pedidas and fila not in filas_pedidas:
                    continue
                if a.owner_vacio and fila != "G5-41":
                    continue
                reg = {"pantalla": p["pantalla"], "estado": "", "motivo": "", "capturas": [], "notas": [], "segundos": 0}
                if fila in NO_APLICA:
                    reg["estado"], reg["motivo"] = "NO APLICA", NO_APLICA[fila]
                    res["filas"].setdefault(fila, {})[variante] = reg
                    continue
                c = Ctx(page, a.web, salida, variante, datos, reg, api, hoy)
                c.fila = fila
                ti = time.time()
                try:
                    RECETAS[fila](c)
                    malas = [x["captura"] for x in reg["capturas"] if not x["detector_ok"] or not x["acreditacion"]["visible"]]
                    if not reg["capturas"]:
                        reg["estado"], reg["motivo"] = "PENDIENTE", "sin capturas"
                    elif malas:
                        reg["estado"], reg["motivo"] = "PENDIENTE", f"captura sin acreditar o detector fallido: {', '.join(malas)}"
                    else:
                        reg["estado"] = "CAPTURADA"
                except NoCapturada as exc:
                    reg["estado"] = "PENDIENTE"
                    reg["motivo"] = ("ruta no alcanzada tras capturas parciales: " if reg["capturas"] else "ruta no alcanzada: ") + str(exc)
                except Exception as exc:  # noqa: BLE001 - una receta no detiene las demas
                    reg["estado"] = "PENDIENTE"
                    reg["motivo"] = ("fallo tras capturas parciales: " if reg["capturas"] else "fallo: ") + f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
                    reg["traza"] = traceback.format_exc()[-1200:]
                    try:
                        f = f"{fila}_{variante}_estado_al_fallar.png"
                        page.screenshot(path=str(salida / f))
                        reg["captura_al_fallar"] = f
                    except Exception:  # noqa: BLE001
                        pass
                reg["segundos"] = round(time.time() - ti, 1)
                res["filas"].setdefault(fila, {})[variante] = reg
                print(f"{variante} {fila} {reg['estado']} {len(reg['capturas'])} {reg['motivo'][:120]}", flush=True)
                guardar()
            res["ejecuciones"][-1]["fin"] = dt.datetime.now().isoformat(timespec="seconds")
            res["ejecuciones"][-1]["segundos"] = round(time.time() - t0)
            res["ejecuciones"][-1]["errores_consola"] = consola[:50]
            guardar()
            ctx.close()
        nav.close()


if __name__ == "__main__":
    main()
