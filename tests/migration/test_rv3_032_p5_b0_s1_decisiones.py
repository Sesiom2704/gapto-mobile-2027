# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_032_p5_b0_s1_decisiones.py
# Ruta: tests/migration/test_rv3_032_p5_b0_s1_decisiones.py
# Descripcion: RV3 / P5 v0.36.0 (mandato correctivo 2026-09-22). Corpus SINTETICO sin PII.
#              Fianza con contraparte decidida desde el origen (D10-N) frente a la regla del inquilino principal;
#              contrato V3 recreado fusionado en el contrato real (D10-L): un solo contrato, cancelacion V3 como
#              artificio, fecha_fin del recreado no aplicada, cotitulares al mismo nivel (D10-M), avalista y gestor
#              continuan, una sola fianza, renta versionada 550 -> 561 en UNA regla (D5-S1R); determinismo de la
#              fusion (S9); derecho S1 cobrado sin factura generadora (D8B-S1) sin ingreso ficticio; clasificacion
#              por registro de altas S1; decision sobre fila B0 ausente en S1 -> NO_APLICA_S1_FILA_AUSENTE (G1).
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
_s12 = importlib.util.spec_from_file_location("t12_032", Path(__file__).resolve().parent / "test_rv3_012_p5_dominio10.py")
T12 = importlib.util.module_from_spec(_s12)
_s12.loader.exec_module(T12)
_s10 = importlib.util.spec_from_file_location("t10_032", Path(__file__).resolve().parent / "test_rv3_010_p5_dominio8b.py")
T10 = importlib.util.module_from_spec(_s10)
_s10.loader.exec_module(T10)
T8 = T12.T8
F = P5.fu
SHA = "0" * 64
N = "141"
G, I, CB, CC, CP = "public.gastos", "public.ingresos", "public.cuentas_bancarias", "public.contratos", "public.contratos_participantes"
DOMINIO_5 = True
TH = P5.TIPOS_HECHO_SEED
RECREADO = {"K2": {"original": "K1", "ingreso_original": "IR", "ingreso_recreado": "IR2"}}


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    for k, v in (("CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR")}),
                 ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {}),
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("ISA_TIPO_HECHO_DECIDIDO", None), ("DOMINIO_5_ACTIVO", True),
                 ("FIANZA_CONTRAPARTE_DECIDIDA", {}), ("CONTRATO_RECREADO_V3", {})):
        monkeypatch.setattr(P5, k, v)
    monkeypatch.setattr(P5, "CATEGORIA_POR_TIPO_V3", {**P5.CATEGORIA_POR_TIPO_V3, "TX": "SIN_CATEGORIA_TEST"})
    real = P5.clasificar
    monkeypatch.setattr(P5, "clasificar", lambda ds, co, cl, f: ("NULL", None) if f.get("tipo_id") == "TX" else real(ds, co, cl, f))


def _i(k, **kw):
    d = {"id": k, "concepto": f"ALQ {k}", "tipo_id": "TX", "periodicidad": "MENSUAL", "fecha_inicio": "2024-09-01",
         "createon": "2024-09-01T10:00:00", "rango_cobro": "1-3", "importe": 550, "cuenta_id": "C1", "activo": True,
         "inactivatedon": N, "ultimo_ingreso_on": N, "contrato_alquiler": N, "referencia_vivienda_id": N}
    d.update(kw)
    return (I, k, d)


PF = ("public.personas", "PF", {"id": "PF", "nombre_completo": "Cotitular", "email": "f@example.invalid"})
P5_F = (CP, "P5", {"id": "P5", "contrato_id": "K1", "persona_id": "PF", "rol": "inquilino", "es_principal": False, "inactivatedon": N})


def _escenario(recreado=True, k2=None, ir2=None):
    con = {"renta_mensual": "550.00", "fianza": "550.00"}
    extra = [PF, P5_F, _i("IR", contrato_alquiler="K1")]
    if recreado:
        con.update(estado="cancelado", inactivatedon="2026-09-01T17:03:39+00:00")
        extra[2] = _i("IR", contrato_alquiler="K1", activo=False, inactivatedon="2026-09-01T17:03:40")
        c2 = {"id": "K2", "patrimonio_id": "V1", "estado": "activo", "objeto_alquiler": "completa",
              "fecha_inicio": "2026-09-01", "fecha_fin": "2027-09-01", "incremento_ipc": True, "observaciones": N,
              "renta_mensual": "561.00", "fianza": "550.00", "createon": "2026-09-01T17:04:16+00:00", "inactivatedon": None}
        c2.update(k2 or {})
        extra += [(CC, "K2", c2),
                  (CP, "P6", {"id": "P6", "contrato_id": "K2", "persona_id": "PI", "rol": "inquilino", "es_principal": False,
                              "inactivatedon": None}),
                  (CP, "P7", {"id": "P7", "contrato_id": "K2", "persona_id": "PF", "rol": "inquilino", "es_principal": False,
                              "inactivatedon": None}),
                  _i("IR2", contrato_alquiler="K2", importe=561, fecha_inicio="2026-09-01",
                     createon="2026-09-01T17:05:00", **(ir2 or {}))]
    return T12._filas(con=con, extra=tuple(extra))


def _t(filas, monkeypatch=None, recreado=True, fianza_pf=True):
    if monkeypatch is not None:
        if recreado:
            monkeypatch.setattr(P5, "CONTRATO_RECREADO_V3", RECREADO)
        if fianza_pf:
            monkeypatch.setattr(P5, "FIANZA_CONTRAPARTE_DECIDIDA", {"K1": ("public.personas", "PF")})
    return P5.transformar(T8._b0(filas), SHA, modo_lab=True)


def _eid(k):
    return F.uuid_v3(CC, k, "entidades", "contrato")


def _p(ds, k):
    return ds.filas["contrato_participantes"][F.uuid_v3(CP, k, "contrato_participantes", "participante")]


def _actor(k):
    return F.uuid_v3("public.personas", k, "actores_financieros", "actor")


def _fianzas(ds):
    return [d for d in ds.filas["derechos_obligaciones_financieras"].values()
            if ds.filas["entidades"][d["entidad_id"]]["nombre"].startswith("FIANZA")]


# ---------------------------------------------------------------- fianza (B0)
def test_fianza_contraparte_decidida_desde_origen_y_no_marina(monkeypatch):
    ds = _t(_escenario(recreado=False), monkeypatch, recreado=False)
    (f,) = _fianzas(ds)
    assert f["contraparte_actor_id"] == _actor("PF") and f["importe_original_documentado"] == Decimal("550")
    assert any(e["regla"] == "D10-N" for e in ds.ledger)


def test_sin_decision_la_regla_del_principal_sigue_vigente(monkeypatch):
    ds = _t(_escenario(recreado=False), monkeypatch, recreado=False, fianza_pf=False)
    (f,) = _fianzas(ds)
    assert f["contraparte_actor_id"] == _actor("PI")


def test_fianza_decidida_a_no_inquilino_falla(monkeypatch):
    monkeypatch.setattr(P5, "FIANZA_CONTRAPARTE_DECIDIDA", {"K1": ("public.personas", "PA2")})
    with pytest.raises(P5.ErrorP5) as e:
        _t(_escenario(recreado=False))
    assert e.value.codigo == "S1_FIANZA_CONTRAPARTE_NO_INQUILINO"


# ---------------------------------------------------------------- contrato recreado (S1)
def test_un_solo_contrato_real_vigente_desde_2024(monkeypatch):
    ds = _t(_escenario(), monkeypatch)
    assert list(ds.filas["contratos"]) == [_eid("K1")] and _eid("K2") not in ds.filas["entidades"]
    k = ds.filas["contratos"][_eid("K1")]
    assert (k["fecha_inicio"], k["estado_documental"], k["fecha_fin_prevista"], k["fecha_fin_real"]) == \
        ("2024-09-01", "FORMALIZADO", None, None)
    maps = [m for m in ds.filas["mapeos_importacion"].values() if m["registro_origen_id"] == F.uuid_origen(CC, "K2")]
    assert {(m["tabla_destino"], m["tipo_mapping"]) for m in maps} >= {("entidades", "FUSIONADO"), ("contratos", "FUSIONADO")}
    assert all(m["registro_destino_id"] in (_eid("K1"), F.uuid_v3(CC, "K1", "entidades", "fianza"),
                                            F.uuid_v3(CC, "K1", "contrato_revision_renta_versiones", "v1"))
               or m["tabla_destino"] in ("reglas_financieras", "regla_versiones") for m in maps)


def test_cotitulares_mismo_nivel_y_participantes_originales_continuan(monkeypatch):
    ds = _t(_escenario(), monkeypatch)
    marina, francisco = _p(ds, "P1"), _p(ds, "P5")
    assert (marina["rol"], marina["principal"], marina["vigente_hasta"]) == ("INQUILINO", False, None)
    assert (francisco["rol"], francisco["principal"], francisco["vigente_hasta"]) == ("INQUILINO", False, None)
    assert _p(ds, "P4")["rol"] == "AVALISTA" and _p(ds, "P4")["vigente_hasta"] is None
    assert _p(ds, "P2")["rol"] == "GESTOR" and _p(ds, "P2")["vigente_hasta"] is None
    assert len(ds.filas["contrato_participantes"]) == 5  # P1..P5: los del recreado no crean filas
    for k, gemelo in (("P6", "P1"), ("P7", "P5")):
        (m,) = [m for m in ds.filas["mapeos_importacion"].values() if m["registro_origen_id"] == F.uuid_origen(CP, k)]
        assert (m["tipo_mapping"], m["registro_destino_id"]) == ("FUSIONADO", _p(ds, gemelo)["id"])


def test_una_sola_fianza_de_francisco(monkeypatch):
    ds = _t(_escenario(), monkeypatch)
    (f,) = _fianzas(ds)
    assert f["contraparte_actor_id"] == _actor("PF") and f["contraparte_actor_id"] != _actor("PI")


def test_renta_versionada_en_una_sola_regla(monkeypatch):
    ds = _t(_escenario(), monkeypatch)
    (r,) = ds.filas["reglas_financieras"].values()
    assert r["entidad_origen_id"] == _eid("K1") and ds.filas["contratos"][_eid("K1")]["regla_renta_id"] == r["id"]
    vs = sorted((v for v in ds.filas["regla_versiones"].values() if v["regla_id"] == r["id"]), key=lambda v: v["vigente_desde"])
    assert [(v["vigente_desde"], v["vigente_hasta"], v["importe_fijo"]) for v in vs] == \
        [("2024-09-01", "2026-08-31", Decimal("550")), ("2026-09-01", None, Decimal("561"))]
    assert any(e["regla"] == "D5-S1R" for e in ds.ledger)


@pytest.mark.parametrize("cambio, codigo", [
    ({"fianza": "600.00"}, "S9_RECREACION_NO_DETERMINISTA"),
    ({"patrimonio_id": "OTRA"}, "S9_RECREACION_NO_DETERMINISTA"),
    ({"fecha_inicio": "2026-10-01"}, "S9_RECREACION_NO_DETERMINISTA"),
])
def test_fusion_no_determinista_falla(monkeypatch, cambio, codigo):
    with pytest.raises(P5.ErrorP5) as e:
        _t(_escenario(k2=cambio), monkeypatch)
    assert e.value.codigo == codigo


def test_renta_con_hueco_entre_versiones_falla(monkeypatch):
    filas = [x if x[:2] != (I, "IR") else _i("IR", contrato_alquiler="K1", activo=False,
                                                inactivatedon="2026-08-15T10:00:00") for x in _escenario()]
    with pytest.raises(P5.ErrorP5) as e:
        _t(filas, monkeypatch)
    assert e.value.codigo == "S9_RENTA_VERSIONES_NO_CONTIGUAS"


def test_sin_recreado_no_hay_fusion(monkeypatch):
    ds = _t(_escenario(recreado=False), monkeypatch)  # la decision solo actua si la fila recreada existe
    assert _p(ds, "P1")["principal"] is True and not any(e["regla"] in ("D10-L", "D10-M", "D5-S1R") for e in ds.ledger)


# ---------------------------------------------------------------- derecho S1 sin factura generadora
def test_derecho_s1_cobrado_antes_del_cargo_sin_ingreso(monkeypatch):
    for k, v in T10.__dict__.items():
        pass
    monkeypatch.setattr(P5, "DERECHOS_V3", T10.CAT)
    monkeypatch.setattr(P5, "CANON_TRANSITORIAS", (2, Decimal("15.25")))
    monkeypatch.setattr(P5, "CANON_UNIVERSIDAD", Decimal("150"))
    monkeypatch.setattr(P5, "CONTRAPARTE_V3_DECIDIDA", {})
    monkeypatch.setattr(P5, "CATEGORIAS_ACTIVAS", False)
    monkeypatch.setattr(P5, "DERECHOS_S1", [{"id": "D-S1", "genera": None, "evidencia": [(I, "IS1")], "modo": "TRANSITORIA"}])
    filas = T10._filas() + [(I, "IS1", {"id": "IS1", "concepto": "LUZ 8", "importe": 88.44, "fecha_inicio": "2026-09-01"})]
    ds = P5.transformar(T8._b0(filas), SHA, modo_lab=True)
    d = ds.filas["derechos_obligaciones_financieras"][F.uuid_v3(I, "IS1", "entidades", "derecho")]
    assert (d["estado"], d["motivo_cierre"], d["saldo_apertura"], d["importe_original_documentado"]) == \
        ("CERRADA", "LIQUIDADA", Decimal("0"), Decimal("88.44"))
    assert any(e["regla"] == "D8B-S1" for e in ds.ledger)
    h = ds.filas["hechos_financieros"].get(F.uuid_v3(I, "IS1", "hechos_financieros", "hecho"))
    if h is not None:  # con dominio 6 activo: el cobro reduce el derecho y no es INGRESO
        assert h["tipo_hecho_id"] != TH["INGRESO"]
        efs = [e for e in ds.filas["hecho_efectos"].values() if e["hecho_id"] == h["id"]]
        assert all(e["tipo_efecto"] != "INGRESO" for e in efs)
    sin = P5.transformar(T8._b0(T10._filas()), SHA, modo_lab=True)  # sin la fila S1, el derecho no existe
    assert F.uuid_v3(I, "IS1", "entidades", "derecho") not in sin.filas["derechos_obligaciones_financieras"]


def test_declaracion_real_s1():
    sp = importlib.util.spec_from_file_location("p5_real_032", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
    real = importlib.util.module_from_spec(sp)
    sys.modules["p5_real_032"] = real
    try:
        sp.loader.exec_module(real)
    finally:
        sys.modules.pop("p5_real_032", None)
    assert real.FIANZA_CONTRAPARTE_DECIDIDA == {"CON-MARINA-240901": ("public.personas", "PER-8C62EC5126")}
    assert real.CONTRATO_RECREADO_V3["CON-08D54D30C8"]["original"] == "CON-MARINA-240901"
    assert real.CONTRAPARTE_V3_DECIDIDA["DER-LUZ-08"] == ("public.personas", "PER-8C62EC5126")
    assert real.CLASIFICACION_REGISTRO_S1 == {
        "public.gastos/gasto-81srs1": "VIVIENDA Y HOGAR > Suministros > Electricidad",
        "public.gastos/gasto-f7i6dm": "OCIO Y CULTURA > Videojuegos",
        "public.gastos/gasto-pty1ta": "COMUNICACIONES Y DIGITAL > Software y servicios digitales"}
    assert [d["id"] for d in real.DERECHOS_S1] == ["DER-LUZ-08"]


# ---------------------------------------------------------------- G1 y clasificacion por registro
def test_decision_sobre_fila_ausente_en_s1():
    class D:
        doc = {"clasificacion": {"registros": {"public.gastos/GX": None}}}
    ds = P5.Dataset(owner="o")
    ds.categorias, ds.decisiones = {("A",): "c"}, D()
    with pytest.raises(P5.ErrorP5) as e:
        P5.verificar_clasificacion(ds, {"public.gastos": {}})
    assert e.value.codigo == "S8_CLASIFICACION_SIN_ORIGEN"
    ds.ausentes_s1 = frozenset({"public.gastos/GX"})
    P5.verificar_clasificacion(ds, {"public.gastos": {}})
    assert [e for e in ds.ledger if e["regla"] == "NO_APLICA_S1_FILA_AUSENTE"] == \
        [{"regla": "NO_APLICA_S1_FILA_AUSENTE", "origen": "public.gastos/GX", "decision": "clasificacion"}]


def test_clasificacion_por_registro_s1(monkeypatch):
    monkeypatch.setattr(P5, "CLASIFICACION_REGISTRO_S1", {"public.gastos/GX": "OCIO Y CULTURA > Videojuegos"})
    ds = P5.Dataset(owner="o")
    ds.categorias = {("OCIO Y CULTURA", "Videojuegos"): "cat-v", ("OCIO Y CULTURA",): "cat-o"}
    ds.decisiones = None
    assert P5.clasificar(ds, "public.gastos", "GX", {"tipo_id": "CAP-TIPOGASTO-334BFEC7"}) == ("CAT", "cat-v")
    with pytest.raises(P5.ErrorP5):
        P5.clasificar(ds, "public.gastos", "GY", {"tipo_id": "CAP-TIPOGASTO-334BFEC7"})  # sin decision -> S20


def test_participante_del_recreado_sin_gemelo_falla(monkeypatch):
    filas = _escenario() + [(CP, "P8", {"id": "P8", "contrato_id": "K2", "persona_id": "PA2", "rol": "gestor",
                                        "es_principal": False, "inactivatedon": None})]
    with pytest.raises(P5.ErrorP5) as e:
        _t(filas, monkeypatch)
    assert e.value.codigo == "S9_RECREACION_PARTICIPANTE_SIN_GEMELO"
