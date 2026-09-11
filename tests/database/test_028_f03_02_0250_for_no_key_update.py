# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_028_f03_02_0250_for_no_key_update.py
# Ruta: tests/database/test_028_f03_02_0250_for_no_key_update.py
# Descripción: Verifica la migration 0250 (FASE 03, frente de concurrencia):
#              las ocho funciones de invariante multi-fila bloquean la fila
#              padre con FOR NO KEY UPDATE en lugar de FOR UPDATE, conservando
#              el resto de sus atributos.
#
#              Motivo (medido con test_027 en Neon y Supabase): FOR UPDATE es
#              incompatible con el FOR KEY SHARE que toman las FK de las hijas,
#              lo que producía un deadlock sistemático entre dos transacciones
#              que insertan hijas del mismo padre. FOR NO KEY UPDATE sigue
#              serializando a los validadores entre sí y con los UPDATE/DELETE
#              del padre, y solo deja de chocar con FOR KEY SHARE.
#
#              La prohibición de FOR UPDATE en el schema gapto se afirma como
#              propiedad: cualquier función futura que la reintroduzca debe
#              justificarse y ajustar este test de forma explícita.
#
#              EQUIVALENCIA ESTRUCTURAL (v0.2.0). entidad_participaciones,
#              inversion_asignaciones_efecto y hecho_movimientos_tesoreria no
#              tienen caso concurrente propio en test_027: se aceptan por
#              equivalencia con topologías ya probadas (C1-C4b). Esa
#              equivalencia se verifica aquí, no se presume: trigger CONSTRAINT
#              AFTER DEFERRABLE INITIALLY DEFERRED sobre INSERT/UPDATE/DELETE,
#              función esperada, un único FOR NO KEY UPDATE sobre el padre
#              situado ANTES del primer agregado, y ningún otro lock de fila.
#
# PRECONDICIÓN: requiere 0250.
# Versión: 0.3.0  -- las huellas aceptan la sucesora de 0260 (fail-closed y
#                   cambio de padre); el modo de lock se sigue afirmando.
#                   v0.2.0: añade la verificación de equivalencia estructural.
# ============================================================

from __future__ import annotations

import psycopg
import pytest

# ({(md5 de prosrc, bytes) aceptados: 0250 y sucesora 0260}, apariciones de FOR NO KEY UPDATE).
HUELLAS_0250 = {
    "fn_check_atribucion_suma": ({("1875c05dfd509221eb2acd2665ec3477", 1556), ("31f04f601350a6dbc7baa3ec8919e980", 2222)}, 1),
    "fn_check_bolsa_prioridad": ({("e0640d1e1af1a043cb5585ae69c4b89b", 1147), ("a583bbd419cb337152617b0c19a1cc42", 1395)}, 1),
    "fn_check_bolsa_prioridad_alcance": ({("7d9abf8d58b812b88d8c58e9968a50fe", 1531), ("7c876f1970c850e791af25226da520b1", 1947)}, 1),
    "fn_check_hecho_mov_tesoreria_suma": ({("693fa7086767b581a6bd45eadc8944c2", 993), ("2b9483c066e3f637f24d396babe27720", 1670)}, 1),
    "fn_check_inversion_asignacion_suma": ({("9a59512f3e0109689af70e79e78159ee", 1281), ("182087c02d004ca2c2f0d38bd00f10ff", 1957)}, 1),
    "fn_check_participacion_suma": ({("d01fd963789d8adf4b29cbb007604414", 2443), ("b76161555c227a8aa19c3ab513aa4687", 3082)}, 1),
    "fn_check_reversion_movimiento": ({("859f7f7e9a5b0b518e6272c410bedf83", 1775), ("00161f7875783230311834ca84e472e2", 2208)}, 1),
    "fn_check_transferencia_estructura": ({("a6c74336f91ddb4239914672cab01c97", 1876), ("e956eb54ec62b7ac7b9bcf11ca3f107e", 2392)}, 2),
}


def test_0250_ninguna_funcion_gapto_usa_for_update(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'gapto' AND p.prosrc ~* 'for\\s+update'
             ORDER BY 1
        """)
        filas = [f[0] for f in cursor.fetchall()]
    assert filas == [], f"funciones del schema gapto que siguen usando FOR UPDATE: {filas}"


@pytest.mark.parametrize("funcion", sorted(HUELLAS_0250))
def test_0250_huella_y_modo_de_lock(db: psycopg.Connection, funcion: str) -> None:
    aceptadas, apariciones = HUELLAS_0250[funcion]
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT md5(p.prosrc), length(p.prosrc),
                   (SELECT count(*) FROM regexp_matches(p.prosrc,
                        'for\\s+no\\s+key\\s+update', 'gi')),
                   p.provolatile, p.prosecdef, pg_catalog.pg_get_userbyid(p.proowner)
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'gapto' AND p.proname = %s
        """, (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"{funcion} no existe"
    md5_real, bytes_reales, no_key, volatilidad, secdef, propietario = fila
    assert (md5_real, bytes_reales) in aceptadas, (
        f"{funcion}: huella {(md5_real, bytes_reales)} no es ninguna de {sorted(aceptadas)}"
    )
    assert no_key == apariciones, f"{funcion}: {no_key} FOR NO KEY UPDATE, se esperaban {apariciones}"
    assert volatilidad == "v", f"{funcion}: debe seguir VOLATILE (instantánea nueva por sentencia)"
    assert secdef is False, f"{funcion}: no debe ser SECURITY DEFINER"
    assert propietario == "gapto_owner", f"{funcion}: propietario {propietario}"


# tabla hija -> (trigger, función, argumentos del trigger)
EQUIVALENCIAS = {
    "entidad_participaciones": (
        "trg_entidad_participaciones__suma_100", "fn_check_participacion_suma",
        ["entidad_id", "entidades"],
    ),
    "inversion_asignaciones_efecto": (
        "trg_inversion_asignaciones_efecto__suma", "fn_check_inversion_asignacion_suma", [],
    ),
    "hecho_movimientos_tesoreria": (
        "trg_hecho_movimientos_tesoreria__suma", "fn_check_hecho_mov_tesoreria_suma", [],
    ),
}


@pytest.mark.parametrize("tabla", sorted(EQUIVALENCIAS))
def test_0250_equivalencia_estructural(db: psycopg.Connection, tabla: str) -> None:
    trigger, funcion, argumentos = EQUIVALENCIAS[tabla]
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname, t.tgconstraint <> 0, t.tgdeferrable, t.tginitdeferred,
                   (t.tgtype & 2) = 0, (t.tgtype & 4) <> 0, (t.tgtype & 16) <> 0,
                   (t.tgtype & 8) <> 0, t.tgenabled, t.tgargs, p.prosrc
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
             WHERE n.nspname = 'gapto' AND c.relname = %s AND t.tgname = %s
        """, (tabla, trigger))
        fila = cursor.fetchone()
    assert fila is not None, f"{tabla}: no existe {trigger}"
    (nombre, es_constraint, diferible, diferido, after, ins, upd, dele,
     habilitado, args, fuente) = fila
    assert nombre == funcion, f"{tabla}: llama a {nombre}, se esperaba {funcion}"
    assert (es_constraint, diferible, diferido, after) == (True, True, True, True), (
        f"{tabla}: debe ser CONSTRAINT TRIGGER AFTER DEFERRABLE INITIALLY DEFERRED"
    )
    assert (ins, upd, dele) == (True, True, True), f"{tabla}: debe cubrir INSERT, UPDATE y DELETE"
    assert habilitado == "O", f"{tabla}: trigger no habilitado ({habilitado})"
    decodificados = [a.decode() for a in bytes(args).split(b"\x00") if a]
    assert decodificados == argumentos, f"{tabla}: argumentos {decodificados} != {argumentos}"

    texto = fuente.lower()
    assert texto.count("for no key update") == 1, f"{funcion}: debe tener un único lock de padre"
    for otro in ("for update", "for share", "for key share", "pg_advisory"):
        assert otro not in texto.replace("for no key update", ""), (
            f"{funcion}: segunda topología de lock ({otro})"
        )
    posicion_lock = texto.index("for no key update")
    agregados = [texto.index(a) for a in ("sum(", "count(") if a in texto]
    assert agregados, f"{funcion}: no se encuentra el agregado"
    assert posicion_lock < min(agregados), f"{funcion}: el lock del padre no precede al agregado"
