# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_026_p5_etiqueta_capricho.py
# Ruta: tests/migration/test_rv3_026_p5_etiqueta_capricho.py
# Descripcion: RV3 / P5 v0.31.0. D-MIG-002 (Migration V3 §12): el tipo V3 CAPRICHOS conserva su dimension analitica
#              como etiqueta "Capricho" del hecho, ademas de su categoria. Corpus SINTETICO sin PII. Discrimina:
#              etiqueta unica compartida, vinculo por hecho, solo el tipo declarado, residual si el registro no
#              tiene hecho y no colision con las etiquetas de evento.
# Versión: 0.2.1
#              0.2.1 (P5 v0.33.0): Tailandia 2026 con los 5 candidatos confirmados; el hotel de agosto no.
#              0.2.0 (P5 v0.32.0): Bizum como medio de cobro en notas con la cuenta V3 de recepcion; residual sin
#              hecho; contexto Tailandia 2026 ampliado por decision del propietario.
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


I = "public.ingresos"
BIZ = "BIZ-TIPOINGRESO-6UJSD0"


def test_bizum_en_notas_con_cuenta_de_recepcion():
    ds = _ds()
    h = _hecho(ds, I, "i1")
    ds.filas["hechos_financieros"][h]["notas"] = "previa"
    cid = F.uuid_v3("public.cuentas_bancarias", "C1", "cuentas", "cuenta")
    ds.filas["cuentas"][cid] = {"id": cid, "nombre": "NOMINA - BANCO X"}
    h2 = _hecho(ds, I, "i2")
    r = _run(ds, {I: {"i1": {"id": "i1", "tipo_id": BIZ, "cuenta_id": "C1"},
                      "i2": {"id": "i2", "tipo_id": "OTRO", "cuenta_id": "C1"}}})
    assert ds.filas["hechos_financieros"][h]["notas"] == (
        "previa\nV3 medio de cobro: BIZUM (cuenta V3 de recepcion: NOMINA - BANCO X)")
    assert ds.filas["hechos_financieros"][h2]["notas"] is None and r["medio_cobro_notas"] == 1


def test_bizum_sin_hecho_queda_residual():
    ds = _ds()
    _run(ds, {I: {"i1": {"id": "i1", "tipo_id": BIZ, "cuenta_id": "141"}}})
    assert [x["pregunta"] for x in ds.trazabilidad["r02_residuales"][f"{I}.tipo_id"]] == ["D-MIG-002"]


def test_contexto_tailandia_declarado():
    # instancia propia del modulo: conftest vacia los catalogos reales en la instancia compartida
    sp = importlib.util.spec_from_file_location("p5_real_026", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
    real = importlib.util.module_from_spec(sp)
    sys.modules["p5_real_026"] = real  # dataclasses exige el modulo registrado
    try:
        sp.loader.exec_module(real)
    finally:
        sys.modules.pop("p5_real_026", None)
    tai = {k[1] for k, v in real.CONTEXTO_ADICIONAL.items() if v == "CTX-TAILANDIA-2026"}
    assert tai == {"gasto-x2t6dm", "gasto-mpvffi", "gasto-g6r51s", "gasto-ovijms", "gasto-t631sb", "gasto-u99z4c",
                   "gasto-kcbwxz", "gasto-xg1mue", "GASTO_COTIDIANO-4A80N3", "GASTO_COTIDIANO-HCCO1Y",
                   "GASTO_COTIDIANO-1FRA14"}
    assert "GASTO_COTIDIANO-0J3XPQ" not in tai  # hotel de agosto: el propietario confirma que NO
    assert P5.MEDIO_COBRO_TIPO_V3 == {BIZ: "BIZUM"}
