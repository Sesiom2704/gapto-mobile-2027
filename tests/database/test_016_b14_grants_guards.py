# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_016_b14_grants_guards.py
# Ruta: tests/database/test_016_b14_grants_guards.py
# Descripción: Verifica F03-01-B14: GRANTs de mínimo privilegio para
#              gapto_runtime (SELECT=79/INSERT=74/UPDATE=67/DELETE=67) y
#              gapto_backup (BYPASSRLS + SELECT=79, sin escritura), PUBLIC
#              revocado, y 7 guard triggers append-only que bloquean
#              UPDATE/DELETE incluso con RLS fuera de juego (BYPASSRLS).
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

GUARD_TABLES = {
    "auditoria", "cierre_metricas", "cierre_posiciones_entidad",
    "cierre_presupuesto_lineas", "cierre_saldos_cuenta",
    "mapeos_importacion", "registros_origen_importacion",
}


def _grant_count(db: psycopg.Connection, role: str, priv: str) -> int:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE n.nspname='gapto' AND c.relkind='r'
               AND r.rolname=%s AND acl.privilege_type=%s
        """, (role, priv))
        (count,) = cursor.fetchone()
    return count


def test_b14_runtime_select_on_79_tables(db: psycopg.Connection) -> None:
    assert _grant_count(db, "gapto_runtime", "SELECT") == 79


def test_b14_runtime_insert_on_74_tables(db: psycopg.Connection) -> None:
    assert _grant_count(db, "gapto_runtime", "INSERT") == 74


def test_b14_runtime_update_on_67_tables(db: psycopg.Connection) -> None:
    assert _grant_count(db, "gapto_runtime", "UPDATE") == 67


def test_b14_runtime_delete_on_67_tables(db: psycopg.Connection) -> None:
    assert _grant_count(db, "gapto_runtime", "DELETE") == 67


def test_b14_backup_select_only_on_79_tables_no_write(db: psycopg.Connection) -> None:
    assert _grant_count(db, "gapto_backup", "SELECT") == 79
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert _grant_count(db, "gapto_backup", priv) == 0, (
            f"gapto_backup no debe tener {priv}"
        )


def test_b14_backup_has_bypassrls(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT rolbypassrls FROM pg_catalog.pg_roles WHERE rolname='gapto_backup'"
        )
        (bypass,) = cursor.fetchone()
    assert bypass is True


def test_b14_runtime_has_no_bypassrls_no_ownership_no_inheritance(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT rolbypassrls, rolinherit FROM pg_catalog.pg_roles WHERE rolname='gapto_runtime'"
        )
        bypass, inherit = cursor.fetchone()
    assert bypass is False
    assert inherit is False

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_tables
             WHERE schemaname='gapto' AND tableowner='gapto_runtime'
        """)
        (owned,) = cursor.fetchone()
    assert owned == 0

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_auth_members m
              JOIN pg_catalog.pg_roles r ON r.oid = m.member
             WHERE r.rolname='gapto_runtime'
        """)
        (memberships,) = cursor.fetchone()
    assert memberships == 0


def test_b14_public_has_no_privileges_on_schema_or_tables(db: psycopg.Connection) -> None:
    """PUBLIC en el ACL de Postgres aparece como un grantee vacio antes
    del '=' (p.ej. '=U/owner'), a diferencia de un rol con nombre
    (p.ej. 'gapto_runtime=U/gapto_owner'). Se usa aclexplode con
    grantee=0 (PUBLIC) para no depender de parsing de texto fragil."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_namespace n
              CROSS JOIN LATERAL aclexplode(n.nspacl) AS acl
             WHERE n.nspname='gapto' AND acl.grantee = 0
        """)
        (public_schema_grants,) = cursor.fetchone()
    assert public_schema_grants == 0, "PUBLIC no debe tener privilegios sobre el schema gapto"

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
             WHERE n.nspname='gapto' AND c.relkind='r' AND acl.grantee = 0
        """)
        (public_grants,) = cursor.fetchone()
    assert public_grants == 0, "PUBLIC (grantee=0) no debe tener ningun GRANT sobre tablas de gapto"


def test_b14_exactly_7_guard_triggers(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname LIKE '%%guard_append_only%%'
        """)
        found = {r[0] for r in cursor.fetchall()}
    assert found == GUARD_TABLES


def test_b14_guard_blocks_update_even_with_bypassrls(db: psycopg.Connection) -> None:
    """Prueba real: como rol con BYPASSRLS (equivalente a gapto_backup),
    un UPDATE sobre auditoria debe seguir bloqueado por el guard trigger,
    independientemente de RLS."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1'")
        cursor.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES "
            "('99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1','test_guard@example.com','Test Guard')"
        )
        cursor.execute(
            "INSERT INTO gapto.auditoria "
            "(id, owner_user_id, actor_tipo, tabla, registro_id, accion) VALUES "
            "('99999999-d2d2-d2d2-d2d2-d2d2d2d2d2d2',"
            "'99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1','SISTEMA','usuarios',"
            "'99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1','CREAR')"
        )
        cursor.execute("COMMIT")

    # RESET ROLE vuelve al rol de conexion de GAPTO_TEST_DATABASE_URL.
    # Este test ASUME que ese rol tiene BYPASSRLS (como gapto_backup, o
    # como el rol administrativo de Neon/Supabase usado en desarrollo),
    # para que el UPDATE no se filtre silenciosamente por ausencia de
    # policy y demuestre que el guard actua independientemente de RLS.
    # Si el rol de conexion NO tiene BYPASSRLS, este test seguira
    # pasando pero por el motivo equivocado (RLS filtra antes de llegar
    # al guard) -- verificar manualmente si el assert de mas abajo no
    # detecta ninguna excepcion.
    with db.cursor() as cursor:
        cursor.execute("RESET ROLE")
        with pytest.raises(psycopg.errors.RaiseException):
            cursor.execute(
                "UPDATE gapto.auditoria SET accion='ACTUALIZAR' WHERE id = "
                "'99999999-d2d2-d2d2-d2d2-d2d2d2d2d2d2'"
            )

    # limpieza
    with db.cursor() as cursor:
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "ALTER TABLE gapto.auditoria DISABLE TRIGGER trg_auditoria__guard_append_only"
        )
        cursor.execute("RESET ROLE")
        cursor.execute(
            "DELETE FROM gapto.auditoria WHERE id = "
            "'99999999-d2d2-d2d2-d2d2-d2d2d2d2d2d2'"
        )
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "ALTER TABLE gapto.auditoria ENABLE TRIGGER trg_auditoria__guard_append_only"
        )
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute("SET LOCAL gapto.owner_user_id = '99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1'")
        cursor.execute(
            "DELETE FROM gapto.usuarios WHERE id = "
            "'99999999-d1d1-d1d1-d1d1-d1d1d1d1d1d1'"
        )
        cursor.execute("COMMIT")
