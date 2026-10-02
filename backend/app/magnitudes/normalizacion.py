# ============================================================
# GAPTO MOBILE 2027
# Fichero: normalizacion.py
# Ruta: backend/app/magnitudes/normalizacion.py
# Descripcion: Validacion y normalizacion de los datos de una magnitud
#   (F05-D020 D-MAG-05). Reutiliza la normalizacion de C06 de categorias
#   (NFKC -> recortar -> colapsar -> casefold -> sin diacriticos) para la
#   unicidad, pero NO `nombre_valido` (limite 100): el limite fisico de
#   magnitudes.nombre es 80 (CE-S7MAG-05).
#     - `nombre_magnitud_valido`: 1..80 caracteres sobre el nombre visible
#       (NFKC, recortado y con espacios internos colapsados).
#     - `unidad_valida`: 1..20 caracteres visibles, no blanca. Se persiste la
#       forma visible (misma regla NFKC + recorte + colapso; decision de
#       ejecucion D30 del mandato S7-MAG backend).
#     - `precision_valida`: 0..6 (CHECK de 0020; el DTO ya la acota).
#   La unicidad se compara contra TODAS las magnitudes del owner, habilitadas
#   o no (la UNIQUE de 0080 no es parcial), bajo el advisory.
# Version: 0.1.0 (F05-01 S7-MAG)
# ============================================================

from __future__ import annotations

from app.categorias.normalizacion import nombre_visible, normalizar

LONGITUD_NOMBRE = 80
LONGITUD_UNIDAD = 20
PRECISION_MAXIMA = 6

__all__ = ("normalizar", "nombre_visible", "nombre_magnitud_valido", "unidad_valida", "precision_valida",
           "LONGITUD_NOMBRE", "LONGITUD_UNIDAD", "PRECISION_MAXIMA")


def nombre_magnitud_valido(nombre: str) -> bool:
    return 0 < len(nombre_visible(nombre)) <= LONGITUD_NOMBRE


def unidad_valida(unidad: str) -> bool:
    return 0 < len(nombre_visible(unidad)) <= LONGITUD_UNIDAD


def precision_valida(precision: int) -> bool:
    return isinstance(precision, int) and not isinstance(precision, bool) and 0 <= precision <= PRECISION_MAXIMA
