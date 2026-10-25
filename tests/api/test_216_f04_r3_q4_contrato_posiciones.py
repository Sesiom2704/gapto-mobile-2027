# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_216_f04_r3_q4_contrato_posiciones.py
# Ruta: tests/api/test_216_f04_r3_q4_contrato_posiciones.py
# Descripcion: F05-D051 paso 2 · contrato HTTP Q4/Q4-H2 (F05 §65.4, aprobado).
#   Ampliacion aditiva: `apertura_indeterminada` en las tres exposiciones de
#   posiciones (cobro/pago/perdon, «Pendiente con», reparto del hecho) y
#   `estado` en PosicionDeParteHttp; el reparto del hecho lee cada posicion con
#   PosicionesService.saldo (estado autoritativo) y no con el neto OP-20.
#   Semantica de los tres estados, todos por HTTP:
#     - ACTIVA con saldo desconocido      -> saldo null,   indicador false;
#     - CERRADA con apertura conocida     -> saldo "0.00", indicador false;
#     - CERRADA con apertura desconocida  -> saldo "0.00", indicador true, y la
#       apertura sigue desconocida (saldo_apertura NULL en la fila).
#   El estado se prepara SOLO por vias legitimas del motor: el gasto compartido
#   por HTTP (apertura 0) o por OP-22 (HechosCompuestosService) con la misma
#   composicion del adaptador y la posicion dada de alta con apertura y
#   seguimiento desconocidos (patron de test_199); cobro, pago y perdon por
#   HTTP; cierre declarativo F04-D055 A3 con PosicionesService.cerrar_posicion
#   (no hay ruta HTTP de cierre; no se crea ninguna). Sin SQL de escritura: el
#   SQL del test solo lee. La lectura del indicador true en la respuesta de
#   cobro, pago y perdon es la del reintento exacto (idempotente) de la misma
#   intencion tras el cierre, que el motor responde con el estado actual.
#   Aislamiento por owner: otro owner no lee ni opera esas posiciones.
#   Datos sinteticos; base desechable.
# Version: 0.1.0 (F05-D051 paso 2; F05 §65.4 contrato HTTP Q4/Q4-H2; sustituye
#   al test propuesto en Q4_propuesta.diff, renumerado: 215 esta ocupado)
# ============================================================

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest

import f05_01_helpers as fh
import f05_06_m3_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_reparto as rep
from app.api.dto_reparto import IntencionGastoCompartido, PosicionDeParteHttp, PosicionPendiente, ResultadoPosicionHttp
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_posicion import DatosCierre
from app.services.compuesto_service import HechosCompuestosService
from app.services.posiciones_service import PosicionesService
from app.services.previsiones_service import impacto_correccion_ancla

FECHA_CIERRE = dt.date(2026, 10, 10)


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    tania, carlos = m.persona(cli, "Tania"), m.persona(cli, "Carlos")
    return owner, actor, cli, cta, ahorro, tania, carlos


def _ctx(owner):
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def _fila(owner, entidad):
    """(estado, saldo_apertura, fecha_inicio_seguimiento) en la fila, solo lectura."""
    return m.uno(owner, "SELECT estado, saldo_apertura, fecha_inicio_seguimiento "
                        "FROM gapto.derechos_obligaciones_financieras WHERE entidad_id = %s", (entidad,))


def _version_entidad(owner, entidad) -> int:
    return m.uno(owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (entidad,))[0]


def _registrar_con_apertura_desconocida(t, cuerpo: dict) -> uuid.UUID:
    """OP-22 con la composicion del adaptador; la posicion nace con apertura y
    seguimiento desconocidos (realidad valida del motor, F04-D055 A3/A4)."""
    owner, yo, cli, cta, _, tania, carlos = t
    terceros = (tania, carlos)
    _, r = m.cena(cli, cta, tania, carlos, tania_debe="NO")  # crea los actores, sin posicion
    assert r.status_code == 200, r.text
    intencion = IntencionGastoCompartido(**cuerpo)
    datos = rep.componer_gasto_compartido(intencion, yo, {t_: m.actor_de(owner, t_) for t_ in terceros})
    assert len(datos.posiciones) == 1
    datos = dataclasses.replace(datos, posiciones=[dataclasses.replace(
        datos.posiciones[0], saldo_apertura=None, fecha_inicio_seguimiento=None)])
    HechosCompuestosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla).registrar_hecho_compuesto(
        _ctx(owner), datos)
    return intencion.intencion_id


def _cena_desconocida(t):
    _, _, _, cta, _, tania, carlos = t
    c = m.cuerpo("44.50", pagado_por=m.con_cuenta(cta), fecha=m.FECHA_CENA, nota="Cena con amigos",
                 reparto=m.repartir("14.50", (tania, "15.00", "SI"), (carlos, "15.00", "NO")))
    return _registrar_con_apertura_desconocida(t, c)


def _peluqueria_desconocida(t):
    tania = t[5]
    c = m.cuerpo("15.00", pagado_por=m.por_persona(tania, "SI"), reparto=m.SOLO_MIO, nota="Peluquería")
    return _registrar_con_apertura_desconocida(t, c)


def _posicion_de_reparto(cli, hecho, *, tercero=None):
    r = cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH)
    assert r.status_code == 200, r.text
    partes = r.json()["partes"]
    parte = next(p for p in partes if (p["es_yo"] if tercero is None else p["tercero_id"] == str(tercero)))
    return parte["posicion"]


def _terna(d: dict) -> tuple:
    return d["saldo"], d["estado"], d["apertura_indeterminada"]


def _cerrar(owner, entidad, motivo: str):
    return PosicionesService(fh.unidad()).cerrar_posicion(
        _ctx(owner), entidad_id=entidad, entidad_row_version_esperada=_version_entidad(owner, entidad),
        cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=FECHA_CIERRE))


# ------------------------------------------------------------------ Q4-H1 · contrato de los DTO
def test_q4_h1_las_tres_exposiciones_declaran_el_indicador():
    for dto in (ResultadoPosicionHttp, PosicionPendiente, PosicionDeParteHttp):
        campo = dto.model_fields.get("apertura_indeterminada")
        assert campo is not None and campo.annotation is bool and campo.is_required(), dto.__name__
    assert PosicionDeParteHttp.model_fields["estado"].is_required()
    assert set(PosicionDeParteHttp.model_fields) == {"entidad_id", "tipo", "saldo", "estado", "apertura_indeterminada"}


# ------------------------------------------------------------------ CERRADA con apertura conocida
@pytest.mark.parametrize("accion", ["cobro", "perdon"])
def test_derecho_apertura_conocida_cerrado_por_http_es_cero_y_false(t, accion):
    """Cena por HTTP (apertura 0): ACTIVA 15 -> cobro o perdon del total -> CERRADA 0, false (Q4-H2)."""
    owner, _, cli, cta, _, tania, carlos = t
    c, r = m.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    entidad = m.entidad_de_posicion(owner, hecho)
    pos = _posicion_de_reparto(cli, hecho, tercero=tania)
    assert pos == {"entidad_id": str(entidad), "tipo": "DERECHO_COBRO", "saldo": "15.00",
                   "estado": "ACTIVA", "apertura_indeterminada": False}, pos
    p = m.pendiente(cli, tania).json()
    assert [(x["entidad_id"], x["saldo"], x["estado"], x["apertura_indeterminada"]) for x in p["posiciones"]] == [
        (str(entidad), "15.00", "ACTIVA", False)], p

    _, r = m.cobro(cli, entidad, cta, "15.00") if accion == "cobro" else m.perdon(cli, entidad, "15.00")
    assert r.status_code == 200, r.text
    assert _terna(r.json()) == ("0.00", "CERRADA", False), r.json()
    assert _terna(_posicion_de_reparto(cli, hecho, tercero=tania)) == ("0.00", "CERRADA", False)
    assert _fila(owner, entidad)[:2] == ("CERRADA", 0)
    assert m.pendiente(cli, tania).json()["posiciones"] == []  # «Pendiente con» solo lista ACTIVAS


def test_obligacion_apertura_conocida_pagada_por_http_es_cero_y_false(t):
    owner, _, cli, cta, _, tania, _ = t
    c, r = m.peluqueria(cli, tania)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    entidad = m.entidad_de_posicion(owner, hecho)
    assert _terna(_posicion_de_reparto(cli, hecho)) == ("15.00", "ACTIVA", False)
    _, r = m.cobro(cli, entidad, cta, "15.00", accion="pago")
    assert r.status_code == 200, r.text
    assert _terna(r.json()) == ("0.00", "CERRADA", False), r.json()
    assert _terna(_posicion_de_reparto(cli, hecho)) == ("0.00", "CERRADA", False)


# ------------------------------------------------------------------ ACTIVA desconocida -> CERRADA desconocida
@pytest.mark.parametrize("accion,motivo", [("cobro", "LIQUIDADA"), ("perdon", "CONDONADA")])
def test_derecho_apertura_desconocida_tres_estados_por_http(t, accion, motivo):
    owner, _, cli, cta, _, tania, _ = t
    hecho = _cena_desconocida(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    assert _fila(owner, entidad) == ("ACTIVA", None, None)

    # ACTIVA con saldo desconocido: saldo indeterminado, indicador false.
    pos = _posicion_de_reparto(cli, hecho, tercero=tania)
    assert pos == {"entidad_id": str(entidad), "tipo": "DERECHO_COBRO", "saldo": None,
                   "estado": "ACTIVA", "apertura_indeterminada": False}, pos
    p = m.pendiente(cli, tania).json()
    assert [(x["saldo"], x["estado"], x["apertura_indeterminada"]) for x in p["posiciones"]] == [
        (None, "ACTIVA", False)], p
    assert p["neto_estado"] == "INDETERMINADO" and p["neto"] is None

    intencion = uuid.uuid4()
    if accion == "cobro":
        _, r = m.cobro(cli, entidad, cta, "15.00", intencion_id=intencion)
    else:
        c = {"intencion_id": str(intencion), "importe": "15.00", "fecha": "2026-10-10"}
        r = cli.post(f"/v1/posiciones/{entidad}/perdon", json=c, headers=h.AUTH)
    assert r.status_code == 200, r.text
    # Con saldo desconocido el adaptador no cierra: sigue ACTIVA e indeterminada.
    assert _terna(r.json()) == (None, "ACTIVA", False) and r.json()["idempotente"] is False, r.json()
    assert _terna(_posicion_de_reparto(cli, hecho, tercero=tania)) == (None, "ACTIVA", False)

    # Cierre declarativo del motor (F04-D055 A3), con el motivo de las causas (R-Q1).
    cerrada = _cerrar(owner, entidad, motivo)
    assert (cerrada.estado, cerrada.apertura_indeterminada) == ("CERRADA", True)

    # CERRADA con apertura desconocida: saldo 0, indicador true; la apertura sigue desconocida.
    assert _posicion_de_reparto(cli, hecho, tercero=tania) == {
        "entidad_id": str(entidad), "tipo": "DERECHO_COBRO", "saldo": "0.00",
        "estado": "CERRADA", "apertura_indeterminada": True}
    if accion == "cobro":
        _, r = m.cobro(cli, entidad, cta, "15.00", intencion_id=intencion)
    else:
        r = cli.post(f"/v1/posiciones/{entidad}/perdon", json=c, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert _terna(r.json()) == ("0.00", "CERRADA", True) and r.json()["idempotente"] is True, r.json()
    assert _fila(owner, entidad) == ("CERRADA", None, None)  # la lectura no fabrica apertura
    assert m.pendiente(cli, tania).json()["posiciones"] == []


def test_obligacion_apertura_desconocida_pago_y_cierre_por_http(t):
    owner, _, cli, cta, _, _, _ = t
    hecho = _peluqueria_desconocida(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    assert _posicion_de_reparto(cli, hecho) == {"entidad_id": str(entidad), "tipo": "OBLIGACION_PAGO",
                                                "saldo": None, "estado": "ACTIVA", "apertura_indeterminada": False}
    intencion = uuid.uuid4()
    _, r = m.cobro(cli, entidad, cta, "15.00", accion="pago", intencion_id=intencion)
    assert r.status_code == 200, r.text
    assert _terna(r.json()) == (None, "ACTIVA", False), r.json()
    _cerrar(owner, entidad, "LIQUIDADA")
    assert _terna(_posicion_de_reparto(cli, hecho)) == ("0.00", "CERRADA", True)
    _, r = m.cobro(cli, entidad, cta, "15.00", accion="pago", intencion_id=intencion)
    assert r.status_code == 200, r.text
    assert _terna(r.json()) == ("0.00", "CERRADA", True) and r.json()["idempotente"] is True, r.json()
    assert _fila(owner, entidad) == ("CERRADA", None, None)


def test_cerrada_no_admite_operacion_nueva_ni_cambia_el_indicador(t):
    """Una CERRADA desconocida rechaza una intencion NUEVA sin escribir; el indicador no cambia."""
    owner, _, cli, cta, _, tania, _ = t
    hecho = _cena_desconocida(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    _, r = m.cobro(cli, entidad, cta, "5.00")
    assert r.status_code == 200, r.text
    _cerrar(owner, entidad, "LIQUIDADA")
    antes = m.huella(owner)
    _, r = m.cobro(cli, entidad, cta, "1.00")
    assert (r.status_code, r.json().get("codigo")) == (409, "POSICION_CERRADA"), r.text
    assert m.huella(owner) == antes
    assert _terna(_posicion_de_reparto(cli, hecho, tercero=tania)) == ("0.00", "CERRADA", True)


# ------------------------------------------------------------------ aislamiento por owner
def test_aislamiento_por_owner(t):
    owner, _, cli, cta, _, tania, _ = t
    hecho = _cena_desconocida(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    _, r = m.cobro(cli, entidad, cta, "5.00")
    assert r.status_code == 200, r.text
    _cerrar(owner, entidad, "LIQUIDADA")

    otro, _, otro_cli, otra_cta, _ = m.entorno()
    antes_otro, antes = m.huella(otro), m.huella(owner)
    assert otro_cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH).status_code == 404
    # El adaptador la rechaza como no encontrada antes del motor (y el motor, por RLS, tampoco la ve).
    _, r = m.cobro(otro_cli, entidad, otra_cta, "1.00")
    assert (r.status_code, r.json().get("codigo")) == (404, "POSICION_NO_ENCONTRADA"), r.text
    r = otro_cli.post(f"/v1/posiciones/{entidad}/perdon",
                      json={"intencion_id": str(uuid.uuid4()), "importe": "1.00", "fecha": "2026-10-10"},
                      headers=h.AUTH)
    assert (r.status_code, r.json().get("codigo")) == (404, "POSICION_NO_ENCONTRADA"), r.text
    assert m.huella(otro) == antes_otro and m.huella(owner) == antes
    # El motor tampoco la lee bajo el otro owner (RLS).
    with pytest.raises(ErrorMotor) as e:
        PosicionesService(fh.unidad()).saldo(_ctx(otro), entidad)
    assert e.value.codigo == CodigoError.AGREGADO_NO_ENCONTRADO
    # Y el owner sigue leyendo su CERRADA desconocida intacta.
    assert _terna(_posicion_de_reparto(cli, hecho, tercero=tania)) == ("0.00", "CERRADA", True)
    # Las posiciones propias del otro owner llevan su propio estado (apertura conocida).
    o_tania, o_carlos = m.persona(otro_cli, "Tania"), m.persona(otro_cli, "Carlos")
    c, r = m.cena(otro_cli, otra_cta, o_tania, o_carlos)
    assert r.status_code == 200, r.text
    assert _terna(_posicion_de_reparto(otro_cli, uuid.UUID(c["intencion_id"]), tercero=o_tania)) == (
        "15.00", "ACTIVA", False)
