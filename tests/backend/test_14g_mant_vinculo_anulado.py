# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14g_mant_vinculo_anulado.py
# Ruta: tests/backend/test_14g_mant_vinculo_anulado.py
# Descripcion: MANT DEU-F04-VINCULO-ANULADO (R-R2C-01; dictamen 2026-10-18 Q8).
#   Discriminantes de la guarda de `corregir_vinculo`: bajo el lock del hecho,
#   el importe de un vinculo que SIGUE en un hecho ANULADO no se corrige ->
#   OPERACION_NO_PERMITIDA_EN_ESTADO, motivo HECHO_DEL_VINCULO_ANULADO, sin
#   efectos. El hecho se anula por OP-03 (sin tesoreria) y por OP-03P (pagado
#   por duplicado). Siguen admitidos: reasignar el vinculo al hecho correcto
#   (AMB-009 / F04-D021, test_113) y a otra prevision (preparacion C1 de F04-R1,
#   test_139); con el hecho ACTIVO nada cambia.
# Version: 0.1.0 (MANT DEU-F04-VINCULO-ANULADO)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

from app.core.errores import CodigoError, ErrorMotor
from test_138_f04_r1_discriminantes import anular, hecho_simple, prevision_manual, vincular, vinculos_de
from test_140_f04_r3_op22 import op22  # noqa: F401
from test_14c_f04_r2b_discriminantes import gasto, nuevo
from test_14e_f04_r2c_discriminantes import anular as anular_op03p
from test_14e_f04_r2c_discriminantes import op03p  # noqa: F401

D = decimal.Decimal
MOTIVO = "HECHO_DEL_VINCULO_ANULADO"


def _corregir(servicio_previsiones, contexto, vinculo_id, previsiones, **cambios):
    versiones = {p: servicio_previsiones.estado_de(contexto, p).row_version for p in previsiones}
    return servicio_previsiones.corregir_vinculo(nuevo(contexto), vinculo_id=vinculo_id,
                                                 versiones_esperadas=versiones, motivo="MANT vinculo", **cambios)


def _rechazo(excinfo) -> None:
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, excinfo.value
    assert excinfo.value.contexto_extra.get("motivo") == MOTIVO, excinfo.value.contexto_extra


def _anulado(via, servicio, servicio_previsiones, op22, op03p, contexto, admin, cuenta):  # noqa: F811
    """Hecho con un vinculo de 40 a una prevision, anulado por la via indicada."""
    prevision = prevision_manual(servicio_previsiones, contexto)
    vinculo = uuid.uuid4()
    if via == "OP-03":
        hecho = hecho_simple(servicio, contexto)
        vincular(servicio_previsiones, contexto, prevision, hecho, "40.0000", vinculo_id=vinculo)
        anular(servicio, contexto, admin, hecho)
    else:
        hecho = gasto(op22, contexto, cuenta).hecho
        vincular(servicio_previsiones, contexto, prevision, hecho, "40.0000", vinculo_id=vinculo)
        anular_op03p(op03p, contexto, admin, hecho)
    return hecho, prevision, vinculo


VIAS = ["OP-03", "OP-03P"]


@pytest.mark.parametrize("via", VIAS)
def test_corregir_importe_de_un_hecho_anulado_se_rechaza(via, servicio, servicio_previsiones, op22, op03p, contexto,
                                                         admin, cuenta):  # noqa: F811
    hecho, prevision, vinculo = _anulado(via, servicio, servicio_previsiones, op22, op03p, contexto, admin, cuenta)
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir(servicio_previsiones, contexto, vinculo, (prevision,), nuevo_importe=D("45.00"))
    _rechazo(excinfo)
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(prevision, D("40.0000"))]
    assert servicio_previsiones.estado_de(contexto, prevision).row_version == version


@pytest.mark.parametrize("via", VIAS)
def test_reasignar_al_hecho_correcto_sigue_admitido(via, servicio, servicio_previsiones, op22, op03p, contexto,
                                                    admin, cuenta):  # noqa: F811
    """AMB-009 / F04-D021 (test_113): el vinculo de un hecho anulado se mueve
    al hecho correcto (ACTIVO), tambien con un importe nuevo."""
    hecho, prevision, vinculo = _anulado(via, servicio, servicio_previsiones, op22, op03p, contexto, admin, cuenta)
    correcto = hecho_simple(servicio, contexto)
    _corregir(servicio_previsiones, contexto, vinculo, (prevision,), nuevo_hecho_id=correcto, nuevo_importe=D("45.00"))
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == []
    assert vinculos_de(admin, contexto.owner_user_id, correcto) == [(prevision, D("45.0000"))]


@pytest.mark.parametrize("via", VIAS)
def test_reasignar_a_otra_prevision_sigue_admitido(via, servicio, servicio_previsiones, op22, op03p, contexto, admin,
                                                   cuenta):  # noqa: F811
    """AMB-009 / F04-R1 C1: el vinculo historico de un hecho anulado puede
    moverse a otra prevision (sucesor) sin cambiar su realidad."""
    hecho, prevision, vinculo = _anulado(via, servicio, servicio_previsiones, op22, op03p, contexto, admin, cuenta)
    destino = prevision_manual(servicio_previsiones, contexto)
    _corregir(servicio_previsiones, contexto, vinculo, (prevision, destino), nueva_prevision_id=destino)
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(destino, D("40.0000"))]


def test_con_el_hecho_activo_la_correccion_no_cambia(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vinculo = uuid.uuid4()
    vincular(servicio_previsiones, contexto, prevision, hecho, "40.0000", vinculo_id=vinculo)
    _corregir(servicio_previsiones, contexto, vinculo, (prevision,), nuevo_importe=D("45.00"))
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(prevision, D("45.0000"))]
