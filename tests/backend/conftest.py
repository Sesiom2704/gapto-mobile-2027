# ============================================================
# GAPTO MOBILE 2027
# Fichero: conftest.py
# Ruta: tests/backend/conftest.py
# Descripcion: Fixtures de los tests del motor financiero (F04-01).
#
#   Dos decisiones que evitan falsos verdes:
#
#   1) El rol de conexion NUNCA ejecuta el dominio. La unidad de trabajo hace
#      `SET LOCAL ROLE gapto_runtime` dentro de cada transaccion, de modo que
#      lo que se prueba es el contrato que realmente tendra produccion, con RLS
#      y FORCE RLS aplicando. Un test que corriese como superusuario pasaria
#      aunque el aislamiento tenant estuviese roto (Working Method 12C.7).
#
#   2) Los datos de fixture se crean bajo `SET ROLE gapto_owner` y con la GUC
#      de tenant ya fijada, porque `usuarios` tiene policy sobre su propio id:
#      sin contexto no se puede ni crear el usuario.
#
#   Los tests exigen GAPTO_TEST_DATABASE_URL. No se apunta implicitamente a
#   ninguna base: una suite que se autoconfigura acaba escribiendo donde no
#   debe.
# Version: 0.3.0
#   0.3.0 (F04-03): fixtures de cuentas y del servicio de tesoreria. `cuenta_usd`
#   existe para probar multidivisa: D-169 solo compara cuando la moneda del
#   hecho coincide con la de la cuenta, y sin una cuenta en otra divisa esa
#   rama no se ejercita nunca.
# Version: 0.2.0
#   0.2.0 (F04-02): fixtures de actores y del servicio de efectos. El segundo
#   actor se crea con tercero porque
#   `uq_actores_financieros__owner_tercero UNIQUE NULLS NOT DISTINCT` solo
#   admite UN actor con tercero NULL por owner: el self.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import os
import pathlib
import sys
import uuid
from contextlib import contextmanager
from typing import Iterator

import psycopg
import pytest

_RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
if str(_RAIZ_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RAIZ_BACKEND))

from app.core.contexto import ContextoOperacion  # noqa: E402
from app.core.unidad_trabajo import UnidadDeTrabajo  # noqa: E402
from app.services.efectos_service import EfectosService  # noqa: E402
from app.services.hechos_service import HechosService  # noqa: E402
from app.services.tesoreria_service import TesoreriaService  # noqa: E402

ROL_RUNTIME = "gapto_runtime"


@pytest.fixture(scope="session")
def dsn() -> str:
    valor = os.getenv("GAPTO_TEST_DATABASE_URL")
    if not valor:
        pytest.fail(
            "Falta GAPTO_TEST_DATABASE_URL; los tests del motor nunca deben "
            "apuntarse implicitamente a una base no identificada."
        )
    return valor


@pytest.fixture(scope="session")
def proveedor_conexion(dsn: str):
    @contextmanager
    def _abrir() -> Iterator[psycopg.Connection]:
        with psycopg.connect(dsn) as conexion:
            yield conexion

    return _abrir


@pytest.fixture()
def unidad(proveedor_conexion) -> UnidadDeTrabajo:
    return UnidadDeTrabajo(
        proveedor_conexion,
        rol_runtime=ROL_RUNTIME,
        max_intentos=3,
        espera_inicial_s=0.001,
    )


@pytest.fixture()
def servicio(unidad: UnidadDeTrabajo) -> HechosService:
    return HechosService(unidad)


@pytest.fixture(scope="session")
def admin(dsn: str) -> Iterator[psycopg.Connection]:
    """Conexion administrativa solo para montar fixtures y verificar."""
    with psycopg.connect(dsn, autocommit=True) as conexion:
        yield conexion


def _crear_usuario(admin: psycopg.Connection, owner: uuid.UUID) -> None:
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            cursor.execute(
                "INSERT INTO gapto.usuarios (id, email, nombre) "
                "VALUES (%s, %s, 'F04-01') ON CONFLICT DO NOTHING",
                (owner, f"{uuid.uuid4()}@example.invalid"),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


@pytest.fixture()
def owner(admin: psycopg.Connection) -> uuid.UUID:
    identificador = uuid.uuid4()
    _crear_usuario(admin, identificador)
    return identificador


@pytest.fixture()
def otro_owner(admin: psycopg.Connection) -> uuid.UUID:
    identificador = uuid.uuid4()
    _crear_usuario(admin, identificador)
    return identificador


@pytest.fixture()
def contexto(owner: uuid.UUID) -> ContextoOperacion:
    return ContextoOperacion.de_usuario(owner)


@pytest.fixture(scope="session")
def localidad(admin: psycopg.Connection) -> uuid.UUID:
    """Una localidad del catalogo global, creada si la base esta vacia.

    Los catalogos geograficos no tienen RLS: se crean bajo gapto_owner y se
    comparten entre tenants, que es justamente su contrato.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute("SELECT id FROM gapto.localidades LIMIT 1")
            fila = cursor.fetchone()
            if fila is not None:
                return fila[0]

            # El codigo ISO se elige libre en tiempo de ejecucion: fijarlo a
            # 'ZZ' colisionaba con test_013, que crea y espera ausente ese
            # mismo codigo. Un fixture no debe dejar residuo que rompa otra
            # suite.
            cursor.execute(
                "SELECT c FROM (SELECT chr(88 + i) || chr(65 + j) AS c "
                "FROM generate_series(0, 1) i, generate_series(0, 25) j) cand "
                "WHERE NOT EXISTS (SELECT 1 FROM gapto.paises p WHERE p.iso2 = cand.c) "
                "LIMIT 1"
            )
            iso2 = cursor.fetchone()[0]

            pais_id = uuid.uuid4()
            region_id = uuid.uuid4()
            localidad_id = uuid.uuid4()
            cursor.execute(
                "INSERT INTO gapto.paises (id, iso2, iso3, nombre) "
                "VALUES (%s, %s, %s, 'Pais de pruebas F04-01')",
                (pais_id, iso2, iso2 + "X"),
            )
            cursor.execute(
                "INSERT INTO gapto.regiones (id, pais_id, nombre) "
                "VALUES (%s, %s, 'Region de pruebas')",
                (region_id, pais_id),
            )
            cursor.execute(
                "INSERT INTO gapto.localidades (id, region_id, nombre) "
                "VALUES (%s, %s, 'Localidad de pruebas')",
                (localidad_id, region_id),
            )
            return localidad_id
        finally:
            cursor.execute("RESET ROLE")


def leer_fila(admin: psycopg.Connection, owner: uuid.UUID, sql: str, params: tuple):
    """Lectura de verificacion con contexto de tenant y limpieza posterior."""
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
        )
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        finally:
            cursor.execute("RESET ALL")


@pytest.fixture()
def servicio_efectos(unidad: UnidadDeTrabajo) -> EfectosService:
    return EfectosService(unidad)


def _crear_actor(
    admin: psycopg.Connection, owner: uuid.UUID, con_tercero: bool
) -> uuid.UUID:
    actor_id = uuid.uuid4()
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            if con_tercero:
                tercero_id = uuid.uuid4()
                cursor.execute(
                    "INSERT INTO gapto.terceros (id, owner_user_id, nombre) "
                    "VALUES (%s, %s, 'Tercero F04-02')",
                    (tercero_id, owner),
                )
                cursor.execute(
                    "INSERT INTO gapto.actores_financieros "
                    "(id, owner_user_id, tercero_id) VALUES (%s, %s, %s)",
                    (actor_id, owner, tercero_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO gapto.actores_financieros (id, owner_user_id) "
                    "VALUES (%s, %s)",
                    (actor_id, owner),
                )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")
    return actor_id


@pytest.fixture()
def actor_a(admin: psycopg.Connection, owner: uuid.UUID) -> uuid.UUID:
    """Actor self del tenant (tercero_id NULL)."""
    return _crear_actor(admin, owner, con_tercero=False)


@pytest.fixture()
def actor_b(admin: psycopg.Connection, owner: uuid.UUID) -> uuid.UUID:
    """Segundo actor, necesariamente con tercero."""
    return _crear_actor(admin, owner, con_tercero=True)


@pytest.fixture()
def actor_ajeno(admin: psycopg.Connection, otro_owner: uuid.UUID) -> uuid.UUID:
    """Actor de OTRO tenant, para probar que no hay fuga."""
    return _crear_actor(admin, otro_owner, con_tercero=False)


@pytest.fixture()
def servicio_tesoreria(unidad: UnidadDeTrabajo) -> TesoreriaService:
    return TesoreriaService(unidad)


def _crear_cuenta(
    admin: psycopg.Connection, owner: uuid.UUID, moneda: str = "EUR"
) -> uuid.UUID:
    cuenta_id = uuid.uuid4()
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            cursor.execute(
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, "
                "naturaleza, moneda, computa_liquidez, computa_patrimonio, "
                "permite_negativo) VALUES (%s, %s, %s, 'CORRIENTE', 'ACTIVO', %s, "
                "true, true, false)",
                (cuenta_id, owner, f"Cuenta {moneda} F04-03", moneda),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")
    return cuenta_id


@pytest.fixture()
def cuenta(admin: psycopg.Connection, owner: uuid.UUID) -> uuid.UUID:
    return _crear_cuenta(admin, owner, "EUR")


@pytest.fixture()
def cuenta_usd(admin: psycopg.Connection, owner: uuid.UUID) -> uuid.UUID:
    """Cuenta en otra divisa: D-169 no compara nominalmente contra ella."""
    return _crear_cuenta(admin, owner, "USD")


@pytest.fixture()
def cuenta_ajena(admin: psycopg.Connection, otro_owner: uuid.UUID) -> uuid.UUID:
    return _crear_cuenta(admin, otro_owner, "EUR")


def anular_movimiento(
    admin: psycopg.Connection, owner: uuid.UUID, movimiento_id: uuid.UUID
) -> None:
    """Anula un movimiento para montar escenarios.

    F04-03 no implementa la anulacion de movimientos —pertenece a F04-06— asi
    que el estado se monta desde el fixture, no inventando una operacion.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            cursor.execute(
                "UPDATE gapto.movimientos_tesoreria SET estado = 'ANULADO', "
                "anulado_at = CURRENT_TIMESTAMP, row_version = row_version + 1 "
                "WHERE id = %s",
                (movimiento_id,),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")
