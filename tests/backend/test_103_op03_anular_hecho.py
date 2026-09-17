# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_103_op03_anular_hecho.py
# Ruta: tests/backend/test_103_op03_anular_hecho.py
# Descripcion: F04-01 OP-03. Anulacion de un hecho que nunca debio existir:
#   transicion ACTIVO -> ANULADO sin borrado fisico, motivo obligatorio,
#   preservacion de vinculos historicos, rechazo cuando el hecho SI tuvo
#   realidad, optimistic locking, tenant y atomicidad.
#
#   Incluye tambien la frontera diferida a F04-02: corregir tipo_hecho_id con
#   efectos dependientes debe fallar cerrado en vez de inventar que ocurre con
#   esos efectos.
# Version: 0.2.0
#   0.2.0 (F04-02): F04-D004 sustituye el error transitorio
#   DECISION_DIFERIDA_F04_02 por CORRECCION_AGREGADA_REQUERIDA.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import CamposCorreccion
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo
from app.services.hechos_service import HechosService
from conftest import leer_fila
from test_101_op01_crear_hecho import datos_minimos


@pytest.fixture()
def hecho(servicio: HechosService, contexto: ContextoOperacion):
    datos = datos_minimos(
        concepto="hecho a anular", importe_total=decimal.Decimal("20.0000")
    )
    resultado = servicio.crear_hecho(contexto, datos)
    return datos.hecho_id, resultado.row_version


def _como_owner(admin: psycopg.Connection, owner: uuid.UUID, sentencias) -> None:
    """Monta datos dependientes bajo gapto_owner con contexto de tenant."""
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            for sql, params in sentencias:
                cursor.execute(sql, params)
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


# ------------------------------------------------------------------
# Camino correcto
# ------------------------------------------------------------------

def test_transicion_activo_a_anulado(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    resultado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="se registro dos veces por error",
    )

    assert resultado.estado == "ANULADO"
    assert resultado.row_version == version + 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, anulado_at IS NOT NULL, motivo_anulacion, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == ("ANULADO", True, "se registro dos veces por error", version + 1)


def test_no_hay_borrado_fisico(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="nunca debio existir",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(concepto) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (1, "hecho a anular")


def test_runtime_no_conserva_delete_sobre_hechos(admin: psycopg.Connection) -> None:
    """La imposibilidad de hard delete es fisica, no solo de codigo."""
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT has_table_privilege('gapto_runtime', 'gapto.hechos_financieros', "
            "'DELETE')"
        )
        assert cursor.fetchone()[0] is False


def test_auditoria_de_anulacion(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="duplicado",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'estado', datos_despues->>'estado', motivo "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ANULAR'",
        (hecho_id,),
    )
    assert fila == ("ANULAR", "ACTIVO", "ANULADO", "duplicado")


def test_los_vinculos_historicos_se_preservan(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """Una prevision vinculada sigue existiendo tras anular el hecho."""
    hecho_id, version = hecho
    prevision_id = uuid.uuid4()
    vinculo_id = uuid.uuid4()
    _como_owner(
        admin,
        contexto.owner_user_id,
        [
            (
                "INSERT INTO gapto.previsiones (id, owner_user_id, concepto, "
                "tipo_hecho_id, fecha_esperada_desde, fecha_esperada_hasta, "
                "flujo_tesoreria_esperado, moneda, importe_esperado, presupuestable) "
                "SELECT %s, %s, 'prevision F04-01', t.id, CURRENT_DATE, "
                "CURRENT_DATE, 'SALIDA', 'EUR', '20.0000', true "
                "FROM gapto.tipos_hecho t WHERE t.codigo = 'GASTO'",
                (prevision_id, contexto.owner_user_id),
            ),
            (
                "INSERT INTO gapto.prevision_hechos (id, prevision_id, hecho_id, "
                "importe_asignado) VALUES (%s, %s, %s, '20.0000')",
                (vinculo_id, prevision_id, hecho_id),
            ),
        ],
    )

    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="nunca debio existir",
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.prevision_hechos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (1,)


def test_el_hecho_anulado_deja_de_contar_como_activo(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """El read-model conserva el hecho pero con estado ANULADO."""
    hecho_id, version = hecho
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="duplicado",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.v_hechos_resumen WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == ("ANULADO",)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.v_hechos_resumen "
        "WHERE hecho_id = %s AND estado = 'ACTIVO'",
        (hecho_id,),
    )
    assert fila == (0,)


# ------------------------------------------------------------------
# Motivo, estado, version y tenant
# ------------------------------------------------------------------

@pytest.mark.parametrize("motivo", [None, "", "  "])
def test_motivo_de_anulacion_obligatorio(
    servicio: HechosService, contexto: ContextoOperacion, hecho, motivo
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo_anulacion=motivo,
        )
    assert excinfo.value.codigo is CodigoError.MOTIVO_AUSENTE


def test_segunda_anulacion_con_otro_request_es_conflicto(
    servicio: HechosService, owner: uuid.UUID, hecho
) -> None:
    """Eleccion documentada: NO idempotente, para no perder el segundo motivo."""
    hecho_id, version = hecho
    primero = servicio.anular_hecho(
        ContextoOperacion.de_usuario(owner),
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="motivo uno",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            ContextoOperacion.de_usuario(owner),
            hecho_id=hecho_id,
            row_version_esperada=primero.row_version,
            motivo_anulacion="motivo distinto",
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_reintento_de_la_misma_anulacion_es_idempotente(
    servicio: HechosService, owner: uuid.UUID, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho
    ctx = ContextoOperacion.de_usuario(owner)

    primero = servicio.anular_hecho(
        ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="duplicado",
    )
    segundo = servicio.anular_hecho(
        ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="duplicado",
    )
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version

    fila = leer_fila(
        admin,
        owner,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (hecho_id,),
    )
    assert fila == (1,)


def test_row_version_desfasada_en_anulacion(
    servicio: HechosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(notas="corregido"),
        motivo="faltaba la nota",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo_anulacion="duplicado",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_aislamiento_tenant_en_anulacion(
    servicio: HechosService, otro_owner: uuid.UUID, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo_anulacion="intento cross-tenant",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_hecho_inexistente_en_anulacion(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            contexto,
            hecho_id=uuid.uuid4(),
            row_version_esperada=1,
            motivo_anulacion="motivo",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


# ------------------------------------------------------------------
# Un hecho con realidad asociada NO se anula
# ------------------------------------------------------------------

def test_hecho_con_tesoreria_vinculada_no_se_anula(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    cuenta_id = uuid.uuid4()
    movimiento_id = uuid.uuid4()
    conciliacion_id = uuid.uuid4()
    _como_owner(
        admin,
        contexto.owner_user_id,
        [
            (
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, "
                "naturaleza, moneda, computa_liquidez, computa_patrimonio, "
                "permite_negativo) VALUES (%s, %s, 'Cuenta F04-01', 'CORRIENTE', "
                "'ACTIVO', 'EUR', true, true, false)",
                (cuenta_id, contexto.owner_user_id),
            ),
            (
                "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, "
                "fecha_movimiento, importe, confirmado_at, clase_movimiento) "
                "VALUES (%s, %s, CURRENT_DATE, '-20.0000', CURRENT_TIMESTAMP, "
                "'OPERACION')",
                (movimiento_id, cuenta_id),
            ),
            (
                "INSERT INTO gapto.hecho_movimientos_tesoreria (id, hecho_id, "
                "movimiento_tesoreria_id, importe_asignado) "
                "VALUES (%s, %s, %s, '-20.0000')",
                (conciliacion_id, hecho_id, movimiento_id),
            ),
        ],
    )

    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo_anulacion="quiero borrarlo",
        )
    assert excinfo.value.codigo is CodigoError.HECHO_CON_REALIDAD_ASOCIADA

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == ("ACTIVO",)


# ------------------------------------------------------------------
# Frontera diferida a F04-02
# ------------------------------------------------------------------

def test_corregir_tipo_hecho_con_efectos_dependientes_falla_cerrado(  # F04-D004
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    efecto_id = uuid.uuid4()
    _como_owner(
        admin,
        contexto.owner_user_id,
        [
            (
                "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, "
                "importe_delta, estado_atribucion) "
                "VALUES (%s, %s, 'GASTO', '20.0000', 'NO_DISPONIBLE')",
                (efecto_id, hecho_id),
            )
        ],
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'INGRESO'",
        (),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(tipo_hecho_id=fila[0]),
            motivo="arquetipo equivocado",
        )
    assert excinfo.value.codigo is CodigoError.CORRECCION_AGREGADA_REQUERIDA


# ------------------------------------------------------------------
# Atomicidad
# ------------------------------------------------------------------

def test_rollback_completo_si_falla_la_auditoria_de_anulacion(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho

    def operacion(sesion):
        repo.exigir_contexto(sesion)
        repo.anular(sesion, hecho_id, version, "no debe persistir")
        auditoria.registrar(
            sesion,
            tabla=repo.TABLA,
            registro_id=hecho_id,
            accion=auditoria.ACCION_ANULAR,
            datos_despues_json='{"secret": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op03")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, anulado_at, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == ("ACTIVO", None, version)
