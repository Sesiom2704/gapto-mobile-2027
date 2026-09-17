# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_106_op06_op07_aportaciones.py
# Ruta: tests/backend/test_106_op06_op07_aportaciones.py
# Descripcion: F04-03 OP-06 y OP-07. Aportaciones reales y su vinculo con una
#   conciliacion: frontera F04-D009, actor desconocido, batch todo-o-nada,
#   version de la raiz, D-169 en moneda comparable y su ausencia en multidivisa,
#   INV-13 (no auto-vinculacion), tenant, auditoria y atomicidad.
# Version: 0.2.0
#   0.2.0 (F04-04): el recuento de posiciones se acota al tenant. Contarlas
#   globalmente era una expresion incorrecta de INV-04 y rompia en cuanto otra
#   subfase creo posiciones legitimas en la misma base.
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
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_tesoreria import (
    DatosAportacion,
    DatosConciliacion,
    DatosMovimiento,
)
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo_hechos
from app.repositories import tesoreria_repository as repo_tes
from app.services.hechos_service import HechosService
from app.services.tesoreria_service import TesoreriaService
from conftest import anular_movimiento, leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 5, 4)


def datos_hecho(**extra) -> DatosCreacionHecho:
    base = {
        "hecho_id": uuid.uuid4(),
        "fecha_hecho": FECHA,
        "moneda": "EUR",
        "presupuestable": True,
        "estado_localizacion": "DESCONOCIDA",
        "tipo_hecho_codigo": "GASTO",
        "importe_total": D("100.0000"),
    }
    base.update(extra)
    return DatosCreacionHecho(**base)


def aportacion(importe: str, **extra) -> DatosAportacion:
    base = {
        "aportacion_id": uuid.uuid4(),
        "importe": D(importe),
        "criterio_aportacion": "MANUAL",
    }
    base.update(extra)
    return DatosAportacion(**base)


@pytest.fixture()
def hecho(servicio: HechosService, contexto: ContextoOperacion):
    datos = datos_hecho()
    resultado = servicio.crear_hecho(contexto, datos)
    return datos.hecho_id, resultado.row_version


@pytest.fixture()
def salida_conciliada(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
):
    """Hecho de 100 EUR conciliado contra una salida de -100 EUR."""
    datos = datos_hecho()
    creado = servicio.crear_hecho(contexto, datos)
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=FECHA,
            importe=D("-100.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    conciliacion_id = uuid.uuid4()
    resultado = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=conciliacion_id,
            hecho_id=datos.hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-100.0000"),
        ),
        hecho_row_version_esperada=creado.row_version,
        movimiento_row_version_esperada=movimiento.row_version,
    )
    return {
        "hecho_id": datos.hecho_id,
        "movimiento_id": movimiento_id,
        "conciliacion_id": conciliacion_id,
        "hecho_rv": resultado.hecho_row_version,
        "mov_rv": resultado.movimiento_row_version,
    }


# ==================================================================
# OP-06
# ==================================================================

def test_una_aportacion_manual(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    una = aportacion("100.0000", actor_id=actor_a)
    resultado = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    assert resultado.aportaciones_creadas == 1
    assert resultado.hecho_row_version == version + 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_id, actor_id, importe, criterio_aportacion, "
        "porcentaje_aplicado, hecho_movimiento_tesoreria_id "
        "FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (hecho_id, actor_a, D("100.0000"), "MANUAL", None, None)


def test_batch_multi_actor_incrementa_la_version_una_sola_vez(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    resultado = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[
            aportacion("70.0000", actor_id=actor_a),
            aportacion("30.0000", actor_id=actor_b),
        ],
    )
    assert resultado.hecho_row_version == version + 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (2, D("100.0000"))


def test_actor_desconocido_permanece_null_y_no_se_vuelve_self(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """`actor_id=NULL` significa aportante real desconocido (F04-D009)."""
    hecho_id, version = hecho
    una = aportacion("100.0000")
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT actor_id FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (None,)


def test_el_mismo_actor_puede_aparecer_en_varias_filas(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """No hay UNIQUE artificial por actor: financiar en dos tramos es real."""
    hecho_id, version = hecho
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[
            aportacion("60.0000", actor_id=actor_a),
            aportacion("40.0000", actor_id=actor_a),
        ],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s AND actor_id = %s",
        (hecho_id, actor_a),
    )
    assert fila == (2,)


@pytest.mark.parametrize("importe", ["0.0000", "-10.0000"])
def test_importe_no_positivo_rechazado(
    servicio_tesoreria: TesoreriaService, contexto, hecho, importe
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[aportacion(importe)],
        )
    assert excinfo.value.codigo is CodigoError.IMPORTE_NO_POSITIVO


def test_criterio_invalido(
    servicio_tesoreria: TesoreriaService, contexto, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[aportacion("10.0000", criterio_aportacion="INVENTADO")],
        )
    assert excinfo.value.codigo is CodigoError.CRITERIO_INVALIDO


def test_porcentaje_null_es_valido(
    servicio_tesoreria: TesoreriaService, contexto, admin, hecho, actor_a
) -> None:
    hecho_id, version = hecho
    una = aportacion("100.0000", actor_id=actor_a, porcentaje_aplicado=None)
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT porcentaje_aplicado FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (None,)


def test_participacion_cuenta_es_snapshot_no_regla_viva(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """El importe materializado manda; el porcentaje solo documenta el origen."""
    hecho_id, version = hecho
    una = aportacion(
        "50.0000",
        actor_id=actor_a,
        criterio_aportacion="PARTICIPACION_CUENTA",
        porcentaje_aplicado=D("50.0000"),
    )
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe, porcentaje_aplicado, criterio_aportacion "
        "FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (D("50.0000"), D("50.0000"), "PARTICIPACION_CUENTA")


def test_no_modifica_efecto_atribuciones(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """INV-03/INV-04: aportacion y atribucion son dimensiones independientes."""
    hecho_id, version = hecho
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[aportacion("100.0000", actor_id=actor_a)],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        # Acotado al tenant: la conexion de verificacion tiene BYPASSRLS, y
        # ademas F04-04 crea posiciones legitimas en la misma base. Lo que
        # INV-04 prohibe es que ESTA operacion cree una posicion a ESTE
        # usuario, no que existan posiciones en el mundo.
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)


def test_hecho_anulado_rechazado(
    servicio: HechosService, servicio_tesoreria: TesoreriaService, contexto, hecho
) -> None:
    hecho_id, version = hecho
    anulado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="nunca debio existir",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=anulado.row_version,
            aportaciones=[aportacion("10.0000")],
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_hecho_cross_tenant(
    servicio_tesoreria: TesoreriaService, otro_owner: uuid.UUID, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[aportacion("10.0000")],
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_actor_de_otro_tenant_no_filtra(
    servicio_tesoreria: TesoreriaService, contexto, hecho, actor_ajeno
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[aportacion("10.0000", actor_id=actor_ajeno)],
        )
    assert excinfo.value.codigo is CodigoError.ACTOR_DESCONOCIDO


def test_version_desfasada(
    servicio_tesoreria: TesoreriaService, contexto, hecho
) -> None:
    hecho_id, version = hecho
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[aportacion("10.0000")],
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[aportacion("10.0000")],
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_rollback_de_batch(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor):
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportaciones=[
                aportacion("70.0000", actor_id=actor_a),
                aportacion("30.0000", criterio_aportacion="INVENTADO"),
            ],
        )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)


def test_auditoria_de_cada_aportacion(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    una = aportacion("100.0000", actor_id=actor_a)
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tabla, accion, datos_antes, datos_despues->>'importe', request_id "
        "FROM gapto.auditoria WHERE registro_id = %s",
        (una.aportacion_id,),
    )
    assert fila == (
        "hecho_aportaciones_pago",
        "CREAR",
        None,
        "100.0000",
        contexto.request_id,
    )


def test_rollback_por_fallo_de_auditoria(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho
    aportacion_id = uuid.uuid4()

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        repo_hechos.tocar_raiz(sesion, hecho_id, version)
        repo_tes.insertar_aportacion_si_no_existe(
            sesion,
            {
                "id": aportacion_id,
                "hecho_id": hecho_id,
                "actor_id": None,
                "importe": D("10.0000"),
                "porcentaje_aplicado": None,
                "criterio_aportacion": "MANUAL",
                "medio_pago_codigo": None,
                "hecho_movimiento_tesoreria_id": None,
            },
        )
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_APORTACIONES,
            registro_id=aportacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"password": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op06")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (aportacion_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)


# ------------------------------------------------------------------
# Idempotencia de lote (todo-o-nada)
# ------------------------------------------------------------------

def test_lote_totalmente_repetido_es_idempotente(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    lote = [aportacion("70.0000", actor_id=actor_a), aportacion("30.0000")]
    primero = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=lote,
    )
    segundo = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=lote,
    )
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.hecho_row_version == primero.hecho_row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (2,)


def test_lote_parcialmente_preexistente_rechazado(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    primera = aportacion("70.0000")
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[primera],
    )
    ausente = aportacion("30.0000")
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version + 1,
            aportaciones=[primera, ausente],
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (ausente.aportacion_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version + 1,)


def test_identidad_reutilizada_con_otra_intencion(
    servicio_tesoreria: TesoreriaService, contexto, hecho
) -> None:
    hecho_id, version = hecho
    una = aportacion("70.0000")
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    distinta = DatosAportacion(
        aportacion_id=una.aportacion_id,
        importe=D("99.0000"),
        criterio_aportacion="MANUAL",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version + 1,
            aportaciones=[distinta],
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


# ==================================================================
# OP-07
# ==================================================================

def test_vincular_desvincular_y_revincular(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    salida_conciliada,
    actor_a: uuid.UUID,
) -> None:
    hecho_id = salida_conciliada["hecho_id"]
    conciliacion_id = salida_conciliada["conciliacion_id"]
    una = aportacion("100.0000", actor_id=actor_a)
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[una],
    )

    vinculada = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=creada.hecho_row_version,
        aportacion_id=una.aportacion_id,
        destino=conciliacion_id,
    )
    assert vinculada.vinculada_a == conciliacion_id
    assert vinculada.hecho_row_version == creada.hecho_row_version + 1

    desvinculada = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=vinculada.hecho_row_version,
        aportacion_id=una.aportacion_id,
        destino=None,
    )
    assert desvinculada.vinculada_a is None

    revinculada = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=desvinculada.hecho_row_version,
        aportacion_id=una.aportacion_id,
        destino=conciliacion_id,
    )
    assert revinculada.vinculada_a == conciliacion_id

    # La fila es SIEMPRE la misma: se corrige el vinculo, no se borra y recrea.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (1,)


@pytest.mark.parametrize("repetido", [True, False])
def test_no_op_no_incrementa_version_ni_audita(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    salida_conciliada,
    repetido,
) -> None:
    """Mismo destino y NULL->NULL son no-ops: auditarlos afirmaria un cambio
    de realidad que no ocurrio."""
    hecho_id = salida_conciliada["hecho_id"]
    destino = salida_conciliada["conciliacion_id"] if repetido else None
    una = aportacion("100.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[una],
    )
    version = creada.hecho_row_version
    if repetido:
        vinculada = servicio_tesoreria.vincular_aportacion(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=version,
            aportacion_id=una.aportacion_id,
            destino=destino,
        )
        version = vinculada.hecho_row_version

    resultado = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportacion_id=una.aportacion_id,
        destino=destino,
    )
    assert resultado.sin_cambios is True
    assert resultado.hecho_row_version == version

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (una.aportacion_id,),
    )
    assert fila == (1 if repetido else 0,)


def test_conciliacion_de_otro_hecho(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    salida_conciliada,
) -> None:
    otros = datos_hecho()
    otro = servicio.crear_hecho(contexto, otros)
    una = aportacion("10.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=otros.hecho_id,
        hecho_row_version_esperada=otro.row_version,
        aportaciones=[una],
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.vincular_aportacion(
            contexto,
            hecho_id=otros.hecho_id,
            hecho_row_version_esperada=creada.hecho_row_version,
            aportacion_id=una.aportacion_id,
            destino=salida_conciliada["conciliacion_id"],
        )
    assert excinfo.value.codigo is CodigoError.CONCILIACION_DE_OTRO_HECHO


def test_vincular_a_una_entrada_rechazado(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """Una aportacion financia una SALIDA; una entrada no es su destino."""
    datos = datos_hecho(tipo_hecho_codigo="INGRESO")
    creado = servicio.crear_hecho(contexto, datos)
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=FECHA,
            importe=D("100.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    conciliacion_id = uuid.uuid4()
    conciliada = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=conciliacion_id,
            hecho_id=datos.hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("100.0000"),
        ),
        hecho_row_version_esperada=creado.row_version,
        movimiento_row_version_esperada=movimiento.row_version,
    )
    una = aportacion("100.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=conciliada.hecho_row_version,
        aportaciones=[una],
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.vincular_aportacion(
            contexto,
            hecho_id=datos.hecho_id,
            hecho_row_version_esperada=creada.hecho_row_version,
            aportacion_id=una.aportacion_id,
            destino=conciliacion_id,
        )
    assert excinfo.value.codigo is CodigoError.USO_EN_COBRO_NO_PERMITIDO


def test_d119_hace_inalcanzable_la_rama_de_movimiento_anulado_en_op07(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    salida_conciliada,
) -> None:
    """Un movimiento con asignaciones NO puede quedar anulado (D-119).

    De ahi se sigue que la rama MOVIMIENTO_ANULADO de OP-07 es inalcanzable por
    construccion: para ser destino de un vinculo hace falta una conciliacion, y
    mientras esa conciliacion exista el movimiento no puede anularse. La guarda
    del servicio se conserva como defensa en profundidad —protege si algun dia
    otra via crea ese estado— pero quien lo impide hoy es el contrato fisico, y
    este test lo demuestra en vez de fingir un escenario imposible.

    El caso SI alcanzable es el de OP-09 sobre un movimiento anulado y todavia
    sin conciliar, y esta cubierto en la suite de OP-08/OP-09.
    """
    with pytest.raises(psycopg.errors.RaiseException):
        anular_movimiento(
            admin, contexto.owner_user_id, salida_conciliada["movimiento_id"]
        )

    # El movimiento sigue ACTIVO y el vinculo se puede declarar con normalidad.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.movimientos_tesoreria WHERE id = %s",
        (salida_conciliada["movimiento_id"],),
    )
    assert fila == ("ACTIVO",)


def test_suma_vinculada_menor_e_igual_a_la_porcion(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    salida_conciliada,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """70 cabe, y 70+30 cuadra exacto: D-169 exige <=, no igualdad."""
    hecho_id = salida_conciliada["hecho_id"]
    conciliacion_id = salida_conciliada["conciliacion_id"]
    a = aportacion("70.0000", actor_id=actor_a)
    b = aportacion("30.0000", actor_id=actor_b)
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[a, b],
    )
    primera = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=creada.hecho_row_version,
        aportacion_id=a.aportacion_id,
        destino=conciliacion_id,
    )
    segunda = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=primera.hecho_row_version,
        aportacion_id=b.aportacion_id,
        destino=conciliacion_id,
    )
    assert segunda.vinculada_a == conciliacion_id


def test_exceso_en_moneda_comparable_rechazado(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    salida_conciliada,
    actor_a: uuid.UUID,
) -> None:
    hecho_id = salida_conciliada["hecho_id"]
    conciliacion_id = salida_conciliada["conciliacion_id"]
    a = aportacion("100.0000", actor_id=actor_a)
    b = aportacion("1.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[a, b],
    )
    primera = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=creada.hecho_row_version,
        aportacion_id=a.aportacion_id,
        destino=conciliacion_id,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.vincular_aportacion(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=primera.hecho_row_version,
            aportacion_id=b.aportacion_id,
            destino=conciliacion_id,
        )
    assert excinfo.value.codigo is CodigoError.SUMA_EXCEDE_PORCION


def test_multidivisa_no_se_compara_nominalmente(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta_usd: uuid.UUID,
    actor_a: uuid.UUID,
) -> None:
    """Hecho en EUR pagado desde cuenta USD: 100 EUR vinculados a una porcion
    de -90 USD NO se rechazan por nominal. 0310 excluye esa comparacion por
    diseno, no hay FX y no se inventa ninguno."""
    datos = datos_hecho()
    creado = servicio.crear_hecho(contexto, datos)
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta_usd,
            fecha_movimiento=FECHA,
            importe=D("-90.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    conciliacion_id = uuid.uuid4()
    conciliada = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=conciliacion_id,
            hecho_id=datos.hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-90.0000"),
        ),
        hecho_row_version_esperada=creado.row_version,
        movimiento_row_version_esperada=movimiento.row_version,
    )
    una = aportacion("100.0000", actor_id=actor_a)
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=conciliada.hecho_row_version,
        aportaciones=[una],
    )
    resultado = servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=creada.hecho_row_version,
        aportacion_id=una.aportacion_id,
        destino=conciliacion_id,
    )
    assert resultado.vinculada_a == conciliacion_id


def test_inv13_no_hay_auto_vinculacion_por_coincidencia(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    salida_conciliada,
    actor_a: uuid.UUID,
) -> None:
    """Importe identico, unica conciliacion y misma cuenta: aun asi el vinculo
    NO nace solo. Persistirlo exige declaracion explicita."""
    hecho_id = salida_conciliada["hecho_id"]
    una = aportacion("100.0000", actor_id=actor_a)
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_movimiento_tesoreria_id "
        "FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (None,)


def test_aportacion_sin_vincular_es_realidad_valida(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """C-18: se sabe quien financio, la conciliacion concreta aun no."""
    hecho_id, version = hecho
    una = aportacion("100.0000", actor_id=actor_a)
    servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[una],
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe, hecho_movimiento_tesoreria_id "
        "FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (D("100.0000"), None)


def test_version_desfasada_en_op07(
    servicio_tesoreria: TesoreriaService, contexto, salida_conciliada
) -> None:
    hecho_id = salida_conciliada["hecho_id"]
    una = aportacion("100.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[una],
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.vincular_aportacion(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=creada.hecho_row_version - 1,
            aportacion_id=una.aportacion_id,
            destino=salida_conciliada["conciliacion_id"],
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_aportacion_cross_tenant_en_op07(
    servicio_tesoreria: TesoreriaService, otro_owner: uuid.UUID, salida_conciliada
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.vincular_aportacion(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=salida_conciliada["hecho_id"],
            hecho_row_version_esperada=salida_conciliada["hecho_rv"],
            aportacion_id=uuid.uuid4(),
            destino=None,
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_auditoria_del_vinculo_con_antes_y_despues(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    salida_conciliada,
) -> None:
    hecho_id = salida_conciliada["hecho_id"]
    conciliacion_id = salida_conciliada["conciliacion_id"]
    una = aportacion("100.0000")
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=salida_conciliada["hecho_rv"],
        aportaciones=[una],
    )
    servicio_tesoreria.vincular_aportacion(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=creada.hecho_row_version,
        aportacion_id=una.aportacion_id,
        destino=conciliacion_id,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'hecho_movimiento_tesoreria_id', "
        "datos_despues->>'hecho_movimiento_tesoreria_id', motivo "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (una.aportacion_id,),
    )
    assert fila == (
        "ACTUALIZAR",
        None,
        str(conciliacion_id),
        "vinculo de aportacion a conciliacion",
    )
