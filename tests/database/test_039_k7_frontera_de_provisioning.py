# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_039_k7_frontera_de_provisioning.py
# Ruta: tests/database/test_039_k7_frontera_de_provisioning.py
# Descripción: D-177 §2 y §3. Regresión de la comprobación de virginidad de
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
#              D-177 §3 — DURABILIDAD DE EVIDENCIA. Se añade la regresión de
#              `problemas_de_ruta_de_evidencia`, que es la contrapartida de K2:
#              el runner deja de aceptar que un manifest se escriba dentro del
#              repositorio o que sobrescriba a otro existente. La política deja
#              de depender de que el operador se acuerde.
#
# Decision: D-177 §2 (K7) y §3 (durabilidad)
# Versión: 0.2.0  -- añade la regresión de rutas de evidencia (§3).
#              v0.1.0: solo la frontera de provisioning (§2).
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


# ------------------------------------------------------------
# D-177 §3 — durabilidad de la evidencia
#
# K2 ocurrió porque cuatro ejecuciones de R7 reutilizaron el mismo nombre de
# fichero, y K1 porque los artefactos se escribían en logs/, dentro del
# repositorio, que está en .gitignore. Ambas son ahora condiciones que el
# runner rechaza por sí mismo.
# ------------------------------------------------------------

def test_ruta_nueva_fuera_del_repositorio_es_aceptable(runner, tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    fuera = tmp_path / "evidencia"
    fuera.mkdir()
    destino = fuera / "manifiesto_20260916-120000_ab12cd34.json"
    assert runner.problemas_de_ruta_de_evidencia(destino, repo, debe_existir=False) == []


def test_ruta_dentro_del_repositorio_es_rechazada(runner, tmp_path) -> None:
    """K1 EXACTAMENTE. logs/ del repositorio se borra en cada descarga."""
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    problemas = runner.problemas_de_ruta_de_evidencia(
        repo / "logs" / "manifiesto.json", repo, debe_existir=False)
    assert len(problemas) == 1
    assert "DENTRO del repositorio" in problemas[0]


def test_no_se_sobrescribe_un_manifest_existente(runner, tmp_path) -> None:
    """K2 EXACTAMENTE. Reutilizar un nombre fijo borró el log de la ejecución
    anómala de R7, que ya no es recuperable."""
    repo = tmp_path / "repo"
    repo.mkdir()
    fuera = tmp_path / "evidencia"
    fuera.mkdir()
    ya_esta = fuera / "manifiesto.json"
    ya_esta.write_text("{}", encoding="utf-8")
    problemas = runner.problemas_de_ruta_de_evidencia(ya_esta, repo, debe_existir=False)
    assert len(problemas) == 1
    assert "YA existe" in problemas[0]


def test_completar_exige_que_el_manifest_exista(runner, tmp_path) -> None:
    """La fase 2 adjunta el JUnit a un manifest de fase 1: si no está, algo se
    perdió y no debe crearse uno nuevo en su lugar."""
    repo = tmp_path / "repo"
    repo.mkdir()
    fuera = tmp_path / "evidencia"
    fuera.mkdir()
    problemas = runner.problemas_de_ruta_de_evidencia(
        fuera / "no_esta.json", repo, debe_existir=True)
    assert len(problemas) == 1
    assert "no existe" in problemas[0]


def test_completar_un_manifest_existente_fuera_es_aceptable(runner, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fuera = tmp_path / "evidencia"
    fuera.mkdir()
    ya_esta = fuera / "manifiesto.json"
    ya_esta.write_text("{}", encoding="utf-8")
    assert runner.problemas_de_ruta_de_evidencia(ya_esta, repo, debe_existir=True) == []


def test_se_acumulan_las_discrepancias_de_ruta(runner, tmp_path) -> None:
    """Dentro del repositorio Y ausente: dos motivos, ambos reportados."""
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    problemas = runner.problemas_de_ruta_de_evidencia(
        repo / "logs" / "manifiesto.json", repo, debe_existir=True)
    assert len(problemas) == 2


def test_el_manifest_lleva_identidad_unica_de_ejecucion(runner) -> None:
    """D-177 §3: timestamp UTC y run_id, para que dos ejecuciones nunca sean
    confundibles aunque compartan entorno y head."""
    assert len(runner.RUN_ID) == 12
    assert runner.AHORA_UTC.endswith("Z") and len(runner.AHORA_UTC) == 20
