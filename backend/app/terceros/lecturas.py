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
# Version: 0.2.0 (F05-05 K2 §1.4; F05 §49.4 A4, §49.5 R10; M5-09): cada fila
#   anade `ultimo_uso` (fecha del ultimo hecho ACTIVO; homonimos por naturaleza
#   y uso, sin datos inventados). `buscar`: busqueda en servidor con ILIKE
#   '%q%' sobre `nombre` y `nombre_legal`, SIN indice nuevo (los GIN trigram no
#   los usa gapto_runtime bajo RLS: DEU-F03-TRGM-RLS); SENSIBLE a acentos en v1
#   («garcía» encuentra «García»; «garcia» no); inactivos solo con
#   `incluir_inactivos`; hasta 50 en orden (nombre normalizado, id).
# ============================================================

from __future__ import annotations

from typing import Any

from app.categorias.normalizacion import normalizar
from app.core.unidad_trabajo import SesionMotor

_SELECT = (
    "SELECT t.id, t.nombre, t.naturaleza, t.enabled, t.row_version, "
    "(SELECT count(DISTINCT ht.hecho_id) FROM gapto.hecho_terceros ht "
    " JOIN gapto.hechos_financieros h ON h.id = ht.hecho_id "
    " WHERE ht.tercero_id = t.id AND h.estado = 'ACTIVO') AS usos, "
    "(SELECT max(h.fecha_hecho) FROM gapto.hecho_terceros ht "
    " JOIN gapto.hechos_financieros h ON h.id = ht.hecho_id "
    " WHERE ht.tercero_id = t.id AND h.estado = 'ACTIVO') AS ultimo_uso "
    "FROM gapto.terceros t WHERE t.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_CLAVES = ("id", "nombre", "naturaleza", "enabled", "row_version", "usos", "ultimo_uso")
LIMITE_BUSQUEDA = 50
_FILTRO_BUSQUEDA = " AND (t.nombre ILIKE %s OR t.nombre_legal ILIKE %s)"


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


def _patron(texto: str) -> str:
    """Literal para ILIKE: escapa los comodines del usuario."""
    return "%" + texto.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def buscar(sesion: SesionMotor, texto: str, incluir_inactivos: bool) -> list[dict[str, Any]]:
    q = texto.strip()
    if not q:
        return []
    patron = _patron(q)
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + _FILTRO_BUSQUEDA, (patron, patron))
        filas = [dict(zip(_CLAVES, f)) for f in cur.fetchall()]
    if not incluir_inactivos:
        filas = [x for x in filas if x["enabled"]]
    filas.sort(key=lambda x: (normalizar(x["nombre"]), str(x["id"])))
    return filas[:LIMITE_BUSQUEDA]
