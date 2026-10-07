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
#   - Diff del bloque frente a la base a44bb34: no anade writer de terceros;
#     el diff de test_154 es solo aditivo (clase PREFERENCIA, REGISTRO,
#     FRONTERA, EXCLUIDOS e I3 ampliado) y las funciones de I13 no cambian.
#   Estatico salvo los dos primeros apartados (base desechable).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BASE_COMMIT = "a44bb34"
REPO_PREF = "backend/app/preferencias/repositorio.py"
SERV_PREF = "backend/app/preferencias/servicio.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
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


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(RAIZ).as_posix()


def _codigo_productivo() -> list[pathlib.Path]:
    candidatos = sorted((RAIZ / "backend").rglob("*.py")) + sorted((RAIZ / "scripts").rglob("*.py"))
    return [p for p in candidatos if _rel(p) not in EXCLUIDOS]


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr.strip()} (se exige la base {BASE_COMMIT})"
    return r.stdout


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
    valor = ph.tercero(owner) if campo == "tercero_id" else _entidad(owner)
    pid, r = ph.alta(cli, cuenta_default_id=a, **{campo: valor})
    assert r.status_code == 422 and r.json()["codigo"] == "PREFERENCIA_DIMENSION_DIFERIDA"
    assert ph.fila(owner, pid) is None
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.editar(cli, pid, 1, cuenta_default_id=a, **{campo: valor})
    assert r.status_code == 422 and r.json()["codigo"] == "PREFERENCIA_DIMENSION_DIFERIDA"
    assert ph.n_preferencias(owner) == 1


@pytest.mark.parametrize("campo", ["tercero_id", "entidad_id"])
def test_el_resolver_ignora_filas_con_dimension_diferida(t, campo):
    owner, _, _, a, b = t
    cat = ph.categoria(owner, "Super")
    valor = ph.tercero(owner) if campo == "tercero_id" else _entidad(owner)
    # Mas especifica y con todos los campos: si se consumiera, ganaria.
    ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), categoria_id=cat, cuenta=b, presupuestable=True,
                    **{campo: valor})
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

    assert not repo.COLUMNAS_EDITABLES & {"tercero_id", "entidad_id", "prioridad", "id", "owner_user_id"}
    arbol = ast.parse((RAIZ / REPO_PREF).read_bytes().decode("utf-8"))
    fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "insertar_preferencia")
    cuerpo = fn.body[1:]  # sin la docstring
    sql = " ".join(c.value for s in cuerpo for c in ast.walk(s) if isinstance(c, ast.Constant)
                   and isinstance(c.value, str))
    assert "INSERT INTO gapto.preferencias_registro" in sql
    for col in ("tercero_id", "entidad_id", "prioridad"):
        assert col not in sql, col


# ------------------------------------------------------------------ diff del bloque
def test_el_diff_del_bloque_no_anade_writer_de_terceros():
    diff = _git("diff", BASE_COMMIT, "--", "backend", "scripts")
    nuevos = _git("ls-files", "--others", "--exclude-standard", "--", "backend", "scripts").split()
    anadidas = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    for ruta in nuevos:
        if ruta not in EXCLUIDOS and ruta.endswith(".py"):
            anadidas += (RAIZ / ruta).read_bytes().decode("utf-8").splitlines()
    culpables = [l for l in anadidas if _ESCRITURA_TERCEROS.search(l)]
    assert not culpables, culpables


def _funciones(texto: str) -> dict[str, str]:
    arbol = ast.parse(texto)
    return {n.name: ast.dump(n) for n in arbol.body if isinstance(n, ast.FunctionDef)}


def test_el_diff_de_test_154_es_solo_aditivo_e_i13_intacto():
    antes = _git("show", f"{BASE_COMMIT}:{T154}")
    despues = (RAIZ / T154).read_bytes().decode("utf-8")
    f_antes, f_despues = _funciones(antes), _funciones(despues)
    # Ninguna funcion desaparece ni cambia, salvo I3 (admite PREFERENCIA).
    assert set(f_antes) <= set(f_despues)
    cambiadas = {n for n in f_antes if f_antes[n] != f_despues[n]}
    assert cambiadas <= {"test_i3_frontera_solo_r_guarda_o_a_frontera"}, cambiadas
    assert all(f_antes[n] == f_despues[n] for n in f_antes if n.startswith("test_i13"))
    # Lineas eliminadas: solo las sustituidas por su version ampliada.
    diff = _git("diff", "-U0", BASE_COMMIT, "--", T154)
    quitadas = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    puestas = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    permitidas = {
        "# Version: 0.8.1": "# Version: 0.9.0",
        'FRONTERA = ("backend/app/api/", "backend/app/categorias/", "backend/app/magnitudes/")':
            'FRONTERA = ("backend/app/api/", "backend/app/categorias/", "backend/app/magnitudes/", '
            '"backend/app/preferencias/")',
        'CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO", "SEED_DEV"}':
            'CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO", "SEED_DEV", "PREFERENCIA"}',
        '            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO"}, (ruta, qual, clase)':
            '            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO", "PREFERENCIA"}, (ruta, qual, clase)',
    }
    assert set(quitadas) <= set(permitidas), set(quitadas) - set(permitidas)
    for vieja in quitadas:
        assert permitidas[vieja] in puestas, vieja
    # Las entradas nuevas del REGISTRO son de los ficheros del bloque y
    # ninguna previa cambia (se evalua el modulo de cada version).
    def registro(texto: str) -> tuple[dict, dict]:
        espacio: dict = {"__name__": "t154_version", "__file__": str(RAIZ / T154)}
        exec(compile(texto, str(RAIZ / T154), "exec"), espacio)
        return espacio["REGISTRO"], espacio["EXCLUIDOS"]

    r_antes, e_antes = registro(antes)
    r_despues, e_despues = registro(despues)
    assert all(r_despues.get(k) == v for k, v in r_antes.items()), "entrada previa modificada"
    nuevas = set(r_despues) - set(r_antes)
    ficheros = {"backend/app/api/app.py", "backend/app/api/dto_preferencias.py"}
    assert all(k[0] in ficheros or k[0].startswith("backend/app/preferencias/") for k in nuevas), nuevas
    assert all(r_despues[k][0] in {"PREFERENCIA", "R"} for k in nuevas)
    assert e_antes.items() <= e_despues.items() and set(e_despues) - set(e_antes) == {"scripts/dev/mutantes_f05_02.py"}
