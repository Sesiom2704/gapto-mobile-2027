-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0140_f03_01_views_readmodel.sql
-- Descripcion: Las 3 vistas read-model aprobadas en F03-00-I.
--   Todas security_invoker=true (obligatorio segun la decision
--   cerrada): la vista se ejecuta con los privilegios y RLS del
--   rol que consulta, nunca con los de gapto_owner. No dependen
--   de contenido de tipos_hecho ni metricas_definicion (pendientes
--   de microdecision funcional), solo de estructura ya cerrada.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ============================================================
-- 1) v_hechos_resumen: hecho + desglose de efectos por tipo_efecto
--    (sin fusionar naturalezas: cada tipo_efecto en su propia columna)
-- ============================================================
CREATE VIEW gapto.v_hechos_resumen
WITH (security_invoker = true) AS
SELECT
    h.id AS hecho_id,
    h.owner_user_id,
    h.tipo_hecho_id,
    h.fecha_hecho,
    h.concepto,
    h.moneda,
    h.estado,
    h.presupuestable,
    h.importe_total,
    h.numero_participantes_total,
    COALESCE(e.total_gasto, 0)          AS total_gasto,
    COALESCE(e.total_ingreso, 0)        AS total_ingreso,
    COALESCE(e.total_deuda, 0)          AS total_deuda,
    COALESCE(e.total_derecho_cobro, 0)  AS total_derecho_cobro,
    COALESCE(e.total_inversion, 0)      AS total_inversion,
    COALESCE(e.total_valor_activo, 0)   AS total_valor_activo,
    COALESCE(e.num_efectos, 0)          AS num_efectos
FROM gapto.hechos_financieros h
LEFT JOIN LATERAL (
    SELECT
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'GASTO')          AS total_gasto,
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'INGRESO')        AS total_ingreso,
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'DEUDA')          AS total_deuda,
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'DERECHO_COBRO')  AS total_derecho_cobro,
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'INVERSION')      AS total_inversion,
        sum(importe_delta) FILTER (WHERE tipo_efecto = 'VALOR_ACTIVO')   AS total_valor_activo,
        count(*)                                                        AS num_efectos
    FROM gapto.hecho_efectos he
    WHERE he.hecho_id = h.id
) e ON true;

COMMENT ON VIEW gapto.v_hechos_resumen IS
    'F03-01: read-model aprobado en F03-00-I. Resumen por hecho con desglose de efectos por tipo_efecto (sin sumar naturalezas distintas entre si).';

-- ============================================================
-- 2) v_movimientos_conciliacion: movimiento de tesoreria vs hechos
--    vinculados (grado de conciliacion, sin inferir nada no asignado)
-- ============================================================
CREATE VIEW gapto.v_movimientos_conciliacion
WITH (security_invoker = true) AS
SELECT
    m.id AS movimiento_id,
    c.owner_user_id,
    m.cuenta_id,
    m.fecha_movimiento,
    m.importe AS importe_movimiento,
    m.descripcion,
    m.clase_movimiento,
    m.estado,
    COALESCE(hm.total_asignado, 0) AS importe_conciliado,
    m.importe - COALESCE(hm.total_asignado, 0) AS importe_pendiente_conciliar,
    COALESCE(hm.num_hechos, 0) AS num_hechos_vinculados
FROM gapto.movimientos_tesoreria m
JOIN gapto.cuentas c ON c.id = m.cuenta_id
LEFT JOIN LATERAL (
    SELECT sum(importe_asignado) AS total_asignado, count(*) AS num_hechos
    FROM gapto.hecho_movimientos_tesoreria hmt
    WHERE hmt.movimiento_tesoreria_id = m.id
) hm ON true;

COMMENT ON VIEW gapto.v_movimientos_conciliacion IS
    'F03-01: read-model aprobado en F03-00-I. Grado de conciliacion de cada movimiento de tesoreria frente a los hechos que lo referencian via hecho_movimientos_tesoreria.';

-- ============================================================
-- 3) v_previsiones_realizacion: previsiones vs hechos que las
--    satisfacen (cobertura real, sin exigir SUM=esperado)
-- ============================================================
CREATE VIEW gapto.v_previsiones_realizacion
WITH (security_invoker = true) AS
SELECT
    p.id AS prevision_id,
    p.owner_user_id,
    p.concepto,
    p.tipo_hecho_id,
    p.categoria_id,
    p.tercero_id,
    p.entidad_id,
    p.fecha_esperada_desde,
    p.fecha_esperada_hasta,
    p.flujo_tesoreria_esperado,
    p.moneda,
    p.importe_esperado,
    p.estado,
    COALESCE(ph.total_asignado, 0) AS importe_realizado,
    p.importe_esperado - COALESCE(ph.total_asignado, 0) AS importe_pendiente,
    COALESCE(ph.num_hechos, 0) AS num_hechos_asignados
FROM gapto.previsiones p
LEFT JOIN LATERAL (
    SELECT sum(importe_asignado) AS total_asignado, count(*) AS num_hechos
    FROM gapto.prevision_hechos ph2
    WHERE ph2.prevision_id = p.id
) ph ON true;

COMMENT ON VIEW gapto.v_previsiones_realizacion IS
    'F03-01: read-model aprobado en F03-00-I. Grado de realizacion de cada prevision frente a los hechos asignados via prevision_hechos; no exige cobertura total para permanecer ABIERTA.';

-- ============================================================
-- 4) GRANTs sobre las vistas (no heredan del GRANT previo a tablas)
-- ============================================================
GRANT SELECT ON gapto.v_hechos_resumen TO gapto_runtime, gapto_backup;
GRANT SELECT ON gapto.v_movimientos_conciliacion TO gapto_runtime, gapto_backup;
GRANT SELECT ON gapto.v_previsiones_realizacion TO gapto_runtime, gapto_backup;

RESET ROLE;

DO $gapto$
DECLARE
    v_vistas integer;
    v_invoker integer;
BEGIN
    SELECT count(*) INTO v_vistas FROM pg_views WHERE schemaname='gapto' AND viewname LIKE 'v\_%';
    SELECT count(*) INTO v_invoker
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='gapto' AND c.relkind='v' AND c.reloptions @> ARRAY['security_invoker=true'];

    IF v_vistas <> 3 THEN
        RAISE EXCEPTION 'POSTCHECK: esperadas 3 vistas v_%%; encontradas=%', v_vistas;
    END IF;
    IF v_invoker <> 3 THEN
        RAISE EXCEPTION 'POSTCHECK: esperadas 3 vistas con security_invoker=true; encontradas=%', v_invoker;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
