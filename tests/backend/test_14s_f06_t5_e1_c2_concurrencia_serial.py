# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14s_f06_t5_e1_c2_concurrencia_serial.py
# Ruta: tests/backend/test_14s_f06_t5_e1_c2_concurrencia_serial.py
# Descripcion: F06 T5 E1 · C2, intercalacion CONCURRENTE determinista (A §3.1-2, AJ-T5A-04; O-A2, O-A20).
#   Bateria SERIAL, fuera de la suite general: solo con GAPTO_T5E1_C2_CONCURRENCIA=1; nunca en paralelo.
#   Evidencia JSON por escenario si GAPTO_T5E1_EVIDENCIA apunta a una carpeta. COMMIT real sobre base desechable.
#   Tecnica (patron de test_139, sin sleeps a ciegas): barreras de superusuario FOR UPDATE o un paso retenido
#   DENTRO de su transaccion; cada paso debe verse esperando (pg_blocking_pids) antes del siguiente; se observa
#   QUIEN bloquea A QUIEN (orden de locks) y se libera en orden fijo.
#     P1 · recalcular_futuras(A) frente a OP-17 sobre una prevision de A, en los dos ordenes.
#     P2 · recalcular_futuras(A) frente a recalcular_futuras(B): con A retenido, B termina SIN esperar a A.
#     P3 · frente a una «revision con tope» que bloquea A y B: el writer es de E3; se EMULA con una UdT que
#          toma las dos reglas en el orden global (por UUID) y se retiene; recalcular_futuras(A) y (B) esperan
#          y terminan sin 40P01. Y al reves: recalcular_futuras(A) retenido y la «revision» detras.
#   Oraculos por escenario: nadie colgado, 0 reintentos 40P01, deadlocks_delta = 0, cada paso OK o
#   VERSION_DESFASADA, y ningun agregado ajeno cambia (foto de la otra regla identica antes/despues).
# Version: 0.1.0 (F06 T5 E1, mandato T5E1_HITO v1.0 P1.3)
# ============================================================
from __future__ import annotations

import datetime as dt
import decimal
import json
import logging
import os
import pathlib
import threading
import time
import uuid

import psycopg
import pytest

from app.core.errores import ErrorMotor
from app.core.modelos_prevision import DatosVinculo
from app.repositories import previsiones_repository as repo_prev
from app.repositories import reglas_repository as repo_reglas
from test_113_rodante_y_materializacion import crear_hecho
from test_14r_f06_t5_e1_c2_dos_reglas import crear_regla_calendario, estados, foto_regla, nueva_version

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_T5E1_C2_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_T5E1_C2_CONCURRENCIA=1)")
LOGGER = "gapto.motor.transaccion"
D = decimal.Decimal
F = dt.date.fromisoformat
OK = "OK"
ADMITIDOS = {OK, "VERSION_DESFASADA"}


class Barrera:
    def __init__(self, dsn: str, tabla: str, ident: uuid.UUID) -> None:
        self.conexion = psycopg.connect(dsn)
        self.conexion.execute(f"SELECT id FROM gapto.{tabla} WHERE id = %s FOR UPDATE", (ident,))
        self.pid = self.conexion.execute("SELECT pg_backend_pid()").fetchone()[0]

    def liberar(self) -> None:
        if not self.conexion.closed:
            self.conexion.commit()
            self.conexion.close()


class Paso(threading.Thread):
    def __init__(self, nombre: str, fn) -> None:
        super().__init__(name=nombre, daemon=True)
        self.fn, self.resultado, self.error, self.pid = fn, None, None, None

    def run(self) -> None:
        try:
            self.resultado = self.fn()
        except ErrorMotor as exc:
            self.error = exc.codigo.value
        except Exception as exc:  # pragma: no cover - se registra
            self.error = f"{type(exc).__name__}: {exc}"


def bloqueos(dsn: str) -> dict[int, list[int]]:
    with psycopg.connect(dsn, autocommit=True) as mon:
        filas = mon.execute("SELECT pid, pg_blocking_pids(pid) FROM pg_stat_activity "
                            "WHERE cardinality(pg_blocking_pids(pid)) > 0").fetchall()
    return {f[0]: list(f[1]) for f in filas}


def esperar(cond, limite: float = 15.0) -> bool:
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.05)
    return False


def deadlocks(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


def reintentos(caplog, sqlstate: str) -> int:
    return sum(1 for r in caplog.records if r.name == LOGGER and getattr(r, "sqlstate", None) == sqlstate)


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_T5E1_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def cierre(dsn, caplog, pasos, antes) -> dict:
    for p in pasos:
        p.join(60)
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    return {"resultados": {p.name: p.error or OK for p in pasos}, "vivos": [p.name for p in pasos if p.is_alive()],
            "reintentos_40P01": reintentos(caplog, "40P01"), "reintentos_40001": reintentos(caplog, "40001"),
            "deadlocks_delta": deadlocks(dsn) - antes}


def oraculo(traza: dict) -> None:
    assert not traza["vivos"], traza
    assert traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    assert set(traza["resultados"].values()) <= ADMITIDOS, traza


class Retener:
    """Retiene al hilo `nombre` DENTRO de su transaccion, al entrar en `objetivo` (ya con sus locks previos)."""

    def __init__(self, monkeypatch, modulo, funcion: str, nombre: str) -> None:
        self.llego, self.sigue = threading.Event(), threading.Event()
        original = getattr(modulo, funcion)

        def envoltorio(*args, **kwargs):
            if threading.current_thread().name == nombre and not self.llego.is_set():
                self.llego.set()
                self.sigue.wait(60)
            return original(*args, **kwargs)

        monkeypatch.setattr(modulo, funcion, envoltorio)


@pytest.fixture()
def dos(servicio, servicio_reglas, servicio_previsiones, contexto):
    a = crear_regla_calendario(servicio_reglas, servicio_previsiones, contexto, "C2c A", "800.0000")
    b = crear_regla_calendario(servicio_reglas, servicio_previsiones, contexto, "C2c B", "300.0000")
    estados(servicio, servicio_previsiones, contexto, a, "800.0000", realizada=3, omitida=4, parcial=6)
    estados(servicio, servicio_previsiones, contexto, b, "300.0000", realizada=2, omitida=6, parcial=7)
    a.row_version = nueva_version(servicio_reglas, contexto, a, "900.0000").regla_row_version
    b.row_version = nueva_version(servicio_reglas, contexto, b, "350.0000").regla_row_version
    return a, b


def _recalc(prev, ctx, r):
    return lambda: prev.recalcular_futuras(ctx, regla_id=r.regla_id, desde_fecha=F("2027-05-01"), motivo="C2c")


def _op17(servicio, prev, ctx, prevision_id):
    hecho = crear_hecho(servicio, ctx, F("2027-08-10"), importe=D("900.0000"))
    v = prev.estado_de(ctx, prevision_id).row_version
    return lambda: prev.vincular_realidad(ctx, prevision_id=prevision_id, row_version_esperada=v,
                                          datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho,
                                                             importe_asignado=D("900.0000")))


# ------------------------------------------------------------------ P1
@pytest.mark.parametrize("orden", ["recalculo_primero", "op17_primero"])
def test_p1_recalcular_frente_a_op17_sobre_la_misma_regla(dos, dsn, servicio, servicio_previsiones, contexto, admin,
                                                          caplog, orden):
    a, b = dos
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    owner, agosto = contexto.owner_user_id, a.mapa[F("2027-08-10")]
    foto_b = foto_regla(admin, owner, b.regla_id)
    recalc = ("recalcular_A", _recalc(servicio_previsiones, contexto, a))
    op17 = ("op17_A_agosto", _op17(servicio, servicio_previsiones, contexto, agosto))
    primero, segundo = (recalc, op17) if orden == "recalculo_primero" else (op17, recalc)
    antes = deadlocks(dsn)
    caplog.clear()
    barreras = [Barrera(dsn, "reglas_financieras", a.regla_id), Barrera(dsn, "previsiones", agosto)]
    pasos = [Paso(n, fn) for n, fn in (primero, segundo)]
    traza: dict = {"orden": [primero[0], segundo[0]], "barreras": {"regla_A": barreras[0].pid,
                                                                   "prevision_agosto": barreras[1].pid}}
    try:
        pasos[0].start()
        traza["primero_espera"] = esperar(lambda: len(bloqueos(dsn)) >= 1)
        traza["bloqueos_1"] = bloqueos(dsn)
        pasos[1].start()
        traza["segundo_espera"] = esperar(lambda: len(bloqueos(dsn)) >= 2)
        traza["bloqueos_2"] = bloqueos(dsn)
        for br in barreras:  # orden fijo: regla, despues prevision
            br.liberar()
    finally:
        for br in barreras:
            br.liberar()
    traza.update(cierre(dsn, caplog, pasos, antes))
    traza["agosto"] = str(servicio_previsiones.estado_de(contexto, agosto))
    traza["vinculos_agosto"] = leer_n(admin, owner, "SELECT count(*) FROM gapto.prevision_hechos WHERE prevision_id "
                                                    "= %s", (agosto,))
    traza["foto_b_igual"] = foto_regla(admin, owner, b.regla_id) == foto_b
    evidencia(f"p1_{orden}", traza)
    oraculo(traza)
    assert traza["primero_espera"] and traza["segundo_espera"], traza
    assert traza["foto_b_igual"], traza                                                     # O-A2 / O-A20
    assert traza["vinculos_agosto"] == (1 if traza["resultados"]["op17_A_agosto"] == OK else 0), traza


def leer_n(admin, owner, sql, params) -> int:
    with admin.cursor() as c:
        c.execute("RESET ROLE")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
        try:
            return c.execute(sql, params).fetchone()[0]
        finally:
            c.execute("RESET ALL")


# ------------------------------------------------------------------ P2
def test_p2_recalcular_a_retenido_no_retiene_recalcular_b(dos, dsn, servicio_previsiones, contexto, admin, caplog,
                                                          monkeypatch):
    a, b = dos
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    owner = contexto.owner_user_id
    foto_a0 = foto_regla(admin, owner, a.regla_id)
    antes = deadlocks(dsn)
    caplog.clear()
    retener = Retener(monkeypatch, repo_prev, "futuras_de_regla", "recalcular_A")  # A ya tiene SU regla
    pa = Paso("recalcular_A", _recalc(servicio_previsiones, contexto, a))
    pb = Paso("recalcular_B", _recalc(servicio_previsiones, contexto, b))
    traza: dict = {}
    try:
        pa.start()
        traza["a_retenido"] = retener.llego.wait(30)
        pb.start()
        pb.join(30)
        traza["b_termino_sin_esperar_a_A"] = not pb.is_alive()
        traza["b_resultado"] = pb.error or OK
        traza["foto_a_igual_mientras_b"] = foto_regla(admin, owner, a.regla_id) == foto_a0
    finally:
        retener.sigue.set()
        monkeypatch.undo()
    traza.update(cierre(dsn, caplog, [pa, pb], antes))
    evidencia("p2_dos_recalculos", traza)
    oraculo(traza)
    assert traza["a_retenido"] and traza["b_termino_sin_esperar_a_A"], traza
    assert traza["foto_a_igual_mientras_b"], traza                                          # B no toca A
    assert traza["resultados"] == {"recalcular_A": OK, "recalcular_B": OK}, traza


# ------------------------------------------------------------------ P3
def _revision_con_tope(unidad, ctx, reglas, retener_evento=None):
    """EMULA el writer de revision con tope (E3): una UdT que toma las DOS reglas en orden global por UUID."""
    def operacion(sesion):
        for regla_id in sorted(reglas, key=str):
            assert repo_reglas.bloquear_regla(sesion, regla_id) is not None
        if retener_evento is not None:
            retener_evento[0].set()
            retener_evento[1].wait(60)
        return "OK"
    return lambda: unidad.ejecutar_con_traza(ctx, operacion, nombre="revision_con_tope_emulada").valor


def test_p3_revision_con_tope_retenida_y_los_dos_recalculos_detras(dos, dsn, unidad, servicio_previsiones, contexto,
                                                                   admin, caplog):
    a, b = dos
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    antes = deadlocks(dsn)
    caplog.clear()
    ev = (threading.Event(), threading.Event())
    pt = Paso("revision_tope", _revision_con_tope(unidad, contexto, [a.regla_id, b.regla_id], ev))
    pa = Paso("recalcular_A", _recalc(servicio_previsiones, contexto, a))
    pb = Paso("recalcular_B", _recalc(servicio_previsiones, contexto, b))
    traza: dict = {}
    try:
        pt.start()
        traza["tope_tiene_las_dos"] = ev[0].wait(30)
        pa.start()
        traza["a_espera"] = esperar(lambda: len(bloqueos(dsn)) >= 1)
        pb.start()
        traza["b_espera"] = esperar(lambda: len(bloqueos(dsn)) >= 2)
        traza["bloqueos"] = bloqueos(dsn)
    finally:
        ev[1].set()
    traza.update(cierre(dsn, caplog, [pt, pa, pb], antes))
    evidencia("p3_tope_primero", traza)
    oraculo(traza)
    assert traza["tope_tiene_las_dos"] and traza["a_espera"] and traza["b_espera"], traza
    assert len({tuple(v) for v in traza["bloqueos"].values()}) == 1, traza                 # los dos esperan al tope
    assert traza["resultados"] == {"revision_tope": OK, "recalcular_A": OK, "recalcular_B": OK}, traza


def test_p3_recalculo_retenido_y_la_revision_con_tope_detras(dos, dsn, unidad, servicio_previsiones, contexto, admin,
                                                             caplog, monkeypatch):
    a, b = dos
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    owner = contexto.owner_user_id
    foto_b0 = foto_regla(admin, owner, b.regla_id)
    antes = deadlocks(dsn)
    caplog.clear()
    retener = Retener(monkeypatch, repo_prev, "futuras_de_regla", "recalcular_A")
    pa = Paso("recalcular_A", _recalc(servicio_previsiones, contexto, a))
    pt = Paso("revision_tope", _revision_con_tope(unidad, contexto, [a.regla_id, b.regla_id]))
    traza: dict = {"a_menor_uuid": str(a.regla_id) < str(b.regla_id)}
    try:
        pa.start()
        traza["a_retenido"] = retener.llego.wait(30)
        pt.start()
        traza["tope_espera"] = esperar(lambda: len(bloqueos(dsn)) >= 1)
        traza["bloqueos"] = bloqueos(dsn)
        traza["foto_b_igual_con_a_retenido"] = foto_regla(admin, owner, b.regla_id) == foto_b0
    finally:
        retener.sigue.set()
        monkeypatch.undo()
    traza.update(cierre(dsn, caplog, [pa, pt], antes))
    evidencia("p3_recalculo_primero", traza)
    oraculo(traza)
    assert traza["a_retenido"] and traza["tope_espera"], traza
    assert traza["foto_b_igual_con_a_retenido"], traza
    assert traza["resultados"] == {"recalcular_A": OK, "revision_tope": OK}, traza
