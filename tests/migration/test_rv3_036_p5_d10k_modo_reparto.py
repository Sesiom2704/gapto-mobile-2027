# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_036_p5_d10k_modo_reparto.py
# Ruta: tests/migration/test_rv3_036_p5_d10k_modo_reparto.py
# Descripcion: RV3 / P5 v0.37.0 · F06-01 B0 (F06-D002, PB0-08). La regla D10-K
#              fija modo_reparto = 'FIJO' en la unica fila de contrato_servicios
#              que crea P5 (repercutible, con actor y porcentaje), y la carga
#              fisica con RV3_IMPORT (ROLLBACK) cumple
#              ck_contrato_servicios__repercusion_coherente de 0351. Corpus
#              SINTETICO de test_rv3_012 (sin PII). Contra un head anterior a
#              0351 la carga falla porque la columna no existe: P5 v0.37 exige
#              0351 (orden de despliegue, PLAN_APLICACION).
# Versión: 0.2.0  -- PAQUETE B0 v0.2 (no candidato hasta dictamen).
# ============================================================
from __future__ import annotations

import os
from decimal import Decimal

import pytest

import test_rv3_012_p5_dominio10 as D10

cfg = D10.cfg  # fixture autouse del modulo D10 (configuracion sintetica)
P5 = D10.P5

SERVICIO = [{"clave": "luz", "tipo_servicio": "SUMINISTRO_ELECTRICO", "actor": ("public.personas", "PI"),
             "porcentaje": Decimal(100)}]


def test_d10k_fija_modo_reparto_fijo(monkeypatch):
    monkeypatch.setattr(P5, "SERVICIOS_REPERCUTIDOS", {"K1": SERVICIO})
    cs = list(D10._t().filas["contrato_servicios"].values())
    assert len(cs) == 1
    assert (cs[0]["repercutible"], cs[0]["modo_reparto"], cs[0]["porcentaje_repercutible"]) == \
        (True, "FIJO", Decimal(100))
    assert cs[0]["actor_repercusion_id"] is not None


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_d10k_fisico_por_head(monkeypatch):
    import psycopg

    url = os.environ["GAPTO_RV3_IMPORT_URL"]
    with psycopg.connect(url) as c:
        head_0351 = c.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'gapto.contrato_servicios'::regclass "
            "AND attname = 'modo_reparto' AND NOT attisdropped)").fetchone()[0]
    monkeypatch.setattr(P5, "SERVICIOS_REPERCUTIDOS", {"K1": SERVICIO})
    ds = D10._t(con={"fianza": "550.00"})
    if head_0351:
        res = P5.validar_fisico(ds, url)
        assert res["contrato_servicios"] == 1 and res["contratos"] == 1
    else:
        with pytest.raises(psycopg.errors.UndefinedColumn):
            P5.validar_fisico(ds, url)
