# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_323_f06_t6_s6_clase_no_persistida.py
# Ruta: tests/api/test_323_f06_t6_s6_clase_no_persistida.py
# Descripcion: F06 T6 · S6 (N1 conservador): retirar «¿Que tipo de gasto es?» del registro (dictamen 1 Q3/A4; DF-14;
#   F09 0.55 §12.107.3). El SERVIDOR NO CAMBIA: sigue aceptando REPARACION en el bloque `propiedad` de VS-01. Este test
#   demuestra la equivalencia que permite retirar la pregunta: un gasto de vivienda con clase GASTO_CORRIENTE y otro
#   identico con REPARACION componen EXACTAMENTE lo mismo (tipo de hecho, efectos, categoria, atribuciones, posiciones,
#   movimientos y vinculo con la propiedad) y la clase no se persiste en ningun sitio. Discriminante del mutante
#   M-S6-REP (el servidor rechaza REPARACION).
#   Exige GAPTO_TEST_DATABASE_URL (base local DESECHABLE con la cadena aplicada).
# Version: 0.1.0 (F06 T6 · S6)
# ============================================================

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import f05_06_m5_helpers as m5
import f06_01_b3_helpers as b3
import test_280_f06_t2_cat_viv_oraculos as cv

D = Decimal


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


def _composicion(lab, hid: uuid.UUID) -> dict:
    """Todo lo que el registro persiste para el hecho, sin identificadores propios del hecho."""
    return {
        "tipo": lab.sql("SELECT th.codigo FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
                        "WHERE h.id = %s", (hid,)),
        "efectos": sorted((t, str(c), str(D(i).quantize(D("0.01")))) for t, c, i in lab.sql(
            "SELECT tipo_efecto, categoria_id, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,))),
        "atribuciones": cv._atribuciones(lab, hid),
        "posiciones": cv._posiciones(lab, hid),
        "movimientos": m5.movimientos(lab.owner, hid),
        "afecta_a": sorted((str(e), p, f) for _, e, p, f in cv._afecta_a(lab, hid)),
    }


def test_gasto_corriente_y_reparacion_componen_igual_y_la_clase_no_se_persiste(lab):
    cv._marcada(lab)
    hids = {}
    for clase in ("GASTO_CORRIENTE", "REPARACION"):
        j = cv._ok(lab, cv._vs01(lab, propiedad=cv._bloque(lab, clase=clase)))                   # M-S6-REP: REPARACION se acepta
        hids[clase] = uuid.UUID(j["hecho_id"])
    a, b = (_composicion(lab, hids[k]) for k in ("GASTO_CORRIENTE", "REPARACION"))
    assert a == b
    assert a["tipo"] == [("GASTO",)]
    # Ninguna tabla del dominio guarda la clase del registro: ninguna columna de texto de los hechos ni de sus
    # efectos contiene «REPARACION» ni «GASTO_CORRIENTE».
    cols = lab.sql("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'gapto' "
                   "AND table_name IN ('hechos_financieros', 'hecho_efectos', 'hecho_entidades', 'efecto_atribuciones') "
                   "AND data_type IN ('text', 'character varying')")
    for tabla, col in cols:
        n = lab.sql(f"SELECT count(*) FROM gapto.{tabla} WHERE {col}::text IN ('REPARACION', 'GASTO_CORRIENTE')")  # noqa: S608
        assert n == [(0,)], (tabla, col)


def test_sin_clase_vale_gasto_corriente(lab):
    cv._marcada(lab)
    bloque = cv._bloque(lab)
    del bloque["clase"]
    j = cv._ok(lab, cv._vs01(lab, propiedad=bloque))
    con = cv._ok(lab, cv._vs01(lab, propiedad=cv._bloque(lab, clase="GASTO_CORRIENTE")))
    assert _composicion(lab, uuid.UUID(j["hecho_id"])) == _composicion(lab, uuid.UUID(con["hecho_id"]))
