# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_049_f06_01h_0354_garantias.py
# Ruta: tests/database/test_049_f06_01h_0354_garantias.py
# Descripción: Verifica la migration 0354 (MIG-HIP-GAR; T3-F06 bloque 2
#              F06-01H; mandato v1.1 §8.5; contrato v0.4 §10.1.7). Nombre
#              distinto del test_049 de laboratorio, que no se arrastra.
#
#              ESCENARIOS. Cada caso abre UNA transaccion que termina SIEMPRE
#              en ROLLBACK (nada persiste): fija la GUC de tenant, crea los
#              fixtures sinteticos bajo SET ROLE gapto_owner, vacia los
#              eventos diferidos de los fixtures (SET CONSTRAINTS ALL
#              IMMEDIATE y vuelta a DEFERRED, D-173), pasa a gapto_runtime
#              (RLS y FORCE activos) y ejecuta la operacion; las garantias
#              diferidas (G2) se evaluan con SET CONSTRAINTS ALL IMMEDIATE,
#              que adelanta la comprobacion del COMMIT.
#
#              DISCRIMINACION CONTRA 0353. Cada positivo (rechazo) espera el
#              mensaje con prefijo INV-0354-<Id>; sobre una base en 0353 la
#              misma operacion prospera y el positivo FALLA (se ejecuta el
#              modulo contra 0353 y se guarda la salida como evidencia). Los
#              negativos de ambito N-01..N-06 pasan en ambas.
#
#              HUELLA CURRENT. Las ocho huellas D-111 y los recuentos son
#              HUELLAS_D111_POR_HEAD['0354'] del runner; inventario cerrado de
#              seis funciones y siete triggers con su forma.
# Versión: 0.1.0  -- F06 T3-F06 bloque 2 F06-01H (mandato v1.1 §8.5).
# Versión: 0.2.0  -- F06 T3-F06 bloque 2 F06-01H, firma Q2 de Moises (ae67cf8c…)
#                    condicion (b): discriminante de la PO-04 de 0354 v0.1.1
#                    (aclexplode): con un privilegio indebido de gapto_runtime
#                    el postcheck falla; sin el, pasa (control).
# ============================================================
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
OWNER = "0354a000-0000-4000-8000-000000000001"
GDO = "26ee751e-aa9c-5c3b-a81c-7a28e5a5be34"          # GENERACION_DERECHO_OBLIGACION (0150)
GASTO = "b9c7573f-fa72-54a1-8b2d-b1c189f32533"        # GASTO (0150)
ESCRITURA = dt.date(2026, 1, 15)

FUNCIONES = {
    "fn_guard_cuota_inmutable_no_abierta",
    "fn_guard_prevision_cuota_no_reabrible",
    "fn_check_cuadro_hipoteca",
    "fn_validar_cuadro_hipoteca",
    "fn_guard_financiacion_ambito_hipoteca",
    "fn_guard_condiciones_version_historico",
}
TRIGGERS = {
    "trg_financiacion_cuotas__inmutable_no_abierta": ("financiacion_cuotas", False),
    "trg_previsiones__cuota_no_reabrible": ("previsiones", False),
    "trg_financiacion_cuotas__cuadro_hipoteca": ("financiacion_cuotas", True),
    "trg_financiaciones__cuadro_hipoteca": ("financiaciones", True),
    "trg_financiacion_condiciones_versiones__cuadro_hipoteca": ("financiacion_condiciones_versiones", True),
    "trg_financiaciones__ambito_hipoteca": ("financiaciones", False),
    "trg_financiacion_condiciones_versiones__historico": ("financiacion_condiciones_versiones", False),
}


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


# ------------------------------------------------------------------ escenario
class Esc:
    """Fixtures sinteticos de un owner dentro de una transaccion que se revierte."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0354') ON CONFLICT DO NOTHING",
                   (OWNER, f"{uuid.uuid4()}@example.invalid"))
        db.execute("SET LOCAL ROLE gapto_owner")

    def x(self, sql: str, params: tuple = ()) -> None:
        self.db.execute(sql, params)

    def hecho(self) -> str:
        hid = str(uuid.uuid4())
        self.x("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto, "
               "importe_total, moneda, estado_localizacion, presupuestable) "
               "VALUES (%s, %s, %s, %s, 'Hd sintetico', 300, 'EUR', 'NO_APLICA', false)",
               (hid, OWNER, GDO, ESCRITURA))
        return hid

    def prevision(self, estado: str = "ABIERTA", importe: str = "100") -> str:
        pid = str(uuid.uuid4())
        self.x("INSERT INTO gapto.previsiones (id, owner_user_id, concepto, tipo_hecho_id, fecha_esperada_desde, "
               "fecha_esperada_hasta, flujo_tesoreria_esperado, moneda, importe_esperado, presupuestable, estado, "
               "recalculo_automatico) VALUES (%s, %s, 'Cuota sintetica', %s, %s, %s, 'SALIDA', 'EUR', %s, false, %s, "
               "false)", (pid, OWNER, GASTO, ESCRITURA, ESCRITURA, importe, estado))
        return pid

    def financiacion(self, *, tipo: str = "HIPOTECA", capital: str | None = "300", m: bool = True,
                     cuotas: list[tuple[int, str | None]] | None = None, estados: list[str] | None = None,
                     con_prevision: bool = True, version: bool = True) -> dict:
        f = str(uuid.uuid4())
        self.x("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
               "VALUES (%s, %s, 'FINANCIACION', 'Financiacion sintetica')", (f, OWNER))
        self.x("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado) "
               "VALUES (%s, %s, 'EUR', %s)", (f, tipo, capital))
        hd = self.hecho() if m else None
        ver = None
        if version:
            ver = str(uuid.uuid4())
            self.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
                   "motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) "
                   "VALUES (%s, %s, %s, 'ALTA', %s, 'FIJO', 2.5, 'FRANCES', 'MENSUAL')", (ver, f, ESCRITURA, hd))
        cuotas = [(1, "100"), (2, "100"), (3, "100")] if cuotas is None else cuotas
        estados = estados or ["ABIERTA"] * len(cuotas)
        ids, prevs = [], []
        for (numero, capital_k), estado in zip(cuotas, estados):
            pid = self.prevision(estado) if con_prevision else None
            cid = str(uuid.uuid4())
            self.x("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, condicion_version_id, "
                   "numero_cuota, fecha_vencimiento, capital_previsto, interes_previsto, comisiones_previstas, "
                   "importe_total_previsto, prevision_id) VALUES (%s, %s, %s, %s, %s, %s, 0, 0, %s, %s)",
                   (cid, f, ver, numero, ESCRITURA + dt.timedelta(days=30 * numero), capital_k,
                    capital_k if capital_k not in (None, "0") else "1", pid))
            ids.append(cid)
            prevs.append(pid)
        return {"f": f, "hd": hd, "version": ver, "cuotas": ids, "previsiones": prevs}

    def fijar(self) -> None:
        """Comprueba los diferidos de los fixtures y vuelve a diferir; pasa a gapto_runtime."""
        self.x("SET CONSTRAINTS ALL IMMEDIATE")
        self.x("SET CONSTRAINTS ALL DEFERRED")
        self.x("SET LOCAL ROLE gapto_runtime")

    def comprobar(self) -> None:
        self.x("SET CONSTRAINTS ALL IMMEDIATE")


def _rechaza(db: psycopg.Connection, prefijo: str, preparar, actuar) -> None:
    with db.transaction(force_rollback=True):
        e = Esc(db)
        ctx = preparar(e)
        e.fijar()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            with db.transaction():
                actuar(e, ctx)
                e.comprobar()
        assert exc.value.sqlstate == "P0001"
        assert str(exc.value).startswith(prefijo + ":"), str(exc.value)


def _admite(db: psycopg.Connection, preparar, actuar) -> None:
    with db.transaction(force_rollback=True):
        e = Esc(db)
        ctx = preparar(e)
        e.fijar()
        actuar(e, ctx)
        e.comprobar()


# ------------------------------------------------------------------ G2 (B-G2-01..07)
def test_b_g2_01_modificar_p_sin_tocar_cuotas(db):
    _rechaza(db, "INV-0354-G2", lambda e: e.financiacion(),
             lambda e, c: e.x("UPDATE gapto.financiaciones SET capital_original_contratado = "
                              "capital_original_contratado + 0.01 WHERE entidad_id = %s", (c["f"],)))


def test_b_g2_02_p_a_null(db):
    _rechaza(db, "INV-0354-G2", lambda e: e.financiacion(),
             lambda e, c: e.x("UPDATE gapto.financiaciones SET capital_original_contratado = NULL "
                              "WHERE entidad_id = %s", (c["f"],)))


def test_b_g2_03_capital_de_cuota_abierta_rompe_suma(db):
    _rechaza(db, "INV-0354-G2", lambda e: e.financiacion(),
             lambda e, c: e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = capital_previsto + 1 "
                              "WHERE id = %s", (c["cuotas"][0],)))


def test_b_g2_04_cuota_duplicada_capital_cero(db):
    _rechaza(db, "INV-0354-G2", lambda e: e.financiacion(),
             lambda e, c: e.x("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, numero_cuota, "
                              "fecha_vencimiento, capital_previsto, interes_previsto, comisiones_previstas, "
                              "importe_total_previsto) VALUES (%s, %s, 2, %s, 0, 1, 0, 1)",
                              (str(uuid.uuid4()), c["f"], ESCRITURA + dt.timedelta(days=61))))


def test_b_g2_05_version_alta_con_hecho_sin_cuotas(db):
    def preparar(e):
        c = e.financiacion(m=False, cuotas=[], version=False)
        c["hd"] = e.hecho()
        return c
    _rechaza(db, "INV-0354-G2", preparar,
             lambda e, c: e.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, "
                              "vigente_desde, motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, "
                              "sistema_amortizacion, periodicidad) VALUES (%s, %s, %s, 'ALTA', %s, 'FIJO', 2.5, "
                              "'FRANCES', 'MENSUAL')", (str(uuid.uuid4()), c["f"], ESCRITURA, c["hd"])))


def test_b_g2_06_revision_valida(db):
    def actuar(e, c):
        e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
            (ESCRITURA + dt.timedelta(days=44), c["version"]))
        nueva = str(uuid.uuid4())
        e.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
            "motivo_version, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) "
            "VALUES (%s, %s, %s, 'CAMBIO_CONDICIONES', 'FIJO', 2.95, 'FRANCES', 'MENSUAL')",
            (nueva, c["f"], ESCRITURA + dt.timedelta(days=45)))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 110, importe_total_previsto = 111, "
            "condicion_version_id = %s WHERE id = %s", (nueva, c["cuotas"][1]))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 90, importe_total_previsto = 91, "
            "condicion_version_id = %s WHERE id = %s", (nueva, c["cuotas"][2]))
    _admite(db, lambda e: e.financiacion(), actuar)


def test_b_g2_07_legacy_v3_con_cuotas_p_distinto_de_suma(db):
    _rechaza(db, "INV-0354-G2", lambda e: e.financiacion(m=False, con_prevision=False),
             lambda e, c: e.x("UPDATE gapto.financiaciones SET capital_original_contratado = 301 "
                              "WHERE entidad_id = %s", (c["f"],)))


# ------------------------------------------------------------------ G2-E
def test_b_g2e_01_hipoteca_a_prestamo_con_cuotas(db):
    _rechaza(db, "INV-0354-G2E", lambda e: e.financiacion(),
             lambda e, c: e.x("UPDATE gapto.financiaciones SET tipo_financiacion = 'PRESTAMO' "
                              "WHERE entidad_id = %s", (c["f"],)))


# ------------------------------------------------------------------ G1 y G1-R
def test_b_g1_01_cuota_con_prevision_realizada(db):
    _rechaza(db, "INV-0354-G1", lambda e: e.financiacion(estados=["REALIZADA", "ABIERTA", "ABIERTA"]),
             lambda e, c: e.x("UPDATE gapto.financiacion_cuotas SET interes_previsto = 1, "
                              "importe_total_previsto = 101 WHERE id = %s", (c["cuotas"][0],)))


def test_b_g1_02_cuota_sin_prevision(db):
    _rechaza(db, "INV-0354-G1", lambda e: e.financiacion(m=False, con_prevision=False),
             lambda e, c: e.x("UPDATE gapto.financiacion_cuotas SET interes_previsto = 1, "
                              "importe_total_previsto = 101 WHERE id = %s", (c["cuotas"][0],)))


@pytest.mark.parametrize("estado", ["OMITIDA", "CANCELADA"])
def test_b_g1_03_cuota_con_prevision_omitida_o_cancelada(db, estado):
    _rechaza(db, "INV-0354-G1", lambda e: e.financiacion(estados=[estado, "ABIERTA", "ABIERTA"]),
             lambda e, c: e.x("UPDATE gapto.financiacion_cuotas SET interes_previsto = 1, "
                              "importe_total_previsto = 101 WHERE id = %s", (c["cuotas"][0],)))


def test_b_g1_04_cambio_de_prevision_en_cuota_abierta(db):
    def preparar(e):
        c = e.financiacion()
        c["otra"] = e.prevision()
        return c
    _rechaza(db, "INV-0354-G1", preparar,
             lambda e, c: e.x("UPDATE gapto.financiacion_cuotas SET prevision_id = %s WHERE id = %s",
                              (c["otra"], c["cuotas"][0])))


def test_b_g1r_01_reabrir_prevision_de_cuota(db):
    _rechaza(db, "INV-0354-G1R", lambda e: e.financiacion(estados=["REALIZADA", "ABIERTA", "ABIERTA"]),
             lambda e, c: e.x("UPDATE gapto.previsiones SET estado = 'ABIERTA' WHERE id = %s",
                              (c["previsiones"][0],)))


# ------------------------------------------------------------------ G3
def test_b_g3_01_primer_cierre_de_vigencia(db):
    _admite(db, lambda e: e.financiacion(),
            lambda e, c: e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
                             (ESCRITURA + dt.timedelta(days=44), c["version"])))


@pytest.mark.parametrize("nuevo", ["mover", "reabrir"])
def test_b_g3_02_segundo_cambio_de_vigencia(db, nuevo):
    def preparar(e):
        c = e.financiacion()
        e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
            (ESCRITURA + dt.timedelta(days=44), c["version"]))
        return c
    valor = None if nuevo == "reabrir" else ESCRITURA + dt.timedelta(days=50)
    _rechaza(db, "INV-0354-G3", preparar,
             lambda e, c: e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
                              (valor, c["version"])))


@pytest.mark.parametrize("columna", ["tasa_anual_pct", "hecho_causa_id"])
def test_b_g3_03_cambio_de_condicion_historica(db, columna):
    def preparar(e):
        c = e.financiacion()
        c["otro_hecho"] = e.hecho()
        return c

    def actuar(e, c):
        if columna == "tasa_anual_pct":
            e.x("UPDATE gapto.financiacion_condiciones_versiones SET tasa_anual_pct = 2.6 WHERE id = %s",
                (c["version"],))
        else:
            e.x("UPDATE gapto.financiacion_condiciones_versiones SET hecho_causa_id = %s WHERE id = %s",
                (c["otro_hecho"], c["version"]))
    _rechaza(db, "INV-0354-G3", preparar, actuar)


# ------------------------------------------------------------------ negativos de ambito (N-01..N-06)
def test_n_01_prestamo_con_cuotas_y_suma_distinta(db):
    def actuar(e, c):
        e.x("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
            "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
            "VALUES (%s, %s, 7, %s, 55, 0, 0, 55)", (str(uuid.uuid4()), c["f"], ESCRITURA + dt.timedelta(days=200)))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 99 WHERE id = %s", (c["cuotas"][0],))
        e.x("UPDATE gapto.financiaciones SET capital_original_contratado = 1000 WHERE entidad_id = %s", (c["f"],))
    _admite(db, lambda e: e.financiacion(tipo="PRESTAMO", m=False), actuar)


@pytest.mark.parametrize("tipo", ["COMPRA_FINANCIADA", "HIPOTECA"])
def test_n_02_version_fuera_de_m(db, tipo):
    def actuar(e, c):
        e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
            (ESCRITURA + dt.timedelta(days=44), c["version"]))
        e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s, tasa_anual_pct = 3.1 "
            "WHERE id = %s", (ESCRITURA + dt.timedelta(days=60), c["version"]))
    _admite(db, lambda e: e.financiacion(tipo=tipo, m=False, con_prevision=False), actuar)


def test_n_03_legacy_sin_cuotas_capital_null(db):
    _admite(db, lambda e: e.financiacion(capital=None, m=False, cuotas=[]),
            lambda e, c: e.x("UPDATE gapto.financiaciones SET notas = 'nota' WHERE entidad_id = %s", (c["f"],)))


def test_n_04_prevision_de_regla_reabierta(db):
    def preparar(e):
        return {"p": e.prevision("REALIZADA")}
    _admite(db, preparar,
            lambda e, c: e.x("UPDATE gapto.previsiones SET estado = 'ABIERTA' WHERE id = %s", (c["p"],)))


def test_n_05_cuota_abierta_de_m_conservando_suma(db):
    def preparar(e):
        c = e.financiacion()
        c["v2"] = str(uuid.uuid4())
        e.x("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
            (ESCRITURA + dt.timedelta(days=44), c["version"]))
        e.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
            "motivo_version, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) "
            "VALUES (%s, %s, %s, 'CAMBIO_CONDICIONES', 'FIJO', 3, 'FRANCES', 'MENSUAL')",
            (c["v2"], c["f"], ESCRITURA + dt.timedelta(days=45)))
        return c

    def actuar(e, c):
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101, interes_previsto = 2, "
            "importe_total_previsto = 103, condicion_version_id = %s WHERE id = %s", (c["v2"], c["cuotas"][1]))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 99, interes_previsto = 2, "
            "importe_total_previsto = 101, condicion_version_id = %s WHERE id = %s", (c["v2"], c["cuotas"][2]))
    _admite(db, preparar, actuar)


def test_n_06_financiacion_en_h_sin_tocar_capital_ni_tipo(db):
    _admite(db, lambda e: e.financiacion(),
            lambda e, c: e.x("UPDATE gapto.financiaciones SET notas = 'revisada', fecha_vencimiento_final_prevista = %s "
                             "WHERE entidad_id = %s", (ESCRITURA + dt.timedelta(days=120), c["f"])))


# ------------------------------------------------------------------ inventario, forma y huella
def test_0354_inventario_seis_funciones_invoker(db):
    with db.cursor() as cur:
        cur.execute("SELECT p.proname, p.prosecdef, l.lanname, p.proowner::regrole::text, p.proacl IS NULL, "
                    "strpos(p.prosrc, '--') FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid = p.prolang "
                    "WHERE p.pronamespace = 'gapto'::regnamespace AND p.proname = ANY(%s) ORDER BY p.proname",
                    (sorted(FUNCIONES),))
        filas = cur.fetchall()
    assert {f[0] for f in filas} == FUNCIONES and len(filas) == 6
    assert all(f[1:] == (False, "plpgsql", "gapto_owner", True, 0) for f in filas), filas


def test_0354_inventario_siete_triggers(db):
    with db.cursor() as cur:
        cur.execute("SELECT t.tgname, c.relname, t.tgdeferrable, t.tginitdeferred, t.tgenabled "
                    "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "
                    "WHERE NOT t.tgisinternal AND t.tgname = ANY(%s) ORDER BY t.tgname", (sorted(TRIGGERS),))
        filas = {f[0]: f[1:] for f in cur.fetchall()}
    assert set(filas) == set(TRIGGERS)
    for nombre, (tabla, diferido) in TRIGGERS.items():
        assert filas[nombre] == (tabla, diferido, diferido, "O"), (nombre, filas[nombre])


def test_0354_huella_d111_current(db):
    referencia = _runner().HUELLAS_D111_POR_HEAD["0354"]
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    observadas = dict(zip([d.name for d in cursor.description], cursor.fetchone()))
    assert {k: observadas[k] for k in referencia} == referencia


def test_0354_desviacion_frente_a_0353():
    h = _runner().HUELLAS_D111_POR_HEAD
    assert {k for k in h["0354"] if h["0354"][k] != h["0353"][k]} == {
        "h2_constraints", "h5_triggers", "h6_funciones", "recuentos"}
    assert h["0354"]["recuentos"] == "788/655/287/82/65/34/1024/3"


def test_0354_runner_declara_0354_y_conserva_0353():
    runner = _runner()
    assert runner.CONTRATOS_POR_HEAD["0354"] == {**runner.CONTRATOS_POR_HEAD["0353"], "funciones": 34,
                                                  "triggers_no_internos": 65, "constraint_triggers": 44}
    assert runner.CONTRATO_POR_DEFECTO == runner.CONTRATOS_POR_HEAD["0354"]
    exigidos = runner.TESTS_EXIGIDOS_POR_HEAD
    assert exigidos["0354"] == (*exigidos["0353"], "test_049_f06_01h_0354_garantias")
    assert "0354" in runner.HEADS_QUE_EXIGEN_REFERENCIA_D111


def test_0354_fichero_forma():
    texto = (RAIZ / "migrations" / "0354_f06_01h_garantias_hipoteca.sql").read_text(encoding="utf-8")
    cuerpo = texto.split("BEGIN;", 1)[1]
    assert "SET search_path" not in cuerpo and "SECURITY DEFINER" not in cuerpo and "ALTER TABLE" not in cuerpo
    assert texto.count("CREATE FUNCTION") == 6 and texto.count("CREATE TRIGGER") + texto.count(
        "CREATE CONSTRAINT TRIGGER") == 7


def _postcheck_0354() -> str:
    texto = (RAIZ / "migrations" / "0354_f06_01h_garantias_hipoteca.sql").read_text(encoding="utf-8")
    inicio = texto.index("DO $postcheck_0354$")
    fin = texto.index("$postcheck_0354$;", inicio + len("DO $postcheck_0354$")) + len("$postcheck_0354$;")
    return texto[inicio:fin]


def test_0354_po04_discrimina_privilegio_indebido(db):
    """Firma Q2 (b): el bloque de postchecks de 0354, ejecutado sobre el head, pasa (control); con UN privilegio
    de tabla de mas para gapto_runtime falla en PO-04 (cuenta con aclexplode, no con information_schema, que
    dependia de los roles habilitados del usuario conectado: STOP_F06-T3-2_1). Todo en transacciones revertidas."""
    bloque = _postcheck_0354()
    assert "aclexplode" in bloque and "information_schema" not in bloque
    with db.transaction(force_rollback=True):
        db.execute(bloque)                                                        # control: head 0354 intacto
    with db.transaction(force_rollback=True):
        db.execute("SET LOCAL ROLE gapto_owner")
        db.execute("GRANT TRUNCATE ON gapto.financiacion_cuotas TO gapto_runtime")  # privilegio indebido
        db.execute("RESET ROLE")
        with pytest.raises(psycopg.errors.RaiseException,
                           match=r"PO-04: privilegios de tabla de gapto_runtime = 267 \(esperados 266\)"):
            with db.transaction():
                db.execute(bloque)
