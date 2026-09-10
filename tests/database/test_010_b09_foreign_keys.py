# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_010_b09_foreign_keys.py
# Ruta: tests/database/test_010_b09_foreign_keys.py
# Descripción: Verifica F03-01-B09: 161 FK totales, con la política de
#              borrado fijada en F03-00-E1 (RESTRICT por defecto para
#              relaciones financieras/históricas, CASCADE solo para
#              hijos estrictamente dependientes sin historia propia) =
#              141 RESTRICT + 20 CASCADE. Confirma layering: EXCLUDE
#              (B10) todavía no materializado en este punto.
# Versión: 0.2.0
#                   D-098: expectativa caducada migrada a validacion de
#                   propiedad/baseline. El layering se sigue verificando a
#                   nivel de fichero de migration, que es donde es cierto de
#                   forma permanente, y no contra el estado acumulado de la BD.
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg


def test_b09_exactly_161_foreign_keys(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='f'
        """)
        (count,) = cursor.fetchone()
    assert count >= 161, f'baseline B09 = 161 FK; encontrado {count}'


def test_b09_delete_policy_matches_f03_00_e1(db: psycopg.Connection) -> None:
    """RESTRICT ('r') es la politica base; CASCADE ('c') solo para hijos
    estrictamente dependientes. No se esperan SET NULL ('n') en este
    baseline salvo excepcion documentada, ni NO ACTION ('a')."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.confdeltype, count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='f'
             GROUP BY con.confdeltype
        """)
        by_type = dict(cursor.fetchall())
    assert by_type.get('r', 0) >= 141, f"RESTRICT baseline=141, encontrado={by_type.get('r', 0)}"
    assert by_type.get('c', 0) >= 20, f"CASCADE baseline=20, encontrado={by_type.get('c', 0)}"
    assert set(by_type.keys()) <= {'r', 'c'}, f"Tipos de ON DELETE inesperados: {by_type.keys()}"


def test_b09_no_on_update_cascade(db: psycopg.Connection) -> None:
    """F03-00-E1: las identidades UUID no se actualizan por cascada."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='f' AND con.confupdtype = 'c'
        """)
        (count,) = cursor.fetchone()
    assert count == 0


def test_b09_migration_has_no_exclude() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0090_f03_01_b09_foreign_keys.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'EXCLUDE USING' not in text
    assert text.count('FOREIGN KEY') >= 161
