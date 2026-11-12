# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_254_f06_01_b2_concurrencia_serial.py
# Ruta: tests/api/test_254_f06_01_b2_concurrencia_serial.py
# Descripcion: F06 T1-F06 · B2 N1 · bateria SERIAL y determinista con COMMIT real (R1 v0.9.5 §1.4, §I.5.1-§I.5.4,
#   §II.1; oraculos v0.7 §A.9.4, §A.9.5, §A.10.1, §A.10.4), FUERA de la suite general: solo con
#   GAPTO_B2_CONCURRENCIA=1 (base desechable). Barreras externas que retienen la fila que el escenario necesita
#   (HF-18); pg_locks y pg_stat_database.deadlocks; JSON por caso si GAPTO_B2_EVIDENCIA apunta a una carpeta.
#   Los consumidores de 0352 se activan dentro de cada test (monkeypatch), nunca por entorno.
#     O6.20  compra concurrente: (a) identica -> una compone y la otra idempotente; (b) otra linea -> la otra
#            IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION; sin 40P01, una auditoria de la propiedad.
#     O7.8 (S14, variante B2) C-COMPRA-03 (componente <= corte) || C-PROP-05 con la huella previa, en los dos
#            ordenes: C-COMPRA-03 primero -> C-PROP-05 VERSION_DESFASADA (el gasto posterior sube la version de la
#            propiedad; con el NK, la declaracion nunca ve el conjunto viejo); C-PROP-05 primero -> 200 y el gasto
#            posterior VERSION_DESFASADA. Nunca COMPLETO con un conjunto distinto. (C-MEJ-03 es de B3: su O7.8
#            literal va en el gate de B3.)
#     O7.9 (S15) OP-03 anula un componente || C-PROP-05: confirmada despues de la relectura -> PARCIAL.
#     AJ-0352-12 caso 11 (HF-06; O11.9 = S16, O11.10 = S17) cuatro variantes sobre la misma propiedad.
#     O11.14 (S18) misma intencion en P1 y P2, los dos ordenes; O11.15 (S19) intencion ya confirmada por B1.
#     O11.18 / S20 par 9 con C-PROP-05 REAL (G3); O11.21 con C-PROP-05 real; O11.17 / O11.23 de C-PROP-05.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import threading
import uuid

import psycopg
import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.core.contexto import ContextoOperacion
from app.patrimonio import completitud as compl
from app.propiedades import servicio as serv
from test_237_f06_01_b1r_intencion_concurrente_serial import (BarreraNK, Retener, cliente, clave_0p, deadlocks,
                                                              en_hilo, esperar_bloqueado, foto_locks, unidad)

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ORDENES = ["A-primero", "B-primero"]

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_B2_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_B2_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B2_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def _r(salida: dict):
    assert "e" not in salida, salida
    r = salida["r"]
    j = r.json()
    return r.status_code, j.get("codigo"), j.get("idempotente")


def _correr(fa, fb, barrera, nombre_a="b1r_A", nombre_b="b1r_B"):
    """A llega primero a la barrera, despues B; se suelta la barrera y se recogen los resultados."""
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado(nombre_a)
        tb, rb = en_hilo(fb)
        esperar_bloqueado(nombre_b)
        locks = foto_locks()
    finally:
        for x in (barrera if isinstance(barrera, list) else [barrera]):
            x.soltar()
    ta.join(60)
    tb.join(60)
    vivos = [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]
    return ra, rb, {"deadlocks_nuevos": deadlocks() - d0, "vivos": vivos, "pg_locks": locks,
                    "esperas": [f for f in locks if not f[3]]}


@pytest.fixture()
def on(monkeypatch):
    c2.habilitar_0352(monkeypatch)


# ================================================================== O6.20
@pytest.mark.parametrize("variante", ["identica", "otra_linea"])
def test_o6_20_compra_concurrente(variante):
    lab = c2.Lab()
    cuerpo = lab.peticion()
    otro = cuerpo if variante == "identica" else {**cuerpo, "gastos": cuerpo["gastos"][:2]}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    ra, rb, traza = _correr(lambda: lab.compra(cuerpo, ca), lambda: lab.compra(otro, cb), barrera)
    a, bb = _r(ra), _r(rb)
    auds = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id = %s AND tabla = 'entidades'",
                   (cuerpo["intencion_id"],))[0][0]
    datos = {"variante": variante, "A": a, "B": bb, "auditorias_propiedad": auds, **traza}
    evidencia(f"O6_20_{variante}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert a == (200, None, False), datos
    assert bb == ((200, None, True) if variante == "identica" else (409, REUTILIZADA, None)), datos
    assert auds == 1, datos
    assert any(f[0] == "b1r_B" and f[1] == "advisory" for f in traza["esperas"]), datos   # B espera en el nivel 0


# ================================================================== O7.8 (variante B2)
@pytest.mark.parametrize("orden", ORDENES)
def test_o7_8_gasto_posterior_frente_a_c_prop_05(on, orden):
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    rv = lab.version()
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    linea = lab.gasto("OTRO", "250.00", "2026-03-19", "2026-03-19")       # <= corte: cambia el conjunto
    gasto = lab.peticion03(linea, version=rv, atribucion={"modo": "NO_LO_SE"})   # sin titularidad el 19-03
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    f_gasto = lambda cli: lambda: lab.gasto_posterior(gasto, cli)          # noqa: E731
    f_decl = lambda cli: lambda: lab.declarar("ADQUISICION", True, c2.CORTE, huella, version=rv, cli=cli)  # noqa: E731
    barrera = BarreraNK(lab.pid)
    if orden == "A-primero":   # C-COMPRA-03 primero
        ra, rb, traza = _correr(f_gasto(ca), f_decl(cb), barrera)
        gasto_r, decl_r = _r(ra), _r(rb)
    else:
        ra, rb, traza = _correr(f_decl(ca), f_gasto(cb), barrera)
        decl_r, gasto_r = _r(ra), _r(rb)
    coste = lab.coste()["ADQUISICION"]
    datos = {"orden": orden, "gasto": gasto_r, "declaracion": decl_r, "coste": coste, **traza}
    evidencia(f"O7_8_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    if orden == "A-primero":
        # C-COMPRA-03 sube la version de la propiedad (C-MEJ-03 no): gana VERSION_DESFASADA (precedencia §I.5.1.7)
        assert gasto_r[0] == 200 and decl_r == (409, "VERSION_DESFASADA", None), datos
        assert coste["motivo_estado"] == "SIN_DECLARACION", datos
    else:
        assert decl_r[0] == 200 and gasto_r == (409, "VERSION_DESFASADA", None), datos
        assert coste["estado"] == "COMPLETO", datos            # el conjunto declarado es el vigente


# ================================================================== O7.9 (S15)
def test_o7_9_op03_confirmada_despues_de_la_relectura(on):
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    hecho, _ = c2.componente_fixture(lab.owner, lab.pid, "2026-05-01", "3000.00", "TRANSFORMACION_CAPITALIZABLE")
    huella = lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]
    retener = Retener("SELECT 1 FROM gapto.hechos_financieros WHERE id = %s FOR UPDATE", hecho)
    d0 = deadlocks()
    try:
        t3, r3 = en_hilo(lambda: c2.op03_anular(lab.owner, hecho))
        r5 = lab.declarar("MEJORAS", True, b.HOY, huella)                  # relee el conjunto con el componente
    finally:
        retener.soltar()
    t3.join(60)
    mej = lab.coste()["MEJORAS"]
    datos = {"declaracion": r5.status_code, "op03": repr(r3.get("r") or r3.get("e")), "mejoras": mej,
             "deadlocks_nuevos": deadlocks() - d0}
    evidencia("O7_9", datos)
    assert r5.status_code == 200 and "e" not in r3 and datos["deadlocks_nuevos"] == 0, datos
    assert (mej["estado"], mej["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA"), datos


# ================================================================== AJ-0352-12 caso 11 (HF-06) · O11.9 · O11.10
@pytest.mark.parametrize("variante", ["intenciones_distintas_mismo_ambito", "intenciones_distintas_otro_ambito",
                                      "O11_9_misma_intencion_identica", "O11_10_misma_intencion_otro_corte"])
def test_caso11_doble_declaracion_concurrente(on, variante):
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    rv = lab.version()
    hu = {c: lab.coste(c)["ADQUISICION"]["huella_conjunto"] for c in (c2.CORTE, "2026-04-01")}
    hm = lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]
    i1 = uuid.uuid4()
    i2 = i1 if variante.startswith("O11") else uuid.uuid4()
    a = dict(ambito="ADQUISICION", completo=True, fecha_corte=c2.CORTE, huella=hu[c2.CORTE], version=rv, intencion_id=i1)
    if variante == "intenciones_distintas_otro_ambito":
        bdat = dict(ambito="MEJORAS", completo=True, fecha_corte=b.HOY, huella=hm, version=rv, intencion_id=i2)
    elif variante == "O11_10_misma_intencion_otro_corte":
        bdat = {**a, "fecha_corte": "2026-04-01", "huella": hu["2026-04-01"]}
    else:
        bdat = {**a, "intencion_id": i2}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    ra, rb, traza = _correr(lambda: lab.declarar(**a, cli=ca), lambda: lab.declarar(**bdat, cli=cb), BarreraNK(lab.pid))
    ar, br = _r(ra), _r(rb)
    auds = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s AND "
                   "datos_despues -> 'intencion' ->> 'operacion' = 'COMPLETITUD'", (lab.pid,))[0][0]
    datos = {"variante": variante, "A": ar, "B": br, "auditorias_completitud": auds, **traza}
    evidencia(f"caso11_{variante}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert ar == (200, None, False) and auds == 1, datos
    esperado = {"intenciones_distintas_mismo_ambito": (409, "VERSION_DESFASADA", None),
                "intenciones_distintas_otro_ambito": (409, "VERSION_DESFASADA", None),
                "O11_9_misma_intencion_identica": (200, None, True),
                "O11_10_misma_intencion_otro_corte": (409, REUTILIZADA, None)}[variante]
    assert br == esperado, datos


# ================================================================== S18 (O11.14) y S19 (O11.15)
def _dos_propiedades():
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    p2 = b.crear(lab.cli, b.alta(b.solo_mia(), nombre="Garaje", fecha_adquisicion="2026-01-01"))["id"]
    return lab, p2


def _decl(lab, pid, i, cli):
    hm = c2.leer_coste(lab.cli, pid, b.HOY)["MEJORAS"]["huella_conjunto"]
    rv = b.leer(lab.cli, pid)["row_version"]
    cuerpo = {"intencion_id": str(i), "row_version_esperada": rv, "ambito": "MEJORAS", "completo": True,
              "fecha_corte": b.HOY, "huella_conjunto_vista": hm}
    return lambda: cli.post(f"/v1/propiedades/{pid}/completitud", json=cuerpo, headers=h.AUTH)


@pytest.mark.parametrize("orden", ORDENES)
def test_s18_o11_14_misma_intencion_en_dos_propiedades(on, orden):
    lab, p2 = _dos_propiedades()
    i = uuid.uuid4()
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    p_a, p_b = (lab.pid, p2) if orden == "A-primero" else (p2, lab.pid)
    fa, fb = _decl(lab, p_a, i, ca), _decl(lab, p_b, i, cb)
    rv_b = b.leer(lab.cli, p_b)["row_version"]
    barreras = [Retener("SELECT 1 FROM gapto.propiedades WHERE entidad_id = %s FOR UPDATE", p) for p in (p_a, p_b)]
    ra, rb, traza = _correr(fa, fb, barreras)
    ar, br = _r(ra), _r(rb)
    auds = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (str(i),))[0][0]
    datos = {"orden": orden, "A": ar, "B": br, "auditorias": auds, "row_version_b": [rv_b, b.leer(lab.cli, p_b)["row_version"]],
             **traza}
    evidencia(f"S18_O11_14_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert ar == (200, None, False) and br == (409, REUTILIZADA, None) and auds == 1, datos
    assert datos["row_version_b"][0] == datos["row_version_b"][1], datos
    k1, _ = clave_0p(lab.owner, i)
    assert any(f[0] == "b1r_B" and f[1] == "advisory" and f[5] == k1 for f in traza["esperas"]), datos


@pytest.mark.parametrize("tercera", [False, True], ids=["b1_en_P1", "b1_en_P3"])
def test_s19_o11_15_intencion_ya_confirmada_por_b1(on, tercera):
    lab, p2 = _dos_propiedades()
    i = uuid.uuid4()
    destino = b.crear(lab.cli, b.alta(b.solo_mia(), nombre="Trastero"))["id"] if tercera else lab.pid
    assert b.post(lab.cli, f"/v1/propiedades/{destino}/editar", {"intencion_id": str(i), "row_version_esperada":
                                                                  b.leer(lab.cli, destino)["row_version"], "notas": "B1"}).status_code == 200
    antes = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (str(i),))[0][0]
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barreras = [Retener("SELECT 1 FROM gapto.propiedades WHERE entidad_id = %s FOR UPDATE", p) for p in (lab.pid, p2)]
    d0 = deadlocks()
    ta, ra = en_hilo(_decl(lab, lab.pid, i, ca))
    tb, rb = en_hilo(_decl(lab, p2, i, cb))
    ta.join(30)
    tb.join(30)
    for x in barreras:
        x.soltar()
    ar, br = _r(ra), _r(rb)
    despues = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (str(i),))[0][0]
    datos = {"A": ar, "B": br, "auditorias": [antes, despues], "deadlocks_nuevos": deadlocks() - d0}
    evidencia(f"S19_O11_15_{'P3' if tercera else 'P1'}", datos)
    assert ar == br == (409, REUTILIZADA, None) and antes == despues and datos["deadlocks_nuevos"] == 0, datos


# ================================================================== S20 par 9 con C-PROP-05 real (O11.18 gate) y O11.21
def test_s20_par_9_c_prop_02_frente_a_c_prop_05_real(on):
    lab, p2 = _dos_propiedades()
    i = uuid.uuid4()
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    rv1 = lab.version()
    fa = lambda: b.post(ca, f"/v1/propiedades/{lab.pid}/editar", {"intencion_id": str(i), "row_version_esperada": rv1,  # noqa: E731
                                                                 "notas": "x"})
    fb = _decl(lab, p2, i, cb)
    rv2 = b.leer(lab.cli, p2)["row_version"]
    barreras = [Retener("SELECT 1 FROM gapto.propiedades WHERE entidad_id = %s FOR UPDATE", p) for p in (lab.pid, p2)]
    ra, rb, traza = _correr(fa, fb, barreras)
    ar, br = _r(ra), _r(rb)
    auds = lab.sql("SELECT count(*) FROM gapto.auditoria WHERE request_id = %s AND tabla = 'entidades'", (str(i),))[0][0]
    datos = {"A": ar, "B": br, "auditorias": auds, "row_version_p2": [rv2, b.leer(lab.cli, p2)["row_version"]], **traza}
    evidencia("S20_par9_C-PROP-02__C-PROP-05_real", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert ar[0] == 200 and br == (409, REUTILIZADA, None) and auds == 1, datos
    assert datos["row_version_p2"][0] == datos["row_version_p2"][1], datos


def test_o11_21_editar_frente_a_c_prop_05_misma_propiedad(on):
    lab, _ = _dos_propiedades()
    i = uuid.uuid4()
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    rv = lab.version()
    fa = lambda: b.post(ca, f"/v1/propiedades/{lab.pid}/editar", {"intencion_id": str(i), "row_version_esperada": rv,  # noqa: E731
                                                                 "notas": "O11.21"})
    fb = _decl(lab, lab.pid, i, cb)
    ra, rb, traza = _correr(fa, fb, BarreraNK(lab.pid))
    ar, br = _r(ra), _r(rb)
    datos = {"editar": ar, "cprop05": br, **traza}
    evidencia("O11_21_cprop05_real", datos)
    assert traza["deadlocks_nuevos"] == 0 and ar[0] == 200 and br == (409, REUTILIZADA, None), datos


def test_o11_17_o11_23_c_prop_05_primer_lock_es_el_0p(on, monkeypatch):
    lab = c2.Lab()
    assert lab.compra(lab.peticion()).status_code == 200
    i = uuid.uuid4()
    llego, sigue = threading.Event(), threading.Event()
    original = compl.bloquear_intencion_propiedad

    def pausa(sesion, intencion_id):
        original(sesion, intencion_id)
        if threading.current_thread().name == "O11_23" and not llego.is_set():
            llego.set()
            sigue.wait(60)
    monkeypatch.setattr(compl, "bloquear_intencion_propiedad", pausa)
    huella = lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]
    rv = lab.version()
    u = unidad("b1r_O11_23")
    salida: dict = {}

    def correr():
        try:
            salida["r"] = u.ejecutar(ContextoOperacion.de_usuario(lab.owner, request_id=i), lambda s: compl.declarar(
                s, propiedad_id=uuid.UUID(lab.pid), intencion_id=i, row_version=rv, ambito="MEJORAS", completo=True,
                fecha_corte=__import__("datetime").date.fromisoformat(b.HOY), huella_vista=huella,
                reloj=c2.x5.reloj(b.RELOJ)))
        except Exception as exc:  # pragma: no cover
            salida["e"] = repr(exc)
    hilo = threading.Thread(target=correr, name="O11_23", daemon=True)
    try:
        hilo.start()
        assert llego.wait(30)
        with psycopg.connect(h.dsn(), autocommit=True) as c:
            locks = [list(f) for f in c.execute(
                "SELECT l.locktype, l.mode, l.granted, l.relation::regclass::text, l.classid::bigint, l.objid::bigint "
                "FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.application_name = 'b1r_O11_23' "
                "AND l.locktype <> 'virtualxid' ORDER BY 1").fetchall()]
    finally:
        sigue.set()
        hilo.join(60)
    k1, k2 = clave_0p(lab.owner, i)
    datos = {"locks_tras_0p": locks, "clave": [k1, k2], "salida": repr(salida.get("r") or salida.get("e"))}
    evidencia("O11_23_C-PROP-05", datos)
    assert locks == [["advisory", "ExclusiveLock", True, None, k1, k2]], datos
    assert isinstance(salida.get("r"), compl.Resultado), datos
