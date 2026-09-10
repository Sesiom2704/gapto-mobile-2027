# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_022_b19_policies_autorreferentes.py
# Ruta: tests/database/test_022_b19_policies_autorreferentes.py
# Descripción: Verifica F03-01-B19 (migration 0210): ninguna policy vuelve
#              a referenciar su propia tabla, las cuatro tablas afectadas
#              son escribibles bajo RLS, y la garantía de padre del mismo
#              tenant que antes vivía en WITH CHECK sigue vigente, ahora
#              como FK compuesto declarativo.
#
#              El defecto original era 42P17 "infinite recursion detected
#              in policy": categorias_financieras, clasificaciones_tercero,
#              cierres_mensuales y presupuestos NO admitían INSERT desde
#              ningún rol sujeto a RLS, ni siquiera con la columna
#              autorreferente a NULL, porque el fallo ocurre al planificar.
#
# PRECONDICIÓN: requiere F03-01-B16 (migration 0190).
# Versión: 0.1.1  -- corrige SET LOCAL parametrizado por set_config().
# ============================================================

from __future__ import annotations

import psycopg
import pytest

AFECTADAS = {
    "categorias_financieras": "parent_id",
    "clasificaciones_tercero": "parent_id",
    "cierres_mensuales": "reemplaza_cierre_id",
    "presupuestos": "reemplaza_presupuesto_id",
}

OWNER_A = "b19a0000-0000-4000-8000-000000000001"
OWNER_B = "b19b0000-0000-4000-8000-000000000002"
RAIZ = "b19c0000-0000-4000-8000-000000000003"


def _scalar(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        fila = cursor.fetchone()
    return fila[0] if fila else None


def test_b19_ninguna_policy_es_autorreferente(db: psycopg.Connection) -> None:
    """Invariante estructural: una policy nunca debe leer su propia tabla.

    Es la regla general, no solo el parche de las cuatro conocidas: si un
    bloque futuro reintroduce el patrón, este test lo detecta.
    """
    with db.cursor() as cursor:
        cursor.execute(r"""
            SELECT tablename, policyname
              FROM pg_catalog.pg_policies p
             WHERE p.schemaname = 'gapto'
               AND coalesce(p.with_check,'') || coalesce(p.qual,'')
                   ~ ('gapto\.' || p.tablename || '\M')
        """)
        recursivas = cursor.fetchall()
    assert recursivas == [], f"policies autorreferentes: {recursivas}"


@pytest.mark.parametrize("tabla,columna", sorted(AFECTADAS.items()))
def test_b19_fk_compuesto_de_mismo_owner(db: psycopg.Connection, tabla: str, columna: str) -> None:
    """La garantía se mantiene, ahora declarativa."""
    definicion = _scalar(db, """
        SELECT pg_catalog.pg_get_constraintdef(con.oid)
          FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname='gapto' AND c.relname=%s AND con.contype='f'
           AND con.conname LIKE '%%same_owner'
    """, (tabla,))
    assert definicion is not None, f"{tabla} debe tener FK compuesto de mismo owner"
    assert "owner_user_id" in definicion and columna in definicion
    assert "ON DELETE RESTRICT" in definicion


@pytest.mark.parametrize("tabla", sorted(AFECTADAS))
def test_b19_anchor_de_ownership(db: psycopg.Connection, tabla: str) -> None:
    total = _scalar(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname='gapto' AND c.relname=%s AND con.contype='u'
           AND pg_catalog.pg_get_constraintdef(con.oid) = 'UNIQUE (owner_user_id, id)'
    """, (tabla,))
    assert total == 1


@pytest.mark.parametrize("tabla", sorted(AFECTADAS))
def test_b19_force_rls_restaurado(db: psycopg.Connection, tabla: str) -> None:
    """0210 retira FORCE para validar y lo devuelve en la misma transacción."""
    forzada = _scalar(db, """
        SELECT c.relrowsecurity AND c.relforcerowsecurity
          FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname='gapto' AND c.relname=%s
    """, (tabla,))
    assert forzada is True


@pytest.fixture(scope="module")
def tenants_b19(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET LOCAL ROLE gapto_owner")
        for uid, mail in ((OWNER_A, "b19a@example.com"), (OWNER_B, "b19b@example.com")):
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (uid,))
            cursor.execute(
                "INSERT INTO gapto.usuarios (id,email,nombre) VALUES (%s,%s,'B19')",
                (uid, mail),
            )
        cursor.execute("RESET ROLE")
    yield
    with db.cursor() as cursor:
        cursor.execute("ROLLBACK")


def test_b19_runtime_puede_escribir_jerarquia_propia(db: psycopg.Connection, tenants_b19) -> None:
    """Antes de 0210 esto fallaba con 42P17 desde cualquier rol bajo RLS."""
    with db.cursor() as cursor:
        cursor.execute("SAVEPOINT sp")
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
        cursor.execute(
            "INSERT INTO gapto.categorias_financieras "
            "(id, owner_user_id, nombre, ambito, presupuestable_default) "
            "VALUES (%s, %s, 'Raiz', 'GASTO', true)",
            (RAIZ, OWNER_A),
        )
        cursor.execute(
            "INSERT INTO gapto.categorias_financieras "
            "(owner_user_id, nombre, ambito, presupuestable_default, parent_id) "
            "VALUES (%s, 'Hija', 'GASTO', true, %s)",
            (OWNER_A, RAIZ),
        )
        cursor.execute("SELECT count(*) FROM gapto.categorias_financieras")
        (visibles,) = cursor.fetchone()
        cursor.execute("RESET ROLE")
        cursor.execute("ROLLBACK TO SAVEPOINT sp")
    assert visibles == 2


def test_b19_padre_de_otro_tenant_rechazado(db: psycopg.Connection, tenants_b19) -> None:
    """La protección cross-tenant de D-074 sigue viva, ahora vía FK."""
    with db.cursor() as cursor:
        cursor.execute("SAVEPOINT sp")
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
        cursor.execute(
            "INSERT INTO gapto.categorias_financieras "
            "(id, owner_user_id, nombre, ambito, presupuestable_default) "
            "VALUES (%s, %s, 'Raiz', 'GASTO', true)",
            (RAIZ, OWNER_A),
        )
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_B,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cursor.execute(
                "INSERT INTO gapto.categorias_financieras "
                "(owner_user_id, nombre, ambito, presupuestable_default, parent_id) "
                "VALUES (%s, 'Intrusa', 'GASTO', true, %s)",
                (OWNER_B, RAIZ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT sp")
        cursor.execute("RESET ROLE")
