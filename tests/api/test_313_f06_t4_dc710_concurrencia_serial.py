# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_313_f06_t4_dc710_concurrencia_serial.py
# Ruta: tests/api/test_313_f06_t4_dc710_concurrencia_serial.py
# Descripcion: D-C7-10 · bateria serial de concurrencia del gesto «Pagado» (mandato F06 T4 DC710 v1.0 §4,
#   AJ-DC710-07 casos 7 y 8; «concurrencia en serie ×3»). Mismo arnes que test_295 (A se detiene antes del COMMIT con
#   sus locks; B arranca y debe quedar en Lock; pg_locks en el punto de espera; se suelta A). El payload del swipe sale
#   SOLO del bloque `cuota` de Pendientes. Casos, cada uno ×3:
#   - DC-C1 swipe ∥ boton (intenciones distintas): gana el swipe; el boton CUOTA_NO_PENDIENTE o VERSION_DESFASADA;
#     un solo hecho.
#   - DC-C2 boton ∥ swipe: gana el boton; el swipe es rechazo (la cola lo deja RECHAZADA); un solo hecho.
#   - DC-C3 revision del tipo ∥ swipe (revision primero): el swipe espera en la financiacion y es VERSION_DESFASADA;
#     ningun pago.
#   Sin deadlocks ni reintentos 40P01/40001. Fuera de la suite general (GAPTO_DC710_CONCURRENCIA=1).
# Version: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
# ============================================================
from __future__ import annotations

import os

import pytest

from test_295_f06_01h_concurrencia_serial import (  # noqa: F401 - `arnes` es el fixture autouse de las pausas
    FINANCIACION, arnes, assert_g2, cerrar, clientes, g2, intercalar, pagadas, pagar, revisar)
from test_311_f06_t4_dc710_bloque_cuota import _payload
from test_312_f06_t4_dc710_integracion_pago import LabC

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_DC710_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_DC710_CONCURRENCIA=1)")

REPS = [1, 2, 3]
RECHAZOS = ((409, "CUOTA_NO_PENDIENTE"), (409, "VERSION_DESFASADA"))


def _hechos(lab, *intenciones) -> int:
    return lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = ANY(%s::uuid[])",
                   ([str(i) for i in intenciones],))[0][0]


@pytest.mark.parametrize("rep", REPS)
def test_dc_c1_swipe_frente_al_boton(rep):
    lab = LabC()
    ca, cb = clientes(lab)
    swipe, boton = _payload(lab.fila(1)), lab.cuerpo()
    t = intercalar("DC-C1", lambda: pagar(lab, ca, 1, swipe), lambda: pagar(lab, cb, 1, boton), espera=True)
    datos = cerrar(f"DC-C1_rep{rep}", t, hechos=_hechos(lab, swipe["intencion_id"], boton["intencion_id"]),
                   g2=g2(lab), pagadas=pagadas(lab))
    assert datos["espera_b"], datos
    assert datos["A"] == (200, None) and datos["B"] in RECHAZOS, datos
    assert datos["hechos"] == 1 and [p[0] for p in datos["pagadas"]] == [1], datos
    assert _hechos(lab, swipe["intencion_id"]) == 1
    assert_g2(lab, datos)


@pytest.mark.parametrize("rep", REPS)
def test_dc_c2_boton_frente_al_swipe(rep):
    lab = LabC()
    ca, cb = clientes(lab)
    swipe, boton = _payload(lab.fila(1)), lab.cuerpo()
    t = intercalar("DC-C2", lambda: pagar(lab, ca, 1, boton), lambda: pagar(lab, cb, 1, swipe), espera=True)
    datos = cerrar(f"DC-C2_rep{rep}", t, hechos=_hechos(lab, swipe["intencion_id"], boton["intencion_id"]),
                   g2=g2(lab), pagadas=pagadas(lab))
    assert datos["espera_b"], datos
    assert datos["A"] == (200, None) and datos["B"] in RECHAZOS, datos
    assert datos["hechos"] == 1 and _hechos(lab, swipe["intencion_id"]) == 0, datos
    assert_g2(lab, datos)


@pytest.mark.parametrize("rep", REPS)
def test_dc_c3_revision_frente_al_swipe(rep):
    lab = LabC()
    ca, cb = clientes(lab)
    swipe = _payload(lab.fila(1))
    rev = lab.cuerpo_rev(desde="2026-04-01")
    t = intercalar("DC-C3", lambda: revisar(lab, ca, rev), lambda: pagar(lab, cb, 1, swipe), espera=True)
    datos = cerrar(f"DC-C3_rep{rep}", t, g2=g2(lab), pagadas=pagadas(lab), versiones=len(lab.versiones()))
    assert set(datos["espera_b"]) & FINANCIACION, datos
    assert datos["A"] == (200, None) and datos["B"] == (409, "VERSION_DESFASADA"), datos
    assert datos["versiones"] == 2 and datos["pagadas"] == [] and _hechos(lab, swipe["intencion_id"]) == 0, datos
    assert_g2(lab, datos)
