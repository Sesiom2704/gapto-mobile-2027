# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_315_f06_t4_aj05_semantica_postgres.py
# Ruta: tests/api/test_315_f06_t4_aj05_semantica_postgres.py
# Descripcion: AJ-05 (F06 T4), pruebas de semantica de PostgreSQL y psycopg del diseno v0.2 §4, con el caso 2 y la
#   prueba del COMMIT diferido SUSTITUIDOS por la adenda 02 §4 (AJ-R4-04, opcion C). Se ejecutan igual en local y en
#   Neon (GAPTO_TEST_DATABASE_URL; resultados separados por la evidencia de cada tirada). No necesitan el esquema gapto:
#   crean una tabla y una funcion sonda propias en `public` con nombre unico y las borran al terminar.
#   - sesion: `transaction_timeout` en autocommit sin transaccion implicita; despues BEGIN real.
#   - SET LOCAL (set_config(..., true)) efectivo dentro y revertido al terminar.
#   - 55P03 esperando `pg_advisory_xact_lock` y `FOR UPDATE` con lock_timeout propio.
#   - statement_timeout salta antes que transaction_timeout en una sentencia ordinaria; cero filas tras el rollback.
#   - Adenda 02 §4 A: statement_timeout NO corta el COMMIT con triggers diferidos (se registra duracion, desenlace SQL
#     y persistencia real: la fila queda).
#   - Adenda 02 §4 B: transaction_timeout corta la sesion durante el COMMIT diferido (25P04) y no persiste nada; por la
#     unidad de trabajo del producto el intento queda COMMIT_INDETERMINADO.
# Version: 0.1.0 (F06 T4 · AJ-05, mandato b4ff6b70…, adenda 01 24113472… y adenda 02 9744307e…)
# ============================================================
from __future__ import annotations

import time
import uuid

import psycopg
import pytest

import vs01_api_helpers as h
from app.core import peticion as pet
from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import UnidadDeTrabajo

DUERME_S = 4


@pytest.fixture()
def sonda():
    sufijo = uuid.uuid4().hex[:12]
    tabla, funcion = f"public.aj05_sonda_{sufijo}", f"public.aj05_dormir_{sufijo}"
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        c.execute(f"CREATE TABLE {tabla} (id int PRIMARY KEY, lenta boolean NOT NULL DEFAULT false)")
        c.execute(f"CREATE FUNCTION {funcion}() RETURNS trigger LANGUAGE plpgsql AS "
                  f"$$ BEGIN IF NEW.lenta THEN PERFORM pg_sleep({DUERME_S}); END IF; RETURN NULL; END $$")
        c.execute(f"CREATE CONSTRAINT TRIGGER aj05_diferido AFTER INSERT ON {tabla} DEFERRABLE INITIALLY DEFERRED "
                  f"FOR EACH ROW EXECUTE FUNCTION {funcion}()")
        c.execute(f"INSERT INTO {tabla} (id) VALUES (0)")
        c.execute(f"GRANT ALL ON {tabla} TO PUBLIC")
    yield tabla
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        c.execute(f"DROP TABLE IF EXISTS {tabla}")
        c.execute(f"DROP FUNCTION IF EXISTS {funcion}()")


def _filas(tabla, id_):
    with psycopg.connect(h.dsn()) as c:
        return c.execute(f"SELECT count(*) FROM {tabla} WHERE id = %s", (id_,)).fetchone()[0]


def test_sesion_sin_transaccion_implicita_y_begin_real():
    with psycopg.connect(h.dsn()) as c:
        c.autocommit = True
        c.execute("SELECT set_config('transaction_timeout', '7000ms', false)")
        assert c.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        with c.transaction():
            assert c.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
            assert c.execute("SHOW transaction_timeout").fetchone()[0] == "7s"
            xid1 = c.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
        with c.transaction():
            xid2 = c.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
        assert xid1 != xid2                                     # dos BEGIN reales, no savepoints de una misma
        assert c.execute("SHOW transaction_timeout").fetchone()[0] == "7s"


def test_set_local_efectivo_y_revertido():
    with psycopg.connect(h.dsn()) as c:
        c.autocommit = True
        base = (c.execute("SHOW statement_timeout").fetchone()[0], c.execute("SHOW lock_timeout").fetchone()[0])
        with c.transaction():
            c.execute("SELECT set_config('statement_timeout', '1234ms', true), set_config('lock_timeout', '0', true)")
            assert c.execute("SHOW statement_timeout").fetchone()[0] == "1234ms"
            assert c.execute("SHOW lock_timeout").fetchone()[0] == "0"
        assert (c.execute("SHOW statement_timeout").fetchone()[0], c.execute("SHOW lock_timeout").fetchone()[0]) == base


def test_55p03_en_advisory_y_en_for_update(sonda):
    clave = uuid.uuid4().int % 2_000_000_000
    with psycopg.connect(h.dsn()) as retiene:
        retiene.execute("SELECT pg_advisory_xact_lock(4242, %s)", (clave,))
        retiene.execute(f"SELECT id FROM {sonda} WHERE id = 0 FOR UPDATE")
        for sql, params in (("SELECT pg_advisory_xact_lock(4242, %s)", (clave,)),
                            (f"SELECT id FROM {sonda} WHERE id = 0 FOR UPDATE", ())):
            with psycopg.connect(h.dsn()) as c:
                t0 = time.monotonic()
                with pytest.raises(psycopg.errors.LockNotAvailable) as e:
                    with c.transaction():
                        c.execute("SELECT set_config('lock_timeout', '500ms', true)")
                        c.execute(sql, params)
                assert e.value.sqlstate == "55P03" and time.monotonic() - t0 < 3
        retiene.rollback()


def test_statement_timeout_salta_antes_que_transaction_timeout_y_cero_filas(sonda):
    with psycopg.connect(h.dsn()) as c:
        c.autocommit = True
        c.execute("SELECT set_config('transaction_timeout', '3000ms', false)")
        t0 = time.monotonic()
        with pytest.raises(psycopg.errors.QueryCanceled) as e:
            with c.transaction():
                c.execute("SELECT set_config('statement_timeout', '1000ms', true)")
                c.execute(f"INSERT INTO {sonda} (id) VALUES (1)")
                c.execute("SELECT pg_sleep(10)")
        assert e.value.sqlstate == "57014" and time.monotonic() - t0 < 2.5
    assert _filas(sonda, 1) == 0


def test_adenda02_a_statement_timeout_no_corta_el_commit_diferido_y_persiste(sonda, capsys):
    """AJ-R4-04 A: se REGISTRA lo que hace PostgreSQL. Con statement_timeout = 1 s y un trigger diferido de 4 s, el
    COMMIT termina sin error pasado el limite y la fila persiste."""
    with psycopg.connect(h.dsn()) as c:
        c.autocommit = True
        t0 = time.monotonic()
        with c.transaction():
            c.execute("SELECT set_config('statement_timeout', '1000ms', true)")
            c.execute(f"INSERT INTO {sonda} (id, lenta) VALUES (2, true)")
        dur = time.monotonic() - t0
    assert dur >= DUERME_S - 0.2, dur
    assert _filas(sonda, 2) == 1
    with capsys.disabled():
        print(f"\n[AJ05-ADENDA02-A] statement_timeout=1s, trigger diferido {DUERME_S}s: COMMIT OK en {dur:.2f}s, fila persiste")


def test_adenda02_b_transaction_timeout_corta_la_sesion_en_el_commit_y_no_persiste(sonda, capsys):
    with psycopg.connect(h.dsn()) as c:
        c.autocommit = True
        c.execute("SELECT set_config('transaction_timeout', '1500ms', false)")
        t0 = time.monotonic()
        with pytest.raises(psycopg.Error) as e:
            with c.transaction():
                c.execute("SELECT set_config('statement_timeout', '1000ms', true)")
                c.execute(f"INSERT INTO {sonda} (id, lenta) VALUES (3, true)")
        dur = time.monotonic() - t0
    assert e.value.sqlstate == "25P04" and dur < DUERME_S, (e.value.sqlstate, dur)
    assert _filas(sonda, 3) == 0
    with capsys.disabled():
        print(f"\n[AJ05-ADENDA02-B] transaction_timeout=1.5s: {type(e.value).__name__} {e.value.sqlstate} en {dur:.2f}s, "
              f"sin fila")


def test_adenda02_b_por_la_unidad_de_trabajo_commit_indeterminado(sonda):
    """El mismo corte por el camino del producto: la unidad fija transaction_timeout = restante + margen; el COMMIT con
    el trigger diferido lento lo corta la sesion -> el intento queda COMMIT_INDETERMINADO (nunca ROLLBACK_CONFIRMADO ni
    un plazo propio), y no persiste nada."""
    proveedor = lambda: psycopg.connect(h.dsn())  # noqa: E731
    u = UnidadDeTrabajo(proveedor)
    estado, token = pet.iniciar("POST", "/v1/intenciones/gasto-pagado")
    try:
        estado.deadline = estado.t0 + 1.0
        with pytest.raises(BaseException) as e:
            u.ejecutar(ContextoOperacion.de_usuario(uuid.uuid4(), request_id=uuid.uuid4()),
                       lambda s: s.ejecutar(f"INSERT INTO {sonda} (id, lenta) VALUES (4, true)"), nombre="sonda")
    finally:
        pet.terminar(token)
    assert not isinstance(e.value, pet.PlazoAgotado)
    intento = estado.unidades[0].intentos[-1]
    assert intento.sqlstate == "25P04" and intento.estado is pet.EstadoUnidad.COMMIT_INDETERMINADO, intento
    assert estado.persistencia() is pet.Persistencia.COMMIT_INDETERMINADO
    assert _filas(sonda, 4) == 0


def test_statement_timeout_propio_por_la_unidad_de_trabajo_es_plazo_y_cero_filas(sonda):
    u = UnidadDeTrabajo(lambda: psycopg.connect(h.dsn()))
    estado, token = pet.iniciar("POST", "/v1/intenciones/gasto-pagado")

    def op(s):
        s.ejecutar(f"INSERT INTO {sonda} (id) VALUES (5)")
        s.uno("SELECT pg_sleep(10)")
    try:
        estado.deadline = estado.t0 + 1.5
        with pytest.raises(pet.PlazoAgotado) as e:
            u.ejecutar(ContextoOperacion.de_usuario(uuid.uuid4(), request_id=uuid.uuid4()), op, nombre="sonda")
    finally:
        pet.terminar(token)
    assert e.value.motivo == "STATEMENT_TIMEOUT" and e.value.sqlstate == "57014"
    assert estado.unidades[0].intentos[-1].estado is pet.EstadoUnidad.ROLLBACK_CONFIRMADO
    assert estado.persistencia() is pet.Persistencia.NINGUNA
    assert _filas(sonda, 5) == 0
