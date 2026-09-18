# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_041_f03_04_0320_delete_correccion_agregada.py
# Ruta: tests/database/test_041_f03_04_0320_delete_correccion_agregada.py
# Descripción: Verifica F03-04 / migration 0320 (D-182 + D-183 + D-186 §1/§4):
#              gapto_runtime recupera DELETE sobre las DOCE tablas hijas o
#              puente sin lifecycle propio, y ÚNICAMENTE sobre ellas.
#
#              DISCRIMINACIÓN. Contra 0310 fallan los bloques 1 y 6: allí las
#              doce no tienen DELETE y la matriz es 36. Contra un mutante que
#              conceda DELETE a hechos_financieros falla el bloque 2. Contra un
#              mutante que conceda por simetría al resto del Bucket A de B18
#              falla el bloque 3.
#
#              LO QUE NO SE PRUEBA AQUÍ Y NO ES UN OLVIDO. 0320 concede
#              capacidad física, no una API de borrado. El motivo obligatorio,
#              la atomicidad del comando de corrección y el snapshot
#              antes/después son garantías SRV/API de F04-06 (D-186 §4) y se
#              prueban allí, no contra el catálogo.
#
#              RIESGO DECLARADO QUE ESTE TEST HACE VISIBLE.
#              test_0320_riesgo_transferencia_declarado documenta que borrar
#              una fila de `transferencias` deja las dos patas ACTIVAS y
#              desemparejadas sin que ninguna constraint lo impida. No es un
#              fallo del contrato: es la razón por la que la corrección debe
#              ser atómica. Si algún día aparece una invariante que lo cubra,
#              este test debe cambiar junto con su decisión, nunca silenciarse.
#
#              COBERTURA gapto_runtime. El ACL solo demuestra el privilegio;
#              el camino real de la aplicación es gapto_runtime sin BYPASSRLS
#              y bajo FORCE ROW LEVEL SECURITY. Si el rol de conexión del arnés
#              no puede asumir gapto_runtime, esos tests SE SALTAN con mensaje
#              explícito, nunca en silencio (mismo criterio que test_038).
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER = "0320a000-0000-4000-8000-000000000001"

# D-183: las doce candidatas aprobadas. El orden es el de la decisión.
DOCE = (
    "hecho_efectos",
    "efecto_atribuciones",
    "hecho_aportaciones_pago",
    "hecho_movimientos_tesoreria",
    "inversion_asignaciones_efecto",
    "efecto_cuentas",
    "hecho_entidades",
    "hecho_participantes",
    "hecho_terceros",
    "hecho_magnitudes",
    "hecho_relaciones",
    "transferencias",
)

# Raíces con lifecycle ACTIVO/ANULADO: D-183 les niega el hard-delete y
# D-186 §1 confirma que OP-03 ya cubre el alta creada por error.
RAICES_SIN_DELETE = ("hechos_financieros", "movimientos_tesoreria")

# Resto del Bucket A de B18 (0200): snapshots y calendarios históricos. No se
# amplía por simetría.
SNAPSHOTS_SIN_DELETE = (
    "cierres_mensuales",
    "financiacion_cuotas",
    "inversion_valoraciones",
    "propiedad_valoraciones",
)

# B21 (0230): versionado e identidad. 0320 no los toca.
B21_SIN_DELETE = (
    "regla_versiones",
    "financiacion_condiciones_versiones",
    "contrato_revision_renta_versiones",
    "inversion_objetivos_versiones",
    "entidad_participaciones",
    "cuenta_participaciones",
    "contrato_participantes",
    "usuarios",
    "inversiones",
    "financiaciones",
    "derechos_obligaciones_financieras",
    "contratos",
    "documentos",
    "fuentes_importacion",
)

APPEND_ONLY = (
    "auditoria",
    "cierre_metricas",
    "cierre_posiciones_entidad",
    "cierre_presupuesto_lineas",
    "cierre_saldos_cuenta",
    "mapeos_importacion",
    "registros_origen_importacion",
)

CATALOGOS_GLOBALES = ("paises", "regiones", "localidades", "tipos_hecho", "metricas_definicion")

# Validadores que referencian NEW de forma incondicional: añadirles el evento
# DELETE abortaría con "record new is not assigned yet".
SIN_TRIGGER_DELETE = ("hecho_efectos", "hecho_aportaciones_pago", "hecho_relaciones", "transferencias")


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


def _priv(db: psycopg.Connection, rol: str, tabla: str, priv: str) -> bool:
    return _uno(db, "SELECT pg_catalog.has_table_privilege(%s, %s, %s)", (rol, f"gapto.{tabla}", priv))


def _cuenta(db: psycopg.Connection, rol: str, priv: str) -> int:
    return _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relkind='r'
           AND r.rolname=%s AND acl.privilege_type=%s
    """, (rol, priv))


def _asumir_runtime(db: psycopg.Connection) -> None:
    """Cambia a gapto_runtime conservando el contexto de tenant."""
    db.execute("SAVEPOINT antes_de_runtime")
    try:
        db.execute("RESET ROLE")
        db.execute("SET ROLE gapto_runtime")
    except psycopg.errors.InsufficientPrivilege:
        db.execute("ROLLBACK TO SAVEPOINT antes_de_runtime")
        pytest.skip(
            "El rol de conexión del arnés no puede asumir gapto_runtime: la "
            "cobertura de runtime de 0320 NO se ha ejercitado en esta ejecución."
        )


# ------------------------------------------------------------
# Bloque 1 — ACL completa de las doce
# ------------------------------------------------------------

@pytest.mark.parametrize("tabla", DOCE)
def test_0320_doce_con_acl_completa(db: psycopg.Connection, tabla: str) -> None:
    """D-150: se verifica el ACL esperado COMPLETO, no solo la ausencia."""
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _priv(db, "gapto_runtime", tabla, priv) is True, (
            f"{tabla} debe tener {priv} tras 0320"
        )


@pytest.mark.parametrize("tabla", DOCE)
def test_0320_doce_sin_privilegios_de_mas(db: psycopg.Connection, tabla: str) -> None:
    """Exactamente cuatro: un TRUNCATE o un REFERENCES colados serían un
    desbordamiento silencioso del alcance aprobado."""
    total = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relname=%s AND r.rolname='gapto_runtime'
    """, (tabla,))
    assert total == 4, f"{tabla}: gapto_runtime tiene {total} privilegios, esperados 4"


# ------------------------------------------------------------
# Bloque 2 — las raíces conservan su lifecycle
# ------------------------------------------------------------

@pytest.mark.parametrize("tabla", RAICES_SIN_DELETE)
def test_0320_raices_siguen_sin_delete(db: psycopg.Connection, tabla: str) -> None:
    """D-183: una raíz con ACTIVO/ANULADO no recupera hard-delete. D-186 §1:
    OP-03 ya cubre el hecho que nunca debió existir."""
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is False
    for priv in ("SELECT", "INSERT", "UPDATE"):
        assert _priv(db, "gapto_runtime", tabla, priv) is True


def test_0320_las_raices_conservan_su_columna_de_estado(db: psycopg.Connection) -> None:
    """Justificación viva de la exclusión anterior: si una raíz perdiera su
    lifecycle, la razón para negarle DELETE desaparecería y habría que
    revisar D-183, nunca silenciar este test."""
    con_estado = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
               AND a.attnum > 0 AND NOT a.attisdropped AND a.attname = 'estado'
         WHERE c.relnamespace = 'gapto'::regnamespace AND c.relname = ANY(%s)
    """, (list(RAICES_SIN_DELETE),))
    assert con_estado == 2


# ------------------------------------------------------------
# Bloque 3 — no se amplía por simetría
# ------------------------------------------------------------

@pytest.mark.parametrize("tabla", SNAPSHOTS_SIN_DELETE + B21_SIN_DELETE + APPEND_ONLY)
def test_0320_fuera_de_alcance_sigue_denegado(db: psycopg.Connection, tabla: str) -> None:
    assert _priv(db, "gapto_runtime", tabla, "DELETE") is False, (
        f"{tabla} está fuera del alcance de D-183 y no debía ganar DELETE"
    )


@pytest.mark.parametrize("tabla", CATALOGOS_GLOBALES)
def test_0320_catalogos_globales_intactos(db: psycopg.Connection, tabla: str) -> None:
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert _priv(db, "gapto_runtime", tabla, priv) is False


def test_0320_documento_vinculos_sin_grant_redundante(db: psycopg.Connection) -> None:
    """D-183: ya tenía DELETE desde 0130; 0320 no le añade nada. Sigue con
    exactamente cuatro privilegios."""
    total = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relname='documento_vinculos'
           AND r.rolname='gapto_runtime'
    """)
    assert total == 4
    assert _priv(db, "gapto_runtime", "documento_vinculos", "DELETE") is True


# ------------------------------------------------------------
# Bloque 4 — las FK RESTRICT siguen siendo la barrera
# ------------------------------------------------------------

def test_0320_fk_entrantes_siguen_restrict(db: psycopg.Connection) -> None:
    """El orden de retirada no es una recomendación: lo impone la FK. Si
    alguna pasara a CASCADE, un borrado arrastraría realidad en silencio."""
    no_restrict = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class ref ON ref.oid = k.confrelid
         WHERE k.contype='f' AND ref.relnamespace = 'gapto'::regnamespace
           AND ref.relname = ANY(%s) AND k.confdeltype <> 'r'
    """, (list(DOCE),))
    assert no_restrict == 0, "alguna FK entrante a las doce ha dejado de ser RESTRICT"


def test_0320_hecho_efectos_conserva_sus_cinco_fk_entrantes(db: psycopg.Connection) -> None:
    total = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class ref ON ref.oid = k.confrelid
         WHERE k.contype='f' AND ref.relnamespace='gapto'::regnamespace
           AND ref.relname='hecho_efectos'
    """)
    assert total == 5


# ------------------------------------------------------------
# Bloque 5 — las invariantes diferidas no se han tocado
# ------------------------------------------------------------

def test_0320_no_crea_ni_modifica_triggers(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
    """) == 58
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
           AND t.tgconstraint <> 0
    """) == 41


@pytest.mark.parametrize("tabla", SIN_TRIGGER_DELETE)
def test_0320_no_anade_evento_delete_a_validadores_con_new(db: psycopg.Connection, tabla: str) -> None:
    """fn_check_aportaciones_conciliacion y fn_check_transferencia_estructura
    usan NEW incondicionalmente. Extenderlas a DELETE por simetría abortaría
    con 'record new is not assigned yet'."""
    con_delete = _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
           AND c.relname=%s AND (t.tgtype & 8) = 8
    """, (tabla,))
    assert con_delete == 0


def test_0320_los_cuatro_validadores_que_si_cubren_delete(db: psycopg.Connection) -> None:
    """La seguridad del bloque descansa en que estas cuatro superficies sigan
    revalidando en DELETE."""
    tablas = _uno(db, """
        SELECT count(DISTINCT c.relname) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
           AND (t.tgtype & 8) = 8
           AND c.relname = ANY(ARRAY['efecto_atribuciones','hecho_entidades',
                                     'hecho_movimientos_tesoreria',
                                     'inversion_asignaciones_efecto'])
    """)
    assert tablas == 4


# ------------------------------------------------------------
# Bloque 6 — matriz efectiva y contrato no movido
# ------------------------------------------------------------

def test_0320_matriz_efectiva_de_runtime(db: psycopg.Connection) -> None:
    """SELECT 80 / INSERT 74 / UPDATE 68 / DELETE 48.

    Si este número cambia, alguien ha movido la política de borrado. Debe
    actualizarse aquí y en la documentación canónica, nunca silenciarse.
    """
    assert _cuenta(db, "gapto_runtime", "SELECT") == 80
    assert _cuenta(db, "gapto_runtime", "INSERT") == 74
    assert _cuenta(db, "gapto_runtime", "UPDATE") == 68
    assert _cuenta(db, "gapto_runtime", "DELETE") == 48


def test_0320_es_acl_puro(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_attribute a
          JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
         WHERE c.relnamespace='gapto'::regnamespace AND c.relkind='r'
           AND a.attnum > 0 AND NOT a.attisdropped
    """) == 772
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_indexes WHERE schemaname='gapto'") == 285
    assert _uno(db, "SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'") == 82
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_proc WHERE pronamespace='gapto'::regnamespace
    """) == 28


def test_0320_no_afecta_a_owner_ni_backup(db: psycopg.Connection) -> None:
    assert _priv(db, "gapto_owner", "hechos_financieros", "DELETE") is True
    assert _cuenta(db, "gapto_backup", "SELECT") == 80
    for priv in ("INSERT", "UPDATE", "DELETE"):
        assert _cuenta(db, "gapto_backup", priv) == 0


# ------------------------------------------------------------
# Bloque 7 — comportamiento real bajo gapto_runtime
# ------------------------------------------------------------

class Escenario:
    """Hecho GASTO de 100 con un efecto y una atribución completa."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        db.execute(
            "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0320') "
            "ON CONFLICT DO NOTHING", (OWNER, f"{uuid.uuid4()}@example.invalid"))
        self.actor = str(uuid.uuid4())
        db.execute(
            "INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)",
            (self.actor, OWNER))
        tipo = _uno(db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        self.hecho = str(uuid.uuid4())
        db.execute(
            "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, "
            "fecha_hecho, concepto, importe_total, moneda, estado_localizacion, presupuestable) "
            "VALUES (%s, %s, %s, CURRENT_DATE, '0320', '100.0000', 'EUR', 'NO_APLICA', true)",
            (self.hecho, OWNER, tipo))
        self.efecto = str(uuid.uuid4())
        db.execute(
            "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
            "estado_atribucion) VALUES (%s, %s, 'GASTO', '100.0000', 'COMPLETA')",
            (self.efecto, self.hecho))
        self.atribucion = str(uuid.uuid4())
        db.execute(
            "INSERT INTO gapto.efecto_atribuciones (id, efecto_id, actor_id, "
            "importe_atribuido, criterio_atribucion) "
            "VALUES (%s, %s, %s, '100.0000', 'MANUAL')",
            (self.atribucion, self.efecto, self.actor))

    def evaluar(self) -> None:
        self.db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.db.execute("SET CONSTRAINTS ALL DEFERRED")


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


@pytest.mark.parametrize("tabla", DOCE)
def test_runtime_delete_no_lanza_42501(db: psycopg.Connection, tabla: str) -> None:
    """Prueba efectiva del privilegio, no lectura del ACL. Sin filas: lo
    relevante es que no aborte por privilegio insuficiente."""
    db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    _asumir_runtime(db)
    with db.cursor() as cur:
        cur.execute(f"DELETE FROM gapto.{tabla} WHERE id = %s", (str(uuid.uuid4()),))
        assert cur.rowcount == 0
    db.rollback()


@pytest.mark.parametrize("tabla", RAICES_SIN_DELETE)
def test_runtime_delete_raiz_sigue_denegado(db: psycopg.Connection, tabla: str) -> None:
    db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
    _asumir_runtime(db)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(f"DELETE FROM gapto.{tabla} WHERE id = %s", (str(uuid.uuid4()),))
    db.rollback()


def test_runtime_delete_respeta_el_aislamiento_tenant(esc: Escenario) -> None:
    """Con el contexto de OTRO tenant la fila no es visible: cero filas
    afectadas, no excepción. RLS sigue gobernando el DELETE porque la policy
    es FOR ALL y su USING aplica también al borrado."""
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)",
                   ("0320a000-0000-4000-8000-0000000000ff",))
    _asumir_runtime(esc.db)
    with esc.db.cursor() as cur:
        cur.execute("DELETE FROM gapto.efecto_atribuciones WHERE id = %s", (esc.atribucion,))
        assert cur.rowcount == 0
    esc.db.rollback()


def test_runtime_delete_bloqueado_por_fk_restrict(esc: Escenario) -> None:
    """No se puede retirar el efecto mientras tenga hijas: 23503, no un
    estado inválido."""
    _asumir_runtime(esc.db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        esc.db.execute("DELETE FROM gapto.hecho_efectos WHERE id = %s", (esc.efecto,))
    esc.db.rollback()


def test_runtime_delete_en_orden_correcto_confirma(esc: Escenario) -> None:
    """Retirada completa en el orden que imponen las FK. El validador de
    atribuciones hace CONTINUE cuando el efecto ya no existe, de modo que la
    evaluación diferida no falsea un error de visibilidad."""
    _asumir_runtime(esc.db)
    esc.db.execute("DELETE FROM gapto.efecto_atribuciones WHERE id = %s", (esc.atribucion,))
    esc.db.execute("DELETE FROM gapto.hecho_efectos WHERE id = %s", (esc.efecto,))
    esc.evaluar()
    assert _uno(esc.db, "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s", (esc.efecto,)) == 0
    esc.db.rollback()


def test_runtime_delete_no_rompe_un_efecto_completa(esc: Escenario) -> None:
    """Fail-closed conservado: retirar la atribución dejando vivo un efecto
    COMPLETA descuadra la suma y se rechaza en la evaluación diferida."""
    _asumir_runtime(esc.db)
    esc.db.execute("DELETE FROM gapto.efecto_atribuciones WHERE id = %s", (esc.atribucion,))
    with pytest.raises(psycopg.errors.RaiseException) as err:
        esc.evaluar()
    assert "COMPLETA" in str(err.value), str(err.value)
    esc.db.rollback()


def test_0320_riesgo_transferencia_declarado(db: psycopg.Connection) -> None:
    """RIESGO ACEPTADO Y VISIBLE. `transferencias` no tiene trigger en DELETE
    y su borrado deja las dos patas ACTIVAS y desemparejadas. Ninguna
    constraint lo impide: la protección es la atomicidad del agregado en
    F04-06. Este test fija el estado conocido; si algún día aparece una
    garantía física, debe cambiar con su decisión, no silenciarse.
    """
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
           AND c.relname='transferencias' AND (t.tgtype & 8) = 8
    """) == 0
    # Tampoco tiene owner_user_id ni row_version: el write-path debe bloquear
    # los dos movimientos, no la fila.
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_attribute a
          JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
         WHERE c.relnamespace='gapto'::regnamespace AND c.relname='transferencias'
           AND a.attnum > 0 AND NOT a.attisdropped
           AND a.attname IN ('owner_user_id','row_version')
    """) == 0
