# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_020_p5_dominio12_disposicion.py
# Ruta: tests/migration/test_rv3_020_p5_dominio12_disposicion.py
# Descripcion: RV3 / P5 v0.25.0. Resto del dominio 12 — R05 completo sobre corpus SINTETICO sin PII.
#              Discrimina: todo origen con disposicion (origen sin disposicion -> S8), mapeo a destino
#              inexistente -> S8 (R-RV3-002), gasto V3 de referencia de cuota VINCULADO a su financiacion
#              (D5-T), taxonomia V3 reemplazada (D-MIG-001) sin destino con codigo de disposicion
#              PROPUESTO: pendiente S20 bloqueante en ambos modos, materializada solo en laboratorio,
#              taxonomia con destino contradictoria -> S1, decision de clasificacion VINCULADA solo a los
#              destinos donde se aplico (GASTO/INGRESO y versiones de regla) con verificacion de
#              coherencia (S9), determinismo y carga fisica RV3_IMPORT con ROLLBACK.
#   0.2.0: OBSOLETO CONFIRMADO por el propietario (P5 v0.26.0); la rama PROPUESTA se ejercita
#          explicitamente para conservar su discriminacion.
# Versión: 0.2.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s8 = importlib.util.spec_from_file_location("t8_d12", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
F = P5.fu
SHA = "0" * 64
CB, GA, TG = "public.cuentas_bancarias", "public.gastos", "public.tipo_gasto"
DOMINIO_5 = True
DOMINIO_12 = True


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})


def _t(extra=(), lab=True):
    return P5.transformar(T8._b0(T8._filas(extra=tuple(extra))), SHA, modo_lab=lab)


def _maps(ds, co, cl):
    o = F.uuid_origen(co, cl)
    return [m for m in ds.filas["mapeos_importacion"].values() if m["registro_origen_id"] == o]


def _envolver(monkeypatch, nombre, extra):
    real = getattr(P5, nombre)

    def f(ds, *a, **k):
        r = real(ds, *a, **k)
        extra(ds)
        return r
    monkeypatch.setattr(P5, nombre, f)


# ---------------------------------------------------------------- R05 completo
@pytest.mark.parametrize("lab", [True, False])
def test_todo_origen_tiene_disposicion(lab):
    ds = _t(lab=lab)
    tz = ds.trazabilidad
    assert tz["R05_origenes"] == len(ds.filas["registros_origen_importacion"]) == tz["R05_con_disposicion"]
    assert (tz["R05_sin_disposicion_pendiente_decision"], tz["R05_destinos_sin_origen"],
            tz["R05_mapeos_destino_inexistente"]) == (0, 0, 0)


def test_origen_sin_disposicion_falla_s8():
    with pytest.raises(P5.ErrorP5) as e:
        _t([("public.contenedor_sin_dominio", "X1", {"id": "X1"})])
    assert e.value.codigo == "S8_ORIGEN_SIN_DISPOSICION" and "public.contenedor_sin_dominio/X1" in str(e.value)


def test_gasto_de_referencia_sin_vinculo_queda_sin_disposicion(monkeypatch):
    monkeypatch.setattr(P5, "GASTO_REFERENCIA_CUOTA_VINCULADO", False)
    with pytest.raises(P5.ErrorP5) as e:
        _t()
    assert e.value.codigo == "S8_ORIGEN_SIN_DISPOSICION" and "public.gastos/GH" in str(e.value)


def test_mapeo_a_destino_inexistente_falla_s8(monkeypatch):
    fantasma = F.uuid_v3("TEST", "x", "financiaciones", "fantasma")
    _envolver(monkeypatch, "dominio_10_contratos",
              lambda ds: ds.mapear(GA, "GH", "financiaciones", fantasma, "fantasma", tipo="VINCULADO"))
    with pytest.raises(P5.ErrorP5) as e:
        _t()
    assert e.value.codigo == "S8_MAPEO_DESTINO_INEXISTENTE"


# ---------------------------------------------------------------- gastos de referencia de cuota (D5-T)
def test_gasto_de_referencia_de_cuota_vinculado_a_su_financiacion():
    ds = _t()
    for gasto, prestamo in (("GH", "P1"), ("GP", "P2")):
        (m,) = _maps(ds, GA, gasto)
        eid = F.uuid_v3("public.prestamo", prestamo, "entidades", "financiacion")
        assert (m["tipo_mapping"], m["tabla_destino"], m["registro_destino_id"]) == ("VINCULADO", "financiaciones", eid)
        assert m["transformacion_codigo"].endswith("financiaciones.expectativa_cuota")
    # la expectativa sigue siendo el calendario: no se crea regla para la cuota
    assert not [m for g in ("GH", "GP") for m in _maps(ds, GA, g) if m["tabla_destino"] == "reglas_financieras"]
    assert ds.trazabilidad["gastos_referencia_cuota_vinculados"] == 2


# ---------------------------------------------------------------- taxonomia V3 reemplazada (D-MIG-001)
def test_taxonomia_confirmada_por_defecto_es_obsoleto_sin_pendiente():
    assert (P5.DISPOSICION_TAXONOMIA_V3, P5.DISPOSICION_TAXONOMIA_ESTADO) == ("OBSOLETO", "CONFIRMADA")
    ds = _t(lab=False)
    assert {m["tipo_mapping"] for k in ("TH", "TP", "TF") for m in _maps(ds, TG, k)} == {"OBSOLETO"}
    assert not [p for p in ds.pendientes if p.get("S20") == "DISPOSICION_TAXONOMIA_V3"]


def test_taxonomia_en_laboratorio_sin_destino_con_propuesta_y_pendiente(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_TAXONOMIA_ESTADO", "PROPUESTA")
    ds = _t()
    for k in ("TH", "TP", "TF"):
        (m,) = _maps(ds, TG, k)
        assert (m["tipo_mapping"], m["tabla_destino"], m["registro_destino_id"]) == ("OBSOLETO", None, None)
        assert m["transformacion_codigo"] == "RV3_P5.sin_destino.disposicion"
    (p,) = [p for p in ds.pendientes if p.get("S20") == "DISPOSICION_TAXONOMIA_V3"]
    assert (p["filas"], p["bloquea_gate"], p["propuesta"]) == (3, True, "OBSOLETO")


def test_taxonomia_fuera_de_laboratorio_no_presupone_codigo_y_bloquea(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_TAXONOMIA_ESTADO", "PROPUESTA")
    ds = _t(lab=False)
    assert all(not _maps(ds, TG, k) for k in ("TH", "TP", "TF"))
    assert any(p.get("S20") == "DISPOSICION_TAXONOMIA_V3" and p["bloquea_gate"] for p in ds.pendientes)
    tz = ds.trazabilidad
    assert (tz["R05_sin_disposicion_pendiente_decision"], tz["R05_con_disposicion"]) == (3, tz["R05_origenes"] - 3)


@pytest.mark.parametrize("codigo", ["OBSOLETO", "IGNORADO"])
def test_taxonomia_confirmada_se_materializa_sin_pendiente(monkeypatch, codigo):
    monkeypatch.setattr(P5, "DISPOSICION_TAXONOMIA_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "DISPOSICION_TAXONOMIA_V3", codigo)
    ds = _t(lab=False)
    assert {m["tipo_mapping"] for k in ("TH", "TP", "TF") for m in _maps(ds, TG, k)} == {codigo}
    assert not [p for p in ds.pendientes if p.get("S20") == "DISPOSICION_TAXONOMIA_V3"]
    assert ds.trazabilidad["R05_con_disposicion"] == ds.trazabilidad["R05_origenes"]


def test_taxonomia_con_destino_es_contradictoria(monkeypatch):
    _envolver(monkeypatch, "dominio_10_contratos",
              lambda ds: ds.mapear(TG, "TH", "financiaciones", next(iter(ds.filas["financiaciones"])), "x",
                                   tipo="VINCULADO"))
    with pytest.raises(P5.ErrorP5) as e:
        _t()
    assert e.value.codigo == "S1_TAXONOMIA_V3_CON_DESTINO"


# ---------------------------------------------------------------- decision de clasificacion
def _ds_clasif(registros, destinos):
    """destinos: [(clave_registro, tabla, id, tipo_efecto|None, categoria_id)]"""
    ds = P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))
    ds.categorias = {("A",): "cat-a", ("B",): "cat-b"}
    ds.decisiones = SimpleNamespace(doc={"clasificacion": {"id": "CAT-T", "registros": registros}})
    for clave, t, did, te, cat in destinos:
        co, cl = clave.split("/", 1)
        fila = {"id": did, "categoria_id": cat}
        if te is not None:
            fila["tipo_efecto"] = te
        ds.filas[t][did] = fila
        ds.mapear(co, cl, t, did, f"x.{did}")
    return ds


def _vinculos(ds):
    o = F.uuid_origen(P5.CONT_DECISIONES, "clasificacion/CAT-T")
    return sorted((m["tabla_destino"], m["registro_destino_id"]) for m in ds.filas["mapeos_importacion"].values()
                  if m["registro_origen_id"] == o)


def test_clasificacion_vinculada_solo_donde_se_aplico():
    ds = _ds_clasif({"public.gastos/G1": "A", "public.gastos/G2": None, "public.ingresos/I1": "B"},
                    [("public.gastos/G1", "hecho_efectos", "e1", "GASTO", "cat-a"),
                     ("public.gastos/G1", "hecho_efectos", "e2", "DERECHO_COBRO", None),
                     ("public.gastos/G2", "hecho_efectos", "e3", "GASTO", None),
                     ("public.gastos/G2", "regla_versiones", "v1", None, None),
                     ("public.ingresos/I1", "hecho_efectos", "e4", "INGRESO", "cat-b"),
                     ("public.ingresos/I1", "hecho_efectos", "e5", "DEUDA", None)])
    assert P5._vincular_clasificacion(ds) == 4
    assert _vinculos(ds) == [("hecho_efectos", "e1"), ("hecho_efectos", "e3"), ("hecho_efectos", "e4"),
                             ("regla_versiones", "v1")]
    assert {m["tipo_mapping"] for m in ds.filas["mapeos_importacion"].values()
            if m["transformacion_codigo"].find(".clasificacion.") > 0} == {"VINCULADO"}


@pytest.mark.parametrize("decidida,persistida", [("A", "cat-b"), ("A", None), (None, "cat-a")])
def test_clasificacion_no_aplicada_falla_s9(decidida, persistida):
    ds = _ds_clasif({"public.gastos/G1": decidida},
                    [("public.gastos/G1", "hecho_efectos", "e1", "GASTO", persistida)])
    with pytest.raises(P5.ErrorP5) as e:
        P5._vincular_clasificacion(ds)
    assert e.value.codigo == "S9_CLASIFICACION_NO_APLICADA"


def test_clasificacion_con_desglose_admite_sus_categorias():
    ds = _ds_clasif({"public.gastos/G1": {"desglose": [["A", "1.00"], ["B", "2.00"]]}},
                    [("public.gastos/G1", "hecho_efectos", "e1", "GASTO", "cat-a"),
                     ("public.gastos/G1", "hecho_efectos", "e2", "GASTO", "cat-b")])
    assert P5._vincular_clasificacion(ds) == 2


# ---------------------------------------------------------------- determinismo y carga fisica
def test_determinista():
    assert _t().hash() == _t().hash()
    assert _t(lab=False).hash() == _t(lab=False).hash()


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
@pytest.mark.parametrize("lab", [True, False])
def test_fisico_rv3_import_rollback(lab):
    ds = _t(lab=lab)
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["mapeos_importacion"] == len(ds.filas["mapeos_importacion"])
    assert res["registros_origen_importacion"] == len(ds.filas["registros_origen_importacion"])
