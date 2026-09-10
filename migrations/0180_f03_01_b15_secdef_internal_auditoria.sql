-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0180_f03_01_b15_secdef_internal_auditoria.sql
-- Ruta: migrations/0180_f03_01_b15_secdef_internal_auditoria.sql
-- Descripcion: F03-01-B15. Materializa la unica funcion SECURITY DEFINER
--   aprobada en D-082: el writer interno de gapto.auditoria, propiedad de
--   gapto_internal, y corrige la incompatibilidad D-1 entre D-068 y B14.
--
--   D-068/F03-00-H fija que auditoria es append-only real y que la escritura
--   corresponde a un mecanismo interno controlado, no a gapto_runtime. B14
--   (0130) concedio INSERT de forma uniforme a las 74 tablas tenant no
--   catalogo, alcanzando tambien a auditoria. Este bloque revoca ese INSERT
--   y enruta la escritura por la funcion privilegiada.
--
--   Contenido:
--   1) REVOKE INSERT ON gapto.auditoria FROM gapto_runtime.
--   2) Habilitacion minima de gapto_internal: USAGE sobre gapto, INSERT
--      unicamente sobre gapto.auditoria y CREATE TEMPORAL sobre el schema
--      (necesario para que gapto_internal pueda ser propietario de la
--      funcion; se revoca en esta misma migration).
--   3) gapto.fn_registrar_auditoria(...): SECURITY DEFINER, search_path
--      fijo pg_catalog+pg_temp, sin SQL dinamico, deriva owner/actor/
--      request del contexto transaccional y NO los acepta como parametro.
--   4) REVOKE EXECUTE FROM PUBLIC + GRANT EXECUTE solo a gapto_runtime, y
--      default privileges restrictivos para futuras funciones de
--      gapto_internal.
--
--   Alcance deliberadamente NO cubierto por este bloque:
--   - No se crean setters de contexto, helpers de hard-delete ni ninguna
--     otra funcion privilegiada sin consumidor aprobado (D-082).
--   - No se crean triggers genericos de auditoria: eso introduciria una
--     politica nueva sobre que campos auditar y chocaria con la
--     minimizacion de PII de D-068.
--   - No se toca el DELETE que gapto_runtime conserva sobre las 67 tablas
--     tenant escribibles (hallazgo D-3). Se reporta aparte; corregirlo aqui
--     seria un cambio de politica de escritura fuera del alcance de B15.
--
--   Este fichero NO modifica 0130 ni ninguna migration ya aplicada: la
--   correccion es forward-only. test_016_b14_grants_guards.py pasa a v0.1.1
--   porque su asercion INSERT==74 deja de ser cierta por diseno.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- ============================================================
-- 1) D-1: auditoria deja de ser escribible directamente por runtime
-- ============================================================
-- El grantor debe ser el propietario de la tabla (gapto_owner), no el rol
-- administrativo de conexion.
SET ROLE gapto_owner;

REVOKE INSERT ON gapto.auditoria FROM gapto_runtime;

-- gapto_runtime conserva SELECT: la lectura de auditoria sigue permitida y
-- aislada por la policy tenant_select. Lo que desaparece es la escritura
-- directa. UPDATE/DELETE ya estaban ausentes desde B14 y ademas bloqueados
-- por trg_auditoria__guard_append_only.

-- ============================================================
-- 2) Habilitacion minima de gapto_internal
-- ============================================================
-- Estado previo verificado: gapto_internal no tenia USAGE sobre el schema
-- gapto ni ningun privilegio de tabla. Se concede exclusivamente lo que la
-- funcion de este bloque necesita para ejecutarse.
GRANT USAGE ON SCHEMA gapto TO gapto_internal;

GRANT INSERT ON gapto.auditoria TO gapto_internal;

-- CREATE es TEMPORAL. PostgreSQL exige que el propietario de una funcion
-- tenga CREATE sobre el schema que la contiene en el momento de crearla o
-- de recibir su ownership. Se revoca al final de esta misma migration para
-- no dejar superficie permanente.
GRANT CREATE ON SCHEMA gapto TO gapto_internal;

RESET ROLE;

-- ============================================================
-- 3) Writer interno de auditoria
-- ============================================================
-- Se crea directamente BAJO gapto_internal para que nazca con el owner
-- correcto y no haga falta ALTER FUNCTION ... OWNER TO.
SET ROLE gapto_internal;

CREATE FUNCTION gapto.fn_registrar_auditoria(
    p_tabla         varchar(100),
    p_registro_id   uuid,
    p_accion        varchar(30),
    p_datos_antes   jsonb DEFAULT NULL,
    p_datos_despues jsonb DEFAULT NULL,
    p_motivo        text  DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_id          uuid;
    v_owner       uuid;
    v_actor_tipo  text;
    v_actor_user  uuid;
    v_request     uuid;
    v_relid       oid;
BEGIN
    -- --------------------------------------------------------
    -- 3.1 Contexto transaccional (D-075). NUNCA parametros del caller.
    -- --------------------------------------------------------
    -- '' se trata expresamente como ausencia: un backend PostgreSQL
    -- reutilizado puede dejar una GUC personalizada en cadena vacia tras
    -- reset o fin de transaccion, y ''::uuid no fallaria de forma legible.
    v_owner      := NULLIF(pg_catalog.current_setting('gapto.owner_user_id', true), '')::uuid;
    v_actor_tipo := NULLIF(pg_catalog.current_setting('gapto.actor_tipo',     true), '');
    v_actor_user := NULLIF(pg_catalog.current_setting('gapto.actor_user_id',  true), '')::uuid;
    v_request    := NULLIF(pg_catalog.current_setting('gapto.request_id',     true), '')::uuid;

    IF v_owner IS NULL THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: contexto de tenant ausente (gapto.owner_user_id no fijado)'
            USING ERRCODE = '28000';
    END IF;

    IF v_actor_tipo IS NULL OR v_actor_tipo NOT IN ('USUARIO', 'SISTEMA') THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: gapto.actor_tipo invalido o ausente (esperado USUARIO o SISTEMA)'
            USING ERRCODE = '28000';
    END IF;

    -- USUARIO exige actor identificado; SISTEMA no lo inventa ni lo admite.
    IF v_actor_tipo = 'USUARIO' AND v_actor_user IS NULL THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: actor_tipo=USUARIO exige gapto.actor_user_id'
            USING ERRCODE = '28000';
    END IF;

    IF v_actor_tipo = 'SISTEMA' AND v_actor_user IS NOT NULL THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: actor_tipo=SISTEMA no admite gapto.actor_user_id'
            USING ERRCODE = '28000';
    END IF;

    -- La nulabilidad fisica de auditoria.request_id existe por legacy. El
    -- write-path ordinario de runtime debe correlacionar siempre; un
    -- backfill historico se materializa bajo gapto_owner, no por aqui.
    IF v_request IS NULL THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: gapto.request_id ausente; el write-path ordinario debe correlacionar la operacion'
            USING ERRCODE = '28000';
    END IF;

    -- --------------------------------------------------------
    -- 3.2 Validacion del objeto auditado
    -- --------------------------------------------------------
    -- D-068: auditoria.tabla lo informa el mecanismo interno, no entrada
    -- libre del cliente, y no se duplica la lista de 79 tablas en un CHECK.
    -- Se resuelve el nombre contra el catalogo (resolucion de nombre, no
    -- SQL dinamico ejecutable) y se exige que sea una tabla real de gapto.
    v_relid := pg_catalog.to_regclass('gapto.' || pg_catalog.quote_ident(p_tabla));

    IF v_relid IS NULL
       OR NOT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             WHERE c.oid = v_relid
               AND n.nspname = 'gapto'
               AND c.relkind = 'r'
          )
    THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: % no es una tabla del schema gapto', p_tabla
            USING ERRCODE = '22023';
    END IF;

    -- p_accion no se valida aqui contra una lista duplicada: el conjunto
    -- cerrado ya vive en ck_auditoria__accion y debe tener una unica fuente
    -- de verdad. Un valor invalido falla como CheckViolation en el INSERT.

    -- --------------------------------------------------------
    -- 3.3 Minimizacion de PII/secretos (D-068)
    -- --------------------------------------------------------
    -- Los snapshots deben llegar ya proyectados por dominio
    -- (FULL_FUNCTIONAL / MASKED_PII / EVENT_ONLY). Esta comprobacion es una
    -- red de seguridad de ultimo recurso sobre claves de primer nivel, no
    -- un sustituto de la proyeccion en el write-path.
    IF (p_datos_antes   IS NOT NULL AND pg_catalog.jsonb_typeof(p_datos_antes)   <> 'object')
       OR (p_datos_despues IS NOT NULL AND pg_catalog.jsonb_typeof(p_datos_despues) <> 'object')
    THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: datos_antes/datos_despues deben ser objetos jsonb'
            USING ERRCODE = '22023';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (
                SELECT pg_catalog.jsonb_object_keys(p_datos_antes)   AS k
                UNION ALL
                SELECT pg_catalog.jsonb_object_keys(p_datos_despues) AS k
               ) AS claves
         WHERE pg_catalog.lower(claves.k) ~ '(password|passwd|token|api[_-]?key|secret|private[_-]?key|storage_key|signed_url)'
    ) THEN
        RAISE EXCEPTION
            'gapto.fn_registrar_auditoria: el snapshot contiene una clave prohibida (password/token/api key/secreto/clave privada/storage_key/URL firmada)'
            USING ERRCODE = '22023';
    END IF;

    -- --------------------------------------------------------
    -- 3.4 Insercion
    -- --------------------------------------------------------
    -- Sin RETURNING: gapto_internal tiene INSERT pero no SELECT sobre
    -- auditoria, y INSERT ... RETURNING exigiria SELECT. El id se genera
    -- aqui para poder devolverlo sin ampliar privilegios.
    v_id := pg_catalog.gen_random_uuid();

    INSERT INTO gapto.auditoria (
        id, owner_user_id, actor_tipo, actor_user_id,
        tabla, registro_id, accion,
        datos_antes, datos_despues, motivo, request_id
    ) VALUES (
        v_id, v_owner, v_actor_tipo, v_actor_user,
        p_tabla, p_registro_id, p_accion,
        p_datos_antes, p_datos_despues,
        NULLIF(pg_catalog.btrim(p_motivo), ''), v_request
    );

    RETURN v_id;
END;
$fn$;

COMMENT ON FUNCTION gapto.fn_registrar_auditoria(varchar, uuid, varchar, jsonb, jsonb, text) IS
    'F03-01-B15 / D-082: unico writer de gapto.auditoria. SECURITY DEFINER bajo gapto_internal. '
    'owner_user_id, actor_tipo, actor_user_id y request_id se derivan del contexto transaccional '
    '(SET LOCAL gapto.*) y NO son parametros falsificables por el caller. NO bypassa RLS: la policy '
    'tenant_insert de auditoria sigue aplicando bajo FORCE ROW LEVEL SECURITY. Debe invocarse en la '
    'misma transaccion que la mutacion auditada.';

-- ============================================================
-- 4) EXECUTE: deny-by-default y concesion minima
-- ============================================================
-- CREATE FUNCTION concede EXECUTE a PUBLIC por defecto; B14 solo fijo
-- default privileges restrictivos sobre TABLES y para el rol gapto_owner,
-- asi que este REVOKE es imprescindible, no decorativo.
REVOKE ALL ON FUNCTION gapto.fn_registrar_auditoria(varchar, uuid, varchar, jsonb, jsonb, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION gapto.fn_registrar_auditoria(varchar, uuid, varchar, jsonb, jsonb, text) TO gapto_runtime;

-- Defensa en profundidad para futuras funciones de gapto_internal.
ALTER DEFAULT PRIVILEGES FOR ROLE gapto_internal IN SCHEMA gapto
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

RESET ROLE;

-- ============================================================
-- 5) Retirada del CREATE temporal
-- ============================================================
SET ROLE gapto_owner;

REVOKE CREATE ON SCHEMA gapto FROM gapto_internal;

RESET ROLE;

COMMIT;
