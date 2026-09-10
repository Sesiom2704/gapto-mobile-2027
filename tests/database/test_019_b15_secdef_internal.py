# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_019_b15_secdef_internal.py
# Ruta: tests/database/test_019_b15_secdef_internal.py
# Descripción: Verifica F03-01-B15: el writer interno de auditoría
#              gapto.fn_registrar_auditoria (SECURITY DEFINER, owner
#              gapto_internal, search_path fijo), la resolución de D-1
#              (gapto_runtime pierde INSERT directo sobre auditoria) y los
#              privilegios mínimos de gapto_internal.
#
#              Cubre camino correcto Y camino denegado. El camino denegado
#              se prueba de dos formas distintas, porque son fallos
#              distintos: (a) un rol SIN GRANT EXECUTE no puede invocar la
#              función -> demuestra que el REVOKE FROM PUBLIC es efectivo;
#              (b) gapto_runtime, que SÍ puede invocarla, ya no puede hacer
#              lo mismo por vía directa -> demuestra que la función aporta
#              algo y no es decorativa.
#
# PRECONDICIÓN: requiere F03-01-B16 (migration 0190), que completa la
#              cadena SET ROLE hacia gapto_runtime y gapto_backup. Sin
#              ella, los tests de camino correcto y de contexto inválido
#              fallan con 42501 "permission denied to set role" y NO por
#              el motivo que pretenden probar.
# Versión: 0.1.4  -- D-098: las lecturas de verificacion fijan el contexto de
#                   tenant; sin el, un rol de conexion sin BYPASSRLS aborta con
#                   22P02 al evaluar la policy de auditoria.
#                   v0.1.3: D-098: _borrar_auditoria pasa a ser portable entre
#                   proveedores (gapto_owner + NO FORCE temporal) y restaura
#                   guard y FORCE RLS en finally.
#                   v0.1.2: corrige SET LOCAL parametrizado: SET no admite
#                   parametros vinculados, se usa set_config().  -- el test de guard append-only pasa a afirmar la
#                   propiedad (fila inmutable) en vez de la capa concreta
#                   que deniega, que depende del rol de conexión del
#                   proveedor. Se añade test de instalación del guard.
# ============================================================

from __future__ import annotations

import psycopg
import pytest

FN_SIG = "gapto.fn_registrar_auditoria(varchar, uuid, varchar, jsonb, jsonb, text)"

# UUIDs propios de este test, disjuntos de los usados en test_016.
OWNER_A = "b15a0000-0000-4000-8000-000000000001"
OWNER_B = "b15b0000-0000-4000-8000-000000000002"
REGISTRO = "b15c0000-0000-4000-8000-000000000003"
REQUEST = "b15d0000-0000-4000-8000-000000000004"


# ============================================================
# Utilidades
# ============================================================

def _scalar(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return row[0] if row else None


def _fijar_contexto(db: psycopg.Connection, owner: str | None) -> None:
    """Fija (o limpia) la GUC de tenant a nivel de sesión.

    D-098: cualquier lectura de `gapto.auditoria` hecha fuera de una
    transacción con contexto falla con 22P02 si el rol de conexión no tiene
    BYPASSRLS, porque la policy castea '' a uuid. Neon lo ocultaba; Supabase
    no. Las lecturas de verificación fijan el contexto explícitamente.
    """
    with db.cursor() as cursor:
        cursor.execute("RESET ROLE")
        if owner is None:
            cursor.execute("RESET ALL")
        else:
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (owner,))


def _scalar_tenant(db: psycopg.Connection, owner: str, sql: str, params: tuple):
    """Lectura de verificación con contexto de tenant y limpieza posterior.

    Fijar la GUC a nivel de sesión sin limpiarla contamina los casos que
    prueban precisamente su ausencia, así que se limpia siempre.
    """
    _fijar_contexto(db, owner)
    try:
        return _scalar(db, sql, params)
    finally:
        _fijar_contexto(db, None)


def _borrar_auditoria(db: psycopg.Connection, owner_ids: tuple[str, ...]) -> None:
    """Elimina filas de auditoría de forma portable entre proveedores.

    D-098: la versión anterior borraba con el rol de conexión, lo que solo
    funciona donde ese rol puede escribir en toda la base. En Supabase,
    `postgres` no tiene DELETE sobre gapto.auditoria y el helper fallaba con
    42501, arrastrando todo el módulo (misma asimetría de D-088).

    Se hace como `gapto_owner`, que es el propietario, retirando a la vez las
    dos barreras que impiden el borrado: el guard append-only y FORCE RLS,
    porque bajo FORCE y sin policy de DELETE el propietario obtendría 0 filas
    en silencio. Ambas se restauran en `finally`: dejarlas retiradas sería
    drift de seguridad.
    """
    with db.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "ALTER TABLE gapto.auditoria "
                "DISABLE TRIGGER trg_auditoria__guard_append_only"
            )
            cursor.execute("ALTER TABLE gapto.auditoria NO FORCE ROW LEVEL SECURITY")
            cursor.execute(
                "DELETE FROM gapto.auditoria WHERE owner_user_id = ANY(%s::uuid[])",
                (list(owner_ids),),
            )
        finally:
            cursor.execute("ALTER TABLE gapto.auditoria FORCE ROW LEVEL SECURITY")
            cursor.execute(
                "ALTER TABLE gapto.auditoria "
                "ENABLE TRIGGER trg_auditoria__guard_append_only"
            )
            cursor.execute("RESET ROLE")


def _tenants(db: psycopg.Connection, crear: bool) -> None:
    """Crea o retira los dos tenants como gapto_owner y con contexto fijado.

    D-098: hacerlo con el rol de conexión solo funciona donde ese rol tiene
    BYPASSRLS. En Supabase no lo tiene y la policy `tenant_isolation` rechaza
    el INSERT. Como `usuarios` es la raíz de ownership, basta fijar la GUC al
    propio id para que WITH CHECK se cumpla.
    """
    with db.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE gapto_owner")
            for uid, mail in ((OWNER_A, "b15.owner.a@example.com"),
                              (OWNER_B, "b15.owner.b@example.com")):
                cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (uid,))
                cursor.execute("DELETE FROM gapto.usuarios WHERE id = %s", (uid,))
                if crear:
                    cursor.execute(
                        "INSERT INTO gapto.usuarios (id, email, nombre) "
                        "VALUES (%s, %s, 'B15 Owner')",
                        (uid, mail),
                    )
            cursor.execute("COMMIT")
        except psycopg.Error:
            cursor.execute("ROLLBACK")
            raise
        finally:
            cursor.execute("RESET ROLE")


@pytest.fixture(scope="module")
def usuarios_b15(db: psycopg.Connection):
    """Dos usuarios/tenants para probar aislamiento y FK de auditoría."""
    _borrar_auditoria(db, (OWNER_A, OWNER_B))
    _tenants(db, crear=True)

    yield

    _borrar_auditoria(db, (OWNER_A, OWNER_B))
    _tenants(db, crear=False)


def _registrar(
    db: psycopg.Connection,
    *,
    rol: str = "gapto_runtime",
    owner: str | None = OWNER_A,
    actor_tipo: str | None = "SISTEMA",
    actor_user: str | None = None,
    request: str | None = REQUEST,
    tabla: str = "usuarios",
    registro_id: str = REGISTRO,
    accion: str = "CREAR",
    datos_antes=None,
    datos_despues=None,
    motivo: str | None = None,
) -> str:
    """Invoca la función bajo `rol` fijando el contexto con SET LOCAL.

    Un valor None omite la GUC; una cadena vacía la fija a '' para probar
    explícitamente el tratamiento de ausencia frente a cadena vacía.
    """
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute(f"SET LOCAL ROLE {rol}")
            for guc, valor in (
                ("gapto.owner_user_id", owner),
                ("gapto.actor_tipo", actor_tipo),
                ("gapto.actor_user_id", actor_user),
                ("gapto.request_id", request),
            ):
                if valor is not None:
                    cursor.execute("SELECT set_config(%s, %s, true)", (guc, valor))
            cursor.execute(
                "SELECT gapto.fn_registrar_auditoria(%s, %s::uuid, %s, %s, %s, %s)",
                (tabla, registro_id, accion, datos_antes, datos_despues, motivo),
            )
            (nuevo_id,) = cursor.fetchone()
            cursor.execute("COMMIT")
            return nuevo_id
        except Exception:
            cursor.execute("ROLLBACK")
            raise


# ============================================================
# 1) Contrato físico de la función
# ============================================================

def test_b15_existe_una_unica_funcion_security_definer(db: psycopg.Connection) -> None:
    """D-082: exactamente una función SECURITY DEFINER, sin catálogo inflado."""
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'gapto' AND p.prosecdef
        """)
        encontradas = {r[0] for r in cursor.fetchall()}
    assert encontradas == {"fn_registrar_auditoria"}


def test_b15_owner_es_gapto_internal(db: psycopg.Connection) -> None:
    owner = _scalar(db, f"SELECT pg_catalog.pg_get_userbyid(proowner) FROM pg_catalog.pg_proc WHERE oid = '{FN_SIG}'::regprocedure")
    assert owner == "gapto_internal"


def test_b15_search_path_fijo_y_seguro(db: psycopg.Connection) -> None:
    """search_path explícito, sin schemas escribibles por runtime, pg_temp al final."""
    config = _scalar(db, f"SELECT proconfig FROM pg_catalog.pg_proc WHERE oid = '{FN_SIG}'::regprocedure")
    assert config is not None, "la función debe fijar search_path explícitamente"
    entradas = [c for c in config if c.startswith("search_path=")]
    assert len(entradas) == 1
    valor = entradas[0].split("=", 1)[1]
    partes = [p.strip() for p in valor.split(",")]
    assert partes[0] == "pg_catalog"
    assert partes[-1] == "pg_temp"
    assert "public" not in partes
    assert "gapto" not in partes


def test_b15_firma_no_admite_owner_actor_ni_request(db: psycopg.Connection) -> None:
    """El caller no puede falsificar el tenant ni el actor: no son parámetros."""
    nombres = _scalar(
        db,
        f"SELECT proargnames FROM pg_catalog.pg_proc WHERE oid = '{FN_SIG}'::regprocedure",
    )
    assert nombres == [
        "p_tabla", "p_registro_id", "p_accion",
        "p_datos_antes", "p_datos_despues", "p_motivo",
    ]
    prohibidos = {"owner_user_id", "actor_tipo", "actor_user_id", "request_id"}
    assert not prohibidos & {n.removeprefix("p_") for n in nombres}


# ============================================================
# 2) D-1: runtime pierde la escritura directa
# ============================================================

def test_b15_runtime_sin_insert_sobre_auditoria(db: psycopg.Connection) -> None:
    assert _scalar(
        db, "SELECT has_table_privilege('gapto_runtime', 'gapto.auditoria', 'INSERT')"
    ) is False
    # La lectura se conserva: append-only no significa ilegible.
    assert _scalar(
        db, "SELECT has_table_privilege('gapto_runtime', 'gapto.auditoria', 'SELECT')"
    ) is True


def test_b15_runtime_insert_directo_falla(db: psycopg.Connection, usuarios_b15) -> None:
    """Camino denegado (b): la función aporta algo porque la vía directa está cerrada."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO gapto.auditoria "
                "(owner_user_id, actor_tipo, tabla, registro_id, accion) "
                "VALUES (%s, 'SISTEMA', 'usuarios', %s, 'CREAR')",
                (OWNER_A, REGISTRO),
            )
        cursor.execute("ROLLBACK")


def test_b15_insert_grant_total_es_73(db: psycopg.Connection) -> None:
    """B14 concedía INSERT en 74 tablas; auditoria sale de esa lista."""
    total = _scalar(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relkind='r'
           AND r.rolname='gapto_runtime' AND acl.privilege_type='INSERT'
    """)
    assert total == 73


# ============================================================
# 3) Privilegios mínimos de gapto_internal
# ============================================================

def test_b15_internal_privilegios_minimos(db: psycopg.Connection) -> None:
    assert _scalar(db, "SELECT has_schema_privilege('gapto_internal','gapto','USAGE')") is True
    # El CREATE temporal necesario para el ownership se retiró en la migration.
    assert _scalar(db, "SELECT has_schema_privilege('gapto_internal','gapto','CREATE')") is False
    assert _scalar(db, "SELECT has_table_privilege('gapto_internal','gapto.auditoria','INSERT')") is True
    # Sin SELECT: la función no usa RETURNING precisamente para no exigirlo.
    for priv in ("SELECT", "UPDATE", "DELETE"):
        assert _scalar(
            db, f"SELECT has_table_privilege('gapto_internal','gapto.auditoria','{priv}')"
        ) is False, f"gapto_internal no debe tener {priv} sobre auditoria"


def test_b15_internal_sin_privilegios_en_otras_tablas(db: psycopg.Connection) -> None:
    """auditoria es la única superficie de gapto_internal."""
    total = _scalar(db, """
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_internal'
    """)
    assert total == 1


def test_b15_internal_sigue_sin_bypassrls(db: psycopg.Connection) -> None:
    """SECURITY DEFINER no es un atajo para saltarse RLS."""
    assert _scalar(db, "SELECT rolbypassrls FROM pg_catalog.pg_roles WHERE rolname='gapto_internal'") is False


# ============================================================
# 4) EXECUTE: deny-by-default
# ============================================================

def test_b15_execute_revocado_de_public(db: psycopg.Connection) -> None:
    assert _scalar(
        db, f"SELECT has_function_privilege('public', '{FN_SIG}', 'EXECUTE')"
    ) is False


def test_b15_execute_solo_para_runtime(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(f"""
            SELECT r.rolname
              FROM pg_catalog.pg_proc p
              CROSS JOIN LATERAL aclexplode(p.proacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE p.oid = '{FN_SIG}'::regprocedure
               AND acl.privilege_type = 'EXECUTE'
        """)
        concedidos = {r[0] for r in cursor.fetchall()}
    # gapto_internal aparece como propietario; el único consumidor es runtime.
    assert concedidos == {"gapto_internal", "gapto_runtime"}


def test_b15_rol_sin_grant_no_puede_ejecutar(db: psycopg.Connection, usuarios_b15) -> None:
    """Camino denegado (a): prueba real, no lectura del DDL.

    gapto_backup sirve de sonda: tiene USAGE sobre el schema y BYPASSRLS,
    pero ningún GRANT EXECUTE. Si el REVOKE FROM PUBLIC no fuese efectivo,
    este test pasaría a ejecutar la función.
    """
    assert _scalar(
        db, f"SELECT has_function_privilege('gapto_backup', '{FN_SIG}', 'EXECUTE')"
    ) is False

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _registrar(db, rol="gapto_backup")


# ============================================================
# 5) Camino correcto
# ============================================================

def test_b15_camino_correcto_sistema(db: psycopg.Connection, usuarios_b15) -> None:
    nuevo_id = _registrar(db, actor_tipo="SISTEMA", motivo="  alta automatica  ")
    assert nuevo_id is not None

    fila = None
    with db.cursor() as cursor:
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (OWNER_A,))
        cursor.execute(
            "SELECT owner_user_id::text, actor_tipo, actor_user_id, request_id::text, "
            "       tabla, registro_id::text, accion, motivo "
            "  FROM gapto.auditoria WHERE id = %s",
            (nuevo_id,),
        )
        fila = cursor.fetchone()
        cursor.execute("RESET ALL")

    assert fila is not None
    owner, actor_tipo, actor_user, request, tabla, registro, accion, motivo = fila
    assert owner == OWNER_A
    assert actor_tipo == "SISTEMA"
    assert actor_user is None
    assert request == REQUEST
    assert tabla == "usuarios"
    assert registro == REGISTRO
    assert accion == "CREAR"
    # Texto opcional en blanco se normaliza (F03-00-D).
    assert motivo == "alta automatica"


def test_b15_camino_correcto_usuario(db: psycopg.Connection, usuarios_b15) -> None:
    nuevo_id = _registrar(db, actor_tipo="USUARIO", actor_user=OWNER_A, accion="ACTUALIZAR")
    with db.cursor() as cursor:
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (OWNER_A,))
        cursor.execute(
            "SELECT actor_tipo, actor_user_id::text FROM gapto.auditoria WHERE id = %s",
            (nuevo_id,),
        )
        actor_tipo, actor_user = cursor.fetchone()
        cursor.execute("RESET ALL")
    assert (actor_tipo, actor_user) == ("USUARIO", OWNER_A)


def test_b15_owner_no_es_falsificable(db: psycopg.Connection, usuarios_b15) -> None:
    """El tenant almacenado procede de la GUC, no de nada que envíe el caller.

    Se ejecuta con contexto de OWNER_B; la fila debe quedar en OWNER_B aunque
    todos los parámetros del caller sean idénticos al caso de OWNER_A.
    """
    nuevo_id = _registrar(db, owner=OWNER_B)
    assert _scalar_tenant(
        db, OWNER_B, "SELECT owner_user_id::text FROM gapto.auditoria WHERE id = %s", (nuevo_id,)
    ) == OWNER_B


def test_b15_llamada_en_la_misma_transaccion_hace_rollback(db: psycopg.Connection, usuarios_b15) -> None:
    """SECURITY DEFINER no crea una transacción autónoma: o ambas o ninguna."""
    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
        cursor.execute("SELECT set_config('gapto.actor_tipo', 'SISTEMA', true)")
        cursor.execute("SELECT set_config('gapto.request_id', %s, true)", (REQUEST,))
        cursor.execute(
            "SELECT gapto.fn_registrar_auditoria('usuarios', %s::uuid, 'ANULAR')",
            (REGISTRO,),
        )
        (id_descartado,) = cursor.fetchone()
        cursor.execute("ROLLBACK")
    assert _scalar_tenant(
        db, OWNER_A, "SELECT count(*) FROM gapto.auditoria WHERE id = %s", (id_descartado,)
    ) == 0


# ============================================================
# 6) Camino denegado por contexto inválido
# ============================================================

@pytest.mark.parametrize(
    "kwargs, motivo_fallo",
    [
        ({"owner": None}, "owner ausente"),
        ({"owner": ""}, "owner en cadena vacia"),
        ({"actor_tipo": None}, "actor_tipo ausente"),
        ({"actor_tipo": ""}, "actor_tipo en cadena vacia"),
        ({"actor_tipo": "ADMIN"}, "actor_tipo fuera del conjunto cerrado"),
        ({"actor_tipo": "USUARIO", "actor_user": None}, "USUARIO sin actor_user_id"),
        ({"actor_tipo": "USUARIO", "actor_user": ""}, "USUARIO con actor_user_id vacio"),
        ({"actor_tipo": "SISTEMA", "actor_user": OWNER_A}, "SISTEMA con actor inventado"),
        ({"request": None}, "request_id ausente"),
        ({"request": ""}, "request_id en cadena vacia"),
    ],
)
def test_b15_contexto_invalido_falla(
    db: psycopg.Connection, usuarios_b15, kwargs: dict, motivo_fallo: str
) -> None:
    with pytest.raises(psycopg.errors.InvalidAuthorizationSpecification):
        _registrar(db, **kwargs)


def test_b15_tabla_inexistente_falla(db: psycopg.Connection, usuarios_b15) -> None:
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        _registrar(db, tabla="tabla_que_no_existe")


def test_b15_tabla_fuera_del_schema_falla(db: psycopg.Connection, usuarios_b15) -> None:
    """pg_class existe, pero no dentro de gapto."""
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        _registrar(db, tabla="pg_class")


def test_b15_vista_no_es_tabla_auditable(db: psycopg.Connection, usuarios_b15) -> None:
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        _registrar(db, tabla="v_hechos_resumen")


def test_b15_accion_invalida_falla(db: psycopg.Connection, usuarios_b15) -> None:
    """El conjunto cerrado vive en ck_auditoria__accion, sin duplicarlo."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _registrar(db, accion="BORRAR_TODO")


def test_b15_snapshot_con_clave_prohibida_falla(db: psycopg.Connection, usuarios_b15) -> None:
    """D-068: passwords, tokens, API keys y URLs firmadas nunca se duplican."""
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        _registrar(db, datos_despues='{"email": "a@b.c", "password_hash": "xxx"}')

    with pytest.raises(psycopg.errors.InvalidParameterValue):
        _registrar(db, datos_antes='{"storage_key": "privado/abc"}')


def test_b15_snapshot_funcional_valido_se_acepta(db: psycopg.Connection, usuarios_b15) -> None:
    nuevo_id = _registrar(
        db,
        datos_antes='{"nombre": "Antes"}',
        datos_despues='{"nombre": "Despues"}',
    )
    assert _scalar_tenant(
        db, OWNER_A, "SELECT datos_despues->>'nombre' FROM gapto.auditoria WHERE id = %s", (nuevo_id,)
    ) == "Despues"


# ============================================================
# 7) RLS e inmutabilidad siguen vigentes
# ============================================================

def test_b15_lectura_aislada_por_tenant(db: psycopg.Connection, usuarios_b15) -> None:
    id_a = _registrar(db, owner=OWNER_A)
    id_b = _registrar(db, owner=OWNER_B)

    with db.cursor() as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET LOCAL ROLE gapto_runtime")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
        cursor.execute(
            "SELECT count(*) FROM gapto.auditoria WHERE id = ANY(%s::uuid[])",
            ([id_a, id_b],),
        )
        (visibles,) = cursor.fetchone()
        cursor.execute("ROLLBACK")

    assert visibles == 1, "runtime solo debe ver la fila de su propio tenant"


def test_b15_rls_sigue_aplicando_dentro_de_la_funcion(db: psycopg.Connection, usuarios_b15) -> None:
    """La función no bypassa RLS: la policy tenant_insert sigue evaluándose.

    Se comprueba de forma estructural, porque el WITH CHECK se satisface
    siempre por construcción (la función escribe el mismo owner que lee de
    la GUC). Lo relevante es que la policy siga ahí y que FORCE RLS impida
    que un futuro cambio de propietario la desactive de hecho.
    """
    forzada = _scalar(db, """
        SELECT c.relrowsecurity AND c.relforcerowsecurity
          FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname='gapto' AND c.relname='auditoria'
    """)
    assert forzada is True

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT policyname FROM pg_catalog.pg_policies
             WHERE schemaname='gapto' AND tablename='auditoria'
        """)
        policies = {r[0] for r in cursor.fetchall()}
    assert policies == {"tenant_select", "tenant_insert"}


def test_b15_update_delete_siguen_bloqueados(db: psycopg.Connection, usuarios_b15) -> None:
    """auditoria sigue siendo append-only para filas creadas por la función.

    La CAPA que deniega depende del rol de conexión y por tanto del
    proveedor, así que el test afirma la propiedad, no la capa:

    - Neon: `neondb_owner` hereda `neon_superuser`, tiene UPDATE/DELETE
      sobre gapto.auditoria y BYPASSRLS, así que llega al guard y recibe
      P0001.
    - Supabase: `postgres` no tiene UPDATE/DELETE sobre gapto.auditoria y
      la denegación llega antes, por ACL, con 42501.

    Ninguna de las dos es incorrecta: en ambos casos la fila es inmutable.
    Fijar P0001 haría el test dependiente del proveedor, que es justo lo
    que F03-01 no admite. Ver D-087 sobre la inalcanzabilidad del guard
    desde los roles del modelo.
    """
    nuevo_id = _registrar(db)

    for sentencia in (
        "UPDATE gapto.auditoria SET accion='ACTUALIZAR' WHERE id = %s",
        "DELETE FROM gapto.auditoria WHERE id = %s",
    ):
        with db.cursor() as cursor:
            cursor.execute("BEGIN")
            # Sin contexto, la policy castea '' a uuid y el intento fallaria por
            # 22P02 en vez de por la denegacion que se quiere demostrar (D-075).
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_A,))
            try:
                cursor.execute(sentencia, (nuevo_id,))
                afectadas = cursor.rowcount
                denegado = afectadas == 0
                detalle = f"sin error pero {afectadas} filas afectadas"
            except (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege) as exc:
                denegado = True
                detalle = type(exc).__name__
            finally:
                cursor.execute("ROLLBACK")

        assert denegado, f"auditoria debe ser inmutable; {sentencia.split()[0]}: {detalle}"

    # La fila sigue intacta.
    assert _scalar_tenant(
        db, OWNER_A, "SELECT accion FROM gapto.auditoria WHERE id = %s", (nuevo_id,)
    ) == "CREAR"


def test_b15_guard_append_only_sigue_instalado(db: psycopg.Connection) -> None:
    """El guard existe y está habilitado, aunque hoy sea inalcanzable.

    Ningún rol del modelo gapto puede llegar a él: runtime y backup no
    tienen UPDATE/DELETE sobre auditoria, y gapto_owner queda filtrado por
    FORCE RLS (0 filas, sin error) porque no existe policy de UPDATE ni de
    DELETE. El guard es defensa en profundidad frente a un futuro error de
    privilegios, no la barrera activa. Ver D-087.
    """
    estado = _scalar(db, """
        SELECT t.tgenabled
          FROM pg_catalog.pg_trigger t
         WHERE t.tgrelid = 'gapto.auditoria'::regclass
           AND t.tgname = 'trg_auditoria__guard_append_only'
    """)
    assert estado == "O", "el guard append-only debe existir y estar habilitado"


# ============================================================
# 8) Paridad Neon / Supabase
# ============================================================

def test_b15_fingerprint_estable(db: psycopg.Connection) -> None:
    """Huella del bloque; debe coincidir literalmente en ambos proveedores."""
    huella = _scalar(db, f"""
        SELECT p.proname || '|' || pg_catalog.pg_get_userbyid(p.proowner)
                        || '|secdef=' || p.prosecdef::text
                        || '|' || pg_catalog.array_to_string(p.proconfig, ',')
                        || '|' || pg_catalog.pg_get_function_identity_arguments(p.oid)
          FROM pg_catalog.pg_proc p
         WHERE p.oid = '{FN_SIG}'::regprocedure
    """)
    assert huella == (
        "fn_registrar_auditoria|gapto_internal|secdef=true"
        "|search_path=pg_catalog, pg_temp"
        "|p_tabla character varying, p_registro_id uuid, p_accion character varying, "
        "p_datos_antes jsonb, p_datos_despues jsonb, p_motivo text"
    )
