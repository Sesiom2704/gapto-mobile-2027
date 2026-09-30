# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_161_f05_01_reordenar_hermanos.py
# Ruta: tests/api/test_161_f05_01_reordenar_hermanos.py
# Descripcion: Bateria de S6-ORDEN (F05-D012 §26.3; diseno D-ORD-01..10 del
#   mandato S6-ORDEN v0.1): comando atomico POST /v1/categorias/reordenar
#   con el conjunto COMPLETO de hijos directos de un padre (raiz si null).
#     - reordenacion con habilitados y deshabilitados: orden = posicion
#       0..n-1, solo las filas que cambian suben row_version y se auditan
#       (ACTUALIZAR "F05-01 REORDENAR", snapshots, mismo request_id); la
#       lectura del arbol refleja el nuevo orden;
#     - mismo orden: idempotente, sin escritura ni auditoria (E1);
#     - conjunto incompleto, id de otro padre, inexistente o de otro tenant:
#       CONJUNTO_HERMANOS_DESFASADO sin distinguir la causa y sin escritura;
#     - row_version desfasado en un hermano: VERSION_DESFASADA sin escritura
#       en NINGUNO (atomicidad); respuesta perdida (Q5): VERSION_DESFASADA;
#     - raiz y padre deshabilitado admitidos; padre inexistente o ajeno:
#       AGREGADO_NO_ENCONTRADO;
#     - 422 estructural: lista vacia, ids repetidos, campo extra,
#       row_version < 1, parent_id ausente.
#   La espera del advisory esta en test_156; la prohibicion de reordenar con
#   N llamadas por nodo, en test_154 (I11).
#   Base local desechable 0001..0340 (estos tests confirman filas). Datos
#   sinteticos, creados como gapto_owner con la GUC del tenant (WM 12C.7).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import json
import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

B = fh.BASE
RUTA = f"{B}/reordenar"
DESFASADO = "CONJUNTO_HERMANOS_DESFASADO"


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _codigo(r) -> str:
    return r.json().get("codigo")


def _cuerpo(parent, hermanos: list[tuple[uuid.UUID, int]]) -> dict:
    return {"parent_id": None if parent is None else str(parent),
            "hermanos": [{"id": str(i), "row_version": rv} for i, rv in hermanos]}


def _estado(owner, ids) -> dict:
    return {i: (o, rv) for i, o, rv in h.leer(
        owner, "SELECT id, orden, row_version FROM gapto.categorias_financieras WHERE id = ANY(%s)", (list(ids),))}


def _reordenadas(owner, ids) -> list[tuple]:
    return h.leer(owner, "SELECT registro_id, accion, request_id, datos_antes, datos_despues FROM gapto.auditoria "
                         "WHERE motivo = 'F05-01 REORDENAR' AND registro_id = ANY(%s)", (list(ids),))


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


def _cuatro(owner, parent=None):
    """A(0), B(1), C(2, deshabilitada), D(3) bajo `parent`."""
    return [fh.crear_categoria(owner, n, "GASTO", parent_id=parent, orden=o, enabled=(n != "C"))
            for o, n in enumerate("ABCD")]


# ------------------------------------------------------------------ exito
def test_reordenacion_completa_escribe_solo_lo_que_cambia(ctx):
    owner, _, cli = ctx
    padre = fh.crear_categoria(owner, "Padre", "GASTO")
    a, b, c, d = _cuatro(owner, padre)
    # Nuevo orden: A, C, B, D -> A y D no cambian; C (2->1) y B (1->2) si.
    r = fh.cmd(cli, RUTA, _cuerpo(padre, [(a, 1), (c, 1), (b, 1), (d, 1)]))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["idempotente"] is False and sorted(cuerpo["modificadas"]) == sorted([str(c), str(b)])
    assert [n["id"] for n in cuerpo["hermanos"]] == [str(a), str(c), str(b), str(d)]
    assert [n["orden"] for n in cuerpo["hermanos"]] == [0, 1, 2, 3]
    assert _estado(owner, [a, b, c, d]) == {a: (0, 1), c: (1, 2), b: (2, 2), d: (3, 1)}
    audit = _reordenadas(owner, [a, b, c, d])
    assert sorted(x[0] for x in audit) == sorted([b, c]) and {x[1] for x in audit} == {"ACTUALIZAR"}
    assert len({x[2] for x in audit}) == 1, "una transaccion: mismo request_id"
    for reg, _, _, antes, despues in audit:
        esperado = {b: (1, 2), c: (2, 1)}[reg]
        assert (_json(antes)["orden"], _json(despues)["orden"]) == esperado
        assert (_json(antes)["row_version"], _json(despues)["row_version"]) == (1, 2)
    # La lectura del arbol refleja el orden (orden -> nombre -> id).
    arbol = cli.get(B, headers=h.AUTH).json()["categorias"]
    hijos = [n["id"] for n in arbol if n["parent_id"] == str(padre)]
    assert hijos == [str(a), str(c), str(b), str(d)]


def test_mismo_orden_es_idempotente_sin_escritura(ctx):
    owner, _, cli = ctx
    a, b, c, d = _cuatro(owner)
    antes = _estado(owner, [a, b, c, d])
    r = fh.cmd(cli, RUTA, _cuerpo(None, [(a, 1), (b, 1), (c, 1), (d, 1)]))
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is True and r.json()["modificadas"] == []
    assert _estado(owner, [a, b, c, d]) == antes and _reordenadas(owner, [a, b, c, d]) == []


def test_alta_deja_orden_cero_y_la_reordenacion_asigna_posiciones(ctx):
    owner, _, cli = ctx
    x, _ = fh.alta(cli, "X")
    y, _ = fh.alta(cli, "Y")
    assert _estado(owner, [x, y]) == {x: (0, 1), y: (0, 1)}
    r = fh.cmd(cli, RUTA, _cuerpo(None, [(y, 1), (x, 1)]))
    assert r.status_code == 200 and r.json()["modificadas"] == [str(x)], r.text
    assert _estado(owner, [x, y]) == {y: (0, 1), x: (1, 2)}


def test_bajo_padre_deshabilitado_se_admite(ctx):
    owner, _, cli = ctx
    padre = fh.crear_categoria(owner, "Vieja", "GASTO", enabled=False)
    a = fh.crear_categoria(owner, "A", "GASTO", parent_id=padre, enabled=False)
    b = fh.crear_categoria(owner, "B", "GASTO", parent_id=padre, enabled=False, orden=1)
    r = fh.cmd(cli, RUTA, _cuerpo(padre, [(b, 1), (a, 1)]))
    assert r.status_code == 200, r.text
    assert _estado(owner, [a, b]) == {b: (0, 2), a: (1, 2)}
    assert h.leer(owner, "SELECT enabled, row_version FROM gapto.categorias_financieras WHERE id=%s",
                  (padre,)) == [(False, 1)]


# ------------------------------------------------------------------ conjunto desfasado
@pytest.mark.parametrize("caso", ["FALTA_UNO", "OTRO_PADRE", "INEXISTENTE", "OTRO_TENANT", "OTRO_PADRE_SUSTITUYE"])
def test_conjunto_distinto_del_persistido_se_rechaza_sin_escritura(ctx, caso):
    owner, _, cli = ctx
    padre = fh.crear_categoria(owner, "Padre", "GASTO")
    a, b, c, d = _cuatro(owner, padre)
    lista = [(d, 1), (c, 1), (b, 1), (a, 1)]
    if caso == "FALTA_UNO":
        lista = lista[:3]
    elif caso == "OTRO_PADRE":
        lista.append((fh.crear_categoria(owner, "Suelta", "GASTO"), 1))
    elif caso == "INEXISTENTE":
        lista.append((uuid.uuid4(), 1))
    elif caso == "OTRO_TENANT":
        otro, _ = h.crear_tenant()
        lista.append((fh.crear_categoria(otro, "Ajena", "GASTO"), 1))
    else:  # mismo tamano: uno propio sustituido por uno de otro padre
        lista[0] = (fh.crear_categoria(owner, "Suelta", "GASTO"), 1)
    antes = _estado(owner, [a, b, c, d])
    r = fh.cmd(cli, RUTA, _cuerpo(padre, lista))
    assert r.status_code == 409 and _codigo(r) == DESFASADO, r.text
    assert r.json()["reintentable"] is False
    assert _estado(owner, [a, b, c, d]) == antes and _reordenadas(owner, [a, b, c, d]) == []


# ------------------------------------------------------------------ row_version y atomicidad
@pytest.mark.parametrize("desfasado", [0, 3])
def test_row_version_desfasado_en_un_hermano_no_escribe_en_ninguno(ctx, desfasado):
    owner, _, cli = ctx
    a, b, c, d = _cuatro(owner)
    # Evoluciona uno de los hermanos por otro camino (renombrar): row_version 2.
    objetivo = [d, c, b, a][desfasado]
    assert fh.cmd(cli, f"{B}/{objetivo}/renombrar", {"nombre": "Otro", "row_version": 1}).status_code == 200
    antes = _estado(owner, [a, b, c, d])
    r = fh.cmd(cli, RUTA, _cuerpo(None, [(d, 1), (c, 1), (b, 1), (a, 1)]))
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA", r.text
    assert _estado(owner, [a, b, c, d]) == antes and _reordenadas(owner, [a, b, c, d]) == []


def test_respuesta_perdida_reintento_tras_commit_es_version_desfasada(ctx):
    owner, _, cli = ctx
    a, b, c, d = _cuatro(owner)
    cuerpo = _cuerpo(None, [(d, 1), (c, 1), (b, 1), (a, 1)])
    assert fh.cmd(cli, RUTA, cuerpo).status_code == 200
    despues = _estado(owner, [a, b, c, d])
    r = fh.cmd(cli, RUTA, cuerpo)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA", r.text
    assert _estado(owner, [a, b, c, d]) == despues and len(_reordenadas(owner, [a, b, c, d])) == 4


# ------------------------------------------------------------------ padre
@pytest.mark.parametrize("origen", ["INEXISTENTE", "AJENO"])
def test_padre_inexistente_o_ajeno(ctx, origen):
    owner, _, cli = ctx
    a = fh.crear_categoria(owner, "A", "GASTO")
    if origen == "AJENO":
        otro, _ = h.crear_tenant()
        padre = fh.crear_categoria(otro, "Ajeno", "GASTO")
    else:
        padre = uuid.uuid4()
    r = fh.cmd(cli, RUTA, _cuerpo(padre, [(a, 1)]))
    assert r.status_code == 404 and _codigo(r) == "AGREGADO_NO_ENCONTRADO", r.text
    assert _estado(owner, [a]) == {a: (0, 1)}


# ------------------------------------------------------------------ 422 estructural
@pytest.mark.parametrize("variante", ["VACIA", "REPETIDOS", "CAMPO_EXTRA", "CAMPO_EXTRA_HERMANO",
                                      "ROW_VERSION_CERO", "SIN_PARENT"])
def test_cuerpo_estructuralmente_invalido_422(ctx, variante):
    owner, _, cli = ctx
    a, b, c, d = _cuatro(owner)
    cuerpo = _cuerpo(None, [(d, 1), (c, 1), (b, 1), (a, 1)])
    if variante == "VACIA":
        cuerpo["hermanos"] = []
    elif variante == "REPETIDOS":
        cuerpo["hermanos"].append({"id": str(a), "row_version": 1})
    elif variante == "CAMPO_EXTRA":
        cuerpo["orden"] = 3
    elif variante == "CAMPO_EXTRA_HERMANO":
        cuerpo["hermanos"][0]["orden"] = 3
    elif variante == "ROW_VERSION_CERO":
        cuerpo["hermanos"][0]["row_version"] = 0
    else:
        del cuerpo["parent_id"]
    antes = _estado(owner, [a, b, c, d])
    r = fh.cmd(cli, RUTA, cuerpo)
    assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA", r.text
    assert _estado(owner, [a, b, c, d]) == antes and _reordenadas(owner, [a, b, c, d]) == []
