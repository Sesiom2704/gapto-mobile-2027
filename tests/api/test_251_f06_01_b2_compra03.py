# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_251_f06_01_b2_compra03.py
# Ruta: tests/api/test_251_f06_01_b2_compra03.py
# Descripcion: F06 T1-F06 · B2 N1 · C-COMPRA-03 (anadir un gasto de la compra despues) por HTTP, como
#   gapto_runtime con RLS: composicion de Hk′ (ADQUISICION_PATRIMONIAL, VALOR_ACTIVO causa ADQUISICION, sin
#   categoria, AFECTA_A de nivel efecto con el sello, PARTE_DE compra03.lote hacia H0), replay exacto y distinto
#   (una raiz), HF-09 / O6.17 (H0 unico; COMPRA_NO_REGISTRADA con cero o dos candidatos), O6.24 (propuesta en la
#   fecha economica de SU efecto, no en la de escritura), version y elegibilidad de cuentas.
#   La declaracion de C-COMPRA-03 (consumidor de 0352) se prueba en test_252.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f06_01_b2_helpers as c2
import vs01_api_helpers as h

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


@pytest.fixture()
def comprado():
    lab = c2.Lab()
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    return lab, uuid.UUID(cuerpo["intencion_id"])


def test_compra03_composicion_y_pertenencia(comprado):
    lab, h0 = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-05", nota="Tasacion")
    cuerpo = lab.peticion03(linea)
    j = _ok(lab.gasto_posterior(cuerpo))
    hk = uuid.UUID(cuerpo["intencion_id"])
    assert j["idempotente"] is False and j["compra"]["sale_de_tus_cuentas"] == "-400.00"
    assert j["compra"]["gasto_del_mes"] == "0.00"
    fila = lab.sql("SELECT th.codigo, h.fecha_hecho::text, h.notas, h.presupuestable FROM gapto.hechos_financieros h "
                   "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE h.id = %s", (hk,))
    assert fila == [("ADQUISICION_PATRIMONIAL", "2026-04-02", "Tasacion", False)]
    rel = lab.sql("SELECT id, hecho_destino_id FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s", (hk,))
    assert rel == [(uuid.uuid5(hk, "gapto.f06.compra03.lote"), h0)]
    ef = lab.sql("SELECT e.causa_valor_activo, e.categoria_id, x.efecto_id = e.id FROM gapto.hecho_efectos e "
                 "JOIN gapto.hecho_entidades x ON x.hecho_id = e.hecho_id WHERE e.hecho_id = %s", (hk,))
    assert ef == [("ADQUISICION", None, True)]
    assert j["propiedad"]["row_version"] == 3


def test_compra03_replay_exacto_y_distinto(comprado):
    lab, _ = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    cuerpo = lab.peticion03(linea)
    _ok(lab.gasto_posterior(cuerpo))
    antes = c2.huella()
    assert _ok(lab.gasto_posterior(cuerpo))["idempotente"] is True                    # con la version superada
    assert c2.huella() == antes
    for cambio in ({"linea": {**linea, "importe": "400.01"}}, {"atribucion": {"modo": "NO_LO_SE"}},
                   {"row_version_esperada": cuerpo["row_version_esperada"] + 1}):
        _rechazo(lab.gasto_posterior({**cuerpo, **cambio}), 409, REUTILIZADA)
    assert c2.huella() == antes


def test_compra03_con_la_intencion_de_la_compra_o_de_un_hk(comprado):
    lab, h0 = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    antes = c2.huella()
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, intencion_id=h0)), 409, REUTILIZADA)
    assert c2.huella() == antes


def test_o6_17_h0_unico_sin_hk_y_compra_no_registrada():
    lab = c2.Lab()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    _rechazo(lab.gasto_posterior(lab.peticion03(linea)), 409, "COMPRA_NO_REGISTRADA")       # cero candidatos
    sin_hk = lab.peticion(gastos=[])
    _ok(lab.compra(sin_hk))
    cuerpo = lab.peticion03(linea)
    _ok(lab.gasto_posterior(cuerpo))                                                         # (a) el unico candidato
    hk = uuid.UUID(cuerpo["intencion_id"])
    assert lab.sql("SELECT hecho_destino_id::text FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s",
                   (hk,)) == [(sin_hk["intencion_id"],)]
    # (b) dos candidatos a H0 (fixture): COMPRA_NO_REGISTRADA sin escribir
    c2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "10.00", "ADQUISICION")
    antes = c2.huella()
    _rechazo(lab.gasto_posterior(lab.peticion03(lab.gasto("OTRO", "5.00", "2026-04-03", "2026-04-03"))), 409,
             "COMPRA_NO_REGISTRADA")
    assert c2.huella() == antes


def test_o6_24_propuesta_en_la_fecha_economica_de_su_efecto(comprado):
    lab, _ = comprado
    linea = lab.gasto("OTRO", "90.00", "2026-02-20", "2026-02-20")                 # antes de la titularidad
    assert c2.titularidad_en(lab.cli, lab.pid, "2026-02-20") == []
    escritura = lab.propuesta(c2.ESCRITURA)
    cuerpo = lab.peticion03(linea, atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
        **escritura, "criterio": "TITULARIDAD_EN_FECHA_ECONOMICA"}})
    antes = c2.huella()
    _rechazo(lab.gasto_posterior(cuerpo), 422, "ENTRADA_INVALIDA")                 # fecha_referencia != la del efecto
    forzado = lab.peticion03(linea, atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
        "criterio": "TITULARIDAD_EN_FECHA_ECONOMICA", "fecha_referencia": "2026-02-20", "partes": escritura["partes"]}})
    _rechazo(lab.gasto_posterior(forzado), 422, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA")
    escritura_crit = lab.peticion03(linea, atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": escritura})
    _rechazo(lab.gasto_posterior(escritura_crit), 422, "ENTRADA_INVALIDA")         # criterio de la compra: no
    assert c2.huella() == antes
    _ok(lab.gasto_posterior(lab.peticion03(linea, atribucion={"modo": "NO_LO_SE"})))


def test_compra03_version_y_cuenta(comprado):
    lab, _ = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, version=1)), 409, "VERSION_DESFASADA")
    sin_pago = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=())
    _rechazo(lab.gasto_posterior(lab.peticion03({**linea, "cuenta_id": str(sin_pago)})), 422, "CUENTA_DESCONOCIDA")
    r = lab.cli.post(f"/v1/propiedades/{uuid.uuid4()}/compra/gastos", json=lab.peticion03(linea), headers=h.AUTH)
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")
