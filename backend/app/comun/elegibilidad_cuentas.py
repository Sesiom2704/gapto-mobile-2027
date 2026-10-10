# ============================================================
# GAPTO MOBILE 2027
# Fichero: elegibilidad_cuentas.py
# Ruta: backend/app/comun/elegibilidad_cuentas.py
# Descripcion: Contrato UNICO de elegibilidad de cuentas del registro (F05
#   §46.4 R1, AJ-F0504-02; F05-D032 C1; E1 de §46.5). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#
#   `cuenta_capacidades` es la UNICA fuente de la elegibilidad operativa:
#     GASTO «Pagado con»            -> PAGAR_GASTO
#     INGRESO «Cobrado en»          -> RECIBIR_INGRESO
#     OP-10 origen («Desde»)        -> TRANSFERIR_SALIDA
#     OP-10 destino («A»)           -> TRANSFERIR_ENTRADA
#   y ademas, en todos los casos: del owner (RLS + GUC del tenant; el owner no
#   es parametro, convencion del backend), habilitada, sin fecha_cierre
#   anterior o igual a la fecha funcional, fecha_inicio_ledger NULL o anterior
#   o igual a la fecha (regla de ledger de C1; NULL no bloquea), moneda EUR
#   (v1) y la fila de capacidad presente.
#   - Una cuenta sin la fila de capacidad NO es elegible: ningun default por
#     tipo ni por naturaleza (C1). Se retira el filtro naturaleza = 'ACTIVO'
#     (E1): una cuenta PASIVO con PAGAR_GASTO es elegible para GASTO (R2).
#   - COMPRA_TARJETA y DOMICILIAR no sustituyen ni implican PAGAR_GASTO: no
#     cuentan (R1).
#   - Ninguna preferencia ni plantilla relaja esta matriz.
#   Una sola regla para todos los consumidores: lecturas (cuentas-pago y
#   cuentas por operacion), confirmacion del registro BAJO el lock de la
#   cuenta, resolver y writers de preferencias y de plantillas.
#
#   Motivo por cuenta (primer motivo que aplica, orden fijo):
#     DESHABILITADA, CERRADA, LEDGER_POSTERIOR, MONEDA, SIN_CAPACIDAD.
#   Solo lectura y sin locks propios: la confirmacion toma antes el lock de la
#   cuenta (FOR NO KEY UPDATE) y llama a `motivo_cuenta` ya bajo el.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.1)
# Version: 0.2.0 (F05-03/F05-04 J2 §3, interleaving L5 «transferencia frente a
#   cambio de capacidad», F05 §46.4 R4): el lock de la cuenta (NO KEY UPDATE)
#   es COMPATIBLE con el DELETE de una fila de cuenta_capacidades, asi que no
#   serializa la retirada de una capacidad frente al registro. En la
#   confirmacion, `motivo_cuenta(..., bloquear=True)` toma ademas FOR SHARE de
#   la fila de capacidad (orden: cuenta -> capacidad). Un writer de
#   capacidades (deuda DEU-F05-CAPACIDADES-UI) que la borre espera al registro
#   y, a la inversa, el registro que llega despues ya no la encuentra
#   (SIN_CAPACIDAD). Sin ciclo: borrar la capacidad no bloquea la cuenta. Las
#   lecturas siguen sin locks.
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

#: Moneda del registro v1 (R1: EUR).
MONEDA_REGISTRO = "EUR"

#: Operacion -> capacidad exigida (R1, literal).
CAPACIDAD_POR_OPERACION: dict[str, str] = {
    "GASTO": "PAGAR_GASTO",
    "INGRESO": "RECIBIR_INGRESO",
    "TRANSFERENCIA_ORIGEN": "TRANSFERIR_SALIDA",
    "TRANSFERENCIA_DESTINO": "TRANSFERIR_ENTRADA",
}
OPERACIONES = frozenset(CAPACIDAD_POR_OPERACION)

DESHABILITADA = "DESHABILITADA"
CERRADA = "CERRADA"
LEDGER_POSTERIOR = "LEDGER_POSTERIOR"
MONEDA = "MONEDA"
SIN_CAPACIDAD = "SIN_CAPACIDAD"
#: Cuenta inexistente u oculta por RLS (solo en `motivo_cuenta`).
NO_ENCONTRADA = "NO_ENCONTRADA"

_SELECT = (
    "SELECT c.id, c.nombre, c.moneda, c.enabled, c.fecha_cierre, c.fecha_inicio_ledger, "
    "EXISTS (SELECT 1 FROM gapto.cuenta_capacidades k WHERE k.cuenta_id = c.id "
    "AND k.capacidad_codigo = %s) AS capacidad "
    "FROM gapto.cuentas c WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)


def _capacidad(operacion: str) -> str:
    if operacion not in CAPACIDAD_POR_OPERACION:
        raise ValueError(f"operacion de registro desconocida: {operacion!r}")
    return CAPACIDAD_POR_OPERACION[operacion]


def _motivo(fila: tuple, fecha: dt.date) -> str | None:
    _, _, moneda, enabled, fecha_cierre, inicio_ledger, capacidad = fila
    if not enabled:
        return DESHABILITADA
    if fecha_cierre is not None and fecha_cierre <= fecha:
        return CERRADA
    if inicio_ledger is not None and inicio_ledger > fecha:
        return LEDGER_POSTERIOR
    if moneda != MONEDA_REGISTRO:
        return MONEDA
    if not capacidad:
        return SIN_CAPACIDAD
    return None


def elegibilidad_cuentas(sesion: SesionMotor, operacion: str, fecha: dt.date) -> list[dict[str, Any]]:
    """Todas las cuentas del owner con su elegibilidad para `operacion` en la
    fecha funcional `fecha`: [{cuenta_id, nombre, moneda, elegible, motivo}]
    en orden estable (orden, nombre, id)."""
    capacidad = _capacidad(operacion)
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY c.orden, c.nombre, c.id", (capacidad,))
        filas = cur.fetchall()
    salida = []
    for f in filas:
        motivo = _motivo(f, fecha)
        salida.append({"cuenta_id": f[0], "nombre": f[1], "moneda": f[2], "elegible": motivo is None, "motivo": motivo})
    return salida


def cuentas_elegibles(sesion: SesionMotor, operacion: str, fecha: dt.date) -> list[tuple[uuid.UUID, str, str]]:
    """Solo las elegibles: [(id, nombre, moneda)] en el mismo orden estable."""
    return [(c["cuenta_id"], c["nombre"], c["moneda"]) for c in elegibilidad_cuentas(sesion, operacion, fecha)
            if c["elegible"]]


def motivo_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID, operacion: str, fecha: dt.date,
                  *, bloquear: bool = False) -> str | None:
    """Motivo de no elegibilidad de UNA cuenta (None = elegible). Para la
    confirmacion: se invoca con la cuenta ya bloqueada por el llamante y con
    `bloquear=True`, que toma FOR SHARE de la fila de capacidad."""
    capacidad = _capacidad(operacion)
    if bloquear:
        sesion.uno("SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = %s FOR SHARE",
                   (cuenta_id, capacidad))
    fila = sesion.uno(_SELECT + " AND c.id = %s", (capacidad, cuenta_id))
    if fila is None:
        return NO_ENCONTRADA
    return _motivo(fila, fecha)
