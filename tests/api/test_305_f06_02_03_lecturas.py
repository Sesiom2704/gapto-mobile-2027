# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_305_f06_02_03_lecturas.py
# Ruta: tests/api/test_305_f06_02_03_lecturas.py
# Descripcion: F06-02/03 · Lecturas L-CON-01..03, L-SRV-01, L-TER-01 y V-bis (contrato v1.1 Parte VI y V-bis), por
#   HTTP como gapto_runtime con RLS. Oraculos: O-1a (fixture independiente: piso de 4 habitaciones; hoy 2026-11-18),
#   O-1b (escenario A1 de la lamina CON v0.8: 3 ocupadas, 1 proxima, 1 libre, `fin_previsto_vencido` en 25-HAB5-LM,
#   26-HAB4-ES en «Borradores», 2 finalizados), O-32 (homonimos distinguibles por naturaleza y uso, regla estable de
#   desempate) y O-33 (el uso nunca incluye contratos, hechos ni movimientos de otro owner; UNA consulta, sin N+1).
#   La situacion y la ocupacion son DERIVADAS (sin columna). `GET /v1/terceros/{id}` es ruta nueva: debe convivir
#   con `GET /v1/terceros/candidatos`. Los contratos del escenario A1 que solapan por construccion (datos
#   «migrados») se fijan con SQL bajo gapto_owner: el alta bloquea el solape entre firmados.
#   ESCRITO SIN EJECUTAR (sin base esta noche).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid

import psycopg
import pytest

import f06_02_03_helpers as c
import vs01_api_helpers as h


@pytest.fixture()
def t():
    owner, actor, cli = c.entorno()
    return owner, cli


def _contrato(cli, pid, ana, nombre, habitacion, estado, inicio, **kw) -> dict:
    personas = c.partes(ana) if estado == "FORMALIZADO" else None
    return c.crear(cli, pid, habitacion=habitacion, estado=estado, inicio=inicio, nombre=nombre, personas=personas, **kw)


def _terminar(cli, ct, fin) -> None:
    r = c.post(cli, c.ruta(ct["id"], "/terminar"), c.cuerpo_v(ct, fecha_fin_real=fin))
    assert r.status_code == 200, r.text


# ================================================================== O-1a y O-1b
def test_o_1a_fixture_independiente_de_ocupacion(t):
    owner, cli = t
    ana = c.tercero(cli, "Ana")
    pid = c.propiedad(cli, habitaciones=4)
    _contrato(cli, pid, ana, "H1", 1, "FORMALIZADO", "2026-09-01")
    _contrato(cli, pid, ana, "H2", 2, "FORMALIZADO", "2026-03-01", fecha_fin_prevista="2027-08-31")
    _contrato(cli, pid, ana, "H3", 3, "FORMALIZADO", "2026-12-01")
    _contrato(cli, pid, ana, "H4", 4, "BORRADOR", "2026-11-01")
    lectura = c.get(cli, f"/v1/propiedades/{pid}/contratos").json()
    estados = {o["habitacion"]: o["estado"] for o in lectura["ocupacion"]}
    assert estados == {1: "OCUPADA", 2: "OCUPADA", 3: "PROXIMA", 4: "LIBRE"}           # el borrador no ocupa
    assert sorted(x["nombre"] for x in lectura["vigentes"]) == ["H1", "H2"]
    assert [x["nombre"] for x in lectura["proximos"]] == ["H3"] and [x["nombre"] for x in lectura["borradores"]] == ["H4"]
    assert lectura["hoy"] == "2026-11-18" and lectura["habitaciones_ficha"] == 4
    assert len(lectura["contratos"]) == 4 and all("contrato_id" in x and "inquilino_principal" in x for x in lectura["contratos"])


def test_o_1b_escenario_a1_validado_de_la_lamina_v08(t):
    owner, cli = t
    ana = c.tercero(cli, "Ana")
    pid = c.propiedad(cli, habitaciones=5)
    # los dos terminados primero: un firmado sin fin real solaparia despues con 26-HAB3-PR (el alta lo bloquea)
    for nombre, hab, inicio, fin in (("25-HAB3-X", 3, "2025-01-01", "2025-12-31"), ("25-HAB4-Y", 4, "2025-01-01", "2026-06-30")):
        _terminar(cli, _contrato(cli, pid, ana, nombre, hab, "FORMALIZADO", inicio), fin)
    _contrato(cli, pid, ana, "26-HAB1-CR", 1, "FORMALIZADO", "2026-09-01")
    _contrato(cli, pid, ana, "26-HAB2-AG", 2, "FORMALIZADO", "2026-01-01", fecha_fin_prevista="2027-08-31")
    _contrato(cli, pid, ana, "25-HAB5-LM", 5, "FORMALIZADO", "2025-11-01", fecha_fin_prevista="2026-10-31")  # sin fin real
    _contrato(cli, pid, ana, "26-HAB3-PR", 3, "FORMALIZADO", "2026-12-01")
    _contrato(cli, pid, ana, "26-HAB4-ES", 4, "BORRADOR", "2026-11-01")
    lectura = c.get(cli, f"/v1/propiedades/{pid}/contratos").json()
    estados = {o["habitacion"]: o["estado"] for o in lectura["ocupacion"]}
    assert sorted(h for h, e in estados.items() if e == "OCUPADA") == [1, 2, 5]
    assert [h for h, e in estados.items() if e == "PROXIMA"] == [3] and [h for h, e in estados.items() if e == "LIBRE"] == [4]
    por_nombre = {x["nombre"]: x for g in ("vigentes", "proximos", "borradores", "finalizados") for x in lectura[g]}
    assert por_nombre["25-HAB5-LM"]["fin_previsto_vencido"] is True                       # «termina o prorroga»
    assert por_nombre["25-HAB5-LM"] in lectura["vigentes"]
    assert [x["nombre"] for x in lectura["borradores"]] == ["26-HAB4-ES"]
    assert sorted(x["nombre"] for x in lectura["finalizados"]) == ["25-HAB3-X", "25-HAB4-Y"]
    assert not any(x["fin_previsto_vencido"] for n, x in por_nombre.items() if n != "25-HAB5-LM")


def test_no_hay_columna_de_situacion_ni_de_ocupacion(t):
    owner, _ = t
    columnas = {f[0] for f in h.leer(owner, "SELECT column_name FROM information_schema.columns "
                                              "WHERE table_schema = 'gapto' AND table_name = 'contratos'")}
    assert not {"situacion", "ocupacion", "ocupada", "vigente", "finalizado", "fin_previsto_vencido"} & columnas


def test_cancelado_aparece_aparte_y_no_ocupa(t):
    owner, cli = t
    pid = c.propiedad(cli, habitaciones=2)
    bor = c.crear(cli, pid, habitacion=1, estado="BORRADOR")
    assert c.post(cli, c.ruta(bor["id"], "/cancelar"), c.cuerpo_v(bor, motivo="No")).status_code == 200
    lectura = c.get(cli, f"/v1/propiedades/{pid}/contratos").json()
    assert [x["id"] for x in lectura["cancelados"]] == [bor["id"]] and lectura["borradores"] == []
    assert c.get(cli, f"/v1/propiedades/{uuid.uuid4()}/contratos").status_code == 404


# ================================================================== L-CON-02 terminable y renta V3
def test_l_con_02_terminable_y_motivo(t):
    owner, cli = t
    ana = c.tercero(cli, "Ana")
    pid = c.propiedad(cli)
    ct = _contrato(cli, pid, ana, "A", 1, "FORMALIZADO", "2026-09-01")
    assert ct["terminable"] == {"terminable": True, "motivo": None} and ct["renta_registrada"] is False
    bor = _contrato(cli, pid, ana, "B", 2, "BORRADOR", "2026-09-01")
    assert bor["terminable"] == {"terminable": False, "motivo": "CONTRATO_NO_VIGENTE"}
    c.con_regla_renta(owner, ct["id"])
    v3 = c.leer(cli, ct["id"])
    assert v3["terminable"] == {"terminable": False, "motivo": "RENTA_PENDIENTE_DE_F06_04"}
    assert v3["renta_registrada"] is True and "importe" not in str(v3).lower()          # sin importes: es de F06-04
    assert c.get(cli, f"/v1/contratos/{uuid.uuid4()}").status_code == 404


# ================================================================== L-CON-03 propuesta
def test_l_con_03_propuesta_de_arrendadores_habitaciones_y_nombre(t):
    owner, cli = t
    pid, ana = c.propiedad(cli, habitaciones=3), c.tercero(cli, "Ana Pérez")
    r = c.get(cli, f"/v1/propiedades/{pid}/contratos/propuesta?tipo=HABITACION&habitacion=2&inicio=2026-09-01&inquilino_id={ana}")
    assert r.status_code == 200, r.text
    p = r.json()
    assert [(a["yo"], a["tercero_id"]) for a in p["arrendadores"]] == [(True, None)]      # titular vigente en `inicio`
    assert p["nombre_propuesto"] == "26-HAB2-AP" and len(p["habitaciones"]) == 3
    # con el nombre ya usado se propone «-2»; la propuesta no escribe ni bloquea
    c.crear(cli, pid, habitacion=2, estado="BORRADOR", nombre="26-HAB2-AP")
    antes = c.huella()
    p = c.get(cli, f"/v1/propiedades/{pid}/contratos/propuesta?tipo=HABITACION&habitacion=2&inicio=2026-09-01&inquilino_id={ana}").json()
    assert p["nombre_propuesto"] == "26-HAB2-AP-2" and c.huella() == antes
    viv = c.get(cli, f"/v1/propiedades/{pid}/contratos/propuesta?tipo=VIVIENDA_COMPLETA&inicio=2026-09-01&inquilino_id={ana}").json()
    otro = c.get(cli, f"/v1/propiedades/{pid}/contratos/propuesta?tipo=OTRO&inicio=2026-09-01&inquilino_id={ana}").json()
    assert viv["nombre_propuesto"] == "26-VIV-AP" and otro["nombre_propuesto"] == "26-OTRO-AP"
    # titularidad DESCONOCIDA: lista vacia de arrendadores
    from f06_01_b1_helpers import alta as alta_propiedad, crear as crear_propiedad
    desconocida = crear_propiedad(cli, alta_propiedad({"modo": "DESCONOCIDA"}, nombre="Desconocida"))
    p = c.get(cli, f"/v1/propiedades/{desconocida['id']}/contratos/propuesta?tipo=OTRO&inicio=2026-09-01").json()
    assert p["arrendadores"] == []


# ================================================================== L-SRV-01
def test_l_srv_01_servicios_y_tratamiento_en_cada_contrato_vigente(t):
    owner, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    luz, agua = c.servicio(cli, pid, tipo="LUZ", nombre="Luz"), c.servicio(cli, pid, tipo="AGUA", nombre="Agua")
    c.crear_firmado(cli, pid, ana, habitacion=1, servicios=[
        {"servicio_id": str(luz), "modo": "REPERCUTIDO_FIJO", "inquilino_tercero_id": str(ana), "porcentaje": "50"},
        {"servicio_id": str(agua), "modo": "POR_FACTURA", "inquilino_tercero_id": str(ana)}])
    s = {x["nombre"]: x for x in c.get(cli, f"/v1/propiedades/{pid}/servicios").json()["servicios"]}
    assert s["Luz"]["tratamientos"][0]["modo_reparto"] == "FIJO" and s["Luz"]["tratamientos"][0]["porcentaje"] == "50.0000"
    assert s["Agua"]["tratamientos"][0]["modo_reparto"] == "POR_FACTURA"
    assert s["Agua"]["tratamientos"][0]["texto"] == "Se reparte en cada factura"
    assert c.get(cli, f"/v1/propiedades/{uuid.uuid4()}/servicios").status_code == 404


# ================================================================== L-TER-01
def test_l_ter_01_ficha_con_roles_clasificacion_y_uso_en_gapto(t):
    owner, cli = t
    pid, ana = c.propiedad(cli), c.tercero(cli, "Ana")
    ct = c.crear_firmado(cli, pid, ana, habitacion=1, inicio="2026-09-01", nombre="26-HAB1-AN")
    assert c.post(cli, f"/v1/terceros/{ana}/roles", {"intencion_id": str(uuid.uuid4()), "row_version_esperada":
                  c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (ana,)), "anadir": ["INQUILINO"]}).status_code == 200
    r = c.get(cli, f"/v1/terceros/{ana}")
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert ficha["tercero"]["id"] == str(ana)
    assert ficha["roles"] == ["INQUILINO"] and ficha["clasificaciones"] == []
    assert [(u["contrato_nombre"], u["rol"], u["desde"], u["hasta"]) for u in ficha["uso"]] == \
        [("26-HAB1-AN", "INQUILINO", "2026-09-01", None)]
    assert "direcciones" not in ficha                                                   # sin direcciones en este bloque
    # la ruta nueva no oculta a `/candidatos` (que se declara antes)
    cand = c.get(cli, "/v1/terceros/candidatos?nombre=Ana")
    assert cand.status_code == 200 and [x["id"] for x in cand.json()["terceros"]] == [str(ana)]
    assert c.get(cli, f"/v1/terceros/{uuid.uuid4()}").status_code == 404 and ct
    assert c.get(cli, "/v1/clasificaciones-tercero").json()["clasificaciones"] == []


# ================================================================== V-bis · O-32 y O-33
def test_o_32_homonimos_distinguibles_por_naturaleza_y_uso(t):
    owner, cli = t
    pid = c.propiedad(cli)
    a, b = c.tercero(cli, "Empresa SL", "EMPRESA"), c.tercero(cli, "Empresa SL", "EMPRESA")
    c.crear_firmado(cli, pid, a, habitacion=1, inicio="2026-09-01", nombre="26-HAB1-ES")
    r = c.get(cli, "/v1/terceros/asistente-contratos?q=empresa")
    assert r.status_code == 200, r.text
    filas = {x["id"]: x for x in r.json()["terceros"]}
    assert filas[str(a)]["homonimo"] is True and filas[str(b)]["homonimo"] is True
    assert filas[str(a)]["naturaleza"] == "EMPRESA"
    assert (filas[str(a)]["uso"]["tipo"], filas[str(a)]["uso"]["rol"], filas[str(a)]["uso"]["contrato_nombre"]) == \
        ("CONTRATO", "INQUILINO", "26-HAB1-ES")
    assert filas[str(b)]["uso"] == {"tipo": "SIN_USO"}                                   # sin uso: nada inventado


def test_o_32_con_dos_contratos_se_muestra_el_de_inicio_mas_reciente(t):
    owner, cli = t
    pid, a, otro = c.propiedad(cli), c.tercero(cli, "Empresa SL", "EMPRESA"), c.tercero(cli, "Empresa SL", "EMPRESA")
    primero = c.crear_firmado(cli, pid, a, habitacion=1, inicio="2026-01-01", nombre="26-HAB1-VIEJO")
    _terminar(cli, primero, "2026-06-30")
    c.crear_firmado(cli, pid, a, habitacion=1, inicio="2026-07-01", nombre="26-HAB1-NUEVO")
    # desempate estable: dos contratos con el MISMO inicio -> el de mayor contratos.entidad_id (nunca el orden fisico)
    uso = {x["id"]: x for x in c.get(cli, "/v1/terceros/asistente-contratos").json()["terceros"]}[str(a)]["uso"]
    assert uso["contrato_nombre"] == "26-HAB1-NUEVO" and uso["tipo"] == "CONTRATO" and otro


def test_el_selector_solo_lista_activos_y_sin_contratos_cae_al_ultimo_hecho(t):
    owner, cli = t
    activo, baja = c.tercero(cli, "Activo SL", "EMPRESA"), c.tercero(cli, "Baja SL", "EMPRESA")
    ver = c.uno(owner, "SELECT row_version FROM gapto.terceros WHERE id = %s", (baja,))
    assert c.post(cli, f"/v1/terceros/{baja}/desactivar", {"row_version": ver}).status_code == 200
    ids = [x["id"] for x in c.get(cli, "/v1/terceros/asistente-contratos").json()["terceros"]]
    assert str(activo) in ids and str(baja) not in ids                                   # los inactivos van por V-ter


def test_o_33_aislamiento_del_uso_y_una_sola_consulta(t, monkeypatch):
    owner, cli = t
    otro_owner, _, cli2 = c.entorno()
    pid = c.propiedad(cli)
    pid2 = c.propiedad(cli2)
    mio = c.tercero(cli, "Empresa SL", "EMPRESA")
    ajeno = c.tercero(cli2, "Empresa SL", "EMPRESA")
    c.crear_firmado(cli2, pid2, ajeno, habitacion=1, inicio="2026-09-01", nombre="CONTRATO-DEL-OTRO")
    filas = c.get(cli, "/v1/terceros/asistente-contratos?q=empresa").json()["terceros"]
    assert [x["id"] for x in filas] == [str(mio)]                                       # ni siquiera ve al tercero ajeno
    assert filas[0]["uso"] == {"tipo": "SIN_USO"} and filas[0]["homonimo"] is False                    # el contrato del otro owner no cuenta
    assert "CONTRATO-DEL-OTRO" not in str(c.get(cli, f"/v1/terceros/{mio}").json())

    # una sola consulta de datos del selector con 1 o con 25 terceros (sin N+1)
    def contar() -> int:
        n = {"v": 0}
        original = psycopg.Cursor.execute

        def espia(self, query, *a, **k):
            if "FROM gapto.terceros t LEFT JOIN LATERAL" in str(query):
                n["v"] += 1
            return original(self, query, *a, **k)

        monkeypatch.setattr(psycopg.Cursor, "execute", espia)
        try:
            assert c.get(cli, "/v1/terceros/asistente-contratos").status_code == 200
        finally:
            monkeypatch.setattr(psycopg.Cursor, "execute", original)
        return n["v"]

    una = contar()
    for i in range(25):
        c.tercero(cli, f"Tercero {i}")
    assert una == 1 and contar() == 1
