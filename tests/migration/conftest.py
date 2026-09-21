# ============================================================
# GAPTO MOBILE 2027
# Fichero: conftest.py
# Ruta: tests/migration/conftest.py
# Descripcion: RV3. Aisla los corpus SINTETICOS de los catalogos cerrados de
#              P5 anclados a claves V3 reales (p. ej. DERECHOS_V3, P5 v0.7.0):
#              esos catalogos fallan cerrados (S8) si su origen no existe, que es
#              lo correcto con datos reales pero no aplica a un corpus sintetico
#              que no los contiene. Un modulo de test que SI quiera ejercitar el
#              catalogo declara CATALOGOS_V3_REALES = True y aporta su corpus.
#              Asi los tests historicos verifican su baseline sin bloquear los
#              bloques posteriores (Working Method).
#   0.2.0: aisla tambien el arbol de categorias canonico (CATEGORIAS_ACTIVAS, P5 v0.13.0).
# Versión: 0.2.0
# ============================================================
from __future__ import annotations

import pytest

CATALOGOS = {"DERECHOS_V3": [], "CATEGORIAS_ACTIVAS": False}


@pytest.fixture(autouse=True)
def _aislar_catalogos_v3(request, monkeypatch):
    p5 = getattr(request.module, "P5", None)
    if p5 is None or getattr(request.module, "CATALOGOS_V3_REALES", False):
        return
    for nombre, vacio in CATALOGOS.items():
        if hasattr(p5, nombre):
            monkeypatch.setattr(p5, nombre, vacio)
