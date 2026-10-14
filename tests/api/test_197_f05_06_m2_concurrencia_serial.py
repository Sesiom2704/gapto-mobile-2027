# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_197_f05_06_m2_concurrencia_serial.py
# Ruta: tests/api/test_197_f05_06_m2_concurrencia_serial.py
# Descripcion: Concurrencia de la devolucion contextual (F05-06 M2-A §A5;
#   F05 §51.4 CC-06-C). Bateria SERIAL y determinista, FUERA de la suite
#   general: solo con GAPTO_M2_CONCURRENCIA=1. Reutiliza el arnes de test_190
#   (_serie, _barrera_fila): una sesion BARRERA retiene el lock de la fila, los
#   comandos se lanzan uno a uno y cada uno debe quedar esperando antes del
#   siguiente; al liberar, PostgreSQL concede en orden de llegada. Si
#   GAPTO_J2J3_EVIDENCIA apunta a una carpeta, cada escenario deja alli su JSON
#   (pg_locks y resultados). Escenarios, en los DOS ordenes:
#     (a) dos devoluciones (70 y 60 sobre 120) que juntas exceden el limite:
#         la primera pasa y la segunda recibe EXCEDE_CAPACIDAD_REVERSIBLE;
#     (b) devolucion frente a anulacion del origen (OP-03, G-R1-A): si va
#         primero la devolucion, OP-03 recibe HECHO_CON_REALIDAD_ASOCIADA; si
#         va primero OP-03, la devolucion recibe DEVOLUCION_ORIGEN_NO_ACTIVO;
#     (c) abono doble sobre la misma devolucion pendiente (dos cuentas
#         distintas, para que solo se encuentren en el hecho): uno pasa, el
#         otro recibe YA_CONCILIADO; una sola conciliacion.
#   En todos: ningun 40P01 (ni reintento de la UnidadDeTrabajo ni aumento de
#   pg_stat_database.deadlocks) y nada parcial.
# Version: 0.1.0 (F05-06 M2-A §A5)
# ============================================================

from __future__ import annotations

import logging
import os
import time
import uuid

import psycopg
import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as m
import vs01_api_helpers as h
from app.core.errores import CodigoError, ErrorMotor
from test_190_f05_j2j3_concurrencia_serial import _barrera_fila, _cod, _serie

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M2_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M2_CONCURRENCIA=1)")
HECHO_FOR_UPDATE = "SELECT id FROM gapto.hechos_financieros WHERE id=%s FOR UPDATE"


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    ropa = x.categoria(owner, "Ropa")
    return owner, actor, cli, cta, ahorro, ropa


@pytest.fixture(autouse=True)
def sin_40p01(caplog):
    caplog.set_level(logging.WARNING, logger="gapto.motor.transaccion")
    antes = _deadlocks()
    yield
    reintentos = [r for r in caplog.records if r.name == "gapto.motor.transaccion" and getattr(r, "sqlstate", None)]
    assert not reintentos, [(r.getMessage(), r.sqlstate) for r in reintentos]
    assert _deadlocks(espera=True) == antes


def _deadlocks(espera: bool = False) -> int:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        if espera:
            time.sleep(1.1)
            c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


def _en_orden(primero: str, pasos: dict) -> list:
    otro = next(k for k in pasos if k != primero)
    return [(primero, pasos[primero]), (otro, pasos[otro])]


def _devoluciones(owner, origen) -> list:
    return h.leer(owner, "SELECT r.importe_relacionado FROM gapto.hecho_relaciones r "
                         "WHERE r.hecho_destino_id=%s AND r.tipo_relacion='DEVOLUCION_DE' ORDER BY 1", (origen,))


@pytest.mark.parametrize("primero", ["A70", "B60"])
def test_a_dos_devoluciones_que_juntas_exceden(t, primero):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    a, b = m.cuerpo("70.00"), m.cuerpo("60.00")
    url = m.url_devoluciones(origen)
    barrera = _barrera_fila(owner, HECHO_FOR_UPDATE, (origen,))
    pasos = {"A70": lambda: cli.post(url, json=a, headers=h.AUTH), "B60": lambda: cli.post(url, json=b, headers=h.AUTH)}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M2_a_{primero}")
    segundo = "B60" if primero == "A70" else "A70"
    assert salida[primero].status_code == 200, salida[primero].text
    assert (salida[segundo].status_code, _cod(salida[segundo])) == (409, "EXCEDE_CAPACIDAD_REVERSIBLE")
    gana = "70.0000" if primero == "A70" else "60.0000"
    assert [str(f[0]) for f in _devoluciones(owner, origen)] == [gana]
    assert salida[segundo].json()["detalle"]["queda"] == ("50.00" if primero == "A70" else "60.00")


@pytest.mark.parametrize("primero", ["devolucion", "anulacion"])
def test_b_devolucion_frente_a_anulacion_del_origen(t, primero):
    owner, actor, cli, _, _, ropa = t
    origen = x.hecho_motor(owner, [("GASTO", "120", "COMPLETA", ropa, [(actor, "120")])], fecha=m.FECHA_COMPRA)
    cuerpo = m.cuerpo()
    barrera = _barrera_fila(owner, HECHO_FOR_UPDATE, (origen,))
    pasos = {"devolucion": lambda: cli.post(m.url_devoluciones(origen), json=cuerpo, headers=h.AUTH),
             "anulacion": lambda: m.anular_op03(owner, origen)}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M2_b_{primero}")
    estado = h.leer(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id=%s", (origen,))[0][0]
    if primero == "devolucion":
        assert salida["devolucion"].status_code == 200, salida["devolucion"].text
        exc = salida["anulacion"]
        assert isinstance(exc, ErrorMotor) and exc.codigo is CodigoError.HECHO_CON_REALIDAD_ASOCIADA
        assert estado == "ACTIVO" and len(_devoluciones(owner, origen)) == 1
    else:
        assert not isinstance(salida["anulacion"], ErrorMotor), salida["anulacion"]
        r = salida["devolucion"]
        assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_NO_ACTIVO")
        assert estado == "ANULADO" and _devoluciones(owner, origen) == []
        assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
                      (uuid.UUID(cuerpo["intencion_id"]),))[0][0] == 0


@pytest.mark.parametrize("primero", ["cuenta1", "cuenta2"])
def test_c_abono_doble(t, primero):
    owner, actor, cli, cta, _, ropa = t
    otra = h.crear_cuenta(owner, [(actor, 100)], tipo="CORRIENTE")
    origen = m.compra(cli, cta, categoria_id=ropa)
    c, r = m.devolver(cli, origen)
    assert r.status_code == 200, r.text
    dev = uuid.UUID(c["intencion_id"])
    barrera = _barrera_fila(owner, HECHO_FOR_UPDATE, (dev,))
    pasos = {"cuenta1": lambda: m.abonar(cli, dev, cta)[1], "cuenta2": lambda: m.abonar(cli, dev, otra)[1]}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M2_c_{primero}")
    segundo = "cuenta2" if primero == "cuenta1" else "cuenta1"
    assert salida[primero].status_code == 200, salida[primero].text
    assert (salida[segundo].status_code, _cod(salida[segundo])) == (409, "YA_CONCILIADO")
    conc = h.leer(owner, "SELECT m.cuenta_id FROM gapto.hecho_movimientos_tesoreria hm "
                         "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id WHERE hm.hecho_id=%s",
                  (dev,))
    assert conc == [(cta if primero == "cuenta1" else otra,)]
