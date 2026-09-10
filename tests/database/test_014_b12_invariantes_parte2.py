# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_014_b12_invariantes_parte2.py
# Ruta: tests/database/test_014_b12_invariantes_parte2.py
# Descripción: Verifica F03-01-B12 parte 2: 7 funciones de invariantes de
#              suma multi-fila con locking (participaciones ≤100%,
#              atribuciones, conciliación tesorería, asignaciones de
#              inversión, estructura de transferencias, reversiones,
#              prioridad BOLSA) y sus 9 constraint triggers, TODOS
#              DEFERRABLE INITIALLY DEFERRED. Incluye la prueba
#              funcional real que detectó el bug de la sesión original
#              (trigger inmediato bloqueaba reparto en varios pasos).
# Versión: 0.1.1  -- D-098: el reparto en dos pasos usaba el MISMO actor y
#                   chocaba con uq_efecto_atribuciones__efecto_actor.
#                   v0.1.0 anterior.
# ============================================================

from __future__ import annotations

import psycopg
import pytest

PARTE2_FUNCTIONS = {
    "fn_check_participacion_suma",
    "fn_check_atribucion_suma",
    "fn_check_hecho_mov_tesoreria_suma",
    "fn_check_inversion_asignacion_suma",
    "fn_check_transferencia_estructura",
    "fn_check_reversion_movimiento",
    "fn_check_bolsa_prioridad",
}

PARTE2_TRIGGERS = {
    "trg_cuenta_participaciones__suma_100",
    "trg_entidad_participaciones__suma_100",
    "trg_efecto_atribuciones__suma",
    "trg_hecho_efectos__atribucion_suma",
    "trg_hecho_movimientos_tesoreria__suma",
    "trg_inversion_asignaciones_efecto__suma",
    "trg_transferencias__estructura",
    "trg_movimientos_tesoreria__reversion",
    "trg_presupuesto_lineas__bolsa_prioridad",
}


def test_b12p2_seven_functions_exist(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='gapto' AND p.proname = ANY(%s)
        """, (sorted(PARTE2_FUNCTIONS),))
        found = {r[0] for r in cursor.fetchall()}
    assert found == PARTE2_FUNCTIONS


def test_b12p2_nine_triggers_all_deferred(db: psycopg.Connection) -> None:
    """Los 9 triggers de parte 2 son CONSTRAINT TRIGGER DEFERRABLE
    INITIALLY DEFERRED sin excepcion -- correccion aplicada tras
    detectar que un trigger inmediato bloqueaba transacciones legitimas
    construidas en varios pasos (ej. repartir un gasto entre 2 actores)."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname = ANY(%s) AND t.tgdeferrable AND t.tginitdeferred
        """, (sorted(PARTE2_TRIGGERS),))
        found = {r[0] for r in cursor.fetchall()}
    assert found == PARTE2_TRIGGERS


def test_b12p2_no_immediate_triggers_leaked(db: psycopg.Connection) -> None:
    """Ninguno de los 9 debe quedar como inmediato -- el bug original."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname = ANY(%s) AND NOT t.tgdeferrable
        """, (sorted(PARTE2_TRIGGERS),))
        leaked = [r[0] for r in cursor.fetchall()]
    assert leaked == [], f"Triggers de parte 2 sin DEFERRABLE (regresion del bug original): {leaked}"


def test_b12p2_multistep_attribution_completes_within_transaction(db: psycopg.Connection) -> None:
    """Prueba funcional real: repartir un gasto de 100 en dos INSERT
    dentro de la misma transaccion debe funcionar (motivo original de
    la correccion a DEFERRED)."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET ROLE gapto_owner")
            cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-4444-4444-4444-444444444444'")
            cursor.execute(
                "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
                "('99999999-4444-4444-4444-444444444444','test_b12p2@example.com','Test B12P2')"
            )
            # D-098: uq_efecto_atribuciones__efecto_actor impide dos atribuciones
            # del MISMO actor sobre el mismo efecto. Para probar el reparto en
            # varios pasos hacen falta dos actores distintos.
            cursor.execute(
                "INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) VALUES "
                "('99999999-5555-5555-5555-555555555555',"
                "'99999999-4444-4444-4444-444444444444', NULL)"
            )
            # El segundo actor necesita un tercero: uq_actores_financieros__owner_tercero
            # solo admite un actor propio (tercero_id NULL) por tenant.
            cursor.execute(
                "INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) VALUES "
                "('99999999-3333-3333-3333-333333333333',"
                "'99999999-4444-4444-4444-444444444444','Tercero B12P2','PERSONA')"
            )
            cursor.execute(
                "INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) VALUES "
                "('99999999-5555-5555-5555-555555555556',"
                "'99999999-4444-4444-4444-444444444444',"
                "'99999999-3333-3333-3333-333333333333')"
            )
            cursor.execute(
                "SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'"
            )
            (tipo_gasto_id,) = cursor.fetchone()
            cursor.execute(
                "INSERT INTO gapto.hechos_financieros "
                "(id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto, moneda, "
                "estado_localizacion, presupuestable) VALUES "
                "('99999999-6666-6666-6666-666666666666',"
                "'99999999-4444-4444-4444-444444444444', %s, CURRENT_DATE, "
                "'Test B12P2 reparto', 'EUR', 'NO_APLICA', true)",
                (tipo_gasto_id,),
            )
            cursor.execute(
                "INSERT INTO gapto.hecho_efectos "
                "(id, hecho_id, tipo_efecto, importe_delta, estado_atribucion) VALUES "
                "('99999999-7777-7777-7777-777777777777',"
                "'99999999-6666-6666-6666-666666666666','GASTO',-100.00,'COMPLETA')"
            )
            # reparto en DOS pasos dentro de la misma transaccion: debe
            # funcionar porque el trigger es DEFERRED (se evalua al COMMIT)
            cursor.execute(
                "INSERT INTO gapto.efecto_atribuciones "
                "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) VALUES "
                "('99999999-7777-7777-7777-777777777777',"
                "'99999999-5555-5555-5555-555555555555',-70.00,'MANUAL')"
            )
            cursor.execute(
                "INSERT INTO gapto.efecto_atribuciones "
                "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) VALUES "
                "('99999999-7777-7777-7777-777777777777',"
                "'99999999-5555-5555-5555-555555555556',-30.00,'MANUAL')"
            )
        finally:
            cursor.execute("ROLLBACK")


def test_b12p2_incomplete_attribution_fails_at_commit(db: psycopg.Connection) -> None:
    """Contraprueba: dejar la suma incompleta debe seguir fallando,
    solo que en el COMMIT en vez de en el INSERT inmediato."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-8888-8888-8888-888888888888'")
        cursor.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
            "('99999999-8888-8888-8888-888888888888','test_b12p2b@example.com','Test B12P2 B')"
        )
        cursor.execute(
            "INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) VALUES "
            "('99999999-9999-9999-9999-999999999999',"
            "'99999999-8888-8888-8888-888888888888', NULL)"
        )
        cursor.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'")
        (tipo_gasto_id,) = cursor.fetchone()
        cursor.execute(
            "INSERT INTO gapto.hechos_financieros "
            "(id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto, moneda, "
            "estado_localizacion, presupuestable) VALUES "
            "('99999999-aaaa-aaaa-aaaa-aaaaaaaaaaaa',"
            "'99999999-8888-8888-8888-888888888888', %s, CURRENT_DATE, "
            "'Test B12P2 incompleto', 'EUR', 'NO_APLICA', true)",
            (tipo_gasto_id,),
        )
        cursor.execute(
            "INSERT INTO gapto.hecho_efectos "
            "(id, hecho_id, tipo_efecto, importe_delta, estado_atribucion) VALUES "
            "('99999999-bbbb-bbbb-bbbb-bbbbbbbbbbbb',"
            "'99999999-aaaa-aaaa-aaaa-aaaaaaaaaaaa','GASTO',-100.00,'COMPLETA')"
        )
        cursor.execute(
            "INSERT INTO gapto.efecto_atribuciones "
            "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) VALUES "
            "('99999999-bbbb-bbbb-bbbb-bbbbbbbbbbbb',"
            "'99999999-9999-9999-9999-999999999999',-70.00,'MANUAL')"
        )
        with pytest.raises(psycopg.errors.RaiseException):
            cursor.execute("COMMIT")
        cursor.execute("ROLLBACK")
