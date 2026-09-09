# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_002_tables_b01.py
# Ruta: tests/database/test_002_tables_b01.py
# Descripción: Verifica el contrato físico F03-01-B01 de las tablas 1..16:
#              existencia, ownership, PK, columnas, defaults y CHECK locales.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import psycopg


B01_TABLES = {
    "usuarios",
    "configuracion_usuario",
    "preferencias_ui",
    "acciones_rapidas",
    "paises",
    "regiones",
    "localidades",
    "direcciones",
    "terceros",
    "tercero_direcciones",
    "actores_financieros",
    "tercero_roles",
    "clasificaciones_tercero",
    "tercero_clasificaciones",
    "categorias_financieras",
    "tercero_afinidades",
}

PK_COLUMNS = {
    "usuarios": ["id"],
    "configuracion_usuario": ["owner_user_id"],
    "preferencias_ui": ["owner_user_id"],
    "acciones_rapidas": ["id"],
    "paises": ["id"],
    "regiones": ["id"],
    "localidades": ["id"],
    "direcciones": ["id"],
    "terceros": ["id"],
    "tercero_direcciones": ["id"],
    "actores_financieros": ["id"],
    "tercero_roles": ["id"],
    "clasificaciones_tercero": ["id"],
    "tercero_clasificaciones": ["id"],
    "categorias_financieras": ["id"],
    "tercero_afinidades": ["id"],
}

UUID_DEFAULT_TABLES = B01_TABLES - {"configuracion_usuario", "preferencias_ui"}

EXPECTED_COLUMNS = {
    "usuarios": {
        "id": ("uuid", True), "email": ("character varying(254)", True),
        "nombre": ("character varying(120)", True), "timezone": ("character varying(50)", True),
        "locale": ("character varying(10)", True), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "configuracion_usuario": {
        "owner_user_id": ("uuid", True), "moneda_default": ("character varying(3)", True),
        "multimoneda_enabled": ("boolean", True), "meses_historico_presupuesto": ("smallint", True),
        "metodo_estimacion_default": ("character varying(30)", False),
        "dia_inicio_mes_financiero": ("smallint", True), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "preferencias_ui": {
        "owner_user_id": ("uuid", True), "modo": ("character varying(20)", True),
        "densidad": ("character varying(20)", True), "accent_key": ("character varying(30)", False),
        "mostrar_centimos": ("boolean", True), "mostrar_importes_atribuibles": ("boolean", True),
        "home_layout": ("jsonb", False), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "acciones_rapidas": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True),
        "nombre": ("character varying(80)", True), "plantilla_registro_id": ("uuid", True),
        "orden": ("smallint", True), "icono_key": ("character varying(50)", False),
        "enabled": ("boolean", True), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "paises": {
        "id": ("uuid", True), "iso2": ("character varying(2)", True),
        "iso3": ("character varying(3)", True), "nombre": ("character varying(100)", True),
        "enabled": ("boolean", True),
    },
    "regiones": {
        "id": ("uuid", True), "pais_id": ("uuid", True), "parent_region_id": ("uuid", False),
        "nombre": ("character varying(120)", True), "tipo_region": ("character varying(40)", False),
        "codigo_oficial": ("character varying(30)", False), "enabled": ("boolean", True),
    },
    "localidades": {
        "id": ("uuid", True), "region_id": ("uuid", True),
        "nombre": ("character varying(120)", True), "codigo_oficial": ("character varying(30)", False),
        "codigo_oficial_tipo": ("character varying(30)", False), "enabled": ("boolean", True),
    },
    "direcciones": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "localidad_id": ("uuid", False),
        "codigo_postal": ("character varying(20)", False), "via_tipo": ("character varying(30)", False),
        "via_nombre": ("character varying(150)", False), "numero": ("character varying(20)", False),
        "bloque": ("character varying(20)", False), "escalera": ("character varying(20)", False),
        "planta": ("character varying(20)", False), "puerta": ("character varying(20)", False),
        "observaciones": ("text", False), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "terceros": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True),
        "nombre": ("character varying(160)", True), "nombre_legal": ("character varying(200)", False),
        "naturaleza": ("character varying(30)", False), "identificador_fiscal": ("character varying(50)", False),
        "tipo_identificador_fiscal": ("character varying(30)", False), "pais_fiscal_id": ("uuid", False),
        "email": ("character varying(254)", False), "telefono": ("character varying(40)", False),
        "notas": ("text", False), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "enabled": ("boolean", True),
        "row_version": ("bigint", True),
    },
    "tercero_direcciones": {
        "id": ("uuid", True), "tercero_id": ("uuid", True), "direccion_id": ("uuid", True),
        "tipo": ("character varying(30)", True), "principal": ("boolean", True),
    },
    "actores_financieros": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "tercero_id": ("uuid", False),
    },
    "tercero_roles": {
        "id": ("uuid", True), "tercero_id": ("uuid", True),
        "rol_codigo": ("character varying(50)", True),
    },
    "clasificaciones_tercero": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "parent_id": ("uuid", False),
        "nombre": ("character varying(100)", True), "codigo": ("character varying(50)", False),
        "orden": ("smallint", True), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "enabled": ("boolean", True),
        "row_version": ("bigint", True),
    },
    "tercero_clasificaciones": {
        "id": ("uuid", True), "tercero_id": ("uuid", True), "clasificacion_id": ("uuid", True),
        "principal": ("boolean", True),
    },
    "categorias_financieras": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "parent_id": ("uuid", False),
        "nombre": ("character varying(100)", True), "codigo": ("character varying(60)", False),
        "ambito": ("character varying(20)", True), "presupuestable_default": ("boolean", True),
        "orden": ("smallint", True), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "enabled": ("boolean", True),
        "row_version": ("bigint", True),
    },
    "tercero_afinidades": {
        "id": ("uuid", True), "tercero_id": ("uuid", True), "categoria_id": ("uuid", True),
        "prioridad_manual": ("smallint", False),
    },
}

EXPECTED_CHECKS = {
    "ck_usuarios__email_no_blanco",
    "ck_usuarios__nombre_no_blanco",
    "ck_usuarios__timezone_no_blanco",
    "ck_usuarios__locale_no_blanco",
    "ck_configuracion_usuario__moneda_default_formato",
    "ck_configuracion_usuario__meses_historico_positivo",
    "ck_configuracion_usuario__metodo_estimacion",
    "ck_configuracion_usuario__dia_inicio_mes_financiero",
    "ck_preferencias_ui__modo",
    "ck_preferencias_ui__densidad",
    "ck_preferencias_ui__accent_key_no_blanco",
    "ck_acciones_rapidas__nombre_no_blanco",
    "ck_acciones_rapidas__orden_no_negativo",
    "ck_acciones_rapidas__icono_key_no_blanco",
    "ck_paises__iso2_formato",
    "ck_paises__iso3_formato",
    "ck_paises__nombre_no_blanco",
    "ck_regiones__parent_no_self",
    "ck_regiones__nombre_no_blanco",
    "ck_regiones__tipo_region_formato",
    "ck_regiones__codigo_oficial_no_blanco",
    "ck_localidades__nombre_no_blanco",
    "ck_localidades__codigo_oficial_no_blanco",
    "ck_localidades__codigo_oficial_tipo_formato",
    "ck_localidades__tipo_requiere_codigo",
    "ck_direcciones__codigo_postal_no_blanco",
    "ck_direcciones__via_tipo_no_blanco",
    "ck_direcciones__via_nombre_no_blanco",
    "ck_direcciones__numero_no_blanco",
    "ck_direcciones__bloque_no_blanco",
    "ck_direcciones__escalera_no_blanco",
    "ck_direcciones__planta_no_blanco",
    "ck_direcciones__puerta_no_blanco",
    "ck_direcciones__observaciones_no_blanco",
    "ck_direcciones__contenido_minimo",
    "ck_terceros__nombre_no_blanco",
    "ck_terceros__nombre_legal_no_blanco",
    "ck_terceros__naturaleza",
    "ck_terceros__identificador_fiscal_no_blanco",
    "ck_terceros__tipo_identificador_fiscal_formato",
    "ck_terceros__tipo_fiscal_requiere_identificador",
    "ck_terceros__email_no_blanco",
    "ck_terceros__telefono_no_blanco",
    "ck_terceros__notas_no_blanco",
    "ck_tercero_direcciones__tipo",
    "ck_tercero_roles__rol_codigo",
    "ck_clasificaciones_tercero__parent_no_self",
    "ck_clasificaciones_tercero__nombre_no_blanco",
    "ck_clasificaciones_tercero__codigo_formato",
    "ck_clasificaciones_tercero__orden_no_negativo",
    "ck_categorias_financieras__parent_no_self",
    "ck_categorias_financieras__nombre_no_blanco",
    "ck_categorias_financieras__codigo_formato",
    "ck_categorias_financieras__ambito",
    "ck_categorias_financieras__orden_no_negativo",
    "ck_tercero_afinidades__prioridad_no_negativa",
}


def _scalar(db: psycopg.Connection, sql: str, params: Iterable[object] | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_b01_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class AS c
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.relnamespace
             WHERE n.nspname = 'gapto'
               AND c.relkind = 'r'
               AND c.relname = ANY(%s)
             ORDER BY c.relname
            """,
            (sorted(B01_TABLES),),
        )
        rows = cursor.fetchall()

    assert {row[0] for row in rows} == B01_TABLES
    assert all(owner == "gapto_owner" for _, owner in rows)



def test_b01_column_contract_is_exact(db: psycopg.Connection) -> None:
    for table, expected in EXPECTED_COLUMNS.items():
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.attname,
                    pg_catalog.format_type(a.atttypid, a.atttypmod),
                    a.attnotnull
                  FROM pg_catalog.pg_attribute AS a
                  JOIN pg_catalog.pg_class AS c
                    ON c.oid = a.attrelid
                  JOIN pg_catalog.pg_namespace AS n
                    ON n.oid = c.relnamespace
                 WHERE n.nspname = 'gapto'
                   AND c.relname = %s
                   AND a.attnum > 0
                   AND NOT a.attisdropped
                 ORDER BY a.attnum
                """,
                (table,),
            )
            actual = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

        assert actual == expected

def test_b01_primary_keys_and_uuid_defaults(db: psycopg.Connection) -> None:
    for table, expected_columns in PK_COLUMNS.items():
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.attname
                  FROM pg_catalog.pg_constraint AS con
                  JOIN pg_catalog.pg_class AS c
                    ON c.oid = con.conrelid
                  JOIN pg_catalog.pg_namespace AS n
                    ON n.oid = c.relnamespace
                  JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                    ON true
                  JOIN pg_catalog.pg_attribute AS a
                    ON a.attrelid = c.oid
                   AND a.attnum = k.attnum
                 WHERE n.nspname = 'gapto'
                   AND c.relname = %s
                   AND con.contype = 'p'
                 ORDER BY k.ord
                """,
                (table,),
            )
            columns = [row[0] for row in cursor.fetchall()]
        assert columns == expected_columns

    for table in UUID_DEFAULT_TABLES:
        default_expr = _scalar(
            db,
            """
            SELECT pg_catalog.pg_get_expr(d.adbin, d.adrelid)
              FROM pg_catalog.pg_attrdef AS d
              JOIN pg_catalog.pg_class AS c
                ON c.oid = d.adrelid
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_attribute AS a
                ON a.attrelid = c.oid
               AND a.attnum = d.adnum
             WHERE n.nspname = 'gapto'
               AND c.relname = %s
               AND a.attname = 'id'
            """,
            (table,),
        )
        assert "gen_random_uuid()" in default_expr


def test_b01_critical_defaults_and_nullability(db: psycopg.Connection) -> None:
    expectations = {
        ("usuarios", "email"): ("NO", None),
        ("usuarios", "timezone"): ("NO", "'Europe/Madrid'::character varying"),
        ("usuarios", "locale"): ("NO", "'es-ES'::character varying"),
        ("usuarios", "row_version"): ("NO", "1"),
        ("configuracion_usuario", "moneda_default"): ("NO", "'EUR'::character varying"),
        ("configuracion_usuario", "multimoneda_enabled"): ("NO", "false"),
        ("configuracion_usuario", "meses_historico_presupuesto"): ("NO", "4"),
        ("configuracion_usuario", "dia_inicio_mes_financiero"): ("NO", "1"),
        ("preferencias_ui", "modo"): ("NO", "'SISTEMA'::character varying"),
        ("preferencias_ui", "densidad"): ("NO", "'NORMAL'::character varying"),
        ("acciones_rapidas", "orden"): ("NO", "0"),
        ("acciones_rapidas", "enabled"): ("NO", "true"),
        ("paises", "enabled"): ("NO", "true"),
        ("direcciones", "localidad_id"): ("YES", None),
        ("terceros", "naturaleza"): ("YES", None),
        ("terceros", "enabled"): ("NO", "true"),
        ("tercero_direcciones", "principal"): ("NO", "false"),
        ("actores_financieros", "tercero_id"): ("YES", None),
        ("clasificaciones_tercero", "orden"): ("NO", "0"),
        ("categorias_financieras", "presupuestable_default"): ("NO", None),
        ("categorias_financieras", "orden"): ("NO", "0"),
        ("tercero_afinidades", "prioridad_manual"): ("YES", None),
    }

    for (table, column), (nullable, expected_default) in expectations.items():
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema = 'gapto'
                   AND table_name = %s
                   AND column_name = %s
                """,
                (table, column),
            )
            row = cursor.fetchone()
        assert row is not None
        assert row[0] == nullable
        if expected_default is None:
            assert row[1] is None
        else:
            assert row[1] == expected_default


def test_b01_local_checks_are_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT con.conname
              FROM pg_catalog.pg_constraint AS con
              JOIN pg_catalog.pg_class AS c
                ON c.oid = con.conrelid
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.relnamespace
             WHERE n.nspname = 'gapto'
               AND c.relname = ANY(%s)
               AND con.contype = 'c'
            """,
            (sorted(B01_TABLES),),
        )
        checks = {row[0] for row in cursor.fetchall()}

    assert EXPECTED_CHECKS <= checks


def test_b01_public_has_no_table_dml(db: psycopg.Connection) -> None:
    for table in B01_TABLES:
        qualified = f"gapto.{table}"
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert _scalar(
                db,
                "SELECT pg_catalog.has_table_privilege('public', %s, %s)",
                (qualified, privilege),
            ) is False


def test_b01_migration_respects_layering() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "0010_f03_01_tables_b01_usuario_geografia_terceros.sql"
    )
    sql = migration.read_text(encoding="utf-8").upper()

    # B08/B09 materializarán UNIQUE/FK/anchors. B01 crea únicamente columnas,
    # PK y CHECK locales para poder resolver dependencias/ciclos más adelante.
    assert "FOREIGN KEY" not in sql
    assert " REFERENCES " not in sql
    assert "CONSTRAINT UQ_" not in sql
    assert "CREATE UNIQUE INDEX" not in sql
    assert "CREATE TABLE IF NOT EXISTS" not in sql
    assert "CREATE SCHEMA IF NOT EXISTS" not in sql
    assert "CREATE EXTENSION IF NOT EXISTS" not in sql
