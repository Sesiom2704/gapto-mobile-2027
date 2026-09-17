# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_109_op12_posiciones.py
# Ruta: tests/backend/test_109_op12_posiciones.py
# Descripcion: F04-04 OP-12. Alta de posicion, calculo de saldo, reduccion de
#   obligacion y cierre explicito.
#
#   El nucleo de esta suite es INV-17: saldo CONOCIDO frente a INDETERMINADO.
#   No son un numero y su ausencia, son dos estados distintos, y la diferencia
#   se pierde en cuanto alguien trata el NULL como cero.
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
    DatosAltaPosicion,
    DatosCierre,
    DatosDeltaPosicion,
    TIPO_DERECHO,
    TIPO_OBLIGACION,
)
from app.core.modelos_posicion import DatosTesoreriaReembolso
from app.core.modelos_tesoreria import DatosMovimiento
from app.services.posiciones_service import PosicionesService
from app.services.tesoreria_service import TesoreriaService
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)


def alta(contraparte: uuid.UUID, **extra) -> DatosAltaPosicion:
    base = {
        "entidad_id": uuid.uuid4(),
        "nombre": "Posicion de prueba",
        "tipo": TIPO_DERECHO,
        "contraparte_actor_id": contraparte,
        "moneda": "EUR",
        "justificacion": "DECISION_EXPLICITA",
        "fecha_inicio_seguimiento": FECHA,
        "saldo_apertura": D("0"),
        "hecho_id": uuid.uuid4(),
        "fecha_hecho": FECHA,
        "concepto": "alta de posicion",
        "efecto_id": uuid.uuid4(),
        "vinculo_id": uuid.uuid4(),
        "importe_inicial": D("100.0000"),
    }
    base.update(extra)
    return DatosAltaPosicion(**base)


def delta(importe: str, **extra) -> DatosDeltaPosicion:
    base = {
        "hecho_id": uuid.uuid4(),
        "efecto_id": uuid.uuid4(),
        "vinculo_id": uuid.uuid4(),
        "importe": D(importe),
        "fecha_hecho": dt.date(2026, 6, 15),
    }
    base.update(extra)
    return DatosDeltaPosicion(**base)


@pytest.fixture()
def derecho(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


@pytest.fixture()
def obligacion(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="Obligacion")
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


# ==================================================================
# Alta
# ==================================================================

def test_alta_de_derecho(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    datos = alta(contraparte)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)

    assert resultado.entidad_row_version == 1
    assert resultado.tipo == TIPO_DERECHO
    assert resultado.estado == "ACTIVA"
    assert resultado.saldo.conocido and resultado.saldo.importe == D("100.0000")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT e.tipo_entidad, p.tipo, p.moneda, p.contraparte_actor_id, "
        "p.saldo_apertura, p.estado "
        "FROM gapto.entidades e JOIN gapto.derechos_obligaciones_financieras p "
        "ON p.entidad_id = e.id WHERE e.id = %s",
        (datos.entidad_id,),
    )
    assert fila == (
        "DERECHO_OBLIGACION",
        "DERECHO_COBRO",
        "EUR",
        contraparte,
        D("0.0000"),
        "ACTIVA",
    )


def test_alta_de_obligacion(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    resultado = servicio_posiciones.crear_posicion(
        contexto, alta(contraparte, tipo=TIPO_OBLIGACION)
    )
    assert resultado.tipo == TIPO_OBLIGACION
    assert resultado.saldo.importe == D("100.0000")


@pytest.mark.parametrize(
    "justificacion", ["DECISION_EXPLICITA", "REGLA", "CONTRATO"]
)
def test_las_tres_justificaciones_valen(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
    justificacion,
) -> None:
    datos = alta(contraparte, justificacion=justificacion)
    servicio_posiciones.crear_posicion(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT motivo FROM gapto.auditoria "
        "WHERE registro_id = %s AND tabla = 'entidades'",
        (datos.entidad_id,),
    )
    assert fila == (f"POSICION:{justificacion}",)


@pytest.mark.parametrize("justificacion", [None, "", "HEURISTICA", "SALDO_NETO"])
def test_sin_justificacion_valida_se_rechaza(
    servicio_posiciones: PosicionesService, contexto, contraparte, justificacion
) -> None:
    """INV-04: ninguna diferencia calculada sustituye a la declaracion."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(
            contexto, alta(contraparte, justificacion=justificacion)
        )
    assert excinfo.value.codigo is CodigoError.POSICION_SIN_JUSTIFICACION


def test_contraparte_requerida(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(
            contexto, alta(contraparte, contraparte_actor_id=None)
        )
    assert excinfo.value.codigo is CodigoError.CONTRAPARTE_REQUERIDA


def test_contraparte_self_rechazada(
    servicio_posiciones: PosicionesService, contexto, contraparte, actor_a
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(
            contexto, alta(contraparte, contraparte_actor_id=actor_a)
        )
    assert excinfo.value.codigo is CodigoError.CONTRAPARTE_SELF_NO_PERMITIDA


def test_contraparte_cross_tenant_no_filtra(
    servicio_posiciones: PosicionesService, contexto, contraparte, contraparte_ajena
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(
            contexto, alta(contraparte, contraparte_actor_id=contraparte_ajena)
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


@pytest.mark.parametrize(
    "apertura, fecha",
    [(D("0"), None), (None, FECHA)],
)
def test_pareja_apertura_fecha_inconsistente(
    servicio_posiciones: PosicionesService, contexto, contraparte, apertura, fecha
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(
            contexto,
            alta(contraparte, saldo_apertura=apertura, fecha_inicio_seguimiento=fecha),
        )
    assert excinfo.value.codigo is CodigoError.APERTURA_INCONSISTENTE


def test_entidad_y_subtipo_son_atomicos(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    """Un alta fallida no deja entidad sin subtipo ni al reves."""
    datos = alta(contraparte, moneda="eur")
    with pytest.raises(ErrorMotor):
        servicio_posiciones.crear_posicion(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.entidades WHERE id = %s), "
        "(SELECT count(*) FROM gapto.derechos_obligaciones_financieras "
        " WHERE entidad_id = %s)",
        (datos.entidad_id, datos.entidad_id),
    )
    assert fila == (0, 0)


def test_efecto_causal_compatible_y_vinculado(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    datos = alta(contraparte)
    servicio_posiciones.crear_posicion(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT ef.tipo_efecto, ef.importe_delta, v.tipo_relacion, v.principal "
        "FROM gapto.hecho_efectos ef "
        "JOIN gapto.hecho_entidades v ON v.efecto_id = ef.id "
        "WHERE ef.id = %s",
        (datos.efecto_id,),
    )
    assert fila == ("DERECHO_COBRO", D("100.0000"), "GENERADO_POR", True)


def test_obligacion_usa_efecto_deuda(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    datos = alta(contraparte, tipo=TIPO_OBLIGACION)
    servicio_posiciones.crear_posicion(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s",
        (datos.efecto_id,),
    )
    assert fila == ("DEUDA",)


def test_alta_idempotente(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    datos = alta(contraparte)
    primero = servicio_posiciones.crear_posicion(contexto, datos)
    segundo = servicio_posiciones.crear_posicion(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.entidad_row_version == primero.entidad_row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (datos.hecho_id,),
    )
    assert fila == (1,)


def test_uuid_reutilizado_con_otra_intencion(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    datos = alta(contraparte)
    servicio_posiciones.crear_posicion(contexto, datos)
    otra = alta(
        contraparte,
        entidad_id=datos.entidad_id,
        nombre="otra cosa",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.crear_posicion(contexto, otra)
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_la_posicion_no_nace_de_una_diferencia(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    """INV-04. El servicio no lee atribuciones, aportaciones ni participaciones.

    La comprobacion util es negativa: sin llamada explicita a OP-12 no existe
    ninguna posicion del tenant, por muchos efectos y pagos que haya.
    """
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)


# ==================================================================
# Saldo
# ==================================================================

def test_apertura_cero_mas_derecho_cien(derecho) -> None:
    _, resultado = derecho
    assert resultado.saldo.importe == D("100.0000")


def test_apertura_veinte_mas_treinta(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    resultado = servicio_posiciones.crear_posicion(
        contexto,
        alta(contraparte, saldo_apertura=D("20"), importe_inicial=D("30.0000")),
    )
    assert resultado.saldo.importe == D("50.0000")


def test_obligacion_cien_menos_pago_cuarenta(
    servicio_posiciones: PosicionesService, contexto, obligacion
) -> None:
    entidad_id, creada = obligacion
    resultado = servicio_posiciones.reducir_obligacion(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=delta("40.0000"),
    )
    assert resultado.saldo.importe == D("60.0000")


def test_hecho_anulado_no_participa_en_el_saldo(
    servicio: "HechosService",  # noqa: F821
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada = derecho
    reduccion = delta("30.0000")
    servicio_posiciones.reducir_obligacion  # noqa: B018 - referencia intencionada
    # Se usa la via de derecho: un reembolso reduce el saldo a 70.
    from app.core.modelos_posicion import DatosReembolso

    tras = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=reduccion),
    )
    assert tras.saldo.importe == D("70.0000")

    # Al anular el hecho del reembolso, su delta deja de contar.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (reduccion.hecho_id,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=reduccion.hecho_id,
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    vuelta = servicio_posiciones.saldo(contexto, entidad_id)
    assert vuelta.saldo.importe == D("100.0000")


def test_importe_original_documentado_no_es_saldo(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    resultado = servicio_posiciones.crear_posicion(
        contexto,
        alta(
            contraparte,
            saldo_apertura=D("0"),
            importe_inicial=D("10.0000"),
            importe_original_documentado=D("9999.0000"),
        ),
    )
    assert resultado.saldo.importe == D("10.0000")


def test_saldo_indeterminado_con_apertura_nula(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    """INV-17. Y sigue indeterminado aunque haya deltas."""
    resultado = servicio_posiciones.crear_posicion(
        contexto,
        alta(contraparte, saldo_apertura=None, fecha_inicio_seguimiento=None),
    )
    assert resultado.saldo.conocido is False
    with pytest.raises(Exception):
        _ = resultado.saldo.importe


def test_saldo_cero_no_cierra_la_posicion(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    from app.core.modelos_posicion import DatosReembolso

    entidad_id, creada = derecho
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("100.0000")),
    )
    assert resultado.saldo.importe == D("0.0000")
    assert resultado.estado == "ACTIVA"


# ==================================================================
# Obligacion
# ==================================================================

def test_reduccion_de_obligacion_no_crea_gasto_ni_ingreso(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    obligacion,
) -> None:
    """El gasto se reconocio al nacer la obligacion; repetirlo seria doble
    conteo (INV-12)."""
    entidad_id, creada = obligacion
    reduccion = delta("40.0000")
    servicio_posiciones.reducir_obligacion(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=reduccion,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s",
        (reduccion.hecho_id,),
    )
    assert fila == ("DEUDA", D("-40.0000"))


def test_pago_de_obligacion_con_movimiento_negativo(
    servicio_tesoreria: TesoreriaService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    obligacion,
    cuenta: uuid.UUID,
) -> None:
    entidad_id, creada = obligacion
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=dt.date(2026, 6, 15),
            importe=D("-40.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    tesoreria = DatosTesoreriaReembolso(
        conciliacion_id=uuid.uuid4(),
        movimiento_id=movimiento_id,
        movimiento_row_version_esperada=movimiento.row_version,
    )
    resultado = servicio_posiciones.reducir_obligacion(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=delta("40.0000"),
        movimiento=tesoreria,
    )
    assert resultado.saldo.importe == D("60.0000")
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "WHERE id = %s",
        (tesoreria.conciliacion_id,),
    )
    assert fila == (D("-40.0000"),)


def test_pago_de_obligacion_con_movimiento_positivo_rechazado(
    servicio_tesoreria: TesoreriaService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    obligacion,
    cuenta: uuid.UUID,
) -> None:
    entidad_id, creada = obligacion
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=dt.date(2026, 6, 15),
            importe=D("40.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=delta("40.0000"),
            movimiento=DatosTesoreriaReembolso(
                conciliacion_id=uuid.uuid4(),
                movimiento_id=movimiento_id,
                movimiento_row_version_esperada=movimiento.row_version,
            ),
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_exceso_conocido_sobre_obligacion(
    servicio_posiciones: PosicionesService, contexto, obligacion
) -> None:
    entidad_id, creada = obligacion
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=delta("101.0000"),
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_SALDO_POSICION


def test_reduccion_sobre_saldo_indeterminado_se_registra_sin_validar(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    contraparte: uuid.UUID,
) -> None:
    creada = servicio_posiciones.crear_posicion(
        contexto,
        alta(
            contraparte,
            tipo=TIPO_OBLIGACION,
            saldo_apertura=None,
            fecha_inicio_seguimiento=None,
        ),
    )
    resultado = servicio_posiciones.reducir_obligacion(
        contexto,
        entidad_id=creada.entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        delta=delta("9999.0000"),
    )
    assert resultado.saldo.conocido is False


def test_naturaleza_incompatible(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    entidad_id, creada = derecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reducir_obligacion(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=delta("10.0000"),
        )
    assert excinfo.value.codigo is CodigoError.NATURALEZA_INCOMPATIBLE


# ==================================================================
# Cierre
# ==================================================================

def test_cierre_explicito(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada = derecho
    resultado = servicio_posiciones.cerrar_posicion(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=dt.date(2026, 7, 1)),
    )
    assert resultado.estado == "CERRADA"
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, motivo_cierre, fecha_cierre "
        "FROM gapto.derechos_obligaciones_financieras WHERE entidad_id = %s",
        (entidad_id,),
    )
    assert fila == ("CERRADA", "LIQUIDADA", dt.date(2026, 7, 1))


@pytest.mark.parametrize("motivo", [None, "", "PORQUE_SI"])
def test_cierre_sin_motivo_valido(
    servicio_posiciones: PosicionesService, contexto, derecho, motivo
) -> None:
    entidad_id, creada = derecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.cerrar_posicion(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=dt.date(2026, 7, 1)),
        )
    assert excinfo.value.codigo is CodigoError.CIERRE_SIN_MOTIVO


def test_posicion_cerrada_no_admite_deltas(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    from app.core.modelos_posicion import DatosReembolso

    entidad_id, creada = derecho
    cerrada = servicio_posiciones.cerrar_posicion(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        cierre=DatosCierre(motivo_cierre="CANCELADA", fecha_cierre=dt.date(2026, 7, 1)),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=cerrada.entidad_row_version,
            datos=DatosReembolso(delta=delta("10.0000")),
        )
    assert excinfo.value.codigo is CodigoError.POSICION_CERRADA


def test_version_desfasada_en_cierre(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    entidad_id, creada = derecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.cerrar_posicion(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version + 99,
            cierre=DatosCierre(
                motivo_cierre="OTRO", fecha_cierre=dt.date(2026, 7, 1)
            ),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_posicion_cross_tenant_no_encontrada(
    servicio_posiciones: PosicionesService, otro_owner: uuid.UUID, derecho
) -> None:
    entidad_id, creada = derecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.cerrar_posicion(
            ContextoOperacion.de_usuario(otro_owner),
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            cierre=DatosCierre(
                motivo_cierre="OTRO", fecha_cierre=dt.date(2026, 7, 1)
            ),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_no_hay_delete_de_posicion(admin: psycopg.Connection) -> None:
    """El cierre nunca se representa borrando: ademas es imposible."""
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT has_table_privilege('gapto_runtime', "
            "'gapto.derechos_obligaciones_financieras', 'DELETE')"
        )
        assert cursor.fetchone()[0] is False
