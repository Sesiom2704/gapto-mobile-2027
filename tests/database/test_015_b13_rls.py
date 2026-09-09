# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_015_b13_rls.py
# Ruta: tests/database/test_015_b13_rls.py
# Descripción: Verifica F03-01-B13: RLS+FORCE ROW LEVEL SECURITY en las
#              74 tablas tenant, 5 catálogos globales sin RLS, 81
#              policies (67 tenant_isolation + 14 select/insert en las 7
#              append-only). Incluye la prueba funcional real del caso
#              Ana/Berto: un intento de referenciar el actor real de otro
#              owner en efecto_atribuciones debe bloquearse por RLS.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

CATALOG_TABLES_NO_RLS = {
    "paises", "regiones", "localidades", "tipos_hecho", "metricas_definicion",
}


def test_b13_exactly_74_tables_with_rls_and_force(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r'
               AND c.relrowsecurity AND c.relforcerowsecurity
        """)
        (count,) = cursor.fetchone()
    assert count == 74


def test_b13_exactly_5_catalogs_without_rls(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND NOT c.relrowsecurity
        """)
        found = {r[0] for r in cursor.fetchall()}
    assert found == CATALOG_TABLES_NO_RLS


def test_b13_exactly_81_policies(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'")
        (count,) = cursor.fetchone()
    assert count == 81


def test_b13_append_only_tables_have_only_select_and_insert(db: psycopg.Connection) -> None:
    append_only = {
        "auditoria", "cierre_saldos_cuenta", "cierre_presupuesto_lineas",
        "cierre_metricas", "cierre_posiciones_entidad",
        "registros_origen_importacion", "mapeos_importacion",
    }
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT tablename, cmd FROM pg_catalog.pg_policies
             WHERE schemaname='gapto' AND tablename = ANY(%s)
        """, (sorted(append_only),))
        rows = cursor.fetchall()
    by_table: dict[str, set[str]] = {}
    for table, cmd in rows:
        by_table.setdefault(table, set()).add(cmd)
    assert set(by_table.keys()) == append_only
    for table, cmds in by_table.items():
        assert cmds == {"SELECT", "INSERT"}, f"{table}: comandos inesperados {cmds}"


def test_b13_cross_tenant_actor_reference_is_blocked(db: psycopg.Connection) -> None:
    """Caso Ana/Berto: Ana no puede atribuir un efecto propio al actor
    real de Berto (otro owner), aunque ambos existan en la BD."""
    with db.cursor() as cursor:
        # Berto: crea su propio actor self en su propio contexto
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-c1c1-c1c1-c1c1-c1c1c1c1c1c1'")
        cursor.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
            "('99999999-c1c1-c1c1-c1c1-c1c1c1c1c1c1','berto_rls_test@example.com','Berto RLS Test')"
        )
        cursor.execute(
            "INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) VALUES "
            "('99999999-c2c2-c2c2-c2c2-c2c2c2c2c2c2',"
            "'99999999-c1c1-c1c1-c1c1-c1c1c1c1c1c1', NULL)"
        )
        cursor.execute("COMMIT")

        # Ana: intenta atribuir su propio efecto al actor real de Berto
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-a1a1-a1a1-a1a1-a1a1a1a1a1a1'")
        cursor.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
            "('99999999-a1a1-a1a1-a1a1-a1a1a1a1a1a1','ana_rls_test@example.com','Ana RLS Test')"
        )
        cursor.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'")
        (tipo_gasto_id,) = cursor.fetchone()
        cursor.execute(
            "INSERT INTO gapto.hechos_financieros "
            "(id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto, moneda, "
            "estado_localizacion, presupuestable) VALUES "
            "('99999999-a3a3-a3a3-a3a3-a3a3a3a3a3a3',"
            "'99999999-a1a1-a1a1-a1a1-a1a1a1a1a1a1', %s, CURRENT_DATE, "
            "'Test RLS cross-tenant', 'EUR', 'NO_APLICA', true)",
            (tipo_gasto_id,),
        )
        cursor.execute(
            "INSERT INTO gapto.hecho_efectos "
            "(id, hecho_id, tipo_efecto, importe_delta) VALUES "
            "('99999999-a4a4-a4a4-a4a4-a4a4a4a4a4a4',"
            "'99999999-a3a3-a3a3-a3a3-a3a3a3a3a3a3','GASTO',-50.00)"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO gapto.efecto_atribuciones "
                "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) VALUES "
                "('99999999-a4a4-a4a4-a4a4-a4a4a4a4a4a4',"
                "'99999999-c2c2-c2c2-c2c2-c2c2c2c2c2c2',-50.00,'MANUAL')"
            )
        cursor.execute("ROLLBACK")

        # limpieza de lo committeado (Berto)
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "ALTER TABLE gapto.actores_financieros DISABLE TRIGGER "
            "trg_actores_financieros__self_unico"
        )
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-c1c1-c1c1-c1c1-c1c1c1c1c1c1'")
        cursor.execute(
            "DELETE FROM gapto.actores_financieros WHERE id = "
            "'99999999-c2c2-c2c2-c2c2-c2c2c2c2c2c2'"
        )
        cursor.execute(
            "DELETE FROM gapto.usuarios WHERE id = "
            "'99999999-c1c1-c1c1-c1c1-c1c1c1c1c1c1'"
        )
        cursor.execute("COMMIT")
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "ALTER TABLE gapto.actores_financieros ENABLE TRIGGER "
            "trg_actores_financieros__self_unico"
        )
        cursor.execute("COMMIT")


def test_b13_no_context_denies_by_default(db: psycopg.Connection) -> None:
    """Sin gapto.owner_user_id fijado, la consulta debe fallar (cast
    invalido) o devolver 0 filas -- nunca datos de otro owner."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("RESET gapto.owner_user_id")
        with pytest.raises(Exception):
            cursor.execute("SELECT * FROM gapto.hechos_financieros LIMIT 1")
        cursor.execute("ROLLBACK")
