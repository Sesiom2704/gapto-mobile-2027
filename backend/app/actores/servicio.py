# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/actores/servicio.py
# Descripcion: Writer de alta perezosa del actor financiero de un tercero
#   PERSONA (F05-06 M3 §A3; F05-D043 §57.1.4; AJ-M3-DEC-06/07). API DE
#   INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Se ejecuta SIEMPRE dentro de la transaccion del adaptador que lo invoca
#   (no abre transaccion propia) y en el orden canonico de M3-PRE2 P2:
#     [advisory INVERSIONES] -> cuentas FNKU -> capacidad FS -> categoria FS
#     -> terceros FOR SHARE (por UUID) -> ESTE WRITER -> hecho -> posiciones.
#   Requisitos que la BD no protege (M3-PRE2 P1) y por eso valida el writer
#   bajo el FOR SHARE del tercero: tercero del owner (ademas de la RLS),
#   naturaleza PERSONA (sin actores de empresas) y habilitado.
#   - No toca titularidades ni participaciones (cuenta/entidad_participaciones).
#   - Auditoria del alta en la misma transaccion (fn_registrar_auditoria, con
#     el request_id del contexto); el rollback del adaptador no deja huerfanos.
#   - Un 42501 de la RLS (owner o tercero ajeno) se traduce a
#     TERCERO_NO_DISPONIBLE sin efectos: no revela si el tercero existe.
#   Los rechazos son codigos de capa F05 (sin escritura previa).
# Version: 0.1.0 (F05-06 M3 §A3)
# ============================================================

from __future__ import annotations

import uuid

import psycopg

from app.actores import repositorio as repo
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria

TERCERO_NO_DISPONIBLE = "TERCERO_NO_DISPONIBLE"
TERCERO_NO_PERSONA = "TERCERO_NO_PERSONA"
MOTIVO_ALTA = "F05-06 M3: alta del actor financiero de un tercero persona"


class RechazoActor(Exception):
    """Rechazo de capa F05 del writer de actor (sin escritura)."""

    def __init__(self, codigo: str, tercero_id: uuid.UUID) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.tercero_id = tercero_id


def validar_tercero_persona(sesion: SesionMotor, tercero_id: uuid.UUID) -> None:
    """FOR SHARE del tercero y relectura: owner, PERSONA y habilitado."""
    tercero = repo.leer_tercero_compartido(sesion, tercero_id)
    if tercero is None or not tercero["enabled"]:
        raise RechazoActor(TERCERO_NO_DISPONIBLE, tercero_id)
    if tercero["naturaleza"] != repo.NATURALEZA_PERSONA:
        raise RechazoActor(TERCERO_NO_PERSONA, tercero_id)


def actor_de_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> uuid.UUID:
    """Actor del tercero; lo crea si no existe. Exige `validar_tercero_persona`
    previo en la MISMA transaccion (el FOR SHARE debe seguir retenido)."""
    try:
        with sesion.conexion.transaction():
            creado = repo.insertar_si_no_existe(sesion, tercero_id)
    except psycopg.errors.InsufficientPrivilege as exc:
        raise RechazoActor(TERCERO_NO_DISPONIBLE, tercero_id) from exc
    if creado is not None:
        actor_id, foto = creado
        auditoria.registrar(
            sesion,
            tabla=repo.TABLA,
            registro_id=actor_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=foto,
            motivo=MOTIVO_ALTA,
        )
        return actor_id
    actor_id = repo.leer_actor_de_tercero(sesion, tercero_id)
    if actor_id is None:  # pragma: no cover - la UNIQUE garantiza la fila
        raise RechazoActor(TERCERO_NO_DISPONIBLE, tercero_id)
    return actor_id


def actores_de_terceros(sesion: SesionMotor, terceros: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """Orden canonico: TODOS los terceros FOR SHARE por UUID y despues las
    altas, tambien por UUID. Devuelve {tercero_id: actor_id}."""
    ordenados = sorted(set(terceros), key=str)
    for tercero_id in ordenados:
        validar_tercero_persona(sesion, tercero_id)
    return {tercero_id: actor_de_tercero(sesion, tercero_id) for tercero_id in ordenados}
