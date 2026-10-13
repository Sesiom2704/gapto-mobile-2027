# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_194_f05_06_m4_concurrencia_serial.py
# Ruta: tests/api/test_194_f05_06_m4_concurrencia_serial.py
# Descripcion: Concurrencia del writer de capacidades (F05-06 M4 §4.3; F05
#   §51.4 AJ-F0506P-09; F05 §46.4 R4; PD-1). Bateria SERIAL y determinista,
#   FUERA de la suite general (como test_190): solo con
#   GAPTO_M4_CONCURRENCIA=1. Reutiliza el arnes de test_190 (_serie,
#   _barrera_fila, _barrera_advisory, _nowait): una sesion BARRERA retiene un
#   lock, los comandos se lanzan uno a uno y cada uno debe quedar esperando
#   antes del siguiente; al liberar, PostgreSQL concede en orden de llegada.
#   Si GAPTO_J2J3_EVIDENCIA apunta a una carpeta, cada escenario deja alli su
#   JSON (pg_locks y resultados).
#   Escenarios, en los DOS ordenes:
#     (a) desactivar PAGAR_GASTO frente a confirmar un gasto con esa cuenta;
#     (b) activar RECIBIR_INGRESO frente a confirmar un ingreso;
#     (c) desactivar TRANSFERIR_SALIDA frente a OP-10;
#     (d) desactivar PAGAR_GASTO frente a guardar una plantilla y una
#         preferencia con esa cuenta: NO comparten lock (cada uno avanza
#         mientras el otro espera su barrera) y el resultado depende solo
#         del orden de COMMIT;
#     (e) dos writers sobre la misma cuenta: gana el primero; el segundo
#         recibe VERSION_DESFASADA sin escribir.
#   En todos: ningun 40P01 (ni reintento de la UnidadDeTrabajo ni aumento de
#   pg_stat_database.deadlocks) y nada parcial.
# Version: 0.1.0 (F05-06 M4 F3)
# ============================================================

from __future__ import annotations

import logging
import os
import time
import uuid

import psycopg
import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h
from test_190_f05_j2j3_concurrencia_serial import _barrera_advisory, _barrera_fila, _cod, _nowait, _serie

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_M4_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_M4_CONCURRENCIA=1)")
GASTO = "/v1/intenciones/gasto-pagado"
INGRESO = "/v1/intenciones/ingreso-cobrado"
TRANSF = "/v1/intenciones/transferencia"
FECHA = "2026-09-24"
CUENTA_FOR_UPDATE = "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE"
ORDENES = ["registro", "capacidad"]


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    nomina = h.crear_cuenta(owner, [(actor, 100)], capacidades=("PAGAR_GASTO", "TRANSFERIR_SALIDA"))
    ahorro = h.crear_cuenta(owner, [(actor, 100)], capacidades=("TRANSFERIR_ENTRADA",))
    return owner, actor, cli, nomina, ahorro


@pytest.fixture(autouse=True)
def sin_40p01(caplog):
    """Ningun deadlock: ni reintento de la UnidadDeTrabajo ni contador de la base."""
    caplog.set_level(logging.WARNING, logger="gapto.motor.transaccion")
    antes = _deadlocks()
    yield
    reintentos = [r for r in caplog.records if r.name == "gapto.motor.transaccion" and getattr(r, "sqlstate", None)]
    assert not reintentos, [(r.getMessage(), r.sqlstate) for r in reintentos]
    assert _deadlocks(espera=True) == antes


def _deadlocks(espera: bool = False) -> int:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        if espera:
            time.sleep(1.1)  # las estadisticas acumuladas se publican con retardo
            c.execute("SELECT pg_stat_clear_snapshot()")
        return c.execute("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()").fetchone()[0]


def _cambiar(cli, cuenta, capacidad, accion, row_version=1):
    return cli.post(f"/v1/cuentas/{cuenta}/capacidades/{capacidad}/{accion}", json={"row_version": row_version},
                    headers=h.AUTH)


def _caps(owner, cuenta):
    return [f[0] for f in h.leer(owner, "SELECT capacidad_codigo FROM gapto.cuenta_capacidades WHERE cuenta_id=%s "
                                        "ORDER BY capacidad_codigo", (cuenta,))]


def _hechos(owner, intencion_id):
    return h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (uuid.UUID(intencion_id),))[0][0]


def _auditorias(owner, cuenta):
    return h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla='cuentas' AND registro_id=%s", (cuenta,))[0][0]


def _en_orden(primero: str, pasos: dict) -> list:
    otro = next(k for k in pasos if k != primero)
    return [(primero, pasos[primero]), (otro, pasos[otro])]


# ------------------------------------------------------------------ (a) gasto
@pytest.mark.parametrize("primero", ORDENES)
def test_a_desactivar_pagar_gasto_frente_a_gasto(t, primero):
    owner, _, cli, nomina, _ = t
    cuerpo = h.intencion(nomina)
    barrera = _barrera_fila(owner, CUENTA_FOR_UPDATE, (nomina,))
    pasos = {"registro": lambda: cli.post(GASTO, json=cuerpo, headers=h.AUTH),
             "capacidad": lambda: _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar")}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M4_a_{primero}")
    assert salida["capacidad"].status_code == 200, salida["capacidad"].text
    assert _caps(owner, nomina) == ["TRANSFERIR_SALIDA"] and _auditorias(owner, nomina) == 1
    if primero == "registro":
        assert salida["registro"].status_code == 200 and _hechos(owner, cuerpo["intencion_id"]) == 1
    else:
        assert (salida["registro"].status_code, _cod(salida["registro"])) == (409, "CUENTA_SIN_CAPACIDAD")
        assert _hechos(owner, cuerpo["intencion_id"]) == 0


# ------------------------------------------------------------------ (b) ingreso
@pytest.mark.parametrize("primero", ORDENES)
def test_b_activar_recibir_ingreso_frente_a_ingreso(t, primero):
    owner, _, cli, nomina, _ = t
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": FECHA,
              "cuenta_id": str(nomina), "presupuestable": True, "atribucion": "SOLO_MIO",
              "categoria": {"estado": "SIN_CATEGORIA"}}
    barrera = _barrera_fila(owner, CUENTA_FOR_UPDATE, (nomina,))
    pasos = {"registro": lambda: cli.post(INGRESO, json=cuerpo, headers=h.AUTH),
             "capacidad": lambda: _cambiar(cli, nomina, "RECIBIR_INGRESO", "activar")}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M4_b_{primero}")
    assert salida["capacidad"].status_code == 200, salida["capacidad"].text
    assert "RECIBIR_INGRESO" in _caps(owner, nomina)
    if primero == "registro":
        assert (salida["registro"].status_code, _cod(salida["registro"])) == (409, "CUENTA_SIN_CAPACIDAD")
        assert _hechos(owner, cuerpo["intencion_id"]) == 0
    else:
        assert salida["registro"].status_code == 200 and _hechos(owner, cuerpo["intencion_id"]) == 1


# ------------------------------------------------------------------ (c) OP-10
@pytest.mark.parametrize("primero", ORDENES)
def test_c_desactivar_transferir_salida_frente_a_op10(t, primero):
    owner, _, cli, nomina, ahorro = t
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": FECHA,
              "cuenta_origen_id": str(nomina), "cuenta_destino_id": str(ahorro)}
    barrera = _barrera_fila(owner, CUENTA_FOR_UPDATE, (nomina,))
    pasos = {"registro": lambda: cli.post(TRANSF, json=cuerpo, headers=h.AUTH),
             "capacidad": lambda: _cambiar(cli, nomina, "TRANSFERIR_SALIDA", "desactivar")}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M4_c_{primero}")
    assert salida["capacidad"].status_code == 200, salida["capacidad"].text
    assert _caps(owner, nomina) == ["PAGAR_GASTO"]
    if primero == "registro":
        assert salida["registro"].status_code == 200 and _hechos(owner, cuerpo["intencion_id"]) == 1
    else:
        assert (salida["registro"].status_code, _cod(salida["registro"])) == (409, "CUENTA_SIN_CAPACIDAD")
        assert salida["registro"].json()["detalle"]["operacion"] == "TRANSFERENCIA_ORIGEN"
        assert _hechos(owner, cuerpo["intencion_id"]) == 0


# ------------------------------------------------------------------ (d) plantilla y preferencia
def _alta_plantilla(cli, tipos, cuenta, pid):
    return cli.post("/v1/plantillas", json={"id": str(pid), "nombre": f"Alquiler {pid}", "tipo_hecho_id": tipos["GASTO"],
                                            "cuenta_default_id": str(cuenta)}, headers=h.AUTH)


def _alta_preferencia(cli, cuenta, pid):
    return ph.alta(cli, pid=pid, cuenta_default_id=cuenta)[1]


@pytest.mark.parametrize("writer", ["plantilla", "preferencia"])
@pytest.mark.parametrize("primero", ["maestro", "capacidad"])
def test_d_desactivar_frente_a_plantilla_o_preferencia(t, writer, primero):
    """Sin lock comun: el que espera su barrera no bloquea al otro; al liberar,
    el resultado depende solo del orden de COMMIT."""
    owner, _, cli, nomina, _ = t
    tipos = cli.get("/v1/preferencias", headers=h.AUTH).json()["tipos"]
    pid = uuid.uuid4()
    alta = (lambda: _alta_plantilla(cli, tipos, nomina, pid)) if writer == "plantilla" else (
        lambda: _alta_preferencia(cli, nomina, pid))
    advisory = "PLANTILLAS" if writer == "plantilla" else "PREFERENCIAS"
    rechazo = "PLANTILLA_CUENTA_NO_ELEGIBLE" if writer == "plantilla" else "PREFERENCIA_CUENTA_NO_ELEGIBLE"
    if primero == "capacidad":
        # El alta espera su advisory; la desactivacion NO espera y confirma.
        barrera = _barrera_advisory(owner, advisory)
        r_cap = _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar")
        assert r_cap.status_code == 200, r_cap.text
        salida = _serie(barrera, [("maestro", alta)], f"M4_d_{writer}_capacidad_primero")
        assert (salida["maestro"].status_code, _cod(salida["maestro"])) == (409, rechazo)
    else:
        # La barrera toma la cuenta en el MISMO modo que el writer (NO KEY UPDATE): la
        # desactivacion espera; el alta NO espera (su FK pide KEY SHARE, compatible) y confirma.
        barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR NO KEY UPDATE", (nomina,))
        r_alta = alta()
        assert r_alta.status_code == 200, r_alta.text
        impacto = cli.get(f"/v1/cuentas/{nomina}/capacidades/PAGAR_GASTO/impacto", headers=h.AUTH).json()
        clave = "plantillas" if writer == "plantilla" else "preferencias"
        assert [x[f"{writer}_id"] for x in impacto[clave]] == [str(pid)]
        salida = _serie(barrera, [("capacidad", lambda: _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar"))],
                        f"M4_d_{writer}_maestro_primero")
        assert salida["capacidad"].status_code == 200, salida["capacidad"].text
        # Guardada antes: queda «No disponible», sin reasignar (D-CAP-03).
        if writer == "plantilla":
            p = next(x for x in cli.get("/v1/plantillas", headers=h.AUTH).json()["plantillas"] if x["id"] == str(pid))
            assert p["cuenta_default_id"] == str(nomina) and {"campo": "cuenta", "motivo": "NO_ELEGIBLE"} in p["avisos"]
        else:
            p = next(x for x in cli.get("/v1/preferencias", headers=h.AUTH).json()["preferencias"] if x["id"] == str(pid))
            assert p["cuenta_default_id"] == str(nomina) and p["cuenta_disponible_hoy"] is False
    assert _caps(owner, nomina) == ["TRANSFERIR_SALIDA"]


# ------------------------------------------------------------------ (e) dos writers
@pytest.mark.parametrize("primero", ["activar", "desactivar"])
def test_e_dos_writers_misma_cuenta(t, primero):
    owner, _, cli, nomina, _ = t
    barrera = _barrera_fila(owner, CUENTA_FOR_UPDATE, (nomina,))
    pasos = {"activar": lambda: _cambiar(cli, nomina, "RECIBIR_INGRESO", "activar", 1),
             "desactivar": lambda: _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar", 1)}
    salida = _serie(barrera, _en_orden(primero, pasos), f"M4_e_{primero}")
    segundo = "desactivar" if primero == "activar" else "activar"
    assert salida[primero].status_code == 200 and salida[primero].json()["cuenta"]["row_version"] == 2
    assert (salida[segundo].status_code, _cod(salida[segundo])) == (409, "VERSION_DESFASADA")
    esperado = ["PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA"] if primero == "activar" else ["TRANSFERIR_SALIDA"]
    assert _caps(owner, nomina) == esperado
    assert h.leer(owner, "SELECT row_version FROM gapto.cuentas WHERE id=%s", (nomina,))[0][0] == 2
    assert _auditorias(owner, nomina) == 1


def test_orden_de_locks_writer_cuenta_antes_que_capacidad(t):
    """Mientras el writer espera la cuenta no tiene la fila de capacidad: la
    sonda NOWAIT sobre la capacidad no esta bloqueada (cuenta -> capacidad)."""
    owner, _, cli, nomina, _ = t
    barrera = _barrera_fila(owner, CUENTA_FOR_UPDATE, (nomina,))

    def inspeccion(evid):
        libre = not _nowait(owner, "SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id=%s "
                                   "AND capacidad_codigo='PAGAR_GASTO' FOR UPDATE", (nomina,))
        assert libre, "el writer toma la capacidad antes que la cuenta"
        return {"capacidad_libre_mientras_espera_la_cuenta": libre}

    salida = _serie(barrera, [("capacidad", lambda: _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar"))],
                    "M4_orden_cuenta_capacidad", inspeccion)
    assert salida["capacidad"].status_code == 200
