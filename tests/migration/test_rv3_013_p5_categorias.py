# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_013_p5_categorias.py
# Ruta: tests/migration/test_rv3_013_p5_categorias.py
# Descripcion: RV3 / P5 v0.13.0. D2-E opcion A: arbol de categorias canonico de
#              Migration V3 §15.2 como fuente suplementaria. Comprueba el arbol
#              embebido (93 nodos, 23 raices, jerarquia y orden), la trazabilidad
#              nodo -> registro origen, el ambito por raiz, el fallo cerrado
#              mientras la configuracion siga PROPUESTA y la carga fisica.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s8 = importlib.util.spec_from_file_location("t8", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
CATALOGOS_V3_REALES = True
SHA = "0" * 64
SHA_ARBOL = "1ace6cbaed87d1dfa4a35e7844d9064080aa6e094572b96d262db3835eb9910a"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    monkeypatch.setattr(P5, "DERECHOS_V3", [])


def _t(lab=True):
    return P5.transformar(T8._b0(T8._filas()), SHA, modo_lab=lab)


def test_arbol_embebido_es_el_canonico():
    assert hashlib.sha256(P5.ARBOL_CATEGORIAS_MV3.encode("utf-8")).hexdigest() == SHA_ARBOL
    nodos = P5.parsear_arbol(P5.ARBOL_CATEGORIAS_MV3)
    assert len(nodos) == 93 and sum(1 for r, _, _ in nodos if len(r) == 1) == 23
    rutas = {r for r, _, _ in nodos}
    assert ("VIVIENDA Y HOGAR", "Suministros", "Electricidad") in rutas
    assert all(r[:-1] in rutas for r in rutas if len(r) > 1)
    assert P5.RAICES_INGRESO <= {r[0] for r in rutas}


def test_arbol_mal_formado_o_duplicado_falla():
    with pytest.raises(P5.ErrorP5) as e:
        P5.parsear_arbol("A\n│   │   └── X")
    assert e.value.codigo == "S4_ARBOL_MAL_FORMADO"
    with pytest.raises(P5.ErrorP5) as e:
        P5.parsear_arbol("A\n├── X\n└── X")
    assert e.value.codigo == "S7_ARBOL_DUPLICADO"


def test_categorias_trazadas_con_jerarquia_ambito_y_orden():
    ds = _t()
    cats = ds.filas["categorias_financieras"]
    assert len(cats) == 93
    P5.verificar_trazabilidad(ds)
    el = cats[ds.categorias[("VIVIENDA Y HOGAR", "Suministros", "Electricidad")]]
    su = cats[el["parent_id"]]
    assert su["nombre"] == "Suministros" and el["orden"] == 0 and el["ambito"] == "GASTO"
    nom = cats[ds.categorias[("INGRESOS LABORALES", "Nómina")]]
    assert nom["ambito"] == "INGRESO" and nom["presupuestable_default"] is False and nom["codigo"] is None
    f = [x for x in ds.filas["fuentes_importacion"].values() if x["sha256"] == SHA_ARBOL]
    assert len(f) == 1 and f[0]["tipo_fuente"] == "OTRO"


def test_propuesta_falla_cerrada_fuera_de_lab(monkeypatch):
    with pytest.raises(P5.ErrorP5) as e:
        _t(lab=False)
    assert e.value.codigo == "S20_CATEGORIAS"
    monkeypatch.setattr(P5, "CATEGORIAS_ESTADO", "CONFIRMADA")
    assert len(_t(lab=False).filas["categorias_financieras"]) == 93


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    res = P5.validar_fisico(_t(), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["categorias_financieras"] == 93
