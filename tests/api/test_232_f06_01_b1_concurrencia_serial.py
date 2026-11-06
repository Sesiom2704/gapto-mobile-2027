# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_232_f06_01_b1_concurrencia_serial.py
# Ruta: tests/api/test_232_f06_01_b1_concurrencia_serial.py
# Descripcion: F06-01 B1 · Propiedad (N1; mandato del lote 12, Parte B.4).
#   Bateria SERIAL y determinista con COMMIT real, FUERA de la suite
#   general: solo con GAPTO_B1_CONCURRENCIA=1 (base desechable). Si
#   GAPTO_B1_EVIDENCIA apunta a una carpeta, cada escenario deja su JSON.
#   Tecnica de M3 (test_200, reutilizada sin cambios): el primer paso se
#   detiene DENTRO de su transaccion en un punto fijo, ya con sus locks; con
#   el retenido se lanza el segundo; ambos ordenes, un resultado esperado por
#   orden y oraculo de estado final. Oraculos comunes: nadie colgado, 0
#   reintentos 40P01 y 0 deadlocks nuevos.
#     K1 dos altas simultaneas con la MISMA intencion y un cotitular nuevo:
#        una crea, la otra es replay (idempotente); una entidad, un actor, una
#        auditoria CREAR;
#     K2 cambio de titularidad frente a valoracion (misma version vista): el
#        segundo espera en la entidad (nivel 2) y sale VERSION_DESFASADA;
#     K3 dos cambios de titularidad: uno OK y el otro VERSION_DESFASADA;
#     K4 orden de locks (prueba POSITIVA, v0.8 §1.4): con el writer retenido
#        tras el nivel 2, la entidad esta bloqueada y NO hay advisory
#        (ni INVERSIONES ni raiz de OP-22): B1 empieza en el nivel 2.
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import logging
import os
import pathlib
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f06_01_b1_helpers as b
import vs01_api_helpers as h
from app.core.contexto import ContextoOperacion
from app.propiedades import repositorio as repo_prop
from app.propiedades import servicio as serv
from test_200_f05_06_m3_concurrencia_serial import Pausa, Paso, bloqueados, deadlocks, esperar, reintentos

D = decimal.Decimal
LOGGER = "gapto.motor.transaccion"
ORDENES = ["A-primero", "B-primero"]
OK = "OK"
RELOJ = lambda: dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)  # noqa: E731

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_B1_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_B1_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B1_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def correr(monkeypatch, caplog, nombre: str, orden: str, a: tuple, b_: tuple) -> tuple[dict, dict]:
    """Como test_200.correr, con la evidencia de este bloque; devuelve tambien los pasos por nombre."""
    primero, segundo = (a, b_) if orden == "A-primero" else (b_, a)
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
                  "deadlocks_delta": deadlocks(dsn) - antes,
                  "primero": primero[0], "segundo": segundo[0]})
    evidencia(f"{nombre}_{orden}", traza)
    assert traza["primero_retenido"], traza
    assert traza["vivos"] == [] and traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    return traza, {p1.name: p1, p2.name: p2}


def ejecutar(owner, intencion_id, operacion):
    ctx = ContextoOperacion.de_usuario(owner, request_id=intencion_id)
    return fh.unidad().ejecutar(ctx, operacion, nombre="test B1 concurrencia")


def alta(owner, intencion_id, tercero_id):
    partes = [serv.Parte(yo=True, tercero_id=None, porcentaje=D("50")),
              serv.Parte(yo=False, tercero_id=tercero_id, porcentaje=D("50"))]
    return lambda: ejecutar(owner, intencion_id, lambda s: serv.alta(
        s, entidad_id=intencion_id, nombre="Piso concurrente", datos={"tipo_propiedad": "VIVIENDA"},
        modo="COMPARTIDA", desde=dt.date(2026, 1, 1), partes=partes, reloj=RELOJ))


def titularidad(owner, pid, version, vista, desde: dt.date, partes=None, modo="SOLO_MIA"):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.cambiar_titularidad(
        s, entidad_id=pid, intencion_id=i, row_version=version, modo=modo, desde=desde, partes=partes,
        vista_cliente=vista, reloj=RELOJ))


def valoracion(owner, pid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.alta_valoracion(
        s, propiedad_id=pid, valoracion_id=i, row_version=version, valor_total=D("250000"),
        fecha=dt.date(2026, 9, 1), metodo="MERCADO", fuente=None, notas=None, reloj=RELOJ))


def _pt_bloquear():
    return repo_prop, "bloquear"


def _pt_insertar():
    return repo_prop, "insertar_propiedad"


@pytest.fixture()
def t():
    owner, actor, cli = b.entorno()
    return owner, actor, cli


def _propiedad(cli):
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01")))
    vista = [(uuid.UUID(x["actor_id"]), D(x["porcentaje"])) for x in p["titularidad"]["partes"]]
    return uuid.UUID(p["id"]), vista


def _uno(owner, sql, params=()):
    return h.leer(owner, sql, params)[0][0]


# ------------------------------------------------------------------ K1
@pytest.mark.parametrize("orden", ORDENES)
def test_k1_dos_altas_misma_intencion(t, monkeypatch, caplog, orden):
    owner, _, cli = t
    ana = b.tercero(cli, "Ana nueva")
    i = uuid.uuid4()
    traza, pasos = correr(monkeypatch, caplog, "k1_dos_altas_misma_intencion", orden,
                          ("ALTA-A", alta(owner, i, ana), _pt_insertar()),
                          ("ALTA-B", alta(owner, i, ana), _pt_insertar()))
    assert (traza["ALTA-A"], traza["ALTA-B"]) == (OK, OK), traza
    assert traza["segundo_bloqueado"] is True, traza
    assert pasos[traza["primero"]].resultado.idempotente is False
    assert pasos[traza["segundo"]].resultado.idempotente is True
    assert _uno(owner, "SELECT count(*) FROM gapto.entidades WHERE id = %s", (i,)) == 1
    assert _uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (ana,)) == 1
    assert _uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s", (i,)) == 1
    assert _uno(owner, "SELECT count(*) FROM gapto.entidad_participaciones WHERE entidad_id = %s", (i,)) == 2


# ------------------------------------------------------------------ K2
@pytest.mark.parametrize("orden", ORDENES)
def test_k2_titularidad_frente_a_valoracion(t, monkeypatch, caplog, orden):
    owner, _, cli = t
    pid, vista = _propiedad(cli)
    traza, _ = correr(monkeypatch, caplog, "k2_titularidad_frente_a_valoracion", orden,
                      ("TITULARIDAD", titularidad(owner, pid, 1, vista, dt.date(2026, 12, 1)), _pt_bloquear()),
                      ("VALORACION", valoracion(owner, pid, 1), _pt_bloquear()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza[traza["primero"]], traza[traza["segundo"]]) == (OK, "VERSION_DESFASADA"), traza
    assert _uno(owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (pid,)) == 2
    valoraciones = _uno(owner, "SELECT count(*) FROM gapto.propiedad_valoraciones WHERE propiedad_entidad_id = %s",
                        (pid,))
    filas = _uno(owner, "SELECT count(*) FROM gapto.entidad_participaciones WHERE entidad_id = %s", (pid,))
    assert (valoraciones, filas) == ((1, 1) if traza["primero"] == "VALORACION" else (0, 2))


# ------------------------------------------------------------------ K3
@pytest.mark.parametrize("orden", ORDENES)
def test_k3_dos_cambios_de_titularidad(t, monkeypatch, caplog, orden):
    owner, _, cli = t
    pid, vista = _propiedad(cli)
    ana = b.tercero(cli, "Ana")
    partes = [serv.Parte(yo=True, tercero_id=None, porcentaje=D("50")),
              serv.Parte(yo=False, tercero_id=ana, porcentaje=D("50"))]
    traza, _ = correr(monkeypatch, caplog, "k3_dos_cambios_de_titularidad", orden,
                      ("CAMBIO-A", titularidad(owner, pid, 1, vista, dt.date(2026, 10, 10), partes, "COMPARTIDA"),
                       _pt_bloquear()),
                      ("CAMBIO-B", titularidad(owner, pid, 1, vista, dt.date(2026, 12, 1)), _pt_bloquear()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza[traza["primero"]], traza[traza["segundo"]]) == (OK, "VERSION_DESFASADA"), traza
    assert _uno(owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (pid,)) == 2
    abiertas = _uno(owner, "SELECT count(*) FROM gapto.entidad_participaciones WHERE entidad_id = %s "
                           "AND vigente_hasta IS NULL", (pid,))
    assert abiertas == (2 if traza["primero"] == "CAMBIO-A" else 1)


# ------------------------------------------------------------------ K4
def _sondear(owner, pid) -> dict:
    with psycopg.connect(h.dsn(), autocommit=True) as cn:
        advisory = cn.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'").fetchone()[0]
        inversiones = cn.execute("SELECT pg_try_advisory_lock(hashtext('gapto:INVERSIONES'), hashtext(%s::text))",
                                 (str(owner),)).fetchone()[0]
        if inversiones:
            cn.execute("SELECT pg_advisory_unlock(hashtext('gapto:INVERSIONES'), hashtext(%s::text))", (str(owner),))
        try:
            with cn.transaction():
                cn.execute("SET LOCAL lock_timeout = '200ms'")
                cn.execute("SELECT 1 FROM gapto.entidades WHERE id = %s FOR UPDATE NOWAIT", (pid,))
            entidad_bloqueada = False
        except psycopg.errors.LockNotAvailable:
            entidad_bloqueada = True
    return {"advisory": advisory, "inversiones_libre": inversiones, "entidad_bloqueada": entidad_bloqueada}


@pytest.mark.parametrize("escritor", ["titularidad", "valoracion"])
def test_k4_orden_de_locks_empieza_en_el_nivel_2(t, monkeypatch, escritor):
    owner, _, cli = t
    pid, vista = _propiedad(cli)
    pausa = Pausa(monkeypatch, *_pt_bloquear(), hilo="ESCRITOR")
    fn = titularidad(owner, pid, 1, vista, dt.date(2026, 12, 1)) if escritor == "titularidad" \
        else valoracion(owner, pid, 1)
    paso = Paso("ESCRITOR", fn)
    try:
        paso.start()
        assert pausa.llego.wait(30)
        estado = _sondear(owner, pid)
    finally:
        pausa.sigue.set()
        paso.join(60)
    evidencia(f"k4_orden_locks_{escritor}", estado)
    assert estado == {"advisory": 0, "inversiones_libre": True, "entidad_bloqueada": True}, estado
    assert paso.codigo == OK


def test_k4_alta_sin_advisory(t, monkeypatch):
    owner, _, cli = t
    ana = b.tercero(cli, "Ana")
    i = uuid.uuid4()
    pausa = Pausa(monkeypatch, *_pt_insertar(), hilo="ALTA")
    paso = Paso("ALTA", alta(owner, i, ana))
    try:
        paso.start()
        assert pausa.llego.wait(30)
        with psycopg.connect(h.dsn(), autocommit=True) as cn:
            advisory = cn.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'").fetchone()[0]
    finally:
        pausa.sigue.set()
        paso.join(60)
    evidencia("k4_orden_locks_alta", {"advisory": advisory})
    assert advisory == 0 and paso.codigo == OK
