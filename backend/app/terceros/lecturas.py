# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/terceros/lecturas.py
# Descripcion: Lecturas de terceros para el registro y Ajustes › Terceros
#   (F05-04 J2 §1.3/§1.9; lamina REG-DYN / SET-TH v0.1 P01, P02, S01). Solo
#   lectura, gapto_runtime con RLS del tenant, sin locks.
#   - `listar`: todos los terceros del owner (activos e inactivos) en orden
#     estable (nombre normalizado, id), con `usos` = hechos ACTIVOS en los que
#     participa (dato de la fila de P02 «Empresa · 14 gastos»).
#   - `candidatos`: posibles duplicados de un nombre (P02): terceros del owner
#     cuyo nombre normalizado (C06: NFKC, recorte, espacios, casefold, sin
#     diacriticos) es IGUAL al del nombre dado, INCLUIDOS los inactivos (para
#     ofrecer «Reactivar»). Es un aviso: nunca un control de unicidad ni una
#     fusion (R5).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.3)
# ============================================================

from __future__ import annotations

from typing import Any

from app.categorias.normalizacion import normalizar
from app.core.unidad_trabajo import SesionMotor

_SELECT = (
    "SELECT t.id, t.nombre, t.naturaleza, t.enabled, t.row_version, "
    "(SELECT count(DISTINCT ht.hecho_id) FROM gapto.hecho_terceros ht "
    " JOIN gapto.hechos_financieros h ON h.id = ht.hecho_id "
    " WHERE ht.tercero_id = t.id AND h.estado = 'ACTIVO') AS usos "
    "FROM gapto.terceros t WHERE t.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_CLAVES = ("id", "nombre", "naturaleza", "enabled", "row_version", "usos")


def _todos(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT)
        filas = [dict(zip(_CLAVES, f)) for f in cur.fetchall()]
    return sorted(filas, key=lambda x: (normalizar(x["nombre"]), str(x["id"])))


def listar(sesion: SesionMotor) -> list[dict[str, Any]]:
    return _todos(sesion)


def candidatos(sesion: SesionMotor, nombre: str) -> list[dict[str, Any]]:
    clave = normalizar(nombre)
    if not clave:
        return []
    return [x for x in _todos(sesion) if normalizar(x["nombre"]) == clave]
