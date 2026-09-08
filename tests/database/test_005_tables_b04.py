# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_005_tables_b04.py
# Ruta: tests/database/test_005_tables_b04.py
# Descripción: Verifica el contrato físico F03-01-B04 de las tablas 33..45:
#              núcleo de hechos financieros, efectos, atribuciones,
#              terceros/entidades/participantes/aportaciones, tesorería,
#              conciliación, transferencias, previsión-hecho, magnitudes
#              y relaciones entre hechos.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import psycopg

B04_TABLES = {
    "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_terceros",
    "hecho_entidades", "hecho_participantes", "hecho_aportaciones_pago",
    "movimientos_tesoreria", "hecho_movimientos_tesoreria", "transferencias",
    "prevision_hechos", "hecho_magnitudes", "hecho_relaciones",
}
B01_B03_TABLES = {
    "usuarios", "configuracion_usuario", "preferencias_ui", "acciones_rapidas",
    "paises", "regiones", "localidades", "direcciones", "terceros",
    "tercero_direcciones", "actores_financieros", "tercero_roles",
    "clasificaciones_tercero", "tercero_clasificaciones", "categorias_financieras",
    "tercero_afinidades", "tipos_hecho", "magnitudes", "categoria_magnitudes",
    "preferencias_registro", "plantillas_registro", "cuentas", "cuenta_capacidades",
    "cuenta_participaciones", "entidades", "entidad_participaciones",
    "entidad_relaciones", "contextos",
    "reglas_financieras", "regla_versiones", "regla_excepciones", "previsiones",
}
B04_BASELINE_TABLES = B01_B03_TABLES | B04_TABLES

EXPECTED_CHECKS = {
    "ck_hechos_financieros__importe_total", "ck_hechos_financieros__participantes_total",
    "ck_hechos_financieros__moneda_formato", "ck_hechos_financieros__estado_localizacion",
    "ck_hechos_financieros__localidad_coherente", "ck_hechos_financieros__estado",
    "ck_hechos_financieros__anulado_coherente",
    "ck_hecho_efectos__tipo_efecto", "ck_hecho_efectos__importe_delta", "ck_hecho_efectos__estado_atribucion",
    "ck_efecto_atribuciones__porcentaje", "ck_efecto_atribuciones__criterio",
    "ck_hecho_terceros__rol",
    "ck_hecho_entidades__tipo_relacion",
    "ck_hecho_aportaciones_pago__importe", "ck_hecho_aportaciones_pago__porcentaje",
    "ck_hecho_aportaciones_pago__criterio",
    "ck_movimientos_tesoreria__importe", "ck_movimientos_tesoreria__clase",
    "ck_movimientos_tesoreria__estado", "ck_movimientos_tesoreria__anulado_coherente",
    "ck_movimientos_tesoreria__reversion_no_self",
    "ck_hecho_movimientos_tesoreria__importe",
    "ck_prevision_hechos__importe",
    "ck_hecho_relaciones__no_self", "ck_hecho_relaciones__tipo", "ck_hecho_relaciones__importe_relacionado",
}

ROW_VERSION_ROOTS_B04 = {"hechos_financieros", "movimientos_tesoreria"}


def _scalar(db: psycopg.Connection, sql: str, params: Iterable[object] | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_b04_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
        """, (sorted(B04_TABLES),))
        rows = cursor.fetchall()
    assert {r[0] for r in rows} == B04_TABLES
    assert all(r[1] == 'gapto_owner' for r in rows)


def test_b04_baseline_45_tables_remain_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto'
               AND c.relkind='r'
               AND c.relname = ANY(%s)
            """,
            (sorted(B04_BASELINE_TABLES),),
        )
        actual = {row[0] for row in cursor.fetchall()}
    assert actual == B04_BASELINE_TABLES


def test_b04_local_checks_are_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.conname FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND con.contype='c'
        """, (sorted(B04_TABLES),))
        names = {r[0] for r in cursor.fetchall()}
    assert names == EXPECTED_CHECKS


def test_b04_primary_keys_and_uuid_defaults(db: psycopg.Connection) -> None:
    for table in B04_TABLES:
        assert _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='gapto' AND c.relname=%s AND con.contype='p'
        """, (table,)) == 1
        default_expr = _scalar(db, """
            SELECT pg_catalog.pg_get_expr(d.adbin,d.adrelid)
              FROM pg_catalog.pg_attrdef d JOIN pg_catalog.pg_class c ON c.oid=d.adrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=d.adnum
             WHERE n.nspname='gapto' AND c.relname=%s AND a.attname='id'
        """, (table,))
        assert 'gen_random_uuid()' in default_expr


def test_b04_row_version_only_on_expected_roots(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s)
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """, (sorted(B04_TABLES),))
        actual = {r[0] for r in cursor.fetchall()}
    assert actual == ROW_VERSION_ROOTS_B04


def test_b04_layering_has_no_fk_unique_exclude_or_secondary_indexes(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.contype, count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND con.contype IN ('f','u','x') GROUP BY con.contype
        """, (sorted(B04_TABLES),))
        assert cursor.fetchall() == []
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND NOT i.indisprimary
        """, (sorted(B04_TABLES),))
        assert cursor.fetchone()[0] == 0


def test_b04_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0040_f03_01_tables_b04_hechos_tesoreria.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'CREATE INDEX' not in text
    assert 'CREATE UNIQUE INDEX' not in text
    assert 'EXCLUDE USING' not in text
    assert 'CREATE TABLE IF NOT EXISTS' not in text
