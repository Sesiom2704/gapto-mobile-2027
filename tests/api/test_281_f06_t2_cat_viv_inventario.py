# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_281_f06_t2_cat_viv_inventario.py
# Ruta: tests/api/test_281_f06_t2_cat_viv_inventario.py
# Descripcion: T2-F06 CAT-VIV N1 · inventario DISCRIMINANTE de OBL-VIV-01 (AJ-T2 §2.1 punto 8; mandato v1.1 §2.3.7;
#   O-CV-14; mutantes M-CV-07, M-CV-09 y M-CV-12). Sin base de datos: AST sobre backend/app.
#
#   UNIVERSO: toda funcion (con su nombre cualificado, anidadas incluidas) de backend/app FUERA del motor F04
#   (services/, repositories/, core/) que invoca directamente un creador de hechos del motor:
#   registrar_hecho_compuesto (OP-22), devolver (OP-13), transferir (OP-10) o crear_hecho (OP-01). No es el
#   criterio del laboratorio (llamadores de C-a): un writer que crea un hecho sin pasar por C-a tambien entra.
#   Cada una tiene que figurar en el REGISTRO con su clase; una nueva o una retirada hace fallar el test:
#     EXIGE              crea un hecho real con efecto GASTO y categoria elegida: llama a exigir_propiedad DESPUES
#                        de la identidad y de C-a y ANTES del creador (M5 incluido: la prevision viaja en el
#                        mismo writer, sin exencion);
#     POR_CONSTRUCCION   la propiedad es dato obligatorio de su contrato (C-MEJ-01/02, C-COMPRA-01/03);
#     SIN_GASTO          no crea efecto GASTO con categoria (ingreso, Q-CV-11; transferencia);
#     REVERSION          OP-13: gasto de signo contrario de un hecho EXISTENTE con la categoria heredada del origen,
#                        sin seleccion nueva (D-CV-07, declarado para la revision).
#   Ademas: exigir_propiedad tiene firma cerrada (sin parametro de exencion, OBL-VIV-01.5) y se invoca siempre
#   con cuatro argumentos posicionales; ningun modulo de correccion (OP-21 V3, C-MEJ-03) compone un AFECTA_A.
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# ============================================================
from __future__ import annotations

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
APP = RAIZ / "backend" / "app"
MOTOR = ("services", "repositories", "core")
CREADORES = {"registrar_hecho_compuesto", "devolver", "transferir", "crear_hecho"}
C_A = {"validar_seleccion_categoria", "validar_categoria_y_magnitudes"}
IDENTIDAD = {"leer_estado"}

REGISTRO: dict[tuple[str, str], tuple[str, str]] = {
    ("api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion"): (
        "EXIGE", "VS-01 gasto-pagado (y M5: registro desde la prevision)"),
    ("api/ejecucion_reparto.py", "registrar_gasto_compartido.operacion"): (
        "EXIGE", "M3 gasto-compartido (y M5: registro desde la prevision)"),
    ("api/ejecucion_reembolsable.py", "registrar_gasto_reembolsable.operacion"): (
        "EXIGE", "M3 gasto-reembolsable (C-03)"),
    ("patrimonio/gasto_propiedad.py", "registrar_gasto"): ("POR_CONSTRUCCION", "C-MEJ-01: propiedad_id obligatorio"),
    ("patrimonio/gasto_propiedad.py", "registrar_mejora_historica"): (
        "POR_CONSTRUCCION", "C-MEJ-02: ruta de la propiedad; VALOR_ACTIVO sin categoria"),
    ("patrimonio/compra.py", "registrar_compra"): ("POR_CONSTRUCCION", "C-COMPRA-01: ruta de la propiedad"),
    ("patrimonio/compra.py", "gasto_posterior"): ("POR_CONSTRUCCION", "C-COMPRA-03: ruta de la propiedad"),
    ("api/ejecucion_registro.py", "registrar_ingreso_cobrado.operacion"): (
        "SIN_GASTO", "ingreso-cobrado: efecto INGRESO (Q-CV-11, la marca solo rige para GASTO)"),
    ("api/ejecucion_registro.py", "transferir_bajo_locks"): ("SIN_GASTO", "transferencia: sin efecto ni categoria"),
    ("api/ejecucion_devolucion.py", "registrar_devolucion.operacion"): (
        "REVERSION", "OP-13 sobre un origen existente; categoria heredada, sin seleccion (D-CV-07)"),
}
CLASES = {"EXIGE", "POR_CONSTRUCCION", "SIN_GASTO", "REVERSION"}
CORRECCIONES = ("api/ejecucion_categoria_v3.py", "patrimonio/correccion_clase.py")


# ------------------------------------------------------------------ AST
def _nombre(c: ast.Call) -> str | None:
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _funciones(arbol: ast.AST):
    """(qualname, nodo) de toda funcion, anidadas incluidas (las clases cualifican)."""
    def rec(nodo, pila):
        for h in ast.iter_child_nodes(nodo):
            if isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = pila + [h.name]
                if not isinstance(h, ast.ClassDef):
                    yield ".".join(q), h
                yield from rec(h, q)
            else:
                yield from rec(h, pila)
    yield from rec(arbol, [])


def _llamadas_propias(fn: ast.AST) -> list[ast.Call]:
    """Llamadas del cuerpo de `fn` sin entrar en funciones anidadas (las lambdas SI cuentan)."""
    salida: list[ast.Call] = []

    def rec(nodo):
        for h in ast.iter_child_nodes(nodo):
            if isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(h, ast.Call):
                salida.append(h)
            rec(h)
    rec(fn)
    return salida


def _orden(c: ast.Call) -> tuple[int, int]:
    return (c.lineno, c.col_offset)


def inventario(app: pathlib.Path) -> dict[tuple[str, str], ast.AST]:
    encontrados = {}
    for p in sorted(app.rglob("*.py")):
        rel = p.relative_to(app).as_posix()
        if rel.split("/")[0] in MOTOR:
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(_nombre(c) in CREADORES for c in _llamadas_propias(n)):
                encontrados[(rel, q)] = n
    return encontrados


def violaciones(app: pathlib.Path, registro: dict) -> list[str]:
    errores = []
    encontrados = inventario(app)
    for clave in sorted(set(encontrados) - set(registro)):
        errores.append(f"writer de hechos sin clasificar en OBL-VIV-01: {clave}")
    for clave in sorted(set(registro) - set(encontrados)):
        errores.append(f"entrada obsoleta del registro: {clave}")
    for clave, (clase, _) in registro.items():
        if clase != "EXIGE" or clave not in encontrados:
            continue
        llamadas = _llamadas_propias(encontrados[clave])
        exige = [c for c in llamadas if _nombre(c) == "exigir_propiedad"]
        creador = [c for c in llamadas if _nombre(c) in CREADORES]
        guarda = [c for c in llamadas if _nombre(c) in C_A]
        identidad = [c for c in llamadas if _nombre(c) in IDENTIDAD]
        if len(exige) != 1:
            errores.append(f"{clave}: exigir_propiedad debe invocarse exactamente una vez (hay {len(exige)})")
            continue
        if not creador or not _orden(exige[0]) < min(map(_orden, creador)):
            errores.append(f"{clave}: exigir_propiedad no va antes del creador")
        if not guarda or not min(map(_orden, guarda)) < _orden(exige[0]):
            errores.append(f"{clave}: exigir_propiedad no va despues de la guarda C-a (mismo FOR SHARE)")
        if not identidad or not min(map(_orden, identidad)) < _orden(exige[0]):
            errores.append(f"{clave}: exigir_propiedad no va despues de la identidad")
        if len(exige[0].args) != 4 or exige[0].keywords:
            errores.append(f"{clave}: exigir_propiedad con argumentos distintos de los cuatro del contrato")
        elif not (isinstance(exige[0].args[2], ast.Constant) and exige[0].args[2].value == "GASTO"):
            errores.append(f"{clave}: exigir_propiedad no se invoca para GASTO")
    return errores


# ------------------------------------------------------------------ tests
def test_registro_con_clases_validas():
    assert {c for c, _ in REGISTRO.values()} <= CLASES


def test_obl_viv_01_inventario_de_writers_de_hechos_cerrado_y_conforme():
    assert violaciones(APP, REGISTRO) == []


def test_exigir_propiedad_firma_cerrada_sin_exencion():
    arbol = ast.parse((APP / "api" / "elegibilidad_categoria.py").read_bytes().decode("utf-8"))
    fn = next(n for q, n in _funciones(arbol) if q == "exigir_propiedad")
    assert [a.arg for a in fn.args.args] == ["sesion", "categoria_id", "tipo_efecto", "propiedad_id"]
    assert not fn.args.kwonlyargs and not fn.args.vararg and not fn.args.kwarg and not fn.args.defaults
    # Unica funcion de la guarda: nadie mas lee asociada_vivienda para decidir un registro.
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(APP).as_posix()
        if rel in ("api/elegibilidad_categoria.py", "categorias/servicio.py", "categorias/repositorio.py",
                   "categorias/lecturas.py", "actividad/lecturas.py", "api/dto_categorias.py",
                   "api/app.py") or rel.split("/")[0] in MOTOR:
            continue
        assert "asociada_vivienda" not in p.read_bytes().decode("utf-8"), f"{rel} lee la marca fuera de la guarda"


def test_todas_las_llamadas_a_exigir_propiedad_son_de_writers_exige():
    llamadores = set()
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(APP).as_posix()
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(_nombre(c) == "exigir_propiedad" for c in _llamadas_propias(n)):
                llamadores.add((rel, q))
    assert llamadores == {k for k, (c, _) in REGISTRO.items() if c == "EXIGE"}


def test_las_correcciones_no_componen_afecta_a():
    """OBL-VIV-01.6 (M-CV-10): corregir la categoria no crea, mueve ni retira vinculos."""
    for rel in CORRECCIONES:
        texto = (APP / rel).read_bytes().decode("utf-8")
        assert 'tipo_relacion="AFECTA_A"' not in texto, rel                      # no compone el vinculo
        assert "propiedad_registro" not in texto and "DatosEntidadHecho" not in texto, rel


# ------------------------------------------------------------------ O-CV-14: writer plantado
PLANTADO = '''
from app.services.compuesto_service import HechosCompuestosService


def registrar_gasto_plantado(sesion, contexto, datos):
    return HechosCompuestosService(None).registrar_hecho_compuesto(contexto, datos)
'''


def _copia(tmp_path: pathlib.Path) -> pathlib.Path:
    destino = tmp_path / "app"
    for p in APP.rglob("*.py"):
        rel = p.relative_to(APP)
        if rel.parts[0] in MOTOR:
            continue
        (destino / rel).parent.mkdir(parents=True, exist_ok=True)
        (destino / rel).write_bytes(p.read_bytes())
    return destino


def test_o_cv_14_writer_plantado_sin_exigir_propiedad_hace_fallar_el_inventario(tmp_path):
    app = _copia(tmp_path)
    (app / "api" / "plantado.py").write_text(PLANTADO, encoding="utf-8")
    errores = violaciones(app, REGISTRO)
    assert errores == ["writer de hechos sin clasificar en OBL-VIV-01: ('api/plantado.py', 'registrar_gasto_plantado')"]


def test_o_cv_14_writer_exige_sin_la_llamada_hace_fallar_el_inventario(tmp_path):
    app = _copia(tmp_path)
    ruta = app / "api" / "ejecucion_reembolsable.py"
    texto = ruta.read_text(encoding="utf-8")
    assert texto.count("rechazo = exigir_propiedad(") == 1
    ruta.write_text(texto.replace("rechazo = exigir_propiedad(", "rechazo = (lambda *a: None)("), encoding="utf-8")
    assert any("exigir_propiedad debe invocarse" in e for e in violaciones(app, REGISTRO))


@pytest.mark.parametrize("cambio", ["exencion", "orden"])
def test_o_cv_14_exencion_o_desorden_detectados(tmp_path, cambio):
    app = _copia(tmp_path)
    ruta = app / "api" / "ejecucion_gasto_pagado.py"
    texto = ruta.read_text(encoding="utf-8")
    if cambio == "exencion":
        nuevo = texto.replace('rechazo = exigir_propiedad(sesion, intencion.categoria_id, "GASTO",',
                              'rechazo = exigir_propiedad(sesion, intencion.categoria_id, "GASTO", True,')
    else:   # despues del creador
        nuevo = texto.replace("        datos = componer(intencion, actor)\n",
                              "        datos = componer(intencion, actor)\n        op22 = None\n", 1)
        nuevo = nuevo.replace("                # 3b-bis.", "                # 3b-bis movido.")
        nuevo = nuevo.replace("op22.registrar_hecho_compuesto(contexto, datos)",
                              "op22.registrar_hecho_compuesto(contexto, datos) if False else "
                              "exigir_propiedad(sesion, None, 'GASTO', None)", 1)
    assert nuevo != texto
    ruta.write_text(nuevo, encoding="utf-8")
    assert violaciones(app, REGISTRO), cambio
