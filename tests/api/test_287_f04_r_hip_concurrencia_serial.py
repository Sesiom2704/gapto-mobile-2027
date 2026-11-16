# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_287_f04_r_hip_concurrencia_serial.py
# Ruta: tests/api/test_287_f04_r_hip_concurrencia_serial.py
# Descripcion: T3-F06 · F04-R-HIP (mandato v1.2 §11; literal F04 v1.1 A7;
#   literal F05 v1.2, S10). Bateria SERIAL y determinista, FUERA de la suite
#   general: solo con GAPTO_F04RHIP_CONCURRENCIA=1 (evidencia JSON si
#   GAPTO_F04RHIP_EVIDENCIA apunta a una carpeta). COMMIT real sobre base
#   desechable. Nunca en paralelo. En cada caso: pg_locks (locks no concedidos
#   en la base) durante la intercalacion, pg_stat_database.deadlocks antes y
#   despues sin cambio y ningun 40P01.
#     C1-01  sesion B retiene el hecho de una cuota (FOR NO KEY UPDATE, como
#            OP-21) || A: OP-21 sobre ese hecho -> A espera a B (unica espera,
#            acotada) y, al liberar, OWNERSHIP_F07 con estado identico.
#     C1-02  B retiene cuenta -> financiacion (orden futuro de F06-01H) || A:
#            OP-21 sobre el hecho de la cuota -> A no espera (OP-21 no toma
#            la financiacion): sin ciclo posible; OWNERSHIP_F07.
#     C1-03  B retiene la raiz del hecho (OP-21 en curso) || A: S1 reparto ->
#            A rechaza SIN esperar (guarda previa a los locks).
#     C1-04  B retiene la prevision de una cuota || A: S7 «Reabrir» y «Dar por
#            cubierta» -> ambos rechazados sin esperar.
#     C1-05  IC-13: B retiene el hecho de la cuota 2 || A: OP-21 sobre la
#            cuota 1 -> OWNERSHIP_F07 sin esperar (sin bloqueo cruzado).
#     C1-06  A: OP-03P sobre el pago de una cuota || B: S7 sobre su prevision,
#            simultaneos -> ambos rechazados, sin espera indefinida.
#     C1-07  (S10) B retiene FOR UPDATE la prevision y su fila de
#            financiacion_cuotas sin confirmar || A: S10 GP marcar=true -> A
#            rechaza SIN esperar (ningun lock de A con granted=false); B
#            confirma; estado final = el de B.
#     C1-08  (S10) A: S10 GC marcar=false || B: S7 «Dar por cubierta» sobre
#            la misma prevision, simultaneos -> ambos rechazados; prevision,
#            cuota y auditoria identicas.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, paso 5)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m
import vs01_api_helpers as h

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import f04_r_hip_formas as fz  # noqa: E402

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04RHIP_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04RHIP_CONCURRENCIA=1)")

#: Locks no concedidos de las sesiones de ESTA base (los de transactionid/tuple no llevan `database`).
NO_CONCEDIDOS = ("SELECT l.pid, l.locktype, l.mode, l.relation::regclass::text FROM pg_locks l "
                 "JOIN pg_stat_activity a ON a.pid = l.pid WHERE NOT l.granted AND a.datname = current_database() "
                 "ORDER BY l.pid, l.locktype")


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04RHIP_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def deadlocks(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


class Hilo(threading.Thread):
    def __init__(self, fn) -> None:
        super().__init__(daemon=True)
        self.fn, self.resultado, self.error, self.fin = fn, None, None, None

    def run(self) -> None:
        try:
            self.resultado = self.fn()
        except Exception as exc:  # noqa: BLE001 - se inspecciona en el oraculo
            self.error = exc
        self.fin = time.monotonic()


def _codigo(hilo: Hilo) -> str:
    if hilo.error is not None:
        codigo = getattr(hilo.error, "codigo", None)
        sqlstate = getattr(hilo.error, "sqlstate", None)
        assert sqlstate != "40P01", hilo.error
        return getattr(codigo, "value", None) or type(hilo.error).__name__
    r = hilo.resultado
    if hasattr(r, "status_code"):
        return r.json().get("codigo", "OK") if r.status_code >= 400 else "OK"
    return "OK"


def _sondear(hilo: Hilo, dsn: str, limite: float = 8.0) -> list:
    """Locks no concedidos vistos mientras el hilo corre (hasta `limite`)."""
    vistos = []
    fin = time.monotonic() + limite
    with psycopg.connect(dsn, autocommit=True) as mon:
        while hilo.is_alive() and time.monotonic() < fin:
            vistos += mon.execute(NO_CONCEDIDOS).fetchall()
            time.sleep(0.02)
    return vistos


def _retener(dsn: str, owner, sentencias: list[tuple[str, tuple]]) -> psycopg.Connection:
    c = psycopg.connect(dsn)
    cur = c.cursor()
    cur.execute("SET ROLE gapto_owner")
    cur.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
    for sql, params in sentencias:
        cur.execute(sql, params)
    return c


class Esc:
    def __init__(self):
        self.owner, self.actor, self.cli, self.cta, self.ahorro = m.entorno()
        self.dsn = h.dsn()

    def cuota(self, *, conciliada=False):
        pid = m.prevision(self.owner, "Cuota hipoteca", importe="500.00", cuenta_salida=self.cta,
                          desde="2026-10-01")
        entidad, cuota = fz.financiacion(self.dsn, self.owner, prevision_id=pid)
        f = fz.cuota_pagada(self.dsn, fh.unidad(), m.ctx(self.owner), self.owner, entidad,
                            cuenta_id=self.cta if conciliada else None, actor_id=self.actor)
        return pid, cuota, f


def _op21_baja(esc, f):
    from app.services.correcciones_service import CorreccionesService, DatosCorreccion
    return lambda: CorreccionesService(fh.unidad()).corregir(m.ctx(esc.owner), DatosCorreccion(
        hecho_id=f.hecho_id, row_version_esperada=f.version, motivo="C1", entidades_a_eliminar=(f.vinculo_id,)))


def _caso_retenido(nombre, esc, retener, fn, *, espera_esperada: bool, codigo: str, pid=None, cuota=None, f=None):
    d0 = deadlocks(esc.dsn)
    antes = fz.foto(esc.dsn, esc.owner, f.hecho_id, pid, cuota) if f else None
    b = _retener(esc.dsn, esc.owner, retener)
    a = Hilo(fn)
    t0 = time.monotonic()
    try:
        a.start()
        vistos = _sondear(a, esc.dsn, limite=3.0 if espera_esperada else 8.0)
        vivo_con_b = a.is_alive()
    finally:
        b.commit()
        b.close()
    a.join(30)
    traza = {"caso": nombre, "a_esperaba_a_b": vivo_con_b, "no_concedidos": vistos, "codigo_a": _codigo(a),
             "duracion_a_s": None if a.fin is None else round(a.fin - t0, 3), "deadlocks": [d0, deadlocks(esc.dsn)]}
    evidencia(nombre, traza)
    assert not a.is_alive(), traza
    assert traza["codigo_a"] == codigo, traza
    assert traza["deadlocks"][0] == traza["deadlocks"][1], traza
    if espera_esperada:
        assert vivo_con_b and vistos, traza
    else:
        assert not vivo_con_b and not vistos, traza
    if f is not None:
        assert fz.foto(esc.dsn, esc.owner, f.hecho_id, pid, cuota) == antes, traza
    return traza


def test_c1_01_op21_espera_a_la_raiz_y_rechaza() -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    _caso_retenido("C1-01", esc, [("SELECT id FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE",
                                   (f.hecho_id,))], _op21_baja(esc, f), espera_esperada=True,
                   codigo="OWNERSHIP_F07", pid=pid, cuota=cuota, f=f)


def test_c1_02_orden_futuro_cuenta_financiacion_sin_ciclo() -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    _caso_retenido("C1-02", esc, [
        ("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (esc.cta,)),
        ("SELECT id FROM gapto.entidades WHERE id = %s FOR NO KEY UPDATE", (f.entidad_id,)),
    ], _op21_baja(esc, f), espera_esperada=False, codigo="OWNERSHIP_F07", pid=pid, cuota=cuota, f=f)


def test_c1_03_reparto_frente_a_op21_en_curso() -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    partes = {m3.atribucion_de(esc.owner, f.hecho_id, esc.actor): "100.00"}
    _caso_retenido("C1-03", esc, [("SELECT id FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE",
                                   (f.hecho_id,))],
                   lambda: m3.corregir(esc.cli, f.hecho_id, f.version, partes), espera_esperada=False,
                   codigo="REPARTO_NO_CORREGIBLE", pid=pid, cuota=cuota, f=f)


@pytest.mark.parametrize("accion", ["reabrir", "dar-por-realizada"])
def test_c1_04_s7_frente_a_la_prevision_retenida(accion) -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(esc.owner, pid), "motivo": "C1-04"}
    _caso_retenido(f"C1-04-{accion}", esc, [("SELECT id FROM gapto.previsiones WHERE id = %s FOR UPDATE", (pid,))],
                   lambda: esc.cli.post(f"/v1/previsiones/{pid}/{accion}", json=cuerpo, headers=h.AUTH),
                   espera_esperada=False, codigo="PREVISION_DE_CUOTA", pid=pid, cuota=cuota, f=f)


def test_c1_05_ic13_op21_sobre_una_cuota_mientras_se_escribe_la_siguiente() -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    _pid2, _cuota2, f2 = esc.cuota()
    _caso_retenido("C1-05", esc, [("SELECT id FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE",
                                   (f2.hecho_id,))], _op21_baja(esc, f), espera_esperada=False,
                   codigo="OWNERSHIP_F07", pid=pid, cuota=cuota, f=f)


def _simultaneos(nombre, esc, fns, codigos, *, pid, cuota, f):
    d0 = deadlocks(esc.dsn)
    antes = fz.foto(esc.dsn, esc.owner, f.hecho_id, pid, cuota)
    barrera = threading.Barrier(len(fns))

    def con_barrera(fn):
        def _():
            barrera.wait(10)
            return fn()
        return _
    hilos = [Hilo(con_barrera(fn)) for fn in fns]
    for hl in hilos:
        hl.start()
    vistos = _sondear(hilos[0], esc.dsn, limite=20)
    for hl in hilos:
        hl.join(30)
    traza = {"caso": nombre, "codigos": [_codigo(hl) for hl in hilos], "no_concedidos": vistos,
             "vivos": [hl.is_alive() for hl in hilos], "deadlocks": [d0, deadlocks(esc.dsn)]}
    evidencia(nombre, traza)
    assert traza["vivos"] == [False] * len(fns), traza
    assert traza["codigos"] == codigos, traza
    assert traza["deadlocks"][0] == traza["deadlocks"][1], traza
    assert fz.foto(esc.dsn, esc.owner, f.hecho_id, pid, cuota) == antes, traza


def test_c1_06_op03p_frente_a_s7_sobre_su_prevision() -> None:
    from app.services.anulacion_tesoreria_service import AnulacionTesoreriaService, DatosAnulacionRegistro
    from app.services.previsiones_service import adquirir_impacto_ancla, aplicar_impacto_ancla

    esc = Esc()
    pid, cuota, f = esc.cuota(conciliada=True)
    movs = {mv[0]: mv[2] for mv in fz.foto(esc.dsn, esc.owner, f.hecho_id)["movimientos"]}
    op03p = lambda: AnulacionTesoreriaService(  # noqa: E731
        fh.unidad(), adquirir_impacto=adquirir_impacto_ancla, aplicar_impacto=aplicar_impacto_ancla
    ).anular_registro(m.ctx(esc.owner), DatosAnulacionRegistro(
        hecho_id=f.hecho_id, row_version_esperada=f.version, movimientos_row_version_esperadas=movs,
        motivo="C1-06", movimiento_en_banco=False))
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(esc.owner, pid), "motivo": "C1-06"}
    s7 = lambda: esc.cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=cuerpo, headers=h.AUTH)  # noqa: E731
    _simultaneos("C1-06", esc, [op03p, s7], ["ANULACION_FINANCIACION_SIN_REVERSION", "PREVISION_DE_CUOTA"],
                 pid=pid, cuota=cuota, f=f)


def test_c1_07_s10_no_espera_a_la_prevision_retenida() -> None:
    """S10: guarda sin lock antes de cualquier lock; si fuera tardia, A esperaria
    a B en OP-17 (prevision FOR UPDATE)."""
    esc = Esc()
    pid, cuota, f = esc.cuota()
    huella = m.huella(esc.owner)
    traza = _caso_retenido("C1-07", esc, [
        ("SELECT id FROM gapto.previsiones WHERE id = %s FOR UPDATE", (pid,)),
        ("SELECT id FROM gapto.financiacion_cuotas WHERE prevision_id = %s FOR UPDATE", (pid,)),
    ], lambda: m.gasto_desde(esc.cli, esc.owner, esc.cta, pid, "500.00", True)[1], espera_esperada=False,
        codigo="PREVISION_DE_CUOTA", pid=pid, cuota=cuota, f=f)
    assert m.huella(esc.owner) == huella, traza


def test_c1_08_s10_gc_frente_a_s7_dar_por_cubierta() -> None:
    esc = Esc()
    pid, cuota, f = esc.cuota()
    huella = m.huella(esc.owner)
    c = m3.cuerpo("500.00", pagado_por=m3.con_cuenta(esc.cta), reparto=m3.SOLO_MIO)
    c["prevision"] = m.bloque(esc.owner, pid, False)
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(esc.owner, pid), "motivo": "C1-08"}
    gc = lambda: esc.cli.post(m.COMPARTIDO, json=c, headers=h.AUTH)  # noqa: E731
    s7 = lambda: esc.cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=cuerpo, headers=h.AUTH)  # noqa: E731
    _simultaneos("C1-08", esc, [gc, s7], ["PREVISION_DE_CUOTA", "PREVISION_DE_CUOTA"], pid=pid, cuota=cuota, f=f)
    assert m.huella(esc.owner) == huella
