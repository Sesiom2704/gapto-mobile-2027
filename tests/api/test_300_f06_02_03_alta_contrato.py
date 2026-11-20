# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_300_f06_02_03_alta_contrato.py
# Ruta: tests/api/test_300_f06_02_03_alta_contrato.py
# Descripcion: F06-02/03 · C-CON-01 alta de contrato SIN RENTA (contrato v1.1 §I; D25; decisiones 1-7). Por HTTP,
#   como gapto_runtime con RLS. Oraculos: O-8 (borrador sin fecha), O-9 (HABITACIONES_EN_USO con B1), O-14 (renta
#   fuera: RENTA_NO_DISPONIBLE, 0 filas), O-22 (YO no es inquilino/agencia/administrador), O-23 (AGENCIA y
#   ADMINISTRADOR no formalizan), O-24 (principal por rol), INV-ALQ-09 (el borrador no ocupa) y la idempotencia.
#   Todo rechazo deja la HUELLA del estado identica. Orden de validaciones (§I): propiedad -> renta -> inicio ->
#   habitacion -> fechas -> personas -> solape.
#   ESCRITO SIN EJECUTAR (sin base esta noche): se ejecuta cuando haya GAPTO_TEST_DATABASE_URL, tras la 0355.
# Version: 0.1.2 (F06 T3-F06 Bloque 3, B3-COMP, decision 11 de Moises): O-30 en el servidor con la MISMA alta (misma
#   intencion y mismo cuerpo): inactivo -> TERCERO_NO_DISPONIBLE sin cambios; reactivado por F05 -> 200. Discriminante
#   M-CON-42a (la validacion de participantes ignora `enabled`).
# Version: 0.1.1 (F06 T3-F06 Bloque 3, pasos 3-4 con base): fixture: la salida del patrimonio exige motivo_salida (ck_propiedades__salida_exige_motivo).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f06_01_b1_helpers as b
import f06_02_03_helpers as c
import vs01_api_helpers as h

ALTA = "/v1/intenciones/contrato-alquiler"


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    return owner, actor, cli


# ================================================================== felices
def test_alta_habitacion_firmada_con_personas_y_sin_renta(t):
    owner, actor, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana Pérez")
    cid = uuid.uuid4()
    r = c.alta(cli, pid, intencion_id=cid, habitacion=2, personas=c.partes(ana), nombre="26-HAB2-AP",
               fecha_fin_prevista="2027-08-31", notas="Contrato de prueba")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["contrato_id"] == str(cid) and cuerpo["row_version"] == 1 and cuerpo["idempotente"] is False
    ct = cuerpo["contrato"]
    assert (ct["tipo"], ct["habitacion"], ct["estado_documental"], ct["situacion"]) == \
        ("HABITACION", 2, "FORMALIZADO", "VIGENTE")
    assert ct["fecha_inicio"] == "2026-09-01" and ct["fecha_fin_prevista"] == "2027-08-31" and ct["notas"]
    roles = sorted((p["rol"], p["principal"], p["vigente_desde"], p["vigente_hasta"]) for p in ct["personas"])
    assert roles == [("INQUILINO", True, "2026-09-01", None), ("PROPIETARIO", True, "2026-09-01", None)]
    assert ct["terminable"] == {"terminable": True, "motivo": None}
    # INV-ALQ-02 / O-14: el contrato no lleva renta y ninguna tabla de reglas, previsiones o hechos se toca
    assert c.uno(owner, "SELECT regla_renta_id IS NULL FROM gapto.contratos WHERE entidad_id = %s", (cid,)) is True
    assert c.filas_renta(owner) == 0
    # una entidad CONTRATO enabled, un actor por tercero, auditoria CREAR de la raiz con la intencion sellada
    assert c.uno(owner, "SELECT tipo_entidad || ':' || enabled FROM gapto.entidades WHERE id = %s", (cid,)) == "CONTRATO:true"
    assert c.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s "
                        "AND accion = 'CREAR'", (cid,)) == 1
    assert c.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (ana,)) == 1


def test_alta_vivienda_completa_y_otro(t):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    viv = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-01-01",
                          nombre="26-VIV-AN")
    assert viv["tipo"] == "VIVIENDA_COMPLETA" and viv["habitacion"] is None
    assert c.uno(owner, "SELECT tipo_contrato FROM gapto.contratos WHERE entidad_id = %s", (viv["id"],)) == "ALQUILER_VIVIENDA"
    # OTRO no solapa con nada (D25 solo habla de habitacion <-> vivienda): se firma aunque haya vivienda completa
    otro = c.crear_firmado(cli, pid, ana, tipo="OTRO", habitacion=None, inicio="2026-03-01", nombre="26-OTRO-AN")
    assert otro["tipo"] == "OTRO" and otro["estado_documental"] == "FORMALIZADO"


def test_borrador_sin_personas_y_sin_renta_no_ocupa(t):
    owner, _, cli = t
    pid = c.propiedad(cli)
    bor = c.crear(cli, pid, estado="BORRADOR", habitacion=1)
    assert bor["estado_documental"] == "BORRADOR" and bor["situacion"] == "BORRADOR" and bor["personas"] == []
    ocupacion = c.get(cli, f"/v1/propiedades/{pid}/contratos").json()["ocupacion"]
    assert {o["estado"] for o in ocupacion} == {"LIBRE"}                       # INV-ALQ-09: un borrador no ocupa
    assert c.filas_renta(owner) == 0


def test_alta_con_tercero_nuevo_agencia_no_escribe_roles_de_tercero(t):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    nid = uuid.uuid4()
    pers = c.partes(ana) + [c.nuevo("Inmobiliaria Sol SL", "AGENCIA", id_=nid)]
    antes_roles = c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles")
    ct = c.crear(cli, pid, personas=pers, habitacion=1)
    # el writer de F05 creo el tercero (id del cliente) y su actor; AGENCIA no es rol de tercero (decision 2 = A)
    assert c.uno(owner, "SELECT nombre FROM gapto.terceros WHERE id = %s", (nid,)) == "Inmobiliaria Sol SL"
    assert c.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (nid,)) == 1
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles") == antes_roles
    assert [p["rol"] for p in ct["personas"]].count("AGENCIA") == 1
    # el rol AGENCIA no cuenta como arrendador: sin la agencia el contrato sigue siendo valido
    assert c.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'terceros' AND registro_id = %s", (nid,)) == 1


def test_gestor_puede_ser_yo_o_un_tercero(t):
    _, _, cli = t
    pid, ana, socio = c.propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Socio")
    pers = [c.de(socio, "GESTOR", True), c.de(ana, "INQUILINO", True)]
    assert c.crear(cli, pid, personas=pers, habitacion=1)["estado_documental"] == "FORMALIZADO"
    yo_gestor = [c.yo("GESTOR", True), c.de(ana, "INQUILINO", True)]
    assert c.crear(cli, pid, personas=yo_gestor, habitacion=2)["estado_documental"] == "FORMALIZADO"


# ================================================================== idempotencia y identidad
def test_replay_identico_es_idempotente_y_el_divergente_no_escribe(t):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    i = uuid.uuid4()
    cuerpo = c.alta_cuerpo(pid, intencion_id=i, personas=c.partes(ana))
    r1 = c.post(cli, ALTA, cuerpo)
    assert r1.status_code == 200 and r1.json()["idempotente"] is False
    antes = c.huella()
    r2 = c.post(cli, ALTA, cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True and r2.json()["contrato_id"] == str(i)
    assert c.huella() == antes                                              # sin filas nuevas
    diverge = {**cuerpo, "nombre": "otro nombre"}
    c.rechazo_sin_cambios(cli, c.post(cli, ALTA, diverge), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", antes)
    # el UUID de una entidad que ya existe (la propiedad) tampoco se reutiliza
    otro = c.alta_cuerpo(pid, intencion_id=pid, personas=c.partes(ana))
    c.rechazo_sin_cambios(cli, c.post(cli, ALTA, otro), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", antes)
    # reordenar las personas es el mismo contenido canonico
    invertido = {**cuerpo, "personas": list(reversed(cuerpo["personas"]))}
    assert c.post(cli, ALTA, invertido).json()["idempotente"] is True


def test_propiedad_ajena_o_inexistente_es_404_sin_eco(t):
    owner, _, cli = t
    pid = c.propiedad(cli)
    otro_owner, _, cli2 = c.entorno()
    ajena = c.propiedad(cli2)
    antes = c.huella()
    for p in (ajena, uuid.uuid4()):
        c.rechazo_sin_cambios(cli, c.alta(cli, p, habitacion=1), 404, "AGREGADO_NO_ENCONTRADO", antes)
    assert c.huella() == antes and pid


def test_propiedad_fuera_del_patrimonio_antes_del_inicio(t):
    owner, _, cli = t
    pid = c.propiedad(cli)
    h.como_owner(owner, "UPDATE gapto.propiedades SET fecha_salida_patrimonio = '2026-06-30', motivo_salida = 'VENTA' WHERE entidad_id = %s",
                 (pid,))
    antes = c.huella()
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, inicio="2026-09-01"), 422, "PROPIEDAD_FUERA_DE_PATRIMONIO", antes)
    assert c.alta(cli, pid, inicio="2026-06-30", estado="BORRADOR").status_code == 200   # salida >= inicio: admitida


# ================================================================== renta fuera (R-E-01; O-14)
@pytest.mark.parametrize("campo", ["renta", "fianza"])
def test_renta_o_fianza_son_renta_no_disponible_con_cero_filas(t, campo):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    antes = c.huella()
    r = c.alta(cli, pid, personas=c.partes(ana), **{campo: {"importe": "600.00"}})
    c.rechazo_sin_cambios(cli, r, 422, "RENTA_NO_DISPONIBLE", antes)
    assert c.uno(owner, "SELECT count(*) FROM gapto.contratos") == 0 and c.filas_renta(owner) == 0


def test_la_propiedad_se_valida_antes_que_la_renta(t):
    """El orden de §I fija el codigo: propiedad inexistente + renta -> 404 (sin eco), no RENTA_NO_DISPONIBLE."""
    _, _, cli = t
    r = c.alta(cli, uuid.uuid4(), renta={"importe": "1"})
    c.rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


# ================================================================== tipo, habitacion y fechas
def test_borrador_sin_fecha_de_inicio_es_fecha_inicio_requerida(t):          # O-8
    _, _, cli = t
    pid = c.propiedad(cli)
    antes = c.huella()
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, estado="BORRADOR", inicio=None), 422, "FECHA_INICIO_REQUERIDA", antes)


def test_habitacion_reglas_por_tipo_y_contra_la_ficha(t):
    owner, _, cli = t
    pid = c.propiedad(cli, habitaciones=3)
    antes = c.huella()
    casos = [
        (dict(tipo="HABITACION", habitacion=None), "HABITACION_REQUERIDA"),
        (dict(tipo="VIVIENDA_COMPLETA", habitacion=2), "HABITACION_NO_ADMITIDA"),
        (dict(tipo="OTRO", habitacion=1), "HABITACION_NO_ADMITIDA"),
        (dict(tipo="HABITACION", habitacion=4), "HABITACION_FUERA_DE_FICHA"),
        (dict(tipo="HABITACION", habitacion=0), "HABITACION_NO_ADMITIDA"),
    ]
    for kw, codigo in casos:
        c.rechazo_sin_cambios(cli, c.alta(cli, pid, estado="BORRADOR", **kw), 422, codigo, antes)
    # ficha con habitaciones NULL o 0: no se inventan (D-A-11)
    sin_dato, cero = c.propiedad(cli, habitaciones=None, nombre="Sin dato"), c.propiedad(cli, habitaciones=0, nombre="Cero")
    antes = c.huella()
    for p in (sin_dato, cero):
        c.rechazo_sin_cambios(cli, c.alta(cli, p, estado="BORRADOR", habitacion=1), 422, "HABITACIONES_NO_INDICADAS", antes)
    # la habitacion se guarda como etiqueta ordinal (Q-CON-03 A): dos borradores en la misma habitacion conviven
    assert c.alta(cli, pid, estado="BORRADOR", habitacion=3).status_code == 200
    assert c.alta(cli, pid, estado="BORRADOR", habitacion=3).status_code == 200


def test_fin_previsto_anterior_al_inicio(t):
    _, _, cli = t
    pid = c.propiedad(cli)
    antes = c.huella()
    r = c.alta(cli, pid, estado="BORRADOR", inicio="2026-09-01", fecha_fin_prevista="2026-08-31")
    c.rechazo_sin_cambios(cli, r, 422, "FECHA_ANTERIOR_INICIO", antes)


# ================================================================== personas (D25; O-22, O-23, O-24)
def test_o_22_yo_no_es_inquilino_ni_agencia_ni_administrador(t):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    antes = c.huella()
    base = [c.yo("PROPIETARIO", True)]
    casos = [([c.yo("INQUILINO", True)] + base, "INQUILINO_NO_PUEDE_SER_YO"),
             (base + [c.de(ana, "INQUILINO", True), c.yo("AGENCIA")], "ROL_NO_ADMITIDO_PARA_YO"),
             (base + [c.de(ana, "INQUILINO", True), c.yo("ADMINISTRADOR")], "ROL_NO_ADMITIDO_PARA_YO")]
    for pers, codigo in casos:
        c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=pers), 422, codigo, antes)
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles") == 0      # 0 escrituras en tercero_roles
    mensaje = c.alta(cli, pid, personas=casos[0][0]).json()["mensaje"]
    assert mensaje == "Tú no puedes ser inquilino de tu propio contrato."


def test_o_23_agencia_y_administrador_no_formalizan(t):
    _, _, cli = t
    pid, ana, ag = c.propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Inmo SL", "EMPRESA")
    antes = c.huella()
    sin_arrendador = [c.de(ana, "INQUILINO", True), c.de(ag, "AGENCIA")]
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=sin_arrendador), 422, "FALTAN_PARTES_PARA_FORMALIZAR", antes)
    sin_inquilino = [c.yo("PROPIETARIO", True), c.de(ag, "ADMINISTRADOR")]
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=sin_inquilino), 422, "FALTAN_PARTES_PARA_FORMALIZAR", antes)
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=[]), 422, "FALTAN_PARTES_PARA_FORMALIZAR", antes)
    ok = c.alta(cli, pid, personas=c.partes(ana) + [c.de(ag, "AGENCIA")])
    assert ok.status_code == 200, ok.text


def test_o_24_principal_por_rol(t):
    owner, _, cli = t
    pid, ana, av, ag1, ag2 = (c.propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Aval"),
                              c.tercero(cli, "Agencia 1", "EMPRESA"), c.tercero(cli, "Agencia 2", "EMPRESA"))
    base = c.partes(ana)
    # AVALISTA, AGENCIA y ADMINISTRADOR sin principal: OK
    ok = c.alta(cli, pid, habitacion=1, personas=base + [c.de(av, "AVALISTA"), c.de(ag1, "AGENCIA"),
                                                        c.de(ag2, "ADMINISTRADOR")])
    assert ok.status_code == 200, ok.text
    antes = c.huella()
    # INQUILINO sin principal -> PRINCIPAL_REQUERIDO (tambien PROPIETARIO y GESTOR)
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=2, personas=[c.yo("PROPIETARIO", True), c.de(ana, "INQUILINO")]),
                          422, "PRINCIPAL_REQUERIDO", antes)
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=2, personas=[c.yo("PROPIETARIO"), c.de(ana, "INQUILINO", True)]),
                          422, "PRINCIPAL_REQUERIDO", antes)
    # dos principales en AGENCIA: validacion previa y, de fondo, la EXCLUDE (O-15 lo prueba por el camino fisico)
    dos = base + [c.de(ag1, "AGENCIA", True), c.de(ag2, "AGENCIA", True)]
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=2, personas=dos), 422, "PRINCIPAL_DUPLICADO", antes)


def test_tercero_ajeno_inexistente_o_inactivo_es_tercero_no_disponible(t):
    owner, _, cli = t
    pid, ana, baja = c.propiedad(cli), c.tercero(cli, "Ana"), c.tercero(cli, "Baja")
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (baja,))
    assert c.post(cli, f"/v1/terceros/{baja}/desactivar", {"row_version": ver}).status_code == 200
    _, _, cli2 = c.entorno()
    ajeno = c.tercero(cli2, "De otro owner")
    antes = c.huella()
    for tid in (baja, ajeno, uuid.uuid4()):                                    # O-30: inactivo -> no disponible
        pers = [c.yo("PROPIETARIO", True), c.de(tid, "INQUILINO", True)]
        c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=pers), 409, "TERCERO_NO_DISPONIBLE", antes)
    # reactivado por F05, vuelve a ser elegible
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (baja,))
    assert c.post(cli, f"/v1/terceros/{baja}/reactivar", {"row_version": ver}).status_code == 200
    assert c.alta(cli, pid, personas=c.partes(baja)).status_code == 200


def test_o_30_la_misma_alta_con_tercero_inactivo_sale_tras_reactivarlo_por_f05(t):
    """O-30 (B3-COMP): la MISMA peticion (misma intencion_id, mismo cuerpo) con un inquilino inactivo se rechaza con
    TERCERO_NO_DISPONIBLE y estado identico; reactivado por POST /v1/terceros/{id}/reactivar (writer de F05), la misma
    peticion sale 200 y el contrato lleva a ese tercero como inquilino."""
    owner, _, cli = t
    pid, ines = c.propiedad(cli), c.tercero(cli, "Inés")
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (ines,))
    assert c.post(cli, f"/v1/terceros/{ines}/desactivar", {"row_version": ver}).status_code == 200
    cid = uuid.uuid4()
    peticion = dict(intencion_id=cid, habitacion=1, personas=c.partes(ines), nombre="26-HAB1-IN")
    antes = c.huella()
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, **peticion), 409, "TERCERO_NO_DISPONIBLE", antes)
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (ines,))
    assert c.post(cli, f"/v1/terceros/{ines}/reactivar", {"row_version": ver}).status_code == 200
    r = c.alta(cli, pid, **peticion)
    assert r.status_code == 200, r.text
    assert r.json()["contrato_id"] == str(cid) and r.json()["idempotente"] is False
    assert c.uno(owner, "SELECT count(*) FROM gapto.contrato_participantes cp JOIN gapto.actores_financieros a "
                        "ON a.id = cp.actor_id WHERE cp.contrato_entidad_id = %s AND a.tercero_id = %s "
                        "AND cp.rol = 'INQUILINO'", (cid, ines)) == 1


def test_actor_repetido_en_el_mismo_rol(t):
    _, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    antes = c.huella()
    pers = [c.yo("PROPIETARIO", True), c.de(ana, "INQUILINO", True), c.de(ana, "INQUILINO")]
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, personas=pers), 422, "PARTICIPANTE_DUPLICADO", antes)


def test_nuevo_tercero_repetido_en_otra_alta_no_se_reutiliza(t):
    _, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    nid = uuid.uuid4()
    pers = c.partes(ana) + [c.nuevo("Gestoría Uno", "ADMINISTRADOR", id_=nid)]
    assert c.alta(cli, pid, habitacion=1, personas=pers).status_code == 200
    antes = c.huella()
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=2, personas=pers), 409,
                          "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", antes)


# ================================================================== B1 (reverso: HABITACIONES_EN_USO; O-9)
def test_o_9_habitaciones_en_uso_y_contrato_cancelado(t):
    owner, _, cli = t
    pid = c.propiedad(cli, habitaciones=3)
    bor = c.crear(cli, pid, estado="BORRADOR", habitacion=3)
    p = b.leer(cli, pid)
    r = c.post(cli, f"/v1/propiedades/{pid}/editar", {"intencion_id": str(uuid.uuid4()),
                                                      "row_version_esperada": p["row_version"], "habitaciones": 2})
    c.rechazo(r, 409, "HABITACIONES_EN_USO")
    assert r.json()["detalle"]["contratos"] == [bor["id"]]
    cancelado = c.post(cli, c.ruta(bor["id"], "/cancelar"), c.cuerpo_v(bor, motivo="Ya no se alquila"))
    assert cancelado.status_code == 200, cancelado.text
    r = c.post(cli, f"/v1/propiedades/{pid}/editar", {"intencion_id": str(uuid.uuid4()),
                                                      "row_version_esperada": p["row_version"], "habitaciones": 2})
    assert r.status_code == 200, r.text                    # con el contrato 3 CANCELADO se acepta


# ================================================================== aislamiento y formas
def test_aislamiento_por_owner_con_rls(t):
    owner, _, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    _, _, cli2 = c.entorno()
    assert c.get(cli2, c.ruta(ct["id"])).status_code == 404                  # INV-ALQ-14: 404 sin eco
    r = c.post(cli2, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-12-01"))
    c.rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


def test_cuerpo_invalido_es_422_entrada_invalida(t):
    _, _, cli = t
    pid = c.propiedad(cli)
    for mal in ({"estado": "ACTIVO"}, {"tipo": "OTRA_COSA"}, {"nombre": " "}, {"campo_inventado": 1}):
        r = c.post(cli, ALTA, {**c.alta_cuerpo(pid, estado="BORRADOR"), **mal})
        assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", (mal, r.text)
