# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_302_f06_02_03_sucesor_y_personas.py
# Ruta: tests/api/test_302_f06_02_03_sucesor_y_personas.py
# Descripcion: F06-02/03 · C-CON-05 sucesor en una habitacion y C-CON-06 personas por vigencias (Q-CON-07; D25).
#   Oraculos: O-3 (cambio de inquilino en la habitacion 1: terminacion + contrato nuevo en UNA operacion; fallo
#   inyectado entre ambos -> 0 filas), O-4 (vivienda completa con dos inquilinos: uno se va y el contrato sigue;
#   cerrar al ultimo -> CONTRATO_SIN_INQUILINO), O-22 (YO inquilino en C-CON-06), O-27 (ultimo arrendador:
#   CONTRATO_SIN_ARRENDADOR; con un GESTOR anadido antes, OK; correccion de fechas que deja un hueco -> 409),
#   O-29 (sucesor con tercero nuevo por el writer de F05; la prueba concurrente esta en test_307).
#   ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f06_02_03_helpers as c
import vs01_api_helpers as h
from app.contratos import servicio as serv_contratos


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    return owner, cli, pid, ana


def _nuevo(inquilino, **extra) -> dict:
    return {"nombre": "26-HAB1-LU", "fecha_inicio": "2026-11-01", "estado": "FORMALIZADO",
            "personas": c.partes(inquilino), **extra}


# ================================================================== O-3 sucesor
def test_o_3_cambio_de_inquilino_en_la_habitacion_1_en_una_operacion(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01", nombre="26-HAB1-AN")
    i = uuid.uuid4()
    cuerpo = {"intencion_id": str(i), "row_version_esperada": actual["row_version"], "fecha_fin_real": "2026-10-31",
              "nuevo": _nuevo(luis)}
    r = c.post(cli, c.ruta(actual["id"], "/sucesor"), cuerpo)
    assert r.status_code == 200, r.text
    nuevo, terminado = r.json()["contrato"], r.json()["terminado"]
    assert nuevo["id"] == str(uuid.uuid5(i, "contrato"))                          # identidad derivada de la intencion
    assert (nuevo["tipo"], nuevo["habitacion"], nuevo["fecha_inicio"]) == ("HABITACION", 1, "2026-11-01")
    assert terminado["fecha_fin_real"] == "2026-10-31" and terminado["situacion"] == "FINALIZADO"
    assert {p["vigente_hasta"] for p in terminado["personas"]} == {"2026-10-31"}
    assert c.uno(owner, "SELECT count(*) FROM gapto.contratos WHERE propiedad_entidad_id = %s", (pid,)) == 2
    assert c.filas_renta(owner) == 0
    # replay identico: idempotente y sin filas nuevas
    antes = c.huella()
    r2 = c.post(cli, c.ruta(actual["id"], "/sucesor"), cuerpo)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True and c.huella() == antes


def test_o_3_fallo_inyectado_entre_la_terminacion_y_el_contrato_nuevo_deja_cero_filas(t, monkeypatch):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    antes = c.huella()

    def explota(*a, **k):
        raise RuntimeError("fallo inyectado entre la terminacion y el contrato nuevo")

    monkeypatch.setattr(serv_contratos.repo, "insertar_contrato", explota)
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": actual["row_version"],
              "fecha_fin_real": "2026-10-31", "nuevo": _nuevo(luis)}
    r = c.post(cli, c.ruta(actual["id"], "/sucesor"), cuerpo)
    assert r.status_code == 500
    assert c.huella() == antes                                                    # 0 filas: nada a medias


def test_sucesor_requisitos(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    antes = c.huella()

    def sucesor(contrato, **kw):
        base = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": contrato["row_version"],
                "fecha_fin_real": "2026-10-31", "nuevo": _nuevo(luis)}
        base.update(kw)
        return c.post(cli, c.ruta(contrato["id"], "/sucesor"), base)

    # el nuevo empieza el ultimo dia del anterior (o antes) -> SUCESOR_SOLAPADO
    for inicio in ("2026-10-31", "2026-09-01"):
        c.rechazo_sin_cambios(cli, sucesor(actual, nuevo=_nuevo(luis, fecha_inicio=inicio)), 422, "SUCESOR_SOLAPADO", antes)
    # fin real anterior al inicio del actual
    c.rechazo_sin_cambios(cli, sucesor(actual, fecha_fin_real="2025-12-31"), 422, "FECHA_FIN_ANTERIOR_A_VIGENCIA", antes)
    # renta / fianza en el nuevo
    c.rechazo_sin_cambios(cli, sucesor(actual, nuevo=_nuevo(luis, renta={"importe": "1"})), 422, "RENTA_NO_DISPONIBLE", antes)
    # el nuevo, FORMALIZADO, no puede coincidir con otro firmado de la propiedad (p. ej. una vivienda completa)
    # una vivienda completa que ya coincide con la habitacion 1 solo puede existir como DATO MIGRADO (V3): el alta no
    # la admite firmada; se fija con SQL bajo gapto_owner (borrador -> FORMALIZADO)
    viv = c.crear(cli, pid, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-11-15", nombre="V",
                  estado="BORRADOR", personas=c.partes(ana))
    h.como_owner(owner, "UPDATE gapto.contratos SET estado_documental = 'FORMALIZADO' WHERE entidad_id = %s", (viv["id"],))
    antes = c.huella()
    c.rechazo_sin_cambios(cli, sucesor(actual, nuevo=_nuevo(luis, fecha_inicio="2026-11-20")), 409,
                          "SOLAPE_CON_CONTRATO_FIRMADO", antes)
    # solo HABITACION vigentes: vivienda completa, borrador y terminado -> CONTRATO_NO_VIGENTE
    c.rechazo_sin_cambios(cli, sucesor(viv), 409, "CONTRATO_NO_VIGENTE", antes)
    bor = c.crear(cli, pid, habitacion=3, estado="BORRADOR")
    antes = c.huella()
    c.rechazo_sin_cambios(cli, sucesor(bor), 409, "CONTRATO_NO_VIGENTE", antes)


def test_o_29_sucesor_con_tercero_nuevo_usa_el_writer_de_f05(t):
    owner, cli, pid, ana = t
    actual = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    nid = uuid.uuid4()
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": actual["row_version"],
              "fecha_fin_real": "2026-10-31",
              "nuevo": {"nombre": "26-HAB1-NU", "fecha_inicio": "2026-11-01", "estado": "FORMALIZADO",
                        "personas": [c.yo("PROPIETARIO", True), c.nuevo("Nuevo Inquilino", "INQUILINO", True,
                                                                        naturaleza="PERSONA", id_=nid)]}}
    r = c.post(cli, c.ruta(actual["id"], "/sucesor"), cuerpo)
    assert r.status_code == 200, r.text
    assert c.uno(owner, "SELECT nombre FROM gapto.terceros WHERE id = %s", (nid,)) == "Nuevo Inquilino"
    assert c.uno(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (nid,)) == 1


# ================================================================== O-4 vivienda completa con dos inquilinos
def test_o_4_uno_se_va_y_el_contrato_sigue_cerrar_al_ultimo_es_contrato_sin_inquilino(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-01-01")
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(luis)}, rol="INQUILINO",
                                                              desde="2026-02-01"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    luis_fila = next(p for p in ct["personas"] if p["tercero_id"] == str(luis))
    ana_fila = next(p for p in ct["personas"] if p["tercero_id"] == str(ana))
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{luis_fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-06-30"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    assert ct["estado_documental"] == "FORMALIZADO" and ct["situacion"] == "VIGENTE"   # el contrato sigue
    antes = c.huella()
    # el principal (Ana) es el ultimo inquilino: cerrarla -> CONTRATO_SIN_INQUILINO, estado identico
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{ana_fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-09-30"))
    c.rechazo_sin_cambios(cli, r, 409, "CONTRATO_SIN_INQUILINO", antes)
    # una vigencia ya cerrada no se vuelve a cerrar
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{luis_fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-07-31"))
    c.rechazo_sin_cambios(cli, r, 409, "OPERACION_NO_PERMITIDA_EN_ESTADO", antes)


def test_cerrar_al_principal_exige_nombrar_otro_si_quedan_personas_en_el_rol(t):
    owner, cli, pid, ana = t
    luis = c.tercero(cli, "Luis")
    ct = c.crear_firmado(cli, pid, ana, tipo="VIVIENDA_COMPLETA", habitacion=None, inicio="2026-01-01")
    ct = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(luis)}, rol="INQUILINO",
                                                               desde="2026-01-01")).json()["contrato"]
    ana_fila = next(p for p in ct["personas"] if p["tercero_id"] == str(ana))
    luis_fila = next(p for p in ct["personas"] if p["tercero_id"] == str(luis))
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{ana_fila['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-06-30"))
    c.rechazo_sin_cambios(cli, r, 422, "PRINCIPAL_REQUERIDO", antes)               # no nombra a otro principal
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{ana_fila['id']}/cerrar"),
               c.cuerpo_v(ct, hasta="2026-06-30", nuevo_principal=luis_fila["id"]))
    assert r.status_code == 200, r.text
    nuevas = {p["tercero_id"]: p for p in r.json()["contrato"]["personas"]}
    assert nuevas[str(luis)]["principal"] is True and nuevas[str(ana)]["vigente_hasta"] == "2026-06-30"


# ================================================================== O-27 ultimo arrendador
def test_o_27_cerrar_al_ultimo_arrendador(t):
    owner, cli, pid, ana = t
    socio = c.tercero(cli, "Socio")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    prop = next(p for p in ct["personas"] if p["rol"] == "PROPIETARIO")
    antes = c.huella()
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{prop['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-06-30"))
    c.rechazo_sin_cambios(cli, r, 409, "CONTRATO_SIN_ARRENDADOR", antes)
    # con un GESTOR vigente anadido antes, se puede cerrar al PROPIETARIO (relevo contiguo)
    r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(socio)}, rol="GESTOR",
                                                              principal=True, desde="2026-01-01"))
    assert r.status_code == 200, r.text
    ct = r.json()["contrato"]
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{prop['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-06-30"))
    assert r.status_code == 200, r.text


def test_o_27_corregir_fechas_de_personas_que_dejan_un_hueco(t):
    _, cli, pid, ana = t
    socio = c.tercero(cli, "Socio")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-01-01")
    ct = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(socio)}, rol="GESTOR",
                                                               principal=True, desde="2026-07-01")).json()["contrato"]
    prop = next(p for p in ct["personas"] if p["rol"] == "PROPIETARIO")
    ct = c.post(cli, c.ruta(ct["id"], f"/personas/{prop['id']}/cerrar"), c.cuerpo_v(ct, hasta="2026-06-30")).json()["contrato"]
    prop = next(p for p in ct["personas"] if p["rol"] == "PROPIETARIO")
    antes = c.huella()
    # adelantar el fin del propietario deja del 15-jun al 30-jun sin arrendador (el gestor entra el 1-jul): 409
    r = c.post(cli, c.ruta(ct["id"], f"/personas/{prop['id']}/corregir"), c.cuerpo_v(ct, hasta="2026-06-14", motivo="Error de fecha"))
    c.rechazo_sin_cambios(cli, r, 409, "CONTRATO_SIN_ARRENDADOR", antes)
    sin_motivo = c.post(cli, c.ruta(ct["id"], f"/personas/{prop['id']}/corregir"), c.cuerpo_v(ct, hasta="2026-06-29"))
    c.rechazo_sin_cambios(cli, sin_motivo, 422, "MOTIVO_AUSENTE", antes)


# ================================================================== C-CON-06 reglas de personas
def test_o_22_yo_inquilino_agencia_administrador_en_personas(t):
    owner, cli, pid, ana = t
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    antes = c.huella()
    for rol, codigo in (("INQUILINO", "INQUILINO_NO_PUEDE_SER_YO"), ("AGENCIA", "ROL_NO_ADMITIDO_PARA_YO"),
                        ("ADMINISTRADOR", "ROL_NO_ADMITIDO_PARA_YO")):
        r = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor="YO", rol=rol, desde="2026-09-01"))
        c.rechazo_sin_cambios(cli, r, 422, codigo, antes)
    assert c.uno(owner, "SELECT count(*) FROM gapto.tercero_roles") == 0


def test_anadir_persona_reglas_de_fechas_duplicados_y_principal(t):
    _, cli, pid, ana = t
    av = c.tercero(cli, "Aval")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-03-01")
    antes = c.huella()
    anterior = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(av)}, rol="AVALISTA",
                                                                     desde="2026-02-28"))
    c.rechazo_sin_cambios(cli, anterior, 422, "FECHA_ANTERIOR_INICIO", antes)
    repetido = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(ana)}, rol="INQUILINO",
                                                                     desde="2026-03-01"))
    c.rechazo_sin_cambios(cli, repetido, 422, "PARTICIPANTE_DUPLICADO", antes)
    segundo_principal = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(av)},
                                                                              rol="INQUILINO", principal=True,
                                                                              desde="2026-03-01"))
    c.rechazo_sin_cambios(cli, segundo_principal, 422, "PRINCIPAL_DUPLICADO", antes)
    ok = c.post(cli, c.ruta(ct["id"], "/personas"), c.cuerpo_v(ct, actor={"tercero_id": str(av)}, rol="AVALISTA",
                                                               desde="2026-03-01"))
    assert ok.status_code == 200, ok.text                                         # AVALISTA sin principal: OK (O-24)


def test_la_edicion_de_personas_nunca_cambia_la_titularidad(t):
    owner, cli, pid, ana = t
    from f06_01_b1_helpers import leer as leer_propiedad
    antes = leer_propiedad(cli, pid)
    ct = c.crear_firmado(cli, pid, ana, habitacion=1)
    despues = leer_propiedad(cli, pid)
    assert despues["titularidad"] == antes["titularidad"] and despues["row_version"] == antes["row_version"]
    assert ct
