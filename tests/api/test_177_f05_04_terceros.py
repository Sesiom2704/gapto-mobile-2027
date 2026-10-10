# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_177_f05_04_terceros.py
# Ruta: tests/api/test_177_f05_04_terceros.py
# Descripcion: Terceros del registro (F05-04 J2 §1.3; F05 §46.3 A5/A7,
#   §46.4 R4/R5; F05-D032 C2, D-032.2). Por HTTP salvo lo indicado.
#   - Alta con UUID de cliente: id creado; mismo UUID y contenido ->
#     idempotente; mismo UUID con otro contenido o de otro owner ->
#     IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos (E09).
#   - Nombre (normalizacion visible C06, 1..160) y naturaleza (NULL =
#     «No lo sé»); ENTRADA_INVALIDA.
#   - Editar (estado completo), desactivar, reactivar con row_version;
#     VERSION_DESFASADA; TERCERO_NO_ENCONTRADO; auditoria CREAR/ACTUALIZAR.
#   - Naturaleza incompatible con tercero_personas -> trigger traducido por
#     firma -> TERCERO_NATURALEZA_NO_ADMITIDA (en es_ES y en C).
#   - Candidatos a duplicado por normalizacion C06, incluidos inactivos; sin
#     unicidad ni fusion (homonimos validos).
#   - Desactivar un tercero NO escribe plantillas ni preferencias (C2).
#   - Lista con `usos` (hechos activos) y aislamiento por owner.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.3)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

BASE = "/v1/terceros"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, actor, cli


def alta(cli, tid=None, **campos):
    tid = tid or uuid.uuid4()
    return tid, cli.post(BASE, json={"id": str(tid), **campos}, headers=h.AUTH)


def fila(owner, tid):
    f = h.leer(owner, "SELECT nombre, naturaleza, enabled, row_version FROM gapto.terceros WHERE id=%s", (tid,))
    return f[0] if f else None


def auditorias(owner, tid):
    return h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE tabla='terceros' AND registro_id=%s "
                         "ORDER BY created_at, id", (tid,))


def test_alta_normaliza_audita_y_es_idempotente(t):
    owner, _, cli = t
    tid, r = alta(cli, nombre="  Mercadona   SA ", naturaleza="EMPRESA")
    assert r.status_code == 200, r.text
    assert r.json()["tercero"]["nombre"] == "Mercadona SA" and r.json()["idempotente"] is False
    assert fila(owner, tid) == ("Mercadona SA", "EMPRESA", True, 1)
    _, r2 = alta(cli, tid, nombre="Mercadona SA", naturaleza="EMPRESA")
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    assert auditorias(owner, tid) == [("CREAR", "F05-04 TERCERO ALTA")]


def test_alta_minima_solo_con_nombre_no_lo_se(t):
    owner, _, cli = t
    tid, r = alta(cli, nombre="ALDI")
    assert r.status_code == 200 and fila(owner, tid) == ("ALDI", None, True, 1)


@pytest.mark.parametrize("cambio", [{"nombre": "Otro"}, {"naturaleza": "PERSONA"}])
def test_mismo_uuid_con_otro_contenido(t, cambio):
    owner, _, cli = t
    tid, _ = alta(cli, nombre="ALDI", naturaleza="EMPRESA")
    _, r = alta(cli, tid, **{"nombre": "ALDI", "naturaleza": "EMPRESA", **cambio})
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fila(owner, tid) == ("ALDI", "EMPRESA", True, 1) and len(auditorias(owner, tid)) == 1


def test_uuid_de_otro_owner_sin_efectos(t):
    owner, _, cli = t
    otro, _, cli_otro = ph.tenant()
    tid, r = alta(cli_otro, nombre="Ajeno")
    assert r.status_code == 200
    _, r = alta(cli, tid, nombre="Mio")
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fila(otro, tid) == ("Ajeno", None, True, 1) and fila(owner, tid) is None
    assert h.leer(owner, "SELECT count(*) FROM gapto.terceros")[0][0] == 0


@pytest.mark.parametrize("cuerpo", [{"nombre": "   "}, {"nombre": "x" * 161}, {"nombre": "Ok", "naturaleza": "ROBOT"},
                                    {"nombre": "Ok", "email": "a@b.c"}])
def test_entrada_invalida(t, cuerpo):
    owner, _, cli = t
    tid, r = alta(cli, **cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA"
    assert fila(owner, tid) is None


def test_editar_desactivar_reactivar_con_version_y_auditoria(t):
    owner, _, cli = t
    tid, _ = alta(cli, nombre="Repsol")
    r = cli.post(f"{BASE}/{tid}/editar", json={"row_version": 1, "nombre": "Repsol ", "naturaleza": None},
                 headers=h.AUTH)
    assert r.status_code == 200 and r.json()["idempotente"] is True  # mismo nombre visible: sin escritura
    r = cli.post(f"{BASE}/{tid}/editar", json={"row_version": 1, "nombre": "Repsol Cartagena",
                                               "naturaleza": "EMPRESA"}, headers=h.AUTH)
    assert r.status_code == 200 and fila(owner, tid) == ("Repsol Cartagena", "EMPRESA", True, 2)
    r = cli.post(f"{BASE}/{tid}/editar", json={"row_version": 1, "nombre": "X", "naturaleza": None}, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    assert cli.post(f"{BASE}/{tid}/desactivar", json={"row_version": 2}, headers=h.AUTH).status_code == 200
    assert cli.post(f"{BASE}/{tid}/desactivar", json={"row_version": 3}, headers=h.AUTH).json()["idempotente"]
    assert cli.post(f"{BASE}/{tid}/reactivar", json={"row_version": 3}, headers=h.AUTH).status_code == 200
    assert fila(owner, tid) == ("Repsol Cartagena", "EMPRESA", True, 4)
    assert [a[1] for a in auditorias(owner, tid)] == [
        "F05-04 TERCERO ALTA", "F05-04 TERCERO EDITAR", "F05-04 TERCERO DESACTIVAR", "F05-04 TERCERO REACTIVAR"]


@pytest.mark.parametrize("ruta", ["editar", "desactivar", "reactivar"])
def test_no_encontrado(t, ruta):
    _, _, cli = t
    cuerpo = {"row_version": 1, "nombre": "X", "naturaleza": None} if ruta == "editar" else {"row_version": 1}
    r = cli.post(f"{BASE}/{uuid.uuid4()}/{ruta}", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 404 and r.json()["codigo"] == "TERCERO_NO_ENCONTRADO"


def test_naturaleza_contra_tercero_personas_traducida_por_firma(t):
    """Traduccion por FIRMA de la funcion del trigger (no por texto): la suite
    se ejecuta en es_ES y en C (§5)."""
    owner, _, cli = t
    tid, _ = alta(cli, nombre="Ana", naturaleza="PERSONA")
    h.como_owner(owner, "INSERT INTO gapto.tercero_personas (tercero_id) VALUES (%s)", (tid,))
    r = cli.post(f"{BASE}/{tid}/editar", json={"row_version": 1, "nombre": "Ana", "naturaleza": "EMPRESA"},
                 headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "TERCERO_NATURALEZA_NO_ADMITIDA", r.text
    assert fila(owner, tid) == ("Ana", "PERSONA", True, 1)


def test_candidatos_por_normalizacion_incluidos_inactivos_y_homonimos_validos(t):
    owner, _, cli = t
    a, _ = alta(cli, nombre="Mercadona")
    b, _ = alta(cli, nombre="MERCADONA ")
    assert cli.post(f"{BASE}/{b}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    c, r = alta(cli, nombre="Mercadoná")  # homonimo tras normalizar: valido, sin fusion
    assert r.status_code == 200
    alta(cli, nombre="Mercadona Online")
    r = cli.get(f"{BASE}/candidatos", params={"nombre": " mercadona"}, headers=h.AUTH)
    assert r.status_code == 200
    ids = {x["id"]: x["enabled"] for x in r.json()["terceros"]}
    assert ids == {str(a): True, str(b): False, str(c): True}
    assert h.leer(owner, "SELECT count(*) FROM gapto.terceros")[0][0] == 4


def test_lista_con_usos_y_aislamiento(t):
    owner, actor, cli = t
    tid, _ = alta(cli, nombre="Uno")
    otro, _, cli_otro = ph.tenant()
    alta(cli_otro, nombre="Ajeno")
    lista = cli.get(BASE, headers=h.AUTH).json()["terceros"]
    assert [(x["nombre"], x["usos"]) for x in lista] == [("Uno", 0)]


def test_desactivar_no_toca_plantillas_ni_preferencias(t):
    owner, actor, cli = t
    cuenta = ph.cuenta(owner, actor)
    tid, _ = alta(cli, nombre="Proveedor")
    pid, r = ph.alta(cli, tercero_id=tid, cuenta_default_id=cuenta)
    assert r.status_code == 200
    plantilla = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.plantillas_registro (id, owner_user_id, nombre, tipo_hecho_id, tercero_id) "
                        "VALUES (%s,%s,'P',%s,%s)", (plantilla, owner, ph.tipo_gasto(owner), tid))
    antes = (h.leer(owner, "SELECT row_version, enabled FROM gapto.preferencias_registro WHERE id=%s", (pid,)),
             h.leer(owner, "SELECT row_version, enabled FROM gapto.plantillas_registro WHERE id=%s", (plantilla,)))
    assert cli.post(f"{BASE}/{tid}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    despues = (h.leer(owner, "SELECT row_version, enabled FROM gapto.preferencias_registro WHERE id=%s", (pid,)),
               h.leer(owner, "SELECT row_version, enabled FROM gapto.plantillas_registro WHERE id=%s", (plantilla,)))
    assert antes == despues


def test_el_writer_toma_el_advisory_terceros():
    """Barrera (TERCEROS, owner): el alta espera a quien lo retiene (C2)."""
    import threading
    import time

    import psycopg

    owner, _, cli = ph.tenant()
    x = fh.sesion_owner(owner)
    x.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:TERCEROS'), hashtext(%s::uuid::text))", (str(owner),))
    salida = {}
    hilo = threading.Thread(target=lambda: salida.update(r=alta(cli, nombre="Espera")[1]))
    hilo.start()
    pid_x = fh.pid_servidor(x)
    esperando = False
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        for _ in range(160):
            if mon.execute("SELECT count(*) FROM pg_stat_activity a WHERE %s = ANY(pg_blocking_pids(a.pid))",
                           (pid_x,)).fetchone()[0]:
                esperando = True
                break
            time.sleep(0.05)
    assert esperando and "r" not in salida
    x.execute("COMMIT")
    x.close()
    hilo.join(timeout=20)
    assert salida["r"].status_code == 200


def test_longitud_del_nombre_es_regla_de_dominio_sin_intentar_escribir():
    """El limite 1..160 lo decide el servicio antes de escribir (Rechazo de
    dominio), no el error fisico de la columna varchar(160)."""
    from app.terceros import servicio

    owner, _, _ = ph.tenant()
    r = fh.en_transaccion(owner, lambda s: servicio.alta(s, tercero_id=uuid.uuid4(), nombre="x" * 161))
    assert r == servicio.Rechazo("ENTRADA_INVALIDA")
    assert isinstance(fh.en_transaccion(owner, lambda s: servicio.alta(s, tercero_id=uuid.uuid4(),
                                                                      nombre="x" * 160)), servicio.Resultado)
