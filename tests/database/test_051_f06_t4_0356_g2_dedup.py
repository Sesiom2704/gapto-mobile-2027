# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_051_f06_t4_0356_g2_dedup.py
# Ruta: tests/database/test_051_f06_t4_0356_g2_dedup.py
# Descripción: F06 T4 · P-RB206-1 · migration 0356 (deduplicacion de G2 con memo de transaccion; opcion M).
#              Mandato MANDATO_F06-T4_G2_0356_v1.0 (753bebb2…) §3 y enmienda 01 (257be460…); ajustes 1, 2 y 5
#              del dictamen DICTAMEN_T4_G2_v1.0. Casos dirigidos que discriminan cada guarda del memo:
#                a) invalidacion en INSERT, UPDATE y DELETE de T3, T4 y T5; UPDATE que mueve una cuota entre dos
#                   financiaciones (OLD y NEW; la guarda G1 se retira en la transaccion revertida para simular una
#                   ruta de escritura que la eludiera); cambio de ambito (tipo y capital);
#                b) SET CONSTRAINTS ALL IMMEDIATE (valida) -> DML que rompe Σ capital -> rechazo al COMMIT real;
#                c) SAVEPOINT -> validacion inmediata -> ROLLBACK TO SAVEPOINT -> DML invalida -> rechazo; DML
#                   invalida antes del savepoint corregida y validada dentro de el y revertida -> rechazo; DML
#                   invalida dentro de un savepoint revertido -> valido;
#                d) dos transacciones seguidas en la misma conexion: la segunda no reutiliza el memo de la primera;
#                e) GUC escrito a mano mal formado o de otra transaccion -> se valida;
#                f) varias financiaciones en una transaccion, una incumplidora -> rechazo.
#              Ademas: inventario de 0356 (funcion invoker y tres triggers ordinarios que ordenan antes de G2),
#              forma del fichero, runner y huella D-111 current. Todo en transacciones revertidas salvo los COMMIT
#              que se esperan rechazados (no persisten nada).
#              Rechazos: SQLSTATE P0001 con el prefijo «INV-0354-G2:» (mensajes de 0354, nucleo sin cambios).
# Versión: 0.1.0 (F06 T4 P-RB206-1; mandato 753bebb2… y enmienda 01 257be460…)
# ============================================================
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import uuid

import psycopg
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0356_f06_t4_g2_dedup.sql"
OWNER = "0356a000-0000-4000-8000-000000000001"
GDO = "26ee751e-aa9c-5c3b-a81c-7a28e5a5be34"          # GENERACION_DERECHO_OBLIGACION (0150)
GASTO = "b9c7573f-fa72-54a1-8b2d-b1c189f32533"        # GASTO (0150)
ESCRITURA = dt.date(2026, 1, 15)
G2 = "INV-0354-G2"
MEMO = "gapto_g2.validadas"
TRIGGERS_0356 = {
    "trg_financiacion_cuotas__borrar_memo_g2": ("financiacion_cuotas", "trg_financiacion_cuotas__cuadro_hipoteca"),
    "trg_financiaciones__borrar_memo_g2": ("financiaciones", "trg_financiaciones__cuadro_hipoteca"),
    "trg_financiacion_condiciones_versiones__borrar_memo_g2": (
        "financiacion_condiciones_versiones", "trg_financiacion_condiciones_versiones__cuadro_hipoteca"),
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
    """Fixtures sinteticos de un owner dentro de una transaccion (patron de test_049)."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0356') ON CONFLICT DO NOTHING",
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

    def prevision(self) -> str:
        pid = str(uuid.uuid4())
        self.x("INSERT INTO gapto.previsiones (id, owner_user_id, concepto, tipo_hecho_id, fecha_esperada_desde, "
               "fecha_esperada_hasta, flujo_tesoreria_esperado, moneda, importe_esperado, presupuestable, estado, "
               "recalculo_automatico) VALUES (%s, %s, 'Cuota sintetica', %s, %s, %s, 'SALIDA', 'EUR', 100, false, "
               "'ABIERTA', false)", (pid, OWNER, GASTO, ESCRITURA, ESCRITURA))
        return pid

    def financiacion(self, *, f: str | None = None, tipo: str = "HIPOTECA", capital: str = "300", m: bool = True,
                     cuotas: tuple[int, ...] = (1, 2, 3), capital_cuota: str = "100", version: bool = True) -> dict:
        f = f or str(uuid.uuid4())
        self.x("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
               "VALUES (%s, %s, 'FINANCIACION', 'Financiacion sintetica 0356')", (f, OWNER))
        self.x("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado) "
               "VALUES (%s, %s, 'EUR', %s)", (f, tipo, capital))
        hd = self.hecho() if m else None
        ver = None
        if version:
            ver = str(uuid.uuid4())
            self.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
                   "motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) "
                   "VALUES (%s, %s, %s, 'ALTA', %s, 'FIJO', 2.5, 'FRANCES', 'MENSUAL')", (ver, f, ESCRITURA, hd))
        ids = [self.cuota(f, ver, n, capital_cuota) for n in cuotas]
        return {"f": f, "version": ver, "cuotas": ids}

    def cuota(self, f: str, ver: str, numero: int, capital: str = "100") -> str:
        cid = str(uuid.uuid4())
        self.x("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, condicion_version_id, "
               "numero_cuota, fecha_vencimiento, capital_previsto, interes_previsto, comisiones_previstas, "
               "importe_total_previsto, prevision_id) VALUES (%s, %s, %s, %s, %s, %s, 0, 0, %s, %s)",
               (cid, f, ver, numero, ESCRITURA + dt.timedelta(days=30 * numero), capital, capital, self.prevision()))
        return cid

    def validar(self) -> None:
        """Valida ya los diferidos pendientes (escribe el memo) y vuelve a diferir."""
        self.x("SET CONSTRAINTS ALL IMMEDIATE")
        self.x("SET CONSTRAINTS ALL DEFERRED")

    def runtime(self) -> None:
        self.x("SET LOCAL ROLE gapto_runtime")

    def owner(self) -> None:
        self.x("SET LOCAL ROLE gapto_owner")

    def sin_g1(self) -> None:
        """Retira SOLO la guarda G1 (cuota inmutable) en esta transaccion revertida para simular una ruta de
        escritura que mueva una cuota de financiacion; los triggers de G2 y de 0356 siguen activos."""
        self.owner()
        self.x("ALTER TABLE gapto.financiacion_cuotas DISABLE TRIGGER trg_financiacion_cuotas__inmutable_no_abierta")

    def memo(self) -> str | None:
        return _uno(self.db, "SELECT pg_catalog.current_setting(%s, true)", (MEMO,))

    def xid(self) -> str:
        return str(_uno(self.db, "SELECT pg_catalog.pg_current_xact_id()::text"))


def _rechaza_comprobando(db: psycopg.Connection, preparar, actuar) -> None:
    """Transaccion revertida; el «COMMIT» es SET CONSTRAINTS ALL IMMEDIATE (patron de test_049)."""
    with db.transaction(force_rollback=True):
        e = Esc(db)
        ctx = preparar(e)
        e.validar()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            with db.transaction():
                actuar(e, ctx)
                e.x("SET CONSTRAINTS ALL IMMEDIATE")
        assert exc.value.sqlstate == "P0001"
        assert str(exc.value).startswith(G2 + ":"), str(exc.value)


def _admite_comprobando(db: psycopg.Connection, preparar, actuar) -> None:
    with db.transaction(force_rollback=True):
        e = Esc(db)
        ctx = preparar(e)
        e.validar()
        actuar(e, ctx)
        e.x("SET CONSTRAINTS ALL IMMEDIATE")


def _rechaza_al_commit(db: psycopg.Connection, actuar) -> None:
    """COMMIT REAL que se espera rechazado por G2: no persiste nada."""
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        with db.transaction():
            actuar(Esc(db))
    assert exc.value.sqlstate == "P0001"
    assert str(exc.value).startswith(G2 + ":"), str(exc.value)


# ------------------------------------------------------------------ a) invalidacion por tabla y evento
def test_a_t3_insert_tras_validar(db):
    """T3 INSERT (NEW): una cuota mas en una hipoteca ya validada rompe la numeracion y Σ."""
    _rechaza_comprobando(db, lambda e: e.financiacion(),
                         lambda e, c: (e.runtime(), e.cuota(c["f"], c["version"], 4)))


def test_a_t3_update_capital_tras_validar(db):
    """T3 UPDATE (OLD y NEW de la misma financiacion)."""
    _rechaza_comprobando(db, lambda e: e.financiacion(),
                         lambda e, c: (e.runtime(), e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 99 "
                                                         "WHERE id = %s", (c["cuotas"][0],))))


def test_a_t3_delete_tras_validar(db):
    """T3 DELETE (OLD)."""
    _rechaza_comprobando(db, lambda e: e.financiacion(),
                         lambda e, c: e.x("DELETE FROM gapto.financiacion_cuotas WHERE id = %s", (c["cuotas"][2],)))


def test_a_t3_update_mueve_cuota_old_rompe(db):
    """T3 UPDATE que mueve una cuota de F1 (hipoteca validada) a F2 (prestamo, fuera de ambito): solo se rompe la
    financiacion de OLD. Discrimina la invalidacion de OLD."""
    def preparar(e):
        return {"f1": e.financiacion(), "f2": e.financiacion(tipo="PRESTAMO", m=False, cuotas=(1,))}
    def actuar(e, c):
        e.sin_g1()
        e.x("UPDATE gapto.financiacion_cuotas SET financiacion_entidad_id = %s, condicion_version_id = %s, "
            "numero_cuota = 2 WHERE id = %s", (c["f2"]["f"], c["f2"]["version"], c["f1"]["cuotas"][2]))
    _rechaza_comprobando(db, preparar, actuar)


def test_a_t3_update_mueve_cuota_new_rompe(db):
    """T3 UPDATE que mueve una cuota de F2 (prestamo, fuera de ambito) a F1 (hipoteca validada): solo se rompe la
    financiacion de NEW. Discrimina la invalidacion de NEW."""
    def preparar(e):
        return {"f1": e.financiacion(), "f2": e.financiacion(tipo="PRESTAMO", m=False, cuotas=(1,))}
    def actuar(e, c):
        e.sin_g1()
        e.x("UPDATE gapto.financiacion_cuotas SET financiacion_entidad_id = %s, condicion_version_id = %s, "
            "numero_cuota = 4 WHERE id = %s", (c["f1"]["f"], c["f1"]["version"], c["f2"]["cuotas"][0]))
    _rechaza_comprobando(db, preparar, actuar)


def test_a_t4_update_capital_tras_validar(db):
    """T4 UPDATE de capital_original_contratado."""
    _rechaza_comprobando(db, lambda e: e.financiacion(),
                         lambda e, c: e.x("UPDATE gapto.financiaciones SET capital_original_contratado = 301 "
                                          "WHERE entidad_id = %s", (c["f"],)))


def test_a_t4_cambio_de_ambito_por_tipo(db):
    """T4 UPDATE de tipo (cambio de ambito): un prestamo con cuotas que no suman el capital se valida fuera de
    ambito (entra en el memo) y al pasar a HIPOTECA debe revalidarse y rechazarse."""
    _rechaza_comprobando(db, lambda e: e.financiacion(tipo="PRESTAMO", capital="500", m=False),
                         lambda e, c: e.x("UPDATE gapto.financiaciones SET tipo_financiacion = 'HIPOTECA' "
                                          "WHERE entidad_id = %s", (c["f"],)))


def test_a_t5_insert_version_entra_en_m(db):
    """T5 INSERT (NEW): una hipoteca sin cuotas y sin M esta fuera de H y se valida; una version ALTA con hecho
    causa la mete en M sin cuotas y debe rechazarse."""
    def actuar(e, c):
        e.x("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
            "motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) "
            "VALUES (%s, %s, %s, 'ALTA', %s, 'FIJO', 2.5, 'FRANCES', 'MENSUAL')",
            (str(uuid.uuid4()), c["f"], ESCRITURA + dt.timedelta(days=1), e.hecho()))
    _rechaza_comprobando(db, lambda e: e.financiacion(m=False, cuotas=(), version=False), actuar)


def test_a_t5_update_version_entra_en_m(db):
    """T5 UPDATE (OLD y NEW): poner hecho_causa a la version ALTA de una hipoteca sin cuotas la mete en M."""
    _rechaza_comprobando(db, lambda e: e.financiacion(m=False, cuotas=()),
                         lambda e, c: e.x("UPDATE gapto.financiacion_condiciones_versiones SET hecho_causa_id = %s "
                                          "WHERE id = %s", (e.hecho(), c["version"])))


def test_a_t5_update_mueve_version_entre_financiaciones(db):
    """T5 UPDATE que mueve una version con hecho causa de F2 (prestamo, fuera de ambito) a F1 (hipoteca sin
    cuotas, validada fuera de H): F1 entra en M sin cuotas (NEW) y debe rechazarse."""
    def preparar(e):
        return {"f1": e.financiacion(m=False, cuotas=(), version=False), "f2": e.financiacion(tipo="PRESTAMO", m=True, cuotas=())}
    _rechaza_comprobando(db, preparar,
                         lambda e, c: e.x("UPDATE gapto.financiacion_condiciones_versiones SET financiacion_entidad_id = %s "
                                          "WHERE id = %s", (c["f1"]["f"], c["f2"]["version"])))


def test_a_valido_tras_validar_sigue_admitido(db):
    """Control de equivalencia: una DML que conserva G2 tras una validacion previa se admite."""
    def actuar(e, c):
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 90 WHERE id = %s", (c["cuotas"][0],))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 110 WHERE id = %s", (c["cuotas"][1],))
    _admite_comprobando(db, lambda e: e.financiacion(), actuar)


# ------------------------------------------------------------------ b) IMMEDIATE -> DML -> COMMIT real
def test_b_immediate_valida_y_la_dml_posterior_se_rechaza_al_commit(db):
    def actuar(e):
        c = e.financiacion()
        e.x("SET CONSTRAINTS ALL IMMEDIATE")
        e.x("SET CONSTRAINTS ALL DEFERRED")
        assert c["f"] in (e.memo() or "")
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
    _rechaza_al_commit(db, actuar)


def test_b_immediate_sigue_activo_y_la_dml_posterior_se_rechaza(db):
    """Con SET CONSTRAINTS ALL IMMEDIATE vigente, invalidacion y G2 son AFTER ROW del mismo evento: la
    invalidacion (nombre que ordena antes) debe correr primero."""
    def actuar(e):
        c = e.financiacion()
        e.x("SET CONSTRAINTS ALL IMMEDIATE")
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
    _rechaza_al_commit(db, actuar)


# ------------------------------------------------------------------ c) SAVEPOINT
def test_c_savepoint_validado_revertido_y_dml_invalida_se_rechaza(db):
    def actuar(e):
        c = e.financiacion()
        e.x("SAVEPOINT s1")
        e.x("SET CONSTRAINTS ALL IMMEDIATE")
        e.x("SET CONSTRAINTS ALL DEFERRED")
        assert c["f"] in (e.memo() or "")
        e.x("ROLLBACK TO SAVEPOINT s1")
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
    _rechaza_al_commit(db, actuar)


def test_c_memo_de_un_savepoint_revertido_no_sobrevive(db):
    """DML invalida ANTES del savepoint; dentro se corrige y se valida (memo con F); ROLLBACK TO SAVEPOINT devuelve
    el estado invalido y debe revertir tambien el memo: el COMMIT se rechaza."""
    def actuar(e):
        c = e.financiacion()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
        e.x("SAVEPOINT s1")
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 100 WHERE id = %s", (c["cuotas"][0],))
        e.x("SET CONSTRAINTS ALL IMMEDIATE")
        e.x("SET CONSTRAINTS ALL DEFERRED")
        assert c["f"] in (e.memo() or "")
        e.x("ROLLBACK TO SAVEPOINT s1")
        assert c["f"] not in (e.memo() or "")
    _rechaza_al_commit(db, actuar)


def test_c_dml_invalida_en_savepoint_revertido_se_admite(db):
    def actuar(e, c):
        e.x("SAVEPOINT s1")
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
        e.x("ROLLBACK TO SAVEPOINT s1")
    _admite_comprobando(db, lambda e: e.financiacion(), actuar)


# ------------------------------------------------------------------ d) dos transacciones en la misma conexion
def test_d_segunda_transaccion_no_reutiliza_el_memo(db):
    f = str(uuid.uuid4())
    with db.transaction(force_rollback=True):
        e = Esc(db)
        e.financiacion(f=f)
        e.validar()
        assert f in (e.memo() or "")
    assert f not in (_uno(db, "SELECT pg_catalog.current_setting(%s, true)", (MEMO,)) or "")
    with db.transaction(force_rollback=True):
        e = Esc(db)
        c = e.financiacion(f=f)
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            with db.transaction():
                e.runtime()
                e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
                e.x("SET CONSTRAINTS ALL IMMEDIATE")
        assert str(exc.value).startswith(G2 + ":"), str(exc.value)


# ------------------------------------------------------------------ e) GUC escrito a mano
@pytest.mark.parametrize("forma", ["otra_transaccion", "mal_formado", "sin_xid", "basura"])
def test_e_guc_manual_no_valido_se_valida(db, forma):
    def actuar(e, c):
        f = c["f"]
        valor = {"otra_transaccion": f"{int(e.xid()) - 1}:{f}",
                 "mal_formado": f"{e.xid()}:{f},no-es-un-uuid",
                 "sin_xid": f":{f}",
                 "basura": f"{e.xid()};{f}"}[forma]
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
        e.x("SELECT pg_catalog.set_config(%s, %s, true)", (MEMO, valor))
    _rechaza_comprobando(db, lambda e: e.financiacion(), actuar)


def test_e_guc_manual_de_esta_transaccion_salta_g2_r_g2_m1(db):
    """R-G2-M1 (aceptado): quien ejecuta SQL con gapto_runtime y escribe a proposito el memo de ESTA transaccion
    hace que el despachador omita la validacion. Se deja demostrado, no protegido."""
    def actuar(e, c):
        e.runtime()
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (c["cuotas"][0],))
        e.x("SELECT pg_catalog.set_config(%s, %s, true)", (MEMO, f"{e.xid()}:{c['f']}"))
    _admite_comprobando(db, lambda e: e.financiacion(), actuar)


# ------------------------------------------------------------------ f) varias financiaciones
def test_f_varias_financiaciones_una_incumplidora_se_rechaza(db):
    def preparar(e):
        return [e.financiacion() for _ in range(3)]
    def actuar(e, cs):
        e.runtime()
        for c in cs[:2]:
            e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 100 WHERE id = %s", (c["cuotas"][0],))
        e.x("UPDATE gapto.financiacion_cuotas SET capital_previsto = 101 WHERE id = %s", (cs[2]["cuotas"][0],))
    _rechaza_comprobando(db, preparar, actuar)


def test_f_varias_financiaciones_validas_se_admiten_y_quedan_en_el_memo(db):
    with db.transaction(force_rollback=True):
        e = Esc(db)
        cs = [e.financiacion() for _ in range(3)]
        e.x("SET CONSTRAINTS ALL IMMEDIATE")
        memo = e.memo() or ""
        assert memo.split(":")[0] == e.xid()
        assert all(c["f"] in memo for c in cs)


# ------------------------------------------------------------------ inventario, fichero y runner
def test_0356_inventario_funcion_y_triggers(db):
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid = p.prolang "
                    "WHERE p.oid = 'gapto.fn_borrar_memo_cuadro_hipoteca()'::regprocedure AND NOT p.prosecdef "
                    "AND l.lanname = 'plpgsql' AND p.proacl IS NULL AND p.proowner = 'gapto_owner'::regrole") == 1
    for nombre, (tabla, g2) in TRIGGERS_0356.items():
        fila = db.execute(
            "SELECT n.tgrelid::regclass::text, n.tgdeferrable, n.tgenabled, n.tgtype = g.tgtype, "
            "n.tgattr::text = g.tgattr::text, n.tgname < g.tgname, g.tgdeferrable "
            "FROM pg_catalog.pg_trigger n JOIN pg_catalog.pg_trigger g ON g.tgrelid = n.tgrelid AND g.tgname = %s "
            "WHERE n.tgname = %s", (g2, nombre)).fetchone()
        assert fila == (f"gapto.{tabla}", False, "O", True, True, True, True), (nombre, fila)


def test_0356_nucleo_sin_cambios_y_despachador_con_memo(db):
    nucleo = _uno(db, "SELECT prosrc FROM pg_catalog.pg_proc WHERE oid = 'gapto.fn_validar_cuadro_hipoteca(uuid[])'::regprocedure")
    texto_0354 = (RAIZ / "migrations" / "0354_f06_01h_garantias_hipoteca.sql").read_text(encoding="utf-8")
    assert nucleo.strip() in texto_0354
    desp = _uno(db, "SELECT prosrc FROM pg_catalog.pg_proc WHERE oid = 'gapto.fn_check_cuadro_hipoteca()'::regprocedure")
    assert MEMO in desp and "pg_current_xact_id" in desp and "fn_validar_cuadro_hipoteca" in desp


def test_0356_fichero_forma():
    texto = MIGRATION.read_text(encoding="utf-8")
    codigo = "\n".join(linea for linea in texto.splitlines() if not linea.lstrip().startswith("--"))
    assert texto.count("\nBEGIN;\n") == 1 and texto.count("\nCOMMIT;\n") == 1
    for prohibido in ("SECURITY DEFINER", "SET search_path", "CREATE TABLE", "ALTER TABLE", "GRANT ", "REVOKE ",
                      "CREATE INDEX", "CREATE POLICY", "fn_validar_cuadro_hipoteca(p_financiaciones", "DROP "):
        assert prohibido not in codigo, prohibido
    assert codigo.count("CREATE TRIGGER") == 3 and codigo.count("CREATE CONSTRAINT TRIGGER") == 0
    assert "CREATE OR REPLACE FUNCTION gapto.fn_check_cuadro_hipoteca()" in texto


def test_0356_runner_declara_0356():
    r = _runner()
    assert r.CONTRATOS_POR_HEAD["0356"] == {**r.CONTRATOS_POR_HEAD["0355"], "funciones": 35, "triggers_no_internos": 68}
    assert r.TESTS_EXIGIDOS_POR_HEAD["0356"] == (*r.TESTS_EXIGIDOS_POR_HEAD["0355"], "test_051_f06_t4_0356_g2_dedup")
    assert "0356" in r.HEADS_QUE_EXIGEN_REFERENCIA_D111
    h55, h56 = r.HUELLAS_D111_POR_HEAD["0355"], r.HUELLAS_D111_POR_HEAD["0356"]
    assert {k for k in h55 if h55[k] != h56[k]} == {"h5_triggers", "h6_funciones", "recuentos"}


def test_0356_huella_d111_current(db):
    referencia = _runner().HUELLAS_D111_POR_HEAD["0356"]
    sql = (RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")
    cursor = db.execute(sql)
    observadas = dict(zip([d.name for d in cursor.description], cursor.fetchone()))
    assert {k: observadas[k] for k in referencia} == referencia
