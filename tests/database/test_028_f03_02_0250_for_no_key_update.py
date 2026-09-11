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
# PRECONDICIÓN: requiere 0250.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

# (md5 de prosrc, bytes, apariciones de FOR NO KEY UPDATE) tras 0250.
HUELLAS_0250 = {
    "fn_check_atribucion_suma": ("1875c05dfd509221eb2acd2665ec3477", 1556, 1),
    "fn_check_bolsa_prioridad": ("e0640d1e1af1a043cb5585ae69c4b89b", 1147, 1),
    "fn_check_bolsa_prioridad_alcance": ("7d9abf8d58b812b88d8c58e9968a50fe", 1531, 1),
    "fn_check_hecho_mov_tesoreria_suma": ("693fa7086767b581a6bd45eadc8944c2", 993, 1),
    "fn_check_inversion_asignacion_suma": ("9a59512f3e0109689af70e79e78159ee", 1281, 1),
    "fn_check_participacion_suma": ("d01fd963789d8adf4b29cbb007604414", 2443, 1),
    "fn_check_reversion_movimiento": ("859f7f7e9a5b0b518e6272c410bedf83", 1775, 1),
    "fn_check_transferencia_estructura": ("a6c74336f91ddb4239914672cab01c97", 1876, 2),
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
    md5_esperado, bytes_esperados, apariciones = HUELLAS_0250[funcion]
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
    assert (md5_real, bytes_reales) == (md5_esperado, bytes_esperados), (
        f"{funcion}: huella {(md5_real, bytes_reales)} != {(md5_esperado, bytes_esperados)}"
    )
    assert no_key == apariciones, f"{funcion}: {no_key} FOR NO KEY UPDATE, se esperaban {apariciones}"
    assert volatilidad == "v", f"{funcion}: debe seguir VOLATILE (instantánea nueva por sentencia)"
    assert secdef is False, f"{funcion}: no debe ser SECURITY DEFINER"
    assert propietario == "gapto_owner", f"{funcion}: propietario {propietario}"
