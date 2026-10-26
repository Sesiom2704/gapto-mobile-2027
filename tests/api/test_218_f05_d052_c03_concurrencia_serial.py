# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_218_f05_d052_c03_concurrencia_serial.py
# Ruta: tests/api/test_218_f05_d052_c03_concurrencia_serial.py
# Descripcion: F05-D052 (F05 §66.A.5, §66.A.11.6). Bateria SERIAL y
#   determinista del gasto reembolsable C-03, FUERA de la suite general: solo
#   con GAPTO_C03_CONCURRENCIA=1. Si GAPTO_C03_EVIDENCIA apunta a una carpeta,
#   cada escenario deja su JSON. Nunca en paralelo.
#   Tecnica de M3 (test_200/test_201, reutilizada sin cambios): el primer paso
#   se detiene DENTRO de su transaccion en un punto fijo, ya con sus locks;
#   con el retenido se lanza el segundo; ambos ordenes, un resultado esperado
#   por orden y oraculo de estado final. Oraculos comunes: nadie colgado, 0
#   reintentos 40P01 y 0 deadlocks nuevos; ningun actor huerfano.
#     C1 dos C-03 simultaneos con la misma empresa nueva: un solo actor;
#     C2 C-03 frente a deshabilitar el tercero;
#     C3 C-03 frente a cambiar la naturaleza del tercero (a ORGANISMO);
#     C4 cobro frente a anulacion (anular por duplicado, guarda POSICIONES, y
#        OP-03 del motor);
#     C5 cobro frente a otro cobro de la misma posicion;
#     C6 orden de locks (prueba POSITIVA, §66.A.5): en cada pausa lo retenido
#        es un prefijo de raiz -> INVERSIONES -> cuenta -> terceros por UUID
#        -> writer de actor.
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.11.6)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import logging
import os
import pathlib
import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_d052_c03_helpers as c
import f05_06_m3_helpers as m
import vs01_api_helpers as h
from app.actores import servicio as actores
from app.api import ejecucion_anulacion as eja
from app.api import ejecucion_reembolsable as ejr
from app.api import ejecucion_reparto as rep
from app.api.dto_edicion import IntencionAnularDuplicado
from app.api.dto_reembolsable import IntencionGastoReembolsable
from app.api.dto_reparto import IntencionCobroPago
from app.core.contexto import ContextoOperacion
from test_200_f05_06_m3_concurrencia_serial import Pausa, Paso, bloqueados, deadlocks, esperar, reintentos
from test_201_f05_06_m3_orden_locks import PausaEn

D = decimal.Decimal
LOGGER = "gapto.motor.transaccion"
FECHA_OP = dt.date(2026, 10, 8)
ORDENES = ["A-primero", "B-primero"]
OK = "OK"
ADVISORY_INV = "SELECT pg_try_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(%s::text))"
ADVISORY_RAIZ = "SELECT pg_try_advisory_xact_lock(hashtext('gapto:OP22'), hashtext(%s::text))"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_C03_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_C03_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_C03_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def correr(monkeypatch, caplog, nombre: str, orden: str, a: tuple, b: tuple) -> dict:
    """Igual que test_200.correr, con la evidencia de este bloque."""
    primero, segundo = (a, b) if orden == "A-primero" else (b, a)
    dsn = h.dsn()
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    antes = deadlocks(dsn)
    pausa = Pausa(monkeypatch, *primero[2], hilo=primero[0])
    p1, p2 = Paso(primero[0], primero[1]), Paso(segundo[0], segundo[1])
    traza: dict = {"escenario": nombre, "orden": [primero[0], segundo[0]]}
    try:
        p1.start()
        traza["primero_retenido"] = pausa.llego.wait(30)
        p2.start()
        esperar(lambda: not p2.is_alive() or len(bloqueados(dsn)) >= 1, 30)
        traza["segundo_bloqueado"] = p2.is_alive()
    finally:
        pausa.sigue.set()
        for p in (p1, p2):
            p.join(60)
    time.sleep(1.1)
    traza.update({p.name: p.codigo for p in (p1, p2)})
    traza.update({"vivos": [p.name for p in (p1, p2) if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"), "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    evidencia(f"{nombre}_{orden}", traza)
    assert traza["primero_retenido"], traza
    assert traza["vivos"] == [] and traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    return traza


def ctx(owner) -> ContextoOperacion:
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def c03(owner, cuerpo: dict):
    return lambda: ejr.registrar_gasto_reembolsable(fh.unidad(), ctx(owner), IntencionGastoReembolsable(**cuerpo))


def cobro(owner, entidad, cuenta, importe: str):
    return lambda: rep.cobrar(fh.unidad(), ctx(owner), entidad, IntencionCobroPago(
        intencion_id=uuid.uuid4(), importe=D(importe), cuenta_id=cuenta, fecha=FECHA_OP))


def desactivar_tercero(owner, tercero):
    from app.terceros import servicio as st
    v = m.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (tercero,))[0]
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: st.desactivar(s, tercero_id=tercero, row_version=v))


def editar_naturaleza(owner, tercero, naturaleza):
    from app.terceros import servicio as st
    v, nombre = m.uno(owner, "SELECT row_version, nombre FROM gapto.terceros WHERE id = %s", (tercero,))
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: st.editar(
        s, tercero_id=tercero, row_version=v, nombre=nombre, naturaleza=naturaleza))


def anular_duplicado(owner, cli, hecho):
    ed = c.edicion(cli, hecho)
    mov = ed["movimientos"][0]
    intencion = IntencionAnularDuplicado(
        intencion_id=uuid.uuid4(), row_version=ed["row_version"], motivo="C-03 concurrencia",
        movimientos_row_version={uuid.UUID(mov["movimiento_id"]): mov["row_version"]}, duplicado_declarado=True)
    return lambda: eja.anular_duplicado_http(fh.unidad(), ctx(owner), hecho, intencion)


def anular_op03(owner, hecho):
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla
    v = m.version(owner, hecho)
    return lambda: HechosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla).anular_hecho(
        ctx(owner), hecho_id=hecho, row_version_esperada=v, motivo_anulacion="duplicado")


def _pt_actor():
    return actores, "actor_de_tercero"


def _pt_tercero():
    from app.terceros import repositorio
    return repositorio, "leer"


def _pt_posiciones():
    from app.repositories import posiciones_repository
    return posiciones_repository, "bloquear_posiciones"


@pytest.fixture()
def t():
    owner, yo, cli, cta, ahorro, comb = c.entorno()
    return owner, yo, cli, cta, comb


def _actores(owner, tercero) -> int:
    return m.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (tercero,))[0]


def _hecho(owner, cuerpo) -> int:
    return m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (cuerpo["intencion_id"],))[0]


# ------------------------------------------------------------------ C1
@pytest.mark.parametrize("orden", ORDENES)
def test_c1_dos_c03_simultaneos_con_la_misma_empresa_nueva(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _ = t
    emp = c.tercero(cli, "Empresa nueva")
    a, b = c.cuerpo(cta, emp, "10.00", importe="10.00"), c.cuerpo(cta, emp, "20.00", importe="20.00")
    traza = correr(monkeypatch, caplog, "c1_dos_c03_misma_empresa", orden,
                   ("C03-A", c03(owner, a), _pt_actor()), ("C03-B", c03(owner, b), _pt_actor()))
    assert (traza["C03-A"], traza["C03-B"]) == (OK, OK), traza
    assert traza["segundo_bloqueado"] is True, traza
    assert _actores(owner, emp) == 1
    assert m.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'actores_financieros' "
                        "AND registro_id = %s", (m.actor_de(owner, emp),))[0] == 1
    assert m.pendiente(cli, emp).json()["te_debe"] == "30.00"


# ------------------------------------------------------------------ C2
@pytest.mark.parametrize("orden", ORDENES)
def test_c2_c03_frente_a_deshabilitar_el_tercero(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _ = t
    emp = c.tercero(cli, "Empresa")
    cuerpo = c.cuerpo(cta, emp, "10.00")
    traza = correr(monkeypatch, caplog, "c2_c03_vs_desactivar", orden,
                   ("C03", c03(owner, cuerpo), _pt_actor()),
                   ("DESACTIVAR", desactivar_tercero(owner, emp), _pt_tercero()))
    assert traza["segundo_bloqueado"] is True, traza
    if orden == "A-primero":
        assert (traza["C03"], traza["DESACTIVAR"], _hecho(owner, cuerpo), _actores(owner, emp)) == (OK, OK, 1, 1), traza
    else:
        assert (traza["C03"], traza["DESACTIVAR"], _hecho(owner, cuerpo), _actores(owner, emp)) == (
            "TERCERO_NO_DISPONIBLE", OK, 0, 0), traza
    assert m.uno(owner, "SELECT enabled FROM gapto.terceros WHERE id = %s", (emp,))[0] is False


# ------------------------------------------------------------------ C3
@pytest.mark.parametrize("orden", ORDENES)
def test_c3_c03_frente_a_cambiar_la_naturaleza(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _ = t
    emp = c.tercero(cli, "Empresa")
    cuerpo = c.cuerpo(cta, emp, "10.00")
    traza = correr(monkeypatch, caplog, "c3_c03_vs_naturaleza", orden,
                   ("C03", c03(owner, cuerpo), _pt_actor()),
                   ("EDITAR", editar_naturaleza(owner, emp, "ORGANISMO"), _pt_tercero()))
    assert traza["segundo_bloqueado"] is True, traza
    if orden == "A-primero":
        assert (traza["C03"], traza["EDITAR"], _hecho(owner, cuerpo), _actores(owner, emp)) == (OK, OK, 1, 1), traza
    else:
        assert (traza["C03"], traza["EDITAR"], _hecho(owner, cuerpo), _actores(owner, emp)) == (
            "NATURALEZA_NO_ADMITIDA_EN_REEMBOLSO", OK, 0, 0), traza


# ------------------------------------------------------------------ C4
@pytest.mark.parametrize("orden", ORDENES)
@pytest.mark.parametrize("via", ["anular_duplicado", "op03_motor"])
def test_c4_cobro_frente_a_anulacion(t, monkeypatch, caplog, orden, via):
    owner, _, cli, cta, _ = t
    emp = c.tercero(cli, "Empresa")
    cuerpo = c.cuerpo(cta, emp, "40.00")
    entidad = uuid.UUID(c.registrar(cli, cuerpo).json()["posiciones"][0]["entidad_id"])
    hecho = uuid.UUID(cuerpo["intencion_id"])
    if via == "anular_duplicado":
        anulacion, pausa = anular_duplicado(owner, cli, hecho), (eja, "con_posiciones")
    else:
        anulacion, pausa = anular_op03(owner, hecho), _pt_posiciones()
    traza = correr(monkeypatch, caplog, f"c4_cobro_vs_{via}", orden,
                   ("ANULAR", anulacion, pausa), ("COBRO", cobro(owner, entidad, cta, "10.00"), _pt_posiciones()))
    assert (traza["ANULAR"], traza["COBRO"]) == ("HECHO_CON_REALIDAD_ASOCIADA", OK), traza
    assert m.uno(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0] == "ACTIVO"
    assert m.pendiente(cli, emp).json()["te_debe"] == "30.00"


# ------------------------------------------------------------------ C5
@pytest.mark.parametrize("orden", ORDENES)
def test_c5_cobro_frente_a_otro_cobro(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _ = t
    emp = c.tercero(cli, "Empresa")
    entidad = uuid.UUID(c.registrar(cli, c.cuerpo(cta, emp, "40.00")).json()["posiciones"][0]["entidad_id"])
    traza = correr(monkeypatch, caplog, "c5_cobro_vs_cobro", orden,
                   ("COBRO-A", cobro(owner, entidad, cta, "30.00"), _pt_posiciones()),
                   ("COBRO-B", cobro(owner, entidad, cta, "30.00"), _pt_posiciones()))
    assert traza["segundo_bloqueado"] is True, traza
    primero, segundo = traza["orden"]
    assert traza[primero] == OK and traza[segundo] == "EXCEDE_SALDO_DEL_DERECHO", traza
    assert m.pendiente(cli, emp).json()["te_debe"] == "10.00"  # nunca por debajo de cero


# ------------------------------------------------------------------ C6 orden de locks (§66.A.5)
def _sondear(owner, raiz, recursos: dict, pid: int) -> dict:
    estado: dict = {}
    with psycopg.connect(h.dsn()) as cn:
        estado["raiz"] = "LIBRE" if cn.execute(ADVISORY_RAIZ, (str(raiz),)).fetchone()[0] else "RETENIDO"
        cn.rollback()
        estado["inversiones"] = "LIBRE" if cn.execute(ADVISORY_INV, (str(owner),)).fetchone()[0] else "RETENIDO"
        cn.rollback()
        for nombre, (tabla, ident) in recursos.items():
            try:
                cn.execute(f"SELECT 1 FROM gapto.{tabla} WHERE id = %s FOR UPDATE NOWAIT", (ident,))
                estado[nombre] = "LIBRE"
            except psycopg.errors.LockNotAvailable:
                estado[nombre] = "RETENIDO"
            cn.rollback()
        estado["pg_locks"] = [list(f) for f in cn.execute(
            "SELECT locktype, relation::regclass::text, mode, granted FROM pg_locks WHERE pid = %s "
            "ORDER BY locktype, relation::regclass::text, mode", (pid,)).fetchall()]
    return estado


def test_c6_orden_de_locks_c03(t, monkeypatch):
    owner, _, cli, cta, _ = t
    emp, comercio = c.tercero(cli, "Empresa"), c.tercero(cli, "Comercio")
    primero, segundo = sorted([("contraparte", emp), ("comercio", comercio)], key=lambda p: str(p[1]))
    cuerpo = c.cuerpo(cta, emp, "10.00", comercio=comercio)
    raiz = uuid.UUID(cuerpo["intencion_id"])
    pausa_tercero = {"contraparte": (actores, "validar_tercero_reembolso"), "comercio": (ejr, "validar_tercero")}
    pausas = [("P1", ejr.repo_comp, "tomar_advisory_raiz"), ("P2", ejr, "tomar_inversiones"),
              ("P3", ejr, "bloquear_cuentas"), ("P4", *pausa_tercero[primero[0]]),
              ("P5", *pausa_tercero[segundo[0]]), ("P6", actores, "actor_de_tercero")]
    hilo = "C03-orden"
    puntos = [(e, PausaEn(monkeypatch, mod, attr, hilo)) for e, mod, attr in pausas]
    salida: dict = {}

    def cuerpo_hilo():
        try:
            salida["resultado"] = c03(owner, cuerpo)()
        except Exception as exc:  # pragma: no cover - se registra
            salida["error"] = repr(exc)

    hebra = threading.Thread(target=cuerpo_hilo, name=hilo, daemon=True)
    hebra.start()
    recursos = {"cuenta": ("cuentas", cta), primero[0]: ("terceros", primero[1]), segundo[0]: ("terceros", segundo[1])}
    trazas = []
    for etiqueta, punto in puntos:
        assert punto.llego.wait(30), f"no se alcanzo la pausa {etiqueta}"
        trazas.append({"pausa": etiqueta, **_sondear(owner, raiz, recursos, punto.pid)})
        punto.sigue.set()
    hebra.join(60)
    evidencia("c6_orden_locks", trazas)
    assert not hebra.is_alive() and "error" not in salida, salida
    assert not isinstance(getattr(salida["resultado"], "codigo", None), str), salida
    orden = ["raiz", "inversiones", "cuenta", primero[0], segundo[0]]
    previos = 0
    for paso in trazas:
        retenidos = [r for r in orden if paso[r] == "RETENIDO"]
        assert retenidos == orden[:len(retenidos)], (paso["pausa"], retenidos, trazas)
        assert len(retenidos) >= previos, trazas
        previos = len(retenidos)
    # Cada pausa anade exactamente su recurso; el writer llega con todo retenido.
    assert [len([r for r in orden if p[r] == "RETENIDO"]) for p in trazas] == [1, 2, 3, 4, 5, 5], trazas
