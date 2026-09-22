# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_027_p5b_rf04015.py
# Ruta: tests/migration/test_rv3_027_p5b_rf04015.py
# Descripcion: RV3 / P5b v0.1.0. Discrimina la clasificacion R-F04-015 (PROTEGIDA solo con protector que
#              gapto_runtime no puede borrar; NO_PROTEGIDA con protectores borrables o sin ellos; INDETERMINADA sin
#              tipo; evasion por UPDATE del FK del protector) y contrasta el mapa FK/ACL declarado con el catalogo
#              fisico 0330 del laboratorio (deriva = fallo). Corpus SINTETICO sin PII.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
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
        self.filas = {t: {} for t in ("entidades", "entidad_participaciones", "hecho_entidades", "financiacion_cuotas",
                                      "contrato_servicios")}


def _ent(ds, i, tipo):
    ds.filas["entidades"][i] = {"id": i, "tipo_entidad": tipo, "nombre": i}


def _clase(r, i):
    return next((f["clase"], f["evadible_por_update"]) for f in r["detalle"] if f["entidad_id"] == i)


def test_clasificacion_por_protector():
    ds = _DS()
    for i, t in (("d1", "DERECHO_OBLIGACION"), ("d2", "DERECHO_OBLIGACION"), ("f1", "FINANCIACION"), ("x", "RARO")):
        _ent(ds, i, t)
    ds.filas["entidad_participaciones"]["p"] = {"id": "p", "entidad_id": "d1"}
    ds.filas["hecho_entidades"]["h"] = {"id": "h", "entidad_id": "d2"}
    ds.filas["financiacion_cuotas"]["q"] = {"id": "q", "financiacion_entidad_id": "f1"}
    r = P5B.auditar(ds)
    assert _clase(r, "d1") == ("PROTEGIDA", True)       # participacion: runtime no la borra, pero la reapunta
    assert _clase(r, "d2") == ("NO_PROTEGIDA", False)   # hecho_entidades: runtime puede borrarla (D-183)
    assert _clase(r, "f1") == ("PROTEGIDA", True)
    assert _clase(r, "x")[0] == "INDETERMINADA"
    assert r["financieras_no_protegidas"] == ["d2"] and r["veredicto"] == "BLOQUEA_CARGA"


def test_financiera_sin_protector_bloquea_y_no_financiera_va_a_r_rv3_003():
    ds = _DS()
    _ent(ds, "c1", "CONTEXTO")
    r = P5B.auditar(ds)
    assert r["veredicto"] == "SIN_BLOQUEO_POR_DELETE_DIRECTO" and r["no_financieras_no_protegidas_R_RV3_003"] == ["c1"]
    _ent(ds, "i1", "INVERSION")
    assert P5B.auditar(ds)["veredicto"] == "BLOQUEA_CARGA"


URL = os.environ.get("GAPTO_RV3_IMPORT_URL")


@pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")
def test_mapa_declarado_igual_al_catalogo_0330():
    import psycopg
    with psycopg.connect(URL) as c:
        c.execute("SET ROLE gapto_migrator")  # perfil RV3_IMPORT (D-E): lectura de catalogo como gapto_owner
        c.execute("SET ROLE gapto_owner")
        fk = c.execute("""
            SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text, c.confdeltype
              FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
             WHERE c.contype = 'f' AND a.attname <> 'owner_user_id'  -- FK compuestas por tenant (0288)
               AND c.confrelid::regclass::text IN ('gapto.entidades','gapto.contratos','gapto.financiaciones',
                   'gapto.inversiones','gapto.propiedades','gapto.servicios','gapto.contextos',
                   'gapto.derechos_obligaciones_financieras')""").fetchall()
        cascada = {t.split(".")[1] for t, a, p, d in fk if p == "gapto.entidades" and d == "c"}
        assert cascada == set(P5B.SUBTIPO_POR_TIPO.values())
        restr_ent = {(t.split(".")[1], a) for t, a, p, d in fk if p == "gapto.entidades" and d == "r"}
        assert restr_ent == {(t, c) for t, cs in P5B.RESTRICT_ENTIDAD.items() for c in cs}
        restr_sub = {(p.split(".")[1], t.split(".")[1], a) for t, a, p, d in fk if p != "gapto.entidades" and d == "r"}
        assert restr_sub == {(s, t, c) for s, m in P5B.RESTRICT_SUBTIPO.items() for t, cs in m.items() for c in cs}
        protectoras = {t for t, _ in restr_ent} | {t for _, t, _ in restr_sub}
        sin_delete = {t for t in protectoras if not c.execute(
            "SELECT has_table_privilege('gapto_runtime', 'gapto.' || %s, 'DELETE')", (t,)).fetchone()[0]}
        assert sin_delete == P5B.RUNTIME_SIN_DELETE
        fks = {(t, col) for t, col in ({(t, a) for t, a in restr_ent} | {(t, a) for _, t, a in restr_sub})}
        upd = {(t, col) for t, col in fks if t in P5B.RUNTIME_SIN_DELETE and c.execute(
            "SELECT has_column_privilege('gapto_runtime', 'gapto.' || %s, %s, 'UPDATE')", (t, col)).fetchone()[0]}
        assert upd == P5B.RUNTIME_UPDATE_FK
