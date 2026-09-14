# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_034_f03_02_0286_efecto_cuentas.py
# Ruta: tests/database/test_034_f03_02_0286_efecto_cuentas.py
# Descripción: FASE 03 / F03-02 / migration 0286 / D-146 / F02-F01-R2.
#              Fija el contrato de gapto.efecto_cuentas: relación
#              efecto --GENERADO_POR--> cuenta, a nivel de EFECTO, con una
#              sola cuenta generadora por efecto, integridad declarativa de
#              ownership y pertenencia, y el invariante fundamental de que la
#              relación no altera saldo, deuda, liquidez, gasto ni ingreso.
#              Todos los casos se ejecutan con el rol de conexión, sea cual
#              sea, creando los datos bajo SET ROLE gapto_owner (D-137), y las
#              transacciones se revierten siempre.
# Versión: 0.1.1  -- el contrato de FK sube a 174 por 0288.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER_A = "c0286000-0000-4000-8000-000000000001"
OWNER_B = "c0286000-0000-4000-8000-000000000002"

HUELLAS_0286 = {
    "tablas": 80,
    "policies": 82,
    # SUCESORA 0288: +5 FK compuestas de tenant fuera de esta tabla.
    "foreign_keys": 174,
    "unique_constraints": 41,
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
    """Monta el caso real: póliza de crédito, cuenta corriente y un hecho de
    comisión con un efecto de gasto. Nada de esto se confirma."""

    def __init__(self, db: psycopg.Connection, owner: str, limite: str = "30000.0000") -> None:
        self.db = db
        self.owner = owner
        self.usuario(owner)
        self.poliza = self.cuenta("POLIZA_CREDITO", "PASIVO", limite)
        self.corriente = self.cuenta("CORRIENTE", "ACTIVO", None)
        self.hecho, self.efecto = self.hecho_gasto("9.9000")

    def usuario(self, owner: str) -> None:
        self.db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (owner, f"{uuid.uuid4()}@example.invalid", "0286"),
        )

    def cuenta(self, tipo: str, naturaleza: str, limite: str | None, owner: str | None = None) -> str:
        cid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "limite_credito, permite_negativo, computa_liquidez, computa_patrimonio, orden, enabled) "
            "VALUES (%s, %s, %s, %s, %s, 'EUR', %s, %s, true, true, 0, true)",
            (cid, owner or self.owner, f"{tipo} {cid[:8]}", tipo, naturaleza, limite,
             naturaleza == "PASIVO"),
        )
        return cid

    def hecho_gasto(self, importe: str, owner: str | None = None) -> tuple[str, str]:
        hid, eid = str(uuid.uuid4()), str(uuid.uuid4())
        tipo = _uno(self.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        self.db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
            "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, 'EUR', 'NO_APLICA', true)",
            (hid, owner or self.owner, tipo, "comision poliza", importe),
        )
        self.db.execute(
            "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
            "estado_atribucion) VALUES (%s, %s, 'GASTO', %s, 'NO_DISPONIBLE')",
            (eid, hid, importe),
        )
        return hid, eid

    def generado_por(self, cuenta: str, efecto: str | None = None, hecho: str | None = None,
                     owner: str | None = None, tipo: str = "GENERADO_POR") -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.efecto_cuentas (id, owner_user_id, hecho_id, efecto_id, cuenta_id, "
            "tipo_relacion) VALUES (%s, %s, %s, %s, %s, %s)",
            (rid, owner or self.owner, hecho or self.hecho, efecto or self.efecto, cuenta, tipo),
        )
        return rid

    def saldo(self, cuenta: str) -> str:
        return _uno(self.db, """
            SELECT coalesce((SELECT c.saldo_apertura FROM gapto.cuentas c WHERE c.id = %s), 0)
                 + coalesce((SELECT sum(m.importe) FROM gapto.movimientos_tesoreria m
                              WHERE m.cuenta_id = %s AND m.estado = 'ACTIVO'), 0)""",
            (cuenta, cuenta))


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    _tenant(db, OWNER_A)
    return Escenario(db, OWNER_A)


# ------------------------------------------------------------
# T1-T3. Estructura y vocabulario
# ------------------------------------------------------------

def test_0286_estructura_de_la_tabla(db: psycopg.Connection) -> None:
    columnas = {
        r[0]: (r[1], r[2])
        for r in db.execute("""
            SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
               AND a.attnum > 0 AND NOT a.attisdropped""").fetchall()
    }
    assert columnas == {
        "id": ("uuid", True),
        "owner_user_id": ("uuid", True),
        "hecho_id": ("uuid", True),
        "efecto_id": ("uuid", True),
        "cuenta_id": ("uuid", True),
        "tipo_relacion": ("character varying(50)", True),
    }, "la tabla no debe crecer con columnas no aprobadas; efecto_id es NOT NULL"


def test_0286_sin_lifecycle_ni_triggers(db: psycopg.Connection) -> None:
    """La familia de puentes del núcleo no lleva lifecycle, y la tabla debe ser
    inerte: sin trigger no puede tocar ningún saldo."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
           AND a.attname IN ('enabled', 'deleted_at', 'created_at', 'updated_at',
                             'row_version', 'principal')""") == 0
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
         WHERE t.tgrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
           AND NOT t.tgisinternal""") == 0


def test_0286_integridad_declarativa(db: psycopg.Connection) -> None:
    """Ownership y pertenencia del efecto son FK compuestas contra los anchors,
    no policies ni triggers: sobreviven a BYPASSRLS (D-100)."""
    defs = {
        r[0]: r[1]
        for r in db.execute("""
            SELECT k.conname, pg_catalog.pg_get_constraintdef(k.oid)
              FROM pg_catalog.pg_constraint k
             WHERE k.conrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass""").fetchall()
    }
    assert defs["fk_efecto_cuentas__hecho"] == (
        "FOREIGN KEY (owner_user_id, hecho_id) REFERENCES "
        "gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT")
    assert defs["fk_efecto_cuentas__efecto"] == (
        "FOREIGN KEY (hecho_id, efecto_id) REFERENCES "
        "gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT")
    assert defs["fk_efecto_cuentas__cuenta"] == (
        "FOREIGN KEY (owner_user_id, cuenta_id) REFERENCES "
        "gapto.cuentas(owner_user_id, id) ON DELETE RESTRICT")
    assert defs["uq_efecto_cuentas__efecto_cuenta_tipo"] == (
        "UNIQUE (efecto_id, cuenta_id, tipo_relacion)")


def test_0286_unicidad_de_cuenta_generadora(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT pg_catalog.pg_get_indexdef(i.indexrelid)
          FROM pg_catalog.pg_index i
         WHERE i.indrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
           AND i.indexrelid::pg_catalog.regclass::text
               = 'gapto.ux_efecto_cuentas__generado_por'""") == (
        "CREATE UNIQUE INDEX ux_efecto_cuentas__generado_por ON gapto.efecto_cuentas "
        "USING btree (efecto_id) WHERE ((tipo_relacion)::text = 'GENERADO_POR'::text)")


def test_0286_vocabulario_minimo(db: psycopg.Connection) -> None:
    """Solo GENERADO_POR. PAGADO_DESDE y FINANCIADO_POR ya viven en tesorería y
    aportaciones; duplicarlos crearía una segunda fuente de verdad."""
    definicion = _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(k.oid) FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
           AND k.conname = 'ck_efecto_cuentas__tipo_relacion'""")
    assert "'GENERADO_POR'" in definicion
    for prohibido in ("PAGADO_DESDE", "FINANCIADO_POR", "RELACIONADO_CON"):
        assert prohibido not in definicion


def test_0286_tipo_relacion_invalido_se_rechaza(esc: Escenario) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(esc.poliza, tipo="PAGADO_DESDE")


# ------------------------------------------------------------
# T4-T9. Semántica de la relación
# ------------------------------------------------------------

def test_0286_relacion_a_nivel_de_efecto(esc: Escenario) -> None:
    esc.generado_por(esc.poliza)
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.efecto_cuentas
         WHERE efecto_id = %s AND cuenta_id = %s AND tipo_relacion = 'GENERADO_POR'""",
        (esc.efecto, esc.poliza)) == 1


def test_0286_segunda_cuenta_generadora_se_rechaza(esc: Escenario) -> None:
    """R9: si un efecto pudiera tener dos cuentas generadoras, GENERADO_POR
    dejaría de significar origen. Una comisión conjunta de dos instrumentos se
    representa como dos efectos."""
    esc.generado_por(esc.poliza)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(esc.corriente)


def test_0286_duplicado_exacto_se_rechaza(esc: Escenario) -> None:
    esc.generado_por(esc.poliza)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(esc.poliza)


def test_0286_dos_efectos_del_mismo_hecho_con_cuentas_distintas(esc: Escenario) -> None:
    """R8: un hecho puede tener varios efectos y solo alguno pertenecer
    funcionalmente a una cuenta determinada."""
    segundo = str(uuid.uuid4())
    esc.db.execute(
        "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
        "estado_atribucion) VALUES (%s, %s, 'GASTO', '1.0000', 'NO_DISPONIBLE')",
        (segundo, esc.hecho))
    esc.generado_por(esc.poliza)
    esc.generado_por(esc.corriente, efecto=segundo)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.efecto_cuentas WHERE hecho_id = %s",
                (esc.hecho,)) == 2


def test_0286_efecto_de_otro_hecho_se_rechaza(esc: Escenario) -> None:
    """R12: la FK compuesta impide declarar un efecto que no pertenece al hecho."""
    otro_hecho, otro_efecto = esc.hecho_gasto("5.0000")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(esc.poliza, efecto=otro_efecto)
    assert otro_hecho is not None


def test_0286_dos_polizas_del_mismo_banco_se_discriminan(esc: Escenario) -> None:
    """R4: la discriminación es por cuenta, nunca por tercero."""
    pol2 = esc.cuenta("POLIZA_CREDITO", "PASIVO", "15000.0000")
    esc.generado_por(esc.poliza)
    hecho2, efecto2 = esc.hecho_gasto("35.0000")
    esc.generado_por(pol2, efecto=efecto2, hecho=hecho2)
    assert str(_uno(esc.db, "SELECT cuenta_id FROM gapto.efecto_cuentas WHERE efecto_id = %s",
                    (esc.efecto,))) == esc.poliza
    assert str(_uno(esc.db, "SELECT cuenta_id FROM gapto.efecto_cuentas WHERE efecto_id = %s",
                    (efecto2,))) == pol2


@pytest.mark.parametrize("tipo,naturaleza", [
    ("CORRIENTE", "ACTIVO"),   # R5 comision de mantenimiento
    ("CREDITO", "PASIVO"),     # R6 cuota anual de tarjeta
    ("POLIZA_CREDITO", "PASIVO"),
])
def test_0286_la_relacion_no_es_especifica_de_polizas(esc: Escenario, tipo: str,
                                                      naturaleza: str) -> None:
    cuenta = esc.cuenta(tipo, naturaleza, "1000.0000" if naturaleza == "PASIVO" else None)
    esc.generado_por(cuenta)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.efecto_cuentas WHERE cuenta_id = %s",
                (cuenta,)) == 1


def test_0286_cuenta_deshabilitada_sigue_siendo_valida(esc: Escenario) -> None:
    """R15: una cuenta cerrada sigue siendo históricamente válida como cuenta
    generadora; la FK no mira enabled."""
    esc.db.execute("UPDATE gapto.cuentas SET enabled = false, fecha_cierre = CURRENT_DATE "
                   "WHERE id = %s", (esc.poliza,))
    esc.generado_por(esc.poliza)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.efecto_cuentas WHERE cuenta_id = %s",
                (esc.poliza,)) == 1


def test_0286_correccion_por_update(esc: Escenario) -> None:
    """R14: capturar POL1 cuando era POL2 se corrige con UPDATE auditado."""
    rid = esc.generado_por(esc.poliza)
    pol2 = esc.cuenta("POLIZA_CREDITO", "PASIVO", "5000.0000")
    esc.db.execute("UPDATE gapto.efecto_cuentas SET cuenta_id = %s WHERE id = %s", (pol2, rid))
    assert str(_uno(esc.db, "SELECT cuenta_id FROM gapto.efecto_cuentas WHERE id = %s", (rid,))) == pol2


# ------------------------------------------------------------
# T11-T17. Invariante fundamental: la relación no mueve dinero
# ------------------------------------------------------------

def test_0286_no_altera_saldo_ni_crea_movimiento_ni_efecto(esc: Escenario) -> None:
    """T11, T12 y T13 en una sola comprobación: nada cambia salvo la fila de
    trazabilidad."""
    antes = (esc.saldo(esc.poliza),
             _uno(esc.db, "SELECT count(*) FROM gapto.movimientos_tesoreria"),
             _uno(esc.db, "SELECT count(*) FROM gapto.hecho_efectos"))
    esc.generado_por(esc.poliza)
    esc.db.execute("UPDATE gapto.efecto_cuentas SET cuenta_id = %s WHERE efecto_id = %s",
                   (esc.corriente, esc.efecto))
    despues = (esc.saldo(esc.poliza),
               _uno(esc.db, "SELECT count(*) FROM gapto.movimientos_tesoreria"),
               _uno(esc.db, "SELECT count(*) FROM gapto.hecho_efectos"))
    assert antes == despues


def test_0286_caso_real_comision_poliza_deuda_cero(esc: Escenario) -> None:
    """T14: límite 30.000, dispuesto 0, comisión 9,90 pagada desde CC1. El gasto
    existe, la deuda de la póliza sigue siendo 0 y la salida real es de CC1."""
    esc.db.execute("UPDATE gapto.cuentas SET saldo_apertura = 0, fecha_inicio_ledger = CURRENT_DATE "
                   "WHERE id IN (%s, %s)", (esc.poliza, esc.corriente))
    esc.generado_por(esc.poliza)
    esc.db.execute(
        "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
        "confirmado_at, clase_movimiento, estado) VALUES (%s, %s, CURRENT_DATE, '-9.9000', "
        "CURRENT_TIMESTAMP, 'OPERACION', 'ACTIVO')",
        (str(uuid.uuid4()), esc.corriente))
    assert float(esc.saldo(esc.poliza)) == 0.0
    assert float(esc.saldo(esc.corriente)) == -9.9
    assert float(_uno(esc.db, "SELECT limite_credito FROM gapto.cuentas WHERE id = %s",
                      (esc.poliza,))) == 30000.0


def test_0286_caso_real_interes_pagado_desde_otra_cuenta(esc: Escenario) -> None:
    """T15: dispuesto 10.000, interés 35 pagado desde CC1; la deuda sigue en
    10.000 porque hecho_cuentas no mueve nada."""
    esc.db.execute("UPDATE gapto.cuentas SET saldo_apertura = '-10000.0000', "
                   "fecha_inicio_ledger = CURRENT_DATE WHERE id = %s", (esc.poliza,))
    esc.db.execute("UPDATE gapto.cuentas SET saldo_apertura = 0, "
                   "fecha_inicio_ledger = CURRENT_DATE WHERE id = %s", (esc.corriente,))
    hecho, efecto = esc.hecho_gasto("35.0000")
    esc.generado_por(esc.poliza, efecto=efecto, hecho=hecho)
    esc.db.execute(
        "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
        "confirmado_at, clase_movimiento, estado) VALUES (%s, %s, CURRENT_DATE, '-35.0000', "
        "CURRENT_TIMESTAMP, 'OPERACION', 'ACTIVO')",
        (str(uuid.uuid4()), esc.corriente))
    assert float(esc.saldo(esc.poliza)) == -10000.0


def test_0286_caso_real_interes_financiado_por_la_poliza(esc: Escenario) -> None:
    """T16: el mismo interés financiado con la póliza lleva la deuda a 10.035,
    y lo hace el movimiento, no la relación funcional."""
    esc.db.execute("UPDATE gapto.cuentas SET saldo_apertura = '-10000.0000', "
                   "fecha_inicio_ledger = CURRENT_DATE WHERE id = %s", (esc.poliza,))
    hecho, efecto = esc.hecho_gasto("35.0000")
    esc.generado_por(esc.poliza, efecto=efecto, hecho=hecho)
    esc.db.execute(
        "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
        "confirmado_at, clase_movimiento, estado) VALUES (%s, %s, CURRENT_DATE, '-35.0000', "
        "CURRENT_TIMESTAMP, 'OPERACION', 'ACTIVO')",
        (str(uuid.uuid4()), esc.poliza))
    assert float(esc.saldo(esc.poliza)) == -10035.0


# ------------------------------------------------------------
# T7, T10. Aislamiento por tenant
# ------------------------------------------------------------

def test_0286_cuenta_de_otro_owner_se_rechaza(esc: Escenario) -> None:
    """R11: lo impide la FK compuesta, no la policy. Se comprueba con el
    contexto de tenant puesto y con FORCE RLS levantado dentro de la propia
    transacción, para simular BYPASSRLS."""
    _tenant(esc.db, OWNER_B)
    esc.usuario(OWNER_B)
    ajena = esc.cuenta("CORRIENTE", "ACTIVO", None, owner=OWNER_B)
    _tenant(esc.db, OWNER_A)
    esc.db.execute("ALTER TABLE gapto.efecto_cuentas NO FORCE ROW LEVEL SECURITY")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(ajena)


def test_0286_owner_declarado_distinto_del_hecho_se_rechaza(esc: Escenario) -> None:
    _tenant(esc.db, OWNER_B)
    esc.usuario(OWNER_B)
    _tenant(esc.db, OWNER_A)
    esc.db.execute("ALTER TABLE gapto.efecto_cuentas NO FORCE ROW LEVEL SECURITY")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with esc.db.transaction(force_rollback=True):
            esc.generado_por(esc.poliza, owner=OWNER_B)


def test_0286_rls_aisla_a_otro_tenant(esc: Escenario) -> None:
    esc.generado_por(esc.poliza)
    _tenant(esc.db, OWNER_B)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.efecto_cuentas") == 0
    _tenant(esc.db, OWNER_A)
    assert _uno(esc.db, "SELECT count(*) FROM gapto.efecto_cuentas") == 1


def test_0286_rls_enable_y_force(db: psycopg.Connection) -> None:
    assert db.execute("""
        SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_catalog.pg_class c
         WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass""").fetchone() == (True, True)


# ------------------------------------------------------------
# GRANTs: bucket A de D-093
# ------------------------------------------------------------

def test_0286_grants_bucket_a(db: psycopg.Connection) -> None:
    """SELECT + INSERT + UPDATE para runtime, sin DELETE, igual que el resto de
    los vínculos del hecho; SELECT para backup y nada más."""
    privs = {
        (r[0], r[1])
        for r in db.execute("""
            SELECT e.grantee::pg_catalog.regrole::text, e.privilege_type
              FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
             WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass
               AND e.grantee::pg_catalog.regrole::text IN ('gapto_runtime', 'gapto_backup')
        """).fetchall()
    }
    assert privs == {
        ("gapto_runtime", "SELECT"), ("gapto_runtime", "INSERT"), ("gapto_runtime", "UPDATE"),
        ("gapto_backup", "SELECT"),
    }


def test_0286_contrato_fisico(db: psycopg.Connection) -> None:
    obtenido = {
        "tablas": _uno(db, "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='gapto'"),
        "policies": _uno(db, "SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'"),
        "foreign_keys": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint k
              JOIN pg_catalog.pg_class t ON t.oid = k.conrelid
             WHERE t.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f'"""),
        "unique_constraints": _uno(db, """
            SELECT count(*) FROM pg_catalog.pg_constraint k
              JOIN pg_catalog.pg_class t ON t.oid = k.conrelid
             WHERE t.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'u'"""),
    }
    assert obtenido == HUELLAS_0286


def test_0286_no_cambia_funciones_ni_triggers(db: psycopg.Connection) -> None:
    """0286 es puramente declarativa: el recuento de 0285 no se mueve."""
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_proc p "
                    "WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace") == 25
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal""") == 48
