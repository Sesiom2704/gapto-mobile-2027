# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/afinidades/servicio.py
# Descripcion: Writer de afinidades explicitas tercero -> categoria
#   (F05 §49.4 A5, §49.5 R9 con la excepcion acotada de R16, AJ-F0505-02;
#   casos 10, 11 y 31 de §49.9). UNA afinidad = UNA transaccion: «Guardar»
#   varias son varias llamadas (R9 prohibe varias categorias por transaccion:
#   40P01 real frente a desactivar una rama, K1-PRE P4).
#
#   Orden de locks OBLIGATORIO (R9), identico en alta y baja:
#     advisory (TERCEROS, owner)            -- primera llamada (C2)
#     -> terceros FOR NO KEY UPDATE         -- relee owner y enabled
#     -> [savepoint] incremento de row_version y updated_at del tercero
#        (solo esas dos columnas: ningun campo de negocio cambia)
#     -> UNA categorias_financieras FOR SHARE (relee owner, enabled, ambito;
#        nunca FOR NO KEY UPDATE)
#     -> INSERT / DELETE en tercero_afinidades
#     -> fn_registrar_auditoria
#   El savepoint hace que un rechazo deshaga tambien el incremento de
#   row_version: nada se escribe si la afinidad no se escribe.
#   El registro no lee afinidades ni toma (TERCEROS, owner): su orden
#   (F05-D032 C2) no cambia. Reintento completo ante 40P01: la UdT.
#
#   Respuestas:
#   - alta con un `afinidad_id` (UUID del cliente) ya usado: mismo par ->
#     idempotente; otro par -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#   - 23505 de la UNIQUE (tercero_id, categoria_id): SOLO ese caso es
#     idempotente, con el id existente y el aviso AFINIDAD_YA_EXISTE (el par
#     es del mismo owner: el tercero ya esta bloqueado y es visible).
#   - 42501 (RLS: categoria de otro owner o inexistente) ->
#     REFERENCIA_NO_DISPONIBLE con el sqlstate en el detalle y en el log;
#     nunca se enmascara como otra causa.
#   - tercero no visible o deshabilitado -> TERCERO_NO_ELEGIBLE; categoria
#     visible pero deshabilitada -> CATEGORIA_NO_ELEGIBLE.
#   - baja de una afinidad que no existe (o de otro owner, invisible) ->
#     idempotente, sin escritura.
# Version: 0.1.0 (F05-05 K2 §1.3)
# ============================================================

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg

from app.afinidades import repositorio as repo
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria
from app.terceros import repositorio as repo_ter

_LOG = logging.getLogger("gapto.f05_05.afinidades")

TABLA = "tercero_afinidades"
ACCION_ELIMINAR = "ELIMINAR"
MOTIVOS = {"ALTA": "F05-05 AFINIDAD ALTA", "BAJA": "F05-05 AFINIDAD BAJA"}

TERCERO_NO_ELEGIBLE = "TERCERO_NO_ELEGIBLE"
CATEGORIA_NO_ELEGIBLE = "CATEGORIA_NO_ELEGIBLE"
AFINIDAD_YA_EXISTE = "AFINIDAD_YA_EXISTE"
REFERENCIA_NO_DISPONIBLE = "REFERENCIA_NO_DISPONIBLE"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"

_UNIQUE_PAR = "uq_tercero_afinidades__tercero_categoria"
_PK = "pk_tercero_afinidades"


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    afinidad: dict[str, Any] | None
    idempotente: bool = False
    aviso: str | None = None


class _Abortar(Exception):
    def __init__(self, rechazo: Rechazo):
        self.rechazo = rechazo


def _tercero_bloqueado(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any] | None:
    return repo_ter.leer(sesion, tercero_id, bloquear=True)


def alta(sesion: SesionMotor, *, afinidad_id: uuid.UUID, tercero_id: uuid.UUID,
         categoria_id: uuid.UUID) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    tercero = _tercero_bloqueado(sesion, tercero_id)
    if tercero is None or not tercero["enabled"]:
        return Rechazo(TERCERO_NO_ELEGIBLE)
    previa = repo.leer(sesion, afinidad_id)
    if previa is not None:
        if previa["tercero_id"] == tercero_id and previa["categoria_id"] == categoria_id:
            return Resultado(afinidad=previa, idempotente=True)
        return Rechazo(IDENTIDAD_REUTILIZADA)
    conexion = sesion.conexion
    try:
        with conexion.transaction():  # savepoint: un rechazo deshace tambien row_version
            repo_ter.incrementar_version(sesion, tercero_id)
            categoria = repo.leer_categoria_compartida(sesion, categoria_id)
            if categoria is not None and not categoria["enabled"]:
                raise _Abortar(Rechazo(CATEGORIA_NO_ELEGIBLE))
            repo.insertar_afinidad(sesion, afinidad_id=afinidad_id, tercero_id=tercero_id, categoria_id=categoria_id)
    except _Abortar as abortado:
        return abortado.rechazo
    except psycopg.Error as exc:
        if exc.sqlstate == "23505" and exc.diag.constraint_name == _UNIQUE_PAR:
            existente = repo.leer_par(sesion, tercero_id, categoria_id)
            if existente is not None:
                return Resultado(afinidad=existente, idempotente=True, aviso=AFINIDAD_YA_EXISTE)
            raise
        if exc.sqlstate == "23505" and exc.diag.constraint_name == _PK:
            return Rechazo(IDENTIDAD_REUTILIZADA)
        if exc.sqlstate == "42501":
            _LOG.warning("afinidad rechazada por RLS", extra={"sqlstate": exc.sqlstate, "tabla": TABLA})
            return Rechazo(REFERENCIA_NO_DISPONIBLE, {"sqlstate": exc.sqlstate})
        raise
    auditoria.registrar(sesion, tabla=TABLA, registro_id=afinidad_id, accion=auditoria.ACCION_CREAR,
                        datos_despues_json=repo.snapshot(sesion, afinidad_id), motivo=MOTIVOS["ALTA"])
    return Resultado(afinidad=repo.leer(sesion, afinidad_id))


def baja(sesion: SesionMotor, *, afinidad_id: uuid.UUID) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    previa = repo.leer(sesion, afinidad_id)
    if previa is None:
        return Resultado(afinidad=None, idempotente=True)
    tercero = _tercero_bloqueado(sesion, previa["tercero_id"])
    if tercero is None:
        return Resultado(afinidad=None, idempotente=True)
    antes = repo.snapshot(sesion, afinidad_id)
    with sesion.conexion.transaction():
        repo_ter.incrementar_version(sesion, previa["tercero_id"])
        repo.leer_categoria_compartida(sesion, previa["categoria_id"])
        repo.borrar_afinidad(sesion, afinidad_id)
    auditoria.registrar(sesion, tabla=TABLA, registro_id=afinidad_id, accion=ACCION_ELIMINAR,
                        datos_antes_json=antes, motivo=MOTIVOS["BAJA"])
    return Resultado(afinidad=previa)
