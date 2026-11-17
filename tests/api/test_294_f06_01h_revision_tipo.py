# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_294_f06_01h_revision_tipo.py
# Ruta: tests/api/test_294_f06_01h_revision_tipo.py
# Descripcion: W-HIP-03/04 · revision del tipo con fecha y recalculo hacia delante por HTTP como gapto_runtime con
#   RLS (F06-01H; contrato v0.4 §3.5; Q-H-11; mandato T3-F06 bloque 2 v1.1 §2.4 y §11.1). Oraculos: O-H4 (12
#   cuotas de O-H1 y despues 2,95 % en 348: pendiente 156.372,35, cuota 669,15, Σ intereses 76.492,02, 348 cuotas
#   identicas a caso4 de oraculos.json, cuota a cuota), O-H19 (cuotas anteriores VENCIDAS sin pagar: siguen
#   ABIERTAS con su importe; base = P - Σ capital previsto anterior), O-H9 (revision desde antes de una cuota
#   pagada: REVISION_SOBRE_CUOTA_PAGADA), O-H12 (periodicidad distinta: CONDICIONES_INCOMPLETAS /
#   PERIODICIDAD_NO_SOPORTADA; version vigente intacta), O-H20 (auditoria por cuota con datos_antes completos; el
#   cuadro anterior se reconstruye desde la auditoria y coincide con caso1; version anterior intacta; M-H-34/35),
#   O-H24 (replay idempotente; misma intencion con otra tasa o fecha: IDENTIDAD_REUTILIZADA), O-H25 (rechazos y
#   defecto CUADRO_NO_CUADRA inyectado tras las escrituras: estado identico). I3: ajustar_importe_cuota_hipoteca
#   rechaza la prevision con regla, la no ABIERTA y la que no es de una cuota de esa financiacion (servicio).
#   Fechas fijas (hoy del laboratorio 2026-10-10); orden explicito.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 7)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 11): test_o_h9_cuota_pagada_precede_a_version_desfasada (IC-01 sin
#   concurrencia, contrato §6; revision.py v0.2.0; mata M-H-44).
# ============================================================
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

import f05_06_m5_helpers as m5
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from test_288_f06_01h_cuadro_y_lectura import _csv
from test_289_f06_01h_alta_en_compra import huella
from test_293_f06_01h_pago_cuota import LabPago

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
DESDE = "2027-04-01"            # primera afectada: c13 (2027-04-20)
CAMPOS_CUOTA = {"id", "numero_cuota", "fecha_vencimiento", "capital_previsto", "interes_previsto",
                "comisiones_previstas", "importe_total_previsto", "condicion_version_id", "prevision_id"}


class LabRev(LabPago):
    def cuerpo_rev(self, *, intencion=None, desde=DESDE, tasa="2.95", version=None, **extra) -> dict:
        hip = self.hipoteca()
        return {"intencion_id": str(intencion or uuid.uuid4()),
                "row_version_esperada": hip["row_version"] if version is None else version,
                "vigente_desde": desde, "tasa_anual": tasa, **extra}

    def revisar(self, cuerpo: dict, financiacion=None):
        return self.cli.post(f"/v1/hipotecas/{financiacion or self.f}/revision", json=cuerpo, headers=h.AUTH)

    def cuotas(self) -> list[tuple]:
        return self.sql("SELECT q.numero_cuota, q.importe_total_previsto, q.interes_previsto, q.capital_previsto, "
                        "q.condicion_version_id, p.estado, p.importe_esperado, p.motivo_ajuste, p.row_version "
                        "FROM gapto.financiacion_cuotas q JOIN gapto.previsiones p ON p.id = q.prevision_id "
                        "WHERE q.financiacion_entidad_id = %s ORDER BY q.numero_cuota", (self.f,))

    def versiones(self) -> list[tuple]:
        return self.sql("SELECT id, motivo_version, vigente_desde::text, vigente_hasta::text, tasa_anual_pct::text, "
                        "importe_cuota_referencia::text, numero_cuotas_referencia, tipo_interes "
                        "FROM gapto.financiacion_condiciones_versiones WHERE financiacion_entidad_id = %s "
                        "ORDER BY vigente_desde", (self.f,))


@pytest.fixture()
def lab():
    return LabRev()


def _rechazo(r, status, codigo, motivo=None):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text
    if motivo is not None:
        assert r.json()["motivo"] == motivo, r.text


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


# ================================================================== O-H4 + O-H19
def test_o_h4_o_h19_revision_tras_12_cuotas_al_2_95(lab):
    alta_version = lab.versiones()[0][0]
    rv = lab.hipoteca()["row_version"]
    antes = lab.cuotas()
    cuerpo = lab.cuerpo_rev()
    r = lab.revisar(cuerpo)
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is False and r.json()["hipoteca"]["row_version"] == rv + 1
    despues = lab.cuotas()
    assert len(despues) == 360
    # O-H19: c1..c12 (las seis primeras VENCIDAS sin pagar el 2026-10-10) intactas y ABIERTAS
    assert despues[:12] == antes[:12]
    assert all(q[5] == "ABIERTA" for q in despues[:12])
    estados = [c["estado"] for c in r.json()["hipoteca"]["cuotas"][:12]]
    assert estados[:6] == ["VENCIDA"] * 6 and estados[6:] == ["PENDIENTE"] * 6
    caso1 = _csv("caso1_frances_160000_2.5_360.csv")
    assert [(_d(q[1]), _d(q[2]), _d(q[3])) for q in despues[:12]] == [
        (_d(f["cuota"]), _d(f["interes"]), _d(f["capital"])) for f in caso1[:12]]
    base = Decimal("160000.00") - sum((_d(q[3]) for q in despues[:12]), Decimal(0))
    # O-H4: base 156.372,35; 348 cuotas identicas al CSV, cuota a cuota
    assert base == Decimal("156372.35")
    caso4 = _csv("caso4_revision_2.95_348.csv")
    assert len(caso4) == 348
    assert [(q[0], _d(q[1]), _d(q[2]), _d(q[3])) for q in despues[12:]] == [
        (int(f["n"]), _d(f["cuota"]), _d(f["interes"]), _d(f["capital"])) for f in caso4]
    assert sum((_d(q[2]) for q in despues[12:]), Decimal(0)) == Decimal("76492.02")
    assert sum((_d(q[3]) for q in despues[12:]), Decimal(0)) == base
    # version nueva, cierre de la anterior, cuotas afectadas a la nueva y previsiones ajustadas (M-H-16, M-H-17)
    v = lab.versiones()
    vid = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), "gapto.f06.hipoteca.revision.version")
    assert v == [(alta_version, "ALTA", "2026-03-20", "2027-03-31", "2.500000", "632.1900", 360, "FIJO"),
                 (vid, "CAMBIO_CONDICIONES", DESDE, None, "2.950000", "669.1500", 348, "FIJO")]
    assert all(q[4] == vid for q in despues[12:]) and all(q[4] == alta_version for q in despues[:12])
    assert all(_d(q[6]) == _d(q[1]) and q[7] and q[8] == a[8] + 1 for q, a in zip(despues[12:], antes[12:]))


def test_o_h9_revision_sobre_cuota_pagada(lab):
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    antes = huella()
    _rechazo(lab.revisar(lab.cuerpo_rev(desde="2026-03-21")), 409, "REVISION_SOBRE_CUOTA_PAGADA")
    assert huella() == antes
    # desde despues de la pagada: admitida (la pagada no se toca)
    pagada = lab.cuotas()[0]
    r = lab.revisar(lab.cuerpo_rev(desde="2026-04-21"))
    assert r.status_code == 200, r.text
    assert lab.cuotas()[0] == pagada


def test_o_h9_cuota_pagada_precede_a_version_desfasada(lab):
    """IC-01 sin concurrencia (contrato §6; revision.py v0.2.0; mata M-H-44): revision preparada con la version
    anterior al pago de c1. Si afecta a c1 -> REVISION_SOBRE_CUOTA_PAGADA; si no -> VERSION_DESFASADA; sin escribir."""
    vieja = lab.hipoteca()["row_version"]
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    antes = huella()
    _rechazo(lab.revisar(lab.cuerpo_rev(desde="2026-03-21", version=vieja)), 409, "REVISION_SOBRE_CUOTA_PAGADA")
    _rechazo(lab.revisar(lab.cuerpo_rev(desde="2026-04-21", version=vieja)), 409, "VERSION_DESFASADA")
    # con desfase y sin cuotas afectadas, VERSION_DESFASADA precede a SIN_CUOTAS_FUTURAS
    _rechazo(lab.revisar(lab.cuerpo_rev(desde="2056-03-21", version=vieja)), 409, "VERSION_DESFASADA")
    assert huella() == antes


def test_o_h12_periodicidad_distinta(lab):
    antes = huella()
    for p in ("ANUAL", "SEMANAL"):
        _rechazo(lab.revisar(lab.cuerpo_rev(periodicidad=p)), 422, "CONDICIONES_INCOMPLETAS",
                 "PERIODICIDAD_NO_SOPORTADA")
    assert huella() == antes
    assert [x[1:4] for x in lab.versiones()] == [("ALTA", "2026-03-20", None)]


# ================================================================== O-H20 (M-H-34, M-H-35)
def test_o_h20_auditoria_por_cuota_y_reconstruccion(lab):
    alta_version = lab.versiones()[0][0]
    cuerpo = lab.cuerpo_rev()
    assert lab.revisar(cuerpo).status_code == 200
    filas = lab.sql("SELECT registro_id, datos_antes::text, datos_despues::text FROM gapto.auditoria WHERE "
                    "tabla = 'financiacion_cuotas' AND accion = 'ACTUALIZAR' AND request_id = %s",
                    (cuerpo["intencion_id"],))
    assert len(filas) == 348
    antes = sorted((json.loads(a) for _, a, _ in filas), key=lambda x: x["numero_cuota"])
    despues = {json.loads(d)["numero_cuota"]: json.loads(d) for _, _, d in filas}
    assert all(CAMPOS_CUOTA <= set(a) and CAMPOS_CUOTA <= set(despues[a["numero_cuota"]]) for a in antes)
    assert all(a["condicion_version_id"] == str(alta_version) for a in antes)
    assert {d["condicion_version_id"] for d in despues.values()} != {str(alta_version)}
    caso1 = _csv("caso1_frances_160000_2.5_360.csv")[12:]
    assert [(a["numero_cuota"], _d(a["importe_total_previsto"]), _d(a["interes_previsto"]),
             _d(a["capital_previsto"])) for a in antes] == [
        (int(f["n"]), _d(f["cuota"]), _d(f["interes"]), _d(f["capital"])) for f in caso1]
    assert lab.versiones()[0][4:7] == ("2.500000", "632.1900", 360)


# ================================================================== O-H24
def test_o_h24_replay_y_misma_intencion_con_otro_contenido(lab):
    cuerpo = lab.cuerpo_rev()
    assert lab.revisar(cuerpo).status_code == 200
    antes = huella()
    r = lab.revisar(cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert huella() == antes
    version = lab.hipoteca()["row_version"]
    _rechazo(lab.revisar({**cuerpo, "tasa_anual": "3.10", "row_version_esperada": version}), 409, REUTILIZADA)
    _rechazo(lab.revisar({**cuerpo, "vigente_desde": "2027-05-01", "row_version_esperada": version}), 409,
             REUTILIZADA)
    assert huella() == antes


# ================================================================== O-H25
@pytest.mark.parametrize("caso, status, codigo, motivo", [
    ("version", 409, "VERSION_DESFASADA", None),
    ("fecha_igual_alta", 422, "FECHA_REVISION_INCOHERENTE", None),
    ("sin_cuotas", 409, "SIN_CUOTAS_FUTURAS", None),
    ("tasa", 422, "CONDICIONES_INCOMPLETAS", "VALORES_FUERA_DE_RANGO"),
    ("tipo", 422, "CONDICIONES_INCOMPLETAS", "VALORES_FUERA_DE_RANGO"),
    ("inexistente", 404, "AGREGADO_NO_ENCONTRADO", None),
])
def test_o_h25_rechazos_sin_escrituras(lab, caso, status, codigo, motivo):
    financiacion = None
    if caso == "version":
        cuerpo = lab.cuerpo_rev(version=99)
    elif caso == "fecha_igual_alta":
        cuerpo = lab.cuerpo_rev(desde=c2.ESCRITURA)
    elif caso == "sin_cuotas":
        cuerpo = lab.cuerpo_rev(desde="2056-03-21")
    elif caso == "tasa":
        cuerpo = lab.cuerpo_rev(tasa="30.0001")
    elif caso == "tipo":
        cuerpo = lab.cuerpo_rev(tipo_interes="MIXTO")
    else:
        cuerpo, financiacion = lab.cuerpo_rev(), uuid.uuid4()
    antes = huella()
    _rechazo(lab.revisar(cuerpo, financiacion), status, codigo, motivo)
    assert huella() == antes


def test_o_h25_revision_anterior_a_las_condiciones_vigentes(lab):
    assert lab.revisar(lab.cuerpo_rev()).status_code == 200
    antes = huella()
    _rechazo(lab.revisar(lab.cuerpo_rev(desde="2027-03-01")), 422, "FECHA_REVISION_INCOHERENTE")
    _rechazo(lab.revisar(lab.cuerpo_rev(desde=DESDE)), 422, "FECHA_REVISION_INCOHERENTE")
    assert huella() == antes


def test_o_h25_otro_owner_y_legacy(lab):
    otro = LabRev()
    antes = huella()
    r = otro.cli.post(f"/v1/hipotecas/{lab.f}/revision", json=lab.cuerpo_rev(), headers=h.AUTH)
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")
    assert huella() == antes
    c2.como_owner(lab.owner, "UPDATE gapto.financiaciones SET saldo_principal_apertura = NULL, "
                             "fecha_inicio_seguimiento = NULL WHERE entidad_id = %s", (lab.f,))
    antes = huella()
    _rechazo(lab.revisar(lab.cuerpo_rev()), 409, "SALDO_PRINCIPAL_INDETERMINADO")
    assert huella() == antes


def test_o_h25_cuadro_no_cuadra_tras_escribir_hace_rollback(lab, monkeypatch):
    from app.hipotecas import calculadora as calc
    from app.hipotecas import revision

    def defecto(*_a, **_k):
        raise calc.CuadroNoCuadra("INYECTADO_TRAS_ESCRIBIR")
    cuerpo = lab.cuerpo_rev()
    monkeypatch.setattr(revision.lecturas, "leer", defecto)       # ultima llamada de revisar(), tras escribir
    antes = huella()
    r = lab.revisar(cuerpo)
    assert r.status_code == 500 and r.json()["codigo"] == "VIOLACION_INVARIANTE_FISICA", r.text
    assert huella() == antes


# ================================================================== I3 · ajustar_importe_cuota_hipoteca (servicio)
def _ajustar(lab, pid, *, financiacion=None, importe="700.00"):
    from app.services.previsiones_service import PrevisionesService
    rv = lab.sql("SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]
    return PrevisionesService(c2.unidad()).ajustar_importe_cuota_hipoteca(
        c2.ctx(lab.owner), prevision_id=pid, financiacion_id=financiacion or lab.f, importe_esperado=Decimal(importe),
        row_version_esperada=rv, motivo_ajuste="prueba")


def _incompatible(lab, pid, motivo, **kw):
    from app.core.errores import CodigoError, ErrorMotor
    antes = huella()
    with pytest.raises(ErrorMotor) as exc:
        _ajustar(lab, pid, **kw)
    assert exc.value.codigo == CodigoError.ESTADO_PREVISION_INCOMPATIBLE
    assert exc.value.contexto_extra == {"motivo": motivo}
    assert huella() == antes


def test_i3_ajuste_de_una_cuota_abierta(lab):
    pid = uuid.uuid5(lab.f, "gapto.f06.hipoteca.prevision:2")
    rv = lab.sql("SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]
    res = _ajustar(lab, pid)
    assert res.row_version == rv + 1 and res.importe_esperado == Decimal("700.00")
    assert lab.sql("SELECT importe_esperado::text, motivo_ajuste FROM gapto.previsiones WHERE id = %s",
                   (pid,)) == [("700.0000", "prueba")]


def test_i3_rechaza_la_prevision_no_abierta(lab):
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    _incompatible(lab, uuid.uuid5(lab.f, "gapto.f06.hipoteca.prevision:1"), "PREVISION_NO_ABIERTA")


def test_i3_rechaza_la_prevision_con_regla(lab):
    _, cabeza = m5.rodante(lab.owner)
    _incompatible(lab, cabeza, "PREVISION_CON_REGLA")


def test_i3_rechaza_la_prevision_que_no_es_de_una_cuota_de_esa_financiacion(lab):
    manual = m5.prevision(lab.owner, "Manual ajena", importe="10.00")
    _incompatible(lab, manual, "PREVISION_NO_ES_DE_CUOTA")
    _incompatible(lab, uuid.uuid5(lab.f, "gapto.f06.hipoteca.prevision:2"), "PREVISION_NO_ES_DE_CUOTA",
                  financiacion=uuid.uuid4())
