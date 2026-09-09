"""
Fichero: test_005_tables_b06.py
Ruta: tests/database/test_005_tables_b06.py
Descripcion: Verificacion estructural de las 8 tablas materializadas en
    F03-01-B06 (0060_f03_01_tables_b06_presupuestos_cierres.sql):
    presupuestos, presupuesto_lineas, cierres_mensuales,
    cierre_saldos_cuenta, cierre_presupuesto_lineas, metricas_definicion,
    cierre_metricas, cierre_posiciones_entidad.

    NOTA IMPORTANTE (desviacion deliberada del patron B01-B03): este test
    se genera A POSTERIORI, cuando la base de datos ya tiene materializados
    todos los bloques posteriores (B08 anchors/UNIQUE, B09 FK, B10 EXCLUDE,
    B11 indices, B12 invariantes, B13 RLS, B14 grants/guards). Por tanto,
    a diferencia de test_002/003/004, este test NO afirma "sin FK/anchors/
    indices todavia" -- esa afirmacion seria falsa contra el estado actual
    de Neon/Supabase. Se limita a verificar que las 8 tablas existen con
    la estructura exacta (columnas, tipos, nulabilidad, ownership) fijada
    por F03-00, independientemente de que capas posteriores ya existan.

    Requiere una fixture `db_conn` en conftest.py que entregue una
    conexion psycopg abierta contra el proveedor bajo prueba (Neon o
    Supabase), parametrizada por proveedor igual que en tests anteriores.
    Si el nombre/firma real de esa fixture difiere del asumido aqui,
    ajustar unicamente la firma de las funciones de test, no la logica.
Version: 0.1.0
"""

import pytest


B06_TABLES = [
    "presupuestos",
    "presupuesto_lineas",
    "cierres_mensuales",
    "cierre_saldos_cuenta",
    "cierre_presupuesto_lineas",
    "metricas_definicion",
    "cierre_metricas",
    "cierre_posiciones_entidad",
]

# columna -> (nullable esperado, data_type esperado) para las columnas mas
# significativas de cada tabla (no se listan todas para mantener el test
# legible; las columnas listadas son las que fijan contrato/PK/ownership).
EXPECTED_COLUMNS = {
    "presupuestos": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "periodo_desde": (False, "date"),
        "periodo_hasta": (False, "date"),
        "moneda": (False, "character varying"),
        "perspectiva": (False, "character varying"),
        "version_presupuesto": (False, "integer"),
        "reemplaza_presupuesto_id": (True, "uuid"),
        "estado": (False, "character varying"),
        "generado_desde_cierre_id": (True, "uuid"),
        "row_version": (False, "bigint"),
    },
    "presupuesto_lineas": {
        "id": (False, "uuid"),
        "presupuesto_id": (False, "uuid"),
        "tipo_linea": (False, "character varying"),
        "naturaleza_economica": (False, "character varying"),
        "prioridad_consumo": (True, "integer"),
        "importe_objetivo": (False, "numeric"),
        "metodo_estimacion": (False, "character varying"),
        "recalculo_automatico": (False, "boolean"),
    },
    "cierres_mensuales": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "periodo_desde": (False, "date"),
        "periodo_hasta": (False, "date"),
        "cerrado_at": (False, "timestamp with time zone"),
        "origen_cierre": (False, "character varying"),
        "estado": (False, "character varying"),
        "version_cierre": (False, "integer"),
        "reemplaza_cierre_id": (True, "uuid"),
        "row_version": (False, "bigint"),
    },
    "cierre_saldos_cuenta": {
        "id": (False, "uuid"),
        "cierre_id": (False, "uuid"),
        "cuenta_id": (False, "uuid"),
        "moneda": (False, "character varying"),
        "naturaleza": (False, "character varying"),
        "computa_liquidez": (False, "boolean"),
        "computa_patrimonio": (False, "boolean"),
        "saldo_total": (True, "numeric"),
    },
    "cierre_presupuesto_lineas": {
        "id": (False, "uuid"),
        "cierre_id": (False, "uuid"),
        "presupuesto_linea_id": (False, "uuid"),
        "tipo_linea": (False, "character varying"),
        "naturaleza_economica": (False, "character varying"),
        "perspectiva": (False, "character varying"),
        "moneda": (False, "character varying"),
        "importe_objetivo": (False, "numeric"),
        "estado_calculo": (False, "character varying"),
    },
    "metricas_definicion": {
        "id": (False, "uuid"),
        "codigo": (False, "character varying"),
        "nombre": (False, "character varying"),
        "tipo_valor": (False, "character varying"),
        "unidad": (False, "character varying"),
        "enabled": (False, "boolean"),
    },
    "cierre_metricas": {
        "id": (False, "uuid"),
        "cierre_id": (False, "uuid"),
        "metrica_id": (False, "uuid"),
        "valor_numeric": (True, "numeric"),
        "valor_text": (True, "text"),
    },
    "cierre_posiciones_entidad": {
        "id": (False, "uuid"),
        "cierre_id": (False, "uuid"),
        "entidad_id": (False, "uuid"),
        "naturaleza_posicion": (False, "character varying"),
        "dominio_posicion": (False, "character varying"),
        "moneda": (False, "character varying"),
        "incluida_en_total_patrimonio": (False, "boolean"),
    },
}


class TestTablesB06Existence:
    """Las 8 tablas de B06 existen bajo gapto_owner."""

    def test_all_b06_tables_exist(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename, tableowner FROM pg_tables
                WHERE schemaname = 'gapto' AND tablename = ANY(%s)
                """,
                (B06_TABLES,),
            )
            rows = {r[0]: r[1] for r in cur.fetchall()}

        missing = set(B06_TABLES) - set(rows.keys())
        assert not missing, f"Tablas B06 ausentes: {missing}"

        wrong_owner = {t: o for t, o in rows.items() if o != "gapto_owner"}
        assert not wrong_owner, f"Tablas B06 con owner incorrecto: {wrong_owner}"

    def test_b06_table_count_exact(self, db_conn):
        """Exactamente 8 tablas nuevas introducidas por este bloque."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM pg_tables
                WHERE schemaname = 'gapto' AND tablename = ANY(%s)
                """,
                (B06_TABLES,),
            )
            (count,) = cur.fetchone()
        assert count == 8, f"Se esperaban 8 tablas B06; encontradas={count}"


@pytest.mark.parametrize("table_name", B06_TABLES)
class TestTablesB06Columns:
    """Contrato de columnas fijado por F03-00 para cada tabla de B06."""

    def test_expected_columns_present_with_correct_type(self, db_conn, table_name):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, is_nullable, data_type
                FROM information_schema.columns
                WHERE table_schema = 'gapto' AND table_name = %s
                """,
                (table_name,),
            )
            actual = {
                r[0]: (r[1] == "YES", r[2]) for r in cur.fetchall()
            }

        expected = EXPECTED_COLUMNS[table_name]
        for col, (nullable, dtype) in expected.items():
            assert col in actual, f"{table_name}.{col} no existe"
            actual_nullable, actual_dtype = actual[col]
            assert actual_nullable == nullable, (
                f"{table_name}.{col}: nullable esperado={nullable}, "
                f"encontrado={actual_nullable}"
            )
            assert actual_dtype == dtype, (
                f"{table_name}.{col}: data_type esperado={dtype}, "
                f"encontrado={actual_dtype}"
            )

    def test_has_primary_key(self, db_conn, table_name):
        """Toda tabla de B06 tiene PK propia (uuid 'id')."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
                """,
                (f"gapto.{table_name}",),
            )
            pk_cols = [r[0] for r in cur.fetchall()]
        assert pk_cols == ["id"], f"{table_name}: PK esperada=['id'], encontrada={pk_cols}"
