# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14i_f04_r2_recierre_comp.py
# Ruta: tests/backend/test_14i_f04_r2_recierre_comp.py
# Descripcion: F04-R2 RECIERRE COMP (mandato F04-R2_REC_COMP v1.0; contrato
#   F04-R2 v0.9 §10.1 D2-e, §10.4 y §10.5 bis). Cierra huecos de cobertura del
#   gate acumulado sobre c9c2932, SIN cambios de produccion:
#     HUECO-01 (D2-e): OP-03P sobre un gasto pagado que cumple la cabeza de una
#       cadena RODANTE con sucesor -> resultado EXITOSO con requiere_revision =
#       true, motivo REVISION_DERIVADA_REQUERIDA, la cabeza como unica
#       prevision afectada y sin propagacion; la cabeza conserva REALIZADA y se expone
#       como REALIZADA_SIN_REALIDAD_ACTIVA; vinculo historico conservado
#       (AMB-009) y sucesion intacta (identidad y fecha del sucesor). Control:
#       OP-03 ordinaria sobre el mismo montaje da el mismo resultado.
#     HUECO-02 (§10.4): una fila de auditoria por mutacion de OP-03P con su
#       accion, motivo y request_id (asertos que discriminan los mutantes W14 y
#       W15 de mutantes_f04_r2c).
#     HUECO-03 (§10.5 bis): rollback forzado de OP-21T tras la ultima escritura
#       (mismo mecanismo que test_14c para OP-21P): foto completa identica y 0
#       filas de auditoria con el request_id.
# Version: 0.1.0 (F04-R2 RECIERRE COMP)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid

import pytest

from conftest import _crear_cuenta
from test_113_rodante_y_materializacion import REALIZADA, REALIZADA_SIN_REALIDAD_ACTIVA, cadena  # noqa: F401
from test_113_rodante_y_materializacion import crear_hecho
from test_113_rodante_y_materializacion import vincular as vincular_rodante
from test_138_f04_r1_discriminantes import version_hecho
from test_140_f04_r3_op22 import op22  # noqa: F401
from test_14c_f04_r2b_discriminantes import _todas, corregir_t, gasto, nuevo, op21, saldo, transferencia  # noqa: F401
from test_14e_f04_r2c_discriminantes import MOTIVO, anular, auditorias, op03p  # noqa: F401

D = decimal.Decimal
F = dt.date.fromisoformat


# ==================================================================
# HUECO-01 · D2-e: previsión RODANTE cumplida por el registro anulado
# ==================================================================
def _montaje_rodante(servicio_previsiones, contexto, cadena, hecho):  # noqa: F811
    """El hecho realiza la cabeza y la cadena tiene sucesor (sucesion RODANTE)."""
    sucesor = uuid.uuid4()
    vincular_rodante(servicio_previsiones, contexto, cadena["cabeza"], hecho, "45.0000", realizar=True,
                     sucesor=sucesor)
    return sucesor


def _estado_cadena(servicio_previsiones, contexto, admin, cadena, sucesor, hecho):  # noqa: F811
    cabeza = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    suc = servicio_previsiones.estado_de(contexto, sucesor)
    return {
        "cabeza": (cabeza.estado, cabeza.estado_derivado),
        "sucesor": (suc.estado, suc.fecha_objetivo_regla, suc.row_version),
        "vinculos": _todas(admin, "SELECT prevision_id, importe_asignado FROM gapto.prevision_hechos "
                                  "WHERE hecho_id = %s ORDER BY prevision_id", (hecho,)),
        "previsiones": _todas(admin, "SELECT count(*) FROM gapto.previsiones p JOIN gapto.regla_versiones v "
                                     "ON v.id = p.regla_version_id WHERE v.regla_id = %s", (cadena["regla_id"],)),
    }


def _afirmar_d2e(resultado, antes, despues, cadena, sucesor):  # noqa: F811
    assert resultado.requiere_revision is True
    assert resultado.motivo_revision == "REVISION_DERIVADA_REQUERIDA"
    # La previsión afectada es la que pierde su realidad: la cabeza (no se propaga al sucesor).
    assert resultado.previsiones_afectadas == (cadena["cabeza"],)
    assert resultado.previsiones_propagadas == ()
    # La cabeza conserva REALIZADA y se expone sin realidad activa (AMB-009, F04-D022).
    assert despues["cabeza"] == (REALIZADA, REALIZADA_SIN_REALIDAD_ACTIVA)
    # Vinculo historico conservado y sucesion intacta (ni se mueve ni se crea otra prevision).
    assert despues["vinculos"] == antes["vinculos"] != []
    assert despues["sucesor"] == antes["sucesor"]
    assert despues["previsiones"] == antes["previsiones"]


def test_d2e_op03p_sobre_gasto_que_cumple_una_rodante(op22, op03p, servicio_previsiones, contexto, admin, cuenta,
                                                      cadena):  # noqa: F811
    g = gasto(op22, contexto, cuenta, "45.0000", fecha=F("2027-02-02"))
    sucesor = _montaje_rodante(servicio_previsiones, contexto, cadena, g.hecho)
    antes = _estado_cadena(servicio_previsiones, contexto, admin, cadena, sucesor, g.hecho)
    assert antes["cabeza"][0] == REALIZADA and antes["cabeza"][1] is None
    resultado = anular(op03p, contexto, admin, g.hecho)
    despues = _estado_cadena(servicio_previsiones, contexto, admin, cadena, sucesor, g.hecho)
    _afirmar_d2e(resultado, antes, despues, cadena, sucesor)


def test_d2e_control_op03_ordinaria_mismo_resultado(servicio, servicio_previsiones, contexto, admin,
                                                    cadena):  # noqa: F811
    hecho = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = _montaje_rodante(servicio_previsiones, contexto, cadena, hecho)
    antes = _estado_cadena(servicio_previsiones, contexto, admin, cadena, sucesor, hecho)
    resultado = servicio.anular_hecho(nuevo(contexto), hecho_id=hecho,
                                      row_version_esperada=version_hecho(admin, contexto.owner_user_id, hecho),
                                      motivo_anulacion=MOTIVO)
    despues = _estado_cadena(servicio_previsiones, contexto, admin, cadena, sucesor, hecho)
    _afirmar_d2e(resultado, antes, despues, cadena, sucesor)


# ==================================================================
# HUECO-02 · §10.4: una fila de auditoria por mutacion de OP-03P
# ==================================================================
def test_auditoria_por_fila_de_op03p_en_una_transferencia(op03p, servicio_transferencias, contexto, admin, cuenta,
                                                          cuenta_destino):
    """W1-W3 (ELIMINAR: conciliaciones y fila de transferencias) y W4-W5 (ANULAR:
    las dos patas y el hecho), cada una con su foto, motivo y request_id."""
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    conciliaciones = [f[0] for f in _todas(admin, "SELECT id FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
                                           (t.hecho,))]
    fila_t = _todas(admin, "SELECT id FROM gapto.transferencias WHERE movimiento_salida_id = %s", (t.salida,))[0][0]
    ctx = nuevo(contexto)
    anular(op03p, contexto, admin, t.hecho, ctx=ctx)
    filas = auditorias(admin, ctx.request_id)
    por = {(f[0], f[1]): f for f in filas}
    esperadas = ([("hecho_movimientos_tesoreria", c, "ELIMINAR") for c in conciliaciones]
                 + [("transferencias", fila_t, "ELIMINAR")]
                 + [("movimientos_tesoreria", m, "ANULAR") for m in (t.salida, t.entrada)]
                 + [("hechos_financieros", t.hecho, "ANULAR")])
    assert len(filas) == len(esperadas) == 6
    for tabla, registro, accion in esperadas:
        f = por[(tabla, registro)]
        assert f[2] == accion and f[5] == MOTIVO and f[3] is not None, (tabla, f)
        if accion == "ANULAR":
            assert json.loads(f[4])["estado"] == "ANULADO"
        else:
            assert f[4] is None


# ==================================================================
# HUECO-03 · §10.5 bis: rollback forzado de OP-21T tras la ultima escritura
# ==================================================================
def _foto_transferencia(admin, t, cuentas) -> dict:
    movs = [t.salida, t.entrada]
    return {
        "hecho": _todas(admin, "SELECT importe_total, fecha_hecho, row_version, estado FROM gapto.hechos_financieros "
                               "WHERE id = %s", (t.hecho,)),
        "patas": _todas(admin, "SELECT id, importe, fecha_movimiento, cuenta_id, row_version, estado "
                               "FROM gapto.movimientos_tesoreria WHERE id = ANY(%s) ORDER BY id", (movs,)),
        "transferencias": _todas(admin, "SELECT id, movimiento_salida_id, movimiento_entrada_id FROM gapto.transferencias "
                                        "WHERE movimiento_salida_id = %s", (t.salida,)),
        "conciliaciones": _todas(admin, "SELECT id, movimiento_tesoreria_id, importe_asignado FROM "
                                        "gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s ORDER BY id", (t.hecho,)),
        "aportaciones": _todas(admin, "SELECT id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
                               (t.hecho,)),
        "efectos": _todas(admin, "SELECT id, tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s",
                          (t.hecho,)),
        "saldos": [saldo(admin, c) for c in cuentas],
    }


def test_rollback_op21t_tras_la_ultima_escritura_no_deja_nada(op21, servicio_transferencias, contexto, admin, cuenta,
                                                              cuenta_destino, monkeypatch):
    from app.services import correccion_tesoreria_service as servicio_mod

    tercera = _crear_cuenta(admin, contexto.owner_user_id)
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    cuentas = [cuenta, cuenta_destino, tercera]
    antes = _foto_transferencia(admin, t, cuentas)

    def fallo(*_a, **_k):
        raise RuntimeError("fallo forzado tras la ultima escritura")

    monkeypatch.setattr(servicio_mod.CorreccionTesoreriaService, "_resultado", fallo)
    ctx = nuevo(contexto)
    with pytest.raises(Exception):
        # Importe, fecha y cuenta de la entrada: todas las escrituras de OP-21T.
        corregir_t(op21, contexto, admin, t, ctx=ctx, importe=D("90"), fecha=F("2027-06-04"),
                   cuenta_destino_id=tercera)
    assert _foto_transferencia(admin, t, cuentas) == antes
    assert auditorias(admin, ctx.request_id) == []


def test_control_op21t_sin_fallo_si_escribe(op21, servicio_transferencias, contexto, admin, cuenta, cuenta_destino):
    """Control positivo del rollback: la misma correccion sin fallo cambia el estado y audita."""
    tercera = _crear_cuenta(admin, contexto.owner_user_id)
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    cuentas = [cuenta, cuenta_destino, tercera]
    antes = _foto_transferencia(admin, t, cuentas)
    ctx = nuevo(contexto)
    corregir_t(op21, contexto, admin, t, ctx=ctx, importe=D("90"), fecha=F("2027-06-04"), cuenta_destino_id=tercera)
    assert _foto_transferencia(admin, t, cuentas) != antes
    assert auditorias(admin, ctx.request_id) != []
