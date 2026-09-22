# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_021_p5_r02_campos.py
# Ruta: tests/migration/test_rv3_021_p5_r02_campos.py
# Descripcion: RV3 / P5 v0.26.0. R02 (disposicion campo a campo) sobre corpus SINTETICO sin PII.
#              Discrimina: registro de columnas consumidas por la transformacion, clases de disposicion
#              declaradas (identidad, tenant, auditoria, canon), SIN_VALOR solo si ningun valor es
#              conocido, campo con valor sin disposicion -> S4, campo pendiente -> S20 bloqueante agrupado
#              por pregunta, y la instrumentacion no altera el dataset.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s8 = importlib.util.spec_from_file_location("t8_r02", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
F = P5.fu
C = "public.contenedor_test"
N = "141"
REAL_DISPOSICION, REAL_PENDIENTES = dict(P5.DISPOSICION_CAMPOS), dict(P5.CAMPOS_PENDIENTES)


def _ds():
    return P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))


def _fuente(*filas):
    return {C: {f["id"]: f for f in filas}}


def _r02(fuente, leidos=frozenset()):
    ds = _ds()
    return ds, P5.r02_disposicion_campos(ds, fuente, set(leidos))


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_CAMPOS", {(C, "declarado"): "CONTROL_DERIVADO: test"})
    monkeypatch.setattr(P5, "CAMPOS_PENDIENTES", {(C, "p1"): "Q-T-1", (C, "p2"): "Q-T-1", (C, "p3"): "Q-T-2"})


def test_clases_de_disposicion():
    fuente = _fuente({"id": "a", "user_id": 2, "createon": "2026-01-01", "declarado": 1, "vacio": N, "leido": 5},
                     {"id": "b", "user_id": 2, "createon": "2026-01-02", "declarado": 2, "vacio": "None", "leido": 6})
    ds, r = _r02(fuente, {(C, "leido")})
    assert r["R02_campos_b0"] == 6
    assert r["R02_por_clase"] == {"AUDITORIA_V3": 1, "CONSUMIDO": 1, "CONTROL_DERIVADO": 1, "IDENTIDAD_ORIGEN": 1,
                                  "SIN_VALOR": 1, "TENANT": 1}
    assert not ds.pendientes


def test_campo_con_un_solo_valor_no_es_sin_valor():
    with pytest.raises(P5.ErrorP5) as e:
        _r02(_fuente({"id": "a", "raro": N}, {"id": "b", "raro": "x"}))
    assert e.value.codigo == "S4_CAMPO_SIN_DISPOSICION" and f"{C}.raro (1 valores)" in str(e.value)


def test_campo_consumido_no_necesita_declaracion():
    _ds_, r = _r02(_fuente({"id": "a", "raro": "x"}), {(C, "raro")})
    assert r["R02_por_clase"]["CONSUMIDO"] == 1


def test_pendientes_agrupados_por_pregunta_y_bloqueantes():
    ds, r = _r02(_fuente({"id": "a", "p1": "x", "p2": "y", "p3": "z"}))
    assert r["R02_por_clase"]["PENDIENTE_S20"] == 3
    assert sorted((p["pregunta"], p["campos"], p["bloquea_gate"]) for p in ds.pendientes) == [
        ("Q-T-1", [f"{C}.p1 (1)", f"{C}.p2 (1)"], True), ("Q-T-2", [f"{C}.p3 (1)"], True)]


def test_pendiente_sin_valor_no_genera_pregunta():
    ds, r = _r02(_fuente({"id": "a", "p3": N}))
    assert r["R02_por_clase"].get("SIN_VALOR") == 1 and not ds.pendientes


def test_instrumentacion_registra_consumo_y_no_altera_el_dataset(monkeypatch):
    leidos = set()
    fuente = P5._instrumentar({C: {"a": {"id": "a", "x": 1, "y": 2}}}, leidos)
    fila = fuente[C]["a"]
    assert fila.get("x") == 1 and fila["y"] == 2 and "z" not in fila
    assert leidos == {(C, "x"), (C, "y"), (C, "z")}
    assert dict(fila) == {"id": "a", "x": 1, "y": 2}
    # el dataset real es identico con y sin instrumentacion
    b0 = T8._b0(T8._filas())
    for k, v in (("CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")}),
                 ("CONFIG_CUENTAS_ESTADO", "CONFIRMADA"), ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}),
                 ("DOMINIO_12_DISPOSICION_ACTIVO", False)):
        monkeypatch.setattr(P5, k, v)
    h0 = P5.transformar(b0, "0" * 64, modo_lab=True).hash()
    monkeypatch.setattr(P5.fu, "fuente_b0", lambda b, _r=P5.fu.fuente_b0: P5._instrumentar(_r(b), set()))
    assert P5.transformar(b0, "0" * 64, modo_lab=True).hash() == h0


def test_declaraciones_reales_no_se_solapan():
    assert not set(REAL_DISPOSICION) & set(REAL_PENDIENTES)
    assert all(v.split(":", 1)[0].isupper() for v in REAL_DISPOSICION.values())
