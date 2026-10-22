# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_211_f05_06_m5b_resueltas_mes.py
# Ruta: tests/api/test_211_f05_06_m5b_resueltas_mes.py
# Descripcion: F05-06 M5-B v1.1 · «Resueltas este mes» por HTTP
#   (HANDOFF_M5BM1 §6: una OMITIDA por swipe no llegaba a «Reabrir»). Con el rol
#   real gapto_runtime y RLS, GET /v1/previsiones/pendientes → `resueltas_mes`:
#     - incluye OMITIDA («No hubo»), REALIZADA (dar por cubierta y pagada
#       completa) y la derivada REALIZADA_SIN_REALIDAD_ACTIVA, con la fecha de
#       su transicion (AUDITORIA) y orden de mas reciente a mas antigua;
#     - excluye ABIERTA y CANCELADA; sin auditoria de la transicion, usa la
#       fecha objetivo (OBJETIVO) y aplica el mismo limite de mes;
#     - limite del mes natural de hoy_owner: fuera el mes anterior y el
#       siguiente;
#     - no suma: `n`, «Por pagar» y «Por cobrar» de pendientes no cambian;
#     - reabrir la saca de «Resueltas» y la devuelve a «Vencidas».
#   El reloj del cliente fija hoy_owner; la auditoria lleva la hora real del
#   servidor, asi que los limites de mes se calculan desde ella.
# Version: 0.1.0 (F05-06 M5-B v1.1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import pytest

import f05_06_m5_helpers as m
import vs01_api_helpers as h

D = m.D


def _hoy_real(owner) -> dt.date:
    """Fecha de la auditoria que se va a escribir (now() del servidor en Madrid)."""
    return m.uno(owner, "SELECT (now() AT TIME ZONE 'Europe/Madrid')::date")[0]


def _iso(fecha: dt.date) -> str:
    return f"{fecha.isoformat()}T12:00:00"


@pytest.fixture()
def t():
    owner, actor, _, cta, ahorro = m.entorno()
    hoy = _hoy_real(owner)
    cli = h.cliente(owner, reloj=m.x.reloj(_iso(hoy)))
    iber = m.x.tercero(cli, "Iberdrola")
    return owner, cli, cta, iber, hoy


def _resueltas(cli) -> dict:
    return m.pendientes(cli)["resueltas_mes"]


def _ids(cli) -> list[str]:
    return [f["id"] for f in _resueltas(cli)["filas"]]


def _fila(cli, pid) -> dict:
    return next(f for f in _resueltas(cli)["filas"] if f["id"] == str(pid))


def _dar(cli, owner, pid, motivo="la factura definitiva fue menor"):
    r = cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": m.version(owner, pid), "motivo": motivo})
    assert r.status_code == 200, r.text


def _reabrir(cli, owner, pid):
    r = cli.post(f"/v1/previsiones/{pid}/reabrir", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": m.version(owner, pid), "motivo": "la marqué por error",
        "sucesor_row_version": None})
    assert r.status_code == 200, r.text


def _vencida(owner, concepto, hoy, **kw):
    """ABIERTA y vencida dentro del mes de hoy (o el 1, si hoy es dia 1)."""
    dia = max(hoy.replace(day=1), hoy - dt.timedelta(days=1))
    return m.prevision(owner, concepto, desde=str(dia), **kw)


def test_omitida_aparece_con_la_fecha_de_su_transicion(t):
    owner, cli, cta, iber, hoy = t
    pid = _vencida(owner, "Electricidad", hoy, tercero=iber)
    assert str(pid) in [f["id"] for f in m.pendientes(cli)["secciones"]["vencidas"]]
    _, r = m.omitir(cli, owner, pid, motivo="no hubo")
    assert r.status_code == 200, r.text
    res = _resueltas(cli)
    assert (res["desde"], res["hasta"]) == (str(hoy.replace(day=1)),
                                           str((hoy.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)))
    f = _fila(cli, pid)
    assert (f["estado"], f["estado_derivado"], f["resuelta_el"], f["resuelta_por"]) == ("OMITIDA", None, str(hoy), "AUDITORIA")
    assert res["n"] == len(res["filas"]) == 1
    assert str(pid) not in [f["id"] for f in m.pendientes(cli)["secciones"]["vencidas"]]


def test_realizadas_cubierta_pagada_y_sin_realidad_activa(t):
    owner, cli, cta, iber, hoy = t
    seguro = _vencida(owner, "Seguro hogar", hoy, importe="120.00", tercero=iber, cuenta_salida=cta)
    _, r = m.gasto_desde(cli, owner, cta, seguro, "40.00", False, tercero=iber, fecha=str(hoy))
    assert r.status_code == 200, r.text
    _dar(cli, owner, seguro)
    luz = _vencida(owner, "Luz", hoy, importe="74.00", tercero=iber, cuenta_salida=cta)
    c, r = m.gasto_desde(cli, owner, cta, luz, "74.00", True, tercero=iber, fecha=str(hoy))
    assert r.status_code == 200, r.text
    assert m.estado(owner, luz) == "REALIZADA"
    m.x.anular(owner, uuid.UUID(c["intencion_id"]))  # el pago desaparece: queda REALIZADA sin realidad activa
    filas = {f["id"]: f for f in _resueltas(cli)["filas"]}
    assert (filas[str(seguro)]["estado"], filas[str(seguro)]["estado_derivado"], filas[str(seguro)]["cubierto"]) == (
        "REALIZADA", None, "40.00")
    assert (filas[str(luz)]["estado"], filas[str(luz)]["estado_derivado"]) == ("REALIZADA", "REALIZADA_SIN_REALIDAD_ACTIVA")
    assert all(f["resuelta_por"] == "AUDITORIA" and f["resuelta_el"] == str(hoy) for f in filas.values())


def test_abiertas_y_canceladas_no_aparecen(t):
    owner, cli, cta, iber, hoy = t
    abierta = _vencida(owner, "Agua", hoy, tercero=iber)
    cancelada = _vencida(owner, "Gas", hoy, tercero=iber)
    h.como_owner(owner, "UPDATE gapto.previsiones SET estado = 'CANCELADA' WHERE id = %s", (cancelada,))
    omitida = _vencida(owner, "Internet", hoy, tercero=iber)
    m.omitir(cli, owner, omitida, motivo="no hubo")
    assert _ids(cli) == [str(omitida)]
    assert str(abierta) in [f["id"] for f in m.pendientes(cli)["secciones"]["vencidas"]]


def test_sin_auditoria_de_la_transicion_usa_la_fecha_objetivo(t):
    owner, cli, cta, iber, hoy = t
    inicio = hoy.replace(day=1)
    dentro = m.prevision(owner, "Comunidad", desde=str(inicio), tercero=iber)
    fuera = m.prevision(owner, "Comunidad (mes anterior)", desde=str(inicio - dt.timedelta(days=1)), tercero=iber)
    for pid in (dentro, fuera):  # terminal sin fila de auditoria de la transicion (p. ej. datos cargados)
        h.como_owner(owner, "UPDATE gapto.previsiones SET estado = 'OMITIDA' WHERE id = %s", (pid,))
    f = _fila(cli, dentro)
    assert (f["resuelta_el"], f["resuelta_por"]) == (str(inicio), "OBJETIVO")
    assert str(fuera) not in _ids(cli)


@pytest.mark.parametrize("mes", ["anterior", "siguiente"])
def test_limite_del_mes(t, mes):
    owner, cli, cta, iber, hoy = t
    pid = _vencida(owner, "Electricidad", hoy, tercero=iber)
    m.omitir(cli, owner, pid, motivo="no hubo")
    assert str(pid) in _ids(cli)
    inicio = hoy.replace(day=1)
    otro = inicio - dt.timedelta(days=1) if mes == "anterior" else (inicio + dt.timedelta(days=32)).replace(day=1)
    cli_otro = h.cliente(owner, reloj=m.x.reloj(_iso(otro)))
    assert str(pid) not in _ids(cli_otro)


def test_no_suma_a_pendientes(t):
    owner, cli, cta, iber, hoy = t
    a = _vencida(owner, "Electricidad", hoy, importe="74.00", tercero=iber)
    _vencida(owner, "Agua", hoy, importe="30.00", tercero=iber)
    antes = m.pendientes(cli)
    m.omitir(cli, owner, a, motivo="no hubo")
    despues = m.pendientes(cli)
    assert (despues["n"], despues["por_pagar"]) == (antes["n"] - 1, {**antes["por_pagar"], "importe": "30.00", "n": 1})
    assert despues["resueltas_mes"]["n"] == 1  # aparte: no entra en n ni en «Por pagar»


def test_reabrir_la_devuelve_a_vencidas(t):
    owner, cli, cta, iber, hoy = t
    pid = _vencida(owner, "Electricidad", hoy, tercero=iber)
    m.omitir(cli, owner, pid, motivo="no hubo")
    assert str(pid) in _ids(cli)
    _reabrir(cli, owner, pid)
    p = m.pendientes(cli)
    assert str(pid) not in [f["id"] for f in p["resueltas_mes"]["filas"]]
    assert str(pid) in [f["id"] for f in p["secciones"]["vencidas"]]


def test_orden_mas_reciente_primero_y_detalle_con_reabrir(t):
    owner, cli, cta, iber, hoy = t
    primera = _vencida(owner, "Agua", hoy, tercero=iber)
    segunda = _vencida(owner, "Gas", hoy, tercero=iber)
    m.omitir(cli, owner, primera, motivo="no hubo")
    m.omitir(cli, owner, segunda, motivo="no hubo")
    assert _ids(cli) == [str(segunda), str(primera)]  # la ultima resuelta, arriba
    assert m.detalle(cli, segunda)["acciones"]["reabrir"]["disponible"] is True
