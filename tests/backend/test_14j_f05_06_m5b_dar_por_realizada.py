# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14j_f05_06_m5b_dar_por_realizada.py
# Ruta: tests/backend/test_14j_f05_06_m5b_dar_por_realizada.py
# Descripcion: F04-D065 (reapertura nominal parcial de F04; M5-B de F05-06;
#   AJ-M5BM1-01/02/03/11). `dar_por_realizada` («Dar por cubierta»):
#     - cada precondicion con su codigo y SIN escritura: motivo ausente o en
#       blanco (MOTIVO_AUSENTE), estado no ABIERTO (ESTADO_PREVISION_
#       INCOMPATIBLE), version distinta (VERSION_DESFASADA), cero hechos ACTIVOS
#       vinculados, tambien con el unico hecho ANULADO (PREVISION_SIN_REALIDAD_
#       ACTIVA), RODANTE sin uuid_sucesor (ENTRADA_INVALIDA);
#     - caso PARCIAL: ABIERTA -> REALIZADA, recalculo_automatico=false, el
#       importe esperado se conserva (la desviacion es derivada y no se
#       persiste) y no se crea ni toca ningun hecho, vinculo, efecto ni
#       movimiento; auditoria «realizacion sin realidad nueva: <motivo>»;
#     - RODANTE con uuid_sucesor: sucesor ABIERTO con ese id, en la misma
#       transaccion;
#     - AJ-11: retirar despues el ultimo vinculo deja REALIZADA expuesta como
#       REALIZADA_SIN_REALIDAD_ACTIVA (_revalidar no cambia).
# Version: 0.1.0 (F05-06 M5-B, F04-D065)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import ABIERTA, OMITIDA, REALIZADA, REALIZADA_SIN_REALIDAD_ACTIVA
from app.services.hechos_service import HechosService
from app.services.previsiones_service import PrevisionesService
from conftest import leer_fila
from test_113_rodante_y_materializacion import cadena, crear_hecho, vincular  # noqa: F401
from test_138_f04_r1_discriminantes import anular, hecho_simple, prevision_manual

D = decimal.Decimal


def _dar(servicio_previsiones, contexto, pid, *, motivo="la factura definitiva fue menor", version=None, sucesor=None):
    v = version if version is not None else servicio_previsiones.estado_de(contexto, pid).row_version
    return servicio_previsiones.dar_por_realizada(
        contexto, prevision_id=pid, row_version_esperada=v, motivo=motivo, uuid_sucesor=sucesor)


def _foto(admin, owner, pid) -> tuple:
    """Estado persistido de la previsión y recuentos de realidad del tenant."""
    p = leer_fila(admin, owner, "SELECT estado, row_version, importe_esperado, recalculo_automatico "
                                "FROM gapto.previsiones WHERE id = %s", (pid,))
    n = leer_fila(admin, owner, "SELECT (SELECT count(*) FROM gapto.hechos_financieros), "
                                "(SELECT count(*) FROM gapto.prevision_hechos), "
                                "(SELECT COALESCE(sum(importe_asignado), 0) FROM gapto.prevision_hechos), "
                                "(SELECT count(*) FROM gapto.hecho_efectos), "
                                "(SELECT count(*) FROM gapto.movimientos_tesoreria)", ())
    return p, n


def _parcial(servicio: HechosService, servicio_previsiones: PrevisionesService, contexto) -> tuple[uuid.UUID, uuid.UUID]:
    pid = prevision_manual(servicio_previsiones, contexto)  # esperado 76.10
    hid = hecho_simple(servicio, contexto, importe=D("40.0000"))
    from test_138_f04_r1_discriminantes import vincular as vincular_138

    vincular_138(servicio_previsiones, contexto, pid, hid, "40.0000")
    return pid, hid


def _rechazo(fn, codigo: CodigoError) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        fn()
    assert excinfo.value.codigo is codigo, excinfo.value


# ------------------------------------------------------------------ precondiciones (sin escritura)
@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_motivo_ausente(servicio, servicio_previsiones, contexto, admin, motivo):
    pid, _ = _parcial(servicio, servicio_previsiones, contexto)
    antes = _foto(admin, contexto.owner_user_id, pid)
    _rechazo(lambda: _dar(servicio_previsiones, contexto, pid, motivo=motivo), CodigoError.MOTIVO_AUSENTE)
    assert _foto(admin, contexto.owner_user_id, pid) == antes


def test_sin_realidad_activa(servicio, servicio_previsiones, contexto, admin):
    pid = prevision_manual(servicio_previsiones, contexto)
    antes = _foto(admin, contexto.owner_user_id, pid)
    _rechazo(lambda: _dar(servicio_previsiones, contexto, pid), CodigoError.PREVISION_SIN_REALIDAD_ACTIVA)
    assert _foto(admin, contexto.owner_user_id, pid) == antes


def test_con_el_unico_hecho_anulado_no_hay_realidad(servicio, servicio_previsiones, contexto, admin):
    pid, hid = _parcial(servicio, servicio_previsiones, contexto)
    anular(servicio, contexto, admin, hid)
    antes = _foto(admin, contexto.owner_user_id, pid)
    _rechazo(lambda: _dar(servicio_previsiones, contexto, pid), CodigoError.PREVISION_SIN_REALIDAD_ACTIVA)
    assert _foto(admin, contexto.owner_user_id, pid) == antes


def test_estado_no_abierto(servicio, servicio_previsiones, contexto, admin):
    pid, _ = _parcial(servicio, servicio_previsiones, contexto)
    _dar(servicio_previsiones, contexto, pid)  # REALIZADA
    antes = _foto(admin, contexto.owner_user_id, pid)
    _rechazo(lambda: _dar(servicio_previsiones, contexto, pid), CodigoError.ESTADO_PREVISION_INCOMPATIBLE)
    assert _foto(admin, contexto.owner_user_id, pid) == antes
    omitida = prevision_manual(servicio_previsiones, contexto)
    servicio_previsiones.omitir(contexto, prevision_id=omitida,
                                row_version_esperada=servicio_previsiones.estado_de(contexto, omitida).row_version)
    assert servicio_previsiones.estado_de(contexto, omitida).estado == OMITIDA
    _rechazo(lambda: _dar(servicio_previsiones, contexto, omitida), CodigoError.ESTADO_PREVISION_INCOMPATIBLE)


def test_version_desfasada(servicio, servicio_previsiones, contexto, admin):
    pid, _ = _parcial(servicio, servicio_previsiones, contexto)
    v = servicio_previsiones.estado_de(contexto, pid).row_version
    antes = _foto(admin, contexto.owner_user_id, pid)
    _rechazo(lambda: _dar(servicio_previsiones, contexto, pid, version=v - 1), CodigoError.VERSION_DESFASADA)
    assert _foto(admin, contexto.owner_user_id, pid) == antes


# ------------------------------------------------------------------ caso PARCIAL
def test_parcial_queda_realizada_sin_tocar_la_realidad_ni_la_desviacion(servicio, servicio_previsiones, contexto, admin):
    pid, hid = _parcial(servicio, servicio_previsiones, contexto)
    (estado, version, esperado, _), recuentos = _foto(admin, contexto.owner_user_id, pid)
    assert (estado, esperado) == (ABIERTA, D("76.1000"))
    r = _dar(servicio_previsiones, contexto, pid, motivo="la factura definitiva fue menor")
    assert r.estado == REALIZADA and r.estado_derivado is None and r.row_version == version + 1
    assert r.recalculo_automatico is False
    (estado2, version2, esperado2, recalculo2), recuentos2 = _foto(admin, contexto.owner_user_id, pid)
    # La desviacion (76.10 - 40.00) no se persiste: el esperado se conserva.
    assert (estado2, version2, esperado2, recalculo2) == (REALIZADA, version + 1, D("76.1000"), False)
    # Ni hechos, ni vinculos (ni su importe), ni efectos, ni movimientos nuevos o tocados.
    assert recuentos2 == recuentos
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT importe_asignado FROM gapto.prevision_hechos WHERE prevision_id = %s", (pid,)) == (
        D("40.0000"),)
    fila = leer_fila(admin, contexto.owner_user_id,
                     "SELECT datos_antes->>'estado', datos_despues->>'estado', motivo FROM gapto.auditoria "
                     "WHERE registro_id = %s AND accion = 'ACTUALIZAR' ORDER BY created_at DESC LIMIT 1", (pid,))
    assert fila == (ABIERTA, REALIZADA, "realizacion sin realidad nueva: la factura definitiva fue menor")


# ------------------------------------------------------------------ RODANTE
def test_rodante_sin_uuid_sucesor_se_rechaza(servicio, servicio_previsiones, contexto, admin, cadena):  # noqa: F811
    from test_113_rodante_y_materializacion import F

    hid = crear_hecho(servicio, contexto, F("2027-01-10"), importe=D("20.0000"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hid, "20.0000")
    antes = _foto(admin, contexto.owner_user_id, cadena["cabeza"])
    _rechazo(lambda: _dar(servicio_previsiones, contexto, cadena["cabeza"]), CodigoError.ENTRADA_INVALIDA)
    assert _foto(admin, contexto.owner_user_id, cadena["cabeza"]) == antes
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.previsiones p JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
                     "WHERE v.regla_id = %s",
                     (cadena["regla_id"],)) == (1,)


def test_rodante_con_uuid_sucesor_crea_el_sucesor(servicio, servicio_previsiones, contexto, admin, cadena):  # noqa: F811
    from test_113_rodante_y_materializacion import F

    hid = crear_hecho(servicio, contexto, F("2027-01-10"), importe=D("20.0000"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hid, "20.0000")
    sucesor = uuid.uuid4()
    r = _dar(servicio_previsiones, contexto, cadena["cabeza"], sucesor=sucesor)
    assert r.estado == REALIZADA
    assert servicio_previsiones.estado_de(contexto, sucesor).estado == ABIERTA
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.previsiones p JOIN gapto.regla_versiones v ON v.id = "
                                                    "p.regla_version_id WHERE v.regla_id = %s AND p.estado = 'ABIERTA'", (cadena["regla_id"],)) == (1,)


# ------------------------------------------------------------------ AJ-11
def test_retirar_despues_el_ultimo_vinculo_deja_realizada_sin_realidad(servicio, servicio_previsiones, contexto, admin):
    pid, hid = _parcial(servicio, servicio_previsiones, contexto)
    _dar(servicio_previsiones, contexto, pid)
    vinculo = leer_fila(admin, contexto.owner_user_id,
                        "SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (pid,))[0]
    servicio_previsiones.retirar_vinculo(
        contexto, vinculo_id=vinculo, prevision_id_esperada=pid,
        prevision_row_version_esperada=servicio_previsiones.estado_de(contexto, pid).row_version,
        motivo="nunca debio existir")
    r = servicio_previsiones.estado_de(contexto, pid)
    assert (r.estado, r.estado_derivado) == (REALIZADA, REALIZADA_SIN_REALIDAD_ACTIVA)
