# ============================================================
# GAPTO MOBILE 2027
# Fichero: unidad_trabajo.py
# Ruta: backend/app/core/unidad_trabajo.py
# Descripcion: Unidad transaccional comun del motor financiero.
#
#   Garantiza, para cada operacion de dominio:
#     1) UNA sola transaccion PostgreSQL bajo READ COMMITTED;
#     2) contexto tenant/actor/request fijado DENTRO de esa transaccion
#        mediante `SET LOCAL` / `set_config(..., true)`, nunca a nivel de
#        sesion (una GUC de sesion sobreviviria a la transaccion y podria
#        contaminar la siguiente operacion del mismo backend);
#     3) retry de la TRANSACCION COMPLETA ante 40P01 y 40001 (D-171);
#     4) limite explicito de intentos y traza de cada intento.
#
#   Por que el retry envuelve tambien al COMMIT: 0310 instala constraint
#   triggers DEFERRABLE INITIALLY DEFERRED. Su validacion ocurre al confirmar,
#   de modo que un deadlock puede materializarse en el COMMIT y no en el DML.
#   Un wrapper que solo protegiese el cuerpo dejaria ese caso sin cubrir.
#
#   Cada intento reconstruye la transaccion DESDE EL PRINCIPIO sobre una
#   transaccion nueva. Nunca se reutiliza una transaccion abortada ni se
#   continua desde la mitad de una operacion. La identidad (UUID reservado) la
#   aporta el llamante y NO se regenera entre intentos: esa es la pieza que
#   hace seguro el reintento de un alta.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterator, TypeVar

import psycopg

from app.core.clasificacion_errores import es_reintentable, traducir
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor

T = TypeVar("T")

_LOG = logging.getLogger("gapto.motor.transaccion")

MAX_INTENTOS_POR_DEFECTO = 3
ESPERA_INICIAL_POR_DEFECTO_S = 0.01


@dataclass(frozen=True, slots=True)
class IntentoFallido:
    """Registro de un intento que no llego a confirmar."""

    numero: int
    sqlstate: str | None
    resumen: str


@dataclass(slots=True)
class Traza:
    """Trazabilidad de una operacion transaccional."""

    operacion: str
    request_id: uuid.UUID
    intentos_realizados: int = 0
    fallidos: list[IntentoFallido] = field(default_factory=list)

    @property
    def hubo_retry(self) -> bool:
        return self.intentos_realizados > 1


@dataclass(frozen=True, slots=True)
class Resultado(Generic[T]):
    valor: T
    traza: Traza


class SesionMotor:
    """Acceso a la conexion dentro de una transaccion ya contextualizada."""

    __slots__ = ("conexion", "contexto", "intento")

    def __init__(
        self,
        conexion: psycopg.Connection,
        contexto: ContextoOperacion,
        intento: int,
    ) -> None:
        self.conexion = conexion
        self.contexto = contexto
        self.intento = intento

    def uno(self, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def ejecutar(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount


class UnidadDeTrabajo:
    """Ejecuta una operacion de dominio como transaccion unica y reintentable.

    `proveedor_conexion` devuelve un gestor de contexto con una conexion lista.
    Se pide una conexion por INTENTO: asi una conexion que quedase en estado
    dudoso no se arrastra al siguiente intento.

    `rol_runtime` permite fijar `SET LOCAL ROLE` cuando el rol de conexion no
    es ya `gapto_runtime` (laboratorio y tests). En produccion la conexion
    llega como `gapto_runtime` y no hace falta. No introduce bifurcacion de SQL
    por proveedor: el SQL de dominio es identico en Neon y Supabase.
    """

    __slots__ = ("_proveedor", "_rol_runtime", "_max_intentos", "_espera_inicial_s")

    def __init__(
        self,
        proveedor_conexion: Callable[[], Any],
        *,
        rol_runtime: str | None = None,
        max_intentos: int = MAX_INTENTOS_POR_DEFECTO,
        espera_inicial_s: float = ESPERA_INICIAL_POR_DEFECTO_S,
    ) -> None:
        if max_intentos < 1:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "max_intentos debe ser al menos 1.",
            )
        self._proveedor = proveedor_conexion
        self._rol_runtime = rol_runtime
        self._max_intentos = max_intentos
        self._espera_inicial_s = espera_inicial_s

    @property
    def max_intentos(self) -> int:
        return self._max_intentos

    def ejecutar(
        self,
        contexto: ContextoOperacion,
        operacion: Callable[[SesionMotor], T],
        *,
        nombre: str = "operacion",
    ) -> T:
        return self.ejecutar_con_traza(contexto, operacion, nombre=nombre).valor

    def ejecutar_con_traza(
        self,
        contexto: ContextoOperacion,
        operacion: Callable[[SesionMotor], T],
        *,
        nombre: str = "operacion",
    ) -> Resultado[T]:
        traza = Traza(operacion=nombre, request_id=contexto.request_id)

        for numero in range(1, self._max_intentos + 1):
            traza.intentos_realizados = numero
            try:
                with self._proveedor() as conexion:
                    with conexion.transaction():
                        self._fijar_contexto(conexion, contexto)
                        sesion = SesionMotor(conexion, contexto, numero)
                        valor = operacion(sesion)
                    # Salir del bloque `transaction()` sin excepcion equivale a
                    # COMMIT confirmado, incluida la validacion de constraints
                    # diferidas de 0310.
                    return Resultado(valor=valor, traza=traza)
            except BaseException as exc:  # noqa: BLE001 - se reclasifica abajo
                reintentable = es_reintentable(exc)
                sqlstate = getattr(exc, "sqlstate", None)
                if reintentable:
                    traza.fallidos.append(
                        IntentoFallido(
                            numero=numero,
                            sqlstate=sqlstate,
                            resumen=type(exc).__name__,
                        )
                    )
                    _LOG.warning(
                        "retry de transaccion completa",
                        extra={
                            "operacion": nombre,
                            "request_id": str(contexto.request_id),
                            "intento": numero,
                            "max_intentos": self._max_intentos,
                            "sqlstate": sqlstate,
                        },
                    )
                    if numero < self._max_intentos:
                        time.sleep(self._espera_inicial_s * (2 ** (numero - 1)))
                        continue
                    raise ErrorMotor(
                        CodigoError.CONFLICTO_CONCURRENCIA,
                        "Se agoto el limite de reintentos por concurrencia; "
                        "nada se ha persistido.",
                        causa=exc,
                        sqlstate=sqlstate,
                        contexto_extra={
                            "operacion": nombre,
                            "intentos": numero,
                        },
                    ) from exc
                raise traducir(exc) from exc

        # Inalcanzable: el bucle siempre retorna o lanza.
        raise ErrorMotor(  # pragma: no cover
            CodigoError.INTERNO,
            "El wrapper transaccional termino sin resultado ni error.",
        )

    def _fijar_contexto(
        self,
        conexion: psycopg.Connection,
        contexto: ContextoOperacion,
    ) -> None:
        """Fija rol y GUC dentro de la transaccion en curso.

        `set_config(..., true)` es equivalente a SET LOCAL y revierte al
        terminar la transaccion, confirme o no. Se usa `set_config` en vez de
        `SET LOCAL` porque SET no admite parametros vinculados y concatenar el
        valor seria inyeccion.
        """
        with conexion.cursor() as cursor:
            if self._rol_runtime is not None:
                cursor.execute(f"SET LOCAL ROLE {self._rol_runtime}")
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, true),"
                "       set_config('gapto.actor_tipo',    %s, true),"
                "       set_config('gapto.actor_user_id', %s, true),"
                "       set_config('gapto.request_id',    %s, true)",
                (
                    str(contexto.owner_user_id),
                    contexto.actor_tipo,
                    "" if contexto.actor_user_id is None else str(contexto.actor_user_id),
                    str(contexto.request_id),
                ),
            )


@contextmanager
def conexion_directa(dsn: str) -> Iterator[psycopg.Connection]:
    """Proveedor minimo: una conexion nueva por intento.

    Suficiente para tests y para un backend sin pool. Cuando F10 introduzca
    pool, basta sustituir el proveedor: la unidad de trabajo no cambia.
    """
    with psycopg.connect(dsn) as conexion:
        yield conexion
