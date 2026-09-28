# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_157_f05_01_bolsa_intensional.py
# Ruta: tests/api/test_157_f05_01_bolsa_intensional.py
# Descripcion: Escenarios BOLSA de §22.5 frente a la gestion del catalogo
#   (F05-01, S5; D-198; F05-D010 Q6/AJ-05).
#   *** ORACULO EXCLUSIVO DE TEST, NO PRODUCTIVO ***: `_lineas_que_capturan`
#   evalua la semantica intensional de D-198 (jerarquia vigente en el momento
#   de evaluar) con una consulta recursiva. NO es un read-model ni el matching
#   efecto -> alcance, que pertenece a F08 (R03).
#   Escenarios:
#     1. alta bajo un ancestro cubierto por un presupuesto NO BORRADOR: se
#        admite y el descendiente queda capturado prospectivamente;
#     2. alta fuera del subarbol: sin falso positivo;
#     3. dos BOLSAS solapables con prioridades distintas + descendiente nuevo:
#        el ganador es inequivoco.
#   En todos, la operacion de catalogo no reescribe hechos, efectos,
#   presupuestos, lineas ni alcances ya materializados.
#   Base local desechable 0001..0340 (estos tests confirman filas).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _lineas_que_capturan(owner, categoria_id) -> list[tuple]:
    """ORACULO DE TEST. Lineas BOLSA cuyo alcance es la categoria o un
    ancestro suyo con incluir_descendientes, segun la jerarquia VIGENTE.
    Devuelve (linea_id, prioridad) ordenado por prioridad."""
    return h.leer(owner, """
        WITH RECURSIVE anc(id, parent_id, nivel) AS (
            SELECT id, parent_id, 0 FROM gapto.categorias_financieras WHERE id = %s
            UNION ALL
            SELECT c.id, c.parent_id, a.nivel + 1 FROM anc a
              JOIN gapto.categorias_financieras c ON c.id = a.parent_id
        )
        SELECT DISTINCT l.id, l.prioridad_consumo
          FROM gapto.presupuesto_linea_alcances al
          JOIN gapto.presupuesto_lineas l ON l.id = al.presupuesto_linea_id
          JOIN anc ON anc.id = al.categoria_id
         WHERE l.tipo_linea = 'BOLSA' AND (anc.nivel = 0 OR al.incluir_descendientes)
         ORDER BY l.prioridad_consumo NULLS LAST, l.id
    """, (categoria_id,))


def _huella(owner) -> tuple:
    """Todo lo materializado que el catalogo NO puede reescribir."""
    return tuple(h.leer(owner, q)[0][0] for q in (
        "SELECT md5(coalesce(string_agg(row_to_json(e)::text, '|' ORDER BY e.id), '')) FROM gapto.hecho_efectos e",
        "SELECT md5(coalesce(string_agg(row_to_json(x)::text, '|' ORDER BY x.id), '')) FROM gapto.hechos_financieros x",
        "SELECT md5(coalesce(string_agg(row_to_json(p)::text, '|' ORDER BY p.id), '')) FROM gapto.presupuestos p",
        "SELECT md5(coalesce(string_agg(row_to_json(l)::text, '|' ORDER BY l.id), '')) FROM gapto.presupuesto_lineas l",
        "SELECT md5(coalesce(string_agg(row_to_json(a)::text, '|' ORDER BY a.id), '')) FROM gapto.presupuesto_linea_alcances a",
    ))


def _gasto(cli, cuenta, categoria):
    cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(categoria)})
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200


def test_1_alta_bajo_ancestro_congelado_se_captura_prospectivamente(ctx):
    owner, actor, cli = ctx
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    alim, _ = fh.alta(cli, "Alimentacion")
    fh.crear_presupuesto(owner, [(1, [(alim, True)])], estado_final="ACTIVO")
    _gasto(cli, cuenta, alim)
    antes = _huella(owner)
    nueva, r = fh.alta(cli, "Panaderia", parent_id=alim)
    assert r.status_code == 200, r.text  # D-198: congelar el presupuesto no congela el catalogo
    assert _huella(owner) == antes
    assert len(_lineas_que_capturan(owner, nueva)) == 1


def test_2_alta_fuera_del_subarbol_sin_falso_positivo(ctx):
    owner, _, cli = ctx
    alim, _ = fh.alta(cli, "Alimentacion")
    fh.crear_presupuesto(owner, [(1, [(alim, True)])], estado_final="ACTIVO")
    antes = _huella(owner)
    fuera, r = fh.alta(cli, "Transporte")
    assert r.status_code == 200
    assert _huella(owner) == antes
    assert _lineas_que_capturan(owner, fuera) == []


def test_3_bolsas_solapables_prioridad_inequivoca(ctx):
    owner, _, cli = ctx
    ocio, _ = fh.alta(cli, "Ocio")
    viajes, _ = fh.alta(cli, "Viajes", parent_id=ocio)
    fh.crear_presupuesto(owner, [(1, [(ocio, True)]), (2, [(viajes, True)])], estado_final="ACTIVO")
    antes = _huella(owner)
    hoteles, r = fh.alta(cli, "Hoteles", parent_id=viajes)
    assert r.status_code == 200
    assert _huella(owner) == antes
    capturan = _lineas_que_capturan(owner, hoteles)
    assert [p for _, p in capturan] == [1, 2]
    prioridades = [p for _, p in capturan]
    assert len(set(prioridades)) == len(prioridades) and None not in prioridades  # ganador unico: prioridad 1


def test_desactivar_y_renombrar_no_reescriben_historia(ctx):
    owner, actor, cli = ctx
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    cat, _ = fh.alta(cli, "Libros")
    _gasto(cli, cuenta, cat)
    antes = _huella(owner)
    assert fh.cmd(cli, f"{fh.BASE}/{cat}/renombrar", {"nombre": "Libros y revistas", "row_version": 1}).status_code == 200
    assert fh.cmd(cli, f"{fh.BASE}/{cat}/desactivar", {"modo": "RAMA", "row_version": 2}).status_code == 200
    assert _huella(owner) == antes
    # La lectura historica sigue mostrandola (D-198).
    arbol = cli.get("/v1/categorias", headers=h.AUTH).json()["categorias"]
    assert any(c["id"] == str(cat) and c["enabled"] is False for c in arbol)
