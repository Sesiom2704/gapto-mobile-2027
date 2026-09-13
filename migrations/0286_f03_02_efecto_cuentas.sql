-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0286_f03_02_efecto_cuentas.sql
-- Ruta: migrations/0286_f03_02_efecto_cuentas.sql
-- Descripcion: FASE 03 / F03-02. Ampliacion forward-only del nucleo de
--   hechos/efectos aprobada por la reapertura controlada F02-F01-R2. No edita
--   la cadena congelada 0001..0240 ni reabre 0250..0285. Queda fuera D-080
--   (0290).
--
--   CARENCIA. El modelo representa el efecto economico, la cuenta que paga
--   (movimientos_tesoreria, hecho_movimientos_tesoreria,
--   hecho_aportaciones_pago), la deuda de un instrumento (saldo_apertura mas
--   movimientos) y el tercero (hecho_terceros, hecho_entidades), pero NO la
--   frase "este efecto economico lo genero este instrumento". Caso real: una
--   poliza de credito POL1 con limite 30.000 y dispuesto 0 devenga una
--   comision trimestral de 9,90 que se paga desde la cuenta corriente CC1. El
--   gasto existe, la deuda de POL1 sigue siendo 0 y la salida real es de CC1.
--   Mismo patron en intereses de poliza, comision de mantenimiento de cuenta
--   corriente, cuota anual de tarjeta e intereses de descubierto.
--
--   RELACION. Se crea gapto.efecto_cuentas, puente de la familia de
--   efecto_atribuciones:
--     efecto --GENERADO_POR--> cuenta
--   Es exclusivamente trazabilidad semantica de dominio. No modifica saldo,
--   deuda ni liquidez, no crea gasto ni ingreso, y no sustituye a tesoreria ni
--   a aportaciones. La deuda de una cuenta sigue derivandose SOLO de
--   saldo_apertura mas movimientos_tesoreria validos. Esta migration no crea
--   ninguna funcion ni ningun trigger, de modo que la tabla es fisicamente
--   incapaz de alterar un saldo.
--
--   NIVEL DE EFECTO, NO DE HECHO. efecto_id es NOT NULL. El caso real no dice
--   "el hecho pertenece a la poliza" sino "este gasto lo genero la poliza", y
--   un hecho puede tener varios efectos de los que solo uno corresponda a la
--   cuenta. Admitir efecto_id NULL crearia de inmediato una ambiguedad entre
--   la relacion del hecho y la del efecto que exigiria reglas de precedencia o
--   un trigger cross-row sin necesidad demostrada. Si en F04/F05 aparece un
--   caso real de relacion a nivel de hecho, relajar el NOT NULL es forward-only
--   y trivial.
--
--   UNA SOLA CUENTA GENERADORA POR EFECTO. ux_efecto_cuentas__generado_por
--   impone como maximo un GENERADO_POR por efecto. Si un efecto pudiera tener
--   dos cuentas generadoras, GENERADO_POR dejaria de significar origen. Una
--   comision conjunta de dos instrumentos se representa como dos efectos, o
--   exigira decidir otra semantica; no se degrada GENERADO_POR por una
--   hipotesis. Imponer 1 ahora y relajarlo despues es trivial; permitir N y
--   querer imponer 1 mas tarde exigiria sanear datos. Ademas evita reproducir
--   aqui el problema de unicidad que D-080 resuelve en 0290.
--
--   VOCABULARIO MINIMO. tipo_relacion admite unicamente GENERADO_POR.
--   PAGADO_DESDE y FINANCIADO_POR no se anaden: ya estan representados
--   autoritativamente por movimientos_tesoreria y hecho_aportaciones_pago, y
--   duplicarlos crearia una segunda fuente de verdad.
--
--   OWNERSHIP DECLARATIVO. La tabla lleva owner_user_id y hecho_id, que no son
--   redundancia decorativa: permiten resolver el aislamiento con FK compuestas
--   contra los anchors ya existentes, sin un solo trigger.
--     fk_efecto_cuentas__hecho  (owner_user_id, hecho_id)
--         -> hechos_financieros(owner_user_id, id)
--     fk_efecto_cuentas__efecto (hecho_id, efecto_id)
--         -> hecho_efectos(hecho_id, id)
--     fk_efecto_cuentas__cuenta (owner_user_id, cuenta_id)
--         -> cuentas(owner_user_id, id)
--   La cadena encadena cuenta.owner = owner = hecho.owner y garantiza que el
--   efecto pertenece exactamente a ese hecho. Cumple D-100: la coherencia de
--   tenant es de PostgreSQL y sobrevive a BYPASSRLS; no depende de RLS. Es el
--   patron de anchors de D-094/B19 y mejora el de hecho_entidades, cuyo
--   same-owner solo vive en el WITH CHECK de su policy.
--
--   Los dos indices secundarios cubren la primera columna de cada FK
--   (F03-00-E1/I): (owner_user_id, cuenta_id) encabeza owner_user_id, que es
--   la primera columna de las FK al hecho y a la cuenta, y (hecho_id,
--   efecto_id) encabeza hecho_id, primera columna de la FK al efecto.
--
--   Todas las FK son ON DELETE RESTRICT, conforme a la politica de historico y
--   finanzas. La FK a cuentas no mira enabled ni fecha_cierre: una cuenta
--   cerrada sigue siendo historicamente valida como cuenta generadora.
--
--   LIFECYCLE. Sin enabled, sin deleted_at, sin timestamps y sin principal: la
--   familia de puentes del nucleo no los lleva. La correccion de una relacion
--   mal capturada es un UPDATE auditado de cuenta_id.
--
--   DELETE, BUCKET A. La tabla pertenece a la realidad financiera y a sus
--   vinculos, la familia que D-093/B18 cubrio para hecho_entidades,
--   hecho_participantes, hecho_terceros, hecho_magnitudes y hecho_relaciones.
--   No es una raiz de identidad de las de D-105/B21. Por tanto gapto_runtime
--   recibe SELECT, INSERT y UPDATE, y NO recibe DELETE. Retirar por completo
--   un vinculo sobrante no es posible desde runtime; ese caso queda igual de
--   abierto que para los demas puentes del hecho y se decidira explicitamente
--   si el backend demuestra que la operacion es legitima.
--
--   CONTRATO FISICO. La tabla nueva cambia deliberadamente el techo de 79
--   tablas fijado en F03-01-B07, las 81 policies de B13 y la matriz de GRANTs
--   de B14/B16/B18/B21. Resultado esperado: 80 tablas, 169 FK, 41 UNIQUE, 82
--   policies, 5 indices nuevos y 12 GRANTs nuevos. Funciones (25), triggers
--   (48), constraint triggers (31), EXCLUDE (11) y vistas (3) NO cambian,
--   porque esta migration no crea ninguno.
--
--   Migration V3: V3 solo conserva la cuenta pagadora. La cuenta generadora se
--   migrara unicamente cuando pueda demostrarse; si solo se conoce el banco o
--   un texto ambiguo, la relacion no se crea. Desconocido permanece
--   desconocido.
--
-- Decision: D-146 / F02-F01-R2
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0286$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-02-0286 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    IF to_regclass('gapto.efecto_cuentas') IS NOT NULL THEN
        v_rep := v_rep || ' gapto.efecto_cuentas ya existe;';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r';
    IF v_n <> 79 THEN
        v_rep := v_rep || pg_catalog.format(' tablas=%s (esperadas 79 antes de 0286);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND k.contype = 'u'
       AND k.conname IN ('uq_hechos_financieros__owner_anchor', 'uq_cuentas__owner_anchor',
                         'uq_hecho_efectos__hecho_anchor');
    IF v_n <> 3 THEN
        v_rep := v_rep || pg_catalog.format(' anchors_presentes=%s (esperados 3);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0286 PRECHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-02-0286 PRECHECK: OK';
END;
$precheck_0286$;

SET ROLE gapto_owner;

-- ============================================================
-- 1) Tabla puente efecto -> cuenta generadora
-- ============================================================
CREATE TABLE gapto.efecto_cuentas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    hecho_id uuid NOT NULL,
    efecto_id uuid NOT NULL,
    cuenta_id uuid NOT NULL,
    tipo_relacion varchar(50) NOT NULL,

    CONSTRAINT pk_efecto_cuentas PRIMARY KEY (id),
    CONSTRAINT ck_efecto_cuentas__tipo_relacion
        CHECK (tipo_relacion IN ('GENERADO_POR')),
    CONSTRAINT uq_efecto_cuentas__efecto_cuenta_tipo
        UNIQUE (efecto_id, cuenta_id, tipo_relacion),
    CONSTRAINT fk_efecto_cuentas__hecho
        FOREIGN KEY (owner_user_id, hecho_id)
        REFERENCES gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_efecto_cuentas__efecto
        FOREIGN KEY (hecho_id, efecto_id)
        REFERENCES gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_efecto_cuentas__cuenta
        FOREIGN KEY (owner_user_id, cuenta_id)
        REFERENCES gapto.cuentas(owner_user_id, id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ux_efecto_cuentas__generado_por
    ON gapto.efecto_cuentas (efecto_id) WHERE tipo_relacion = 'GENERADO_POR';

CREATE INDEX ix_efecto_cuentas__cuenta
    ON gapto.efecto_cuentas (owner_user_id, cuenta_id);

CREATE INDEX ix_efecto_cuentas__hecho
    ON gapto.efecto_cuentas (hecho_id, efecto_id);

-- ============================================================
-- 2) RLS
-- ============================================================
ALTER TABLE gapto.efecto_cuentas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.efecto_cuentas FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON gapto.efecto_cuentas
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

RESET ROLE;

-- ============================================================
-- 3) GRANTs. Bucket A: runtime sin DELETE.
-- ============================================================
GRANT SELECT, INSERT, UPDATE ON gapto.efecto_cuentas TO gapto_runtime;
GRANT SELECT ON gapto.efecto_cuentas TO gapto_backup;

DO $postcheck_0286$
DECLARE
    v_n bigint;
    v_b boolean;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r';
    IF v_n <> 80 THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: tablas = % (esperadas 80)', v_n;
    END IF;

    SELECT c.relrowsecurity AND c.relforcerowsecurity INTO v_b
      FROM pg_catalog.pg_class c WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass;
    IF NOT coalesce(v_b, false) THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: efecto_cuentas sin RLS ENABLE + FORCE';
    END IF;

    IF pg_catalog.pg_get_userbyid((SELECT c.relowner FROM pg_catalog.pg_class c
        WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass)) <> 'gapto_owner' THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: efecto_cuentas no pertenece a gapto_owner';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass
       AND k.contype = 'f' AND k.confdeltype = 'r' AND k.convalidated;
    IF v_n <> 3 THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: FK RESTRICT validadas = % (esperadas 3)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c, pg_catalog.aclexplode(c.relacl) e
     WHERE c.oid = 'gapto.efecto_cuentas'::pg_catalog.regclass
       AND e.grantee::pg_catalog.regrole::text = 'gapto_runtime'
       AND e.privilege_type = 'DELETE';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: gapto_runtime tiene DELETE sobre efecto_cuentas';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid = 'gapto.efecto_cuentas'::pg_catalog.regclass AND NOT t.tgisinternal;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: efecto_cuentas tiene % triggers; debe ser inerte', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i
     WHERE i.schemaname = 'gapto' AND i.tablename = 'efecto_cuentas';
    IF v_n <> 5 THEN
        RAISE EXCEPTION 'F03-02-0286 POSTCHECK: indices de efecto_cuentas = % (esperados 5)', v_n;
    END IF;

    RAISE NOTICE 'F03-02-0286 POSTCHECK: OK';
END;
$postcheck_0286$;

COMMIT;
