# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14h_mant_vinculo_concurrencia_serial.py
# Ruta: tests/backend/test_14h_mant_vinculo_concurrencia_serial.py
# Descripcion: MANT DEU-F04-VINCULO-ANULADO (dictamen 2026-10-18 Q8). Bateria
#   SERIAL y determinista, FUERA de la suite general: solo con
#   GAPTO_MANT_VINCULO_CONCURRENCIA=1 (evidencia JSON si
#   GAPTO_MANT_VINCULO_EVIDENCIA apunta a una carpeta). Nunca en paralelo.
#   `corregir_vinculo` (nuevo importe) frente a OP-03 y frente a OP-03P sobre el
#   MISMO hecho, en los dos ordenes, con la tecnica de test_14d/test_14f: el
#   primero se retiene DENTRO de su transaccion con el lock del hecho y el
#   segundo espera. Oraculo de estado final equivalente al serial:
#     corregir primero -> la correccion entra (hecho ACTIVO bajo su lock) y la
#       anulacion despues deja el vinculo corregido sobre el hecho ANULADO
#       (AMB-009);
#     anulacion primero -> corregir espera el lock, relee el hecho ANULADO y
#       rechaza HECHO_DEL_VINCULO_ANULADO; el vinculo no cambia.
#   Oraculos comunes: nadie colgado, 0 reintentos 40P01, 0 deadlocks nuevos.
# Version: 0.1.0 (MANT DEU-F04-VINCULO-ANULADO)
# ============================================================

from __future__ import annotations

import decimal
import json
import logging
import os
import pathlib
import uuid

import pytest

from app.core.errores import CodigoError
from app.repositories import relaciones_repository as repo_rel
from test_138_f04_r1_discriminantes import hecho_simple, prevision_manual, version_hecho, vincular, vinculos_de
from test_139_f04_r1_concurrencia_serial import LOGGER, OK, Paso
from test_140_f04_r3_op22 import op22  # noqa: F401
from test_14b_f04_r2a_concurrencia_serial import Pausa
from test_14c_f04_r2b_discriminantes import gasto, nuevo
from test_14d_f04_r2b_concurrencia_serial import ORDENES, comunes, correr
from test_14e_f04_r2c_discriminantes import op03p  # noqa: F401
from test_14f_f04_r2c_concurrencia_serial import estado, paso_op03p, pausa_op03p

D = decimal.Decimal

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_MANT_VINCULO_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_MANT_VINCULO_CONCURRENCIA=1)")


def evidencia(nombre: str, traza: dict) -> None:
    carpeta = os.getenv("GAPTO_MANT_VINCULO_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(traza, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _paso_corregir(servicio_previsiones, contexto, vinculo, prevision) -> Paso:
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    return Paso("corregir_vinculo", lambda: servicio_previsiones.corregir_vinculo(
        nuevo(contexto), vinculo_id=vinculo, versiones_esperadas={prevision: version}, nuevo_importe=D("45.00"),
        motivo="MANT vinculo"))


@pytest.mark.parametrize("via", ["OP-03", "OP-03P"])
@pytest.mark.parametrize("orden", ORDENES)
def test_corregir_vinculo_frente_a_la_anulacion(dsn, servicio, servicio_previsiones, op22, op03p, contexto, admin,
                                               cuenta, orden, via, caplog, monkeypatch):  # noqa: F811
    caplog.set_level(logging.WARNING, logger=LOGGER)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vinculo = uuid.uuid4()
    if via == "OP-03":
        hecho = hecho_simple(servicio, contexto)
        vincular(servicio_previsiones, contexto, prevision, hecho, "40.0000", vinculo_id=vinculo)
        v = version_hecho(admin, contexto.owner_user_id, hecho)
        b = Paso("OP-03", lambda: servicio.anular_hecho(nuevo(contexto), hecho_id=hecho, row_version_esperada=v,
                                                        motivo_anulacion="MANT vinculo"))
    else:
        hecho = gasto(op22, contexto, cuenta).hecho
        vincular(servicio_previsiones, contexto, prevision, hecho, "40.0000", vinculo_id=vinculo)
        b = paso_op03p(op03p, contexto, admin, hecho)
    a = _paso_corregir(servicio_previsiones, contexto, vinculo, prevision)
    if orden == "A-primero":
        traza = correr(dsn, caplog, a, b, Pausa(monkeypatch, repo_rel, "bloquear_hechos", "corregir_vinculo"))
    else:  # la pausa del segundo se instala SOLO en este orden (si no, retendria al segundo en A-primero)
        retener_b = (Pausa(monkeypatch, repo_rel, "bloquear_hechos", "OP-03") if via == "OP-03"
                     else pausa_op03p(monkeypatch))
        traza = correr(dsn, caplog, b, a, retener_b)
    evidencia(f"mant_corregir_{via}_{orden}", traza)
    comunes(traza)
    assert traza[via] == OK and estado(admin, hecho) == "ANULADO", traza
    vinculos = vinculos_de(admin, contexto.owner_user_id, hecho)
    if orden == "A-primero":  # serial corregir -> anular: la correccion entra y el vinculo queda (AMB-009)
        assert traza["corregir_vinculo"] == OK and vinculos == [(prevision, D("45.0000"))], traza
    else:  # serial anular -> corregir: espera el lock, relee ANULADO y rechaza sin efectos
        assert traza["segundo_bloqueado"], traza
        assert traza["corregir_vinculo"] == CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO.value, traza
        assert vinculos == [(prevision, D("40.0000"))], traza
