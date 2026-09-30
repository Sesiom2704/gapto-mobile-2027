# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/categorias/repositorio.py
# Descripcion: Acceso a datos de la gestion del arbol de categorias (F05-01,
#   S4). Es el UNICO escritor runtime de gapto.categorias_financieras
#   (inventario fail-closed C-b, test_154 I5): solo INSERT y UPDATE; ningun
#   DELETE (F05-01-R12). Todas las escrituras las invoca servicio.py DESPUES
#   de `tomar_advisory` (AJ-S4-01).
#
#   - row_version y updated_at los mantiene esta capa: 0340 no tiene trigger
#     de version sobre la tabla.
#   - El padre del mismo tenant lo garantiza la FK compuesta de 0210; la
#     aciclicidad y D-122/D-139 los triggers 0280/0285. Aqui solo se leen
#     datos para dar el error de dominio antes de escribir (AJ-S4-07).
#   - Recorridos recursivos con CYCLE: un dato legacy corrupto no cuelga la
#     consulta.
#
#   v0.2.0 (F05-01 S6-ICONO (F05-D013)): `insertar` persiste `icon_key` del
#   alta (Q6) y COLUMNAS_EDITABLES incluye `icon_key` (§27.3; F05-D013 supera
#   prospectivamente F05-D010 Q4). La validacion contra la biblioteca v1 la
#   hace el servicio antes de escribir; el CHECK de 0340 es defensa residual.
#   Sigue siendo el unico escritor runtime del catalogo; ningun DELETE.
#
#   v0.3.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): primitiva de LECTURA
#   `hijos_bloqueados` (hijos directos de un padre, NULL-safe para la raiz,
#   habilitados o no, FOR NO KEY UPDATE en orden por id) para el comando
#   `reordenar`. Ningun escritor nuevo: la reordenacion escribe con
#   `actualizar`. Cosmetico §30.6: el mensaje de `actualizar` ya no alude a S4.
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

_SNAPSHOT = (
    "SELECT row_to_json(c)::text FROM gapto.categorias_financieras c WHERE c.id = %s"
)


def tomar_advisory(sesion: SesionMotor) -> None:
    """Advisory transaccional (CATEGORIAS, owner): la MISMA clave que usan los
    triggers 0280/0285, de modo que el orden es siempre advisory -> filas."""
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'), "
        "hashtext(current_setting('gapto.owner_user_id')::uuid::text))"
    )


def leer(sesion: SesionMotor, categoria_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    sql = (
        "SELECT id, owner_user_id, parent_id, nombre, codigo, ambito, presupuestable_default, "
        "orden, enabled, icon_key, row_version FROM gapto.categorias_financieras "
        "WHERE id = %s AND owner_user_id = current_setting('gapto.owner_user_id')::uuid"
    )
    if bloquear:
        sql += " FOR NO KEY UPDATE"
    fila = sesion.uno(sql, (categoria_id,))
    if fila is None:
        return None
    claves = ("id", "owner_user_id", "parent_id", "nombre", "codigo", "ambito",
              "presupuestable_default", "orden", "enabled", "icon_key", "row_version")
    return dict(zip(claves, fila))


def snapshot(sesion: SesionMotor, categoria_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (categoria_id,))
    assert fila is not None
    return fila[0]


def hermanos_activos(
    sesion: SesionMotor, parent_id: uuid.UUID | None, excluir: uuid.UUID | None
) -> list[tuple[uuid.UUID, str]]:
    """Hermanos ACTIVOS bajo `parent_id` con comparacion NULL-safe (raiz
    incluida) y exclusion del propio nodo (AJ-S4-06)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, nombre FROM gapto.categorias_financieras "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "AND parent_id IS NOT DISTINCT FROM %s AND enabled "
            "AND id IS DISTINCT FROM %s",
            (parent_id, excluir),
        )
        return list(cur.fetchall())


def cadena_ancestros(sesion: SesionMotor, desde: uuid.UUID) -> list[tuple[uuid.UUID, bool]]:
    """`desde` y todos sus ancestros con su `enabled` (AJ-S4-03)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "WITH RECURSIVE a(id, parent_id, enabled) AS ("
            " SELECT id, parent_id, enabled FROM gapto.categorias_financieras WHERE id = %s"
            " UNION ALL"
            " SELECT c.id, c.parent_id, c.enabled FROM a"
            " JOIN gapto.categorias_financieras c ON c.id = a.parent_id"
            ") CYCLE id SET es_ciclo USING ruta "
            "SELECT id, enabled FROM a WHERE NOT es_ciclo",
            (desde,),
        )
        return list(cur.fetchall())


def subarbol(sesion: SesionMotor, raiz: uuid.UUID) -> list[uuid.UUID]:
    """TODOS los descendientes de `raiz`, habilitados o no (AJ-S4-02),
    ordenados por id. No incluye la raiz."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "WITH RECURSIVE d(id) AS ("
            " SELECT id FROM gapto.categorias_financieras WHERE parent_id = %s"
            " UNION ALL"
            " SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id"
            ") CYCLE id SET es_ciclo USING ruta "
            "SELECT DISTINCT id FROM d WHERE NOT es_ciclo ORDER BY id",
            (raiz,),
        )
        return [f[0] for f in cur.fetchall()]


def bloquear(sesion: SesionMotor, ids: list[uuid.UUID]) -> list[tuple[uuid.UUID, bool]]:
    """FOR NO KEY UPDATE en orden determinista por id."""
    if not ids:
        return []
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, enabled FROM gapto.categorias_financieras WHERE id = ANY(%s) "
            "ORDER BY id FOR NO KEY UPDATE",
            (list(ids),),
        )
        return list(cur.fetchall())


def hijos_bloqueados(sesion: SesionMotor, parent_id: uuid.UUID | None) -> list[dict[str, Any]]:
    """Hijos DIRECTOS de `parent_id` (raiz si None, comparacion NULL-safe),
    habilitados o no, con FOR NO KEY UPDATE en orden determinista por id
    (S6-ORDEN: el conjunto persistido se compara bajo el advisory)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, orden, row_version FROM gapto.categorias_financieras "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "AND parent_id IS NOT DISTINCT FROM %s ORDER BY id FOR NO KEY UPDATE",
            (parent_id,),
        )
        return [{"id": i, "orden": o, "row_version": rv} for i, o, rv in cur.fetchall()]


def insertar(
    sesion: SesionMotor,
    *,
    categoria_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    nombre: str,
    ambito: str,
    presupuestable_default: bool,
    icon_key: str | None,
) -> None:
    sesion.uno(
        "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
        "presupuestable_default, icon_key) VALUES (%s, current_setting('gapto.owner_user_id')::uuid, "
        "%s, %s, %s, %s, %s) RETURNING id",
        (categoria_id, parent_id, nombre, ambito, presupuestable_default, icon_key),
    )


#: Columnas que los comandos pueden modificar. icon_key SI desde S6-ICONO
#: (F05-D013 supera F05-D010 Q4); presupuestable_default NO (Q6: no editable).
COLUMNAS_EDITABLES = frozenset({"nombre", "parent_id", "orden", "enabled", "ambito", "icon_key"})


def actualizar(sesion: SesionMotor, categoria_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE con row_version + 1 y updated_at. El control de version del
    cliente lo hace el servicio sobre la fila ya bloqueada."""
    if not cambios or not set(cambios) <= COLUMNAS_EDITABLES:
        raise ValueError(f"columnas no editables por los comandos: {sorted(set(cambios) - COLUMNAS_EDITABLES)}")
    columnas = sorted(cambios)
    asignaciones = ", ".join(f"{c} = %s" for c in columnas)
    sesion.uno(
        f"UPDATE gapto.categorias_financieras SET {asignaciones}, "
        "row_version = row_version + 1, updated_at = now() WHERE id = %s RETURNING id",
        tuple(cambios[c] for c in columnas) + (categoria_id,),
    )


def json_o_none(texto: str | None) -> Any:
    return None if texto is None else json.loads(texto)
