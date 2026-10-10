# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/plantillas/repositorio.py
# Descripcion: Acceso a datos de plantillas de registro y acciones rapidas
#   (F05-03 J2 §1.6; F05 §45.3 A1/A2, §45.4 R3; F05-D032 C2, D-032.2). UNICO
#   escritor runtime de gapto.plantillas_registro y gapto.acciones_rapidas:
#   solo INSERT y UPDATE; ningun DELETE (lifecycle por `enabled`). Todas las
#   escrituras las invoca servicio.py DESPUES de `tomar_advisory`.
#   - row_version y updated_at los mantiene esta capa.
#   - El owner nunca es parametro (GUC). La garantia de mismo owner de las
#     referencias (plantilla -> categoria/tercero/entidad/cuenta; accion ->
#     plantilla) es la RLS WITH CHECK EXISTS(owner) con FORCE RLS (D-099,
#     D-032.2): una referencia ajena falla con 42501 tambien en UPDATE.
#   - Bloqueo de varias filas SIEMPRE en orden de id (UUID ascendente, R3).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

COLUMNAS_PLANTILLA = (
    "id", "nombre", "tipo_hecho_id", "categoria_id", "tercero_id", "entidad_id", "cuenta_default_id",
    "presupuestable_default", "enabled", "row_version",
)
COLUMNAS_ACCION = ("id", "nombre", "plantilla_registro_id", "orden", "icono_key", "enabled", "row_version")

_SELECT_PLANTILLA = (
    "SELECT id, nombre, tipo_hecho_id, categoria_id, tercero_id, entidad_id, cuenta_default_id, "
    "presupuestable_default, enabled, row_version FROM gapto.plantillas_registro "
    "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_SELECT_ACCION = (
    "SELECT id, nombre, plantilla_registro_id, orden, icono_key, enabled, row_version FROM gapto.acciones_rapidas "
    "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)

#: Columnas que los comandos pueden modificar. Nunca id ni owner.
EDITABLES_PLANTILLA = frozenset({
    "nombre", "tipo_hecho_id", "categoria_id", "tercero_id", "entidad_id", "cuenta_default_id",
    "presupuestable_default", "enabled",
})
EDITABLES_ACCION = frozenset({"nombre", "orden", "icono_key", "enabled"})


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory transaccional (PLANTILLAS, owner): plantillas -> acciones (R3)."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:PLANTILLAS'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def _p(f: tuple) -> dict[str, Any]:
    return dict(zip(COLUMNAS_PLANTILLA, f))


def _a(f: tuple) -> dict[str, Any]:
    return dict(zip(COLUMNAS_ACCION, f))


# ------------------------------------------------------------------ plantillas
def leer_plantilla(sesion: SesionMotor, plantilla_id: uuid.UUID, *, bloquear: bool = False) -> dict | None:
    sql = _SELECT_PLANTILLA + " AND id = %s" + (" FOR NO KEY UPDATE" if bloquear else "")
    fila = sesion.uno(sql, (plantilla_id,))
    return None if fila is None else _p(fila)


def plantillas(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT_PLANTILLA + " ORDER BY id")
        return [_p(f) for f in cur.fetchall()]


def snapshot_plantilla(sesion: SesionMotor, plantilla_id: uuid.UUID) -> str:
    fila = sesion.uno("SELECT row_to_json(p)::text FROM gapto.plantillas_registro p WHERE p.id = %s",
                      (plantilla_id,))
    assert fila is not None
    return fila[0]


def insertar_plantilla(sesion: SesionMotor, *, plantilla_id: uuid.UUID, v: dict[str, Any]) -> None:
    sesion.uno(
        "INSERT INTO gapto.plantillas_registro (id, owner_user_id, nombre, tipo_hecho_id, categoria_id, tercero_id, "
        "entidad_id, cuenta_default_id, presupuestable_default) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (plantilla_id, v["nombre"], v["tipo_hecho_id"], v["categoria_id"], v["tercero_id"], v["entidad_id"],
         v["cuenta_default_id"], v["presupuestable_default"]),
    )


def actualizar_plantilla(sesion: SesionMotor, plantilla_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    if not cambios or not set(cambios) <= EDITABLES_PLANTILLA:
        raise ValueError(f"columnas no editables: {sorted(set(cambios) - EDITABLES_PLANTILLA)}")
    columnas = sorted(cambios)
    sesion.uno(
        "UPDATE gapto.plantillas_registro SET " + ", ".join(f"{c} = %s" for c in columnas)
        + ", row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (plantilla_id,),
    )


# ------------------------------------------------------------------ acciones rapidas
def leer_accion(sesion: SesionMotor, accion_id: uuid.UUID, *, bloquear: bool = False) -> dict | None:
    sql = _SELECT_ACCION + " AND id = %s" + (" FOR NO KEY UPDATE" if bloquear else "")
    fila = sesion.uno(sql, (accion_id,))
    return None if fila is None else _a(fila)


def acciones(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT_ACCION + " ORDER BY orden, id")
        return [_a(f) for f in cur.fetchall()]


def acciones_habilitadas_bloqueadas(sesion: SesionMotor) -> list[dict[str, Any]]:
    """Acciones habilitadas del owner, FOR NO KEY UPDATE en orden de id."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT_ACCION + " AND enabled ORDER BY id FOR NO KEY UPDATE")
        return [_a(f) for f in cur.fetchall()]


def acciones_de_plantilla_bloqueadas(sesion: SesionMotor, plantilla_id: uuid.UUID) -> list[dict[str, Any]]:
    """Acciones HABILITADAS de una plantilla, FOR NO KEY UPDATE en orden de id."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT_ACCION + " AND plantilla_registro_id = %s AND enabled ORDER BY id FOR NO KEY UPDATE",
                    (plantilla_id,))
        return [_a(f) for f in cur.fetchall()]


def snapshot_accion(sesion: SesionMotor, accion_id: uuid.UUID) -> str:
    fila = sesion.uno("SELECT row_to_json(a)::text FROM gapto.acciones_rapidas a WHERE a.id = %s", (accion_id,))
    assert fila is not None
    return fila[0]


def insertar_accion(sesion: SesionMotor, *, accion_id: uuid.UUID, nombre: str, plantilla_id: uuid.UUID,
                    orden: int, icono_key: str | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.acciones_rapidas (id, owner_user_id, nombre, plantilla_registro_id, orden, icono_key) "
        "VALUES (%s, current_setting('gapto.owner_user_id')::uuid, %s, %s, %s, %s) RETURNING id",
        (accion_id, nombre, plantilla_id, orden, icono_key),
    )


def actualizar_accion(sesion: SesionMotor, accion_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    if not cambios or not set(cambios) <= EDITABLES_ACCION:
        raise ValueError(f"columnas no editables: {sorted(set(cambios) - EDITABLES_ACCION)}")
    columnas = sorted(cambios)
    sesion.uno(
        "UPDATE gapto.acciones_rapidas SET " + ", ".join(f"{c} = %s" for c in columnas)
        + ", row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (accion_id,),
    )
