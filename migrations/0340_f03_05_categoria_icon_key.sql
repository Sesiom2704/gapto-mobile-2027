-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0340_f03_05_categoria_icon_key.sql
-- Ruta: migrations/0340_f03_05_categoria_icon_key.sql
-- Descripcion: FASE 03 REABIERTA PARCIALMENTE / D-197. Materializa
--   SET-CAT-ICON-01 (F09 §12.94): clave de icono opcional por categoria
--   financiera. Unico cambio fisico de la reapertura D-197.
--
--   CONTRATO (D-197, DB Schema 0.94 §15):
--     categorias_financieras.icon_key varchar(80) NULL
--     - sin DEFAULT, sin UNIQUE, sin FK hacia el Design System;
--     - CHECK icon_key IS NULL OR (icon_key <> '' AND icon_key = btrim(icon_key));
--     - NULL = "sin icono explicito": la UI usa un fallback neutro. No hay
--       herencia padre -> hijo ni iconos inventados (D-052: desconocido = NULL).
--
--   LO QUE NO ES FISICO Y NO ES UN OLVIDO. Que la clave exista en la
--   biblioteca de iconos de F09 se valida en aplicacion: un FK o un catalogo
--   en PostgreSQL ataria el esquema al Design System. Que editar icon_key
--   incremente row_version y updated_at es responsabilidad del write-path,
--   como para cualquier otra columna de la tabla: no se crea trigger.
--   ALCANCE DEL CHECK: btrim sin segundo argumento recorta solo el espacio
--   U+0020. Tabuladores, saltos de linea o U+00A0 exteriores NO los rechaza
--   el CHECK; los excluye la validacion contra la biblioteca cerrada de F09.
--   Es el texto literal aprobado por D-197 y no se amplia aqui.
--
--   ACL. Los GRANT de gapto_runtime y gapto_backup sobre esta tabla son de
--   TABLA (0130) y la tabla no tiene ACL por columna, asi que la columna nueva
--   los hereda: runtime puede leerla, insertarla y actualizarla sin GRANT
--   nuevo. El postcheck lo verifica con has_column_privilege y exige que la
--   columna no tenga ACL propia (h7 de D-111 no debe cambiar).
--
--   TRIGGERS. Los cuatro triggers no internos de la tabla son UPDATE OF
--   parent_id o UPDATE OF owner_user_id (0280/0285). Una edicion de icon_key
--   no dispara ninguno. Ningun trigger se crea ni se modifica.
--
--   FORCE RLS (D-094/D-095, D-104). Se aplica el mismo patron que 0330:
--   levantar FORCE, anadir y validar, restaurar FORCE, todo en la MISMA
--   transaccion explicita. El postcheck exige de nuevo 75 tablas con FORCE.
--   D-173: la migration no escribe filas, asi que no hay eventos diferidos
--   pendientes (la tabla tiene constraint triggers diferidos de 0280/0285) y
--   el ALTER TABLE no puede fallar con ObjectInUse.
--
--   FILAS PREEXISTENTES INTACTAS (exigencia de D-197). Antes del ALTER se
--   calcula, bajo gapto_owner y sin FORCE (el owner ve todas las filas), una
--   huella md5 de TODAS las filas de la tabla con todas sus columnas; tras el
--   ALTER se recalcula excluyendo icon_key y se exige identidad, recuento
--   igual y cero filas con icon_key informado. Si ADD COLUMN reescribiese la
--   tabla o algo tocase row_version, updated_at o cualquier otra columna, la
--   migration aborta en todo entorno donde se aplique, con datos reales o
--   sinteticos. La huella viaja en un GUC local a la transaccion.
--
--   IMPACTO FISICO ESPERADO (hipotesis hasta medir, D-197). Columnas
--   777 -> 778; constraints 644 -> 645 (un CHECK). No se mueven FK (175),
--   UNIQUE (41), EXCLUDE (11), indices (287), policies (82), triggers (58),
--   funciones (28), vistas (3), FORCE RLS (75) ni la matriz de runtime
--   (80/74/68/48). De las ocho huellas D-111 cambian solo h1 y h2.
--
--   MIGRACION V3. V3 no aporta iconos: icon_key queda NULL en todas las
--   categorias migradas y no se fabrican valores.
--
--   D-179. No se aplica persistentemente a Supabase: permanece en 0310.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0340$
DECLARE
    v_n   bigint;
    v_rep text := '';
BEGIN
    -- 'SET', no 'USAGE': las pertenencias son INHERIT FALSE / SET TRUE (D-189).
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F03-05-0340 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    -- Estado de partida: head 0330 (definicion canonica de h1: r, v, p).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p')
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 777 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 777: 0340 exige 0330 aplicada);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 644 THEN
        v_rep := v_rep || pg_catalog.format(' constraints = %s (esperadas 644 antes de 0340);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'categorias_financieras'
       AND a.attname = 'icon_key' AND NOT a.attisdropped;
    IF v_n <> 0 THEN
        v_rep := v_rep || ' categorias_financieras.icon_key ya existe;';
    END IF;

    -- La herencia del ACL de tabla es la razon por la que no hay GRANT.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'categorias_financieras'
       AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s columna(s) de categorias_financieras con ACL propia; 0340 razona sobre ACL de tabla;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'categorias_financieras'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' categorias_financieras sin RLS/FORCE RLS antes de levantarlo;';
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-05-0340 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-05-0340 PRECHECK: OK';
END;
$precheck_0340$;

SET ROLE gapto_owner;

ALTER TABLE gapto.categorias_financieras NO FORCE ROW LEVEL SECURITY;

-- Huella de las filas preexistentes, tomada como owner y sin FORCE.
SELECT pg_catalog.set_config('gapto_f03_05.huella_pre',
       (SELECT pg_catalog.count(*)::text || ':' ||
               coalesce(pg_catalog.md5(pg_catalog.string_agg(pg_catalog.to_jsonb(c)::text, E'\n' ORDER BY c.id)), '-')
          FROM gapto.categorias_financieras c),
       true);

ALTER TABLE gapto.categorias_financieras
    ADD COLUMN icon_key varchar(80);

ALTER TABLE gapto.categorias_financieras
    ADD CONSTRAINT ck_categorias_financieras__icon_key_no_vacia_recortada
    CHECK (icon_key IS NULL OR (icon_key <> '' AND icon_key = btrim(icon_key)));

DO $filas_0340$
DECLARE
    v_pre  text := pg_catalog.current_setting('gapto_f03_05.huella_pre', true);
    v_post text;
    v_n    bigint;
BEGIN
    SELECT pg_catalog.count(*)::text || ':' ||
           coalesce(pg_catalog.md5(pg_catalog.string_agg((pg_catalog.to_jsonb(c) - 'icon_key')::text, E'\n' ORDER BY c.id)), '-')
      INTO v_post
      FROM gapto.categorias_financieras c;
    IF v_pre IS NULL OR v_pre = '' OR v_post IS DISTINCT FROM v_pre THEN
        RAISE EXCEPTION 'F03-05-0340 FILAS: las filas preexistentes cambiaron (pre=%, post=%)', v_pre, v_post;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.categorias_financieras WHERE icon_key IS NOT NULL;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-05-0340 FILAS: % fila(s) con icon_key informado tras la migration', v_n;
    END IF;

    RAISE NOTICE 'F03-05-0340 FILAS: OK (%)', v_post;
END;
$filas_0340$;

ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY;

COMMENT ON COLUMN gapto.categorias_financieras.icon_key IS
    'D-197 / SET-CAT-ICON-01: clave de icono de la biblioteca F09. NULL = sin icono explicito (fallback neutro en UI); sin herencia padre-hijo. La pertenencia a la biblioteca se valida en aplicacion; editarla incrementa row_version y updated_at en el write-path.';

RESET ROLE;

DO $postcheck_0340$
DECLARE
    v_n   bigint;
    v_rep text := '';
BEGIN
    -- 1) Columna con tipo exacto, nullable y sin DEFAULT.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'categorias_financieras' AND a.attname = 'icon_key'
       AND NOT a.attisdropped AND NOT a.attnotnull AND NOT a.atthasdef
       AND a.attacl IS NULL
       AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'character varying(80)';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' icon_key no es varchar(80) nullable, sin DEFAULT y sin ACL propia;';
    END IF;

    -- 2) Exactamente UNA constraint toca icon_key: el CHECK, validado e inmediato.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
      JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attname = 'icon_key'
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'categorias_financieras'
       AND a.attnum = ANY (k.conkey);
    IF v_n <> 1 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sobre icon_key = %s (esperada 1: sin UNIQUE ni FK);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND k.conname = 'ck_categorias_financieras__icon_key_no_vacia_recortada'
       AND k.contype = 'c' AND k.convalidated AND NOT k.condeferrable;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta ck_categorias_financieras__icon_key_no_vacia_recortada validado;';
    END IF;

    -- 3) Ningun indice sobre icon_key.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_index i
      JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attname = 'icon_key'
     WHERE i.indrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND a.attnum = ANY (i.indkey);
    IF v_n <> 0 THEN
        v_rep := v_rep || ' existe un indice sobre icon_key;';
    END IF;

    -- 4) Herencia efectiva del ACL de tabla.
    IF NOT (pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'icon_key', 'SELECT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'icon_key', 'INSERT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'icon_key', 'UPDATE')
        AND pg_catalog.has_column_privilege('gapto_backup',  'gapto.categorias_financieras', 'icon_key', 'SELECT')) THEN
        v_rep := v_rep || ' gapto_runtime/gapto_backup no heredan el privilegio esperado sobre icon_key;';
    END IF;

    -- 5) Recuentos globales del head 0340.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p')
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 778 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 778);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 645 THEN
        v_rep := v_rep || pg_catalog.format(' constraints = %s (esperadas 645);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    -- 6) Lo que 0340 NO debe mover.
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        v_rep := v_rep || pg_catalog.format(' FK = %s (esperadas 175);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'u';
    IF v_n <> 41 THEN
        v_rep := v_rep || pg_catalog.format(' UNIQUE constraints = %s (esperadas 41);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        v_rep := v_rep || pg_catalog.format(' policies = %s (esperadas 82);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 48 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 48; 0340 no toca ACL);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-05-0340 POSTCHECK:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-05-0340 POSTCHECK: OK';
END;
$postcheck_0340$;

COMMIT;
