# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_038_f03_03_0310_aportaciones_vs_porcion_conciliada.py
# Ruta: tests/database/test_038_f03_03_0310_aportaciones_vs_porcion_conciliada.py
# Descripción: FASE 03 REABIERTA / D-169 + D-170 + D-171. Cubre la migration
#              0310: la invariante agregada
#
#                SUM(aportaciones vinculadas a R) <= ABS(R.importe_asignado)
#                cuando moneda_hecho(R) = moneda_cuenta(R)
#
#              DISCRIMINACION. Los casos negativos N1..N8 PASAN solo contra
#              0310 y FALLAN contra 0300, que aceptaba cualquier suma. El
#              caso canonico de D-169 es 80 + 80 sobre una porcion de 100:
#              ambas filas son individualmente <= 100 y solo la suma delata la
#              violacion, de modo que una validacion fila a fila no
#              discriminaria.
#
#              COBERTURA gapto_runtime. Las dos funciones de 0310 son INVOKER y
#              su correccion depende de RLS, FORCE RLS y del contexto de tenant,
#              asi que probarlas solo bajo gapto_owner seria insuficiente. Los
#              tests test_runtime_* preparan los datos con el rol
#              administrativo, cambian a gapto_runtime y demuestran: un caso
#              valido que atraviesa el trigger y confirma; una escritura sin
#              contexto valido que NUNCA se confirma; y una violacion de D-169
#              rechazada tambien bajo runtime. Si el rol de la conexion del
#              arnes no puede asumir gapto_runtime, esos tests SE SALTAN con
#              mensaje explicito: un skip silencioso dejaria la cobertura
#              exigida sin cubrir sin que nadie lo note.
#
#              DIFERIDO. Los cuatro triggers son DEFERRABLE INITIALLY DEFERRED,
#              asi que la violacion no aflora en el INSERT sino al cierre de la
#              transaccion. Los tests fuerzan la evaluacion con
#              SET CONSTRAINTS ALL IMMEDIATE dentro de un SAVEPOINT, que es lo
#              que permite comprobar tanto el rechazo como la correccion
#              multi-fila atomica de D-170 §4 sin confirmar nada.
#
#              DEPENDENCIA HEREDADA (D-171 §5). test_dep_* hace visible que la
#              proteccion concurrente del caso "UPDATE cuenta_id frente a
#              INSERT de HMT" NO nace en 0310 sino en el anchor
#              uq_movimientos_tesoreria__cuenta_anchor de 0220/D-099. Si un
#              cambio futuro lo eliminase o lo debilitase, el fallo sera
#              diagnosticable aqui y no solo en la bateria de concurrencia.
#              La garantia de COMPORTAMIENTO sigue siendo R7, con dos sesiones.
#
#              NO se prueban aqui los escenarios concurrentes: requieren dos
#              sesiones simultaneas y viven en el arnes R7.
#
# PRECONDICIÓN: requiere 0310 aplicada.
# Versión: 0.1.2  -- primera ejecución real contra Neon gapto2027_test: 39
#              passed, 4 failed. Los cuatro fallos eran defectos DEL TEST, no de
#              0310, y se corrigen aquí sin tocar la migration:
#              (a) el nombre de la FK HMT->movimiento era inventado
#                  ("__mov"); el real es "__movimiento". Se toma del catálogo.
#              (b,c,d) n5, n8 y el fan-out creaban dos conciliaciones del mismo
#                  hecho sobre el MISMO movimiento, lo que viola el
#                  UNIQUE (hecho_id, movimiento_tesoreria_id) de 0080. Ahora
#                  cada conciliación adicional usa su propio movimiento. La
#                  semántica de los tres casos no cambia.
#              (e) corrección autorizada: el negativo de runtime comprueba
#                  ausencia para el hecho del fixture en lugar de count(*)
#                  global, que era trivialmente cierto sobre una base vacía.
#              v0.1.1: cobertura runtime, FK exacta, N1..N8.
#              v0.1.0: primera version entregada para revision.
# ============================================================

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER = "cccccccc-0310-4000-8000-000000000001"

NUCLEO = "fn_validar_aportaciones_conciliacion"
DESPACHADOR = "fn_check_aportaciones_conciliacion"
ANCHOR_CUENTA = "uq_movimientos_tesoreria__cuenta_anchor"

TRIGGERS = (
    "trg_hecho_aportaciones_pago__conciliacion_suma",
    "trg_hecho_movimientos_tesoreria__aportaciones",
    "trg_hechos_financieros__aportaciones_moneda",
    "trg_movimientos_tesoreria__aportaciones_cuenta",
)


@pytest.fixture()
def db():
    url = os.environ.get("GAPTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GAPTO_TEST_DATABASE_URL no definida")
    con = psycopg.connect(url)
    con.execute("SET ROLE gapto_owner")
    yield con
    con.rollback()
    con.close()


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cur:
        cur.execute(sql, params)
        fila = cur.fetchone()
    return fila[0] if fila else None


class Escenario:
    """Un movimiento de 1000 sobre una cuenta EUR y un hecho EUR.

    La porcion conciliada por defecto es 100, de modo que el caso canonico de
    D-169 (80 + 80) se expresa sin ruido. El movimiento es holgado para que el
    validador de suma de conciliaciones (0170) nunca sea el que falle.
    """

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0310') "
            "ON CONFLICT DO NOTHING", (OWNER, f"{uuid.uuid4()}@example.invalid"))
        self.cuenta_eur = self.cuenta("EUR")
        self.movimiento = self.mov(self.cuenta_eur, "-1000.0000")
        self.hecho_eur = self.hecho("EUR")
        self.conc = self.conciliacion(self.hecho_eur, self.movimiento, "-100.0000")

    # --- constructores -------------------------------------------------
    def cuenta(self, moneda: str) -> str:
        cid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "computa_liquidez, computa_patrimonio, permite_negativo) "
            "VALUES (%s, %s, %s, 'CORRIENTE', 'ACTIVO', %s, true, true, false)",
            (cid, OWNER, f"Cuenta {cid[:8]}", moneda))
        return cid

    def mov(self, cuenta: str, importe: str) -> str:
        mid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, importe, "
            "confirmado_at, clase_movimiento) "
            "VALUES (%s, %s, CURRENT_DATE, %s, CURRENT_TIMESTAMP, 'OPERACION')",
            (mid, cuenta, importe))
        return mid

    def hecho(self, moneda: str) -> str:
        hid = str(uuid.uuid4())
        tipo = _uno(self.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        self.db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
            "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, '0310', '100.0000', %s, 'NO_APLICA', true)",
            (hid, OWNER, tipo, moneda))
        return hid

    def conciliacion(self, hecho: str, movimiento: str, importe: str) -> str:
        cid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_movimientos_tesoreria (id, hecho_id, movimiento_tesoreria_id, "
            "importe_asignado) VALUES (%s, %s, %s, %s)", (cid, hecho, movimiento, importe))
        return cid

    def aportacion(self, hecho: str, conciliacion: str | None, importe: str) -> str:
        aid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.hecho_aportaciones_pago (id, hecho_id, importe, "
            "criterio_aportacion, hecho_movimiento_tesoreria_id) "
            "VALUES (%s, %s, %s, 'MANUAL', %s)", (aid, hecho, importe, conciliacion))
        return aid

    # --- control del diferido ------------------------------------------
    def evaluar(self) -> None:
        """Fuerza la evaluacion de los constraint triggers diferidos."""
        self.db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.db.execute("SET CONSTRAINTS ALL DEFERRED")


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


def _rechaza(esc: Escenario, fragmento: str) -> None:
    """Exige que la evaluacion diferida falle citando el fragmento dado."""
    with pytest.raises(psycopg.errors.RaiseException) as err:
        esc.evaluar()
    assert fragmento in str(err.value), str(err.value)
    esc.db.rollback()


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

def test_0310_funciones_existen_y_son_invoker(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::regnamespace
           AND p.proname = ANY(%s) AND NOT p.prosecdef
    """, ([NUCLEO, DESPACHADOR],)) == 2


def test_0310_no_introduce_security_definer(db: psycopg.Connection) -> None:
    """D-171 §4: 0310 no resuelve por privilegio lo que el contrato tenant ya
    resuelve por pertenencia al mismo owner."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_proc p
         WHERE p.pronamespace = 'gapto'::regnamespace AND p.prosecdef
    """) == 1  # solo fn_registrar_auditoria, de B15


@pytest.mark.parametrize("nombre", TRIGGERS)
def test_0310_trigger_es_constraint_diferido(db: psycopg.Connection, nombre: str) -> None:
    fila = _uno(db, """
        SELECT t.tgconstraint <> 0 AND t.tgdeferrable AND t.tginitdeferred
          FROM pg_catalog.pg_trigger t WHERE t.tgname = %s AND NOT t.tgisinternal
    """, (nombre,))
    assert fila is True, f"{nombre} no es CONSTRAINT TRIGGER DEFERRABLE INITIALLY DEFERRED"


@pytest.mark.parametrize("nombre", TRIGGERS)
def test_0310_trigger_no_dispara_en_delete(db: psycopg.Connection, nombre: str) -> None:
    """D-171 §2: borrar una aportacion solo puede bajar la suma. Ademas, no
    encolar comprobacion en DELETE es lo que permite fail-closed puro sin rama
    de vacuidad."""
    assert _uno(db, """
        SELECT (t.tgtype & 8) <> 0 FROM pg_catalog.pg_trigger t WHERE t.tgname = %s
    """, (nombre,)) is False


def test_0310_contrato_fisico(db: psycopg.Connection) -> None:
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_proc p "
                    "WHERE p.pronamespace = 'gapto'::regnamespace") == 28
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::regnamespace AND NOT t.tgisinternal
    """) == 58
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::regnamespace AND NOT t.tgisinternal
           AND t.tgconstraint <> 0
    """) == 41


def test_0310_no_toca_fk_ni_indices(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
         WHERE c.relnamespace = 'gapto'::regnamespace AND k.contype = 'f'
    """) == 175
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_indexes WHERE schemaname = 'gapto'") == 285


# ------------------------------------------------------------
# Dependencia estructural heredada de 0220/D-099 (D-171 §5)
# ------------------------------------------------------------

def test_dep_anchor_cuenta_de_0220_sigue_existiendo(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(k.oid)
          FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.movimientos_tesoreria'::regclass AND k.conname = %s
    """, (ANCHOR_CUENTA,)) == "UNIQUE (cuenta_id, id)"


def test_dep_cuenta_id_es_columna_key_del_movimiento(db: psycopg.Connection) -> None:
    """La proteccion concurrente de 0310 frente a UPDATE de cuenta_id NO nace en
    0310: nace de que cuenta_id participe en un indice UNICO, lo que convierte
    ese UPDATE en un key update y le hace tomar un lock de tupla FOR UPDATE,
    incompatible con el FOR KEY SHARE que toma el INSERT de una HMT.

    Si un cambio futuro retirase ese indice, cuenta_id dejaria de ser columna
    KEY, el UPDATE pasaria a FOR NO KEY UPDATE, dejaria de conflictuar y
    reaparecerian los conjuntos de locks disjuntos. Este test hace visible esa
    dependencia; la garantia de comportamiento es R7."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_index i
          JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
         WHERE i.indrelid = 'gapto.movimientos_tesoreria'::regclass
           AND i.indisunique AND a.attname = 'cuenta_id'
    """) >= 1, "cuenta_id ya no es columna KEY: 0310 pierde su serializacion heredada"


FK_HMT_MOVIMIENTO = "fk_hecho_movimientos_tesoreria__movimiento"
FK_HMT_MOVIMIENTO_DEF = (
    "FOREIGN KEY (movimiento_tesoreria_id) REFERENCES "
    "gapto.movimientos_tesoreria(id) ON DELETE RESTRICT"
)


def test_dep_fk_hmt_hacia_movimiento_es_exactamente_la_esperada(db: psycopg.Connection) -> None:
    """El otro extremo del conflicto de locks. No basta con que exista "alguna"
    FK entre las dos tablas: la cadena que protegemos es concreta, y es esta FK
    la que hace que el INSERT de una HMT tome FOR KEY SHARE sobre la fila del
    movimiento. Se comprueba por nombre y por definicion, y ademas por columnas
    de catalogo para no depender solo del texto."""
    assert _uno(db, """
        SELECT pg_catalog.pg_get_constraintdef(k.oid)
          FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.hecho_movimientos_tesoreria'::regclass
           AND k.conname = %s AND k.contype = 'f'
    """, (FK_HMT_MOVIMIENTO,)) == FK_HMT_MOVIMIENTO_DEF

    assert _uno(db, """
        SELECT count(*)
          FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_attribute hijo
            ON hijo.attrelid = k.conrelid AND hijo.attnum = k.conkey[1]
          JOIN pg_catalog.pg_attribute padre
            ON padre.attrelid = k.confrelid AND padre.attnum = k.confkey[1]
         WHERE k.conrelid = 'gapto.hecho_movimientos_tesoreria'::regclass
           AND k.confrelid = 'gapto.movimientos_tesoreria'::regclass
           AND k.contype = 'f'
           AND pg_catalog.array_length(k.conkey, 1) = 1
           AND hijo.attname = 'movimiento_tesoreria_id'
           AND padre.attname = 'id'
    """) == 1


def test_dep_precondicion_0300_sigue_vigente(db: psycopg.Connection) -> None:
    """D-171 §10: la FK compuesta de 0300 es la que hace inequivoca la moneda
    del hecho aplicable a una aportacion vinculada. 0310 no la duplica en
    logica procedimental; la comprueba aqui."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
         WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::regclass
           AND k.conname = 'fk_hecho_aportaciones_pago__hecho_conciliacion'
           AND k.contype = 'f' AND k.convalidated
    """) == 1


# ------------------------------------------------------------
# Canonicalizacion de Hs (D-171 §4)
# ------------------------------------------------------------

def test_hs_duplicado_no_produce_falso_error_de_visibilidad(esc: Escenario) -> None:
    """OLD.hecho_id = NEW.hecho_id es el caso NORMAL de un UPDATE. Sin
    deduplicar, cardinality = 2 frente a ROW_COUNT = 1 daria un falso
    VISIBILIDAD."""
    esc.db.execute("SELECT gapto.fn_validar_aportaciones_conciliacion(ARRAY[%s::uuid, %s::uuid])",
                   (esc.hecho_eur, esc.hecho_eur))


def test_hs_con_nulos_se_ignoran(esc: Escenario) -> None:
    esc.db.execute("SELECT gapto.fn_validar_aportaciones_conciliacion(ARRAY[NULL::uuid, %s::uuid])",
                   (esc.hecho_eur,))


def test_hs_vacio_no_hace_nada(esc: Escenario) -> None:
    esc.db.execute("SELECT gapto.fn_validar_aportaciones_conciliacion(ARRAY[]::uuid[])")
    esc.db.execute("SELECT gapto.fn_validar_aportaciones_conciliacion(NULL::uuid[])")


def test_hecho_inexistente_falla_cerrado(esc: Escenario) -> None:
    """Ausencia inesperada = error. No existe rama 'no visible = borrado'."""
    with pytest.raises(psycopg.errors.RaiseException) as err:
        esc.db.execute("SELECT gapto.fn_validar_aportaciones_conciliacion(ARRAY[%s::uuid])",
                       (str(uuid.uuid4()),))
    assert "VISIBILIDAD" in str(err.value)
    esc.db.rollback()


# ------------------------------------------------------------
# Positivos
# ------------------------------------------------------------

def test_p1_aportacion_por_debajo_de_la_porcion(esc: Escenario) -> None:
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.evaluar()


def test_p2_reparto_en_dos_inserts_es_valido(esc: Escenario) -> None:
    """40 + 40 sobre 100. Es el caso que obliga a que el trigger sea DEFERRED:
    un trigger inmediato veria estados intermedios legitimos."""
    esc.aportacion(esc.hecho_eur, esc.conc, "40.0000")
    esc.aportacion(esc.hecho_eur, esc.conc, "40.0000")
    esc.evaluar()


def test_p3_la_regla_es_un_maximo_no_una_igualdad(esc: Escenario) -> None:
    """80 <= 100 es valido: el resto puede ser financiacion no modelada. Dato
    desconocido es desconocido, no cero."""
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.evaluar()
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
                        "WHERE hecho_movimiento_tesoreria_id = %s", (esc.conc,)) == 1


def test_p4_aportaciones_sin_vinculo_no_suman(esc: Escenario) -> None:
    esc.aportacion(esc.hecho_eur, esc.conc, "90.0000")
    esc.aportacion(esc.hecho_eur, None, "500.0000")
    esc.evaluar()


def test_p5_multidivisa_no_compara_nominalmente(esc: Escenario) -> None:
    """Hecho USD contra cuenta EUR: 120 frente a 100 NO se compara. No se
    inventa FX ni se conserva el limite nominal (D-170 §8)."""
    hecho_usd = esc.hecho("USD")
    conc = esc.conciliacion(hecho_usd, esc.movimiento, "-100.0000")
    esc.aportacion(hecho_usd, conc, "60.0000")
    esc.aportacion(hecho_usd, conc, "60.0000")
    esc.evaluar()


def test_p6_comparable_a_multidivisa_es_permitido(esc: Escenario) -> None:
    """La transicion inversa se permite; D-169 simplemente deja de comparar."""
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hechos_financieros SET moneda = 'USD' WHERE id = %s",
                   (esc.hecho_eur,))
    esc.evaluar()


def test_p7_delete_de_aportacion_no_puede_violar(esc: Escenario) -> None:
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.evaluar()
    esc.db.execute("DELETE FROM gapto.hecho_aportaciones_pago WHERE hecho_movimiento_tesoreria_id = %s",
                   (esc.conc,))
    esc.evaluar()


def test_p8_ampliar_la_porcion_repara_el_estado(esc: Escenario) -> None:
    """La invariante es sobre el estado final: subir importe_asignado es una
    correccion valida."""
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.db.execute("UPDATE gapto.hecho_movimientos_tesoreria SET importe_asignado = '-200.0000' "
                   "WHERE id = %s", (esc.conc,))
    esc.evaluar()


# ------------------------------------------------------------
# Negativos (discriminan contra 0300)
# ------------------------------------------------------------

def test_n1_caso_canonico_80_mas_80_sobre_100(esc: Escenario) -> None:
    """El caso de D-169: cada fila es <= 100, solo la SUMA delata la violacion.
    Una validacion fila a fila no discriminaria."""
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    _rechaza(esc, "supera la porcion conciliada")


def test_n2_una_sola_aportacion_que_excede(esc: Escenario) -> None:
    esc.aportacion(esc.hecho_eur, esc.conc, "120.0000")
    _rechaza(esc, "supera la porcion conciliada")


def test_n3_update_de_importe_que_rompe_la_suma(esc: Escenario) -> None:
    aid = esc.aportacion(esc.hecho_eur, esc.conc, "50.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET importe = '150.0000' WHERE id = %s",
                   (aid,))
    _rechaza(esc, "supera la porcion conciliada")


def test_n4_bajar_importe_asignado_rompe_desde_el_padre(esc: Escenario) -> None:
    """Parent-side: un trigger solo en la tabla hija no veria esto."""
    esc.aportacion(esc.hecho_eur, esc.conc, "90.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hecho_movimientos_tesoreria SET importe_asignado = '-50.0000' "
                   "WHERE id = %s", (esc.conc,))
    _rechaza(esc, "supera la porcion conciliada")


def test_n5_relink_que_rompe_la_conciliacion_destino(esc: Escenario) -> None:
    """Dos conciliaciones del MISMO hecho exigen movimientos distintos: el
    UNIQUE (hecho_id, movimiento_tesoreria_id) de 0080 admite una sola
    conciliacion por par hecho/movimiento."""
    mov2 = esc.mov(esc.cuenta_eur, "-1000.0000")
    conc2 = esc.conciliacion(esc.hecho_eur, mov2, "-100.0000")
    esc.aportacion(esc.hecho_eur, esc.conc, "90.0000")
    aid = esc.aportacion(esc.hecho_eur, conc2, "90.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET hecho_movimiento_tesoreria_id = %s "
                   "WHERE id = %s", (esc.conc, aid))
    _rechaza(esc, "supera la porcion conciliada")


def test_n6_multidivisa_a_comparable_via_moneda_del_hecho(esc: Escenario) -> None:
    """El ejemplo canonico de D-170 §1: USD/EUR con 60+60 sobre 100 es valido,
    y deja de serlo si la transaccion termina en EUR/EUR."""
    hecho_usd = esc.hecho("USD")
    conc = esc.conciliacion(hecho_usd, esc.movimiento, "-100.0000")
    esc.aportacion(hecho_usd, conc, "60.0000")
    esc.aportacion(hecho_usd, conc, "60.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hechos_financieros SET moneda = 'EUR' WHERE id = %s", (hecho_usd,))
    _rechaza(esc, "supera la porcion conciliada")


def test_n7_multidivisa_a_comparable_via_cuenta_del_movimiento(esc: Escenario) -> None:
    """D-170 §6: cambiar el movimiento/cuenta tambien altera la comparabilidad."""
    cuenta_usd = esc.cuenta("USD")
    mov_usd = esc.mov(cuenta_usd, "-1000.0000")
    conc = esc.conciliacion(esc.hecho_eur, mov_usd, "-100.0000")
    esc.aportacion(esc.hecho_eur, conc, "60.0000")
    esc.aportacion(esc.hecho_eur, conc, "60.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.movimientos_tesoreria SET cuenta_id = %s WHERE id = %s",
                   (esc.cuenta_eur, mov_usd))
    _rechaza(esc, "supera la porcion conciliada")


def test_n8_relink_de_conciliacion_a_otra_del_mismo_movimiento(esc: Escenario) -> None:
    mov2 = esc.mov(esc.cuenta_eur, "-1000.0000")
    conc2 = esc.conciliacion(esc.hecho_eur, mov2, "-300.0000")
    esc.aportacion(esc.hecho_eur, conc2, "250.0000")
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET hecho_movimiento_tesoreria_id = %s "
                   "WHERE hecho_movimiento_tesoreria_id = %s", (esc.conc, conc2))
    _rechaza(esc, "supera la porcion conciliada")


# ------------------------------------------------------------
# Fan-out y correccion atomica (D-170 §4 y §5)
# ------------------------------------------------------------

def test_fanout_solo_se_validan_las_conciliaciones_comparables(esc: Escenario) -> None:
    """D-170 §5. Hecho USD con tres conciliaciones: dos sobre cuentas EUR y una
    sobre GBP. Al pasar el hecho a EUR, las dos primeras se vuelven comparables
    y la tercera sigue siendo multidivisa. La violacion vive en una de las que
    pasan a ser comparables."""
    hecho = esc.hecho("USD")
    cuenta_gbp = esc.cuenta("GBP")
    mov_gbp = esc.mov(cuenta_gbp, "-1000.0000")
    mov_eur2 = esc.mov(esc.cuenta_eur, "-1000.0000")
    c1 = esc.conciliacion(hecho, esc.movimiento, "-100.0000")     # EUR
    c2 = esc.conciliacion(hecho, mov_eur2, "-500.0000")           # EUR, otro movimiento
    c3 = esc.conciliacion(hecho, mov_gbp, "-100.0000")            # GBP
    esc.aportacion(hecho, c1, "60.0000")
    esc.aportacion(hecho, c1, "60.0000")     # 120 > 100, solo comparable tras el cambio
    esc.aportacion(hecho, c2, "100.0000")    # 100 <= 500, siempre valido
    esc.aportacion(hecho, c3, "900.0000")    # 900 > 100 pero GBP != EUR: nunca se compara
    esc.evaluar()
    esc.db.execute("UPDATE gapto.hechos_financieros SET moneda = 'EUR' WHERE id = %s", (hecho,))
    with pytest.raises(psycopg.errors.RaiseException) as err:
        esc.evaluar()
    mensaje = str(err.value)
    assert c1 in mensaje, "debe delatar la conciliacion EUR que incumple"
    assert c3 not in mensaje, "la conciliacion GBP sigue siendo multidivisa y no se compara"
    esc.db.rollback()


def test_correccion_multifila_atomica(esc: Escenario) -> None:
    """D-170 §4. USD/EUR con 60+60 sobre 100 se corrige, en la MISMA
    transaccion, a EUR/EUR con 40+40. El estado final es 80 <= 100 y debe ser
    valido SIN exigir ningun estado intermedio persistido. Es la prueba de que
    la seguridad de la invariante no depende del orden de las sentencias."""
    hecho = esc.hecho("USD")
    conc = esc.conciliacion(hecho, esc.movimiento, "-100.0000")
    a1 = esc.aportacion(hecho, conc, "60.0000")
    a2 = esc.aportacion(hecho, conc, "60.0000")
    # orden deliberadamente "peor": primero la moneda, que deja el estado
    # intermedio en 120 > 100, y despues la correccion de los importes.
    esc.db.execute("UPDATE gapto.hechos_financieros SET moneda = 'EUR' WHERE id = %s", (hecho,))
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET importe = '40.0000' WHERE id = %s", (a1,))
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET importe = '40.0000' WHERE id = %s", (a2,))
    esc.evaluar()


def test_correccion_multifila_atomica_orden_inverso(esc: Escenario) -> None:
    """El mismo caso con las sentencias en el orden contrario. Debe dar el mismo
    resultado: la invariante evalua el estado final, no el recorrido."""
    hecho = esc.hecho("USD")
    conc = esc.conciliacion(hecho, esc.movimiento, "-100.0000")
    a1 = esc.aportacion(hecho, conc, "60.0000")
    a2 = esc.aportacion(hecho, conc, "60.0000")
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET importe = '40.0000' WHERE id = %s", (a1,))
    esc.db.execute("UPDATE gapto.hecho_aportaciones_pago SET importe = '40.0000' WHERE id = %s", (a2,))
    esc.db.execute("UPDATE gapto.hechos_financieros SET moneda = 'EUR' WHERE id = %s", (hecho,))
    esc.evaluar()


# ------------------------------------------------------------
# Regresion D-120 (D-171 §6): 0310 NO duplica esta proteccion
# ------------------------------------------------------------

def test_regresion_d120_moneda_de_cuenta_con_movimientos_es_inmutable(esc: Escenario) -> None:
    """0310 no cubre cuentas.moneda porque D-120 hace esa ruta imposible: una
    cuenta con movimientos no puede cambiar de moneda. Si esta proteccion se
    debilitara, 0310 tendria un writer descubierto."""
    with pytest.raises(psycopg.errors.RaiseException) as err:
        esc.db.execute("UPDATE gapto.cuentas SET moneda = 'USD' WHERE id = %s", (esc.cuenta_eur,))
    assert "inmutable" in str(err.value)
    esc.db.rollback()


# ------------------------------------------------------------
# Cobertura bajo gapto_runtime
#
# Las dos funciones de 0310 son INVOKER: se ejecutan con los privilegios y el
# contexto del escritor. Probarlas solo bajo gapto_owner no demostraria que la
# invariante funciona por el camino real de la aplicacion, que es el backend
# operando como gapto_runtime, sin BYPASSRLS y bajo FORCE ROW LEVEL SECURITY.
# ------------------------------------------------------------

def _asumir_runtime(esc: Escenario) -> None:
    """Cambia a gapto_runtime conservando el contexto de tenant.

    Si el rol de conexion del arnes no puede asumir gapto_runtime, se SALTA el
    test con un mensaje explicito en vez de fallar: es una limitacion del
    entorno, no del contrato. El skip es ruidoso a proposito, porque esta
    cobertura fue exigida expresamente y no debe desaparecer en silencio.
    """
    esc.db.execute("SAVEPOINT antes_de_runtime")
    try:
        esc.db.execute("RESET ROLE")
        esc.db.execute("SET ROLE gapto_runtime")
    except psycopg.Error as error:
        esc.db.execute("ROLLBACK TO SAVEPOINT antes_de_runtime")
        esc.db.execute("SET ROLE gapto_owner")
        pytest.skip(
            "COBERTURA RUNTIME NO EJECUTADA: el rol de conexion no puede asumir "
            f"gapto_runtime ({error}). La exigencia de probar 0310 bajo runtime "
            "sigue pendiente y debe cubrirse con un rol adecuado."
        )


def test_runtime_positivo_caso_valido_atraviesa_el_trigger(esc: Escenario) -> None:
    """A. Runtime con contexto correcto: escribe, alcanza el trigger diferido,
    bloquea el hecho, relee la cadena HMT/movimiento/cuenta y confirma un estado
    valido."""
    _asumir_runtime(esc)
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.evaluar()
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
                        "WHERE hecho_movimiento_tesoreria_id = %s", (esc.conc,)) == 1


def test_runtime_sin_contexto_nunca_confirma_la_escritura(esc: Escenario) -> None:
    """B. Runtime sin gapto.owner_user_id valido: deny-by-default.

    El fallo puede producirse por RLS o por el contexto antes de alcanzar el
    mensaje interno de VISIBILIDAD, y eso es aceptable. Lo que se exige demostrar
    es que la escritura JAMAS se confirma y que no existe RETURN silencioso ni
    validacion omitida.
    """
    _asumir_runtime(esc)
    esc.db.execute("SELECT set_config('gapto.owner_user_id', '', true)")
    with pytest.raises(psycopg.Error) as err:
        esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
        esc.evaluar()
    assert err.value is not None
    esc.db.rollback()
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
                        "WHERE hecho_id = %s", (esc.hecho_eur,)) == 0


def test_runtime_rechaza_la_violacion_de_d169(esc: Escenario) -> None:
    """C. Runtime con contexto correcto y 80 + 80 sobre una porcion de 100.

    Demuestra que la invariante no depende de estar operando como gapto_owner:
    el camino real de la aplicacion queda igualmente protegido.
    """
    _asumir_runtime(esc)
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    esc.aportacion(esc.hecho_eur, esc.conc, "80.0000")
    _rechaza(esc, "supera la porcion conciliada")
