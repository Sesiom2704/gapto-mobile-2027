# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_registro.py
# Ruta: backend/app/api/ejecucion_registro.py
# Descripcion: Ejecucion transaccional del registro por tipo de F05-04 (J2
#   §1.7; F05 §46.3 A3/A4/A5/A6, §46.4 R1/R3/R4; F05-D032 C2/C3/C6). «Ingreso
#   cobrado» (C-14 via OP-22 adscrito) y «Entre cuentas» (OP-10 adscrito).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10. Las piezas
#   compartidas con el gasto (contexto, tercero, fecha) viven aqui y las usa
#   tambien ejecucion_gasto_pagado.py.
#
#   UNA transaccion del adaptador (UnidadDeTrabajo, retry completo ante
#   40P01/40001) con el ORDEN DE LOCKS VINCULANTE (C2, R4):
#     [advisory INVERSIONES, solo si hay contexto: OP-22 lo tomara al escribir
#      hecho_entidades y el trigger D-080 al COMMIT; tomarlo ANTES que las
#      cuentas evita la inversion cuenta -> INVERSIONES]
#     -> cuentas FOR NO KEY UPDATE (1; o 2 en ORDER BY id, el mismo orden
#        LEAST/GREATEST de los triggers de OP-10)
#     -> categoria FOR SHARE (guarda C-a por tipo) -> C07 FOR SHARE
#     -> tercero / contexto FOR SHARE
#     -> OP-22 / OP-10 adscritos.
#   Ningun advisory de catalogo (CATEGORIAS, PREFERENCIAS, PLANTILLAS,
#   TERCEROS, CONTEXTOS): el registro no serializa la gestion de maestros.
#
#   Identidad ANTES que revalidacion (como §16.5): si la intencion ya esta
#   materializada se delega en OP-22/OP-10 (o en la guarda de replay propia)
#   sin revalidar el estado actual; un hecho valido no se rechaza despues.
#   Intencion nueva, ya bajo los locks, en orden fijo:
#     FECHA_FUTURA (hoy del owner) -> cuenta(s) por la regla unica R1
#     (MISMA_CUENTA, MONEDA_INVALIDA, CUENTA_DESCONOCIDA) -> C-a -> C07 ->
#     tercero (TERCERO_NO_DISPONIBLE) -> contexto (CONTEXTO_NO_DISPONIBLE).
#   Los rechazos de capa F05 se devuelven como valor (sin escritura previa).
#
#   OP-10: su replay solo compara las seis identidades y el par de
#   movimientos (J1). La guarda de replay propia compara ademas importe,
#   cuentas, fecha y nota canonicalizada con lo persistido; cualquier
#   diferencia -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.7)
# Version: 0.2.0 (F05-03/F05-04 J2 §3, L5): la regla R1 bajo el lock toma
#   tambien FOR SHARE de la fila de capacidad (cuenta -> capacidad).
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass
from typing import Any

from app.api.captura_magnitudes import validar_magnitudes
from app.api.dto_registro import IntencionIngresoCobrado, IntencionTransferencia
from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.api.traductor_registro import componer_ingreso, componer_transferencia
from app.api.traductor_gasto_pagado import leer_actor_self
from app.comun.elegibilidad_cuentas import MONEDA, motivo_cuenta
from app.comun.fecha_funcional import CODIGO_FECHA_FUTURA, Reloj, es_futura, reloj_sistema
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import hechos_repository as repo_hechos
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla
from app.services.transferencias_service import TransferenciasService

CODIGO_TERCERO_NO_DISPONIBLE = "TERCERO_NO_DISPONIBLE"
CODIGO_CONTEXTO_NO_DISPONIBLE = "CONTEXTO_NO_DISPONIBLE"


@dataclass(frozen=True, slots=True)
class RechazoRegistro:
    codigo: str


@dataclass(frozen=True, slots=True)
class Registrado:
    hecho_id: uuid.UUID
    idempotente: bool
    estado_atribucion: str | None


# ------------------------------------------------------------------ piezas comunes
def tomar_inversiones(sesion: SesionMotor) -> None:
    """Advisory INVERSIONES del owner (D-080), ANTES de cualquier row lock."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def bloquear_cuentas(sesion: SesionMotor, *cuentas: uuid.UUID) -> None:
    """FOR NO KEY UPDATE de las cuentas visibles en ORDER BY id."""
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id FROM gapto.cuentas WHERE id = ANY(%s) ORDER BY id FOR NO KEY UPDATE",
                    (sorted(set(cuentas)),))
        cur.fetchall()


def rechazo_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID, operacion: str, fecha) -> None:
    """Regla unica R1 bajo el lock: MONEDA -> MONEDA_INVALIDA; otro motivo ->
    CUENTA_DESCONOCIDA (codigos F04 ya traducidos por la API)."""
    motivo = motivo_cuenta(sesion, cuenta_id, operacion, fecha, bloquear=True)
    if motivo == MONEDA:
        raise ErrorMotor(CodigoError.MONEDA_INVALIDA, "Solo se admite una cuenta en EUR.")
    if motivo is not None:
        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta no existe o no esta disponible.")


def validar_tercero(sesion: SesionMotor, tercero_id: uuid.UUID | None) -> str | None:
    """FOR SHARE del tercero; del owner y habilitado (R3)."""
    if tercero_id is None:
        return None
    fila = sesion.uno(
        "SELECT enabled FROM gapto.terceros WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE", (tercero_id,))
    return None if fila is not None and fila[0] else CODIGO_TERCERO_NO_DISPONIBLE


def validar_contexto(sesion: SesionMotor, contexto_id: uuid.UUID | None) -> str | None:
    """FOR SHARE de la entidad CONTEXTO; del owner y habilitada (R3)."""
    if contexto_id is None:
        return None
    fila = sesion.uno(
        "SELECT enabled, tipo_entidad FROM gapto.entidades WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE", (contexto_id,))
    return None if fila is not None and fila[0] and fila[1] == "CONTEXTO" else CODIGO_CONTEXTO_NO_DISPONIBLE


def validar_categoria_y_magnitudes(sesion: SesionMotor, categoria_id, tipo: str, magnitudes,
                                   desconocidas) -> str | None:
    if categoria_id is None:
        return None
    rechazo = validar_seleccion_categoria(sesion, categoria_id, tipo)
    if rechazo is not None:
        return rechazo
    return validar_magnitudes(sesion, categoria_id, magnitudes, desconocidas)


def _op22(sesion: SesionMotor) -> HechosCompuestosService:
    return HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)


# ------------------------------------------------------------------ ingreso cobrado
def registrar_ingreso_cobrado(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                              intencion: IntencionIngresoCobrado,
                              reloj: Reloj = reloj_sistema) -> Registrado | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Registrado | RechazoRegistro:
        if intencion.contexto_id is not None:
            tomar_inversiones(sesion)
        bloquear_cuentas(sesion, intencion.cuenta_id)
        actor = leer_actor_self(sesion)
        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None
        if not ya_materializada:
            if es_futura(sesion, intencion.fecha_hecho, reloj):
                return RechazoRegistro(CODIGO_FECHA_FUTURA)
            rechazo_cuenta(sesion, intencion.cuenta_id, "INGRESO", intencion.fecha_hecho)
            rechazo = (
                validar_categoria_y_magnitudes(sesion, intencion.categoria_id, "INGRESO", intencion.magnitudes,
                                               intencion.magnitudes_desconocidas)
                or validar_tercero(sesion, intencion.tercero_id)
                or validar_contexto(sesion, intencion.contexto_id)
            )
            if rechazo is not None:
                return RechazoRegistro(rechazo)
        datos = componer_ingreso(intencion, actor)
        r = _op22(sesion).registrar_hecho_compuesto(contexto, datos)
        return Registrado(hecho_id=r.hecho_id, idempotente=r.idempotente,
                          estado_atribucion=datos.efectos[0].estado_atribucion)

    return unidad.ejecutar(contexto, operacion, nombre="F05-04 ingreso_cobrado (locks + OP-22)")


# ------------------------------------------------------------------ entre cuentas (OP-10)
def _replay_transferencia(sesion: SesionMotor, intencion: IntencionTransferencia) -> bool:
    """True si lo persistido para el hecho de la intencion describe EXACTAMENTE
    la misma transferencia (guarda propia; C3)."""
    fila = sesion.uno(
        "SELECT h.importe_total, h.fecha_hecho, h.concepto, h.moneda, t.codigo, "
        "ms.cuenta_id, me.cuenta_id, ms.importe, me.importe, ms.descripcion, me.descripcion "
        "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id "
        "JOIN gapto.transferencias tr ON tr.movimiento_salida_id IN ("
        " SELECT hm.movimiento_tesoreria_id FROM gapto.hecho_movimientos_tesoreria hm WHERE hm.hecho_id = h.id) "
        "JOIN gapto.movimientos_tesoreria ms ON ms.id = tr.movimiento_salida_id "
        "JOIN gapto.movimientos_tesoreria me ON me.id = tr.movimiento_entrada_id "
        "WHERE h.id = %s",
        (intencion.intencion_id,),
    )
    if fila is None:
        return False
    x = intencion.importe.quantize(decimal.Decimal("0.0001"))
    return (
        fila[4] == "TRANSFERENCIA" and fila[0] == x and fila[1] == intencion.fecha_hecho
        and fila[2] == intencion.nota and fila[3] == intencion.moneda
        and fila[5] == intencion.cuenta_origen_id and fila[6] == intencion.cuenta_destino_id
        and fila[7] == -x and fila[8] == x and fila[9] == intencion.nota and fila[10] == intencion.nota
    )


def registrar_transferencia(unidad: UnidadDeTrabajo, contexto: ContextoOperacion,
                            intencion: IntencionTransferencia,
                            reloj: Reloj = reloj_sistema) -> Registrado | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Registrado | RechazoRegistro:
        bloquear_cuentas(sesion, intencion.cuenta_origen_id, intencion.cuenta_destino_id)
        if repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None:
            if not _replay_transferencia(sesion, intencion):
                raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                                 "Esta transferencia ya existe con otros datos.")
        else:
            if es_futura(sesion, intencion.fecha_hecho, reloj):
                return RechazoRegistro(CODIGO_FECHA_FUTURA)
            if intencion.cuenta_origen_id == intencion.cuenta_destino_id:
                raise ErrorMotor(CodigoError.MISMA_CUENTA, "Origen y destino deben ser cuentas distintas.")
            rechazo_cuenta(sesion, intencion.cuenta_origen_id, "TRANSFERENCIA_ORIGEN", intencion.fecha_hecho)
            rechazo_cuenta(sesion, intencion.cuenta_destino_id, "TRANSFERENCIA_DESTINO", intencion.fecha_hecho)
        r = TransferenciasService(UnidadDeTrabajoAdscrita(sesion)).transferir(
            contexto, componer_transferencia(intencion))
        return Registrado(hecho_id=r.hecho_id, idempotente=r.idempotente, estado_atribucion=None)

    return unidad.ejecutar(contexto, operacion, nombre="F05-04 transferencia (locks + OP-10)")
