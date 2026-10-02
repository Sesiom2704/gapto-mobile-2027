# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/magnitudes/servicio.py
# Descripcion: Comandos de S7-MAG (F05-D020, expediente F05 §34): parametri-
#   zacion de magnitudes por categoria. API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10 (F10-03/04).
#
#   Comandos sobre ASOCIACIONES de una categoria (D-MAG-01, bloque
#   «Configuracion de esta categoria»):
#     asociar (origen EXISTENTE o NUEVA = alta rapida + asociacion),
#     cambiar_obligatoria, retirar (DELETE legitimo + compactacion), reordenar.
#   Comandos sobre la MAGNITUD (bloque «afecta a todas sus categorias»):
#     renombrar, deshabilitar (confirmacion de impacto), rehabilitar.
#
#   LOCKS (D-MAG-03). Toda funcion publica mutadora toma PRIMERO el advisory
#   (CATEGORIAS, owner) con categorias/repositorio.tomar_advisory (la misma
#   clave que los comandos del arbol y los triggers 0280/0285). Despues:
#     - asociaciones: la fila de la categoria FOR NO KEY UPDATE (lectura con
#       categorias/repositorio.leer; existe y es del owner, sin exigir que
#       este habilitada: P1) -> magnitud(es) FOR NO KEY UPDATE por id
#       ordenado -> validaciones -> escrituras -> auditoria. El FOR NO KEY
#       UPDATE de la categoria es incompatible con el FOR SHARE de C-a/C07:
#       un registro en curso hace esperar al escritor y viceversa (R16).
#     - magnitud: la fila de magnitudes FOR NO KEY UPDATE + row_version ->
#       (deshabilitar) categorias afectadas leidas bajo ese lock, sin
#       bloquearlas -> escritura -> auditoria.
#   Nunca FOR SHARE. Ningun comando escribe la categoria ni su row_version
#   (D-MAG-04). Orden de locks en todos: advisory -> categoria -> magnitudes,
#   el mismo sentido que C07 (categoria -> asociaciones -> magnitudes).
#
#   CONCURRENCIA OPTIMISTA (D-MAG-04). Magnitud: row_version. Asociacion:
#   identidad estable `asociacion_id` (PK) + categoria + magnitud + valor
#   esperado del atributo (obligatoria_actual); cualquier discrepancia ->
#   ASOCIACION_NO_EXISTE sin distinguir la causa. Reordenar: el conjunto
#   COMPLETO esperado (asociacion_id, magnitud_id, orden, obligatoria) frente
#   al persistido -> CONJUNTO_MAGNITUDES_DESFASADO. Una asociacion eliminada y
#   recreada tiene otra identidad (CE-S7MAG-02).
#
#   ORDEN DE EVALUACION FIJO (B1: todo rechazo funcional ANTES de la primera
#   escritura):
#     asociar:   advisory -> categoria (AGREGADO_NO_ENCONTRADO) ->
#                EXISTENTE: magnitud (MAGNITUD_NO_ADMITIDA) -> par ya asociado
#                  (misma obligatoria: idempotente; distinta: ASOCIACION_YA_EXISTE)
#                NUEVA: datos (ENTRADA_INVALIDA) -> identidad de la magnitud
#                  ya usada (idempotente si row_version 1, campos iguales y la
#                  asociacion igual; si no IDENTIDAD_REUTILIZADA) -> nombre
#                  normalizado (MAGNITUD_NOMBRE_DUPLICADO + detalle)
#                -> capacidad de orden (ENTRADA_INVALIDA)
#     cambiar_obligatoria / retirar: advisory -> categoria -> magnitud ->
#                identidad de la asociacion (ASOCIACION_NO_EXISTE) -> (sin
#                cambio: idempotente)
#     reordenar: advisory -> categoria -> magnitudes de la categoria ->
#                conjunto (CONJUNTO_MAGNITUDES_DESFASADO) -> (sin cambio:
#                idempotente)
#     renombrar / deshabilitar / rehabilitar: advisory -> magnitud de la ruta
#                (AGREGADO_NO_ENCONTRADO) -> row_version (VERSION_DESFASADA) ->
#                renombrar: nombre (ENTRADA_INVALIDA) -> mismo nombre:
#                idempotente -> colision (MAGNITUD_NOMBRE_DUPLICADO);
#                deshabilitar: ya deshabilitada: idempotente -> impacto bajo
#                lock frente a la confirmacion
#                (MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION + detalle);
#                rehabilitar: ya habilitada: idempotente.
#
#   ORDEN DE LAS ASOCIACIONES (D-S7-04): contiguo 0..n-1 por categoria;
#   asociar anade en la posicion n; retirar compacta en el mismo comando;
#   reordenar escribe 0..n-1 solo en las filas que cambian. Un estado previo
#   no contiguo se tolera en lectura y se normaliza en la primera mutacion de
#   asociaciones de esa categoria.
#
#   ATOMICIDAD (D-MAG-10, B1..B6). Cada comando ejecuta TODAS sus escrituras
#   y auditorias dentro de UN savepoint de alcance de comando (`_comando`).
#   Cada escritura va ademas en su propio savepoint (`_escribir`) que aisla
#   el fallo fisico; un fallo fisico TRADUCIBLE se convierte en
#   _AbortarComando, que SALE del savepoint de comando (ROLLBACK TO SAVEPOINT
#   revierte datos y auditoria) y se captura fuera: se devuelve el Rechazo con
#   CERO mutaciones. Un fallo no reconocido se propaga hasta la UdT (rollback
#   total). No se modifica core/unidad_trabajo.py ni F04.
#   Traduccion fisica SOLO por IDENTIDAD (diag.constraint_name) de las
#   constraints conocidas (_CONSTRAINTS). `42501` NUNCA se traduce (R19; D32
#   ajustada por la revisora, AJ-S7MAGIMPL-01): la traduccion de 42501 no puede
#   basarse unicamente en que el error ocurra dentro de la primitiva de
#   asociacion; tras la prevalidacion bajo FOR NO KEY UPDATE de la categoria y
#   de la magnitud (el owner de una fila no cambia), un 42501 en cualquier
#   escritura solo puede ser un error de privilegios o de configuracion RLS y
#   debe seguir siendo un error tecnico observable: no se reconoce, sale del
#   savepoint de comando (rollback total) y la UdT lo clasifica (500).
#   MAGNITUD_NO_ADMITIDA solo lo produce la prevalidacion.
#
#   IDENTIDAD DE LA ASOCIACION (D-MAG-04; AJ-S7MAGIMPL-02). En el alta rapida
#   (NUEVA) el asociacion_id se DERIVA de la identidad de la intencion del
#   cliente: uuid5(magnitud_id, "asociacion:<categoria_id>") (mismo patron que
#   AJ-C07-03); en EXISTENTE es aleatorio (uuid4). Una asociacion retirada y
#   recreada como EXISTENTE tiene siempre otra identidad que la creada por el
#   alta. El reintento NUEVA es idempotente solo si la magnitud sigue como la
#   dejo el alta (row_version 1, enabled, nombre, unidad y precision) Y existe
#   la asociacion con EXACTAMENTE el id derivado, la misma categoria, magnitud
#   y obligatoria; el `orden` NO forma parte del criterio (D39: lo alteran
#   comandos ajenos a la intencion -compactar, reordenar- y la intencion no
#   fija posicion). Cualquier otra combinacion -> IDENTIDAD_REUTILIZADA.
#
#   AUDITORIA (D-MAG-09): auditoria.registrar con tabla `magnitudes` (CREAR en
#   la alta rapida; ACTUALIZAR en renombrar/deshabilitar/rehabilitar) y tabla
#   `categoria_magnitudes` (CREAR al asociar; ACTUALIZAR en obligatoriedad y
#   en cada fila cuyo orden cambia; ELIMINAR al retirar, con datos_antes = la
#   fila y datos_despues NULL). Constante local ACCION_ELIMINAR:
#   auditoria_repository.py no se modifica. Motivos cerrados «F05-01 MAG_*».
#   Todas las filas de un comando comparten el request_id de la transaccion.
# Version: 0.1.0 (F05-01 S7-MAG)
# Version: 0.2.0 (F05-01 S7-MAG correctivo AJ-S7MAGIMPL-01/02): 42501 nunca se
#   traduce (se retira `rls_prevalidado`); asociacion_id derivado en NUEVA y
#   criterio de idempotencia por ese id (D39: sin `orden`).
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import psycopg

from app.categorias import repositorio as repo_cat
from app.categorias.servicio import Rechazo
from app.core.unidad_trabajo import SesionMotor
from app.magnitudes import repositorio as repo
from app.magnitudes.normalizacion import (
    nombre_magnitud_valido,
    nombre_visible,
    normalizar,
    precision_valida,
    unidad_valida,
)
from app.repositories import auditoria_repository as auditoria

TABLA_MAGNITUDES = "magnitudes"
TABLA_ASOCIACIONES = "categoria_magnitudes"
#: Accion de auditoria admitida por el CHECK de 0070; F04 no publica la constante.
ACCION_ELIMINAR = "ELIMINAR"
#: orden es smallint: posiciones 0..32767 (CE-S7MAG-08).
ORDEN_MAXIMO = 32767

MOTIVOS = {
    "ALTA": "F05-01 MAG_ALTA",
    "RENOMBRAR": "F05-01 MAG_RENOMBRAR",
    "DESHABILITAR": "F05-01 MAG_DESHABILITAR",
    "REHABILITAR": "F05-01 MAG_REHABILITAR",
    "ASOCIAR": "F05-01 MAG_ASOCIAR",
    "OBLIGATORIA": "F05-01 MAG_OBLIGATORIA",
    "ORDEN": "F05-01 MAG_ORDEN",
    "RETIRAR": "F05-01 MAG_RETIRAR",
}

# Codigos F05 nuevos (D-MAG-09).
NOMBRE_DUPLICADO = "MAGNITUD_NOMBRE_DUPLICADO"
ASOCIACION_YA_EXISTE = "ASOCIACION_YA_EXISTE"
ASOCIACION_NO_EXISTE = "ASOCIACION_NO_EXISTE"
CONJUNTO_DESFASADO = "CONJUNTO_MAGNITUDES_DESFASADO"
REQUIERE_CONFIRMACION = "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"
# Reutilizados conforme a su contrato.
MAGNITUD_NO_ADMITIDA = "MAGNITUD_NO_ADMITIDA"
NO_ENCONTRADO = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

#: Identidades fisicas conocidas -> codigo estable (defensa residual).
_CONSTRAINTS = {
    "uq_magnitudes__owner_nombre": NOMBRE_DUPLICADO,
    "uq_categoria_magnitudes__categoria_magnitud": ASOCIACION_YA_EXISTE,
    "pk_magnitudes": IDENTIDAD_REUTILIZADA,
    "ck_magnitudes__nombre_no_blanco": ENTRADA_INVALIDA,
    "ck_magnitudes__unidad_default_no_blanco": ENTRADA_INVALIDA,
    "ck_magnitudes__precision_decimales": ENTRADA_INVALIDA,
    "ck_categoria_magnitudes__orden_no_negativo": ENTRADA_INVALIDA,
}


@dataclass(frozen=True)
class ResultadoAsociacion:
    categoria_id: uuid.UUID
    asociacion: dict[str, Any]
    magnitud: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoAsociaciones:
    categoria_id: uuid.UUID
    asociaciones: tuple[dict[str, Any], ...]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoMagnitud:
    magnitud: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


class _AbortarComando(Exception):
    """Sale del savepoint de comando con un rechazo traducido (D-MAG-10 B2/B3)."""

    def __init__(self, rechazo: Rechazo) -> None:
        super().__init__(rechazo.codigo)
        self.rechazo = rechazo


# ------------------------------------------------------------------ atomicidad
def _traducir(exc: psycopg.Error) -> str | None:
    """Solo identidades fisicas conocidas. 42501 (y cualquier otra) -> None (R19)."""
    return _CONSTRAINTS.get(exc.diag.constraint_name)


def _escribir(sesion: SesionMotor, accion: Callable[[], None]) -> None:
    """Una escritura en su propio savepoint. Fallo traducible -> _AbortarComando
    (sale del savepoint de comando); no reconocido -> se propaga a la UdT."""
    try:
        with sesion.conexion.transaction():
            accion()
    except psycopg.Error as exc:
        codigo = _traducir(exc)
        if codigo is None:
            raise
        raise _AbortarComando(Rechazo(codigo)) from exc


def _comando(sesion: SesionMotor, escrituras: Callable[[], None]) -> Rechazo | None:
    """Savepoint de alcance de comando (D-MAG-10): todas las escrituras y
    auditorias del comando, o ninguna."""
    try:
        with sesion.conexion.transaction():  # savepoint de alcance de comando (D-MAG-10)
            escrituras()
    except _AbortarComando as abortado:
        return abortado.rechazo
    return None


# ------------------------------------------------------------------ auditoria
def _auditar_magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    auditoria.registrar(
        sesion,
        tabla=TABLA_MAGNITUDES,
        registro_id=magnitud_id,
        accion=auditoria.ACCION_CREAR if operacion == "ALTA" else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes,
        datos_despues_json=repo.snapshot_magnitud(sesion, magnitud_id),
        motivo=MOTIVOS[operacion],
    )


def _auditar_asociacion(sesion: SesionMotor, asociacion_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    eliminar = operacion == "RETIRAR"
    auditoria.registrar(
        sesion,
        tabla=TABLA_ASOCIACIONES,
        registro_id=asociacion_id,
        accion=(ACCION_ELIMINAR if eliminar
                else auditoria.ACCION_CREAR if operacion == "ASOCIAR" else auditoria.ACCION_ACTUALIZAR),
        datos_antes_json=antes,
        datos_despues_json=None if eliminar else repo.snapshot_asociacion(sesion, asociacion_id),
        motivo=MOTIVOS[operacion],
    )


# ------------------------------------------------------------------ utilidades
def _colision(sesion: SesionMotor, nombre: str, excluir: uuid.UUID | None) -> tuple[uuid.UUID, bool] | None:
    clave = normalizar(nombre)
    for mid, existente, enabled in repo.nombres(sesion):
        if mid != excluir and normalizar(existente) == clave:
            return mid, enabled
    return None


def _ficha(sesion: SesionMotor, magnitud_id: uuid.UUID) -> dict[str, Any]:
    ficha = repo.leer_magnitud(sesion, magnitud_id)
    assert ficha is not None
    return ficha


def _escribir_orden(sesion: SesionMotor, persistidas: list[dict[str, Any]], objetivo: list[uuid.UUID]) -> list[uuid.UUID]:
    """Escribe orden = posicion en `objetivo` solo en las filas cuyo orden cambia,
    con una auditoria ACTUALIZAR MAG_ORDEN por fila (dentro del comando)."""
    actual = {a["asociacion_id"]: a["orden"] for a in persistidas}
    cambian = [(aid, pos) for pos, aid in enumerate(objetivo) if actual[aid] != pos]
    for aid, pos in cambian:
        antes = repo.snapshot_asociacion(sesion, aid)
        _escribir(sesion, lambda aid=aid, pos=pos: repo.actualizar_asociacion(sesion, aid, {"orden": pos}))
        _auditar_asociacion(sesion, aid, "ORDEN", antes)
    return [aid for aid, _ in cambian]


def _categoria_bloqueada(sesion: SesionMotor, categoria_id: uuid.UUID) -> bool:
    """FOR NO KEY UPDATE de la categoria (existe y es del owner; habilitada o no: P1)."""
    return repo_cat.leer(sesion, categoria_id, bloquear=True) is not None


def _identidad_valida(persistidas: list[dict[str, Any]], asociacion_id, magnitud_id, obligatoria_actual) -> dict | None:
    a = next((x for x in persistidas if x["asociacion_id"] == asociacion_id), None)
    if a is None or a["magnitud_id"] != magnitud_id or a["obligatoria"] != obligatoria_actual:
        return None
    return a


def _asociacion_id_del_alta(magnitud_id: uuid.UUID, categoria_id: uuid.UUID) -> uuid.UUID:
    """Identidad derivada de la asociacion creada por el alta rapida (AJ-S7MAGIMPL-02)."""
    return uuid.uuid5(magnitud_id, f"asociacion:{categoria_id}")


def _vista(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a[k] for k in ("asociacion_id", "magnitud_id", "obligatoria", "orden")}


# ------------------------------------------------------------------ comandos de asociaciones
def asociar(sesion: SesionMotor, *, categoria_id: uuid.UUID, obligatoria: bool,
            magnitud_id: uuid.UUID | None = None, nueva: dict[str, Any] | None = None
            ) -> ResultadoAsociacion | Rechazo:
    """EXISTENTE (magnitud_id) o NUEVA (nueva = {magnitud_id, nombre,
    unidad_default, precision_decimales}): alta rapida + asociacion atomicas."""
    repo_cat.tomar_advisory(sesion)
    if not _categoria_bloqueada(sesion, categoria_id):
        return Rechazo(NO_ENCONTRADO)
    if nueva is None:
        mid = magnitud_id
        magnitud = repo.leer_magnitud(sesion, mid, bloquear=True)
        if magnitud is None:
            # Ajena o inexistente: no se distingue (no revela otros owners).
            return Rechazo(MAGNITUD_NO_ADMITIDA)
    else:
        mid = nueva["magnitud_id"]
        if not (nombre_magnitud_valido(nueva["nombre"]) and unidad_valida(nueva["unidad_default"])
                and precision_valida(nueva["precision_decimales"])):
            return Rechazo(ENTRADA_INVALIDA)
        visible = nombre_visible(nueva["nombre"])
        unidad = nombre_visible(nueva["unidad_default"])
        magnitud = repo.leer_magnitud(sesion, mid, bloquear=True)
    persistidas = repo.asociaciones(sesion, categoria_id)
    existente = next((a for a in persistidas if a["magnitud_id"] == mid), None)
    # NUEVA: identidad derivada de la intencion; EXISTENTE: aleatoria (AJ-S7MAGIMPL-02).
    asociacion_id = _asociacion_id_del_alta(mid, categoria_id) if nueva is not None else uuid.uuid4()
    if nueva is not None:
        if magnitud is not None:
            # AJ-S4-05: la identidad de intencion ya se uso; idempotente solo si
            # la magnitud y LA asociacion creada por el alta (id derivado) siguen
            # como las dejo; el orden no cuenta (D39).
            igual = (
                magnitud["row_version"] == 1 and magnitud["nombre"] == visible
                and magnitud["unidad_default"] == unidad
                and magnitud["precision_decimales"] == nueva["precision_decimales"] and magnitud["enabled"]
                and existente is not None and existente["asociacion_id"] == asociacion_id
                and existente["obligatoria"] == obligatoria
            )
            if not igual:
                return Rechazo(IDENTIDAD_REUTILIZADA)
            return ResultadoAsociacion(categoria_id, _vista(existente), magnitud, idempotente=True)
        colision = _colision(sesion, visible, None)
        if colision is not None:
            return Rechazo(NOMBRE_DUPLICADO, {"magnitud_id": str(colision[0]), "enabled": colision[1]})
    elif existente is not None:
        if existente["obligatoria"] != obligatoria:
            return Rechazo(ASOCIACION_YA_EXISTE)
        return ResultadoAsociacion(categoria_id, _vista(existente), magnitud, idempotente=True)
    if len(persistidas) > ORDEN_MAXIMO:
        return Rechazo(ENTRADA_INVALIDA)

    modificadas: list[uuid.UUID] = []

    def escrituras() -> None:
        if nueva is not None:
            _escribir(sesion, lambda: repo.insertar_magnitud(
                sesion, magnitud_id=mid, nombre=visible, unidad_default=unidad,
                precision_decimales=nueva["precision_decimales"]))
            _auditar_magnitud(sesion, mid, "ALTA", None)
            modificadas.append(mid)
        modificadas.extend(_escribir_orden(sesion, persistidas, [a["asociacion_id"] for a in persistidas]))
        _escribir(sesion, lambda: repo.insertar_asociacion(
            sesion, asociacion_id=asociacion_id, categoria_id=categoria_id, magnitud_id=mid,
            obligatoria=obligatoria, orden=len(persistidas)))
        _auditar_asociacion(sesion, asociacion_id, "ASOCIAR", None)
        modificadas.append(asociacion_id)

    rechazo = _comando(sesion, escrituras)
    if rechazo is not None:
        return rechazo
    asociacion = {"asociacion_id": asociacion_id, "magnitud_id": mid, "obligatoria": obligatoria,
                  "orden": len(persistidas)}
    return ResultadoAsociacion(categoria_id, asociacion, _ficha(sesion, mid), modificadas=tuple(modificadas))


def cambiar_obligatoria(sesion: SesionMotor, *, categoria_id: uuid.UUID, asociacion_id: uuid.UUID,
                        magnitud_id: uuid.UUID, obligatoria_actual: bool, obligatoria: bool
                        ) -> ResultadoAsociacion | Rechazo:
    """Guarda prospectiva (AJ-C07-04): nunca revalida ni reinterpreta hecho_magnitudes."""
    repo_cat.tomar_advisory(sesion)
    if not _categoria_bloqueada(sesion, categoria_id):
        return Rechazo(NO_ENCONTRADO)
    magnitud = repo.leer_magnitud(sesion, magnitud_id, bloquear=True)
    persistidas = repo.asociaciones(sesion, categoria_id)
    a = None if magnitud is None else _identidad_valida(persistidas, asociacion_id, magnitud_id, obligatoria_actual)
    if a is None:
        return Rechazo(ASOCIACION_NO_EXISTE)
    if a["obligatoria"] == obligatoria:
        return ResultadoAsociacion(categoria_id, _vista(a), magnitud, idempotente=True)
    modificadas: list[uuid.UUID] = []

    def escrituras() -> None:
        modificadas.extend(_escribir_orden(sesion, persistidas, [x["asociacion_id"] for x in persistidas]))
        antes = repo.snapshot_asociacion(sesion, asociacion_id)
        _escribir(sesion, lambda: repo.actualizar_asociacion(sesion, asociacion_id, {"obligatoria": obligatoria}))
        _auditar_asociacion(sesion, asociacion_id, "OBLIGATORIA", antes)
        modificadas.append(asociacion_id)

    rechazo = _comando(sesion, escrituras)
    if rechazo is not None:
        return rechazo
    posicion = [x["asociacion_id"] for x in persistidas].index(asociacion_id)
    asociacion = {"asociacion_id": asociacion_id, "magnitud_id": magnitud_id, "obligatoria": obligatoria,
                  "orden": posicion}
    return ResultadoAsociacion(categoria_id, asociacion, magnitud, modificadas=tuple(dict.fromkeys(modificadas)))


def retirar(sesion: SesionMotor, *, categoria_id: uuid.UUID, asociacion_id: uuid.UUID, magnitud_id: uuid.UUID,
            obligatoria_actual: bool) -> ResultadoAsociaciones | Rechazo:
    """DELETE legitimo de la asociacion (no de la magnitud ni de su historia,
    R-09) y compactacion 0..n-2 de las restantes en el mismo comando."""
    repo_cat.tomar_advisory(sesion)
    if not _categoria_bloqueada(sesion, categoria_id):
        return Rechazo(NO_ENCONTRADO)
    magnitud = repo.leer_magnitud(sesion, magnitud_id, bloquear=True)
    persistidas = repo.asociaciones(sesion, categoria_id)
    if magnitud is None or _identidad_valida(persistidas, asociacion_id, magnitud_id, obligatoria_actual) is None:
        return Rechazo(ASOCIACION_NO_EXISTE)
    restantes = [x for x in persistidas if x["asociacion_id"] != asociacion_id]
    modificadas: list[uuid.UUID] = []

    def escrituras() -> None:
        antes = repo.snapshot_asociacion(sesion, asociacion_id)
        _escribir(sesion, lambda: repo.eliminar_asociacion(sesion, asociacion_id))
        _auditar_asociacion(sesion, asociacion_id, "RETIRAR", antes)
        modificadas.append(asociacion_id)
        modificadas.extend(_escribir_orden(sesion, restantes, [x["asociacion_id"] for x in restantes]))

    rechazo = _comando(sesion, escrituras)
    if rechazo is not None:
        return rechazo
    return ResultadoAsociaciones(categoria_id, tuple(_vista(x) for x in repo.asociaciones(sesion, categoria_id)),
                                 modificadas=tuple(modificadas))


def reordenar(sesion: SesionMotor, *, categoria_id: uuid.UUID,
              asociaciones: list[tuple[uuid.UUID, uuid.UUID, int, bool]]) -> ResultadoAsociaciones | Rechazo:
    """`asociaciones`: [(asociacion_id, magnitud_id, orden, obligatoria)] en el
    orden deseado; debe ser el conjunto COMPLETO persistido (con su orden y
    obligatoria actuales). El orden objetivo es la posicion 0..n-1."""
    repo_cat.tomar_advisory(sesion)
    if not _categoria_bloqueada(sesion, categoria_id):
        return Rechazo(NO_ENCONTRADO)
    if not asociaciones or len(asociaciones) > ORDEN_MAXIMO + 1:
        return Rechazo(ENTRADA_INVALIDA)
    persistidas = repo.asociaciones(sesion, categoria_id)
    repo.bloquear_magnitudes(sesion, [a["magnitud_id"] for a in persistidas])
    esperado = [(aid, mid, orden, oblig) for aid, mid, orden, oblig in asociaciones]
    real = {(a["asociacion_id"], a["magnitud_id"], a["orden"], a["obligatoria"]) for a in persistidas}
    ids = [x[0] for x in esperado]
    # Sin distinguir falta, sobra, recreada, otro orden u otra obligatoriedad.
    if len(set(ids)) != len(ids) or set(esperado) != real:
        return Rechazo(CONJUNTO_DESFASADO)
    actual = {a["asociacion_id"]: a["orden"] for a in persistidas}
    if all(actual[aid] == pos for pos, aid in enumerate(ids)):
        return ResultadoAsociaciones(categoria_id, tuple(_vista(a) for a in persistidas), idempotente=True)
    modificadas: list[uuid.UUID] = []

    def escrituras() -> None:
        modificadas.extend(_escribir_orden(sesion, persistidas, ids))

    rechazo = _comando(sesion, escrituras)
    if rechazo is not None:
        return rechazo
    return ResultadoAsociaciones(categoria_id, tuple(_vista(x) for x in repo.asociaciones(sesion, categoria_id)),
                                 modificadas=tuple(modificadas))


# ------------------------------------------------------------------ comandos de la magnitud
def _magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID, row_version: int) -> dict[str, Any] | Rechazo:
    fila = repo.leer_magnitud(sesion, magnitud_id, bloquear=True)
    if fila is None:
        return Rechazo(NO_ENCONTRADO)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def _actualizar(sesion: SesionMotor, magnitud_id: uuid.UUID, cambios: dict[str, Any], operacion: str
                ) -> ResultadoMagnitud | Rechazo:
    def escrituras() -> None:
        antes = repo.snapshot_magnitud(sesion, magnitud_id)
        _escribir(sesion, lambda: repo.actualizar_magnitud(sesion, magnitud_id, cambios))
        _auditar_magnitud(sesion, magnitud_id, operacion, antes)

    rechazo = _comando(sesion, escrituras)
    if rechazo is not None:
        return rechazo
    return ResultadoMagnitud(_ficha(sesion, magnitud_id), modificadas=(magnitud_id,))


def renombrar(sesion: SesionMotor, *, magnitud_id: uuid.UUID, nombre: str, row_version: int
              ) -> ResultadoMagnitud | Rechazo:
    """Corrige la denominacion de la magnitud en todas sus categorias (CE-S7MAG-04)."""
    repo_cat.tomar_advisory(sesion)
    magnitud = _magnitud(sesion, magnitud_id, row_version)
    if isinstance(magnitud, Rechazo):
        return magnitud
    if not nombre_magnitud_valido(nombre):
        return Rechazo(ENTRADA_INVALIDA)
    visible = nombre_visible(nombre)
    if visible == magnitud["nombre"]:
        return ResultadoMagnitud(magnitud, idempotente=True)
    colision = _colision(sesion, visible, magnitud_id)
    if colision is not None:
        return Rechazo(NOMBRE_DUPLICADO, {"magnitud_id": str(colision[0]), "enabled": colision[1]})
    return _actualizar(sesion, magnitud_id, {"nombre": visible}, "RENOMBRAR")


def deshabilitar(sesion: SesionMotor, *, magnitud_id: uuid.UUID, row_version: int,
                 confirmacion_impacto: list[uuid.UUID] | None) -> ResultadoMagnitud | Rechazo:
    """No elimina asociaciones ni altera hechos. Si hay categorias habilitadas
    con asociacion obligatoria, exige confirmar ese conjunto EXACTO, calculado
    bajo el lock de la magnitud (CE-S7MAG-03/07)."""
    repo_cat.tomar_advisory(sesion)
    magnitud = _magnitud(sesion, magnitud_id, row_version)
    if isinstance(magnitud, Rechazo):
        return magnitud
    if not magnitud["enabled"]:
        return ResultadoMagnitud(magnitud, idempotente=True)
    impacto = repo.categorias_obligatorias_habilitadas(sesion, magnitud_id)
    if set(confirmacion_impacto or ()) != {c["categoria_id"] for c in impacto}:
        return Rechazo(REQUIERE_CONFIRMACION, {"categorias_no_capturables": [
            {"categoria_id": str(c["categoria_id"]), "nombre": c["nombre"], "obligatoria": c["obligatoria"]}
            for c in impacto]})
    return _actualizar(sesion, magnitud_id, {"enabled": False}, "DESHABILITAR")


def rehabilitar(sesion: SesionMotor, *, magnitud_id: uuid.UUID, row_version: int) -> ResultadoMagnitud | Rechazo:
    """Accion elegida por el usuario, nunca automatica (D-MAG-05)."""
    repo_cat.tomar_advisory(sesion)
    magnitud = _magnitud(sesion, magnitud_id, row_version)
    if isinstance(magnitud, Rechazo):
        return magnitud
    if magnitud["enabled"]:
        return ResultadoMagnitud(magnitud, idempotente=True)
    return _actualizar(sesion, magnitud_id, {"enabled": True}, "REHABILITAR")
