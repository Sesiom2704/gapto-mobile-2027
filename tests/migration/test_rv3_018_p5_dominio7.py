# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_018_p5_dominio7.py
# Ruta: tests/migration/test_rv3_018_p5_dominio7.py
# Descripcion: RV3 / P5 v0.22.0. Dominio 7 (tesoreria legacy) sobre corpus SINTETICO sin PII:
#              transferencia V3 -> hecho neutro + 2 movimientos OPERACION + transferencias +
#              2 conciliaciones (F04-D001); misma cuenta -> un unico AJUSTE_SALDO con signo del
#              saldo (DV-7, nunca autotransferencia); movimientos solo anteriores al inicio del
#              ledger (no computan en el saldo de apertura); sin fechas/horas fabricadas; carga
#              fisica RV3_IMPORT con ROLLBACK.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s12 = importlib.util.spec_from_file_location("t12_d7", Path(__file__).resolve().parent / "test_rv3_012_p5_dominio10.py")
T12 = importlib.util.module_from_spec(_s12)
_s12.loader.exec_module(T12)
T8 = T12.T8
F = P5.fu
SHA = "0" * 64
CB, MV = "public.cuentas_bancarias", "public.movimientos_cuenta"
N = "141"
DOMINIO_5 = True
DOMINIO_6 = True
DOMINIO_7 = True

C2 = (CB, "C2", {"id": "C2", "anagrama": "CTA DOS", "banco_id": "PA", "liquidez": "5.00", "liquidez_inicial": "0.00",
                 "participacion_pct": "100.00", "activo": True})


def _m(k, **kw):
    d = {"id": k, "comentarios": "Nota", "createdon": "2026-02-01T10:00:00+00:00", "cuenta_origen_id": "C1",
         "cuenta_destino_id": "C2", "fecha": "2026-02-01", "importe": "50.00", "modifiedon": N,
         "saldo_origen_antes": "100.00", "saldo_origen_despues": "50.00", "saldo_destino_antes": "10.00",
         "saldo_destino_despues": "60.00", "user_id": 2}
    d.update(kw)
    return (MV, k, d)


def _aj(k, antes, despues, importe, **kw):
    return _m(k, cuenta_destino_id="C1", importe=importe, saldo_origen_antes=antes, saldo_origen_despues=despues,
              saldo_destino_antes=antes, saldo_destino_despues=despues, comentarios="Ajuste manual de liquidez", **kw)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    for k, v in (("CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                     (CB, "C2"): ("AHORRO", "ACTIVO", True, True, False, "EUR")}),
                 ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {}),
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("ISA_TIPO_HECHO_DECIDIDO", None), ("CUENTA_AHORRO", (CB, "C2")),
                 ("DOMINIO_5_ACTIVO", True), ("DOMINIO_6_ACTIVO", True), ("DOMINIO_7_ACTIVO", True)):
        monkeypatch.setattr(P5, k, v)
    real = P5.clasificar
    monkeypatch.setattr(P5, "clasificar", lambda ds, co, cl, f: ("NULL", None) if f.get("tipo_id") in ("TX", "TF")
                        else real(ds, co, cl, f))


def _t(extra=()):
    return P5.transformar(T8._b0(T12._filas(extra=(C2,) + tuple(extra))), SHA, modo_lab=True)


def _cta(k):
    return F.uuid_v3(CB, k, "cuentas", "cuenta")


def _movs(ds, cl):
    return {r: ds.filas["movimientos_tesoreria"].get(F.uuid_v3(MV, cl, "movimientos_tesoreria", r))
            for r in ("salida", "entrada", "ajuste")}


def _err(extra):
    with pytest.raises(P5.ErrorP5) as e:
        _t(extra)
    return e.value.codigo


def test_transferencia_hecho_neutro_dos_patas_y_conciliaciones():
    ds = _t([_m("M1")])
    m = _movs(ds, "M1")
    assert m["ajuste"] is None
    assert (m["salida"]["cuenta_id"], m["salida"]["importe"], m["salida"]["clase_movimiento"]) == (_cta("C1"), Decimal("-50.00"), "OPERACION")
    assert (m["entrada"]["cuenta_id"], m["entrada"]["importe"]) == (_cta("C2"), Decimal("50.00"))
    assert (m["salida"]["fecha_movimiento"], m["salida"]["confirmado_at"], m["salida"]["descripcion"]) == \
        ("2026-02-01", "2026-02-01T10:00:00+00:00", "Nota")
    (t,) = ds.filas["transferencias"].values()
    assert (t["movimiento_salida_id"], t["movimiento_entrada_id"]) == (m["salida"]["id"], m["entrada"]["id"])
    h = ds.filas["hechos_financieros"][F.uuid_v3(MV, "M1", "hechos_financieros", "hecho")]
    assert h["tipo_hecho_id"] == P5.TIPOS_HECHO_SEED["TRANSFERENCIA"] and h["presupuestable"] is False
    assert not any(e["hecho_id"] == h["id"] for e in ds.filas["hecho_efectos"].values())
    conc = sorted((c["movimiento_tesoreria_id"], c["importe_asignado"]) for c in ds.filas["hecho_movimientos_tesoreria"].values()
                  if c["hecho_id"] == h["id"])
    assert conc == sorted([(m["salida"]["id"], Decimal("-50.00")), (m["entrada"]["id"], Decimal("50.00"))])


def test_ajuste_es_un_unico_movimiento_con_signo_del_saldo_nunca_autotransferencia():
    ds = _t([_aj("A1", "100.00", "70.00", "30.00")])
    m = _movs(ds, "A1")
    assert m["salida"] is None and m["entrada"] is None
    assert (m["ajuste"]["importe"], m["ajuste"]["clase_movimiento"], m["ajuste"]["cuenta_id"]) == \
        (Decimal("-30.00"), "AJUSTE_SALDO", _cta("C1"))
    assert ds.filas["transferencias"] == {} and ds.filas["hecho_movimientos_tesoreria"] == {}
    assert F.uuid_v3(MV, "A1", "hechos_financieros", "hecho") not in ds.filas["hechos_financieros"]


def test_ajuste_con_importe_que_no_cuadra_con_el_saldo_falla():
    assert _err([_aj("A1", "100.00", "70.00", "31.00")]) == "S9_AJUSTE_INCOHERENTE"


@pytest.mark.parametrize("fecha", [P5.FECHA_INICIO_LEDGER, "2026-12-01"])
def test_movimiento_dentro_del_ledger_se_contaria_dos_veces(fecha):
    assert _err([_m("M1", fecha=fecha)]) == "S9_MOVIMIENTO_DENTRO_DEL_LEDGER"


def test_confirmacion_desconocida_no_se_fabrica():
    assert _err([_m("M1", createdon=N)]) == "S6_MOVIMIENTO_INCOMPLETO"


def test_saldo_de_apertura_de_las_cuentas_no_cambia():
    sin = _t()
    con = _t([_m("M1"), _aj("A1", "100.00", "70.00", "30.00")])
    assert sin.filas["cuentas"] == con.filas["cuentas"]


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    ds = _t([_m("M1"), _m("M2", cuenta_origen_id="C2", cuenta_destino_id="C1", importe="12.34"),
             _aj("A1", "100.00", "70.00", "30.00"), _aj("A2", "10.00", "15.50", "5.50")])
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert (res["movimientos_tesoreria"], res["transferencias"], res["hecho_movimientos_tesoreria"]) == (6, 2, 4)
