# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_163_f05_01_magnitudes_concurrencia.py
# Ruta: tests/api/test_163_f05_01_magnitudes_concurrencia.py
# Descripcion: Concurrencia de S7-MAG (F05-D020 D-MAG-03/04; AJ-S7MAG-02/03;
#   R16 verificable). Interleavings forzados con barrera explicita (WM 12C.1,
#   patron test_156): el bloqueo se OBSERVA en pg_stat_activity /
#   pg_blocking_pids con el PID real (pg_backend_pid()).
#     - todo escritor de magnitudes (8 comandos) espera el advisory;
#     - R-15: dos escritores del catalogo se serializan por el advisory
#       (nombre normalizado y posicion n contigua);
#     - R-01: el escritor de asociaciones espera al FOR SHARE de C07 sobre la
#       categoria y, en sentido inverso, C07 espera al FOR NO KEY UPDATE del
#       escritor y revalida tras su confirmacion (sin deadlock);
#     - R-02: deshabilitar frente a C07: C07 espera la fila de la magnitud y
#       rechaza tras la confirmacion del escritor;
#     - CE-S7MAG-02: asociacion eliminada y recreada entre la lectura y el
#       comando -> ASOCIACION_NO_EXISTE / CONJUNTO_MAGNITUDES_DESFASADO;
#     - CE-S7MAG-07: el impacto cambia entre la consulta y la confirmacion ->
#       nueva confirmacion con el conjunto nuevo.
#   El escritor "a mitad de transaccion" ejecuta el SERVICIO real en una
#   transaccion abierta a mano (rol gapto_runtime y GUC del tenant como la
#   UdT) y confirma cuando el test lo decide.
#   Base local desechable 0001..0340 (estos tests confirman filas).
# Version: 0.1.0 (F05-01 S7-MAG)
# ============================================================

from __future__ import annotations

import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.magnitudes import servicio as serv_mag

URL_REGISTRO = "/v1/intenciones/gasto-pagado"


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, cuenta, h.cliente(owner)


def _lanzar(salida: dict, clave: str, fn) -> threading.Thread:
    t = threading.Thread(target=lambda: salida.update({clave: fn()}))
    t.start()
    return t


def _esperar(hilos) -> None:
    for t in hilos:
        t.join(timeout=20)
        assert not t.is_alive()


def _barrera(owner, pasos: list, durante=None) -> dict:
    """Retiene el advisory, lanza los pasos en orden (cada uno debe quedar
    bloqueado antes del siguiente), ejecuta `durante(x)` en la sesion que lo
    retiene y libera."""
    salida: dict = {}
    x = fh.retener_advisory(owner)
    hilos = []
    try:
        pid_x = fh.pid_servidor(x)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilos.append(_lanzar(salida, clave, fn))
            assert fh.esperar_bloqueo((pid_x,), minimo=n), f"{clave} no espero el advisory"
        assert not salida, "algun comando termino sin esperar el advisory"
        if durante is not None:
            durante(x)
        x.execute("COMMIT")
    finally:
        x.close()
    _esperar(hilos)
    return salida


def _bloqueados_por(pid: int, *, advisory: bool | None = None, limite_s: float = 8.0) -> list[int]:
    """PIDs de esta base bloqueados por `pid` (pg_blocking_pids). Con
    advisory=False exige que lo esperado NO sea un lock advisory (lock de fila)."""
    filtro = ""
    if advisory is True:
        filtro = " AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid = a.pid AND l.locktype = 'advisory' AND NOT l.granted)"
    elif advisory is False:
        filtro = (" AND NOT EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid = a.pid AND l.locktype = 'advisory' "
                  "AND NOT l.granted)")
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            pids = [f[0] for f in mon.execute(
                "SELECT a.pid FROM pg_stat_activity a WHERE a.datname = current_database() "
                "AND %s = ANY(pg_blocking_pids(a.pid))" + filtro, (pid,)).fetchall()]
            if pids:
                return pids
            time.sleep(0.05)
    return []


class _EscritorAbierto:
    """Ejecuta un comando del servicio real en una transaccion que el test confirma."""

    def __init__(self, owner):
        self.conexion = psycopg.connect(h.dsn(), autocommit=True)
        self._tx = self.conexion.transaction()
        self._tx.__enter__()
        contexto = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
        UnidadDeTrabajo(lambda: None, rol_runtime="gapto_runtime")._fijar_contexto(self.conexion, contexto)
        self.sesion = SesionMotor(self.conexion, contexto, 1)
        self.pid = fh.pid_servidor(self.conexion)

    def confirmar(self) -> None:
        self._tx.__exit__(None, None, None)
        self.conexion.close()

    def abortar(self) -> None:
        try:
            self._tx.__exit__(RuntimeError, RuntimeError("abortado"), None)
        except RuntimeError:
            pass
        self.conexion.close()


def _post(cli, ruta, cuerpo):
    return cli.post(ruta, json=cuerpo, headers=h.AUTH)


def _registro(cli, cuenta, cat, magnitudes=None):
    categoria = {"estado": "CATEGORIA", "categoria_id": str(cat)}
    if magnitudes is not None:
        categoria["magnitudes"] = [{"magnitud_id": str(m), "valor": v} for m, v in magnitudes]
    return lambda: _post(cli, URL_REGISTRO, h.intencion(cuenta, categoria=categoria))


# ------------------------------------------------------------------ todo escritor espera el advisory
def _preparar(owner):
    cat = fh.crear_categoria(owner, "Luz")
    m1, m2, libre = h.crear_magnitud(owner, "A"), h.crear_magnitud(owner, "B"), h.crear_magnitud(owner, "Libre")
    a1 = h.crear_asociacion(owner, cat, m1, obligatoria=False, orden=0)
    a2 = h.crear_asociacion(owner, cat, m2, obligatoria=False, orden=1)
    return cat, (a1, m1), (a2, m2), libre


_COMANDOS = {
    "asociar": lambda cli, cat, x, y, libre: _post(cli, f"/v1/categorias/{cat}/magnitudes", {
        "origen": "EXISTENTE", "magnitud_id": str(libre), "obligatoria": True}),
    "alta_rapida": lambda cli, cat, x, y, libre: _post(cli, f"/v1/categorias/{cat}/magnitudes", {
        "origen": "NUEVA", "obligatoria": False, "magnitud": {"magnitud_id": str(uuid.uuid4()), "nombre": "Nueva",
                                                              "unidad_default": "u", "precision_decimales": 0}}),
    "obligatoria": lambda cli, cat, x, y, libre: _post(cli, f"/v1/categorias/{cat}/magnitudes/{x[0]}/obligatoria", {
        "magnitud_id": str(x[1]), "obligatoria_actual": False, "obligatoria": True}),
    "retirar": lambda cli, cat, x, y, libre: _post(cli, f"/v1/categorias/{cat}/magnitudes/{x[0]}/retirar", {
        "magnitud_id": str(x[1]), "obligatoria_actual": False}),
    "reordenar": lambda cli, cat, x, y, libre: _post(cli, f"/v1/categorias/{cat}/magnitudes/reordenar", {
        "asociaciones": [{"asociacion_id": str(y[0]), "magnitud_id": str(y[1]), "orden": 1, "obligatoria": False},
                         {"asociacion_id": str(x[0]), "magnitud_id": str(x[1]), "orden": 0, "obligatoria": False}]}),
    "renombrar": lambda cli, cat, x, y, libre: _post(cli, f"/v1/magnitudes/{libre}/renombrar",
                                                     {"nombre": "Libre 2", "row_version": 1}),
    "deshabilitar": lambda cli, cat, x, y, libre: _post(cli, f"/v1/magnitudes/{libre}/deshabilitar",
                                                        {"row_version": 1, "confirmacion_impacto": None}),
}


@pytest.mark.parametrize("comando", sorted(_COMANDOS) + ["rehabilitar"])
def test_todo_escritor_de_magnitudes_espera_el_advisory(ctx, comando):
    owner, _, cli = ctx
    cat, x, y, libre = _preparar(owner)
    if comando == "rehabilitar":
        h.como_owner(owner, "UPDATE gapto.magnitudes SET enabled = false WHERE id = %s", (libre,))
        fn = lambda: _post(cli, f"/v1/magnitudes/{libre}/rehabilitar", {"row_version": 1})  # noqa: E731
    else:
        fn = lambda: _COMANDOS[comando](cli, cat, x, y, libre)  # noqa: E731
    salida: dict = {}
    retenedor = fh.retener_advisory(owner)
    try:
        t = _lanzar(salida, comando, fn)
        assert len(_bloqueados_por(fh.pid_servidor(retenedor), advisory=True)) == 1, f"{comando} no espera el advisory"
        assert not salida
        retenedor.execute("COMMIT")
    finally:
        retenedor.close()
    _esperar([t])
    assert salida[comando].status_code == 200, salida[comando].text


# ------------------------------------------------------------------ R-15
def test_dos_altas_rapidas_con_nombre_normalizado_igual_se_serializan(ctx):
    owner, _, cli = ctx
    c1, c2 = fh.crear_categoria(owner, "Uno"), fh.crear_categoria(owner, "Dos")

    def alta(cat, nombre):
        return lambda: _post(cli, f"/v1/categorias/{cat}/magnitudes", {"origen": "NUEVA", "obligatoria": True,
                             "magnitud": {"magnitud_id": str(uuid.uuid4()), "nombre": nombre,
                                          "unidad_default": "h", "precision_decimales": 0}})

    salida = _barrera(owner, [("a", alta(c1, "Horas extra")), ("b", alta(c2, "HORAS  EXTRA"))])
    codigos = sorted((r.status_code, r.json().get("codigo")) for r in salida.values())
    assert codigos == [(200, None), (409, "MAGNITUD_NOMBRE_DUPLICADO")], codigos
    assert h.leer(owner, "SELECT count(*) FROM gapto.magnitudes") == [(1,)]


def test_dos_asociaciones_concurrentes_quedan_contiguas(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Coche")
    m1, m2 = h.crear_magnitud(owner, "A"), h.crear_magnitud(owner, "B")
    asociar = lambda m: lambda: _post(cli, f"/v1/categorias/{cat}/magnitudes",  # noqa: E731
                                      {"origen": "EXISTENTE", "magnitud_id": str(m), "obligatoria": False})
    salida = _barrera(owner, [("a", asociar(m1)), ("b", asociar(m2))])
    assert all(r.status_code == 200 for r in salida.values())
    assert sorted(o for *_, o in h.asociaciones_persistidas(owner, cat)) == [0, 1]


# ------------------------------------------------------------------ R-01 (R16)
def test_escritor_de_asociacion_espera_al_for_share_de_c07(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), h.crear_magnitud(owner)
    lector = fh.sesion_owner(owner)  # registro en curso: C07 ya tomo la categoria FOR SHARE
    salida: dict = {}
    try:
        lector.execute("SELECT id FROM gapto.categorias_financieras WHERE id = %s FOR SHARE", (cat,))
        t = _lanzar(salida, "w", lambda: _post(cli, f"/v1/categorias/{cat}/magnitudes", {
            "origen": "EXISTENTE", "magnitud_id": str(mid), "obligatoria": True}))
        assert _bloqueados_por(fh.pid_servidor(lector), advisory=False), "el escritor no espero el FOR SHARE de C07"
        assert not salida and h.asociaciones_persistidas(owner, cat) == []
        lector.execute("COMMIT")
    finally:
        lector.close()
    _esperar([t])
    assert salida["w"].status_code == 200, salida["w"].text


def test_c07_espera_al_escritor_de_asociacion_y_revalida(ctx):
    owner, cuenta, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), h.crear_magnitud(owner)
    escritor = _EscritorAbierto(owner)
    salida: dict = {}
    try:
        r = serv_mag.asociar(escritor.sesion, categoria_id=cat, magnitud_id=mid, obligatoria=True)
        assert isinstance(r, serv_mag.ResultadoAsociacion)
        t = _lanzar(salida, "registro", _registro(cli, cuenta, cat))  # sin la magnitud ahora obligatoria
        assert _bloqueados_por(escritor.pid, advisory=False), "C07 no espero al escritor (R16)"
        assert not salida
        escritor.confirmar()
    except BaseException:
        escritor.abortar()
        raise
    _esperar([t])
    r = salida["registro"]
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_OBLIGATORIA_AUSENTE", r.text


# ------------------------------------------------------------------ R-02
def test_deshabilitar_frente_a_c07_rechaza_tras_la_confirmacion(ctx):
    owner, cuenta, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), h.crear_magnitud(owner, precision=2)
    h.crear_asociacion(owner, cat, mid, obligatoria=True)
    escritor = _EscritorAbierto(owner)
    salida: dict = {}
    try:
        r = serv_mag.deshabilitar(escritor.sesion, magnitud_id=mid, row_version=1, confirmacion_impacto=[cat])
        assert isinstance(r, serv_mag.ResultadoMagnitud)
        t = _lanzar(salida, "registro", _registro(cli, cuenta, cat, [(mid, "1.5")]))
        assert _bloqueados_por(escritor.pid, advisory=False), "C07 no espero la magnitud bloqueada"
        assert not salida
        escritor.confirmar()
    except BaseException:
        escritor.abortar()
        raise
    _esperar([t])
    r = salida["registro"]
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_MAGNITUD_NO_DISPONIBLE", r.text


# ------------------------------------------------------------------ CE-S7MAG-02
def _recrear(owner, cat, aid, mid):
    def durante(x):
        x.execute("DELETE FROM gapto.categoria_magnitudes WHERE id = %s", (aid,))
        x.execute("INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
                  "VALUES (%s, %s, %s, false, 0)", (uuid.uuid4(), cat, mid))
    return durante


def test_obligatoria_tras_eliminar_y_recrear_la_asociacion(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), h.crear_magnitud(owner)
    aid = h.crear_asociacion(owner, cat, mid, obligatoria=False)
    salida = _barrera(owner, [("c", lambda: _post(cli, f"/v1/categorias/{cat}/magnitudes/{aid}/obligatoria", {
        "magnitud_id": str(mid), "obligatoria_actual": False, "obligatoria": True}))],
        durante=_recrear(owner, cat, aid, mid))
    assert salida["c"].status_code == 409 and salida["c"].json()["codigo"] == "ASOCIACION_NO_EXISTE"
    assert [ob for _, _, ob, _ in h.asociaciones_persistidas(owner, cat)] == [False]


def test_reordenar_tras_eliminar_y_recrear_la_asociacion(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Coche")
    ma, mb = h.crear_magnitud(owner, "A"), h.crear_magnitud(owner, "B")
    a = h.crear_asociacion(owner, cat, ma, obligatoria=False, orden=0)
    b = h.crear_asociacion(owner, cat, mb, obligatoria=False, orden=1)

    def durante(x):
        x.execute("DELETE FROM gapto.categoria_magnitudes WHERE id = %s", (b,))
        x.execute("INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
                  "VALUES (%s, %s, %s, false, 1)", (uuid.uuid4(), cat, mb))

    salida = _barrera(owner, [("e", lambda: _post(cli, f"/v1/categorias/{cat}/magnitudes/reordenar", {"asociaciones": [
        {"asociacion_id": str(b), "magnitud_id": str(mb), "orden": 1, "obligatoria": False},
        {"asociacion_id": str(a), "magnitud_id": str(ma), "orden": 0, "obligatoria": False}]}))], durante=durante)
    assert salida["e"].status_code == 409 and salida["e"].json()["codigo"] == "CONJUNTO_MAGNITUDES_DESFASADO"
    assert h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE motivo LIKE 'F05-01 MAG_%%'") == [(0,)]


# ------------------------------------------------------------------ CE-S7MAG-07
def test_impacto_cambia_entre_consulta_y_confirmacion(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner, "Consumo")
    c1, c2 = fh.crear_categoria(owner, "Luz"), fh.crear_categoria(owner, "Transporte")
    h.crear_asociacion(owner, c1, mid, obligatoria=True)
    url = f"/v1/magnitudes/{mid}/deshabilitar"
    consulta = _post(cli, url, {"row_version": 1, "confirmacion_impacto": None}).json()
    confirmadas = [c["categoria_id"] for c in consulta["detalle"]["categorias_no_capturables"]]
    assert confirmadas == [str(c1)]

    def durante(x):
        x.execute("INSERT INTO gapto.categoria_magnitudes (categoria_id, magnitud_id, obligatoria) "
                  "VALUES (%s, %s, true)", (c2, mid))

    salida = _barrera(owner, [("g", lambda: _post(cli, url, {"row_version": 1, "confirmacion_impacto": confirmadas}))],
                      durante=durante)
    r = salida["g"]
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION", r.text
    assert sorted(c["categoria_id"] for c in r.json()["detalle"]["categorias_no_capturables"]) == sorted(
        [str(c1), str(c2)])
    assert h.magnitud_persistida(owner, mid)[3] is True
