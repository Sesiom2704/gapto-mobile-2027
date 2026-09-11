# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_004_tables_b03.py
# Ruta: tests/database/test_004_tables_b03.py
# Descripción: Verifica el contrato físico F03-01-B03 de las tablas 29..32:
#              reglas financieras, versiones, excepciones y previsiones.
# Versión: 0.1.4  -- 0270 (A8) añade ck_regla_versiones__ventana_dias_obligatorios
#                   como segunda sucesora conocida (Working Method 12C.5); el
#                   CHECK congelado de 0030 se conserva intacto.
#                   v0.1.3: 0265 (D-126) añade regla_versiones.anclaje_recurrencia y
#                   cuatro CHECK. El test valida el baseline B03 y acepta
#                   exactamente esa sucesora conocida (Working Method 12C.5);
#                   cualquier otra columna o CHECK sigue siendo drift.
#                   v0.1.2:
#                   D-098: expectativa caducada migrada a validacion de
#                   propiedad/baseline. El layering se sigue verificando a
#                   nivel de fichero de migration, que es donde es cierto de
#                   forma permanente, y no contra el estado acumulado de la BD.
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import psycopg

B03_TABLES = {"reglas_financieras", "regla_versiones", "regla_excepciones", "previsiones"}
B01_B02_TABLES = {
    "usuarios", "configuracion_usuario", "preferencias_ui", "acciones_rapidas",
    "paises", "regiones", "localidades", "direcciones", "terceros",
    "tercero_direcciones", "actores_financieros", "tercero_roles",
    "clasificaciones_tercero", "tercero_clasificaciones", "categorias_financieras",
    "tercero_afinidades", "tipos_hecho", "magnitudes", "categoria_magnitudes",
    "preferencias_registro", "plantillas_registro", "cuentas", "cuenta_capacidades",
    "cuenta_participaciones", "entidades", "entidad_participaciones",
    "entidad_relaciones", "contextos",
}
B03_BASELINE_TABLES = B01_B02_TABLES | B03_TABLES
EXPECTED_COLUMNS = {
    "reglas_financieras": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "nombre": ("character varying(160)", True),
        "entidad_origen_id": ("uuid", False), "created_at": ("timestamp with time zone", True),
        "updated_at": ("timestamp with time zone", True), "row_version": ("bigint", True),
    },
    "regla_versiones": {
        "id": ("uuid", True), "regla_id": ("uuid", True), "vigente_desde": ("date", True),
        "vigente_hasta": ("date", False), "tipo_hecho_id": ("uuid", True),
        "flujo_tesoreria_esperado": ("character varying(30)", True), "categoria_id": ("uuid", False),
        "tercero_id": ("uuid", False), "cuenta_salida_esperada_id": ("uuid", False),
        "cuenta_entrada_esperada_id": ("uuid", False), "moneda": ("character varying(3)", True),
        "importe_referencia_lado": ("character varying(10)", False), "periodicidad": ("character varying(30)", False),
        "intervalo": ("smallint", False), "fecha_modo": ("character varying(30)", True),
        "dia_desde": ("smallint", False), "dia_hasta": ("smallint", False),
        "importe_modo": ("character varying(40)", True), "importe_fijo": ("numeric(18,4)", False),
        "cuenta_calculo_id": ("uuid", False), "saldo_objetivo": ("numeric(18,4)", False),
        "meses_historico": ("smallint", False), "presupuestable": ("boolean", True),
    },
    "regla_excepciones": {
        "id": ("uuid", True), "regla_id": ("uuid", True), "fecha_objetivo": ("date", True),
        "omitida": ("boolean", True), "importe_override": ("numeric(18,4)", False),
        "fecha_override": ("date", False), "motivo": ("text", False),
        "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True),
    },
    "previsiones": {
        "id": ("uuid", True), "owner_user_id": ("uuid", True), "regla_version_id": ("uuid", False),
        "fecha_objetivo_regla": ("date", False), "concepto": ("character varying(200)", True),
        "tipo_hecho_id": ("uuid", True), "categoria_id": ("uuid", False), "tercero_id": ("uuid", False),
        "entidad_id": ("uuid", False), "fecha_esperada_desde": ("date", True), "fecha_esperada_hasta": ("date", True),
        "flujo_tesoreria_esperado": ("character varying(30)", True), "moneda": ("character varying(3)", True),
        "importe_esperado": ("numeric(18,4)", False), "importe_referencia_lado": ("character varying(10)", False),
        "cuenta_salida_esperada_id": ("uuid", False), "cuenta_entrada_esperada_id": ("uuid", False),
        "presupuestable": ("boolean", True), "estado": ("character varying(20)", True),
        "recalculo_automatico": ("boolean", True), "motivo_ajuste": ("text", False),
        "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True),
        "row_version": ("bigint", True),
    },
}
# Sucesora conocida: 0265 / D-126 (anclaje de recurrencia).
SUCESORA_0265_COLUMNAS = {"anclaje_recurrencia": ("character varying(30)", False)}
SUCESORA_0265_CHECKS = {
    "ck_regla_versiones__anclaje_recurrencia", "ck_regla_versiones__anclaje_periodicidad",
    "ck_regla_versiones__rodante_fecha_modo", "ck_regla_versiones__rodante_importe_modo",
}
# Sucesora conocida: 0270 / A8 (dias obligatorios con fecha_modo=VENTANA).
SUCESORA_0270_CHECKS = {"ck_regla_versiones__ventana_dias_obligatorios"}

EXPECTED_CHECKS = {
    "ck_reglas_financieras__nombre_no_blanco",
    "ck_regla_versiones__vigencia", "ck_regla_versiones__flujo_tesoreria", "ck_regla_versiones__moneda_formato",
    "ck_regla_versiones__importe_referencia_lado", "ck_regla_versiones__periodicidad", "ck_regla_versiones__intervalo",
    "ck_regla_versiones__fecha_modo", "ck_regla_versiones__ventana", "ck_regla_versiones__importe_modo",
    "ck_regla_versiones__importe_fijo", "ck_regla_versiones__saldo_objetivo", "ck_regla_versiones__meses_historico",
    "ck_regla_versiones__cuentas_por_flujo", "ck_regla_excepciones__importe_override",
    "ck_previsiones__concepto_no_blanco", "ck_previsiones__fechas", "ck_previsiones__flujo_tesoreria",
    "ck_previsiones__moneda_formato", "ck_previsiones__importe_esperado", "ck_previsiones__importe_referencia_lado",
    "ck_previsiones__cuentas_por_flujo", "ck_previsiones__estado", "ck_previsiones__recalculo_estado",
}


def _scalar(db: psycopg.Connection, sql: str, params: Iterable[object] | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_b03_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
        """, (sorted(B03_TABLES),))
        rows = cursor.fetchall()
    assert {r[0] for r in rows} == B03_TABLES
    assert all(r[1] == 'gapto_owner' for r in rows)


def test_b03_baseline_32_tables_remain_materialized(db: psycopg.Connection) -> None:
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
            (sorted(B03_BASELINE_TABLES),),
        )
        actual = {row[0] for row in cursor.fetchall()}
    assert actual == B03_BASELINE_TABLES


def test_b03_column_contract_is_exact(db: psycopg.Connection) -> None:
    for table, expected in EXPECTED_COLUMNS.items():
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod), a.attnotnull
                  FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
                  JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                 WHERE n.nspname='gapto' AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum
            """, (table,))
            actual = {r[0]:(r[1],r[2]) for r in cursor.fetchall()}
        if table == "regla_versiones":
            assert actual in (expected, {**expected, **SUCESORA_0265_COLUMNAS})
        else:
            assert actual == expected


def test_b03_primary_keys_and_uuid_defaults(db: psycopg.Connection) -> None:
    for table in B03_TABLES:
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


def test_b03_critical_defaults_and_nullability(db: psycopg.Connection) -> None:
    defaults = {}
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, a.attname, pg_catalog.pg_get_expr(d.adbin,d.adrelid)
              FROM pg_catalog.pg_attrdef d JOIN pg_catalog.pg_class c ON c.oid=d.adrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=d.adnum
             WHERE n.nspname='gapto' AND c.relname = ANY(%s)
        """, (sorted(B03_TABLES),))
        for table, col, expr in cursor.fetchall(): defaults[(table,col)] = expr
    assert defaults[("reglas_financieras","row_version")] == '1'
    assert defaults[("regla_versiones","intervalo")] == '1'
    assert defaults[("regla_excepciones","omitida")] == 'false'
    assert "'ABIERTA'" in defaults[("previsiones","estado")]
    assert defaults[("previsiones","recalculo_automatico")] == 'true'
    assert defaults[("previsiones","row_version")] == '1'
    assert ("regla_versiones","moneda") not in defaults
    assert ("regla_versiones","anclaje_recurrencia") not in defaults
    assert ("previsiones","moneda") not in defaults


def test_b03_local_checks_are_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT con.conname FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s) AND con.contype='c'
        """, (sorted(B03_TABLES),))
        names = {r[0] for r in cursor.fetchall()}
    assert names in (
        EXPECTED_CHECKS,
        EXPECTED_CHECKS | SUCESORA_0265_CHECKS,
        EXPECTED_CHECKS | SUCESORA_0265_CHECKS | SUCESORA_0270_CHECKS,
    )


def test_b03_public_has_no_table_dml(db: psycopg.Connection) -> None:
    for table in B03_TABLES:
        assert not _scalar(db, "SELECT has_table_privilege('public', %s, 'INSERT,UPDATE,DELETE')", (f'gapto.{table}',))


def test_b03_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0030_f03_01_tables_b03_reglas_previsiones.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'CREATE INDEX' not in text
    assert 'CREATE UNIQUE INDEX' not in text
    assert 'EXCLUDE USING' not in text
    assert 'CREATE TABLE IF NOT EXISTS' not in text
