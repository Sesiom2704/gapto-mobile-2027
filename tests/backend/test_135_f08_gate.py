# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_135_f08_gate.py
# Ruta: tests/backend/test_135_f08_gate.py
# Descripcion: F04-D042 §35. Gate de cobertura de la bateria integral.
#
#   QUE ES Y QUE NO ES. Este gate comprueba que EXISTE un escenario que
#   declara cubrir cada elemento exigido, y que ese escenario forma parte de
#   una suite que pasa. No comprueba que lo cubra bien: eso lo hace el
#   oraculo de cada escenario. Los dos niveles son necesarios y ninguno
#   sustituye al otro.
#
#   POR QUE UN TEST Y NO UN RUNNER. El mandato admite no construir un runner
#   complejo si pytest mas un manifest determinista demuestran lo mismo con
#   menos superficie. Un gate que vive en la suite se ejecuta siempre, en
#   local y en Neon, sin un ejecutable aparte que mantener, versionar y
#   verificar. Si alguien borra un escenario, la suite cae ese mismo dia.
#
#   IMPORTACION EXPLICITA. Los modulos de escenarios se importan aqui a
#   proposito: si el gate dependiese del orden de recoleccion de pytest,
#   ejecutarlo solo —`pytest test_135`— daria un falso FAIL, y ejecutarlo con
#   `-k` podria dar un falso PASS con la mitad de los escenarios sin cargar.
#
#   LOS 40 ESCENARIOS HISTORICOS NO SE COMPRUEBAN. F04-D042 resolvio el §5.2
#   por la opcion (b): el inventario exacto de F04-00-A no es recuperable,
#   permanece como dato historico agregado y queda prohibido reconstruirlo
#   por inferencia. Este gate no tiene, ni debe tener, una comprobacion 40/40.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import importlib
import os
import pathlib

import pytest

from f08_cobertura import (
    CASOS,
    CRUZADOS,
    DIMENSIONES,
    EXCEPCIONES,
    INVARIANTES,
    NATURALEZAS,
    OPERACIONES,
    OPERACIONES_POSTERIORES,
    PROPIEDADES,
    REGISTRO,
    faltantes,
)

MODULOS_DE_ESCENARIOS: tuple[str, ...] = (
    "test_130_f08_casos_nucleo",
    "test_131_f08_casos_posiciones",
    "test_132_f08_multiactor_y_excepciones",
    "test_133_f08_cruzados",
    "test_134_f08_propiedades",
)

UNIVERSOS: tuple[tuple[str, object, str], ...] = (
    ("casos", CASOS, "22 casos reales canonicos"),
    ("operaciones", OPERACIONES, "20 operaciones internas"),
    ("invariantes", INVARIANTES, "21 invariantes"),
    ("naturalezas", NATURALEZAS, "6 naturalezas de efecto"),
    ("dimensiones", DIMENSIONES, "8 dimensiones nucleares"),
    ("excepciones", EXCEPCIONES, "3 escenarios de excepcion"),
    ("cruzados", CRUZADOS, "12 escenarios cruzados"),
    ("propiedades", PROPIEDADES, "28 propiedades transversales"),
)


@pytest.fixture(scope="module", autouse=True)
def _cargar_escenarios() -> None:
    for modulo in MODULOS_DE_ESCENARIOS:
        importlib.import_module(modulo)


@pytest.mark.parametrize(
    "etiqueta, universo, descripcion",
    UNIVERSOS,
    ids=[etiqueta for etiqueta, _, _ in UNIVERSOS],
)
def test_cobertura_completa(etiqueta: str, universo, descripcion: str) -> None:
    """Cada elemento exigido tiene al menos un escenario que lo declara."""
    ausentes = faltantes(etiqueta, universo)
    assert not ausentes, (
        f"{descripcion}: sin escenario declarado para {ausentes}"
    )


def test_no_se_declara_cobertura_fuera_de_universo() -> None:
    """Nada registrado puede quedar fuera de su universo.

    `cubre` ya lo valida al decorar, pero esta afirmacion protege el caso en
    que alguien amplie un universo y olvide el gate: aqui se veria de
    inmediato que el recuento exigido dejo de cuadrar.
    """
    universos = {
        "casos": set(CASOS),
        "operaciones": set(OPERACIONES) | set(OPERACIONES_POSTERIORES),
        "invariantes": set(INVARIANTES),
        "naturalezas": set(NATURALEZAS),
        "dimensiones": set(DIMENSIONES),
        "excepciones": set(EXCEPCIONES),
        "cruzados": set(CRUZADOS),
        "propiedades": set(PROPIEDADES),
    }
    for etiqueta, universo in universos.items():
        sobrantes = sorted(REGISTRO.get(etiqueta, set()) - universo)
        assert not sobrantes, f"{etiqueta}: registrado fuera de universo {sobrantes}"


def test_matriz_de_cobertura(capsys: pytest.CaptureFixture[str]) -> None:
    """Emite la matriz legible por maquina y por humano.

    La evidencia primaria vive fuera del repositorio (§12C.11): si
    `GAPTO_F08_MATRIZ` apunta a una ruta, la matriz se escribe alli; si no,
    se imprime. En ningun caso se escribe dentro del arbol.
    """
    lineas: list[str] = ["# GaptoMobile 2027 — F04-08 · matriz de cobertura", ""]
    veredicto = "PASS"

    for etiqueta, universo, descripcion in UNIVERSOS:
        cubiertos = sorted(set(universo) & REGISTRO.get(etiqueta, set()))
        ausentes = faltantes(etiqueta, universo)
        if ausentes:
            veredicto = "FAIL"
        lineas.append(
            f"{etiqueta:12s} {len(cubiertos):2d}/{len(universo):2d}  {descripcion}"
        )
        if ausentes:
            lineas.append(f"{'':12s} FALTAN: {', '.join(ausentes)}")

    posteriores = sorted(
        REGISTRO.get("operaciones", set()) & set(OPERACIONES_POSTERIORES)
    )
    lineas += [
        "",
        "Operaciones posteriores al catalogo F04-00-C, registradas y NO exigidas "
        f"por el criterio de cierre: {', '.join(posteriores) or 'ninguna'}",
        "",
        "Escenarios historicos de F04-00-A: NO comprobados. F04-D042 resolvio "
        "el §5.2 por la opcion (b); el inventario de los 40 no es recuperable "
        "y queda prohibido reconstruirlo por inferencia.",
        "",
        f"VEREDICTO: {veredicto}",
    ]
    salida = "\n".join(lineas)

    destino = os.environ.get("GAPTO_F08_MATRIZ")
    if destino:
        ruta = pathlib.Path(destino)
        repo = pathlib.Path(__file__).resolve().parents[2]
        assert repo not in ruta.resolve().parents, (
            "la evidencia primaria no se escribe dentro del repositorio"
        )
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(salida + "\n", encoding="utf-8")
    with capsys.disabled():
        print("\n" + salida)

    assert veredicto == "PASS"
