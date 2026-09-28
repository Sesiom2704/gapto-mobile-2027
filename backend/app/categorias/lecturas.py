# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/categorias/lecturas.py
# Descripcion: Lecturas del arbol de categorias para F05-01 (S3). Solo
#   lectura, bajo gapto_runtime y RLS del tenant.
#
#   - `arbol`: TODAS las categorias del owner, incluidas las deshabilitadas,
#     marcadas como tales. La historia no filtra por `enabled` (D-198); la
#     selectabilidad la decide la UI con la guarda C-a como autoridad final.
#     `icon_key` se devuelve tal cual: NULL significa fallback neutro (C08) y
#     su escritura no esta autorizada hasta que F09 publique la lista cerrada
#     del Design System (Q4).
#   - `uso_por_naturaleza`: efectos de hechos ACTIVOS que referencian la
#     categoria, por naturaleza. Es la informacion que C06 exige mostrar antes
#     de confirmar un cambio de `ambito`.
#   Orden estable: `orden`, `nombre`, `id`. El orden no es identidad.
#
#   v0.2.0 (F05-01, S6-C07; F05-D014 §28.2 AJ-C07-08): cada nodo de `arbol`
#   incluye sus magnitudes (magnitud_id, nombre, obligatoria, orden, enabled,
#   unidad_default, precision_decimales, row_version de la magnitud),
#   ordenadas por orden de la asociacion -> nombre -> id, mas `capturable`
#   (false si alguna asociacion OBLIGATORIA apunta a una magnitud
#   deshabilitada o no visible) y `motivo_no_capturable` (None o
#   MAGNITUD_OBLIGATORIA_NO_DISPONIBLE). Una opcional deshabilitada NO hace la
#   categoria no capturable. `capturable` no sustituye a `enabled` ni a
#   `ambito`, y esta lectura nunca es autoridad de persistencia: decide C07
#   dentro de la transaccion del registro (captura_magnitudes.py). Sin locks.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor

_COLUMNAS = (
    "id",
    "parent_id",
    "nombre",
    "codigo",
    "ambito",
    "enabled",
    "orden",
    "icon_key",
    "presupuestable_default",
    "row_version",
)


MOTIVO_OBLIGATORIA_NO_DISPONIBLE = "MAGNITUD_OBLIGATORIA_NO_DISPONIBLE"

_COLUMNAS_MAGNITUD = (
    "magnitud_id",
    "nombre",
    "obligatoria",
    "orden",
    "enabled",
    "unidad_default",
    "precision_decimales",
    "row_version",
)


def _magnitudes_por_categoria(sesion: SesionMotor) -> dict[uuid.UUID, dict[str, Any]]:
    """Asociaciones de las categorias del owner. LEFT JOIN: una obligatoria
    hacia una magnitud no visible no se lista, pero hace la categoria no
    capturable (mismo criterio fail-closed que C07)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT cm.categoria_id, cm.obligatoria, cm.orden, m.id, m.nombre, m.enabled, "
            "m.unidad_default, m.precision_decimales, m.row_version "
            "FROM gapto.categoria_magnitudes cm "
            "JOIN gapto.categorias_financieras c ON c.id = cm.categoria_id "
            "LEFT JOIN gapto.magnitudes m ON m.id = cm.magnitud_id "
            "WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "ORDER BY cm.categoria_id, cm.orden, m.nombre, m.id"
        )
        filas = cur.fetchall()
    salida: dict[uuid.UUID, dict[str, Any]] = {}
    for cat, obligatoria, orden, mid, nombre, enabled, unidad, precision, version in filas:
        nodo = salida.setdefault(cat, {"magnitudes": [], "capturable": True})
        if mid is None or not enabled:
            if obligatoria:
                nodo["capturable"] = False
            if mid is None:
                continue
        nodo["magnitudes"].append(
            dict(zip(_COLUMNAS_MAGNITUD, (mid, nombre, obligatoria, orden, enabled, unidad, precision, version)))
        )
    return salida


def arbol(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, parent_id, nombre, codigo, ambito, enabled, orden, icon_key, "
            "presupuestable_default, row_version "
            "FROM gapto.categorias_financieras "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "ORDER BY orden, nombre, id"
        )
        filas = cur.fetchall()
    magnitudes = _magnitudes_por_categoria(sesion)
    nodos = []
    for f in filas:
        nodo = dict(zip(_COLUMNAS, f))
        extra = magnitudes.get(nodo["id"], {"magnitudes": [], "capturable": True})
        nodo["magnitudes"] = extra["magnitudes"]
        nodo["capturable"] = extra["capturable"]
        nodo["motivo_no_capturable"] = None if extra["capturable"] else MOTIVO_OBLIGATORIA_NO_DISPONIBLE
        nodos.append(nodo)
    return nodos


def uso_por_naturaleza(sesion: SesionMotor, categoria_id: uuid.UUID) -> dict[str, Any]:
    existe = sesion.uno(
        "SELECT ambito FROM gapto.categorias_financieras WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid",
        (categoria_id,),
    )
    if existe is None:
        raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "Categoria no encontrada.")
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT e.tipo_efecto, count(*) FROM gapto.hecho_efectos e "
            "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
            "WHERE e.categoria_id = %s AND h.estado = 'ACTIVO' "
            "GROUP BY e.tipo_efecto ORDER BY e.tipo_efecto",
            (categoria_id,),
        )
        por_naturaleza = {t: int(n) for t, n in cur.fetchall()}
    return {"categoria_id": categoria_id, "ambito": existe[0], "efectos_activos": por_naturaleza}
