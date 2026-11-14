# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_263_f06_t2_pag_concurrencia_serial.py
# Ruta: tests/api/test_263_f06_t2_pag_concurrencia_serial.py
# Descripcion: T2-F06 · PAG N1 · bateria SERIAL y determinista con COMMIT real (WM 0.33 §13.3.7; mandato PAG §9.2), FUERA de
#   la suite general: solo con GAPTO_PAG_CONCURRENCIA=1 (base desechable). Barreras externas que retienen el recurso que
#   el escenario necesita; pg_locks y pg_stat_database.deadlocks; JSON por caso si GAPTO_PAG_EVIDENCIA apunta a una
#   carpeta. Sin 40P01 en ningun caso.
#     C-1 C-MEJ-01 v2 || C-PROP-03 (titularidad en la fecha del hecho): C-PROP-03 primero -> ATRIBUCION_PROPUESTA_
#         DESFASADA; C-MEJ-01 v2 primero -> los dos 200.
#     C-2 C-MEJ-01 v2 || C-MEJ-01 v2 con la misma intencion (0P raiz de OP-22): una escritura y un idempotente.
#     C-3 C-MEJ-01 v2 (P3 con LE_DEBO) || cambio del tercero pagador a EMPRESA (terceros FOR SHARE): el cambio primero ->
#         ENTRADA_INVALIDA sin escrituras; C-MEJ-01 primero -> los dos 200 (la posicion se crea frente a la PERSONA).
#     C-4 C-MEJ-01 v2 (P1) || desactivar PAGAR_GASTO de la cuenta de mi pago: la capacidad primero -> CUENTA_DESCONOCIDA
#         sin escrituras; C-MEJ-01 primero -> los dos 200.
#     C-5 C-MEJ-01 v2 || C-PROP-03bis de B1-R (adelanto del inicio): C-PROP-03bis primero -> el gasto entra con la
#         titularidad corregida; C-MEJ-01 primero (sin titularidad en la fecha) -> TITULARIDAD_NO_DISPONIBLE_EN_FECHA.
#     C-6 OP-12B sobre la obligacion de P3 || C-MEJ-03 sobre el mismo hecho: C-MEJ-03 se rechaza sin escrituras en los
#         dos ordenes y OP-12B paga. No comparten recurso (C-MEJ-03 cae en la guarda 2bis antes de esperar): carrera sin
#         barrera, con el estado final y pg_stat_database.deadlocks como oraculo.
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import uuid

import psycopg
import pytest

import f05_05_helpers as x5
import f05_06_m3_helpers as m3
import f06_01_b1_helpers as b
import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from test_237_f06_01_b1r_intencion_concurrente_serial import (BarreraNK, Retener, cliente, deadlocks, en_hilo,
                                                              esperar_bloqueado, foto_locks)
from test_257_f06_01_b3_concurrencia_serial import BarreraRaiz

ORDENES = ["A-primero", "B-primero"]
FECHA = "2026-05-15"
TIPO = {"ME_DEBE": "DERECHO_COBRO", "LE_DEBO": "OBLIGACION_PAGO"}

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_PAG_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_PAG_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_PAG_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def _correr(fa, fb, barrera, nombre_a="b1r_A", nombre_b="b1r_B"):
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado(nombre_a)
        tb, rb = en_hilo(fb)
        esperar_bloqueado(nombre_b)
        locks = foto_locks()
    finally:
        barrera.soltar()
    ta.join(90)
    tb.join(90)
    vivos = [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]
    return ra, rb, {"deadlocks_nuevos": deadlocks() - d0, "vivos": vivos, "pg_locks": locks,
                    "esperas": [f for f in locks if not f[3]]}


def _http(salida: dict):
    assert "e" not in salida, salida
    r = salida["r"]
    j = r.json()
    return r.status_code, j.get("codigo"), j.get("idempotente")


def _peticion(lab, *, pagos, saldos, fecha=FECHA, iid=None, atribucion=None) -> dict:
    saldos = [{k: str(v) for k, v in x.items()} for x in saldos]
    return {"intencion_id": str(iid or uuid.uuid4()), "propiedad_id": str(lab.pid), "clase": "MEJORA", "importe": "8000.00",
            "fecha_hecho": fecha, "nota": "Cocina",
            "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": lab.vista(fecha)},
            "pagos": [{k: str(v) for k, v in x.items()} for x in pagos], "saldos": saldos,
            "posiciones_confirmadas": [{"actor_id": s["actor_id"], "tipo": TIPO[s["sentido"]], "importe": s["importe"]}
                                       for s in saldos if s["sentido"] != "NADA"]}


def _p3(lab, **kw):
    return _peticion(lab, pagos=[{"pagador": lab.ta, "importe": "8000.00"}],
                     saldos=[{"actor_id": lab.ta, "sentido": "LE_DEBO", "importe": "4000.00"}], **kw)


def _p1(lab, **kw):
    return _peticion(lab, pagos=[{"pagador": "YO", "cuenta_id": lab.c1, "importe": "8000.00"}],
                     saldos=[{"actor_id": lab.ta, "sentido": "ME_DEBE", "importe": "4000.00"}], **kw)


def _n_hechos(lab, iid) -> int:
    return lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (iid,))[0][0]


def _comun(traza, datos):
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert traza["esperas"], datos                                                       # hubo espera real


# ================================================================== C-1
@pytest.mark.parametrize("orden", ORDENES)
def test_c1_cmej01_v2_frente_a_cambio_de_titularidad(orden):
    lab = b3.Lab(cambio=False)
    cuerpo = _p3(lab, fecha=b.HOY)
    cambio = b.cambio(b.leer(lab.cli, lab.pid), b.solo_mia(desde=b.HOY))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    f_g = lambda cli: lambda: lab.registrar(cuerpo, cli)                                           # noqa: E731
    f_t = lambda cli: lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/titularidad", cambio)        # noqa: E731
    if orden == "A-primero":
        ra, rb, traza = _correr(f_t(ca), f_g(cb), barrera)
        tit, gasto = _http(ra), _http(rb)
        esperado = (200, (409, "ATRIBUCION_PROPUESTA_DESFASADA", None))
    else:
        ra, rb, traza = _correr(f_g(ca), f_t(cb), barrera)
        gasto, tit = _http(ra), _http(rb)
        esperado = (200, (200, None, False))
    datos = {"orden": orden, "gasto": gasto, "titularidad": tit, **traza}
    evidencia(f"C1_CMEJ01v2_CPROP03_{orden}", datos)
    _comun(traza, datos)
    assert (tit[0], gasto) == esperado, datos
    assert _n_hechos(lab, cuerpo["intencion_id"]) == (0 if orden == "A-primero" else 1)


# ================================================================== C-2
def test_c2_dos_cmej01_v2_con_la_misma_intencion():
    lab = b3.Lab()
    cuerpo = _p3(lab)
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraRaiz(cuerpo["intencion_id"])
    ra, rb, traza = _correr(lambda: lab.registrar(cuerpo, ca), lambda: lab.registrar(cuerpo, cb), barrera)
    a, bb = _http(ra), _http(rb)
    datos = {"a": a, "b": bb, **traza}
    evidencia("C2_misma_intencion", datos)
    _comun(traza, datos)
    assert sorted([a, bb], key=str) == sorted([(200, None, False), (200, None, True)], key=str), datos
    assert _n_hechos(lab, cuerpo["intencion_id"]) == 1
    assert len(m3.posiciones(lab.owner, cuerpo["intencion_id"])) == 1


# ================================================================== C-3
@pytest.mark.parametrize("orden", ORDENES)
def test_c3_cmej01_v2_p3_frente_al_cambio_del_tercero_pagador(orden):
    lab = b3.Lab(cambio=False)
    cuerpo = _p3(lab, fecha=b.HOY)
    tercero = next(x for x in lab.cli.get("/v1/terceros", headers=h.AUTH).json()["terceros"] if x["id"] == str(lab.t))
    edicion = {"row_version": tercero["row_version"], "nombre": tercero["nombre"], "naturaleza": "EMPRESA"}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = Retener("SELECT 1 FROM gapto.terceros WHERE id = %s FOR UPDATE", lab.t)
    f_g = lambda cli: lambda: lab.registrar(cuerpo, cli)                                                    # noqa: E731
    f_e = lambda cli: lambda: cli.post(f"/v1/terceros/{lab.t}/editar", json=edicion, headers=h.AUTH)       # noqa: E731
    if orden == "A-primero":
        ra, rb, traza = _correr(f_e(ca), f_g(cb), barrera)
        ed, gasto = _http(ra), _http(rb)
    else:
        ra, rb, traza = _correr(f_g(ca), f_e(cb), barrera)
        gasto, ed = _http(ra), _http(rb)
    datos = {"orden": orden, "gasto": gasto, "edicion": ed, **traza}
    evidencia(f"C3_CMEJ01v2_P3_tercero_{orden}", datos)
    _comun(traza, datos)
    if orden == "A-primero" and ed[0] == 200:                     # ya es EMPRESA: nunca una posicion frente a ella
        assert gasto[:2] == (422, "ENTRADA_INVALIDA") and _n_hechos(lab, cuerpo["intencion_id"]) == 0, datos
    else:
        assert gasto == (200, None, False), datos
        assert [p[0] for p in m3.posiciones(lab.owner, cuerpo["intencion_id"])] == ["OBLIGACION_PAGO"]


# ================================================================== C-4
@pytest.mark.parametrize("orden", ORDENES)
def test_c4_cmej01_v2_p1_frente_a_desactivar_pagar_gasto(orden):
    lab = b3.Lab(cambio=False)
    cuerpo = _p1(lab, fecha=b.HOY)
    version = lab.sql("SELECT row_version FROM gapto.cuentas WHERE id = %s", (lab.c1,))[0][0]
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = Retener("SELECT 1 FROM gapto.cuentas WHERE id = %s FOR UPDATE", lab.c1)
    f_g = lambda cli: lambda: lab.registrar(cuerpo, cli)                                                    # noqa: E731
    f_c = lambda cli: lambda: cli.post(f"/v1/cuentas/{lab.c1}/capacidades/PAGAR_GASTO/desactivar",          # noqa: E731
                                       json={"row_version": version}, headers=h.AUTH)
    if orden == "A-primero":
        ra, rb, traza = _correr(f_c(ca), f_g(cb), barrera)
        cap, gasto = _http(ra), _http(rb)
    else:
        ra, rb, traza = _correr(f_g(ca), f_c(cb), barrera)
        gasto, cap = _http(ra), _http(rb)
    datos = {"orden": orden, "gasto": gasto, "capacidad": cap, **traza}
    evidencia(f"C4_CMEJ01v2_P1_capacidad_{orden}", datos)
    _comun(traza, datos)
    assert cap[0] == 200, datos
    if orden == "A-primero":
        assert gasto[0] in (409, 422) and gasto[1] == "CUENTA_DESCONOCIDA", datos
        assert _n_hechos(lab, cuerpo["intencion_id"]) == 0
    else:
        assert gasto == (200, None, False), datos


# ================================================================== C-5
@pytest.mark.parametrize("orden", ORDENES)
def test_c5_cmej01_v2_frente_a_corregir_el_inicio_de_b1r(orden):
    import test_261_f06_t2_b1r_concurrencia_serial as t261
    lab = t261.Lab(adquisicion=None)
    partes = sorted(lab.detalle()["inicio_titularidad"]["primera_version"], key=lambda p: p["actor_id"])
    fecha = "2026-05-15"
    propuesta = {"criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": fecha, "partes": partes}
    otro = next(p["actor_id"] for p in partes if p["actor_id"] != lab.yo)
    gasto = _peticion(lab, pagos=[{"pagador": otro, "importe": "8000.00"}], saldos=[
        {"actor_id": otro, "sentido": "NADA"}], fecha=fecha,
        atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": propuesta})
    corregir = lab.peticion("2026-01-01")
    ca, cb = t261.cliente(lab.owner, "b1r_A"), t261.cliente(lab.owner, "b1r_B")
    f_i = lambda cli: t261._post(cli, t261.RUTA.format(lab.pid), corregir)                              # noqa: E731
    f_g = lambda cli: lambda: lab.registrar(gasto, cli)                                                  # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":
        ra, rb, traza = _correr(f_i(ca), f_g(cb), barrera)
        inicio, g = _http(ra), _http(rb)
        esperado_g = (200, None)
    else:
        ra, rb, traza = _correr(f_g(ca), f_i(cb), barrera)
        g, inicio = _http(ra), _http(rb)
        esperado_g = (422, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA")
    datos = {"orden": orden, "corregir_inicio": inicio, "c_mej_01_v2": g, **traza}
    evidencia(f"C5_CMEJ01v2_inicio_{orden}", datos)
    _comun(traza, datos)
    assert inicio == (200, None, False), datos
    assert (g[0], g[1]) == esperado_g, datos


# ================================================================== C-6
@pytest.mark.parametrize("orden", ["op12b-primero", "cmej03-primero"])
def test_c6_op12b_de_la_obligacion_frente_a_cmej03(orden):
    lab = b3.Lab()
    cuerpo = _p3(lab)
    assert lab.registrar(cuerpo).status_code == 200
    hid = cuerpo["intencion_id"]
    entidad = m3.entidad_de_posicion(lab.owner, hid)
    g = lab.leer_gasto(hid)
    efecto = next(e[0] for e in lab.efectos(hid) if e[1] == "VALOR_ACTIVO")
    correccion = {"intencion_id": b3.intencion_vigente(efecto), "row_version_esperada": g["row_version"],
                  "clase_nueva": "REPARACION", "motivo": "Error", "categoria_id": str(lab.cat), "presupuestable": True,
                  "comparacion_vista": lab.impacto(hid, "REPARACION", True)}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_p = lambda cli: lambda: m3.cobro(cli, entidad, lab.c1, "4000.00", fecha="2026-06-01", accion="pago")[1]  # noqa: E731
    f_c = lambda cli: lambda: lab.corregir(hid, correccion, cli=cli)                                          # noqa: E731
    efectos_antes = lab.efectos(hid)
    d0 = deadlocks()
    # No comparten recurso: C-MEJ-03 se rechaza por la guarda 2bis (dos efectos vigentes: el del gasto y el de la
    # posicion) antes de cualquier espera, y OP-12B no toca el hecho original. Sin barrera: se lanzan en el orden del
    # caso y se comprueban el resultado, la ausencia de 40P01 y el estado final.
    primero, segundo = (f_p(ca), f_c(cb)) if orden == "op12b-primero" else (f_c(ca), f_p(cb))
    ta, ra = en_hilo(primero)
    tb, rb = en_hilo(segundo)
    locks = foto_locks()
    ta.join(90)
    tb.join(90)
    pago_r, corr_r = (ra, rb) if orden == "op12b-primero" else (rb, ra)
    pago, corr = _http(pago_r), _http(corr_r)
    datos = {"orden": orden, "op12b": pago, "cmej03": corr, "deadlocks_nuevos": deadlocks() - d0, "pg_locks": locks,
             "vivos": [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]}
    evidencia(f"C6_OP12B_CMEJ03_{orden}", datos)
    assert datos["deadlocks_nuevos"] == 0 and datos["vivos"] == [], datos
    assert pago[0] == 200, datos
    assert corr[0] in (409, 422), datos
    assert [(e[0], e[1]) for e in lab.efectos(hid) if e[1] == "VALOR_ACTIVO"] == [
        (e[0], e[1]) for e in efectos_antes if e[1] == "VALOR_ACTIVO"]
