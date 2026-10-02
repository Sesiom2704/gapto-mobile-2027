# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_153_f05_01_lecturas_categorias.py
# Ruta: tests/api/test_153_f05_01_lecturas_categorias.py
# Descripcion: Lecturas del arbol de categorias (F05-01, S3):
#     - el arbol incluye las deshabilitadas, marcadas (D-198: la historia no
#       filtra por enabled);
#     - aislamiento de tenant (RLS) y orden estable orden/nombre/id;
#     - icon_key NULL se devuelve como NULL (fallback neutro, C08); la lectura
#       devuelve icon_key tal cual, incluidas claves legacy fuera de la
#       biblioteca (AJ-ICON-07); la escritura es S6-ICONO (test_159);
#     - uso historico por naturaleza cuenta solo efectos de hechos ACTIVOS y
#       no revela categorias ajenas (404).
#   Base local desechable 0001..0340 (estos tests confirman filas).
#
#   v0.1.1 (F05-01 S6-ICONO-AJ (AJ-S6ICONO-06)): solo cabecera; el comentario
#   Q4 (sin ruta de escritura de icon_key) quedo obsoleto con S6-ICONO.
#
#   v0.2.0 (F05-01 S7-MAG (F05-D020 D-MAG-04), commit 1): cada magnitud del
#   arbol trae `asociacion_id` = PK de la asociacion persistida, con el
#   conjunto exacto de claves del contrato (campo aditivo; nada se relaja).
# Version: 0.2.0
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


def test_arbol_magnitudes_con_asociacion_id_y_claves_exactas(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Luz", "GASTO")
    mid, cm = uuid.uuid4(), uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
                        "VALUES (%s, %s, 'Consumo', 'kWh', 2)", (mid, owner))
    h.como_owner(owner, "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
                        "VALUES (%s, %s, %s, true, 0)", (cm, cat, mid))
    cats = h.cliente(owner).get("/v1/categorias", headers=h.AUTH).json()["categorias"]
    [nodo] = [c for c in cats if c["id"] == str(cat)]
    [m] = nodo["magnitudes"]
    assert set(m) == {"asociacion_id", "magnitud_id", "nombre", "obligatoria", "orden", "enabled",
                      "unidad_default", "precision_decimales", "row_version"}
    assert m["asociacion_id"] == str(cm) and m["magnitud_id"] == str(mid)


def test_lecturas_exigen_token(tenant):
    owner, _, _ = tenant
    assert h.cliente(owner).get("/v1/categorias").status_code == 401
