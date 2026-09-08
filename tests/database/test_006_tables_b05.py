# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_006_tables_b05.py
# Ruta: tests/database/test_006_tables_b05.py
# Descripción: Verifica el contrato físico F03-01-B05 de las tablas 46..59:
#              derechos/obligaciones financieras, propiedades y su
#              valoración, contratos y participantes, servicios y sus
#              vínculos, financiaciones con condiciones/cuotas, e
#              inversiones con objetivos/valoraciones.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg

B05_TABLES = {
    "derechos_obligaciones_financieras", "propiedades", "propiedad_valoraciones",
    "contratos", "contrato_participantes", "servicios", "propiedad_servicios",
    "contrato_servicios", "financiaciones", "financiacion_condiciones_versiones",
    "financiacion_cuotas", "inversiones", "inversion_objetivos_versiones",
    "inversion_valoraciones",
}
B01_B04_TABLES = {
    "usuarios", "configuracion_usuario", "preferencias_ui", "acciones_rapidas",
    "paises", "regiones", "localidades", "direcciones", "terceros",
    "tercero_direcciones", "actores_financieros", "tercero_roles",
    "clasificaciones_tercero", "tercero_clasificaciones", "categorias_financieras",
    "tercero_afinidades", "tipos_hecho", "magnitudes", "categoria_magnitudes",
    "preferencias_registro", "plantillas_registro", "cuentas", "cuenta_capacidades",
    "cuenta_participaciones", "entidades", "entidad_participaciones",
    "entidad_relaciones", "contextos",
    "reglas_financieras", "regla_versiones", "regla_excepciones", "previsiones",
    "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_terceros",
    "hecho_entidades", "hecho_participantes", "hecho_aportaciones_pago",
    "movimientos_tesoreria", "hecho_movimientos_tesoreria", "transferencias",
    "prevision_hechos", "hecho_magnitudes", "hecho_relaciones",
}
B05_BASELINE_TABLES = B01_B04_TABLES | B05_TABLES

# Tablas subtipo de `entidades`: PK = FK del padre (entidad_id), sin default propio.
SUBTYPE_PK_FK_TABLES = {
    "derechos_obligaciones_financieras", "propiedades", "contratos",
    "servicios", "financiaciones", "inversiones",
}


def test_b05_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
        """, (sorted(B05_TABLES),))
        rows = cursor.fetchall()
    assert {r[0] for r in rows} == B05_TABLES
    assert all(r[1] == 'gapto_owner' for r in rows)


def test_b05_baseline_59_tables_remain_materialized(db: psycopg.Connection) -> None:
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
            (sorted(B05_BASELINE_TABLES),),
        )
        actual = {row[0] for row in cursor.fetchall()}
    assert actual == B05_BASELINE_TABLES


def test_b05_subtype_tables_use_entidad_id_as_pk(db: psycopg.Connection) -> None:
    for table in SUBTYPE_PK_FK_TABLES:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT a.attname FROM pg_catalog.pg_constraint con
                  JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
                  JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                  JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum = ANY(con.conkey)
                 WHERE n.nspname='gapto' AND c.relname=%s AND con.contype='p'
            """, (table,))
            pk_cols = {r[0] for r in cursor.fetchall()}
        assert pk_cols == {"entidad_id"}


def test_b05_layering_has_no_fk_unique_exclude_or_secondary_indexes(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.contype, count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND con.contype IN ('f','u','x') GROUP BY con.contype
        """, (sorted(B05_TABLES),))
        assert cursor.fetchall() == []
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND NOT i.indisprimary
        """, (sorted(B05_TABLES),))
        assert cursor.fetchone()[0] == 0


def test_b05_no_row_version_on_subtype_or_bridge_tables(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s)
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """, (sorted(B05_TABLES),))
        assert cursor.fetchone()[0] == 0


def test_b05_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0050_f03_01_tables_b05_dominios_especializados.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'CREATE INDEX' not in text
    assert 'CREATE UNIQUE INDEX' not in text
    assert 'EXCLUDE USING' not in text
    assert 'CREATE TABLE IF NOT EXISTS' not in text
