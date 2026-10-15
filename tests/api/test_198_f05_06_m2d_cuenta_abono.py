# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_198_f05_06_m2d_cuenta_abono.py
# Ruta: tests/api/test_198_f05_06_m2d_cuenta_abono.py
# Descripcion: Capacidad de la cuenta del abono de una devolucion (F05-06
#   M2-D §1 y §3; decision R-M2A-02 = opcion (b) endurecida, AJ-M2C-01..04).
#   Con el rol real gapto_runtime (adaptador HTTP) y RLS, por las DOS vias del
#   abono (devolucion «Ya cobrado» y «Registrar abono» posterior):
#     1. cuenta original (tarjeta de credito, PAGAR_GASTO sin RECIBIR_INGRESO)
#        -> permitido;
#     2. cuenta original SIN PAGAR_GASTO (retirada por el writer de M4)
#        -> permitido: la original no exige capacidad;
#     3. otra cuenta con RECIBIR_INGRESO -> permitido;
#     4. otra cuenta sin RECIBIR_INGRESO (con o sin PAGAR_GASTO)
#        -> CUENTA_SIN_CAPACIDAD (capacidad RECIBIR_INGRESO), sin escritura;
#     5. cuenta original cerrada o deshabilitada, cuenta ajena o de otra
#        moneda -> rechazo como hoy, sin escritura;
#     6. origen con dos conciliaciones -> cuenta_compra = null y la cuenta de
#        la compra ya no tiene trato especial (exige RECIBIR_INGRESO);
#     8. replay idempotente sin segundo movimiento.
#   Los casos 1-6 y 8 corren en las dos vias (punto 7). Discriminantes frente
#   a a61cadf (PAGAR_GASTO para cualquier cuenta y cuenta_compra = primer
#   movimiento de salida): fallan 2, 3, 4 (con PAGAR_GASTO) y 6.
#   Reloj fijo 2026-10-10 (Madrid).
# Version: 0.1.0 (F05-06 M2-D §3)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

import f05_01_helpers as fh
import f05_05_helpers as x
import f05_06_m2_helpers as m
import vs01_api_helpers as h
from app.core.errores import CodigoError, ErrorMotor

D = decimal.Decimal
VIAS = ["inmediato", "posterior"]


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    ropa = x.categoria(owner, "Ropa")
    # Tarjeta de credito sintetica: PAGAR_GASTO y TRANSFERIR_ENTRADA, sin RECIBIR_INGRESO (tipo CREDITO, C1).
    tarjeta = h.crear_cuenta(owner, [(actor, 100)], tipo="CREDITO", naturaleza="PASIVO")
    return owner, actor, cli, cta, tarjeta, ropa


def _cod(r):
    return r.json().get("codigo")


def _contexto(cli, origen):
    r = cli.get(m.url_devoluciones(origen), headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _version_cuenta(owner, cuenta) -> int:
    return m.contar(owner, "SELECT row_version FROM gapto.cuentas WHERE id=%s", (cuenta,))


def _desactivar(cli, owner, cuenta, capacidad):
    r = cli.post(f"/v1/cuentas/{cuenta}/capacidades/{capacidad}/desactivar",
                 json={"row_version": _version_cuenta(owner, cuenta)}, headers=h.AUTH)
    assert r.status_code == 200, r.text


def _abono(cli, origen, cuenta, via, *, intencion_id=None):
    """Intenta el abono de 40 sobre `origen` en `cuenta` por la via indicada.
    Devuelve (respuesta, id de la devolucion o None). En la via posterior la
    devolucion pendiente se crea antes (y debe pasar)."""
    if via == "inmediato":
        c, r = m.devolver(cli, origen, abono=m.cobrado(cuenta), intencion_id=intencion_id)
        return r, uuid.UUID(c["intencion_id"])
    c, r0 = m.devolver(cli, origen)
    assert r0.status_code == 200, r0.text
    dev = uuid.UUID(c["intencion_id"])
    _, r = m.abonar(cli, dev, cuenta, intencion_id=intencion_id)
    return r, dev


def _preparar(cli, origen, via):
    """Para medir «sin escritura» desde el punto justo antes del abono: en la
    via posterior la devolucion pendiente ya existe."""
    if via == "inmediato":
        return None
    c, r0 = m.devolver(cli, origen)
    assert r0.status_code == 200, r0.text
    return uuid.UUID(c["intencion_id"])


def _intentar(cli, origen, dev, cuenta, via):
    if via == "inmediato":
        return m.devolver(cli, origen, abono=m.cobrado(cuenta))[1]
    return m.abonar(cli, dev, cuenta)[1]


def _abonos(owner, dev) -> list[tuple]:
    return h.leer(owner, "SELECT m.cuenta_id, m.importe FROM gapto.hecho_movimientos_tesoreria hm "
                         "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
                         "WHERE hm.hecho_id=%s", (dev,))


def _conciliar_salida(owner, hecho, cuenta, importe: str) -> None:
    """Movimiento de salida + conciliacion con `hecho` por los servicios del
    motor (OP-08 + OP-09), como el pago de una compra en dos cuentas."""
    from app.core.contexto import ContextoOperacion
    from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
    from app.services.tesoreria_service import TesoreriaService

    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    tes = TesoreriaService(fh.unidad())
    mov = tes.registrar_movimiento(ctx, DatosMovimiento(
        movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=dt.date.fromisoformat(m.FECHA_COMPRA),
        importe=-D(importe), clase_movimiento="OPERACION", descripcion="M2-D pago partido",
        confirmado_at=dt.datetime.now(dt.timezone.utc)))
    version = m.contar(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (hecho,))
    tes.conciliar(ctx, DatosConciliacion(conciliacion_id=uuid.uuid4(), hecho_id=hecho,
                                         movimiento_tesoreria_id=mov.movimiento_id, importe_asignado=-D(importe)),
                  hecho_row_version_esperada=version, movimiento_row_version_esperada=mov.row_version)


# ------------------------------------------------------------------ 1-2 cuenta original
@pytest.mark.parametrize("via", VIAS)
def test_1_cuenta_original_tarjeta_sin_recibir_ingreso(t, via):
    owner, _, cli, _, tarjeta, ropa = t
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    assert _contexto(cli, origen)["cuenta_compra"]["cuenta_id"] == str(tarjeta)
    r, dev = _abono(cli, origen, tarjeta, via)
    assert r.status_code == 200, r.text
    assert _abonos(owner, dev) == [(tarjeta, D("40.0000"))]


@pytest.mark.parametrize("via", VIAS)
def test_2_cuenta_original_sin_pagar_gasto(t, via):
    owner, _, cli, _, tarjeta, ropa = t
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    _desactivar(cli, owner, tarjeta, "PAGAR_GASTO")
    assert m.contar(owner, "SELECT count(*) FROM gapto.cuenta_capacidades WHERE cuenta_id=%s "
                           "AND capacidad_codigo IN ('PAGAR_GASTO','RECIBIR_INGRESO')", (tarjeta,)) == 0
    assert _contexto(cli, origen)["cuenta_compra"]["cuenta_id"] == str(tarjeta)
    r, dev = _abono(cli, origen, tarjeta, via)
    assert r.status_code == 200, r.text
    assert _abonos(owner, dev) == [(tarjeta, D("40.0000"))]


# ------------------------------------------------------------------ 3-4 otra cuenta
@pytest.mark.parametrize("via", VIAS)
def test_3_otra_cuenta_con_recibir_ingreso(t, via):
    owner, actor, cli, _, tarjeta, ropa = t
    solo_recibir = h.crear_cuenta(owner, [(actor, 100)], capacidades=("RECIBIR_INGRESO",))
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    r, dev = _abono(cli, origen, solo_recibir, via)
    assert r.status_code == 200, r.text
    assert _abonos(owner, dev) == [(solo_recibir, D("40.0000"))]


@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize("capacidades", [("PAGAR_GASTO",), ()], ids=["con_pagar_gasto", "sin_capacidades"])
def test_4_otra_cuenta_sin_recibir_ingreso(t, via, capacidades):
    owner, actor, cli, _, tarjeta, ropa = t
    otra = h.crear_cuenta(owner, [(actor, 100)], capacidades=capacidades)
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    dev = _preparar(cli, origen, via)
    antes = m.huella(owner)
    r = _intentar(cli, origen, dev, otra, via)
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD"), r.text
    detalle = r.json()["detalle"]
    assert (detalle["operacion"], detalle["capacidad"], detalle["cuenta_id"]) == (
        "ABONO_DEVOLUCION", "RECIBIR_INGRESO", str(otra))
    assert "recibir dinero" in r.json()["mensaje"] and "ingreso" not in r.json()["mensaje"].lower()
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ 5 reglas de cuenta siempre
@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize("cambio", ["cerrada", "deshabilitada"])
def test_5_cuenta_original_cerrada_o_deshabilitada(t, via, cambio):
    owner, _, cli, _, tarjeta, ropa = t
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    dev = _preparar(cli, origen, via)
    # Una cuenta cerrada esta ademas deshabilitada (ck_cuentas__cierre_deshabilita).
    sql = ("UPDATE gapto.cuentas SET enabled = false, fecha_cierre = DATE '2026-09-01' WHERE id=%s"
           if cambio == "cerrada" else "UPDATE gapto.cuentas SET enabled = false WHERE id=%s")
    h.como_owner(owner, sql, (tarjeta,))
    antes = m.huella(owner)
    r = _intentar(cli, origen, dev, tarjeta, via)
    assert (r.status_code, _cod(r)) == (422, "CUENTA_DESCONOCIDA"), r.text
    assert m.huella(owner) == antes


@pytest.mark.parametrize("via", VIAS)
def test_5_cuenta_ajena(t, via):
    owner, _, cli, _, tarjeta, ropa = t
    _, _, _, ajena, _ = x.entorno()
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    dev = _preparar(cli, origen, via)
    antes = m.huella(owner)
    r = _intentar(cli, origen, dev, ajena, via)
    assert (r.status_code, _cod(r)) == (422, "CUENTA_DESCONOCIDA"), r.text
    assert m.huella(owner) == antes


def test_5_cuenta_original_de_otra_moneda_no_se_exime(t):
    """La via sin capacidad de la cuenta original sigue exigiendo EUR (y owner,
    habilitada, cierre): servicio del adaptador sobre una cuenta USD tratada
    como original. Ninguna ruta HTTP crea un origen EUR pagado en USD."""
    from app.api.ejecucion_devolucion import _rechazo_cuenta_abono
    from app.comun.elegibilidad_cuentas import MONEDA, motivo_cuenta_original_abono
    from app.core.contexto import ContextoOperacion

    owner, actor, _, _, _, _ = t
    usd = h.crear_cuenta(owner, [(actor, 100)], "USD", capacidades=())
    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    fecha = dt.date.fromisoformat(m.FECHA_DEVOLUCION)
    assert fh.unidad().ejecutar(ctx, lambda s: motivo_cuenta_original_abono(s, usd, fecha)) == MONEDA

    def rechazar(s):
        try:
            _rechazo_cuenta_abono(s, usd, fecha, usd)
        except ErrorMotor as exc:
            return exc.codigo
        return None

    assert fh.unidad().ejecutar(ctx, rechazar) is CodigoError.MONEDA_INVALIDA


# ------------------------------------------------------------------ 6 sin cuenta original unica
@pytest.mark.parametrize("via", VIAS)
def test_6_origen_con_dos_conciliaciones(t, via):
    owner, actor, cli, cta, tarjeta, ropa = t
    origen = x.hecho_motor(owner, [("GASTO", "120", "COMPLETA", ropa, [(actor, "120")])], fecha=m.FECHA_COMPRA)
    _conciliar_salida(owner, origen, cta, "70")
    _conciliar_salida(owner, origen, tarjeta, "50")
    assert _contexto(cli, origen)["cuenta_compra"] is None
    # La tarjeta pago parte de la compra, pero ya no es «la» cuenta original: exige RECIBIR_INGRESO.
    dev = _preparar(cli, origen, via)
    antes = m.huella(owner)
    r = _intentar(cli, origen, dev, tarjeta, via)
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD"), r.text
    assert r.json()["detalle"]["capacidad"] == "RECIBIR_INGRESO"
    assert m.huella(owner) == antes
    # Una cuenta con RECIBIR_INGRESO (la corriente, que tambien pago parte) si sirve.
    r = _intentar(cli, origen, dev, cta, via)
    assert r.status_code == 200, r.text


def test_6_cuenta_compra_con_una_conciliacion_de_salida(t):
    """Contraste del 6: con UNA conciliacion contra un movimiento de salida
    ACTIVO hay cuenta original y el contexto la propone."""
    owner, actor, cli, cta, tarjeta, ropa = t
    origen = x.hecho_motor(owner, [("GASTO", "120", "COMPLETA", ropa, [(actor, "120")])], fecha=m.FECHA_COMPRA)
    assert _contexto(cli, origen)["cuenta_compra"] is None  # ninguna conciliacion: no hay original
    _conciliar_salida(owner, origen, tarjeta, "120")
    assert _contexto(cli, origen)["cuenta_compra"] == {"cuenta_id": str(tarjeta), "nombre": "Cuenta EUR sintetica"}


# ------------------------------------------------------------------ 8 replay
@pytest.mark.parametrize("via", VIAS)
def test_8_replay_idempotente_sin_segundo_movimiento(t, via):
    owner, _, cli, _, tarjeta, ropa = t
    origen = m.compra(cli, tarjeta, categoria_id=ropa)
    _desactivar(cli, owner, tarjeta, "PAGAR_GASTO")
    intencion = uuid.uuid4()
    r, dev = _abono(cli, origen, tarjeta, via, intencion_id=intencion)
    assert r.status_code == 200, r.text
    antes = m.huella(owner)
    if via == "inmediato":
        r2 = m.devolver(cli, origen, abono=m.cobrado(tarjeta), intencion_id=intencion)[1]
    else:
        r2 = m.abonar(cli, dev, tarjeta, intencion_id=intencion)[1]
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotente"] is True
    assert m.huella(owner) == antes
    assert _abonos(owner, dev) == [(tarjeta, D("40.0000"))]
