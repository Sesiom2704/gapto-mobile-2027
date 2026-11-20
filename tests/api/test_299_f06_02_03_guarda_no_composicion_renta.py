# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_299_f06_02_03_guarda_no_composicion_renta.py
# Ruta: tests/api/test_299_f06_02_03_guarda_no_composicion_renta.py
# Descripcion: F06-02/03 · GUARDA PROPIA de no-composicion de renta (contrato v1.1 §VII.1; PC-CON-01; INV-ALQ-02;
#   D-A-08 y D-A-09). NO sustituye ni amplia a test_230 (que NO se toca: exige que NINGUNA ruta alcance sus
#   objetivos y hoy rutas legitimas alcanzan escritores de previsiones). Esta guarda mira SOLO desde los modulos
#   nuevos del bloque (`backend/app/contratos/*`) y falla si alcanzan cualquiera de los escritores de reglas o de
#   previsiones, IDENTIFICADOS POR NOMBRE CUALIFICADO (modulo + funcion; `actualizar_vinculo` existe tambien en
#   tesoreria_repository y ese NO es objetivo).
#   Metodo (analisis estatico, sin base de datos; no exige GAPTO_TEST_DATABASE_URL):
#     1. CIERRE TRANSITIVO DE IMPORTACIONES (incluidas las perezosas dentro de funciones) de los modulos del bloque:
#        no puede contener ninguno de los cuatro modulos de escritores (reglas_repository, previsiones_repository,
#        reglas_service, previsiones_service). Es la comprobacion principal: sin importarlos no se les alcanza.
#     2. Ningun modulo del bloque importa ReglasService, PrevisionesService ni esos repositorios (directo).
#     3. Ninguna referencia (`Name`, `Attribute`, nombre importado o cadena identificador) a los escritores de
#        reglas ni de previsiones por su nombre (salvo `actualizar_vinculo`, que solo cuenta cualificado).
#     4. Sin despacho dinamico (importlib, __import__, getattr con nombre no constante, eval/exec): un modulo del
#        bloque no puede esquivar el analisis.
#     5. Integridad de la propia guarda: cada identidad cualificada de PROHIBIDOS existe de verdad en backend/app
#        (si un escritor se renombra, la guarda lo dice en vez de quedarse ciega).
#     6. Mutantes DIFERENCIADOS sobre una copia en memoria (nunca en disco): (a) un servicio del bloque llama a un
#        escritor de REGLAS (`ReglasService.crear_regla`) -> la guarda falla; (b) otro llama a un escritor de
#        PREVISIONES (`insertar_prevision`) -> falla; (c) control: el codigo real pasa y test_230 sigue intacto.
#   Negativo HTTP de esta garantia: ver test_300 (`renta`/`fianza` -> RENTA_NO_DISPONIBLE, 0 filas).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4; escrito sin ejecutar contra base: no la necesita)
# ============================================================

from __future__ import annotations

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
APP = BACKEND / "app"
PAQUETE = "app.contratos"

#: Identidades cualificadas (modulo, funcion) de los escritores prohibidos (revalidacion del paso 1, §6; D-A-08/09).
PROHIBIDOS: frozenset[tuple[str, str]] = frozenset({
    # reglas
    ("app.repositories.reglas_repository", "tocar_regla"),
    ("app.repositories.reglas_repository", "insertar_regla_si_no_existe"),
    ("app.repositories.reglas_repository", "insertar_version"),
    ("app.repositories.reglas_repository", "cerrar_version"),
    ("app.repositories.reglas_repository", "insertar_excepcion"),
    ("app.repositories.reglas_repository", "actualizar_excepcion"),
    ("app.services.reglas_service", "crear_regla"),
    ("app.services.reglas_service", "crear_version"),
    ("app.services.reglas_service", "corregir_excepcion"),
    ("app.services.reglas_service", "registrar_excepcion"),
    # previsiones (el `actualizar_vinculo` de PREVISIONES, no el de tesoreria_repository)
    ("app.repositories.previsiones_repository", "insertar_prevision"),
    ("app.repositories.previsiones_repository", "tocar_prevision"),
    ("app.repositories.previsiones_repository", "actualizar_prevision"),
    ("app.repositories.previsiones_repository", "insertar_vinculo"),
    ("app.repositories.previsiones_repository", "actualizar_vinculo"),
    ("app.repositories.previsiones_repository", "borrar_vinculo"),
    ("app.services.previsiones_service", "generar_calendario"),
    ("app.services.previsiones_service", "recalcular_futuras"),
    ("app.services.previsiones_service", "crear_manual"),
    ("app.services.previsiones_service", "ajustar_importe_cuota_hipoteca"),
})
MODULOS_PROHIBIDOS = frozenset(m for m, _ in PROHIBIDOS)
#: Nombres que, solos, identifican sin ambiguedad un escritor prohibido (`actualizar_vinculo` tiene homonimo).
NOMBRES_PROHIBIDOS = frozenset(n for _, n in PROHIBIDOS) - {"actualizar_vinculo"}
#: Clases de servicio prohibidas (no deben importarse ni referenciarse).
CLASES_PROHIBIDAS = frozenset({"ReglasService", "PrevisionesService"})
DINAMICOS_NOMBRE = {"eval", "exec", "__import__", "attrgetter", "methodcaller", "import_module", "globals", "vars"}
ACCESO_ATRIBUTO = {"getattr", "setattr", "hasattr", "delattr"}


# ---------------------------------------------------------------- indice de modulos (nombre -> fuente)
def _nombre_modulo(ruta: pathlib.Path) -> str:
    partes = list(ruta.relative_to(BACKEND).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def indice_real() -> dict[str, str]:
    return {_nombre_modulo(p): p.read_text(encoding="utf-8") for p in sorted(APP.rglob("*.py"))}


def raices_reales(indice: dict[str, str]) -> list[str]:
    return sorted(m for m in indice if m == PAQUETE or m.startswith(PAQUETE + "."))


def _importaciones(fuente: str, indice: dict[str, str]) -> set[str]:
    """Modulos de backend/app importados por `fuente`, en cualquier punto (tambien dentro de funciones)."""
    salida: set[str] = set()
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            if n.module in indice:
                salida.add(n.module)
            for a in n.names:
                if f"{n.module}.{a.name}" in indice:
                    salida.add(f"{n.module}.{a.name}")
        elif isinstance(n, ast.Import):
            salida.update(a.name for a in n.names if a.name in indice)
    return salida


def cierre(raices: list[str], indice: dict[str, str]) -> set[str]:
    vistos, pendientes = set(raices), list(raices)
    while pendientes:
        for destino in _importaciones(indice[pendientes.pop()], indice):
            if destino not in vistos:
                vistos.add(destino)
                pendientes.append(destino)
    return vistos


def _referencias(fuente: str) -> tuple[set[str], list[str]]:
    """(nombres referenciados, usos de despacho dinamico) de un modulo."""
    refs: set[str] = set()
    dinamicos: list[str] = []
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.Name):
            refs.add(n.id)
            if n.id in DINAMICOS_NOMBRE:
                dinamicos.append(n.id)
        elif isinstance(n, ast.Attribute):
            refs.add(n.attr)
            if n.attr in DINAMICOS_NOMBRE:
                dinamicos.append(n.attr)
        elif isinstance(n, ast.alias):
            refs.add(n.name.split(".")[-1])
            if n.name.split(".")[0] == "importlib":
                dinamicos.append("importlib")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
            refs.add(n.value)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ACCESO_ATRIBUTO
                and len(n.args) >= 2 and not isinstance(n.args[1], ast.Constant)):
            dinamicos.append(n.func.id)
    return refs, dinamicos


def analizar(indice: dict[str, str], raices: list[str]) -> list[str]:
    """Violaciones de la guarda sobre las raices (modulos del bloque) del indice dado. Vacia = limpia."""
    violaciones: list[str] = []
    alcanzados = cierre(raices, indice)
    for prohibido in sorted(MODULOS_PROHIBIDOS & alcanzados):
        violaciones.append(f"importa (transitivamente) el modulo de escritores {prohibido}")
    for raiz in raices:
        directos = _importaciones(indice[raiz], indice)
        for d in sorted(directos & MODULOS_PROHIBIDOS):
            violaciones.append(f"{raiz} importa {d}")
        refs, dinamicos = _referencias(indice[raiz])
        for nombre in sorted(refs & (NOMBRES_PROHIBIDOS | CLASES_PROHIBIDAS)):
            violaciones.append(f"{raiz} referencia el escritor/servicio prohibido `{nombre}`")
        for d in sorted(set(dinamicos)):
            violaciones.append(f"{raiz} usa despacho dinamico `{d}`")
    return violaciones


# ---------------------------------------------------------------- pruebas sobre el codigo real
def test_hay_modulos_del_bloque_y_la_guarda_ve_el_cierre():
    indice = indice_real()
    raices = raices_reales(indice)
    assert {"app.contratos.servicio", "app.contratos.servicios", "app.contratos.terceros",
            "app.contratos.lecturas", "app.contratos.rutas", "app.contratos.repositorio"} <= set(raices)
    # la guarda ve a traves de los modulos de F05 y B1 que el bloque reutiliza (cierre no trivial)
    assert {"app.propiedades.servicio", "app.terceros.servicio", "app.actores.servicio"} <= cierre(raices, indice)


def test_el_bloque_no_alcanza_escritores_de_reglas_ni_de_previsiones():
    indice = indice_real()
    assert analizar(indice, raices_reales(indice)) == []


def test_ningun_modulo_del_bloque_importa_los_servicios_ni_repositorios_de_reglas_y_previsiones():
    indice = indice_real()
    for raiz in raices_reales(indice):
        assert not (_importaciones(indice[raiz], indice) & MODULOS_PROHIBIDOS), raiz


def test_identidades_cualificadas_existen_en_backend():
    """La guarda no queda ciega si un escritor se renombra o se mueve: cada identidad de PROHIBIDOS debe existir."""
    indice = indice_real()
    for modulo, nombre in sorted(PROHIBIDOS):
        assert modulo in indice, f"el modulo {modulo} ya no existe: actualizar PROHIBIDOS"
        definidas = {n.name for n in ast.walk(ast.parse(indice[modulo]))
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert nombre in definidas, f"{modulo}.{nombre} ya no existe: actualizar PROHIBIDOS"


def test_el_homonimo_de_tesoreria_no_es_objetivo():
    """`actualizar_vinculo` de tesoreria_repository NO es un escritor prohibido (D-A-08): solo se identifica el de
    previsiones por su modulo."""
    assert ("app.repositories.tesoreria_repository", "actualizar_vinculo") not in PROHIBIDOS
    assert ("app.repositories.previsiones_repository", "actualizar_vinculo") in PROHIBIDOS


def test_el_bloque_no_escribe_regla_renta_id_ni_tablas_de_reglas_o_previsiones():
    """Complemento textual: ningun SQL del bloque inserta o actualiza las tablas de renta, reglas o previsiones."""
    prohibidas = ("regla_renta_id =", "INSERT INTO gapto.reglas_financieras", "INSERT INTO gapto.regla_versiones",
                  "INSERT INTO gapto.previsiones", "UPDATE gapto.previsiones", "UPDATE gapto.reglas_financieras",
                  "UPDATE gapto.regla_versiones", "INSERT INTO gapto.hecho", "hecho_entidades")
    for raiz, fuente in indice_real().items():
        if raiz.startswith(PAQUETE):
            for trozo in prohibidas:
                assert trozo not in fuente, f"{raiz} contiene `{trozo}`"


# ---------------------------------------------------------------- mutantes diferenciados (en memoria)
MUTANTE_A_REGLAS = (
    "from app.services.reglas_service import ReglasService\n"
    "def crea_renta(sesion):\n    return ReglasService().crear_regla(sesion)\n"
)
MUTANTE_B_PREVISIONES = (
    "from app.repositories import previsiones_repository as prev\n"
    "def crea_cuota(sesion):\n    return prev.insertar_prevision(sesion)\n"
)
MUTANTE_B_LAZY = "def crea_cuota(sesion):\n    from app.repositories.previsiones_repository import insertar_prevision\n    return insertar_prevision(sesion)\n"
MUTANTE_DINAMICO = "import importlib\ndef x():\n    return importlib.import_module('app.services.reglas_service')\n"


def _con_mutante(fuente: str) -> tuple[dict[str, str], list[str]]:
    indice = indice_real()
    nombre = f"{PAQUETE}.mutante_de_prueba"
    indice[nombre] = fuente
    return indice, raices_reales(indice) + [nombre]


def test_mutante_a_un_servicio_del_bloque_llama_a_un_escritor_de_reglas_falla():
    indice, raices = _con_mutante(MUTANTE_A_REGLAS)
    violaciones = analizar(indice, raices)
    assert any("reglas_service" in v for v in violaciones), violaciones
    assert any("crear_regla" in v or "ReglasService" in v for v in violaciones), violaciones


def test_mutante_b_un_servicio_del_bloque_llama_a_un_escritor_de_previsiones_falla():
    for fuente in (MUTANTE_B_PREVISIONES, MUTANTE_B_LAZY):
        indice, raices = _con_mutante(fuente)
        violaciones = analizar(indice, raices)
        assert any("previsiones_repository" in v for v in violaciones), violaciones
        assert any("insertar_prevision" in v for v in violaciones), violaciones


def test_mutante_despacho_dinamico_falla():
    indice, raices = _con_mutante(MUTANTE_DINAMICO)
    assert any("despacho dinamico" in v for v in analizar(indice, raices))


def test_control_el_codigo_real_pasa_y_test_230_sigue_intacto():
    indice = indice_real()
    assert analizar(indice, raices_reales(indice)) == []
    t230 = (RAIZ / "tests" / "api" / "test_230_f05_d052_no_invocacion_f06.py").read_text(encoding="utf-8")
    # el original conserva sus tres objetivos y NO se amplia (AJ-COMP-02): sin escritores de previsiones nuevos
    assert '"crear_version": "app/services/reglas_service.py"' in t230
    assert '"corregir_excepcion": "app/services/reglas_service.py"' in t230
    assert '"recalcular_futuras": "app/services/previsiones_service.py"' in t230
    assert "insertar_prevision" not in t230 and "ajustar_importe_cuota_hipoteca" not in t230


@pytest.mark.parametrize("modulo", ["app.contratos.servicio", "app.contratos.servicios", "app.contratos.terceros"])
def test_los_writers_no_importan_la_composicion_de_op22_ni_op21(modulo):
    """INV-ALQ-10 y decision 1: ningun writer del bloque compone OP-22/OP-21 ni toma INVERSIONES."""
    fuente = indice_real()[modulo]
    for trozo in ("efectos_a_eliminar", "entidades_a_eliminar", "gapto:INVERSIONES"):
        assert trozo not in fuente
