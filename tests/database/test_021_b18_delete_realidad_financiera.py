# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_021_b18_delete_realidad_financiera.py
# Ruta: tests/database/test_021_b18_delete_realidad_financiera.py
# Descripción: Verifica F03-01-B18 (migration 0200): gapto_runtime pierde
#              el DELETE directo sobre las 17 tablas de realidad financiera
#              y conciliación (Bucket A de D-086), conservando SELECT,
#              INSERT y UPDATE sobre todas ellas.
#
#              Comprueba también lo que NO debe cambiar: los Buckets B y C
#              siguen con DELETE porque su decisión está pendiente, las
#              tablas de configuración y planificación lo conservan, y
#              gapto_owner no se ve afectado.
#
# PRECONDICIÓN: requiere F03-01-B16 (migration 0190) para poder asumir
#              gapto_runtime. Ver test_020.
# Versión: 0.2.0  -- B21 cierra D-086: DELETE pasa de 50 a 36 y la muestra de
#                   control pasa a las tres tablas que lo conservan a proposito.
#                   v0.1.1: corrige SET LOCAL parametrizado por set_config().
# ============================================================

from __future__ import annotations

import psycopg
import pytest

# Bucket A de D-086: importes económicos, su conciliación y los snapshots.
SIN_DELETE = (
    "hechos_financieros",
    "hecho_efectos",
    "efecto_atribuciones",
    "hecho_aportaciones_pago",
    "hecho_movimientos_tesoreria",
    "hecho_entidades",
    "hecho_participantes",
    "hecho_terceros",
    "hecho_magnitudes",
    "hecho_relaciones",
    "movimientos_tesoreria",
    "transferencias",
    "cierres_mensuales",
    "financiacion_cuotas",
    "inversion_valoraciones",
    "inversion_asignaciones_efecto",
    "propiedad_valoraciones",
)

# Muestra representativa de lo que B18 deliberadamente NO toca.
CON_DELETE = (
    # Bucket D1 — configuración del usuario
    "acciones_rapidas", "plantillas_registro", "preferencias_ui", "etiquetas", "hecho_etiquetas",
    # Bucket D3 — previsión y planificación, no realidad
    "presupuestos", "presupuesto_lineas", "previsiones", "reglas_financieras",
    # Buckets B y C ya resueltos por B21: aquí solo quedan las que conservan
    # DELETE de forma deliberada (D-105), para detectar un exceso de alcance.
    "entidades", "cuentas", "propiedades",
)


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


@pytest.mark.parametrize("tabla", SIN_DELETE)
def test_b18_bucket_a_sin_delete(db: psycopg.Connection, tabla: str) -> None:
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is False, (
        f"{tabla} es realidad financiera: D-068 no admite hard-delete directo"
    )


@pytest.mark.parametrize("tabla", SIN_DELETE)
def test_b18_bucket_a_conserva_lectura_y_correccion(db: psycopg.Connection, tabla: str) -> None:
    """Revocar DELETE no puede convertir estas tablas en inertes.

    La corrección de un error de captura sigue siendo una edición auditada
    (D-040), así que UPDATE debe permanecer.
    """
    for priv in ("SELECT", "INSERT", "UPDATE"):
        assert _priv(db, "gapto_runtime", tabla, priv) is True, (
            f"{tabla} debe conservar {priv}"
        )


@pytest.mark.parametrize("tabla", CON_DELETE)
def test_b18_no_desborda_su_alcance(db: psycopg.Connection, tabla: str) -> None:
    """B18 cubre solo el Bucket A; B y C siguen pendientes de decisión."""
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is True, (
        f"{tabla} está fuera del alcance de B18 y no debía perder DELETE"
    )


def test_b18_matriz_efectiva_de_runtime(db: psycopg.Connection) -> None:
    """SELECT 79 / INSERT 73 / UPDATE 67 / DELETE 36."""
    assert _cuenta(db, "gapto_runtime", "SELECT") == 79
    assert _cuenta(db, "gapto_runtime", "INSERT") == 73
    assert _cuenta(db, "gapto_runtime", "UPDATE") == 67
    assert _cuenta(db, "gapto_runtime", "DELETE") == 36


def test_b18_no_afecta_a_owner_ni_backup(db: psycopg.Connection) -> None:
    assert _priv(db, "gapto_owner", "hechos_financieros", "DELETE") is True
    assert _cuenta(db, "gapto_backup", "SELECT") == 79
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert _cuenta(db, "gapto_backup", priv) == 0


def test_b18_delete_real_denegado(db: psycopg.Connection) -> None:
    """Prueba efectiva, no lectura del ACL."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE gapto_runtime")
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", ("b18a0000-0000-4000-8000-000000000001",))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    "DELETE FROM gapto.hechos_financieros WHERE id = %s",
                    ("b18a0000-0000-4000-8000-000000000001",),
                )
        finally:
            cursor.execute("ROLLBACK")


def test_b18_delete_permitido_donde_procede(db: psycopg.Connection) -> None:
    """Una etiqueta del usuario sigue siendo borrable: no es realidad financiera."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE gapto_runtime")
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", ("b18a0000-0000-4000-8000-000000000001",))
            cursor.execute(
                "DELETE FROM gapto.etiquetas WHERE id = %s",
                ("b18a0000-0000-4000-8000-000000000001",),
            )
            afectadas = cursor.rowcount
        finally:
            cursor.execute("ROLLBACK")
    assert afectadas == 0  # no hay fila; lo relevante es que no lanzó 42501


def test_b18_d086_cerrado(db: psycopg.Connection) -> None:
    """D-086 cerrado por B21: quedan 36 tablas con DELETE.

    Si este número cambia, es que alguien ha movido la política de borrado.
    Debe actualizarse aquí y en la documentación canónica, nunca silenciarse.
    """
    assert _cuenta(db, "gapto_runtime", "DELETE") == 36
