# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_314_f06_t4_aj05_plazos_desenlaces.py
# Ruta: tests/api/test_314_f06_t4_aj05_plazos_desenlaces.py
# Descripcion: AJ-05 ampliado + R-C7-07 (F06 T4), Fase 4: casos 1-15 del diseno v0.2 §8, oraculos AJ-R2-04 (1-6),
#   replay por ruta con trabajo posterior al COMMIT (AJ-R2-06) y red de seguridad acotada (AJ-R2-03). Perfil BETA_LOCAL
#   (adenda 01, AJ-R3-02): A 8 s / B 40 s, lock_timeout A 3 s / B 0. Los tests que necesitan un plazo corto lo fijan
#   con monkeypatch (`aj.plazo`); el resto usa los valores del perfil. Recuentos exactos y estado HTTP en cada caso.
#   Las rutas de prueba (`/v1/_aj05/...`) se anaden SOLO a la app de cada test; no existen en el producto.
# Version: 0.1.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70… y adenda 01 24113472…)
# ============================================================
from __future__ import annotations

import json
import threading
import time
import uuid

import psycopg
import pytest
from fastapi.responses import JSONResponse

import aj05_helpers as aj
import f05_05_helpers as x
import f05_06_m2_helpers as m2
import vs01_api_helpers as h
from app.api import errores_http as eh
from app.api import middleware_peticion as mp
from app.api import registro_peticiones as regp
from app.core import peticion as pet
from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import UnidadDeTrabajo

GASTO = aj.GASTO


@pytest.fixture()
def t(tmp_path):
    owner, actor, _cli, cta, ahorro = x.entorno()
    prov = aj.Proveedor()
    reg = aj.registro(tmp_path / "registro")
    cli = aj.cliente(owner, proveedor=prov, registro=reg)
    return {"owner": owner, "actor": actor, "cta": cta, "ahorro": ahorro, "prov": prov, "reg": reg, "cli": cli}


def _post(cli, ruta, cuerpo, **cab):
    return cli.post(ruta, json=cuerpo, headers={**h.AUTH, **cab})


def _codigo(r):
    try:
        return r.json().get("codigo")
    except Exception:  # noqa: BLE001
        return None


def _estados(traza: dict) -> list[str]:
    return [i["estado"] for u in traza["unidades"] for i in u["intentos"]]


# ================================================================== casos 1 y 8: tiempo agotado antes del COMMIT
def test_c01a_c08_lock_timeout_antes_del_commit_no_guardado_y_reenvio_crea_una_vez(t):
    """55P03 del lock_timeout PROPIO (clase A, 3 s) esperando el advisory por raiz -> 503 TIEMPO_AGOTADO, cero filas;
    el reenvio de la MISMA intencion tras liberar crea una sola vez (caso 8)."""
    cuerpo = h.intencion(t["cta"])
    antes = aj.auditoria(t["owner"])
    with aj.bloquear_raiz(cuerpo["intencion_id"]):
        t0 = time.monotonic()
        r = _post(t["cli"], GASTO, cuerpo)
        dur = time.monotonic() - t0
    assert r.status_code == 503 and _codigo(r) == "TIEMPO_AGOTADO", r.text
    assert r.json()["reintentable"] is True
    assert 2.5 < dur < 6.0, dur
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 0 and aj.auditoria(t["owner"]) == antes
    tr = aj.ultima(t["reg"], GASTO)
    assert tr["desenlace"] == "NO_GUARDADO" and tr["persistencia"] == "NINGUNA", tr
    assert "ROLLBACK_CONFIRMADO" in _estados(tr) and any(i["sqlstate"] == "55P03" for u in tr["unidades"]
                                                         for i in u["intentos"]), tr
    r2 = _post(t["cli"], GASTO, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is False, r2.text
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 1


def test_c01b_statement_timeout_antes_del_commit_no_guardado(t, monkeypatch):
    """Plazo A de 2 s < lock_timeout de 3 s: salta el statement_timeout PROPIO (57014, con el deadline cumplido)."""
    aj.plazo(monkeypatch, a=2.0)
    cuerpo = h.intencion(t["cta"])
    with aj.bloquear_raiz(cuerpo["intencion_id"]):
        r = _post(t["cli"], GASTO, cuerpo)
    assert r.status_code == 503 and _codigo(r) == "TIEMPO_AGOTADO", r.text
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 0
    tr = aj.ultima(t["reg"], GASTO)
    assert any(i["sqlstate"] == "57014" for u in tr["unidades"] for i in u["intentos"]), tr
    assert tr["persistencia"] == "NINGUNA"


# ================================================================== caso 2: tiempo agotado en los triggers diferidos
def _trigger_diferido_lento(_n, c):
    """Antes del COMMIT: una tabla temporal con un constraint trigger DIFERIDO que duerme; el COMMIT lo ejecuta."""
    c.execute("CREATE TEMP TABLE IF NOT EXISTS aj05_lenta (x int)")
    c.execute("CREATE OR REPLACE FUNCTION pg_temp.aj05_dormir() RETURNS trigger LANGUAGE plpgsql AS "
              "$$ BEGIN PERFORM pg_sleep(30); RETURN NULL; END $$")
    c.execute("CREATE CONSTRAINT TRIGGER aj05_diferido AFTER INSERT ON aj05_lenta DEFERRABLE INITIALLY DEFERRED "
              "FOR EACH ROW EXECUTE FUNCTION pg_temp.aj05_dormir()")
    c.execute("INSERT INTO aj05_lenta VALUES (1)")


def _cardinalidad(owner, hecho_id) -> dict:
    q = {"hechos": "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
         "efectos": "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
         "conciliaciones": "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s"}
    return {k: h.leer(owner, v, (str(hecho_id),))[0][0] for k, v in q.items()}


def test_c02_b_c_transaction_timeout_corta_el_commit_diferido_indeterminado_y_se_reconcilia(t, monkeypatch):
    """Caso 2 sustituido por la adenda 02 §4 (AJ-R4-04), partes B y C en HTTP. El statement_timeout NO corta el COMMIT
    con triggers diferidos (parte A en test_315); lo corta el transaction_timeout de la sesion (25P04) -> COMMIT_INDETERMINADO
    -> 503 RESULTADO_NO_CONFIRMADO, nunca TIEMPO_AGOTADO ni BACKEND_NO_DISPONIBLE. Reconciliacion: el reenvio con la MISMA
    intencion y el mismo cuerpo deja la cardinalidad exacta de UNA operacion, sin duplicados ni auditoria del intento
    cortado."""
    aj.plazo(monkeypatch, a=2.0)
    cuerpo = h.intencion(t["cta"])
    audit_antes = aj.auditoria(t["owner"])
    t["prov"].antes_commit = _trigger_diferido_lento
    t0 = time.monotonic()
    r = _post(t["cli"], GASTO, cuerpo)
    dur = time.monotonic() - t0
    t["prov"].limpiar()
    tr = aj.ultima(t["reg"], GASTO)
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", json.dumps(tr["unidades"])
    intento = tr["unidades"][0]["intentos"][-1]
    assert intento["sqlstate"] == "25P04" and intento["estado"] == "COMMIT_INDETERMINADO", tr
    assert tr["persistencia"] == "COMMIT_INDETERMINADO" and tr["desenlace"] == "INDETERMINADO", tr
    assert dur <= 2.0 + pet.MARGEN_TRANSACTION_TIMEOUT_S + 1.0, dur
    # persistencia real del intento cortado: ninguna (la sesion murio antes del registro de COMMIT)
    assert _cardinalidad(t["owner"], cuerpo["intencion_id"]) == {"hechos": 0, "efectos": 0, "conciliaciones": 0}
    assert aj.auditoria(t["owner"]) == audit_antes
    audit_cortado = intento and tr["unidades"][0]["audit_request_id"]
    r2 = _post(t["cli"], GASTO, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is False, r2.text
    una = _cardinalidad(t["owner"], cuerpo["intencion_id"])
    assert una["hechos"] == 1 and una["efectos"] >= 1 and una["conciliaciones"] >= 1, una
    tras = aj.auditoria(t["owner"])
    r3 = _post(t["cli"], GASTO, cuerpo)
    assert r3.status_code == 200 and r3.json()["idempotente"] is True
    assert _cardinalidad(t["owner"], cuerpo["intencion_id"]) == una and aj.auditoria(t["owner"]) == tras
    assert h.leer(t["owner"], "SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (audit_cortado,))[0][0] == 0


# ================================================================== caso 3: corte durante el COMMIT
def test_c03a_o6_corte_tras_confirmar_es_indeterminado_y_el_reenvio_es_replay(t):
    cuerpo = h.intencion(t["cta"])
    t["prov"].despues_commit = aj.corte
    r = _post(t["cli"], GASTO, cuerpo)
    t["prov"].limpiar()
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    assert "no ha guardado" not in r.json()["mensaje"]
    tr = aj.ultima(t["reg"], GASTO)
    assert tr["persistencia"] == "COMMIT_INDETERMINADO" and tr["desenlace"] == "INDETERMINADO", tr
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 1          # el servidor SI confirmo
    antes = aj.auditoria(t["owner"])
    r2 = _post(t["cli"], GASTO, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True, r2.text
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 1 and aj.auditoria(t["owner"]) == antes


def test_c03b_corte_al_pedir_el_commit_sin_confirmar_es_indeterminado_y_el_reenvio_crea_una_vez(t):
    cuerpo = h.intencion(t["cta"])
    t["prov"].antes_commit = aj.corte
    r = _post(t["cli"], GASTO, cuerpo)
    t["prov"].limpiar()
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    assert aj.ultima(t["reg"], GASTO)["persistencia"] == "COMMIT_INDETERMINADO"
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 0
    r2 = _post(t["cli"], GASTO, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is False
    assert aj.hechos(t["owner"], cuerpo["intencion_id"]) == 1


# ================================================================== casos 4 y 5 + replay por ruta (AJ-R2-06)
def _v3(t):
    hid = x.gasto(t["cli"], t["cta"], importe="65.00", concepto="FONTANERO")
    m2.marcar_v3(t["owner"], hid)
    return hid


def _ed(cli, hid):
    r = cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _ruta_categoria(t):
    hid = _v3(t)
    e = _ed(t["cli"], hid)
    obras = x.categoria(t["owner"], "Obras")
    return f"/v1/hechos/{hid}/corregir-categoria", "/v1/hechos/{hecho_id}/corregir-categoria", {
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"], "motivo": "Categoria mal asignada en V3",
        "categoria_id": str(obras)}


def _ruta_pago(t):
    hid = x.gasto(t["cli"], t["cta"], importe="20.00")
    e = _ed(t["cli"], hid)
    return f"/v1/hechos/{hid}/corregir-pago", "/v1/hechos/{hecho_id}/corregir-pago", {
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
        "movimiento_row_version": e["movimientos"][0]["row_version"], "motivo": "Importe mal tecleado",
        "error_de_registro": True, "importe": "21.00"}


def _ruta_anular(t):
    hid = x.gasto(t["cli"], t["cta"], importe="30.00")
    e = _ed(t["cli"], hid)
    return f"/v1/hechos/{hid}/anular-duplicado", "/v1/hechos/{hecho_id}/anular-duplicado", {
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
        "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
        "motivo": "Lo registre dos veces", "duplicado_declarado": True}


def _ruta_transferencia(t):
    hid = x.transferencia(t["cli"], t["cta"], t["ahorro"], importe="500.00")
    e = _ed(t["cli"], hid)
    return f"/v1/transferencias/{hid}/corregir", "/v1/transferencias/{hecho_id}/corregir", {
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
        "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
        "motivo": "Importe mal tecleado", "error_de_registro": True, "importe": "450.00"}


RUTAS_EDICION = {"corregir-categoria": _ruta_categoria, "corregir-pago": _ruta_pago,
                 "anular-duplicado": _ruta_anular, "transferencia-corregir": _ruta_transferencia}


def _huella(owner):
    return h.leer(owner, "SELECT (SELECT count(*) FROM gapto.auditoria), (SELECT coalesce(sum(row_version), 0) "
                         "FROM gapto.hechos_financieros), (SELECT coalesce(sum(row_version), 0) FROM "
                         "gapto.movimientos_tesoreria), (SELECT count(*) FROM gapto.hecho_efectos)")[0]


@pytest.mark.parametrize("nombre", list(RUTAS_EDICION))
def test_c05_o3_o6_replay_por_ruta_tras_fallo_de_la_segunda_lectura(t, nombre):
    """AJ-R2-06: la escritura confirma (unidad 1); la segunda lectura `estado` falla -> 503 RESULTADO_NO_CONFIRMADO con
    traza ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA; el reenvio con la MISMA intencion y el mismo cuerpo devuelve el
    resultado funcional correcto (replay) sin ninguna escritura nueva."""
    ruta, plantilla, cuerpo = RUTAS_EDICION[nombre](t)
    base = t["prov"].aperturas
    t["prov"].al_abrir = lambda n: aj.corte() if n == base + 2 else None
    r = _post(t["cli"], ruta, cuerpo)
    t["prov"].limpiar()
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    tr = aj.ultima(t["reg"], plantilla)
    assert tr["persistencia"] == "ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA", tr
    assert [u["solo_lectura"] for u in tr["unidades"]] == [False, True], tr
    assert tr["unidades"][0]["intentos"][-1]["estado"] == "COMMIT_CONFIRMADO", tr
    tras_escritura = _huella(t["owner"])
    r2 = _post(t["cli"], ruta, cuerpo)
    assert r2.status_code == 200, r2.text
    j = r2.json()
    assert j["idempotente"] is True and j["intencion_id"] == cuerpo["intencion_id"], j
    assert _huella(t["owner"]) == tras_escritura


def test_c04_plazo_agotado_tras_escritura_confirmada_nunca_es_no_guardado(t, monkeypatch):
    aj.plazo(monkeypatch, a=2.5)
    ruta, plantilla, cuerpo = _ruta_categoria(t)
    t["prov"].despues_commit = lambda _n, _c: aj.dormir_hasta_restante(0.3)
    r = _post(t["cli"], ruta, cuerpo)
    t["prov"].limpiar()
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    tr = aj.ultima(t["reg"], plantilla)
    assert tr["persistencia"] == "ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA", tr
    assert len(tr["unidades"]) == 2 and tr["unidades"][1]["intentos"] == [], tr   # la lectura ni empezo
    assert tr["anomalias"] == [], tr   # lo decide el manejador global, no la red de seguridad del middleware
    r2 = _post(t["cli"], ruta, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True


# ================================================================== caso 6: reenvio con el primero en curso (B)
def _lab_hip(n, reg):
    from test_294_f06_01h_revision_tipo import LabRev

    class LabN(LabRev):
        def bloque(self, **cambios):
            cambios.setdefault("numero_cuotas", n)
            return super().bloque(**cambios)

    lab = LabN()
    lab.cli = aj.cliente(lab.owner, registro=reg, reloj="2026-10-10T12:00:00")
    return lab


def _en_paralelo(f1, f2, retardo=0.8):
    salida = {}

    def correr(k, f):
        salida[k] = f()
    a = threading.Thread(target=correr, args=("a", f1))
    b = threading.Thread(target=correr, args=("b", f2))
    a.start()
    time.sleep(retardo)
    b.start()
    a.join(120)
    b.join(120)
    return salida["a"], salida["b"]


def test_c06a_reenvio_de_la_compra_de_360_con_el_primero_en_curso(t):
    from test_289_f06_01h_alta_en_compra import LabHip, huella

    class Lab360(LabHip):
        def bloque(self, **cambios):
            cambios.setdefault("numero_cuotas", 360)
            return super().bloque(**cambios)

    lab = Lab360()
    otro = aj.cliente(lab.owner, registro=t["reg"], reloj="2026-10-10T12:00:00")
    lab.cli = aj.cliente(lab.owner, registro=t["reg"], reloj="2026-10-10T12:00:00")
    cuerpo = lab.peticion_hip(hip=lab.bloque())
    ra, rb = _en_paralelo(lambda: lab.compra(cuerpo), lambda: lab.compra(cuerpo, cli=otro))
    assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)
    assert sorted([ra.json()["idempotente"], rb.json()["idempotente"]]) == [False, True]
    f = uuid.UUID(ra.json()["hipoteca"]["financiacion_id"])
    assert lab.sql("SELECT count(*) FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s", (f,))[0][0] == 360
    assert lab.sql("SELECT count(*) FROM gapto.previsiones WHERE entidad_id = %s", (f,))[0][0] == 360
    assert lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (cuerpo["intencion_id"],))[0][0] == 1
    antes = huella()
    r3 = lab.compra(cuerpo)
    assert r3.status_code == 200 and r3.json()["idempotente"] is True and huella() == antes
    clases = {e["clase"] for e in aj.terminadas(t["reg"], "/v1/propiedades/{propiedad_id}/compra")}
    assert clases == {"B"}


def test_c06b_reenvio_de_la_revision_de_360_con_el_primero_en_curso(t):
    lab = _lab_hip(360, t["reg"])
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    otro = aj.cliente(lab.owner, registro=t["reg"], reloj="2026-10-10T12:00:00")
    cuerpo = lab.cuerpo_rev(desde="2041-04-01", tasa="3.5")
    ra, rb = _en_paralelo(lambda: lab.revisar(cuerpo),
                          lambda: otro.post(f"/v1/hipotecas/{lab.f}/revision", json=cuerpo, headers=h.AUTH))
    assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)
    assert sorted([ra.json()["idempotente"], rb.json()["idempotente"]]) == [False, True]
    assert len(lab.versiones()) == 2
    clases = {e["clase"] for e in aj.terminadas(t["reg"], "/v1/hipotecas/{financiacion_id}/revision")}
    assert clases == {"B"}


# ================================================================== casos 7 y 9
def test_c07_reenvio_tras_confirmar_es_replay(t):
    cuerpo = h.intencion(t["cta"])
    assert _post(t["cli"], GASTO, cuerpo).status_code == 200
    antes = aj.auditoria(t["owner"])
    r = _post(t["cli"], GASTO, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert aj.auditoria(t["owner"]) == antes and aj.hechos(t["owner"], cuerpo["intencion_id"]) == 1


def test_c09_misma_intencion_con_otro_contenido_rechazo_vigente(t):
    cuerpo = h.intencion(t["cta"])
    assert _post(t["cli"], GASTO, cuerpo).status_code == 200
    r = _post(t["cli"], GASTO, {**cuerpo, "concepto": "Otra cosa"})
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", r.text
    assert aj.ultima(t["reg"], GASTO)["desenlace"] == "RECHAZO"


# ================================================================== casos 10 y 11: presupuesto unico
def _ctx(owner):
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def test_c10_ningun_intento_empieza_sin_plazo_y_el_deadline_no_se_reinicia(t):
    """40P01 en cada intento: el backoff consume el MISMO presupuesto; ningun intento empieza con < 0,5 s; el deadline
    es el mismo en todos los intentos y en la segunda unidad (no se reinicia ni por intento ni por unidad)."""
    vistos: list[tuple[float, float]] = []

    @__import__("contextlib").contextmanager
    def prov():
        e = pet.actual()
        vistos.append((e.restante(), e.deadline))
        raise psycopg.errors.DeadlockDetected("deadlock simulado")
        yield  # pragma: no cover

    estado, token = pet.iniciar("POST", "/v1/intenciones/gasto-pagado")
    try:
        estado.deadline = estado.t0 + 2.0
        u = UnidadDeTrabajo(prov, max_intentos=50, espera_inicial_s=0.2)
        with pytest.raises(pet.PlazoAgotado) as e1:
            u.ejecutar(_ctx(t["owner"]), lambda s: None, nombre="u1")
        assert e1.value.motivo == "SIN_PLAZO_PARA_INTENTO"
        n1 = len(vistos)
        with pytest.raises(pet.PlazoAgotado):
            u.ejecutar(_ctx(t["owner"]), lambda s: None, nombre="u2")
    finally:
        pet.terminar(token)
    assert n1 >= 2
    assert all(r >= pet.MINIMO_PARA_INTENTO_S for r, _ in vistos), vistos
    assert {d for _, d in vistos} == {estado.deadline}
    assert [u.nombre for u in estado.unidades] == ["u1", "u2"]
    assert estado.persistencia() is pet.Persistencia.NINGUNA


def test_c11_conexion_y_esperas_no_superan_el_plazo_mas_el_margen(t, monkeypatch):
    aj.plazo(monkeypatch, a=2.0)

    def lento(_n):
        time.sleep(0.9)
        raise psycopg.errors.DeadlockDetected("deadlock simulado")
    t["prov"].al_abrir = lento
    t0 = time.monotonic()
    r = _post(t["cli"], GASTO, h.intencion(t["cta"]))
    dur = time.monotonic() - t0
    t["prov"].limpiar()
    assert r.status_code == 503 and _codigo(r) == "TIEMPO_AGOTADO", r.text
    assert dur <= 2.0 + pet.MARGEN_TRANSACTION_TIMEOUT_S, dur


def test_c12_respuesta_posterior_al_deadline_devuelve_el_resultado_real(t, monkeypatch):
    aj.plazo(monkeypatch, a=1.5)
    cuerpo = h.intencion(t["cta"])
    t["prov"].despues_commit = lambda _n, _c: time.sleep(1.8)
    r = _post(t["cli"], GASTO, cuerpo)
    t["prov"].limpiar()
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    tr = aj.ultima(t["reg"], GASTO)
    assert tr["fuera_de_plazo"] is True and tr["desenlace"] == "CONFIRMADO", tr


# ================================================================== caso 13 (parte en suite): el plazo no es ErrorMotor
def test_c13_plazo_agotado_no_es_error_motor_y_lo_traduce_un_manejador_global(t, monkeypatch):
    from app.core.errores import ErrorMotor

    assert not issubclass(pet.PlazoAgotado, ErrorMotor)
    original = UnidadDeTrabajo.ejecutar_con_traza

    def agotar(self, contexto, operacion, *, nombre="operacion", solo_lectura=False):
        raise pet.PlazoAgotado("SIN_PLAZO_PARA_INTENTO", unidad=nombre)
    monkeypatch.setattr(UnidadDeTrabajo, "ejecutar_con_traza", agotar)
    ruta, _p, cuerpo = "/v1/hechos/{}/corregir-categoria".format(uuid.uuid4()), None, {
        "intencion_id": str(uuid.uuid4()), "row_version": 1, "motivo": "x", "categoria_id": str(uuid.uuid4())}
    for metodo, url, c in (("POST", GASTO, h.intencion(t["cta"])), ("POST", ruta, cuerpo),
                           ("GET", "/v1/previsiones/pendientes", None)):
        r = t["cli"].request(metodo, url, json=c, headers=h.AUTH)
        assert r.status_code == 503 and _codigo(r) == "TIEMPO_AGOTADO", (url, r.text)
    monkeypatch.setattr(UnidadDeTrabajo, "ejecutar_con_traza", original)


# ================================================================== oraculos AJ-R2-04 y red de seguridad
def _app_con_rutas(t, monkeypatch=None):
    from fastapi.testclient import TestClient

    from app.api.app import create_app

    cfg = h.configuracion(t["owner"])
    app = create_app(cfg, reloj=x.reloj(aj.RELOJ), proveedor_conexion=t["prov"], registro=t["reg"])
    u = UnidadDeTrabajo(t["prov"], rol_runtime=cfg.rol_runtime)
    ctx = lambda: ContextoOperacion.de_usuario(t["owner"], request_id=uuid.uuid4())  # noqa: E731

    @app.post("/v1/_aj05/bloqueo-sin-dml")
    def bloqueo_sin_dml():
        u.ejecutar(ctx(), lambda s: s.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR UPDATE", (t["cta"],)),
                   nombre="AJ05 bloqueo")
        raise psycopg.OperationalError("conexion perdida (simulada)")

    @app.post("/v1/_aj05/lectura-sin-xid")
    def lectura_sin_xid():
        u.ejecutar(ctx(), lambda s: s.uno("SELECT 1"), nombre="AJ05 lectura")
        raise psycopg.OperationalError("conexion perdida (simulada)")

    @app.post("/v1/_aj05/solo-lectura-escribe")
    def solo_lectura_escribe():
        u.ejecutar(ctx(), lambda s: s.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR UPDATE", (t["cta"],)),
                   nombre="AJ05 solo lectura", solo_lectura=True)
        return {"ok": True}

    @app.post("/v1/_aj05/confirma-y-rechaza")
    def confirma_y_rechaza():
        u.ejecutar(ctx(), lambda s: s.uno("SELECT 1"), nombre="AJ05 confirma")
        return JSONResponse({"codigo": "VERSION_DESFASADA", "mensaje": "x", "reintentable": False}, status_code=409)

    @app.post("/v1/_aj05/confirma-y-dice-no-guardado")
    def confirma_y_dice_no_guardado():
        u.ejecutar(ctx(), lambda s: s.uno("SELECT 1"), nombre="AJ05 confirma")
        status, cuerpo = eh.tiempo_agotado()
        return JSONResponse(cuerpo, status_code=status)

    @app.post("/v1/_aj05/confirma-y-lanza-rechazo")
    def confirma_y_lanza_rechazo():
        from app.core.errores import CodigoError, ErrorMotor
        u.ejecutar(ctx(), lambda s: s.uno("SELECT 1"), nombre="AJ05 confirma")
        raise ErrorMotor(CodigoError.VERSION_DESFASADA, "rechazo funcional tras un COMMIT (prueba)")

    @app.post("/v1/_aj05/falla")
    def falla():
        raise RuntimeError("password=secreto-aj05 CONCEPTO-SECRETO-AJ05 postgresql://u:p@host/db")

    @app.get("/v1/_aj05/ok")
    def ok():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_o1_xid_sin_dml_falso_positivo_conservador_documentado(t):
    """AJ-R2-04 (1): una unidad no declarada solo lectura que solo bloquea (FOR UPDATE, XID asignado, sin DML) cuenta
    como potencialmente persistente: un error posterior es RESULTADO_NO_CONFIRMADO (falso positivo conservador)."""
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/bloqueo-sin-dml", headers=h.AUTH)
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    tr = aj.ultima(t["reg"], "/v1/_aj05/bloqueo-sin-dml")
    assert tr["unidades"][0]["intentos"][0]["xid_auxiliar"] is True
    assert tr["persistencia"] == "ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA"


def test_o1b_el_xid_no_es_el_criterio(t):
    """Sin XID asignado (un SELECT), la unidad potencialmente persistente confirmada sigue contando: el criterio es el
    seguimiento explicito, no el XID."""
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/lectura-sin-xid", headers=h.AUTH)
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    tr = aj.ultima(t["reg"], "/v1/_aj05/lectura-sin-xid")
    assert tr["unidades"][0]["intentos"][0]["xid_auxiliar"] is False
    assert tr["unidades"][0]["intentos"][0]["estado"] == "COMMIT_CONFIRMADO"


def test_solo_lectura_es_read_only_desde_la_primera_sentencia(t):
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/solo-lectura-escribe", headers=h.AUTH)
    assert r.status_code >= 500, r.text
    tr = aj.ultima(t["reg"], "/v1/_aj05/solo-lectura-escribe")
    assert tr["unidades"][0]["intentos"][0]["sqlstate"] == "25006", tr
    assert tr["persistencia"] == "NINGUNA"


def test_o2_rechazo_funcional_tras_commit_se_conserva(t, monkeypatch):
    """AJ-R2-04 (2) y AJ-R2-03: la red de seguridad NUNCA convierte un 4xx. En la lista cerrada: sin anomalia; fuera de
    ella: anomalia registrada y el rechazo se devuelve tal cual."""
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/confirma-y-rechaza", headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA", r.text
    tr = aj.ultima(t["reg"], "/v1/_aj05/confirma-y-rechaza")
    assert tr["anomalias"] == ["RECHAZO_TRAS_COMMIT_NO_PREVISTO:VERSION_DESFASADA"], tr
    monkeypatch.setattr(mp, "RECHAZOS_TRAS_COMMIT_PREVISTOS",
                        mp.RECHAZOS_TRAS_COMMIT_PREVISTOS | {("POST", "/v1/_aj05/confirma-y-rechaza", 409)})
    r = cli.post("/v1/_aj05/confirma-y-rechaza", headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    assert aj.ultima(t["reg"], "/v1/_aj05/confirma-y-rechaza")["anomalias"] == []


def test_o2b_lista_cerrada_del_inventario_completa():
    """Las 23 rutas de la lista cerrada de la Fase 1 (INVENTARIO_FRONTERAS §3), sin anadidos."""
    assert len(mp.RECHAZOS_TRAS_COMMIT_PREVISTOS) == 23
    assert all(m == "POST" and s in (409, 422) for m, _r, s in mp.RECHAZOS_TRAS_COMMIT_PREVISTOS)


def test_red_de_seguridad_sustituye_solo_un_no_guardado_falso(t):
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/confirma-y-dice-no-guardado", headers=h.AUTH)
    assert r.status_code == 503 and _codigo(r) == "RESULTADO_NO_CONFIRMADO", r.text
    assert int(r.headers["content-length"]) == len(r.content)
    tr = aj.ultima(t["reg"], "/v1/_aj05/confirma-y-dice-no-guardado")
    assert tr["anomalias"] == ["RED_DE_SEGURIDAD:TIEMPO_AGOTADO"], tr


# ================================================================== caso 15: registro de peticiones
def test_c15a_recibida_y_terminada_con_identidades_separadas(t):
    intento, cuerpo = str(uuid.uuid4()), h.intencion(t["cta"])
    r = _post(t["cli"], GASTO, cuerpo, **{"X-Gapto-Intento-Id": intento, "X-Gapto-Intencion-Id": cuerpo["intencion_id"]})
    assert r.status_code == 200
    ev = aj.eventos(t["reg"])
    rec = [e for e in ev if e["evento"] == "RECIBIDA"][-1]
    ter = aj.ultima(t["reg"], GASTO)
    assert "ruta" not in rec and rec["clase_provisional"] == "A"
    assert rec["http_request_id"] == ter["http_request_id"]
    assert ter["client_attempt_id"] == intento and ter["intencion_id"] == cuerpo["intencion_id"]
    assert len({ter["http_request_id"], ter["client_attempt_id"], ter["intencion_id"]}) == 3
    audit = ter["unidades"][0]["audit_request_id"]                          # el request_id vigente de la unidad
    assert audit not in (ter["http_request_id"], intento)
    assert h.leer(t["owner"], "SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (audit,))[0][0] > 0
    assert ter["desenlace"] == "CONFIRMADO" and ter["estado_http"] == 200
    for k in ("conexion_ms", "transaccion_ms", "commit_ms"):
        assert ter["unidades"][0]["intentos"][0][k] is not None
    assert ter["duracion_ms"] > 0


def test_c15b_cabeceras_ausentes_o_mal_formadas_y_ruta_no_resuelta(t):
    r = t["cli"].get("/v1/no-existe-aj05", headers={**h.AUTH, "X-Gapto-Intento-Id": "no-es-un-uuid"})
    assert r.status_code == 404
    ter = aj.terminadas(t["reg"])[-1]
    assert ter["ruta"] == "NO_RESUELTA" and ter["client_attempt_id"] == "INVALIDO" and ter["intencion_id"] is None


def test_c15c_excepcion_del_backend_registra_terminada_sin_mensaje(t):
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/falla", headers=h.AUTH)
    assert r.status_code == 500 and _codigo(r) == "INTERNO"
    ter = aj.ultima(t["reg"], "/v1/_aj05/falla")
    assert ter["excepcion"] == "RuntimeError" and ter["desenlace"] == "EXCEPCION"


def test_c15d_logger_no_disponible_al_arrancar_no_arranca(tmp_path, monkeypatch):
    fichero = tmp_path / "soy_un_fichero"
    fichero.write_text("x")
    with pytest.raises(regp.RegistroNoDisponible):
        regp.RegistroPeticiones.abrir(fichero)
    with pytest.raises(regp.RegistroNoDisponible):
        regp.desde_entorno({})
    raiz_repo = __import__("pathlib").Path(regp.__file__).resolve().parents[3]
    with pytest.raises(regp.RegistroNoDisponible):
        regp.desde_entorno({"GAPTO_LOG_DIR": str(raiz_repo / "logs_aj05")})
    assert not (raiz_repo / "logs_aj05").exists()
    # y la factoria de arranque lo exige (fail-closed)
    from app.api import app as adaptador
    for k, v in {"GAPTO_ENV": "development", "GAPTO_DATABASE_URL": h.dsn(), "GAPTO_DEV_OWNER_USER_ID": str(uuid.uuid4()),
                 "GAPTO_DEV_TOKEN": h.TOKEN, "GAPTO_DEV_DB_ALLOWLIST": h.nombre_base()}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GAPTO_LOG_DIR", raising=False)
    with pytest.raises(regp.RegistroNoDisponible):
        adaptador.create_app_desde_entorno()
    monkeypatch.setenv("GAPTO_LOG_DIR", str(tmp_path / "logs_ok"))
    assert adaptador.create_app_desde_entorno() is not None
    assert list((tmp_path / "logs_ok").glob("peticiones-*.jsonl"))


def _peticiones_fijas(cli, cta):
    """Respuestas comparables con y sin fallo del registro: OK, rechazo 4xx, 5xx de excepcion y ruta inexistente."""
    cuerpo = h.intencion(cta, intencion_id="2b0f0b8e-1c55-4b0c-9a49-5f0000a05a05")
    salida = []
    for metodo, ruta, c in (("GET", "/v1/_aj05/ok", None), ("POST", GASTO, {**cuerpo, "importe": "x"}),
                            ("POST", "/v1/_aj05/falla", None), ("GET", "/v1/no-existe-aj05", None)):
        r = cli.request(metodo, ruta, json=c, headers=h.AUTH)
        cab = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "content-length")}
        salida.append((r.status_code, r.content, cab))
    return salida


def test_o4_o5_c15e_el_logger_que_falla_no_cambia_ninguna_respuesta(t, tmp_path, monkeypatch):
    """AJ-R2-04 (4) y (5): con el registro fallando en cada escritura (tambien durante una excepcion del backend), el
    codigo, el cuerpo y las cabeceras funcionales son identicos; se cuenta el fallo y la consola recibe un texto fijo."""
    base = _peticiones_fijas(_app_con_rutas(t), t["cta"])
    avisos: list[str] = []
    roto = aj.registro(tmp_path / "roto", consola=avisos.append)

    def romper(_evento):
        raise OSError("disco lleno (simulado) password=secreto-aj05")
    monkeypatch.setattr(roto, "_escribir_linea", romper)
    t2 = {**t, "reg": roto}
    assert _peticiones_fijas(_app_con_rutas(t2), t["cta"]) == base
    assert roto.fallos >= 8 and set(avisos) == {regp.AVISO_CONSOLA}


def test_c15f_barrido_de_secretos_e_importes(t):
    cli = _app_con_rutas(t)
    cuerpo = h.intencion(t["cta"], importe="98765.43", concepto="CONCEPTO-SECRETO-AJ05",
                         financiacion=h.propuesta_self_100("98765.43"))
    _post(cli, GASTO, cuerpo)
    cli.post("/v1/_aj05/falla", headers=h.AUTH)
    texto = t["reg"].fichero_actual().read_text(encoding="utf-8")
    for prohibido in (h.TOKEN, "Bearer", "98765", "CONCEPTO-SECRETO", "secreto-aj05", "postgresql://", h.dsn(),
                      "password"):
        assert prohibido not in texto, prohibido


def test_c15g_rotacion_diaria_y_retencion(tmp_path):
    import datetime as dt

    hoy = [dt.date(2026, 11, 22)]
    reg = regp.RegistroPeticiones.abrir(tmp_path, hoy=lambda: hoy[0])
    viejo = tmp_path / "peticiones-20261001.jsonl"
    reciente = tmp_path / "peticiones-20261101.jsonl"
    ajeno = tmp_path / "otro.jsonl"
    for f in (viejo, reciente, ajeno):
        f.write_text("{}\n")
    hoy[0] = dt.date(2026, 11, 23)
    reg.escribir({"evento": "X"})
    assert reg.fichero_actual().name == "peticiones-20261123.jsonl"
    assert not viejo.exists() and reciente.exists() and ajeno.exists()
    assert json.loads(reg.fichero_actual().read_text(encoding="utf-8").splitlines()[-1])["evento"] == "X"


def test_o2c_rechazo_de_error_motor_tras_commit_no_lo_convierte_el_manejador(t):
    cli = _app_con_rutas(t)
    r = cli.post("/v1/_aj05/confirma-y-lanza-rechazo", headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA", r.text


# ================================================================== limites por clase y procedencia del error
def _proveedor_con_sesion(*sets):
    import contextlib

    @contextlib.contextmanager
    def prov():
        with psycopg.connect(h.dsn()) as c:
            c.autocommit = True
            for s in sets:
                c.execute(s)
            c.autocommit = False
            yield c
    return prov


@pytest.mark.parametrize("metodo,ruta,lock", [("POST", "/v1/intenciones/gasto-pagado", "3s"),
                                              ("POST", "/v1/hipotecas/x/revision", "0"),
                                              ("POST", "/v1/propiedades/x/compra", "0")])
def test_c16_lock_timeout_por_clase_explicito_sin_herencia_de_sesion(t, metodo, ruta, lock):
    """A: lock_timeout 3 s; B: 0 EXPLICITO aunque la sesion (o el rol) traiga otro valor; statement_timeout propio."""
    u = UnidadDeTrabajo(_proveedor_con_sesion("SET lock_timeout = '17s'", "SET statement_timeout = '99s'"))
    estado, token = pet.iniciar(metodo, ruta)
    try:
        vistos = u.ejecutar(_ctx(t["owner"]), lambda s: (s.uno("SHOW lock_timeout")[0],
                                                         s.uno("SHOW statement_timeout")[0]), nombre="c16")
    finally:
        pet.terminar(token)
    assert vistos[0] == lock and vistos[1] not in ("99s", "0"), vistos
    assert estado.clase == ("A" if lock == "3s" else "B")


def test_c17_57014_de_una_cancelacion_externa_no_es_plazo_ni_se_reintenta(t):
    u = UnidadDeTrabajo(aj.Proveedor())

    def op(s):
        pid = s.uno("SELECT pg_backend_pid()")[0]

        def cancelar():
            time.sleep(0.5)
            with psycopg.connect(h.dsn(), autocommit=True) as c:
                c.execute("SELECT pg_cancel_backend(%s)", (pid,))
        threading.Thread(target=cancelar, daemon=True).start()
        s.uno("SELECT pg_sleep(5)")

    estado, token = pet.iniciar("POST", "/v1/intenciones/gasto-pagado")
    try:
        with pytest.raises(BaseException) as e:
            u.ejecutar(_ctx(t["owner"]), op, nombre="c17")
    finally:
        pet.terminar(token)
    assert not isinstance(e.value, pet.PlazoAgotado), e.value
    intentos = estado.unidades[0].intentos
    assert len(intentos) == 1 and intentos[0].sqlstate == "57014", intentos
    assert intentos[0].estado is pet.EstadoUnidad.ROLLBACK_CONFIRMADO


def test_c18_55p03_de_otro_origen_en_clase_b_no_es_plazo(t):
    u = UnidadDeTrabajo(aj.Proveedor())
    estado, token = pet.iniciar("POST", "/v1/hipotecas/x/revision")
    try:
        with psycopg.connect(h.dsn()) as retiene:
            retiene.execute("SELECT id FROM gapto.cuentas WHERE id = %s FOR UPDATE", (t["cta"],))
            with pytest.raises(BaseException) as e:
                u.ejecutar(_ctx(t["owner"]), lambda s: s.uno(
                    "SELECT id FROM gapto.cuentas WHERE id = %s FOR UPDATE NOWAIT", (t["cta"],)), nombre="c18")
            retiene.rollback()
    finally:
        pet.terminar(token)
    assert not isinstance(e.value, pet.PlazoAgotado), e.value
    assert estado.unidades[0].intentos[0].sqlstate == "55P03"
