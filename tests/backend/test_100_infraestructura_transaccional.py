# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_100_infraestructura_transaccional.py
# Ruta: tests/backend/test_100_infraestructura_transaccional.py
# Descripcion: F04-01. Unidad de trabajo: transaccion unica, contexto tenant
#   dentro de la transaccion y retry de la TRANSACCION COMPLETA ante 40P01 y
#   40001 (D-171).
#
#   El error transitorio se provoca con un RAISE real de PostgreSQL con
#   ERRCODE 40P01 / 40001, no con una excepcion de Python fabricada. La
#   diferencia es esencial: un RAISE real ABORTA la transaccion en el servidor,
#   de modo que si el wrapper intentase continuar sobre ella todo fallaria con
#   InFailedSqlTransaction. Que el segundo intento funcione demuestra que se
#   reconstruye la transaccion desde cero y no se reutiliza la abortada.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo
from conftest import ROL_RUNTIME, leer_fila

SQL_DEADLOCK = "DO $$ BEGIN RAISE EXCEPTION 'deadlock simulado' USING ERRCODE = '40P01'; END $$"
SQL_SERIALIZACION = (
    "DO $$ BEGIN RAISE EXCEPTION 'serializacion simulada' "
    "USING ERRCODE = '40001'; END $$"
)


def _datos(hecho_id: uuid.UUID) -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=hecho_id,
        fecha_hecho=dt.date(2026, 3, 1),
        moneda="EUR",
        presupuestable=True,
        estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="GASTO",
        concepto="retry",
    )


def _operacion_que_falla_una_vez(hecho_id: uuid.UUID, sql_error: str, estado: dict):
    """Crea el hecho y, en el primer intento, aborta con un error transitorio."""

    def operacion(sesion: SesionMotor) -> int:
        estado["intentos"] = estado.get("intentos", 0) + 1
        tipo_id = repo.resolver_tipo_hecho(
            sesion, codigo="GASTO", tipo_hecho_id=None
        )
        creado = repo.insertar_si_no_existe(sesion, _datos(hecho_id), tipo_id)
        assert creado is not None
        auditoria.registrar(
            sesion,
            tabla=repo.TABLA,
            registro_id=hecho_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=creado[2],
        )
        if estado["intentos"] == 1:
            sesion.ejecutar(sql_error)
        return creado[0]

    return operacion


@pytest.mark.parametrize(
    "sql_error, sqlstate", [(SQL_DEADLOCK, "40P01"), (SQL_SERIALIZACION, "40001")]
)
def test_retry_reconstruye_la_transaccion_completa(
    unidad: UnidadDeTrabajo,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    sql_error: str,
    sqlstate: str,
) -> None:
    hecho_id = uuid.uuid4()
    estado: dict = {}

    resultado = unidad.ejecutar_con_traza(
        contexto,
        _operacion_que_falla_una_vez(hecho_id, sql_error, estado),
        nombre="prueba-retry",
    )

    assert estado["intentos"] == 2
    assert resultado.traza.intentos_realizados == 2
    assert resultado.traza.hubo_retry is True
    assert [f.sqlstate for f in resultado.traza.fallidos] == [sqlstate]

    # Lo escrito en el intento abortado NO sobrevive: hay exactamente un hecho
    # y exactamente una auditoria de creacion.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(row_version) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (1, 1)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s AND accion = 'CREAR'",
        (hecho_id,),
    )
    assert fila == (1,)


def test_el_uuid_reservado_se_conserva_entre_intentos(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    hecho_id = uuid.uuid4()
    vistos: list[uuid.UUID] = []

    def operacion(sesion: SesionMotor) -> None:
        vistos.append(hecho_id)
        tipo_id = repo.resolver_tipo_hecho(sesion, codigo="GASTO", tipo_hecho_id=None)
        repo.insertar_si_no_existe(sesion, _datos(hecho_id), tipo_id)
        if len(vistos) == 1:
            sesion.ejecutar(SQL_DEADLOCK)

    unidad.ejecutar(contexto, operacion, nombre="prueba-uuid")

    assert vistos == [hecho_id, hecho_id]
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (1,)


def test_agotamiento_controlado_de_reintentos(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion
) -> None:
    intentos: list[int] = []

    def operacion(sesion: SesionMotor) -> None:
        intentos.append(sesion.intento)
        sesion.ejecutar(SQL_DEADLOCK)

    with pytest.raises(ErrorMotor) as excinfo:
        unidad.ejecutar(contexto, operacion, nombre="prueba-agotamiento")

    assert excinfo.value.codigo is CodigoError.CONFLICTO_CONCURRENCIA
    assert intentos == [1, 2, 3]
    assert unidad.max_intentos == 3


def test_un_error_no_reintentable_no_se_reintenta(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion
) -> None:
    intentos: list[int] = []

    def operacion(sesion: SesionMotor) -> None:
        intentos.append(sesion.intento)
        sesion.ejecutar(
            "DO $$ BEGIN RAISE EXCEPTION 'invariante' USING ERRCODE = 'P0001'; END $$"
        )

    with pytest.raises(ErrorMotor) as excinfo:
        unidad.ejecutar(contexto, operacion, nombre="prueba-no-reintentable")

    assert excinfo.value.codigo is CodigoError.VIOLACION_INVARIANTE_FISICA
    assert intentos == [1]


def test_el_contexto_es_local_a_la_transaccion(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, dsn: str
) -> None:
    """La GUC no debe sobrevivir a la transaccion ni al rol de conexion."""
    valores: dict = {}

    def operacion(sesion: SesionMotor) -> None:
        fila = sesion.uno(
            "SELECT current_setting('gapto.owner_user_id', true), current_user"
        )
        valores["dentro"] = fila

    unidad.ejecutar(contexto, operacion, nombre="prueba-contexto")

    assert valores["dentro"][0] == str(contexto.owner_user_id)
    assert valores["dentro"][1] == ROL_RUNTIME

    with psycopg.connect(dsn) as conexion, conexion.cursor() as cursor:
        cursor.execute("SELECT current_setting('gapto.owner_user_id', true)")
        assert cursor.fetchone()[0] in (None, "")


def test_sin_contexto_tenant_falla_cerrado(dsn: str) -> None:
    """Sin GUC de tenant, el write-path se niega antes de tocar datos."""
    with psycopg.connect(dsn) as conexion:
        with conexion.transaction():
            with conexion.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {ROL_RUNTIME}")
            sesion = SesionMotor(conexion, None, 1)  # type: ignore[arg-type]
            with pytest.raises(ErrorMotor) as excinfo:
                repo.exigir_contexto(sesion)
    assert excinfo.value.codigo is CodigoError.TENANT_AUSENTE


def test_auditoria_sin_contexto_se_traduce_a_tenant_ausente(dsn: str) -> None:
    """28000 de fn_registrar_auditoria no se filtra como error tecnico."""
    from app.core.clasificacion_errores import traducir

    with psycopg.connect(dsn) as conexion:
        with pytest.raises(psycopg.Error) as excinfo:
            with conexion.transaction():
                with conexion.cursor() as cursor:
                    cursor.execute(f"SET LOCAL ROLE {ROL_RUNTIME}")
                    cursor.execute(
                        "SELECT gapto.fn_registrar_auditoria("
                        "'hechos_financieros', %s::uuid, 'CREAR', NULL, NULL, NULL)",
                        (uuid.uuid4(),),
                    )

    error = traducir(excinfo.value)
    assert error.codigo is CodigoError.TENANT_AUSENTE
    assert error.sqlstate == "28000"
