-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0190_f03_01_b16_role_chain_set_option.sql
-- Ruta: migrations/0190_f03_01_b16_role_chain_set_option.sql
-- Descripcion: F03-01-B16. Resuelve D-085/D-4 completando la cadena
--   administrativa SET ROLE hacia gapto_runtime y gapto_backup.
--
--   PROBLEMA. Desde PostgreSQL 16, SET ROLE exige que la membresia tenga
--   set_option = true. Las membresias que el proveedor concede al rol
--   administrativo (cloud_admin en Neon, supabase_admin en Supabase) llegan
--   con set_option = false. La unica cadena con SET habilitado, creada por
--   0001, es:
--       rol administrativo --SET--> gapto_migrator --SET--> gapto_owner
--                                                  --SET--> gapto_internal
--   No existe camino SET ROLE hacia gapto_runtime ni gapto_backup, lo que
--   hace fisicamente imposible ejercitar el write-path real en tests:
--   B15 solo puede verificarse estructuralmente y las pruebas de
--   aislamiento multi-tenant de B13 nunca han ejecutado como gapto_runtime.
--
--   CORRECCION. Se completa la cadena que 0001 dejo incompleta. Esto NO
--   concede ningun privilegio nuevo a gapto_runtime ni a gapto_backup, y no
--   amplia lo que gapto_migrator puede hacer en terminos de datos:
--   gapto_migrator ya podia asumir gapto_owner, que es estrictamente mas
--   poderoso que ambos. Lo unico que cambia es la capacidad de impersonar
--   roles menos privilegiados para verificacion.
--
--   INHERIT FALSE es explicito y deliberado: gapto_migrator no debe heredar
--   pasivamente privilegios de runtime/backup; solo debe poder asumirlos de
--   forma consciente mediante SET ROLE. Coincide con las membresias que
--   0001 ya creo hacia gapto_owner y gapto_internal.
--
--   ALCANCE. Correccion de provisioning administrativo. No toca GRANTs de
--   tabla, RLS, policies, funciones ni ownership. No modifica 0001, que
--   permanece inmutable: la correccion es forward-only.
--
--   Reapertura parcial declarada de D-070 (F03-01-B00 / bootstrap), acotada
--   exclusivamente a la cadena SET ROLE. No reabre F03-00-H.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- Estas sentencias requieren ADMIN OPTION sobre los roles concedidos, que el
-- rol administrativo del proveedor ya posee. Se ejecutan con el rol de
-- conexion, NO bajo SET ROLE gapto_owner: gapto_owner no puede administrar
-- otros roles, igual que ocurria con el ALTER ROLE de 0130.

GRANT gapto_runtime TO gapto_migrator WITH INHERIT FALSE, SET TRUE;

GRANT gapto_backup  TO gapto_migrator WITH INHERIT FALSE, SET TRUE;

COMMIT;
