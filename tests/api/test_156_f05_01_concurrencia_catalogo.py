# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_156_f05_01_concurrencia_catalogo.py
# Ruta: tests/api/test_156_f05_01_concurrencia_catalogo.py
# Descripcion: Concurrencia del catalogo de categorias (F05-01, S5; §22.5;
#   AJ-S4-01/02). Interleaving forzado con barrera explicita (WM 12C.1): una
#   sesion retiene el advisory (CATEGORIAS, owner); los comandos quedan
#   ESPERANDO (se observa en pg_stat_activity) y al liberarla se serializan
#   en orden de llegada.
#     - cada uno de los 9 comandos toma el advisory ANTES de escribir;
#     - unicidad normalizada en las seis combinaciones alta / renombrado /
#       reactivacion, con literales distintos ("Café" / "cafe") para que la
#       UNIQUE fisica literal no pueda salvar el caso: solo el advisory +
#       normalizacion lo impiden;
#     - desactivar RAMA frente a alta bajo un descendiente, en ambos ordenes:
#       nunca queda un nodo activo bajo un ancestro recien desactivado.
#   Base local desechable 0001..0340 (estos tests confirman filas).
#
#   v0.2.0 (F05-01 S6-ICONO (F05-D013), AJ-ICON-06): el comando de icono
#   entra en la bateria de advisory. Ademas se observa que la sesion del
#   comando esta bloqueada POR la que retiene el advisory
#   (pg_blocking_pids, con el PID real de pg_backend_pid()) y que lo que
#   espera es un lock advisory no concedido.
#
#   v0.3.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): `reordenar` entra en la
#   bateria de advisory (9 comandos; cosmetico §30.6: el recuento de la
#   cabecera decia 7). Caso especifico: la sesion A retiene el advisory y la
#   B reordena y queda bloqueada POR A (pg_blocking_pids / pg_backend_pid);
#   al liberar, B aplica sobre el estado actual si A no cambio nada, o
#   rechaza sin escritura con CONJUNTO_HERMANOS_DESFASADO (A anadio un
#   hermano) o VERSION_DESFASADA (A cambio un hermano).
#   Ademas, el lock de filas del conjunto (FOR NO KEY UPDATE en la lectura de
#   hermanos) frente a un escritor que NO toma el advisory: reordenar espera
#   la fila y ve la version nueva (VERSION_DESFASADA); sin ese lock leeria la
#   version antigua y aplicaria encima (perdida de actualizacion).
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

B = fh.BASE


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _lanzar(salida: dict, clave: str, fn) -> threading.Thread:
    t = threading.Thread(target=lambda: salida.update({clave: fn()}))
    t.start()
    return t


def _barrera(owner, pasos: list):
    """Retiene el advisory, lanza los pasos en orden (esperando a que cada uno
    quede bloqueado antes de lanzar el siguiente) y libera. Devuelve las
    respuestas por clave."""
    salida: dict = {}
    x = fh.retener_advisory(owner)
    hilos = []
    try:
        pid_x = fh.pid_servidor(x)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilos.append(_lanzar(salida, clave, fn))
            assert fh.esperar_bloqueo((pid_x,), minimo=n), f"{clave} no espero el advisory"
        assert not salida, "algun comando termino sin esperar el advisory"
        x.execute("COMMIT")
    finally:
        x.close()
    for t in hilos:
        t.join(timeout=20)
        assert not t.is_alive()
    return salida


# ------------------------------------------------------------ advisory en todos
def _preparar(owner, cli):
    padre, _ = fh.alta(cli, "Padre")
    nodo, _ = fh.alta(cli, "Nodo")
    return padre, nodo


_COMANDOS = {
    "alta": lambda cli, p, n: fh.alta(cli, "Nueva")[1],
    "renombrar": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/renombrar", {"nombre": "Nodo 2", "row_version": 1}),
    "mover": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/mover", {"parent_id": str(p), "row_version": 1}),
    "orden": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/orden", {"orden": 4, "row_version": 1}),
    "ambito": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/ambito", {"ambito": "AMBOS", "confirmacion_uso": {}, "row_version": 1}),
    "desactivar": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/desactivar", {"modo": "RAMA", "row_version": 1}),
    "icono": lambda cli, p, n: fh.cmd(cli, f"{B}/{n}/icono", {"icon_key": "hogar.casa", "row_version": 1}),
    "reordenar": lambda cli, p, n: fh.cmd(cli, f"{B}/reordenar", {"parent_id": None, "hermanos": [
        {"id": str(n), "row_version": 1}, {"id": str(p), "row_version": 1}]}),
}


@pytest.mark.parametrize("comando", sorted(_COMANDOS) + ["reactivar"])
def test_todo_escritor_espera_el_advisory(ctx, comando):
    owner, _, cli = ctx
    padre, nodo = _preparar(owner, cli)
    if comando == "reactivar":
        assert fh.cmd(cli, f"{B}/{nodo}/desactivar", {"modo": "RAMA", "row_version": 1}).status_code == 200
        fn = lambda: fh.cmd(cli, f"{B}/{nodo}/reactivar", {"row_version": 2})  # noqa: E731
    else:
        fn = lambda: _COMANDOS[comando](cli, padre, nodo)  # noqa: E731
    salida = _barrera(owner, [(comando, fn)])
    assert salida[comando].status_code == 200, salida[comando].text


def _bloqueados_por_advisory(pid_x: int, limite_s: float = 8.0) -> list[int]:
    """PIDs de esta base bloqueados por `pid_x` y esperando un lock advisory."""
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            pids = [f[0] for f in mon.execute(
                "SELECT a.pid FROM pg_stat_activity a WHERE a.datname = current_database() "
                "AND %s = ANY(pg_blocking_pids(a.pid)) AND EXISTS (SELECT 1 FROM pg_locks l "
                "WHERE l.pid = a.pid AND l.locktype = 'advisory' AND NOT l.granted)",
                (pid_x,),
            ).fetchall()]
            if pids:
                return pids
            time.sleep(0.05)
    return []


def test_icono_bloqueado_por_el_advisory_observado_con_pg_blocking_pids(ctx):
    owner, _, cli = ctx
    _, nodo = _preparar(owner, cli)
    salida: dict = {}
    x = fh.retener_advisory(owner)
    try:
        pid_x = fh.pid_servidor(x)
        t = _lanzar(salida, "icono", lambda: fh.cmd(cli, f"{B}/{nodo}/icono",
                                                    {"icon_key": "hogar.casa", "row_version": 1}))
        assert len(_bloqueados_por_advisory(pid_x)) == 1, "el comando de icono no espera el advisory"
        assert not salida and fh.rv(owner, nodo) == 1
        x.execute("COMMIT")
    finally:
        x.close()
    t.join(timeout=20)
    assert not t.is_alive()
    assert salida["icono"].status_code == 200, salida["icono"].text
    assert fh.rv(owner, nodo) == 2


@pytest.mark.parametrize("cambio_de_a", ["NINGUNO", "NUEVO_HERMANO", "HERMANO_MODIFICADO"])
def test_reordenar_bloqueado_por_el_advisory_y_serializado(ctx, cambio_de_a):
    owner, _, cli = ctx
    padre, nodo = _preparar(owner, cli)
    cuerpo = {"parent_id": None, "hermanos": [{"id": str(nodo), "row_version": 1}, {"id": str(padre), "row_version": 1}]}
    salida: dict = {}
    x = fh.retener_advisory(owner)
    try:
        pid_x = fh.pid_servidor(x)
        t = _lanzar(salida, "reordenar", lambda: fh.cmd(cli, f"{B}/reordenar", cuerpo))
        assert len(_bloqueados_por_advisory(pid_x)) == 1, "reordenar no espera el advisory"
        assert not salida
        if cambio_de_a == "NUEVO_HERMANO":
            x.execute("INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
                      "presupuestable_default) VALUES (%s, %s, NULL, 'Tercera', 'GASTO', true)", (uuid.uuid4(), owner))
        elif cambio_de_a == "HERMANO_MODIFICADO":
            x.execute("UPDATE gapto.categorias_financieras SET nombre = 'Nodo B', row_version = row_version + 1 "
                      "WHERE id = %s", (nodo,))
        x.execute("COMMIT")
    finally:
        x.close()
    t.join(timeout=20)
    assert not t.is_alive()
    r = salida["reordenar"]
    orden = dict(h.leer(owner, "SELECT id, orden FROM gapto.categorias_financieras WHERE id = ANY(%s)",
                        ([padre, nodo],)))
    reordenadas = h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE motivo = 'F05-01 REORDENAR' "
                                "AND registro_id = ANY(%s)", ([padre, nodo],))[0][0]
    if cambio_de_a == "NINGUNO":
        assert r.status_code == 200, r.text
        assert orden == {nodo: 0, padre: 1} and reordenadas == 1
    else:
        esperado = "CONJUNTO_HERMANOS_DESFASADO" if cambio_de_a == "NUEVO_HERMANO" else "VERSION_DESFASADA"
        assert r.status_code == 409 and r.json()["codigo"] == esperado, r.text
        assert orden == {nodo: 0, padre: 0} and reordenadas == 0


def test_reordenar_bloquea_las_filas_frente_a_un_escritor_sin_advisory(ctx):
    owner, _, cli = ctx
    padre, nodo = _preparar(owner, cli)
    cuerpo = {"parent_id": None, "hermanos": [{"id": str(nodo), "row_version": 1}, {"id": str(padre), "row_version": 1}]}
    salida: dict = {}
    s = fh.sesion_owner(owner)  # escritor sin advisory, con la fila de `padre` modificada y sin confirmar
    try:
        s.execute("UPDATE gapto.categorias_financieras SET nombre = 'Padre B', row_version = row_version + 1 "
                  "WHERE id = %s", (padre,))
        pid_s = fh.pid_servidor(s)
        t = _lanzar(salida, "reordenar", lambda: fh.cmd(cli, f"{B}/reordenar", cuerpo))
        assert fh.esperar_bloqueo((pid_s,)), "reordenar no espero la fila del hermano"
        assert not salida
        s.execute("COMMIT")
    finally:
        s.close()
    t.join(timeout=20)
    assert not t.is_alive()
    r = salida["reordenar"]
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA", r.text
    assert dict(h.leer(owner, "SELECT id, orden FROM gapto.categorias_financieras WHERE id = ANY(%s)",
                       ([padre, nodo],))) == {padre: 0, nodo: 0}


# ------------------------------------------------------------ unicidad normalizada
def _op(cli, owner, tipo: str, nombre: str):
    """Prepara el estado previo y devuelve el callable concurrente."""
    if tipo == "alta":
        return lambda: fh.alta(cli, nombre)[1]
    if tipo == "renombrar":
        cid, _ = fh.alta(cli, f"Previo {uuid.uuid4().hex[:6]}")
        return lambda: fh.cmd(cli, f"{B}/{cid}/renombrar", {"nombre": nombre, "row_version": 1})
    cid = fh.crear_categoria(owner, nombre, "GASTO", enabled=False)
    return lambda: fh.cmd(cli, f"{B}/{cid}/reactivar", {"row_version": 1})


_PARES = [("alta", "alta"), ("alta", "renombrar"), ("alta", "reactivar"),
          ("renombrar", "renombrar"), ("renombrar", "reactivar"), ("reactivar", "reactivar")]


@pytest.mark.parametrize("primero,segundo", _PARES)
def test_unicidad_normalizada_concurrente(ctx, primero, segundo):
    owner, _, cli = ctx
    a = _op(cli, owner, primero, "Café")
    b = _op(cli, owner, segundo, "cafe")
    salida = _barrera(owner, [("a", a), ("b", b)])
    codigos = sorted(r.status_code for r in salida.values())
    assert codigos == [200, 409], {k: r.text for k, r in salida.items()}
    perdedor = next(r for r in salida.values() if r.status_code == 409)
    assert perdedor.json()["codigo"] == "CATEGORIA_NOMBRE_DUPLICADO"
    activos = h.leer(owner, "SELECT nombre FROM gapto.categorias_financieras WHERE enabled AND parent_id IS NULL "
                            "AND lower(nombre) IN ('café', 'cafe')")
    assert len(activos) == 1


# ------------------------------------------------------------ RAMA frente a alta
@pytest.mark.parametrize("orden", ["RAMA_PRIMERO", "ALTA_PRIMERO"])
def test_desactivar_rama_frente_a_alta_bajo_descendiente(ctx, orden):
    owner, _, cli = ctx
    raiz, _ = fh.alta(cli, "Raiz")
    hija, _ = fh.alta(cli, "Hija", parent_id=raiz)
    nueva = uuid.uuid4()
    rama = ("rama", lambda: fh.cmd(cli, f"{B}/{raiz}/desactivar", {"modo": "RAMA", "row_version": 1}))
    alta = ("alta", lambda: fh.alta(cli, "Nieta", parent_id=hija, cid=nueva)[1])
    salida = _barrera(owner, [rama, alta] if orden == "RAMA_PRIMERO" else [alta, rama])
    assert salida["rama"].status_code == 200
    if orden == "RAMA_PRIMERO":
        assert salida["alta"].status_code == 409
        assert salida["alta"].json()["codigo"] == "CATEGORIA_PADRE_DESHABILITADO"
    else:
        assert salida["alta"].status_code == 200
        assert str(nueva) in salida["rama"].json()["modificadas"]
    # Invariante: ningun nodo activo bajo la raiz desactivada.
    activos = h.leer(owner, "WITH RECURSIVE d(id) AS (SELECT id FROM gapto.categorias_financieras WHERE parent_id=%s "
                            "UNION ALL SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id=d.id) "
                            "SELECT count(*) FROM d JOIN gapto.categorias_financieras c USING (id) WHERE c.enabled", (raiz,))
    assert activos == [(0,)]
