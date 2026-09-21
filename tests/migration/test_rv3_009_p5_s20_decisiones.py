# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_009_p5_s20_decisiones.py
# Ruta: tests/migration/test_rv3_009_p5_s20_decisiones.py
# Descripcion: RV3 / P5 v0.6.0. Corpus SINTETICO (sin PII) de las respuestas S20
#              del propietario: configuracion confirmada, tipo de financiacion
#              decidido, financiador no demostrado -> NULL, participaciones de
#              financiacion 100 % propietario con vigencia PROPUESTA, y fuente
#              suplementaria DECISIONES_PROPIETARIO (personas sin fila V3) con
#              fallo cerrado mientras arquitectura no la apruebe.
#   0.2.0: P5 v0.8.0 -> fuente APROBADA y vigencias CONFIRMADAS en produccion; los
#          tests de mecanismo fijan el estado previo; financiador decidido y
#          vigencia justificada.
# Versión: 0.2.0
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
F = P5.fu
PROD = (P5.CONFIG_CUENTAS_ESTADO, dict(P5.CONFIG_CUENTAS), dict(P5.TIPO_FINANCIACION_DECIDIDO),
        P5.ARQ_FUENTE_DECISIONES_ESTADO, P5.PARTICIPACION_FIN_VIGENCIA_ESTADO)
SHA = "0" * 64
CB, PT = "public.cuentas_bancarias", "public.patrimonio"


def _filas():
    hip = T8._frances(Decimal("1000.00"), "12.000", 4, venc0="2024-03-01", pagadas=2)
    otra = T8._frances(Decimal("600.00"), "0.000", 3, venc0="2021-01-01", pagadas=3)
    base = [f for f in T8._filas() if f[0] not in ("public.prestamo", "public.prestamo_cuota")
            and f[1] not in ("GH", "GP")]
    return base + [
        (CB, "C2", {"id": "C2", "anagrama": "CTA COMPARTIDA", "banco_id": "PA", "liquidez": "20.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "50.00", "activo": True}),
        (PT, "V2", {"id": "V2", "referencia": "V2", "tipo_inmueble": "VIVIENDA", "activo": True, "disponible": True,
                    "fecha_adquisicion": "2024-02-20", "participacion_pct": "50"}),
        (PT, "V3", {"id": "V3", "referencia": "V3", "tipo_inmueble": "VIVIENDA", "activo": True, "disponible": True,
                    "fecha_adquisicion": "2019-05-05", "participacion_pct": "1"}),
        ("public.gastos", "GH", {"id": "GH", "nombre": "CUOTA", "tipo_id": "TP", "prestamo_id": "P1"}),
        ("public.gastos", "GO", {"id": "GO", "nombre": "CUOTA", "tipo_id": "TH", "prestamo_id": "P2"}),
    ] + T8._prestamo("P1", "HIP. COMPARTIDA", "GH", Decimal("1000.00"), "12.000", hip, vivienda="V2") \
      + T8._prestamo("P2", "HIP. FAMILIA", "GO", Decimal("600.00"), "0.000", otra, vivienda="V1")


def _decisiones(tmp_path, **cambios):
    doc = {"id": "SINT-S20", "fecha": "2026-09-21",
           "personas": {"P-A": {"nombre": "Persona A"}, "P-B": {"nombre": "Persona B"}},
           "participaciones": [
               {"id": "D1", "origen": f"{CB}/C2", "desde": "2026-09-05", "repartos": [["SELF", "50"], ["P-A", "50"]]},
               {"id": "D2", "origen": f"{PT}/V2", "desde": {"fecha_adquisicion_de": f"{PT}/V2"},
                "repartos": [["SELF", "50"], ["P-A", "50"]]},
               {"id": "D3", "origen": f"{PT}/V3", "desde": {"fecha_adquisicion_de": f"{PT}/V3"},
                "repartos": [["P-B", "100"]], "corrige_v3": "1 % V3 = 0 % real"},
               {"id": "D4", "origen": "public.prestamo/P1", "desde": {"fecha_adquisicion_de": f"{PT}/V2"},
                "repartos": [["SELF", "50"], ["P-A", "50"]]}]}
    doc.update(cambios)
    p = tmp_path / "decisiones.json"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return P5.cargar_decisiones(p)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                               (CB, "C2"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "TIPO_FINANCIACION_DECIDIDO", {"P1": "HIPOTECA", "P2": "PRESTAMO"})
    monkeypatch.setattr(P5, "FINANCIADOR_NO_DEMOSTRADO", {"P2"})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {("public.prestamo", "P2"): None, ("public.gastos", "G1"): None})
    # Los tests de mecanismo parten del estado previo a las aprobaciones (baseline v0.6.0).
    monkeypatch.setattr(P5, "ARQ_FUENTE_DECISIONES_ESTADO", "PENDIENTE_ARQUITECTURA")
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_VIGENCIA_ESTADO", "PROPUESTA")


def _t(ds, decisiones=None, lab=True):
    return P5.transformar(T8._b0(_filas()), SHA, modo_lab=lab, decisiones=decisiones)


def _fin(ds, nombre):
    eid = next(e for e, x in ds.filas["entidades"].items() if x["nombre"] == nombre)
    return eid, ds.filas["financiaciones"][eid]


def test_configuracion_confirmada_en_produccion():
    estado, config, tipos, arq, vig = PROD
    assert (arq, vig) == ("APROBADA", "CONFIRMADA")
    assert estado == "CONFIRMADA" and config[("public.gastos", "gasto-xg1mue")][5] == "EUR"
    assert tipos == {"prestamo-N622DI": "HIPOTECA", "prestamo-wb8ysw": "PRESTAMO"}


def test_tipo_decidido_prevalece_y_prestamo_con_vivienda_sin_garantia(tmp_path):
    ds = _t(None, _decisiones(tmp_path))
    e1, f1 = _fin(ds, "HIP. COMPARTIDA")
    e2, f2 = _fin(ds, "HIP. FAMILIA")
    assert (f1["tipo_financiacion"], f2["tipo_financiacion"]) == ("HIPOTECA", "PRESTAMO")
    rel = [r for r in ds.filas["entidad_relaciones"].values()]
    assert [r["entidad_origen_id"] for r in rel] == [e1] and rel[0]["tipo_relacion"] == "GARANTIZADA_POR"
    assert any(l["regla"] == "D8-B2" and l["origen"].endswith("/P2") for l in ds.ledger)
    assert any(l["regla"] == "D8-A2" and l["origen"].endswith("/P1") for l in ds.ledger)


def test_financiador_no_demostrado_es_null_sin_rol(tmp_path):
    ds = _t(None, _decisiones(tmp_path))
    assert _fin(ds, "HIP. FAMILIA")[1]["financiador_actor_id"] is None
    assert _fin(ds, "HIP. COMPARTIDA")[1]["financiador_actor_id"] is not None
    assert any(q["id"] == "Q-S20-8-FINANCIADOR" for q in ds.preguntas)


def test_participacion_fin_self_vigencia_propuesta_solo_en_lab(tmp_path, monkeypatch):
    ds = _t(None, _decisiones(tmp_path))
    e2, f2 = _fin(ds, "HIP. FAMILIA")
    ps = [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == e2]
    assert len(ps) == 1 and ps[0]["porcentaje"] == Decimal(100) and ps[0]["vigente_desde"] == f2["fecha_inicio"]
    assert any(p.get("S20") == "VIGENCIA_PARTICIPACION_FIN" for p in ds.pendientes)
    monkeypatch.setattr(P5, "ARQ_FUENTE_DECISIONES_ESTADO", "APROBADA")
    with pytest.raises(P5.ErrorP5) as e:
        _t(None, _decisiones(tmp_path), lab=False)
    assert e.value.codigo == "S20_VIGENCIA_PARTICIPACION_FIN"


def test_financiacion_sin_decision_no_recibe_participacion(tmp_path, monkeypatch):
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    ds = _t(None, None)
    fins = set(ds.filas["financiaciones"])
    assert not [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] in fins]


def test_fuente_suplementaria_crea_personas_y_repartos_trazados(tmp_path):
    dec = _decisiones(tmp_path)
    ds = _t(None, dec)
    fuentes = {f["tipo_fuente"]: f for f in ds.filas["fuentes_importacion"].values()}
    assert fuentes["OTRO"]["sha256"] == dec.sha256 and fuentes["XLSX"]["sha256"] == SHA
    fx = fuentes["XLSX"]["id"]
    assert len([r for r in ds.filas["registros_origen_importacion"].values() if r["fuente_importacion_id"] == fx]) \
        == len(_filas())
    cid = F.uuid_v3(CB, "C2", "cuentas", "cuenta")
    cps = sorted(p["porcentaje"] for p in ds.filas["cuenta_participaciones"].values() if p["cuenta_id"] == cid)
    assert cps == [Decimal(50), Decimal(50)]
    v3 = F.uuid_v3(PT, "V3", "entidades", "propiedad")
    pv3 = [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == v3]
    assert len(pv3) == 1 and pv3[0]["actor_id"] != ds.self_id and pv3[0]["vigente_desde"] == "2019-05-05"
    nombres = {t["nombre"] for t in ds.filas["terceros"].values() if t["naturaleza"] == "PERSONA"}
    assert {"Persona A", "Persona B"} <= nombres
    assert any(p.get("S20") == "ARQ_FUENTE_DECISIONES" for p in ds.pendientes)


def test_fuente_suplementaria_falla_cerrada_fuera_de_lab(tmp_path):
    with pytest.raises(P5.ErrorP5) as e:
        _t(None, _decisiones(tmp_path), lab=False)
    assert e.value.codigo == "S20_ARQ_FUENTE_DECISIONES"


def test_decision_que_contradice_v3_exige_correccion_explicita(tmp_path):
    reps = _decisiones(tmp_path).doc["participaciones"]
    reps[2] = {k: v for k, v in reps[2].items() if k != "corrige_v3"}
    with pytest.raises(P5.ErrorP5) as e:
        _t(None, _decisiones(tmp_path, participaciones=reps))
    assert e.value.codigo == "S1_DECISION_CONTRADICE_V3"


def test_reparto_no_100_y_actor_desconocido_fallan(tmp_path):
    reps = _decisiones(tmp_path).doc["participaciones"]
    malo = [dict(reps[0], repartos=[["SELF", "50"], ["P-A", "40"]])] + reps[1:]
    with pytest.raises(P5.ErrorP5) as e:
        _decisiones(tmp_path, participaciones=malo)
    assert e.value.codigo == "S9_DECISION_REPARTO_NO_100"
    malo = [dict(reps[0], repartos=[["SELF", "50"], ["P-X", "50"]])] + reps[1:]
    with pytest.raises(P5.ErrorP5) as e:
        _decisiones(tmp_path, participaciones=malo)
    assert e.value.codigo == "S8_DECISION_ACTOR_DESCONOCIDO"


def test_vigencia_anterior_al_inicio_se_eleva(tmp_path):
    ds = _t(None, _decisiones(tmp_path))
    q = [q for q in ds.preguntas if q["id"] == "Q-S20-7-VIGENCIA"]
    assert len(q) == 1 and q[0]["vigente_desde"] == "2024-02-20" and q[0]["fecha_inicio"] == "2024-03-01"


def test_todo_destino_tiene_mapeo_a_registro_existente(tmp_path):
    ds = _t(None, _decisiones(tmp_path))
    P5.verificar_trazabilidad(ds)
    orig = ds.filas["registros_origen_importacion"]
    sup = {m["tabla_destino"] for m in ds.filas["mapeos_importacion"].values()
           if orig[m["registro_origen_id"]]["contenedor_origen"] == P5.CONT_DECISIONES}
    assert {"terceros", "tercero_personas", "actores_financieros", "cuenta_participaciones",
            "entidad_participaciones"} <= sup


def test_financiador_decidido_y_vigencia_justificada(tmp_path, monkeypatch):
    monkeypatch.setattr(P5, "ARQ_FUENTE_DECISIONES_ESTADO", "APROBADA")
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_VIGENCIA_ESTADO", "CONFIRMADA")
    base = _decisiones(tmp_path)
    reps = base.doc["participaciones"]
    reps[3] = dict(reps[3], justificacion="firmado antes del primer vencimiento")
    dec = _decisiones(tmp_path, personas={**base.doc["personas"], "P-G": {"nombre": "Grupo", "naturaleza": None}},
                      participaciones=reps,
                      financiadores=[{"id": "F1", "origen": "public.prestamo/P2", "persona": "P-G"}])
    ds = _t(None, dec, lab=False)
    aid = F.uuid_v3(P5.CONT_DECISIONES, "persona/P-G", "actores_financieros", "actor")
    tid = F.uuid_v3(P5.CONT_DECISIONES, "persona/P-G", "terceros", "tercero")
    assert _fin(ds, "HIP. FAMILIA")[1]["financiador_actor_id"] == aid
    assert ds.filas["terceros"][tid]["naturaleza"] is None and tid not in ds.filas["tercero_personas"]
    assert any(r["tercero_id"] == tid and r["rol_codigo"] == "FINANCIADOR" for r in ds.filas["tercero_roles"].values())
    assert not ds.preguntas and not ds.pendientes


def test_hash_determinista(tmp_path):
    dec = _decisiones(tmp_path)
    assert _t(None, dec).hash() == _t(None, dec).hash()


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback(tmp_path):
    ds = _t(None, _decisiones(tmp_path))
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["cuenta_participaciones"] == 3 and res["entidad_participaciones"] == 8
    assert res["fuentes_importacion"] == 2


def test_plantilla_de_decisiones_es_valida_y_sin_datos_reales():
    dec = P5.cargar_decisiones(RAIZ / "scripts" / "migration_v3" / "rv3_decisiones_propietario.ejemplo.json")
    assert sorted(dec.doc["personas"]) == ["P-EJEMPLO", "P-GRUPO"]
    assert all("CLAVE-V3" in x["origen"] for x in dec.doc["participaciones"] + dec.doc["contrapartes"] + dec.doc["financiadores"])
