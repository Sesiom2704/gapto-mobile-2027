# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_185_f05_05_senales.py
# Ruta: tests/api/test_185_f05_05_senales.py
# Descripcion: Senales de F05-05 (K2 §1.2; F05 §49.4 A1/A2/A4/A6, §49.5
#   R1-R8). Dominio SENALES. Casos de §49.9: 1 (afinidad primero, motivo
#   AFINIDAD), 2 (orden por historial con el tercero), 4 (afinidad hacia
#   categoria deshabilitada o incompatible no se sugiere), 5 (tercero
#   desactivado y reactivado: sus afinidades vuelven a contar), 18 (IDs
#   ajenos), 19/R7 (ventana (f-365, f] por la fecha recibida), 20 (mismas
#   entradas, mismo orden) y empate (nombre normalizado, id).
#   Ademas: «Recientes» de terceros (RECIENTE en 7 dias, despues frecuencia),
#   RECIENTE como motivo del primero del tipo, FECHA_FUTURA, tipo invalido y
#   lectura sin escritura (R5).
# Version: 0.1.0 (F05-05 K2 §1.2)
# Version: 0.2.0 (F05-05 K3 §3, mutantes SE03/SE05/SE06/SE09/SE14): hechos
#   anulados fuera; frecuencia por HECHO (no por efecto); desempate por
#   recencia antes que por nombre (R6); nunca mas de 3 tambien con el bloque
#   del tercero; «Recientes» por recencia y no por uso (R4).
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import pytest

import f05_05_helpers as x
import vs01_api_helpers as h

URL_CAT = "/v1/senales/categorias"
URL_TER = "/v1/senales/terceros"


def senales(cli, tipo="GASTO", tercero=None, fecha="2026-10-10"):
    params = {"tipo": tipo, "fecha": fecha}
    if tercero:
        params["tercero_id"] = str(tercero)
    r = cli.get(URL_CAT, params=params, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return [(c["nombre"], c["motivo"]) for c in r.json()["candidatas"]], r.json()


@pytest.fixture()
def e():
    owner, actor, cli, corriente, ahorro = x.entorno()
    return owner, cli, corriente, ahorro


def test_caso1_afinidad_primero_con_su_motivo(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    super_, hogar = x.categoria(owner, "Supermercados"), x.categoria(owner, "Hogar")
    for _ in range(3):
        x.gasto(cli, cta, categoria_id=hogar, tercero_id=aldi)
    r = cli.post("/v1/afinidades", json={"id": str(uuid.uuid4()), "tercero_id": str(aldi), "categoria_id": str(super_)},
                 headers=h.AUTH)
    assert r.status_code == 200, r.text
    obtenido, cuerpo = senales(cli, tercero=aldi)
    assert obtenido[0] == ("Supermercados", "AFINIDAD")
    assert obtenido[1] == ("Hogar", "FRECUENTE_TERCERO")
    assert cuerpo["candidatas"][0]["fuente"] == "AFINIDAD" and cuerpo["candidatas"][1]["fuente"] == "HISTORIAL"


def test_caso2_orden_por_historial_con_el_tercero(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    super_, hogar = x.categoria(owner, "Supermercados"), x.categoria(owner, "Hogar")
    for _ in range(5):
        x.gasto(cli, cta, categoria_id=super_, tercero_id=aldi, fecha="2026-09-01")
    x.gasto(cli, cta, categoria_id=hogar, tercero_id=aldi, fecha="2026-10-09")  # mas reciente, menos frecuente
    obtenido, cuerpo = senales(cli, tercero=aldi)
    assert obtenido[:2] == [("Supermercados", "FRECUENTE_TERCERO"), ("Hogar", "FRECUENTE_TERCERO")]
    assert cuerpo["candidatas"][0]["usos"] == 5 and cuerpo["candidatas"][0]["ultimo_uso"] == "2026-09-01"


def test_completa_con_el_tipo_y_reciente_como_motivo_del_primero(e):
    """Con tercero: afinidades, despues su historial y, para completar hasta 3,
    el historial del tipo; el primero de ese bloque lleva RECIENTE si es de los
    ultimos 7 dias (lamina A1, R4)."""
    owner, cli, cta, _ = e
    aldi, otro = x.tercero(cli, "ALDI"), x.tercero(cli, "Bar Paco")
    a, b, c = x.categoria(owner, "Supermercados"), x.categoria(owner, "Restaurantes"), x.categoria(owner, "Cine")
    x.gasto(cli, cta, categoria_id=a, tercero_id=aldi)
    x.gasto(cli, cta, categoria_id=b, tercero_id=otro, fecha="2026-10-08")
    for _ in range(4):
        x.gasto(cli, cta, categoria_id=c, tercero_id=otro, fecha="2026-06-01")
    obtenido, _ = senales(cli, tercero=aldi)
    assert obtenido == [("Supermercados", "FRECUENTE_TERCERO"), ("Cine", "FRECUENTE_TIPO"),
                        ("Restaurantes", "FRECUENTE_TIPO")]
    x.gasto(cli, cta, categoria_id=c, tercero_id=otro, fecha="2026-10-09")  # Cine pasa a reciente
    obtenido, _ = senales(cli, tercero=aldi)
    assert obtenido[1] == ("Cine", "RECIENTE") and obtenido[2] == ("Restaurantes", "FRECUENTE_TIPO")


def test_sin_tercero_frecuente_en_el_tipo_y_reciente_solo_para_el_primero(e):
    owner, cli, cta, _ = e
    a, b = x.categoria(owner, "Supermercados"), x.categoria(owner, "Farmacia")
    for _ in range(3):
        x.gasto(cli, cta, categoria_id=a, fecha="2026-08-01")
    x.gasto(cli, cta, categoria_id=b, fecha="2026-10-09")
    obtenido, _ = senales(cli)
    assert obtenido == [("Supermercados", "FRECUENTE_TIPO"), ("Farmacia", "FRECUENTE_TIPO")]
    for _ in range(3):
        x.gasto(cli, cta, categoria_id=b, fecha="2026-10-09")
    obtenido, _ = senales(cli)
    assert obtenido == [("Farmacia", "RECIENTE"), ("Supermercados", "FRECUENTE_TIPO")]


def test_caso4_deshabilitada_e_incompatible_no_se_sugieren(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    super_, limpieza = x.categoria(owner, "Supermercados"), x.categoria(owner, "Limpieza")
    nomina = x.categoria(owner, "Nómina", "INGRESO")
    for cid in (super_, limpieza):
        r = cli.post("/v1/afinidades", json={"id": str(uuid.uuid4()), "tercero_id": str(aldi), "categoria_id": str(cid)},
                     headers=h.AUTH)
        assert r.status_code == 200
    x.ingreso(cli, cta, categoria_id=nomina, tercero_id=aldi)
    x.desactivar_categoria(owner, limpieza)
    obtenido, _ = senales(cli, tercero=aldi)
    assert ("Limpieza", "AFINIDAD") not in obtenido and ("Supermercados", "AFINIDAD") in obtenido
    assert all(n != "Nómina" for n, _ in obtenido)  # ambito INGRESO en un gasto
    obtenido, _ = senales(cli, tipo="INGRESO", tercero=aldi)
    assert obtenido == [("Nómina", "FRECUENTE_TERCERO")]  # GASTO no se sugiere en un ingreso


def test_ambos_vale_para_gasto_e_ingreso(e):
    owner, cli, cta, _ = e
    ambos = x.categoria(owner, "Regalos", "AMBOS")
    x.gasto(cli, cta, categoria_id=ambos)
    x.ingreso(cli, cta, categoria_id=ambos)
    assert senales(cli)[0] == [("Regalos", "RECIENTE")]
    assert senales(cli, tipo="INGRESO")[0] == [("Regalos", "RECIENTE")]


def test_caso5_tercero_desactivado_y_reactivado(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    super_ = x.categoria(owner, "Supermercados")
    assert cli.post("/v1/afinidades", json={"id": str(uuid.uuid4()), "tercero_id": str(aldi),
                    "categoria_id": str(super_)}, headers=h.AUTH).status_code == 200
    x.desactivar_tercero(cli, aldi)
    x.reactivar_tercero(cli, aldi)
    assert senales(cli, tercero=aldi)[0][0] == ("Supermercados", "AFINIDAD")


def test_r7_ventana_semiabierta_por_la_fecha_recibida(e):
    owner, cli, cta, _ = e
    dentro, fuera = x.categoria(owner, "Dentro"), x.categoria(owner, "Fuera")
    x.gasto(cli, cta, categoria_id=fuera, fecha="2025-10-10")  # f - 365: excluido
    x.gasto(cli, cta, categoria_id=dentro, fecha="2025-10-11")  # f - 364: incluido
    assert senales(cli, fecha="2026-10-10")[0] == [("Dentro", "FRECUENTE_TIPO")]
    assert senales(cli, fecha="2026-10-09")[0] == [("Dentro", "FRECUENTE_TIPO"), ("Fuera", "FRECUENTE_TIPO")]
    # un hecho posterior a la fecha funcional no cuenta
    assert senales(cli, fecha="2025-10-10")[0] == [("Fuera", "RECIENTE")]


def test_caso20_determinismo_y_empate_por_nombre_normalizado_e_id(e):
    owner, cli, cta, _ = e
    b, a, a2 = x.categoria(owner, "Beta"), x.categoria(owner, "Álamo"), x.categoria(owner, "alamo")
    for cid in (b, a, a2):
        x.gasto(cli, cta, categoria_id=cid, fecha="2026-09-01")
    primera = cli.get(URL_CAT, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH).json()
    segunda = cli.get(URL_CAT, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH).json()
    assert primera == segunda
    nombres = [c["nombre"] for c in primera["candidatas"]]
    alamos = sorted([(a, "Álamo"), (a2, "alamo")], key=lambda p: str(p[0]))
    assert nombres == [alamos[0][1], alamos[1][1], "Beta"]  # «álamo» == «alamo» en C06 -> manda el id


def test_hasta_tres_candidatas(e):
    owner, cli, cta, _ = e
    for i in range(5):
        x.gasto(cli, cta, categoria_id=x.categoria(owner, f"C{i}"), fecha="2026-09-01")
    assert len(senales(cli)[0]) == 3


def test_terceros_recientes_primero_los_de_7_dias_despues_frecuencia(e):
    owner, cli, cta, _ = e
    aldi, merca, iber, viejo = (x.tercero(cli, n) for n in ("ALDI", "Mercadona", "Iberdrola", "Viejo"))
    x.gasto(cli, cta, tercero_id=aldi, fecha="2026-10-08")
    x.gasto(cli, cta, tercero_id=merca, fecha="2026-10-05")
    for _ in range(3):
        x.gasto(cli, cta, tercero_id=iber, fecha="2026-08-01")
    x.gasto(cli, cta, tercero_id=viejo, fecha="2025-01-01")  # fuera de la ventana
    r = cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH)
    assert r.status_code == 200
    assert [(t["nombre"], t["motivo"]) for t in r.json()["terceros"]] == [
        ("ALDI", "RECIENTE"), ("Mercadona", "RECIENTE"), ("Iberdrola", "FRECUENTE_TIPO")]


def test_terceros_recientes_excluye_inactivos_y_limita_a_cinco(e):
    owner, cli, cta, _ = e
    ids = [x.tercero(cli, f"T{i}") for i in range(7)]
    for tid in ids:
        x.gasto(cli, cta, tercero_id=tid)
    x.desactivar_tercero(cli, ids[0])
    r = cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH).json()
    assert len(r["terceros"]) == 5 and str(ids[0]) not in {t["tercero_id"] for t in r["terceros"]}


def test_caso18_tercero_ajeno_rechazado_y_datos_ajenos_invisibles(e):
    owner, cli, cta, _ = e
    owner_b, _, cli_b, cta_b, _ = x.entorno()
    ter_b = x.tercero(cli_b, "Ajeno")
    x.gasto(cli_b, cta_b, categoria_id=x.categoria(owner_b, "De B"), tercero_id=ter_b)
    r = cli.get(URL_CAT, params={"tipo": "GASTO", "fecha": "2026-10-10", "tercero_id": str(ter_b)}, headers=h.AUTH)
    assert r.status_code == 404 and r.json()["codigo"] == "TERCERO_NO_ENCONTRADO"
    assert senales(cli)[0] == []
    assert cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH).json()["terceros"] == []


def test_fecha_futura_y_tipo_invalido(e):
    _, cli, _, _ = e
    r = cli.get(URL_CAT, params={"tipo": "GASTO", "fecha": "2026-10-11"}, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    r = cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-11"}, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    assert cli.get(URL_CAT, params={"tipo": "DEUDA", "fecha": "2026-10-10"}, headers=h.AUTH).status_code == 422
    assert cli.get(URL_CAT, params={"tipo": "GASTO"}, headers=h.AUTH).status_code == 422  # fecha obligatoria


def test_r5_la_lectura_no_escribe(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    x.gasto(cli, cta, categoria_id=x.categoria(owner, "Supermercados"), tercero_id=aldi)
    antes = h.leer(owner, "SELECT row_version FROM gapto.terceros WHERE id=%s", (aldi,))
    auditorias = h.leer(owner, "SELECT count(*) FROM gapto.auditoria")
    senales(cli, tercero=aldi)
    cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH)
    assert h.leer(owner, "SELECT row_version FROM gapto.terceros WHERE id=%s", (aldi,)) == antes
    assert h.leer(owner, "SELECT count(*) FROM gapto.auditoria") == auditorias


# ------------------------------------------------------------------ K3 §3: refuerzo (mutantes)
def test_hechos_anulados_no_cuentan_como_uso(e):
    owner, cli, cta, _ = e
    a, b = x.categoria(owner, "Anulada"), x.categoria(owner, "Vigente")
    for _ in range(2):
        x.anular(owner, x.gasto(cli, cta, categoria_id=a, fecha="2026-10-08"))
    x.gasto(cli, cta, categoria_id=b, fecha="2026-09-01")
    obtenido, _ = senales(cli)
    assert [n for n, _ in obtenido] == ["Vigente"]


def test_frecuencia_por_hecho_y_no_por_efecto():
    """Un hecho con dos efectos de la misma categoria es UN uso: 2 hechos de B
    van antes que 1 hecho (mas reciente) con dos efectos de A."""
    owner, actor, cli, cta, _ = x.entorno()
    a, b = x.categoria(owner, "Alfa"), x.categoria(owner, "Beta")
    x.hecho_motor(owner, [("GASTO", "5.00", "COMPLETA", a, [(actor, "5.00")]),
                          ("GASTO", "6.00", "COMPLETA", a, [(actor, "6.00")])], fecha="2026-10-09")
    for _ in range(2):
        x.gasto(cli, cta, categoria_id=b, fecha="2026-09-01")
    obtenido, cuerpo = senales(cli)
    assert [n for n, _ in obtenido] == ["Beta", "Alfa"]
    assert [c["usos"] for c in cuerpo["candidatas"]] == [2, 1]


def test_desempate_por_recencia_antes_que_por_nombre(e):
    owner, cli, cta, _ = e
    a, z = x.categoria(owner, "Aaa"), x.categoria(owner, "Zzz")
    x.gasto(cli, cta, categoria_id=a, fecha="2026-08-01")
    x.gasto(cli, cta, categoria_id=z, fecha="2026-09-01")  # misma frecuencia, mas reciente
    obtenido, _ = senales(cli)
    assert [n for n, _ in obtenido] == ["Zzz", "Aaa"]


def test_con_tercero_nunca_mas_de_tres(e):
    owner, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    for i, nombre in enumerate(["Uno", "Dos", "Tres", "Cuatro"]):
        cat = x.categoria(owner, nombre)
        for _ in range(4 - i):
            x.gasto(cli, cta, categoria_id=cat, tercero_id=aldi, fecha="2026-09-01")
    obtenido, _ = senales(cli, tercero=aldi)
    assert [n for n, _ in obtenido] == ["Uno", "Dos", "Tres"]


def test_recientes_por_recencia_y_no_por_uso(e):
    owner, cli, cta, _ = e
    mucho, ayer = x.tercero(cli, "Mucho uso"), x.tercero(cli, "Usado ayer")
    for _ in range(3):
        x.gasto(cli, cta, tercero_id=mucho, fecha="2026-10-05")
    x.gasto(cli, cta, tercero_id=ayer, fecha="2026-10-09")
    r = cli.get(URL_TER, params={"tipo": "GASTO", "fecha": "2026-10-10"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert [(t["nombre"], t["motivo"]) for t in r.json()["terceros"]] == [("Usado ayer", "RECIENTE"), ("Mucho uso", "RECIENTE")]
