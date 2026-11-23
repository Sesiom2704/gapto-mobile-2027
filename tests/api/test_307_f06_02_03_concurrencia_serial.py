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
# Version: 0.4.0 (F06 T3 · cadena de noche 21->22-11, T-C MANT N1 RK-ARN-03; dictamen del 21-11 §3 y AJ-03): la
#   medida de advisory locks (_advisory) y de esperas (K9) queda AISLADA: solo locks de la base del test y, en K6,
#   solo del backend retenido (pid capturado en el punto de pausa). K6-AIS demuestra que un advisory con la misma
#   clave en OTRA base del cluster o en OTRO backend de la misma base no entra en la medida.
# Version: 0.3.0 (F06 T3-F06 Bloque 3, B3-COMP, decision 11 de Moises): K9 O-29 sucesor con tercero nuevo || C-MEJ-01 v2
#   de PAG (writer certificado) sobre la misma propiedad, con foto de pg_locks en el punto de espera (la propiedad
#   antes que los terceros) y discriminante M-CON-46b (C-CON-05 con terceros antes que la propiedad).
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
from test_201_f05_06_m3_orden_locks import PausaEn
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
def _advisory(cn, clave: str, pid: int | None = None) -> int:
    """Advisory `clave` concedidos en la base de `cn` (RK-ARN-03: nunca de otra base del cluster) y, si se da `pid`,
    solo los de ese backend (el retenido en el punto de pausa)."""
    return cn.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND "
        "database = (SELECT oid FROM pg_database WHERE datname = current_database()) AND "
        "(%s::int IS NULL OR pid = %s::int) AND "
        "classid::bigint = ((hashtext(%s)::bigint + 4294967296) %% 4294967296)", (pid, pid, clave)).fetchone()[0]


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
    pausa = PausaEn(monkeypatch, repo_prop, "bloquear", hilo="ALTA")                   # tras el nivel 3 (con pid)
    paso = Paso("ALTA", alta(owner, pid, cid, ana, personas=personas))
    try:
        paso.start()
        assert pausa.llego.wait(30)
        with psycopg.connect(h.dsn(), autocommit=True) as cn:
            tras_propiedad = {"0p": _advisory(cn, "gapto:INTENCION", pausa.pid),
                              "terceros": _advisory(cn, "gapto:TERCEROS", pausa.pid),
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


# ------------------------------------------------------------------ K6-AIS · RK-ARN-03 (instrumento aislado)
def _dsn_otra_base(dsn: str, base: str) -> str:
    from psycopg import conninfo
    partes = conninfo.conninfo_to_dict(dsn)
    partes["dbname"] = base
    return conninfo.make_conninfo(**partes)


def test_k6_ais_la_medida_ignora_advisory_de_otra_base_y_de_otro_backend():
    """RK-ARN-03: el mismo advisory gapto:TERCEROS tomado en OTRA base del cluster (postgres) y en OTRO backend de
    esta base no entra en la medida de K6 (por pid) ni en la de K9 (por base). Control: el lock existe en el cluster."""
    clave = "gapto:TERCEROS"
    sql_tomar = "SELECT pg_advisory_lock(hashtext(%s), 0)"     # forma de dos claves, como la app (classid)
    dsn = h.dsn()
    with psycopg.connect(_dsn_otra_base(dsn, "postgres"), autocommit=True) as otra_base, \
            psycopg.connect(dsn, autocommit=True) as otro_backend, psycopg.connect(dsn, autocommit=True) as cn:
        otra_base.execute(sql_tomar, (clave,))
        foto = {"cluster": cn.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND "
            "classid::bigint = ((hashtext(%s)::bigint + 4294967296) %% 4294967296)", (clave,)).fetchone()[0],
            "k9_por_base_con_lock_en_otra_base": _advisory(cn, clave)}
        otro_backend.execute(sql_tomar, (clave,))
        pid_medido = cn.execute("SELECT pg_backend_pid()").fetchone()[0]
        foto.update({"k9_por_base_con_lock_en_esta_base": _advisory(cn, clave),
                     "k6_medido_en_un_backend_sin_el_lock": _advisory(cn, clave, pid_medido)})
        otro_backend.execute("SELECT pg_advisory_unlock_all()")
        otra_base.execute("SELECT pg_advisory_unlock_all()")
    evidencia("k6_ais_instrumento_aislado", foto)
    assert foto["cluster"] >= 1, foto                          # control: el lock ajeno existe
    assert foto["k9_por_base_con_lock_en_otra_base"] == 0, foto  # otra base del cluster: fuera
    assert foto["k9_por_base_con_lock_en_esta_base"] == 1, foto  # control positivo de la medida por base
    assert foto["k6_medido_en_un_backend_sin_el_lock"] == 0, foto         # otro backend de esta base: fuera


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


# ------------------------------------------------------------------ K9 · O-29 contra PAG (B3-COMP, decision 11)
# C-CON-05 (sucesor con tercero NUEVO, writer de F05) || C-MEJ-01 v2 de PAG (writer certificado, `gasto_propiedad`)
# sobre la MISMA propiedad. Orden certificado de los dos: 0P/raiz -> propiedad (el sucesor FOR NO KEY UPDATE, PAG FOR
# SHARE; conflictan) -> terceros. Foto de pg_locks con el primero retenido tras tomar la propiedad y el segundo ya
# esperando: ninguno de los dos tiene todavia el advisory de terceros (gapto:TERCEROS) y hay una espera real sobre la
# propiedad. Ambos acaban bien; 0 x 40P01 y 0 deadlocks nuevos. Discriminante: M-CON-46b (C-CON-05 con terceros
# antes que la propiedad) deja el advisory de terceros tomado en la foto -> este caso falla.
def _entorno_con_cuenta():
    import f05_05_helpers as x5
    return x5.entorno("2026-10-10T12:00:00")


def _gasto_pag(owner, cli, pid, cuenta, categoria):
    from app.patrimonio import gasto_propiedad
    from app.patrimonio.dto_b3 import GastoPropiedad
    fecha = "2026-05-15"
    r = cli.get(f"/v1/propiedades/{pid}/propuesta-gasto", params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    vista = {"criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": fecha,
             "partes": [{"actor_id": x["actor_id"], "porcentaje": x["porcentaje"]} for x in r.json()["partes"]]}
    iid = uuid.uuid4()
    cuerpo = {"intencion_id": str(iid), "propiedad_id": str(pid), "clase": "REPARACION", "importe": "300.00",
              "fecha_hecho": fecha, "cuenta_id": str(cuenta), "categoria_id": str(categoria), "presupuestable": True,
              "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": vista},
              "deuda": [], "derechos_confirmados": []}
    peticion = GastoPropiedad(**cuerpo).model_dump()
    return iid, lambda: ejecutar(owner, iid, lambda s: gasto_propiedad.registrar_gasto(s, peticion=peticion, reloj=RELOJ))


def _foto_k9(dsn: str, pid) -> dict:
    with psycopg.connect(dsn, autocommit=True) as cn:
        esperas = cn.execute("SELECT count(*) FROM pg_locks WHERE NOT granted AND pid IN (SELECT pid FROM "
                             "pg_stat_activity WHERE datname = current_database())").fetchone()[0]
        return {"advisory_terceros": _advisory(cn, "gapto:TERCEROS"), "esperas_no_concedidas": esperas,
                "propiedad_bloqueada": _propiedad_bloqueada(cn, pid),
                "pg_locks": [list(f) for f in cn.execute(
                    "SELECT l.locktype, l.mode, l.granted, c.relname FROM pg_locks l LEFT JOIN pg_class c "
                    "ON c.oid = l.relation WHERE l.pid <> pg_backend_pid() AND (l.locktype = 'advisory' OR "
                    "c.relnamespace = 'gapto'::regnamespace OR NOT l.granted) ORDER BY 1, 2, 4").fetchall()]}


@pytest.mark.parametrize("orden", ORDENES)
def test_k9_sucesor_con_tercero_nuevo_frente_a_pag_cmej01_en_la_misma_propiedad(monkeypatch, caplog, orden):
    import logging
    import time
    from app.patrimonio import gasto_propiedad
    from test_200_f05_06_m3_concurrencia_serial import LOGGER, deadlocks, reintentos
    owner, _actor, cli, cuenta, _ = _entorno_con_cuenta()
    pid, ana = _propiedad(cli), c.tercero(cli, "Ana")
    categoria = fh.crear_categoria(owner, "Hogar · Reparaciones", "GASTO")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    iid_pag, f_pag = _gasto_pag(owner, cli, pid, cuenta, categoria)
    a = ("SUCESOR", _sucesor_con_tercero_nuevo(owner, actual, uuid.uuid4()), (repo_prop, "bloquear"))
    b_ = ("PAG", f_pag, (gasto_propiedad, "bloquear_propiedad_compartida"))
    primero, segundo = (a, b_) if orden == "A-primero" else (b_, a)
    dsn = h.dsn()
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    antes = deadlocks(dsn)
    pausa = Pausa(monkeypatch, *primero[2], hilo=primero[0])
    p1, p2 = Paso(primero[0], primero[1]), Paso(segundo[0], segundo[1])
    traza: dict = {"escenario": "k9_sucesor_frente_a_pag_cmej01", "orden": [primero[0], segundo[0]]}
    try:
        p1.start()
        traza["primero_retenido"] = pausa.llego.wait(30)
        p2.start()
        esperar(lambda: not p2.is_alive() or len(bloqueados(dsn)) >= 1, 30)
        traza["segundo_bloqueado"] = p2.is_alive()
        traza["foto"] = _foto_k9(dsn, pid)
    finally:
        pausa.sigue.set()
        for p in (p1, p2):
            p.join(60)
    time.sleep(1.1)
    traza.update({p.name: p.codigo for p in (p1, p2)})
    traza.update({"vivos": [p.name for p in (p1, p2) if p.is_alive()],
                  "reintentos_40P01": reintentos(caplog, "40P01"), "reintentos_40001": reintentos(caplog, "40001"),
                  "deadlocks_delta": deadlocks(dsn) - antes})
    evidencia(f"k9_sucesor_frente_a_pag_cmej01_{orden}", traza)
    assert traza["primero_retenido"] and traza["segundo_bloqueado"], traza            # espera real en la propiedad
    assert traza["vivos"] == [] and traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    # la propiedad antes que los terceros: en el punto de espera nadie tiene el advisory de terceros
    assert traza["foto"]["advisory_terceros"] == 0, traza
    assert traza["foto"]["propiedad_bloqueada"] is True and traza["foto"]["esperas_no_concedidas"] >= 1, traza
    assert (traza["SUCESOR"], traza["PAG"]) == (OK, OK), traza
    assert _uno(owner, "SELECT count(*) FROM gapto.contratos WHERE propiedad_entidad_id = %s", (pid,)) == 2
    assert _uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (iid_pag,)) == 1
