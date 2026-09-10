# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_024_b21_delete_versionado_identidad.py
# Ruta: tests/database/test_024_b21_delete_versionado_identidad.py
# Descripción: Verifica F03-01-B21 (migration 0230), que cierra D-086:
#              gapto_runtime pierde DELETE sobre las 7 tablas de versionado
#              (Bucket B) y sobre las 7 de identidad y trazabilidad con ciclo
#              de vida propio (Bucket C), y lo conserva deliberadamente sobre
#              `entidades`, `cuentas` y `propiedades`, que hoy no tienen
#              alternativa al borrado y quedan protegidas por FK RESTRICT.
#
#              Matriz resultante: SELECT 79 / INSERT 73 / UPDATE 67 / DELETE 36.
#
# PRECONDICIÓN: requiere 0190 (B16) para poder asumir gapto_runtime.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

# Bucket B — versionado. El pasado se sucede, no se borra.
VERSIONADO = (
    "regla_versiones",
    "financiacion_condiciones_versiones",
    "contrato_revision_renta_versiones",
    "inversion_objetivos_versiones",
    "entidad_participaciones",
    "cuenta_participaciones",
    "contrato_participantes",
)

# Bucket C — identidad y trazabilidad con ciclo de vida propio.
IDENTIDAD_SIN_DELETE = (
    "usuarios",
    "inversiones",
    "financiaciones",
    "derechos_obligaciones_financieras",
    "contratos",
    "documentos",
    "fuentes_importacion",
)

# Bucket C — conservan DELETE de forma deliberada: sin ciclo de vida propio,
# el borrado es hoy la única forma de retirar un alta errónea.
IDENTIDAD_CON_DELETE = ("entidades", "cuentas", "propiedades")


def _priv(db: psycopg.Connection, rol: str, tabla: str, priv: str) -> bool:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
            (rol, f"gapto.{tabla}", priv),
        )
        (resultado,) = cursor.fetchone()
    return resultado


def _cuenta(db: psycopg.Connection, rol: str, priv: str) -> int:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE n.nspname='gapto' AND c.relkind='r'
               AND r.rolname=%s AND acl.privilege_type=%s
        """, (rol, priv))
        (total,) = cursor.fetchone()
    return total


@pytest.mark.parametrize("tabla", VERSIONADO)
def test_b21_versionado_sin_delete(db: psycopg.Connection, tabla: str) -> None:
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is False, (
        f"{tabla} versiona condiciones en el tiempo: borrar reinterpreta el pasado"
    )


@pytest.mark.parametrize("tabla", IDENTIDAD_SIN_DELETE)
def test_b21_identidad_sin_delete(db: psycopg.Connection, tabla: str) -> None:
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is False, (
        f"{tabla} tiene ciclo de vida propio o es raíz del tenant"
    )


@pytest.mark.parametrize("tabla", VERSIONADO + IDENTIDAD_SIN_DELETE)
def test_b21_conserva_lectura_y_correccion(db: psycopg.Connection, tabla: str) -> None:
    """Retirar DELETE no puede dejar la tabla inerte.

    La corrección de un error de captura sigue siendo edición auditada (D-040)
    y la sucesión de condiciones sigue siendo un INSERT de versión nueva.
    """
    for priv in ("SELECT", "INSERT", "UPDATE"):
        assert _priv(db, "gapto_runtime", tabla, priv) is True, (
            f"{tabla} debe conservar {priv}"
        )


@pytest.mark.parametrize("tabla", IDENTIDAD_CON_DELETE)
def test_b21_conservan_delete_deliberadamente(db: psycopg.Connection, tabla: str) -> None:
    """Decisión explícita, no descuido.

    `entidades`, `cuentas` y `propiedades` no tienen columna de estado, así que
    sin DELETE no habría forma de retirar un alta errónea. Si algún día
    adquieren ciclo de vida propio, este test debe cambiar junto con una
    migration nueva, nunca silenciarse.
    """
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is True, (
        f"{tabla} conserva DELETE por decisión; revocarlo exige migration y decisión"
    )


def test_b21_esas_tres_siguen_sin_ciclo_de_vida(db: psycopg.Connection) -> None:
    """Justificación viva de la excepción anterior.

    Si alguna de las tres gana una columna de estado, la razón para conservar
    DELETE desaparece y hay que revisar la decisión. Este test lo detecta.
    """
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
                   AND a.attnum > 0 AND NOT a.attisdropped
             WHERE n.nspname='gapto'
               AND c.relname = ANY(%s)
               AND a.attname ~ '(estado|activo|archivad|anulad|baja)'
        """, (list(IDENTIDAD_CON_DELETE),))
        con_estado = [fila[0] for fila in cursor.fetchall()]
    assert con_estado == [], (
        f"{con_estado} ya tienen ciclo de vida: revisar si deben conservar DELETE"
    )


def test_b21_matriz_efectiva_de_runtime(db: psycopg.Connection) -> None:
    """SELECT 79 / INSERT 73 / UPDATE 67 / DELETE 36."""
    assert _cuenta(db, "gapto_runtime", "SELECT") == 79
    assert _cuenta(db, "gapto_runtime", "INSERT") == 73
    assert _cuenta(db, "gapto_runtime", "UPDATE") == 67
    assert _cuenta(db, "gapto_runtime", "DELETE") == 36


def test_b21_delete_real_denegado(db: psycopg.Connection) -> None:
    """Prueba efectiva sobre la raíz del tenant, no lectura del ACL."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE gapto_runtime")
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, true)",
                ("b21a0000-0000-4000-8000-000000000001",),
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    "DELETE FROM gapto.usuarios WHERE id = %s",
                    ("b21a0000-0000-4000-8000-000000000001",),
                )
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


def test_b21_no_afecta_a_owner_ni_backup(db: psycopg.Connection) -> None:
    for tabla in ("usuarios", "regla_versiones", "documentos"):
        assert _priv(db, "gapto_owner", tabla, "DELETE") is True
    assert _cuenta(db, "gapto_backup", "SELECT") == 79
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert _cuenta(db, "gapto_backup", priv) == 0
