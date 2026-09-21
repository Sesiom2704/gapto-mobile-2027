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
#   0.5.0: aisla inicio por creacion, cobro parcial y compra cancelada (P5 v0.18.0).
#   0.4.0: aisla fusiones, inicio/fin y compras financiadas decididas (P5 v0.17.0).
#   0.3.0: aisla tambien los catalogos del dominio 5 (P5 v0.16.0).
#   0.2.0: aisla tambien el arbol de categorias canonico (CATEGORIAS_ACTIVAS, P5 v0.13.0).
# Versión: 0.5.0
# ============================================================
from __future__ import annotations

import pytest

CATALOGOS = {"DERECHOS_V3": [], "CATEGORIAS_ACTIVAS": False,
             # 0.3.0: catalogos del dominio 5 (P5 v0.16.0) anclados a claves V3 reales
             "CONTENEDORES_PRESUPUESTARIOS": set(), "TRANSFERENCIAS_AHORRO": set(), "FUSION_MEDIOLANUM": None,
             "REGLA_DERECHO_ISA": {}, "RODANTES_VALIDADOS": set(),
             # 0.4.0: decisiones del propietario 2026-09-21 ancladas a claves V3 reales (P5 v0.17.0)
             "FUSIONES_PROPIETARIO": [], "INICIO_CONFIRMADO": set(), "FIN_POR_MODIFICACION": set(),
             "COMPRA_FINANCIADA_DECIDIDA": set(),
             # 0.5.0: respuestas A-F (P5 v0.18.0)
             "INICIO_POR_CREACION": set(), "COBRO_PARCIAL_NO_REGLA": set(), "COMPRA_FINANCIADA_CANCELADA": set()}


@pytest.fixture(autouse=True)
def _aislar_catalogos_v3(request, monkeypatch):
    p5 = getattr(request.module, "P5", None)
    if p5 is None:
        return
    # 0.3.0: el dominio 5 solo se ejecuta en los modulos que lo declaran (DOMINIO_5 = True):
    # los tests historicos verifican su baseline sin el bloque posterior (Working Method).
    if hasattr(p5, "DOMINIO_5_ACTIVO") and not getattr(request.module, "DOMINIO_5", False):
        monkeypatch.setattr(p5, "DOMINIO_5_ACTIVO", False)
    if getattr(request.module, "CATALOGOS_V3_REALES", False):
        return
    for nombre, vacio in CATALOGOS.items():
        if hasattr(p5, nombre):
            monkeypatch.setattr(p5, nombre, vacio)
