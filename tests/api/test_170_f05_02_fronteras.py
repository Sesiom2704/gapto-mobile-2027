# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_170_f05_02_fronteras.py
# Ruta: tests/api/test_170_f05_02_fronteras.py
# Descripcion: Fronteras negativas de F05-02 B1 (F05-D026 CC-02-6; AJ-D026-12,
#   AJ-D025-11) e inventario de writers (CC-02-5).
#   - Dimensiones diferidas: alta y edicion con tercero_id o entidad_id se
#     rechazan con PREFERENCIA_DIMENSION_DIFERIDA; el resolver ignora filas
#     con tercero_id o entidad_id escritas por SQL directo, aunque sean mas
#     especificas.
#   - La propuesta solo tiene cuenta y presupuestable: no propone categoria,
#     concepto ni atribucion.
#   - Inventario fail-closed: ningun INSERT/UPDATE/DELETE/MERGE/TRUNCATE
#     sobre preferencias_registro fuera de backend/app/preferencias/
#     repositorio.py (solo INSERT y UPDATE, DELETE = 0); las primitivas solo
#     se invocan desde servicio.py y cada comando toma el advisory como
#     PRIMERA llamada; el INSERT no admite tercero_id, entidad_id ni
#     prioridad, y COLUMNAS_EDITABLES tampoco.
#   - El paquete backend/app/preferencias/ solo escribe preferencias_registro:
#     ningun writer de terceros ni de ninguna otra tabla (comprobacion
#     estatica ACOTADA al paquete: no depende de lo que F05-04 anada en otro
#     modulo).
#   Estatico salvo los dos primeros apartados (base desechable).
#
#   v0.2.0 (F05-02 B1-C, AJ-B1-05/06): se RETIRAN de la suite permanente las
#   comprobaciones ancladas a una base concreta (a44bb34): «el diff no anade
#   writer de terceros», «test_154 solo aditivo» e «I13 sin cambios por AST».
#   Pasan a scripts/dev/verificar_cierre_f05_02_b1.py (--base/--head
#   obligatorios), que se ejecuta al cierre del bloque. Queda aqui la
#   garantia permanente acotada al paquete. I13 lo sigue protegiendo
#   test_154 con sus propias reglas.
#
#   v0.3.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E2, §46.4 R6; decision OPCION
#   A2 del STOP 2, tabla «tests adaptados» del handoff J2+J3): tercero_id
#   pasa a ser dimension OPERATIVA. Casos conservados con oraculo nuevo:
#   [tercero_id] en alta/edicion -> categoria + tercero rechazado con
#   PREFERENCIA_AMBITO_NO_ADMITIDO; [tercero_id] en el resolver -> la fila
#   tipo + tercero solo se consume en el contexto de ese tercero; el writer
#   escribe tercero_id (INSERT y COLUMNAS_EDITABLES) y sigue sin escribir
#   entidad_id ni prioridad. [entidad_id] no cambia.
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re
import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PAQUETE = RAIZ / "backend" / "app" / "preferencias"
REPO_PREF = "backend/app/preferencias/repositorio.py"
SERV_PREF = "backend/app/preferencias/servicio.py"
EXCLUIDOS = {"scripts/dev/mutantes_f05_02.py"}  # arnes: los mutantes son texto

_ESCRITURA_PREF = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
    r"preferencias_registro\b",
    re.IGNORECASE,
)
_ESCRITURA_TERCEROS = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
    r"(terceros|tercero_\w+|hecho_terceros|actores_financieros)\b",
    re.IGNORECASE,
)
_ESCRITURA_GAPTO = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?gapto\s*\.\s*\"?(\w+)",
    re.IGNORECASE,
)


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(RAIZ).as_posix()


def _codigo_productivo() -> list[pathlib.Path]:
    candidatos = sorted((RAIZ / "backend").rglob("*.py")) + sorted((RAIZ / "scripts").rglob("*.py"))
    return [p for p in candidatos if _rel(p) not in EXCLUIDOS]


# ------------------------------------------------------------------ dimensiones diferidas
@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="A")
    b = ph.cuenta(owner, actor, nombre="B")
    return owner, actor, cli, a, b


def _entidad(owner) -> uuid.UUID:
    eid = uuid.uuid4()
    c = fh.sesion_owner(owner)
    try:
        c.execute("SET CONSTRAINTS ALL DEFERRED")
        c.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                  "VALUES (%s, %s, 'PROPIEDAD', 'Vivienda sintetica')", (eid, owner))
        c.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')", (eid,))
        c.execute("COMMIT")
    finally:
        c.close()
    return eid


@pytest.mark.parametrize("campo", ["tercero_id", "entidad_id"])
def test_alta_y_edicion_con_dimension_diferida_se_rechazan(t, campo):
    owner, _, cli, a, _ = t
    if campo == "tercero_id":
        # E2: tercero operativo; el caso negativo es categoria + tercero (R6).
        extra = {"tercero_id": ph.tercero(owner), "categoria_id": ph.categoria(owner, "Super")}
        codigo = "PREFERENCIA_AMBITO_NO_ADMITIDO"
    else:
        extra = {"entidad_id": _entidad(owner)}
        codigo = "PREFERENCIA_DIMENSION_DIFERIDA"
    pid, r = ph.alta(cli, cuenta_default_id=a, **extra)
    assert r.status_code == 422 and r.json()["codigo"] == codigo
    assert ph.fila(owner, pid) is None
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.editar(cli, pid, 1, cuenta_default_id=a, **extra)
    assert r.status_code == 422 and r.json()["codigo"] == codigo
    assert ph.n_preferencias(owner) == 1


@pytest.mark.parametrize("campo", ["tercero_id", "entidad_id"])
def test_el_resolver_ignora_filas_con_dimension_diferida(t, campo):
    owner, _, _, a, b = t
    cat = ph.categoria(owner, "Super")
    if campo == "tercero_id":
        # E2: la fila tipo + tercero es operativa: se ignora fuera del contexto
        # de su tercero y se consume (y gana) dentro de el.
        ter = ph.tercero(owner)
        p_ter = ph.insertar_sql(owner, tercero_id=ter, cuenta=b, presupuestable=True)
        p_glob = ph.insertar_sql(owner, cuenta=a)
        p = ph.resolver(owner, cat)
        assert ph.origen(p, "cuenta") == ("PREFERENCIA", p_glob) and p["presupuestable"] is None
        p = ph.resolver(owner, cat, tercero_id=ter)
        assert ph.origen(p, "cuenta") == ("PREFERENCIA", p_ter)
        return
    # Mas especifica y con todos los campos: si se consumiera, ganaria.
    ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), categoria_id=cat, cuenta=b, presupuestable=True,
                    entidad_id=_entidad(owner))
    p_glob = ph.insertar_sql(owner, cuenta=a)
    p = ph.resolver(owner, cat)
    assert ph.origen(p, "cuenta") == ("PREFERENCIA", p_glob)
    assert p["presupuestable"] is None


def test_la_propuesta_solo_tiene_cuenta_y_presupuestable(t):
    owner, _, cli, a, _ = t
    from app.api.dto_preferencias import PropuestaRegistro

    assert set(PropuestaRegistro.model_fields) == {"cuenta", "presupuestable"}
    assert set(ph.resolver(owner, None)) == {"cuenta", "presupuestable"}
    assert set(ph.propuesta_http(cli).json()) == {"cuenta", "presupuestable"}


# ------------------------------------------------------------------ inventario de writers
def test_escritores_de_preferencias_registro_solo_en_el_repositorio():
    hallados = {}
    for p in _codigo_productivo():
        for m in _ESCRITURA_PREF.finditer(p.read_bytes().decode("utf-8")):
            hallados.setdefault(_rel(p), set()).add(m.group(1).split()[0].upper())
    assert hallados == {REPO_PREF: {"INSERT", "UPDATE"}}, hallados


def test_primitivas_solo_desde_el_servicio_y_advisory_primero():
    primitivas = {"insertar_preferencia", "actualizar_preferencia"}
    for p in _codigo_productivo():
        ruta = _rel(p)
        if ruta in (REPO_PREF, SERV_PREF):
            continue
        texto = p.read_bytes().decode("utf-8")
        assert not any(n in texto for n in primitivas), ruta
    arbol = ast.parse((RAIZ / SERV_PREF).read_bytes().decode("utf-8"))
    for fn in (n for n in arbol.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")):
        cuerpo = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) \
            else fn.body
        primera = cuerpo[0]
        assert isinstance(primera, ast.Expr) and isinstance(primera.value, ast.Call) \
            and ast.unparse(primera.value.func) == "repo.tomar_advisory", fn.name


def test_el_writer_no_escribe_dimensiones_diferidas_ni_prioridad():
    from app.preferencias import repositorio as repo

    # E2: tercero_id es operativo y editable; entidad_id y prioridad no.
    assert "tercero_id" in repo.COLUMNAS_EDITABLES
    assert not repo.COLUMNAS_EDITABLES & {"entidad_id", "prioridad", "id", "owner_user_id"}
    arbol = ast.parse((RAIZ / REPO_PREF).read_bytes().decode("utf-8"))
    fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "insertar_preferencia")
    cuerpo = fn.body[1:]  # sin la docstring
    sql = " ".join(c.value for s in cuerpo for c in ast.walk(s) if isinstance(c, ast.Constant)
                   and isinstance(c.value, str))
    assert "INSERT INTO gapto.preferencias_registro" in sql
    assert "tercero_id" in sql
    for col in ("entidad_id", "prioridad"):
        assert col not in sql, col


# ------------------------------------------------------------------ paquete sin writer de terceros
def _literales_sql_del_paquete() -> dict[str, list[str]]:
    """Literales de texto (SQL incluido) de cada modulo del paquete."""
    salida = {}
    for p in sorted(PAQUETE.rglob("*.py")):
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        salida[_rel(p)] = [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return salida


def test_el_paquete_de_preferencias_no_escribe_terceros_ni_otras_tablas():
    """AJ-D025-11 / AJ-D026-12, garantia permanente acotada al paquete: su SQL
    solo escribe preferencias_registro y nunca terceros ni tablas de
    tercero. No depende de una base ni de otros modulos (F05-04 anadira su
    writer fuera de este paquete)."""
    tablas, terceros = set(), []
    literales = _literales_sql_del_paquete()
    assert REPO_PREF in literales and SERV_PREF in literales
    for ruta, textos in literales.items():
        for texto in textos:
            tablas |= {m.group(4).lower() for m in _ESCRITURA_GAPTO.finditer(texto)}
            terceros += [f"{ruta}: {texto}" for _ in _ESCRITURA_TERCEROS.finditer(texto)]
    assert not terceros, terceros
    assert tablas == {"preferencias_registro"}, tablas
