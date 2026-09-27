# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_043_f03_05_0340_categoria_icon_key.py
# Ruta: tests/database/test_043_f03_05_0340_categoria_icon_key.py
# Descripción: Verifica F03-05 / migration 0340 (D-197, SET-CAT-ICON-01):
#              categorias_financieras.icon_key varchar(80) NULL, sin DEFAULT,
#              sin UNIQUE, sin FK y con CHECK de no vacío y sin espacios
#              exteriores (btrim).
#
#              DISCRIMINACIÓN. Contra 0330 fallan 22 de los 24 casos: la columna
#              no existe. Los otros dos, test_0340_triggers_de_la_tabla_intactos
#              y test_0340_force_rls_intacto, son GUARDAS DE REGRESIÓN: afirman
#              propiedades que 0330 ya cumple y que 0340 no debe romper, y
#              discriminan M10 y cualquier trigger nuevo, no la ausencia de
#              0340. El gate de mutación ejecutable es
#              scripts/mutantes/f03_05_0340.py. Catálogo y discriminantes:
#                M1 sin CHECK ................. test_0340_rechaza (todos)
#                M2 CHECK solo <> '' .......... test_0340_rechaza[...espacio...]
#                M3 ltrim en vez de btrim ..... test_0340_rechaza[espacio_final]
#                M4 rtrim en vez de btrim ..... test_0340_rechaza[espacio_inicial]
#                M5 DEFAULT 'x' ............... test_0340_columna_con_tipo_exacto,
#                                               test_0340_alta_sin_icono_queda_null
#                M6 NOT NULL .................. test_0340_columna_con_tipo_exacto,
#                                               test_0340_alta_sin_icono_queda_null
#                M7 CHECK NOT VALID ........... test_0340_check_validado_e_inmediato
#                M8 UNIQUE (owner, icon_key) .. test_0340_sin_unique_fk_ni_indice,
#                                               test_0340_icono_repetido_admitido
#                M9 varchar(100) .............. test_0340_columna_con_tipo_exacto,
#                                               test_0340_longitud_81_rechazada
#                M10 FORCE RLS no restaurado .. test_0340_force_rls_intacto
#
#              LO QUE NO SE PRUEBA AQUÍ Y NO ES UN OLVIDO. Que la clave
#              pertenezca a la biblioteca de iconos F09 y que editarla
#              incremente row_version y updated_at son garantías del
#              write-path, no del catálogo. Que aplicar 0340 no cambie ninguna
#              fila preexistente lo comprueba la propia migration (bloque
#              $filas_0340$) en cada entorno donde se aplica: un test que corre
#              después de la migration no puede observar el estado anterior.
#              El CHECK aprobado recorta solo U+0020: tabuladores o U+00A0
#              exteriores no se prueban en ningún sentido, para no congelar
#              como contrato ni la aceptación ni el rechazo.
# Versión: 0.1.1  -- P1 de 0340 en réplica local: la cabecera afirmaba que
#                   contra 0330 fallaba todo el módulo y dos casos son guardas
#                   de regresión que 0330 ya cumple. Corrección SOLO de
#                   comentario; ningún caso ni aserción cambia.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER = "0340a000-0000-4000-8000-000000000001"
OTRO_OWNER = "0340a000-0000-4000-8000-0000000000ff"
CHECK_0340 = "ck_categorias_financieras__icon_key_no_vacia_recortada"
TRIGGERS_TABLA = {
    "trg_categorias_financieras__aciclica",
    "trg_categorias_financieras__bolsa_reparenting",
    "trg_categorias_financieras__deriva_d122",
    "trg_categorias_financieras__owner_inmutable",
}


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


class Escenario:
    """Un owner con una categoría raíz sin icono."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0340') "
            "ON CONFLICT DO NOTHING", (OWNER, f"{uuid.uuid4()}@example.invalid"))
        self.raiz = self.categoria()

    def categoria(self, icon_key=..., parent: str | None = None) -> str:
        cid = str(uuid.uuid4())
        if icon_key is ...:
            self.db.execute(
                "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, "
                "ambito, presupuestable_default) VALUES (%s, %s, %s, %s, 'GASTO', true)",
                (cid, OWNER, parent, f"Cat {cid[:8]}"))
        else:
            self.db.execute(
                "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, "
                "ambito, presupuestable_default, icon_key) VALUES (%s, %s, %s, %s, 'GASTO', true, %s)",
                (cid, OWNER, parent, f"Cat {cid[:8]}", icon_key))
        return cid

    def icono(self, cid: str) -> str | None:
        return _uno(self.db, "SELECT icon_key FROM gapto.categorias_financieras WHERE id = %s", (cid,))

    def poner_icono(self, cid: str, icon_key) -> None:
        self.db.execute(
            "UPDATE gapto.categorias_financieras SET icon_key = %s WHERE id = %s", (icon_key, cid))


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


def _rechaza(esc: Escenario, excepcion, accion) -> None:
    esc.db.execute("SAVEPOINT s")
    with pytest.raises(excepcion):
        accion()
    esc.db.execute("ROLLBACK TO SAVEPOINT s")


def _como_runtime(esc: Escenario) -> None:
    esc.db.execute("SAVEPOINT r")
    try:
        esc.db.execute("RESET ROLE")
        esc.db.execute("SET ROLE gapto_runtime")
    except psycopg.errors.InsufficientPrivilege:
        esc.db.execute("ROLLBACK TO SAVEPOINT r")
        pytest.skip("El rol del arnés no puede asumir gapto_runtime: cobertura no ejercitada.")


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

def test_0340_columna_con_tipo_exacto(db: psycopg.Connection) -> None:
    with db.cursor() as cur:
        cur.execute("""
            SELECT pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull, a.atthasdef
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = 'gapto.categorias_financieras'::regclass
               AND a.attname = 'icon_key' AND NOT a.attisdropped
        """)
        fila = cur.fetchone()
    assert fila is not None, "falta categorias_financieras.icon_key"
    assert fila == ("character varying(80)", False, False), \
        "icon_key debe ser varchar(80), nullable y sin DEFAULT (D-197)"


def test_0340_check_validado_e_inmediato(db: psycopg.Connection) -> None:
    """Un CHECK NOT VALID sería una invariante decorativa."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint
         WHERE conrelid = 'gapto.categorias_financieras'::regclass
           AND conname = %s AND contype = 'c' AND convalidated AND NOT condeferrable
    """, (CHECK_0340,)) == 1


def test_0340_sin_unique_fk_ni_indice(db: psycopg.Connection) -> None:
    """D-197: sin UNIQUE ni FK hacia el Design System. La única constraint que
    toca icon_key es el CHECK, y ningún índice la incluye."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT k.conname, k.contype FROM pg_catalog.pg_constraint k
              JOIN pg_catalog.pg_attribute a
                ON a.attrelid = k.conrelid AND a.attname = 'icon_key'
             WHERE k.conrelid = 'gapto.categorias_financieras'::regclass
               AND a.attnum = ANY (k.conkey)
        """)
        assert cur.fetchall() == [(CHECK_0340, "c")]
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_index i
          JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attname = 'icon_key'
         WHERE i.indrelid = 'gapto.categorias_financieras'::regclass
           AND a.attnum = ANY (i.indkey)
    """) == 0


def test_0340_acl_heredado_de_tabla(db: psycopg.Connection) -> None:
    """Sin GRANT nuevo: la columna hereda el ACL de tabla de 0130 y no tiene
    ACL propia (h7 de D-111 no cambia)."""
    assert _uno(db, """
        SELECT attacl IS NULL FROM pg_catalog.pg_attribute
         WHERE attrelid = 'gapto.categorias_financieras'::regclass AND attname = 'icon_key'
    """) is True
    for rol, priv in (("gapto_runtime", "SELECT"), ("gapto_runtime", "INSERT"),
                      ("gapto_runtime", "UPDATE"), ("gapto_backup", "SELECT")):
        assert _uno(db, "SELECT has_column_privilege(%s, 'gapto.categorias_financieras', "
                        "'icon_key', %s)", (rol, priv)) is True, f"{rol} {priv}"
    for priv in ("INSERT", "UPDATE"):
        assert _uno(db, "SELECT has_column_privilege('gapto_backup', "
                        "'gapto.categorias_financieras', 'icon_key', %s)", (priv,)) is False


def test_0340_triggers_de_la_tabla_intactos(db: psycopg.Connection) -> None:
    """0340 no crea triggers y ninguno de los existentes escucha icon_key."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT t.tgname,
                   EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                            WHERE a.attrelid = t.tgrelid AND a.attname = 'icon_key'
                              AND a.attnum = ANY (t.tgattr))
              FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = 'gapto.categorias_financieras'::regclass AND NOT t.tgisinternal
        """)
        filas = cur.fetchall()
    assert {f[0] for f in filas} == TRIGGERS_TABLA
    assert not any(f[1] for f in filas)


def test_0340_force_rls_intacto(db: psycopg.Connection) -> None:
    """D-104: el patrón levantar/validar/restaurar no puede dejar la tabla sin FORCE."""
    assert _uno(db, """
        SELECT relrowsecurity AND relforcerowsecurity FROM pg_catalog.pg_class
         WHERE oid = 'gapto.categorias_financieras'::regclass
    """) is True


# ------------------------------------------------------------
# Comportamiento
# ------------------------------------------------------------

def test_0340_alta_sin_icono_queda_null(esc: Escenario) -> None:
    """NULL = sin icono explícito. Sin DEFAULT ni valor inventado."""
    assert esc.icono(esc.raiz) is None


def test_0340_hijo_no_hereda_icono(esc: Escenario) -> None:
    """Sin herencia padre -> hijo."""
    padre = esc.categoria("home")
    hijo = esc.categoria(parent=padre)
    assert esc.icono(hijo) is None


@pytest.mark.parametrize("clave", [
    "shopping-cart", "cat.food", "a", "icono con espacios interiores", "x" * 80,
])
def test_0340_admite(esc: Escenario, clave: str) -> None:
    cid = esc.categoria(clave)
    assert esc.icono(cid) == clave


@pytest.mark.parametrize("clave", ["", " ", "   ", " home", "home ", "  home  "],
                         ids=["vacia", "un_espacio", "solo_espacios", "espacio_inicial",
                              "espacio_final", "ambos_extremos"])
def test_0340_rechaza(esc: Escenario, clave: str) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation, lambda: esc.categoria(clave))
    _rechaza(esc, psycopg.errors.CheckViolation, lambda: esc.poner_icono(esc.raiz, clave))


def test_0340_longitud_81_rechazada(esc: Escenario) -> None:
    _rechaza(esc, psycopg.errors.StringDataRightTruncation, lambda: esc.categoria("x" * 81))


def test_0340_icono_repetido_admitido(esc: Escenario) -> None:
    """Sin UNIQUE: dos categorías del mismo owner pueden compartir icono."""
    esc.categoria("home")
    esc.categoria("home")


def test_0340_quitar_icono_vuelve_a_null(esc: Escenario) -> None:
    esc.poner_icono(esc.raiz, "home")
    esc.poner_icono(esc.raiz, None)
    assert esc.icono(esc.raiz) is None


# ------------------------------------------------------------
# Camino real: gapto_runtime bajo FORCE RLS
# ------------------------------------------------------------

def test_0340_runtime_edita_icono_propio(esc: Escenario) -> None:
    _como_runtime(esc)
    esc.poner_icono(esc.raiz, "home")
    assert esc.icono(esc.raiz) == "home"


def test_0340_runtime_no_ve_icono_ajeno(esc: Escenario) -> None:
    esc.poner_icono(esc.raiz, "home")
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
    _como_runtime(esc)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.categorias_financieras WHERE id = %s",
                (esc.raiz,)) == 0
