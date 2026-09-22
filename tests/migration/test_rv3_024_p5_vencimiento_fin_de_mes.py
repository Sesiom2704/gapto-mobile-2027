# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_024_p5_vencimiento_fin_de_mes.py
# Ruta: tests/migration/test_rv3_024_p5_vencimiento_fin_de_mes.py
# Descripcion: RV3 / P5 v0.30.0. Financiacion que se carga el ULTIMO dia de cada mes y que V3 registra el dia 28
#              (propietario 2026-09-22) sobre corpus SINTETICO sin PII. Discrimina: calendario y vencimiento final
#              previsto a fin de mes (incluido febrero bisiesto), solo para las financiaciones declaradas, fallo
#              cerrado si el dia V3 no es 28, ledger D8-K y fecha economica de la cuota pagada a fin de mes.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s8 = importlib.util.spec_from_file_location("t8_fdm", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
_s23 = importlib.util.spec_from_file_location("t23_fdm", Path(__file__).resolve().parent /
                                              "test_rv3_023_p5_r02_cuotas_direcciones_omisiones.py")
T23 = importlib.util.module_from_spec(_s23)
_s23.loader.exec_module(T23)
F = P5.fu


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(T8.CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})


def _filas_hipoteca_dia_28():
    base = [f for f in T8._filas() if not (f[0] == T8.PR and f[1] == "P1") and not (f[0] == T8.PQ and f[1].startswith("P1-"))]
    hip = T8._frances(Decimal("1000.00"), "12.000", 4, venc0="2024-01-28", pagadas=2)
    return base + T8._prestamo("P1", "HIP. CASA", "GH", Decimal("1000.00"), "12.000", hip, vivienda="V1")


def _calendario(ds, nombre):
    eid = next(e for e, x in ds.filas["entidades"].items() if x["nombre"] == nombre)
    cs = sorted((c["numero_cuota"], c["fecha_vencimiento"]) for c in ds.filas["financiacion_cuotas"].values()
                if c["financiacion_entidad_id"] == eid)
    return cs, ds.filas["financiaciones"][eid]


def test_calendario_a_fin_de_mes_solo_en_la_financiacion_declarada(monkeypatch):
    monkeypatch.setattr(P5, "VENCIMIENTO_FIN_DE_MES", {"P1"})
    ds = P5.transformar(T8._b0(_filas_hipoteca_dia_28()), "0" * 64)
    cs, fin = _calendario(ds, "HIP. CASA")
    assert cs == [(1, "2024-01-31"), (2, "2024-02-29"), (3, "2024-03-31"), (4, "2024-04-30")]
    assert fin["fecha_vencimiento_final_prevista"] == "2024-04-30"
    assert any(e["regla"] == "D8-K-FIN_DE_MES" and e["cuotas"] == 4 for e in ds.ledger)
    otro, _ = _calendario(ds, "PRÉSTAMO CERO")
    assert [d for _, d in otro] == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_sin_declaracion_se_conserva_el_dia_v3(monkeypatch):
    monkeypatch.setattr(P5, "VENCIMIENTO_FIN_DE_MES", set())
    ds = P5.transformar(T8._b0(_filas_hipoteca_dia_28()), "0" * 64)
    cs, _ = _calendario(ds, "HIP. CASA")
    assert [d for _, d in cs] == ["2024-01-28", "2024-02-28", "2024-03-28", "2024-04-28"]


def test_dia_v3_distinto_de_28_falla_cerrado(monkeypatch):
    monkeypatch.setattr(P5, "VENCIMIENTO_FIN_DE_MES", {"P1"})
    with pytest.raises(P5.ErrorP5) as e:
        P5._venc_real("P1", "2024-01-27")
    assert e.value.codigo == "S9_VENCIMIENTO_FIN_DE_MES_NO_28"
    assert P5._venc_real("P2", "2024-01-27") == "2024-01-27" and P5._venc_real("P1", None) is None


def test_cuota_pagada_con_fecha_economica_a_fin_de_mes(monkeypatch):
    monkeypatch.setattr(T23.P5, "VENCIMIENTO_FIN_DE_MES", {"P1"})  # T23 ejecuta su propia instancia del modulo
    ds, _ = T23._ds(desde="2024-08-31")  # la participacion empieza el dia real de inicio
    T23._cuotas(ds, T23._cuota(fecha_vencimiento="2024-08-28"))
    fechas = {h["fecha_hecho"] for h in ds.filas["hechos_financieros"].values()}
    assert fechas == {"2024-08-31"} and len(ds.filas["hechos_financieros"]) == 2
    assert not ds.trazabilidad.get("r02_residuales")
