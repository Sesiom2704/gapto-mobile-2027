# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_045_f03_06_0350_tipo_hecho_condonacion.py
# Ruta: tests/database/test_045_f03_06_0350_tipo_hecho_condonacion.py
# Descripción: Verifica F03-06 / migration 0350 (D-201, requerida por
#              F04-D052): arquetipo `CONDONACION` sembrado en gapto.tipos_hecho
#              solo por DML.
#
#              CUERPO REAL DE 0350. Los casos que necesitan el estado anterior
#              (reaplicar, datos preexistentes, seed distinto) ejecutan el
#              cuerpo de migrations/0350_f03_06_tipo_hecho_condonacion.sql
#              extraído de forma determinista del propio fichero (lo que hay
#              entre su única línea `BEGIN;` y su única línea `COMMIT;`),
#              dentro de un SAVEPOINT de una transacción del test que SIEMPRE
#              termina en ROLLBACK. Nada queda escrito ni retirado fuera de
#              esa transacción. El estado «head 0340» se simula borrando la
#              fila CONDONACION con el rol gapto_owner (propietario de la
#              tabla, sin RLS ni triggers; gapto_runtime solo tiene SELECT).
#
#              DATOS PREEXISTENTES. Antes del cuerpo se crean, bajo
#              gapto_owner y con la GUC de un tenant nuevo, un usuario, una
#              categoría y un hecho por cada arquetipo de 0150. Se toma una
#              huella de (id, tipo_hecho_id, row_version, updated_at, xmin) de
#              esas filas y de las siete filas de 0150; tras el cuerpo se
#              exige identidad. xmin delata cualquier UPDATE, aunque no cambie
#              ningún valor. La medida global de todas las filas de la réplica
#              se hace aparte (evidencia de la Fase A, superusuario del cluster
#              desechable), no aquí.
#
#              DISCRIMINACIÓN CONTRA 0340 (WM 12C.2). Sobre una base en head
#              0340 fallan test_0350_fila_con_contrato_d201,
#              test_0350_exactamente_ocho_tipos y
#              test_0350_reaplicar_rechazado_por_precheck (el cuerpo se aplica
#              sin error). Los otros tres casos son GUARDAS que 0340 ya cumple
#              (estructura sin DDL, simulación sobre datos preexistentes y
#              rechazo de un seed distinto de 0150) y discriminan mutantes, no la
#              ausencia de 0350. Gate de mutación: scripts/mutantes/f03_06_0350.py.
#                M1 sin precheck .......... reaplicar, seed_distinto
#                M2 UUID distinto ......... fila_con_contrato_d201,
#                                           test_017 (UUIDv5)
#                M3 código distinto ....... fila_con_contrato_d201, test_017
#                M4 enabled=false ......... fila_con_contrato_d201, test_017
#                M5 fila duplicada ........ exactamente_ocho_tipos, test_017
#                M6 DDL colado ............ estructura_sin_ddl
#                M7 test_017 sin estados .. test_017 (falla en 0350)
#                M8 toca una fila ajena ... datos_preexistentes_intactos (xmin)
#              ON CONFLICT DO NOTHING no es mutante del catálogo: con el precheck
#              presente es equivalente (el reaplicado aborta antes del INSERT);
#              sin precheck lo cubre M1.
# Versión: 0.1.0  -- F03-06 / D-201 / 0350 (B1, Fase A).
# ============================================================

from __future__ import annotations

import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0350_f03_06_tipo_hecho_condonacion.sql"

ID_CONDONACION = "0d216df5-59eb-56c8-998e-7d47953b9351"
NOMBRE_CONDONACION = "Condonacion de derecho u obligacion"
SEED_0150 = {
    "GASTO", "INGRESO", "TRANSFERENCIA", "COMPRA_FINANCIADA",
    "REEMBOLSO", "APORTACION_INVERSION", "GENERACION_DERECHO_OBLIGACION",
}
#: Rol con el que se simula el head 0340 (borrado de la fila) y se crean y
#: leen los datos preexistentes: propietario de las tablas.
ROL_SIMULACION = "gapto_owner"


def cuerpo_0350() -> str:
    """Cuerpo de 0350 sin su control transaccional, extraído del fichero."""
    lineas = MIGRATION.read_bytes().decode("utf-8").split("\n")
    inicio = [i for i, linea in enumerate(lineas) if linea == "BEGIN;"]
    fin = [i for i, linea in enumerate(lineas) if linea == "COMMIT;"]
    assert len(inicio) == 1 and len(fin) == 1 and inicio[0] < fin[0], "0350 no separable de BEGIN/COMMIT"
    return "\n".join(lineas[inicio[0] + 1:fin[0]])


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


@pytest.fixture()
def transaccion(db: psycopg.Connection):
    """Transacción explícita que SIEMPRE termina en ROLLBACK."""
    db.execute("BEGIN")
    try:
        yield db
    finally:
        db.execute("ROLLBACK")
        db.execute("RESET ROLE")


def _simular_0340(db: psycopg.Connection) -> None:
    db.execute(f"SET LOCAL ROLE {ROL_SIMULACION}")
    db.execute("DELETE FROM gapto.tipos_hecho WHERE id = %s", (ID_CONDONACION,))
    db.execute("RESET ROLE")


def _aplicar_cuerpo(db: psycopg.Connection) -> None:
    db.execute("SAVEPOINT s_0350")
    db.execute(cuerpo_0350())


# ------------------------------------------------------------------ estado tras 0350
def test_0350_fila_con_contrato_d201(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT id::text, nombre, enabled FROM gapto.tipos_hecho WHERE codigo = 'CONDONACION'")
        filas = cursor.fetchall()
    assert filas == [(ID_CONDONACION, NOMBRE_CONDONACION, True)]
    assert ID_CONDONACION == str(uuid.uuid5(uuid.NAMESPACE_URL, "gapto2027:tipos_hecho:CONDONACION"))


def test_0350_exactamente_ocho_tipos(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT codigo FROM gapto.tipos_hecho")
        codigos = sorted(r[0] for r in cursor.fetchall())
    assert codigos == sorted(SEED_0150 | {"CONDONACION"})


def test_0350_estructura_sin_ddl(db: psycopg.Connection) -> None:
    """Guarda de regresión: 0350 no toca columnas, constraints, índices,
    triggers, RLS ni ACL de gapto.tipos_hecho."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = 'gapto.tipos_hecho'::regclass AND a.attnum > 0 AND NOT a.attisdropped
             ORDER BY a.attnum""")
        columnas = cursor.fetchall()
        cursor.execute("SELECT conname FROM pg_catalog.pg_constraint WHERE conrelid = 'gapto.tipos_hecho'::regclass")
        constraints = {r[0] for r in cursor.fetchall()}
        cursor.execute("SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname = 'gapto' AND tablename = 'tipos_hecho'")
        indices = {r[0] for r in cursor.fetchall()}
        # Los triggers internos son los RI de las FK que apuntan a tipos_hecho; no son de la tabla.
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_trigger "
                       "WHERE tgrelid = 'gapto.tipos_hecho'::regclass AND NOT tgisinternal")
        triggers = cursor.fetchone()[0]
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_catalog.pg_class WHERE oid = 'gapto.tipos_hecho'::regclass")
        rls = cursor.fetchone()
        # has_table_privilege no depende de la pertenencia del rol de conexión (INHERIT FALSE, D-189).
        cursor.execute("SELECT p FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES',"
                       "'TRIGGER']) p WHERE pg_catalog.has_table_privilege('gapto_runtime', 'gapto.tipos_hecho', p)")
        runtime = {r[0] for r in cursor.fetchall()}
    assert columnas == [("id", "uuid", True), ("codigo", "character varying(50)", True),
                        ("nombre", "character varying(100)", True), ("enabled", "boolean", True)]
    assert constraints == {"pk_tipos_hecho", "ck_tipos_hecho__codigo_formato",
                           "ck_tipos_hecho__nombre_no_blanco", "uq_tipos_hecho__codigo"}
    assert indices == {"pk_tipos_hecho", "uq_tipos_hecho__codigo"}
    assert triggers == 0
    assert rls == (False, False)
    assert runtime == {"SELECT"}


# ------------------------------------------------------------------ cuerpo real de 0350
def test_0350_reaplicar_rechazado_por_precheck(transaccion: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="F03-06-0350 PRECHECK: CONDONACION ya existe"):
        _aplicar_cuerpo(transaccion)


def test_0350_precheck_rechaza_seed_distinto_de_0150(transaccion: psycopg.Connection) -> None:
    _simular_0340(transaccion)
    transaccion.execute(f"SET LOCAL ROLE {ROL_SIMULACION}")
    transaccion.execute("INSERT INTO gapto.tipos_hecho (id, codigo, nombre, enabled) VALUES (%s, 'MUT_EXTRA', 'Extra', true)",
                        (str(uuid.uuid5(uuid.NAMESPACE_URL, "gapto2027:tipos_hecho:MUT_EXTRA")),))
    transaccion.execute("RESET ROLE")
    with pytest.raises(psycopg.errors.RaiseException, match="F03-06-0350 PRECHECK: tipos_hecho no es exactamente el seed de 0150"):
        _aplicar_cuerpo(transaccion)


def _huellas(db: psycopg.Connection) -> dict:
    db.execute(f"SET LOCAL ROLE {ROL_SIMULACION}")
    try:
        consultas = {
            "hechos_financieros": "SELECT id::text || ':' || tipo_hecho_id::text || ':' || row_version || ':' || "
                                  "updated_at::text || ':' || xmin::text FROM gapto.hechos_financieros",
            "categorias_financieras": "SELECT id::text || ':' || row_version || ':' || updated_at::text || ':' || "
                                      "xmin::text FROM gapto.categorias_financieras",
            "usuarios": "SELECT id::text || ':' || row_version || ':' || updated_at::text || ':' || xmin::text "
                        "FROM gapto.usuarios",
            "tipos_hecho_0150": "SELECT id::text || ':' || codigo || ':' || nombre || ':' || enabled::text || ':' || "
                                "xmin::text FROM gapto.tipos_hecho WHERE codigo <> 'CONDONACION'",
        }
        res = {}
        for tabla, sql in consultas.items():
            with db.cursor() as cursor:
                cursor.execute(sql)
                res[tabla] = sorted(r[0] for r in cursor.fetchall())
        return res
    finally:
        db.execute("RESET ROLE")


def test_0350_datos_preexistentes_intactos(transaccion: psycopg.Connection) -> None:
    db = transaccion
    _simular_0340(db)
    owner = uuid.uuid4()
    db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
    db.execute(f"SET LOCAL ROLE {ROL_SIMULACION}")
    db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0350')",
               (owner, f"{owner}@example.invalid"))
    db.execute("INSERT INTO gapto.categorias_financieras (id, owner_user_id, nombre, ambito, presupuestable_default) "
               "VALUES (%s, %s, 'Prexistente 0350', 'GASTO', true)", (uuid.uuid4(), owner))
    with db.cursor() as cursor:
        cursor.execute("SELECT id, codigo FROM gapto.tipos_hecho ORDER BY codigo")
        tipos = cursor.fetchall()
    assert {c for _, c in tipos} == SEED_0150  # estado simulado = head 0340
    for tipo_id, _codigo in tipos:
        db.execute("INSERT INTO gapto.hechos_financieros (owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                   "estado_localizacion, presupuestable) VALUES (%s, %s, DATE '2026-10-01', 'EUR', 'NO_APLICA', false)",
                   (owner, tipo_id))
    db.execute("RESET ROLE")
    antes = _huellas(db)
    assert len(antes["hechos_financieros"]) == 7 and len(antes["tipos_hecho_0150"]) == 7

    _aplicar_cuerpo(db)

    assert _uno(db, "SELECT count(*) FROM gapto.tipos_hecho") == 8
    assert _huellas(db) == antes
