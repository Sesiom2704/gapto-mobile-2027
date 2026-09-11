# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_013_b12_invariantes_parte1.py
# Ruta: tests/database/test_013_b12_invariantes_parte1.py
# Descripción: Verifica F03-01-B12 parte 1: 5 funciones estructurales
#              (prevención de ciclos genérica, GARANTIZADA_POR,
#              tercero_personas↔naturaleza, actor self único, subtipo
#              único de entidad) y 17 triggers: 8 inmediatos (6 ciclos +
#              GARANTIZADA_POR + tercero_personas) y 9 diferidos
#              (actor self único + 8 subtipo_unico, uno por entidades
#              y cada uno de sus 7 subtipos).
# Versión: 0.1.1  -- acepta exactamente la sucesora de 0280 (F03-02): la
#                   prevención de ciclos BEFORE inmediata se sustituye por
#                   constraint triggers diferidos (D-123) y por la cadena de
#                   sustitución; el ciclo real se rechaza igualmente, ahora al
#                   validar las restricciones diferidas (Working Method 12C.5).
# ============================================================

from __future__ import annotations

import psycopg
import pytest

PARTE1_FUNCTIONS = {
    "fn_prevent_self_referencing_cycle",
    "fn_check_garantizada_por",
    "fn_check_tercero_persona_naturaleza",
    "fn_check_actor_self_unico",
    "fn_check_entidad_subtipo_unico",
}

CYCLE_TRIGGERS = {
    "trg_regiones__no_ciclo", "trg_clasificaciones_tercero__no_ciclo",
    "trg_categorias_financieras__no_ciclo", "trg_inversiones__no_ciclo",
    "trg_presupuestos__no_ciclo", "trg_cierres_mensuales__no_ciclo",
}
# Sucesora conocida 0280.
PARTE1_FUNCTIONS_0280 = (PARTE1_FUNCTIONS - {"fn_prevent_self_referencing_cycle"}) | {
    "fn_check_jerarquia_aciclica", "fn_check_cadena_sustitucion",
}
CYCLE_TRIGGERS_0280 = {
    "trg_regiones__aciclica", "trg_clasificaciones_tercero__aciclica",
    "trg_categorias_financieras__aciclica", "trg_inversiones__aciclica",
    "trg_presupuestos__cadena_sustitucion", "trg_cierres_mensuales__cadena_sustitucion",
}
IMMEDIATE_TRIGGERS = CYCLE_TRIGGERS | {
    "trg_entidad_relaciones__garantizada_por",
    "trg_tercero_personas__naturaleza",
}
DEFERRED_TRIGGERS_PARTE1 = {
    "trg_actores_financieros__self_unico",
    "trg_entidades__subtipo_unico", "trg_propiedades__subtipo_unico",
    "trg_contratos__subtipo_unico", "trg_servicios__subtipo_unico",
    "trg_financiaciones__subtipo_unico", "trg_inversiones__subtipo_unico",
    "trg_derechos_obligaciones__subtipo_unico", "trg_contextos__subtipo_unico",
}


def test_b12p1_five_functions_exist(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='gapto' AND p.proname = ANY(%s)
        """, (sorted(PARTE1_FUNCTIONS | PARTE1_FUNCTIONS_0280),))
        found = {r[0] for r in cursor.fetchall()}
    assert found in (PARTE1_FUNCTIONS, PARTE1_FUNCTIONS_0280)


def test_b12p1_eight_immediate_triggers(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname = ANY(%s) AND NOT t.tgdeferrable
        """, (sorted(IMMEDIATE_TRIGGERS),))
        found = {r[0] for r in cursor.fetchall()}
        cursor.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
             WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
               AND t.tgname = ANY(%s) AND t.tgdeferrable AND t.tginitdeferred
        """, (sorted(CYCLE_TRIGGERS_0280),))
        diferidos_0280 = {r[0] for r in cursor.fetchall()}
    assert (found, diferidos_0280) in (
        (IMMEDIATE_TRIGGERS, set()),
        (IMMEDIATE_TRIGGERS - CYCLE_TRIGGERS, CYCLE_TRIGGERS_0280),
    )


def test_b12p1_nine_deferred_triggers(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT t.tgname FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
               AND t.tgname = ANY(%s) AND t.tgdeferrable AND t.tginitdeferred
        """, (sorted(DEFERRED_TRIGGERS_PARTE1),))
        found = {r[0] for r in cursor.fetchall()}
    assert found == DEFERRED_TRIGGERS_PARTE1, (
        "Los 9 triggers de parte 1 (actor self unico + subtipo unico) "
        "deben ser CONSTRAINT TRIGGER DEFERRABLE INITIALLY DEFERRED: "
        "necesitan que la fila relacionada (subtipo, u otro actor) pueda "
        "crearse en un paso posterior de la misma transaccion."
    )


def test_b12p1_cycle_prevention_blocks_real_cycle(db: psycopg.Connection) -> None:
    """Prueba funcional, no solo de catalogo: intentar crear un ciclo
    real en regiones debe fallar con la excepcion del trigger."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET ROLE gapto_owner")
            cursor.execute(
                "INSERT INTO gapto.paises (id, iso2, iso3, nombre) "
                "VALUES ('99999999-1111-1111-1111-111111111111','ZZ','ZZZ','Pais test B12P1')"
            )
            cursor.execute(
                "INSERT INTO gapto.regiones (id, pais_id, nombre) VALUES "
                "('99999999-2222-2222-2222-222222222222',"
                "'99999999-1111-1111-1111-111111111111','RegionA test B12P1')"
            )
            cursor.execute(
                "INSERT INTO gapto.regiones (id, pais_id, parent_region_id, nombre) "
                "VALUES ('99999999-3333-3333-3333-333333333333',"
                "'99999999-1111-1111-1111-111111111111',"
                "'99999999-2222-2222-2222-222222222222','RegionB test B12P1')"
            )
            with pytest.raises(psycopg.errors.RaiseException, match="(?i)ciclo"):
                cursor.execute(
                    "UPDATE gapto.regiones SET parent_region_id = "
                    "'99999999-3333-3333-3333-333333333333' "
                    "WHERE id = '99999999-2222-2222-2222-222222222222'"
                )
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
