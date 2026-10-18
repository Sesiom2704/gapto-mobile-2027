# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14e_f04_r2c_discriminantes.py
# Ruta: tests/backend/test_14e_f04_r2c_discriminantes.py
# Descripcion: F04-R2 R2-C (contrato F04-R2 v0.9 §2.3, §2.3.2 bis, §2.3.5-§2.3.7,
#   §2.4, §2.5, §5, §6.3, §6.4, §8.1, §9, §10.1, §10.1 bis; mandato F04-R2C
#   v1.0 P3-P5). Discriminantes de OP-03P que FALLAN sobre c6864ee (el servicio
#   no existe: cada test importa su identidad DENTRO del fixture) y pasan con
#   R2-C, todos con el rol real gapto_runtime (RLS activa).
#     Casos felices con oraculo I-03P-1..6 (estado final, saldo POR CUENTA y
#       con importes firmados, intactos, auditoria fila a fila y
#       reconstruccion): gasto pagado con aportacion, ingreso cobrado,
#       transferencia (fila retirada, dos patas ANULADAS) y devolucion con abono
#       (§2.4: capacidad liberada, relacion conservada, original anulable).
#     Rechazos sin efectos: declaracion ausente o true (tambien con abono),
#       request_id ausente, motivo vacio; cada fila de evidencia persistida de
#       §2.5 (importacion de hecho y de MOVIMIENTO con mapeos sinteticos,
#       AJUSTE_SALDO, cierre, ledger, reversion ACTIVA y ANULADA, movimiento
#       compartido, dependencias activas); A-1 (ya anulado, sin tesoreria);
#       §6.3 (hecho, movimiento, mapa incompleto); §6.4 (idempotente e
#       identidad reutilizada).
#     W3-W7 de R2-C-PRE: el motor nunca los deja (oraculo global tras cada
#       caso feliz).
#     Atomicidad (§2.3.6): fallo inyectado tras W3, tras W4 de una pata, tras
#       W5 y durante W6 -> rollback exacto de datos y de auditoria.
#     Refactor de OP-03 (§2.3.2 bis): impacto_correccion_ancla =
#       aplicar(adquirir), sin cambio (sus suites no cambian expectativas).
# Version: 0.1.0 (F04-R2 R2-C)
# ============================================================

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import json
import uuid

import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_tesoreria import DatosReversion
from conftest import _crear_cuenta
from test_113_rodante_y_materializacion import cadena  # noqa: F401
from test_113_rodante_y_materializacion import vincular as vincular_rodante
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_138_f04_r1_discriminantes import version_hecho
from test_14c_f04_r2b_discriminantes import (
    _todas,
    cierre,
    gasto,
    importar,
    nuevo,
    rechazo,
    saldo,
    sql_admin,
    transferencia,
)
from test_140_f04_r3_op22 import op22  # noqa: F401

D = decimal.Decimal
F = dt.date.fromisoformat
MOTIVO = "registro duplicado"


# ==================================================================
# Utilidades
# ==================================================================
@pytest.fixture()
def op03p(unidad):
    from app.services.anulacion_tesoreria_service import AnulacionTesoreriaService
    from app.services.previsiones_service import adquirir_impacto_ancla, aplicar_impacto_ancla

    return AnulacionTesoreriaService(unidad, adquirir_impacto=adquirir_impacto_ancla,
                                     aplicar_impacto=aplicar_impacto_ancla)


def movimientos_de(admin, hecho) -> list[uuid.UUID]:
    """Movimientos conciliados con el hecho y las patas de su transferencia."""
    filas = _todas(admin, "SELECT movimiento_tesoreria_id FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
                   (hecho,))
    movs = {f[0] for f in filas}
    for salida, entrada in _todas(admin, "SELECT movimiento_salida_id, movimiento_entrada_id FROM gapto.transferencias "
                                         "WHERE movimiento_salida_id = ANY(%s) OR movimiento_entrada_id = ANY(%s)",
                                  (list(movs), list(movs))):
        movs.update((salida, entrada))
    return sorted(movs, key=str)


def datos(admin, owner, hecho, **kw):
    from app.services.anulacion_tesoreria_service import DatosAnulacionRegistro

    movs = kw.pop("movimientos", None)
    if movs is None:
        movs = {m: _todas(admin, "SELECT row_version FROM gapto.movimientos_tesoreria WHERE id = %s", (m,))[0][0]
                for m in movimientos_de(admin, hecho)}
    base = dict(hecho_id=hecho, row_version_esperada=version_hecho(admin, owner, hecho),
                movimientos_row_version_esperadas=movs, motivo=MOTIVO, movimiento_en_banco=False)
    base.update(kw)
    return DatosAnulacionRegistro(**base)


def anular(op03p, contexto, admin, hecho, **kw):
    ctx = kw.pop("ctx", None) or nuevo(contexto)
    return op03p.anular_registro(ctx, datos(admin, contexto.owner_user_id, hecho, **kw))


def foto(admin, hecho, cuentas, movs=None) -> dict:
    """Todo lo que OP-03P puede tocar o debe dejar intacto (I-03P-1..5).
    `movs`: ids fijados antes (tras W2 ya no se llega a ellos por conciliacion)."""
    movs = movimientos_de(admin, hecho) if movs is None else movs
    return {
        "hecho": _todas(admin, "SELECT estado, row_version, anulado_at IS NOT NULL, motivo_anulacion, importe_total "
                               "FROM gapto.hechos_financieros WHERE id = %s", (hecho,)),
        "efectos": _todas(admin, "SELECT id, tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos "
                                 "WHERE hecho_id = %s ORDER BY id", (hecho,)),
        "atribuciones": _todas(admin, "SELECT a.id, a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                                      "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s "
                                      "ORDER BY a.id", (hecho,)),
        "relaciones": _todas(admin, "SELECT id, hecho_origen_id, hecho_destino_id, tipo_relacion FROM "
                                    "gapto.hecho_relaciones WHERE hecho_origen_id = %s OR hecho_destino_id = %s "
                                    "ORDER BY id", (hecho, hecho)),
        "terceros": _todas(admin, "SELECT tercero_id FROM gapto.hecho_terceros WHERE hecho_id = %s ORDER BY 1",
                           (hecho,)),
        "magnitudes": _todas(admin, "SELECT count(*) FROM gapto.hecho_magnitudes WHERE hecho_id = %s", (hecho,)),
        "movimientos": _todas(admin, "SELECT id, importe, estado, row_version, anulado_at IS NOT NULL, "
                                     "motivo_anulacion FROM gapto.movimientos_tesoreria WHERE id = ANY(%s) ORDER BY id",
                              (movs,)),
        "conciliaciones": _todas(admin, "SELECT id, movimiento_tesoreria_id, importe_asignado FROM "
                                        "gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s ORDER BY id", (hecho,)),
        "aportaciones": _todas(admin, "SELECT id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s "
                                      "ORDER BY id", (hecho,)),
        "transferencias": _todas(admin, "SELECT id FROM gapto.transferencias WHERE movimiento_salida_id = ANY(%s) "
                                        "OR movimiento_entrada_id = ANY(%s) ORDER BY id", (movs, movs)),
        "saldos": [saldo(admin, c) for c in cuentas],
    }


def auditorias(admin, request_id) -> list[tuple]:
    return _todas(admin, "SELECT tabla, registro_id, accion, datos_antes::text, datos_despues::text, motivo "
                         "FROM gapto.auditoria WHERE request_id = %s ORDER BY tabla, registro_id", (request_id,))


def oraculo_global(admin, owner) -> None:
    """W3-W7 de R2-C-PRE: nunca un hecho ANULADO con conciliaciones o
    aportaciones, nunca un movimiento ACTIVO de un hecho ANULADO, nunca una
    transferencia asimetrica ni un hecho TRANSFERENCIA ACTIVO sin su fila."""
    assert _todas(admin, "SELECT count(*) FROM gapto.hechos_financieros h WHERE h.owner_user_id = %s "
                         "AND h.estado = 'ANULADO' AND (EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria c "
                         "WHERE c.hecho_id = h.id) OR EXISTS (SELECT 1 FROM gapto.hecho_aportaciones_pago a "
                         "WHERE a.hecho_id = h.id))", (owner,)) == [(0,)]
    assert _todas(admin, "SELECT count(*) FROM gapto.transferencias t JOIN gapto.movimientos_tesoreria s "
                         "ON s.id = t.movimiento_salida_id JOIN gapto.movimientos_tesoreria e "
                         "ON e.id = t.movimiento_entrada_id WHERE s.estado <> e.estado", ()) == [(0,)]
    assert _todas(admin, "SELECT count(*) FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th "
                         "ON th.id = h.tipo_hecho_id WHERE h.owner_user_id = %s AND th.codigo = 'TRANSFERENCIA' "
                         "AND h.estado = 'ACTIVO' AND NOT EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria c "
                         "JOIN gapto.transferencias t ON t.movimiento_salida_id = c.movimiento_tesoreria_id "
                         "WHERE c.hecho_id = h.id)", (owner,)) == [(0,)]


def comprobar_feliz(admin, contexto, ctx, hecho, cuentas, antes: dict, deltas_saldo: list[D]) -> list[tuple]:
    """I-03P-1..6 sobre el estado final y la auditoria del request_id."""
    despues = foto(admin, hecho, cuentas, [m[0] for m in antes["movimientos"]])
    # I-03P-1
    assert despues["conciliaciones"] == [] and despues["aportaciones"] == []
    assert despues["hecho"][0][:4] == ("ANULADO", antes["hecho"][0][1] + 1, True, MOTIVO)
    # I-03P-2
    assert [m[:1] + m[2:] for m in despues["movimientos"]] == [
        (m[0], "ANULADO", m[3] + 1, True, MOTIVO) for m in antes["movimientos"]]
    # I-03P-3
    assert despues["transferencias"] == []
    # I-03P-4: por cuenta y con importes firmados (saldo - Σ importes anulados).
    assert despues["saldos"] == [a + d for a, d in zip(antes["saldos"], deltas_saldo)]
    # I-03P-5
    for k in ("efectos", "atribuciones", "relaciones", "terceros", "magnitudes"):
        assert despues[k] == antes[k], k
    # I-03P-6: una fila por mutacion, con fotos, motivo y request_id; reconstruccion.
    filas = auditorias(admin, ctx.request_id)
    esperadas = (len(antes["aportaciones"]) + len(antes["conciliaciones"]) + len(antes["transferencias"])
                 + len(antes["movimientos"]) + 1)
    assert len(filas) == esperadas
    assert all(f[5] == MOTIVO for f in filas)
    por = {(f[0], f[1]): f for f in filas}
    for aid, importe in antes["aportaciones"]:
        f = por[("hecho_aportaciones_pago", aid)]
        assert f[2] == "ELIMINAR" and f[4] is None and D(str(json.loads(f[3])["importe"])) == importe
    for cid, mid, importe in antes["conciliaciones"]:
        f = por[("hecho_movimientos_tesoreria", cid)]
        r = json.loads(f[3])
        assert f[2] == "ELIMINAR" and f[4] is None and r["movimiento_tesoreria_id"] == str(mid)
        assert D(str(r["importe_asignado"])) == importe and r["hecho_id"] == str(hecho)
    for (tid,) in antes["transferencias"]:
        assert por[("transferencias", tid)][2] == "ELIMINAR"
    for mid, importe, estado, version, _, _ in antes["movimientos"]:
        f = por[("movimientos_tesoreria", mid)]
        a, b = json.loads(f[3]), json.loads(f[4])
        assert f[2] == "ANULAR" and (a["row_version"], a["estado"]) == (version, estado)
        assert (b["row_version"], b["estado"], b["motivo_anulacion"]) == (version + 1, "ANULADO", MOTIVO)
        assert D(str(a["importe"])) == importe
    h = por[("hechos_financieros", hecho)]
    assert h[2] == "ANULAR" and json.loads(h[3])["row_version"] == antes["hecho"][0][1]
    assert json.loads(h[4])["row_version"] == antes["hecho"][0][1] + 1
    oraculo_global(admin, contexto.owner_user_id)
    return filas


# ==================================================================
# Casos felices (I-03P-1..6)
# ==================================================================
def test_gasto_pagado_con_aportacion(op22, op03p, contexto, admin, cuenta, actor_a):
    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "48.7200", None)],
              aportaciones=[(actor_a, "48.7200", "PARTICIPACION_CUENTA", "100", False)])
    antes = foto(admin, g.hecho, [cuenta])
    ctx = nuevo(contexto)
    r = anular(op03p, contexto, admin, g.hecho, ctx=ctx)
    assert r.idempotente is False and r.filas_auditadas == 4
    assert r.movimientos == {g.movimiento: antes["movimientos"][0][3] + 1}
    comprobar_feliz(admin, contexto, ctx, g.hecho, [cuenta], antes, [D("48.7200")])


def test_ingreso_cobrado(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, "1500.0000", tipo="INGRESO")
    antes = foto(admin, g.hecho, [cuenta])
    ctx = nuevo(contexto)
    anular(op03p, contexto, admin, g.hecho, ctx=ctx)
    comprobar_feliz(admin, contexto, ctx, g.hecho, [cuenta], antes, [D("-1500.0000")])


def test_transferencia_las_dos_patas_y_su_fila(op03p, servicio_transferencias, contexto, admin, cuenta,
                                               cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino, "500.0000")
    antes = foto(admin, t.hecho, [cuenta, cuenta_destino])
    assert len(antes["transferencias"]) == 1 and len(antes["movimientos"]) == 2
    ctx = nuevo(contexto)
    r = anular(op03p, contexto, admin, t.hecho, ctx=ctx)
    assert set(r.movimientos) == {t.salida, t.entrada}
    # cada cuenta recupera su saldo anterior
    comprobar_feliz(admin, contexto, ctx, t.hecho, [cuenta, cuenta_destino], antes, [D("500.0000"), D("-500.0000")])


def test_devolucion_con_abono_libera_capacidad_y_conserva_la_relacion(
        op03p, servicio, servicio_efectos, servicio_devoluciones, contexto, admin, cuenta):
    """§2.4 / §10.1: movimiento de entrada ANULADO, saldo restituido, capacidad
    del origen liberada, DEVOLUCION_DE conservada y el original vuelve a ser
    anulable por OP-03 (G-R1-A ya no lo bloquea)."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    dev = datos_devolucion(original, movimiento_id=uuid.uuid4(), conciliacion_id=uuid.uuid4(), cuenta_id=cuenta,
                           fecha_movimiento=F("2027-05-20"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    acumulado = ("SELECT COALESCE(sum(abs(e.importe_delta)), 0) FROM gapto.hecho_relaciones r JOIN "
                 "gapto.hechos_financieros d ON d.id = r.hecho_origen_id AND d.estado = 'ACTIVO' JOIN "
                 "gapto.hecho_efectos e ON e.hecho_id = d.id WHERE r.hecho_destino_id = %s "
                 "AND r.tipo_relacion = 'DEVOLUCION_DE'")
    assert _todas(admin, acumulado, (original,)) == [(D("45.0000"),)]
    antes = foto(admin, dev.hecho_id, [cuenta])
    ctx = nuevo(contexto)
    anular(op03p, contexto, admin, dev.hecho_id, ctx=ctx)
    comprobar_feliz(admin, contexto, ctx, dev.hecho_id, [cuenta], antes, [D("-45.0000")])
    assert _todas(admin, acumulado, (original,)) == [(D("0"),)]
    assert foto(admin, dev.hecho_id, [cuenta])["relaciones"] == antes["relaciones"] != []
    resultado = servicio.anular_hecho(nuevo(contexto), hecho_id=original,
                                      row_version_esperada=version_hecho(admin, contexto.owner_user_id, original),
                                      motivo_anulacion="original anulable tras OP-03P")
    assert resultado.estado == "ANULADO"


# ==================================================================
# Declaracion, request_id y motivo (§2.3.3, §8.1, §9)
# ==================================================================
@pytest.mark.parametrize("declaracion", [None, True])
def test_sin_declaracion_explicita_no_se_anula(op22, op03p, contexto, admin, cuenta, declaracion):
    g = gasto(op22, contexto, cuenta)
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho, movimiento_en_banco=declaracion)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "MOVIMIENTO_REAL_NO_ANULABLE")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_devolucion_con_abono_y_movimiento_en_banco_true(op03p, servicio, servicio_efectos, servicio_devoluciones,
                                                         contexto, admin, cuenta):
    original = crear_origen(servicio, servicio_efectos, contexto)
    dev = datos_devolucion(original, movimiento_id=uuid.uuid4(), conciliacion_id=uuid.uuid4(), cuenta_id=cuenta,
                           fecha_movimiento=F("2027-05-20"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    antes = foto(admin, dev.hecho_id, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, dev.hecho_id, movimiento_en_banco=True)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "MOVIMIENTO_REAL_NO_ANULABLE")
    assert foto(admin, dev.hecho_id, [cuenta]) == antes


def test_sin_request_id_y_sin_motivo(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    antes = foto(admin, g.hecho, [cuenta])
    sin = object.__new__(ContextoOperacion)
    for campo, valor in (("owner_user_id", contexto.owner_user_id), ("actor_tipo", "USUARIO"),
                         ("actor_user_id", contexto.owner_user_id), ("request_id", None)):
        object.__setattr__(sin, campo, valor)
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho, ctx=sin)
    rechazo(excinfo, CodigoError.ENTRADA_INVALIDA, "REQUEST_ID_AUSENTE")
    for motivo in ("", "   ", None):
        with pytest.raises(ErrorMotor) as excinfo:
            anular(op03p, contexto, admin, g.hecho, motivo=motivo)
        rechazo(excinfo, CodigoError.MOTIVO_AUSENTE)
    assert foto(admin, g.hecho, [cuenta]) == antes


# ==================================================================
# Evidencia persistida (§2.5, §2.3.7): siempre prevalece sobre la declaracion
# ==================================================================
@pytest.mark.parametrize("tabla", ["hechos_financieros", "movimientos_tesoreria"])
def test_origen_importado_hecho_y_movimiento(op22, op03p, contexto, admin, cuenta, tabla):
    g = gasto(op22, contexto, cuenta)
    importar(admin, contexto.owner_user_id, tabla, g.hecho if tabla == "hechos_financieros" else g.movimiento)
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "ORIGEN_IMPORTADO")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_ajuste_de_saldo(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET clase_movimiento = 'AJUSTE_SALDO' WHERE id = %s",
              (g.movimiento,))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    assert foto(admin, g.hecho, [cuenta]) == antes


@pytest.mark.parametrize("cierres, rechaza", [
    (["CERRADO"], True), (["CERRADO", "REABIERTO"], False), (["CERRADO", "REABIERTO", "CERRADO"], True),
    (["CERRADO@07"], False),
])
def test_periodo_cerrado(op22, op03p, contexto, admin, cuenta, cierres, rechaza):
    g = gasto(op22, contexto, cuenta)
    anterior = None
    for version, marca in enumerate(cierres, start=1):
        estado, _, mes = marca.partition("@")
        desde, hasta = ("2027-07-01", "2027-07-31") if mes == "07" else ("2027-06-01", "2027-06-30")
        anterior = cierre(admin, contexto.owner_user_id, estado, version, anterior, desde, hasta)
    antes = foto(admin, g.hecho, [cuenta])
    if not rechaza:
        anular(op03p, contexto, admin, g.hecho)
        return
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.PERIODO_CERRADO_SIN_POLITICA)
    assert foto(admin, g.hecho, [cuenta]) == antes


@pytest.mark.parametrize("inicio, rechaza", [("2027-06-02", True), ("2027-06-01", False)])
def test_ledger_de_la_cuenta(op22, op03p, contexto, admin, cuenta, inicio, rechaza):
    g = gasto(op22, contexto, cuenta)  # movimiento del 2027-06-01
    sql_admin(admin, "UPDATE gapto.cuentas SET fecha_inicio_ledger = %s, saldo_apertura = 0 WHERE id = %s",
              (F(inicio), cuenta))
    antes = foto(admin, g.hecho, [cuenta])
    if not rechaza:
        anular(op03p, contexto, admin, g.hecho)
        return
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "FECHA_ANTERIOR_INICIO")
    assert foto(admin, g.hecho, [cuenta]) == antes


@pytest.mark.parametrize("estado_reversion", ["ACTIVA", "ANULADA"])
def test_reversion_existente(op22, op03p, servicio_tesoreria, contexto, admin, cuenta, estado_reversion):
    g = gasto(op22, contexto, cuenta)
    servicio_tesoreria.revertir_movimiento(nuevo(contexto), DatosReversion(
        reversion_id=uuid.uuid4(), movimiento_original_id=g.movimiento, cuenta_id=cuenta,
        fecha_movimiento=F("2027-06-10"), importe=D("10.00")))
    if estado_reversion == "ANULADA":
        sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET estado = 'ANULADO', anulado_at = now() "
                         "WHERE reversion_de_movimiento_id = %s", (g.movimiento,))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "REVERSION_EXISTENTE")
    assert excinfo.value.sqlstate not in ("23503", "P0001")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_movimiento_compartido(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, "30.0000", movimiento="50.0000")
    otro = gasto(op22, contexto, cuenta, "20.0000")
    sql_admin(admin, "UPDATE gapto.hecho_movimientos_tesoreria SET movimiento_tesoreria_id = %s WHERE id = %s",
              (g.movimiento, otro.conciliacion))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "MOVIMIENTO_COMPARTIDO")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_dependencias_activas_g_r1_a(op22, op03p, servicio_devoluciones, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    servicio_devoluciones.devolver(nuevo(contexto), datos_devolucion(g.hecho, importe=D("10.0000"),
                                                                      fecha_hecho=F("2027-06-05")))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.HECHO_CON_REALIDAD_ASOCIADA, "DEPENDENCIAS_ACTIVAS")
    assert foto(admin, g.hecho, [cuenta]) == antes


# ==================================================================
# A-1, versiones (§6.3) e identidad (§6.4)
# ==================================================================
def test_a1_ya_anulado_y_sin_tesoreria(op22, op03p, servicio, servicio_efectos, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    movs = {m: v for m, v in datos(admin, contexto.owner_user_id, g.hecho).movimientos_row_version_esperadas.items()}
    anular(op03p, contexto, admin, g.hecho)
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho, movimientos=movs)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "HECHO_ANULADO")
    sin_tesoreria = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, sin_tesoreria)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "SIN_TESORERIA")


def test_versiones_desfasadas(op03p, servicio_transferencias, contexto, admin, cuenta, cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    owner = contexto.owner_user_id
    buenos = datos(admin, owner, t.hecho)
    antes = foto(admin, t.hecho, [cuenta, cuenta_destino])
    for malo in (dataclasses.replace(buenos, row_version_esperada=buenos.row_version_esperada - 1),
                 dataclasses.replace(buenos, movimientos_row_version_esperadas={
                     m: v - 1 if m == t.entrada else v for m, v in buenos.movimientos_row_version_esperadas.items()}),
                 dataclasses.replace(buenos, movimientos_row_version_esperadas={
                     t.salida: buenos.movimientos_row_version_esperadas[t.salida]})):
        with pytest.raises(ErrorMotor) as excinfo:
            op03p.anular_registro(nuevo(contexto), malo)
        rechazo(excinfo, CodigoError.VERSION_DESFASADA)
    assert foto(admin, t.hecho, [cuenta, cuenta_destino]) == antes


def test_idempotencia_e_identidad_reutilizada(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    otro = gasto(op22, contexto, cuenta, "20.0000")
    ctx = nuevo(contexto)
    pedido = datos(admin, contexto.owner_user_id, g.hecho)
    primera = op03p.anular_registro(ctx, pedido)
    n = len(auditorias(admin, ctx.request_id))
    despues = foto(admin, g.hecho, [cuenta])
    repetida = op03p.anular_registro(ctx, pedido)
    assert repetida.idempotente and repetida.hecho_row_version == primera.hecho_row_version
    assert repetida.movimientos == primera.movimientos
    assert len(auditorias(admin, ctx.request_id)) == n and foto(admin, g.hecho, [cuenta]) == despues
    otro_pedido = datos(admin, contexto.owner_user_id, otro.hecho)
    otras_versiones = {m: v + 5 for m, v in pedido.movimientos_row_version_esperadas.items()}
    for intento in (dataclasses.replace(pedido, motivo="otra razon"), otro_pedido,
                    dataclasses.replace(pedido, row_version_esperada=pedido.row_version_esperada + 5),
                    dataclasses.replace(pedido, movimientos_row_version_esperadas=otras_versiones)):
        with pytest.raises(ErrorMotor) as excinfo:
            op03p.anular_registro(ctx, intento)
        rechazo(excinfo, CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION)
    assert len(auditorias(admin, ctx.request_id)) == n
    assert _todas(admin, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (otro.hecho,)) == [("ACTIVO",)]


# ==================================================================
# Atomicidad (§2.3.6, §8.4): rollback exacto de datos y de auditoria
# ==================================================================
def _fallo_tras(monkeypatch, modulo, nombre: str, *, en_llamada: int = 1):
    original = getattr(modulo, nombre)
    llamadas = {"n": 0}

    def envoltorio(*a, **k):
        resultado = original(*a, **k)
        llamadas["n"] += 1
        if llamadas["n"] == en_llamada:
            raise RuntimeError(f"fallo inyectado tras {nombre} #{en_llamada}")
        return resultado

    monkeypatch.setattr(modulo, nombre, envoltorio)


def _cadena_de_causas(exc: BaseException) -> str:
    """La UnidadDeTrabajo clasifica el fallo (INTERNO); la causa viaja encadenada."""
    textos, vistos = [], set()
    while exc is not None and id(exc) not in vistos:
        vistos.add(id(exc))
        textos.append(str(exc))
        exc = exc.__cause__ or exc.__context__
    return " | ".join(textos)


@pytest.mark.parametrize("punto", ["tras_W3", "tras_W4_una_pata", "tras_W5", "durante_W6"])
def test_atomicidad_fallos_inyectados(op22, op03p, servicio_transferencias, servicio_previsiones, contexto, admin,
                                      cuenta, cuenta_destino, cadena, monkeypatch, punto):  # noqa: F811
    from app.repositories import anulacion_tesoreria_repository as repo

    if punto in ("tras_W3", "tras_W4_una_pata"):
        hecho = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino).hecho
    else:
        # W6 con trabajo real: el gasto ancla una cadena RODANTE (AMB-009 al anularlo).
        hecho = gasto(op22, contexto, cuenta, "45.0000", fecha=F("2027-02-02")).hecho
        vincular_rodante(servicio_previsiones, contexto, cadena["cabeza"], hecho, "45.0000", realizar=True)
    previsiones_antes = _todas(admin, "SELECT id, row_version, fecha_esperada_desde FROM gapto.previsiones "
                                      "ORDER BY id", ())
    antes = foto(admin, hecho, [cuenta, cuenta_destino])
    if punto == "tras_W3":
        _fallo_tras(monkeypatch, repo, "eliminar_transferencia")
    elif punto == "tras_W4_una_pata":
        _fallo_tras(monkeypatch, repo, "anular_movimiento")
    elif punto == "tras_W5":
        _fallo_tras(monkeypatch, repo, "anular_hecho")
    else:
        aplicar = op03p._aplicar_impacto

        def durante(sesion, plan):
            impacto = aplicar(sesion, plan)
            assert impacto["afectadas"], "la cadena debia quedar afectada"
            raise RuntimeError("fallo inyectado durante W6")

        object.__setattr__(op03p, "_aplicar_impacto", durante)
    ctx = nuevo(contexto)
    with pytest.raises(Exception) as fallo:
        anular(op03p, contexto, admin, hecho, ctx=ctx)
    assert "fallo inyectado" in _cadena_de_causas(fallo.value)
    assert foto(admin, hecho, [cuenta, cuenta_destino]) == antes  # fila, patas, conciliaciones, hecho
    assert _todas(admin, "SELECT id, row_version, fecha_esperada_desde FROM gapto.previsiones ORDER BY id",
                  ()) == previsiones_antes
    assert auditorias(admin, ctx.request_id) == []


def test_refactor_op03_aplicar_de_adquirir_es_la_misma_funcion():
    """§2.3.2 bis: impacto_correccion_ancla es la composicion exacta; OP-02,
    OP-03, OP-21P y OP-21T la siguen usando sin cambio (sus suites no cambian
    ninguna expectativa)."""
    import inspect

    from app.services import previsiones_service as ps

    fuente = inspect.getsource(ps.impacto_correccion_ancla)
    assert "aplicar_impacto_ancla(sesion, adquirir_impacto_ancla(sesion, hecho_id))" in fuente
    assert "_bloquear_reglas" not in inspect.getsource(ps.aplicar_impacto_ancla)
    assert "bloquear_prevision" not in inspect.getsource(ps.aplicar_impacto_ancla)


# ==================================================================
# Guardas restantes (una prueba por guarda, para su mutante, P7)
# ==================================================================
def test_a1_tipo_no_anulable(op22, op03p, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.hechos_financieros SET tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho "
                     "WHERE codigo = 'REEMBOLSO') WHERE id = %s", (g.hecho,))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_a1_inversion_fuera(op22, op03p, contexto, admin, cuenta):
    from test_140_f04_r3_op22 import como_owner, nueva_entidad

    g = gasto(op22, contexto, cuenta)
    entidad = nueva_entidad(admin, contexto.owner_user_id, "INVERSION")
    como_owner(admin, contexto.owner_user_id, "INSERT INTO gapto.hecho_entidades (id, owner_user_id, hecho_id, "
               "entidad_id, tipo_relacion, principal) VALUES (%s, %s, %s, %s, 'RELACIONADO_CON', false)",
               (uuid.uuid4(), contexto.owner_user_id, g.hecho, entidad))
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "INVERSION")
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_a3_movimiento_que_es_reversion(op22, op03p, servicio_tesoreria, contexto, admin, cuenta):
    """El movimiento del hecho es a su vez la reversion de otro (reversion_de)."""
    g = gasto(op22, contexto, cuenta)
    otro = gasto(op22, contexto, cuenta, "10.0000", tipo="INGRESO")
    sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = %s WHERE id = %s",
              (g.movimiento, otro.movimiento))
    antes = foto(admin, otro.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, otro.hecho)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "REVERSION_EXISTENTE")
    assert foto(admin, otro.hecho, [cuenta]) == antes


def test_a3_transferencia_sin_su_fila(op03p, servicio_transferencias, contexto, admin, cuenta, cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    sql_admin(admin, "DELETE FROM gapto.transferencias WHERE movimiento_salida_id = %s", (t.salida,))
    antes = foto(admin, t.hecho, [cuenta, cuenta_destino])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, t.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    assert foto(admin, t.hecho, [cuenta, cuenta_destino]) == antes


def test_a3_gasto_con_las_patas_de_una_transferencia(op03p, servicio_transferencias, contexto, admin, cuenta,
                                                     cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    sql_admin(admin, "UPDATE gapto.hechos_financieros SET tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho "
                     "WHERE codigo = 'GASTO') WHERE id = %s", (t.hecho,))
    antes = foto(admin, t.hecho, [cuenta, cuenta_destino])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, t.hecho)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    assert foto(admin, t.hecho, [cuenta, cuenta_destino]) == antes


def test_a5_periodo_cerrado_por_la_fecha_del_movimiento(op22, op03p, contexto, admin, cuenta):
    """El hecho cae en un periodo abierto; su movimiento, en uno cerrado."""
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET fecha_movimiento = '2027-07-05' WHERE id = %s",
              (g.movimiento,))
    cierre(admin, contexto.owner_user_id, "CERRADO", 1, None, "2027-07-01", "2027-07-31")
    antes = foto(admin, g.hecho, [cuenta])
    with pytest.raises(ErrorMotor) as excinfo:
        anular(op03p, contexto, admin, g.hecho)
    rechazo(excinfo, CodigoError.PERIODO_CERRADO_SIN_POLITICA)
    assert foto(admin, g.hecho, [cuenta]) == antes


def test_orden_de_fases_l_y_w(op22, op03p, servicio_previsiones, contexto, admin, cuenta, cadena,
                              monkeypatch):  # noqa: F811
    """§2.3.2 bis / §6.1: L3/L4 -> L5 (reglas y previsiones) -> L6 (movimientos)
    y, despues, W1..W5 -> W6. Nunca una adquisicion tras un movimiento ni una
    escritura antes de L6."""
    from app.repositories import anulacion_tesoreria_repository as repo
    from app.repositories import correccion_tesoreria_repository as repo_lect
    from app.services import integridad_posicion
    from app.services import previsiones_service as ps

    g = gasto(op22, contexto, cuenta, "45.0000", fecha=F("2027-02-02"))
    vincular_rodante(servicio_previsiones, contexto, cadena["cabeza"], g.hecho, "45.0000", realizar=True)
    orden: list[str] = []

    def espia(modulo, nombre, etiqueta):
        original = getattr(modulo, nombre)

        def envoltorio(*a, **k):
            orden.append(etiqueta)
            return original(*a, **k)
        monkeypatch.setattr(modulo, nombre, envoltorio)

    espia(integridad_posicion, "adquirir_raiz", "L3")
    espia(ps, "_bloquear_reglas", "L5")
    espia(repo_lect, "bloquear_movimientos", "L6")
    for nombre, etiqueta in (("eliminar_aportacion", "W1"), ("eliminar_conciliacion", "W2"),
                             ("eliminar_transferencia", "W3"), ("anular_movimiento", "W4"),
                             ("anular_hecho", "W5")):
        espia(repo, nombre, etiqueta)
    aplicar = op03p._aplicar_impacto

    def w6(sesion, plan):
        orden.append("W6")
        return aplicar(sesion, plan)
    object.__setattr__(op03p, "_aplicar_impacto", w6)
    anular(op03p, contexto, admin, g.hecho)
    compacto = [e for i, e in enumerate(orden) if i == 0 or orden[i - 1] != e]
    assert compacto == ["L3", "L5", "L6", "W2", "W4", "W5", "W6"], orden
