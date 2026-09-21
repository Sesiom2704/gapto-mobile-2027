# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_006_p5_dominio3.py
# Ruta: tests/migration/test_rv3_006_p5_dominio3.py
# Descripcion: RV3 / P5 v0.3.0. Corpus SINTETICO (sin PII) del dominio 3
#              (cuentas): fallo cerrado S20 mientras la configuracion sin dato
#              V3 siga en PROPUESTA; saldo_apertura = liquidez V3 (no se
#              recalcula ni se usa liquidez_inicial); cuentas derivadas con
#              saldo desconocido NULL (nunca 0); moneda no demostrada nunca se
#              rellena; cotitular no identificado nunca se inventa; sin
#              capacidades fabricadas.
#   0.1.1: la fixture fija CONFIG_CUENTAS_ESTADO=PROPUESTA (el estado de
#          produccion paso a CONFIRMADA en P5 v0.6.0, S20-1); el test sigue
#          verificando su baseline sin bloquear bloques posteriores.
# Versión: 0.1.1
# ============================================================
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
F = P5.fu
SHA = "0" * 64
CB = "public.cuentas_bancarias"


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {
        (CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
        (CB, "C2"): ("CREDITO", "PASIVO", False, True, True, "EUR"),
        (CB, "C3"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
        ("public.inversion", "I1"): ("AHORRO", "ACTIVO", True, True, False, "EUR"),
        ("public.gastos", "G1"): ("PREPAGO", "ACTIVO", True, True, False, None),
    })
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {("public.inversion", "I1"): ("CUENTA AHORRO", "proveedor_id"),
                                                 ("public.gastos", "G1"): ("PREPAGO X", None)})
    monkeypatch.setattr(P5, "GESTOR_REVOLUT", "PB")
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "PROPUESTA")


def _b0():
    filas = [
        ("public.users", "7", {"id": 7, "email": "t@example.invalid", "full_name": "Tenant"}),
        ("public.tipo_ramas_proveedores", "R1", {"id": "R1", "nombre": "BANCOS"}),
        ("public.proveedores", "PA", {"id": "PA", "nombre": "BANCO A", "rama_id": "R1", "subsegmento_id": "141", "activo": True}),
        ("public.proveedores", "PB", {"id": "PB", "nombre": "FINTECH B", "rama_id": "R1", "subsegmento_id": "141", "activo": True}),
        (CB, "C1", {"id": "C1", "anagrama": "CTA UNO", "banco_id": "PA", "liquidez": "-12.50",
                    "liquidez_inicial": "100.00", "participacion_pct": "100.00", "activo": True}),
        (CB, "C2", {"id": "C2", "anagrama": "TARJETA", "banco_id": "PA", "liquidez": "0.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "100.00", "activo": True}),
        (CB, "C3", {"id": "C3", "anagrama": "COMPARTIDA", "banco_id": "PA", "liquidez": "40.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "50.00", "activo": True}),
        ("public.inversion", "I1", {"id": "I1", "proveedor_id": "PA", "aporte_estimado": "930.00"}),
        ("public.gastos", "G1", {"id": "G1", "nombre": "CARGA PREPAGO", "importe": "250"}),
    ]
    b0 = {}
    for i, (c, k, d) in enumerate(filas, 1):
        t = json.dumps(d, ensure_ascii=False)
        b0.setdefault(c, {})[k] = F.RegistroB0(c, k, d, t, F.hash_registro(t), f"r{i}", i)
    return b0


def _cuentas(ds):
    return {c["nombre"]: c for c in ds.filas["cuentas"].values()}


def test_sin_confirmacion_falla_cerrado_s20(cfg):
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(), SHA)
    assert e.value.codigo == "S20_CONFIG_CUENTAS"


def test_saldo_apertura_es_la_liquidez_del_corte(cfg):
    c = _cuentas(P5.transformar(_b0(), SHA, modo_lab=True))
    assert c["CTA UNO"]["saldo_apertura"] == Decimal("-12.50")
    assert c["CTA UNO"]["fecha_inicio_ledger"] == P5.FECHA_INICIO_LEDGER
    assert c["TARJETA"]["naturaleza"] == "PASIVO" and c["TARJETA"]["computa_liquidez"] is False


def test_cuenta_derivada_con_saldo_desconocido_nunca_cero(cfg):
    c = _cuentas(P5.transformar(_b0(), SHA, modo_lab=True))
    assert c["CUENTA AHORRO"]["saldo_apertura"] is None and c["CUENTA AHORRO"]["fecha_inicio_ledger"] is None


def test_moneda_no_demostrada_no_se_rellena(cfg):
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    assert "PREPAGO X" not in _cuentas(ds)
    assert any(p.get("S20") == "MONEDA_NO_DEMOSTRADA" for p in ds.pendientes)


def test_cotitular_no_identificado_no_se_inventa(cfg):
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    comp = _cuentas(ds)["COMPARTIDA"]["id"]
    assert not [p for p in ds.filas["cuenta_participaciones"].values() if p["cuenta_id"] == comp]
    assert len(ds.filas["actores_financieros"]) == 1
    assert any(p.get("S20") == "COTITULAR_NO_IDENTIFICADO" for p in ds.pendientes)


def test_participacion_100_self_y_sin_capacidades(cfg):
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    parts = list(ds.filas["cuenta_participaciones"].values())
    assert len(parts) == 2 and all(p["porcentaje"] == Decimal(100) for p in parts)
    assert "cuenta_capacidades" not in ds.filas


def test_gestor_es_el_tercero_v3(cfg):
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    banco = next(t["id"] for t in ds.filas["terceros"].values() if t["nombre"] == "BANCO A")
    assert _cuentas(ds)["CTA UNO"]["tercero_gestor_id"] == banco
