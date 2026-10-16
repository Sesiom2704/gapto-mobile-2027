# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14b_f04_r2a_concurrencia_serial.py
# Ruta: tests/backend/test_14b_f04_r2a_concurrencia_serial.py
# Descripcion: F04-R2 R2-A (F04-D060; contrato F04-R2 v0.6 §7.2.1; mandato
#   F04-R2A v1.0 §3 y encadenado 2026-10-16 v1.2, AJ-NEON-04). Bateria SERIAL
#   y determinista, FUERA de la suite general: solo con
#   GAPTO_F04R2A_CONCURRENCIA=1. Si GAPTO_F04R2A_EVIDENCIA apunta a una
#   carpeta, cada escenario deja su JSON. Nunca en paralelo.
#
#   Hipotesis «retirar desde el origen no exige lock del destino» (V06-03):
#   la relacion DEVOLUCION_DE D -> O se retira con OP-21 sobre el ORIGEN D.
#     C-REL-01 · frente a OP-13 sobre el destino O (nueva devolucion), con un
#       importe que solo cabe si la relacion ya no cuenta (80) y con otro que
#       cabe siempre (40);
#     C-REL-02 · frente a OP-03 sobre el destino O;
#     C-REL-04 · relectura: dos OP-21 sobre el origen, y OP-21 desde el
#       destino mientras el origen tiene la retirada sin confirmar.
#   Tecnica: el PRIMER paso se detiene DENTRO de su transaccion en un punto
#   fijo (OP-21 justo despues del DELETE de la relacion; OP-13 y OP-03 justo
#   despues del lock de su raiz) mediante un envoltorio del repositorio que
#   solo actua en el hilo de ese paso. Con el primero retenido se lanza el
#   segundo y se espera a que termine o quede bloqueado (pg_blocking_pids);
#   despues se libera el primero. Cada orden tiene UN resultado esperado.
#   Oraculos: capacidad reversible nunca excedida; acumulado = suma de las
#   devoluciones ACTIVAS con relacion efectiva; ningun destino ANULADO con una
#   dependencia activa; nada parcial; ni 40P01 ni deadlocks.
#
#   ORACULO DE «SIN LOCK DEL DESTINO» (AJ-NEON-04, obligatorio en C-REL-01/02):
#   con OP-21 retenido tras el DELETE, otra sesion ejecuta
#   `SELECT ... FROM gapto.hechos_financieros WHERE id = <destino> FOR UPDATE
#   NOWAIT` y debe obtener el lock sin error (FOR UPDATE choca con cualquier
#   lock de fila); ademas se captura `pg_locks` de la sesion de OP-21 (ninguna
#   fila de tipo tuple) y se comprueba que el `xmax` del destino no es el xid
#   de OP-21. La contraprueba es un mutante que hace FOR SHARE del destino.
# Version: 0.1.0 (F04-R2 R2-A)
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
from types import SimpleNamespace

import psycopg
import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.repositories import correcciones_repository as repo_corr
from app.repositories import relaciones_repository as repo_rel
from app.services.correcciones_service import DatosCorreccion
from test_117_op13_devolucion import BRUTO, crear_origen, datos_devolucion
from test_138_f04_r1_discriminantes import version_hecho
from test_139_f04_r1_concurrencia_serial import LOGGER, OK, Paso, bloqueados, deadlocks, esperar, reintentos

D = decimal.Decimal

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R2A_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R2A_CONCURRENCIA=1)")


# ------------------------------------------------------------------ arnes
class Pausa:
    """Detiene el hilo `hilo` justo DESPUES de `modulo.atributo`, dentro de su transaccion."""

    def __init__(self, monkeypatch, modulo, atributo: str, hilo: str) -> None:
        self.llego, self.sigue = threading.Event(), threading.Event()
        self.pid = self.xid = None
        original = getattr(modulo, atributo)

        def envoltorio(sesion, *args, **kwargs):
            resultado = original(sesion, *args, **kwargs)
            if threading.current_thread().name == hilo and not self.llego.is_set():
                self.pid, self.xid = sesion.uno("SELECT pg_backend_pid(), pg_current_xact_id()::text")
                self.llego.set()
                self.sigue.wait(90)
            return resultado

        monkeypatch.setattr(modulo, atributo, envoltorio)


def oraculo_sin_lock(dsn: str, destino: uuid.UUID, pausa: Pausa) -> dict:
    """Con OP-21 retenido: lock del destino con NOWAIT, pg_locks de OP-21 y xmax del destino."""
    datos: dict = {"op21_pid": pausa.pid, "op21_xid": pausa.xid}
    with psycopg.connect(dsn) as c:
        # xmax ANTES de la sonda: el FOR UPDATE de la propia sonda dejaria su xid.
        datos["xmax_destino"] = c.execute("SELECT xmax::text FROM gapto.hechos_financieros WHERE id = %s",
                                          (destino,)).fetchone()[0]
        c.rollback()
        try:
            c.execute("SELECT id FROM gapto.hechos_financieros WHERE id = %s FOR UPDATE NOWAIT", (destino,))
            datos["nowait"] = "OBTENIDO"
        except psycopg.errors.LockNotAvailable as exc:
            datos["nowait"] = f"55P03: {type(exc).__name__}"
        c.rollback()
        datos["pg_locks_op21"] = [list(f) for f in c.execute(
            "SELECT locktype, relation::regclass::text, mode, granted, page, tuple, transactionid::text "
            "FROM pg_locks WHERE pid = %s ORDER BY locktype, relation::regclass::text, mode",
            (pausa.pid,)).fetchall()]
        c.rollback()
    datos["tuple_locks_op21"] = [f for f in datos["pg_locks_op21"] if f[0] == "tuple"]
    return datos


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R2A_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def par(dsn, caplog, pausa: Pausa, primero: Paso, segundo: Paso, *, destino: uuid.UUID | None = None) -> dict:
    caplog.clear()
    antes = deadlocks(dsn)
    traza: dict = {"orden": [primero.name, segundo.name]}
    try:
        primero.start()
        traza["primero_retenido"] = pausa.llego.wait(30)
        if destino is not None and traza["primero_retenido"]:
            traza["sin_lock"] = oraculo_sin_lock(dsn, destino, pausa)
        segundo.start()
        esperar(lambda: not segundo.is_alive() or len(bloqueados(dsn)) >= 1, 30)
        traza["segundo_bloqueado"] = segundo.is_alive()
    finally:
        pausa.sigue.set()
        for p in (primero, segundo):
            p.join(60)
    time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
    for p in (primero, segundo):
        traza[p.name] = p.error or OK
    traza.update({"vivos": [p.name for p in (primero, segundo) if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"),
                  "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    return traza


def _superusuario(admin, sql, params=()):
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute(sql, params)
        return cur.fetchall()


def estado_destino(admin, original) -> dict:
    """Lectura de verificacion: relaciones entrantes efectivas, acumulado y estado del destino."""
    entrantes = _superusuario(admin, """
        SELECT r.id, r.hecho_origen_id, o.estado, r.tipo_relacion
          FROM gapto.hecho_relaciones r JOIN gapto.hechos_financieros o ON o.id = r.hecho_origen_id
         WHERE r.hecho_destino_id = %s ORDER BY r.id""", (original,))
    devuelto = _superusuario(admin, """
        SELECT COALESCE(sum(abs(e.importe_delta)), 0)
          FROM gapto.hecho_relaciones r
          JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id
          JOIN gapto.hecho_efectos e ON e.hecho_id = d.id
         WHERE r.hecho_destino_id = %s AND r.tipo_relacion = 'DEVOLUCION_DE'
           AND d.estado = 'ACTIVO' AND e.tipo_efecto = 'GASTO'""", (original,))[0][0]
    estado = _superusuario(admin, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (original,))[0][0]
    return {"entrantes": [[str(c) for c in f] for f in entrantes], "devuelto": D(devuelto), "estado": estado}


def auditorias(admin, registro_id) -> int:
    return _superusuario(admin, "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ANULAR'",
                         (registro_id,))[0][0]


@pytest.fixture()
def s(dsn, servicio, servicio_efectos, servicio_devoluciones, servicio_correcciones, contexto, admin, monkeypatch):
    original = crear_origen(servicio, servicio_efectos, contexto)  # GASTO de BRUTO (120)
    devolucion = datos_devolucion(original)  # 45, relacion DEVOLUCION_DE devolucion -> original
    servicio_devoluciones.devolver(contexto, devolucion)
    return SimpleNamespace(dsn=dsn, hec=servicio, dev=servicio_devoluciones, cor=servicio_correcciones,
                           ctx=contexto, admin=admin, mp=monkeypatch, original=original, d=devolucion)


def op21_origen(s):
    v = version_hecho(s.admin, s.ctx.owner_user_id, s.d.hecho_id)
    return lambda: s.cor.corregir(s.ctx, DatosCorreccion(
        hecho_id=s.d.hecho_id, row_version_esperada=v, motivo="la devolucion no era de ese hecho",
        relaciones_a_eliminar=(s.d.relacion_id,)))


def op21_destino(s):
    v = version_hecho(s.admin, s.ctx.owner_user_id, s.original)
    return lambda: s.cor.corregir(s.ctx, DatosCorreccion(
        hecho_id=s.original, row_version_esperada=v, motivo="desde el destino",
        relaciones_a_eliminar=(s.d.relacion_id,)))


def op13(s, importe: str):
    nueva = datos_devolucion(s.original, importe=D(importe))
    return nueva, (lambda: s.dev.devolver(s.ctx, nueva))


def op03(s):
    v = version_hecho(s.admin, s.ctx.owner_user_id, s.original)
    return lambda: s.hec.anular_hecho(s.ctx, hecho_id=s.original, row_version_esperada=v,
                                      motivo_anulacion="capturado por error")


def comprobar_sin_lock(traza):
    sl = traza["sin_lock"]
    assert sl["nowait"] == "OBTENIDO", traza
    assert sl["tuple_locks_op21"] == [], traza
    assert sl["xmax_destino"] != sl["op21_xid"], traza


def comunes(traza):
    assert traza["primero_retenido"], traza
    assert not traza["vivos"], traza
    assert traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza


# ------------------------------------------------------------------ C-REL-01
EXCEDE = CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE.value
C_REL_01 = {
    # (importe OP-13, primero): (resultado OP-21, resultado OP-13)
    ("80.0000", "OP-21"): (OK, EXCEDE),   # OP-13 lee la relacion aun vigente: rechazo conservador (OP-13 -> OP-21)
    ("80.0000", "OP-13"): (OK, OK),       # OP-13 lee tras el COMMIT de OP-21: cabe (OP-21 -> OP-13)
    ("40.0000", "OP-21"): (OK, OK),
    ("40.0000", "OP-13"): (OK, OK),
}


@pytest.mark.parametrize("importe, primero", list(C_REL_01), ids=[f"{i}-{p}-primero" for i, p in C_REL_01])
def test_c_rel_01_op21_origen_frente_a_op13_destino(s, importe, primero, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    nueva, f13 = op13(s, importe)
    pasos = {"OP-21": Paso("OP-21", op21_origen(s)), "OP-13": Paso("OP-13", f13)}
    if primero == "OP-21":
        pausa = Pausa(s.mp, repo_corr, "eliminar_relacion", "OP-21")
    else:
        pausa = Pausa(s.mp, repo_rel, "bloquear_hechos", "OP-13")
    segundo = "OP-13" if primero == "OP-21" else "OP-21"
    traza = par(s.dsn, caplog, pausa, pasos[primero], pasos[segundo],
                destino=s.original if primero == "OP-21" else None)
    s.mp.undo()
    final = estado_destino(s.admin, s.original)
    traza.update({"escenario": "C-REL-01", "importe_op13": importe, "final": final})
    evidencia(f"C-REL-01_{importe}_{primero}_primero", traza)
    comunes(traza)
    if primero == "OP-21":
        comprobar_sin_lock(traza)
    assert (traza["OP-21"], traza["OP-13"]) == C_REL_01[(importe, primero)], traza
    # Capacidad nunca excedida y acumulado = devoluciones ACTIVAS con relacion efectiva.
    assert final["devuelto"] <= BRUTO, traza
    esperado = D(importe) if traza["OP-13"] == OK else D("0")
    assert final["devuelto"] == esperado, traza
    # Sin actualizacion perdida: cada exito deja su rastro y nada mas.
    assert auditorias(s.admin, s.d.relacion_id) == 1, traza
    relaciones = {f[0] for f in final["entrantes"]}
    assert str(s.d.relacion_id) not in relaciones, traza
    assert (str(nueva.relacion_id) in relaciones) == (traza["OP-13"] == OK), traza


# ------------------------------------------------------------------ C-REL-02
DEPENDENCIAS = CodigoError.HECHO_CON_REALIDAD_ASOCIADA.value
C_REL_02 = {
    "OP-21": (OK, DEPENDENCIAS),  # OP-03 ve la dependencia aun vigente: rechazo conservador (OP-03 -> OP-21)
    "OP-03": (OK, OK),            # OP-03 lee tras el COMMIT de OP-21: ya no hay dependencia (OP-21 -> OP-03)
}


@pytest.mark.parametrize("primero", list(C_REL_02), ids=[f"{p}-primero" for p in C_REL_02])
def test_c_rel_02_op21_origen_frente_a_op03_destino(s, primero, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    pasos = {"OP-21": Paso("OP-21", op21_origen(s)), "OP-03": Paso("OP-03", op03(s))}
    if primero == "OP-21":
        pausa = Pausa(s.mp, repo_corr, "eliminar_relacion", "OP-21")
    else:
        pausa = Pausa(s.mp, repo_rel, "bloquear_hechos", "OP-03")
    segundo = "OP-03" if primero == "OP-21" else "OP-21"
    traza = par(s.dsn, caplog, pausa, pasos[primero], pasos[segundo],
                destino=s.original if primero == "OP-21" else None)
    s.mp.undo()
    final = estado_destino(s.admin, s.original)
    traza.update({"escenario": "C-REL-02", "final": final})
    evidencia(f"C-REL-02_{primero}_primero", traza)
    comunes(traza)
    if primero == "OP-21":
        comprobar_sin_lock(traza)
    assert (traza["OP-21"], traza["OP-03"]) == C_REL_02[primero], traza
    # Nunca un destino ANULADO con una dependencia activa; nada parcial.
    activas = [f for f in final["entrantes"] if f[2] == "ACTIVO"]
    if final["estado"] == "ANULADO":
        assert activas == [], traza
    assert final["estado"] == ("ANULADO" if traza["OP-03"] == OK else "ACTIVO"), traza
    assert auditorias(s.admin, s.d.relacion_id) == 1 and activas == [], traza


# ------------------------------------------------------------------ C-REL-04
DESFASADA = CodigoError.VERSION_DESFASADA.value


def test_c_rel_04_dos_op21_sobre_el_origen(s, caplog):
    """El segundo valida tras el lock con la version y el conjunto ACTUALES: VERSION_DESFASADA, una sola
    retirada y una sola auditoria."""
    caplog.set_level(logging.WARNING, logger=LOGGER)
    pausa = Pausa(s.mp, repo_corr, "eliminar_relacion", "OP-21a")
    traza = par(s.dsn, caplog, pausa, Paso("OP-21a", op21_origen(s)), Paso("OP-21b", op21_origen(s)))
    s.mp.undo()
    traza["escenario"] = "C-REL-04 dos OP-21"
    evidencia("C-REL-04_dos_op21", traza)
    comunes(traza)
    assert traza["segundo_bloqueado"], traza  # el segundo espera el root lock del origen
    assert (traza["OP-21a"], traza["OP-21b"]) == (OK, DESFASADA), traza
    assert auditorias(s.admin, s.d.relacion_id) == 1, traza


def test_c_rel_04_destino_mientras_el_origen_retira(s, caplog):
    """OP-21 desde el destino durante la retirada sin confirmar del origen: su DELETE (filtrado por origen) no
    toca la fila ni espera; la relectura ve la relacion vigente -> DEPENDENCIAS_ACTIVAS. Repetido tras el COMMIT
    del origen, la relectura ve el estado confirmado -> AGREGADO_NO_ENCONTRADO. Nunca una segunda retirada."""
    caplog.set_level(logging.WARNING, logger=LOGGER)
    pausa = Pausa(s.mp, repo_corr, "eliminar_relacion", "OP-21-origen")
    traza = par(s.dsn, caplog, pausa, Paso("OP-21-origen", op21_origen(s)),
                Paso("OP-21-destino", op21_destino(s)), destino=s.original)
    s.mp.undo()
    with pytest.raises(ErrorMotor) as excinfo:
        op21_destino(s)()
    traza.update({"escenario": "C-REL-04 destino", "despues": excinfo.value.codigo.value})
    evidencia("C-REL-04_destino_durante_origen", traza)
    comunes(traza)
    comprobar_sin_lock(traza)
    assert not traza["segundo_bloqueado"], traza
    assert (traza["OP-21-origen"], traza["OP-21-destino"]) == (OK, DEPENDENCIAS), traza
    assert traza["despues"] == CodigoError.AGREGADO_NO_ENCONTRADO.value, traza
    assert auditorias(s.admin, s.d.relacion_id) == 1, traza
