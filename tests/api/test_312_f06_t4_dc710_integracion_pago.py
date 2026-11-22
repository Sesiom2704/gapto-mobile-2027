# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_312_f06_t4_dc710_integracion_pago.py
# Ruta: tests/api/test_312_f06_t4_dc710_integracion_pago.py
# Descripcion: D-C7-10 · integracion del gesto «Pagado» con W-HIP-02 (mandato F06 T4 DC710 v1.0 §4 «Integracion»;
#   AJ-DC710-07 casos 1, 2, 3, 5, 7, 8 y 9 en secuencia; la concurrencia real esta en test_313). El payload se compone
#   SOLO con el bloque `cuota` de Pendientes, como el cliente. Oraculos: (1) intereses como GASTO, capital como
#   reduccion de DEUDA y salida por la cuota completa en la cuenta de cargo; (2) importes y atribuciones exactos
#   (suma exacta, 60/40 del prestamo), aportaciones de la cuenta de cargo y un solo hecho; (3) la prevision pasa a
#   REALIZADA solo con la escritura confirmada (un rechazo la deja ABIERTA con el estado identico); (5) cuota vencida:
#   hecho y movimiento en el vencimiento, no hoy; (7) revision del tipo entre la lectura y el pago: VERSION_DESFASADA
#   sin pago; (8) el boton paga primero: el swipe es CUOTA_NO_PENDIENTE, un solo pago; (9) replay de la misma
#   intencion: idempotente; la intencion del swipe tras el pago de otra: CUOTA_NO_PENDIENTE, nunca idempotente.
#   Ninguna escritura por gasto-pagado (el unico hecho es el de W-HIP-02, id = intencion).
# Version: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
# ============================================================
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from test_289_f06_01h_alta_en_compra import huella
from test_294_f06_01h_revision_tipo import LabRev
from test_311_f06_t4_dc710_bloque_cuota import LabSwipe, _payload


class LabC(LabSwipe, LabRev):
    """LabSwipe (cargo `cc` 60/40, sin dudas) con la revision del tipo de LabRev."""


@pytest.fixture()
def lab():
    return LabC()


def _hechos(lab) -> int:
    return lab.sql("SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.hecho_efectos e ON e.hecho_id = h.id "
                   "WHERE e.id IN (SELECT efecto_id FROM gapto.hecho_entidades WHERE entidad_id = %s) "
                   "AND h.tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO')", (lab.f,))[0][0]


def _estado_prevision(lab, numero: int) -> str:
    return lab.sql("SELECT estado FROM gapto.previsiones WHERE id = %s", (lab.cuotas()[numero],))[0][0]


def test_1_2_3_5_pago_por_el_bloque_compone_hecho_efectos_tesoreria_y_atribuciones_exactos(lab):
    f = lab.fila(1)
    payload = _payload(f)
    hid = uuid.UUID(payload["intencion_id"])
    assert _estado_prevision(lab, 1) == "ABIERTA"
    total, interes, capital = lab.sql(
        "SELECT importe_total_previsto, interes_previsto, capital_previsto FROM gapto.financiacion_cuotas "
        "WHERE financiacion_entidad_id = %s AND numero_cuota = 1", (lab.f,))[0]
    assert total == interes + capital and interes > 0 and capital > 0
    r = lab.pagar(1, payload)
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    # (1) GASTO por los intereses, DEUDA por -capital; (5) el hecho en el vencimiento
    assert lab.sql("SELECT fecha_hecho::text, importe_total FROM gapto.hechos_financieros WHERE id = %s",
                   (hid,)) == [("2026-04-20", total)]
    efectos = dict(lab.sql("SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,)))
    assert efectos == {"GASTO": interes, "DEUDA": -capital}
    # (1) salida por la cuota completa en la cuenta de cargo, (5) en el vencimiento, conciliada entera
    mov = lab.sql("SELECT m.cuenta_id, m.fecha_movimiento::text, m.importe, c.importe_asignado "
                  "FROM gapto.hecho_movimientos_tesoreria c JOIN gapto.movimientos_tesoreria m "
                  "ON m.id = c.movimiento_tesoreria_id WHERE c.hecho_id = %s", (hid,))
    assert mov == [(lab.cc, "2026-04-20", -total, -total)]
    # (2) atribuciones: titularidad del prestamo 60/40, suma exacta por efecto
    for tipo, importe in efectos.items():
        filas = dict(lab.sql("SELECT a.actor_id::text, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                             "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s "
                             "AND e.tipo_efecto = %s", (hid, tipo)))
        assert set(filas) == {lab.yo, lab.a} and sum(filas.values()) == importe, (tipo, filas)
        assert abs(filas[lab.yo] - importe * Decimal("0.6")) <= Decimal("0.01"), (tipo, filas)
    # (2) aportaciones de la cuenta de cargo por su participacion (60/40), suma = cuota
    aport = dict(lab.sql("SELECT actor_id::text, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", (hid,)))
    assert set(aport) == {lab.yo, lab.a} and sum(aport.values()) == total, aport
    # (3) la prevision, REALIZADA tras el COMMIT; un solo hecho de pago de la financiacion
    assert _estado_prevision(lab, 1) == "REALIZADA"
    assert _hechos(lab) == 1
    assert lab.sql("SELECT count(*) FROM gapto.prevision_hechos WHERE prevision_id = %s", (lab.cuotas()[1],))[0][0] == 1


def test_3_7_revision_del_tipo_entre_la_lectura_y_el_pago_version_desfasada_sin_escritura(lab):
    f = lab.fila(1)                                       # el cliente lee la fila (version de la financiacion)
    r = lab.revisar(lab.cuerpo_rev(desde="2026-12-01"))  # otra sesion revisa el tipo (no afecta a c1)
    assert r.status_code == 200, r.text
    antes = huella()
    r = lab.pagar(1, _payload(f))
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA", r.text
    assert huella() == antes and _estado_prevision(lab, 1) == "ABIERTA"
    # la fila releida trae la version nueva y vuelve a ofrecer el gesto
    q = lab.fila(1)["cuota"]
    assert q["financiacion_row_version"] == lab.hipoteca()["row_version"] != f["cuota"]["financiacion_row_version"]
    assert lab.pagar(1, _payload(lab.fila(1))).status_code == 200


def test_8_el_boton_paga_primero_el_swipe_es_cuota_no_pendiente_y_hay_un_solo_pago(lab):
    f = lab.fila(1)
    assert lab.pagar(1, lab.cuerpo()).status_code == 200      # boton: otra intencion
    antes = huella()
    r = lab.pagar(1, _payload(f))
    assert r.status_code == 409 and r.json()["codigo"] in ("CUOTA_NO_PENDIENTE", "VERSION_DESFASADA"), r.text
    assert huella() == antes and _hechos(lab) == 1


def test_9_replay_de_la_misma_intencion_idempotente_y_otra_intencion_nunca_idempotente(lab):
    f = lab.fila(1)
    p_swipe = _payload(f)
    # respuesta perdida del swipe: el replay con la MISMA intencion y el mismo payload confirma sin escribir
    assert lab.pagar(1, p_swipe).status_code == 200
    antes = huella()
    r = lab.pagar(1, p_swipe)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["hecho_id"] == p_swipe["intencion_id"]
    assert huella() == antes
    # otra intencion (p. ej. un segundo swipe o el boton) sobre la cuota ya pagada: rechazo, nunca idempotente
    otra = {**p_swipe, "intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.hipoteca()["row_version"]}
    r = lab.pagar(1, otra)
    assert r.status_code == 409 and r.json()["codigo"] == "CUOTA_NO_PENDIENTE", r.text
    assert huella() == antes and _hechos(lab) == 1


def test_9_respuesta_perdida_mientras_otra_intencion_paga_el_replay_del_swipe_es_rechazo(lab):
    """El swipe no llego a escribir (respuesta perdida antes del servidor) y el boton pago la cuota: el replay del
    swipe con su intencion es CUOTA_NO_PENDIENTE (la cola lo deja RECHAZADA), aunque la prevision este REALIZADA."""
    p_swipe = _payload(lab.fila(1))
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    assert _estado_prevision(lab, 1) == "REALIZADA"
    r = lab.pagar(1, p_swipe)
    assert r.status_code == 409 and r.json()["codigo"] in ("CUOTA_NO_PENDIENTE", "VERSION_DESFASADA"), r.text
    assert lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (p_swipe["intencion_id"],)) == [(0,)]
