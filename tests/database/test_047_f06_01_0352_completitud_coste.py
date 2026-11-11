# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_047_f06_01_0352_completitud_coste.py
# Ruta: tests/database/test_047_f06_01_0352_completitud_coste.py
# Descripción: Verifica la migration 0352 (F06-01 B2-B3; declaraciones de
#              completitud del coste con el conjunto que las respalda; dictamen
#              de diseño 0352 del 2026-11-07, AJ-0352-01..12, política I-B).
#
#              HUELLA CURRENT. Las ocho huellas D-111 y sus recuentos son
#              HUELLAS_D111_POR_HEAD['0352'] del runner; DESVIACIÓN frente a
#              0351: solo cambian h1, h2 y los recuentos (columnas 781→787,
#              constraints 649→652); h3..h8 idénticas a 0351.
#
#              CONTRATO. Seis columnas nullable con su tipo; tres CHECK con su
#              definición exacta y validados; sin defaults; ninguna propiedad
#              existente queda declarada; runner con 0352 declarado y 0351
#              conservado (R-0352-14).
#
#              NEGATIVOS N1–N13 y POSITIVOS P1–P3 (consulta 0352, P0352-02).
#              Cada caso en una transacción que SIEMPRE termina en ROLLBACK,
#              con datos sintéticos creados como gapto_owner con la GUC de
#              tenant. N8 y N13 son los discriminantes del hueco NULL de la
#              version descartada del diseno (mutante obligatorio M-CK-01).
#
#              REAPLICAR. El precheck de 0352 rechaza volver a aplicarla.
#
#              DISCRIMINACIÓN CONTRA 0351 (WM 12C.2). Sobre head 0351 fallan la
#              huella, el contrato y todos los negativos (no existen las
#              columnas): el módulo solo pasa con 0352 aplicada.
# Versión: 0.1.0  -- F03 · N1 de 0352 (mandato v1.4, lote 22; AJ-0352-06). Procede del prototipo
#                   del lote 18 (Parte C), revisado y reejecutado en este N1. Nuevo:
#                   test_0352_force_rls_restaurado (el mutante M-DDL-01 sobrevivia sin el).
# ============================================================
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0352_f06_01_b2_completitud_coste.sql"

COLUMNAS = {
    "coste_adquisicion_declarado_completo": "boolean",
    "coste_adquisicion_declarado_en": "date",
    "coste_adquisicion_conjunto_declarado": "jsonb",
    "mejoras_declaradas_completas": "boolean",
    "mejoras_declaradas_en": "date",
    "mejoras_conjunto_declarado": "jsonb",
}
ADQ = "ck_propiedades__coste_adquisicion_declaracion"
MEJ = "ck_propiedades__mejoras_declaracion"
CORTE = "ck_propiedades__coste_adquisicion_corte_no_anterior"
CHECKS = {
    CORTE: "CHECK (((coste_adquisicion_declarado_en IS NULL) OR (fecha_adquisicion IS NULL) OR "
           "(coste_adquisicion_declarado_en >= fecha_adquisicion)))",
    ADQ: "CHECK ((((coste_adquisicion_declarado_completo IS NULL) AND (coste_adquisicion_declarado_en IS NULL) "
         "AND (coste_adquisicion_conjunto_declarado IS NULL)) OR ((coste_adquisicion_declarado_completo IS TRUE) "
         "AND (coste_adquisicion_declarado_en IS NOT NULL) AND (coste_adquisicion_conjunto_declarado IS NOT NULL) "
         "AND (jsonb_typeof(coste_adquisicion_conjunto_declarado) = 'array'::text))))",
    MEJ: "CHECK ((((mejoras_declaradas_completas IS NULL) AND (mejoras_declaradas_en IS NULL) "
         "AND (mejoras_conjunto_declarado IS NULL)) OR ((mejoras_declaradas_completas IS TRUE) "
         "AND (mejoras_declaradas_en IS NOT NULL) AND (mejoras_conjunto_declarado IS NOT NULL) "
         "AND (jsonb_typeof(mejoras_conjunto_declarado) = 'array'::text))))",
}
FA = dt.date(2025, 6, 1)
CONJUNTO = json.dumps([{"efecto_id": "00000000-0000-4000-8000-0000000000e1", "hecho_id":
                        "00000000-0000-4000-8000-0000000000d1", "importe": "1000.00",
                        "fecha": "2025-06-01", "causa": "ADQUISICION"}])


def _runner():
    spec = importlib.util.spec_from_file_location("rcr_047", RAIZ / "scripts" / "postgres" / "run_clean_room.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _uno(db: psycopg.Connection, sql: str, params: tuple = ()):
    return db.execute(sql, params).fetchone()[0]


def _huellas(db: psycopg.Connection) -> dict:
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    return dict(zip([d.name for d in cursor.description], cursor.fetchone()))


# ------------------------------------------------------------------ huella y desviación
def test_0352_huella_d111_current(db: psycopg.Connection) -> None:
    referencia = _runner().HUELLAS_D111_POR_HEAD["0352"]
    observadas = _huellas(db)
    assert {k: observadas[k] for k in referencia} == referencia


def test_0352_desviacion_frente_a_0351_solo_h1_h2_recuentos() -> None:
    huellas = _runner().HUELLAS_D111_POR_HEAD
    distintas = {k for k in huellas["0352"] if huellas["0352"][k] != huellas["0351"][k]}
    assert distintas == {"h1_columnas", "h2_constraints", "recuentos"}
    assert huellas["0351"]["recuentos"] == "781/649/287/82/58/28/1024/3"
    assert huellas["0352"]["recuentos"] == "787/652/287/82/58/28/1024/3"


def test_0352_runner_declara_0352_y_conserva_0351() -> None:
    runner = _runner()
    assert runner.CONTRATOS_POR_HEAD["0352"] == runner.CONTRATOS_POR_HEAD["0351"]
    assert runner.CONTRATOS_POR_HEAD["0351"] == {**runner.CONTRATOS_POR_HEAD["0350"], "runtime_delete": 41}
    assert "test_047_f06_01_0352_completitud_coste" in runner.TESTS_EXIGIDOS_POR_HEAD["0352"]
    assert "test_046_f06_01_0351_base_patrimonial" in runner.TESTS_EXIGIDOS_POR_HEAD["0352"]
    assert "test_047_f06_01_0352_completitud_coste" not in runner.TESTS_EXIGIDOS_POR_HEAD["0351"]
    assert {"0351", "0352"} <= set(runner.HEADS_QUE_EXIGEN_REFERENCIA_D111)


# ------------------------------------------------------------------ contrato
def test_0352_columnas_nuevas(db: psycopg.Connection) -> None:
    filas = db.execute(
        "SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull, a.atthasdef "
        "FROM pg_catalog.pg_attribute a WHERE a.attrelid = 'gapto.propiedades'::regclass AND a.attnum > 0 "
        "AND NOT a.attisdropped AND a.attname = ANY(%s)", (list(COLUMNAS),)).fetchall()
    assert {f[0]: f[1] for f in filas} == COLUMNAS
    assert all(not f[2] and not f[3] for f in filas), "nullable y sin default (P0352-01)"
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid = 'gapto.propiedades'::regclass "
                    "AND attnum > 0 AND NOT attisdropped") == 24


def test_0352_checks_exactos_y_validados(db: psycopg.Connection) -> None:
    filas = db.execute(
        "SELECT conname, pg_catalog.pg_get_constraintdef(oid), convalidated FROM pg_catalog.pg_constraint "
        "WHERE conrelid = 'gapto.propiedades'::regclass AND contype = 'c' AND conname = ANY(%s)",
        (list(CHECKS),)).fetchall()
    assert {f[0]: f[1] for f in filas} == CHECKS
    assert all(f[2] for f in filas)


def test_0352_ninguna_propiedad_declarada_por_la_migration(db: psycopg.Connection) -> None:
    # No rellena (P0352-09): en la base de la suite de tests/database (replay; ningún test de este
    # directorio confirma declaraciones) ninguna de las seis columnas tiene valor.
    assert _uno(db, "SELECT count(*) FROM gapto.propiedades WHERE num_nonnulls("
                    + ", ".join(COLUMNAS) + ") > 0") == 0


def test_0352_force_rls_restaurado(db: psycopg.Connection) -> None:
    """0352 levanta FORCE RLS de propiedades y lo restaura en la misma transaccion: tras ella, propiedades sigue con
    RLS y FORCE y el total de tablas con FORCE es 75 (como en 0351). Las huellas D-111 no miran relforcerowsecurity:
    sin este test, una 0352 que no restaurase FORCE solo la detectaria su propio postcheck (mutante M-DDL-01)."""
    fila = db.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_catalog.pg_class "
                      "WHERE oid = 'gapto.propiedades'::regclass").fetchone()
    assert fila == (True, True)
    total = db.execute("SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace = 'gapto'::regnamespace "
                       "AND relkind = 'r' AND relrowsecurity AND relforcerowsecurity").fetchone()[0]
    assert total == 75


def test_0352_reaplicar_rechazado_por_precheck(db: psycopg.Connection) -> None:
    texto = MIGRATION.read_bytes().decode("utf-8")
    lineas = texto.split("\n")
    inicio = lineas.index("BEGIN;")
    fin = lineas.index("COMMIT;")
    cuerpo = "\n".join(lineas[inicio + 1:fin])
    with pytest.raises(psycopg.errors.RaiseException) as error:
        with db.transaction(force_rollback=True):
            db.execute(cuerpo)
    assert "0352 ya esta aplicada" in str(error.value)


# ------------------------------------------------------------------ negativos y positivos
@pytest.fixture()
def escenario(db: psycopg.Connection):
    owner, prop = uuid.uuid4(), uuid.uuid4()
    with db.transaction(force_rollback=True):
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        db.execute("SET LOCAL ROLE gapto_owner")
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0352')",
                   (owner, f"{owner}@example.invalid"))
        db.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'PROPIEDAD', '0352 prueba')", (prop, owner))
        db.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad, fecha_adquisicion) "
                   "VALUES (%s, 'VIVIENDA', %s)", (prop, FA))
        yield db, prop


def _intentar(db: psycopg.Connection, sentencias: list[tuple[str, tuple]]) -> str | None:
    """None si se admite; el nombre de la constraint si 23514. Siempre revierte el caso."""
    try:
        with db.transaction(force_rollback=True):
            for sql, params in sentencias:
                db.execute(sql, params)
    except psycopg.errors.CheckViolation as error:
        return error.diag.constraint_name
    return None


def _adq(completo, en, conjunto):
    return ("UPDATE gapto.propiedades SET coste_adquisicion_declarado_completo = %s, "
            "coste_adquisicion_declarado_en = %s, coste_adquisicion_conjunto_declarado = %s::jsonb "
            "WHERE entidad_id = %s", (completo, en, conjunto))


def _mej(completo, en, conjunto):
    return ("UPDATE gapto.propiedades SET mejoras_declaradas_completas = %s, mejoras_declaradas_en = %s, "
            "mejoras_conjunto_declarado = %s::jsonb WHERE entidad_id = %s", (completo, en, conjunto))


ENERO = dt.date(2026, 1, 1)
# (id, [(constructor, args)], constraint esperada o None)
CASOS = [
    ("P1 adquisicion true, corte = adquisicion, array de 1", [(_adq, (True, FA, CONJUNTO))], None),
    ("P2 mejoras true, corte anterior a la adquisicion, []", [(_mej, (True, dt.date(1990, 1, 1), "[]"))], None),
    ("P3 retirar declaracion (terna a NULL)", [(_adq, (True, FA, CONJUNTO)), (_adq, (None, None, None))], None),
    ("N1 adquisicion false + fecha + conjunto", [(_adq, (False, ENERO, CONJUNTO))], ADQ),
    ("N2 adquisicion true sin fecha", [(_adq, (True, None, CONJUNTO))], ADQ),
    ("N3 adquisicion NULL + fecha", [(_adq, (None, ENERO, None))], ADQ),
    ("N4 mejoras false sin fecha", [(_mej, (False, None, None))], MEJ),
    ("N5 mejoras true sin fecha", [(_mej, (True, None, "[]"))], MEJ),
    ("N6 corte anterior a fecha_adquisicion", [(_adq, (True, FA - dt.timedelta(days=1), CONJUNTO))], CORTE),
    ("N8 adquisicion true + fecha sin conjunto (hueco NULL v1.1)", [(_adq, (True, FA, None))], ADQ),
    ("N9 adquisicion conjunto objeto", [(_adq, (True, FA, '{"efecto_id": "x"}'))], ADQ),
    ("N10 adquisicion conjunto jsonb null", [(_adq, (True, FA, "null"))], ADQ),
    ("N11 adquisicion conjunto sin declaracion", [(_adq, (None, None, CONJUNTO))], ADQ),
    ("N12 mejoras conjunto texto", [(_mej, (True, ENERO, '"[]"'))], MEJ),
    ("N13 mejoras true + fecha sin conjunto (hueco NULL v1.1)", [(_mej, (True, ENERO, None))], MEJ),
]


@pytest.mark.parametrize("nombre,pasos,esperado", CASOS, ids=[c[0].split(" ")[0] for c in CASOS])
def test_0352_negativos_y_positivos(escenario, nombre, pasos, esperado) -> None:
    db, prop = escenario
    sentencias = []
    for constructor, args in pasos:
        sql, params = constructor(*args)
        sentencias.append((sql, params + (prop,)))
    assert _intentar(db, sentencias) == esperado


def test_0352_n7_fecha_adquisicion_posterior_al_corte(escenario) -> None:
    """N7: la invariante física impide mover fecha_adquisicion después del corte declarado; la guarda
    funcional (código de dominio) es de C-PROP-02 (P0352-06), no de este CHECK."""
    db, prop = escenario
    sql, params = _adq(True, FA, CONJUNTO)
    assert _intentar(db, [(sql, params + (prop,)),
                          ("UPDATE gapto.propiedades SET fecha_adquisicion = %s WHERE entidad_id = %s",
                           (FA + dt.timedelta(days=1), prop))]) == CORTE
