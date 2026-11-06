# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/propiedades/repositorio.py
# Descripcion: Acceso a datos de propiedades (F06-01 B1; contratos R1 v0.8
#   Parte I). Entidad PROPIEDAD + subtipo `propiedades`, titularidad en
#   `entidad_participaciones` y `propiedad_valoraciones`. SQL puro.
#   - Solo INSERT y UPDATE: runtime no tiene DELETE en participaciones ni en
#     valoraciones (0200, 0230). Una titularidad se cierra con vigente_hasta.
#   - row_version del agregado = el de la entidad; toda escritura en sus
#     hijas la incrementa en la misma transaccion (v0.8 §1.4).
#   - El owner nunca es parametro (GUC); la RLS hace el resto. Un id de otro
#     owner no es visible: se trata como inexistente.
#   - Nivel 2 del orden de locks (v0.8 §1.4): FOR NO KEY UPDATE de la
#     entidad PROPIEDAD antes de leer participaciones o valoraciones.
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor

TRIGGERS_SUBTIPO = "gapto.trg_entidades__subtipo_unico, gapto.trg_propiedades__subtipo_unico"

#: Columnas de `propiedades` que escribe B1 (direccion y salida: fuera de B1).
COLUMNAS_PROPIEDAD = (
    "tipo_propiedad", "fecha_adquisicion", "superficie_m2", "superficie_construida_m2", "habitaciones",
    "banos", "tiene_garaje", "tiene_trastero", "referencia_catastral", "incluir_en_rentabilidad", "notas",
)
COLUMNAS_LECTURA = COLUMNAS_PROPIEDAD + ("fecha_salida_patrimonio",)

_SNAPSHOT = (
    "SELECT json_build_object('entidad', row_to_json(e), 'propiedad', row_to_json(p), "
    "'participaciones', (SELECT coalesce(json_agg(row_to_json(x) ORDER BY x.vigente_desde, x.actor_id), '[]'::json) "
    "FROM gapto.entidad_participaciones x WHERE x.entidad_id = e.id), "
    "'valoraciones', (SELECT coalesce(json_agg(row_to_json(v) ORDER BY v.id), '[]'::json) "
    "FROM gapto.propiedad_valoraciones v WHERE v.propiedad_entidad_id = e.id))::text "
    "FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s"
)


def actor_self(sesion: SesionMotor) -> uuid.UUID | None:
    fila = sesion.uno(
        "SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid"
    )
    return None if fila is None else fila[0]


def existe_entidad(sesion: SesionMotor, entidad_id: uuid.UUID) -> bool:
    """Cualquier entidad del owner con ese id (de cualquier tipo)."""
    return sesion.uno(
        "SELECT 1 FROM gapto.entidades WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (entidad_id,)
    ) is not None


def bloquear(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    """Nivel 2: FOR NO KEY UPDATE de la entidad PROPIEDAD del owner."""
    fila = sesion.uno(
        "SELECT e.row_version, e.enabled, p.fecha_adquisicion FROM gapto.entidades e "
        "JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s AND e.tipo_entidad = 'PROPIEDAD' "
        "AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE OF e",
        (entidad_id,),
    )
    return None if fila is None else {"row_version": fila[0], "enabled": fila[1], "fecha_adquisicion": fila[2]}


_SELECT = (
    "SELECT e.id, e.nombre, e.enabled, e.row_version, " + ", ".join(f"p.{c}" for c in COLUMNAS_LECTURA)
    + " FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id "
    "WHERE e.tipo_entidad = 'PROPIEDAD' AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_CLAVES = ("id", "nombre", "enabled", "row_version") + COLUMNAS_LECTURA


def leer(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(_SELECT + " AND e.id = %s", (entidad_id,))
    return None if fila is None else dict(zip(_CLAVES, fila))


def listar(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY e.nombre, e.id")
        return [dict(zip(_CLAVES, f)) for f in cur.fetchall()]


def participaciones(sesion: SesionMotor, entidad_id: uuid.UUID, *, bloquear_filas: bool = False) -> list[dict[str, Any]]:
    """Todas las filas de titularidad con su actor y tercero (FOR UPDATE por id si se van a cerrar)."""
    sufijo = " ORDER BY x.id FOR UPDATE OF x" if bloquear_filas else " ORDER BY x.vigente_desde, x.actor_id"
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT x.id, x.actor_id, a.tercero_id, t.nombre, x.porcentaje, x.vigente_desde, x.vigente_hasta "
            "FROM gapto.entidad_participaciones x JOIN gapto.actores_financieros a ON a.id = x.actor_id "
            "LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE x.entidad_id = %s" + sufijo, (entidad_id,))
        claves = ("id", "actor_id", "tercero_id", "nombre", "porcentaje", "vigente_desde", "vigente_hasta")
        return [dict(zip(claves, f)) for f in cur.fetchall()]


def snapshot(sesion: SesionMotor, entidad_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (entidad_id,))
    assert fila is not None
    return fila[0]


def insertar_propiedad(sesion: SesionMotor, *, entidad_id: uuid.UUID, nombre: str, datos: dict[str, Any]) -> None:
    sesion.uno(
        "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, 'PROPIEDAD', %s) RETURNING id",
        (entidad_id, nombre),
    )
    columnas = ("entidad_id",) + COLUMNAS_PROPIEDAD
    sesion.uno(
        f"INSERT INTO gapto.propiedades ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) "
        "RETURNING entidad_id",
        (entidad_id,) + tuple(datos[c] for c in COLUMNAS_PROPIEDAD),
    )


def actualizar_propiedad(sesion: SesionMotor, entidad_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE de nombre (entidad) y de columnas de `propiedades`; las claves vienen de listas cerradas."""
    if "nombre" in cambios:
        sesion.ejecutar("UPDATE gapto.entidades SET nombre = %s, updated_at = now() WHERE id = %s",
                        (cambios["nombre"], entidad_id))
    columnas = [c for c in COLUMNAS_PROPIEDAD if c in cambios]
    if columnas:
        sesion.ejecutar(
            f"UPDATE gapto.propiedades SET {', '.join(f'{c} = %s' for c in columnas)} WHERE entidad_id = %s",
            tuple(cambios[c] for c in columnas) + (entidad_id,))


def insertar_participacion(sesion: SesionMotor, *, fila_id: uuid.UUID, entidad_id: uuid.UUID,
                           actor_id: uuid.UUID, porcentaje: Decimal, desde: dt.date) -> None:
    sesion.uno(
        "INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (fila_id, entidad_id, actor_id, porcentaje, desde),
    )


def cerrar_participacion(sesion: SesionMotor, fila_id: uuid.UUID, hasta: dt.date) -> None:
    sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_hasta = %s WHERE id = %s", (hasta, fila_id))


def subir_version(sesion: SesionMotor, entidad_id: uuid.UUID) -> int:
    fila = sesion.uno(
        "UPDATE gapto.entidades SET row_version = row_version + 1, updated_at = now() WHERE id = %s "
        "RETURNING row_version", (entidad_id,))
    assert fila is not None
    return fila[0]


def max_habitacion_en_uso(sesion: SesionMotor, entidad_id: uuid.UUID) -> tuple[int | None, list[uuid.UUID]]:
    """Mayor `contratos.habitacion` de los contratos no CANCELADOS de la propiedad y sus ids (Q-CON-03 A)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT entidad_id, habitacion FROM gapto.contratos WHERE propiedad_entidad_id = %s "
            "AND estado_documental <> 'CANCELADO' AND habitacion IS NOT NULL ORDER BY entidad_id", (entidad_id,))
        filas = cur.fetchall()
    return (max((f[1] for f in filas), default=None), [f[0] for f in filas])


# ------------------------------------------------------------------ valoraciones
COLUMNAS_VALORACION = ("id", "valor_total", "fecha_valoracion", "metodo", "fuente", "notas", "moneda",
                       "propiedad_id")


def leer_valoracion(sesion: SesionMotor, valoracion_id: uuid.UUID) -> dict | None:
    fila = sesion.uno(
        "SELECT id, valor_total, fecha_valoracion, metodo, fuente, notas, moneda, propiedad_entidad_id "
        "FROM gapto.propiedad_valoraciones WHERE id = %s",
        (valoracion_id,))
    return None if fila is None else dict(zip(COLUMNAS_VALORACION, fila))


def insertar_valoracion(sesion: SesionMotor, *, valoracion_id: uuid.UUID, propiedad_id: uuid.UUID,
                        valor_total: Decimal, fecha: dt.date, metodo: str, fuente, notas) -> None:
    sesion.uno(
        "INSERT INTO gapto.propiedad_valoraciones (id, propiedad_entidad_id, fecha_valoracion, valor_total, "
        "moneda, metodo, fuente, notas) VALUES (%s, %s, %s, %s, 'EUR', %s, %s, %s) RETURNING id",
        (valoracion_id, propiedad_id, fecha, valor_total, metodo, fuente, notas),
    )


def valoraciones(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, valor_total, fecha_valoracion, metodo, fuente, notas, moneda, propiedad_entidad_id "
            "FROM gapto.propiedad_valoraciones WHERE propiedad_entidad_id = %s "
            "ORDER BY fecha_valoracion NULLS FIRST, id", (propiedad_id,))
        return [dict(zip(COLUMNAS_VALORACION, f)) for f in cur.fetchall()]


# ------------------------------------------------------------------ idempotencia (auditoria por request_id)
def auditorias_de_intencion(sesion: SesionMotor, intencion_id: uuid.UUID) -> list[dict[str, Any]]:
    """Auditoria visible (RLS por owner) escrita con request_id = intencion_id."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT tabla, registro_id, motivo, datos_despues::text FROM gapto.auditoria WHERE request_id = %s "
            "ORDER BY created_at, id", (intencion_id,))
        return [dict(zip(("tabla", "registro_id", "motivo", "despues"), f)) for f in cur.fetchall()]
