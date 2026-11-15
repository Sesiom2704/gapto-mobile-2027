# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_282_f06_t2_cat_viv_concurrencia_serial.py
# Ruta: tests/api/test_282_f06_t2_cat_viv_concurrencia_serial.py
# Descripcion: T2-F06 CAT-VIV N1 · bateria SERIAL y determinista con COMMIT real (WM 0.33 §13.3.7; mandato v1.1 §9.3;
#   Q-CV-12), FUERA de la suite general: solo con GAPTO_CATVIV_CONCURRENCIA=1 (base desechable). Barreras externas
#   que retienen el recurso que los dos necesitan (la fila de la categoria FOR UPDATE o la entidad FOR NO KEY UPDATE),
#   pg_locks y pg_stat_database.deadlocks; JSON por caso si GAPTO_CATVIV_EVIDENCIA apunta a una carpeta. Sin 40P01.
#     S-CV-01 marcar || registrar sin propiedad: marcar primero -> CATEGORIA_EXIGE_PROPIEDAD sin escrituras;
#             registrar primero (toma el FOR SHARE) -> marcar espera, el hecho queda sin propiedad y no se reinterpreta.
#     S-CV-02 desmarcar || registrar con propiedad: los dos 200 en los dos ordenes; el hecho con su AFECTA_A.
#     S-CV-03 marcar || confirmar una prevision que crea el hecho: marcar primero -> 422 y la prevision ABIERTA;
#             confirmar primero -> REALIZADA sin propiedad.
#     S-CV-04 VS-01 con propiedad || C-PROP-03 (cambio de titularidad en la fecha): C-PROP-03 primero ->
#             ATRIBUCION_PROPUESTA_DESFASADA; VS-01 primero -> los dos 200.
#     S-CV-05 marcar || marcar con la misma version (advisory CATEGORIAS): uno 200 y el otro VERSION_DESFASADA.
#     S-CV-06 VS-01 con propiedad || C-MEJ-01 sobre la misma propiedad: los dos 200, sin interbloqueo (§2.4.5).
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import uuid

import psycopg
import pytest

import f05_05_helpers as x5
import f05_06_m5_helpers as m5
import f06_01_b1_helpers as b
import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from test_237_f06_01_b1r_intencion_concurrente_serial import (BarreraNK, cliente, deadlocks, en_hilo,
                                                              esperar_bloqueado, foto_locks)

ORDENES = ["A-primero", "B-primero"]
FECHA = "2026-05-15"
GASTO = "/v1/intenciones/gasto-pagado"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_CATVIV_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_CATVIV_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_CATVIV_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


class BarreraCategoria:
    """Conexion de control que retiene la fila de la categoria FOR UPDATE hasta `soltar`."""

    def __init__(self, categoria_id):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        self.c.execute("SELECT 1 FROM gapto.categorias_financieras WHERE id = %s FOR UPDATE", (categoria_id,))

    def soltar(self):
        self.c.commit()
        self.c.close()


def _correr(fa, fb, barrera):
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado("b1r_A")
        tb, rb = en_hilo(fb)
        esperar_bloqueado("b1r_B")
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
    return r.status_code, j.get("codigo")


def _comun(traza, datos):
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert traza["esperas"], datos                                                       # hubo espera real


def _version(lab, cat=None) -> int:
    return lab.sql("SELECT row_version FROM gapto.categorias_financieras WHERE id = %s", (cat or lab.cat,))[0][0]


def _marcar_cuerpo(valor: bool, version: int) -> dict:
    return {"asociada_vivienda": valor, "row_version": version}


def _vs01(lab, *, propiedad=None, fecha=FECHA, prevision=None) -> dict:
    c = h.intencion(lab.c1, importe="120.00", fecha_hecho=fecha, concepto="Comunidad", atribucion="SIN_INDICAR",
                    financiacion=h.NO_DETERMINADA, categoria=x5._cat(lab.cat))
    if propiedad is not None:
        c["propiedad"] = propiedad
    if prevision is not None:
        c["prevision"] = prevision
    return c


def _bloque(lab, fecha=FECHA) -> dict:
    return {"propiedad_id": str(lab.pid), "clase": "GASTO_CORRIENTE",
            "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": lab.vista(fecha)},
            "pagos": [{"pagador": "YO", "cuenta_id": str(lab.c1), "importe": "120.00"}],
            "saldos": [{"actor_id": lab.ta, "sentido": "ME_DEBE", "importe": "60.00"}],
            "posiciones_confirmadas": [{"actor_id": lab.ta, "tipo": "DERECHO_COBRO", "importe": "60.00"}]}


def _marca(lab) -> bool:
    return lab.sql("SELECT asociada_vivienda FROM gapto.categorias_financieras WHERE id = %s", (lab.cat,))[0][0]


def _afecta_a(lab, iid) -> int:
    return lab.sql("SELECT count(*) FROM gapto.hecho_entidades WHERE hecho_id = %s AND tipo_relacion = 'AFECTA_A'",
                   (iid,))[0][0]


def _n_hechos(lab, iid) -> int:
    return lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (iid,))[0][0]


def _f_post(cli, ruta, cuerpo):
    return lambda: cli.post(ruta, json=cuerpo, headers=h.AUTH)


# ================================================================== S-CV-01
@pytest.mark.parametrize("orden", ORDENES)
def test_s_cv_01_marcar_frente_a_registrar_sin_propiedad(orden):
    lab = b3.Lab()
    cuerpo = _vs01(lab)
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    marcar = lambda cli: _f_post(cli, f"/v1/categorias/{lab.cat}/vivienda", _marcar_cuerpo(True, _version(lab)))  # noqa: E731
    registrar = lambda cli: _f_post(cli, GASTO, cuerpo)                                    # noqa: E731
    barrera = BarreraCategoria(lab.cat)
    if orden == "A-primero":
        ra, rb, traza = _correr(marcar(ca), registrar(cb), barrera)
        m, g = _http(ra), _http(rb)
        esperado = ((200, None), (422, "CATEGORIA_EXIGE_PROPIEDAD"), 0)
    else:
        ra, rb, traza = _correr(registrar(ca), marcar(cb), barrera)
        g, m = _http(ra), _http(rb)
        esperado = ((200, None), (200, None), 1)
    datos = {"orden": orden, "marcar": m, "registrar": g, **traza}
    evidencia(f"S-CV-01_marcar_registrar_{orden}", datos)
    _comun(traza, datos)
    assert (m, g, _n_hechos(lab, cuerpo["intencion_id"])) == esperado, datos
    assert _marca(lab) is True and _afecta_a(lab, cuerpo["intencion_id"]) == 0          # no se reinterpreta


# ================================================================== S-CV-02
@pytest.mark.parametrize("orden", ORDENES)
def test_s_cv_02_desmarcar_frente_a_registrar_con_propiedad(orden):
    lab = b3.Lab()
    r = lab.cli.post(f"/v1/categorias/{lab.cat}/vivienda", json=_marcar_cuerpo(True, _version(lab)), headers=h.AUTH)
    assert r.status_code == 200, r.text
    cuerpo = _vs01(lab, propiedad=_bloque(lab))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    desmarcar = lambda cli: _f_post(cli, f"/v1/categorias/{lab.cat}/vivienda", _marcar_cuerpo(False, _version(lab)))  # noqa: E731
    registrar = lambda cli: _f_post(cli, GASTO, cuerpo)                                    # noqa: E731
    barrera = BarreraCategoria(lab.cat)
    if orden == "A-primero":
        ra, rb, traza = _correr(desmarcar(ca), registrar(cb), barrera)
        d, g = _http(ra), _http(rb)
    else:
        ra, rb, traza = _correr(registrar(ca), desmarcar(cb), barrera)
        g, d = _http(ra), _http(rb)
    datos = {"orden": orden, "desmarcar": d, "registrar": g, **traza}
    evidencia(f"S-CV-02_desmarcar_registrar_{orden}", datos)
    _comun(traza, datos)
    assert (d, g) == ((200, None), (200, None)), datos
    assert _marca(lab) is False and _afecta_a(lab, cuerpo["intencion_id"]) == 1


# ================================================================== S-CV-03
@pytest.mark.parametrize("orden", ORDENES)
def test_s_cv_03_marcar_frente_a_confirmar_prevision(orden):
    lab = b3.Lab()
    prev = m5.prevision(lab.owner, "Comunidad", desde=FECHA, importe="120.00", categoria=lab.cat,
                        cuenta_salida=lab.c1)
    cuerpo = _vs01(lab, prevision=m5.bloque(lab.owner, prev, True))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    marcar = lambda cli: _f_post(cli, f"/v1/categorias/{lab.cat}/vivienda", _marcar_cuerpo(True, _version(lab)))  # noqa: E731
    confirmar = lambda cli: _f_post(cli, GASTO, cuerpo)                                    # noqa: E731
    barrera = BarreraCategoria(lab.cat)
    if orden == "A-primero":
        ra, rb, traza = _correr(marcar(ca), confirmar(cb), barrera)
        m, g = _http(ra), _http(rb)
        esperado = ((200, None), (422, "CATEGORIA_EXIGE_PROPIEDAD"), "ABIERTA")
    else:
        ra, rb, traza = _correr(confirmar(ca), marcar(cb), barrera)
        g, m = _http(ra), _http(rb)
        esperado = ((200, None), (200, None), "REALIZADA")
    datos = {"orden": orden, "marcar": m, "confirmar": g, **traza}
    evidencia(f"S-CV-03_marcar_prevision_{orden}", datos)
    _comun(traza, datos)
    assert (m, g, m5.estado(lab.owner, prev)) == esperado, datos
    assert _afecta_a(lab, cuerpo["intencion_id"]) == 0


# ================================================================== S-CV-04
@pytest.mark.parametrize("orden", ORDENES)
def test_s_cv_04_vs01_con_propiedad_frente_a_cambio_de_titularidad(orden):
    lab = b3.Lab(cambio=False)
    cuerpo = _vs01(lab, propiedad=_bloque(lab, b.HOY), fecha=b.HOY)
    cambio = b.cambio(b.leer(lab.cli, lab.pid), b.solo_mia(desde=b.HOY))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_g = lambda cli: _f_post(cli, GASTO, cuerpo)                                          # noqa: E731
    f_t = lambda cli: lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/titularidad", cambio)  # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":
        ra, rb, traza = _correr(f_t(ca), f_g(cb), barrera)
        t, g = _http(ra), _http(rb)
        esperado = (200, (409, "ATRIBUCION_PROPUESTA_DESFASADA"), 0)
    else:
        ra, rb, traza = _correr(f_g(ca), f_t(cb), barrera)
        g, t = _http(ra), _http(rb)
        esperado = (200, (200, None), 1)
    datos = {"orden": orden, "titularidad": t, "registrar": g, **traza}
    evidencia(f"S-CV-04_vs01_cprop03_{orden}", datos)
    _comun(traza, datos)
    assert (t[0], g, _n_hechos(lab, cuerpo["intencion_id"])) == esperado, datos


# ================================================================== S-CV-05
def test_s_cv_05_marcar_frente_a_marcar_misma_version():
    lab = b3.Lab()
    v = _version(lab)
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraCategoria(lab.cat)
    ra, rb, traza = _correr(_f_post(ca, f"/v1/categorias/{lab.cat}/vivienda", _marcar_cuerpo(True, v)),
                            _f_post(cb, f"/v1/categorias/{lab.cat}/vivienda", _marcar_cuerpo(False, v)), barrera)
    a, bb = _http(ra), _http(rb)
    datos = {"A": a, "B": bb, **traza}
    evidencia("S-CV-05_marcar_marcar", datos)
    _comun(traza, datos)
    assert (a, bb) == ((200, None), (409, "VERSION_DESFASADA")), datos
    assert _marca(lab) is True and _version(lab) == v + 1


# ================================================================== S-CV-06
@pytest.mark.parametrize("orden", ORDENES)
def test_s_cv_06_vs01_con_propiedad_frente_a_c_mej_01(orden):
    lab = b3.Lab()
    vs01 = _vs01(lab, propiedad=_bloque(lab))
    cmej = lab.cuerpo(clase="REPARACION")
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_v = lambda cli: _f_post(cli, GASTO, vs01)                                            # noqa: E731
    f_c = lambda cli: lambda: lab.registrar(cmej, cli)                                     # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":
        ra, rb, traza = _correr(f_v(ca), f_c(cb), barrera)
    else:
        ra, rb, traza = _correr(f_c(ca), f_v(cb), barrera)
    datos = {"orden": orden, "A": _http(ra), "B": _http(rb), **traza}
    evidencia(f"S-CV-06_vs01_cmej01_{orden}", datos)
    _comun(traza, datos)
    assert (datos["A"][0], datos["B"][0]) == (200, 200), datos
    assert _afecta_a(lab, vs01["intencion_id"]) == 1 and _n_hechos(lab, cmej["intencion_id"]) == 1
