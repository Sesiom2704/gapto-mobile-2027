# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_181_f05_03_onboarding.py
# Ruta: tests/api/test_181_f05_03_onboarding.py
# Descripcion: Onboarding de categorias sugeridas (F05-03 J2 §1.8; F05 §45.3
#   A8, §45.4 R5; F05-D032 C5; caso 13 de §45.7).
#   - Fichero versionado: SHA-256 COMPLETO aprobado y 93 nodos en 23 grupos.
#   - Contrato del parser: rechazos de version, columnas, nivel sin padre,
#     ruta ambigua, icono no publicado, presupuesto o ambito ausentes;
#     ningun default inventado.
#   - Comando: crea el arbol con los writers de C06 (alta + reordenar) solo
#     con CERO categorias; IRPF / Renta AMBOS bajo un padre GASTO; reintento
#     con el arbol exacto idempotente; owner con categorias ->
#     ONBOARDING_NO_APLICABLE sin escribir; rechazo o fallo inyectado a mitad
#     -> cero categorias; SHA distinto -> no se parsea ni se escribe.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.8)
# ============================================================

from __future__ import annotations

import hashlib
import pathlib

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

SHA = "929b308e38f18da44d047e17dc7e5f2f0bf8be7446da9f7c725e93b915cc3fcc"
RUTA = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "app" / "categorias" / "onboarding"
        / "F05-03_categorias_sugeridas_v1.md")


def _n(owner) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.categorias_financieras")[0][0]


def test_fichero_exacto_y_93_nodos_en_23_grupos():
    from app.categorias import onboarding as o

    assert hashlib.sha256(RUTA.read_bytes()).hexdigest() == SHA == o.SHA256_V1
    nodos = o.arbol_v1()
    assert len(nodos) == 93 and sum(1 for n in nodos if n.nivel == 0) == 23
    assert len({n.ruta for n in nodos}) == 93
    irpf = next(n for n in nodos if n.nombre == "IRPF / Renta")
    assert irpf.ambito == "AMBOS" and irpf.presupuestable_default is False and irpf.padre is not None
    assert next(n for n in nodos if n.nombre == "Alquileres").ambito == "AMBOS"


def _alterar(antes: str, despues: str) -> bytes:
    texto = RUTA.read_bytes().decode("utf-8")
    assert antes in texto
    return texto.replace(antes, despues, 1).encode("utf-8")


@pytest.mark.parametrize("antes,despues", [
    ("— versión 1", "— versión 2"),
    ("| 1 | **Supermercados** | GASTO | Sí | `compras.carrito` |  |", "| 1 | **Supermercados** | GASTO | Sí | `compras.carrito` |"),
    ("| 1 | **Supermercados** | GASTO |", "| 1 | — — Supermercados | GASTO |"),
    ("| 2 | **Restaurantes** |", "| 2 | **Supermercados** |"),
    ("| 1 | **Supermercados** | GASTO | Sí | `compras.carrito`", "| 1 | **Supermercados** | GASTO | Sí | `compras.patinete`"),
    ("| 1 | **Supermercados** | GASTO | Sí |", "| 1 | **Supermercados** | GASTO |  |"),
    ("| 1 | **Supermercados** | GASTO |", "| 1 | **Supermercados** |  |"),
    ("| 2 | **Restaurantes**", "| 3 | **Restaurantes**"),
])
def test_contrato_del_parser_rechaza_sin_inventar(antes, despues):
    from app.categorias import onboarding as o

    with pytest.raises(o.ErrorFichero):
        o.parsear(_alterar(antes, despues))


def test_sha_distinto_no_parsea_ni_escribe(monkeypatch):
    from app.categorias import onboarding as o

    owner, _, cli = ph.tenant()
    monkeypatch.setattr(o, "SHA256_V1", "0" * 64)
    r = cli.post("/v1/categorias/onboarding", headers=h.AUTH)
    assert r.status_code == 500 and _n(owner) == 0


def test_crea_el_arbol_completo_con_c06_y_es_idempotente():
    owner, _, cli = ph.tenant()
    r = cli.post("/v1/categorias/onboarding", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == {"creadas": 93, "idempotente": False}
    arbol = cli.get("/v1/categorias", headers=h.AUTH).json()["categorias"]
    assert len(arbol) == 93
    por_id = {c["id"]: c for c in arbol}
    irpf = next(c for c in arbol if c["nombre"] == "IRPF / Renta")
    assert irpf["ambito"] == "AMBOS" and por_id[irpf["parent_id"]]["ambito"] == "GASTO"
    raiz = sorted((c for c in arbol if c["parent_id"] is None), key=lambda c: c["orden"])
    assert [c["nombre"] for c in raiz[:3]] == ["Supermercados", "Restaurantes", "Vivienda y hogar"]
    aud = h.leer(owner, "SELECT accion, count(*) FROM gapto.auditoria WHERE tabla='categorias_financieras' "
                        "GROUP BY accion ORDER BY accion")
    assert dict(aud)["CREAR"] == 93
    r2 = cli.post("/v1/categorias/onboarding", headers=h.AUTH)
    assert r2.status_code == 200 and r2.json() == {"creadas": 0, "idempotente": True}
    assert h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla='categorias_financieras'")[0][0] \
        == sum(n for _, n in aud)
    sug = cli.get("/v1/categorias/sugeridas", headers=h.AUTH).json()
    assert sug["version"] == 1 and len(sug["nodos"]) == 93


def test_owner_con_categorias_no_aplicable():
    owner, _, cli = ph.tenant()
    ph.categoria(owner, "Mía")
    r = cli.post("/v1/categorias/onboarding", headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "ONBOARDING_NO_APLICABLE" and _n(owner) == 1
    otro, _, cli_otro = ph.tenant()
    assert cli_otro.post("/v1/categorias/onboarding", headers=h.AUTH).status_code == 200
    h.como_owner(otro, "UPDATE gapto.categorias_financieras SET nombre='Súper' WHERE nombre='Supermercados'")
    r = cli_otro.post("/v1/categorias/onboarding", headers=h.AUTH)  # arbol ya no exacto
    assert r.status_code == 409 and r.json()["codigo"] == "ONBOARDING_NO_APLICABLE" and _n(otro) == 93


@pytest.mark.parametrize("como", ["rechazo", "excepcion"])
def test_fallo_a_mitad_deja_cero_categorias(monkeypatch, como):
    from app.categorias import onboarding as o
    from app.categorias import servicio as serv_cat

    owner, _, _ = ph.tenant()
    original, cuenta = serv_cat.alta, []

    def alta(sesion, **kw):
        cuenta.append(1)
        if len(cuenta) == 50:
            if como == "rechazo":
                return serv_cat.Rechazo("CATEGORIA_NOMBRE_DUPLICADO")
            raise RuntimeError("fallo inyectado")
        return original(sesion, **kw)

    monkeypatch.setattr(o.serv_cat, "alta", alta)
    if como == "rechazo":
        r = fh.en_transaccion(owner, o.onboarding_categorias)
        assert r == serv_cat.Rechazo("CATEGORIA_NOMBRE_DUPLICADO")
    else:
        with pytest.raises(Exception):
            fh.en_transaccion(owner, o.onboarding_categorias)
    assert _n(owner) == 0
    assert h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla='categorias_financieras'")[0][0] == 0
