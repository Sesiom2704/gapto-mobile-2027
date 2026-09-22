# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_026_p5_etiqueta_capricho.py
# Ruta: tests/migration/test_rv3_026_p5_etiqueta_capricho.py
# Descripcion: RV3 / P5 v0.31.0. D-MIG-002 (Migration V3 §12): el tipo V3 CAPRICHOS conserva su dimension analitica
#              como etiqueta "Capricho" del hecho, ademas de su categoria. Corpus SINTETICO sin PII. Discrimina:
#              etiqueta unica compartida, vinculo por hecho, solo el tipo declarado, residual si el registro no
#              tiene hecho y no colision con las etiquetas de evento.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
F = P5.fu
R02C = True
G, GC = "public.gastos", "public.gastos_cotidianos"
CAP = "CAP-TIPOGASTO-334BFEC7"


def _ds():
    return P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))


def _hecho(ds, co, cl):
    hid = F.uuid_v3(co, cl, "hechos_financieros", "hecho")
    ds.filas["hechos_financieros"][hid] = {"id": hid, "notas": None}
    ds.mapear(co, cl, "hechos_financieros", hid, "hecho")
    return hid


def _run(ds, fuente):
    return P5.dominio_12_r02_complementos(ds, fuente, F.contexto_de(fuente))


def test_capricho_etiqueta_unica_por_hecho():
    ds = _ds()
    h1, h2 = _hecho(ds, G, "g1"), _hecho(ds, G, "g2")
    _hecho(ds, G, "g3")
    r = _run(ds, {G: {"g1": {"id": "g1", "tipo_id": CAP}, "g2": {"id": "g2", "tipo_id": CAP},
                      "g3": {"id": "g3", "tipo_id": "OTRO-TIPO"}}})
    assert [e["nombre"] for e in ds.filas["etiquetas"].values()] == ["Capricho"]
    assert sorted(x["hecho_id"] for x in ds.filas["hecho_etiquetas"].values()) == sorted([h1, h2])
    assert r["etiquetas_tipo_v3"] == 2


def test_capricho_sin_hecho_queda_residual():
    ds = _ds()
    _run(ds, {G: {"g1": {"id": "g1", "tipo_id": CAP}}})
    assert not ds.filas["hecho_etiquetas"]
    assert [x["pregunta"] for x in ds.trazabilidad["r02_residuales"][f"{G}.tipo_id"]] == ["D-MIG-002"]


def test_capricho_y_evento_conviven_en_el_mismo_hecho():
    ds = _ds()
    h = _hecho(ds, GC, "c1")
    _run(ds, {GC: {"c1": {"id": "c1", "tipo_id": CAP, "evento": "AMIGOS", "fecha": "2025-01-01"}}})
    nombres = {e["id"]: e["nombre"] for e in ds.filas["etiquetas"].values()}
    assert sorted(nombres[x["etiqueta_id"]] for x in ds.filas["hecho_etiquetas"].values() if x["hecho_id"] == h) == [
        "AMIGOS", "Capricho"]


def test_declaracion_real():
    assert P5.ETIQUETA_TIPO_V3 == {CAP: "Capricho"}
