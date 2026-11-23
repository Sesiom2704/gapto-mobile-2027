# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_320_f06_t6_s4_presupuesto_defecto.py
# Ruta: tests/api/test_320_f06_t6_s4_presupuesto_defecto.py
# Descripcion: F06 T6 · S4 (N1): presupuesto «Si» por defecto (dictamen 1 Q1/A2; DF-04/06/12;
#   F09 0.55 §12.107.3; contrato en la evidencia T6 P9_s4/S4_CONTRATO.md). Lectura aditiva
#   `GET /v1/registro/presupuesto-propuesto`: precedencia preferencia > categoria (incluido No)
#   > «Si» por defecto; false nunca pasa a «Si»; gasto e ingreso; sin categoria. Las rutas de
#   propuesta de hoy no cambian (E1 para quien no pide la lectura nueva) y el registro sigue
#   exigiendo `presupuestable` explicito: el valor por defecto nunca se aplica al sellar ni en
#   un replay. Discriminantes de los mutantes M-S4-01..04.
#   Exige GAPTO_TEST_DATABASE_URL (base local DESECHABLE con la cadena aplicada).
# Version: 0.1.0 (F06 T6 · S4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h

from app.preferencias import presupuesto_defecto as pd

RUTA = "/v1/registro/presupuesto-propuesto"
FECHA = ph.FECHA


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, actor, cli


def _pedir(cli, tipo: str = "GASTO", categoria: uuid.UUID | None = None, **extra) -> dict:
    q = f"?tipo={tipo}&fecha={FECHA.isoformat()}&sin_tercero=true"
    q += f"&categoria_id={categoria}" if categoria else "&sin_categoria=true"
    for k, v in extra.items():
        q += f"&{k}={v}"
    r = cli.get(RUTA + q, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _categoria(owner, nombre: str, *, ambito: str = "GASTO", presupuestable: bool | None = None) -> uuid.UUID:
    cid = ph.categoria(owner, nombre, ambito=ambito)
    if presupuestable is not None:
        h.como_owner(owner, "UPDATE gapto.categorias_financieras SET presupuestable_default = %s WHERE id = %s", (presupuestable, cid))
    return cid


def _tipo(owner, codigo: str) -> uuid.UUID:
    return h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo=%s", (codigo,))[0][0]


# ------------------------------------------------------------------ precedencia (dominio puro)
def test_precedencia_pura_ausencia_false_true_y_origenes():
    pref_false = {"valor": False, "origen": {"capa": "PREFERENCIA", "preferencia_id": "p"}}
    pref_true = {"valor": True, "origen": {"capa": "PREFERENCIA", "preferencia_id": "p"}}
    plantilla_false = {"valor": False, "origen": {"capa": "PLANTILLA", "plantilla_id": "x", "preferencia_id": None}}
    assert pd.precedencia(None, None) == {"valor": True, "origen": "POR_DEFECTO"}
    assert pd.precedencia(None, True) == {"valor": True, "origen": "CATEGORIA"}
    assert pd.precedencia(None, False) == {"valor": False, "origen": "CATEGORIA"}          # M-S4-03
    assert pd.precedencia(pref_false, True) == {"valor": False, "origen": "PREFERENCIA"}  # M-S4-01 / M-S4-02
    assert pd.precedencia(pref_false, None) == {"valor": False, "origen": "PREFERENCIA"}  # false nunca pasa a «Si»
    assert pd.precedencia(pref_true, False) == {"valor": True, "origen": "PREFERENCIA"}   # M-S4-01
    assert pd.precedencia(plantilla_false, True) == {"valor": False, "origen": "EXPLICITO"}
    assert set(pd.ORIGENES) == {"EXPLICITO", "PREFERENCIA", "CATEGORIA", "POR_DEFECTO"}


# ------------------------------------------------------------------ ruta (base real, RLS)
def test_gasto_sin_categoria_y_sin_preferencia_si_por_defecto(t):
    _, _, cli = t
    assert _pedir(cli) == {"valor": True, "origen": "POR_DEFECTO"}


def test_categoria_con_si_y_categoria_con_no(t):
    owner, _, cli = t
    si = _categoria(owner, "Super", presupuestable=True)
    no = _categoria(owner, "Inversion", presupuestable=False)
    assert _pedir(cli, categoria=si) == {"valor": True, "origen": "CATEGORIA"}
    assert _pedir(cli, categoria=no) == {"valor": False, "origen": "CATEGORIA"}               # M-S4-03


def test_preferencia_manda_sobre_la_categoria_y_false_explicito_no_pasa_a_si(t):
    owner, _, cli = t
    si = _categoria(owner, "Ocio", presupuestable=True)
    no = _categoria(owner, "Viajes", presupuestable=False)
    ph.insertar_sql(owner, categoria_id=si, presupuestable=False)
    ph.insertar_sql(owner, categoria_id=no, presupuestable=True)
    assert _pedir(cli, categoria=si) == {"valor": False, "origen": "PREFERENCIA"}             # M-S4-01 / M-S4-02
    assert _pedir(cli, categoria=no) == {"valor": True, "origen": "PREFERENCIA"}              # M-S4-01


def test_preferencia_general_false_sin_categoria(t):
    owner, _, cli = t
    ph.insertar_sql(owner, presupuestable=False)
    assert _pedir(cli) == {"valor": False, "origen": "PREFERENCIA"}                           # M-S4-02


def test_ingreso_categoria_y_sin_categoria(t):
    owner, _, cli = t
    nomina = _categoria(owner, "Nomina", ambito="INGRESO")                                    # INGRESO: No en el helper
    assert _pedir(cli, "INGRESO", nomina) == {"valor": False, "origen": "CATEGORIA"}
    assert _pedir(cli, "INGRESO") == {"valor": True, "origen": "POR_DEFECTO"}
    ph.insertar_sql(owner, tipo_hecho_id=_tipo(owner, "INGRESO"), categoria_id=nomina, presupuestable=True)
    assert _pedir(cli, "INGRESO", nomina) == {"valor": True, "origen": "PREFERENCIA"}


def test_categoria_no_elegible_se_rechaza_como_la_propuesta(t):
    owner, _, cli = t
    nomina = _categoria(owner, "Nomina", ambito="INGRESO")
    q = f"?tipo=GASTO&fecha={FECHA.isoformat()}&categoria_id={nomina}&sin_tercero=true"
    r = cli.get(RUTA + q, headers=h.AUTH)
    hoy = cli.get("/v1/registro/propuesta" + q, headers=h.AUTH)
    assert r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    assert (r.status_code, r.json()) == (hoy.status_code, hoy.json())                         # mismo rechazo que la propuesta


def test_las_rutas_de_propuesta_de_hoy_no_cambian(t):
    owner, _, cli = t
    cat = _categoria(owner, "Hogar", presupuestable=True)
    r = ph.propuesta_http(cli, cat)
    assert r.status_code == 200 and r.json()["presupuestable"] is None                       # E1 para quien no pide la lectura nueva
    r2 = cli.get(f"/v1/registro/propuesta?tipo=GASTO&fecha={FECHA.isoformat()}&categoria_id={cat}&sin_tercero=true", headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["campos"]["presupuestable"] is None


# ------------------------------------------------------------------ registro: sin valor por defecto al sellar ni en el replay
def test_el_registro_exige_presupuestable_explicito_y_el_replay_devuelve_lo_sellado(t):
    owner, actor, cli = t
    cuenta = ph.cuenta(owner, actor, nombre="Nomina")
    sin = h.intencion(cuenta)
    del sin["presupuestable"]
    r = cli.post("/v1/intenciones/gasto-pagado", json=sin, headers=h.AUTH)
    assert r.status_code == 422                                                              # M-S4-04: nunca «Si» al sellar
    cuerpo = h.intencion(cuenta, presupuestable=False)
    r1 = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    r2 = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r2.json()["idempotente"] is True
    fila = h.leer(owner, "SELECT presupuestable FROM gapto.hechos_financieros WHERE id = %s", (r1.json()["hecho_id"],))
    assert fila == [(False,)]                                                                # lo sellado, nunca el defecto
