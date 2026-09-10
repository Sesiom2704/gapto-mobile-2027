# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_026_f03_gate_01.py
# Ruta: tests/database/test_026_f03_gate_01.py
# Descripción: F03-GATE-01. Certifica, de forma reejecutable, que el conjunto
#              cerrado hasta B22 cumple el contrato exigido para cerrar F03-01.
#
#              Un gate documentado en un acta envejece en cuanto alguien aplica
#              una migration. Este fichero convierte el gate en aserciones, de
#              modo que cualquier deriva posterior lo rompe.
#
#              Cubre tres de los seis criterios:
#                G2  contrato fisico completo.
#                G5  cero hallazgos abiertos: ninguna policy autorreferente,
#                    ninguna FK tenant sin validar, ningun trigger deshabilitado.
#                G6  inventario de artefactos coherente y con cabecera.
#
#              G1 (alineacion de las cuatro fuentes), G3 (suite verde en ambos
#              proveedores) y G4 (reproducibilidad desde main) NO se comprueban
#              aqui: G1 y G3 no son comprobables desde dentro de una sola
#              conexion, y G4 lo cubre scripts/postgres/run_clean_room.py, que
#              necesita una base virgen.
#
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]

CONTRATO = {
    "tablas": 79,
    "tablas_force_rls": 74,
    "policies": 81,
    "foreign_keys": 166,
    "unique_constraints": 37,
    "exclude_constraints": 11,
    "vistas_security_invoker": 3,
    "funciones": 15,
    "funciones_security_definer": 1,
    "triggers_no_internos": 34,
    "constraint_triggers": 19,
    "guards_append_only": 7,
}

MATRIZ_RUNTIME = {"SELECT": 79, "INSERT": 73, "UPDATE": 67, "DELETE": 36}


def _scalar(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        fila = cursor.fetchone()
    return fila[0] if fila else None


# ------------------------------------------------------------
# G2 - contrato fisico
# ------------------------------------------------------------

def test_gate_g2_contrato_fisico(db: psycopg.Connection) -> None:
    obtenido = {
        "tablas": _scalar(db, "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='gapto'"),
        "tablas_force_rls": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relforcerowsecurity"""),
        "policies": _scalar(db, "SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'"),
        "foreign_keys": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint c
              JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND c.contype='f'"""),
        "unique_constraints": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint c
              JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND c.contype='u'"""),
        "exclude_constraints": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint c
              JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND c.contype='x'"""),
        "vistas_security_invoker": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='v'
               AND c.reloptions @> ARRAY['security_invoker=true']"""),
        "funciones": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='gapto'"""),
        "funciones_security_definer": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='gapto' AND p.prosecdef"""),
        "triggers_no_internos": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal"""),
        "constraint_triggers": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgconstraint <> 0"""),
        "guards_append_only": _scalar(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgname LIKE '%%guard%%'"""),
    }
    assert obtenido == CONTRATO


@pytest.mark.parametrize("privilegio,esperado", sorted(MATRIZ_RUNTIME.items()))
def test_gate_g2_matriz_runtime(db: psycopg.Connection, privilegio: str, esperado: int) -> None:
    total = _scalar(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
         WHERE n.nspname='gapto' AND c.relkind='r'
           AND r.rolname='gapto_runtime' AND acl.privilege_type=%s
    """, (privilegio,))
    assert total == esperado


# ------------------------------------------------------------
# G5 - cero hallazgos abiertos
# ------------------------------------------------------------

def test_gate_g5_sin_policies_autorreferentes(db: psycopg.Connection) -> None:
    """D-094."""
    with db.cursor() as cursor:
        cursor.execute(r"""
            SELECT tablename, policyname FROM pg_catalog.pg_policies p
             WHERE p.schemaname='gapto'
               AND coalesce(p.with_check,'') || coalesce(p.qual,'')
                   ~ ('gapto\.' || p.tablename || '\M')
        """)
        recursivas = cursor.fetchall()
    assert recursivas == []


def test_gate_g5_sin_fk_tenant_sin_validar(db: psycopg.Connection) -> None:
    """D-099."""
    with db.cursor() as cursor:
        cursor.execute("""
            WITH tenant AS (
              SELECT c.oid, c.relname FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='gapto' AND c.relkind='r' AND c.relrowsecurity
            ), fks AS (
              SELECT DISTINCT t.relname AS tabla, att.attname AS columna,
                     array_length(con.conkey,1) AS ncols
                FROM pg_catalog.pg_constraint con
                JOIN tenant t ON t.oid=con.conrelid
                JOIN tenant tf ON tf.oid=con.confrelid
                CROSS JOIN LATERAL unnest(con.conkey) AS k(attnum)
                JOIN pg_catalog.pg_attribute att
                  ON att.attrelid=con.conrelid AND att.attnum=k.attnum
               WHERE con.contype='f' AND att.attname <> 'owner_user_id'
            ), compuestas AS (SELECT tabla, columna FROM fks WHERE ncols>1),
            pol AS (SELECT tablename, string_agg(coalesce(with_check,''),' ') AS wc
                      FROM pg_catalog.pg_policies WHERE schemaname='gapto' GROUP BY tablename)
            SELECT f.tabla, f.columna FROM fks f
              LEFT JOIN pol p ON p.tablename=f.tabla
              LEFT JOIN compuestas cc ON cc.tabla=f.tabla AND cc.columna=f.columna
             WHERE f.ncols=1 AND cc.columna IS NULL
               AND coalesce(p.wc,'') NOT LIKE '%%'||f.columna||'%%'
        """)
        huecos = cursor.fetchall()
    assert huecos == []


def test_gate_g5_sin_triggers_deshabilitados(db: psycopg.Connection) -> None:
    """D-104: el drift del guard en Supabase no puede repetirse en silencio."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, t.tgname, t.tgenabled
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgenabled <> 'O'
        """)
        apagados = cursor.fetchall()
    assert apagados == []


def test_gate_g5_roles_del_modelo_intactos(db: psycopg.Connection) -> None:
    """Los cinco roles siguen siendo de capacidad, no de conexion."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT rolname, rolsuper, rolcanlogin, rolbypassrls, rolcreaterole, rolcreatedb
              FROM pg_catalog.pg_roles WHERE rolname LIKE 'gapto\\_%' ORDER BY rolname
        """)
        filas = cursor.fetchall()
    assert {f[0] for f in filas} == {
        "gapto_owner", "gapto_migrator", "gapto_internal", "gapto_runtime", "gapto_backup",
    }
    for nombre, superusuario, login, bypassrls, crear_rol, crear_bd in filas:
        assert superusuario is False, nombre
        assert login is False, nombre
        assert crear_rol is False, nombre
        assert crear_bd is False, nombre
        assert bypassrls is (nombre == "gapto_backup"), nombre


# ------------------------------------------------------------
# G6 - inventario de artefactos
# ------------------------------------------------------------

def test_gate_g6_inventario_de_migrations() -> None:
    ficheros = sorted((RAIZ / "migrations").glob("*.sql"))
    assert len(ficheros) == 27, [f.name for f in ficheros]

    numeros = [f.name[:4] for f in ficheros]
    assert len(numeros) == len(set(numeros)), "numeracion de migrations duplicada"
    assert numeros == sorted(numeros)
    assert numeros[0] == "0001" and numeros[-1] == "0240"


def test_gate_g6_inventario_de_tests() -> None:
    ficheros = sorted((RAIZ / "tests" / "database").glob("test_*.py"))
    assert len(ficheros) == 26, [f.name for f in ficheros]

    numeros = [f.name[5:8] for f in ficheros]
    assert len(numeros) == len(set(numeros)), f"numeracion duplicada: {numeros}"
    assert numeros == [f"{n:03d}" for n in range(1, 27)]


# Deuda conocida detectada por F03-GATE-01: 0120 nunca llevo cabecera de version
# ni linea Ruta. Es un fichero ya aplicado, de modo que anadirsela es una
# excepcion a forward-only y requiere decision expresa. Mientras no se decida, la
# excepcion vive aqui, a la vista, y no en un comentario perdido.
# 0105 SI la lleva, pero escrita "Version" sin tilde; el patron lo admite a
# proposito, porque exigir la tilde convertiria una inconsistencia cosmetica en
# un fallo de gate.
SIN_CABECERA_ACEPTADO = {
    "0120_f03_01_b13_rls.sql",
}


@pytest.mark.parametrize("relativo", ["migrations", "tests/database"])
def test_gate_g6_cabeceras_versionadas(relativo: str) -> None:
    """Working Method: todo artefacto propio lleva cabecera con version."""
    carpeta = RAIZ / relativo
    patron = "*.sql" if relativo == "migrations" else "*.py"
    sin_version = []
    for fichero in sorted(carpeta.glob(patron)):
        contenido = fichero.read_text(encoding="utf-8")
        if not re.search(r"Versi[oó]n:\s*\d+\.\d+\.\d+", contenido):
            sin_version.append(fichero.name)
    nuevos = sorted(set(sin_version) - SIN_CABECERA_ACEPTADO)
    assert nuevos == [], f"artefactos nuevos sin cabecera de version: {nuevos}"


def test_gate_g6_la_deuda_de_cabeceras_no_crece() -> None:
    """La excepcion es transitoria y debe poder cerrarse.

    Si una de las dos migrations recibe su cabecera, este test obliga a retirarla
    de la lista en vez de dejar la excepcion abierta para siempre.
    """
    carpeta = RAIZ / "migrations"
    todavia_sin = {
        f.name for f in carpeta.glob("*.sql")
        if not re.search(r"Versi[oó]n:\s*\d+\.\d+\.\d+", f.read_text(encoding="utf-8"))
    }
    assert todavia_sin == SIN_CABECERA_ACEPTADO, (
        f"la deuda de cabeceras ha cambiado: ahora es {sorted(todavia_sin)}"
    )


def test_gate_g6_sin_ficheros_muertos() -> None:
    """D-102: los dos ficheros retirados no pueden reaparecer."""
    carpeta = RAIZ / "tests" / "database"
    for nombre in ("test_005_tables_b06.py", "test_006_tables_b07.py"):
        assert not (carpeta / nombre).exists(), f"{nombre} fue retirado por D-102"
