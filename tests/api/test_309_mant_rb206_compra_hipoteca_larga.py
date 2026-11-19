# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_309_mant_rb206_compra_hipoteca_larga.py
# Ruta: tests/api/test_309_mant_rb206_compra_hipoteca_larga.py
# Descripcion: MANT N1 R-B2-06 (AJ-01), oraculo de servidor. La compra con hipoteca de 300 y 360 cuotas (el caso real de 25-30
#   anos) se guarda entera y su replay con la MISMA peticion (lo que hace el cliente tras un timeout, enviarCompraComprobando)
#   responde 200 idempotente SIN escribir: exactamente una financiacion, N cuotas y N previsiones de cuota, un unico Hd y una
#   unica compra H0 por intencion; ninguna fila duplicada. La duracion se registra (no se asserta: depende del equipo; la
#   medicion del MANT esta en la evidencia: G2 de 0354 al COMMIT ~35 ms por cuota, STOP_MANT_RB206_B).
# Version: 0.1.0 (F06 T3-F06 · MANT N1 R-B2-06 (AJ-01), firma b88a3662…)
# ============================================================
from __future__ import annotations

import time
import uuid

import pytest

from test_289_f06_01h_alta_en_compra import LabHip, huella


def _recuentos(lab: LabHip, f: uuid.UUID) -> dict:
    uno = lambda sql: lab.sql(sql, (f,))[0][0]  # noqa: E731
    return {
        "financiaciones": uno("SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = %s"),
        "cuotas": uno("SELECT count(*) FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s"),
        "cuotas_distintas": uno("SELECT count(DISTINCT numero_cuota) FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s"),
        "previsiones": uno("SELECT count(*) FROM gapto.previsiones WHERE entidad_id = %s"),
        "versiones": uno("SELECT count(*) FROM gapto.financiacion_condiciones_versiones WHERE financiacion_entidad_id = %s"),
    }


@pytest.mark.parametrize("n", [300, 360])
def test_compra_hipoteca_larga_y_replay_idempotente_sin_duplicados(n, capsys):
    lab = LabHip()
    cuerpo = lab.peticion_hip(hip=lab.bloque(numero_cuotas=n))
    t0 = time.perf_counter()
    r = lab.compra(cuerpo)
    dur = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["idempotente"] is False and j["hipoteca"]["numero_cuotas"] == n
    f = uuid.UUID(j["hipoteca"]["financiacion_id"])
    esperado = {"financiaciones": 1, "cuotas": n, "cuotas_distintas": n, "previsiones": n, "versiones": 1}
    assert _recuentos(lab, f) == esperado
    h0 = uuid.UUID(cuerpo["intencion_id"])
    hechos = lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (h0,))[0][0]
    assert hechos == 1
    # replay (cliente tras un timeout): misma peticion -> idempotente, sin ninguna escritura
    antes = huella()
    t1 = time.perf_counter()
    r2 = lab.compra(cuerpo)
    dur_replay = time.perf_counter() - t1
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotente"] is True
    assert r2.json()["hipoteca"]["financiacion_id"] == str(f)
    assert huella() == antes
    assert _recuentos(lab, f) == esperado
    with capsys.disabled():
        print(f"\n[R-B2-06] n={n} compra={dur:.2f}s replay={dur_replay:.2f}s")
