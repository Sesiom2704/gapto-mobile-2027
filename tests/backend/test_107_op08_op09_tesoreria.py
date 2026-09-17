# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_107_op08_op09_tesoreria.py
# Ruta: tests/backend/test_107_op08_op09_tesoreria.py
# Descripcion: F04-03 OP-08 y OP-09. Movimientos reales y conciliacion con
#   DOBLE RAIZ (F04-D010): 100 % bancario preservado, movimiento sin hecho,
#   conciliacion parcial permanente, independencia de importe_total, las dos
#   versiones protegidas en SQL, tenant, auditoria, atomicidad, interleaving
#   real y casos canonicos.
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
from test_106_op06_op07_aportaciones import aportacion, datos_hecho

D = decimal.Decimal
FECHA = dt.date(2026, 5, 4)


def movimiento(cuenta_id: uuid.UUID, importe: str, **extra) -> DatosMovimiento:
    base = {
        "movimiento_id": uuid.uuid4(),
        "cuenta_id": cuenta_id,
        "fecha_movimiento": FECHA,
        "importe": D(importe),
        "clase_movimiento": "OPERACION",
    }
    base.update(extra)
    return DatosMovimiento(**base)


@pytest.fixture()
def hecho(servicio: HechosService, contexto: ContextoOperacion):
    datos = datos_hecho()
    resultado = servicio.crear_hecho(contexto, datos)
    return datos.hecho_id, resultado.row_version


@pytest.fixture()
def salida(servicio_tesoreria: TesoreriaService, contexto, cuenta: uuid.UUID):
    datos = movimiento(cuenta, "-100.0000")
    resultado = servicio_tesoreria.registrar_movimiento(contexto, datos)
    return datos.movimiento_id, resultado.row_version


# ==================================================================
# OP-08
# ==================================================================

@pytest.mark.parametrize(
    "importe, clase",
    [
        ("-100.0000", "OPERACION"),
        ("250.0000", "OPERACION"),
        ("-12.5000", "AJUSTE_SALDO"),
        ("12.5000", "AJUSTE_SALDO"),
    ],
)
def test_alta_de_movimiento(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    importe,
    clase,
) -> None:
    datos = movimiento(cuenta, importe, clase_movimiento=clase)
    resultado = servicio_tesoreria.registrar_movimiento(contexto, datos)
    assert resultado.row_version == 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT cuenta_id, importe, clase_movimiento, estado, "
        "confirmado_at IS NOT NULL FROM gapto.movimientos_tesoreria WHERE id = %s",
        (datos.movimiento_id,),
    )
    assert fila == (cuenta, D(importe), clase, "ACTIVO", True)


def test_ajuste_saldo_no_genera_efecto_economico(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """AJUSTE_SALDO afecta al ledger pero no crea gasto ni ingreso."""
    datos = movimiento(cuenta, "-30.0000", clase_movimiento="AJUSTE_SALDO")
    servicio_tesoreria.registrar_movimiento(contexto, datos)
    # Acotado al tenant: la conexion de verificacion tiene BYPASSRLS, de modo
    # que un count(*) global veria las filas de otros tests.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos e "
        "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "WHERE h.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)


def test_confirmado_at_del_llamante_se_preserva(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Y nunca se deriva de fecha_movimiento: son cosas distintas."""
    instante = dt.datetime(2026, 5, 6, 9, 30, tzinfo=dt.timezone.utc)
    datos = movimiento(cuenta, "-40.0000", confirmado_at=instante)
    servicio_tesoreria.registrar_movimiento(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT confirmado_at, fecha_movimiento FROM gapto.movimientos_tesoreria "
        "WHERE id = %s",
        (datos.movimiento_id,),
    )
    assert fila[0] == instante
    assert fila[1] == FECHA


def test_importe_cero_rechazado(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_movimiento(contexto, movimiento(cuenta, "0.0000"))
    assert excinfo.value.codigo is CodigoError.IMPORTE_CERO


def test_cuenta_inexistente(
    servicio_tesoreria: TesoreriaService, contexto
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_movimiento(
            contexto, movimiento(uuid.uuid4(), "-10.0000")
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DESCONOCIDA


def test_cuenta_de_otro_tenant_no_filtra(
    servicio_tesoreria: TesoreriaService, contexto, cuenta_ajena
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_movimiento(
            contexto, movimiento(cuenta_ajena, "-10.0000")
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DESCONOCIDA


def test_el_movimiento_conserva_el_cien_por_cien_en_cuenta_compartida(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """C-13. Cuenta 50/50 y salida de -100: se registran -100, no -50.

    Ademas no se persiste ninguna liquidez atribuible: repartir el movimiento
    por participacion destruiria el dato bancario, que es el unico hecho cierto.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute("BEGIN")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            for actor in (actor_a, actor_b):
                cursor.execute(
                    "INSERT INTO gapto.cuenta_participaciones "
                    "(id, cuenta_id, actor_id, porcentaje, vigente_desde) "
                    "VALUES (%s, %s, %s, 50, CURRENT_DATE)",
                    (uuid.uuid4(), cuenta, actor),
                )
            cursor.execute("COMMIT")
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    datos = movimiento(cuenta, "-100.0000")
    servicio_tesoreria.registrar_movimiento(contexto, datos)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe) FROM gapto.movimientos_tesoreria "
        "WHERE cuenta_id = %s",
        (cuenta,),
    )
    assert fila == (1, D("-100.0000"))


def test_movimiento_sin_hecho_ni_conciliacion_es_valido(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Importacion y clasificacion posterior: no se fabrica un hecho ficticio."""
    datos = movimiento(cuenta, "-77.0000")
    servicio_tesoreria.registrar_movimiento(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "WHERE movimiento_tesoreria_id = %s",
        (datos.movimiento_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)


def test_retry_con_uuid_estable_es_idempotente(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    datos = movimiento(cuenta, "-100.0000")
    primero = servicio_tesoreria.registrar_movimiento(contexto, datos)
    segundo = servicio_tesoreria.registrar_movimiento(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id = %s",
        (datos.movimiento_id,),
    )
    assert fila == (1,)


def test_mismo_uuid_con_otra_intencion(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    datos = movimiento(cuenta, "-100.0000")
    servicio_tesoreria.registrar_movimiento(contexto, datos)
    otro = DatosMovimiento(
        movimiento_id=datos.movimiento_id,
        cuenta_id=cuenta,
        fecha_movimiento=FECHA,
        importe=D("-55.0000"),
        clase_movimiento="OPERACION",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_movimiento(contexto, otro)
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_auditoria_del_movimiento(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    datos = movimiento(cuenta, "-100.0000")
    servicio_tesoreria.registrar_movimiento(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tabla, accion, datos_antes, datos_despues->>'importe' "
        "FROM gapto.auditoria WHERE registro_id = %s",
        (datos.movimiento_id,),
    )
    assert fila == ("movimientos_tesoreria", "CREAR", None, "-100.0000")


def test_rollback_por_auditoria_en_op08(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, cuenta
) -> None:
    movimiento_id = uuid.uuid4()

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        repo_tes.insertar_movimiento_si_no_existe(
            sesion,
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=FECHA,
            importe=D("-10.0000"),
            clase_movimiento="OPERACION",
            descripcion=None,
            confirmado_at=None,
        )
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_MOVIMIENTOS,
            registro_id=movimiento_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"token": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op08")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id = %s",
        (movimiento_id,),
    )
    assert fila == (0,)


# ==================================================================
# OP-09 — doble raiz
# ==================================================================

def test_conciliacion_completa_incrementa_ambas_versiones_una_vez(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    resultado = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-100.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    assert resultado.hecho_row_version == hecho_rv + 1
    assert resultado.movimiento_row_version == mov_rv + 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT h.row_version, m.row_version FROM gapto.hechos_financieros h, "
        "gapto.movimientos_tesoreria m WHERE h.id = %s AND m.id = %s",
        (hecho_id, movimiento_id),
    )
    assert fila == (hecho_rv + 1, mov_rv + 1)


def test_conciliacion_parcial_permanente_es_valida(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    """C-17. Puede quedar porcion sin conciliar para siempre."""
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT sum(importe_asignado) FROM gapto.hecho_movimientos_tesoreria "
        "WHERE movimiento_tesoreria_id = %s",
        (movimiento_id,),
    )
    assert fila == (D("-40.0000"),)


def test_dos_hechos_sobre_un_movimiento(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    hecho,
    salida,
) -> None:
    """C-19."""
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    primera = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-60.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    otros = datos_hecho()
    otro = servicio.crear_hecho(contexto, otros)
    segunda = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=otros.hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=otro.row_version,
        movimiento_row_version_esperada=primera.movimiento_row_version,
    )
    assert segunda.movimiento_row_version == primera.movimiento_row_version + 1


def test_dos_movimientos_sobre_un_hecho(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
    hecho,
) -> None:
    hecho_id, hecho_rv = hecho
    primero = movimiento(cuenta, "-60.0000")
    segundo = movimiento(cuenta, "-40.0000")
    m1 = servicio_tesoreria.registrar_movimiento(contexto, primero)
    m2 = servicio_tesoreria.registrar_movimiento(contexto, segundo)
    a = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=primero.movimiento_id,
            importe_asignado=D("-60.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=m1.row_version,
    )
    b = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=segundo.movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=a.hecho_row_version,
        movimiento_row_version_esperada=m2.row_version,
    )
    assert b.hecho_row_version == hecho_rv + 2


def test_signo_incompatible(
    servicio_tesoreria: TesoreriaService, contexto, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("40.0000"),
            ),
            hecho_row_version_esperada=hecho_rv,
            movimiento_row_version_esperada=mov_rv,
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_excede_importe_del_movimiento(
    servicio_tesoreria: TesoreriaService, contexto, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-140.0000"),
            ),
            hecho_row_version_esperada=hecho_rv,
            movimiento_row_version_esperada=mov_rv,
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_IMPORTE_MOVIMIENTO


def test_movimiento_anulado_sin_conciliar_rechazado(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    """Caso SI alcanzable de MOVIMIENTO_ANULADO: todavia sin asignaciones."""
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    anular_movimiento(admin, contexto.owner_user_id, movimiento_id)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-40.0000"),
            ),
            hecho_row_version_esperada=hecho_rv,
            movimiento_row_version_esperada=mov_rv + 1,
        )
    assert excinfo.value.codigo is CodigoError.MOVIMIENTO_ANULADO


def test_hecho_anulado_rechazado_en_op09(
    servicio: HechosService, servicio_tesoreria: TesoreriaService, contexto, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    anulado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=hecho_rv,
        motivo_anulacion="duplicado",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-40.0000"),
            ),
            hecho_row_version_esperada=anulado.row_version,
            movimiento_row_version_esperada=mov_rv,
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_pareja_duplicada_es_ya_conciliado(
    servicio_tesoreria: TesoreriaService, contexto, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    primera = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-20.0000"),
            ),
            hecho_row_version_esperada=primera.hecho_row_version,
            movimiento_row_version_esperada=primera.movimiento_row_version,
        )
    assert excinfo.value.codigo is CodigoError.YA_CONCILIADO


def test_independencia_de_importe_total(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """La suma conciliada NO tiene que igualar importe_total."""
    datos = datos_hecho(importe_total=D("100.0000"))
    creado = servicio.crear_hecho(contexto, datos)
    mov = movimiento(cuenta, "-30.0000")
    m = servicio_tesoreria.registrar_movimiento(contexto, mov)
    resultado = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=datos.hecho_id,
            movimiento_tesoreria_id=mov.movimiento_id,
            importe_asignado=D("-30.0000"),
        ),
        hecho_row_version_esperada=creado.row_version,
        movimiento_row_version_esperada=m.row_version,
    )
    assert resultado.idempotente is False


@pytest.mark.parametrize("cual", ["hecho", "movimiento"])
def test_version_desfasada_no_incrementa_ninguna_raiz(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
    cual,
) -> None:
    """F04-D010: si UNA version esta desfasada, NINGUNA de las dos cambia."""
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-40.0000"),
            ),
            hecho_row_version_esperada=hecho_rv + (99 if cual == "hecho" else 0),
            movimiento_row_version_esperada=mov_rv
            + (99 if cual == "movimiento" else 0),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT h.row_version, m.row_version, "
        "(SELECT count(*) FROM gapto.hecho_movimientos_tesoreria r "
        "  WHERE r.hecho_id = h.id) "
        "FROM gapto.hechos_financieros h, gapto.movimientos_tesoreria m "
        "WHERE h.id = %s AND m.id = %s",
        (hecho_id, movimiento_id),
    )
    assert fila == (hecho_rv, mov_rv, 0)


def test_retry_idempotente_de_op09(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    datos = DatosConciliacion(
        conciliacion_id=uuid.uuid4(),
        hecho_id=hecho_id,
        movimiento_tesoreria_id=movimiento_id,
        importe_asignado=D("-40.0000"),
    )
    primero = servicio_tesoreria.conciliar(
        contexto,
        datos,
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    segundo = servicio_tesoreria.conciliar(
        contexto,
        datos,
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    assert segundo.idempotente is True
    assert segundo.hecho_row_version == primero.hecho_row_version
    assert segundo.movimiento_row_version == primero.movimiento_row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "WHERE movimiento_tesoreria_id = %s",
        (movimiento_id,),
    )
    assert fila == (1,)


def test_mismo_uuid_con_otra_intencion_en_op09(
    servicio_tesoreria: TesoreriaService, contexto, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    conciliacion_id = uuid.uuid4()
    servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=conciliacion_id,
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=conciliacion_id,
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-10.0000"),
            ),
            hecho_row_version_esperada=hecho_rv + 1,
            movimiento_row_version_esperada=mov_rv + 1,
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_movimiento_cross_tenant(
    servicio_tesoreria: TesoreriaService, otro_owner: uuid.UUID, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            ContextoOperacion.de_usuario(otro_owner),
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-40.0000"),
            ),
            hecho_row_version_esperada=hecho_rv,
            movimiento_row_version_esperada=mov_rv,
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_auditoria_de_la_conciliacion(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    conciliacion_id = uuid.uuid4()
    servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=conciliacion_id,
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=D("-40.0000"),
        ),
        hecho_row_version_esperada=hecho_rv,
        movimiento_row_version_esperada=mov_rv,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tabla, accion, datos_despues->>'importe_asignado' "
        "FROM gapto.auditoria WHERE registro_id = %s",
        (conciliacion_id,),
    )
    assert fila == ("hecho_movimientos_tesoreria", "CREAR", "-40.0000")


def test_rollback_por_auditoria_en_op09(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho, salida
) -> None:
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    conciliacion_id = uuid.uuid4()

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        repo_hechos.tocar_raiz(sesion, hecho_id, hecho_rv)
        repo_tes.tocar_movimiento(sesion, movimiento_id, mov_rv)
        repo_tes.insertar_conciliacion_si_no_existe(
            sesion,
            {
                "id": conciliacion_id,
                "hecho_id": hecho_id,
                "movimiento_tesoreria_id": movimiento_id,
                "importe_asignado": D("-40.0000"),
            },
        )
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_CONCILIACIONES,
            registro_id=conciliacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"secret": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op09")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT h.row_version, m.row_version FROM gapto.hechos_financieros h, "
        "gapto.movimientos_tesoreria m WHERE h.id = %s AND m.id = %s",
        (hecho_id, movimiento_id),
    )
    assert fila == (hecho_rv, mov_rv)


# ==================================================================
# Interleaving real
# ==================================================================

def _escritura_ajena(admin: psycopg.Connection, owner: uuid.UUID, sql: str, params):
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            cursor.execute(sql, params)
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


def test_carrera_real_sobre_la_version_del_hecho(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    """Escritura ajena YA CONFIRMADA entre la lectura y el incremento."""
    hecho_id, version = hecho
    visto: dict = {}

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        assert repo_hechos.leer_estado(sesion, hecho_id)[0] == version
        _escritura_ajena(
            admin,
            contexto.owner_user_id,
            "UPDATE gapto.hechos_financieros SET notas = 'ajena', "
            "row_version = row_version + 1 WHERE id = %s",
            (hecho_id,),
        )
        visto["tocar"] = repo_hechos.tocar_raiz(sesion, hecho_id, version)

    unidad.ejecutar(contexto, operacion, nombre="carrera-hecho")
    assert visto["tocar"] is None


def test_carrera_real_sobre_la_version_del_movimiento(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, salida
) -> None:
    """La SEGUNDA raiz necesita su propia guarda SQL, no basta la del hecho."""
    movimiento_id, version = salida
    visto: dict = {}

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        assert repo_tes.leer_movimiento(sesion, movimiento_id)[0] == version
        _escritura_ajena(
            admin,
            contexto.owner_user_id,
            "UPDATE gapto.movimientos_tesoreria SET descripcion = 'ajena', "
            "row_version = row_version + 1 WHERE id = %s",
            (movimiento_id,),
        )
        visto["tocar"] = repo_tes.tocar_movimiento(sesion, movimiento_id, version)

    unidad.ejecutar(contexto, operacion, nombre="carrera-movimiento")
    assert visto["tocar"] is None


def test_op09_con_una_raiz_actualizada_concurrentemente(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    salida,
) -> None:
    """Interleaving sobre OP-09 completa: el movimiento se mueve por debajo."""
    hecho_id, hecho_rv = hecho
    movimiento_id, mov_rv = salida
    _escritura_ajena(
        admin,
        contexto.owner_user_id,
        "UPDATE gapto.movimientos_tesoreria SET descripcion = 'ajena', "
        "row_version = row_version + 1 WHERE id = %s",
        (movimiento_id,),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.conciliar(
            contexto,
            DatosConciliacion(
                conciliacion_id=uuid.uuid4(),
                hecho_id=hecho_id,
                movimiento_tesoreria_id=movimiento_id,
                importe_asignado=D("-40.0000"),
            ),
            hecho_row_version_esperada=hecho_rv,
            movimiento_row_version_esperada=mov_rv,
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (hecho_rv,)
