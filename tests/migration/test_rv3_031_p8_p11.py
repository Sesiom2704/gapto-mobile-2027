# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_031_p8_p11.py
# Ruta: tests/migration/test_rv3_031_p8_p11.py
# Descripcion: RV3 / P8 post-carga, P9, P10 y P11 (v0.1.0) sobre corpus SINTETICO sin PII. Discrimina:
#              normalizacion y cuantizacion fisica admitida (y solo esa) en la igualdad material; P9 Probe A
#              (DELETE directo rechazado 23503) y Probe B (la secuencia UPDATE+DELETE se ejecuta y se clasifica);
#              RLS con tenant ajeno sin filas; P10 NO_CERRADO ante delta sin explicacion o R en FAIL; P11 replay:
#              carga identica -> YA_APLICADA_SIN_CAMBIOS sin xid, carga distinta o parcial -> S7_CONFLICTO_REPLAY.
#              Los casos de laboratorio usan el laboratorio de REFERENCIA dentro de transacciones revertidas.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import decimal
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MV3 = RAIZ / "scripts" / "migration_v3"


def _mod(nombre, fichero):
    s = importlib.util.spec_from_file_location(nombre, MV3 / fichero)
    m = importlib.util.module_from_spec(s)
    sys.modules[nombre] = m
    s.loader.exec_module(m)
    return m


P6 = _mod("rv3_p6_carga", "rv3_p6_carga.py")
P5 = P6.cargar_p5()
P8M = _mod("rv3_p8_material", "rv3_p8_material.py")
P9 = _mod("rv3_p9_runtime", "rv3_p9_runtime.py")
P10 = _mod("rv3_p10_ledger", "rv3_p10_ledger.py")
_s8 = importlib.util.spec_from_file_location("t8_p811", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
CB = "public.cuentas_bancarias"
DOMINIO_5 = True
DOMINIO_12 = True
URL = os.environ.get("GAPTO_RV3_IMPORT_URL")
lab = pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})


def _ds():
    return P5.transformar(T8._b0(T8._filas()), "0" * 64, modo_lab=True)


# ---------------------------------------------------------------- P8 igualdad material
def test_normalizacion_y_cuantizacion_admitida():
    D = decimal.Decimal
    assert P8M.normalizar(D("100.0000")) == P8M.normalizar(100) and P8M.normalizar(uuid.UUID(int=1)) == str(uuid.UUID(int=1))
    assert P8M.cuantizado_fisico("-588.1099999999998", D("-588.110000"))
    assert P8M.cuantizado_fisico("1.317359507", D("1.317360"))
    assert not P8M.cuantizado_fisico("-588.12", D("-588.110000"))  # distinto de verdad: no se admite
    assert not P8M.cuantizado_fisico("x", D("1.000000")) and not P8M.cuantizado_fisico(None, D("1"))


def test_comparar_celdas_separa_cuantizacion_de_diferencia():
    ds = P5.Dataset(owner="o")
    ds.filas["cierre_metricas"] = {"a": {"id": "a", "v": "1.1000000001"}, "b": {"id": "b", "v": "2.5"}}
    mat = {t: {} for t in P5.ORDEN_TABLAS}
    mat["cierre_metricas"] = {"a": {"id": "a", "v": decimal.Decimal("1.100000")},
                              "b": {"id": "b", "v": decimal.Decimal("2.400000")}}
    for t in P5.ORDEN_TABLAS:
        if t != "cierre_metricas":
            ds.filas[t] = {}
    q = {}
    dif = P8M.comparar_celdas(P5, mat, ds, q)
    assert dif == {"cierre_metricas": {"faltan": 0, "sobran": 0, "celdas_distintas": 1}}
    assert q["cierre_metricas.v"]["celdas"] == 1


# ---------------------------------------------------------------- P10 ledger
def test_p10_no_cerrado_ante_delta_sin_explicacion_o_fail():
    p8 = {"resultados": [{"id": "R12", "estado": "DELTA_CLASIFICADO", "descripcion": "x", "esperado": 1,
                          "obtenido": 2, "explicacion": None},
                         {"id": "R09", "estado": "FAIL", "descripcion": "y", "esperado": 1, "obtenido": 2}]}
    r = P10.construir(p8, {}, {"D6-A": 1, "REGLA-SIN-TEXTO": 2}, {"D6-A": "texto"})
    assert r["veredicto"] == "NO_CERRADO"
    assert set(r["sin_clasificar"]) == {"L-R12", "L-R09", "L-REGLA-REGLA-SIN-TEXTO"}
    ok = P10.construir({"resultados": [{"id": "R01", "estado": "PASS"}]}, {}, {"D6-A": 1}, {"D6-A": "t"})
    assert ok["veredicto"] == "CERRADO"


# ---------------------------------------------------------------- laboratorio de referencia (ROLLBACK)
def _admin_dsn():
    partes = dict(p.split("=", 1) for p in URL.split())
    partes["user"] = "postgres"
    return " ".join(f"{k}={v}" for k, v in partes.items())


@pytest.fixture
def cargado():
    """Carga sintetica sin confirmar en el laboratorio de referencia; se revierte siempre."""
    import psycopg
    ds = _ds()
    with psycopg.connect(_admin_dsn()) as c:
        assert c.execute("SELECT current_database()").fetchone()[0] not in ("gapto2027_p6", "gapto2027_p11")
        with c.transaction(force_rollback=True):
            with c.transaction():
                P6._contexto(c, ds.owner)
                P6.cargar(P5, c, ds)
                c.execute("RESET ROLE")
            yield c, ds


@lab
def test_p9_probe_a_rechaza_delete_directo(cargado):
    c, ds = cargado
    pos = P9._posiciones(c)
    assert pos
    r = P9.probe_a(c, ds.owner, pos)
    assert r["resultado"] == "PASS" and r["rechazadas_23503"] == len(pos)


@lab
def test_p9_probe_b_ejecuta_y_clasifica(cargado):
    c, ds = cargado
    P5B = P9._p5b()
    r = P9.probe_b(c, ds.owner, P9._posiciones(c), P5B)
    assert r["posiciones"] == r["evadidas"] + r["bloqueadas"] and r["posiciones"] > 0
    assert all(d["pasos"] for d in r["detalle"])  # la secuencia se ejecuto, no se infirio
    assert c.execute("SELECT count(*) FROM gapto.entidades").fetchone()[0] == len(ds.filas["entidades"])


@lab
def test_p9_rls_tenant_ajeno_y_acl(cargado):
    c, ds = cargado
    r = P9.sonda_rls(c, ds.owner)
    assert r["por_contexto"]["ajeno"]["visibles"] == 0 and r["por_contexto"]["propio"]["visibles"] == r["filas_tenant_reales"]
    assert r["escritura_owner_ajeno"]["resultado"] == "RECHAZADA"
    assert P9.sonda_acl(c)["resultado"] == "PASS"


@lab
def test_p11_replay_identico_sin_xid(cargado):
    c, ds = cargado
    with c.transaction():
        P6._contexto(c, ds.owner)
        r = P6.detectar_replay(P5, c, ds)
        c.execute("RESET ROLE")
    assert r["resultado"] == "YA_APLICADA_SIN_CAMBIOS" and r["filas_comparadas"] == sum(len(v) for v in ds.filas.values())


@lab
def test_p11_replay_con_contenido_distinto_es_conflicto(cargado):
    c, ds = cargado
    t = next(t for t in ("hechos_financieros", "terceros") if ds.filas[t])
    k = sorted(ds.filas[t])[0]
    col = "concepto" if t == "hechos_financieros" else "nombre"
    ds.filas[t][k] = {**ds.filas[t][k], col: "ALTERADO"}
    with c.transaction():
        P6._contexto(c, ds.owner)
        with pytest.raises(P6.StopP6) as e:
            P6.detectar_replay(P5, c, ds)
        c.execute("RESET ROLE")
    assert e.value.codigo == "S7_CONFLICTO_REPLAY"


@lab
def test_p11_replay_con_fuentes_parciales_es_conflicto(cargado):
    c, ds = cargado
    ds.filas["fuentes_importacion"][str(uuid.uuid4())] = {"id": "x"}  # una fuente del dataset no esta en la BD
    with c.transaction():
        P6._contexto(c, ds.owner)
        with pytest.raises(P6.StopP6) as e:
            P6.detectar_replay(P5, c, ds)
        c.execute("RESET ROLE")
    assert e.value.codigo == "S7_CONFLICTO_REPLAY"


def test_p11_bd_vacia_no_es_replay():
    class C:
        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return []
    ds = P5.Dataset(owner="o")
    ds.filas["fuentes_importacion"] = {"f": {"id": "f"}}
    assert P6.detectar_replay(P5, C(), ds) is None
