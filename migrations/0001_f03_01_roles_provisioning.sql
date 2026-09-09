-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0001_f03_01_roles_provisioning.sql
-- Ruta: migrations/0001_f03_01_roles_provisioning.sql
-- Descripción: Materializa los roles conceptuales base y la cadena de
--              SET ROLE necesaria para ejecutar migrations con ownership
--              separado y mínimo privilegio.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- F03-01 no oculta drift. En un bootstrap limpio ninguno de los roles
-- conceptuales de Gapto puede existir previamente.
DO $gapto$
DECLARE
    v_existing_roles text;
BEGIN
    SELECT string_agg(r.rolname, ', ' ORDER BY r.rolname)
      INTO v_existing_roles
      FROM pg_catalog.pg_roles AS r
     WHERE r.rolname IN (
        'gapto_owner',
        'gapto_migrator',
        'gapto_internal',
        'gapto_runtime',
        'gapto_backup'
     );

    IF v_existing_roles IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B00 ROLE DRIFT: ya existen roles reservados de Gapto: %',
            v_existing_roles;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

-- Los cinco nombres son roles de autorización/capacidad, no credenciales.
-- Las identidades LOGIN concretas son configuración de entorno y nunca
-- almacenan passwords en Git. El bootstrap executor queda enlazado como
-- migrator mediante SET ROLE para poder crear objetos con ownership correcto.
CREATE ROLE gapto_owner
    NOLOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE gapto_migrator
    NOLOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE gapto_internal
    NOLOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE gapto_runtime
    NOLOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE gapto_backup
    NOLOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

COMMENT ON ROLE gapto_owner IS
    'GaptoMobile 2027: owner NOLOGIN de objetos de aplicación.';
COMMENT ON ROLE gapto_migrator IS
    'GaptoMobile 2027: rol de capacidad para migrations controladas.';
COMMENT ON ROLE gapto_internal IS
    'GaptoMobile 2027: owner NOLOGIN de funciones privilegiadas mínimas.';
COMMENT ON ROLE gapto_runtime IS
    'GaptoMobile 2027: capacidad de ejecución ordinaria del backend.';
COMMENT ON ROLE gapto_backup IS
    'GaptoMobile 2027: capacidad de lectura completa controlada para backup.';

-- El migrator puede convertirse explícitamente en owner/internal, pero no
-- hereda silenciosamente sus privilegios.
GRANT gapto_owner
   TO gapto_migrator
 WITH INHERIT FALSE, SET TRUE;

GRANT gapto_internal
   TO gapto_migrator
 WITH INHERIT FALSE, SET TRUE;

-- La identidad administrativa que ejecuta el bootstrap queda vinculada a la
-- capacidad migrator sin herencia automática. En entornos gestionados esta
-- identidad será la credencial administrativa/provisionadora del entorno.
GRANT gapto_migrator
   TO CURRENT_USER
 WITH INHERIT FALSE, SET TRUE;

COMMIT;
