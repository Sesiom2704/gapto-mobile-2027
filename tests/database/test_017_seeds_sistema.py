# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_017_seeds_sistema.py
# Ruta: tests/database/test_017_seeds_sistema.py
# Descripción: Verifica los seeds de sistema de F03-01: tipos_hecho (7
#              valores, arquetipo funcional del hecho -- D-078) y
#              metricas_definicion (3 métricas atómicas de ahorro --
#              D-079). Confirma explícitamente que los candidatos
#              descartados (SALDO_APERTURA, AJUSTE_SALDO, AHORRO_TOTAL_MES,
#              TASA_AHORRO) NO están presentes -- su ausencia es una
#              decisión documentada, no un olvido.
# Versión: 0.1.0
# Versión: 0.2.0  -- F03-06 / D-201 / 0350. El conjunto de tipos_hecho era
#                   igualdad exacta con los 7 códigos de 0150 y 0350 siembra
#                   CONDONACION. Se aceptan EXACTAMENTE dos estados nombrados
#                   (D-073 refinado por D-187 / Working Method §12C.12, mismo
#                   patrón que test_002 con 0340): seed de 0150 (7 códigos,
#                   heads 0150..0340) o seed de 0150 + CONDONACION (8 códigos,
#                   head 0350). Cualquier otro conjunto sigue siendo drift. La
#                   regla UUIDv5 se aplica a TODAS las filas, CONDONACION
#                   incluida, y no se debilita.
# ============================================================

from __future__ import annotations

import psycopg

TIPOS_HECHO_ESPERADOS = {
    "GASTO", "INGRESO", "TRANSFERENCIA", "COMPRA_FINANCIADA",
    "REEMBOLSO", "APORTACION_INVERSION", "GENERACION_DERECHO_OBLIGACION",
}
TIPOS_HECHO_DESCARTADOS = {"SALDO_APERTURA", "AJUSTE_SALDO"}

# Estados autorizados de tipos_hecho por head. Conjunto EXPLICITO y FINITO.
TIPOS_HECHO_POR_HEAD = {
    "0150..0340": TIPOS_HECHO_ESPERADOS,
    "0350": TIPOS_HECHO_ESPERADOS | {"CONDONACION"},
}

METRICAS_ESPERADAS = {
    "APORTACION_INVERSION_NETA", "TRANSFERENCIA_AHORRO_NETA", "AHORRO_NETO_PYL",
}
METRICAS_DESCARTADAS = {"AHORRO_TOTAL_MES", "TASA_AHORRO"}


def test_tipos_hecho_exactly_7_expected_codes(db: psycopg.Connection) -> None:
    """7 códigos de 0150 (hasta 0340) o esos 7 + CONDONACION (0350); nada más."""
    with db.cursor() as cursor:
        cursor.execute("SELECT codigo FROM gapto.tipos_hecho")
        codigos = [r[0] for r in cursor.fetchall()]
    found = set(codigos)
    assert len(codigos) == len(found)
    assert found in TIPOS_HECHO_POR_HEAD.values(), f"tipos_hecho fuera de los estados autorizados: {sorted(found)}"


def test_tipos_hecho_discarded_candidates_absent(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT codigo FROM gapto.tipos_hecho WHERE codigo = ANY(%s)",
            (sorted(TIPOS_HECHO_DESCARTADOS),),
        )
        found = {r[0] for r in cursor.fetchall()}
    assert found == set(), (
        f"Codigos explicitamente descartados presentes en tipos_hecho: {found}"
    )


def test_tipos_hecho_all_enabled(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM gapto.tipos_hecho WHERE NOT enabled")
        (count,) = cursor.fetchone()
    assert count == 0


def test_tipos_hecho_ids_are_deterministic_uuidv5(db: psycopg.Connection) -> None:
    """Los UUID de seed son UUIDv5 deterministas sobre
    'gapto2027:tipos_hecho:<codigo>' -- reproducibles, no gen_random_uuid()."""
    import uuid
    with db.cursor() as cursor:
        cursor.execute("SELECT id, codigo FROM gapto.tipos_hecho")
        rows = cursor.fetchall()
    for row_id, codigo in rows:
        expected = uuid.uuid5(uuid.NAMESPACE_URL, f"gapto2027:tipos_hecho:{codigo}")
        assert str(row_id) == str(expected), f"{codigo}: UUID no coincide con el determinista esperado"


def test_metricas_definicion_exactly_3_expected_codes(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT codigo FROM gapto.metricas_definicion")
        found = {r[0] for r in cursor.fetchall()}
    assert found == METRICAS_ESPERADAS


def test_metricas_definicion_discarded_candidates_absent(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT codigo FROM gapto.metricas_definicion WHERE codigo = ANY(%s)",
            (sorted(METRICAS_DESCARTADAS),),
        )
        found = {r[0] for r in cursor.fetchall()}
    assert found == set(), (
        f"Metricas explicitamente descartadas (agregado derivado o formula "
        f"sin cerrar) presentes en metricas_definicion: {found}"
    )


def test_metricas_definicion_all_numeric_moneda(db: psycopg.Connection) -> None:
    """Las 3 metricas de ahorro son importes monetarios atomicos."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT codigo, tipo_valor, unidad FROM gapto.metricas_definicion
             WHERE codigo = ANY(%s)
        """, (sorted(METRICAS_ESPERADAS),))
        rows = cursor.fetchall()
    for codigo, tipo_valor, unidad in rows:
        assert tipo_valor == "NUMERIC", f"{codigo}: tipo_valor esperado=NUMERIC"
        assert unidad == "MONEDA", f"{codigo}: unidad esperada=MONEDA"


def test_metricas_definicion_ids_are_deterministic_uuidv5(db: psycopg.Connection) -> None:
    import uuid
    with db.cursor() as cursor:
        cursor.execute("SELECT id, codigo FROM gapto.metricas_definicion")
        rows = cursor.fetchall()
    for row_id, codigo in rows:
        expected = uuid.uuid5(uuid.NAMESPACE_URL, f"gapto2027:metricas_definicion:{codigo}")
        assert str(row_id) == str(expected), f"{codigo}: UUID no coincide con el determinista esperado"
