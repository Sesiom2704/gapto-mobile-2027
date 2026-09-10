# ============================================================
# GAPTO MOBILE 2027
# Fichero: conftest.py
# Ruta: tests/database/conftest.py
# Descripción: Fixtures compartidas para tests de integración PostgreSQL.
#
#              D-098: la suite comparte una única conexión de sesión. Si un
#              test abre una transacción explícita y falla dentro de ella, la
#              conexión queda en estado abortado y TODOS los módulos
#              posteriores fallan con InFailedSqlTransaction, aunque el
#              esquema sea correcto. El fixture `_aislamiento` corta esa
#              cadena: antes y después de cada test revierte cualquier
#              transacción abierta y devuelve el rol y las GUC a su estado
#              inicial.
#
#              No abre ni cierra transacciones por su cuenta: los tests que
#              gestionan la suya propia siguen funcionando igual.
# Versión: 0.2.0
# ============================================================

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import pq


@pytest.fixture(scope="session")
def db() -> psycopg.Connection:
    """Abre una conexión nueva contra la BD desechable de integración."""
    dsn = os.getenv("GAPTO_TEST_DATABASE_URL")
    if not dsn:
        pytest.fail(
            "Falta GAPTO_TEST_DATABASE_URL; los tests de BD nunca deben "
            "apuntarse implícitamente a una base no identificada."
        )

    with psycopg.connect(dsn, autocommit=True) as connection:
        yield connection


def _sanear(connection: psycopg.Connection) -> None:
    """Revierte SOLO si la conexión ha quedado abortada.

    Es deliberado no tocar una transacción sana (INTRANS): varios módulos usan
    fixtures de ámbito module que abren su propia transacción y la revierten al
    final, y un rollback preventivo las destruiría. Lo que hay que cortar es el
    estado INERROR, que es el que propaga InFailedSqlTransaction al resto de la
    suite y convierte un fallo aislado en decenas.
    """
    try:
        if connection.info.transaction_status == pq.TransactionStatus.INERROR:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("RESET ALL")
    except psycopg.Error:
        pass


@pytest.fixture(autouse=True)
def _aislamiento(request):
    """Corta la propagación de una transacción abortada entre tests.

    Es autouse pero solo actúa si el test usa `db`; así no fuerza la conexión
    en pruebas que no la necesitan.
    """
    if "db" not in request.fixturenames:
        yield
        return
    connection = request.getfixturevalue("db")
    _sanear(connection)
    yield
    _sanear(connection)
