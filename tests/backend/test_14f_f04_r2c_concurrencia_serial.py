# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14f_f04_r2c_concurrencia_serial.py
# Ruta: tests/backend/test_14f_f04_r2c_concurrencia_serial.py
# Descripcion: F04-R2 R2-C (contrato F04-R2 v0.9 §2.3.8, §2.3.9, §6; mandato
#   F04-R2C v1.0 P6). Bateria SERIAL y determinista, FUERA de la suite general:
#   solo con GAPTO_F04R2C_CONCURRENCIA=1. Si GAPTO_F04R2C_EVIDENCIA apunta a una
#   carpeta, cada escenario deja su JSON. Nunca en paralelo.
#
#   Tecnica (la de R2-A/R2-B, test_14b/test_14d): el PRIMER paso se detiene
#   DENTRO de su transaccion con sus locks (OP-03P tras bloquear sus
#   movimientos, el ultimo nivel L6; los demas tras su primer lock); con el
#   primero retenido se lanza el segundo y se espera a que termine o quede
#   bloqueado; despues se libera el primero. Ambos ordenes, cada uno con UN
#   resultado equivalente al serial y un oraculo de estado CONFIRMADO.
#   Pares de §2.3.9 con la operacion REAL:
#     1 OP-03P(H) frente a OP-13 con H como original;
#     2 GATE §2.3.8: OP-03P(D, devolucion con abono) frente a OP-13 nueva sobre
#       su original O (D sin lock de O): acumulado <= capacidad, equivalente al
#       serial, sin doble consumo ni devolucion admitida indebidamente;
#     3 OP-03P(H) frente a OP-11 sobre su movimiento, con sus triggers reales
#       (fn_check_reversion_movimiento, fn_check_movimiento_padre);
#     4 OP-03P(D) frente al abono de M2 sobre D;
#     5 OP-03P(H) frente a OP-17 y corregir_vinculo;
#     6 OP-03P frente a M4 sobre la cuenta del movimiento (control);
#     7 OP-03P frente a OP-21P, OP-21T y OP-21 (§3.4) del mismo hecho.
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos;
#   nunca un 23503 ni un P0001 sin traducir.
# Version: 0.1.0 (F04-R2 R2-C)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import logging
import os
import pathlib
import uuid

import pytest

from app.core.errores import CodigoError
from app.core.modelos_tesoreria import DatosReversion
from app.repositories import relaciones_repository as repo_rel
from app.repositories import tesoreria_repository as repo_tes
from conftest import _crear_cuenta
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_138_f04_r1_discriminantes import prevision_manual, vincular
from test_139_f04_r1_concurrencia_serial import LOGGER, OK, Paso
from test_140_f04_r3_op22 import op22  # noqa: F401
from test_14b_f04_r2a_concurrencia_serial import Pausa
from test_14c_f04_r2b_discriminantes import _todas, capacidad, gasto, nuevo, op21, transferencia  # noqa: F401
from test_14d_f04_r2b_concurrencia_serial import (
    FUTURO,
    ORDENES,
    _op21_dev,
    capacidad_original,
    comunes,
    correr,
    datos_t,
    devuelto,
    paso_op21p,
)
from test_14e_f04_r2c_discriminantes import datos, op03p  # noqa: F401

D = decimal.Decimal
F = dt.date.fromisoformat

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R2C_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R2C_CONCURRENCIA=1)")
TRADUCIDOS = {c.value for c in CodigoError}


# ------------------------------------------------------------------ arnes
def evidencia(nombre: str, traza: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R2C_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(traza, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def paso_op03p(op03p, contexto, admin, hecho, **kw) -> Paso:
    pedido = datos(admin, contexto.owner_user_id, hecho, **kw)
    return Paso("OP-03P", lambda: op03p.anular_registro(nuevo(contexto), pedido))


def pausa_op03p(monkeypatch) -> Pausa:
    """OP-03P retenido con TODOS sus locks (L6 ya adquirido)."""
    from app.repositories import correccion_tesoreria_repository as repo_ct

    return Pausa(monkeypatch, repo_ct, "bloquear_movimientos", "OP-03P")


def traducido(traza: dict, *pasos: str) -> None:
    """Nunca un 23503 ni un P0001 sin traducir: todo error es un CodigoError."""
    for p in pasos:
        assert traza[p] == OK or traza[p] in TRADUCIDOS, traza


def estado(admin, hecho) -> str:
    return _todas(admin, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0][0]


def con_abono(servicio, servicio_efectos, servicio_devoluciones, contexto, cuenta, importe="45.0000"):
    """Devolucion D (OP-13) con su abono ya conciliado (entrada +importe) sobre un original O de 120."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    dev = datos_devolucion(original, importe=D(importe), movimiento_id=uuid.uuid4(), conciliacion_id=uuid.uuid4(),
                           cuenta_id=cuenta, fecha_movimiento=F("2027-05-20"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    return original, dev


# ==================================================================
# 1 · OP-03P(H) frente a OP-13 con H como original
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_1_op03p_frente_a_op13_sobre_el_mismo_hecho(dsn, op22, op03p, servicio_devoluciones, contexto, admin, cuenta,
                                                    orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta, "100.0000")
    a = paso_op03p(op03p, contexto, admin, g.hecho)
    b = Paso("OP-13", lambda: servicio_devoluciones.devolver(nuevo(contexto), datos_devolucion(
        g.hecho, importe=D("30.0000"), fecha_hecho=F("2027-06-02"))))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-13"))
    evidencia(f"1_op03p_op13_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-13")
    devoluciones = _todas(admin, "SELECT count(*) FROM gapto.hecho_relaciones WHERE hecho_destino_id = %s", (g.hecho,))
    if orden == "A-primero":  # serial: anulado primero; OP-13 rechaza el original ANULADO
        assert traza["OP-03P"] == OK and traza["OP-13"] != OK, traza
        assert estado(admin, g.hecho) == "ANULADO" and devoluciones == [(0,)]
    else:  # serial: la devolucion primero; L-R ve la dependencia -> G-R1-A
        assert traza["OP-13"] == OK and traza["OP-03P"] == CodigoError.HECHO_CON_REALIDAD_ASOCIADA.value, traza
        assert estado(admin, g.hecho) == "ACTIVO" and devoluciones == [(1,)]


# ==================================================================
# 2 · GATE §2.3.8: OP-03P(D) sin lock de O frente a OP-13 nueva sobre O
# ==================================================================
@pytest.mark.parametrize("punto_op13", ["tras_lock_del_original", "tras_leer_lo_devuelto"])
@pytest.mark.parametrize("importe_nueva", ["60.0000", "100.0000"])
@pytest.mark.parametrize("orden", ORDENES)
def test_2_gate_op03p_devolucion_frente_a_op13_nueva_sobre_el_original(
        dsn, op03p, servicio, servicio_efectos, servicio_devoluciones, contexto, admin, cuenta, orden,
        importe_nueva, punto_op13, caplog, monkeypatch):
    """O = 120, D = 45 con abono. Una devolucion nueva de 60 cabe siempre; una
    de 100 solo cabe si D ya no cuenta. Oraculos sobre el estado CONFIRMADO:
    acumulado <= capacidad, resultado igual a uno de los dos seriales, sin
    doble consumo ni devolucion admitida indebidamente."""
    if orden == "A-primero" and punto_op13 == "tras_leer_lo_devuelto":
        pytest.skip("el punto de pausa de OP-13 solo aplica cuando OP-13 va primero")
    caplog.set_level(logging.WARNING, logger=LOGGER)
    original, dev = con_abono(servicio, servicio_efectos, servicio_devoluciones, contexto, cuenta)
    nueva = datos_devolucion(original, importe=D(importe_nueva), fecha_hecho=F("2027-05-25"))
    a = paso_op03p(op03p, contexto, admin, dev.hecho_id)
    b = Paso("OP-13", lambda: servicio_devoluciones.devolver(nuevo(contexto), nueva))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        atributo = "bloquear_hechos" if punto_op13 == "tras_lock_del_original" else "devuelto_acumulado"
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, atributo, "OP-13"))
    traza["devuelto_final"] = str(devuelto(admin, original))
    evidencia(f"2_gate_{orden}_{importe_nueva}_{punto_op13}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-13")
    assert traza["OP-03P"] == OK, traza  # OP-03P(D) solo reduce lo comprometido: nunca lo bloquea O
    assert estado(admin, dev.hecho_id) == "ANULADO"
    # Oraculos del gate (estado confirmado)
    final = devuelto(admin, original)
    assert final <= capacidad_original(admin, original), traza                     # acumulado <= capacidad
    nueva_existe = _todas(admin, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s AND estado = 'ACTIVO'",
                          (nueva.hecho_id,)) == [(1,)]
    assert (traza["OP-13"] == OK) == nueva_existe                                  # sin escritura fantasma
    serial_op03p_primero = {"60.0000": (True, D("60.0000")), "100.0000": (True, D("100.0000"))}[importe_nueva]
    serial_op13_primero = {"60.0000": (True, D("60.0000")), "100.0000": (False, D("0"))}[importe_nueva]
    assert (nueva_existe, final) in (serial_op03p_primero, serial_op13_primero), traza  # equivalente al serial
    assert _todas(admin, "SELECT count(*) FROM gapto.hecho_relaciones WHERE hecho_destino_id = %s",
                  (original,))[0][0] == (2 if nueva_existe else 1)               # D conserva su relacion


# ==================================================================
# 3 · OP-03P(H) frente a OP-11 sobre su movimiento (triggers reales)
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_3_op03p_frente_a_op11_con_sus_triggers(dsn, op22, op03p, servicio_tesoreria, contexto, admin, cuenta, orden,
                                               caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    a = paso_op03p(op03p, contexto, admin, g.hecho)
    b = Paso("OP-11", lambda: servicio_tesoreria.revertir_movimiento(nuevo(contexto), DatosReversion(
        reversion_id=uuid.uuid4(), movimiento_original_id=g.movimiento, cuenta_id=cuenta,
        fecha_movimiento=F("2027-06-05"), importe=D("10.00"))))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_tes, "contexto_de_reversion", "OP-11"))
    evidencia(f"3_op03p_op11_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-11")
    reversiones = _todas(admin, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE reversion_de_movimiento_id = %s",
                         (g.movimiento,))[0][0]
    if orden == "A-primero":  # el movimiento ya esta ANULADO: OP-11 no lo revierte
        assert traza["OP-03P"] == OK and traza["OP-11"] != OK and reversiones == 0, traza
    else:  # ya hay reversion: REVERSION_EXISTENTE releida tras el lock
        assert traza["OP-11"] == OK and reversiones == 1, traza
        assert traza["OP-03P"] == CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO.value and estado(admin, g.hecho) == "ACTIVO"


# ==================================================================
# 4 · OP-03P(D) frente al abono de M2 sobre D
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_4_op03p_frente_al_abono_m2(dsn, unidad, op22, op03p, servicio_devoluciones, contexto, admin, cuenta, orden,
                                    caplog, monkeypatch):
    from app.api import ejecucion_devolucion
    from app.api.dto_devolucion import IntencionAbono

    caplog.set_level(logging.WARNING, logger=LOGGER)
    x = _crear_cuenta(admin, contexto.owner_user_id)
    capacidad(admin, contexto.owner_user_id, x, "PAGAR_GASTO", "RECIBIR_INGRESO")
    compra = gasto(op22, contexto, x, "100.0000")
    dev = datos_devolucion(compra.hecho, importe=D("30.0000"), fecha_hecho=F("2027-06-02"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)  # abono pendiente: D sin tesoreria
    a = paso_op03p(op03p, contexto, admin, dev.hecho_id, movimientos={})  # lo que el llamante ve: sin movimientos
    abono = IntencionAbono(intencion_id=uuid.uuid4(), cuenta_id=x, fecha=F("2027-06-03"))

    def abonar():
        r = ejecucion_devolucion.registrar_abono(unidad, nuevo(contexto), dev.hecho_id, abono, reloj=FUTURO)
        if getattr(r, "codigo", None):
            raise RuntimeError(r.codigo)
        return r
    b = Paso("M2", abonar)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, ejecucion_devolucion, "bloquear_cuentas", "M2"))
    evidencia(f"4_op03p_abono_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P")
    assert traza["M2"] == OK, traza
    conciliaciones = _todas(admin, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
                            (dev.hecho_id,))
    assert estado(admin, dev.hecho_id) == "ACTIVO" and conciliaciones == [(1,)]
    if orden == "A-primero":  # sin tesoreria todavia: no es OP-03P (§2.3.4)
        assert traza["OP-03P"] == CodigoError.CORRECCION_AGREGADA_REQUERIDA.value, traza
    elif not traza["segundo_bloqueado"]:  # M2 retenido sin lock de D: OP-03P lee D sin tesoreria y
        # rechaza sin escribir; equivale al serial OP-03P -> M2 (§2.3.4)
        assert traza["OP-03P"] == CodigoError.CORRECCION_AGREGADA_REQUERIDA.value, traza
    else:  # aparece una conciliacion nueva: conjunto cambiado -> reinicio -> version desfasada
        assert traza["OP-03P"] == CodigoError.VERSION_DESFASADA.value, traza


# ==================================================================
# 5 · OP-03P(H) frente a OP-17 y corregir_vinculo
# ==================================================================
@pytest.mark.parametrize("ruta", ["OP-17", "corregir_vinculo"])
@pytest.mark.parametrize("orden", ORDENES)
def test_5_op03p_frente_a_op17_y_corregir_vinculo(dsn, op22, op03p, servicio_previsiones, contexto, admin, cuenta,
                                                  orden, ruta, caplog, monkeypatch):
    from app.core.modelos_prevision import DatosVinculo

    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    if ruta == "corregir_vinculo":
        vincular(servicio_previsiones, contexto, prevision, g.hecho, "40.0000")
        vinculo = _todas(admin, "SELECT id FROM gapto.prevision_hechos WHERE hecho_id = %s", (g.hecho,))[0][0]
        version = servicio_previsiones.estado_de(contexto, prevision).row_version
        b = Paso(ruta, lambda: servicio_previsiones.corregir_vinculo(
            nuevo(contexto), vinculo_id=vinculo, versiones_esperadas={prevision: version}, nuevo_importe=D("45.00"),
            motivo="vinculo"))
    else:
        version = servicio_previsiones.estado_de(contexto, prevision).row_version
        b = Paso(ruta, lambda: servicio_previsiones.vincular_realidad(
            nuevo(contexto), prevision_id=prevision, row_version_esperada=version,
            datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=g.hecho, importe_asignado=D("40.00"),
                               marcar_realizada=False)))
    a = paso_op03p(op03p, contexto, admin, g.hecho)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", ruta))
    evidencia(f"5_op03p_{ruta}_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", ruta)
    assert traza["OP-03P"] == OK and estado(admin, g.hecho) == "ANULADO", traza
    asignados = _todas(admin, "SELECT importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s", (g.hecho,))
    if orden == "A-primero" and ruta == "OP-17":  # la realidad ya no esta ACTIVA (serial OP-03P -> OP-17)
        assert traza[ruta] != OK and asignados == [], traza
    elif orden == "A-primero":  # serial OP-03P -> corregir_vinculo: espera el lock del hecho y corrige un
        # vinculo sobre un hecho ANULADO (AMB-009; corregir_vinculo no mira el estado del hecho, lectura existente)
        assert traza["segundo_bloqueado"] and traza[ruta] == OK and asignados == [(D("45.0000"),)], traza
    else:  # serial ruta -> OP-03P: el vinculo queda sobre un hecho ANULADO (AMB-009), sin perderse
        assert traza[ruta] == OK and asignados in ([(D("45.0000"),)], [(D("40.0000"),)]), traza


# ==================================================================
# 6 · OP-03P frente a M4 sobre la cuenta del movimiento (control)
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_6_op03p_frente_a_m4_control(dsn, unidad, op22, op03p, contexto, admin, cuenta, orden, caplog, monkeypatch):
    from app.capacidades import servicio as capacidades

    caplog.set_level(logging.WARNING, logger=LOGGER)
    x = _crear_cuenta(admin, contexto.owner_user_id)
    capacidad(admin, contexto.owner_user_id, x, "PAGAR_GASTO")
    g = gasto(op22, contexto, x)
    version_cuenta = _todas(admin, "SELECT row_version FROM gapto.cuentas WHERE id = %s", (x,))[0][0]
    a = paso_op03p(op03p, contexto, admin, g.hecho)
    b = Paso("M4", lambda: unidad.ejecutar(nuevo(contexto), lambda s: capacidades.desactivar(
        s, cuenta_id=x, capacidad="PAGAR_GASTO", row_version=version_cuenta)))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, capacidades, "_bloquear_cuenta", "M4"))
    evidencia(f"6_op03p_m4_{orden}", traza)
    comunes(traza)
    assert traza["OP-03P"] == OK and traza["M4"] == OK, traza
    assert not traza["segundo_bloqueado"], traza  # sin recurso comun: nadie espera
    assert estado(admin, g.hecho) == "ANULADO"


# ==================================================================
# 7 · OP-03P frente a OP-21P, OP-21T y OP-21 (§3.4) del mismo hecho
# ==================================================================
@pytest.mark.parametrize("orden", ORDENES)
def test_7a_op03p_frente_a_op21p(dsn, op22, op21, op03p, contexto, admin, cuenta, orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    g = gasto(op22, contexto, cuenta)
    a = paso_op03p(op03p, contexto, admin, g.hecho)
    b = paso_op21p(op21, contexto, admin, g, importe=D("40.00"))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        from app.repositories import correccion_tesoreria_repository as repo_ct
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_ct, "bloquear_movimientos", "OP-21P"))
    evidencia(f"7a_op03p_op21p_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-21P")
    importe = _todas(admin, "SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s", (g.movimiento,))[0][0]
    if orden == "A-primero":
        assert traza["OP-03P"] == OK and traza["OP-21P"] == CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO.value, traza
        assert estado(admin, g.hecho) == "ANULADO" and importe == D("-48.7200")
    else:
        assert traza["OP-21P"] == OK and traza["OP-03P"] == CodigoError.VERSION_DESFASADA.value, traza
        assert estado(admin, g.hecho) == "ACTIVO" and importe == D("-40.0000")


@pytest.mark.parametrize("orden", ORDENES)
def test_7b_op03p_frente_a_op21t(dsn, op21, op03p, servicio_transferencias, contexto, admin, cuenta, cuenta_destino,
                                 orden, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    a = paso_op03p(op03p, contexto, admin, t.hecho)
    pedido = datos_t(admin, contexto.owner_user_id, t, importe=D("90"))
    b = Paso("OP-21T", lambda: op21.corregir_transferencia(nuevo(contexto), pedido))
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        from app.repositories import correccion_tesoreria_repository as repo_ct
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_ct, "bloquear_movimientos", "OP-21T"))
    evidencia(f"7b_op03p_op21t_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-21T")
    patas = _todas(admin, "SELECT estado, importe FROM gapto.movimientos_tesoreria WHERE id IN (%s, %s) ORDER BY importe",
                   (t.salida, t.entrada))
    if orden == "A-primero":
        assert traza["OP-03P"] == OK and traza["OP-21T"] != OK, traza
        assert patas == [("ANULADO", D("-100.0000")), ("ANULADO", D("100.0000"))]
    else:
        assert traza["OP-21T"] == OK and traza["OP-03P"] == CodigoError.VERSION_DESFASADA.value, traza
        assert patas == [("ACTIVO", D("-90.0000")), ("ACTIVO", D("90.0000"))]


@pytest.mark.parametrize("orden", ORDENES)
def test_7c_op03p_frente_a_op21_de_la_devolucion(dsn, op03p, servicio, servicio_efectos, servicio_devoluciones,
                                                 servicio_correcciones, contexto, admin, cuenta, orden, caplog,
                                                 monkeypatch):
    """§3.4: OP-21 sobre la devolucion bloquea {D, O}; OP-03P(D) solo D."""
    caplog.set_level(logging.WARNING, logger=LOGGER)
    original, dev = con_abono(servicio, servicio_efectos, servicio_devoluciones, contexto, cuenta)
    a = paso_op03p(op03p, contexto, admin, dev.hecho_id)
    b = _op21_dev(servicio_correcciones, contexto, admin, dev, "-40")
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, pausa_op03p(monkeypatch))
    else:
        traza = correr(dsn, caplog, b, a, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-21-dev"))
    evidencia(f"7c_op03p_op21dev_{orden}", traza)
    comunes(traza)
    traducido(traza, "OP-03P", "OP-21-dev")
    assert devuelto(admin, original) <= capacidad_original(admin, original)
    if orden == "A-primero":
        assert traza["OP-03P"] == OK and traza["OP-21-dev"] != OK, traza
        assert estado(admin, dev.hecho_id) == "ANULADO" and devuelto(admin, original) == D("0")
    else:
        assert traza["OP-21-dev"] == OK and traza["OP-03P"] == CodigoError.VERSION_DESFASADA.value, traza
        assert estado(admin, dev.hecho_id) == "ACTIVO" and devuelto(admin, original) == D("40.0000")
