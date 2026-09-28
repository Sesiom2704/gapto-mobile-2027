# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/categorias/servicio.py
# Descripcion: Gestion del arbol de categorias (F05-01, S4; F05-D008 C06;
#   diseno S4 v0.2 conforme con ajustes reconciliados AJ-S4-01..07).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Cada comando se ejecuta dentro de UNA transaccion de UnidadDeTrabajo
#   (retry completo ante 40P01) con esta secuencia fija:
#     advisory (CATEGORIAS, owner)            <- SIEMPRE lo primero (AJ-S4-01)
#     -> FOR NO KEY UPDATE del nodo y control de row_version
#     -> validaciones de dominio
#     -> escritura (repositorio) -> auditoria (misma transaccion).
#   Grafo de locks: advisory -> filas del catalogo en orden de id. El registro
#   (S1) solo toma FOR SHARE de la categoria y nunca espera el advisory, de
#   modo que no hay ciclo. STOP si aparece otra topologia (F05-01-R11).
#
#   Los rechazos de dominio se devuelven como `Rechazo` ANTES de escribir.
#   Los rechazos fisicos (UNIQUE literal, FK, triggers 0280/0285) se
#   traducen por IDENTIDAD tecnica (constraint o funcion del trigger), nunca
#   por el texto del error (AJ-S4-07), dentro de un savepoint que los aisla.
#
#   Auditoria (AJ-S4-04 bis): accion CREAR solo en el alta; el resto
#   ACTUALIZAR, con motivo cerrado por operacion (MOTIVOS) y snapshots de la
#   fila antes y despues. En DESACTIVAR_RAMA, una auditoria por nodo
#   modificado con el mismo request_id de la transaccion.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.categorias import lecturas
from app.categorias import repositorio as repo
from app.categorias.normalizacion import nombre_valido, nombre_visible, normalizar
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria

TABLA = "categorias_financieras"
AMBITOS = frozenset({"GASTO", "INGRESO", "AMBOS"})
ORDEN_MAXIMO = 32767

MOTIVOS = {
    "ALTA": "F05-01 ALTA",
    "RENOMBRAR": "F05-01 RENOMBRAR",
    "MOVER": "F05-01 MOVER",
    "ORDEN": "F05-01 ORDEN",
    "AMBITO": "F05-01 AMBITO",
    "DESACTIVAR": "F05-01 DESACTIVAR",
    "DESACTIVAR_RAMA": "F05-01 DESACTIVAR_RAMA",
    "REACTIVAR": "F05-01 REACTIVAR",
}

# Codigos de capa F05 (no forman parte de la taxonomia F04).
NOMBRE_DUPLICADO = "CATEGORIA_NOMBRE_DUPLICADO"
PADRE_NO_VALIDO = "CATEGORIA_PADRE_NO_VALIDO"
PADRE_DESHABILITADO = "CATEGORIA_PADRE_DESHABILITADO"
TIENE_HIJOS_ACTIVOS = "CATEGORIA_TIENE_HIJOS_ACTIVOS"
MOVIMIENTO_BLOQUEADO = "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO"
AMBITO_REQUIERE_CONFIRMACION = "CAMBIO_AMBITO_REQUIERE_CONFIRMACION"
# Codigos F04 reutilizados (contrato cerrado).
NO_ENCONTRADO = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

#: Identidades fisicas conocidas -> codigo estable (AJ-S4-07).
_CONSTRAINTS = {
    "uq_categorias_financieras__owner_parent_nombre": NOMBRE_DUPLICADO,
    "pk_categorias_financieras": IDENTIDAD_REUTILIZADA,
    "fk_categorias_financieras__parent": PADRE_NO_VALIDO,
    "fk_categorias_financieras__parent_same_owner": PADRE_NO_VALIDO,
    "ck_categorias_financieras__parent_no_self": PADRE_NO_VALIDO,
}
#: Identidad de la funcion del trigger tal como la informa el contexto
#: PL/pgSQL del error (P0001), no el texto del mensaje.
_FUNCIONES_TRIGGER = {
    "function gapto.fn_check_jerarquia_aciclica()": PADRE_NO_VALIDO,
    "function gapto.fn_check_categoria_deriva()": MOVIMIENTO_BLOQUEADO,
    "function gapto.fn_check_bolsa_prioridad()": MOVIMIENTO_BLOQUEADO,
}
_TRIGGERS_DIFERIDOS = (
    "gapto.trg_categorias_financieras__aciclica",
    "gapto.trg_categorias_financieras__bolsa_reparenting",
)


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    categoria: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------ utilidades
def _traducir_fisico(exc: psycopg.Error) -> str | None:
    diag = exc.diag
    if diag.constraint_name in _CONSTRAINTS:
        return _CONSTRAINTS[diag.constraint_name]
    if exc.sqlstate == "P0001" and diag.context:
        for funcion, codigo in _FUNCIONES_TRIGGER.items():
            if funcion in diag.context:
                return codigo
    return None


def _escribir(sesion: SesionMotor, accion) -> Rechazo | None:
    """Ejecuta la escritura en un savepoint forzando los triggers diferidos
    del catalogo a IMMEDIATE (WM 12C.9) y traduce fallos fisicos conocidos.
    Un fallo fisico no reconocido se propaga (error interno, sin escritura)."""
    conexion = sesion.conexion
    try:
        with conexion.transaction():
            accion()
            conexion.execute(f"SET CONSTRAINTS {', '.join(_TRIGGERS_DIFERIDOS)} IMMEDIATE")
    except psycopg.Error as exc:
        codigo = _traducir_fisico(exc)
        if codigo is None:
            raise
        return Rechazo(codigo)
    finally:
        # Restaura la semantica diferida para el resto de la transaccion.
        conexion.execute(f"SET CONSTRAINTS {', '.join(_TRIGGERS_DIFERIDOS)} DEFERRED")
    return None


def _auditar(sesion: SesionMotor, categoria_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    auditoria.registrar(
        sesion,
        tabla=TABLA,
        registro_id=categoria_id,
        accion=auditoria.ACCION_CREAR if operacion == "ALTA" else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes,
        datos_despues_json=repo.snapshot(sesion, categoria_id),
        motivo=MOTIVOS[operacion],
    )


def _colision(sesion: SesionMotor, parent_id, nombre: str, excluir) -> bool:
    clave = normalizar(nombre)
    return any(normalizar(n) == clave for _, n in repo.hermanos_activos(sesion, parent_id, excluir))


def _rama_habilitada(sesion: SesionMotor, parent_id) -> bool:
    if parent_id is None:
        return True
    return all(enabled for _, enabled in repo.cadena_ancestros(sesion, parent_id))


def _nodo(sesion: SesionMotor, categoria_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer(sesion, categoria_id, bloquear=True)
    if fila is None:
        return Rechazo(NO_ENCONTRADO)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def _resultado(sesion: SesionMotor, categoria_id, **kw) -> Resultado:
    return Resultado(categoria=repo.leer(sesion, categoria_id), **kw)


# ------------------------------------------------------------------ comandos
def alta(sesion: SesionMotor, *, categoria_id, nombre: str, parent_id, ambito: str,
         presupuestable_default: bool) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    if ambito not in AMBITOS or not nombre_valido(nombre):
        return Rechazo(ENTRADA_INVALIDA)
    visible = nombre_visible(nombre)
    existente = repo.leer(sesion, categoria_id)
    if existente is not None:
        # AJ-S4-05: idempotente solo si la fila sigue EXACTAMENTE como la dejo
        # el alta (row_version 1: ninguna evolucion posterior).
        igual = (
            existente["row_version"] == 1 and existente["nombre"] == visible
            and existente["parent_id"] == parent_id and existente["ambito"] == ambito
            and existente["presupuestable_default"] == presupuestable_default
            and existente["enabled"] and existente["icon_key"] is None
            and existente["codigo"] is None and existente["orden"] == 0
        )
        return Resultado(categoria=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    if parent_id is not None:
        if repo.leer(sesion, parent_id) is None:
            return Rechazo(PADRE_NO_VALIDO)
        if not _rama_habilitada(sesion, parent_id):
            return Rechazo(PADRE_DESHABILITADO)
    if _colision(sesion, parent_id, visible, None):
        return Rechazo(NOMBRE_DUPLICADO)
    rechazo = _escribir(sesion, lambda: repo.insertar(
        sesion, categoria_id=categoria_id, parent_id=parent_id, nombre=visible,
        ambito=ambito, presupuestable_default=presupuestable_default))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "ALTA", None)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


def renombrar(sesion: SesionMotor, *, categoria_id, nombre: str, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if not nombre_valido(nombre):
        return Rechazo(ENTRADA_INVALIDA)
    visible = nombre_visible(nombre)
    if nodo["enabled"] and _colision(sesion, nodo["parent_id"], visible, categoria_id):
        return Rechazo(NOMBRE_DUPLICADO)
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"nombre": visible}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "RENOMBRAR", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


def mover(sesion: SesionMotor, *, categoria_id, parent_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if parent_id is not None:
        if parent_id == categoria_id or repo.leer(sesion, parent_id) is None:
            return Rechazo(PADRE_NO_VALIDO)
        if parent_id in set(repo.subarbol(sesion, categoria_id)):
            return Rechazo(PADRE_NO_VALIDO)
    if nodo["enabled"]:
        if not _rama_habilitada(sesion, parent_id):
            return Rechazo(PADRE_DESHABILITADO)
        if _colision(sesion, parent_id, nodo["nombre"], categoria_id):
            return Rechazo(NOMBRE_DUPLICADO)
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"parent_id": parent_id}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "MOVER", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


def ordenar(sesion: SesionMotor, *, categoria_id, orden: int, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if not 0 <= orden <= ORDEN_MAXIMO:
        return Rechazo(ENTRADA_INVALIDA)
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"orden": orden}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "ORDEN", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


def cambiar_ambito(sesion: SesionMotor, *, categoria_id, ambito: str, confirmacion_uso: dict[str, int],
                   row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if ambito not in AMBITOS:
        return Rechazo(ENTRADA_INVALIDA)
    # Recuento bajo el lock del nodo: un registro que ya tenia FOR SHARE ha
    # terminado; uno posterior esperara y revalidara el nuevo ambito (C04).
    vigente = lecturas.uso_por_naturaleza(sesion, categoria_id)["efectos_activos"]
    if dict(confirmacion_uso) != vigente:
        return Rechazo(AMBITO_REQUIERE_CONFIRMACION, {"efectos_activos": vigente})
    if ambito == nodo["ambito"]:
        return Resultado(categoria=nodo, idempotente=True)
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"ambito": ambito}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "AMBITO", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


def desactivar(sesion: SesionMotor, *, categoria_id, modo: str, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if modo not in ("RAMA", "SOLO_SI_SIN_HIJOS_ACTIVOS"):
        return Rechazo(ENTRADA_INVALIDA)
    # AJ-S4-02: TODO el subarbol, atravesando nodos ya deshabilitados.
    descendientes = repo.subarbol(sesion, categoria_id)
    bloqueados = dict(repo.bloquear(sesion, descendientes))
    activos = [i for i in descendientes if bloqueados.get(i)]
    if modo == "SOLO_SI_SIN_HIJOS_ACTIVOS" and activos:
        return Rechazo(TIENE_HIJOS_ACTIVOS)
    operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "DESACTIVAR"
    objetivo = ([categoria_id] if nodo["enabled"] else []) + sorted(activos)
    if not objetivo:
        return Resultado(categoria=nodo, idempotente=True)
    for cid in objetivo:
        antes = repo.snapshot(sesion, cid)
        rechazo = _escribir(sesion, lambda cid=cid: repo.actualizar(sesion, cid, {"enabled": False}))
        if rechazo is not None:
            return rechazo
        _auditar(sesion, cid, operacion, antes)
    return _resultado(sesion, categoria_id, modificadas=tuple(objetivo))


def reactivar(sesion: SesionMotor, *, categoria_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    if nodo["enabled"]:
        return Resultado(categoria=nodo, idempotente=True)
    # Q4: solo este nodo, nunca en cascada. AJ-S4-03: toda la cadena de
    # ancestros debe estar habilitada.
    if not _rama_habilitada(sesion, nodo["parent_id"]):
        return Rechazo(PADRE_DESHABILITADO)
    if _colision(sesion, nodo["parent_id"], nodo["nombre"], categoria_id):
        return Rechazo(NOMBRE_DUPLICADO)
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"enabled": True}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "REACTIVAR", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))
