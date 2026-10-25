# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_214_f04_r3_c2_reabrir_serial.py
# Ruta: tests/api/test_214_f04_r3_c2_reabrir_serial.py
# Descripcion: F04-R3 (F05-D050 §64.4; adenda 2 §D). Bateria SERIAL y
#   determinista, FUERA de la suite general: solo con
#   GAPTO_F04R3_CONCURRENCIA=1 (evidencia JSON si GAPTO_F04R3_EVIDENCIA apunta
#   a una carpeta). COMMIT real sobre base desechable. Nunca en paralelo.
#   Solo rutas EXPUESTAS, por las funciones del adaptador HTTP.
#
#   C2 (INFORME_DIAG_F04-R3 §3.2): «Reabrir» frente a las rutas expuestas
#      que comparten sus locks, en los dos ordenes, con el arnes de test_205
#      (el primero se retiene dentro de su transaccion tras su ultimo lock
#      relevante, se lanza el segundo, se espera a que termine o quede
#      bloqueado y se libera el primero). Escenario: dos reglas RODANTE cuyas
#      cabezas P1 y P2 realiza el MISMO hecho H (OP-17 de motor en la fixture,
#      40 + 60: «Ya lo registre» exige la porcion completa y no lo produce):
#        C2a «Reabrir» P1 x «Reabrir» P2;
#        C2b «Reabrir» P1 x OP-22 (gasto pagado) realizando el sucesor S1;
#        C2c «Reabrir» P1 x OP-21P sobre H (corrige la fecha: propaga a las
#            reglas y previsiones de H).
#      Oraculo: nadie colgado, 0 reintentos 40P01 y 0 deadlocks nuevos (arnes
#      de test_205) y resultado semantico FIJO por orden: el mismo desenlace
#      (exito o rechazo sin efectos) y la misma huella de estado que la
#      ejecucion SERIAL de los mismos dos pasos sobre un escenario gemelo,
#      ademas del codigo esperado explicito de cada orden. Observacion C2-O1:
#      en C2b A-primero el perdedor recibe VERSION_DESFASADA (espero la regla
#      con la prevision ya leida) y en serie ESTADO_PREVISION_INCOMPATIBLE;
#      ambos rechazos sin efectos.
#   Hallazgo C2-H1 (serial, NO corregido; reproduccion xfail estricta): con
#      el sucesor S1 ya REALIZADO por OP-22 y su nueva cabeza S1' ABIERTA,
#      «Reabrir» P1 se admite y cancela S1': la cadena queda ABIERTA (P1),
#      REALIZADA (S1), CANCELADA (S1'). La docstring de
#      corregir_estado_terminal (F04-D024.9) pide TRAMO_RODANTE_REQUIERE_REVISION
#      cuando la cadena ya avanzo a un terminal posterior.
# Version: 0.1.0 (F04-R3 il1b y C2)
# Version: 0.1.0 (F04-R3 C2)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import uuid

import pytest

import f05_01_helpers as fh
import f05_06_m5_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_prevision as ejp
from app.api.dto_edicion import IntencionCorregirPago
from app.api.dto_prevision import IntencionReabrir
from app.api.dto_vs01 import IntencionGastoPagado
from app.api.ejecucion_correccion import corregir_pago_http
from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
from app.repositories import correccion_tesoreria_repository as repo_ct
from app.repositories import previsiones_repository as repo_prev
from test_205_f05_06_m5_concurrencia_serial import OK, ORDENES, PT_OP17, Paso, correr, ctx  # arnes comun

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R3_CONCURRENCIA=1)")

PT_REABRIR = (repo_prev, "tocar_prevision")         # reabrir: regla FU -> UPDATE de la prevision
PT_OP21P = (repo_ct, "bloquear_movimientos")         # OP-21P: ... -> reglas -> previsiones -> movimientos
FECHA_H = "2026-10-03"


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _realizar_motor(owner, pid, hecho, importe: str) -> None:
    """OP-17 de motor (fixture): vinculo PARCIAL del hecho y marcar REALIZADA.

    «Ya lo registre» (HTTP) exige vincular TODA la porcion libre del hecho, asi
    que el reparto de un hecho entre dos previsiones no se produce hoy por la
    API; es estado representable (motor, RV3) y es el punto de partida que
    pide C2. Las operaciones en carrera si son las rutas expuestas.
    """
    from app.core.modelos_prevision import DatosVinculo
    from app.services.previsiones_service import PrevisionesService

    PrevisionesService(fh.unidad()).vincular_realidad(
        ctx(owner), prevision_id=pid, row_version_esperada=m.version(owner, pid),
        datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho, importe_asignado=decimal.Decimal(importe),
                           marcar_realizada=True),
        uuid_sucesor=uuid.uuid4())


def _escenario():
    """Dos reglas RODANTE; sus cabezas P1 (40) y P2 (60) realizadas por el MISMO hecho H (100)."""
    owner, _actor, cli, cta, _ahorro = m.entorno()
    r1, p1 = m.rodante(owner, "Seguro coche", cuenta_salida=cta, desde="2026-10-01", importe="40.00")
    r2, p2 = m.rodante(owner, "Seguro hogar", cuenta_salida=cta, desde="2026-10-01", importe="60.00")
    hecho = m.x.gasto(cli, cta, fecha=FECHA_H, importe="100.00")
    for pid, importe in ((p1, "40.00"), (p2, "60.00")):
        _realizar_motor(owner, pid, hecho, importe)
    s1 = [p for p, e, _ in m.previsiones_de_regla(owner, r1) if e == "ABIERTA"][0]
    s2 = [p for p, e, _ in m.previsiones_de_regla(owner, r2) if e == "ABIERTA"][0]
    assert (m.estado(owner, p1), m.estado(owner, p2)) == ("REALIZADA", "REALIZADA")
    return {"owner": owner, "cli": cli, "cta": cta, "r1": r1, "r2": r2, "p1": p1, "p2": p2, "s1": s1, "s2": s2,
            "hecho": hecho}


def reabrir(e, cabeza: str, sucesor: str):
    owner = e["owner"]
    v, sv = m.version(owner, e[cabeza]), m.version(owner, e[sucesor])
    pid = e[cabeza]
    return lambda: ejp.reabrir(fh.unidad(), ctx(owner), pid, IntencionReabrir(
        intencion_id=uuid.uuid4(), row_version=v, motivo="la marqué por error", sucesor_row_version=sv))


def op22_realizando_s1(e):
    owner = e["owner"]
    cuerpo = h.intencion(e["cta"], importe="40.00", fecha_hecho="2026-10-08")
    cuerpo["prevision"] = {"prevision_id": str(e["s1"]), "row_version": m.version(owner, e["s1"]),
                           "marcar_realizada": True}
    i = IntencionGastoPagado(**cuerpo)
    e["op22_intencion"] = i.intencion_id
    return lambda: registrar_gasto_pagado(fh.unidad(), ctx(owner), i, m.x.reloj())


def op21p_fecha(e):
    owner, hecho = e["owner"], e["hecho"]
    v = m.uno(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0]
    mv = m.uno(owner, "SELECT mt.row_version FROM gapto.hecho_movimientos_tesoreria hm JOIN "
                      "gapto.movimientos_tesoreria mt ON mt.id = hm.movimiento_tesoreria_id WHERE hm.hecho_id = %s",
               (hecho,))[0]
    i = IntencionCorregirPago(intencion_id=uuid.uuid4(), row_version=v, movimiento_row_version=mv,
                              motivo="fecha mal elegida", error_de_registro=True, fecha=dt.date(2026, 10, 2))
    return lambda: corregir_pago_http(fh.unidad(), ctx(owner), hecho, i)


def huella(e) -> dict:
    """Estado semantico del escenario, sin identificadores (comparable entre gemelos)."""
    owner = e["owner"]
    datos = {
        "cadena_r1": [(est, str(f)) for _, est, f in m.previsiones_de_regla(owner, e["r1"])],
        "cadena_r2": [(est, str(f)) for _, est, f in m.previsiones_de_regla(owner, e["r2"])],
        "vinculos_h": sorted(str(x[0]) for x in m.leer(owner, "SELECT importe_asignado FROM gapto.prevision_hechos "
                                                              "WHERE hecho_id = %s", (e["hecho"],))),
        "fecha_h": str(m.uno(owner, "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
                             (e["hecho"],))[0]),
        "hechos": m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros")[0],
    }
    if "op22_intencion" in e:
        datos["op22_hecho"] = m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                                    (e["op22_intencion"],))[0]
    return datos


def _codigo(fn) -> str:
    p = Paso("SERIAL", fn)
    p.run()
    return p.codigo


def serial(construir, orden: str) -> dict:
    """Los mismos dos pasos, uno detras de otro, sobre un escenario gemelo."""
    e = _escenario()
    (na, fa, _), (nb, fb, _) = construir(e)
    primero, segundo = ((na, fa), (nb, fb)) if orden == "A-primero" else ((nb, fb), (na, fa))
    codigos = {primero[0]: _codigo(primero[1])}
    codigos[segundo[0]] = _codigo(segundo[1])
    return {"codigos": codigos, "huella": huella(e)}


def desenlace(codigo: str) -> str:
    return OK if codigo == OK else "RECHAZO"


def c2(monkeypatch, caplog, nombre: str, orden: str, construir) -> dict:
    ref = serial(construir, orden)
    e = _escenario()
    a, b = construir(e)
    tr = correr(monkeypatch, caplog, nombre, orden, a, b)  # nadie colgado, 0 40P01, 0 deadlocks
    tr["huella"] = huella(e)
    tr["serial"] = ref
    evidencia(f"{nombre}_{orden}", tr)
    assert {k: desenlace(tr[k]) for k in ref["codigos"]} == {k: desenlace(v) for k, v in ref["codigos"].items()}, tr
    assert tr["huella"] == ref["huella"], tr
    return tr


@pytest.mark.parametrize("orden", ORDENES)
def test_c2a_reabrir_frente_a_reabrir_dos_reglas_del_mismo_hecho(monkeypatch, caplog, orden):
    def construir(e):
        return (("A", reabrir(e, "p1", "s1"), PT_REABRIR), ("B", reabrir(e, "p2", "s2"), PT_REABRIR))

    tr = c2(monkeypatch, caplog, "C2a", orden, construir)
    assert (tr["A"], tr["B"]) == (OK, OK), tr
    assert tr["segundo_bloqueado"] is False, tr  # reglas y previsiones disjuntas: no se esperan
    for cadena in ("cadena_r1", "cadena_r2"):
        assert [est for est, _ in tr["huella"][cadena]] == ["ABIERTA", "CANCELADA"], tr
    assert tr["huella"]["vinculos_h"] == ["40.0000", "60.0000"], tr  # los vinculos se conservan


@pytest.mark.parametrize("orden", ORDENES)
def test_c2b_reabrir_frente_a_op22_realizando_el_sucesor(monkeypatch, caplog, orden):
    def construir(e):
        return (("A", reabrir(e, "p1", "s1"), PT_REABRIR), ("B", op22_realizando_s1(e), PT_OP17))

    tr = c2(monkeypatch, caplog, "C2b", orden, construir)
    if orden == "A-primero":  # reabrir cancela S1; OP-22 espera la regla y la ve desfasada: nada se escribe
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["ABIERTA", "CANCELADA"], tr
        assert tr["huella"]["op22_hecho"] == 0, tr
    else:  # OP-22 realiza S1 (nace S1'); «Reabrir» espera la regla y despues entra: C2-H1 (igual que en serie)
        assert (tr["B"], tr["A"]) == (OK, OK), tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["ABIERTA", "REALIZADA", "CANCELADA"], tr
        assert tr["huella"]["op22_hecho"] == 1, tr


@pytest.mark.parametrize("orden", ORDENES)
def test_c2c_reabrir_frente_a_op21p_sobre_el_hecho(monkeypatch, caplog, orden):
    def construir(e):
        return (("A", reabrir(e, "p1", "s1"), PT_REABRIR), ("B", op21p_fecha(e), PT_OP21P))

    tr = c2(monkeypatch, caplog, "C2c", orden, construir)
    assert tr["B"] == OK and tr["huella"]["fecha_h"] == "2026-10-02", tr
    assert tr["huella"]["vinculos_h"] == ["40.0000", "60.0000"], tr
    if orden == "A-primero":  # reabrir confirma; OP-21P espera la regla R1 con el hecho tomado y entra
        assert tr["A"] == OK and [est for est, _ in tr["huella"]["cadena_r1"]] == ["ABIERTA", "CANCELADA"], tr
    else:  # OP-21P propaga la fecha y toca P1: «Reabrir» espera la regla y la ve desfasada
        assert tr["A"] == "VERSION_DESFASADA", tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["REALIZADA", "ABIERTA"], tr


# ================================================================== 3. hallazgo C2-H1 (serial)
@pytest.mark.xfail(strict=True, reason="C2-H1 (F04-R3, documentado sin corregir): «Reabrir» P1 se admite con el "
                                       "tramo posterior S1 ya REALIZADO; F04-D024.9 pide TRAMO_RODANTE_REQUIERE_REVISION")
def test_c2_h1_reabrir_con_un_tramo_posterior_realizado():
    e = _escenario()
    owner = e["owner"]
    assert _codigo(op22_realizando_s1(e)) == OK  # S1 REALIZADA; nace su sucesor S1' ABIERTA
    cabeza = [p for p, est, _ in m.previsiones_de_regla(owner, e["r1"]) if est == "ABIERTA"][0]
    pid, v, sv = e["p1"], m.version(owner, e["p1"]), m.version(owner, cabeza)  # lo que daria la lectura
    codigo = _codigo(lambda: ejp.reabrir(fh.unidad(), ctx(owner), pid, IntencionReabrir(
        intencion_id=uuid.uuid4(), row_version=v, motivo="la marqué por error", sucesor_row_version=sv)))
    evidencia("C2-H1_serial", {"codigo": codigo, "huella": huella(e)})
    assert codigo == "TRAMO_RODANTE_REQUIERE_REVISION", huella(e)
