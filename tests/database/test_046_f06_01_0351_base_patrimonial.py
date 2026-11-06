# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_046_f06_01_0351_base_patrimonial.py
# Ruta: tests/database/test_046_f06_01_0351_base_patrimonial.py
# Descripción: Verifica F06-01 B0 / migration 0351 (F06-D002; consulta de
#              diseño de B0 §2 y §7; dictamen doble PB0-02, 05, 06, 07, 09, 10).
#
#              HUELLA CURRENT. Las ocho huellas D-111 y sus recuentos de la base
#              bajo prueba son exactamente HUELLAS_D111_POR_HEAD['0351'] del
#              runner de clean-room.
#
#              CONTRATO. Columnas nuevas con su tipo; los cinco CHECK con su
#              definición exacta y validados; la sustituida, ausente; los dos
#              arquetipos con su UUIDv5; diez tipos_hecho.
#
#              NEGATIVOS (L5-5 ampliado). Cada caso en un SAVEPOINT de una
#              transacción que SIEMPRE termina en ROLLBACK, con datos
#              sintéticos creados por el superusuario del laboratorio:
#              VALOR_ACTIVO sin causa, GASTO con causa, causa fuera del dominio;
#              repercutible sin modo, FIJO sin porcentaje, POR_FACTURA CON
#              porcentaje (ahora rechazado), POR_FACTURA sin actor, modo fuera
#              del dominio, no repercutible con modo, con actor, con porcentaje
#              y con ambos (AJ-B0-02); habitación 0, negativa, NULL de tipo
#              ajeno y habitación en contrato no HABITACION. Cada rechazo exige
#              SQLSTATE 23514 y el nombre de la constraint. Los controles
#              (combinaciones válidas) se admiten.
#
#              PRIVILEGIOS. DELETE denegado (42501) a gapto_runtime en cada una
#              de las siete tablas de PB0-09 opción B, por separado; las doce de
#              DEVUELTO_POR_0320 lo conservan.
#
#              REAPLICAR. El cuerpo de 0351 sobre una base que ya la tiene falla
#              en su precheck (patrón de 0350), dentro de un SAVEPOINT revertido.
#
#              PRECHECK DE DATOS (N1-E; dictamen de reconsulta RB0-10). El
#              bloque $precheck_datos_0351$ se extrae LITERAL del fichero (con
#              el SET ROLE gapto_owner y el NO FORCE que lo preceden) y se
#              ejecuta en un SAVEPOINT revertido sobre datos sintéticos que lo
#              disparan: un VALOR_ACTIVO previo (Q2) y un servicio no
#              repercutible con actor, sembrado tras retirar en la misma
#              transacción revertida el CHECK que hoy lo impide (Q3). Cada
#              negativo exige el mensaje de SU guarda; el control, sin datos
#              que lo disparen, lo atraviesa. Sustituye a los escenarios Q2/Q3
#              del arnés como cobertura permanente.
#
#              DISCRIMINACIÓN CONTRA 0350 (WM 12C.2). Sobre head 0350 fallan la
#              huella, el contrato, los negativos que dependen de columnas nuevas
#              y la denegación de DELETE.
# Versión: 0.3.0  -- F06-01 B0 N1 (LOTE9 C2; dictamen de reconsulta RB0-10,
#                   N1-E): negativos permanentes de los prechecks de datos Q2
#                   (VALOR_ACTIVO previo) y Q3 (residuo de repercusión) y su
#                   control. Q3 retira el CHECK como gapto_owner (en Neon el
#                   rol de conexión no es superusuario ni propietario).
# Versión: 0.2.0  -- PAQUETE B0 v0.2 (no candidato hasta dictamen).
# ============================================================
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0351_f06_01_b0_base_patrimonial.sql"

SIETE_SIN_DELETE = (
    "tercero_roles", "tercero_direcciones", "tercero_clasificaciones",
    "clasificaciones_tercero", "contrato_servicios", "propiedad_servicios",
    "entidad_relaciones",
)
DEVUELTO_POR_0320 = (
    "hecho_efectos", "efecto_atribuciones", "hecho_aportaciones_pago",
    "hecho_movimientos_tesoreria", "inversion_asignaciones_efecto",
    "efecto_cuentas", "hecho_entidades", "hecho_participantes",
    "hecho_terceros", "hecho_magnitudes", "hecho_relaciones", "transferencias",
)

CHECKS_0351 = {
    ("hecho_efectos", "ck_hecho_efectos__causa_valor_activo_dominio"):
        "CHECK (((causa_valor_activo IS NULL) OR ((causa_valor_activo)::text = ANY "
        "((ARRAY['ADQUISICION'::character varying, 'TRANSFORMACION_CAPITALIZABLE'::character varying, "
        "'BAJA_TOTAL'::character varying, 'BAJA_PARCIAL'::character varying, "
        "'REDUCCION_ESTRUCTURAL'::character varying])::text[]))))",
    ("hecho_efectos", "ck_hecho_efectos__causa_solo_valor_activo"):
        "CHECK ((((tipo_efecto)::text = 'VALOR_ACTIVO'::text) = (causa_valor_activo IS NOT NULL)))",
    ("contratos", "ck_contratos__habitacion"):
        "CHECK (((habitacion IS NULL) OR ((habitacion >= 1) AND ((tipo_contrato)::text = 'HABITACION'::text))))",
    ("contrato_servicios", "ck_contrato_servicios__modo_reparto_dominio"):
        "CHECK (((modo_reparto IS NULL) OR ((modo_reparto)::text = ANY "
        "((ARRAY['FIJO'::character varying, 'POR_FACTURA'::character varying])::text[]))))",
    ("contrato_servicios", "ck_contrato_servicios__repercusion_coherente"):
        "CHECK ((((NOT repercutible) AND (modo_reparto IS NULL) AND (actor_repercusion_id IS NULL) "
        "AND (porcentaje_repercutible IS NULL)) OR (repercutible AND (modo_reparto IS NOT NULL) "
        "AND (actor_repercusion_id IS NOT NULL) AND ((((modo_reparto)::text = 'FIJO'::text) "
        "AND (porcentaje_repercutible IS NOT NULL)) OR (((modo_reparto)::text = 'POR_FACTURA'::text) "
        "AND (porcentaje_repercutible IS NULL))))))",
}

ARQUETIPOS_0351 = {
    "ADQUISICION_PATRIMONIAL": ("1da0639b-825a-5803-8c50-db1b7543c751", "Adquisicion patrimonial"),
    "MEJORA_PATRIMONIAL": ("d63b1e52-c3c5-5df3-80ff-346288d86c7d", "Mejora patrimonial"),
}


def _runner():
    spec = importlib.util.spec_from_file_location(
        "run_clean_room", RAIZ / "scripts" / "postgres" / "run_clean_room.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _uno(db: psycopg.Connection, sql: str, params: tuple = ()):
    return db.execute(sql, params).fetchone()[0]


def cuerpo_0351() -> str:
    """Cuerpo de 0351 sin su control transaccional, extraído del fichero."""
    lineas = MIGRATION.read_bytes().decode("utf-8").split("\n")
    inicio = [i for i, linea in enumerate(lineas) if linea == "BEGIN;"]
    fin = [i for i, linea in enumerate(lineas) if linea == "COMMIT;"]
    assert len(inicio) == 1 and len(fin) == 1 and inicio[0] < fin[0]
    return "\n".join(lineas[inicio[0] + 1:fin[0]])


# ------------------------------------------------------------------ huella CURRENT
def test_0351_huella_d111_current(db: psycopg.Connection) -> None:
    referencia = _runner().HUELLAS_D111_POR_HEAD["0351"]
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    observadas = dict(zip([d.name for d in cursor.description], cursor.fetchone()))
    assert {k: observadas[k] for k in referencia} == referencia


def test_0351_contrato_declarado_en_el_runner() -> None:
    runner = _runner()
    assert runner.CONTRATOS_POR_HEAD["0351"] == {**runner.CONTRATOS_POR_HEAD["0350"], "runtime_delete": 41}
    assert "test_046_f06_01_0351_base_patrimonial" in runner.TESTS_EXIGIDOS_POR_HEAD["0351"]
    assert "0351" in runner.HEADS_QUE_EXIGEN_REFERENCIA_D111


# ------------------------------------------------------------------ contrato
def test_0351_columnas_nuevas(db: psycopg.Connection) -> None:
    filas = db.execute("""
        SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,
               pg_catalog.pg_get_expr(d.adbin, d.adrelid)
          FROM pg_catalog.pg_attribute a
          JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
          LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
         WHERE c.relnamespace = 'gapto'::regnamespace AND a.attnum > 0 AND NOT a.attisdropped
           AND a.attname IN ('causa_valor_activo', 'habitacion', 'modo_reparto')
         ORDER BY 1, 2""").fetchall()
    assert filas == [
        ("contrato_servicios", "modo_reparto", "character varying(16)", False, None),
        ("contratos", "habitacion", "smallint", False, None),
        ("hecho_efectos", "causa_valor_activo", "character varying(32)", False, None),
    ]


def test_0351_checks_exactos_y_validados(db: psycopg.Connection) -> None:
    filas = db.execute("""
        SELECT c.relname, k.conname, pg_catalog.pg_get_constraintdef(k.oid), k.convalidated, k.condeferrable
          FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
         WHERE c.relnamespace = 'gapto'::regnamespace AND k.contype = 'c'
           AND c.relname IN ('hecho_efectos', 'contratos', 'contrato_servicios')
           AND k.conname IN (%s, %s, %s, %s, %s, 'ck_contrato_servicios__repercusion_exige_datos')""",
        tuple(n for _, n in CHECKS_0351)).fetchall()
    obtenidos = {(t, n): (d, v, f) for t, n, d, v, f in filas}
    assert obtenidos == {clave: (definicion, True, False) for clave, definicion in CHECKS_0351.items()}


def test_0351_arquetipos_patrimoniales(db: psycopg.Connection) -> None:
    filas = db.execute(
        "SELECT codigo, id::text, nombre, enabled FROM gapto.tipos_hecho WHERE codigo = ANY(%s) ORDER BY codigo",
        (sorted(ARQUETIPOS_0351),)).fetchall()
    assert filas == [(c, i, n, True) for c, (i, n) in sorted(ARQUETIPOS_0351.items())]
    for codigo, (ident, _) in ARQUETIPOS_0351.items():
        assert str(uuid.uuid5(uuid.NAMESPACE_URL, f"gapto2027:tipos_hecho:{codigo}")) == ident
    assert _uno(db, "SELECT count(*) FROM gapto.tipos_hecho") == 10


# ------------------------------------------------------------------ privilegios
@pytest.mark.parametrize("tabla", SIETE_SIN_DELETE)
def test_0351_delete_denegado_a_runtime(db: psycopg.Connection, tabla: str) -> None:
    owner = str(uuid.uuid4())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction(force_rollback=True):
            db.execute("SET LOCAL ROLE gapto_runtime")
            db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
            db.execute(f"DELETE FROM gapto.{tabla} WHERE false")


@pytest.mark.parametrize("tabla", DEVUELTO_POR_0320)
def test_0351_devuelto_por_0320_conserva_delete(db: psycopg.Connection, tabla: str) -> None:
    owner = str(uuid.uuid4())
    with db.transaction(force_rollback=True):
        db.execute("SET LOCAL ROLE gapto_runtime")
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))
        db.execute(f"DELETE FROM gapto.{tabla} WHERE false")


def test_0351_acl_completo_de_las_siete(db: psycopg.Connection) -> None:
    filas = db.execute("""
        SELECT c.relname, string_agg(acl.privilege_type, ',' ORDER BY acl.privilege_type)
          FROM pg_catalog.pg_class c
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE c.relnamespace = 'gapto'::regnamespace AND c.relname = ANY(%s) AND r.rolname = 'gapto_runtime'
         GROUP BY 1""", (list(SIETE_SIN_DELETE),)).fetchall()
    assert dict(filas) == {t: "INSERT,SELECT,UPDATE" for t in SIETE_SIN_DELETE}


# ------------------------------------------------------------------ negativos
@pytest.fixture
def escenario(db: psycopg.Connection):
    """Datos sintéticos en una transacción que siempre se revierte."""
    owner, actor = uuid.uuid4(), uuid.uuid4()
    ids = {k: uuid.uuid4() for k in ("prop", "serv", "con_viv", "con_hab", "hecho")}
    with db.transaction(force_rollback=True):
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0351')",
                   (owner, f"{owner}@example.invalid"))
        db.execute("INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)", (actor, owner))
        for k, tipo in (("prop", "PROPIEDAD"), ("serv", "SERVICIO"), ("con_viv", "CONTRATO"), ("con_hab", "CONTRATO")):
            db.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, %s, %s, %s)",
                       (ids[k], owner, tipo, f"0351 {k}"))
        db.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')", (ids["prop"],))
        db.execute("INSERT INTO gapto.servicios (entidad_id, tipo_servicio) VALUES (%s, 'SUMINISTRO')", (ids["serv"],))
        for k, tipo in (("con_viv", "ALQUILER_VIVIENDA"), ("con_hab", "HABITACION")):
            db.execute("INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, tipo_contrato) "
                       "VALUES (%s, %s, %s)", (ids[k], ids["prop"], tipo))
        tipo_gasto = _uno(db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        db.execute("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                   "presupuestable, estado_localizacion, importe_total, concepto) "
                   "VALUES (%s, %s, %s, current_date, 'EUR', false, 'NO_APLICA', 100, '0351')",
                   (ids["hecho"], owner, tipo_gasto))
        yield db, ids, actor


def _intentar(db: psycopg.Connection, sql: str, params: tuple) -> str | None:
    """None si se admite; el nombre de la constraint si 23514. Siempre revierte el caso."""
    try:
        with db.transaction(force_rollback=True):
            db.execute(sql, params)
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except psycopg.errors.CheckViolation as error:
        return error.diag.constraint_name
    return None


EFECTO = ("INSERT INTO gapto.hecho_efectos (hecho_id, tipo_efecto, importe_delta, estado_atribucion, "
          "causa_valor_activo) VALUES (%s, %s, 100, 'NO_DISPONIBLE', %s)")

CASOS_EFECTO = [
    ("VALOR_ACTIVO sin causa", "VALOR_ACTIVO", None, "ck_hecho_efectos__causa_solo_valor_activo"),
    ("GASTO con causa", "GASTO", "ADQUISICION", "ck_hecho_efectos__causa_solo_valor_activo"),
    ("INVERSION con causa", "INVERSION", "BAJA_TOTAL", "ck_hecho_efectos__causa_solo_valor_activo"),
    ("causa fuera del dominio", "VALOR_ACTIVO", "TASACION", "ck_hecho_efectos__causa_valor_activo_dominio"),
    ("causa vacia", "VALOR_ACTIVO", "", "ck_hecho_efectos__causa_valor_activo_dominio"),
    ("control VALOR_ACTIVO ADQUISICION", "VALOR_ACTIVO", "ADQUISICION", None),
    ("control VALOR_ACTIVO REDUCCION_ESTRUCTURAL", "VALOR_ACTIVO", "REDUCCION_ESTRUCTURAL", None),
    ("control GASTO sin causa", "GASTO", None, None),
]


@pytest.mark.parametrize("nombre,tipo,causa,esperado", CASOS_EFECTO, ids=[c[0] for c in CASOS_EFECTO])
def test_0351_causa_valor_activo(escenario, nombre, tipo, causa, esperado) -> None:
    db, ids, _ = escenario
    assert _intentar(db, EFECTO, (ids["hecho"], tipo, causa)) == esperado


SERVICIO = ("INSERT INTO gapto.contrato_servicios (contrato_entidad_id, servicio_entidad_id, repercutible, "
            "actor_repercusion_id, porcentaje_repercutible, modo_reparto, vigente_desde) "
            "VALUES (%s, %s, %s, %s, %s, %s, current_date)")
COHERENTE = "ck_contrato_servicios__repercusion_coherente"

# (nombre, repercutible, con actor, porcentaje, modo, constraint esperada o None)
CASOS_SERVICIO = [
    ("repercutible sin modo", True, True, 50, None, COHERENTE),
    ("FIJO sin porcentaje", True, True, None, "FIJO", COHERENTE),
    ("FIJO sin actor", True, False, 50, "FIJO", COHERENTE),
    ("POR_FACTURA con porcentaje", True, True, 50, "POR_FACTURA", COHERENTE),
    ("POR_FACTURA con porcentaje cero", True, True, 0, "POR_FACTURA", COHERENTE),
    ("POR_FACTURA sin actor", True, False, None, "POR_FACTURA", COHERENTE),
    ("modo fuera del dominio", True, True, 50, "VARIABLE", "ck_contrato_servicios__modo_reparto_dominio"),
    ("no repercutible con modo", False, False, None, "FIJO", COHERENTE),
    ("no repercutible con actor", False, True, None, None, COHERENTE),
    ("no repercutible con porcentaje", False, False, 50, None, COHERENTE),
    ("no repercutible con actor y porcentaje", False, True, 50, None, COHERENTE),
    ("control FIJO completo", True, True, 50, "FIJO", None),
    ("control POR_FACTURA sin porcentaje", True, True, None, "POR_FACTURA", None),
    ("control no repercutible vacio", False, False, None, None, None),
]


@pytest.mark.parametrize("nombre,repercutible,con_actor,porcentaje,modo,esperado", CASOS_SERVICIO,
                         ids=[c[0] for c in CASOS_SERVICIO])
def test_0351_modo_reparto(escenario, nombre, repercutible, con_actor, porcentaje, modo, esperado) -> None:
    db, ids, actor = escenario
    params = (ids["con_viv"], ids["serv"], repercutible, actor if con_actor else None, porcentaje, modo)
    assert _intentar(db, SERVICIO, params) == esperado


CASOS_HABITACION = [
    ("habitacion 0", "con_hab", 0, "ck_contratos__habitacion"),
    ("habitacion negativa", "con_hab", -1, "ck_contratos__habitacion"),
    ("habitacion en ALQUILER_VIVIENDA", "con_viv", 2, "ck_contratos__habitacion"),
    ("control habitacion 2 en HABITACION", "con_hab", 2, None),
    ("control NULL en ALQUILER_VIVIENDA", "con_viv", None, None),
]


@pytest.mark.parametrize("nombre,contrato,valor,esperado", CASOS_HABITACION, ids=[c[0] for c in CASOS_HABITACION])
def test_0351_habitacion(escenario, nombre, contrato, valor, esperado) -> None:
    db, ids, _ = escenario
    assert _intentar(db, "UPDATE gapto.contratos SET habitacion = %s WHERE entidad_id = %s",
                     (valor, ids[contrato])) == esperado


# ------------------------------------------------------------------ reaplicar
def test_0351_reaplicar_rechazado_por_precheck(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="0351 ya esta aplicada"):
        with db.transaction(force_rollback=True):
            db.execute(cuerpo_0351())


# ------------------------------------------------------------------ precheck de datos (N1-E)
def precheck_datos_0351() -> str:
    """Precheck de datos de 0351, literal del fichero: desde el SET ROLE
    gapto_owner que lo precede (con el NO FORCE de las dos tablas contadas)
    hasta el cierre de su bloque DO."""
    cuerpo = cuerpo_0351()
    cierre = "$precheck_datos_0351$;"
    assert cuerpo.count(cierre) == 1
    inicio = cuerpo.index("SET ROLE gapto_owner;")
    fin = cuerpo.index(cierre) + len(cierre)
    assert inicio < cuerpo.index("DO $precheck_datos_0351$") < fin
    return cuerpo[inicio:fin]


def _recuento(db: psycopg.Connection, sql: str) -> int:
    return _uno(db, sql)


VALOR_ACTIVO_PREVIO = "SELECT count(*) FROM gapto.hecho_efectos WHERE tipo_efecto = 'VALOR_ACTIVO'"
RESIDUO_REPERCUSION = ("SELECT count(*) FROM gapto.contrato_servicios WHERE NOT repercutible "
                       "AND (actor_repercusion_id IS NOT NULL OR porcentaje_repercutible IS NOT NULL)")


def test_0351_precheck_datos_valor_activo_previo(escenario) -> None:
    """Q2: un VALOR_ACTIVO preexistente aborta el precheck con su mensaje."""
    db, ids, _ = escenario
    with pytest.raises(psycopg.errors.RaiseException) as excinfo:
        with db.transaction(force_rollback=True):
            db.execute(EFECTO, (ids["hecho"], "VALOR_ACTIVO", "ADQUISICION"))
            # Valida ya los triggers diferidos: con eventos pendientes el ALTER
            # TABLE ... NO FORCE del precheck no se podria ejecutar.
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
            n = _recuento(db, VALOR_ACTIVO_PREVIO)
            db.execute(precheck_datos_0351())
    assert n >= 1
    assert f" {n} efectos VALOR_ACTIVO preexistentes sin causa;" in str(excinfo.value)


def test_0351_precheck_datos_residuo_repercusion(escenario) -> None:
    """Q3: un servicio no repercutible con actor aborta el precheck con su
    mensaje. El CHECK de 0351 que hoy lo impide se retira solo dentro de la
    transacción revertida, para reproducir el estado 0350 que el precheck vigila."""
    db, ids, actor = escenario
    with pytest.raises(psycopg.errors.RaiseException) as excinfo:
        with db.transaction(force_rollback=True):
            # El CHECK es de gapto_owner: sin superusuario (Neon, Supabase,
            # D-189) solo su propietario puede retirarlo.
            db.execute("SET LOCAL ROLE gapto_owner")
            db.execute("ALTER TABLE gapto.contrato_servicios DROP CONSTRAINT ck_contrato_servicios__repercusion_coherente")
            db.execute("RESET ROLE")
            db.execute(SERVICIO, (ids["con_viv"], ids["serv"], False, actor, None, None))
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
            n = _recuento(db, RESIDUO_REPERCUSION)
            db.execute(precheck_datos_0351())
    assert n >= 1
    assert f" {n} servicios no repercutibles con actor o porcentaje;" in str(excinfo.value)


def test_0351_precheck_datos_control_sin_disparadores(escenario) -> None:
    """Control: sin VALOR_ACTIVO ni residuos, el precheck de datos se atraviesa."""
    db, _, _ = escenario
    assert (_recuento(db, VALOR_ACTIVO_PREVIO), _recuento(db, RESIDUO_REPERCUSION)) == (0, 0)
    with db.transaction(force_rollback=True):
        db.execute(precheck_datos_0351())
