# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_016_p5_dominio5.py
# Ruta: tests/migration/test_rv3_016_p5_dominio5.py
# Descripcion: RV3 / P5 v0.16.0. Corpus SINTETICO (sin PII) del dominio 5, reglas
#              financieras y versiones: CALENDARIO/VENTANA frente a RODANTE validado,
#              inicio y fin demostrados (sin createon/ultimo pago como sustitutos),
#              discriminantes gasto / transferencia / aportacion / derecho, fusion N:1
#              con versiones contiguas, renta N:1 contrato + ingreso con regla_renta_id,
#              exclusiones (contenedor, compra financiada), pendientes por fila,
#              trazabilidad, determinismo y validacion fisica 0330 (incluido EXCLUDE de
#              solapamiento) bajo RV3_IMPORT con ROLLBACK.
#   0.2.0: P5 v0.17.0 -> respuestas del propietario 2026-09-21: fusiones N:1 con solape
#          (D5-K2/K3), inicio confirmado, fin por fecha de modificacion y compras financiadas
#          decididas abiertas/cerradas (D8-K2/K3).
#   0.3.0: P5 v0.18.0 -> inicio por creacion, cobro parcial a dominio 6, cuota de prestamo sin
#          regla (calendario de la financiacion) y compra financiada cancelada.
# Versión: 0.3.0
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
_s12 = importlib.util.spec_from_file_location("t12", Path(__file__).resolve().parent / "test_rv3_012_p5_dominio10.py")
T12 = importlib.util.module_from_spec(_s12)
_s12.loader.exec_module(T12)
T8 = T12.T8
F = P5.fu
SHA = "0" * 64
G, I, CB, CC = "public.gastos", "public.ingresos", "public.cuentas_bancarias", "public.contratos"
N = "141"
DOMINIO_5 = True
TH = P5.TIPOS_HECHO_SEED


def _g(k, **kw):
    d = {"id": k, "nombre": f"REGLA {k}", "tipo_id": "TX", "prestamo_id": N, "periodicidad": "MENSUAL", "cuotas": 1,
         "fecha": "2025-01-01", "createon": "2025-02-01T10:00:00", "rango_pago": "4-7", "importe": 10.5,
         "importe_cuota": 10.5, "cuenta_id": "C1", "proveedor_id": "PT", "activo": True, "inactivatedon": N,
         "ultimo_pago_on": "2026-08-05T06:00:00", "referencia_vivienda_id": N}
    d.update(kw)
    return (G, k, d)


def _i(k, **kw):
    d = {"id": k, "concepto": f"INGRESO {k}", "tipo_id": "TX", "periodicidad": "MENSUAL", "fecha_inicio": "2025-01-01",
         "createon": "2025-02-01T10:00:00", "rango_cobro": "1-3", "importe": 550, "cuenta_id": "C1", "activo": True,
         "inactivatedon": N, "ultimo_ingreso_on": "2026-08-02T06:00:00", "contrato_alquiler": N,
         "referencia_vivienda_id": N}
    d.update(kw)
    return (I, k, d)


C2 = (CB, "C2", {"id": "C2", "anagrama": "CTA AHORRO", "banco_id": "PA", "liquidez": "5.00", "liquidez_inicial": "0.00",
                 "participacion_pct": "100.00", "activo": True})


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    for k, v in (("CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                     (CB, "C2"): ("AHORRO", "ACTIVO", True, True, False, "EUR")}),
                 ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {}),
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("CUENTA_AHORRO", (CB, "C2")), ("ISA_TIPO_HECHO_DECIDIDO", None),
                 ("DOMINIO_5_ACTIVO", True)):
        monkeypatch.setattr(P5, k, v)
    monkeypatch.setattr(P5, "CATEGORIA_POR_TIPO_V3", {**P5.CATEGORIA_POR_TIPO_V3, "TX": "SIN_CATEGORIA_TEST"})


def _t(extra=(), con=None):
    return P5.transformar(T8._b0(T12._filas(con=con, extra=(C2,) + tuple(extra))), SHA, modo_lab=True)


def _reglas(ds, co, cl):
    ids = {m["registro_destino_id"] for m in ds.filas["mapeos_importacion"].values()
           if m["tabla_destino"] == "reglas_financieras" and m["registro_origen_id"] == F.uuid_origen(co, cl)}
    return [ds.filas["reglas_financieras"][x] for x in ids]


def _ver(ds, rid):
    return sorted((v for v in ds.filas["regla_versiones"].values() if v["regla_id"] == rid),
                  key=lambda v: v["vigente_desde"])


def _uno(ds, co, cl):
    (r,) = _reglas(ds, co, cl)
    (v,) = _ver(ds, r["id"])
    return r, v


def _pend(ds, co, cl):
    return [p for p in ds.pendientes if p.get("origen") == f"{co}/{cl}" and p.get("dominio") == 5]


def _cta(k):
    return F.uuid_v3(CB, k, "cuentas", "cuenta")


@pytest.fixture(autouse=True)
def _sin_categoria(monkeypatch):
    real = P5.clasificar
    monkeypatch.setattr(P5, "clasificar", lambda ds, co, cl, f: ("NULL", None) if f.get("tipo_id") == "TX" else real(ds, co, cl, f))


def test_gasto_ordinario_calendario_ventana():
    r, v = _uno(_t([_g("GA")]), G, "GA")
    assert (v["tipo_hecho_id"], v["flujo_tesoreria_esperado"]) == (TH["GASTO"], "SALIDA")
    assert (v["cuenta_salida_esperada_id"], v["cuenta_entrada_esperada_id"]) == (_cta("C1"), None)
    assert (v["periodicidad"], v["intervalo"], v["anclaje_recurrencia"], v["fecha_modo"], v["dia_desde"], v["dia_hasta"]) \
        == ("MENSUAL", 1, "CALENDARIO", "VENTANA", 4, 7)
    assert (v["importe_modo"], v["importe_fijo"], v["vigente_desde"], v["vigente_hasta"]) == ("FIJO", Decimal("10.5"), "2025-01-01", None)
    assert v["tercero_id"] == F.uuid_v3("public.proveedores", "PT", "terceros", "tercero")
    assert (v["categoria_id"], v["presupuestable"], v["importe_referencia_lado"], v["moneda"]) == (None, True, None, "EUR")
    assert r["entidad_origen_id"] is None and r["nombre"] == "REGLA GA"


def test_entidad_origen_por_vivienda_v3():
    r, _ = _uno(_t([_g("GV", referencia_vivienda_id="V1")]), G, "GV")
    assert r["entidad_origen_id"] == F.uuid_v3("public.patrimonio", "V1", "entidades", "propiedad")


@pytest.mark.parametrize("kw", [dict(fecha="2026-08-05", createon="2025-08-05T04:00:00", ultimo_pago_on=N),
                                dict(fecha="2026-01-10", createon="2026-01-12T00:00:00", ultimo_pago_on="2026-01-09T00:00:00"),
                                dict(fecha=N)])
def test_inicio_no_demostrado_no_crea_regla(kw):
    ds = _t([_g("GI", **kw)])
    assert not _reglas(ds, G, "GI") and _pend(ds, G, "GI")[0]["S6"] in ("D5_INICIO_NO_DEMOSTRADO", "D5_INICIO_DESCONOCIDO")


def test_fin_dia_anterior_a_la_inactivacion():
    _, v = _uno(_t([_g("GF", activo=False, inactivatedon="2026-02-11T11:25:19")]), G, "GF")
    assert (v["vigente_desde"], v["vigente_hasta"]) == ("2025-01-01", "2026-02-10")


def test_fin_desconocido_o_anterior_al_inicio_pendiente():
    ds = _t([_g("GD", activo=False), _g("GE", activo=False, inactivatedon="2025-01-01T08:00:00")])
    assert not _reglas(ds, G, "GD") and _pend(ds, G, "GD")[0]["S6"] == "D5_FIN_NO_DEMOSTRADO"
    assert not _reglas(ds, G, "GE") and _pend(ds, G, "GE")[0]["S9"] == "D5_FIN_ANTERIOR_A_INICIO"


def test_activo_con_inactivatedon_contradictorio_regla_abierta():
    ds = _t([_g("GC", activo=True, inactivatedon="2025-07-08T04:00:00")])
    _, v = _uno(ds, G, "GC")
    assert v["vigente_hasta"] is None
    assert any(e.get("regla") == "D5-C1" for e in ds.ledger)


def test_rodante_solo_para_el_caso_validado(monkeypatch):
    monkeypatch.setattr(P5, "RODANTES_VALIDADOS", {(G, "GR")})
    ds = _t([_g("GR"), _g("GN")])
    _, v = _uno(ds, G, "GR")
    assert (v["anclaje_recurrencia"], v["fecha_modo"], v["dia_desde"], v["dia_hasta"]) == ("RODANTE", "ANCLA", None, None)
    _, w = _uno(ds, G, "GN")
    assert (w["anclaje_recurrencia"], w["fecha_modo"]) == ("CALENDARIO", "VENTANA")


def test_semestral_es_mensual_intervalo_6_y_anual():
    ds = _t([_i("IS", periodicidad="SEMESTRAL"), _g("GY", periodicidad="ANUAL")])
    _, v = _uno(ds, I, "IS")
    assert (v["periodicidad"], v["intervalo"], v["tipo_hecho_id"], v["flujo_tesoreria_esperado"]) == ("MENSUAL", 6, TH["INGRESO"], "ENTRADA")
    assert (v["cuenta_entrada_esperada_id"], v["cuenta_salida_esperada_id"], v["presupuestable"], v["tercero_id"]) == (_cta("C1"), None, False, None)
    assert _uno(ds, G, "GY")[1]["periodicidad"] == "ANUAL"


@pytest.mark.parametrize("rango", ["28-3", "7", "0-5", "4-32"])
def test_rango_no_representable_no_se_deforma(rango):
    ds = _t([_g("GW", rango_pago=rango)])
    assert not _reglas(ds, G, "GW") and _pend(ds, G, "GW")[0]["S4"] == "D5_RANGO_NO_REPRESENTABLE"


@pytest.mark.parametrize("imp", [0, N])
def test_importe_cero_o_desconocido_no_es_fijo(imp):
    ds = _t([_g("GZ", importe=imp, importe_cuota=imp)])
    assert not _reglas(ds, G, "GZ") and _pend(ds, G, "GZ")[0]["S6"] == "D5_IMPORTE_NO_POSITIVO"


def test_ahorro_es_transferencia_sin_gasto(monkeypatch):
    monkeypatch.setattr(P5, "TRANSFERENCIAS_AHORRO", {"GT"})
    _, v = _uno(_t([_g("GT")]), G, "GT")
    assert (v["tipo_hecho_id"], v["flujo_tesoreria_esperado"]) == (TH["TRANSFERENCIA"], "TRANSFERENCIA")
    assert (v["cuenta_salida_esperada_id"], v["cuenta_entrada_esperada_id"]) == (_cta("C1"), _cta("C2"))
    assert (v["categoria_id"], v["presupuestable"], v["importe_referencia_lado"], v["tercero_id"]) == (None, False, None, None)


def test_ahorro_hacia_la_misma_cuenta_falla(monkeypatch):
    monkeypatch.setattr(P5, "TRANSFERENCIAS_AHORRO", {"GT"})
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GT", cuenta_id="C2")])
    assert e.value.codigo == "S9_AUTOTRANSFERENCIA"


def _inyectar_inversion_y_derecho(ds):
    for eid, tabla, fila in ((F.uuid_v3("public.inversion", "INVX", "entidades", "inversion"), "inversiones", {}),
                             (F.uuid_v3(I, "II", "entidades", "derecho"), "derechos_obligaciones_financieras", {})):
        ds.filas["entidades"][eid] = {"id": eid}
        ds.filas[tabla][eid] = {"entidad_id": eid, **fila}


def _d5(filas, monkeypatch):
    monkeypatch.setattr(P5, "DOMINIO_5_ACTIVO", False)
    b0 = T8._b0(T12._filas(extra=(C2,) + tuple(filas)))
    ds = P5.transformar(b0, SHA, modo_lab=True)
    _inyectar_inversion_y_derecho(ds)
    fuente = F.fuente_b0(b0)
    ds.reglas = P5.dominio_5_reglas(ds, fuente, F.contexto_de(fuente))
    return ds


FUS = {"regla_id": "e6f9b86e-a62e-523b-8490-99a4804df761", "inversion": "INVX", "filas": ["GM1", "GM2"],
       "co": G, "tipo": "APORTACION_INVERSION"}


def test_aportacion_fusion_n1_versiones_contiguas(monkeypatch):
    monkeypatch.setattr(P5, "FUSION_MEDIOLANUM", FUS)
    ds = _d5([_g("GM1", importe=178.95, importe_cuota=178.95, rango_pago="12-15", activo=False,
                 inactivatedon="2026-02-11T11:25:19"),
              _g("GM2", importe=184.13, importe_cuota=184.13, rango_pago="8-11", fecha="2026-02-11",
                 createon="2026-02-11T11:24:58")], monkeypatch)
    (r,) = _reglas(ds, G, "GM1")
    assert _reglas(ds, G, "GM2") == [r] and r["id"] == FUS["regla_id"]
    assert r["entidad_origen_id"] == F.uuid_v3("public.inversion", "INVX", "entidades", "inversion")
    a, b = _ver(ds, r["id"])
    assert [(x["importe_fijo"], x["vigente_desde"], x["vigente_hasta"]) for x in (a, b)] == \
        [(Decimal("178.95"), "2025-01-01", "2026-02-10"), (Decimal("184.13"), "2026-02-11", None)]
    for x in (a, b):
        assert (x["tipo_hecho_id"], x["flujo_tesoreria_esperado"], x["cuenta_entrada_esperada_id"]) == (TH["APORTACION_INVERSION"], "SALIDA", None)
        assert (x["categoria_id"], x["presupuestable"]) == (None, False)
    assert len(ds.filas["reglas_financieras"]) == 1 + 0 * len(a)


def test_fusion_con_hueco_o_incompatible_falla(monkeypatch):
    monkeypatch.setattr(P5, "FUSION_MEDIOLANUM", FUS)
    with pytest.raises(P5.ErrorP5) as e:
        _d5([_g("GM1", activo=False, inactivatedon="2026-02-01T00:00:00"),
             _g("GM2", fecha="2026-02-11", createon="2026-02-11T00:00:00")], monkeypatch)
    assert e.value.codigo == "S9_VERSIONES_NO_CONTIGUAS"
    with pytest.raises(P5.ErrorP5) as e:
        _d5([_g("GM1", activo=False, inactivatedon="2026-02-11T00:00:00"),
             _g("GM2", fecha="2026-02-11", createon="2026-02-11T00:00:00", cuenta_id="C2")], monkeypatch)
    assert e.value.codigo == "S9_FUSION_INCOMPATIBLE"


def test_isa_pendiente_s1_sin_decision(monkeypatch):
    monkeypatch.setattr(P5, "REGLA_DERECHO_ISA", {(I, "II"): (I, "II")})
    ds = _d5([_i("II", importe=270.3)], monkeypatch)
    assert not _reglas(ds, I, "II") and _pend(ds, I, "II")[0]["S1"] == "D5_ISA_TIPO_HECHO"


@pytest.mark.parametrize("tipo", ["REEMBOLSO", "GENERACION_DERECHO_OBLIGACION"])
def test_isa_reduce_derecho_sin_ingreso(monkeypatch, tipo):
    monkeypatch.setattr(P5, "REGLA_DERECHO_ISA", {(I, "II"): (I, "II")})
    monkeypatch.setattr(P5, "ISA_TIPO_HECHO_DECIDIDO", tipo)
    ds = _d5([_i("II", importe=270.3)], monkeypatch)
    r, v = _uno(ds, I, "II")
    assert r["entidad_origen_id"] == F.uuid_v3(I, "II", "entidades", "derecho")
    assert (v["tipo_hecho_id"], v["flujo_tesoreria_esperado"], v["cuenta_entrada_esperada_id"]) == (TH[tipo], "ENTRADA", _cta("C1"))
    assert v["tipo_hecho_id"] != TH["INGRESO"] and (v["categoria_id"], v["presupuestable"]) == (None, False)


def test_isa_como_ingreso_rechazado(monkeypatch):
    monkeypatch.setattr(P5, "REGLA_DERECHO_ISA", {(I, "II"): (I, "II")})
    monkeypatch.setattr(P5, "ISA_TIPO_HECHO_DECIDIDO", "INGRESO")
    with pytest.raises(P5.ErrorP5) as e:
        _d5([_i("II", importe=270.3)], monkeypatch)
    assert e.value.codigo == "S4_ISA_TIPO_HECHO"


def test_renta_n1_contrato_mas_ingreso(monkeypatch):
    monkeypatch.setattr(P5, "FECHA_INICIO_CONTRATO_VALIDADA", {"K1": "2025-03-01"})
    ds = _t([_i("IR", contrato_alquiler="K1", fecha_inicio="2024-09-01")], con={"renta_mensual": "550.00"})
    (r,) = _reglas(ds, I, "IR")
    assert _reglas(ds, CC, "K1") == [r] and len(ds.filas["reglas_financieras"]) == 1
    eid = F.uuid_v3(CC, "K1", "entidades", "contrato")
    assert r["entidad_origen_id"] == eid and ds.filas["contratos"][eid]["regla_renta_id"] == r["id"]
    (v,) = _ver(ds, r["id"])
    assert (v["vigente_desde"], v["importe_fijo"], v["tipo_hecho_id"], v["tercero_id"]) == ("2025-03-01", Decimal("550"), TH["INGRESO"], None)
    assert {m["tipo_mapping"] for m in ds.filas["mapeos_importacion"].values() if m["registro_destino_id"] == r["id"]} == {"FUSIONADO"}
    assert not ds.filas["contrato_revision_renta_versiones"] or all(
        "importe" not in k for x in ds.filas["contrato_revision_renta_versiones"].values() for k in x)


def test_renta_incompatible_con_contrato_falla():
    with pytest.raises(P5.ErrorP5) as e:
        _t([_i("IR", contrato_alquiler="K1", importe=600)], con={"renta_mensual": "550.00"})
    assert e.value.codigo == "S9_RENTA_INCOMPATIBLE"


def test_exclusiones_y_pendientes_de_familia(monkeypatch):
    monkeypatch.setattr(P5, "CONTENEDORES_PRESUPUESTARIOS", {"GB"})
    ds = _t([_g("GB"), _g("GL", prestamo_id="P1"), _g("GP3", cuotas=3, importe_cuota=10.5)])
    assert not _reglas(ds, G, "GB") and f"{G}/GB" in ds.reglas["disposicion"]["EXCLUIDA_D11"]
    assert not _reglas(ds, G, "G1") and f"{G}/G1" in ds.reglas["disposicion"]["EXCLUIDA_D8"]
    assert not _pend(ds, G, "GL") and not _reglas(ds, G, "GL") and f"{G}/GL" in ds.reglas["disposicion"]["EXCLUIDA_D8"]
    assert _pend(ds, G, "GP3")[0]["S20"] == "D5_GASTO_A_PLAZOS_NATURALEZA" and not _reglas(ds, G, "GP3")
    assert not _pend(ds, G, "G1") and not _pend(ds, G, "GB")


def test_cuota_de_prestamo_sin_financiacion_falla():
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GL", prestamo_id="PX")])
    assert e.value.codigo == "S8_HUERFANO"


def test_inicio_por_creacion_decidido(monkeypatch):
    kw = dict(periodicidad="ANUAL", fecha="2026-08-05", createon="2025-08-05T04:49:57", ultimo_pago_on="2025-08-05T04:50:54")
    assert _pend(_t([_g("GC2", **kw)]), G, "GC2")[0]["S6"] == "D5_INICIO_NO_DEMOSTRADO"
    monkeypatch.setattr(P5, "INICIO_POR_CREACION", {(G, "GC2"), (G, "GC3")})
    ds = _t([_g("GC2", **kw), _g("GC3", **dict(kw, ultimo_pago_on="2025-08-01T00:00:00"))])
    _, v = _uno(ds, G, "GC2")
    assert (v["vigente_desde"], v["periodicidad"]) == ("2025-08-05", "ANUAL")
    assert _pend(ds, G, "GC3")[0]["S9"] == "D5_INICIO_CREACION_INVALIDO"


def test_cobro_parcial_no_es_regla(monkeypatch):
    monkeypatch.setattr(P5, "COBRO_PARCIAL_NO_REGLA", {(I, "IP")})
    ds = _t([_i("IP", importe=862.43)])
    assert not _reglas(ds, I, "IP") and not _pend(ds, I, "IP") and f"{I}/IP" in ds.reglas["disposicion"]["EXCLUIDA_D6"]


def test_compra_financiada_cancelada(monkeypatch):
    monkeypatch.setattr(P5, "COMPRA_FINANCIADA_DECIDIDA", {"GX"})
    monkeypatch.setattr(P5, "COMPRA_FINANCIADA_CANCELADA", {"GX"})
    kw = dict(PLAZOS_BASE, activo=False, inactivatedon="2026-08-10T00:00:00")
    ds = _t([_g("GX", **kw)])
    f = ds.filas["financiaciones"][F.uuid_v3(G, "GX", "entidades", "financiacion")]
    assert (f["estado"], f["motivo_cierre"], f["saldo_principal_apertura"], f["fecha_cierre_real"]) == ("CERRADA", "CANCELADA", Decimal("0"), None)
    assert F.uuid_origen(G, "GX") in ds.filas["registros_origen_importacion"] and not _reglas(ds, G, "GX")
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GX", **dict(kw, activo=True))])
    assert e.value.codigo == "S9_CANCELACION_INCOHERENTE"


def test_disposicion_exclusiva_y_exhaustiva(monkeypatch):
    monkeypatch.setattr(P5, "CONTENEDORES_PRESUPUESTARIOS", {"GB"})
    ds = _t([_g("GB"), _g("GA"), _i("IR", contrato_alquiler="K1")], con={"renta_mensual": "550.00"})
    d = ds.reglas["disposicion"]
    n = sum(len(d[k]) for k in ("EXCLUIDA_D11", "EXCLUIDA_D8", "PENDIENTE", "CREADA", "FUSIONADA"))
    assert n == ds.reglas["resumen"]["recurrentes_v3"] and ds.reglas["resumen"]["reglas"] == len(d["CREADA"]) + len(d["FUSIONADA"])


def test_excepciones_no_se_fabrican():
    ds = _t([_g("GO", omitido_count=2, omitido_este_mes=True, ultimo_omitido_on="2026-05-03T00:00:00")])
    assert not ds.filas["regla_excepciones"] and _uno(ds, G, "GO")


def test_trazabilidad_y_determinismo():
    a, b = _t([_g("GA"), _i("IB")]), _t([_g("GA"), _i("IB")])
    assert a.hash() == b.hash()
    dest = {(m["tabla_destino"], m["registro_destino_id"]) for m in a.filas["mapeos_importacion"].values()}
    for t in ("reglas_financieras", "regla_versiones"):
        assert a.filas[t] and all((t, x) in dest for x in a.filas[t])


FZ = [{"co": G, "filas": ["GP1", "GP2"]}]
PRED = dict(activo=False, inactivatedon="2026-06-06T06:36:26", ultimo_pago_on="2025-09-18T00:00:00")
SUCE = dict(fecha="2026-06-01", createon="2026-06-01T03:42:59", importe=12.0, importe_cuota=12.0)


def test_fusion_propietario_solape_trunca_al_inicio_del_sucesor(monkeypatch):
    monkeypatch.setattr(P5, "FUSIONES_PROPIETARIO", FZ)
    ds = _t([_g("GP1", **PRED), _g("GP2", **SUCE)])
    (r,) = _reglas(ds, G, "GP1")
    assert _reglas(ds, G, "GP2") == [r] and r["id"] == F.uuid_v3(G, "GP1", "reglas_financieras", "regla")
    a, b = _ver(ds, r["id"])
    assert (a["vigente_hasta"], b["vigente_desde"], b["vigente_hasta"], b["importe_fijo"]) == ("2026-05-31", "2026-06-01", None, Decimal("12.0"))
    assert any(e.get("regla") == "D5-K2" and e["hasta_evidencia"] == "2026-06-05" for e in ds.ledger)
    assert r["nombre"] == "REGLA GP2"


def test_fusion_propietario_hueco_o_firma_distinta_falla(monkeypatch):
    monkeypatch.setattr(P5, "FUSIONES_PROPIETARIO", FZ)
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GP1", **dict(PRED, inactivatedon="2026-03-01T00:00:00")), _g("GP2", **SUCE)])
    assert e.value.codigo == "S9_VERSIONES_NO_CONTIGUAS"
    with pytest.raises(P5.ErrorP5) as e:
        _t([_g("GP1", **PRED), _g("GP2", referencia_vivienda_id="V1", **SUCE)])
    assert e.value.codigo == "S9_FUSION_INCOMPATIBLE"


def test_fusion_con_miembro_pendiente_no_crea_nada(monkeypatch):
    monkeypatch.setattr(P5, "FUSIONES_PROPIETARIO", FZ)
    ds = _t([_g("GP1", **dict(PRED, fecha="2026-06-23", createon="2025-06-23T09:45:24")), _g("GP2", **SUCE)])
    assert not _reglas(ds, G, "GP1") and not _reglas(ds, G, "GP2")
    assert _pend(ds, G, "GP1")[0]["S6"] == _pend(ds, G, "GP2")[0]["S6"] == "D5_INICIO_NO_DEMOSTRADO"


def test_inicio_confirmado_por_el_propietario(monkeypatch):
    kw = dict(fecha="2026-03-13", createon="2026-03-12T12:16:11")
    assert _pend(_t([_g("GK", **kw)]), G, "GK")
    monkeypatch.setattr(P5, "INICIO_CONFIRMADO", {(G, "GK")})
    _, v = _uno(_t([_g("GK", **kw)]), G, "GK")
    assert v["vigente_desde"] == "2026-03-13"


def test_fin_por_fecha_de_modificacion_decidida(monkeypatch):
    kw = dict(activo=False, modifiedon="2025-10-02T16:35:28.115889")
    assert _pend(_t([_g("GM", **kw)]), G, "GM")[0]["S6"] == "D5_FIN_NO_DEMOSTRADO"
    monkeypatch.setattr(P5, "FIN_POR_MODIFICACION", {(G, "GM"), (G, "GN")})
    ds = _t([_g("GM", **kw), _g("GN", activo=False, modifiedon="2024-12-01T00:00:00")])
    assert _uno(ds, G, "GM")[1]["vigente_hasta"] == "2025-10-02"
    assert _pend(ds, G, "GN")[0]["S9"] == "D5_FIN_MODIFICACION_INVALIDO"


PLAZOS_BASE = dict(tipo_id="TX", cuotas=3, cuotas_pagadas=1, cuotas_restantes=2, importe_cuota=10.5, importe=10.5,
                   total=31.5, importe_pendiente=21.0, activo=True)
PLAZOS = dict(tipo_id="TX", cuotas=3, cuotas_pagadas=1, cuotas_restantes=2, importe_cuota=10.5, importe=10.5,
              total=31.5, importe_pendiente=21.0, activo=True)


def _fin(ds, k):
    return ds.filas["financiaciones"].get(F.uuid_v3(G, k, "entidades", "financiacion"))


def test_compra_financiada_decidida_abierta_y_cerrada(monkeypatch):
    monkeypatch.setattr(P5, "COMPRA_FINANCIADA_DECIDIDA", {"GQ", "GQC"})
    ds = _t([_g("GQ", **PLAZOS), _g("GQC", **dict(PLAZOS, cuotas_pagadas=3, cuotas_restantes=0, importe_pendiente=0,
                                                   activo=False, inactivatedon="2026-01-01T00:00:00"))])
    f = _fin(ds, "GQ")
    assert (f["tipo_financiacion"], f["estado"], f["motivo_cierre"], f["saldo_principal_apertura"], f["capital_original_contratado"]) \
        == ("COMPRA_FINANCIADA", "ACTIVA", None, Decimal("21.0"), Decimal("31.5"))
    assert f["financiador_actor_id"] is None and f["fecha_inicio_seguimiento"] == P5.FECHA_INICIO_LEDGER
    c = _fin(ds, "GQC")
    assert (c["estado"], c["motivo_cierre"], c["saldo_principal_apertura"]) == ("CERRADA", "LIQUIDADA", Decimal("0"))
    assert not _reglas(ds, G, "GQ") and f"{G}/GQ" in ds.reglas["disposicion"]["EXCLUIDA_D8"]
    assert not [x for x in ds.filas["financiacion_cuotas"].values() if x["financiacion_entidad_id"] == f["entidad_id"]]


@pytest.mark.parametrize("kw", [dict(activo=False, inactivatedon="2026-08-10T00:00:00"), dict(importe_pendiente=20.0),
                                dict(cuotas_pagadas=2)])
def test_compra_financiada_abierta_incoherente_no_se_crea(monkeypatch, kw):
    monkeypatch.setattr(P5, "COMPRA_FINANCIADA_DECIDIDA", {"GQ"})
    ds = _t([_g("GQ", **dict(PLAZOS, **kw))])
    assert _fin(ds, "GQ") is None and not _reglas(ds, G, "GQ")
    assert any(p.get("S20") == "D8_COMPRA_FINANCIADA_ABIERTA_INCOHERENTE" for p in ds.pendientes)


def _fisico_ds(monkeypatch):
    monkeypatch.setattr(P5, "TRANSFERENCIAS_AHORRO", {"GT"})
    monkeypatch.setattr(P5, "RODANTES_VALIDADOS", {(G, "GR")})
    monkeypatch.setattr(P5, "FUSIONES_PROPIETARIO", FZ)
    monkeypatch.setattr(P5, "COMPRA_FINANCIADA_DECIDIDA", {"GQ"})
    return _t([_g("GA", referencia_vivienda_id="V1"), _g("GT"), _g("GR"), _i("IS", periodicidad="SEMESTRAL"),
               _g("GF", activo=False, inactivatedon="2026-02-11T11:25:19"), _g("GP1", **PRED), _g("GP2", **SUCE),
               _g("GQ", **PLAZOS), _i("IR", contrato_alquiler="K1")], con={"renta_mensual": "550.00"})


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback(monkeypatch):
    ds = _fisico_ds(monkeypatch)
    res = P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
    assert (res["reglas_financieras"], res["regla_versiones"], res["regla_excepciones"]) == (7, 8, 0)
    assert res["financiaciones"] == 4


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_solapamiento_de_versiones_rechazado(monkeypatch):
    import psycopg
    ds = _fisico_ds(monkeypatch)
    rid = _reglas(ds, G, "GA")[0]["id"]
    (v,) = _ver(ds, rid)
    otra = dict(v, id=F.uuid_v3(G, "GA", "regla_versiones", "solape"), vigente_desde="2026-01-01")
    ds.filas["regla_versiones"][otra["id"]] = otra
    with pytest.raises(psycopg.errors.ExclusionViolation):
        P5.validar_fisico(ds, os.environ["GAPTO_RV3_IMPORT_URL"])
