-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0353_f06_01_categoria_asociada_vivienda.sql
-- Ruta: migrations/0353_f06_01_categoria_asociada_vivienda.sql
-- Descripcion: FASE 06 · T2-F06 bloque 3 CAT-VIV. Marca «Asociada a vivienda»
--   por categoria financiera. Migration forward-only sobre 0352 (no edita
--   0001..0352). Reapertura PARCIAL de F03 por 0353 (L-03, aprobada «tal cual»
--   por Moises, lote 34, d593a15d...); regimen de proveedor WM 0.33 (D-209 con
--   la enmienda D-211): humo de Neon bloqueante, no certificacion. Dictamen de
--   diseno 2/3 del tren 2 (Q-CV-01, AJ-T2-05, AJ-T2-07). Mandato
--   MANDATO_T2_3_CAT-VIV_0353_N1_v1.1 §2.1 y literal de autorizacion v1.1.
--   El «0x» de L-03 se concreta en 01 (F06-01, receptor del vinculo AFECTA_A).
--
--   CONTRATO.
--     gapto.categorias_financieras.asociada_vivienda boolean NOT NULL DEFAULT false
--     - unica DDL de la migration; COMMENT ON COLUMN admitido (patron 0340/0352);
--     - false = la categoria no exige propiedad; true = todo writer que cree un
--       hecho real con efecto GASTO de esta categoria exige una propiedad
--       (OBL-VIV-01; la regla vive en la aplicacion, exigir_propiedad);
--     - la marca no se hereda de padres a hijos (Q-CV-03) y no se copia a
--       ningun hecho: marcar o desmarcar no reinterpreta nada.
--
--   PATRON (el de 0340, la ultima migration que toco esta tabla, y 0352).
--     BEGIN -> precheck fail-closed (con la identidad de la conexion en NOTICE)
--     -> SET ROLE gapto_owner -> NO FORCE RLS -> huella de filas (recuento +
--     md5 de to_jsonb(fila) ordenado por id) y de los triggers de la tabla ->
--     ADD COLUMN -> filas identicas excluyendo la columna nueva y 0 filas en
--     true -> FORCE RLS -> COMMENT -> RESET ROLE -> postcheck -> COMMIT. Todo en
--     la MISMA transaccion. SQL cualificado (pg_catalog., gapto.), sin
--     depender de search_path.
--
--   PRECHECKS (fail-closed, mensaje propio).
--     - el rol puede asumir gapto_owner (pg_has_role SET, D-189);
--     - head de partida 0352: marca de 0352 presente
--       (propiedades.coste_adquisicion_declarado_completo), 787 columnas, 652
--       constraints SIN contar contype = 'n' (PostgreSQL 17 frente a 18,
--       HT2-13), 75 tablas con FORCE y matriz de gapto_runtime 80/74/68/41;
--     - asociada_vivienda inexistente (rechazo de la reaplicacion);
--     - categorias_financieras con RLS y FORCE activos y sin ACL de columna.
--
--   POSTCHECKS (fail-closed).
--     - NOT NULL por pg_attribute.attnotnull, tipo boolean y DEFAULT false
--       exactos (pg_attrdef), attacl IS NULL;
--     - ningun recuento global de constraints que incluya contype = 'n': el
--       control es «652 sin contype = 'n'» (sin cambio);
--     - privilegios heredados: has_column_privilege de gapto_runtime (SELECT,
--       INSERT, UPDATE) y de gapto_backup (SELECT); matriz runtime sin cambios;
--     - 788 columnas, 287 indices, 75 tablas con FORCE y la tabla con FORCE;
--     - triggers de la tabla intactos (UPDATE OF parent_id y UPDATE OF
--       owner_user_id de 0280/0285): huella de sus definiciones antes = despues.
--
--   LO QUE NO HACE A PROPOSITO.
--     - Ni CHECK (boolean NOT NULL basta), ni indice, ni trigger, ni FK, ni
--       vista, ni funcion, ni GRANT: los GRANT de gapto_runtime/gapto_backup
--       son de TABLA (0130) y la columna los hereda.
--     - No marca ninguna categoria: todas quedan en false sin reescritura (ADD
--       COLUMN con DEFAULT constante es solo de catalogo). Migracion V3: sin
--       mapping, todas las categorias migradas en false (D-052).
--     - No crea rutas ni writers: el unico writer de la columna es
--       categorias/servicio.py::marcar_vivienda (C-CAT-VIV-01).
--
--   IMPACTO FISICO (medido en laboratorio local PostgreSQL 17.5 en UTC; lo
--     confirma el humo de Neon). h1 cambia (+1 columna, NOT NULL y DEFAULT en
--     su definicion); h2 NO cambia en PostgreSQL <= 17 (los NOT NULL no estan
--     en pg_constraint y el DEFAULT lo cubre h1); h3..h8 identicas a 0352.
--     Recuentos 788/652/287/82/58/28/1024/3.
--
--   DESPLIEGUE. Aditiva: el codigo anterior no lee la columna y funciona
--   igual. HEAD_AUTORIZADO_ENVDEV no sube aqui (cambio revisado aparte, con su
--   h2 medida y aceptada; Q-CV-10). Supabase: divergencia registrada (D-211).
-- Version: 0.1.0  -- T2-F06 CAT-VIV N1 (mandato v1.1, L-03): migration nueva.
-- ============================================================

BEGIN;

DO $precheck_0353$
DECLARE
    v_n   bigint;
    v_m   text;
    v_rep text := '';
BEGIN
    RAISE NOTICE 'F06-01-0353 PRECHECK: conexion user=% session_user=% db=% servidor=%',
        current_user, session_user, pg_catalog.current_database(), pg_catalog.current_setting('server_version');

    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F06-01-0353 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    -- Reaplicacion: la columna ya existe -> aborta.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND a.attname = 'asociada_vivienda' AND NOT a.attisdropped;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01-0353 PRECHECK: 0353 ya esta aplicada (asociada_vivienda existe); no se reaplica';
    END IF;

    -- Head de partida 0352: su columna marcadora.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                    WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass
                      AND a.attname = 'coste_adquisicion_declarado_completo' AND NOT a.attisdropped) THEN
        v_rep := v_rep || ' falta propiedades.coste_adquisicion_declarado_completo (head anterior a 0352);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p') AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 787 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 787 en 0352);', v_n);
    END IF;

    -- Sin contype = 'n': PostgreSQL 18 cataloga los NOT NULL (HT2-13).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype <> 'n';
    IF v_n <> 652 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sin NOT NULL = %s (esperadas 652 en 0352);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    SELECT pg_catalog.string_agg(x.n::text, '/' ORDER BY x.orden) INTO v_m
      FROM (SELECT p.orden, (SELECT pg_catalog.count(*)
                               FROM pg_catalog.pg_class c
                               CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
                               JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
                              WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
                                AND r.rolname = 'gapto_runtime' AND acl.privilege_type = p.priv) AS n
              FROM (VALUES (1, 'SELECT'), (2, 'INSERT'), (3, 'UPDATE'), (4, 'DELETE')) AS p(orden, priv)) AS x;
    IF v_m IS DISTINCT FROM '80/74/68/41' THEN
        v_rep := v_rep || pg_catalog.format(' matriz runtime = %s (esperada 80/74/68/41);', v_m);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.oid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' categorias_financieras sin RLS/FORCE RLS antes de levantarlo;';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s columna(s) de categorias_financieras con ACL propia;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0353 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;
    RAISE NOTICE 'F06-01-0353 PRECHECK: OK';
END;
$precheck_0353$;

SET ROLE gapto_owner;

ALTER TABLE gapto.categorias_financieras NO FORCE ROW LEVEL SECURITY;

-- Huellas tomadas como owner y sin FORCE: filas (todas las columnas) y triggers de la tabla.
SELECT pg_catalog.set_config('gapto_f06_0353.huella_pre',
       (SELECT pg_catalog.count(*)::text || ':' ||
               coalesce(pg_catalog.md5(pg_catalog.string_agg(pg_catalog.to_jsonb(c)::text, E'\n' ORDER BY c.id)), '-')
          FROM gapto.categorias_financieras c),
       true);
SELECT pg_catalog.set_config('gapto_f06_0353.triggers_pre',
       (SELECT pg_catalog.count(*)::text || ':' ||
               pg_catalog.md5(pg_catalog.string_agg(t.tgname || ':' || t.tgenabled::text || ':' ||
                                                    pg_catalog.pg_get_triggerdef(t.oid), E'\n' ORDER BY t.tgname))
          FROM pg_catalog.pg_trigger t
         WHERE t.tgrelid = 'gapto.categorias_financieras'::pg_catalog.regclass AND NOT t.tgisinternal),
       true);

ALTER TABLE gapto.categorias_financieras
    ADD COLUMN asociada_vivienda boolean NOT NULL DEFAULT false;

DO $filas_0353$
DECLARE
    v_pre  text := pg_catalog.current_setting('gapto_f06_0353.huella_pre', true);
    v_post text;
    v_n    bigint;
BEGIN
    SELECT pg_catalog.count(*)::text || ':' ||
           coalesce(pg_catalog.md5(pg_catalog.string_agg((pg_catalog.to_jsonb(c) - 'asociada_vivienda')::text, E'\n'
                                   ORDER BY c.id)), '-')
      INTO v_post
      FROM gapto.categorias_financieras c;
    IF v_pre IS NULL OR v_pre = '' OR v_post IS DISTINCT FROM v_pre THEN
        RAISE EXCEPTION 'F06-01-0353 FILAS: las filas preexistentes cambiaron (pre=%, post=%)', v_pre, v_post;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.categorias_financieras c WHERE c.asociada_vivienda;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01-0353 FILAS: % categoria(s) marcadas tras la migration', v_n;
    END IF;
    RAISE NOTICE 'F06-01-0353 FILAS: OK (%)', v_post;
END;
$filas_0353$;

ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY;

COMMENT ON COLUMN gapto.categorias_financieras.asociada_vivienda IS
    'T2-F06 CAT-VIV (L-03, OBL-VIV-01): la categoria exige elegir una propiedad en todo gasto real nuevo (solo efectos GASTO). false por defecto; no se hereda de padres a hijos; marcar o desmarcar no reinterpreta hechos. Unico writer: marcar_vivienda (C-CAT-VIV-01).';

RESET ROLE;

DO $postcheck_0353$
DECLARE
    v_n   bigint;
    v_m   text;
    v_rep text := '';
BEGIN
    -- 1) Columna: boolean, NOT NULL por attnotnull, DEFAULT false exacto, sin ACL propia.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
     WHERE a.attrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND a.attname = 'asociada_vivienda' AND NOT a.attisdropped
       AND a.attnotnull AND a.attacl IS NULL
       AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'boolean'
       AND pg_catalog.pg_get_expr(d.adbin, d.adrelid) = 'false';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' asociada_vivienda no es boolean NOT NULL DEFAULT false sin ACL propia;';
    END IF;

    -- 2) Ninguna constraint (salvo, en PostgreSQL 18, su NOT NULL 'n') ni indice sobre la columna.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_attribute a ON a.attrelid = k.conrelid AND a.attname = 'asociada_vivienda'
     WHERE k.conrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND k.contype <> 'n' AND a.attnum = ANY (k.conkey);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sobre asociada_vivienda = %s (esperadas 0);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_index i
      JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attname = 'asociada_vivienda'
     WHERE i.indrelid = 'gapto.categorias_financieras'::pg_catalog.regclass AND a.attnum = ANY (i.indkey);
    IF v_n <> 0 THEN
        v_rep := v_rep || ' existe un indice sobre asociada_vivienda;';
    END IF;

    -- 3) Constraints globales SIN contype = 'n' (nunca un recuento que los incluya).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype <> 'n';
    IF v_n <> 652 THEN
        v_rep := v_rep || pg_catalog.format(' constraints sin NOT NULL = %s (esperadas 652);', v_n);
    END IF;

    -- 4) Privilegios heredados y matriz runtime sin cambios.
    IF NOT (pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'asociada_vivienda', 'SELECT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'asociada_vivienda', 'INSERT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.categorias_financieras', 'asociada_vivienda', 'UPDATE')
        AND pg_catalog.has_column_privilege('gapto_backup',  'gapto.categorias_financieras', 'asociada_vivienda', 'SELECT')) THEN
        v_rep := v_rep || ' gapto_runtime/gapto_backup no heredan el privilegio esperado sobre asociada_vivienda;';
    END IF;
    SELECT pg_catalog.string_agg(x.n::text, '/' ORDER BY x.orden) INTO v_m
      FROM (SELECT p.orden, (SELECT pg_catalog.count(*)
                               FROM pg_catalog.pg_class c
                               CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
                               JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
                              WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
                                AND r.rolname = 'gapto_runtime' AND acl.privilege_type = p.priv) AS n
              FROM (VALUES (1, 'SELECT'), (2, 'INSERT'), (3, 'UPDATE'), (4, 'DELETE')) AS p(orden, priv)) AS x;
    IF v_m IS DISTINCT FROM '80/74/68/41' THEN
        v_rep := v_rep || pg_catalog.format(' matriz runtime = %s (esperada 80/74/68/41);', v_m);
    END IF;

    -- 5) Recuentos del head 0353.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p') AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 788 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 788 = 787 + 1);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;
    IF NOT (SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c
             WHERE c.oid = 'gapto.categorias_financieras'::pg_catalog.regclass) THEN
        v_rep := v_rep || ' categorias_financieras sin FORCE RLS;';
    END IF;

    -- 6) Triggers de la tabla intactos (0280, 0285).
    SELECT pg_catalog.count(*)::text || ':' ||
           pg_catalog.md5(pg_catalog.string_agg(t.tgname || ':' || t.tgenabled::text || ':' ||
                                                pg_catalog.pg_get_triggerdef(t.oid), E'\n' ORDER BY t.tgname))
      INTO v_m
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid = 'gapto.categorias_financieras'::pg_catalog.regclass AND NOT t.tgisinternal;
    IF v_m IS DISTINCT FROM pg_catalog.current_setting('gapto_f06_0353.triggers_pre', true) THEN
        v_rep := v_rep || ' los triggers de categorias_financieras cambiaron;';
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0353 POSTCHECK:%', v_rep;
    END IF;
    RAISE NOTICE 'F06-01-0353 POSTCHECK: OK';
END;
$postcheck_0353$;

COMMIT;
