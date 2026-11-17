# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_295_f06_01h_concurrencia_serial.py
# Ruta: tests/api/test_295_f06_01h_concurrencia_serial.py
# Descripcion: F06 T3-F06 bloque 2 F06-01H · intercalaciones IC-01..IC-12 e IC-14 (mandato v1.1 §13.1 y §13.2;
#   contrato v0.4 §6 y §10.1.4). Bateria SERIAL y determinista, FUERA de la suite general: solo con
#   GAPTO_F06HIP_CONCURRENCIA=1 (base desechable; COMMIT real). JSON por caso si GAPTO_F06HIP_EVIDENCIA apunta a
#   una carpeta. Nunca en paralelo.
#   Mecanica comun (dos conexiones, barreras explicitas): la sesion A ejecuta su operacion completa y se detiene
#   ANTES del COMMIT (envoltura del servicio que espera un Event: retiene todos sus locks); la sesion B arranca y,
#   cuando el caso exige espera, se comprueba que B esta en wait_event_type = 'Lock' y se captura `pg_locks` en
#   ese punto (locks advisory, tuple y transactionid de las sesiones hip_*, con pg_blocking_pids y la sentencia de
#   B); despues se suelta A, A confirma y B termina. En cada caso: pg_stat_database.deadlocks antes/despues sin
#   cambio, ningun reintento 40P01/40001 de UnidadDeTrabajo (se registra es_reintentable) y G2/G1 comprobadas
#   sobre el estado final (Σ capital = P, numeracion 1..N, cuotas pagadas intactas).
#   Tres repeticiones en los casos cuyo veredicto depende del orden (IC-01/02, IC-03, IC-08, IC-12).
#   Enmienda vigente: el Hd va sin aportaciones (APORTACIONES_EN_ENTRADA = False).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 11)
# Version: 0.1.1 (F06 T3-F06 bloque 2 F06-01H, paso 11, relevo 5; N-38): IC-01 «afecta» sin xfail; exige el
#   resultado del contrato §6 (REVISION_SOBRE_CUOTA_PAGADA) tras corregir el orden de guardas en revision.py
#   v0.2.0 (indicacion de Moises del 2026-11-17).
# Version: 0.1.2 (F06 T3-F06 bloque 2 F06-01H, paso 12, relevo 6): IC-12b cuota N+1 concurrente (refuerzo del oraculo
#   de MS-11, indicacion de Moises: IC-12 no discrimina el lock de G2).
# ============================================================
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid
from decimal import Decimal

import psycopg
import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.api import ejecucion_gasto_pagado as egp
from app.api import ejecucion_prevision as ejp
from app.api import guarda_financiacion as gf
from app.api.dto_prevision import IntencionReabrir
from app.capacidades import servicio as serv_cap
from app.core import unidad_trabajo as ut
from app.core.contexto import ContextoOperacion
from app.hipotecas import pago as serv_pago
from app.hipotecas import revision as serv_rev
from app.patrimonio import compra
from app.propiedades import servicio as serv_prop
from test_237_f06_01_b1r_intencion_concurrente_serial import cliente, deadlocks, en_hilo, esperar_bloqueado, unidad
from test_289_f06_01h_alta_en_compra import LabHip
from test_294_f06_01h_revision_tipo import LabRev

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F06HIP_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F06HIP_CONCURRENCIA=1)")

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
REPS = [1, 2, 3]
A, B = "hip_A", "hip_B"
FINANCIACION = {"fila:gapto.entidades", "fila:gapto.financiaciones"}
GUARDA_CUOTA_SQL = "SELECT 1 FROM gapto.financiacion_cuotas WHERE prevision_id = %s"

#: app -> (llego, sigue): la sesion `app` se detiene antes del COMMIT hasta `sigue`.
PAUSAS: dict[str, tuple[threading.Event, threading.Event]] = {}
REINTENTOS: list = []


# ------------------------------------------------------------------ utilidades
def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_F06HIP_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _pausa(sesion) -> None:
    nombre = sesion.uno("SELECT current_setting('application_name')")[0]
    par = PAUSAS.get(nombre)
    if par is not None and not par[0].is_set():
        par[0].set()
        par[1].wait(90)


def _pausable(original):
    def envoltura(sesion, *a, **kw):
        r = original(sesion, *a, **kw)
        _pausa(sesion)
        return r
    return envoltura


@pytest.fixture(autouse=True)
def arnes(monkeypatch):
    PAUSAS.clear()
    REINTENTOS.clear()
    for modulo, nombre in ((serv_pago, "pagar"), (serv_rev, "revisar"), (compra, "registrar_compra"),
                           (serv_cap, "desactivar"), (serv_prop, "editar"), (serv_prop, "corregir_inicio"),
                           (egp, "bloquear_cuenta")):
        monkeypatch.setattr(modulo, nombre, _pausable(getattr(modulo, nombre)))
    original = ut.es_reintentable

    def registrar(exc):
        REINTENTOS.append(getattr(exc, "sqlstate", None) or type(exc).__name__)
        return original(exc)
    monkeypatch.setattr(ut, "es_reintentable", registrar)
    yield
    for _, sigue in PAUSAS.values():
        sigue.set()


def _claves_advisory() -> dict[int, str]:
    nombres = ("INVERSIONES", "OP22", "INTENCION")
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        fila = c.execute("SELECT " + ", ".join(
            f"(hashtext('gapto:{n}')::bigint + 4294967296) % 4294967296" for n in nombres)).fetchone()
    return dict(zip(fila, nombres))


def foto_locks() -> list[dict]:
    """pg_locks en el punto de espera: advisory, tuple y transactionid de las sesiones hip_*."""
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        filas = c.execute(
            "SELECT a.application_name, a.pid, l.locktype, l.mode, l.granted, l.relation::regclass::text, "
            "l.classid::bigint, l.objid::bigint, l.page, l.tuple, l.transactionid::text, a.wait_event_type, "
            "a.wait_event, (SELECT array_agg(x.application_name) FROM pg_stat_activity x "
            "WHERE x.pid = ANY(pg_blocking_pids(a.pid))), left(a.query, 240) "
            "FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.datname = current_database() "
            "AND a.application_name LIKE 'hip\\_%%' AND l.locktype IN ('tuple', 'transactionid', 'advisory') "
            "ORDER BY 1, 3, 4").fetchall()
    campos = ("app", "pid", "locktype", "mode", "granted", "relation", "classid", "objid", "page", "tuple",
              "transactionid", "wait_event_type", "wait_event", "bloqueado_por", "query")
    return [dict(zip(campos, f)) for f in filas]


def espera_de(locks: list[dict], app: str = B) -> list[str]:
    """Recurso en el que espera `app`: advisory:<clave> o fila:<tabla> (tuple lock que precede al transactionid)."""
    claves = _claves_advisory()
    propias = [f for f in locks if f["app"] == app]
    salida = []
    for f in propias:
        if f["granted"]:
            continue
        if f["locktype"] == "advisory":
            salida.append("advisory:" + claves.get(f["classid"], str(f["classid"])))
        elif f["locktype"] == "tuple":
            salida.append("fila:" + str(f["relation"]))
        elif f["locktype"] == "transactionid":
            tuplas = [t for t in propias if t["locktype"] == "tuple" and t["granted"]]
            salida.extend("fila:" + str(t["relation"]) for t in tuplas)
    return sorted(set(salida))


def _codigo(salida: dict):
    """(status, codigo) de una respuesta HTTP; ('EXC', texto) si el hilo lanzo."""
    if "e" in salida:
        assert "40P01" not in salida["e"] and "DeadlockDetected" not in salida["e"], salida["e"]
        return ("EXC", salida["e"])
    r = salida["r"]
    if hasattr(r, "status_code"):
        return (r.status_code, r.json().get("codigo") if r.status_code >= 400 else None)
    return ("OK", repr(r)[:200])


def _cadena(exc: BaseException | None) -> str:
    textos = []
    while exc is not None:
        textos.append(f"{type(exc).__name__}: {exc}")
        exc = exc.__cause__ or exc.__context__
    return " <- ".join(textos)


def en_hilo_exc(fn):
    """Como en_hilo, pero conserva la excepcion (para inspeccionar la causa SQL)."""
    salida: dict = {}

    def correr():
        try:
            salida["r"] = fn()
        except Exception as e:  # noqa: BLE001 - se inspecciona en el oraculo
            salida["e"] = _cadena(e)
            salida["exc"] = e
    t = threading.Thread(target=correr, daemon=True)
    t.start()
    return t, salida


def intercalar(nombre: str, fa, fb, *, espera: bool | None, hilo=en_hilo) -> dict:
    """A llega a su punto de pausa (antes del COMMIT, con sus locks); B arranca; pg_locks en el punto de espera;
    se suelta A. `espera`: True = B debe quedar en Lock; False = B debe terminar con A retenido; None = se registra."""
    d0 = deadlocks()
    PAUSAS[A] = (threading.Event(), threading.Event())
    ta, ra = hilo(fa)
    tb, rb = None, {}
    locks: list[dict] = []
    b_esperaba = None
    try:
        assert PAUSAS[A][0].wait(90), f"{nombre}: A no llego a su punto de pausa ({ra})"
        tb, rb = hilo(fb)
        if espera:
            esperar_bloqueado(B, limite=30)
            locks = foto_locks()
            b_esperaba = True
        else:
            fin = time.monotonic() + (20 if espera is False else 6)
            while tb.is_alive() and time.monotonic() < fin:
                locks = foto_locks() or locks
                if any(f["app"] == B and not f["granted"] for f in locks):
                    break
                time.sleep(0.05)
            b_esperaba = tb.is_alive()
            locks = foto_locks() if tb.is_alive() else locks
    finally:
        PAUSAS[A][1].set()
    ta.join(90)
    if tb is not None:
        tb.join(90)
    time.sleep(0.5)                   # las sesiones cerradas vuelcan sus estadisticas
    traza = {"caso": nombre, "b_esperaba_con_a_retenido": b_esperaba, "espera_b": espera_de(locks),
             "pg_locks": locks, "A": _codigo(ra), "B": _codigo(rb), "vivos": [n for n, t in (("A", ta), ("B", tb))
                                                                               if t is not None and t.is_alive()],
             "deadlocks": [d0, deadlocks()], "reintentos": list(REINTENTOS)}
    traza["_salidas"] = (ra, rb)
    return traza


def cerrar(nombre: str, traza: dict, **extra) -> dict:
    datos = {k: v for k, v in traza.items() if k != "_salidas"}
    datos.update(extra)
    evidencia(nombre, datos)
    assert datos["vivos"] == [], datos
    assert datos["deadlocks"][0] == datos["deadlocks"][1], datos
    assert not [s for s in datos["reintentos"] if s in ("40P01", "40001")], datos
    return datos


def g2(lab, f=None) -> tuple:
    return lab.sql("SELECT f.capital_original_contratado::text, sum(q.capital_previsto)::text, count(*), "
                   "min(q.numero_cuota), max(q.numero_cuota) FROM gapto.financiaciones f JOIN gapto.financiacion_cuotas q "
                   "ON q.financiacion_entidad_id = f.entidad_id WHERE f.entidad_id = %s GROUP BY 1", (f or lab.f,))[0]


def assert_g2(lab, datos, f=None) -> None:
    capital, suma, n, minimo, maximo = g2(lab, f)
    assert Decimal(capital) == Decimal(suma) and n == maximo and minimo == 1, (g2(lab, f), datos)


def pagadas(lab) -> list[tuple]:
    """G1: cuotas cuya prevision no esta ABIERTA, con todo su cuadro."""
    return lab.sql("SELECT q.numero_cuota, q.capital_previsto::text, q.interes_previsto::text, "
                   "q.importe_total_previsto::text, q.condicion_version_id, p.estado, p.importe_esperado::text "
                   "FROM gapto.financiacion_cuotas q JOIN gapto.previsiones p ON p.id = q.prevision_id "
                   "WHERE q.financiacion_entidad_id = %s AND p.estado <> 'ABIERTA' ORDER BY q.numero_cuota", (lab.f,))


def pagar(lab, cli, numero: int, cuerpo: dict):
    return cli.post(f"/v1/hipotecas/{lab.f}/cuotas/{numero}/pago", json=cuerpo, headers=h.AUTH)


def revisar(lab, cli, cuerpo: dict):
    return cli.post(f"/v1/hipotecas/{lab.f}/revision", json=cuerpo, headers=h.AUTH)


def clientes(lab):
    return cliente(lab.owner, A), cliente(lab.owner, B)


def peticion_en(lab, pid, **kw) -> dict:
    """Peticion de compra con hipoteca sobre otra propiedad del mismo owner (version y propuesta de esa propiedad)."""
    original = lab.pid
    lab.pid = pid
    try:
        return lab.peticion_hip(**kw)
    finally:
        lab.pid = original


def segunda_propiedad(lab, nombre="Garaje") -> str:
    return b.crear(lab.cli, b.alta(b.compartida([b.yo("60"), b.de(lab.ta, "40")], desde=c2.ESCRITURA),
                                   nombre=nombre, fecha_adquisicion=c2.ESCRITURA))["id"]


def compra_en(cli, pid, cuerpo):
    return cli.post(f"/v1/propiedades/{pid}/compra", json=cuerpo, headers=h.AUTH)


def saldo(lab, cuenta) -> Decimal:
    return Decimal(lab.sql("SELECT coalesce(sum(importe), 0) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s "
                           "AND estado = 'ACTIVO'", (cuenta,))[0][0])


def fin_de(cuerpo) -> uuid.UUID:
    return uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), "gapto.f06.hipoteca.financiacion")


# ================================================================== IC-01 / IC-02
@pytest.mark.parametrize("rep", REPS)
@pytest.mark.parametrize("afecta", [False, True], ids=["revision_no_afecta_c1", "revision_afecta_c1"])
def test_ic01_pago_primero_revision_despues(rep, afecta):
    """IC-01 (pago ∥ revision, pago primero). Contrato §6: el segundo espera en la financiacion; resultado
    coherente: pago primero -> la revision ve la cuota REALIZADA y responde REVISION_SOBRE_CUOTA_PAGADA si la afecta;
    G1/G2 nunca violadas. Ambas peticiones se preparan con la misma version (la que el cliente leyo)."""
    lab = LabRev()
    ca, cb = clientes(lab)
    pago = lab.cuerpo()
    rev = lab.cuerpo_rev(desde="2026-04-01" if afecta else "2027-04-01")
    t = intercalar("IC-01", lambda: pagar(lab, ca, 1, pago), lambda: revisar(lab, cb, rev), espera=True)
    nombre = f"IC-01_{'afecta' if afecta else 'no_afecta'}_rep{rep}"
    datos = cerrar(nombre, t, g2=g2(lab), pagadas=pagadas(lab), versiones=len(lab.versiones()))
    assert set(datos["espera_b"]) & FINANCIACION, datos
    assert datos["A"] == (200, None), datos
    assert datos["versiones"] == 1 and [p[0] for p in datos["pagadas"]] == [1], datos     # revision sin efecto
    assert_g2(lab, datos)
    # Contrato §6 IC-01 (revision.py v0.2.0): la revision ve la cuota REALIZADA y responde REVISION_SOBRE_CUOTA_PAGADA
    # aunque se preparara con la version previa al pago; si no la afecta, VERSION_DESFASADA. Mata M-H-44.
    assert datos["B"] == ((409, "REVISION_SOBRE_CUOTA_PAGADA") if afecta else (409, "VERSION_DESFASADA")), datos


@pytest.mark.parametrize("rep", REPS)
def test_ic02_revision_primero_pago_despues(rep):
    """IC-02 (pago ∥ revision, revision primero). Contrato §6: el segundo (pago) espera en la financiacion y
    responde VERSION_DESFASADA; G1/G2 nunca violadas (la revision recalcula c1..c360, todas ABIERTAS)."""
    lab = LabRev()
    ca, cb = clientes(lab)
    pago = lab.cuerpo()
    rev = lab.cuerpo_rev(desde="2026-04-01")
    t = intercalar("IC-02", lambda: revisar(lab, ca, rev), lambda: pagar(lab, cb, 1, pago), espera=True)
    datos = cerrar(f"IC-02_rep{rep}", t, g2=g2(lab), pagadas=pagadas(lab), versiones=len(lab.versiones()))
    assert set(datos["espera_b"]) & FINANCIACION, datos
    assert datos["A"] == (200, None) and datos["B"] == (409, "VERSION_DESFASADA"), datos
    assert datos["versiones"] == 2 and datos["pagadas"] == [], datos
    assert_g2(lab, datos)


# ================================================================== IC-03
@pytest.mark.parametrize("rep", REPS)
def test_ic03_pago_frente_a_pago_de_la_misma_cuota(rep):
    """IC-03 (pago ∥ pago de la misma cuota). Contrato §6: uno gana; el otro CUOTA_NO_PENDIENTE o
    VERSION_DESFASADA (R-A de #152). Un solo hecho de pago."""
    lab = LabRev()
    ca, cb = clientes(lab)
    p1, p2 = lab.cuerpo(), lab.cuerpo()
    t = intercalar("IC-03", lambda: pagar(lab, ca, 1, p1), lambda: pagar(lab, cb, 1, p2), espera=True)
    hechos = lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id IN (%s, %s)",
                     (p1["intencion_id"], p2["intencion_id"]))[0][0]
    datos = cerrar(f"IC-03_rep{rep}", t, hechos=hechos, g2=g2(lab), pagadas=pagadas(lab))
    assert datos["espera_b"], datos
    assert datos["A"] == (200, None), datos
    assert datos["B"] in ((409, "CUOTA_NO_PENDIENTE"), (409, "VERSION_DESFASADA")), datos
    assert hechos == 1 and [p[0] for p in datos["pagadas"]] == [1], datos
    assert_g2(lab, datos)


# ================================================================== IC-04
def test_ic04_misma_intencion_en_dos_cuotas():
    """IC-04 (misma intencion en dos cuotas). Contrato §6: 0P; una gana; la otra
    IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. B espera en el advisory de raiz (0P / OP-22)."""
    lab = LabRev()
    ca, cb = clientes(lab)
    i = uuid.uuid4()
    p1, p2 = lab.cuerpo(intencion=i), lab.cuerpo(intencion=i, fecha="2026-05-20")
    t = intercalar("IC-04", lambda: pagar(lab, ca, 1, p1), lambda: pagar(lab, cb, 2, p2), espera=True)
    datos = cerrar("IC-04", t, pagadas=pagadas(lab), g2=g2(lab))
    assert datos["espera_b"] == ["advisory:OP22"], datos
    assert datos["A"] == (200, None) and datos["B"] == (409, REUTILIZADA), datos
    assert [p[0] for p in datos["pagadas"]] == [1], datos
    assert_g2(lab, datos)


# ================================================================== IC-05 / IC-06
def _cprop02(lab, cli):
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.version(), "notas": "IC-05"}
    return lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/editar", cuerpo)


def _cprop03bis(lab, cli):
    d = b.leer(lab.cli, lab.pid)
    it = d["inicio_titularidad"]
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": d["row_version"], "nuevo_desde": "2026-03-01",
              "inicio_visto": it["inicio"], "primera_version_vista": it["primera_version"], "motivo": "IC-06"}
    return lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/titularidad/inicio", cuerpo)


@pytest.mark.parametrize("orden", ["pago_primero", "propiedad_primero"])
@pytest.mark.parametrize("op", ["C-PROP-02", "C-PROP-03bis"])
def test_ic05_ic06_pago_frente_a_operaciones_de_la_propiedad(op, orden):
    """IC-05 (pago ∥ C-PROP-02) e IC-06 (pago ∥ C-PROP-03bis). Contrato §6: sin bloqueo cruzado (el pago no
    bloquea la propiedad; orden parcial global propiedad -> cuenta -> financiacion). Con cualquiera de los dos
    retenido antes del COMMIT, el otro termina sin esperar. Para que C-PROP-03bis sea admisible (200) la
    propiedad se da de alta con fecha de adquisicion 2026-01-01 (titularidad desde la escritura, 2026-03-20) y el
    nuevo inicio es 2026-03-01."""
    lab = LabRev(fecha_adquisicion="2026-01-01")
    ca, cb = clientes(lab)
    pago = lab.cuerpo()
    fprop = (_cprop02 if op == "C-PROP-02" else _cprop03bis)
    if orden == "pago_primero":
        t = intercalar(op, lambda: pagar(lab, ca, 1, pago), fprop(lab, cb), espera=False)
    else:
        t = intercalar(op, fprop(lab, ca), lambda: pagar(lab, cb, 1, pago), espera=False)
    ic = "IC-05" if op == "C-PROP-02" else "IC-06"
    datos = cerrar(f"{ic}_{op}_{orden}", t, pagadas=pagadas(lab), g2=g2(lab))
    assert datos["b_esperaba_con_a_retenido"] is False and datos["espera_b"] == [], datos
    res_pago, res_prop = (datos["A"], datos["B"]) if orden == "pago_primero" else (datos["B"], datos["A"])
    assert res_pago == (200, None), datos
    assert res_prop == (200, None), datos
    assert_g2(lab, datos)


# ================================================================== IC-07
@pytest.mark.parametrize("orden", ["P1_primero", "P2_primero"])
def test_ic07_dos_compras_misma_intencion_dos_propiedades(orden):
    """IC-07 (dos compras con hipoteca y la misma intencion sobre dos propiedades). Contrato §6: una gana (O-H17);
    la otra IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION; una sola financiacion."""
    lab = LabHip()
    p2 = segunda_propiedad(lab)
    i = uuid.uuid4()
    c_p1, c_p2 = peticion_en(lab, lab.pid, intencion_id=i), peticion_en(lab, p2, intencion_id=i)
    ca, cb = clientes(lab)
    (pa, ba), (pb, bb) = ((lab.pid, c_p1), (p2, c_p2)) if orden == "P1_primero" else ((p2, c_p2), (lab.pid, c_p1))
    t = intercalar("IC-07", lambda: compra_en(ca, pa, ba), lambda: compra_en(cb, pb, bb), espera=True)
    fins = lab.sql("SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = %s", (fin_de(c_p1),))[0][0]
    hipotecas = lab.sql("SELECT count(*) FROM gapto.financiaciones WHERE tipo_financiacion = 'HIPOTECA'")[0][0]
    datos = cerrar(f"IC-07_{orden}", t, financiaciones=fins, hipotecas_owner=hipotecas)
    assert datos["espera_b"] and all(e.startswith("advisory:") for e in datos["espera_b"]), datos
    assert datos["A"] == (200, None) and datos["B"] == (409, REUTILIZADA), datos
    assert fins == 1 and hipotecas == 1, datos
    assert_g2(lab, datos, f=fin_de(c_p1))


# ================================================================== IC-08
@pytest.mark.parametrize("rep", REPS)
def test_ic08_revision_frente_a_revision(rep):
    """IC-08 (revision ∥ revision). Contrato §6: la segunda espera en la financiacion y responde
    VERSION_DESFASADA."""
    lab = LabRev()
    ca, cb = clientes(lab)
    r1, r2 = lab.cuerpo_rev(desde="2027-04-01"), lab.cuerpo_rev(desde="2027-05-01", tasa="3.10")
    t = intercalar("IC-08", lambda: revisar(lab, ca, r1), lambda: revisar(lab, cb, r2), espera=True)
    datos = cerrar(f"IC-08_rep{rep}", t, g2=g2(lab), versiones=len(lab.versiones()))
    assert set(datos["espera_b"]) & FINANCIACION, datos
    assert datos["A"] == (200, None) and datos["B"] == (409, "VERSION_DESFASADA"), datos
    assert datos["versiones"] == 2, datos
    assert_g2(lab, datos)


# ================================================================== IC-09
@pytest.mark.parametrize("orden", ["compra_primero", "gasto_primero"])
def test_ic09_compra_con_hipoteca_frente_a_gasto_op22_en_la_cuenta_de_desembolso(orden):
    """IC-09 (compra con hipoteca ∥ gasto OP-22 sobre la cuenta de desembolso). Contrato §6: espera en la cuenta;
    ambos coherentes; saldo final = O-H26 ± el gasto (previo + P - 200.000 - 50)."""
    lab = LabHip()
    ca, cb = clientes(lab)
    cuerpo = lab.peticion_hip()
    gasto = h.intencion(lab.cd, importe="50.00", fecha_hecho="2026-09-24")
    previo = saldo(lab, lab.cd)
    fc = lambda cli: lambda: compra_en(cli, lab.pid, cuerpo)  # noqa: E731
    fg = lambda cli: lambda: cli.post("/v1/intenciones/gasto-pagado", json=gasto, headers=h.AUTH)  # noqa: E731
    if orden == "compra_primero":
        t = intercalar("IC-09", fc(ca), fg(cb), espera=True)
    else:
        t = intercalar("IC-09", fg(ca), fc(cb), espera=True)
    delta = saldo(lab, lab.cd) - previo
    lab.f = fin_de(cuerpo)
    datos = cerrar(f"IC-09_{orden}", t, delta_saldo=str(delta), g2=g2(lab))
    assert datos["espera_b"] == ["fila:gapto.cuentas"], datos
    assert datos["A"][0] == 200 and datos["B"][0] == 200, datos
    assert delta == Decimal("-40050"), datos
    assert_g2(lab, datos)


# ================================================================== IC-10
@pytest.mark.parametrize("orden", ["compra_primero", "pago_primero"])
def test_ic10_compra_con_hipoteca_frente_a_pago_de_otra_hipoteca_misma_cuenta(orden):
    """IC-10 (compra con hipoteca ∥ pago de una cuota de OTRA hipoteca con la misma cuenta). Contrato §6: espera en
    la cuenta; sin ciclo. Nota: ambos toman el advisory INVERSIONES antes de la cuenta (orden normativo §13.1):
    la espera se registra donde ocurra y se exige que sea un recurso anterior a la financiacion."""
    lab = LabRev()
    p2 = segunda_propiedad(lab)
    ca, cb = clientes(lab)
    pago = lab.cuerpo()
    cuerpo = peticion_en(lab, p2)
    fc = lambda cli: lambda: compra_en(cli, p2, cuerpo)  # noqa: E731
    fp = lambda cli: lambda: pagar(lab, cli, 1, pago)  # noqa: E731
    if orden == "compra_primero":
        t = intercalar("IC-10", fc(ca), fp(cb), espera=True)
    else:
        t = intercalar("IC-10", fp(ca), fc(cb), espera=True)
    datos = cerrar(f"IC-10_{orden}", t, g2_h1=g2(lab), g2_h2=g2(lab, fin_de(cuerpo)), pagadas=pagadas(lab))
    assert datos["espera_b"] and set(datos["espera_b"]) <= {"advisory:INVERSIONES", "fila:gapto.cuentas"}, datos
    assert datos["A"][0] == 200 and datos["B"][0] == 200, datos
    assert [p[0] for p in datos["pagadas"]] == [1], datos
    assert_g2(lab, datos)
    assert_g2(lab, datos, f=fin_de(cuerpo))


# ================================================================== IC-11
@pytest.mark.parametrize("variante", ["servicio_vigente", "servicio_mutado"])
def test_ic11_reabrir_prevision_de_cuota_frente_a_revision(variante, monkeypatch):
    """IC-11 («Reabrir» la prevision de una cuota ∥ revision). Contrato §6: rechazo de servicio; con el servicio
    mutado (guardas S7 y M-H-36 anuladas por monkeypatch), G1-R rechaza en la base; nunca cuota pagada editable.
    c1 pagada; la revision (desde 2026-04-01, afecta a c1) queda retenida antes del COMMIT con la financiacion, la
    version y las cuotas bloqueadas, y responde REVISION_SOBRE_CUOTA_PAGADA."""
    lab = LabRev()
    assert pagar(lab, lab.cli, 1, lab.cuerpo()).status_code == 200
    pid = uuid.uuid5(lab.f, "gapto.f06.hipoteca.prevision:1")
    rv = lab.sql("SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]
    antes = pagadas(lab)
    ca, _ = clientes(lab)
    rev = lab.cuerpo_rev(desde="2026-04-01")
    intencion = IntencionReabrir(intencion_id=uuid.uuid4(), row_version=rv, motivo="IC-11")
    if variante == "servicio_mutado":
        monkeypatch.setattr(gf, "rechazo_prevision", lambda sesion, prevision_id: None)
        uno = ut.SesionMotor.uno

        def uno_mutado(self, sql, params=()):
            if sql == GUARDA_CUOTA_SQL:
                return None
            return uno(self, sql, params)
        monkeypatch.setattr(ut.SesionMotor, "uno", uno_mutado)
    reabrir = lambda: ejp.reabrir(unidad(B), ContextoOperacion.de_usuario(lab.owner, request_id=intencion.intencion_id),  # noqa: E731
                                  pid, intencion)
    t = intercalar("IC-11", lambda: revisar(lab, ca, rev), reabrir, espera=None, hilo=en_hilo_exc)
    rb = t["_salidas"][1]
    estado = lab.sql("SELECT estado FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]
    datos = cerrar(f"IC-11_{variante}", t, estado_prevision_c1=estado, pagadas_antes=antes, pagadas=pagadas(lab),
                   g2=g2(lab), resultado_reabrir=repr(rb.get("r")) if "r" in rb else rb.get("e"))
    assert datos["A"] == (409, "REVISION_SOBRE_CUOTA_PAGADA"), datos
    assert estado == "REALIZADA" and datos["pagadas"] == antes, datos
    if variante == "servicio_vigente":
        assert "r" in rb and getattr(rb["r"], "codigo", None) == "PREVISION_DE_CUOTA", datos
    else:
        assert "e" in rb and "INV-0354-G1R" in rb["e"], datos
    assert_g2(lab, datos)


# ================================================================== IC-12
@pytest.mark.parametrize("rep", REPS)
@pytest.mark.parametrize("orden", ["update_primero", "revision_primero"])
def test_ic12_update_de_capital_frente_a_revision(orden, rep):
    """IC-12 (UPDATE de capital_original_contratado por SQL directo como gapto_runtime ∥ revision). Contrato §6 y
    §10.1.4: el validador G2 espera en la financiacion y falla al COMMIT; sin write skew (mata MS-11). Estado final:
    capital = P = Σ capital de las cuotas; la revision confirma (200) y el UPDATE falla con INV-0354-G2."""
    lab = LabRev()
    ca, cb = clientes(lab)
    rev = lab.cuerpo_rev(desde="2027-04-01")
    capital = g2(lab)[0]

    def actualizar(app):
        def op(s):
            n = s.ejecutar("UPDATE gapto.financiaciones SET capital_original_contratado = "
                           "capital_original_contratado + 1000 WHERE entidad_id = %s", (lab.f,))
            assert n == 1
            _pausa(s)
            return "UPDATE confirmado"
        return lambda: unidad(app).ejecutar(ContextoOperacion.de_usuario(lab.owner, request_id=uuid.uuid4()), op,
                                            nombre="IC-12 UPDATE directo")
    if orden == "update_primero":
        t = intercalar("IC-12", actualizar(A), lambda: revisar(lab, cb, rev), espera=True, hilo=en_hilo_exc)
        upd, rv_ = t["_salidas"][0], t["B"]
    else:
        t = intercalar("IC-12", lambda: revisar(lab, ca, rev), actualizar(B), espera=True, hilo=en_hilo_exc)
        upd, rv_ = t["_salidas"][1], t["A"]
    datos = cerrar(f"IC-12_{orden}_rep{rep}", t, g2=g2(lab), capital_inicial=capital, versiones=len(lab.versiones()),
                   update=upd.get("e") or repr(upd.get("r")))
    esperado = FINANCIACION if orden == "update_primero" else {"fila:gapto.financiaciones"}
    assert set(datos["espera_b"]) & esperado, datos
    assert rv_ == (200, None) and datos["versiones"] == 2, datos
    assert "e" in upd and "INV-0354-G2" in upd["e"], datos
    assert datos["g2"][0] == capital, datos                                  # sin write skew
    assert_g2(lab, datos)


# ================================================================== IC-14
@pytest.mark.parametrize("orden", ["alta_primero", "retirada_primero"])
def test_ic14_retirada_de_recibir_ingreso_frente_a_alta_con_hipoteca(orden):
    """IC-14 (O-4 en concurrencia: retirada de RECIBIR_INGRESO de la cuenta de desembolso ∥ alta con hipoteca).
    Contrato (mandato §13.2): la retirada espera al FOR SHARE (alta primero: alta 200, retirada despues) o el alta
    rechaza con CUENTA_SIN_CAPACIDAD y 0 filas (retirada primero)."""
    lab = LabHip()
    ca, cb = clientes(lab)
    cuerpo = lab.peticion_hip()
    rv = lab.sql("SELECT row_version FROM gapto.cuentas WHERE id = %s", (lab.cd,))[0][0]
    ruta = f"/v1/cuentas/{lab.cd}/capacidades/RECIBIR_INGRESO/desactivar"
    fa = lambda cli: lambda: compra_en(cli, lab.pid, cuerpo)  # noqa: E731
    fr = lambda cli: lambda: cli.post(ruta, json={"row_version": rv}, headers=h.AUTH)  # noqa: E731
    if orden == "alta_primero":
        t = intercalar("IC-14", fa(ca), fr(cb), espera=True)
        alta_r, ret_r = t["A"], t["B"]
    else:
        t = intercalar("IC-14", fr(ca), fa(cb), espera=True)
        ret_r, alta_r = t["A"], t["B"]
    h0 = cuerpo["intencion_id"]
    filas = lab.sql("SELECT (SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s), "
                    "(SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = %s)", (h0, fin_de(cuerpo)))[0]
    cap = lab.sql("SELECT count(*) FROM gapto.cuenta_capacidades WHERE cuenta_id = %s "
                  "AND capacidad_codigo = 'RECIBIR_INGRESO'", (lab.cd,))[0][0]
    datos = cerrar(f"IC-14_{orden}", t, filas_compra=filas, recibir_ingreso=cap)
    assert datos["espera_b"], datos
    assert ret_r == (200, None) and cap == 0, datos
    if orden == "alta_primero":
        assert alta_r == (200, None) and filas == (1, 1), datos
        lab.f = fin_de(cuerpo)
        assert_g2(lab, datos)
    else:
        assert alta_r[1] == "CUENTA_SIN_CAPACIDAD" and filas == (0, 0), datos

# ================================================================== IC-12b
@pytest.mark.parametrize("rep", REPS)
def test_ic12b_cuota_de_mas_concurrente_numeracion(rep):
    """IC-12b (refuerzo del oraculo de MS-11, indicacion de Moises: «si MS-11 no muere con IC-12, reforzar el
    oraculo»). En IC-12 la serializacion la dan los locks de fila del UPDATE y de la revision, no el de G2, y el
    UPDATE falla G2 por la suma en cualquier caso. Aqui A y B insertan, como gapto_runtime y por SQL directo, la
    MISMA cuota N+1 (capital 0: Σ intacta; sin version: fuera del indice unico parcial) y fuerzan G2 antes de la
    pausa (SET CONSTRAINTS ALL IMMEDIATE). Con el lock de G2 (FOR NO KEY UPDATE de la financiacion) B espera en la
    fila de la financiacion, relee tras el COMMIT de A y falla con INV-0354-G2 (numeracion 1..N+2 rota): queda una
    sola N+1. Sin el lock (MS-11) B no espera y quedan dos cuotas N+1 (write skew de la numeracion)."""
    lab = LabRev()
    _, _, n_ini, _, max_ini = g2(lab)

    def insertar(app):
        def op(s):
            n = s.ejecutar(
                "INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
                "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
                "SELECT financiacion_entidad_id, numero_cuota + 1, fecha_vencimiento + 31, 0, 1, 0, 1 "
                "FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s "
                "ORDER BY numero_cuota DESC LIMIT 1", (lab.f,))
            assert n == 1
            s.ejecutar("SET CONSTRAINTS ALL IMMEDIATE")
            _pausa(s)
            return "INSERT confirmado"
        return lambda: unidad(app).ejecutar(ContextoOperacion.de_usuario(lab.owner, request_id=uuid.uuid4()), op,
                                            nombre="IC-12b INSERT directo")
    t = intercalar("IC-12b", insertar(A), insertar(B), espera=True, hilo=en_hilo_exc)
    ra, rb = t["_salidas"]
    datos = cerrar(f"IC-12b_rep{rep}", t, g2=g2(lab), max_inicial=max_ini,
                   a=ra.get("e") or repr(ra.get("r")), b=rb.get("e") or repr(rb.get("r")))
    # B espera DENTRO de G2 (sentencia SET CONSTRAINTS) sobre la transaccion de A: el FOR NO KEY UPDATE de la
    # financiacion espera directamente al xid de A (sin tuple lock visible en pg_locks, a diferencia de IC-12)
    assert any(f["app"] == B and not f["granted"] and f["locktype"] == "transactionid"
               and "SET CONSTRAINTS" in (f["query"] or "") for f in datos["pg_locks"]), datos
    assert "r" in ra and "e" not in ra, datos
    assert "e" in rb and "INV-0354-G2" in rb["e"], datos
    assert datos["g2"][2] == n_ini + 1 and datos["g2"][4] == max_ini + 1, datos   # una sola N+1
    assert_g2(lab, datos)
