# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_052_f06_t5_e1_runner_head_obligatorio.py
# Ruta: tests/database/test_052_f06_t5_e1_runner_head_obligatorio.py
# Descripcion: F06 T5 E1 · O-R3-18 (adenda T5 ronda 3 §6, AJ-T5-R3-14): seleccion
#   inequivoca del contrato fisico del clean room.
#     - Modo gate (--junit, --manifiesto, --completar-manifiesto, --proyecto,
#       --commit) sin --head -> el runner sale con «MODO GATE sin --head» ANTES
#       de conectar a ninguna base.
#     - El contrato pedido (--head, o el por defecto sin --head) debe ser el de la
#       ultima migration de la cadena ejecutada: si no, CONTRATO_NO_CORRESPONDE.
#   Sin base de datos: no exige GAPTO_TEST_DATABASE_URL. La ejecucion real contra
#   un cluster desechable (0001..0356 con --head 0355, sin --head y con --head
#   0356) queda en la evidencia de E1.
# Version: 0.1.0 (F06 T5 E1, mandato T5E1_HITO v1.0 P1.5)
# ============================================================
from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
RUNNER = RAIZ / "scripts" / "postgres" / "run_clean_room.py"


@pytest.fixture(scope="module")
def rcr():
    spec = importlib.util.spec_from_file_location("rcr_052", RUNNER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["rcr_052"] = m
    spec.loader.exec_module(m)
    return m


def _args(**kw):
    base = dict(head=None, junit=None, manifiesto=None, completar=None, proyecto=None, commit=None)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.mark.parametrize("opcion", ["junit", "manifiesto", "completar", "proyecto", "commit"])
def test_modo_gate_sin_head_se_rechaza(rcr, opcion):
    assert "MODO GATE sin --head" in rcr.exigir_head_en_gate(_args(**{opcion: "x"}))
    assert rcr.exigir_head_en_gate(_args(**{opcion: "x", "head": "0356"})) is None


def test_sin_opciones_de_gate_no_exige_head(rcr):
    assert rcr.exigir_head_en_gate(_args()) is None


def test_contrato_pedido_distinto_de_la_cadena_es_fallo_inequivoco(rcr):
    m = rcr.contrato_corresponde("0355", "0356")
    assert m.startswith("CONTRATO_NO_CORRESPONDE") and "--head 0355" in m and "0356" in m
    assert rcr.contrato_corresponde("0356", "0356") is None


def test_sin_head_el_contrato_por_defecto_tambien_debe_corresponder(rcr):
    assert rcr.HEAD_POR_DEFECTO == "0355" and rcr.CONTRATOS_POR_HEAD["0355"] is rcr.CONTRATO_POR_DEFECTO
    m = rcr.contrato_corresponde(None, "0356")
    assert m.startswith("CONTRATO_NO_CORRESPONDE") and "por defecto (0355)" in m
    assert rcr.contrato_corresponde(None, "0355") is None


def test_solo_verificar_sin_cadena_no_contrasta(rcr):
    assert rcr.contrato_corresponde("0356", None) is None


def test_invocacion_real_en_modo_gate_sin_head_sale_antes_de_conectar(tmp_path):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GAPTO_")}
    r = subprocess.run([sys.executable, str(RUNNER), "--junit", str(tmp_path / "x.xml")],
                       capture_output=True, text=True, env=entorno, cwd=RAIZ, timeout=60)
    assert r.returncode != 0
    assert "MODO GATE sin --head (--junit)" in (r.stderr + r.stdout)
    assert "Base destino" not in r.stdout          # no llego a conectar
