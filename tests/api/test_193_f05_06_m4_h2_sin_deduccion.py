# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_193_f05_06_m4_h2_sin_deduccion.py
# Ruta: tests/api/test_193_f05_06_m4_h2_sin_deduccion.py
# Descripcion: H2 y prueba negativa por tipo (F05-06 M4 §4.2; F05 §49.13 H2,
#   §51.4 AJ-F0506P-09; D-CAP-04/05; P-CAP-04).
#   - Cuentas de los 7 tipos (y ambas naturalezas) SIN filas de capacidad:
#     ninguna es elegible para ninguna de las cuatro operaciones del registro
#     (motivo SIN_CAPACIDAD), ni en la lectura ni en la confirmacion, y ninguna
#     preferencia ni plantilla puede proponerlas.
#   - Las lecturas de capacidades no contienen propuesta ni default: todas
#     las capacidades «no permitida», todas «sin configurar», respuestas
#     identicas salvo identidad y nombre, sin tipo ni naturaleza.
# Version: 0.1.0 (F05-06 M4 F1)
# ============================================================

from __future__ import annotations

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

FECHA = ph.FECHA
TIPOS = (("CORRIENTE", "ACTIVO"), ("AHORRO", "ACTIVO"), ("EFECTIVO", "ACTIVO"), ("CREDITO", "PASIVO"),
         ("POLIZA_CREDITO", "PASIVO"), ("PREPAGO", "ACTIVO"), ("OTRA", "ACTIVO"))
OPERACIONES = ("GASTO", "INGRESO", "TRANSFERENCIA_ORIGEN", "TRANSFERENCIA_DESTINO")
_PROHIBIDAS = ("tipo", "naturaleza", "sugerencia", "sugerida", "propuesta", "default", "recomendada")


@pytest.fixture()
def cuentas():
    owner, actor, cli = ph.tenant()
    ids = {}
    for tipo, naturaleza in TIPOS:
        cid = h.crear_cuenta(owner, [(actor, 100)], tipo=tipo, naturaleza=naturaleza, capacidades=())
        h.como_owner(owner, "UPDATE gapto.cuentas SET nombre=%s WHERE id=%s", (f"Cuenta {tipo.lower()}", cid))
        ids[tipo] = cid
    return owner, cli, ids


def _claves(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _claves(v)
    elif isinstance(x, list):
        for v in x:
            yield from _claves(v)


def test_siete_tipos_sin_filas_no_son_elegibles(cuentas):
    owner, cli, ids = cuentas
    from app.comun import elegibilidad_cuentas as e

    for op in OPERACIONES:
        filas = fh.en_transaccion(owner, lambda s, op=op: e.elegibilidad_cuentas(s, op, FECHA))
        assert {f["cuenta_id"] for f in filas} == set(ids.values())
        assert all(not f["elegible"] and f["motivo"] == "SIN_CAPACIDAD" for f in filas), op
        r = cli.get("/v1/cuentas/elegibles", params={"operacion": op, "fecha": FECHA.isoformat()}, headers=h.AUTH)
        assert r.status_code == 200 and r.json()["cuentas"] == [], (op, r.text)
    r = cli.get("/v1/vs01/cuentas-pago", params={"fecha": FECHA.isoformat()}, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["cuentas"] == [], r.text


@pytest.mark.parametrize("tipo", [t for t, _ in TIPOS])
def test_ninguna_confirmacion_por_tipo(cuentas, tipo):
    owner, cli, ids = cuentas
    r = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(ids[tipo]), headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CUENTA_SIN_CAPACIDAD", r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros")[0][0] == 0


def test_lecturas_sin_propuesta_ni_default_por_tipo(cuentas):
    owner, cli, ids = cuentas
    lista = cli.get("/v1/cuentas/capacidades", headers=h.AUTH).json()
    assert lista["sin_configurar"] == len(TIPOS)
    assert {c["cuenta_id"] for c in lista["cuentas"]} == {str(v) for v in ids.values()}
    detalles = [cli.get(f"/v1/cuentas/{cid}/capacidades", headers=h.AUTH).json() for cid in ids.values()]
    for cuerpo in [lista, *detalles]:
        assert not {k.lower() for k in _claves(cuerpo)} & set(_PROHIBIDAS), cuerpo
    for d in detalles:
        assert d["sin_configurar"] is True and d["origen_v3"] is False
        assert all(not c["permitida"] for c in d["capacidades"] + d["otras"])
    # Fuera de identidad y nombre, la respuesta no depende del tipo de la cuenta.
    neutras = [{k: v for k, v in d.items() if k not in ("cuenta_id", "nombre")} for d in detalles]
    assert all(n == neutras[0] for n in neutras)
    # Ninguna preferencia puede proponer una de estas cuentas.
    for cid in ids.values():
        _, r = ph.alta(cli, cuenta_default_id=cid)
        assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_CUENTA_NO_ELEGIBLE", r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.cuenta_capacidades")[0][0] == 0
