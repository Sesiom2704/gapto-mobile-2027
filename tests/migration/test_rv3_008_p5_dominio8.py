# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_008_p5_dominio8.py
# Ruta: tests/migration/test_rv3_008_p5_dominio8.py
# Descripcion: RV3 / P5 v0.5.0. Corpus SINTETICO (sin PII) del dominio 8,
#              financiaciones: tipo demostrado solo por coincidencia de nombre y
#              tipo_gasto (S20 si discrepan), garantia solo para HIPOTECA, financiador
#              demostrado por el prestamo, apertura = capital pendiente cuadrado con el
#              calendario, sistema de amortizacion demostrado por calculo, calendario
#              V3 conservado sin correcciones, versiones decididas por numero de cuota,
#              compras financiadas liquidadas sin segundo gasto ni financiador inventado,
#              y participaciones nunca inferidas.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import json
import os
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
F = P5.fu
SHA = "0" * 64
CB, PR, PQ, GA = "public.cuentas_bancarias", "public.prestamo", "public.prestamo_cuota", "public.gastos"


def _frances(principal, tin, n, venc0="2024-01-01", pagadas=0):
    i = Decimal(tin) / 1200
    cuota = (principal * i / (1 - (1 + i) ** -n)).quantize(Decimal("0.01"), ROUND_HALF_UP) if i else principal / n
    saldo, filas = principal, []
    y, m, d = map(int, venc0.split("-"))
    for k in range(1, n + 1):
        interes = (saldo * i).quantize(Decimal("0.01"), ROUND_HALF_UP)
        capital = saldo if k == n else cuota - interes
        saldo -= capital
        mm = m + k - 1
        filas.append({"num": k, "capital": capital, "interes": interes, "importe": capital + interes,
                      "venc": f"{y + (mm - 1) // 12}-{(mm - 1) % 12 + 1:02d}-{d:02d}", "pagada": k <= pagadas,
                      "saldo": saldo})
    return filas


def _prestamo(clave, nombre, gasto, principal, tin, cal, vivienda="141"):
    pend = principal - sum(c["capital"] for c in cal if c["pagada"])
    pr = {"id": clave, "nombre": nombre, "importe_principal": str(principal), "capital_pendiente": str(pend),
          "tin_pct": tin, "tipo_interes": "FIJO", "periodicidad": "MENSUAL", "estado": "ACTIVO", "activo": True,
          "cuenta_id": "C1", "proveedor_id": "PA", "referencia_gasto": gasto, "referencia_vivienda_id": vivienda,
          "fecha_inicio": cal[0]["venc"], "fecha_vencimiento": cal[-1]["venc"], "cuotas_totales": len(cal),
          "indice": "None", "diferencial_pct": "141"}
    qs = [(PQ, f"{clave}-q{c['num']}", {"id": f"{clave}-q{c['num']}", "prestamo_id": clave, "num_cuota": c["num"],
                                        "capital": str(c["capital"]), "interes": str(c["interes"]),
                                        "comisiones": "0.00", "seguros": "0.00", "importe_cuota": str(c["importe"]),
                                        "fecha_vencimiento": c["venc"], "pagada": c["pagada"],
                                        "saldo_posterior": str(c["saldo"])}) for c in cal]
    return [(PR, clave, pr)] + qs


def _filas(extra=()):
    hip = _frances(Decimal("1000.00"), "12.000", 4, pagadas=2)
    cero = _frances(Decimal("300.00"), "0.000", 3, venc0="2026-08-01", pagadas=0)
    return [
        ("public.users", "7", {"id": 7, "email": "t@example.invalid", "full_name": "Tenant"}),
        ("public.tipo_ramas_proveedores", "R1", {"id": "R1", "nombre": "BANCOS"}),
        ("public.proveedores", "PA", {"id": "PA", "nombre": "BANCO A", "rama_id": "R1", "subsegmento_id": "141", "activo": True}),
        ("public.proveedores", "PT", {"id": "PT", "nombre": "TIENDA T", "rama_id": "R1", "subsegmento_id": "141", "activo": True}),
        (CB, "C1", {"id": "C1", "anagrama": "CTA UNO", "banco_id": "PA", "liquidez": "10.00",
                    "liquidez_inicial": "0.00", "participacion_pct": "100.00", "activo": True}),
        ("public.patrimonio", "V1", {"id": "V1", "referencia": "V1", "tipo_inmueble": "VIVIENDA", "activo": True,
                                     "disponible": True, "fecha_adquisicion": "2020-01-15", "participacion_pct": "100"}),
        ("public.tipo_gasto", "TH", {"id": "TH", "nombre": "HIPOTECA"}),
        ("public.tipo_gasto", "TP", {"id": "TP", "nombre": "PRESTAMO PERSONAL"}),
        ("public.tipo_gasto", "TF", {"id": "TF", "nombre": "FINANCIACION"}),
        (GA, "GH", {"id": "GH", "nombre": "CUOTA HIP", "tipo_id": "TH", "prestamo_id": "P1"}),
        (GA, "GP", {"id": "GP", "nombre": "CUOTA PREST", "tipo_id": "TP", "prestamo_id": "P2"}),
        (GA, "G1", {"id": "G1", "nombre": "COMPRA A PLAZOS", "tipo_id": "TF", "prestamo_id": "141", "cuotas": 3,
                    "importe_cuota": 10.1, "total": 30.3, "cuotas_restantes": 0, "importe_pendiente": 0,
                    "periodicidad": "MENSUAL", "fecha": "2025-01-10", "cuenta_id": "C1", "proveedor_id": "PT",
                    "activo": False}),
    ] + _prestamo("P1", "HIP. CASA", "GH", Decimal("1000.00"), "12.000", hip, vivienda="V1") \
      + _prestamo("P2", "PRÉSTAMO CERO", "GP", Decimal("300.00"), "0.000", cero) + list(extra)


def _b0(filas):
    b0 = {}
    for i, (c, k, d) in enumerate(filas, 1):
        t = json.dumps(d, ensure_ascii=False)
        b0.setdefault(c, {})[k] = F.RegistroB0(c, k, d, t, F.hash_registro(t), f"r{i}", i)
    return b0


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    monkeypatch.setattr(P5, "CONFIG_CUENTAS_ESTADO", "CONFIRMADA")
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})


def _fin(ds):
    ent = {e["id"]: e["nombre"] for e in ds.filas["entidades"].values()}
    return {ent[f["entidad_id"]]: f for f in ds.filas["financiaciones"].values()}


def _versiones(ds, nombre):
    eid = next(e for e, x in ds.filas["entidades"].items() if x["nombre"] == nombre)
    return sorted((v for v in ds.filas["financiacion_condiciones_versiones"].values()
                   if v["financiacion_entidad_id"] == eid), key=lambda v: v["vigente_desde"])


def test_hipoteca_demostrada_con_garantia_financiador_y_apertura():
    ds = P5.transformar(_b0(_filas()), SHA)
    f = _fin(ds)["HIP. CASA"]
    assert f["tipo_financiacion"] == "HIPOTECA" and f["moneda"] == "EUR" and f["estado"] == "ACTIVA"
    cal = _frances(Decimal("1000.00"), "12.000", 4, pagadas=2)
    assert f["saldo_principal_apertura"] == Decimal("1000.00") - cal[0]["capital"] - cal[1]["capital"]
    assert f["fecha_inicio_seguimiento"] == P5.FECHA_INICIO_LEDGER
    rel = list(ds.filas["entidad_relaciones"].values())
    assert len(rel) == 1 and rel[0]["entidad_origen_id"] == f["entidad_id"] and rel[0]["vigente_desde"] is None
    actor = ds.filas["actores_financieros"][f["financiador_actor_id"]]
    assert actor["tercero_id"] is not None
    assert [r["rol_codigo"] for r in ds.filas["tercero_roles"].values()] == ["FINANCIADOR"]


def test_prestamo_con_vivienda_no_recibe_garantia_y_sin_interes():
    filas = _filas()
    next(d for c, k, d in filas if k == "P2")["referencia_vivienda_id"] = "V1"
    ds = P5.transformar(_b0(filas), SHA)
    f = _fin(ds)["PRÉSTAMO CERO"]
    assert f["tipo_financiacion"] == "PRESTAMO"
    assert all(r["entidad_origen_id"] != f["entidad_id"] for r in ds.filas["entidad_relaciones"].values())
    assert _versiones(ds, "PRÉSTAMO CERO")[0]["sistema_amortizacion"] == "SIN_INTERES"
    assert any(x["regla"] == "D8-B2" and x["origen"] == f"{PR}/P2" for x in ds.ledger)


def test_frances_solo_si_se_reproduce_el_interes():
    ds = P5.transformar(_b0(_filas()), SHA)
    assert _versiones(ds, "HIP. CASA")[0]["sistema_amortizacion"] == "FRANCES"
    filas = _filas()
    q = next(d for c, k, d in filas if k == "P1-q3")
    q["interes"] = str(Decimal(q["interes"]) + Decimal("0.05"))
    q["importe_cuota"] = str(Decimal(q["importe_cuota"]) + Decimal("0.05"))
    ds2 = P5.transformar(_b0(filas), SHA)
    assert _versiones(ds2, "HIP. CASA")[0]["sistema_amortizacion"] == "OTRO"


def test_calendario_conservado_sin_correccion_y_sin_flag_pagado():
    filas = _filas()
    q = next(d for c, k, d in filas if k == "P2-q3")
    q["importe_cuota"] = str(Decimal(q["importe_cuota"]) + Decimal("0.30"))
    ds = P5.transformar(_b0(filas), SHA)
    assert len(ds.filas["financiacion_cuotas"]) == 7
    c3 = next(c for c in ds.filas["financiacion_cuotas"].values()
              if c["numero_cuota"] == 3 and c["importe_total_previsto"] == Decimal("100.30"))
    assert c3["capital_previsto"] == Decimal("100.00") and c3["prevision_id"] is None
    assert "pagada" not in c3
    assert any(x["regla"] == "D8-G" for x in ds.ledger)
    assert all(c["condicion_version_id"] for c in ds.filas["financiacion_cuotas"].values())


def test_cuota_vencida_antes_del_corte_no_se_desplaza():
    ds = P5.transformar(_b0(_filas()), SHA)
    marcadas = {x["origen"] for x in ds.ledger if x["regla"] == "D8-J"}
    assert f"{PQ}/P2-q1" in marcadas
    c1 = next(c for c in ds.filas["financiacion_cuotas"].values()
              if c["numero_cuota"] == 1 and c["fecha_vencimiento"] == "2026-08-01")
    assert c1 is not None


def test_versiones_decididas_se_asignan_por_numero_de_cuota(monkeypatch):
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {"P1": [
        # como en Allende: la cuota 2 vence el mismo dia en que empieza la v2, pero se rige por la v1
        {"motivo": "ALTA", "desde": None, "hasta": "2024-01-31", "tasa": "12", "cuotas": (1, 2)},
        {"motivo": "CAMBIO_CONDICIONES", "desde": "2024-02-01", "hasta": None, "tasa": "12", "cuotas": (3, None)}]})
    ds = P5.transformar(_b0(_filas()), SHA)
    v1, v2 = _versiones(ds, "HIP. CASA")
    assert (v1["motivo_version"], v1["vigente_hasta"], v2["motivo_version"]) == ("ALTA", "2024-01-31", "CAMBIO_CONDICIONES")
    por_v = {c["numero_cuota"]: c["condicion_version_id"] for c in ds.filas["financiacion_cuotas"].values()
             if c["financiacion_entidad_id"] == v1["financiacion_entidad_id"]}
    assert por_v[1] == por_v[2] == v1["id"] and por_v[3] == por_v[4] == v2["id"]
    assert v2["hecho_causa_id"] is None


def test_tipo_discrepante_falla_s20_y_en_lab_queda_pendiente():
    extra = _prestamo("P3", "HIP. OTRA", "GX", Decimal("300.00"), "0.000",
                      _frances(Decimal("300.00"), "0.000", 3, pagadas=3)) + \
        [(GA, "GX", {"id": "GX", "nombre": "CUOTA", "tipo_id": "TP", "prestamo_id": "P3"})]
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(_filas(extra)), SHA)
    assert e.value.codigo == "S20_TIPO_FINANCIACION"
    ds = P5.transformar(_b0(_filas(extra)), SHA, modo_lab=True)
    assert any(p.get("S20") == "TIPO_FINANCIACION" for p in ds.pendientes)


def test_apertura_que_no_cuadra_con_el_calendario_falla():
    filas = _filas()
    pr = next(d for c, k, d in filas if k == "P1")
    pr["capital_pendiente"] = str(Decimal(pr["capital_pendiente"]) + 1)
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(filas), SHA)
    assert e.value.codigo == "S9_APERTURA_NO_CUADRA"


def test_compra_financiada_liquidada_sin_calendario_ni_financiador():
    ds = P5.transformar(_b0(_filas()), SHA)
    f = _fin(ds)["COMPRA A PLAZOS"]
    assert (f["tipo_financiacion"], f["estado"], f["motivo_cierre"]) == ("COMPRA_FINANCIADA", "CERRADA", "LIQUIDADA")
    assert f["capital_original_contratado"] == Decimal("30.3") and f["saldo_principal_apertura"] == 0
    assert f["fecha_cierre_real"] is None and f["financiador_actor_id"] is None
    v = _versiones(ds, "COMPRA A PLAZOS")[0]
    assert (v["tipo_interes"], v["sistema_amortizacion"], v["tasa_anual_pct"]) == ("SIN_INTERES", "SIN_INTERES", None)
    assert all(c["financiacion_entidad_id"] != f["entidad_id"] for c in ds.filas["financiacion_cuotas"].values())


def test_compra_financiada_con_pendiente_falla_s20():
    filas = _filas()
    g = next(d for c, k, d in filas if k == "G1")
    g.update({"cuotas_restantes": 1, "importe_pendiente": 10.1})
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(filas), SHA)
    assert e.value.codigo == "S20_COMPRA_FINANCIADA_PENDIENTE"


def test_total_de_compra_distinto_de_cuotas_falla():
    filas = _filas()
    next(d for c, k, d in filas if k == "G1")["total"] = 3030
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(filas), SHA)
    assert e.value.codigo == "S9_COMPRA_FINANCIADA_TOTAL"


def test_sin_cuenta_configurada_no_se_inventa_moneda(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")})
    filas = _filas()
    next(d for c, k, d in filas if k == "P2")["cuenta_id"] = "C9"
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(_b0(filas), SHA)
    assert e.value.codigo == "S6_MONEDA_NO_DEMOSTRADA"


def test_participaciones_de_financiacion_no_se_infieren():
    ds = P5.transformar(_b0(_filas()), SHA)
    fins = set(ds.filas["financiaciones"])
    assert not [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] in fins]


def test_todo_destino_del_dominio_tiene_mapeo():
    ds = P5.transformar(_b0(_filas()), SHA)
    mapeados = {(m["tabla_destino"], m["registro_destino_id"]) for m in ds.filas["mapeos_importacion"].values()}
    for t in ("financiaciones", "financiacion_condiciones_versiones", "financiacion_cuotas",
              "entidad_relaciones", "tercero_roles"):
        assert all((t, i) in mapeados for i in ds.filas[t])


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    ds = P5.transformar(_b0(_filas()), SHA)
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["financiaciones"] == 3 and res["financiacion_cuotas"] == 7 and res["entidad_relaciones"] == 1
