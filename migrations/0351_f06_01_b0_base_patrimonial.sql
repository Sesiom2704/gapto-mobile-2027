-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0351_f06_01_b0_base_patrimonial.sql
-- Ruta: migrations/0351_f06_01_b0_base_patrimonial.sql
-- Descripcion: FASE 06 · F06-01 B0 (F06-D002; consulta de diseno de B0 v1.0
--   §2; dictamen doble 2026-11-04, PB0-01..14 y AJ-B0-01..09). Migration
--   agrupada forward-only sobre 0350. Reapertura acotada de F03 dispuesta por
--   F06-D002: DDL, seed de tipos_hecho y privilegios de gapto_runtime.
--
--   CONTRATO.
--     1. gapto.hecho_efectos.causa_valor_activo varchar(32) NULL.
--        ck_hecho_efectos__causa_valor_activo_dominio: NULL o una de
--          ADQUISICION, TRANSFORMACION_CAPITALIZABLE, BAJA_TOTAL,
--          BAJA_PARCIAL, REDUCCION_ESTRUCTURAL (el conjunto cerrado
--          ACONTECIMIENTOS_VALOR_ACTIVO del motor, INV-09).
--        ck_hecho_efectos__causa_solo_valor_activo:
--          (tipo_efecto = 'VALOR_ACTIVO') = (causa_valor_activo IS NOT NULL).
--          Ningun operando puede ser NULL (tipo_efecto es NOT NULL y el IS NOT
--          NULL nunca lo es), asi que el CHECK no puede evaluar a NULL.
--        Filas existentes: NO se rellena ninguna causa (PB0-02). Si existe
--        algun VALOR_ACTIVO, la migration aborta (fail-closed).
--     2. gapto.tipos_hecho: ADQUISICION_PATRIMONIAL y MEJORA_PATRIMONIAL,
--        id = uuid5(NAMESPACE_URL, 'gapto2027:tipos_hecho:<CODIGO>'), patron
--        de 0350/D-201. Ninguna ruta HTTP los admite (PB0-05): exponerlos es
--        de F06-01 B2.
--     3. gapto.contratos.habitacion smallint NULL.
--        ck_contratos__habitacion:
--          habitacion IS NULL OR (habitacion >= 1 AND tipo_contrato = 'HABITACION').
--        Etiqueta ordinal visible, no identidad (PB0-07, AJ-B0-09): sin
--        unicidad fisica; el solape lo valida el writer de F06-02/03.
--     4. gapto.contrato_servicios.modo_reparto varchar(16) NULL.
--        ck_contrato_servicios__modo_reparto_dominio: NULL, FIJO o POR_FACTURA.
--        ck_contrato_servicios__repercusion_coherente SUSTITUYE a
--        ck_contrato_servicios__repercusion_exige_datos:
--          no repercutible -> modo_reparto, actor_repercusion_id y
--                             porcentaje_repercutible NULL (PB0-06, AJ-B0-02);
--          repercutible    -> modo_reparto y actor NOT NULL; FIJO exige
--                             porcentaje y POR_FACTURA lo PROHIBE.
--        Seguro frente a NULL: repercutible es NOT NULL y cada rama compara
--        con IS [NOT] NULL antes de usar modo_reparto (leccion de L3-2 §6).
--        Filas existentes: modo_reparto = 'FIJO' en las repercutibles, fiel
--        porque el CHECK sustituido ya les exigia actor y porcentaje. Las no
--        repercutibles con actor o porcentaje residual NO se limpian: la
--        migration aborta y se decide con inventario (PB0-06).
--     5. REVOKE DELETE de gapto_runtime, opcion B de PB0-09, en siete tablas:
--        tercero_roles, tercero_direcciones, tercero_clasificaciones,
--        clasificaciones_tercero, contrato_servicios, propiedad_servicios y
--        entidad_relaciones. Bajo SET ROLE gapto_owner (D-150, §12C.8): el
--        grantor de esos DELETE es gapto_owner y solo el puede revocarlos;
--        un REVOKE sin efecto no falla, solo advierte, y por eso el postcheck
--        verifica el ACL completo de cada tabla.
--
--   PATRON (el de la cadena).
--     - BEGIN; precheck fail-closed con la identidad de la conexion (★3 de la
--       consulta, PB0-13); SET ROLE gapto_owner; RESET ROLE; postcheck; COMMIT.
--     - SQL cualificado con gapto., sin SET search_path.
--     - FORCE RLS levantado y restaurado en la MISMA transaccion en cada
--       tabla alterada (hecho_efectos, contratos, contrato_servicios).
--     - Recuentos de datos fail-closed: se hacen como gapto_owner con FORCE
--       levantado en la tabla contada, porque es la unica identidad de la
--       cadena que ve TODAS las filas sin depender de BYPASSRLS ni de la GUC
--       de tenant. Contar con la identidad de la conexion podria dar 0 por
--       RLS y aprobar en falso (PB0-11: visibilidad suficiente).
--     - Reaplicar: lo rechaza el precheck (columnas presentes / seed
--       presente), no un IF NOT EXISTS silencioso.
--
--   LO QUE NO HACE A PROPOSITO.
--     - No infiere ni rellena causas de VALOR_ACTIVO existentes.
--     - No limpia datos de repercusion residuales.
--     - No crea unicidad ni EXCLUDE de habitacion.
--     - No toca triggers, funciones, policies, indices ni vistas.
--     - No revoca DELETE en las otras 34 tablas que lo conservan; en
--       particular las doce de DEVUELTO_POR_0320 quedan intactas.
--     - No cambia el procedimiento de aplicacion: se aplica con la credencial
--       administrativa del entorno, como 0350. gapto_migrator (NOLOGIN, sin
--       USAGE en gapto) no puede aplicarla por si mismo: deuda registrada
--       (PB0-13, AJ-B0-08), no se corrige aqui.
--
--   IMPACTO FISICO ESPERADO (medido en laboratorio; ver evidencia B0 v0.2).
--     h1 columnas +3 (778 -> 781); h2 constraints +5 -1 (645 -> 649);
--     h7 grants -7 (1031 -> 1024); runtime 80/74/68/48 -> 80/74/68/41.
--     h3, h4, h5, h6 y h8 identicas a 0350.
--
--   DESPLIEGUE (AJ-B0-05, PB0-01; dictamen B0 implementacion PB0I-02,
--   AJ-B0I-02). El paquete es asimetrico: el codigo B0 no funciona sobre 0350
--   (escribe causa_valor_activo) y el writer anterior no puede crear
--   VALOR_ACTIVO sobre 0351 (el CHECK lo rechaza). Contrato por entorno:
--   detener todos los writers; ejecutar precheck; aplicar 0351; verificar
--   postcheck; desplegar codigo compatible con 0351; arrancar y validar.
--   Si falla antes del COMMIT, la transaccion revierte y el entorno sigue en
--   0350 con el codigo anterior. Si falla despues, mantenimiento y
--   recuperacion controlada; nunca se edita 0351 (una reversion fisica es
--   una migration nueva). Plan en B0_v03/PLAN_APLICACION_Y_DESPLIEGUE.md.
--
--   D-179-B. No se aplica a Supabase sin gate y autorizacion propios.
-- Versión: 0.3.0  -- AJ-B0I-02: solo cambia la cabecera DESPLIEGUE (esquema
--                   primero con writers detenidos). SQL ejecutable identico
--                   al de 0.2.0.
-- Versión: 0.2.0  -- primer candidato SQL (AJ-B0-01). Las 0.1.x fueron
--                   prototipos de diagnostico y no son ascendientes validos.
-- ============================================================

BEGIN;

DO $precheck_0351$
DECLARE
    v_n        bigint;
    v_rep      text := '';
    v_esperado CONSTANT text[] := ARRAY[
        'APORTACION_INVERSION:cf006530-280c-587b-994f-e621e680e3ef',
        'COMPRA_FINANCIADA:7c20e19e-8c62-5df7-b11b-17d15eb4c76c',
        'CONDONACION:0d216df5-59eb-56c8-998e-7d47953b9351',
        'GASTO:b9c7573f-fa72-54a1-8b2d-b1c189f32533',
        'GENERACION_DERECHO_OBLIGACION:26ee751e-aa9c-5c3b-a81c-7a28e5a5be34',
        'INGRESO:bfdad2e0-2d2e-5850-b73a-1d2ecd8eb4c4',
        'REEMBOLSO:a4153b30-58b5-50d4-9073-471ea1d6c294',
        'TRANSFERENCIA:7ba5c0c4-ccd9-557c-838a-9122e96634d6'
    ];
    v_actual   text[];
BEGIN
    -- 'SET', no 'USAGE': pertenencias INHERIT FALSE / SET TRUE (D-189).
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname = 'gapto_runtime') THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK: no existe el rol gapto_runtime';
    END IF;

    -- Reaplicacion: cualquier rastro de 0351 aborta.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND a.attnum > 0 AND NOT a.attisdropped
       AND (c.relname, a.attname) IN (('hecho_efectos', 'causa_valor_activo'),
                                      ('contratos', 'habitacion'),
                                      ('contrato_servicios', 'modo_reparto'));
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK: 0351 ya esta aplicada (% columnas presentes); no se reaplica', v_n;
    END IF;

    -- Head de partida exacto: el seed de 0350, por codigo y por UUID.
    SELECT pg_catalog.array_agg(t.codigo::text || ':' || t.id::text ORDER BY t.codigo::text COLLATE "C")
      INTO v_actual
      FROM gapto.tipos_hecho t;
    IF v_actual IS DISTINCT FROM v_esperado THEN
        v_rep := v_rep || pg_catalog.format(' tipos_hecho no es exactamente el seed de 0350: %s;', v_actual);
    END IF;

    -- Constraint sustituida presente; las nuevas ausentes.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k
                    WHERE k.conrelid = 'gapto.contrato_servicios'::pg_catalog.regclass
                      AND k.conname = 'ck_contrato_servicios__repercusion_exige_datos') THEN
        v_rep := v_rep || ' falta ck_contrato_servicios__repercusion_exige_datos;';
    END IF;

    -- Matriz DELETE de runtime: 48 (0320) y las siete con DELETE.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 48 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 48 en 0350);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
      JOIN pg_catalog.pg_roles g ON g.oid = acl.grantor
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE'
       AND g.rolname = 'gapto_owner'
       AND c.relname = ANY (ARRAY['tercero_roles','tercero_direcciones','tercero_clasificaciones',
                                  'clasificaciones_tercero','contrato_servicios',
                                  'propiedad_servicios','entidad_relaciones']);
    IF v_n <> 7 THEN
        v_rep := v_rep || pg_catalog.format(' %s de las siete tienen DELETE de runtime concedido por gapto_owner (esperadas 7);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;

    RAISE NOTICE 'F06-01-0351 PRECHECK: OK';
END
$precheck_0351$;

SET ROLE gapto_owner;

-- FORCE se levanta ANTES de contar: el propietario sin FORCE ve todas las
-- filas sin GUC de tenant. Se restaura en esta misma transaccion.
ALTER TABLE gapto.hecho_efectos NO FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.contrato_servicios NO FORCE ROW LEVEL SECURITY;

DO $precheck_datos_0351$
DECLARE
    v_n   bigint;
    v_rep text := '';
BEGIN
    IF current_user <> 'gapto_owner' THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK DATOS: se esperaba gapto_owner y es %', current_user;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.oid IN ('gapto.hecho_efectos'::pg_catalog.regclass, 'gapto.contrato_servicios'::pg_catalog.regclass)
       AND c.relforcerowsecurity;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK DATOS: FORCE RLS sigue activo; el recuento no seria completo';
    END IF;

    -- PB0-02: VALOR_ACTIVO preexistente sin causa. No hay dato autoritativo
    -- para inferirla: se aborta y se decide fuera (R-B0-01).
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.hecho_efectos e WHERE e.tipo_efecto = 'VALOR_ACTIVO';
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s efectos VALOR_ACTIVO preexistentes sin causa;', v_n);
    END IF;

    -- PB0-06 / AJ-B0-02: residuos de repercusion en filas no repercutibles.
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.contrato_servicios s
     WHERE NOT s.repercutible
       AND (s.actor_repercusion_id IS NOT NULL OR s.porcentaje_repercutible IS NOT NULL);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s servicios no repercutibles con actor o porcentaje;', v_n);
    END IF;

    -- Defensa: el CHECK sustituido garantiza actor y porcentaje en toda fila
    -- repercutible; si no fuese asi, FIJO no seria un relleno fiel.
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.contrato_servicios s
     WHERE s.repercutible
       AND (s.actor_repercusion_id IS NULL OR s.porcentaje_repercutible IS NULL);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s servicios repercutibles sin actor o porcentaje;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0351 PRECHECK DATOS: no se aplica, nada se limpia ni se rellena:%', v_rep;
    END IF;

    RAISE NOTICE 'F06-01-0351 PRECHECK DATOS: OK';
END
$precheck_datos_0351$;

-- ------------------------------------------------------------
-- 1) Causa de VALOR_ACTIVO
-- ------------------------------------------------------------
ALTER TABLE gapto.hecho_efectos ADD COLUMN causa_valor_activo character varying(32);
ALTER TABLE gapto.hecho_efectos ADD CONSTRAINT ck_hecho_efectos__causa_valor_activo_dominio
    CHECK (causa_valor_activo IS NULL OR causa_valor_activo IN
           ('ADQUISICION', 'TRANSFORMACION_CAPITALIZABLE', 'BAJA_TOTAL', 'BAJA_PARCIAL',
            'REDUCCION_ESTRUCTURAL'));
ALTER TABLE gapto.hecho_efectos ADD CONSTRAINT ck_hecho_efectos__causa_solo_valor_activo
    CHECK ((tipo_efecto = 'VALOR_ACTIVO') = (causa_valor_activo IS NOT NULL));
ALTER TABLE gapto.hecho_efectos FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 2) Arquetipos patrimoniales (catalogo global, sin RLS)
-- ------------------------------------------------------------
INSERT INTO gapto.tipos_hecho (id, codigo, nombre, enabled) VALUES
    ('1da0639b-825a-5803-8c50-db1b7543c751', 'ADQUISICION_PATRIMONIAL', 'Adquisicion patrimonial', true),
    ('d63b1e52-c3c5-5df3-80ff-346288d86c7d', 'MEJORA_PATRIMONIAL', 'Mejora patrimonial', true);

-- ------------------------------------------------------------
-- 3) Habitacion (etiqueta ordinal)
-- ------------------------------------------------------------
ALTER TABLE gapto.contratos NO FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.contratos ADD COLUMN habitacion smallint;
ALTER TABLE gapto.contratos ADD CONSTRAINT ck_contratos__habitacion
    CHECK (habitacion IS NULL OR (habitacion >= 1 AND tipo_contrato = 'HABITACION'));
ALTER TABLE gapto.contratos FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 4) Modo de reparto de los servicios repercutibles
-- ------------------------------------------------------------
ALTER TABLE gapto.contrato_servicios ADD COLUMN modo_reparto character varying(16);
UPDATE gapto.contrato_servicios SET modo_reparto = 'FIJO' WHERE repercutible;
ALTER TABLE gapto.contrato_servicios DROP CONSTRAINT ck_contrato_servicios__repercusion_exige_datos;
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT ck_contrato_servicios__modo_reparto_dominio
    CHECK (modo_reparto IS NULL OR modo_reparto IN ('FIJO', 'POR_FACTURA'));
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT ck_contrato_servicios__repercusion_coherente
    CHECK (
        (NOT repercutible
            AND modo_reparto IS NULL
            AND actor_repercusion_id IS NULL
            AND porcentaje_repercutible IS NULL)
        OR (repercutible
            AND modo_reparto IS NOT NULL
            AND actor_repercusion_id IS NOT NULL
            AND ((modo_reparto = 'FIJO' AND porcentaje_repercutible IS NOT NULL)
                 OR (modo_reparto = 'POR_FACTURA' AND porcentaje_repercutible IS NULL)))
    );
ALTER TABLE gapto.contrato_servicios FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 5) REVOKE DELETE de runtime (PB0-09 opcion B), como grantor gapto_owner
-- ------------------------------------------------------------
REVOKE DELETE ON gapto.tercero_roles           FROM gapto_runtime;
REVOKE DELETE ON gapto.tercero_direcciones     FROM gapto_runtime;
REVOKE DELETE ON gapto.tercero_clasificaciones FROM gapto_runtime;
REVOKE DELETE ON gapto.clasificaciones_tercero FROM gapto_runtime;
REVOKE DELETE ON gapto.contrato_servicios      FROM gapto_runtime;
REVOKE DELETE ON gapto.propiedad_servicios     FROM gapto_runtime;
REVOKE DELETE ON gapto.entidad_relaciones      FROM gapto_runtime;

RESET ROLE;

DO $postcheck_0351$
DECLARE
    v_n    bigint;
    v_rep  text := '';
    v_rep_matriz text;
    v_siete CONSTANT text[] := ARRAY[
        'tercero_roles','tercero_direcciones','tercero_clasificaciones',
        'clasificaciones_tercero','contrato_servicios','propiedad_servicios',
        'entidad_relaciones'];
    -- D-183: las doce a las que 0320 devolvio DELETE. Intactas.
    v_devuelto_por_0320 CONSTANT text[] := ARRAY[
        'hecho_efectos','efecto_atribuciones','hecho_aportaciones_pago',
        'hecho_movimientos_tesoreria','inversion_asignaciones_efecto',
        'efecto_cuentas','hecho_entidades','hecho_participantes',
        'hecho_terceros','hecho_magnitudes','hecho_relaciones','transferencias'];
BEGIN
    -- 1) ACL COMPLETO de las siete: runtime = exactamente SELECT, INSERT, UPDATE.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.unnest(v_siete) AS t(relname)
     WHERE (SELECT pg_catalog.string_agg(acl.privilege_type, ',' ORDER BY acl.privilege_type)
              FROM pg_catalog.pg_class c
              CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relname = t.relname
               AND r.rolname = 'gapto_runtime') IS DISTINCT FROM 'INSERT,SELECT,UPDATE';
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s de las siete no tienen exactamente SELECT+INSERT+UPDATE para runtime;', v_n);
    END IF;

    -- 2) Las doce de 0320 conservan SELECT+INSERT+UPDATE+DELETE.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.unnest(v_devuelto_por_0320) AS t(relname)
     WHERE (SELECT pg_catalog.string_agg(acl.privilege_type, ',' ORDER BY acl.privilege_type)
              FROM pg_catalog.pg_class c
              CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relname = t.relname
               AND r.rolname = 'gapto_runtime') IS DISTINCT FROM 'DELETE,INSERT,SELECT,UPDATE';
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s de DEVUELTO_POR_0320 han perdido o ganado privilegios;', v_n);
    END IF;

    -- 3) Matriz efectiva de runtime 80/74/68/41.
    SELECT pg_catalog.string_agg(x.n::text, '/' ORDER BY x.orden) INTO v_rep_matriz
      FROM (SELECT p.orden, (SELECT pg_catalog.count(*)
                               FROM pg_catalog.pg_class c
                               CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
                               JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
                              WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
                                AND r.rolname = 'gapto_runtime' AND acl.privilege_type = p.priv) AS n
              FROM (VALUES (1, 'SELECT'), (2, 'INSERT'), (3, 'UPDATE'), (4, 'DELETE')) AS p(orden, priv)) AS x;
    IF v_rep_matriz IS DISTINCT FROM '80/74/68/41' THEN
        v_rep := v_rep || pg_catalog.format(' matriz runtime = %s (esperada 80/74/68/41);', v_rep_matriz);
    END IF;

    -- 4) GRANTs a roles gapto_* (recuento de la huella h7): 1031 - 7.
    SELECT (SELECT pg_catalog.count(*)
              FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
             WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND e.grantee <> 0
               AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%')
         + (SELECT pg_catalog.count(*)
              FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid = a.attrelid,
                   pg_catalog.aclexplode(a.attacl) e
             WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND e.grantee <> 0
               AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%')
         + (SELECT pg_catalog.count(*)
              FROM pg_catalog.pg_proc p, pg_catalog.aclexplode(p.proacl) e
             WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND e.grantee <> 0
               AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%')
         + (SELECT pg_catalog.count(*)
              FROM pg_catalog.pg_namespace n, pg_catalog.aclexplode(n.nspacl) e
             WHERE n.nspname IN ('gapto','gapto_ext') AND e.grantee <> 0
               AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%')
      INTO v_n;
    IF v_n <> 1024 THEN
        v_rep := v_rep || pg_catalog.format(' grants a roles gapto_* = %s (esperados 1024 = 1031 - 7);', v_n);
    END IF;

    -- 5) Columnas nuevas con su tipo exacto; recuento canonico h1 (r, v, p).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT a.attnotnull
       AND a.attnum > 0 AND NOT a.attisdropped
       AND (c.relname, a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)) IN
           (('hecho_efectos', 'causa_valor_activo', 'character varying(32)'),
            ('contratos', 'habitacion', 'smallint'),
            ('contrato_servicios', 'modo_reparto', 'character varying(16)'));
    IF v_n <> 3 THEN
        v_rep := v_rep || pg_catalog.format(' columnas nuevas con contrato = %s (esperadas 3);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p') AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 781 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 781 = 778 + 3);', v_n);
    END IF;

    -- 6) Constraints: +5 -1 respecto a 0350.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 649 THEN
        v_rep := v_rep || pg_catalog.format(' constraints = %s (esperadas 649 = 645 + 5 - 1);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.contype = 'c' AND k.convalidated
       AND (k.conrelid, k.conname) IN (
            ('gapto.hecho_efectos'::pg_catalog.regclass, 'ck_hecho_efectos__causa_valor_activo_dominio'),
            ('gapto.hecho_efectos'::pg_catalog.regclass, 'ck_hecho_efectos__causa_solo_valor_activo'),
            ('gapto.contratos'::pg_catalog.regclass, 'ck_contratos__habitacion'),
            ('gapto.contrato_servicios'::pg_catalog.regclass, 'ck_contrato_servicios__modo_reparto_dominio'),
            ('gapto.contrato_servicios'::pg_catalog.regclass, 'ck_contrato_servicios__repercusion_coherente'));
    IF v_n <> 5 THEN
        v_rep := v_rep || pg_catalog.format(' CHECK nuevos validados = %s (esperados 5);', v_n);
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k
                WHERE k.conrelid = 'gapto.contrato_servicios'::pg_catalog.regclass
                  AND k.conname = 'ck_contrato_servicios__repercusion_exige_datos') THEN
        v_rep := v_rep || ' ck_contrato_servicios__repercusion_exige_datos sigue presente;';
    END IF;

    -- 7) Seed: 10 tipos, los dos nuevos con su contrato, los ocho de 0350 intactos.
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.tipos_hecho;
    IF v_n <> 10 THEN
        v_rep := v_rep || pg_catalog.format(' tipos_hecho = %s (esperados 10);', v_n);
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.tipos_hecho t
     WHERE t.enabled AND (t.id, t.codigo, t.nombre) IN (
           ('1da0639b-825a-5803-8c50-db1b7543c751'::uuid, 'ADQUISICION_PATRIMONIAL', 'Adquisicion patrimonial'),
           ('d63b1e52-c3c5-5df3-80ff-346288d86c7d'::uuid, 'MEJORA_PATRIMONIAL', 'Mejora patrimonial'));
    IF v_n <> 2 THEN
        v_rep := v_rep || ' los dos arquetipos nuevos no tienen su contrato;';
    END IF;

    -- 8) FORCE RLS restaurado en todas; el resto del contrato no se mueve.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
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

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01-0351 POSTCHECK:%', v_rep;
    END IF;

    RAISE NOTICE 'F06-01-0351 POSTCHECK: OK';
END
$postcheck_0351$;

COMMIT;
