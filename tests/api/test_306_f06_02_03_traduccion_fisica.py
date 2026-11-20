# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_306_f06_02_03_traduccion_fisica.py
# Ruta: tests/api/test_306_f06_02_03_traduccion_fisica.py
# Descripcion: F06-02/03 · O-15 TRADUCCION DE VIOLACIONES FISICAS (contrato v1.1 §1.5; PC-CON-05; AJ-DELTA-02,
#   AJ-COMP-04). Para CADA fila del mapa, un MUTANTE (monkeypatch en proceso) que SALTA la validacion previa del
#   servicio fuerza el camino fisico y se comprueba predicado <-> SQLSTATE <-> codigo <-> HTTP <-> mensaje, con la
#   huella del estado identica (el savepoint de la operacion deshace todo). Filas del mapa y su mutante:
#     EXCLUDE personas/actor/rol .......... `_duplicada` -> False                    -> PARTICIPANTE_DUPLICADO 422
#     EXCLUDE principal por rol ........... `_principal_solapado`/`_principales_ok`  -> PRINCIPAL_DUPLICADO 422
#     EXCLUDE contrato_servicios .......... `cerrar_vigencia` no cierra la abierta   -> TRATAMIENTO_SOLAPADO 409
#     EXCLUDE propiedad_servicios ......... (sin ruta HTTP que lo alcance) insercion doble por el repositorio
#                                                                                     -> SERVICIO_YA_VINCULADO 409
#     EXCLUDE clausula .................... `cerrar_vigencia` no cierra la abierta   -> CLAUSULA_SOLAPADA 409
#     ck_contratos__habitacion ............ `_validar_habitacion` -> None             -> HABITACION_NO_ADMITIDA 422
#     ck_contrato_servicios__repercusion_coherente / __renta_repercutible_excl / __porcentaje
#                                          `columnas_tratamiento` incoherente         -> TRATAMIENTO_INCOMPATIBLE 422
#     ck_contrato_participantes__rol ...... `ROLES` ampliado con un rol inventado     -> ROL_DESCONOCIDO 422
#     ck_tercero_roles__rol_codigo ........ `ROLES_TERCERO` + AGENCIA                 -> ROL_DESCONOCIDO 422
#     ck_..._clausula (porcentaje fijo / ninguna sin parametros) `validar_clausula` incoherente -> CLAUSULA_INCOMPLETA
#     ck_contratos__fin_prevista_no_anterior / __fin_real_no_anterior                 -> FECHA_ANTERIOR_INICIO 422
#     uq nombre de clasificacion entre hermanos activos (23505)                       -> CLASIFICACION_NOMBRE_REPETIDO 409
#     trigger aciclico (P0001, por la FIRMA de fn_check_jerarquia_aciclica()) -> CLASIFICACION_CICLO 422 (C-31 cerrado, contrato v1.2)
#   Lo que NINGUNA constraint garantiza (principal obligatorio, partes, ultimo inquilino/arrendador, solape,
#   INQUILINO_NO_PUEDE_SER_YO, ROL_NO_ADMITIDO_PARA_YO): el mutante omite la validacion del servicio y la prueba
#   detecta la FILA INDEBIDA en la base (estado), no un SQLSTATE.
#   POLITICA DE EXCLUSION: una constraint FUERA del mapa NO se traduce (500 generico sin codigo de dominio).
#   ESCRITO SIN EJECUTAR (sin base esta noche). Los mutantes son en proceso (TestClient): nunca tocan el disco.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal as D

import psycopg
import pytest

import f05_01_helpers as fh
import f06_02_03_helpers as c
from app.contratos import base as base_mod
from app.contratos import errores as e
from app.contratos import modelos
from app.contratos import repositorio as repo
from app.contratos import servicio as serv
from app.contratos import terceros as ter
from app.core.contexto import ContextoOperacion


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    return owner, cli, pid, ana


def en_unidad(owner, operacion):
    """Ejecuta `operacion(sesion)` como gapto_runtime con RLS (una transaccion)."""
    return fh.unidad().ejecutar(ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()), operacion,
                                nombre="test O-15")


def verificar(r, codigo: str, antes: str) -> None:
    """predicado <-> SQLSTATE <-> codigo <-> HTTP <-> mensaje, y la huella intacta."""
    status, mensaje = e.RECHAZOS[codigo]
    assert r.status_code == status, r.text
    cuerpo = r.json()
    assert cuerpo["codigo"] == codigo and cuerpo["mensaje"] == mensaje, r.text
    assert c.huella() == antes, f"{codigo}: el camino fisico dejo estado"


def _sin(*a, **k):
    return None


def _falso(*a, **k):
    return False


# ================================================================== EXCLUDE (23P01)
def test_exclude_personas_por_contrato_actor_y_rol(t, monkeypatch):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    monkeypatch.setattr(serv, "_duplicada", _falso)                          # salta la validacion previa
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(ana)}, rol="INQUILINO",
                                                              desde="2026-09-01"))
    verificar(r, "PARTICIPANTE_DUPLICADO", antes)


def test_exclude_un_principal_por_contrato_y_rol(t, monkeypatch):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None)
    antes = c.huella()
    monkeypatch.setattr(serv, "_principal_solapado", _falso)
    monkeypatch.setattr(serv, "_principales_ok", _sin)
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(luis)}, rol="INQUILINO",
                                                              principal=True, desde="2026-09-01"))
    verificar(r, "PRINCIPAL_DUPLICADO", antes)


def test_exclude_principal_tambien_para_agencia_tras_0355(t, monkeypatch):
    """AGENCIA y ADMINISTRADOR heredan la EXCLUDE de principal (es por rol). Con `0354` el rol no existe (23514 ->
    ROL_DESCONOCIDO); con `0355` el segundo principal de AGENCIA llega a la EXCLUDE."""
    owner, cli, pid, ana = t
    a1, a2 = c.tercero(cli, "Agencia 1", "EMPRESA"), c.tercero(cli, "Agencia 2", "EMPRESA")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    ct = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(a1)}, rol="AGENCIA",
                                                               principal=True, desde="2026-09-01")).json()["contrato"]
    antes = c.huella()
    monkeypatch.setattr(serv, "_principal_solapado", _falso)
    monkeypatch.setattr(serv, "_principales_ok", _sin)
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(a2)}, rol="AGENCIA",
                                                              principal=True, desde="2026-09-01"))
    verificar(r, "PRINCIPAL_DUPLICADO", antes)


def test_exclude_tratamiento_por_contrato_y_servicio(t, monkeypatch):
    owner, cli, pid, ana = t
    luz = c.servicio(cli, pid)
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01",
                         servicios=[{"servicio_id": str(luz), "modo": "INCLUIDO"}])
    antes = c.huella()
    monkeypatch.setattr(repo, "cerrar_vigencia", _sin)                       # no cierra la fila abierta
    r = c.post(cli, c.ruta(ct["id"], f"/servicios/{luz}"), c.cuerpo_v(ct, modo="NO_REPERCUTIDO", desde="2026-07-01"))
    verificar(r, "TRATAMIENTO_SOLAPADO", antes)


def test_exclude_servicio_vinculado_a_la_propiedad_sin_ruta_http(t):
    """No hay operacion HTTP que vincule un servicio YA existente a una propiedad: el reverso fisico se prueba por el
    camino del repositorio (la unica via es insertar dos vinculos solapados)."""
    owner, cli, pid, _ = t
    luz = c.servicio(cli, pid, desde="2026-01-01")
    antes = c.huella()

    def doble(sesion):
        return base_mod.ejecutar_escritura(sesion, lambda: repo.insertar_vinculo_propiedad(
            sesion, fila_id=uuid.uuid4(), servicio_id=luz, propiedad_id=pid, desde=dt.date(2026, 6, 1), hasta=None))

    rechazo = en_unidad(owner, doble)
    assert rechazo is not None and rechazo.codigo == "SERVICIO_YA_VINCULADO"
    assert e.rechazo_http("SERVICIO_YA_VINCULADO")[0] == 409 and c.huella() == antes


def test_exclude_clausula_sin_solape(t, monkeypatch):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01", clausula_revision={"tipo": "IPC"})
    antes = c.huella()
    monkeypatch.setattr(repo, "cerrar_vigencia", _sin)
    r = c.post(cli, c.ruta(ct["id"], "/clausula"), c.cuerpo_v(ct, desde="2027-03-01", clausula={"tipo": "NINGUNA"}))
    verificar(r, "CLAUSULA_SOLAPADA", antes)


# ================================================================== CHECK (23514)
def test_check_habitacion_solo_en_habitacion(t, monkeypatch):
    owner, cli, pid, _ = t
    antes = c.huella()
    monkeypatch.setattr(serv, "_validar_habitacion", _sin)
    r = c.alta(cli, pid, tipo="VIVIENDA_COMPLETA", habitacion=2, estado="BORRADOR")
    verificar(r, "HABITACION_NO_ADMITIDA", antes)


@pytest.mark.parametrize("columnas,nombre", [
    (dict(incluido_en_renta=False, repercutible=True, modo_reparto="POR_FACTURA", porcentaje_repercutible=D("50")),
     "ck_contrato_servicios__repercusion_coherente"),
    (dict(incluido_en_renta=True, repercutible=True, modo_reparto="FIJO", porcentaje_repercutible=D("50")),
     "ck_contrato_servicios__renta_repercutible_excl"),
    (dict(incluido_en_renta=False, repercutible=True, modo_reparto="FIJO", porcentaje_repercutible=D("150")),
     "ck_contrato_servicios__porcentaje"),
])
def test_check_tratamiento_incompatible(t, monkeypatch, columnas, nombre):
    owner, cli, pid, ana = t
    luz = c.servicio(cli, pid)
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")
    antes = c.huella()
    monkeypatch.setattr(modelos, "columnas_tratamiento", lambda modo, actor, pct: {
        **columnas, "actor_repercusion_id": actor})                           # incoherente a proposito
    r = c.post(cli, c.ruta(ct["id"], f"/servicios/{luz}"),
               c.cuerpo_v(ct, modo="REPERCUTIDO_FIJO", inquilino_tercero_id=str(ana), porcentaje="50", desde="2026-03-01"))
    verificar(r, "TRATAMIENTO_INCOMPATIBLE", antes)
    assert nombre in e.MAPA_FISICO and e.MAPA_FISICO[nombre][1] == "TRATAMIENTO_INCOMPATIBLE"


def test_check_rol_de_participante_fuera_de_catalogo(t, monkeypatch):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    monkeypatch.setattr(modelos, "ROLES", modelos.ROLES + ("FIADOR",))        # rol inventado: salta la validacion
    persona = modelos.Persona(rol="FIADOR", tercero_id=luis, desde=dt.date(2026, 9, 1))
    salida = en_unidad(owner, lambda s: serv.anadir_persona(
        s, contrato_id=uuid.UUID(ct["id"]), intencion_id=uuid.uuid4(), row_version=ct["row_version"], persona=persona,
        desde=dt.date(2026, 9, 1)))
    assert getattr(salida, "codigo", None) == "ROL_DESCONOCIDO" and c.huella() == antes
    assert e.rechazo_http("ROL_DESCONOCIDO")[0] == 422


def test_check_rol_de_tercero_agencia_no_es_rol_de_tercero(t, monkeypatch):
    owner, cli, pid, ana = t
    antes = c.huella()
    monkeypatch.setattr(modelos, "ROLES_TERCERO", modelos.ROLES_TERCERO + ("AGENCIA",))
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (ana,))
    r = c.post(cli, f"/v1/terceros/{ana}/roles", {"intencion_id": str(uuid.uuid4()), "row_version_esperada": ver,
                                                     "anadir": ["AGENCIA"]})
    verificar(r, "ROL_DESCONOCIDO", antes)


@pytest.mark.parametrize("fila", [
    {"tipo_revision": "PORCENTAJE_FIJO", "porcentaje_fijo": None, "periodicidad_meses": None},
    {"tipo_revision": "NINGUNA", "porcentaje_fijo": None, "periodicidad_meses": 12},
])
def test_check_clausula_incompleta(t, monkeypatch, fila):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    monkeypatch.setattr(modelos, "validar_clausula", lambda cl: {
        "indice_referencia": None, "fecha_primera_revision": None, "notas": None, **fila})
    r = c.post(cli, c.ruta(ct["id"], "/clausula"), c.cuerpo_v(ct, desde="2026-09-01", clausula={"tipo": "IPC"}))
    verificar(r, "CLAUSULA_INCOMPLETA", antes)


def test_check_fechas_del_contrato(t, monkeypatch):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-09-01")
    antes = c.huella()
    monkeypatch.setattr(serv, "_fin_previsto_anterior_al_inicio", _falso)
    r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_fin_prevista="2026-08-01", motivo="Error"))
    verificar(r, "FECHA_ANTERIOR_INICIO", antes)
    # el fin REAL anterior al inicio: por el repositorio (las vigencias se cierran con el mismo CHECK de vigencia,
    # que esta fuera del mapa y por eso el camino HTTP de la terminacion no llega al CHECK de contratos)
    def fin_real(sesion):
        return base_mod.ejecutar_escritura(sesion, lambda: repo.actualizar_contrato(
            sesion, uuid.UUID(ct["id"]), {"fecha_fin_real": dt.date(2026, 8, 1)}))

    rechazo = en_unidad(owner, fin_real)
    assert rechazo is not None and rechazo.codigo == "FECHA_ANTERIOR_INICIO" and c.huella() == antes


# ================================================================== UNIQUE parcial y trigger aciclico
def test_unique_nombre_de_clasificacion_entre_hermanos_activos(t, monkeypatch):
    owner, cli, _, _ = t
    raiz = c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Raiz"}).json()["clasificacion"]
    c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Hija", "parent_id": raiz["id"]})
    antes = c.huella()
    monkeypatch.setattr(ter, "_hermano_repetido", _falso)
    r = c.post(cli, "/v1/clasificaciones-tercero", {"intencion_id": str(uuid.uuid4()), "nombre": "Hija", "parent_id": raiz["id"]})
    verificar(r, "CLASIFICACION_NOMBRE_REPETIDO", antes)


def test_trigger_aciclico_se_traduce_por_la_firma_de_la_funcion(t, monkeypatch):
    """C-31 CERRADO (decision de Moises del 19-11; contrato v1.2 §1.5, bbceffda…): P0001 de gapto.fn_check_jerarquia_aciclica(), trigger DIFERIDO forzado a IMMEDIATE
    dentro del savepoint; se identifica por la firma en `diag.context`, no por el texto localizable."""
    owner, cli, _, _ = t
    mk = lambda n, p=None: c.post(cli, "/v1/clasificaciones-tercero", {          # noqa: E731
        "intencion_id": str(uuid.uuid4()), "nombre": n, **({"parent_id": p} if p else {})}).json()["clasificacion"]
    raiz = mk("Raiz")
    nieta = mk("Nieta", mk("Hija", raiz["id"])["id"])
    antes = c.huella()
    monkeypatch.setattr(ter, "_es_descendiente", _falso)
    r = c.post(cli, f"/v1/clasificaciones-tercero/{raiz['id']}/mover",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": raiz["row_version"], "parent_id": nieta["id"]})
    verificar(r, "CLASIFICACION_CICLO", antes)


# ================================================================== lo que ninguna constraint garantiza
def test_principal_ausente_el_mutante_deja_la_fila_indebida_en_la_base(t, monkeypatch):
    """No hay SQLSTATE: con la validacion del servicio omitida, la prueba detecta el ESTADO indebido (inquilino sin
    principal). Control: sin el mutante, PRINCIPAL_REQUERIDO."""
    owner, cli, pid, ana = t
    sin_principal = [c.yo("PROPIETARIO", True), c.de(ana, "INQUILINO", False)]
    antes = c.huella()
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=1, personas=sin_principal), 422, "PRINCIPAL_REQUERIDO", antes)
    monkeypatch.setattr(modelos, "validar_principales", _sin)
    r = c.alta(cli, pid, habitacion=2, personas=sin_principal)
    assert r.status_code == 200                                                # nadie mas lo impide: solo el servicio
    cid = r.json()["contrato_id"]
    assert c.uno(owner, "SELECT count(*) FROM gapto.contrato_participantes WHERE contrato_entidad_id = %s "
                        "AND rol = 'INQUILINO' AND NOT principal", (cid,)) == 1   # la fila indebida: lo detecta la prueba


def test_yo_inquilino_agencia_el_mutante_deja_la_fila_indebida(t, monkeypatch):
    owner, cli, pid, ana = t
    monkeypatch.setattr(modelos, "validar_yo", _sin)
    r = c.alta(cli, pid, habitacion=1, personas=[c.yo("PROPIETARIO", True), c.de(ana, "INQUILINO", True), c.yo("ADMINISTRADOR")])
    if r.status_code == 200:       # con `0355`: nada fisico lo impide; sin `0355` el CHECK de rol responde ROL_DESCONOCIDO
        assert c.uno(owner, "SELECT count(*) FROM gapto.contrato_participantes p JOIN gapto.actores_financieros a "
                            "ON a.id = p.actor_id WHERE a.tercero_id IS NULL AND p.rol = 'ADMINISTRADOR'") == 1
    else:
        c.rechazo(r, 422, "ROL_DESCONOCIDO")


# ================================================================== politica de exclusion (AJ-COMP-04)
def test_constraint_fuera_del_mapa_no_se_traduce_y_sale_como_error_generico(t, monkeypatch):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()

    def rompe_inicio(sesion, contrato_id, cambios):          # viola ck_contratos__formalizado_exige_inicio (NO esta en el mapa)
        sesion.ejecutar("UPDATE gapto.contratos SET fecha_inicio = NULL WHERE entidad_id = %s", (contrato_id,))

    monkeypatch.setattr(repo, "actualizar_contrato", rompe_inicio)
    r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, nombre="Otro nombre"))
    assert r.status_code == 500 and r.json()["codigo"] not in e.RECHAZOS, r.text    # sin codigo de dominio ficticio
    assert c.huella() == antes


def test_traducir_fisico_devuelve_none_para_lo_que_no_esta_en_el_mapa_con_la_base_real(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)

    def fuera_del_mapa(sesion):
        with pytest.raises(psycopg.errors.CheckViolation):
            base_mod.ejecutar_escritura(sesion, lambda: sesion.ejecutar(
                "UPDATE gapto.contratos SET fecha_inicio = NULL WHERE entidad_id = %s", (uuid.UUID(ct["id"]),)))
        return "propagado"

    assert en_unidad(owner, fuera_del_mapa) == "propagado"
