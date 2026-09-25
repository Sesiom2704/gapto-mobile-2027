# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_150_f05_vs01_api.py
# Ruta: tests/api/test_150_f05_vs01_api.py
# Descripcion: Tests del adaptador HTTP F05-00-B / VS-01 contra PostgreSQL
#   local desechable (cadena 0001..0330). Cubren el minimo del mandato VS-01
#   §22 (backend/API) y las condiciones de identidad de desarrollo (§4 v0.2):
#   request valido -> OP-22 con la composicion completa; tenant no
#   manipulable; errores de dominio traducidos sin texto SQL; retry de la
#   misma identidad; misma identidad con otro payload -> conflicto; una sola
#   realidad persistida; SIN_INDICAR -> NO_DISPONIBLE y Home PARCIAL; cuenta
#   compartida sin aportacion inventada; otra moneda no se suma; fail-closed.
#   v0.2.0 (F05-D003): financiacion sellada en la intencion y cuentas-pago
#   por fecha del pago. Las pruebas nuevas de §16.4/§16.5 viven en
#   test_151_f05_vs01_financiacion_atomicidad.py.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from contextlib import contextmanager

import psycopg
import pytest

import vs01_api_helpers as h

D = decimal.Decimal


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


def _conteos(owner, hecho_id):
    q = {
        "hecho": "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
        "efectos": "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id=%s",
        "conciliaciones": "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id=%s",
        "aportaciones": "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s",
        "movimientos": "SELECT count(*) FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c "
                       "ON c.movimiento_tesoreria_id=m.id WHERE c.hecho_id=%s",
    }
    return {k: h.leer(owner, v, (hecho_id,))[0][0] for k, v in q.items()}


def test_request_valido_compone_op22_completo(tenant):
    owner, actor, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta, presupuestable=False)
    r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    js = r.json()
    hid = uuid.UUID(js["hecho_id"])
    assert hid == uuid.UUID(cuerpo["intencion_id"]) and js["idempotente"] is False
    assert js["estado_atribucion"] == "COMPLETA" and js["aportacion_criterio"] == "PARTICIPACION_CUENTA"

    hecho = h.leer(owner, "SELECT estado, importe_total, moneda, presupuestable, estado_localizacion, concepto "
                          "FROM gapto.hechos_financieros WHERE id=%s", (hid,))[0]
    # presupuestable = decision explicita (aqui False), nunca un default; localizacion DESCONOCIDA.
    assert hecho == ("ACTIVO", D("3.5000"), "EUR", False, "DESCONOCIDA", "Café")
    assert h.leer(owner, "SELECT tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos "
                         "WHERE hecho_id=%s", (hid,)) == [("GASTO", D("3.5000"), "COMPLETA")]
    assert h.leer(owner, "SELECT a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                         "JOIN gapto.hecho_efectos e ON e.id=a.efecto_id WHERE e.hecho_id=%s", (hid,)) == [(actor, D("3.5000"))]
    assert h.leer(owner, "SELECT m.cuenta_id, m.importe, c.importe_asignado FROM gapto.movimientos_tesoreria m "
                         "JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id=m.id "
                         "WHERE c.hecho_id=%s", (hid,)) == [(cuenta, D("-3.5000"), D("-3.5000"))]
    assert h.leer(owner, "SELECT actor_id, importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago "
                         "WHERE hecho_id=%s", (hid,)) == [(actor, D("3.5000"), "PARTICIPACION_CUENTA")]


def test_retry_misma_identidad_es_idempotente_y_una_sola_realidad(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    r1 = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    r2 = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["idempotente"] is False and r2.json()["idempotente"] is True
    assert _conteos(owner, uuid.UUID(cuerpo["intencion_id"])) == {
        "hecho": 1, "efectos": 1, "conciliaciones": 1, "aportaciones": 1, "movimientos": 1}


@pytest.mark.parametrize("cambio", [{"importe": "4.00", "financiacion": h.propuesta_self_100("4.00")},
                                    {"concepto": "Otra cosa"}, {"presupuestable": False},
                                    {"financiacion": h.NO_DETERMINADA}])
def test_misma_identidad_otro_payload_es_conflicto(tenant, cambio):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200
    r = cli.post("/v1/intenciones/gasto-pagado", json={**cuerpo, **cambio}, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert r.json()["reintentable"] is False
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert h.leer(owner, "SELECT importe_total, concepto FROM gapto.hechos_financieros WHERE id=%s", (hid,)) \
        == [(D("3.5000"), "Café")]
    assert _conteos(owner, hid)["efectos"] == 1


def test_tenant_no_manipulable_desde_payload(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    for campo in ("owner_user_id", "tenant_id", "actor_id"):
        r = cli.post("/v1/intenciones/gasto-pagado",
                     json={**h.intencion(cuenta), campo: str(uuid.uuid4())}, headers=h.AUTH)
        assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", campo


def test_cuenta_de_otro_tenant_es_invisible_y_nada_persiste(tenant):
    owner, _, _ = tenant
    otro, otro_actor = h.crear_tenant()
    cuenta_ajena = h.crear_cuenta(otro, [(otro_actor, 100)])
    cuerpo = h.intencion(cuenta_ajena)
    r = h.cliente(owner).post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "CUENTA_DESCONOCIDA"
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _conteos(owner, hid)["hecho"] == 0 and _conteos(otro, hid)["hecho"] == 0


@pytest.mark.parametrize("campo", ["presupuestable", "atribucion", "cuenta_id", "fecha_hecho", "intencion_id", "financiacion"])
def test_campos_de_decision_obligatorios_sin_default(tenant, campo):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta)
    del cuerpo[campo]
    r = h.cliente(owner).post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and campo in r.json()["mensaje"]


@pytest.mark.parametrize("importe", ["0", "-3.50", "3.505"])
def test_importe_invalido(tenant, importe):
    owner, _, cuenta = tenant
    r = h.cliente(owner).post("/v1/intenciones/gasto-pagado", json=h.intencion(cuenta, importe=importe), headers=h.AUTH)
    assert r.status_code == 422


def test_error_de_dominio_traducido_sin_texto_sql(tenant):
    owner, actor, _ = tenant
    cuenta_usd = h.crear_cuenta(owner, [(actor, 100)], moneda="USD")
    r = h.cliente(owner).post("/v1/intenciones/gasto-pagado", json=h.intencion(cuenta_usd), headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "MONEDA_INVALIDA"
    texto = r.text.lower()
    for fuga in ("gapto.", "select", "constraint", "violates", "sqlstate", "psycopg"):
        assert fuga not in texto


def test_sin_indicar_es_no_disponible_y_home_parcial(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta, atribucion="SIN_INDICAR", fecha_hecho="2026-08-10")
    r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["estado_atribucion"] == "NO_DISPONIBLE"
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert h.leer(owner, "SELECT count(*) FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e "
                         "ON e.id=a.efecto_id WHERE e.hecho_id=%s", (hid,))[0][0] == 0
    m = cli.get("/v1/vs01/gasto-mes", params={"mes": "2026-08"}, headers=h.AUTH).json()
    # Desconocido NO se suma como cero ni se presenta como total confirmado.
    assert m["gasto_atribuible"] == "0.00" and m["estado"] == "PARCIAL" and m["gastos_sin_reparto"] == 1


def test_gasto_mes_suma_solo_lo_atribuible_confirmado(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    for imp, fecha in (("3.50", "2026-07-02"), ("10.25", "2026-07-31"), ("99.00", "2026-06-30")):
        assert cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(cuenta, importe=imp, fecha_hecho=fecha),
                        headers=h.AUTH).status_code == 200
    m = cli.get("/v1/vs01/gasto-mes", params={"mes": "2026-07"}, headers=h.AUTH).json()
    assert m == {"mes": "2026-07", "moneda": "EUR", "gasto_atribuible": "13.75", "estado": "CONFIRMADO",
                 "gastos_sin_reparto": 0, "gastos_otra_moneda": 0, "contrato": "PROVISIONAL_VS01_CANDIDATO_F08"}


def test_gasto_en_otra_moneda_no_se_suma(tenant):
    """Un GASTO en USD del mismo mes se cuenta aparte y marca PARCIAL."""
    owner, actor, _ = tenant
    from app.core.contexto import ContextoOperacion
    from app.core.modelos import DatosCreacionHecho
    from app.core.modelos_compuesto import DatosHechoCompuesto
    from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
    from app.core.unidad_trabajo import UnidadDeTrabajo, conexion_directa
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    unidad = UnidadDeTrabajo(lambda: conexion_directa(h.dsn()), rol_runtime="gapto_runtime")
    hid = uuid.uuid4()
    datos = DatosHechoCompuesto(
        hecho=DatosCreacionHecho(hecho_id=hid, fecha_hecho=__import__("datetime").date(2026, 5, 5), moneda="USD",
                                 presupuestable=True, estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO",
                                 concepto="usd", importe_total=D("20")),
        efectos=[DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=D("20"),
                             estado_atribucion="COMPLETA",
                             atribuciones=(DatosAtribucion(uuid.uuid4(), actor, D("20"), "MANUAL"),))],
    )
    HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla).registrar_hecho_compuesto(
        ContextoOperacion.de_usuario(owner), datos)
    m = h.cliente(owner).get("/v1/vs01/gasto-mes", params={"mes": "2026-05"}, headers=h.AUTH).json()
    assert m["gasto_atribuible"] == "0.00" and m["gastos_otra_moneda"] == 1 and m["estado"] == "PARCIAL"


def test_cuenta_compartida_no_inventa_aportacion(tenant):
    owner, actor, _ = tenant
    otro = h.crear_actor_tercero(owner)
    compartida = h.crear_cuenta(owner, [(actor, 50), (otro, 50)])
    cli = h.cliente(owner)
    cuentas = cli.get("/v1/vs01/cuentas-pago", params={"fecha": "2026-09-24"}, headers=h.AUTH).json()["cuentas"]
    assert {c["cuenta_id"]: c["propuesta_financiacion"] for c in cuentas}[str(compartida)] == "NO_DETERMINADA"
    cuerpo = h.intencion(compartida, financiacion=h.NO_DETERMINADA)
    r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["aportacion_criterio"] is None
    assert r.json()["financiacion"] == "NO_DETERMINADA"
    assert _conteos(owner, uuid.UUID(cuerpo["intencion_id"]))["aportaciones"] == 0


def test_sin_token_o_token_erroneo_no_escribe(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    for cab in ({}, {"Authorization": "Bearer otro-token-cualquiera-00000000"}):
        r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=cab)
        assert r.status_code == 401 and r.json()["codigo"] == "NO_AUTORIZADO"
    assert _conteos(owner, uuid.UUID(cuerpo["intencion_id"]))["hecho"] == 0


def test_fail_closed_fuera_de_development_y_base_no_permitida(tenant):
    from app.api.app import create_app
    from app.api.configuracion import ConfiguracionInvalida

    owner, _, _ = tenant
    for env in ({"GAPTO_ENV": "production"}, {"GAPTO_ENV": ""}, {"GAPTO_DEV_TOKEN": "corto"}):
        with pytest.raises(ConfiguracionInvalida):
            h.configuracion(owner, **env)
    with pytest.raises(ConfiguracionInvalida):
        create_app(h.configuracion(owner, GAPTO_DEV_DB_ALLOWLIST="gapto2027_test"))


def test_bd_caida_es_indeterminado_reintentable(tenant):
    owner, _, cuenta = tenant
    estado = {"caida": False}

    @contextmanager
    def proveedor():
        if estado["caida"]:
            raise psycopg.OperationalError("conexion perdida (simulada)")
        with psycopg.connect(h.dsn()) as c:
            yield c

    cli = h.cliente(owner, proveedor_conexion=proveedor)
    estado["caida"] = True
    cuerpo = h.intencion(cuenta)
    r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 503 and r.json()["reintentable"] is True
    assert "nada" not in r.json()["mensaje"].lower()  # no se afirma lo que no se sabe
    estado["caida"] = False  # el reintento de la MISMA intencion confirma una sola vez
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200
    assert _conteos(owner, uuid.UUID(cuerpo["intencion_id"]))["hecho"] == 1
