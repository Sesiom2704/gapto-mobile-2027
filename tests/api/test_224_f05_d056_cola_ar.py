# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_224_f05_d056_cola_ar.py
# Ruta: tests/api/test_224_f05_d056_cola_ar.py
# Descripcion: COLA-AR v1.0 (F05 §70.A.6 pruebas 8, 10 y 12; AJ-F0507G7-05):
#   integracion de API con ORACULO FISICO (base desechable) de lo que hace la
#   cola de la app con la MISMA identidad. Ninguna ruta del servidor cambia.
#     - Respuesta perdida tras una escritura confirmada: el reenvio con el mismo
#       intencion_id es 200 idempotente y en la base hay un solo hecho, un solo
#       movimiento y una sola reduccion de la posicion (cobro y pago, F1), un
#       solo gasto (F3, «Repetir hoy»; F4, gasto con bloque prevision).
#     - Dos envios concurrentes de la misma intencion: [200, 200], idempotente
#       [False, True] y una sola realidad.
#     - «No hubo» (F5; decision 1 de Moises del 2026-10-29): el reenvio de la
#       misma intencion tras un COMMIT es 409 sin escritura ni segundo sucesor,
#       y la LECTURA de la prevision (GET /v1/previsiones/{id}) que hace la cola
#       dice OMITIDA -> CONFIRMADA; si la prevision quedo en otro estado, la
#       lectura lo dice (-> RECHAZADA). Concurrencia: un 200 y un 409, y la
#       lectura posterior ve el resultado definitivo (omitir -> _terminar ->
#       _tocar -> tocar_prevision: UPDATE condicionado por row_version con
#       bloqueo de fila; el perdedor espera y recibe 409 sin escribir).
#     - La comprobacion de conexion previa al envio (GET /v1/yo) no escribe.
#   La abono (F2) tiene su replay fisico en test_198::test_8.
# Version: 0.1.0 (F05-D056 paso 2)
# Version: 0.1.1 (pre-S2, AJ-F0507G8-16): solo comentario; recorrido real del servidor
#   (_tocar/tocar_prevision, no bloquear_prevision).
# ============================================================
from __future__ import annotations

import threading
import uuid

import pytest

import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m5
import vs01_api_helpers as h


def _posicion_tania():
    owner, actor, cli, cta, ahorro = m3.entorno()
    tania, carlos = m3.persona(cli, "Tania"), m3.persona(cli, "Carlos")
    c, r = m3.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    return owner, cli, cta, m3.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))


# ------------------------------------------------------------------ F1: cobro y pago con respuesta perdida
@pytest.mark.parametrize("accion", ["cobro", "pago"])
def test_respuesta_perdida_reenvio_misma_identidad_una_sola_reduccion(accion):
    if accion == "cobro":
        owner, cli, cta, entidad = _posicion_tania()
        importe = "15.00"
    else:
        owner, actor, cli, cta, ahorro = m3.entorno()
        tania = m3.persona(cli, "Tania")
        c, r = m3.peluqueria(cli, tania)
        assert r.status_code == 200, r.text
        entidad = m3.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
        importe = "15.00"
    cuerpo, r1 = m3.cobro(cli, entidad, cta, importe, accion=accion)  # la respuesta «se pierde»: el cliente no la ve
    assert r1.status_code == 200 and r1.json()["idempotente"] is False, r1.text
    despues_primero = m3.huella(owner)
    r2 = cli.post(f"/v1/posiciones/{entidad}/{accion}", json=cuerpo, headers=h.AUTH)  # reconciliacion: misma identidad
    assert r2.status_code == 200 and r2.json()["idempotente"] is True, r2.text
    assert r2.json()["hecho_id"] == r1.json()["hecho_id"] and r2.json()["saldo"] == r1.json()["saldo"] == "0.00"
    # Oraculo fisico: nada nuevo tras el reenvio; una sola reduccion del saldo.
    assert m3.huella(owner) == despues_primero
    hecho = uuid.UUID(r1.json()["hecho_id"])
    assert m3.uno(owner, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s", (hecho,))[0] == 1


def test_reenvio_concurrente_de_la_misma_intencion_de_cobro():
    owner, cli, cta, entidad = _posicion_tania()
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "15.00", "cuenta_id": str(cta), "fecha": "2026-10-10"}
    antes = m3.huella(owner)
    clientes = [h.cliente(owner, reloj=m5.x.reloj()) for _ in range(2)]
    barrera, resp = threading.Barrier(2), []

    def enviar(k):
        barrera.wait()
        resp.append(clientes[k].post(f"/v1/posiciones/{entidad}/cobro", json=cuerpo, headers=h.AUTH))

    hilos = [threading.Thread(target=enviar, args=(k,)) for k in range(2)]
    [x.start() for x in hilos]
    [x.join() for x in hilos]
    assert sorted(r.status_code for r in resp) == [200, 200], [r.text for r in resp]
    assert sorted(r.json()["idempotente"] for r in resp) == [False, True]
    assert len({r.json()["hecho_id"] for r in resp}) == 1
    hecho = uuid.UUID(resp[0].json()["hecho_id"])
    assert m3.uno(owner, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s", (hecho,))[0] == 1
    assert {r.json()["saldo"] for r in resp} == {"0.00"}
    # Un unico hecho nuevo: la huella crece lo de UN cobro.
    assert m3.huella(owner) != antes


# ------------------------------------------------------------------ F3 / F4: gasto (Repetir hoy) y gasto con prevision
@pytest.mark.parametrize("con_prevision", [False, True])
def test_gasto_respuesta_perdida_reenvio_un_solo_hecho(con_prevision):
    owner, actor, cli, cta, ahorro = m5.entorno()
    c = m5.h.intencion(cta, importe="74.00", fecha_hecho="2026-10-07")
    if con_prevision:
        luz = m5.prevision(owner, "Electricidad", importe="74.00", cuenta_salida=cta)
        c["prevision"] = m5.bloque(owner, luz, True)
    r1 = cli.post(m5.GASTO, json=c, headers=h.AUTH)
    assert r1.status_code == 200, r1.text
    base = m5.huella(owner)
    r2 = cli.post(m5.GASTO, json=c, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True, r2.text
    assert m5.huella(owner) == base  # ni segundo hecho, ni movimiento, ni vinculo
    assert m5.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (uuid.UUID(c["intencion_id"]),))[0] == 1
    if con_prevision:
        assert len(m5.vinculos(owner, luz)) == 1 and m5.estado(owner, luz) == "REALIZADA"


# ------------------------------------------------------------------ F5: «No hubo» y la lectura de reconciliacion
def test_no_hubo_reenvio_409_sin_escritura_y_la_lectura_dice_omitida():
    owner, actor, cli, cta, ahorro = m5.entorno()
    regla, cabeza = m5.rodante(owner, cuenta_salida=cta)
    c, r1 = m5.omitir(cli, owner, cabeza)
    assert r1.status_code == 200, r1.text
    base = m5.huella(owner)
    r2 = cli.post(f"/v1/previsiones/{cabeza}/omitir", json=c, headers=h.AUTH)  # reenvio de la cola
    assert r2.status_code == 409 and r2.json()["codigo"] == "ESTADO_PREVISION_INCOMPATIBLE"
    assert m5.huella(owner) == base and len(m5.previsiones_de_regla(owner, regla)) == 2  # sin segundo sucesor
    lectura = cli.get(f"/v1/previsiones/{cabeza}", headers=h.AUTH)  # la lectura de reconciliacion
    assert lectura.status_code == 200 and lectura.json()["estado"] == "OMITIDA"
    assert m5.huella(owner) == base  # leer no escribe


def test_no_hubo_reenvio_concurrente_un_200_un_409_y_la_lectura_ve_el_resultado_definitivo():
    owner, actor, cli, cta, ahorro = m5.entorno()
    regla, cabeza = m5.rodante(owner, cuenta_salida=cta)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": m5.version(owner, cabeza), "motivo": None}
    clientes = [h.cliente(owner, reloj=m5.x.reloj()) for _ in range(2)]
    barrera, resp = threading.Barrier(2), []

    def enviar(k):
        barrera.wait()
        resp.append(clientes[k].post(f"/v1/previsiones/{cabeza}/omitir", json=c, headers=h.AUTH))

    hilos = [threading.Thread(target=enviar, args=(k,)) for k in range(2)]
    [x.start() for x in hilos]
    [x.join() for x in hilos]
    assert sorted(r.status_code for r in resp) == [200, 409], [r.text for r in resp]
    assert [e for _, e, _ in m5.previsiones_de_regla(owner, regla)] == ["OMITIDA", "ABIERTA"]  # un solo sucesor
    assert cli.get(f"/v1/previsiones/{cabeza}", headers=h.AUTH).json()["estado"] == "OMITIDA"


def test_no_hubo_reenvio_409_y_la_lectura_dice_otro_estado():
    owner, actor, cli, cta, ahorro = m5.entorno()
    luz = m5.prevision(owner, "Electricidad", importe="74.00", cuenta_salida=cta)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": m5.version(owner, luz), "motivo": None}
    _, r = m5.gasto_desde(cli, owner, cta, luz, "74.00", True)  # otra sesion la cubre antes de que llegue «No hubo»
    assert r.status_code == 200, r.text
    base = m5.huella(owner)
    r2 = cli.post(f"/v1/previsiones/{luz}/omitir", json=c, headers=h.AUTH)
    assert r2.status_code == 409, r2.text
    assert cli.get(f"/v1/previsiones/{luz}", headers=h.AUTH).json()["estado"] == "REALIZADA"
    assert m5.huella(owner) == base


def test_comprobacion_de_conexion_no_escribe():
    owner, actor, cli, cta, ahorro = m5.entorno()
    base = m5.huella(owner)
    r = cli.get("/v1/yo", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert m5.huella(owner) == base
