# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_06_m5b_resueltas.py
# Ruta: scripts/dev/e2e_f05_06_m5b_resueltas.py (helpers de e2e_f05_06_m5_swipe.py)
# Descripcion: E2E web de F05-06 M5-B v1.1 · «Resueltas este mes»
#   (HANDOFF_M5BM1 §6: una OMITIDA por swipe no llegaba a «Reabrir»).
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear) y la
#   siembra del dia (siembra_previsiones_m5.sembrar). Escenario:
#     R1  «Pendientes»: la luz en «Vencidas»;
#     R2  «No hubo» por la accion accesible del swipe (la misma funcion que el
#         gesto; RN-web no reproduce el swipe): aviso y, a los >= 4,5 s, UN
#         solo POST …/omitir; oraculo: OMITIDA y ningun hecho nuevo;
#     R3  al final, «Resueltas este mes» PLEGADO con su recuento; al
#         desplegarlo, la luz con «No hubo · <dia>»;
#     R4  tocar la fila abre el detalle -> «Más › Reabrir» con motivo;
#         oraculo: ABIERTA;
#     R5  «Atrás»: la luz vuelve a «Vencidas» y sale de «Resueltas».
#   Capturas 393x852 @3x (claro y oscuro) y manifest JSON con el estado.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-06 M5-B v1.1)
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
from siembra_previsiones_m5 import sembrar  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


def estado(dsn: str, owner: str, pid: str) -> str:
    return _sql(dsn, owner, "gapto_runtime", "SELECT estado FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]


def n_hechos(dsn: str, owner: str) -> int:
    return _sql(dsn, owner, "gapto_runtime", "SELECT count(*) FROM gapto.hechos_financieros", ())[0][0]


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
    ids = {r["fixture"].split(".", 1)[1]: r["uuid"] for r in siembra if r["fixture"].startswith("prevision.")}
    luz = ids["luz"]
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "prevision": luz, "pasos": {}}
    capturas: list[str] = []
    consola: list[str] = []
    posts: list[tuple[float, str]] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: posts.append((dt.datetime.now().timestamp(), r.url)) if r.method == "POST" else None)
        page.goto(a.web)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"M5B_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def accion_accesible(testid: str, nombre: str) -> None:
            hecho = page.evaluate("""([tid, nombre]) => {
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

        def pasos() -> None:
            # ------------------------------------------------------------ R1 Pendientes
            t("accion-registrar").wait_for(timeout=30000)
            t("campana-pendientes").click()
            t(f"pendiente-{luz}").wait_for(timeout=15000)
            comprobar(t("pendientes-vencidas").locator(f'[data-testid="pendiente-{luz}"]').count() == 1, "R1: luz en Vencidas")
            n_res0 = int(t("resueltas-recuento").inner_text()) if t("resueltas-recuento").count() else 0
            page.wait_for_timeout(1500)  # capacidades de hoy leidas con la lista
            shot("R1_pendientes")
            res["pasos"]["R1"] = {"resueltas_antes": n_res0}

            # ------------------------------------------------------------ R2 «No hubo» por el swipe
            hechos0, n0 = n_hechos(dsn, owner), len(posts)
            accion_accesible(f"pendiente-{luz}", "derecha")
            t(f"aviso-rapida-{luz}-texto").wait_for(timeout=5000)
            inicio = dt.datetime.now().timestamp()
            aviso = t(f"aviso-rapida-{luz}-texto").inner_text()
            shot("R2_no_hubo_aviso")
            t(f"aviso-rapida-{luz}").wait_for(state="detached", timeout=15000)
            page.wait_for_timeout(1500)
            envios = [(s, u) for s, u in posts[n0:] if u.endswith(f"/v1/previsiones/{luz}/omitir")]
            comprobar(len(envios) == 1, f"R2: {len(envios)} envios")
            espera = round(envios[0][0] - inicio, 2)
            comprobar(espera >= 4.5, f"R2: el POST salio a los {espera} s")
            comprobar(estado(dsn, owner, luz) == "OMITIDA" and n_hechos(dsn, owner) == hechos0, "R2: OMITIDA sin hecho")
            res["pasos"]["R2"] = {"aviso": aviso, "espera_s": espera, "estado": "OMITIDA"}

            # ------------------------------------------------------------ R3 «Resueltas este mes», plegado
            t("resueltas-cabecera").wait_for(timeout=15000)
            n_res = int(t("resueltas-recuento").inner_text())
            comprobar(n_res == n_res0 + 1, f"R3: recuento {n_res0} -> {n_res}")
            comprobar(t(f"resuelta-{luz}").count() == 0, "R3: plegado por defecto")
            comprobar(t("pendientes-vencidas").locator(f'[data-testid="pendiente-{luz}"]').count() == 0, "R3: fuera de Vencidas")
            t("resueltas-cabecera").scroll_into_view_if_needed()
            shot("R3_resueltas_plegado")
            t("resueltas-cabecera").click()
            t(f"resuelta-{luz}").wait_for(timeout=15000)
            linea = t(f"resuelta-{luz}-linea").inner_text()
            comprobar(linea.startswith(f"No hubo · {hoy.day} "), f"R3: linea {linea}")
            t(f"resuelta-{luz}").scroll_into_view_if_needed()
            shot("R3_resueltas_desplegado")
            oscuro("R3_resueltas_desplegado")
            res["pasos"]["R3"] = {"recuento": n_res, "linea": linea}

            # ------------------------------------------------------------ R4 detalle -> «Más › Reabrir»
            t(f"resuelta-{luz}").click()
            t("prevision-mas").wait_for(timeout=15000)
            t("prevision-mas").click()
            t("mas-reabrir").click()
            t("hoja-reabrir").wait_for(timeout=15000)
            t("reabrir-sugerencia-0").click()
            shot("R4_reabrir")
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/v1/previsiones/{luz}/reabrir"),
                                      timeout=20000) as resp:
                t("reabrir-confirmar").click()
            comprobar(resp.value.status == 200, f"R4: HTTP {resp.value.status}")
            t("detalle-hecho").wait_for(timeout=15000)
            comprobar(estado(dsn, owner, luz) == "ABIERTA", "R4: ABIERTA")
            res["pasos"]["R4"] = {"estado": "ABIERTA"}

            # ------------------------------------------------------------ R5 vuelve a «Vencidas»
            t("prevision-detalle-atras").click()
            t(f"pendiente-{luz}").wait_for(timeout=15000)
            comprobar(t("pendientes-vencidas").locator(f'[data-testid="pendiente-{luz}"]').count() == 1, "R5: luz en Vencidas")
            n_fin = int(t("resueltas-recuento").inner_text()) if t("resueltas-recuento").count() else 0
            comprobar(n_fin == n_res0, f"R5: recuento {n_fin}")
            shot("R5_vencidas")
            res["pasos"]["R5"] = {"resueltas": n_fin}

        try:
            pasos()
        except BaseException:
            page.screenshot(path=str(salida / f"M5B_{run}_FALLO.png"))
            (salida / f"M5B_{run}_FALLO.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
            raise
        nav.close()

    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"M5B_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
