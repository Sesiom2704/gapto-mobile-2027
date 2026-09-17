# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_108_d169_concurrencia.py
# Ruta: tests/backend/test_108_d169_concurrencia.py
# Descripcion: F04-D011. Evidencia concurrente de D-169 en DOS CAPAS.
#
#   CAPA PRIMARIA — fisica. Dos transacciones PostgreSQL controladas
#   directamente, sin pasar por el servicio. Es lo que hay que discriminar:
#   D-169 y D-171, no el optimistic locking del motor. Ambas vinculan 70 a una
#   porcion de 100 ANTES de que ninguna confirme, de modo que cada una observa
#   individualmente un estado valido —0 vinculados, 70 <= 100—. La primera
#   confirma; la segunda debe morir al validar el constraint diferido, que
#   relee el estado final y encuentra 140 > 100.
#
#   No hay sleep. No hay SELECT SUM(...) preventivo. La invariante no la
#   sostiene ninguna lectura previa: la sostiene el COMMIT.
#
#   CAPA COMPLEMENTARIA — integracion del servicio, con threading.Barrier. Si
#   `row_version` serializa las dos operaciones antes de llegar al trigger, eso
#   es proteccion adicional correcta y NO un fallo de la prueba fisica: son dos
#   defensas distintas y la de arriba no exime de la de abajo.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import threading
from typing import Any
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.services.hechos_service import HechosService
from app.services.tesoreria_service import TesoreriaService
from conftest import ROL_RUNTIME, leer_fila
from test_106_op06_op07_aportaciones import aportacion, datos_hecho

D = decimal.Decimal
FECHA = dt.date(2026, 5, 4)


@pytest.fixture()
def porcion_de_cien(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
):
    """Hecho en EUR conciliado contra una salida de -100 EUR desde cuenta EUR.

    Monedas comparables a proposito: D-169 solo compara en ese caso.
    """
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
        "conciliacion_id": conciliacion_id,
        "hecho_rv": resultado.hecho_row_version,
    }


def _abrir_runtime(dsn: str, owner: uuid.UUID) -> psycopg.Connection:
    """Conexion con transaccion abierta, rol runtime y contexto de tenant.

    Se controla el ciclo BEGIN/COMMIT a mano justamente para poder intercalar
    las dos transacciones; la unidad de trabajo del motor no lo permite, y no
    debe permitirlo.
    """
    conexion = psycopg.connect(dsn)
    conexion.autocommit = False
    with conexion.cursor() as cursor:
        cursor.execute(f"SET ROLE {ROL_RUNTIME}")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, true),"
            "       set_config('gapto.actor_tipo', 'USUARIO', true),"
            "       set_config('gapto.actor_user_id', %s, true),"
            "       set_config('gapto.request_id', %s, true)",
            (str(owner), str(owner), str(uuid.uuid4())),
        )
    return conexion


def _vincular_directo(
    conexion: psycopg.Connection,
    hecho_id: uuid.UUID,
    conciliacion_id: uuid.UUID,
    importe: str,
) -> uuid.UUID:
    aportacion_id = uuid.uuid4()
    with conexion.cursor() as cursor:
        cursor.execute(
            "INSERT INTO gapto.hecho_aportaciones_pago "
            "(id, hecho_id, actor_id, importe, criterio_aportacion, "
            " hecho_movimiento_tesoreria_id) "
            "VALUES (%s, %s, NULL, %s, 'MANUAL', %s)",
            (aportacion_id, hecho_id, D(importe), conciliacion_id),
        )
    return aportacion_id


# ==================================================================
# CAPA PRIMARIA — prueba fisica
# ==================================================================

def test_d169_dos_transacciones_validas_por_separado_no_pueden_confirmar_juntas(
    dsn: str,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    porcion_de_cien,
) -> None:
    """El estado final invalido no puede confirmar.

    Secuencia exacta, sin ninguna espera:
      1. A abre transaccion; B abre transaccion.
      2. A inserta 70 vinculados. B inserta 70 vinculados. Ninguna ha
         confirmado, de modo que ninguna ve a la otra: cada una observa 0
         vinculados sobre una porcion de 100 y su propio 70 cabe.
      3. COMMIT A confirma: 70 <= 100.
      4. COMMIT B debe FALLAR: el constraint diferido relee el estado final y
         encuentra 140 > 100.
      5. Solo quedan 70 vinculados.

    Si esta prueba se sustituyese por un SELECT SUM(...) previo, pasaria
    igualmente y no demostraria nada: las dos lecturas previas son validas. Lo
    que se demuestra aqui es que la invariante la sostiene el COMMIT.
    """
    hecho_id = porcion_de_cien["hecho_id"]
    conciliacion_id = porcion_de_cien["conciliacion_id"]

    a = _abrir_runtime(dsn, contexto.owner_user_id)
    b = _abrir_runtime(dsn, contexto.owner_user_id)
    try:
        _vincular_directo(a, hecho_id, conciliacion_id, "70.0000")
        _vincular_directo(b, hecho_id, conciliacion_id, "70.0000")

        a.commit()  # 70 <= 100

        with pytest.raises(psycopg.errors.RaiseException):
            b.commit()  # 140 > 100 al validar el constraint diferido
    finally:
        for conexion in (a, b):
            try:
                conexion.rollback()
            finally:
                conexion.close()

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), COALESCE(sum(importe), 0) "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_movimiento_tesoreria_id = %s",
        (conciliacion_id,),
    )
    assert fila == (1, D("70.0000"))


def test_d169_permite_confirmar_cuando_el_estado_final_si_cabe(
    dsn: str,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    porcion_de_cien,
) -> None:
    """Contraprueba: la misma coreografia con 70 + 30 confirma las dos.

    Sin ella, la prueba anterior no distinguiria entre "el trigger valida el
    estado final" y "el trigger rechaza siempre la segunda transaccion".
    """
    hecho_id = porcion_de_cien["hecho_id"]
    conciliacion_id = porcion_de_cien["conciliacion_id"]

    a = _abrir_runtime(dsn, contexto.owner_user_id)
    b = _abrir_runtime(dsn, contexto.owner_user_id)
    try:
        _vincular_directo(a, hecho_id, conciliacion_id, "70.0000")
        _vincular_directo(b, hecho_id, conciliacion_id, "30.0000")
        a.commit()
        b.commit()
    finally:
        for conexion in (a, b):
            try:
                conexion.rollback()
            finally:
                conexion.close()

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), COALESCE(sum(importe), 0) "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_movimiento_tesoreria_id = %s",
        (conciliacion_id,),
    )
    assert fila == (2, D("100.0000"))


def test_d169_no_compara_en_multidivisa_ni_siquiera_concurrentemente(
    dsn: str,
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta_usd: uuid.UUID,
) -> None:
    """Hecho EUR contra cuenta USD: 0310 excluye la comparacion por diseno.

    Dos vinculos de 70 sobre una porcion de -90 USD confirman los dos. No es
    un agujero: es que 100 EUR y 90 USD no son comparables sin un tipo de
    cambio, y el motor no inventa ninguno.
    """
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
    servicio_tesoreria.conciliar(
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

    a = _abrir_runtime(dsn, contexto.owner_user_id)
    b = _abrir_runtime(dsn, contexto.owner_user_id)
    try:
        _vincular_directo(a, datos.hecho_id, conciliacion_id, "70.0000")
        _vincular_directo(b, datos.hecho_id, conciliacion_id, "70.0000")
        a.commit()
        b.commit()
    finally:
        for conexion in (a, b):
            try:
                conexion.rollback()
            finally:
                conexion.close()

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_movimiento_tesoreria_id = %s",
        (conciliacion_id,),
    )
    assert fila == (2,)


# ==================================================================
# CAPA COMPLEMENTARIA — integracion del servicio
# ==================================================================

def test_d169_dos_op07_concurrentes_por_el_servicio(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    porcion_de_cien,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """Dos OP-07 que juntas excederian la porcion, lanzadas a la vez.

    Se sincronizan con una barrera, sin sleep. El resultado exigido es que UNA
    triunfe y la otra falle; el codigo concreto puede ser SUMA_EXCEDE_PORCION,
    VERSION_DESFASADA o CONFLICTO_CONCURRENCIA segun que defensa actue primero
    —prevalidacion, optimistic locking del hecho o el propio trigger—, y las
    tres son correctas. Lo que NO puede ocurrir es que triunfen las dos.
    """
    hecho_id = porcion_de_cien["hecho_id"]
    conciliacion_id = porcion_de_cien["conciliacion_id"]
    primera = aportacion("70.0000", actor_id=actor_a)
    segunda = aportacion("70.0000", actor_id=actor_b)
    creadas = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=porcion_de_cien["hecho_rv"],
        aportaciones=[primera, segunda],
    )
    version = creadas.hecho_row_version

    barrera = threading.Barrier(2)
    resultados: list[Any] = []
    cerrojo = threading.Lock()

    def intentar(aportacion_id: uuid.UUID) -> None:
        barrera.wait()
        try:
            servicio_tesoreria.vincular_aportacion(
                ContextoOperacion.de_usuario(contexto.owner_user_id),
                hecho_id=hecho_id,
                hecho_row_version_esperada=version,
                aportacion_id=aportacion_id,
                destino=conciliacion_id,
            )
            salida: Any = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        with cerrojo:
            resultados.append(salida)

    hilos = [
        threading.Thread(target=intentar, args=(primera.aportacion_id,)),
        threading.Thread(target=intentar, args=(segunda.aportacion_id,)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert resultados.count("OK") == 1, resultados
    assert len(resultados) == 2
    fallo = [r for r in resultados if r != "OK"][0]
    assert fallo in (
        CodigoError.SUMA_EXCEDE_PORCION,
        CodigoError.VERSION_DESFASADA,
        CodigoError.CONFLICTO_CONCURRENCIA,
        CodigoError.VIOLACION_INVARIANTE_FISICA,
    ), fallo

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT COALESCE(sum(importe), 0) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_movimiento_tesoreria_id = %s",
        (conciliacion_id,),
    )
    assert fila == (D("70.0000"),)


# ==================================================================
# F04-D012 — prevalidacion acumulada y vinculo inicial en OP-06
# ==================================================================

def test_prevalidacion_acumulada_detecta_el_exceso_del_propio_lote(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    porcion_de_cien,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """60 ya vinculados + 25 + 25 del mismo comando = 110 sobre 100.

    Cada fila nueva cabe por separado; juntas no. Validarlas de una en una
    dejaria pasar exactamente este caso hasta el trigger.
    """
    hecho_id = porcion_de_cien["hecho_id"]
    conciliacion_id = porcion_de_cien["conciliacion_id"]
    previa = aportacion(
        "60.0000", actor_id=actor_a, hecho_movimiento_tesoreria_id=conciliacion_id
    )
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=hecho_id,
        hecho_row_version_esperada=porcion_de_cien["hecho_rv"],
        aportaciones=[previa],
    )

    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=hecho_id,
            hecho_row_version_esperada=creada.hecho_row_version,
            aportaciones=[
                aportacion(
                    "25.0000",
                    actor_id=actor_b,
                    hecho_movimiento_tesoreria_id=conciliacion_id,
                ),
                aportacion(
                    "25.0000", hecho_movimiento_tesoreria_id=conciliacion_id
                ),
            ],
        )
    assert excinfo.value.codigo is CodigoError.SUMA_EXCEDE_PORCION

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_movimiento_tesoreria_id = %s",
        (conciliacion_id,),
    )
    assert fila == (1, D("60.0000"))


def test_op06_con_vinculo_inicial_aplica_las_reglas_de_op07(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """F04-D012: un vinculo inicial explicito no esquiva la frontera de cobro."""
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
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.registrar_aportaciones(
            contexto,
            hecho_id=datos.hecho_id,
            hecho_row_version_esperada=conciliada.hecho_row_version,
            aportaciones=[
                aportacion(
                    "100.0000", hecho_movimiento_tesoreria_id=conciliacion_id
                )
            ],
        )
    assert excinfo.value.codigo is CodigoError.USO_EN_COBRO_NO_PERMITIDO


def test_sin_destino_no_se_deduce_cobro_desde_el_tipo_de_hecho(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una aportacion sin vinculo sobre un hecho INGRESO es valida.

    Deducir "cobro" del arquetipo mezclaria significado economico con
    tesoreria, que es justo lo que F04-D012 prohibe.
    """
    datos = datos_hecho(tipo_hecho_codigo="INGRESO")
    creado = servicio.crear_hecho(contexto, datos)
    una = aportacion("100.0000")
    resultado = servicio_tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=creado.row_version,
        aportaciones=[una],
    )
    assert resultado.aportaciones_creadas == 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_movimiento_tesoreria_id "
        "FROM gapto.hecho_aportaciones_pago WHERE id = %s",
        (una.aportacion_id,),
    )
    assert fila == (None,)
