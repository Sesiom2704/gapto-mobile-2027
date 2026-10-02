# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_magnitudes.py
# Ruta: backend/app/api/dto_magnitudes.py
# Descripcion: DTO HTTP de S7-MAG (F05-01; F05-D020, expediente F05 §34).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-03/04).
#
#   Lectura del arbol (GET /v1/categorias): cada magnitud asociada anade
#   `asociacion_id` (PK de categoria_magnitudes), la identidad estable que
#   exigen los comandos de asociaciones (D-MAG-04). Campo ADITIVO: el resto
#   del nodo es exactamente CategoriaNodoArbol de dto_categorias.py, que no se
#   modifica (decision de ejecucion D29 del mandato S7-MAG backend: el modelo
#   ampliado vive aqui y app.py lo usa como response_model).
# Version: 0.1.0 (F05-01 S7-MAG, commit 1: lectura con asociacion_id)
# ============================================================

from __future__ import annotations

import uuid

from app.api.dto_categorias import CategoriaNodoArbol, MagnitudCategoria, _Estricto


class MagnitudAsociada(MagnitudCategoria):
    asociacion_id: uuid.UUID


class CategoriaNodoArbolMagnitudes(CategoriaNodoArbol):
    magnitudes: list[MagnitudAsociada]


class ArbolCategoriasMagnitudes(_Estricto):
    categorias: list[CategoriaNodoArbolMagnitudes]
