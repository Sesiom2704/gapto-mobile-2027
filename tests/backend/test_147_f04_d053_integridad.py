# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_147_f04_d053_integridad.py
# Ruta: tests/backend/test_147_f04_d053_integridad.py
# Descripcion: F04-D053 B1. Bateria CC-D053-1 y CC-D053-2 y casos del
#   dictamen v0.3 (B5 lectura (b), B6 L2 por hecho, OP-09 solo B5/B6).
#
#   Cada rechazo afirma el codigo INTEGRIDAD_POSICION_VIOLADA y su MOTIVO de
#   B9 (contexto_extra["motivo"] y prefijo del mensaje), nunca un error
#   incidental, y que no queda escritura.
#
#   Los historicos inconsistentes se fabrican con escrituras de FIXTURE que no
#   pasan por el validador (mismo patron que test_144::_reduccion_historica):
#   representan datos anteriores a F04-D053 o migrados.
#
#   Vias x reglas (dictamen v0.3): creacion A1 B2 B3 B4 B5 B6; OP-02 A1 B2 B3
#   B4 B5; OP-03 A1 B2 B3 B5 B6; OP-21 A1 B2 B3 B5 B6; OP-09 SOLO B5 B6.
# Version: 0.1.0
#   0.1.0 (F04-D053 B1 · v0.2/v0.3): bateria inicial.
# ============================================================
from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import uuid

import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor, MotivoIntegridadPosicion
from app.core.modelos import CamposCorreccion
from app.core.modelos_compuesto import DatosHechoCompuesto
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_posicion import (
    TIPO_DERECHO,
    TIPO_OBLIGACION,
    DatosCierre,
    DatosCondonacion,
    DatosCondonacionObligacion,
    DatosReembolso,
)
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.services.correcciones_service import DatosCorreccion
from app.services.neto_service import NetoService
from app.services.posiciones_service import PosicionesService
from conftest import leer_fila
from f08_motor import efecto
from test_109_op12_posiciones import COBRO, CONDONACION, PAGO, alta, delta, tesoreria_nueva
from test_140_f04_r3_op22 import FECHA as FECHA_OP22
from test_140_f04_r3_op22 import alta as alta_op22
from test_140_f04_r3_op22 import como_owner, hecho as hecho_op22, op22  # noqa: F401

D = decimal.Decimal
INICIO = dt.date(2026, 1, 1)
ALTA = dt.date(2026, 6, 1)
M = MotivoIntegridadPosicion


# ==================================================================
# Utilidades
# ==================================================================

def _rechazo(funcion, motivo: MotivoIntegridadPosicion) -> ErrorMotor:
    with pytest.raises(ErrorMotor) as info:
        funcion()
    error = info.value
    assert error.codigo is CodigoError.INTEGRIDAD_POSICION_VIOLADA, (error.codigo, error.mensaje)
    assert error.contexto_extra.get("motivo") == motivo.value, error.contexto_extra
    assert error.mensaje.startswith(f"{motivo.value}:")
    return error


def _version(admin, owner, hecho_id) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
                     (hecho_id,))[0]


def _version_entidad(admin, owner, entidad_id) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.entidades WHERE id = %s",
                     (entidad_id,))[0]


def _saldo(servicio_posiciones, contexto, entidad_id):
    return servicio_posiciones.saldo(contexto, entidad_id).saldo


def _posicion(servicio_posiciones, contexto, contraparte, *, tipo=TIPO_OBLIGACION,
              apertura="0", inicio=INICIO, fecha_alta=ALTA, importe="100.0000"):
    datos = alta(contraparte, tipo=tipo, nombre="D053",
                 saldo_apertura=None if apertura is None else D(apertura),
                 fecha_inicio_seguimiento=None if apertura is None else inicio,
                 fecha_hecho=fecha_alta, importe_inicial=None if importe is None else D(importe))
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos, resultado


def _historico(unidad, contexto, entidad_id, fecha, importe, *, naturaleza="DEUDA",
               codigo="GENERACION_DERECHO_OBLIGACION") -> tuple[uuid.UUID, uuid.UUID]:
    """Delta historico o migrado escrito SIN pasar por el validador."""
    servicio = PosicionesService(unidad)
    hecho_id, efecto_id = uuid.uuid4(), uuid.uuid4()

    def operacion(sesion):
        servicio._crear_hecho(sesion, hecho_id=hecho_id, tipo_hecho_codigo=codigo,
                              fecha_hecho=fecha, moneda="EUR", concepto="historico D053",
                              importe_total=abs(D(importe)))
        servicio._crear_delta(sesion, hecho_id=hecho_id, efecto_id=efecto_id,
                              vinculo_id=uuid.uuid4(), entidad_id=entidad_id,
                              tipo_efecto=naturaleza, importe_delta=D(importe),
                              concepto="historico D053")

    unidad.ejecutar(contexto, operacion, nombre="fixture-historico-d053")
    return hecho_id, efecto_id


def _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id, importe):
    return servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, hecho_id),
        motivo="D053", efectos_a_actualizar={efecto_id: {"importe_delta": D(importe)}}))


def _pagar(servicio_posiciones, contexto, admin, entidad_id, importe, fecha, cuenta, **extra):
    d = delta(importe, causa=PAGO, fecha_hecho=fecha, **extra)
    t = tesoreria_nueva(cuenta)
    servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, entidad_id),
        delta=d, movimiento=t)
    return d, t


def _condonar(servicio_posiciones, contexto, admin, entidad_id, importe, fecha, **extra):
    d = delta(importe, causa=CONDONACION, fecha_hecho=fecha, **extra.pop("delta_extra", {}))
    servicio_posiciones.condonar_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, entidad_id),
        datos=DatosCondonacionObligacion(delta=d, **extra))
    return d


def _movimiento(servicio_tesoreria, contexto, cuenta, importe):
    return servicio_tesoreria.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=dt.date(2026, 7, 1),
        importe=D(importe), clase_movimiento="OPERACION"))


def _op09(servicio_tesoreria, admin, contexto, hecho_id, movimiento, importe):
    return servicio_tesoreria.conciliar(
        contexto, DatosConciliacion(uuid.uuid4(), hecho_id, movimiento.movimiento_id, D(importe)),
        hecho_row_version_esperada=_version(admin, contexto.owner_user_id, hecho_id),
        movimiento_row_version_esperada=movimiento.row_version)


def _conciliado(admin, owner, hecho_id):
    return leer_fila(admin, owner, "SELECT COALESCE(sum(importe_asignado), 0) FROM "
                     "gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s", (hecho_id,))[0]


# ==================================================================
# A1 · saldo canonico (frontera >= inicio), uniforme y sin depender de H9
# ==================================================================

def test_a1_corpus_sintetico_80_a_40(unidad, servicio_posiciones, contexto, admin, contraparte) -> None:
    """Derecho ABIERTA de RV3: apertura 40 al corte y generador +40 anterior."""
    corte = dt.date(2026, 9, 5)
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO,
                         apertura="40.0000", inicio=corte, importe=None)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 3, 10), "40.0000",
               naturaleza="DERECHO_COBRO", codigo="GASTO")
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("40.0000")
    segmento = NetoService(unidad).posicion_neta(
        contexto, contraparte_actor_id=contraparte).segmento(contraparte, "EUR")
    assert segmento.neto == D("40.0000")


def test_a1_delta_exactamente_en_el_inicio_cuenta(servicio_posiciones, contexto, contraparte) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, inicio=ALTA, fecha_alta=ALTA)
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("100.0000")


def test_a1_delta_anterior_al_inicio_no_suma(unidad, servicio_posiciones, contexto, contraparte) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _historico(unidad, contexto, datos.entidad_id, INICIO - dt.timedelta(days=1), "-30.0000")
    _historico(unidad, contexto, datos.entidad_id, INICIO, "-10.0000")
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("90.0000")
    segmento = NetoService(unidad).posicion_neta(
        contexto, contraparte_actor_id=contraparte).segmento(contraparte, "EUR")
    assert segmento.neto == D("-90.0000")


def test_a1_no_depende_de_tipo_relacion_h9(unidad, servicio_posiciones, contexto, admin, contraparte) -> None:
    """H9: un vinculo AFECTA_A (RV3) y uno GENERADO_POR (runtime) cuentan igual;
    la unica frontera es la fecha."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    for fecha, importe in ((INICIO - dt.timedelta(days=1), "-25.0000"), (ALTA, "-5.0000")):
        hecho_id, efecto_id = _historico(unidad, contexto, datos.entidad_id, fecha, importe)
        como_owner(admin, contexto.owner_user_id,
                   "UPDATE gapto.hecho_entidades SET tipo_relacion = 'AFECTA_A' "
                   "WHERE hecho_id = %s AND efecto_id = %s", (hecho_id, efecto_id))
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(DISTINCT tipo_relacion) FROM gapto.hecho_entidades "
                     "WHERE entidad_id = %s", (datos.entidad_id,))[0] == 2
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("95.0000")


# ==================================================================
# B4 · fecha anterior al inicio (creacion, alta, OP-22, OP-02); B7
# ==================================================================

def test_b4_creacion_anterior_al_inicio(servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _rechazo(lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000",
                            INICIO - dt.timedelta(days=1), cuenta), M.FECHA_ANTERIOR_INICIO)
    _rechazo(lambda: _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000",
                               INICIO - dt.timedelta(days=1)), M.FECHA_ANTERIOR_INICIO)
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("100.0000")


def test_b4_creacion_exactamente_en_el_inicio(servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, inicio=ALTA)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000", ALTA, cuenta)
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("90.0000")


def test_b4_alta_anterior_al_inicio(servicio_posiciones, contexto, admin, contraparte) -> None:
    datos = alta(contraparte, tipo=TIPO_OBLIGACION, fecha_inicio_seguimiento=ALTA,
                 fecha_hecho=ALTA - dt.timedelta(days=1))
    _rechazo(lambda: servicio_posiciones.crear_posicion(contexto, datos), M.FECHA_ANTERIOR_INICIO)
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.entidades WHERE id = %s", (datos.entidad_id,))[0] == 0


def test_b4_alta_via_op22_anterior_al_inicio(op22, contexto, admin, contraparte) -> None:
    h = hecho_op22()
    a = dataclasses.replace(alta_op22(h.hecho_id, contraparte, tipo=TIPO_OBLIGACION, importe="40.0000"),
                            fecha_inicio_seguimiento=FECHA_OP22 + dt.timedelta(days=1))
    _rechazo(lambda: op22.registrar_hecho_compuesto(
        contexto, DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))], posiciones=[a])),
        M.FECHA_ANTERIOR_INICIO)
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (h.hecho_id,))[0] == 0


def test_b4_op02_fecha_hacia_antes_del_inicio(servicio, servicio_posiciones, contexto, admin,
                                              contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    d, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000", ALTA, cuenta)
    _rechazo(lambda: servicio.corregir_hecho(
        contexto, hecho_id=d.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, d.hecho_id),
        campos=CamposCorreccion(fecha_hecho=INICIO - dt.timedelta(days=1)), motivo="D053"),
        M.FECHA_ANTERIOR_INICIO)
    servicio.corregir_hecho(
        contexto, hecho_id=d.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, d.hecho_id),
        campos=CamposCorreccion(fecha_hecho=ALTA + dt.timedelta(days=3)), motivo="D053")


def test_b7_indeterminado_sin_b4_ni_saldo(unidad, servicio_posiciones, servicio_correcciones, contexto,
                                          admin, contraparte, cuenta) -> None:
    """Saldo indeterminado (historico migrado): ni B4 ni la regla de saldo."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=None)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "500.0000", dt.date(2020, 1, 1), cuenta)
    hecho_id, efecto_id = _historico(unidad, contexto, datos.entidad_id, ALTA, "-10.0000")
    _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id, "-999.0000")
    assert not _saldo(servicio_posiciones, contexto, datos.entidad_id).conocido


# ==================================================================
# B2 · ningun cierre de fecha negativo (creacion, OP-02, OP-03, OP-21)
# ==================================================================

def test_b2_creacion_intermedio_negativo_final_positivo(servicio_posiciones, contexto, admin,
                                                        contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    error = _rechazo(lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                                    dt.date(2026, 3, 1), cuenta), M.SALDO_NEGATIVO)
    assert error.contexto_extra["fecha"] == "2026-03-01"
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("100.0000")


def test_b2_op21_saldo_final_negativo(servicio_posiciones, servicio_correcciones, contexto, admin,
                                      contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    d, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                  dt.date(2026, 6, 15), cuenta)
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id,
                                   "-999.0000"), M.SALDO_NEGATIVO)
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, datos.hecho_id,
                                   datos.efecto_id, "30.0000"), M.SALDO_NEGATIVO)


def test_b2_op03_anular_el_alta(servicio, servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 15), cuenta)
    _rechazo(lambda: servicio.anular_hecho(
        contexto, hecho_id=datos.hecho_id,
        row_version_esperada=_version(admin, contexto.owner_user_id, datos.hecho_id),
        motivo_anulacion="D053"), M.SALDO_NEGATIVO)


def test_b2_op02_fecha_deja_intermedio_negativo(servicio, servicio_posiciones, contexto, admin,
                                                contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    d, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                  dt.date(2026, 6, 15), cuenta)
    _rechazo(lambda: servicio.corregir_hecho(
        contexto, hecho_id=d.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, d.hecho_id),
        campos=CamposCorreccion(fecha_hecho=dt.date(2026, 3, 1)), motivo="D053"), M.SALDO_NEGATIVO)


def test_b2_op03_anular_reduccion_mejora_y_pasa(servicio, servicio_posiciones, contexto, admin,
                                                contraparte) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    d = _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "30.0000", dt.date(2026, 6, 15))
    servicio.anular_hecho(contexto, hecho_id=d.hecho_id,
                          row_version_esperada=_version(admin, contexto.owner_user_id, d.hecho_id),
                          motivo_anulacion="D053")
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("100.0000")


# ==================================================================
# B3 (a) · crear / agravar / mantener / mejorar, fecha a fecha
# ==================================================================

@pytest.fixture()
def incoherente(unidad, servicio_posiciones, contexto, contraparte):
    """Historico con S(2026-03-05) = -10: delta -10 antes del alta (+100)."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    hecho_id, efecto_id = _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 3, 5), "-10.0000")
    return datos, hecho_id, efecto_id


def test_b3_agravar_se_rechaza(servicio_correcciones, contexto, admin, incoherente) -> None:
    _, hecho_id, efecto_id = incoherente
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id,
                                   "-40.0000"), M.SALDO_NEGATIVO)


def test_b3_mantener_no_se_bloquea(servicio, servicio_correcciones, contexto, admin, incoherente) -> None:
    _, hecho_id, efecto_id = incoherente
    servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, hecho_id),
        motivo="D053", efectos_a_actualizar={efecto_id: {"descripcion": "captura"}}))
    servicio.corregir_hecho(contexto, hecho_id=hecho_id,
                            row_version_esperada=_version(admin, contexto.owner_user_id, hecho_id),
                            campos=CamposCorreccion(concepto="mantener"), motivo="D053")


def test_b3_mejorar_no_se_bloquea(servicio_posiciones, servicio_correcciones, contexto, admin,
                                  incoherente) -> None:
    datos, hecho_id, efecto_id = incoherente
    _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id, "-5.0000")
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("95.0000")


def test_b3_crear_sobre_posicion_sana(servicio_posiciones, servicio_correcciones, contexto, admin,
                                      contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _rechazo(lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000",
                            dt.date(2026, 2, 1), cuenta), M.SALDO_NEGATIVO)


def test_b3_discriminante_a_frente_a_b(servicio, contexto, admin, incoherente) -> None:
    """Q2: -10 el dia 5 -> -10 los dias 3 y 5. (a) rechaza; (b) admitiria."""
    _, hecho_id, _ = incoherente
    _rechazo(lambda: servicio.corregir_hecho(
        contexto, hecho_id=hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, hecho_id),
        campos=CamposCorreccion(fecha_hecho=dt.date(2026, 3, 3)), motivo="D053"), M.SALDO_NEGATIVO)


def test_b3_historico_migrado_saldo_conocido_correccion_rechazada(
        unidad, servicio_posiciones, servicio_correcciones, contexto, contraparte, admin) -> None:
    corte = dt.date(2026, 9, 5)
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO,
                         apertura="40.0000", inicio=corte, importe=None)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 3, 10), "40.0000",
               naturaleza="DERECHO_COBRO", codigo="GASTO")
    hecho_id, efecto_id = _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 9, 20), "-10.0000",
                                     naturaleza="DERECHO_COBRO", codigo="REEMBOLSO")
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id,
                                   "-50.0000"), M.SALDO_NEGATIVO)


def test_b3_historico_migrado_saldo_indeterminado_no_rechazado(
        unidad, servicio_posiciones, servicio_correcciones, contexto, contraparte, admin) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO, apertura=None,
                         importe=None)
    hecho_id, efecto_id = _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 9, 20), "-10.0000",
                                     naturaleza="DERECHO_COBRO", codigo="REEMBOLSO")
    _op21_importe(servicio_correcciones, admin, contexto, hecho_id, efecto_id, "-50.0000")


# ==================================================================
# CC-D053-2 · E1 contra el saldo canonico (B10: INGRESO <= condonado <= saldo)
# ==================================================================

@pytest.mark.parametrize("con_ingreso", [False, True], ids=["sin_ingreso", "con_ingreso"])
def test_e1_condonacion_por_encima_del_saldo(servicio_posiciones, servicio_correcciones, contexto, admin,
                                             contraparte, con_ingreso) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    extra = ({"importe_ingreso": D("40.0000"), "efecto_ingreso_id": uuid.uuid4(), "presupuestable": True}
             if con_ingreso else {})
    d = _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                  dt.date(2026, 6, 15), **extra)
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id,
                                   "-999.0000"), M.SALDO_NEGATIVO)
    # Dentro del saldo canonico la correccion de lo condonado sigue siendo valida.
    _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id, "-90.0000")


def test_e1_condonacion_de_derecho_por_encima_del_saldo(servicio_posiciones, servicio_correcciones,
                                                        contexto, admin, contraparte) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO)
    d = delta("40.0000", causa=CONDONACION, fecha_hecho=dt.date(2026, 6, 15))
    servicio_posiciones.condonar_derecho(
        contexto, entidad_id=datos.entidad_id,
        entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, datos.entidad_id),
        datos=DatosCondonacion(delta=d))
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id,
                                   "-101.0000"), M.SALDO_NEGATIVO)


@pytest.mark.parametrize("operacion", ["cobro", "pago"])
def test_e1_reembolso_inflado_por_encima_del_saldo(servicio_posiciones, servicio_correcciones, contexto,
                                                   admin, contraparte, cuenta, operacion) -> None:
    """Casos S1/S2 de la investigacion v0.6, ahora contra el saldo canonico."""
    tipo = TIPO_DERECHO if operacion == "cobro" else TIPO_OBLIGACION
    datos, creada = _posicion(servicio_posiciones, contexto, contraparte, tipo=tipo)
    d = delta("40.0000", causa=COBRO if operacion == "cobro" else PAGO)
    if operacion == "cobro":
        servicio_posiciones.reembolsar(contexto, entidad_id=datos.entidad_id,
                                       entidad_row_version_esperada=creada.entidad_row_version,
                                       datos=DatosReembolso(delta=d, tesoreria=tesoreria_nueva(cuenta)))
    else:
        servicio_posiciones.reducir_obligacion(contexto, entidad_id=datos.entidad_id,
                                               entidad_row_version_esperada=creada.entidad_row_version,
                                               delta=d, movimiento=tesoreria_nueva(cuenta))
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id,
                                   "-101.0000"), M.SALDO_NEGATIVO)


# ==================================================================
# B5 · lectura (b): posicion cerrada inmutable en lo que le pertenece
# ==================================================================

@pytest.fixture()
def cerrada(servicio_posiciones, contexto, admin, contraparte, cuenta):
    """Obligacion 100: pago 60 y condonacion 40 que la cierra CONDONADA."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, conciliacion = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000",
                                dt.date(2026, 6, 15), cuenta)
    cond = _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 20),
                     delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA",
                                                        fecha_cierre=dt.date(2026, 6, 20))})
    return datos, pago, conciliacion, cond


def test_b5_importe_rechazado(servicio_correcciones, contexto, admin, cerrada) -> None:
    datos, pago, _, _ = cerrada
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, pago.hecho_id, pago.efecto_id,
                                   "-50.0000"), M.POSICION_CERRADA)


def test_b5_fecha_sin_cambio_de_saldo_rechazada(servicio, contexto, admin, cerrada) -> None:
    _, pago, _, _ = cerrada
    _rechazo(lambda: servicio.corregir_hecho(
        contexto, hecho_id=pago.hecho_id,
        row_version_esperada=_version(admin, contexto.owner_user_id, pago.hecho_id),
        campos=CamposCorreccion(fecha_hecho=dt.date(2026, 6, 16)), motivo="D053"), M.POSICION_CERRADA)


def test_b5_anulacion_rechazada(servicio, contexto, admin, cerrada) -> None:
    _, _, _, cond = cerrada
    _rechazo(lambda: servicio.anular_hecho(
        contexto, hecho_id=cond.hecho_id,
        row_version_esperada=_version(admin, contexto.owner_user_id, cond.hecho_id),
        motivo_anulacion="D053"), M.POSICION_CERRADA)


def test_b5_retirar_conciliacion_rechazada(servicio_correcciones, contexto, admin, cerrada) -> None:
    """La retirada de una asignacion solo existe en OP-21 (OP-09 solo anade)."""
    _, pago, conciliacion, _ = cerrada
    _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=pago.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, pago.hecho_id),
        motivo="D053", conciliaciones_a_eliminar=(conciliacion.conciliacion_id,))), M.POSICION_CERRADA)


def test_b5_op09_anadir_asignacion_rechazada(servicio_tesoreria, contexto, admin, cuenta, cerrada) -> None:
    _, pago, _, _ = cerrada
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-5.0000")
    _rechazo(lambda: _op09(servicio_tesoreria, admin, contexto, pago.hecho_id, mov, "-5.0000"),
             M.POSICION_CERRADA)


def test_b5_campos_ajenos_a_la_posicion_corregibles(servicio, contexto, admin, cerrada) -> None:
    _, pago, _, _ = cerrada
    servicio.corregir_hecho(contexto, hecho_id=pago.hecho_id,
                            row_version_esperada=_version(admin, contexto.owner_user_id, pago.hecho_id),
                            campos=CamposCorreccion(concepto="captura corregida"), motivo="D053")


def test_b5_categoria_del_gasto_de_condonacion_corregible(servicio_posiciones, servicio_correcciones,
                                                          contexto, admin, contraparte) -> None:
    """Condonacion de derecho con GASTO declarado que cierra la posicion: la
    categoria del GASTO no pertenece a la posicion -> OK; su DERECHO_COBRO -> STOP."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO)
    gasto_id = uuid.uuid4()
    d = delta("100.0000", causa=CONDONACION, fecha_hecho=dt.date(2026, 6, 15),
              cierre=DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=dt.date(2026, 6, 15)))
    servicio_posiciones.condonar_derecho(
        contexto, entidad_id=datos.entidad_id,
        entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, datos.entidad_id),
        datos=DatosCondonacion(delta=d, declara_gasto_soportado=True, declara_coste_no_reconocido=True,
                               efecto_gasto_id=gasto_id, presupuestable=False))
    categoria = uuid.uuid4()
    como_owner(admin, contexto.owner_user_id,
               "INSERT INTO gapto.categorias_financieras (id, owner_user_id, nombre, ambito, "
               "presupuestable_default) VALUES (%s,%s,'Condonaciones','GASTO',false)",
               (categoria, contexto.owner_user_id))
    servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=d.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, d.hecho_id),
        motivo="D053", efectos_a_actualizar={gasto_id: {"categoria_id": categoria}}))
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT categoria_id FROM gapto.hecho_efectos WHERE id = %s", (gasto_id,))[0] == categoria
    # Ampliar lo condonado (-100 -> -110) no dispara I5 de E1: el rechazo es B5.
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, d.hecho_id, d.efecto_id,
                                   "-110.0000"), M.POSICION_CERRADA)


# ==================================================================
# B6 · L2 por hecho; CONDONACION sin asignaciones; OP-09 solo B5/B6
# ==================================================================

def test_b6_retirar_conciliacion_de_reembolso(servicio_posiciones, servicio_correcciones, contexto, admin,
                                              contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, conciliacion = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                                dt.date(2026, 6, 15), cuenta)
    _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=pago.hecho_id, row_version_esperada=_version(admin, contexto.owner_user_id, pago.hecho_id),
        motivo="D053", conciliaciones_a_eliminar=(conciliacion.conciliacion_id,))),
        M.CONCILIACION_INCOMPATIBLE)


def test_b6_op21_descuadra_efecto_y_conciliacion(servicio_posiciones, servicio_correcciones, contexto,
                                                 admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                     dt.date(2026, 6, 15), cuenta)
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, pago.hecho_id, pago.efecto_id,
                                   "-30.0000"), M.CONCILIACION_INCOMPATIBLE)


def test_b6_nm_valido_un_movimiento_entre_dos_hechos(servicio_posiciones, servicio_tesoreria, contexto,
                                                     admin, contraparte, cuenta) -> None:
    """N:M: un movimiento de -100 repartido entre dos pagos (40 y 60)."""
    from app.core.modelos_posicion import DatosTesoreriaReembolso

    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-100.0000")
    version = mov.row_version
    for importe in ("40.0000", "60.0000"):
        d = delta(importe, causa=PAGO, fecha_hecho=dt.date(2026, 7, 1))
        r = servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=datos.entidad_id,
            entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, datos.entidad_id),
            delta=d, movimiento=DatosTesoreriaReembolso(
                conciliacion_id=uuid.uuid4(), movimiento_id=mov.movimiento_id,
                movimiento_row_version_esperada=version))
        version = r.movimiento_row_version
        assert _conciliado(admin, contexto.owner_user_id, d.hecho_id) == -D(importe)
    assert _saldo(servicio_posiciones, contexto, datos.entidad_id).importe == D("0.0000")


def test_b6_op09_dejaria_incompatible(servicio_posiciones, servicio_tesoreria, contexto, admin,
                                      contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                     dt.date(2026, 6, 15), cuenta)
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-10.0000")
    _rechazo(lambda: _op09(servicio_tesoreria, admin, contexto, pago.hecho_id, mov, "-10.0000"),
             M.CONCILIACION_INCOMPATIBLE)


@pytest.fixture()
def reembolso_historico(servicio_posiciones, contexto, admin, contraparte, cuenta):
    """REEMBOLSO de pago 40 conciliado SOLO por -30 (dato anterior a D053):
    diferencia 10, fabricada por fixture sobre la conciliacion."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, conciliacion = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",
                                dt.date(2026, 6, 15), cuenta)
    como_owner(admin, contexto.owner_user_id,
               "UPDATE gapto.hecho_movimientos_tesoreria SET importe_asignado = -30 WHERE id = %s",
               (conciliacion.conciliacion_id,))
    return datos, pago


@pytest.mark.parametrize("importe, rechaza", [
    ("-5.0000", False),   # -35 frente a -40: reduce la diferencia
    ("-20.0000", False),  # -50 frente a -40: diferencia 10, se mantiene
    ("-25.0000", True),   # -55 frente a -40: agrava (15 > 10)
], ids=["reducir", "mantener", "agravar"])
def test_b6_op09_historico_inconsistente(servicio_tesoreria, contexto, admin, cuenta, reembolso_historico,
                                         importe, rechaza) -> None:
    _, pago = reembolso_historico
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, importe)
    llamada = lambda: _op09(servicio_tesoreria, admin, contexto, pago.hecho_id, mov, importe)  # noqa: E731
    if rechaza:
        _rechazo(llamada, M.CONCILIACION_INCOMPATIBLE)
    else:
        llamada()


def test_b6_op09_condonacion_sin_asignaciones(servicio_posiciones, servicio_tesoreria, contexto, admin,
                                              contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    cond = _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000", dt.date(2026, 6, 15))
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-10.0000")
    _rechazo(lambda: _op09(servicio_tesoreria, admin, contexto, cond.hecho_id, mov, "-10.0000"),
             M.CONCILIACION_INCOMPATIBLE)


def test_b6_op09_hecho_ajeno_a_la_posicion(servicio, servicio_tesoreria, contexto, admin, cuenta) -> None:
    from test_106_op06_op07_aportaciones import datos_hecho

    datos = datos_hecho()
    servicio.crear_hecho(contexto, datos)
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-10.0000")
    _op09(servicio_tesoreria, admin, contexto, datos.hecho_id, mov, "-10.0000")


def test_b6_op09_no_aplica_reglas_de_saldo(unidad, servicio_posiciones, servicio_tesoreria, contexto,
                                           admin, cuenta, incoherente) -> None:
    """OP-09 sobre el hecho del alta de una posicion con saldo intermedio
    negativo preexistente: B5 y B6 no lo rechazan y la regla de saldo no se
    evalua (dictamen v0.3: OP-09 nunca aplica reglas de saldo)."""
    datos, _, _ = incoherente
    mov = _movimiento(servicio_tesoreria, contexto, cuenta, "-3.0000")
    _op09(servicio_tesoreria, admin, contexto, datos.hecho_id, mov, "-3.0000")
