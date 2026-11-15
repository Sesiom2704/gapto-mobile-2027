# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_284_f06_t2_a3_0352_concurrencia_serial.py
# Ruta: tests/api/test_284_f06_t2_a3_0352_concurrencia_serial.py
# Descripcion: F06 T2-F06 · A3-0352 N1 · bateria SERIAL y determinista con COMMIT real (O-A3-CONC; contrato A3-0352
#   v1.1 §10), FUERA de la suite general: solo con GAPTO_A3_CONCURRENCIA=1 (base desechable). Reutiliza las barreras de
#   B1-R/B2 (BarreraNK en la raiz; pg_locks y pg_stat_database.deadlocks) y escribe un JSON por caso si
#   GAPTO_A3_EVIDENCIA apunta a una carpeta. Sin forzar el interruptor (consumidores habilitados por el repositorio).
#     CONC-1 C-PROP-02 (borra la fecha) || C-PROP-05 (declara ADQUISICION), misma row_version, los dos ordenes:
#            el segundo espera en el NK de la raiz y responde 409 VERSION_DESFASADA; estados persistidos; reintento
#            tras releer: C-PROP-05 -> 422 COMPLETITUD_SIN_FECHA_DE_ADQUISICION sin cambios; C-PROP-02 -> 200 y
#            L-COSTE PARCIAL SIN_FECHA_DE_ADQUISICION.
#     CONC-2 C-PROP-02 (borra) || C-COMPRA-03 con declaracion, los dos ordenes: 409 VERSION_DESFASADA del segundo
#            (precedencia §3.3, nunca 422); reintento de C-COMPRA-03 con la version al dia y la fecha NULL -> 422 sin
#            escritura parcial.
#     CONC-3 L-COSTE || C-PROP-02 (borra) con barrera entre S1 y S2 de la lectura: reintento y resultado final PARCIAL
#            SIN_FECHA_DE_ADQUISICION; la lectura no toma locks de fila (pg_locks durante la barrera).
#     CONC-4 contencion inducida: lecturas L-COSTE con un escritor que sube row_version sin parar; muestras por lectura
#            acotadas por 3 y agotamientos contados (numero y frecuencia) para la clasificacion de sensibilidad.
# Version: 0.1.0 (F06 T2-F06 A3-0352 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
import time
import uuid

import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
from app.patrimonio import coste as coste_mod
from app.propiedades import repositorio as repo
from test_237_f06_01_b1r_intencion_concurrente_serial import BarreraNK, cliente, deadlocks, en_hilo, esperar_bloqueado, foto_locks

ORDENES = ["A-primero", "B-primero"]
SIN_FECHA = "COMPLETITUD_SIN_FECHA_DE_ADQUISICION"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_A3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_A3_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_A3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def _r(salida: dict):
    assert "e" not in salida, salida
    r = salida["r"]
    return r.status_code, r.json().get("codigo")


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
    ta.join(60)
    tb.join(60)
    vivos = [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]
    return ra, rb, {"deadlocks_nuevos": deadlocks() - d0, "vivos": vivos, "pg_locks": locks,
                    "esperas": [f for f in locks if not f[3]]}


def _estado(lab) -> tuple:
    return lab.sql("SELECT e.row_version, p.fecha_adquisicion::text, p.coste_adquisicion_declarado_completo, "
                   "p.coste_adquisicion_declarado_en::text FROM gapto.entidades e JOIN gapto.propiedades p "
                   "ON p.entidad_id = e.id WHERE e.id = %s", (lab.pid,))[0]


def _editar(lab, cli, version, **campos):
    return b.post(cli, f"/v1/propiedades/{lab.pid}/editar",
                  {"intencion_id": str(uuid.uuid4()), "row_version_esperada": version, **campos})


def _comprada():
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    return lab


# ================================================================== CONC-1
@pytest.mark.parametrize("orden", ORDENES)
def test_conc_1_c_prop_02_borra_la_fecha_frente_a_c_prop_05(orden):
    lab = _comprada()
    rv = lab.version()
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_borra = lambda cli: lambda: _editar(lab, cli, rv, fecha_adquisicion=None)                          # noqa: E731
    f_decl = lambda cli: lambda: lab.declarar("ADQUISICION", True, c2.CORTE, huella, version=rv, cli=cli)  # noqa: E731
    if orden == "A-primero":   # C-PROP-02 primero
        ra, rb, traza = _correr(f_borra(ca), f_decl(cb), BarreraNK(lab.pid))
        borra, decl = _r(ra), _r(rb)
    else:
        ra, rb, traza = _correr(f_decl(ca), f_borra(cb), BarreraNK(lab.pid))
        decl, borra = _r(ra), _r(rb)
    estado = _estado(lab)
    datos = {"orden": orden, "c_prop_02": borra, "c_prop_05": decl, "estado": estado, **traza}
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert any(f[0] == "b1r_B" and f[1] == "tuple" or f[0] == "b1r_B" and f[1] == "transactionid"
               for f in traza["esperas"]), datos                                       # B espera en el NK de la raiz
    if orden == "A-primero":
        assert borra == (200, None) and decl == (409, "VERSION_DESFASADA"), datos
        assert estado == (rv + 1, None, None, None), datos
        # reintento tras releer: R15-a, sin cambios
        r = lab.declarar("ADQUISICION", True, c2.CORTE, huella)
        datos["reintento"] = (r.status_code, r.json().get("codigo"))
        assert datos["reintento"] == (422, SIN_FECHA) and _estado(lab) == estado, datos
    else:
        assert decl == (200, None) and borra == (409, "VERSION_DESFASADA"), datos
        assert estado == (rv + 1, c2.ESCRITURA, True, c2.CORTE), datos
        r = _editar(lab, lab.cli, lab.version(), fecha_adquisicion=None)
        coste = lab.coste()["ADQUISICION"]
        datos["reintento"] = (r.status_code, coste["estado"], coste["motivo_estado"])
        assert datos["reintento"] == (200, "PARCIAL", "SIN_FECHA_DE_ADQUISICION"), datos
        assert _estado(lab)[1:] == (None, True, c2.CORTE), datos
    evidencia(f"CONC_1_{orden}", datos)


# ================================================================== CONC-2
@pytest.mark.parametrize("orden", ORDENES)
def test_conc_2_c_prop_02_borra_la_fecha_frente_a_c_compra_03_con_declaracion(orden):
    lab = _comprada()
    rv = lab.version()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    huella = lab.coste("2026-04-02")["ADQUISICION"]["huella_conjunto"]
    gasto = lab.peticion03(linea, version=rv, completitud={"completo": True, "fecha_corte": "2026-04-02"},
                           huella_vista=huella)
    hk = gasto["intencion_id"]
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_borra = lambda cli: lambda: _editar(lab, cli, rv, fecha_adquisicion=None)       # noqa: E731
    f_gasto = lambda cli: lambda: lab.gasto_posterior(gasto, cli)                     # noqa: E731
    if orden == "A-primero":   # C-PROP-02 primero
        ra, rb, traza = _correr(f_borra(ca), f_gasto(cb), BarreraNK(lab.pid))
        borra, g = _r(ra), _r(rb)
    else:
        ra, rb, traza = _correr(f_gasto(ca), f_borra(cb), BarreraNK(lab.pid))
        g, borra = _r(ra), _r(rb)
    hechos = lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hk,))[0][0]
    estado = _estado(lab)
    datos = {"orden": orden, "c_prop_02": borra, "c_compra_03": g, "hk": hechos, "estado": estado, **traza}
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    if orden == "A-primero":
        assert borra == (200, None) and g == (409, "VERSION_DESFASADA"), datos      # nunca 422 (precedencia §3.3)
        assert hechos == 0 and estado == (rv + 1, None, None, None), datos
        antes = c2.huella()
        r = lab.gasto_posterior(lab.peticion03(linea, completitud={"completo": True, "fecha_corte": "2026-04-02"},
                                               huella_vista=huella))
        datos["reintento"] = (r.status_code, r.json().get("codigo"))
        assert datos["reintento"] == (422, SIN_FECHA) and c2.huella() == antes, datos   # sin escritura parcial
    else:
        assert g == (200, None) and borra == (409, "VERSION_DESFASADA"), datos
        assert hechos == 1 and estado == (rv + 1, c2.ESCRITURA, True, "2026-04-02"), datos
    evidencia(f"CONC_2_{orden}", datos)


# ================================================================== CONC-3
def test_conc_3_l_coste_frente_a_c_prop_02_con_barrera_entre_s1_y_s2(monkeypatch):
    lab = _comprada()
    assert lab.declarar("ADQUISICION", True, c2.CORTE, lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]).status_code == 200
    llego, sigue = threading.Event(), threading.Event()
    real = repo.leer_coste
    llamadas = []

    def con_barrera(*a, **k):
        filas = real(*a, **k)
        llamadas.append(threading.current_thread().name)
        if threading.current_thread().name == "CONC3" and len(llamadas) == 1:
            llego.set()
            assert sigue.wait(30)
        return filas
    monkeypatch.setattr(repo, "leer_coste", con_barrera)
    salida: dict = {}

    def leer():
        try:
            salida["r"] = c2.unidad().ejecutar(c2.ctx(lab.owner), lambda s: coste_mod.leer(s, uuid.UUID(lab.pid),
                                                                                         dt.date.fromisoformat(b.HOY)))
        except Exception as e:  # pragma: no cover
            salida["e"] = repr(e)
    d0 = deadlocks()
    hilo = threading.Thread(target=leer, name="CONC3", daemon=True)
    hilo.start()
    assert llego.wait(30)
    r = _editar(lab, lab.cli, lab.version(), fecha_adquisicion=None)      # confirma mientras la lectura esta en S1-S2
    from psycopg import connect
    import vs01_api_helpers as h
    with connect(h.dsn(), autocommit=True) as c:
        locks_lectura = c.execute(
            "SELECT l.locktype, l.mode, l.relation::regclass::text FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE a.datname = current_database() AND a.pid <> pg_backend_pid() AND a.state = 'idle in transaction' "
            "AND l.locktype IN ('tuple', 'transactionid', 'advisory')").fetchall()
    sigue.set()
    hilo.join(30)
    assert "e" not in salida, salida
    adq = salida["r"]["ADQUISICION"]
    datos = {"c_prop_02": r.status_code, "resultado": [adq["estado"], adq["motivo_estado"]], "muestras_s1": len(llamadas),
             "locks_de_la_lectura": locks_lectura, "deadlocks_nuevos": deadlocks() - d0}
    evidencia("CONC_3_lcoste_frente_c_prop_02", datos)
    assert r.status_code == 200 and datos["deadlocks_nuevos"] == 0, datos
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "SIN_FECHA_DE_ADQUISICION"), datos
    assert len(llamadas) == 2 and locks_lectura == [], datos


# ================================================================== CONC-4
def test_conc_4_contencion_reintentos_acotados_y_agotamientos(monkeypatch):
    lab = _comprada()
    assert lab.declarar("ADQUISICION", True, c2.CORTE, lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]).status_code == 200
    real = repo.leer_coste
    muestras = threading.local()

    def contar(*a, **k):
        muestras.n = getattr(muestras, "n", 0) + 1
        return real(*a, **k)
    monkeypatch.setattr(repo, "leer_coste", contar)
    parar = threading.Event()
    escrituras = [0]
    escritor_cli = cliente(lab.owner, "a3_escritor")

    def escritor():
        i = 0
        while not parar.is_set():
            i += 1
            r = _editar(lab, escritor_cli, b.leer(escritor_cli, lab.pid)["row_version"], notas=f"contencion {i}")
            escrituras[0] += r.status_code == 200
    hilo = threading.Thread(target=escritor, daemon=True)
    hilo.start()
    unidad, ctx = c2.unidad(), c2.ctx(lab.owner)
    hoy = dt.date.fromisoformat(b.HOY)
    resultados, por_lectura = [], []
    t0 = time.perf_counter()
    try:
        for _ in range(200):
            muestras.n = 0
            r = unidad.ejecutar(ctx, lambda s: coste_mod.leer(s, uuid.UUID(lab.pid), hoy))
            por_lectura.append(muestras.n)
            resultados.append(r["ADQUISICION"]["motivo_estado"] or r["ADQUISICION"]["estado"])
    finally:
        parar.set()
        hilo.join(30)
    duracion = time.perf_counter() - t0
    agotadas = resultados.count("LECTURA_NO_ESTABLE")
    datos = {"lecturas": len(resultados), "escrituras_confirmadas": escrituras[0], "duracion_s": round(duracion, 3),
             "muestras_por_lectura": {str(k): por_lectura.count(k) for k in sorted(set(por_lectura))},
             "agotamientos": agotadas, "frecuencia_agotamiento": agotadas / len(resultados),
             "resultados": {k: resultados.count(k) for k in sorted(set(resultados))}}
    evidencia("CONC_4_contencion", datos)
    assert max(por_lectura) <= 3 and escrituras[0] > 0, datos
    assert set(resultados) <= {"COMPLETO", "LECTURA_NO_ESTABLE"}, datos              # nunca otro estado por la contencion
