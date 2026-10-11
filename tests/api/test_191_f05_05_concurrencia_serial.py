# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_191_f05_05_concurrencia_serial.py
# Ruta: tests/api/test_191_f05_05_concurrencia_serial.py
# Descripcion: Bateria SERIAL y determinista de concurrencia de F05-05 (K3
#   §3; F05 §49.5 R9/R16, §49.9 caso 11; AJ-F0505-02; WM 12C.1), con el
#   patron de test_190. FUERA de la suite general: solo se ejecuta con
#   GAPTO_F0505_CONCURRENCIA=1. Si GAPTO_F0505_EVIDENCIA apunta a una
#   carpeta, cada escenario deja alli su JSON con pg_locks.
#   Tecnica (escenarios AF): una sesion BARRERA retiene un lock; los comandos
#   se lanzan uno a uno y cada uno debe quedar ESPERANDO (bloqueo directo o
#   transitivo) antes del siguiente; al liberar, PostgreSQL concede en orden.
#   Escenarios:
#     AF1 alta de afinidad frente a desactivar el tercero (dos ordenes);
#     AF2 alta de afinidad frente a desactivar la categoria (dos ordenes);
#     AF3 dos altas del mismo par: la segunda es idempotente con aviso;
#     AF4 alta frente a registro con ese tercero (dos ordenes): ambas, y el
#         registro sigue sin tomar el advisory TERCEROS (F05-D032 C2);
#     AFX variantes PROHIBIDAS por R9 (pruebas negativas que ESPERAN 40P01),
#         con sesiones SQL paso a paso como el arnes de K1-PRE P4:
#         X1 categoria NKU (R16 literal) frente al registro, y el control con
#            FOR SHARE (el orden vigente) que NO interbloquea;
#         X2 dos categorias en una transaccion frente a desactivar la rama, y
#            el control con una sola categoria que NO interbloquea.
#   Espera de los pasos tras liberar la barrera: GAPTO_F0505_JOIN_TIMEOUT_S
#   (por defecto 30 s en base local y 300 s en proveedor remoto).
# Version: 0.1.0 (F05-05 K3 §3)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F0505_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F0505_CONCURRENCIA=1)")
GASTO = "/v1/intenciones/gasto-pagado"
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


# ------------------------------------------------------------------ utilidades (patron de test_190)
def _espera_join_s() -> float:
    valor = os.getenv("GAPTO_F0505_JOIN_TIMEOUT_S")
    if valor:
        return float(valor)
    host = conninfo_to_dict(h.dsn()).get("host", "")
    return 30.0 if host == "" or host.startswith("/") or host in HOSTS_LOCALES else 300.0


def _evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_F0505_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=2, default=str, ensure_ascii=False), encoding="utf-8")


def _barrera_fila(owner, sql: str, params: tuple):
    c = fh.sesion_owner(owner)
    c.execute(sql, params)
    return c


def _barrera_advisory(owner, clave: str):
    c = fh.sesion_owner(owner)
    c.execute(f"SELECT pg_advisory_xact_lock(hashtext('gapto:{clave}'), hashtext(%s::uuid::text))", (str(owner),))
    return c


def _bloqueados(pid_x: int, minimo: int, limite: float = 10.0) -> list[int]:
    fin = time.monotonic() + limite
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            filas = mon.execute("SELECT pid, pg_blocking_pids(pid), backend_start FROM pg_stat_activity "
                                "WHERE cardinality(pg_blocking_pids(pid)) > 0").fetchall()
            bloqueados, cambio = set(), True
            while cambio:
                cambio = False
                for pid, por, _ in filas:
                    if pid not in bloqueados and (pid_x in por or bloqueados & set(por)):
                        bloqueados.add(pid)
                        cambio = True
            pids = [f[0] for f in sorted(filas, key=lambda f: f[2]) if f[0] in bloqueados]
            if len(pids) >= minimo:
                return pids
            time.sleep(0.05)
    return []


def _locks(pid: int) -> list[dict]:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        filas = mon.execute(
            "SELECT locktype, mode, granted, classid, objid, objsubid, relation::regclass::text "
            "FROM pg_locks WHERE pid = %s ORDER BY granted DESC, locktype", (pid,)).fetchall()
    claves = ("locktype", "mode", "granted", "classid", "objid", "objsubid", "relacion")
    return [dict(zip(claves, f)) for f in filas]


def _clave_advisory(owner, clave: str) -> tuple[int, int]:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        a, b = c.execute("SELECT hashtext(%s), hashtext(%s::uuid::text)", (f"gapto:{clave}", str(owner))).fetchone()
    return a & 0xFFFFFFFF, b & 0xFFFFFFFF


def _tiene_advisory(locks: list[dict], clave: tuple[int, int]) -> bool:
    return any(l["locktype"] == "advisory" and l["granted"] and (l["classid"], l["objid"]) == clave for l in locks)


def _serie(barrera, pasos: list, nombre: str, inspeccion=None) -> dict:
    salida: dict = {}
    duraciones: dict = {}
    hilos = []
    evid: dict = {"escenario": nombre, "pasos": [p[0] for p in pasos]}

    def _ejecutar(clave, fn):
        inicio = time.monotonic()
        salida[clave] = fn()
        duraciones[clave] = round(time.monotonic() - inicio, 3)

    try:
        pid_x = fh.pid_servidor(barrera)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilo = threading.Thread(target=_ejecutar, args=(clave, fn))
            hilo.start()
            hilos.append(hilo)
            pids = _bloqueados(pid_x, n)
            assert len(pids) >= n, f"{clave} no espero a la barrera"
            evid[f"locks_{clave}"] = _locks(pids[n - 1])
        assert not salida, "algun paso termino sin esperar a la barrera"
        if inspeccion:
            evid["inspeccion"] = inspeccion(evid)
        barrera.execute("COMMIT")
    finally:
        barrera.close()
    espera = _espera_join_s()
    evid["espera_join_s"] = espera
    for hilo in hilos:
        hilo.join(timeout=espera)
        assert not hilo.is_alive()
    evid["duracion_s"] = duraciones
    evid["resultado"] = {k: (v.status_code, v.json()) if hasattr(v, "status_code") else repr(v) for k, v in salida.items()}
    _evidencia(nombre, evid)
    return salida


def _cod(r):
    return r.json().get("codigo")


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    corriente = h.crear_cuenta(owner, [(actor, 100)], tipo="CORRIENTE")
    tid = uuid.uuid4()
    assert cli.post("/v1/terceros", json={"id": str(tid), "nombre": "ALDI"}, headers=h.AUTH).status_code == 200
    cat = ph.categoria(owner, "Supermercados")
    return owner, cli, corriente, tid, cat


def _alta(cli, tid, cat, aid=None):
    return lambda: cli.post("/v1/afinidades", json={"id": str(aid or uuid.uuid4()), "tercero_id": str(tid),
                                                    "categoria_id": str(cat)}, headers=h.AUTH)


def _afinidades(owner, tid) -> list[str]:
    return sorted(str(f[0]) for f in h.leer(owner, "SELECT categoria_id FROM gapto.tercero_afinidades WHERE tercero_id=%s", (tid,)))


# ------------------------------------------------------------------ AF1 / AF2 caso 11
@pytest.mark.parametrize("primero", ["alta", "desactivar"])
def test_af1_alta_frente_a_desactivar_tercero(t, primero):
    owner, cli, _, tid, cat = t
    barrera = _barrera_advisory(owner, "TERCEROS")  # los dos writers toman TERCEROS primero
    pasos = {"alta": _alta(cli, tid, cat),
             "desactivar": lambda: cli.post(f"/v1/terceros/{tid}/desactivar", json={"row_version": 1}, headers=h.AUTH)}
    segundo = "desactivar" if primero == "alta" else "alta"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"AF1_tercero_{primero}")
    assert all(r.status_code != 500 for r in salida.values()), "40P01 no reintentado o error interno"
    if primero == "alta":
        assert salida["alta"].status_code == 200 and _afinidades(owner, tid) == [str(cat)]
        # R9: el alta sube row_version del tercero; la desactivacion con la version leida antes queda desfasada.
        assert _cod(salida["desactivar"]) == "VERSION_DESFASADA"
    else:
        assert salida["desactivar"].status_code == 200
        assert _cod(salida["alta"]) == "TERCERO_NO_ELEGIBLE" and _afinidades(owner, tid) == []


@pytest.mark.parametrize("primero", ["alta", "desactivar"])
def test_af2_alta_frente_a_desactivar_categoria(t, primero):
    owner, cli, _, tid, cat = t
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.categorias_financieras WHERE id=%s FOR UPDATE", (cat,))
    pasos = {"alta": _alta(cli, tid, cat),
             "desactivar": lambda: cli.post(f"/v1/categorias/{cat}/desactivar",
                                            json={"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS", "row_version": 1}, headers=h.AUTH)}
    segundo = "desactivar" if primero == "alta" else "alta"

    def inspeccion(evid):
        # La categoria se pide FOR SHARE (R9), nunca NKU: el alta espera con un tuple lock compartido.
        modos = [l["mode"] for l in evid["locks_alta"] if l["locktype"] in ("tuple", "transactionid") and not l["granted"]]
        return {"alta_esperando": modos}

    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"AF2_categoria_{primero}", inspeccion)
    assert all(r.status_code != 500 for r in salida.values())
    assert salida["desactivar"].status_code == 200
    if primero == "alta":
        assert salida["alta"].status_code == 200 and _afinidades(owner, tid) == [str(cat)]
    else:
        assert _cod(salida["alta"]) == "CATEGORIA_NO_ELEGIBLE" and _afinidades(owner, tid) == []


# ------------------------------------------------------------------ AF3 dos altas del mismo par
def test_af3_dos_altas_del_mismo_par(t):
    owner, cli, _, tid, cat = t
    a, b = uuid.uuid4(), uuid.uuid4()
    barrera = _barrera_advisory(owner, "TERCEROS")
    salida = _serie(barrera, [("A", _alta(cli, tid, cat, a)), ("B", _alta(cli, tid, cat, b))], "AF3_mismo_par")
    assert salida["A"].status_code == salida["B"].status_code == 200
    assert salida["A"].json()["idempotente"] is False
    assert salida["B"].json()["idempotente"] is True and salida["B"].json()["aviso"] == "AFINIDAD_YA_EXISTE"
    assert salida["B"].json()["afinidad"]["id"] == str(a)
    assert h.leer(owner, "SELECT count(*) FROM gapto.tercero_afinidades WHERE tercero_id=%s", (tid,))[0][0] == 1


# ------------------------------------------------------------------ AF4 alta frente a registro
@pytest.mark.parametrize("primero", ["alta", "registro"])
def test_af4_alta_frente_a_registro_con_el_tercero(t, primero):
    owner, cli, corriente, tid, cat = t
    clave = _clave_advisory(owner, "TERCEROS")
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.terceros WHERE id=%s FOR UPDATE", (tid,))
    cuerpo = h.intencion(corriente, tercero_id=str(tid), categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    pasos = {"alta": _alta(cli, tid, cat), "registro": lambda: cli.post(GASTO, json=cuerpo, headers=h.AUTH)}
    segundo = "registro" if primero == "alta" else "alta"

    def inspeccion(evid):
        assert not _tiene_advisory(evid["locks_registro"], clave), "el registro toma el advisory TERCEROS"
        assert _tiene_advisory(evid["locks_alta"], clave), "el alta espera el tercero sin el advisory TERCEROS"
        return {"registro_sin_TERCEROS": True, "alta_con_TERCEROS": True}

    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"AF4_registro_{primero}", inspeccion)
    assert salida["alta"].status_code == 200 and salida["registro"].status_code == 200
    assert _afinidades(owner, tid) == [str(cat)]


# ------------------------------------------------------------------ AFX variantes prohibidas (esperan 40P01)
class _Paso:
    """Sesion SQL paso a paso (gapto_owner + GUC del tenant). Un paso que
    debe bloquear se lanza en un hilo; los demas, en linea."""

    def __init__(self, owner):
        self.c = fh.sesion_owner(owner)
        self.pid = fh.pid_servidor(self.c)
        self.error: Exception | None = None
        self.hilo: threading.Thread | None = None

    def ya(self, sql, params=()):
        self.c.execute(sql, params)

    def en_hilo(self, sql, params=()):
        def _run():
            try:
                self.c.execute(sql, params)
            except Exception as exc:  # se afirma despues
                self.error = exc
        self.hilo = threading.Thread(target=_run)
        self.hilo.start()

    def intentar(self, sql, params=()):
        try:
            self.c.execute(sql, params)
        except Exception as exc:
            self.error = exc

    def cerrar(self):
        if self.hilo:
            self.hilo.join(timeout=_espera_join_s())
        try:
            self.c.rollback()
        finally:
            self.c.close()


ADV = "SELECT pg_advisory_xact_lock(hashtext('gapto:{k}'), hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
_40P01 = psycopg.errors.DeadlockDetected


def _esperando(pid: int) -> bool:
    fin = time.monotonic() + 8.0
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            if mon.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", (pid,)).fetchone()[0]:
                return True
            time.sleep(0.05)
    return False


@pytest.mark.parametrize("modo", ["FOR NO KEY UPDATE", "FOR SHARE"])
def test_afx1_categoria_nku_frente_al_registro(t, modo):
    """Afinidad con la categoria en NKU (R16 literal, PROHIBIDO) frente al
    orden del registro (categoria FS -> tercero FS): 40P01. Con FOR SHARE
    (orden vigente de R9) no hay ciclo."""
    owner, _, corriente, tid, cat = t
    af, rg = _Paso(owner), _Paso(owner)
    evid: dict = {"variante": modo}
    try:
        af.ya(ADV.format(k="TERCEROS"))
        af.ya("SELECT enabled FROM gapto.terceros WHERE id=%s FOR NO KEY UPDATE", (tid,))
        rg.ya("SELECT id FROM gapto.cuentas WHERE id=%s FOR NO KEY UPDATE", (corriente,))
        rg.ya("SELECT enabled FROM gapto.categorias_financieras WHERE id=%s FOR SHARE", (cat,))
        rg.en_hilo("SELECT enabled FROM gapto.terceros WHERE id=%s FOR SHARE", (tid,))
        assert _esperando(rg.pid), "el registro no espera el tercero"
        evid["locks_registro"] = _locks(rg.pid)
        af.intentar(f"SELECT enabled FROM gapto.categorias_financieras WHERE id=%s {modo}", (cat,))
        if af.error is None:
            evid["locks_afinidad"] = _locks(af.pid)
            af.c.execute("COMMIT")
    finally:
        af.cerrar()
        rg.cerrar()
    errores = [e for e in (af.error, rg.error) if e is not None]
    evid["errores"] = [repr(e) for e in errores]
    _evidencia(f"AFX1_{modo.replace(' ', '_')}", evid)
    if modo == "FOR NO KEY UPDATE":
        assert len(errores) == 1 and isinstance(errores[0], _40P01), f"se esperaba 40P01: {errores}"
    else:
        assert errores == [], f"el orden vigente no debe interbloquear: {errores}"


@pytest.mark.parametrize("variante", ["DOS_CATEGORIAS", "UNA_CATEGORIA"])
def test_afx2_dos_categorias_en_una_transaccion_frente_a_desactivar_rama(t, variante):
    """Afinidades de hijo y padre en UNA transaccion (PROHIBIDO por R9)
    frente a desactivar la rama (nodo NKU -> descendientes NKU): 40P01. Con
    una sola categoria por transaccion no hay ciclo."""
    owner, _, _, tid, padre = t
    hijo = ph.categoria(owner, "Hijo", parent_id=padre)
    af, rama = _Paso(owner), _Paso(owner)
    evid: dict = {"variante": variante}
    try:
        af.ya(ADV.format(k="TERCEROS"))
        af.ya("SELECT enabled FROM gapto.terceros WHERE id=%s FOR NO KEY UPDATE", (tid,))
        if variante == "DOS_CATEGORIAS":
            af.ya("SELECT enabled FROM gapto.categorias_financieras WHERE id=%s FOR SHARE", (hijo,))
        rama.ya(ADV.format(k="CATEGORIAS"))
        rama.ya("SELECT enabled FROM gapto.categorias_financieras WHERE id=%s FOR NO KEY UPDATE", (padre,))
        rama.en_hilo("SELECT enabled FROM gapto.categorias_financieras WHERE id = ANY(%s::uuid[]) ORDER BY id "
                     "FOR NO KEY UPDATE", ([str(hijo)],))
        if variante == "DOS_CATEGORIAS":
            assert _esperando(rama.pid), "la rama no espera el hijo"
            evid["locks_rama"] = _locks(rama.pid)
            af.intentar("SELECT enabled FROM gapto.categorias_financieras WHERE id=%s FOR SHARE", (padre,))
        else:
            rama.hilo.join(timeout=_espera_join_s())
            af.en_hilo("SELECT enabled FROM gapto.categorias_financieras WHERE id=%s FOR SHARE", (padre,))
            assert _esperando(af.pid), "la afinidad no espera el padre"
            evid["locks_afinidad"] = _locks(af.pid)
            rama.c.execute("COMMIT")
    finally:
        rama.cerrar()
        af.cerrar()
    errores = [e for e in (af.error, rama.error) if e is not None]
    evid["errores"] = [repr(e) for e in errores]
    _evidencia(f"AFX2_{variante}", evid)
    if variante == "DOS_CATEGORIAS":
        assert len(errores) == 1 and isinstance(errores[0], _40P01), f"se esperaba 40P01: {errores}"
    else:
        assert errores == [], f"una sola categoria no debe interbloquear: {errores}"
