# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_149_f04_d055_concurrencia.py
# Ruta: tests/backend/test_149_f04_d055_concurrencia.py
# Descripcion: F04-D055 B1 · CC-D055-2. Concurrencia de la reapertura bajo la
#   raiz B8 de F04-D053, con operaciones REALES y la misma infraestructura que
#   test_146 (T1 pausado tras adquirir su raiz; espera observada en
#   pg_stat_activity; unidades con max_intentos=1, de modo que un 40P01
#   aflora como CONFLICTO_CONCURRENCIA).
#
#   1. Misma posicion: reabrir frente a cerrar, reabrir, OP-21, OP-02, OP-03
#      y creacion de delta, en los dos sentidos cuando T1 puede ganar. T2
#      ESPERA, el resultado de cada pareja es DETERMINISTA (exito o el codigo
#      exacto con el que pierde) y el recuento C/R de la auditoria es
#      coherente con el estado final.
#   2. Posiciones distintas: no esperan.
#   3. R-Q2: un CERRAR cuya transaccion empezo ANTES que el REABRIR que lo
#      precede en la serializacion queda con created_at anterior; la marca
#      legacy no depende de ese orden (recuento, no "ultimo evento").
#
#   Se ejecuta APARTE, en serie y sin otra suite en paralelo (como test_146).
# Version: 0.1.0
#   0.1.0 (F04-D055 B1): bateria de concurrencia de la reapertura.
# ============================================================
from __future__ import annotations

import datetime as dt
import threading
import uuid

import pytest

import app.services.integridad_posicion as integridad_posicion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_posicion import DatosCierre, DatosCondonacionObligacion
from conftest import leer_fila
from test_109_op12_posiciones import CONDONACION, delta
from test_146_f04_d053_raiz_bloqueo import (  # noqa: F401 - fixture `escenario`
    D,
    OPERACIONES,
    TIMEOUT,
    Hilo,
    Servicios,
    _carrera,
    _cerrar,
    _sin_error,
    _version_entidad,
    escenario,
)

CIERRE = dt.date(2026, 7, 1)


# ==================================================================
# Preparacion de la posicion (fuera de la carrera)
# ==================================================================

def _estado(admin, e, p) -> str:
    return leer_fila(admin, e["owner"], "SELECT estado FROM gapto.derechos_obligaciones_financieras "
                     "WHERE entidad_id = %s", (p["entidad"],))[0]


def _recuento(admin, e, p) -> tuple[int, int]:
    fila = leer_fila(admin, e["owner"],
                     "SELECT count(*) FILTER (WHERE accion = 'CERRAR'), "
                     "count(*) FILTER (WHERE accion = 'REABRIR') FROM gapto.auditoria "
                     "WHERE tabla = 'derechos_obligaciones_financieras' AND registro_id = %s",
                     (p["entidad"],))
    return int(fila[0]), int(fila[1])


def _a_cero(dsn, admin, e, p) -> None:
    """Extingue el residual (60) con una condonacion explicita: saldo 0."""
    s = Servicios(dsn, f"montaje-{uuid.uuid4()}")
    saldo = s.pos.saldo(e["ctx"], p["entidad"]).saldo.importe
    if saldo > 0:
        s.pos.condonar_obligacion(
            e["ctx"], entidad_id=p["entidad"],
            entidad_row_version_esperada=_version_entidad(admin, e["owner"], p["entidad"]),
            datos=DatosCondonacionObligacion(delta=delta(str(saldo), causa=CONDONACION)))


def _cerrada(dsn, admin, e, p) -> None:
    """Saldo 0 y cierre CONDONADA por el servicio (un CERRAR auditado)."""
    _a_cero(dsn, admin, e, p)
    s = Servicios(dsn, f"montaje-{uuid.uuid4()}")
    s.pos.cerrar_posicion(
        e["ctx"], entidad_id=p["entidad"],
        entidad_row_version_esperada=_version_entidad(admin, e["owner"], p["entidad"]),
        cierre=DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE))


def _reabrir(s, e, admin, p):
    return lambda: s.pos.reabrir_posicion(
        e["ctx"], entidad_id=p["entidad"],
        entidad_row_version_esperada=_version_entidad(admin, e["owner"], p["entidad"]),
        motivo="D055 concurrencia")


OPS = {**OPERACIONES, "reabrir": _reabrir, "cerrar": _cerrar}

PREPARACION = {"CERRADA": _cerrada, "CERO": _a_cero, "VIVA": lambda *a: None}

OK = None
VD = CodigoError.VERSION_DESFASADA
NO_ESTADO = CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO

# (T1, T2): (estado previo, resultado de T2, estado final, (C, R) final).
# T1 siempre termina con exito. T2 lee su version ANTES de que T1 confirme y
# valida DESPUES; su resultado depende solo de lo que T1 dejo confirmado.
PAREJAS = {
    ("reabrir", "cerrar"): ("CERRADA", VD, "ACTIVA", (1, 1)),
    ("cerrar", "reabrir"): ("CERO", VD, "CERRADA", (1, 0)),
    ("reabrir", "reabrir"): ("CERRADA", NO_ESTADO, "ACTIVA", (1, 1)),
    ("reabrir", "op21_importe"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("reabrir", "op21_descripcion"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("reabrir", "op21_contexto"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("reabrir", "op02"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("reabrir", "op03"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    # T2 ve la posicion YA reabierta (no POSICION_CERRADA): con saldo 0, el
    # pago de 5 excede.
    ("reabrir", "crear"): ("CERRADA", CodigoError.EXCEDE_SALDO_POSICION, "ACTIVA", (1, 1)),
    ("op02", "reabrir"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("op21_descripcion", "reabrir"): ("CERRADA", OK, "ACTIVA", (1, 1)),
    ("crear", "reabrir"): ("VIVA", NO_ESTADO, "ACTIVA", (0, 0)),
    ("op21_importe", "reabrir"): ("VIVA", NO_ESTADO, "ACTIVA", (0, 0)),
    ("op03", "reabrir"): ("VIVA", NO_ESTADO, "ACTIVA", (0, 0)),
}


# ==================================================================
# 1 · Misma posicion: serializa, sin 40P01, resultado determinista
# ==================================================================

@pytest.mark.parametrize("pareja", sorted(PAREJAS), ids=lambda p: f"{p[0]}-{p[1]}")
def test_1_reapertura_misma_posicion_serializa(dsn, admin, monkeypatch, escenario, pareja) -> None:
    previo, esperado_t2, final, recuento = PAREJAS[pareja]
    p = escenario["p1"]
    PREPARACION[previo](dsn, admin, escenario, p)
    t1, t2 = pareja
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    f1 = OPS[t1](s1, escenario, admin, p)
    f2 = OPS[t2](s2, escenario, admin, p)
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert espero, f"{t2} no espero a {t1} sobre la misma posicion"
    assert not h1.is_alive() and not h2.is_alive()
    assert h1.error is None, repr(h1.error)
    assert h2.fin >= h1.fin
    if esperado_t2 is OK:
        assert h2.error is None, repr(h2.error)
    else:
        assert isinstance(h2.error, ErrorMotor), repr(h2.error)
        assert h2.error.codigo is esperado_t2, (h2.error.codigo, h2.error.mensaje)
    assert _estado(admin, escenario, p) == final
    assert _recuento(admin, escenario, p) == recuento


# ==================================================================
# 2 · Posiciones distintas: no esperan
# ==================================================================

@pytest.mark.parametrize("pareja", [
    ("reabrir", "reabrir"), ("reabrir", "cerrar"), ("reabrir", "op02"), ("reabrir", "op21_descripcion"),
    ("cerrar", "reabrir"), ("op02", "reabrir"), ("op03", "reabrir"), ("op21_descripcion", "reabrir"),
], ids=lambda p: f"{p[0]}-{p[1]}")
def test_2_reapertura_posiciones_distintas_no_esperan(dsn, admin, monkeypatch, escenario, pareja) -> None:
    t1, t2 = pareja
    for t, p in ((t1, escenario["p1"]), (t2, escenario["p2"])):
        if t == "reabrir":
            _cerrada(dsn, admin, escenario, p)
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    f1 = OPS[t1](s1, escenario, admin, escenario["p1"])
    f2 = OPS[t2](s2, escenario, admin, escenario["p2"])
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert not espero, f"{t2} sobre P2 espero a {t1} sobre P1: bloqueo innecesario"
    _sin_error(h1, h2)
    assert h2.fin < h1.fin


# ==================================================================
# 3 · R-Q2: created_at no ordena; la marca es un recuento
# ==================================================================

def test_3_rq2_orden_created_at_no_decide(dsn, admin, monkeypatch, escenario) -> None:
    """CERRAR #2 empieza su transaccion ANTES que el REABRIR que lo precede
    en la serializacion: su created_at queda ANTERIOR. Con C=2 y R=1 el cierre
    actual esta acreditado; decidir por el ultimo evento segun created_at lo
    marcaria legacy por error."""
    p = escenario["p1"]
    _cerrada(dsn, admin, escenario, p)  # CERRAR #1
    v = _version_entidad(admin, escenario["owner"], p["entidad"])
    en_pausa, liberar = threading.Event(), threading.Event()
    original = integridad_posicion.adquirir_raiz

    def antes_de_la_raiz(*args, **kwargs):
        if threading.current_thread().name == "TA":
            en_pausa.set()  # transaccion ya iniciada (contexto fijado)
            if not liberar.wait(TIMEOUT):
                raise RuntimeError("TA sin liberar")
        return original(*args, **kwargs)

    monkeypatch.setattr(integridad_posicion, "adquirir_raiz", antes_de_la_raiz)
    sa = Servicios(dsn, f"TA-{uuid.uuid4()}")
    cierre_2 = Hilo("TA", lambda: sa.pos.cerrar_posicion(
        escenario["ctx"], entidad_id=p["entidad"], entidad_row_version_esperada=v + 1,
        cierre=DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)))
    cierre_2.start()
    assert en_pausa.wait(TIMEOUT), repr(cierre_2.error)
    sb = Servicios(dsn, f"TB-{uuid.uuid4()}")
    sb.pos.reabrir_posicion(escenario["ctx"], entidad_id=p["entidad"],
                            entidad_row_version_esperada=v, motivo="primera")
    liberar.set()
    cierre_2.join(TIMEOUT)
    assert not cierre_2.is_alive() and cierre_2.error is None, repr(cierre_2.error)

    orden = leer_fila(admin, escenario["owner"],
                      "SELECT (SELECT max(created_at) FROM gapto.auditoria WHERE registro_id = %s "
                      "        AND accion = 'CERRAR') "
                      "     < (SELECT max(created_at) FROM gapto.auditoria WHERE registro_id = %s "
                      "        AND accion = 'REABRIR')",
                      (p["entidad"], p["entidad"]))[0]
    assert orden is True, "el escenario no ha producido la inversion de created_at"
    assert _recuento(admin, escenario, p) == (2, 1)

    sb.pos.reabrir_posicion(escenario["ctx"], entidad_id=p["entidad"],
                            entidad_row_version_esperada=v + 2, motivo="segunda")
    motivo = leer_fila(admin, escenario["owner"],
                       "SELECT motivo FROM gapto.auditoria WHERE registro_id = %s AND accion = 'REABRIR' "
                       "AND motivo LIKE %s", (p["entidad"], "%segunda"))[0]
    assert motivo == "REABRIR: segunda"
    assert D("0") == sb.pos.saldo(escenario["ctx"], p["entidad"]).saldo.importe
