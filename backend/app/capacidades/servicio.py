# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/capacidades/servicio.py
# Descripcion: Writer UNICO de gapto.cuenta_capacidades (F05-06 M4; F05
#   §51.2, §51.4 AJ-F0506P-09; F05 §49.13 DEU-F05-CAPACIDADES-UI; DB Schema
#   §23; decisiones PD-1..PD-3 del mandato M4). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#
#   Operaciones: activar(cuenta, capacidad, row_version) y
#   desactivar(cuenta, capacidad, row_version). Editables solo las cuatro
#   capacidades del registro (PAGAR_GASTO, RECIBIR_INGRESO, TRANSFERIR_SALIDA,
#   TRANSFERIR_ENTRADA). DOMICILIAR y COMPRA_TARJETA -> CAPACIDAD_NO_EDITABLE
#   (PD-3; P-CAP-02: solo lectura en v1). Codigo fuera del catalogo ->
#   ENTRADA_INVALIDA.
#
#   Secuencia, en UNA transaccion de UnidadDeTrabajo (retry completo ante
#   40P01/40001):
#     1. cuenta FOR NO KEY UPDATE: el MISMO modo y el MISMO orden que la
#        confirmacion del registro (cuenta -> fila de capacidad; F05 §46.4
#        R4, elegibilidad_cuentas.py v0.2.0). El registro que ya tiene la
#        cuenta hace esperar a este writer y viceversa; ninguno pide la
#        cuenta teniendo la capacidad, asi que no hay ciclo;
#     2. existencia y owner (RLS + GUC del tenant; el owner no es parametro).
#        Inexistente u oculta -> CUENTA_NO_ENCONTRADA, sin distinguir;
#     3. estado: deshabilitada o con fecha_cierre ->
#        OPERACION_NO_PERMITIDA_EN_ESTADO (PD-2);
#     4. cuentas.row_version distinta de la enviada -> VERSION_DESFASADA
#        (PD-1), sin escribir;
#     5. estado pedido igual al actual -> idempotente, sin escribir ni
#        auditar;
#     6. INSERT o DELETE de la fila -> UPDATE cuentas (row_version + 1,
#        updated_at) -> fn_registrar_auditoria (tabla cuentas, registro =
#        la cuenta, ACTUALIZAR, antes/despues con capacidad, permitida y
#        row_version; motivo F05-06 CAPACIDAD ACTIVAR|DESACTIVAR).
#   Sin locks sobre plantillas ni preferencias y sin reasignarlas (D-CAP-03):
#   el impacto se lee sin lock (lecturas.impacto). Ninguna capacidad se
#   deduce del tipo, la naturaleza o el nombre de la cuenta (D-CAP-04, H2).
#   El cambio afecta solo a operaciones nuevas (DB Schema §23): no toca
#   hechos, movimientos ni efectos.
# Version: 0.1.0 (F05-06 M4 F1)
# ============================================================

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.capacidades import lecturas
from app.core.unidad_trabajo import SesionMotor
from app.repositories import auditoria_repository as auditoria

#: Capacidades que el registro consume (F05 §46.4 R1) y que M4 permite editar.
EDITABLES = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA")
#: Capacidades de solo lectura en v1 (P-CAP-02).
NO_EDITABLES = ("COMPRA_TARJETA", "DOMICILIAR")

MOTIVOS = {True: "F05-06 CAPACIDAD ACTIVAR", False: "F05-06 CAPACIDAD DESACTIVAR"}

CUENTA_NO_ENCONTRADA = "CUENTA_NO_ENCONTRADA"
CAPACIDAD_NO_EDITABLE = "CAPACIDAD_NO_EDITABLE"
NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    cuenta: dict[str, Any]
    idempotente: bool


def validar_capacidad(capacidad: str) -> Rechazo | None:
    """Catalogo y editabilidad; sin acceso a la base."""
    if capacidad in NO_EDITABLES:
        return Rechazo(CAPACIDAD_NO_EDITABLE)
    if capacidad not in EDITABLES:
        return Rechazo(ENTRADA_INVALIDA)
    return None


def _bloquear_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID) -> tuple | None:
    return sesion.uno(
        "SELECT enabled, fecha_cierre, row_version FROM gapto.cuentas WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE",
        (cuenta_id,),
    )


def _permitida(sesion: SesionMotor, cuenta_id: uuid.UUID, capacidad: str) -> bool:
    return sesion.uno("SELECT 1 FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = %s",
                      (cuenta_id, capacidad)) is not None


def _snapshot(capacidad: str, permitida: bool, row_version: int) -> str:
    return json.dumps({"capacidad_codigo": capacidad, "permitida": permitida, "row_version": row_version})


def cambiar(sesion: SesionMotor, *, cuenta_id: uuid.UUID, capacidad: str, permitir: bool,
            row_version: int) -> Resultado | Rechazo:
    """Unico punto de escritura de cuenta_capacidades (ver cabecera)."""
    rechazo = validar_capacidad(capacidad)
    if rechazo is not None:
        return rechazo
    fila = _bloquear_cuenta(sesion, cuenta_id)
    if fila is None:
        return Rechazo(CUENTA_NO_ENCONTRADA)
    enabled, fecha_cierre, version = fila
    if not enabled or fecha_cierre is not None:
        return Rechazo(NO_PERMITIDA_EN_ESTADO)
    if version != row_version:
        return Rechazo(VERSION_DESFASADA)
    actual = _permitida(sesion, cuenta_id, capacidad)
    if actual == permitir:
        return Resultado(cuenta=lecturas.detalle(sesion, cuenta_id), idempotente=True)
    if permitir:
        sesion.ejecutar("INSERT INTO gapto.cuenta_capacidades (cuenta_id, capacidad_codigo) VALUES (%s, %s)",
                        (cuenta_id, capacidad))
    else:
        sesion.ejecutar("DELETE FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = %s",
                        (cuenta_id, capacidad))
    sesion.ejecutar("UPDATE gapto.cuentas SET row_version = row_version + 1, updated_at = now() WHERE id = %s",
                    (cuenta_id,))
    auditoria.registrar(
        sesion, tabla="cuentas", registro_id=cuenta_id, accion=auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=_snapshot(capacidad, actual, version),
        datos_despues_json=_snapshot(capacidad, permitir, version + 1),
        motivo=MOTIVOS[permitir],
    )
    return Resultado(cuenta=lecturas.detalle(sesion, cuenta_id), idempotente=False)


def activar(sesion: SesionMotor, *, cuenta_id: uuid.UUID, capacidad: str, row_version: int) -> Resultado | Rechazo:
    return cambiar(sesion, cuenta_id=cuenta_id, capacidad=capacidad, permitir=True, row_version=row_version)


def desactivar(sesion: SesionMotor, *, cuenta_id: uuid.UUID, capacidad: str,
               row_version: int) -> Resultado | Rechazo:
    return cambiar(sesion, cuenta_id=cuenta_id, capacidad=capacidad, permitir=False, row_version=row_version)
