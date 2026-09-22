# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_023_p5_r02_cuotas_direcciones_omisiones.py
# Ruta: tests/migration/test_rv3_023_p5_r02_cuotas_direcciones_omisiones.py
# Descripcion: RV3 / P5 v0.29.0. Respuestas Q-R02-1/5/7 (propietario 2026-09-22) sobre corpus SINTETICO sin PII.
#              Q-R02-1: cuota pagada -> dos hechos (DEUDA -capital AFECTA_A la financiacion, GASTO intereses con
#              categoria de costes financieros), fecha = vencimiento, atribucion por participacion, sin tesoreria,
#              pagada/fecha_pago coherentes, cuadre capital+interes, fallo si cae dentro del seguimiento,
#              residual sin participacion / con comisiones; ledger con fecha_pago y gasto de referencia.
#              Q-R02-5: tercero_direcciones COMERCIAL principal, localidad por id o por nombre, residual si no
#              resuelve o es incoherente, comunidad/pais solo validan, texto libre a observaciones.
#              Q-R02-7: omisiones solo a ledger, sin previsiones ni hechos. R02: SOLO_ORIGEN_Y_LEDGER exige lectura.
# Versión: 0.2.0
#              0.2.0 (P5 v0.35.0): localidad declarada por el propietario para residuales Q-R02-5: por codigo del
#              maestro V3 o como localidad/region nueva ausente del maestro (FUSIONADO a cada fila que la declara).
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
R02C = True
CU, PR, PV = "public.prestamo_cuota", "public.prestamo", "public.proveedores"
YO, OTRO = F.uuid_v3("TEST", "yo", "actores_financieros", "a"), F.uuid_v3("TEST", "otro", "actores_financieros", "a")
CAT = F.uuid_v3("TEST", "cat", "categorias_financieras", "c")


def _res():
    return {k: (Decimal(0) if k.endswith("_total") else 0) for k in (
        "cuotas_capital", "cuotas_intereses", "cuota_capital_total", "cuota_intereses_total",
        "direcciones_proveedor", "proveedor_solo_region", "omisiones_ledger")}


def _ds(participaciones=((YO, "50"), (OTRO, "50")), desde="2024-01-01", seguimiento="2026-09-05"):
    ds = P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))
    eid = F.uuid_v3(PR, "P1", "entidades", "financiacion")
    ds.filas["entidades"][eid] = {"id": eid, "nombre": "HIP. TEST"}
    ds.filas["financiaciones"][eid] = {"entidad_id": eid, "fecha_inicio_seguimiento": seguimiento}
    for actor, pct in participaciones:
        pid = F.uuid_v3("TEST", actor, "entidad_participaciones", "p")
        ds.filas["entidad_participaciones"][pid] = {"id": pid, "entidad_id": eid, "actor_id": actor,
                                                    "porcentaje": Decimal(pct), "vigente_desde": desde,
                                                    "vigente_hasta": None}
    ds.categorias = {("COSTES FINANCIEROS", "Intereses y costes de financiación"): CAT}
    ds.filas["categorias_financieras"][CAT] = {"id": CAT, "presupuestable_default": True}
    return ds, eid


def _cuota(cl="q1", **kv):
    base = {"id": cl, "prestamo_id": "P1", "num_cuota": 1, "pagada": True, "fecha_pago": "2025-10-29",
            "fecha_vencimiento": "2025-09-28", "capital": "300.00", "interes": "100.00", "importe_cuota": "400.00",
            "comisiones": "0.00", "seguros": "0.00", "gasto_id": "gasto-ref"}
    base.update(kv)
    return base


def _cuotas(ds, *filas):
    fuente = {CU: {f["id"]: f for f in filas}}
    r = _res()
    P5.cuotas_pagadas(ds, fuente, F.contexto_de(fuente), r)
    return r


def _efectos(ds, hid):
    return {e["tipo_efecto"]: e for e in ds.filas["hecho_efectos"].values() if e["hecho_id"] == hid}


# ---------------------------------------------------------------- Q-R02-1
def test_cuota_pagada_genera_dos_hechos_sin_tesoreria():
    ds, eid = _ds()
    r = _cuotas(ds, _cuota())
    hc = F.uuid_v3(CU, "q1", "hechos_financieros", "hecho.capital")
    hi = F.uuid_v3(CU, "q1", "hechos_financieros", "hecho.intereses")
    H = ds.filas["hechos_financieros"]
    assert set(H) == {hc, hi}
    assert H[hc]["tipo_hecho_id"] == P5.TIPOS_HECHO_SEED["GENERACION_DERECHO_OBLIGACION"]
    assert H[hi]["tipo_hecho_id"] == P5.TIPOS_HECHO_SEED["GASTO"]
    assert H[hc]["fecha_hecho"] == H[hi]["fecha_hecho"] == "2025-09-28"  # vencimiento, nunca fecha_pago
    assert {t: e["importe_delta"] for t, e in _efectos(ds, hc).items()} == {"DEUDA": Decimal("-300.00")}
    ei = _efectos(ds, hi)
    assert {t: e["importe_delta"] for t, e in ei.items()} == {"GASTO": Decimal("100.00")}
    assert ei["GASTO"]["categoria_id"] == CAT and H[hi]["presupuestable"] is True
    ed = _efectos(ds, hc)["DEUDA"]["id"]
    assert [(x["entidad_id"], x["tipo_relacion"], x["efecto_id"]) for x in ds.filas["hecho_entidades"].values()
            if x["hecho_id"] == hc] == [(eid, "AFECTA_A", ed)]
    atr = sorted((a["actor_id"], a["importe_atribuido"]) for a in ds.filas["efecto_atribuciones"].values()
                 if a["efecto_id"] == ed)
    assert atr == sorted([(YO, Decimal("-150.00")), (OTRO, Decimal("-150.00"))])
    assert not ds.filas["movimientos_tesoreria"] and not ds.filas["hecho_movimientos_tesoreria"]
    assert r["cuota_capital_total"] == Decimal("300.00") and r["cuota_intereses_total"] == Decimal("100.00")
    led = [e for e in ds.ledger if e["regla"] == "R02-Q1"]
    assert led and led[0]["fecha_pago"] == "2025-10-29" and led[0]["gasto_referencia"] == "gasto-ref"


def test_cuota_sin_intereses_solo_reduce_deuda_y_no_pagada_no_genera():
    ds, _ = _ds()
    r = _cuotas(ds, _cuota("q1", interes="0.00", importe_cuota="300.00"),
                _cuota("q2", pagada=False, fecha_pago=None))
    assert r["cuotas_capital"] == 1 and r["cuotas_intereses"] == 0 and len(ds.filas["hechos_financieros"]) == 1


def test_pagada_y_fecha_pago_incoherentes_fallan():
    ds, _ = _ds()
    with pytest.raises(P5.ErrorP5) as e:
        _cuotas(ds, _cuota(fecha_pago=None))
    assert e.value.codigo == "S9_CUOTA_PAGO_INCOHERENTE"


def test_cuota_que_no_cuadra_falla():
    ds, _ = _ds()
    with pytest.raises(P5.ErrorP5) as e:
        _cuotas(ds, _cuota(importe_cuota="401.00"))
    assert e.value.codigo == "S9_CUOTA_NO_CUADRA"


def test_cuota_dentro_del_seguimiento_falla_por_doble_conteo():
    ds, _ = _ds(seguimiento="2025-09-01")
    with pytest.raises(P5.ErrorP5) as e:
        _cuotas(ds, _cuota())
    assert e.value.codigo == "S9_CUOTA_DENTRO_DEL_SEGUIMIENTO"


def test_sin_participacion_vigente_o_con_comisiones_queda_residual():
    ds, _ = _ds(desde="2025-10-01")
    _cuotas(ds, _cuota("q1"), _cuota("q2", fecha_vencimiento="2025-10-28", comisiones="5.00"))
    assert not ds.filas["hechos_financieros"]
    motivos = sorted(x["motivo"] for x in ds.trazabilidad["r02_residuales"][f"{CU}.fecha_pago"])
    assert motivos == ["comisiones/seguros no modelados en la cuota", "financiacion sin participacion vigente"]


def test_participacion_que_no_suma_100_falla():
    ds, _ = _ds(participaciones=((YO, "60"), (OTRO, "30")))
    with pytest.raises(P5.ErrorP5) as e:
        _cuotas(ds, _cuota())
    assert e.value.codigo == "S9_PARTICIPACION_CUOTA_NO_CUADRA"


# ---------------------------------------------------------------- Q-R02-5
def _geo():
    return {"public.paises": {"1": {"id": "1", "nombre": "ESPAÑA"}},
            "public.regiones": {"1": {"id": "1", "nombre": "REGION DE MURCIA", "pais_id": 1}},
            "public.localidades": {"10": {"id": "10", "nombre": "TOTANA", "region_id": 1},
                                   "11": {"id": "11", "nombre": "ALHAMA", "region_id": 1},
                                   "13": {"id": "13", "nombre": "LORCA", "region_id": 1},
                                   "14": {"id": "14", "nombre": "LORCA", "region_id": 1}}}


def _prov(ds, filas):
    fuente = dict(_geo())
    fuente[PV] = {f["id"]: f for f in filas}
    for f in filas:
        tid = F.uuid_v3(PV, f["id"], "terceros", "tercero")
        ds.filas["terceros"][tid] = {"id": tid}
    r = _res()
    P5.direcciones_proveedores(ds, fuente, F.contexto_de(fuente), r)
    return r


def _p(cl, **kv):
    base = {"id": cl, "localidad_id": "141", "localidad": "141", "comunidad": "141", "pais": "141", "direccion": "141"}
    base.update(kv)
    return base


def test_direccion_comercial_por_id_y_por_nombre():
    ds = P5.Dataset(owner="o")
    r = _prov(ds, [_p("a", localidad_id="10", localidad="Totana", comunidad="Región de Murcia", pais="ESPAÑA"),
                   _p("b", localidad="ALHAMA", direccion="NUEVA CONDOMINA")])
    assert r["direcciones_proveedor"] == 2
    td = sorted((x["tipo"], x["principal"]) for x in ds.filas["tercero_direcciones"].values())
    assert td == [("COMERCIAL", True), ("COMERCIAL", True)]
    dirs = {d["localidad_id"]: d for d in ds.filas["direcciones"].values()}
    lb = F.uuid_v3("public.localidades", "11", "localidades", "localidad")
    assert dirs[lb]["observaciones"] == "NUEVA CONDOMINA" and dirs[lb]["via_nombre"] is None
    assert all(d["codigo_postal"] is None for d in dirs.values())


def test_localidad_no_resuelta_o_incoherente_queda_residual():
    ds = P5.Dataset(owner="o")
    _prov(ds, [_p("a", localidad="MADRID"), _p("b", localidad_id="10", localidad="ALHAMA"),
               _p("c", localidad_id="99"), _p("d", localidad_id="10", comunidad="ANDALUCIA"),
               _p("e", localidad_id="10", pais="FRANCIA"), _p("f", localidad="Lorca")])
    assert not ds.filas["direcciones"] and not ds.filas["tercero_direcciones"]
    res = {x["origen"].split("/")[1]: x["motivo"] for x in ds.trazabilidad["r02_residuales"][f"{PV}.localidad"]}
    assert res == {"a": "localidad sin maestro", "b": "nombre e id de localidad incoherentes",
                   "c": "localidad_id 99 inexistente", "d": "comunidad incoherente con la localidad",
                   "e": "pais incoherente con la localidad", "f": "localidad ambigua"}


def test_solo_comunidad_o_pais_no_crea_direccion():
    ds = P5.Dataset(owner="o")
    r = _prov(ds, [_p("a", comunidad="REGION DE MURCIA", pais="ESPAÑA")])
    assert r["proveedor_solo_region"] == 1 and not ds.filas["direcciones"]
    assert any(e["regla"] == "R02-Q5-SIN_LOCALIDAD" for e in ds.ledger)


# ---------------------------------------------------------------- Q-R02-7
def test_omisiones_solo_en_ledger():
    ds = P5.Dataset(owner="o")
    fuente = {"public.gastos": {"g1": {"id": "g1", "ultimo_omitido_on": "2026-05-04T10:47:34", "omitido_count": 2},
                                "g2": {"id": "g2", "ultimo_omitido_on": "141", "omitido_count": 0}},
              "public.ingresos": {"i1": {"id": "i1", "ultimo_omitido_on": "2026-01-10T08:10:57", "omitido_count": 0}}}
    r = _res()
    P5.omisiones_v3(ds, fuente, F.contexto_de(fuente), r)
    assert r["omisiones_ledger"] == 2
    assert sorted(e["origen"] for e in ds.ledger if e["regla"] == "R02-Q7-OMISION") == [
        "public.gastos/g1", "public.ingresos/i1"]
    assert not ds.filas["hechos_financieros"]


def test_r02_campo_de_ledger_exige_su_lectura(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_CAMPOS", {})
    monkeypatch.setattr(P5, "CAMPOS_PENDIENTES", {})
    monkeypatch.setattr(P5, "CAMPOS_LEDGER", {("public.x", "campo")})
    fuente = {"public.x": {"k1": {"id": "k1", "campo": "v"}}}
    r = P5.r02_disposicion_campos(P5.Dataset(owner="o"), fuente, {("public.x", "campo")})
    assert r["R02_por_clase"]["SOLO_ORIGEN_Y_LEDGER"] == 1
    with pytest.raises(P5.ErrorP5) as e:
        P5.r02_disposicion_campos(P5.Dataset(owner="o"), fuente, set())
    assert e.value.codigo == "S4_LEDGER_NO_EJECUTADO"


def test_declaraciones_reales_q_r02_cerradas():
    assert P5.CAMPOS_PENDIENTES == {}
    assert P5.DIRECCION_PROVEEDOR_TIPO == "COMERCIAL"
    assert not P5.CAMPOS_LEDGER & set(P5.DISPOSICION_CAMPOS) and not P5.CAMPOS_LEDGER & P5.CAMPOS_VERIFICADOS
    o = P5.ORDEN_TABLAS
    assert o.index("terceros") < o.index("tercero_direcciones") and o.index("direcciones") < o.index("tercero_direcciones")
    assert "previsiones" not in o  # Q-R02-7: la omision no crea previsiones


def test_complementos_invocan_cuotas_direcciones_y_omisiones():
    ds, _ = _ds()
    fuente = dict(_geo())
    fuente[CU] = {"q1": _cuota()}
    fuente[PV] = {"a": _p("a", localidad_id="10")}
    ds.filas["terceros"][F.uuid_v3(PV, "a", "terceros", "tercero")] = {"id": "t"}
    fuente["public.gastos"] = {"g1": {"id": "g1", "ultimo_omitido_on": "2026-05-04T10:47:34", "omitido_count": 1}}
    r = P5.dominio_12_r02_complementos(ds, fuente, F.contexto_de(fuente))
    assert (r["cuotas_capital"], r["cuotas_intereses"], r["direcciones_proveedor"], r["omisiones_ledger"]) == (1, 1, 1, 1)


def _geo_pais():
    ds = P5.Dataset(owner="o")
    pid = F.uuid_v3("public.paises", "1", "paises", "pais")
    ds.filas["paises"][pid] = {"id": pid, "nombre": "ESPAÑA"}
    return ds


def test_localidad_decidida_por_codigo_ignora_literal_incoherente(monkeypatch):
    monkeypatch.setattr(P5, "LOCALIDAD_PROVEEDOR_DECIDIDA", {"a": ("ID", "11")})
    ds = _geo_pais()
    r = _prov(ds, [_p("a", localidad="9", comunidad="ANDALUCIA")])
    assert r["direcciones_proveedor"] == 1 and not ds.trazabilidad.get("r02_residuales")
    (d,) = ds.filas["direcciones"].values()
    assert d["localidad_id"] == F.uuid_v3("public.localidades", "11", "localidades", "localidad")
    led = [e for e in ds.ledger if e["regla"] == "R02-Q5-DECIDIDA"]
    assert led[0]["decision"] == "ID:11" and led[0]["v3"]["comunidad"] == "ANDALUCIA"


def test_localidad_decidida_inexistente_falla(monkeypatch):
    monkeypatch.setattr(P5, "LOCALIDAD_PROVEEDOR_DECIDIDA", {"a": ("ID", "99")})
    with pytest.raises(P5.ErrorP5) as e:
        _prov(_geo_pais(), [_p("a", localidad="X")])
    assert e.value.codigo == "S8_LOCALIDAD_DECIDIDA_INEXISTENTE"


def test_localidad_nueva_declarada_una_vez_y_trazada_a_cada_fila(monkeypatch):
    monkeypatch.setattr(P5, "LOCALIDAD_PROVEEDOR_DECIDIDA", {"a": ("NUEVA", "MADRID"), "b": ("NUEVA", "MADRID")})
    monkeypatch.setattr(P5, "LOCALIDADES_DECLARADAS", {"MADRID": {"region": "MADRID", "pais": "ESPAÑA"}})
    ds = _geo_pais()
    r = _prov(ds, [_p("a", localidad="MADRID", comunidad="MADRID"), _p("b", localidad="MADRID")])
    assert r["direcciones_proveedor"] == 2
    lid = P5._id_declarada("MADRID", "localidad")
    rid = P5._id_declarada("MADRID", "region")
    assert ds.filas["localidades"][lid] == {"id": lid, "region_id": rid, "nombre": "MADRID", "codigo_oficial": None,
                                             "codigo_oficial_tipo": None}
    assert ds.filas["regiones"][rid]["pais_id"] in ds.filas["paises"]
    assert {d["localidad_id"] for d in ds.filas["direcciones"].values()} == {lid}
    fus = sorted((m["tabla_destino"], m["tipo_mapping"]) for m in ds.filas["mapeos_importacion"].values()
                 if m["registro_destino_id"] in (lid, rid))
    assert fus == [("localidades", "FUSIONADO")] * 2 + [("regiones", "FUSIONADO")] * 2


def test_localidad_nueva_sin_pais_en_maestro_falla(monkeypatch):
    monkeypatch.setattr(P5, "LOCALIDAD_PROVEEDOR_DECIDIDA", {"a": ("NUEVA", "X")})
    monkeypatch.setattr(P5, "LOCALIDADES_DECLARADAS", {"X": {"region": "R", "pais": "FRANCIA"}})
    with pytest.raises(P5.ErrorP5) as e:
        _prov(_geo_pais(), [_p("a", localidad="X")])
    assert e.value.codigo == "S8_PAIS_DECLARADO_SIN_MAESTRO"


def test_declaracion_real_diez_proveedores():
    sp = importlib.util.spec_from_file_location("p5_real_023", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
    real = importlib.util.module_from_spec(sp)
    sys.modules["p5_real_023"] = real
    try:
        sp.loader.exec_module(real)
    finally:
        sys.modules.pop("p5_real_023", None)
    dec = real.LOCALIDAD_PROVEEDOR_DECIDIDA
    assert len(dec) == 10 and sum(1 for v in dec.values() if v == ("NUEVA", "MADRID")) == 6
    assert dec["ITV-PROVEEDOR-JSRGO7"] == ("ID", "1") and dec["PROV-2FWYAS"] == ("ID", "25")
    assert dec["LOT-PROVEEDOR-QLSPRE"] == dec["SAB-PROVEEDOR-AL3ACE"] == ("ID", "9")
