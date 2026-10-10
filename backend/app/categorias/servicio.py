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
#
#   v0.2.0 (F05-01 S6-ICONO (F05-D013)): comando `cambiar_icono` (§27.3) con
#   el orden fijo de AJ-ICON-04: advisory -> nodo (FOR NO KEY UPDATE +
#   row_version) -> validacion contra la biblioteca v1 (iconos.py, exacta,
#   AJ-ICON-03) -> comparacion con el valor persistido -> UPDATE solo si
#   cambia -> auditoria ACTUALIZAR motivo "F05-01 ICONO". Misma clave
#   (incluido NULL -> NULL): sin escritura, idempotente como E1. Se admite en
#   categorias deshabilitadas y solo toca icon_key (Q7). El alta admite
#   `icon_key` opcional (Q6) y su idempotencia (AJ-S4-05) lo compara.
#   Codigo F05 unico: ICONO_CATEGORIA_NO_VALIDO (AJ-ICON-05).
#
#   v0.3.0 (F05-01 R-LOCALE): la funcion del trigger se identifica por su
#   FIRMA calificada ("gapto.fn_...()"), que PostgreSQL no traduce, con
#   coincidencia de firma completa (_funcion_trigger). Antes se buscaba el
#   texto ingles "function gapto.fn_...()" y, con lc_messages en otro
#   idioma, mover bajo D-121/D-122 devolvia 500 en vez de 409. Sin cambios
#   de API, codigos, status ni orden de los comandos.
#
#   v0.4.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): comando atomico `reordenar`
#   del conjunto COMPLETO de hijos directos de un padre (raiz si None), en una
#   transaccion: advisory -> padre existente (sin exigir habilitado ni
#   bloquearlo) -> hijos persistidos FOR NO KEY UPDATE por id -> conjunto
#   identico (si no, CONJUNTO_HERMANOS_DESFASADO sin distinguir la causa) ->
#   row_version de cada hermano (VERSION_DESFASADA) -> orden objetivo = posicion
#   0..n-1 -> UPDATE solo de las filas cuyo orden cambia -> una auditoria
#   ACTUALIZAR "F05-01 REORDENAR" por fila modificada (mismo request_id).
#   Todas las validaciones preceden a la primera escritura. Sin cambios: el
#   orden persistido ya es el pedido -> idempotente, sin escritura.
#
#   v0.5.0 (F05-01 S7-MAG (F05-D020 D-MAG-10 B5; cierre de F05-01-R20)):
#   `desactivar` ejecuta TODAS sus escrituras y auditorias (uno o varios
#   nodos en RAMA) dentro de UN savepoint de alcance de comando. Un rechazo
#   fisico traducido en la escritura k > 1 sale del savepoint como
#   _AbortarComando (ROLLBACK TO SAVEPOINT revierte las k-1 anteriores y sus
#   auditorias) y se devuelve el Rechazo con CERO mutaciones; antes se
#   devolvia el Rechazo y la UdT confirmaba las anteriores (confirmacion
#   parcial). Un fallo no reconocido sigue propagandose (rollback total). Sin
#   cambios de API, codigos, status ni orden del comando.
#
#   v0.6.0 (F05-03 J2 §1.8): helper publico `tomar_advisory_del_catalogo`
#   para el onboarding (recuento de cero categorias bajo el advisory antes de
#   la primera alta) sin que el onboarding importe el repositorio. No
#   escribe; los comandos no cambian.
# Version: 0.6.0
# ============================================================

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.categorias import lecturas
from app.categorias import repositorio as repo
from app.categorias.iconos import icono_valido
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
    "ICONO": "F05-01 ICONO",
    "REORDENAR": "F05-01 REORDENAR",
}

# Codigos de capa F05 (no forman parte de la taxonomia F04).
NOMBRE_DUPLICADO = "CATEGORIA_NOMBRE_DUPLICADO"
PADRE_NO_VALIDO = "CATEGORIA_PADRE_NO_VALIDO"
PADRE_DESHABILITADO = "CATEGORIA_PADRE_DESHABILITADO"
TIENE_HIJOS_ACTIVOS = "CATEGORIA_TIENE_HIJOS_ACTIVOS"
MOVIMIENTO_BLOQUEADO = "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO"
AMBITO_REQUIERE_CONFIRMACION = "CAMBIO_AMBITO_REQUIERE_CONFIRMACION"
ICONO_NO_VALIDO = "ICONO_CATEGORIA_NO_VALIDO"
CONJUNTO_DESFASADO = "CONJUNTO_HERMANOS_DESFASADO"
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
    # Defensa residual (0340): inalcanzable si la biblioteca valida antes.
    "ck_categorias_financieras__icon_key_no_vacia_recortada": ICONO_NO_VALIDO,
}
#: Identidad de la funcion del trigger = su FIRMA calificada, que PostgreSQL
#: no traduce, dentro del contexto PL/pgSQL del error (P0001). Nunca el texto
#: localizable: ni el mensaje ni el prefijo del contexto ("PL/pgSQL function"
#: / "funcion PL/pgSQL" segun lc_messages; R-LOCALE).
_FUNCIONES_TRIGGER = {
    "gapto.fn_check_jerarquia_aciclica()": PADRE_NO_VALIDO,
    "gapto.fn_check_categoria_deriva()": MOVIMIENTO_BLOQUEADO,
    "gapto.fn_check_bolsa_prioridad()": MOVIMIENTO_BLOQUEADO,
}
#: Firma completa: a la izquierda, ningun caracter de identificador; a la
#: derecha, el "()" de la propia firma (fn_check_bolsa_prioridad no coincide
#: con fn_check_bolsa_prioridad_alcance()).
_PATRONES_TRIGGER = tuple(
    (re.compile(r"(?<![\w$.])" + re.escape(firma)), codigo) for firma, codigo in _FUNCIONES_TRIGGER.items()
)
_TRIGGERS_DIFERIDOS = (
    "gapto.trg_categorias_financieras__aciclica",
    "gapto.trg_categorias_financieras__bolsa_reparenting",
)


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


class _AbortarComando(Exception):
    """Sale del savepoint de comando de `desactivar` con un rechazo traducido (B5)."""

    def __init__(self, rechazo: Rechazo) -> None:
        super().__init__(rechazo.codigo)
        self.rechazo = rechazo


@dataclass(frozen=True)
class Resultado:
    categoria: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoReorden:
    hermanos: tuple[dict[str, Any], ...]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------ utilidades
def _traducir_fisico(exc: psycopg.Error) -> str | None:
    diag = exc.diag
    if diag.constraint_name in _CONSTRAINTS:
        return _CONSTRAINTS[diag.constraint_name]
    if exc.sqlstate == "P0001":
        return _funcion_trigger(diag.context)
    return None


def _funcion_trigger(contexto: str | None) -> str | None:
    """Codigo de la primera firma de _FUNCIONES_TRIGGER presente en el
    contexto PL/pgSQL (orden del diccionario); None si no hay ninguna."""
    if not contexto:
        return None
    for patron, codigo in _PATRONES_TRIGGER:
        if patron.search(contexto):
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


def tomar_advisory_del_catalogo(sesion: SesionMotor) -> None:
    """Advisory (CATEGORIAS, owner) para un comando compuesto de C06 (onboarding)."""
    repo.tomar_advisory(sesion)


# ------------------------------------------------------------------ comandos
def alta(sesion: SesionMotor, *, categoria_id, nombre: str, parent_id, ambito: str,
         presupuestable_default: bool, icon_key: str | None = None) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    if ambito not in AMBITOS or not nombre_valido(nombre):
        return Rechazo(ENTRADA_INVALIDA)
    if not icono_valido(icon_key):
        return Rechazo(ICONO_NO_VALIDO)
    visible = nombre_visible(nombre)
    existente = repo.leer(sesion, categoria_id)
    if existente is not None:
        # AJ-S4-05: idempotente solo si la fila sigue EXACTAMENTE como la dejo
        # el alta (row_version 1: ninguna evolucion posterior).
        igual = (
            existente["row_version"] == 1 and existente["nombre"] == visible
            and existente["parent_id"] == parent_id and existente["ambito"] == ambito
            and existente["presupuestable_default"] == presupuestable_default
            and existente["enabled"] and existente["icon_key"] == icon_key
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
        ambito=ambito, presupuestable_default=presupuestable_default, icon_key=icon_key))
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
    try:
        with sesion.conexion.transaction():  # savepoint de alcance de comando (D-MAG-10 B5)
            for cid in objetivo:
                antes = repo.snapshot(sesion, cid)
                rechazo = _escribir(sesion, lambda cid=cid: repo.actualizar(sesion, cid, {"enabled": False}))
                if rechazo is not None:
                    raise _AbortarComando(rechazo)
                _auditar(sesion, cid, operacion, antes)
    except _AbortarComando as abortado:
        return abortado.rechazo
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


def cambiar_icono(sesion: SesionMotor, *, categoria_id, icon_key: str | None, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    nodo = _nodo(sesion, categoria_id, row_version)
    if isinstance(nodo, Rechazo):
        return nodo
    # AJ-ICON-03/05: pertenencia exacta a la biblioteca publicada; None = sin icono.
    if not icono_valido(icon_key):
        return Rechazo(ICONO_NO_VALIDO)
    # Misma clave que la persistida: sin UPDATE ni auditoria (como E1).
    if icon_key == nodo["icon_key"]:
        return Resultado(categoria=nodo, idempotente=True)
    # Q7: tambien en deshabilitadas; solo cambia icon_key (no reactiva).
    antes = repo.snapshot(sesion, categoria_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"icon_key": icon_key}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, categoria_id, "ICONO", antes)
    return _resultado(sesion, categoria_id, modificadas=(categoria_id,))


# `hermanos`: [(id, row_version)] en el orden deseado; debe ser el conjunto
# COMPLETO de hijos directos de `parent_id` (raiz si None).
def reordenar(sesion: SesionMotor, *, parent_id, hermanos: list[tuple[uuid.UUID, int]]) -> ResultadoReorden | Rechazo:
    repo.tomar_advisory(sesion)
    if not hermanos or len(hermanos) > ORDEN_MAXIMO + 1:
        return Rechazo(ENTRADA_INVALIDA)
    if parent_id is not None and repo.leer(sesion, parent_id) is None:
        return Rechazo(NO_ENCONTRADO)
    persistidos = {f["id"]: f for f in repo.hijos_bloqueados(sesion, parent_id)}
    pedidos = [cid for cid, _ in hermanos]
    # Sin distinguir falta, sobra, inexistente, ajena u otro padre (no revela existencia).
    if len(set(pedidos)) != len(pedidos) or set(pedidos) != set(persistidos):
        return Rechazo(CONJUNTO_DESFASADO)
    if any(persistidos[cid]["row_version"] != rv for cid, rv in hermanos):
        return Rechazo(VERSION_DESFASADA)
    cambian = [(cid, pos) for pos, cid in enumerate(pedidos) if persistidos[cid]["orden"] != pos]
    for cid, pos in cambian:
        antes = repo.snapshot(sesion, cid)
        rechazo = _escribir(sesion, lambda cid=cid, pos=pos: repo.actualizar(sesion, cid, {"orden": pos}))
        if rechazo is not None:
            return rechazo
        _auditar(sesion, cid, "REORDENAR", antes)
    return ResultadoReorden(
        hermanos=tuple(repo.leer(sesion, cid) for cid in pedidos),
        idempotente=not cambian,
        modificadas=tuple(cid for cid, _ in cambian),
    )
