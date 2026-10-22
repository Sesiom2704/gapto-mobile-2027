# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_208_f05_06_m5b_concurrencia_serial.py
# Ruta: tests/api/test_208_f05_06_m5b_concurrencia_serial.py
# Descripcion: F05-06 M5-B (F04-D065 §1; F05 §61 F05-D047; AJ-M5BM1-11).
#   Bateria SERIAL y determinista, FUERA de la suite general: solo con
#   GAPTO_M5_CONCURRENCIA=1 (la misma bandera que test_205). Arnes de test_205:
#   el primer paso se retiene dentro de su transaccion despues de su ultimo
#   lock, se lanza el segundo y se libera el primero; ambos ordenes, un
#   resultado esperado por orden y un oraculo de estado final.
#   Orden de locks: «Dar por cubierta» adquiere [regla FU ->] prevision FU, el
#   sufijo de OP-17 (hecho -> regla -> prevision, F04-D058) y de
#   retirar_vinculo; no hay aristas nuevas ni cambio de topologia.
#     C0 dar / OP-17 (vincular_realidad), misma prevision, sin y con regla
#        (orden de locks frente a OP-17; tambien es C2 del mandato);
#     C1 dar / retirar_vinculo del ULTIMO hecho (AJ-11);
#     C1b dar / OP-03 del unico hecho de una cabeza RODANTE ABIERTA. OP-03 no
#        toma el lock de una prevision ABIERTA (F04-D022: la realidad manda y
#        nunca espera a una prevision), asi que no se serializan: si OP-03
#        confirma mientras dar esta retenido, el recuento de dar (posterior a
#        su lock, lectura nueva en READ COMMITTED) ve el hecho ANULADO y
#        rechaza con PREVISION_SIN_REALIDAD_ACTIVA; si dar confirma antes, la
#        anulacion posterior deja REALIZADA_SIN_REALIDAD_ACTIVA (AJ-11). Nunca
#        una REALIZADA de dar con cero hechos ACTIVOS confirmados al leer;
#     C3 doble dar (sin y con regla: nunca dos sucesores);
#     C4 reabrir / OP-17 sobre el sucesor RODANTE.
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos;
#   nunca dos ABIERTAS en una cadena RODANTE; nunca un vinculo ACTIVO sobre una
#   CANCELADA u OMITIDA.
# Version: 0.1.0 (F05-06 M5-B)
# ============================================================

from __future__ import annotations

import os
import uuid

import pytest

import f05_01_helpers as fh
import f05_06_m5_helpers as m
from app.api import ejecucion_prevision as ejp
from app.api.dto_prevision import IntencionDarPorCubierta, IntencionReabrir
from app.repositories import previsiones_repository as repo_prev
from app.services import previsiones_service as serv_prev
from test_205_f05_06_m5_concurrencia_serial import (  # arnes comun (sin tests)
    OK, ORDENES, PT_OP03, PT_OP17, _gasto, _sin_pago, _vincular_motor, correr, ctx, evidencia, op03, op17)

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M5_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M5_CONCURRENCIA=1)")

# Puntos de pausa: el ultimo lock de cada ruta antes de escribir.
PT_DAR = (repo_prev, "bloquear_prevision")      # dar: [regla FU ->] prevision FU
PT_RETIRAR = (repo_prev, "bloquear_prevision")  # retirar_vinculo: [regla FU ->] prevision FU
PT_REABRIR = (repo_prev, "tocar_prevision")     # reabrir: regla FU -> UPDATE con version


def dar(owner, pid, version=None):
    v = version or m.version(owner, pid)
    return lambda: ejp.dar_por_cubierta(fh.unidad(), ctx(owner), pid, IntencionDarPorCubierta(
        intencion_id=uuid.uuid4(), row_version=v, motivo="la factura definitiva fue menor"))


def reabrir(owner, pid, sucesor):
    v, sv = m.version(owner, pid), m.version(owner, sucesor)
    return lambda: ejp.reabrir(fh.unidad(), ctx(owner), pid, IntencionReabrir(
        intencion_id=uuid.uuid4(), row_version=v, motivo="la marqué por error", sucesor_row_version=sv))


def retirar(owner, pid):
    vid = m.uno(owner, "SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (pid,))[0]
    v = m.version(owner, pid)
    return lambda: serv_prev.PrevisionesService(fh.unidad()).retirar_vinculo(
        ctx(owner), vinculo_id=vid, prevision_id_esperada=pid, prevision_row_version_esperada=v,
        motivo="nunca debio existir")


def _parcial(owner, cli, cta, con_regla: bool):
    """Prevision ABIERTA con un pago parcial de 20 (sin regla o cabeza RODANTE)."""
    regla = None
    if con_regla:
        regla, pid = m.rodante(owner, cuenta_salida=cta, desde="2026-10-01", importe="74.00")
    else:
        pid = m.prevision(owner, "Seguro", importe="74.00")
    hid = _gasto(cli, cta, "20.00")
    m.vincular(cli, owner, pid, hid, "20.00", False)
    return regla, pid, hid


def _cadena_sana(owner, regla) -> bool:
    if regla is None:
        return True
    estados = [e for _, e, _ in m.previsiones_de_regla(owner, regla)]
    return estados.count("ABIERTA") <= 1


def _sin_realidad_en_terminal_vacia(owner) -> bool:
    return m.uno(owner, "SELECT count(*) FROM gapto.prevision_hechos pv JOIN gapto.previsiones p ON p.id = "
                        "pv.prevision_id JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id "
                        "WHERE p.estado IN ('CANCELADA', 'OMITIDA') AND h.estado = 'ACTIVO'")[0] == 0


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    return owner, cli, cta, ahorro


# ------------------------------------------------------------------ C0 / C2: dar frente a OP-17
@pytest.mark.parametrize("con_regla", [False, True], ids=["sin_regla", "con_regla"])
@pytest.mark.parametrize("orden", ORDENES)
def test_c0_dar_frente_a_op17_orden_de_locks(t, monkeypatch, caplog, orden, con_regla):
    owner, cli, cta, _ = t
    regla, pid, _ = _parcial(owner, cli, cta, con_regla)
    otro = _gasto(cli, cta, "30.00")
    tr = correr(monkeypatch, caplog, "C0", orden, ("A", dar(owner, pid), PT_DAR),
                ("B", op17(owner, pid, otro, "30.00", False), PT_OP17))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "VERSION_DESFASADA"), tr
    if orden == "A-primero":
        assert m.estado(owner, pid) == "REALIZADA" and len(m.vinculos(owner, pid)) == 1
    else:
        assert m.estado(owner, pid) == "ABIERTA" and len(m.vinculos(owner, pid)) == 2
    assert _cadena_sana(owner, regla)
    evidencia(f"C0_{'regla' if con_regla else 'sin_regla'}_{orden}", {**tr, "estado": m.estado(owner, pid)})


# ------------------------------------------------------------------ C1: dar frente a retirar el ultimo hecho
@pytest.mark.parametrize("con_regla", [False, True], ids=["sin_regla", "con_regla"])
@pytest.mark.parametrize("orden", ORDENES)
def test_c1_dar_frente_a_retirar_el_ultimo_vinculo(t, monkeypatch, caplog, orden, con_regla):
    owner, cli, cta, _ = t
    regla, pid, _ = _parcial(owner, cli, cta, con_regla)
    tr = correr(monkeypatch, caplog, "C1", orden, ("A", dar(owner, pid), PT_DAR),
                ("B", retirar(owner, pid), PT_RETIRAR))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "VERSION_DESFASADA"), tr
    if orden == "A-primero":
        assert m.estado(owner, pid) == "REALIZADA" and len(m.vinculos(owner, pid)) == 1
    else:
        # Nunca una REALIZADA por «Dar por cubierta» sin realidad activa.
        assert m.estado(owner, pid) == "ABIERTA" and m.vinculos(owner, pid) == []
    assert _cadena_sana(owner, regla)
    evidencia(f"C1_{'regla' if con_regla else 'sin_regla'}_{orden}", {**tr, "estado": m.estado(owner, pid)})


@pytest.mark.parametrize("orden", ORDENES)
def test_c1b_dar_frente_a_op03_recuento_bajo_lock(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta, desde="2026-10-01", importe="74.00")
    hid = _sin_pago(owner, "20.00")
    _vincular_motor(owner, cabeza, hid, "20.00")
    # La version de dar es la vigente: solo el recuento posterior al lock puede rechazarlo.
    tr = correr(monkeypatch, caplog, "C1b", orden, ("A", dar(owner, cabeza), PT_DAR), ("B", op03(owner, hid), PT_OP03))
    assert tr["B"] == OK and tr["segundo_bloqueado"] is False, tr  # no se serializan (F04-D022)
    d = m.detalle(cli, cabeza)
    if orden == "A-primero":
        # OP-03 confirma con dar retenido: el recuento de dar ya ve el hecho ANULADO.
        assert tr["A"] == "PREVISION_SIN_REALIDAD_ACTIVA", tr
        assert d["estado"] == "ABIERTA"
    else:
        # dar confirma con OP-03 retenido; la anulacion posterior deja AJ-11.
        assert tr["A"] == OK, tr
        assert (d["estado"], d["estado_derivado"]) == ("REALIZADA", "REALIZADA_SIN_REALIDAD_ACTIVA")
    assert _cadena_sana(owner, regla)
    evidencia(f"C1b_{orden}", {**tr, "estado": d["estado"], "estado_derivado": d["estado_derivado"]})


# ------------------------------------------------------------------ C3: doble dar
@pytest.mark.parametrize("con_regla", [False, True], ids=["sin_regla", "con_regla"])
@pytest.mark.parametrize("orden", ORDENES)
def test_c3_doble_dar(t, monkeypatch, caplog, orden, con_regla):
    owner, cli, cta, _ = t
    regla, pid, _ = _parcial(owner, cli, cta, con_regla)
    v = m.version(owner, pid)
    tr = correr(monkeypatch, caplog, "C3", orden, ("A", dar(owner, pid, v), PT_DAR), ("B", dar(owner, pid, v), PT_DAR))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "ESTADO_PREVISION_INCOMPATIBLE"), tr
    assert m.estado(owner, pid) == "REALIZADA"
    if regla is not None:  # exactamente un sucesor (nunca dos)
        assert [e for _, e, _ in m.previsiones_de_regla(owner, regla)] == ["REALIZADA", "ABIERTA"]
    evidencia(f"C3_{'regla' if con_regla else 'sin_regla'}_{orden}", tr)


# ------------------------------------------------------------------ C4: reabrir frente a OP-17 sobre el sucesor
@pytest.mark.parametrize("orden", ORDENES)
def test_c4_reabrir_frente_a_op17_sobre_el_sucesor(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    regla, cabeza, _ = _parcial(owner, cli, cta, True)
    dar(owner, cabeza)()
    sucesor = [p for p, e, _ in m.previsiones_de_regla(owner, regla) if e == "ABIERTA"][0]
    hid = _gasto(cli, cta, "74.00", fecha="2026-10-08")
    tr = correr(monkeypatch, caplog, "C4", orden, ("A", reabrir(owner, cabeza, sucesor), PT_REABRIR),
                ("B", op17(owner, sucesor, hid, "74.00", False), PT_OP17))
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert (m.estado(owner, cabeza), m.estado(owner, sucesor)) == ("ABIERTA", "CANCELADA")
        assert m.vinculos(owner, sucesor) == []
    else:
        assert (tr["B"], tr["A"]) == (OK, "TRAMO_RODANTE_REQUIERE_REVISION"), tr
        assert (m.estado(owner, cabeza), m.estado(owner, sucesor)) == ("REALIZADA", "ABIERTA")
        assert len(m.vinculos(owner, sucesor)) == 1
    assert _cadena_sana(owner, regla) and _sin_realidad_en_terminal_vacia(owner)
    evidencia(f"C4_{orden}", {**tr, "cabeza": m.estado(owner, cabeza), "sucesor": m.estado(owner, sucesor)})
