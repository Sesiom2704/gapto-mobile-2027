# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14q_f06_t5_e1_cerrar_vigencia.py
# Ruta: tests/backend/test_14q_f06_t5_e1_cerrar_vigencia.py
# Descripcion: F06 T5 E1 · `ReglasService.cerrar_vigencia` (adenda T5 ronda 3 §2,
#   AJ-T5-R3-02). Oraculo O-R3-01 (cierra una version abierta; rechaza la ajena y
#   la ya cerrada) y una prueba por condicion del contrato:
#     C1 lock + row_version (VERSION_DESFASADA, sin cambios)
#     C2 pertenencia en el repositorio: version de otra regla del MISMO owner y de
#        otro owner (AGREGADO_NO_ENCONTRADO / REGLA_NO_ENCONTRADA, sin cambios)
#     C3 version ya cerrada (VERSION_YA_CERRADA; no acorta ni amplia)
#     C4 vigente_hasta >= vigente_desde (ENTRADA_INVALIDA); el mismo dia SI vale
#     C5 version posterior en conflicto: con la version abierta lo impide el
#        EXCLUDE ex_regla_versiones__regla (se documenta; ver handoff)
#     C6 motivo obligatorio (MOTIVO_AUSENTE) y auditoria con el motivo
#     C7 solo cambia vigente_hasta (snapshot completo antes/despues)
#     C8 RLS/owner (C2 con otro owner)
#   No recalcula previsiones: las previsiones existentes no cambian.
#   Se ejecuta como gapto_runtime con RLS (fixtures de conftest).
# Version: 0.1.0 (F06 T5 E1, mandato T5E1_HITO v1.0 P1.2)
# ============================================================
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import DatosRegla
from conftest import leer_fila
from test_113_rodante_y_materializacion import version_rodante

F = dt.date.fromisoformat
COLUMNAS = ("regla_id, vigente_desde, vigente_hasta, importe_modo, importe_fijo, tipo_hecho_id, periodicidad, "
            "intervalo, moneda")


def _regla(servicio_reglas, contexto, desde="2027-01-10"):
    regla_id = uuid.uuid4()
    v = version_rodante(vigente_desde=F(desde))
    r = servicio_reglas.crear_regla(contexto, DatosRegla(regla_id=regla_id, nombre="T5 E1 cerrar_vigencia"), v)
    return regla_id, v.version_id, r.regla_row_version


def _fila(admin, owner, version_id):
    return leer_fila(admin, owner, f"SELECT {COLUMNAS} FROM gapto.regla_versiones WHERE id = %s", (version_id,))


def _rv(admin, owner, regla_id):
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.reglas_financieras WHERE id = %s", (regla_id,))[0]


def _cerrar(servicio_reglas, contexto, regla_id, version_id, rv, hasta="2027-06-30", motivo="terminacion"):
    return servicio_reglas.cerrar_vigencia(contexto, regla_id=regla_id, version_id=version_id,
                                           vigente_hasta=F(hasta), regla_row_version_esperada=rv, motivo=motivo)


def test_o_r3_01_cierra_version_abierta_solo_vigente_hasta_y_audita(servicio_reglas, contexto, admin):
    regla, version, rv = _regla(servicio_reglas, contexto)
    antes = _fila(admin, contexto.owner_user_id, version)
    r = _cerrar(servicio_reglas, contexto, regla, version, rv, motivo="  fin del contrato  ")
    despues = _fila(admin, contexto.owner_user_id, version)
    assert despues[2] == F("2027-06-30")                                         # cerrada
    assert despues[:2] + despues[3:] == antes[:2] + antes[3:]                     # C7: el resto se conserva
    assert r.regla_row_version == rv + 1 == _rv(admin, contexto.owner_user_id, regla)
    assert r.version_id == version
    aud = leer_fila(admin, contexto.owner_user_id,
                    "SELECT accion, motivo, (datos_antes->>'vigente_hasta') IS NULL, datos_despues->>'vigente_hasta' "
                    "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR'", (version,))
    assert aud == ("ACTUALIZAR", "fin del contrato", True, "2027-06-30")         # C6
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.regla_versiones WHERE regla_id = %s",
                     (regla,)) == (1,)                                             # sin version nueva


def test_c4_mismo_dia_vale_y_anterior_se_rechaza(servicio_reglas, contexto, admin):
    regla, version, rv = _regla(servicio_reglas, contexto, desde="2027-01-10")
    with pytest.raises(ErrorMotor) as e:
        _cerrar(servicio_reglas, contexto, regla, version, rv, hasta="2027-01-09")
    assert e.value.codigo is CodigoError.ENTRADA_INVALIDA
    assert _fila(admin, contexto.owner_user_id, version)[2] is None and _rv(admin, contexto.owner_user_id, regla) == rv
    _cerrar(servicio_reglas, contexto, regla, version, rv, hasta="2027-01-10")      # version de un dia (E0-06 v2)
    assert _fila(admin, contexto.owner_user_id, version)[2] == F("2027-01-10")


def test_c3_version_ya_cerrada_no_se_acorta_ni_se_amplia(servicio_reglas, contexto, admin):
    regla, version, rv = _regla(servicio_reglas, contexto)
    rv = _cerrar(servicio_reglas, contexto, regla, version, rv, hasta="2027-06-30").regla_row_version
    for hasta in ("2027-05-31", "2027-07-31"):
        with pytest.raises(ErrorMotor) as e:
            _cerrar(servicio_reglas, contexto, regla, version, rv, hasta=hasta)
        assert e.value.codigo is CodigoError.VERSION_YA_CERRADA
    assert _fila(admin, contexto.owner_user_id, version)[2] == F("2027-06-30")
    assert _rv(admin, contexto.owner_user_id, regla) == rv


def test_c2_o_a19_version_de_otra_regla_del_mismo_owner(servicio_reglas, contexto, admin):
    a, _, rv_a = _regla(servicio_reglas, contexto)
    b, version_b, rv_b = _regla(servicio_reglas, contexto)
    with pytest.raises(ErrorMotor) as e:
        _cerrar(servicio_reglas, contexto, a, version_b, rv_a)
    assert e.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    assert _fila(admin, contexto.owner_user_id, version_b)[2] is None             # B intacta
    assert _rv(admin, contexto.owner_user_id, a) == rv_a                           # A sin cambios (rollback)
    assert _rv(admin, contexto.owner_user_id, b) == rv_b


def test_c2_c8_version_y_regla_de_otro_owner(servicio_reglas, contexto, admin, otro_owner):
    ajeno = ContextoOperacion.de_usuario(otro_owner)
    b, version_b, rv_b = _regla(servicio_reglas, ajeno)
    a, _, rv_a = _regla(servicio_reglas, contexto)
    with pytest.raises(ErrorMotor) as e:                                           # regla propia, version ajena
        _cerrar(servicio_reglas, contexto, a, version_b, rv_a)
    assert e.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    with pytest.raises(ErrorMotor) as e:                                           # regla y version ajenas (RLS)
        _cerrar(servicio_reglas, contexto, b, version_b, rv_b)
    assert e.value.codigo is CodigoError.REGLA_NO_ENCONTRADA
    assert _fila(admin, otro_owner, version_b)[2] is None and _rv(admin, otro_owner, b) == rv_b


def test_c1_row_version_desfasada_sin_cambios(servicio_reglas, contexto, admin):
    regla, version, rv = _regla(servicio_reglas, contexto)
    with pytest.raises(ErrorMotor) as e:
        _cerrar(servicio_reglas, contexto, regla, version, rv - 1)
    assert e.value.codigo is CodigoError.VERSION_DESFASADA
    assert _fila(admin, contexto.owner_user_id, version)[2] is None and _rv(admin, contexto.owner_user_id, regla) == rv


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_c6_motivo_obligatorio(servicio_reglas, contexto, admin, motivo):
    regla, version, rv = _regla(servicio_reglas, contexto)
    with pytest.raises(ErrorMotor) as e:
        _cerrar(servicio_reglas, contexto, regla, version, rv, motivo=motivo)
    assert e.value.codigo is CodigoError.MOTIVO_AUSENTE
    assert _fila(admin, contexto.owner_user_id, version)[2] is None and _rv(admin, contexto.owner_user_id, regla) == rv


def test_c5_version_posterior_imposible_con_version_abierta(servicio_reglas, contexto, admin):
    # C5: una version abierta [desde, inf) solapa con cualquier posterior, asi que ex_regla_versiones__regla
    # impide que exista; la comprobacion explicita del servicio es redundante por construccion (handoff).
    regla, version, rv = _regla(servicio_reglas, contexto, desde="2027-01-10")
    with pytest.raises(ErrorMotor) as e:
        servicio_reglas.crear_version(contexto, regla_id=regla, regla_row_version_esperada=rv,
                                      version=version_rodante(vigente_desde=F("2027-03-01")))
    assert e.value.codigo is CodigoError.VERSION_REGLA_SOLAPADA
    assert _rv(admin, contexto.owner_user_id, regla) == rv
