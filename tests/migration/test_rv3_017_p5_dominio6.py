# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_017_p5_dominio6.py
# Ruta: tests/migration/test_rv3_017_p5_dominio6.py
# Descripcion: RV3 / P5 v0.19.0. Dominio 6 bloque 1 (hechos, efectos, atribuciones,
#              terceros, vinculos a entidades y relaciones) sobre corpus SINTETICO sin PII.
#              Discrimina: gasto con total + parte personal (COMPLETA/PARCIAL sin actores
#              ficticios), traspaso legacy sin efectos ni movimientos (opcion A), devolucion
#              OP-13 negativa con limite de origen, reembolso sin INGRESO con REEMBOLSO_DE,
#              repercusion 100 % a la contraparte, pendientes de fila sin fabricar datos,
#              determinismo y carga fisica RV3_IMPORT con ROLLBACK.
#   0.2.0: atribucion por vivienda decidida (D6-V) y total corregido (D6-W), P5 v0.20.0.
#   0.3.0: bloque 2, compras financiadas OP-15 (P5 v0.20.0).
#   0.4.0: ticket compartido (D6-Z), P5 v0.21.0.
#   0.4.1: la tabla de movimientos existe desde el dominio 7; se afirma que el dominio 6 no genera filas.
#   0.4.2: el helper de participaciones retira tambien los mapeos de las filas que borra (P5 v0.25.0).
#   0.5.0: invitado con importe V3 = total -> atribucion propia 0 (D6-INV, P5 v0.26.0).
#   0.6.0: contexto decidido aplicado tambien a un traspaso; contexto no aplicado -> S8 (P5 v0.33.0).
# Versión: 0.6.0
# ============================================================
from __future__ import annotations

import importlib.util
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
_s12 = importlib.util.spec_from_file_location("t12_d6", Path(__file__).resolve().parent / "test_rv3_012_p5_dominio10.py")
T12 = importlib.util.module_from_spec(_s12)
_s12.loader.exec_module(T12)
T8 = T12.T8
F = P5.fu
SHA = "0" * 64
G, GC, I = "public.gastos", "public.gastos_cotidianos", "public.ingresos"
N = "141"
DOMINIO_5 = True
DOMINIO_6 = True
TH = P5.TIPOS_HECHO_SEED


def _g(k, **kw):
    d = {"id": k, "nombre": f"GASTO {k}", "tipo_id": "TX", "prestamo_id": N, "periodicidad": "PAGO UNICO", "cuotas": 1,
         "fecha": "2026-03-10", "createon": "2026-03-10T10:00:00", "rango_pago": N, "importe": 40, "total": 40,
         "cuenta_id": "C1", "proveedor_id": N, "activo": False, "inactivatedon": N, "comentarios": N,
         "ultimo_pago_on": "2026-03-10T10:00:00", "referencia_vivienda_id": N}
    d.update(kw)
    return (G, k, d)


def _c(k, **kw):
    d = {"id": k, "tipo_id": "TX", "importe": 12.5, "importe_total": 12.5, "fecha": "2026-02-01", "cuenta_id": "C1",
         "pagado": True, "tipo_pago": 1, "cantidad": 1, "proveedor_id": N, "observaciones": N, "evento": N,
         "km": N, "litros": N, "precio_litro": N}
    d.update(kw)
    return (GC, k, d)


def _i(k, **kw):
    d = {"id": k, "concepto": f"INGRESO {k}", "tipo_id": "TX", "periodicidad": "PAGO UNICO",
         "fecha_inicio": "2026-04-02", "createon": "2026-04-02T10:00:00", "rango_cobro": N, "importe": 40,
         "cuenta_id": "C1", "activo": False, "inactivatedon": N, "ultimo_ingreso_on": "2026-04-02T10:00:00",
         "contrato_alquiler": N, "referencia_vivienda_id": N}
    d.update(kw)
    return (I, k, d)


NAT = {"TX": "SIN_CATEGORIA_TEST", "TT": "FUERA: transferencia entre cuentas propias",
       "TR": "FUERA: reembolso de suministros (reduce derecho)", "TV": "FUERA: devolucion de compra (reduce el gasto)"}


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    for k, v in (("CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")}),
                 ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {}),
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("ISA_TIPO_HECHO_DECIDIDO", None),
                 ("DOMINIO_5_ACTIVO", True), ("DOMINIO_6_ACTIVO", True)):
        monkeypatch.setattr(P5, k, v)
    monkeypatch.setattr(P5, "CATEGORIA_POR_TIPO_V3", {**P5.CATEGORIA_POR_TIPO_V3, **NAT})
    real = P5.clasificar

    def clas(ds, co, cl, f):
        t = f.get("tipo_id")
        if t in ("TX", "TF"):  # TF: compra a plazos del corpus T8
            return ("NULL", None)
        if t in NAT:
            return ("FUERA", NAT[t].split(":", 1)[1].strip())
        return real(ds, co, cl, f)
    monkeypatch.setattr(P5, "clasificar", clas)


def _t(extra=()):
    return P5.transformar(T8._b0(T12._filas(extra=tuple(extra))), SHA, modo_lab=True)


def _hecho(ds, co, cl):
    return ds.filas["hechos_financieros"].get(F.uuid_v3(co, cl, "hechos_financieros", "hecho"))


def _efectos(ds, h):
    return [e for e in ds.filas["hecho_efectos"].values() if e["hecho_id"] == h["id"]]


def _atribs(ds, e):
    return [a for a in ds.filas["efecto_atribuciones"].values() if a["efecto_id"] == e["id"]]


def _pend(ds, co, cl):
    return [p["codigo"] for p in ds.pendientes if p.get("dominio") == 6 and p["origen"] == f"{co}/{cl}"]


def _luz(monkeypatch, contraparte=True):
    """Gasto repercutido 100 % al inquilino sintetico PI (vivienda V1 / contrato K1) + su cobro."""
    monkeypatch.setattr(P5, "DERECHOS_V3", [{"id": "DER-LUZ-03", "modo": "TRANSITORIA", "genera": (G, "GL"),
                                             "evidencia": [(I, "IL")]}])
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (1, Decimal("40")))
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {"DER-LUZ-03": ("public.personas", "PI")} if contraparte else {})
    monkeypatch.setattr(P5, "ATRIBUCION_CONTRAPARTE_100", {"DER-LUZ-03"})
    return _t([_g("GL", referencia_vivienda_id="V1"), _i("IL", tipo_id="TR", referencia_vivienda_id="V1")])


def test_gasto_unico_total_atribuido_y_sin_tesoreria():
    ds = _t([_g("GU", proveedor_id="PT", comentarios="nota")])
    h = _hecho(ds, G, "GU")
    assert h["tipo_hecho_id"] == TH["GASTO"] and h["fecha_hecho"] == "2026-03-10"
    assert (h["estado_localizacion"], h["localidad_id"], h["moneda"], h["notas"]) == ("DESCONOCIDA", None, "EUR", "nota")
    (e,) = _efectos(ds, h)
    assert (e["tipo_efecto"], e["importe_delta"], e["estado_atribucion"]) == ("GASTO", Decimal("40"), "COMPLETA")
    (a,) = _atribs(ds, e)
    assert (a["actor_id"], a["importe_atribuido"]) == (ds.self_id, Decimal("40"))
    assert [t["rol_en_hecho"] for t in ds.filas["hecho_terceros"].values() if t["hecho_id"] == h["id"]] == ["VENDEDOR"]
    assert not ds.filas.get("movimientos_tesoreria") and not ds.filas.get("hecho_movimientos_tesoreria")
    assert "hecho_aportaciones_pago" not in ds.filas  # D6-Q: sin aportaciones en el historico


def test_invitado_conserva_total_y_parte_personal_cero_sin_actor_ficticio():
    ds = _t([_c("CI", tipo_pago=2, importe=0, importe_total=30, cantidad=3)])
    h = _hecho(ds, GC, "CI")
    assert (h["importe_total"], h["numero_participantes_total"]) == (Decimal("30"), 3)
    (e,) = _efectos(ds, h)
    assert (e["importe_delta"], e["estado_atribucion"]) == (Decimal("30"), "PARCIAL")
    assert [(a["actor_id"], a["importe_atribuido"]) for a in _atribs(ds, e)] == [(ds.self_id, Decimal("0"))]


@pytest.mark.parametrize("importe", [30, 12])
def test_invitado_con_importe_v3_distinto_de_cero_atribucion_propia_cero(importe):
    # 0.5.0 (P5 v0.26.0, D6-INV): en B0 63/67 invitados guardan importe = total; el canon (MV3 §27) fija
    # atribucion personal explicita 0 para tipo_pago=2, cualquiera que sea el importe V3.
    ds = _t([_c("CI", tipo_pago=2, importe=importe, importe_total=30, cantidad=3)])
    (e,) = _efectos(ds, _hecho(ds, GC, "CI"))
    assert (e["importe_delta"], e["estado_atribucion"]) == (Decimal("30"), "PARCIAL")
    assert [(a["actor_id"], a["importe_atribuido"]) for a in _atribs(ds, e)] == [(ds.self_id, Decimal("0"))]
    assert any(x.get("regla") == "D6-INV" and x["importe_v3"] == str(Decimal(importe)) for x in ds.ledger)


def test_a_medias_parcial_y_pago_propio_completo():
    ds = _t([_c("CM", tipo_pago=3, importe=10, importe_total=20, cantidad=2), _c("CP")])
    (em,) = _efectos(ds, _hecho(ds, GC, "CM"))
    (ep,) = _efectos(ds, _hecho(ds, GC, "CP"))
    assert (em["importe_delta"], em["estado_atribucion"]) == (Decimal("20"), "PARCIAL")
    assert _atribs(ds, em)[0]["importe_atribuido"] == Decimal("10")
    assert ep["estado_atribucion"] == "COMPLETA"


def test_parte_personal_superior_al_total_es_pendiente_sin_redondeo():
    ds = _t([_c("CR", importe=15.61, importe_total=15.605)])
    assert _hecho(ds, GC, "CR") is None
    assert _pend(ds, GC, "CR") == ["D6_PARTE_PERSONAL_SUPERA_TOTAL"]


def test_fecha_desconocida_no_se_fabrica():
    ds = _t([_c("CF", fecha=N)])
    assert _hecho(ds, GC, "CF") is None and _pend(ds, GC, "CF") == ["D6_FECHA_DESCONOCIDA"]


def test_traspaso_legacy_es_transferencia_sin_efectos_ni_movimientos():
    ds = _t([_g("GT", tipo_id="TT", importe=200, total=200)])
    h = _hecho(ds, G, "GT")
    assert h["tipo_hecho_id"] == TH["TRANSFERENCIA"] and h["importe_total"] == Decimal("200")
    assert _efectos(ds, h) == [] and h["presupuestable"] is False
    assert {"regla": "D6-T", "origen": f"{G}/GT"} in ds.ledger


def test_ingreso_sin_categoria_ni_naturaleza_falla_cerrado():
    with pytest.raises(P5.ErrorP5) as e:
        _t([_i("IR")])
    assert e.value.codigo == "S4_INGRESO_SIN_DISPOSICION"


def test_devolucion_con_origen_es_gasto_negativo_relacionado(monkeypatch):
    monkeypatch.setattr(P5, "DEVOLUCION_DECIDIDA", {(I, "ID"): (G, "GO")})
    ds = _t([_g("GO", importe=39, total=39), _i("ID", tipo_id="TV", importe=39)])
    h = _hecho(ds, I, "ID")
    assert h["tipo_hecho_id"] == TH["GASTO"]
    (e,) = _efectos(ds, h)
    assert (e["tipo_efecto"], e["importe_delta"]) == ("GASTO", Decimal("-39"))
    assert _atribs(ds, e)[0]["importe_atribuido"] == Decimal("-39")
    (r,) = [r for r in ds.filas["hecho_relaciones"].values() if r["hecho_origen_id"] == h["id"]]
    assert (r["tipo_relacion"], r["hecho_destino_id"], r["importe_relacionado"]) == \
        ("DEVOLUCION_DE", _hecho(ds, G, "GO")["id"], Decimal("39"))
    assert not any(x["tipo_efecto"] == "INGRESO" for x in ds.filas["hecho_efectos"].values())


def test_devolucion_que_excede_el_origen_falla(monkeypatch):
    monkeypatch.setattr(P5, "DEVOLUCION_DECIDIDA", {(I, "ID"): (G, "GO")})
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GO", importe=39, total=39), _i("ID", tipo_id="TV", importe=40)])
    assert e.value.codigo == "S9_DEVOLUCION_EXCEDE_ORIGEN"


def test_devolucion_sin_origen_no_inventa_relacion(monkeypatch):
    monkeypatch.setattr(P5, "DEVOLUCION_DECIDIDA", {(I, "ID"): None})
    ds = _t([_i("ID", importe=50), _g("GX", importe=60, total=60)])  # candidato plausible: no se vincula
    h = _hecho(ds, I, "ID")
    assert [e["importe_delta"] for e in _efectos(ds, h)] == [Decimal("-50")]
    assert _hecho(ds, G, "GX") is not None
    assert not any(r["hecho_origen_id"] == h["id"] for r in ds.filas["hecho_relaciones"].values())
    assert {"regla": "D6-D2", "origen": f"{I}/ID"} in ds.ledger


def test_repercusion_100_a_la_contraparte_y_reembolso_sin_ingreso(monkeypatch):
    ds = _luz(monkeypatch)
    did = F.uuid_v3(G, "GL", "entidades", "derecho")
    inquilino = ds.filas["derechos_obligaciones_financieras"][did]["contraparte_actor_id"]
    hg, hr = _hecho(ds, G, "GL"), _hecho(ds, I, "IL")
    ef = {e["tipo_efecto"]: e for e in _efectos(ds, hg)}
    assert set(ef) == {"GASTO", "DERECHO_COBRO"}
    assert [(a["actor_id"], a["importe_atribuido"]) for a in _atribs(ds, ef["GASTO"])] == [(inquilino, Decimal("40"))]
    assert ef["GASTO"]["estado_atribucion"] == "COMPLETA"
    assert hr["tipo_hecho_id"] == TH["REEMBOLSO"]
    (er,) = _efectos(ds, hr)
    assert (er["tipo_efecto"], er["importe_delta"]) == ("DERECHO_COBRO", Decimal("-40"))
    ligados = [x for x in ds.filas["hecho_entidades"].values() if x["entidad_id"] == did]
    assert sorted(x["efecto_id"] for x in ligados) == sorted([ef["DERECHO_COBRO"]["id"], er["id"]])
    assert sum(ds.filas["hecho_efectos"][x["efecto_id"]]["importe_delta"] for x in ligados) == 0
    (r,) = [r for r in ds.filas["hecho_relaciones"].values() if r["hecho_origen_id"] == hr["id"]]
    assert (r["tipo_relacion"], r["hecho_destino_id"]) == ("REEMBOLSO_DE", hg["id"])
    assert not any(x["tipo_efecto"] == "INGRESO" for x in ds.filas["hecho_efectos"].values())


def test_repercusion_sin_contraparte_queda_pendiente_y_bloquea_su_cobro(monkeypatch):
    ds = _luz(monkeypatch, contraparte=False)
    assert _hecho(ds, G, "GL") is None and _pend(ds, G, "GL") == ["D6_ATRIBUCION_GASTO_REEMBOLSADO"]
    assert _hecho(ds, I, "IL") is None and _pend(ds, I, "IL") == ["D6_GENERADOR_PENDIENTE"]


def test_vivienda_compartida_sin_decision_queda_pendiente(monkeypatch):
    monkeypatch.setattr(P5, "_participacion_entidad_self_100", lambda ds, eid: False)
    ds = _t([_g("GV", referencia_vivienda_id="V1"), _g("GN")])
    assert _hecho(ds, G, "GV") is None and _pend(ds, G, "GV") == ["D6_ATRIBUCION_ENTIDAD_COMPARTIDA"]
    assert _hecho(ds, G, "GN") is not None


def test_dataset_determinista_y_trazado():
    extra = [_g("GU"), _c("CI", tipo_pago=2, importe=0, importe_total=30), _g("GT", tipo_id="TT")]
    a, b = _t(extra), _t(extra)
    assert a.hash() == b.hash()
    mapeados = {m["registro_destino_id"] for m in a.filas["mapeos_importacion"].values()}
    for t in ("hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_terceros"):
        assert set(a.filas[t]) <= mapeados


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback(monkeypatch):
    monkeypatch.setattr(P5, "DEVOLUCION_DECIDIDA", {(I, "ID"): (G, "GO")})
    monkeypatch.setattr(P5, "DERECHOS_V3", [{"id": "DER-LUZ-03", "modo": "TRANSITORIA", "genera": (G, "GL"),
                                             "evidencia": [(I, "IL")]}])
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (1, Decimal("40")))
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {"DER-LUZ-03": ("public.personas", "PI")})
    monkeypatch.setattr(P5, "ATRIBUCION_CONTRAPARTE_100", {"DER-LUZ-03"})
    ds = _t([_g("GL", referencia_vivienda_id="V1"), _i("IL", tipo_id="TR", referencia_vivienda_id="V1"),
             _g("GO", importe=39, total=39), _i("ID", tipo_id="TV", importe=39), _g("GT", tipo_id="TT"),
             _c("CI", tipo_pago=2, importe=0, importe_total=30, cantidad=3),
             _c("CM", tipo_pago=3, importe=10, importe_total=20)])
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["hechos_financieros"] == 7 and res["hecho_relaciones"] == 2
    assert res["hecho_efectos"] == 7 and res["efecto_atribuciones"] == 7


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_atribucion_completa_descuadrada_rechazada():
    """El contrato fisico 0330 rechaza COMPLETA con suma distinta: el estado PARCIAL no es decorativo."""
    import psycopg
    ds = _t([_c("CM", tipo_pago=3, importe=10, importe_total=20)])
    (e,) = _efectos(ds, _hecho(ds, GC, "CM"))
    e["estado_atribucion"] = "COMPLETA"
    with pytest.raises(psycopg.errors.RaiseException):
        P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])


OTRO = "00000000-0000-5000-8000-0000000000aa"  # actor sintetico (solo validacion logica, no fisica)


def _con_participaciones(monkeypatch, filas):
    """Sustituye las participaciones de la vivienda V1 tras el dominio 4 por las indicadas."""
    real = P5.dominio_4_propiedades

    def d4(ds, fuente, ctx, modo_lab):
        real(ds, fuente, ctx, modo_lab)
        vid = F.uuid_v3("public.patrimonio", "V1", "entidades", "propiedad")
        for k in [k for k, v in ds.filas["entidad_participaciones"].items() if v["entidad_id"] == vid]:
            del ds.filas["entidad_participaciones"][k]
            # 0.4.2: retirar tambien sus mapeos (P5 v0.25.0 rechaza mapeos a destinos inexistentes)
            for mk in [mk for mk, m in ds.filas["mapeos_importacion"].items()
                       if (m["tabla_destino"], m["registro_destino_id"]) == ("entidad_participaciones", k)]:
                del ds.filas["mapeos_importacion"][mk]
        for n, (actor, pct, desde, hasta) in enumerate(filas):
            ds.filas["entidad_participaciones"][f"p{n}"] = {
                "id": f"p{n}", "entidad_id": vid, "actor_id": ds.self_id if actor == "SELF" else actor,
                "porcentaje": Decimal(pct), "vigente_desde": desde, "vigente_hasta": hasta}
            ds.mapear("public.patrimonio", "V1", "entidad_participaciones", f"p{n}", f"test.{n}")
    monkeypatch.setattr(P5, "dominio_4_propiedades", d4)


def test_vivienda_decidida_al_50_reparte_por_participacion_vigente(monkeypatch):
    monkeypatch.setattr(P5, "VIVIENDA_ATRIBUCION_DECIDIDA", {"V1": "PARTICIPACION"})
    _con_participaciones(monkeypatch, [("SELF", 50, "2025-01-01", None), (OTRO, 50, "2025-01-01", None),
                                       (OTRO, 100, "2024-01-01", "2024-12-31")])  # vigencia ya vencida
    ds = _t([_g("GF", importe=11.81, total=11.81, referencia_vivienda_id="V1")])
    (e,) = _efectos(ds, _hecho(ds, G, "GF"))
    assert (e["importe_delta"], e["estado_atribucion"]) == (Decimal("11.81"), "COMPLETA")
    got = sorted((a["actor_id"] == ds.self_id, a["importe_atribuido"], a["porcentaje_aplicado"], a["criterio_atribucion"])
                 for a in _atribs(ds, e))
    assert got == [(False, Decimal("5.905"), Decimal("50"), "PARTICIPACION_ENTIDAD"),
                   (True, Decimal("5.905"), Decimal("50"), "PARTICIPACION_ENTIDAD")]
    assert sum(x[1] for x in got) == e["importe_delta"]


def test_vivienda_decidida_100_propia_sin_participacion(monkeypatch):
    monkeypatch.setattr(P5, "VIVIENDA_ATRIBUCION_DECIDIDA", {"V1": "SELF_100"})
    _con_participaciones(monkeypatch, [(OTRO, 100, "2025-01-01", None)])
    ds = _t([_g("GB", referencia_vivienda_id="V1")])
    (e,) = _efectos(ds, _hecho(ds, G, "GB"))
    assert [(a["actor_id"], a["importe_atribuido"]) for a in _atribs(ds, e)] == [(ds.self_id, Decimal("40"))]


def test_total_corregido_por_el_propietario(monkeypatch):
    monkeypatch.setattr(P5, "IMPORTE_TOTAL_CORREGIDO", {(GC, "CR"): Decimal("15.61")})
    ds = _t([_c("CR", importe=15.61, importe_total=15.605)])
    h = _hecho(ds, GC, "CR")
    (e,) = _efectos(ds, h)
    assert (h["importe_total"], e["importe_delta"], e["estado_atribucion"]) == (Decimal("15.61"), Decimal("15.61"), "COMPLETA")
    assert _pend(ds, GC, "CR") == []


def _fin_g1(ds):
    return next(m["registro_destino_id"] for m in ds.filas["mapeos_importacion"].values()
                if m["tabla_destino"] == "financiaciones" and m["registro_origen_id"] == F.uuid_origen(G, "G1"))


def test_compra_financiada_gasto_total_y_deuda_vinculada_a_la_financiacion(monkeypatch):
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {(G, "G1"): None})
    ds = _t()
    h = _hecho(ds, G, "G1")
    assert (h["tipo_hecho_id"], h["fecha_hecho"], h["importe_total"]) == (TH["COMPRA_FINANCIADA"], "2025-01-10", Decimal("30.3"))
    ef = {e["tipo_efecto"]: e for e in _efectos(ds, h)}
    assert {k: v["importe_delta"] for k, v in ef.items()} == {"GASTO": Decimal("30.3"), "DEUDA": Decimal("30.3")}
    for e in ef.values():
        assert [(a["actor_id"], a["importe_atribuido"], a["criterio_atribucion"]) for a in _atribs(ds, e)] == \
            [(ds.self_id, Decimal("30.3"), "PARTICIPACION_ENTIDAD")]
    (v,) = [x for x in ds.filas["hecho_entidades"].values() if x["hecho_id"] == h["id"] and x["entidad_id"] == _fin_g1(ds)]
    assert (v["efecto_id"], v["tipo_relacion"]) == (ef["DEUDA"]["id"], "AFECTA_A")
    # las cuotas no crean gasto: un unico GASTO por la compra en todo el dataset para ese origen
    assert sum(1 for e in ds.filas["hecho_efectos"].values() if e["hecho_id"] == h["id"] and e["tipo_efecto"] == "GASTO") == 1


def test_compra_sin_participacion_no_presume_propietario():
    ds = _t()
    assert _hecho(ds, G, "G1") is None and _pend(ds, G, "G1") == ["D6_COMPRA_SIN_PARTICIPACION"]


def test_compra_dentro_del_seguimiento_seria_doble_conteo(monkeypatch):
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {(G, "G1"): None})
    monkeypatch.setattr(P5, "FECHA_INICIO_LEDGER", "2025-01-01")
    with pytest.raises(P5.ErrorP5) as e:
        _t()
    assert e.value.codigo == "S9_COMPRA_DENTRO_DEL_SEGUIMIENTO"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_compra_financiada_rollback(monkeypatch):
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {(G, "G1"): None})
    res = P5.validar_fisico(_t(), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["hechos_financieros"] == 1 and res["hecho_efectos"] == 2 and res["hecho_entidades"] == 1


def _compartido(monkeypatch, contraparte):
    monkeypatch.setattr(P5, "DERECHOS_V3", [{"id": "DER-X", "modo": "TRANSITORIA", "genera": (GC, "CT"),
                                             "evidencia": [(I, "IB")]}])
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (1, Decimal("11")))
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {"DER-X": ("public.personas", "PI")} if contraparte else {})
    monkeypatch.setattr(P5, "ATRIBUCION_COMPARTIDA", {"DER-X"})
    # la validacion de inquilino del dominio 8B no aplica a un ticket compartido sintetico
    monkeypatch.setattr(P5, "_validar_inquilino", lambda *a: None)
    return _t([_c("CT", importe=38.33, importe_total=38.33), _i("IB", tipo_id="TR", importe=11)])


def test_ticket_compartido_sin_actor_parte_propia_y_parcial(monkeypatch):
    ds = _compartido(monkeypatch, contraparte=False)
    h = _hecho(ds, GC, "CT")
    ef = {e["tipo_efecto"]: e for e in _efectos(ds, h)}
    assert (ef["GASTO"]["importe_delta"], ef["GASTO"]["estado_atribucion"]) == (Decimal("38.33"), "PARCIAL")
    assert [(a["actor_id"], a["importe_atribuido"]) for a in _atribs(ds, ef["GASTO"])] == [(ds.self_id, Decimal("27.33"))]
    assert ef["DERECHO_COBRO"]["importe_delta"] == Decimal("11")
    hr = _hecho(ds, I, "IB")
    assert hr["tipo_hecho_id"] == TH["REEMBOLSO"]
    assert [r["tipo_relacion"] for r in ds.filas["hecho_relaciones"].values() if r["hecho_origen_id"] == hr["id"]] == ["REEMBOLSO_DE"]


def test_ticket_compartido_con_actor_atribucion_completa(monkeypatch):
    ds = _compartido(monkeypatch, contraparte=True)
    ef = {e["tipo_efecto"]: e for e in _efectos(ds, _hecho(ds, GC, "CT"))}
    got = sorted((a["actor_id"] == ds.self_id, a["importe_atribuido"]) for a in _atribs(ds, ef["GASTO"]))
    assert got == [(False, Decimal("11")), (True, Decimal("27.33"))] and ef["GASTO"]["estado_atribucion"] == "COMPLETA"


def _dec_ctx(*registros):
    return P5.Decisiones(sha256="0" * 64, doc={"id": "T", "personas": {}, "participaciones": [], "contextos": [
        {"id": "CTX-T", "nombre": "Viaje T", "tipo": "VIAJE", "registros": list(registros)}]})


def _ctx_de(ds, co, cl):
    h = _hecho(ds, co, cl)
    ents = {e["id"]: e for e in ds.filas["entidades"].values()}
    return [(ents[x["entidad_id"]]["nombre"], x["tipo_relacion"]) for x in ds.filas["hecho_entidades"].values()
            if x["hecho_id"] == h["id"] and ents[x["entidad_id"]]["tipo_entidad"] == "CONTEXTO"]


def test_contexto_se_aplica_a_traspaso_y_gasto():
    ds = P5.transformar(T8._b0(T12._filas(extra=(_g("GT", tipo_id="TT", importe=200, total=200), _g("GC1")))), SHA,
                        modo_lab=True, decisiones=_dec_ctx(f"{G}/GT", f"{G}/GC1"))
    assert _hecho(ds, G, "GT")["tipo_hecho_id"] == TH["TRANSFERENCIA"]
    assert _ctx_de(ds, G, "GT") == [("Viaje T", "RELACIONADO_CON")] == _ctx_de(ds, G, "GC1")


def test_contexto_no_aplicado_falla_cerrado(monkeypatch):
    real = P5._H.entidad

    def sin_contexto(self, entidad_id, tipo_rel, efecto_id=None, rol="entidad"):
        if rol != "contexto":
            real(self, entidad_id, tipo_rel, efecto_id, rol)
    monkeypatch.setattr(P5._H, "entidad", sin_contexto)
    with pytest.raises(P5.ErrorP5) as e:
        P5.transformar(T8._b0(T12._filas(extra=(_g("GC1"),))), SHA, modo_lab=True, decisiones=_dec_ctx(f"{G}/GC1"))
    assert e.value.codigo == "S8_CONTEXTO_NO_APLICADO"
