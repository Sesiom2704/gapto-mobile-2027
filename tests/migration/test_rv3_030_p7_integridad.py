# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_030_p7_integridad.py
# Ruta: tests/migration/test_rv3_030_p7_integridad.py
# Descripcion: RV3 / P7 v0.1.0 (rv3_p7_integridad.py). Bateria adversarial: cada comprobacion debe pasar a
#              violacion cuando se le inyecta el defecto que vigila. Todo ocurre en el laboratorio de REFERENCIA
#              (nunca en la carga P6) dentro de transacciones que siempre hacen ROLLBACK: esquema sintetico con
#              constraints NOT VALID para los chequeos genericos y, en gapto, filas insertadas con
#              session_replication_role=replica (FK y triggers desactivados solo en esa transaccion) para las
#              invariantes de triggers, destinos polimorficos y trazabilidad. Sin datos V3.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("rv3_p7_integridad", RAIZ / "scripts" / "migration_v3" / "rv3_p7_integridad.py")
P7 = importlib.util.module_from_spec(_s)
sys.modules["rv3_p7_integridad"] = P7
_s.loader.exec_module(P7)
URL = os.environ.get("GAPTO_RV3_IMPORT_URL")
pytestmark = pytest.mark.skipif(not URL, reason="sin laboratorio RV3_IMPORT")


def _admin_dsn():
    # mismo laboratorio de referencia, rol administrador local (solo para montar defectos en ROLLBACK)
    partes = dict(p.split("=", 1) for p in URL.split())
    partes["user"] = "postgres"
    return " ".join(f"{k}={v}" for k, v in partes.items())


@pytest.fixture
def cx():
    import psycopg
    with psycopg.connect(_admin_dsn()) as c:
        assert c.execute("SELECT current_database()").fetchone()[0] != "gapto2027_p6"  # nunca la carga certificada
        yield c
        c.rollback()


def test_huellas_referencia_canonica_y_comparacion():
    ref = P7.huellas_referencia("0330")
    assert ref["recuentos"] == "777/644/287/82/58/28/1031/3" and len(ref) == 9
    assert P7.comparar_huellas(dict(ref), ref) == []
    assert P7.comparar_huellas({**ref, "h5_triggers": "otra"}, ref) == ["h5_triggers"]


def _sintetico(c):
    c.execute("CREATE SCHEMA p7t")
    c.execute("CREATE TABLE p7t.padre (id int PRIMARY KEY)")
    c.execute("""CREATE TABLE p7t.hijo (id int PRIMARY KEY, padre_id int, v int, rango int4range, grupo int,
                                        nn text NOT NULL DEFAULT 'x')""")
    c.execute("INSERT INTO p7t.padre VALUES (1)")
    c.execute("INSERT INTO p7t.hijo (id, padre_id, v, rango, grupo) VALUES (1, 1, 5, '[1,5)', 1), (2, 1, 6, '[10,15)', 1)")


def test_genericos_limpios(cx):
    _sintetico(cx)
    for f in (P7.check_not_null, P7.check_unicos, P7.check_fk, P7.check_check, P7.check_exclude):
        assert not f(cx, "p7t")["violaciones"], f.__name__


def test_fk_detecta_huerfano(cx):
    _sintetico(cx)
    cx.execute("INSERT INTO p7t.hijo (id, padre_id) VALUES (3, 99)")
    cx.execute("ALTER TABLE p7t.hijo ADD CONSTRAINT fk_padre FOREIGN KEY (padre_id) REFERENCES p7t.padre(id) NOT VALID")
    assert P7.check_fk(cx, "p7t")["violaciones"] == {"fk_padre": 1}


def test_check_detecta_violacion_y_catalogo_no_validada(cx):
    _sintetico(cx)
    cx.execute("ALTER TABLE p7t.hijo ADD CONSTRAINT ck_v CHECK (v < 6) NOT VALID")
    assert P7.check_check(cx, "p7t")["violaciones"] == {"ck_v": 1}
    assert P7.check_catalogo(cx, "p7t")["no_validadas"] == 1


def test_unico_detecta_duplicado_con_predicado_y_expresion(cx):
    _sintetico(cx)
    cx.execute("INSERT INTO p7t.hijo (id, v, grupo) VALUES (3, 5, 2)")
    cx.execute("CREATE INDEX ix ON p7t.hijo (v)")  # no unico: no cuenta
    cx.execute("UPDATE pg_index SET indisunique = true WHERE indexrelid = 'p7t.ix'::regclass")  # simula unicidad rota
    assert P7.check_unicos(cx, "p7t")["violaciones"] == {"ix": 1}


def test_exclude_detecta_solape(cx):
    _sintetico(cx)
    cx.execute("CREATE TABLE p7t.r (g int, rango int4range)")
    cx.execute("INSERT INTO p7t.r VALUES (1, '[1,5)'), (1, '[3,12)'), (2, '[3,12)')")
    # la exclusion se valida sobre 0 filas (predicado falso) y despues se amplia en el catalogo: queda un solape
    cx.execute("ALTER TABLE p7t.r ADD CONSTRAINT r_excl EXCLUDE USING gist (g WITH =, rango WITH &&) WHERE (false)")
    assert not P7.check_exclude(cx, "p7t")["violaciones"]
    cx.execute("UPDATE pg_index SET indpred = NULL WHERE indexrelid = 'p7t.r_excl'::regclass")
    assert P7.check_exclude(cx, "p7t")["violaciones"] == {"r_excl": 1}


def test_not_null_detecta_nulo(cx):
    _sintetico(cx)
    cx.execute("ALTER TABLE p7t.hijo ALTER COLUMN nn DROP NOT NULL")
    cx.execute("INSERT INTO p7t.hijo (id, nn) VALUES (3, NULL)")
    cx.execute("UPDATE pg_attribute SET attnotnull = true WHERE attrelid = 'p7t.hijo'::regclass AND attname = 'nn'")
    assert P7.check_not_null(cx, "p7t")["violaciones"] == {"hijo.nn": 1}


# ---------------------------------------------------------------- invariantes y trazabilidad sobre gapto (ROLLBACK)
def _replica(c):
    c.execute("SET LOCAL session_replication_role = replica")


def test_invariantes_detectan_defectos(cx):
    assert not P7.check_invariantes(cx, "gapto")["violaciones"]
    _replica(cx)
    owner, actor, ent, hecho, efecto = (uuid.uuid4() for _ in range(5))
    cx.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, %s, 'CONTEXTO', 'x')",
               (ent, owner))  # sin subtipo
    cx.execute("INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
               "VALUES (%s, %s, %s, 50, '2026-01-01')", (uuid.uuid4(), ent, actor))  # suma 50
    cx.execute("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, estado_atribucion) "
               "VALUES (%s, %s, 'GASTO', 10, 'COMPLETA')", (efecto, hecho))  # sin atribuciones
    v = P7.check_invariantes(cx, "gapto")["violaciones"]
    assert v["subtipo_unico (fn_check_entidad_subtipo_unico)"] == 1
    assert v["participacion_suma_100 (fn_check_participacion_suma: entidades)"] == 1
    assert v["atribucion_suma (fn_check_atribucion_suma)"] == 1


def test_polimorficos_y_trazabilidad_detectan_defectos(cx):
    _replica(cx)
    origen = uuid.uuid4()
    for tabla, destino, tipo in (("hechos_financieros", uuid.uuid4(), "CREADO"), ("tabla_que_no_existe", uuid.uuid4(), "CREADO"),
                                 ("hechos_financieros", uuid.uuid4(), "OBSOLETO")):  # OBSOLETO con destino
        cx.execute("INSERT INTO gapto.mapeos_importacion (id, registro_origen_id, tabla_destino, registro_destino_id, "
                   "tipo_mapping, confianza) VALUES (%s, %s, %s, %s, %s, 'ALTA')",
                   (uuid.uuid4(), origen, tabla, destino, tipo))
    pol = P7.check_polimorficos(cx, "gapto")["violaciones"]
    assert pol["destino_inexistente.hechos_financieros"] == 2
    assert pol["tabla_destino_invalida"] == ["tabla_que_no_existe"]
    assert pol["tipo_vs_destino_incoherente"] == 1
    tr = P7.check_trazabilidad(cx, "gapto", {"mapeos": 0})["violaciones"]
    assert tr["mapeos"] == {"esperado": 0, "obtenido": 3} and tr["mapeo_sin_origen"] == 3


def test_sin_cambios_detecta_fila_posterior(cx):
    base = P7.check_sin_cambios(cx, "gapto", 10 ** 9)  # BD de referencia: solo semillas
    assert not base["violaciones"] and base["semillas_0330"] == 10
    xid_antes = int(cx.execute("SELECT pg_snapshot_xmax(pg_current_snapshot())::text").fetchone()[0]) - 1
    _replica(cx)
    cx.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, %s, 'CONTEXTO', 'y')",
               (uuid.uuid4(), uuid.uuid4()))
    v = P7.check_sin_cambios(cx, "gapto", xid_antes)["violaciones"]
    assert v["filas_con_xmin_posterior_a_la_carga"] >= 1
