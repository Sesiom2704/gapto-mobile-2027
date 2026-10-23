# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_gate_g5.py
# Ruta: scripts/dev/e2e_f05_gate_g5.py
# Descripcion: F05-GATE G5 (F05 §49.16.2; F05-D050 §64.7): E2E web de las
#   pantallas de F05 que no tenian E2E en scripts/dev segun el inventario de
#   cobertura por pantalla de la tirada nocturna (paso 7). Solo tests.
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS ***.
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). Cada subcaso se hace con la UI y se contrasta con la BD:
#     CAT  Ajustes › Categorías: «Empezar desde cero»; alta desde la UI
#          (Mascotas, Veterinario, Aficiones); mover Veterinario bajo Mascotas;
#          renombrar; cambiar ámbito a AMBOS; desactivar y reactivar; editar el
#          orden de la raiz;
#     MAG  sección de magnitudes de una categoría: nueva magnitud (Horas, h,
#          1 decimal, opcional) y otra (Sesiones); hacer obligatoria; renombrar;
#          deshabilitar y rehabilitar; editar el orden; quitar de la categoría;
#     CTX  Ajustes › Contextos: alta, desactivar y reactivar;
#     REG  registro: «Ayer» (fecha_hecho = hoy - 1); salir con datos -> «¿Descartar?»
#          -> «Salir» (nada persiste); plantilla aplicada -> «Quitar plantilla».
#   Un subcaso que falla no detiene los demas: queda FALLO con su detalle.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-07/GATE tirada nocturna, paso 7)
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import traceback
import uuid
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


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
    q = lambda sql, p=(): _sql(dsn, owner, "gapto_runtime", sql, p)  # noqa: E731

    exigir_base_recreada(dsn, owner)
    tarjeta = crear_cuenta(dsn, owner, "Tarjeta", "CREDITO", "PASIVO")
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "casos": {}}
    capturas: list[str] = []
    consola: list[str] = []

    def cat_por_nombre(nombre: str) -> dict | None:
        return next((c for c in api(a.api, "GET", "/v1/categorias")["categorias"] if c["nombre"] == nombre), None)

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"G5_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def inicio() -> None:
            page.goto(a.web)
            t("accion-registrar").wait_for(timeout=30000)
            page.wait_for_timeout(300)

        def ajustes(seccion: str) -> None:
            inicio()
            t("tab-MAS").click()
            if t("mas-ajustes").count():
                t("mas-ajustes").click()
            t(f"ajustes-{seccion}").click()

        def categorias() -> None:
            ajustes("categorias")
            t("pantalla-categorias").wait_for(timeout=15000)
            page.wait_for_timeout(500)

        def caso(clave: str, nombre: str, fn) -> None:
            try:
                r = fn() or {}
                res["casos"][clave] = {"nombre": nombre, "resultado": r.pop("resultado", "PASS"), **r}
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - `comprobar` sale con SystemExit
                shot(f"{clave}_fallo")
                res["casos"][clave] = {"nombre": nombre, "resultado": "FALLO", "detalle": f"{type(exc).__name__}: {str(exc)[:600]}",
                                       "traza": traceback.format_exc()[-1500:]}

        # ------------------------------------------------------------ CAT
        def alta(nombre: str, ambito: str = "GASTO") -> str:
            t("nueva-categoria").click()
            t("nueva-categoria-pantalla").wait_for(timeout=15000)
            t("alta-nombre").fill(nombre)
            t(f"alta-ambito-{ambito}").click()
            t("alta-presupuesto-true").click()
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/v1/categorias"), timeout=20000) as resp:
                t("alta-crear").click()
            comprobar(resp.value.status == 200, f"alta {nombre}: HTTP {resp.value.status}")
            t("pantalla-categorias").wait_for(timeout=15000)
            c = cat_por_nombre(nombre)
            comprobar(c is not None and c["ambito"] == ambito and c["parent_id"] is None, f"alta {nombre}: {c}")
            return c["id"]

        def detalle(cid: str, padre: str | None = None) -> None:
            categorias()
            if padre:
                t(f"fila-{padre}").click()
                page.wait_for_timeout(400)
            t(f"fila-{cid}").click()
            t("detalle-categoria").wait_for(timeout=15000)

        def cat():
            r: dict = {}
            categorias()
            t("onboarding-desde-cero").click()
            shot("CAT_desde_cero")
            mascotas, vet, afic = alta("Mascotas"), alta("Veterinario"), alta("Aficiones")
            r["altas"] = {"mascotas": mascotas, "veterinario": vet, "aficiones": afic}
            # mover
            detalle(vet)
            t("accion-mover").click()
            t("selector-mover").wait_for(timeout=15000)
            t(f"cat-{mascotas}").click()
            page.wait_for_timeout(800)
            comprobar(cat_por_nombre("Veterinario")["parent_id"] == mascotas, "mover: padre")
            # renombrar
            detalle(vet, padre=mascotas)
            t("accion-renombrar").click()
            t("hoja-renombrar").wait_for()
            t("renombrar-nombre").fill("Clínica veterinaria")
            t("renombrar-guardar").click()
            page.wait_for_timeout(800)
            comprobar(cat_por_nombre("Clínica veterinaria") is not None, "renombrar")
            # ambito
            t("accion-ambito").click()
            t("hoja-ambito").wait_for()
            t("ambito-uso").wait_for(timeout=15000)
            t("ambito-nuevo-AMBOS").click()
            shot("CAT_ambito")
            t("ambito-confirmar").click()
            page.wait_for_timeout(800)
            comprobar(cat_por_nombre("Clínica veterinaria")["ambito"] == "AMBOS", "ámbito")
            # desactivar / reactivar
            t("accion-desactivar").click()
            t("hoja-desactivar").wait_for()
            t("desactivar-confirmar").click()
            page.wait_for_timeout(800)
            comprobar(cat_por_nombre("Clínica veterinaria")["enabled"] is False, "desactivar")
            t("accion-reactivar").wait_for(timeout=15000)
            t("accion-reactivar").click()
            t("hoja-reactivar").wait_for()
            t("reactivar-confirmar").click()
            page.wait_for_timeout(800)
            comprobar(cat_por_nombre("Clínica veterinaria")["enabled"] is True, "reactivar")
            shot("CAT_detalle_final")
            # orden de la raiz
            categorias()
            antes = [c["id"] for c in sorted((c for c in api(a.api, "GET", "/v1/categorias")["categorias"] if c["parent_id"] is None),
                                             key=lambda c: c["orden"])]
            t("editar-orden-abrir").click()
            t("editar-orden").wait_for(timeout=15000)
            t(f"orden-bajar-{antes[0]}").click()
            shot("CAT_orden")
            t("orden-guardar").click()
            page.wait_for_timeout(1000)
            despues = [c["id"] for c in sorted((c for c in api(a.api, "GET", "/v1/categorias")["categorias"] if c["parent_id"] is None),
                                               key=lambda c: c["orden"])]
            comprobar(despues == [antes[1], antes[0]] + antes[2:], f"orden {antes} -> {despues}")
            r["orden"] = {"antes": antes, "despues": despues}
            r["bd"] = [list(map(str, f)) for f in q("SELECT c.nombre, coalesce(p.nombre, ''), c.ambito, c.enabled, c.orden FROM "
                                                     "gapto.categorias_financieras c LEFT JOIN gapto.categorias_financieras p ON "
                                                     "p.id = c.parent_id ORDER BY 2, 5")]
            return r
        caso("CAT", "Ajustes › Categorías: alta, mover, renombrar, ámbito, desactivar/reactivar, orden", cat)

        # ------------------------------------------------------------ MAG
        def asociaciones(cid: str) -> list:
            return [list(map(str, f)) for f in q(
                "SELECT m.nombre, m.unidad_default, m.precision_decimales, m.enabled, a.obligatoria, a.orden, a.id "
                "FROM gapto.categoria_magnitudes a JOIN gapto.magnitudes m ON m.id = a.magnitud_id WHERE a.categoria_id = %s "
                "ORDER BY a.orden", (cid,))]

        def expandir() -> None:
            t("seccion-magnitudes").wait_for(timeout=15000)
            if t("magnitudes-anadir").count() == 0:
                t("magnitudes-cabecera").click()
            t("magnitudes-anadir").wait_for(timeout=15000)

        def nueva_magnitud(nombre: str, unidad: str, dec: int) -> None:
            expandir()
            t("magnitudes-anadir").click()
            t("selector-magnitudes").wait_for(timeout=15000)
            t("selmag-nueva").click()
            t("nueva-magnitud").wait_for()
            t("nuevamag-nombre").fill(nombre)
            t("nuevamag-unidad").fill(unidad)
            t(f"nuevamag-decimales-{dec}").click()
            t("nuevamag-obligatoria-false").click()
            t("nuevamag-crear").click()
            t("seccion-magnitudes").wait_for(timeout=15000)
            page.wait_for_timeout(800)

        def ficha(cid: str, nombre: str) -> None:
            expandir()
            fila = next(x for x in asociaciones(cid) if x[0] == nombre)
            t(f"magnitud-fila-{fila[6]}").click()
            t("ficha-magnitud").wait_for(timeout=15000)

        def mag():
            afic = cat_por_nombre("Aficiones")
            comprobar(afic is not None, "MAG: falta «Aficiones» (CAT)")
            cid = afic["id"]
            detalle(cid)
            t("seccion-magnitudes").wait_for(timeout=15000)
            nueva_magnitud("Horas", "h", 1)
            nueva_magnitud("Sesiones", "uds", 0)
            a1 = asociaciones(cid)
            comprobar([x[:6] for x in a1] == [["Horas", "h", "1", "True", "False", "0"], ["Sesiones", "uds", "0", "True", "False", "1"]], f"MAG altas {a1}")
            shot("MAG_seccion")
            ficha(cid, "Horas")
            t("ficha-obligatoriedad").click()
            t("hoja-obligatoriedad").wait_for()
            t("obligatoriedad-confirmar").click()
            page.wait_for_timeout(800)
            comprobar(next(x for x in asociaciones(cid) if x[0] == "Horas")[4] == "True", "MAG obligatoria")
            t("bloque-renombrar").wait_for(timeout=15000)
            t("bloque-renombrar").click()
            t("hoja-renombrar-magnitud").wait_for()
            t("renmag-nombre").fill("Horas dedicadas")
            t("renmag-guardar").click()
            page.wait_for_timeout(800)
            comprobar(any(x[0] == "Horas dedicadas" for x in asociaciones(cid)), "MAG renombrar")
            t("bloque-deshabilitar").click()
            t("hoja-deshabilitar").wait_for(timeout=15000)
            t("deshabilitar-confirmar").click()
            page.wait_for_timeout(600)
            if t("hoja-confirmar-deshabilitar").count():
                t("confirmar-deshabilitar").click()
                page.wait_for_timeout(600)
            comprobar(next(x for x in asociaciones(cid) if x[0] == "Horas dedicadas")[3] == "False", "MAG deshabilitar")
            shot("MAG_ficha_deshabilitada")
            t("bloque-rehabilitar").wait_for(timeout=15000)
            t("bloque-rehabilitar").click()
            t("hoja-rehabilitar").wait_for()
            t("rehabilitar-confirmar").click()
            page.wait_for_timeout(800)
            comprobar(next(x for x in asociaciones(cid) if x[0] == "Horas dedicadas")[3] == "True", "MAG rehabilitar")
            t("ficha-atras").click()
            expandir()
            antes = asociaciones(cid)
            t("magnitudes-editar-orden").click()
            t("orden-magnitudes").wait_for(timeout=15000)
            t(f"ordenmag-bajar-{antes[0][6]}").click()
            t("ordenmag-guardar").click()
            page.wait_for_timeout(1000)
            despues = asociaciones(cid)
            comprobar([x[0] for x in despues] == [antes[1][0], antes[0][0]], f"MAG orden {antes} -> {despues}")
            ficha(cid, "Sesiones")
            t("ficha-quitar").click()
            t("hoja-quitar").wait_for()
            t("quitar-confirmar").click()
            page.wait_for_timeout(800)
            final = asociaciones(cid)
            comprobar([x[0] for x in final] == ["Horas dedicadas"], f"MAG quitar {final}")
            catalogo = sorted(m["nombre"] for m in api(a.api, "GET", "/v1/magnitudes")["magnitudes"])
            return {"bd_final": final, "catalogo": catalogo}
        caso("MAG", "Magnitudes: nueva, obligatoria, renombrar, deshabilitar/rehabilitar, orden, quitar", mag)

        # ------------------------------------------------------------ CTX
        def ctx():
            ajustes("contextos")
            t("pantalla-contextos").wait_for(timeout=15000)
            t("ajctx-nuevo").click()
            t("ajctx-form").wait_for()
            t("ctx-nombre").fill("Viaje a Lisboa")
            page.locator('[data-testid^="ctx-tipo-"]:visible').first.click()
            t("ctx-guardar").click()
            page.wait_for_timeout(1000)
            fila = q("SELECT id::text, enabled FROM gapto.entidades WHERE tipo_entidad = 'CONTEXTO' AND nombre = 'Viaje a Lisboa'")
            comprobar(len(fila) == 1 and fila[0][1] is True, f"CTX alta {fila}")
            cid = fila[0][0]
            t(f"ajctx-fila-{cid}").click()
            t("ajctx-desactivar").click()
            page.wait_for_timeout(1000)
            comprobar(q("SELECT enabled FROM gapto.entidades WHERE id = %s", (cid,))[0][0] is False, "CTX desactivar")
            if t(f"ajctx-fila-{cid}").count():
                t(f"ajctx-fila-{cid}").click()
            t("ajctx-reactivar").wait_for(timeout=15000)
            t("ajctx-reactivar").click()
            page.wait_for_timeout(1000)
            comprobar(q("SELECT enabled FROM gapto.entidades WHERE id = %s", (cid,))[0][0] is True, "CTX reactivar")
            shot("CTX_lista")
            return {"contexto": cid}
        caso("CTX", "Ajustes › Contextos: alta, desactivar, reactivar", ctx)

        # ------------------------------------------------------------ REG
        def reg():
            r: dict = {}
            hechos = lambda: q("SELECT count(*) FROM gapto.hechos_financieros")[0][0]  # noqa: E731
            # salir con datos -> descartar
            antes = hechos()
            inicio()
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").fill("9")
            t("cancelar").click()
            t("confirmar-salida").wait_for(timeout=10000)
            shot("REG_confirmar_salida")
            t("descartar").click()
            t("accion-registrar").wait_for(timeout=15000)
            comprobar(hechos() == antes, "REG descartar: se persistio algo")
            # «Ayer»
            inicio()
            t("accion-registrar").click()
            t("tipo-GASTO").click()
            t("campo-importe").fill("12,30")
            t("fecha-ayer").click()
            t("campo-categoria").click()
            t("selector-sin-categoria").click()
            page.wait_for_timeout(400)
            t("presupuestable-true").click()
            t(f"cuenta-{tarjeta}").click()
            with page.expect_response(lambda x: x.request.method == "POST" and x.url.endswith("/v1/intenciones/gasto-pagado"), timeout=20000) as resp:
                t("registrar").click()
            comprobar(resp.value.status == 200, f"REG ayer: HTTP {resp.value.status}")
            h = resp.value.json()["hecho_id"]
            fecha = str(q("SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s", (h,))[0][0])
            comprobar(fecha == str(hoy - dt.timedelta(days=1)), f"REG ayer: fecha {fecha}")
            r["ayer"] = {"hecho": h, "fecha_hecho": fecha}
            # plantilla aplicada -> quitar
            tipos = api(a.api, "GET", "/v1/preferencias")["tipos"]
            pid, aid = str(uuid.uuid4()), str(uuid.uuid4())
            api(a.api, "POST", "/v1/plantillas", {"id": pid, "nombre": "Pienso", "tipo_hecho_id": tipos["GASTO"],
                                                  "cuenta_default_id": tarjeta, "presupuestable_default": True})
            api(a.api, "POST", "/v1/acciones-rapidas", {"id": aid, "plantilla_registro_id": pid, "nombre": "Pienso"})
            inicio()
            t(f"acceso-{aid}").click()
            t("chip-plantilla").wait_for(timeout=15000)
            shot("REG_plantilla_aplicada")
            t("quitar-plantilla").click()
            page.wait_for_timeout(500)
            comprobar(t("chip-plantilla").count() == 0, "REG quitar plantilla: el chip sigue")
            shot("REG_plantilla_quitada")
            r["plantilla"] = {"quitada": True, "origen_cuenta": t("origen-cuenta").inner_text() if t("origen-cuenta").count() else ""}
            return r
        caso("REG", "Registro: «Ayer», descartar al salir, quitar plantilla", reg)
        nav.close()

    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"G5_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    resumen = {k: v["resultado"] for k, v in res["casos"].items()}
    print(f"FIN {run}: {json.dumps(resumen, ensure_ascii=False)}")
    if any(v == "FALLO" for v in resumen.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
