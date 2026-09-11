# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_032_f03_02_0280_aciclicidad_y_cadenas.py
# Ruta: tests/database/test_032_f03_02_0280_aciclicidad_y_cadenas.py
# Descripción: Verifica la migration 0280 (FASE 03 / F03-02) en una sola
#              sesión: aciclicidad D-123 de los cuatro árboles, PARTE_DE,
#              reversiones de profundidad 1 y cadenas de sustitución de
#              presupuestos y cierres (B.6: monotonía de versión, sin CYCLE).
#              La concurrencia se prueba en test_027 (C18-C25).
#
#              - Contrato: huellas ACTUALES exactas de las 4 funciones de
#                0280, atributos, 7 constraint triggers diferidos, 3 UNIQUE,
#                ausencia de la función y los triggers antiguos.
#              - Equivalencia estructural D-115 de clasificaciones,
#                inversiones y regiones con categorías (misma función, mismo
#                orden lock -> relectura -> CYCLE, mismo tipo de clave).
#              - Árboles: ciclo de 2 y de 3, auto-referencia, estado final
#                distinto del NEW del evento, ciclo previo sin recursión
#                infinita, T1 fail-closed.
#              - PARTE_DE: ciclos, cambio de tipo en ambos sentidos, cambio
#                de extremo, mismo owner exigido también con BYPASSRLS, otros
#                tipos sin aciclicidad.
#              - Reversiones: directas válidas, profundidad 2, A<->B,
#                reversión anulada que apunta a una reversión, movimiento con
#                hijos, mover y quitar la relación, D-119.
#              - Cadenas: identidad, versión mayor con huecos, igual o menor
#                rechazada, bifurcación e identidad duplicada (UNIQUE),
#                revalidación del sucesor, corrección multifila, sin reglas
#                de estado.
#              - La auto-referencia de inversiones la cubre el CHECK previo
#                ck_inversiones__no_self_padre; la versión igual, la UNIQUE.
#
#              Mutantes equivalentes documentados (no discriminables):
#              (1) no revalidar el padre/predecesor ANTIGUO al quitar o mover
#              una arista: ninguna regla exige hijo ni sucesor; (2) '>' -> '>='
#              en la versión: la identidad es obligatoriamente igual y la
#              UNIQUE de identidad versionada rechaza antes la versión igual.
#
# PRECONDICIÓN: requiere 0280.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

HUELLAS_0280 = {
    "fn_check_reversion_movimiento": ("bd4ab19984492486f595cb539f78d263", 3057),
    "fn_check_jerarquia_aciclica": ("7fc289a080c5d9c0b2c731c69399d79c", 3903),
    "fn_check_hecho_parte_de_aciclico": ("0bc045230c00b7857343c9c3d99ce7ad", 2060),
    "fn_check_cadena_sustitucion": ("d8b89d79f5907f6690d0c31cee7ddd54", 5357),
}

# tabla -> (trigger, función, columnas UPDATE OF)
TRIGGERS_0280 = {
    "categorias_financieras": ("trg_categorias_financieras__aciclica", "fn_check_jerarquia_aciclica",
                               ["parent_id"]),
    "clasificaciones_tercero": ("trg_clasificaciones_tercero__aciclica", "fn_check_jerarquia_aciclica",
                                ["parent_id"]),
    "inversiones": ("trg_inversiones__aciclica", "fn_check_jerarquia_aciclica",
                    ["inversion_padre_entidad_id"]),
    "regiones": ("trg_regiones__aciclica", "fn_check_jerarquia_aciclica", ["parent_region_id"]),
    "hecho_relaciones": ("trg_hecho_relaciones__parte_de_aciclico", "fn_check_hecho_parte_de_aciclico",
                         ["hecho_destino_id", "hecho_origen_id", "tipo_relacion"]),
    "presupuestos": ("trg_presupuestos__cadena_sustitucion", "fn_check_cadena_sustitucion",
                     ["moneda", "owner_user_id", "periodo_desde", "periodo_hasta", "perspectiva",
                      "reemplaza_presupuesto_id", "version_presupuesto"]),
    "cierres_mensuales": ("trg_cierres_mensuales__cadena_sustitucion", "fn_check_cadena_sustitucion",
                          ["owner_user_id", "periodo_desde", "periodo_hasta", "reemplaza_cierre_id",
                           "version_cierre"]),
}

UNIQUE_0280 = {
    "uq_presupuestos__identidad_version":
        "UNIQUE (owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva, version_presupuesto)",
    "uq_presupuestos__reemplaza": "UNIQUE (reemplaza_presupuesto_id)",
    "uq_cierres_mensuales__reemplaza": "UNIQUE (reemplaza_cierre_id)",
}

ARBOLES = {  # rama de fn_check_jerarquia_aciclica -> clave del advisory lock
    "categorias_financieras": "CATEGORIAS",
    "clasificaciones_tercero": "CLASIFICACIONES",
    "inversiones": "INVERSIONES",
    "regiones": "REGIONES",
}

P = "c0320000-0000-4000-8000-0000000000"
OWNER, OWNER2 = P + "01", P + "02"
CUENTA = P + "0a"
C_A, C_B, C_C, C_D = P + "11", P + "12", P + "13", P + "14"
H_A, H_B, H_C, H_X = P + "21", P + "22", P + "23", P + "24"
M_A, M_B, M_C, M_D = P + "31", P + "32", P + "33", P + "34"
PR_1, PR_2, PR_3, PR_4 = P + "41", P + "42", P + "43", P + "44"
CI_1, CI_2, CI_3 = P + "51", P + "52", P + "53"
E_1, E_2 = P + "61", P + "62"
PAIS, R_1, R_2 = P + "71", P + "72", P + "73"
CL_1, CL_2 = P + "81", P + "82"

DIFERIDO = "D-123"


# ------------------------------------------------------------
# Montaje
# ------------------------------------------------------------

def _usuarios(cursor) -> None:
    for owner, nombre in ((OWNER, "c0320a"), (OWNER2, "c0320b")):
        cursor.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, %s)",
                       (owner, nombre + "@example.invalid", nombre))


def _contexto(cursor, owner: str = OWNER) -> None:
    cursor.execute("SET LOCAL ROLE gapto_owner")
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))


def _inmediato(cursor) -> None:
    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _validar_montaje(cursor) -> None:
    _inmediato(cursor)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")


class _Tx:
    """Transacción que siempre se revierte. Con rol=None se queda en el rol de
    conexión (BYPASSRLS en todos los entornos del proyecto)."""

    def __init__(self, db: psycopg.Connection, rol: str | None = "gapto_owner") -> None:
        self.db, self.rol = db, rol

    def __enter__(self):
        self.cursor = self.db.cursor()
        self.cursor.execute("BEGIN")
        _usuarios(self.cursor)
        if self.rol:
            _contexto(self.cursor)
        return self.cursor

    def __exit__(self, *exc) -> None:
        self.cursor.execute("ROLLBACK")
        self.cursor.execute("RESET ROLE")
        self.cursor.close()


def _rechaza(cursor, patron: str) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match=patron):
        _inmediato(cursor)


def _categoria(cursor, id_: str, padre: str | None = None, owner: str = OWNER) -> None:
    cursor.execute("INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
                   "presupuestable_default) VALUES (%s, %s, %s, %s, 'GASTO', true)",
                   (id_, owner, padre, "Cat " + id_[-2:]))


def _padre(cursor, tabla: str, col: str, id_: str, padre: str | None, pk: str = "id") -> None:
    cursor.execute(f"UPDATE gapto.{tabla} SET {col} = %s WHERE {pk} = %s", (padre, id_))


def _hecho(cursor, id_: str, owner: str = OWNER) -> None:
    cursor.execute("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
                   "concepto, moneda, estado_localizacion, presupuestable) "
                   "SELECT %s, %s, id, DATE '2026-03-01', 'Hecho C032', 'EUR', 'NO_APLICA', true "
                   "FROM gapto.tipos_hecho WHERE codigo = 'GASTO'", (id_, owner))


def _relacion(cursor, origen: str, destino: str, tipo: str = "PARTE_DE") -> None:
    cursor.execute("INSERT INTO gapto.hecho_relaciones (hecho_origen_id, hecho_destino_id, tipo_relacion) "
                   "VALUES (%s, %s, %s)", (origen, destino, tipo))


def _cuenta(cursor) -> None:
    cursor.execute("INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
                   "computa_liquidez, computa_patrimonio, permite_negativo) "
                   "VALUES (%s, %s, 'Cuenta C032', 'CORRIENTE', 'ACTIVO', 'EUR', true, true, false)",
                   (CUENTA, OWNER))


def _mov(cursor, id_: str, importe: str, reversion_de: str | None = None, estado: str = "ACTIVO") -> None:
    cursor.execute(
        "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, confirmado_at, "
        "clase_movimiento, estado, anulado_at, reversion_de_movimiento_id) "
        "VALUES (%s, %s, DATE '2026-03-01', %s, now(), 'OPERACION', %s, "
        "CASE WHEN %s = 'ANULADO' THEN now() END, %s)",
        (id_, CUENTA, Decimal(importe), estado, estado, reversion_de))


def _presupuesto(cursor, id_: str, version: int, reemplaza: str | None = None, *, moneda: str = "EUR",
                 perspectiva: str = "TOTAL", desde: str = "2026-01-01", hasta: str = "2026-12-31",
                 estado: str = "ACTIVO") -> None:
    cursor.execute("INSERT INTO gapto.presupuestos (id, owner_user_id, periodo_desde, periodo_hasta, moneda, "
                   "perspectiva, version_presupuesto, reemplaza_presupuesto_id, estado) "
                   "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                   (id_, OWNER, desde, hasta, moneda, perspectiva, version, reemplaza, estado))


def _cierre(cursor, id_: str, version: int, reemplaza: str | None = None, *, desde: str = "2026-01-01",
            hasta: str = "2026-01-31") -> None:
    cursor.execute("INSERT INTO gapto.cierres_mensuales (id, owner_user_id, periodo_desde, periodo_hasta, "
                   "cerrado_at, criterio, origen_cierre, metodologia_version, version_cierre, reemplaza_cierre_id) "
                   "VALUES (%s, %s, %s, %s, now(), 'CAJA', 'CALCULADO_2027', 'v1', %s, %s)",
                   (id_, OWNER, desde, hasta, version, reemplaza))


def _fuente(db: psycopg.Connection, funcion: str) -> str:
    with db.cursor() as cursor:
        cursor.execute("SELECT prosrc FROM pg_catalog.pg_proc WHERE proname = %s "
                       "AND pronamespace = 'gapto'::regnamespace", (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"falta {funcion}"
    return fila[0]


# ------------------------------------------------------------
# Contrato
# ------------------------------------------------------------

@pytest.mark.parametrize("funcion", sorted(HUELLAS_0280))
def test_0280_huella_y_atributos(db: psycopg.Connection, funcion: str) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT md5(p.prosrc), length(p.prosrc), p.prosecdef, p.provolatile, p.proconfig,
                   pg_catalog.pg_get_userbyid(p.proowner)
              FROM pg_catalog.pg_proc p
             WHERE p.pronamespace = 'gapto'::regnamespace AND p.proname = %s
        """, (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"{funcion} no existe"
    assert (fila[0], fila[1]) == HUELLAS_0280[funcion], f"{funcion}: huella {fila[:2]}"
    assert fila[2:] == (False, "v", None, "gapto_owner")
    assert "--" not in _fuente(db, funcion)


def test_0280_mecanismo_antiguo_eliminado(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_proc WHERE proname = 'fn_prevent_self_referencing_cycle'")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgname LIKE 'trg\\_%%\\_\\_no\\_ciclo'")
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize("tabla", sorted(TRIGGERS_0280))
def test_0280_trigger(db: psycopg.Connection, tabla: str) -> None:
    trigger, funcion, columnas = TRIGGERS_0280[tabla]
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname, t.tgconstraint <> 0, t.tgdeferrable, t.tginitdeferred, t.tgenabled, t.tgtype,
                   (SELECT array_agg(a.attname::text ORDER BY a.attname) FROM pg_catalog.pg_attribute a
                     WHERE a.attrelid = t.tgrelid AND a.attnum = ANY(t.tgattr))
              FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
             WHERE t.tgrelid = ('gapto.' || %s)::regclass AND t.tgname = %s
        """, (tabla, trigger))
        fila = cursor.fetchone()
    assert fila is not None, f"{tabla}: falta {trigger}"
    assert fila[:5] == (funcion, True, True, True, "O")
    assert fila[5] == 1 | 4 | 16, f"{trigger}: debe ser AFTER INSERT OR UPDATE FOR EACH ROW"
    assert fila[6] == columnas


@pytest.mark.parametrize("nombre", sorted(UNIQUE_0280))
def test_0280_unique(db: psycopg.Connection, nombre: str) -> None:
    with db.cursor() as cursor:
        cursor.execute("SELECT contype, convalidated, pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
                       "WHERE conname = %s", (nombre,))
        fila = cursor.fetchone()
    assert fila == ("u", True, UNIQUE_0280[nombre])


def test_0280_equivalencia_d115_de_los_cuatro_arboles(db: psycopg.Connection) -> None:
    """Las cuatro ramas comparten mecanismo: leer owner con NOT FOUND, advisory
    lock de clave (ARBOL, owner|GLOBAL), recorrido desde la fila ACTUAL con
    CYCLE. Justifica que C18-C20 (categorías) cubran los otros tres árboles."""
    texto = " ".join(_fuente(db, "fn_check_jerarquia_aciclica").split())
    for tabla, clave in ARBOLES.items():
        inicio = texto.index(f"TG_TABLE_NAME = '{tabla}'")
        siguiente = min([texto.index(f"TG_TABLE_NAME = '{t}'") for t in ARBOLES
                         if texto.index(f"TG_TABLE_NAME = '{t}'") > inicio] + [texto.index("ELSE RAISE")])
        rama = texto[inicio:siguiente]
        pasos = ["NOT FOUND", f"pg_advisory_xact_lock(hashtext('gapto:{clave}')", "WITH RECURSIVE",
                 "CYCLE n SET es_ciclo USING ruta", "SELECT EXISTS"]
        posiciones = [rama.index(p) for p in pasos]
        assert posiciones == sorted(posiciones), f"{tabla}: orden lock -> relectura -> CYCLE roto"
        assert "NEW.parent" not in rama and "NEW.inversion_padre" not in rama, f"{tabla}: confía en NEW"
    assert texto.count("pg_advisory_xact_lock") == 4
    assert "hashtext('GLOBAL')" in texto


def test_0280_cadenas_sin_cycle_y_con_lock(db: psycopg.Connection) -> None:
    """B.6: presupuestos y cierres no recorren la cadena; se apoyan en la
    monotonía de versión. El advisory lock se conserva."""
    texto = _fuente(db, "fn_check_cadena_sustitucion")
    assert "RECURSIVE" not in texto and "CYCLE" not in texto
    assert "hashtext('gapto:PRESUPUESTOS')" in texto and "hashtext('gapto:CIERRES')" in texto


# ------------------------------------------------------------
# Árboles
# ------------------------------------------------------------

def test_0280_arbol_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _categoria(cursor, C_A)
        _categoria(cursor, C_B, C_A)
        _categoria(cursor, C_C, C_B)
        _inmediato(cursor)


def test_0280_ciclo_de_dos(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _categoria(cursor, C_A)
        _categoria(cursor, C_B, C_A)
        _validar_montaje(cursor)
        _padre(cursor, "categorias_financieras", "parent_id", C_A, C_B)
        _rechaza(cursor, DIFERIDO)


def test_0280_ciclo_de_tres(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _categoria(cursor, C_A)
        _categoria(cursor, C_B, C_A)
        _categoria(cursor, C_C, C_B)
        _validar_montaje(cursor)
        _padre(cursor, "categorias_financieras", "parent_id", C_A, C_C)
        _rechaza(cursor, DIFERIDO)


def test_0280_estado_final_y_no_new(db: psycopg.Connection) -> None:
    """El primer UPDATE forma un ciclo y el segundo lo deshace: el estado final
    es válido y el evento del primero (con NEW.parent_id = B) no debe fallar."""
    with _Tx(db) as cursor:
        _categoria(cursor, C_A)
        _categoria(cursor, C_B, C_A)
        _validar_montaje(cursor)
        _padre(cursor, "categorias_financieras", "parent_id", C_A, C_B)
        _padre(cursor, "categorias_financieras", "parent_id", C_A, None)
        _inmediato(cursor)


def test_0280_ciclo_previo_no_cuelga_el_recorrido(db: psycopg.Connection) -> None:
    """Z cuelga de Y y después X<->Y forman un ciclo que no contiene a Z. El
    evento de Z se valida primero: su recorrido debe terminar (CYCLE); el
    evento de X detecta el ciclo."""
    with _Tx(db) as cursor:
        cursor.execute("SET LOCAL statement_timeout = '10s'")
        _categoria(cursor, C_A)
        _categoria(cursor, C_B, C_A)
        _validar_montaje(cursor)
        _categoria(cursor, C_C, C_B)
        _padre(cursor, "categorias_financieras", "parent_id", C_A, C_B)
        _rechaza(cursor, DIFERIDO)


def test_0280_contexto_cambiado_falla_visibilidad(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _categoria(cursor, C_A)
        _categoria(cursor, C_B)
        _validar_montaje(cursor)
        _padre(cursor, "categorias_financieras", "parent_id", C_B, C_A)
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER2,))
        _rechaza(cursor, "categorias_financieras: VISIBILIDAD")


def test_0280_clasificaciones_ciclo(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        for id_, padre in ((CL_1, None), (CL_2, CL_1)):
            cursor.execute("INSERT INTO gapto.clasificaciones_tercero (id, owner_user_id, parent_id, nombre) "
                           "VALUES (%s, %s, %s, 'Cl')", (id_, OWNER, padre))
        _validar_montaje(cursor)
        _padre(cursor, "clasificaciones_tercero", "parent_id", CL_1, CL_2)
        _rechaza(cursor, DIFERIDO)


def _inversion(cursor, entidad: str, padre: str | None = None) -> None:
    cursor.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'INVERSION', 'Inv')", (entidad, OWNER))
    cursor.execute("INSERT INTO gapto.inversiones (entidad_id, inversion_padre_entidad_id, rol_estructura, "
                   "tipo_producto, moneda, estado) VALUES (%s, %s, 'POSICION', 'FONDO', 'EUR', 'ACTIVA')",
                   (entidad, padre))


def test_0280_inversiones_ciclo(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _inversion(cursor, E_1)
        _inversion(cursor, E_2, E_1)
        _validar_montaje(cursor)
        _padre(cursor, "inversiones", "inversion_padre_entidad_id", E_1, E_2, pk="entidad_id")
        _rechaza(cursor, DIFERIDO)


def test_0280_regiones_ciclo(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        cursor.execute("INSERT INTO gapto.paises (id, iso2, iso3, nombre) VALUES (%s, 'QZ', 'QZQ', 'Pais C032')",
                       (PAIS,))
        cursor.execute("INSERT INTO gapto.regiones (id, pais_id, nombre) VALUES (%s, %s, 'R1')", (R_1, PAIS))
        cursor.execute("INSERT INTO gapto.regiones (id, pais_id, parent_region_id, nombre) "
                       "VALUES (%s, %s, %s, 'R2')", (R_2, PAIS, R_1))
        _validar_montaje(cursor)
        _padre(cursor, "regiones", "parent_region_id", R_1, R_2)
        _rechaza(cursor, DIFERIDO)


# ------------------------------------------------------------
# PARTE_DE
# ------------------------------------------------------------

def _hechos(cursor) -> None:
    for h in (H_A, H_B, H_C, H_X):
        _hecho(cursor, h)


def test_0280_parte_de_valido(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _relacion(cursor, H_B, H_C)
        _relacion(cursor, H_A, H_C)
        _inmediato(cursor)


def test_0280_parte_de_ciclo_de_dos(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _validar_montaje(cursor)
        _relacion(cursor, H_B, H_A)
        _rechaza(cursor, "ciclo PARTE_DE")


def test_0280_parte_de_ciclo_de_tres(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _relacion(cursor, H_B, H_C)
        _validar_montaje(cursor)
        _relacion(cursor, H_C, H_A)
        _rechaza(cursor, "ciclo PARTE_DE")


def test_0280_parte_de_cambio_de_tipo_a_parte_de(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _relacion(cursor, H_B, H_A, "CORRIGE_A")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_relaciones SET tipo_relacion = 'PARTE_DE' "
                       "WHERE hecho_origen_id = %s AND tipo_relacion = 'CORRIGE_A'", (H_B,))
        _rechaza(cursor, "ciclo PARTE_DE")


def test_0280_parte_de_a_otro_tipo_retira_la_arista(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_relaciones SET tipo_relacion = 'CORRIGE_A' WHERE hecho_origen_id = %s",
                       (H_A,))
        _relacion(cursor, H_B, H_A)
        _inmediato(cursor)


def test_0280_parte_de_cambio_de_extremo(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B)
        _relacion(cursor, H_C, H_X)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.hecho_relaciones SET hecho_destino_id = %s WHERE hecho_origen_id = %s",
                       (H_A, H_C))
        cursor.execute("UPDATE gapto.hecho_relaciones SET hecho_destino_id = %s WHERE hecho_origen_id = %s",
                       (H_C, H_A))
        _rechaza(cursor, "ciclo PARTE_DE")


def test_0280_parte_de_mismo_owner_tambien_con_bypassrls(db: psycopg.Connection) -> None:
    """Sin SET ROLE: rol de conexión con BYPASSRLS. La RLS no interviene; la
    invariante de mismo owner la impone el trigger."""
    with _Tx(db, rol=None) as cursor:
        _hecho(cursor, H_A)
        _hecho(cursor, H_B, OWNER2)
        _relacion(cursor, H_A, H_B)
        _rechaza(cursor, "mismo owner")


def test_0280_otros_tipos_no_tienen_aciclicidad(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _hechos(cursor)
        _relacion(cursor, H_A, H_B, "CORRIGE_A")
        _relacion(cursor, H_B, H_A, "CORRIGE_A")
        _inmediato(cursor)


# ------------------------------------------------------------
# Reversiones
# ------------------------------------------------------------

def _raiz(cursor) -> None:
    _cuenta(cursor)
    _mov(cursor, M_A, "-100")


def test_0280_reversiones_directas_validas(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _raiz(cursor)
        _mov(cursor, M_B, "40", M_A)
        _mov(cursor, M_C, "30", M_A)
        _inmediato(cursor)


def test_0280_reversion_de_una_reversion_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _raiz(cursor)
        _mov(cursor, M_B, "40", M_A)
        _validar_montaje(cursor)
        _mov(cursor, M_C, "-10", M_B)
        _rechaza(cursor, "profundidad 1")


def test_0280_reversion_anulada_tampoco_puede_apuntar_a_una_reversion(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _raiz(cursor)
        _mov(cursor, M_B, "40", M_A)
        _validar_montaje(cursor)
        _mov(cursor, M_C, "-10", M_B, estado="ANULADO")
        _rechaza(cursor, "profundidad 1")


def test_0280_reversion_mutua_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _cuenta(cursor)
        _mov(cursor, M_A, "-100")
        _mov(cursor, M_B, "100")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = %s WHERE id = %s",
                       (M_B, M_A))
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = %s WHERE id = %s",
                       (M_A, M_B))
        _rechaza(cursor, "profundidad 1")


def test_0280_movimiento_con_reversiones_no_pasa_a_reversion(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _raiz(cursor)
        _mov(cursor, M_B, "40", M_A, estado="ANULADO")
        _mov(cursor, M_D, "100")
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = %s WHERE id = %s",
                       (M_D, M_A))
        _rechaza(cursor, "tiene reversiones")


def test_0280_mover_y_quitar_una_reversion(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _raiz(cursor)
        _mov(cursor, M_D, "-100")
        _mov(cursor, M_B, "40", M_A)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = %s WHERE id = %s",
                       (M_D, M_B))
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.movimientos_tesoreria SET reversion_de_movimiento_id = NULL WHERE id = %s",
                       (M_B,))
        _mov(cursor, M_C, "-5", M_B)
        _inmediato(cursor)


def test_0280_d119_se_conserva(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _cuenta(cursor)
        _mov(cursor, M_A, "-100", estado="ANULADO")
        _validar_montaje(cursor)
        _mov(cursor, M_B, "40", M_A)
        _rechaza(cursor, "no puede apuntar al movimiento ANULADO")


# ------------------------------------------------------------
# Cadenas de sustitución
# ------------------------------------------------------------

def test_0280_presupuesto_version_mayor_con_hueco(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _presupuesto(cursor, PR_2, 5, PR_1, estado="BORRADOR")
        _presupuesto(cursor, PR_3, 9, PR_2)
        _inmediato(cursor)


@pytest.mark.parametrize("cambio", [{"desde": "2026-02-01"}, {"hasta": "2026-11-30"}, {"moneda": "USD"},
                                    {"perspectiva": "ATRIBUIBLE"}])
def test_0280_presupuesto_otra_identidad_se_rechaza(db: psycopg.Connection, cambio: dict) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _validar_montaje(cursor)
        _presupuesto(cursor, PR_2, 2, PR_1, **cambio)
        _rechaza(cursor, "mismo owner, periodo, moneda y perspectiva")


def test_0280_presupuesto_version_menor_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 2)
        _validar_montaje(cursor)
        _presupuesto(cursor, PR_2, 1, PR_1)
        _rechaza(cursor, "debe ser mayor")


def test_0280_presupuesto_version_igual_la_rechaza_la_unique(db: psycopg.Connection) -> None:
    """Con la identidad obligatoriamente igual, una versión igual es siempre
    una identidad versionada duplicada: la UNIQUE la rechaza antes que el
    trigger. Por eso el mutante '>' -> '>=' del trigger es equivalente."""
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 2)
        with pytest.raises(psycopg.errors.UniqueViolation, match="uq_presupuestos__identidad_version"):
            _presupuesto(cursor, PR_2, 2, PR_1)


def test_0280_presupuesto_bifurcacion_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _presupuesto(cursor, PR_2, 2, PR_1)
        with pytest.raises(psycopg.errors.UniqueViolation, match="uq_presupuestos__reemplaza"):
            _presupuesto(cursor, PR_3, 3, PR_1)


def test_0280_presupuesto_identidad_duplicada_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        with pytest.raises(psycopg.errors.UniqueViolation, match="uq_presupuestos__identidad_version"):
            _presupuesto(cursor, PR_2, 1)


def test_0280_presupuesto_update_intermedio_revalida_sucesor(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _presupuesto(cursor, PR_2, 4, PR_1)
        _presupuesto(cursor, PR_3, 8, PR_2)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.presupuestos SET version_presupuesto = 9 WHERE id = %s", (PR_2,))
        _rechaza(cursor, "del sucesor")


def test_0280_presupuesto_update_intermedio_revalida_predecesor(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 3)
        _presupuesto(cursor, PR_2, 4, PR_1)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.presupuestos SET version_presupuesto = 2 WHERE id = %s", (PR_2,))
        _rechaza(cursor, "del sustituido")


def test_0280_presupuesto_correccion_multifila(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _presupuesto(cursor, PR_2, 4, PR_1)
        _presupuesto(cursor, PR_3, 8, PR_2)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.presupuestos SET version_presupuesto = 9 WHERE id = %s", (PR_2,))
        cursor.execute("UPDATE gapto.presupuestos SET version_presupuesto = 12 WHERE id = %s", (PR_3,))
        cursor.execute("UPDATE gapto.presupuestos SET periodo_hasta = '2026-06-30' "
                       "WHERE id = ANY(%s::uuid[])", ([PR_1, PR_2, PR_3],))
        _inmediato(cursor)


def test_0280_presupuesto_cambio_de_dimension_revalida_sucesor(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _presupuesto(cursor, PR_1, 1)
        _presupuesto(cursor, PR_2, 2, PR_1)
        _validar_montaje(cursor)
        cursor.execute("UPDATE gapto.presupuestos SET moneda = 'USD' WHERE id = %s", (PR_1,))
        _rechaza(cursor, "debe conservar owner, periodo, moneda y perspectiva")


def test_0280_cierre_cadena(db: psycopg.Connection) -> None:
    with _Tx(db) as cursor:
        _cierre(cursor, CI_1, 2)
        _cierre(cursor, CI_2, 7, CI_1)
        _inmediato(cursor)
        with pytest.raises(psycopg.errors.UniqueViolation, match="uq_cierres_mensuales__reemplaza"):
            _cierre(cursor, CI_3, 9, CI_1)


@pytest.mark.parametrize("version,hasta,patron", [(1, "2026-01-31", "debe ser mayor"),
                                                   (5, "2026-02-28", "mismo owner y periodo")])
def test_0280_cierre_invalido(db: psycopg.Connection, version: int, hasta: str, patron: str) -> None:
    with _Tx(db) as cursor:
        _cierre(cursor, CI_1, 2)
        _validar_montaje(cursor)
        _cierre(cursor, CI_2, version, CI_1, hasta=hasta)
        _rechaza(cursor, patron)
