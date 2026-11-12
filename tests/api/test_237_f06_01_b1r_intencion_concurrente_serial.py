# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_237_f06_01_b1r_intencion_concurrente_serial.py
# Ruta: tests/api/test_237_f06_01_b1r_intencion_concurrente_serial.py
# Descripcion: F06 T1-F06 · subhito B2·R-B1 (reapertura acotada de B1, F06-D009; R1 v0.9.5 §I.5.3-§I.5.5;
#   oraculos v0.7 §A.10.1-§A.10.2). Bateria SERIAL y determinista con COMMIT real, FUERA de la suite general:
#   solo con GAPTO_B1_CONCURRENCIA=1 (base desechable). Si GAPTO_B1_EVIDENCIA apunta a una carpeta, cada caso
#   deja su JSON (resultado, pg_locks y deadlocks).
#     - S20 (O11.19): misma intencion_id en dos writers de la Parte I sobre propiedades DISTINTAS, en vuelo a la
#       vez. Nueve pares. Barrera POSTERIOR a la lectura de la identidad: una conexion de control retiene una
#       fila que el writer solo pide despues de su _replay (propiedades FOR UPDATE para editar, valoracion y
#       C-PROP-05; terceros FOR UPDATE para alta y titularidad), asi que sin 0P las dos leerian la ausencia de
#       la intencion. Con el 0P: una sola ejecucion, la otra espera en el advisory y responde
#       IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin escribir (row_version intacta, una auditoria de la raiz con
#       ese request_id) y 0 deadlocks nuevos.
#       El par C-PROP-02 || C-PROP-05 usa un DOBLE de C-PROP-05 definido en este test (la funcion unica del 0P
#       importada de servicio.py -> NK -> lectura de la auditoria -> escritura y auditoria de la raiz), porque
#       C-PROP-05 es de B2 y el subhito va sin codigo de B2 (§I.5.5 punto 1). Con C-PROP-05 real, el par se
#       repite en el gate de B2 (mandato §7.2).
#     - O11.20 / O11.23: el PRIMER lock concedido de C-PROP-01..04 es el advisory gapto:INTENCION con su clave:
#       retenido el writer justo despues de la funcion del 0P, su backend no tiene ningun otro lock que el
#       advisory (ni relaciones ni tuplas), y no hay otro advisory.
#     - O11.21: C-PROP-02 (editar P) || C-PROP-04 (valoracion de P) con la MISMA intencion y barrera NK en P:
#       con el 0P primero no hay ciclo (0 deadlocks, una ejecucion). El mutante M-IP-09 (0P despues del NK en
#       editar), aplicado por el arnes scripts/mutantes/f06_01_b1.py, crea el ciclo y PostgreSQL aborta una
#       transaccion con 40P01: este test cae.
#     - B1-M30 (discriminante, §I.5.5 punto 4 via (2)): con la funcion del 0P sustituida por un doble SIN
#       advisory en el propio test, dos altas con la misma intencion llegan a la PK y la segunda reconoce el
#       replay tras el 23505 (idempotente). Es la rama que protege B1-M30.
# Version: 0.1.0 (F06 T1-F06 B2·R-B1, F06-D009)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import threading
import time
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import conninfo

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import vs01_api_helpers as h
from app.api.app import create_app
from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.propiedades import repositorio as repo
from app.propiedades import servicio as serv
from app.repositories import auditoria_repository as auditoria

D = decimal.Decimal
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
RELOJ = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_B1_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_B1_CONCURRENCIA=1)")


# ------------------------------------------------------------------ utilidades
def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B1_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _dsn(nombre: str) -> str:
    partes = conninfo.conninfo_to_dict(h.dsn())
    partes["application_name"] = nombre
    return conninfo.make_conninfo(**partes)


def cliente(owner, nombre: str) -> TestClient:
    cfg = h.configuracion(owner, GAPTO_DATABASE_URL=_dsn(nombre))
    return TestClient(create_app(cfg, reloj=x5.reloj(b.RELOJ)), raise_server_exceptions=False)


def unidad(nombre: str) -> UnidadDeTrabajo:
    @contextmanager
    def _abrir():
        with psycopg.connect(_dsn(nombre)) as conexion:
            yield conexion
    return UnidadDeTrabajo(_abrir, rol_runtime="gapto_runtime")


class Retener:
    """Conexion de control (superusuario, solo para el arnes) que retiene una fila con FOR UPDATE."""

    def __init__(self, sql: str, param):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        assert self.c.execute(sql, (param,)).fetchone() is not None

    def soltar(self):
        self.c.commit()
        self.c.close()


def _ret_propiedad(pid):
    return Retener("SELECT 1 FROM gapto.propiedades WHERE entidad_id = %s FOR UPDATE", pid)


def _ret_tercero(tid):
    return Retener("SELECT 1 FROM gapto.terceros WHERE id = %s FOR UPDATE", tid)


class BarreraNK:
    """Conexion de control que retiene la entidad en NK hasta `soltar`."""

    def __init__(self, entidad_id):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        self.c.execute("SELECT 1 FROM gapto.entidades WHERE id = %s FOR NO KEY UPDATE", (entidad_id,))

    def soltar(self):
        self.c.commit()
        self.c.close()


def en_hilo(fn) -> tuple[threading.Thread, dict]:
    salida: dict = {}

    def correr():
        try:
            salida["r"] = fn()
        except Exception as e:  # pragma: no cover - se registra en el resultado
            salida["e"] = repr(e)
    t = threading.Thread(target=correr, daemon=True)
    t.start()
    return t, salida


def esperar_bloqueado(nombre: str, limite: float = 20.0) -> None:
    fin = time.monotonic() + limite
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        while time.monotonic() < fin:
            if c.execute("SELECT 1 FROM pg_stat_activity WHERE application_name = %s AND wait_event_type = 'Lock'",
                         (nombre,)).fetchone():
                return
            time.sleep(0.05)
    raise AssertionError(f"{nombre} no llego a la barrera")


def deadlocks() -> int:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


def foto_locks() -> list:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        return [list(f) for f in c.execute(
            "SELECT a.application_name, l.locktype, l.mode, l.granted, l.relation::regclass::text, "
            "l.classid::bigint, l.objid::bigint, a.wait_event_type FROM pg_locks l "
            "JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.datname = current_database() "
            "AND a.application_name LIKE 'b1r_%%' AND l.locktype IN ('tuple', 'transactionid', 'advisory') "
            "ORDER BY 1, 2, 3").fetchall()]


def clave_0p(owner, intencion) -> tuple[int, int]:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        return c.execute("SELECT (hashtext('gapto:INTENCION')::bigint + 4294967296) %% 4294967296, "
                         "(hashtext(%s::text || ':' || %s::text)::bigint + 4294967296) %% 4294967296",
                         (str(owner), str(intencion))).fetchone()


def auditorias_raiz(owner, i) -> list:
    return h.leer(owner, "SELECT registro_id::text, motivo FROM gapto.auditoria WHERE request_id = %s "
                         "AND tabla = 'entidades' ORDER BY created_at", (i,))


# ------------------------------------------------------------------ doble de C-PROP-05 (solo este test)
MOTIVO_DOBLE = "test_237: doble de C-PROP-05 (B2) para el par C-PROP-02 || C-PROP-05"


def doble_cprop05(sesion, pid: uuid.UUID, i: uuid.UUID, row_version: int):
    """0P con la funcion UNICA de B1 -> NK -> identidad por la auditoria -> escritura -> auditoria de la raiz."""
    serv.bloquear_intencion_propiedad(sesion, i)
    raiz = repo.bloquear(sesion, pid)
    assert raiz is not None
    if repo.auditorias_de_intencion(sesion, i):
        return serv.Rechazo(serv.IDENTIDAD_REUTILIZADA)
    if raiz["row_version"] != row_version:
        return serv.Rechazo(serv.VERSION_DESFASADA)
    sesion.uno("SELECT 1 FROM gapto.propiedades WHERE entidad_id = %s FOR UPDATE", (pid,))
    antes = repo.snapshot(sesion, pid)
    repo.subir_version(sesion, pid)
    despues = json.loads(repo.snapshot(sesion, pid))
    despues["intencion"] = {"operacion": "COMPLETITUD", "contenido": {"propiedad_id": str(pid)}}
    auditoria.registrar(sesion, tabla="entidades", registro_id=pid, accion=auditoria.ACCION_ACTUALIZAR,
                        datos_antes_json=antes, datos_despues_json=json.dumps(despues), motivo=MOTIVO_DOBLE)
    return serv.Resultado(propiedad={})


# ------------------------------------------------------------------ S20 (O11.19)
@pytest.fixture()
def escenario():
    owner, _, cli = b.entorno()
    ana = b.tercero(cli, "Ana")
    p1 = b.crear(cli, b.alta(b.compartida([b.yo("60"), b.de(ana, "40")]), fecha_adquisicion="2026-01-01"))["id"]
    p2 = b.crear(cli, b.alta(b.solo_mia(), nombre="Garaje", fecha_adquisicion="2026-01-01"))["id"]
    t1 = b.tercero(cli, "Tania")
    t2 = b.tercero(cli, "Luis")
    return {"owner": owner, "cli": cli, "p1": p1, "p2": p2, "t1": t1, "t2": t2}


def _op(e: dict, nombre_cli: str, tipo: str, pid, i: uuid.UUID):
    """(funcion que ejecuta y devuelve (status, codigo, idempotente), retencion posterior a la identidad)."""
    cli, t1, t2 = cliente(e["owner"], nombre_cli), e["t1"], e["t2"]

    def http(ruta, cuerpo):
        def fn():
            r = b.post(cli, ruta, cuerpo)
            j = r.json()
            return r.status_code, j.get("codigo"), j.get("idempotente")
        return fn
    if tipo == "C-PROP-01":  # alta: la intencion es el id de la entidad nueva
        cuerpo = b.alta(b.compartida([b.yo("50"), b.de(t1, "50")]), intencion_id=i, nombre="Trastero",
                        fecha_adquisicion="2026-01-01")
        return http("/v1/propiedades", cuerpo), lambda: _ret_tercero(t1)
    prop = b.leer(e["cli"], pid)
    rv = prop["row_version"]
    if tipo == "C-PROP-02":
        return (http(f"/v1/propiedades/{pid}/editar", {"intencion_id": str(i), "row_version_esperada": rv,
                                                        "notas": "x"}), lambda: _ret_propiedad(pid))
    if tipo in ("C-PROP-03", "C-PROP-03-otros"):
        tit = b.compartida([b.yo("50"), b.de(t1, "50")], desde="2026-11-01") if tipo == "C-PROP-03" else \
            {"modo": "DE_OTROS", "desde": "2026-11-01", "partes": [b.de(t2, "100")]}
        tid = t1 if tipo == "C-PROP-03" else t2
        return http(f"/v1/propiedades/{pid}/titularidad", b.cambio(prop, tit, intencion_id=i)), \
            lambda: _ret_tercero(tid)
    if tipo == "C-PROP-04":
        return (http(f"/v1/propiedades/{pid}/valoraciones", b.valoracion(prop, intencion_id=i)),
                lambda: _ret_propiedad(pid))
    if tipo == "C-PROP-05-doble":
        u = unidad(nombre_cli)

        def fn():
            ctx = ContextoOperacion.de_usuario(e["owner"], request_id=i)
            r = u.ejecutar(ctx, lambda s: doble_cprop05(s, uuid.UUID(pid), i, rv), nombre="test_237 doble C-PROP-05")
            return (409, r.codigo, None) if isinstance(r, serv.Rechazo) else (200, None, False)
        return fn, lambda: _ret_propiedad(pid)
    raise AssertionError(tipo)


PARES = [
    ("C-PROP-02", "C-PROP-02"),
    ("C-PROP-03", "C-PROP-03-otros"),    # titularidad con actores disjuntos
    ("C-PROP-03", "C-PROP-03"),          # titularidad con un actor comun
    ("C-PROP-02", "C-PROP-03-otros"),
    ("C-PROP-04", "C-PROP-02"),
    ("C-PROP-04", "C-PROP-04"),
    ("C-PROP-01", "C-PROP-02"),
    ("C-PROP-01", "C-PROP-04"),
    ("C-PROP-02", "C-PROP-05-doble"),    # G3 (R-R1V093-02); con C-PROP-05 real en el gate de B2
]


@pytest.mark.parametrize("par", PARES, ids=[f"{a}__{b_}" for a, b_ in PARES])
def test_s20_o11_19_misma_intencion_en_dos_propiedades(escenario, par):
    e = escenario
    i = uuid.uuid4()
    tipo_a, tipo_b = par
    fa, ret_a = _op(e, "b1r_A", tipo_a, e["p1"], i)
    fb, ret_b = _op(e, "b1r_B", tipo_b, e["p2"], i)
    rv_antes = (b.leer(e["cli"], e["p1"])["row_version"], b.leer(e["cli"], e["p2"])["row_version"])
    d0 = deadlocks()
    retenciones = [ret_a()]
    if not (tipo_a == tipo_b == "C-PROP-03"):   # con el actor comun, la misma fila de tercero retiene a las dos
        retenciones.append(ret_b())
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado("b1r_A")
        tb, rb = en_hilo(fb)
        esperar_bloqueado("b1r_B")
        locks = foto_locks()
    finally:
        for r in retenciones:
            r.soltar()
    ta.join(60)
    tb.join(60)
    rv_despues = (b.leer(e["cli"], e["p1"])["row_version"], b.leer(e["cli"], e["p2"])["row_version"])
    auds = auditorias_raiz(e["owner"], i)
    resultado = {"par": par, "intencion": str(i), "A": ra.get("r") or ra.get("e"), "B": rb.get("r") or rb.get("e"),
                 "vivos": [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()],
                 "auditorias_raiz_request_id": auds, "row_version_antes": rv_antes, "row_version_despues": rv_despues,
                 "deadlocks_nuevos": deadlocks() - d0, "pg_locks_en_espera": [f for f in locks if not f[3]],
                 "pg_locks": locks}
    ejecuciones = sum(1 for r in (resultado["A"], resultado["B"])
                      if isinstance(r, tuple) and r[0] == 200 and not r[2])
    resultado["ejecuciones"] = ejecuciones
    evidencia(f"S20_{tipo_a}__{tipo_b}", resultado)
    assert resultado["vivos"] == [] and "e" not in ra and "e" not in rb, resultado
    assert resultado["deadlocks_nuevos"] == 0, resultado                      # sin 40P01
    assert ejecuciones == 1 and len(auds) == 1, resultado                     # una sola ejecucion de la intencion
    assert resultado["A"][0] == 200 and resultado["B"] == (409, REUTILIZADA, None), resultado
    assert rv_despues[1] == rv_antes[1], resultado                            # B no escribe en su propiedad
    k1, _ = clave_0p(e["owner"], i)
    assert any(f[0] == "b1r_B" and f[1] == "advisory" and f[5] == k1 and not f[3] for f in locks), locks


# ------------------------------------------------------------------ O11.20 / O11.23
def _writer(e: dict, tipo: str, i: uuid.UUID):
    owner, pid = e["owner"], uuid.UUID(e["p1"])
    prop = b.leer(e["cli"], e["p1"])
    vista = [(uuid.UUID(x["actor_id"]), D(x["porcentaje"])) for x in prop["titularidad"]["partes"]]
    reloj = lambda: RELOJ  # noqa: E731
    if tipo == "C-PROP-01":
        return lambda s: serv.alta(s, entidad_id=i, nombre="Piso O11.23", datos={"tipo_propiedad": "VIVIENDA"},
                                   modo="SOLO_MIA", desde=dt.date(2026, 1, 1), partes=None, reloj=reloj)
    if tipo == "C-PROP-02":
        return lambda s: serv.editar(s, entidad_id=pid, intencion_id=i, row_version=prop["row_version"],
                                     campos={"notas": "O11.23"}, reloj=reloj)
    if tipo == "C-PROP-03":
        return lambda s: serv.cambiar_titularidad(s, entidad_id=pid, intencion_id=i, row_version=prop["row_version"],
                                                  modo="SOLO_MIA", desde=dt.date(2026, 12, 1), partes=None,
                                                  vista_cliente=vista, reloj=reloj)
    return lambda s: serv.alta_valoracion(s, propiedad_id=pid, valoracion_id=i, row_version=prop["row_version"],
                                          valor_total=D("250000"), fecha=dt.date(2026, 9, 1), metodo="MERCADO",
                                          fuente=None, notas=None, reloj=reloj)


@pytest.mark.parametrize("tipo", ["C-PROP-01", "C-PROP-02", "C-PROP-03", "C-PROP-04"])
def test_o11_20_o11_23_primer_lock_es_el_0p(escenario, monkeypatch, tipo):
    e = escenario
    i = uuid.uuid4()
    llego, sigue = threading.Event(), threading.Event()
    original = serv.bloquear_intencion_propiedad

    def pausa(sesion, intencion_id):
        original(sesion, intencion_id)
        if threading.current_thread().name == "O11_23" and not llego.is_set():
            llego.set()
            sigue.wait(60)
    monkeypatch.setattr(serv, "bloquear_intencion_propiedad", pausa)
    u = unidad("b1r_O11_23")
    salida: dict = {}

    def correr():
        try:
            salida["r"] = u.ejecutar(ContextoOperacion.de_usuario(e["owner"], request_id=i), _writer(e, tipo, i),
                                     nombre="test_237 O11.23")
        except Exception as exc:  # pragma: no cover
            salida["e"] = repr(exc)
    hilo = threading.Thread(target=correr, name="O11_23", daemon=True)
    try:
        hilo.start()
        assert llego.wait(30), "el writer no llego a la funcion del 0P"
        with psycopg.connect(h.dsn(), autocommit=True) as c:
            locks = [list(f) for f in c.execute(
                "SELECT l.locktype, l.mode, l.granted, l.relation::regclass::text, l.classid::bigint, l.objid::bigint "
                "FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.application_name = 'b1r_O11_23' "
                "AND l.locktype <> 'virtualxid' ORDER BY 1").fetchall()]
            todos_advisory = c.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'").fetchone()[0]
    finally:
        sigue.set()
        hilo.join(60)
    k1, k2 = clave_0p(e["owner"], i)
    resultado = {"writer": tipo, "locks_del_writer_tras_0p": locks, "advisory_en_el_cluster": todos_advisory,
                 "clave_esperada": [k1, k2], "salida": repr(salida.get("r") or salida.get("e"))}
    evidencia(f"O11_23_{tipo}", resultado)
    assert locks == [["advisory", "ExclusiveLock", True, None, k1, k2]], resultado
    assert todos_advisory == 1, resultado
    assert "e" not in salida and not isinstance(salida["r"], serv.Rechazo), resultado


# ------------------------------------------------------------------ O11.21
def test_o11_21_0p_primer_recurso_sin_ciclo_editar_y_valoracion(escenario):
    """editar(P, i) || valoracion(P, id=i) con barrera NK en P: con 0P primero, 0 deadlocks y una ejecucion."""
    e = escenario
    p = e["p1"]
    i = uuid.uuid4()
    prop = b.leer(e["cli"], p)
    ca, cb = cliente(e["owner"], "b1r_A"), cliente(e["owner"], "b1r_B")
    d0 = deadlocks()
    barrera = BarreraNK(p)
    try:
        ta, ra = en_hilo(lambda: b.post(ca, f"/v1/propiedades/{p}/editar",
                                        {"intencion_id": str(i), "row_version_esperada": prop["row_version"],
                                         "notas": "O11.21"}))
        esperar_bloqueado("b1r_A")
        tb, rb = en_hilo(lambda: b.post(cb, f"/v1/propiedades/{p}/valoraciones",
                                        b.valoracion(prop, intencion_id=i)))
        esperar_bloqueado("b1r_B")
        locks = foto_locks()
    finally:
        barrera.soltar()
    ta.join(60)
    tb.join(60)
    assert "e" not in ra and "e" not in rb, (ra, rb)
    r1, r2 = ra["r"], rb["r"]
    auds = auditorias_raiz(e["owner"], i)
    resultado = {"editar": [r1.status_code, r1.json().get("codigo")], "valoracion": [r2.status_code,
                                                                                     r2.json().get("codigo")],
                 "auditorias_raiz": auds, "deadlocks_nuevos": deadlocks() - d0,
                 "pg_locks_en_espera": [f for f in locks if not f[3]]}
    evidencia("O11_21", resultado)
    assert resultado["deadlocks_nuevos"] == 0, resultado
    assert len(auds) == 1, resultado
    assert resultado["editar"] == [200, None] and resultado["valoracion"] == [409, REUTILIZADA], resultado


# ------------------------------------------------------------------ B1-M30 (discriminante con doble del 0P)
def test_b1_m30_alta_sin_0p_replay_tras_la_pk(escenario, monkeypatch):
    """Doble SIN advisory de la funcion del 0P: la segunda alta llega a la PK y reconoce el replay (idempotente)."""
    e = escenario
    monkeypatch.setattr(serv, "bloquear_intencion_propiedad", lambda sesion, intencion_id: None)
    i = uuid.uuid4()
    llego, sigue = threading.Event(), threading.Event()
    original = repo.insertar_propiedad

    def pausa(sesion, **kw):
        original(sesion, **kw)
        if threading.current_thread().name == "ALTA-A" and not llego.is_set():
            llego.set()
            sigue.wait(60)
    monkeypatch.setattr(repo, "insertar_propiedad", pausa)
    d0 = deadlocks()
    alta = _writer(e, "C-PROP-01", i)
    res: dict = {}

    def correr(nombre):
        try:
            res[nombre] = unidad("b1r_" + nombre).ejecutar(ContextoOperacion.de_usuario(e["owner"], request_id=i),
                                                           alta, nombre="test_237 B1-M30")
        except Exception as exc:  # pragma: no cover
            res[nombre] = repr(exc)
    ha = threading.Thread(target=correr, args=("ALTA-A",), name="ALTA-A", daemon=True)
    hb = threading.Thread(target=correr, args=("ALTA-B",), name="ALTA-B", daemon=True)
    try:
        ha.start()
        assert llego.wait(30)
        hb.start()
        esperar_bloqueado("b1r_ALTA-B")   # espera en la PK (insercion de la misma clave en vuelo)
    finally:
        sigue.set()
    ha.join(60)
    hb.join(60)
    resultado = {"A": repr(res.get("ALTA-A")), "B": repr(res.get("ALTA-B")), "deadlocks_nuevos": deadlocks() - d0,
                 "auditorias_raiz": auditorias_raiz(e["owner"], i)}
    evidencia("B1_M30_sin_0p", resultado)
    assert isinstance(res["ALTA-A"], serv.Resultado) and res["ALTA-A"].idempotente is False, resultado
    assert isinstance(res["ALTA-B"], serv.Resultado) and res["ALTA-B"].idempotente is True, resultado
    assert len(resultado["auditorias_raiz"]) == 1 and resultado["deadlocks_nuevos"] == 0, resultado
