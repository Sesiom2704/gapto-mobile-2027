# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_009_b08_anchors_unique.py
# Ruta: tests/database/test_009_b08_anchors_unique.py
# Descripción: Verifica F03-01-B08: 33 UNIQUE constraints estándar + 12
#              índices únicos parciales/de expresión (NULLS NOT DISTINCT,
#              principal por contexto, etc.) = 45 anchors totales,
#              per F03-00-E1/E2. Confirma layering: todavía sin FK ni
#              EXCLUDE materializados en este punto.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg


def test_b08_exactly_33_unique_constraints(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='u'
        """)
        (count,) = cursor.fetchone()
    assert count == 33


def test_b08_exactly_12_unique_indexes_without_constraint(db: psycopg.Connection) -> None:
    """Indices unicos parciales/de expresion (NULLS NOT DISTINCT, principal
    por scope, etc.) que no se expresan como CONSTRAINT UNIQUE simple."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_index i ON i.indexrelid=c.oid
             WHERE n.nspname='gapto' AND c.relkind='i' AND i.indisunique
               AND NOT i.indisprimary
               AND NOT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_constraint con WHERE con.conindid=c.oid
               )
        """)
        (count,) = cursor.fetchone()
    assert count == 12


def test_b08_total_anchors_45(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_index i ON i.indexrelid=c.oid
             WHERE n.nspname='gapto' AND c.relkind='i' AND i.indisunique AND NOT i.indisprimary
        """)
        (count,) = cursor.fetchone()
    assert count == 45


def test_b08_layering_no_fk_or_exclude_yet(db: psycopg.Connection) -> None:
    """B08 solo materializa UNIQUE; FK (B09) y EXCLUDE (B10) vienen despues."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.contype, count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype IN ('f','x')
             GROUP BY con.contype
        """)
        assert cursor.fetchall() == []


def test_b08_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0080_f03_01_b08_anchors_unique.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'EXCLUDE USING' not in text
    assert text.count('UNIQUE') >= 33
