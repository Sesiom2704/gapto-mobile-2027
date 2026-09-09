-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0130_f03_01_b14_grants_guards.sql
-- Descripcion: F03-01-B14. GRANTs de minimo privilegio sobre las 79 tablas
--   para los 5 roles conceptuales, mas guard triggers de inmutabilidad
--   (defensa en profundidad) sobre las 7 tablas append-only.
--
--   Reparto de GRANTs:
--   - gapto_owner: ya es propietario de las 79 tablas; sin GRANT adicional.
--   - gapto_migrator: opera via SET ROLE gapto_owner para DDL/seeds; sin
--     GRANT DML directo (evita superficie de ataque innecesaria).
--   - gapto_internal: SIN GRANTs todavia. Sus futuras funciones SECURITY
--     DEFINER (F03-00-H, aun no construidas) definiran que necesitan
--     exactamente; conceder DML amplio ahora sin funciones que lo consuman
--     viola minimo privilegio.
--   - gapto_runtime: USAGE en schema; SELECT/INSERT/UPDATE/DELETE en las
--     67 tablas de acceso completo; SELECT/INSERT (sin UPDATE/DELETE) en
--     las 7 tablas append-only; SELECT en los 5 catalogos globales.
--   - gapto_backup: BYPASSRLS (excepcion aprobada) + SELECT en las 79
--     tablas para volcado completo; sin escritura.
--
--   PUBLIC: REVOKE explicito en schema y tablas (defensa en profundidad
--   documentada, aunque el estado previo ya no tenia fugas) + ALTER
--   DEFAULT PRIVILEGES para que objetos futuros de gapto_owner tampoco
--   concedan nada a PUBLIC por defecto.
--
--   Guard triggers: BEFORE UPDATE OR DELETE que lanza excepcion
--   incondicional en las 7 tablas append-only, como defensa en
--   profundidad ante un GRANT futuro mal configurado (no depende
--   unicamente de la ausencia de policy RLS).
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- ============================================================
-- 0) Corrige BYPASSRLS de gapto_backup (excepcion aprobada en F03-00-H)
-- ============================================================
-- ALTER ROLE requiere CREATEROLE o ser dueño del rol; se ejecuta con el
-- rol de conexion (admin), ANTES de SET ROLE gapto_owner, porque
-- gapto_owner no tiene privilegio para alterar otros roles.
ALTER ROLE gapto_backup BYPASSRLS;

SET ROLE gapto_owner;

-- ============================================================
-- 1) REVOKE explicito de PUBLIC (defensa en profundidad documentada)
-- ============================================================
REVOKE ALL ON SCHEMA gapto FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA gapto FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE gapto_owner IN SCHEMA gapto
    REVOKE ALL ON TABLES FROM PUBLIC;

-- ============================================================
-- 2) USAGE de schema para los roles que acceden a datos
-- ============================================================
GRANT USAGE ON SCHEMA gapto TO gapto_runtime;
GRANT USAGE ON SCHEMA gapto TO gapto_backup;

-- ============================================================
-- 3) gapto_runtime: catalogos globales (solo lectura)
-- ============================================================
GRANT SELECT ON
    gapto.paises,
    gapto.regiones,
    gapto.localidades,
    gapto.tipos_hecho,
    gapto.metricas_definicion
TO gapto_runtime;

-- ============================================================
-- 4) gapto_runtime: 67 tablas de acceso completo
-- ============================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON
    gapto.acciones_rapidas, gapto.actores_financieros, gapto.categoria_magnitudes,
    gapto.categorias_financieras, gapto.cierres_mensuales, gapto.clasificaciones_tercero,
    gapto.configuracion_usuario, gapto.contextos, gapto.contrato_participantes,
    gapto.contrato_revision_renta_versiones, gapto.contrato_servicios, gapto.contratos,
    gapto.cuenta_capacidades, gapto.cuenta_participaciones, gapto.cuentas,
    gapto.derechos_obligaciones_financieras, gapto.direcciones, gapto.documento_vinculos,
    gapto.documentos, gapto.efecto_atribuciones, gapto.entidad_participaciones,
    gapto.entidad_relaciones, gapto.entidades, gapto.etiquetas,
    gapto.financiacion_condiciones_versiones, gapto.financiacion_cuotas, gapto.financiaciones,
    gapto.fuentes_importacion, gapto.hecho_aportaciones_pago, gapto.hecho_efectos,
    gapto.hecho_entidades, gapto.hecho_etiquetas, gapto.hecho_magnitudes,
    gapto.hecho_movimientos_tesoreria, gapto.hecho_participantes, gapto.hecho_relaciones,
    gapto.hecho_terceros, gapto.hechos_financieros, gapto.inversion_asignaciones_efecto,
    gapto.inversion_objetivos_versiones, gapto.inversion_valoraciones, gapto.inversiones,
    gapto.magnitudes, gapto.movimientos_tesoreria, gapto.plantillas_registro,
    gapto.preferencias_registro, gapto.preferencias_ui, gapto.presupuesto_linea_alcances,
    gapto.presupuesto_lineas, gapto.presupuestos, gapto.prevision_hechos,
    gapto.previsiones, gapto.propiedad_servicios, gapto.propiedad_valoraciones,
    gapto.propiedades, gapto.regla_excepciones, gapto.regla_versiones,
    gapto.reglas_financieras, gapto.servicios, gapto.tercero_afinidades,
    gapto.tercero_clasificaciones, gapto.tercero_direcciones, gapto.tercero_personas,
    gapto.tercero_roles, gapto.terceros, gapto.transferencias,
    gapto.usuarios
TO gapto_runtime;

-- ============================================================
-- 5) gapto_runtime: 7 tablas append-only -> solo SELECT + INSERT
-- ============================================================
GRANT SELECT, INSERT ON
    gapto.auditoria,
    gapto.cierre_metricas,
    gapto.cierre_posiciones_entidad,
    gapto.cierre_presupuesto_lineas,
    gapto.cierre_saldos_cuenta,
    gapto.mapeos_importacion,
    gapto.registros_origen_importacion
TO gapto_runtime;

-- ============================================================
-- 6) gapto_backup: SELECT en las 79 tablas (catalogos + tenant + append-only)
-- ============================================================
GRANT SELECT ON ALL TABLES IN SCHEMA gapto TO gapto_backup;

-- ============================================================
-- 7) Guard triggers de inmutabilidad (defensa en profundidad)
-- ============================================================
CREATE FUNCTION gapto.fn_guard_append_only()
RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'gapto.%: tabla append-only, UPDATE/DELETE no permitido (fila %)',
        TG_TABLE_NAME, COALESCE(OLD.id, NULL);
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_guard_append_only() IS
    'F03-01-B14: bloquea incondicionalmente UPDATE/DELETE sobre tablas append-only, como defensa en profundidad independiente de RLS/GRANT.';

CREATE TRIGGER trg_auditoria__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.auditoria
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_cierre_metricas__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.cierre_metricas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_cierre_posiciones_entidad__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.cierre_posiciones_entidad
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_cierre_presupuesto_lineas__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.cierre_presupuesto_lineas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_cierre_saldos_cuenta__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.cierre_saldos_cuenta
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_mapeos_importacion__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.mapeos_importacion
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

CREATE TRIGGER trg_registros_origen_importacion__guard_append_only
    BEFORE UPDATE OR DELETE ON gapto.registros_origen_importacion
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_append_only();

COMMIT;
