# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_233_f06_01_b1_rls_acl.py
# Ruta: tests/api/test_233_f06_01_b1_rls_acl.py
# Descripcion: F06-01 B1 · Propiedad (N1; mandato del lote 12, Parte B.4):
#   RLS/FORCE RLS y ACL de las superficies que escribe y lee B1, con el ROL
#   REAL (gapto_runtime + GUC de owner), sin DDL:
#     - FORCE RLS activa en entidades, propiedades, entidad_participaciones,
#       propiedad_valoraciones, actores_financieros y auditoria;
#     - gapto_runtime sin DELETE en participaciones ni valoraciones (0200,
#       0230) y sin UPDATE/DELETE en auditoria (append-only);
#     - como runtime, el owner A no ve ni modifica filas de B (0 filas en
#       SELECT y UPDATE) y no puede insertar una valoracion o una fila de
#       titularidad colgada de la propiedad de B (RLS WITH CHECK);
#     - el codigo de B1 no contiene DELETE ni SET ROLE, y su UNICO advisory es la
#       funcion del 0P de intencion (R1 v0.9.5 §I.5.4) y sus llamadas (O11.22).
#   El aislamiento por HTTP de cada ruta nueva lo cubre test_212 (G9).
# Version: 0.1.0 (F06-01 B1, lote 12)
# Version: 0.2.0 (F06 T1-F06 B2·R-B1 (F06-D009); R1 v0.9.5 §I.5.5 punto 4): el inventario admite SOLO la funcion
#   `bloquear_intencion_propiedad` de servicio.py (una definicion, sentencia exacta) y sus cuatro llamadas en B1,
#   cada una como primera llamada con `sesion` de su writer (O11.22); sigue prohibiendo DELETE, SET ROLE y
#   cualquier otro advisory en backend/app/propiedades; el literal 'gapto:INTENCION' solo vive en esa funcion
#   dentro de backend/app y su espacio es distinto del de OP-22 (O11.24).
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re
import uuid

import psycopg
import pytest

import f06_01_b1_helpers as b
import vs01_api_helpers as h

RAIZ = pathlib.Path(__file__).resolve().parents[2]
TABLAS = ("entidades", "propiedades", "entidad_participaciones", "propiedad_valoraciones", "actores_financieros",
          "auditoria")


def test_force_rls_en_las_tablas_de_b1():
    with psycopg.connect(h.dsn()) as c:
        filas = dict(c.execute(
            "SELECT relname, relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relnamespace = "
            "'gapto'::regnamespace AND relname = ANY(%s)", (list(TABLAS),)).fetchall())
    assert filas == {t: True for t in TABLAS}


@pytest.mark.parametrize("tabla,privilegio,esperado", [
    ("entidad_participaciones", "DELETE", False), ("propiedad_valoraciones", "DELETE", False),
    ("auditoria", "UPDATE", False), ("auditoria", "DELETE", False),
    ("entidad_participaciones", "UPDATE", True), ("propiedad_valoraciones", "UPDATE", True),
    ("propiedades", "UPDATE", True), ("entidades", "UPDATE", True),
])
def test_acl_de_gapto_runtime(tabla, privilegio, esperado):
    with psycopg.connect(h.dsn()) as c:
        valor = c.execute("SELECT has_table_privilege('gapto_runtime', %s, %s)",
                          (f"gapto.{tabla}", privilegio)).fetchone()[0]
    assert valor is esperado


def _como_runtime(owner, sql, params=()):
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SET LOCAL ROLE gapto_runtime")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        cur = c.execute(sql, params)
        return cur.rowcount, (cur.fetchall() if cur.description else None)


def test_runtime_aislado_por_owner():
    owner_a, actor_a, _ = b.entorno()
    owner_b, _, cli_b = b.entorno()
    p = b.crear(cli_b, b.alta())
    v = b.post(cli_b, f"/v1/propiedades/{p['id']}/valoraciones", b.valoracion(p)).json()["propiedad"]
    vid = v["valoraciones"][0]["id"]
    antes = b.huella()
    for sql in ("SELECT * FROM gapto.entidades WHERE id = %s", "SELECT * FROM gapto.propiedades WHERE entidad_id = %s",
                "SELECT * FROM gapto.entidad_participaciones WHERE entidad_id = %s",
                "SELECT * FROM gapto.propiedad_valoraciones WHERE propiedad_entidad_id = %s"):
        assert _como_runtime(owner_a, sql, (p["id"],))[1] == []
    assert _como_runtime(owner_a, "UPDATE gapto.entidades SET nombre = 'X' WHERE id = %s", (p["id"],))[0] == 0
    assert _como_runtime(owner_a, "UPDATE gapto.propiedad_valoraciones SET notas = 'X' WHERE id = %s", (vid,))[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner_a, "INSERT INTO gapto.propiedad_valoraciones (propiedad_entidad_id, valor_total, moneda, "
                               "metodo) VALUES (%s, 1, 'EUR', 'MANUAL')", (p["id"],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner_a, "INSERT INTO gapto.entidad_participaciones (entidad_id, actor_id, porcentaje, "
                               "vigente_desde) VALUES (%s, %s, 100, DATE '2027-01-01')", (p["id"], actor_a))
    assert b.huella() == antes
    assert _como_runtime(owner_b, "SELECT count(*) FROM gapto.propiedad_valoraciones WHERE id = %s",
                         (uuid.UUID(vid),))[1] == [(1,)]


SERVICIO = RAIZ / "backend" / "app" / "propiedades" / "servicio.py"
FUNCION_0P = "bloquear_intencion_propiedad"
SQL_0P = ("SELECT pg_advisory_xact_lock(hashtext('gapto:INTENCION'), "
          "hashtext(current_setting('gapto.owner_user_id') || ':' || %s::text))")
#: writer de B1 -> argumento que es la clave del 0P (§I.5.4, punto 2)
CLAVES_0P = {"alta": "entidad_id", "editar": "intencion_id", "cambiar_titularidad": "intencion_id",
             "alta_valoracion": "valoracion_id"}


def _definicion_0p() -> ast.FunctionDef:
    arbol = ast.parse(SERVICIO.read_text(encoding="utf-8"))
    defs = [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == FUNCION_0P]
    assert len(defs) == 1, defs
    return defs[0]


def test_codigo_de_b1_sin_delete_set_role_ni_advisory():
    """Solo la funcion del 0P nombra advisory; DELETE y SET ROLE siguen prohibidos en todo el modulo."""
    d = _definicion_0p()
    hallazgos = []
    for f in (RAIZ / "backend" / "app" / "propiedades").rglob("*.py"):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            codigo = linea.split("#", 1)[0]
            if re.search(r"\bDELETE\b|SET\s+(LOCAL\s+)?ROLE", codigo, re.I):
                hallazgos.append(f"{f.name}:{n}")
            elif re.search(r"advisory", codigo, re.I) and not (f == SERVICIO and d.lineno <= n <= d.end_lineno):
                hallazgos.append(f"{f.name}:{n}")
    assert hallazgos == []


def test_o11_22_funcion_unica_del_0p_y_cuatro_llamadas_en_primer_lugar():
    """O11.22: una definicion con la sentencia exacta y cuatro llamadas, una por writer y antes que nada."""
    d = _definicion_0p()
    llamadas_bd = [n for n in ast.walk(d) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert len(llamadas_bd) == 1 and llamadas_bd[0].func.attr == "uno", ast.dump(d)
    sql = llamadas_bd[0].args[0]
    assert isinstance(sql, ast.Constant) and sql.value == SQL_0P, ast.dump(sql)
    assert ast.unparse(llamadas_bd[0].args[1]) == "(str(intencion_id),)"
    arbol = ast.parse(SERVICIO.read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == FUNCION_0P]
    assert len(llamadas) == len(CLAVES_0P)
    writers = {n.name: n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name in CLAVES_0P}
    assert set(writers) == set(CLAVES_0P)
    for nombre, clave in CLAVES_0P.items():
        # primera llamada del writer que recibe la sesion (cualquier lectura o lock la necesita)
        con_sesion = [n for n in ast.walk(writers[nombre]) if isinstance(n, ast.Call)
                      and any(isinstance(a, ast.Name) and a.id == "sesion" for a in n.args)]
        primera = min(con_sesion, key=lambda n: (n.lineno, n.col_offset))
        assert ast.unparse(primera) == f"{FUNCION_0P}(sesion, {clave})", (nombre, ast.unparse(primera))
        assert sum(1 for n in con_sesion if isinstance(n.func, ast.Name) and n.func.id == FUNCION_0P) == 1, nombre


def test_o11_24_literal_del_espacio_solo_en_la_funcion_y_distinto_de_op22():
    """'gapto:INTENCION' solo dentro de la funcion del 0P (backend/app entero); espacio distinto de OP-22."""
    d = _definicion_0p()
    apariciones = []
    for f in (RAIZ / "backend" / "app").rglob("*.py"):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "gapto:INTENCION" in linea.split("#", 1)[0]:
                apariciones.append((f.relative_to(RAIZ).as_posix(), n))
    assert apariciones and all(f == "backend/app/propiedades/servicio.py" and d.lineno <= n <= d.end_lineno
                               for f, n in apariciones), apariciones
    with psycopg.connect(h.dsn()) as c:
        espacios = c.execute("SELECT hashtext('gapto:INTENCION'), hashtext('gapto:OP22'), "
                             "hashtext('gapto:INVERSIONES')").fetchone()
    assert len(set(espacios)) == 3, espacios
