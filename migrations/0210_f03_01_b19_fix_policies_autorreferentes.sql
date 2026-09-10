-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0210_f03_01_b19_fix_policies_autorreferentes.sql
-- Ruta: migrations/0210_f03_01_b19_fix_policies_autorreferentes.sql
-- Descripcion: F03-01-B19. Corrige un defecto BLOQUEANTE de B13 detectado
--   al construir las fixtures de F03-01-B17 (D-090).
--
--   DEFECTO. Cuatro policies tenant_isolation validan la pertenencia del
--   padre al mismo tenant mediante un EXISTS contra SU PROPIA TABLA. Bajo
--   FORCE ROW LEVEL SECURITY, PostgreSQL vuelve a expandir la policy al
--   planificar ese subselect y aborta con 42P17 "infinite recursion
--   detected in policy for relation". El efecto es que
--   categorias_financieras, clasificaciones_tercero, cierres_mensuales y
--   presupuestos son FISICAMENTE NO ESCRIBIBLES por cualquier rol sujeto a
--   RLS, incluidos gapto_runtime y gapto_owner, incluso cuando la columna
--   autorreferente es NULL: el fallo se produce en planificacion, no en
--   evaluacion.
--
--   Verificado en Neon PostgreSQL 17.11 y Supabase PostgreSQL 17.6.1.166,
--   como gapto_owner y como gapto_runtime. No es un artefacto de version.
--
--   CAUSA. D-074 exige que WITH CHECK valide todos los FK owner-scoped de
--   la fila. Para los FK que apuntan a OTRA tabla el EXISTS es correcto y
--   no recurre. Para los FK autorreferentes no puede resolverse leyendo la
--   misma tabla bajo RLS.
--
--   CORRECCION. Se sustituye la comprobacion imperativa por integridad
--   DECLARATIVA, que es ademas lo que exige el Working Method: preferir
--   CHECK/UNIQUE/FK antes que logica en policies o triggers.
--
--   1) Se anade el anchor UNIQUE (owner_user_id, id) donde falta.
--      cierres_mensuales ya lo tenia desde B08.
--   2) Se anade un FK compuesto (owner_user_id, <col_autorreferente>)
--      contra (owner_user_id, id) de la propia tabla. Con MATCH SIMPLE,
--      si la columna autorreferente es NULL la restriccion se satisface,
--      que es exactamente la semantica buscada; si no lo es, el padre
--      queda obligado a pertenecer al mismo owner. La garantia es
--      estrictamente mas fuerte que el EXISTS, porque tambien se aplica a
--      escrituras hechas por roles con BYPASSRLS.
--   3) Se retira de WITH CHECK unicamente la clausula autorreferente. El
--      resto se conserva intacto: en presupuestos permanece la validacion
--      de generado_desde_cierre_id contra cierres_mensuales, que apunta a
--      otra tabla y no recurre.
--
--   NOTA DE EJECUCION IMPORTANTE. La validacion de un FK compuesto sobre
--   una tabla con FORCE ROW LEVEL SECURITY se ejecuta bajo la policy, y
--   como la GUC gapto.owner_user_id no esta fijada durante una migration,
--   current_setting devuelve cadena vacia y el cast a uuid aborta con
--   22P02 (el caso limite de D-075). Ademas, fijar una GUC cualquiera
--   seria peor: la validacion solo veria las filas de ese tenant y daria
--   por buena una tabla que no ha comprobado entera. Por eso cada tabla se
--   pasa a NO FORCE ROW LEVEL SECURITY, se valida y se devuelve a FORCE
--   dentro de la misma transaccion: el propietario recupera su bypass
--   durante el escaneo, la validacion es completa y no queda ventana
--   abierta. Esto aplica a cualquier DDL futuro que valide constraints
--   sobre tablas tenant.
--
--   Los FK simples de B09 (fk_*__parent, fk_*__reemplaza) se conservan sin
--   cambios. Quedan logicamente implicados por el FK compuesto y son
--   redundantes; retirarlos exigiria tocar el contrato de B09 y no aporta
--   nada a la correccion, asi que se deja anotado como deuda menor.
--
--   No se modifica 0120 ni ninguna migration ya aplicada: la correccion es
--   forward-only. B13 se reabre parcialmente solo para estas 4 policies y
--   vuelve a cerrarse. No reabre F03-00-H ni D-074, cuya intencion se
--   mantiene: cambia el mecanismo, no la garantia.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 1) Anchors de ownership que faltaban
-- ------------------------------------------------------------
ALTER TABLE gapto.categorias_financieras
    ADD CONSTRAINT uq_categorias_financieras__owner_anchor UNIQUE (owner_user_id, id);

ALTER TABLE gapto.clasificaciones_tercero
    ADD CONSTRAINT uq_clasificaciones_tercero__owner_anchor UNIQUE (owner_user_id, id);

ALTER TABLE gapto.presupuestos
    ADD CONSTRAINT uq_presupuestos__owner_anchor UNIQUE (owner_user_id, id);

-- ------------------------------------------------------------
-- 2) FK compuestos autorreferentes de mismo tenant
-- ------------------------------------------------------------
-- Ver NOTA DE EJECUCION en la cabecera: FORCE RLS se retira y se restaura
-- dentro de esta misma transaccion para que la validacion sea completa.

ALTER TABLE gapto.categorias_financieras  NO FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.clasificaciones_tercero NO FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierres_mensuales       NO FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.presupuestos            NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.categorias_financieras
    ADD CONSTRAINT fk_categorias_financieras__parent_same_owner
    FOREIGN KEY (owner_user_id, parent_id)
    REFERENCES gapto.categorias_financieras (owner_user_id, id)
    ON DELETE RESTRICT;

ALTER TABLE gapto.clasificaciones_tercero
    ADD CONSTRAINT fk_clasificaciones_tercero__parent_same_owner
    FOREIGN KEY (owner_user_id, parent_id)
    REFERENCES gapto.clasificaciones_tercero (owner_user_id, id)
    ON DELETE RESTRICT;

ALTER TABLE gapto.cierres_mensuales
    ADD CONSTRAINT fk_cierres_mensuales__reemplaza_same_owner
    FOREIGN KEY (owner_user_id, reemplaza_cierre_id)
    REFERENCES gapto.cierres_mensuales (owner_user_id, id)
    ON DELETE RESTRICT;

ALTER TABLE gapto.presupuestos
    ADD CONSTRAINT fk_presupuestos__reemplaza_same_owner
    FOREIGN KEY (owner_user_id, reemplaza_presupuesto_id)
    REFERENCES gapto.presupuestos (owner_user_id, id)
    ON DELETE RESTRICT;

ALTER TABLE gapto.categorias_financieras  FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.clasificaciones_tercero FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierres_mensuales       FORCE ROW LEVEL SECURITY;
ALTER TABLE gapto.presupuestos            FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 3) Retirada de la clausula autorreferente en WITH CHECK
-- ------------------------------------------------------------
ALTER POLICY tenant_isolation ON gapto.categorias_financieras
    WITH CHECK (owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid);

ALTER POLICY tenant_isolation ON gapto.clasificaciones_tercero
    WITH CHECK (owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid);

ALTER POLICY tenant_isolation ON gapto.cierres_mensuales
    WITH CHECK (owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid);

-- presupuestos conserva la validacion cross-table hacia cierres_mensuales.
ALTER POLICY tenant_isolation ON gapto.presupuestos
    WITH CHECK (
        owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        AND (
            generado_desde_cierre_id IS NULL
            OR EXISTS (
                SELECT 1
                  FROM gapto.cierres_mensuales t1
                 WHERE t1.id = presupuestos.generado_desde_cierre_id
                   AND t1.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
            )
        )
    );

RESET ROLE;

COMMIT;
