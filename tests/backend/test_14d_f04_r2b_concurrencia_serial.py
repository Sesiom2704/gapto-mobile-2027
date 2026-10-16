# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14d_f04_r2b_concurrencia_serial.py
# Ruta: tests/backend/test_14d_f04_r2b_concurrencia_serial.py
# Descripcion: F04-R2 R2-B (contrato F04-R2 v0.8 §3.4, §6.7.1, §10.5;
#   mandato F04-R2B v1.0 §4). Bateria SERIAL y determinista, FUERA de la suite
#   general: solo con GAPTO_F04R2B_CONCURRENCIA=1. Si GAPTO_F04R2B_EVIDENCIA
#   apunta a una carpeta, cada escenario deja su JSON. Nunca en paralelo.
#
#   Tecnica (la de R2-A, test_14b): el PRIMER paso se detiene DENTRO de su
#   transaccion en un punto fijo, ya con sus locks (OP-21P/OP-21T tras bloquear
#   los movimientos, ultimo nivel; los demas tras su primer lock), mediante un
#   envoltorio del repositorio que solo actua en el hilo de ese paso. Con el
#   primero retenido se lanza el segundo y se espera a que termine o quede
#   bloqueado; despues se libera el primero. Ambos ordenes. Cada orden tiene UN
#   resultado esperado, equivalente al serial, y un oraculo de estado final.
#   Pares (§4 del mandato y §10.5 del contrato), con la operacion REAL:
#     cuenta nueva (OP-21P / OP-21T) frente a M4 retirando la capacidad, frente
#     a deshabilitar la cuenta (UPDATE controlado: no existe writer,
#     R-R2BPRE-02), frente al registro F05 con entidades, frente al abono M2 y
#     frente a OP-21 toca_inversion del mismo hecho; OP-21T con dos cuentas
#     nuevas frente a una transferencia F05 con las mismas cuentas al reves;
#     OP-21P frente a OP-21P, corregir_vinculo y OP-17 del mismo hecho; OP-21T
#     frente a OP-11 de una pata; C3 OP-12A enganchado frente a OP-21P; OP-21
#     sobre una devolucion (§3.4) frente a OP-13, OP-03 y OP-21 del original.
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos;
#   capacidad reversible nunca excedida y ninguna actualizacion perdida.
# Version: 0.1.0 (F04-R2 R2-B)
# ============================================================

from __future__ import annotations

import dataclasses
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

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError
from app.repositories import relaciones_repository as repo_rel
from app.repositories import tesoreria_repository as repo_tes
from app.services.correcciones_service import DatosCorreccion
from conftest import _crear_cuenta
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_138_f04_r1_discriminantes import prevision_manual, version_hecho, vincular
from test_139_f04_r1_concurrencia_serial import LOGGER, OK, Paso, bloqueados, deadlocks, esperar, reintentos
from test_140_f04_r3_op22 import alta, nueva_entidad, op22  # noqa: F401
from test_14b_f04_r2a_concurrencia_serial import Pausa
from test_14c_f04_r2b_discriminantes import (  # noqa: F401
    MOTIVO,
    _todas,
    capacidad,
    datos_pago,
    gasto,
    nuevo,
    op21,
    sql_admin,
    transferencia,
    version_mov,
)

D = decimal.Decimal
F = dt.date.fromisoformat
FUTURO = lambda: dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)  # noqa: E731 - reloj de los adaptadores F05

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R2B_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R2B_CONCURRENCIA=1)")
ORDENES = ["A-primero", "B-primero"]


# ------------------------------------------------------------------ arnes
def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R2B_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


class UpdateControlado(threading.Thread):
    """Deshabilitar la cuenta: no existe writer (R-R2BPRE-02). UPDATE en una
    transaccion propia que, una vez escrito, espera a `sigue` para confirmar."""

    def __init__(self, dsn: str, cuenta: uuid.UUID) -> None:
        super().__init__(name="DESHABILITAR", daemon=True)
        self.dsn, self.cuenta = dsn, cuenta
        self.llego, self.sigue = threading.Event(), threading.Event()
        self.error = None
        self.resultado = None

    def run(self) -> None:
        try:
            with psycopg.connect(self.dsn) as c:
                c.execute("UPDATE gapto.cuentas SET enabled = false, row_version = row_version + 1 WHERE id = %s",
                          (self.cuenta,))
                self.llego.set()
                self.sigue.wait(90)
                c.commit()
        except Exception as exc:  # pragma: no cover - se registra
            self.error = f"{type(exc).__name__}: {exc}"


def correr(dsn, caplog, primero, segundo, retener) -> dict:
    """`primero` y `segundo`: Paso. `retener`: objeto con llego/sigue (Pausa o UpdateControlado)."""
    caplog.clear()
    antes = deadlocks(dsn)
    traza: dict = {"orden": [primero.name, segundo.name]}
    try:
        primero.start()
        traza["primero_retenido"] = retener.llego.wait(30)
        segundo.start()
        esperar(lambda: not segundo.is_alive() or len(bloqueados(dsn)) >= 1, 30)
        traza["segundo_bloqueado"] = segundo.is_alive()
    finally:
        retener.sigue.set()
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


def comunes(traza: dict) -> None:
    assert traza["primero_retenido"], traza
    assert not traza["vivos"], traza
    assert traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza


def paso_op21p(op21, contexto, admin, g, **kw) -> Paso:
    datos = datos_pago(admin, contexto.owner_user_id, g, **kw)
    return Paso("OP-21P", lambda: op21.corregir_pago(nuevo(contexto), datos))


def paso_adaptador(unidad, contexto, admin, g, **kw) -> Paso:
    from app.api.ejecucion_correccion import corregir_pago

    datos = datos_pago(admin, contexto.owner_user_id, g, **kw)

    def fn():
        r = corregir_pago(unidad, nuevo(contexto), datos)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    return Paso("OP-21P", fn)


def datos_t(admin, owner, t, **kw):
    from app.services.correccion_tesoreria_service import DatosCorreccionTransferencia

    base = dict(hecho_id=t.hecho, row_version_esperada=version_hecho(admin, owner, t.hecho),
                movimientos_row_version_esperadas={m: version_mov(admin, owner, m) for m in (t.salida, t.entrada)},
                motivo=MOTIVO, error_de_registro=True)
    base.update(kw)
    return DatosCorreccionTransferencia(**base)


def paso_adaptador_t(unidad, contexto, admin, t, **kw) -> Paso:
    from app.api.ejecucion_correccion import corregir_transferencia

    datos = datos_t(admin, contexto.owner_user_id, t, **kw)

    def fn():
        r = corregir_transferencia(unidad, nuevo(contexto), datos)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    return Paso("OP-21T", fn)


def cuenta_de(admin, movimiento) -> uuid.UUID:
    return _todas(admin, "SELECT cuenta_id FROM gapto.movimientos_tesoreria WHERE id = %s", (movimiento,))[0][0]


def pausa_en_movimientos(monkeypatch, hilo: str) -> Pausa:
    """OP-21P / OP-21T retenido con TODOS sus locks (nivel 6 ya adquirido)."""
    from app.repositories import correccion_tesoreria_repository as repo_ct  # diferido: falla por test en la base

    return Pausa(monkeypatch, repo_ct, "bloquear_movimientos", hilo)


def sin_capacidad(nombre: str) -> str:
    return f"RuntimeError: {nombre}"


# ==================================================================
# Cuenta nueva frente a M4 (§6.7.1)
# ==================================================================
@pytest.mark.parametrize("operacion", ["OP-21P", "OP-21T"])
@pytest.mark.parametrize("orden", ORDENES)
def test_cuenta_nueva_frente_a_m4_retirando_la_capacidad(dsn, unidad, op22, servicio_transferencias, contexto, admin,
                                                         cuenta, cuenta_destino, operacion, orden, caplog,
                                                         monkeypatch):
    from app.capacidades import servicio as capacidades

    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x = _crear_cuenta(admin, owner)
    codigo = "PAGAR_GASTO" if operacion == "OP-21P" else "TRANSFERIR_ENTRADA"
    capacidad(admin, owner, x, codigo)
    if operacion == "OP-21P":
        g = gasto(op22, contexto, cuenta)
        a = paso_adaptador(unidad, contexto, admin, g, cuenta_id=x, importe=D("47.82"))
        movimiento = g.movimiento
    else:
        t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
        a = paso_adaptador_t(unidad, contexto, admin, t, cuenta_destino_id=x)
        movimiento = t.entrada
    version_x = _todas(admin, "SELECT row_version FROM gapto.cuentas WHERE id = %s", (x,))[0][0]
    m4 = Paso("M4", lambda: unidad.ejecutar(nuevo(contexto), lambda s: capacidades.desactivar(
        s, cuenta_id=x, capacidad=codigo, row_version=version_x)))
    if orden == "A-primero":
        retener = pausa_en_movimientos(monkeypatch, a.name)
        traza = correr(dsn, caplog, a, m4, retener)
    else:
        retener = Pausa(monkeypatch, capacidades, "_bloquear_cuenta", "M4")
        traza = correr(dsn, caplog, m4, a, retener)
    evidencia(f"m4_{operacion}_{orden}", traza)
    comunes(traza)
    assert traza["M4"] == OK, traza
    tiene = _todas(admin, "SELECT count(*) FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND "
                          "capacidad_codigo = %s", (x, codigo))[0][0]
    assert tiene == 0
    if orden == "A-primero":  # la correccion valido la capacidad antes de que M4 la retirara
        assert traza[a.name] == OK and cuenta_de(admin, movimiento) == x, traza
    else:  # M4 retiro primero: la correccion ya no encuentra la capacidad (sin escritura)
        assert traza[a.name] == sin_capacidad("CUENTA_SIN_CAPACIDAD"), traza
        assert cuenta_de(admin, movimiento) != x


# ==================================================================
# Cuenta nueva frente a deshabilitarla (UPDATE controlado)
# ==================================================================
@pytest.mark.parametrize("operacion", ["OP-21P", "OP-21T", "OP-21P-motor"])
@pytest.mark.parametrize("orden", ORDENES)
def test_cuenta_nueva_frente_a_deshabilitarla(dsn, unidad, op22, op21, servicio_transferencias, contexto, admin,
                                              cuenta, cuenta_destino, operacion, orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x = _crear_cuenta(admin, owner)
    capacidad(admin, owner, x, "PAGAR_GASTO", "TRANSFERIR_ENTRADA")
    if operacion == "OP-21P":
        g = gasto(op22, contexto, cuenta)
        a, movimiento = paso_adaptador(unidad, contexto, admin, g, cuenta_id=x), g.movimiento
    elif operacion == "OP-21P-motor":  # sin adaptador: el lock de la cuenta lo toma el motor (§6.7.1)
        g = gasto(op22, contexto, cuenta)
        a, movimiento = paso_op21p(op21, contexto, admin, g, cuenta_id=x), g.movimiento
    else:
        t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
        a, movimiento = paso_adaptador_t(unidad, contexto, admin, t, cuenta_destino_id=x), t.entrada
    deshabilitar = UpdateControlado(dsn, x)
    if orden == "A-primero":
        deshabilitar.sigue.set()  # de segundo: confirma en cuanto obtiene la fila
        traza = correr(dsn, caplog, a, deshabilitar, pausa_en_movimientos(monkeypatch, a.name))
    else:
        traza = correr(dsn, caplog, deshabilitar, a, deshabilitar)
    evidencia(f"deshabilitar_{operacion}_{orden}", traza)
    comunes(traza)
    assert traza["DESHABILITAR"] == OK
    if orden == "A-primero":
        assert traza[a.name] == OK and cuenta_de(admin, movimiento) == x, traza
    else:
        assert traza[a.name] == CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO.value, traza
        assert cuenta_de(admin, movimiento) != x


# ==================================================================
# Cuenta nueva frente al registro F05 con entidades y al abono M2
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_cuenta_nueva_frente_al_registro_f05_con_entidades(dsn, unidad, op22, contexto, admin, cuenta, actor_a,
                                                          orden, caplog, monkeypatch):
    from app.api import ejecucion_registro
    from app.api.dto_registro import IntencionIngresoCobrado

    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x = _crear_cuenta(admin, owner)
    capacidad(admin, owner, x, "PAGAR_GASTO", "RECIBIR_INGRESO")
    g = gasto(op22, contexto, cuenta)
    a = paso_adaptador(unidad, contexto, admin, g, cuenta_id=x, importe=D("47.82"))
    intencion = IntencionIngresoCobrado.model_validate({
        "intencion_id": str(uuid.uuid4()), "importe": "25.00", "moneda": "EUR", "fecha_hecho": "2027-06-01",
        "cuenta_id": str(x), "presupuestable": False, "atribucion": "SIN_INDICAR",
        "categoria": {"estado": "SIN_CATEGORIA"}, "contexto_id": str(nueva_entidad(admin, owner, "CONTEXTO"))})

    def ingreso():
        r = ejecucion_registro.registrar_ingreso_cobrado(unidad, nuevo(contexto), intencion, reloj=FUTURO)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    b = Paso("F05", ingreso)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        # F05 retenido con el advisory y SIN la cuenta: el candidato A (cuenta antes del advisory) cierra ciclo.
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, ejecucion_registro, "tomar_inversiones", "F05"))
    evidencia(f"registro_f05_entidades_{orden}", traza)
    comunes(traza)
    assert traza["OP-21P"] == OK and traza["F05"] == OK, traza
    assert cuenta_de(admin, g.movimiento) == x
    assert _todas(admin, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                  (intencion.intencion_id,)) == [(1,)]


@pytest.mark.parametrize("orden", ORDENES)
def test_cuenta_nueva_frente_al_abono_m2(dsn, unidad, op22, servicio_devoluciones, contexto, admin, cuenta, orden,
                                         caplog, monkeypatch):
    from app.api import ejecucion_devolucion
    from app.api.dto_devolucion import IntencionAbono

    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x = _crear_cuenta(admin, owner)
    capacidad(admin, owner, x, "PAGAR_GASTO", "RECIBIR_INGRESO")
    # OP-21P corrige la PROPIA compra (cuenta -> x); el abono de su devolucion entra en x por RECIBIR_INGRESO.
    # Abono: x -> compra -> devolucion. Con el candidato B (hecho antes que la cuenta) hay ciclo; con C no.
    compra = gasto(op22, contexto, cuenta, "100.0000")
    dev = datos_devolucion(compra.hecho, importe=D("30.0000"), fecha_hecho=F("2027-06-02"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    g = compra
    a = paso_adaptador(unidad, contexto, admin, g, cuenta_id=x, importe=D("90.00"))
    abono = IntencionAbono(intencion_id=uuid.uuid4(), cuenta_id=x, fecha=F("2027-06-03"))

    def abonar():
        r = ejecucion_devolucion.registrar_abono(unidad, nuevo(contexto), dev.hecho_id, abono, reloj=FUTURO)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    b = Paso("M2", abonar)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, ejecucion_devolucion, "bloquear_cuentas", "M2"))
    evidencia(f"abono_m2_{orden}", traza)
    comunes(traza)
    assert traza["OP-21P"] == OK and traza["M2"] == OK, traza
    assert cuenta_de(admin, g.movimiento) == x
    assert _todas(admin, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
                  (dev.hecho_id,)) == [(1,)]


# ==================================================================
# Cuenta nueva frente a OP-21 toca_inversion del mismo hecho
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_cuenta_nueva_frente_a_op21_toca_inversion(dsn, unidad, op22, servicio_correcciones, contexto, admin, cuenta,
                                                  orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x = _crear_cuenta(admin, owner)
    capacidad(admin, owner, x, "PAGAR_GASTO")
    g = gasto(op22, contexto, cuenta)
    a = paso_adaptador(unidad, contexto, admin, g, cuenta_id=x, importe=D("47.82"))
    v = version_hecho(admin, owner, g.hecho)
    b = Paso("OP-21", lambda: servicio_correcciones.corregir(nuevo(contexto), DatosCorreccion(
        hecho_id=g.hecho, row_version_esperada=v, motivo="descripcion falsa", toca_inversion=True,
        efectos_a_actualizar={g.efecto: {"descripcion": "corregida"}})))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21"))
    evidencia(f"op21_toca_inversion_{orden}", traza)
    comunes(traza)
    ganador, perdedor = ("OP-21P", "OP-21") if orden == "A-primero" else ("OP-21", "OP-21P")
    assert traza[ganador] == OK and traza[perdedor] == CodigoError.VERSION_DESFASADA.value, traza
    assert (cuenta_de(admin, g.movimiento) == x) == (ganador == "OP-21P")


# ==================================================================
# OP-21T con dos cuentas nuevas frente a una transferencia F05 inversa
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_op21t_dos_cuentas_frente_a_transferencia_inversa(dsn, unidad, servicio_transferencias, contexto, admin,
                                                          cuenta, cuenta_destino, orden, caplog, monkeypatch):
    from app.api import ejecucion_registro
    from app.api.dto_registro import IntencionTransferencia

    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    x, y = _crear_cuenta(admin, owner), _crear_cuenta(admin, owner)
    for c in (x, y):
        capacidad(admin, owner, c, "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA")
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    a = paso_adaptador_t(unidad, contexto, admin, t, cuenta_origen_id=x, cuenta_destino_id=y)
    intencion = IntencionTransferencia.model_validate({
        "intencion_id": str(uuid.uuid4()), "importe": "15.00", "moneda": "EUR", "fecha_hecho": "2027-06-01",
        "cuenta_origen_id": str(y), "cuenta_destino_id": str(x)})

    def transferir():
        r = ejecucion_registro.registrar_transferencia(unidad, nuevo(contexto), intencion, reloj=FUTURO)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    b = Paso("F05", transferir)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21T"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, ejecucion_registro, "bloquear_cuentas", "F05"))
    evidencia(f"op21t_dos_cuentas_inversa_{orden}", traza)
    comunes(traza)
    assert traza["OP-21T"] == OK and traza["F05"] == OK, traza
    assert (cuenta_de(admin, t.salida), cuenta_de(admin, t.entrada)) == (x, y)


# ==================================================================
# OP-21P frente a OP-21P, corregir_vinculo y OP-17 del mismo hecho
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_op21p_frente_a_op21p_mismo_hecho(dsn, op22, op21, contexto, admin, cuenta, orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    a = paso_op21p(op21, contexto, admin, g, importe=D("47.82"))
    b = paso_op21p(op21, contexto, admin, g, importe=D("40.00"))
    b.name = "OP-21P-b"
    primero, segundo = (a, b) if orden == "A-primero" else (b, a)
    traza = correr(dsn, caplog, primero, segundo, pausa_en_movimientos(monkeypatch, primero.name))
    evidencia(f"op21p_op21p_{orden}", traza)
    comunes(traza)
    assert traza[primero.name] == OK and traza[segundo.name] == CodigoError.VERSION_DESFASADA.value, traza
    esperado = D("-47.8200") if primero is a else D("-40.0000")
    assert _todas(admin, "SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s",
                  (g.movimiento,)) == [(esperado,)]


@pytest.mark.parametrize("orden", ORDENES)
def test_op21p_frente_a_corregir_vinculo(dsn, op22, op21, servicio_previsiones, contexto, admin, cuenta, orden,
                                         caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, prevision, g.hecho, "40.0000")
    vinculo = _todas(admin, "SELECT id FROM gapto.prevision_hechos WHERE hecho_id = %s", (g.hecho,))[0][0]
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    a = paso_op21p(op21, contexto, admin, g, importe=D("45.00"))
    b = Paso("corregir_vinculo", lambda: servicio_previsiones.corregir_vinculo(
        nuevo(contexto), vinculo_id=vinculo, versiones_esperadas={prevision: version}, nuevo_importe=D("48.00"),
        motivo="vinculo"))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "corregir_vinculo"))
    evidencia(f"op21p_corregir_vinculo_{orden}", traza)
    comunes(traza)
    asignado = _todas(admin, "SELECT importe_asignado FROM gapto.prevision_hechos WHERE id = %s", (vinculo,))[0][0]
    if orden == "A-primero":  # el total ya es 45: subir el vinculo a 48 crearia exceso (G-R1-C)
        assert traza["OP-21P"] == OK and traza["corregir_vinculo"] == "PORCION_DE_REALIDAD_EXCEDIDA", traza
        assert asignado == D("40.0000")
    else:  # vinculo a 48 y despues el total a 45: se confirma con requiere_revision (R1-OBS-01)
        assert traza["OP-21P"] == OK and traza["corregir_vinculo"] == OK, traza
        assert asignado == D("48.0000") and a.resultado.requiere_revision


@pytest.mark.parametrize("orden", ORDENES)
def test_op21p_frente_a_op17_del_mismo_hecho(dsn, op22, op21, servicio_previsiones, contexto, admin, cuenta, orden,
                                             caplog, monkeypatch):
    from app.core.modelos_prevision import DatosVinculo

    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    a = paso_op21p(op21, contexto, admin, g, importe=D("40.00"))
    b = Paso("OP-17", lambda: servicio_previsiones.vincular_realidad(
        nuevo(contexto), prevision_id=prevision, row_version_esperada=version,
        datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=g.hecho, importe_asignado=D("48.72"),
                           marcar_realizada=False)))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-17"))
    evidencia(f"op21p_op17_{orden}", traza)
    comunes(traza)
    vinculos = _todas(admin, "SELECT importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s", (g.hecho,))
    if orden == "A-primero":  # total 40: asignar 48,72 lo excede
        assert traza["OP-21P"] == OK and traza["OP-17"] == "PORCION_DE_REALIDAD_EXCEDIDA", traza
        assert vinculos == []
    else:
        assert traza["OP-21P"] == OK and traza["OP-17"] == OK, traza
        assert vinculos == [(D("48.7200"),)] and a.resultado.requiere_revision


# ==================================================================
# OP-21T frente a OP-11 de una pata; C3 OP-12A frente a OP-21P
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_op21t_frente_a_reversion_de_una_pata(dsn, op21, servicio_transferencias, servicio_tesoreria, contexto, admin,
                                             cuenta, cuenta_destino, orden, caplog, monkeypatch):
    from app.core.modelos_tesoreria import DatosReversion
    from test_14c_f04_r2b_discriminantes import corregir_t

    caplog.set_level(logging.WARNING, logger=LOGGER)
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    datos = datos_t(admin, contexto.owner_user_id, t, importe=D("90"))
    a = Paso("OP-21T", lambda: op21.corregir_transferencia(nuevo(contexto), datos))
    b = Paso("OP-11", lambda: servicio_tesoreria.revertir_movimiento(nuevo(contexto), DatosReversion(
        reversion_id=uuid.uuid4(), movimiento_original_id=t.salida, cuenta_id=cuenta,
        fecha_movimiento=F("2027-06-05"), importe=D("10.00"))))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21T"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_tes, "contexto_de_reversion", "OP-11"))
    evidencia(f"op21t_op11_{orden}", traza)
    comunes(traza)
    assert traza["OP-11"] == OK, traza
    salida = _todas(admin, "SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s", (t.salida,))[0][0]
    if orden == "A-primero":
        assert traza["OP-21T"] == OK and salida == D("-90.0000"), traza
    else:  # ya hay reversion: la transferencia no se corrige (T-2)
        assert traza["OP-21T"] == CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO.value and salida == D("-100.0000")


@pytest.mark.parametrize("orden", ORDENES)
def test_c3_op12a_enganchado_frente_a_op21p(dsn, op22, op21, servicio_posiciones, contexto, admin, cuenta,
                                           contraparte, orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    g = gasto(op22, contexto, cuenta)
    a = paso_op21p(op21, contexto, admin, g, importe=D("47.82"))
    posicion = dataclasses.replace(alta(g.hecho, contraparte, importe="5.0000"),
                                   hecho_row_version_esperada=version_hecho(admin, owner, g.hecho),
                                   fecha_hecho=F("2027-06-01"), fecha_inicio_seguimiento=F("2027-06-01"))
    b = Paso("OP-12A", lambda: servicio_posiciones.crear_posicion(nuevo(contexto), posicion))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_en_movimientos(monkeypatch, "OP-21P"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-12A"))
    evidencia(f"c3_op12a_op21p_{orden}", traza)
    comunes(traza)
    ganador, perdedor = ("OP-21P", "OP-12A") if orden == "A-primero" else ("OP-12A", "OP-21P")
    assert traza[ganador] == OK and traza[perdedor] != OK, traza
    assert traza[perdedor] in (CodigoError.VERSION_DESFASADA.value, CodigoError.CORRECCION_AGREGADA_REQUERIDA.value)


# ==================================================================
# §3.4 · OP-21 sobre una devolucion frente al original
# ==================================================================
def _dev(servicio, servicio_efectos, servicio_devoluciones, contexto, importe="45.0000"):
    original = crear_origen(servicio, servicio_efectos, contexto)  # GASTO 120
    dev = datos_devolucion(original, importe=D(importe))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    return original, dev


def _op21_dev(servicio_correcciones, contexto, admin, dev, delta: str) -> Paso:
    v = version_hecho(admin, contexto.owner_user_id, dev.hecho_id)
    return Paso("OP-21-dev", lambda: servicio_correcciones.corregir(nuevo(contexto), DatosCorreccion(
        hecho_id=dev.hecho_id, row_version_esperada=v, motivo="devolucion tecleada mal",
        efectos_a_actualizar={dev.efecto_id: {"importe_delta": D(delta)}})))


def devuelto(admin, original) -> decimal.Decimal:
    return _todas(admin, "SELECT COALESCE(sum(abs(e.importe_delta)), 0) FROM gapto.hecho_relaciones r "
                         "JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id AND d.estado = 'ACTIVO' "
                         "JOIN gapto.hecho_efectos e ON e.hecho_id = d.id "
                         "WHERE r.hecho_destino_id = %s AND r.tipo_relacion = 'DEVOLUCION_DE'", (original,))[0][0]


def capacidad_original(admin, original) -> decimal.Decimal:
    return abs(_todas(admin, "SELECT COALESCE(sum(importe_delta), 0) FROM gapto.hecho_efectos "
                             "WHERE hecho_id = %s AND tipo_efecto = 'GASTO'", (original,))[0][0])


@pytest.mark.parametrize("orden", ORDENES)
def test_34_op21_devolucion_frente_a_op13_original(dsn, servicio, servicio_efectos, servicio_devoluciones,
                                                   servicio_correcciones, contexto, admin, orden, caplog,
                                                   monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    original, dev = _dev(servicio, servicio_efectos, servicio_devoluciones, contexto)
    a = _op21_dev(servicio_correcciones, contexto, admin, dev, "-80")  # 80 + 50 > 120: solo cabe uno
    b = Paso("OP-13", lambda: servicio_devoluciones.devolver(nuevo(contexto), datos_devolucion(
        original, importe=D("50.0000"))))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21-dev"))
    else:  # OP-13 retenido DESPUES de leer lo devuelto (45): el punto que expone la falta de lock
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "devuelto_acumulado", "OP-13"))
    evidencia(f"34_op21dev_op13_{orden}", traza)
    comunes(traza)
    ganador, perdedor = ("OP-21-dev", "OP-13") if orden == "A-primero" else ("OP-13", "OP-21-dev")
    assert traza[ganador] == OK and traza[perdedor] == CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE.value, traza
    assert devuelto(admin, original) <= capacidad_original(admin, original)


@pytest.mark.parametrize("orden", ORDENES)
def test_34_op21_devolucion_frente_a_op03_original(dsn, servicio, servicio_efectos, servicio_devoluciones,
                                                   servicio_correcciones, contexto, admin, orden, caplog,
                                                   monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    original, dev = _dev(servicio, servicio_efectos, servicio_devoluciones, contexto)
    a = _op21_dev(servicio_correcciones, contexto, admin, dev, "-60")
    v = version_hecho(admin, contexto.owner_user_id, original)
    b = Paso("OP-03", lambda: servicio.anular_hecho(nuevo(contexto), hecho_id=original, row_version_esperada=v,
                                                    motivo_anulacion="duplicado"))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21-dev"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-03"))
    evidencia(f"34_op21dev_op03_{orden}", traza)
    comunes(traza)
    assert traza["OP-21-dev"] == OK and traza["OP-03"] == CodigoError.HECHO_CON_REALIDAD_ASOCIADA.value, traza
    assert _todas(admin, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (original,)) == [("ACTIVO",)]
    assert devuelto(admin, original) == D("60.0000")


@pytest.mark.parametrize("orden", ORDENES)
def test_34_op21_devolucion_frente_a_op21_original(dsn, servicio, servicio_efectos, servicio_devoluciones,
                                                   servicio_correcciones, contexto, admin, orden, caplog,
                                                   monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    original, dev = _dev(servicio, servicio_efectos, servicio_devoluciones, contexto)
    efecto_original = _todas(admin, "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s", (original,))[0][0]
    a = _op21_dev(servicio_correcciones, contexto, admin, dev, "-70")  # 70 > 60: solo cabe uno
    v = version_hecho(admin, contexto.owner_user_id, original)
    b = Paso("OP-21-orig", lambda: servicio_correcciones.corregir(nuevo(contexto), DatosCorreccion(
        hecho_id=original, row_version_esperada=v, motivo="original tecleado mal",
        efectos_a_actualizar={efecto_original: {"importe_delta": D("60")}})))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21-dev"))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21-orig"))
    evidencia(f"34_op21dev_op21orig_{orden}", traza)
    comunes(traza)
    ganador, perdedor = ("OP-21-dev", "OP-21-orig") if orden == "A-primero" else ("OP-21-orig", "OP-21-dev")
    assert traza[ganador] == OK and traza[perdedor] == CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE.value, traza
    assert devuelto(admin, original) <= capacidad_original(admin, original)


def test_34_conjunto_cambiado_reintenta_y_bloquea_las_dos_raices_juntas(servicio, servicio_efectos,
                                                                        servicio_devoluciones, servicio_correcciones,
                                                                        contexto, admin, monkeypatch):
    """§3.4.2: el conjunto {devolucion, original} se adquiere en UNA llamada al
    nivel de hechos (por UUID) y, si la relectura difiere, ConjuntoCambiado
    reinicia la transaccion completa (segundo intento)."""
    from app.repositories import correcciones_repository as repo_corr

    original, dev = _dev(servicio, servicio_efectos, servicio_devoluciones, contexto)
    llamadas: list[list[uuid.UUID]] = []
    real_bloquear = repo_rel.bloquear_hechos

    def espia(sesion, ids):
        llamadas.append(sorted(ids, key=str))
        return real_bloquear(sesion, ids)

    real_leer = repo_corr.originales_de_devolucion
    lecturas = {"n": 0}

    def primera_lectura_obsoleta(sesion, hecho_id):
        lecturas["n"] += 1
        filas = real_leer(sesion, hecho_id)
        return [] if lecturas["n"] == 1 else filas  # intento 1: conjunto previo obsoleto

    monkeypatch.setattr(repo_rel, "bloquear_hechos", espia)
    monkeypatch.setattr(repo_corr, "originales_de_devolucion", primera_lectura_obsoleta)
    _op21_dev(servicio_correcciones, contexto, admin, dev, "-50").fn()
    assert servicio_correcciones.ultima_traza.intentos_realizados == 2
    assert sorted([dev.hecho_id, original], key=str) in llamadas
