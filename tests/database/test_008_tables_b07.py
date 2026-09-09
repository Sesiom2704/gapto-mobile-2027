# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_008_tables_b07.py
# Ruta: tests/database/test_008_tables_b07.py
# Descripción: Verifica el contrato físico F03-01-B07 de las tablas 68..79:
#              documentos/vínculos, etiquetas, auditoría (append-only),
#              asignaciones de inversión, alcances de línea presupuestaria,
#              trazabilidad de importación (fuentes/registros/mapeos),
#              tercero_personas (subtipo PK=FK) y revisión de renta.
#              Este bloque COMPLETA el baseline físico de 79/79 tablas.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg

from test_007_tables_b06 import B06_BASELINE_TABLES

B07_TABLES = {
    "documentos", "documento_vinculos", "etiquetas", "hecho_etiquetas",
    "auditoria", "inversion_asignaciones_efecto", "presupuesto_linea_alcances",
    "fuentes_importacion", "registros_origen_importacion", "mapeos_importacion",
    "tercero_personas", "contrato_revision_renta_versiones",
}
FULL_BASELINE_79 = B06_BASELINE_TABLES | B07_TABLES


def test_b07_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
        """, (sorted(B07_TABLES),))
        rows = cursor.fetchall()
    assert {r[0] for r in rows} == B07_TABLES
    assert all(r[1] == 'gapto_owner' for r in rows)


def test_b07_baseline_79_tables_complete(db: psycopg.Connection) -> None:
    """B07 completa el baseline fisico: exactamente 79/79 tablas, techo
    cerrado y estable (no crece en bloques posteriores)."""
    assert len(FULL_BASELINE_79) == 79
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r'
        """)
        (total,) = cursor.fetchone()
    assert total == 79, f"Se esperaban exactamente 79 tablas en gapto; encontradas={total}"

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r'
        """)
        actual = {r[0] for r in cursor.fetchall()}
    assert actual == FULL_BASELINE_79


def test_b07_tercero_personas_uses_pk_fk_subtype(db: psycopg.Connection) -> None:
    """tercero_personas es subtipo 1:0..1 de terceros (F02-B01): su PK
    es tercero_id, no una columna 'id' propia."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT a.attname FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid=con.conrelid AND a.attnum = ANY(con.conkey)
             WHERE n.nspname='gapto' AND c.relname='tercero_personas' AND con.contype='p'
        """)
        pk_cols = [r[0] for r in cursor.fetchall()]
    assert pk_cols == ["tercero_id"]


def test_b07_auditoria_and_snapshots_have_no_row_version(db: psycopg.Connection) -> None:
    """auditoria es append-only por diseño (F03-00-H); no usa optimistic
    locking porque nunca se actualiza."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname='auditoria'
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """)
        (count,) = cursor.fetchone()
    assert count == 0


def test_b07_row_version_only_on_expected_roots(db: psycopg.Connection) -> None:
    expected = {"documentos", "etiquetas", "fuentes_importacion"}
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s)
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """, (sorted(B07_TABLES),))
        actual = {r[0] for r in cursor.fetchall()}
    assert actual == expected


def test_b07_layering_has_no_fk_unique_exclude_or_secondary_indexes(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.contype, count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND con.contype IN ('f','u','x') GROUP BY con.contype
        """, (sorted(B07_TABLES),))
        assert cursor.fetchall() == []
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND NOT i.indisprimary
        """, (sorted(B07_TABLES),))
        assert cursor.fetchone()[0] == 0


def test_b07_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0070_f03_01_tables_b07_documentos_auditoria_importacion.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'CREATE INDEX' not in text
    assert 'CREATE UNIQUE INDEX' not in text
    assert 'EXCLUDE USING' not in text
    assert 'CREATE TABLE IF NOT EXISTS' not in text
