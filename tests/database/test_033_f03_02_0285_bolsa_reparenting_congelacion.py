# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_033_f03_02_0285_bolsa_reparenting_congelacion.py
# Ruta: tests/database/test_033_f03_02_0285_bolsa_reparenting_congelacion.py
# Descripción: Verifica la migration 0285 (FASE 03 / F03-02) en una sola
#              transacción por caso que siempre se revierte, sin residuo:
#              - D-121: predicado de solape BOLSA (categoría jerárquica x
#                naturaleza, entidad conservadora ent_compat=TRUE), prioridad
#                NOT NULL y distinta solo si hay solape; N2-1..N2-6; caso no
#                transitivo; tres BOLSAS que capturan el mismo efecto;
#                INDICADORES fuera del predicado; eventos presupuesto_id y
#                naturaleza_economica; revalidación tras reparenting.
#              - D-122 E(c): deriva semántica de alcances congelados (ACTIVO,
#                SUSTITUIDO, CERRADO), paso a paso e inmediata.
#              - F(a): congelación de líneas y alcances tras BORRADOR y no
#                retorno a BORRADOR.
#              - Same-owner de todo alcance, también sin RLS (simula
#                BYPASSRLS levantando FORCE RLS dentro de la transacción).
#              - owner_user_id inmutable en presupuestos, categorías y
#                entidades.
#              - Conservación de D-123 y de la cadena de sustitución de 0280.
#              Todo el montaje se hace con SET LOCAL ROLE gapto_owner y el
#              contexto de owner (D-137): no depende de privilegios propios
#              del rol de conexión.
# PRECONDICIÓN: requiere 0285.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import psycopg
import pytest

HUELLAS_0285 = {
    "fn_check_bolsa_prioridad": ("e34503a7cd0f87c1bbf9ee9b8a99d759", 4503),
    "fn_check_bolsa_prioridad_alcance": ("d1d83d6e38a15190244a26be50d90ad4", 3793),
    "fn_check_categoria_deriva": ("72985a925779006d2793f46050571a11", 2432),
    "fn_guard_presupuesto_congelado": ("8fa5efc1cc233552a75426aac93757e0", 2551),
    "fn_guard_presupuesto_estado": ("eee021d32006c62bbfa90d25fc9f7925", 274),
    "fn_guard_owner_inmutable": ("031660da8d1f4b783c06ab46ceb434a6", 194),
}

# tabla, trigger, eventos (I, D, U), columnas UPDATE OF, es_constraint, diferido, BEFORE, función
TRIGGERS_0285 = [
    ("presupuesto_lineas", "trg_presupuesto_lineas__bolsa_prioridad", (True, False, True),
     ["naturaleza_economica", "presupuesto_id", "prioridad_consumo", "tipo_linea"], True, True, False,
     "fn_check_bolsa_prioridad"),
    ("presupuesto_linea_alcances", "trg_presupuesto_linea_alcances__bolsa_prioridad", (True, False, True),
     [], True, True, False, "fn_check_bolsa_prioridad_alcance"),
    ("categorias_financieras", "trg_categorias_financieras__bolsa_reparenting", (False, False, True),
     ["parent_id"], True, True, False, "fn_check_bolsa_prioridad"),
    ("categorias_financieras", "trg_categorias_financieras__deriva_d122", (False, False, True),
     ["parent_id"], False, False, True, "fn_check_categoria_deriva"),
    ("presupuesto_lineas", "trg_presupuesto_lineas__congelacion", (True, True, True),
     [], False, False, True, "fn_guard_presupuesto_congelado"),
    ("presupuesto_linea_alcances", "trg_presupuesto_linea_alcances__congelacion", (True, True, True),
     [], False, False, True, "fn_guard_presupuesto_congelado"),
    ("presupuestos", "trg_presupuestos__no_retorno_borrador", (False, False, True),
     ["estado"], False, False, True, "fn_guard_presupuesto_estado"),
    ("presupuestos", "trg_presupuestos__owner_inmutable", (False, False, True),
     ["owner_user_id"], False, False, True, "fn_guard_owner_inmutable"),
    ("categorias_financieras", "trg_categorias_financieras__owner_inmutable", (False, False, True),
     ["owner_user_id"], False, False, True, "fn_guard_owner_inmutable"),
    ("entidades", "trg_entidades__owner_inmutable", (False, False, True),
     ["owner_user_id"], False, False, True, "fn_guard_owner_inmutable"),
]

P = "c0330000-0000-4000-8000-0000000000"
OWNER, OWNER2 = P + "01", P + "02"
# Árbol:  ALIM ─ SUPER ─ SUPER_H      OCIO ─ ACTIV ─ BUCEO ─ BUCEO_H
#         SEGURO                       DEPORTE
#         ALIM2 (owner 2)
ALIM, SUPER, SUPER_H, SEGURO = P + "11", P + "12", P + "13", P + "14"
OCIO, ACTIV, BUCEO, BUCEO_H, DEPORTE = P + "15", P + "16", P + "17", P + "18", P + "19"
ALIM2 = P + "1a"
E_ALLENDE, E_SAAVEDRA, E_OTRO = P + "21", P + "22", P + "23"
PR_1, PR_2, PR_3 = P + "31", P + "32", P + "33"
L_A, L_B, L_C, L_D = P + "41", P + "42", P + "43", P + "44"

D121 = "pueden capturar el mismo efecto"
DERIVA = "deriva semantica D-122"
CONGELADO = "queda congelado"
MISMO_OWNER = "mismo owner que el presupuesto"


# ------------------------------------------------------------
# Montaje
# ------------------------------------------------------------

def _contexto(cursor, owner: str = OWNER) -> None:
    cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))


def _inmediato(cursor) -> None:
    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _validar_montaje(cursor) -> None:
    _inmediato(cursor)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")


def _cat(cursor, id_: str, padre: str | None = None, owner: str = OWNER) -> None:
    cursor.execute("INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
                   "presupuestable_default) VALUES (%s, %s, %s, %s, 'AMBOS', true)",
                   (id_, owner, padre, "Cat " + id_[-2:]))


def _entidad(cursor, id_: str, owner: str = OWNER) -> None:
    cursor.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                   "VALUES (%s, %s, 'PROPIEDAD', %s)", (id_, owner, "Ent " + id_[-2:]))
    cursor.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad, incluir_en_rentabilidad) "
                   "VALUES (%s, 'VIVIENDA', true)", (id_,))


class _Tx:
    """Transacción como gapto_owner que siempre se revierte. Monta dos owners,
    un árbol de categorías y tres entidades. Con sin_rls=True levanta FORCE
    RLS de las tablas implicadas dentro de la transacción: gapto_owner, dueño
    de las tablas, deja de estar sujeto a RLS y simula BYPASSRLS."""

    TABLAS_RLS = ("presupuestos", "presupuesto_lineas", "presupuesto_linea_alcances",
                  "categorias_financieras", "entidades")

    def __init__(self, db: psycopg.Connection, sin_rls: bool = False) -> None:
        self.db, self.sin_rls = db, sin_rls

    def __enter__(self):
        c = self.cursor = self.db.cursor()
        c.execute("BEGIN")
        c.execute("SET LOCAL ROLE gapto_owner")
        for owner, nombre in ((OWNER2, "c0330b"), (OWNER, "c0330a")):
            _contexto(c, owner)
            c.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, %s)",
                      (owner, nombre + "@example.invalid", nombre))
        _contexto(c, OWNER2)
        _cat(c, ALIM2, owner=OWNER2)
        _entidad(c, E_OTRO, OWNER2)
        _validar_montaje(c)
        _contexto(c, OWNER)
        for id_, padre in ((ALIM, None), (SUPER, ALIM), (SUPER_H, SUPER), (SEGURO, None), (OCIO, None),
                           (ACTIV, OCIO), (BUCEO, ACTIV), (BUCEO_H, BUCEO), (DEPORTE, None)):
            _cat(c, id_, padre)
        _entidad(c, E_ALLENDE)
        _entidad(c, E_SAAVEDRA)
        _validar_montaje(c)
        if self.sin_rls:
            for tabla in self.TABLAS_RLS:
                c.execute(f"ALTER TABLE gapto.{tabla} NO FORCE ROW LEVEL SECURITY")
        return c

    def __exit__(self, *exc) -> None:
        self.cursor.execute("ROLLBACK")
        self.cursor.execute("RESET ROLE")
        self.cursor.close()


def _presupuesto(cursor, id_: str, estado: str = "BORRADOR", owner: str = OWNER, version: int = 1,
                 reemplaza: str | None = None, anio: int = 2026) -> None:
    cursor.execute("INSERT INTO gapto.presupuestos (id, owner_user_id, periodo_desde, periodo_hasta, moneda, "
                   "perspectiva, version_presupuesto, reemplaza_presupuesto_id, estado) "
                   "VALUES (%s, %s, make_date(%s, 1, 1), make_date(%s, 12, 31), 'EUR', 'TOTAL', %s, %s, %s)",
                   (id_, owner, anio, anio, version, reemplaza, estado))


def _linea(cursor, id_: str, presupuesto: str, prioridad: int | None, alcances: list[tuple] = (),
           tipo: str = "BOLSA", naturaleza: str = "GASTO") -> None:
    """alcances: lista de (categoria, entidad, incluir_descendientes)."""
    cursor.execute("INSERT INTO gapto.presupuesto_lineas (id, presupuesto_id, tipo_linea, naturaleza_economica, "
                   "prioridad_consumo, importe_objetivo, metodo_estimacion) "
                   "VALUES (%s, %s, %s, %s, %s, 100, 'MANUAL')", (id_, presupuesto, tipo, naturaleza, prioridad))
    for categoria, entidad, descendientes in alcances:
        _alcance(cursor, id_, categoria, entidad, descendientes)


def _alcance(cursor, linea: str, categoria: str | None, entidad: str | None = None,
             descendientes: bool = True) -> None:
    cursor.execute("INSERT INTO gapto.presupuesto_linea_alcances (presupuesto_linea_id, categoria_id, entidad_id, "
                   "incluir_descendientes) VALUES (%s, %s, %s, %s)", (linea, categoria, entidad, descendientes))


def _estado(cursor, presupuesto: str, estado: str) -> None:
    cursor.execute("UPDATE gapto.presupuestos SET estado = %s WHERE id = %s", (estado, presupuesto))


def _padre(cursor, categoria: str, padre: str | None) -> None:
    cursor.execute("UPDATE gapto.categorias_financieras SET parent_id = %s WHERE id = %s", (padre, categoria))


def _rechaza(cursor, patron: str) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match=patron):
        _inmediato(cursor)


def _rechaza_ya(cursor, patron: str, sql: str, params: tuple) -> None:
    """Rechazo inmediato (BEFORE) de una sentencia concreta."""
    with pytest.raises(psycopg.errors.RaiseException, match=patron):
        cursor.execute(sql, params)


def _dos_bolsas(cursor, a1: list[tuple], a2: list[tuple], p1: int | None, p2: int | None,
                n1: str = "GASTO", n2: str = "GASTO") -> None:
    _presupuesto(cursor, PR_1)
    _linea(cursor, L_A, PR_1, p1, a1, naturaleza=n1)
    _linea(cursor, L_B, PR_1, p2, a2, naturaleza=n2)


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

@pytest.mark.parametrize("funcion", sorted(HUELLAS_0285))
def test_0285_huella_y_atributos(db: psycopg.Connection, funcion: str) -> None:
    """Huella CURRENT de 0285 (Working Method 12C.5) y atributos de seguridad."""
    with db.cursor() as cursor:
        cursor.execute("SELECT md5(p.prosrc), length(p.prosrc), p.prosecdef, p.provolatile, p.proconfig, "
                       "pg_get_userbyid(p.proowner) FROM pg_catalog.pg_proc p "
                       "WHERE p.pronamespace = 'gapto'::regnamespace AND p.proname = %s", (funcion,))
        fila = cursor.fetchone()
    assert fila is not None, f"falta {funcion}"
    assert (fila[0], fila[1]) == HUELLAS_0285[funcion]
    assert fila[2:] == (False, "v", None, "gapto_owner")


@pytest.mark.parametrize("tabla,trigger,eventos,columnas,es_constraint,diferido,before,funcion", TRIGGERS_0285)
def test_0285_trigger(db: psycopg.Connection, tabla, trigger, eventos, columnas, es_constraint, diferido,
                      before, funcion) -> None:
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT (t.tgtype & 4) <> 0, (t.tgtype & 8) <> 0, (t.tgtype & 16) <> 0,
                   COALESCE((SELECT array_agg(a.attname::text ORDER BY a.attname)
                               FROM pg_catalog.pg_attribute a
                              WHERE a.attrelid = t.tgrelid AND a.attnum = ANY (t.tgattr)), '{}'),
                   t.tgconstraint <> 0, t.tginitdeferred, (t.tgtype & 2) <> 0, p.proname, t.tgenabled
              FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
             WHERE t.tgrelid = ('gapto.' || %s)::regclass AND t.tgname = %s
        """, (tabla, trigger))
        fila = cursor.fetchone()
    assert fila is not None, f"falta {trigger}"
    assert tuple(fila[:3]) == eventos
    assert list(fila[3]) == columnas
    assert (fila[4], fila[5], fila[6], fila[7], fila[8]) == (es_constraint, diferido, before, funcion, "O")


def test_0285_validadores_usan_advisory_categorias_y_no_for_update(db: psycopg.Connection) -> None:
    """Clave compartida (CATEGORIAS, owner) de 0280; sin FOR UPDATE nuevo."""
    for funcion in ("fn_check_bolsa_prioridad", "fn_check_bolsa_prioridad_alcance", "fn_check_categoria_deriva"):
        fuente = _fuente(db, funcion)
        assert "pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS')" in fuente, funcion
        assert "CYCLE" in fuente, funcion
    for funcion in HUELLAS_0285:
        assert " FOR UPDATE" not in _fuente(db, funcion).upper().replace("NO KEY UPDATE", ""), funcion
    assert "gapto:BOLSA" not in _fuente(db, "fn_check_bolsa_prioridad")


def test_0285_guard_congelacion_bloquea_y_relee_por_separado(db: psycopg.Connection) -> None:
    """F(a): lock root de fila -> espera -> LECTURA SQL SEPARADA -> validación.

    La comprobación de BORRADOR no puede hacerse en la misma sentencia que
    toma el lock: tras esperar hay que releer el estado en otra consulta. El
    guard tampoco adquiere advisory alguno, para no crear la topología
    advisory -> fila frente a fila -> advisory.
    """
    fuente = _fuente(db, "fn_guard_presupuesto_congelado")
    assert "pg_advisory" not in fuente
    lock = fuente.index("FROM gapto.presupuestos p\n      WHERE p.id = ANY (v_pres) ORDER BY p.id FOR NO KEY UPDATE")
    relectura = fuente.index("SELECT p.id, p.estado INTO v_id, v_estado")
    assert lock < relectura, "el estado se relee antes de tener el lock"
    assert "FOR NO KEY UPDATE" not in fuente[relectura:], "la relectura vuelve a bloquear en la misma sentencia"
    assert "p.estado <> 'BORRADOR'" in fuente[relectura:]
    # en alcances, las líneas se bloquean antes y su presupuesto se lee después
    bloqueo_lineas = fuente.index("FROM gapto.presupuesto_lineas l\n          WHERE l.id = ANY (v_lineas) ORDER BY l.id FOR NO KEY UPDATE")
    lectura_lineas = fuente.index("SELECT array_agg(DISTINCT l.presupuesto_id) INTO v_pres")
    assert bloqueo_lineas < lectura_lineas < lock


def test_0285_deriva_bloquea_presupuestos_antes_de_releer(db: psycopg.Connection) -> None:
    """D-122 E(c) bajo concurrencia: sin bloquear la fila de los presupuestos
    candidatos, una activación concurrente podría confirmarse entre la lectura
    del estado y el COMMIT del reparenting, y un presupuesto acabaría congelado
    con un alcance derivado. Se usa el mismo lock root de fila que F(a), no un
    advisory nuevo.

    Esta comprobación estática sustituye al caso concurrente C32 de test_027:
    ese caso exigiría dejar un presupuesto congelado CON línea y alcance, que
    es residuo imborrable por contrato (F(a) impide vaciarlo y la FK RESTRICT
    impide borrarlo). La topología de lock se demuestra dinámicamente en C30b
    (Working Method 12C.1).
    """
    fuente = _fuente(db, "fn_check_categoria_deriva")
    candidatos = fuente.index("INTO v_candidatos")
    lock = fuente.index("WHERE p.id = ANY (v_candidatos) ORDER BY p.id FOR NO KEY UPDATE")
    relectura = fuente.index("SELECT a.id, l.presupuesto_id INTO v_alcance, v_pres")
    assert candidatos < lock < relectura
    assert "p.estado <> 'BORRADOR'" in fuente[relectura:]
    assert "FOR NO KEY UPDATE" not in fuente[relectura:]


def test_0285_predicado_identico_en_los_dos_validadores(db: psycopg.Connection) -> None:
    """El predicado D-121 vive en dos funciones; debe ser el mismo texto."""
    def bloque(fuente: str) -> str:
        inicio = fuente.index("WITH RECURSIVE d(raiz, cat)")
        fin = fuente.index("LIMIT 1;", inicio)
        return " ".join(fuente[inicio:fin].split())
    assert bloque(_fuente(db, "fn_check_bolsa_prioridad")) == bloque(_fuente(db, "fn_check_bolsa_prioridad_alcance"))


# ------------------------------------------------------------
# D-121 — predicado de solape
# ------------------------------------------------------------

def test_0285_n2_1_categoria_frente_a_entidad_solapan(db: psycopg.Connection) -> None:
    """N2-1: (cat X, ent NULL) frente a (cat NULL, ent E) pueden capturar el mismo efecto."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(None, E_ALLENDE, True)], None, None)
        _rechaza(c, D121)


def test_0285_n2_1_con_prioridades_distintas_se_acepta(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(None, E_ALLENDE, True)], 1, 2)
        _inmediato(c)


def test_0285_n2_2_ramas_disjuntas_con_entidad_comun_no_solapan(db: psycopg.Connection) -> None:
    """N2-2: (X ∩ E) frente a (Y ∩ E) con X, Y en ramas disjuntas: 0280 lo
    rechazaba (falso positivo por la entidad común); 0285 lo acepta."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, E_ALLENDE, True)], [(OCIO, E_ALLENDE, True)], 1, 1)
        _inmediato(c)


def test_0285_n2_3_descendiente_solapa(db: psycopg.Connection) -> None:
    """N2-3: (Alimentación, true) frente a (Supermercados, false)."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, True)], [(SUPER, None, False)], 3, 3)
        _rechaza(c, D121)


def test_0285_n2_3_nieto_solapa(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, True)], [(SUPER_H, None, True)], 3, 3)
        _rechaza(c, D121)


def test_0285_n2_3_simetrico_desde_el_segundo_alcance(db: psycopg.Connection) -> None:
    """Rama (a2.desc y a1 descendiente de a2): el ancestro está en la línea de id mayor."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER_H, None, False)], [(ALIM, None, True)], 3, 3)
        _rechaza(c, D121)


def test_0285_sin_descendientes_frente_a_hijo_no_solapa(db: psycopg.Connection) -> None:
    """(X, false) frente a hijo(X): disjuntos."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, False)], [(SUPER, None, True)], 3, 3)
        _inmediato(c)


def test_0285_sin_descendientes_frente_a_la_misma_categoria_solapa(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, False)], [(ALIM, None, False)], 3, 3)
        _rechaza(c, D121)


def test_0285_hermanos_sin_relacion_no_solapan(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(SEGURO, None, True)], None, None)
        _inmediato(c)


def test_0285_n2_4_naturalezas_distintas_no_solapan(db: psycopg.Connection) -> None:
    """N2-4: misma cobertura categorial, GASTO frente a INGRESO."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, True)], [(ALIM, None, True)], 1, 1, "GASTO", "INGRESO")
        _inmediato(c)


def test_0285_n2_5_prioridad_null_con_solape_se_rechaza(db: psycopg.Connection) -> None:
    """N2-5: NULL no es 0 ni se ignora."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(SUPER, None, True)], None, None)
        _rechaza(c, D121)


def test_0285_n2_5_una_sola_prioridad_null_con_solape_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(SUPER, None, True)], 0, None)
        _rechaza(c, D121)


def test_0285_prioridad_null_sin_solape_se_acepta(db: psycopg.Connection) -> None:
    """D-121: no hay regla global BOLSA => prioridad NOT NULL."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(OCIO, None, True)], None, None)
        _linea(c, L_C, PR_1, None, [(SEGURO, None, True)])
        _inmediato(c)


def test_0285_n2_6_entidades_distintas_solapan(db: psycopg.Connection) -> None:
    """N2-6: (Seguro, Allende) frente a (Seguro, Saavedra): un efecto puede
    estar vinculado a ambas entidades."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SEGURO, E_ALLENDE, True)], [(SEGURO, E_SAAVEDRA, True)], 5, 5)
        _rechaza(c, D121)


def test_0285_n2_6_solo_entidades_distintas_solapan(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(None, E_ALLENDE, True)], [(None, E_SAAVEDRA, True)], None, None)
        _rechaza(c, D121)


def test_0285_n2_6_con_prioridades_distintas_se_acepta(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SEGURO, E_ALLENDE, True)], [(SEGURO, E_SAAVEDRA, True)], 5, 6)
        _inmediato(c)


def test_0285_no_transitivo_reutiliza_prioridad(db: psycopg.Connection) -> None:
    """A solapa B, B solapa C, A no solapa C: prio 1, 2, 1 es válido."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(SUPER, None, True)])
        _linea(c, L_B, PR_1, 2, [(SUPER, None, True), (OCIO, None, True)])
        _linea(c, L_C, PR_1, 1, [(OCIO, None, True)])
        _inmediato(c)


def test_0285_tres_bolsas_mismo_efecto_exigen_distintas_dos_a_dos(db: psycopg.Connection) -> None:
    """A, B, C capturan el mismo efecto: basta un empate para rechazar."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 2, [(SUPER, None, True)])
        _linea(c, L_C, PR_1, 1, [(None, E_ALLENDE, True)])
        _rechaza(c, D121)


def test_0285_tres_bolsas_mismo_efecto_distintas_se_acepta(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 2, [(SUPER, None, True)])
        _linea(c, L_C, PR_1, 3, [(None, E_ALLENDE, True)])
        _inmediato(c)


def test_0285_indicadores_no_participan(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)], tipo="INDICADOR")
        _linea(c, L_B, PR_1, None, [(ALIM, None, True)], tipo="INDICADOR")
        _linea(c, L_C, PR_1, None, [(ALIM, None, True)])
        _inmediato(c)


def test_0285_linea_sin_alcances_no_solapa(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, None, [])
        _linea(c, L_B, PR_1, None, [(ALIM, None, True)])
        _inmediato(c)


def test_0285_presupuestos_distintos_no_se_comparan(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, anio=2027)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)])
        _linea(c, L_B, PR_2, None, [(ALIM, None, True)])
        _inmediato(c)


def test_0285_d121_desde_el_alcance(db: psycopg.Connection) -> None:
    """La superficie de alcances detecta el solape que aparece al añadir un alcance."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(OCIO, None, True)], 1, 1)
        _validar_montaje(c)
        _alcance(c, L_B, SUPER_H, None, False)
        _rechaza(c, D121)


def test_0285_d121_desde_update_de_alcance(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, False)], [(SUPER_H, None, True)], 1, 1)
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_linea_alcances SET incluir_descendientes = true "
                  "WHERE presupuesto_linea_id = %s", (L_A,))
        _rechaza(c, D121)


def test_0285_d121_desde_prioridad(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _dos_bolsas(c, [(SUPER, None, True)], [(SUPER, None, True)], 1, 2)
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET prioridad_consumo = NULL WHERE id = %s", (L_B,))
        _rechaza(c, D121)


def test_0285_d121_desde_tipo_linea(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(SUPER, None, True)])
        _linea(c, L_B, PR_1, 1, [(SUPER, None, True)], tipo="INDICADOR")
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET tipo_linea = 'BOLSA' WHERE id = %s", (L_B,))
        _rechaza(c, D121)


def test_0285_evento_naturaleza_economica(db: psycopg.Connection) -> None:
    """UPDATE OF naturaleza_economica (evento que faltaba en 0280)."""
    with _Tx(db) as c:
        _dos_bolsas(c, [(ALIM, None, True)], [(ALIM, None, True)], 1, 1, "GASTO", "INGRESO")
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET naturaleza_economica = 'GASTO' WHERE id = %s", (L_B,))
        _rechaza(c, D121)


def test_0285_evento_presupuesto_id(db: psycopg.Connection) -> None:
    """UPDATE OF presupuesto_id (evento que faltaba en 0280): mover una BOLSA
    con alcance a un presupuesto BORRADOR donde crea un empate. Misma
    categoría exacta, para que el único mecanismo ausente en 0280 sea el
    evento."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, anio=2027)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_2, 1, [(ALIM, None, True)])
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET presupuesto_id = %s WHERE id = %s", (PR_1, L_B))
        _rechaza(c, D121)


def test_0285_retirar_linea_del_presupuesto_origen_no_exige_nada(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, anio=2027)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 2, [(SUPER, None, True)])
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET presupuesto_id = %s WHERE id = %s", (PR_2, L_B))
        _inmediato(c)


def test_0285_d121_se_mantiene_en_estados_congelados_por_reparenting(db: psycopg.Connection) -> None:
    """D(a): la invariante vale en todos los estados. Un reparenting que haría
    solapar dos BOLSAS de un BORRADOR también se rechaza (revalidación)."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 1, [(BUCEO, None, True)])
        _validar_montaje(c)
        _padre(c, BUCEO, ALIM)
        _rechaza(c, D121)


def test_0285_reparenting_revalida_por_jerarquia_final(db: psycopg.Connection) -> None:
    """Dos reparentings que dejan el árbol final sin solape se aceptan en BORRADOR."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 1, [(BUCEO, None, True)])
        _validar_montaje(c)
        _padre(c, BUCEO, ALIM)
        _padre(c, BUCEO, DEPORTE)
        _inmediato(c)


def test_0285_reparenting_de_otro_owner_no_revalida_este(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _linea(c, L_B, PR_1, 2, [(SUPER, None, True)])
        _validar_montaje(c)
        _contexto(c, OWNER2)
        _cat(c, P + "1b", ALIM2, OWNER2)
        _padre(c, P + "1b", None)
        _inmediato(c)


# ------------------------------------------------------------
# D-122 E(c) — deriva semántica
# ------------------------------------------------------------

def _congelado_con(c, estado: str, categoria: str, descendientes: bool = True, tipo: str = "BOLSA") -> None:
    _presupuesto(c, PR_1)
    _linea(c, L_A, PR_1, 1, [(categoria, None, descendientes)], tipo=tipo)
    _validar_montaje(c)
    if estado != "BORRADOR":
        _estado(c, PR_1, estado)


MOVER_BUCEO = ("UPDATE gapto.categorias_financieras SET parent_id = %s WHERE id = %s", (DEPORTE, BUCEO))


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSTITUIDO", "CERRADO"])
@pytest.mark.parametrize("tipo", ["BOLSA", "INDICADOR"])
def test_0285_deriva_ancestro_viejo_se_rechaza(db: psycopg.Connection, estado: str, tipo: str) -> None:
    """(Ocio, desc) congelado pierde Buceo: RECHAZAR (casos 1, 3, 4, 5)."""
    with _Tx(db) as c:
        _congelado_con(c, estado, OCIO, tipo=tipo)
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSTITUIDO", "CERRADO"])
def test_0285_deriva_ancestro_nuevo_se_rechaza(db: psycopg.Connection, estado: str) -> None:
    """(Deporte, desc) congelado ganaría Buceo: RECHAZAR (caso 2)."""
    with _Tx(db) as c:
        _congelado_con(c, estado, DEPORTE)
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)


def test_0285_deriva_ancestro_intermedio_se_rechaza(db: psycopg.Connection) -> None:
    """Actividades (padre directo antiguo) también pierde Buceo."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", ACTIV, tipo="INDICADOR")
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)


def test_0285_deriva_borrador_permitida(db: psycopg.Connection) -> None:
    """Caso 6: en BORRADOR la deriva está permitida si D-121 sigue válido."""
    with _Tx(db) as c:
        _congelado_con(c, "BORRADOR", OCIO)
        c.execute(*MOVER_BUCEO)
        _inmediato(c)


def test_0285_deriva_alcance_sobre_la_propia_categoria_no_cambia(db: psycopg.Connection) -> None:
    """Caso 7: (Buceo, desc) conserva Buceo y sus descendientes."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", BUCEO)
        c.execute(*MOVER_BUCEO)
        _inmediato(c)


def test_0285_deriva_alcance_sobre_descendiente_no_cambia(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _congelado_con(c, "CERRADO", BUCEO_H)
        c.execute(*MOVER_BUCEO)
        _inmediato(c)


def test_0285_deriva_sin_descendientes_no_cambia(db: psycopg.Connection) -> None:
    """Caso 8: (Ocio, false) solo significa Ocio."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO, descendientes=False)
        c.execute(*MOVER_BUCEO)
        _inmediato(c)


def test_0285_deriva_rama_no_referenciada_se_acepta(db: psycopg.Connection) -> None:
    """Caso 9."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", SEGURO)
        c.execute(*MOVER_BUCEO)
        _inmediato(c)


def test_0285_deriva_ancestro_comun_no_cambia(db: psycopg.Connection) -> None:
    """Mover Buceo de Actividades a Ocio: Ocio (ancestro común) conserva Buceo."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        _padre(c, BUCEO, OCIO)
        _inmediato(c)


def test_0285_deriva_mismo_padre_no_hace_nada(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        _padre(c, BUCEO, ACTIV)
        _inmediato(c)


def test_0285_deriva_convertir_en_raiz_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        _rechaza_ya(c, DERIVA, "UPDATE gapto.categorias_financieras SET parent_id = NULL WHERE id = %s", (BUCEO,))


def test_0285_intento_de_ciclo_termina_y_lo_rechaza_d123(db: psycopg.Connection) -> None:
    """Caso 10: sin congelados, el ciclo lo rechaza D-123 al validar y la
    lógica de deriva termina."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, 1, [(OCIO, None, True)])
        _validar_montaje(c)
        _padre(c, OCIO, BUCEO_H)
        _rechaza(c, "ciclo de jerarquia")


def test_0285_intento_de_ciclo_con_congelado_no_cuelga(db: psycopg.Connection) -> None:
    """Con un alcance congelado sobre un ancestro, la deriva rechaza en el paso y termina."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        c.execute("SET LOCAL statement_timeout = '5s'")
        _rechaza_ya(c, DERIVA, "UPDATE gapto.categorias_financieras SET parent_id = %s WHERE id = %s",
                    (BUCEO_H, ACTIV))


def test_0285_dos_reparentings_paso_a_paso(db: psycopg.Connection) -> None:
    """Caso 11: ir y volver se rechaza en el primer paso si ese paso altera
    semántica congelada, aunque el estado final coincidiera con el inicial."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", DEPORTE, descendientes=True)
        c.execute("SAVEPOINT s")
        _padre(c, BUCEO, OCIO)
        _padre(c, BUCEO, ACTIV)
        _inmediato(c)


def test_0285_dos_reparentings_segundo_paso_detectado(db: psycopg.Connection) -> None:
    """El primer paso es inocuo; el segundo (a Deporte) altera Deporte congelado."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", DEPORTE)
        _padre(c, BUCEO, OCIO)
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)


def test_0285_deriva_ida_y_vuelta_se_rechaza_en_la_ida(db: psycopg.Connection) -> None:
    """Semántica paso a paso: A -> B -> A con (Ocio, desc) congelado."""
    with _Tx(db) as c:
        _congelado_con(c, "ACTIVO", OCIO)
        c.execute("SAVEPOINT antes")
        _rechaza_ya(c, DERIVA, *MOVER_BUCEO)
        c.execute("ROLLBACK TO SAVEPOINT antes")
        _padre(c, BUCEO, ACTIV)
        _inmediato(c)


# ------------------------------------------------------------
# F(a) — congelación
# ------------------------------------------------------------

ESCRITURAS = {
    "insert_linea": ("INSERT INTO gapto.presupuesto_lineas (presupuesto_id, tipo_linea, naturaleza_economica, "
                     "prioridad_consumo, importe_objetivo, metodo_estimacion) "
                     "VALUES (%s, 'INDICADOR', 'GASTO', NULL, 1, 'MANUAL')", lambda: (PR_1,)),
    "update_linea": ("UPDATE gapto.presupuesto_lineas SET importe_objetivo = 7 WHERE id = %s", lambda: (L_A,)),
    "delete_linea": ("DELETE FROM gapto.presupuesto_lineas WHERE id = %s", lambda: (L_B,)),
    "insert_alcance": ("INSERT INTO gapto.presupuesto_linea_alcances (presupuesto_linea_id, categoria_id) "
                       "VALUES (%s, %s)", lambda: (L_A, SEGURO)),
    "update_alcance": ("UPDATE gapto.presupuesto_linea_alcances SET incluir_descendientes = false "
                       "WHERE presupuesto_linea_id = %s", lambda: (L_A,)),
    "delete_alcance": ("DELETE FROM gapto.presupuesto_linea_alcances WHERE presupuesto_linea_id = %s",
                       lambda: (L_A,)),
}


def _congelacion_montaje(c) -> None:
    _presupuesto(c, PR_1)
    _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
    _linea(c, L_B, PR_1, None, [])
    _validar_montaje(c)


@pytest.mark.parametrize("escritura", sorted(ESCRITURAS))
def test_0285_congelacion_borrador_acepta(db: psycopg.Connection, escritura: str) -> None:
    sql, params = ESCRITURAS[escritura]
    with _Tx(db) as c:
        _congelacion_montaje(c)
        c.execute(sql, params())
        _inmediato(c)


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSTITUIDO", "CERRADO"])
@pytest.mark.parametrize("escritura", sorted(ESCRITURAS))
def test_0285_congelacion_congelado_rechaza(db: psycopg.Connection, escritura: str, estado: str) -> None:
    sql, params = ESCRITURAS[escritura]
    with _Tx(db) as c:
        _congelacion_montaje(c)
        _estado(c, PR_1, estado)
        _rechaza_ya(c, CONGELADO, sql, params())


@pytest.mark.parametrize("origen,destino,acepta", [
    ("BORRADOR", "BORRADOR", True), ("ACTIVO", "BORRADOR", False), ("BORRADOR", "ACTIVO", False)])
def test_0285_congelacion_mover_linea(db: psycopg.Connection, origen: str, destino: str, acepta: bool) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, anio=2027)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)])
        _validar_montaje(c)
        for presupuesto, estado in ((PR_1, origen), (PR_2, destino)):
            if estado != "BORRADOR":
                _estado(c, presupuesto, estado)
        sql = "UPDATE gapto.presupuesto_lineas SET presupuesto_id = %s WHERE id = %s"
        if acepta:
            c.execute(sql, (PR_2, L_A))
            _inmediato(c)
        else:
            _rechaza_ya(c, CONGELADO, sql, (PR_2, L_A))


@pytest.mark.parametrize("origen,destino,acepta", [
    ("BORRADOR", "BORRADOR", True), ("ACTIVO", "BORRADOR", False), ("BORRADOR", "ACTIVO", False)])
def test_0285_congelacion_mover_alcance(db: psycopg.Connection, origen: str, destino: str, acepta: bool) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, anio=2027)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)])
        _linea(c, L_B, PR_2, None, [])
        _validar_montaje(c)
        for presupuesto, estado in ((PR_1, origen), (PR_2, destino)):
            if estado != "BORRADOR":
                _estado(c, presupuesto, estado)
        sql = "UPDATE gapto.presupuesto_linea_alcances SET presupuesto_linea_id = %s WHERE presupuesto_linea_id = %s"
        if acepta:
            c.execute(sql, (L_B, L_A))
            _inmediato(c)
        else:
            _rechaza_ya(c, CONGELADO, sql, (L_B, L_A))


def test_0285_activar_no_se_rechaza(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _congelacion_montaje(c)
        _estado(c, PR_1, "ACTIVO")
        _inmediato(c)


@pytest.mark.parametrize("desde", ["ACTIVO", "SUSTITUIDO", "CERRADO"])
def test_0285_no_retorno_a_borrador(db: psycopg.Connection, desde: str) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1, estado=desde)
        _rechaza_ya(c, "no puede volver a BORRADOR",
                    "UPDATE gapto.presupuestos SET estado = 'BORRADOR' WHERE id = %s", (PR_1,))


def test_0285_no_se_fijan_otras_transiciones(db: psycopg.Connection) -> None:
    """0285 no diseña una máquina de estados: ACTIVO -> CERRADO -> SUSTITUIDO
    no lo rechaza la congelación (solo el retorno a BORRADOR)."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1, estado="ACTIVO")
        _estado(c, PR_1, "CERRADO")
        _estado(c, PR_1, "SUSTITUIDO")
        _estado(c, PR_1, "ACTIVO")
        _inmediato(c)


def test_0285_version_nueva_borrador_editable(db: psycopg.Connection) -> None:
    """Flujo canónico: v1 ACTIVO congelado, v2 BORRADOR editable."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1, estado="BORRADOR")
        _linea(c, L_A, PR_1, 1, [(ALIM, None, True)])
        _validar_montaje(c)
        _estado(c, PR_1, "ACTIVO")
        _presupuesto(c, PR_2, version=2, reemplaza=PR_1)
        _linea(c, L_B, PR_2, 1, [(ALIM, None, True)])
        _alcance(c, L_B, SEGURO)
        _estado(c, PR_1, "SUSTITUIDO")
        _estado(c, PR_2, "ACTIVO")
        _inmediato(c)


# ------------------------------------------------------------
# Same-owner (H(b)) — también sin RLS
# ------------------------------------------------------------

def test_0285_same_owner_misma_categoria_se_acepta(db: psycopg.Connection) -> None:
    with _Tx(db, sin_rls=True) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, None, [(ALIM, E_ALLENDE, True)])
        _inmediato(c)


@pytest.mark.parametrize("tipo", ["BOLSA", "INDICADOR"])
@pytest.mark.parametrize("alcance", [(ALIM2, None), (None, E_OTRO), (ALIM, E_OTRO), (ALIM2, E_ALLENDE)])
def test_0285_same_owner_sin_rls(db: psycopg.Connection, tipo: str, alcance: tuple) -> None:
    """Categoría o entidad de otro owner, en BOLSA e INDICADOR, con RLS fuera
    de juego: lo rechaza el trigger, no la policy."""
    with _Tx(db, sin_rls=True) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, None, [], tipo=tipo)
        _alcance(c, L_A, alcance[0], alcance[1])
        _rechaza(c, MISMO_OWNER)


def test_0285_same_owner_mover_linea_a_otro_owner(db: psycopg.Connection) -> None:
    """Mover una línea con alcances revalida frente al presupuesto FINAL."""
    with _Tx(db, sin_rls=True) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, owner=OWNER2, anio=2027)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)], tipo="INDICADOR")
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_lineas SET presupuesto_id = %s WHERE id = %s", (PR_2, L_A))
        _rechaza(c, MISMO_OWNER)


def test_0285_same_owner_mover_alcance_a_linea_de_otro_owner(db: psycopg.Connection) -> None:
    with _Tx(db, sin_rls=True) as c:
        _presupuesto(c, PR_1)
        _presupuesto(c, PR_2, owner=OWNER2, anio=2027)
        _linea(c, L_A, PR_1, None, [(ALIM, None, True)], tipo="INDICADOR")
        _linea(c, L_B, PR_2, None, [], tipo="INDICADOR")
        _validar_montaje(c)
        c.execute("UPDATE gapto.presupuesto_linea_alcances SET presupuesto_linea_id = %s "
                  "WHERE presupuesto_linea_id = %s", (L_B, L_A))
        _rechaza(c, MISMO_OWNER)


def test_0285_same_owner_con_rls_la_policy_tambien_rechaza(db: psycopg.Connection) -> None:
    """Con RLS activa la policy ya lo impedía: no es la invariante, es una capa más."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _linea(c, L_A, PR_1, None, [], tipo="INDICADOR")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _alcance(c, L_A, ALIM2)


# ------------------------------------------------------------
# owner_user_id inmutable
# ------------------------------------------------------------

@pytest.mark.parametrize("tabla,id_", [("presupuestos", PR_1), ("categorias_financieras", SEGURO),
                                       ("entidades", E_ALLENDE)])
def test_0285_owner_inmutable(db: psycopg.Connection, tabla: str, id_: str) -> None:
    """Filas sin hijas ni referencias: en 0280 el cambio de owner prosperaba
    (la FK compuesta de parent_id solo lo impedía con hijas)."""
    with _Tx(db, sin_rls=True) as c:
        _presupuesto(c, PR_1)
        c.execute("SAVEPOINT s")
        _rechaza_ya(c, "owner_user_id es inmutable",
                    f"UPDATE gapto.{tabla} SET owner_user_id = %s WHERE id = %s", (OWNER2, id_))
        c.execute("ROLLBACK TO SAVEPOINT s")
        c.execute(f"UPDATE gapto.{tabla} SET owner_user_id = %s WHERE id = %s", (OWNER, id_))
        assert c.rowcount == 1
        _inmediato(c)


# ------------------------------------------------------------
# Conservación de 0280
# ------------------------------------------------------------

def test_0285_d123_se_conserva(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _padre(c, ALIM, SUPER_H)
        _rechaza(c, "ciclo de jerarquia")


def test_0285_cadena_de_sustitucion_se_conserva(db: psycopg.Connection) -> None:
    with _Tx(db) as c:
        _presupuesto(c, PR_1, estado="ACTIVO", version=2)
        _presupuesto(c, PR_2, version=1, reemplaza=PR_1)
        _rechaza(c, "debe ser mayor")


def test_0285_contexto_ausente_falla_visibilidad(db: psycopg.Connection) -> None:
    """Fail-closed (D-118): la congelación no puede ver el presupuesto."""
    with _Tx(db) as c:
        _presupuesto(c, PR_1)
        _contexto(c, OWNER2)
        with pytest.raises(psycopg.errors.RaiseException, match="VISIBILIDAD"):
            c.execute("INSERT INTO gapto.presupuesto_lineas (presupuesto_id, tipo_linea, naturaleza_economica, "
                      "importe_objetivo, metodo_estimacion) VALUES (%s, 'BOLSA', 'GASTO', 1, 'MANUAL')", (PR_1,))
