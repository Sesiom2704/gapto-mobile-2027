"""
Fichero: test_006_tables_b07.py
Ruta: tests/database/test_006_tables_b07.py
Descripcion: Verificacion estructural de las 12 tablas materializadas en
    F03-01-B07 (0070_f03_01_tables_b07_documentos_auditoria_importacion.sql):
    documentos, documento_vinculos, etiquetas, hecho_etiquetas, auditoria,
    inversion_asignaciones_efecto, presupuesto_linea_alcances,
    fuentes_importacion, registros_origen_importacion, mapeos_importacion,
    tercero_personas, contrato_revision_renta_versiones.

    Este bloque completa el baseline de 79/79 tablas; por eso incluye
    ademas una verificacion GLOBAL de conteo total (no solo acumulativa
    "al menos N" como en B02/B03, porque 79 es un techo cerrado y estable
    desde este punto en adelante, no un numero que vaya a seguir creciendo
    por bloques posteriores).

    NOTA IMPORTANTE (misma desviacion que test_005_tables_b06.py): este
    test se genera a posteriori contra una base de datos que ya tiene
    materializadas todas las capas posteriores (FK, RLS, indices,
    invariantes, grants). No afirma "sin FK/indices todavia".

    tercero_personas es la unica tabla de este bloque con PK=FK
    (tercero_id), no PK 'id' propia -- es un subtipo 1:0..1 de terceros,
    tal como fija F02-B01. El test de PK lo trata como caso especial.

    Requiere la misma fixture `db_conn` asumida en test_005_tables_b06.py.
Version: 0.1.0
"""

import pytest


B07_TABLES = [
    "documentos",
    "documento_vinculos",
    "etiquetas",
    "hecho_etiquetas",
    "auditoria",
    "inversion_asignaciones_efecto",
    "presupuesto_linea_alcances",
    "fuentes_importacion",
    "registros_origen_importacion",
    "mapeos_importacion",
    "tercero_personas",
    "contrato_revision_renta_versiones",
]

# Excepcion de PK: tabla -> nombre de la columna PK real (cuando no es 'id')
PK_OVERRIDES = {
    "tercero_personas": ["tercero_id"],
}

EXPECTED_COLUMNS = {
    "documentos": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "tipo": (False, "character varying"),
        "nombre_archivo_original": (False, "character varying"),
        "mime_type": (False, "character varying"),
        "size_bytes": (False, "bigint"),
        "estado_archivo": (False, "character varying"),
        "eliminado_at": (True, "timestamp with time zone"),
        "row_version": (False, "bigint"),
    },
    "documento_vinculos": {
        "id": (False, "uuid"),
        "documento_id": (False, "uuid"),
        "hecho_id": (True, "uuid"),
        "entidad_id": (True, "uuid"),
        "tercero_id": (True, "uuid"),
        "cuenta_id": (True, "uuid"),
        "rol_vinculo": (False, "character varying"),
    },
    "etiquetas": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "nombre": (False, "character varying"),
        "enabled": (False, "boolean"),
        "row_version": (False, "bigint"),
    },
    "hecho_etiquetas": {
        "id": (False, "uuid"),
        "hecho_id": (False, "uuid"),
        "etiqueta_id": (False, "uuid"),
        "created_at": (False, "timestamp with time zone"),
    },
    "auditoria": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "actor_tipo": (False, "character varying"),
        "actor_user_id": (True, "uuid"),
        "tabla": (False, "character varying"),
        "registro_id": (False, "uuid"),
        "accion": (False, "character varying"),
        "datos_antes": (True, "jsonb"),
        "datos_despues": (True, "jsonb"),
        "request_id": (True, "uuid"),
    },
    "inversion_asignaciones_efecto": {
        "id": (False, "uuid"),
        "efecto_inversion_id": (False, "uuid"),
        "inversion_entidad_id": (False, "uuid"),
        "importe_asignado": (False, "numeric"),
        "porcentaje_aplicado": (True, "numeric"),
    },
    "presupuesto_linea_alcances": {
        "id": (False, "uuid"),
        "presupuesto_linea_id": (False, "uuid"),
        "categoria_id": (True, "uuid"),
        "entidad_id": (True, "uuid"),
        "incluir_descendientes": (False, "boolean"),
    },
    "fuentes_importacion": {
        "id": (False, "uuid"),
        "owner_user_id": (False, "uuid"),
        "tipo_fuente": (False, "character varying"),
        "nombre_fuente": (False, "character varying"),
        "documento_origen_id": (True, "uuid"),
        "estado": (False, "character varying"),
        "row_version": (False, "bigint"),
    },
    "registros_origen_importacion": {
        "id": (False, "uuid"),
        "fuente_importacion_id": (False, "uuid"),
        "contenedor_origen": (False, "character varying"),
        "datos_origen": (False, "jsonb"),
    },
    "mapeos_importacion": {
        "id": (False, "uuid"),
        "registro_origen_id": (False, "uuid"),
        "tabla_destino": (True, "character varying"),
        "registro_destino_id": (True, "uuid"),
        "tipo_mapping": (False, "character varying"),
        "confianza": (False, "character varying"),
    },
    "tercero_personas": {
        "tercero_id": (False, "uuid"),
        "fecha_nacimiento": (True, "date"),
    },
    "contrato_revision_renta_versiones": {
        "id": (False, "uuid"),
        "contrato_entidad_id": (False, "uuid"),
        "vigente_desde": (True, "date"),
        "vigente_hasta": (True, "date"),
        "tipo_revision": (False, "character varying"),
        "periodicidad_meses": (True, "smallint"),
    },
}


class TestTablesB07Existence:
    """Las 12 tablas de B07 existen bajo gapto_owner."""

    def test_all_b07_tables_exist(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename, tableowner FROM pg_tables
                WHERE schemaname = 'gapto' AND tablename = ANY(%s)
                """,
                (B07_TABLES,),
            )
            rows = {r[0]: r[1] for r in cur.fetchall()}

        missing = set(B07_TABLES) - set(rows.keys())
        assert not missing, f"Tablas B07 ausentes: {missing}"

        wrong_owner = {t: o for t, o in rows.items() if o != "gapto_owner"}
        assert not wrong_owner, f"Tablas B07 con owner incorrecto: {wrong_owner}"

    def test_b07_table_count_exact(self, db_conn):
        """Exactamente 12 tablas nuevas introducidas por este bloque."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM pg_tables
                WHERE schemaname = 'gapto' AND tablename = ANY(%s)
                """,
                (B07_TABLES,),
            )
            (count,) = cur.fetchone()
        assert count == 12, f"Se esperaban 12 tablas B07; encontradas={count}"


class TestBaselineComplete79:
    """B07 completa el baseline fisico de 79/79 tablas (techo cerrado)."""

    def test_total_tables_equals_79(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'gapto'"
            )
            (count,) = cur.fetchone()
        assert count == 79, (
            f"El baseline fisico debe tener exactamente 79 tablas; "
            f"encontradas={count}. Si este numero cambio deliberadamente, "
            f"actualizar este test junto con la decision que lo justifique."
        )

    def test_all_tables_owned_by_gapto_owner(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'gapto' AND tableowner <> 'gapto_owner'
                """
            )
            wrong = [r[0] for r in cur.fetchall()]
        assert not wrong, f"Tablas no propiedad de gapto_owner: {wrong}"


@pytest.mark.parametrize("table_name", B07_TABLES)
class TestTablesB07Columns:
    """Contrato de columnas fijado por F02/F03-00 para cada tabla de B07."""

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
        """Toda tabla de B07 tiene PK; tercero_personas usa PK=FK (tercero_id)."""
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

        expected_pk = PK_OVERRIDES.get(table_name, ["id"])
        assert pk_cols == expected_pk, (
            f"{table_name}: PK esperada={expected_pk}, encontrada={pk_cols}"
        )
