# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_201_f05_06_m3_orden_locks.py
# Ruta: tests/api/test_201_f05_06_m3_orden_locks.py
# Descripcion: F05-06 M3 §A7 · prueba POSITIVA del orden de locks (F05-D043
#   §57.1.3; AJ-M3-DEC-05; M3-PRE2 P4). Sustituye a la prueba negativa
#   DEU-F04-OP12A (saldada por F04-D061). Fuera de la suite general: solo con
#   GAPTO_M3_CONCURRENCIA=1. Nunca en paralelo.
#
#   Tecnica: la operacion REAL se detiene, en el mismo hilo y en serie, en
#   puntos fijos (P1 tras el advisory INVERSIONES, P2 tras el ultimo lock
#   intermedio y P3 tras el lock de las posiciones). En cada pausa, OTRA sesion
#   sondea sin esperar: el advisory con pg_try_advisory_xact_lock, y la cuenta,
#   el hecho y la posicion con FOR UPDATE NOWAIT (55P03 = retenido); ademas se
#   captura pg_locks de la sesion retenida. Oraculo: en cada pausa, lo
#   retenido es un PREFIJO del orden canonico
#     advisory -> cuenta -> tercero/actor -> hecho -> posiciones
#   (M3-PRE2 P2), y nada posterior se toma antes que algo anterior.
#   Operaciones: OP-22 con posicion (gasto compartido), OP-14 (cobro), OP-12B
#   (pago), condonacion (perdon) y OP-21 («Corregir reparto»).
#   Los mutantes que invierten el orden (A8) hacen fallar este test.
# Version: 0.1.0 (F05-06 M3 §A7)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import threading
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_06_m3_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_reparto as rep
from app.api.dto_reparto import IntencionCobroPago, IntencionCorregirReparto, IntencionGastoCompartido, IntencionPerdon
from app.core.contexto import ContextoOperacion

D = decimal.Decimal
FECHA_OP = dt.date(2026, 10, 10)
ADVISORY = ("SELECT pg_try_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(%s::text))")

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M3_CONCURRENCIA=1)")


class PausaEn:
    """Pausa en la PRIMERA llamada a `modulo.atributo` del hilo `hilo`, DESPUES de ejecutarla."""

    def __init__(self, monkeypatch, modulo, atributo: str, hilo: str) -> None:
        self.llego, self.sigue = threading.Event(), threading.Event()
        self.pid = None
        original = getattr(modulo, atributo)

        def envoltorio(sesion, *args, **kwargs):
            resultado = original(sesion, *args, **kwargs)
            if threading.current_thread().name == hilo and not self.llego.is_set():
                self.pid = sesion.uno("SELECT pg_backend_pid()")[0]
                self.llego.set()
                self.sigue.wait(60)
            return resultado

        monkeypatch.setattr(modulo, atributo, envoltorio)


def sondear(owner, recursos: dict[str, tuple[str, uuid.UUID]], pid: int) -> dict:
    """Estado de cada recurso visto desde OTRA sesion, sin esperar."""
    dsn = h.dsn()
    estado: dict = {}
    with psycopg.connect(dsn) as c:
        estado["advisory"] = "LIBRE" if c.execute(ADVISORY, (str(owner),)).fetchone()[0] else "RETENIDO"
        c.rollback()
        for nombre, (tabla, ident) in recursos.items():
            try:
                c.execute(f"SELECT 1 FROM gapto.{tabla} WHERE id = %s FOR UPDATE NOWAIT", (ident,))
                estado[nombre] = "LIBRE"
            except psycopg.errors.LockNotAvailable:
                estado[nombre] = "RETENIDO"
            c.rollback()
        estado["pg_locks"] = [list(f) for f in c.execute(
            "SELECT locktype, relation::regclass::text, mode, granted FROM pg_locks WHERE pid = %s "
            "ORDER BY locktype, relation::regclass::text, mode", (pid,)).fetchall()]
        c.rollback()
    return estado


def recorrer(monkeypatch, owner, nombre: str, fn, pausas: list[tuple[str, object, str]],
             recursos: dict[str, tuple[str, uuid.UUID]]) -> list[dict]:
    """Ejecuta `fn` en un hilo y la detiene en cada pausa (en orden); sondea en cada una."""
    hilo = f"M3-{nombre}"
    puntos = [(etiqueta, PausaEn(monkeypatch, modulo, atributo, hilo)) for etiqueta, modulo, atributo in pausas]
    salida: dict = {}

    def cuerpo():
        try:
            salida["resultado"] = fn()
        except Exception as exc:  # pragma: no cover - se registra
            salida["error"] = repr(exc)

    t = threading.Thread(target=cuerpo, name=hilo, daemon=True)
    t.start()
    trazas = []
    for etiqueta, punto in puntos:
        assert punto.llego.wait(30), f"{nombre}: no se alcanzo la pausa {etiqueta}"
        trazas.append({"pausa": etiqueta, **sondear(owner, recursos, punto.pid)})
        punto.sigue.set()
    t.join(60)
    assert not t.is_alive() and "error" not in salida, salida
    codigo = getattr(salida.get("resultado"), "codigo", None)
    assert not isinstance(codigo, str), salida
    carpeta = os.getenv("GAPTO_M3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta) / "orden_locks"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(trazas, indent=1, default=str), encoding="utf-8")
    return trazas


def es_prefijo(traza: list[dict], orden: list[str]) -> None:
    """En cada pausa lo RETENIDO es un prefijo del orden canonico y crece monotonamente."""
    previos = 0
    for paso in traza:
        retenidos = [r for r in orden if paso[r] == "RETENIDO"]
        assert retenidos == orden[:len(retenidos)], (paso["pausa"], retenidos, traza)
        assert len(retenidos) >= previos, traza
        previos = len(retenidos)


def ctx(owner) -> ContextoOperacion:
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def _puntos():
    from app.actores import servicio as actores
    from app.repositories import correcciones_repository, posiciones_repository, relaciones_repository
    return actores, correcciones_repository, posiciones_repository, relaciones_repository


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    tania, carlos = m.persona(cli, "Tania"), m.persona(cli, "Carlos")
    return owner, actor, cli, cta, ahorro, tania, carlos


def _cena(t):
    owner, _, cli, cta, _, tania, carlos = t
    c, r = m.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    return hecho, m.entidad_de_posicion(owner, hecho)


# ------------------------------------------------------------------ OP-22 con posicion
def test_orden_op22_con_posicion(t, monkeypatch):
    owner, _, cli, cta, _, _, _ = t
    actores, _, _, _ = _puntos()
    simon = m.persona(cli, "Simón")
    cuerpo = m.cuerpo("20.00", pagado_por=m.con_cuenta(cta), reparto=m.repartir("10.00", (simon, "10.00", "SI")))
    traza = recorrer(
        monkeypatch, owner, "op22_con_posicion",
        lambda: rep.registrar_gasto_compartido(fh.unidad(), ctx(owner), IntencionGastoCompartido(**cuerpo)),
        [("P1", rep, "tomar_inversiones"), ("P2", rep, "bloquear_cuentas"), ("P3", actores, "actor_de_tercero")],
        {"cuenta": ("cuentas", cta), "tercero": ("terceros", simon)})
    es_prefijo(traza, ["advisory", "cuenta", "tercero"])
    assert [p["advisory"] for p in traza] == ["RETENIDO"] * 3
    assert (traza[0]["cuenta"], traza[1]["cuenta"], traza[2]["tercero"]) == ("LIBRE", "RETENIDO", "RETENIDO"), traza


# ------------------------------------------------------------------ OP-14, OP-12B y condonacion
@pytest.mark.parametrize("operacion", ["cobro", "pago", "perdon"])
def test_orden_reducciones(t, monkeypatch, operacion):
    owner, _, cli, cta, _, tania, _ = t
    _, _, pos, rel = _puntos()
    if operacion == "pago":
        c, _ = m.peluqueria(cli, tania)
        hecho = uuid.UUID(c["intencion_id"])
        entidad = m.entidad_de_posicion(owner, hecho)
    else:
        hecho, entidad = _cena(t)
    if operacion == "perdon":
        fn = lambda: rep.perdonar(fh.unidad(), ctx(owner), entidad, IntencionPerdon(  # noqa: E731
            intencion_id=uuid.uuid4(), importe=D("5.00"), fecha=FECHA_OP))
        pausas = [("P1", rep, "tomar_inversiones"), ("P3", pos, "bloquear_posiciones")]
        orden = ["advisory", "posicion"]
    else:
        operar = rep.cobrar if operacion == "cobro" else rep.pagar
        fn = lambda: operar(fh.unidad(), ctx(owner), entidad, IntencionCobroPago(  # noqa: E731
            intencion_id=uuid.uuid4(), importe=D("5.00"), cuenta_id=cta, fecha=FECHA_OP))
        pausas = [("P1", rep, "tomar_inversiones"), ("P2", rep, "bloquear_cuentas")]
        if operacion == "cobro":  # OP-14 bloquea el hecho causal en la raiz (G-R1-B)
            pausas.append(("P2b", rel, "bloquear_hechos"))
        pausas.append(("P3", pos, "bloquear_posiciones"))
        orden = ["advisory", "cuenta"] + (["hecho"] if operacion == "cobro" else []) + ["posicion"]
    recursos = {"cuenta": ("cuentas", cta), "hecho": ("hechos_financieros", hecho), "posicion": ("entidades", entidad)}
    traza = recorrer(monkeypatch, owner, f"reduccion_{operacion}", fn, pausas, recursos)
    es_prefijo(traza, orden)
    assert traza[0]["posicion"] == "LIBRE" and traza[-1]["posicion"] == "RETENIDO", traza
    assert all(p["advisory"] == "RETENIDO" for p in traza), traza


# ------------------------------------------------------------------ OP-21 («Corregir reparto»)
def test_orden_op21_corregir_reparto(t, monkeypatch):
    owner, yo, cli, *_ = t
    _, corr, pos, rel = _puntos()
    hecho, entidad = _cena(t)
    tania = t[5]
    partes = {m.atribucion_de(owner, hecho, yo): D("9.50"),
              m.atribucion_de(owner, hecho, m.actor_de(owner, tania)): D("20.00")}
    fn = lambda: rep.corregir_reparto(fh.unidad(), ctx(owner), hecho, IntencionCorregirReparto(  # noqa: E731
        row_version=m.version(owner, hecho), motivo="orden de locks",
        partes=[{"atribucion_id": a, "importe": i} for a, i in partes.items()]))
    traza = recorrer(monkeypatch, owner, "op21_corregir_reparto", fn,
                     [("P1", corr, "tomar_advisory_inversiones"), ("P2", rel, "bloquear_hechos"),
                      ("P3", pos, "bloquear_posiciones")],
                     {"hecho": ("hechos_financieros", hecho), "posicion": ("entidades", entidad)})
    es_prefijo(traza, ["advisory", "hecho", "posicion"])
    assert [(p["hecho"], p["posicion"]) for p in traza] == [("LIBRE", "LIBRE"), ("RETENIDO", "LIBRE"),
                                                            ("RETENIDO", "RETENIDO")], traza
