# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_003_tables_b02.py
# Ruta: tests/database/test_003_tables_b02.py
# Descripción: Verifica el contrato físico F03-01-B02 de las tablas 17..28:
#              existencia, ownership, PK, columnas, defaults y CHECK locales.
# Versión: 0.1.1
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import psycopg


B02_TABLES = {
    "tipos_hecho",
    "magnitudes",
    "categoria_magnitudes",
    "preferencias_registro",
    "plantillas_registro",
    "cuentas",
    "cuenta_capacidades",
    "cuenta_participaciones",
    "entidades",
    "entidad_participaciones",
    "entidad_relaciones",
    "contextos",
}

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

B02_BASELINE_TABLES = B01_TABLES | B02_TABLES

PK_COLUMNS = {
    "tipos_hecho": ["id"],
    "magnitudes": ["id"],
    "categoria_magnitudes": ["id"],
    "preferencias_registro": ["id"],
    "plantillas_registro": ["id"],
    "cuentas": ["id"],
    "cuenta_capacidades": ["id"],
    "cuenta_participaciones": ["id"],
    "entidades": ["id"],
    "entidad_participaciones": ["id"],
    "entidad_relaciones": ["id"],
    "contextos": ["entidad_id"],
}

UUID_DEFAULT_TABLES = B02_TABLES - {"contextos"}

EXPECTED_COLUMNS = {
    "tipos_hecho": {
        "id": ("uuid", True),
        "codigo": ("character varying(50)", True),
        "nombre": ("character varying(100)", True),
        "enabled": ("boolean", True),
    },
    "magnitudes": {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "nombre": ("character varying(80)", True),
        "unidad_default": ("character varying(20)", True),
        "precision_decimales": ("smallint", True),
        "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True),
        "enabled": ("boolean", True),
        "row_version": ("bigint", True),
    },
    "categoria_magnitudes": {
        "id": ("uuid", True),
        "categoria_id": ("uuid", True),
        "magnitud_id": ("uuid", True),
        "obligatoria": ("boolean", True),
        "orden": ("smallint", True),
    },
    "preferencias_registro": {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "tipo_hecho_id": ("uuid", False),
        "categoria_id": ("uuid", False),
        "tercero_id": ("uuid", False),
        "entidad_id": ("uuid", False),
        "cuenta_default_id": ("uuid", False),
        "presupuestable_default": ("boolean", False),
        "prioridad": ("integer", True),
        "enabled": ("boolean", True),
        "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True),
        "row_version": ("bigint", True),
    },
    "plantillas_registro": {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "nombre": ("character varying(100)", True),
        "tipo_hecho_id": ("uuid", True),
        "categoria_id": ("uuid", False),
        "tercero_id": ("uuid", False),
        "entidad_id": ("uuid", False),
        "cuenta_default_id": ("uuid", False),
        "presupuestable_default": ("boolean", False),
        "enabled": ("boolean", True),
        "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True),
        "row_version": ("bigint", True),
    },
    "cuentas": {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "nombre": ("character varying(120)", True),
        "tercero_gestor_id": ("uuid", False),
        "tipo": ("character varying(30)", True),
        "naturaleza": ("character varying(20)", True),
        "moneda": ("character varying(3)", True),
        "saldo_apertura": ("numeric(18,4)", False),
        "fecha_inicio_ledger": ("date", False),
        "limite_credito": ("numeric(18,4)", False),
        "computa_liquidez": ("boolean", True),
        "computa_patrimonio": ("boolean", True),
        "permite_negativo": ("boolean", True),
        "orden": ("smallint", True),
        "enabled": ("boolean", True),
        "fecha_cierre": ("date", False),
        "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True),
        "row_version": ("bigint", True),
    },
    "cuenta_capacidades": {
        "id": ("uuid", True),
        "cuenta_id": ("uuid", True),
        "capacidad_codigo": ("character varying(50)", True),
    },
    "cuenta_participaciones": {
        "id": ("uuid", True),
        "cuenta_id": ("uuid", True),
        "actor_id": ("uuid", True),
        "porcentaje": ("numeric(7,4)", True),
        "vigente_desde": ("date", True),
        "vigente_hasta": ("date", False),
    },
    "entidades": {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "tipo_entidad": ("character varying(50)", True),
        "nombre": ("character varying(160)", True),
        "enabled": ("boolean", True),
        "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True),
        "row_version": ("bigint", True),
    },
    "entidad_participaciones": {
        "id": ("uuid", True),
        "entidad_id": ("uuid", True),
        "actor_id": ("uuid", True),
        "porcentaje": ("numeric(7,4)", True),
        "vigente_desde": ("date", True),
        "vigente_hasta": ("date", False),
    },
    "entidad_relaciones": {
        "id": ("uuid", True),
        "entidad_origen_id": ("uuid", True),
        "entidad_destino_id": ("uuid", True),
        "tipo_relacion": ("character varying(50)", True),
        "vigente_desde": ("date", False),
        "vigente_hasta": ("date", False),
        "row_version": ("bigint", True),
    },
    "contextos": {
        "entidad_id": ("uuid", True),
        "tipo_contexto": ("character varying(30)", True),
        "fecha_inicio": ("date", False),
        "fecha_fin": ("date", False),
        "notas": ("text", False),
    },
}

EXPECTED_CHECKS = {
    "ck_tipos_hecho__codigo_formato",
    "ck_tipos_hecho__nombre_no_blanco",
    "ck_magnitudes__nombre_no_blanco",
    "ck_magnitudes__unidad_default_no_blanco",
    "ck_magnitudes__precision_decimales",
    "ck_categoria_magnitudes__orden_no_negativo",
    "ck_preferencias_registro__propone_valor",
    "ck_plantillas_registro__nombre_no_blanco",
    "ck_cuentas__nombre_no_blanco",
    "ck_cuentas__tipo",
    "ck_cuentas__naturaleza",
    "ck_cuentas__moneda_formato",
    "ck_cuentas__apertura_pareja",
    "ck_cuentas__limite_credito_no_negativo",
    "ck_cuentas__orden_no_negativo",
    "ck_cuentas__fecha_cierre_ledger",
    "ck_cuentas__cierre_deshabilita",
    "ck_cuenta_capacidades__capacidad_codigo",
    "ck_cuenta_participaciones__porcentaje",
    "ck_cuenta_participaciones__vigencia",
    "ck_entidades__tipo_entidad",
    "ck_entidades__nombre_no_blanco",
    "ck_entidad_participaciones__porcentaje",
    "ck_entidad_participaciones__vigencia",
    "ck_entidad_relaciones__no_self",
    "ck_entidad_relaciones__tipo_relacion",
    "ck_entidad_relaciones__vigencia",
    "ck_contextos__tipo_contexto",
    "ck_contextos__fechas",
    "ck_contextos__notas_no_blanco",
}


def _scalar(db: psycopg.Connection, sql: str, params: Iterable[object] | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_b02_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
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
            (sorted(B02_TABLES),),
        )
        rows = cursor.fetchall()

    assert {row[0] for row in rows} == B02_TABLES
    assert all(owner == "gapto_owner" for _, owner in rows)


def test_b02_baseline_28_tables_remain_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname
              FROM pg_catalog.pg_class AS c
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.relnamespace
             WHERE n.nspname = 'gapto'
               AND c.relkind = 'r'
               AND c.relname = ANY(%s)
            """,
            (sorted(B02_BASELINE_TABLES),),
        )
        actual = {row[0] for row in cursor.fetchall()}

    assert actual == B02_BASELINE_TABLES


def test_b02_column_contract_is_exact(db: psycopg.Connection) -> None:
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


def test_b02_primary_keys_and_uuid_defaults(db: psycopg.Connection) -> None:
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

    assert _scalar(
        db,
        """
        SELECT count(*)
          FROM pg_catalog.pg_attrdef AS d
          JOIN pg_catalog.pg_class AS c
            ON c.oid = d.adrelid
          JOIN pg_catalog.pg_namespace AS n
            ON n.oid = c.relnamespace
          JOIN pg_catalog.pg_attribute AS a
            ON a.attrelid = c.oid
           AND a.attnum = d.adnum
         WHERE n.nspname = 'gapto'
           AND c.relname = 'contextos'
           AND a.attname = 'entidad_id'
        """,
    ) == 0


def test_b02_critical_defaults_and_nullability(db: psycopg.Connection) -> None:
    expectations = {
        ("tipos_hecho", "enabled"): ("NO", "true"),
        ("magnitudes", "precision_decimales"): ("NO", None),
        ("magnitudes", "enabled"): ("NO", "true"),
        ("magnitudes", "row_version"): ("NO", "1"),
        ("categoria_magnitudes", "obligatoria"): ("NO", "false"),
        ("categoria_magnitudes", "orden"): ("NO", "0"),
        ("preferencias_registro", "tipo_hecho_id"): ("YES", None),
        ("preferencias_registro", "prioridad"): ("NO", "100"),
        ("preferencias_registro", "enabled"): ("NO", "true"),
        ("plantillas_registro", "tipo_hecho_id"): ("NO", None),
        ("plantillas_registro", "enabled"): ("NO", "true"),
        ("cuentas", "moneda"): ("NO", None),
        ("cuentas", "computa_liquidez"): ("NO", None),
        ("cuentas", "computa_patrimonio"): ("NO", None),
        ("cuentas", "permite_negativo"): ("NO", None),
        ("cuentas", "orden"): ("NO", "0"),
        ("cuentas", "enabled"): ("NO", "true"),
        ("cuentas", "saldo_apertura"): ("YES", None),
        ("cuenta_participaciones", "vigente_desde"): ("NO", None),
        ("cuenta_participaciones", "vigente_hasta"): ("YES", None),
        ("entidades", "enabled"): ("NO", "true"),
        ("entidades", "row_version"): ("NO", "1"),
        ("entidad_participaciones", "vigente_desde"): ("NO", None),
        ("entidad_relaciones", "vigente_desde"): ("YES", None),
        ("entidad_relaciones", "row_version"): ("NO", "1"),
        ("contextos", "entidad_id"): ("NO", None),
        ("contextos", "fecha_inicio"): ("YES", None),
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


def test_b02_local_checks_are_materialized(db: psycopg.Connection) -> None:
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
            (sorted(B02_TABLES),),
        )
        checks = {row[0] for row in cursor.fetchall()}

    assert EXPECTED_CHECKS <= checks


def test_b02_public_has_no_table_dml(db: psycopg.Connection) -> None:
    for table in B02_TABLES:
        qualified = f"gapto.{table}"
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        ):
            assert _scalar(
                db,
                "SELECT pg_catalog.has_table_privilege('public', %s, %s)",
                (qualified, privilege),
            ) is False


def test_b02_migration_respects_layering() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "0020_f03_01_tables_b02_catalogos_cuentas_entidades.sql"
    )
    sql = migration.read_text(encoding="utf-8").upper()

    # B08/B09 materializarán anchors/UNIQUE y relaciones entre tablas.
    # B02 crea únicamente columnas, PK y CHECK locales.
    assert "FOREIGN KEY" not in sql
    assert " REFERENCES " not in sql
    assert "CONSTRAINT UQ_" not in sql
    assert "CREATE UNIQUE INDEX" not in sql
    assert "CREATE TABLE IF NOT EXISTS" not in sql
    assert "CREATE SCHEMA IF NOT EXISTS" not in sql
    assert "CREATE EXTENSION IF NOT EXISTS" not in sql
