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
#   (reglas y previsiones por UUID) debe serializar sin 40P01. Orden REAL
#   observado con G-R1-D (local y Neon, evidencia_f04r1\f7b\): OP-02 toma las
#   reglas y pide s_b ANTES que s_a (orden por UUID), asi que la barrera de s_b
#   lo retiene desde el principio y corregir_vinculo espera a OP-02 en la regla;
#   liberar s_a no lo desbloquea. La tercera espera acredita que OP-02 sigue
#   pidiendo s_b (barrera o cola) tras liberar s_a; el oraculo no cambia.
#   Las barreras guardan el pid REAL del servidor (pg_backend_pid()): tras el
#   proxy de Neon, info.backend_pid es la clave de cancelacion del proxy y no
#   coincide con pg_stat_activity/pg_blocking_pids (F7b, sonda_backend_pid).
#   C2 (dos reglas frente a recalcular_futuras/corregir_estado_terminal):
#   NO_REPRODUCIBLE sobre la base (ver HANDOFF_F04-R1_F1.md).
#
#   F5 · pares SERIALES en los dos ordenes (`serie`): una barrera retiene el
#   primer recurso comun; el primer paso queda esperando, despues el segundo, y
#   se libera. El resultado de cada orden es fijo (ESPERADO) y en ninguno hay
#   40P01 ni deadlocks. Pares: OP-17 frente a OP-02/03/13/14/22; dos OP-17 sobre
#   el mismo hecho; corregir_vinculo cruzados, frente a retirar_vinculo y frente
#   a OP-17; OP-03 frente a OP-13/14/18; ruta con posiciones H->E->R->P (OP-02
#   de un hecho de posicion que realiza una RODANTE) frente a OP-09, OP-14 y
#   cerrar_posicion; relectura con el conjunto cambiado (el vinculo cambia de
#   previsión o de hecho entre la lectura y la adquisicion: 40001 y reintento
#   completo, nunca exito con una proteccion incompleta).
# Version: 0.4.1 (F04-R1 MANT-RV3): comentario en linea de la tercera espera
#   de C1 con el orden real (OP-02 pide s_b antes que s_a). Sin cambios de
#   codigo ni de aserciones.
# Version: 0.4.0 (F04-R1 F7c; HANDOFF_F04-R1_F7B): Barrera.pid = pg_backend_pid()
#   (pid real; tras el proxy de Neon info.backend_pid no coincide con
#   pg_blocking_pids y C1 no podia cumplir su tercera espera). Comentarios de C1
#   con el orden real (OP-02 pide s_b antes que s_a). Aserciones sin cambios.
# Version: 0.3.0 (F04-R1 CORR paso 2; STOP_F04-R1_F6): par OP-22 con
#   marcar_realizada=True frente a OP-17 sobre la MISMA previsión y version, con
#   el ganador forzado por barrera en los dos ordenes. Oraculo IL4: el perdedor
#   recibe VERSION_DESFASADA (nunca ESTADO_PREVISION_INCOMPATIBLE), un unico
#   vinculo, nada del perdedor persiste y, si pierde OP-22, ni rastro de su hecho.
#   Mismo patron en corregir_vinculo/retirar_vinculo (auditoria 3.1): el
#   perdedor cuyo vinculo otro writer movio o retiro recibe VERSION_DESFASADA
#   SIN reintento (la guarda de version precede a la relectura), como en la
#   base; nuevo par dos_retirar.
# Version: 0.2.0 (F04-R1 IMPL F5: pares seriales, posiciones y relectura)
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
        # pid REAL del backend (el que ven pg_stat_activity y pg_blocking_pids); info.backend_pid no vale tras el
        # proxy de Neon (F04-R1 F7c).
        self.pid = self.conexion.execute("SELECT pg_backend_pid()").fetchone()[0]

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
        # Orden real con G-R1-D: OP-02 pide s_b ANTES que s_a, asi que liberar s_a no lo desbloquea. Sigue pidiendo
        # s_b y espera a la barrera de s_b o al primero de la cola (lock de tupla): cualquiera de los dos lo acredita.
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



# ------------------------------------------------------------------ F5 · pares seriales
from types import SimpleNamespace  # noqa: E402

from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPrevisionCompuesta  # noqa: E402
from app.core.modelos_posicion import (  # noqa: E402
    TIPO_OBLIGACION, DatosCierre, DatosCondonacionObligacion, DatosReembolso)
from app.core.modelos_prevision import DatosVinculo  # noqa: E402
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento  # noqa: E402
from app.services.compuesto_service import HechosCompuestosService  # noqa: E402
from app.services.previsiones_service import impacto_correccion_ancla  # noqa: E402
from conftest import leer_fila  # noqa: E402
from f08_motor import efecto  # noqa: E402
from test_109_op12_posiciones import CONDONACION, COBRO, PAGO, alta, delta, tesoreria_nueva  # noqa: E402
from test_117_op13_devolucion import crear_origen, datos_devolucion  # noqa: E402
from test_118_op18_suplemento import datos_suplemento  # noqa: E402
from test_138_f04_r1_discriminantes import hecho_simple, vinculos_de  # noqa: E402
from test_140_f04_r3_op22 import hecho as hecho_op22  # noqa: E402

OK = "OK"
PORCION = "PORCION_DE_REALIDAD_EXCEDIDA"
DESFASADA = "VERSION_DESFASADA"
DEPENDENCIAS = "HECHO_CON_REALIDAD_ASOCIADA"
ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"


def reintentos(caplog, sqlstate: str) -> int:
    return sum(1 for r in caplog.records if r.name == LOGGER and getattr(r, "sqlstate", None) == sqlstate)


def serie(dsn, caplog, barreras, primero, segundo) -> dict:
    """Ejecuta dos pasos en serie determinista detras de las barreras. Devuelve la traza."""
    caplog.clear()
    antes = deadlocks(dsn)
    retenidas = [Barrera(dsn, tabla, ident) for tabla, ident in barreras]
    pasos = [Paso(nombre, fn) for nombre, fn in (primero, segundo)]
    traza: dict = {"orden": [primero[0], segundo[0]]}
    try:
        pasos[0].start()
        traza["primero_espera"] = esperar(lambda: len(bloqueados(dsn)) >= 1)
        pasos[1].start()
        traza["segundo_espera"] = esperar(lambda: len(bloqueados(dsn)) >= 2)
        for b in retenidas:
            b.liberar()
        for p in pasos:
            p.join(60)
    finally:
        for b in retenidas:
            b.liberar()
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    for p in pasos:
        traza[p.name] = p.error or OK
    traza.update({"vivos": [p.name for p in pasos if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"),
                  "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    traza["resultados"] = {p.name: p.resultado for p in pasos}
    return traza


@pytest.fixture()
def s(dsn, unidad, servicio, servicio_reglas, servicio_previsiones, servicio_efectos, servicio_devoluciones,
      servicio_posiciones, servicio_suplementos, servicio_tesoreria, contexto, admin, contraparte, cuenta):
    return SimpleNamespace(
        dsn=dsn, hec=servicio, reg=servicio_reglas, prev=servicio_previsiones, efe=servicio_efectos,
        dev=servicio_devoluciones, pos=servicio_posiciones, sup=servicio_suplementos, tes=servicio_tesoreria,
        op22=HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla),
        ctx=contexto, admin=admin, owner=contexto.owner_user_id, contraparte=contraparte, cuenta=cuenta)


def _version_prev(s, p) -> int:
    return s.prev.estado_de(s.ctx, p).row_version


def _version_entidad(s, entidad_id) -> int:
    return leer_fila(s.admin, s.owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (entidad_id,))[0]


def _op02(s, hecho_id, campos):
    v = version_hecho(s.admin, s.owner, hecho_id)
    return lambda: s.hec.corregir_hecho(s.ctx, hecho_id=hecho_id, row_version_esperada=v, campos=campos,
                                        motivo="F04-R1 F5")


def _op03(s, hecho_id):
    v = version_hecho(s.admin, s.owner, hecho_id)
    return lambda: s.hec.anular_hecho(s.ctx, hecho_id=hecho_id, row_version_esperada=v,
                                      motivo_anulacion="F04-R1 F5")


def _op17(s, prevision_id, hecho_id, importe, *, sucesor=None):
    v = _version_prev(s, prevision_id)
    return lambda: s.prev.vincular_realidad(
        s.ctx, prevision_id=prevision_id, row_version_esperada=v,
        datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho_id, importe_asignado=D(importe),
                           marcar_realizada=sucesor is not None), uuid_sucesor=sucesor)


def _cv(s, vinculo_id, previsiones, **cambios):
    versiones = {p: _version_prev(s, p) for p in previsiones}
    return lambda: s.prev.corregir_vinculo(s.ctx, vinculo_id=vinculo_id, versiones_esperadas=versiones,
                                           motivo="F04-R1 F5", **cambios)


def _retirar(s, vinculo_id, prevision_id):
    v = _version_prev(s, prevision_id)
    return lambda: s.prev.retirar_vinculo(s.ctx, vinculo_id=vinculo_id, prevision_row_version_esperada=v,
                                          motivo="F04-R1 F5")


def _op14_reembolso(s, causal):
    datos_alta = alta(s.contraparte)
    creada = s.pos.crear_posicion(s.ctx, datos_alta)
    return lambda: s.pos.reembolsar(
        s.ctx, entidad_id=datos_alta.entidad_id, entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("40.0000", causa=COBRO), tesoreria=tesoreria_nueva(s.cuenta),
                             hecho_causal_id=causal, relacion_id=uuid.uuid4()))


def _rodante(s, vigente: str = "2027-01-10") -> tuple[uuid.UUID, uuid.UUID]:
    regla, cabeza = uuid.uuid4(), uuid.uuid4()
    s.reg.crear_regla(s.ctx, DatosRegla(regla_id=regla, nombre=f"F5 {vigente}"),
                      version_rodante(vigente_desde=F(vigente)))
    s.prev.generar_rodante(s.ctx, regla_id=regla, uuid_nuevo=cabeza)
    return regla, cabeza


def _vinculo(s, prevision_id, hecho_id, importe) -> uuid.UUID:
    vinculo_id = uuid.uuid4()
    vincular(s.prev, s.ctx, prevision_id, hecho_id, importe, vinculo_id=vinculo_id)
    return vinculo_id


# Cada escenario devuelve (barreras, {nombre: fn}, comprobacion_final | None).
def esc_op17_op02(s):
    _, ca = _rodante(s, "2027-01-10")
    _, cb = _rodante(s, "2027-01-17")
    h1 = crear_hecho(s.hec, s.ctx, F("2027-02-02"), importe=D("100.0000"))
    _vincular(s.prev, s.ctx, ca, h1, sucesor=uuid.uuid4())
    return ([("hechos_financieros", h1)],
            {"OP-17": _op17(s, cb, h1, "45.0000", sucesor=uuid.uuid4()),
             "OP-02": _op02(s, h1, CamposCorreccion(fecha_hecho=F("2027-02-09")))}, None)


def esc_op17_op03(s):
    _, ca = _rodante(s, "2027-01-10")
    _, cb = _rodante(s, "2027-01-17")
    h1 = crear_hecho(s.hec, s.ctx, F("2027-02-02"), importe=D("100.0000"))
    _vincular(s.prev, s.ctx, ca, h1, sucesor=uuid.uuid4())
    return ([("hechos_financieros", h1)],
            {"OP-17": _op17(s, cb, h1, "45.0000", sucesor=uuid.uuid4()), "OP-03": _op03(s, h1)}, None)


def esc_op17_op13(s):
    original = crear_origen(s.hec, s.efe, s.ctx)
    pm = prevision_manual(s.prev, s.ctx)
    return ([("hechos_financieros", original)],
            {"OP-17": _op17(s, pm, original, "10.0000"),
             "OP-13": lambda: s.dev.devolver(s.ctx, datos_devolucion(original))}, None)


def esc_op17_op14(s):
    causal = hecho_simple(s.hec, s.ctx)
    pm = prevision_manual(s.prev, s.ctx)
    return ([("hechos_financieros", causal)],
            {"OP-17": _op17(s, pm, causal, "10.0000"), "OP-14": _op14_reembolso(s, causal)}, None)


def esc_op17_op22(s):
    pm = prevision_manual(s.prev, s.ctx)
    h = hecho_simple(s.hec, s.ctx)
    v = _version_prev(s, pm)
    datos = hecho_op22()
    return ([("previsiones", pm)],
            {"OP-17": _op17(s, pm, h, "10.0000"),
             "OP-22": lambda: s.op22.registrar_hecho_compuesto(s.ctx, DatosHechoCompuesto(
                 hecho=datos, efectos=[efecto("GASTO", D("100.0000"))],
                 prevision=DatosPrevisionCompuesta(prevision_id=pm, prevision_row_version_esperada=v,
                                                   vinculo_id=uuid.uuid4(), importe_asignado=D("100.0000"),
                                                   marcar_realizada=False)))}, None)


def esc_op22_realizada_op17(s):
    """IL4 forzado: OP-22 deja la previsión REALIZADA si gana; OP-17 suelto con la misma version."""
    pm = prevision_manual(s.prev, s.ctx)
    suelto = hecho_simple(s.hec, s.ctx)
    v = _version_prev(s, pm)
    datos = hecho_op22(total="76.1000")
    vinculo_op17, vinculo_op22 = uuid.uuid4(), uuid.uuid4()

    def op17():
        return s.prev.vincular_realidad(
            s.ctx, prevision_id=pm, row_version_esperada=v,
            datos=DatosVinculo(vinculo_id=vinculo_op17, hecho_id=suelto, importe_asignado=D("76.1000"),
                               marcar_realizada=False))

    def comprobar(traza):
        with s.admin.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (pm,))
            vinculos = [f[0] for f in cur.fetchall()]
            cur.execute("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (datos.hecho_id,))
            hechos_op22 = cur.fetchone()[0]
            cur.execute("SELECT estado FROM gapto.previsiones WHERE id = %s", (pm,))
            estado = cur.fetchone()[0]
        traza.update({"vinculos": len(vinculos), "hecho_op22": hechos_op22, "estado_prevision": estado})
        assert len(vinculos) == 1, traza
        if traza["OP-22"] == OK:
            assert vinculos == [vinculo_op22] and hechos_op22 == 1 and estado == "REALIZADA", traza
        else:
            assert vinculos == [vinculo_op17] and hechos_op22 == 0 and estado == "ABIERTA", traza

    return ([("previsiones", pm)],
            {"OP-17": op17,
             "OP-22": lambda: s.op22.registrar_hecho_compuesto(s.ctx, DatosHechoCompuesto(
                 hecho=datos, efectos=[efecto("GASTO", D("76.1000"))],
                 prevision=DatosPrevisionCompuesta(prevision_id=pm, prevision_row_version_esperada=v,
                                                   vinculo_id=vinculo_op22, importe_asignado=D("76.1000"),
                                                   marcar_realizada=True)))}, comprobar)


def _sin_exceso(s, hecho_id, tope="76.1000"):
    def comprobar(traza):
        total = sum((fila[1] for fila in vinculos_de(s.admin, s.owner, hecho_id)), D("0"))
        traza["asignado_final"] = str(total)
        assert total <= D(tope), traza
    return comprobar


def esc_dos_op17(s):
    h = hecho_simple(s.hec, s.ctx)
    p1, p2 = prevision_manual(s.prev, s.ctx), prevision_manual(s.prev, s.ctx)
    return ([("hechos_financieros", h)],
            {"OP-17a": _op17(s, p1, h, "50.0000"), "OP-17b": _op17(s, p2, h, "50.0000")}, _sin_exceso(s, h))


def esc_cv_cruzados(s):
    h1, h2 = hecho_simple(s.hec, s.ctx), hecho_simple(s.hec, s.ctx)
    p1, p2 = prevision_manual(s.prev, s.ctx), prevision_manual(s.prev, s.ctx)
    v1, v2 = _vinculo(s, p1, h1, "30.0000"), _vinculo(s, p2, h2, "30.0000")
    return ([("previsiones", p1), ("previsiones", p2)],
            {"cv1": _cv(s, v1, (p1, p2), nueva_prevision_id=p2),
             "cv2": _cv(s, v2, (p1, p2), nueva_prevision_id=p1)}, None)


def esc_cv_retirar(s):
    h = hecho_simple(s.hec, s.ctx)
    p1, p2 = prevision_manual(s.prev, s.ctx), prevision_manual(s.prev, s.ctx)
    v = _vinculo(s, p1, h, "30.0000")
    # Versiones de p1 y p2 distintas a proposito (retirar_vinculo solo recibe la version, no la previsión).
    _vinculo(s, p2, hecho_simple(s.hec, s.ctx), "1.0000")
    _vinculo(s, p2, hecho_simple(s.hec, s.ctx), "1.0000")
    # Barrera solo en p1, el unico recurso que piden los dos: la cola sigue el orden de arranque.
    return ([("previsiones", p1)],
            {"cv": _cv(s, v, (p1, p2), nueva_prevision_id=p2), "retirar": _retirar(s, v, p1)}, None)


def esc_dos_retirar(s):
    h = hecho_simple(s.hec, s.ctx)
    p1 = prevision_manual(s.prev, s.ctx)
    v = _vinculo(s, p1, h, "30.0000")
    return ([("previsiones", p1)], {"retirar_a": _retirar(s, v, p1), "retirar_b": _retirar(s, v, p1)}, None)


def esc_cv_op17(s):
    h = hecho_simple(s.hec, s.ctx)
    p1, p2 = prevision_manual(s.prev, s.ctx), prevision_manual(s.prev, s.ctx)
    v = _vinculo(s, p1, h, "30.0000")
    return ([("hechos_financieros", h)],
            {"cv": _cv(s, v, (p1,), nuevo_importe=D("60.0000")), "OP-17": _op17(s, p2, h, "40.0000")},
            _sin_exceso(s, h))


def esc_op03_op13(s):
    original = crear_origen(s.hec, s.efe, s.ctx)
    return ([("hechos_financieros", original)],
            {"OP-03": _op03(s, original), "OP-13": lambda: s.dev.devolver(s.ctx, datos_devolucion(original))}, None)


def esc_op03_op14(s):
    causal = hecho_simple(s.hec, s.ctx)
    return ([("hechos_financieros", causal)], {"OP-03": _op03(s, causal), "OP-14": _op14_reembolso(s, causal)}, None)


def esc_op03_op18(s):
    ajustado = hecho_simple(s.hec, s.ctx)
    return ([("hechos_financieros", ajustado)],
            {"OP-03": _op03(s, ajustado),
             "OP-18": lambda: s.sup.registrar(s.ctx, datos_suplemento(relacion_id=uuid.uuid4(),
                                                                      hecho_ajustado_id=ajustado))}, None)


def _posicion_con_rodante(s) -> dict:
    """Obligacion con pago y condonacion; el hecho de la condonacion realiza una RODANTE
    (ruta H -> E -> R -> P en OP-02)."""
    a = alta(s.contraparte, tipo=TIPO_OBLIGACION, nombre="F04-R1 F5")
    r = s.pos.crear_posicion(s.ctx, a)
    pago = delta("30.0000", causa=PAGO)
    r = s.pos.reducir_obligacion(s.ctx, entidad_id=a.entidad_id, entidad_row_version_esperada=r.entidad_row_version,
                                 delta=pago, movimiento=tesoreria_nueva(s.cuenta))
    cond = delta("10.0000", causa=CONDONACION)
    s.pos.condonar_obligacion(s.ctx, entidad_id=a.entidad_id, entidad_row_version_esperada=r.entidad_row_version,
                              datos=DatosCondonacionObligacion(delta=cond))
    regla, cabeza = _rodante(s)
    sucesor = uuid.uuid4()
    _vincular(s.prev, s.ctx, cabeza, cond.hecho_id, "5.0000", sucesor=sucesor)
    return {"entidad": a.entidad_id, "alta": a, "cond": cond, "regla": regla, "sucesor": sucesor}


def _op02_posicion(s, p):
    return _op02(s, p["cond"].hecho_id, CamposCorreccion(concepto="F04-R1 F5 posicion"))


def esc_pos_op09(s):
    p = _posicion_con_rodante(s)
    mov = s.tes.registrar_movimiento(s.ctx, DatosMovimiento(
        movimiento_id=uuid.uuid4(), cuenta_id=s.cuenta, fecha_movimiento=dt.date(2026, 6, 2),
        importe=D("-7.0000"), clase_movimiento="OPERACION"))
    hecho_alta = p["alta"].hecho_id
    v = version_hecho(s.admin, s.owner, hecho_alta)
    return ([("entidades", p["entidad"])],
            {"OP-02": _op02_posicion(s, p),
             "OP-09": lambda: s.tes.conciliar(s.ctx, DatosConciliacion(uuid.uuid4(), hecho_alta, mov.movimiento_id,
                                                                     D("-7.0000")),
                                              hecho_row_version_esperada=v,
                                              movimiento_row_version_esperada=mov.row_version)}, None)


def esc_pos_op14(s):
    p = _posicion_con_rodante(s)
    v = _version_entidad(s, p["entidad"])
    return ([("entidades", p["entidad"])],
            {"OP-02": _op02_posicion(s, p),
             "OP-14": lambda: s.pos.reducir_obligacion(s.ctx, entidad_id=p["entidad"], entidad_row_version_esperada=v,
                                                       delta=delta("5.0000", causa=PAGO),
                                                       movimiento=tesoreria_nueva(s.cuenta))}, None)


def esc_pos_cerrar(s):
    p = _posicion_con_rodante(s)
    saldo = s.pos.saldo(s.ctx, p["entidad"]).saldo.importe
    s.pos.condonar_obligacion(s.ctx, entidad_id=p["entidad"],
                              entidad_row_version_esperada=_version_entidad(s, p["entidad"]),
                              datos=DatosCondonacionObligacion(delta=delta(str(saldo), causa=CONDONACION)))
    v = _version_entidad(s, p["entidad"])
    return ([("entidades", p["entidad"])],
            {"OP-02": _op02_posicion(s, p),
             "cerrar": lambda: s.pos.cerrar_posicion(s.ctx, entidad_id=p["entidad"], entidad_row_version_esperada=v,
                                                     cierre=DatosCierre(motivo_cierre="CONDONADA",
                                                                        fecha_cierre=dt.date(2026, 7, 1)))}, None)


def esc_relectura_prevision(s):
    h = hecho_simple(s.hec, s.ctx)
    p1, p2, p3 = (prevision_manual(s.prev, s.ctx) for _ in range(3))
    v = _vinculo(s, p1, h, "30.0000")
    return ([("hechos_financieros", h)],
            {"cv_a_p2": _cv(s, v, (p1, p2), nueva_prevision_id=p2),
             "cv_a_p3": _cv(s, v, (p1, p3), nueva_prevision_id=p3)}, None)


def esc_relectura_hecho(s):
    h, h2 = hecho_simple(s.hec, s.ctx), hecho_simple(s.hec, s.ctx)
    p1 = prevision_manual(s.prev, s.ctx)
    v = _vinculo(s, p1, h, "30.0000")
    return ([("hechos_financieros", h)],
            {"cv_hecho": _cv(s, v, (p1,), nuevo_hecho_id=h2),
             "cv_importe": _cv(s, v, (p1,), nuevo_importe=D("20.0000"))}, None)


# ESPERADO[escenario] = (preparacion, {primero: {paso: resultado}}). Cada orden tiene UN resultado.
ESPERADO = {
    "op17_op02": (esc_op17_op02, {"OP-17": {"OP-17": OK, "OP-02": OK}, "OP-02": {"OP-02": OK, "OP-17": OK}}),
    "op17_op03": (esc_op17_op03, {"OP-17": {"OP-17": OK, "OP-03": OK}, "OP-03": {"OP-03": OK, "OP-17": ESTADO}}),
    "op17_op13": (esc_op17_op13, {"OP-17": {"OP-17": OK, "OP-13": OK}, "OP-13": {"OP-13": OK, "OP-17": OK}}),
    "op17_op14": (esc_op17_op14, {"OP-17": {"OP-17": OK, "OP-14": OK}, "OP-14": {"OP-14": OK, "OP-17": OK}}),
    "op17_op22": (esc_op17_op22, {"OP-17": {"OP-17": OK, "OP-22": DESFASADA},
                                  "OP-22": {"OP-22": OK, "OP-17": DESFASADA}}),
    # IL4 forzado (CORR): el perdedor SIEMPRE VERSION_DESFASADA, tambien cuando OP-22 deja la previsión REALIZADA.
    "op22r_op17": (esc_op22_realizada_op17, {"OP-17": {"OP-17": OK, "OP-22": DESFASADA},
                                             "OP-22": {"OP-22": OK, "OP-17": DESFASADA}}),
    "dos_op17": (esc_dos_op17, {"OP-17a": {"OP-17a": OK, "OP-17b": PORCION},
                                "OP-17b": {"OP-17b": OK, "OP-17a": PORCION}}),
    "cv_cruzados": (esc_cv_cruzados, {"cv1": {"cv1": OK, "cv2": DESFASADA}, "cv2": {"cv2": OK, "cv1": DESFASADA}}),
    "cv_retirar": (esc_cv_retirar, {"cv": {"cv": OK, "retirar": DESFASADA},
                                    "retirar": {"retirar": OK, "cv": DESFASADA}}),
    "dos_retirar": (esc_dos_retirar, {"retirar_a": {"retirar_a": OK, "retirar_b": DESFASADA},
                                      "retirar_b": {"retirar_b": OK, "retirar_a": DESFASADA}}),
    "cv_op17": (esc_cv_op17, {"cv": {"cv": OK, "OP-17": PORCION}, "OP-17": {"OP-17": OK, "cv": PORCION}}),
    "op03_op13": (esc_op03_op13, {"OP-03": {"OP-03": OK, "OP-13": ESTADO},
                                  "OP-13": {"OP-13": OK, "OP-03": DEPENDENCIAS}}),
    "op03_op14": (esc_op03_op14, {"OP-03": {"OP-03": OK, "OP-14": ESTADO},
                                  "OP-14": {"OP-14": OK, "OP-03": DEPENDENCIAS}}),
    "op03_op18": (esc_op03_op18, {"OP-03": {"OP-03": OK, "OP-18": ESTADO},
                                  "OP-18": {"OP-18": OK, "OP-03": DEPENDENCIAS}}),
    "pos_op09": (esc_pos_op09, {"OP-02": {"OP-02": OK, "OP-09": OK}, "OP-09": {"OP-09": OK, "OP-02": OK}}),
    "pos_op14": (esc_pos_op14, {"OP-02": {"OP-02": OK, "OP-14": OK}, "OP-14": {"OP-14": OK, "OP-02": OK}}),
    "pos_cerrar": (esc_pos_cerrar, {"OP-02": {"OP-02": OK, "cerrar": OK}, "cerrar": {"cerrar": OK, "OP-02": OK}}),
    # El vinculo cambio de previsión: la version de su origen avanzo y la guarda de version gana (como en la base).
    "relectura_prevision": (esc_relectura_prevision, {"cv_a_p2": {"cv_a_p2": OK, "cv_a_p3": DESFASADA},
                                                      "cv_a_p3": {"cv_a_p3": OK, "cv_a_p2": DESFASADA}}),
    "relectura_hecho": (esc_relectura_hecho, {"cv_hecho": {"cv_hecho": OK, "cv_importe": DESFASADA},
                                              "cv_importe": {"cv_importe": OK, "cv_hecho": DESFASADA}}),
}
# CORR: el vinculo movido o retirado por el primero NO provoca reintento en el segundo: la guarda de version
# (precedencia de la base) decide antes de la relectura. ConjuntoCambiado queda como defensa.
SIN_REINTENTO_40001 = {("relectura_prevision", "cv_a_p2"), ("relectura_prevision", "cv_a_p3"),
                       ("relectura_hecho", "cv_hecho"), ("cv_retirar", "cv"), ("cv_retirar", "retirar"),
                       ("dos_retirar", "retirar_a"), ("dos_retirar", "retirar_b"),
                       ("op22r_op17", "OP-22"), ("op22r_op17", "OP-17")}

CASOS = [(nombre, primero) for nombre, (_, ordenes) in ESPERADO.items() for primero in ordenes]


@pytest.mark.parametrize("escenario, primero", CASOS, ids=[f"{n}-{p}-primero" for n, p in CASOS])
def test_f5_par_serial(escenario, primero, s, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    preparar, ordenes = ESPERADO[escenario]
    barreras, pasos, comprobar = preparar(s)
    segundo = next(n for n in pasos if n != primero)
    traza = serie(s.dsn, caplog, barreras, (primero, pasos[primero]), (segundo, pasos[segundo]))
    traza["escenario"] = escenario
    if comprobar:
        comprobar(traza)
    resultados = traza.pop("resultados")
    evidencia(f"F5_{escenario}_{primero}_primero", traza)
    assert traza["primero_espera"] and traza["segundo_espera"], traza
    assert not traza["vivos"], traza
    assert traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    assert {primero: traza[primero], segundo: traza[segundo]} == ordenes[primero], traza
    if (escenario, primero) in SIN_REINTENTO_40001:
        assert traza["reintentos_40001"] == 0, traza
    if escenario == "op17_op02":  # OP-02 propaga tambien el sucesor que OP-17 haya creado antes
        assert len(resultados["OP-02"].previsiones_propagadas) == (2 if primero == "OP-17" else 1), traza
