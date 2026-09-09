# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_011_b10_exclude_temporal.py
# Ruta: tests/database/test_011_b10_exclude_temporal.py
# Descripción: Verifica F03-01-B10: 11 EXCLUDE USING gist DEFERRABLE
#              INITIALLY IMMEDIATE (F03-00-G-A) sobre daterange derivado
#              de vigente_desde/vigente_hasta, requiere btree_gist.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg


def test_b10_exactly_11_exclude_constraints(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='x'
        """)
        (count,) = cursor.fetchone()
    assert count == 11


def test_b10_all_exclude_are_deferrable_initially_immediate(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.conname, con.condeferrable, con.condeferred
              FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='x'
        """)
        rows = cursor.fetchall()
    assert len(rows) == 11
    for name, deferrable, deferred in rows:
        assert deferrable is True, f"{name}: debe ser DEFERRABLE"
        assert deferred is False, f"{name}: debe ser INITIALLY IMMEDIATE (no DEFERRED)"


def test_b10_exclude_use_gist_index(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_class ix ON ix.oid = con.conindid
              JOIN pg_catalog.pg_am am ON am.oid = ix.relam
             WHERE n.nspname='gapto' AND con.contype='x' AND am.amname='gist'
        """)
        (count,) = cursor.fetchone()
    assert count == 11


def test_b10_btree_gist_extension_installed(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")
        (count,) = cursor.fetchone()
    assert count == 1


def test_b10_migration_uses_deferrable_initially_immediate() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0100_f03_01_b10_exclude_temporal.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert text.count('EXCLUDE USING') == 11
    assert 'INITIALLY DEFERRED' not in text
