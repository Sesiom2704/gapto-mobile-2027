# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_202_f04_r2_consumidores_anulacion.py
# Ruta: tests/api/test_202_f04_r2_consumidores_anulacion.py
# Descripcion: F04-R2 RECIERRE COMP, HUECO-04 (contrato F04-R2 v0.9 §10.8,
#   §2.4 y §2.4.1; F05 §55, P-EDIT-02). Consumidores F05 tras OP-03P de una
#   devolucion CON abono (M2), por la API real: el registro y el abono por sus
#   rutas HTTP, la anulacion por el adaptador interno
#   `app.api.ejecucion_anulacion` (OP-03P no tiene ruta HTTP, §2.3.10) y las
#   lecturas por GET. Comprueba, antes y despues:
#     - la devolucion desaparece de la Actividad del mes;
#     - la compra deja de mostrar lo devuelto (detalle y contexto de
#       devoluciones, P-EDIT-02);
#     - el Resultado de Inicio del mes cambia en la diferencia exacta y con su
#       signo (la devolucion restaba gasto: al anularla, el gasto propio vuelve);
#     - el saldo de la cuenta del abono vuelve al de antes del abono (no hay
#       lectura HTTP de saldo por cuenta: se lee de los movimientos ACTIVOS);
#     - la compra deja de estar bloqueada por DEPENDENCIAS_ACTIVAS en la
#       elegibilidad de anulacion (GET /v1/hechos/{id}/anulacion); por tener
#       tesoreria, la via de anulacion de la compra es OP-03P, que ahora la anula.
# Version: 0.1.0 (F04-R2 RECIERRE COMP)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

import f05_01_helpers as fh
import f05_05_helpers as x
import f05_06_m2_helpers as m
import vs01_api_helpers as h

D = decimal.Decimal
SEPTIEMBRE = {"desde": "2026-09-01", "hasta": "2026-09-30"}


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    ropa = x.categoria(owner, "Ropa")
    return owner, actor, cli, cta, ahorro, ropa


def _get(cli, url, **params):
    r = cli.get(url, params=params or None, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _saldo(owner, cuenta) -> D:
    return h.leer(owner, "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
                         "WHERE cuenta_id = %s AND estado = 'ACTIVO'", (cuenta,))[0][0]


def _lecturas(cli, owner, origen, dev, cuenta) -> dict:
    ids = [f["id"] for f in _get(cli, "/v1/actividad", **SEPTIEMBRE, limite=100)["filas"]]
    detalle = _get(cli, f"/v1/actividad/{origen}")
    contexto = _get(cli, m.url_devoluciones(origen))
    return {
        "dev_en_actividad": str(dev) in ids,
        "detalle_devoluciones": detalle["devoluciones"],
        "contexto": (contexto["devuelto"], contexto["queda"]),
        "septiembre": _get(cli, "/v1/inicio/resultado-mes", fecha="2026-09-30"),
        "agosto": _get(cli, "/v1/inicio/resultado-mes", fecha="2026-08-31"),
        "saldo": _saldo(owner, cuenta),
        "elegibilidad": _get(cli, f"/v1/hechos/{origen}/anulacion"),
    }


def _anular_por_el_adaptador(owner, hecho):
    from app.api import ejecucion_anulacion
    from app.core.contexto import ContextoOperacion
    from app.services.anulacion_tesoreria_service import DatosAnulacionRegistro

    version = h.leer(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0][0]
    movs = dict(h.leer(owner, "SELECT m.id, m.row_version FROM gapto.hecho_movimientos_tesoreria c "
                              "JOIN gapto.movimientos_tesoreria m ON m.id = c.movimiento_tesoreria_id "
                              "WHERE c.hecho_id = %s", (hecho,)))
    return ejecucion_anulacion.anular_registro(
        fh.unidad(), ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()),
        DatosAnulacionRegistro(hecho_id=hecho, row_version_esperada=version, movimientos_row_version_esperadas=movs,
                               motivo="devolucion registrada por duplicado", movimiento_en_banco=False))


def test_op03p_de_una_devolucion_con_abono_en_los_consumidores_f05(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)                       # 120,00 en agosto
    saldo_sin_abono = _saldo(owner, cta)
    c, r = m.devolver(cli, origen)                                       # 40,00 en septiembre
    assert r.status_code == 200, r.text
    dev = uuid.UUID(c["intencion_id"])
    _, r = m.abonar(cli, dev, cta, fecha="2026-09-12")                   # abono +40,00
    assert r.status_code == 200, r.text

    antes = _lecturas(cli, owner, origen, dev, cta)
    assert antes["dev_en_actividad"] is True
    assert antes["detalle_devoluciones"]["devuelto"] == "40.00"
    assert [i for i in antes["detalle_devoluciones"]["items"]] != []
    assert antes["contexto"] == ("40.00", "80.00")
    assert (antes["septiembre"]["gastos_propios"], antes["septiembre"]["resultado"]) == ("-40.00", "40.00")
    assert antes["saldo"] == saldo_sin_abono + D("40")
    assert "DEPENDENCIAS_ACTIVAS" in antes["elegibilidad"]["motivos"] and not antes["elegibilidad"]["elegible"]

    resultado = _anular_por_el_adaptador(owner, dev)
    assert resultado.hecho_id == dev and resultado.idempotente is False

    despues = _lecturas(cli, owner, origen, dev, cta)
    # La devolucion anulada desaparece de la Actividad del mes.
    assert despues["dev_en_actividad"] is False
    # La compra deja de mostrar lo devuelto (P-EDIT-02).
    assert despues["detalle_devoluciones"] is None  # sin devoluciones ACTIVAS (lecturas.devoluciones_de_origen)
    assert despues["contexto"] == ("0.00", "120.00")
    # Inicio: septiembre pierde la devolucion (-40 de gasto propio) -> resultado 40,00 -> 0,00 (diferencia -40).
    assert (despues["septiembre"]["gastos_propios"], despues["septiembre"]["resultado"]) == ("0.00", "0.00")
    assert D(despues["septiembre"]["resultado"]) - D(antes["septiembre"]["resultado"]) == D("-40.00")
    assert despues["agosto"] == antes["agosto"]  # la compra no cambia
    # El saldo de la cuenta del abono vuelve al de antes del abono.
    assert despues["saldo"] == saldo_sin_abono
    # G-R1-A ya no bloquea la compra.
    assert "DEPENDENCIAS_ACTIVAS" not in despues["elegibilidad"]["motivos"]
    # Y la compra (con tesoreria) es anulable de nuevo, por su via (OP-03P).
    r2 = _anular_por_el_adaptador(owner, origen)
    assert r2.hecho_id == origen
    assert h.leer(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (origen,)) == [("ANULADO",)]
