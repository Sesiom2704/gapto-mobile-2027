# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_173_f05_03_conversion_preferencias.py
# Ruta: tests/api/test_173_f05_03_conversion_preferencias.py
# Descripcion: Conversion de las preferencias sin tipo (F05-03/F05-04 J2
#   §1.5; F05 §46.4 R6 «Conversion de preferencias sin tipo»; F05-D032 C4).
#   Comando preferencias/servicio.py::convertir_preferencias_sin_tipo:
#     - convierte TODAS las filas sin tipo del owner (habilitadas o no, con o
#       sin categoria) a GASTO, row_version + 1, auditoria ACTUALIZAR por fila
#       con antes/despues y motivo «F05-03 CONVERTIR_SIN_TIPO»;
#     - nunca toca filas con tipo; repetirla no hace nada (idempotente);
#     - aislamiento entre owners;
#     - fallo inyectado en la segunda fila -> rollback COMPLETO;
#     - concurrencia determinista frente a alta y edicion (barrera sobre el
#       advisory (PREFERENCIAS, owner), los dos ordenes, WM 12C.1).
#   Base desechable (GAPTO_TEST_DATABASE_URL); las filas sin tipo se escriben
#   por SQL directo (el writer ya no las crea, E3).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.5)
# ============================================================

from __future__ import annotations

import json

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h
from test_169_f05_02_concurrencia import _barrera

MOTIVO = "F05-03 CONVERTIR_SIN_TIPO"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="A")
    b = ph.cuenta(owner, actor, nombre="B")
    return owner, actor, cli, a, b


def _convertir(owner):
    from app.preferencias import servicio

    return fh.en_transaccion(owner, servicio.convertir_preferencias_sin_tipo)


def _auditorias_conversion(owner, pid):
    return h.leer(owner, "SELECT accion, datos_antes->>'tipo_hecho_id', datos_despues->>'tipo_hecho_id' "
                         "FROM gapto.auditoria WHERE tabla='preferencias_registro' AND registro_id=%s "
                         "AND motivo=%s", (pid, MOTIVO))


def test_convierte_todas_las_filas_sin_tipo_y_audita(t):
    owner, _, _, a, b = t
    cat = ph.categoria(owner, "Super")
    g = ph.tipo_gasto(owner)
    sin1 = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    sin2 = ph.insertar_sql(owner, tipo_hecho_id=None, categoria_id=cat, presupuestable=True, enabled=False)
    con = ph.insertar_sql(owner, cuenta=b)
    r = _convertir(owner)
    assert r.idempotente is False and sorted(r.convertidas) == sorted([sin1, sin2])
    for pid, enabled in ((sin1, True), (sin2, False)):
        f = ph.fila(owner, pid)
        assert f["tipo_hecho_id"] == g and f["row_version"] == 2 and f["enabled"] is enabled
        assert _auditorias_conversion(owner, pid) == [("ACTUALIZAR", None, str(g))]
    assert ph.fila(owner, sin2)["categoria_id"] == cat
    # La fila con tipo no se toca.
    assert ph.fila(owner, con)["row_version"] == 1 and ph.auditorias(owner, con) == []


def test_repetirla_no_hace_nada(t):
    owner, _, _, a, _ = t
    pid = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    assert _convertir(owner).convertidas == (pid,)
    r = _convertir(owner)
    assert r.idempotente is True and r.convertidas == ()
    assert ph.fila(owner, pid)["row_version"] == 2 and len(_auditorias_conversion(owner, pid)) == 1


def test_aislamiento_entre_owners(t):
    owner, _, _, a, _ = t
    otro, otro_actor = h.crear_tenant()
    ajena = ph.insertar_sql(otro, tipo_hecho_id=None, cuenta=ph.cuenta(otro, otro_actor))
    propia = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    assert _convertir(owner).convertidas == (propia,)
    assert ph.fila(otro, ajena)["tipo_hecho_id"] is None and ph.fila(otro, ajena)["row_version"] == 1


def test_fallo_inyectado_revierte_toda_la_conversion(t, monkeypatch):
    from app.core.errores import ErrorMotor
    from app.preferencias import servicio

    owner, _, _, a, b = t
    ids = sorted([ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a),
                  ph.insertar_sql(owner, tipo_hecho_id=None, presupuestable=True)])
    original = servicio._auditar
    llamadas = []

    def fallar_en_la_segunda(sesion, pid, operacion, antes):
        llamadas.append(pid)
        if len(llamadas) == 2:
            raise RuntimeError("fallo inyectado")
        return original(sesion, pid, operacion, antes)

    monkeypatch.setattr(servicio, "_auditar", fallar_en_la_segunda)
    # La UdT clasifica el fallo no reconocido como error interno y revierte.
    with pytest.raises(ErrorMotor):
        _convertir(owner)
    assert len(llamadas) == 2
    for pid in ids:
        assert ph.fila(owner, pid)["tipo_hecho_id"] is None and ph.fila(owner, pid)["row_version"] == 1
        assert ph.auditorias(owner, pid) == []


def test_la_conversion_espera_el_advisory(t):
    owner, _, _, a, _ = t
    pid = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    salida = _barrera(owner, [("conversion", lambda: _convertir(owner))])
    assert salida["conversion"].convertidas == (pid,)


@pytest.mark.parametrize("primero", ["conversion", "alta"])
def test_conversion_frente_a_alta(t, primero):
    """Alta de «Todos los gastos» contradictoria con la fila sin tipo: la fila
    sin tipo no participa del empate (E3) mientras no se convierte; una vez
    convertida si. Orden 1: conversion y luego alta -> la alta choca con la
    convertida (EMPATE). Orden 2: alta y luego conversion -> la alta entra y
    la conversion convierte igualmente (C4 convierte TODAS)."""
    owner, _, cli, a, b = t
    sin = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    pasos = {"conversion": lambda: _convertir(owner),
             "alta": lambda: ph.alta(cli, cuenta_default_id=b)[1]}
    orden = [(primero, pasos[primero])]
    segundo = "alta" if primero == "conversion" else "conversion"
    orden.append((segundo, pasos[segundo]))
    salida = _barrera(owner, orden)
    assert salida["conversion"].convertidas == (sin,)
    if primero == "conversion":
        r = salida["alta"]
        assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_EMPATE_CONTRADICTORIO"
        assert ph.n_preferencias(owner) == 1
    else:
        assert salida["alta"].status_code == 200
        assert ph.n_preferencias(owner) == 2
    assert ph.fila(owner, sin)["tipo_hecho_id"] == ph.tipo_gasto(owner)


@pytest.mark.parametrize("primero", ["conversion", "edicion"])
def test_conversion_frente_a_edicion(t, primero):
    """La edicion de una fila sin tipo que le da tipo INGRESO. Orden 1:
    conversion primero -> la fila pasa a GASTO (row_version 2) y la edicion
    con row_version 1 responde VERSION_DESFASADA. Orden 2: edicion primero ->
    la fila ya tiene tipo y la conversion no la toca."""
    owner, _, cli, a, _ = t
    sin = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    ingreso = h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo='INGRESO'")[0][0]
    pasos = {"conversion": lambda: _convertir(owner),
             "edicion": lambda: ph.editar(cli, sin, 1, tipo_hecho_id=ingreso, cuenta_default_id=a)}
    segundo = "edicion" if primero == "conversion" else "conversion"
    salida = _barrera(owner, [(primero, pasos[primero]), (segundo, pasos[segundo])])
    f = ph.fila(owner, sin)
    if primero == "conversion":
        assert salida["conversion"].convertidas == (sin,)
        assert salida["edicion"].status_code == 409 and salida["edicion"].json()["codigo"] == "VERSION_DESFASADA"
        assert f["tipo_hecho_id"] == ph.tipo_gasto(owner) and f["row_version"] == 2
    else:
        assert salida["edicion"].status_code == 200, salida["edicion"].text
        assert salida["conversion"].convertidas == () and salida["conversion"].idempotente is True
        assert f["tipo_hecho_id"] == ingreso and f["row_version"] == 2


def test_auditoria_lleva_el_snapshot_completo(t):
    owner, _, _, a, _ = t
    pid = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    _convertir(owner)
    antes, despues = h.leer(owner, "SELECT datos_antes::text, datos_despues::text FROM gapto.auditoria "
                                   "WHERE registro_id=%s AND motivo=%s", (pid, MOTIVO))[0]
    antes, despues = json.loads(antes), json.loads(despues)
    assert antes["row_version"] == 1 and despues["row_version"] == 2
    assert antes["cuenta_default_id"] == despues["cuenta_default_id"] == str(a)
