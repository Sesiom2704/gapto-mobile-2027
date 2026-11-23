# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_321_f06_t6_s5_ambos.py
# Ruta: tests/api/test_321_f06_t6_s5_ambos.py
# Descripcion: F06 T6 · S5 (N1): «Ambos» al recordar (dictamen 1 Q2/A3; DF-10/13; F09 0.55 §12.107.3;
#   contrato en la evidencia T6 Q2_s5/S5_CONTRATO.md). `POST /v1/preferencias/ambos`: dos preferencias
#   independientes (tercero y categoria) en UNA transaccion; preflight de todas las operaciones antes de
#   escribir; rechazo con ambitos y campos en conflicto; todas o ninguna (fallo inyectado en la segunda
#   escritura); sin precedencia implicita nueva; editar, desactivar y reactivar con contradiccion; replay.
#   Discriminantes de M-S5-01..03. La concurrencia va aparte (test_322).
#   Exige GAPTO_TEST_DATABASE_URL (base local DESECHABLE con la cadena aplicada).
# Version: 0.1.0 (F06 T6 · S5)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h

from app.preferencias import servicio as srv

RUTA = "/v1/preferencias/ambos"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, actor, cli, ph.tercero(owner), ph.categoria(owner, "Super"), ph.tipo_gasto(owner)


def _op(ambito: str, tipo, clave, *, presupuestable=True, cuenta=None, accion="ALTA", pid=None, row_version=None) -> dict:
    contenido = {"tipo_hecho_id": str(tipo), "presupuestable_default": presupuestable}
    if cuenta is not None:
        contenido["cuenta_default_id"] = str(cuenta)
    contenido["tercero_id" if ambito == "TERCERO" else "categoria_id"] = str(clave)
    op = {"ambito": ambito, "accion": accion, "id": str(pid or uuid.uuid4()), "contenido": contenido}
    if row_version is not None:
        op["row_version"] = row_version
    return op


def _post(cli, *ops):
    return cli.post(RUTA, json={"operaciones": list(ops)}, headers=h.AUTH)


def _filas(owner):
    return h.leer(owner, "SELECT tercero_id, categoria_id, presupuestable_default, prioridad, enabled "
                         "FROM gapto.preferencias_registro ORDER BY tercero_id NULLS LAST")


def test_ambos_nuevos_dos_preferencias_independientes_sin_precedencia_nueva(t):
    owner, _, cli, ter, cat, tipo = t
    r = _post(cli, _op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat))
    assert r.status_code == 200, r.text
    assert [x["ambito"] for x in r.json()["resultados"]] == ["TERCERO", "CATEGORIA"]
    filas = _filas(owner)
    assert filas == [(ter, None, True, 100, True), (None, cat, True, 100, True)]           # M-S5-03: misma prioridad
    # El resolver de siempre: en un contexto con los dos, ambas casan y proponen lo mismo (sin contradiccion).
    p = ph.resolver(owner, cat, tercero_id=ter)
    assert ph.valor(p, "presupuestable") is True


def test_replay_y_uno_ya_existe_igual_son_idempotentes(t):
    owner, _, cli, ter, cat, tipo = t
    pid_cat = uuid.uuid4()
    r1 = cli.post(ph.BASE, json={"id": str(pid_cat), "tipo_hecho_id": str(tipo), "categoria_id": str(cat),
                                 "presupuestable_default": True}, headers=h.AUTH)
    assert r1.status_code == 200, r1.text
    ops = (_op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat, pid=pid_cat))
    r = _post(cli, *ops)
    assert r.status_code == 200, r.text
    assert [x["idempotente"] for x in r.json()["resultados"]] == [False, True]
    r2 = _post(cli, *ops)                                                                   # replay
    assert r2.status_code == 200 and [x["idempotente"] for x in r2.json()["resultados"]] == [True, True]
    assert len(_filas(owner)) == 2


def test_uno_contradice_se_rechaza_con_su_ambito_y_sus_campos_y_nada_se_guarda(t):
    owner, _, cli, ter, cat, tipo = t
    otra = ph.categoria(owner, "Ocio")
    ph.insertar_sql(owner, categoria_id=otra, presupuestable=False)                         # choca solo con la del tercero
    r = _post(cli, _op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat))
    assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO", r.text
    conflictos = r.json()["detalle"]["conflictos"]
    assert [(c["ambito"], c["campos"]) for c in conflictos] == [("TERCERO", ["presupuestable_default"])]
    assert len(_filas(owner)) == 1                                                          # nada nuevo


def test_los_dos_contradicen_se_informan_los_dos(t):
    owner, _, cli, ter, cat, tipo = t
    ph.insertar_sql(owner, categoria_id=cat, presupuestable=False)                          # choca con las dos
    r = _post(cli, _op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat))
    assert r.status_code == 409
    assert sorted(c["ambito"] for c in r.json()["detalle"]["conflictos"]) == ["CATEGORIA", "TERCERO"]   # M-S5-02
    assert len(_filas(owner)) == 1


def test_contradiccion_entre_las_dos_operaciones(t):
    owner, _, cli, ter, cat, tipo = t
    r = _post(cli, _op("TERCERO", tipo, ter, presupuestable=True), _op("CATEGORIA", tipo, cat, presupuestable=False))
    assert r.status_code == 409
    assert sorted(c["ambito"] for c in r.json()["detalle"]["conflictos"]) == ["CATEGORIA", "TERCERO"]
    assert _filas(owner) == []


def test_fallo_de_la_segunda_escritura_no_deja_ninguna(t, monkeypatch):
    owner, _, cli, ter, cat, tipo = t
    original = srv.alta
    llamadas = {"n": 0}

    def alta_que_falla_la_segunda(*a, **kw):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            return srv.Rechazo(srv.EMPATE_CONTRADICTORIO, {"preferencia_conflicto_id": uuid.uuid4()})
        return original(*a, **kw)

    monkeypatch.setattr(srv, "alta", alta_que_falla_la_segunda)
    r = _post(cli, _op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat))
    assert llamadas["n"] == 2
    assert r.status_code == 409 and r.json()["detalle"]["conflictos"][0]["ambito"] == "CATEGORIA", r.text
    assert _filas(owner) == []                                                              # M-S5-01: ninguna
    assert h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla='preferencias_registro'") == [(0,)]


def test_editar_desactivar_y_reactivar_con_contradiccion(t):
    owner, _, cli, ter, cat, tipo = t
    r = _post(cli, _op("TERCERO", tipo, ter), _op("CATEGORIA", tipo, cat))
    assert r.status_code == 200
    p_ter, p_cat = (x["preferencia"] for x in r.json()["resultados"])
    cuerpo_ter = {"tipo_hecho_id": str(tipo), "tercero_id": str(ter), "presupuestable_default": False}
    r = ph.editar(cli, uuid.UUID(p_ter["id"]), p_ter["row_version"], **{k: v for k, v in cuerpo_ter.items()})
    assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO"
    r = ph.desactivar(cli, uuid.UUID(p_cat["id"]), p_cat["row_version"])
    assert r.status_code == 200, r.text                                                     # desactivar nunca contradice
    r = ph.editar(cli, uuid.UUID(p_ter["id"]), p_ter["row_version"], **cuerpo_ter)
    assert r.status_code == 200, r.text
    fila_cat = ph.fila(owner, uuid.UUID(p_cat["id"]))
    r = ph.reactivar(cli, uuid.UUID(p_cat["id"]), fila_cat["row_version"])
    assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO"


def test_entrada_invalida(t):
    _, _, cli, ter, cat, tipo = t
    assert _post(cli, _op("TERCERO", tipo, ter), _op("TERCERO", tipo, ter)).status_code == 422          # mismo ambito
    assert _post(cli).status_code == 422                                                                # ninguna
    assert _post(cli, *(_op("TERCERO", tipo, ter),) * 3).status_code == 422                            # tres
    malo = _op("TERCERO", tipo, ter)
    malo["contenido"]["categoria_id"] = str(cat)                                                        # ambito combinado
    r = _post(cli, malo)
    assert r.status_code == 422 and r.json()["detalle"]["conflictos"][0]["ambito"] == "TERCERO"
