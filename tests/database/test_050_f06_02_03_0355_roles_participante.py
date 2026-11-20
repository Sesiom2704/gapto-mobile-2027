# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_050_f06_02_03_0355_roles_participante.py
# Ruta: tests/database/test_050_f06_02_03_0355_roles_participante.py
# Descripcion: Verifica la migration 0355 (MIG-ALQ-ROLES; T3-F06 bloque 3
#              F06-02/03; mandato v1.2 §9; contrato N1 v1.1 §IX).
#
#              CONTRATO. ck_contrato_participantes__rol conserva su nombre y
#              su definicion es EXACTAMENTE la literal nueva (los cuatro roles
#              de 0050 mas AGENCIA y ADMINISTRADOR); el resto de constraints de
#              la tabla, su ACL y FORCE RLS no cambian.
#
#              COMPORTAMIENTO BAJO gapto_runtime (RLS y FORCE activos). Cada
#              caso abre UNA transaccion que termina SIEMPRE en ROLLBACK: fija
#              la GUC de tenant, crea los fixtures sinteticos bajo SET LOCAL
#              ROLE gapto_owner, vacia los diferidos (D-173) y pasa a
#              gapto_runtime. Los seis roles se admiten; un rol inventado sigue
#              rechazado con 23514 y el nombre de la constraint; la EXCLUDE de
#              un principal por contrato y rol (0100) vale para los roles
#              nuevos; otro owner no puede escribir ni ver (aislamiento).
#
#              DISCRIMINACION CONTRA 0354 (WM 12C.2). (a) Ejecutado contra una
#              base en 0354, el modulo falla en la definicion, en las altas con
#              AGENCIA/ADMINISTRADOR (23514), en la huella y en la reaplicacion.
#              (b) Ademas, dentro de una transaccion revertida se repone la
#              definicion de 0354 y la misma alta con AGENCIA falla con 23514:
#              el test demuestra su propia capacidad de discriminar.
#
#              APLICACION SIMULADA. En una transaccion revertida se repone la
#              CHECK de 0354, se siembran participantes con los cuatro roles de
#              partida y se ejecuta el cuerpo LITERAL de 0355 sin BEGIN/COMMIT:
#              filas intactas, definicion nueva, FORCE restaurado. Una
#              definicion de partida distinta de la literal BLOQUEA el precheck
#              (fail-closed, STOP 8 del contrato) sin corregir nada.
#
#              HUELLA D-111. HUELLAS_D111_POR_HEAD['0355'] esta PENDIENTE_REPLAY
#              (None, fail-closed) hasta medirla en el replay 0001..0355: los
#              tests de huella y desviacion FALLAN mientras tanto, a proposito.
# Version: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03; mandato v1.2 §9, contrato v1.1 §IX): test nuevo.
# ============================================================
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0355_f06_02_03_alq_roles_participante.sql"
OWNER = "0355a000-0000-4000-8000-000000000001"
OTRO_OWNER = "0355a000-0000-4000-8000-000000000002"
INICIO = dt.date(2026, 1, 1)
CK = "ck_contrato_participantes__rol"

ROLES_0354 = ("PROPIETARIO", "INQUILINO", "AVALISTA", "GESTOR")
ROLES_NUEVOS = ("AGENCIA", "ADMINISTRADOR")
ROLES_INVENTADOS = ("ARRENDADOR", "AGENTE", "agencia", "ADMINISTRADORA", "")

DEF_0354 = ("CHECK (((rol)::text = ANY ((ARRAY['PROPIETARIO'::character varying, 'INQUILINO'::character varying, "
            "'AVALISTA'::character varying, 'GESTOR'::character varying])::text[])))")
DEF_0355 = ("CHECK (((rol)::text = ANY ((ARRAY['PROPIETARIO'::character varying, 'INQUILINO'::character varying, "
            "'AVALISTA'::character varying, 'GESTOR'::character varying, 'AGENCIA'::character varying, "
            "'ADMINISTRADOR'::character varying])::text[])))")
CONSTRAINTS_TABLA = {
    "pk_contrato_participantes", "ck_contrato_participantes__rol", "ck_contrato_participantes__vigencia",
    "fk_contrato_participantes__contrato", "fk_contrato_participantes__actor",
    "ex_contrato_participantes__contrato_actor_rol", "ex_contrato_participantes__principal_por_rol",
}
PENDIENTE = ("PENDIENTE_REPLAY: HUELLAS_D111_POR_HEAD['0355'] solo puede salir del replay 0001..0355 "
             "de la clean-room; nunca se declara a mano")


def _runner():
    spec = importlib.util.spec_from_file_location("rcr", RAIZ / "scripts" / "postgres" / "run_clean_room.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cur:
        cur.execute(sql, params)
        fila = cur.fetchone()
    return fila[0] if fila else None


def cuerpo_0355() -> str:
    """Cuerpo de 0355 sin su control transaccional, extraido del fichero."""
    texto = MIGRATION.read_text(encoding="utf-8")
    inicio = texto.index("\nBEGIN;\n") + len("\nBEGIN;\n")
    fin = texto.rindex("\nCOMMIT;")
    return texto[inicio:fin]


def _definicion(db: psycopg.Connection) -> str | None:
    return _uno(db, "SELECT pg_catalog.pg_get_constraintdef(k.oid) FROM pg_catalog.pg_constraint k "
                    "WHERE k.conrelid = 'gapto.contrato_participantes'::regclass AND k.conname = %s", (CK,))


def _reponer_check(db: psycopg.Connection, roles: tuple[str, ...]) -> None:
    """Sustituye la CHECK como gapto_owner dentro de la transaccion revertida del llamador."""
    lista = ",".join(f"'{r}'" for r in roles)
    db.execute("SET LOCAL ROLE gapto_owner")
    db.execute(f"ALTER TABLE gapto.contrato_participantes DROP CONSTRAINT {CK}, "
               f"ADD CONSTRAINT {CK} CHECK (rol IN ({lista}))")


# ------------------------------------------------------------------ escenario
class Esc:
    """Un owner con una propiedad, un contrato y actores sinteticos (transaccion revertida del llamador)."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute("SET LOCAL ROLE gapto_owner")
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0355') ON CONFLICT DO NOTHING",
                   (OWNER, f"{uuid.uuid4()}@example.invalid"))
        self.prop, self.contrato = str(uuid.uuid4()), str(uuid.uuid4())
        for eid, tipo in ((self.prop, "PROPIEDAD"), (self.contrato, "CONTRATO")):
            db.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, %s, %s, %s)",
                       (eid, OWNER, tipo, f"0355 {tipo.lower()}"))
        db.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')", (self.prop,))
        db.execute("INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, tipo_contrato) "
                   "VALUES (%s, %s, 'ALQUILER_VIVIENDA')", (self.contrato, self.prop))
        self.actores = [self.actor() for _ in range(3)]

    def actor(self) -> str:
        aid = str(uuid.uuid4())
        self.db.execute("INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)", (aid, OWNER))
        return aid

    def participante(self, rol: str, actor: str, *, principal: bool = False, desde: dt.date = INICIO,
                     hasta: dt.date | None = None) -> None:
        self.db.execute("INSERT INTO gapto.contrato_participantes (contrato_entidad_id, actor_id, rol, principal, "
                        "vigente_desde, vigente_hasta) VALUES (%s, %s, %s, %s, %s, %s)",
                        (self.contrato, actor, rol, principal, desde, hasta))

    def fijar(self) -> None:
        """Vacia los diferidos de los fixtures, vuelve a diferir y pasa a gapto_runtime (RLS y FORCE)."""
        self.db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.db.execute("SET CONSTRAINTS ALL DEFERRED")
        self.db.execute("SET LOCAL ROLE gapto_runtime")


def _intentar(db: psycopg.Connection, accion) -> str | None:
    """None si se admite; el SQLSTATE y la constraint si se rechaza. El caso siempre se revierte."""
    try:
        with db.transaction(force_rollback=True):
            accion()
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except psycopg.errors.IntegrityError as exc:
        return f"{exc.sqlstate}:{exc.diag.constraint_name}"
    return None


# ------------------------------------------------------------------ contrato fisico
def test_0355_definicion_literal_y_nombre_conservado(db):
    with db.cursor() as cur:
        cur.execute("SELECT k.contype, k.convalidated, pg_catalog.pg_get_constraintdef(k.oid) "
                    "FROM pg_catalog.pg_constraint k "
                    "WHERE k.conrelid = 'gapto.contrato_participantes'::regclass AND k.conname = %s", (CK,))
        filas = cur.fetchall()
    assert filas == [("c", True, DEF_0355)]


def test_0355_constraints_de_la_tabla_intactas(db):
    with db.cursor() as cur:
        cur.execute("SELECT k.conname FROM pg_catalog.pg_constraint k "
                    "WHERE k.conrelid = 'gapto.contrato_participantes'::regclass AND k.contype <> 'n'")
        nombres = {f[0] for f in cur.fetchall()}
    assert nombres == CONSTRAINTS_TABLA


def test_0355_force_rls_restaurado(db):
    assert _uno(db, "SELECT relrowsecurity AND relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid = 'gapto.contrato_participantes'::regclass") is True
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace = 'gapto'::regnamespace "
                    "AND c.relkind = 'r' AND c.relrowsecurity AND c.relforcerowsecurity") == 75


def test_0355_privilegios_sin_cambio(db):
    for priv, esperado in (("SELECT", True), ("INSERT", True), ("UPDATE", True), ("DELETE", False)):
        assert _uno(db, "SELECT has_table_privilege('gapto_runtime', 'gapto.contrato_participantes', %s)",
                    (priv,)) is esperado, priv
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_class c CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a "
                    "WHERE c.relnamespace = 'gapto'::regnamespace AND c.relkind IN ('r', 'v', 'p') "
                    "AND a.grantee = 'gapto_runtime'::regrole") == 266


# ------------------------------------------------------------------ comportamiento bajo gapto_runtime
@pytest.mark.parametrize("rol", ROLES_0354 + ROLES_NUEVOS)
def test_0355_runtime_admite_los_seis_roles(db, rol):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.fijar()
        assert _intentar(db, lambda: e.participante(rol, e.actores[0])) is None


@pytest.mark.parametrize("rol", ROLES_INVENTADOS)
def test_0355_runtime_rechaza_rol_inventado(db, rol):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.fijar()
        assert _intentar(db, lambda: e.participante(rol, e.actores[0])) == f"23514:{CK}"


@pytest.mark.parametrize("rol", ROLES_NUEVOS)
def test_0355_discrimina_contra_la_definicion_de_0354(db, rol):
    """Con la CHECK de 0354 repuesta (transaccion revertida) la misma alta falla con 23514; GESTOR sigue
    admitido. Demuestra que los positivos de este modulo distinguen 0355 de 0354."""
    with db.transaction(force_rollback=True):
        e = Esc(db)
        _reponer_check(db, ROLES_0354)
        assert _definicion(db) == DEF_0354
        e.fijar()
        assert _intentar(db, lambda: e.participante(rol, e.actores[0])) == f"23514:{CK}"
        assert _intentar(db, lambda: e.participante("GESTOR", e.actores[0])) is None


@pytest.mark.parametrize("rol", ROLES_NUEVOS)
def test_0355_un_principal_por_contrato_y_rol_nuevo(db, rol):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.fijar()
        a1, a2 = e.actores[0], e.actores[1]
        def solapado():
            e.participante(rol, a1, principal=True)
            e.participante(rol, a2, principal=True, desde=INICIO + dt.timedelta(days=10))
        assert _intentar(db, solapado) == "23P01:ex_contrato_participantes__principal_por_rol"

        def sucesivo():
            e.participante(rol, a1, principal=True, hasta=INICIO + dt.timedelta(days=9))
            e.participante(rol, a2, principal=True, desde=INICIO + dt.timedelta(days=10))
        assert _intentar(db, sucesivo) is None

        def sin_principal():
            e.participante(rol, a1)
            e.participante(rol, a2)
        assert _intentar(db, sin_principal) is None


def test_0355_agencia_y_administrador_principales_a_la_vez(db):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.fijar()
        def ambos():
            e.participante("AGENCIA", e.actores[0], principal=True)
            e.participante("ADMINISTRADOR", e.actores[0], principal=True)
            e.participante("INQUILINO", e.actores[1], principal=True)
        assert _intentar(db, ambos) is None


def test_0355_aislamiento_por_owner(db):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.participante("AGENCIA", e.actores[0])
        e.fijar()
        assert _uno(db, "SELECT count(*) FROM gapto.contrato_participantes WHERE contrato_entidad_id = %s",
                    (e.contrato,)) == 1
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        assert _uno(db, "SELECT count(*) FROM gapto.contrato_participantes WHERE contrato_entidad_id = %s",
                    (e.contrato,)) == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.transaction():
                e.participante("ADMINISTRADOR", e.actores[1])


# ------------------------------------------------------------------ cuerpo de la migration
def test_0355_reaplicar_rechazado_por_precheck(db):
    with pytest.raises(psycopg.errors.RaiseException, match="0355 ya esta aplicada"):
        with db.transaction(force_rollback=True):
            db.execute(cuerpo_0355())


def _sembrar_en_0354(db: psycopg.Connection, roles_check: tuple[str, ...]) -> Esc:
    e = Esc(db)
    for i, rol in enumerate(r for r in ROLES_0354 if r in roles_check):   # filas validas para la CHECK repuesta
        e.participante(rol, e.actores[i % 3], principal=(rol == "INQUILINO"))
    db.execute("SET CONSTRAINTS ALL IMMEDIATE")  # D-173: sin eventos diferidos antes del ALTER
    db.execute("SET CONSTRAINTS ALL DEFERRED")
    _reponer_check(db, roles_check)
    db.execute("RESET ROLE")
    return e


def _filas(db: psycopg.Connection) -> str:
    db.execute("SET LOCAL ROLE gapto_owner")
    db.execute("ALTER TABLE gapto.contrato_participantes NO FORCE ROW LEVEL SECURITY")
    huella = _uno(db, "SELECT count(*)::text || ':' || coalesce(md5(string_agg(to_jsonb(p)::text, E'\\n' "
                      "ORDER BY p.id)), '-') FROM gapto.contrato_participantes p")
    db.execute("ALTER TABLE gapto.contrato_participantes FORCE ROW LEVEL SECURITY")
    db.execute("RESET ROLE")
    return huella


def test_0355_aplicacion_simulada_sobre_0354(db):
    with db.transaction(force_rollback=True):
        _sembrar_en_0354(db, ROLES_0354)
        assert _definicion(db) == DEF_0354
        antes = _filas(db)
        assert int(antes.split(":")[0]) >= 4
        db.execute(cuerpo_0355())
        assert _definicion(db) == DEF_0355
        assert _filas(db) == antes
        assert _uno(db, "SELECT relrowsecurity AND relforcerowsecurity FROM pg_catalog.pg_class "
                        "WHERE oid = 'gapto.contrato_participantes'::regclass") is True


@pytest.mark.parametrize("roles", [ROLES_0354 + ("OTRO",), ROLES_0354[:3],
                                   ("INQUILINO", "PROPIETARIO", "AVALISTA", "GESTOR")],
                         ids=["rol_de_mas", "sin_gestor", "orden_distinto"])
def test_0355_precheck_bloquea_definicion_distinta(db, roles):
    """Fail-closed (STOP 8 del contrato): si la definicion vigente no es la literal, 0355 no se aplica."""
    with db.transaction(force_rollback=True):
        _sembrar_en_0354(db, roles)
        with pytest.raises(psycopg.errors.RaiseException, match="PRECHECK: BLOQUEA"):
            with db.transaction():
                db.execute(cuerpo_0355())


# ------------------------------------------------------------------ fichero y runner (sin base)
def test_0355_fichero_forma():
    texto = MIGRATION.read_text(encoding="utf-8")
    assert texto.count("\nBEGIN;\n") == 1 and texto.count("\nCOMMIT;\n") == 1
    cuerpo = cuerpo_0355()
    for prohibido in ("CREATE ", "GRANT ", "REVOKE ", "INSERT INTO", "UPDATE gapto", "DELETE FROM", "COMMENT ON",
                      "SET search_path", "SECURITY DEFINER", "TRUNCATE", "POLICY"):
        assert prohibido not in cuerpo, prohibido
    assert cuerpo.count("ALTER TABLE") == 3
    assert cuerpo.count("ALTER TABLE gapto.contrato_participantes NO FORCE ROW LEVEL SECURITY;") == 1
    assert cuerpo.count("ALTER TABLE gapto.contrato_participantes FORCE ROW LEVEL SECURITY;") == 1
    assert cuerpo.count("DROP ") == 1 and cuerpo.count("ADD CONSTRAINT") == 1
    assert ("ALTER TABLE gapto.contrato_participantes\n    DROP CONSTRAINT ck_contrato_participantes__rol,\n"
            "    ADD CONSTRAINT ck_contrato_participantes__rol\n"
            "        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR','AGENCIA','ADMINISTRADOR'));\n"
            ) in cuerpo
    assert cuerpo.index("NO FORCE ROW LEVEL SECURITY") < cuerpo.index("DROP CONSTRAINT") < cuerpo.index(
        "contrato_participantes FORCE ROW LEVEL SECURITY")
    assert DEF_0354 in texto and DEF_0355 in texto


def test_0355_regla_de_migrations_del_bloque():
    """Mandato v1.2 §1: tras 0354 la unica migration nueva es esta 0355."""
    posteriores = sorted(p.name for p in (RAIZ / "migrations").glob("*.sql") if p.name[:4] > "0354")
    assert posteriores == [MIGRATION.name]


def test_0355_runner_declara_0355_y_conserva_0354():
    runner = _runner()
    assert runner.CONTRATOS_POR_HEAD["0355"] == runner.CONTRATOS_POR_HEAD["0354"]
    assert runner.CONTRATO_POR_DEFECTO is runner.CONTRATOS_POR_HEAD["0355"]
    exigidos = runner.TESTS_EXIGIDOS_POR_HEAD
    assert exigidos["0355"] == (*exigidos["0354"], "test_050_f06_02_03_0355_roles_participante")
    assert "test_050_f06_02_03_0355_roles_participante" not in exigidos["0354"]
    assert {"0354", "0355"} <= set(runner.HEADS_QUE_EXIGEN_REFERENCIA_D111)
    assert "0355" in runner.HUELLAS_D111_POR_HEAD


def test_0355_huella_d111_current(db):
    referencia = _runner().HUELLAS_D111_POR_HEAD["0355"]
    assert referencia is not None, PENDIENTE
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    observadas = dict(zip([d.name for d in cursor.description], cursor.fetchone()))
    assert {k: observadas[k] for k in referencia} == referencia


def test_0355_desviacion_frente_a_0354_solo_h2():
    h = _runner().HUELLAS_D111_POR_HEAD
    assert h["0355"] is not None, PENDIENTE
    assert set(h["0355"]) == set(h["0354"])
    assert {k for k in h["0355"] if h["0355"][k] != h["0354"][k]} == {"h2_constraints"}
    assert h["0355"]["recuentos"] == h["0354"]["recuentos"] == "788/655/287/82/65/34/1024/3"
