# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_255_f06_01_b3_gasto_propiedad.py
# Ruta: tests/api/test_255_f06_01_b3_gasto_propiedad.py
# Descripcion: F06 T1-F06 · B3 N1 · C-MEJ-01 y C-MEJ-02, reparto propuesto y deuda por defecto, por HTTP como
#   gapto_runtime con RLS (contratos R1 v0.9.5 Parte III; oraculos v0.7):
#   - alta de las tres clases (O3.1, O3.2, O3.3 sin servicio), O3.4 sin clase, DTO de clase/categoria/
#     presupuestable, O5.39 (DESCONOCIDA en las tres clases y en C-MEJ-02), M-8 DE_OTROS, identidad (replay e
#     IDENTIDAD_REUTILIZADA), C-MEJ-02 (sin pago, version, fecha futura);
#   - reparto (§III.1bis 1-7, 9): O9.8-O9.13; deuda (8, 8bis, 8ter): O9.14-O9.16, O9.18-O9.22 y O9.24;
#   - lecturas: propuesta en la fecha del hecho, L-GASTO-PROPIEDAD (intencion_correccion_id y limitacion de
#     8quater con deuda), lista de gastos y L-COSTE de MEJORAS con los componentes de B3 (politica de B2, §II.6).
#   Cada rechazo comprueba el estado identico (huella de las tablas de B3).
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# Version: 0.1.1 (F06 T1-F06 B3 N1, tirada de mutantes del paso 10): O9.21 con «No lo sé» y un derecho confirmado o
#   una aportacion manual sin deuda declarada (el caso que alcanza la guarda de la exclusion 4; M-DM02-13 quedaba VIVO).
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


def _rechazo(lab, cuerpo, status, codigo=None):
    antes = b3.huella()
    r = lab.registrar(cuerpo)
    assert r.status_code == status, r.text
    if codigo:
        assert r.json()["codigo"] == codigo
    assert b3.huella() == antes
    return r


# ------------------------------------------------------------------ alta de las tres clases
def test_o3_1_mejora_valor_activo_transformacion_desconocida_y_vinculo_de_nivel_efecto(lab):
    c = lab.cuerpo(clase="MEJORA", importe="8500.00", fecha="2026-02-10")
    r = lab.ok(c)
    hid = c["intencion_id"]
    assert r["tipo_hecho"] == "MEJORA_PATRIMONIAL" and r["clase"] == "MEJORA" and r["gasto_del_mes"] == "0.00"
    ef = lab.efectos(hid)
    efecto = uuid.uuid5(uuid.UUID(hid), "gapto.f06.gasto_propiedad.efecto")
    assert [(e[0], e[1], e[2], e[3], e[4]) for e in ef] == [(efecto, "VALOR_ACTIVO", "8500.0000", None,
                                                             "TRANSFORMACION_CAPITALIZABLE")]
    assert lab.hecho(hid)[:4:2] + lab.hecho(hid)[3:4] == ("MEJORA_PATRIMONIAL", False, "DESCONOCIDA")
    v = lab.sql("SELECT id, efecto_id, principal, tipo_relacion FROM gapto.hecho_entidades WHERE hecho_id = %s", (hid,))
    assert v == [(b3.marca(hid), efecto, True, "AFECTA_A")]
    atr = lab.sql("SELECT actor_id::text, importe_atribuido::text, criterio_atribucion FROM gapto.efecto_atribuciones "
                  "WHERE efecto_id = %s ORDER BY 2", (efecto,))
    assert sorted(a[1] for a in atr) == ["4250.0000", "4250.0000"] and {a[2] for a in atr} == {"PARTICIPACION_ENTIDAD"}
    mov = lab.sql("SELECT m.importe::text FROM gapto.hecho_movimientos_tesoreria x JOIN gapto.movimientos_tesoreria m "
                  "ON m.id = x.movimiento_tesoreria_id WHERE x.hecho_id = %s", (hid,))
    assert mov == [("-8500.0000",)]
    assert r["intencion_correccion_id"] == b3.intencion_vigente(efecto)
    coste = b2.leer_coste(lab.cli, lab.pid)
    assert coste["MEJORAS"]["total"] == "8500.00" and coste["MEJORAS"]["estado"] == "PARCIAL"


@pytest.mark.parametrize("clase", ["REPARACION", "GASTO_CORRIENTE"])
def test_o3_2_o3_3_gasto_con_categoria_y_presupuestable_la_clase_no_se_persiste(lab, clase):
    c = lab.cuerpo(clase=clase, importe="300.00")
    r = lab.ok(c)
    hid = c["intencion_id"]
    assert r["tipo_hecho"] == "GASTO" and r["gasto_del_mes"] == "-300.00"
    ef = lab.efectos(hid)
    assert [(e[1], e[2], e[3], e[4]) for e in ef] == [("GASTO", "300.0000", lab.cat, None)]
    assert lab.hecho(hid)[:4:2] + lab.hecho(hid)[3:4] == ("GASTO", True, "DESCONOCIDA")
    g = lab.leer_gasto(hid)
    assert g["clase"] == "GASTO" and g["tipo_hecho"] == "GASTO"     # ninguna lectura distingue la clase (AJ-11)


def test_o3_4_sin_clase_y_dto_de_clase(lab):
    c = lab.cuerpo()
    del c["clase"]
    _rechazo(lab, c, 422, "CLASE_GASTO_PROPIEDAD_AUSENTE")
    _rechazo(lab, lab.cuerpo(clase="MEJORA", categoria_id=str(lab.cat)), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(clase="MEJORA", presupuestable=False), 422, "ENTRADA_INVALIDA")
    sin = lab.cuerpo()
    del sin["presupuestable"]
    _rechazo(lab, sin, 422, "ENTRADA_INVALIDA")
    sin = lab.cuerpo()
    del sin["categoria_id"]
    _rechazo(lab, sin, 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(servicio_id=str(uuid.uuid4())), 422)              # DTO estricto
    _rechazo(lab, lab.cuerpo(fecha="2026-10-11"), 422, "FECHA_FUTURA")


def test_o5_39_desconocida_en_las_tres_clases_y_en_c_mej_02(lab):
    ids = []
    for clase in ("MEJORA", "REPARACION", "GASTO_CORRIENTE"):
        c = lab.cuerpo(clase=clase)
        lab.ok(c)
        ids.append(c["intencion_id"])
    mh = lab.cuerpo_mh()
    assert lab.mejora_historica(mh).status_code == 200
    ids.append(mh["intencion_id"])
    assert [lab.hecho(i)[3] for i in ids] == ["DESCONOCIDA"] * 4


def test_m8_propiedad_de_otros_operacion_no_permitida(lab):
    otra = b.crear(lab.cli, b.alta({"modo": "DE_OTROS", "desde": "2026-01-01",
                                    "partes": [b.de(lab.t, "100")]}, nombre="Casa de Tomás"))
    c = lab.cuerpo(pid=otra["id"], atribucion={"modo": "NO_LO_SE"}, deuda=[])
    _rechazo(lab, c, 422, "OPERACION_NO_PERMITIDA_EN_ESTADO")


def test_identidad_replay_idempotente_y_reutilizacion(lab):
    c = lab.cuerpo()
    primero = lab.ok(c)
    antes = b3.huella()
    segundo = lab.ok(c)
    assert segundo["idempotente"] is True and b3.huella() == antes
    assert segundo["hecho_id"] == primero["hecho_id"]
    otro = dict(c, importe="301.00")
    _rechazo(lab, otro, 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")


def test_propiedad_ajena_o_inexistente_404(lab):
    _rechazo(lab, lab.cuerpo(pid=uuid.uuid4(), atribucion={"modo": "NO_LO_SE"}, deuda=[]), 404,
             "AGREGADO_NO_ENCONTRADO")


# ------------------------------------------------------------------ C-MEJ-02
def test_c_mej_02_mejora_historica_sin_pago_version_y_fecha(lab):
    c = lab.cuerpo_mh(fecha="2026-02-10")
    r = lab.mejora_historica(c)
    assert r.status_code == 200, r.text
    hid = c["intencion_id"]
    assert lab.hecho(hid)[:4:2] + lab.hecho(hid)[3:4] == ("MEJORA_PATRIMONIAL", False, "DESCONOCIDA")
    assert lab.sql("SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s", (hid,)) == [(0,)]
    ef = lab.efectos(hid)
    assert [(e[1], e[4]) for e in ef] == [("VALOR_ACTIVO", "TRANSFORMACION_CAPITALIZABLE")]
    assert lab.sql("SELECT id FROM gapto.hecho_entidades WHERE hecho_id = %s", (hid,)) == [
        (b3.marca(hid, "gapto.f06.mejora_historica."),)]
    assert lab.leer_gasto(hid)["procedencia"] == "MEJORA_HISTORICA"
    antes = b3.huella()
    vieja = lab.cuerpo_mh(version=lab.version_propiedad() + 5)
    assert lab.mejora_historica(vieja).json()["codigo"] == "VERSION_DESFASADA"
    futura = lab.cuerpo_mh(fecha="2026-10-11", atribucion={"modo": "NO_LO_SE"})
    assert lab.mejora_historica(futura).json()["codigo"] == "FECHA_FUTURA"
    assert b3.huella() == antes
    assert lab.mejora_historica(c).json()["idempotente"] is True


# ------------------------------------------------------------------ reparto propuesto (§III.1bis)
def test_o9_8_propuesta_por_la_propiedad_nunca_por_la_cuenta_pagadora():
    lab = b3.Lab(titularidad=b.solo_mia(desde="2026-01-01"), cambio=False)
    otro = h.crear_actor_tercero(lab.owner)
    c2 = h.crear_cuenta(lab.owner, [(lab.actor, 50), (otro, 50)])
    p = lab.propuesta("2026-06-10", cuenta=c2).json()
    assert [(x["yo"], x["porcentaje"]) for x in p["partes"]] == [(True, "100.0000")]
    assert p["cuenta"]["solo_mia"] is False and p["cuenta"]["compartida_con"] == [str(otro)]
    c = lab.cuerpo(fecha="2026-06-10", cuenta=c2)
    assert c["atribucion"]["propuesta_vista"]["partes"] == [{"actor_id": lab.yo, "porcentaje": "100.0000"}]
    lab.ok(c)
    atr = lab.sql("SELECT actor_id::text, importe_atribuido::text FROM gapto.efecto_atribuciones t JOIN "
                  "gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s", (c["intencion_id"],))
    assert atr == [(lab.yo, "300.0000")]


def test_o9_9_titularidad_en_la_fecha_del_hecho_no_la_de_hoy(lab):
    mayo = lab.propuesta("2026-05-15").json()
    junio = lab.propuesta("2026-06-10").json()
    assert sorted(x["porcentaje"] for x in mayo["partes"]) == ["50.0000", "50.0000"]
    assert [(x["yo"], x["porcentaje"]) for x in junio["partes"]] == [(True, "100.0000")]
    t = next(x for x in mayo["partes"] if not x["yo"])
    assert t["naturaleza"] == "PERSONA" and t["nombre"] == "Tomás"
    c = lab.cuerpo(fecha="2026-05-15")
    lab.ok(c)
    atr = lab.sql("SELECT importe_atribuido::text FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e "
                  "ON e.id = t.efecto_id WHERE e.hecho_id = %s", (c["intencion_id"],))
    assert sorted(a[0] for a in atr) == ["150.0000", "150.0000"]


def test_o9_10_no_lo_se_y_manual(lab):
    c = lab.cuerpo(atribucion={"modo": "NO_LO_SE"}, deuda=[])
    lab.ok(c)
    assert lab.efectos(c["intencion_id"])[0][5] == "NO_DISPONIBLE"
    assert lab.sql("SELECT count(*) FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e ON e.id = t.efecto_id "
                   "WHERE e.hecho_id = %s", (c["intencion_id"],)) == [(0,)]
    m = lab.cuerpo(atribucion={"modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "70"},
                                                             {"actor_id": lab.ta, "porcentaje": "30"}]})
    lab.ok(m)
    atr = lab.sql("SELECT importe_atribuido::text, criterio_atribucion FROM gapto.efecto_atribuciones t JOIN "
                  "gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s ORDER BY 1", (m["intencion_id"],))
    assert atr == [("210.0000", "MANUAL"), ("90.0000", "MANUAL")]


def test_o9_11_hechos_previos_no_se_reinterpretan(lab):
    previo = lab.cuerpo(atribucion={"modo": "NO_LO_SE"}, deuda=[], fecha="2026-05-01")
    lab.ok(previo)
    b3b = lab.cuerpo(atribucion={"modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]},
                     fecha="2026-05-02", deuda=[])
    lab.ok(b3b)
    def foto():
        return lab.sql("SELECT e.hecho_id::text, e.estado_atribucion, coalesce(string_agg(t.actor_id::text || ':' || "
                       "t.importe_atribuido::text, ',' ORDER BY t.actor_id), '') FROM gapto.hecho_efectos e LEFT JOIN "
                       "gapto.efecto_atribuciones t ON t.efecto_id = e.id WHERE e.hecho_id IN (%s, %s) "
                       "GROUP BY 1, 2 ORDER BY 1", (previo["intencion_id"], b3b["intencion_id"]))
    antes = foto()
    aud = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id IN (%s, %s)",
                  (previo["intencion_id"], b3b["intencion_id"]))
    lab.ok(lab.cuerpo(fecha="2026-05-15"))
    assert foto() == antes
    assert lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id IN (%s, %s)",
                   (previo["intencion_id"], b3b["intencion_id"])) == aud


def test_o9_12_sin_titularidad_en_la_fecha_no_hay_propuesta():
    lab = b3.Lab(titularidad={"modo": "DESCONOCIDA"}, cambio=False)
    p = lab.propuesta("2026-05-15").json()
    assert p["titularidad_disponible"] is False and p["partes"] == []
    forzada = {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
        "criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": "2026-05-15",
        "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]}}
    _rechazo(lab, lab.cuerpo(atribucion=forzada, deuda=[]), 422, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA")


def test_o9_12_c_mej_02_antes_de_toda_titularidad(lab):
    p = lab.propuesta("2025-01-01").json()
    assert p["titularidad_disponible"] is False
    forzada = {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
        "criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": "2025-01-01",
        "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]}}
    antes = b3.huella()
    r = lab.mejora_historica(lab.cuerpo_mh(fecha="2025-01-01", atribucion=forzada))
    assert r.json()["codigo"] == "TITULARIDAD_NO_DISPONIBLE_EN_FECHA" and b3.huella() == antes


def test_o9_13_propuesta_desfasada(lab):
    vista = lab.vista("2026-05-15")
    vista["partes"] = [{"actor_id": lab.yo, "porcentaje": "60.0000"}, {"actor_id": lab.ta, "porcentaje": "40.0000"}]
    _rechazo(lab, lab.cuerpo(atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": vista}), 409,
             "ATRIBUCION_PROPUESTA_DESFASADA")


# ------------------------------------------------------------------ deuda (8, 8bis, 8ter)
def _si(lab, importe="150.00"):
    return dict(deuda=[{"actor_id": lab.ta, "me_debe": "SI"}], derechos=[{"actor_id": lab.ta, "importe": importe}])


def test_o9_14_deuda_por_defecto_confirmada_crea_derecho_por_su_parte(lab):
    c = lab.cuerpo(**_si(lab))
    r = lab.ok(c)
    hid = c["intencion_id"]
    assert [(p["actor_id"], p["importe"]) for p in r["posiciones"]] == [(lab.ta, "150.0000")]
    pos = lab.posiciones(hid)
    assert [(x[1], str(x[2])) for x in pos] == [("DERECHO_COBRO", lab.ta)]
    assert len(lab.efectos(hid)) == 2                                  # principal + causal de la posicion
    pendiente = lab.cli.get(f"/v1/terceros/{lab.t}/pendiente", headers=h.AUTH)
    assert pendiente.status_code == 200, pendiente.text
    assert pendiente.json()["te_debe"] == "150.00"
    g = lab.leer_gasto(hid)
    assert g["con_deuda"] is True and g["intencion_correccion_id"] is None and g["limitacion"] == b3.LIMITACION


def test_o9_15_no_sin_posicion(lab):
    c = lab.cuerpo()
    r = lab.ok(c)
    assert r["posiciones"] == [] and lab.posiciones(c["intencion_id"]) == []
    assert c["deuda"] == [{"actor_id": lab.ta, "me_debe": "NO"}]


def test_o9_16_cuenta_compartida_solo_con_aportacion_manual(lab):
    _rechazo(lab, lab.cuerpo(cuenta=lab.c2, **_si(lab)), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(cuenta=lab.c2, aportacion="MANUAL", **_si(lab, "150.01")), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(aportacion="MANUAL", **_si(lab, "100.00")), 422, "ENTRADA_INVALIDA")  # cuenta solo mia
    c = lab.cuerpo(cuenta=lab.c2, aportacion="MANUAL", **_si(lab, "100.00"))
    r = lab.ok(c)
    assert [(p["actor_id"], p["importe"]) for p in r["posiciones"]] == [(lab.ta, "100.0000")]


def test_o9_18_empresa_no_admite_te_debe():
    lab = b3.Lab(naturaleza_t="EMPRESA")
    _rechazo(lab, lab.cuerpo(**_si(lab)), 422, "ENTRADA_INVALIDA")
    p = lab.propuesta("2026-05-15").json()
    assert next(x for x in p["partes"] if not x["yo"])["naturaleza"] == "EMPRESA"
    c = lab.cuerpo()
    assert lab.ok(c)["posiciones"] == []


def test_o9_19_sin_el_campo_me_debe_422(lab):
    _rechazo(lab, lab.cuerpo(deuda=[]), 422, "ENTRADA_INVALIDA")
    sin = lab.cuerpo()
    del sin["deuda"]
    _rechazo(lab, sin, 422, "ENTRADA_INVALIDA")


def test_o9_20_c_mej_02_no_admite_derecho(lab):
    antes = b3.huella()
    r = lab.mejora_historica(lab.cuerpo_mh(deuda=[{"actor_id": lab.ta, "me_debe": "SI"}]))
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA" and b3.huella() == antes
    r = lab.mejora_historica(lab.cuerpo_mh(deuda=[{"actor_id": lab.ta, "me_debe": "SI"}]) | {
        "derechos_confirmados": [{"actor_id": lab.ta, "importe": "1500.00"}]})
    assert r.status_code == 422 and b3.huella() == antes


def test_o9_21_no_lo_se_no_admite_derecho(lab):
    _rechazo(lab, lab.cuerpo(atribucion={"modo": "NO_LO_SE"}, **_si(lab)), 422, "ENTRADA_INVALIDA")
    # sin partes no hay cotitular al que deber: un derecho confirmado o una aportacion manual sueltos -> 422
    _rechazo(lab, lab.cuerpo(atribucion={"modo": "NO_LO_SE"}, deuda=[],
                             derechos=[{"actor_id": lab.ta, "importe": "150.00"}]), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(atribucion={"modo": "NO_LO_SE"}, deuda=[], aportacion="MANUAL"), 422, "ENTRADA_INVALIDA")


def test_o9_22_sin_confirmacion_o_con_otro_importe_422(lab):
    _rechazo(lab, lab.cuerpo(deuda=[{"actor_id": lab.ta, "me_debe": "SI"}]), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(**_si(lab, "149.99")), 422, "ENTRADA_INVALIDA")
    _rechazo(lab, lab.cuerpo(derechos=[{"actor_id": lab.ta, "importe": "150.00"}]), 422, "ENTRADA_INVALIDA")


def test_o9_24_la_posicion_no_es_un_movimiento(lab):
    con = lab.cuerpo(**_si(lab))
    sin = lab.cuerpo()
    lab.ok(con)
    lab.ok(sin)
    def mov(hid):
        return lab.sql("SELECT m.cuenta_id, m.importe::text FROM gapto.hecho_movimientos_tesoreria x JOIN "
                       "gapto.movimientos_tesoreria m ON m.id = x.movimiento_tesoreria_id WHERE x.hecho_id = %s", (hid,))
    assert mov(con["intencion_id"]) == mov(sin["intencion_id"]) == [(lab.c1, "-300.0000")]
    total = lab.sql("SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s", (lab.c1,))
    assert total == [(2,)]


# ------------------------------------------------------------------ lecturas
def test_lectura_lista_y_404_de_hecho_de_otra_propiedad(lab):
    c = lab.cuerpo()
    lab.ok(c)
    lista = lab.cli.get(f"/v1/propiedades/{lab.pid}/gastos", headers=h.AUTH).json()["gastos"]
    assert [g["hecho_id"] for g in lista] == [c["intencion_id"]]
    otra = b.crear(lab.cli, b.alta(b.solo_mia(), nombre="Otra"))
    assert lab.gasto(c["intencion_id"], pid=otra["id"]).status_code == 404
    assert lab.gasto(uuid.uuid4()).status_code == 404


def test_consumidores_0352_siguen_bloqueados():
    from app.patrimonio import habilitacion
    assert habilitacion.CONSUMIDORES_0352_HABILITADOS is False
