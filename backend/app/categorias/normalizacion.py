# ============================================================
# GAPTO MOBILE 2027
# Fichero: normalizacion.py
# Ruta: backend/app/categorias/normalizacion.py
# Descripcion: Normalizacion de nombres de categoria para la unicidad entre
#   hermanos activos (F05-D008 C06; F05-D010 AJ-04). Orden FIJO del
#   contrato: NFKC -> recortar extremos -> colapsar espacios internos ->
#   casefold -> quitar diacriticos (NFD y descarte de marcas Mn).
#   Es la garantia principal de unicidad; la UNIQUE fisica
#   uq_categorias_financieras__owner_parent_nombre compara el nombre literal
#   y solo es defensa residual (F05-01-R07).
#   `nombre_visible` es lo que se persiste: NFKC, recortado y con espacios
#   internos colapsados; conserva mayusculas y acentos del usuario.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import re
import unicodedata

LONGITUD_MAXIMA = 100
_ESPACIOS = re.compile(r"\s+")


def nombre_visible(nombre: str) -> str:
    return _ESPACIOS.sub(" ", unicodedata.normalize("NFKC", nombre).strip())


def normalizar(nombre: str) -> str:
    texto = nombre_visible(nombre).casefold()
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def nombre_valido(nombre: str) -> bool:
    visible = nombre_visible(nombre)
    return 0 < len(visible) <= LONGITUD_MAXIMA
