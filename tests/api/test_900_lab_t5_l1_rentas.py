# ============================================================
# GAPTO MOBILE 2027 · LABORATORIO (rama lab-t5; no es implementacion de T5)
# Fichero: test_900_lab_t5_l1_rentas.py
# Ruta: tests/api/test_900_lab_t5_l1_rentas.py
# Descripcion: L1 · F06-04 Rentas (mandato MANDATO_F06-T5_LAB_v1.0). Reglas puras de `app.lab_rentas.dominio` con
#   los datos reales de las decisiones (ALLE 550 -> 561; SAAV 600 + garaje 50; FUEN 50/50) y la migracion de
#   laboratorio LAB_0357 (registro de revisiones y tope con receptor, versionados; historico sin UPDATE/DELETE;
#   RLS por owner). Discriminantes de los mutantes M-LAB-L1-01..06.
#   Los tests de base exigen GAPTO_TEST_DATABASE_URL apuntando al cluster DESECHABLE del laboratorio con LAB_0357.
# Version: 0.1.0 (LAB T5 · L1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal as D

import psycopg
import pytest

import f06_02_03_helpers as c
import vs01_api_helpers as h
from app.lab_rentas import dominio as d

F = dt.date


# ------------------------------------------------------------------ reglas puras
def test_r8_r14_calendario_medio_mes_y_nunca_despues_del_fin():
    cobros = d.calendario_cobros(F(2026, 3, 15), D("600"), hasta=F(2027, 12, 31), fin=F(2026, 6, 15))
    assert [(x.fecha, x.importe, x.medio_mes) for x in cobros] == [
        (F(2026, 3, 1), D("300.00"), True), (F(2026, 4, 1), D("600.00"), False),
        (F(2026, 5, 1), D("600.00"), False), (F(2026, 6, 1), D("300.00"), True)]                 # M-LAB-L1-01
    assert d.calendario_cobros(F(2026, 1, 1), D("561"), hasta=F(2026, 12, 31), fin=F(2026, 7, 1))[-1].fecha == F(2026, 6, 1)
    assert len(d.calendario_cobros(F(2026, 1, 1), D("561"), hasta=F(2026, 12, 31))) == 12          # sin fin: hasta el horizonte
    with pytest.raises(d.ReglaRenta):
        d.calendario_cobros(F(2026, 1, 10), D("500"), hasta=F(2026, 3, 1))                          # R8: solo 1 o 15


def test_r5_alle_550_a_561_y_redondeo_a_la_baja():
    p = d.proponer_revision(D("550"), D("2"))
    assert (p.exacta, p.propuesta) == (D("561.0000"), D("561"))
    q = d.proponer_revision(D("561"), D("2.8"))                                                     # 576,708 -> 576
    assert (q.exacta, q.propuesta) == (D("576.7080"), D("576"))                                    # M-LAB-L1-02


def test_r6_tope_saav_vivienda_con_receptor_garaje():
    r = d.aplicar_tope(D("600"), D("640"), D("50"), D("51"), D("5"))
    assert (r.renta_contrato, r.renta_receptor, r.exceso) == (D("632.50"), D("58.50"), D("7.50"))   # M-LAB-L1-03
    assert r.renta_contrato + r.renta_receptor == D("640") + D("51")                                # el total no cambia
    s = d.aplicar_tope(D("600"), D("612"), D("50"), D("51"), D("5"))
    assert s.exceso == D("0.00") and s.renta_contrato == D("612")


def test_r10_r11_avisos_y_aviso_tardio():
    assert d.avisos(F(2026, 9, 1)) == (F(2026, 7, 1), F(2026, 8, 1))
    assert d.fecha_efecto(F(2026, 9, 1), F(2026, 8, 1)) == F(2026, 9, 1)                          # aviso a tiempo
    assert d.fecha_efecto(F(2026, 9, 1), F(2026, 8, 10)) == F(2026, 10, 1)                         # «pasariamos a octubre»
    assert d.fecha_efecto(F(2026, 9, 1), F(2026, 6, 1)) == F(2026, 9, 1)                           # nunca antes del aniversario  M-LAB-L1-04


def test_r14b_prorroga_y_limites():
    assert d.prorrogar_un_anio(F(2026, 6, 15)) == F(2027, 6, 15)
    assert d.limites_legales(F(2024, 9, 1)) == (F(2029, 9, 1), F(2032, 9, 1))
    assert d.antiguedad_meses(F(2024, 9, 1), F(2026, 11, 23)) == 26


def test_r7_fuen_reparto_por_participacion_exacto():
    r = d.repartir(D("348.01"), {"yo": D("50"), "simon": D("50")})
    assert sum(r.values()) == D("348.01") and sorted(r.values()) == [D("174.00"), D("174.01")]       # M-LAB-L1-05
    with pytest.raises(d.ReglaRenta):
        d.repartir(D("100"), {"yo": D("60")})


def test_r4b_r15_diferencias():
    assert d.pendiente_por_renta_antigua(D("550"), D("561")) == D("11.00")
    assert d.pendiente_por_renta_antigua(D("561"), D("561")) == D("0.00")
    assert d.perdonar_lo_que_falta(D("561"), D("500")) == D("61.00")


def test_r16_r18_r10_tareas():
    t = d.tareas_contrato("ALLE", tipo_revision=None, renta_registrada=True, renta_completa=False, aniversario=None, hoy=F(2026, 11, 23))
    assert [x.clave for x in t] == ["INDICAR_REVISION", "COMPLETAR_RENTA"]
    t = d.tareas_contrato("ALLE", tipo_revision="IPC", renta_registrada=True, renta_completa=True, aniversario=F(2026, 9, 1), hoy=F(2026, 8, 5))
    assert [(x.clave, x.fecha) for x in t] == [("REVISAR_RENTA", F(2026, 8, 1))]
    assert d.tareas_contrato("ALLE", tipo_revision="IPC", renta_registrada=True, renta_completa=True,
                             aniversario=F(2026, 9, 1), hoy=F(2026, 6, 30)) == []                    # antes del primer aviso  M-LAB-L1-06


# ------------------------------------------------------------------ LAB_0357 (base del laboratorio)
@pytest.fixture()
def con():
    owner, actor, cli = c.entorno()
    prop = c.propiedad(cli, habitaciones=None)
    inq = c.tercero(cli, "Inquilina ALLE")
    k1 = c.crear_firmado(cli, prop, inq, tipo="VIVIENDA_COMPLETA", habitacion=None)
    prop2 = c.propiedad(cli, habitaciones=None, nombre="Garaje")
    k2 = c.crear_firmado(cli, prop2, inq, tipo="VIVIENDA_COMPLETA", habitacion=None)
    return owner, uuid.UUID(k1["id"]), uuid.UUID(k2["id"])


def _runtime(owner):
    x = psycopg.connect(h.dsn())
    x.execute("SET ROLE gapto_runtime")
    x.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
    return x


def test_revision_registrada_es_historico_y_el_redondeo_no_puede_subir(con):
    owner, k1, _ = con
    with _runtime(owner) as x:
        x.execute("INSERT INTO gapto.lab_renta_revisiones (contrato_entidad_id, aniversario, renta_anterior, indice_texto, "
                  "indice_porcentaje, renta_exacta, renta_propuesta, decision, renta_aplicada, aviso_primero, aviso_segundo) "
                  "VALUES (%s, '2026-09-01', 550, 'IPC INE', 2, 561.0000, 561, 'APLICADA', 561, '2026-07-01', '2026-08-01')", (k1,))
        x.commit()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("UPDATE gapto.lab_renta_revisiones SET renta_aplicada = 600")
        x.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("DELETE FROM gapto.lab_renta_revisiones")
        x.rollback()
        with pytest.raises(psycopg.errors.CheckViolation):
            x.execute("INSERT INTO gapto.lab_renta_revisiones (contrato_entidad_id, aniversario, renta_anterior, renta_exacta, "
                      "renta_propuesta, decision, renta_aplicada) VALUES (%s, '2027-09-01', 561, 576.7080, 577, 'APLICADA', 577)", (k1,))
        x.rollback()
        with pytest.raises(psycopg.errors.UniqueViolation):                      # un registro por aniversario
            x.execute("INSERT INTO gapto.lab_renta_revisiones (contrato_entidad_id, aniversario, renta_anterior, decision) "
                      "VALUES (%s, '2026-09-01', 550, 'NO_APLICADA')", (k1,))
        x.rollback()
        x.execute("INSERT INTO gapto.lab_renta_revisiones (contrato_entidad_id, aniversario, renta_anterior, decision, motivo) "
                  "VALUES (%s, '2027-09-01', 561, 'NO_APLICADA', 'No aplicar este año')", (k1,))  # R4-A registrado
        x.commit()


def test_tope_versionado_sin_solapes_y_receptor_del_mismo_owner(con):
    owner, k1, k2 = con
    with _runtime(owner) as x:
        x.execute("INSERT INTO gapto.lab_contrato_topes (contrato_entidad_id, receptor_contrato_entidad_id, porcentaje_tope, "
                  "vigente_desde, vigente_hasta) VALUES (%s, %s, 5, '2025-03-01', '2026-02-28')", (k1, k2))
        x.execute("INSERT INTO gapto.lab_contrato_topes (contrato_entidad_id, receptor_contrato_entidad_id, porcentaje_tope, "
                  "vigente_desde) VALUES (%s, %s, 4, '2026-03-01')", (k1, k2))
        x.commit()
        with pytest.raises(psycopg.errors.ExclusionViolation):
            x.execute("INSERT INTO gapto.lab_contrato_topes (contrato_entidad_id, receptor_contrato_entidad_id, porcentaje_tope, "
                      "vigente_desde) VALUES (%s, %s, 3, '2026-06-01')", (k1, k2))
        x.rollback()
    otro, _, _ = c.entorno()
    with _runtime(otro) as y:                                                    # RLS: otro owner no ve nada
        assert y.execute("SELECT count(*) FROM gapto.lab_contrato_topes").fetchone()[0] == 0
        assert y.execute("SELECT count(*) FROM gapto.lab_renta_revisiones").fetchone()[0] == 0


# ------------------------------------------------------------------ rutas /v1/lab (marca «LAB»)
def test_rutas_lab_calendario_propuesta_revision_y_tope():
    owner, actor, cli = c.entorno()
    prop = c.propiedad(cli, habitaciones=None)
    inq = c.tercero(cli, "Inquilina SAAV")
    k1 = c.crear_firmado(cli, prop, inq, tipo="VIVIENDA_COMPLETA", habitacion=None)["id"]
    k2 = c.crear_firmado(cli, c.propiedad(cli, habitaciones=None, nombre="Garaje SAAV"), inq, tipo="VIVIENDA_COMPLETA", habitacion=None)["id"]
    r = cli.get(f"/v1/lab/contratos/{k1}/renta/calendario?inicio=2025-03-01&renta=600&hasta=2025-05-31", headers=h.AUTH)
    assert r.status_code == 200 and r.json()["marca"] == "LAB" and [x["importe"] for x in r.json()["cobros"]] == ["600.00"] * 3
    r = cli.get("/v1/lab/renta/propuesta-revision?renta_anterior=550&porcentaje=2&aniversario=2026-09-01&fecha_aviso=2026-08-10", headers=h.AUTH)
    assert r.json()["propuesta"] == "561" and r.json()["efecto"] == "2026-10-01"
    cuerpo = {"aniversario": "2026-03-01", "renta_anterior": "600", "indice_texto": "IPC INE", "indice_porcentaje": "2",
              "decision": "APLICADA", "renta_aplicada": "612"}
    r = cli.post(f"/v1/lab/contratos/{k1}/revisiones", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["revision"]["renta_propuesta"] == "612"
    assert cli.post(f"/v1/lab/contratos/{k1}/revisiones", json=cuerpo, headers=h.AUTH).status_code == 409
    r = cli.post(f"/v1/lab/contratos/{k1}/revisiones", json={"aniversario": "2027-03-01", "renta_anterior": "612",
                                                             "decision": "NO_APLICADA", "motivo": "No aplicar este año"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    for desde, pct in (("2025-03-01", "5"), ("2026-03-01", "4")):
        r = cli.post(f"/v1/lab/contratos/{k1}/tope", json={"receptor_contrato_id": k2, "porcentaje_tope": pct, "vigente_desde": desde}, headers=h.AUTH)
        assert r.status_code == 200, r.text
    filas = h.leer(owner, "SELECT porcentaje_tope, vigente_desde, vigente_hasta FROM gapto.lab_contrato_topes ORDER BY vigente_desde")
    assert [(str(D(p).normalize()), str(a), str(b)) for p, a, b in filas] == [("5", "2025-03-01", "2026-02-28"), ("4", "2026-03-01", "None")]
