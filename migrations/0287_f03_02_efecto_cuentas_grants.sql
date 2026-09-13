-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0287_f03_02_efecto_cuentas_grants.sql
-- Ruta: migrations/0287_f03_02_efecto_cuentas_grants.sql
-- Descripcion: FASE 03 / F03-02. Correccion forward-only de un defecto de
--   0286, ya aplicada y COMMITTEADA en los tres entornos. 0286 no se edita.
--
--   DEFECTO. 0286 emitio sus dos GRANT despues de RESET ROLE, es decir, con el
--   rol de conexion. Ese rol no es propietario de gapto.efecto_cuentas ni
--   tiene grant option sobre ella: en Neon, neondb_owner es miembro de
--   gapto_owner con inherit_option = false, y en Supabase postgres solo tiene
--   SET ROLE. PostgreSQL no aborta en ese caso, se limita a advertir que no se
--   concedio ningun privilegio, asi que la migration confirmo sin conceder
--   nada. Comprobado: gapto.efecto_cuentas quedo con los 8 privilegios
--   implicitos de su propietario y sin los 4 de gapto_runtime y gapto_backup,
--   de modo que la huella de GRANTs dio 1015 en los tres entornos en lugar de
--   1019.
--
--   El defecto no se detecto en local porque alli la cadena se aplica con un
--   rol superusuario, para el que el GRANT si es efectivo. Es un caso claro de
--   que la replica local no es evidencia de proveedor.
--
--   CORRECCION. Los mismos dos GRANT, ahora emitidos bajo SET ROLE
--   gapto_owner, que es el patron de 0130/B14. El postcheck ya no se limita a
--   comprobar la ausencia de DELETE: verifica el ACL exacto, porque un
--   postcheck que solo comprueba lo que no debe existir no detecta que no
--   exista nada.
--
--   La operacion es idempotente: si la cadena se aplico con un rol para el que
--   0286 si concedio los privilegios, volver a concederlos no cambia el ACL.
--
--   Bucket A de D-093, sin cambios respecto de lo aprobado en D-146:
--   gapto_runtime recibe SELECT, INSERT y UPDATE y NO recibe DELETE;
--   gapto_backup recibe SELECT y nada mas.
--
--   Contrato fisico: no cambia ningun recuento estructural. Solo la huella de
--   GRANTs, que pasa de 1015 a 1019 (+8 de propietario ya presentes, +3 de
--   runtime, +1 de backup).
--
-- Decision: D-146 / F02-F01-R2
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0287$
DECLARE
    v_bypass boolean;
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-02-0287 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    IF to_regclass('gapto.efecto_cuentas') IS NULL THEN
        RAISE EXCEPTION 'F03-02-0287 PRECHECK: falta gapto.efecto_cuentas; 0286 no esta aplicada';
    END IF;

    IF pg_catalog.pg_get_userbyid((SELECT c.relowner FROM pg_catalog.pg_class c
        WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass)) <> 'gapto_owner' THEN
        RAISE EXCEPTION 'F03-02-0287 PRECHECK: gapto.efecto_cuentas no pertenece a gapto_owner';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
     WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass
       AND e.grantee::pg_catalog.regrole::text = 'gapto_runtime'
       AND e.privilege_type = 'DELETE';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0287 PRECHECK: gapto_runtime ya tiene DELETE sobre efecto_cuentas';
    END IF;

    RAISE NOTICE 'F03-02-0287 PRECHECK: OK';
END;
$precheck_0287$;

SET ROLE gapto_owner;

GRANT SELECT, INSERT, UPDATE ON gapto.efecto_cuentas TO gapto_runtime;
GRANT SELECT ON gapto.efecto_cuentas TO gapto_backup;

RESET ROLE;

DO $postcheck_0287$
DECLARE
    v_acl text;
BEGIN
    SELECT pg_catalog.string_agg(x, ' | ' ORDER BY x) INTO v_acl
      FROM (SELECT e.grantee::pg_catalog.regrole::text || ':' ||
                   pg_catalog.string_agg(e.privilege_type, ',' ORDER BY e.privilege_type) AS x
              FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
             WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass
             GROUP BY e.grantee) AS t;

    IF v_acl <> 'gapto_backup:SELECT | gapto_owner:DELETE,INSERT,MAINTAIN,REFERENCES,SELECT,TRIGGER,TRUNCATE,UPDATE | gapto_runtime:INSERT,SELECT,UPDATE' THEN
        RAISE EXCEPTION 'F03-02-0287 POSTCHECK: ACL inesperado en efecto_cuentas -> %', v_acl;
    END IF;

    RAISE NOTICE 'F03-02-0287 POSTCHECK: OK';
END;
$postcheck_0287$;

COMMIT;
