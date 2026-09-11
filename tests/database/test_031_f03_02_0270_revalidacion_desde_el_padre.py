# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_031_f03_02_0270_revalidacion_desde_el_padre.py
# Ruta: tests/database/test_031_f03_02_0270_revalidacion_desde_el_padre.py
# Descripción: Verifica la migration 0270 (FASE 03 / F03-02): revalidación de
#              invariantes multi-fila desde la fila padre, D-119 (T6), D-120
#              (R-MON), R-TPN, R-GAR y A8, en una sola sesión. La concurrencia
#              se prueba aparte en test_027 (C12-C17).
#
#              - Contrato: 4 funciones nuevas y 6 reescritas con su huella
#                ACTUAL exacta (los tests históricos aceptan baseline +
#                sucesoras; este fija el estado vigente), 5 triggers nuevos
#                con eventos y diferibilidad, FOR UPDATE solo en R-MON, orden
#                LEAST/GREATEST en los dos padres de GARANTIZADA_POR.
#              - D-119(a): no se anula un movimiento con transferencia,
#                asignaciones o reversiones ACTIVAS; sí con reversiones
#                anuladas o anulando original y reversión juntos.
#              - Revalidación desde el padre: importe frente a asignaciones,
#                estructura de transferencia (importe y cuenta de una pata),
#                reversiones (suma y signo), importe_delta y tipo_efecto frente
#                a asignaciones de inversión.
#              - T6(b): ninguna dependencia nueva o movida hacia un ANULADO; en
#                reversiones solo si la reversión está ACTIVA (reactivar falla,
#                editar una anulada no).
#              - R-MON inmediato: saldo_apertura 0 cuenta, movimiento anulado
#                cuenta, cierre cuenta, participaciones no cuentan, mismo valor
#                y alta simultánea de moneda y apertura permitidos.
#              - R-TPN con NULL (IS DISTINCT FROM) y R-GAR en ambos extremos.
#              - T1: VISIBILIDAD al revalidar desde el padre con el contexto
#                cambiado; hijas por el camino de gapto_runtime.
#
#              Todas las transacciones se revierten. Las invariantes diferidas
#              se fuerzan con SET CONSTRAINTS ALL IMMEDIATE tras validar antes
#              el montaje.
#
# PRECONDICIÓN: requiere 0270.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

HUELLAS_0270 = {
    "fn_check_hecho_mov_tesoreria_suma": ("808128976910a4333fd8c6843d0b9919", 1986),
    "fn_check_transferencia_estructura": ("545db95496409a5adf01fbb98e4b161a", 2722),
    "fn_check_reversion_movimiento": ("91a33cb088ab4ff8d9c56c29fc3d12c2", 2466),
    "fn_check_inversion_asignacion_suma": ("128a6bd0e45f5fe3632c83b25cbfa371", 2129),
    "fn_check_tercero_persona_naturaleza": ("c2fd9d2c7261ca315a658eba18db02c5", 616),
    "fn_check_garantizada_por": ("e31522fac182a670d7f698b6e728fab7", 1738),
    "fn_check_movimiento_padre": ("d62ba0700dbac9a94884e39bafd3baeb", 5859),
    "fn_check_cuenta_moneda": ("f13b175f54af8780ed57ffaebd5e72bf", 1085),
    "fn_check_tercero_naturaleza": ("067d309ba09fe37c8743928d78826bc8", 706),
    "fn_check_entidad_garantizada_por": ("04ef0d4c49fdf1a1b1e06e82aeca3845", 1922),
}

# tabla -> (trigger, función, eventos UPDATE OF, constraint diferido)
TRIGGERS_0270 = {
    "movimientos_tesoreria": ("trg_movimientos_tesoreria__padre_dependencias",
                              "fn_check_movimiento_padre", ["cuenta_id", "estado", "importe"], True),
    "hecho_efectos": ("trg_hecho_efectos__inversion_asignacion",
                      "fn_check_inversion_asignacion_suma", ["importe_delta", "tipo_efecto"], True),
    "cuentas": ("trg_cuentas__moneda_con_historia", "fn_check_cuenta_moneda", ["moneda"], False),
    "terceros": ("trg_terceros__naturaleza_personas", "fn_check_tercero_naturaleza",
                 ["naturaleza"], True),
    "entidades": ("trg_entidades__garantizada_por", "fn_check_entidad_garantizada_por",
                  ["tipo_entidad"], True),
}

P = "c0310000-0000-4000-8000-0000000000"
OWNER, OTRO_OWNER, SELF = P + "01", P + "ff", P + "02"
CUENTA_A, CUENTA_B, CUENTA_C, CUENTA_USD = P + "0a", P + "0b", P + "0c", P + "0d"
HECHO, EFECTO_INV = P + "10", P + "11"
MOV_OUT, MOV_IN, MOV_X, MOV_Y, REV_1 = P + "31", P + "32", P + "33", P + "34", P + "35"
ENT_INV, ENT_FIN, ENT_PROP = P + "41", P + "42", P + "43"
TERCERO = P + "51"
CIERRE = P + "61"


# ------------------------------------------------------------
# Montaje
# ------------------------------------------------------------

def _montar(cursor) -> None:
    cursor.execute("SET LOCAL ROLE gapto_owner")
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    cursor.execute("INSERT INTO gapto.usuarios (id, email, nombre) "
                   "VALUES (%s, 'c0310@example.com', 'C0310')", (OWNER,))
    cursor.execute("INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) "
                   "VALUES (%s, %s, NULL)", (SELF, OWNER))
    for cuenta, moneda in ((CUENTA_A, "EUR"), (CUENTA_B, "EUR"), (CUENTA_C, "EUR"),
                           (CUENTA_USD, "USD")):
        cursor.execute(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "computa_liquidez, computa_patrimonio, permite_negativo) "
            "VALUES (%s, %s, 'Cuenta C0310', 'CORRIENTE', 'ACTIVO', %s, true, true, false)",
            (cuenta, OWNER, moneda))
    cursor.execute(
        "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
        "concepto, moneda, estado_localizacion, presupuestable) "
        "SELECT %s, %s, id, DATE '2026-03-01', 'Hecho C0310', 'EUR', 'NO_APLICA', true "
        "FROM gapto.tipos_hecho WHERE codigo = 'GASTO'", (HECHO, OWNER))


def _mov(cursor, id_: str, cuenta: str, importe: str, reversion_de: str | None = None,
         estado: str = "ACTIVO") -> None:
    cursor.execute(
        "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
        "confirmado_at, clase_movimiento, estado, anulado_at, reversion_de_movimiento_id) "
        "VALUES (%s, %s, DATE '2026-03-01', %s, now(), 'OPERACION', %s, "
        "CASE WHEN %s = 'ANULADO' THEN now() END, %s)",
        (id_, cuenta, Decimal(importe), estado, estado, reversion_de))


def _hmt(cursor, movimiento: str, importe: str) -> None:
    cursor.execute(
        "INSERT INTO gapto.hecho_movimientos_tesoreria (hecho_id, movimiento_tesoreria_id, "
        "importe_asignado) VALUES (%s, %s, %s)", (HECHO, movimiento, Decimal(importe)))


def _transferencia(cursor) -> None:
    _mov(cursor, MOV_OUT, CUENTA_A, "-100")
    _mov(cursor, MOV_IN, CUENTA_B, "100")
    cursor.execute("INSERT INTO gapto.transferencias (movimiento_salida_id, movimiento_entrada_id) "
                   "VALUES (%s, %s)", (MOV_OUT, MOV_IN))


def _anular(cursor, movimiento: str) -> None:
    cursor.execute("UPDATE gapto.movimientos_tesoreria SET estado = 'ANULADO', anulado_at = now() "
                   "WHERE id = %s", (movimiento,))


def _reactivar(cursor, movimiento: str) -> None:
    cursor.execute("UPDATE gapto.movimientos_tesoreria SET estado = 'ACTIVO', anulado_at = NULL "
                   "WHERE id = %s", (movimiento,))


def _efecto_inversion(cursor, importe: str = "100") -> None:
    cursor.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'INVERSION', 'Fondo C0310')", (ENT_INV, OWNER))
    cursor.execute("INSERT INTO gapto.inversiones (entidad_id, rol_estructura, tipo_producto, "
                   "moneda, estado) VALUES (%s, 'POSICION', 'FONDO', 'EUR', 'ACTIVA')", (ENT_INV,))
    cursor.execute("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
                   "estado_atribucion) VALUES (%s, %s, 'INVERSION', %s, 'PARCIAL')",
                   (EFECTO_INV, HECHO, Decimal(importe)))


def _asignacion_inversion(cursor, importe: str) -> None:
    cursor.execute("INSERT INTO gapto.inversion_asignaciones_efecto (efecto_inversion_id, "
                   "inversion_entidad_id, importe_asignado) VALUES (%s, %s, %s)",
                   (EFECTO_INV, ENT_INV, Decimal(importe)))


def _tercero_persona(cursor) -> None:
    cursor.execute("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) "
                   "VALUES (%s, %s, 'Persona C0310', 'PERSONA')", (TERCERO, OWNER))
    cursor.execute("INSERT INTO gapto.tercero_personas (tercero_id) VALUES (%s)", (TERCERO,))


def _garantia(cursor) -> None:
    cursor.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca C0310'), "
                   "(%s, %s, 'PROPIEDAD', 'Piso C0310')", (ENT_FIN, OWNER, ENT_PROP, OWNER))
    cursor.execute("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, estado) "
                   "VALUES (%s, 'HIPOTECA', 'EUR', 'ACTIVA')", (ENT_FIN,))
    cursor.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad, "
                   "incluir_en_rentabilidad) VALUES (%s, 'VIVIENDA', true)", (ENT_PROP,))
    cursor.execute("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, entidad_destino_id, "
                   "tipo_relacion) VALUES (%s, %s, 'GARANTIZADA_POR')", (ENT_FIN, ENT_PROP))


def _cambiar_tipo(cursor, entidad: str, desde: str, hacia: str) -> None:
    """Cambio de tipo coherente con A7: retira el subtipo antiguo y crea el nuevo."""
    tabla = {"FINANCIACION": "financiaciones", "PROPIEDAD": "propiedades"}[desde]
    cursor.execute(f"DELETE FROM gapto.{tabla} WHERE entidad_id = %s", (entidad,))
    cursor.execute("UPDATE gapto.entidades SET tipo_entidad = %s WHERE id = %s", (hacia, entidad))
    assert hacia == "SERVICIO"
    cursor.execute("INSERT INTO gapto.servicios (entidad_id, tipo_servicio) VALUES (%s, 'OTRO')",
                   (entidad,))


def _inmediato(cursor) -> None:
    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _validar_montaje(cursor) -> None:
    _inmediato(cursor)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")


class _Tx:
    """Transacción de prueba con montaje validado; siempre se revierte."""

    def __init__(self, db: psycopg.Connection, *extras) -> None:
        self.db = db
        self.extras = extras

    def __enter__(self):
        self.cursor = self.db.cursor()
        self.cursor.execute("BEGIN")
        _montar(self.cursor)
        for extra in self.extras:
            extra(self.cursor)
        _validar_montaje(self.cursor)
        return self.cursor

    def __exit__(self, *exc) -> None:
        self.cursor.execute("ROLLBACK")
        self.cursor.execute("RESET ROLE")
        self.cursor.close()


def _rechaza(cursor, patron: str) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match=patron):
        _inmediato(cursor)


# ------------------------------------------------------------
# Contrato
# ------------------------------------------------------------

@pytest.mark.parametrize("funcion", sorted(HUELLAS_0270))
def test_0270_huella_y_atributos(db: psycopg.Connection, funcion: str) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT md5(p.prosrc), length(p.prosrc), p.prosecdef, p.provolatile, p.proconfig,
                   pg_catalog.pg_get_userbyid(p.proowner)
              FROM pg_catalog.pg_proc p
             WHERE p.pronamespace = 'gapto'::regnamespace AND p.proname = %s
        """, (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"{funcion} no existe"
    assert (fila[0], fila[1]) == HUELLAS_0270[funcion], f"{funcion}: huella {fila[:2]}"
    assert fila[2:] == (False, "v", None, "gapto_owner"), f"{funcion}: atributos {fila[2:]}"
    assert "--" not in _fuente(db, funcion), f"{funcion}: comentario dentro del cuerpo"


def _fuente(db: psycopg.Connection, funcion: str) -> str:
    with db.cursor() as cursor:
        cursor.execute("SELECT prosrc FROM pg_catalog.pg_proc WHERE proname = %s "
                       "AND pronamespace = 'gapto'::regnamespace", (funcion,))
        return cursor.fetchone()[0]


@pytest.mark.parametrize("tabla", sorted(TRIGGERS_0270))
def test_0270_trigger(db: psycopg.Connection, tabla: str) -> None:
    trigger, funcion, columnas, diferido = TRIGGERS_0270[tabla]
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname, t.tgconstraint <> 0, t.tgdeferrable, t.tginitdeferred, t.tgenabled,
                   t.tgtype,
                   (SELECT array_agg(a.attname::text ORDER BY a.attname)
                      FROM pg_catalog.pg_attribute a
                     WHERE a.attrelid = t.tgrelid AND a.attnum = ANY(t.tgattr))
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
             WHERE t.tgrelid = ('gapto.' || %s)::regclass AND t.tgname = %s
        """, (tabla, trigger))
        fila = cursor.fetchone()
    assert fila is not None, f"{tabla}: falta {trigger}"
    nombre, es_constraint, diferible, inicial, habilitado, tipo, atributos = fila
    assert nombre == funcion
    assert (es_constraint, diferible, inicial) == (diferido, diferido, diferido)
    assert habilitado == "O"
    assert tipo == 1 | 16, f"{trigger}: debe ser AFTER UPDATE FOR EACH ROW (tgtype={tipo})"
    assert atributos == columnas


def test_0270_for_update_solo_en_r_mon(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname FROM pg_catalog.pg_proc p
             WHERE p.pronamespace = 'gapto'::regnamespace AND p.prosrc ~* 'for\\s+update'
        """)
        assert [f[0] for f in cursor.fetchall()] == ["fn_check_cuenta_moneda"]
    texto = " ".join(_fuente(db, "fn_check_cuenta_moneda").lower().split())
    lock = texto.index("for update")
    assert texto.index("is not distinct from old.moneda") < lock, "debe salir antes de bloquear"
    assert lock < texto.index("old.saldo_apertura") < texto.index("gapto.movimientos_tesoreria")


@pytest.mark.parametrize("funcion,locks", [
    ("fn_check_garantizada_por", 2), ("fn_check_tercero_persona_naturaleza", 1),
    ("fn_check_movimiento_padre", 3), ("fn_check_tercero_naturaleza", 1),
    ("fn_check_entidad_garantizada_por", 1),
])
def test_0270_modo_de_lock(db: psycopg.Connection, funcion: str, locks: int) -> None:
    texto = " ".join(_fuente(db, funcion).lower().split())
    assert texto.count("for no key update") == locks
    if funcion in ("fn_check_garantizada_por", "fn_check_movimiento_padre"):
        menor = texto.index("least(")
        mayor = texto.index("greatest(")
        assert menor < mayor, f"{funcion}: los dos padres deben bloquearse en orden LEAST -> GREATEST"
    if funcion in ("fn_check_garantizada_por", "fn_check_tercero_persona_naturaleza"):
        assert texto.index("for no key update") < texto.index("not found"), (
            f"{funcion}: el lock debe preceder a la lectura que valida")


def test_0270_check_a8(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT convalidated, pg_catalog.pg_get_constraintdef(oid)
              FROM pg_catalog.pg_constraint
             WHERE conrelid = 'gapto.regla_versiones'::regclass
               AND conname = 'ck_regla_versiones__ventana_dias_obligatorios'
        """)
        fila = cursor.fetchone()
    assert fila is not None and fila[0]
    assert "dia_desde IS NOT NULL" in fila[1] and "dia_hasta IS NOT NULL" in fila[1]


# ------------------------------------------------------------
# D-119 (a) y T6 (b)
# ------------------------------------------------------------

def test_0270_anular_con_asignacion_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _hmt(cursor, MOV_X, "-100")
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _rechaza(cursor, "ANULADO porque tiene asignaciones")


def test_0270_anular_con_transferencia_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        _anular(cursor, MOV_IN)
        _rechaza(cursor, "ANULADO porque participa en una transferencia")


def test_0270_anular_original_con_reversion_activa_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X)
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _rechaza(cursor, "reversiones ACTIVAS")


def test_0270_anular_original_y_reversion_juntos_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X)
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _anular(cursor, REV_1)
        _inmediato(cursor)


def test_0270_anular_sin_dependencias_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _inmediato(cursor)


def test_0270_asignacion_hacia_anulado_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100", estado="ANULADO")
        _validar_montaje(cursor)
        _hmt(cursor, MOV_X, "-10")
        _rechaza(cursor, "esta ANULADO y no admite asignaciones")


def test_0270_mover_asignacion_hacia_anulado_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, MOV_Y, CUENTA_A, "-100", estado="ANULADO")
        _hmt(cursor, MOV_X, "-10")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_movimientos_tesoreria SET movimiento_tesoreria_id = %s "
                       "WHERE movimiento_tesoreria_id = %s", (MOV_Y, MOV_X))
        _rechaza(cursor, "esta ANULADO y no admite asignaciones")


def test_0270_transferencia_con_pata_anulada_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_OUT, CUENTA_A, "-100")
        _mov(cursor, MOV_IN, CUENTA_B, "100", estado="ANULADO")
        _validar_montaje(cursor)
        cursor.execute("INSERT INTO gapto.transferencias (movimiento_salida_id, "
                       "movimiento_entrada_id) VALUES (%s, %s)", (MOV_OUT, MOV_IN))
        _rechaza(cursor, "las dos patas deben estar ACTIVAS")


def test_0270_reversion_activa_hacia_anulado_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100", estado="ANULADO")
        _validar_montaje(cursor)
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X)
        _rechaza(cursor, "una reversion ACTIVA no puede apuntar")


def test_0270_reactivar_reversion_de_anulado_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X, estado="ANULADO")
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _validar_montaje(cursor)
        _reactivar(cursor, REV_1)
        _rechaza(cursor, "una reversion ACTIVA no puede apuntar")


def test_0270_editar_reversion_anulada_de_anulado_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X, estado="ANULADO")
        _validar_montaje(cursor)
        _anular(cursor, MOV_X)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = 30 WHERE id = %s", (REV_1,))
        _inmediato(cursor)


# ------------------------------------------------------------
# Revalidación desde el padre: tesorería
# ------------------------------------------------------------

def test_0270_importe_bajo_asignaciones_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _hmt(cursor, MOV_X, "-100")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -50 WHERE id = %s", (MOV_X,))
        _rechaza(cursor, "supera en valor absoluto el nuevo importe")


def test_0270_cambio_de_signo_con_asignaciones_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _hmt(cursor, MOV_X, "-60")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = 100 WHERE id = %s", (MOV_X,))
        _rechaza(cursor, "mismo signo que el movimiento")


def test_0270_importe_compatible_con_asignaciones_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _hmt(cursor, MOV_X, "-60")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -60 WHERE id = %s", (MOV_X,))
        _inmediato(cursor)


def test_0270_importe_de_una_pata_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = 80 WHERE id = %s", (MOV_IN,))
        _rechaza(cursor, "debe igualar importe_entrada")


def test_0270_importe_de_las_dos_patas_juntas_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = 80 WHERE id = %s", (MOV_IN,))
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -80 WHERE id = %s", (MOV_OUT,))
        _inmediato(cursor)


def test_0270_pata_a_la_misma_cuenta_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET cuenta_id = %s WHERE id = %s",
                       (CUENTA_A, MOV_IN))
        _rechaza(cursor, "cuentas distintas")


def test_0270_pata_a_otra_cuenta_valida_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET cuenta_id = %s WHERE id = %s",
                       (CUENTA_C, MOV_IN))
        _inmediato(cursor)


def test_0270_pata_a_otra_moneda_no_exige_igualdad(db: psycopg.Connection) -> None:
    with _Tx(db, _transferencia) as cursor:
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET cuenta_id = %s, importe = 110 "
                       "WHERE id = %s", (CUENTA_USD, MOV_IN))
        _inmediato(cursor)


def test_0270_original_bajo_sus_reversiones_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "70", reversion_de=MOV_X)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -50 WHERE id = %s", (MOV_X,))
        _rechaza(cursor, "supera el nuevo importe del original")


def test_0270_original_cambia_de_signo_con_reversion_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "40", reversion_de=MOV_X)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = 100 WHERE id = %s", (MOV_X,))
        _rechaza(cursor, "del mismo signo que su nuevo importe")


def test_0270_original_con_reversion_anulada_puede_bajar(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _mov(cursor, REV_1, CUENTA_A, "70", reversion_de=MOV_X, estado="ANULADO")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -50 WHERE id = %s", (MOV_X,))
        _inmediato(cursor)


# ------------------------------------------------------------
# R-INV
# ------------------------------------------------------------

def test_0270_importe_delta_bajo_asignaciones_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _efecto_inversion) as cursor:
        _asignacion_inversion(cursor, "100")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_efectos SET importe_delta = 50 WHERE id = %s", (EFECTO_INV,))
        _rechaza(cursor, "supera en valor absoluto el efecto")


def test_0270_tipo_efecto_con_asignaciones_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _efecto_inversion) as cursor:
        _asignacion_inversion(cursor, "40")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_efectos SET tipo_efecto = 'GASTO' WHERE id = %s",
                       (EFECTO_INV,))
        _rechaza(cursor, "debe ser tipo_efecto=INVERSION")


def test_0270_tipo_efecto_sin_asignaciones_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db, _efecto_inversion) as cursor:
        cursor.execute("UPDATE gapto.hecho_efectos SET tipo_efecto = 'GASTO' WHERE id = %s",
                       (EFECTO_INV,))
        _inmediato(cursor)


def test_0270_asignacion_a_efecto_no_inversion_sigue_rechazandose(db: psycopg.Connection) -> None:
    with _Tx(db, _efecto_inversion) as cursor:
        cursor.execute("UPDATE gapto.hecho_efectos SET tipo_efecto = 'GASTO' WHERE id = %s",
                       (EFECTO_INV,))
        _validar_montaje(cursor)
        _asignacion_inversion(cursor, "10")
        _rechaza(cursor, "debe ser tipo_efecto=INVERSION")


# ------------------------------------------------------------
# R-MON (inmediato)
# ------------------------------------------------------------

def _moneda(cursor, cuenta: str, moneda: str) -> None:
    cursor.execute("UPDATE gapto.cuentas SET moneda = %s WHERE id = %s", (moneda, cuenta))


def test_0270_moneda_sin_historia_se_puede_cambiar(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        cursor.execute("INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, "
                       "vigente_desde) VALUES (%s, %s, 100, '2026-01-01')", (CUENTA_C, SELF))
        _validar_montaje(cursor)
        _moneda(cursor, CUENTA_C, "GBP")


def test_0270_moneda_con_saldo_apertura_cero_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        cursor.execute("UPDATE gapto.cuentas SET saldo_apertura = 0, "
                       "fecha_inicio_ledger = DATE '2026-01-01' WHERE id = %s", (CUENTA_C,))
        with pytest.raises(psycopg.errors.RaiseException, match="saldo de apertura"):
            _moneda(cursor, CUENTA_C, "GBP")


def test_0270_moneda_con_movimiento_anulado_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_C, "-5", estado="ANULADO")
        with pytest.raises(psycopg.errors.RaiseException, match="movimientos de tesoreria"):
            _moneda(cursor, CUENTA_C, "GBP")


def test_0270_moneda_con_cierre_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        cursor.execute(
            "INSERT INTO gapto.cierres_mensuales (id, owner_user_id, periodo_desde, periodo_hasta, "
            "cerrado_at, criterio, origen_cierre, metodologia_version, version_cierre) "
            "VALUES (%s, %s, '2026-01-01', '2026-01-31', now(), 'CAJA', 'CALCULADO_2027', 'v1', 1)",
            (CIERRE, OWNER))
        cursor.execute(
            "INSERT INTO gapto.cierre_saldos_cuenta (cierre_id, cuenta_id, moneda, naturaleza, "
            "computa_liquidez, computa_patrimonio) VALUES (%s, %s, 'EUR', 'ACTIVO', true, true)",
            (CIERRE, CUENTA_C))
        with pytest.raises(psycopg.errors.RaiseException, match="saldos de cierre"):
            _moneda(cursor, CUENTA_C, "GBP")


def test_0270_moneda_mismo_valor_con_historia_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_C, "-5")
        _moneda(cursor, CUENTA_C, "EUR")


def test_0270_moneda_y_apertura_en_la_misma_sentencia_es_valido(db: psycopg.Connection) -> None:
    """OLD.saldo_apertura IS NULL: la historia nace ya bajo la moneda nueva."""
    with _Tx(db) as cursor:
        cursor.execute("UPDATE gapto.cuentas SET moneda = 'GBP', saldo_apertura = 10, "
                       "fecha_inicio_ledger = DATE '2026-01-01' WHERE id = %s", (CUENTA_C,))


# ------------------------------------------------------------
# R-TPN
# ------------------------------------------------------------

@pytest.mark.parametrize("naturaleza", ["EMPRESA", None])
def test_0270_naturaleza_con_persona_se_rechaza(db: psycopg.Connection, naturaleza) -> None:
    with _Tx(db, _tercero_persona) as cursor:
        cursor.execute("UPDATE gapto.terceros SET naturaleza = %s WHERE id = %s", (naturaleza, TERCERO))
        _rechaza(cursor, "su naturaleza debe ser PERSONA")


def test_0270_naturaleza_y_baja_de_persona_juntas_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db, _tercero_persona) as cursor:
        cursor.execute("UPDATE gapto.terceros SET naturaleza = 'EMPRESA' WHERE id = %s", (TERCERO,))
        cursor.execute("DELETE FROM gapto.tercero_personas WHERE tercero_id = %s", (TERCERO,))
        _inmediato(cursor)


def test_0270_persona_por_runtime_bloquea_y_valida(db: psycopg.Connection) -> None:
    """Camino real: gapto_runtime inserta la persona (necesita poder bloquear el tercero)."""
    with _Tx(db) as cursor:
        cursor.execute("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) "
                       "VALUES (%s, %s, 'T', 'PERSONA')", (TERCERO, OWNER))
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("INSERT INTO gapto.tercero_personas (tercero_id) VALUES (%s)", (TERCERO,))
        cursor.execute("UPDATE gapto.terceros SET naturaleza = 'OTRO' WHERE id = %s", (TERCERO,))
        _rechaza(cursor, "su naturaleza debe ser PERSONA")


def test_0270_persona_con_tercero_invisible_falla_visibilidad(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        cursor.execute("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) "
                       "VALUES (%s, %s, 'T', 'PERSONA')", (TERCERO, OWNER))
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        with pytest.raises(psycopg.errors.RaiseException, match="tercero_personas: VISIBILIDAD"):
            cursor.execute("INSERT INTO gapto.tercero_personas (tercero_id) VALUES (%s)", (TERCERO,))


# ------------------------------------------------------------
# R-GAR
# ------------------------------------------------------------

def test_0270_origen_deja_de_ser_financiacion_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _garantia) as cursor:
        _cambiar_tipo(cursor, ENT_FIN, "FINANCIACION", "SERVICIO")
        _rechaza(cursor, "es origen de GARANTIZADA_POR y debe ser FINANCIACION")


def test_0270_destino_deja_de_ser_propiedad_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db, _garantia) as cursor:
        _cambiar_tipo(cursor, ENT_PROP, "PROPIEDAD", "SERVICIO")
        _rechaza(cursor, "es destino de GARANTIZADA_POR y debe ser PROPIEDAD")


def test_0270_cambio_de_tipo_sin_garantia_es_valido(db: psycopg.Connection) -> None:
    with _Tx(db, _garantia) as cursor:
        cursor.execute("DELETE FROM gapto.entidad_relaciones WHERE entidad_origen_id = %s", (ENT_FIN,))
        _cambiar_tipo(cursor, ENT_PROP, "PROPIEDAD", "SERVICIO")
        _inmediato(cursor)


def test_0270_garantia_por_runtime_control(db: psycopg.Connection) -> None:
    """Control del camino real: gapto_runtime puede bloquear las dos entidades
    (necesita UPDATE sobre entidades) y crear una garantía válida; la
    discriminación del lock es concurrente (C17)."""
    with _Tx(db, _garantia) as cursor:
        cursor.execute("DELETE FROM gapto.entidad_relaciones WHERE entidad_origen_id = %s", (ENT_FIN,))
        _validar_montaje(cursor)
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, "
                       "entidad_destino_id, tipo_relacion) VALUES (%s, %s, 'GARANTIZADA_POR')",
                       (ENT_FIN, ENT_PROP))
        _inmediato(cursor)


def test_0270_garantia_con_entidad_invisible_falla_visibilidad(db: psycopg.Connection) -> None:
    with _Tx(db, _garantia) as cursor:
        cursor.execute("DELETE FROM gapto.entidad_relaciones WHERE entidad_origen_id = %s", (ENT_FIN,))
        _validar_montaje(cursor)
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        with pytest.raises(psycopg.errors.RaiseException, match="entidad_relaciones: VISIBILIDAD"):
            cursor.execute("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, "
                           "entidad_destino_id, tipo_relacion) VALUES (%s, %s, 'GARANTIZADA_POR')",
                           (ENT_FIN, ENT_PROP))


# ------------------------------------------------------------
# T1 desde el padre
# ------------------------------------------------------------

def test_0270_movimiento_con_contexto_cambiado_falla(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _mov(cursor, MOV_X, CUENTA_A, "-100")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET importe = -90 WHERE id = %s", (MOV_X,))
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        _rechaza(cursor, "movimientos_tesoreria: VISIBILIDAD")


def test_0270_efecto_con_contexto_cambiado_falla(db: psycopg.Connection) -> None:
    """Se usa tipo_efecto porque importe_delta dispara también el trigger de
    atribuciones, que ya era fail-closed antes de 0270."""
    with _Tx(db, _efecto_inversion) as cursor:
        cursor.execute("UPDATE gapto.hecho_efectos SET tipo_efecto = 'INVERSION' WHERE id = %s",
                       (EFECTO_INV,))
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
        _rechaza(cursor, "hecho_efectos: VISIBILIDAD - el efecto .* asignacion de inversion")
