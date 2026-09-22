# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_033_s1_suplementario.py
# Ruta: tests/migration/test_rv3_033_s1_suplementario.py
# Descripcion: RV3 / escenario S1 v0.1.0 (rv3_s1_suplementario.py). Corpus SINTETICO sin PII. Discrimina:
#              P3-S1/G2 (float entero -> entero, '' -> ausencia, fechas ISO, sin tocar el 141 ni inferir);
#              fuente efectiva (equivalentes con literal B0, MODIFICADA solo en sus columnas DISTINTO, altas
#              completas, baja fuera); STOP por hash S1 distinto del contractual y por delta distinto del
#              contrato; reetiquetado de la fuente de importacion como S1; y la declaracion real del contrato.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import datetime as _dt
import decimal
import importlib.util
import json
import sys
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


DOMINIO_12 = True  # este modulo ejercita la disposicion R05 del dominio 12
S1 = _mod("rv3_s1_suplementario", "rv3_s1_suplementario.py")
P5 = _mod("rv3_p5_transformacion", "rv3_p5_transformacion.py")
FU = P5.fu


# ---------------------------------------------------------------- P3-S1 (G2)
@pytest.mark.parametrize("entrada, salida", [
    (46.0, 46), (46.5, 46.5), (decimal.Decimal("11.0"), 11), ("", None), ("  ", None),
    ("141", "141"), ("MADRID", "MADRID"), (True, True), (False, False), (0, 0), (None, None),
    (_dt.date(2026, 9, 1), "2026-09-01"), (_dt.datetime(2026, 9, 1, 17, 4), "2026-09-01T17:04:00"),
])
def test_normalizacion_representacional(entrada, salida):
    assert S1.normalizar_export(entrada) == salida


def test_normalizacion_no_infiere_semantica():
    assert S1.normalizar_export("None") == "None" and S1.normalizar_export("0") == "0"  # sentinels intactos


# ---------------------------------------------------------------- fuente efectiva
def _b0(filas):
    out = {}
    for co, k, datos in filas:
        texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        out.setdefault(co, {})[k] = FU.RegistroB0(co, k, datos, texto, FU.hash_registro(texto), f"R-{k}", None)
    return out


def _s1(filas):
    return {co: {"campos": sorted({c for _, _, d in filas for c in d}), "filas": {k: d for c, k, d in filas if c == co}}
            for co in {c for c, _, _ in filas}}


def test_fuente_efectiva_por_clase():
    b0 = _b0([("t", "EQ", {"id": "EQ", "a": 1, "b": "141"}),
              ("t", "MOD", {"id": "MOD", "a": 1, "b": "141"}),
              ("t", "BAJA", {"id": "BAJA", "a": 9})])
    s1 = _s1([("t", "EQ", {"id": "EQ", "a": 1.0, "b": ""}),
              ("t", "MOD", {"id": "MOD", "a": 2.0, "b": ""}),
              ("t", "ALTA", {"id": "ALTA", "a": 3.0, "b": ""})])
    deltas = [{"contenedor": "t", "clave": "MOD", "tipo": "MODIFICADA", "columnas": ["a"]},
              {"contenedor": "t", "clave": "ALTA", "tipo": "SOLO_SHEET", "columnas": []},
              {"contenedor": "t", "clave": "BAJA", "tipo": "SOLO_SNAPSHOT", "columnas": []}]
    comb, clases = S1.fuente_efectiva(FU, b0, s1, deltas)
    assert comb["t"]["EQ"].datos == {"id": "EQ", "a": 1, "b": "141"}          # equivalente: literal B0 intacto
    assert comb["t"]["MOD"].datos == {"id": "MOD", "a": 2, "b": "141"}        # solo la columna DISTINTO cambia
    assert comb["t"]["ALTA"].datos == {"id": "ALTA", "a": 3, "b": None}       # alta normalizada
    assert "BAJA" not in comb["t"]                                            # la baja no forma parte de S1
    assert clases == {"MODIFICADA": ["t/MOD"], "SOLO_SHEET": ["t/ALTA"], "SOLO_SNAPSHOT": ["t/BAJA"]}
    assert comb["t"]["MOD"].sha256_registro == FU.hash_registro(comb["t"]["MOD"].texto)


def test_delta_distinto_del_contrato_es_stop(monkeypatch):
    monkeypatch.setattr(S1, "DELTA_CONTRACTUAL", {"EQUIVALENTE": 1, "MODIFICADA": 1, "SOLO_SHEET": 0, "SOLO_SNAPSHOT": 0})

    class P1:
        @staticmethod
        def cargar_snapshot(wb):
            return {}

        @staticmethod
        def comparar(a, b):
            return ({}, {}, [{"contenedor": "t", "clave": "X", "tipo": "SOLO_SHEET", "columnas": []}])
    monkeypatch.setattr(S1, "_mod", lambda *a: None)
    import openpyxl
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: None)
    with pytest.raises(S1.StopS1) as e:
        S1.delta_b0_s1(P1, Path("x"), Path("y"))
    assert e.value.codigo == "S3_DELTA_DISTINTO_DEL_CONTRATO"


def test_hash_s1_distinto_es_stop(tmp_path, monkeypatch):
    class P1B:
        @staticmethod
        def main(argv):
            (tmp_path / "rv3_p1b_manifest_s1_X.json").write_text(json.dumps({"hash_semantico": "0" * 64}), encoding="utf-8")
            return 0

    class P1:
        @staticmethod
        def sha256_fichero(p):
            return "sha"
    with pytest.raises(S1.StopS1) as e:
        S1.fijar_s1(P1B, P1, tmp_path / "s.xlsx", tmp_path / "r.xlsx", "id", "t", tmp_path)
    assert e.value.codigo == "S3_S1_NO_REPRODUCIBLE"


def test_fuente_de_importacion_reetiquetada_como_s1():
    class DS:
        filas = {"fuentes_importacion": {"f": {"sha256": "SHAB0", "nombre_fuente": "RUN06", "version_fuente": "v08"},
                                         "g": {"sha256": "OTRA", "nombre_fuente": "decisiones"}}}
    S1.etiquetar_fuente_s1(DS, "SHAB0", "SEMHASH")
    f, g = DS.filas["fuentes_importacion"]["f"], DS.filas["fuentes_importacion"]["g"]
    assert (f["sha256"], f["version_fuente"], f["nombre_fuente"]) == ("SEMHASH", "S1", S1.NOMBRE_FUENTE_S1)
    assert g["sha256"] == "OTRA" and g["nombre_fuente"] == "decisiones"  # las demas fuentes no se tocan


def test_declaracion_contractual_s1():
    assert S1.S1_SEMHASH_CONTRACTUAL == "0a180ec40f525b30d9a4e3a42dc9ef078347aca74d0f5a4d8bc4862bde2ef665"
    assert S1.DELTA_CONTRACTUAL == {"EQUIVALENTE": 2474, "MODIFICADA": 26, "SOLO_SHEET": 38, "SOLO_SNAPSHOT": 1}


# ---------------------------------------------------------------- G1 sobre decisiones de participacion
def test_decision_de_participacion_sobre_fila_ausente_queda_ignorada():
    class D:
        doc = {"participaciones": [{"id": "S20-X", "origen": "public.gastos/GX", "repartos": []}]}
    ds = P5.Dataset(owner="o")
    ds.decisiones = D()
    ds.ausentes_s1 = frozenset({"public.gastos/GX"})
    ds.trazabilidad["contenedores_pendientes"] = ()
    clave = f"{P5.CONT_DECISIONES}/participacion/S20-X"
    oid = FU.uuid_origen(P5.CONT_DECISIONES, "participacion/S20-X")
    ds.filas["registros_origen_importacion"][oid] = {"id": oid, "contenedor_origen": P5.CONT_DECISIONES,
                                                     "clave_origen": "participacion/S20-X"}
    P5.verificar_trazabilidad(ds)
    (m,) = ds.filas["mapeos_importacion"].values()
    assert (m["tipo_mapping"], m["tabla_destino"], m["registro_destino_id"]) == ("IGNORADO", None, None)
    assert any(e["regla"] == "NO_APLICA_S1_FILA_AUSENTE" for e in ds.ledger)
    assert clave  # la decision historica se conserva; solo no se ejecuta contra S1
