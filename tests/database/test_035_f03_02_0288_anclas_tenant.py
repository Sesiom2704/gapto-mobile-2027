# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_035_f03_02_0288_anclas_tenant.py
# Ruta: tests/database/test_035_f03_02_0288_anclas_tenant.py
# Descripción: FASE 03 / F03-02 / migration 0288. Fija el endurecimiento
#              declarativo de tenant de `hecho_entidades` y de
#              `inversion_asignaciones_efecto`: la coherencia de owner deja de
#              depender de RLS y pasa a imponerla PostgreSQL mediante FK
#              compuestas contra los anchors. Todos los casos cross-tenant se
#              comprueban con FORCE RLS levantado dentro de la transacción,
#              que es como se simula un rol BYPASSRLS (D-137).
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER_A = "c0288000-0000-4000-8000-000000000001"
OWNER_B = "c0288000-0000-4000-8000-000000000002"

COMPUESTAS = {
    "fk_hecho_entidades__owner_hecho":
        "FOREIGN KEY (owner_user_id, hecho_id) REFERENCES "
        "gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT",
    "fk_hecho_entidades__owner_entidad":
        "FOREIGN KEY (owner_user_id, entidad_id) REFERENCES "
        "gapto.entidades(owner_user_id, id) ON DELETE RESTRICT",
    "fk_hecho_entidades__hecho_efecto":
        "FOREIGN KEY (hecho_id, efecto_id) REFERENCES "
        "gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT",
    "fk_inversion_asignaciones_efecto__owner_hecho":
        "FOREIGN KEY (owner_user_id, hecho_id) REFERENCES "
        "gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT",
    "fk_inversion_asignaciones_efecto__hecho_efecto":
        "FOREIGN KEY (hecho_id, efecto_inversion_id) REFERENCES "
        "gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT",
    "fk_inversion_asignaciones_efecto__owner_inversion":
        "FOREIGN KEY (owner_user_id, inversion_entidad_id) REFERENCES "
        "gapto.entidades(owner_user_id, id) ON DELETE RESTRICT",
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


def _tenant(db: psycopg.Connection, owner: str) -> None:
    db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))


class Escenario:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        _tenant(db, OWNER_A)
        self.usuario(OWNER_A)
        self.hecho, self.efecto = self.hecho_inversion(OWNER_A)
        self.inversion = self.inversion_de(OWNER_A)

    def usuario(self, owner: str) -> None:
        self.db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0288') "
            "ON CONFLICT DO NOTHING", (owner, f"{uuid.uuid4()}@example.invalid"))

    def hecho_inversion(self, owner: str) -> tuple[str, str]:
        hid, eid = str(uuid.uuid4()), str(uuid.uuid4())
        tipo = _uno(self.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        self.db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
            "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, 'aportacion', '100.0000', 'EUR', 'NO_APLICA', true)",
            (hid, owner, tipo))
        self.db.execute(
            "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
            "estado_atribucion) VALUES (%s, %s, 'INVERSION', '100.0000', 'PARCIAL')", (eid, hid))
        return hid, eid

    def inversion_de(self, owner: str) -> str:
        ent = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
            "VALUES (%s, %s, 'INVERSION', %s)", (ent, owner, f"Fondo {ent[:8]}"))
        self.db.execute(
            "INSERT INTO gapto.inversiones (entidad_id, rol_estructura, tipo_producto, moneda, "
            "estado) VALUES (%s, 'POSICION', 'FONDO', 'EUR', 'ACTIVA')", (ent,))
        return ent

    def otro_owner(self) -> None:
        _tenant(self.db, OWNER_B)
        self.usuario(OWNER_B)
        self.hecho_b, self.efecto_b = self.hecho_inversion(OWNER_B)
        self.inversion_b = self.inversion_de(OWNER_B)
        _tenant(self.db, OWNER_A)

    def sin_force(self) -> None:
        """Simula un rol BYPASSRLS dentro de la transacción del test."""
        self.db.execute("ALTER TABLE gapto.hecho_entidades NO FORCE ROW LEVEL SECURITY")
        self.db.execute("ALTER TABLE gapto.inversion_asignaciones_efecto NO FORCE ROW LEVEL SECURITY")

    def relacion(self, entidad: str, owner: str = OWNER_A, hecho: str | None = None,
                 efecto: str | None = "usar", tipo: str = "AFECTA_A") -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_entidades (id, owner_user_id, hecho_id, efecto_id, "
            "entidad_id, tipo_relacion) VALUES (%s, %s, %s, %s, %s, %s)",
            (rid, owner, hecho or self.hecho,
             self.efecto if efecto == "usar" else efecto, entidad, tipo))
        return rid

    def asignacion(self, inversion: str, owner: str = OWNER_A, hecho: str | None = None,
                   efecto: str | None = None, importe: str = "50.0000") -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.inversion_asignaciones_efecto (id, owner_user_id, hecho_id, "
            "efecto_inversion_id, inversion_entidad_id, importe_asignado) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (rid, owner, hecho or self.hecho, efecto or self.efecto, inversion, importe))
        return rid


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

@pytest.mark.parametrize("tabla,columnas", [
    # hecho_entidades ya tenia hecho_id desde el baseline; 0288 solo anade owner.
    ("hecho_entidades", {"owner_user_id", "hecho_id"}),
    ("inversion_asignaciones_efecto", {"owner_user_id", "hecho_id"}),
])
def test_0288_localizadores_not_null(db: psycopg.Connection, tabla: str, columnas: set) -> None:
    obtenidas = {
        r[0] for r in db.execute("""
            SELECT a.attname FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = ('gapto.' || %s)::pg_catalog.regclass
               AND a.attname IN ('owner_user_id', 'hecho_id')
               AND a.attnotnull AND NOT a.attisdropped""", (tabla,)).fetchall()
    }
    assert obtenidas == columnas


@pytest.mark.parametrize("nombre,definicion", sorted(COMPUESTAS.items()))
def test_0288_fk_compuesta(db: psycopg.Connection, nombre: str, definicion: str) -> None:
    assert _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(k.oid) FROM pg_catalog.pg_constraint k
         WHERE k.conname = %s AND k.connamespace = 'gapto'::pg_catalog.regnamespace""",
        (nombre,)) == definicion


def test_0288_force_rls_restaurado(db: psycopg.Connection) -> None:
    """La validación de las FK exigió levantar FORCE; debe quedar restaurado."""
    assert db.execute("""
        SELECT count(*) FROM pg_catalog.pg_class c
         WHERE c.relname IN ('hecho_entidades', 'inversion_asignaciones_efecto')
           AND c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND c.relrowsecurity AND c.relforcerowsecurity""").fetchone()[0] == 2


def test_0288_sin_triggers_nuevos(db: psycopg.Connection) -> None:
    """El endurecimiento es declarativo: el único trigger de las dos tablas
    sigue siendo el de suma de asignaciones, que ya existía."""
    nombres = {
        r[0] for r in db.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid IN ('gapto.hecho_entidades'::pg_catalog.regclass,
                                 'gapto.inversion_asignaciones_efecto'::pg_catalog.regclass)
               AND NOT t.tgisinternal""").fetchall()
    }
    assert nombres == {"trg_inversion_asignaciones_efecto__suma"}


def test_0288_fk_simples_conservadas(db: psycopg.Connection) -> None:
    """No se retira ninguna FK de la cadena congelada: la simple al hecho es la
    única garantía cuando efecto_id es NULL, y la de inversiones prueba el
    subtipo, cosa que el anchor de entidades no hace."""
    nombres = {
        r[0] for r in db.execute("""
            SELECT k.conname FROM pg_catalog.pg_constraint k
              JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
             WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f'
               AND c.relname IN ('hecho_entidades', 'inversion_asignaciones_efecto')""").fetchall()
    }
    assert {"fk_hecho_entidades__hecho", "fk_hecho_entidades__entidad",
            "fk_inversion_asignaciones_efecto__efecto",
            "fk_inversion_asignaciones_efecto__inversion"} <= nombres


def test_0288_contrato_fisico(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f'""") == 174


# ------------------------------------------------------------
# Casos legítimos
# ------------------------------------------------------------

def test_0288_relacion_de_efecto_legitima(esc: Escenario) -> None:
    esc.relacion(esc.inversion)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_entidades WHERE efecto_id = %s",
                (esc.efecto,)) == 1


def test_0288_relacion_a_nivel_de_hecho_sigue_siendo_valida(esc: Escenario) -> None:
    """efecto_id NULL conserva su semántica de relación de hecho: la FK
    compuesta al efecto no se aplica (MATCH SIMPLE) y la simple al hecho sí."""
    esc.relacion(esc.inversion, efecto=None)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_entidades "
                        "WHERE hecho_id = %s AND efecto_id IS NULL", (esc.hecho,)) == 1


def test_0288_asignacion_legitima(esc: Escenario) -> None:
    esc.asignacion(esc.inversion)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.inversion_asignaciones_efecto "
                        "WHERE efecto_inversion_id = %s", (esc.efecto,)) == 1


# ------------------------------------------------------------
# Cross-tenant: lo impide la FK, no la policy
# ------------------------------------------------------------

def test_0288_entidad_de_otro_owner_se_rechaza(esc: Escenario) -> None:
    esc.otro_owner()
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.relacion(esc.inversion_b)


def test_0288_relacion_con_owner_declarado_ajeno_se_rechaza(esc: Escenario) -> None:
    esc.otro_owner()
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.relacion(esc.inversion, owner=OWNER_B)


def test_0288_inversion_de_otro_owner_se_rechaza(esc: Escenario) -> None:
    esc.otro_owner()
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.asignacion(esc.inversion_b)


def test_0288_asignacion_con_owner_declarado_ajeno_se_rechaza(esc: Escenario) -> None:
    esc.otro_owner()
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.asignacion(esc.inversion, owner=OWNER_B)


def test_0288_asignacion_a_efecto_de_otro_hecho_se_rechaza(esc: Escenario) -> None:
    """La FK compuesta (hecho_id, efecto_inversion_id) ata el efecto a su hecho."""
    otro_hecho, _ = esc.hecho_inversion(OWNER_A)
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.asignacion(esc.inversion, hecho=otro_hecho)


def test_0288_relacion_con_efecto_de_otro_hecho_se_rechaza(esc: Escenario) -> None:
    otro_hecho, otro_efecto = esc.hecho_inversion(OWNER_A)
    esc.sin_force()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.relacion(esc.inversion, efecto=otro_efecto)
    assert otro_hecho is not None


def test_0288_rls_sigue_aislando(esc: Escenario) -> None:
    esc.relacion(esc.inversion)
    esc.asignacion(esc.inversion)
    _tenant(esc.db, OWNER_B)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_entidades") == 0
    assert _uno(esc.db, "SELECT count(*) FROM gapto.inversion_asignaciones_efecto") == 0
    _tenant(esc.db, OWNER_A)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_entidades") == 1
