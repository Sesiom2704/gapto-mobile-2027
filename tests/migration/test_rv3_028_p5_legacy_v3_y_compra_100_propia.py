# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_028_p5_legacy_v3_y_compra_100_propia.py
# Ruta: tests/migration/test_rv3_028_p5_legacy_v3_y_compra_100_propia.py
# Descripcion: RV3 / P5 v0.34.0, bloqueantes de cierre de P5. Corpus SINTETICO sin PII.
#              D11-D: el bundle LEGACY_V3_* solo es valido deshabilitado, sin colision con seeds modernos, usado solo
#              por snapshots IMPORTADO_LEGACY/V3_SNAPSHOT, sin definiciones huerfanas y sin residuos del prefijo en
#              datos de dominio. SAA2: compra financiada 100 % propia; falla si pasa a compartida, parcial,
#              recuperable, con aportacion, con importe distinto o sin participacion 100 % propia.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
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
SELF, OTRO = "actor-self", "actor-otro"


# ---------------------------------------------------------------- D11-D / LEGACY_V3_*
def _ds_legacy(enabled=False, codigo="LEGACY_V3_GASTOS_REALES_TOTAL", origen="IMPORTADO_LEGACY", uso=True):
    ds = P5.Dataset(owner="o")
    ds.filas["metricas_definicion"]["m"] = {"id": "m", "codigo": codigo, "enabled": enabled}
    ds.filas["cierres_mensuales"]["c"] = {"id": "c", "origen_cierre": origen, "metodologia_version": "V3_SNAPSHOT"}
    if uso:
        ds.filas["cierre_metricas"]["v"] = {"id": "v", "cierre_id": "c", "metrica_id": "m"}
    ds.filas["mapeos_importacion"]["x"] = {"id": "x", "transformacion_codigo": f"RV3_P5.metricas_definicion.{codigo}"}
    return ds


def _err(ds, fn=P5.verificar_legacy_v3):
    with pytest.raises(P5.ErrorP5) as e:
        fn(ds)
    return e.value.codigo


def test_bundle_legacy_valido():
    assert P5.verificar_legacy_v3(_ds_legacy()) == {"definiciones": 1, "valores_snapshot": 1}


def test_legacy_habilitada_falla():
    assert _err(_ds_legacy(enabled=True)) == "S1_LEGACY_V3_HABILITADA"


def test_legacy_que_finge_equivalencia_moderna_falla():
    assert _err(_ds_legacy(codigo="LEGACY_V3_AHORRO_NETO_PYL")) == "S1_LEGACY_V3_FINGE_EQUIVALENCIA"


def test_legacy_fuera_de_snapshot_falla():
    assert _err(_ds_legacy(origen="GENERADO")) == "S1_LEGACY_V3_FUERA_DE_SNAPSHOT"


def test_legacy_sin_uso_falla():
    assert _err(_ds_legacy(uso=False)) == "S8_LEGACY_V3_SIN_USO"


def test_residuo_legacy_en_dato_de_dominio_falla():
    ds = _ds_legacy()
    ds.filas["hechos_financieros"]["h"] = {"id": "h", "notas": "LEGACY_V3_GASTOS_REALES_TOTAL"}
    assert _err(ds) == "S1_LEGACY_V3_RESIDUO"


# ---------------------------------------------------------------- SAA2
CO, CL = "public.gastos", "g-caso"


def _ds_saa2(**cambio):
    ds = P5.Dataset(owner="o")
    ds.self_id = SELF
    hid = F.uuid_v3(CO, CL, "hechos_financieros", "hecho")
    ds.filas["hechos_financieros"][hid] = {"id": hid, "tipo_hecho_id": P5.TIPOS_HECHO_SEED[cambio.get("tipo", "COMPRA_FINANCIADA")],
                                           "importe_total": Decimal("173.07")}
    for t, imp in (("GASTO", cambio.get("gasto", Decimal("173.07"))), ("DEUDA", Decimal("173.07"))):
        eid = f"e-{t}"
        ds.filas["hecho_efectos"][eid] = {"id": eid, "hecho_id": hid, "tipo_efecto": t, "importe_delta": imp,
                                          "estado_atribucion": cambio.get("estado", "COMPLETA")}
        ats = cambio.get("atribs", [(SELF, imp)])
        for i, (a, v) in enumerate(ats):
            ds.filas["efecto_atribuciones"][f"a-{t}-{i}"] = {"id": f"a-{t}-{i}", "efecto_id": eid, "actor_id": a,
                                                             "importe_atribuido": v}
    ds.filas["financiaciones"]["fin"] = {"entidad_id": "fin"}
    ds.filas["hecho_entidades"]["he"] = {"id": "he", "hecho_id": hid, "entidad_id": "fin"}
    ds.filas["entidad_participaciones"]["p"] = {"id": "p", "entidad_id": "fin", "actor_id": cambio.get("part_actor", SELF),
                                                "porcentaje": Decimal(cambio.get("part_pct", "100"))}
    if cambio.get("derecho"):
        ds.filas["hecho_efectos"]["e-der"] = {"id": "e-der", "hecho_id": hid, "tipo_efecto": "DERECHO_COBRO",
                                              "importe_delta": Decimal("10"), "estado_atribucion": "COMPLETA"}
    if cambio.get("relacion"):
        ds.filas["hecho_relaciones"]["r"] = {"id": "r", "hecho_origen_id": "otro", "hecho_destino_id": hid}
    if cambio.get("aportacion"):
        ds.filas.setdefault("hecho_aportaciones_pago", {})["ap"] = {"id": "ap", "hecho_id": hid}
    return ds


@pytest.fixture(autouse=True)
def caso(monkeypatch):
    monkeypatch.setattr(P5, "CASO_COMPRA_100_PROPIA", {(CO, CL)})


def _v(ds):
    return P5.verificar_compra_100_propia(ds, {CO: {CL: {}}})


def test_saa2_compra_100_propia_valida():
    assert _v(_ds_saa2())[f"{CO}/{CL}"]["gasto_propio"] == "173.07"


def test_saa2_origen_ausente_no_aplica():
    assert P5.verificar_compra_100_propia(_ds_saa2(), {}) == {}


@pytest.mark.parametrize("cambio, codigo", [
    ({"tipo": "GASTO"}, "S9_CASO_100_PROPIO_NO_ES_COMPRA"),
    ({"atribs": [(SELF, Decimal("86.535")), (OTRO, Decimal("86.535"))]}, "S9_CASO_100_PROPIO_ATRIBUCION"),
    ({"estado": "PARCIAL"}, "S9_CASO_100_PROPIO_ATRIBUCION"),
    ({"atribs": [(OTRO, Decimal("173.07"))]}, "S9_CASO_100_PROPIO_ATRIBUCION"),
    ({"gasto": Decimal("100.00"), "atribs": None}, "S9_CASO_100_PROPIO_IMPORTE"),
    ({"derecho": True}, "S9_CASO_100_PROPIO_EFECTOS"),
    ({"relacion": True}, "S9_CASO_100_PROPIO_RECUPERABLE"),
    ({"aportacion": True}, "S9_CASO_100_PROPIO_APORTACION"),
    ({"part_pct": "50"}, "S9_CASO_100_PROPIO_PARTICIPACION"),
    ({"part_actor": OTRO}, "S9_CASO_100_PROPIO_PARTICIPACION"),
])
def test_saa2_reinterpretado_falla(cambio, codigo):
    if cambio.get("atribs", 0) is None:
        cambio = {"gasto": cambio["gasto"]}
    ds = _ds_saa2(**cambio)
    assert _err(ds, _v) == codigo


def test_declaracion_real_saa2():
    sp = importlib.util.spec_from_file_location("p5_real_028", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
    real = importlib.util.module_from_spec(sp)
    sys.modules["p5_real_028"] = real
    try:
        sp.loader.exec_module(real)
    finally:
        sys.modules.pop("p5_real_028", None)
    assert real.CASO_COMPRA_100_PROPIA == {("public.gastos", "gasto-ep2gra")}
    assert "gasto-ep2gra" in real.COMPRA_FINANCIADA_DECIDIDA
    assert real.PARTICIPACION_FIN_SELF.get(("public.gastos", "gasto-ep2gra"), "ausente") is None
