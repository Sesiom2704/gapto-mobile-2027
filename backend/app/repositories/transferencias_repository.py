# ============================================================
# GAPTO MOBILE 2027
# Fichero: transferencias_repository.py
# Ruta: backend/app/repositories/transferencias_repository.py
# Descripcion: F04-06 / B1. Acceso a `gapto.transferencias` para OP-10.
#
#   LA TABLA NO REFERENCIA AL HECHO. Solo guarda el par de movimientos. El
#   vinculo entre el hecho TRANSFERENCIA y su transferencia existe UNICAMENTE a
#   traves de las dos conciliaciones de `hecho_movimientos_tesoreria`. Es una
#   propiedad del contrato fisico de 0040, no una omision, y por eso la lectura
#   "la transferencia de este hecho" pasa siempre por ese puente.
#
#   AUTORIDAD FISICA CONSUMIDA, NO REIMPLEMENTADA:
#   - `uq_transferencias__movimiento_salida` y `__movimiento_entrada` (0080)
#     impiden que un movimiento participe en dos transferencias;
#   - `trg_transferencias__estructura` (DEFERRABLE INITIALLY DEFERRED) valida
#     salida<0, entrada>0, cuentas distintas, mismo owner e igualdad absoluta
#     en misma moneda, bloqueando ambas patas con FOR NO KEY UPDATE en orden
#     LEAST/GREATEST;
#   - `trg_movimientos_tesoreria__padre_dependencias` (0270) revalida la
#     estructura desde el lado del padre ante UPDATE de importe, estado o
#     cuenta_id.
#
#   El servicio prevalida para producir errores funcionales legibles, pero la
#   ultima palabra la tiene PostgreSQL al COMMIT. Aqui no se duplica ninguna de
#   esas comprobaciones como segunda fuente de verdad.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA = "transferencias"

TIPOS_SQL_TRANSFERENCIA: dict[str, str] = {
    "id": "uuid",
    "movimiento_salida_id": "uuid",
    "movimiento_entrada_id": "uuid",
    "notas": "text",
}


def _snapshot_desde_fila(alias: str) -> sql.Composed:
    partes: list[sql.Composed] = []
    for columna in TIPOS_SQL_TRANSFERENCIA:
        partes.append(
            sql.SQL("{}, to_jsonb({}.{})").format(
                sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
            )
        )
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def insertar_si_no_existe(
    sesion: SesionMotor,
    *,
    transferencia_id: uuid.UUID,
    movimiento_salida_id: uuid.UUID,
    movimiento_entrada_id: uuid.UUID,
    notas: str | None,
) -> str | None:
    """INSERT idempotente por identidad reservada.

    Devuelve el snapshot JSON si la fila se creo aqui; None si el UUID ya
    estaba ocupado. `ON CONFLICT DO NOTHING` no lee la fila en conflicto, de
    modo que no distingue "no existe" de "es de otro tenant": esa opacidad es
    deliberada y es la misma de OP-01.
    """
    consulta = sql.SQL(
        """
        INSERT INTO gapto.transferencias (
            id, movimiento_salida_id, movimiento_entrada_id, notas)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila(TABLA))
    fila = sesion.uno(
        consulta,
        (transferencia_id, movimiento_salida_id, movimiento_entrada_id, notas),
    )
    return None if fila is None else fila[0]


def leer(sesion: SesionMotor, transferencia_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        """
        SELECT t.id, t.movimiento_salida_id, t.movimiento_entrada_id, t.notas
          FROM gapto.transferencias t
         WHERE t.id = %s::uuid
        """,
        (transferencia_id,),
    )
    if fila is None:
        return None
    return {
        "id": fila[0],
        "movimiento_salida_id": fila[1],
        "movimiento_entrada_id": fila[2],
        "notas": fila[3],
    }


def creacion_previa_coincide(
    sesion: SesionMotor,
    *,
    transferencia_id: uuid.UUID,
    movimiento_salida_id: uuid.UUID,
    movimiento_entrada_id: uuid.UUID,
) -> bool:
    """True si la fila existente es EXACTAMENTE la misma intencion.

    Se comparan solo las dos patas: `notas` es texto libre y no forma parte de
    la identidad economica de la transferencia. Distinguir un reintento de la
    misma operacion de otra operacion que casualmente comparte datos es
    requisito del mandato, y el par de movimientos es lo que la determina.
    """
    fila = sesion.uno(
        """
        SELECT t.movimiento_salida_id = %s::uuid
           AND t.movimiento_entrada_id = %s::uuid
          FROM gapto.transferencias t
         WHERE t.id = %s::uuid
        """,
        (movimiento_salida_id, movimiento_entrada_id, transferencia_id),
    )
    return bool(fila and fila[0])


def transferencia_de_movimiento(
    sesion: SesionMotor, movimiento_id: uuid.UUID
) -> dict[str, Any] | None:
    """Transferencia en la que participa un movimiento, en cualquiera de las
    dos patas.

    Un movimiento participa como maximo en una (UNIQUE de 0080), de modo que
    devolver una sola fila no pierde informacion.
    """
    fila = sesion.uno(
        """
        SELECT t.id, t.movimiento_salida_id, t.movimiento_entrada_id
          FROM gapto.transferencias t
         WHERE t.movimiento_salida_id = %s::uuid
            OR t.movimiento_entrada_id = %s::uuid
        """,
        (movimiento_id, movimiento_id),
    )
    if fila is None:
        return None
    return {
        "id": fila[0],
        "movimiento_salida_id": fila[1],
        "movimiento_entrada_id": fila[2],
    }


def contexto_de_movimientos(
    sesion: SesionMotor, salida_id: uuid.UUID, entrada_id: uuid.UUID
) -> dict[str, Any] | None:
    """Importe, cuenta, owner y moneda de las dos patas, para PREVALIDAR.

    Bloquea ambas filas con FOR NO KEY UPDATE en orden LEAST/GREATEST, el mismo
    que usan `fn_check_transferencia_estructura` y la revalidacion parent-side
    de 0270. Tomar aqui otro orden introduciria un ciclo de espera con esos
    triggers, que son los que cierran la operacion al COMMIT.

    Devuelve None si alguna pata no es visible: el tenant llega por RLS y una
    pata ajena simplemente no existe para esta sesion.
    """
    sesion.uno(
        """
        SELECT 1 FROM gapto.movimientos_tesoreria
         WHERE id = LEAST(%s::uuid, %s::uuid) FOR NO KEY UPDATE
        """,
        (salida_id, entrada_id),
    )
    sesion.uno(
        """
        SELECT 1 FROM gapto.movimientos_tesoreria
         WHERE id = GREATEST(%s::uuid, %s::uuid) FOR NO KEY UPDATE
        """,
        (salida_id, entrada_id),
    )
    fila = sesion.uno(
        """
        SELECT s.importe, s.cuenta_id, cs.owner_user_id, cs.moneda, s.estado,
               e.importe, e.cuenta_id, ce.owner_user_id, ce.moneda, e.estado
          FROM gapto.movimientos_tesoreria s
          JOIN gapto.cuentas cs ON cs.id = s.cuenta_id
          JOIN gapto.movimientos_tesoreria e ON e.id = %s::uuid
          JOIN gapto.cuentas ce ON ce.id = e.cuenta_id
         WHERE s.id = %s::uuid
        """,
        (entrada_id, salida_id),
    )
    if fila is None:
        return None
    return {
        "salida": {
            "importe": fila[0],
            "cuenta_id": fila[1],
            "owner_user_id": fila[2],
            "moneda": fila[3],
            "estado": fila[4],
        },
        "entrada": {
            "importe": fila[5],
            "cuenta_id": fila[6],
            "owner_user_id": fila[7],
            "moneda": fila[8],
            "estado": fila[9],
        },
    }
