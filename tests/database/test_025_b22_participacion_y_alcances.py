# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_025_b22_participacion_y_alcances.py
# Ruta: tests/database/test_025_b22_participacion_y_alcances.py
# Descripción: Verifica F03-01-B22 (migration 0240), que cierra D-091:
#
#              1. La participación debe sumar EXACTAMENTE 100 en todo instante
#                 cubierto, no solo "no pasarse de 100". Como ahora sí puede
#                 violarse borrando, los dos triggers cubren DELETE.
#              2. El empate de prioridad entre líneas BOLSA se vigila también
#                 desde `presupuesto_linea_alcances`, que podía crearlo sin que
#                 nada se disparara.
#
#              Los casos límite deliberados también se comprueban: cero filas y
#              padre inexistente no se comprueban, y el reparto construido en
#              varios pasos dentro de una transacción sigue siendo válido porque
#              los triggers son DEFERRABLE INITIALLY DEFERRED (D-081).
#
#              Huellas: el test histórico valida su baseline (0240) sin
#              impedir la sucesora conocida. Se acepta la huella de 0240 o la
#              de 0250 (F03-02, FOR UPDATE -> FOR NO KEY UPDATE), y nada más:
#              cualquier otra huella sigue siendo drift.
#
# PRECONDICIÓN: requiere 0190 (B16).
# Versión: 0.1.5  -- acepta también exactamente la sucesora de 0285: huella de
#                   fn_check_bolsa_prioridad_alcance y recuento de triggers (48
#                   no internos, 31 constraint, 7 guards).
#                   v0.1.4: acepta también exactamente la sucesora de 0280 (40 no
#                   internos, 30 constraint, 7 guards).
#                   v0.1.3: el recuento de triggers acepta exactamente la sucesora de
#                   0270 (39 no internos, 23 constraint, 7 guards) además del
#                   baseline B22 (Working Method 12C.5).
#                   v0.1.2: acepta las huellas sucesoras de 0250 y 0260.
# ============================================================

from __future__ import annotations

import psycopg
import pytest

HUELLAS = {
    "fn_check_participacion_suma": {
        ("c909c04f4e0131a32c6552efe601d370", 2436),  # 0240 (baseline)
        ("d01fd963789d8adf4b29cbb007604414", 2443),  # 0250 (sucesora)
        ("b76161555c227a8aa19c3ab513aa4687", 3082),  # 0260 (sucesora)
    },
    "fn_check_bolsa_prioridad_alcance": {
        ("0eb39ed53b28a3c4657e032f3aaaa037", 1524),  # 0240 (baseline)
        ("7d9abf8d58b812b88d8c58e9968a50fe", 1531),  # 0250 (sucesora)
        ("7c876f1970c850e791af25226da520b1", 1947),  # 0260 (sucesora)
        ("d1d83d6e38a15190244a26be50d90ad4", 3793),  # 0285 (sucesora)
    },
}

OWNER = "b22a0000-0000-4000-8000-000000000001"
CUENTA = "b22c0000-0000-4000-8000-000000000002"
ACTOR_1 = "b22e0000-0000-4000-8000-000000000003"
ACTOR_2 = "b22e0000-0000-4000-8000-000000000004"
TERCERO = "b22d0000-0000-4000-8000-000000000009"


def _scalar(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        fila = cursor.fetchone()
    return fila[0] if fila else None


@pytest.mark.parametrize("funcion", sorted(HUELLAS))
def test_b22_huella_de_funcion(db: psycopg.Connection, funcion: str) -> None:
    """Paridad byte a byte entre proveedores y contra la migration.

    Los cuerpos van sin comentarios inline a propósito: cualquier comentario
    dentro de prosrc es una fuente de divergencia silenciosa entre entornos.
    """
    aceptadas = HUELLAS[funcion]
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT md5(p.prosrc), length(p.prosrc)
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname='gapto' AND p.proname = %s
        """, (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"{funcion} no existe"
    assert tuple(fila) in aceptadas, (
        f"{funcion}: huella {tuple(fila)} no es ninguna de las aceptadas {sorted(aceptadas)}"
    )


@pytest.mark.parametrize("trigger,tabla", [
    ("trg_cuenta_participaciones__suma_100", "cuenta_participaciones"),
    ("trg_entidad_participaciones__suma_100", "entidad_participaciones"),
])
def test_b22_participacion_cubre_delete(db: psycopg.Connection, trigger: str, tabla: str) -> None:
    """Con igualdad exacta, borrar SÍ puede romper la invariante."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT (t.tgtype & 4) <> 0, (t.tgtype & 8) <> 0, (t.tgtype & 16) <> 0,
                   t.tgconstraint <> 0, t.tgdeferrable, t.tginitdeferred, t.tgenabled
              FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = ('gapto.' || %s)::regclass AND t.tgname = %s
        """, (tabla, trigger))
        fila = cursor.fetchone()
    assert fila is not None, f"{trigger} no existe"
    insert, delete, update, es_constraint, diferible, diferido, habilitado = fila
    assert (insert, delete, update) == (True, True, True)
    assert es_constraint and diferible and diferido, (
        "debe seguir siendo CONSTRAINT TRIGGER DEFERRABLE INITIALLY DEFERRED (D-081)"
    )
    assert habilitado == "O"


def test_b22_trigger_de_alcances_existe_y_no_cubre_delete(db: psycopg.Connection) -> None:
    """Retirar un alcance solo puede reducir intersecciones, nunca crear empate.

    Cubrir DELETE aquí sería código muerto, y la disciplina de la auditoría de
    D-091 es cubrir el evento que puede romper la invariante, no todos por
    simetría.
    """
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT (t.tgtype & 4) <> 0, (t.tgtype & 8) <> 0, (t.tgtype & 16) <> 0,
                   t.tgconstraint <> 0, t.tginitdeferred
              FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = 'gapto.presupuesto_linea_alcances'::regclass
               AND t.tgname = 'trg_presupuesto_linea_alcances__bolsa_prioridad'
        """)
        fila = cursor.fetchone()
    assert fila is not None, "el hueco de alcances debe estar cubierto"
    insert, delete, update, es_constraint, diferido = fila
    assert (insert, update) == (True, True)
    assert delete is False, "DELETE no puede crear un empate: cubrirlo sería código muerto"
    assert es_constraint and diferido


def test_b22_recuento_de_triggers(db: psycopg.Connection) -> None:
    """Baseline B22: 34 triggers no internos (19 constraint, 7 guards, 8
    ordinarios). Sucesora 0270: 39 (23 constraint, 7 guards, 9 ordinarios).
    Sucesora 0280: 40 (30 constraint, 7 guards). Sucesora 0285: 48 (31
    constraint, 7 guards): los triggers de 0285 no llevan 'guard' en el nombre
    del trigger, solo en el de su función, así que el recuento de guards
    append-only de B14 no varía."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT count(*),
                   count(*) FILTER (WHERE t.tgconstraint <> 0),
                   count(*) FILTER (WHERE t.tgname LIKE '%%guard%%')
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname='gapto' AND NOT t.tgisinternal
        """)
        total, constraint, guards = cursor.fetchone()
    assert (total, constraint, guards) in ((34, 19, 7), (39, 23, 7), (40, 30, 7), (48, 31, 7))


# ------------------------------------------------------------
# Comportamiento
# ------------------------------------------------------------

def _montar(cursor) -> None:
    cursor.execute("SET LOCAL ROLE gapto_owner")
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    cursor.execute(
        "INSERT INTO gapto.usuarios (id,email,nombre) VALUES (%s,'b22@example.com','B22') "
        "ON CONFLICT (id) DO NOTHING",
        (OWNER,),
    )
    cursor.execute(
        "INSERT INTO gapto.cuentas (id,owner_user_id,nombre,tipo,naturaleza,moneda,"
        "computa_liquidez,computa_patrimonio,permite_negativo) "
        "VALUES (%s,%s,'Cuenta B22','CORRIENTE','ACTIVO','EUR',true,true,false) "
        "ON CONFLICT (id) DO NOTHING",
        (CUENTA, OWNER),
    )
    cursor.execute(
        "INSERT INTO gapto.terceros (id,owner_user_id,nombre,naturaleza) "
        "VALUES (%s,%s,'Tercero B22','PERSONA') ON CONFLICT (id) DO NOTHING",
        (TERCERO, OWNER),
    )
    cursor.execute(
        "INSERT INTO gapto.actores_financieros (id,owner_user_id,tercero_id) "
        "VALUES (%s,%s,NULL), (%s,%s,%s) ON CONFLICT (id) DO NOTHING",
        (ACTOR_1, OWNER, ACTOR_2, OWNER, TERCERO),
    )


def test_b22_reparto_completo_en_varios_pasos_es_valido(db: psycopg.Connection) -> None:
    """60 + 40 en la misma transacción: válido gracias al diferimiento."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) VALUES (%s,%s,60,'2026-01-01')",
                (CUENTA, ACTOR_1),
            )
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) VALUES (%s,%s,40,'2026-01-01')",
                (CUENTA, ACTOR_2),
            )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


def test_b22_reparto_incompleto_se_rechaza(db: psycopg.Connection) -> None:
    """60 solo: la propiedad no está completa y debe rechazarse."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) VALUES (%s,%s,60,'2026-01-01')",
                (CUENTA, ACTOR_1),
            )
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


def test_b22_borrado_parcial_se_rechaza(db: psycopg.Connection) -> None:
    """La razón por la que estos triggers pasan a cubrir DELETE."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) VALUES (%s,%s,60,'2026-01-01'), "
                "(%s,%s,40,'2026-01-01')",
                (CUENTA, ACTOR_1, CUENTA, ACTOR_2),
            )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute(
                    "DELETE FROM gapto.cuenta_participaciones WHERE actor_id = %s",
                    (ACTOR_2,),
                )
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


def test_b22_hueco_temporal_se_rechaza(db: psycopg.Connection) -> None:
    """Un periodo sin cobertura entre dos vigencias también es reparto inválido.

    Es lo que aporta muestrear `vigente_hasta + 1` además de `vigente_desde`.
    """
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde,vigente_hasta) "
                "VALUES (%s,%s,100,'2026-01-01','2026-06-30')",
                (CUENTA, ACTOR_1),
            )
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) "
                "VALUES (%s,%s,100,'2026-08-01')",
                (CUENTA, ACTOR_2),
            )
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


def test_b22_borrar_el_padre_no_falla(db: psycopg.Connection) -> None:
    """Caso límite deliberado: sin padre no hay nada que exigir."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(cuenta_id,actor_id,porcentaje,vigente_desde) VALUES (%s,%s,100,'2026-01-01')",
                (CUENTA, ACTOR_1),
            )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("DELETE FROM gapto.cuenta_participaciones WHERE cuenta_id = %s", (CUENTA,))
            cursor.execute("DELETE FROM gapto.cuentas WHERE id = %s", (CUENTA,))
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")
