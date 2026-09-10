# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_001_bootstrap.py
# Ruta: tests/database/test_001_bootstrap.py
# Descripción: Verifica el contrato físico de F03-01-B00: plataforma,
#              roles, schemas, extensiones y deny-by-default inicial.
# Versión: 0.1.1
#                   D-098: gapto_backup tiene BYPASSRLS por D-081.
# ============================================================

from __future__ import annotations

from collections.abc import Iterable

import psycopg


GAPTO_ROLES = {
    "gapto_owner",
    "gapto_migrator",
    "gapto_internal",
    "gapto_runtime",
    "gapto_backup",
}


def _scalar(db: psycopg.Connection, sql: str, params: Iterable[object] | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_postgresql_baseline(db: psycopg.Connection) -> None:
    server_version_num = _scalar(
        db,
        "SELECT pg_catalog.current_setting('server_version_num')::integer",
    )
    assert 170000 <= server_version_num < 180000

    assert _scalar(db, "SHOW server_encoding") == "UTF8"
    assert _scalar(db, "SHOW TimeZone") == "UTC"
    assert _scalar(db, "SHOW default_transaction_isolation") == "read committed"

    has_pg_c_utf8 = _scalar(
        db,
        """
        SELECT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_collation AS c
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.collnamespace
             WHERE n.nspname = 'pg_catalog'
               AND c.collname = 'pg_c_utf8'
        )
        """,
    )
    assert has_pg_c_utf8 is True

    uuid_type = _scalar(db, "SELECT pg_catalog.pg_typeof(pg_catalog.gen_random_uuid())::text")
    assert uuid_type == "uuid"


def test_gapto_roles_are_restricted_capability_roles(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                rolname,
                rolsuper,
                rolinherit,
                rolcreaterole,
                rolcreatedb,
                rolcanlogin,
                rolreplication,
                rolbypassrls
              FROM pg_catalog.pg_roles
             WHERE rolname = ANY(%s)
             ORDER BY rolname
            """,
            (sorted(GAPTO_ROLES),),
        )
        rows = cursor.fetchall()

    assert {row[0] for row in rows} == GAPTO_ROLES
    for row in rows:
        rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls = row
        assert rolsuper is False
        assert rolinherit is False
        assert rolcreaterole is False
        assert rolcreatedb is False
        assert rolcanlogin is False
        assert rolreplication is False
        # D-081 concedio BYPASSRLS a gapto_backup de forma deliberada, para que
        # el backup sea completo sin depender del contexto de tenant. Es el unico
        # rol del modelo que puede tenerlo.
        assert rolbypassrls is (rolname == 'gapto_backup'), (
            f"BYPASSRLS inesperado en {rolname}"
        )


def test_migrator_set_role_chain_is_explicit(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                granted.rolname,
                member.rolname,
                am.admin_option,
                am.inherit_option,
                am.set_option
              FROM pg_catalog.pg_auth_members AS am
              JOIN pg_catalog.pg_roles AS granted
                ON granted.oid = am.roleid
              JOIN pg_catalog.pg_roles AS member
                ON member.oid = am.member
             WHERE member.rolname = 'gapto_migrator'
               AND granted.rolname IN ('gapto_owner', 'gapto_internal')
             ORDER BY granted.rolname
            """
        )
        rows = cursor.fetchall()

    assert rows == [
        ("gapto_internal", "gapto_migrator", False, False, True),
        ("gapto_owner", "gapto_migrator", False, False, True),
    ]


def test_schemas_and_extensions(db: psycopg.Connection) -> None:
    gapto_owner = _scalar(
        db,
        """
        SELECT pg_catalog.pg_get_userbyid(n.nspowner)
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto'
        """,
    )
    assert gapto_owner == "gapto_owner"

    gapto_ext_owner = _scalar(
        db,
        """
        SELECT pg_catalog.pg_get_userbyid(n.nspowner)
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto_ext'
        """,
    )
    assert gapto_ext_owner == "gapto_migrator"

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.extname, n.nspname, e.extrelocatable
              FROM pg_catalog.pg_extension AS e
              JOIN pg_catalog.pg_namespace AS n
                ON n.oid = e.extnamespace
             WHERE e.extname IN ('btree_gist', 'pg_trgm')
             ORDER BY e.extname
            """
        )
        extensions = cursor.fetchall()

    assert extensions == [
        ("btree_gist", "gapto_ext", True),
        ("pg_trgm", "gapto_ext", True),
    ]


def test_initial_schema_security_is_deny_by_default(db: psycopg.Connection) -> None:
    for schema in ("gapto", "gapto_ext"):
        assert _scalar(
            db,
            "SELECT pg_catalog.has_schema_privilege('public', %s, 'USAGE')",
            (schema,),
        ) is False
        assert _scalar(
            db,
            "SELECT pg_catalog.has_schema_privilege('public', %s, 'CREATE')",
            (schema,),
        ) is False

    assert _scalar(
        db,
        "SELECT pg_catalog.has_schema_privilege('gapto_owner', 'gapto_ext', 'USAGE')",
    ) is True

    # Esta propiedad debe seguir siendo cierta también después de B14:
    # runtime podrá recibir USAGE sobre gapto, pero nunca CREATE.
    assert _scalar(
        db,
        "SELECT pg_catalog.has_schema_privilege('gapto_runtime', 'gapto', 'CREATE')",
    ) is False
