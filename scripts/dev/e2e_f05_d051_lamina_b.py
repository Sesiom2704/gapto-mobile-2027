# ============================================================
# GAPTO MOBILE 2027
# Fichero: e2e_f05_d051_lamina_b.py
# Ruta: scripts/dev/e2e_f05_d051_lamina_b.py
# Descripcion: E2E web de la lamina B (F05-D051 paso 8; D-F0507L-03, sobre el
#   contrato HTTP Q4/Q4-H2 de F05 §65.4): una posicion saldada no es
#   «Sin determinar».
#   *** EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS *** (corroboracion de
#   desarrollo, no certificacion de proveedor).
#
#   Exige una base dev local RECIEN RECREADA (bootstrap_dev_db --recrear, sin
#   --seed-categorias). Preparacion SOLO por vias legitimas del motor (mismo
#   patron que tests/api/test_216):
#     - cuenta «Cuenta nómina» como gapto_owner (igual que e2e_j2j3); terceros
#       «La Tagliatella» (EMPRESA), «Simón», «Tania» y «Marta» (PERSONA) por
#       la API publica;
#     - cena 120,00 € repartida a cuartos (30/30/30/30), pagada con la nomina,
#       los tres «Sí, me debe»: OP-22 (HechosCompuestosService) con la MISMA
#       composicion del adaptador (componer_gasto_compartido, con sus advisory
#       y locks y el writer de actor), y las posiciones de Simón y Marta dadas
#       de alta con apertura y seguimiento desconocidos (realidad valida del
#       motor, F04-D055 A3/A4; Tania con apertura 0, la del alta ordinaria);
#     - Marta: cobro de 30,00 € por HTTP (con saldo desconocido sigue ACTIVA)
#       y cierre declarativo con PosicionesService.cerrar_posicion (no hay
#       ruta HTTP de cierre; no se crea ninguna). Sin SQL de escritura salvo la
#       cuenta.
#   Escenario desde la UI:
#     B1  Día a día › detalle › «Pendiente con Tania» › «Registrar cobro» de
#         los 30,00 €: el exito dice «0,00 € · Saldado. Ya no queda nada
#         pendiente.» sin «Importe inicial desconocido» ni «Sin determinar»;
#     B2  «Pendiente con Simón»: su posicion dice «Sin determinar»;
#     B3  «Corregir reparto» de la cena (claro y oscuro): Simón «Te debe ·
#         pendiente Sin determinar»; Tania «Te debe · 0,00 € · Saldado»; Marta
#         «Te debe · 0,00 € · Saldado» y debajo «Importe inicial desconocido»;
#         ninguna saldada dice «Sin determinar»; etiqueta accesible
#         (aria-label en web) igual al texto.
#   Oraculo fisico (solo lectura): estado y saldo_apertura de las tres filas
#   (Simón ACTIVA/NULL, Tania CERRADA/0, Marta CERRADA/NULL) y terna HTTP
#   (saldo, estado, apertura_indeterminada) del reparto.
#   Capturas 393x852 @3x y manifest JSON.
#   Requiere (ya levantados): API en --api con CORS para --web, cliente web en
#   --web (o --dist), GAPTO_DATABASE_URL (base LOCAL), GAPTO_DEV_OWNER_USER_ID y
#   GAPTO_DEV_TOKEN (nunca se imprime).
# Version: 0.1.0 (F05-D051 paso 8; lamina B D-F0507L-03)
# ============================================================

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import json
import os
import pathlib
import sys
import uuid
from zoneinfo import ZoneInfo

import psycopg
from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ / "backend"))
from e2e_j2j3 import _exigir_local, _sql, api, comprobar, crear_cuenta, exigir_base_recreada, servidor_web  # noqa: E402

ETIQUETA = "EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS"


# ------------------------------------------------------------------ preparacion por el motor
def _unidad(dsn: str):
    from app.core.unidad_trabajo import UnidadDeTrabajo

    @contextlib.contextmanager
    def _abrir():
        with psycopg.connect(dsn) as conexion:
            yield conexion

    return UnidadDeTrabajo(_abrir, rol_runtime="gapto_runtime")


def _ctx(owner: str):
    from app.core.contexto import ContextoOperacion

    return ContextoOperacion.de_usuario(uuid.UUID(owner), request_id=uuid.uuid4())


def registrar_con_aperturas_desconocidas(dsn: str, owner: str, cuerpo: dict, desconocidas: set[str]) -> str:
    """OP-22 con la composicion del adaptador (advisory, locks, writer de actor
    y componer_gasto_compartido); las posiciones de `desconocidas` nacen con
    apertura y seguimiento desconocidos (F04-D055 A3/A4), las demas con el alta
    ordinaria (apertura 0)."""
    from app.actores import servicio as actores
    from app.api import ejecucion_reparto as rep
    from app.api.dto_reparto import IntencionGastoCompartido, PagadoConCuenta
    from app.api.ejecucion_registro import bloquear_cuentas, tomar_inversiones
    from app.api.traductor_gasto_pagado import leer_actor_self
    from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
    from app.repositories import compuesto_repository as repo_comp
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    intencion = IntencionGastoCompartido(**cuerpo)
    ctx = _ctx(owner)

    def operacion(sesion):
        repo_comp.tomar_advisory_raiz(sesion, intencion.intencion_id)
        tomar_inversiones(sesion)
        if isinstance(intencion.pagado_por, PagadoConCuenta):
            bloquear_cuentas(sesion, intencion.pagado_por.cuenta_id)
        yo = leer_actor_self(sesion)
        actores_de = {}
        for t in sorted(rep._personas(intencion), key=str):
            actores.validar_tercero_persona(sesion, t)
            actores_de[t] = actores.actor_de_tercero(sesion, t)
        datos = rep.componer_gasto_compartido(intencion, yo, actores_de)
        sin_apertura = {actores_de[uuid.UUID(t)] for t in desconocidas}
        datos = dataclasses.replace(datos, posiciones=[
            dataclasses.replace(p, saldo_apertura=None, fecha_inicio_seguimiento=None)
            if p.contraparte_actor_id in sin_apertura else p for p in datos.posiciones])
        op22 = HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)
        return op22.registrar_hecho_compuesto(ctx, datos)

    r = _unidad(dsn).ejecutar(ctx, operacion, nombre="F05-D051 paso 8 preparacion (OP-22, aperturas desconocidas)")
    return str(r.hecho_id)


def cerrar_declarativo(dsn: str, owner: str, entidad: str, motivo: str, fecha: dt.date) -> tuple[str, bool]:
    """Cierre declarado F04-D055 A3 (PosicionesService.cerrar_posicion)."""
    from app.core.modelos_posicion import DatosCierre
    from app.services.posiciones_service import PosicionesService

    version = _sql(dsn, owner, "gapto_runtime", "SELECT row_version FROM gapto.entidades WHERE id = %s", (entidad,))[0][0]
    r = PosicionesService(_unidad(dsn)).cerrar_posicion(
        _ctx(owner), entidad_id=uuid.UUID(entidad), entidad_row_version_esperada=version,
        cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=fecha))
    return r.estado, r.apertura_indeterminada


def filas_posicion(dsn: str, owner: str, hecho: str) -> dict:
    """(estado, saldo_apertura) de cada posicion del hecho por persona; solo lectura."""
    return {n: [e, None if a is None else str(a)] for n, e, a in _sql(dsn, owner, "gapto_runtime",
        "SELECT t.nombre, p.estado, p.saldo_apertura FROM gapto.hecho_entidades v "
        "JOIN gapto.derechos_obligaciones_financieras p ON p.entidad_id = v.entidad_id "
        "JOIN gapto.actores_financieros a ON a.id = p.contraparte_actor_id JOIN gapto.terceros t ON t.id = a.tercero_id "
        "WHERE v.hecho_id = %s", (hecho,))}


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
    tagli, simon, tania, marta = (str(uuid.uuid4()) for _ in range(4))
    for tid, nom, nat in ((tagli, "La Tagliatella", "EMPRESA"), (simon, "Simón", "PERSONA"),
                          (tania, "Tania", "PERSONA"), (marta, "Marta", "PERSONA")):
        api(a.api, "POST", "/v1/terceros", {"id": tid, "nombre": nom, "naturaleza": nat})
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "120.00", "moneda": "EUR", "fecha_hecho": str(hoy),
              "presupuestable": True, "categoria": {"estado": "SIN_CATEGORIA"}, "tercero_id": tagli,
              "nota": "Cena con amigos", "pagado_por": {"tipo": "CUENTA", "cuenta_id": nomina},
              "reparto": {"modo": "REPARTIR", "mi_parte": "30.00", "partes": [
                  {"tercero_id": x, "importe": "30.00", "me_debe": "SI"} for x in (simon, tania, marta)]}}
    cena = registrar_con_aperturas_desconocidas(dsn, owner, cuerpo, {simon, marta})
    reparto = api(a.api, "GET", f"/v1/hechos/{cena}/reparto")
    parte = {p["tercero_id"]: p for p in reparto["partes"] if p["tercero_id"]}
    terna = lambda p: [p["posicion"]["saldo"], p["posicion"]["estado"], p["posicion"]["apertura_indeterminada"]]  # noqa: E731
    comprobar([terna(parte[x]) for x in (simon, tania, marta)] == [[None, "ACTIVA", False], ["30.00", "ACTIVA", False],
                                                                 [None, "ACTIVA", False]], f"prep: {reparto}")
    e_marta = parte[marta]["posicion"]["entidad_id"]
    r = api(a.api, "POST", f"/v1/posiciones/{e_marta}/cobro",
            {"intencion_id": str(uuid.uuid4()), "importe": "30.00", "cuenta_id": nomina, "fecha": str(hoy)})
    comprobar([r["saldo"], r["estado"], r["apertura_indeterminada"]] == [None, "ACTIVA", False], f"prep Marta cobro: {r}")
    comprobar(cerrar_declarativo(dsn, owner, e_marta, "LIQUIDADA", hoy) == ("CERRADA", True), "prep: cierre de Marta")

    capturas: list[str] = []
    res: dict = {"etiqueta": ETIQUETA, "run_id": run, "hoy": str(hoy), "hecho_cena": cena,
                 "terceros": {"tagliatella": tagli, "simon": simon, "tania": tania, "marta": marta},
                 "prep_bd": filas_posicion(dsn, owner, cena)}
    comprobar(res["prep_bd"] == {"Simón": ["ACTIVA", None], "Tania": ["ACTIVA", "0.0000"], "Marta": ["CERRADA", None]},
              f"prep: {res['prep_bd']}")
    consola: list[str] = []

    with servidor_web(a.dist, a.web), sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, locale="es-ES", timezone_id="Europe/Madrid")
        page.on("console", lambda m: consola.append(m.text) if m.type == "error" else None)
        t = lambda i: page.locator(f'[data-testid="{i}"]:visible')  # noqa: E731

        def shot(nombre: str) -> None:
            f = salida / f"LB_{run}_{nombre}_WEB-VIEWPORT-393x852.png"
            page.wait_for_timeout(400)
            page.screenshot(path=str(f))
            capturas.append(f.name)

        def oscuro(nombre: str) -> None:
            page.emulate_media(color_scheme="dark")
            shot(f"{nombre}_oscuro")
            page.emulate_media(color_scheme="light")

        def detalle() -> None:
            page.goto(a.web)
            t("accion-registrar").wait_for(timeout=30000)
            t("tab-DIA").click()
            t("actividad-periodo").click()
            t("periodo-ESTE_MES").click()
            t(f"fila-{cena}").wait_for(timeout=20000)
            t(f"fila-{cena}").click()
            t(f"detalle-pendiente-{tania}").wait_for(timeout=15000)

        # ------------------------------------------------------------ B1 cobro de Tania -> saldada
        detalle()
        shot("B0_detalle_cena")
        t(f"detalle-pendiente-{tania}").click()
        t("pendiente-lista-te-debe").wait_for(timeout=15000)
        e_tania = parte[tania]["posicion"]["entidad_id"]
        t(f"posicion-{e_tania}").click()
        t("posicion-cobrar").click()
        t("accion-cobro").wait_for()
        comprobar(t("accion-importe").input_value() == "30,00", "B1: importe propuesto")
        t(f"accion-cuenta-{nomina}").wait_for(timeout=15000)
        t(f"accion-cuenta-{nomina}").click()
        with page.expect_response(lambda x: x.request.method == "POST" and x.url.endswith(f"/v1/posiciones/{e_tania}/cobro"), timeout=20000) as resp:
            t("accion-enviar").click()
        r1 = resp.value.json()
        comprobar(resp.value.status == 200 and [r1["saldo"], r1["estado"], r1["apertura_indeterminada"]] == ["0.00", "CERRADA", False], f"B1: {r1}")
        t("posicion-exito").wait_for()
        res["B1_exito"] = t("posicion-exito").inner_text()
        comprobar(t("posicion-exito-saldo").inner_text() == "0,00 € · Saldado. Ya no queda nada pendiente.", f"B1: {res['B1_exito']}")
        comprobar(t("posicion-exito-inicial").count() == 0, "B1: «Importe inicial desconocido» con apertura conocida")
        comprobar("Sin determinar" not in res["B1_exito"], "B1: «Sin determinar» en una saldada")
        comprobar(t("posicion-exito-estado").get_attribute("aria-label") == "0,00 € · Saldado. Ya no queda nada pendiente.", "B1: aria-label")
        shot("B1_exito_tania_saldado")
        oscuro("B1_exito_tania_saldado")

        # ------------------------------------------------------------ B2 Simón pendiente desconocida
        detalle()
        t(f"detalle-pendiente-{simon}").click()
        t("pendiente-lista-te-debe").wait_for(timeout=15000)
        e_simon = parte[simon]["posicion"]["entidad_id"]
        res["B2_pendiente_simon"] = t("pendiente-con").inner_text()
        comprobar(t(f"posicion-saldo-{e_simon}").inner_text() == "Sin determinar", f"B2: {res['B2_pendiente_simon']}")
        comprobar("Importe inicial desconocido" not in res["B2_pendiente_simon"], "B2: indicador en una ACTIVA")
        shot("B2_pendiente_con_simon")

        # ------------------------------------------------------------ B3 Corregir reparto: los tres estados
        detalle()
        t("detalle-corregir-reparto").click()
        t("corregir-form").wait_for(timeout=15000)
        ids = {p["tercero_id"]: p["atribucion_id"] for p in api(a.api, "GET", f"/v1/hechos/{cena}/reparto")["partes"] if p["tercero_id"]}
        linea = lambda x: t(f"corregir-posicion-saldo-{ids[x]}").inner_text()  # noqa: E731
        res["B3_lineas"] = {"Simón": linea(simon), "Tania": linea(tania), "Marta": linea(marta)}
        comprobar(res["B3_lineas"] == {"Simón": "Te debe · pendiente Sin determinar", "Tania": "Te debe · 0,00 € · Saldado",
                                       "Marta": "Te debe · 0,00 € · Saldado"}, f"B3: {res['B3_lineas']}")
        comprobar(t(f"corregir-posicion-inicial-{ids[simon]}").count() == 0 and t(f"corregir-posicion-inicial-{ids[tania]}").count() == 0,
                  "B3: «Importe inicial desconocido» fuera de Marta")
        comprobar(t(f"corregir-posicion-inicial-{ids[marta]}").inner_text() == "Importe inicial desconocido", "B3: Marta sin indicador")
        for x in (tania, marta):
            comprobar("Sin determinar" not in t(f"corregir-posicion-{ids[x]}").inner_text(), f"B3: «Sin determinar» en una saldada ({x})")
        res["B3_aria"] = {n: t(f"corregir-posicion-{ids[x]}").get_attribute("aria-label") for n, x in (("Simón", simon), ("Tania", tania), ("Marta", marta))}
        comprobar(res["B3_aria"] == {"Simón": "Te debe · pendiente Sin determinar", "Tania": "Te debe · 0,00 € · Saldado",
                                     "Marta": "Te debe · 0,00 € · Saldado. Importe inicial desconocido"}, f"B3: {res['B3_aria']}")
        t(f"corregir-parte-{ids[marta]}").scroll_into_view_if_needed()
        shot("B3_corregir_reparto_tres_estados")
        oscuro("B3_corregir_reparto_tres_estados")
        nav.close()

    # ---------------------------------------------------------------- oraculo final
    res["final_bd"] = filas_posicion(dsn, owner, cena)
    comprobar(res["final_bd"] == {"Simón": ["ACTIVA", None], "Tania": ["CERRADA", "0.0000"], "Marta": ["CERRADA", None]},
              f"final: {res['final_bd']}")
    final = {p["tercero_id"]: p for p in api(a.api, "GET", f"/v1/hechos/{cena}/reparto")["partes"] if p["tercero_id"]}
    res["final_http"] = {n: terna(final[x]) for n, x in (("Simón", simon), ("Tania", tania), ("Marta", marta))}
    comprobar(res["final_http"] == {"Simón": [None, "ACTIVA", False], "Tania": ["0.00", "CERRADA", False],
                                    "Marta": ["0.00", "CERRADA", True]}, f"final: {res['final_http']}")
    res["capturas"] = capturas
    res["errores_consola"] = consola
    (salida / f"LB_{run}_manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comprobar(not consola, f"errores de consola: {consola[:3]}")
    print(f"PASS {run}: {len(capturas)} capturas")


if __name__ == "__main__":
    main()
