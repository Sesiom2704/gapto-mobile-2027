-- ============================================================
-- GAPTO MOBILE 2027 · LABORATORIO (no es la cadena oficial)
-- Fichero: LAB_0357_f06_04_rentas.sql
-- Ruta: lab/migrations/LAB_0357_f06_04_rentas.sql
-- Descripcion: LABORATORIO de T5 (mandato MANDATO_F06-T5_LAB_v1.0, rama lab-t5). NUNCA se aplica fuera del
--   cluster local desechable del laboratorio; fuera de migrations/ y sin numero de la cadena.
--   Prueba en codigo R9 (registro de cada revision y tope con receptor, VERSIONADOS) de las decisiones de
--   Moises del 2026-11-23 (F06-00_Decisiones_Moises_2026-11-23_T5_negocio_v1.0.md, c1c1f467…):
--   1) gapto.lab_renta_revisiones: una fila por aniversario y contrato con la renta anterior, el indice
--      tecleado, la renta exacta (4 decimales), la propuesta redondeada a la baja (R5), la decision
--      (APLICADA / NO_APLICADA, R4-A), la renta aplicada y los dos avisos registrados (R10). Historico: sin
--      UPDATE ni DELETE para runtime (una revision registrada no se reescribe).
--   2) gapto.lab_contrato_topes: tope (% sobre el total) con contrato RECEPTOR del exceso (R6), versionado por
--      vigencia sin solapes (EXCLUDE). Sin DELETE para runtime.
--   RLS FORCE por el owner del contrato (patron de contrato_revision_renta_versiones, 0120). Sin tocar ninguna
--   tabla existente. Prechecks: head 0356; postchecks: tablas, FORCE y grants.
-- Version: 0.1.0 (LAB T5 · L1)
-- ============================================================

BEGIN;

DO $$
BEGIN
    IF to_regclass('gapto.contratos') IS NULL OR to_regclass('gapto.contrato_revision_renta_versiones') IS NULL THEN
        RAISE EXCEPTION 'LAB_0357: falta la cadena 0001..0356';
    END IF;
    IF to_regclass('gapto.lab_renta_revisiones') IS NOT NULL THEN
        RAISE EXCEPTION 'LAB_0357: ya aplicada';
    END IF;
END $$;

SET ROLE gapto_owner;

CREATE TABLE gapto.lab_renta_revisiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    contrato_entidad_id uuid NOT NULL REFERENCES gapto.contratos (entidad_id) ON DELETE RESTRICT,
    aniversario date NOT NULL,
    renta_anterior numeric(14,2) NOT NULL,
    indice_texto varchar(80),
    indice_porcentaje numeric(9,4),
    renta_exacta numeric(14,4),
    renta_propuesta numeric(14,2),
    decision varchar(20) NOT NULL,
    renta_aplicada numeric(14,2),
    aviso_primero date,
    aviso_segundo date,
    motivo text,
    registrada_en timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_lab_renta_revisiones PRIMARY KEY (id),
    CONSTRAINT uq_lab_renta_revisiones__contrato_aniversario UNIQUE (contrato_entidad_id, aniversario),
    CONSTRAINT ck_lab_renta_revisiones__decision CHECK (decision IN ('APLICADA', 'NO_APLICADA')),
    CONSTRAINT ck_lab_renta_revisiones__aplicada_con_renta
        CHECK ((decision = 'APLICADA') = (renta_aplicada IS NOT NULL)),
    CONSTRAINT ck_lab_renta_revisiones__positivas
        CHECK (renta_anterior > 0 AND (renta_aplicada IS NULL OR renta_aplicada > 0)),
    CONSTRAINT ck_lab_renta_revisiones__redondeo_a_la_baja
        CHECK (renta_exacta IS NULL OR renta_propuesta IS NULL OR renta_propuesta <= renta_exacta),
    CONSTRAINT ck_lab_renta_revisiones__avisos_ordenados
        CHECK (aviso_primero IS NULL OR aviso_segundo IS NULL OR aviso_primero <= aviso_segundo)
);

CREATE TABLE gapto.lab_contrato_topes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    contrato_entidad_id uuid NOT NULL REFERENCES gapto.contratos (entidad_id) ON DELETE RESTRICT,
    receptor_contrato_entidad_id uuid NOT NULL REFERENCES gapto.contratos (entidad_id) ON DELETE RESTRICT,
    porcentaje_tope numeric(9,4) NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,
    registrada_en timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_lab_contrato_topes PRIMARY KEY (id),
    CONSTRAINT ck_lab_contrato_topes__porcentaje CHECK (porcentaje_tope > 0 AND porcentaje_tope <= 100),
    CONSTRAINT ck_lab_contrato_topes__receptor_distinto CHECK (receptor_contrato_entidad_id <> contrato_entidad_id),
    CONSTRAINT ck_lab_contrato_topes__vigencia CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ex_lab_contrato_topes__sin_solape EXCLUDE USING gist (
        contrato_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
);

ALTER TABLE gapto.lab_renta_revisiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.lab_renta_revisiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.lab_renta_revisiones
    USING (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id
                   WHERE m1.entidad_id = lab_renta_revisiones.contrato_entidad_id
                     AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id
                        WHERE m1.entidad_id = lab_renta_revisiones.contrato_entidad_id
                          AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.lab_contrato_topes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.lab_contrato_topes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.lab_contrato_topes
    USING (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id
                   WHERE m1.entidad_id = lab_contrato_topes.contrato_entidad_id
                     AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (
        EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id
                WHERE m1.entidad_id = lab_contrato_topes.contrato_entidad_id
                  AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
        AND EXISTS (SELECT 1 FROM gapto.contratos m2 JOIN gapto.entidades t2 ON t2.id = m2.entidad_id
                    WHERE m2.entidad_id = lab_contrato_topes.receptor_contrato_entidad_id
                      AND t2.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

GRANT SELECT, INSERT ON gapto.lab_renta_revisiones TO gapto_runtime;
GRANT SELECT, INSERT, UPDATE ON gapto.lab_contrato_topes TO gapto_runtime;
REVOKE UPDATE, DELETE ON gapto.lab_renta_revisiones FROM gapto_runtime;
REVOKE DELETE ON gapto.lab_contrato_topes FROM gapto_runtime;

RESET ROLE;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
     WHERE s.nspname = 'gapto' AND c.relname IN ('lab_renta_revisiones', 'lab_contrato_topes')
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF n <> 2 THEN RAISE EXCEPTION 'LAB_0357 postcheck: FORCE RLS en % de 2 tablas', n; END IF;
    IF has_table_privilege('gapto_runtime', 'gapto.lab_renta_revisiones', 'UPDATE')
       OR has_table_privilege('gapto_runtime', 'gapto.lab_renta_revisiones', 'DELETE')
       OR has_table_privilege('gapto_runtime', 'gapto.lab_contrato_topes', 'DELETE') THEN
        RAISE EXCEPTION 'LAB_0357 postcheck: privilegios de runtime de mas';
    END IF;
END $$;

COMMIT;
