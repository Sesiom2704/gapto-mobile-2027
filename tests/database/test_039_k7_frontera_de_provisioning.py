# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_039_k7_frontera_de_provisioning.py
# Ruta: tests/database/test_039_k7_frontera_de_provisioning.py
# Descripción: D-177 §2. Regresión de la comprobación de virginidad de
#              scripts/postgres/run_clean_room.py, corregida en v0.10.1 (K7).
#
#              EL DEFECTO. Hasta v0.10.0 la comprobación miraba ÚNICAMENTE el
#              schema `gapto`. La migration 0002 crea `gapto_ext`, instala
#              btree_gist y pg_trgm dentro de él, y crea `gapto`, todo con
#              CREATE ... sin IF NOT EXISTS. Un residuo en `gapto_ext`, o esas
#              extensiones ya instaladas, pasaban el preflight en verde y hacían
#              fallar 0002 a mitad de cadena.
#
#              LA FRONTERA NO ES ABSOLUTA, ES CONDICIONAL. D-177 advierte
#              expresamente de no inventar una regla "gapto_ext siempre
#              ausente". Depende del tramo que se vaya a aplicar:
#                - cadena que INCLUYE 0002 -> ambos schemas ausentes y ninguna
#                  de las dos extensiones instalada;
#                - cadena que EMPIEZA DESPUÉS de 0002 -> ambos schemas
#                  presentes, porque 0002 ya los creó. Su ausencia es entonces
#                  tan sospechosa como su presencia en el caso anterior.
#
#              POR QUÉ ES UN TEST DE PREDICADO Y NO DE BASE DE DATOS. Se prueba
#              `problemas_de_frontera`, que es una función pura sobre el estado
#              leído del catálogo. Así el caso B -residuo centinela en
#              `gapto_ext`- se ejercita de verdad, en lugar de requerir ensuciar
#              una base real para observarlo. La lectura del catálogo en sí
#              (`estado_de_provisioning`) la ejercita cada ejecución del
#              clean-room.
#
#              Este fichero NO requiere conexión: es el único de la suite que
#              puede correr sin base de datos.
#
# Decision: D-177 §2 (K7)
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "postgres" / "run_clean_room.py"


@pytest.fixture(scope="module")
def runner():
    """Carga run_clean_room.py como módulo sin ejecutarlo como script."""
    if not RUNNER.is_file():
        pytest.fail(f"no se encuentra el runner en {RUNNER}")
    spec = importlib.util.spec_from_file_location("run_clean_room_bajo_prueba", RUNNER)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _estado(gapto: bool, gapto_ext: bool,
            btree_gist: str | None = None, pg_trgm: str | None = None) -> dict:
    return {
        "schemas": {"gapto": gapto, "gapto_ext": gapto_ext},
        "extensiones": {"btree_gist": btree_gist, "pg_trgm": pg_trgm},
    }


# ------------------------------------------------------------
# A. Estado limpio esperado -> PASS
# ------------------------------------------------------------

def test_a_base_virgen_para_cadena_con_0002(runner) -> None:
    """Ningún schema de aplicación y ninguna extensión: frontera correcta."""
    assert runner.problemas_de_frontera(_estado(False, False), incluye_0002=True) == []


def test_a_tramo_posterior_a_0002_con_schemas_presentes(runner) -> None:
    """Reanudar después de 0002 exige que 0002 ya haya corrido."""
    assert runner.problemas_de_frontera(_estado(True, True), incluye_0002=False) == []


# ------------------------------------------------------------
# B. Residuo no autorizado -> FAIL (sin --permitir-sucia)
# ------------------------------------------------------------

def test_b_residuo_en_gapto_ext_es_rechazado(runner) -> None:
    """EL CASO QUE v0.10.0 DEJABA PASAR.

    `gapto` ausente y `gapto_ext` presente: la comprobación anterior daba verde
    porque solo miraba `gapto`, y 0002 fallaba después al hacer CREATE SCHEMA
    gapto_ext."""
    problemas = runner.problemas_de_frontera(_estado(False, True), incluye_0002=True)
    assert len(problemas) == 1
    assert "gapto_ext" in problemas[0]


def test_b_extension_centinela_ya_instalada_es_rechazada(runner) -> None:
    """Extensión instalada en otro schema: 0002 la crea WITH SCHEMA gapto_ext y
    fallaría. Ningún schema de aplicación existe, de modo que la comprobación
    anterior tampoco lo habría visto."""
    problemas = runner.problemas_de_frontera(
        _estado(False, False, btree_gist="public"), incluye_0002=True)
    assert len(problemas) == 1
    assert "btree_gist" in problemas[0] and "public" in problemas[0]


def test_b_schema_gapto_presente_sigue_rechazandose(runner) -> None:
    """Regresión del comportamiento que v0.10.0 SÍ tenía: no debe perderse."""
    problemas = runner.problemas_de_frontera(_estado(True, False), incluye_0002=True)
    assert any("gapto" in p for p in problemas)


def test_b_tramo_posterior_a_0002_sin_schemas_es_rechazado(runner) -> None:
    """La frontera es condicional en los dos sentidos: reanudar después de 0002
    sobre una base sin schemas significa que falta la mitad de la cadena."""
    problemas = runner.problemas_de_frontera(_estado(False, False), incluye_0002=False)
    assert len(problemas) == 2


def test_b_base_completa_acumula_todas_las_discrepancias(runner) -> None:
    """Base ya migrada frente a una cadena que incluye 0002: dos schemas y dos
    extensiones. El mensaje debe enumerarlas todas, no abortar en la primera."""
    problemas = runner.problemas_de_frontera(
        _estado(True, True, btree_gist="gapto_ext", pg_trgm="gapto_ext"),
        incluye_0002=True)
    assert len(problemas) == 4


# ------------------------------------------------------------
# Compatibilidad y contrato del runner
# ------------------------------------------------------------

def test_base_esta_vacia_conserva_su_semantica(runner) -> None:
    """base_esta_vacia() se mantiene como atajo para el tramo que incluye 0002."""
    assert runner.problemas_de_frontera(_estado(False, False), incluye_0002=True) == []
    assert runner.problemas_de_frontera(_estado(False, True), incluye_0002=True) != []


def test_la_frontera_cubre_ambos_namespaces_y_ambas_extensiones(runner) -> None:
    """Si alguien añadiera un tercer namespace o una extensión al provisioning,
    este test obliga a actualizar también la comprobación de frontera."""
    assert set(runner.NAMESPACES_DE_APLICACION) == {"gapto", "gapto_ext"}
    assert set(runner.EXTENSIONES_DE_APLICACION) == {"btree_gist", "pg_trgm"}


def test_permitir_sucia_sigue_siendo_la_unica_salida(runner) -> None:
    """D-177 §2: no debilitar --permitir-sucia. El predicado no conoce esa
    bandera; decide solo sobre el estado observado, y saltársela sigue siendo
    una decisión explícita del operador en el punto de llamada."""
    import inspect
    firma = inspect.signature(runner.problemas_de_frontera)
    assert list(firma.parameters) == ["estado", "incluye_0002"]
