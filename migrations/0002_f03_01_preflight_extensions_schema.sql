-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0002_f03_01_preflight_extensions_schema.sql
-- Ruta: migrations/0002_f03_01_preflight_extensions_schema.sql
-- Descripción: Valida el baseline PostgreSQL 17.x, fija defaults operativos
--              de BD, crea los schemas gapto/gapto_ext e instala las
--              extensiones requeridas btree_gist y pg_trgm.
-- Versión: 0.1.2
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. PREFLIGHT FAIL-FAST
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_server_version_num integer :=
        pg_catalog.current_setting('server_version_num')::integer;
    v_encoding text;
    v_existing_schemas text;
    v_existing_extensions text;
    v_supported_extensions integer;
BEGIN
    IF v_server_version_num < 170000 OR v_server_version_num >= 180000 THEN
        RAISE EXCEPTION
            'F03-01-B00 PLATFORM: PostgreSQL 17.x requerido; server_version_num=%',
            v_server_version_num;
    END IF;

    SELECT pg_catalog.pg_encoding_to_char(d.encoding)
      INTO v_encoding
      FROM pg_catalog.pg_database AS d
     WHERE d.datname = pg_catalog.current_database();

    IF v_encoding IS DISTINCT FROM 'UTF8' THEN
        RAISE EXCEPTION
            'F03-01-B00 PLATFORM: encoding UTF8 requerido; encoding=%',
            v_encoding;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_collation AS c
          JOIN pg_catalog.pg_namespace AS n
            ON n.oid = c.collnamespace
         WHERE n.nspname = 'pg_catalog'
           AND c.collname = 'pg_c_utf8'
    ) THEN
        RAISE EXCEPTION
            'F03-01-B00 PLATFORM: collation pg_catalog.pg_c_utf8 no disponible';
    END IF;

    SELECT string_agg(n.nspname, ', ' ORDER BY n.nspname)
      INTO v_existing_schemas
      FROM pg_catalog.pg_namespace AS n
     WHERE n.nspname IN ('gapto', 'gapto_ext');

    IF v_existing_schemas IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B00 SCHEMA DRIFT: ya existen schemas reservados: %',
            v_existing_schemas;
    END IF;

    SELECT string_agg(e.extname, ', ' ORDER BY e.extname)
      INTO v_existing_extensions
      FROM pg_catalog.pg_extension AS e
     WHERE e.extname IN ('btree_gist', 'pg_trgm');

    IF v_existing_extensions IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B00 EXTENSION DRIFT: ya existen extensiones requeridas: %',
            v_existing_extensions;
    END IF;

    SELECT count(*)
      INTO v_supported_extensions
      FROM pg_catalog.pg_available_extensions AS ae
      JOIN pg_catalog.pg_available_extension_versions AS aev
        ON aev.name = ae.name
       AND aev.version = ae.default_version
     WHERE ae.name IN ('btree_gist', 'pg_trgm')
       AND aev.trusted
       AND aev.relocatable
       AND aev.schema IS NULL;

    IF v_supported_extensions <> 2 THEN
        RAISE EXCEPTION
            'F03-01-B00 EXTENSIONS: btree_gist y pg_trgm deben estar disponibles, trusted y relocatable; encontrados=%',
            v_supported_extensions;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

-- Verificación práctica de la cadena de SET ROLE creada por 0001.
SET ROLE gapto_owner;
RESET ROLE;
SET ROLE gapto_internal;
RESET ROLE;
SET ROLE gapto_migrator;
RESET ROLE;

-- ------------------------------------------------------------
-- 2. DEFAULTS OPERATIVOS DE LA BASE
-- ------------------------------------------------------------
-- Encoding/collation no pueden corregirse después de CREATE DATABASE, por
-- eso se validan arriba. Timezone e isolation sí se fijan reproduciblemente.
DO $gapto$
BEGIN
    EXECUTE pg_catalog.format(
        'ALTER DATABASE %I SET timezone TO %L',
        pg_catalog.current_database(),
        'UTC'
    );

    EXECUTE pg_catalog.format(
        'ALTER DATABASE %I SET default_transaction_isolation TO %L',
        pg_catalog.current_database(),
        'read committed'
    );
END
$gapto$ LANGUAGE plpgsql;

-- La configuración ALTER DATABASE aplica a conexiones futuras; esta migration
-- usa UTC también en la sesión actual.
SET LOCAL TIME ZONE 'UTC';

-- ------------------------------------------------------------
-- 3. SCHEMA TÉCNICO DE EXTENSIONES
-- ------------------------------------------------------------
-- PostgreSQL exige CREATE sobre la base para crear un schema y para instalar
-- extensiones trusted. El privilegio se concede de forma temporal al rol de
-- migrations y se revoca dentro de la misma transacción.
DO $gapto$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT CREATE ON DATABASE %I TO gapto_migrator',
        pg_catalog.current_database()
    );
END
$gapto$ LANGUAGE plpgsql;

SET ROLE gapto_migrator;

CREATE SCHEMA gapto_ext;
REVOKE ALL ON SCHEMA gapto_ext FROM PUBLIC;

CREATE EXTENSION btree_gist WITH SCHEMA gapto_ext;
CREATE EXTENSION pg_trgm    WITH SCHEMA gapto_ext;

-- gapto_migrator es owner de gapto_ext, por lo que el GRANT debe ejecutarse
-- bajo este rol. El bootstrap executor no debe depender de privilegios
-- implícitos del proveedor para delegar USAGE sobre el schema técnico.
GRANT USAGE ON SCHEMA gapto_ext TO gapto_owner;

RESET ROLE;

DO $gapto$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE CREATE ON DATABASE %I FROM gapto_migrator',
        pg_catalog.current_database()
    );
END
$gapto$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- 4. SCHEMA AUTORITATIVO DE APLICACIÓN
-- ------------------------------------------------------------
-- También aquí se concede CREATE sobre la base solo durante la creación del
-- schema. Tras RESET ROLE se revoca inmediatamente.
DO $gapto$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT CREATE ON DATABASE %I TO gapto_owner',
        pg_catalog.current_database()
    );
END
$gapto$ LANGUAGE plpgsql;

SET ROLE gapto_owner;

CREATE SCHEMA gapto;
REVOKE ALL ON SCHEMA gapto FROM PUBLIC;

RESET ROLE;

DO $gapto$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE CREATE ON DATABASE %I FROM gapto_owner',
        pg_catalog.current_database()
    );
END
$gapto$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- 5. POSTCHECK DEL BOOTSTRAP
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_bad_extensions text;
BEGIN
    SELECT string_agg(e.extname, ', ' ORDER BY e.extname)
      INTO v_bad_extensions
      FROM pg_catalog.pg_extension AS e
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = e.extnamespace
     WHERE e.extname IN ('btree_gist', 'pg_trgm')
       AND n.nspname <> 'gapto_ext';

    IF v_bad_extensions IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: extensiones fuera de gapto_ext: %',
            v_bad_extensions;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: gapto no existe o no pertenece a gapto_owner';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto_ext'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_migrator'
    ) THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: gapto_ext no existe o no pertenece a gapto_migrator';
    END IF;

    IF pg_catalog.has_schema_privilege('public', 'gapto', 'USAGE')
       OR pg_catalog.has_schema_privilege('public', 'gapto', 'CREATE') THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: PUBLIC conserva privilegios sobre gapto';
    END IF;

    IF pg_catalog.has_schema_privilege('public', 'gapto_ext', 'USAGE')
       OR pg_catalog.has_schema_privilege('public', 'gapto_ext', 'CREATE') THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: PUBLIC conserva privilegios sobre gapto_ext';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
           'gapto_owner', 'gapto_ext', 'USAGE'
       ) THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: gapto_owner no tiene USAGE sobre gapto_ext';
    END IF;

    IF pg_catalog.has_database_privilege(
           'gapto_migrator', pg_catalog.current_database(), 'CREATE'
       ) THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: gapto_migrator conserva CREATE sobre la base';
    END IF;

    IF pg_catalog.has_database_privilege(
           'gapto_owner', pg_catalog.current_database(), 'CREATE'
       ) THEN
        RAISE EXCEPTION
            'F03-01-B00 POSTCHECK: gapto_owner conserva CREATE sobre la base';
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
