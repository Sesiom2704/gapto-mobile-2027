# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_171_f05_02_integracion_reg01.py
# Ruta: tests/api/test_171_f05_02_integracion_reg01.py
# Descripcion: Integracion de las preferencias de registro en REG-01 (F05-02
#   B2; F05-D026 §41.3/§41.4, E1/E2; F05-D027 §42.6/§42.7). Extremo a extremo
#   por HTTP contra la API de integracion (propuesta -> intencion sellada ->
#   ejecucion), sin tocar la ejecucion ni el traductor:
#   - CC-02-3 (v): la cuenta preferida deja de ser elegible entre la propuesta
#     y el envio -> CUENTA_DESCONOCIDA, sin sustitucion ni hecho (tampoco en
#     el reintento con el mismo UUID).
#   - CC-02-4: cambiar, desactivar o reactivar la preferencia despues de pedir
#     la propuesta no altera la intencion enviada; el reintento con el mismo
#     UUID es idempotente aunque la preferencia haya cambiado; la financiacion
#     propuesta sobre la cuenta preferida se revalida
#     (PROPUESTA_FINANCIACION_OBSOLETA).
#   - CC-02-6: «Guardar como preferencia» es una escritura independiente: un
#     fallo inyectado en su escritura deja el hecho intacto y sin preferencia;
#     el reintento con el MISMO UUID la crea (R06).
#   - §42.7 (R-B1-03): la propuesta con una categoria no elegible para GASTO
#     responde CATEGORIA_NO_ELEGIBLE y nunca una propuesta, aunque exista una
#     preferencia con esa clave.
#   - AJ-B1-09: con una unica cuenta y en otra moneda no hay propuesta de
#     cuenta (cuentas-pago la lista: el fallback anterior del cliente la habria
#     propuesto).
#   Datos sinteticos como gapto_owner; el adaptador corre como gapto_runtime.
#
#   v0.2.0 (F05-02 B3, AJ-B2-05): alta aditiva. La propuesta con categoria no
#   elegible conserva codigo y status pero lleva un mensaje de lectura (sin
#   «no se ha guardado nada»); el rechazo de la intencion conserva el suyo.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h
from app.api import errores_http as eh
from app.api.app import MENSAJE_PROPUESTA_NO_ELEGIBLE

URL = "/v1/intenciones/gasto-pagado"
CAMBIO = dt.date(2026, 9, 20)  # desde esta fecha la cuenta pasa a 50/50


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="Tarjeta")
    b = ph.cuenta(owner, actor, nombre="Efectivo")
    cat = ph.categoria(owner, "Supermercado")
    return owner, actor, cli, a, b, cat


def _intencion_desde_propuesta(propuesta: dict, cat: uuid.UUID, **cambios) -> dict:
    """Lo que sella el cliente: los valores PROPUESTOS que el usuario no toca."""
    cuerpo = h.intencion(uuid.UUID(propuesta["cuenta"]["valor"]), categoria={
        "estado": "CATEGORIA", "categoria_id": str(cat), "magnitudes": []})
    if propuesta["presupuestable"] is not None:
        cuerpo["presupuestable"] = propuesta["presupuestable"]["valor"]
    cuerpo.update(cambios)
    return cuerpo


def _sellado(owner: uuid.UUID, hid: uuid.UUID) -> tuple:
    """(cuenta del movimiento, presupuestable del hecho) materializados."""
    cuenta = h.leer(owner, "SELECT m.cuenta_id FROM gapto.hecho_movimientos_tesoreria hm "
                           "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
                           "WHERE hm.hecho_id=%s", (hid,))
    presupuestable = h.leer(owner, "SELECT presupuestable FROM gapto.hechos_financieros WHERE id=%s", (hid,))
    return [f[0] for f in cuenta], [f[0] for f in presupuestable]


def _foto_hecho(owner: uuid.UUID, hid: uuid.UUID) -> dict:
    """Contenido completo del agregado del hecho (filas como JSON)."""
    consultas = {
        "hecho": "SELECT row_to_json(x)::text FROM gapto.hechos_financieros x WHERE id=%s",
        "efectos": "SELECT row_to_json(x)::text FROM gapto.hecho_efectos x WHERE hecho_id=%s ORDER BY id",
        "conciliaciones": "SELECT row_to_json(x)::text FROM gapto.hecho_movimientos_tesoreria x WHERE hecho_id=%s "
                          "ORDER BY id",
        "aportaciones": "SELECT row_to_json(x)::text FROM gapto.hecho_aportaciones_pago x WHERE hecho_id=%s "
                        "ORDER BY id",
        "auditoria": "SELECT count(*)::text FROM gapto.auditoria WHERE registro_id=%s",
    }
    return {k: h.leer(owner, q, (hid,)) for k, q in consultas.items()}


def _n_hechos(owner: uuid.UUID) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros")[0][0]


def _propuesta(cli, cat=None) -> dict:
    r = ph.propuesta_http(cli, cat)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ CC-02-3 (v)
def test_preferida_deja_de_ser_elegible_antes_del_envio_rechazo_sin_sustitucion(t):
    owner, _, cli, a, b, cat = t
    pid, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    assert r.status_code == 200, r.text
    p = _propuesta(cli, cat)
    assert p["cuenta"] == {"valor": str(a), "origen": {"capa": "PREFERENCIA", "preferencia_id": str(pid)}}
    cuerpo = _intencion_desde_propuesta(p, cat)
    ph.deshabilitar_cuenta(owner, a)  # entre la carga y la confirmacion
    hid = uuid.UUID(cuerpo["intencion_id"])
    for _ in range(2):  # el reintento con el mismo UUID tampoco sustituye
        r = cli.post(URL, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 422 and r.json()["codigo"] == "CUENTA_DESCONOCIDA", r.text
    assert fh.huella_agregado(owner, hid) == {"hechos": 0, "efectos": 0, "conciliaciones": 0, "aportaciones": 0,
                                              "auditoria": 0}
    assert _n_hechos(owner) == 0  # ni con la preferida ni con la otra cuenta elegible
    assert h.leer(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id=%s", (b,))[0][0] == 0


# ------------------------------------------------------------------ CC-02-4
def _cambiar_preferencia(cli, pid: uuid.UUID, cambio: str, b: uuid.UUID, cat: uuid.UUID) -> None:
    """row_version conocida por el escenario: 1 tras el alta; 2 tras desactivar."""
    if cambio == "editar":
        r = ph.editar(cli, pid, 1, categoria_id=cat, cuenta_default_id=b, presupuestable_default=False)
    elif cambio == "desactivar":
        r = ph.desactivar(cli, pid, 1)
    else:
        r = ph.reactivar(cli, pid, 2)
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text


@pytest.mark.parametrize("cambio", ["editar", "desactivar", "reactivar"])
def test_cambio_de_preferencia_tras_la_propuesta_no_altera_la_intencion(t, cambio):
    owner, _, cli, a, b, cat = t
    pid, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    assert r.status_code == 200, r.text
    if cambio == "reactivar":
        assert ph.desactivar(cli, pid, 1).status_code == 200
        p = _propuesta(cli, cat)
        assert p == {"cuenta": None, "presupuestable": None}  # dos cuentas, sin preferencia vigente
        # Sin propuesta, el usuario elige explicitamente (lo explicito se sella tal cual).
        cuerpo = h.intencion(a, presupuestable=False, categoria={
            "estado": "CATEGORIA", "categoria_id": str(cat), "magnitudes": []})
        esperado = ([a], [False])
    else:
        p = _propuesta(cli, cat)
        cuerpo = _intencion_desde_propuesta(p, cat)
        esperado = ([a], [True])
    _cambiar_preferencia(cli, pid, cambio, b, cat)
    if cambio != "desactivar":  # la propuesta vigente ya es otra: el envio no la relee
        assert _propuesta(cli, cat) != p
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert r.json()["hecho_id"] == str(hid)  # el UUID sellado no cambia
    assert _sellado(owner, hid) == esperado


def test_reintento_mismo_uuid_idempotente_aunque_la_preferencia_cambie(t):
    owner, _, cli, a, b, cat = t
    pid, _ = ph.alta(cli, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    cuerpo = _intencion_desde_propuesta(_propuesta(cli, cat), cat)
    primero = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert primero.status_code == 200 and primero.json()["idempotente"] is False
    hid = uuid.UUID(cuerpo["intencion_id"])
    foto = _foto_hecho(owner, hid)
    # El cliente no vio la respuesta (INDETERMINADO) y entretanto la preferencia cambia.
    assert ph.editar(cli, pid, 1, categoria_id=cat, cuenta_default_id=b, presupuestable_default=False).status_code == 200
    for _ in range(2):
        r = cli.post(URL, json=cuerpo, headers=h.AUTH)  # mismo payload sellado: no se recalcula
        assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
        assert r.json()["hecho_id"] == str(hid)
    assert _foto_hecho(owner, hid) == foto
    assert _sellado(owner, hid) == ([a], [True])
    assert _n_hechos(owner) == 1


def _cambiar_a_compartida(owner, cuenta, actor, otro) -> None:
    with psycopg.connect(h.dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cur.execute("UPDATE gapto.cuenta_participaciones SET vigente_hasta = %s "
                        "WHERE cuenta_id = %s AND vigente_hasta IS NULL", (CAMBIO - dt.timedelta(days=1), cuenta))
            for x in (actor, otro):
                cur.execute("INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, vigente_desde) "
                            "VALUES (%s, %s, 50, %s)", (cuenta, x, CAMBIO))


def test_financiacion_sobre_la_cuenta_preferida_se_revalida(t):
    owner, actor, cli, a, _, cat = t
    otro = h.crear_actor_tercero(owner)
    ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    p = _propuesta(cli, cat)
    assert p["cuenta"]["valor"] == str(a)
    cuentas = cli.get("/v1/vs01/cuentas-pago", params={"fecha": ph.FECHA.isoformat()}, headers=h.AUTH).json()["cuentas"]
    assert {c["cuenta_id"]: c["propuesta_financiacion"] for c in cuentas}[str(a)] == "SELF_100"
    cuerpo = _intencion_desde_propuesta(p, cat)  # financiacion self 100 % sellada sobre la preferida
    assert cuerpo["financiacion"]["estado"] == "PROPUESTA_ACEPTADA"
    _cambiar_a_compartida(owner, a, actor, otro)
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA", r.text
    assert fh.huella_agregado(owner, uuid.UUID(cuerpo["intencion_id"]))["hechos"] == 0
    # La preferencia sigue proponiendo la cuenta; la financiacion visible pasa a no determinada.
    assert _propuesta(cli, cat)["cuenta"]["valor"] == str(a)
    cuentas = cli.get("/v1/vs01/cuentas-pago", params={"fecha": ph.FECHA.isoformat()}, headers=h.AUTH).json()["cuentas"]
    assert {c["cuenta_id"]: c["propuesta_financiacion"] for c in cuentas}[str(a)] == "NO_DETERMINADA"


# ------------------------------------------------------------------ CC-02-6: guardar desacoplado
def test_fallo_inyectado_al_guardar_la_preferencia_no_afecta_al_hecho(t, monkeypatch):
    owner, _, cli, a, b, cat = t
    cuerpo = h.intencion(b, categoria={"estado": "CATEGORIA", "categoria_id": str(cat), "magnitudes": []})
    assert cli.post(URL, json=cuerpo, headers=h.AUTH).status_code == 200
    hid = uuid.UUID(cuerpo["intencion_id"])
    foto = _foto_hecho(owner, hid)

    from app.preferencias import repositorio

    def _falla(*_a, **_k):
        raise RuntimeError("fallo inyectado en la escritura de la preferencia")

    monkeypatch.setattr(repositorio, "insertar_preferencia", _falla)
    pid = uuid.uuid4()  # UUID generado al abrir la tarjeta
    _, r = ph.alta(cli, pid, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 500 and r.json()["codigo"] == "INTERNO", r.text  # el cliente lo trata como INDETERMINADO
    assert ph.n_preferencias(owner) == 0
    assert _foto_hecho(owner, hid) == foto
    monkeypatch.undo()
    # Reintentar (R06) con el MISMO UUID: la crea; repetirlo es idempotente.
    _, r = ph.alta(cli, pid, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    _, r = ph.alta(cli, pid, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert ph.n_preferencias(owner) == 1
    assert _foto_hecho(owner, hid) == foto
    assert _n_hechos(owner) == 1


def test_rechazo_del_guardado_no_afecta_al_hecho(t):
    """Conflicto (R07): el alta contradictoria se rechaza sin tocar el hecho."""
    owner, _, cli, a, b, cat = t
    ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    cuerpo = h.intencion(b, categoria={"estado": "CATEGORIA", "categoria_id": str(cat), "magnitudes": []})
    assert cli.post(URL, json=cuerpo, headers=h.AUTH).status_code == 200
    hid = uuid.UUID(cuerpo["intencion_id"])
    foto = _foto_hecho(owner, hid)
    _, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO"
    assert _foto_hecho(owner, hid) == foto


# ------------------------------------------------------------------ §42.7: categoria no elegible
@pytest.mark.parametrize("caso", ["deshabilitada", "ingreso", "otro_owner", "inexistente"])
def test_propuesta_con_categoria_no_elegible_responde_codigo_y_nunca_propuesta(t, caso):
    owner, _, cli, a, _, _ = t
    if caso == "deshabilitada":
        cat = ph.categoria(owner, "Vieja", enabled=False)
    elif caso == "ingreso":
        cat = ph.categoria(owner, "Nomina", ambito="INGRESO")
    elif caso == "otro_owner":
        otro, _ = h.crear_tenant()
        cat = ph.categoria(otro, "Ajena")
    else:
        cat = uuid.uuid4()
    if caso in ("deshabilitada", "ingreso"):
        # Aunque exista una preferencia con esa clave (escrita fuera del writer), no hay propuesta.
        ph.insertar_sql(owner, categoria_id=cat, cuenta=a, presupuestable=True)
    r = ph.propuesta_http(cli, cat)
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE" and r.json()["reintentable"] is False
    assert "cuenta" not in r.json() and "presupuestable" not in r.json()


@pytest.mark.parametrize("ambito", ["GASTO", "AMBOS"])
def test_propuesta_con_categoria_elegible_para_gasto(t, ambito):
    owner, _, cli, a, _, _ = t
    cat = ph.categoria(owner, f"Cat {ambito}", ambito=ambito)
    pid = ph.insertar_sql(owner, categoria_id=cat, cuenta=a)
    assert _propuesta(cli, cat)["cuenta"] == {"valor": str(a), "origen": {"capa": "PREFERENCIA",
                                                                          "preferencia_id": str(pid)}}


def test_propuesta_no_elegible_lleva_mensaje_de_lectura_y_la_intencion_conserva_el_suyo(t):
    """AJ-B2-05: mismo codigo y status; la propuesta (lectura) no dice «no se ha guardado nada»;
    el rechazo de la intencion con esa misma categoria conserva su mensaje."""
    owner, _, cli, a, _, _ = t
    cat = ph.categoria(owner, "Nomina", ambito="INGRESO")
    antiguo = eh.rechazo_integracion("CATEGORIA_NO_ELEGIBLE")[1]["mensaje"]
    r = ph.propuesta_http(cli, cat)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE", r.text
    assert r.json()["mensaje"] == MENSAJE_PROPUESTA_NO_ELEGIBLE
    assert r.json()["mensaje"] != antiguo and "no se ha guardado nada" not in r.json()["mensaje"]
    cuerpo = h.intencion(a, categoria={"estado": "CATEGORIA", "categoria_id": str(cat), "magnitudes": []})
    ri = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert ri.status_code == 409 and ri.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE", ri.text
    assert ri.json()["mensaje"] == antiguo and "no se ha guardado nada" in antiguo


def test_propuesta_sin_categoria_no_consulta_la_guarda(t):
    owner, _, cli, a, _, _ = t
    pid = ph.insertar_sql(owner, cuenta=a)
    assert _propuesta(cli, None)["cuenta"]["origen"]["preferencia_id"] == str(pid)


# ------------------------------------------------------------------ AJ-B1-09: otra moneda
def test_unica_cuenta_en_otra_moneda_sin_propuesta_de_cuenta():
    owner, actor, cli = ph.tenant()
    usd = ph.cuenta(owner, actor, moneda="USD")
    cuentas = cli.get("/v1/vs01/cuentas-pago", params={"fecha": ph.FECHA.isoformat()}, headers=h.AUTH).json()["cuentas"]
    assert [c["cuenta_id"] for c in cuentas] == [str(usd)]  # el antiguo fallback del cliente la habria propuesto
    assert _propuesta(cli, None) == {"cuenta": None, "presupuestable": None}
    # Ni siquiera una preferencia hacia ella la propone (no elegible para EUR).
    ph.insertar_sql(owner, cuenta=usd)
    assert _propuesta(cli, None)["cuenta"] is None
    # Con una cuenta EUR adicional, esa es la unica elegible y la que se propone.
    eur = ph.cuenta(owner, actor)
    assert _propuesta(cli, None)["cuenta"] == {"valor": str(eur), "origen": {"capa": "DEFAULT_GENERAL",
                                                                             "preferencia_id": None}}
