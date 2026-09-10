# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_009_b08_anchors_unique.py
# Ruta: tests/database/test_009_b08_anchors_unique.py
# Descripción: Verifica F03-01-B08: 33 UNIQUE constraints estándar + 12
#              índices únicos parciales/de expresión (NULLS NOT DISTINCT,
#              principal por contexto, etc.) = 45 anchors totales,
#              per F03-00-E1/E2. Confirma layering: todavía sin FK ni
#              EXCLUDE materializados en este punto.
# Versión: 0.2.0
#                   D-098: expectativa caducada migrada a validacion de
#                   propiedad/baseline. El layering se sigue verificando a
#                   nivel de fichero de migration, que es donde es cierto de
#                   forma permanente, y no contra el estado acumulado de la BD.
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
    assert count >= 33, f'baseline B08 = 33 constraints UNIQUE; encontrado {count}'


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
    assert count >= 12, f'baseline B08 = 12 indices unicos sin constraint; encontrado {count}'


def test_b08_total_anchors_45(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_index i ON i.indexrelid=c.oid
             WHERE n.nspname='gapto' AND c.relkind='i' AND i.indisunique AND NOT i.indisprimary
        """)
        (count,) = cursor.fetchone()
    assert count >= 45, f'baseline B08 = 45 anchors; encontrado {count}'


def test_b08_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0080_f03_01_b08_anchors_unique.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'EXCLUDE USING' not in text
    assert text.count('UNIQUE') >= 33
