# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_026_f03_gate_01.py
# Ruta: tests/database/test_026_f03_gate_01.py
# Descripción: F03-GATE-01. Convierte el gate en algo reejecutable en vez de
#              un acta que envejece. Cubre tres de sus seis criterios:
#
#                G2  contrato fisico completo, en una sola comprobacion.
#                G5  cero hallazgos abiertos: ninguna policy autorreferente,
#                    ninguna FK tenant sin validar, ningun trigger apagado.
#                G6  inventario de artefactos coherente entre repositorio y
#                    documentacion: numeracion sin duplicados y cabecera de
#                    version en todos los ficheros propios.
#
#              G1 (alineacion de fuentes), G3 (suite verde) y G4
#              (reproducibilidad desde main) no son comprobables desde dentro
#              de la propia suite: G3 es el resultado de ejecutarla, y G4 lo
#              cubre scripts/postgres/run_clean_room.py contra una base virgen.
#
# PRECONDICIÓN: requiere 0190 (B16). Debe ejecutarse desde la raiz del
#              repositorio, porque G6 inspecciona migrations/ y tests/.
# Versión: 0.4.0  -- G2 acepta además EXACTAMENTE la sucesora 0285 (funciones
#                   25, triggers 48, constraint triggers 31).
#                   v0.3.0: G2 acepta además EXACTAMENTE la sucesora 0280 (funciones
#                   21, triggers 40, constraint triggers 30, UNIQUE 40).
#                   v0.2.0: G2 acepta el contrato del gate o EXACTAMENTE su sucesora
#                   conocida 0270 (funciones 19, triggers 39, constraint
#                   triggers 23); el resto del contrato no cambia y cualquier
#                   otra combinacion es drift (Working Method 12C.5).
#                   v0.1.1: G6 inspecciona solo ficheros regulares (is_file): un
#                   directorio que encaje con el patrón (p. ej. __pycache__)
#                   ya no se intenta leer como fichero.
# ============================================================

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent

CONTRATO_ESPERADO = {
    "tablas": 79,
    "tenant_force_rls": 74,
    "catalogos_globales": 5,
    "policies": 81,
    "foreign_keys": 166,
    "unique_constraints": 37,
    "exclude_constraints": 11,
    "funciones": 15,
    "security_definer": 1,
    "vistas_security_invoker": 3,
    "triggers_no_internos": 34,
    "constraint_triggers": 19,
    "guards_append_only": 7,
}

# Sucesora conocida: 0270 (revalidacion desde el padre, R-MON, R-TPN, R-GAR).
SUCESORA_0270 = {**CONTRATO_ESPERADO, "funciones": 19, "triggers_no_internos": 39,
                 "constraint_triggers": 23}

SUCESORA_0280 = {**CONTRATO_ESPERADO, "funciones": 21, "triggers_no_internos": 40,
                 "constraint_triggers": 30, "unique_constraints": 40}

# Sucesora conocida: 0285 (D-121, D-122 E(c), congelacion F(a), same-owner de
# alcances y owner inmutable). Anade 4 funciones y 8 triggers, de los cuales
# uno es constraint trigger (la revalidacion BOLSA del reparenting).
SUCESORA_0285 = {**SUCESORA_0280, "funciones": 25, "triggers_no_internos": 48,
                 "constraint_triggers": 31}

MATRIZ_RUNTIME = {"SELECT": 79, "INSERT": 73, "UPDATE": 67, "DELETE": 36}


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        fila = cursor.fetchone()
    return fila[0] if fila else None


# ------------------------------------------------------------
# G2 - contrato fisico
# ------------------------------------------------------------

def test_gate_g2_contrato_fisico(db: psycopg.Connection) -> None:
    """El contrato completo en una sola comprobacion, no repartido."""
    obtenido = {
        "tablas": _uno(db, "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='gapto'"),
        "tenant_force_rls": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND c.relforcerowsecurity"""),
        "catalogos_globales": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' AND NOT c.relrowsecurity"""),
        "policies": _uno(db, "SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'"),
        "foreign_keys": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND con.contype='f'"""),
        "unique_constraints": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND con.contype='u'"""),
        "exclude_constraints": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname='gapto' AND con.contype='x'"""),
        "funciones": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='gapto'"""),
        "security_definer": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='gapto' AND p.prosecdef"""),
        "vistas_security_invoker": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='v'
               AND c.reloptions @> ARRAY['security_invoker=true']"""),
        "triggers_no_internos": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal"""),
        "constraint_triggers": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgconstraint <> 0"""),
        "guards_append_only": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname LIKE '%%guard%%'"""),
    }
    if obtenido in (SUCESORA_0270, SUCESORA_0280, SUCESORA_0285):
        return
    diferencias = {
        k: (CONTRATO_ESPERADO[k], obtenido[k])
        for k in CONTRATO_ESPERADO if obtenido[k] != CONTRATO_ESPERADO[k]
    }
    assert diferencias == {}, (
        f"contrato fisico desviado del gate y de sus sucesoras conocidas (esperado, obtenido): {diferencias}"
    )


@pytest.mark.parametrize("privilegio,esperado", sorted(MATRIZ_RUNTIME.items()))
def test_gate_g2_matriz_runtime(db: psycopg.Connection, privilegio: str, esperado: int) -> None:
    total = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relkind='r'
           AND r.rolname='gapto_runtime' AND acl.privilege_type=%s
    """, (privilegio,))
    assert total == esperado


# ------------------------------------------------------------
# G5 - cero hallazgos abiertos
# ------------------------------------------------------------

def test_gate_g5_ninguna_policy_autorreferente(db: psycopg.Connection) -> None:
    """Invariante de D-094."""
    with db.cursor() as cursor:
        cursor.execute(r"""
            SELECT tablename, policyname FROM pg_catalog.pg_policies p
             WHERE p.schemaname='gapto'
               AND coalesce(p.with_check,'') || coalesce(p.qual,'')
                   ~ ('gapto\.' || p.tablename || '\M')
        """)
        recursivas = cursor.fetchall()
    assert recursivas == [], f"policies autorreferentes: {recursivas}"


def test_gate_g5_ninguna_fk_tenant_sin_validar(db: psycopg.Connection) -> None:
    """Invariante de D-099."""
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
            pol AS (
              SELECT tablename, string_agg(coalesce(with_check,''),' ') AS wc
                FROM pg_catalog.pg_policies WHERE schemaname='gapto' GROUP BY tablename
            )
            SELECT f.tabla, f.columna FROM fks f
              LEFT JOIN pol p ON p.tablename=f.tabla
              LEFT JOIN compuestas cc ON cc.tabla=f.tabla AND cc.columna=f.columna
             WHERE f.ncols=1 AND cc.columna IS NULL
               AND coalesce(p.wc,'') NOT LIKE '%' || f.columna || '%'
        """)
        sin_validar = cursor.fetchall()
    assert sin_validar == [], f"FK tenant sin validar: {sin_validar}"


def test_gate_g5_ningun_trigger_deshabilitado(db: psycopg.Connection) -> None:
    """Lo que cazo el drift de D-104."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, t.tgname, t.tgenabled
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgenabled <> 'O'
        """)
        apagados = cursor.fetchall()
    assert apagados == [], f"triggers deshabilitados: {apagados}"


# ------------------------------------------------------------
# G6 - inventario de artefactos
# ------------------------------------------------------------

def _ficheros(subruta: str, patron: str) -> list[Path]:
    carpeta = RAIZ / subruta
    if not carpeta.is_dir():
        pytest.skip(f"{carpeta} no accesible; ejecuta pytest desde la raiz del repositorio")
    return sorted(fichero for fichero in carpeta.glob(patron) if fichero.is_file())


def test_gate_g6_inventario_de_migrations() -> None:
    """Prefijos unicos, en orden y arrancando en 0001.

    Baseline en el gate: 27 ficheros hasta 0240. Se afirma como suelo y no
    como igualdad, por la misma razon que D-073: una migration legitima
    posterior no debe hacer fallar el gate historico.
    """
    ficheros = _ficheros("migrations", "*.sql")
    assert len(ficheros) >= 27, [f.name for f in ficheros]
    prefijos = [f.name[:4] for f in ficheros]
    assert len(set(prefijos)) == len(prefijos), f"prefijos duplicados: {prefijos}"
    assert prefijos == sorted(prefijos)
    assert prefijos[0] == "0001"


def test_gate_g6_inventario_de_tests() -> None:
    """Numeracion contigua desde 1, sin duplicados ni huecos.

    Es la propiedad que costo recuperar: hubo dos test_005 y dos test_006, y
    dos ficheros muertos que nunca ejecutaron una asercion.
    """
    ficheros = _ficheros("tests/database", "test_*.py")
    numeros = sorted(int(f.name[5:8]) for f in ficheros)
    assert len(numeros) >= 26, [f.name for f in ficheros]
    assert numeros == list(range(1, len(numeros) + 1)), (
        f"numeracion con duplicados o huecos: {numeros}"
    )


def test_gate_g6_todo_fichero_propio_declara_version() -> None:
    """El Working Method exige cabecera y version en todo artefacto propio."""
    sin_version = []
    for carpeta, patron in (("migrations", "*.sql"), ("tests/database", "*.py"),
                            ("scripts/postgres", "*")):
        for fichero in _ficheros(carpeta, patron):
            texto = fichero.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"Versi[oó]n:\s*\d+\.\d+\.\d+", texto):
                sin_version.append(str(fichero.relative_to(RAIZ)))
    assert sin_version == [], f"artefactos sin cabecera de version: {sin_version}"
