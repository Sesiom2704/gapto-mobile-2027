# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_207_f05_06_m5b_dar_y_reabrir.py
# Ruta: tests/api/test_207_f05_06_m5b_dar_y_reabrir.py
# Descripcion: F05-06 M5-B por HTTP (F04-D065; F05 §61 F05-D047;
#   AJ-M5BM1-01..11). Con el rol real gapto_runtime y RLS:
#     - POST /v1/previsiones/{id}/dar-por-realizada: PARCIAL -> REALIZADA sin
#       hecho, efecto, movimiento ni vinculo nuevos; la desviacion no se
#       persiste; resultado del mes identico; motivo obligatorio (422); sin
#       realidad o con el unico hecho anulado (409 PREVISION_SIN_REALIDAD_ACTIVA,
#       texto que informa de «No hubo este mes»); estado y version (409 con el
#       estado releido); reintento de la misma intencion (409, sin escritura ni
#       segundo sucesor); RODANTE con sucesor determinista;
#     - POST /v1/previsiones/{id}/reabrir: REALIZADA y OMITIDA -> ABIERTA con
#       vinculos conservados; CANCELADA rechazada en el adaptador (el motor si
#       la admite); ABIERTA 409; RODANTE con sucesor: exige su version, lo
#       cancela; con realidad en el sucesor TRAMO_RODANTE_REQUIERE_REVISION;
#     - lectura: pendiente con signo (negativo = registrado de mas), recalculable, sucesor (id y version) y
#       acciones dar_por_cubierta / reabrir con motivo; id de otro owner 404.
#   Reloj fijo 2026-10-10 12:00Z (Madrid).
# Version: 0.1.0 (F05-06 M5-B)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import f05_06_m5_helpers as m
import vs01_api_helpers as h

D = m.D


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    iber = m.x.tercero(cli, "Iberdrola")
    return owner, actor, cli, cta, ahorro, iber


def _cod(r):
    return r.json().get("codigo")


def dar(cli, owner, pid, *, motivo="la factura definitiva fue menor", row_version=None, intencion_id=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "row_version": row_version or m.version(owner, pid),
         "motivo": motivo}
    return c, cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=c, headers=h.AUTH)


def reabrir(cli, owner, pid, *, motivo="la marqué por error", row_version=None, sucesor_row_version=None):
    c = {"intencion_id": str(uuid.uuid4()), "row_version": row_version or m.version(owner, pid), "motivo": motivo,
         "sucesor_row_version": sucesor_row_version}
    return c, cli.post(f"/v1/previsiones/{pid}/reabrir", json=c, headers=h.AUTH)


def _seguro_parcial(t, pagado="40.00"):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Seguro hogar", importe="120.00", tercero=iber, cuenta_salida=cta)
    c, r = m.gasto_desde(cli, owner, cta, pid, pagado, False, tercero=iber)
    assert r.status_code == 200, r.text
    return pid, uuid.UUID(c["intencion_id"])


# ==================================================================
# Dar por cubierta
# ==================================================================
def test_dar_parcial_sin_realidad_nueva_ni_desviacion_persistida(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, hid = _seguro_parcial(t)
    d = m.detalle(cli, pid)
    assert d["acciones"]["dar_por_cubierta"] == {"disponible": True, "motivo": None}
    assert (d["cubierto"], d["queda"], d["pendiente"]) == ("40.00", "80.00", "80.00")
    assert d["recalculable"] is False and d["sucesor"] is None
    base, saldo, res = m.huella(owner), m.saldo(owner, cta), m.resultado(cli)
    c, r = dar(cli, owner, pid, motivo="  la factura definitiva fue menor  ")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "REALIZADA" and r.json()["prevision_id"] == str(pid)
    assert r.json()["row_version"] == m.version(owner, pid)
    despues = m.huella(owner)
    # Solo cambian la prevision (misma fila) y la auditoria: ningun hecho, efecto, movimiento ni vinculo.
    assert despues[:8] == base[:8] and despues[8] > base[8]
    assert m.saldo(owner, cta) == saldo and m.resultado(cli) == res
    assert m.vinculos(owner, pid) == [(hid, D("40.0000"))]
    assert m.uno(owner, "SELECT estado, importe_esperado, recalculo_automatico FROM gapto.previsiones WHERE id = %s",
                 (pid,)) == ("REALIZADA", D("120.0000"), False)
    assert m.uno(owner, "SELECT motivo FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR' "
                        "ORDER BY created_at DESC LIMIT 1", (pid,)) == (
        "realizacion sin realidad nueva: la factura definitiva fue menor",)
    d = m.detalle(cli, pid)
    assert d["estado"] == "REALIZADA" and d["acciones"]["dar_por_cubierta"]["disponible"] is False
    assert d["acciones"]["reabrir"]["disponible"] is True
    assert pid not in [uuid.UUID(f["id"]) for f in m.pendientes(cli)["secciones"]["con_pago_parcial"]]


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_dar_sin_motivo_422_sin_escritura(t, motivo):
    owner, actor, cli, cta, ahorro, iber = t
    pid, _ = _seguro_parcial(t)
    base = m.huella(owner)
    _, r = dar(cli, owner, pid, motivo=motivo)
    assert r.status_code == 422 and _cod(r) == "MOTIVO_AUSENTE"
    assert m.huella(owner) == base and m.estado(owner, pid) == "ABIERTA"


def test_dar_motivo_demasiado_largo_422(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, _ = _seguro_parcial(t)
    _, r = dar(cli, owner, pid, motivo="x" * 201)
    assert r.status_code == 422 and m.estado(owner, pid) == "ABIERTA"


def test_dar_sin_realidad_409_informa_de_no_hubo(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00", tercero=iber, cuenta_salida=cta)
    d = m.detalle(cli, pid)
    assert d["acciones"]["dar_por_cubierta"]["disponible"] is False
    assert "No hubo este mes" in d["acciones"]["dar_por_cubierta"]["motivo"]
    base = m.huella(owner)
    _, r = dar(cli, owner, pid)
    assert r.status_code == 409 and _cod(r) == "PREVISION_SIN_REALIDAD_ACTIVA"
    assert "No hubo este mes" in r.json()["mensaje"] and "No se ha guardado nada" in r.json()["mensaje"]
    assert m.huella(owner) == base and m.estado(owner, pid) == "ABIERTA"


def test_dar_con_el_unico_hecho_anulado_409(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, hid = _seguro_parcial(t)
    m.x.anular(owner, hid)
    assert m.detalle(cli, pid)["acciones"]["dar_por_cubierta"]["disponible"] is False
    base = m.huella(owner)
    _, r = dar(cli, owner, pid)
    assert r.status_code == 409 and _cod(r) == "PREVISION_SIN_REALIDAD_ACTIVA"
    assert m.huella(owner) == base and m.estado(owner, pid) == "ABIERTA"


def test_dar_version_desfasada_409_con_estado_releido(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, _ = _seguro_parcial(t)
    v = m.version(owner, pid)
    base = m.huella(owner)
    _, r = dar(cli, owner, pid, row_version=v + 3)
    assert r.status_code == 409 and _cod(r) == "VERSION_DESFASADA"
    assert r.json()["detalle"]["estado_actual"]["row_version"] == v
    assert m.huella(owner) == base


def test_dar_reintento_misma_intencion_409_sin_segunda_escritura(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, _ = _seguro_parcial(t)
    c, r = dar(cli, owner, pid)
    assert r.status_code == 200, r.text
    base = m.huella(owner)
    r2 = cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=c, headers=h.AUTH)
    assert r2.status_code == 409 and _cod(r2) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert r2.json()["detalle"]["estado_actual"]["estado"] == "REALIZADA"
    assert m.huella(owner) == base


def test_dar_omitida_409(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    m.omitir(cli, owner, pid)
    base = m.huella(owner)
    _, r = dar(cli, owner, pid)
    assert r.status_code == 409 and _cod(r) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert m.huella(owner) == base


def test_dar_rodante_crea_sucesor_determinista(t):
    owner, actor, cli, cta, ahorro, iber = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    m.gasto_desde(cli, owner, cta, cabeza, "20.00", False, fecha="2026-10-01")
    c, r = dar(cli, owner, cabeza)
    assert r.status_code == 200, r.text
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    assert [(p, e) for p, e, _ in m.previsiones_de_regla(owner, regla)] == [(cabeza, "REALIZADA"),
                                                                            (sucesor, "ABIERTA")]
    d = m.detalle(cli, cabeza)
    assert d["sucesor"] == {"id": str(sucesor), "row_version": m.version(owner, sucesor)}


def test_dar_otro_owner_404(t):
    owner, actor, cli, cta, ahorro, iber = t
    otro = m.entorno()
    ajena = m.prevision(otro[0], "Ajena", importe="10.00")
    c = {"intencion_id": str(uuid.uuid4()), "row_version": 1, "motivo": "x"}
    r = cli.post(f"/v1/previsiones/{ajena}/dar-por-realizada", json=c, headers=h.AUTH)
    assert r.status_code == 404
    assert m.estado(otro[0], ajena) == "ABIERTA"


def test_dar_sin_token_401(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, _ = _seguro_parcial(t)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(owner, pid), "motivo": "x"}
    assert cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=c).status_code == 401


# ==================================================================
# Reabrir
# ==================================================================
def test_reabrir_realizada_conserva_los_vinculos(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid, hid = _seguro_parcial(t)
    dar(cli, owner, pid)
    base = m.huella(owner)
    _, r = reabrir(cli, owner, pid)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ABIERTA" and m.estado(owner, pid) == "ABIERTA"
    assert m.vinculos(owner, pid) == [(hid, D("40.0000"))]
    assert m.huella(owner)[:8] == base[:8]
    d = m.detalle(cli, pid)
    assert d["acciones"]["dar_por_cubierta"]["disponible"] is True and d["acciones"]["reabrir"]["disponible"] is False


def test_reabrir_omitida(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    m.omitir(cli, owner, pid)
    _, r = reabrir(cli, owner, pid)
    assert r.status_code == 200, r.text
    assert m.estado(owner, pid) == "ABIERTA"


@pytest.mark.parametrize("motivo", [None, "  "])
def test_reabrir_sin_motivo_422(t, motivo):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    m.omitir(cli, owner, pid)
    base = m.huella(owner)
    _, r = reabrir(cli, owner, pid, motivo=motivo)
    assert r.status_code == 422 and _cod(r) == "MOTIVO_AUSENTE"
    assert m.huella(owner) == base and m.estado(owner, pid) == "OMITIDA"


def test_reabrir_abierta_409(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    _, r = reabrir(cli, owner, pid)
    assert r.status_code == 409 and _cod(r) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert r.json()["detalle"]["estado_actual"]["estado"] == "ABIERTA"


def test_reabrir_cancelada_rechazada_en_el_adaptador(t):
    owner, actor, cli, cta, ahorro, iber = t
    from app.services.previsiones_service import PrevisionesService

    pid = m.prevision(owner, "Luz", importe="74.00")
    PrevisionesService(fh.unidad()).cancelar(m.ctx(owner), prevision_id=pid, row_version_esperada=m.version(owner, pid))
    assert m.estado(owner, pid) == "CANCELADA"
    d = m.detalle(cli, pid)
    assert d["acciones"]["reabrir"] == {"disponible": False,
                                        "motivo": "Una previsión cancelada no se reabre desde la app."}
    base = m.huella(owner)
    _, r = reabrir(cli, owner, pid)
    assert r.status_code == 409 and _cod(r) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert r.json()["detalle"]["estado_actual"]["estado"] == "CANCELADA"
    assert m.huella(owner) == base and m.estado(owner, pid) == "CANCELADA"


def test_reabrir_version_desfasada_409(t):
    owner, actor, cli, cta, ahorro, iber = t
    pid = m.prevision(owner, "Luz", importe="74.00")
    m.omitir(cli, owner, pid)
    base = m.huella(owner)
    _, r = reabrir(cli, owner, pid, row_version=m.version(owner, pid) + 2)
    assert r.status_code == 409 and _cod(r) == "VERSION_DESFASADA" and m.huella(owner) == base


def test_reabrir_rodante_cancela_el_sucesor_con_su_version(t):
    owner, actor, cli, cta, ahorro, iber = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    c, _ = m.omitir(cli, owner, cabeza)
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    d = m.detalle(cli, cabeza)
    assert d["sucesor"] == {"id": str(sucesor), "row_version": m.version(owner, sucesor)}
    base = m.huella(owner)
    # Sin la version del sucesor: rechazo sin escritura.
    _, r = reabrir(cli, owner, cabeza)
    assert r.status_code == 409 and _cod(r) == "ENTRADA_INVALIDA" and m.huella(owner) == base
    _, r = reabrir(cli, owner, cabeza, sucesor_row_version=d["sucesor"]["row_version"])
    assert r.status_code == 200, r.text
    assert [(p, e) for p, e, _ in m.previsiones_de_regla(owner, regla)] == [(cabeza, "ABIERTA"),
                                                                            (sucesor, "CANCELADA")]


def test_reabrir_rodante_con_realidad_en_el_sucesor_requiere_revision(t):
    owner, actor, cli, cta, ahorro, iber = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    c, _ = m.omitir(cli, owner, cabeza)
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    m.gasto_desde(cli, owner, cta, sucesor, "10.00", False, fecha="2026-10-08")
    sv = m.version(owner, sucesor)
    base = m.huella(owner)
    _, r = reabrir(cli, owner, cabeza, sucesor_row_version=sv)
    assert r.status_code == 409 and _cod(r) == "TRAMO_RODANTE_REQUIERE_REVISION"
    assert "No se ha cambiado nada" in r.json()["mensaje"]
    assert m.huella(owner) == base and m.estado(owner, cabeza) == "OMITIDA"


def test_reabrir_otro_owner_404(t):
    owner, actor, cli, cta, ahorro, iber = t
    otro = m.entorno()
    ajena = m.prevision(otro[0], "Ajena", importe="10.00")
    c = {"intencion_id": str(uuid.uuid4()), "row_version": 1, "motivo": "x", "sucesor_row_version": None}
    assert cli.post(f"/v1/previsiones/{ajena}/reabrir", json=c, headers=h.AUTH).status_code == 404


# ==================================================================
# Lectura (Q4)
# ==================================================================
def test_pendiente_con_signo_y_recalculable(t):
    owner, actor, cli, cta, ahorro, iber = t
    nueva = m.prevision(owner, "Luz", importe="74.00")
    d = m.detalle(cli, nueva)
    assert (d["pendiente"], d["recalculable"]) == ("74.00", False)  # manual: nunca recalculable
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    assert m.detalle(cli, cabeza)["recalculable"] is True  # de regla y sin realidad
    gas = m.prevision(owner, "Gas", importe="120.00", tercero=iber)
    m.gasto_desde(cli, owner, cta, gas, "130.00", False)
    d = m.detalle(cli, gas)
    assert (d["pendiente"], d["desviacion"], d["recalculable"]) == ("-10.00", "10.00", False)
    agua = m.prevision(owner, "Agua", importe=None)
    assert m.detalle(cli, agua)["pendiente"] is None
