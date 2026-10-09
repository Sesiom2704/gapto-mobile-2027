# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_172_f05_02_locks_propuesta.py
# Ruta: tests/api/test_172_f05_02_locks_propuesta.py
# Descripcion: Evidencia del orden de locks de la lectura de la propuesta de
#   preferencias (F05-02 B3, AJ-B2-01; F05-D028 §43.4). GET
#   /v1/preferencias/propuesta?categoria_id=X reutiliza la guarda C-a
#   (elegibilidad_categoria.validar_seleccion_categoria) como segundo llamante,
#   de lectura. El test detiene la transaccion de la propuesta en dos puntos
#   deterministas (al entrar en el resolver, ya con la guarda pasada, y al
#   salir de el, antes del COMMIT) sustituyendo `lecturas.resolver` por un
#   envoltorio con barreras (threading.Event), y desde OTRA conexion afirma:
#     - pg_locks del pid: exactamente UN RowShareLock de tabla y es sobre
#       gapto.categorias_financieras (sus indices lo llevan tambien: se
#       atribuyen a la tabla); ningun lock `advisory`; el resto de locks
#       de relacion son AccessShareLock (lecturas sin lock de fila);
#     - la fila de la categoria esta bloqueada en modo compartido: FOR UPDATE
#       NOWAIT falla (55P03) y FOR SHARE NOWAIT no;
#     - los advisory (PREFERENCIAS, owner) y (CATEGORIAS, owner) estan libres
#       y la fila de la preferencia no esta bloqueada;
#     - tras el COMMIT la categoria queda libre.
#   Sin categoria («Sin categoria») no hay RowShareLock ni advisory.
#   Orden resultante: categoria (FOR SHARE) -> lecturas sin lock -> COMMIT.
#   Datos sinteticos; el adaptador corre como gapto_runtime con RLS.
# Version: 0.1.0 (F05-02 B3, AJ-B2-01)
# ============================================================

from __future__ import annotations

import threading
import uuid

import psycopg
import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h

ESPERA = 30  # s: tope de cada barrera (nunca se alcanza si el flujo es correcto)

# Cada lock de relacion se atribuye a su TABLA: un indice cuenta como la tabla que indexa
# (el planificador bloquea tambien los indices de la tabla con el mismo modo).
_LOCKS = """
SELECT l.locktype, l.mode, n.nspname, COALESCE(t.relname, c.relname), c.relkind
  FROM pg_locks l
  LEFT JOIN pg_class c ON c.oid = l.relation
  LEFT JOIN pg_index i ON i.indexrelid = c.oid
  LEFT JOIN pg_class t ON t.oid = i.indrelid
  LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE l.pid = %s AND l.granted AND l.locktype IN ('relation', 'advisory', 'tuple')
"""


class _Barreras:
    """Envoltorio de `lecturas.resolver` que se detiene al entrar y al salir."""

    def __init__(self, original):
        self.original = original
        self.pid: int | None = None
        self.llegada = {"entrada": threading.Event(), "salida": threading.Event()}
        self.seguir = {"entrada": threading.Event(), "salida": threading.Event()}

    def _parar(self, punto: str) -> None:
        self.llegada[punto].set()
        assert self.seguir[punto].wait(ESPERA), f"barrera {punto} sin liberar"

    def __call__(self, sesion, **kw):
        self.pid = sesion.uno("SELECT pg_backend_pid()")[0]
        self._parar("entrada")
        r = self.original(sesion, **kw)
        self._parar("salida")
        return r

    def esperar(self, punto: str) -> None:
        assert self.llegada[punto].wait(ESPERA), f"la propuesta no llego a {punto}"

    def liberar(self, punto: str) -> None:
        self.seguir[punto].set()


def _locks(pid: int) -> list[tuple]:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        return c.execute(_LOCKS, (pid,)).fetchall()


def _intentar(sql: str, params: tuple) -> bool:
    """True si la sentencia obtiene el lock sin esperar; False si 55P03."""
    with psycopg.connect(h.dsn()) as c:
        try:
            c.execute(sql, params)
            return True
        except psycopg.errors.LockNotAvailable:
            return False
        finally:
            c.rollback()


def _advisory_libre(clase: str, owner: uuid.UUID) -> bool:
    with psycopg.connect(h.dsn()) as c:
        libre = c.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s), hashtext(%s::uuid::text))", (f"gapto:{clase}", str(owner))
        ).fetchone()[0]
        c.rollback()
        return libre


def _lanzar(cli, categoria_id):
    salida: dict = {}
    hilo = threading.Thread(target=lambda: salida.update(r=ph.propuesta_http(cli, categoria_id)), daemon=True)
    hilo.start()
    return hilo, salida


@pytest.fixture()
def escenario(monkeypatch):
    from app.preferencias import lecturas

    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="Tarjeta")
    ph.cuenta(owner, actor, nombre="Efectivo")
    cat = ph.categoria(owner, "Supermercado")
    pid_pref = ph.insertar_sql(owner, categoria_id=cat, cuenta=a)
    barreras = _Barreras(lecturas.resolver)
    monkeypatch.setattr(lecturas, "resolver", barreras)
    return owner, cli, a, cat, pid_pref, barreras


def _comprobar_un_rowshare_sin_advisory(pid: int) -> None:
    locks = _locks(pid)
    # Exactamente UN RowShareLock de tabla, sobre gapto.categorias_financieras; sus indices, con el mismo modo.
    assert [(n, r) for (t, m, n, r, k) in locks if m == "RowShareLock" and k in ("r", "p")] == [
        ("gapto", "categorias_financieras")], locks
    assert {(n, r) for (t, m, n, r, k) in locks if m == "RowShareLock"} == {("gapto", "categorias_financieras")}, locks
    assert [x for x in locks if x[0] == "advisory"] == [], locks
    otros = {m for (t, m, n, r, k) in locks if t == "relation" and m != "RowShareLock"}
    assert otros <= {"AccessShareLock"}, locks


def test_propuesta_con_categoria_toma_solo_for_share_de_la_categoria(escenario):
    owner, cli, a, cat, pid_pref, b = escenario
    hilo, salida = _lanzar(cli, cat)
    try:
        for punto in ("entrada", "salida"):
            b.esperar(punto)
            _comprobar_un_rowshare_sin_advisory(b.pid)
            fila_cat = "SELECT 1 FROM gapto.categorias_financieras WHERE id = %s "
            assert _intentar(fila_cat + "FOR UPDATE NOWAIT", (cat,)) is False  # fila bloqueada en modo compartido
            assert _intentar(fila_cat + "FOR SHARE NOWAIT", (cat,)) is True  # otro lector no espera
            assert _intentar("SELECT 1 FROM gapto.preferencias_registro WHERE id = %s FOR UPDATE NOWAIT", (pid_pref,))
            assert _advisory_libre("PREFERENCIAS", owner) and _advisory_libre("CATEGORIAS", owner)
            b.liberar(punto)
    finally:
        b.liberar("entrada")
        b.liberar("salida")
        hilo.join(ESPERA)
    assert salida["r"].status_code == 200, salida["r"].text
    assert salida["r"].json()["cuenta"]["valor"] == str(a)
    # Tras el COMMIT la categoria queda libre.
    assert _intentar("SELECT 1 FROM gapto.categorias_financieras WHERE id = %s FOR UPDATE NOWAIT", (cat,)) is True


def test_propuesta_sin_categoria_no_toma_ningun_lock_de_fila_ni_advisory(escenario):
    owner, cli, _a, cat, _pid_pref, b = escenario
    hilo, salida = _lanzar(cli, None)
    try:
        b.esperar("entrada")
        locks = _locks(b.pid)
        assert [x for x in locks if x[1] == "RowShareLock" or x[0] == "advisory"] == [], locks
        assert _intentar("SELECT 1 FROM gapto.categorias_financieras WHERE id = %s FOR UPDATE NOWAIT", (cat,)) is True
    finally:
        b.liberar("entrada")
        b.liberar("salida")
        hilo.join(ESPERA)
    assert salida["r"].status_code == 200, salida["r"].text
