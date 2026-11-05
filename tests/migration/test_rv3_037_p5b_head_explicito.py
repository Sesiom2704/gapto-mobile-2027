# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_037_p5b_head_explicito.py
# Ruta: tests/migration/test_rv3_037_p5b_head_explicito.py
# Descripcion: RV3 / P5b 0.2.0 · F06-01 B0 v0.3 (dictamen B0 implementacion
#              PB0I-03, AJ-B0I-05; deuda R-RV3-016). auditar() exige el head
#              de forma explicita: sin head no clasifica (TypeError), un head
#              sin mapa declarado falla cerrado (ValueError), '0330' conserva
#              la clasificacion historica y '0351' aplica sus mapas (las tres
#              protectoras durables nuevas). La salida declara el head usado,
#              de modo que una auditoria sobre 0351 no puede certificarse con
#              el mapa historico en silencio. Corpus SINTETICO sin PII.
# Versión: 0.3.0  -- CANDIDATO B0 v0.3 (pendiente de dictamen y decision).
# ============================================================
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("rv3_p5b_rf04015", RAIZ / "scripts" / "migration_v3" / "rv3_p5b_rf04015.py")
P5B = importlib.util.module_from_spec(_s)
sys.modules["rv3_p5b_rf04015"] = P5B
_s.loader.exec_module(P5B)


class _DS:
    def __init__(self):
        self.filas = {t: {} for t in ("entidades", "contrato_servicios", "entidad_relaciones",
                                      "entidad_participaciones")}


def _ds() -> _DS:
    """Un servicio protegido SOLO por contrato_servicios, una inversion protegida
    SOLO por entidad_relaciones y un derecho protegido por una participacion."""
    ds = _DS()
    for i, t in (("s1", "SERVICIO"), ("i1", "INVERSION"), ("d1", "DERECHO_OBLIGACION"), ("c1", "CONTEXTO")):
        ds.filas["entidades"][i] = {"id": i, "tipo_entidad": t, "nombre": i}
    ds.filas["contrato_servicios"]["cs"] = {"id": "cs", "contrato_entidad_id": "k", "servicio_entidad_id": "s1"}
    ds.filas["entidad_relaciones"]["r"] = {"id": "r", "entidad_origen_id": "c1", "entidad_destino_id": "i1"}
    ds.filas["entidad_participaciones"]["p"] = {"id": "p", "entidad_id": "d1"}
    return ds


def _clase(r, i):
    return next((f["clase"], f["evadible_por_update"]) for f in r["detalle"] if f["entidad_id"] == i)


def test_sin_head_no_audita():
    with pytest.raises(TypeError):
        P5B.auditar(_ds())  # noqa: el head es obligatorio por contrato (PB0I-03)


@pytest.mark.parametrize("head", ["0340", "0350", "0352", "", None])
def test_head_sin_mapa_declarado_falla_cerrado(head):
    with pytest.raises(ValueError):
        P5B.auditar(_ds(), head=head)


def test_head_0330_conserva_la_clasificacion_historica():
    r = P5B.auditar(_ds(), head="0330")
    assert r["head_auditoria"] == "0330"
    assert _clase(r, "s1") == ("NO_PROTEGIDA", False)   # contrato_servicios borrable en 0330
    assert _clase(r, "i1") == ("NO_PROTEGIDA", False)   # entidad_relaciones borrable en 0330
    assert _clase(r, "d1") == ("PROTEGIDA", True)
    assert r["financieras_no_protegidas"] == ["i1"] and r["veredicto"] == "BLOQUEA_CARGA"


def test_head_0351_aplica_sus_mapas():
    r = P5B.auditar(_ds(), head="0351")
    assert r["head_auditoria"] == "0351"
    assert _clase(r, "s1") == ("PROTEGIDA", True)       # sin DELETE de runtime desde 0351; FK reapuntable
    assert _clase(r, "i1") == ("PROTEGIDA", True)
    assert _clase(r, "d1") == ("PROTEGIDA", True)
    assert r["financieras_no_protegidas"] == [] and r["veredicto"] == "SIN_BLOQUEO_POR_DELETE_DIRECTO"


def test_los_mapas_declarados_son_los_mismos_heads():
    assert set(P5B.RUNTIME_SIN_DELETE_POR_HEAD) == set(P5B.RUNTIME_UPDATE_FK_POR_HEAD) == {"0330", "0351"}
    assert P5B.RUNTIME_SIN_DELETE_POR_HEAD["0330"] is P5B.RUNTIME_SIN_DELETE
    assert P5B.RUNTIME_UPDATE_FK_POR_HEAD["0330"] is P5B.RUNTIME_UPDATE_FK


def test_cli_exige_head():
    with pytest.raises(SystemExit):
        P5B.main(["--run06", "x", "--decisiones-propietario", "y", "--salida", "z"])
