# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_304_f06_02_03_terceros_roles_y_clasificacion.py
# Ruta: tests/api/test_304_f06_02_03_terceros_roles_y_clasificacion.py
# Descripcion: F06-02/03 · C-TER-01 roles y C-TER-03 clasificacion de terceros (contrato v1.1 Parte V; Q-CON-13:
#   AÑADIR Y EDITAR, NUNCA RETIRAR). Oraculos: O-11 (rol INQUILINO dos veces -> 1 fila; quitar -> RETIRADA_NO_ADMITIDA
#   sin escritura; desactivar una clasificacion -> enabled = false con las asignaciones intactas, O-13; cambiar la
#   clasificacion principal -> 1 UPDATE auditado, O-16, sin direcciones). AGENCIA y ADMINISTRADOR NO son roles de
#   tercero (decision 2 = A). Arbol: sin ciclos y sin nombre repetido entre hermanos activos. Sin DELETE: el rol
#   `gapto_runtime` no puede borrar en ninguna de estas tablas (0351). C-TER-02 (direcciones) NO existe en el bloque.
#   ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import psycopg
import pytest

import f06_02_03_helpers as c
import vs01_api_helpers as h


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    return owner, cli, c.tercero(cli, "Aseguradora Norte", "EMPRESA")


def _ver(owner, tid) -> int:
    return c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (tid,))


def _roles(cli, tid, owner, anadir, **extra):
    return c.post(cli, f"/v1/terceros/{tid}/roles", {"intencion_id": str(uuid.uuid4()),
                                                       "row_version_esperada": _ver(owner, tid), "anadir": anadir, **extra})


def _clasif(cli, nombre, parent=None) -> dict:
    i = uuid.uuid4()
    r = c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(i), "nombre": nombre,
                                                     **({"parent_id": str(parent)} if parent else {})})
    assert r.status_code == 200, r.text
    return r.json()["clasificacion"]


# ================================================================== C-TER-01 roles
def test_o_11_rol_dos_veces_es_una_fila_y_sube_una_sola_version(t):
    owner, cli, tid = t
    v0 = _ver(owner, tid)
    r = _roles(cli, tid, owner, ["INQUILINO", "SUMINISTRADOR"])
    assert r.status_code == 200, r.text
    assert sorted(r.json()["tercero"]["roles"]) == ["INQUILINO", "SUMINISTRADOR"] and _ver(owner, tid) == v0 + 1
    antes = c.huella()
    r = _roles(cli, tid, owner, ["INQUILINO"])                                    # ya esta: no escribe
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["ya_estaban"] == ["INQUILINO"]
    assert c.huella() == antes
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles WHERE tercero_id = %s AND rol_codigo = 'INQUILINO'", (tid,)) == 1


def test_quitar_un_rol_es_retirada_no_admitida_sin_escritura(t):
    owner, cli, tid = t
    assert _roles(cli, tid, owner, ["INQUILINO"]).status_code == 200
    antes = c.huella()
    r = _roles(cli, tid, owner, [], quitar=["INQUILINO"])
    c.rechazo_sin_cambios(cli, r, 409, "RETIRADA_NO_ADMITIDA", antes)
    r = _roles(cli, tid, owner, ["AVALISTA"], quitar=["INQUILINO"])
    c.rechazo_sin_cambios(cli, r, 409, "RETIRADA_NO_ADMITIDA", antes)               # anadir + quitar: nada se escribe
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles WHERE tercero_id = %s", (tid,)) == 1


def test_corregir_un_rol_es_anadir_el_correcto_y_el_erroneo_se_queda(t):
    owner, cli, tid = t
    assert _roles(cli, tid, owner, ["COMERCIO"]).status_code == 200
    r = _roles(cli, tid, owner, ["SUMINISTRADOR"])
    assert sorted(r.json()["tercero"]["roles"]) == ["COMERCIO", "SUMINISTRADOR"]       # Q-CON-19: el erroneo se queda


def test_roles_agencia_y_administrador_no_son_roles_de_tercero(t):
    owner, cli, tid = t
    antes = c.huella()
    for rol in ("AGENCIA", "ADMINISTRADOR", "ROL_INVENTADO"):
        c.rechazo_sin_cambios(cli, _roles(cli, tid, owner, [rol]), 422, "ROL_DESCONOCIDO", antes)
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles") == 0
    # los 10 roles de ck_tercero_roles__rol_codigo se admiten (Q-CON-12: la interfaz muestra todos)
    todos = ["COMERCIO", "ENTIDAD_FINANCIERA", "FINANCIADOR", "INQUILINO", "AVALISTA", "EMPLEADOR", "SUMINISTRADOR",
             "OBLIGADO_REEMBOLSO", "GESTOR", "ASEGURADORA"]
    assert _roles(cli, tid, owner, todos).status_code == 200


def test_roles_version_desfasada_replay_y_tercero_ajeno(t):
    owner, cli, tid = t
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": _ver(owner, tid), "anadir": ["GESTOR"]}
    assert c.post(cli, f"/v1/terceros/{tid}/roles", cuerpo).status_code == 200
    r = c.post(cli, f"/v1/terceros/{tid}/roles", cuerpo)                             # replay con la version superada
    assert r.status_code == 200 and r.json()["idempotente"] is True
    otra = {**cuerpo, "intencion_id": str(uuid.uuid4()), "anadir": ["AVALISTA"]}
    c.rechazo(c.post(cli, f"/v1/terceros/{tid}/roles", otra), 409, "VERSION_DESFASADA")
    mala = {**cuerpo, "anadir": ["AVALISTA"]}                                         # misma intencion, otro contenido
    c.rechazo(c.post(cli, f"/v1/terceros/{tid}/roles", mala), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    _, _, cli2 = c.entorno()
    r = c.post(cli2, f"/v1/terceros/{tid}/roles", {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1,
                                                     "anadir": ["GESTOR"]})
    c.rechazo(r, 404, "TERCERO_NO_ENCONTRADO")


def test_el_runtime_no_puede_borrar_roles_ni_clasificaciones(t):
    owner, cli, tid = t
    assert _roles(cli, tid, owner, ["GESTOR"]).status_code == 200
    for tabla in ("tercero_roles", "tercero_clasificaciones", "clasificaciones_tercero", "contrato_servicios",
                  "propiedad_servicios", "contratos", "contrato_participantes", "contrato_revision_renta_versiones"):
        with psycopg.connect(h.dsn()) as cn:
            cn.execute("SET ROLE gapto_runtime")
            cn.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cn.execute(f"DELETE FROM gapto.{tabla}")


# ================================================================== C-TER-03 clasificacion y arbol
def test_o_11_asignar_clasificacion_y_desactivarla_conserva_las_asignaciones(t):
    owner, cli, tid = t
    raiz = _clasif(cli, "Proveedores")
    hija = _clasif(cli, "Seguros", raiz["id"])
    r = c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                              "row_version_esperada": _ver(owner, tid), "anadir": [hija["id"]]})
    assert r.status_code == 200, r.text
    assert [(x["nombre"], x["principal"]) for x in r.json()["tercero"]["clasificaciones"]] == [("Seguros", False)]
    asignaciones = c.uno(owner, "SELECT count(*) FROM gapto.tercero_clasificaciones WHERE tercero_id = %s", (tid,))
    r = c.post(cli, f"/v1/clasificaciones-tercero/{hija['id']}/desactivar",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": hija["row_version"]})
    assert r.status_code == 200 and r.json()["clasificacion"]["enabled"] is False        # O-13: enabled = false
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_clasificaciones WHERE tercero_id = %s", (tid,)) == asignaciones
    assert c.uno(owner, "SELECT enabled FROM gapto.clasificaciones_tercero WHERE id = %s", (hija["id"],)) is False


def test_o_16_cambiar_la_clasificacion_principal_es_un_update_auditado(t):
    owner, cli, tid = t
    a, b = _clasif(cli, "A"), _clasif(cli, "B")
    r = c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                              "row_version_esperada": _ver(owner, tid),
                                                              "anadir": [a["id"], b["id"]], "principal": a["id"]})
    assert r.status_code == 200, r.text
    filas = c.uno(owner, "SELECT count(*) FROM gapto.tercero_clasificaciones WHERE tercero_id = %s", (tid,))
    auditorias = c.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'terceros' AND registro_id = %s", (tid,))
    r = c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                              "row_version_esperada": _ver(owner, tid), "principal": b["id"]})
    assert r.status_code == 200, r.text
    principales = [x["nombre"] for x in r.json()["tercero"]["clasificaciones"] if x["principal"]]
    assert principales == ["B"]                                                        # como mucho una principal
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_clasificaciones WHERE tercero_id = %s", (tid,)) == filas
    assert c.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'terceros' AND registro_id = %s", (tid,)) == auditorias + 1


def test_desasignar_es_retirada_no_admitida_y_principal_debe_estar_asignada(t):
    owner, cli, tid = t
    a, b = _clasif(cli, "A"), _clasif(cli, "B")
    assert c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                                 "row_version_esperada": _ver(owner, tid),
                                                                 "anadir": [a["id"]]}).status_code == 200
    antes = c.huella()
    r = c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                              "row_version_esperada": _ver(owner, tid), "quitar": [a["id"]]})
    c.rechazo_sin_cambios(cli, r, 409, "RETIRADA_NO_ADMITIDA", antes)
    r = c.post(cli, f"/v1/terceros/{tid}/clasificaciones", {"intencion_id": str(uuid.uuid4()),
                                                              "row_version_esperada": _ver(owner, tid), "principal": b["id"]})
    c.rechazo_sin_cambios(cli, r, 422, "ENTRADA_INVALIDA", antes)


def test_arbol_ciclo_y_nombre_repetido_entre_hermanos_activos(t):
    owner, cli, _ = t
    raiz = _clasif(cli, "Raiz")
    hija = _clasif(cli, "Hija", raiz["id"])
    nieta = _clasif(cli, "Nieta", hija["id"])
    antes = c.huella()
    # mover la raiz bajo su nieta -> ciclo
    r = c.post(cli, f"/v1/clasificaciones-tercero/{raiz['id']}/mover",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": raiz["row_version"], "parent_id": nieta["id"]})
    c.rechazo_sin_cambios(cli, r, 422, "CLASIFICACION_CICLO", antes)
    r = c.post(cli, f"/v1/clasificaciones-tercero/{raiz['id']}/mover",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": raiz["row_version"], "parent_id": raiz["id"]})
    c.rechazo_sin_cambios(cli, r, 422, "CLASIFICACION_CICLO", antes)
    # nombre repetido entre hermanos activos
    r = c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Hija", "parent_id": raiz["id"]})
    c.rechazo_sin_cambios(cli, r, 409, "CLASIFICACION_NOMBRE_REPETIDO", antes)
    # mismo nombre en otro nivel: OK; un hermano desactivado libera el nombre
    assert c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Hija"}).status_code == 200
    r = c.post(cli, f"/v1/clasificaciones-tercero/{hija['id']}/desactivar",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": hija["row_version"]})
    assert r.status_code == 200
    assert c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Hija", "parent_id": raiz["id"]}).status_code == 200
    # reactivar la desactivada choca con la nueva hermana activa
    todas = c.get(cli, "/v1/clasificaciones-tercero").json()["clasificaciones"]
    vieja = next(x for x in todas if x["nombre"] == "Hija" and x["enabled"] is False)
    r = c.post(cli, f"/v1/clasificaciones-tercero/{vieja['id']}/reactivar",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": vieja["row_version"]})
    c.rechazo(r, 409, "CLASIFICACION_NOMBRE_REPETIDO")


def test_renombrar_y_mover_con_version_y_replay(t):
    owner, cli, _ = t
    a, b = _clasif(cli, "A"), _clasif(cli, "B")
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": a["row_version"], "nombre": "A renombrada"}
    r = c.post(cli, f"/v1/clasificaciones-tercero/{a['id']}/renombrar", cuerpo)
    assert r.status_code == 200 and r.json()["clasificacion"]["nombre"] == "A renombrada"
    assert c.post(cli, f"/v1/clasificaciones-tercero/{a['id']}/renombrar", cuerpo).json()["idempotente"] is True
    r = c.post(cli, f"/v1/clasificaciones-tercero/{a['id']}/renombrar", {**cuerpo, "intencion_id": str(uuid.uuid4())})
    c.rechazo(r, 409, "VERSION_DESFASADA")
    r = c.post(cli, f"/v1/clasificaciones-tercero/{b['id']}/mover",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": b["row_version"], "parent_id": a["id"]})
    assert r.status_code == 200 and r.json()["clasificacion"]["parent_id"] == a["id"]


def test_las_rutas_de_direcciones_de_terceros_no_existen_en_este_bloque(t):
    owner, cli, tid = t
    for ruta in (f"/v1/terceros/{tid}/direcciones", f"/v1/terceros/{tid}/direcciones/{uuid.uuid4()}"):
        assert c.post(cli, ruta, {"intencion_id": str(uuid.uuid4())}).status_code in (404, 405)    # C-TER-02 fuera
