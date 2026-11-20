# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_301_f06_02_03_editar_terminar_formalizar.py
# Ruta: tests/api/test_301_f06_02_03_editar_terminar_formalizar.py
# Descripcion: F06-02/03 · C-CON-02 editar y prorrogar, C-CON-03 terminar y corregir la terminacion, C-CON-04
#   formalizar o cancelar, y el SOLAPE BLOQUEANTE entre firmados (decision 3 = A; INV-ALQ-08; D25 simetrico).
#   Oraculos: O-2 (el fin previsto NO libera la habitacion), O-5 (prorroga con motivo; correccion sin reabrir
#   vigencias), O-12 (terminar con `regla_renta_id` -> 409 RENTA_PENDIENTE_DE_F06_04 con estado identico), O-14,
#   O-25 (solape habitacion <-> vivienda en los DOS sentidos; borrador y OTRO no solapan) y O-28 (negativos
#   temporales: inicio que solapa, vigencia invertida, fin anterior a una vigencia abierta; huella antes = despues).
#   Hoy = 2026-11-18. ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.1.2 (F06 T3-F06 Bloque 3, paso 6): test_o_28_mover_el_inicio_detras_de_una_vigencia_ya_cerrada (mata M-CON-39e).
# Version: 0.1.1 (F06 T3-F06 Bloque 3, pasos 3-4 con base): la huella de antes se toma despues de crear terceros o contratos auxiliares (solo mide el rechazo); O-2 con la forma de ocupacion del cliente (desde/hasta).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f06_02_03_helpers as c


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    return owner, cli, pid, ana


# ================================================================== O-2 el fin previsto no libera
def test_o_2_fin_previsto_vencido_no_libera_la_habitacion(t):
    owner, cli, pid, ana = t
    viejo = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2025-01-01", fecha_fin_prevista="2026-06-30",
                            nombre="25-HAB1-AN")
    assert viejo["fin_previsto_vencido"] is True and viejo["situacion"] == "VIGENTE"
    ocupacion = c.get(cli, f"/v1/propiedades/{pid}/contratos").json()["ocupacion"]
    # forma alineada con el cliente (OcupacionHabitacion: desde/hasta para el texto de la habitacion)
    assert ocupacion[0] == {"habitacion": 1, "estado": "OCUPADA", "contrato_id": viejo["id"], "desde": "2025-01-01",
                            "hasta": "2026-06-30"}
    luis = c.tercero(cli, "Luis")
    antes = c.huella()  # despues de crear el tercero: solo se mide el rechazo
    # un nuevo FORMALIZADO posterior al fin previsto sigue chocando: solo el fin REAL libera
    r = c.alta(cli, pid, habitacion=1, inicio="2026-09-01", personas=c.partes(luis), nombre="26-HAB1-LU")
    cuerpo = c.rechazo(r, 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert [x["id"] for x in cuerpo["detalle"]["solapados"]] == [viejo["id"]]
    assert c.huella() == antes                                                  # 0 filas
    # el mismo como BORRADOR se acepta; formalizarlo -> 409 hasta registrar el fin real del otro
    bor = c.crear(cli, pid, habitacion=1, inicio="2026-09-01", estado="BORRADOR", nombre="26-HAB1-LU",
                  personas=c.partes(luis))
    r = c.post(cli, c.ruta(bor["id"], "/formalizar"), c.cuerpo_v(bor))
    c.rechazo(r, 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert c.leer(cli, bor["id"])["estado_documental"] == "BORRADOR"            # sigue siendo borrador
    viejo = c.leer(cli, viejo["id"])
    ok = c.post(cli, c.ruta(viejo["id"], "/terminar"), c.cuerpo_v(viejo, fecha_fin_real="2026-08-31"))
    assert ok.status_code == 200, ok.text
    bor = c.leer(cli, bor["id"])
    assert c.post(cli, c.ruta(bor["id"], "/formalizar"), c.cuerpo_v(bor)).status_code == 200


def test_el_borrador_existente_no_cuenta_para_el_solape(t):
    _, cli, pid, ana = t
    c.crear(cli, pid, habitacion=1, estado="BORRADOR")
    assert c.alta(cli, pid, habitacion=1, personas=c.partes(ana)).status_code == 200


# ================================================================== O-25 solape simetrico y bloqueante
def test_o_25_vivienda_primero_y_despues_habitacion(t):
    owner, cli, pid, ana = t
    viv = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-09-01",
                          fecha_fin_prevista="2027-08-31", nombre="26-VIV-AN")
    luis = c.tercero(cli, "Luis")
    antes = c.huella()  # despues de crear el tercero: solo se mide el rechazo
    r = c.alta(cli, pid, habitacion=2, inicio="2026-11-01", personas=c.partes(luis))
    cuerpo = c.rechazo(r, 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert [(x["id"], x["tipo"]) for x in cuerpo["detalle"]["solapados"]] == [(viv["id"], "VIVIENDA_COMPLETA")]
    assert c.huella() == antes
    assert c.alta(cli, pid, habitacion=2, inicio="2026-11-01", estado="BORRADOR").status_code == 200   # como borrador, OK
    otro = c.alta(cli, pid, tipo="OTRO", habitacion=None, inicio="2026-11-01", personas=c.partes(luis))
    assert otro.status_code == 200, otro.text                                    # OTRO no solapa con nada


def test_o_25_habitacion_primero_y_despues_vivienda(t):
    _, cli, pid, ana = t
    hab = c.crear_firmado(cli, pid, ana, habitacion=3, inicio="2026-10-01", nombre="26-HAB3-AN")
    luis = c.tercero(cli, "Luis")
    r = c.alta(cli, pid, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-11-01", personas=c.partes(luis))
    cuerpo = c.rechazo(r, 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert [x["id"] for x in cuerpo["detalle"]["solapados"]] == [hab["id"]]
    # otra habitacion no solapa con la habitacion 3
    assert c.alta(cli, pid, habitacion=4, inicio="2026-11-01", personas=c.partes(luis)).status_code == 200


def test_ocupacion_hasta_el_fin_real_inclusive(t):
    _, cli, pid, ana = t
    a = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    assert c.post(cli, c.ruta(a["id"], "/terminar"), c.cuerpo_v(a, fecha_fin_real="2026-06-30")).status_code == 200
    luis = c.tercero(cli, "Luis")
    # el mismo dia del fin real coincide (intervalo inclusivo); el dia siguiente, no
    c.rechazo(c.alta(cli, pid, habitacion=1, inicio="2026-06-30", personas=c.partes(luis)), 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert c.alta(cli, pid, habitacion=1, inicio="2026-07-01", personas=c.partes(luis)).status_code == 200


# ================================================================== C-CON-02 editar y prorrogar (O-5)
def test_prorroga_con_motivo_y_correccion_libre_de_nombre_y_notas(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, fecha_fin_prevista="2027-08-31")
    antes = c.huella()
    sin_motivo = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_fin_prevista="2028-08-31"))
    c.rechazo_sin_cambios(cli, sin_motivo, 422, "MOTIVO_AUSENTE", antes)
    ok = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_fin_prevista="2028-08-31", motivo="Prorroga acordada"))
    assert ok.status_code == 200 and ok.json()["contrato"]["fecha_fin_prevista"] == "2028-08-31"
    assert ok.json()["row_version"] == ct["row_version"] + 1
    ct = c.leer(cli, ct["id"])
    ok = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, nombre="  26-HAB1-AN  ", notas="Nota nueva"))
    assert ok.status_code == 200 and ok.json()["contrato"]["nombre"] == "26-HAB1-AN"
    # la prorroga no repite el solape ni toca la ocupacion; queda auditada con el motivo
    assert c.uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s "
                        "AND motivo LIKE '%%Prorroga acordada%%'", (ct["id"],)) == 1
    assert c.filas_renta(owner) == 0


def test_propiedad_y_tipo_son_inmutables_y_un_cancelado_no_se_edita(t):
    _, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    for campo, valor in (("tipo", "OTRO"), ("propiedad_id", str(uuid.uuid4()))):
        r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, **{campo: valor}))
        c.rechazo_sin_cambios(cli, r, 422, "CAMPO_INMUTABLE", antes)
    bor = c.crear(cli, pid, habitacion=2, estado="BORRADOR")
    assert c.post(cli, c.ruta(bor["id"], "/cancelar"), c.cuerpo_v(bor, motivo="No sigue")).status_code == 200
    bor = c.leer(cli, bor["id"])
    antes = c.huella()
    r = c.post(cli, c.ruta(bor["id"], "/editar"), c.cuerpo_v(bor, nombre="x"))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)


def test_version_desfasada_y_replay_de_la_edicion(t):
    _, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    cuerpo = c.cuerpo_v(ct, nombre="Otro nombre")
    assert c.post(cli, c.ruta(ct["id"], "/editar"), cuerpo).status_code == 200
    r = c.post(cli, c.ruta(ct["id"], "/editar"), cuerpo)                         # replay con la version ya superada
    assert r.status_code == 200 and r.json()["idempotente"] is True
    stale = c.cuerpo_v(ct, nombre="Distinto")                                    # misma version vieja, otra intencion
    c.rechazo(c.post(cli, c.ruta(ct["id"], "/editar"), stale), 409, "VERSION_DESFASADA")


# ================================================================== O-28 negativos temporales de la edicion
def test_o_28_cambio_de_inicio_o_habitacion_que_solapa_con_un_firmado(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    a = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01", nombre="A")
    assert c.post(cli, c.ruta(a["id"], "/terminar"), c.cuerpo_v(a, fecha_fin_real="2026-06-30")).status_code == 200
    b2 = c.crear_firmado(cli, pid, luis, habitacion=1, inicio="2026-07-15", nombre="B")
    antes = c.huella()
    # adelantar el inicio de B hasta pisar a A -> 409 (habitacion 1 ocupada por A hasta el 30-jun)
    r = c.post(cli, c.ruta(b2["id"], "/editar"), c.cuerpo_v(b2, fecha_inicio="2026-06-30"))
    c.rechazo_sin_cambios(cli, r, 409, "SOLAPE_CON_CONTRATO_FIRMADO", antes)
    # mover B a la habitacion 2 esta libre; moverlo de vuelta con A encima se prueba creando C en la 2 y moviendo B
    c.crear_firmado(cli, pid, ana, habitacion=2, inicio="2026-07-01", nombre="C")
    antes = c.huella()  # C ya existe: solo se mide el rechazo de mover B
    r = c.post(cli, c.ruta(b2["id"], "/editar"), c.cuerpo_v(b2, habitacion=2))
    c.rechazo_sin_cambios(cli, r, 409, "SOLAPE_CON_CONTRATO_FIRMADO", antes)


def test_o_28_inicio_que_dejaria_una_vigencia_invertida(t):
    _, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    assert c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-03-31")).status_code == 200
    ct = c.leer(cli, ct["id"])
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_inicio="2026-05-01"))   # posterior al fin real
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)


def test_cambio_de_inicio_mueve_las_vigencias_que_empezaban_con_el_contrato(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")
    ok = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_inicio="2026-02-01"))
    assert ok.status_code == 200, ok.text
    assert {p["vigente_desde"] for p in ok.json()["contrato"]["personas"]} == {"2026-02-01"}


# ================================================================== C-CON-03 terminar (y renta, O-12)
def test_terminar_cierra_las_vigencias_abiertas_y_no_las_ya_cerradas(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-01-01")
    # un segundo inquilino que se va el 31-mar (vigencia cerrada antes)
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(luis)}, rol="INQUILINO",
                                                              desde="2026-01-01"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    fila = next(p for p in ct["personas"] if p["rol"] == "INQUILINO" and not p["principal"])
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-03-31"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    r = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-10-31"))
    assert r.status_code == 200, r.text
    fin = r.json()["contrato"]
    assert fin["fecha_fin_real"] == "2026-10-31" and fin["situacion"] == "FINALIZADO" and fin["terminable"]["terminable"] is False
    hasta = sorted((p["rol"], p["principal"], p["vigente_hasta"]) for p in fin["personas"])
    assert ("INQUILINO", False, "2026-03-31") in hasta                          # la cerrada antes no se toca
    assert ("INQUILINO", True, "2026-10-31") in hasta and ("PROPIETARIO", True, "2026-10-31") in hasta
    assert c.filas_renta(owner) == 0                                             # O-14: ni reglas ni previsiones tocadas


def test_terminar_requisitos_estado_y_fechas(t):
    _, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")
    antes = c.huella()
    anterior = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-02-28"))
    c.rechazo_sin_cambios(cli, anterior, 422, "FECHA_FIN_ANTERIOR_A_VIGENCIA", antes)
    bor = c.crear(cli, pid, habitacion=2, estado="BORRADOR")
    antes = c.huella()
    r = c.post(cli, c.ruta(bor["id"], "/terminar"), c.cuerpo_v(bor, fecha_fin_real="2026-11-30"))
    c.rechazo_sin_cambios(cli, r, 409, "CONTRATO_NO_VIGENTE", antes)             # no se termina un borrador
    assert c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-11-30")).status_code == 200
    ct2 = c.leer(cli, ct["id"])
    antes = c.huella()
    r = c.post(cli, c.ruta(ct2["id"], "/terminar"), c.cuerpo_v(ct2, fecha_fin_real="2026-12-31"))
    c.rechazo_sin_cambios(cli, r, 409, "CONTRATO_NO_VIGENTE", antes)             # ya terminado


def test_o_12_terminar_un_contrato_con_regla_renta_es_409_con_estado_identico(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    c.con_regla_renta(owner, ct["id"])                                           # dato migrado de V3 (fixture)
    visto = c.leer(cli, ct["id"])
    assert visto["terminable"] == {"terminable": False, "motivo": "RENTA_PENDIENTE_DE_F06_04"}
    assert visto["marca_renta"] == "Renta registrada · se gestiona en la parte de cobros"
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(visto, fecha_fin_real="2026-11-30"))
    cuerpo = c.rechazo(r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", "RENTA_PENDIENTE_DE_F06_04")
    assert cuerpo["mensaje"].startswith("Este contrato tiene una renta registrada.")
    assert c.huella() == antes
    # lo mismo al corregir la terminacion y al mover su inicio (PC-CON-04); tambien el sucesor
    r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(visto, fecha_inicio="2026-08-01"))
    c.rechazo(r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", "RENTA_PENDIENTE_DE_F06_04")
    assert c.huella() == antes


def test_el_motivo_de_renta_es_lo_primero_tras_el_replay_y_la_version(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    c.con_regla_renta(owner, ct["id"])
    visto = c.leer(cli, ct["id"])
    # con fecha invalida Y renta: gana la renta (se comprueba antes que las fechas)
    r = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(visto, fecha_fin_real="2020-01-01"))
    c.rechazo(r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", "RENTA_PENDIENTE_DE_F06_04")
    # con version vieja gana VERSION_DESFASADA
    r = c.post(cli, c.ruta(ct["id"], "/terminar"), {**c.cuerpo_v(visto, fecha_fin_real="2026-11-30"),
                                                    "row_version_esperada": visto["row_version"] + 5})
    c.rechazo(r, 409, "VERSION_DESFASADA")


# ================================================================== corregir la terminacion
def test_corregir_terminacion_mueve_juntos_fin_y_cierres_sin_reabrir(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-01-01")
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(luis)}, rol="INQUILINO",
                                                              desde="2026-01-01"))
    ct = r.json()["contrato"]
    extra = next(p for p in ct["personas"] if p["rol"] == "INQUILINO" and not p["principal"])
    ct = c.post(cli, c.ruta(ct["id"], f"/personas/{extra['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-03-31")).json()["contrato"]
    ct = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real="2026-10-31")).json()["contrato"]
    antes = c.huella()
    sin_motivo = c.post(cli, c.ruta(ct["id"], "/corregir-terminacion"), c.cuerpo_v(ct, fecha_fin_real="2026-11-15"))
    c.rechazo_sin_cambios(cli, sin_motivo, 422, "MOTIVO_AUSENTE", antes)
    r = c.post(cli, c.ruta(ct["id"], "/corregir-terminacion"),
               c.cuerpo_v(ct, fecha_fin_real="2026-11-15", motivo="Se firmo la salida el 15"))
    assert r.status_code == 200, r.text
    fin = r.json()["contrato"]
    assert fin["fecha_fin_real"] == "2026-11-15"
    hastas = sorted((p["rol"], p["principal"], p["vigente_hasta"]) for p in fin["personas"])
    # los cierres de la terminacion se mueven; el cierre anterior (31-mar) NO se reabre ni se mueve
    assert hastas == [("INQUILINO", False, "2026-03-31"), ("INQUILINO", True, "2026-11-15"),
                      ("PROPIETARIO", True, "2026-11-15")]
    # nunca por debajo del inicio de lo que se mueve
    antes = c.huella()
    r = c.post(cli, c.ruta(fin["id"], "/corregir-terminacion"),
               c.cuerpo_v(fin, fecha_fin_real="2025-12-31", motivo="Error"))
    c.rechazo_sin_cambios(cli, r, 422, "FECHA_FIN_ANTERIOR_A_VIGENCIA", antes)


def test_corregir_terminacion_que_crea_solape_es_409(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    a = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    a = c.post(cli, c.ruta(a["id"], "/terminar"), c.cuerpo_v(a, fecha_fin_real="2026-06-30")).json()["contrato"]
    c.crear_firmado(cli, pid, luis, habitacion=1, inicio="2026-07-15")
    antes = c.huella()
    r = c.post(cli, c.ruta(a["id"], "/corregir-terminacion"), c.cuerpo_v(a, fecha_fin_real="2026-08-31", motivo="Se queda mas"))
    c.rechazo_sin_cambios(cli, r, 409, "SOLAPE_CON_CONTRATO_FIRMADO", antes)


def test_corregir_terminacion_solo_en_un_contrato_terminado(t):
    _, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], "/corregir-terminacion"), c.cuerpo_v(ct, fecha_fin_real="2026-12-01", motivo="x"))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)


# ================================================================== C-CON-04 formalizar y cancelar
def test_formalizar_exige_partes_y_principal_y_cancelar_solo_un_borrador(t):
    owner, cli, pid, ana = t
    bor = c.crear(cli, pid, habitacion=1, estado="BORRADOR")                     # sin personas
    antes = c.huella()
    r = c.post(cli, c.ruta(bor["id"], "/formalizar"), c.cuerpo_v(bor))
    c.rechazo_sin_cambios(cli, r, 422, "FALTAN_PARTES_PARA_FORMALIZAR", antes)
    r = c.post(cli, c.ruta(bor["id"], "/personas"), c.cuerpo_v(bor, actor="YO", rol="PROPIETARIO", principal=True,
                                                               desde="2026-09-01"))
    bor = r.json()["contrato"]
    r = c.post(cli, c.ruta(bor["id"], "/personas"), c.cuerpo_v(bor, actor={"tercero_id": str(ana)}, rol="INQUILINO",
                                                               principal=False, desde="2026-09-01"))
    c.rechazo(r, 422, "PRINCIPAL_REQUERIDO")                                      # D25: el inquilino necesita principal
    r = c.post(cli, c.ruta(bor["id"], "/personas"), c.cuerpo_v(bor, actor={"tercero_id": str(ana)}, rol="INQUILINO",
                                                               principal=True, desde="2026-09-01"))
    bor = r.json()["contrato"]
    ok = c.post(cli, c.ruta(bor["id"], "/formalizar"), c.cuerpo_v(bor))
    assert ok.status_code == 200 and ok.json()["contrato"]["estado_documental"] == "FORMALIZADO"
    firmado = ok.json()["contrato"]
    antes = c.huella()
    r = c.post(cli, c.ruta(firmado["id"], "/cancelar"), c.cuerpo_v(firmado, motivo="x"))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)   # un FORMALIZADO se termina
    r = c.post(cli, c.ruta(firmado["id"], "/formalizar"), c.cuerpo_v(firmado))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)
    otro = c.crear(cli, pid, habitacion=2, estado="BORRADOR")
    sin_motivo = c.post(cli, c.ruta(otro["id"], "/cancelar"), c.cuerpo_v(otro))
    c.rechazo(sin_motivo, 422, "MOTIVO_AUSENTE")
    ok = c.post(cli, c.ruta(otro["id"], "/cancelar"), c.cuerpo_v(otro, motivo="No hay inquilino"))
    assert ok.status_code == 200 and ok.json()["contrato"]["estado_documental"] == "CANCELADO"
    # el registro se conserva (nada se borra)
    assert c.uno(owner, "SELECT count(*) FROM gapto.contratos WHERE entidad_id = %s", (otro["id"],)) == 1


def test_formalizar_con_solape_sigue_siendo_borrador_y_no_cuenta_otro_borrador(t):
    _, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-09-01")
    b1 = c.crear(cli, pid, habitacion=1, estado="BORRADOR", inicio="2026-10-01", personas=c.partes(luis))
    c.rechazo(c.post(cli, c.ruta(b1["id"], "/formalizar"), c.cuerpo_v(b1)), 409, "SOLAPE_CON_CONTRATO_FIRMADO")
    assert c.leer(cli, b1["id"])["estado_documental"] == "BORRADOR"


def test_o_28_mover_el_inicio_detras_de_una_vigencia_ya_cerrada(t):
    """Mata M-CON-39e: una persona que entro el dia del inicio y ya salio no puede quedar con `hasta < desde` al
    retrasar el inicio del contrato: 409 VIGENCIA_INVERTIDA, estado identico."""
    _, cli, pid, ana = t
    av = c.tercero(cli, "Aval")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(av)}, rol="AVALISTA",
                                                              desde="2026-03-01"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    fila = next(p for p in ct["personas"] if p["tercero_id"] == str(av))
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-03-31"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], "/editar"), c.cuerpo_v(ct, fecha_inicio="2026-04-15"))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes, motivo="VIGENCIA_INVERTIDA")
