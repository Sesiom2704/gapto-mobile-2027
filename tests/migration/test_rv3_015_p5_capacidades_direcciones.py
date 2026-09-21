# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_015_p5_capacidades_direcciones.py
# Ruta: tests/migration/test_rv3_015_p5_capacidades_direcciones.py
# Descripcion: RV3 / P5 v0.15.0. Corpus SINTETICO (sin PII) de las respuestas
#              del propietario 2026-09-21: capacidades de cuenta SOLO declaradas
#              (D3-D), direccion de propiedad con localidad vinculada por nombre
#              exacto normalizado y fallo cerrado ante 0 / varias coincidencias
#              (D4-A), coordenadas MANUALES del propietario redondeadas a 6
#              decimales y nunca fabricadas (D4-G / D-184). Validacion fisica
#              con ROLLBACK si hay laboratorio RV3_IMPORT.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import json
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
F = P5.fu
SHA = "0" * 64
CB, PA = "public.cuentas_bancarias", "public.patrimonio"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                               (CB, "C2"): ("EFECTIVO", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})


def _prop(ref, localidad, **kw):
    d = {"id": ref, "referencia": ref, "tipo_inmueble": "VIVIENDA", "activo": True, "disponible": True,
         "fecha_adquisicion": "2020-01-15", "participacion_pct": "100", "calle": "CALLE X", "numero": "3",
         "piso": "2", "puerta": "B", "escalera": "141", "localidad": localidad}
    d.update(kw)
    return d


def _b0(props=None):
    filas = [
        ("public.users", "7", {"id": 7, "email": "t@example.invalid", "full_name": "Tenant"}),
        ("public.paises", "1", {"id": 1, "nombre": "ESPAÑA", "codigo_iso": "141"}),
        ("public.regiones", "1", {"id": 1, "nombre": "REGION A", "pais_id": 1}),
        ("public.regiones", "2", {"id": 2, "nombre": "REGION B", "pais_id": 1}),
        ("public.localidades", "1", {"id": 1, "nombre": "Pueblo Ñandú", "region_id": 1, "codigo_postal": "141"}),
        ("public.localidades", "2", {"id": 2, "nombre": "DOBLE", "region_id": 1, "codigo_postal": "141"}),
        ("public.localidades", "3", {"id": 3, "nombre": "DOBLE", "region_id": 2, "codigo_postal": "141"}),
        ("public.tipo_ramas_proveedores", "R1", {"id": "R1", "nombre": "BANCOS"}),
        ("public.proveedores", "PB", {"id": "PB", "nombre": "BANCO A", "rama_id": "R1", "subsegmento_id": "141", "activo": True}),
        (CB, "C1", {"id": "C1", "anagrama": "CTA UNO", "banco_id": "PB", "liquidez": "10.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "100.00", "activo": True}),
        (CB, "C2", {"id": "C2", "anagrama": "MONEDERO", "banco_id": "PB", "liquidez": "5.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "100.00", "activo": True}),
    ] + [(PA, p["id"], p) for p in (props if props is not None else [_prop("V1", "PUEBLO NANDU")])]
    b0 = {}
    for i, (c, k, d) in enumerate(filas, 1):
        t = json.dumps(d, ensure_ascii=False)
        b0.setdefault(c, {})[k] = F.RegistroB0(c, k, d, t, F.hash_registro(t), f"r{i}", i)
    return b0


def _dec(tmp_path, capacidades=(), geos=()):
    doc = {"id": "S", "personas": {}, "participaciones": [], "capacidades": list(capacidades),
           "geolocalizaciones": list(geos)}
    p = tmp_path / "d.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return P5.cargar_decisiones(p)


CAP_C1 = {"id": "CAP-1", "origen": f"{CB}/C1", "codigos": ["PAGAR_GASTO", "TRANSFERIR_SALIDA"]}
GEO_V1 = {"id": "GEO-1", "origen": f"{PA}/V1", "latitud": "37.98929989413326", "longitud": "-1.200768861210747"}


def _t(dec=None, props=None):
    return P5.transformar(_b0(props), SHA, modo_lab=False, decisiones=dec)


def _err(**kw):
    with pytest.raises(P5.ErrorP5) as e:
        _t(**kw)
    return e.value.codigo


def _prop_v1(ds):
    return next(iter(ds.filas["propiedades"].values()))


# ---------------------------------------------------------------- D3-D
def test_capacidades_solo_las_declaradas(tmp_path):
    ds = _t(_dec(tmp_path, [CAP_C1]))
    c1 = F.uuid_v3(CB, "C1", "cuentas", "cuenta")
    caps = {(c["cuenta_id"], c["capacidad_codigo"]) for c in ds.filas["cuenta_capacidades"].values()}
    assert caps == {(c1, "PAGAR_GASTO"), (c1, "TRANSFERIR_SALIDA")}  # C2 sin declaracion -> 0 filas


def test_capacidad_fuera_de_catalogo_o_repetida_falla(tmp_path):
    for cods in (["VOLAR"], ["PAGAR_GASTO", "PAGAR_GASTO"], []):
        with pytest.raises(P5.ErrorP5) as e:
            _dec(tmp_path, [{**CAP_C1, "codigos": cods}])
        assert e.value.codigo == "S4_DECISIONES_FORMATO"


def test_capacidad_sobre_cuenta_inexistente_falla(tmp_path):
    assert _err(dec=_dec(tmp_path, [{**CAP_C1, "origen": f"{CB}/C9"}])) == "S8_DECISION_SIN_ORIGEN"


def test_capacidades_trazadas_a_la_fuente_suplementaria(tmp_path):
    ds = _t(_dec(tmp_path, [CAP_C1]))
    origen = F.uuid_origen(P5.CONT_DECISIONES, "capacidad/CAP-1")
    maps = [m for m in ds.filas["mapeos_importacion"].values() if m["tabla_destino"] == "cuenta_capacidades"]
    assert len(maps) == 2 and all(m["registro_origen_id"] == origen for m in maps)


# ---------------------------------------------------------------- D4-A
def test_direccion_con_localidad_por_nombre_normalizado():
    ds = _t()
    d = ds.filas["direcciones"][_prop_v1(ds)["direccion_id"]]
    assert d["localidad_id"] == F.uuid_v3("public.localidades", "1", "localidades", "localidad")
    assert (d["via_nombre"], d["numero"], d["planta"], d["puerta"]) == ("CALLE X", "3", "2", "B")
    assert d["escalera"] is None and d["via_tipo"] is None and d["codigo_postal"] is None


def test_localidad_inexistente_falla_cerrado():
    assert _err(props=[_prop("V1", "OTRA")]) == "S8_LOCALIDAD_SIN_MAESTRO"


def test_localidad_ambigua_falla_cerrado():
    assert _err(props=[_prop("V1", "doble")]) == "S7_LOCALIDAD_AMBIGUA"


def test_sin_datos_de_direccion_no_hay_direccion():
    vacia = _prop("V1", "141", calle="141", numero="141", piso="141", puerta="141")
    ds = _t(props=[vacia])
    assert _prop_v1(ds)["direccion_id"] is None and not ds.filas["direcciones"]


# ---------------------------------------------------------------- D4-G
def test_coordenadas_manuales_redondeadas_a_6_decimales(tmp_path):
    p = _prop_v1(_t(_dec(tmp_path, geos=[GEO_V1])))
    assert (p["latitud"], p["longitud"], p["geolocalizacion_origen"]) == \
        (Decimal("37.989300"), Decimal("-1.200769"), "MANUAL")


def test_sin_declaracion_no_hay_coordenadas(tmp_path):
    p = _prop_v1(_t(_dec(tmp_path)))
    assert p["latitud"] is None and p["longitud"] is None and p["geolocalizacion_origen"] is None


def test_coordenada_fuera_de_rango_o_sin_origen_falla(tmp_path):
    with pytest.raises(P5.ErrorP5) as e:
        _dec(tmp_path, geos=[{**GEO_V1, "latitud": "91"}])
    assert e.value.codigo == "S4_DECISIONES_FORMATO"
    assert _err(dec=_dec(tmp_path, geos=[{**GEO_V1, "origen": f"{PA}/V9"}])) == "S8_DECISION_SIN_ORIGEN"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback(tmp_path):
    res = P5.validar_fisico(_t(_dec(tmp_path, [CAP_C1], [GEO_V1])), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert (res["cuenta_capacidades"], res["direcciones"], res["propiedades"]) == (2, 1, 1)
