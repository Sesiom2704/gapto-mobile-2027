# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_007_tables_b06.py
# Ruta: tests/database/test_007_tables_b06.py
# Descripción: Verifica el contrato físico F03-01-B06 de las tablas 60..67:
#              presupuestos, presupuesto_lineas, cierres_mensuales y sus
#              cuatro snapshots (saldos de cuenta, líneas presupuestarias,
#              métricas, posiciones patrimoniales), más metricas_definicion
#              (catálogo de sistema, sin RLS, seed aparte en F03-01 seeds).
# Versión: 0.1.1
#                   D-098: expectativa caducada migrada a validacion de
#                   propiedad/baseline. El layering se sigue verificando a
#                   nivel de fichero de migration, que es donde es cierto de
#                   forma permanente, y no contra el estado acumulado de la BD.
# ============================================================

from __future__ import annotations

from pathlib import Path

import psycopg

B06_TABLES = {
    "presupuestos", "presupuesto_lineas", "cierres_mensuales",
    "cierre_saldos_cuenta", "cierre_presupuesto_lineas", "metricas_definicion",
    "cierre_metricas", "cierre_posiciones_entidad",
}
B01_B05_TABLES = {
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
    # B05: dominios especializados (propiedades, contratos, servicios,
    # financiaciones, inversiones, derechos/obligaciones)
    "propiedades", "propiedad_valoraciones", "contratos", "contrato_participantes",
    "servicios", "propiedad_servicios", "contrato_servicios",
    "financiaciones", "financiacion_condiciones_versiones", "financiacion_cuotas",
    "inversiones", "inversion_objetivos_versiones", "inversion_valoraciones",
    "derechos_obligaciones_financieras",
}
B06_BASELINE_TABLES = B01_B05_TABLES | B06_TABLES


def test_b06_tables_exist_and_are_owned_by_gapto_owner(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner)
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
        """, (sorted(B06_TABLES),))
        rows = cursor.fetchall()
    assert {r[0] for r in rows} == B06_TABLES
    assert all(r[1] == 'gapto_owner' for r in rows)


def test_b06_baseline_67_tables_remain_materialized(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname = ANY(%s)
            """,
            (sorted(B06_BASELINE_TABLES),),
        )
        actual = {row[0] for row in cursor.fetchall()}
    assert actual == B06_BASELINE_TABLES
    assert len(B06_BASELINE_TABLES) == 67


def test_b06_cierres_snapshots_have_no_row_version(db: psycopg.Connection) -> None:
    """Los snapshots 63..67 son inmutables por privilegios/guard (F03-00-H),
    no por optimistic locking: no deben tener row_version."""
    snapshots = {"cierre_saldos_cuenta", "cierre_presupuesto_lineas",
                 "cierre_metricas", "cierre_posiciones_entidad"}
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname = ANY(%s)
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """, (sorted(snapshots),))
        found = {r[0] for r in cursor.fetchall()}
    assert found == set(), f"Snapshots con row_version inesperado: {found}"


def test_b06_presupuestos_cierres_have_row_version(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relname IN ('presupuestos','cierres_mensuales')
               AND a.attname='row_version' AND a.attnum>0 AND NOT a.attisdropped
        """)
        found = {r[0] for r in cursor.fetchall()}
    assert found == {"presupuestos", "cierres_mensuales"}


def test_b06_migration_respects_layering() -> None:
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '0060_f03_01_tables_b06_presupuestos_cierres.sql'
    text = migration.read_text(encoding='utf-8').upper()
    assert 'FOREIGN KEY' not in text
    assert 'CREATE INDEX' not in text
    assert 'CREATE UNIQUE INDEX' not in text
    assert 'EXCLUDE USING' not in text
    assert 'CREATE TABLE IF NOT EXISTS' not in text
