# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14k_f04_r3_il1b_advisory_serial.py
# Ruta: tests/backend/test_14k_f04_r3_il1b_advisory_serial.py
# Descripcion: F04-R3 `il1b` (F05-D050 §64.4.3; adenda 2 §D). Prueba
#   discriminante del advisory POR RAIZ de OP-22. Bateria SERIAL, FUERA de la
#   suite general: solo con GAPTO_F04R3_CONCURRENCIA=1 (evidencia JSON si
#   GAPTO_F04R3_EVIDENCIA apunta a una carpeta). COMMIT real sobre base
#   desechable. Nunca en paralelo.
#
#   Diagnostico (INFORME_DIAG_F04-R3 §2): sin entidades ni posiciones, OP-22
#   no tomaba ningun lock antes de leer la identidad. Dos invocaciones con la
#   misma raiz la leian ausente y componian las dos: el perdedor devolvia
#   `idempotente=False` (IL1B-2, doble «creado») o, si los dos INSERT del ancla
#   coincidian, 23505 de uq_hechos_financieros__owner_anchor traducido a
#   VIOLACION_INVARIANTE_FISICA.
#
#   Tecnica (sin sleeps a ciegas): el hilo A se retiene DENTRO de su
#   transaccion justo antes del INSERT del ancla (ya ha tomado el advisory y ha
#   leido la identidad ausente); se lanza B y se espera a VER su backend en
#   pg_locks esperando el advisory (locktype advisory, NOT granted, clave
#   (hashtext('gapto:OP22'), hashtext(<raiz>))); despues se libera A.
#   Oraculo POR VUELTA (>= 300 vueltas en serie):
#     - B observado esperando el advisory de la raiz;
#     - exactamente un resultado con idempotente=False;
#     - el otro idempotente (misma intencion) o
#       IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (otra intencion);
#     - ningun VIOLACION_INVARIANTE_FISICA;
#     - estado fisico 1/1/1/1: la realizacion de un gasto pagado son cuatro
#       filas, hechos_financieros (la raiz), hecho_efectos (el efecto GASTO),
#       hecho_movimientos_tesoreria (la conciliacion) y movimientos_tesoreria
#       (el movimiento de A); con otra intencion, 0 movimientos de B.
#   Oraculos de la bateria: nadie colgado, 0 reintentos 40P01 y 0 deadlocks.
#   Mutantes (scripts/dev/mutantes_f04_r3.py): M1 sin el advisory, M2 advisory
#   despues de leer la identidad: los dos MUEREN en la primera vuelta.
# Version: 0.1.0 (F04-R3 il1b)
# ============================================================

from __future__ import annotations

import collections
import dataclasses
import decimal
import json
import logging
import os
import pathlib
import threading
import time

import psycopg
import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_compuesto import DatosHechoCompuesto
from app.repositories import hechos_repository as repo_hechos
from f08_motor import efecto
from test_140_f04_r3_op22 import cuenta_filas, hecho, op22, pago  # noqa: F401

D = decimal.Decimal
LOGGER = "gapto.motor.transaccion"
VUELTAS = int(os.getenv("GAPTO_F04R3_VUELTAS", "300"))
VUELTAS_OTRA = int(os.getenv("GAPTO_F04R3_VUELTAS_OTRA", "50"))
ESPERA_BLOQUEO = 10.0
IDEMPOTENTE, CREADO = "IDEMPOTENTE", "CREADO"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R3_CONCURRENCIA=1)")

ESPERANDO_ADVISORY = (
    "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND objsubid = 2 "
    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
    "AND classid::bigint = (hashtext('gapto:OP22')::bigint & 4294967295) "
    "AND objid::bigint = (hashtext(%s::text)::bigint & 4294967295)"
)


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def deadlocks(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


def clasificar(r: dict) -> str:
    if "r" in r:
        return IDEMPOTENTE if r["r"].idempotente else CREADO
    e = r["e"]
    if isinstance(e, ErrorMotor):
        diag = getattr(getattr(e, "causa", None), "diag", None)
        restriccion = getattr(diag, "constraint_name", None)
        return e.codigo.value + (f"[{restriccion}]" if restriccion else "")
    return f"{type(e).__name__}: {e}"


class RetenerAntesDelAncla:
    """Detiene al hilo `A` justo ANTES de `insertar_si_no_existe` (dentro de su
    transaccion, con el advisory ya tomado y la identidad ya leida)."""

    def __init__(self, monkeypatch) -> None:
        self.llego, self.sigue = threading.Event(), threading.Event()
        original = repo_hechos.insertar_si_no_existe

        def envoltorio(sesion, *args, **kwargs):
            if threading.current_thread().name == "A" and not self.llego.is_set():
                self.llego.set()
                self.sigue.wait(60)
            return original(sesion, *args, **kwargs)

        monkeypatch.setattr(repo_hechos, "insertar_si_no_existe", envoltorio)


def vuelta(op22, contexto, admin, monitor, cuenta, monkeypatch, otra: bool) -> dict:  # noqa: F811
    owner = contexto.owner_user_id
    h = hecho()
    datos_a = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                  pagos=[pago(h.hecho_id, cuenta, "-100.0000")])
    datos_b = datos_a
    if otra:  # misma raiz, otra intencion (concepto y movimiento distintos)
        datos_b = DatosHechoCompuesto(hecho=dataclasses.replace(h, concepto="otra intencion"),
                                      efectos=[efecto("GASTO", D("100.0000"))],
                                      pagos=[pago(h.hecho_id, cuenta, "-100.0000")])
    retener = RetenerAntesDelAncla(monkeypatch)
    res: dict[str, dict] = {"A": {}, "B": {}}

    def correr(nombre, datos):
        try:
            res[nombre]["r"] = op22.registrar_hecho_compuesto(contexto, datos)
        except Exception as exc:  # noqa: BLE001 - se clasifica en el oraculo
            res[nombre]["e"] = exc

    a = threading.Thread(target=correr, args=("A", datos_a), name="A", daemon=True)
    b = threading.Thread(target=correr, args=("B", datos_b), name="B", daemon=True)
    traza: dict = {}
    try:
        a.start()
        traza["a_retenido"] = retener.llego.wait(30)
        b.start()
        fin = time.monotonic() + ESPERA_BLOQUEO
        visto = []
        while time.monotonic() < fin and b.is_alive():
            visto = [f[0] for f in monitor.execute(ESPERANDO_ADVISORY, (str(h.hecho_id),)).fetchall()]
            if visto:
                break
            time.sleep(0.005)
        traza["b_esperando_advisory"] = bool(visto)
    finally:
        retener.sigue.set()
        a.join(60)
        b.join(60)
        monkeypatch.undo()
    traza["vivos"] = [t.name for t in (a, b) if t.is_alive()]
    traza["A"], traza["B"] = clasificar(res["A"]), clasificar(res["B"])
    traza["fisico"] = {
        "hechos_financieros": cuenta_filas(admin, owner, "hechos_financieros", "id", h.hecho_id),
        "hecho_efectos": cuenta_filas(admin, owner, "hecho_efectos", "hecho_id", h.hecho_id),
        "hecho_movimientos_tesoreria": cuenta_filas(admin, owner, "hecho_movimientos_tesoreria", "hecho_id",
                                                    h.hecho_id),
        "movimientos_tesoreria": cuenta_filas(admin, owner, "movimientos_tesoreria", "id",
                                              datos_a.pagos[0].movimiento.movimiento_id),
    }
    if otra:
        traza["movimiento_b"] = cuenta_filas(admin, owner, "movimientos_tesoreria", "id",
                                             datos_b.pagos[0].movimiento.movimiento_id)
    return traza


def oraculo_vuelta(traza: dict, otra: bool) -> None:
    assert traza["a_retenido"] and not traza["vivos"], traza
    assert traza["b_esperando_advisory"], ("el segundo backend no espero el advisory de la raiz", traza)
    codigos = (traza["A"], traza["B"])
    assert not any("VIOLACION_INVARIANTE_FISICA" in c for c in codigos), traza
    assert codigos.count(CREADO) == 1, traza  # exactamente un idempotente=False
    perdedor = traza["B"] if traza["A"] == CREADO else traza["A"]
    esperado = CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.value if otra else IDEMPOTENTE
    assert perdedor == esperado, traza
    assert traza["fisico"] == {"hechos_financieros": 1, "hecho_efectos": 1, "hecho_movimientos_tesoreria": 1,
                               "movimientos_tesoreria": 1}, traza
    if otra:
        assert traza["movimiento_b"] == 0, traza


@pytest.mark.parametrize("intencion", ["misma", "otra"])
def test_il1b_advisory_por_raiz_serializa_op22(dsn, op22, contexto, admin, cuenta, monkeypatch, caplog,  # noqa: F811
                                              intencion):
    otra = intencion == "otra"
    n = VUELTAS_OTRA if otra else VUELTAS
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    antes = deadlocks(dsn)
    resultados: collections.Counter = collections.Counter()
    inicio = time.monotonic()
    with psycopg.connect(dsn, autocommit=True) as monitor:
        for i in range(n):
            traza = vuelta(op22, contexto, admin, monitor, cuenta, monkeypatch, otra)
            resultados[f"{traza['A']} + {traza['B']}"] += 1
            try:
                oraculo_vuelta(traza, otra)
            except AssertionError:
                evidencia(f"il1b_{intencion}_fallo", {"vuelta": i, "traza": traza, "resultados": dict(resultados)})
                raise
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    resumen = {
        "intencion": intencion, "vueltas": n, "segundos": round(time.monotonic() - inicio, 1),
        "resultados": dict(resultados),
        "reintentos_40P01": sum(1 for r in caplog.records
                                if r.name == LOGGER and getattr(r, "sqlstate", None) == "40P01"),
        "deadlocks_delta": deadlocks(dsn) - antes,
    }
    evidencia(f"il1b_{intencion}", resumen)
    assert resumen["reintentos_40P01"] == 0 and resumen["deadlocks_delta"] == 0, resumen
