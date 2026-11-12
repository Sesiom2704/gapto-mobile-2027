# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_250_f06_01_b2_compra.py
# Ruta: tests/api/test_250_f06_01_b2_compra.py
# Descripcion: F06 T1-F06 · B2 N1 · C-COMPRA-01 por HTTP, como gapto_runtime con RLS (adaptador real):
#   - O2′ (composicion H0/Hk, atribucion M-2, respuesta: sale_de_tus_cuentas, liquidez_atribuible por la
#     participacion de cada cuenta, gasto_del_mes 0, coste_adquisicion; valoracion COMPRA y FISCAL_REFERENCIA);
#   - O6′ (O6.1, O6.2, O6.5-O6.10) e identidad del lote con el comparador propio (O6.14-O6.16, O6.19, O6.21,
#     O6.14 bis, inventario sin metodos privados de OP-22);
#   - O8.4, O8.5 (precedencias), O8.7 (HF-10), O9.7 (redondeo M-2 con residuo), O9.2/O9.3 (conjunto completo);
#   - fecha de escritura (AJ-TR1-10): O6.22, O6.23, O6.25, O6.26 (+ Jest de la pantalla en el cliente);
#   - HF-12 (criterio y ids de atribucion), HF-16 / O6.18 (valoracion COMPRA y C-PROP-05 con la intencion de la
#     compra), elegibilidad de cuentas por la operacion de pago explicita (PB0-05).
#   Los consumidores de 0352 (declaracion) solo se activan dentro del test que los prueba (habilitar_0352).
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import pathlib
import re
import uuid
from decimal import Decimal

import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.services.compuesto_service import HechosCompuestosService

RAIZ = pathlib.Path(__file__).resolve().parents[2]
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


@pytest.fixture()
def lab():
    return c2.Lab()


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


def _hechos(lab, h0) -> list[tuple]:
    return lab.sql("SELECT h.id::text, th.codigo, h.fecha_hecho::text, h.importe_total::text, h.presupuestable "
                   "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
                   "WHERE h.id = %s OR h.id IN (SELECT hecho_origen_id FROM gapto.hecho_relaciones "
                   "WHERE hecho_destino_id = %s) ORDER BY h.fecha_hecho, h.id", (h0, h0))


# ================================================================== O2′
def test_o2_compra_completa_composicion_y_respuesta(lab):
    cuerpo = lab.peticion(valor_referencia="150000.00")
    j = _ok(lab.compra(cuerpo))
    h0 = cuerpo["intencion_id"]
    assert j["idempotente"] is False
    compra = j["compra"]
    assert compra["sale_de_tus_cuentas"] == "-216830.00"
    assert compra["liquidez_atribuible"] == "-215015.00"          # C1 100 % + C2 50 %; no la titularidad (-130.098)
    assert compra["gasto_del_mes"] == "0.00"
    assert [x["linea_id"] for x in compra["hechos"]][0] is None and len(compra["hechos"]) == 4
    coste = compra["coste_adquisicion"]
    assert coste["total"] == "216830.00" and coste["estado"] == "PARCIAL" and coste["motivo_estado"] == "SIN_DECLARACION"
    assert coste["tu_parte"] == {"importe": "130098.00", "estado": "COMPLETO"}
    hechos = _hechos(lab, h0)
    assert len(hechos) == 4 and {x[1] for x in hechos} == {"ADQUISICION_PATRIMONIAL"}
    assert all(x[4] is False for x in hechos)
    # efectos VALOR_ACTIVO causa ADQUISICION con AFECTA_A principal de nivel efecto (HF-08)
    efectos = lab.sql("SELECT e.tipo_efecto, e.causa_valor_activo, e.importe_delta::text, x.principal, "
                      "x.efecto_id = e.id FROM gapto.hecho_efectos e JOIN gapto.hecho_entidades x ON x.hecho_id = e.hecho_id "
                      "WHERE x.entidad_id = %s ORDER BY e.importe_delta", (lab.pid,))
    assert [(e[0], e[1], e[3], e[4]) for e in efectos] == [("VALOR_ACTIVO", "ADQUISICION", True, True)] * 4
    # agencia: fecha economica 2026-02-28 sin cambio (AJ-TR1-10 (a)); H0 en la escritura
    assert ("2026-02-28", "3630.0000") in {(x[2], x[3]) for x in hechos}
    assert (h0, "ADQUISICION_PATRIMONIAL", c2.ESCRITURA, "200000.0000", False) in hechos
    # valoraciones COMPRA y FISCAL_REFERENCIA con ids derivados (HF-16)
    vals = dict(lab.sql("SELECT metodo, id::text FROM gapto.propiedad_valoraciones WHERE propiedad_entidad_id = %s",
                        (lab.pid,)))
    assert vals["COMPRA"] == str(uuid.uuid5(uuid.UUID(h0), "gapto.f06.compra.valoracion"))
    assert vals["FISCAL_REFERENCIA"] == str(uuid.uuid5(uuid.UUID(h0), "gapto.f06.compra.valoracion_fiscal"))
    # atribucion M-2: PARTICIPACION_ENTIDAD, ids uuid5(efecto, prefijo + actor), 60/40 (HF-12)
    e0 = uuid.uuid5(uuid.UUID(h0), "gapto.f06.compra.efecto")
    atr = set(lab.sql("SELECT id::text, actor_id::text, round(importe_atribuido, 2)::text, criterio_atribucion FROM "
                      "gapto.efecto_atribuciones WHERE efecto_id = %s", (e0,)))
    assert atr == {(str(uuid.uuid5(e0, f"gapto.f06.compra.atribucion:{lab.a}")), lab.a, "80000.00", "PARTICIPACION_ENTIDAD"),
                   (str(uuid.uuid5(e0, f"gapto.f06.compra.atribucion:{lab.yo}")), lab.yo, "120000.00",
                    "PARTICIPACION_ENTIDAD")}
    # vinculo de H0 con el sello; PARTE_DE compra.lote de cada Hk; row_version + 1
    assert j["propiedad"]["row_version"] == 2
    rel = lab.sql("SELECT id::text, hecho_origen_id::text FROM gapto.hecho_relaciones WHERE hecho_destino_id = %s", (h0,))
    assert len(rel) == 3 and all(i == str(uuid.uuid5(uuid.UUID(o), "gapto.f06.compra.lote")) for i, o in rel)


def test_o2_respuesta_con_importes_en_texto_y_movimientos_conciliados(lab):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    movs = lab.sql("SELECT m.importe::text, m.cuenta_id::text FROM gapto.movimientos_tesoreria m JOIN "
                   "gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id = m.id WHERE c.hecho_id IN "
                   "(SELECT hecho_id FROM gapto.hecho_entidades WHERE entidad_id = %s) ORDER BY m.importe", (lab.pid,))
    assert [m[0] for m in movs] == ["-180000.0000", "-20000.0000", "-12000.0000", "-3630.0000", "-1200.0000"]


# ================================================================== O6′ e identidad del lote
def _replay_igual(lab, cuerpo, esperado_idempotente=True):
    antes = c2.huella()
    r = lab.compra(cuerpo)
    assert c2.huella() == antes, "replay o rechazo con escrituras o auditoria (O6.14 bis)"
    return r


def test_o6_1_replay_reordenado_es_idempotente_sin_escribir_ni_invocar_op22(lab, monkeypatch):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    llamadas = []
    original = HechosCompuestosService.registrar_hecho_compuesto
    monkeypatch.setattr(HechosCompuestosService, "registrar_hecho_compuesto",
                        lambda self, *a, **k: llamadas.append(1) or original(self, *a, **k))
    reordenado = {**cuerpo, "gastos": list(reversed(cuerpo["gastos"])),
                  "pagos_propios": list(reversed(cuerpo["pagos_propios"]))}
    r = _replay_igual(lab, reordenado)
    assert _ok(r)["idempotente"] is True
    assert llamadas == []                                                  # O6.14: 0 invocaciones de OP-22
    assert _ok(_replay_igual(lab, cuerpo))["idempotente"] is True         # replay con la version ya superada


@pytest.mark.parametrize("cambio", ["sin_agencia", "linea_nueva", "itp_cambiado", "linea_id_cambiado",
                                    "otra_atribucion", "otra_valor_referencia"])
def test_o6_2_a_o6_7_reintento_distinto_es_reutilizada(lab, cambio):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    otro = dict(cuerpo)
    gastos = [dict(g) for g in cuerpo["gastos"]]
    if cambio == "sin_agencia":
        otro["gastos"] = gastos[:2]
    elif cambio == "linea_nueva":
        otro["gastos"] = gastos + [lab.gasto("OTRO", "400.00", c2.ESCRITURA, c2.ESCRITURA)]
    elif cambio == "itp_cambiado":
        gastos[0]["importe"] = "12000.01"
        otro["gastos"] = gastos
    elif cambio == "linea_id_cambiado":
        gastos[1]["linea_id"] = str(uuid.uuid4())
        otro["gastos"] = gastos
    elif cambio == "otra_atribucion":
        otro["atribucion"] = {"modo": "NO_LO_SE"}
    else:
        otro["valor_referencia"] = "1.00"
    _rechazo(_replay_igual(lab, otro), 409, REUTILIZADA)


def test_o6_8_gasto_posterior_no_entra_en_el_lote_sellado(lab):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    _ok(lab.gasto_posterior(lab.peticion03(lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02"))))
    assert _ok(_replay_igual(lab, cuerpo))["idempotente"] is True


def test_o6_9_o6_16_o6_21_parte_de_ajena_hacia_h0(lab):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    h0 = uuid.UUID(cuerpo["intencion_id"])
    otro = lab.peticion(gastos=[])                    # otra compra de otra propiedad: un hecho ajeno
    lab2 = c2.Lab()
    _ok(lab2.compra({**otro, "row_version_esperada": 1, "atribucion": {"modo": "NO_LO_SE"},
                     "pagos_propios": [{**p, "cuenta_id": str(lab2.c1)} for p in otro["pagos_propios"]]}))
    ajeno = uuid.UUID(otro["intencion_id"])
    # el hecho ajeno es de otro owner: se fabrica uno del mismo owner con OP-22 (C-COMPRA-03) y se le anade una
    # PARTE_DE con la marca compra.lote de otro origen (O6.16) o la suya (O6.9/O6.21)
    extra = lab.peticion03(lab.gasto("OTRO", "50.00", "2026-04-01", "2026-04-01"))
    _ok(lab.gasto_posterior(extra))
    x = uuid.UUID(extra["intencion_id"])
    for ident in (uuid.uuid5(x, "gapto.f06.compra.lote"), uuid.uuid5(ajeno, "gapto.f06.compra.lote")):
        c2.como_owner(lab.owner, "INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, "
                                 "tipo_relacion) VALUES (%s, %s, %s, 'PARTE_DE')", (ident, x, h0))
        _rechazo(_replay_igual(lab, cuerpo), 409, REUTILIZADA)
        c2.como_owner(lab.owner, "DELETE FROM gapto.hecho_relaciones WHERE id = %s", (ident,))
    assert _ok(_replay_igual(lab, cuerpo))["idempotente"] is True


def test_o6_10_misma_peticion_por_la_ruta_de_c_compra_03(lab):
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    g = cuerpo["gastos"][0]
    _rechazo(lab.gasto_posterior(lab.peticion03(g, intencion_id=cuerpo["intencion_id"])), 409, REUTILIZADA)


def test_o6_15_campo_cambiado_en_un_hk_rompe_el_replay(lab):
    cuerpo = lab.peticion(atribucion={"modo": "NO_LO_SE"})      # sin atribuciones: el fixture solo toca el importe
    _ok(lab.compra(cuerpo))
    hk = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), f"gapto.f06.compra.gasto:{cuerpo['gastos'][0]['linea_id']}")
    # por fixture (la ruta de OP-21 sobre Hk no existe, §II.7): importe del efecto cambiado
    c2.como_owner(lab.owner, "UPDATE gapto.hecho_efectos SET importe_delta = 12500 WHERE hecho_id = %s", (hk,))
    _rechazo(_replay_igual(lab, cuerpo), 409, REUTILIZADA)


def test_o6_19_lote_parcial_no_se_completa(lab, monkeypatch):
    cuerpo = lab.peticion(gastos=[lab.gasto("ITP", "12000.00", c2.ESCRITURA, c2.ESCRITURA)])
    _ok(lab.compra(cuerpo))
    con_otro = {**cuerpo, "gastos": cuerpo["gastos"] + [lab.gasto("OTRO", "100.00", c2.ESCRITURA, c2.ESCRITURA)]}
    llamadas = []
    original = HechosCompuestosService.registrar_hecho_compuesto
    monkeypatch.setattr(HechosCompuestosService, "registrar_hecho_compuesto",
                        lambda self, *a, **k: llamadas.append(1) or original(self, *a, **k))
    _rechazo(_replay_igual(lab, con_otro), 409, REUTILIZADA)
    assert llamadas == []


def test_inventario_sin_metodos_privados_de_op22_ni_subclases():
    texto = "\n".join(f.read_text(encoding="utf-8") for f in (RAIZ / "backend" / "app" / "patrimonio").rglob("*.py"))
    assert "_agregado_coincide" not in texto and "_identidades_declaradas" not in texto
    assert not re.search(r"class\s+\w+\(\s*HechosCompuestosService", texto)


# ================================================================== precedencias y validaciones
def test_o8_4_compra_ya_registrada_antes_que_la_suma(lab):
    _ok(lab.compra(lab.peticion()))
    otra = lab.peticion(precio="1.00")
    antes = c2.huella()
    _rechazo(lab.compra(otra), 409, "COMPRA_YA_REGISTRADA")
    assert c2.huella() == antes


def test_o8_5_cuenta_antes_que_la_propuesta_desfasada(lab):
    cuenta_sin_pago = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=())
    cuerpo = lab.peticion()
    cuerpo["pagos_propios"][0]["cuenta_id"] = str(cuenta_sin_pago)
    cuerpo["atribucion"]["propuesta_vista"]["partes"][0]["porcentaje"] = "59.9999"
    cuerpo["atribucion"]["propuesta_vista"]["partes"][1]["porcentaje"] = "40.0001"
    _rechazo(lab.compra(cuerpo), 422, "CUENTA_DESCONOCIDA")


def test_elegibilidad_por_la_operacion_de_pago_explicita(lab):
    """PB0-05: una cuenta sin PAGAR_GASTO se rechaza por la regla R1 de la operacion GASTO, no por accidente."""
    solo_ingresos = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",))
    cuerpo = lab.peticion()
    cuerpo["gastos"][0]["cuenta_id"] = str(solo_ingresos)
    antes = c2.huella()
    _rechazo(lab.compra(cuerpo), 422, "CUENTA_DESCONOCIDA")
    assert c2.huella() == antes


def test_suma_de_pagos_y_fechas_de_arras_y_firma(lab):
    cuerpo = lab.peticion()
    cuerpo["pagos_propios"][0]["importe"] = "19999.99"
    _rechazo(lab.compra(cuerpo), 422, "SUMA_NO_CUADRA")
    cuerpo = lab.peticion()
    cuerpo["pagos_propios"][1]["fecha_pago"] = "2026-03-21"
    _rechazo(lab.compra(cuerpo), 422, "FECHA_PAGO_INCOHERENTE")
    cuerpo = lab.peticion()
    cuerpo["pagos_propios"][0]["fecha_pago"] = "2026-03-21"
    _rechazo(lab.compra(cuerpo), 422, "FECHA_PAGO_INCOHERENTE")


@pytest.mark.parametrize("cuerpo_extra", [{"hipoteca": {"importe": "1"}}, {"coste_completo": True}],
                         ids=["hipoteca", "campo_desconocido"])
def test_dto_estricto_sin_hipoteca(lab, cuerpo_extra):
    _rechazo(lab.compra({**lab.peticion(), **cuerpo_extra}), 422, "ENTRADA_INVALIDA")


def test_linea_repetida_e_importes_invalidos(lab):
    cuerpo = lab.peticion()
    cuerpo["gastos"][1]["linea_id"] = cuerpo["gastos"][0]["linea_id"]
    _rechazo(lab.compra(cuerpo), 422, "ENTRADA_INVALIDA")
    cuerpo = lab.peticion()
    cuerpo["gastos"][0]["importe"] = "1.001"
    _rechazo(lab.compra(cuerpo), 422, "ENTRADA_INVALIDA")


def test_propiedad_de_otro_owner_o_inexistente(lab):
    otro = c2.Lab()
    cuerpo = lab.peticion()
    r = otro.cli.post(f"/v1/propiedades/{lab.pid}/compra", json=cuerpo, headers=h.AUTH)
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


def test_version_desfasada(lab):
    _rechazo(lab.compra(lab.peticion(version=7)), 409, "VERSION_DESFASADA")


@pytest.mark.parametrize("valor", [{"completo": True}, {"completo": False, "fecha_corte": c2.CORTE}],
                         ids=["completo_sin_corte", "retirar_con_corte"])
def test_o8_7_hf10_completitud_mal_formada(lab, monkeypatch, valor):
    c2.habilitar_0352(monkeypatch)
    _rechazo(lab.compra(lab.peticion(completitud=valor)), 422, "ENTRADA_INVALIDA")


# ================================================================== M-2
def test_o9_7_redondeo_half_even_con_residuo(lab):
    manual = {"modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "25"}, {"actor_id": lab.a, "porcentaje": "75"}]}
    gastos = [lab.gasto("OTRO", "100.10", c2.ESCRITURA, c2.ESCRITURA), lab.gasto("OTRO", "0.05", c2.ESCRITURA, c2.ESCRITURA)]
    cuerpo = lab.peticion(gastos=gastos, atribucion=manual)
    _ok(lab.compra(cuerpo))
    h0 = uuid.UUID(cuerpo["intencion_id"])
    porg = {}
    for g in gastos:
        hk = uuid.uuid5(h0, f"gapto.f06.compra.gasto:{g['linea_id']}")
        porg[g["importe"]] = dict(lab.sql("SELECT t.actor_id::text, round(t.importe_atribuido, 2)::text FROM gapto.efecto_atribuciones t "
                                          "JOIN gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s", (hk,)))
    assert porg["100.10"] == {lab.yo: "25.02", lab.a: "75.08"}
    # 0,05 a 25/75: 0,01 / 0,04 exactos; suma exacta
    assert sum(Decimal(v) for v in porg["0.05"].values()) == Decimal("0.05")
    assert lab.sql("SELECT DISTINCT criterio_atribucion FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e "
                   "ON e.id = t.efecto_id WHERE e.hecho_id = %s", (h0,)) == [("MANUAL",)]


def test_o9_7_empate_50_50_residuo_al_actor_menor(lab):
    a1, b2 = sorted([lab.yo, lab.a])
    manual = {"modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "50"}, {"actor_id": lab.a, "porcentaje": "50"}]}
    g = lab.gasto("OTRO", "0.05", c2.ESCRITURA, c2.ESCRITURA)
    cuerpo = lab.peticion(gastos=[g], atribucion=manual)
    _ok(lab.compra(cuerpo))
    hk = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), f"gapto.f06.compra.gasto:{g['linea_id']}")
    filas = dict(lab.sql("SELECT t.actor_id::text, round(t.importe_atribuido, 2)::text FROM gapto.efecto_atribuciones t "
                         "JOIN gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s", (hk,)))
    assert filas == {a1: "0.03", b2: "0.02"}


@pytest.mark.parametrize("caso", ["porcentaje_distinto", "actor_de_mas"])
def test_o9_2_o9_3_conjunto_completo_y_porcentaje_exacto(lab, caso):
    cuerpo = lab.peticion()
    partes = cuerpo["atribucion"]["propuesta_vista"]["partes"]
    if caso == "porcentaje_distinto":
        partes[0]["porcentaje"], partes[1]["porcentaje"] = (
            ("59.9999", "40.0001") if partes[0]["porcentaje"] == "60.0000" else ("39.9999", "60.0001"))
    else:
        partes.pop()
        partes[0]["porcentaje"] = "100.0000"
    antes = c2.huella()
    _rechazo(lab.compra(cuerpo), 409, "ATRIBUCION_PROPUESTA_DESFASADA")
    assert c2.huella() == antes


def test_o9_5_no_lo_se_sin_atribuciones(lab):
    cuerpo = lab.peticion(atribucion={"modo": "NO_LO_SE"})
    j = _ok(lab.compra(cuerpo))
    assert j["compra"]["coste_adquisicion"]["tu_parte"] == {"importe": None, "estado": "NO_DISPONIBLE"}
    assert lab.sql("SELECT count(*) FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e ON e.id = t.efecto_id "
                   "JOIN gapto.hecho_entidades x ON x.efecto_id = e.id WHERE x.entidad_id = %s", (lab.pid,)) == [(0,)]


# ================================================================== fecha de escritura (AJ-TR1-10)
def test_o6_22_propuesta_en_la_fecha_de_escritura_para_todas_las_raices(lab):
    cuerpo = lab.peticion()          # agencia del 2026-02-28, anterior a la titularidad (desde la escritura)
    assert c2.titularidad_en(lab.cli, lab.pid, "2026-02-28") == []
    _ok(lab.compra(cuerpo))
    agencia = next(g for g in cuerpo["gastos"] if g["concepto"] == "AGENCIA")
    hk = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), f"gapto.f06.compra.gasto:{agencia['linea_id']}")
    assert lab.sql("SELECT fecha_hecho::text FROM gapto.hechos_financieros WHERE id = %s", (hk,)) == [("2026-02-28",)]
    filas = dict(lab.sql("SELECT t.actor_id::text, t.porcentaje_aplicado::text FROM gapto.efecto_atribuciones t "
                         "JOIN gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s", (hk,)))
    assert filas == {lab.yo: "60.0000", lab.a: "40.0000"}


def test_o6_23_sin_titularidad_en_la_escritura_y_fecha_referencia_distinta():
    lab = c2.Lab(titularidad_desde="2026-04-01", fecha_adquisicion="2026-03-01")
    assert c2.titularidad_en(lab.cli, lab.pid, c2.ESCRITURA) == []
    propuesta = {"criterio": "TITULARIDAD_EN_FECHA_ESCRITURA", "fecha_referencia": c2.ESCRITURA,
                 "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]}
    antes = c2.huella()
    _rechazo(lab.compra(lab.peticion(atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": propuesta})),
             422, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA")                       # nunca YO 100 por defecto
    otra = {**propuesta, "fecha_referencia": "2026-04-01",
            "partes": [{"actor_id": p["actor_id"], "porcentaje": p["porcentaje"]} for p in c2.titularidad_en(lab.cli, lab.pid, "2026-04-01")]}
    _rechazo(lab.compra(lab.peticion(atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": otra})),
             422, "ENTRADA_INVALIDA")
    otro_criterio = {**propuesta, "criterio": "TITULARIDAD_EN_FECHA_ECONOMICA"}
    _rechazo(lab.compra(lab.peticion(atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": otro_criterio})),
             422, "ENTRADA_INVALIDA")
    assert c2.huella() == antes


def test_o6_25_no_reatribuye_hechos_previos_ni_cambia_la_titularidad(lab):
    previa = c2.Lab()
    tit_antes = b.huella(("entidad_participaciones",))
    atr_antes = b.huella(("efecto_atribuciones",))
    _ok(previa.compra(previa.peticion()))
    # la compra de `previa` no toca la titularidad ni atribuciones previas de otra propiedad (lab, sin hechos)
    assert b.huella(("entidad_participaciones",)) == tit_antes
    _ok(lab.compra(lab.peticion()))
    filas_previa = previa.sql("SELECT t.id::text, t.importe_atribuido::text FROM gapto.efecto_atribuciones t "
                              "ORDER BY t.id")
    assert len(filas_previa) == 8
    assert atr_antes != b.huella(("efecto_atribuciones",))


def test_o6_26_titularidad_cambiada_entre_la_lectura_y_el_envio(lab):
    cuerpo = lab.peticion()
    # C-PROP-03 de B1 no puede cambiar la titularidad en el pasado: se cambia la del 2026-03-20 por fixture
    c2.como_owner(lab.owner, "UPDATE gapto.entidad_participaciones SET porcentaje = CASE WHEN porcentaje = 60 THEN 50 "
                             "ELSE 50 END WHERE entidad_id = %s", (lab.pid,))
    antes = c2.huella()
    _rechazo(lab.compra(cuerpo), 409, "ATRIBUCION_PROPUESTA_DESFASADA")
    assert c2.huella() == antes


def test_titularidad_en_fecha_lectura_nueva(lab):
    partes = c2.titularidad_en(lab.cli, lab.pid, c2.ESCRITURA)
    assert sorted((p["yo"], p["porcentaje"]) for p in partes) == [(False, "40.0000"), (True, "60.0000")]
    assert c2.titularidad_en(lab.cli, lab.pid, "2026-03-19") == []
    r = lab.cli.get(f"/v1/propiedades/{uuid.uuid4()}/titularidad-en-fecha", params={"fecha": c2.ESCRITURA}, headers=h.AUTH)
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


# ================================================================== HF-16 / O6.18
def test_o6_18_c_prop_05_con_la_intencion_de_la_compra(lab, monkeypatch):
    c2.habilitar_0352(monkeypatch)
    cuerpo = lab.peticion()
    _ok(lab.compra(cuerpo))
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    antes = c2.huella()
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=cuerpo["intencion_id"]), 409, REUTILIZADA)
    assert c2.huella() == antes
