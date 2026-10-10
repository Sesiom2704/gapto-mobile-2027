# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_178_f05_04_contextos.py
# Ruta: tests/api/test_178_f05_04_contextos.py
# Descripcion: Contextos del registro (F05-04 J2 §1.4; F05 §46.3 A6/A7,
#   §46.4 R4/R5; F05-D032 C2, D-032.2). Por HTTP salvo lo indicado.
#   - Alta = entidad CONTEXTO + contextos en UNA transaccion, UUID de cliente,
#     idempotente; mismo UUID con otro contenido, de otra entidad del owner o
#     de otro owner -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos.
#   - Tipo obligatorio (VIAJE..OTRO), fechas opcionales (fin >= inicio).
#   - Editar (estado completo), desactivar, reactivar con row_version de la
#     entidad; CONTEXTO_NO_ENCONTRADO; auditoria en `entidades`.
#   - El writer toma (CONTEXTOS, owner) y NUNCA INVERSIONES (C2): con
#     INVERSIONES retenido por otra sesion el alta no espera.
#   - Desactivar no escribe plantillas ni preferencias.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.4)
# ============================================================

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

BASE = "/v1/contextos"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, actor, cli


def alta(cli, cid=None, **campos):
    cid = cid or uuid.uuid4()
    cuerpo = {"id": str(cid), "nombre": "Finde Cartagena", "tipo_contexto": "VIAJE", **campos}
    return cid, cli.post(BASE, json=cuerpo, headers=h.AUTH)


def fila(owner, cid):
    f = h.leer(owner, "SELECT e.nombre, e.tipo_entidad, c.tipo_contexto, c.fecha_inicio, c.fecha_fin, e.enabled, "
                      "e.row_version FROM gapto.entidades e JOIN gapto.contextos c ON c.entidad_id = e.id "
                      "WHERE e.id=%s", (cid,))
    return f[0] if f else None


def test_alta_crea_entidad_y_subtipo_y_es_idempotente(t):
    owner, _, cli = t
    cid, r = alta(cli, fecha_inicio="2026-10-10", fecha_fin="2026-10-12")
    assert r.status_code == 200, r.text
    assert fila(owner, cid) == ("Finde Cartagena", "CONTEXTO", "VIAJE", dt.date(2026, 10, 10), dt.date(2026, 10, 12),
                                True, 1)
    _, r = alta(cli, cid, fecha_inicio="2026-10-10", fecha_fin="2026-10-12")
    assert r.status_code == 200 and r.json()["idempotente"] is True
    aud = h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE tabla='entidades' AND registro_id=%s", (cid,))
    assert aud == [("CREAR", "F05-04 CONTEXTO ALTA")]


def test_mismo_uuid_otro_contenido_otra_entidad_u_otro_owner(t):
    owner, _, cli = t
    cid, _ = alta(cli)
    _, r = alta(cli, cid, tipo_contexto="EVENTO")
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    prop = ph.entidad(owner)  # PROPIEDAD del mismo owner
    _, r = alta(cli, prop)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    otro, _, cli_otro = ph.tenant()
    ajeno, _ = alta(cli_otro)
    _, r = alta(cli, ajeno)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fila(otro, ajeno)[6] == 1 and fila(owner, ajeno) is None


@pytest.mark.parametrize("cambio", [{"nombre": " "}, {"tipo_contexto": "OTRA"}, {"tipo_contexto": None},
                                    {"fecha_inicio": "2026-10-12", "fecha_fin": "2026-10-10"}, {"notas": "x"}])
def test_entrada_invalida(t, cambio):
    owner, _, cli = t
    cid, r = alta(cli, **cambio)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA"
    assert h.leer(owner, "SELECT count(*) FROM gapto.entidades WHERE id=%s", (cid,))[0][0] == 0


def test_editar_desactivar_reactivar(t):
    owner, _, cli = t
    cid, _ = alta(cli)
    r = cli.post(f"{BASE}/{cid}/editar", json={"row_version": 1, "nombre": "Boda Ana", "tipo_contexto": "EVENTO",
                                               "fecha_inicio": "2026-11-07"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert fila(owner, cid) == ("Boda Ana", "CONTEXTO", "EVENTO", dt.date(2026, 11, 7), None, True, 2)
    r = cli.post(f"{BASE}/{cid}/editar", json={"row_version": 1, "nombre": "X", "tipo_contexto": "OTRO"},
                 headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    assert cli.post(f"{BASE}/{cid}/desactivar", json={"row_version": 2}, headers=h.AUTH).status_code == 200
    assert fila(owner, cid)[5:] == (False, 3)
    assert cli.post(f"{BASE}/{cid}/reactivar", json={"row_version": 3}, headers=h.AUTH).status_code == 200
    assert fila(owner, cid)[5:] == (True, 4)
    lista = cli.get(BASE, headers=h.AUTH).json()["contextos"]
    assert [(x["nombre"], x["tipo_contexto"], x["enabled"]) for x in lista] == [("Boda Ana", "EVENTO", True)]


@pytest.mark.parametrize("ruta", ["editar", "desactivar", "reactivar"])
def test_no_encontrado_incluida_entidad_de_otro_tipo(t, ruta):
    owner, _, cli = t
    cuerpo = {"row_version": 1, "nombre": "X", "tipo_contexto": "OTRO"} if ruta == "editar" else {"row_version": 1}
    for cid in (uuid.uuid4(), ph.entidad(owner)):
        r = cli.post(f"{BASE}/{cid}/{ruta}", json=cuerpo, headers=h.AUTH)
        assert r.status_code == 404 and r.json()["codigo"] == "CONTEXTO_NO_ENCONTRADO"


def _bloqueado_por(pid_x: int) -> bool:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        for _ in range(60):
            if mon.execute("SELECT count(*) FROM pg_stat_activity a WHERE %s = ANY(pg_blocking_pids(a.pid))",
                           (pid_x,)).fetchone()[0]:
                return True
            time.sleep(0.05)
    return False


@pytest.mark.parametrize("clave,espera", [("CONTEXTOS", True), ("INVERSIONES", False)])
def test_advisory_contextos_y_nunca_inversiones(t, clave, espera):
    owner, _, cli = t
    x = fh.sesion_owner(owner)
    x.execute(f"SELECT pg_advisory_xact_lock(hashtext('gapto:{clave}'), hashtext(%s::uuid::text))", (str(owner),))
    salida = {}
    hilo = threading.Thread(target=lambda: salida.update(r=alta(cli)[1]))
    hilo.start()
    try:
        assert _bloqueado_por(fh.pid_servidor(x)) is espera
        if not espera:
            hilo.join(timeout=20)
            assert salida["r"].status_code == 200
    finally:
        x.execute("COMMIT")
        x.close()
    hilo.join(timeout=20)
    assert salida["r"].status_code == 200


def test_desactivar_no_toca_plantillas_ni_preferencias(t):
    owner, actor, cli = t
    cid, _ = alta(cli)
    plantilla = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.plantillas_registro (id, owner_user_id, nombre, tipo_hecho_id, entidad_id) "
                        "VALUES (%s,%s,'P',%s,%s)", (plantilla, owner, ph.tipo_gasto(owner), cid))
    antes = h.leer(owner, "SELECT row_version, enabled FROM gapto.plantillas_registro WHERE id=%s", (plantilla,))
    assert cli.post(f"{BASE}/{cid}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    assert h.leer(owner, "SELECT row_version, enabled FROM gapto.plantillas_registro WHERE id=%s", (plantilla,)) == antes
