# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_174_f05_03_elegibilidad_cuentas.py
# Ruta: tests/api/test_174_f05_03_elegibilidad_cuentas.py
# Descripcion: Contrato unico de elegibilidad de cuentas (F05-03/F05-04 J2
#   §1.0/§1.1; F05 §46.4 R1/R2, §46.5 E1; F05-D032 C1).
#   - Matriz operacion -> capacidad (GASTO PAGAR_GASTO, INGRESO
#     RECIBIR_INGRESO, OP-10 origen TRANSFERIR_SALIDA, destino
#     TRANSFERIR_ENTRADA) sobre las cuentas sinteticas de C1 (CORRIENTE,
#     EFECTIVO, AHORRO, CREDITO) y una sin capacidades.
#   - COMPRA_TARJETA y DOMICILIAR no implican PAGAR_GASTO.
#   - Motivos en orden fijo: DESHABILITADA, CERRADA, LEDGER_POSTERIOR,
#     MONEDA, SIN_CAPACIDAD; regla de ledger (NULL no bloquea).
#   - Aislamiento por owner; GET /v1/cuentas/elegibles.
#   - Confirmacion VS-01 bajo el lock: cuenta de credito con PAGAR_GASTO
#     admitida (un efecto GASTO, un movimiento en la cuenta de credito, sin
#     efectos de deuda, R2); sin capacidad o con ledger posterior ->
#     CUENTA_DESCONOCIDA; USD -> MONEDA_INVALIDA (test_150 sin cambios).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

FECHA = ph.FECHA
OPERACIONES = ("GASTO", "INGRESO", "TRANSFERENCIA_ORIGEN", "TRANSFERENCIA_DESTINO")
URL = "/v1/intenciones/gasto-pagado"


def _elegibles(owner, operacion, fecha=FECHA):
    from app.comun import elegibilidad_cuentas as e

    return fh.en_transaccion(owner, lambda s: e.elegibilidad_cuentas(s, operacion, fecha))


def _motivo(owner, cuenta, operacion="GASTO", fecha=FECHA):
    from app.comun import elegibilidad_cuentas as e

    return fh.en_transaccion(owner, lambda s: e.motivo_cuenta(s, cuenta, operacion, fecha))


@pytest.fixture()
def t():
    return ph.tenant()


def _cuenta(owner, actor, tipo, naturaleza="ACTIVO", capacidades=None, nombre=None):
    cid = h.crear_cuenta(owner, [(actor, 100)], tipo=tipo, naturaleza=naturaleza, capacidades=capacidades)
    h.como_owner(owner, "UPDATE gapto.cuentas SET nombre=%s WHERE id=%s", (nombre or tipo, cid))
    return cid


def test_matriz_r1_sobre_las_cuentas_sinteticas(t):
    owner, actor, _ = t
    c = {
        "CORRIENTE": _cuenta(owner, actor, "CORRIENTE"),
        "EFECTIVO": _cuenta(owner, actor, "EFECTIVO"),
        "AHORRO": _cuenta(owner, actor, "AHORRO"),
        "CREDITO": _cuenta(owner, actor, "CREDITO", naturaleza="PASIVO"),
        "SIN": _cuenta(owner, actor, "CORRIENTE", capacidades=(), nombre="SIN"),
    }
    esperado = {
        "GASTO": {"CORRIENTE", "EFECTIVO", "CREDITO"},
        "INGRESO": {"CORRIENTE", "EFECTIVO"},
        "TRANSFERENCIA_ORIGEN": {"CORRIENTE", "EFECTIVO", "AHORRO"},
        "TRANSFERENCIA_DESTINO": {"CORRIENTE", "EFECTIVO", "AHORRO", "CREDITO"},
    }
    inverso = {v: k for k, v in c.items()}
    for op in OPERACIONES:
        filas = _elegibles(owner, op)
        assert {inverso[f["cuenta_id"]] for f in filas if f["elegible"]} == esperado[op], op
        for f in filas:
            assert f["motivo"] == (None if f["elegible"] else "SIN_CAPACIDAD"), (op, f)


def test_compra_tarjeta_y_domiciliar_no_implican_pagar_gasto(t):
    owner, actor, _ = t
    cid = _cuenta(owner, actor, "CREDITO", naturaleza="PASIVO", capacidades=("COMPRA_TARJETA", "DOMICILIAR"))
    assert _motivo(owner, cid) == "SIN_CAPACIDAD"


@pytest.mark.parametrize("caso,motivo", [
    ("deshabilitada", "DESHABILITADA"), ("cerrada", "DESHABILITADA"), ("ledger_posterior", "LEDGER_POSTERIOR"),
    ("usd", "MONEDA"), ("sin_capacidad", "SIN_CAPACIDAD"), ("ledger_igual", None), ("ledger_anterior", None),
])
def test_motivos_en_orden_fijo(t, caso, motivo):
    owner, actor, _ = t
    if caso == "usd":
        cid = h.crear_cuenta(owner, [(actor, 100)], moneda="USD")
    elif caso == "sin_capacidad":
        cid = h.crear_cuenta(owner, [(actor, 100)], capacidades=())
    else:
        cid = h.crear_cuenta(owner, [(actor, 100)])
    if caso == "deshabilitada":
        ph.deshabilitar_cuenta(owner, cid)
    if caso == "cerrada":  # ck_cuentas__cierre_deshabilita: el cierre exige enabled=false
        h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false, fecha_cierre=%s WHERE id=%s", (FECHA, cid))
    ledger = {"ledger_posterior": FECHA + dt.timedelta(days=1), "ledger_igual": FECHA,
              "ledger_anterior": FECHA - dt.timedelta(days=30)}.get(caso)
    if ledger is not None:
        h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                     (ledger, cid))
    assert _motivo(owner, cid) == motivo


def test_cuenta_ajena_o_inexistente_no_encontrada(t):
    owner, _, _ = t
    otro, otro_actor = h.crear_tenant()
    ajena = h.crear_cuenta(otro, [(otro_actor, 100)])
    assert _motivo(owner, ajena) == "NO_ENCONTRADA"
    assert _motivo(owner, uuid.uuid4()) == "NO_ENCONTRADA"
    assert ajena not in {f["cuenta_id"] for f in _elegibles(owner, "GASTO")}


def test_endpoint_cuentas_elegibles(t):
    owner, actor, cli = t
    corriente = _cuenta(owner, actor, "CORRIENTE", nombre="B corriente")
    credito = _cuenta(owner, actor, "CREDITO", naturaleza="PASIVO", nombre="A credito")
    ahorro = _cuenta(owner, actor, "AHORRO", nombre="C ahorro")
    r = cli.get("/v1/cuentas/elegibles", params={"operacion": "GASTO", "fecha": FECHA.isoformat()}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == {"operacion": "GASTO", "cuentas": [
        {"cuenta_id": str(credito), "nombre": "A credito", "moneda": "EUR"},
        {"cuenta_id": str(corriente), "nombre": "B corriente", "moneda": "EUR"}]}
    r = cli.get("/v1/cuentas/elegibles", params={"operacion": "TRANSFERENCIA_ORIGEN", "fecha": FECHA.isoformat()},
                headers=h.AUTH)
    assert [c["cuenta_id"] for c in r.json()["cuentas"]] == [str(corriente), str(ahorro)]
    r = cli.get("/v1/cuentas/elegibles", params={"operacion": "OTRA", "fecha": FECHA.isoformat()}, headers=h.AUTH)
    assert r.status_code == 422


# ------------------------------------------------------------------ confirmacion VS-01 bajo el lock
def test_gasto_pagado_con_credito_un_solo_efecto_y_sin_deuda(t):
    """R2: compra con credito -> un efecto GASTO y un movimiento -X en la
    cuenta de credito; ningun efecto de deuda."""
    owner, actor, cli = t
    credito = _cuenta(owner, actor, "CREDITO", naturaleza="PASIVO")
    cuerpo = h.intencion(credito, importe="25.00")
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(cuerpo["intencion_id"])
    efectos = h.leer(owner, "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE hecho_id=%s", (hid,))
    assert [(e[0], str(e[1])) for e in efectos] == [("GASTO", "25.0000")]
    movs = h.leer(owner, "SELECT m.cuenta_id, m.importe FROM gapto.movimientos_tesoreria m "
                         "JOIN gapto.hecho_movimientos_tesoreria hm ON hm.movimiento_tesoreria_id = m.id "
                         "WHERE hm.hecho_id=%s", (hid,))
    assert [(m[0], str(m[1])) for m in movs] == [(credito, "-25.0000")]


@pytest.mark.parametrize("caso", ["sin_capacidad", "ledger_posterior", "ahorro"])
def test_gasto_pagado_con_cuenta_no_elegible(t, caso):
    owner, actor, cli = t
    if caso == "ahorro":
        cid = _cuenta(owner, actor, "AHORRO")
    else:
        cid = h.crear_cuenta(owner, [(actor, 100)], capacidades=() if caso == "sin_capacidad" else None)
    if caso == "ledger_posterior":
        h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                     (dt.date(2026, 9, 25), cid))
    cuerpo = h.intencion(cid)
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "CUENTA_DESCONOCIDA", r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
                  (uuid.UUID(cuerpo["intencion_id"]),))[0][0] == 0
