# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_019_p5_dominio11.py
# Ruta: tests/migration/test_rv3_019_p5_dominio11.py
# Descripcion: RV3 / P5 v0.23.0. Dominio 11 (cierres legacy) sobre corpus SINTETICO sin PII:
#              snapshot IMPORTADO_LEGACY/CAJA/V3_SNAPSHOT sin recalculo, bundle LEGACY_V3_*
#              deshabilitado, campos inexistentes antes del rediseno de dic-2025 no convertidos
#              en ceros, desconocido nunca cero, detalle con clave de desglose, presupuestos
#              G-V3-03 pendientes y carga fisica RV3_IMPORT con ROLLBACK.
#   0.2.0: presupuesto de contenedores G-V3-03 decidido (importe_cuota = presupuesto), P5 v0.24.0.
# Versión: 0.2.0
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
_s12 = importlib.util.spec_from_file_location("t12_d11", Path(__file__).resolve().parent / "test_rv3_012_p5_dominio10.py")
T12 = importlib.util.module_from_spec(_s12)
_s12.loader.exec_module(T12)
T8 = T12.T8
F = P5.fu
SHA = "0" * 64
CM, CD = "public.cierre_mensual", "public.cierre_mensual_detalle"
N = "141"
DOMINIO_11 = True


def _c(k, anio, mes, **kw):
    d = {"id": k, "anio": anio, "mes": mes, "criterio": "CAJA", "fecha_cierre": f"{anio}-{mes:02d}-28T16:08:29.989631",
         "user_id": 2, "gastos_esperados_total": 100.0, "gastos_reales_total": 150.0, "desv_gastos_total": 7.0,
         "liquidez_total": "0.00", "n_cotidianos": 0, "gastos_cotidianos_reales": 0}
    d.update(kw)
    return (CM, k, d)


def _d(k, padre, anio, mes, **kw):
    d = {"id": k, "cierre_id": padre, "anio": anio, "mes": mes, "tipo_detalle": "COTIDIANOS", "segmento_id": "COT-1",
         "esperado": 10.0, "real": 12.5, "desviacion": -2.5, "cumplimiento_pct": 1.25, "incluye_kpi": True,
         "fecha_cierre": "x", "user_id": 2}
    d.update(kw)
    return (CD, k, d)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    for k, v in (("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {}),
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("DOMINIO_11_ACTIVO", True)):
        monkeypatch.setattr(P5, k, v)


def _t(extra=()):
    return P5.transformar(T8._b0(T12._filas(extra=tuple(extra))), SHA, modo_lab=True)


def _met(ds, cl, codigo, co=CM):
    return ds.filas["cierre_metricas"].get(F.uuid_v3(co, cl, "cierre_metricas", codigo))


def test_cierre_es_snapshot_legacy_sin_recalculo():
    ds = _t([_c("K12", 2025, 12, liquidez_total="4562.75", n_cotidianos=45, gastos_cotidianos_reales=0)])
    (c,) = ds.filas["cierres_mensuales"].values()
    assert (c["periodo_desde"], c["periodo_hasta"], c["criterio"], c["origen_cierre"], c["metodologia_version"], c["estado"]) == \
        ("2025-12-01", "2025-12-31", "CAJA", "IMPORTADO_LEGACY", "V3_SNAPSHOT", "CERRADO")
    assert c["cerrado_at"] == "2025-12-28T16:08:29.989631+00:00"
    # desviacion V3 incoherente con esperado/real: se conserva tal cual
    assert _met(ds, "K12", "LEGACY_V3_DESV_GASTOS_TOTAL")["valor_numeric"] == Decimal("7.0")
    assert _met(ds, "K12", "LEGACY_V3_LIQUIDEZ_TOTAL")["valor_numeric"] == Decimal("4562.75")
    assert _met(ds, "K12", "LEGACY_V3_GASTOS_COTIDIANOS_REALES")["valor_numeric"] == 0  # cero real tras el rediseno


def test_campos_previos_al_rediseno_no_se_convierten_en_cero():
    ds = _t([_c("K08", 2025, 8)])
    for codigo in ("LEGACY_V3_LIQUIDEZ_TOTAL", "LEGACY_V3_N_COTIDIANOS", "LEGACY_V3_GASTOS_COTIDIANOS_REALES"):
        assert _met(ds, "K08", codigo) is None
    assert _met(ds, "K08", "LEGACY_V3_GASTOS_REALES_TOTAL")["valor_numeric"] == Decimal("150.0")


def test_valor_previo_al_rediseno_no_nulo_contradice_el_canon():
    with pytest.raises(P5.ErrorP5) as e:
        _t([_c("K08", 2025, 8, liquidez_total="12.00")])
    assert e.value.codigo == "S9_CAMPO_PREVIO_AL_REDISENO"


def test_desconocido_nunca_es_cero():
    ds = _t([_c("K12", 2025, 12, gastos_esperados_total=N)])
    assert _met(ds, "K12", "LEGACY_V3_GASTOS_ESPERADOS_TOTAL") is None


def test_metricas_legacy_deshabilitadas_para_cierres_nuevos():
    ds = _t([_c("K12", 2025, 12)])
    leg = [m for m in ds.filas["metricas_definicion"].values() if m["codigo"].startswith("LEGACY_V3_")]
    assert leg and all(m["enabled"] is False for m in leg)


def test_detalle_con_clave_de_desglose_y_valores_v3():
    ds = _t([_c("K12", 2025, 12), _d("D1", "K12", 2025, 12)])
    cid = F.uuid_v3(CM, "K12", "cierres_mensuales", "cierre")
    r = _met(ds, "D1", "LEGACY_V3_DETALLE_REAL", CD)
    assert (r["cierre_id"], r["clave_desglose"], r["valor_numeric"]) == (cid, "COTIDIANOS/COT-1", Decimal("12.5"))
    k = _met(ds, "D1", "LEGACY_V3_DETALLE_INCLUYE_KPI", CD)
    assert (k["valor_text"], k["valor_numeric"]) == ("true", None)


def test_detalle_sin_cierre_falla():
    with pytest.raises(P5.ErrorP5) as e:
        _t([_c("K12", 2025, 12), _d("D1", "KX", 2025, 12)])
    assert e.value.codigo == "S8_DETALLE_SIN_CIERRE"


def _gc(k, **kw):
    d = {"id": k, "nombre": f"BOLSA {k}", "tipo_id": "TX", "importe_cuota": 437.43, "importe": 120.0, "total": 0,
         "periodicidad": "MENSUAL", "activo": True, "fecha": "2025-06-30", "cuenta_id": "C1"}
    d.update(kw)
    return ("public.gastos", k, d)


@pytest.fixture
def contenedor(monkeypatch):
    monkeypatch.setattr(P5, "CONTENEDORES_PRESUPUESTARIOS", {"GC1"})
    monkeypatch.setattr(P5, "clasificar", lambda ds, co, cl, f: ("NULL", None))


def _linea(ds):
    (l,) = ds.filas["presupuesto_lineas"].values()
    return l


def test_contenedor_sin_decision_queda_pendiente(monkeypatch, contenedor):
    monkeypatch.setattr(P5, "PRESUPUESTO_CONTENEDORES_DECIDIDO", False)
    ds = _t([_c("K12", 2025, 12), _gc("GC1")])
    assert [p["codigo"] for p in ds.pendientes if p.get("dominio") == 11] == ["D11_PRESUPUESTO_SEMANTICA_NO_FIABLE"]
    assert ds.filas["presupuestos"] == {}


def test_presupuesto_del_mes_del_corte_con_objetivo_importe_cuota(contenedor):
    ds = _t([_c("K12", 2025, 12), _gc("GC1")])
    (p,) = ds.filas["presupuestos"].values()
    assert (p["periodo_desde"], p["periodo_hasta"], p["estado"], p["perspectiva"], p["moneda"], p["version_presupuesto"]) == \
        ("2026-09-01", "2026-09-30", "ACTIVO", "ATRIBUIBLE", "EUR", 1)
    l = _linea(ds)
    assert (l["tipo_linea"], l["naturaleza_economica"], l["importe_objetivo"], l["metodo_estimacion"]) == \
        ("BOLSA", "GASTO", Decimal("437.43"), "MANUAL")  # el restante V3 (120) no es el objetivo
    assert ds.filas["presupuesto_linea_alcances"] == {}  # sin categoria unica: sin alcance (D11-H)


def test_alcance_por_categoria_con_descendientes(monkeypatch, contenedor):
    monkeypatch.setattr(P5, "clasificar", lambda ds, co, cl, f: ("CAT", "00000000-0000-5000-8000-0000000000c1"))
    ds = _t([_c("K12", 2025, 12), _gc("GC1")])
    (a,) = ds.filas["presupuesto_linea_alcances"].values()
    assert (a["categoria_id"], a["incluir_descendientes"], a["presupuesto_linea_id"]) == \
        ("00000000-0000-5000-8000-0000000000c1", True, _linea(ds)["id"])


def test_presupuesto_sin_objetivo_conocido_falla(contenedor):
    with pytest.raises(P5.ErrorP5) as e:
        _t([_c("K12", 2025, 12), _gc("GC1", importe_cuota=N)])
    assert e.value.codigo == "S6_PRESUPUESTO_SIN_OBJETIVO"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_presupuesto_activo_via_borrador(contenedor):
    ds = _t([_c("K12", 2025, 12), _gc("GC1")])
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert (res["presupuestos"], res["presupuesto_lineas"]) == (1, 1)


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    ds = _t([_c("K08", 2025, 8), _c("K12", 2025, 12, liquidez_total="4562.75"), _d("D1", "K12", 2025, 12)])
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["cierres_mensuales"] == 2 and res["cierre_metricas"] == len(ds.filas["cierre_metricas"])
    assert res["metricas_definicion"] == 3 + sum(1 for m in ds.filas["metricas_definicion"].values())
