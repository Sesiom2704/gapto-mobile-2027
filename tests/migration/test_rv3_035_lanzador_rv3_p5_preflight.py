# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_035_lanzador_rv3_p5_preflight.py
# Ruta: tests/migration/test_rv3_035_lanzador_rv3_p5_preflight.py
# Descripcion: Preflight del lanzador de mutantes rv3_p5 (F05 §67.3, AJ-F0507G4-07;
#              scripts/dev/lanzar_mutantes_rv3_p5.py 0.2.0). Sin base de datos. Discrimina:
#              sin GAPTO_RV3_IMPORT_URL (ausente o vacia) aborta con rc=2 ANTES de leer o cargar
#              el arnes certificado (sin mutar, sin VIVO); URL en lugar de clave=valor, hosts no
#              locales (Neon, Supabase, otro host, hostaddr, varios hosts con uno remoto) y sin
#              dbname abortan; un laboratorio local de loopback pasa. El arnes certificado no cambia.
# Version: 0.1.0 (F05-D053 paso 2)
# ============================================================
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("lanzar_mutantes_rv3_p5", RAIZ / "scripts" / "dev" / "lanzar_mutantes_rv3_p5.py")
L = importlib.util.module_from_spec(_s)
sys.modules["lanzar_mutantes_rv3_p5"] = L
_s.loader.exec_module(L)

LOCAL = "host=127.0.0.1 port=5463 user=postgres dbname=mpb_rv3_import"


@pytest.mark.parametrize("entorno", [{}, {"GAPTO_RV3_IMPORT_URL": ""}, {"GAPTO_RV3_IMPORT_URL": "   "}])
def test_sin_laboratorio_aborta_en_preflight(entorno, capsys):
    with pytest.raises(SystemExit) as e:
        L.preflight_laboratorio(entorno)
    assert e.value.code == 2
    assert "STOP-RV3P5-PREFLIGHT" in capsys.readouterr().err


@pytest.mark.parametrize("dsn", [
    "postgresql://postgres@127.0.0.1:5463/mpb_rv3_import",
    "host=ep-lucky-base-b2zxsueb.c-6.eu-central-1.aws.neon.tech user=neondb_owner dbname=gapto2027_cleanroom",
    "host=db.abcdefghij.supabase.co user=postgres dbname=postgres",
    "host=192.168.1.20 user=postgres dbname=lab",
    "host=127.0.0.1,ep-x.neon.tech user=postgres dbname=lab",
    "host=127.0.0.1 hostaddr=10.0.0.5 user=postgres dbname=lab",
    "user=postgres dbname=lab",
    "host=127.0.0.1 user=postgres",
    "host=127.0.0.1 dbname=",
])
def test_laboratorio_no_local_o_mal_formado_aborta(dsn):
    with pytest.raises(SystemExit) as e:
        L.preflight_laboratorio({"GAPTO_RV3_IMPORT_URL": dsn})
    assert e.value.code == 2


@pytest.mark.parametrize("dsn", [LOCAL, "host=localhost port=5463 user=postgres dbname=lab"])
def test_laboratorio_local_pasa(dsn):
    assert L.preflight_laboratorio({"GAPTO_RV3_IMPORT_URL": dsn}) == dsn


def test_main_sin_laboratorio_no_carga_ni_muta_el_arnes(monkeypatch):
    """El preflight va ANTES de leer el arnes: sin laboratorio no se carga ni se ejecuta nada."""
    arnes = RAIZ / L.REL
    antes = hashlib.sha256(arnes.read_bytes()).hexdigest()
    monkeypatch.delenv("GAPTO_RV3_IMPORT_URL", raising=False)

    def prohibido(*_a, **_k):
        raise AssertionError("el lanzador cargo el arnes sin laboratorio")
    monkeypatch.setattr(L.importlib.util, "spec_from_file_location", prohibido)
    monkeypatch.setattr(Path, "read_bytes", prohibido)
    with pytest.raises(SystemExit) as e:
        L.main()
    assert e.value.code == 2
    monkeypatch.undo()
    assert hashlib.sha256(arnes.read_bytes()).hexdigest() == antes == L.SHA_CERTIFICADO
