# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_007_p5_dominio4.py
# Ruta: tests/migration/test_rv3_007_p5_dominio4.py
# Descripcion: RV3 / P5 v0.4.0. Corpus SINTETICO (sin PII) del dominio 4,
#              subtipo PROPIEDAD: entidad + subtipo con misma identidad,
#              ausencias 141 nunca convertidas en valor, disponible ->
#              incluir_en_rentabilidad (Migration V3 §9), reparto 100 % con
#              vigencia desde la adquisicion demostrada, reparto parcial nunca
#              completado con cotitulares inventados (fallo cerrado S20 fuera
#              de laboratorio) y sin direccion ni geolocalizacion fabricadas.
# Versión: 0.1.0
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
PA = "public.patrimonio"


def _prop(ref, pct, **kw):
    base = {"id": ref, "referencia": ref, "tipo_inmueble": "VIVIENDA", "activo": True, "disponible": True,
            "fecha_adquisicion": "2020-01-15", "superficie_m2": "50.00", "superficie_construida": "141",
            "habitaciones": "2", "banos": "141", "garaje": False, "trastero": True, "participacion_pct": pct,
            "calle": "CALLE X", "localidad": "PUEBLO"}
    base.update(kw)
    return base


def _b0(extra=()):
    filas = [("public.users", "7", {"id": 7, "email": "t@example.invalid", "full_name": "Tenant"}),
             (PA, "V1", _prop("V1", "100")),
             (PA, "V2", _prop("V2", "50", disponible=False))] + list(extra)
    b0 = {}
    for i, (c, k, d) in enumerate(filas, 1):
        t = json.dumps(d, ensure_ascii=False)
        b0.setdefault(c, {})[k] = F.RegistroB0(c, k, d, t, F.hash_registro(t), f"r{i}", i)
    return b0


def _props(ds):
    ent = {e["id"]: e["nombre"] for e in ds.filas["entidades"].values()}
    return {ent[p["entidad_id"]]: p for p in ds.filas["propiedades"].values()}


def test_entidad_y_subtipo_comparten_identidad():
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    assert set(ds.filas["entidades"]) == set(ds.filas["propiedades"])
    assert all(e["tipo_entidad"] == "PROPIEDAD" for e in ds.filas["entidades"].values())


def test_ausencias_141_no_se_convierten_en_valor():
    p = _props(P5.transformar(_b0(), SHA, modo_lab=True))["V1"]
    assert p["superficie_m2"] == Decimal("50.00") and p["superficie_construida_m2"] is None
    assert p["habitaciones"] == 2 and p["banos"] is None


def test_disponible_significa_incluir_en_rentabilidad():
    p = _props(P5.transformar(_b0(), SHA, modo_lab=True))
    assert p["V1"]["incluir_en_rentabilidad"] is True and p["V2"]["incluir_en_rentabilidad"] is False


def test_sin_direccion_ni_geolocalizacion_fabricadas():
    p = _props(P5.transformar(_b0(), SHA, modo_lab=True))["V1"]
    assert p["direccion_id"] is None and p["latitud"] is None and p["geolocalizacion_origen"] is None


def test_reparto_100_con_vigencia_desde_adquisicion():
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    parts = list(ds.filas["entidad_participaciones"].values())
    assert len(parts) == 1 and parts[0]["porcentaje"] == Decimal(100)
    assert parts[0]["vigente_desde"] == "2020-01-15"


def test_reparto_parcial_no_se_completa_con_inventos():
    ds = P5.transformar(_b0(), SHA, modo_lab=True)
    v2 = next(e for e, x in ds.filas["entidades"].items() if x["nombre"] == "V2")
    assert not [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == v2]
    assert len(ds.filas["actores_financieros"]) == 1


def test_reparto_parcial_aislado_falla_s20():
    b0 = _b0()
    ds = P5.Dataset(owner="o")
    ds.filas["actores_financieros"]["self"] = {"id": "self"}
    fuente = {PA: {"V2": b0[PA]["V2"].datos}}
    with pytest.raises(P5.ErrorP5) as e:
        P5.dominio_4_propiedades(ds, fuente, P5.fu.contexto_de(fuente), modo_lab=False)
    assert e.value.codigo == "S20_COTITULAR_NO_IDENTIFICADO"


def test_tipo_de_propiedad_desconocido_falla_cerrado():
    b0 = _b0()
    b0[PA]["V1"].datos["tipo_inmueble"] = "141"
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(b0, SHA, modo_lab=True)
    assert e.value.codigo == "S4_TIPO_PROPIEDAD"
