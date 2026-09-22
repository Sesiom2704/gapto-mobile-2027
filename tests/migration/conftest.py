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
#   0.12.0: aisla R02 del dominio 12 (DOMINIO_12_R02_ACTIVO salvo modulos con R02 = True), P5 v0.26.0.
#   0.11.0: aisla la disposicion R05 del dominio 12 (DOMINIO_12_DISPOSICION_ACTIVO salvo modulos con
#           DOMINIO_12 = True), P5 v0.25.0.
#   0.10.0: aisla el dominio 11 (DOMINIO_11_ACTIVO salvo modulos con DOMINIO_11 = True), P5 v0.23.0.
#   0.9.0: aisla el dominio 7 (DOMINIO_7_ACTIVO salvo modulos con DOMINIO_7 = True), P5 v0.22.0.
#   0.8.0: aisla ATRIBUCION_COMPARTIDA y CONTEXTO_ADICIONAL (P5 v0.21.0).
#   0.7.0: aisla VIVIENDA_ATRIBUCION_DECIDIDA e IMPORTE_TOTAL_CORREGIDO (P5 v0.20.0).
#   0.6.0: aisla el dominio 6 (DOMINIO_6_ACTIVO salvo modulos con DOMINIO_6 = True) y sus
#          catalogos anclados a claves V3 reales (P5 v0.19.0).
#   0.5.0: aisla inicio por creacion, cobro parcial y compra cancelada (P5 v0.18.0).
#   0.4.0: aisla fusiones, inicio/fin y compras financiadas decididas (P5 v0.17.0).
#   0.3.0: aisla tambien los catalogos del dominio 5 (P5 v0.16.0).
#   0.2.0: aisla tambien el arbol de categorias canonico (CATEGORIAS_ACTIVAS, P5 v0.13.0).
# Versión: 0.12.0
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
             "INICIO_POR_CREACION": set(), "COBRO_PARCIAL_NO_REGLA": set(), "COMPRA_FINANCIADA_CANCELADA": set(),
             # 0.6.0: dominio 6 (P5 v0.19.0)
             "TRANSFERENCIA_LEGACY_DECIDIDA": set(), "DEVOLUCION_DECIDIDA": {}, "GASTO_CORREGIDO_V3": set(),
             "ATRIBUCION_CONTRAPARTE_100": set(), "ATRIBUCION_DERECHO_PENDIENTE": set(), "GENERACION_PURA": set(),
             # 0.7.0: respuestas al bloque 1 del dominio 6 (P5 v0.20.0)
             "VIVIENDA_ATRIBUCION_DECIDIDA": {}, "IMPORTE_TOTAL_CORREGIDO": {},
             # 0.8.0: ticket compartido y contexto adicional (P5 v0.21.0)
             "ATRIBUCION_COMPARTIDA": set(), "CONTEXTO_ADICIONAL": {}}


@pytest.fixture(autouse=True)
def _aislar_catalogos_v3(request, monkeypatch):
    p5 = getattr(request.module, "P5", None)
    if p5 is None:
        return
    # 0.3.0: el dominio 5 solo se ejecuta en los modulos que lo declaran (DOMINIO_5 = True):
    # los tests historicos verifican su baseline sin el bloque posterior (Working Method).
    if hasattr(p5, "DOMINIO_5_ACTIVO") and not getattr(request.module, "DOMINIO_5", False):
        monkeypatch.setattr(p5, "DOMINIO_5_ACTIVO", False)
    # 0.12.0: igual para R02 (disposicion campo a campo; exige el pipeline completo)
    if hasattr(p5, "DOMINIO_12_R02_ACTIVO") and not getattr(request.module, "R02", False):
        monkeypatch.setattr(p5, "DOMINIO_12_R02_ACTIVO", False)
    # 0.11.0: igual para la disposicion R05 del dominio 12 (exige el pipeline completo)
    if hasattr(p5, "DOMINIO_12_DISPOSICION_ACTIVO") and not getattr(request.module, "DOMINIO_12", False):
        monkeypatch.setattr(p5, "DOMINIO_12_DISPOSICION_ACTIVO", False)
    # 0.10.0: igual para el dominio 11
    if hasattr(p5, "DOMINIO_11_ACTIVO") and not getattr(request.module, "DOMINIO_11", False):
        monkeypatch.setattr(p5, "DOMINIO_11_ACTIVO", False)
    # 0.9.0: igual para el dominio 7
    if hasattr(p5, "DOMINIO_7_ACTIVO") and not getattr(request.module, "DOMINIO_7", False):
        monkeypatch.setattr(p5, "DOMINIO_7_ACTIVO", False)
    # 0.6.0: igual para el dominio 6
    if hasattr(p5, "DOMINIO_6_ACTIVO") and not getattr(request.module, "DOMINIO_6", False):
        monkeypatch.setattr(p5, "DOMINIO_6_ACTIVO", False)
    if getattr(request.module, "CATALOGOS_V3_REALES", False):
        return
    for nombre, vacio in CATALOGOS.items():
        if hasattr(p5, nombre):
            monkeypatch.setattr(p5, nombre, vacio)
