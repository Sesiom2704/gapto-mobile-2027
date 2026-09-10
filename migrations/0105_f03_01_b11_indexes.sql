-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0105_f03_01_b11_indexes.sql
-- Ruta: migrations/0105_f03_01_b11_indexes.sql
-- Descripcion: Materializa los 134 indices de F03-01-B11: 109 de
--   cobertura de FK (toda FK sin cobertura equivalente por PK/UNIQUE/
--   EXCLUDE recibe indice util, per F03-00-E1/I), 19 compuestos de
--   patron de acceso demostrable (owner+fecha, cuenta+fecha, etc.,
--   per F03-00-I) y 6 GIN pg_trgm sobre busqueda humana (terceros.
--   nombre/nombre_legal, entidades.nombre, hechos_financieros.concepto,
--   documentos.titulo/nombre_archivo_original), unica extension de
--   busqueda aprobada -- sin full-text search, unaccent ni motor externo.
--   No incluye los 11 indices GiST que ya crean automaticamente los
--   EXCLUDE de B10, ni las anchors/UNIQUE de B08 (45) ni las FK de B09
--   (161), que ya tienen su propio indice por definicion de constraint.
-- Version: 0.1.1
-- Nota v0.1.1 (excepcion pre-freeze F03-GATE-01): las seis referencias a
--   gin_trgm_ops pasan a estar cualificadas como gapto_ext.gin_trgm_ops.
--   Sin cualificar, el fichero solo funcionaba si la sesion traia gapto_ext en
--   el search_path, cosa que ninguna migration fija: 0002 establece timezone y
--   default_transaction_isolation por ALTER DATABASE, pero no search_path. El
--   fichero era por tanto irreproducible desde una sesion limpia. El cambio es
--   semanticamente neutro: el catalogo de Neon y Supabase ya almacena estos
--   indices con el opclass cualificado, de modo que la correccion alinea el
--   fichero con lo que la base ya contiene. No se anade SET search_path, no se
--   toca ninguna otra definicion y NO se reaplica sobre las bases existentes.
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_index i ON i.indexrelid=c.oid
     WHERE n.nspname='gapto' AND c.relkind='i' AND NOT i.indisprimary
       AND NOT i.indisunique
       AND NOT EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid=c.oid AND con.contype='x');
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'PRECHECK: ya existen % indices secundarios (no-EXCLUDE) en gapto; se esperaba 0', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

CREATE INDEX ix_acciones_rapidas__owner ON gapto.acciones_rapidas (owner_user_id);
CREATE INDEX ix_acciones_rapidas__plantilla ON gapto.acciones_rapidas (plantilla_registro_id);
CREATE INDEX ix_actores_financieros__tercero ON gapto.actores_financieros (tercero_id);
CREATE INDEX ix_auditoria__actor ON gapto.auditoria (actor_user_id);
CREATE INDEX ix_auditoria__owner ON gapto.auditoria (owner_user_id);
CREATE INDEX ix_categoria_magnitudes__magnitud ON gapto.categoria_magnitudes (magnitud_id);
CREATE INDEX ix_categorias_financieras__parent ON gapto.categorias_financieras (parent_id);
CREATE INDEX ix_cierre_metricas__cierre ON gapto.cierre_metricas (cierre_id);
CREATE INDEX ix_cierre_metricas__metrica ON gapto.cierre_metricas (metrica_id);
CREATE INDEX ix_cierre_posiciones_entidad__cierre ON gapto.cierre_posiciones_entidad (cierre_id);
CREATE INDEX ix_cierre_posiciones_entidad__entidad ON gapto.cierre_posiciones_entidad (entidad_id);
CREATE INDEX ix_cierre_presupuesto_lineas__cierre ON gapto.cierre_presupuesto_lineas (cierre_id);
CREATE INDEX ix_cierre_presupuesto_lineas__linea ON gapto.cierre_presupuesto_lineas (presupuesto_linea_id);
CREATE INDEX ix_cierre_saldos_cuenta__cierre ON gapto.cierre_saldos_cuenta (cierre_id);
CREATE INDEX ix_cierre_saldos_cuenta__cuenta ON gapto.cierre_saldos_cuenta (cuenta_id);
CREATE INDEX ix_cierres_mensuales__reemplaza ON gapto.cierres_mensuales (reemplaza_cierre_id);
CREATE INDEX ix_clasificaciones_tercero__parent ON gapto.clasificaciones_tercero (parent_id);
CREATE INDEX ix_contrato_participantes__actor ON gapto.contrato_participantes (actor_id);
CREATE INDEX ix_contrato_servicios__actor_repercusion ON gapto.contrato_servicios (actor_repercusion_id);
CREATE INDEX ix_contrato_servicios__servicio ON gapto.contrato_servicios (servicio_entidad_id);
CREATE INDEX ix_contratos__propiedad ON gapto.contratos (propiedad_entidad_id);
CREATE INDEX ix_contratos__regla_renta ON gapto.contratos (regla_renta_id);
CREATE INDEX ix_cuenta_participaciones__actor ON gapto.cuenta_participaciones (actor_id);
CREATE INDEX ix_cuentas__tercero_gestor ON gapto.cuentas (tercero_gestor_id);
CREATE INDEX ix_derechos_obligaciones_financieras__contraparte ON gapto.derechos_obligaciones_financieras (contraparte_actor_id);
CREATE INDEX ix_direcciones__localidad ON gapto.direcciones (localidad_id);
CREATE INDEX ix_direcciones__owner ON gapto.direcciones (owner_user_id);
CREATE INDEX ix_documento_vinculos__cuenta ON gapto.documento_vinculos (cuenta_id);
CREATE INDEX ix_documento_vinculos__entidad ON gapto.documento_vinculos (entidad_id);
CREATE INDEX ix_documento_vinculos__hecho ON gapto.documento_vinculos (hecho_id);
CREATE INDEX ix_documento_vinculos__tercero ON gapto.documento_vinculos (tercero_id);
CREATE INDEX ix_efecto_atribuciones__actor ON gapto.efecto_atribuciones (actor_id);
CREATE INDEX ix_entidad_participaciones__actor ON gapto.entidad_participaciones (actor_id);
CREATE INDEX ix_entidad_relaciones__destino ON gapto.entidad_relaciones (entidad_destino_id);
CREATE INDEX ix_financiacion_condiciones_versiones__hecho_causa ON gapto.financiacion_condiciones_versiones (hecho_causa_id);
CREATE INDEX ix_financiacion_cuotas__financiacion ON gapto.financiacion_cuotas (financiacion_entidad_id);
CREATE INDEX ix_financiacion_cuotas__financiacion_condicion ON gapto.financiacion_cuotas (financiacion_entidad_id, condicion_version_id);
CREATE INDEX ix_financiacion_cuotas__prevision ON gapto.financiacion_cuotas (prevision_id);
CREATE INDEX ix_financiaciones__financiador ON gapto.financiaciones (financiador_actor_id);
CREATE INDEX ix_fuentes_importacion__documento_origen ON gapto.fuentes_importacion (documento_origen_id);
CREATE INDEX ix_fuentes_importacion__owner ON gapto.fuentes_importacion (owner_user_id);
CREATE INDEX ix_hecho_aportaciones_pago__actor ON gapto.hecho_aportaciones_pago (actor_id);
CREATE INDEX ix_hecho_aportaciones_pago__hecho ON gapto.hecho_aportaciones_pago (hecho_id);
CREATE INDEX ix_hecho_aportaciones_pago__movimiento ON gapto.hecho_aportaciones_pago (hecho_movimiento_tesoreria_id);
CREATE INDEX ix_hecho_efectos__categoria ON gapto.hecho_efectos (categoria_id);
CREATE INDEX ix_hecho_entidades__entidad ON gapto.hecho_entidades (entidad_id);
CREATE INDEX ix_hecho_etiquetas__etiqueta ON gapto.hecho_etiquetas (etiqueta_id);
CREATE INDEX ix_hecho_magnitudes__magnitud ON gapto.hecho_magnitudes (magnitud_id);
CREATE INDEX ix_hecho_movimientos_tesoreria__movimiento ON gapto.hecho_movimientos_tesoreria (movimiento_tesoreria_id);
CREATE INDEX ix_hecho_participantes__actor ON gapto.hecho_participantes (actor_id);
CREATE INDEX ix_hecho_relaciones__destino ON gapto.hecho_relaciones (hecho_destino_id);
CREATE INDEX ix_hecho_relaciones__origen ON gapto.hecho_relaciones (hecho_origen_id);
CREATE INDEX ix_hecho_terceros__tercero ON gapto.hecho_terceros (tercero_id);
CREATE INDEX ix_hechos_financieros__localidad ON gapto.hechos_financieros (localidad_id);
CREATE INDEX ix_hechos_financieros__tipo_hecho ON gapto.hechos_financieros (tipo_hecho_id);
CREATE INDEX ix_inversion_asignaciones_efecto__inversion ON gapto.inversion_asignaciones_efecto (inversion_entidad_id);
CREATE INDEX ix_inversion_valoraciones__inversion ON gapto.inversion_valoraciones (inversion_entidad_id);
CREATE INDEX ix_inversiones__padre ON gapto.inversiones (inversion_padre_entidad_id);
CREATE INDEX ix_inversiones__tercero_gestor ON gapto.inversiones (tercero_gestor_id);
CREATE INDEX ix_localidades__region ON gapto.localidades (region_id);
CREATE INDEX ix_mapeos_importacion__registro_origen ON gapto.mapeos_importacion (registro_origen_id);
CREATE INDEX ix_movimientos_tesoreria__cuenta ON gapto.movimientos_tesoreria (cuenta_id);
CREATE INDEX ix_movimientos_tesoreria__reversion ON gapto.movimientos_tesoreria (reversion_de_movimiento_id);
CREATE INDEX ix_plantillas_registro__categoria ON gapto.plantillas_registro (categoria_id);
CREATE INDEX ix_plantillas_registro__cuenta ON gapto.plantillas_registro (cuenta_default_id);
CREATE INDEX ix_plantillas_registro__entidad ON gapto.plantillas_registro (entidad_id);
CREATE INDEX ix_plantillas_registro__owner ON gapto.plantillas_registro (owner_user_id);
CREATE INDEX ix_plantillas_registro__tercero ON gapto.plantillas_registro (tercero_id);
CREATE INDEX ix_plantillas_registro__tipo_hecho ON gapto.plantillas_registro (tipo_hecho_id);
CREATE INDEX ix_preferencias_registro__categoria ON gapto.preferencias_registro (categoria_id);
CREATE INDEX ix_preferencias_registro__cuenta ON gapto.preferencias_registro (cuenta_default_id);
CREATE INDEX ix_preferencias_registro__entidad ON gapto.preferencias_registro (entidad_id);
CREATE INDEX ix_preferencias_registro__owner ON gapto.preferencias_registro (owner_user_id);
CREATE INDEX ix_preferencias_registro__tercero ON gapto.preferencias_registro (tercero_id);
CREATE INDEX ix_preferencias_registro__tipo_hecho ON gapto.preferencias_registro (tipo_hecho_id);
CREATE INDEX ix_presupuesto_linea_alcances__categoria ON gapto.presupuesto_linea_alcances (categoria_id);
CREATE INDEX ix_presupuesto_linea_alcances__entidad ON gapto.presupuesto_linea_alcances (entidad_id);
CREATE INDEX ix_presupuesto_linea_alcances__linea ON gapto.presupuesto_linea_alcances (presupuesto_linea_id);
CREATE INDEX ix_presupuesto_lineas__presupuesto ON gapto.presupuesto_lineas (presupuesto_id);
CREATE INDEX ix_presupuestos__cierre_origen ON gapto.presupuestos (generado_desde_cierre_id);
CREATE INDEX ix_presupuestos__owner ON gapto.presupuestos (owner_user_id);
CREATE INDEX ix_presupuestos__reemplaza ON gapto.presupuestos (reemplaza_presupuesto_id);
CREATE INDEX ix_prevision_hechos__hecho ON gapto.prevision_hechos (hecho_id);
CREATE INDEX ix_previsiones__categoria ON gapto.previsiones (categoria_id);
CREATE INDEX ix_previsiones__cuenta_entrada ON gapto.previsiones (cuenta_entrada_esperada_id);
CREATE INDEX ix_previsiones__cuenta_salida ON gapto.previsiones (cuenta_salida_esperada_id);
CREATE INDEX ix_previsiones__entidad ON gapto.previsiones (entidad_id);
CREATE INDEX ix_previsiones__owner ON gapto.previsiones (owner_user_id);
CREATE INDEX ix_previsiones__regla_version ON gapto.previsiones (regla_version_id);
CREATE INDEX ix_previsiones__tercero ON gapto.previsiones (tercero_id);
CREATE INDEX ix_previsiones__tipo_hecho ON gapto.previsiones (tipo_hecho_id);
CREATE INDEX ix_propiedad_servicios__servicio ON gapto.propiedad_servicios (servicio_entidad_id);
CREATE INDEX ix_propiedad_valoraciones__propiedad ON gapto.propiedad_valoraciones (propiedad_entidad_id);
CREATE INDEX ix_propiedades__direccion ON gapto.propiedades (direccion_id);
CREATE INDEX ix_regiones__pais ON gapto.regiones (pais_id);
CREATE INDEX ix_regiones__parent ON gapto.regiones (parent_region_id);
CREATE INDEX ix_regla_versiones__categoria ON gapto.regla_versiones (categoria_id);
CREATE INDEX ix_regla_versiones__cuenta_calculo ON gapto.regla_versiones (cuenta_calculo_id);
CREATE INDEX ix_regla_versiones__cuenta_entrada ON gapto.regla_versiones (cuenta_entrada_esperada_id);
CREATE INDEX ix_regla_versiones__cuenta_salida ON gapto.regla_versiones (cuenta_salida_esperada_id);
CREATE INDEX ix_regla_versiones__tercero ON gapto.regla_versiones (tercero_id);
CREATE INDEX ix_regla_versiones__tipo_hecho ON gapto.regla_versiones (tipo_hecho_id);
CREATE INDEX ix_reglas_financieras__entidad_origen ON gapto.reglas_financieras (entidad_origen_id);
CREATE INDEX ix_reglas_financieras__owner ON gapto.reglas_financieras (owner_user_id);
CREATE INDEX ix_tercero_afinidades__categoria ON gapto.tercero_afinidades (categoria_id);
CREATE INDEX ix_tercero_clasificaciones__clasificacion ON gapto.tercero_clasificaciones (clasificacion_id);
CREATE INDEX ix_tercero_direcciones__direccion ON gapto.tercero_direcciones (direccion_id);
CREATE INDEX ix_terceros__owner ON gapto.terceros (owner_user_id);
CREATE INDEX ix_terceros__pais_fiscal ON gapto.terceros (pais_fiscal_id);
-- Composites de acceso documentados en F03-00-I / Índices mínimos
CREATE INDEX ix_hechos_financieros__owner_fecha ON gapto.hechos_financieros (owner_user_id, fecha_hecho DESC, id);
CREATE INDEX ix_movimientos_tesoreria__cuenta_fecha ON gapto.movimientos_tesoreria (cuenta_id, fecha_movimiento);
CREATE INDEX ix_previsiones__owner_estado_fecha ON gapto.previsiones (owner_user_id, estado, fecha_esperada_desde);
CREATE INDEX ix_presupuestos__owner_periodo_estado ON gapto.presupuestos (owner_user_id, periodo_desde, periodo_hasta, estado);
CREATE INDEX ix_presupuesto_lineas__presupuesto_tipo_prioridad ON gapto.presupuesto_lineas (presupuesto_id, tipo_linea, prioridad_consumo);
CREATE INDEX ix_cierre_saldos_cuenta__cierre_cuenta ON gapto.cierre_saldos_cuenta (cierre_id, cuenta_id);
CREATE INDEX ix_cierre_presupuesto_lineas__cierre_linea ON gapto.cierre_presupuesto_lineas (cierre_id, presupuesto_linea_id);
CREATE INDEX ix_cierre_posiciones_entidad__cierre_entidad ON gapto.cierre_posiciones_entidad (cierre_id, entidad_id);
CREATE INDEX ix_cierre_metricas__cierre_metrica ON gapto.cierre_metricas (cierre_id, metrica_id);
CREATE INDEX ix_auditoria__owner_tabla_registro_fecha ON gapto.auditoria (owner_user_id, tabla, registro_id, created_at);
CREATE INDEX ix_auditoria__request_id ON gapto.auditoria (request_id) WHERE request_id IS NOT NULL;
CREATE INDEX ix_fuentes_importacion__owner_fecha_estado ON gapto.fuentes_importacion (owner_user_id, created_at, estado);
CREATE INDEX ix_registros_origen_importacion__fuente ON gapto.registros_origen_importacion (fuente_importacion_id);
CREATE INDEX ix_mapeos_importacion__destino ON gapto.mapeos_importacion (tabla_destino, registro_destino_id);
CREATE INDEX ix_propiedad_valoraciones__propiedad_fecha ON gapto.propiedad_valoraciones (propiedad_entidad_id, fecha_valoracion);
CREATE INDEX ix_contratos__propiedad_fecha_inicio ON gapto.contratos (propiedad_entidad_id, fecha_inicio);
CREATE INDEX ix_financiacion_cuotas__financiacion_vencimiento ON gapto.financiacion_cuotas (financiacion_entidad_id, fecha_vencimiento);
CREATE INDEX ix_inversion_valoraciones__inversion_fecha ON gapto.inversion_valoraciones (inversion_entidad_id, fecha_valoracion);
CREATE INDEX ix_terceros__owner_nombre ON gapto.terceros (owner_user_id, nombre);

-- Búsqueda humana (pg_trgm GIN) según F03-00-I
CREATE INDEX ix_terceros__nombre_trgm ON gapto.terceros USING gin (nombre gapto_ext.gin_trgm_ops);
CREATE INDEX ix_terceros__nombre_legal_trgm ON gapto.terceros USING gin (nombre_legal gapto_ext.gin_trgm_ops);
CREATE INDEX ix_entidades__nombre_trgm ON gapto.entidades USING gin (nombre gapto_ext.gin_trgm_ops);
CREATE INDEX ix_hechos_financieros__concepto_trgm ON gapto.hechos_financieros USING gin (concepto gapto_ext.gin_trgm_ops);
CREATE INDEX ix_documentos__titulo_trgm ON gapto.documentos USING gin (titulo gapto_ext.gin_trgm_ops);
CREATE INDEX ix_documentos__nombre_archivo_trgm ON gapto.documentos USING gin (nombre_archivo_original gapto_ext.gin_trgm_ops);

RESET ROLE;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_index i ON i.indexrelid=c.oid
     WHERE n.nspname='gapto' AND c.relkind='i' AND NOT i.indisprimary
       AND NOT i.indisunique
       AND NOT EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid=c.oid AND con.contype='x');
    IF v_count <> 134 THEN
        RAISE EXCEPTION 'POSTCHECK: esperados 134 indices B11; encontrados=%', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

COMMIT;
