# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_022_p5_r02_complementos.py
# Ruta: tests/migration/test_rv3_022_p5_r02_complementos.py
# Descripcion: RV3 / P5 v0.27.0. Destinos de los campos V3 decididos por el propietario (Q-R02, 2026-09-22),
#              sobre corpus SINTETICO sin PII. Discrimina: rango_pago -> financiaciones.notas concatenada;
#              evento -> etiquetas con variantes unificadas, una etiqueta por valor y sin fabricar filas sin
#              hecho; tienda -> notas del hecho y residual si no hay hecho; hecho no unico -> S7; referencia
#              de cuenta verificada como prefijo del nombre; km/litros -> magnitudes, 0 = DESCONOCIDO,
#              odometro regresivo, precio no verificable o captura dudosa -> residual; tolerancia de la
#              formula V3; y R02: residual -> PENDIENTE_S20 aunque se haya leido, verificado exige lectura.
#              0.2.0 (P5 v0.28.0): correccion de captura decidida (y fallo cerrado si el valor V3 no es el
#              exigido), desconocido decidido sin residual, "Kilometraje", tienda sin hecho DESCARTADA y
#              patrimonio_compra.notas -> propiedades.notas.
# Versión: 0.2.0
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
PR, GC, G, CB = "public.prestamo", "public.gastos_cotidianos", "public.gastos", "public.cuentas_bancarias"


def _ds():
    return P5.Dataset(owner=F.uuid_v3("TEST", "o", "usuarios", "u"))


def _hecho(ds, co, cl, notas=None):
    hid = F.uuid_v3(co, cl, "hechos_financieros", "hecho")
    ds.filas["hechos_financieros"][hid] = {"id": hid, "notas": notas}
    ds.mapear(co, cl, "hechos_financieros", hid, "hecho")
    return hid


def _fin(ds, cl, notas=None):
    eid = F.uuid_v3(PR, cl, "entidades", "financiacion")
    ds.filas["financiaciones"][eid] = {"entidad_id": eid, "notas": notas}
    return eid


def _cot(cl, fecha="2025-06-01", **kv):
    base = {"id": cl, "fecha": fecha, "evento": "141", "km": "141", "litros": "141", "precio_litro": "141",
            "importe_total": "50"}
    base.update(kv)
    return base


def _run(ds, fuente):
    return P5.dominio_12_r02_complementos(ds, fuente, F.contexto_de(fuente))


def _resid(ds):
    return {k: sorted((r["origen"].split("/", 1)[1], r["pregunta"]) for r in v)
            for k, v in ds.trazabilidad.get("r02_residuales", {}).items()}


# ---------------------------------------------------------------- Q-R02-6
def test_rango_pago_a_notas_de_financiacion_concatenadas():
    ds = _ds()
    a, b = _fin(ds, "P1"), _fin(ds, "P2", notas="previa")
    r = _run(ds, {PR: {"P1": {"id": "P1", "rango_pago": "28-31"}, "P2": {"id": "P2", "rango_pago": "1-3"},
                       "P3": {"id": "P3", "rango_pago": "141"}}})
    assert ds.filas["financiaciones"][a]["notas"] == P5.NOTA_RANGO_PAGO.format("28-31")
    assert ds.filas["financiaciones"][b]["notas"] == "previa\n" + P5.NOTA_RANGO_PAGO.format("1-3")
    assert r["rango_pago"] == 2 and not _resid(ds)


def test_rango_pago_sin_financiacion_es_residual():
    ds = _ds()
    _run(ds, {PR: {"P9": {"id": "P9", "rango_pago": "28-31"}}})
    assert _resid(ds) == {f"{PR}.rango_pago": [("P9", "Q-R02-6")]}


# ---------------------------------------------------------------- Q-R02-2
def test_evento_variantes_unificadas_una_etiqueta_por_valor():
    ds = _ds()
    for cl in ("c1", "c2", "c3", "c4"):
        _hecho(ds, GC, cl)
    r = _run(ds, {GC: {"c1": _cot("c1", evento="FAMILIA"), "c2": _cot("c2", evento="FAMILIA DE"),
                       "c3": _cot("c3", evento="ROMANTIC"), "c4": _cot("c4", evento="141")}})
    assert sorted(e["nombre"] for e in ds.filas["etiquetas"].values()) == ["FAMILIA", "ROMANTICO"]
    assert r["hecho_etiquetas"] == 3 and len(ds.filas["hecho_etiquetas"]) == 3
    et = {e["id"]: e["nombre"] for e in ds.filas["etiquetas"].values()}
    por_hecho = {x["hecho_id"]: et[x["etiqueta_id"]] for x in ds.filas["hecho_etiquetas"].values()}
    assert por_hecho[F.uuid_v3(GC, "c2", "hechos_financieros", "hecho")] == "FAMILIA"
    assert any(e.get("regla") == "R02-Q2-VARIANTE" and e["v3"] == "ROMANTIC" for e in ds.ledger)


def test_evento_desconocido_falla_cerrado():
    ds = _ds()
    _hecho(ds, GC, "c1")
    with pytest.raises(P5.ErrorP5) as e:
        _run(ds, {GC: {"c1": _cot("c1", evento="VIAJE")}})
    assert e.value.codigo == "S4_EVENTO_SIN_ETIQUETA"


def test_evento_sin_hecho_no_fabrica_etiqueta():
    ds = _ds()
    _run(ds, {GC: {"c1": _cot("c1", evento="AMIGOS")}})
    assert not ds.filas["etiquetas"] and not ds.filas["hecho_etiquetas"]
    assert _resid(ds) == {f"{GC}.evento": [("c1", "Q-R02-2")]}


# ---------------------------------------------------------------- Q-R02-4
def test_tienda_se_concatena_a_las_notas_del_hecho():
    ds = _ds()
    h = _hecho(ds, G, "g1", notas="comentario V3")
    r = _run(ds, {G: {"g1": {"id": "g1", "tienda": "AMAZON"}, "g2": {"id": "g2", "tienda": "NONE"}}})
    assert ds.filas["hechos_financieros"][h]["notas"] == "comentario V3\n" + P5.NOTA_TIENDA.format("AMAZON")
    assert r["tienda_notas"] == 1 and not _resid(ds)


def test_tienda_sin_hecho_se_descarta_con_traza():
    ds = _ds()
    r = _run(ds, {G: {"g1": {"id": "g1", "tienda": "APOLO FITNESS"}}})
    assert not _resid(ds) and r["descartes"] == 1
    assert [d["origen"] for d in ds.trazabilidad["r02_descartes"]] == [f"{G}/g1"]
    assert any(e.get("regla") == "R02-Q4-DESCARTE" for e in ds.ledger)


def test_hecho_no_unico_falla_cerrado():
    ds = _ds()
    _hecho(ds, G, "g1")
    h2 = F.uuid_v3(G, "g1", "hechos_financieros", "otro")
    ds.filas["hechos_financieros"][h2] = {"id": h2, "notas": None}
    ds.mapear(G, "g1", "hechos_financieros", h2, "otro")
    with pytest.raises(P5.ErrorP5) as e:
        _run(ds, {G: {"g1": {"id": "g1", "tienda": "AMAZON"}}})
    assert e.value.codigo == "S7_HECHO_NO_UNICO"


def test_referencia_de_cuenta_verificada_como_prefijo_del_nombre():
    ds = _ds()
    for cl, nombre in (("A", "NOMINA - BANCO X"), ("B", "GASTOS - BANCO Y")):
        cid = F.uuid_v3(CB, cl, "cuentas", "cuenta")
        ds.filas["cuentas"][cid] = {"id": cid, "nombre": nombre}
    r = _run(ds, {CB: {"A": {"id": "A", "referencia": "NOMINA"}, "B": {"id": "B", "referencia": "ALQUILERES"}}})
    assert r["referencias_verificadas"] == 1
    assert _resid(ds) == {f"{CB}.referencia": [("B", "Q-R02-4")]}


# ---------------------------------------------------------------- Q-R02-3
def test_magnitudes_odometro_y_litros_cero_es_desconocido():
    ds = _ds()
    h1, h2 = _hecho(ds, GC, "c1"), _hecho(ds, GC, "c2")
    r = _run(ds, {GC: {"c1": _cot("c1", "2025-06-01", km="115940", litros="36", precio_litro="1.39"),
                       "c2": _cot("c2", "2025-06-02", km="0", litros="0", precio_litro="0")}})
    vals = {(v["hecho_id"], v["unidad"]): v["valor"] for v in ds.filas["hecho_magnitudes"].values()}
    assert vals == {(h1, "km"): Decimal("115940"), (h1, "l"): Decimal("36")}
    assert sorted(m["nombre"] for m in ds.filas["magnitudes"].values()) == ["Combustible", "Kilometraje"]
    assert r["precio_litro_verificado"] == 1 and r["cero_desconocido"] == 3 and not _resid(ds)
    assert h2 not in {v["hecho_id"] for v in ds.filas["hecho_magnitudes"].values()}


def test_odometro_regresivo_es_residual_y_no_rebaja_el_maximo():
    ds = _ds()
    for cl in ("c1", "c2", "c3"):
        _hecho(ds, GC, cl)
    _run(ds, {GC: {"c1": _cot("c1", "2026-01-15", km="128097"), "c2": _cot("c2", "2026-01-30", km="12811"),
                   "c3": _cot("c3", "2026-02-13", km="20000")}})
    # c3 sigue siendo inferior a la ultima lectura valida: la lectura residual no rebaja el maximo
    assert _resid(ds) == {f"{GC}.km": [("c2", "Q-R02-3b"), ("c3", "Q-R02-3b")]}
    assert [v["valor"] for v in ds.filas["hecho_magnitudes"].values()] == [Decimal("128097")]


def test_precio_que_no_cumple_la_formula_o_sin_litros_es_residual():
    ds = _ds()
    for cl in ("c1", "c2"):
        _hecho(ds, GC, cl)
    _run(ds, {GC: {"c1": _cot("c1", litros="30", precio_litro="1.50"),  # 45 != 50
                   "c2": _cot("c2", litros="0", precio_litro="17785")}})
    assert _resid(ds) == {f"{GC}.precio_litro": [("c1", "Q-R02-3b"), ("c2", "Q-R02-3b")]}


def test_tolerancia_de_la_formula_es_una_unidad_de_cada_factor():
    # 33,84 l x 1,4774 = 49,9952 (litros redondeado de 50 / 1,4774): dentro de 0,0034 + 0,0148
    assert abs(Decimal("33.84") * Decimal("1.4774") - 50) <= P5._tolerancia_formula(Decimal("33.84"), Decimal("1.4774"))
    assert P5._tolerancia_formula(Decimal("35.11"), Decimal("1.42")) == Decimal("0.3511") + Decimal("0.0142")
    assert abs(Decimal("35.11") * Decimal("1.40") - 50) > P5._tolerancia_formula(Decimal("35.11"), Decimal("1.40"))


def test_captura_dudosa_no_materializa_litros(monkeypatch):
    monkeypatch.setattr(P5, "CAPTURA_DUDOSA_REPOSTAJE", {"c1": "motivo"})
    ds = _ds()
    _hecho(ds, GC, "c1")
    _run(ds, {GC: {"c1": _cot("c1", litros="30", precio_litro="1", importe_total="30")}})
    assert not ds.filas["hecho_magnitudes"]
    assert _resid(ds) == {f"{GC}.litros": [("c1", "Q-R02-3b")], f"{GC}.precio_litro": [("c1", "Q-R02-3b")]}


# ---------------------------------------------------------------- R02 con residuales y verificados
def test_r02_residual_es_pendiente_aunque_se_haya_leido(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_CAMPOS", {})
    monkeypatch.setattr(P5, "CAMPOS_PENDIENTES", {})
    ds = _ds()
    P5._residual(ds, "public.x", "campo", "k1", "Q-T", "motivo")
    r = P5.r02_disposicion_campos(ds, {"public.x": {"k1": {"id": "k1", "campo": "v"}}}, {("public.x", "campo")})
    assert r["R02_por_clase"]["PENDIENTE_S20"] == 1 and "CONSUMIDO" not in r["R02_por_clase"]
    assert [(p["pregunta"], p["campos"]) for p in ds.pendientes] == [("Q-T", ["public.x.campo (1 filas residuales)"])]


def test_r02_verificado_exige_que_la_verificacion_se_ejecute(monkeypatch):
    monkeypatch.setattr(P5, "DISPOSICION_CAMPOS", {})
    monkeypatch.setattr(P5, "CAMPOS_PENDIENTES", {})
    monkeypatch.setattr(P5, "CAMPOS_VERIFICADOS", {("public.x", "campo")})
    fuente = {"public.x": {"k1": {"id": "k1", "campo": "v"}}}
    r = P5.r02_disposicion_campos(_ds(), fuente, {("public.x", "campo")})
    assert r["R02_por_clase"]["CONTROL_DERIVADO_VERIFICADO"] == 1
    with pytest.raises(P5.ErrorP5) as e:
        P5.r02_disposicion_campos(_ds(), fuente, set())
    assert e.value.codigo == "S4_VERIFICACION_NO_EJECUTADA"


def test_declaraciones_reales_coherentes():
    assert set(P5.EVENTO_ETIQUETA.values()) == {"AMIGOS", "FAMILIA", "ROMANTICO", "LABORAL"}
    for c in (("public.gastos_cotidianos", "evento"), ("public.prestamo", "rango_pago"), ("public.gastos", "tienda"),
              ("public.cuentas_bancarias", "referencia")):
        assert c not in P5.CAMPOS_PENDIENTES and c not in P5.DISPOSICION_CAMPOS
    assert not P5.CAMPOS_VERIFICADOS & set(P5.DISPOSICION_CAMPOS)
    orden = P5.ORDEN_TABLAS
    assert orden.index("hechos_financieros") < orden.index("hecho_etiquetas")
    assert orden.index("etiquetas") < orden.index("hecho_etiquetas") < orden.index("mapeos_importacion")
    assert orden.index("magnitudes") < orden.index("hecho_magnitudes")


def test_transformar_invoca_los_complementos(monkeypatch):
    llamadas = []
    monkeypatch.setattr(P5, "dominio_12_r02_complementos", lambda ds, f, c: llamadas.append(ds.owner) or {})
    _s8 = importlib.util.spec_from_file_location("t8_r02c", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
    t8 = importlib.util.module_from_spec(_s8)
    _s8.loader.exec_module(t8)
    for k, v in (("CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")}),
                 ("CONFIG_CUENTAS_ESTADO", "CONFIRMADA"), ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}),
                 ("DOMINIO_12_DISPOSICION_ACTIVO", False)):
        monkeypatch.setattr(P5, k, v)
    ds = P5.transformar(t8._b0(t8._filas()), "0" * 64, modo_lab=True)
    assert llamadas == [ds.owner] and "r02_complementos" in ds.trazabilidad


def test_correccion_de_captura_decidida(monkeypatch):
    monkeypatch.setattr(P5, "CORRECCION_CAPTURA_PROPIETARIO", {("c2", "km"): (Decimal("12811"), Decimal("128111"))})
    ds = _ds()
    for cl in ("c1", "c2", "c3"):
        _hecho(ds, GC, cl)
    r = _run(ds, {GC: {"c1": _cot("c1", "2026-01-15", km="128097"), "c2": _cot("c2", "2026-01-30", km="12811"),
                       "c3": _cot("c3", "2026-02-13", km="129385")}})
    assert sorted(v["valor"] for v in ds.filas["hecho_magnitudes"].values()) == [
        Decimal("128097"), Decimal("128111"), Decimal("129385")]
    assert r["correcciones"] == 1 and not _resid(ds)
    assert any(e.get("regla") == "R02-Q3-CORRECCION" and e["v3"] == "12811" for e in ds.ledger)


def test_correccion_sobre_valor_distinto_falla_cerrado(monkeypatch):
    monkeypatch.setattr(P5, "CORRECCION_CAPTURA_PROPIETARIO", {("c1", "km"): (Decimal("12811"), Decimal("128111"))})
    ds = _ds()
    _hecho(ds, GC, "c1")
    with pytest.raises(P5.ErrorP5) as e:
        _run(ds, {GC: {"c1": _cot("c1", km="12812")}})
    assert e.value.codigo == "S9_CORRECCION_SOBRE_VALOR_DISTINTO"


def test_desconocido_decidido_no_materializa_ni_queda_pendiente(monkeypatch):
    monkeypatch.setattr(P5, "DESCONOCIDO_PROPIETARIO", {("c1", "precio_litro"): "m", ("c2", "litros"): "m",
                                                        ("c2", "precio_litro"): "m"})
    ds = _ds()
    for cl in ("c1", "c2"):
        _hecho(ds, GC, cl)
    r = _run(ds, {GC: {"c1": _cot("c1", litros="0", precio_litro="17785"),
                       "c2": _cot("c2", litros="30", precio_litro="1", importe_total="30")}})
    assert not ds.filas["hecho_magnitudes"] and not _resid(ds) and r["desconocido_decidido"] == 3


def test_notas_de_compra_a_notas_de_la_propiedad():
    ds = _ds()
    eid = F.uuid_v3("public.patrimonio", "V1", "entidades", "propiedad")
    ds.filas["propiedades"][eid] = {"entidad_id": eid, "notas": "previa"}
    r = _run(ds, {"public.patrimonio_compra": {"V1": {"patrimonio_id": "V1", "notas": "casa como inversion"},
                                               "V2": {"patrimonio_id": "V2", "notas": "otra"}}})
    assert ds.filas["propiedades"][eid]["notas"] == "previa\n" + P5.NOTA_COMPRA_PROPIEDAD.format("casa como inversion")
    assert r["compra_notas"] == 1 and _resid(ds) == {"public.patrimonio_compra.notas": [("V2", "Q-R02-4")]}
