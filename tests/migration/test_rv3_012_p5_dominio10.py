# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_012_p5_dominio10.py
# Ruta: tests/migration/test_rv3_012_p5_dominio10.py
# Descripcion: RV3 / P5 v0.11.0. Corpus SINTETICO (sin PII) del dominio 10:
#              contratos (tipo y estado por tabla cerrada, fecha corregida validada),
#              participantes con vigencias sin solape (sustitucion historica), persona
#              propia como actor self, clausula de revision IPC/NINGUNA, sin servicios
#              fabricados, y valoraciones de propiedad con total_inversion comprobado.
# Versión: 0.1.0
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
_s8 = importlib.util.spec_from_file_location("t8", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
F = P5.fu
SHA = "0" * 64
CC, CP, PC = "public.contratos", "public.contratos_participantes", "public.patrimonio_compra"
N = "141"


def _filas(con=None, pc=None, extra=()):
    c = {"id": "K1", "patrimonio_id": "V1", "estado": "activo", "objeto_alquiler": "completa",
         "fecha_inicio": "2024-09-01", "fecha_fin": N, "incremento_ipc": True, "observaciones": "RENTA X"}
    c.update(con or {})
    compra = {"patrimonio_id": "V1", "valor_compra": 100, "impuestos_eur": 8, "notaria": N, "agencia": 0,
              "reforma_adecuamiento": "2.00", "total_inversion": "110.00", "fecha_compra": N,
              "valor_mercado": "150.00", "valor_mercado_fecha": "2026-01-12", "valor_referencia": "60.00"}
    compra.update(pc or {})
    return T8._filas() + [
        ("public.personas", "PSELF", {"id": "PSELF", "nombre_completo": "Tenant", "email": "t@example.invalid"}),
        ("public.personas", "PI", {"id": "PI", "nombre_completo": "Inquilina", "email": "i@example.invalid"}),
        ("public.personas", "PA2", {"id": "PA2", "nombre_completo": "Avalista", "email": "a@example.invalid"}),
        (CC, "K1", c),
        (CP, "P1", {"id": "P1", "contrato_id": "K1", "persona_id": "PI", "rol": "inquilino", "es_principal": True, "inactivatedon": N}),
        (CP, "P2", {"id": "P2", "contrato_id": "K1", "persona_id": "PSELF", "rol": "gestor", "es_principal": False, "inactivatedon": N}),
        (CP, "P3", {"id": "P3", "contrato_id": "K1", "persona_id": "PA2", "rol": "avalista", "es_principal": False,
                    "inactivatedon": "2026-03-07T16:41:46+00:00"}),
        (CP, "P4", {"id": "P4", "contrato_id": "K1", "persona_id": "PA2", "rol": "avalista", "es_principal": False, "inactivatedon": N}),
        (PC, "V1", compra)] + list(extra)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    monkeypatch.setattr(P5, "FECHA_INICIO_CONTRATO_VALIDADA", {})


def _t(**kw):
    return P5.transformar(T8._b0(_filas(**kw)), SHA, modo_lab=True)


def _err(**kw):
    with pytest.raises(P5.ErrorP5) as e:
        _t(**kw)
    return e.value.codigo


def _k(ds):
    return ds.filas["contratos"][F.uuid_v3(CC, "K1", "entidades", "contrato")]


def _p(ds, k):
    return ds.filas["contrato_participantes"][F.uuid_v3(CP, k, "contrato_participantes", "participante")]


def test_contrato_formalizado_con_tipo_mapeado_y_sin_renta_aun():
    k = _k(_t())
    assert (k["tipo_contrato"], k["estado_documental"], k["fecha_inicio"], k["fecha_fin_prevista"], k["regla_renta_id"]) == \
        ("ALQUILER_VIVIENDA", "FORMALIZADO", "2024-09-01", None, None)
    assert k["propiedad_entidad_id"] == F.uuid_v3("public.patrimonio", "V1", "entidades", "propiedad")


def test_fecha_validada_prevalece_y_origen_se_conserva(monkeypatch):
    monkeypatch.setattr(P5, "FECHA_INICIO_CONTRATO_VALIDADA", {"K1": "2025-01-01"})
    ds = _t()
    assert _k(ds)["fecha_inicio"] == "2025-01-01"
    orig = [r for r in ds.filas["registros_origen_importacion"].values() if r["clave_origen"] == "K1"][0]
    assert orig["datos_origen"]["fecha_inicio"] == "2024-09-01"


def test_valor_v3_sin_mapping_falla():
    assert _err(con={"objeto_alquiler": "local"}) == "S4_CONTRATO_SIN_MAPPING"
    assert _err(con={"estado": "borrado"}) == "S4_CONTRATO_SIN_MAPPING"


def test_participantes_self_y_sustitucion_sin_solape():
    ds = _t()
    assert _p(ds, "P2")["actor_id"] == ds.self_id and _p(ds, "P2")["rol"] == "GESTOR"
    assert _p(ds, "P1")["principal"] is True and _p(ds, "P1")["vigente_desde"] == "2024-09-01"
    viejo, nuevo = _p(ds, "P3"), _p(ds, "P4")
    assert (viejo["vigente_desde"], viejo["vigente_hasta"]) == ("2024-09-01", "2026-03-06")
    assert (nuevo["vigente_desde"], nuevo["vigente_hasta"]) == ("2026-03-07", None)


def test_revision_ipc_y_ninguna():
    ds = _t()
    assert [r["tipo_revision"] for r in ds.filas["contrato_revision_renta_versiones"].values()] == ["IPC"]
    ds = _t(con={"incremento_ipc": False})
    r = list(ds.filas["contrato_revision_renta_versiones"].values())[0]
    assert r["tipo_revision"] == "NINGUNA" and r["periodicidad_meses"] is None


def test_sin_servicios_ni_contextos_fabricados():
    ds = _t()
    assert not [e for e in ds.filas["entidades"].values() if e["tipo_entidad"] in ("SERVICIO", "CONTEXTO")]


def test_valoraciones_por_metodo_y_total_comprobado():
    ds = _t()
    v = {x["metodo"]: x for x in ds.filas["propiedad_valoraciones"].values()}
    assert set(v) == {"COMPRA", "MERCADO", "FISCAL_REFERENCIA"}
    assert (v["COMPRA"]["valor_total"], v["COMPRA"]["fecha_valoracion"]) == (Decimal("100"), "2020-01-15")
    assert (v["MERCADO"]["fecha_valoracion"], v["FISCAL_REFERENCIA"]["fecha_valoracion"]) == ("2026-01-12", None)
    assert _err(pc={"total_inversion": "111.00"}) == "S9_TOTAL_INVERSION_NO_CUADRA"


def test_valor_desconocido_no_crea_valoracion():
    ds = _t(pc={"valor_referencia": N})
    assert "FISCAL_REFERENCIA" not in {x["metodo"] for x in ds.filas["propiedad_valoraciones"].values()}


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    res = P5.validar_fisico(_t(), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert (res["contratos"], res["contrato_participantes"], res["propiedad_valoraciones"]) == (1, 4, 3)
