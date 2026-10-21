# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_205_f05_06_m5_concurrencia_serial.py
# Ruta: tests/api/test_205_f05_06_m5_concurrencia_serial.py
# Descripcion: F05-06 M5 §A7 (F05 §59 F05-D044 decision 11; D-M5-12;
#   AJ-M5-DEC-06; dictamen Q10). Bateria SERIAL y determinista, FUERA de la
#   suite general: solo con GAPTO_M5_CONCURRENCIA=1. Si GAPTO_M5_EVIDENCIA
#   apunta a una carpeta, cada escenario deja su JSON. Nunca en paralelo.
#
#   Tecnica (la de M3 y R2): el PRIMER paso se detiene DENTRO de su
#   transaccion justo despues de su ultimo lock (envoltorio que solo actua en
#   su hilo); con el primero retenido se lanza el segundo y se espera a que
#   termine o quede bloqueado; despues se libera el primero. Ambos ordenes.
#   Cada orden tiene UN resultado esperado y un ORACULO DE ESTADO FINAL.
#   Pares (D-M5-12, con las operaciones REALES del adaptador M5):
#     P1 OP-17 / OP-17, misma prevision y hechos distintos;
#     P2 OP-17 / OP-17, mismo hecho y previsiones distintas (G-R1-C);
#     P3 omitir / OP-17, prevision SIN regla y CON regla (RODANTE);
#     P4 omitir / OP-22 + prevision, sin y con regla;
#     P5 OP-10 + OP-17 / omitir (atomicidad: un rechazo de OP-17 revierte las
#        dos patas);
#     P6 OP-17 / OP-03 y OP-03P sobre el mismo hecho, sobre ESTE head (R2-C);
#     P7 OP-22 + prevision / OP-17 suelto, misma prevision;
#     P8 «desactivacion de regla»: NO REPRESENTABLE (no existe la operacion;
#        R-M5PRE-04). Se declara en el handoff y no se simula;
#     P9 OP-17 / corregir_vinculo sobre el mismo hecho, ACTIVO y ANULADO
#        (guarda del MANT).
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos;
#   nunca un vinculo sobre una OMITIDA ni una OMITIDA con realidad ACTIVA;
#   nunca Σ vinculado > importe_total de un hecho; nunca medio registro.
# Version: 0.1.0 (F05-06 M5 §A7)
# ============================================================

from __future__ import annotations

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
import f05_06_m5_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_anulacion
from app.api import ejecucion_prevision as ejp
from app.api.dto_prevision import IntencionOmitir, IntencionVincular
from app.api.dto_registro import IntencionTransferencia
from app.api.dto_vs01 import IntencionGastoPagado
from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
from app.core.contexto import ContextoOperacion
from app.core.errores import ErrorMotor
from app.repositories import previsiones_repository as repo_prev
from app.repositories import relaciones_repository as repo_rel
from app.services import previsiones_service as serv_prev

D = decimal.Decimal
LOGGER = "gapto.motor.transaccion"
ORDENES = ["A-primero", "B-primero"]
OK = "OK"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M5_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M5_CONCURRENCIA=1)")


# ------------------------------------------------------------------ arnes (el de M3)
def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_M5_EVIDENCIA")
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

        def envoltorio(*args, **kwargs):
            resultado = original(*args, **kwargs)
            if threading.current_thread().name == hilo and not self.llego.is_set():
                self.llego.set()
                self.sigue.wait(90)
            return resultado

        monkeypatch.setattr(modulo, atributo, envoltorio)


def correr(monkeypatch, caplog, nombre: str, orden: str, a: tuple, b: tuple) -> dict:
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
    time.sleep(1.1)
    traza.update({p.name: p.codigo for p in (p1, p2)})
    traza.update({"vivos": [p.name for p in (p1, p2) if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"), "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    assert traza["primero_retenido"], traza
    assert traza["vivos"] == [] and traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    return traza


def ctx(owner) -> ContextoOperacion:
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


# ------------------------------------------------------------------ operaciones reales del adaptador
def op17(owner, pid, hecho, importe: str, marcar: bool = True, version=None):
    v = version or m.version(owner, pid)
    return lambda: ejp.vincular(fh.unidad(), ctx(owner), pid, IntencionVincular(
        intencion_id=uuid.uuid4(), row_version=v, hecho_id=hecho, importe_a_vincular=D(importe),
        marcar_realizada=marcar))


def omitir(owner, pid):
    v = m.version(owner, pid)
    return lambda: ejp.omitir(fh.unidad(), ctx(owner), pid, IntencionOmitir(intencion_id=uuid.uuid4(), row_version=v))


def op22(owner, cuenta, pid, importe: str, marcar: bool = True):
    cuerpo = h.intencion(cuenta, importe=importe, fecha_hecho="2026-10-07")
    cuerpo["prevision"] = {"prevision_id": str(pid), "row_version": m.version(owner, pid), "marcar_realizada": marcar}
    i = IntencionGastoPagado(**cuerpo)
    return i.intencion_id, lambda: registrar_gasto_pagado(fh.unidad(), ctx(owner), i, m.x.reloj())


def op10_op17(owner, origen, destino, pid, importe: str):
    i = IntencionTransferencia(intencion_id=uuid.uuid4(), importe=D(importe), moneda="EUR", fecha_hecho="2026-10-07",
                               cuenta_origen_id=origen, cuenta_destino_id=destino,
                               prevision={"prevision_id": pid, "row_version": m.version(owner, pid),
                                          "marcar_realizada": True})
    return i.intencion_id, lambda: ejp.registrar_transferencia_prevista(fh.unidad(), ctx(owner), i, m.x.reloj())


def op03(owner, hecho):
    from app.services.hechos_service import HechosService

    v = m.uno(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0]
    return lambda: HechosService(fh.unidad(), impacto_ancla=serv_prev.impacto_correccion_ancla).anular_hecho(
        ctx(owner), hecho_id=hecho, row_version_esperada=v, motivo_anulacion="duplicado")


def op03p(owner, hecho):
    from app.services.anulacion_tesoreria_service import DatosAnulacionRegistro

    v = m.uno(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0]
    movs = dict(m.leer(owner, "SELECT mv.id, mv.row_version FROM gapto.hecho_movimientos_tesoreria c JOIN "
                              "gapto.movimientos_tesoreria mv ON mv.id = c.movimiento_tesoreria_id WHERE c.hecho_id = %s",
                       (hecho,)))
    return lambda: ejecucion_anulacion.anular_registro(fh.unidad(), ctx(owner), DatosAnulacionRegistro(
        hecho_id=hecho, row_version_esperada=v, movimientos_row_version_esperadas=movs, motivo="duplicado",
        movimiento_en_banco=False))


def corregir_vinculo(owner, vinculo, pid, importe: str):
    v = m.version(owner, pid)
    return lambda: serv_prev.PrevisionesService(fh.unidad()).corregir_vinculo(
        ctx(owner), vinculo_id=vinculo, nuevo_importe=D(importe), versiones_esperadas={pid: v}, motivo="M5 P9")


# Puntos de pausa: el ultimo lock de cada ruta antes de escribir.
PT_OP17 = (repo_prev, "bloquear_prevision")       # OP-17: hecho -> regla -> prevision FU
PT_OMITIR = (repo_prev, "tocar_prevision")        # omitir: [regla FU ->] UPDATE con version
PT_OP03 = (serv_prev, "aplicar_impacto_ancla")    # OP-03: hecho -> reglas -> previsiones
PT_OP03P = (ejecucion_anulacion, "aplicar_impacto_ancla")
PT_HECHO = (repo_rel, "bloquear_hechos")          # rutas que se rechazan bajo el lock del hecho


def _gasto(cli, cta, importe: str, tercero=None, fecha="2026-10-03"):
    return m.x.gasto(cli, cta, fecha=fecha, importe=importe, tercero_id=tercero)


def _sin_pago(owner, importe: str):
    """Hecho GASTO sin tesoreria (OP-22 de motor), anulable por OP-03."""
    return m.x.hecho_motor(owner, [("GASTO", importe, "NO_DISPONIBLE", None, [])], fecha="2026-10-03", total=importe)


def _vincular_motor(owner, pid, hecho, importe: str):
    from app.core.modelos_prevision import DatosVinculo

    serv_prev.PrevisionesService(fh.unidad()).vincular_realidad(
        ctx(owner), prevision_id=pid, row_version_esperada=m.version(owner, pid),
        datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho, importe_asignado=D(importe), marcar_realizada=False))


def _sin_omitida_con_realidad(owner):
    """Oraculo AJ-M5-DEC-06: ni vinculo sobre OMITIDA ni OMITIDA con realidad ACTIVA."""
    return m.uno(owner, "SELECT count(*) FROM gapto.prevision_hechos pv JOIN gapto.previsiones p ON p.id = "
                        "pv.prevision_id WHERE p.estado = 'OMITIDA'")[0] == 0


def _sin_exceso(owner):
    return m.uno(owner, "SELECT count(*) FROM (SELECT h.id FROM gapto.hechos_financieros h JOIN gapto.prevision_hechos "
                        "pv ON pv.hecho_id = h.id GROUP BY h.id, h.importe_total "
                        "HAVING sum(pv.importe_asignado) > h.importe_total) x")[0] == 0


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    return owner, cli, cta, ahorro


# ------------------------------------------------------------------ P1
@pytest.mark.parametrize("orden", ORDENES)
def test_p1_op17_op17_misma_prevision(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    luz = m.prevision(owner, "Luz", importe="74.00")
    h1, h2 = _gasto(cli, cta, "74.00"), _gasto(cli, cta, "75.00")
    tr = correr(monkeypatch, caplog, "P1", orden, ("A", op17(owner, luz, h1, "74.00"), PT_OP17),
                ("B", op17(owner, luz, h2, "75.00"), PT_OP17))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "VERSION_DESFASADA"), tr
    assert len(m.vinculos(owner, luz)) == 1 and m.estado(owner, luz) == "REALIZADA"
    evidencia(f"P1_{orden}", {**tr, "vinculos": m.vinculos(owner, luz)})


# ------------------------------------------------------------------ P2
@pytest.mark.parametrize("orden", ORDENES)
def test_p2_op17_op17_mismo_hecho(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    a, b = m.prevision(owner, "A", importe="74.00"), m.prevision(owner, "B", importe="74.00")
    hid = _gasto(cli, cta, "74.00")
    tr = correr(monkeypatch, caplog, "P2", orden, ("A", op17(owner, a, hid, "74.00"), PT_OP17),
                ("B", op17(owner, b, hid, "74.00"), PT_OP17))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "PORCION_DE_REALIDAD_EXCEDIDA"), tr
    assert _sin_exceso(owner)
    assert m.uno(owner, "SELECT count(*) FROM gapto.prevision_hechos WHERE hecho_id = %s", (hid,))[0] == 1
    evidencia(f"P2_{orden}", tr)


# ------------------------------------------------------------------ P3 / P4
def _prevision_p3(owner, cta, con_regla: bool):
    if con_regla:
        regla, cabeza = m.rodante(owner, cuenta_salida=cta, desde="2026-10-01", importe="74.00")
        return regla, cabeza
    return None, m.prevision(owner, "Luz", importe="74.00")


@pytest.mark.parametrize("con_regla", [False, True], ids=["sin_regla", "con_regla"])
@pytest.mark.parametrize("orden", ORDENES)
def test_p3_omitir_frente_a_op17(t, monkeypatch, caplog, orden, con_regla):
    owner, cli, cta, _ = t
    regla, pid = _prevision_p3(owner, cta, con_regla)
    hid = _gasto(cli, cta, "74.00")
    tr = correr(monkeypatch, caplog, "P3", orden, ("A", omitir(owner, pid), PT_OMITIR),
                ("B", op17(owner, pid, hid, "74.00"), PT_OP17))
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert m.estado(owner, pid) == "OMITIDA" and m.vinculos(owner, pid) == []
    else:
        assert tr["B"] == OK and tr["A"] in ("VERSION_DESFASADA", "ESTADO_PREVISION_INCOMPATIBLE"), tr
        assert m.estado(owner, pid) == "REALIZADA" and len(m.vinculos(owner, pid)) == 1
    assert _sin_omitida_con_realidad(owner)
    if regla is not None:  # exactamente un sucesor ABIERTO de la cadena (nunca dos)
        assert [e for _, e, _ in m.previsiones_de_regla(owner, regla)].count("ABIERTA") == 1
    evidencia(f"P3_{'regla' if con_regla else 'sin_regla'}_{orden}", {**tr, "estado": m.estado(owner, pid)})


@pytest.mark.parametrize("con_regla", [False, True], ids=["sin_regla", "con_regla"])
@pytest.mark.parametrize("orden", ORDENES)
def test_p4_omitir_frente_a_op22_con_prevision(t, monkeypatch, caplog, orden, con_regla):
    owner, cli, cta, _ = t
    regla, pid = _prevision_p3(owner, cta, con_regla)
    hid, registrar = op22(owner, cta, pid, "74.00")
    base_hechos = m.huella(owner)[0]
    tr = correr(monkeypatch, caplog, "P4", orden, ("A", omitir(owner, pid), PT_OMITIR),
                ("B", registrar, PT_OP17))
    existe = m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0]
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert m.estado(owner, pid) == "OMITIDA" and existe == 0 and m.huella(owner)[0] == base_hechos
    else:
        assert tr["B"] == OK and tr["A"] in ("VERSION_DESFASADA", "ESTADO_PREVISION_INCOMPATIBLE"), tr
        assert m.estado(owner, pid) == "REALIZADA" and existe == 1
    assert _sin_omitida_con_realidad(owner)
    if regla is not None:
        assert [e for _, e, _ in m.previsiones_de_regla(owner, regla)].count("ABIERTA") == 1
    evidencia(f"P4_{'regla' if con_regla else 'sin_regla'}_{orden}", tr)


# ------------------------------------------------------------------ P5
@pytest.mark.parametrize("orden", ORDENES)
def test_p5_op10_op17_frente_a_omitir(t, monkeypatch, caplog, orden):
    owner, cli, cta, ahorro = t
    pid = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00")
    hid, transferir = op10_op17(owner, cta, ahorro, pid, "500.00")
    s_cta, s_aho = m.saldo(owner, cta), m.saldo(owner, ahorro)
    tr = correr(monkeypatch, caplog, "P5", orden, ("A", transferir, PT_OP17), ("B", omitir(owner, pid), PT_OMITIR))
    existe = m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0]
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert existe == 1 and m.estado(owner, pid) == "REALIZADA"
        assert (m.saldo(owner, cta) - s_cta, m.saldo(owner, ahorro) - s_aho) == (D(-500), D(500))
    else:
        assert (tr["B"], tr["A"]) == (OK, "VERSION_DESFASADA"), tr
        # Un rechazo de OP-17 revierte las DOS patas de OP-10.
        assert existe == 0 and m.estado(owner, pid) == "OMITIDA"
        assert (m.saldo(owner, cta), m.saldo(owner, ahorro)) == (s_cta, s_aho)
        assert m.uno(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id IN (%s, %s)", (
            uuid.uuid5(hid, "gapto.f05.transferencia.movimiento.salida"),
            uuid.uuid5(hid, "gapto.f05.transferencia.movimiento.entrada")))[0] == 0
    assert _sin_omitida_con_realidad(owner)
    evidencia(f"P5_{orden}", tr)


# ------------------------------------------------------------------ P6
@pytest.mark.parametrize("anulacion", ["OP-03", "OP-03P"])
@pytest.mark.parametrize("orden", ORDENES)
def test_p6_op17_frente_a_op03_y_op03p(t, monkeypatch, caplog, orden, anulacion):
    owner, cli, cta, _ = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    # OP-03 solo anula un hecho sin tesoreria (HECHO_CON_REALIDAD_ASOCIADA); el pagado va por OP-03P.
    hid = _sin_pago(owner, "74.00") if anulacion == "OP-03" else _gasto(cli, cta, "74.00")
    fn, pt = (op03(owner, hid), PT_OP03) if anulacion == "OP-03" else (op03p(owner, hid), PT_OP03P)
    tr = correr(monkeypatch, caplog, f"P6_{anulacion}", orden, ("A", op17(owner, pid, hid, "74.00"), PT_OP17),
                ("B", fn, pt))
    estado_hecho = m.uno(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0]
    assert estado_hecho == "ANULADO"
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, OK), tr
        assert len(m.vinculos(owner, pid)) == 1 and m.detalle(cli, pid)["estado_derivado"] == \
            "REALIZADA_SIN_REALIDAD_ACTIVA"
    else:
        assert (tr["B"], tr["A"]) == (OK, "OPERACION_NO_PERMITIDA_EN_ESTADO"), tr
        assert m.vinculos(owner, pid) == [] and m.estado(owner, pid) == "ABIERTA"
    evidencia(f"P6_{anulacion}_{orden}", tr)


# ------------------------------------------------------------------ P7
@pytest.mark.parametrize("orden", ORDENES)
def test_p7_op22_con_prevision_frente_a_op17(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    otro = _gasto(cli, cta, "74.00")
    hid, registrar = op22(owner, cta, pid, "81.37")
    tr = correr(monkeypatch, caplog, "P7", orden, ("A", registrar, PT_OP17), ("B", op17(owner, pid, otro, "74.00"),
                                                                              PT_OP17))
    ganador, perdedor = ("A", "B") if orden == "A-primero" else ("B", "A")
    assert (tr[ganador], tr[perdedor]) == (OK, "VERSION_DESFASADA"), tr
    existe = m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0]
    assert existe == (1 if orden == "A-primero" else 0)  # el OP-22 perdedor no deja medio registro
    assert len(m.vinculos(owner, pid)) == 1 and m.estado(owner, pid) == "REALIZADA"
    evidencia(f"P7_{orden}", tr)


# ------------------------------------------------------------------ P9
@pytest.mark.parametrize("orden", ORDENES)
def test_p9_op17_frente_a_corregir_vinculo_hecho_activo(t, monkeypatch, caplog, orden):
    owner, cli, cta, _ = t
    a, b = m.prevision(owner, "A", importe="40.00"), m.prevision(owner, "B", importe="60.00")
    hid = _gasto(cli, cta, "100.00")
    m.vincular(cli, owner, a, hid, "100.00", False)  # A tiene toda la porcion; B la espera tras corregir
    vid = m.uno(owner, "SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (a,))[0]
    # A corrige su vinculo a 40 (libera 60); B quiere vincular los 60 que vio.
    tr = correr(monkeypatch, caplog, "P9", orden, ("A", corregir_vinculo(owner, vid, a, "40.00"), PT_OP17),
                ("B", op17(owner, b, hid, "60.00"), PT_OP17))
    if orden == "A-primero":
        assert (tr["A"], tr["B"]) == (OK, OK), tr
        assert m.vinculos(owner, b) == [(hid, D("60.0000"))]
    else:
        assert (tr["B"], tr["A"]) == ("PORCION_DE_REALIDAD_EXCEDIDA", OK), tr
        assert m.vinculos(owner, b) == []
    assert _sin_exceso(owner)
    evidencia(f"P9_activo_{orden}", tr)


@pytest.mark.parametrize("orden", ORDENES)
def test_p9_op17_frente_a_corregir_vinculo_hecho_anulado(t, monkeypatch, caplog, orden):
    """MANT DEU-F04-VINCULO-ANULADO: ni el importe de un vinculo que sigue en un hecho
    ANULADO se corrige, ni un hecho ANULADO satisface una prevision."""
    owner, cli, cta, _ = t
    a, b = m.prevision(owner, "A", importe="40.00"), m.prevision(owner, "B", importe="60.00")
    hid = _sin_pago(owner, "100.00")
    _vincular_motor(owner, a, hid, "40.00")  # estado de partida: 40 de 100 (la API exige toda la porcion)
    vid = m.uno(owner, "SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (a,))[0]
    op03(owner, hid)()
    antes = m.huella(owner)
    tr = correr(monkeypatch, caplog, "P9_anulado", orden, ("A", corregir_vinculo(owner, vid, a, "70.00"), PT_HECHO),
                ("B", op17(owner, b, hid, "60.00"), PT_HECHO))
    assert (tr["A"], tr["B"]) == ("OPERACION_NO_PERMITIDA_EN_ESTADO", "OPERACION_NO_PERMITIDA_EN_ESTADO"), tr
    assert m.huella(owner) == antes
    evidencia(f"P9_anulado_{orden}", tr)
