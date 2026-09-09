-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0080_f03_01_b08_anchors_unique.sql
-- Ruta: migrations/0080_f03_01_b08_anchors_unique.sql
-- Descripción: Materializa los anchors auxiliares (owner_id, id) y las
--              UNIQUE conceptuales fijadas en F03-00-E2 sobre las 79
--              tablas ya existentes. No crea FK, EXCLUDE ni tablas
--              nuevas. Los anchors (cuentas, entidades, hechos_financieros,
--              hecho_efectos, hecho_movimientos_tesoreria,
--              financiacion_condiciones_versiones, cierres_mensuales)
--              existen para que F03-01-B09 pueda construir FK compuestas
--              de ownership/pertenencia sin añadir columnas redundantes.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_unique_count integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 79 THEN
        RAISE EXCEPTION 'F03-01-B08 PRECHECK: esperadas exactamente 79 tablas; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_unique_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'u';

    IF v_unique_count <> 0 THEN
        RAISE EXCEPTION 'F03-01-B08 PRECHECK: ya existen % constraints UNIQUE; se esperaba 0', v_unique_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 1. usuarios
ALTER TABLE gapto.usuarios ADD CONSTRAINT uq_usuarios__email UNIQUE (email);

-- 5. paises
ALTER TABLE gapto.paises ADD CONSTRAINT uq_paises__iso2 UNIQUE (iso2);
ALTER TABLE gapto.paises ADD CONSTRAINT uq_paises__iso3 UNIQUE (iso3);

-- 10. tercero_direcciones
ALTER TABLE gapto.tercero_direcciones ADD CONSTRAINT uq_tercero_direcciones__tercero_direccion_tipo
    UNIQUE (tercero_id, direccion_id, tipo);

-- 11. actores_financieros (self = tercero_id NULL; NULLS NOT DISTINCT evita múltiples selfs)
ALTER TABLE gapto.actores_financieros ADD CONSTRAINT uq_actores_financieros__owner_tercero
    UNIQUE NULLS NOT DISTINCT (owner_user_id, tercero_id);

-- 12. tercero_roles
ALTER TABLE gapto.tercero_roles ADD CONSTRAINT uq_tercero_roles__tercero_rol
    UNIQUE (tercero_id, rol_codigo);

-- 13. clasificaciones_tercero (nombre único entre hermanos activos; codigo único por owner)
CREATE UNIQUE INDEX uq_clasificaciones_tercero__owner_parent_nombre
    ON gapto.clasificaciones_tercero (owner_user_id, parent_id, nombre)
    NULLS NOT DISTINCT
    WHERE enabled = true;
CREATE UNIQUE INDEX uq_clasificaciones_tercero__owner_codigo
    ON gapto.clasificaciones_tercero (owner_user_id, codigo)
    WHERE codigo IS NOT NULL;

-- 14. tercero_clasificaciones
ALTER TABLE gapto.tercero_clasificaciones ADD CONSTRAINT uq_tercero_clasificaciones__tercero_clasificacion
    UNIQUE (tercero_id, clasificacion_id);

-- 15. categorias_financieras (mismo patrón que clasificaciones_tercero)
CREATE UNIQUE INDEX uq_categorias_financieras__owner_parent_nombre
    ON gapto.categorias_financieras (owner_user_id, parent_id, nombre)
    NULLS NOT DISTINCT
    WHERE enabled = true;
CREATE UNIQUE INDEX uq_categorias_financieras__owner_codigo
    ON gapto.categorias_financieras (owner_user_id, codigo)
    WHERE codigo IS NOT NULL;

-- 16. tercero_afinidades
ALTER TABLE gapto.tercero_afinidades ADD CONSTRAINT uq_tercero_afinidades__tercero_categoria
    UNIQUE (tercero_id, categoria_id);

-- 17. tipos_hecho
ALTER TABLE gapto.tipos_hecho ADD CONSTRAINT uq_tipos_hecho__codigo UNIQUE (codigo);

-- 18. magnitudes
ALTER TABLE gapto.magnitudes ADD CONSTRAINT uq_magnitudes__owner_nombre UNIQUE (owner_user_id, nombre);

-- 19. categoria_magnitudes
ALTER TABLE gapto.categoria_magnitudes ADD CONSTRAINT uq_categoria_magnitudes__categoria_magnitud
    UNIQUE (categoria_id, magnitud_id);

-- 22. cuentas: anchor de ownership para FK compuestas de B09
ALTER TABLE gapto.cuentas ADD CONSTRAINT uq_cuentas__owner_anchor UNIQUE (owner_user_id, id);

-- 23. cuenta_capacidades
ALTER TABLE gapto.cuenta_capacidades ADD CONSTRAINT uq_cuenta_capacidades__cuenta_capacidad
    UNIQUE (cuenta_id, capacidad_codigo);

-- 25. entidades: anchor de ownership para FK compuestas de B09
ALTER TABLE gapto.entidades ADD CONSTRAINT uq_entidades__owner_anchor UNIQUE (owner_user_id, id);

-- 31. regla_excepciones
ALTER TABLE gapto.regla_excepciones ADD CONSTRAINT uq_regla_excepciones__regla_fecha
    UNIQUE (regla_id, fecha_objetivo);

-- 33. hechos_financieros: anchor de ownership
ALTER TABLE gapto.hechos_financieros ADD CONSTRAINT uq_hechos_financieros__owner_anchor
    UNIQUE (owner_user_id, id);

-- 34. hecho_efectos: anchor de pertenencia a hecho
ALTER TABLE gapto.hecho_efectos ADD CONSTRAINT uq_hecho_efectos__hecho_anchor
    UNIQUE (hecho_id, id);

-- 35. efecto_atribuciones
ALTER TABLE gapto.efecto_atribuciones ADD CONSTRAINT uq_efecto_atribuciones__efecto_actor
    UNIQUE (efecto_id, actor_id);

-- 36. hecho_terceros
ALTER TABLE gapto.hecho_terceros ADD CONSTRAINT uq_hecho_terceros__hecho_tercero_rol
    UNIQUE (hecho_id, tercero_id, rol_en_hecho);

-- 37. hecho_entidades (efecto_id=NULL conserva semántica real de relación a nivel de hecho)
ALTER TABLE gapto.hecho_entidades ADD CONSTRAINT uq_hecho_entidades__hecho_efecto_entidad_tipo
    UNIQUE NULLS NOT DISTINCT (hecho_id, efecto_id, entidad_id, tipo_relacion);

-- 38. hecho_participantes
ALTER TABLE gapto.hecho_participantes ADD CONSTRAINT uq_hecho_participantes__hecho_actor_rol
    UNIQUE (hecho_id, actor_id, rol);

-- 41. hecho_movimientos_tesoreria: UNIQUE conceptual + anchor de pertenencia a hecho
ALTER TABLE gapto.hecho_movimientos_tesoreria ADD CONSTRAINT uq_hecho_movimientos_tesoreria__hecho_movimiento
    UNIQUE (hecho_id, movimiento_tesoreria_id);
ALTER TABLE gapto.hecho_movimientos_tesoreria ADD CONSTRAINT uq_hecho_movimientos_tesoreria__hecho_anchor
    UNIQUE (hecho_id, id);

-- 42. transferencias: ya especificado en el diseño lógico como UNIQUE por movimiento
ALTER TABLE gapto.transferencias ADD CONSTRAINT uq_transferencias__movimiento_salida
    UNIQUE (movimiento_salida_id);
ALTER TABLE gapto.transferencias ADD CONSTRAINT uq_transferencias__movimiento_entrada
    UNIQUE (movimiento_entrada_id);

-- 43. prevision_hechos
ALTER TABLE gapto.prevision_hechos ADD CONSTRAINT uq_prevision_hechos__prevision_hecho
    UNIQUE (prevision_id, hecho_id);

-- 44. hecho_magnitudes
ALTER TABLE gapto.hecho_magnitudes ADD CONSTRAINT uq_hecho_magnitudes__hecho_magnitud
    UNIQUE (hecho_id, magnitud_id);

-- 55. financiacion_condiciones_versiones: anchor de pertenencia a financiación
ALTER TABLE gapto.financiacion_condiciones_versiones ADD CONSTRAINT uq_financiacion_condiciones_versiones__financiacion_anchor
    UNIQUE (financiacion_entidad_id, id);

-- 56. financiacion_cuotas: única por versión+número solo cuando la versión es conocida
CREATE UNIQUE INDEX uq_financiacion_cuotas__condicion_numero
    ON gapto.financiacion_cuotas (condicion_version_id, numero_cuota)
    WHERE condicion_version_id IS NOT NULL;

-- 62. cierres_mensuales: anchor de ownership + UNIQUE ya aprobada owner+periodo+versión
ALTER TABLE gapto.cierres_mensuales ADD CONSTRAINT uq_cierres_mensuales__owner_anchor
    UNIQUE (owner_user_id, id);
ALTER TABLE gapto.cierres_mensuales ADD CONSTRAINT uq_cierres_mensuales__owner_periodo_version
    UNIQUE (owner_user_id, periodo_desde, periodo_hasta, version_cierre);

-- 65. metricas_definicion
ALTER TABLE gapto.metricas_definicion ADD CONSTRAINT uq_metricas_definicion__codigo UNIQUE (codigo);

-- 68. documentos: deduplicación opcional por hash cuando existe
CREATE UNIQUE INDEX uq_documentos__owner_sha256
    ON gapto.documentos (owner_user_id, sha256)
    WHERE sha256 IS NOT NULL;

-- 69. documento_vinculos: exactamente un destino por fila (impuesto por CHECK);
--     unicidad documento+destino+rol respetando el destino nullable vía índices parciales
CREATE UNIQUE INDEX uq_documento_vinculos__hecho
    ON gapto.documento_vinculos (documento_id, hecho_id, rol_vinculo)
    WHERE hecho_id IS NOT NULL;
CREATE UNIQUE INDEX uq_documento_vinculos__entidad
    ON gapto.documento_vinculos (documento_id, entidad_id, rol_vinculo)
    WHERE entidad_id IS NOT NULL;
CREATE UNIQUE INDEX uq_documento_vinculos__tercero
    ON gapto.documento_vinculos (documento_id, tercero_id, rol_vinculo)
    WHERE tercero_id IS NOT NULL;
CREATE UNIQUE INDEX uq_documento_vinculos__cuenta
    ON gapto.documento_vinculos (documento_id, cuenta_id, rol_vinculo)
    WHERE cuenta_id IS NOT NULL;

-- 70. etiquetas: unicidad case-insensitive por owner
CREATE UNIQUE INDEX uq_etiquetas__owner_nombre_normalizado
    ON gapto.etiquetas (owner_user_id, lower(nombre));

-- 71. hecho_etiquetas
ALTER TABLE gapto.hecho_etiquetas ADD CONSTRAINT uq_hecho_etiquetas__hecho_etiqueta
    UNIQUE (hecho_id, etiqueta_id);

-- 73. inversion_asignaciones_efecto
ALTER TABLE gapto.inversion_asignaciones_efecto ADD CONSTRAINT uq_inversion_asignaciones_efecto__efecto_inversion
    UNIQUE (efecto_inversion_id, inversion_entidad_id);

-- 76. registros_origen_importacion: única solo cuando la clave de origen es fiable/conocida
CREATE UNIQUE INDEX uq_registros_origen_importacion__fuente_contenedor_clave
    ON gapto.registros_origen_importacion (fuente_importacion_id, contenedor_origen, clave_origen)
    WHERE clave_origen IS NOT NULL;

RESET ROLE;

DO $gapto$
DECLARE
    v_unique_count integer;
    v_expected integer := 46; -- 33 ALTER TABLE ADD CONSTRAINT UNIQUE + 13 CREATE UNIQUE INDEX
BEGIN
    SELECT count(*) INTO v_unique_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'u';

    IF v_unique_count <> 33 THEN
        RAISE EXCEPTION 'F03-01-B08 POSTCHECK: esperadas 33 constraints UNIQUE (ALTER TABLE); encontradas=%', v_unique_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
