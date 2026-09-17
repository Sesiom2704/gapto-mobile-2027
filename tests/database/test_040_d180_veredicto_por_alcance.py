# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_040_d180_veredicto_por_alcance.py
# Ruta: tests/database/test_040_d180_veredicto_por_alcance.py
# Descripcion: D-180. El veredicto de `run_clean_room.py` debe estar tipado por
#   alcance: INSTANCE_BOOTSTRAP frente a BASE_CLEANROOM.
#
#   Lo que se prueba, y por que:
#
#   1) Un clean-room DE BASE correcto ya NO puede quedar etiquetado como fallo
#      por la sola razon de no haber aplicado 0001. En una instancia ya
#      provisionada aplicarlo es imposible por diseno: 0001 aborta con su
#      propio postcheck de ROLE DRIFT. Etiquetarlo FALLO hacia ilegible la
#      evidencia.
#
#   2) NINGUNA condicion del PASS se relaja. Virginidad, JUnit presente, JUnit
#      con tests, suite verde y contrato sin discrepancias se siguen exigiendo
#      exactamente igual en los dos alcances. Estos tests fallan si alguien
#      intenta ablandar cualquiera de ellas.
#
#   3) La etiqueta de instancia conserva su forma historica literal, de modo
#      que los manifests anteriores siguen siendo comparables y no hay que
#      reescribir ninguno.
#
#   Es un test de unidad puro: no toca base de datos. Vive en tests/database
#   por coherencia con la organizacion actual del runner, conforme a la
#   autorizacion expresa del mandato F04-03.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_RUNNER = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "postgres" / "run_clean_room.py"
)


def _cargar_runner():
    especificacion = importlib.util.spec_from_file_location("run_clean_room", _RUNNER)
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules["run_clean_room"] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


runner = _cargar_runner()

HEAD = "0310"
JUNIT_VERDE = {"tests": 924, "failures": 0, "errors": 0, "skipped": 55}
JUNIT_ROJO = {"tests": 924, "failures": 3, "errors": 0, "skipped": 55}
JUNIT_VACIO = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


# ------------------------------------------------------------------
# Alcance
# ------------------------------------------------------------------

def test_el_alcance_lo_determina_quien_creo_los_roles() -> None:
    assert runner.alcance_de(True) == runner.SCOPE_INSTANCIA
    assert runner.alcance_de(False) == runner.SCOPE_BASE


def test_la_etiqueta_de_instancia_conserva_su_forma_historica() -> None:
    """Los manifests anteriores a D-180 deben seguir siendo comparables."""
    assert (
        runner.etiqueta_veredicto(runner.SCOPE_INSTANCIA, "0001", HEAD, True)
        == "PASS_INSTANCE_BOOTSTRAP_F03_0001_0310"
    )
    assert (
        runner.etiqueta_veredicto(runner.SCOPE_INSTANCIA, "0001", HEAD, False)
        == "FALLO_INSTANCE_BOOTSTRAP_F03_0001_0310"
    )


def test_la_etiqueta_de_base_es_propia_y_declara_su_tramo() -> None:
    assert (
        runner.etiqueta_veredicto(runner.SCOPE_BASE, "0002", HEAD, True)
        == "PASS_BASE_CLEANROOM_F03_0002_0310"
    )
    assert (
        runner.etiqueta_veredicto(runner.SCOPE_BASE, "0002", HEAD, False)
        == "FALLO_BASE_CLEANROOM_F03_0002_0310"
    )


# ------------------------------------------------------------------
# El caso que motiva D-180
# ------------------------------------------------------------------

def test_base_cleanroom_correcto_es_PASS_y_sin_razones() -> None:
    """Es exactamente el escenario de F04-02, que acabo etiquetado FALLO."""
    resultado, razones = runner.veredicto(
        HEAD, "0002", runner.SCOPE_BASE, [], JUNIT_VERDE, True
    )
    assert resultado == "PASS_BASE_CLEANROOM_F03_0002_0310"
    assert razones == []


def test_no_aplicar_0001_ya_no_es_una_razon_de_fallo() -> None:
    _, razones = runner.veredicto(
        HEAD, "0002", runner.SCOPE_BASE, [], JUNIT_VERDE, True
    )
    assert not any("0001" in r for r in razones)


def test_instancia_completa_sigue_siendo_PASS() -> None:
    resultado, razones = runner.veredicto(
        HEAD, "0001", runner.SCOPE_INSTANCIA, [], JUNIT_VERDE, True
    )
    assert resultado == "PASS_INSTANCE_BOOTSTRAP_F03_0001_0310"
    assert razones == []


# ------------------------------------------------------------------
# Ninguna condicion del PASS se relaja, en NINGUNO de los dos alcances
# ------------------------------------------------------------------

@pytest.mark.parametrize(
    "scope, primera",
    [(runner.SCOPE_INSTANCIA, "0001"), (runner.SCOPE_BASE, "0002")],
)
def test_base_no_virgen_nunca_es_PASS(scope, primera) -> None:
    resultado, razones = runner.veredicto(
        HEAD, primera, scope, [], JUNIT_VERDE, False
    )
    assert resultado.startswith("FALLO_")
    assert any("virgen" in r for r in razones)


@pytest.mark.parametrize(
    "scope, primera",
    [(runner.SCOPE_INSTANCIA, "0001"), (runner.SCOPE_BASE, "0002")],
)
def test_sin_junit_nunca_es_PASS(scope, primera) -> None:
    resultado, razones = runner.veredicto(HEAD, primera, scope, [], None, True)
    assert resultado.startswith("FALLO_")
    assert any("JUnit" in r for r in razones)


@pytest.mark.parametrize(
    "scope, primera",
    [(runner.SCOPE_INSTANCIA, "0001"), (runner.SCOPE_BASE, "0002")],
)
def test_junit_sin_tests_nunca_es_PASS(scope, primera) -> None:
    resultado, razones = runner.veredicto(
        HEAD, primera, scope, [], JUNIT_VACIO, True
    )
    assert resultado.startswith("FALLO_")
    assert any("ningun test" in r for r in razones)


@pytest.mark.parametrize(
    "scope, primera",
    [(runner.SCOPE_INSTANCIA, "0001"), (runner.SCOPE_BASE, "0002")],
)
def test_suite_roja_nunca_es_PASS(scope, primera) -> None:
    resultado, razones = runner.veredicto(
        HEAD, primera, scope, [], JUNIT_ROJO, True
    )
    assert resultado.startswith("FALLO_")
    assert any("no esta verde" in r for r in razones)


@pytest.mark.parametrize(
    "scope, primera",
    [(runner.SCOPE_INSTANCIA, "0001"), (runner.SCOPE_BASE, "0002")],
)
def test_discrepancia_de_contrato_nunca_es_PASS(scope, primera) -> None:
    resultado, razones = runner.veredicto(
        HEAD, primera, scope, ["tablas esperado=80 obtenido=79"], JUNIT_VERDE, True
    )
    assert resultado.startswith("FALLO_")
    assert "tablas esperado=80 obtenido=79" in razones


def test_las_razones_de_contrato_se_conservan_intactas() -> None:
    """El veredicto no reescribe ni resume lo que le llega de `comparar`."""
    entrada = ["a esperado=1 obtenido=2", "b esperado=3 obtenido=4"]
    _, razones = runner.veredicto(
        HEAD, "0002", runner.SCOPE_BASE, entrada, JUNIT_VERDE, True
    )
    assert razones == entrada


# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------

def test_el_manifest_registra_el_alcance(tmp_path: pathlib.Path) -> None:
    destino = tmp_path / "manifest.json"
    runner.escribir_manifiesto(
        destino,
        observado={"base": "gapto2027_cleanroom"},
        declarado={"head_declarado": HEAD},
        resultado="PASS_BASE_CLEANROOM_F03_0002_0310",
        razones=[],
        scope=runner.SCOPE_BASE,
    )
    contenido = json.loads(destino.read_text(encoding="utf-8"))
    assert contenido["scope"] == runner.SCOPE_BASE
    assert contenido["version"] == "0.11.0"
    assert "D-180" in contenido["decision"]
    # observado y declarado siguen separados: es el requisito de D-136.
    assert contenido["observado"]["base"] == "gapto2027_cleanroom"
    assert contenido["declarado"]["head_declarado"] == HEAD
