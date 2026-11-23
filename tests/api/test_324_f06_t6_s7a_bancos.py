# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_324_f06_t6_s7a_bancos.py
# Ruta: tests/api/test_324_f06_t6_s7a_bancos.py
# Descripcion: F06 T6 · S7-A (N2): bancos (DP-09, DT-04; F09 0.55 §12.107.3). Base fisica existente
#   (gapto.tercero_roles, rol ENTIDAD_FINANCIERA; 0010), sin DDL, GRANT ni RLS nuevos. `GET /v1/terceros?rol=
#   ENTIDAD_FINANCIERA` lista SOLO los terceros marcados (el rol lo escribe el usuario con la ruta de roles de
#   siempre, `POST /v1/terceros/{id}/roles`; nunca se deriva). Sin el parametro, la ruta no cambia. El rol se
#   persiste y es solo aditivo (contrato certificado C-TER-01: quitar -> RETIRADA_NO_ADMITIDA). Aislamiento por
#   owner. Discriminante del mutante «selector sin filtro».
#   Exige GAPTO_TEST_DATABASE_URL (base local DESECHABLE con la cadena aplicada).
# Version: 0.1.0 (F06 T6 · S7-A)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, cli


def _alta(cli, nombre: str) -> dict:
    r = cli.post("/v1/terceros", json={"id": str(uuid.uuid4()), "nombre": nombre, "naturaleza": "EMPRESA"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["tercero"]


def _marcar_banco(cli, t: dict):
    return cli.post(f"/v1/terceros/{t['id']}/roles", json={"intencion_id": str(uuid.uuid4()),
                                                           "row_version_esperada": t["row_version"], "anadir": ["ENTIDAD_FINANCIERA"]},
                    headers=h.AUTH)


def _nombres(cli, q: str = "") -> list[str]:
    r = cli.get(f"/v1/terceros{q}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return [x["nombre"] for x in r.json()["terceros"]]


def test_solo_los_marcados_como_banco_y_sin_parametro_todos(t):
    owner, cli = t
    banco = _alta(cli, "Banco Ejemplo")
    _alta(cli, "Super ALDI")
    assert _nombres(cli, "?rol=ENTIDAD_FINANCIERA") == []                                     # nunca derivado del nombre
    r = _marcar_banco(cli, banco)
    assert r.status_code == 200, r.text
    assert h.leer(owner, "SELECT rol_codigo FROM gapto.tercero_roles WHERE tercero_id = %s", (banco["id"],)) == [("ENTIDAD_FINANCIERA",)]
    assert _nombres(cli, "?rol=ENTIDAD_FINANCIERA") == ["Banco Ejemplo"]                      # selector con filtro
    assert sorted(_nombres(cli)) == ["Banco Ejemplo", "Super ALDI"]                           # sin parametro: no cambia


def test_otro_rol_no_cuenta_como_banco_y_el_rol_es_solo_aditivo(t):
    _, cli = t
    comercio = _alta(cli, "Comercio")
    r = cli.post(f"/v1/terceros/{comercio['id']}/roles", json={"intencion_id": str(uuid.uuid4()),
                 "row_version_esperada": comercio["row_version"], "anadir": ["COMERCIO"]}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert _nombres(cli, "?rol=ENTIDAD_FINANCIERA") == []
    banco = _alta(cli, "Caja")
    assert _marcar_banco(cli, banco).status_code == 200
    fila = cli.get("/v1/terceros?rol=ENTIDAD_FINANCIERA", headers=h.AUTH).json()["terceros"][0]
    r = cli.post(f"/v1/terceros/{banco['id']}/roles", json={"intencion_id": str(uuid.uuid4()),
                 "row_version_esperada": fila["row_version"], "anadir": [], "quitar": ["ENTIDAD_FINANCIERA"]}, headers=h.AUTH)
    assert r.status_code != 200 and r.json()["codigo"] == "RETIRADA_NO_ADMITIDA"              # contrato certificado: no se quita


def test_rol_invalido_en_el_filtro_422(t):
    _, cli = t
    assert cli.get("/v1/terceros?rol=COMERCIO", headers=h.AUTH).status_code == 422


def test_aislamiento_por_owner(t):
    _, cli = t
    _marcar_banco(cli, _alta(cli, "Mi banco"))
    _, _, otro = ph.tenant()
    assert _nombres(otro, "?rol=ENTIDAD_FINANCIERA") == []
