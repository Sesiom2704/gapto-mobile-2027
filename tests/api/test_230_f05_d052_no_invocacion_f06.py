# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_230_f05_d052_no_invocacion_f06.py
# Ruta: tests/api/test_230_f05_d052_no_invocacion_f06.py
# Descripcion: F05-D052 paso 7 (AJ-F0507G3-14, F05 §66.5): prueba de NO
#   INVOCACION. Ninguna ruta HTTP actual del adaptador (F05) alcanza, directa
#   ni indirectamente, RVRX-REGLA (`ReglasService.crear_version` /
#   `ReglasService.corregir_excepcion`) ni `PrevisionesService.recalcular_futuras`.
#   Metodo (analisis estatico conservador, sin base de datos):
#     - Raices: se construye la app FastAPI REAL (`create_app`) con un
#       proveedor de conexion ficticio que solo responde a
#       `SELECT current_database()` (no se abre ninguna conexion) y se
#       enumeran desde ella TODAS las rutas (endpoint y dependencias, en
#       cascada) y los manejadores de excepciones. Cada callable se casa con
#       su `def` en el AST de backend/app por fichero y linea; ninguno puede
#       quedar sin casar. Se anaden como raices el codigo de nivel de modulo
#       de backend/app (se ejecuta al importar).
#     - Aristas por NOMBRE (sobreaproximacion): desde cada funcion, a TODAS
#       las funciones de backend/app con el mismo nombre que cualquier
#       identificador (`Name`), atributo (`Attribute`, llamado o no: cubre
#       inyeccion por constructor, callbacks y referencias guardadas),
#       nombre importado o cadena constante que sea un identificador
#       (cubre getattr con nombre literal) que aparezca en su cuerpo,
#       decoradores, anotaciones y valores por defecto. Referenciar una
#       clase alcanza sus metodos especiales y decorados (validadores,
#       propiedades) y los de sus bases.
#     - Despacho dinamico: getattr/setattr/hasattr/delattr con nombre no
#       constante, eval/exec/compile/__import__, importlib, attrgetter,
#       methodcaller, vars/globals/__dict__ en codigo alcanzable deben estar
#       en DINAMICOS_REVISADOS (revisados uno a uno en el informe); uno nuevo
#       hace fallar el test hasta revisarlo.
#   Limites (documentados en INFORME_NO_INVOCACION_F06.md): solo codigo Python
#   de backend/app; no ve funciones SQL, triggers ni otros procesos.
#   Sin base de datos: no exige GAPTO_TEST_DATABASE_URL.
# Version: 0.2.0 (F06 T5 E1 · RN-02/RN-03, Cons. §7, A §3.1-3, adenda T5 ronda 3; O-A36): MATRIZ NOMINAL de
#   escritores de reglas, ADITIVA. OBJETIVOS (los tres de F05) y su test NO cambian (test_299, AJ-COMP-02). Nuevo
#   OBJETIVOS_REGLAS con los siete escritores de reglas/previsiones (crear_regla, crear_version,
#   registrar_excepcion, corregir_excepcion, cerrar_vigencia, generar_calendario, recalcular_futuras),
#   identificados por (fichero, qualname). Una ruta puede alcanzar uno de ellos SOLO a
#   traves de un modulo de MATRIZ_ESCRITORES_REGLAS que lo permita (barrera por modulo); cualquier otro
#   camino, transitivo, por alias o por adaptador, falla. Precision: `alias.attr` con `alias` un MODULO de
#   app importado enlaza solo con las funciones que ese modulo define (si no la define, por nombre como
#   antes): evita el falso positivo de `app.contratos.repositorio.cerrar_vigencia` (homonimo). Controles
#   positivo (por permiso) y negativo (por frontera) sobre un arbol sintetico con llamadas transitivas,
#   alias y adaptadores. Los permisos de app/alquileres/* son de E3+ (modulos aun inexistentes): su
#   control positivo real queda PENDIENTE hasta que existan. test_299 no se toca.
# Version: 0.1.0 (F05-D052 paso 7)
# ============================================================

from __future__ import annotations

import ast
import contextlib
import pathlib
import sys
import uuid
from dataclasses import dataclass, field

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
APP = BACKEND / "app"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: Funciones que ninguna ruta de F05 puede alcanzar: nombre -> fichero donde se definen.
OBJETIVOS = {
    "crear_version": "app/services/reglas_service.py",
    "corregir_excepcion": "app/services/reglas_service.py",
    "recalcular_futuras": "app/services/previsiones_service.py",
}

#: F06 T5 E1 (RN-02, aditivo): escritores de reglas/previsiones por (fichero, qualname). Ninguna ruta los alcanza
#: salvo a traves de MATRIZ_ESCRITORES_REGLAS.
_RS = "app/services/reglas_service.py"
_PS = "app/services/previsiones_service.py"
OBJETIVOS_REGLAS = {
    (_RS, "ReglasService.crear_regla"),
    (_RS, "ReglasService.crear_version"),
    (_RS, "ReglasService.registrar_excepcion"),
    (_RS, "ReglasService.corregir_excepcion"),
    (_RS, "ReglasService.cerrar_vigencia"),
    (_PS, "PrevisionesService.generar_calendario"),
    (_PS, "PrevisionesService.recalcular_futuras"),
}

#: MATRIZ NOMINAL (Cons. §7, adenda T5 ronda 3 §2): modulo escritor -> objetivos que puede alcanzar.
#: `corregir_excepcion` solo en sus DOS usos nominales (prorroga y revision); `cerrar_vigencia` solo para el
#: writer de terminacion (E3). Los modulos de app/alquileres/ aun no existen (E3+): hoy ninguna ruta puede
#: alcanzar ningun objetivo. Tocar esta matriz es una decision N1 (RN-02), no un ajuste del test.
MATRIZ_ESCRITORES_REGLAS: dict[str, frozenset] = {
    "app/alquileres/alta.py": frozenset({"ReglasService.crear_regla", "PrevisionesService.generar_calendario",
                                         "ReglasService.registrar_excepcion"}),
    "app/alquileres/prorroga.py": frozenset({"PrevisionesService.generar_calendario",
                                             "ReglasService.corregir_excepcion"}),
    "app/alquileres/revision.py": frozenset({"ReglasService.crear_version", "PrevisionesService.recalcular_futuras",
                                             "ReglasService.corregir_excepcion"}),
    "app/alquileres/terminacion.py": frozenset({"ReglasService.cerrar_vigencia",
                                                "PrevisionesService.recalcular_futuras",
                                                "ReglasService.registrar_excepcion"}),
}

#: Sitios de despacho dinamico revisados: (fichero, funcion, tipo). Ver informe, seccion «Despacho dinamico».
#: Los tres LEEN un atributo de datos del resultado (no lo invocan); el nombre es una cadena constante del
#: llamante, que el grafo ya trata como referencia.
DINAMICOS_REVISADOS = {
    ("app/api/app.py", "create_app._comando_maestro", "getattr"),
    ("app/api/app.py", "create_app._comando_plantilla", "getattr"),
    ("app/api/app.py", "create_app.categorias_sugeridas", "__dict__"),
}

#: Builtins de despacho dinamico (como `Name`) y atributos que lo son (`importlib.import_module`, `operator.*`,
#: `obj.__dict__`). `re.compile` no es dinamico: `compile` solo cuenta como builtin.
DINAMICOS_NOMBRE = {"eval", "exec", "compile", "__import__", "vars", "globals", "locals", "attrgetter",
                    "methodcaller", "import_module"}
DINAMICOS_ATRIBUTO = {"import_module", "attrgetter", "methodcaller", "__dict__"}
ACCESO_ATRIBUTO = {"getattr", "setattr", "hasattr", "delattr"}
DECORADORES_IMPLICITOS = {"field_validator", "model_validator", "validator", "root_validator", "computed_field",
                          "field_serializer", "model_serializer", "property", "cached_property", "setter"}


@dataclass
class Funcion:
    fichero: str
    qualname: str
    nombre: str
    linea: int
    lineas_inicio: frozenset
    nodo: ast.AST
    refs: set = field(default_factory=set)
    dinamicos: list = field(default_factory=list)


@dataclass
class Clase:
    fichero: str
    nombre: str
    bases: list
    metodos: list


def _alias_de_modulos(arbol: ast.AST, app_dir: pathlib.Path, base: pathlib.Path) -> dict[str, str]:
    """Nombres locales que son MODULOS de app (`from app.x import y as z`, `import app.x.y as z`) -> fichero."""
    out: dict[str, str] = {}

    def fichero(punteado: str) -> str | None:
        partes = punteado.split(".")
        if partes[0] != "app":
            return None
        ruta = app_dir.joinpath(*partes[1:]).with_suffix(".py")
        return ruta.relative_to(base).as_posix() if ruta.is_file() else None

    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            for a in n.names:
                rel = fichero(f"{n.module}.{a.name}")
                if rel:
                    out[a.asname or a.name] = rel
        elif isinstance(n, ast.Import):
            for a in n.names:
                rel = fichero(a.name)
                if rel and a.asname:
                    out[a.asname] = rel
    return out


def _refs_y_dinamicos(nodo: ast.AST, alias_mod: dict[str, str] | None = None) -> tuple[set, list]:
    refs: set = set()
    din: list[str] = []
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name):
            refs.add(n.id)
            if n.id in DINAMICOS_NOMBRE:
                din.append(n.id)
        elif isinstance(n, ast.Attribute):
            if alias_mod and isinstance(n.value, ast.Name) and n.value.id in alias_mod:
                refs.add(("MOD", alias_mod[n.value.id], n.attr))   # acceso exacto a un modulo de app
            else:
                refs.add(n.attr)
            if n.attr in DINAMICOS_ATRIBUTO:
                din.append(n.attr)
        elif isinstance(n, ast.alias):
            refs.add(n.name.split(".")[-1])
            if n.asname:
                refs.add(n.asname)
            if n.name.split(".")[0] == "importlib":
                din.append("importlib")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
            refs.add(n.value)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ACCESO_ATRIBUTO
                and len(n.args) >= 2 and not isinstance(n.args[1], ast.Constant)):
            din.append(n.func.id)
    return refs, din


def indexar(app_dir: pathlib.Path = APP, base: pathlib.Path = BACKEND
            ) -> tuple[list[Funcion], dict[str, list[Clase]], list[Funcion]]:
    """Todas las funciones (cualquier anidamiento) y clases de backend/app, y el nivel de modulo."""
    funciones: list[Funcion] = []
    clases: dict[str, list[Clase]] = {}
    modulos: list[Funcion] = []
    for ruta in sorted(app_dir.rglob("*.py")):
        rel = ruta.relative_to(base).as_posix()
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        alias_mod = _alias_de_modulos(arbol, app_dir, base)

        def visitar(nodo: ast.AST, prefijo: str, clase: Clase | None) -> None:
            for hijo in ast.iter_child_nodes(nodo):
                if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = f"{prefijo}{hijo.name}"
                    inicio = {hijo.lineno} | {d.lineno for d in hijo.decorator_list}
                    f = Funcion(rel, q, hijo.name, hijo.lineno, frozenset(inicio), hijo)
                    f.refs, f.dinamicos = _refs_y_dinamicos(hijo, alias_mod)
                    funciones.append(f)
                    if clase is not None:
                        clase.metodos.append(f)
                    visitar(hijo, q + ".", None)
                elif isinstance(hijo, ast.ClassDef):
                    c = Clase(rel, hijo.name, [ast.unparse(b).split(".")[-1].split("[")[0] for b in hijo.bases], [])
                    clases.setdefault(hijo.name, []).append(c)
                    visitar(hijo, f"{prefijo}{hijo.name}.", c)
                else:
                    visitar(hijo, prefijo, clase)

        visitar(arbol, "", None)
        # Nivel de modulo: todo lo que no es def ni cuerpo de def (se ejecuta al importar).
        mod = ast.Module(body=[s for s in arbol.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))],
                         type_ignores=[])
        m = Funcion(rel, "<modulo>", "<modulo>", 0, frozenset(), mod)
        for s in mod.body:
            if isinstance(s, ast.ClassDef):
                # El cuerpo de clase se ejecuta al importar, pero no los cuerpos de sus metodos.
                for b in s.body:
                    if not isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        r, d = _refs_y_dinamicos(b, alias_mod)
                        m.refs |= r
                        m.dinamicos += d
                for b in s.bases + s.decorator_list + s.keywords:
                    r, d = _refs_y_dinamicos(b, alias_mod)
                    m.refs |= r
            else:
                r, d = _refs_y_dinamicos(s, alias_mod)
                m.refs |= r
                m.dinamicos += d
        modulos.append(m)
    return funciones, clases, modulos


def _metodos_implicitos(c: Clase, clases: dict[str, list[Clase]], vistos: set) -> list[Funcion]:
    if (c.fichero, c.nombre) in vistos:
        return []
    vistos.add((c.fichero, c.nombre))
    out = []
    for f in c.metodos:
        decor = {ast.unparse(d).split("(")[0].split(".")[-1] for d in f.nodo.decorator_list}
        if (f.nombre.startswith("__") and f.nombre.endswith("__")) or decor & DECORADORES_IMPLICITOS:
            out.append(f)
    for b in c.bases:
        for cb in clases.get(b, []):
            out += _metodos_implicitos(cb, clases, vistos)
    return out


def _app_real():
    from app.api.app import create_app
    from app.api.configuracion import cargar_desde_entorno

    class _Resultado:
        def fetchone(self):
            return ("gapto2027_no_invocacion",)

    class _Conexion:
        def execute(self, sql, *a, **k):
            assert sql.strip() == "SELECT current_database()", sql
            return _Resultado()

    @contextlib.contextmanager
    def _proveedor():
        yield _Conexion()

    cfg = cargar_desde_entorno({
        "GAPTO_ENV": "development",
        "GAPTO_DATABASE_URL": "postgresql://sin-conexion@127.0.0.1:1/gapto2027_no_invocacion",
        "GAPTO_DEV_OWNER_USER_ID": str(uuid.uuid4()),
        "GAPTO_DEV_TOKEN": "t" * 64,
        "GAPTO_DEV_DB_ALLOWLIST": "gapto2027_no_invocacion",
    })
    return create_app(cfg, proveedor_conexion=_proveedor)


def _callables_de_rutas(app) -> list[tuple[str, object]]:
    from fastapi.routing import APIRoute

    out = []

    def dependencias(dep, etiqueta):
        for d in dep.dependencies:
            if d.call is not None:
                out.append((etiqueta + " [dependencia]", d.call))
            dependencias(d, etiqueta)

    for r in app.routes:
        if isinstance(r, APIRoute):
            etiqueta = f"{','.join(sorted(r.methods))} {r.path}"
            out.append((etiqueta, r.endpoint))
            dependencias(r.dependant, etiqueta)
    for exc, h in app.exception_handlers.items():
        out.append((f"exception_handler {getattr(exc, '__name__', exc)}", h))
    return out


def construir_sucesores(funciones: list[Funcion], clases: dict[str, list[Clase]]):
    """Aristas por nombre (sobreaproximacion) y, para `modulo.attr`, exactas al modulo (con respaldo por nombre)."""
    por_nombre: dict[str, list[Funcion]] = {}
    por_modulo: dict[tuple[str, str], list[Funcion]] = {}
    for f in funciones:
        por_nombre.setdefault(f.nombre, []).append(f)
        if "." not in f.qualname:
            por_modulo.setdefault((f.fichero, f.nombre), []).append(f)

    def sucesores(f: Funcion) -> list[Funcion]:
        out = []
        for ref in f.refs:
            if isinstance(ref, tuple):
                _, fichero, nombre = ref
                exactas = por_modulo.get((fichero, nombre))
                out += exactas if exactas else por_nombre.get(nombre, [])
            else:
                nombre = ref
                out += por_nombre.get(nombre, [])
            for c in clases.get(nombre, []):
                out += _metodos_implicitos(c, clases, set())
        return out

    return sucesores, por_nombre


def alcanzables_con_barrera(raices: list, sucesores, barrera) -> dict[int, tuple[int | None, str]]:
    """BFS desde las raices sin EXPANDIR las funciones para las que `barrera(f)` es cierto (modulo autorizado)."""
    padre: dict[int, tuple[int | None, str]] = {}
    cola = []
    for etiqueta, f in raices:
        if id(f) not in padre:
            padre[id(f)] = (None, etiqueta)
            cola.append(f)
    i = 0
    while i < len(cola):
        f = cola[i]
        i += 1
        if barrera(f):
            continue
        for s in sucesores(f):
            if id(s) not in padre:
                padre[id(s)] = (id(f), "")
                cola.append(s)
    return padre


def violaciones_matriz(raices: list, sucesores, funciones: list[Funcion], objetivos, matriz) -> list:
    """(objetivo, funcion alcanzada, padre) para cada objetivo alcanzable SIN pasar por un modulo que lo permita."""
    out = []
    for fichero, qual in sorted(objetivos):
        permitidos = {m for m, objs in matriz.items() if qual in objs}
        padre = alcanzables_con_barrera(raices, sucesores, lambda f, p=permitidos: f.fichero in p)
        for f in funciones:
            if f.fichero == fichero and f.qualname == qual and id(f) in padre:
                out.append(((fichero, qual), f, padre))
    return out


def grafo() -> dict:
    funciones, clases, modulos = indexar()
    sucesores, por_nombre = construir_sucesores(funciones, clases)
    app = _app_real()
    rutas = [r for r in app.routes if r.__class__.__name__ == "APIRoute"]
    raices: list[tuple[str, Funcion]] = []
    externas: list[str] = []
    sin_casar: list[str] = []
    for etiqueta, fn in _callables_de_rutas(app):
        code = getattr(fn, "__code__", None)
        if code is None:
            sin_casar.append(f"{etiqueta}: sin __code__ ({fn!r})")
            continue
        fichero = pathlib.Path(code.co_filename).resolve()
        if APP.resolve() not in fichero.parents:
            externas.append(f"{etiqueta}: {fichero.name}:{code.co_firstlineno}")
            continue
        rel = fichero.relative_to(BACKEND.resolve()).as_posix()
        casados = [f for f in funciones if f.fichero == rel and code.co_firstlineno in f.lineas_inicio
                   and f.nombre == code.co_name]
        if len(casados) != 1:
            sin_casar.append(f"{etiqueta}: {rel}:{code.co_firstlineno} {code.co_name} ({len(casados)} candidatos)")
            continue
        raices.append((etiqueta, casados[0]))
    for m in modulos:
        raices.append((f"modulo {m.fichero}", m))

    # BFS conservando el primer camino (para el diagnostico).
    padre: dict[int, tuple[int | None, str]] = {}
    cola = []
    for etiqueta, f in raices:
        if id(f) not in padre:
            padre[id(f)] = (None, etiqueta)
            cola.append(f)
    por_id = {id(f): f for f in funciones + modulos}
    i = 0
    while i < len(cola):
        f = cola[i]
        i += 1
        for s in sucesores(f):
            if id(s) not in padre:
                padre[id(s)] = (id(f), "")
                cola.append(s)

    def camino(f: Funcion) -> list[str]:
        out, k = [], id(f)
        while k is not None:
            p, etiqueta = padre[k]
            g = por_id[k]
            out.append(f"{g.fichero}:{g.qualname}" + (f"  <- {etiqueta}" if etiqueta else ""))
            k = p
        return list(reversed(out))

    alcanzables = [por_id[k] for k in padre]
    return {
        "rutas": rutas, "raices": raices, "externas": externas, "sin_casar": sin_casar,
        "funciones": funciones, "alcanzables": alcanzables, "camino": camino,
        "sucesores": sucesores, "por_id": por_id,
        "objetivos_definidos": {n: [f for f in por_nombre.get(n, [])] for n in OBJETIVOS},
        "objetivos_reglas_definidos": {o: [f for f in funciones if (f.fichero, f.qualname) == o]
                                       for o in OBJETIVOS_REGLAS},
        "dinamicos": sorted({(f.fichero, f.qualname, d) for f in alcanzables for d in f.dinamicos}),
    }


@pytest.fixture(scope="module")
def g() -> dict:
    return grafo()


def test_rutas_enumeradas_desde_la_app_real_y_todas_casadas(g):
    assert len(g["rutas"]) >= 50, f"solo {len(g['rutas'])} rutas: la enumeracion no es la de la app real"
    assert all(r.path.startswith("/v1/") for r in g["rutas"]), "ruta fuera de /v1"
    assert g["sin_casar"] == [], "callables de ruta sin casar con el AST:\n" + "\n".join(g["sin_casar"])
    endpoints = {e for e, _ in g["raices"] if not e.startswith("modulo ") and "[dependencia]" not in e
                 and not e.startswith("exception_handler")}
    assert len(endpoints) == len(g["rutas"])


def test_objetivos_existen_con_su_firma(g):
    for nombre, fichero in OBJETIVOS.items():
        defs = g["objetivos_definidos"][nombre]
        assert [f.fichero for f in defs] == [fichero], f"{nombre}: definiciones {[(f.fichero, f.qualname) for f in defs]}"


def test_objetivos_reglas_existen_una_vez(g):
    for objetivo in OBJETIVOS_REGLAS:
        defs = g["objetivos_reglas_definidos"][objetivo]
        assert len(defs) == 1, f"{objetivo}: definiciones {[(f.fichero, f.qualname) for f in defs]}"


def test_control_positivo_el_grafo_alcanza_el_motor(g):
    # Sin este control, un grafo vacio pasaria el test negativo: OP-22 debe ser alcanzable desde la ruta VS-01.
    alc = {(f.fichero, f.qualname) for f in g["alcanzables"]}
    assert ("app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado") in alc
    assert any(fi == "app/services/compuesto_service.py" and not q.startswith("<") for fi, q in alc)
    # Otros metodos de los mismos servicios SI son alcanzables: la exclusion es por funcion, no por modulo.
    assert any(fi == "app/services/previsiones_service.py" and q.startswith("PrevisionesService.") for fi, q in alc)


def test_ninguna_ruta_alcanza_rvrx_regla_ni_recalcular_futuras(g):
    malos = [f for f in g["alcanzables"] if f.nombre in OBJETIVOS and f.fichero == OBJETIVOS[f.nombre]]
    assert malos == [], "\n\n".join("ALCANZABLE " + f.qualname + ":\n  " + "\n  ".join(g["camino"](f)) for f in malos)


def test_matriz_nominal_escritores_de_reglas(g):
    # RN-02 (O-A36, frontera): ningun objetivo alcanzable salvo a traves de un modulo de la matriz que lo permita.
    malos = violaciones_matriz(g["raices"], g["sucesores"], g["funciones"], OBJETIVOS_REGLAS,
                               MATRIZ_ESCRITORES_REGLAS)
    assert malos == [], [o for o, _, _ in malos]


def test_matriz_corregir_excepcion_solo_en_sus_dos_usos_nominales():
    usos = sorted(m for m, objs in MATRIZ_ESCRITORES_REGLAS.items() if "ReglasService.corregir_excepcion" in objs)
    assert usos == ["app/alquileres/prorroga.py", "app/alquileres/revision.py"]
    usos = sorted(m for m, objs in MATRIZ_ESCRITORES_REGLAS.items() if "ReglasService.cerrar_vigencia" in objs)
    assert usos == ["app/alquileres/terminacion.py"]
    assert all(m.startswith("app/alquileres/") for m in MATRIZ_ESCRITORES_REGLAS)
    assert all(q in {o[1] for o in OBJETIVOS_REGLAS} for objs in MATRIZ_ESCRITORES_REGLAS.values() for q in objs)


def test_permisos_de_la_matriz_pendientes_hasta_e3(g):
    # Control positivo REAL por permiso: si el modulo autorizado existe, debe alcanzar lo que se le permite.
    # Hoy (E1) ninguno existe: PENDIENTE, nunca «no aplicable» (adenda ronda 3 §5).
    por_fichero = {}
    for f in g["funciones"]:
        por_fichero.setdefault(f.fichero, []).append(f)
    for modulo, objs in MATRIZ_ESCRITORES_REGLAS.items():
        if modulo not in por_fichero:
            continue
        raices = [(f"permiso {modulo}", f) for f in por_fichero[modulo]]
        padre = alcanzables_con_barrera(raices, g["sucesores"], lambda f: False)
        for q in objs:
            assert any(id(f) in padre for f in g["funciones"] if f.qualname == q), (modulo, q)
    if not any(m in por_fichero for m in MATRIZ_ESCRITORES_REGLAS):
        pytest.xfail("PENDIENTE (E3+): ningun modulo de app/alquileres existe todavia")


def test_homonimo_de_contratos_no_alcanza_reglas(g):
    # app.contratos usa `repo.cerrar_vigencia` (su repositorio): la arista cualificada no llega a ReglasService.
    alc = {(f.fichero, f.qualname) for f in g["alcanzables"]}
    assert ("app/contratos/repositorio.py", "cerrar_vigencia") in alc
    assert ("app/services/reglas_service.py", "ReglasService.cerrar_vigencia") not in alc


# ------------------------------------------------------------------ controles sobre arbol sintetico (O-A36)
_SINTETICO = {
    "app/__init__.py": "",
    "app/services/__init__.py": "",
    "app/services/reglas_service.py": (
        "class ReglasService:\n"
        "    def cerrar_vigencia(self):\n        return 1\n"
        "    def corregir_excepcion(self):\n        return 2\n"),
    "app/alquileres/__init__.py": "",
    "app/alquileres/terminacion.py": (
        "from app.services.reglas_service import ReglasService\n"
        "def escribir():\n    return ReglasService().cerrar_vigencia()\n"),
    "app/otros/__init__.py": "",
    "app/otros/directo.py": (
        "from app.services.reglas_service import ReglasService\n"
        "def escribir():\n    return ReglasService().corregir_excepcion()\n"),
    "app/otros/transitivo.py": (
        "from app.otros import intermedio\n"
        "def escribir():\n    return intermedio.paso()\n"),
    "app/otros/intermedio.py": (
        "from app.services.reglas_service import ReglasService as RS\n"
        "def paso():\n    return RS().cerrar_vigencia()\n"),
    "app/otros/adaptador.py": (
        "def escribir(svc):\n    cb = svc.cerrar_vigencia\n    return ejecutar(cb)\n"
        "def ejecutar(f):\n    return f()\n"),
    "app/otros/homonimo.py": (
        "from app.otros import repo_propio as repo\n"
        "def escribir():\n    return repo.cerrar_vigencia()\n"),
    "app/otros/repo_propio.py": "def cerrar_vigencia():\n    return 3\n",
}
_OBJ_SINT = {("app/services/reglas_service.py", "ReglasService.cerrar_vigencia"),
             ("app/services/reglas_service.py", "ReglasService.corregir_excepcion")}
_MATRIZ_SINT = {"app/alquileres/terminacion.py": frozenset({"ReglasService.cerrar_vigencia"})}


@pytest.fixture(scope="module")
def sint(tmp_path_factory):
    base = tmp_path_factory.mktemp("arbol_230")
    for rel, texto in _SINTETICO.items():
        ruta = base / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
    funciones, clases, _ = indexar(base / "app", base)
    sucesores, _ = construir_sucesores(funciones, clases)
    por = {(f.fichero, f.qualname): f for f in funciones}
    return funciones, sucesores, por


def _viol(sint, raiz):
    funciones, sucesores, por = sint
    return {o[1] for o, _, _ in violaciones_matriz([("ruta", por[raiz])], sucesores, funciones, _OBJ_SINT,
                                                   _MATRIZ_SINT)}


def test_control_positivo_por_permiso(sint):
    assert _viol(sint, ("app/alquileres/terminacion.py", "escribir")) == set()


def test_control_negativo_directo_desde_frontera_no_autorizada(sint):
    assert _viol(sint, ("app/otros/directo.py", "escribir")) == {"ReglasService.corregir_excepcion"}


def test_control_negativo_transitivo_y_alias(sint):
    assert _viol(sint, ("app/otros/transitivo.py", "escribir")) == {"ReglasService.cerrar_vigencia"}


def test_control_negativo_adaptador(sint):
    assert _viol(sint, ("app/otros/adaptador.py", "escribir")) == {"ReglasService.cerrar_vigencia"}


def test_control_homonimo_en_otro_modulo_no_es_violacion(sint):
    assert _viol(sint, ("app/otros/homonimo.py", "escribir")) == set()


def test_despacho_dinamico_alcanzable_revisado(g):
    nuevos = [d for d in g["dinamicos"] if d not in DINAMICOS_REVISADOS]
    assert nuevos == [], f"despacho dinamico alcanzable sin revisar: {nuevos}"
