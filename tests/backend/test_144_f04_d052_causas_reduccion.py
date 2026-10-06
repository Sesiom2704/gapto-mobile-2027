# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_144_f04_d052_causas_reduccion.py
# Ruta: tests/backend/test_144_f04_d052_causas_reduccion.py
# Descripcion: F04-D052 B2. Bateria minima 1..10 de la reapertura parcial de
#   F04 (condonacion de obligaciones, causa explicita de reduccion y cuenta
#   Gapto en pagos y cobros propios) y un discriminante por guarda.
#
#   Vocabulario cerrado y forma fisica (writers nuevos):
#     PAGO (OP-12B)       REEMBOLSO + movimiento en cuenta Gapto
#     COBRO (OP-14)       REEMBOLSO + movimiento en cuenta Gapto
#     CONDONACION         CONDONACION (D-201) sin movimiento
#   La causa no se persiste: se comprueba fisicamente por arquetipo +
#   conciliacion (consulta SQL) y en lectura por `causas_de_reduccion`.
#
#   Las guardas se prueban con "cero escrituras": un rechazo no deja hecho,
#   efecto, movimiento ni posicion. Las financiaciones formales se prueban
#   con una entidad FINANCIACION REAL y con el id de una fila REAL de
#   financiacion_cuotas (guarda estructural, D4). Los casos mixtos (pago +
#   condonacion del resto y al reves) prueban la guarda motivo_cierre <->
#   causa, anadida por iniciativa propia y mantenida por la orquestacion.
# Version: 0.2.0
#   0.2.0 (F04-D053 A1): test_cc4_historico[2025-01-01] pasa de 70 a 80: el
#   delta anterior a fecha_inicio_seguimiento no se suma (cambio legitimo).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_posicion import (
    CAUSA_NO_DETERMINABLE,
    DatosCierre,
    DatosCondonacion,
    DatosCondonacionObligacion,
    DatosReembolso,
    DatosTesoreriaReembolso,
    TIPO_HECHO_POSICION,
    TIPO_OBLIGACION,
)
from app.core.modelos_tesoreria import DatosMovimiento
from app.services.posiciones_service import PosicionesService
from app.services.tesoreria_service import TesoreriaService
from conftest import leer_fila
from test_109_op12_posiciones import (
    FECHA as FECHA_INICIO_SEGUIMIENTO,
    COBRO,
    CONDONACION,
    PAGO,
    alta,
    delta,
    tesoreria_nueva,
)

D = decimal.Decimal
CIERRE = dt.date(2026, 7, 1)
ID_CONDONACION = "0d216df5-59eb-56c8-998e-7d47953b9351"


# ==================================================================
# Fixtures y utilidades
# ==================================================================

@pytest.fixture()
def obligacion(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="Obligacion D052")
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


@pytest.fixture()
def obligacion_indeterminada(
    servicio_posiciones: PosicionesService, contexto, contraparte
):
    datos = alta(
        contraparte,
        tipo=TIPO_OBLIGACION,
        nombre="Obligacion historica",
        saldo_apertura=None,
        fecha_inicio_seguimiento=None,
    )
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


@pytest.fixture()
def derecho(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte, nombre="Derecho D052")
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


def _como_owner(admin: psycopg.Connection, owner: uuid.UUID, sentencias) -> None:
    """Escribe fixtures en UNA transaccion bajo gapto_owner (las invariantes
    diferidas de subtipo se validan en el COMMIT)."""
    with admin.transaction():
        with admin.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE gapto_owner")
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),)
            )
            for sql, params in sentencias:
                cursor.execute(sql, params)


@pytest.fixture()
def cuenta_efectivo(admin: psycopg.Connection, owner: uuid.UUID) -> uuid.UUID:
    """Cuenta Gapto de tipo EFECTIVO: valida, no una excepcion (F04-D052)."""
    cuenta_id = uuid.uuid4()
    _como_owner(admin, owner, [(
        "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, "
        "moneda, computa_liquidez, computa_patrimonio, permite_negativo) "
        "VALUES (%s, %s, 'Cartera', 'EFECTIVO', 'ACTIVO', 'EUR', true, true, false)",
        (cuenta_id, owner),
    )])
    return cuenta_id


@pytest.fixture()
def financiacion(admin: psycopg.Connection, owner: uuid.UUID):
    """Financiacion formal REAL con una cuota REAL: (entidad_id, cuota_id)."""
    entidad_id, cuota_id = uuid.uuid4(), uuid.uuid4()
    _como_owner(admin, owner, [
        ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
         "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca formal')", (entidad_id, owner)),
        ("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, "
         "saldo_principal_apertura, fecha_inicio_seguimiento) "
         "VALUES (%s, 'HIPOTECA', 'EUR', 1000, %s)", (entidad_id, dt.date(2026, 1, 1))),
        ("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, "
         "numero_cuota, fecha_vencimiento, importe_total_previsto) "
         "VALUES (%s, %s, 1, %s, 100)", (cuota_id, entidad_id, dt.date(2026, 7, 1))),
    ])
    return entidad_id, cuota_id


def _contar(admin, contexto, sql: str, params: tuple = ()) -> int:
    return leer_fila(admin, contexto.owner_user_id, sql, params)[0]


def _forma_fisica(admin, contexto, hecho_id) -> tuple:
    """(arquetipo, conciliaciones, INGRESO, GASTO) del hecho: la causa fisica."""
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT th.codigo, "
        " (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria c WHERE c.hecho_id = h.id), "
        " (SELECT count(*) FROM gapto.hecho_efectos e "
        "   WHERE e.hecho_id = h.id AND e.tipo_efecto = 'INGRESO'), "
        " (SELECT count(*) FROM gapto.hecho_efectos e "
        "   WHERE e.hecho_id = h.id AND e.tipo_efecto = 'GASTO') "
        "FROM gapto.hechos_financieros h "
        "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE h.id = %s",
        (hecho_id,),
    )


def _sin_escrituras(admin, contexto, d, tesoreria=None) -> None:
    """Nada de la operacion rechazada llego a la base."""
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                   (d.hecho_id,)) == 0
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
                   (d.efecto_id,)) == 0
    if tesoreria is not None:
        assert _contar(admin, contexto,
                       "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id = %s",
                       (tesoreria.movimiento_id,)) == 0


def _condonar_obligacion(servicio, contexto, entidad_id, version, importe, **extra):
    datos = DatosCondonacionObligacion(
        delta=delta(importe, causa=CONDONACION, **extra.pop("delta_extra", {})),
        **extra,
    )
    resultado = servicio.condonar_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=version, datos=datos,
    )
    return datos, resultado


# ==================================================================
# 1 · Pago de obligacion -> REEMBOLSO + movimiento; completo -> LIQUIDADA
# ==================================================================

def test_1_pago_es_reembolso_con_movimiento(
    servicio_posiciones, contexto, admin, obligacion, cuenta
) -> None:
    entidad_id, creada = obligacion
    pago = delta("40.0000", causa=PAGO)
    tesoreria = tesoreria_nueva(cuenta)
    resultado = servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=pago, movimiento=tesoreria,
    )
    assert resultado.saldo.importe == D("60.0000")
    assert _forma_fisica(admin, contexto, pago.hecho_id) == ("REEMBOLSO", 1, 0, 0)
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s",
        (tesoreria.movimiento_id,),
    ) == (D("-40.0000"),)


def test_1_pago_consumiendo_movimiento_existente_no_crea_otro(
    servicio_posiciones, servicio_tesoreria: TesoreriaService, contexto, admin,
    obligacion, cuenta,
) -> None:
    """Crear O consumir, nunca ambos: consumir no crea un segundo movimiento."""
    entidad_id, creada = obligacion
    movimiento_id = uuid.uuid4()
    mov = servicio_tesoreria.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=movimiento_id, cuenta_id=cuenta, fecha_movimiento=CIERRE,
        importe=D("-25.0000"), clase_movimiento="OPERACION",
    ))
    pago = delta("25.0000", causa=PAGO)
    servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version, delta=pago,
        movimiento=DatosTesoreriaReembolso(
            conciliacion_id=uuid.uuid4(), movimiento_id=movimiento_id,
            movimiento_row_version_esperada=mov.row_version,
        ),
    )
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s",
                   (cuenta,)) == 1
    assert _forma_fisica(admin, contexto, pago.hecho_id) == ("REEMBOLSO", 1, 0, 0)


def test_1_pago_completo_cierra_liquidada(
    servicio_posiciones, contexto, admin, obligacion, cuenta
) -> None:
    entidad_id, creada = obligacion
    resultado = servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=delta("100.0000", causa=PAGO,
                    cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE)),
        movimiento=tesoreria_nueva(cuenta),
    )
    assert resultado.estado == "CERRADA" and resultado.saldo.importe == D("0")
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT estado, motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s", (entidad_id,),
    ) == ("CERRADA", "LIQUIDADA")


# ==================================================================
# 2 · Pago sin cuenta -> STOP
# ==================================================================

def test_2_pago_sin_cuenta_stop(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    entidad_id, creada = obligacion
    pago = delta("40.0000", causa=PAGO)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version, delta=pago,
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_GAPTO_REQUERIDA
    _sin_escrituras(admin, contexto, pago)


# ==================================================================
# 3 · Cobro con cuenta y en EFECTIVO -> aceptado; sin cuenta -> STOP
# ==================================================================

@pytest.mark.parametrize("tipo_cuenta", ["CORRIENTE", "EFECTIVO"])
def test_3_cobro_con_cuenta_gapto_aceptado(
    servicio_posiciones, contexto, admin, derecho, cuenta, cuenta_efectivo,
    tipo_cuenta,
) -> None:
    entidad_id, creada = derecho
    destino = cuenta if tipo_cuenta == "CORRIENTE" else cuenta_efectivo
    cobro = delta("30.0000", causa=COBRO)
    tesoreria = tesoreria_nueva(destino)
    resultado = servicio_posiciones.reembolsar(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=cobro, tesoreria=tesoreria),
    )
    assert resultado.saldo.importe == D("70.0000")
    assert _forma_fisica(admin, contexto, cobro.hecho_id) == ("REEMBOLSO", 1, 0, 0)
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT c.tipo, m.importe FROM gapto.movimientos_tesoreria m "
        "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE m.id = %s",
        (tesoreria.movimiento_id,),
    ) == (tipo_cuenta, D("30.0000"))


def test_3_cobro_sin_cuenta_stop(
    servicio_posiciones, contexto, admin, derecho
) -> None:
    entidad_id, creada = derecho
    cobro = delta("30.0000", causa=COBRO)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosReembolso(delta=cobro),
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_GAPTO_REQUERIDA
    _sin_escrituras(admin, contexto, cobro)


# ==================================================================
# 4 · Condonacion de obligacion: parcial, total y saldo indeterminado
# ==================================================================

def test_4_condonacion_parcial_queda_activa(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    entidad_id, creada = obligacion
    datos, resultado = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "30.0000",
    )
    assert resultado.estado == "ACTIVA"
    assert resultado.saldo.importe == D("70.0000")
    assert _forma_fisica(admin, contexto, datos.delta.hecho_id) == (
        "CONDONACION", 0, 0, 0,
    )
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT tipo_hecho_id::text FROM gapto.hechos_financieros WHERE id = %s",
        (datos.delta.hecho_id,),
    ) == (ID_CONDONACION,)


def test_4_condonacion_total_cierra_condonada(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    entidad_id, creada = obligacion
    datos, resultado = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "100.0000",
        delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)},
    )
    assert resultado.estado == "CERRADA" and resultado.saldo.importe == D("0")
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT estado, motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s", (entidad_id,),
    ) == ("CERRADA", "CONDONADA")
    assert _forma_fisica(admin, contexto, datos.delta.hecho_id) == (
        "CONDONACION", 0, 0, 0,
    )


def test_4_condonacion_saldo_indeterminado_sin_validar_importe(
    servicio_posiciones, contexto, obligacion_indeterminada
) -> None:
    """F04-D015 §9 como en el derecho: se admite el importe observado sin
    validacion cuantitativa y el saldo SIGUE indeterminado."""
    entidad_id, creada = obligacion_indeterminada
    _, resultado = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "9999.0000",
    )
    assert resultado.saldo.conocido is False
    assert resultado.estado == "ACTIVA"


def test_4_condonacion_total_indeterminada_solo_por_declaracion_sin_residual(
    servicio_posiciones, contexto, admin, obligacion_indeterminada
) -> None:
    """Cierre total con saldo indeterminado: solo por declaracion explicita
    del llamante y sin fabricar residual (un unico efecto: el delta)."""
    entidad_id, creada = obligacion_indeterminada
    sin_cierre, tras = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "50.0000",
    )
    assert tras.estado == "ACTIVA"  # sin declaracion no se cierra
    datos, resultado = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, tras.entidad_row_version,
        "50.0000",
        delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)},
    )
    assert resultado.estado == "CERRADA"
    assert resultado.saldo.conocido is False
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
                   (datos.delta.hecho_id,)) == 1


def test_4_condonacion_obligacion_excede_saldo_conocido(
    servicio_posiciones, contexto, obligacion
) -> None:
    entidad_id, creada = obligacion
    with pytest.raises(ErrorMotor) as excinfo:
        _condonar_obligacion(
            servicio_posiciones, contexto, entidad_id,
            creada.entidad_row_version, "100.0001",
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_SALDO_POSICION


# ==================================================================
# 5 · Condonacion de derecho -> CONDONACION; cobro y condonacion distintos
# ==================================================================

def test_5_cobro_y_condonacion_de_derecho_fisicamente_diferenciables(
    servicio_posiciones, contexto, admin, derecho, cuenta
) -> None:
    entidad_id, creada = derecho
    cobro = delta("20.0000", causa=COBRO)
    tras = servicio_posiciones.reembolsar(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=cobro, tesoreria=tesoreria_nueva(cuenta)),
    )
    condonacion = DatosCondonacion(delta=delta("20.0000", causa=CONDONACION))
    final = servicio_posiciones.condonar_derecho(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=tras.entidad_row_version, datos=condonacion,
    )
    assert final.saldo.importe == D("60.0000")
    # Diferenciacion FISICA por consulta SQL: arquetipo + conciliacion.
    assert _forma_fisica(admin, contexto, cobro.hecho_id) == ("REEMBOLSO", 1, 0, 0)
    assert _forma_fisica(admin, contexto, condonacion.delta.hecho_id) == (
        "CONDONACION", 0, 0, 0,
    )
    leidas = {c.hecho_id: c.causa for c in servicio_posiciones.causas_de_reduccion(
        contexto, entidad_id)}
    assert leidas == {cobro.hecho_id: "COBRO",
                      condonacion.delta.hecho_id: "CONDONACION"}


# ==================================================================
# 6 · INGRESO cero por defecto; solo declarado
# ==================================================================

def test_6_ingreso_cero_por_defecto(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    entidad_id, creada = obligacion
    datos, _ = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "40.0000",
    )
    assert _forma_fisica(admin, contexto, datos.delta.hecho_id)[2] == 0
    # Hecho puramente posicional: conserva los valores de posicion.
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT presupuestable, estado_localizacion FROM gapto.hechos_financieros "
        "WHERE id = %s", (datos.delta.hecho_id,),
    ) == (False, "NO_APLICA")


@pytest.mark.parametrize("decision", [True, False])
def test_6_ingreso_declarado_sigue_el_contrato_e01(
    servicio_posiciones, contexto, admin, obligacion, decision
) -> None:
    entidad_id, creada = obligacion
    efecto_ingreso_id = uuid.uuid4()
    datos, _ = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "40.0000", importe_ingreso=D("15.0000"),
        efecto_ingreso_id=efecto_ingreso_id, presupuestable=decision,
    )
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta, categoria_id FROM gapto.hecho_efectos "
        "WHERE id = %s", (efecto_ingreso_id,),
    ) == ("INGRESO", D("15.0000"), None)
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT presupuestable, estado_localizacion FROM gapto.hechos_financieros "
        "WHERE id = %s", (datos.delta.hecho_id,),
    ) == (decision, "DESCONOCIDA")
    assert _forma_fisica(admin, contexto, datos.delta.hecho_id) == (
        "CONDONACION", 0, 1, 0,
    )


def test_6_ingreso_igual_a_lo_condonado_admitido(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    entidad_id, creada = obligacion
    datos, _ = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "40.0000", importe_ingreso=D("40.0000"), efecto_ingreso_id=uuid.uuid4(),
        presupuestable=True,
    )
    assert _forma_fisica(admin, contexto, datos.delta.hecho_id)[2] == 1


@pytest.mark.parametrize("importe_ingreso", ["40.0001", "0", "-5.0000"])
def test_6_ingreso_fuera_de_rango_rechazado(
    servicio_posiciones, contexto, admin, obligacion, importe_ingreso
) -> None:
    """INGRESO > condonado (exceso), cero o negativo -> INGRESO_NO_PERMITIDO."""
    entidad_id, creada = obligacion
    d = delta("40.0000", causa=CONDONACION)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosCondonacionObligacion(
                delta=d, importe_ingreso=D(importe_ingreso),
                efecto_ingreso_id=uuid.uuid4(), presupuestable=True,
            ),
        )
    assert excinfo.value.codigo is CodigoError.INGRESO_NO_PERMITIDO
    if importe_ingreso == "40.0001":
        assert "excede" in excinfo.value.mensaje
    _sin_escrituras(admin, contexto, d)


@pytest.mark.parametrize("extra", [
    {},                                                    # sin decision
    {"presupuestable": True, "estado_localizacion": "NO_APLICA"},
], ids=["sin_decision", "no_aplica"])
def test_6_ingreso_declarado_sin_contrato_e01_rechazado(
    servicio_posiciones, contexto, admin, obligacion, extra
) -> None:
    entidad_id, creada = obligacion
    d = delta("40.0000", causa=CONDONACION)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosCondonacionObligacion(
                delta=d, importe_ingreso=D("10.0000"),
                efecto_ingreso_id=uuid.uuid4(), **extra,
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA
    _sin_escrituras(admin, contexto, d)


def test_6_ingreso_duplicado_sobre_la_misma_porcion_rechazado(
    servicio_posiciones, contexto, admin, obligacion
) -> None:
    """D6: como maximo un INGRESO por hecho de condonacion y solo en la misma
    operacion. Reintento exacto: idempotente. Mismo hecho con otro INGRESO:
    otra intencion. No existe via en posiciones para anadirlo despues."""
    entidad_id, creada = obligacion
    datos = DatosCondonacionObligacion(
        delta=delta("40.0000", causa=CONDONACION), importe_ingreso=D("10.0000"),
        efecto_ingreso_id=uuid.uuid4(), presupuestable=True,
    )
    kwargs = dict(entidad_id=entidad_id,
                  entidad_row_version_esperada=creada.entidad_row_version)
    servicio_posiciones.condonar_obligacion(contexto, datos=datos, **kwargs)
    assert servicio_posiciones.condonar_obligacion(
        contexto, datos=datos, **kwargs).idempotente
    otro = DatosCondonacionObligacion(
        delta=datos.delta, importe_ingreso=D("10.0000"),
        efecto_ingreso_id=uuid.uuid4(), presupuestable=True,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_obligacion(contexto, datos=otro, **kwargs)
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.hecho_efectos "
                   "WHERE hecho_id = %s AND tipo_efecto = 'INGRESO'",
                   (datos.delta.hecho_id,)) == 1
    assert not hasattr(servicio_posiciones, "declarar_ingreso")


def test_6_identidad_de_ingreso_sin_ingreso_declarado_rechazada(
    servicio_posiciones, contexto, obligacion
) -> None:
    entidad_id, creada = obligacion
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosCondonacionObligacion(
                delta=delta("10.0000", causa=CONDONACION),
                efecto_ingreso_id=uuid.uuid4(),
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ==================================================================
# 7 · Causa no permitida -> STOP; pago por tercero -> STOP
# ==================================================================

@pytest.mark.parametrize(
    "causa", [None, COBRO, CONDONACION, "PAGO", "PERDON"],
    ids=["ausente", "cobro", "condonacion_con_movimiento", "cadena_cruda", "desconocida"],
)
def test_7_op12b_causa_erronea_stop(
    servicio_posiciones, contexto, admin, obligacion, cuenta, causa
) -> None:
    """Ausente, de otra operacion, cadena cruda o desconocida -> STOP.
    CONDONACION con movimiento cae aqui: la causa no es la de OP-12B."""
    entidad_id, creada = obligacion
    d = delta("10.0000", causa=causa)
    tesoreria = tesoreria_nueva(cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=d, movimiento=tesoreria,
        )
    assert excinfo.value.codigo is CodigoError.CAUSA_REDUCCION_INVALIDA
    _sin_escrituras(admin, contexto, d, tesoreria)


@pytest.mark.parametrize("causa", [None, PAGO, CONDONACION],
                         ids=["ausente", "pago", "condonacion_con_movimiento"])
def test_7_op14_causa_erronea_stop(
    servicio_posiciones, contexto, admin, derecho, cuenta, causa
) -> None:
    entidad_id, creada = derecho
    d = delta("10.0000", causa=causa)
    tesoreria = tesoreria_nueva(cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosReembolso(delta=d, tesoreria=tesoreria),
        )
    assert excinfo.value.codigo is CodigoError.CAUSA_REDUCCION_INVALIDA
    _sin_escrituras(admin, contexto, d, tesoreria)


@pytest.mark.parametrize("causa", [None, PAGO, COBRO], ids=["ausente", "pago", "cobro"])
def test_7_condonaciones_con_causa_erronea_stop(
    servicio_posiciones, contexto, admin, derecho, obligacion, causa
) -> None:
    d1 = delta("10.0000", causa=causa)
    with pytest.raises(ErrorMotor) as e1:
        servicio_posiciones.condonar_derecho(
            contexto, entidad_id=derecho[0],
            entidad_row_version_esperada=derecho[1].entidad_row_version,
            datos=DatosCondonacion(delta=d1),
        )
    d2 = delta("10.0000", causa=causa)
    with pytest.raises(ErrorMotor) as e2:
        servicio_posiciones.condonar_obligacion(
            contexto, entidad_id=obligacion[0],
            entidad_row_version_esperada=obligacion[1].entidad_row_version,
            datos=DatosCondonacionObligacion(delta=d2),
        )
    assert e1.value.codigo is e2.value.codigo is CodigoError.CAUSA_REDUCCION_INVALIDA
    _sin_escrituras(admin, contexto, d1)
    _sin_escrituras(admin, contexto, d2)


def test_7_pago_por_tercero_stop_sin_nada(
    servicio_posiciones, contexto, admin, obligacion, cuenta
) -> None:
    """R-F04-038: ni CONDONACION, ni PAGO propio, ni posicion nueva."""
    entidad_id, creada = obligacion
    posiciones_antes = _contar(
        admin, contexto,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,))
    d = delta("40.0000", causa=PAGO)
    tesoreria = tesoreria_nueva(cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=d, movimiento=tesoreria, pagado_por_tercero=True,
        )
    assert excinfo.value.codigo is CodigoError.PAGO_POR_TERCERO_FUERA_DE_ALCANCE
    _sin_escrituras(admin, contexto, d, tesoreria)
    assert _contar(
        admin, contexto,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,)) == posiciones_antes
    assert _contar(
        admin, contexto,
        "SELECT count(*) FROM gapto.hechos_financieros h "
        "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
        "WHERE h.owner_user_id = %s AND th.codigo IN ('CONDONACION', 'REEMBOLSO')",
        (contexto.owner_user_id,)) == 0
    assert servicio_posiciones.saldo(contexto, entidad_id).saldo.importe == D("100.0000")


@pytest.mark.parametrize("motivo, operacion", [
    ("CONDONADA", "pago"), ("LIQUIDADA", "condonacion"), ("CANCELADA", "pago"),
])
def test_7_motivo_de_cierre_incoherente_con_la_causa(
    servicio_posiciones, contexto, admin, obligacion, cuenta, motivo, operacion
) -> None:
    """Pago y condonacion son causas separadas: un pago no cierra CONDONADA
    ni una condonacion LIQUIDADA (no hay causa mixta, CC10)."""
    entidad_id, creada = obligacion
    d = delta("100.0000", causa=PAGO if operacion == "pago" else CONDONACION,
              cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=CIERRE))
    with pytest.raises(ErrorMotor) as excinfo:
        if operacion == "pago":
            servicio_posiciones.reducir_obligacion(
                contexto, entidad_id=entidad_id,
                entidad_row_version_esperada=creada.entidad_row_version,
                delta=d, movimiento=tesoreria_nueva(cuenta),
            )
        else:
            servicio_posiciones.condonar_obligacion(
                contexto, entidad_id=entidad_id,
                entidad_row_version_esperada=creada.entidad_row_version,
                datos=DatosCondonacionObligacion(delta=d),
            )
    assert excinfo.value.codigo is CodigoError.CAUSA_REDUCCION_INVALIDA
    _sin_escrituras(admin, contexto, d)


def test_7_pago_y_condonacion_son_operaciones_separadas(
    servicio_posiciones, contexto, admin, obligacion, cuenta
) -> None:
    """CC10: una misma realidad (pago 60 + quita 40) son DOS hechos con dos
    formas fisicas distintas; nunca una causa mixta."""
    entidad_id, creada = obligacion
    pago = delta("60.0000", causa=PAGO)
    tras = servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=pago, movimiento=tesoreria_nueva(cuenta),
    )
    quita, final = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, tras.entidad_row_version,
        "40.0000",
        delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)},
    )
    assert final.saldo.importe == D("0") and final.estado == "CERRADA"
    assert _forma_fisica(admin, contexto, pago.hecho_id) == ("REEMBOLSO", 1, 0, 0)
    assert _forma_fisica(admin, contexto, quita.delta.hecho_id) == (
        "CONDONACION", 0, 0, 0)
    # El cierre lo pone la operacion que extingue el resto: CONDONADA.
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s", (entidad_id,),
    ) == ("CONDONADA",)


def test_7_condonacion_parcial_y_pago_del_resto_cierra_liquidada(
    servicio_posiciones, contexto, admin, obligacion, cuenta
) -> None:
    """Caso mixto inverso (CC10): quita de 30 y pago del resto (70) con
    cierre. Dos hechos separados; el cierre del pago es LIQUIDADA."""
    entidad_id, creada = obligacion
    quita, tras = _condonar_obligacion(
        servicio_posiciones, contexto, entidad_id, creada.entidad_row_version,
        "30.0000",
    )
    assert tras.estado == "ACTIVA"
    pago = delta("70.0000", causa=PAGO,
                 cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE))
    final = servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=tras.entidad_row_version,
        delta=pago, movimiento=tesoreria_nueva(cuenta),
    )
    assert final.saldo.importe == D("0") and final.estado == "CERRADA"
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s", (entidad_id,),
    ) == ("LIQUIDADA",)
    assert _forma_fisica(admin, contexto, quita.delta.hecho_id) == (
        "CONDONACION", 0, 0, 0)
    assert _forma_fisica(admin, contexto, pago.hecho_id) == ("REEMBOLSO", 1, 0, 0)


# ==================================================================
# 8 · Una cuota de financiacion no cae por la rama CONDONACION (D4)
# ==================================================================

@pytest.mark.parametrize("objetivo", ["entidad", "cuota"])
def test_8_financiacion_formal_no_entra_por_condonacion(
    servicio_posiciones, contexto, admin, financiacion, objetivo
) -> None:
    entidad_id, cuota_id = financiacion
    destino = entidad_id if objetivo == "entidad" else cuota_id
    d = delta("100.0000", causa=CONDONACION)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_obligacion(
            contexto, entidad_id=destino, entidad_row_version_esperada=1,
            datos=DatosCondonacionObligacion(delta=d),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    _sin_escrituras(admin, contexto, d)
    assert _contar(admin, contexto,
                   "SELECT count(*) FROM gapto.hecho_entidades WHERE entidad_id = %s",
                   (entidad_id,)) == 0


@pytest.mark.parametrize("objetivo", ["entidad", "cuota"])
def test_8_financiacion_formal_no_entra_por_op12b(
    servicio_posiciones, contexto, admin, financiacion, cuenta, objetivo
) -> None:
    entidad_id, cuota_id = financiacion
    destino = entidad_id if objetivo == "entidad" else cuota_id
    d = delta("100.0000", causa=PAGO)
    tesoreria = tesoreria_nueva(cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto, entidad_id=destino, entidad_row_version_esperada=1,
            delta=d, movimiento=tesoreria,
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    _sin_escrituras(admin, contexto, d, tesoreria)


# ==================================================================
# CC4 · Lectura: historico/migrado -> causa no determinable, sin reclasificar
# ==================================================================

def _reduccion_historica(unidad, contexto, entidad_id, fecha) -> uuid.UUID:
    """Simula una reduccion escrita ANTES de F04-D052 (o migrada por RV3):
    GENERACION_DERECHO_OBLIGACION + DEUDA negativa + sin movimiento."""
    servicio = PosicionesService(unidad)
    hecho_id = uuid.uuid4()

    def operacion(sesion):
        servicio._crear_hecho(
            sesion, hecho_id=hecho_id, tipo_hecho_codigo=TIPO_HECHO_POSICION,
            fecha_hecho=fecha, moneda="EUR", concepto="reduccion historica",
            importe_total=D("10.0000"),
        )
        servicio._crear_delta(
            sesion, hecho_id=hecho_id, efecto_id=uuid.uuid4(),
            vinculo_id=uuid.uuid4(), entidad_id=entidad_id, tipo_efecto="DEUDA",
            importe_delta=D("-10.0000"), concepto="reduccion historica",
        )

    unidad.ejecutar(contexto, operacion, nombre="fixture-historico-d052")
    return hecho_id


@pytest.mark.parametrize("fecha", [dt.date(2025, 1, 1), dt.date(2027, 1, 1)])
def test_cc4_historico_causa_no_determinable_sin_reclasificar(
    unidad, servicio_posiciones, contexto, admin, obligacion, cuenta, fecha
) -> None:
    """La fecha no discrimina: antes o despues de D052, una reduccion con
    GENERACION_DERECHO_OBLIGACION se lee NO_DETERMINABLE y no se toca."""
    entidad_id, creada = obligacion
    historica = _reduccion_historica(unidad, contexto, entidad_id, fecha)
    pago = delta("20.0000", causa=PAGO)
    servicio_posiciones.reducir_obligacion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=pago, movimiento=tesoreria_nueva(cuenta),
    )
    leidas = {c.hecho_id: (c.tipo_hecho, c.con_movimiento, c.causa)
              for c in servicio_posiciones.causas_de_reduccion(contexto, entidad_id)}
    assert leidas == {
        historica: ("GENERACION_DERECHO_OBLIGACION", False, CAUSA_NO_DETERMINABLE),
        pago.hecho_id: ("REEMBOLSO", True, "PAGO"),
    }
    # Leer no reclasifica: el historico conserva su arquetipo y su version.
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT th.codigo, h.row_version FROM gapto.hechos_financieros h "
        "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE h.id = %s",
        (historica,),
    ) == ("GENERACION_DERECHO_OBLIGACION", 1)
    # F04-D053 A1: el historico cuenta en el saldo solo si su fecha economica
    # no es anterior a fecha_inicio_seguimiento (2026-06-01). 2025-01-01 ya
    # esta dentro de la apertura: 100 - 20 = 80. 2027-01-01 cuenta: 70.
    esperado = D("80.0000") if fecha < FECHA_INICIO_SEGUIMIENTO else D("70.0000")
    assert servicio_posiciones.saldo(contexto, entidad_id).saldo.importe == esperado


def test_cc4_creacion_sigue_usando_generacion_derecho_obligacion(
    servicio_posiciones, contexto, admin, contraparte
) -> None:
    datos = alta(contraparte, tipo=TIPO_OBLIGACION)
    servicio_posiciones.crear_posicion(contexto, datos)
    assert _forma_fisica(admin, contexto, datos.hecho_id)[0] == (
        "GENERACION_DERECHO_OBLIGACION"
    )
    # El alta no es una reduccion: no aparece en la lectura de causas.
    assert servicio_posiciones.causas_de_reduccion(contexto, datos.entidad_id) == []
