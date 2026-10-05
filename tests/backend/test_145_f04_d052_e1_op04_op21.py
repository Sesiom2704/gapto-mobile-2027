# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_145_f04_d052_e1_op04_op21.py
# Ruta: tests/backend/test_145_f04_d052_e1_op04_op21.py
# Descripcion: F04-D052 enmienda E1. Frontera economica de OP-04 y OP-21
#   sobre hechos de reduccion, por ARQUETIPO:
#     I1 sin GASTO/INGRESO creado por OP-04/OP-21 en un hecho CONDONACION;
#     I2 sin reclasificar hacia/desde GASTO/INGRESO en CONDONACION (OP-21);
#     I3 el efecto declarado no supera |efecto de posicion negativo| del hecho;
#     I4 como maximo un efecto declarado por hecho CONDONACION;
#     I5 corregir el efecto de posicion no deja lo condonado por debajo del
#        declarado;
#     I6 un hecho REEMBOLSO no admite INGRESO ni GASTO negativo (INV-12).
#   Cada rechazo afirma el codigo semantico de E1 y la etiqueta de la guarda,
#   NUNCA el de localizacion: por eso varios casos se repiten tras pasar la
#   localizacion a DESCONOCIDA por OP-02 (la via que eludia la frontera
#   territorial en la investigacion v0.4). Se repiten A1-A4, B1/B2 y C1-C3 del
#   INFORME. Regresion: GENERACION_DERECHO_OBLIGACION no se ve afectado.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import CamposCorreccion, DatosCreacionHecho
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_posicion import (
    DatosCondonacion,
    DatosCondonacionObligacion,
    DatosReembolso,
    TIPO_OBLIGACION,
)
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from test_109_op12_posiciones import (
    COBRO,
    CONDONACION,
    PAGO,
    alta,
    delta,
    tesoreria_nueva,
)

D = decimal.Decimal
COND = CodigoError.CONDONACION_EFECTO_NO_PERMITIDO
REEM = CodigoError.REEMBOLSO_EFECTO_NO_PERMITIDO


# ==================================================================
# Utilidades
# ==================================================================

def _ef(tipo: str, importe: str, efecto_id: uuid.UUID | None = None) -> DatosEfecto:
    return DatosEfecto(
        efecto_id=efecto_id or uuid.uuid4(), tipo_efecto=tipo,
        importe_delta=D(importe), estado_atribucion="NO_DISPONIBLE",
    )


def _version(admin, contexto, hecho_id) -> int:
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
                     (hecho_id,))[0]


def _efectos(admin, contexto, hecho_id) -> list:
    fila = leer_fila(
        admin, contexto.owner_user_id,
        "SELECT coalesce(json_agg(json_build_array(tipo_efecto, importe_delta::text) "
        "ORDER BY tipo_efecto, importe_delta), '[]') FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s", (hecho_id,))
    return fila[0]


def _rechazo(fn, codigo, etiqueta: str) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        fn()
    assert excinfo.value.codigo is codigo, excinfo.value
    assert excinfo.value.mensaje.startswith(etiqueta), excinfo.value.mensaje


def _op04(servicio_efectos, contexto, admin, hecho_id, *efectos, presupuestable=True):
    return servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id,
        row_version_esperada=_version(admin, contexto, hecho_id),
        efectos=list(efectos), presupuestable=presupuestable,
    )


def _op21(servicio_correcciones, contexto, admin, hecho_id, **cambios):
    return servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=_version(admin, contexto, hecho_id),
        motivo="F04-D052 E1", **cambios,
    ))


def _a_desconocida(servicio, contexto, admin, hecho_id) -> None:
    """OP-02: la via que eludia la frontera territorial (investigacion v0.4)."""
    servicio.corregir_hecho(
        contexto, hecho_id=hecho_id,
        row_version_esperada=_version(admin, contexto, hecho_id),
        campos=CamposCorreccion(estado_localizacion="DESCONOCIDA"),
        motivo="F04-D052 E1: localizacion",
    )


# ==================================================================
# Fixtures: hechos de reduccion reales escritos por PosicionesService
# ==================================================================

@pytest.fixture()
def condonacion_sin_declarado(servicio_posiciones, contexto, contraparte):
    """Obligacion 100 condonada en 40, SIN INGRESO: (hecho_id, efecto_deuda_id)."""
    a = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="E1 sin declarado")
    r = servicio_posiciones.crear_posicion(contexto, a)
    d = delta("40.0000", causa=CONDONACION)
    servicio_posiciones.condonar_obligacion(
        contexto, entidad_id=a.entidad_id,
        entidad_row_version_esperada=r.entidad_row_version,
        datos=DatosCondonacionObligacion(delta=d))
    return d.hecho_id, d.efecto_id


@pytest.fixture()
def condonacion_con_ingreso(servicio_posiciones, contexto, contraparte):
    """Obligacion 100 condonada en 40 con INGRESO declarado 10:
    (hecho_id, efecto_deuda_id, efecto_ingreso_id)."""
    a = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="E1 con INGRESO")
    r = servicio_posiciones.crear_posicion(contexto, a)
    d, ingreso = delta("40.0000", causa=CONDONACION), uuid.uuid4()
    servicio_posiciones.condonar_obligacion(
        contexto, entidad_id=a.entidad_id,
        entidad_row_version_esperada=r.entidad_row_version,
        datos=DatosCondonacionObligacion(
            delta=d, importe_ingreso=D("10.0000"), efecto_ingreso_id=ingreso,
            presupuestable=True))
    return d.hecho_id, d.efecto_id, ingreso


@pytest.fixture()
def condonacion_derecho_con_gasto(servicio_posiciones, contexto, contraparte):
    """Derecho 100 condonado en 30 con GASTO declarado (F04-D015 §7)."""
    a = alta(contraparte, nombre="E1 derecho con GASTO")
    r = servicio_posiciones.crear_posicion(contexto, a)
    d, gasto = delta("30.0000", causa=CONDONACION), uuid.uuid4()
    servicio_posiciones.condonar_derecho(
        contexto, entidad_id=a.entidad_id,
        entidad_row_version_esperada=r.entidad_row_version,
        datos=DatosCondonacion(
            delta=d, declara_gasto_soportado=True, declara_coste_no_reconocido=True,
            efecto_gasto_id=gasto, presupuestable=True))
    return d.hecho_id, d.efecto_id, gasto


@pytest.fixture(params=["cobro_OP14", "pago_OP12B"])
def reembolso(request, servicio_posiciones, contexto, contraparte, cuenta):
    """Hecho REEMBOLSO real (cobro u OP-12B pago): (hecho_id, efecto_posicion_id)."""
    if request.param == "cobro_OP14":
        a = alta(contraparte, nombre="E1 derecho")
        r = servicio_posiciones.crear_posicion(contexto, a)
        d = delta("40.0000", causa=COBRO)
        servicio_posiciones.reembolsar(
            contexto, entidad_id=a.entidad_id,
            entidad_row_version_esperada=r.entidad_row_version,
            datos=DatosReembolso(delta=d, tesoreria=tesoreria_nueva(cuenta)))
    else:
        a = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="E1 obligacion")
        r = servicio_posiciones.crear_posicion(contexto, a)
        d = delta("40.0000", causa=PAGO)
        servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=a.entidad_id,
            entidad_row_version_esperada=r.entidad_row_version,
            delta=d, movimiento=tesoreria_nueva(cuenta))
    return d.hecho_id, d.efecto_id


# ==================================================================
# I1 · CONDONACION sin declarado: ni OP-04 ni OP-21 crean GASTO/INGRESO
#      (B1/B2 del INFORME, tambien tras OP-02 a DESCONOCIDA)
# ==================================================================

@pytest.mark.parametrize("localizacion", ["NO_APLICA", "DESCONOCIDA"])
@pytest.mark.parametrize("tipo", ["INGRESO", "GASTO"])
def test_i1_op04_no_crea_gasto_ni_ingreso_en_condonacion(
    servicio, servicio_efectos, contexto, admin, condonacion_sin_declarado,
    tipo, localizacion,
) -> None:
    hecho_id, _ = condonacion_sin_declarado
    if localizacion == "DESCONOCIDA":
        _a_desconocida(servicio, contexto, admin, hecho_id)
    antes = _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op04(servicio_efectos, contexto, admin, hecho_id,
                           _ef(tipo, "10.0000")), COND, "I1:")
    assert _efectos(admin, contexto, hecho_id) == antes


@pytest.mark.parametrize("localizacion", ["NO_APLICA", "DESCONOCIDA"])
@pytest.mark.parametrize("tipo", ["INGRESO", "GASTO"])
def test_i1_op21_no_crea_gasto_ni_ingreso_en_condonacion(
    servicio, servicio_correcciones, contexto, admin, condonacion_sin_declarado,
    tipo, localizacion,
) -> None:
    hecho_id, _ = condonacion_sin_declarado
    if localizacion == "DESCONOCIDA":
        _a_desconocida(servicio, contexto, admin, hecho_id)
    antes = _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           presupuestable=True,
                           efectos_a_crear=(_ef(tipo, "10.0000"),)), COND, "I1:")
    assert _efectos(admin, contexto, hecho_id) == antes


# ==================================================================
# I2 · OP-21 no reclasifica hacia ni desde GASTO/INGRESO en CONDONACION
# ==================================================================

@pytest.mark.parametrize("hacia", ["INGRESO", "GASTO"])
def test_i2_op21_no_convierte_el_efecto_de_posicion_en_gasto_o_ingreso(
    servicio_correcciones, contexto, admin, condonacion_sin_declarado, hacia
) -> None:
    """Incluye DEUDA -> INGRESO (y DEUDA -> GASTO)."""
    hecho_id, efecto_deuda = condonacion_sin_declarado
    antes = _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id, presupuestable=True,
        efectos_a_actualizar={efecto_deuda: {"tipo_efecto": hacia,
                                             "importe_delta": D("40.0000")}}),
        COND, "I2:")
    assert _efectos(admin, contexto, hecho_id) == antes


def test_i2_op21_derecho_cobro_a_gasto_rechazado(
    servicio_correcciones, contexto, admin, condonacion_derecho_con_gasto
) -> None:
    """DERECHO_COBRO -> GASTO en una condonacion de derecho."""
    hecho_id, efecto_derecho, _ = condonacion_derecho_con_gasto
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id,
        efectos_a_actualizar={efecto_derecho: {"tipo_efecto": "GASTO",
                                               "importe_delta": D("30.0000")}}),
        COND, "I2:")


@pytest.mark.parametrize("hacia", ["GASTO", "DEUDA"])
def test_i2_op21_no_cambia_la_naturaleza_del_declarado(
    servicio_correcciones, contexto, admin, condonacion_con_ingreso, hacia
) -> None:
    hecho_id, _, ingreso = condonacion_con_ingreso
    antes = _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id,
        efectos_a_actualizar={ingreso: {"tipo_efecto": hacia}}), COND, "I2:")
    assert _efectos(admin, contexto, hecho_id) == antes


# ==================================================================
# I3 / I5 · el declarado no supera lo condonado (A3, C2 del INFORME)
# ==================================================================

@pytest.mark.parametrize("importe", ["40.0001", "999.0000"])
def test_i3_op21_declarado_por_encima_de_lo_condonado(
    servicio_correcciones, contexto, admin, condonacion_con_ingreso, importe
) -> None:
    hecho_id, _, ingreso = condonacion_con_ingreso
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id,
        efectos_a_actualizar={ingreso: {"importe_delta": D(importe)}}),
        COND, "I3/I5:")
    assert _efectos(admin, contexto, hecho_id) == [["DEUDA", "-40.0000"],
                                                   ["INGRESO", "10.0000"]]


def test_i3_c2_gasto_de_condonacion_de_derecho_inflado(
    servicio_correcciones, contexto, admin, condonacion_derecho_con_gasto
) -> None:
    hecho_id, _, gasto = condonacion_derecho_con_gasto
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id,
        efectos_a_actualizar={gasto: {"importe_delta": D("999.0000")}}),
        COND, "I3/I5:")


def test_i5_op21_reducir_lo_condonado_por_debajo_del_declarado(
    servicio_correcciones, contexto, admin, condonacion_con_ingreso
) -> None:
    """DEUDA -40 -> -5 con INGRESO 10 declarado: lo condonado (5) < 10."""
    hecho_id, efecto_deuda, _ = condonacion_con_ingreso
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id,
        efectos_a_actualizar={efecto_deuda: {"importe_delta": D("-5.0000")}}),
        COND, "I3/I5:")
    assert _efectos(admin, contexto, hecho_id) == [["DEUDA", "-40.0000"],
                                                   ["INGRESO", "10.0000"]]


@pytest.mark.parametrize("cambios", [
    {"ingreso": {"importe_delta": D("25.0000")}},
    {"ingreso": {"importe_delta": D("40.0000")}},
    {"ingreso": {"descripcion": "correccion de captura"}},
    {"deuda": {"importe_delta": D("-15.0000")}},
], ids=["ingreso_25", "ingreso_igual_condonado", "descripcion", "deuda_15_sobre_10"])
def test_correccion_valida_del_declarado_o_de_lo_condonado_ok(
    servicio_correcciones, contexto, admin, condonacion_con_ingreso, cambios
) -> None:
    """Sin cambiar naturaleza y dentro del tope: OP-21 sigue corrigiendo."""
    hecho_id, efecto_deuda, ingreso = condonacion_con_ingreso
    destino = {"ingreso": ingreso, "deuda": efecto_deuda}
    _op21(servicio_correcciones, contexto, admin, hecho_id,
          efectos_a_actualizar={destino[k]: v for k, v in cambios.items()})
    efectos = dict(_efectos(admin, contexto, hecho_id))
    assert set(efectos) == {"DEUDA", "INGRESO"}


# ==================================================================
# I4 · como maximo un declarado (A1, A2, A4, C1, C3 del INFORME)
# ==================================================================

@pytest.mark.parametrize("importe", ["30.0000", "100.0000"], ids=["A1", "A2"])
def test_i4_op04_segundo_ingreso_declarado(
    servicio_efectos, contexto, admin, condonacion_con_ingreso, importe
) -> None:
    hecho_id, _, _ = condonacion_con_ingreso
    _rechazo(lambda: _op04(servicio_efectos, contexto, admin, hecho_id,
                           _ef("INGRESO", importe), presupuestable=None),
             COND, "I4:")
    assert _efectos(admin, contexto, hecho_id) == [["DEUDA", "-40.0000"],
                                                   ["INGRESO", "10.0000"]]


def test_i4_op21_segundo_ingreso_declarado_a4(
    servicio_correcciones, contexto, admin, condonacion_con_ingreso
) -> None:
    hecho_id, _, _ = condonacion_con_ingreso
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_crear=(_ef("INGRESO", "5.0000"),)),
             COND, "I4:")


def test_i4_c1_c3_segundo_gasto_en_condonacion_de_derecho(
    servicio_efectos, servicio_correcciones, contexto, admin,
    condonacion_derecho_con_gasto,
) -> None:
    hecho_id, _, _ = condonacion_derecho_con_gasto
    _rechazo(lambda: _op04(servicio_efectos, contexto, admin, hecho_id,
                           _ef("GASTO", "30.0000"), presupuestable=None),
             COND, "I4:")
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_crear=(_ef("GASTO", "20.0000"),)),
             COND, "I4:")
    assert _efectos(admin, contexto, hecho_id) == [["DERECHO_COBRO", "-30.0000"],
                                                   ["GASTO", "30.0000"]]


# ==================================================================
# I6 · REEMBOLSO: ni INGRESO ni GASTO negativo (R1/R2 del INFORME ampliado)
# ==================================================================

@pytest.mark.parametrize("localizacion", ["NO_APLICA", "DESCONOCIDA"])
@pytest.mark.parametrize("tipo, importe", [("INGRESO", "10.0000"), ("GASTO", "-10.0000")],
                         ids=["ingreso", "gasto_negativo"])
def test_i6_op04_reembolso_sin_ingreso_ni_gasto_negativo(
    servicio, servicio_efectos, contexto, admin, reembolso, tipo, importe,
    localizacion,
) -> None:
    hecho_id, _ = reembolso
    if localizacion == "DESCONOCIDA":
        _a_desconocida(servicio, contexto, admin, hecho_id)
    antes = _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op04(servicio_efectos, contexto, admin, hecho_id,
                           _ef(tipo, importe)), REEM, "I6:")
    assert _efectos(admin, contexto, hecho_id) == antes


@pytest.mark.parametrize("tipo, importe", [("INGRESO", "10.0000"), ("GASTO", "-10.0000")],
                         ids=["ingreso", "gasto_negativo"])
def test_i6_op21_reembolso_no_crea_ingreso_ni_gasto_negativo(
    servicio, servicio_correcciones, contexto, admin, reembolso, tipo, importe
) -> None:
    hecho_id, _ = reembolso
    _a_desconocida(servicio, contexto, admin, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           presupuestable=True,
                           efectos_a_crear=(_ef(tipo, importe),)), REEM, "I6:")


def test_i6_op21_reembolso_no_convierte_en_ingreso(
    servicio_correcciones, contexto, admin, reembolso
) -> None:
    hecho_id, efecto_posicion = reembolso
    _rechazo(lambda: _op21(
        servicio_correcciones, contexto, admin, hecho_id, presupuestable=True,
        efectos_a_actualizar={efecto_posicion: {"tipo_efecto": "INGRESO",
                                                "importe_delta": D("40.0000")}}),
        REEM, "I6:")


def test_i6_regresion_gasto_positivo_admitido_y_no_mutable_a_negativo(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin, reembolso
) -> None:
    """Regresion de I6: un GASTO POSITIVO en REEMBOLSO sigue admitido (no es
    INV-12 via 1), pero corregirlo a negativo se rechaza."""
    hecho_id, _ = reembolso
    _a_desconocida(servicio, contexto, admin, hecho_id)
    gasto = uuid.uuid4()
    _op04(servicio_efectos, contexto, admin, hecho_id, _ef("GASTO", "10.0000", gasto))
    assert ["GASTO", "10.0000"] in _efectos(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_actualizar={gasto: {"importe_delta": D("-10.0000")}}),
             REEM, "I6:")


# ==================================================================
# Regresion · GENERACION_DERECHO_OBLIGACION no se ve afectado por E1
# ==================================================================

def test_generacion_derecho_obligacion_no_afectado(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """Historico/migrado: E1 no reinterpreta ni bloquea este arquetipo."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(contexto, DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=dt.date(2026, 6, 1), moneda="EUR",
        presupuestable=False, estado_localizacion="DESCONOCIDA", localidad_id=None,
        tipo_hecho_codigo="GENERACION_DERECHO_OBLIGACION",
        importe_total=D("100.0000")))
    _op04(servicio_efectos, contexto, admin, hecho_id, _ef("INGRESO", "10.0000"))
    _op04(servicio_efectos, contexto, admin, hecho_id, _ef("GASTO", "-5.0000"),
          presupuestable=None)
    _op21(servicio_correcciones, contexto, admin, hecho_id,
          efectos_a_crear=(_ef("INGRESO", "7.0000"),))
    assert _efectos(admin, contexto, hecho_id) == [
        ["GASTO", "-5.0000"], ["INGRESO", "7.0000"], ["INGRESO", "10.0000"]]
