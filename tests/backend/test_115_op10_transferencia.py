# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_115_op10_transferencia.py
# Ruta: tests/backend/test_115_op10_transferencia.py
# Descripcion: F04-06 / B1. OP-10 transferencia propia.
#
#   Lo que vigila esta suite, por encima de cada caso concreto:
#
#   INV-15  una transferencia es hecho + dos movimientos + fila
#           `transferencias` + dos conciliaciones, y CERO efectos.
#   INV-16  no hay efecto economico: el patrimonio no cambia, cambia donde
#           esta el dinero.
#   F04-D001 la comision no se embebe: es su propia realidad economica.
#
#   Y dos propiedades del contrato FISICO que el servicio consume y no
#   reimplementa: el UNIQUE por movimiento de 0080, y la revalidacion
#   parent-side de 0270 que rechaza dejar una transferencia invalida tras
#   tocar una sola pata.
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
from app.core.modelos_transferencia import DatosTransferencia
from app.services.transferencias_service import TransferenciasService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat

IMPORTE = D("500.0000")


def datos_transferencia(origen: uuid.UUID, destino: uuid.UUID, **extra):
    base = {
        "transferencia_id": uuid.uuid4(),
        "hecho_id": uuid.uuid4(),
        "movimiento_salida_id": uuid.uuid4(),
        "movimiento_entrada_id": uuid.uuid4(),
        "conciliacion_salida_id": uuid.uuid4(),
        "conciliacion_entrada_id": uuid.uuid4(),
        "cuenta_origen_id": origen,
        "cuenta_destino_id": destino,
        "fecha_hecho": F("2027-03-15"),
        "fecha_movimiento": F("2027-03-15"),
        "moneda": "EUR",
        "importe_salida": IMPORTE,
        "importe_entrada": IMPORTE,
        "concepto": "Traspaso al ahorro",
    }
    base.update(extra)
    return DatosTransferencia(**base)


def saldo_de(admin, owner, cuenta_id) -> decimal.Decimal:
    fila = leer_fila(
        admin,
        owner,
        "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
        "WHERE cuenta_id = %s AND estado = 'ACTIVO'",
        (cuenta_id,),
    )
    return decimal.Decimal(fila[0])


# ==================================================================
# Camino correcto
# ==================================================================

def test_transferencia_valida_cumple_inv15(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    datos = datos_transferencia(cuenta, cuenta_destino)
    resultado = servicio_transferencias.transferir(contexto, datos)
    assert resultado.hecho_row_version == 1

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE hecho_id = %s), "
        "       (SELECT count(*) FROM gapto.transferencias WHERE id = %s), "
        "       (SELECT t.codigo FROM gapto.hechos_financieros h "
        "          JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id "
        "         WHERE h.id = %s)",
        (datos.hecho_id, datos.hecho_id, datos.transferencia_id, datos.hecho_id),
    ) == (0, 2, 1, "TRANSFERENCIA")


def test_los_signos_los_pone_el_motor(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """El llamante declara magnitudes; salida negativa y entrada positiva."""
    datos = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s), "
        "       (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s)",
        (datos.movimiento_salida_id, datos.movimiento_entrada_id),
    ) == (-IMPORTE, IMPORTE)


def test_la_liquidez_total_no_cambia(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """INV-16. Cambia donde esta el dinero, no cuanto hay."""
    antes = saldo_de(admin, contexto.owner_user_id, cuenta) + saldo_de(
        admin, contexto.owner_user_id, cuenta_destino
    )
    servicio_transferencias.transferir(
        contexto, datos_transferencia(cuenta, cuenta_destino)
    )
    despues = saldo_de(admin, contexto.owner_user_id, cuenta) + saldo_de(
        admin, contexto.owner_user_id, cuenta_destino
    )
    assert despues == antes
    assert saldo_de(admin, contexto.owner_user_id, cuenta) == -IMPORTE
    assert saldo_de(admin, contexto.owner_user_id, cuenta_destino) == IMPORTE


def test_las_conciliaciones_conservan_el_signo_de_su_movimiento(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Conciliar declara a que hecho pertenece un apunte, no invierte su
    sentido."""
    datos = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "WHERE id = %s",
        (datos.conciliacion_salida_id,),
    ) == (-IMPORTE,)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "WHERE id = %s",
        (datos.conciliacion_entrada_id,),
    ) == (IMPORTE,)


def test_auditoria_de_las_seis_filas(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    datos = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, datos)
    for registro_id in datos.identidades:
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT count(*) FROM gapto.auditoria "
            "WHERE registro_id = %s AND accion = 'CREAR'",
            (registro_id,),
        ) == (1,)


# ==================================================================
# Rechazos funcionales
# ==================================================================

def test_misma_cuenta(
    servicio_transferencias: TransferenciasService, contexto, cuenta
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto, datos_transferencia(cuenta, cuenta)
        )
    assert excinfo.value.codigo is CodigoError.MISMA_CUENTA


def test_importes_no_coinciden_en_misma_moneda(
    servicio_transferencias: TransferenciasService, contexto, cuenta, cuenta_destino
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto,
            datos_transferencia(cuenta, cuenta_destino, importe_entrada=D("400.0000")),
        )
    assert excinfo.value.codigo is CodigoError.IMPORTES_NO_COINCIDEN


def test_magnitud_negativa_rechazada(
    servicio_transferencias: TransferenciasService, contexto, cuenta, cuenta_destino
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto,
            datos_transferencia(cuenta, cuenta_destino, importe_salida=D("-500.0000")),
        )
    assert excinfo.value.codigo is CodigoError.SIGNOS_INCORRECTOS


def test_comision_embebida_rechazada(
    servicio_transferencias: TransferenciasService, contexto, cuenta, cuenta_destino
) -> None:
    """F04-D001. Una comision real tiene su propio hecho y su propio efecto."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto,
            datos_transferencia(cuenta, cuenta_destino, comision=D("2.5000")),
        )
    assert excinfo.value.codigo is CodigoError.COMISION_EMBEBIDA


def test_owner_distinto(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
    cuenta_ajena: uuid.UUID,
) -> None:
    """La cuenta ajena no es visible para este tenant: RLS la oculta antes de
    que el owner pueda compararse."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto, datos_transferencia(cuenta, cuenta_ajena)
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DESCONOCIDA


def test_cuenta_inexistente(
    servicio_transferencias: TransferenciasService, contexto, cuenta
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto, datos_transferencia(cuenta, uuid.uuid4())
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DESCONOCIDA


def test_moneda_invalida(
    servicio_transferencias: TransferenciasService, contexto, cuenta, cuenta_destino
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto, datos_transferencia(cuenta, cuenta_destino, moneda="eur")
        )
    assert excinfo.value.codigo is CodigoError.MONEDA_INVALIDA


def test_identidades_repetidas_en_el_lote(
    servicio_transferencias: TransferenciasService, contexto, cuenta, cuenta_destino
) -> None:
    """Seis identidades distintas. Reutilizar una dentro del mismo lote no es
    un ahorro: hace irreconocible que fila representa que."""
    compartido = uuid.uuid4()
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto,
            datos_transferencia(
                cuenta,
                cuenta_destino,
                movimiento_salida_id=compartido,
                conciliacion_salida_id=compartido,
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_cross_tenant(
    servicio_transferencias: TransferenciasService,
    otro_owner: uuid.UUID,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            ContextoOperacion.de_usuario(otro_owner),
            datos_transferencia(cuenta, cuenta_destino),
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DESCONOCIDA


# ==================================================================
# Multidivisa
# ==================================================================

def test_multidivisa_sin_igualdad_nominal(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_usd: uuid.UUID,
) -> None:
    """Con monedas distintas los importes pueden diferir y el motor NO infiere
    ningun tipo de cambio. No hay FX y no se fabrica."""
    datos = datos_transferencia(
        cuenta,
        cuenta_usd,
        importe_salida=D("500.0000"),
        importe_entrada=D("540.0000"),
    )
    servicio_transferencias.transferir(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s), "
        "       (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s)",
        (datos.movimiento_salida_id, datos.movimiento_entrada_id),
    ) == (D("-500.0000"), D("540.0000"))


# ==================================================================
# Idempotencia
# ==================================================================

def test_retry_idempotente(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    datos = datos_transferencia(cuenta, cuenta_destino)
    primero = servicio_transferencias.transferir(contexto, datos)
    segundo = servicio_transferencias.transferir(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.hecho_row_version == primero.hecho_row_version
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.transferencias WHERE id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE hecho_id = %s)",
        (datos.transferencia_id, datos.hecho_id),
    ) == (1, 2)


def test_lote_parcialmente_ocupado_es_conflicto(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Todo-o-nada. Si solo una parte de la reserva esta ocupada, la reserva se
    mezclo con otra operacion y no se completa a medias."""
    primera = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, primera)
    segunda = datos_transferencia(
        cuenta, cuenta_destino, hecho_id=primera.hecho_id
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(contexto, segunda)
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )


def test_misma_identidad_con_otro_par_de_movimientos(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """La identidad economica de una transferencia es su par de movimientos.

    Reutilizar el UUID de la transferencia con otras patas no es un reintento:
    es otra operacion.
    """
    primera = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, primera)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(
            contexto,
            datos_transferencia(
                cuenta, cuenta_destino, transferencia_id=primera.transferencia_id
            ),
        )
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )


# ==================================================================
# Garantias fisicas consumidas
# ==================================================================

def test_un_movimiento_no_participa_en_dos_transferencias(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Autoridad: uq_transferencias__movimiento_salida (0080).

    Se intenta directamente contra la base, saltandose el servicio, para
    comprobar que la garantia es FISICA y no depende de la prevalidacion.
    """
    primera = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, primera)
    segunda = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, segunda)

    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cursor.execute(
                "INSERT INTO gapto.transferencias "
                "(id, movimiento_salida_id, movimiento_entrada_id) "
                "VALUES (%s, %s, %s)",
                (
                    uuid.uuid4(),
                    primera.movimiento_salida_id,
                    segunda.movimiento_entrada_id,
                ),
            )
        admin.rollback()


def test_tocar_una_sola_pata_deja_estado_invalido_y_se_rechaza(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    dsn: str,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Revalidacion parent-side de 0270, verificada por CONDUCTA.

    Se abre una conexion propia SIN autocommit: la de verificacion lo tiene
    activado y el rechazo diferido llegaria en el propio UPDATE, que no es lo
    que hay que demostrar. Aqui el UPDATE se acepta y el COMMIT falla, que es
    el comportamiento real de un CONSTRAINT TRIGGER INITIALLY DEFERRED.

    HALLAZGO: el primer guardian que salta NO es la estructura de la
    transferencia sino la coherencia de conciliaciones —lo asignado al hecho
    (-500) supera el nuevo importe (-400)—. Ambas guardas viven en
    `fn_check_movimiento_padre`. Es el motivo por el que corregir el importe de
    una transferencia exige tocar cuatro filas a la vez y pertenece a OP-21.

    Es el germen del mutante N14.
    """
    datos = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, datos)

    with psycopg.connect(dsn) as propia, propia.cursor() as cursor:
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        cursor.execute(
            "UPDATE gapto.movimientos_tesoreria SET importe = %s WHERE id = %s",
            (D("-400.0000"), datos.movimiento_salida_id),
        )
        with pytest.raises(psycopg.errors.RaiseException):
            propia.commit()
        propia.rollback()

    # El rechazo fue atomico: la transferencia sigue intacta.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s",
        (datos.movimiento_salida_id,),
    ) == (-IMPORTE,)


def test_correccion_coherente_de_las_cuatro_filas_es_aceptada(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    dsn: str,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """La misma revalidacion ACEPTA el cambio coherente del agregado completo.

    No bastan las dos patas: hay que ajustar tambien las dos conciliaciones,
    porque lo asignado al hecho no puede superar el importe del movimiento. Sin
    este caso el test anterior solo demostraria que el trigger rechaza, no que
    DISCRIMINA.

    Esto es, literalmente, el contrato de OP-21 corregido a mano: cuatro filas
    en una transaccion o ninguna.
    """
    datos = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, datos)

    with psycopg.connect(dsn) as propia, propia.cursor() as cursor:
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        for conciliacion_id, importe in (
            (datos.conciliacion_salida_id, D("-400.0000")),
            (datos.conciliacion_entrada_id, D("400.0000")),
        ):
            cursor.execute(
                "UPDATE gapto.hecho_movimientos_tesoreria "
                "SET importe_asignado = %s WHERE id = %s",
                (importe, conciliacion_id),
            )
        for movimiento_id, importe in (
            (datos.movimiento_salida_id, D("-400.0000")),
            (datos.movimiento_entrada_id, D("400.0000")),
        ):
            cursor.execute(
                "UPDATE gapto.movimientos_tesoreria SET importe = %s WHERE id = %s",
                (importe, movimiento_id),
            )
        propia.commit()

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s), "
        "       (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s)",
        (datos.movimiento_salida_id, datos.movimiento_entrada_id),
    ) == (D("-400.0000"), D("400.0000"))


def test_lote_casi_completo_no_es_reintento(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Cuatro de seis identidades reutilizadas NO es un reintento.

    El par de movimientos coincide, de modo que la transferencia parece la
    misma. Pero las dos conciliaciones son nuevas: aceptarlo como reintento
    devolveria exito sin haber creado esas dos filas, y el llamante creeria
    que existen.

    Es el caso que discrimina la guarda de lote completo de la de identidad
    economica: sin ella, la segunda da por bueno lo que falta.
    """
    primera = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, primera)

    reusando = datos_transferencia(
        cuenta,
        cuenta_destino,
        transferencia_id=primera.transferencia_id,
        hecho_id=primera.hecho_id,
        movimiento_salida_id=primera.movimiento_salida_id,
        movimiento_entrada_id=primera.movimiento_entrada_id,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(contexto, reusando)
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE id = %s",
        (reusando.conciliacion_salida_id,),
    ) == (0,)


def test_las_mismas_seis_identidades_con_las_patas_invertidas(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Intercambiar salida y entrada es otra operacion, no un reintento.

    Las seis identidades existen y coinciden una a una, asi que la guarda de
    lote completo no lo detecta. Lo que cambia es el SENTIDO del dinero, y eso
    lo ve unicamente la comprobacion de identidad economica: la transferencia
    almacenada declara (salida, entrada) y aqui llegan al reves.
    """
    primera = datos_transferencia(cuenta, cuenta_destino)
    servicio_transferencias.transferir(contexto, primera)

    invertida = datos_transferencia(
        cuenta_destino,
        cuenta,
        transferencia_id=primera.transferencia_id,
        hecho_id=primera.hecho_id,
        movimiento_salida_id=primera.movimiento_entrada_id,
        movimiento_entrada_id=primera.movimiento_salida_id,
        conciliacion_salida_id=primera.conciliacion_entrada_id,
        conciliacion_entrada_id=primera.conciliacion_salida_id,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_transferencias.transferir(contexto, invertida)
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )
    # El sentido original no se ha tocado.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT movimiento_salida_id FROM gapto.transferencias WHERE id = %s",
        (primera.transferencia_id,),
    ) == (primera.movimiento_salida_id,)
