# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_164_f05_01_magnitudes_atomicidad.py
# Ruta: tests/api/test_164_f05_01_magnitudes_atomicidad.py
# Descripcion: Atomicidad de los comandos multirregistro (F05-D020 D-MAG-10,
#   condiciones B1..B6; AJ-S7MAG-01 B4; cierre de F05-01-R20). Se inyecta un
#   fallo REAL de PostgreSQL en la SEGUNDA escritura del comando, sustituyendo
#   la primitiva del repositorio por una que ejecuta SQL que falla:
#     - traducible (violacion de una UNIQUE con identidad conocida): el
#       comando devuelve el rechazo traducido y NO queda ninguna mutacion de
#       la primera escritura ni ninguna auditoria (savepoint de comando);
#     - no traducible (NOT NULL sin constraint conocida): error interno
#       (VIOLACION_INVARIANTE_FISICA, 500) y rollback total.
#   Comandos: alta rapida + asociacion, reordenar, retirar con compactacion y
#   desactivar(RAMA) de categorias (B5). Ademas, R19: un `42501` en cualquier
#   escritura es un error tecnico observable (500) con rollback total, nunca
#   MAGNITUD_NO_ADMITIDA.
#   Base local desechable 0001..0340.
# Version: 0.1.0 (F05-01 S7-MAG)
# Version: 0.2.0 (F05-01 S7-MAG correctivo AJ-S7MAGIMPL-01; D32 ajustada): 42501
#   real (privilegio o RLS WITH CHECK) inyectado en insertar_asociacion, flujos
#   EXISTENTE y NUEVA, y en insertar_magnitud (NUEVA): 500 tecnico, nunca
#   MAGNITUD_NO_ADMITIDA, huella de datos y auditoria identica (en NUEVA la
#   magnitud recien insertada tambien se revierte). La referencia ajena o
#   inexistente -> MAGNITUD_NO_ADMITIDA por prevalidacion sigue en test_162.
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

from app.categorias import repositorio as repo_cat
from app.magnitudes import repositorio as repo_mag

_ESCRITURAS_MAG = ("insertar_magnitud", "actualizar_magnitud", "insertar_asociacion", "actualizar_asociacion",
                   "eliminar_asociacion")


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, h.cliente(owner)


def _huella(owner) -> dict:
    """Todo lo que un comando S7-MAG o desactivar podria haber escrito."""
    return {
        "magnitudes": h.leer(owner, "SELECT id, nombre, enabled, row_version FROM gapto.magnitudes ORDER BY id"),
        "asociaciones": h.leer(owner, "SELECT id, categoria_id, magnitud_id, obligatoria, orden "
                                      "FROM gapto.categoria_magnitudes ORDER BY id"),
        "categorias": h.leer(owner, "SELECT id, enabled, row_version FROM gapto.categorias_financieras ORDER BY id"),
        "auditoria": h.leer(owner, "SELECT count(*) FROM gapto.auditoria")[0][0],
    }


def _choque(owner, nombre="Choque") -> None:
    h.crear_magnitud(owner, nombre)


def _fallar_en_segunda(monkeypatch, modulo, primitivas, fallo):
    """Sustituye las primitivas de escritura: la 2.a llamada (contando todas)
    ejecuta `fallo(sesion)` en lugar de escribir."""
    llamadas = {"n": 0}
    for nombre in primitivas:
        original = getattr(modulo, nombre)

        def envoltura(sesion, *a, _original=original, **kw):
            llamadas["n"] += 1
            if llamadas["n"] == 2:
                return fallo(sesion)
            return _original(sesion, *a, **kw)

        monkeypatch.setattr(modulo, nombre, envoltura)
    return llamadas


def _uq_magnitud(nombre="Choque"):
    # Traducible: uq_magnitudes__owner_nombre -> MAGNITUD_NOMBRE_DUPLICADO.
    return lambda s: s.uno("INSERT INTO gapto.magnitudes (owner_user_id, nombre, unidad_default, precision_decimales) "
                           "VALUES (current_setting('gapto.owner_user_id')::uuid, %s, 'u', 0) RETURNING id", (nombre,))


def _not_null_magnitud(s):
    # No traducible: NOT NULL sin constraint conocida -> VIOLACION_INVARIANTE_FISICA (500, rollback total).
    return s.uno("INSERT INTO gapto.magnitudes (owner_user_id, nombre, unidad_default, precision_decimales) "
                 "VALUES (current_setting('gapto.owner_user_id')::uuid, NULL, 'u', 0) RETURNING id")


FALLOS = {
    "TRADUCIBLE": (_uq_magnitud(), 409, "MAGNITUD_NOMBRE_DUPLICADO"),
    "NO_TRADUCIBLE": (_not_null_magnitud, 500, "VIOLACION_INVARIANTE_FISICA"),
}


def _comprobar(r, owner, antes, llamadas, esperado):
    status, codigo = esperado
    assert llamadas["n"] >= 2, "el fallo no se inyecto en la segunda escritura"
    assert r.status_code == status and r.json()["codigo"] == codigo, r.text
    assert _huella(owner) == antes  # cero mutaciones de datos y de auditoria


# ------------------------------------------------------------------ alta rapida + asociacion
@pytest.mark.parametrize("tipo", sorted(FALLOS))
def test_alta_rapida_y_asociacion_atomicas(ctx, monkeypatch, tipo):
    owner, cli = ctx
    _choque(owner)
    cat = fh.crear_categoria(owner, "Trabajo")
    antes = _huella(owner)
    fallo, *esperado = FALLOS[tipo]
    llamadas = _fallar_en_segunda(monkeypatch, repo_mag, _ESCRITURAS_MAG, fallo)
    r = cli.post(f"/v1/categorias/{cat}/magnitudes", headers=h.AUTH, json={
        "origen": "NUEVA", "obligatoria": True,
        "magnitud": {"magnitud_id": str(uuid.uuid4()), "nombre": "Horas", "unidad_default": "h",
                     "precision_decimales": 0}})
    _comprobar(r, owner, antes, llamadas, esperado)


# ------------------------------------------------------------------ reordenar
def _tres(owner):
    cat = fh.crear_categoria(owner, "Coche")
    ms = [h.crear_magnitud(owner, n) for n in ("A", "B", "C")]
    ids = [h.crear_asociacion(owner, cat, m, obligatoria=False, orden=i) for i, m in enumerate(ms)]
    return cat, list(zip(ids, ms))


@pytest.mark.parametrize("tipo", sorted(FALLOS))
def test_reordenar_atomico(ctx, monkeypatch, tipo):
    owner, cli = ctx
    _choque(owner)
    cat, filas = _tres(owner)
    antes = _huella(owner)
    fallo, *esperado = FALLOS[tipo]
    llamadas = _fallar_en_segunda(monkeypatch, repo_mag, _ESCRITURAS_MAG, fallo)
    pedido = [filas[2], filas[1], filas[0]]  # cambian las tres posiciones extremas: 2 escrituras
    r = cli.post(f"/v1/categorias/{cat}/magnitudes/reordenar", headers=h.AUTH, json={"asociaciones": [
        {"asociacion_id": str(a), "magnitud_id": str(m), "orden": [x[0] for x in filas].index(a),
         "obligatoria": False} for a, m in pedido]})
    _comprobar(r, owner, antes, llamadas, esperado)


# ------------------------------------------------------------------ retirar con compactacion
@pytest.mark.parametrize("tipo", sorted(FALLOS))
def test_retirar_con_compactacion_atomico(ctx, monkeypatch, tipo):
    owner, cli = ctx
    _choque(owner)
    cat, filas = _tres(owner)
    antes = _huella(owner)
    fallo, *esperado = FALLOS[tipo]
    llamadas = _fallar_en_segunda(monkeypatch, repo_mag, _ESCRITURAS_MAG, fallo)
    aid, mid = filas[0]
    r = cli.post(f"/v1/categorias/{cat}/magnitudes/{aid}/retirar", headers=h.AUTH,
                 json={"magnitud_id": str(mid), "obligatoria_actual": False})
    _comprobar(r, owner, antes, llamadas, esperado)


# ------------------------------------------------------------------ desactivar(RAMA), B5
def _fallos_categoria(raiz):
    return {
        # Traducible: pk_categorias_financieras -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
        "TRADUCIBLE": (lambda s: s.uno(
            "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
            "presupuestable_default) VALUES (%s, current_setting('gapto.owner_user_id')::uuid, NULL, 'Otra', "
            "'GASTO', true) RETURNING id", (raiz,)), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"),
        "NO_TRADUCIBLE": (lambda s: s.uno(
            "INSERT INTO gapto.categorias_financieras (owner_user_id, parent_id, nombre, ambito, "
            "presupuestable_default) VALUES (current_setting('gapto.owner_user_id')::uuid, NULL, NULL, 'GASTO', "
            "true) RETURNING id"), 500, "VIOLACION_INVARIANTE_FISICA"),
    }


@pytest.mark.parametrize("tipo", ["NO_TRADUCIBLE", "TRADUCIBLE"])
def test_desactivar_rama_atomico_b5(ctx, monkeypatch, tipo):
    owner, cli = ctx
    raiz = fh.crear_categoria(owner, "Raiz")
    fh.crear_categoria(owner, "Hija", parent_id=raiz)
    antes = _huella(owner)
    fallo, *esperado = _fallos_categoria(raiz)[tipo]
    llamadas = _fallar_en_segunda(monkeypatch, repo_cat, ("actualizar",), fallo)
    r = cli.post(f"/v1/categorias/{raiz}/desactivar", headers=h.AUTH, json={"modo": "RAMA", "row_version": 1})
    _comprobar(r, owner, antes, llamadas, esperado)


# ------------------------------------------------------------------ 42501 acotado (R19)
def _privilegio(sesion, **_):
    # 42501 de privilegio real: gapto_runtime no tiene DELETE sobre la realidad financiera (0200).
    return sesion.uno("DELETE FROM gapto.hechos_financieros WHERE false")


def _rls_ajena(magnitud_ajena):
    original = repo_mag.insertar_asociacion

    def con_magnitud_ajena(sesion, **kw):
        # 42501 por la RLS WITH CHECK de categoria_magnitudes (F5).
        return original(sesion, **{**kw, "magnitud_id": magnitud_ajena})
    return con_magnitud_ajena


@pytest.mark.parametrize("flujo,primitiva,origen", [
    ("EXISTENTE", "insertar_asociacion", "PRIVILEGIO"),
    ("EXISTENTE", "insertar_asociacion", "RLS"),
    ("NUEVA", "insertar_asociacion", "PRIVILEGIO"),
    ("NUEVA", "insertar_asociacion", "RLS"),
    ("NUEVA", "insertar_magnitud", "PRIVILEGIO"),
])
def test_42501_en_cualquier_escritura_es_error_tecnico_sin_mutaciones(ctx, monkeypatch, flujo, primitiva, origen):
    """AJ-S7MAGIMPL-01: 42501 nunca se traduce; sale como error tecnico con rollback total."""
    owner, cli = ctx
    otro, _ = h.crear_tenant()
    ajena = h.crear_magnitud(otro, "Ajena")
    cat = fh.crear_categoria(owner, "Propia")
    propia = h.crear_magnitud(owner, "Propia")
    antes = _huella(owner)
    monkeypatch.setattr(repo_mag, primitiva, _privilegio if origen == "PRIVILEGIO" else _rls_ajena(ajena))
    if flujo == "EXISTENTE":
        cuerpo = {"origen": "EXISTENTE", "magnitud_id": str(propia), "obligatoria": True}
    else:
        cuerpo = {"origen": "NUEVA", "obligatoria": False,
                  "magnitud": {"magnitud_id": str(uuid.uuid4()), "nombre": "Horas", "unidad_default": "h",
                               "precision_decimales": 0}}
    r = cli.post(f"/v1/categorias/{cat}/magnitudes", headers=h.AUTH, json=cuerpo)
    assert r.status_code == 500 and r.json()["codigo"] != "MAGNITUD_NO_ADMITIDA", r.text
    assert _huella(owner) == antes  # en NUEVA tampoco queda la magnitud de la primera escritura


def test_42501_por_privilegio_fuera_del_punto_prevalidado_no_se_enmascara(ctx, monkeypatch):
    owner, cli = ctx
    mid = h.crear_magnitud(owner, "Litros")
    antes = _huella(owner)
    # gapto_runtime no tiene DELETE sobre la realidad financiera (0200): 42501 de privilegio.
    monkeypatch.setattr(repo_mag, "actualizar_magnitud",
                        lambda sesion, *a, **kw: sesion.uno("DELETE FROM gapto.hechos_financieros WHERE false"))
    r = cli.post(f"/v1/magnitudes/{mid}/renombrar", headers=h.AUTH, json={"nombre": "Otro", "row_version": 1})
    # Error tecnico observable (el core lo clasifica TENANT_AUSENTE, 500), nunca un conflicto funcional.
    assert r.status_code == 500 and r.json()["codigo"] != "MAGNITUD_NO_ADMITIDA", r.text
    assert _huella(owner) == antes
