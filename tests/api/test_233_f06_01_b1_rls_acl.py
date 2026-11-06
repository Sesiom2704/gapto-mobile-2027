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
#     - el codigo de B1 no contiene DELETE, SET ROLE ni advisory locks.
#   El aislamiento por HTTP de cada ruta nueva lo cubre test_212 (G9).
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

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


def test_codigo_de_b1_sin_delete_set_role_ni_advisory():
    hallazgos = []
    for f in (RAIZ / "backend" / "app" / "propiedades").rglob("*.py"):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            codigo = linea.split("#", 1)[0]
            if re.search(r"\bDELETE\b|SET\s+(LOCAL\s+)?ROLE|advisory", codigo, re.I):
                hallazgos.append(f"{f.name}:{n}")
    assert hallazgos == []
