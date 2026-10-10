# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/preferencias/servicio.py
# Descripcion: Writers de las preferencias de registro (F05-02, F05-D026
#   §41.3/§41.4): alta, editar, desactivar y reactivar.
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Cada comando se ejecuta dentro de UNA transaccion de UnidadDeTrabajo
#   (retry completo ante 40P01/40001, D-171) con esta secuencia fija:
#     advisory (PREFERENCIAS, owner)           <- SIEMPRE lo primero
#     -> FOR NO KEY UPDATE de la fila y control de row_version (no en el alta)
#     -> validaciones de dominio (lecturas sin lock de categoria y cuenta)
#     -> regla de empate contra las habilitadas del owner (bajo el advisory)
#     -> escritura (repositorio) -> auditoria (misma transaccion).
#   Grafo de locks: advisory -> fila de preferencia. Categoria y cuenta se
#   leen sin lock: su elegibilidad al escribir es informativa y el resolver
#   la vuelve a evaluar en la fecha del registro (AJ-D025-14). El registro
#   (REG-01) nunca toma este advisory ni bloquea preferencias (§41.4).
#
#   Los rechazos de dominio se devuelven como `Rechazo` ANTES de escribir.
#   Los rechazos fisicos conocidos (CHECK «propone algo», PK) se traducen por
#   IDENTIDAD de la constraint dentro de un savepoint, nunca por el texto.
#
#   Auditoria (patron F05-01): accion CREAR en el alta; ACTUALIZAR en el
#   resto, motivo cerrado por operacion (MOTIVOS) y snapshots antes/despues.
#
#   Codigos de capa F05 (no forman parte de la taxonomia F04):
#     PREFERENCIA_SIN_VALOR, PREFERENCIA_DIMENSION_DIFERIDA,
#     PREFERENCIA_PRIORIDAD_NO_ADMITIDA, PREFERENCIA_CUENTA_NO_ELEGIBLE,
#     PREFERENCIA_CATEGORIA_NO_ELEGIBLE, PREFERENCIA_EMPATE_CONTRADICTORIO
#     (detalle: preferencia_conflicto_id).
#   F04 reutilizados: AGREGADO_NO_ENCONTRADO, VERSION_DESFASADA,
#     IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, ENTRADA_INVALIDA.
#
#   v0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3; F05-D032 C4):
#   - Ambitos v1 (R6, plano 2): tipo; tipo + categoria; tipo + tercero. El
#     writer rechaza tipo NULL (PREFERENCIA_SIN_TIPO) y categoria + tercero
#     (PREFERENCIA_AMBITO_NO_ADMITIDO). `tercero_id` es operativo (E2): del
#     owner y habilitado (si no, PREFERENCIA_TERCERO_NO_ELEGIBLE), leido sin
#     lock como la categoria. `entidad_id` sigue rechazandose con
#     PREFERENCIA_DIMENSION_DIFERIDA.
#   - Especificidad 0..3 (plano 1); la precedencia D-042 y el desempate de
#     §41.4 (plano 3) no cambian. El empate ignora las filas que el resolver
#     no consume (sin tipo o con entidad).
#   - Reactivar una fila sin tipo (solo posible por datos previos a C4 o SQL
#     directo) se rechaza con PREFERENCIA_SIN_TIPO.
#   - Comando `convertir_preferencias_sin_tipo` (C4): UNA transaccion bajo el
#     mismo advisory (PREFERENCIAS, owner) -> filas sin tipo del owner FOR NO
#     KEY UPDATE en orden de id -> UPDATE tipo_hecho_id = GASTO de TODAS
#     (habilitadas o no, con o sin categoria) -> auditoria ACTUALIZAR por fila
#     con antes/despues (motivo «F05-03 CONVERTIR_SIN_TIPO»). Nunca toca filas
#     con tipo. Repetirla no hace nada (idempotente por estado). Cualquier
#     fallo propaga y la UdT revierte TODA la conversion.
#
#   v0.3.0 (F05-03/F05-04 J2 §1.1; F05 §46.4 R1; F05-D032 C1): la cuenta
#   propuesta se valida con el contrato unico de elegibilidad para la
#   operacion del TIPO de la preferencia (INGRESO -> RECIBIR_INGRESO; GASTO y
#   el resto -> PAGAR_GASTO). Ninguna preferencia relaja la matriz.
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo
from app.preferencias.resolver import (
    CAMPOS,
    consumible,
    cuentas_elegibles_registro,
    dimension_diferida,
    especificidad,
    pueden_coincidir,
    operacion_de_tipo,
    sin_tipo,
    tipo_hecho_registro,
)
from app.repositories import auditoria_repository as auditoria

TABLA = "preferencias_registro"
#: Unica prioridad admitida en v1 (AJ-D026-04).
PRIORIDAD_V1 = 100

MOTIVOS = {
    "ALTA": "F05-02 ALTA",
    "EDITAR": "F05-02 EDITAR",
    "DESACTIVAR": "F05-02 DESACTIVAR",
    "REACTIVAR": "F05-02 REACTIVAR",
    "CONVERTIR_SIN_TIPO": "F05-03 CONVERTIR_SIN_TIPO",
}

SIN_VALOR = "PREFERENCIA_SIN_VALOR"
DIMENSION_DIFERIDA = "PREFERENCIA_DIMENSION_DIFERIDA"
PRIORIDAD_NO_ADMITIDA = "PREFERENCIA_PRIORIDAD_NO_ADMITIDA"
CUENTA_NO_ELEGIBLE = "PREFERENCIA_CUENTA_NO_ELEGIBLE"
CATEGORIA_NO_ELEGIBLE = "PREFERENCIA_CATEGORIA_NO_ELEGIBLE"
EMPATE_CONTRADICTORIO = "PREFERENCIA_EMPATE_CONTRADICTORIO"
SIN_TIPO = "PREFERENCIA_SIN_TIPO"
AMBITO_NO_ADMITIDO = "PREFERENCIA_AMBITO_NO_ADMITIDO"
TERCERO_NO_ELEGIBLE = "PREFERENCIA_TERCERO_NO_ELEGIBLE"
NO_ENCONTRADO = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

#: Identidades fisicas conocidas -> codigo estable.
_CONSTRAINTS = {
    "ck_preferencias_registro__propone_valor": SIN_VALOR,
    "pk_preferencias_registro": IDENTIDAD_REUTILIZADA,
}


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    preferencia: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoConversion:
    convertidas: tuple[uuid.UUID, ...]
    idempotente: bool


# ------------------------------------------------------------------ utilidades
def _escribir(sesion: SesionMotor, accion) -> Rechazo | None:
    """Escritura en un savepoint; traduce por identidad de constraint. Un
    fallo fisico no reconocido se propaga (error interno, sin escritura)."""
    try:
        with sesion.conexion.transaction():
            accion()
    except psycopg.Error as exc:
        codigo = _CONSTRAINTS.get(exc.diag.constraint_name)
        if codigo is None:
            raise
        return Rechazo(codigo)
    return None


def _auditar(sesion: SesionMotor, preferencia_id: uuid.UUID, operacion: str, antes: str | None) -> None:
    auditoria.registrar(
        sesion,
        tabla=TABLA,
        registro_id=preferencia_id,
        accion=auditoria.ACCION_CREAR if operacion == "ALTA" else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes,
        datos_despues_json=repo.snapshot(sesion, preferencia_id),
        motivo=MOTIVOS[operacion],
    )


def _fila(sesion: SesionMotor, preferencia_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer(sesion, preferencia_id, bloquear=True)
    if fila is None:
        return Rechazo(NO_ENCONTRADO)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def _categoria_elegible(sesion: SesionMotor, categoria_id) -> bool:
    """Del owner y habilitada. Inexistente u oculta por RLS: no elegible."""
    fila = sesion.uno(
        "SELECT enabled FROM gapto.categorias_financieras WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid",
        (categoria_id,),
    )
    return fila is not None and fila[0]


def _tercero_elegible(sesion: SesionMotor, tercero_id) -> bool:
    """Del owner y habilitado. Inexistente u oculto por RLS: no elegible."""
    fila = sesion.uno(
        "SELECT enabled FROM gapto.terceros WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid",
        (tercero_id,),
    )
    return fila is not None and fila[0]


def _hoy(sesion: SesionMotor):
    return sesion.uno("SELECT current_date")[0]


def _validar_valores(sesion: SesionMotor, v: dict[str, Any]) -> Rechazo | None:
    """Validaciones del contenido propuesto, en orden fijo."""
    if dimension_diferida(v):
        return Rechazo(DIMENSION_DIFERIDA)
    if v["prioridad"] != PRIORIDAD_V1:
        return Rechazo(PRIORIDAD_NO_ADMITIDA)
    if v["cuenta_default_id"] is None and v["presupuestable_default"] is None:
        return Rechazo(SIN_VALOR)
    if v["tipo_hecho_id"] is None:
        return Rechazo(SIN_TIPO)
    if v["categoria_id"] is not None and v["tercero_id"] is not None:
        return Rechazo(AMBITO_NO_ADMITIDO)
    if sesion.uno("SELECT 1 FROM gapto.tipos_hecho WHERE id = %s", (v["tipo_hecho_id"],)) is None:
        return Rechazo(ENTRADA_INVALIDA)
    if v["categoria_id"] is not None and not _categoria_elegible(sesion, v["categoria_id"]):
        return Rechazo(CATEGORIA_NO_ELEGIBLE)
    if v["tercero_id"] is not None and not _tercero_elegible(sesion, v["tercero_id"]):
        return Rechazo(TERCERO_NO_ELEGIBLE)
    if v["cuenta_default_id"] is not None and v["cuenta_default_id"] not in cuentas_elegibles_registro(
        sesion, _hoy(sesion), operacion_de_tipo(sesion, v["tipo_hecho_id"])
    ):
        return Rechazo(CUENTA_NO_ELEGIBLE)
    return None


def _empate(sesion: SesionMotor, v: dict[str, Any], propia: uuid.UUID) -> Rechazo | None:
    """Regla de empate de §41.4 (AJ-D026-03) contra las habilitadas del owner,
    excluida la propia: misma especificidad, misma prioridad, posibilidad de
    coincidir y el MISMO campo con valores distintos. Campos distintos no
    chocan (AJ-D026-08); mismo valor no es contradictorio. Las filas que el
    resolver no consume (entidad diferida o sin tipo, E3) no participan."""
    for q in repo.habilitadas(sesion):
        if q["id"] == propia or not consumible(q):
            continue
        if especificidad(q) != especificidad(v) or q["prioridad"] != v["prioridad"]:
            continue
        if not pueden_coincidir(v, q):
            continue
        for columna in CAMPOS.values():
            if v[columna] is not None and q[columna] is not None and v[columna] != q[columna]:
                return Rechazo(EMPATE_CONTRADICTORIO, {"preferencia_conflicto_id": q["id"]})
    return None


def _resultado(sesion: SesionMotor, preferencia_id, **kw) -> Resultado:
    return Resultado(preferencia=repo.leer(sesion, preferencia_id), **kw)


def _valores(**kw) -> dict[str, Any]:
    return {
        "tipo_hecho_id": kw["tipo_hecho_id"], "categoria_id": kw["categoria_id"],
        "tercero_id": kw["tercero_id"], "entidad_id": kw["entidad_id"],
        "cuenta_default_id": kw["cuenta_default_id"],
        "presupuestable_default": kw["presupuestable_default"], "prioridad": kw["prioridad"],
    }


_CONTENIDO = ("tipo_hecho_id", "categoria_id", "tercero_id", "cuenta_default_id", "presupuestable_default")


# ------------------------------------------------------------------ comandos
def alta(sesion: SesionMotor, *, preferencia_id, tipo_hecho_id=None, categoria_id=None, tercero_id=None,
         entidad_id=None, cuenta_default_id=None, presupuestable_default=None,
         prioridad: int = PRIORIDAD_V1) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    v = _valores(tipo_hecho_id=tipo_hecho_id, categoria_id=categoria_id, tercero_id=tercero_id,
                 entidad_id=entidad_id, cuenta_default_id=cuenta_default_id,
                 presupuestable_default=presupuestable_default, prioridad=prioridad)
    existente = repo.leer(sesion, preferencia_id)
    if existente is not None:
        # Idempotente solo si la fila sigue EXACTAMENTE como la dejo el alta
        # (row_version 1, habilitada y mismo contenido), como AJ-S4-05.
        igual = (
            existente["row_version"] == 1 and existente["enabled"]
            and all(existente[k] == v[k] for k in v)
        )
        return Resultado(preferencia=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    rechazo = _validar_valores(sesion, v) or _empate(sesion, v, preferencia_id)
    if rechazo is not None:
        return rechazo
    rechazo = _escribir(sesion, lambda: repo.insertar_preferencia(
        sesion, preferencia_id=preferencia_id, tipo_hecho_id=tipo_hecho_id, categoria_id=categoria_id,
        tercero_id=tercero_id, cuenta_default_id=cuenta_default_id,
        presupuestable_default=presupuestable_default))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, preferencia_id, "ALTA", None)
    return _resultado(sesion, preferencia_id, modificadas=(preferencia_id,))


def editar(sesion: SesionMotor, *, preferencia_id, row_version: int, tipo_hecho_id=None, categoria_id=None,
           tercero_id=None, entidad_id=None, cuenta_default_id=None, presupuestable_default=None,
           prioridad: int = PRIORIDAD_V1) -> Resultado | Rechazo:
    """Sustituye el contenido completo (claves y valores propuestos)."""
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, preferencia_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    v = _valores(tipo_hecho_id=tipo_hecho_id, categoria_id=categoria_id, tercero_id=tercero_id,
                 entidad_id=entidad_id, cuenta_default_id=cuenta_default_id,
                 presupuestable_default=presupuestable_default, prioridad=prioridad)
    rechazo = _validar_valores(sesion, v)
    if rechazo is not None:
        return rechazo
    cambios = {k: v[k] for k in _CONTENIDO if fila[k] != v[k]}
    if not cambios:
        return Resultado(preferencia=fila, idempotente=True)
    # Una desactivada no participa: el empate se evalua al reactivarla.
    if fila["enabled"]:
        # prioridad no es editable: el empate usa la persistida.
        rechazo = _empate(sesion, {**v, "prioridad": fila["prioridad"]}, preferencia_id)
        if rechazo is not None:
            return rechazo
    antes = repo.snapshot(sesion, preferencia_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_preferencia(sesion, preferencia_id, cambios))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, preferencia_id, "EDITAR", antes)
    return _resultado(sesion, preferencia_id, modificadas=(preferencia_id,))


def desactivar(sesion: SesionMotor, *, preferencia_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, preferencia_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if not fila["enabled"]:
        return Resultado(preferencia=fila, idempotente=True)
    antes = repo.snapshot(sesion, preferencia_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_preferencia(sesion, preferencia_id, {"enabled": False}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, preferencia_id, "DESACTIVAR", antes)
    return _resultado(sesion, preferencia_id, modificadas=(preferencia_id,))


def reactivar(sesion: SesionMotor, *, preferencia_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _fila(sesion, preferencia_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if fila["enabled"]:
        return Resultado(preferencia=fila, idempotente=True)
    # Una fila con dimension diferida (solo posible por SQL directo) no se
    # pone en uso: el writer no crea ni habilita esas preferencias.
    if dimension_diferida(fila):
        return Rechazo(DIMENSION_DIFERIDA)
    # E3: una fila sin tipo no se pone en uso (el resolver no la consumiria).
    if sin_tipo(fila):
        return Rechazo(SIN_TIPO)
    rechazo = _empate(sesion, fila, preferencia_id)
    if rechazo is not None:
        return rechazo
    antes = repo.snapshot(sesion, preferencia_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_preferencia(sesion, preferencia_id, {"enabled": True}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, preferencia_id, "REACTIVAR", antes)
    return _resultado(sesion, preferencia_id, modificadas=(preferencia_id,))


def convertir_preferencias_sin_tipo(sesion: SesionMotor) -> ResultadoConversion:
    """Conversion C4 de TODAS las preferencias sin tipo del owner a GASTO, en
    la transaccion de la UdT, bajo el advisory de los writers. Idempotente por
    estado: sin filas sin tipo no escribe nada."""
    repo.tomar_advisory(sesion)
    filas = repo.sin_tipo_bloqueadas(sesion)
    if not filas:
        return ResultadoConversion(convertidas=(), idempotente=True)
    gasto = tipo_hecho_registro(sesion)
    for f in filas:
        antes = repo.snapshot(sesion, f["id"])
        repo.actualizar_preferencia(sesion, f["id"], {"tipo_hecho_id": gasto})
        _auditar(sesion, f["id"], "CONVERTIR_SIN_TIPO", antes)
    return ResultadoConversion(convertidas=tuple(f["id"] for f in filas), idempotente=False)
