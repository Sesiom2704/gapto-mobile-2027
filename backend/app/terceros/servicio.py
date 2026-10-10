# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/terceros/servicio.py
# Descripcion: Writers de terceros del registro (F05-04 J2 §1.3; F05 §46.4
#   R4/R5; F05-D032 C2, D-032.2). Patron de categorias/: alta, editar,
#   desactivar y reactivar. API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   Cada comando se ejecuta dentro de UNA transaccion de UnidadDeTrabajo
#   (retry completo ante 40P01/40001) con esta secuencia fija:
#     advisory (TERCEROS, owner)            <- SIEMPRE lo primero (C2)
#     -> FOR NO KEY UPDATE de la fila y control de row_version (no en el alta)
#     -> validaciones de dominio -> escritura (repositorio) -> auditoria.
#   Grafo de locks: advisory -> fila del tercero. Un writer de terceros NO
#   toca plantillas ni preferencias (desactivar no cascada, C2): estas
#   ignoran o avisan del tercero desactivado al leerlo. El registro solo toma
#   FOR SHARE del tercero y nunca este advisory.
#
#   - Alta con UUID de cliente (R5): devuelve una identificacion inequivoca
#     (id creado o ya existente para ese UUID). Idempotente solo si la fila
#     sigue EXACTAMENTE como la dejo el alta (row_version 1, habilitada, mismo
#     nombre visible y naturaleza); en otro caso, o con un UUID de otro owner
#     (PK fisica), IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos.
#   - Nombre: normalizacion visible de C06 (NFKC, recorte, espacios), 1..160.
#     SIN unicidad: el aviso de posible duplicado es una lectura
#     (lecturas.candidatos) y nunca un control ni una fusion (R5).
#   - Naturaleza: PERSONA, EMPRESA, ORGANISMO, OTRO o NULL («No lo sé»). Un
#     cambio que contradiga tercero_personas lo rechaza el trigger 0080/
#     fn_check_tercero_naturaleza, traducido por FIRMA de la funcion dentro de
#     un savepoint con el trigger diferido forzado a IMMEDIATE.
#   - Auditoria: CREAR en el alta; ACTUALIZAR (motivo por operacion) en el
#     resto, con snapshots antes/despues.
#   Codigos de capa F05: TERCERO_NO_ENCONTRADO, TERCERO_NATURALEZA_NO_ADMITIDA.
#   F04 reutilizados: VERSION_DESFASADA, IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
#   ENTRADA_INVALIDA.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.3)
# ============================================================

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.categorias.normalizacion import nombre_visible
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria
from app.terceros import repositorio as repo

TABLA = "terceros"
LONGITUD_MAXIMA = 160
NATURALEZAS = frozenset({"PERSONA", "EMPRESA", "ORGANISMO", "OTRO"})

MOTIVOS = {
    "ALTA": "F05-04 TERCERO ALTA",
    "EDITAR": "F05-04 TERCERO EDITAR",
    "DESACTIVAR": "F05-04 TERCERO DESACTIVAR",
    "REACTIVAR": "F05-04 TERCERO REACTIVAR",
}

NO_ENCONTRADO = "TERCERO_NO_ENCONTRADO"
NATURALEZA_NO_ADMITIDA = "TERCERO_NATURALEZA_NO_ADMITIDA"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

_CONSTRAINTS = {"pk_terceros": IDENTIDAD_REUTILIZADA}
_FIRMA_TRIGGER = re.compile(r"(?<![\w$.])" + re.escape("gapto.fn_check_tercero_naturaleza()"))
_TRIGGER = "gapto.trg_terceros__naturaleza_personas"


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    tercero: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def _traducir(exc: psycopg.Error) -> str | None:
    if exc.diag.constraint_name in _CONSTRAINTS:
        return _CONSTRAINTS[exc.diag.constraint_name]
    if exc.sqlstate == "P0001" and exc.diag.context and _FIRMA_TRIGGER.search(exc.diag.context):
        return NATURALEZA_NO_ADMITIDA
    return None


def _escribir(sesion: SesionMotor, accion) -> Rechazo | None:
    """Escritura en un savepoint con el trigger diferido forzado a IMMEDIATE;
    traduce por identidad (constraint o firma de la funcion). Un fallo no
    reconocido se propaga (error interno, sin escritura)."""
    conexion = sesion.conexion
    try:
        with conexion.transaction():
            accion()
            conexion.execute(f"SET CONSTRAINTS {_TRIGGER} IMMEDIATE")
    except psycopg.Error as exc:
        codigo = _traducir(exc)
        if codigo is None:
            raise
        return Rechazo(codigo)
    finally:
        conexion.execute(f"SET CONSTRAINTS {_TRIGGER} DEFERRED")
    return None


def _auditar(sesion: SesionMotor, tercero_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    auditoria.registrar(
        sesion,
        tabla=TABLA,
        registro_id=tercero_id,
        accion=auditoria.ACCION_CREAR if operacion == "ALTA" else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes,
        datos_despues_json=repo.snapshot(sesion, tercero_id),
        motivo=MOTIVOS[operacion],
    )


def _fila(sesion: SesionMotor, tercero_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer(sesion, tercero_id, bloquear=True)
    if fila is None:
        return Rechazo(NO_ENCONTRADO)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def _validos(nombre: str, naturaleza: str | None) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    if not 0 < len(visible) <= LONGITUD_MAXIMA:
        return Rechazo(ENTRADA_INVALIDA)
    if naturaleza is not None and naturaleza not in NATURALEZAS:
        return Rechazo(ENTRADA_INVALIDA)
    return visible


def _resultado(sesion: SesionMotor, tercero_id, **kw) -> Resultado:
    return Resultado(tercero=repo.leer(sesion, tercero_id), **kw)


# ------------------------------------------------------------------ comandos
def alta(sesion: SesionMotor, *, tercero_id, nombre: str, naturaleza: str | None = None) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    visible = _validos(nombre, naturaleza)
    if isinstance(visible, Rechazo):
        return visible
    existente = repo.leer(sesion, tercero_id)
    if existente is not None:
        igual = (
            existente["row_version"] == 1 and existente["enabled"]
            and existente["nombre"] == visible and existente["naturaleza"] == naturaleza
        )
        return Resultado(tercero=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    rechazo = _escribir(sesion, lambda: repo.insertar_tercero(
        sesion, tercero_id=tercero_id, nombre=visible, naturaleza=naturaleza))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, tercero_id, "ALTA", None)
    return _resultado(sesion, tercero_id, modificadas=(tercero_id,))


def editar(sesion: SesionMotor, *, tercero_id, row_version: int, nombre: str,
           naturaleza: str | None) -> Resultado | Rechazo:
    """Sustituye nombre y naturaleza (estado completo; NULL = «No lo sé»)."""
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, tercero_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    visible = _validos(nombre, naturaleza)
    if isinstance(visible, Rechazo):
        return visible
    cambios = {k: v for k, v in (("nombre", visible), ("naturaleza", naturaleza)) if fila[k] != v}
    if not cambios:
        return Resultado(tercero=fila, idempotente=True)
    antes = repo.snapshot(sesion, tercero_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_tercero(sesion, tercero_id, cambios))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, tercero_id, "EDITAR", antes)
    return _resultado(sesion, tercero_id, modificadas=(tercero_id,))


def desactivar(sesion: SesionMotor, *, tercero_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, tercero_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if not fila["enabled"]:
        return Resultado(tercero=fila, idempotente=True)
    antes = repo.snapshot(sesion, tercero_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_tercero(sesion, tercero_id, {"enabled": False}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, tercero_id, "DESACTIVAR", antes)
    return _resultado(sesion, tercero_id, modificadas=(tercero_id,))


def reactivar(sesion: SesionMotor, *, tercero_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, tercero_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if fila["enabled"]:
        return Resultado(tercero=fila, idempotente=True)
    antes = repo.snapshot(sesion, tercero_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_tercero(sesion, tercero_id, {"enabled": True}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, tercero_id, "REACTIVAR", antes)
    return _resultado(sesion, tercero_id, modificadas=(tercero_id,))
