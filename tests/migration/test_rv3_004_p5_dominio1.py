# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_004_p5_dominio1.py
# Ruta: tests/migration/test_rv3_004_p5_dominio1.py
# Descripcion: RV3 / P5 v0.1.0. Corpus SINTETICO (sin PII) para el dominio 1
#              (tenant/geografia) y la base del dominio 12 (trazabilidad):
#              determinismo e independencia de orden (G4), UNKNOWN nunca como
#              valor (G8), trazabilidad destino->origen (R05), fallo cerrado
#              ante colision (S7), pais sin referencia (S4) o contradictorio,
#              actor self unico. Validacion fisica opcional con
#              GAPTO_RV3_IMPORT_URL (perfil RV3_IMPORT, siempre ROLLBACK).
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / "migration_v3" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


P5 = _cargar("rv3_p5_transformacion")
F = P5.fu
SHA = "0" * 64


def _reg(cont, clave, datos, fila=1):
    texto = json.dumps(datos, ensure_ascii=False)
    return F.RegistroB0(cont, clave, datos, texto, F.hash_registro(texto), f"run06-{clave}", fila)


def _b0(orden_inverso=False):
    filas = [
        ("public.users", "7", {"id": 7, "email": "t@example.invalid", "full_name": "Tenant Sintetico",
                                "password": "***REDACTED***", "role": "admin", "is_active": True}),
        ("public.paises", "1", {"id": 1, "nombre": "ESPAÑA", "codigo_iso": "141"}),
        ("public.regiones", "1", {"id": 1, "nombre": "REGION A", "pais_id": 1}),
        ("public.regiones", "2", {"id": 2, "nombre": "PROVINCIA B", "pais_id": 1}),
        ("public.localidades", "1", {"id": 1, "nombre": "PUEBLO", "region_id": 1, "codigo_postal": "141"}),
        ("public.localidades", "2", {"id": 2, "nombre": "CIUDAD", "region_id": 2, "codigo_postal": "30001"}),
    ]
    # numero_fila_origen es dato de la fuente: se fija por registro, no por orden de lectura.
    filas = [(c, k, d, i) for i, (c, k, d) in enumerate(filas, 1)]
    if orden_inverso:
        filas = list(reversed(filas))
    b0 = {}
    for c, k, d, i in filas:
        b0.setdefault(c, {})[k] = _reg(c, k, d, i)
    return b0


def test_determinismo_e_independencia_de_orden():
    a = P5.transformar(_b0(), SHA)
    b = P5.transformar(_b0(), SHA)
    c = P5.transformar(_b0(orden_inverso=True), SHA)
    assert a.hash() == b.hash() == c.hash()
    assert a.filas == c.filas


def test_owner_deriva_de_la_clave_v3_no_del_email():
    b0 = _b0()
    b0["public.users"]["7"].datos["email"] = "otro@example.invalid"
    assert P5.transformar(b0, SHA).owner == P5.transformar(_b0(), SHA).owner


def test_141_postal_no_se_convierte_en_valor_y_el_literal_se_conserva():
    ds = P5.transformar(_b0(), SHA)
    locs = {l["nombre"]: l for l in ds.filas["localidades"].values()}
    assert locs["PUEBLO"]["codigo_oficial"] is None and locs["PUEBLO"]["codigo_oficial_tipo"] is None
    assert locs["CIUDAD"]["codigo_oficial"] == "30001"
    orig = ds.filas["registros_origen_importacion"][F.uuid_origen("public.localidades", "1")]
    assert '"codigo_postal": "141"' in orig["datos_origen_texto"]


def test_regiones_sin_jerarquia_ni_tipo_inventados():
    ds = P5.transformar(_b0(), SHA)
    assert all(r["parent_region_id"] is None and r["tipo_region"] is None for r in ds.filas["regiones"].values())


def test_un_unico_actor_self():
    ds = P5.transformar(_b0(), SHA)
    act = list(ds.filas["actores_financieros"].values())
    assert len(act) == 1 and act[0]["tercero_id"] is None and act[0]["owner_user_id"] == ds.owner


def test_todo_destino_tiene_mapeo_y_origen_exacto():
    ds = P5.transformar(_b0(), SHA)
    assert len(ds.filas["registros_origen_importacion"]) == 6
    for r in ds.filas["registros_origen_importacion"].values():
        assert F.hash_registro(r["datos_origen_texto"]) == r["sha256_registro"]


def test_mutante_mapping_omitido_falla_cerrado():
    ds = P5.transformar(_b0(), SHA)
    victima = sorted(ds.filas["mapeos_importacion"])[0]
    del ds.filas["mapeos_importacion"][victima]
    with pytest.raises(P5.ErrorP5) as e:
        P5.verificar_trazabilidad(ds)
    assert e.value.codigo == "S8_DESTINO_SIN_ORIGEN"


def test_colision_de_identidad_falla_cerrado():
    ds = P5.transformar(_b0(), SHA)
    fila = copy.deepcopy(next(iter(ds.filas["regiones"].values())))
    fila["nombre"] = "DISTINTO"
    with pytest.raises(P5.ErrorP5) as e:
        ds.add("regiones", fila)
    assert e.value.codigo == "S7_COLISION_UUID"


def test_pais_sin_referencia_falla_cerrado():
    b0 = _b0()
    b0["public.paises"]["1"].datos["nombre"] = "PAIS DESCONOCIDO"
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(b0, SHA)
    assert e.value.codigo == "S4_PAIS_SIN_REFERENCIA"


def test_iso_v3_conocido_y_contradictorio_falla_cerrado():
    b0 = _b0()
    b0["public.paises"]["1"].datos["codigo_iso"] = "FR"
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(b0, SHA)
    assert e.value.codigo == "S1_ISO_CONTRADICTORIO"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    ds = P5.transformar(_b0(), SHA)
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["_rol"][0] == "gapto_owner"
    for t in P5.ORDEN_TABLAS:
        assert res[t] >= len(ds.filas[t])
