# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_153_f05_01_lecturas_categorias.py
# Ruta: tests/api/test_153_f05_01_lecturas_categorias.py
# Descripcion: Lecturas del arbol de categorias (F05-01, S3):
#     - el arbol incluye las deshabilitadas, marcadas (D-198: la historia no
#       filtra por enabled);
#     - aislamiento de tenant (RLS) y orden estable orden/nombre/id;
#     - icon_key NULL se devuelve como NULL (fallback neutro, C08); no hay
#       ruta de escritura de icon_key (Q4);
#     - uso historico por naturaleza cuenta solo efectos de hechos ACTIVOS y
#       no revela categorias ajenas (404).
#   Base local desechable 0001..0340 (estos tests confirman filas).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


def test_arbol_incluye_deshabilitadas_y_respeta_orden(tenant):
    owner, _, _ = tenant
    raiz = fh.crear_categoria(owner, "Hogar", "GASTO", orden=2)
    hija = fh.crear_categoria(owner, "Luz", "GASTO", parent_id=raiz, orden=1, icon_key="bulb")
    vieja = fh.crear_categoria(owner, "Antigua", "AMBOS", enabled=False, orden=1)
    r = h.cliente(owner).get("/v1/categorias", headers=h.AUTH)
    assert r.status_code == 200, r.text
    cats = r.json()["categorias"]
    assert [c["id"] for c in cats] == [str(vieja), str(hija), str(raiz)]  # orden, nombre
    por_id = {c["id"]: c for c in cats}
    assert por_id[str(vieja)]["enabled"] is False
    assert por_id[str(hija)]["parent_id"] == str(raiz)
    assert por_id[str(hija)]["icon_key"] == "bulb"
    assert por_id[str(raiz)]["icon_key"] is None
    assert all(c["row_version"] >= 1 for c in cats)


def test_arbol_no_muestra_categorias_de_otro_tenant(tenant):
    owner, _, _ = tenant
    otro, _ = h.crear_tenant()
    fh.crear_categoria(otro, "Ajena", "GASTO")
    propia = fh.crear_categoria(owner, "Propia", "GASTO")
    cats = h.cliente(owner).get("/v1/categorias", headers=h.AUTH).json()["categorias"]
    assert [c["id"] for c in cats] == [str(propia)]


def test_no_existe_ruta_de_escritura_de_categorias(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Fija", "GASTO")
    cli = h.cliente(owner)
    for metodo in ("post", "put", "patch", "delete"):
        r = getattr(cli, metodo)(f"/v1/categorias/{cat}", headers=h.AUTH)
        assert r.status_code in (404, 405), (metodo, r.status_code)


def test_uso_por_naturaleza_solo_hechos_activos(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Supermercado", "GASTO")
    cli = h.cliente(owner)
    ids = []
    for _ in range(3):
        cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
        assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200
        ids.append(uuid.UUID(cuerpo["intencion_id"]))
    # Un hecho ANULADO no cuenta como uso vigente.
    h.como_owner(
        owner,
        "UPDATE gapto.hechos_financieros SET estado='ANULADO', anulado_at=now(), "
        "motivo_anulacion='test' WHERE id=%s",
        (ids[0],),
    )
    r = cli.get(f"/v1/categorias/{cat}/uso", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == {"categoria_id": str(cat), "ambito": "GASTO", "efectos_activos": {"GASTO": 2}}


def test_uso_de_categoria_sin_uso_es_vacio(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Nueva", "INGRESO")
    r = h.cliente(owner).get(f"/v1/categorias/{cat}/uso", headers=h.AUTH)
    assert r.json() == {"categoria_id": str(cat), "ambito": "INGRESO", "efectos_activos": {}}


@pytest.mark.parametrize("origen", ["OTRO_TENANT", "INEXISTENTE"])
def test_uso_de_categoria_ajena_o_inexistente_es_404(tenant, origen):
    owner, _, _ = tenant
    if origen == "OTRO_TENANT":
        otro, _ = h.crear_tenant()
        cat = fh.crear_categoria(otro, "Ajena", "GASTO")
    else:
        cat = uuid.uuid4()
    r = h.cliente(owner).get(f"/v1/categorias/{cat}/uso", headers=h.AUTH)
    assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO"


def test_lecturas_exigen_token(tenant):
    owner, _, _ = tenant
    assert h.cliente(owner).get("/v1/categorias").status_code == 401
