# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_310_mant_rt_revision_larga.py
# Ruta: tests/api/test_310_mant_rt_revision_larga.py
# Descripcion: MANT N1 de revision del tipo (A4; dictamen MANT R-B2-06 punto 3 y AJ-03; reevaluacion AJ-REE-02; decision 14),
#   oraculo de servidor. Revision del tipo (W-HIP-03/04) sobre hipotecas de 300 y 360 cuotas con la cuota 1 pagada, desde la
#   mitad del cuadro: una sola version CAMBIO_CONDICIONES nueva; la cuota pagada y las anteriores a la fecha, intactas fila a
#   fila; las cuotas desde la fecha, iguales al recalculo con la calculadora (base = capital - Σ capital previsto anterior,
#   mismo plazo y vencimientos); y el reenvio con la MISMA peticion (lo que hace el cliente tras un timeout,
#   enviarRevisionComprobando) responde 200 idempotente SIN escribir (huella global y recuentos iguales antes y despues).
#   La duracion se registra, no se asserta (depende del equipo; medicion en la evidencia, 06_revision_latencia).
# Version: 0.1.0 (F06 T3 · MANT N1 de revision del tipo, A4)
# ============================================================
from __future__ import annotations

import datetime as dt
import time
import uuid
from decimal import Decimal

import pytest

from test_289_f06_01h_alta_en_compra import huella
from test_294_f06_01h_revision_tipo import LabRev

MARCA_VERSION = "gapto.f06.hipoteca.revision.version"


def _lab(n: int) -> LabRev:
    class LabN(LabRev):
        def bloque(self, **cambios) -> dict:
            cambios.setdefault("numero_cuotas", n)
            return super().bloque(**cambios)
    return LabN()


def _filas(lab: LabRev) -> list[tuple]:
    return lab.sql("SELECT q.numero_cuota, q.fecha_vencimiento, q.capital_previsto, q.interes_previsto, q.importe_total_previsto, "
                   "q.condicion_version_id, q.prevision_id, p.estado, p.importe_esperado, p.row_version "
                   "FROM gapto.financiacion_cuotas q JOIN gapto.previsiones p ON p.id = q.prevision_id "
                   "WHERE q.financiacion_entidad_id = %s ORDER BY q.numero_cuota", (lab.f,))


def _recuentos(lab: LabRev) -> dict:
    uno = lambda sql: lab.sql(sql, (lab.f,))[0][0]  # noqa: E731
    return {
        "cuotas": uno("SELECT count(*) FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s"),
        "previsiones": uno("SELECT count(*) FROM gapto.previsiones WHERE entidad_id = %s"),
        "versiones": uno("SELECT count(*) FROM gapto.financiacion_condiciones_versiones WHERE financiacion_entidad_id = %s"),
        "cambios": uno("SELECT count(*) FROM gapto.financiacion_condiciones_versiones WHERE financiacion_entidad_id = %s "
                       "AND motivo_version = 'CAMBIO_CONDICIONES'"),
        "auditoria_cuotas": lab.sql("SELECT count(*) FROM gapto.auditoria WHERE tabla = 'financiacion_cuotas' AND registro_id IN "
                                    "(SELECT id FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s)", (lab.f,))[0][0],
    }


@pytest.mark.parametrize("n", [300, 360])
def test_revision_larga_una_version_pagadas_intactas_recalculo_y_replay_sin_escrituras(n, capsys):
    from app.hipotecas import calculadora as calc

    lab = _lab(n)
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    k = n // 2 + 1
    venc = lab.sql("SELECT fecha_vencimiento FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s "
                   "AND numero_cuota = %s", (lab.f, k))[0][0]
    desde = dt.date(venc.year, venc.month, 1)
    antes = _filas(lab)
    assert len(antes) == n and antes[0][7] == "REALIZADA"
    capital = Decimal(lab.sql("SELECT capital_original_contratado FROM gapto.financiaciones WHERE entidad_id = %s", (lab.f,))[0][0])
    cuerpo = lab.cuerpo_rev(desde=desde.isoformat(), tasa="3.5")
    t0 = time.perf_counter()
    r = lab.revisar(cuerpo)
    dur = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is False
    despues = _filas(lab)
    anteriores = [q for q in antes if q[1] < desde]
    afectadas = [q for q in despues if q[1] >= desde]
    assert len(anteriores) == k - 1 and len(afectadas) == n - k + 1
    # cuota 1 pagada y anteriores a la fecha: intactas fila a fila (capital, interes, cuota, version, prevision y su estado)
    assert despues[:k - 1] == antes[:k - 1]
    assert despues[0][7] == "REALIZADA"
    # una sola version CAMBIO_CONDICIONES nueva, la de la intencion
    vid = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), MARCA_VERSION)
    vers = lab.sql("SELECT id, motivo_version, vigente_desde FROM gapto.financiacion_condiciones_versiones "
                   "WHERE financiacion_entidad_id = %s ORDER BY vigente_desde", (lab.f,))
    assert [v[1] for v in vers] == ["ALTA", "CAMBIO_CONDICIONES"] and vers[1][0] == vid and vers[1][2] == desde
    # cuotas desde la fecha: iguales al recalculo (base = capital - Σ capital previsto anterior; mismos numeros y vencimientos)
    base = capital - sum((Decimal(q[2]) for q in anteriores), Decimal(0))
    tramo = calc.tramo_desde(base, Decimal("3.5"), [q[0] for q in afectadas], [q[1] for q in afectadas])
    assert [(q[0], Decimal(q[2]), Decimal(q[3]), Decimal(q[4]), q[5]) for q in afectadas] == [
        (q[0], c.capital, c.interes, c.cuota, vid) for q, c in zip(afectadas, tramo)]
    assert all(q[7] == "ABIERTA" and Decimal(q[8]) == Decimal(q[4]) for q in afectadas)
    assert sum((Decimal(q[2]) for q in afectadas), Decimal(0)) == base
    # reenvio con la MISMA peticion (cliente tras un timeout): idempotente y sin ninguna escritura
    rec = _recuentos(lab)
    h = huella()
    t1 = time.perf_counter()
    r2 = lab.revisar(cuerpo)
    dur_replay = time.perf_counter() - t1
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotente"] is True
    assert huella() == h
    assert _recuentos(lab) == rec
    assert rec["cambios"] == 1 and rec["versiones"] == 2
    assert _filas(lab) == despues
    with capsys.disabled():
        print(f"\n[MANT-RT] n={n} desde=c{k} revision={dur:.2f}s replay={dur_replay:.2f}s")
