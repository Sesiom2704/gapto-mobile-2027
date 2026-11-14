# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_262_f06_t2_pag_quien_pago.py
# Ruta: tests/api/test_262_f06_t2_pag_quien_pago.py
# Descripcion: T2-F06 · PAG N1 · «quien pago y quien debe» (mandato PAG §1.1, contrato operativo unico; §9.1), por
#   HTTP como gapto_runtime con RLS contra C-MEJ-01 v2 (`pagos[]`, `saldos[]`, `posiciones_confirmadas[]`):
#   - casos base O-PAG-01..13 (P1, P2, P3 con LE_DEBO/NADA/NO_LO_SE, confirmacion, sentido, EMPRESA, cuadre,
#     replay, C-MEJ-03 con obligacion, hechos de B3 del tren 1, OP-14 del derecho y OP-12B de la obligacion);
#   - prototipo adoptado (laboratorio lab-t2 05dec08, test_270 renumerado): QP-P1..P7, QP-R x6, QP-C, QP-L, QP-X,
#     QP-E, QP-D, QP-M3 (M3 sin cambios); QP-B2 y QP-B3 dejan de ser negativos (los cubre PAG);
#   - nuevos: O-PAG-14 (H-PAG-02 frente a la reserva de OP-21), O-PAG-15/16 (tres titulares; mixto; tope por la
#     suma), O-PAG-17 (cuenta compartida en `pagos[]`), O-PAG-18 (EMPRESA pagadora), O-PAG-19 (deuda parcial en los
#     dos sentidos), O-PAG-20 (invitacion), O-PAG-21 (confirmacion distinta), O-PAG-22 (replay de B3 v1 y mezcla),
#     O-PAG-23 («Invertido en viviendas este mes»), O-PAG-25 (L-MOV-CUENTA), O-PAG-26
#     (Resultado del mes), O-PAG-27 (H-PAG-03, «Pendiente con»), O-PAG-28 (P2 admite C-MEJ-03); H-PAG-01 en N1 real
#     (pago conciliado por menos que el efecto + aportacion sin movimiento, triggers de 0310 en el COMMIT).
#   Gasto de 8.000,00 de una propiedad compartida YO 50 / T 50 (fecha 2026-05-15) salvo indicacion. Cada rechazo
#   comprueba el estado identico (huella de las tablas de B3). O-PAG-24 (Actividad de F05) va aparte, en test_264 (commit C3).
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import ast
import pathlib
import uuid
from decimal import Decimal

import pytest

import f05_05_helpers as x5
import f05_06_m3_helpers as m3
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h

FECHA = "2026-05-15"
TOTAL = "8000.00"
D = Decimal
RAIZ = pathlib.Path(__file__).resolve().parents[2]
APP = RAIZ / "backend" / "app"


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


def lab3(naturaleza_t2: str = "PERSONA") -> b3.Lab:
    """Propiedad de TRES titulares: YO 50 / T 25 / U 25 desde 2026-01-01 (sin cambio posterior)."""
    lab = b3.Lab.__new__(b3.Lab)
    lab.owner, lab.actor, lab.cli, lab.c1, _ = x5.entorno(b.RELOJ)
    lab.t = b.tercero(lab.cli, "Tomás")
    lab.u = b.tercero(lab.cli, "Úrsula", naturaleza=naturaleza_t2)
    prop = b.crear(lab.cli, b.alta(b.compartida([b.yo("50"), b.de(lab.t, "25"), b.de(lab.u, "25")]),
                                   fecha_adquisicion="2025-12-01"))
    lab.pid = prop["id"]
    partes = prop["titularidad"]["partes"]
    lab.yo = next(x["actor_id"] for x in partes if x["yo"])
    lab.ta = next(x["actor_id"] for x in partes if x.get("tercero_id") == str(lab.t))
    lab.ua = next(x["actor_id"] for x in partes if x.get("tercero_id") == str(lab.u))
    lab.c2 = h.crear_cuenta(lab.owner, [(lab.actor, 50), (uuid.UUID(lab.ta), 50)])
    lab.cat = x5.categoria(lab.owner, "Hogar · Reparaciones")
    return lab


# ------------------------------------------------------------------ utilidades
TIPO = {"ME_DEBE": "DERECHO_COBRO", "LE_DEBO": "OBLIGACION_PAGO"}


def _peticion(lab, *, pagos, saldos, clase="REPARACION", importe=TOTAL, atribucion=None, iid=None,
              confirmadas=None, fecha=FECHA) -> dict:
    atr = atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": lab.vista(fecha)}
    saldos = [{k: str(v) for k, v in x.items()} for x in saldos]
    p = {"intencion_id": str(iid or uuid.uuid4()), "propiedad_id": str(lab.pid), "clase": clase,
         "importe": importe, "fecha_hecho": fecha, "nota": "Cocina", "atribucion": atr,
         "pagos": [{k: str(v) for k, v in x.items()} for x in pagos], "saldos": saldos,
         "posiciones_confirmadas": confirmadas if confirmadas is not None else [
             {"actor_id": s["actor_id"], "tipo": TIPO[s["sentido"]], "importe": s["importe"]}
             for s in saldos if s["sentido"] != "NADA"]}
    if clase != "MEJORA":
        p["categoria_id"] = str(lab.cat)
        p["presupuestable"] = True
    return p


def _registrar(lab, peticion):
    r = lab.registrar(peticion)
    assert r.status_code == 200, r.text
    return r.json()


def _yo(lab, importe, cuenta=None):
    return {"pagador": "YO", "cuenta_id": cuenta or lab.c1, "importe": importe}


def _t(lab, importe, actor=None):
    return {"pagador": actor or lab.ta, "importe": importe}


def _saldo(lab, sentido, importe=None, actor=None):
    s = {"actor_id": actor or lab.ta, "sentido": sentido}
    if importe is not None:
        s["importe"] = importe
    return s


def _sale_de_mis_cuentas(lab, hid) -> D:
    filas = lab.sql("SELECT coalesce(sum(m.importe), 0) FROM gapto.hecho_movimientos_tesoreria x "
                    "JOIN gapto.movimientos_tesoreria m ON m.id = x.movimiento_tesoreria_id WHERE x.hecho_id = %s",
                    (hid,))
    return D(filas[0][0]).quantize(D("0.01"))


def _aportaciones(lab, hid):
    return sorted((str(a), str(D(i).quantize(D("0.01"))), con_mov) for a, i, con_mov in lab.sql(
        "SELECT actor_id, importe, hecho_movimiento_tesoreria_id IS NOT NULL FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s", (hid,)))


def _posiciones(lab, hid):
    return sorted((t, str(a), str(D(i).quantize(D("0.01")))) for t, a, i in m3.posiciones(lab.owner, hid))


def _atribuciones(lab, hid):
    return sorted(str(D(i).quantize(D("0.01"))) for (i,) in lab.sql(
        "SELECT t.importe_atribuido FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e ON e.id = t.efecto_id "
        "WHERE e.hecho_id = %s AND e.tipo_efecto IN ('GASTO', 'VALOR_ACTIVO')", (hid,)))


def _pendiente(lab, tercero=None):
    r = m3.pendiente(lab.cli, tercero or lab.t)
    assert r.status_code == 200, r.text
    j = r.json()
    return j["te_debe"], j["le_debes"], j["neto_estado"]


def _rechazo(lab, peticion, codigo, status=None):
    antes = b3.huella()
    r = lab.registrar(peticion)
    assert r.status_code in ((status,) if status else (409, 422)), r.text
    if codigo:
        assert r.json().get("codigo") == codigo, r.text
    assert b3.huella() == antes
    return r


def _entidad_posicion(lab, hid):
    return lab.sql("SELECT d.entidad_id FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras d "
                   "ON d.entidad_id = v.entidad_id WHERE v.hecho_id = %s", (hid,))[0][0]


# ================================================================== casos base (anexo B §7 y §10)
def test_o_pag_01_qp_p1_pago_yo_todo_y_me_debe_su_parte(lab):
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")])
    r = _registrar(lab, p)
    assert r["idempotente"] is False, r
    hid = p["intencion_id"]
    assert _sale_de_mis_cuentas(lab, hid) == D("-8000.00")
    assert _posiciones(lab, hid) == [("DERECHO_COBRO", lab.ta, "4000.00")]
    assert _aportaciones(lab, hid) == [(lab.yo, "8000.00", True)]
    assert _atribuciones(lab, hid) == ["4000.00", "4000.00"]
    assert _pendiente(lab)[0] == "4000.00"
    g = lab.leer_gasto(hid)
    assert g["procedencia"] == "GASTO_PROPIEDAD" and g["con_deuda"] is True and g["importe"] == TOTAL
    assert g["pago"]["posiciones"] == [{"actor_id": lab.ta, "sentido": "ME_DEBE", "tipo": "DERECHO_COBRO",
                                        "importe": "4000.00", "estado": "ACTIVA"}]


def test_o_pag_02_qp_p2_cada_uno_su_parte_h_pag_01_conciliado_por_menos(lab):
    """H-PAG-01 en N1 real: pago conciliado por 4.000 de un efecto de 8.000 y aportacion sin movimiento de 4.000;
    los triggers de 0310 (D-169) juzgan el COMMIT y lo aceptan. Nadie debe; no queda «pendiente de pago»."""
    p = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    assert _sale_de_mis_cuentas(lab, hid) == D("-4000.00")
    assert _posiciones(lab, hid) == []
    assert _aportaciones(lab, hid) == sorted([(lab.yo, "4000.00", True), (lab.ta, "4000.00", False)])
    assert _atribuciones(lab, hid) == ["4000.00", "4000.00"]
    assert _pendiente(lab)[2] == "SIN_POSICIONES"
    g = lab.leer_gasto(hid)
    assert g["importe"] == TOTAL and g["con_deuda"] is False and g["intencion_correccion_id"] is not None
    assert g["pago"]["declarado"] is True and g["pago"]["sale_de_mis_cuentas"] == "4000.00"
    assert hid in [x["hecho_id"] for x in lab.cli.get(f"/v1/propiedades/{lab.pid}/gastos",
                                                      headers=h.AUTH).json()["gastos"]]
    det = lab.cli.get(f"/v1/actividad/{hid}", headers=h.AUTH).json()
    assert "pendiente_de_pago" not in str(det).lower()


def test_o_pag_03_qp_p3_paga_el_cotitular_le_debo_y_despues_le_pago_op12b(lab):
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    assert _sale_de_mis_cuentas(lab, hid) == D("0.00")
    assert _posiciones(lab, hid) == [("OBLIGACION_PAGO", lab.ta, "4000.00")]
    assert _aportaciones(lab, hid) == [(lab.ta, "8000.00", False)]
    assert _atribuciones(lab, hid) == ["4000.00", "4000.00"]
    assert _pendiente(lab)[1] == "4000.00"
    g = lab.leer_gasto(hid)
    assert g["con_deuda"] is True and g["pago"]["sale_de_mis_cuentas"] == "0.00"
    assert [x["sentido"] for x in g["pago"]["posiciones"]] == ["LE_DEBO"]
    _, r = m3.cobro(lab.cli, _entidad_posicion(lab, hid), lab.c1, "4000.00", fecha="2026-06-01", accion="pago")
    assert r.status_code == 200, r.text
    assert D(r.json()["saldo"]) == 0
    assert _pendiente(lab)[2] == "SIN_POSICIONES"


def test_o_pag_04_p3_con_nada_sin_posicion(lab):
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    assert _posiciones(lab, hid) == [] and _aportaciones(lab, hid) == [(lab.ta, "8000.00", False)]
    assert _pendiente(lab)[2] == "SIN_POSICIONES"


def test_o_pag_05_qp_p7_no_lo_se_admite_pagadores_sin_deuda(lab):
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[], atribucion={"modo": "NO_LO_SE"})
    _registrar(lab, p)
    hid = p["intencion_id"]
    assert _posiciones(lab, hid) == [] and _atribuciones(lab, hid) == []
    assert _aportaciones(lab, hid) == [(lab.ta, "8000.00", False)]
    p2 = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[], atribucion={"modo": "NO_LO_SE"})
    _registrar(lab, p2)
    assert _aportaciones(lab, p2["intencion_id"]) == sorted([(lab.yo, "4000.00", True), (lab.ta, "4000.00", False)])
    otro = h.crear_actor_tercero(lab.owner)                       # pagador ajeno a la titularidad en la fecha
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), {"pagador": otro, "importe": "4000.00"}], saldos=[],
                            atribucion={"modo": "NO_LO_SE"}), "ENTRADA_INVALIDA")
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")],
                            atribucion={"modo": "NO_LO_SE"}), "ENTRADA_INVALIDA")


def test_o_pag_05b_no_lo_se_pagador_valido_en_la_fecha_y_no_hoy():
    """Q-PAG-09: el cotitular de la fecha del hecho (T, 50 % hasta 05-31) paga aunque hoy ya no sea titular."""
    lab = b3.Lab()
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[], atribucion={"modo": "NO_LO_SE"}, fecha="2026-05-15")
    _registrar(lab, p)
    tarde = _peticion(lab, pagos=[_t(lab, "300.00")], saldos=[], atribucion={"modo": "NO_LO_SE"}, importe="300.00",
                      fecha="2026-07-01")
    _rechazo(lab, tarde, "ENTRADA_INVALIDA")


def test_o_pag_06_posicion_sin_confirmar_422_estado_identico(lab):
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")],
                            confirmadas=[]), "ENTRADA_INVALIDA", 422)
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")],
                            confirmadas=[]), "ENTRADA_INVALIDA", 422)


def test_o_pag_07_saldo_sin_sentido_o_sin_importe_422(lab):
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "NADA")])
    p["saldos"] = [{"actor_id": lab.ta, "importe": "4000.00"}]                # sin sentido: DTO
    _rechazo(lab, p, None, 422)
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "NADA")])
    p["saldos"] = [{"actor_id": lab.ta, "sentido": "ME_DEBE"}]                # sin importe
    p["posiciones_confirmadas"] = []
    _rechazo(lab, p, "ENTRADA_INVALIDA", 422)
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "NADA")])
    p["saldos"] = [{"actor_id": lab.ta, "sentido": "NADA", "importe": "1.00"}]  # NADA con importe
    _rechazo(lab, p, "ENTRADA_INVALIDA", 422)


def test_o_pag_08_qp_e_empresa_aporta_sin_posicion_y_nunca_le_debo():
    """Q-PAG-05: con un cotitular EMPRESA, P2 (aportacion sin posicion) se admite; LE_DEBO o ME_DEBE frente a una
    EMPRESA se rechazan."""
    lab = b3.Lab(naturaleza_t="EMPRESA")
    p = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    assert _posiciones(lab, p["intencion_id"]) == []
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")]),
             "ENTRADA_INVALIDA")
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")]),
             "ENTRADA_INVALIDA")


def test_o_pag_09_pagos_no_cuadran(lab):
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "3000.00")], saldos=[_saldo(lab, "NADA")]),
             "PAGOS_NO_CUADRAN", 422)
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.01")], saldos=[_saldo(lab, "NADA")]), "PAGOS_NO_CUADRAN", 422)


def test_o_pag_10_qp_p6_replay_idempotente_y_reutilizacion(lab):
    p = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[_saldo(lab, "NADA")])
    assert _registrar(lab, p)["idempotente"] is False
    antes = b3.huella()
    assert _registrar(lab, p)["idempotente"] is True
    assert b3.huella() == antes
    otro = _peticion(lab, pagos=[_yo(lab, "5000.00"), _t(lab, "3000.00")], saldos=[_saldo(lab, "NADA")],
                     iid=p["intencion_id"])
    r = lab.registrar(otro)
    assert r.status_code == 409 and "IDENTIDAD_REUTILIZADA" in r.json()["codigo"], r.text
    assert b3.huella() == antes


def test_o_pag_11_c_mej_03_con_obligacion_no_se_ofrece_ni_se_admite(lab):
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    g = lab.leer_gasto(hid)
    assert g["intencion_correccion_id"] is None and g["limitacion"] == b3.LIMITACION and g["con_deuda"] is True
    efecto = next(e[0] for e in lab.efectos(hid) if e[1] == "GASTO")
    cuerpo = {"intencion_id": b3.intencion_vigente(efecto), "row_version_esperada": g["row_version"],
              "clase_nueva": "MEJORA", "motivo": "Error",
              "comparacion_vista": lab.impacto(hid, "MEJORA")}
    antes = b3.huella()
    r = lab.corregir(hid, cuerpo)
    assert r.status_code in (409, 422), r.text
    assert b3.huella() == antes


def test_o_pag_12_hecho_de_b3_del_tren_1_pago_sin_declarar_sin_escrituras(lab):
    c = lab.cuerpo(importe=TOTAL, fecha=FECHA)                                   # forma de B3 (v1)
    lab.ok(c)
    antes = b3.huella()
    g = lab.leer_gasto(c["intencion_id"])["pago"]
    assert g == {"declarado": False, "sale_de_mis_cuentas": "8000.00", "cuentas_movimiento": [str(lab.c1)],
                 "pagos": [], "posiciones": []}
    lab.cli.get(f"/v1/propiedades/{lab.pid}/gastos", headers=h.AUTH)
    assert b3.huella() == antes


def test_o_pag_13_op14_del_derecho_y_op12b_de_la_obligacion(lab):
    p1 = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")])
    _registrar(lab, p1)
    _, r = m3.cobro(lab.cli, _entidad_posicion(lab, p1["intencion_id"]), lab.c1, "4000.00", fecha="2026-06-01")
    assert r.status_code == 200 and D(r.json()["saldo"]) == 0, r.text
    p3 = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p3)
    _, r = m3.cobro(lab.cli, _entidad_posicion(lab, p3["intencion_id"]), lab.c1, "1000.00", fecha="2026-06-01",
                    accion="pago")
    assert r.status_code == 200 and D(r.json()["saldo"]) == D("3000.00"), r.text
    assert _pendiente(lab)[1] == "3000.00"


# ================================================================== prototipo adoptado
def test_qp_b1_linea_base_b3_v1_sigue_igual(lab):
    """Forma de B3 (v1) sin cambios: DERECHO 4.000, sale 8.000 de mis cuentas, sin aportaciones."""
    c = lab.cuerpo(importe=TOTAL, fecha=FECHA, deuda=[{"actor_id": lab.ta, "me_debe": "SI"}],
                   derechos=[{"actor_id": lab.ta, "importe": "4000.00"}])
    lab.ok(c)
    hid = c["intencion_id"]
    assert _sale_de_mis_cuentas(lab, hid) == D("-8000.00")
    assert _posiciones(lab, hid) == [("DERECHO_COBRO", lab.ta, "4000.00")]
    assert _aportaciones(lab, hid) == []


def test_qp_m3_gasto_compartido_de_f05_sin_cambios(lab):
    """M3 (L-04b no firmado) conserva su modelo de un solo pagador; no es gasto de la propiedad."""
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": TOTAL, "moneda": "EUR", "fecha_hecho": FECHA,
              "presupuestable": True, "categoria": {"estado": "CATEGORIA", "categoria_id": str(lab.cat)},
              "pagado_por": {"tipo": "PERSONA", "tercero_id": str(lab.t), "le_debo": "SI"},
              "reparto": {"modo": "REPARTIR", "mi_parte": "4000.00",
                          "partes": [{"tercero_id": str(lab.t), "importe": "4000.00"}]}}
    r = lab.cli.post("/v1/intenciones/gasto-compartido", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hid = cuerpo["intencion_id"]
    assert _posiciones(lab, hid) == [("OBLIGACION_PAGO", lab.ta, "4000.00")]
    assert lab.gasto(hid).status_code == 404
    dos = dict(cuerpo, intencion_id=str(uuid.uuid4()), pagado_por=[{"tipo": "CUENTA", "cuenta_id": str(lab.c1)},
                                                                     {"tipo": "PERSONA", "tercero_id": str(lab.t),
                                                                      "le_debo": "NO"}])
    assert lab.cli.post("/v1/intenciones/gasto-compartido", json=dos, headers=h.AUTH).status_code == 422


def test_qp_p4_mixto_bilateral_pago_6000_el_2000_me_debe_2000(lab):
    p = _peticion(lab, pagos=[_yo(lab, "6000.00"), _t(lab, "2000.00")], saldos=[_saldo(lab, "ME_DEBE", "2000.00")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    assert _sale_de_mis_cuentas(lab, hid) == D("-6000.00")
    assert _posiciones(lab, hid) == [("DERECHO_COBRO", lab.ta, "2000.00")]
    assert _aportaciones(lab, hid) == sorted([(lab.yo, "6000.00", True), (lab.ta, "2000.00", False)])


def test_qp_p5_mejora_pagada_por_el_cotitular_cuenta_en_el_coste(lab):
    p = _peticion(lab, clase="MEJORA", pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p)
    assert b2.leer_coste(lab.cli, lab.pid)["MEJORAS"]["total"] == "8000.00"
    assert _sale_de_mis_cuentas(lab, p["intencion_id"]) == D("0.00")


@pytest.mark.parametrize("caso", ["no_cuadran", "le_debo_si_pague_todo", "me_debe_mas_que_su_parte",
                                  "saldo_no_declarado", "me_debe_si_pago_el", "pagador_no_cotitular"])
def test_qp_r_rechazos_sin_escritura(lab, caso):
    if caso == "no_cuadran":
        _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "3000.00")], saldos=[_saldo(lab, "NADA")]),
                 "PAGOS_NO_CUADRAN")
    elif caso == "le_debo_si_pague_todo":
        _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")]),
                 "SALDO_INCOHERENTE")
    elif caso == "me_debe_mas_que_su_parte":
        _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.01")]),
                 "SALDO_INCOHERENTE")
    elif caso == "saldo_no_declarado":
        _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[]), "SALDO_NO_DECLARADO")
    elif caso == "me_debe_si_pago_el":
        _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")]),
                 "SALDO_INCOHERENTE")
    else:
        otro = h.crear_actor_tercero(lab.owner)
        _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), {"pagador": otro, "importe": "4000.00"}],
                                saldos=[_saldo(lab, "NADA")]), "ENTRADA_INVALIDA")


@pytest.mark.parametrize("caso", ["P1_pago_yo_todo", "P2_cada_uno_su_parte", "P3_paga_el_todo"])
def test_qp_d_actividad_tu_parte(lab, caso):
    pagos = {"P1_pago_yo_todo": [_yo(lab, "8000.00")],
             "P2_cada_uno_su_parte": [_yo(lab, "4000.00"), _t(lab, "4000.00")],
             "P3_paga_el_todo": [_t(lab, "8000.00")]}[caso]
    saldos = {"P1_pago_yo_todo": [_saldo(lab, "ME_DEBE", "4000.00")], "P2_cada_uno_su_parte": [_saldo(lab, "NADA")],
              "P3_paga_el_todo": [_saldo(lab, "LE_DEBO", "4000.00")]}[caso]
    p = _peticion(lab, pagos=pagos, saldos=saldos)
    _registrar(lab, p)
    det = lab.cli.get(f"/v1/actividad/{p['intencion_id']}", headers=h.AUTH)
    assert det.status_code == 200, det.text
    assert det.json().get("tu_parte") in ("4000.00", "-4000.00"), det.json()


def test_qp_c_o_pag_28_p2_sin_posiciones_admite_c_mej_03_y_conserva_pagos(lab):
    """O-PAG-28 / QP-C: un P2 sin posiciones conserva UN efecto y admite C-MEJ-03, que mantiene aportaciones,
    movimiento y atribuciones; con deuda en cualquier sentido, no (O-PAG-11)."""
    p = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    antes = {"aportaciones": _aportaciones(lab, hid), "sale": _sale_de_mis_cuentas(lab, hid),
             "atribuciones": _atribuciones(lab, hid)}
    r = lab.corregir(hid, lab.correccion(hid, "MEJORA"))
    assert r.status_code == 200, r.text
    assert _aportaciones(lab, hid) == antes["aportaciones"] and _sale_de_mis_cuentas(lab, hid) == antes["sale"]
    assert _atribuciones(lab, hid) == antes["atribuciones"]
    assert [e[1] for e in lab.efectos(hid)] == ["VALOR_ACTIVO"]


def test_qp_l_lectura_pago_en_l_gasto_propiedad(lab):
    p = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    g = lab.leer_gasto(p["intencion_id"])["pago"]
    assert g["declarado"] is True and g["sale_de_mis_cuentas"] == "4000.00" and g["posiciones"] == []
    assert sorted((x["actor_id"], x["importe"], x["con_movimiento"], x["cuenta_id"]) for x in g["pagos"]) == sorted(
        [(lab.yo, "4000.00", True, str(lab.c1)), (lab.ta, "4000.00", False, None)])


@pytest.mark.parametrize("caso", ["v2_con_cuenta_id", "v2_con_deuda", "v2_con_derechos", "v2_con_aportacion",
                                  "v1_sin_cuenta", "v1_con_saldos", "v1_con_confirmadas", "cotitular_con_cuenta",
                                  "dos_pagos_mios", "yo_sin_cuenta", "pagador_repetido"])
def test_qp_x_o_pag_22_mezclas_rechazadas(lab, caso):
    base = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")])
    if caso == "v2_con_cuenta_id":
        base["cuenta_id"] = str(lab.c1)
    elif caso == "v2_con_deuda":
        base["deuda"] = [{"actor_id": lab.ta, "me_debe": "SI"}]
    elif caso == "v2_con_derechos":
        base["derechos_confirmados"] = [{"actor_id": lab.ta, "importe": "4000.00"}]
    elif caso == "v2_con_aportacion":
        base["aportacion_indicada"] = "MANUAL"
    elif caso == "v1_sin_cuenta":
        base = lab.cuerpo(importe=TOTAL, fecha=FECHA)
        del base["cuenta_id"]
    elif caso == "v1_con_saldos":
        base = lab.cuerpo(importe=TOTAL, fecha=FECHA, saldos=[_saldo(lab, "NADA")])
    elif caso == "v1_con_confirmadas":
        base = lab.cuerpo(importe=TOTAL, fecha=FECHA, posiciones_confirmadas=[
            {"actor_id": lab.ta, "tipo": "DERECHO_COBRO", "importe": "4000.00"}])
    elif caso == "cotitular_con_cuenta":
        base["pagos"] = [{"pagador": lab.ta, "cuenta_id": str(lab.c1), "importe": "8000.00"}]
    elif caso == "dos_pagos_mios":
        base["pagos"] = [{"pagador": "YO", "cuenta_id": str(lab.c1), "importe": "4000.00"},
                         {"pagador": "YO", "cuenta_id": str(lab.c1), "importe": "4000.00"}]
    elif caso == "yo_sin_cuenta":
        base["pagos"] = [{"pagador": "YO", "importe": "8000.00"}]
    else:
        base["pagos"] = [{"pagador": lab.ta, "importe": "4000.00"}, {"pagador": lab.ta, "importe": "4000.00"}]
        base["saldos"] = [{"actor_id": lab.ta, "sentido": "NADA"}]
        base["posiciones_confirmadas"] = []
    _rechazo(lab, base, "ENTRADA_INVALIDA")


# ================================================================== nuevos de este mandato
def test_o_pag_14_h_pag_02_obligacion_frente_a_la_reserva_de_op21(lab, monkeypatch):
    """H-PAG-02 (F04-D073): la OBLIGACION_PAGO con su vinculo de nivel efecto convive con la reserva de PROPIEDAD.
    Ninguna superficie HTTP aplica OP-21 ni OP-03 sobre el hecho (estado identico) y la edicion no ofrece ninguna
    correccion; ningun modulo de PAG importa OP-21/OP-03 (Parte IV-bis)."""
    from app.services.correcciones_service import CorreccionesService
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p)
    hid = p["intencion_id"]
    espia = []
    original = CorreccionesService.corregir
    monkeypatch.setattr(CorreccionesService, "corregir",
                        lambda self, ctx, datos: espia.append(datos) or original(self, ctx, datos))
    v = lab.hecho(hid)[1]
    atr = lab.sql("SELECT t.id::text, t.importe_atribuido FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e "
                  "ON e.id = t.efecto_id WHERE e.hecho_id = %s ORDER BY t.id", (hid,))
    peticiones = {
        "reparto": (f"/v1/hechos/{hid}/reparto", {"row_version": v, "motivo": "O-PAG-14", "partes": [
            {"atribucion_id": a, "importe": "1.00" if i == 0 else str(imp)} for i, (a, imp) in enumerate(atr)]}),
        "corregir_categoria": (f"/v1/hechos/{hid}/corregir-categoria",
                               {"intencion_id": str(uuid.uuid4()), "row_version": v, "categoria_id": str(lab.cat)}),
        "anular_duplicado": (f"/v1/hechos/{hid}/anular-duplicado", {
            "intencion_id": str(uuid.uuid4()), "row_version": v, "movimientos_row_version": {},
            "duplicado_declarado": True, "motivo": "O-PAG-14"}),
    }
    for nombre, (ruta, cuerpo) in peticiones.items():
        antes = b3.huella()
        r = lab.cli.post(ruta, json=cuerpo, headers=h.AUTH)
        assert r.status_code >= 400, (nombre, r.text)
        assert b3.huella() == antes, nombre
    for datos in espia:
        assert not getattr(datos, "efectos_a_eliminar", None) and not getattr(datos, "entidades_a_eliminar", None)
    ed = lab.cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH)
    assert ed.status_code == 200, ed.text
    acciones = ed.json()["acciones"]
    assert acciones["corregir"]["disponible"] is False and acciones["anular_duplicado"]["disponible"] is False
    prohibidos = ("correcciones_service", "hechos_service", "anulacion_tesoreria_service",
                  "correccion_tesoreria_service", "ejecucion_correccion", "ejecucion_anulacion", "ejecucion_reparto")
    for modulo in ("patrimonio/pagos.py", "patrimonio/lecturas_pag.py", "patrimonio/rutas_pag.py"):
        arbol = ast.parse((APP / modulo).read_text(encoding="utf-8"))
        importados = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        assert not any(x in m for m in importados for x in prohibidos), (modulo, importados)


def test_o_pag_15_tres_titulares_p1_p2_p3_sin_posiciones_entre_terceros():
    lab = lab3()
    # P1: pago yo todo; T y U me deben su parte
    p1 = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "2000.00"),
                                                              _saldo(lab, "ME_DEBE", "2000.00", actor=lab.ua)])
    _registrar(lab, p1)
    assert _posiciones(lab, p1["intencion_id"]) == sorted([("DERECHO_COBRO", lab.ta, "2000.00"),
                                                            ("DERECHO_COBRO", lab.ua, "2000.00")])
    # P2: cada uno su parte
    p2 = _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "2000.00"), _t(lab, "2000.00", actor=lab.ua)],
                   saldos=[_saldo(lab, "NADA"), _saldo(lab, "NADA", actor=lab.ua)])
    _registrar(lab, p2)
    assert _posiciones(lab, p2["intencion_id"]) == []
    # P3: T paga todo; solo le debo yo mi parte; U no me debe nada a mi (su deuda es con T: nunca se registra)
    p3 = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00"),
                                                             _saldo(lab, "NADA", actor=lab.ua)])
    _registrar(lab, p3)
    assert _posiciones(lab, p3["intencion_id"]) == [("OBLIGACION_PAGO", lab.ta, "4000.00")]
    # P3 con LE_DEBO por mas de mi parte (lo que U le debe a T): posicion entre terceros -> rechazo
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "6000.00"),
                                                                      _saldo(lab, "NADA", actor=lab.ua)]),
             "SALDO_INCOHERENTE")
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00"),
                                                                      _saldo(lab, "ME_DEBE", "2000.00", actor=lab.ua)]),
             "SALDO_INCOHERENTE")


def test_o_pag_16_mixto_con_tres_titulares_rechazado():
    """§1.1.5: con tres o mas titulares solo P1, P2 y P3; el mixto es solo bilateral (ENTRADA_INVALIDA)."""
    lab = lab3()
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "6000.00"), _t(lab, "2000.00")],
                            saldos=[_saldo(lab, "NADA"), _saldo(lab, "ME_DEBE", "2000.00", actor=lab.ua)]),
             "ENTRADA_INVALIDA")
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "4000.00")],
                            saldos=[_saldo(lab, "LE_DEBO", "2000.00"), _saldo(lab, "NADA", actor=lab.ua)]),
             "ENTRADA_INVALIDA")


def test_o_pag_16b_tope_por_la_suma_bilateral_y_compuesto():
    """M-PAG-17: el tope es la SUMA de mis ME_DEBE frente a lo que pague de mas. Con tres titulares en P1 cada saldo
    individual cabe en |saldo_c| y en mi exceso, pero la suma no: rechazo."""
    lab = lab3()
    # Reparto 50/25/25 de 8.000: T y U deben 2.000 cada uno; yo pague 8.000 (exceso 4.000). 2.000 + 2.000 = 4.000 OK.
    ok = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "2000.00"),
                                                              _saldo(lab, "ME_DEBE", "2000.00", actor=lab.ua)])
    _registrar(lab, ok)
    # P2 «casi»: pago 4.000 (mi parte), T 2.000 y U 2.000 -> nadie me debe; ME_DEBE de U es incoherente aunque U
    # hubiese pagado menos que su parte si mi exceso es 0.
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "4000.00"), _t(lab, "2000.00"), _t(lab, "2000.00", actor=lab.ua)],
                            saldos=[_saldo(lab, "NADA"), _saldo(lab, "ME_DEBE", "1.00", actor=lab.ua)]),
             "SALDO_INCOHERENTE")
    # Cada saldo frente a SU desequilibrio (M-PAG-09): la suma cabe en mi exceso (4.000) pero T no puede deber 2.000,01.
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "2000.01"),
                                                                       _saldo(lab, "ME_DEBE", "1999.99", actor=lab.ua)]),
             "SALDO_INCOHERENTE")
    # LE_DEBO solo a quien pago de mas (M-PAG-09b): con T pagando todo, a U (que pago de menos) no le debo nada.
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "3000.00"),
                                                                      _saldo(lab, "LE_DEBO", "1000.00", actor=lab.ua)]),
             "SALDO_INCOHERENTE")


def test_o_pag_17_cuenta_compartida_en_pagos_rechazada_y_via_b3_sigue(lab):
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00", cuenta=lab.c2)], saldos=[_saldo(lab, "NADA")]),
             "PAGO_DESDE_CUENTA_COMPARTIDA", 422)
    c = lab.cuerpo(importe=TOTAL, fecha=FECHA, cuenta=lab.c2, deuda=[{"actor_id": lab.ta, "me_debe": "SI"}],
                   derechos=[{"actor_id": lab.ta, "importe": "1000.00"}], aportacion="MANUAL")    # O9.16 (8ter)
    lab.ok(c)
    assert _posiciones(lab, c["intencion_id"]) == [("DERECHO_COBRO", lab.ta, "1000.00")]


def test_o_pag_18_empresa_como_pagador_frente_a_cotitular_persona():
    """Dos variantes: (a) cotitular EMPRESA que paga todo (aportacion sin posicion, NADA); (b) con tres titulares,
    la EMPRESA paga su parte y la PERSONA paga la suya; ninguna posicion frente a la EMPRESA."""
    lab = b3.Lab(naturaleza_t="EMPRESA")
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    assert _posiciones(lab, p["intencion_id"]) == [] and _aportaciones(lab, p["intencion_id"]) == [
        (lab.ta, "8000.00", False)]
    lab = lab3(naturaleza_t2="EMPRESA")
    p = _peticion(lab, pagos=[_yo(lab, "6000.00"), _t(lab, "2000.00", actor=lab.ua)],
                  saldos=[_saldo(lab, "ME_DEBE", "2000.00"), _saldo(lab, "NADA", actor=lab.ua)])
    _rechazo(lab, p, "ENTRADA_INVALIDA")                                    # mixto con tres titulares
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "2000.00"),
                                                             _saldo(lab, "NADA", actor=lab.ua)])
    _registrar(lab, p)
    assert _posiciones(lab, p["intencion_id"]) == [("DERECHO_COBRO", lab.ta, "2000.00")]
    _rechazo(lab, _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[
        _saldo(lab, "ME_DEBE", "2000.00"), _saldo(lab, "ME_DEBE", "2000.00", actor=lab.ua)]), "ENTRADA_INVALIDA")


def test_o_pag_19_deuda_parcial_en_los_dos_sentidos(lab):
    p = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "1500.00")])
    _registrar(lab, p)
    assert _posiciones(lab, p["intencion_id"]) == [("DERECHO_COBRO", lab.ta, "1500.00")]
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "0.01")])
    _registrar(lab, p)
    assert _posiciones(lab, p["intencion_id"]) == [("OBLIGACION_PAGO", lab.ta, "0.01")]
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.01")]),
             "SALDO_INCOHERENTE")


def test_o_pag_20_nada_con_desequilibrio_es_invitacion(lab):
    for pagos in ([_yo(lab, "8000.00")], [_t(lab, "8000.00")], [_yo(lab, "6000.00"), _t(lab, "2000.00")]):
        p = _peticion(lab, pagos=pagos, saldos=[_saldo(lab, "NADA")])
        _registrar(lab, p)
        assert _posiciones(lab, p["intencion_id"]) == []


@pytest.mark.parametrize("cambio", ["actor", "tipo", "importe", "sobra", "duplicada"])
def test_o_pag_21_posiciones_confirmadas_distintas_422(lab, cambio):
    s = [_saldo(lab, "LE_DEBO", "4000.00")]
    conf = {"actor_id": lab.ta, "tipo": "OBLIGACION_PAGO", "importe": "4000.00"}
    if cambio == "actor":
        conf = dict(conf, actor_id=str(h.crear_actor_tercero(lab.owner)))
        confirmadas = [conf]
    elif cambio == "tipo":
        confirmadas = [dict(conf, tipo="DERECHO_COBRO")]
    elif cambio == "importe":
        confirmadas = [dict(conf, importe="3999.99")]
    elif cambio == "sobra":
        s = [_saldo(lab, "NADA")]
        confirmadas = [conf]
    else:
        confirmadas = [conf, conf]
    _rechazo(lab, _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=s, confirmadas=confirmadas),
             "ENTRADA_INVALIDA", 422)


def test_o_pag_22_replay_de_una_intencion_de_b3_v1_idempotente(lab):
    c = lab.cuerpo(importe=TOTAL, fecha=FECHA, deuda=[{"actor_id": lab.ta, "me_debe": "SI"}],
                   derechos=[{"actor_id": lab.ta, "importe": "4000.00"}])
    assert lab.ok(c)["idempotente"] is False
    antes = b3.huella()
    assert lab.ok(c)["idempotente"] is True
    assert b3.huella() == antes
    v2 = _peticion(lab, pagos=[_yo(lab, "8000.00")], saldos=[_saldo(lab, "ME_DEBE", "4000.00")],
                   iid=c["intencion_id"])
    r = lab.registrar(v2)                                  # misma intencion, otra forma: OP-22 decide (no identica)
    assert r.status_code == 409 and "IDENTIDAD_REUTILIZADA" in r.json()["codigo"], r.text
    assert b3.huella() == antes


def _invertido(lab, fecha=FECHA) -> dict:
    r = lab.cli.get("/v1/patrimonio/invertido-mes", params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _resultado(lab, fecha=FECHA) -> dict:
    r = lab.cli.get("/v1/inicio/resultado-mes", params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_o_pag_23_invertido_en_viviendas_este_mes(lab):
    assert _invertido(lab)["invertido"] == "0.00"
    antes = _resultado(lab)
    p = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "1500.00")],
                  saldos=[_saldo(lab, "ME_DEBE", "750.00")])
    _registrar(lab, p)
    assert _invertido(lab)["invertido"] == "750.00"
    p = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_t(lab, "1500.00")],
                  saldos=[_saldo(lab, "LE_DEBO", "750.00")])
    _registrar(lab, p)
    assert _invertido(lab)["invertido"] == "1500.00"
    otro_mes = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "1500.00")],
                         saldos=[_saldo(lab, "NADA")], fecha="2026-04-10")
    _registrar(lab, otro_mes)
    assert _invertido(lab)["invertido"] == "1500.00" and _invertido(lab, "2026-04-20")["invertido"] == "750.00"
    sin = _peticion(lab, clase="MEJORA", importe="500.00", pagos=[_yo(lab, "500.00")], saldos=[],
                    atribucion={"modo": "NO_LO_SE"})
    _registrar(lab, sin)
    assert _invertido(lab) == {"mes": "2026-05", "moneda": "EUR", "invertido": "1500.00", "sin_reparto": 1}
    assert _resultado(lab) == antes                                      # el Resultado del mes no cambia


def test_o_pag_23b_invertido_no_cuenta_compras():
    lab = b2.Lab()
    cuerpo = lab.peticion()
    r = lab.compra(cuerpo)
    assert r.status_code == 200, r.text
    fechas = [f for (f,) in lab.sql("SELECT DISTINCT h.fecha_hecho FROM gapto.hechos_financieros h JOIN gapto.hecho_efectos e "
                                    "ON e.hecho_id = h.id WHERE e.tipo_efecto = 'VALOR_ACTIVO'")]
    assert fechas                                                            # la compra tiene VALOR_ACTIVO atribuido
    assert lab.sql("SELECT count(*) FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
                   "WHERE e.tipo_efecto = 'VALOR_ACTIVO' AND a.importe_atribuido > 0")[0][0] > 0
    for fecha in fechas:
        r = lab.cli.get("/v1/patrimonio/invertido-mes", params={"fecha": str(fecha)}, headers=h.AUTH)
        assert r.status_code == 200 and r.json()["invertido"] == "0.00", r.text


def test_o_pag_25_l_mov_cuenta(lab):
    p = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "750.00"), _t(lab, "750.00")],
                  saldos=[_saldo(lab, "NADA")])
    _registrar(lab, p)
    p1 = _peticion(lab, clase="MEJORA", importe="1500.00", pagos=[_yo(lab, "1500.00")],
                   saldos=[_saldo(lab, "ME_DEBE", "750.00")], fecha="2026-05-20")
    _registrar(lab, p1)
    r = lab.cli.get(f"/v1/cuentas/{lab.c1}/movimientos", headers=h.AUTH)
    assert r.status_code == 200, r.text
    j = r.json()
    movs = [(m["fecha"], m["importe"], [x["hecho_id"] for x in m["hechos"]]) for m in j["movimientos"]]
    assert ("2026-05-15", "-750.00", [p["intencion_id"]]) in movs
    assert ("2026-05-20", "-1500.00", [p1["intencion_id"]]) in movs
    assert movs.index(("2026-05-15", "-750.00", [p["intencion_id"]])) < movs.index(
        ("2026-05-20", "-1500.00", [p1["intencion_id"]]))                       # orden cronologico
    texto = str(j).lower()
    assert "punteado" not in texto and "conciliar" not in texto and "acciones" not in j
    assert all(set(m) == {"movimiento_id", "fecha", "importe", "descripcion", "clase", "hechos"}
               for m in j["movimientos"])
    vacia = lab.cli.get(f"/v1/cuentas/{lab.c2}/movimientos", headers=h.AUTH).json()
    assert vacia["movimientos"] == []                                          # solo los de ESA cuenta
    pag = lab.cli.get(f"/v1/cuentas/{lab.c1}/movimientos", params={"limite": 1}, headers=h.AUTH).json()
    assert len(pag["movimientos"]) == 1 and pag["hay_mas"] is True
    owner_b, actor_b = h.crear_tenant()                                         # RLS: cuenta ajena -> 404 sin eco
    cli_b = h.cliente(owner_b)
    r = cli_b.get(f"/v1/cuentas/{lab.c1}/movimientos", headers=h.AUTH)
    assert r.status_code == 404 and str(lab.c1) not in r.text


def test_o_pag_26_resultado_del_mes_cuenta_mi_parte_de_gastos_y_nunca_la_mejora(lab):
    base = D(_resultado(lab)["gastos_propios"])
    for pagos, saldos in (([_yo(lab, "1000.00")], [_saldo(lab, "ME_DEBE", "500.00")]),
                          ([_yo(lab, "500.00"), _t(lab, "500.00")], [_saldo(lab, "NADA")]),
                          ([_t(lab, "1000.00")], [_saldo(lab, "LE_DEBO", "500.00")])):
        for clase in ("REPARACION", "GASTO_CORRIENTE", "MEJORA"):
            _registrar(lab, _peticion(lab, clase=clase, importe="1000.00", pagos=pagos, saldos=saldos))
    assert D(_resultado(lab)["gastos_propios"]) - base == D("3000.00")        # 3 casos x 2 clases x 500


def test_o_pag_27_h_pag_03_pendiente_con_suma_la_obligacion_y_0_tras_op12b(lab):
    p = _peticion(lab, pagos=[_t(lab, "8000.00")], saldos=[_saldo(lab, "LE_DEBO", "4000.00")])
    _registrar(lab, p)
    te_debe, le_debes, _ = _pendiente(lab)
    assert le_debes == "4000.00"
    _, r = m3.cobro(lab.cli, _entidad_posicion(lab, p["intencion_id"]), lab.c1, "4000.00", fecha="2026-06-01",
                    accion="pago")
    assert r.status_code == 200, r.text
    assert _pendiente(lab)[1] in ("0.00", None, "0")


def test_m_pag_23_un_unico_punto_de_llamada_a_op22_en_c_mej_01():
    """§1.2.2: v1 y v2 de C-MEJ-01 comparten UNA llamada a OP-22 (registrar_hecho_compuesto) y pagos.py no llama."""
    arbol = ast.parse((APP / "patrimonio/gasto_propiedad.py").read_text(encoding="utf-8"))
    func = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "registrar_gasto")
    llamadas = [n for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "registrar_hecho_compuesto"]
    assert len(llamadas) == 1
    for modulo in ("patrimonio/pagos.py", "patrimonio/lecturas_pag.py", "patrimonio/rutas_pag.py"):
        assert "registrar_hecho_compuesto" not in (APP / modulo).read_text(encoding="utf-8")


def test_rutas_de_pag_son_exactamente_dos_lecturas():
    import re
    rutas = re.findall(r'@app\.(get|post|put|patch|delete)\("([^"]+)"',
                       (APP / "patrimonio/rutas_pag.py").read_text(encoding="utf-8"))
    assert sorted(rutas) == [("get", "/v1/cuentas/{cuenta_id}/movimientos"), ("get", "/v1/patrimonio/invertido-mes")]
