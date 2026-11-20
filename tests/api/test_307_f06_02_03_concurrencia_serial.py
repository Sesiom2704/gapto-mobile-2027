# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_307_f06_02_03_concurrencia_serial.py
# Ruta: tests/api/test_307_f06_02_03_concurrencia_serial.py
# Descripcion: F06-02/03 · Bateria SERIAL y determinista con COMMIT real, FUERA de la suite general: solo con
#   GAPTO_F060203_CONCURRENCIA=1 (base desechable). Tecnica de test_232/test_200 (reutilizada sin cambios): el primer
#   paso se detiene DENTRO de su transaccion en un punto fijo, ya con sus locks; con el retenido se lanza el segundo;
#   ambos ordenes, un resultado esperado por orden y oraculo de estado final. Oraculos comunes: nadie colgado, 0
#   reintentos 40P01 y 0 deadlocks nuevos. Escenarios:
#     K1 O-10  dos altas FORMALIZADO en la MISMA habitacion: la segunda espera el lock de la propiedad, relee y recibe
#              SOLAPE_CON_CONTRATO_FIRMADO; nunca quedan dos firmados;
#     K2 O-10  formalizar un borrador || alta firmada sobre la misma habitacion: exactamente uno firmado;
#     K3 O-10  alta firmada || terminacion cruzadas en la misma propiedad (con la terminacion primero el alta cabe);
#     K4 O-17  la MISMA intencion en dos propiedades: la segunda espera en el 0P y responde
#              IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION; el contrato solo existe en la primera;
#     K5 O-29  sucesor con tercero nuevo (writer de F05) || alta de tercero del mismo owner || C-PROP-02 de B1 sobre la
#              misma propiedad: 0 x 40P01, 0 deadlocks (propiedad antes que terceros);
#     K6 §1.3  orden de recursos observado con pg_locks: tras el nivel 3 solo el 0P y la propiedad bloqueada; el
#              advisory de terceros llega DESPUES (nunca antes que la propiedad).
#     K7 §8    C-CON-02 (editar) || C-CON-06 (anadir persona) sobre el MISMO contrato y la misma version: el segundo
#              espera en la propiedad, relee el contrato y recibe VERSION_DESFASADA; una sola escritura;
#     K8 §8    C-SRV-04 (tratamiento) || C-SRV-03 (baja del servicio): mismo orden §1.3; la baja siempre sale; con la
#              baja primero el tratamiento llega desfasado; al final ninguna fila de tratamiento abierta.
#   Mutantes que estas pruebas deben detectar (arnes de mutantes, no se ejecuta esta noche): alta sin lock de la
#   propiedad (K1/K2 en rojo); C-CON-01 con terceros antes que la propiedad y C-CON-05 con terceros antes que la
#   propiedad (K5/K6 en rojo).
#   ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.2.0 (F06 T3-F06 Bloque 3, paso 7): K7 y K8, los dos escenarios de concurrencia del mandato v1.2 §8 que
#   faltaban (C-CON-02 || C-CON-06 y C-SRV-04 || C-SRV-03).
#   Primera ejecucion con base: K5 se detiene en el advisory de terceros de F05 (repo_ter.tomar_advisory), que toman
#   los dos pasos (el writer de F05 no pasa por contratos.bloquear_terceros); K6 escapa el % del modulo en el SQL.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import os
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f06_01_b1_helpers as b1
import f06_02_03_helpers as c
import vs01_api_helpers as h
from app.contratos import servicio as serv
from app.contratos import servicios as serv_srv
from app.contratos.modelos import NuevoTercero, Persona
from app.core.contexto import ContextoOperacion
from app.propiedades import repositorio as repo_prop
from app.terceros import repositorio as repo_ter
from app.propiedades import servicio as serv_prop
from test_200_f05_06_m3_concurrencia_serial import Paso, Pausa, bloqueados, esperar
from test_232_f06_01_b1_concurrencia_serial import ORDENES, OK, RELOJ, correr, evidencia

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F060203_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F060203_CONCURRENCIA=1)")


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    return owner, cli


def ejecutar(owner, intencion_id, operacion):
    ctx = ContextoOperacion.de_usuario(owner, request_id=intencion_id)
    return fh.unidad().ejecutar(ctx, operacion, nombre="test F06-02/03 concurrencia")


def _datos(nombre, tercero, *, habitacion=1, estado="FORMALIZADO", inicio=dt.date(2026, 9, 1), personas=None):
    personas = personas if personas is not None else [
        Persona(rol="PROPIETARIO", yo=True, principal=True), Persona(rol="INQUILINO", tercero_id=tercero, principal=True)]
    return serv.DatosContrato(nombre=nombre, tipo="HABITACION", habitacion=habitacion, fecha_inicio=inicio,
                              fecha_fin_prevista=None, estado=estado, personas=personas)


def alta(owner, pid, cid, tercero, **kw):
    return lambda: ejecutar(owner, cid, lambda s: serv.alta(
        s, contrato_id=cid, propiedad_id=pid, datos=_datos(kw.pop("nombre", f"C-{str(cid)[:4]}"), tercero, **kw),
        reloj=RELOJ))


def formalizar(owner, cid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.formalizar(
        s, contrato_id=cid, intencion_id=i, row_version=version, reloj=RELOJ))


def terminar(owner, cid, version, fin=dt.date(2026, 10, 31)):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.terminar(
        s, contrato_id=cid, intencion_id=i, row_version=version, fecha_fin_real=fin, reloj=RELOJ))


def _propiedad(cli, **kw) -> uuid.UUID:
    return c.propiedad(cli, **kw)


def _pt_propiedad():
    return repo_prop, "bloquear"


def _uno(owner, sql, params=()):
    return h.leer(owner, sql, params)[0][0]


def _firmados(owner, pid, habitacion=1) -> int:
    return _uno(owner, "SELECT count(*) FROM gapto.contratos WHERE propiedad_entidad_id = %s AND habitacion = %s "
                       "AND estado_documental = 'FORMALIZADO'", (pid, habitacion))


# ------------------------------------------------------------------ K1
@pytest.mark.parametrize("orden", ORDENES)
def test_k1_dos_altas_firmadas_en_la_misma_habitacion(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana, luis = _propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Luis")
    traza, _ = correr(monkeypatch, caplog, "k1_dos_altas_misma_habitacion", orden,
                      ("ALTA-A", alta(owner, pid, uuid.uuid4(), ana, nombre="A"), _pt_propiedad()),
                      ("ALTA-B", alta(owner, pid, uuid.uuid4(), luis, nombre="B"), _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza                                  # espera al lock de la propiedad
    assert (traza[traza["primero"]], traza[traza["segundo"]]) == (OK, "SOLAPE_CON_CONTRATO_FIRMADO"), traza
    assert _firmados(owner, pid) == 1                                                  # nunca dos firmados


# ------------------------------------------------------------------ K2
@pytest.mark.parametrize("orden", ORDENES)
def test_k2_formalizar_frente_a_alta_firmada_en_la_misma_habitacion(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana, luis = _propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Luis")
    bor = c.crear(cli, pid, habitacion=1, estado="BORRADOR", personas=c.partes(luis), nombre="BOR")
    traza, _ = correr(monkeypatch, caplog, "k2_formalizar_frente_a_alta", orden,
                      ("FORMALIZAR", formalizar(owner, uuid.UUID(bor["id"]), bor["row_version"]), _pt_propiedad()),
                      ("ALTA", alta(owner, pid, uuid.uuid4(), ana, nombre="ALTA"), _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza
    assert (traza[traza["primero"]], traza[traza["segundo"]]) == (OK, "SOLAPE_CON_CONTRATO_FIRMADO"), traza
    assert _firmados(owner, pid) == 1


# ------------------------------------------------------------------ K3
@pytest.mark.parametrize("orden", ORDENES)
def test_k3_alta_y_terminacion_cruzadas_en_la_misma_propiedad(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana, luis = _propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Luis")
    viejo = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01", nombre="VIEJO")
    traza, _ = correr(monkeypatch, caplog, "k3_alta_y_terminacion", orden,
                      ("TERMINAR", terminar(owner, uuid.UUID(viejo["id"]), viejo["row_version"]), _pt_propiedad()),
                      ("ALTA", alta(owner, pid, uuid.uuid4(), luis, nombre="NUEVO", inicio=dt.date(2026, 11, 1)),
                       _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza
    assert traza["TERMINAR"] == OK                                                     # la terminacion siempre sale
    # con la terminacion primero, el alta (inicio posterior al fin real) cabe; con el alta primero, el viejo seguia
    # abierto y choca
    assert traza["ALTA"] == (OK if traza["primero"] == "TERMINAR" else "SOLAPE_CON_CONTRATO_FIRMADO"), traza
    assert _firmados(owner, pid) == (2 if traza["primero"] == "TERMINAR" else 1)


# ------------------------------------------------------------------ K4 · O-17
def test_k4_misma_intencion_en_dos_propiedades_espera_en_el_0p(t, monkeypatch, caplog):
    owner, cli = t
    p1, p2, ana = _propiedad(cli), _propiedad(cli), c.tercero(cli, "Ana")
    i = uuid.uuid4()
    traza, _ = correr(monkeypatch, caplog, "k4_misma_intencion_dos_propiedades", "A-primero",
                      ("ALTA-P1", alta(owner, p1, i, ana, nombre="X"), (serv, "bloquear_intencion_propiedad")),
                      ("ALTA-P2", alta(owner, p2, i, ana, nombre="X"), (serv, "bloquear_intencion_propiedad")))
    assert traza["segundo_bloqueado"] is True, traza                                    # esperando en el 0P
    assert (traza["ALTA-P1"], traza["ALTA-P2"]) == (OK, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), traza
    assert _uno(owner, "SELECT propiedad_entidad_id FROM gapto.contratos WHERE entidad_id = %s", (i,)) == p1
    assert _uno(owner, "SELECT count(*) FROM gapto.contratos WHERE entidad_id = %s", (i,)) == 1


# ------------------------------------------------------------------ K5 · O-29
def _sucesor_con_tercero_nuevo(owner, actual, pid_nuevo_tercero: uuid.UUID):
    i = uuid.uuid4()
    nuevo = serv.DatosContrato(
        nombre="SUC", tipo="HABITACION", habitacion=None, fecha_inicio=dt.date(2026, 11, 1), fecha_fin_prevista=None,
        estado="FORMALIZADO", personas=[Persona(rol="PROPIETARIO", yo=True, principal=True),
                                         Persona(rol="INQUILINO", principal=True,
                                                 nuevo=NuevoTercero(id=pid_nuevo_tercero, nombre="Inquilino nuevo",
                                                                    naturaleza="PERSONA"))])
    return lambda: ejecutar(owner, i, lambda s: serv.sucesor(
        s, contrato_id=uuid.UUID(actual["id"]), intencion_id=i, row_version=actual["row_version"],
        fecha_fin_real=dt.date(2026, 10, 31), nuevo=nuevo, reloj=RELOJ))


def _alta_tercero(owner):
    from app.terceros import servicio as serv_ter
    tid = uuid.uuid4()
    return lambda: ejecutar(owner, uuid.uuid4(), lambda s: serv_ter.alta(s, tercero_id=tid, nombre="Otro", naturaleza="PERSONA"))


def _editar_propiedad(owner, pid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv_prop.editar(
        s, entidad_id=pid, intencion_id=i, row_version=version, campos={"notas": "nota concurrente"}, reloj=RELOJ))


@pytest.mark.parametrize("orden", ORDENES)
def test_k5_sucesor_con_tercero_nuevo_frente_a_alta_de_tercero(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana = _propiedad(cli), c.tercero(cli, "Ana")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    traza, _ = correr(monkeypatch, caplog, "k5_sucesor_frente_a_alta_de_tercero", orden,
                      ("SUCESOR", _sucesor_con_tercero_nuevo(owner, actual, uuid.uuid4()), (repo_ter, "tomar_advisory")),
                      ("TERCERO", _alta_tercero(owner), (repo_ter, "tomar_advisory")))
    assert (traza["SUCESOR"], traza["TERCERO"]) == (OK, OK), traza                      # 0 x 40P01 y 0 deadlocks (correr)
    assert _uno(owner, "SELECT count(*) FROM gapto.contratos WHERE propiedad_entidad_id = %s", (pid,)) == 2


@pytest.mark.parametrize("orden", ORDENES)
def test_k5_sucesor_con_tercero_nuevo_frente_a_c_prop_02_de_b1(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana = _propiedad(cli), c.tercero(cli, "Ana")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    propiedad = b1.leer(cli, pid)
    traza, _ = correr(monkeypatch, caplog, "k5_sucesor_frente_a_c_prop_02", orden,
                      ("SUCESOR", _sucesor_con_tercero_nuevo(owner, actual, uuid.uuid4()), _pt_propiedad()),
                      ("PROP-02", _editar_propiedad(owner, pid, propiedad["row_version"]), _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza                                    # los dos toman la propiedad
    assert traza["SUCESOR"] == OK and traza["PROP-02"] == OK, traza


# ------------------------------------------------------------------ K6 · orden observado con pg_locks
def _advisory(cn, clave: str) -> int:
    return cn.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND "
        "classid::bigint = ((hashtext(%s)::bigint + 4294967296) %% 4294967296)", (clave,)).fetchone()[0]


def _propiedad_bloqueada(cn, pid) -> bool:
    try:
        with cn.transaction():
            cn.execute("SET LOCAL lock_timeout = '200ms'")
            cn.execute("SELECT 1 FROM gapto.entidades WHERE id = %s FOR UPDATE NOWAIT", (pid,))
        return False
    except psycopg.errors.LockNotAvailable:
        return True


def test_k6_la_propiedad_se_bloquea_antes_que_los_terceros(t, monkeypatch):
    owner, cli = t
    pid, ana = _propiedad(cli), c.tercero(cli, "Ana")
    nid = uuid.uuid4()
    personas = [Persona(rol="PROPIETARIO", yo=True, principal=True), Persona(rol="INQUILINO", principal=True,
                                                                              nuevo=NuevoTercero(id=nid, nombre="Nuevo"))]
    cid = uuid.uuid4()
    pausa = Pausa(monkeypatch, repo_prop, "bloquear", hilo="ALTA")                     # tras el nivel 3
    paso = Paso("ALTA", alta(owner, pid, cid, ana, personas=personas))
    try:
        paso.start()
        assert pausa.llego.wait(30)
        with psycopg.connect(h.dsn(), autocommit=True) as cn:
            tras_propiedad = {"0p": _advisory(cn, "gapto:INTENCION"), "terceros": _advisory(cn, "gapto:TERCEROS"),
                              "propiedad_bloqueada": _propiedad_bloqueada(cn, pid)}
    finally:
        pausa.sigue.set()
        paso.join(60)
    evidencia("k6_orden_locks_tras_propiedad", tras_propiedad)
    # tras el nivel 3: solo el 0P y la propiedad bloqueada; el advisory de terceros NO esta tomado todavia
    assert tras_propiedad == {"0p": 1, "terceros": 0, "propiedad_bloqueada": True}, tras_propiedad
    assert paso.codigo == OK
    # y no se toman INVERSIONES ni la raiz de OP-22 (el bloque no compone OP-22)
    assert _uno(owner, "SELECT count(*) FROM gapto.hechos_financieros") == 0


# ------------------------------------------------------------------ K7 · mandato v1.2 §8: C-CON-02 || C-CON-06
def _editar_notas(owner, cid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.editar(
        s, contrato_id=cid, intencion_id=i, row_version=version, campos={"notas": "nota concurrente"}, reloj=RELOJ))


def _anadir_avalista(owner, cid, version, tercero):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv.anadir_persona(
        s, contrato_id=cid, intencion_id=i, row_version=version, persona=Persona(rol="AVALISTA", tercero_id=tercero),
        desde=dt.date(2026, 10, 1), reloj=RELOJ))


@pytest.mark.parametrize("orden", ORDENES)
def test_k7_editar_frente_a_anadir_persona_en_el_mismo_contrato(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana, av = _propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Aval")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01", nombre="K7")
    cid, v = uuid.UUID(ct["id"]), ct["row_version"]
    traza, _ = correr(monkeypatch, caplog, "k7_editar_frente_a_personas", orden,
                      ("EDITAR", _editar_notas(owner, cid, v), _pt_propiedad()),
                      ("PERSONA", _anadir_avalista(owner, cid, v, av), _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza                       # espera al lock de la propiedad (nivel 3)
    # misma version leida por los dos: el segundo relee el contrato bajo su lock y recibe VERSION_DESFASADA
    assert (traza[traza["primero"]], traza[traza["segundo"]]) == (OK, "VERSION_DESFASADA"), traza
    assert _uno(owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (cid,)) == v + 1     # una sola escritura
    avalistas = _uno(owner, "SELECT count(*) FROM gapto.contrato_participantes WHERE contrato_entidad_id = %s "
                            "AND rol = 'AVALISTA'", (cid,))
    notas = _uno(owner, "SELECT notas FROM gapto.contratos WHERE entidad_id = %s", (cid,))
    assert (avalistas, notas) == ((0, "nota concurrente") if traza["primero"] == "EDITAR" else (1, None)), traza


# ------------------------------------------------------------------ K8 · mandato v1.2 §8: C-SRV-04 || C-SRV-03
def _tratamiento(owner, cid, sid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv_srv.tratamiento(
        s, contrato_id=cid, servicio_id=sid, intencion_id=i, row_version=version, modo="NO_REPERCUTIDO",
        inquilino_tercero_id=None, porcentaje=None, desde=dt.date(2026, 10, 1), reloj=RELOJ))


def _baja_servicio(owner, sid, version):
    i = uuid.uuid4()
    return lambda: ejecutar(owner, i, lambda s: serv_srv.baja(
        s, servicio_id=sid, intencion_id=i, row_version=version, fecha_fin_real=dt.date(2026, 11, 30), reloj=RELOJ))


@pytest.mark.parametrize("orden", ORDENES)
def test_k8_tratamiento_frente_a_baja_del_servicio(t, monkeypatch, caplog, orden):
    owner, cli = t
    pid, ana = _propiedad(cli), c.tercero(cli, "Ana")
    sid = c.servicio(cli, pid, tipo="LUZ", nombre="Luz K8")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01", nombre="K8",
                         servicios=[{"servicio_id": str(sid), "modo": "INCLUIDO"}])
    cid = uuid.UUID(ct["id"])
    v_srv = _uno(owner, "SELECT row_version FROM gapto.entidades WHERE id = %s", (sid,))
    traza, _ = correr(monkeypatch, caplog, "k8_tratamiento_frente_a_baja", orden,
                      ("TRATAMIENTO", _tratamiento(owner, cid, sid, ct["row_version"]), _pt_propiedad()),
                      ("BAJA", _baja_servicio(owner, sid, v_srv), _pt_propiedad()))
    assert traza["segundo_bloqueado"] is True, traza                       # mismo orden §1.3: espera en la propiedad
    assert traza["BAJA"] == OK, traza                                       # la baja siempre sale
    # con la baja primero, el contrato afectado sube de version y el tratamiento llega desfasado
    assert traza["TRATAMIENTO"] == (OK if traza["primero"] == "TRATAMIENTO" else "VERSION_DESFASADA"), traza
    # estado final: el servicio de baja y ninguna fila de tratamiento abierta (la baja cierra tambien la nueva)
    assert _uno(owner, "SELECT fecha_fin_real FROM gapto.servicios WHERE entidad_id = %s", (sid,)) == dt.date(2026, 11, 30)
    assert _uno(owner, "SELECT count(*) FROM gapto.contrato_servicios WHERE servicio_entidad_id = %s "
                       "AND vigente_hasta IS NULL", (sid,)) == 0
