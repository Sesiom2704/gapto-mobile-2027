# ============================================================
# GAPTO MOBILE 2027
# Fichero: participantes_repository.py
# Ruta: backend/app/repositories/participantes_repository.py
# Descripcion: Acceso a `gapto.hecho_participantes` (F04-D038 §9).
#
#   La tabla existe desde 0040 con UNIQUE fisica (hecho_id, actor_id, rol) y
#   RLS, pero no tenia writer. F04-07 lo activa.
#
#   `rol` es vocabulario DELIBERADAMENTE EXTENSIBLE segun DB Schema: no hay
#   CHECK ni catalogo fisico, y no se crea ninguno. El conjunto de codigos
#   admitidos lo decide el motor por version y se valida en el servicio.
# Version: 0.2.0
#   0.2.0 (F04-D038 enmienda §11): `eliminar_participante`, retirada local
#   de una asociacion que nunca fue verdadera. Devuelve el snapshot previo
#   porque, tras el DELETE, es la unica prueba que queda de que esa fila
#   existio como captura erronea.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_PARTICIPANTES = "hecho_participantes"

TIPOS_SQL_PARTICIPANTE: dict[str, str] = {
    "id": "uuid",
    "hecho_id": "uuid",
    "actor_id": "uuid",
    "rol": "varchar",
}


def _snapshot_desde_fila(alias: str, columnas: dict[str, str]) -> sql.Composed:
    partes = [
        sql.SQL("{}, {}.{}").format(
            sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
        )
        for columna in columnas
    ]
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def insertar_participante_si_no_existe(
    sesion: SesionMotor,
    *,
    participante_id: uuid.UUID,
    hecho_id: uuid.UUID,
    actor_id: uuid.UUID,
    rol: str,
) -> str | None:
    """INSERT idempotente por identidad reservada.

    Devuelve el snapshot si se creo aqui; None si el UUID ya estaba ocupado.
    `ON CONFLICT DO NOTHING` no necesita leer la fila en conflicto, de modo que
    funciona tambien cuando pertenece a otro tenant.
    """
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_participantes (id, hecho_id, actor_id, rol)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila("hecho_participantes", TIPOS_SQL_PARTICIPANTE))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (participante_id, hecho_id, actor_id, rol))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_participante(
    sesion: SesionMotor, participante_id: uuid.UUID
) -> tuple[Any, ...] | None:
    """Devuelve (hecho_id, actor_id, rol) o None si no es visible."""
    return sesion.uno(
        "SELECT hecho_id, actor_id, rol FROM gapto.hecho_participantes "
        "WHERE id = %s::uuid",
        (participante_id,),
    )


def participacion_existente(
    sesion: SesionMotor, *, hecho_id: uuid.UUID, actor_id: uuid.UUID, rol: str
) -> uuid.UUID | None:
    """Identidad de la fila que ya ocupa la terna logica, si existe."""
    fila = sesion.uno(
        "SELECT id FROM gapto.hecho_participantes "
        "WHERE hecho_id = %s::uuid AND actor_id = %s::uuid AND rol = %s::varchar",
        (hecho_id, actor_id, rol),
    )
    return None if fila is None else fila[0]


def recuento_identificados(sesion: SesionMotor, hecho_id: uuid.UUID) -> int:
    """PERSONAS distintas, no filas.

    Un mismo actor con dos roles es una sola persona. Contar filas inflaria el
    recuento y haria fallar la guarda del total por un motivo inventado.
    """
    fila = sesion.uno(
        "SELECT count(DISTINCT actor_id) FROM gapto.hecho_participantes "
        "WHERE hecho_id = %s::uuid",
        (hecho_id,),
    )
    return 0 if fila is None else int(fila[0])


def total_declarado(sesion: SesionMotor, hecho_id: uuid.UUID) -> tuple[bool, int | None]:
    """(hecho_visible, numero_participantes_total).

    El total puede ser NULL de forma legitima: significa que el numero global
    de participantes no se conoce, no que sea cero.
    """
    fila = sesion.uno(
        "SELECT numero_participantes_total FROM gapto.hechos_financieros "
        "WHERE id = %s::uuid",
        (hecho_id,),
    )
    if fila is None:
        return (False, None)
    return (True, None if fila[0] is None else int(fila[0]))


def eliminar_participante(
    sesion: SesionMotor, *, participante_id: uuid.UUID, hecho_id: uuid.UUID
) -> str | None:
    """DELETE acotado al hecho, devolviendo el snapshot previo.

    El `hecho_id` viaja en el WHERE y no solo como comprobacion previa en
    Python: impide retirar por identidad una fila que pertenece a otro hecho
    aunque el llamante acierte el UUID. Lo que RLS no vea, no se borra.
    """
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_participantes AS hecho_participantes
         WHERE id = %s::uuid AND hecho_id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila("hecho_participantes", TIPOS_SQL_PARTICIPANTE))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (participante_id, hecho_id))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]
