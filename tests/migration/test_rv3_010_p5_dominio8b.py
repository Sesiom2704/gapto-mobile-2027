# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_010_p5_dominio8b.py
# Ruta: tests/migration/test_rv3_010_p5_dominio8b.py
# Descripcion: RV3 / P5 v0.7.0. Corpus SINTETICO (sin PII) del dominio 8B,
#              derechos de cobro: catalogo cerrado, posicion abierta con saldo =
#              importe documentado, transitoria liquidada antes del corte (saldo 0,
#              CERRADA/LIQUIDADA, importe = cobro), canon de transitorias, principal
#              desconocido NULL, saldo indeterminado NULL (nunca 0), contraparte
#              desconocida NULL salvo decision S20, trazabilidad y carga fisica.
#   0.2.0: P5 v0.8.0 -> participacion 100 % propietario (S20 R2-7), vinculados (R2-8),
#          contraparte desconocida sin pregunta (R2-6), gate con fuente PENDIENTE.
#   0.3.0: contraparte = persona V3 validada como inquilino del contrato de la vivienda.
# Versión: 0.3.0
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
_s8 = importlib.util.spec_from_file_location("t8", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
CATALOGOS_V3_REALES = True
F = P5.fu
SHA = "0" * 64
G, I = "public.gastos", "public.ingresos"
CAT = [
    {"id": "D-AB", "genera": (G, "GA"), "evidencia": [], "modo": "ABIERTA"},
    {"id": "D-T1", "genera": (G, "GT1"), "evidencia": [(I, "IT1")], "modo": "TRANSITORIA"},
    {"id": "D-T2", "genera": (G, "GT2"), "evidencia": [(I, "IT2")], "modo": "TRANSITORIA"},
    {"id": "D-U", "genera": None, "evidencia": [(I, "IU1"), (I, "IU2")], "modo": "LIQUIDADA_SIN_PRINCIPAL"},
    {"id": "D-IN", "genera": None, "evidencia": [(I, "IX")], "modo": "INDETERMINADA"},
]


def _filas(**cambios):
    f = {
        "GA": (G, {"id": "GA", "nombre": "ADELANTO A", "importe": 40.5, "fecha": "2026-05-01"}),
        "GT1": (G, {"id": "GT1", "nombre": "REPERCUTIDO 1", "importe": 10, "fecha": "2026-03-01"}),
        "GT2": (G, {"id": "GT2", "nombre": "REPERCUTIDO 2", "importe": 5.25, "fecha": "2026-04-01"}),
        "IT1": (I, {"id": "IT1", "concepto": "COBRO 1", "importe": 10, "fecha_inicio": "2026-03-03"}),
        "IT2": (I, {"id": "IT2", "concepto": "COBRO 2", "importe": 5.25, "fecha_inicio": "2026-04-02"}),
        "IU1": (I, {"id": "IU1", "concepto": "PAGO U 1", "importe": 100, "fecha_inicio": "2025-11-30"}),
        "IU2": (I, {"id": "IU2", "concepto": "PAGO U 2", "importe": 50, "fecha_inicio": "2026-04-27"}),
        "IX": (I, {"id": "IX", "concepto": "COBRO MENSUAL", "importe": 70.3, "fecha_inicio": "2022-01-01"}),
    }
    for k, v in cambios.items():
        if v is None:
            f.pop(k)
        else:
            f[k] = (f[k][0], {**f[k][1], **v})
    return T8._filas() + [(c, k, d) for k, (c, d) in f.items()]


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    monkeypatch.setattr(P5, "DERECHOS_V3", CAT)
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (2, Decimal("15.25")))
    monkeypatch.setattr(P5, "CANON_UNIVERSIDAD", Decimal("150"))
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {})


def _t(filas=None, dec=None, lab=True):
    return P5.transformar(T8._b0(filas or _filas()), SHA, modo_lab=lab, decisiones=dec)


def _d(ds, co, cl):
    return ds.filas["derechos_obligaciones_financieras"][F.uuid_v3(co, cl, "entidades", "derecho")]


def _err(**kw):
    with pytest.raises(P5.ErrorP5) as e:
        _t(**kw)
    return e.value.codigo


def test_catalogo_real_declarado(monkeypatch):
    real = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(real)
    ids = [d["id"] for d in real.DERECHOS_V3]
    assert len(ids) == 11 and len(set(ids)) == 11
    assert sum(1 for d in real.DERECHOS_V3 if d["modo"] == "TRANSITORIA") == real.CANON_TRANSITORIAS[0] == 7
    assert real.CANON_TRANSITORIAS[1] == Decimal("330.11") and real.CANON_UNIVERSIDAD == Decimal("1352.00")


def test_abierto_saldo_igual_a_importe_y_contraparte_desconocida_null():
    ds = _t()
    d = _d(ds, G, "GA")
    assert (d["estado"], d["saldo_apertura"], d["importe_original_documentado"]) == ("ACTIVA", Decimal("40.5"), Decimal("40.5"))
    assert d["fecha_inicio_seguimiento"] == P5.FECHA_INICIO_LEDGER and d["contraparte_actor_id"] is None
    assert any(x["regla"] == "D8B-C" and x["derecho"] == "D-AB" for x in ds.ledger)


def test_transitoria_liquidada_saldo_cero_cerrada():
    d = _d(_t(), G, "GT2")
    assert (d["estado"], d["motivo_cierre"], d["saldo_apertura"]) == ("CERRADA", "LIQUIDADA", Decimal("0"))
    assert d["importe_original_documentado"] == Decimal("5.25") and d["fecha_cierre"] is None


def test_transitoria_cobrada_tras_el_corte_falla():
    assert _err(filas=_filas(IT1={"fecha_inicio": "2026-09-10"})) == "S9_TRANSITORIA_NO_LIQUIDADA_AL_CORTE"


def test_transitoria_con_importe_distinto_falla():
    assert _err(filas=_filas(IT2={"importe": 5})) == "S9_TRANSITORIA_IMPORTE_DISTINTO"


def test_canon_de_transitorias(monkeypatch):
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (2, Decimal("15.26")))
    assert _err() == "S9_TRANSITORIAS_CANON"


def test_liquidada_sin_principal_nunca_inventa_principal():
    d = _d(_t(), I, "IU1")
    assert d["importe_original_documentado"] is None and d["saldo_apertura"] == Decimal("0")
    assert _err(filas=_filas(IU2={"importe": 49})) == "S9_UNIVERSIDAD_NO_CUADRA"


def test_indeterminada_nunca_cero():
    d = _d(_t(), I, "IX")
    assert d["estado"] == "ACTIVA" and d["saldo_apertura"] is None and d["fecha_inicio_seguimiento"] is None
    assert d["importe_original_documentado"] is None


def test_origen_ausente_falla_cerrado():
    assert _err(filas=_filas(IX=None)) == "S8_ORIGEN_AUSENTE"


def test_contraparte_decidida_por_fuente_suplementaria(tmp_path, monkeypatch):
    doc = {"id": "S", "personas": {"P-A": {"nombre": "Persona A"}}, "participaciones": [],
           "contrapartes": [{"id": "C1", "origen": f"{G}/GA", "persona": "P-A"}]}
    p = tmp_path / "d.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    dec = P5.cargar_decisiones(p)
    ds = _t(dec=dec)
    aid = F.uuid_v3(P5.CONT_DECISIONES, "persona/P-A", "actores_financieros", "actor")
    assert _d(ds, G, "GA")["contraparte_actor_id"] == aid
    monkeypatch.setattr(P5, "ARQ_FUENTE_DECISIONES_ESTADO", "PENDIENTE_ARQUITECTURA")
    with pytest.raises(P5.ErrorP5) as e:
        _t(dec=dec, lab=False)
    assert e.value.codigo == "S20_ARQ_FUENTE_DECISIONES"


def test_participacion_del_derecho_100_propietario_con_fecha_de_origen():
    ds = _t()
    ps = {p["entidad_id"]: p for p in ds.filas["entidad_participaciones"].values()}
    ga = ps[F.uuid_v3(G, "GA", "entidades", "derecho")]
    iu = ps[F.uuid_v3(I, "IU1", "entidades", "derecho")]
    assert (ga["actor_id"], ga["porcentaje"], ga["vigente_desde"]) == (ds.self_id, Decimal(100), "2026-05-01")
    assert iu["vigente_desde"] == "2025-11-30"


def test_vinculado_relacionado_por_el_propietario(monkeypatch):
    cat = [dict(x) for x in CAT]
    cat[3]["vinculados"] = [(G, "GT1")]
    monkeypatch.setattr(P5, "DERECHOS_V3", cat)
    ds = _t()
    orig = ds.filas["registros_origen_importacion"]
    assert any(m["tipo_mapping"] == "VINCULADO" and orig[m["registro_origen_id"]]["clave_origen"] == "GT1"
               and m["registro_destino_id"] == F.uuid_v3(I, "IU1", "entidades", "derecho")
               for m in ds.filas["mapeos_importacion"].values())
    cat[3]["vinculados"] = [(G, "NOEXISTE")]
    assert _err() == "S8_ORIGEN_AUSENTE"


def _con_contrato(rol="inquilino", viv="V1"):
    return _filas(GT1={"referencia_vivienda_id": "V1"}) + [
        ("public.personas", "PX", {"id": "PX", "nombre_completo": "Persona X", "email": "x@example.invalid"}),
        ("public.contratos", "K1", {"id": "K1", "patrimonio_id": viv, "estado": "activo",
                                    "objeto_alquiler": "completa", "fecha_inicio": "2024-01-01"}),
        ("public.contratos_participantes", "KP1", {"id": "KP1", "contrato_id": "K1", "persona_id": "PX", "rol": rol})]


def test_contraparte_persona_v3_validada_como_inquilino(monkeypatch):
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {"D-T1": ("public.personas", "PX")})
    ds = _t(filas=_con_contrato())
    assert _d(ds, G, "GT1")["contraparte_actor_id"] == F.uuid_v3("public.personas", "PX", "actores_financieros", "actor")
    P5.verificar_trazabilidad(ds)
    assert _err(filas=_con_contrato(rol="avalista")) == "S1_CONTRAPARTE_NO_INQUILINO"
    assert _err(filas=_con_contrato(viv="OTRA")) == "S1_CONTRAPARTE_NO_INQUILINO"


def test_trazabilidad_y_evidencia_vinculada():
    ds = _t()
    P5.verificar_trazabilidad(ds)
    orig = ds.filas["registros_origen_importacion"]
    ev = [m for m in ds.filas["mapeos_importacion"].values()
          if m["tabla_destino"] == "derechos_obligaciones_financieras" and orig[m["registro_origen_id"]]["clave_origen"] == "IT1"]
    assert len(ev) == 1 and ev[0]["tipo_mapping"] == "VINCULADO"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    res = P5.validar_fisico(_t(), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["derechos_obligaciones_financieras"] == 5 and res["entidad_participaciones"] >= 5
