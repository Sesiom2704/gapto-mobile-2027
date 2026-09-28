# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_156_f05_01_concurrencia_catalogo.py
# Ruta: tests/api/test_156_f05_01_concurrencia_catalogo.py
# Descripcion: Concurrencia del catalogo de categorias (F05-01, S5; §22.5;
#   AJ-S4-01/02). Interleaving forzado con barrera explicita (WM 12C.1): una
#   sesion retiene el advisory (CATEGORIAS, owner); los comandos quedan
#   ESPERANDO (se observa en pg_stat_activity) y al liberarla se serializan
#   en orden de llegada.
#     - cada uno de los 7 comandos toma el advisory ANTES de escribir;
#     - unicidad normalizada en las seis combinaciones alta / renombrado /
#       reactivacion, con literales distintos ("Café" / "cafe") para que la
#       UNIQUE fisica literal no pueda salvar el caso: solo el advisory +
#       normalizacion lo impiden;
#     - desactivar RAMA frente a alta bajo un descendiente, en ambos ordenes:
#       nunca queda un nodo activo bajo un ancestro recien desactivado.
#   Base local desechable 0001..0340 (estos tests confirman filas).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import threading
import uuid

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
