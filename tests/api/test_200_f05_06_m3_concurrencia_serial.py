# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_200_f05_06_m3_concurrencia_serial.py
# Ruta: tests/api/test_200_f05_06_m3_concurrencia_serial.py
# Descripcion: F05-06 M3 §A7 (F05 §51.4 M3 «gate de concurrencia propio»;
#   AJ-M3-DEC-05/07; M3-PRE P5 y M3-PRE2 P2). Bateria SERIAL y determinista,
#   FUERA de la suite general: solo con GAPTO_M3_CONCURRENCIA=1. Si
#   GAPTO_M3_EVIDENCIA apunta a una carpeta, cada escenario deja su JSON.
#   Nunca en paralelo.
#
#   Tecnica (la de R2-A/R2-B): el PRIMER paso se detiene DENTRO de su
#   transaccion en un punto fijo, ya con sus locks, mediante un envoltorio que
#   solo actua en el hilo de ese paso. Con el primero retenido se lanza el
#   segundo y se espera a que termine o quede bloqueado; despues se libera el
#   primero. Ambos ordenes. Cada orden tiene UN resultado esperado, equivalente
#   al serial, y un oraculo de estado final.
#   Pares, con las operaciones REALES del adaptador M3:
#     M3-PRE P5: (1) dos altas del actor del mismo tercero; (2) alta del actor
#     y OP-22 frente a desactivar el tercero; (3) OP-22 frente al writer de
#     afinidades; (4) cobro OP-14 frente a «Corregir reparto»; (5) pago OP-12B
#     frente a cobro OP-14 de la misma contraparte; (6) cobro/pago frente a M4
#     retirando la capacidad; (7) OP-22 con posicion frente a OP-21 (importe)
#     de otro hecho; (8) perdon frente a cobro de la misma posicion; (9) OP-03
#     de la cena frente al cobro de su derecho.
#     M3-PRE2 P2: ademas (3') editar la naturaleza del tercero; (5') registro
#     F05 (FOR SHARE) del mismo tercero; (6') OP-22 con posiciones frente a
#     OP-21P cambiando a la misma cuenta y frente al registro F05 con contexto
#     (advisory antes de la cuenta); (7') rollback forzado tras el alta del
#     actor: sin actor, sin hecho, sin auditoria.
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos;
#   ningun derecho por debajo de lo cobrado/perdonado; ningun huerfano.
# Version: 0.1.0 (F05-06 M3 §A7)
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

import f05_01_helpers as fh
import f05_05_helpers as x
import f05_06_m3_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_reparto as rep
from app.api.dto_reparto import IntencionCobroPago, IntencionCorregirReparto, IntencionGastoCompartido, IntencionPerdon
from app.api.dto_vs01 import IntencionGastoPagado
from app.core.contexto import ContextoOperacion
from app.core.errores import ErrorMotor

D = decimal.Decimal
LOGGER = "gapto.motor.transaccion"
FECHA_OP = dt.date(2026, 10, 10)
ORDENES = ["A-primero", "B-primero"]
OK = "OK"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M3_CONCURRENCIA=1)")


# ------------------------------------------------------------------ arnes
def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_M3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


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


def reintentos(caplog, sqlstate: str) -> int:
    return sum(1 for r in caplog.records if r.name == LOGGER and getattr(r, "sqlstate", None) == sqlstate)


class Paso(threading.Thread):
    """Un paso: resultado OK, codigo de RechazoRegistro/Rechazo, o codigo de ErrorMotor."""

    def __init__(self, nombre: str, fn) -> None:
        super().__init__(name=nombre, daemon=True)
        self.fn, self.resultado, self.codigo = fn, None, None

    def run(self) -> None:
        try:
            self.resultado = self.fn()
            codigo = getattr(self.resultado, "codigo", None)
            self.codigo = codigo if isinstance(codigo, str) else OK
        except ErrorMotor as exc:
            self.codigo = exc.codigo.value
        except Exception as exc:  # pragma: no cover - se registra
            self.codigo = f"{type(exc).__name__}: {exc}"


class Pausa:
    """Detiene el hilo `hilo` justo DESPUES de `modulo.atributo`, dentro de su transaccion."""

    def __init__(self, monkeypatch, modulo, atributo: str, hilo: str) -> None:
        self.llego, self.sigue = threading.Event(), threading.Event()
        original = getattr(modulo, atributo)

        def envoltorio(sesion, *args, **kwargs):
            resultado = original(sesion, *args, **kwargs)
            if threading.current_thread().name == hilo and not self.llego.is_set():
                self.llego.set()
                self.sigue.wait(90)
            return resultado

        monkeypatch.setattr(modulo, atributo, envoltorio)


def correr(monkeypatch, caplog, nombre: str, orden: str, a: tuple, b: tuple) -> dict:
    """a, b = (nombre, fn, (modulo, atributo) del punto de pausa). `orden` decide quien va primero."""
    primero, segundo = (a, b) if orden == "A-primero" else (b, a)
    dsn = h.dsn()
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    antes = deadlocks(dsn)
    pausa = Pausa(monkeypatch, *primero[2], hilo=primero[0])
    p1, p2 = Paso(primero[0], primero[1]), Paso(segundo[0], segundo[1])
    traza: dict = {"escenario": nombre, "orden": [primero[0], segundo[0]]}
    try:
        p1.start()
        traza["primero_retenido"] = pausa.llego.wait(30)
        p2.start()
        esperar(lambda: not p2.is_alive() or len(bloqueados(dsn)) >= 1, 30)
        traza["segundo_bloqueado"] = p2.is_alive()
    finally:
        pausa.sigue.set()
        for p in (p1, p2):
            p.join(60)
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    traza.update({p.name: p.codigo for p in (p1, p2)})
    traza.update({"vivos": [p.name for p in (p1, p2) if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"), "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    evidencia(f"{nombre}_{orden}", traza)
    assert traza["primero_retenido"], traza
    assert traza["vivos"] == [] and traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    return traza


def ctx(owner) -> ContextoOperacion:
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


# ------------------------------------------------------------------ operaciones reales
def op22(owner, cuerpo: dict):
    return lambda: rep.registrar_gasto_compartido(fh.unidad(), ctx(owner), IntencionGastoCompartido(**cuerpo))


def cobro(owner, entidad, cuenta, importe: str, operacion=rep.cobrar):
    return lambda: operacion(fh.unidad(), ctx(owner), entidad, IntencionCobroPago(
        intencion_id=uuid.uuid4(), importe=D(importe), cuenta_id=cuenta, fecha=FECHA_OP))


def perdon(owner, entidad, importe: str):
    return lambda: rep.perdonar(fh.unidad(), ctx(owner), entidad, IntencionPerdon(
        intencion_id=uuid.uuid4(), importe=D(importe), fecha=FECHA_OP))


def corregir(owner, hecho, partes: dict):
    def fn():
        return rep.corregir_reparto(fh.unidad(), ctx(owner), hecho, IntencionCorregirReparto(
            row_version=m.version(owner, hecho), motivo="M3 concurrencia",
            partes=[{"atribucion_id": a, "importe": D(i)} for a, i in partes.items()]))
    return fn


def desactivar_tercero(owner, tercero):
    from app.terceros import servicio as st
    v = m.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (tercero,))[0]
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: st.desactivar(s, tercero_id=tercero, row_version=v))


def editar_a_empresa(owner, tercero):
    from app.terceros import servicio as st
    v, nombre = m.uno(owner, "SELECT row_version, nombre FROM gapto.terceros WHERE id = %s", (tercero,))
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: st.editar(
        s, tercero_id=tercero, row_version=v, nombre=nombre, naturaleza="EMPRESA"))


def afinidad(owner, tercero, categoria):
    from app.afinidades import servicio as sa
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: sa.alta(
        s, afinidad_id=uuid.uuid4(), tercero_id=tercero, categoria_id=categoria))


def registro_f05(owner, cuenta, **cambios):
    from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
    cuerpo = h.intencion(cuenta, fecha_hecho="2026-10-05", **{k: str(v) for k, v in cambios.items()})
    return lambda: registrar_gasto_pagado(fh.unidad(), ctx(owner), IntencionGastoPagado(**cuerpo))


def retirar_capacidad(owner, cuenta, capacidad: str):
    from app.capacidades import servicio as cap
    v = m.uno(owner, "SELECT row_version FROM gapto.cuentas WHERE id = %s", (cuenta,))[0]
    return lambda: fh.unidad().ejecutar(ctx(owner), lambda s: cap.desactivar(
        s, cuenta_id=cuenta, capacidad=capacidad, row_version=v))


def anular(owner, hecho):
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla
    v = m.version(owner, hecho)
    return lambda: HechosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla).anular_hecho(
        ctx(owner), hecho_id=hecho, row_version_esperada=v, motivo_anulacion="duplicado")


# Puntos de pausa (ultimo lock antes de escribir de cada ruta).
def _pt_actor():
    from app.actores import servicio
    return servicio, "actor_de_tercero"


def _pt_tercero():
    from app.terceros import repositorio
    return repositorio, "leer"


def _pt_posiciones():
    from app.repositories import posiciones_repository
    return posiciones_repository, "bloquear_posiciones"


def _pt_cuenta_m4():
    from app.capacidades import servicio
    return servicio, "_bloquear_cuenta"


def _pt_registro_tercero():
    from app.api import ejecucion_gasto_pagado
    return ejecucion_gasto_pagado, "validar_tercero"


def _pt_registro_cuenta():
    from app.api import ejecucion_gasto_pagado
    return ejecucion_gasto_pagado, "bloquear_cuenta"


def _pt_op21p_cuenta():
    from app.api import ejecucion_correccion
    return ejecucion_correccion, "bloquear_cuentas"


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    tania, carlos = m.persona(cli, "Tania"), m.persona(cli, "Carlos")
    return owner, actor, cli, cta, ahorro, tania, carlos


def _cena(t, **kw):
    owner, _, cli, cta, _, tania, carlos = t
    c, r = m.cena(cli, cta, tania, carlos, **kw)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    return hecho, m.entidad_de_posicion(owner, hecho)


def _nuevo_gasto(cuenta, persona, *, me_debe="SI"):
    return m.cuerpo("20.00", pagado_por=m.con_cuenta(cuenta), reparto=m.repartir("10.00", (persona, "10.00", me_debe)))


# ================================================================== M3-PRE P5 / M3-PRE2 P2
@pytest.mark.parametrize("orden", ORDENES)
def test_p1_dos_altas_simultaneas_del_mismo_actor(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    a, b = _nuevo_gasto(cta, simon), _nuevo_gasto(cta, simon)
    traza = correr(monkeypatch, caplog, "p1_altas_actor", orden,
                   ("OP22-A", op22(owner, a), _pt_actor()), ("OP22-B", op22(owner, b), _pt_actor()))
    assert (traza["OP22-A"], traza["OP22-B"]) == (OK, OK), traza
    assert traza["segundo_bloqueado"] is True, traza  # espera en la UNIQUE, no en una fila inexistente
    assert m.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (simon,))[0] == 1
    assert m.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'actores_financieros' "
                        "AND registro_id = %s", (m.actor_de(owner, simon),))[0] == 1


@pytest.mark.parametrize("orden", ORDENES)
def test_p2_alta_del_actor_frente_a_desactivar_el_tercero(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    cuerpo = _nuevo_gasto(cta, simon)
    traza = correr(monkeypatch, caplog, "p2_actor_vs_desactivar", orden,
                   ("OP22", op22(owner, cuerpo), _pt_actor()),
                   ("DESACTIVAR", desactivar_tercero(owner, simon), _pt_tercero()))
    assert traza["segundo_bloqueado"] is True, traza
    hecho = m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (cuerpo["intencion_id"],))[0]
    if orden == "A-primero":
        assert (traza["OP22"], traza["DESACTIVAR"], hecho) == (OK, OK, 1), traza
        assert m.actor_de(owner, simon) is not None
    else:
        assert (traza["OP22"], traza["DESACTIVAR"], hecho) == ("TERCERO_NO_DISPONIBLE", OK, 0), traza
        assert m.actor_de(owner, simon) is None  # sin huerfanos
    assert m.uno(owner, "SELECT enabled FROM gapto.terceros WHERE id = %s", (simon,))[0] is False


@pytest.mark.parametrize("orden", ORDENES)
def test_p3_alta_del_actor_frente_a_editar_la_naturaleza(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    cuerpo = _nuevo_gasto(cta, simon)
    traza = correr(monkeypatch, caplog, "p3_actor_vs_editar", orden,
                   ("OP22", op22(owner, cuerpo), _pt_actor()),
                   ("EDITAR", editar_a_empresa(owner, simon), _pt_tercero()))
    assert traza["segundo_bloqueado"] is True, traza
    if orden == "A-primero":
        assert (traza["OP22"], traza["EDITAR"]) == (OK, OK), traza
    else:
        assert (traza["OP22"], traza["EDITAR"]) == ("TERCERO_NO_PERSONA", OK), traza
        assert m.actor_de(owner, simon) is None


@pytest.mark.parametrize("orden", ORDENES)
def test_p4_op22_frente_al_writer_de_afinidades(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    ropa = x.categoria(owner, "Ropa")
    traza = correr(monkeypatch, caplog, "p4_op22_vs_afinidad", orden,
                   ("OP22", op22(owner, _nuevo_gasto(cta, simon)), _pt_actor()),
                   ("AFINIDAD", afinidad(owner, simon, ropa), _pt_tercero()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza["OP22"], traza["AFINIDAD"]) == (OK, OK), traza


@pytest.mark.parametrize("orden", ORDENES)
def test_p5_alta_del_actor_frente_al_registro_f05_del_mismo_tercero(t, monkeypatch, caplog, orden):
    """FOR SHARE frente a FOR SHARE: compatibles; ninguno espera al otro."""
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    traza = correr(monkeypatch, caplog, "p5_actor_vs_registro_f05", orden,
                   ("OP22", op22(owner, _nuevo_gasto(cta, simon, me_debe="NO")), _pt_actor()),
                   ("REGISTRO", registro_f05(owner, cta, tercero_id=simon), _pt_registro_tercero()))
    assert (traza["OP22"], traza["REGISTRO"]) == (OK, OK), traza


@pytest.mark.parametrize("orden", ORDENES)
def test_p6_cobro_frente_a_corregir_reparto(t, monkeypatch, caplog, orden):
    owner, yo, cli, cta, _, tania, _ = t
    hecho, entidad = _cena(t)
    a_yo, a_tania = m.atribucion_de(owner, hecho, yo), m.atribucion_de(owner, hecho, m.actor_de(owner, tania))
    traza = correr(monkeypatch, caplog, "p6_cobro_vs_corregir", orden,
                   ("COBRO", cobro(owner, entidad, cta, "5.00"), _pt_posiciones()),
                   ("CORREGIR", corregir(owner, hecho, {a_yo: "9.50", a_tania: "20.00"}), _pt_posiciones()))
    assert traza["segundo_bloqueado"] is True, traza
    # Equivalente al serial: el derecho queda en 20 y lo cobrado (5) se descuenta; nada se pierde.
    assert traza["COBRO"] == OK, traza
    if traza["CORREGIR"] == OK:
        assert m.efectos(owner, hecho)["DERECHO_COBRO"] == D("20.0000")
        assert m.pendiente(cli, tania).json()["te_debe"] == "15.00"
    else:  # leyo la version antes de que el cobro tocara la raiz
        assert traza["CORREGIR"] == "VERSION_DESFASADA", traza
        assert m.pendiente(cli, tania).json()["te_debe"] == "10.00"


@pytest.mark.parametrize("orden", ORDENES)
def test_p7_pago_frente_a_cobro_de_la_misma_contraparte(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, tania, _ = t
    _, derecho = _cena(t)
    c, _ = m.peluqueria(cli, tania)
    obligacion = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    traza = correr(monkeypatch, caplog, "p7_pago_vs_cobro", orden,
                   ("PAGO", cobro(owner, obligacion, cta, "15.00", rep.pagar), _pt_posiciones()),
                   ("COBRO", cobro(owner, derecho, cta, "15.00"), _pt_posiciones()))
    assert (traza["PAGO"], traza["COBRO"]) == (OK, OK), traza
    assert m.pendiente(cli, tania).json()["neto_estado"] == "SIN_POSICIONES"


@pytest.mark.parametrize("operacion", ["cobro", "pago"])
@pytest.mark.parametrize("orden", ORDENES)
def test_p8_cobro_o_pago_frente_a_m4_retirando_la_capacidad(t, monkeypatch, caplog, orden, operacion):
    owner, _, cli, cta, _, tania, _ = t
    if operacion == "cobro":
        _, entidad = _cena(t)
        fn, capacidad = cobro(owner, entidad, cta, "5.00"), "RECIBIR_INGRESO"
    else:
        c, _ = m.peluqueria(cli, tania)
        entidad = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
        fn, capacidad = cobro(owner, entidad, cta, "5.00", rep.pagar), "PAGAR_GASTO"
    traza = correr(monkeypatch, caplog, f"p8_{operacion}_vs_m4", orden,
                   ("OPERACION", fn, _pt_posiciones()), ("M4", retirar_capacidad(owner, cta, capacidad), _pt_cuenta_m4()))
    assert traza["segundo_bloqueado"] is True, traza
    if orden == "A-primero":
        assert (traza["OPERACION"], traza["M4"]) == (OK, OK), traza
    else:
        assert (traza["OPERACION"], traza["M4"]) == ("CUENTA_SIN_CAPACIDAD", OK), traza


@pytest.mark.parametrize("orden", ORDENES)
def test_p9_op22_con_posicion_frente_a_op21_importe_de_otro_hecho(t, monkeypatch, caplog, orden):
    """IL5 en M3: ambas toman el advisory INVERSIONES antes que nada y se serializan."""
    owner, yo, cli, cta, _, tania, _ = t
    hecho, _ = _cena(t)
    a_yo, a_tania = m.atribucion_de(owner, hecho, yo), m.atribucion_de(owner, hecho, m.actor_de(owner, tania))
    simon = m.persona(cli, "Simón")
    traza = correr(monkeypatch, caplog, "p9_op22_vs_op21", orden,
                   ("OP22", op22(owner, _nuevo_gasto(cta, simon)), _pt_actor()),
                   ("CORREGIR", corregir(owner, hecho, {a_yo: "9.50", a_tania: "20.00"}), _pt_posiciones()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza["OP22"], traza["CORREGIR"]) == (OK, OK), traza


@pytest.mark.parametrize("orden", ORDENES)
def test_p10_perdon_frente_a_cobro_de_la_misma_posicion(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, tania, _ = t
    _, entidad = _cena(t)
    traza = correr(monkeypatch, caplog, "p10_perdon_vs_cobro", orden,
                   ("PERDON", perdon(owner, entidad, "10.00"), _pt_posiciones()),
                   ("COBRO", cobro(owner, entidad, cta, "10.00"), _pt_posiciones()))
    assert traza["segundo_bloqueado"] is True, traza
    primero, segundo = traza["orden"]
    assert traza[primero] == OK and traza[segundo] == "EXCEDE_SALDO_DEL_DERECHO", traza
    assert m.pendiente(cli, tania).json()["te_debe"] == "5.00"  # nunca por debajo de cero


@pytest.mark.parametrize("orden", ORDENES)
def test_p11_op03_de_la_cena_frente_al_cobro_de_su_derecho(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, _, tania, _ = t
    hecho, entidad = _cena(t)
    traza = correr(monkeypatch, caplog, "p11_op03_vs_cobro", orden,
                   ("OP03", anular(owner, hecho), _pt_posiciones()),
                   ("COBRO", cobro(owner, entidad, cta, "5.00"), _pt_posiciones()))
    assert (traza["OP03"], traza["COBRO"]) == ("HECHO_CON_REALIDAD_ASOCIADA", OK), traza
    assert m.uno(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0] == "ACTIVO"


@pytest.mark.parametrize("orden", ORDENES)
def test_p12_op22_con_posiciones_frente_al_registro_f05_con_contexto(t, monkeypatch, caplog, orden):
    """R-M3PRE2-01: los dos toman el advisory ANTES de la cuenta: se serializan sin ciclo."""
    owner, _, cli, cta, _, _, _ = t
    simon = m.persona(cli, "Simón")
    viaje = x.contexto(cli, "Viaje")
    traza = correr(monkeypatch, caplog, "p12_op22_vs_registro_contexto", orden,
                   ("OP22", op22(owner, _nuevo_gasto(cta, simon)), _pt_actor()),
                   ("REGISTRO", registro_f05(owner, cta, contexto_id=viaje), _pt_registro_cuenta()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza["OP22"], traza["REGISTRO"]) == (OK, OK), traza


@pytest.mark.parametrize("orden", ORDENES)
def test_p13_op22_con_posiciones_frente_a_op21p_a_la_misma_cuenta(t, monkeypatch, caplog, orden):
    owner, _, cli, cta, ahorro, _, _ = t
    from app.api.ejecucion_correccion import corregir_pago
    from app.services.correccion_tesoreria_service import DatosCorreccionPago

    simon = m.persona(cli, "Simón")
    otra = h.crear_cuenta(owner, [(t[1], 100)])
    # Sin aportacion PARTICIPACION_CUENTA: si no, cambiar de cuenta exige decision (R2-B B47).
    r = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(otra, fecha_hecho="2026-10-05",
                                                                   financiacion=h.NO_DETERMINADA), headers=h.AUTH)
    assert r.status_code == 200, r.text
    gasto = uuid.UUID(r.json()["hecho_id"])
    mov = m.uno(owner, "SELECT c.movimiento_tesoreria_id FROM gapto.hecho_movimientos_tesoreria c "
                       "WHERE c.hecho_id = %s", (gasto,))[0]

    def op21p():
        datos = DatosCorreccionPago(
            hecho_id=gasto, row_version_esperada=m.version(owner, gasto),
            movimiento_row_version_esperada=m.uno(owner, "SELECT row_version FROM gapto.movimientos_tesoreria "
                                                         "WHERE id = %s", (mov,))[0],
            motivo="cuenta equivocada", error_de_registro=True, cuenta_id=cta)
        return corregir_pago(fh.unidad(), ctx(owner), datos)

    traza = correr(monkeypatch, caplog, "p13_op22_vs_op21p", orden,
                   ("OP22", op22(owner, _nuevo_gasto(cta, simon)), _pt_actor()),
                   ("OP21P", op21p, _pt_op21p_cuenta()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza["OP22"], traza["OP21P"]) == (OK, OK), traza


def test_p14_rollback_forzado_tras_el_alta_del_actor_sin_huerfanos(t, monkeypatch):
    owner, _, cli, cta, _, _, _ = t
    from app.services import compuesto_service

    simon = m.persona(cli, "Simón")
    antes = m.huella(owner)

    def falla(self, contexto, datos):
        raise RuntimeError("fallo inyectado tras el alta del actor")
    monkeypatch.setattr(compuesto_service.HechosCompuestosService, "registrar_hecho_compuesto", falla)
    with pytest.raises(ErrorMotor):  # la UdT lo clasifica como INTERNO y hace rollback completo
        op22(owner, _nuevo_gasto(cta, simon))()
    assert m.huella(owner) == antes
    assert m.actor_de(owner, simon) is None
