# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_prevision.py
# Ruta: backend/app/api/ejecucion_prevision.py
# Descripcion: Ejecucion transaccional de la confirmacion de previsiones de
#   F05-06 M5 (F05 §59 F05-D044 decisiones 1-5 y 14; AJ-M5-DEC-01, 02, 03, 05,
#   06). API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   EXCEPCION I3 NOMINAL (decision 1; test_154 v0.29.0; ampliada por F05-D047
#   §61.3 en v0.30.0): este es el UNICO fichero de la frontera que puede
#   referenciar PrevisionesService, y solo sus metodos `vincular_realidad`,
#   `omitir`, `dar_por_realizada` y `corregir_estado_terminal`, siempre adscrito
#   a la transaccion del adaptador (UnidadDeTrabajoAdscrita). Nada de corregir
#   vinculos, retirar, cancelar, crear_manual, generar_* ni recalcular_futuras:
#   ninguna ruta crea, cancela, corrige vinculos, retira ni recalcula
#   previsiones.
#
#   «Ya lo registre» (OP-17 suelto, `vincular`):
#     vinculo_id = intencion_id; importe_asignado = importe_a_vincular (el que
#     el usuario vio); uuid_sucesor = uuid5(intencion_id, "sucesor").
#     Locks: los de OP-17 (hecho NKU -> regla FU -> prevision FU). TRAS OP-17,
#     con el hecho ya bloqueado, se relee la porcion restante del hecho: si no
#     es exactamente 0 (crecio desde la lista) -> PORCION_CAMBIADA y ROLLBACK;
#     si no es determinable -> PORCION_DE_REALIDAD_EXCEDIDA (NO_DETERMINABLE) y
#     ROLLBACK. Nunca se vincula ni mas ni menos de lo que el usuario vio y era
#     toda la porcion libre. Un replay exacto (mismo vinculo) no se relee.
#     Antes de OP-17, el tipo del hecho debe ser el de la prevision
#     (PREVISION_TIPO_DISTINTO, sin escritura; tipos inmutables).
#   «No hubo este mes» (`omitir`): row_version esperada, motivo opcional,
#     uuid_sucesor = uuid5(intencion_id, "sucesor"). Sin replay de exito: un
#     reintento sobre una OMITIDA es ESTADO_PREVISION_INCOMPATIBLE (409) y la
#     ruta devuelve el estado releido, sin escritura ni segundo sucesor.
#   Transferencia desde la prevision (opcion A, decision 2):
#     UNA UnidadDeTrabajo; dentro, `transferir_bajo_locks` (el mismo prologo de
#     registrar_transferencia: cuentas FNKU por id -> identidad -> capacidad FS
#     -> revalidaciones -> OP-10 adscrito) y despues OP-17 adscrito con
#     vinculo uuid5(intencion, "vinculo"), importe = el de la transferencia y
#     sucesor si marcar_realizada. Sin commit intermedio: un rechazo de OP-17
#     revierte tambien OP-10. Orden de adquisicion: cuentas -> capacidad ->
#     hecho (nuevo) -> movimientos (nuevos) -> regla FU -> prevision FU: el
#     mismo sufijo que OP-22 + prevision (F04-R2 §6).
#     Replay compuesto (AJ-M5-DEC-02): transferencia identica
#     (_replay_transferencia) Y vinculos del hecho = {vinculo compuesto} con la
#     misma prevision e importe (y REALIZADA si se declaro); si no ->
#     IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin escritura.
# Version: 0.1.0 (F05-06 M5 §A0/§A4)
# Version: 0.2.0 (F05-06 M5-B; F05-D047 §61.1 y §61.3; F04-D065):
#   «Dar por cubierta» (`dar_por_cubierta` -> dar_por_realizada): row_version,
#   motivo obligatorio (lo exige el motor) y uuid_sucesor = uuid5(intencion,
#   "sucesor"); sin replay de exito, como omitir. Locks: los del motor
#   ([regla FU ->] prevision FU), sin nada propio.
#   «Reabrir» (`reabrir` -> corregir_estado_terminal, sin cambios): solo
#   REALIZADA y OMITIDA; una CANCELADA se rechaza AQUI con
#   ESTADO_PREVISION_INCOMPATIBLE antes de llamar al motor (F05-D047: CANCELADA
#   fuera de la UI). Motivo y version del sucesor RODANTE (la lectura la da).
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass

from app.api.dto_prevision import IntencionDarPorCubierta, IntencionOmitir, IntencionReabrir, IntencionVincular
from app.api.dto_registro import IntencionTransferencia
from app.api.ejecucion_registro import (
    CODIGO_PREVISION_TIPO_DISTINTO,
    RechazoRegistro,
    Registrado,
    con_rechazo_capacidad,
    transferir_bajo_locks,
    validar_tipo_prevision,
)
from app.api.traductor_registro import ESCALA, uuid_sucesor, vinculo_compuesto
from app.comun.fecha_funcional import Reloj, reloj_sistema
from app.core.contexto import ContextoOperacion
from app.core.errores import ErrorMotor
from app.core.modelos_prevision import DatosVinculo
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.previsiones import lecturas as lect_prev
from app.services.previsiones_service import PrevisionesService

CODIGO_PORCION_CAMBIADA = "PORCION_CAMBIADA"
CODIGO_PORCION_EXCEDIDA = "PORCION_DE_REALIDAD_EXCEDIDA"


@dataclass(frozen=True, slots=True)
class Vinculado:
    prevision_id: uuid.UUID
    hecho_id: uuid.UUID
    importe: decimal.Decimal
    estado: str
    row_version: int
    idempotente: bool


@dataclass(frozen=True, slots=True)
class Transicion:
    prevision_id: uuid.UUID
    estado: str
    row_version: int


@dataclass(frozen=True, slots=True)
class Omitida:
    prevision_id: uuid.UUID
    estado: str
    row_version: int


class _PorcionNoCoincide(Exception):
    """Abortar tras OP-17 (ya escrito): la UnidadDeTrabajo hace ROLLBACK."""

    def __init__(self, codigo: str, detalle: dict) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.detalle = detalle


def _previsiones(sesion: SesionMotor) -> PrevisionesService:
    return PrevisionesService(UnidadDeTrabajoAdscrita(sesion))


def _como_rechazo(exc: Exception) -> RechazoRegistro | None:
    if isinstance(exc, ErrorMotor) and isinstance(exc.causa, _PorcionNoCoincide):
        return RechazoRegistro(exc.causa.codigo, exc.causa.detalle)
    return None


# ------------------------------------------------------------------ «Ya lo registre» (OP-17)
def vincular(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, prevision_id: uuid.UUID,
             intencion: IntencionVincular) -> Vinculado | RechazoRegistro:
    importe = intencion.importe_a_vincular.quantize(ESCALA)

    def operacion(sesion: SesionMotor) -> Vinculado | RechazoRegistro:
        tipo_hecho = lect_prev.tipo_de_hecho(sesion, intencion.hecho_id)
        tipo_prev = lect_prev.tipo_de_prevision(sesion, prevision_id)
        if tipo_hecho is not None and tipo_prev is not None and tipo_hecho != tipo_prev:
            return RechazoRegistro(CODIGO_PREVISION_TIPO_DISTINTO)
        r = _previsiones(sesion).vincular_realidad(
            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,
            datos=DatosVinculo(vinculo_id=intencion.intencion_id, hecho_id=intencion.hecho_id,
                               importe_asignado=importe, marcar_realizada=intencion.marcar_realizada),
            uuid_sucesor=uuid_sucesor(intencion.intencion_id))
        if not r.idempotente:
            # Con el hecho bloqueado por OP-17: lo vinculado debe ser TODA la porcion libre.
            restante = lect_prev.porcion_restante(sesion, intencion.hecho_id)
            if restante is None:
                raise _PorcionNoCoincide(CODIGO_PORCION_EXCEDIDA, {"motivo": "NO_DETERMINABLE"})
            if restante != 0:
                raise _PorcionNoCoincide(CODIGO_PORCION_CAMBIADA, {
                    "porcion_disponible": str((restante + importe).quantize(decimal.Decimal("0.01")))})
        return Vinculado(prevision_id=prevision_id, hecho_id=intencion.hecho_id, importe=importe, estado=r.estado,
                         row_version=r.row_version, idempotente=r.idempotente)

    try:
        return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5 vincular (OP-17)")
    except Exception as exc:
        rechazo = _como_rechazo(exc)
        if rechazo is None:
            raise
        return rechazo


# ------------------------------------------------------------------ «No hubo este mes»
def omitir(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, prevision_id: uuid.UUID,
           intencion: IntencionOmitir) -> Omitida:
    def operacion(sesion: SesionMotor) -> Omitida:
        r = _previsiones(sesion).omitir(
            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,
            motivo=intencion.motivo, uuid_sucesor=uuid_sucesor(intencion.intencion_id))
        return Omitida(prevision_id=prevision_id, estado=r.estado, row_version=r.row_version)

    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5 omitir")


# ------------------------------------------------------------------ «Dar por cubierta» (M5-B)
def dar_por_cubierta(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, prevision_id: uuid.UUID,
                     intencion: IntencionDarPorCubierta) -> Transicion:
    def operacion(sesion: SesionMotor) -> Transicion:
        r = _previsiones(sesion).dar_por_realizada(
            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,
            motivo=intencion.motivo,
            uuid_sucesor=uuid_sucesor(intencion.intencion_id))
        return Transicion(prevision_id=prevision_id, estado=r.estado, row_version=r.row_version)

    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5-B dar por cubierta")


# ------------------------------------------------------------------ «Reabrir» (M5-B)
CODIGO_ESTADO_INCOMPATIBLE = "ESTADO_PREVISION_INCOMPATIBLE"


def reabrir(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, prevision_id: uuid.UUID,
            intencion: IntencionReabrir) -> Transicion | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Transicion | RechazoRegistro:
        # F05-D047: una CANCELADA no se reabre desde la app (el motor si la admite, F04-D024.3).
        if lect_prev.estado_persistido(sesion, prevision_id) == "CANCELADA":
            return RechazoRegistro(CODIGO_ESTADO_INCOMPATIBLE)
        r = _previsiones(sesion).corregir_estado_terminal(
            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,
            motivo=intencion.motivo, sucesor_row_version_esperada=intencion.sucesor_row_version)
        return Transicion(prevision_id=prevision_id, estado=r.estado, row_version=r.row_version)

    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5-B reabrir")


# ------------------------------------------------------------------ transferencia desde la prevision
def registrar_transferencia_prevista(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                                     intencion: IntencionTransferencia,
                                     reloj: Reloj = reloj_sistema) -> Registrado | RechazoRegistro:
    bloque = intencion.prevision
    iid = intencion.intencion_id
    importe = intencion.importe.quantize(ESCALA)
    vinculo = vinculo_compuesto(iid)

    def replay_compuesto(sesion: SesionMotor) -> bool:
        if lect_prev.vinculos_del_hecho(sesion, iid) != {vinculo: (bloque.prevision_id, importe)}:
            return False
        return not bloque.marcar_realizada or lect_prev.estado_persistido(sesion, bloque.prevision_id) == "REALIZADA"

    def operacion(sesion: SesionMotor) -> Registrado | RechazoRegistro:
        r = transferir_bajo_locks(sesion, contexto, intencion, reloj, replay_compuesto,
                                  lambda s: validar_tipo_prevision(s, bloque, "TRANSFERENCIA"))
        if isinstance(r, RechazoRegistro) or r.idempotente:
            return r
        _previsiones(sesion).vincular_realidad(
            contexto, prevision_id=bloque.prevision_id, row_version_esperada=bloque.row_version,
            datos=DatosVinculo(vinculo_id=vinculo, hecho_id=iid, importe_asignado=importe,
                               marcar_realizada=bloque.marcar_realizada),
            uuid_sucesor=uuid_sucesor(iid) if bloque.marcar_realizada else None)
        return r

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),
                           nombre="F05-06 M5 transferencia prevista (locks + OP-10 + OP-17)")
