# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_029_f03_02_0260_fail_closed_y_cambio_de_padre.py
# Ruta: tests/database/test_029_f03_02_0260_fail_closed_y_cambio_de_padre.py
# Descripción: Verifica la migration 0260 (FASE 03, hallazgos post-0250):
#
#              - D-a: estado_atribucion ya no tiene DEFAULT; omitirlo falla.
#              - H1: un efecto COMPLETA se valida también al insertarse, y el
#                efecto y sus atribuciones pueden construirse en la misma
#                transacción. La transición PARCIAL -> COMPLETA se valida
#                sobre el valor final.
#              - T2: cuando una hija cambia de padre, se valida también el
#                padre antiguo (participaciones, atribuciones, subtipos).
#              - A7: una entidad no puede tener filas en tablas de subtipo
#                distintas de la coherente con su tipo.
#              - T1/D-b: si el padre no es visible al validar un INSERT o un
#                UPDATE, la transacción falla (VISIBILIDAD) en lugar de pasar
#                en silencio; en DELETE, un padre desaparecido deja la
#                invariante vacía. Se documenta el falso positivo aceptado.
#
#              Las invariantes son diferidas: se fuerzan con
#              SET CONSTRAINTS ALL IMMEDIATE dentro de una transacción que se
#              revierte siempre.
#
# PRECONDICIÓN: requiere 0260.
# Versión: 0.2.0  -- las huellas aceptan exactamente {0260, sucesora 0270} en
#                   las cuatro funciones que 0270 reescribe (T6 y R-INV); el
#                   resto sigue fijado a 0260 (Working Method 12C.5).
# ============================================================

from __future__ import annotations

import psycopg
import pytest

HUELLAS_0260 = {
    "fn_check_atribucion_suma": ("31f04f601350a6dbc7baa3ec8919e980", 2222),
    "fn_check_bolsa_prioridad": ("a583bbd419cb337152617b0c19a1cc42", 1395),
    "fn_check_bolsa_prioridad_alcance": ("7c876f1970c850e791af25226da520b1", 1947),
    "fn_check_entidad_subtipo_unico": ("210cae8afdff0401c1225d258420dd80", 2766),
    "fn_check_hecho_mov_tesoreria_suma": ("2b9483c066e3f637f24d396babe27720", 1670),
    "fn_check_inversion_asignacion_suma": ("182087c02d004ca2c2f0d38bd00f10ff", 1957),
    "fn_check_participacion_suma": ("b76161555c227a8aa19c3ab513aa4687", 3082),
    "fn_check_reversion_movimiento": ("00161f7875783230311834ca84e472e2", 2208),
    "fn_check_transferencia_estructura": ("e956eb54ec62b7ac7b9bcf11ca3f107e", 2392),
}

SUCESORAS_0270 = {
    "fn_check_hecho_mov_tesoreria_suma": {("808128976910a4333fd8c6843d0b9919", 1986)},
    "fn_check_inversion_asignacion_suma": {("128a6bd0e45f5fe3632c83b25cbfa371", 2129)},
    "fn_check_reversion_movimiento": {("91a33cb088ab4ff8d9c56c29fc3d12c2", 2466)},
    "fn_check_transferencia_estructura": {("545db95496409a5adf01fbb98e4b161a", 2722)},
}

OWNER = "c0260000-0000-4000-8000-000000000001"
OTRO_OWNER = "c0260000-0000-4000-8000-0000000000ff"
SELF = "c0260000-0000-4000-8000-000000000002"
TERCERO_2 = "c0260000-0000-4000-8000-000000000003"
ACTOR_2 = "c0260000-0000-4000-8000-000000000004"
TERCERO_3 = "c0260000-0000-4000-8000-000000000005"
ACTOR_3 = "c0260000-0000-4000-8000-000000000006"
CUENTA_A = "c0260000-0000-4000-8000-00000000000a"
CUENTA_B = "c0260000-0000-4000-8000-00000000000b"
HECHO = "c0260000-0000-4000-8000-000000000010"
EFECTO_1 = "c0260000-0000-4000-8000-000000000011"
EFECTO_2 = "c0260000-0000-4000-8000-000000000012"
ENTIDAD_1 = "c0260000-0000-4000-8000-000000000021"
ENTIDAD_2 = "c0260000-0000-4000-8000-000000000022"
MOV_OUT = "c0260000-0000-4000-8000-000000000031"
MOV_IN = "c0260000-0000-4000-8000-000000000032"

INS_CP = ("INSERT INTO gapto.cuenta_participaciones "
          "(cuenta_id, actor_id, porcentaje, vigente_desde) VALUES (%s, %s, %s, '2026-01-01')")
INS_EFECTO = ("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
              "estado_atribucion) VALUES (%s, %s, 'GASTO', %s, %s)")
INS_ATR = ("INSERT INTO gapto.efecto_atribuciones "
           "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) "
           "VALUES (%s, %s, %s, 'MANUAL')")


def _montar(cursor) -> None:
    cursor.execute("SET LOCAL ROLE gapto_owner")
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    cursor.execute("INSERT INTO gapto.usuarios (id, email, nombre) "
                   "VALUES (%s, 'c0260@example.com', 'C0260')", (OWNER,))
    cursor.execute("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) "
                   "VALUES (%s, %s, 'T2', 'PERSONA'), (%s, %s, 'T3', 'PERSONA')",
                   (TERCERO_2, OWNER, TERCERO_3, OWNER))
    cursor.execute("INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) "
                   "VALUES (%s, %s, NULL), (%s, %s, %s), (%s, %s, %s)",
                   (SELF, OWNER, ACTOR_2, OWNER, TERCERO_2, ACTOR_3, OWNER, TERCERO_3))
    for cuenta in (CUENTA_A, CUENTA_B):
        cursor.execute(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "computa_liquidez, computa_patrimonio, permite_negativo) "
            "VALUES (%s, %s, 'Cuenta C0260', 'CORRIENTE', 'ACTIVO', 'EUR', true, true, false)",
            (cuenta, OWNER))
    cursor.execute(
        "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
        "concepto, moneda, estado_localizacion, presupuestable) "
        "SELECT %s, %s, id, DATE '2026-03-01', 'Hecho C0260', 'EUR', 'NO_APLICA', true "
        "FROM gapto.tipos_hecho WHERE codigo = 'GASTO'", (HECHO, OWNER))


def _inmediato(cursor) -> None:
    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _validar_montaje(cursor) -> None:
    """Dispara ya los eventos diferidos del montaje (p. ej. el actor self), para
    que al cambiar de contexto solo quede pendiente el evento bajo prueba."""
    _inmediato(cursor)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")


def _transaccion(db: psycopg.Connection):
    cursor = db.cursor()
    cursor.execute("BEGIN")
    _montar(cursor)
    return cursor


def _cerrar(cursor) -> None:
    cursor.execute("ROLLBACK")
    cursor.execute("RESET ROLE")
    cursor.close()


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

@pytest.mark.parametrize("funcion", sorted(HUELLAS_0260))
def test_0260_huella(db: psycopg.Connection, funcion: str) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT md5(p.prosrc), length(p.prosrc) FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'gapto' AND p.proname = %s
        """, (funcion,))
        fila = cursor.fetchone()
    aceptadas = {HUELLAS_0260[funcion]} | SUCESORAS_0270.get(funcion, set())
    assert fila is not None and tuple(fila) in aceptadas, (
        f"{funcion}: huella {fila} no es ninguna de {sorted(aceptadas)}"
    )


def test_0260_trigger_de_efectos_cubre_insert(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT (t.tgtype & 4) <> 0, (t.tgtype & 16) <> 0, t.tgconstraint <> 0,
                   t.tgdeferrable, t.tginitdeferred
              FROM pg_catalog.pg_trigger t
             WHERE t.tgrelid = 'gapto.hecho_efectos'::regclass
               AND t.tgname = 'trg_hecho_efectos__atribucion_suma'
        """)
        fila = cursor.fetchone()
    assert fila == (True, True, True, True, True)


def test_0260_estado_atribucion_sin_default(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT a.attnotnull, pg_catalog.pg_get_expr(d.adbin, d.adrelid)
              FROM pg_catalog.pg_attribute a
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = 'gapto.hecho_efectos'::regclass AND a.attname = 'estado_atribucion'
        """)
        assert cursor.fetchone() == (True, None)


# ------------------------------------------------------------
# D-a y H1
# ------------------------------------------------------------

def test_0260_omitir_estado_atribucion_falla(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        with pytest.raises(psycopg.errors.NotNullViolation):
            cursor.execute("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, "
                           "importe_delta) VALUES (%s, %s, 'GASTO', -100)", (EFECTO_1, HECHO))
    finally:
        _cerrar(cursor)


def test_0260_efecto_completa_sin_atribuciones_se_rechaza(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_EFECTO, (EFECTO_1, HECHO, -100, "COMPLETA"))
        with pytest.raises(psycopg.errors.RaiseException, match="COMPLETA"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_efecto_y_atribuciones_en_la_misma_transaccion(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_EFECTO, (EFECTO_1, HECHO, -100, "COMPLETA"))
        cursor.execute(INS_ATR, (EFECTO_1, SELF, -60))
        cursor.execute(INS_ATR, (EFECTO_1, ACTOR_2, -40))
        _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_parcial_a_completa_se_valida_sobre_el_valor_final(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_EFECTO, (EFECTO_1, HECHO, -100, "PARCIAL"))
        cursor.execute(INS_ATR, (EFECTO_1, SELF, -60))
        _inmediato(cursor)
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute("UPDATE gapto.hecho_efectos SET estado_atribucion = 'COMPLETA' WHERE id = %s",
                       (EFECTO_1,))
        with pytest.raises(psycopg.errors.RaiseException, match="COMPLETA"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


# ------------------------------------------------------------
# T2: cambio de padre
# ------------------------------------------------------------

def test_0260_mover_participacion_valida_el_padre_antiguo(db: psycopg.Connection) -> None:
    """Estado inicial válido: A = 50+50 y B = 100. En la misma transacción, B
    baja a 50 y recibe una fila de 50 desde A: B vuelve a 100 (válida) y A se
    queda en 50. Antes de 0260 el UPDATE solo validaba B y el cambio pasaba."""
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_CP, (CUENTA_A, SELF, 50))
        cursor.execute(INS_CP, (CUENTA_A, ACTOR_2, 50))
        cursor.execute(INS_CP, (CUENTA_B, ACTOR_3, 100))
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.cuenta_participaciones SET porcentaje = 50 "
                       "WHERE cuenta_id = %s", (CUENTA_B,))
        cursor.execute("UPDATE gapto.cuenta_participaciones SET cuenta_id = %s "
                       "WHERE cuenta_id = %s AND actor_id = %s", (CUENTA_B, CUENTA_A, ACTOR_2))
        with pytest.raises(psycopg.errors.RaiseException, match=CUENTA_A):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_mover_atribucion_valida_el_efecto_antiguo(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_EFECTO, (EFECTO_1, HECHO, -100, "COMPLETA"))
        cursor.execute(INS_ATR, (EFECTO_1, SELF, -60))
        cursor.execute(INS_ATR, (EFECTO_1, ACTOR_2, -40))
        cursor.execute(INS_EFECTO, (EFECTO_2, HECHO, -100, "PARCIAL"))
        _inmediato(cursor)
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute("UPDATE gapto.efecto_atribuciones SET efecto_id = %s "
                       "WHERE efecto_id = %s AND actor_id = %s", (EFECTO_2, EFECTO_1, ACTOR_2))
        with pytest.raises(psycopg.errors.RaiseException, match=EFECTO_1):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def _entidad_propiedad(cursor, entidad: str, con_subtipo: bool) -> None:
    cursor.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'PROPIEDAD', 'Propiedad C0260')", (entidad, OWNER))
    if con_subtipo:
        cursor.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) "
                       "VALUES (%s, 'VIVIENDA')", (entidad,))


def test_0260_mover_subtipo_valida_la_entidad_antigua(db: psycopg.Connection) -> None:
    """Estado inicial válido: dos PROPIEDAD con su fila. En la misma
    transacción se borra la fila de la segunda y se le mueve la de la primera:
    la segunda vuelve a ser válida y la primera se queda sin subtipo. Antes de
    0260 el UPDATE solo validaba la entidad nueva."""
    cursor = _transaccion(db)
    try:
        _entidad_propiedad(cursor, ENTIDAD_1, True)
        _entidad_propiedad(cursor, ENTIDAD_2, True)
        _validar_montaje(cursor)
        cursor.execute("DELETE FROM gapto.propiedades WHERE entidad_id = %s", (ENTIDAD_2,))
        cursor.execute("UPDATE gapto.propiedades SET entidad_id = %s WHERE entidad_id = %s",
                       (ENTIDAD_2, ENTIDAD_1))
        with pytest.raises(psycopg.errors.RaiseException, match=ENTIDAD_1):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_subtipo_adicional_incoherente_se_rechaza(db: psycopg.Connection) -> None:
    """A7: una PROPIEDAD con su fila en propiedades y además una fila en
    contratos. Antes de 0260 solo se contaba la tabla coherente y pasaba."""
    cursor = _transaccion(db)
    try:
        _entidad_propiedad(cursor, ENTIDAD_1, True)
        _inmediato(cursor)
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute("INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, "
                       "tipo_contrato) VALUES (%s, %s, 'OTRO')", (ENTIDAD_1, ENTIDAD_1))
        with pytest.raises(psycopg.errors.RaiseException, match="total en tablas de subtipo=2"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


# ------------------------------------------------------------
# T1 / D-b: visibilidad
# ------------------------------------------------------------

def test_0260_participacion_con_contexto_cambiado_falla(db: psycopg.Connection) -> None:
    cursor = _transaccion(db)
    try:
        _validar_montaje(cursor)
        cursor.execute(INS_CP, (CUENTA_A, SELF, 100))
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        with pytest.raises(psycopg.errors.RaiseException, match="VISIBILIDAD"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_transferencia_con_contexto_cambiado_falla(db: psycopg.Connection) -> None:
    """Antes de 0260 las comparaciones con NULL no disparaban ningún RAISE y la
    transferencia pasaba sin validar (fail-open implícito)."""
    cursor = _transaccion(db)
    try:
        _validar_montaje(cursor)
        for movimiento, cuenta, importe in ((MOV_OUT, CUENTA_A, -100), (MOV_IN, CUENTA_B, 100)):
            cursor.execute(
                "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, "
                "importe, confirmado_at, clase_movimiento) "
                "VALUES (%s, %s, DATE '2026-03-01', %s, now(), 'OPERACION')",
                (movimiento, cuenta, importe))
        cursor.execute("INSERT INTO gapto.transferencias (movimiento_salida_id, "
                       "movimiento_entrada_id) VALUES (%s, %s)", (MOV_OUT, MOV_IN))
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        with pytest.raises(psycopg.errors.RaiseException, match="VISIBILIDAD"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_borrar_hijas_y_padre_en_la_misma_transaccion_es_valido(
        db: psycopg.Connection) -> None:
    """DELETE: el padre desaparecido deja la invariante vacía (FK RESTRICT)."""
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_CP, (CUENTA_A, SELF, 100))
        _inmediato(cursor)
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute("DELETE FROM gapto.cuenta_participaciones WHERE cuenta_id = %s", (CUENTA_A,))
        cursor.execute("DELETE FROM gapto.cuentas WHERE id = %s", (CUENTA_A,))
        _inmediato(cursor)
    finally:
        _cerrar(cursor)


def test_0260_falso_positivo_aceptado_por_d_b(db: psycopg.Connection) -> None:
    """D-b(i): INSERT hija -> DELETE hija -> DELETE padre en la misma
    transacción. El evento de INSERT llega al COMMIT con el padre ya borrado y
    se rechaza. Se acepta a propósito: detectar el evento obsoleto exigiría
    comprobar la hija bajo RLS y reabriría el fail-open."""
    cursor = _transaccion(db)
    try:
        cursor.execute(INS_CP, (CUENTA_A, SELF, 100))
        cursor.execute("DELETE FROM gapto.cuenta_participaciones WHERE cuenta_id = %s", (CUENTA_A,))
        cursor.execute("DELETE FROM gapto.cuentas WHERE id = %s", (CUENTA_A,))
        with pytest.raises(psycopg.errors.RaiseException, match="VISIBILIDAD"):
            _inmediato(cursor)
    finally:
        _cerrar(cursor)
