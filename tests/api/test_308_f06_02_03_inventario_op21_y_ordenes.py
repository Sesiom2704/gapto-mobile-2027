# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_308_f06_02_03_inventario_op21_y_ordenes.py
# Ruta: tests/api/test_308_f06_02_03_inventario_op21_y_ordenes.py
# Descripcion: F06-02/03 · INVENTARIOS estaticos del bloque (sin base de datos; ejecutables):
#     O-20 / INV-ALQ-10  ningun adaptador de F06-02/03 envia `efectos_a_eliminar` ni `entidades_a_eliminar` a OP-21 ni
#                        importa la composicion de OP-21/OP-22 (F04-D073: CONTRATO y SERVICIO siguen reservados;
#                        R-L12-01, R-L17-01). Mutante: un adaptador con retiradas -> el inventario falla.
#     INV-ALQ-11         el PRIMER recurso de cada writer es el 0P de intencion (`bloquear_intencion_propiedad`,
#                        importada, nunca copiada: test_233 exige el literal `gapto:INTENCION` solo en su funcion).
#                        Mutante: writer sin 0P -> falla.
#     §1.3               orden de recursos por posicion de llamadas: 0P -> propiedad -> terceros -> contrato -> hijas.
#                        Mutante: terceros antes que la propiedad (C-CON-01 / C-CON-05) -> falla.
#     INV-ALQ-16         nada se borra: ni DELETE, ni DDL, ni GRANT/REVOKE en el paquete; SQL de escritura solo sobre
#                        las tablas del bloque; `regla_renta_id` y `hecho_entidades` no se escriben.
#   Los inventarios de otras fases (test_154 I13a, test_182 CAPA_F05, test_123, test_281...) NO se adaptan aqui: si una
#   adaptacion fuera necesaria se hara con ficha L-06-T3 cuando haya base (ver NOTAS_PASOS_3_4.md).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4; escrito y ejecutable sin base)
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PAQUETE = RAIZ / "backend" / "app" / "contratos"

#: Writers publicos y la funcion que da su primer recurso. Los que delegan en un preludio comun se verifican
#: tambien en el preludio (`abrir`, `_abrir_tercero`, `_comando_arbol`).
WRITERS_CONTRATOS = ("alta", "editar", "terminar", "corregir_terminacion", "formalizar", "cancelar", "sucesor",
                     "anadir_persona", "cerrar_persona", "corregir_persona", "nueva_clausula", "corregir_clausula")
WRITERS_SERVICIOS = ("alta", "editar", "baja", "tratamiento")
WRITERS_TERCEROS = ("anadir_roles", "asignar_clasificaciones", "crear_clasificacion", "renombrar_clasificacion",
                    "mover_clasificacion", "desactivar_clasificacion", "reactivar_clasificacion")
PRELUDIOS = {"servicio": ("abrir",), "terceros": ("_abrir_tercero", "_comando_arbol")}
PRIMER_RECURSO = {"bloquear_intencion_propiedad", "abrir", "_abrir_tercero", "_comando_arbol"}
SQL_PROHIBIDO = re.compile(r"\b(DELETE\s+FROM|TRUNCATE|ALTER\s+TABLE|CREATE\s+(TABLE|INDEX|FUNCTION|TRIGGER)|DROP\s+|GRANT\s|REVOKE\s)", re.I)
TABLAS_ESCRITURA_PERMITIDAS = {"entidades", "contratos", "contrato_participantes", "contrato_revision_renta_versiones",
                               "contrato_servicios", "servicios", "propiedad_servicios", "tercero_roles",
                               "tercero_clasificaciones", "clasificaciones_tercero"}


def fuentes() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(PAQUETE.glob("*.py"))}


def _funcion(fuente: str, nombre: str) -> ast.FunctionDef:
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
    raise AssertionError(f"no existe la funcion {nombre}")


def _llamadas(f: ast.FunctionDef) -> list[tuple[int, int, str, bool]]:
    """(linea, columna, nombre llamado, ¿recibe `sesion`?) en orden de aparicion en el codigo."""
    salida = []
    for n in _sin_anidadas(f):
        if isinstance(n, ast.Call):
            nombre = n.func.id if isinstance(n.func, ast.Name) else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
            con_sesion = any(isinstance(a, ast.Name) and a.id == "sesion" for a in n.args)
            salida.append((n.lineno, n.col_offset, nombre, con_sesion))
    return sorted(salida)


def _sin_anidadas(f: ast.AST):
    """Nodos de la funcion SIN entrar en funciones o lambdas anidadas (sus llamadas no son del flujo principal)."""
    pendientes = list(ast.iter_child_nodes(f))
    while pendientes:
        n = pendientes.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            pendientes.extend(ast.iter_child_nodes(n))


def primer_recurso(fuente: str, funcion: str) -> str | None:
    """Nombre de la PRIMERA llamada que recibe `sesion`; el primer recurso de una transaccion."""
    for _, _, nombre, con_sesion in _llamadas(_funcion(fuente, funcion)):
        if con_sesion:
            return nombre
    return None


def orden(fuente: str, funcion: str) -> list[str]:
    return [n for _, _, n, _ in _llamadas(_funcion(fuente, funcion))]


def _en_orden(nombres: list[str], esperado: list[str]) -> bool:
    """`esperado` aparece como subsecuencia de `nombres` (primera aparicion de cada uno, en ese orden)."""
    pos = -1
    for e in esperado:
        try:
            pos = nombres.index(e, pos + 1)
        except ValueError:
            return False
    return True


# ================================================================== O-20 / INV-ALQ-10
PROHIBIDO_OP21 = ("efectos_a_eliminar", "entidades_a_eliminar", "correcciones_service", "compuesto_service",
                  "compuesto_repository", "gapto:INVERSIONES", "hecho_entidades", "regla_renta_id =")


def test_o_20_ningun_adaptador_envia_retiradas_a_op21():
    for modulo, fuente in fuentes().items():
        for trozo in PROHIBIDO_OP21:
            assert trozo not in fuente, f"{modulo}.py contiene `{trozo}` (INV-ALQ-10)"


def test_o_20_mutante_un_adaptador_con_retiradas_hace_fallar_el_inventario():
    mutante = "def retira(sesion):\n    return {'efectos_a_eliminar': [1], 'entidades_a_eliminar': [2]}\n"
    assert any(t in mutante for t in PROHIBIDO_OP21)


def test_sin_delete_ddl_ni_grants_en_el_paquete():
    for modulo, fuente in fuentes().items():
        cadenas = [n.value for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and len(n.value) > 25]
        for cadena in cadenas:
            assert not SQL_PROHIBIDO.search(cadena), f"{modulo}.py: SQL prohibido en `{cadena[:60]}`"


def test_el_sql_de_escritura_solo_toca_las_tablas_del_bloque():
    patron = re.compile(r"\b(?:INSERT\s+INTO|UPDATE)\s+gapto\.(\w+)", re.I)
    vistas: set[str] = set()
    for fuente in fuentes().values():
        for n in ast.walk(ast.parse(fuente)):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                vistas |= set(patron.findall(n.value))
    assert vistas and vistas <= TABLAS_ESCRITURA_PERMITIDAS, sorted(vistas - TABLAS_ESCRITURA_PERMITIDAS)
    # ninguna escribe renta, reglas, previsiones, hechos ni la tabla `terceros` (eso es del writer de F05)
    assert not vistas & {"reglas_financieras", "regla_versiones", "previsiones", "hechos_financieros", "terceros"}


# ================================================================== INV-ALQ-11 el 0P es el primer recurso
@pytest.mark.parametrize("modulo,writers", [("servicio", WRITERS_CONTRATOS), ("servicios", WRITERS_SERVICIOS),
                                            ("terceros", WRITERS_TERCEROS)])
def test_el_primer_recurso_de_cada_writer_es_el_0p_o_su_preludio(modulo, writers):
    fuente = fuentes()[modulo]
    for w in writers:
        assert primer_recurso(fuente, w) in PRIMER_RECURSO, f"{modulo}.{w}: primer recurso = {primer_recurso(fuente, w)}"


@pytest.mark.parametrize("modulo", ["servicio", "terceros"])
def test_los_preludios_comunes_empiezan_por_el_0p(modulo):
    fuente = fuentes()[modulo]
    for pre in PRELUDIOS[modulo]:
        assert primer_recurso(fuente, pre) == "bloquear_intencion_propiedad", f"{modulo}.{pre}"


def test_los_writers_importan_el_0p_en_vez_de_copiarlo():
    for modulo, fuente in fuentes().items():
        assert "gapto:INTENCION" not in fuente, f"{modulo}.py copia el literal del 0P (test_233)"
    assert "from app.propiedades.servicio import bloquear_intencion_propiedad" in fuentes()["base"]


def test_mutante_writer_sin_0p_falla():
    mutante = ("def writer(sesion, i):\n    hoy = hoy_owner(sesion)\n    bloquear_intencion_propiedad(sesion, i)\n")
    assert primer_recurso(mutante, "writer") == "hoy_owner"               # el 0P ya no es lo primero
    assert primer_recurso(mutante, "writer") not in PRIMER_RECURSO


# ================================================================== §1.3 orden de recursos
def test_orden_alta_0p_propiedad_terceros_replay():
    llamadas = orden(fuentes()["servicio"], "alta")
    assert _en_orden(llamadas, ["bloquear_intencion_propiedad", "bloquear", "bloquear_terceros", "replay"]), llamadas
    # la lectura de la ficha y el solape son posteriores al lock de la propiedad
    assert llamadas.index("bloquear") < llamadas.index("leer") < llamadas.index("_validar_nuevo")


def test_orden_abrir_0p_propiedad_terceros_contrato():
    llamadas = orden(fuentes()["servicio"], "abrir")
    assert _en_orden(llamadas, ["bloquear_intencion_propiedad", "contrato", "bloquear", "bloquear_terceros", "contrato",
                                "replay"]), llamadas
    # el contrato se bloquea (FOR NO KEY UPDATE) DESPUES de la propiedad y de los terceros
    assert llamadas.index("bloquear") < llamadas.index("bloquear_terceros") < len(llamadas) - 1 - llamadas[::-1].index("contrato")


def test_orden_sucesor_0p_propiedad_terceros_contrato_actual_y_despues_el_writer_de_f05():
    fuente = fuentes()["servicio"]
    # C-CON-05 toma los recursos con `abrir` (0P -> propiedad -> advisory/terceros FS -> contrato) y el writer de F05
    # (crear_tercero) solo corre dentro de la escritura, tras todos los locks
    llamadas = orden(fuente, "sucesor")
    assert llamadas.index("abrir") < llamadas.index("_validar_nuevo") < llamadas.index("ejecutar_escritura"), llamadas
    assert "crear_tercero" not in llamadas                                      # solo dentro de `_escribir_nuevo`
    assert "crear_tercero" in orden(fuente, "_escribir_nuevo")


def test_orden_bloquear_terceros_advisory_solo_si_se_crea_y_despues_fs():
    llamadas = orden(fuentes()["base"], "bloquear_terceros")
    assert _en_orden(llamadas, ["tomar_advisory", "leer_tercero_compartido", "leer"]), llamadas


def test_orden_baja_de_servicio_propiedades_contratos_servicio():
    llamadas = orden(fuentes()["servicios"], "baja")
    assert _en_orden(llamadas, ["bloquear_intencion_propiedad", "bloquear", "bloquear_contratos", "servicio", "replay"]), llamadas


def test_mutante_terceros_antes_que_la_propiedad_falla():
    """El mutante de C-CON-01/C-CON-05 que toma los terceros ANTES que la propiedad rompe el orden certificado."""
    real = fuentes()["servicio"]
    mutante = real.replace("    if repo_prop.bloquear(sesion, propiedad_id) is None:                                     # nivel 3\n"
                           "        return Rechazo(e.AGREGADO_NO_ENCONTRADO)\n"
                           "    existentes, nuevos = _ids_terceros(datos.personas)\n"
                           "    terceros = bloquear_terceros(sesion, existentes=existentes, nuevos=nuevos)               # niveles 4 y 5\n",
                           "    existentes, nuevos = _ids_terceros(datos.personas)\n"
                           "    terceros = bloquear_terceros(sesion, existentes=existentes, nuevos=nuevos)\n"
                           "    if repo_prop.bloquear(sesion, propiedad_id) is None:\n"
                           "        return Rechazo(e.AGREGADO_NO_ENCONTRADO)\n")
    assert mutante != real, "el texto del mutante ya no coincide con servicio.alta: actualizar el arnes"
    assert not _en_orden(orden(mutante, "alta"), ["bloquear_intencion_propiedad", "bloquear", "bloquear_terceros", "replay"])


# ================================================================== el bloque no cambia codigo de fases anteriores
def test_el_unico_cambio_en_codigo_de_otras_fases_es_el_registro_de_rutas():
    app = (RAIZ / "backend" / "app" / "api" / "app.py").read_text(encoding="utf-8")
    assert "from app.contratos import rutas as rutas_contratos" in app
    assert app.count("rutas_contratos.registrar(") == 1
    # la ruta nueva GET /v1/terceros/{id} se registra DESPUES de /candidatos (la declara create_app)
    assert app.index('"/v1/terceros/candidatos"') < app.index("rutas_contratos.registrar(")
