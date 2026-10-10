# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/contextos/servicio.py
# Descripcion: Writers de contextos del registro (F05-04 J2 §1.4; F05-D031;
#   F05 §46.4 R4/R5; F05-D032 C2, D-032.2). Alta, editar, desactivar y
#   reactivar. API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Cada comando, en UNA transaccion de UnidadDeTrabajo (retry completo ante
#   40P01/40001):
#     advisory (CONTEXTOS, owner)               <- SIEMPRE lo primero (C2)
#     -> FOR NO KEY UPDATE de la entidad y de su fila de contextos (no en el
#        alta) + control de row_version (el de la entidad)
#     -> validaciones -> escritura (repositorio) -> auditoria.
#   NUNCA toma INVERSIONES: no escribe entidades.tipo_entidad tras el alta,
#   asi que el trigger D-080 de entidades no se dispara. Desactivar un
#   contexto no escribe plantillas ni preferencias (C2).
#
#   - Alta con UUID de cliente (R5): entidad CONTEXTO + contextos en la misma
#     transaccion. Idempotente solo si el agregado sigue EXACTAMENTE como lo
#     dejo el alta (row_version 1, habilitado, mismo nombre visible, tipo y
#     fechas); en otro caso, o si el UUID es de otra entidad o de otro owner
#     (PK fisica de entidades), IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#   - Tipo: VIAJE, REFORMA, EVENTO, SOCIAL, PROYECTO u OTRO (sin preseleccion
#     en la UI). Fechas opcionales; si ambas, fin >= inicio.
#   - Nombre: normalizacion visible de C06, 1..160. Sin unicidad.
#   - Auditoria: tabla `entidades` (raiz del agregado) con el snapshot del par
#     entidad+contexto; CREAR en el alta y ACTUALIZAR en el resto.
#   Codigos F05: CONTEXTO_NO_ENCONTRADO. F04 reutilizados: VERSION_DESFASADA,
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, ENTRADA_INVALIDA.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.categorias.normalizacion import nombre_visible
from app.contextos import repositorio as repo
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria

TABLA = "entidades"
LONGITUD_MAXIMA = 160
TIPOS = frozenset({"VIAJE", "REFORMA", "EVENTO", "SOCIAL", "PROYECTO", "OTRO"})

MOTIVOS = {
    "ALTA": "F05-04 CONTEXTO ALTA",
    "EDITAR": "F05-04 CONTEXTO EDITAR",
    "DESACTIVAR": "F05-04 CONTEXTO DESACTIVAR",
    "REACTIVAR": "F05-04 CONTEXTO REACTIVAR",
}

NO_ENCONTRADO = "CONTEXTO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

_CONSTRAINTS = {"pk_entidades": IDENTIDAD_REUTILIZADA, "pk_contextos": IDENTIDAD_REUTILIZADA}


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    contexto: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def _escribir(sesion: SesionMotor, accion) -> Rechazo | None:
    """Escritura en un savepoint con los triggers diferidos de subtipo forzados
    a IMMEDIATE; traduce la PK por identidad. Fallo no reconocido: propaga."""
    conexion = sesion.conexion
    triggers = "gapto.trg_entidades__subtipo_unico, gapto.trg_contextos__subtipo_unico"
    try:
        with conexion.transaction():
            accion()
            conexion.execute(f"SET CONSTRAINTS {triggers} IMMEDIATE")
    except psycopg.Error as exc:
        codigo = _CONSTRAINTS.get(exc.diag.constraint_name)
        if codigo is None:
            raise
        return Rechazo(codigo)
    finally:
        conexion.execute(f"SET CONSTRAINTS {triggers} DEFERRED")
    return None


def _auditar(sesion: SesionMotor, contexto_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    auditoria.registrar(
        sesion,
        tabla=TABLA,
        registro_id=contexto_id,
        accion=auditoria.ACCION_CREAR if operacion == "ALTA" else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes,
        datos_despues_json=repo.snapshot(sesion, contexto_id),
        motivo=MOTIVOS[operacion],
    )


def _validos(nombre: str, tipo: str, desde: dt.date | None, hasta: dt.date | None) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    if not 0 < len(visible) <= LONGITUD_MAXIMA or tipo not in TIPOS:
        return Rechazo(ENTRADA_INVALIDA)
    if desde is not None and hasta is not None and hasta < desde:
        return Rechazo(ENTRADA_INVALIDA)
    return visible


def _fila(sesion: SesionMotor, contexto_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer(sesion, contexto_id, bloquear=True)
    if fila is None:
        return Rechazo(NO_ENCONTRADO)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def _resultado(sesion: SesionMotor, contexto_id, **kw) -> Resultado:
    return Resultado(contexto=repo.leer(sesion, contexto_id), **kw)


# ------------------------------------------------------------------ comandos
def alta(sesion: SesionMotor, *, contexto_id, nombre: str, tipo_contexto: str, fecha_inicio=None,
         fecha_fin=None) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    visible = _validos(nombre, tipo_contexto, fecha_inicio, fecha_fin)
    if isinstance(visible, Rechazo):
        return visible
    existente = repo.leer(sesion, contexto_id)
    if existente is not None:
        igual = (
            existente["row_version"] == 1 and existente["enabled"] and existente["nombre"] == visible
            and existente["tipo_contexto"] == tipo_contexto and existente["fecha_inicio"] == fecha_inicio
            and existente["fecha_fin"] == fecha_fin
        )
        return Resultado(contexto=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    if repo.existe_entidad(sesion, contexto_id):
        # El UUID ya es de otra entidad del owner (otro tipo): nunca se reutiliza.
        return Rechazo(IDENTIDAD_REUTILIZADA)
    rechazo = _escribir(sesion, lambda: repo.insertar_contexto(
        sesion, contexto_id=contexto_id, nombre=visible, tipo_contexto=tipo_contexto,
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, contexto_id, "ALTA", None)
    return _resultado(sesion, contexto_id, modificadas=(contexto_id,))


def editar(sesion: SesionMotor, *, contexto_id, row_version: int, nombre: str, tipo_contexto: str,
           fecha_inicio=None, fecha_fin=None) -> Resultado | Rechazo:
    """Sustituye nombre, tipo y fechas (estado completo)."""
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, contexto_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    visible = _validos(nombre, tipo_contexto, fecha_inicio, fecha_fin)
    if isinstance(visible, Rechazo):
        return visible
    nuevo = {"nombre": visible, "tipo_contexto": tipo_contexto, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}
    cambios = {k: v for k, v in nuevo.items() if fila[k] != v}
    if not cambios:
        return Resultado(contexto=fila, idempotente=True)
    antes = repo.snapshot(sesion, contexto_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_contexto(sesion, contexto_id, cambios))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, contexto_id, "EDITAR", antes)
    return _resultado(sesion, contexto_id, modificadas=(contexto_id,))


def _cambiar_estado(sesion: SesionMotor, contexto_id, row_version: int, enabled: bool) -> Resultado | Rechazo:
    fila = _fila(sesion, contexto_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if fila["enabled"] is enabled:
        return Resultado(contexto=fila, idempotente=True)
    antes = repo.snapshot(sesion, contexto_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_contexto(sesion, contexto_id, {"enabled": enabled}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, contexto_id, "REACTIVAR" if enabled else "DESACTIVAR", antes)
    return _resultado(sesion, contexto_id, modificadas=(contexto_id,))


def desactivar(sesion: SesionMotor, *, contexto_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    return _cambiar_estado(sesion, contexto_id, row_version, False)


def reactivar(sesion: SesionMotor, *, contexto_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    return _cambiar_estado(sesion, contexto_id, row_version, True)
