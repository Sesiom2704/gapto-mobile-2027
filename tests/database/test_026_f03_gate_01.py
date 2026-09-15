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
# Versión: 0.8.0  -- D-168/D-169. Sucesora 0300 (175 FK) y, sobre todo, los tres
#              criterios del GATE DE RECIERRE F03 que el gate original no tenia
#              y por cuya ausencia el defecto de D-057 llego hasta D-164:
#
#                R1  invariantes NOMBRADAS, no recuentos.
#                R2  ningun anchor contextual (parent_id, id) queda huerfano.
#                R3  barrido de pertenencia hecho-scoped sin FK compuesta.
#
#              R2 es la comprobacion decisiva: el anchor de
#              hecho_movimientos_tesoreria existia desde 0080 SIN consumidor, y
#              un recuento agregado no puede distinguir un anchor consumido de
#              uno huerfano. R1, R2 y R3 deben fallar contra 0290 y pasar contra
#              0300; si pasaran contra ambos, no discriminarian.
#              v0.7.0: sucesora 0290: +1 funcion y +6 constraint triggers por
#              D-080. Version anterior: 0.6.0.  -- G2 acepta la sucesora 0288 (174 FK).
# Versión: 0.5.0  -- G2 acepta la sucesora 0286 y la matriz de runtime sube en 1.
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

# Sucesora conocida: 0286 (D-146 / F02-F01-R2). Anade la tabla puente
# gapto.efecto_cuentas: +1 tabla tenant con FORCE RLS, +1 policy, +3 FK y
# +1 UNIQUE. No anade funciones, triggers ni vistas: la tabla es inerte.
SUCESORA_0286 = {**SUCESORA_0285, "tablas": 80, "tenant_force_rls": 75,
                 "policies": 82, "foreign_keys": 169, "unique_constraints": 41}

# Sucesora conocida: 0288. Endurecimiento declarativo de tenant sobre
# hecho_entidades e inversion_asignaciones_efecto: +5 FK compuestas contra los
# anchors. No cambia ninguna otra magnitud del contrato.
SUCESORA_0288 = {**SUCESORA_0286, "foreign_keys": 174}
# 0290 materializa D-080: una funcion nueva y seis constraint triggers. No
# toca tablas, FK, UNIQUE, EXCLUDE, policies, vistas ni la matriz runtime.
SUCESORA_0290 = {**SUCESORA_0288, "funciones": 26,
                 "triggers_no_internos": 54, "constraint_triggers": 37}
# 0300 repara el DEFECTO 1 de D-168: la FK compuesta de pertenencia
# hecho<->conciliacion aprobada por D-057 y nunca materializada. +1 FK. No crea
# funciones, triggers, policies, columnas ni GRANTs; el indice compuesto de
# D-169/S2 no forma parte de este contrato, que no cuenta indices.
SUCESORA_0300 = {**SUCESORA_0290, "foreign_keys": 175}

# La matriz de runtime la fija B14/B18/B21; 0286 suma efecto_cuentas en
# SELECT, INSERT y UPDATE, y NO en DELETE (bucket A de D-093).
MATRIZ_RUNTIME = {"SELECT": 80, "INSERT": 74, "UPDATE": 68, "DELETE": 36}


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
    if obtenido in (SUCESORA_0270, SUCESORA_0280, SUCESORA_0285, SUCESORA_0286,
                    SUCESORA_0288, SUCESORA_0290, SUCESORA_0300):
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


# ------------------------------------------------------------
# R1/R2/R3 - gate de recierre F03 (D-168 / D-169)
# ------------------------------------------------------------

# R1. Invariantes de pertenencia aprobadas en F03-00-E2-D (D-057), por nombre.
PERTENENCIAS_NOMBRADAS = {
    "fk_hecho_entidades__hecho_efecto":
        ("hecho_entidades", "hecho_efectos", "(hecho_id, efecto_id)"),
    "fk_inversion_asignaciones_efecto__hecho_efecto":
        ("inversion_asignaciones_efecto", "hecho_efectos", "(hecho_id, efecto_inversion_id)"),
    "fk_hecho_aportaciones_pago__hecho_conciliacion":
        ("hecho_aportaciones_pago", "hecho_movimientos_tesoreria",
         "(hecho_id, hecho_movimiento_tesoreria_id)"),
}


@pytest.mark.parametrize("nombre", sorted(PERTENENCIAS_NOMBRADAS))
def test_gate_r1_invariantes_nombradas(db: psycopg.Connection, nombre: str) -> None:
    """R1. El gate historico solo contaba constraints. Un recuento no sabe QUE
    garantiza el esquema: por eso una FK simple pudo ocupar el hueco de una
    compuesta durante toda F03."""
    tabla, destino, columnas = PERTENENCIAS_NOMBRADAS[nombre]
    definicion = _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(con.oid)
          FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='gapto' AND c.relname=%s AND con.conname=%s
           AND con.contype='f' AND con.convalidated
    """, (tabla, nombre))
    assert definicion is not None, f"{nombre} ausente o sin validar en {tabla}"
    assert columnas in definicion and destino in definicion, definicion


def test_gate_r2_ningun_anchor_contextual_huerfano(db: psycopg.Connection) -> None:
    """R2. Todo UNIQUE (parent_id, id) existe para que alguien lo consuma. Un
    anchor sin consumidor es una garantia que se creo y se olvido: es la forma
    exacta que tuvo el defecto de D-057 entre 0080 y 0300."""
    huerfanos = _uno(db, """
        WITH anchors AS (
          SELECT k.conname, k.conindid
            FROM pg_catalog.pg_constraint k
            JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
           WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND k.contype='u'
             AND pg_catalog.array_length(k.conkey,1)=2
             AND (SELECT a.attname FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid=k.conrelid AND a.attnum=k.conkey[2])='id'
        )
        SELECT coalesce(pg_catalog.string_agg(a.conname, ', ' ORDER BY a.conname), '')
          FROM anchors a
         WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint f
                            WHERE f.contype='f' AND f.conindid=a.conindid)
    """)
    assert huerfanos == "", f"anchors contextuales sin consumidor: {huerfanos}"


def test_gate_r3_pertenencia_hecho_scoped_cubierta(db: psycopg.Connection) -> None:
    """R3. Barrido de la familia completa: toda FK simple hijo->padre en la que
    ambos comparten hecho_id debe estar respaldada por una FK compuesta. 0220
    audito la granularidad OWNER y 0288 dos superficies concretas; la
    granularidad HECHO nunca se habia barrido de forma exhaustiva."""
    descubiertos = _uno(db, """
        WITH fk AS (
          SELECT hijo.oid AS hijo_oid, hijo.relname AS hijo, padre.oid AS padre_oid,
                 padre.relname AS padre, k.conname
            FROM pg_catalog.pg_constraint k
            JOIN pg_catalog.pg_class hijo ON hijo.oid=k.conrelid
            JOIN pg_catalog.pg_class padre ON padre.oid=k.confrelid
           WHERE hijo.relnamespace='gapto'::pg_catalog.regnamespace AND k.contype='f'
             AND pg_catalog.array_length(k.conkey,1)=1
             AND EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                          WHERE a.attrelid=hijo.oid AND a.attname='hecho_id'
                            AND a.attnum>0 AND NOT a.attisdropped)
             AND EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                          WHERE a.attrelid=padre.oid AND a.attname='hecho_id'
                            AND a.attnum>0 AND NOT a.attisdropped)
        )
        SELECT coalesce(pg_catalog.string_agg(f.hijo||'.'||f.conname, ', ' ORDER BY f.conname), '')
          FROM fk f
         WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k2
                            WHERE k2.contype='f' AND k2.conrelid=f.hijo_oid
                              AND k2.confrelid=f.padre_oid
                              AND pg_catalog.array_length(k2.conkey,1)=2)
    """)
    assert descubiertos == "", (
        f"FK simples hecho-scoped sin respaldo compuesto: {descubiertos}"
    )


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
