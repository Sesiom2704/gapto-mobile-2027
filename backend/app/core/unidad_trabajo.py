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
# Version: 0.2.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70… y adenda 01 24113472… (perfil BETA_LOCAL,
#   AJ-R3-02); diseno v0.2 §3-§5 con AJ-R2-01/02/05):
#   DENTRO de una peticion HTTP (estado de `app.core.peticion`, creado por el middleware) cada intento:
#   - mide el restante del deadline UNICO de la peticion antes del intento y antes del backoff, y no empieza con
#     menos de 0,5 s (`PlazoAgotado`); el deadline nunca se reinicia;
#   - fija en la sesion, en autocommit (sin transaccion implicita), `transaction_timeout = restante + margen`, y
#     despues abre un BEGIN real; dentro, junto al contexto, `statement_timeout = restante` y `lock_timeout`
#     (3 s en A; 0 EXPLICITO en B);
#   - deja su estado en el seguimiento ACUMULADO de la peticion (SIN_ESCRITURA_POSIBLE / ESCRITURA_POSIBLE /
#     COMMIT_INICIADO / COMMIT_CONFIRMADO / COMMIT_INDETERMINADO / ROLLBACK_CONFIRMADO / ABORTADA_SIN_COMMIT), con
#     las duraciones de conexion, transaccion y COMMIT; el XID asignado se guarda solo como evidencia auxiliar;
#   - convierte en `PlazoAgotado` (fuera de ErrorMotor) solo un 57014 del statement_timeout propio (llega con el
#     deadline cumplido) o un 55P03 del lock_timeout propio (clase A). 57014 no se reintenta.
#   Un COMMIT confirmado no se rebaja nunca, ni por un error posterior (cierre de la conexion).
#   `solo_lectura=True` (de cualquier llamante) abre la transaccion en READ ONLY ANTES de cualquier consulta, incluida
#   la de contexto. Fuera de una peticion HTTP la unidad no cambia de comportamiento.
# ============================================================

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterator, TypeVar

import psycopg

from app.core import peticion as pet
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
        solo_lectura: bool = False,
    ) -> T:
        return self.ejecutar_con_traza(contexto, operacion, nombre=nombre, solo_lectura=solo_lectura).valor

    def ejecutar_con_traza(
        self,
        contexto: ContextoOperacion,
        operacion: Callable[[SesionMotor], T],
        *,
        nombre: str = "operacion",
        solo_lectura: bool = False,
    ) -> Resultado[T]:
        traza = Traza(operacion=nombre, request_id=contexto.request_id)
        peticion = pet.actual()
        registro: pet.RegistroUnidad | None = None
        if peticion is not None:
            registro = pet.RegistroUnidad(nombre=nombre, audit_request_id=str(contexto.request_id),
                                          solo_lectura=solo_lectura)
            peticion.unidades.append(registro)   # acumulado: nunca se borra lo de otra unidad

        for numero in range(1, self._max_intentos + 1):
            traza.intentos_realizados = numero
            intento: pet.RegistroIntento | None = None
            if peticion is not None:
                if peticion.restante() < pet.MINIMO_PARA_INTENTO_S:
                    raise pet.PlazoAgotado("SIN_PLAZO_PARA_INTENTO", unidad=nombre)
                intento = pet.RegistroIntento(
                    numero=numero, solo_lectura=solo_lectura,
                    estado=pet.EstadoUnidad.SIN_ESCRITURA_POSIBLE if solo_lectura else pet.EstadoUnidad.ESCRITURA_POSIBLE)
                registro.intentos.append(intento)
            t_intento = time.monotonic()
            t_commit = t_intento
            try:
                with self._proveedor() as conexion:
                    if peticion is not None:
                        intento.conexion_ms = _ms(t_intento)
                        _ajustar_sesion(conexion, peticion)
                    t_tx = time.monotonic()
                    with conexion.transaction():
                        if solo_lectura:
                            # Primera sentencia de la transaccion: PostgreSQL impide que escriba (AJ-R2-01).
                            conexion.execute("SET TRANSACTION READ ONLY")
                        self._fijar_contexto(conexion, contexto, peticion)
                        sesion = SesionMotor(conexion, contexto, numero)
                        valor = operacion(sesion)
                        if intento is not None:
                            intento.xid_auxiliar = conexion.execute(
                                "SELECT pg_current_xact_id_if_assigned() IS NOT NULL").fetchone()[0]
                            intento.transaccion_ms = _ms(t_tx)
                            if not solo_lectura:
                                intento.estado = pet.EstadoUnidad.COMMIT_INICIADO
                            t_commit = time.monotonic()
                    # Salir del bloque `transaction()` sin excepcion equivale a
                    # COMMIT confirmado, incluida la validacion de constraints
                    # diferidas de 0310.
                    if intento is not None:
                        intento.commit_ms = _ms(t_commit)
                        if not solo_lectura:
                            intento.estado = pet.EstadoUnidad.COMMIT_CONFIRMADO
                    return Resultado(valor=valor, traza=traza)
            except BaseException as exc:  # noqa: BLE001 - se reclasifica abajo
                reintentable = es_reintentable(exc)
                sqlstate = getattr(exc, "sqlstate", None)
                if intento is not None:
                    intento.sqlstate = sqlstate
                    if not solo_lectura:
                        intento.estado = _estado_tras_error(intento.estado, exc)
                    motivo = (None if intento.estado is pet.EstadoUnidad.COMMIT_CONFIRMADO
                              else _plazo_propio(exc, peticion))
                    if motivo is not None:
                        raise pet.PlazoAgotado(motivo, sqlstate=sqlstate, unidad=nombre) from exc
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
                        espera = self._espera_inicial_s * (2 ** (numero - 1))
                        if peticion is not None and peticion.restante() - espera < pet.MINIMO_PARA_INTENTO_S:
                            # El backoff consume el MISMO presupuesto: si tras esperar no quedaria plazo, no se espera.
                            raise pet.PlazoAgotado("SIN_PLAZO_PARA_INTENTO", sqlstate=sqlstate, unidad=nombre) from exc
                        time.sleep(espera)
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
        peticion: pet.EstadoPeticion | None = None,
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
            if peticion is not None:
                # AJ-05 (diseno §4.2): limites LOCALES de esta transaccion; revierten al terminar.
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true),"
                    "       set_config('lock_timeout',      %s, true)",
                    (f"{max(1, int(peticion.restante() * 1000))}ms", f"{peticion.lock_timeout_ms()}ms"),
                )


def _ms(desde: float) -> float:
    return round((time.monotonic() - desde) * 1000, 2)


def _ajustar_sesion(conexion: psycopg.Connection, peticion: pet.EstadoPeticion) -> None:
    """Diseno §4.1: ajuste de SESION sin transaccion implicita. En autocommit, `set_config(..., false)` no abre
    transaccion; despues `conexion.transaction()` emite un BEGIN real (no un savepoint). La conexion es de este
    intento y se cierra con el: el ajuste muere con ella."""
    conexion.autocommit = True
    ms = int((peticion.restante() + pet.MARGEN_TRANSACTION_TIMEOUT_S) * 1000)
    conexion.execute("SELECT set_config('transaction_timeout', %s, false)", (f"{max(1, ms)}ms",))


# SQLSTATE con los que el servidor corta la sesion: no prueban que la transaccion abortase antes del COMMIT.
_CORTE_DE_SESION = ("57P01", "57P02", "57P03", "57P04", "57P05", "25P04")


def _es_corte(exc: BaseException) -> bool:
    sqlstate = getattr(exc, "sqlstate", None)
    if isinstance(exc, psycopg.OperationalError) and sqlstate is None:
        return True    # conexion perdida sin respuesta del servidor
    return sqlstate is not None and (sqlstate.startswith("08") or sqlstate in _CORTE_DE_SESION)


def _estado_tras_error(previo: pet.EstadoUnidad, exc: BaseException) -> pet.EstadoUnidad:
    """AJ-R2-02. Durante el COMMIT: un corte deja el resultado INDETERMINADO; una respuesta de error del servidor
    (trigger diferido, 57014, 40P01...) prueba el aborto. Antes del COMMIT nunca puede haber confirmado.
    Un COMMIT ya confirmado NUNCA se rebaja (p. ej. un error al cerrar la conexion despues del COMMIT)."""
    if previo is pet.EstadoUnidad.COMMIT_CONFIRMADO:
        return previo
    if previo is pet.EstadoUnidad.COMMIT_INICIADO:
        return pet.EstadoUnidad.COMMIT_INDETERMINADO if _es_corte(exc) else pet.EstadoUnidad.ROLLBACK_CONFIRMADO
    return pet.EstadoUnidad.ABORTADA_SIN_COMMIT if _es_corte(exc) else pet.EstadoUnidad.ROLLBACK_CONFIRMADO


def _plazo_propio(exc: BaseException, peticion: pet.EstadoPeticion | None) -> str | None:
    """Diseno §5.4: 57014/55P03 son plazo SOLO si los provoco un limite que fijo la propia unidad.
    - 57014: la unidad fija statement_timeout = restante, asi que el suyo solo salta con el deadline cumplido; uno
      anterior (p. ej. una cancelacion externa) conserva el error original.
    - 55P03: solo con lock_timeout propio > 0 (clase A). En B es 0: un 55P03 no puede venir de su limite."""
    if peticion is None:
        return None
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate == "57014" and time.monotonic() >= peticion.deadline - pet.TOLERANCIA_DEADLINE_S:
        return "STATEMENT_TIMEOUT"
    if sqlstate == "55P03" and peticion.lock_timeout_ms() > 0:
        return "LOCK_TIMEOUT"
    return None


@contextmanager
def conexion_directa(dsn: str) -> Iterator[psycopg.Connection]:
    """Proveedor minimo: una conexion nueva por intento.

    Suficiente para tests y para un backend sin pool. Cuando F10 introduzca
    pool, basta sustituir el proveedor: la unidad de trabajo no cambia.
    """
    with psycopg.connect(dsn) as conexion:
        yield conexion
