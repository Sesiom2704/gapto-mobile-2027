# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_151_f05_vs01_financiacion_atomicidad.py
# Ruta: tests/api/test_151_f05_vs01_financiacion_atomicidad.py
# Descripcion: Pruebas discriminantes de F05-D003 §16.3-§16.5 (VS-01):
#   financiacion sellada en la intencion, aceptacion implicita solo self 100 %,
#   PROPUESTA_FINANCIACION_OBSOLETA, precedencia identidad -> revalidacion,
#   vigencia evaluada en la fecha del pago, fecha no futura, agregado exacto
#   en el reconocimiento de identidad y atomicidad bajo el lock de cuenta con
#   interleaving controlado (WM 12C.1: barrera SET CONSTRAINTS ALL IMMEDIATE).
#   Base local desechable 0001..0330 (estos tests confirman filas).
#   v0.2.0 (F05 §18): el caso de financiacion reducida se apoya en OP-22
#   recertificado, sin guarda propia en la capa F05.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid

import psycopg
import pytest

import vs01_api_helpers as h

URL = "/v1/intenciones/gasto-pagado"
CAMBIO = dt.date(2026, 9, 20)  # desde esta fecha la cuenta pasa a 50/50


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    otro = h.crear_actor_tercero(owner)
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, otro, cuenta


def _sql_cambio_a_compartida(cur, cuenta, actor, otro) -> None:
    """Version nueva de participaciones: self 100 % hasta el 19/09 y 50/50
    desde el 20/09. No reescribe el pasado: cierra la vigencia anterior."""
    cur.execute(
        "UPDATE gapto.cuenta_participaciones SET vigente_hasta = %s "
        "WHERE cuenta_id = %s AND vigente_hasta IS NULL",
        (CAMBIO - dt.timedelta(days=1), cuenta),
    )
    for a in (actor, otro):
        cur.execute(
            "INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, vigente_desde) "
            "VALUES (%s, %s, 50, %s)",
            (cuenta, a, CAMBIO),
        )


def _cambiar_a_compartida(owner, cuenta, actor, otro) -> None:
    with psycopg.connect(h.dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            _sql_cambio_a_compartida(cur, cuenta, actor, otro)


def _n(owner, tabla, hid) -> int:
    return h.leer(owner, f"SELECT count(*) FROM gapto.{tabla} WHERE hecho_id=%s", (hid,))[0][0]


def _propuesta(cli, cuenta, fecha) -> str:
    cuentas = cli.get("/v1/vs01/cuentas-pago", params={"fecha": fecha}, headers=h.AUTH).json()["cuentas"]
    return {c["cuenta_id"]: c["propuesta_financiacion"] for c in cuentas}[str(cuenta)]


# ---------------------------------------------------------------- §16.4
def test_self_100_propuesta_visible_y_aportacion_sin_toque_adicional(tenant):
    owner, actor, _, cuenta = tenant
    cli = h.cliente(owner)
    assert _propuesta(cli, cuenta, "2026-09-24") == "SELF_100"
    cuerpo = h.intencion(cuenta)  # propuesta self 100 % aceptada al confirmar
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["financiacion"] == "PROPUESTA_ACEPTADA"
    fila = h.leer(owner, "SELECT actor_id, importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago "
                         "WHERE hecho_id=%s", (uuid.UUID(cuerpo["intencion_id"]),))
    assert [(f[0], str(f[1]), f[2]) for f in fila] == [(actor, "3.5000", "PARTICIPACION_CUENTA")]


def test_sin_participaciones_no_determinada_y_propuesta_obsoleta(tenant):
    owner, _, _, _ = tenant
    sin_part = h.crear_cuenta(owner, [])
    cli = h.cliente(owner)
    assert _propuesta(cli, sin_part, "2026-09-24") == "NO_DETERMINADA"
    ok = h.intencion(sin_part, financiacion=h.NO_DETERMINADA)
    assert cli.post(URL, json=ok, headers=h.AUTH).status_code == 200
    assert _n(owner, "hecho_aportaciones_pago", uuid.UUID(ok["intencion_id"])) == 0
    malo = h.intencion(sin_part)
    r = cli.post(URL, json=malo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA"
    assert r.json()["reintentable"] is False
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
                  (uuid.UUID(malo["intencion_id"]),))[0][0] == 0


def test_reparto_50_50_no_determinada_y_propuesta_rechazada(tenant):
    owner, actor, otro, _ = tenant
    compartida = h.crear_cuenta(owner, [(actor, 50), (otro, 50)])
    cli = h.cliente(owner)
    assert _propuesta(cli, compartida, "2026-09-24") == "NO_DETERMINADA"
    r = cli.post(URL, json=h.intencion(compartida), headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA"


def test_unico_actor_100_no_self_no_es_propuesta(tenant):
    owner, _, otro, _ = tenant
    ajena = h.crear_cuenta(owner, [(otro, 100)])
    cli = h.cliente(owner)
    assert _propuesta(cli, ajena, "2026-09-24") == "NO_DETERMINADA"
    assert cli.post(URL, json=h.intencion(ajena), headers=h.AUTH).json()["codigo"] == \
        "PROPUESTA_FINANCIACION_OBSOLETA"


def test_cambio_antes_de_ejecutar_obsoleta_sin_mutaciones_y_reintento_rechazado(tenant):
    owner, actor, otro, cuenta = tenant
    cli = h.cliente(owner)
    assert _propuesta(cli, cuenta, "2026-09-24") == "SELF_100"  # el formulario la ve
    cuerpo = h.intencion(cuenta)  # sellada con la propuesta
    _cambiar_a_compartida(owner, cuenta, actor, otro)  # cambia antes de ejecutar
    hid = uuid.UUID(cuerpo["intencion_id"])
    for _ in range(2):  # el reintento de una intencion NO aplicada sigue rechazado
        r = cli.post(URL, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 409 and r.json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA"
    for tabla in ("hecho_efectos", "hecho_movimientos_tesoreria", "hecho_aportaciones_pago"):
        assert _n(owner, tabla, hid) == 0
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (hid,))[0][0] == 0
    assert h.leer(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id=%s", (cuenta,))[0][0] == 0


def test_reintento_tras_commit_real_es_idempotente_aunque_cambie_la_participacion(tenant):
    owner, actor, otro, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    primero = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert primero.status_code == 200 and primero.json()["idempotente"] is False
    # El cliente no vio la respuesta (INDETERMINADO) y entretanto cambia la cuenta.
    _cambiar_a_compartida(owner, cuenta, actor, otro)
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is True and r.json()["financiacion"] == "PROPUESTA_ACEPTADA"
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _n(owner, "hecho_aportaciones_pago", hid) == 1


def test_misma_identidad_con_financiacion_reducida_no_es_idempotente(tenant):
    """Mismo UUID con NO_DETERMINADA frente a una aportacion ya materializada
    -> IDENTIDAD_REUTILIZADA, no exito. La igualdad exacta la impone OP-22
    (F04-D050/F04-D051); este test la comprueba extremo a extremo por HTTP."""
    owner, _, _, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    assert cli.post(URL, json=cuerpo, headers=h.AUTH).status_code == 200
    r = cli.post(URL, json={**cuerpo, "financiacion": h.NO_DETERMINADA}, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


# ---------------------------------------------------------------- §16.3
def test_vigencia_se_evalua_en_la_fecha_del_pago(tenant):
    owner, actor, otro, cuenta = tenant
    _cambiar_a_compartida(owner, cuenta, actor, otro)
    cli = h.cliente(owner)
    assert _propuesta(cli, cuenta, "2026-09-10") == "SELF_100"
    assert _propuesta(cli, cuenta, "2026-09-24") == "NO_DETERMINADA"
    antes = h.intencion(cuenta, fecha_hecho="2026-09-10")
    r = cli.post(URL, json=antes, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["financiacion"] == "PROPUESTA_ACEPTADA"
    mov = h.leer(owner, "SELECT m.fecha_movimiento FROM gapto.movimientos_tesoreria m "
                        "JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id = m.id "
                        "WHERE c.hecho_id=%s", (uuid.UUID(antes["intencion_id"]),))
    assert mov == [(dt.date(2026, 9, 10),)]  # fecha comun gasto/pago
    despues = h.intencion(cuenta, fecha_hecho="2026-09-24")
    assert cli.post(URL, json=despues, headers=h.AUTH).json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA"


def test_fecha_futura_rechazada_y_pasada_admitida(tenant):
    from app.api.dto_vs01 import hoy_referencia

    owner, _, _, cuenta = tenant
    cli = h.cliente(owner)
    futura = (hoy_referencia() + dt.timedelta(days=1)).isoformat()
    r = cli.post(URL, json=h.intencion(cuenta, fecha_hecho=futura), headers=h.AUTH)
    assert r.status_code == 422 and "fecha_hecho" in r.json()["mensaje"]
    ayer = (hoy_referencia() - dt.timedelta(days=1)).isoformat()
    assert cli.post(URL, json=h.intencion(cuenta, fecha_hecho=ayer), headers=h.AUTH).status_code == 200


def test_importe_de_la_propuesta_debe_igualar_el_gasto(tenant):
    owner, _, _, cuenta = tenant
    cuerpo = h.intencion(cuenta, financiacion=h.propuesta_self_100("1.00"))
    assert h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH).status_code == 422


# ---------------------------------------------------------------- §16.5
def _esperar_bloqueo(pid_excluido: int, limite_s: float = 8.0) -> bool:
    """True si otra sesion de esta base queda esperando un lock."""
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            fila = mon.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> %s AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'",
                (pid_excluido,),
            ).fetchone()
            if fila[0] > 0:
                return True
            time.sleep(0.05)
    return False


@pytest.mark.parametrize("desenlace_b", ["COMMIT", "ROLLBACK"])
def test_interleaving_lock_de_cuenta_serializa_con_cambio_de_participacion(tenant, desenlace_b):
    """Barrera explicita (WM 12C.1): B cambia participaciones y fuerza su
    validacion diferida con SET CONSTRAINTS ALL IMMEDIATE, que toma
    FOR NO KEY UPDATE sobre la cuenta y lo retiene. A (VS-01) debe QUEDAR
    ESPERANDO ese mismo root; al terminar B, A relee bajo el lock:
      COMMIT de B   -> la propuesta sellada ya no se sostiene -> OBSOLETA;
      ROLLBACK de B -> la propuesta sigue valida -> materializa la aportacion.
    Sin el lock (o con la lectura fuera de la transaccion) A no espera o
    decide sobre una fotografia obsoleta: el test falla."""
    owner, actor, otro, cuenta = tenant
    cli = h.cliente(owner)
    cuerpo = h.intencion(cuenta)
    salida: dict = {}

    b = psycopg.connect(h.dsn())
    try:
        cur = b.cursor()
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gapto_owner")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        _sql_cambio_a_compartida(cur, cuenta, actor, otro)
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # B retiene el lock de la cuenta
        pid_b = b.info.backend_pid

        hilo = threading.Thread(target=lambda: salida.update(r=cli.post(URL, json=cuerpo, headers=h.AUTH)))
        hilo.start()
        assert _esperar_bloqueo(pid_b), "VS-01 no espero el lock de la cuenta"
        assert hilo.is_alive() and "r" not in salida
        cur.execute(desenlace_b)
    finally:
        b.close()
    hilo.join(timeout=15)
    assert not hilo.is_alive()

    r = salida["r"]
    hid = uuid.UUID(cuerpo["intencion_id"])
    if desenlace_b == "COMMIT":
        assert r.status_code == 409 and r.json()["codigo"] == "PROPUESTA_FINANCIACION_OBSOLETA"
        assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (hid,))[0][0] == 0
    else:
        assert r.status_code == 200, r.text
        assert _n(owner, "hecho_aportaciones_pago", hid) == 1
