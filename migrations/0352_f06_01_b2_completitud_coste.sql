-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0352_f06_01_b2_completitud_coste.sql
-- Ruta: migrations/0352_f06_01_b2_completitud_coste.sql
-- Descripcion: FASE 06 · F06-01 R1 (B2-B3). Declaraciones de completitud del
--   coste de una propiedad con el conjunto de componentes que respaldo cada
--   declaracion (opcion A, politica I-B; decision de Moises del 2026-11-07).
--   Migration forward-only sobre 0351 (no edita 0001..0351). Reapertura
--   acotada de F03 para 0352 dispuesta por D-208 (2026-11-08); dictamen de
--   diseno de 0352 del 2026-11-07 (AJ-0352-01..12); mandato N1 de 0352 v1.4
--   (lote 22). Cuerpo SQL identico byte a byte al prototipo de diseno
--   aprobado (SHA-256 9e9327641435d84d78a9a704ab3654314339b52885cbcfd01f9bf910e07d618f,
--   AJ-0352-01): solo esta cabecera es nueva.
--
--   CONTRATO.
--     1. gapto.propiedades, seis columnas nullable (tres por ambito):
--          coste_adquisicion_declarado_completo boolean NULL
--          coste_adquisicion_declarado_en       date    NULL
--          coste_adquisicion_conjunto_declarado jsonb   NULL
--          mejoras_declaradas_completas         boolean NULL
--          mejoras_declaradas_en                date    NULL
--          mejoras_conjunto_declarado           jsonb   NULL
--        NULL/NULL/NULL = no declarado. Declarado = (true, fecha de corte,
--        array jsonb canonico de componentes). No existe «declarado
--        incompleto»: false no se admite.
--     2. ck_propiedades__coste_adquisicion_declaracion y
--        ck_propiedades__mejoras_declaracion: o las tres NULL, o
--        (true, fecha NOT NULL, conjunto IS NOT NULL y jsonb_typeof =
--        'array'). Seguro frente a NULL: cada rama usa IS [NOT] NULL / IS
--        TRUE. El «conjunto IS NOT NULL» explicito es necesario: sin el,
--        jsonb_typeof(NULL) = 'array' es NULL, la rama declarada da NULL y el
--        CHECK la aceptaria (P0352-02; mutante M-CK-01).
--     3. ck_propiedades__coste_adquisicion_corte_no_anterior: la fecha de
--        corte de la adquisicion no es anterior a fecha_adquisicion (si las
--        dos existen). Mismo patron que ck_propiedades__salida_no_anterior.
--        Las mejoras no tienen esta regla.
--
--   PATRON (el de la cadena, como 0351).
--     - BEGIN; precheck fail-closed con la identidad de la conexion;
--       SET ROLE gapto_owner (propietario de la tabla); RESET ROLE; postcheck;
--       COMMIT.
--     - SQL cualificado con gapto., sin SET search_path.
--     - FORCE RLS levantado y restaurado en la MISMA transaccion en la unica
--       tabla alterada (propiedades). El postcheck verifica 75 tablas con FORCE.
--     - Reaplicar: lo rechaza el precheck (columnas presentes).
--
--   LO QUE NO HACE A PROPOSITO.
--     - No rellena ninguna declaracion: toda propiedad existente queda «no
--       declarada» (NULL/NULL/NULL), que es lo unico fiel sin dato del usuario.
--     - No toca privilegios (AJ-0352-08): gapto_runtime ya tiene UPDATE a nivel
--       de tabla y las columnas nuevas lo heredan; no hay ACL de columna. La
--       unica via de escritura funcional sera C-PROP-05 (B2-B3); C-PROP-01/02
--       no las escriben (no estan en COLUMNAS_PROPIEDAD).
--     - No toca triggers, funciones, policies, indices, vistas ni el seed.
--     - No impone que el conjunto declarado sea el vigente, ni «corte <= hoy»,
--       ni la forma interna de cada elemento del array: la primera depende de
--       otras tablas (la valida L-COSTE en lectura, politica I-B), la segunda
--       de current_date y la tercera es contrato del writer (C-PROP-05).
--     - Ningun writer de componentes escribe estas columnas: la invalidacion
--       es en lectura (I-B), no transaccional.
--     - No representa bajas (L-COSTE las marca NO REPRESENTADAS).
--     - No crea ninguna ruta HTTP ni consumidor (R-L18-01; Alcance 9).
--
--   IMPACTO FISICO (medido en laboratorio UTC en el lote 18; se vuelve a
--     medir en el gate de este N1): h1 columnas +6 (781 -> 787); h2
--     constraints +3 (649 -> 652); h3..h8 identicas a 0351; matriz runtime
--     sin cambios.
--
--   DESPLIEGUE. Solo aditiva y nullable: el codigo de 0351 no lee ni escribe
--   las columnas y funciona igual sobre 0351 y 0352; la guarda de C-PROP-02
--   (AJ-0352-05) solo actua si hay una declaracion. HEAD_AUTORIZADO_ENVDEV
--   solo sube en un cambio revisado. D-179-B: Supabase con gate y
--   autorizacion propios.
-- Versión: 1.0.0  -- N1 de 0352 (mandato v1.4, lote 22): migration definitiva.
-- ============================================================

BEGIN;

DO $precheck_0352$
DECLARE
    v_n   bigint;
    v_rep text := '';
BEGIN
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F06-01-0352 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    -- Reaplicacion: cualquier columna de 0352 aborta.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass AND a.attnum > 0 AND NOT a.attisdropped
       AND a.attname IN ('coste_adquisicion_declarado_completo', 'coste_adquisicion_declarado_en',
                         'coste_adquisicion_conjunto_declarado',
                         'mejoras_declaradas_completas', 'mejoras_declaradas_en',
                         'mejoras_conjunto_declarado');
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01-0352 PRECHECK: 0352 ya esta aplicada (% columnas presentes); no se reaplica', v_n;
    END IF;

    -- Head de partida 0351: su columna marcadora y sus dos arquetipos.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                    WHERE a.attrelid = 'gapto.hecho_efectos'::pg_catalog.regclass
                      AND a.attname = 'causa_valor_activo' AND NOT a.attisdropped) THEN
        v_rep := v_rep || ' falta hecho_efectos.causa_valor_activo (head anterior a 0351);';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.tipos_hecho t
     WHERE t.codigo IN ('ADQUISICION_PATRIMONIAL', 'MEJORA_PATRIMONIAL');
    IF v_n <> 2 THEN
        v_rep := v_rep || pg_catalog.format(' arquetipos de 0351 = %s (esperados 2);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 18 THEN
        v_rep := v_rep || pg_catalog.format(' propiedades tiene %s columnas (esperadas 18);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p') AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 781 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 781 en 0351);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 649 THEN
        v_rep := v_rep || pg_catalog.format(' constraints = %s (esperadas 649 en 0351);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    IF pg_catalog.pg_get_userbyid((SELECT c.relowner FROM pg_catalog.pg_class c
                                    WHERE c.oid = 'gapto.propiedades'::pg_catalog.regclass)) <> 'gapto_owner' THEN
        v_rep := v_rep || ' propiedades no pertenece a gapto_owner;';
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0352 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;
    RAISE NOTICE 'F06-01-0352 PRECHECK: OK';
END
$precheck_0352$;

SET ROLE gapto_owner;

ALTER TABLE gapto.propiedades NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.propiedades
    ADD COLUMN coste_adquisicion_declarado_completo boolean,
    ADD COLUMN coste_adquisicion_declarado_en       date,
    ADD COLUMN coste_adquisicion_conjunto_declarado jsonb,
    ADD COLUMN mejoras_declaradas_completas         boolean,
    ADD COLUMN mejoras_declaradas_en                date,
    ADD COLUMN mejoras_conjunto_declarado           jsonb;

ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__coste_adquisicion_declaracion CHECK (
        (coste_adquisicion_declarado_completo IS NULL AND coste_adquisicion_declarado_en IS NULL
         AND coste_adquisicion_conjunto_declarado IS NULL)
        OR (coste_adquisicion_declarado_completo IS TRUE AND coste_adquisicion_declarado_en IS NOT NULL
            AND coste_adquisicion_conjunto_declarado IS NOT NULL
            AND pg_catalog.jsonb_typeof(coste_adquisicion_conjunto_declarado) = 'array')),
    ADD CONSTRAINT ck_propiedades__mejoras_declaracion CHECK (
        (mejoras_declaradas_completas IS NULL AND mejoras_declaradas_en IS NULL
         AND mejoras_conjunto_declarado IS NULL)
        OR (mejoras_declaradas_completas IS TRUE AND mejoras_declaradas_en IS NOT NULL
            AND mejoras_conjunto_declarado IS NOT NULL
            AND pg_catalog.jsonb_typeof(mejoras_conjunto_declarado) = 'array')),
    ADD CONSTRAINT ck_propiedades__coste_adquisicion_corte_no_anterior CHECK (
        coste_adquisicion_declarado_en IS NULL OR fecha_adquisicion IS NULL
        OR coste_adquisicion_declarado_en >= fecha_adquisicion);

COMMENT ON COLUMN gapto.propiedades.coste_adquisicion_declarado_completo IS
    'F06-01 B2 (AJ-R1-02): declaracion del usuario de que el coste de adquisicion esta completo hasta coste_adquisicion_declarado_en. NULL = no declarado.';
COMMENT ON COLUMN gapto.propiedades.coste_adquisicion_declarado_en IS
    'F06-01 B2 (AJ-R1-02): fecha de corte de la declaracion de coste de adquisicion completo. NULL = no declarado.';
COMMENT ON COLUMN gapto.propiedades.coste_adquisicion_conjunto_declarado IS
    'F06-01 B2 (RR1-02, politica I-B): array jsonb canonico de los componentes ACTIVO de adquisicion con fecha <= corte que respaldaron la declaracion. L-COSTE lo compara con el vigente. NULL = no declarado.';
COMMENT ON COLUMN gapto.propiedades.mejoras_declaradas_completas IS
    'F06-01 B3 (AJ-R1-03): declaracion de que las mejoras estan completas hasta mejoras_declaradas_en. NULL = no declarado.';
COMMENT ON COLUMN gapto.propiedades.mejoras_declaradas_en IS
    'F06-01 B3 (AJ-R1-03): fecha de corte de la declaracion de mejoras completas. NULL = no declarado.';
COMMENT ON COLUMN gapto.propiedades.mejoras_conjunto_declarado IS
    'F06-01 B3 (RR1-02, politica I-B): array jsonb canonico de las mejoras ACTIVO con fecha <= corte que respaldaron la declaracion ([] = no hubo mejoras). NULL = no declarado.';

ALTER TABLE gapto.propiedades FORCE ROW LEVEL SECURITY;

RESET ROLE;

DO $postcheck_0352$
DECLARE
    v_n   bigint;
    v_rep text := '';
    v_m   text;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass AND NOT a.attnotnull
       AND a.attnum > 0 AND NOT a.attisdropped
       AND (a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)) IN
           (('coste_adquisicion_declarado_completo', 'boolean'), ('coste_adquisicion_declarado_en', 'date'),
            ('coste_adquisicion_conjunto_declarado', 'jsonb'),
            ('mejoras_declaradas_completas', 'boolean'), ('mejoras_declaradas_en', 'date'),
            ('mejoras_conjunto_declarado', 'jsonb'));
    IF v_n <> 6 THEN
        v_rep := v_rep || pg_catalog.format(' columnas nuevas con contrato = %s (esperadas 6);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p') AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 787 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 787 = 781 + 6);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 652 THEN
        v_rep := v_rep || pg_catalog.format(' constraints = %s (esperadas 652 = 649 + 3);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.contype = 'c' AND k.convalidated AND k.conrelid = 'gapto.propiedades'::pg_catalog.regclass
       AND k.conname IN ('ck_propiedades__coste_adquisicion_declaracion', 'ck_propiedades__mejoras_declaracion',
                         'ck_propiedades__coste_adquisicion_corte_no_anterior');
    IF v_n <> 3 THEN
        v_rep := v_rep || pg_catalog.format(' CHECK nuevos validados = %s (esperados 3);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;
    IF NOT (SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c WHERE c.oid = 'gapto.propiedades'::pg_catalog.regclass) THEN
        v_rep := v_rep || ' propiedades sin FORCE RLS;';
    END IF;
    -- Privilegios de runtime sin cambios (matriz 80/74/68/41 de 0351).
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
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n); END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN v_rep := v_rep || pg_catalog.format(' policies = %s (esperadas 82);', v_n); END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58);', v_n); END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28);', v_n); END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.tipos_hecho;
    IF v_n <> 10 THEN v_rep := v_rep || pg_catalog.format(' tipos_hecho = %s (esperados 10);', v_n); END IF;
    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0352 POSTCHECK:%', v_rep;
    END IF;
    RAISE NOTICE 'F06-01-0352 POSTCHECK: OK';
END
$postcheck_0352$;

COMMIT;
