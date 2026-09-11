-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: huellas_d111.sql
-- Ruta: scripts/postgres/huellas_d111.sql
-- Descripcion: Consulta de SOLO LECTURA que calcula las ocho huellas
--   estructurales md5 del schema gapto usadas para certificar paridad entre
--   entornos (D-111 / Working Method 12B.3): columnas (tipo, NOT NULL,
--   default), constraints (definicion completa y flags de validacion y
--   diferibilidad), indices (indexdef), policies (USING y WITH CHECK),
--   triggers (estado, tipo y definicion), funciones (md5 de prosrc,
--   SECURITY DEFINER, volatilidad y proconfig), GRANTs a roles gapto_*
--   (tabla, columna, funcion y schema) y vistas (viewdef y reloptions).
--   Devuelve ademas los recuentos de cada conjunto como diagnostico.
--
--   Se versiona en F03-02 porque las consultas originales de D-111 no
--   estaban en Git ni en Drive y no eran reproducibles. Los valores que
--   produce NO son comparables con los historicos de D-111; la paridad se
--   certifica ejecutandola sobre todas las bases en el mismo estado. Cada
--   conjunto se ordena con COLLATE "C" para que el resultado no dependa de
--   la collation del proveedor. No modifica nada y puede ejecutarse con
--   cualquier rol que vea el catalogo.
-- Versión: 0.1.0
-- ============================================================
WITH
col AS (SELECT c.relname||'.'||a.attname||':'||pg_catalog.format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull::text||':'||coalesce(pg_catalog.pg_get_expr(d.adbin,d.adrelid),'') AS x
  FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
  LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
  WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND c.relkind IN ('r','v','p') AND a.attnum>0 AND NOT a.attisdropped),
con AS (SELECT c.relname||'.'||k.conname||':'||k.contype::text||':'||k.convalidated::text||':'||k.condeferrable::text||':'||k.condeferred::text||':'||pg_catalog.pg_get_constraintdef(k.oid) AS x
  FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
  WHERE c.relnamespace='gapto'::pg_catalog.regnamespace),
idx AS (SELECT i.indexdef AS x FROM pg_catalog.pg_indexes i WHERE i.schemaname='gapto'),
pol AS (SELECT p.tablename||'.'||p.policyname||':'||p.permissive||':'||p.roles::text||':'||p.cmd||':'||coalesce(p.qual,'')||':'||coalesce(p.with_check,'') AS x
  FROM pg_catalog.pg_policies p WHERE p.schemaname='gapto'),
trg AS (SELECT c.relname||'.'||t.tgname||':'||t.tgenabled::text||':'||t.tgtype::text||':'||pg_catalog.pg_get_triggerdef(t.oid) AS x
  FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal),
fun AS (SELECT p.proname||'('||pg_catalog.pg_get_function_identity_arguments(p.oid)||'):'||pg_catalog.md5(p.prosrc)||':'||p.prosecdef::text||':'||p.provolatile::text||':'||coalesce(p.proconfig::text,'') AS x
  FROM pg_catalog.pg_proc p WHERE p.pronamespace='gapto'::pg_catalog.regnamespace),
gr AS (
  SELECT 'T:'||c.relname||':'||e.grantee::pg_catalog.regrole::text||':'||e.privilege_type AS x
    FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
   WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND e.grantee<>0 AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%'
  UNION ALL
  SELECT 'C:'||c.relname||'.'||a.attname||':'||e.grantee::pg_catalog.regrole::text||':'||e.privilege_type
    FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid, pg_catalog.aclexplode(a.attacl) e
   WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND e.grantee<>0 AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%'
  UNION ALL
  SELECT 'F:'||p.proname||':'||e.grantee::pg_catalog.regrole::text||':'||e.privilege_type
    FROM pg_catalog.pg_proc p, pg_catalog.aclexplode(p.proacl) e
   WHERE p.pronamespace='gapto'::pg_catalog.regnamespace AND e.grantee<>0 AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%'
  UNION ALL
  SELECT 'S:'||n.nspname||':'||e.grantee::pg_catalog.regrole::text||':'||e.privilege_type
    FROM pg_catalog.pg_namespace n, pg_catalog.aclexplode(n.nspacl) e
   WHERE n.nspname IN ('gapto','gapto_ext') AND e.grantee<>0 AND e.grantee::pg_catalog.regrole::text LIKE 'gapto\_%'),
vw AS (SELECT c.relname||':'||pg_catalog.pg_get_viewdef(c.oid)||':'||coalesce(c.reloptions::text,'') AS x
  FROM pg_catalog.pg_class c WHERE c.relnamespace='gapto'::pg_catalog.regnamespace AND c.relkind IN ('v','m'))
SELECT
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM col) AS h1_columnas,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM con) AS h2_constraints,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM idx) AS h3_indices,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM pol) AS h4_policies,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM trg) AS h5_triggers,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM fun) AS h6_funciones,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM gr)  AS h7_grants,
 (SELECT pg_catalog.md5(pg_catalog.string_agg(x, E'\n' ORDER BY x COLLATE "C")) FROM vw)  AS h8_vistas,
 (SELECT pg_catalog.count(*) FROM col)::text||'/'||(SELECT pg_catalog.count(*) FROM con)||'/'||(SELECT pg_catalog.count(*) FROM idx)||'/'||(SELECT pg_catalog.count(*) FROM pol)||'/'||(SELECT pg_catalog.count(*) FROM trg)||'/'||(SELECT pg_catalog.count(*) FROM fun)||'/'||(SELECT pg_catalog.count(*) FROM gr)||'/'||(SELECT pg_catalog.count(*) FROM vw) AS recuentos
;
