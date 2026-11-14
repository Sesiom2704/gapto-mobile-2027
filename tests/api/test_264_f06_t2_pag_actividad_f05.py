# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_264_f06_t2_pag_actividad_f05.py
# Ruta: tests/api/test_264_f06_t2_pag_actividad_f05.py
# Descripcion: T2-F06 · PAG · Actividad de F05 con la reforma (mandato PAG §1.5, lista cerrada autorizada por el parrafo 3
#   del literal; Q-VP-03; O-PAG-24), por HTTP como gapto_runtime con RLS: para un hecho MEJORA_PATRIMONIAL la fila de
#   GET /v1/actividad trae «tu parte» desde su VALOR_ACTIVO, la vivienda (`propiedad`), lo que salio de mis cuentas
#   (`salida_cuentas`) y sus posiciones reales en su sentido (`posiciones`); nunca una posicion inferida desde una cuenta
#   compartida; los demas tipos llevan esos campos a null. Va en el commit C3 (aislable para la revision de F05).
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import pytest

import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from test_262_f06_t2_pag_quien_pago import FECHA, _peticion, _registrar, _saldo, _t, _yo


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


def test_o_pag_24_actividad_mi_parte_salida_real_y_posicion(lab):
    p = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "1500.00")],
                  saldos=[_saldo(lab, "ME_DEBE", "750.00")])
    _registrar(lab, p)
    p2 = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "750.00"), _t(lab, "750.00")],
                   saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p2)
    p3 = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_t(lab, "1500.00")],
                   saldos=[_saldo(lab, "LE_DEBO", "750.00")])
    _registrar(lab, p3)
    filas = {f["id"]: f for f in lab.cli.get("/v1/actividad", headers=h.AUTH).json()["filas"]}
    f1, f2, f3 = filas[p["intencion_id"]], filas[p2["intencion_id"]], filas[p3["intencion_id"]]
    for f in (f1, f2, f3):
        assert f["tipo"] == "MEJORA_PATRIMONIAL" and f["tu_parte"] == "750.00" and f["importe_total"] == "1500.00"
        assert f["propiedad"] == {"id": str(lab.pid), "nombre": "Piso Gran Vía"}
    assert (f1["salida_cuentas"], f2["salida_cuentas"], f3["salida_cuentas"]) == ("1500.00", "750.00", "0.00")
    assert f1["posiciones"] == [{"sentido": "ME_DEBE", "importe": "750.00", "tercero": "Tomás"}]
    assert f2["posiciones"] == []
    assert f3["posiciones"] == [{"sentido": "LE_DEBO", "importe": "750.00", "tercero": "Tomás"}]
    c = lab.cuerpo(clase="REPARACION", importe="300.00", fecha=FECHA)           # otros tipos: sin campos nuevos
    lab.ok(c)
    filas = {f["id"]: f for f in lab.cli.get("/v1/actividad", headers=h.AUTH).json()["filas"]}
    g = filas[c["intencion_id"]]
    assert g["propiedad"] is None and g["salida_cuentas"] is None and g["posiciones"] is None


def test_o_pag_24b_actividad_sin_posicion_inferida_con_cuenta_compartida(lab):
    c = lab.cuerpo(clase="MEJORA", importe="1500.00", fecha=FECHA, cuenta=lab.c2)   # B3: cuenta compartida, NO
    lab.ok(c)
    f = next(x for x in lab.cli.get("/v1/actividad", headers=h.AUTH).json()["filas"] if x["id"] == c["intencion_id"])
    assert f["posiciones"] == [] and f["tu_parte"] == "750.00"
