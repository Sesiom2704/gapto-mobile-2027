# ============================================================
# GAPTO MOBILE 2027
# Fichero: clasificacion_errores.py
# Ruta: backend/app/core/clasificacion_errores.py
# Descripcion: Traduccion de la causa tecnica PostgreSQL al error funcional del
#   motor, y clasificacion de lo que es reintentable.
#
#   Se construye sobre el inventario REAL del esquema 0001..0310, no sobre
#   supuestos: las unicas excepciones que el esquema levanta explicitamente con
#   ERRCODE propio son 28000 (contexto/tenant ausente o incoherente) y 22023
#   (parametro invalido para fn_registrar_auditoria). El resto de fallos llegan
#   como errores nativos: CheckViolation, ForeignKeyViolation, RaiseException
#   de los triggers de invariante, InsufficientPrivilege de RLS, etc.
#
#   Distincion deliberada:
#     - CheckViolation / ForeignKeyViolation / NotNullViolation nacen de datos
#       de entrada que no cumplen el contrato declarativo -> VIOLACION_INVARIANTE_FISICA.
#     - RaiseException (P0001) proviene de los triggers de invariante del
#       dominio -> VIOLACION_INVARIANTE_FISICA igualmente, pero conservando la
#       causa para distinguirlas en log.
#     - 42501 incluye tanto falta de GRANT como violacion de policy RLS. No se
#       intenta adivinar cual: ambas son fallo cerrado de autorizacion.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
from psycopg import errors as pgerr

from app.core.errores import CodigoError, ErrorMotor

# Deadlock y fallo de serializacion. Ambos exigen repetir la TRANSACCION
# COMPLETA (D-171). 40001 se trata igual que 40P01 por mandato F04-01.
SQLSTATES_REINTENTABLES: frozenset[str] = frozenset({"40P01", "40001"})

# Contexto de tenant/actor ausente o incoherente. Lo levanta
# gapto.fn_registrar_auditoria y cualquier cast fallido de la GUC.
SQLSTATE_CONTEXTO_INVALIDO = "28000"


def es_reintentable(exc: BaseException) -> bool:
    """True solo para deadlock y fallo de serializacion.

    No se amplia a errores de conexion: un fallo de red puede haber dejado la
    transaccion COMMITEADA en el servidor, y reintentarla a ciegas duplicaria
    realidad. El reintento seguro tras corte de conexion depende de la
    identidad UUID reservada (idempotencia de OP-01), no de esta funcion.
    """
    sqlstate = getattr(exc, "sqlstate", None)
    return sqlstate in SQLSTATES_REINTENTABLES


def traducir(exc: BaseException) -> ErrorMotor:
    """Convierte una excepcion tecnica en el error funcional equivalente."""
    if isinstance(exc, ErrorMotor):
        return exc

    sqlstate = getattr(exc, "sqlstate", None)

    if sqlstate in SQLSTATES_REINTENTABLES:
        return ErrorMotor(
            CodigoError.CONFLICTO_CONCURRENCIA,
            "La operacion no pudo completarse por concurrencia; nada se ha persistido.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if sqlstate == SQLSTATE_CONTEXTO_INVALIDO:
        return ErrorMotor(
            CodigoError.TENANT_AUSENTE,
            "La operacion se ejecuto sin contexto de tenant/actor valido.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if isinstance(exc, pgerr.InsufficientPrivilege):
        return ErrorMotor(
            CodigoError.TENANT_AUSENTE,
            "La operacion no esta autorizada en este contexto.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if isinstance(
        exc,
        (
            pgerr.CheckViolation,
            pgerr.ForeignKeyViolation,
            pgerr.NotNullViolation,
            pgerr.UniqueViolation,
            pgerr.ExclusionViolation,
            pgerr.RaiseException,
            pgerr.IntegrityError,
        ),
    ):
        return ErrorMotor(
            CodigoError.VIOLACION_INVARIANTE_FISICA,
            "La operacion viola una invariante del contrato de datos.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if isinstance(exc, (pgerr.InvalidTextRepresentation, pgerr.DataError)):
        return ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "Algun valor de entrada no tiene el tipo o formato esperado.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if isinstance(exc, psycopg.OperationalError):
        return ErrorMotor(
            CodigoError.BD_NO_DISPONIBLE,
            "La base de datos no esta disponible en este momento.",
            causa=exc,
            sqlstate=sqlstate,
        )

    if isinstance(exc, psycopg.Error):
        return ErrorMotor(
            CodigoError.INTERNO,
            "Error interno al ejecutar la operacion.",
            causa=exc,
            sqlstate=sqlstate,
        )

    return ErrorMotor(
        CodigoError.INTERNO,
        "Error interno no clasificado al ejecutar la operacion.",
        causa=exc,
    )
