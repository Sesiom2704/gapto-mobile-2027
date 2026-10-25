# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_214_f04_r3_c2_reabrir_serial.py
# Ruta: tests/api/test_214_f04_r3_c2_reabrir_serial.py
# Descripcion: F04-R3 (F05-D050 §64.4; adenda 2 §D). Bateria SERIAL y
#   determinista de las carreras C2, FUERA de la suite general: solo con
#   GAPTO_F04R3_CONCURRENCIA=1 (evidencia JSON si GAPTO_F04R3_EVIDENCIA apunta
#   a una carpeta). COMMIT real sobre base desechable. Nunca en paralelo.
#   Solo rutas EXPUESTAS, por las funciones del adaptador HTTP. Las pruebas
#   C2-H1 sin carrera (seccion 3) son ORDINARIAS y van en la suite general.
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
#   C2-H1 (F05-D051 §65.4, AJ-F0507G2-07; CORREGIDO): con el sucesor S1 ya
#      REALIZADO (u OMITIDO) y su nueva cabeza S1' ABIERTA, «Reabrir» P1 se
#      rechaza con TRAMO_RODANTE_REQUIERE_REVISION antes de cualquier
#      escritura: el terminal INTERMEDIO S1 cuenta aunque exista una cabeza
#      abierta posterior. El rechazo conserva previsiones, vinculos, hechos y
#      tesoreria (comparacion fila a fila antes/despues). Solo se cancela el
#      sucesor abierto sin realidad cuando no existe ese avance terminal (el
#      ultimo terminal de la cadena SI se reabre). C2b B-primero pasa a ese
#      rechazo; C2b se repite GAPTO_F04R3_VUELTAS_C2 veces por orden (y C2d,
#      «Reabrir» P1 x «Omitir» S1, igual) para la serie de concurrencia.
# Version: 0.2.0 (F05-D051 paso 1: C2-H1 corregido; xfail -> prueba ordinaria;
#   casos de conservacion, terminal intermedio + cabeza abierta, cadena de
#   tres terminales, rechazo por HTTP y serie C2b/C2d en los dos ordenes)
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
from app.api.dto_prevision import IntencionOmitir, IntencionReabrir
from app.api.dto_vs01 import IntencionGastoPagado
from app.api.ejecucion_correccion import corregir_pago_http
from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
from app.repositories import correccion_tesoreria_repository as repo_ct
from app.repositories import previsiones_repository as repo_prev
from test_205_f05_06_m5_concurrencia_serial import OK, ORDENES, PT_OP17, Paso, correr, ctx  # arnes comun

# Solo las carreras quedan fuera de la suite general; las pruebas C2-H1 sin carrera son ordinarias.
concurrencia = pytest.mark.skipif(os.getenv("GAPTO_F04R3_CONCURRENCIA") != "1",
                                  reason="bateria serial fuera de la suite general (GAPTO_F04R3_CONCURRENCIA=1)")
VUELTAS_C2 = int(os.getenv("GAPTO_F04R3_VUELTAS_C2", "1"))

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


@concurrencia
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


def _vuelta(i: int) -> str:
    return f"v{i:03d}"


@concurrencia
@pytest.mark.parametrize("vuelta", [_vuelta(i) for i in range(VUELTAS_C2)])
@pytest.mark.parametrize("orden", ORDENES)
def test_c2b_reabrir_frente_a_op22_realizando_el_sucesor(monkeypatch, caplog, orden, vuelta):
    def construir(e):
        return (("A", reabrir(e, "p1", "s1"), PT_REABRIR), ("B", op22_realizando_s1(e), PT_OP17))

    tr = c2(monkeypatch, caplog, f"C2b_{vuelta}", orden, construir)
    if orden == "A-primero":  # reabrir cancela S1; OP-22 espera la regla y la ve desfasada: nada se escribe
        assert (tr["A"], tr["B"]) == (OK, "VERSION_DESFASADA"), tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["ABIERTA", "CANCELADA"], tr
        assert tr["huella"]["op22_hecho"] == 0, tr
    else:  # OP-22 realiza S1 (nace S1'); «Reabrir» espera la regla y ve el terminal intermedio S1: C2-H1 rechaza
        assert (tr["B"], tr["A"]) == (OK, "TRAMO_RODANTE_REQUIERE_REVISION"), tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["REALIZADA", "REALIZADA", "ABIERTA"], tr
        assert tr["huella"]["op22_hecho"] == 1, tr
    assert tr["huella"]["vinculos_h"] == ["40.0000", "60.0000"], tr


def omitir_s1(e):
    owner = e["owner"]
    v, pid = m.version(owner, e["s1"]), e["s1"]
    return lambda: ejp.omitir(fh.unidad(), ctx(owner), pid, IntencionOmitir(intencion_id=uuid.uuid4(), row_version=v))


@concurrencia
@pytest.mark.parametrize("vuelta", [_vuelta(i) for i in range(VUELTAS_C2)])
@pytest.mark.parametrize("orden", ORDENES)
def test_c2d_reabrir_frente_a_omitir_el_sucesor(monkeypatch, caplog, orden, vuelta):
    """C2-H1 con el tramo siguiente TERMINADO por «Omitir» (OMITIDA es terminal; nace S1')."""
    def construir(e):
        return (("A", reabrir(e, "p1", "s1"), PT_REABRIR), ("B", omitir_s1(e), PT_REABRIR))

    tr = c2(monkeypatch, caplog, f"C2d_{vuelta}", orden, construir)
    if orden == "A-primero":  # reabrir cancela S1; «Omitir» espera y la encuentra cambiada: rechazo sin efectos
        assert tr["A"] == OK and tr["B"] != OK, tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["ABIERTA", "CANCELADA"], tr
    else:  # S1 OMITIDA (nace S1'); «Reabrir» ve el terminal intermedio: rechazo sin efectos
        assert (tr["B"], tr["A"]) == (OK, "TRAMO_RODANTE_REQUIERE_REVISION"), tr
        assert [est for est, _ in tr["huella"]["cadena_r1"]] == ["REALIZADA", "OMITIDA", "ABIERTA"], tr
    assert tr["huella"]["vinculos_h"] == ["40.0000", "60.0000"], tr


@concurrencia
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


# ================================================================== 3. C2-H1 (serial, prueba ORDINARIA)
TABLAS_CONSERVADAS = ("previsiones", "prevision_hechos", "hechos_financieros", "hecho_efectos",
                      "efecto_atribuciones", "movimientos_tesoreria", "hecho_movimientos_tesoreria",
                      "transferencias", "reglas_financieras", "regla_versiones", "regla_excepciones", "auditoria")


def foto(owner) -> dict:
    """Todas las filas del owner (to_jsonb) de previsiones, vinculos, hechos, tesoreria, reglas y auditoria."""
    return {t: [f[0] for f in m.leer(owner, f"SELECT to_jsonb(x)::text FROM gapto.{t} x ORDER BY 1")]
            for t in TABLAS_CONSERVADAS}


def cabeza_abierta(e) -> uuid.UUID:
    abiertas = [p for p, est, _ in m.previsiones_de_regla(e["owner"], e["r1"]) if est == "ABIERTA"]
    assert len(abiertas) == 1, abiertas
    return abiertas[0]


def reabrir_como_la_app(e, pid) -> str:
    """Lo que enviaria la app: version de la prevision y de la cabeza abierta de la cadena."""
    owner = e["owner"]
    v = m.version(owner, pid)
    sv = m.version(owner, cabeza_abierta(e))
    return _codigo(lambda: ejp.reabrir(fh.unidad(), ctx(owner), pid, IntencionReabrir(
        intencion_id=uuid.uuid4(), row_version=v, motivo="la marqué por error", sucesor_row_version=sv)))


def rechazo_sin_efectos(e, pid) -> None:
    antes = foto(e["owner"])
    codigo = reabrir_como_la_app(e, pid)
    assert codigo == "TRAMO_RODANTE_REQUIERE_REVISION", huella(e)
    despues = foto(e["owner"])
    for t in TABLAS_CONSERVADAS:  # previsiones, vinculos, hechos y tesoreria intactos, fila a fila
        assert despues[t] == antes[t], t


def test_c2_h1_reabrir_con_un_tramo_posterior_realizado():
    """Terminal INTERMEDIO REALIZADO (S1) + cabeza ABIERTA posterior (S1'): rechazo atomico sin efectos."""
    e = _escenario()
    owner = e["owner"]
    assert _codigo(op22_realizando_s1(e)) == OK  # S1 REALIZADA; nace su sucesor S1' ABIERTA
    assert [est for _, est, _ in m.previsiones_de_regla(owner, e["r1"])] == ["REALIZADA", "REALIZADA", "ABIERTA"]
    rechazo_sin_efectos(e, e["p1"])
    evidencia("C2-H1_serial", {"huella": huella(e)})
    assert [est for _, est, _ in m.previsiones_de_regla(owner, e["r1"])] == ["REALIZADA", "REALIZADA", "ABIERTA"]
    assert huella(e)["vinculos_h"] == ["40.0000", "60.0000"]


def test_c2_h1_reabrir_con_un_tramo_posterior_omitido():
    """Terminal INTERMEDIO OMITIDO (S1) + cabeza ABIERTA posterior: el mismo rechazo sin efectos."""
    e = _escenario()
    owner = e["owner"]
    assert _codigo(omitir_s1(e)) == OK
    assert [est for _, est, _ in m.previsiones_de_regla(owner, e["r1"])] == ["REALIZADA", "OMITIDA", "ABIERTA"]
    rechazo_sin_efectos(e, e["p1"])


def _prevision_hechos(owner) -> list[str]:
    return sorted(map(str, m.leer(owner, "SELECT id, prevision_id, hecho_id, importe_asignado "
                                         "FROM gapto.prevision_hechos")))


def test_c2_h1_cadena_de_tres_terminales_solo_reabre_el_ultimo():
    """P1, S1 y S1' REALIZADAS y S1'' ABIERTA. P1 y S1 tienen terminales posteriores: rechazo. S1' es el
    ultimo terminal: se reabre y cancela S1'' (sin realidad), como antes de C2-H1."""
    e = _escenario()
    owner = e["owner"]
    assert _codigo(op22_realizando_s1(e)) == OK
    s1p = cabeza_abierta(e)
    cuerpo = h.intencion(e["cta"], importe="40.00", fecha_hecho="2026-10-09")
    cuerpo["prevision"] = {"prevision_id": str(s1p), "row_version": m.version(owner, s1p), "marcar_realizada": True}
    i = IntencionGastoPagado(**cuerpo)
    assert _codigo(lambda: registrar_gasto_pagado(fh.unidad(), ctx(owner), i, m.x.reloj())) == OK
    assert [est for _, est, _ in m.previsiones_de_regla(owner, e["r1"])] == ["REALIZADA"] * 3 + ["ABIERTA"]
    rechazo_sin_efectos(e, e["p1"])
    rechazo_sin_efectos(e, e["s1"])
    s1pp = cabeza_abierta(e)
    vinculos_antes = _prevision_hechos(owner)
    assert reabrir_como_la_app(e, s1p) == OK
    cadena = {p: est for p, est, _ in m.previsiones_de_regla(owner, e["r1"])}
    assert (cadena[e["p1"]], cadena[e["s1"]], cadena[s1p], cadena[s1pp]) == (
        "REALIZADA", "REALIZADA", "ABIERTA", "CANCELADA")
    assert _prevision_hechos(owner) == vinculos_antes


def test_c2_h1_por_http_409_sin_cambios():
    """La ruta HTTP devuelve el rechazo con su codigo (409, ya mapeado; sin cambio de contrato)."""
    e = _escenario()
    owner, cli = e["owner"], e["cli"]
    assert _codigo(op22_realizando_s1(e)) == OK
    antes = foto(owner)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(owner, e["p1"]), "motivo": "la marqué por error",
         "sucesor_row_version": m.version(owner, cabeza_abierta(e))}
    r = cli.post(f"/v1/previsiones/{e['p1']}/reabrir", json=c, headers=h.AUTH)
    assert r.status_code == 409 and r.json().get("codigo") == "TRAMO_RODANTE_REQUIERE_REVISION", r.text
    assert foto(owner) == antes
