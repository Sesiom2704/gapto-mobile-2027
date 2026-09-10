# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_020_b16_role_chain.py
# Ruta: tests/database/test_020_b16_role_chain.py
# Descripción: Verifica F03-01-B16 (migration 0190): la cadena
#              administrativa SET ROLE alcanza los cinco roles del modelo.
#              Resuelve D-085/D-4, que impedía ejercitar el write-path real
#              como gapto_runtime y dejaba sin cobertura efectiva las
#              pruebas de aislamiento multi-tenant de B13.
#
#              El test comprueba también lo que NO debe cambiar: la
#              corrección es de impersonación, no de privilegios. Ni
#              gapto_runtime ni gapto_backup ganan nada, y gapto_migrator
#              no hereda pasivamente sus privilegios (INHERIT FALSE).
# Versión: 0.1.2  -- corrige el SET LOCAL parametrizado que quedo sin migrar
#                   a set_config() en v0.1.1.
#                   v0.1.1: el conteo DELETE==67 pasa a rango 50/67 por
#                   F03-01-B18. La aserción sigue verificando que 0190 no
#                   movió privilegios de datos, que es su propósito.
# ============================================================

from __future__ import annotations

import psycopg
import pytest

ROLES_ASUMIBLES = ("gapto_migrator", "gapto_owner", "gapto_internal",
                   "gapto_runtime", "gapto_backup")


def _scalar(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return row[0] if row else None


@pytest.mark.parametrize("rol", ROLES_ASUMIBLES)
def test_b16_set_role_alcanzable(db: psycopg.Connection, rol: str) -> None:
    """El rol de conexión debe poder asumir los cinco roles del modelo.

    Desde PostgreSQL 16 no basta con ser miembro: la membresía necesita
    set_option = true. Las que concede el proveedor llegan con
    set_option = false, de ahí 0190.
    """
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute(f"SET LOCAL ROLE {rol}")
            cursor.execute("SELECT current_user")
            (actual,) = cursor.fetchone()
        finally:
            cursor.execute("ROLLBACK")
    assert actual == rol


def test_b16_membresias_con_set_y_sin_inherit(db: psycopg.Connection) -> None:
    """gapto_migrator puede ASUMIR runtime/backup pero no HEREDA sus privilegios."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT r.rolname, am.set_option, am.inherit_option
              FROM pg_catalog.pg_auth_members am
              JOIN pg_catalog.pg_roles r ON r.oid = am.roleid
              JOIN pg_catalog.pg_roles m ON m.oid = am.member
             WHERE m.rolname = 'gapto_migrator'
               AND r.rolname LIKE 'gapto%'
        """)
        filas = {nombre: (set_opt, inh) for nombre, set_opt, inh in cursor.fetchall()}

    esperados = {"gapto_owner", "gapto_internal", "gapto_runtime", "gapto_backup"}
    assert set(filas) == esperados

    for rol, (set_opt, inherit) in filas.items():
        assert set_opt is True, f"gapto_migrator debe poder SET ROLE {rol}"
        assert inherit is False, f"gapto_migrator no debe heredar {rol}"


def test_b16_no_concede_privilegios_nuevos(db: psycopg.Connection) -> None:
    """La corrección es de impersonación, no de privilegios de datos.

    Se re-afirma la matriz de B14/B15 para descartar que 0190 haya movido
    algo por efecto colateral.
    """
    def cuenta(rol: str, priv: str) -> int:
        return _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE n.nspname='gapto' AND c.relkind='r'
               AND r.rolname=%s AND acl.privilege_type=%s
        """, (rol, priv))

    assert cuenta("gapto_runtime", "SELECT") == 79
    assert cuenta("gapto_runtime", "INSERT") == 73
    assert cuenta("gapto_runtime", "UPDATE") == 67  # B18 no toca UPDATE
    # B18 revoca el DELETE del Bucket A; se admiten ambos baselines.
    assert cuenta("gapto_runtime", "DELETE") in (50, 67)
    assert cuenta("gapto_backup", "SELECT") == 79
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert cuenta("gapto_backup", priv) == 0

    # gapto_migrator no adquiere superficie de datos propia.
    assert cuenta("gapto_migrator", "SELECT") == 0


def test_b16_roles_siguen_nologin(db: psycopg.Connection) -> None:
    """0190 no convierte ningún rol conceptual en rol de conexión."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT rolname, rolcanlogin, rolsuper, rolbypassrls
              FROM pg_catalog.pg_roles
             WHERE rolname LIKE 'gapto%' ORDER BY rolname
        """)
        filas = cursor.fetchall()

    esperado_bypassrls = {"gapto_backup"}
    for nombre, canlogin, superuser, bypassrls in filas:
        assert canlogin is False, f"{nombre} debe seguir NOLOGIN"
        assert superuser is False, f"{nombre} no debe ser superusuario"
        assert bypassrls is (nombre in esperado_bypassrls), (
            f"{nombre}: BYPASSRLS inesperado"
        )


def test_b16_aislamiento_tenant_como_runtime_real(db: psycopg.Connection) -> None:
    """Primera comprobación de RLS ejecutada realmente como gapto_runtime.

    Antes de 0190 esto era imposible, y por eso B13 se validó como
    gapto_owner. Se usa `usuarios` por ser la raíz de ownership y no
    requerir fixtures de otras tablas.

    ATENCIÓN: esto NO cierra el hueco de cobertura de B13. Sólo cubre una
    tabla con columna owner_user_id directa. Las 52 tablas tenant con
    ownership derivado por padres siguen sin ejercitarse como runtime.
    """
    a = "b16a0000-0000-4000-8000-000000000001"
    b = "b16b0000-0000-4000-8000-000000000002"

    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE gapto_owner")
            for uid, mail in ((a, "b16.a@example.com"), (b, "b16.b@example.com")):
                cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (uid,))
                cursor.execute(
                    "INSERT INTO gapto.usuarios (id,email,nombre) VALUES (%s,%s,'B16')",
                    (uid, mail),
                )
            cursor.execute("RESET ROLE")

            cursor.execute("SET LOCAL ROLE gapto_runtime")
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (a,))
            cursor.execute(
                "SELECT count(*) FROM gapto.usuarios WHERE id = ANY(%s::uuid[])",
                ([a, b],),
            )
            (visibles,) = cursor.fetchone()

            # Escribir en el tenant ajeno debe fallar por WITH CHECK.
            cursor.execute("SAVEPOINT sp_cross")
            cross_tenant_denegado = False
            try:
                cursor.execute(
                    "UPDATE gapto.usuarios SET nombre='INTRUSO' WHERE id = %s", (b,)
                )
                cross_tenant_denegado = cursor.rowcount == 0
            except psycopg.Error:
                cross_tenant_denegado = True
            cursor.execute("ROLLBACK TO SAVEPOINT sp_cross")
            cursor.execute("RESET ROLE")
        finally:
            cursor.execute("ROLLBACK")

    assert visibles == 1, "gapto_runtime sólo debe ver su propio tenant"
    assert cross_tenant_denegado, "gapto_runtime no debe poder escribir en otro tenant"
