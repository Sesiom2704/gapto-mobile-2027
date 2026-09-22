# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_025_p8_reconciliacion.py
# Ruta: tests/migration/test_rv3_025_p8_reconciliacion.py
# Descripcion: RV3 / P8 previo v0.1.0 sobre corpus SINTETICO sin PII. Discrimina que la reconciliacion tipada
#              R01..R26 marca FAIL (nunca PASS) ante: transferencia con efectos (R18), reembolso con INGRESO (R19),
#              atribucion sin estado (R20), derecho con importe 0 fabricado (R21), hecho no TRANSFERENCIA sin
#              efectos (R17), cuenta derivada con saldo inferido (R08), delta RUN06 sin clasificar (R26); y que un
#              delta RUN06 clasificado queda DELTA_CLASIFICADO y R25 PENDIENTE_FASE.
# Versión: 0.2.0
#              0.2.0: la clasificacion R26 resuelve el alias RUN06 -> 0330 y toda tabla con delta exige regla.
# ============================================================
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p8_reconciliacion", RAIZ / "scripts" / "migration_v3" / "rv3_p8_reconciliacion.py")
P8 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p8_reconciliacion"] = P8
_spec.loader.exec_module(P8)
P5 = P8._cargar_p5()
F = P5.fu


def _ds():
    ds = P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))
    ds.self_id = F.uuid_v3("TEST", "self", "actores_financieros", "a")
    return ds


def _estado(ds, rid, run06=None):
    return next(r for r in P8.reconciliar(P5, ds, {}, run06) if r["id"] == rid)["estado"]


def _hecho(ds, tipo, nombre):
    hid = F.uuid_v3("TEST", nombre, "hechos_financieros", "h")
    ds.filas["hechos_financieros"][hid] = {"id": hid, "tipo_hecho_id": P5.TIPOS_HECHO_SEED[tipo], "importe_total": Decimal(1)}
    return hid


def _efecto(ds, hid, tipo, estado="COMPLETA"):
    eid = F.uuid_v3("TEST", hid + tipo, "hecho_efectos", "e")
    ds.filas["hecho_efectos"][eid] = {"id": eid, "hecho_id": hid, "tipo_efecto": tipo, "estado_atribucion": estado}


def test_transferencia_con_efectos_es_fail():
    ds = _ds()
    h = _hecho(ds, "TRANSFERENCIA", "t")
    assert _estado(ds, "R18") == "PASS"
    _efecto(ds, h, "GASTO")
    assert _estado(ds, "R18") == "FAIL"


def test_reembolso_con_ingreso_es_fail():
    ds = _ds()
    h = _hecho(ds, "REEMBOLSO", "r")
    _efecto(ds, h, "DERECHO_COBRO")
    assert _estado(ds, "R19") == "PASS"
    _efecto(ds, h, "INGRESO")
    assert _estado(ds, "R19") == "FAIL"


def test_atribucion_sin_estado_y_hecho_sin_efectos_son_fail():
    ds = _ds()
    h = _hecho(ds, "GASTO", "g")
    assert _estado(ds, "R17") == "FAIL"
    _efecto(ds, h, "GASTO", estado=None)
    assert _estado(ds, "R17") == "PASS" and _estado(ds, "R20") == "FAIL"


def test_derecho_con_cero_fabricado_es_fail():
    ds = _ds()
    ds.filas["derechos_obligaciones_financieras"]["d"] = {"entidad_id": "d", "importe_original_documentado": None}
    assert _estado(ds, "R21") == "PASS"
    ds.filas["derechos_obligaciones_financieras"]["d"]["importe_original_documentado"] = Decimal("0.00")
    assert _estado(ds, "R21") == "FAIL"


def test_cuenta_derivada_con_saldo_inferido_es_fail(monkeypatch):
    ds = _ds()
    ds.filas["cuentas"]["x"] = {"id": "x", "saldo_apertura": None}
    monkeypatch.setitem(P8.BASE, "R08", 0)
    assert _estado(ds, "R08") == "PASS"
    ds.filas["cuentas"]["x"]["saldo_apertura"] = Decimal("5.00")
    assert _estado(ds, "R08") == "FAIL"


def test_delta_run06_sin_clasificar_es_fail_y_clasificado_es_delta():
    ds = _ds()
    ds.filas["transferencias"]["t"] = {"id": "t", "movimiento_salida_id": "a", "movimiento_entrada_id": "b"}
    assert _estado(ds, "R26", {"transferencias": 2}) == "DELTA_CLASIFICADO"
    ds.filas["cuentas"]["c"] = {"id": "c", "saldo_apertura": None}  # tabla sin regla de delta declarada
    assert _estado(ds, "R26", {"transferencias": 2}) == "FAIL"
    assert _estado(ds, "R26") == "PENDIENTE_FASE" and _estado(ds, "R25") == "PENDIENTE_FASE"


def test_r26_resuelve_el_alias_run06():
    ds = _ds()
    assert _estado(ds, "R26", {"fin_condiciones_versiones": 3}) == "DELTA_CLASIFICADO"
    assert all(v for v in P8.CLASIFICACION_R26.values())
