# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_014_p5_clasificacion.py
# Ruta: tests/migration/test_rv3_014_p5_clasificacion.py
# Descripcion: RV3 / P5 v0.14.0. Clasificacion de registros operativos V3:
#              decision por registro > tabla por tipo; FUERA para naturalezas que no
#              son categoria; tipo heterogeneo sin decision -> S20; ruta no canonica
#              -> S1; decision sobre registro inexistente -> S8; desglose que no
#              cuadra con el total -> S9. Tabla real: 52 tipos, rutas canonicas.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import json
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
G, GC = "public.gastos", "public.gastos_cotidianos"
REAL = dict(P5.CATEGORIA_POR_TIPO_V3)


def _filas(*extra):
    base = [f for f in T8._filas() if f[0] != G]
    return base + [
        ("public.tipo_gasto", "TC", {"id": "TC", "nombre": "COMIDA"}),
        ("public.tipo_gasto", "TX", {"id": "TX", "nombre": "CAPRICHOS"}),
        ("public.tipo_gasto", "TA", {"id": "TA", "nombre": "AHORRO"}),
        (GC, "C1", {"id": "C1", "tipo_id": "TC", "importe": 5}),
        (G, "X1", {"id": "X1", "tipo_id": "TX", "nombre": "REGALO", "importe": 15, "total": 15}),
        (G, "A1", {"id": "A1", "tipo_id": "TA", "nombre": "TRASPASO", "importe": 100}),
    ] + list(extra)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    monkeypatch.setattr(P5, "DERECHOS_V3", [])
    monkeypatch.setattr(P5, "CATEGORIA_POR_TIPO_V3", {"TC": "SUPERMERCADOS", "TX": "POR_REGISTRO", "TA": "FUERA: transferencia",
                                                      "TF": "FUERA: compra financiada", "TH": "FUERA: cuota",
                                                      "TP": "FUERA: cuota"})


def _dec(tmp_path, registros):
    doc = {"id": "S", "personas": {}, "participaciones": [],
           "clasificacion": {"id": "CAT-S", "registros": registros}}
    p = tmp_path / "d.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return P5.cargar_decisiones(p)


def _t(dec=None, filas=None):
    return P5.transformar(T8._b0(filas or _filas()), SHA, modo_lab=True, decisiones=dec)


def _err(**kw):
    with pytest.raises(P5.ErrorP5) as e:
        _t(**kw)
    return e.value.codigo


def test_tabla_real_cubre_52_tipos_con_rutas_canonicas():
    rutas = {" > ".join(P5._norm(x) for x in r) for r, _, _ in P5.parsear_arbol(P5.ARBOL_CATEGORIAS_MV3)}
    assert len(REAL) == 52
    for v in REAL.values():
        assert v in rutas or v in ("POR_REGISTRO", "SIN_USO") or v.startswith("FUERA:"), v


def test_registro_decidido_prevalece_y_tipo_resuelve_el_resto(tmp_path):
    ds = _t(_dec(tmp_path, {f"{G}/X1": "REGALOS Y DETALLES"}))
    assert ds.clasificacion == {"CAT": 2, "FUERA": 1}
    k, cid = P5.clasificar(ds, G, "X1", {"tipo_id": "TX"})
    assert k == "CAT" and ds.filas["categorias_financieras"][cid]["nombre"] == "REGALOS Y DETALLES"
    assert P5.clasificar(ds, G, "A1", {"tipo_id": "TA"}) == ("FUERA", "transferencia")


def test_tipo_heterogeneo_sin_decision_falla_s20():
    assert _err() == "S20_CLASIFICACION_REGISTRO"


def test_null_decidido_no_inventa_categoria(tmp_path):
    ds = _t(_dec(tmp_path, {f"{G}/X1": None}))
    assert ds.clasificacion == {"CAT": 1, "NULL": 1, "FUERA": 1}


def test_ruta_no_canonica_y_registro_inexistente_fallan(tmp_path):
    assert _err(dec=_dec(tmp_path, {f"{G}/X1": "REGALOS INVENTADOS"})) == "S1_CATEGORIA_NO_CANONICA"
    assert _err(dec=_dec(tmp_path, {f"{G}/X1": None, f"{G}/NOEXISTE": None})) == "S8_CLASIFICACION_SIN_ORIGEN"


def test_desglose_debe_cuadrar(tmp_path):
    ok = {"desglose": [["DEPORTE > CARRERAS Y COMPETICIONES", "10"], ["RESTAURANTES", "4"], ["OCIO Y CULTURA > LOTERIA", "1"]]}
    ds = _t(_dec(tmp_path, {f"{G}/X1": ok}))
    assert ds.clasificacion["DESGLOSE"] == 1
    malo = {"desglose": [["RESTAURANTES", "14"]]}
    assert _err(dec=_dec(tmp_path, {f"{G}/X1": malo})) == "S9_DESGLOSE_NO_CUADRA"


def test_tipo_sin_tabla_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(P5, "CATEGORIA_POR_TIPO_V3", {"TC": "SUPERMERCADOS"})
    assert _err(dec=_dec(tmp_path, {f"{G}/X1": None})) == "S4_TIPO_SIN_CLASIFICACION"
