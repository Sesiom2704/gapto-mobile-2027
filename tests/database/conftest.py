# ============================================================
# GAPTO MOBILE 2027
# Fichero: conftest.py
# Ruta: tests/database/conftest.py
# Descripción: Fixtures compartidas para tests de integración PostgreSQL.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import os

import psycopg
import pytest


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
