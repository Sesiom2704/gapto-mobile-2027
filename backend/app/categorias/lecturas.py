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
# Version: 0.1.0
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
    return [dict(zip(_COLUMNAS, f)) for f in filas]


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
