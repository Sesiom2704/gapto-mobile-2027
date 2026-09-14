# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_036_f03_02_0290_inversion_principal.py
# Ruta: tests/database/test_036_f03_02_0290_inversion_principal.py
# Descripción: FASE 03 / F03-02 / migration 0290. Fija D-080: inversión
#              principal inequívoca por efecto y destinos dentro de su rama.
#              Cubre el contrato físico, los seis eventos de señal, el
#              predicado completo y el protocolo de locks de P4, que retira el
#              row lock de los dos validadores y deja el advisory
#              (INVERSIONES, owner) como único lock root.
#              Las invariantes son CONSTRAINT TRIGGER DEFERRABLE INITIALLY
#              DEFERRED, así que el rechazo se provoca con
#              `SET CONSTRAINTS ALL IMMEDIATE` dentro de un savepoint y el
#              montaje multi-paso se valida con `_validar_montaje`.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER_A = "c0290000-0000-4000-8000-000000000001"
OWNER_B = "c0290000-0000-4000-8000-000000000002"

FUNCION = "fn_check_inversion_principal"
SUMA = "fn_check_inversion_asignacion_suma"

# Huella CURRENT de 0290. Conforme a Working Method 12C.5, el test nuevo de una
# migration fija solo la huella de esa migration; cualquier otra es drift.
PROSRC_CURRENT = {
    FUNCION: "1f2cbd5647ae5a013121bdadc41b6c8a",
    SUMA: "3ffd4236dea6f3ad75ad5ffacc5dd247",
}

# tgtype: 4 = INSERT, 8 = DELETE, 16 = UPDATE, 2 = BEFORE.
TRIGGERS = {
    "trg_inversion_asignaciones_efecto__d080": ("inversion_asignaciones_efecto", 4 + 16),
    "trg_hecho_entidades__d080": ("hecho_entidades", 4 + 8 + 16),
    "trg_hecho_efectos__d080_tipo_efecto": ("hecho_efectos", 16),
    "trg_inversiones__d080_reparenting": ("inversiones", 16),
    "trg_inversiones__d080_alta_subtipo": ("inversiones", 4),
    "trg_entidades__d080_subtipo": ("entidades", 16),
}

CLAUSULAS_DE_BLOQUEO = ("FOR UPDATE", "FOR NO KEY UPDATE", "FOR SHARE", "FOR KEY SHARE")


# ------------------------------------------------------------
# Infraestructura
# ------------------------------------------------------------

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


def _inmediato(db: psycopg.Connection) -> None:
    db.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _validar_montaje(db: psycopg.Connection) -> None:
    """Confirma lógicamente el estado actual y vuelve al modo diferido."""
    _inmediato(db)
    db.execute("SET CONSTRAINTS ALL DEFERRED")


def _acepta(db: psycopg.Connection) -> None:
    _validar_montaje(db)


def _rechaza(db: psycopg.Connection, patron: str) -> None:
    db.execute("SAVEPOINT d080")
    try:
        with pytest.raises(psycopg.errors.RaiseException, match=patron):
            _inmediato(db)
    finally:
        db.execute("ROLLBACK TO SAVEPOINT d080")
        db.execute("SET CONSTRAINTS ALL DEFERRED")


class Escenario:
    """Owner A con un efecto INVERSION y el árbol PLAN -> HIJA -> NIETA, más
    AJENA colgando de nada."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        _tenant(db, OWNER_A)
        self.usuario(OWNER_A)
        self.hecho, self.efecto = self.hecho_con_efecto(OWNER_A, "INVERSION")
        self.plan = self.inversion(OWNER_A, "CONTENEDOR")
        self.hija = self.inversion(OWNER_A, "POSICION", padre=self.plan)
        self.nieta = self.inversion(OWNER_A, "POSICION", padre=self.hija)
        self.ajena = self.inversion(OWNER_A, "POSICION")
        _validar_montaje(db)

    # -- montaje ---------------------------------------------------------
    def usuario(self, owner: str) -> None:
        self.db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0290') "
            "ON CONFLICT DO NOTHING", (owner, f"{uuid.uuid4()}@example.invalid"))

    def hecho_con_efecto(self, owner: str, tipo_efecto: str,
                         importe: str = "1000.0000") -> tuple[str, str]:
        hid, eid = str(uuid.uuid4()), str(uuid.uuid4())
        tipo = _uno(self.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'APORTACION_INVERSION'")
        self.db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
            "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, 'aportacion', %s, 'EUR', 'NO_APLICA', false)",
            (hid, owner, tipo, importe))
        self.db.execute(
            "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
            "estado_atribucion) VALUES (%s, %s, %s, %s, 'NO_DISPONIBLE')",
            (eid, hid, tipo_efecto, importe))
        return hid, eid

    def entidad(self, owner: str, tipo: str = "INVERSION") -> str:
        ent = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
            "VALUES (%s, %s, %s, %s)", (ent, owner, tipo, f"E {ent[:8]}"))
        return ent

    def subtipo_inversion(self, ent: str, rol: str = "POSICION",
                          padre: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO gapto.inversiones (entidad_id, inversion_padre_entidad_id, "
            "rol_estructura, tipo_producto, moneda, estado) "
            "VALUES (%s, %s, %s, 'FONDO', 'EUR', 'ACTIVA')", (ent, padre, rol))

    def inversion(self, owner: str, rol: str = "POSICION", padre: str | None = None) -> str:
        ent = self.entidad(owner)
        self.subtipo_inversion(ent, rol, padre)
        return ent

    def principal(self, entidad: str, owner: str = OWNER_A, efecto: str | None = "usar",
                  tipo: str = "AFECTA_A", marca: bool = True, hecho: str | None = None) -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_entidades (id, owner_user_id, hecho_id, efecto_id, "
            "entidad_id, tipo_relacion, principal) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (rid, owner, hecho or self.hecho,
             self.efecto if efecto == "usar" else efecto, entidad, tipo, marca))
        return rid

    def asignacion(self, inversion: str, owner: str = OWNER_A, efecto: str | None = None,
                   hecho: str | None = None, importe: str = "100.0000") -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.inversion_asignaciones_efecto (id, owner_user_id, hecho_id, "
            "efecto_inversion_id, inversion_entidad_id, importe_asignado) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (rid, owner, hecho or self.hecho, efecto or self.efecto, inversion, importe))
        return rid

    def reparentar(self, entidad: str, padre: str | None) -> None:
        self.db.execute(
            "UPDATE gapto.inversiones SET inversion_padre_entidad_id = %s WHERE entidad_id = %s",
            (padre, entidad))

    def tipo_efecto(self, valor: str, efecto: str | None = None) -> None:
        self.db.execute("UPDATE gapto.hecho_efectos SET tipo_efecto = %s WHERE id = %s",
                        (valor, efecto or self.efecto))

    def sin_force(self) -> None:
        """Simula un rol BYPASSRLS dentro de la transacción del test (D-137)."""
        for t in ("hecho_entidades", "inversion_asignaciones_efecto", "inversiones", "entidades"):
            self.db.execute(f"ALTER TABLE gapto.{t} NO FORCE ROW LEVEL SECURITY")


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


# ------------------------------------------------------------
# Contrato físico
# ------------------------------------------------------------

def test_0290_funcion_creada_bajo_gapto_owner(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT pg_catalog.pg_get_userbyid(p.proowner) FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
           AND p.proname = %s""", (FUNCION,)) == "gapto_owner"


@pytest.mark.parametrize("nombre,tabla,eventos",
                         [(n, t, e) for n, (t, e) in sorted(TRIGGERS.items())])
def test_0290_trigger_contrato(db: psycopg.Connection, nombre: str, tabla: str,
                               eventos: int) -> None:
    fila = db.execute("""
        SELECT c.relname, t.tgtype & (4 + 8 + 16), t.tgconstraint <> 0,
               t.tgdeferrable, t.tginitdeferred, t.tgtype & 2, t.tgenabled,
               t.tgfoid::pg_catalog.regprocedure::text
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND NOT t.tgisinternal AND t.tgname = %s""", (nombre,)).fetchone()
    assert fila is not None, f"{nombre} no existe"
    assert fila[0] == tabla
    assert fila[1] == eventos, f"{nombre}: máscara de eventos {fila[1]}, esperada {eventos}"
    assert fila[2], f"{nombre} no es CONSTRAINT TRIGGER"
    assert fila[3] and fila[4], f"{nombre} no es DEFERRABLE INITIALLY DEFERRED"
    assert fila[5] == 0, f"{nombre} no es AFTER"
    assert fila[6] == "O", f"{nombre} no está habilitado"
    assert fila[7] == f"gapto.{FUNCION}()"


def test_0290_conjunto_exacto_de_triggers(db: psycopg.Connection) -> None:
    obtenidos = {r[0] for r in db.execute("""
        SELECT t.tgname FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND NOT t.tgisinternal AND t.tgname LIKE '%%d080%%'""").fetchall()}
    assert obtenidos == set(TRIGGERS)


def test_0290_inversiones_delete_sin_trigger(db: psycopg.Connection) -> None:
    """El DELETE de inversiones es evento equivalente: las FK RESTRICT lo cubren."""
    assert _uno(db, """
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t
         WHERE t.tgrelid = 'gapto.inversiones'::pg_catalog.regclass
           AND NOT t.tgisinternal AND t.tgname LIKE '%%d080%%'
           AND (t.tgtype & 8) <> 0""") == 0


@pytest.mark.parametrize("funcion", sorted(PROSRC_CURRENT))
def test_0290_validador_sin_row_lock(db: psycopg.Connection, funcion: str) -> None:
    """P4: el advisory (INVERSIONES, owner) es el único lock root explícito."""
    cuerpo = _uno(db, """
        SELECT p.prosrc FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = %s""",
        (funcion,))
    presentes = [c for c in CLAUSULAS_DE_BLOQUEO if c in cuerpo]
    assert presentes == [], f"{funcion} conserva {presentes}; P4 exige cero row locks"


@pytest.mark.parametrize("funcion", sorted(PROSRC_CURRENT))
def test_0290_validador_toma_advisory(db: psycopg.Connection, funcion: str) -> None:
    cuerpo = _uno(db, """
        SELECT p.prosrc FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = %s""",
        (funcion,))
    assert "pg_advisory_xact_lock(hashtext('gapto:INVERSIONES')" in cuerpo


@pytest.mark.parametrize("funcion,md5", sorted(PROSRC_CURRENT.items()))
def test_0290_huella_prosrc(db: psycopg.Connection, funcion: str, md5: str) -> None:
    assert _uno(db, """
        SELECT pg_catalog.md5(p.prosrc) FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = %s""",
        (funcion,)) == md5


def test_0290_recuentos_como_suelo(db: psycopg.Connection) -> None:
    """Suelo, no igualdad: una migration posterior legítima no debe romper esto."""
    funciones = _uno(db, "SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc p "
                         "WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace")
    triggers = _uno(db, """
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal""")
    constraint_triggers = _uno(db, """
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND NOT t.tgisinternal AND t.tgconstraint <> 0""")
    assert funciones >= 26
    assert triggers >= 54
    assert constraint_triggers >= 37


def test_0290_no_toca_superficies_ajenas(db: psycopg.Connection) -> None:
    """0290 no crea tablas, columnas, FK, UNIQUE, EXCLUDE, índices ni policies."""
    assert _uno(db, "SELECT pg_catalog.count(*) FROM pg_catalog.pg_class c "
                    "WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace "
                    "AND c.relkind = 'r'") == 80
    assert _uno(db, """
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f'""") == 174
    assert _uno(db, "SELECT pg_catalog.count(*) FROM pg_catalog.pg_indexes i "
                    "WHERE i.schemaname = 'gapto'") == 284
    assert _uno(db, "SELECT pg_catalog.count(*) FROM pg_catalog.pg_policies p "
                    "WHERE p.schemaname = 'gapto'") == 82


# ------------------------------------------------------------
# Predicado: unicidad de la principal
# ------------------------------------------------------------

def test_0290_una_principal_es_valida(esc: Escenario) -> None:
    esc.principal(esc.plan)
    _acepta(esc.db)


def test_0290_dos_principales_rechazadas(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.principal(esc.ajena)
    _rechaza(esc.db, "inversiones marcadas principal")


def test_0290_principal_false_no_cuenta(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.principal(esc.ajena, marca=False)
    _acepta(esc.db)


def test_0290_entidad_sin_subtipo_inversion_no_cuenta(esc: Escenario) -> None:
    """La marca es genérica de hecho_entidades: solo cuenta si hay subtipo."""
    otra = esc.entidad(OWNER_A, "CONTEXTO")
    esc.db.execute("INSERT INTO gapto.contextos (entidad_id, tipo_contexto) "
                   "VALUES (%s, 'VIAJE')", (otra,))
    esc.principal(esc.plan)
    esc.principal(otra)
    _acepta(esc.db)


# ------------------------------------------------------------
# P2: tipo_relacion no participa en el predicado
# ------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["AFECTA_A", "GENERADO_POR", "REPERCUTIBLE_A", "RELACIONADO_CON"])
def test_0290_cualquier_tipo_relacion_satisface(esc: Escenario, tipo: str) -> None:
    esc.principal(esc.plan, tipo=tipo)
    esc.asignacion(esc.hija)
    _acepta(esc.db)


def test_0290_misma_entidad_dos_relaciones_principales_rechazada(esc: Escenario) -> None:
    """Consecuencia deliberada de P2: principal vive en la relación, no en la
    entidad; dos filas hacia la misma inversión son dos principales."""
    esc.principal(esc.plan, tipo="AFECTA_A")
    esc.principal(esc.plan, tipo="RELACIONADO_CON")
    _rechaza(esc.db, "inversiones marcadas principal")


# ------------------------------------------------------------
# Obligatoriedad: solo con asignaciones (D-017)
# ------------------------------------------------------------

def test_0290_efecto_sin_principal_y_sin_asignaciones_valido(esc: Escenario) -> None:
    _acepta(esc.db)


def test_0290_principal_sin_asignaciones_valida(esc: Escenario) -> None:
    esc.principal(esc.plan)
    _acepta(esc.db)


def test_0290_asignaciones_sin_principal_rechazadas(esc: Escenario) -> None:
    esc.asignacion(esc.plan)
    _rechaza(esc.db, "ninguna inversion principal")


def test_0290_principal_a_nivel_de_hecho_no_satisface(esc: Escenario) -> None:
    """Una relación con efecto_id NULL no cumple D-080: la regla es de efecto."""
    esc.principal(esc.plan, efecto=None)
    esc.asignacion(esc.plan)
    _rechaza(esc.db, "ninguna inversion principal")


# ------------------------------------------------------------
# Destinos dentro de la rama
# ------------------------------------------------------------

def test_0290_destino_es_la_propia_principal(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.plan)
    _acepta(esc.db)


def test_0290_destino_descendiente_directo(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.hija)
    _acepta(esc.db)


def test_0290_destino_descendiente_en_segundo_nivel(esc: Escenario) -> None:
    """El recorrido no es de profundidad 1."""
    esc.principal(esc.plan)
    esc.asignacion(esc.nieta)
    _acepta(esc.db)


def test_0290_destino_fuera_de_rama_rechazado(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.ajena)
    _rechaza(esc.db, "no es su principal")


def test_0290_ascendiente_no_es_descendiente(esc: Escenario) -> None:
    """Con la principal en HIJA, PLAN es su padre y por tanto está fuera."""
    esc.principal(esc.hija)
    esc.asignacion(esc.plan)
    _rechaza(esc.db, "no es su principal")


# ------------------------------------------------------------
# Alcance: D-080 solo aplica a tipo_efecto = INVERSION
# ------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["VALOR_ACTIVO", "GASTO", "INGRESO", "DEUDA", "DERECHO_COBRO"])
def test_0290_fuera_de_alcance_admite_varias_principales(esc: Escenario, tipo: str) -> None:
    hecho, efecto = esc.hecho_con_efecto(OWNER_A, tipo)
    esc.principal(esc.plan, efecto=efecto, hecho=hecho)
    esc.principal(esc.ajena, efecto=efecto, hecho=hecho)
    _acepta(esc.db)


# ------------------------------------------------------------
# P1: señal hecho_efectos UPDATE OF tipo_efecto
# ------------------------------------------------------------

def test_0290_p1_transicion_a_inversion_con_dos_principales(esc: Escenario) -> None:
    """El hueco que cerró P1: sobre 0288 esta secuencia confirmaba con 2."""
    esc.tipo_efecto("GASTO")
    esc.principal(esc.plan)
    esc.principal(esc.ajena)
    _validar_montaje(esc.db)
    esc.tipo_efecto("INVERSION")
    _rechaza(esc.db, "inversiones marcadas principal")


def test_0290_p1_transicion_a_inversion_con_una_principal(esc: Escenario) -> None:
    esc.tipo_efecto("GASTO")
    esc.principal(esc.plan)
    _validar_montaje(esc.db)
    esc.tipo_efecto("INVERSION")
    _acepta(esc.db)


def test_0290_p1_salir_de_inversion_desactiva_d080(esc: Escenario) -> None:
    """Sin asignaciones, dejar de ser INVERSION saca el efecto del alcance."""
    esc.principal(esc.plan)
    _validar_montaje(esc.db)
    esc.tipo_efecto("GASTO")
    esc.principal(esc.ajena)
    _acepta(esc.db)


# ------------------------------------------------------------
# Señales parent-side de subtipo
# ------------------------------------------------------------

def test_0290_transicion_de_subtipo_crea_la_segunda_principal(esc: Escenario) -> None:
    """Señal parent-side de subtipo. La relación principal hacia la entidad ya
    está confirmada cuando todavía es una PROPIEDAD y no cuenta para D-080; la
    transición posterior a INVERSION la convierte en la segunda principal.

    NOTA DE EQUIVALENCIA. Este caso ejercita la familia parent-side completa,
    no un trigger aislado. `trg_inversiones__d080_alta_subtipo` no es
    discriminable por separado: para que `inversiones INSERT` fuese la ÚNICA
    señal, la entidad tendría que estar confirmada con `tipo_entidad='INVERSION'`
    y sin fila en `inversiones`, estado que D-124 ya prohíbe en cualquier estado
    confirmado. Se conserva como defensa en profundidad y se documenta como
    evento equivalente, sin inventar una invariante para matarlo (12C.5)."""
    esc.principal(esc.plan)
    futura = esc.entidad(OWNER_A, "PROPIEDAD")
    esc.db.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) "
                   "VALUES (%s, 'VIVIENDA')", (futura,))
    esc.principal(futura)
    _validar_montaje(esc.db)          # aún es PROPIEDAD: una sola principal
    esc.db.execute("DELETE FROM gapto.propiedades WHERE entidad_id = %s", (futura,))
    esc.db.execute("UPDATE gapto.entidades SET tipo_entidad = 'INVERSION' WHERE id = %s",
                   (futura,))
    esc.subtipo_inversion(futura)
    _rechaza(esc.db, "inversiones marcadas principal")


def test_0290_update_tipo_entidad_no_produce_falso_positivo(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.hija)
    _validar_montaje(esc.db)
    esc.db.execute("UPDATE gapto.entidades SET tipo_entidad = 'INVERSION' WHERE id = %s",
                   (esc.plan,))
    _acepta(esc.db)


# ------------------------------------------------------------
# Reparenting
# ------------------------------------------------------------

def test_0290_reparenting_saca_el_destino_de_la_rama(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.hija)
    _validar_montaje(esc.db)
    esc.reparentar(esc.hija, None)
    _rechaza(esc.db, "no es su principal")


def test_0290_reparenting_mete_el_destino_en_la_rama(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.reparentar(esc.ajena, esc.plan)
    esc.asignacion(esc.ajena)
    _acepta(esc.db)


def test_0290_reparenting_intermedio_arrastra_el_subarbol(esc: Escenario) -> None:
    """Mover HIJA saca también a NIETA, que cuelga de ella."""
    esc.principal(esc.plan)
    esc.asignacion(esc.nieta)
    _validar_montaje(esc.db)
    esc.reparentar(esc.hija, None)
    _rechaza(esc.db, "no es su principal")


# ------------------------------------------------------------
# Cross-tenant y fail-closed
# ------------------------------------------------------------

def test_0290_destino_de_otro_owner_rechazado_por_fk(esc: Escenario) -> None:
    """0288 ya lo impone declarativamente, también frente a BYPASSRLS."""
    esc.principal(esc.plan)
    _validar_montaje(esc.db)
    esc.sin_force()
    _tenant(esc.db, OWNER_B)
    esc.usuario(OWNER_B)
    ajena_b = esc.inversion(OWNER_B)
    _tenant(esc.db, OWNER_A)
    esc.db.execute("SAVEPOINT x")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.asignacion(ajena_b)
    esc.db.execute("ROLLBACK TO SAVEPOINT x")


def test_0290_rama_acotada_al_owner(esc: Escenario) -> None:
    """A8: un nodo intermedio de otro owner no extiende la rama. El same-owner
    de inversion_padre_entidad_id lo impone una policy, no una FK, así que solo
    es alcanzable simulando BYPASSRLS."""
    esc.sin_force()
    _tenant(esc.db, OWNER_B)
    esc.usuario(OWNER_B)
    puente_b = esc.inversion(OWNER_B)
    _tenant(esc.db, OWNER_A)
    esc.reparentar(puente_b, esc.plan)      # nodo de B colgando del PLAN de A
    esc.reparentar(esc.ajena, puente_b)     # AJENA de A colgando del nodo de B
    esc.principal(esc.plan)
    esc.asignacion(esc.ajena)
    _rechaza(esc.db, "no es su principal")


def test_0290_fail_closed_por_visibilidad(esc: Escenario) -> None:
    """D-118: si el efecto que motiva el evento no es visible, se falla cerrado."""
    esc.principal(esc.plan)
    esc.asignacion(esc.hija)
    _tenant(esc.db, OWNER_B)
    esc.db.execute("SAVEPOINT v")
    try:
        with pytest.raises(psycopg.errors.RaiseException, match="VISIBILIDAD"):
            _inmediato(esc.db)
    finally:
        esc.db.execute("ROLLBACK TO SAVEPOINT v")
        esc.db.execute("SET CONSTRAINTS ALL DEFERRED")
        _tenant(esc.db, OWNER_A)


# ------------------------------------------------------------
# Convivencia con la invariante de suma, que es independiente
# ------------------------------------------------------------

def test_0290_suma_sigue_vigente(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.hija, importe="900.0000")
    esc.asignacion(esc.nieta, importe="900.0000")
    _rechaza(esc.db, "supera en valor absoluto")


def test_0290_suma_signo_sigue_vigente(esc: Escenario) -> None:
    esc.principal(esc.plan)
    esc.asignacion(esc.hija, importe="-100.0000")
    _rechaza(esc.db, "mismo signo")


def test_0290_reparto_multipaso_valido(esc: Escenario) -> None:
    """El carácter diferido permite construir el reparto en varios INSERT."""
    esc.asignacion(esc.hija, importe="400.0000")
    esc.asignacion(esc.nieta, importe="600.0000")
    esc.principal(esc.plan)
    _acepta(esc.db)
