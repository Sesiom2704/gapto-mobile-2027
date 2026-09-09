# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_018_views_readmodel.py
# Ruta: tests/database/test_018_views_readmodel.py
# Descripción: Verifica las 3 vistas read-model de F03-00-I/F03-01:
#              v_hechos_resumen, v_movimientos_conciliacion,
#              v_previsiones_realizacion. Todas deben ser
#              security_invoker=true (obligatorio, para que respeten el
#              RLS del rol que consulta y no el del owner de la vista).
#              Incluye prueba funcional real: desglose correcto por
#              tipo_efecto sin fusionar naturalezas, y aislamiento
#              cross-tenant efectivo a traves de la vista.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg

VIEWS = {"v_hechos_resumen", "v_movimientos_conciliacion", "v_previsiones_realizacion"}


def test_exactly_3_views_exist(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT viewname FROM pg_catalog.pg_views WHERE schemaname='gapto'")
        found = {r[0] for r in cursor.fetchall()}
    assert found == VIEWS


def test_all_3_views_are_security_invoker(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='v'
               AND c.reloptions @> ARRAY['security_invoker=true']
        """)
        found = {r[0] for r in cursor.fetchall()}
    assert found == VIEWS, (
        f"Todas las vistas deben tener security_invoker=true; "
        f"con la opcion encontradas={found}"
    )


def test_v_hechos_resumen_breaks_down_by_tipo_efecto_without_merging(db: psycopg.Connection) -> None:
    """Prueba funcional: un GASTO de -60 debe aparecer en total_gasto sin
    tocar el resto de columnas de naturaleza distinta."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-e1e1-e1e1-e1e1-e1e1e1e1e1e1'")
        cursor.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
            "('99999999-e1e1-e1e1-e1e1-e1e1e1e1e1e1','test_view@example.com','Test View')"
        )
        cursor.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'")
        (tipo_gasto_id,) = cursor.fetchone()
        cursor.execute(
            "INSERT INTO gapto.hechos_financieros "
            "(id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto, moneda, "
            "estado_localizacion, presupuestable) VALUES "
            "('99999999-e2e2-e2e2-e2e2-e2e2e2e2e2e2',"
            "'99999999-e1e1-e1e1-e1e1-e1e1e1e1e1e1', %s, CURRENT_DATE, "
            "'Test view resumen', 'EUR', 'NO_APLICA', true)",
            (tipo_gasto_id,),
        )
        cursor.execute(
            "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta) "
            "VALUES ('99999999-e3e3-e3e3-e3e3-e3e3e3e3e3e3',"
            "'99999999-e2e2-e2e2-e2e2-e2e2e2e2e2e2','GASTO',-60.00)"
        )
        cursor.execute(
            "SELECT total_gasto, total_ingreso, total_deuda, total_derecho_cobro, "
            "total_inversion, total_valor_activo, num_efectos "
            "FROM gapto.v_hechos_resumen WHERE hecho_id = "
            "'99999999-e2e2-e2e2-e2e2-e2e2e2e2e2e2'"
        )
        row = cursor.fetchone()
        cursor.execute("ROLLBACK")

    total_gasto, total_ingreso, total_deuda, total_derecho_cobro, total_inversion, total_valor_activo, num_efectos = row
    assert total_gasto == -60
    assert total_ingreso == 0
    assert total_deuda == 0
    assert total_derecho_cobro == 0
    assert total_inversion == 0
    assert total_valor_activo == 0
    assert num_efectos == 1


def test_views_respect_rls_of_querying_role_not_owner(db: psycopg.Connection) -> None:
    """security_invoker=true: un owner distinto no debe ver filas de
    otro, incluso a traves de la vista."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-f1f1-f1f1-f1f1-f1f1f1f1f1f1'")
        cursor.execute("SELECT count(*) FROM gapto.v_hechos_resumen")
        (count,) = cursor.fetchone()
        cursor.execute("ROLLBACK")
    assert count == 0, "Un owner sin datos propios no debe ver filas de otros owners via la vista"
