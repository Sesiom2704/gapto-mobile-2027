# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_030_f03_02_0265_anclaje_recurrencia.py
# Ruta: tests/database/test_030_f03_02_0265_anclaje_recurrencia.py
# Descripción: Verifica la migration 0265 (D-126 / F02-E01-R2): separación
#              entre cadencia (periodicidad + intervalo) y anclaje de la
#              cadena de ocurrencias (CALENDARIO / RODANTE) en
#              regla_versiones.
#
#              Alcance: SOLO el contrato físico de F03. El algoritmo de
#              generación (CALENDARIO no se desplaza, RODANTE se encadena
#              desde la fecha real, omisión, versionado, transición entre
#              segmentos) es del motor de F04 y se verificará allí con los
#              vectores documentados en D-126. Este test no finge haberlo
#              probado.
#
#              Comprueba:
#              - columna varchar(30) nullable, sin DEFAULT;
#              - solo tokens CALENDARIO / RODANTE;
#              - recurrente <=> anclaje definido (en ambos sentidos);
#              - RODANTE solo con fecha_modo=ANCLA (VENTANA y
#                CALENDARIO_ENTIDAD rechazados) y nunca con
#                importe_modo=CALENDARIO_ENTIDAD;
#              - CALENDARIO conserva todas las combinaciones previas;
#              - las constraints previas de regla_versiones siguen actuando;
#                se documenta con xfail estricto un defecto previo de 0030
#                (VENTANA con días NULL aceptada) que no forma parte de D-126;
#              - FORCE RLS sigue activo y gapto_runtime puede escribir la
#                columna.
#
# PRECONDICIÓN: requiere 0265.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

OWNER = "c0265000-0000-4000-8000-000000000001"
REGLA = "c0265000-0000-4000-8000-000000000002"
CHECKS_0265 = {
    "ck_regla_versiones__anclaje_recurrencia",
    "ck_regla_versiones__anclaje_periodicidad",
    "ck_regla_versiones__rodante_fecha_modo",
    "ck_regla_versiones__rodante_importe_modo",
}


def _montar(cursor) -> None:
    cursor.execute("SET LOCAL ROLE gapto_owner")
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    cursor.execute("INSERT INTO gapto.usuarios (id, email, nombre) "
                   "VALUES (%s, 'c0265@example.com', 'C0265')", (OWNER,))
    cursor.execute("INSERT INTO gapto.reglas_financieras (id, owner_user_id, nombre) "
                   "VALUES (%s, %s, 'Bono gimnasio')", (REGLA, OWNER))


def _version(cursor, *, periodicidad, anclaje, fecha_modo="ANCLA", importe_modo="MANUAL",
             dia_desde=None, dia_hasta=None, desde="2026-01-10", hasta=None) -> None:
    cursor.execute(
        "INSERT INTO gapto.regla_versiones (regla_id, vigente_desde, vigente_hasta, "
        "tipo_hecho_id, flujo_tesoreria_esperado, moneda, periodicidad, intervalo, "
        "anclaje_recurrencia, fecha_modo, dia_desde, dia_hasta, importe_modo, presupuestable) "
        "SELECT %s, %s, %s, id, 'SIN_MOVIMIENTO', 'EUR', %s, 5, %s, %s, %s, %s, %s, true "
        "FROM gapto.tipos_hecho WHERE codigo = 'GASTO'",
        (REGLA, desde, hasta, periodicidad, anclaje, fecha_modo, dia_desde, dia_hasta,
         importe_modo),
    )


def _intentar(db: psycopg.Connection, **kwargs):
    """Ejecuta el alta dentro de una transacción que se revierte siempre."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            _version(cursor, **kwargs)
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

def test_0265_columna_nullable_sin_default(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,
                   pg_catalog.pg_get_expr(d.adbin, d.adrelid)
              FROM pg_catalog.pg_attribute a
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = 'gapto.regla_versiones'::regclass
               AND a.attname = 'anclaje_recurrencia' AND NOT a.attisdropped
        """)
        assert cursor.fetchone() == ("character varying(30)", False, None)


def test_0265_checks_materializados_y_validados(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.conname FROM pg_catalog.pg_constraint c
             WHERE c.conrelid = 'gapto.regla_versiones'::regclass
               AND c.contype = 'c' AND c.convalidated AND c.conname = ANY(%s)
        """, (sorted(CHECKS_0265),))
        assert {r[0] for r in cursor.fetchall()} == CHECKS_0265


def test_0265_force_rls_y_privilegios_runtime(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT c.relrowsecurity, c.relforcerowsecurity,
                   has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'SELECT'),
                   has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'INSERT'),
                   has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'UPDATE')
              FROM pg_catalog.pg_class c WHERE c.oid = 'gapto.regla_versiones'::regclass
        """)
        assert cursor.fetchone() == (True, True, True, True, True)


# ------------------------------------------------------------
# Integridad local
# ------------------------------------------------------------

def test_0265_token_no_aprobado_se_rechaza(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="anclaje_recurrencia"):
        _intentar(db, periodicidad="SEMANAL", anclaje="CONSUMO")


def test_0265_recurrente_sin_anclaje_se_rechaza(db: psycopg.Connection) -> None:
    """Sin DEFAULT: la omisión del writer no se convierte en CALENDARIO."""
    with pytest.raises(psycopg.errors.CheckViolation, match="anclaje_periodicidad"):
        _intentar(db, periodicidad="SEMANAL", anclaje=None)


def test_0265_no_recurrente_con_anclaje_se_rechaza(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="anclaje_periodicidad"):
        _intentar(db, periodicidad=None, anclaje="RODANTE")


def test_0265_no_recurrente_sin_anclaje_es_valida(db: psycopg.Connection) -> None:
    _intentar(db, periodicidad=None, anclaje=None)


@pytest.mark.parametrize("fecha_modo,dias", [
    ("ANCLA", (None, None)),
    ("VENTANA", (1, 5)),
    ("CALENDARIO_ENTIDAD", (None, None)),
])
def test_0265_calendario_conserva_todas_las_combinaciones(db: psycopg.Connection,
                                                           fecha_modo: str, dias) -> None:
    _intentar(db, periodicidad="MENSUAL", anclaje="CALENDARIO", fecha_modo=fecha_modo,
              dia_desde=dias[0], dia_hasta=dias[1])


def test_0265_calendario_con_importe_calendario_entidad_es_valido(db: psycopg.Connection) -> None:
    _intentar(db, periodicidad="MENSUAL", anclaje="CALENDARIO", importe_modo="CALENDARIO_ENTIDAD")


def test_0265_rodante_con_ancla_es_valido(db: psycopg.Connection) -> None:
    """El caso del gimnasio: cada 5 semanas desde la ocurrencia anterior."""
    _intentar(db, periodicidad="SEMANAL", anclaje="RODANTE", fecha_modo="ANCLA")


def test_0265_rodante_con_ventana_se_rechaza(db: psycopg.Connection) -> None:
    """VENTANA son días del mes (calendario): incompatible con RODANTE. No hay
    todavía ventana relativa (decisión R2)."""
    with pytest.raises(psycopg.errors.CheckViolation, match="rodante_fecha_modo"):
        _intentar(db, periodicidad="SEMANAL", anclaje="RODANTE", fecha_modo="VENTANA",
                  dia_desde=1, dia_hasta=5)


def test_0265_rodante_con_fecha_calendario_entidad_se_rechaza(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="rodante_fecha_modo"):
        _intentar(db, periodicidad="SEMANAL", anclaje="RODANTE", fecha_modo="CALENDARIO_ENTIDAD")


def test_0265_rodante_con_importe_calendario_entidad_se_rechaza(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="rodante_importe_modo"):
        _intentar(db, periodicidad="SEMANAL", anclaje="RODANTE",
                  importe_modo="CALENDARIO_ENTIDAD")


# ------------------------------------------------------------
# Regresión de constraints previas de regla_versiones
# ------------------------------------------------------------

def test_0265_ventana_fuera_de_rango_sigue_rechazandose(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="ventana"):
        _intentar(db, periodicidad="MENSUAL", anclaje="CALENDARIO", fecha_modo="VENTANA",
                  dia_desde=0, dia_hasta=5)


@pytest.mark.xfail(strict=True, reason=(
    "Defecto previo en 0030 (congelada): ck_regla_versiones__ventana evalúa a NULL "
    "cuando dia_desde/dia_hasta son NULL y un CHECK con resultado NULL se acepta. El "
    "canon exige ambos días con VENTANA. Pendiente de corrección forward-only fuera "
    "de D-126; strict=True obliga a revisar este test cuando se corrija."))
def test_0265_ventana_sin_dias_deberia_rechazarse(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="ventana"):
        _intentar(db, periodicidad="MENSUAL", anclaje="CALENDARIO", fecha_modo="VENTANA")


def test_0265_versionado_sin_solape_sigue_actuando(db: psycopg.Connection) -> None:
    """Cambio de condiciones entre dos ocurrencias: nueva versión contigua de
    la misma regla durable (válido); una versión solapada sigue rechazándose."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            _montar(cursor)
            _version(cursor, periodicidad="SEMANAL", anclaje="RODANTE",
                     desde="2026-01-10", hasta="2026-02-14")
            _version(cursor, periodicidad="SEMANAL", anclaje="RODANTE", desde="2026-02-15")
            with pytest.raises(psycopg.errors.ExclusionViolation):
                _version(cursor, periodicidad="SEMANAL", anclaje="RODANTE", desde="2026-03-01")
        finally:
            cursor.execute("ROLLBACK")
            cursor.execute("RESET ROLE")
