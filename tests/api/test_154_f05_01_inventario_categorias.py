# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_154_f05_01_inventario_categorias.py
# Ruta: tests/api/test_154_f05_01_inventario_categorias.py
# Descripcion: Inventario FAIL-CLOSED de escritores y consumidores de
#   categoria (F05-D009 §23.3 C-b; mandato F05-01 backend v0.2, AJ-03).
#   Test estatico: no necesita base de datos.
#
#   Se congela la PROPIEDAD, no la cardinalidad (el baseline de H2 era 16
#   ficheros / 28 lineas en backend/app). Reglas:
#
#   I1  Toda funcion (o nivel de modulo) del codigo productivo que mencione
#       `categoria_id` esta REGISTRADA con write-path + operacion + semantica.
#       Una aparicion nueva sin registrar, o un registro que ya no existe,
#       hace fallar el test. Si un componente tuviera caminos A y B, se
#       registran como entradas separadas (una por funcion).
#   I2  Clases:
#         A_FRONTERA  composicion de una seleccion NUEVA en la frontera F05;
#                     solo es valida tras la guarda C-a (se verifica en I4).
#         GUARDA      la guarda C-a y su punto de invocacion.
#         A_MOTOR     write-path del motor F04 que persiste una seleccion
#                     nueva sin guarda propia (la guarda es de la frontera).
#         B           referencia historica o correccion: no revalida
#                     selectabilidad actual (D-194, C04, D-198).
#         P           semantica A/B dependiente de una superficie F05 aun no
#                     contratada: la frontera NO puede alcanzarla (I3).
#         R           lectura, declaracion de tipo/columna o valor NULL fijo.
#   I3  La frontera F05 (backend/app/api, backend/app/categorias) solo contiene
#       apariciones R, GUARDA o A_FRONTERA y solo alcanza el motor a traves de
#       OP-22 (HechosCompuestosService): no referencia directamente servicios
#       con caminos A_MOTOR, B o P.
#   I4  La guarda se invoca DESPUES del reconocimiento de identidad (dentro de
#       la rama `not ya_materializada`) y ANTES de `componer`; `componer`
#       tiene un unico llamador productivo.
#   I5  Escritores de `categorias_financieras`: ninguno en runtime hasta S4, y
#       DELETE/TRUNCATE prohibidos siempre (`DELETE writers = 0`, F05-01-R12).
#   I6  SQL con nombre de tabla dinamico: solo las construcciones de la lista
#       blanca, cada una SELECT sobre un conjunto cerrado que no contiene
#       `categorias_financieras`; y ninguna construccion troceada de los
#       literales `categoria_id` / `categorias_financieras`.
#   I7  Cliente movil y scripts/dev: ninguna mencion sin registrar. Unica
#       exclusion cerrada: el arnes de mutacion (texto de mutantes).
#
#   v0.2.0 (F05-01, S4; AJ-S4-01): clase CATALOGO para el paquete de gestion
#   del arbol (escribe/lee categorias_financieras; NO consume
#   hecho_efectos.categoria_id). I5 autoriza exactamente
#   backend/app/categorias/repositorio.py como escritor del catalogo (INSERT y
#   UPDATE; DELETE = 0). I8: toda funcion publica de servicio.py toma el
#   advisory como PRIMERA llamada, y las primitivas de escritura del
#   repositorio solo se invocan desde servicio.py.
#
#   v0.3.0 (F05-01, S6-C07; F05-D014 §28.2 "Inventario C-b"): se amplia a
#   las magnitudes.
#   I4  ademas: C07 (`validar_magnitudes`) se invoca UNA vez, dentro de
#       `not ya_materializada`, DESPUES de la guarda C-a y ANTES de `componer`.
#   I9  Escritores de `magnitudes` y `categoria_magnitudes`: CERO en runtime
#       (gate F05-01-R16: todo writer futuro de asociaciones exige decision y
#       lock de la categoria padre). Escritores de `hecho_magnitudes`:
#       exactamente las primitivas certificadas de F04 en
#       contexto_repository.py (alta OP-22, correccion OP-21); la frontera F05
#       no escribe `hecho_magnitudes` directamente (solo via OP-22). Se
#       congela la propiedad (conjunto de escritores), no una cardinalidad.
#
#   v0.4.0 (F05-01 S6-ICONO (F05-D013), AJ-ICON-06): se registran la ruta
#   POST /v1/categorias/{id}/icono y el comando `cambiar_icono` (I1, I8: toma
#   el advisory como PRIMERA llamada). COLUMNAS_EDITABLES incluye `icon_key`
#   y sigue excluyendo presupuestable_default e identidad. I10: la biblioteca
#   (backend/app/categorias/iconos.py) es un modulo puro, sin SQL, sin
#   escritores y sin dependencias de acceso a datos; alta y cambiar_icono la
#   invocan antes de escribir.
#
#   v0.5.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): el comando `reordenar` entra
#   en COMANDOS (I8: advisory como PRIMERA llamada; escribe solo via
#   `_escribir` + `repo.actualizar`). Ninguna primitiva de escritura nueva:
#   `hijos_bloqueados` es lectura. I11: prohibicion de §26.3 como propiedad
#   estatica: la ruta por nodo /{id}/orden solo aparece en su declaracion de
#   app.py; ningun otro codigo productivo ni el cliente movil la invoca, y la
#   reordenacion tiene una unica ruta atomica /v1/categorias/reordenar.
# Version: 0.5.0
# ============================================================

from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

APP = BACKEND / "app"
FRONTERA = ("backend/app/api/", "backend/app/categorias/")
TOKEN = "categoria_id"

# ------------------------------------------------------------------ registro
# (ruta, funcion) -> (clase, operacion, justificacion)
REGISTRO: dict[tuple[str, str], tuple[str, str, str]] = {
    # --- frontera F05
    ("backend/app/api/elegibilidad_categoria.py", "validar_seleccion_categoria"): (
        "GUARDA", "F05-01 C-a", "guarda unica de elegibilidad (F05-D009 §23.3)"),
    ("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion"): (
        "GUARDA", "VS-01 intencion", "invoca la guarda tras la identidad y antes de componer (I4)"),
    ("backend/app/api/traductor_gasto_pagado.py", "componer"): (
        "A_FRONTERA", "VS-01 -> OP-22", "sella categoria_id en el efecto GASTO; guardado por I4"),
    ("backend/app/api/dto_vs01.py", "CategoriaSeleccionada"): (
        "R", "DTO", "declaracion del estado CATEGORIA del wire"),
    ("backend/app/api/dto_vs01.py", "IntencionGastoPagado.categoria_id"): (
        "R", "DTO", "lectura derivada del estado categorial sellado"),
    ("backend/app/api/dto_categorias.py", "UsoCategoria"): (
        "R", "DTO", "respuesta de lectura"),
    ("backend/app/api/app.py", "create_app.uso_categoria"): (
        "R", "GET /v1/categorias/{id}/uso", "parametro de ruta de una lectura"),
    ("backend/app/categorias/lecturas.py", "uso_por_naturaleza"): (
        "R", "lectura S3", "recuento de uso historico (C06)"),
    ("backend/app/categorias/lecturas.py", "_magnitudes_por_categoria"): (
        "R", "lectura S6-C07", "magnitudes y capturabilidad por categoria (AJ-C07-08); no es autoridad"),
    ("backend/app/api/captura_magnitudes.py", "validar_magnitudes"): (
        "GUARDA", "F05-01 C07", "C07 servidor autoridad; invocada tras C-a y antes de componer (I4)"),
    ("backend/app/api/captura_magnitudes.py", "_asociaciones"): (
        "GUARDA", "F05-01 C07", "lectura FOR SHARE de las asociaciones de la categoria (AJ-C07-07)"),
    # --- catalogo S4 (escritor/lector de categorias_financieras)
    **{("backend/app/api/app.py", f"create_app.{n}"): ("CATALOGO", "ruta S4", "parametro de ruta del comando")
       for n in ("alta_categoria", "renombrar_categoria", "mover_categoria", "desactivar_categoria",
                 "reactivar_categoria", "ordenar_categoria", "ambito_categoria", "icono_categoria")},
    **{("backend/app/categorias/servicio.py", n): ("CATALOGO", f"C06 {n}", "comando del arbol bajo advisory (I8)")
       for n in ("alta", "renombrar", "mover", "ordenar", "cambiar_ambito", "desactivar", "reactivar",
                 "cambiar_icono", "_auditar", "_nodo", "_resultado")},
    **{("backend/app/categorias/repositorio.py", n): ("CATALOGO", f"repositorio {n}", "unico escritor del catalogo (I5)")
       for n in ("leer", "snapshot", "insertar", "actualizar")},
    # --- motor F04 (certificado, no se modifica)
    ("backend/app/core/modelos_efectos.py", "DatosEfecto"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_devolucion.py", "DatosDevolucion"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_suplemento.py", "DatosSuplemento"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_prevision.py", "DatosVersionRegla"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_prevision.py", "DatosPrevisionManual"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/repositories/efectos_repository.py", "<modulo>"): (
        "R", "tipos SQL", "mapa de columnas; la escritura se registra en la funcion"),
    ("backend/app/repositories/efectos_repository.py", "insertar_efecto_si_no_existe"): (
        "A_MOTOR", "primitiva INSERT hecho_efectos",
        "persiste lo que decide el llamador: OP-04/OP-18 (A_MOTOR), OP-13/OP-21 (B/P)"),
    ("backend/app/services/efectos_service.py", "EfectosService.registrar_efectos.operacion"): (
        "A_MOTOR", "OP-04", "efecto nuevo con la categoria declarada; guarda en frontera"),
    ("backend/app/services/efectos_service.py", "EfectosService._valores_efecto"): (
        "R", "OP-04 idempotencia", "comparacion de intencion en reintento"),
    ("backend/app/services/compuesto_service.py", "HechosCompuestosService._agregado_coincide"): (
        "R", "OP-22 identidad", "comparacion exacta del agregado (F04-D051)"),
    ("backend/app/services/suplementos_service.py", "SuplementosService.registrar.operacion"): (
        "A_MOTOR", "OP-18", "realidad suplementaria nueva con categoria declarada (no se presupone B)"),
    ("backend/app/services/devoluciones_service.py", "DevolucionesService.devolver.operacion"): (
        "B", "OP-13", "categoria heredada del efecto origen (D-194); superficie F05-06"),
    ("backend/app/services/correcciones_service.py", "<modulo>"): (
        "R", "OP-21", "lista cerrada de campos corregibles"),
    ("backend/app/services/correcciones_service.py", "CorreccionesService._crear_efectos"): (
        "P", "OP-21 reemplazo", "correccion de error de captura; A/B segun superficie F05-06"),
    ("backend/app/repositories/correcciones_repository.py", "<modulo>"): (
        "R", "OP-21", "tipos SQL de la correccion"),
    ("backend/app/repositories/correcciones_repository.py", "actualizar_efecto"): (
        "P", "OP-21 UPDATE", "puede conservar referencia historica (C04) o elegir otra; superficie F05-06"),
    ("backend/app/services/posiciones_service.py", "PosicionesService.condonar_derecho.extra"): (
        "R", "OP-12/condonacion", "categoria_id=None fijo"),
    ("backend/app/services/posiciones_service.py", "PosicionesService._crear_delta"): (
        "R", "OP-12 delta", "categoria_id=None fijo"),
    ("backend/app/services/reglas_service.py", "ReglasService._insertar_version"): (
        "P", "regla_versiones", "expectativa configurada; superficie de reglas no contratada en F05-01"),
    ("backend/app/repositories/reglas_repository.py", "<modulo>"): ("R", "tipos SQL", "mapa de columnas"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService.crear_manual.operacion"): (
        "P", "prevision manual", "expectativa; superficie no contratada en F05-01"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._materializar_ocurrencia"): (
        "B", "generacion", "snapshot de la version de regla ya configurada"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._regobernar"): (
        "B", "regobernanza", "snapshot de la version de regla ya configurada"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._snapshot_de_version"): (
        "R", "snapshot", "lectura de la version"),
    ("backend/app/repositories/previsiones_repository.py", "<modulo>"): ("R", "tipos SQL", "mapa de columnas"),
}

CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO"}

#: Servicios del motor que la frontera NO puede referenciar (I3): tienen
#: caminos A_MOTOR, B o P con categoria. OP-22 es la unica puerta.
SERVICIOS_VEDADOS_EN_FRONTERA = (
    "EfectosService", "SuplementosService", "DevolucionesService", "CorreccionesService",
    "ReglasService", "PrevisionesService", "insertar_efecto_si_no_existe", "actualizar_efecto",
)

#: Construcciones con nombre de tabla dinamico (I6): (ruta, funcion) ->
#: (modulo, atributo del conjunto cerrado, justificacion).
DINAMICAS_AUTORIZADAS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("backend/app/repositories/posiciones_repository.py", "existe_registro"): (
        "app.repositories.posiciones_repository", "TABLAS_CON_ID", "SELECT 1 por identidad; lista blanca"),
    ("backend/app/repositories/contexto_repository.py", "leer_registro"): (
        "app.repositories.contexto_repository", "TABLAS_CONTEXTO", "SELECT por id; conjunto cerrado"),
    ("backend/app/repositories/compuesto_repository.py", "leer"): (
        "app.repositories.compuesto_repository", "TABLAS_IDENTIDAD", "SELECT por identidad OP-22"),
    ("backend/app/repositories/compuesto_repository.py", "identidades_del_agregado"): (
        "app.repositories.compuesto_repository", "FILTROS_AGREGADO", "SELECT de ids del agregado OP-22"),
}

#: Escritores autorizados de categorias_financieras (I5): exactamente el
#: repositorio del paquete S4.
ESCRITORES_CATALOGO: dict[tuple[str, str], str] = {
    ("backend/app/categorias/repositorio.py", "insertar"): "INSERT del alta",
    ("backend/app/categorias/repositorio.py", "actualizar"): "UPDATE de columnas editables",
}
SERVICIO = "backend/app/categorias/servicio.py"
PRIMITIVAS_ESCRITURA = {"insertar", "actualizar"}
COMANDOS = ("alta", "renombrar", "mover", "ordenar", "cambiar_ambito", "desactivar", "reactivar", "cambiar_icono",
            "reordenar")
ICONOS = "backend/app/categorias/iconos.py"


# ------------------------------------------------------------------ utilidades
def _rel(p: pathlib.Path) -> str:
    return p.relative_to(RAIZ).as_posix()


#: Herramientas de test dentro de scripts/dev que NO se ejecutan en runtime y
#: contienen, como texto, los mutantes que este inventario debe detectar.
EXCLUIDOS: dict[str, str] = {
    "scripts/dev/mutantes_f05_01.py": "arnes de mutacion F05-01 (D-181): los mutantes son texto",
}


def _productivos_py() -> list[pathlib.Path]:
    candidatos = sorted(p for p in APP.rglob("*.py")) + sorted((RAIZ / "scripts" / "dev").rglob("*.py"))
    return [p for p in candidatos if _rel(p) not in EXCLUIDOS]


def _menciona(nodo: ast.AST) -> bool:
    for n in ast.walk(nodo):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and TOKEN in n.value:
            return True
        if isinstance(n, ast.Name) and n.id == TOKEN:
            return True
        if isinstance(n, ast.Attribute) and n.attr == TOKEN:
            return True
        if isinstance(n, ast.arg) and n.arg == TOKEN:
            return True
        if isinstance(n, ast.keyword) and n.arg == TOKEN:
            return True
    return False


def _apariciones(ruta: pathlib.Path) -> set[str]:
    """Nombres cualificados de funcion/clase (o '<modulo>') cuyo cuerpo
    PROPIO menciona `categoria_id` (sin contar funciones anidadas)."""
    arbol = ast.parse(ruta.read_bytes().decode("utf-8"))
    hallados: set[str] = set()

    def visitar(nodo: ast.AST, pila: list[str]) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nueva = pila + [hijo.name]
                if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = hijo.args.args + hijo.args.kwonlyargs + hijo.args.posonlyargs
                    if any(a.arg == TOKEN for a in args):
                        hallados.add(".".join(nueva))
                visitar(hijo, nueva)
            elif _menciona(hijo):
                hallados.add(".".join(pila) or "<modulo>")

    visitar(arbol, [])
    return hallados


def _funciones(arbol: ast.AST):
    def rec(nodo, pila):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = pila + [hijo.name]
                yield ".".join(q), hijo
                yield from rec(hijo, q)

    yield from rec(arbol, [])


def _nodo(ruta: str, qual: str) -> ast.AST:
    arbol = ast.parse((RAIZ / ruta).read_bytes().decode("utf-8"))
    for q, n in _funciones(arbol):
        if q == qual:
            return n
    raise AssertionError(f"{ruta}:{qual} no existe")


# ------------------------------------------------------------------ I1 / I2
def test_i1_toda_aparicion_de_categoria_id_esta_registrada():
    encontradas = {(_rel(p), q) for p in _productivos_py() for q in _apariciones(p)}
    sin_registrar = sorted(encontradas - set(REGISTRO))
    obsoletas = sorted(set(REGISTRO) - encontradas)
    assert not sin_registrar, f"consumidores/escritores de categoria_id sin clasificar: {sin_registrar}"
    assert not obsoletas, f"entradas del registro que ya no existen: {obsoletas}"


def test_i2_clases_validas_y_justificadas():
    for clave, (clase, operacion, justificacion) in REGISTRO.items():
        assert clase in CLASES, clave
        assert operacion.strip() and justificacion.strip(), clave


# ------------------------------------------------------------------ I3
def test_i3_frontera_solo_r_guarda_o_a_frontera():
    for (ruta, qual), (clase, _, _) in REGISTRO.items():
        if ruta.startswith(FRONTERA):
            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO"}, (ruta, qual, clase)


def test_i3_frontera_no_referencia_servicios_con_caminos_a_b_o_p():
    for p in _productivos_py():
        ruta = _rel(p)
        if not ruta.startswith(FRONTERA):
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        for imp in (n for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)):
            nombres |= {a.name for a in imp.names}
        vedados = sorted(nombres & set(SERVICIOS_VEDADOS_EN_FRONTERA))
        assert not vedados, f"{ruta} alcanza el motor sin pasar por OP-22: {vedados}"


# ------------------------------------------------------------------ I4
def _llamadas(nodo: ast.AST, nombre: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(nodo)
        if isinstance(n, ast.Call)
        and ((isinstance(n.func, ast.Name) and n.func.id == nombre)
             or (isinstance(n.func, ast.Attribute) and n.func.attr == nombre))
    ]


def test_i4_guarda_tras_identidad_y_antes_de_componer():
    fn = _nodo("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")
    guardas = _llamadas(fn, "validar_seleccion_categoria")
    composiciones = _llamadas(fn, "componer")
    assert len(guardas) == 1 and len(composiciones) == 1
    assert guardas[0].lineno < composiciones[0].lineno, "la guarda debe preceder a componer"
    # La guarda vive dentro de `if not ya_materializada:` (identidad antes).
    padres = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and any(g is c for g in ast.walk(n) for c in guardas)
    ]
    assert any(
        isinstance(i.test, ast.UnaryOp) and isinstance(i.test.op, ast.Not)
        and isinstance(i.test.operand, ast.Name) and i.test.operand.id == "ya_materializada"
        for i in padres
    ), "la guarda no esta subordinada al reconocimiento de identidad"


def test_i4_componer_tiene_un_unico_llamador_productivo():
    llamadores = []
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(True for _ in _llamadas_directas(n, "componer")):
                llamadores.append((_rel(p), q))
    assert llamadores == [("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")]


def _llamadas_directas(fn: ast.AST, nombre: str):
    """Llamadas en el cuerpo propio (sin funciones anidadas)."""
    pila = list(ast.iter_child_nodes(fn))
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nombre:
            yield n
        pila.extend(ast.iter_child_nodes(n))


def test_i4_c07_tras_la_guarda_y_antes_de_componer():
    fn = _nodo("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")
    guardas = _llamadas(fn, "validar_seleccion_categoria")
    c07 = _llamadas(fn, "validar_magnitudes")
    composiciones = _llamadas(fn, "componer")
    assert len(c07) == 1, "C07 debe invocarse exactamente una vez"
    assert guardas[0].lineno < c07[0].lineno < composiciones[0].lineno, "orden guarda -> C07 -> componer"
    padres = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and any(g is c07[0] for g in ast.walk(n))
    ]
    assert any(
        isinstance(i.test, ast.UnaryOp) and isinstance(i.test.op, ast.Not)
        and isinstance(i.test.operand, ast.Name) and i.test.operand.id == "ya_materializada"
        for i in padres
    ), "C07 no esta subordinada al reconocimiento de identidad (AJ-C07-04)"


def test_i4_c07_solo_se_invoca_desde_la_ejecucion():
    llamadores = []
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(True for _ in _llamadas_directas(n, "validar_magnitudes")):
                llamadores.append((_rel(p), q))
    assert llamadores == [("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")]


# ------------------------------------------------------------------ I5
_ESCRITURA = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?categorias_financieras\b",
    re.IGNORECASE,
)
_BORRADO = re.compile(r"\b(DELETE\s+FROM|TRUNCATE)\b[^;]*categorias_financieras", re.IGNORECASE | re.DOTALL)


def _textos_productivos():
    for p in _productivos_py():
        yield p, p.read_bytes().decode("utf-8")
    for p in sorted((RAIZ / "mobile" / "src").rglob("*")):
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            yield p, p.read_bytes().decode("utf-8")


def test_i5_escritores_de_categorias_financieras():
    encontrados = set()
    for p, texto in _textos_productivos():
        if _ESCRITURA.search(texto):
            encontrados.add(_rel(p))
    autorizados = {ruta for ruta, _ in ESCRITORES_CATALOGO}
    assert encontrados <= autorizados, f"escritor de categorias_financieras no autorizado: {sorted(encontrados - autorizados)}"


def test_i5_delete_writers_cero():
    for p, texto in _textos_productivos():
        assert not _BORRADO.search(texto), f"DELETE/TRUNCATE de categorias_financieras en {_rel(p)}"


def test_i5_escrituras_solo_en_las_funciones_autorizadas():
    ruta = "backend/app/categorias/repositorio.py"
    texto = (RAIZ / ruta).read_bytes().decode("utf-8")
    arbol = ast.parse(texto)
    lineas = texto.splitlines()
    con_escritura = set()
    for q, n in _funciones(arbol):
        cuerpo = "\n".join(lineas[n.lineno - 1:n.end_lineno])
        if re.search(r"\b(INSERT\s+INTO|UPDATE)\s+gapto\.categorias_financieras", cuerpo):
            con_escritura.add((ruta, q))
    assert con_escritura == set(ESCRITORES_CATALOGO)


# ------------------------------------------------------------------ I9
def _escritura_de(tabla: str) -> re.Pattern:
    return re.compile(
        r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
        + tabla + r"\b",
        re.IGNORECASE,
    )


#: Escritores autorizados de hecho_magnitudes: primitivas certificadas F04.
ESCRITORES_HECHO_MAGNITUDES = {
    ("backend/app/repositories/contexto_repository.py", "insertar_magnitud"),
    ("backend/app/repositories/contexto_repository.py", "eliminar_magnitud"),
    ("backend/app/repositories/contexto_repository.py", "actualizar_magnitud"),
}


def test_i9_sin_escritores_runtime_de_magnitudes_ni_asociaciones():
    for tabla in ("magnitudes", "categoria_magnitudes"):
        patron = _escritura_de(tabla)
        encontrados = sorted(_rel(p) for p, texto in _textos_productivos() if patron.search(texto))
        assert encontrados == [], f"escritor runtime de {tabla} no autorizado (F05-01-R16): {encontrados}"


def test_i9_escritores_de_hecho_magnitudes_solo_f04():
    patron = _escritura_de("hecho_magnitudes")
    hallados = set()
    for p in _productivos_py():
        texto = p.read_bytes().decode("utf-8")
        if not patron.search(texto):
            continue
        lineas = texto.splitlines()
        for q, n in _funciones(ast.parse(texto)):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if patron.search("\n".join(lineas[n.lineno - 1:n.end_lineno])):
                hallados.add((_rel(p), q))
    assert hallados == ESCRITORES_HECHO_MAGNITUDES, sorted(hallados ^ ESCRITORES_HECHO_MAGNITUDES)
    for ruta, _ in hallados:
        assert not ruta.startswith(FRONTERA), ruta


# ------------------------------------------------------------------ I8
def _nombre_llamada(c: ast.Call) -> str | None:
    if isinstance(c.func, ast.Attribute):
        return c.func.attr
    if isinstance(c.func, ast.Name):
        return c.func.id
    return None


def test_i8_todo_comando_toma_el_advisory_primero():
    for qual in COMANDOS:
        fn = _nodo(SERVICIO, qual)
        primera = fn.body[0]
        assert (isinstance(primera, ast.Expr) and isinstance(primera.value, ast.Call)
                and _nombre_llamada(primera.value) == "tomar_advisory"), f"{qual} no toma el advisory primero"


def test_i8_toda_funcion_que_escribe_es_un_comando_con_advisory():
    arbol = ast.parse((RAIZ / SERVICIO).read_bytes().decode("utf-8"))
    for q, n in _funciones(arbol):
        if not isinstance(n, ast.FunctionDef):
            continue
        llamadas = {_nombre_llamada(c) for c in ast.walk(n) if isinstance(c, ast.Call)}
        if llamadas & (PRIMITIVAS_ESCRITURA | {"_escribir"}) and q not in ("_escribir",):
            assert q in COMANDOS, f"{q} escribe el catalogo sin ser un comando con advisory"


def test_i8_primitivas_de_escritura_solo_desde_el_servicio():
    for p in _productivos_py():
        ruta = _rel(p)
        if ruta in (SERVICIO, "backend/app/categorias/repositorio.py"):
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for c in ast.walk(arbol):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in PRIMITIVAS_ESCRITURA:
                if isinstance(c.func.value, ast.Name) and c.func.value.id in ("repo", "repositorio"):
                    raise AssertionError(f"{ruta} invoca una primitiva de escritura del catalogo")
        texto = p.read_bytes().decode("utf-8")
        assert "categorias.repositorio" not in texto and "categorias import repositorio" not in texto, ruta


def test_i8_columnas_editables_incluyen_icon_key():
    repo = importlib.import_module("app.categorias.repositorio")
    assert repo.COLUMNAS_EDITABLES == frozenset({"nombre", "parent_id", "orden", "enabled", "ambito", "icon_key"})


# ------------------------------------------------------------------ I10
_SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b|\bgapto\s*\.", re.IGNORECASE)


def test_i10_biblioteca_de_iconos_sin_sql_ni_escritores():
    texto = (RAIZ / ICONOS).read_bytes().decode("utf-8")
    arbol = ast.parse(texto)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            assert not _SQL.search(n.value), f"SQL en la biblioteca de iconos: {n.value!r}"
    importados = {a.name for i in ast.walk(arbol) if isinstance(i, (ast.Import, ast.ImportFrom)) for a in i.names}
    modulos = {i.module for i in ast.walk(arbol) if isinstance(i, ast.ImportFrom)}
    assert importados <= {"annotations"} and modulos <= {"__future__"}, (importados, modulos)
    llamadas = {_nombre_llamada(c) for c in ast.walk(arbol) if isinstance(c, ast.Call)}
    assert not llamadas & (PRIMITIVAS_ESCRITURA | {"uno", "execute", "_escribir"}), llamadas


def test_i10_alta_y_cambiar_icono_validan_con_la_biblioteca_antes_de_escribir():
    for qual in ("alta", "cambiar_icono"):
        fn = _nodo(SERVICIO, qual)
        validaciones = _llamadas(fn, "icono_valido")
        escrituras = _llamadas(fn, "_escribir")
        assert len(validaciones) == 1 and len(escrituras) == 1, qual
        assert validaciones[0].lineno < escrituras[0].lineno, f"{qual} escribe antes de validar el icono"


# ------------------------------------------------------------------ I6
_DINAMICA = re.compile(r"gapto\s*\.\s*\{|Identifier\(\s*[\"']gapto[\"']|[\"']gapto\.[\"']\s*\+")
_TROCEO = re.compile(
    r"[\"']categoria[s]?_?[\"']\s*\+|\+\s*[\"']_?id[\"']|categorias?_\{|[\"']categorias_[\"']\s*\+|[\"']financieras[\"']"
)


def test_i6_sql_de_tabla_dinamica_solo_en_lista_blanca():
    halladas = set()
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        lineas = p.read_bytes().decode("utf-8").splitlines()
        for q, n in _funciones(arbol):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cuerpo = "\n".join(lineas[n.lineno - 1:n.end_lineno])
            propias = [f for f in ast.walk(n) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f is not n]
            if propias:
                continue
            if _DINAMICA.search(cuerpo):
                halladas.add((_rel(p), q))
    assert halladas == set(DINAMICAS_AUTORIZADAS), f"SQL de tabla dinamica no autorizado: {sorted(halladas ^ set(DINAMICAS_AUTORIZADAS))}"
    for (ruta, qual), (modulo, atributo, _) in DINAMICAS_AUTORIZADAS.items():
        conjunto = getattr(importlib.import_module(modulo), atributo)
        assert "categorias_financieras" not in conjunto, (ruta, qual)
        cuerpo = "\n".join(
            (RAIZ / ruta).read_bytes().decode("utf-8").splitlines()[_nodo(ruta, qual).lineno - 1:_nodo(ruta, qual).end_lineno]
        )
        for linea in cuerpo.splitlines():
            if _DINAMICA.search(linea):
                assert re.search(r"SELECT", linea, re.IGNORECASE), (ruta, qual, linea)


def test_i6_sin_literales_troceados():
    for p, texto in _textos_productivos():
        assert not _TROCEO.search(texto), f"literal de categoria construido por piezas en {_rel(p)}"


def test_exclusiones_cerradas_y_existentes():
    """La lista de exclusiones es cerrada: cada entrada existe y es un arnes
    de mutacion, nunca codigo que el backend importe."""
    for ruta, motivo in EXCLUIDOS.items():
        assert (RAIZ / ruta).is_file() and motivo.strip(), ruta
        assert ruta.startswith("scripts/dev/mutantes_"), ruta
    for p in APP.rglob("*.py"):
        texto = p.read_bytes().decode("utf-8")
        assert "mutantes_f05_01" not in texto, _rel(p)


# ------------------------------------------------------------------ I7
def test_i7_cliente_movil_sin_menciones_sin_registrar():
    menciones = sorted(
        _rel(p) for p, t in _textos_productivos()
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"} and (TOKEN in t or "categorias_financieras" in t)
    )
    assert menciones == [], menciones


# ------------------------------------------------------------------ I11
_RUTA_POR_NODO = re.compile(r"/orden\b")


def test_i11_reordenar_solo_por_la_ruta_atomica():
    """F05-D012 §26.3: prohibido reordenar con N llamadas al comando por nodo.
    La ruta /{id}/orden (S4) solo aparece en su declaracion de app.py; ningun
    otro codigo productivo ni el cliente movil la invoca."""
    usos = []
    for p, texto in _textos_productivos():
        for linea in texto.splitlines():
            if linea.lstrip().startswith(("#", "//", "*", "/*")):
                continue
            if _RUTA_POR_NODO.search(linea):
                usos.append((_rel(p), linea.strip()))
    assert usos == [("backend/app/api/app.py", '@app.post("/v1/categorias/{categoria_id}/orden", **_R)')], usos
    app_py = (RAIZ / "backend" / "app" / "api" / "app.py").read_bytes().decode("utf-8")
    assert app_py.count('"/v1/categorias/reordenar"') == 1
    comandos = [n for n in ast.walk(_nodo(SERVICIO, "reordenar")) if isinstance(n, ast.For)]
    assert len(comandos) == 1, "reordenar: un unico bucle de escritura sobre las filas que cambian"
