# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_029_p6_carga.py
# Ruta: tests/migration/test_rv3_029_p6_carga.py
# Descripcion: RV3 / P6 v0.1.0 (rv3_p6_carga.py) sobre corpus SINTETICO sin PII. Discrimina: STOP por hash distinto
#              del autorizado; comparacion fila a fila por PK; en laboratorio (RV3_IMPORT) ensayo completo sin
#              --commit que carga, pasa las comprobaciones pre-COMMIT y revierte dejando la BD virgen; carga no
#              exacta -> S8_CARGA_NO_EXACTA; BD no virgen -> S2_BD_NO_VIRGEN.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("rv3_p6_carga", RAIZ / "scripts" / "migration_v3" / "rv3_p6_carga.py")
P6 = importlib.util.module_from_spec(_s)
sys.modules["rv3_p6_carga"] = P6
_s.loader.exec_module(P6)
P5 = P6.cargar_p5()
_s8 = importlib.util.spec_from_file_location("t8_p6", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
CB = "public.cuentas_bancarias"
DOMINIO_5 = True
DOMINIO_12 = True
URL = os.environ.get("GAPTO_RV3_IMPORT_URL")


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})


def _ds():
    return P5.transformar(T8._b0(T8._filas()), "0" * 64, modo_lab=True)


def test_hash_distinto_es_stop():
    P6.comprobar_hash("a" * 64, "a" * 64)
    with pytest.raises(P6.StopP6) as e:
        P6.comprobar_hash("a" * 64, "b" * 64)
    assert e.value.codigo == "S7_HASH_DATASET_DISTINTO"


def test_diferencias_ids():
    assert P6.diferencias_ids({"t": {"1", "2"}}, {"t": {"1", "2"}}) == {}
    assert P6.diferencias_ids({"t": {"1", "2"}}, {"t": {"2", "3", "4"}}) == {"t": {"faltan": 1, "sobran": 2}}


@pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")
def test_ensayo_sin_commit_carga_verifica_y_revierte():
    ds = _ds()
    ev = P6.ejecutar(P5, ds, URL, commit=False)
    assert ev["commit"].startswith("ROLLBACK") and ev["pre_commit"]["mapeos_destino_inexistente"] == 0
    assert ev["filas_insertadas"] == sum(len(v) for v in ds.filas.values())
    assert ev["perfil"][1] == "gapto_owner"
    assert P6.ejecutar(P5, ds, URL, commit=False)["virgen"]  # sigue virgen: el ensayo no dejo filas


@pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")
def test_carga_no_exacta_es_stop(monkeypatch):
    ds = _ds()
    real = P6.cargar

    def carga_y_desaparece(P5_, c, d):
        n = real(P5_, c, d)
        t = "hechos_financieros" if d.filas["hechos_financieros"] else "terceros"
        d.filas[t].pop(sorted(d.filas[t])[0])  # el dataset esperado ya no coincide con lo cargado
        return n
    monkeypatch.setattr(P6, "cargar", carga_y_desaparece)
    with pytest.raises(P6.StopP6) as e:
        P6.ejecutar(P5, ds, URL, commit=False)
    assert e.value.codigo == "S8_CARGA_NO_EXACTA"


@pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")
def test_bd_no_virgen_es_stop():
    import psycopg
    ds = _ds()
    with psycopg.connect(URL) as c:
        P6._contexto(c, ds.owner)
        P6.cargar(P5, c, ds)
        with pytest.raises(P6.StopP6) as e:
            P6.verificar_virgen(P5, c)
        c.rollback()
    assert e.value.codigo == "S2_BD_NO_VIRGEN"
