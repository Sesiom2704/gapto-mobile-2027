-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0355_f06_02_03_alq_roles_participante.sql
-- Ruta: migrations/0355_f06_02_03_alq_roles_participante.sql
-- Descripcion: FASE 06 · T3-F06 bloque 3 F06-02/03 (contratos de alquiler,
--   servicios y terceros, sin renta). MIG-ALQ-ROLES: catalogo de roles de
--   participante de contrato ampliado con AGENCIA y ADMINISTRADOR (D24 del
--   lote 40, mantenida en el lote 42; Q-T3D-21; AJ-T3D-10). Migration
--   forward-only sobre 0354 (no edita 0001..0354). Contrato N1 F06-02/03
--   v1.1 §IX y §1.1; mandato MANDATO_T3_03_F06-02-03_v1.2 §2.1, §6 (STOP B
--   autorizado expresamente solo para esta migration) y §9. Regimen WM 0.34
--   (D-211): humo de Neon bloqueante y acumulativo con 0354; Supabase en
--   divergencia registrada.
--
--   CONTRATO (§IX, literal).
--     Unica DDL: sustituir gapto.contrato_participantes.ck_contrato_participantes__rol
--     CONSERVANDO EL NOMBRE por la misma definicion mas 'AGENCIA' y
--     'ADMINISTRADOR'. Vigente (0050:192-193): PROPIETARIO, INQUILINO,
--     AVALISTA, GESTOR. Tras 0355: esos cuatro mas AGENCIA y ADMINISTRADOR.
--     La sustitucion es un unico ALTER TABLE con DROP y ADD de la constraint
--     (atomico; la validacion de las filas existentes no puede fallar porque
--     el conjunto nuevo contiene al anterior).
--
--   LO QUE NO HACE (a proposito). Sin filas, sin GRANT/REVOKE, sin tablas,
--   columnas, indices, otras constraints, policies, funciones ni triggers.
--   La semantica de los roles nuevos (no cuentan para FORMALIZADO; principal
--   opcional y como mucho uno por la EXCLUDE ex_contrato_participantes__
--   principal_por_rol de 0100, que ya es por rol) vive en el servicio
--   (oraculos O-23/O-24), no aqui. No toca HEAD_AUTORIZADO_ENVDEV (C7 del
--   cierre del tren, fuera de L-06-T3).
--
--   PATRON FORCE RLS (el de 0351/0353). BEGIN -> precheck fail-closed con la
--   identidad de la conexion -> SET ROLE gapto_owner -> NO FORCE RLS en
--   contrato_participantes -> huella de filas (recuento + md5 de
--   to_jsonb(fila) ordenado por id; el propietario sin FORCE ve todas las
--   filas sin GUC de tenant) -> ALTER TABLE (DROP + ADD) -> filas identicas
--   -> FORCE RLS restaurado -> RESET ROLE -> postcheck -> COMMIT. Todo en la
--   MISMA transaccion; SQL cualificado (pg_catalog., gapto.), sin depender de
--   search_path.
--
--   PRECHECKS (fail-closed; si algo difiere -> STOP 8 del contrato / STOP
--   especifico 2 del mandato: NO se corrige nada).
--     - el rol de conexion puede asumir gapto_owner (pg_has_role SET, D-189);
--     - head de partida 0354: funcion gapto.fn_validar_cuadro_hipoteca(uuid[])
--       presente; 34 funciones, 65 triggers no internos, 44 constraint
--       triggers, 655 constraints sin contype = 'n' (HT2-13), 75 tablas con
--       FORCE RLS, 82 policies, 287 indices;
--     - la constraint existe una sola vez, es CHECK, esta validada y
--       pg_get_constraintdef = definicion vigente LITERAL (la de 0050). Si ya
--       es la definicion nueva: 0355 ya aplicada, no se reaplica;
--     - contrato_participantes con RLS y FORCE activos;
--     - se registran (NOTICE) el COUNT(*) visible de contrato_participantes,
--       su ACL de tabla, la huella de sus policies y la huella del resto de
--       constraints declarativas del schema para el postcheck.
--   POSTCHECKS (fail-closed).
--     - pg_get_constraintdef = definicion nueva LITERAL, una sola constraint
--       con ese nombre, CHECK validada sobre la columna rol;
--     - mismo COUNT(*) y mismas filas (huella antes = despues, como owner
--       sin FORCE);
--     - relrowsecurity y relforcerowsecurity iguales a antes (true/true);
--     - ACL de la tabla (relacl) y policies de la tabla iguales a antes;
--     - resto de constraints declarativas del schema identicas a antes;
--     - recuentos globales del head 0354 sin cambios (constraints 655 sin
--       'n', funciones 34, triggers 65, constraint triggers 44, indices 287,
--       policies 82, FORCE 75, tablas 80, privilegios de tabla de
--       gapto_runtime 266 por aclexplode).
--
--   DEFINICIONES LITERALES. Derivadas del DDL de 0050 con la forma de
--   pg_get_constraintdef que test_046 ya mide para CHECK equivalentes sobre
--   varchar (ck_hecho_efectos__causa_valor_activo_dominio,
--   ck_contrato_servicios__modo_reparto_dominio). Se CONFIRMAN en el replay
--   0001..0355 de la clean-room (D-DISC-10 de la revalidacion del paso 1): si
--   el precheck no casa con la base real, la migration aborta (fail-closed) y
--   es STOP B, sin corregir.
--
--   IMPACTO FISICO ESPERADO (a medir en el replay). Cambia solo h2
--   (definicion de una constraint); h1, h3..h8 y los recuentos identicos a
--   0354 (788/655/287/82/65/34/1024/3).
--
-- Version: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03; mandato v1.2 §9, contrato v1.1 §IX): migration nueva.
-- ============================================================

BEGIN;

DO $precheck_0355$
DECLARE
    v_def_0354 CONSTANT text := $d$CHECK (((rol)::text = ANY ((ARRAY['PROPIETARIO'::character varying, 'INQUILINO'::character varying, 'AVALISTA'::character varying, 'GESTOR'::character varying])::text[])))$d$;
    v_def_0355 CONSTANT text := $d$CHECK (((rol)::text = ANY ((ARRAY['PROPIETARIO'::character varying, 'INQUILINO'::character varying, 'AVALISTA'::character varying, 'GESTOR'::character varying, 'AGENCIA'::character varying, 'ADMINISTRADOR'::character varying])::text[])))$d$;
    v_n   bigint;
    v_def text;
    v_m   text;
    v_rep text := '';
BEGIN
    RAISE NOTICE 'F06-02-03-0355 PRECHECK: conexion user=% session_user=% db=% servidor=%',
        current_user, session_user, pg_catalog.current_database(), pg_catalog.current_setting('server_version');

    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F06-02-03-0355 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    -- La constraint: una sola, CHECK, validada, con la definicion vigente literal.
    SELECT pg_catalog.count(*), pg_catalog.min(pg_catalog.pg_get_constraintdef(k.oid))
      INTO v_n, v_def
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND k.conname = 'ck_contrato_participantes__rol';
    IF v_n = 1 AND v_def = v_def_0355 THEN
        RAISE EXCEPTION 'F06-02-03-0355 PRECHECK: 0355 ya esta aplicada (ck_contrato_participantes__rol ya admite AGENCIA y ADMINISTRADOR); no se reaplica';
    END IF;
    IF v_n <> 1 THEN
        v_rep := v_rep || pg_catalog.format(' ck_contrato_participantes__rol aparece %s vez/veces (esperada 1);', v_n);
    ELSIF v_def IS DISTINCT FROM v_def_0354 THEN
        v_rep := v_rep || pg_catalog.format(' definicion vigente de ck_contrato_participantes__rol distinta de la literal del contrato: %s;', v_def);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND k.conname = 'ck_contrato_participantes__rol'
       AND k.contype = 'c' AND k.convalidated;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' ck_contrato_participantes__rol no es una CHECK validada;';
    END IF;

    -- Head de partida 0354: su funcion marcadora y sus recuentos.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = 'fn_validar_cuadro_hipoteca';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta gapto.fn_validar_cuadro_hipoteca (head anterior a 0354);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 34 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 34 en 0354);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 65 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 65 en 0354);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 44 THEN
        v_rep := v_rep || pg_catalog.format(' constraint triggers = %s (esperados 44 en 0354);', v_n);
    END IF;

    -- Sin contype = 'n': PostgreSQL 18 cataloga los NOT NULL (HT2-13).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype <> 'n';
    IF v_n <> 655 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sin NOT NULL = %s (esperadas 655 en 0354);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        v_rep := v_rep || pg_catalog.format(' policies = %s (esperadas 82);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.oid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' contrato_participantes sin RLS/FORCE RLS antes de levantarlo;';
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-02-03-0355 PRECHECK: BLOQUEA (STOP 8 del contrato; STOP B del mandato), no se corrige nada:%', v_rep;
    END IF;

    -- Huellas para el postcheck (transaccionales).
    PERFORM pg_catalog.set_config('gapto_f06_0355.acl_pre',
        coalesce((SELECT c.relacl::text FROM pg_catalog.pg_class c
                   WHERE c.oid = 'gapto.contrato_participantes'::pg_catalog.regclass), '-'), true);
    PERFORM pg_catalog.set_config('gapto_f06_0355.policies_pre',
        coalesce((SELECT pg_catalog.count(*)::text || ':' ||
                         pg_catalog.md5(pg_catalog.string_agg(p.policyname || ':' || p.cmd || ':' ||
                                        coalesce(p.qual, '-') || ':' || coalesce(p.with_check, '-'),
                                        E'\n' ORDER BY p.policyname))
                    FROM pg_catalog.pg_policies p
                   WHERE p.schemaname = 'gapto' AND p.tablename = 'contrato_participantes'), '-'), true);
    SELECT pg_catalog.count(*)::text || ':' ||
           pg_catalog.md5(pg_catalog.string_agg(k.conrelid::pg_catalog.regclass::text || '.' || k.conname || ':' ||
                                                pg_catalog.pg_get_constraintdef(k.oid),
                                                E'\n' ORDER BY k.conrelid::pg_catalog.regclass::text, k.conname))
      INTO v_m
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype IN ('p', 'u', 'f', 'c', 'x')
       AND NOT (k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
                AND k.conname = 'ck_contrato_participantes__rol');
    PERFORM pg_catalog.set_config('gapto_f06_0355.resto_constraints_pre', v_m, true);

    RAISE NOTICE 'F06-02-03-0355 PRECHECK: OK (definicion vigente = literal de 0050; acl=%)',
        pg_catalog.current_setting('gapto_f06_0355.acl_pre', true);
END;
$precheck_0355$;

SET ROLE gapto_owner;

-- FORCE se levanta ANTES de contar: el propietario sin FORCE ve todas las
-- filas sin GUC de tenant. Se restaura en esta misma transaccion.
ALTER TABLE gapto.contrato_participantes NO FORCE ROW LEVEL SECURITY;

DO $filas_pre_0355$
DECLARE
    v_n bigint;
BEGIN
    IF current_user <> 'gapto_owner' THEN
        RAISE EXCEPTION 'F06-02-03-0355 FILAS: se esperaba gapto_owner y es %', current_user;
    END IF;
    IF (SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c
         WHERE c.oid = 'gapto.contrato_participantes'::pg_catalog.regclass) THEN
        RAISE EXCEPTION 'F06-02-03-0355 FILAS: FORCE RLS sigue activo; el recuento no seria completo';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.contrato_participantes;
    PERFORM pg_catalog.set_config('gapto_f06_0355.filas_pre',
        (SELECT pg_catalog.count(*)::text || ':' ||
                coalesce(pg_catalog.md5(pg_catalog.string_agg(pg_catalog.to_jsonb(p)::text, E'\n' ORDER BY p.id)), '-')
           FROM gapto.contrato_participantes p), true);
    RAISE NOTICE 'F06-02-03-0355 FILAS: COUNT(*) de contrato_participantes antes = % (huella %)',
        v_n, pg_catalog.current_setting('gapto_f06_0355.filas_pre', true);
END;
$filas_pre_0355$;

ALTER TABLE gapto.contrato_participantes
    DROP CONSTRAINT ck_contrato_participantes__rol,
    ADD CONSTRAINT ck_contrato_participantes__rol
        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR','AGENCIA','ADMINISTRADOR'));

DO $filas_post_0355$
DECLARE
    v_pre  text := pg_catalog.current_setting('gapto_f06_0355.filas_pre', true);
    v_post text;
BEGIN
    SELECT pg_catalog.count(*)::text || ':' ||
           coalesce(pg_catalog.md5(pg_catalog.string_agg(pg_catalog.to_jsonb(p)::text, E'\n' ORDER BY p.id)), '-')
      INTO v_post
      FROM gapto.contrato_participantes p;
    IF v_pre IS NULL OR v_pre = '' OR v_post IS DISTINCT FROM v_pre THEN
        RAISE EXCEPTION 'F06-02-03-0355 FILAS: las filas de contrato_participantes cambiaron (pre=%, post=%)', v_pre, v_post;
    END IF;
    RAISE NOTICE 'F06-02-03-0355 FILAS: OK (%)', v_post;
END;
$filas_post_0355$;

ALTER TABLE gapto.contrato_participantes FORCE ROW LEVEL SECURITY;

RESET ROLE;

DO $postcheck_0355$
DECLARE
    v_def_0355 CONSTANT text := $d$CHECK (((rol)::text = ANY ((ARRAY['PROPIETARIO'::character varying, 'INQUILINO'::character varying, 'AVALISTA'::character varying, 'GESTOR'::character varying, 'AGENCIA'::character varying, 'ADMINISTRADOR'::character varying])::text[])))$d$;
    v_n   bigint;
    v_def text;
    v_m   text;
    v_rep text := '';
BEGIN
    -- 1) Definicion nueva literal, una sola constraint con ese nombre, CHECK validada sobre rol.
    SELECT pg_catalog.count(*), pg_catalog.min(pg_catalog.pg_get_constraintdef(k.oid))
      INTO v_n, v_def
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND k.conname = 'ck_contrato_participantes__rol';
    IF v_n <> 1 OR v_def IS DISTINCT FROM v_def_0355 THEN
        v_rep := v_rep || pg_catalog.format(' ck_contrato_participantes__rol: %s constraint(s), definicion %s (esperada la literal nueva);', v_n, v_def);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
       AND k.conname = 'ck_contrato_participantes__rol'
       AND k.contype = 'c' AND k.convalidated
       AND k.conkey = ARRAY[(SELECT a.attnum FROM pg_catalog.pg_attribute a
                              WHERE a.attrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
                                AND a.attname = 'rol' AND NOT a.attisdropped)]::int2[];
    IF v_n <> 1 THEN
        v_rep := v_rep || ' ck_contrato_participantes__rol no es una CHECK validada sobre la columna rol;';
    END IF;

    -- 2) RLS y FORCE iguales a antes (true/true).
    IF NOT (SELECT c.relrowsecurity AND c.relforcerowsecurity FROM pg_catalog.pg_class c
             WHERE c.oid = 'gapto.contrato_participantes'::pg_catalog.regclass) THEN
        v_rep := v_rep || ' contrato_participantes sin RLS o sin FORCE RLS tras la migration;';
    END IF;

    -- 3) ACL y policies de la tabla iguales a antes.
    SELECT coalesce(c.relacl::text, '-') INTO v_m FROM pg_catalog.pg_class c
     WHERE c.oid = 'gapto.contrato_participantes'::pg_catalog.regclass;
    IF v_m IS DISTINCT FROM pg_catalog.current_setting('gapto_f06_0355.acl_pre', true) THEN
        v_rep := v_rep || pg_catalog.format(' ACL de contrato_participantes cambiada (%s);', v_m);
    END IF;
    SELECT coalesce((SELECT pg_catalog.count(*)::text || ':' ||
                            pg_catalog.md5(pg_catalog.string_agg(p.policyname || ':' || p.cmd || ':' ||
                                           coalesce(p.qual, '-') || ':' || coalesce(p.with_check, '-'),
                                           E'\n' ORDER BY p.policyname))
                       FROM pg_catalog.pg_policies p
                      WHERE p.schemaname = 'gapto' AND p.tablename = 'contrato_participantes'), '-')
      INTO v_m;
    IF v_m IS DISTINCT FROM pg_catalog.current_setting('gapto_f06_0355.policies_pre', true) THEN
        v_rep := v_rep || ' policies de contrato_participantes cambiadas;';
    END IF;

    -- 4) Resto de constraints declarativas del schema identicas a antes.
    SELECT pg_catalog.count(*)::text || ':' ||
           pg_catalog.md5(pg_catalog.string_agg(k.conrelid::pg_catalog.regclass::text || '.' || k.conname || ':' ||
                                                pg_catalog.pg_get_constraintdef(k.oid),
                                                E'\n' ORDER BY k.conrelid::pg_catalog.regclass::text, k.conname))
      INTO v_m
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype IN ('p', 'u', 'f', 'c', 'x')
       AND NOT (k.conrelid = 'gapto.contrato_participantes'::pg_catalog.regclass
                AND k.conname = 'ck_contrato_participantes__rol');
    IF v_m IS DISTINCT FROM pg_catalog.current_setting('gapto_f06_0355.resto_constraints_pre', true) THEN
        v_rep := v_rep || ' otras constraints del schema cambiaron;';
    END IF;

    -- 5) Recuentos globales del head 0354 sin cambios.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype <> 'n';
    IF v_n <> 655 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sin NOT NULL = %s (esperadas 655);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 34 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 34);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 65 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 65);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 44 THEN
        v_rep := v_rep || pg_catalog.format(' constraint triggers = %s (esperados 44);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        v_rep := v_rep || pg_catalog.format(' policies = %s (esperadas 82);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r';
    IF v_n <> 80 THEN
        v_rep := v_rep || pg_catalog.format(' tablas = %s (esperadas 80);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind IN ('r', 'v', 'p')
       AND a.grantee = 'gapto_runtime'::pg_catalog.regrole;
    IF v_n <> 266 THEN
        v_rep := v_rep || pg_catalog.format(' privilegios de tabla de gapto_runtime = %s (esperados 266);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-02-03-0355 POSTCHECK:%', v_rep;
    END IF;
    RAISE NOTICE 'F06-02-03-0355 POSTCHECK: OK';
END;
$postcheck_0355$;

COMMIT;
