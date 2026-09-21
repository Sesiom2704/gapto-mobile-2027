# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_005_p5_dominio2.py
# Ruta: tests/migration/test_rv3_005_p5_dominio2.py
# Descripcion: RV3 / P5 v0.2.0. Corpus SINTETICO (sin PII) del dominio 2
#              parcial: la persona del propio tenant no se convierte en
#              tercero (C43 / R-RV3-008), naturaleza y roles no se deducen,
#              clasificacion mas especifica con jerarquia V3 demostrada,
#              ausencias 141 sin convertirse en valor, fallo cerrado ante
#              incoherencia rama/subsegmento o persona propia ambigua, y
#              orden de insercion padre->hijo.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
F = P5.fu
SHA = "0" * 64
EMAIL = "t@example.invalid"


def _b0():
    filas = [
        ("public.users", "7", {"id": 7, "email": EMAIL, "full_name": "Tenant Sintetico"}),
        ("public.tipo_ramas_proveedores", "R1", {"id": "R1", "nombre": "RAMA UNO"}),
        ("public.tipo_ramas_proveedores", "R2", {"id": "R2", "nombre": "RAMA DOS"}),
        ("public.tipo_subsegmentos_provee", "S1", {"id": "S1", "nombre": "SUB UNO", "rama_id": "R1", "activo": True}),
        ("public.proveedores", "P1", {"id": "P1", "nombre": "COMERCIO A", "rama_id": "R1", "subsegmento_id": "S1",
                                      "activo": True, "cif": "141", "email": "141", "telefono": "141",
                                      "persona_contacto": "141"}),
        ("public.proveedores", "P2", {"id": "P2", "nombre": "PROFESIONAL B", "rama_id": "R2", "subsegmento_id": "141",
                                      "activo": False, "cif": "141", "email": "141", "telefono": "141",
                                      "persona_contacto": "CONTACTO X"}),
        ("public.personas", "PE1", {"id": "PE1", "nombre_completo": "TENANT SINTETICO", "email": EMAIL.upper(),
                                     "dni": "00000000T", "telefono": "600000000", "fecha_nacimiento": "1990-01-01",
                                     "observaciones": "141", "inactivatedon": "141"}),
        ("public.personas", "PE2", {"id": "PE2", "nombre_completo": "OTRA PERSONA", "email": "141",
                                     "dni": "00000001R", "telefono": "141", "fecha_nacimiento": "141",
                                     "observaciones": "NOTA", "inactivatedon": "141"}),
    ]
    b0 = {}
    for i, (c, k, d) in enumerate(filas, 1):
        t = json.dumps(d, ensure_ascii=False)
        b0.setdefault(c, {})[k] = F.RegistroB0(c, k, d, t, F.hash_registro(t), f"r{i}", i)
    return b0


def _por_nombre(ds, tabla):
    return {f["nombre"]: f for f in ds.filas[tabla].values()}


def test_persona_propia_no_es_tercero_y_se_vincula_al_tenant():
    ds = P5.transformar(_b0(), SHA)
    assert "TENANT SINTETICO" not in _por_nombre(ds, "terceros")
    vinc = [m for m in ds.filas["mapeos_importacion"].values()
            if m["registro_origen_id"] == F.uuid_origen("public.personas", "PE1")]
    assert len(vinc) == 1 and vinc[0]["tipo_mapping"] == "VINCULADO" and vinc[0]["tabla_destino"] == "usuarios"
    assert any(e["regla"] == "D2-C" for e in ds.ledger)


def test_otra_persona_es_tercero_persona_con_subtipo():
    ds = P5.transformar(_b0(), SHA)
    t = _por_nombre(ds, "terceros")["OTRA PERSONA"]
    assert t["naturaleza"] == "PERSONA" and t["tipo_identificador_fiscal"] is None
    assert t["email"] is None and t["telefono"] is None
    assert ds.filas["tercero_personas"][t["id"]]["fecha_nacimiento"] is None


def test_proveedor_sin_naturaleza_ni_datos_inventados():
    ds = P5.transformar(_b0(), SHA)
    a = _por_nombre(ds, "terceros")["COMERCIO A"]
    assert a["naturaleza"] is None and a["identificador_fiscal"] is None and a["email"] is None
    assert a["notas"] is None and a["enabled"] is True
    b = _por_nombre(ds, "terceros")["PROFESIONAL B"]
    assert b["enabled"] is False and "CONTACTO X" in b["notas"]


def test_clasificacion_mas_especifica_y_jerarquia_v3():
    ds = P5.transformar(_b0(), SHA)
    clas = _por_nombre(ds, "clasificaciones_tercero")
    assert clas["SUB UNO"]["parent_id"] == clas["RAMA UNO"]["id"] and clas["RAMA UNO"]["parent_id"] is None
    ter = _por_nombre(ds, "terceros")
    asign = {tc["tercero_id"]: tc["clasificacion_id"] for tc in ds.filas["tercero_clasificaciones"].values()}
    assert asign[ter["COMERCIO A"]["id"]] == clas["SUB UNO"]["id"]
    assert asign[ter["PROFESIONAL B"]["id"]] == clas["RAMA DOS"]["id"]


def test_orden_insercion_padre_antes_que_hijo():
    ds = P5.transformar(_b0(), SHA)
    orden = P5.orden_insercion(ds, "clasificaciones_tercero")
    clas = _por_nombre(ds, "clasificaciones_tercero")
    assert orden.index(clas["RAMA UNO"]["id"]) < orden.index(clas["SUB UNO"]["id"])


def test_rama_subsegmento_incoherente_falla_cerrado():
    b0 = _b0()
    b0["public.proveedores"]["P1"].datos["rama_id"] = "R2"
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(b0, SHA)
    assert e.value.codigo == "S1_RAMA_SUBSEGMENTO_INCOHERENTE"


def test_persona_propia_ambigua_falla_cerrado():
    b0 = _b0()
    b0["public.personas"]["PE2"].datos["email"] = EMAIL
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(b0, SHA)
    assert e.value.codigo == "S20_PERSONA_PROPIA_AMBIGUA"


def test_sin_roles_deducidos():
    ds = P5.transformar(_b0(), SHA)
    assert "tercero_roles" not in ds.filas


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    ds = P5.transformar(_b0(), SHA)
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    for t in P5.ORDEN_TABLAS:
        assert res[t] >= len(ds.filas[t])


def test_orden_insercion_no_depende_del_orden_de_uuid():
    # Hijo con id lexicograficamente MENOR que el padre: solo la profundidad lo ordena bien.
    ds = P5.Dataset(owner="o")
    padre, hijo, nieto = "ffff", "0000", "0001"
    ds.filas["clasificaciones_tercero"] = {padre: {"id": padre, "parent_id": None},
                                           hijo: {"id": hijo, "parent_id": padre},
                                           nieto: {"id": nieto, "parent_id": hijo}}
    assert P5.orden_insercion(ds, "clasificaciones_tercero") == [padre, hijo, nieto]
