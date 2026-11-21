-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0356_f06_t4_g2_dedup.sql
-- Ruta: migrations/0356_f06_t4_g2_dedup.sql
-- Descripcion: FASE 06 · T4 · P-RB206-1: deduplicacion de G2 de 0354
--   (opcion M del diseno DISENO_T4_G2_DEDUP_v0.1, dictamen DICTAMEN_T4_G2_v1.0
--   CONFORME CON AJUSTES, decision de Moises del 2026-11-21 con R-G2-M1
--   aceptado). Mandato MANDATO_F06-T4_G2_0356_v1.0 (753bebb2…) con su
--   enmienda 01 (257be460…). Migration forward-only sobre 0355 (no edita
--   0001..0355).
--
--   CAUSA. G2 son tres constraint triggers DEFERRABLE INITIALLY DEFERRED FOR
--   EACH ROW (T3 cuotas, T4 financiaciones, T5 versiones de 0354); el backend
--   escribe fila a fila y al COMMIT cada evento revalidaba la financiacion
--   completa: coste O(N^2) en el numero de cuotas.
--
--   MEMO. GUC de transaccion gapto_g2.validadas, escrito solo con
--   set_config(..., true), con la forma «<xid>:<uuid>[,<uuid>...]» donde xid
--   es pg_current_xact_id() de la transaccion que lo escribe. Es el conjunto
--   de financiaciones ya validadas en su estado vigente. Ausente, con otra
--   forma o con otro xid: se trata como vacio (falla cerrado: se valida).
--   Los cambios de un SAVEPOINT revertido se revierten con el GUC.
--
--   INVALIDACION. Tres triggers ORDINARIOS (no diferibles) AFTER ... FOR EACH
--   ROW con los mismos eventos y columnas que T3, T4 y T5, que quitan del memo
--   las financiaciones de OLD y de NEW segun TG_OP (INSERT: NEW; UPDATE: OLD y
--   NEW; DELETE: OLD). Sus nombres («__borrar_memo_g2») ordenan antes que los
--   de G2 («__cuadro_hipoteca»): con SET CONSTRAINTS ... IMMEDIATE ambos son
--   AFTER ROW del mismo evento y PostgreSQL los dispara por orden de nombre,
--   asi que el memo se invalida antes de que el despachador lo consulte.
--
--   DESPACHADOR. CREATE OR REPLACE de gapto.fn_check_cuadro_hipoteca(): mismas
--   financiaciones por evento que en 0354; llama al nucleo solo con las que no
--   estan en el memo y, tras validar sin error, las anade.
--   gapto.fn_validar_cuadro_hipoteca(uuid[]) NO se toca (mismo prosrc, mismos
--   mensajes INV-0354-G2, mismo lock FOR NO KEY UPDATE ordenado). T3, T4 y T5
--   no se tocan.
--
--   INVENTARIO. Una funcion nueva y tres triggers nuevos; una funcion
--   reemplazada (cambia su prosrc: huella h6).
--     F7 gapto.fn_borrar_memo_cuadro_hipoteca()   T8 T9 T10 (invalidacion)
--     F3 gapto.fn_check_cuadro_hipoteca()          (reemplazada; despachador)
--     T8  trg_financiacion_cuotas__borrar_memo_g2               (= eventos de T3)
--     T9  trg_financiaciones__borrar_memo_g2                    (= eventos de T4)
--     T10 trg_financiacion_condiciones_versiones__borrar_memo_g2 (= eventos de T5)
--
--   PATRON (el de 0354). SECURITY INVOKER; SQL cualificado con gapto. y
--   pg_catalog.; sin SET search_path; propietario gapto_owner; ACL por defecto
--   (proacl NULL); cuerpos sin comentarios inline (prosrc participa en D-111);
--   sin SQL dinamico.
--
--   RIESGO ACEPTADO R-G2-M1 (decision de Moises del 2026-11-21, ajuste 4 del
--   dictamen). Quien pueda ejecutar SQL con gapto_runtime puede escribir el
--   GUC del memo y hacer que el despachador omita una validacion: es una via
--   directa de saltarse G2. G2 confia en que gapto_runtime solo lo usa el
--   backend y NO protege frente a quien tenga esa credencial.
--
--   LO QUE NO HACE (a proposito). Sin tablas, columnas, filas, indices,
--   constraints, policies ni privilegios nuevos; sin ALTER TABLE; sin SECURITY
--   DEFINER; no corrige datos; no cambia HEAD_AUTORIZADO_ENVDEV.
--
--   PRECHECKS (fail-closed, misma transaccion). PC-01 el rol de conexion puede
--   asumir gapto_owner; PC-02 head fisico 0355 (ck_contrato_participantes__rol
--   admite AGENCIA y existe fn_validar_cuadro_hipoteca); PC-03 ningun objeto
--   de 0356 existe; PC-04 los tres constraint triggers de G2 existen con su
--   definicion de 0354. Registra los recuentos de partida y el md5 del prosrc
--   del nucleo para el postcheck.
--   POSTCHECKS. PO-01 F7 y F3 invoker, plpgsql, gapto_owner, proacl NULL, sin
--   comentarios en prosrc; PO-02 T8..T10 no diferibles, tgenabled = 'O', mismo
--   tgtype y tgattr que T3..T5, funcion F7; T3..T5 intactos; PO-03 nucleo con
--   el mismo prosrc; PO-04 deltas exactos sobre el head real: funciones +1,
--   triggers no internos +3, constraint triggers +0; FORCE RLS, policies y
--   privilegios de tabla de gapto_runtime sin cambios.
--
-- Version: 0.1.0 (F06 T4 P-RB206-1; mandato 753bebb2… y enmienda 01 257be460…)
-- ============================================================

BEGIN;

DO $precheck_0356$
DECLARE
    v_rep text := '';
    v_n   bigint;
BEGIN
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F06-T4-0356 PRECHECK PC-01: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;
    RAISE NOTICE 'F06-T4-0356 PRECHECK: conexion db=% rol=%', pg_catalog.current_database(), current_user;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND k.conname = 'ck_contrato_participantes__rol'
       AND pg_catalog.strpos(pg_catalog.pg_get_constraintdef(k.oid), '''AGENCIA''') > 0;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' PC-02 falta la marca de 0355 (ck_contrato_participantes__rol con AGENCIA);';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.oid = pg_catalog.to_regprocedure('gapto.fn_validar_cuadro_hipoteca(uuid[])');
    IF v_n <> 1 THEN
        v_rep := v_rep || ' PC-02 falta gapto.fn_validar_cuadro_hipoteca(uuid[]) (head anterior a 0354);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = 'fn_borrar_memo_cuadro_hipoteca';
    IF v_n <> 0 THEN
        v_rep := v_rep || ' PC-03 0356 ya aplicada (existe fn_borrar_memo_cuadro_hipoteca);';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgname IN ('trg_financiacion_cuotas__borrar_memo_g2', 'trg_financiaciones__borrar_memo_g2',
                        'trg_financiacion_condiciones_versiones__borrar_memo_g2');
    IF v_n <> 0 THEN
        v_rep := v_rep || ' PC-03 0356 ya aplicada (existen triggers __borrar_memo_g2);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
     WHERE NOT t.tgisinternal AND t.tgenabled = 'O' AND t.tgqual IS NULL
       AND t.tgdeferrable AND t.tginitdeferred AND t.tgconstraint <> 0
       AND p.oid = 'gapto.fn_check_cuadro_hipoteca()'::pg_catalog.regprocedure
       AND ((t.tgname = 'trg_financiacion_cuotas__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiacion_cuotas'::pg_catalog.regclass AND t.tgtype = 29
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 3)
         OR (t.tgname = 'trg_financiaciones__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiaciones'::pg_catalog.regclass AND t.tgtype = 17
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 2)
         OR (t.tgname = 'trg_financiacion_condiciones_versiones__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiacion_condiciones_versiones'::pg_catalog.regclass AND t.tgtype = 21
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 3));
    IF v_n <> 3 THEN
        v_rep := v_rep || pg_catalog.format(' PC-04 constraint triggers de G2 con su definicion de 0354 = %s (esperados 3);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-T4-0356 PRECHECK: BLOQUEA, no se aplica nada:%', v_rep;
    END IF;

    PERFORM pg_catalog.set_config('gapto_f06_0356.funciones_pre',
        (SELECT pg_catalog.count(*)::text FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.triggers_pre',
        (SELECT pg_catalog.count(*)::text FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
          WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.ctriggers_pre',
        (SELECT pg_catalog.count(*)::text FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
          WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.force_pre',
        (SELECT pg_catalog.count(*)::text FROM pg_catalog.pg_class c
          WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r' AND c.relforcerowsecurity), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.policies_pre',
        (SELECT pg_catalog.count(*)::text || ':' || pg_catalog.md5(coalesce(pg_catalog.string_agg(
                    p.tablename || ':' || p.policyname || ':' || p.cmd || ':' || coalesce(p.qual, '-') || ':' || coalesce(p.with_check, '-'),
                    E'\n' ORDER BY p.tablename, p.policyname), ''))
           FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto'), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.privilegios_pre',
        (SELECT pg_catalog.count(*)::text FROM pg_catalog.pg_class c
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
          WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind IN ('r', 'v', 'p')
            AND a.grantee = 'gapto_runtime'::pg_catalog.regrole), true);
    PERFORM pg_catalog.set_config('gapto_f06_0356.nucleo_pre',
        (SELECT pg_catalog.md5(p.prosrc) FROM pg_catalog.pg_proc p
          WHERE p.oid = 'gapto.fn_validar_cuadro_hipoteca(uuid[])'::pg_catalog.regprocedure), true);

    RAISE NOTICE 'F06-T4-0356 PRECHECK: OK (funciones=%, triggers=%, constraint triggers=%)',
        pg_catalog.current_setting('gapto_f06_0356.funciones_pre'), pg_catalog.current_setting('gapto_f06_0356.triggers_pre'),
        pg_catalog.current_setting('gapto_f06_0356.ctriggers_pre');
END;
$precheck_0356$;

SET ROLE gapto_owner;

-- ============================================================
-- F7 / T8 T9 T10 · invalidacion del memo de G2 (triggers ordinarios).
-- ============================================================
CREATE FUNCTION gapto.fn_borrar_memo_cuadro_hipoteca()
RETURNS trigger AS $fn$
DECLARE
    v_fs    uuid[];
    v_memo  text;
    v_xid   text;
    v_resto uuid[];
BEGIN
    CASE TG_TABLE_NAME
        WHEN 'financiacion_cuotas' THEN
            IF TG_OP = 'INSERT' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            ELSIF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[OLD.financiacion_entidad_id];
            END IF;
        WHEN 'financiaciones' THEN
            v_fs := ARRAY[NEW.entidad_id, OLD.entidad_id];
        WHEN 'financiacion_condiciones_versiones' THEN
            IF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            END IF;
        ELSE
            RAISE EXCEPTION 'INV-0356-G2: fn_borrar_memo_cuadro_hipoteca, tabla no contemplada %', TG_TABLE_NAME;
    END CASE;

    v_memo := pg_catalog.current_setting('gapto_g2.validadas', true);
    v_xid := pg_catalog.pg_current_xact_id()::text;
    IF v_memo IS NULL OR v_memo !~ '^[0-9]+:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(,[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})*)?$'
       OR pg_catalog.split_part(v_memo, ':', 1) <> v_xid THEN
        IF v_memo IS NOT NULL AND v_memo <> '' THEN
            PERFORM pg_catalog.set_config('gapto_g2.validadas', '', true);
        END IF;
        RETURN NULL;
    END IF;

    SELECT pg_catalog.array_agg(m.x ORDER BY m.x) INTO v_resto
      FROM pg_catalog.unnest(pg_catalog.string_to_array(pg_catalog.split_part(v_memo, ':', 2), ',')::uuid[]) AS m(x)
     WHERE NOT (m.x = ANY (v_fs));
    PERFORM pg_catalog.set_config('gapto_g2.validadas',
        v_xid || ':' || coalesce(pg_catalog.array_to_string(v_resto, ','), ''), true);
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_borrar_memo_cuadro_hipoteca() IS
    'F06 T4 0356 G2: invalidacion del memo gapto_g2.validadas. Trigger ordinario AFTER ROW con los eventos de T3, T4 y T5; quita del memo las financiaciones de OLD y NEW (INSERT: NEW; UPDATE: OLD y NEW; DELETE: OLD). Memo ausente, mal formado o de otra transaccion: se vacia.';

-- ============================================================
-- F3 (reemplazada) · G2 despachador con memo. El nucleo no cambia.
-- ============================================================
CREATE OR REPLACE FUNCTION gapto.fn_check_cuadro_hipoteca()
RETURNS trigger AS $fn$
DECLARE
    v_fs      uuid[];
    v_memo    text;
    v_xid     text;
    v_hechas  uuid[] := '{}';
    v_validar uuid[];
BEGIN
    CASE TG_TABLE_NAME
        WHEN 'financiacion_cuotas' THEN
            IF TG_OP = 'INSERT' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            ELSIF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[OLD.financiacion_entidad_id];
            END IF;
        WHEN 'financiaciones' THEN
            v_fs := ARRAY[NEW.entidad_id];
        WHEN 'financiacion_condiciones_versiones' THEN
            IF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            END IF;
        ELSE
            RAISE EXCEPTION 'INV-0354-G2: fn_check_cuadro_hipoteca, tabla no contemplada %', TG_TABLE_NAME;
    END CASE;

    v_memo := pg_catalog.current_setting('gapto_g2.validadas', true);
    v_xid := pg_catalog.pg_current_xact_id()::text;
    IF v_memo IS NOT NULL
       AND v_memo ~ '^[0-9]+:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(,[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})*)?$'
       AND pg_catalog.split_part(v_memo, ':', 1) = v_xid THEN
        v_hechas := coalesce(pg_catalog.string_to_array(pg_catalog.split_part(v_memo, ':', 2), ',')::uuid[], '{}');
    END IF;

    SELECT pg_catalog.array_agg(DISTINCT f.x) INTO v_validar
      FROM pg_catalog.unnest(v_fs) AS f(x)
     WHERE f.x IS NOT NULL AND NOT (f.x = ANY (v_hechas));
    IF v_validar IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM gapto.fn_validar_cuadro_hipoteca(v_validar);

    PERFORM pg_catalog.set_config('gapto_g2.validadas',
        v_xid || ':' || (SELECT pg_catalog.array_to_string(pg_catalog.array_agg(DISTINCT u.x ORDER BY u.x), ',')
                           FROM pg_catalog.unnest(v_hechas || v_validar) AS u(x)), true);
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_cuadro_hipoteca() IS
    'F06-01H 0354 G2 despachador (contrato v0.4 §10.1.2), con memo de 0356 (F06 T4, P-RB206-1). Por TG_TABLE_NAME, sin SQL dinamico; OLD y NEW solo aportan identificadores. Llama a fn_validar_cuadro_hipoteca solo con las financiaciones que no estan en gapto_g2.validadas de esta transaccion y, tras validar sin error, las anade. R-G2-M1 aceptado: el GUC es falsificable por quien ejecute SQL con gapto_runtime.';

CREATE TRIGGER trg_financiacion_cuotas__borrar_memo_g2
    AFTER INSERT OR UPDATE OF capital_previsto, numero_cuota, financiacion_entidad_id OR DELETE
    ON gapto.financiacion_cuotas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_borrar_memo_cuadro_hipoteca();

CREATE TRIGGER trg_financiaciones__borrar_memo_g2
    AFTER UPDATE OF capital_original_contratado, tipo_financiacion
    ON gapto.financiaciones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_borrar_memo_cuadro_hipoteca();

CREATE TRIGGER trg_financiacion_condiciones_versiones__borrar_memo_g2
    AFTER INSERT OR UPDATE OF motivo_version, hecho_causa_id, financiacion_entidad_id
    ON gapto.financiacion_condiciones_versiones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_borrar_memo_cuadro_hipoteca();

RESET ROLE;

DO $postcheck_0356$
DECLARE
    v_n bigint;
    v_t text;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_language l ON l.oid = p.prolang
     WHERE p.oid IN ('gapto.fn_borrar_memo_cuadro_hipoteca()'::pg_catalog.regprocedure,
                     'gapto.fn_check_cuadro_hipoteca()'::pg_catalog.regprocedure)
       AND NOT p.prosecdef AND l.lanname = 'plpgsql' AND p.proacl IS NULL
       AND p.proowner = 'gapto_owner'::pg_catalog.regrole
       AND p.prorettype = 'trigger'::pg_catalog.regtype
       AND pg_catalog.strpos(p.prosrc, '--') = 0
       AND pg_catalog.strpos(p.prosrc, 'EXECUTE ') = 0;
    IF v_n <> 2 THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-01: funciones de 0356 conformes = % (esperadas 2: invoker, plpgsql, gapto_owner, ACL por defecto, sin comentarios ni SQL dinamico)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger n
      JOIN pg_catalog.pg_trigger g ON g.tgrelid = n.tgrelid
     WHERE NOT n.tgisinternal AND n.tgenabled = 'O' AND NOT n.tgdeferrable AND NOT n.tginitdeferred
       AND n.tgconstraint = 0 AND n.tgqual IS NULL
       AND n.tgfoid = 'gapto.fn_borrar_memo_cuadro_hipoteca()'::pg_catalog.regprocedure
       AND n.tgtype = g.tgtype AND n.tgattr::text = g.tgattr::text
       AND g.tgfoid = 'gapto.fn_check_cuadro_hipoteca()'::pg_catalog.regprocedure
       AND g.tgdeferrable AND g.tginitdeferred AND g.tgconstraint <> 0 AND g.tgenabled = 'O'
       AND ((n.tgname = 'trg_financiacion_cuotas__borrar_memo_g2' AND g.tgname = 'trg_financiacion_cuotas__cuadro_hipoteca')
         OR (n.tgname = 'trg_financiaciones__borrar_memo_g2' AND g.tgname = 'trg_financiaciones__cuadro_hipoteca')
         OR (n.tgname = 'trg_financiacion_condiciones_versiones__borrar_memo_g2'
             AND g.tgname = 'trg_financiacion_condiciones_versiones__cuadro_hipoteca'))
       AND n.tgname < g.tgname;
    IF v_n <> 3 THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-02: triggers de invalidacion conformes = % (esperados 3: no diferibles, habilitados, mismos tgtype y tgattr que T3..T5 y nombre que ordena antes)', v_n;
    END IF;

    SELECT pg_catalog.md5(p.prosrc) INTO v_t FROM pg_catalog.pg_proc p
     WHERE p.oid = 'gapto.fn_validar_cuadro_hipoteca(uuid[])'::pg_catalog.regprocedure;
    IF v_t IS DISTINCT FROM pg_catalog.current_setting('gapto_f06_0356.nucleo_pre') THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-03: el prosrc de fn_validar_cuadro_hipoteca cambio (% -> %)',
            pg_catalog.current_setting('gapto_f06_0356.nucleo_pre'), v_t;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> pg_catalog.current_setting('gapto_f06_0356.funciones_pre')::bigint + 1 THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: funciones = % (esperadas % + 1)', v_n, pg_catalog.current_setting('gapto_f06_0356.funciones_pre');
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> pg_catalog.current_setting('gapto_f06_0356.triggers_pre')::bigint + 3 THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: triggers no internos = % (esperados % + 3)', v_n, pg_catalog.current_setting('gapto_f06_0356.triggers_pre');
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> pg_catalog.current_setting('gapto_f06_0356.ctriggers_pre')::bigint THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: constraint triggers = % (esperados %, sin cambios)', v_n, pg_catalog.current_setting('gapto_f06_0356.ctriggers_pre');
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r' AND c.relforcerowsecurity;
    IF v_n <> pg_catalog.current_setting('gapto_f06_0356.force_pre')::bigint THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: tablas con FORCE RLS = % (esperadas %)', v_n, pg_catalog.current_setting('gapto_f06_0356.force_pre');
    END IF;
    SELECT pg_catalog.count(*)::text || ':' || pg_catalog.md5(coalesce(pg_catalog.string_agg(
               p.tablename || ':' || p.policyname || ':' || p.cmd || ':' || coalesce(p.qual, '-') || ':' || coalesce(p.with_check, '-'),
               E'\n' ORDER BY p.tablename, p.policyname), ''))
      INTO v_t FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_t <> pg_catalog.current_setting('gapto_f06_0356.policies_pre') THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: policies cambiadas (% -> %)', pg_catalog.current_setting('gapto_f06_0356.policies_pre'), v_t;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_class c
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind IN ('r', 'v', 'p')
       AND a.grantee = 'gapto_runtime'::pg_catalog.regrole;
    IF v_n <> pg_catalog.current_setting('gapto_f06_0356.privilegios_pre')::bigint THEN
        RAISE EXCEPTION 'F06-T4-0356 POSTCHECK PO-04: privilegios de tabla de gapto_runtime = % (esperados %)', v_n, pg_catalog.current_setting('gapto_f06_0356.privilegios_pre');
    END IF;

    RAISE NOTICE 'F06-T4-0356 POSTCHECK: OK';
END;
$postcheck_0356$;

COMMIT;
