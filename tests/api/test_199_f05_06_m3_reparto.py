# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_199_f05_06_m3_reparto.py
# Ruta: tests/api/test_199_f05_06_m3_reparto.py
# Descripcion: F05-06 M3 §A6 (F05 §51.4 M3; §57 F05-D043; lamina REP v0.2).
#   Discriminantes del reparto, pagador real y posiciones por la API, con el
#   rol real gapto_runtime (adaptador) y oraculo fisico:
#     - GD-3 (peluqueria + cena) completo: hechos, efectos, atribuciones,
#       participantes, aportaciones, movimientos, posiciones y neto 0
#       informativo que NO extingue nada (OP-20);
#     - OP-22 de UNA sola llamada (un solo hecho por intencion, idempotente);
#     - participacion, pagador esperado y pagador real distinguidos;
#     - INV-04: ninguna posicion sin «SI» (NO / NO_LO_SE / invitado);
#     - G3: lo no indicado queda PARCIAL; nunca a cero ni completo solo;
#     - writer de actor: PERSONA, habilitado, del owner; sin actores de
#       empresas; idempotente; ids ajenos sin efectos;
#     - cobro OP-14 / pago OP-12B con cuenta Gapto y capacidad; perdon;
#       «Pendiente con» con «Sin determinar» y neto informativo;
#     - «Corregir reparto»: whitelist y matriz (a)/(b)/(c) de M3-PRE2 P3, con
#       el rechazo exacto de cada caso (b) y REPARTO_CAMBIA_POSICIONES;
#     - elegibilidad de anulacion (lectura, sin locks).
# Version: 0.1.0 (F05-06 M3 §A6)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

import f05_06_m3_helpers as m
import vs01_api_helpers as h

D = decimal.Decimal


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    tania, carlos = m.persona(cli, "Tania"), m.persona(cli, "Carlos")
    return owner, actor, cli, cta, ahorro, tania, carlos


def _cod(r):
    return r.json().get("codigo")


# ------------------------------------------------------------------ GD-3 · peluqueria + cena
def test_gd3_peluqueria_y_cena_oraculo_fisico_completo(t):
    owner, yo, cli, cta, _, tania, carlos = t
    lola = m.empresa(cli, "Peluquería Lola")
    c_pelu, r = m.peluqueria(cli, tania, tercero_id=lola)
    assert r.status_code == 200, r.text
    assert r.json()["posiciones"][0]["tipo"] == "OBLIGACION_PAGO" and r.json()["movimiento"] is None
    pelu = uuid.UUID(c_pelu["intencion_id"])
    c_cena, r = m.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    cena = uuid.UUID(c_cena["intencion_id"])
    a_tania, a_carlos = m.actor_de(owner, tania), m.actor_de(owner, carlos)

    # Peluqueria: gasto mio 15 COMPLETA; pago Tania (aportacion sin caja); deuda 15.
    assert m.efectos(owner, pelu) == {"GASTO": D("15.0000"), "DEUDA": D("15.0000")}
    assert m.atribuciones(owner, pelu) == {yo: D("15.0000")}
    assert m.leer(owner, "SELECT actor_id, importe, hecho_movimiento_tesoreria_id IS NULL "
                         "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", (pelu,)) == [(a_tania, D("15.0000"), True)]
    assert m.uno(owner, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s", (pelu,))[0] == 0
    assert m.posiciones(owner, pelu) == [("OBLIGACION_PAGO", a_tania, D("15.0000"))]
    # Cena: 100 % conservado; movimiento real -44,50; tu parte 14,50; derecho solo de Tania.
    assert m.efectos(owner, cena) == {"GASTO": D("44.5000"), "DERECHO_COBRO": D("15.0000")}
    assert m.atribuciones(owner, cena) == {yo: D("14.5000"), a_tania: D("15.0000"), a_carlos: D("15.0000")}
    assert m.uno(owner, "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE hecho_id = %s "
                        "AND tipo_efecto = 'GASTO'", (cena,))[0] == "COMPLETA"
    assert m.uno(owner, "SELECT sum(m.importe) FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c "
                        "ON c.movimiento_tesoreria_id = m.id WHERE c.hecho_id = %s", (cena,))[0] == D("-44.5000")
    assert m.leer(owner, "SELECT actor_id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
                  (cena,)) == [(yo, D("44.5000"))]
    assert m.posiciones(owner, cena) == [("DERECHO_COBRO", a_tania, D("15.0000"))]
    assert sorted(m.leer(owner, "SELECT actor_id FROM gapto.hecho_participantes WHERE hecho_id = %s", (cena,)),
                  key=str) == sorted([(yo,), (a_tania,), (a_carlos,)], key=str)
    assert m.uno(owner, "SELECT numero_participantes_total FROM gapto.hechos_financieros WHERE id = %s", (cena,))[0] == 3
    # Pendiente con Tania: te debe 15, le debes 15, neto 0 informativo que no salda.
    antes = m.huella(owner)
    r = m.pendiente(cli, tania)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["te_debe"], p["le_debes"], p["neto"], p["neto_estado"]) == ("15.00", "15.00", "0.00", "DETERMINADO")
    assert {x["tipo"]: x["origen_hecho_id"] for x in p["posiciones"]} == {
        "DERECHO_COBRO": str(cena), "OBLIGACION_PAGO": str(pelu)}
    assert all(x["estado"] == "ACTIVA" for x in p["posiciones"])
    # Origen de cada posicion (C1): la nota del gasto y su comercio.
    assert {x["tipo"]: (x["origen_concepto"], x["origen_tercero"]) for x in p["posiciones"]} == {
        "DERECHO_COBRO": ("Cena con amigos", None), "OBLIGACION_PAGO": ("Peluquería", "Peluquería Lola")}
    assert m.huella(owner) == antes  # leer no escribe ni extingue nada
    # Carlos invitado: sin posiciones.
    assert m.pendiente(cli, carlos).json()["neto_estado"] == "SIN_POSICIONES"


def test_op22_una_sola_llamada_un_hecho_e_idempotente(t):
    owner, _, cli, cta, _, tania, carlos = t
    c, r = m.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    antes = m.huella(owner)
    r2 = m.registrar(cli, c)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True, r2.text
    assert m.huella(owner) == antes
    otro = dict(c, importe="45.00")
    r3 = m.registrar(cli, otro)
    assert (r3.status_code, _cod(r3)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    assert m.huella(owner) == antes


def test_participacion_pagador_esperado_y_real_distinguidos(t):
    """Tania participa y paga (aportacion), yo soporto mi parte; nadie debe nada sin «SI»."""
    owner, yo, cli, _, _, tania, carlos = t
    c = m.cuerpo("30.00", pagado_por=m.por_persona(tania, "NO"),
                 reparto=m.repartir("15.00", (tania, "15.00", None)))
    r = m.registrar(cli, c)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    a_tania = m.actor_de(owner, tania)
    assert m.atribuciones(owner, hecho) == {yo: D("15.0000"), a_tania: D("15.0000")}
    assert m.leer(owner, "SELECT actor_id FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", (hecho,)) == [(a_tania,)]
    assert m.posiciones(owner, hecho) == []
    assert r.json()["movimiento"] is None


# ------------------------------------------------------------------ INV-04 y G3
@pytest.mark.parametrize("le_debo", ["NO", "NO_LO_SE"])
def test_inv04_sin_si_no_hay_deuda(t, le_debo):
    owner, _, cli, _, _, tania, _ = t
    c, r = m.peluqueria(cli, tania, le_debo=le_debo)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(c["intencion_id"])
    assert m.posiciones(owner, hecho) == [] and r.json()["posiciones"] == []
    assert m.efectos(owner, hecho) == {"GASTO": D("15.0000")}


def test_inv04_invitado_y_pago_de_mas_no_crean_derecho(t):
    owner, _, cli, cta, _, tania, carlos = t
    c, r = m.cena(cli, cta, tania, carlos, tania_debe="NO")
    assert r.status_code == 200, r.text
    assert m.posiciones(owner, uuid.UUID(c["intencion_id"])) == []


def test_g3_parte_sin_indicar_queda_parcial(t):
    owner, yo, cli, cta, _, tania, carlos = t
    c = m.cuerpo("44.50", pagado_por=m.con_cuenta(cta),
                 reparto=m.repartir("14.50", (tania, "15.00", "SI"), (carlos, None, None)))
    r = m.registrar(cli, c)
    assert r.status_code == 200 and r.json()["estado_atribucion"] == "PARCIAL", r.text
    hecho = uuid.UUID(c["intencion_id"])
    assert m.atribuciones(owner, hecho) == {yo: D("14.5000"), m.actor_de(owner, tania): D("15.0000")}
    # Nunca 15 por resta para Carlos, ni cero.
    assert m.uno(owner, "SELECT count(*) FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e "
                        "ON e.id = a.efecto_id WHERE e.hecho_id = %s AND a.actor_id = %s",
                 (hecho, m.actor_de(owner, carlos)))[0] == 0


def test_g3_sin_ninguna_parte_es_no_disponible(t):
    owner, _, cli, cta, _, tania, carlos = t
    c = m.cuerpo("44.50", pagado_por=m.con_cuenta(cta), reparto=m.repartir(None, (tania, None, None)))
    r = m.registrar(cli, c)
    assert r.status_code == 200 and r.json()["estado_atribucion"] == "NO_DISPONIBLE", r.text


@pytest.mark.parametrize("cuerpo_mal", [
    lambda tania, carlos, cta: m.cuerpo("10.00", pagado_por=m.con_cuenta(cta),
                                        reparto=m.repartir("5.00", (tania, "6.00", None))),  # supera el total
    lambda tania, carlos, cta: m.cuerpo("10.00", pagado_por=m.con_cuenta(cta),
                                        reparto=m.repartir("5.00", (tania, None, "SI"))),  # derecho sin importe
    lambda tania, carlos, cta: m.cuerpo("10.00", pagado_por=m.por_persona(tania, "SI"),
                                        reparto=m.repartir(None, (carlos, "5.00", None))),  # deuda sin mi parte
    lambda tania, carlos, cta: m.cuerpo("10.00", pagado_por=m.por_persona(tania, "NO"),
                                        reparto=m.repartir("5.00", (carlos, "5.00", "SI"))),  # derecho sin pagar yo
    lambda tania, carlos, cta: m.cuerpo("10.00", pagado_por=m.con_cuenta(cta),
                                        reparto=m.repartir("5.00", (tania, "2.00", None), (tania, "3.00", None))),
])
def test_estructura_invalida_422_sin_efectos(t, cuerpo_mal):
    owner, _, cli, cta, _, tania, carlos = t
    antes = m.huella(owner)
    r = m.registrar(cli, cuerpo_mal(tania, carlos, cta))
    assert r.status_code == 422, r.text
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ writer de actor (AJ-M3-DEC-06/07)
def test_writer_actor_idempotente_y_auditado(t):
    owner, _, cli, cta, _, tania, carlos = t
    assert m.actor_de(owner, tania) is None
    m.cena(cli, cta, tania, carlos)
    actor = m.actor_de(owner, tania)
    assert actor is not None
    _, r = m.peluqueria(cli, tania)
    assert r.status_code == 200, r.text  # la segunda alta del mismo tercero reutiliza el actor
    assert m.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (tania,))[0] == 1
    assert m.actor_de(owner, tania) == actor
    assert m.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'actores_financieros' "
                        "AND registro_id = %s AND accion = 'CREAR' AND request_id IS NOT NULL", (actor,))[0] == 1
    # Sin tocar titularidades ni participaciones.
    assert m.uno(owner, "SELECT count(*) FROM gapto.cuenta_participaciones WHERE actor_id = %s", (actor,))[0] == 0
    assert m.uno(owner, "SELECT count(*) FROM gapto.entidad_participaciones WHERE actor_id = %s", (actor,))[0] == 0


@pytest.mark.parametrize("caso", ["empresa", "deshabilitado", "otro_owner", "inexistente"])
def test_writer_actor_rechaza_sin_efectos(t, caso):
    owner, _, cli, cta, _, tania, _ = t
    if caso == "empresa":
        quien, codigo = m.empresa(cli, "Talleres SL"), "TERCERO_NO_PERSONA"
    elif caso == "deshabilitado":
        quien, codigo = m.persona(cli, "Simón"), "TERCERO_NO_DISPONIBLE"
        h.como_owner(owner, "UPDATE gapto.terceros SET enabled = false WHERE id = %s", (quien,))
    elif caso == "otro_owner":
        _, _, otro_cli, _, _ = m.entorno()
        quien, codigo = m.persona(otro_cli, "Ajena"), "TERCERO_NO_DISPONIBLE"
    else:
        quien, codigo = uuid.uuid4(), "TERCERO_NO_DISPONIBLE"
    antes = m.huella(owner)
    c = m.cuerpo("30.00", pagado_por=m.con_cuenta(cta), reparto=m.repartir("15.00", (quien, "15.00", "SI")))
    r = m.registrar(cli, c)
    assert (r.status_code, _cod(r)) == (409, codigo), r.text
    assert m.huella(owner) == antes


def test_comercio_ajeno_rechazado_sin_efectos(t):
    owner, _, cli, cta, _, tania, carlos = t
    _, _, otro_cli, _, _ = m.entorno()
    ajeno = m.empresa(otro_cli, "Ajena SL")
    antes = m.huella(owner)
    c = m.cuerpo("10.00", pagado_por=m.con_cuenta(cta), reparto=m.SOLO_MIO, tercero_id=ajeno)
    r = m.registrar(cli, c)
    assert (r.status_code, _cod(r)) == (409, "TERCERO_NO_DISPONIBLE"), r.text
    assert m.huella(owner) == antes


def test_cuenta_sin_capacidad_rechaza_sin_efectos(t):
    owner, actor, cli, _, _, tania, carlos = t
    sin = h.crear_cuenta(owner, [(actor, 100)], capacidades=("RECIBIR_INGRESO",))
    antes = m.huella(owner)
    c, r = m.cena(cli, sin, tania, carlos)
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD"), r.text
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ cobro, pago, perdon y «Pendiente con»
def test_cobro_parcial_total_y_exceso(t):
    owner, _, cli, cta, _, tania, carlos = t
    c, _ = m.cena(cli, cta, tania, carlos)
    entidad = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    _, r = m.cobro(cli, entidad, cta, "5.00")
    assert r.status_code == 200 and (r.json()["saldo"], r.json()["estado"]) == ("10.00", "ACTIVA"), r.text
    _, r = m.cobro(cli, entidad, cta, "11.00")
    assert (r.status_code, _cod(r)) == (409, "EXCEDE_SALDO_DEL_DERECHO"), r.text
    cuerpo, r = m.cobro(cli, entidad, cta, "10.00")
    assert r.status_code == 200 and (r.json()["saldo"], r.json()["estado"]) == ("0.00", "CERRADA"), r.text
    hecho_cobro = uuid.UUID(r.json()["hecho_id"])
    # Es un REEMBOLSO con su movimiento de entrada, nunca un INGRESO; relacion con la cena.
    assert m.efectos(owner, hecho_cobro) == {"DERECHO_COBRO": D("-10.0000")}
    assert m.uno(owner, "SELECT count(*) FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s "
                        "AND hecho_destino_id = %s AND tipo_relacion = 'REEMBOLSO_DE'",
                 (hecho_cobro, uuid.UUID(c["intencion_id"])))[0] == 1
    # Repetir la misma intencion es idempotente.
    r2 = cli.post(f"/v1/posiciones/{entidad}/cobro", json=cuerpo, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True, r2.text
    # Saldada: deja de estar pendiente (las posiciones cerradas no entran en OP-20).
    assert m.pendiente(cli, tania).json()["neto_estado"] == "SIN_POSICIONES"


def test_pago_de_la_deuda_y_operacion_cruzada(t):
    owner, _, cli, cta, _, tania, _ = t
    c, _ = m.peluqueria(cli, tania)
    entidad = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    _, r = m.cobro(cli, entidad, cta, "5.00")  # cobrar una obligacion no procede
    assert (r.status_code, _cod(r)) == (409, "POSICION_NO_ADMITE_OPERACION"), r.text
    _, r = m.cobro(cli, entidad, cta, "15.00", accion="pago")
    assert r.status_code == 200 and r.json()["estado"] == "CERRADA", r.text
    assert m.uno(owner, "SELECT m.importe FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c "
                        "ON c.movimiento_tesoreria_id = m.id WHERE c.hecho_id = %s",
                 (uuid.UUID(r.json()["hecho_id"]),))[0] == D("-15.0000")


def test_cobro_sin_capacidad_y_posicion_ajena(t):
    owner, actor, cli, cta, _, tania, carlos = t
    c, _ = m.cena(cli, cta, tania, carlos)
    entidad = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    solo_pagar = h.crear_cuenta(owner, [(actor, 100)], capacidades=("PAGAR_GASTO",))
    antes = m.huella(owner)
    _, r = m.cobro(cli, entidad, solo_pagar, "5.00")
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD"), r.text
    assert m.huella(owner) == antes
    _, _, otro_cli, otra_cta, _ = m.entorno()
    _, r = m.cobro(otro_cli, entidad, otra_cta, "5.00")
    assert (r.status_code, _cod(r)) == (404, "POSICION_NO_ENCONTRADA"), r.text
    assert m.huella(owner) == antes


def test_perdon_no_mueve_dinero(t):
    owner, _, cli, cta, _, tania, carlos = t
    c, _ = m.cena(cli, cta, tania, carlos)
    entidad = m.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    movs = m.uno(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria")[0]
    _, r = m.perdon(cli, entidad, "15.00")
    assert r.status_code == 200 and r.json()["estado"] == "CERRADA", r.text
    assert m.uno(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria")[0] == movs
    hecho = uuid.UUID(r.json()["hecho_id"])
    assert m.uno(owner, "SELECT t.codigo FROM gapto.hechos_financieros f JOIN gapto.tipos_hecho t "
                        "ON t.id = f.tipo_hecho_id WHERE f.id = %s", (hecho,))[0] == "CONDONACION"


def test_pendiente_con_saldo_desconocido_es_sin_determinar(t):
    """C4 / D-REP-09: una posicion con apertura indeterminada -> neto «Sin determinar», nunca 0."""
    owner, _, cli, cta, _, tania, carlos = t
    m.cena(cli, cta, carlos, tania, tania_debe="SI")  # la primera persona (Carlos) me debe 15
    import f05_01_helpers as fh
    from app.core.contexto import ContextoOperacion
    from app.core.modelos_posicion import DatosAltaPosicion
    from app.services.posiciones_service import PosicionesService

    PosicionesService(fh.unidad()).crear_posicion(
        ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()),
        DatosAltaPosicion(entidad_id=uuid.uuid4(), nombre="Préstamo viaje", tipo="OBLIGACION_PAGO",
                          contraparte_actor_id=m.actor_de(owner, carlos), moneda="EUR",
                          justificacion="DECISION_EXPLICITA", fecha_inicio_seguimiento=None, saldo_apertura=None,
                          hecho_id=uuid.uuid4(), fecha_hecho=__import__("datetime").date(2026, 9, 1),
                          concepto="Préstamo viaje"))
    p = m.pendiente(cli, carlos).json()
    assert (p["te_debe"], p["le_debes"], p["neto"], p["neto_estado"]) == ("15.00", None, None, "INDETERMINADO"), p


def test_pendiente_tercero_ajeno_404(t):
    _, _, cli, _, _, _, _ = t
    _, _, otro_cli, _, _ = m.entorno()
    r = m.pendiente(cli, m.persona(otro_cli, "Ajena"))
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ «Corregir reparto» · matriz (a)/(b)/(c)
def _cena_con_ids(t):
    owner, yo, cli, cta, _, tania, carlos = t
    c, _ = m.cena(cli, cta, tania, carlos)
    hecho = uuid.UUID(c["intencion_id"])
    ids = {q: m.atribucion_de(owner, hecho, a) for q, a in
           (("yo", yo), ("tania", m.actor_de(owner, tania)), ("carlos", m.actor_de(owner, carlos)))}
    return hecho, ids


def test_a_cambiar_importes_actualiza_el_derecho_coherente(t):
    owner, yo, cli, *_ = t
    tania = t[5]
    hecho, ids = _cena_con_ids(t)
    r = m.corregir(cli, hecho, m.version(owner, hecho), {ids["yo"]: "9.50", ids["tania"]: "20.00"})
    assert r.status_code == 200, r.text
    assert r.json()["tu_parte"] == "9.50" and r.json()["posiciones"][0]["importe"] == "20.00"
    assert r.json()["posiciones"][0]["tercero_id"] == str(tania)  # el wire habla de terceros, no de actores
    assert m.efectos(owner, hecho)["DERECHO_COBRO"] == D("20.0000")
    assert m.atribuciones(owner, hecho)[yo] == D("9.5000")
    # Importe total, pagador y aportaciones intactos.
    assert m.efectos(owner, hecho)["GASTO"] == D("44.5000")
    assert m.leer(owner, "SELECT actor_id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
                  (hecho,)) == [(yo, D("44.5000"))]


def test_a_invitado_sin_posicion_cambia_su_importe(t):
    owner, _, cli, *_ = t
    hecho, ids = _cena_con_ids(t)
    r = m.corregir(cli, hecho, m.version(owner, hecho), {ids["yo"]: "16.50", ids["carlos"]: "13.00"})
    assert r.status_code == 200 and r.json()["posiciones"] == [], r.text
    assert m.efectos(owner, hecho)["DERECHO_COBRO"] == D("15.0000")


def test_a_no_baja_por_debajo_de_lo_cobrado(t):
    owner, _, cli, cta, *_ = t
    hecho, ids = _cena_con_ids(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    m.cobro(cli, entidad, cta, "12.00")
    antes = m.huella(owner)
    r = m.corregir(cli, hecho, m.version(owner, hecho), {ids["yo"]: "18.50", ids["tania"]: "11.00"})
    assert (r.status_code, _cod(r)) == (409, "INTEGRIDAD_POSICION_VIOLADA"), r.text
    assert m.huella(owner) == antes


@pytest.mark.parametrize("partes, codigo", [
    (lambda ids: {ids["yo"]: "10.00"}, "REPARTO_NO_CORREGIBLE"),  # COMPLETA deja de sumar el total
    (lambda ids: {uuid.uuid4(): "1.00"}, "REPARTO_NO_CORREGIBLE"),  # parte que no es de este gasto
])
def test_whitelist_rechaza_sin_efectos(t, partes, codigo):
    owner, _, cli, *_ = t
    hecho, ids = _cena_con_ids(t)
    antes = m.huella(owner)
    r = m.corregir(cli, hecho, m.version(owner, hecho), partes(ids))
    assert (r.status_code, _cod(r)) == (409, codigo), r.text
    assert m.huella(owner) == antes


def test_whitelist_campos_fuera_de_contrato_422(t):
    owner, _, cli, *_ = t
    hecho, ids = _cena_con_ids(t)
    v = m.version(owner, hecho)
    for cuerpo in (
        {"row_version": v, "motivo": "x", "partes": [{"atribucion_id": str(ids["yo"]), "importe": "0"}]},
        {"row_version": v, "motivo": "x", "partes": [{"atribucion_id": str(ids["yo"]), "importe": "1", "actor_id": "x"}]},
        {"row_version": v, "motivo": "x", "partes": [], "efectos": []},
        {"row_version": v, "motivo": " ", "partes": [{"atribucion_id": str(ids["yo"]), "importe": "1"}]},
    ):
        r = cli.post(f"/v1/hechos/{hecho}/reparto", json=cuerpo, headers=h.AUTH)
        assert r.status_code == 422, (cuerpo, r.text)


def test_version_desfasada_no_pisa(t):
    owner, yo, cli, *_ = t
    hecho, ids = _cena_con_ids(t)
    v = m.version(owner, hecho)
    assert m.corregir(cli, hecho, v, {ids["yo"]: "16.50", ids["carlos"]: "13.00"}).status_code == 200
    r = m.corregir(cli, hecho, v, {ids["yo"]: "14.50", ids["carlos"]: "15.00"})
    assert (r.status_code, _cod(r)) == (409, "VERSION_DESFASADA"), r.text
    assert m.atribuciones(owner, hecho)[yo] == D("16.5000")


def _motor_corregir(owner, datos):
    import f05_01_helpers as fh
    from app.core.contexto import ContextoOperacion
    from app.services.correcciones_service import CorreccionesService

    return CorreccionesService(fh.unidad()).corregir(ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()), datos)


def _b_casos(owner, cli, hecho, ids, actor_simon, entidad_otra):
    from app.core.modelos_compuesto import DatosEntidadHecho
    from app.core.modelos_efectos import DatosEfecto
    from app.services.correcciones_service import DatosAtribucionNueva

    efecto_gasto = m.uno(owner, "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s AND tipo_efecto = 'GASTO'",
                         (hecho,))[0]
    efecto_derecho = m.uno(owner, "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s "
                                  "AND tipo_efecto = 'DERECHO_COBRO'", (hecho,))[0]
    return {
        "RETIRA_EFECTO_DE_POSICION": {"efectos_a_eliminar": (efecto_derecho,)},
        "CREA_EFECTO_DE_POSICION": {"efectos_a_crear": (DatosEfecto(
            efecto_id=uuid.uuid4(), tipo_efecto="DERECHO_COBRO", importe_delta=D("15"),
            estado_atribucion="NO_DISPONIBLE"),)},
        "CAMBIA_NATURALEZA_DE_POSICION": {"efectos_a_actualizar": {efecto_gasto: {"tipo_efecto": "DEUDA"}}},
        "ALTA_O_BAJA_DE_PARTICIPANTE:baja": {"atribuciones_a_eliminar": (ids["tania"],)},
        "ALTA_O_BAJA_DE_PARTICIPANTE:alta": {"atribuciones_a_crear": (DatosAtribucionNueva(
            atribucion_id=uuid.uuid4(), efecto_id=efecto_gasto, actor_id=actor_simon,
            importe_atribuido=D("1"), criterio_atribucion="MANUAL"),)},
        # OP-21 solo admite un alta contextual como reemplazo de una baja: se
        # retira un vinculo RELACIONADO_CON (sin posicion) y se pretende vincular
        # una posicion en su lugar.
        "VINCULA_POSICION": {"entidades_a_eliminar": (_vinculo_contexto(owner, cli, hecho),),
                             "entidades_a_crear": (DatosEntidadHecho(
                                 registro_id=uuid.uuid4(), entidad_id=entidad_otra, tipo_relacion="AFECTA_A",
                                 principal=False),)},
    }


def _vinculo_contexto(owner, cli, hecho) -> uuid.UUID:
    """Vinculo RELACIONADO_CON del hecho con una entidad CONTEXTO (sin posicion)."""
    import f05_05_helpers as x

    entidad, vinculo = x.contexto(cli, "Viaje"), uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, "
                        "principal, owner_user_id) VALUES (%s, %s, NULL, %s, 'RELACIONADO_CON', false, %s)",
                 (vinculo, hecho, entidad, owner))
    return vinculo


@pytest.mark.parametrize("caso", ["RETIRA_EFECTO_DE_POSICION", "CREA_EFECTO_DE_POSICION",
                                  "CAMBIA_NATURALEZA_DE_POSICION", "ALTA_O_BAJA_DE_PARTICIPANTE:baja",
                                  "ALTA_O_BAJA_DE_PARTICIPANTE:alta", "VINCULA_POSICION"])
def test_b_guarda_motor_reparto_cambia_posiciones(t, caso):
    """Clase (b) de M3-PRE2 P3 por el motor (OP-21), con su rechazo exacto y sin efectos."""
    from app.core.errores import CodigoError, ErrorMotor
    from app.services.correcciones_service import DatosCorreccion

    owner, _, cli, cta, _, tania, carlos = t
    hecho, ids = _cena_con_ids(t)
    simon = m.persona(cli, "Simón")
    otra, _ = m.cena(cli, cta, simon, carlos)  # crea el actor de Simon y otra posicion
    entidad_otra = m.entidad_de_posicion(owner, uuid.UUID(otra["intencion_id"]))
    cambios = _b_casos(owner, cli, hecho, ids, m.actor_de(owner, simon), entidad_otra)[caso]
    antes = m.huella(owner)
    with pytest.raises(ErrorMotor) as exc:
        _motor_corregir(owner, DatosCorreccion(hecho_id=hecho, row_version_esperada=m.version(owner, hecho),
                                               motivo="prueba", **cambios))
    assert exc.value.codigo is CodigoError.CORRECCION_AGREGADA_REQUERIDA
    assert exc.value.contexto_extra == {"motivo": "REPARTO_CAMBIA_POSICIONES", "detalle": caso.split(":")[0]}
    assert m.huella(owner) == antes


def test_b_retirar_afecta_a_con_efecto_de_posicion_r_m3pre2_02(t):
    """R-M3PRE2-02: un vinculo AFECTA_A con efecto_id (como lo deja V3) no se retira por OP-21."""
    from app.core.errores import CodigoError, ErrorMotor
    from app.services.correcciones_service import DatosCorreccion

    owner, _, cli, *_ = t
    hecho, _ = _cena_con_ids(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    efecto_derecho = m.uno(owner, "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s "
                                  "AND tipo_efecto = 'DERECHO_COBRO'", (hecho,))[0]
    vinculo = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, "
                        "principal, owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', false, %s)",
                 (vinculo, hecho, efecto_derecho, entidad, owner))
    antes = m.huella(owner)
    with pytest.raises(ErrorMotor) as exc:
        _motor_corregir(owner, DatosCorreccion(hecho_id=hecho, row_version_esperada=m.version(owner, hecho),
                                               motivo="prueba", entidades_a_eliminar=(vinculo,)))
    assert exc.value.codigo is CodigoError.CORRECCION_AGREGADA_REQUERIDA
    assert exc.value.contexto_extra["detalle"] == "RETIRA_VINCULO_DE_POSICION"
    assert m.huella(owner) == antes


def test_b_por_la_api_devuelve_el_motivo(t, monkeypatch):
    """La API no puede expresar altas ni bajas (whitelist); si el motor rechaza por (b), el motivo llega a la UI."""
    from app.api import ejecucion_reparto as rep
    from app.core.errores import CodigoError, ErrorMotor

    owner, _, cli, *_ = t
    hecho, ids = _cena_con_ids(t)

    def falla(*a, **k):
        raise ErrorMotor(CodigoError.CORRECCION_AGREGADA_REQUERIDA, "x",
                         contexto_extra={"motivo": "REPARTO_CAMBIA_POSICIONES", "detalle": "X"})
    monkeypatch.setattr(rep, "corregir_reparto", falla)
    r = m.corregir(cli, hecho, 1, {ids["yo"]: "1.00"})
    assert (r.status_code, _cod(r), r.json()["detalle"]) == (
        409, "CORRECCION_AGREGADA_REQUERIDA", {"motivo": "REPARTO_CAMBIA_POSICIONES"})


@pytest.mark.parametrize("caso", ["devolucion", "ingreso", "transferencia", "v3"])
def test_c_fuera_de_m3(t, caso):
    import f05_05_helpers as x
    import f05_06_m2_helpers as m2

    owner, _, cli, cta, ahorro, tania, carlos = t
    if caso == "devolucion":
        origen = m2.compra(cli, cta)
        c, _ = m2.devolver(cli, origen)
        hecho = uuid.UUID(c["intencion_id"])
    elif caso == "ingreso":
        hecho = x.ingreso(cli, cta)
    elif caso == "transferencia":
        hecho = x.transferencia(cli, cta, ahorro)
    else:
        hecho, _ = _cena_con_ids(t)
        m2.marcar_v3(owner, hecho)
    atr = m.uno(owner, "SELECT a.id FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
                       "WHERE e.hecho_id = %s LIMIT 1", (hecho,))
    antes = m.huella(owner)
    r = m.corregir(cli, hecho, m.version(owner, hecho), {(atr[0] if atr else uuid.uuid4()): "1.00"})
    motivo = "ORIGEN_IMPORTADO" if caso == "v3" else "TIPO_NO_ADMITIDO"
    assert (r.status_code, _cod(r), r.json()["detalle"]) == (409, "REPARTO_NO_CORREGIBLE", {"motivo": motivo}), r.text
    assert m.huella(owner) == antes


def test_corregir_hecho_ajeno_404(t):
    owner, _, cli, *_ = t
    hecho, ids = _cena_con_ids(t)
    _, _, otro_cli, _, _ = m.entorno()
    r = m.corregir(otro_cli, hecho, 1, {ids["yo"]: "1.00"})
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ elegibilidad de anulacion (iii)
def test_elegibilidad_anulacion_no_promete(t):
    owner, _, cli, cta, _, tania, carlos = t
    hecho, _ = _cena_con_ids(t)
    antes = m.huella(owner)
    r = cli.get(f"/v1/hechos/{hecho}/anulacion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["elegible"] is False and set(r.json()["motivos"]) == {"TESORERIA", "POSICIONES"}
    assert m.huella(owner) == antes  # la lectura no escribe
    entidad = m.entidad_de_posicion(owner, hecho)
    m.cobro(cli, entidad, cta, "5.00")
    assert "DEPENDENCIAS_ACTIVAS" in cli.get(f"/v1/hechos/{hecho}/anulacion", headers=h.AUTH).json()["motivos"]
    assert cli.get(f"/v1/hechos/{uuid.uuid4()}/anulacion", headers=h.AUTH).status_code == 404


def test_a_coherencia_no_demostrable_se_rechaza(t):
    """AJ-M3-DEC-03: si el efecto de la posicion no es demostrablemente la parte que se
    corrige (derecho 10 frente a una parte de 15), no se corrige: REPARTO_NO_DEMOSTRABLE."""
    import dataclasses

    import f05_01_helpers as fh
    from app.api import ejecucion_reparto as rep
    from app.api.dto_reparto import IntencionGastoCompartido
    from app.core.contexto import ContextoOperacion
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    owner, yo, cli, cta, _, tania, carlos = t
    m.cena(cli, cta, tania, carlos)  # crea los actores
    intencion = IntencionGastoCompartido(**m.cuerpo(
        "44.50", pagado_por=m.con_cuenta(cta), reparto=m.repartir("14.50", (tania, "15.00", "SI"), (carlos, "15.00", "NO"))))
    datos = rep.componer_gasto_compartido(intencion, yo, {tania: m.actor_de(owner, tania),
                                                          carlos: m.actor_de(owner, carlos)})
    datos = dataclasses.replace(datos, posiciones=[dataclasses.replace(datos.posiciones[0], importe_inicial=D("10"))])
    HechosCompuestosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla).registrar_hecho_compuesto(
        ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()), datos)
    hecho = intencion.intencion_id
    antes = m.huella(owner)
    r = m.corregir(cli, hecho, m.version(owner, hecho),
                   {m.atribucion_de(owner, hecho, yo): "15.50", m.atribucion_de(owner, hecho, m.actor_de(owner, tania)): "14.00"})
    assert (r.status_code, _cod(r)) == (409, "REPARTO_NO_DEMOSTRABLE"), r.text
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ lectura del reparto (E6)
def test_lectura_reparto_cena(t):
    owner, yo, cli, cta, _, tania, carlos = t
    hecho, ids = _cena_con_ids(t)
    entidad = m.entidad_de_posicion(owner, hecho)
    _, r = m.cobro(cli, entidad, cta, "5.00")
    assert r.status_code == 200, r.text
    antes = m.huella(owner)
    r = cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert m.huella(owner) == antes  # la lectura no escribe
    assert (d["corregible"], d["motivo"], d["importe"], d["estado_atribucion"], d["row_version"]) == (
        True, None, "44.50", "COMPLETA", m.version(owner, hecho))
    partes = {p["atribucion_id"]: p for p in d["partes"]}
    assert d["partes"][0]["es_yo"] is True and d["partes"][0]["nombre"] == "Tú"
    assert partes[str(ids["yo"])]["importe"] == "14.50" and partes[str(ids["yo"])]["posicion"] is None
    assert partes[str(ids["tania"])]["tercero_id"] == str(tania)
    assert partes[str(ids["tania"])]["posicion"] == {"entidad_id": str(entidad), "tipo": "DERECHO_COBRO", "saldo": "10.00"}
    assert partes[str(ids["carlos"])]["posicion"] is None  # invitado


@pytest.mark.parametrize("caso", ["solo_mio", "v3", "ingreso"])
def test_lectura_reparto_no_corregible(t, caso):
    import f05_05_helpers as x
    import f05_06_m2_helpers as m2

    owner, _, cli, cta, _, tania, _ = t
    if caso == "solo_mio":
        c, _ = m.peluqueria(cli, tania)
        hecho, motivo = uuid.UUID(c["intencion_id"]), "SIN_REPARTO"
    elif caso == "v3":
        hecho, _ = _cena_con_ids(t)
        m2.marcar_v3(owner, hecho)
        motivo = "ORIGEN_IMPORTADO"
    else:
        hecho, motivo = x.ingreso(cli, cta), "TIPO_NO_ADMITIDO"
    r = cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert (r.json()["corregible"], r.json()["motivo"]) == (False, motivo)


def test_lectura_reparto_ajeno_404(t):
    hecho, _ = _cena_con_ids(t)
    _, _, otro_cli, _, _ = m.entorno()
    assert otro_cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH).status_code == 404
