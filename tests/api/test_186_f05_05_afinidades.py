# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_186_f05_05_afinidades.py
# Ruta: tests/api/test_186_f05_05_afinidades.py
# Descripcion: Writer y lectura de afinidades (K2 §1.3; F05 §49.4 A5/A8,
#   §49.5 R8/R9, AJ-F0505-02). Dominio AFINIDADES. Casos de §49.9:
#   10 (doble envio -> una sola afinidad; el hecho no depende de la afinidad),
#   31 (23505 idempotente SOLO para el mismo par; categoria de otro owner ->
#   42501 visible como REFERENCIA_NO_DISPONIBLE; row_version del tercero sube
#   sin tocar nombre ni naturaleza), 4 («No disponible» en Ajustes) y 18.
#   Ademas: UUID reutilizado con otro par, tercero/categoria no elegibles,
#   auditoria CREAR/ELIMINAR, rechazo sin efectos (el savepoint deshace el
#   row_version), baja idempotente y prioridad_manual NULL.
#   El orden de locks y la concurrencia: test_191 (serie, con pg_locks).
# Version: 0.1.0 (F05-05 K2 §1.3)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_05_helpers as x
import vs01_api_helpers as h

URL = "/v1/afinidades"


def alta(cli, tercero, categoria, aid=None):
    return cli.post(URL, json={"id": str(aid or uuid.uuid4()), "tercero_id": str(tercero), "categoria_id": str(categoria)},
                    headers=h.AUTH)


def fila_tercero(owner, tid):
    return h.leer(owner, "SELECT nombre, naturaleza, enabled, row_version FROM gapto.terceros WHERE id=%s", (tid,))[0]


def afinidades(owner, tid):
    return h.leer(owner, "SELECT id, categoria_id, prioridad_manual FROM gapto.tercero_afinidades WHERE tercero_id=%s",
                  (tid,))


def auditorias(owner, aid):
    return h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE tabla='tercero_afinidades' "
                         "AND registro_id=%s ORDER BY created_at", (aid,))


@pytest.fixture()
def e():
    owner, actor, cli, corriente, ahorro = x.entorno()
    aldi = x.tercero(cli, "ALDI", "EMPRESA")
    super_ = x.categoria(owner, "Supermercados")
    return owner, cli, corriente, aldi, super_


def test_alta_auditada_con_prioridad_null_y_row_version_sin_campos_de_negocio(e):
    owner, cli, _, aldi, super_ = e
    antes = fila_tercero(owner, aldi)
    aid = uuid.uuid4()
    r = alta(cli, aldi, super_, aid)
    assert r.status_code == 200, r.text
    assert r.json() == {"afinidad": {"id": str(aid), "tercero_id": str(aldi), "categoria_id": str(super_)},
                        "idempotente": False, "aviso": None}
    assert afinidades(owner, aldi) == [(aid, super_, None)]
    despues = fila_tercero(owner, aldi)
    assert despues[:3] == antes[:3] and despues[3] == antes[3] + 1  # caso 31: solo row_version
    assert auditorias(owner, aid) == [("CREAR", "F05-05 AFINIDAD ALTA")]


def test_caso10_doble_envio_mismo_uuid_una_sola_afinidad(e):
    owner, cli, _, aldi, super_ = e
    aid = uuid.uuid4()
    assert alta(cli, aldi, super_, aid).status_code == 200
    rv = fila_tercero(owner, aldi)[3]
    r = alta(cli, aldi, super_, aid)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["aviso"] is None
    assert len(afinidades(owner, aldi)) == 1 and fila_tercero(owner, aldi)[3] == rv  # sin escritura


def test_caso31_23505_idempotente_solo_para_el_mismo_par(e):
    owner, cli, _, aldi, super_ = e
    primera = uuid.uuid4()
    assert alta(cli, aldi, super_, primera).status_code == 200
    rv = fila_tercero(owner, aldi)[3]
    r = alta(cli, aldi, super_)  # otro UUID, mismo par -> UNIQUE (tercero, categoria)
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is True and r.json()["aviso"] == "AFINIDAD_YA_EXISTE"
    assert r.json()["afinidad"]["id"] == str(primera)
    assert len(afinidades(owner, aldi)) == 1 and fila_tercero(owner, aldi)[3] == rv  # savepoint deshecho


def test_uuid_reutilizado_con_otro_par(e):
    owner, cli, _, aldi, super_ = e
    aid = uuid.uuid4()
    assert alta(cli, aldi, super_, aid).status_code == 200
    r = alta(cli, aldi, x.categoria(owner, "Hogar"), aid)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


def test_caso31_categoria_de_otro_owner_42501_visible_y_sin_efectos(e):
    owner, cli, _, aldi, _ = e
    owner_b, _, _, _, _ = x.entorno()
    cat_b = x.categoria(owner_b, "De B")
    rv = fila_tercero(owner, aldi)[3]
    r = alta(cli, aldi, cat_b)
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == "REFERENCIA_NO_DISPONIBLE" and r.json()["detalle"] == {"sqlstate": "42501"}
    assert afinidades(owner, aldi) == [] and fila_tercero(owner, aldi)[3] == rv


def test_categoria_inexistente_misma_respuesta_que_ajena(e):
    owner, cli, _, aldi, _ = e
    r = alta(cli, aldi, uuid.uuid4())
    assert r.status_code == 409 and r.json()["codigo"] == "REFERENCIA_NO_DISPONIBLE"


def test_caso18_tercero_ajeno_o_deshabilitado(e):
    owner, cli, _, aldi, super_ = e
    owner_b, _, cli_b, _, _ = x.entorno()
    ter_b = x.tercero(cli_b, "Ajeno")
    r = alta(cli, ter_b, super_)
    assert r.status_code == 409 and r.json()["codigo"] == "TERCERO_NO_ELEGIBLE"
    assert h.leer(owner_b, "SELECT count(*) FROM gapto.tercero_afinidades")[0][0] == 0
    x.desactivar_tercero(cli, aldi)
    r = alta(cli, aldi, super_)
    assert r.status_code == 409 and r.json()["codigo"] == "TERCERO_NO_ELEGIBLE"


def test_categoria_deshabilitada_rechazada_sin_efectos(e):
    owner, cli, _, aldi, super_ = e
    x.desactivar_categoria(owner, super_)
    rv = fila_tercero(owner, aldi)[3]
    r = alta(cli, aldi, super_)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    assert afinidades(owner, aldi) == [] and fila_tercero(owner, aldi)[3] == rv


def test_entrada_con_campos_colados_422(e):
    _, cli, _, aldi, super_ = e
    r = cli.post(URL, json={"id": str(uuid.uuid4()), "tercero_id": str(aldi), "categoria_id": str(super_),
                            "owner_user_id": str(uuid.uuid4())}, headers=h.AUTH)
    assert r.status_code == 422


def test_baja_auditada_e_idempotente(e):
    owner, cli, _, aldi, super_ = e
    aid = uuid.uuid4()
    assert alta(cli, aldi, super_, aid).status_code == 200
    rv = fila_tercero(owner, aldi)[3]
    r = cli.post(f"{URL}/{aid}/retirar", headers=h.AUTH)
    assert r.status_code == 200 and r.json()["idempotente"] is False
    assert afinidades(owner, aldi) == [] and fila_tercero(owner, aldi)[3] == rv + 1
    assert auditorias(owner, aid) == [("CREAR", "F05-05 AFINIDAD ALTA"), ("ELIMINAR", "F05-05 AFINIDAD BAJA")]
    r = cli.post(f"{URL}/{aid}/retirar", headers=h.AUTH)
    assert r.status_code == 200 and r.json() == {"afinidad": None, "idempotente": True, "aviso": None}
    assert fila_tercero(owner, aldi)[3] == rv + 1


def test_baja_de_afinidad_ajena_sin_efectos(e):
    owner, cli, _, aldi, super_ = e
    aid = uuid.uuid4()
    assert alta(cli, aldi, super_, aid).status_code == 200
    _, _, cli_b, _, _ = x.entorno()
    r = cli_b.post(f"{URL}/{aid}/retirar", headers=h.AUTH)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert len(afinidades(owner, aldi)) == 1


def test_baja_permitida_con_tercero_desactivado(e):
    owner, cli, _, aldi, super_ = e
    aid = uuid.uuid4()
    assert alta(cli, aldi, super_, aid).status_code == 200
    x.desactivar_tercero(cli, aldi)
    assert cli.post(f"{URL}/{aid}/retirar", headers=h.AUTH).status_code == 200
    assert afinidades(owner, aldi) == []


def test_caso10_el_hecho_no_depende_de_la_afinidad(e):
    """«Recordar» es una escritura independiente: un fallo de la afinidad no
    toca el hecho ya registrado (otra transaccion)."""
    owner, cli, cta, aldi, super_ = e
    hid = x.gasto(cli, cta, categoria_id=super_, tercero_id=aldi)
    r = alta(cli, aldi, uuid.uuid4())  # falla
    assert r.status_code == 409
    assert h.leer(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id=%s", (hid,)) == [("ACTIVO",)]


def test_detalle_guardadas_disponible_y_segun_historial(e):
    owner, cli, cta, aldi, super_ = e
    limpieza, drogueria = x.categoria(owner, "Limpieza"), x.categoria(owner, "Droguería")
    for _ in range(3):
        x.gasto(cli, cta, categoria_id=super_, tercero_id=aldi)
    for _ in range(2):
        x.gasto(cli, cta, categoria_id=drogueria, tercero_id=aldi)
    x.gasto(cli, cta, tercero_id=aldi)  # sin categoria: cuenta en M, no en N
    assert alta(cli, aldi, super_).status_code == 200
    assert alta(cli, aldi, limpieza).status_code == 200
    x.desactivar_categoria(owner, limpieza)
    r = cli.get(f"/v1/terceros/{aldi}/afinidades", params={"fecha": "2026-10-10"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(g["nombre"], g["disponible"]) for g in d["guardadas"]] == [("Limpieza", False), ("Supermercados", True)]
    assert [(s["nombre"], s["usos"]) for s in d["segun_historial"]] == [("Droguería", 2)]  # sin las guardadas
    assert d["total_registros"] == 6 and d["tipo"] == "GASTO"


def test_detalle_de_tercero_ajeno_404(e):
    _, cli, _, _, _ = e
    _, _, cli_b, _, _ = x.entorno()
    ter_b = x.tercero(cli_b, "Ajeno")
    r = cli.get(f"/v1/terceros/{ter_b}/afinidades", params={"fecha": "2026-10-10"}, headers=h.AUTH)
    assert r.status_code == 404 and r.json()["codigo"] == "TERCERO_NO_ENCONTRADO"
