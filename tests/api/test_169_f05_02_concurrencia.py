# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_169_f05_02_concurrencia.py
# Ruta: tests/api/test_169_f05_02_concurrencia.py
# Descripcion: Serializacion por owner de los writers de preferencias
#   (F05-02 B1; F05-D026 §41.3/§41.4; CC-02-5). Interleaving forzado con
#   barrera explicita (WM 12C.1), EN SERIE y determinista: una sesion retiene
#   el advisory (PREFERENCIAS, owner); los comandos se lanzan uno a uno y
#   cada uno debe quedar ESPERANDO (pg_stat_activity) antes de lanzar el
#   siguiente; al liberar, PostgreSQL concede el advisory en orden de
#   llegada.
#     - todo writer (alta, editar, desactivar, reactivar) espera el advisory
#       y lo que espera es un lock advisory de la sesion barrera;
#     - dos altas contradictorias, en los dos ordenes: gana exactamente la
#       primera; la segunda ve la ya confirmada y responde EMPATE;
#     - alta frente a reactivacion contradictoria, en los dos ordenes;
#     - dos ediciones con la misma row_version: una aplica, la otra
#       VERSION_DESFASADA;
#     - el registro VS-01 y la propuesta NO toman el advisory (§41.4).
#   Sin el advisory (mutante de mutantes_f05_02.py) los comandos no esperan
#   la barrera y estos tests fallan.
#   No se paraleliza con nada: cada test crea su tenant y sus hilos.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import threading
import time

import psycopg
import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

EMPATE = "PREFERENCIA_EMPATE_CONTRADICTORIO"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="A")
    b = ph.cuenta(owner, actor, nombre="B")
    return owner, actor, cli, a, b


def _lanzar(salida: dict, clave: str, fn) -> threading.Thread:
    hilo = threading.Thread(target=lambda: salida.update({clave: fn()}))
    hilo.start()
    return hilo


def _bloqueados_por_advisory(pid_x: int, minimo: int, limite_s: float = 8.0) -> bool:
    """True si al menos `minimo` sesiones de esta base estan bloqueadas por
    `pid_x` esperando un lock advisory no concedido."""
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            n = mon.execute(
                "SELECT count(*) FROM pg_stat_activity a WHERE a.datname = current_database() "
                "AND %s = ANY(pg_blocking_pids(a.pid)) AND EXISTS (SELECT 1 FROM pg_locks l "
                "WHERE l.pid = a.pid AND l.locktype = 'advisory' AND NOT l.granted)",
                (pid_x,),
            ).fetchone()[0]
            if n >= minimo:
                return True
            time.sleep(0.05)
    return False


def _barrera(owner, pasos: list) -> dict:
    """Retiene el advisory, lanza los pasos EN ORDEN (cada uno debe quedar
    bloqueado por la barrera antes de lanzar el siguiente) y libera."""
    salida: dict = {}
    x = ph.retener_advisory(owner)
    hilos = []
    try:
        pid_x = fh.pid_servidor(x)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilos.append(_lanzar(salida, clave, fn))
            assert _bloqueados_por_advisory(pid_x, n), f"{clave} no espero el advisory (PREFERENCIAS, owner)"
        assert not salida, "algun comando termino sin esperar el advisory"
        x.execute("COMMIT")
    finally:
        x.close()
    for hilo in hilos:
        hilo.join(timeout=20)
        assert not hilo.is_alive()
    return salida


def _codigo(r):
    return r.json().get("codigo")


# ------------------------------------------------------------------ todo writer espera
@pytest.mark.parametrize("comando", ["alta", "editar", "desactivar", "reactivar"])
def test_todo_writer_espera_el_advisory(t, comando):
    owner, _, cli, a, b = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    if comando == "reactivar":
        assert ph.desactivar(cli, pid, 1).status_code == 200
    fn = {
        "alta": lambda: ph.alta(cli, presupuestable_default=True)[1],
        "editar": lambda: ph.editar(cli, pid, 1, cuenta_default_id=b),
        "desactivar": lambda: ph.desactivar(cli, pid, 1),
        "reactivar": lambda: ph.reactivar(cli, pid, 2),
    }[comando]
    salida = _barrera(owner, [(comando, fn)])
    assert salida[comando].status_code == 200, salida[comando].text


# ------------------------------------------------------------------ altas contradictorias
@pytest.mark.parametrize("primero", ["A", "B"])
def test_dos_altas_contradictorias_gana_exactamente_la_primera(t, primero):
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Super")
    ids = {}

    def alta(cuenta, clave):
        def fn():
            pid, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=cuenta)
            ids[clave] = pid
            return r
        return fn

    orden = [("A", alta(a, "A")), ("B", alta(b, "B"))]
    if primero == "B":
        orden.reverse()
    salida = _barrera(owner, orden)
    segundo = "B" if primero == "A" else "A"
    assert salida[primero].status_code == 200, salida[primero].text
    assert salida[segundo].status_code == 409 and _codigo(salida[segundo]) == EMPATE
    assert salida[segundo].json()["detalle"]["preferencia_conflicto_id"] == str(ids[primero])
    assert ph.n_preferencias(owner) == 1


@pytest.mark.parametrize("primero", ["alta", "reactivar"])
def test_alta_frente_a_reactivacion_contradictoria(t, primero):
    owner, _, cli, a, b = t
    vieja, _ = ph.alta(cli, cuenta_default_id=a)
    assert ph.desactivar(cli, vieja, 1).status_code == 200
    nueva = {}

    def alta():
        pid, r = ph.alta(cli, cuenta_default_id=b)
        nueva["id"] = pid
        return r

    pasos = [("alta", alta), ("reactivar", lambda: ph.reactivar(cli, vieja, 2))]
    if primero == "reactivar":
        pasos.reverse()
    salida = _barrera(owner, pasos)
    segundo = "reactivar" if primero == "alta" else "alta"
    assert salida[primero].status_code == 200, salida[primero].text
    assert salida[segundo].status_code == 409 and _codigo(salida[segundo]) == EMPATE
    habilitadas = h.leer(owner, "SELECT count(*) FROM gapto.preferencias_registro WHERE enabled")[0][0]
    assert habilitadas == 1
    if primero == "alta":
        assert ph.fila(owner, vieja)["enabled"] is False
    else:
        assert ph.fila(owner, nueva["id"]) is None


def test_dos_ediciones_con_la_misma_row_version(t):
    owner, actor, cli, a, b = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    c = ph.cuenta(owner, actor, nombre="C")
    salida = _barrera(owner, [
        ("e1", lambda: ph.editar(cli, pid, 1, cuenta_default_id=b)),
        ("e2", lambda: ph.editar(cli, pid, 1, cuenta_default_id=c)),
    ])
    assert salida["e1"].status_code == 200, salida["e1"].text
    assert salida["e2"].status_code == 409 and _codigo(salida["e2"]) == "VERSION_DESFASADA"
    f = ph.fila(owner, pid)
    assert f["cuenta_default_id"] == b and f["row_version"] == 2
    assert [m for _, m in ph.auditorias(owner, pid)] == ["F05-02 ALTA", "F05-02 EDITAR"]


# ------------------------------------------------------------------ el registro no toma el advisory
def test_el_registro_y_la_propuesta_no_toman_el_advisory(t):
    """§41.4: el registro no toma el advisory de preferencias ni relee la
    preferencia al confirmar; la propuesta es una lectura sin locks."""
    owner, _, cli, a, _ = t
    x = ph.retener_advisory(owner)
    try:
        r = ph.propuesta_http(cli, None)
        assert r.status_code == 200, r.text
        r = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(a), headers=h.AUTH)
        assert r.status_code == 200, r.text
        r = cli.get(ph.BASE, headers=h.AUTH)
        assert r.status_code == 200, r.text
    finally:
        x.execute("ROLLBACK")
        x.close()
