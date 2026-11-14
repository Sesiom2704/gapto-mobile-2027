# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_261_f06_t2_b1r_concurrencia_serial.py
# Ruta: tests/api/test_261_f06_t2_b1r_concurrencia_serial.py
# Descripcion: F06 T2-F06 · B1-R (mandato §8.2; WM §13.3.7). Bateria SERIAL y determinista con COMMIT real, FUERA
#   de la suite general: solo con GAPTO_B1_CONCURRENCIA=1 (base desechable; la base sale de GAPTO_TEST_DATABASE_URL
#   y nada mas, para poder repetirla sin cambios contra otra base, p. ej. la rama del humo de Neon del cierre del
#   tren). Barreras externas (conexion de control) que retienen el recurso del escenario; traza de pg_locks y
#   pg_stat_database.deadlocks; JSON por caso si GAPTO_B1_EVIDENCIA apunta a una carpeta. 0 x 40P01 en todos.
#     O-B1R-13  misma intencion en C-PROP-03bis sobre DOS propiedades a la vez (0P, R-R1V093-01): barrera POSTERIOR a
#               la lectura de la identidad (la fila del usuario en FOR UPDATE: la auditoria la pide en su FK); una
#               ejecucion, la otra IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin escribir.
#     O-B1R-14  C-PROP-03bis || C-PROP-03 sobre la misma propiedad, en los dos ordenes: el primero 200, el segundo
#               VERSION_DESFASADA.
#     O-B1R-18  C-PROP-03bis (FOR NO KEY UPDATE) || C-MEJ-01 (FOR SHARE) con la propuesta leida antes, en los dos
#               ordenes y en dos fechas del hecho (HT2-20): serializados; C-MEJ-01 relee la titularidad bajo lock.
#     O-B1R-27  C-PROP-03bis || C-PROP-02 (editar la adquisicion), en los dos ordenes: serializados; nunca queda la
#               adquisicion posterior al inicio ni el inicio anterior a la adquisicion.
#     O11.23    C-PROP-03bis: retenido justo despues de la funcion del 0P, su backend solo tiene el advisory.
# Version: 0.1.0 (F06 T2-F06 · B1-R N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import vs01_api_helpers as h
from app.api.app import create_app
from app.core.contexto import ContextoOperacion
from app.propiedades import servicio as serv
from test_237_f06_01_b1r_intencion_concurrente_serial import (BarreraNK, _dsn, clave_0p, deadlocks, en_hilo,
                                                              esperar_bloqueado, foto_locks, unidad)
from test_260_f06_t2_b1r_inicio_titularidad import HOY, RELOJ, RUTA, Lab

ORDENES = ["A-primero", "B-primero"]
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_B1_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_B1_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B1_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"B1R_{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                              encoding="utf-8")


def cliente(owner, nombre: str) -> TestClient:
    """Cliente de la app con application_name propio (para pg_locks) y el reloj de B1-R (HOY)."""
    cfg = h.configuracion(owner, GAPTO_DATABASE_URL=_dsn(nombre))
    return TestClient(create_app(cfg, reloj=x5.reloj(RELOJ)), raise_server_exceptions=False)


class BarreraUsuario:
    """Conexion de control que retiene la fila del usuario (FOR UPDATE): la FK de la auditoria pide FOR KEY SHARE,
    asi que el writer se para DESPUES de leer la identidad y de escribir, justo antes de auditar."""

    def __init__(self, owner):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        assert self.c.execute("SELECT 1 FROM gapto.usuarios WHERE id = %s FOR UPDATE", (owner,)).fetchone()

    def soltar(self):
        self.c.commit()
        self.c.close()


def _correr(fa, fb, barrera, nombre_a="b1r_A", nombre_b="b1r_B"):
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado(nombre_a)
        tb, rb = en_hilo(fb)
        esperar_bloqueado(nombre_b)
        locks = foto_locks()
    finally:
        barrera.soltar()
    ta.join(90)
    tb.join(90)
    vivos = [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]
    return ra, rb, {"deadlocks_nuevos": deadlocks() - d0, "vivos": vivos, "pg_locks": locks,
                    "esperas": [f for f in locks if not f[3]]}


def _http(salida: dict):
    assert "e" not in salida, salida
    r = salida["r"]
    j = r.json()
    return r.status_code, j.get("codigo"), j.get("idempotente")


def _post(cli, ruta: str, cuerpo: dict):
    return lambda: b.post(cli, ruta, cuerpo)


def _invariante(lab: Lab) -> tuple:
    """(adquisicion, inicio) tras la carrera: nunca adquisicion > inicio."""
    d = lab.detalle()
    return d["fecha_adquisicion"], d["inicio_titularidad"]["inicio"]


# ================================================================== O-B1R-13
def test_o_b1r_13_misma_intencion_en_dos_propiedades():
    lab = Lab(adquisicion=None)
    p2 = b.crear(lab.cli, b.alta(b.solo_mia("2026-11-01"), nombre="Garaje"))["id"]
    i = uuid.uuid4()
    cuerpo_1 = lab.peticion("2020-01-01", iid=i)
    d2 = b.leer(lab.cli, p2)
    cuerpo_2 = {**cuerpo_1, "row_version_esperada": d2["row_version"], "nuevo_desde": "2021-01-01",
                "inicio_visto": d2["inicio_titularidad"]["inicio"],
                "primera_version_vista": d2["inicio_titularidad"]["primera_version"]}
    rv = (lab.detalle()["row_version"], d2["row_version"])
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraUsuario(lab.owner)
    ra, rb, traza = _correr(_post(ca, RUTA.format(lab.pid), cuerpo_1), _post(cb, RUTA.format(p2), cuerpo_2), barrera)
    a, bb = _http(ra), _http(rb)
    auds = lab.sql("SELECT registro_id::text FROM gapto.auditoria WHERE request_id = %s AND tabla = 'entidades'", (i,))
    rv_despues = (lab.detalle()["row_version"], b.leer(lab.cli, p2)["row_version"])
    k1, _ = clave_0p(lab.owner, i)
    datos = {"A": a, "B": bb, "auditorias": auds, "rv_antes": rv, "rv_despues": rv_despues, **traza}
    evidencia("O13_misma_intencion_dos_propiedades", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert a == (200, None, False) and bb == (409, REUTILIZADA, None), datos
    assert auds == [(lab.pid,)] and rv_despues == (rv[0] + 1, rv[1]), datos
    assert any(f[0] == "b1r_B" and f[1] == "advisory" and f[5] == k1 and not f[3] for f in traza["pg_locks"]), datos


# ================================================================== O-B1R-14
@pytest.mark.parametrize("orden", ORDENES)
def test_o_b1r_14_corregir_inicio_frente_a_cambio_de_titularidad(orden):
    lab = Lab(adquisicion=None)
    corregir = lab.peticion("2020-01-01")
    cambio = b.cambio(lab.detalle(), b.solo_mia(desde="2026-12-01"))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_i = lambda cli: _post(cli, RUTA.format(lab.pid), corregir)                                      # noqa: E731
    f_t = lambda cli: _post(cli, f"/v1/propiedades/{lab.pid}/titularidad", cambio)                    # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":   # C-PROP-03bis primero
        ra, rb, traza = _correr(f_i(ca), f_t(cb), barrera)
        inicio, tit = _http(ra), _http(rb)
        esperado = ((200, None, False), (409, "VERSION_DESFASADA", None))
    else:
        ra, rb, traza = _correr(f_t(ca), f_i(cb), barrera)
        tit, inicio = _http(ra), _http(rb)
        esperado = ((409, "VERSION_DESFASADA", None), (200, None, False))
    filas = lab.filas()
    datos = {"orden": orden, "corregir_inicio": inicio, "cambio_titularidad": tit, "filas": filas, **traza}
    evidencia(f"O14_inicio_frente_a_cprop03_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert (inicio, tit) == esperado, datos
    if orden == "A-primero":
        assert [f[2] for f in filas] == ["2020-01-01", "2020-01-01"], datos
    else:
        assert sorted({f[2] for f in filas}) == ["2026-11-01", "2026-12-01"], datos


# ================================================================== O-B1R-18
@pytest.mark.parametrize("fecha", ["2026-05-15", HOY], ids=["periodo_corregido", "fecha_con_titularidad"])
@pytest.mark.parametrize("orden", ORDENES)
def test_o_b1r_18_corregir_inicio_frente_a_c_mej_01(orden, fecha):
    lab = Lab(adquisicion=None)
    partes = sorted(lab.detalle()["inicio_titularidad"]["primera_version"], key=lambda p: p["actor_id"])
    propuesta = {"criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": fecha, "partes": partes}
    gasto = lab.cuerpo(fecha=fecha, atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": propuesta})
    corregir = lab.peticion("2026-01-01")
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_i = lambda cli: _post(cli, RUTA.format(lab.pid), corregir)                                      # noqa: E731
    f_g = lambda cli: lambda: lab.registrar(gasto, cli)                                                # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":   # C-PROP-03bis primero: C-MEJ-01 relee bajo lock la titularidad ya corregida
        ra, rb, traza = _correr(f_i(ca), f_g(cb), barrera)
        inicio, g = _http(ra), _http(rb)
        esperado_g = (200, None, None)
    else:                      # C-MEJ-01 primero: en el periodo aun no hay titularidad
        ra, rb, traza = _correr(f_g(ca), f_i(cb), barrera)
        g, inicio = _http(ra), _http(rb)
        esperado_g = (422, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA", None) if fecha != HOY else (200, None, None)
    datos = {"orden": orden, "fecha_hecho": fecha, "corregir_inicio": inicio, "c_mej_01": g, **traza}
    evidencia(f"O18_inicio_frente_a_cmej01_{orden}_{fecha}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert inicio == (200, None, False), datos
    assert (g[0], g[1]) == esperado_g[:2], datos
    assert any(not f[3] for f in traza["pg_locks"] if f[0] in ("b1r_A", "b1r_B")), datos   # hubo espera real


# ================================================================== O-B1R-27
@pytest.mark.parametrize("orden", ORDENES)
def test_o_b1r_27_corregir_inicio_frente_a_editar_la_adquisicion(orden):
    lab = Lab(adquisicion="2015-03-10")
    v = lab.detalle()["row_version"]
    corregir = lab.peticion("2016-01-01")
    editar = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": v, "fecha_adquisicion": "2018-01-01"}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_i = lambda cli: _post(cli, RUTA.format(lab.pid), corregir)                                      # noqa: E731
    f_e = lambda cli: _post(cli, f"/v1/propiedades/{lab.pid}/editar", editar)                          # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":
        ra, rb, traza = _correr(f_i(ca), f_e(cb), barrera)
        inicio, ed = _http(ra), _http(rb)
        esperado = ((200, None, False), (409, "VERSION_DESFASADA", None), ("2015-03-10", "2016-01-01"))
    else:
        ra, rb, traza = _correr(f_e(ca), f_i(cb), barrera)
        ed, inicio = _http(ra), _http(rb)
        esperado = ((409, "VERSION_DESFASADA", None), (200, None, False), ("2018-01-01", "2026-11-01"))
    final = _invariante(lab)
    datos = {"orden": orden, "corregir_inicio": inicio, "editar": ed, "adquisicion_e_inicio": final, **traza}
    evidencia(f"O27_inicio_frente_a_cprop02_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert (inicio, ed, final) == esperado, datos
    assert final[0] <= final[1], datos


# ================================================================== O11.23 para C-PROP-03bis
def test_o11_23_corregir_inicio_primer_lock_es_el_0p(monkeypatch):
    lab = Lab(adquisicion=None)
    d = lab.detalle()
    i = uuid.uuid4()
    llego, sigue = threading.Event(), threading.Event()
    original = serv.bloquear_intencion_propiedad

    def pausa(sesion, intencion_id):
        original(sesion, intencion_id)
        if threading.current_thread().name == "O11_23_B1R" and not llego.is_set():
            llego.set()
            sigue.wait(60)
    monkeypatch.setattr(serv, "bloquear_intencion_propiedad", pausa)
    u = unidad("b1r_O11_23")
    vista = [(uuid.UUID(p["actor_id"]), Decimal(p["porcentaje"])) for p in d["inicio_titularidad"]["primera_version"]]
    salida: dict = {}

    def correr():
        try:
            salida["r"] = u.ejecutar(ContextoOperacion.de_usuario(lab.owner, request_id=i), lambda s: serv.corregir_inicio(
                s, entidad_id=uuid.UUID(lab.pid), intencion_id=i, row_version=d["row_version"],
                nuevo_desde=dt.date(2020, 1, 1), inicio_visto=dt.date(2026, 11, 1), primera_version_vista=vista,
                reloj=x5.reloj(RELOJ)), nombre="test_261 O11.23")
        except Exception as exc:  # pragma: no cover
            salida["e"] = repr(exc)
    hilo = threading.Thread(target=correr, name="O11_23_B1R", daemon=True)
    try:
        hilo.start()
        assert llego.wait(30), "el writer no llego a la funcion del 0P"
        with psycopg.connect(h.dsn(), autocommit=True) as c:
            locks = [list(f) for f in c.execute(
                "SELECT l.locktype, l.mode, l.granted, l.relation::regclass::text, l.classid::bigint, l.objid::bigint "
                "FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.application_name = 'b1r_O11_23' "
                "AND l.locktype <> 'virtualxid' ORDER BY 1").fetchall()]
    finally:
        sigue.set()
        hilo.join(60)
    k1, k2 = clave_0p(lab.owner, i)
    datos = {"locks_del_writer_tras_0p": locks, "clave_esperada": [k1, k2], "salida": repr(salida.get("r") or salida.get("e"))}
    evidencia("O11_23_corregir_inicio", datos)
    assert locks == [["advisory", "ExclusiveLock", True, None, k1, k2]], datos
    assert "e" not in salida and not isinstance(salida["r"], serv.Rechazo), datos
