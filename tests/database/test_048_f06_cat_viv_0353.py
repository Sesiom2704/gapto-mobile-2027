# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_048_f06_cat_viv_0353.py
# Ruta: tests/database/test_048_f06_cat_viv_0353.py
# Descripción: Verifica la migration 0353 (T2-F06 CAT-VIV; reapertura parcial
#              de F03 por L-03; mandato CAT-VIV v1.1 §2.1.9; Q-CV-01, AJ-T2-07).
#
#              CONTRATO. categorias_financieras.asociada_vivienda boolean NOT
#              NULL (por pg_attribute.attnotnull) DEFAULT false, sin ACL propia,
#              sin indice, CHECK, FK ni trigger nuevos; FORCE RLS restaurado;
#              privilegios heredados de la tabla.
#
#              HUELLA CURRENT. Las ocho huellas D-111 y sus recuentos son
#              HUELLAS_D111_POR_HEAD['0353'] del runner; DESVIACIÓN frente a
#              0352: solo h1 y los recuentos (788 columnas). h2 es identica en
#              PostgreSQL <= 17 (los NOT NULL no viven en pg_constraint y el
#              DEFAULT lo cubre h1); h3..h8 identicas. Runner con 0353 declarado
#              y 0352 conservado (R-0352-14).
#
#              APLICACION SIMULADA SOBRE FILAS PREEXISTENTES. Dentro de UNA
#              transaccion que termina SIEMPRE en ROLLBACK: se retira la columna
#              (queda attisdropped, fuera de h1), se crean categorias sinteticas
#              como gapto_owner con la GUC de tenant, se vacian los eventos
#              diferidos (SET CONSTRAINTS ALL IMMEDIATE, D-173) y se ejecuta el
#              cuerpo LITERAL del fichero 0353 sin su BEGIN/COMMIT. Asi mueren
#              los mutantes de la migration (DEFAULT true, sin NOT NULL, GRANT
#              de columna, sin FORCE, precheck sin la marca de 0352).
#
#              DISCRIMINACIÓN CONTRA 0352 (WM 12C.2). Sobre una base en 0352
#              fallan la huella, el contrato, el comportamiento y la aplicacion
#              simulada (no existe la columna): el modulo solo pasa con 0353.
# Versión: 0.1.0  -- T2-F06 CAT-VIV N1 (mandato v1.1, lote 34; L-03).
# ============================================================
from __future__ import annotations

import importlib.util
import os
import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0353_f06_01_categoria_asociada_vivienda.sql"
OWNER = "0353a000-0000-4000-8000-000000000001"
OTRO_OWNER = "0353a000-0000-4000-8000-000000000002"
TRIGGERS_TABLA = {
    "trg_categorias_financieras__aciclica",
    "trg_categorias_financieras__bolsa_reparenting",
    "trg_categorias_financieras__deriva_d122",
    "trg_categorias_financieras__owner_inmutable",
}


def _runner():
    spec = importlib.util.spec_from_file_location("rcr_048", RAIZ / "scripts" / "postgres" / "run_clean_room.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def db():
    url = os.environ.get("GAPTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GAPTO_TEST_DATABASE_URL no definida")
    con = psycopg.connect(url)
    con.execute("SET ROLE gapto_owner")
    yield con
    con.rollback()
    con.close()


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cur:
        cur.execute(sql, params)
        fila = cur.fetchone()
    return fila[0] if fila else None


def _huellas(db: psycopg.Connection) -> dict:
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    return dict(zip([d.name for d in cursor.description], cursor.fetchone()))


def cuerpo_0353() -> str:
    """Cuerpo de 0353 sin su control transaccional, extraido del fichero."""
    texto = MIGRATION.read_text(encoding="utf-8")
    inicio = texto.index("BEGIN;") + len("BEGIN;")
    fin = texto.rindex("COMMIT;")
    return texto[inicio:fin]


class Escenario:
    """Un owner con categorias sinteticas (GASTO, INGRESO, AMBOS y un hijo)."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0353') ON CONFLICT DO NOTHING",
                   (OWNER, f"{uuid.uuid4()}@example.invalid"))

    def categoria(self, ambito: str = "GASTO", parent: str | None = None, *, con_marca: bool | None = None) -> str:
        cid = str(uuid.uuid4())
        if con_marca is None:
            self.db.execute(
                "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
                "presupuestable_default) VALUES (%s, %s, %s, %s, %s, true)",
                (cid, OWNER, parent, f"Cat {cid[:8]}", ambito))
        else:
            self.db.execute(
                "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
                "presupuestable_default, asociada_vivienda) VALUES (%s, %s, %s, %s, %s, true, %s)",
                (cid, OWNER, parent, f"Cat {cid[:8]}", ambito, con_marca))
        return cid

    def marca(self, cid: str):
        return _uno(self.db, "SELECT asociada_vivienda FROM gapto.categorias_financieras WHERE id = %s", (cid,))


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


def _como_runtime(db: psycopg.Connection) -> None:
    db.execute("SAVEPOINT r")
    try:
        db.execute("RESET ROLE")
        db.execute("SET ROLE gapto_runtime")
    except psycopg.errors.InsufficientPrivilege:
        db.execute("ROLLBACK TO SAVEPOINT r")
        pytest.skip("El rol del arnés no puede asumir gapto_runtime: cobertura no ejercitada.")


# ------------------------------------------------------------------ huella y desviación
def test_0353_huella_d111_current(db: psycopg.Connection) -> None:
    referencia = _runner().HUELLAS_D111_POR_HEAD["0353"]
    observadas = _huellas(db)
    assert {k: observadas[k] for k in referencia} == referencia


def test_0353_desviacion_frente_a_0352_solo_h1_y_recuentos() -> None:
    huellas = _runner().HUELLAS_D111_POR_HEAD
    distintas = {k for k in huellas["0353"] if huellas["0353"][k] != huellas["0352"][k]}
    assert distintas == {"h1_columnas", "recuentos"}
    assert huellas["0352"]["recuentos"] == "787/652/287/82/58/28/1024/3"
    assert huellas["0353"]["recuentos"] == "788/652/287/82/58/28/1024/3"


def test_0353_runner_declara_0353_y_conserva_0352() -> None:
    runner = _runner()
    assert runner.CONTRATOS_POR_HEAD["0353"] == runner.CONTRATOS_POR_HEAD["0352"]
    assert runner.CONTRATO_POR_DEFECTO == runner.CONTRATOS_POR_HEAD["0353"]
    exigidos = runner.TESTS_EXIGIDOS_POR_HEAD
    assert exigidos["0353"] == (*exigidos["0352"], "test_048_f06_cat_viv_0353")
    assert "test_048_f06_cat_viv_0353" not in exigidos["0352"]
    assert {"0352", "0353"} <= set(runner.HEADS_QUE_EXIGEN_REFERENCIA_D111)


# ------------------------------------------------------------------ contrato
def test_0353_columna_boolean_not_null_default_false(db: psycopg.Connection) -> None:
    with db.cursor() as cur:
        cur.execute("""
            SELECT pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,
                   pg_catalog.pg_get_expr(d.adbin, d.adrelid), a.attacl IS NULL
              FROM pg_catalog.pg_attribute a
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = 'gapto.categorias_financieras'::regclass
               AND a.attname = 'asociada_vivienda' AND NOT a.attisdropped
        """)
        fila = cur.fetchone()
    assert fila == ("boolean", True, "false", True), "boolean NOT NULL (attnotnull) DEFAULT false sin ACL propia"


def test_0353_sin_constraint_indice_ni_trigger_nuevos(db: psycopg.Connection) -> None:
    # NOT NULL (contype 'n' en PostgreSQL 18) no cuenta: el control es por attnotnull.
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_attribute a ON a.attrelid = k.conrelid AND a.attname = 'asociada_vivienda'
         WHERE k.conrelid = 'gapto.categorias_financieras'::regclass AND k.contype <> 'n'
           AND a.attnum = ANY (k.conkey)
    """) == 0
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_index i
          JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attname = 'asociada_vivienda'
         WHERE i.indrelid = 'gapto.categorias_financieras'::regclass AND a.attnum = ANY (i.indkey)
    """) == 0
    with db.cursor() as cur:
        cur.execute("""
            SELECT t.tgname, EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                                      WHERE a.attrelid = t.tgrelid AND a.attname = 'asociada_vivienda'
                                        AND a.attnum = ANY (t.tgattr))
              FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = 'gapto.categorias_financieras'::regclass AND NOT t.tgisinternal
        """)
        filas = cur.fetchall()
    assert {f[0] for f in filas} == TRIGGERS_TABLA
    assert not any(f[1] for f in filas)
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c "
                    "ON c.oid = k.conrelid WHERE c.relnamespace = 'gapto'::regnamespace AND k.contype <> 'n'") == 652


def test_0353_force_rls_restaurado(db: psycopg.Connection) -> None:
    assert _uno(db, "SELECT relrowsecurity AND relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid = 'gapto.categorias_financieras'::regclass") is True
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace = 'gapto'::regnamespace "
                    "AND c.relkind = 'r' AND c.relrowsecurity AND c.relforcerowsecurity") == 75


def test_0353_privilegios_heredados(db: psycopg.Connection) -> None:
    for rol, priv in (("gapto_runtime", "SELECT"), ("gapto_runtime", "INSERT"),
                      ("gapto_runtime", "UPDATE"), ("gapto_backup", "SELECT")):
        assert _uno(db, "SELECT has_column_privilege(%s, 'gapto.categorias_financieras', "
                        "'asociada_vivienda', %s)", (rol, priv)) is True, f"{rol} {priv}"
    for priv in ("INSERT", "UPDATE"):
        assert _uno(db, "SELECT has_column_privilege('gapto_backup', 'gapto.categorias_financieras', "
                        "'asociada_vivienda', %s)", (priv,)) is False


# ------------------------------------------------------------------ comportamiento
def test_0353_alta_sin_la_columna_queda_en_false(esc: Escenario) -> None:
    cid = esc.categoria()
    assert esc.marca(cid) is False


def test_0353_no_se_hereda_de_padre_a_hijo(esc: Escenario) -> None:
    padre = esc.categoria(con_marca=True)
    hijo = esc.categoria(parent=padre)
    assert esc.marca(padre) is True and esc.marca(hijo) is False


def test_0353_null_rechazado(esc: Escenario) -> None:
    esc.db.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.NotNullViolation):
        esc.db.execute(
            "INSERT INTO gapto.categorias_financieras (id, owner_user_id, nombre, ambito, presupuestable_default, "
            "asociada_vivienda) VALUES (%s, %s, 'nula', 'GASTO', true, NULL)", (str(uuid.uuid4()), OWNER))
    esc.db.execute("ROLLBACK TO SAVEPOINT s")


def test_0353_runtime_edita_la_marca_propia(esc: Escenario) -> None:
    cid = esc.categoria()
    _como_runtime(esc.db)
    esc.db.execute("UPDATE gapto.categorias_financieras SET asociada_vivienda = true WHERE id = %s", (cid,))
    assert esc.marca(cid) is True


def test_0353_runtime_no_ve_la_marca_ajena(esc: Escenario) -> None:
    cid = esc.categoria(con_marca=True)
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
    _como_runtime(esc.db)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.categorias_financieras WHERE id = %s", (cid,)) == 0
    with esc.db.cursor() as cur:
        cur.execute("UPDATE gapto.categorias_financieras SET asociada_vivienda = false WHERE id = %s", (cid,))
        assert cur.rowcount == 0


# ------------------------------------------------------------------ aplicación simulada (filas preexistentes)
def _retirar_columna(db: psycopg.Connection) -> None:
    db.execute("ALTER TABLE gapto.categorias_financieras DROP COLUMN asociada_vivienda")


def _sembrar_sin_columna(esc: Escenario) -> list[str]:
    padre = esc.categoria("GASTO")
    ids = [padre, esc.categoria("GASTO", parent=padre), esc.categoria("INGRESO"), esc.categoria("AMBOS")]
    esc.db.execute("SET CONSTRAINTS ALL IMMEDIATE")  # D-173: sin eventos diferidos antes del ALTER
    return ids


def _aplicar_0353(db: psycopg.Connection) -> None:
    db.execute("RESET ROLE")
    db.execute(cuerpo_0353())


def _huella_filas(db: psycopg.Connection, excluir: bool) -> str:
    expr = "(pg_catalog.to_jsonb(c) - 'asociada_vivienda')" if excluir else "pg_catalog.to_jsonb(c)"
    return _uno(db, f"SELECT count(*)::text || ':' || coalesce(md5(string_agg({expr}::text, E'\\n' "
                    "ORDER BY c.id)), '-') FROM gapto.categorias_financieras c")


def test_0353_aplicada_sobre_filas_preexistentes_las_deja_intactas_y_en_false(esc: Escenario) -> None:
    db = esc.db
    _retirar_columna(db)
    ids = _sembrar_sin_columna(esc)
    db.execute("ALTER TABLE gapto.categorias_financieras NO FORCE ROW LEVEL SECURITY")
    antes = _huella_filas(db, excluir=False)
    db.execute("ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY")
    _aplicar_0353(db)
    db.execute("SET ROLE gapto_owner")
    db.execute("ALTER TABLE gapto.categorias_financieras NO FORCE ROW LEVEL SECURITY")
    assert _huella_filas(db, excluir=True) == antes
    assert _uno(db, "SELECT count(*) FROM gapto.categorias_financieras WHERE asociada_vivienda") == 0
    db.execute("ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY")
    assert all(esc.marca(i) is False for i in ids)
    assert _uno(db, "SELECT relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid = 'gapto.categorias_financieras'::regclass") is True


def test_0353_reaplicacion_rechazada_por_el_precheck(db: psycopg.Connection) -> None:
    db.execute("RESET ROLE")
    with pytest.raises(psycopg.errors.RaiseException, match="0353 ya esta aplicada"):
        db.execute(cuerpo_0353())


def test_0353_precheck_exige_la_marca_de_0352(db: psycopg.Connection) -> None:
    """M-0353-04: sin la marca de 0352 (renombrada: el recuento de columnas no cambia) el precheck aborta."""
    _retirar_columna(db)
    db.execute("ALTER TABLE gapto.propiedades RENAME COLUMN coste_adquisicion_declarado_completo TO x_0353")
    db.execute("RESET ROLE")
    with pytest.raises(psycopg.errors.RaiseException, match="falta propiedades.coste_adquisicion_declarado_completo"):
        db.execute(cuerpo_0353())
