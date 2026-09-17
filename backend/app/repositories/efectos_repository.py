# ============================================================
# GAPTO MOBILE 2027
# Fichero: efectos_repository.py
# Ruta: backend/app/repositories/efectos_repository.py
# Descripcion: Acceso SQL a gapto.hecho_efectos y gapto.efecto_atribuciones
#   para OP-04 y OP-05.
#
#   Mantiene las mismas tres decisiones estructurales de F04-01, por las mismas
#   razones: el owner nunca viaja como parametro (RLS lo impone via las policies
#   derivadas del hecho), los snapshots viajan como TEXTO JSON generado y
#   consumido por PostgreSQL —un round-trip por float destruiria la exactitud de
#   numeric(18,4) y arruinaria la comparacion de idempotencia—, y la comparacion
#   de intencion se hace con jsonb EN SQL, que iguala numeros por valor.
#
#   Nota sobre `uq_efecto_atribuciones__efecto_actor UNIQUE (efecto_id, actor_id)`:
#   fisicamente un actor solo puede tener UNA fila por efecto. Eso encaja con el
#   contrato de OP-05, donde enriquecer significa anadir actores todavia no
#   declarados y nunca reescribir el importe de uno ya materializado.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_EFECTOS = "hecho_efectos"
TABLA_ATRIBUCIONES = "efecto_atribuciones"

TIPOS_SQL_EFECTO: dict[str, str] = {
    "id": "uuid",
    "hecho_id": "uuid",
    "tipo_efecto": "varchar",
    "importe_delta": "numeric",
    "categoria_id": "uuid",
    "estado_atribucion": "varchar",
    "descripcion": "varchar",
}

TIPOS_SQL_ATRIBUCION: dict[str, str] = {
    "id": "uuid",
    "efecto_id": "uuid",
    "actor_id": "uuid",
    "importe_atribuido": "numeric",
    "porcentaje_aplicado": "numeric",
    "criterio_atribucion": "varchar",
}


def _snapshot_desde_fila(alias: str, columnas: dict[str, str]) -> sql.Composed:
    partes = [
        sql.SQL("{}, {}.{}").format(
            sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
        )
        for columna in columnas
    ]
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def _jsonb_desde_valores(
    valores: dict[str, Any], columnas: dict[str, str]
) -> tuple[sql.Composed, list[Any]]:
    partes: list[sql.Composed] = []
    params: list[Any] = []
    for columna, valor in valores.items():
        partes.append(
            sql.SQL("{}, %s::{}").format(
                sql.Literal(columna), sql.SQL(columnas[columna])
            )
        )
        params.append(valor)
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes)), params


# ------------------------------------------------------------------
# Efectos
# ------------------------------------------------------------------

def insertar_efecto_si_no_existe(
    sesion: SesionMotor,
    hecho_id: uuid.UUID,
    *,
    efecto_id: uuid.UUID,
    tipo_efecto: str,
    importe_delta: Any,
    estado_atribucion: str,
    categoria_id: uuid.UUID | None,
    descripcion: str | None,
) -> tuple[str, str] | None:
    """INSERT idempotente por identidad reservada.

    Devuelve (estado_atribucion, snapshot_json) si se creo aqui; None si el
    UUID ya estaba ocupado. `ON CONFLICT DO NOTHING` no necesita leer la fila en
    conflicto, de modo que funciona tambien cuando pertenece a otro tenant.
    """
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_efectos (
            id, hecho_id, tipo_efecto, importe_delta, categoria_id,
            estado_atribucion, descripcion)
        VALUES (%s::uuid, %s::uuid, %s::varchar, %s::numeric, %s::uuid,
                %s::varchar, %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING estado_atribucion, ({})::text
        """
    ).format(_snapshot_desde_fila("hecho_efectos", TIPOS_SQL_EFECTO))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                efecto_id,
                hecho_id,
                tipo_efecto,
                importe_delta,
                categoria_id,
                estado_atribucion,
                descripcion,
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def creacion_efecto_previa_coincide(
    sesion: SesionMotor, valores: dict[str, Any]
) -> bool:
    """True si la auditoria CREAR de ese efecto corresponde a la misma intencion.

    Se compara contra el snapshot DE CREACION, no contra el estado actual: si el
    efecto ya paso de PARCIAL a COMPLETA por un OP-05 posterior, un reintento
    tardio del alta seguiria siendo el mismo alta.
    """
    snapshot_sql, params = _jsonb_desde_valores(valores, TIPOS_SQL_EFECTO)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues = ({})
          FROM gapto.auditoria a
         WHERE a.tabla = 'hecho_efectos'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, valores["id"]))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def leer_efecto(
    sesion: SesionMotor, efecto_id: uuid.UUID
) -> tuple[uuid.UUID, str, Any, str, str] | None:
    """(hecho_id, tipo_efecto, importe_delta, estado_atribucion, snapshot_json).

    None incluye deliberadamente "pertenece a otro tenant": RLS lo oculta y el
    motor no intenta distinguirlo.
    """
    consulta = sql.SQL(
        """
        SELECT e.hecho_id, e.tipo_efecto, e.importe_delta, e.estado_atribucion,
               ({})::text
          FROM gapto.hecho_efectos e
         WHERE e.id = %s::uuid
        """
    ).format(_snapshot_desde_fila("e", TIPOS_SQL_EFECTO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (efecto_id,))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1], fila[2], fila[3], fila[4])


def actualizar_estado_efecto(
    sesion: SesionMotor, efecto_id: uuid.UUID, estado: str
) -> str | None:
    """Cambia `estado_atribucion` y devuelve el snapshot posterior."""
    consulta = sql.SQL(
        """
        UPDATE gapto.hecho_efectos AS e
           SET estado_atribucion = %s::varchar
         WHERE e.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila("e", TIPOS_SQL_EFECTO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (estado, efecto_id))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def tiene_efectos(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.hecho_efectos e WHERE e.hecho_id = %s::uuid)",
        (hecho_id,),
    )
    return bool(fila and fila[0])


# ------------------------------------------------------------------
# Atribuciones
# ------------------------------------------------------------------

def insertar_atribucion_si_no_existe(
    sesion: SesionMotor,
    *,
    atribucion_id: uuid.UUID,
    efecto_id: uuid.UUID,
    actor_id: uuid.UUID,
    importe_atribuido: Any,
    criterio_atribucion: str,
    porcentaje_aplicado: Any,
) -> str | None:
    """INSERT idempotente. None si el UUID reservado ya estaba ocupado."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.efecto_atribuciones (
            id, efecto_id, actor_id, importe_atribuido, porcentaje_aplicado,
            criterio_atribucion)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::numeric, %s::numeric,
                %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila("efecto_atribuciones", TIPOS_SQL_ATRIBUCION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                atribucion_id,
                efecto_id,
                actor_id,
                importe_atribuido,
                porcentaje_aplicado,
                criterio_atribucion,
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def creacion_atribucion_previa_coincide(
    sesion: SesionMotor, valores: dict[str, Any]
) -> bool:
    snapshot_sql, params = _jsonb_desde_valores(valores, TIPOS_SQL_ATRIBUCION)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues = ({})
          FROM gapto.auditoria a
         WHERE a.tabla = 'efecto_atribuciones'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, valores["id"]))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def resumen_atribuciones(sesion: SesionMotor, efecto_id: uuid.UUID) -> tuple[int, Any]:
    """(numero de filas, suma de importes) del efecto, bajo RLS."""
    fila = sesion.uno(
        "SELECT count(*), COALESCE(sum(importe_atribuido), 0) "
        "FROM gapto.efecto_atribuciones WHERE efecto_id = %s::uuid",
        (efecto_id,),
    )
    return (0, 0) if fila is None else (fila[0], fila[1])


def actores_ya_atribuidos(
    sesion: SesionMotor, efecto_id: uuid.UUID
) -> set[uuid.UUID]:
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            "SELECT actor_id FROM gapto.efecto_atribuciones WHERE efecto_id = %s::uuid",
            (efecto_id,),
        )
        return {fila[0] for fila in cursor.fetchall()}


def actores_visibles(
    sesion: SesionMotor, actor_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Actores del tenant. Un actor de otro owner simplemente no aparece."""
    if not actor_ids:
        return set()
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM gapto.actores_financieros WHERE id = ANY(%s::uuid[])",
            (actor_ids,),
        )
        return {fila[0] for fila in cursor.fetchall()}
