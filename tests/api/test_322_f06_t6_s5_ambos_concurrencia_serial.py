# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_322_f06_t6_s5_ambos_concurrencia_serial.py
# Ruta: tests/api/test_322_f06_t6_s5_ambos_concurrencia_serial.py
# Descripcion: F06 T6 · S5 (N1): concurrencia de «Ambos», EN SERIE y determinista (patron de test_169,
#   WM 12C.1). Una barrera retiene el advisory (PREFERENCIAS, owner); dos «Ambos» sobre el MISMO tercero
#   se lanzan en orden y cada uno queda esperando el advisory antes de lanzar el siguiente; al liberar, los
#   dos terminan (sin deadlock) en el orden de la cola: el primero escribe sus dos preferencias y el segundo,
#   con valores contradictorios, se rechaza sin escribir nada (todas o ninguna). Con los mismos valores, el
#   segundo tambien escribe (no es contradictorio, §41.4).
#   Exige GAPTO_TEST_DATABASE_URL (base local DESECHABLE con la cadena aplicada).
# Version: 0.1.0 (F06 T6 · S5)
# ============================================================

from __future__ import annotations

import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

RUTA = "/v1/preferencias/ambos"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, cli, ph.tercero(owner), ph.categoria(owner, "Super"), ph.tipo_gasto(owner)


def _ambos(cli, tipo, ter, cat, presupuestable: bool):
    def ops():
        return {"operaciones": [
            {"ambito": "TERCERO", "accion": "ALTA", "id": str(uuid.uuid4()),
             "contenido": {"tipo_hecho_id": str(tipo), "tercero_id": str(ter), "presupuestable_default": presupuestable}},
            {"ambito": "CATEGORIA", "accion": "ALTA", "id": str(uuid.uuid4()),
             "contenido": {"tipo_hecho_id": str(tipo), "categoria_id": str(cat), "presupuestable_default": presupuestable}},
        ]}
    cuerpo = ops()
    return lambda: cli.post(RUTA, json=cuerpo, headers=h.AUTH)


def _bloqueados_por_advisory(pid_x: int, minimo: int, limite_s: float = 8.0) -> bool:
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


def _en_serie(owner, pasos: list) -> dict:
    salida: dict = {}
    x = ph.retener_advisory(owner)
    hilos = []
    try:
        pid_x = fh.pid_servidor(x)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilo = threading.Thread(target=lambda c=clave, f=fn: salida.update({c: f()}))
            hilo.start()
            hilos.append(hilo)
            assert _bloqueados_por_advisory(pid_x, n), f"{clave} no espero el advisory (PREFERENCIAS, owner)"
        assert not salida, "algun «Ambos» termino sin esperar el advisory"
        x.execute("COMMIT")
    finally:
        x.close()
    for hilo in hilos:
        hilo.join(timeout=20)
        assert not hilo.is_alive(), "deadlock o espera sin fin"
    return salida


def _n(owner) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.preferencias_registro")[0][0]


def test_dos_ambos_contradictorios_en_serie_el_segundo_no_escribe_nada(t):
    owner, cli, ter, cat, tipo = t
    salida = _en_serie(owner, [("primero", _ambos(cli, tipo, ter, cat, True)), ("segundo", _ambos(cli, tipo, ter, cat, False))])
    assert salida["primero"].status_code == 200, salida["primero"].text
    assert salida["segundo"].status_code == 409, salida["segundo"].text
    assert salida["segundo"].json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO"
    assert sorted(c["ambito"] for c in salida["segundo"].json()["detalle"]["conflictos"]) == ["CATEGORIA", "TERCERO"]
    assert _n(owner) == 2                                                                   # solo las del primero


def test_dos_ambos_iguales_en_serie_terminan_los_dos(t):
    owner, cli, ter, cat, tipo = t
    salida = _en_serie(owner, [("primero", _ambos(cli, tipo, ter, cat, True)), ("segundo", _ambos(cli, tipo, ter, cat, True))])
    assert salida["primero"].status_code == 200 and salida["segundo"].status_code == 200
    assert _n(owner) == 4                                                                   # mismo valor: no contradictorio
