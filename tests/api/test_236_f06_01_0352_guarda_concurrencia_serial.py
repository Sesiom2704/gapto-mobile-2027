# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_236_f06_01_0352_guarda_concurrencia_serial.py
# Ruta: tests/api/test_236_f06_01_0352_guarda_concurrencia_serial.py
# Descripcion: N1 de 0352 (mandato v1.4), Alcance 5 y 5bis.4: concurrencia REAL de la guarda de C-PROP-02
#   (AJ-0352-05) con una declaracion de adquisicion simultanea. C-PROP-05 (B2-B3) no existe en este N1: un
#   declarante SIMULADO, con COMMIT real, toma primero el lock de la entidad (FOR NO KEY UPDATE OF e, el nivel 2 del
#   orden de locks de B1) y escribe la declaracion; mientras lo mantiene, `editar` (motor real, UnidadDeTrabajo,
#   gapto_runtime) con una fecha posterior al corte queda ESPERANDO en ese lock (comprobado en pg_stat_activity).
#   Al confirmar el declarante:
#     - S1 (declarante correcto, sube row_version): `editar` devuelve VERSION_DESFASADA (precedencia frente a la
#       guarda) y no escribe nada;
#     - S2 (declarante que no sube row_version): `editar` ve la declaracion confirmada bajo su lock y devuelve
#       ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO sin escribir nada.
#   En ambos: sin 40P01 ni 40001 y declaracion conservada. Bateria serie fuera de la suite general
#   (GAPTO_0352_CONCURRENCIA=1), como test_232.
# Version: 0.1.0 (F03 · N1 de 0352, mandato v1.4)
# ============================================================

from __future__ import annotations

import datetime as dt
import os
import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f06_01_b1_helpers as b
import vs01_api_helpers as h
from app.core.contexto import ContextoOperacion
from app.propiedades import servicio as serv

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_0352_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_0352_CONCURRENCIA=1)")


@pytest.fixture()
def t():
    return b.entorno()


def _esperando_lock(pid_backend: int | None = None, plazo: float = 15.0) -> bool:
    limite = time.time() + plazo
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        while time.time() < limite:
            n = c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                          "AND wait_event_type = 'Lock' AND state = 'active'").fetchone()[0]
            if n >= 1:
                return True
            time.sleep(0.05)
    return False


def _escenario(owner, pid, *, sube_version: bool):
    dec = psycopg.connect(h.dsn())
    dec.execute("SET ROLE gapto_owner")
    dec.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
    # declarante: lock de nivel 2 (entidad) y escritura de la declaracion, sin confirmar todavia
    dec.execute("SELECT 1 FROM gapto.entidades e WHERE e.id = %s FOR NO KEY UPDATE OF e", (pid,))
    dec.execute("UPDATE gapto.propiedades SET coste_adquisicion_declarado_completo = true, coste_adquisicion_declarado_en = "
                "'2025-12-31', coste_adquisicion_conjunto_declarado = '[]'::jsonb WHERE entidad_id = %s", (pid,))
    if sube_version:
        dec.execute("UPDATE gapto.entidades SET row_version = row_version + 1 WHERE id = %s", (pid,))
    resultado = {}

    def editar():
        ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
        resultado["r"] = fh.unidad().ejecutar(ctx, lambda s: serv.editar(
            s, entidad_id=uuid.UUID(str(pid)), intencion_id=uuid.uuid4(), row_version=1,
            campos={"fecha_adquisicion": dt.date(2026, 1, 1)}), nombre="test 0352 guarda concurrente")

    hilo = threading.Thread(target=editar)
    antes_deadlocks = h.leer(owner, "SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")[0][0]
    hilo.start()
    bloqueado = _esperando_lock()
    dec.commit()
    dec.close()
    hilo.join(timeout=60)
    despues_deadlocks = h.leer(owner, "SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")[0][0]
    return bloqueado, resultado.get("r"), despues_deadlocks - antes_deadlocks


def test_s1_declarante_que_sube_version_gana_version_desfasada(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    bloqueado, r, deadlocks = _escenario(owner, p["id"], sube_version=True)
    assert bloqueado, "editar no llego a esperar el lock de la entidad"
    assert isinstance(r, serv.Rechazo) and r.codigo == "VERSION_DESFASADA", r
    assert deadlocks == 0
    prop = b.leer(cli, p["id"])
    assert prop["fecha_adquisicion"] == "2025-06-01" and prop["row_version"] == 2


def test_s2_declarante_sin_version_la_guarda_ve_la_declaracion_confirmada(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    bloqueado, r, deadlocks = _escenario(owner, p["id"], sube_version=False)
    assert bloqueado, "editar no llego a esperar el lock de la entidad"
    assert isinstance(r, serv.Rechazo) and r.codigo == "ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO", r
    assert deadlocks == 0
    prop = b.leer(cli, p["id"])
    assert prop["fecha_adquisicion"] == "2025-06-01" and prop["row_version"] == 1
    decl = h.leer(owner, "SELECT coste_adquisicion_declarado_completo, coste_adquisicion_declarado_en FROM gapto.propiedades "
                         "WHERE entidad_id = %s", (p["id"],))[0]
    assert decl == (True, dt.date(2025, 12, 31))
