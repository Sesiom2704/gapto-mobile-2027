# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_012_b11_indexes.py
# Ruta: tests/database/test_012_b11_indexes.py
# Descripción: Verifica F03-01-B11: 134 índices secundarios (cobertura de
#              FK + patrones de acceso compuestos + 6 GIN pg_trgm),
#              excluyendo explícitamente los índices que EXCLUDE (B10)
#              ya crea automáticamente por sí mismo.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg


def _non_exclude_secondary_index_count(db: psycopg.Connection) -> int:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_index i
              JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT i.indisprimary AND NOT i.indisunique
               AND NOT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_constraint con
                     WHERE con.conindid = c.oid AND con.contype = 'x'
               )
        """)
        (count,) = cursor.fetchone()
    return count


def test_b11_exactly_134_secondary_indexes(db: psycopg.Connection) -> None:
    assert _non_exclude_secondary_index_count(db) == 134


def test_b11_gin_trgm_indexes_on_expected_columns(db: psycopg.Connection) -> None:
    expected = {
        ("terceros", "nombre"), ("terceros", "nombre_legal"),
        ("entidades", "nombre"),
        ("hechos_financieros", "concepto"),
        ("documentos", "titulo"), ("documentos", "nombre_archivo_original"),
    }
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname AS tabla, a.attname AS columna
              FROM pg_catalog.pg_index i
              JOIN pg_catalog.pg_class ix ON ix.oid = i.indexrelid
              JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_am am ON am.oid = ix.relam
              JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
             WHERE n.nspname='gapto' AND am.amname = 'gin'
        """)
        actual = {(r[0], r[1]) for r in cursor.fetchall()}
    assert actual == expected


def test_b11_every_fk_has_index_coverage(db: psycopg.Connection) -> None:
    """Toda FK debe tener indice util (primera columna del FK cubierta por
    algun indice), salvo cobertura equivalente por PK/UNIQUE/EXCLUDE
    (F03-00-E1/I)."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, a.attname
              FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
             WHERE n.nspname = 'gapto' AND con.contype = 'f'
               AND NOT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_index i
                     WHERE i.indrelid = con.conrelid
                       AND i.indkey[0] = con.conkey[1]
               )
        """)
        uncovered = cursor.fetchall()
    assert uncovered == [], f"FK sin indice de cobertura: {uncovered}"


def test_b11_migration_file_has_correct_index_count() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0105_f03_01_b11_indexes.sql'
    text = migration.read_text(encoding='utf-8')
    assert text.count('CREATE INDEX') == 134
