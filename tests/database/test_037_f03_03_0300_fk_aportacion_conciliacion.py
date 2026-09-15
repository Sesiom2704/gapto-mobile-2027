# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_037_f03_03_0300_fk_aportacion_conciliacion.py
# Ruta: tests/database/test_037_f03_03_0300_fk_aportacion_conciliacion.py
# Descripción: FASE 03 REABIERTA / D-168 + D-169. Cubre la migration 0300:
#              la FK compuesta de pertenencia
#                hecho_aportaciones_pago(hecho_id, hecho_movimiento_tesoreria_id)
#                -> hecho_movimientos_tesoreria(hecho_id, id)
#              aprobada por D-057 / F03-00-E2-D y nunca materializada hasta 0300.
#
#              DISCRIMINACION. Los casos negativos N1..N3 de este modulo PASAN
#              solo contra 0300 y FALLAN contra 0290, que aceptaba el enlace
#              cross-hecho. Se verifico experimentalmente contra el estado 0290
#              antes de aplicar la migration. Esa es la condicion de aceptacion
#              del Working Method: un test que no discrimina no prueba nada.
#
#              COBERTURA POR QUE NO BASTA LA POLICY. El caso N4 levanta FORCE
#              ROW LEVEL SECURITY dentro de la transaccion del test para simular
#              BYPASSRLS (patron de test_035). Es el argumento entero de 0300:
#              el WITH CHECK de la policy solo garantiza MISMO OWNER, no mismo
#              hecho, y ademas no sobrevive a BYPASSRLS. Si N4 pasara sin la FK,
#              la correccion seria innecesaria.
#
#              NO se prueba aqui la segunda invariante de D-169 (suma de
#              aportaciones vinculadas <= porcion conciliada). 0300 no la
#              materializa; corresponde a 0310 y a su propio modulo.
#
# PRECONDICIÓN: requiere 0300 aplicada.
# Versión: 0.1.1  -- D-173/D-174. Dos correcciones, ninguna toca 0300:
#              (1) el centinela de triggers/funciones reconoce el estado 0310
#                  POR NOMBRE, no por recuento: exige exactamente el unico
#                  constraint trigger que 0310 crea sobre hecho_aportaciones_pago
#                  y sigue delatando cualquier otro. Tambien el recuento de
#                  funciones pasa a conjunto finito (26 y 28); ese segundo
#                  fallo no figuraba en el informe del STOP porque la asercion
#                  de triggers abortaba antes de alcanzarlo.
#              (2) N4 ejecuta el ALTER TABLE ... NO FORCE ANTES de crear
#                  ningun fixture. El escenario insertaba conciliaciones que
#                  encolan eventos del constraint trigger diferido
#                  trg_hecho_movimientos_tesoreria__suma -preexistente a 0310-
#                  y PostgreSQL rechaza ALTER TABLE sobre una relacion con
#                  eventos pendientes. El caso estaba roto desde que se
#                  escribio: nunca llego a ejecutarse contra 0300. Es la regla
#                  transversal aprobada como D-173.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER_A = "aaaaaaaa-0300-4000-8000-000000000001"
OWNER_B = "bbbbbbbb-0300-4000-8000-000000000002"

FK_COMPUESTA = "fk_hecho_aportaciones_pago__hecho_conciliacion"
FK_SIMPLE = "fk_hecho_aportaciones_pago__movimiento"
ANCHOR = "uq_hecho_movimientos_tesoreria__hecho_anchor"
INDICE = "ix_hecho_aportaciones_pago__hecho_conciliacion"

DEFINICION_ESPERADA = (
    "FOREIGN KEY (hecho_id, hecho_movimiento_tesoreria_id) REFERENCES "
    "gapto.hecho_movimientos_tesoreria(hecho_id, id) ON DELETE RESTRICT"
)


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
    """Un movimiento de 200 EUR repartido entre dos hechos del MISMO owner.

    El reparto entre dos hechos es deliberado: es el escenario minimo en el que
    la policy de tenant no puede distinguir nada, porque ambas conciliaciones
    pertenecen al mismo usuario. Solo la FK compuesta separa H1 de H2.
    """

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        _tenant(db, OWNER_A)
        self.usuario(OWNER_A)
        self.cuenta = self.cuenta_de(OWNER_A)
        self.movimiento = self.movimiento_de(self.cuenta, "-200.0000")
        self.h1 = self.hecho(OWNER_A)
        self.h2 = self.hecho(OWNER_A)
        self.conc1 = self.conciliacion(self.h1, self.movimiento, "-100.0000")
        self.conc2 = self.conciliacion(self.h2, self.movimiento, "-100.0000")

    def usuario(self, owner: str) -> None:
        self.db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0300') "
            "ON CONFLICT DO NOTHING", (owner, f"{uuid.uuid4()}@example.invalid"))

    def cuenta_de(self, owner: str, moneda: str = "EUR") -> str:
        cid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "computa_liquidez, computa_patrimonio, permite_negativo) "
            "VALUES (%s, %s, %s, 'CORRIENTE', 'ACTIVO', %s, true, true, false)",
            (cid, owner, f"Cuenta {cid[:8]}", moneda))
        return cid

    def movimiento_de(self, cuenta: str, importe: str) -> str:
        mid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
            "confirmado_at, clase_movimiento) "
            "VALUES (%s, %s, CURRENT_DATE, %s, CURRENT_TIMESTAMP, 'OPERACION')",
            (mid, cuenta, importe))
        return mid

    def hecho(self, owner: str, moneda: str = "EUR") -> str:
        hid = str(uuid.uuid4())
        tipo = _uno(self.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        self.db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
            "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, '0300', '100.0000', %s, 'NO_APLICA', true)",
            (hid, owner, tipo, moneda))
        return hid

    def conciliacion(self, hecho: str, movimiento: str, importe: str) -> str:
        cid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_movimientos_tesoreria (id, hecho_id, movimiento_tesoreria_id, "
            "importe_asignado) VALUES (%s, %s, %s, %s)", (cid, hecho, movimiento, importe))
        return cid

    def aportacion(self, hecho: str, conciliacion: str | None,
                   importe: str = "50.0000") -> str:
        aid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_aportaciones_pago (id, hecho_id, importe, "
            "criterio_aportacion, hecho_movimiento_tesoreria_id) "
            "VALUES (%s, %s, %s, 'MANUAL', %s)", (aid, hecho, importe, conciliacion))
        return aid

    def otro_owner(self) -> None:
        _tenant(self.db, OWNER_B)
        self.usuario(OWNER_B)
        self.cuenta_b = self.cuenta_de(OWNER_B)
        self.movimiento_b = self.movimiento_de(self.cuenta_b, "-100.0000")
        self.hb = self.hecho(OWNER_B)
        self.conc_b = self.conciliacion(self.hb, self.movimiento_b, "-100.0000")
        _tenant(self.db, OWNER_A)

    @staticmethod
    def levantar_force(db: psycopg.Connection) -> None:
        """Simula un rol BYPASSRLS dentro de la transacción del test.

        DEBE invocarse ANTES de crear ningun fixture (D-173): en cuanto la
        transaccion escribe en una tabla con constraint triggers DEFERRABLE
        INITIALLY DEFERRED, PostgreSQL rechaza cualquier ALTER TABLE sobre ella
        con ObjectInUse / pending trigger events. hecho_movimientos_tesoreria ya
        llevaba trg_hecho_movimientos_tesoreria__suma antes de 0310, y 0310
        extiende la situacion a hecho_aportaciones_pago.

        El rollback del fixture db restaura FORCE ROW LEVEL SECURITY, porque
        ALTER TABLE es transaccional en PostgreSQL."""
        db.execute("ALTER TABLE gapto.hecho_aportaciones_pago NO FORCE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE gapto.hecho_movimientos_tesoreria NO FORCE ROW LEVEL SECURITY")


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

def test_0300_fk_compuesta_existe_y_esta_validada(db: psycopg.Connection) -> None:
    fila = _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(k.oid)
          FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::regclass
           AND k.conname = %s AND k.contype = 'f' AND k.convalidated
    """, (FK_COMPUESTA,))
    assert fila == DEFINICION_ESPERADA, f"definicion inesperada: {fila}"


def test_0300_fk_compuesta_consume_el_anchor_de_0080(db: psycopg.Connection) -> None:
    """D-057 exige que la FK apunte al anchor (hecho_id, id), no a otro indice."""
    consumidores = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint f
          JOIN pg_catalog.pg_constraint u ON u.conindid = f.conindid
         WHERE f.contype = 'f' AND f.conname = %s AND u.contype = 'u' AND u.conname = %s
    """, (FK_COMPUESTA, ANCHOR))
    assert consumidores == 1, "la FK compuesta no consume el anchor de hecho_movimientos_tesoreria"


def test_0300_ningun_anchor_contextual_queda_huerfano(db: psycopg.Connection) -> None:
    """R2 del gate de recierre. Esta comprobacion, sola, habria detectado el
    defecto el 2026-09-06: el anchor existia desde 0080 sin consumidor."""
    huerfanos = _uno(db, """
        WITH anchors AS (
          SELECT k.conname, k.conindid
            FROM pg_catalog.pg_constraint k
            JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
           WHERE c.relnamespace = 'gapto'::regnamespace AND k.contype = 'u'
             AND array_length(k.conkey, 1) = 2
             AND (SELECT a.attname FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid = k.conrelid AND a.attnum = k.conkey[2]) = 'id'
        )
        SELECT coalesce(string_agg(a.conname, ', ' ORDER BY a.conname), '')
          FROM anchors a
         WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint f
                            WHERE f.contype = 'f' AND f.conindid = a.conindid)
    """)
    assert huerfanos == "", f"anchors contextuales sin consumidor: {huerfanos}"


def test_0300_conserva_la_fk_simple(db: psycopg.Connection) -> None:
    """0288 fijo el precedente: no se retira una FK de la cadena congelada."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::regclass
           AND k.conname = %s AND k.contype = 'f'
    """, (FK_SIMPLE,)) == 1


def test_0300_indice_compuesto_presente_y_con_prefijo_correcto(db: psycopg.Connection) -> None:
    """D-169/S2 + F03-00-E1: indice util que COMIENZA por las columnas de la FK."""
    definicion = _uno(db, "SELECT indexdef FROM pg_catalog.pg_indexes "
                          "WHERE schemaname = 'gapto' AND indexname = %s", (INDICE,))
    assert definicion is not None, "falta el indice compuesto"
    assert definicion.endswith("(hecho_id, hecho_movimiento_tesoreria_id)"), definicion


def test_0300_force_rls_restaurado(db: psycopg.Connection) -> None:
    """D-094/D-095: la validacion levanta FORCE, pero no puede dejarlo levantado."""
    assert _uno(db, """
        SELECT c.relrowsecurity AND c.relforcerowsecurity
          FROM pg_catalog.pg_class c
         WHERE c.oid = 'gapto.hecho_aportaciones_pago'::regclass
    """) is True


def test_0300_contrato_fisico(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
         WHERE c.relnamespace = 'gapto'::regnamespace AND k.contype = 'f'
    """) == 175
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_indexes WHERE schemaname = 'gapto'") == 285


# Estados autorizados del centinela. Conjuntos EXPLICITOS Y FINITOS (D-173).
# 0310 crea UN solo constraint trigger sobre hecho_aportaciones_pago; cualquier
# otro nombre sigue significando que alguien ha adelantado trabajo sin
# autorizacion. Se compara por NOMBRE, no por recuento, porque aqui se puede.
TRIGGERS_AUTORIZADOS_EN_APORTACIONES = (
    frozenset(),                                              # 0300: ninguno
    frozenset({"trg_hecho_aportaciones_pago__conciliacion_suma"}),  # 0310
)
FUNCIONES_AUTORIZADAS = (26, 28)   # 26 en 0300; 28 con el nucleo y el despachador de 0310


def test_0300_no_introduce_triggers_ni_funciones(db: psycopg.Connection) -> None:
    """0300 es integridad declarativa pura: por si sola no anade funciones ni
    triggers procedimentales.

    El centinela NO se relaja a "cualquier trigger posterior". Reconoce
    exactamente el estado que 0310 autoriza y sigue delatando cualquier otro:
    esa es la razon por la que este test existe y la que hizo que detectara la
    llegada de 0310."""
    nombres = frozenset(
        r[0] for r in db.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = 'gapto.hecho_aportaciones_pago'::regclass
               AND NOT t.tgisinternal
        """).fetchall()
    )
    assert nombres in TRIGGERS_AUTORIZADOS_EN_APORTACIONES, (
        f"triggers no autorizados en hecho_aportaciones_pago: {sorted(nombres)}")

    funciones = _uno(db, "SELECT count(*) FROM pg_catalog.pg_proc p "
                         "WHERE p.pronamespace = 'gapto'::regnamespace")
    assert funciones in FUNCIONES_AUTORIZADAS, (
        f"{funciones} funciones; autorizadas {FUNCIONES_AUTORIZADAS}")


# ------------------------------------------------------------
# Comportamiento: casos positivos
# ------------------------------------------------------------

def test_p1_aportacion_vinculada_a_conciliacion_del_mismo_hecho(esc: Escenario) -> None:
    assert esc.aportacion(esc.h1, esc.conc1) is not None


def test_p2_aportacion_sin_vinculo_es_valida(esc: Escenario) -> None:
    """MATCH SIMPLE: el vinculo con la conciliacion es opcional por contrato."""
    assert esc.aportacion(esc.h1, None) is not None


def test_p3_desvincular_una_aportacion_es_valido(esc: Escenario) -> None:
    aid = esc.aportacion(esc.h1, esc.conc1)
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago "
                   "SET hecho_movimiento_tesoreria_id = NULL WHERE id = %s", (aid,))


def test_p4_varias_aportaciones_sobre_la_misma_conciliacion(esc: Escenario) -> None:
    """0300 NO limita la suma: eso es 0310. Dos aportaciones de 80 sobre una
    porcion de 100 deben seguir siendo aceptadas por el estado fisico actual.
    Cuando 0310 se materialice, este test debera moverse o invertirse."""
    esc.aportacion(esc.h1, esc.conc1, "80.0000")
    esc.aportacion(esc.h1, esc.conc1, "80.0000")


# ------------------------------------------------------------
# Comportamiento: casos negativos (discriminantes contra 0290)
# ------------------------------------------------------------

def test_n1_insert_cross_hecho_del_mismo_owner_es_rechazado(esc: Escenario) -> None:
    """EL CASO. Ambos hechos son del mismo owner y la policy los acepta: solo la
    FK compuesta impide anclar la financiacion de H1 a la tesoreria de H2."""
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.aportacion(esc.h1, esc.conc2)


def test_n2_relink_a_conciliacion_de_otro_hecho_es_rechazado(esc: Escenario) -> None:
    aid = esc.aportacion(esc.h1, esc.conc1)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.db.execute("UPDATE gapto.hecho_aportaciones_pago "
                       "SET hecho_movimiento_tesoreria_id = %s WHERE id = %s", (esc.conc2, aid))


def test_n3_delete_de_la_conciliacion_vinculada_es_restrict(esc: Escenario) -> None:
    esc.aportacion(esc.h1, esc.conc1)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.db.execute("DELETE FROM gapto.hecho_movimientos_tesoreria WHERE id = %s",
                       (esc.conc1,))


def test_n4_cross_hecho_sigue_rechazado_sin_force_rls(db: psycopg.Connection) -> None:
    """D-100: la integridad es de PostgreSQL, no de RLS. Con FORCE levantado
    (equivalente a BYPASSRLS) la policy ya no protege nada y la FK debe seguir
    siendo la barrera.

    Toma db en lugar de esc para poder ejecutar el DDL ANTES del DML: el orden
    DDL -> DML es el aprobado por D-173, y evita que el montaje del test quede
    bloqueado por eventos diferidos ajenos a la propiedad que se prueba. No se
    usa SET CONSTRAINTS ALL IMMEDIATE: no hace falta."""
    Escenario.levantar_force(db)
    esc = Escenario(db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.aportacion(esc.h1, esc.conc2)


def test_n5_cross_tenant_sigue_rechazado(esc: Escenario) -> None:
    """La garantia de owner preexistente no se pierde al anadir la compuesta."""
    esc.otro_owner()
    with pytest.raises(psycopg.errors.Error):
        esc.aportacion(esc.h1, esc.conc_b)


def test_n6_mover_el_hecho_de_la_aportacion_rompe_la_pertenencia(esc: Escenario) -> None:
    """Simetrico de N2: el predicado tambien puede romperse cambiando hecho_id
    en lugar de la conciliacion."""
    aid = esc.aportacion(esc.h1, esc.conc1)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET hecho_id = %s WHERE id = %s",
                       (esc.h2, aid))
