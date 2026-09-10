-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0220_f03_01_b20_fk_owner_scoped_sin_validar.sql
-- Ruta: migrations/0220_f03_01_b20_fk_owner_scoped_sin_validar.sql
-- Descripcion: F03-01-B20. Cierra una FUGA CROSS-TENANT REAL y tres huecos
--   de la misma familia, detectados al ejecutar F03-01-B17 contra Supabase.
--
--   DEFECTO. D-074 exige que WITH CHECK valide todas las claves foraneas
--   owner-scoped de la fila. La auditoria del catalogo demuestra que cuatro
--   FK simples hacia tablas tenant no estaban cubiertas ni por FK compuesto
--   ni por policy:
--
--     tercero_direcciones.direccion_id          -> direcciones
--     movimientos_tesoreria.reversion_de_movimiento_id -> movimientos_tesoreria
--     inversiones.inversion_padre_entidad_id    -> inversiones
--     auditoria.actor_user_id                   -> usuarios
--
--   La primera es una fuga EXPLOTADA Y REPRODUCIDA: un tenant enlaza su
--   propio tercero con una direccion de otro tenant. Verificada en Supabase
--   por pytest y en Neon por SQL directo. El atacante no puede leer la fila
--   ajena, porque el RLS de direcciones la sigue tapando, pero crea una fila
--   hija sobre un dato que no le pertenece y bloquea el borrado legitimo del
--   propietario mediante un RESTRICT que este no puede diagnosticar.
--
--   HALLAZGO ASOCIADO. fn_check_reversion_movimiento SI contiene la
--   comprobacion de mismo owner, pero es inalcanzable: la funcion no es
--   SECURITY DEFINER, su SELECT sobre movimientos_tesoreria va bajo RLS y,
--   cuando el movimiento original pertenece a otro tenant, no devuelve fila,
--   la variable queda NULL y la funcion hace RETURN NEW sin comprobar nada.
--   La defensa se apaga exactamente en el caso para el que fue escrita. Es
--   el mismo patron que D-088.
--
--   CORRECCION. Se prefiere integridad declarativa donde es posible y
--   validacion cross-table en policy donde el padre esta en otra tabla y no
--   hay riesgo de recursion.
--
--   1) tercero_direcciones: se anade a WITH CHECK un EXISTS sobre
--      direcciones. Tabla distinta, no recurre. Es el patron que ya usan las
--      otras 42 policies con WITH CHECK ampliado.
--
--   2) auditoria: se anade a tenant_insert la condicion de que actor_user_id,
--      si viene informado, sea el propio tenant. No hace falta subconsulta
--      porque en usuarios el propietario es el propio id. gapto_runtime no
--      tiene INSERT sobre auditoria desde B15, asi que esto protege la via
--      del writer privilegiado frente a un contexto mal formado.
--
--   3) inversiones: se anade a WITH CHECK un EXISTS sobre entidades, no
--      sobre inversiones. No recurre, porque la propiedad de una inversion
--      vive en su entidad supertipo.
--
--   4) movimientos_tesoreria: la tabla no tiene owner_user_id y su propiedad
--      deriva de cuentas, de modo que no cabe ni EXISTS sobre si misma
--      (recursion, ver D-094) ni FK compuesto sobre owner. Se resuelve con
--      anchor UNIQUE (cuenta_id, id) y FK compuesto
--      (cuenta_id, reversion_de_movimiento_id) -> (cuenta_id, id), que obliga
--      a que la reversion viva en la MISMA CUENTA que el movimiento original.
--      Con MATCH SIMPLE, una reversion nula satisface la restriccion.
--      Es una restriccion semantica NUEVA y APROBADA EXPRESAMENTE: revertir
--      un movimiento sobre una cuenta distinta no tiene sentido financiero y
--      D-039 describe la reversion como un movimiento nuevo enlazado sobre el
--      mismo saldo. Misma cuenta implica mismo owner, de modo que la fuga
--      queda cerrada de forma declarativa y tambien frente a BYPASSRLS, que
--      es mas fuerte que cualquier comprobacion en policy o en trigger.
--
--   Se aplica D-095: la validacion de constraints sobre una tabla con FORCE
--   ROW LEVEL SECURITY se hace retirando FORCE y devolviendolo dentro de la
--   misma transaccion, para que el escaneo sea completo y no quede ventana.
--
--   No se modifica 0120 ni ninguna migration ya aplicada: forward-only. B13
--   se reabre parcialmente solo para estas cuatro policies/constraints y
--   vuelve a cerrarse. No reabre F03-00-H ni D-074, cuya intencion se
--   mantiene intacta: cambia el mecanismo, no la garantia.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 1) tercero_direcciones: la direccion debe ser del mismo tenant
-- ------------------------------------------------------------
ALTER POLICY tenant_isolation ON gapto.tercero_direcciones
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM gapto.terceros t1
             WHERE t1.id = tercero_direcciones.tercero_id
               AND t1.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        )
        AND EXISTS (
            SELECT 1 FROM gapto.direcciones t2
             WHERE t2.id = tercero_direcciones.direccion_id
               AND t2.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        )
    );

-- ------------------------------------------------------------
-- 2) auditoria: el actor, si se informa, es el propio tenant
-- ------------------------------------------------------------
ALTER POLICY tenant_insert ON gapto.auditoria
    WITH CHECK (
        owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        AND (
            actor_user_id IS NULL
            OR actor_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        )
    );

-- ------------------------------------------------------------
-- 3) inversiones: la inversion padre debe ser del mismo tenant
-- ------------------------------------------------------------
ALTER POLICY tenant_isolation ON gapto.inversiones
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM gapto.entidades t1
             WHERE t1.id = inversiones.entidad_id
               AND t1.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
        )
        AND (
            tercero_gestor_id IS NULL
            OR EXISTS (
                SELECT 1 FROM gapto.terceros t2
                 WHERE t2.id = inversiones.tercero_gestor_id
                   AND t2.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
            )
        )
        AND (
            inversion_padre_entidad_id IS NULL
            OR EXISTS (
                SELECT 1 FROM gapto.entidades t3
                 WHERE t3.id = inversiones.inversion_padre_entidad_id
                   AND t3.owner_user_id = (current_setting('gapto.owner_user_id', true))::uuid
            )
        )
    );

-- ------------------------------------------------------------
-- 4) movimientos_tesoreria: la reversion vive en la misma cuenta
-- ------------------------------------------------------------
ALTER TABLE gapto.movimientos_tesoreria
    ADD CONSTRAINT uq_movimientos_tesoreria__cuenta_anchor UNIQUE (cuenta_id, id);

ALTER TABLE gapto.movimientos_tesoreria NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.movimientos_tesoreria
    ADD CONSTRAINT fk_movimientos_tesoreria__reversion_misma_cuenta
    FOREIGN KEY (cuenta_id, reversion_de_movimiento_id)
    REFERENCES gapto.movimientos_tesoreria (cuenta_id, id)
    ON DELETE RESTRICT;

ALTER TABLE gapto.movimientos_tesoreria FORCE ROW LEVEL SECURITY;

RESET ROLE;

COMMIT;
