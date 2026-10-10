# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_183_f05_04_corte_concepto.py
# Ruta: tests/api/test_183_f05_04_corte_concepto.py
# Descripcion: Corte de Concepto en el servidor (F05-03/F05-04 J3 §2.7;
#   F05 §46.3 A8, F05-D022 §36.5; E1/E4 de §46.5). Bateria de servidor de
#   CNC-01..20 (CNC-09 NO APLICABLE; la presentacion CNC-20 se cubre en el
#   cliente: registro_tipo.test.tsx):
#     - CNC-18: omitido, null, "" y espacios -> NULL en
#       hechos_financieros.concepto Y en movimientos_tesoreria.descripcion
#       (write-path de gasto pagado); max_length sobre el valor normalizado
#       (300 espacios = ausencia; 201 letras = 422); texto recortado.
#     - CNC-19: misma intencion sin concepto y reintento -> idempotente;
#       blanco y omitido -> la MISMA intencion canonica; NULL frente a un
#       concepto real (y al reves) -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
#       nunca completado silencioso.
#     - CNC-01/02/04/05/06: el gasto sin concepto se registra con tercero y
#       categoria, sin tercero, «Sin categoria» y sin ninguno de los dos.
#     - CNC-03/07: un concepto real se conserva (recortado) junto a la
#       descripcion estructurada.
#     - CNC-08: la plantilla no tiene concepto (test_179 rechaza `concepto`
#       en su DTO) y el cliente no rellena la nota desde una plantilla
#       (registro_tipo.test.tsx); aqui, el gasto sin nota persiste NULL.
#     - CNC-10..13 (renombrados y busqueda): el titulo se calcula en el
#       cliente con los nombres VIGENTES (nunca se persiste) y no hay
#       busqueda de hechos en esta superficie (F05-05).
#     - CNC-16/17: un concepto historico (fila anterior al corte) no se
#       reescribe al registrar hechos nuevos.
#     - Ingreso y transferencia: la nota canonica antes de max_length
#       (validador `before`).
#     - AJ-RLOCALE-03: la forma funcional del error de dominio (codigo,
#       mensaje del catalogo, reintentable) es IDENTICA con lc_messages C y
#       es_ES, sin lista de traducciones (ninguna excepcion de PostgreSQL cruda
#       alcanza HTTP). Complementa test_150, que no cambia.
# Version: 0.1.0 (F05-03/F05-04 J3 §2.7)
# ============================================================

from __future__ import annotations

import decimal
import urllib.parse
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

D = decimal.Decimal
GASTO = "/v1/intenciones/gasto-pagado"
INGRESO = "/v1/intenciones/ingreso-cobrado"
TRANSFERENCIA = "/v1/intenciones/transferencia"


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


def _sin(cuerpo: dict, campo: str) -> dict:
    return {k: v for k, v in cuerpo.items() if k != campo}


def _concepto_y_descripcion(owner, hid) -> tuple:
    return h.leer(owner, "SELECT h.concepto, m.descripcion FROM gapto.hechos_financieros h "
                         "JOIN gapto.hecho_movimientos_tesoreria c ON c.hecho_id = h.id "
                         "JOIN gapto.movimientos_tesoreria m ON m.id = c.movimiento_tesoreria_id "
                         "WHERE h.id = %s", (hid,))[0]


# ------------------------------------------------------------------ CNC-18
@pytest.mark.parametrize("ausencia", ["OMITIDO", None, "", "   ", " " * 300])
def test_cnc18_ausencia_canonica_es_null_en_hecho_y_movimiento(tenant, ausencia):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta)
    cuerpo = _sin(cuerpo, "concepto") if ausencia == "OMITIDO" else {**cuerpo, "concepto": ausencia}
    r = h.cliente(owner).post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert _concepto_y_descripcion(owner, uuid.UUID(cuerpo["intencion_id"])) == (None, None)


def test_cnc18_texto_recortado_y_max_length_sobre_el_normalizado(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta, concepto="  Cena con Ana  ")
    assert cli.post(GASTO, json=cuerpo, headers=h.AUTH).status_code == 200
    assert _concepto_y_descripcion(owner, uuid.UUID(cuerpo["intencion_id"])) == ("Cena con Ana", "Cena con Ana")
    # 200 letras rodeadas de espacios caben (se mide el valor normalizado); 201 no.
    ok = h.intencion(cuenta, concepto="  " + "a" * 200 + "  ")
    assert cli.post(GASTO, json=ok, headers=h.AUTH).status_code == 200
    largo = h.intencion(cuenta, concepto="a" * 201)
    r = cli.post(GASTO, json=largo, headers=h.AUTH)
    assert r.status_code == 422
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (uuid.UUID(largo["intencion_id"]),))[0][0] == 0


def test_cnc18_tipo_no_textual_sigue_siendo_422(tenant):
    owner, _, cuenta = tenant
    r = h.cliente(owner).post(GASTO, json=h.intencion(cuenta, concepto=5), headers=h.AUTH)
    assert r.status_code == 422


# ------------------------------------------------------------------ CNC-19
def test_cnc19_blanco_y_omitido_son_la_misma_intencion_idempotente(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = _sin(h.intencion(cuenta), "concepto")
    r1 = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    r2 = cli.post(GASTO, json={**cuerpo, "concepto": "   "}, headers=h.AUTH)
    r3 = cli.post(GASTO, json={**cuerpo, "concepto": None}, headers=h.AUTH)
    assert [r.status_code for r in (r1, r2, r3)] == [200, 200, 200]
    assert [r.json()["idempotente"] for r in (r1, r2, r3)] == [False, True, True]
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (uuid.UUID(cuerpo["intencion_id"]),))[0][0] == 1


@pytest.mark.parametrize("primero,segundo", [(None, "Cena"), ("Cena", None), ("Cena", "Comida")])
def test_cnc19_null_frente_a_concepto_real_es_identidad_reutilizada(tenant, primero, segundo):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta, concepto=primero)
    assert cli.post(GASTO, json=cuerpo, headers=h.AUTH).status_code == 200
    r = cli.post(GASTO, json={**cuerpo, "concepto": segundo}, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", r.text
    # Nunca completado silencioso: el concepto persistido es el del primer envio.
    assert _concepto_y_descripcion(owner, uuid.UUID(cuerpo["intencion_id"]))[0] == primero


# ------------------------------------------------------------------ CNC-01/02/04/05/06 y CNC-03/07
def _tercero(owner) -> uuid.UUID:
    cli = h.cliente(owner)
    tid = uuid.uuid4()
    r = cli.post("/v1/terceros", json={"id": str(tid), "nombre": f"ALDI {tid.hex[:6]}", "naturaleza": "EMPRESA"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return tid


@pytest.mark.parametrize("con_tercero,con_categoria", [(True, True), (False, True), (True, False), (False, False)])
def test_cnc01_04_05_06_gasto_sin_concepto_con_descripcion_estructurada(tenant, con_tercero, con_categoria):
    owner, _, cuenta = tenant
    extra: dict = {}
    if con_tercero:
        extra["tercero_id"] = str(_tercero(owner))
    if con_categoria:
        extra["categoria"] = {"estado": "CATEGORIA", "categoria_id": str(fh.crear_categoria(owner, f"Super {uuid.uuid4().hex[:6]}", "GASTO"))}
    cuerpo = _sin(h.intencion(cuenta, **extra), "concepto")
    r = h.cliente(owner).post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["estado_categorial"] == ("CATEGORIA" if con_categoria else "SIN_CATEGORIA")
    assert _concepto_y_descripcion(owner, uuid.UUID(cuerpo["intencion_id"])) == (None, None)


def test_cnc03_07_concepto_util_se_conserva_junto_a_la_estructura(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Restaurantes {uuid.uuid4().hex[:6]}", "GASTO")
    cuerpo = h.intencion(cuenta, concepto=" Cumpleaños de Lucía ", tercero_id=str(_tercero(owner)),
                         categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    assert h.cliente(owner).post(GASTO, json=cuerpo, headers=h.AUTH).status_code == 200
    assert _concepto_y_descripcion(owner, uuid.UUID(cuerpo["intencion_id"])) == ("Cumpleaños de Lucía", "Cumpleaños de Lucía")


# ------------------------------------------------------------------ CNC-16/17
def test_cnc16_17_concepto_historico_intacto(tenant):
    owner, _, cuenta = tenant
    cli = h.cliente(owner)
    historico = h.intencion(cuenta, concepto="Factura luz octubre (V3)")
    assert cli.post(GASTO, json=historico, headers=h.AUTH).status_code == 200
    nuevo = _sin(h.intencion(cuenta), "concepto")
    assert cli.post(GASTO, json=nuevo, headers=h.AUTH).status_code == 200
    assert _concepto_y_descripcion(owner, uuid.UUID(historico["intencion_id"])) == ("Factura luz octubre (V3)", "Factura luz octubre (V3)")
    assert _concepto_y_descripcion(owner, uuid.UUID(nuevo["intencion_id"])) == (None, None)


# ------------------------------------------------------------------ ingreso y transferencia
def test_nota_de_ingreso_y_transferencia_canonica_antes_de_max_length(tenant):
    owner, actor, cuenta = tenant
    cli = h.cliente(owner)
    base = {"importe": "10.00", "moneda": "EUR", "fecha_hecho": "2026-09-24"}
    ingreso = {**base, "intencion_id": str(uuid.uuid4()), "cuenta_id": str(cuenta), "presupuestable": False,
               "atribucion": "SIN_INDICAR", "categoria": {"estado": "SIN_CATEGORIA"}, "nota": " " * 300}
    r = cli.post(INGRESO, json=ingreso, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert h.leer(owner, "SELECT concepto FROM gapto.hechos_financieros WHERE id=%s", (uuid.UUID(ingreso["intencion_id"]),)) == [(None,)]
    otra = h.crear_cuenta(owner, [(actor, 100)])
    transf = {**base, "intencion_id": str(uuid.uuid4()), "cuenta_origen_id": str(cuenta), "cuenta_destino_id": str(otra), "nota": "  "}
    r = cli.post(TRANSFERENCIA, json=transf, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert h.leer(owner, "SELECT concepto FROM gapto.hechos_financieros WHERE id=%s", (uuid.UUID(r.json()["hecho_id"]),)) == [(None,)]


# ------------------------------------------------------------------ AJ-RLOCALE-03
def _dsn_con_lc(base: str, lc: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options={urllib.parse.quote(f'-c lc_messages={lc}')}"


def test_aj_rlocale03_forma_funcional_del_error_igual_en_c_y_es_es(monkeypatch):
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        puede = c.execute("SELECT r.rolsuper OR has_parameter_privilege(current_user, 'lc_messages', 'SET') "
                          "FROM pg_roles r WHERE r.rolname = current_user").fetchone()[0]
    if not puede:
        pytest.skip("R-LOCALE: el rol de conexion no puede fijar lc_messages (parametro de superusuario)")
    base = h.dsn()
    respuestas = {}
    for lc in ("C", "es_ES"):
        monkeypatch.setenv("GAPTO_TEST_DATABASE_URL", _dsn_con_lc(base, lc))
        owner, actor = h.crear_tenant()
        cuenta_usd = h.crear_cuenta(owner, [(actor, 100)], moneda="USD")
        r = h.cliente(owner).post(GASTO, json=_sin(h.intencion(cuenta_usd), "concepto"), headers=h.AUTH)
        respuestas[lc] = (r.status_code, r.json())
    esperado = (422, {"codigo": "MONEDA_INVALIDA", "mensaje": "La cuenta debe estar en la misma moneda que el gasto.", "reintentable": False})
    assert respuestas["C"] == esperado, respuestas["C"]
    assert respuestas["es_ES"] == esperado, respuestas["es_ES"]
