# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_139_f04_r1_concurrencia_serial.py
# Ruta: tests/backend/test_139_f04_r1_concurrencia_serial.py
# Descripcion: F04-R1 (F04-D058 G-R1-D punto 5; AJ-F04R1-V11-05; mandato
#   F04-R1 IMPL v1.0 §F1.3 y §F5.1). Bateria SERIAL y determinista, FUERA de la
#   suite general: solo con GAPTO_F04R1_CONCURRENCIA=1 (WM §13.3.7). Si
#   GAPTO_F04R1_EVIDENCIA apunta a una carpeta, cada escenario deja su JSON.
#   Tecnica: sesiones BARRERA (superusuario) retienen filas con FOR UPDATE; los
#   comandos se lanzan uno a uno en hilos y cada uno debe quedar esperando
#   (pg_blocking_pids) antes del siguiente; las barreras se liberan en un orden
#   fijo. Un 40P01 se detecta por el log de reintento de la UnidadDeTrabajo
#   (logger gapto.motor.transaccion, sqlstate) y por pg_stat_database.deadlocks.
#
#   C1 · corregir_vinculo (previsiones por UUID) frente a la propagacion de
#   OP-02 (impacto_correccion_ancla, previsiones por fecha del predecesor y sin
#   regla), con las dos previsiones en ambos papeles. Preparacion alcanzable
#   por la API: un vinculo V cuyo hecho se anula queda en un sucesor que sigue
#   siendo propagable (sin realidad ACTIVA y con recalculo_automatico=true).
#   Los UUID de los sucesores (los da el llamante) fijan UUID(s_b) < UUID(s_a)
#   mientras la propagacion procesa s_a antes que s_b. Sobre la base el ciclo
#   P_s_a <-> P_s_b produce 40P01 (rojo: evidencia_f04r1\f1\); con G-R1-D
#   (reglas y previsiones por UUID) debe serializar sin 40P01.
#   C2 (dos reglas frente a recalcular_futuras/corregir_estado_terminal):
#   NO_REPRODUCIBLE sobre la base (ver HANDOFF_F04-R1_F1.md).
# Version: 0.1.0 (F04-R1 IMPL F1)
# ============================================================

from __future__ import annotations

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
from app.core.modelos import CamposCorreccion
from app.core.modelos_prevision import DatosRegla
from test_113_rodante_y_materializacion import crear_hecho, version_rodante
from test_128_f04_r1_oraculos_propagacion import _vincular
from test_138_f04_r1_discriminantes import anular, prevision_manual, version_hecho, vincular

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R1_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R1_CONCURRENCIA=1)")
LOGGER = "gapto.motor.transaccion"
import datetime as dt  # noqa: E402
import decimal  # noqa: E402

D = decimal.Decimal
F = dt.date.fromisoformat


# ------------------------------------------------------------------ arnes
class Barrera:
    """Transaccion de superusuario que retiene filas FOR UPDATE hasta liberar()."""

    def __init__(self, dsn: str, tabla: str, ident: uuid.UUID) -> None:
        self.conexion = psycopg.connect(dsn)
        self.conexion.execute(f"SELECT id FROM gapto.{tabla} WHERE id = %s FOR UPDATE", (ident,))
        self.pid = self.conexion.info.backend_pid

    def liberar(self) -> None:
        if not self.conexion.closed:
            self.conexion.commit()
            self.conexion.close()


def bloqueados(dsn: str) -> dict[int, list[int]]:
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


class Paso(threading.Thread):
    def __init__(self, nombre: str, fn) -> None:
        super().__init__(name=nombre, daemon=True)
        self.fn, self.resultado, self.error = fn, None, None

    def run(self) -> None:
        try:
            self.resultado = self.fn()
        except ErrorMotor as exc:
            self.error = exc.codigo.value
        except Exception as exc:  # pragma: no cover - se registra
            self.error = f"{type(exc).__name__}: {exc}"


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R1_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def reintentos_40p01(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and getattr(r, "sqlstate", None) == "40P01"]


# ------------------------------------------------------------------ C1
def _preparar_c1(servicio, servicio_reglas, servicio_previsiones, contexto, admin, v_en: str):
    ra, rb, ca, cb = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    servicio_reglas.crear_regla(contexto, DatosRegla(regla_id=ra, nombre="A"), version_rodante(vigente_desde=F("2027-01-10")))
    servicio_reglas.crear_regla(contexto, DatosRegla(regla_id=rb, nombre="B"), version_rodante(vigente_desde=F("2027-01-17")))
    servicio_previsiones.generar_rodante(contexto, regla_id=ra, uuid_nuevo=ca)
    servicio_previsiones.generar_rodante(contexto, regla_id=rb, uuid_nuevo=cb)
    s_b, s_a = sorted([uuid.uuid4(), uuid.uuid4()], key=str)  # UUID(s_b) < UUID(s_a)
    h1 = crear_hecho(servicio, contexto, F("2027-02-02"), importe=D("100.0000"))
    _vincular(servicio_previsiones, contexto, ca, h1, sucesor=s_a)  # la propagacion procesa s_a primero
    _vincular(servicio_previsiones, contexto, cb, h1, sucesor=s_b)
    # V: vinculo de un hecho que se anula; movido a un sucesor sigue propagable.
    pm = prevision_manual(servicio_previsiones, contexto)
    h3 = crear_hecho(servicio, contexto, F("2027-02-03"), importe=D("45.0000"))
    vinculo_id = uuid.uuid4()
    vincular(servicio_previsiones, contexto, pm, h3, "45.0000", vinculo_id=vinculo_id)
    anular(servicio, contexto, admin, h3)
    origen = s_a if v_en == "s_a" else s_b
    versiones = {p: servicio_previsiones.estado_de(contexto, p).row_version for p in (pm, origen)}
    servicio_previsiones.corregir_vinculo(contexto, vinculo_id=vinculo_id, versiones_esperadas=versiones,
                                          nueva_prevision_id=origen, motivo="preparacion C1")
    return {"h1": h1, "s_a": s_a, "s_b": s_b, "vinculo": vinculo_id, "origen": origen,
            "destino": s_b if origen == s_a else s_a}


@pytest.mark.parametrize("v_en", ["s_a", "s_b"])
def test_c1_corregir_vinculo_frente_a_propagacion_de_op02(v_en, dsn, servicio, servicio_reglas, servicio_previsiones,
                                                          contexto, admin, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    d = _preparar_c1(servicio, servicio_reglas, servicio_previsiones, contexto, admin, v_en)
    s_a, s_b = d["s_a"], d["s_b"]
    for p in (s_a, s_b):  # las dos son propagables
        e = servicio_previsiones.estado_de(contexto, p)
        assert e.estado == "ABIERTA" and e.recalculo_automatico is True
    versiones = {p: servicio_previsiones.estado_de(contexto, p).row_version for p in (s_a, s_b)}
    version_h1 = version_hecho(admin, contexto.owner_user_id, d["h1"])
    antes = deadlocks(dsn)
    x, y = Barrera(dsn, "previsiones", s_a), Barrera(dsn, "previsiones", s_b)
    traza: dict = {"v_en": v_en, "uuid_s_b<uuid_s_a": str(s_b) < str(s_a)}
    op02 = Paso("OP-02", lambda: servicio.corregir_hecho(
        contexto, hecho_id=d["h1"], row_version_esperada=version_h1,
        campos=CamposCorreccion(fecha_hecho=F("2027-02-09")), motivo="C1"))
    cv = Paso("corregir_vinculo", lambda: servicio_previsiones.corregir_vinculo(
        contexto, vinculo_id=d["vinculo"], versiones_esperadas=versiones, nueva_prevision_id=d["destino"], motivo="C1"))
    try:
        op02.start()
        assert esperar(lambda: len(bloqueados(dsn)) >= 1), "OP-02 no espero"
        pid_op02 = next(iter(bloqueados(dsn)))
        traza["op02_espera_a"] = "barrera_s_a" if x.pid in bloqueados(dsn)[pid_op02] else "otro"
        cv.start()
        assert esperar(lambda: len(bloqueados(dsn)) >= 2), "corregir_vinculo no espero"
        pid_cv = next(p for p in bloqueados(dsn) if p != pid_op02)
        traza["cv_espera_a"] = "barrera_s_b" if y.pid in bloqueados(dsn).get(pid_cv, []) else "otro"
        x.liberar()
        # Con corregir_vinculo ya en cola sobre s_b, OP-02 espera al primero de la cola (lock de tupla), no a la
        # barrera: cualquiera de los dos acredita que OP-02 tiene s_a y pide s_b.
        assert esperar(lambda: bool({y.pid, pid_cv} & set(bloqueados(dsn).get(pid_op02, [])))),             "OP-02 no llego a esperar s_b"
        traza["op02_tras_liberar_s_a"] = "espera s_b (barrera o cola de corregir_vinculo)"
        y.liberar()
        op02.join(60)
        cv.join(60)
    finally:
        x.liberar()
        y.liberar()
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    traza.update({
        "op02": op02.error or {"propagadas": sorted(("s_a" if p == s_a else "s_b") for p in op02.resultado.previsiones_propagadas)},
        "corregir_vinculo": cv.error or "OK",
        "reintentos_40P01": reintentos_40p01(caplog),
        "deadlocks_delta": deadlocks(dsn) - antes,
    })
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SELECT prevision_id FROM gapto.prevision_hechos WHERE id = %s", (d["vinculo"],))
        filas = cur.fetchall()
    traza["vinculo_en"] = ["s_a" if f[0] == s_a else "s_b" if f[0] == s_b else "otra" for f in filas]
    evidencia(f"C1_{v_en}", traza)
    assert not op02.is_alive() and not cv.is_alive()
    assert len(filas) == 1, traza
    assert op02.error is None, traza
    assert cv.error in (None, "VERSION_DESFASADA"), traza
    assert not traza["reintentos_40P01"] and traza["deadlocks_delta"] == 0, traza
