# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_303_f06_02_03_clausula_y_servicios.py
# Ruta: tests/api/test_303_f06_02_03_clausula_y_servicios.py
# Descripcion: F06-02/03 · C-REV-01 clausula de revision y C-SRV-01..04 servicios (contrato v1.1 Partes II-III; M-9).
#   Oraculos: O-6 (IPC con parametros NULL; NINGUNA frente a «No lo sé»; version nueva que cierra la anterior),
#   O-7 (limpieza INCLUIDO; luz FIJO 50 % al inquilino vigente -> modo_reparto FIJO, 50,0000; POR_FACTURA -> % NULL y
#   «Se reparte en cada factura»; POR_FACTURA con % -> TRATAMIENTO_INCOMPATIBLE; FIJO al avalista ->
#   ACTOR_NO_ES_INQUILINO; FIJO con 0 % -> rechazo del writer; SIN_INDICAR -> fila con vigente_hasta y count(*)
#   igual), O-28 (DESDE_IGUAL_A_VERSION_ABIERTA) y O-31 (baja de servicio con regla: REGLA_SERVICIO_PENDIENTE_DE_F06_04,
#   nunca el motivo de renta). La clausula NUNCA toca la renta; el tratamiento no crea ningun derecho de cobro.
#   ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f06_02_03_helpers as c
import vs01_api_helpers as h


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    return owner, cli, pid, ana


def _clausula(tipo="IPC", **kw) -> dict:
    return {"tipo": tipo, **kw}


# ================================================================== O-6 clausula
def test_o_6_clausula_en_el_alta_ipc_con_parametros_desconocidos(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01", clausula_revision=_clausula("IPC"))
    cl = ct["clausula"]
    assert (cl["tipo_revision"], cl["indice_referencia"], cl["vigente_desde"], cl["vigente_hasta"]) == \
        ("IPC", "IPC INE", "2026-03-01", None)
    assert cl["periodicidad_meses"] is None and cl["fecha_primera_revision"] is None   # desconocidos = NULL
    assert c.filas_renta(owner) == 0                                                    # la clausula nunca toca la renta


def test_o_6_ninguna_frente_a_no_lo_se(t):
    owner, cli, pid, ana = t
    sin = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")              # «No lo sé»: sin fila
    assert sin["clausula"] is None and c.uno(
        owner, "SELECT count(*) FROM gapto.contrato_revision_renta_versiones WHERE contrato_entidad_id = %s", (sin["id"],)) == 0
    ninguna = c.crear_firmado(cli, pid, ana, habitacion=2, inicio="2026-03-01", clausula_revision=_clausula("NINGUNA"))
    assert ninguna["clausula"]["tipo_revision"] == "NINGUNA"                             # fila NINGUNA: distinta de «No lo sé»
    antes = c.huella()
    for extra in ({"periodicidad_meses": 12}, {"porcentaje_fijo": "2"}, {"indice_referencia": "IPC INE"}):
        r = c.alta(cli, pid, habitacion=3, personas=c.partes(ana), clausula_revision=_clausula("NINGUNA", **extra))
        c.rechazo_sin_cambios(cli, r, 422, "CLAUSULA_INCOMPLETA", antes)
    r = c.alta(cli, pid, habitacion=3, personas=c.partes(ana), clausula_revision=_clausula("PORCENTAJE_FIJO"))
    c.rechazo_sin_cambios(cli, r, 422, "CLAUSULA_INCOMPLETA", antes)
    ok = c.alta(cli, pid, habitacion=3, personas=c.partes(ana),
                clausula_revision=_clausula("PORCENTAJE_FIJO", porcentaje_fijo="3.5"))
    assert ok.status_code == 200, ok.text


def test_o_6_version_nueva_cierra_la_anterior_y_nunca_invierte(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01", clausula_revision=_clausula("IPC"))
    antes = c.huella()
    igual = c.post(cli, c.ruta(ct["id"], "/clausula"), c.cuerpo_v(ct, desde="2026-03-01", clausula=_clausula("NINGUNA")))
    c.rechazo_sin_cambios(cli, igual, 422, "DESDE_IGUAL_A_VERSION_ABIERTA", antes)      # es una errata: «corregir»
    anterior = c.post(cli, c.ruta(ct["id"], "/clausula"), c.cuerpo_v(ct, desde="2026-02-01", clausula=_clausula("NINGUNA")))
    c.rechazo_sin_cambios(cli, anterior, 422, "FECHA_ANTERIOR_INICIO", antes)
    r = c.post(cli, c.ruta(ct["id"], "/clausula"), c.cuerpo_v(ct, desde="2027-03-01",
                                                              clausula=_clausula("PORCENTAJE_FIJO", porcentaje_fijo="2")))
    assert r.status_code == 200, r.text
    versiones = r.json()["contrato"]["clausulas"]
    assert [(v["tipo_revision"], v["vigente_desde"], v["vigente_hasta"]) for v in versiones] == \
        [("IPC", "2026-03-01", "2027-02-28"), ("PORCENTAJE_FIJO", "2027-03-01", None)]
    assert c.filas_renta(owner) == 0


def test_corregir_una_clausula_es_una_errata_auditada_con_motivo(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, clausula_revision=_clausula("IPC"))
    version = ct["clausula"]["id"]
    sin_motivo = c.post(cli, c.ruta(ct["id"], f"/clausula/{version}/corregir"), c.cuerpo_v(ct, clausula=_clausula("INDICE")))
    c.rechazo(sin_motivo, 422, "MOTIVO_AUSENTE")
    r = c.post(cli, c.ruta(ct["id"], f"/clausula/{version}/corregir"),
               c.cuerpo_v(ct, clausula=_clausula("INDICE", indice_referencia="IRAV"), motivo="Era otro indice"))
    assert r.status_code == 200 and r.json()["contrato"]["clausula"]["indice_referencia"] == "IRAV"
    assert r.json()["contrato"]["clausula"]["vigente_desde"] == ct["clausula"]["vigente_desde"]  # misma vigencia


# ================================================================== C-SRV-01/02 alta y edicion
def test_servicio_alta_con_propiedad_y_sin_ella_sin_reglas(t):
    owner, cli, pid, _ = t
    sid = c.servicio(cli, pid, tipo="LUZ", nombre="Luz del piso")
    s = c.get(cli, f"/v1/propiedades/{pid}/servicios").json()["servicios"]
    assert [x["nombre"] for x in s] == ["Luz del piso"] and s[0]["vigente"] is True
    assert c.uno(owner, "SELECT count(*) FROM gapto.propiedad_servicios WHERE servicio_entidad_id = %s", (sid,)) == 1
    assert c.filas_renta(owner) == 0                                                    # no crea reglas (F06-04)
    suelto = uuid.uuid4()
    r = c.post(cli, "/v1/intenciones/servicio", {"intencion_id": str(suelto), "tipo_servicio": "AGUA", "nombre": "Agua"})
    assert r.status_code == 200, r.text                                                  # sin propiedad ni `desde`
    antes = c.huella()
    r = c.post(cli, "/v1/intenciones/servicio", {"intencion_id": str(uuid.uuid4()), "tipo_servicio": "GAS",
                                                  "nombre": "Gas", "propiedad_id": str(pid)})
    c.rechazo_sin_cambios(cli, r, 422, "FECHA_INICIO_REQUERIDA", antes)                  # `desde` obligatoria con propiedad
    r = c.post(cli, "/v1/intenciones/servicio", {"intencion_id": str(uuid.uuid4()), "tipo_servicio": "INVENTADO", "nombre": "x"})
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA"


def test_servicio_editar_nombre_categoria_y_notas(t):
    owner, cli, pid, _ = t
    sid = c.servicio(cli, pid)
    s = c.get(cli, f"/v1/propiedades/{pid}/servicios").json()["servicios"][0]
    r = c.post(cli, f"/v1/servicios/{sid}/editar", {"intencion_id": str(uuid.uuid4()),
                                                     "row_version_esperada": s["row_version"], "nombre": "Luz y calefaccion"})
    assert r.status_code == 200 and r.json()["servicio"]["nombre"] == "Luz y calefaccion"
    assert r.json()["row_version"] == s["row_version"] + 1
    antes = c.huella()
    r = c.post(cli, f"/v1/servicios/{sid}/editar", {"intencion_id": str(uuid.uuid4()),
                                                     "row_version_esperada": s["row_version"], "notas": "x"})
    c.rechazo_sin_cambios(cli, r, 409, "VERSION_DESFASADA", antes)


# ================================================================== O-7 tratamiento (M-9)
def _firmado_con_servicios(cli, pid, ana, **kw):
    luz, limpieza = c.servicio(cli, pid, tipo="LUZ", nombre="Luz"), c.servicio(cli, pid, tipo="LIMPIEZA", nombre="Limpieza")
    return luz, limpieza


def test_o_7_tratamiento_en_el_alta_incluido_fijo_y_por_factura(t):
    owner, cli, pid, ana = t
    luz, limpieza = _firmado_con_servicios(cli, pid, ana)
    agua = c.servicio(cli, pid, tipo="AGUA", nombre="Agua")
    servicios = [{"servicio_id": str(limpieza), "modo": "INCLUIDO"},
                 {"servicio_id": str(luz), "modo": "REPERCUTIDO_FIJO", "inquilino_tercero_id": str(ana), "porcentaje": "50"},
                 {"servicio_id": str(agua), "modo": "POR_FACTURA", "inquilino_tercero_id": str(ana)}]
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01", servicios=servicios)
    por = {s["servicio_id"]: s for s in ct["servicios"]}
    assert por[str(limpieza)]["modo"] == "INCLUIDO" and por[str(limpieza)]["porcentaje"] is None
    assert por[str(luz)]["modo"] == "REPERCUTIDO_FIJO" and por[str(luz)]["modo_reparto"] == "FIJO"
    assert por[str(luz)]["porcentaje"] == "50.0000"
    assert por[str(agua)]["modo"] == "POR_FACTURA" and por[str(agua)]["porcentaje"] is None
    assert por[str(agua)]["texto"] == "Se reparte en cada factura"                         # nunca «Sin indicar» ni 100 %
    assert c.uno(owner, "SELECT modo_reparto FROM gapto.contrato_servicios WHERE servicio_entidad_id = %s", (luz,)) == "FIJO"
    assert c.filas_renta(owner) == 0                                                      # no crea derecho de cobro


def test_o_7_negativos_del_tratamiento(t):
    owner, cli, pid, ana = t
    av = c.tercero(cli, "Aval")
    luz = c.servicio(cli, pid, tipo="LUZ", nombre="Luz")
    base = [c.yo("PROPIETARIO", True), c.de(ana, "INQUILINO", True), c.de(av, "AVALISTA")]
    antes = c.huella()
    casos = [({"modo": "POR_FACTURA", "inquilino_tercero_id": str(ana), "porcentaje": "50"}, "TRATAMIENTO_INCOMPATIBLE"),
             ({"modo": "REPERCUTIDO_FIJO", "inquilino_tercero_id": str(av), "porcentaje": "50"}, "ACTOR_NO_ES_INQUILINO"),
             ({"modo": "REPERCUTIDO_FIJO", "inquilino_tercero_id": str(ana), "porcentaje": "0"}, "TRATAMIENTO_INCOMPATIBLE"),
             ({"modo": "REPERCUTIDO_FIJO", "inquilino_tercero_id": str(ana)}, "TRATAMIENTO_INCOMPATIBLE"),
             ({"modo": "INCLUIDO", "porcentaje": "10"}, "TRATAMIENTO_INCOMPATIBLE")]
    for tr, codigo in casos:
        r = c.alta(cli, pid, habitacion=1, personas=base, servicios=[{"servicio_id": str(luz), **tr}])
        c.rechazo_sin_cambios(cli, r, 422, codigo, antes)
    # servicio de OTRA propiedad: no vinculado a la del contrato
    otra = c.propiedad(cli, nombre="Otra")
    ajeno = c.servicio(cli, otra, nombre="Luz de otra")
    r = c.alta(cli, pid, habitacion=1, personas=base, servicios=[{"servicio_id": str(ajeno), "modo": "INCLUIDO"}])
    c.rechazo_sin_cambios(cli, r, 422, "SERVICIO_NO_VINCULADO_A_PROPIEDAD", antes)
    dos = [{"servicio_id": str(luz), "modo": "INCLUIDO"}, {"servicio_id": str(luz), "modo": "NO_REPERCUTIDO"}]
    c.rechazo_sin_cambios(cli, c.alta(cli, pid, habitacion=1, personas=base, servicios=dos), 422, "ENTRADA_INVALIDA", antes)


def test_o_7_cambio_de_tratamiento_sin_indicar_y_errata(t):
    owner, cli, pid, ana = t
    luz = c.servicio(cli, pid, tipo="LUZ", nombre="Luz")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01",
                         servicios=[{"servicio_id": str(luz), "modo": "INCLUIDO"}])
    ruta = c.ruta(ct["id"], f"/servicios/{luz}")
    antes = c.huella()
    igual = c.post(cli, ruta, c.cuerpo_v(ct, modo="NO_REPERCUTIDO", desde="2026-03-01"))
    c.rechazo_sin_cambios(cli, igual, 422, "DESDE_IGUAL_A_VERSION_ABIERTA", antes)
    anterior = c.post(cli, ruta, c.cuerpo_v(ct, modo="NO_REPERCUTIDO", desde="2026-02-01"))
    c.rechazo_sin_cambios(cli, anterior, 422, "FECHA_ANTERIOR_INICIO", antes)
    r = c.post(cli, ruta, c.cuerpo_v(ct, modo="REPERCUTIDO_FIJO", inquilino_tercero_id=str(ana), porcentaje="50",
                                     desde="2026-07-01"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    historia = [(s["modo"], s["vigente_desde"], s["vigente_hasta"]) for s in ct["servicios"]]
    assert historia == [("INCLUIDO", "2026-03-01", "2026-06-30"), ("REPERCUTIDO_FIJO", "2026-07-01", None)]
    # SIN_INDICAR: cierra la abierta (desde - 1) y nunca borra
    filas = c.uno(owner, "SELECT count(*) FROM gapto.contrato_servicios WHERE contrato_entidad_id = %s", (ct["id"],))
    r = c.post(cli, ruta, c.cuerpo_v(ct, modo="SIN_INDICAR", desde="2026-10-01"))
    assert r.status_code == 200, r.text
    assert c.uno(owner, "SELECT count(*) FROM gapto.contrato_servicios WHERE contrato_entidad_id = %s", (ct["id"],)) == filas
    ct = r.json()["contrato"]
    assert [s["vigente_hasta"] for s in ct["servicios"]] == ["2026-06-30", "2026-09-30"]
    # errata sin cambio de vigencia: UPDATE auditado con motivo
    ct2 = c.crear_firmado(cli, pid, ana, habitacion=2, inicio="2026-03-01",
                          servicios=[{"servicio_id": str(luz), "modo": "NO_REPERCUTIDO"}])
    err = c.post(cli, c.ruta(ct2["id"], f"/servicios/{luz}"), c.cuerpo_v(ct2, modo="INCLUIDO", corregir=True))
    c.rechazo(err, 422, "MOTIVO_AUSENTE")
    ok = c.post(cli, c.ruta(ct2["id"], f"/servicios/{luz}"), c.cuerpo_v(ct2, modo="INCLUIDO", corregir=True, motivo="Estaba mal"))
    assert ok.status_code == 200 and [s["modo"] for s in ok.json()["contrato"]["servicios"]] == ["INCLUIDO"]


# ================================================================== C-SRV-03 baja y O-31
def test_baja_cierra_vigencias_sin_borrar_y_valida_fechas(t):
    owner, cli, pid, ana = t
    luz = c.servicio(cli, pid, tipo="LUZ", nombre="Luz", desde="2026-01-01")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01",
                         servicios=[{"servicio_id": str(luz), "modo": "INCLUIDO"}])
    s = c.get(cli, f"/v1/propiedades/{pid}/servicios").json()["servicios"][0]
    antes = c.huella()
    anterior = c.post(cli, f"/v1/servicios/{luz}/baja", {"intencion_id": str(uuid.uuid4()),
                                                          "row_version_esperada": s["row_version"], "fecha_fin_real": "2026-02-28"})
    c.rechazo_sin_cambios(cli, anterior, 422, "FECHA_FIN_ANTERIOR_A_VIGENCIA", antes)    # antes del `desde` del tratamiento
    r = c.post(cli, f"/v1/servicios/{luz}/baja", {"intencion_id": str(uuid.uuid4()),
                                                   "row_version_esperada": s["row_version"], "fecha_fin_real": "2026-10-31"})
    assert r.status_code == 200, r.text
    assert c.uno(owner, "SELECT count(*) FROM gapto.propiedad_servicios WHERE servicio_entidad_id = %s "
                        "AND vigente_hasta = '2026-10-31'", (luz,)) == 1
    assert c.uno(owner, "SELECT count(*) FROM gapto.contrato_servicios WHERE servicio_entidad_id = %s "
                        "AND vigente_hasta = '2026-10-31'", (luz,)) == 1
    assert c.leer(cli, ct["id"])["row_version"] == ct["row_version"] + 1                # el contrato sube su version
    # despues de la baja: ni tratamiento ni vinculo nuevos
    ct = c.leer(cli, ct["id"])
    nuevo = c.post(cli, c.ruta(ct["id"], f"/servicios/{luz}"), c.cuerpo_v(ct, modo="NO_REPERCUTIDO", desde="2026-11-15"))
    c.rechazo(nuevo, 409, "SERVICIO_DADO_DE_BAJA")


def test_o_31_baja_de_servicio_con_regla_financiera(t):
    owner, cli, pid, _ = t
    luz = c.servicio(cli, pid)
    h.como_owner(owner, "INSERT INTO gapto.reglas_financieras (id, owner_user_id, nombre, entidad_origen_id) "
                        "VALUES (%s, current_setting('gapto.owner_user_id')::uuid, 'Luz mensual', %s)", (uuid.uuid4(), luz))
    s = c.get(cli, f"/v1/propiedades/{pid}/servicios").json()["servicios"][0]
    antes = c.huella()
    r = c.post(cli, f"/v1/servicios/{luz}/baja", {"intencion_id": str(uuid.uuid4()),
                                                   "row_version_esperada": s["row_version"], "fecha_fin_real": "2026-10-31"})
    cuerpo = c.rechazo(r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", "REGLA_SERVICIO_PENDIENTE_DE_F06_04")
    assert cuerpo["motivo"] != "RENTA_PENDIENTE_DE_F06_04" and "pago previsto" in cuerpo["mensaje"]
    assert c.huella() == antes
