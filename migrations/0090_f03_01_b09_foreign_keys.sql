-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0090_f03_01_b09_foreign_keys.sql
-- Ruta: migrations/0090_f03_01_b09_foreign_keys.sql
-- Descripción: Materializa las Foreign Keys sobre las 79 tablas ya
--              existentes. Política general: RESTRICT/NO ACTION en
--              relaciones financieras/históricas; CASCADE únicamente
--              en extensiones 1:0..1 sin identidad propia, subtipos
--              PK=FK de entidades/terceros y bridges de configuración
--              estrictamente dependientes (F03-00-E1/E2). Ningún FK
--              usa ON UPDATE CASCADE (identidades UUID inmutables).
--              Como las tablas ya existen de bloques anteriores, el
--              orden de ALTER TABLE no genera dependencias cíclicas
--              de creación (a diferencia de un CREATE TABLE inline).
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_fk_count integer;
BEGIN
    SELECT count(*) INTO v_fk_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'f';

    IF v_fk_count <> 0 THEN
        RAISE EXCEPTION 'F03-01-B09 PRECHECK: ya existen % FK; se esperaba 0', v_fk_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 2..4 extensiones/config directa de usuario (CASCADE, sin identidad propia)
ALTER TABLE gapto.configuracion_usuario ADD CONSTRAINT fk_configuracion_usuario__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE CASCADE;
ALTER TABLE gapto.preferencias_ui ADD CONSTRAINT fk_preferencias_ui__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE CASCADE;
ALTER TABLE gapto.acciones_rapidas ADD CONSTRAINT fk_acciones_rapidas__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE CASCADE;
ALTER TABLE gapto.acciones_rapidas ADD CONSTRAINT fk_acciones_rapidas__plantilla FOREIGN KEY (plantilla_registro_id) REFERENCES gapto.plantillas_registro(id) ON DELETE RESTRICT;

-- 6..8 geografía (RESTRICT)
ALTER TABLE gapto.regiones ADD CONSTRAINT fk_regiones__pais FOREIGN KEY (pais_id) REFERENCES gapto.paises(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regiones ADD CONSTRAINT fk_regiones__parent FOREIGN KEY (parent_region_id) REFERENCES gapto.regiones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.localidades ADD CONSTRAINT fk_localidades__region FOREIGN KEY (region_id) REFERENCES gapto.regiones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.direcciones ADD CONSTRAINT fk_direcciones__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.direcciones ADD CONSTRAINT fk_direcciones__localidad FOREIGN KEY (localidad_id) REFERENCES gapto.localidades(id) ON DELETE RESTRICT;

-- 9..16 terceros y sus bridges (bridges CASCADE desde tercero, referencias a catálogos RESTRICT)
ALTER TABLE gapto.terceros ADD CONSTRAINT fk_terceros__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.terceros ADD CONSTRAINT fk_terceros__pais_fiscal FOREIGN KEY (pais_fiscal_id) REFERENCES gapto.paises(id) ON DELETE RESTRICT;
ALTER TABLE gapto.tercero_direcciones ADD CONSTRAINT fk_tercero_direcciones__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE CASCADE;
ALTER TABLE gapto.tercero_direcciones ADD CONSTRAINT fk_tercero_direcciones__direccion FOREIGN KEY (direccion_id) REFERENCES gapto.direcciones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.actores_financieros ADD CONSTRAINT fk_actores_financieros__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.actores_financieros ADD CONSTRAINT fk_actores_financieros__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.tercero_roles ADD CONSTRAINT fk_tercero_roles__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE CASCADE;
ALTER TABLE gapto.clasificaciones_tercero ADD CONSTRAINT fk_clasificaciones_tercero__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.clasificaciones_tercero ADD CONSTRAINT fk_clasificaciones_tercero__parent FOREIGN KEY (parent_id) REFERENCES gapto.clasificaciones_tercero(id) ON DELETE RESTRICT;
ALTER TABLE gapto.tercero_clasificaciones ADD CONSTRAINT fk_tercero_clasificaciones__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE CASCADE;
ALTER TABLE gapto.tercero_clasificaciones ADD CONSTRAINT fk_tercero_clasificaciones__clasificacion FOREIGN KEY (clasificacion_id) REFERENCES gapto.clasificaciones_tercero(id) ON DELETE RESTRICT;
ALTER TABLE gapto.tercero_afinidades ADD CONSTRAINT fk_tercero_afinidades__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE CASCADE;
ALTER TABLE gapto.tercero_afinidades ADD CONSTRAINT fk_tercero_afinidades__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;

-- 18..21 magnitudes, categorías financieras y preferencias/plantillas de registro
ALTER TABLE gapto.categorias_financieras ADD CONSTRAINT fk_categorias_financieras__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.categorias_financieras ADD CONSTRAINT fk_categorias_financieras__parent FOREIGN KEY (parent_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.magnitudes ADD CONSTRAINT fk_magnitudes__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.categoria_magnitudes ADD CONSTRAINT fk_categoria_magnitudes__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE CASCADE;
ALTER TABLE gapto.categoria_magnitudes ADD CONSTRAINT fk_categoria_magnitudes__magnitud FOREIGN KEY (magnitud_id) REFERENCES gapto.magnitudes(id) ON DELETE CASCADE;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE CASCADE;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__tipo_hecho FOREIGN KEY (tipo_hecho_id) REFERENCES gapto.tipos_hecho(id) ON DELETE RESTRICT;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.preferencias_registro ADD CONSTRAINT fk_preferencias_registro__cuenta FOREIGN KEY (cuenta_default_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE CASCADE;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__tipo_hecho FOREIGN KEY (tipo_hecho_id) REFERENCES gapto.tipos_hecho(id) ON DELETE RESTRICT;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.plantillas_registro ADD CONSTRAINT fk_plantillas_registro__cuenta FOREIGN KEY (cuenta_default_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;

-- 22..28 cuentas y entidades
ALTER TABLE gapto.cuentas ADD CONSTRAINT fk_cuentas__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cuentas ADD CONSTRAINT fk_cuentas__tercero_gestor FOREIGN KEY (tercero_gestor_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cuenta_capacidades ADD CONSTRAINT fk_cuenta_capacidades__cuenta FOREIGN KEY (cuenta_id) REFERENCES gapto.cuentas(id) ON DELETE CASCADE;
ALTER TABLE gapto.cuenta_participaciones ADD CONSTRAINT fk_cuenta_participaciones__cuenta FOREIGN KEY (cuenta_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cuenta_participaciones ADD CONSTRAINT fk_cuenta_participaciones__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.entidades ADD CONSTRAINT fk_entidades__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.entidad_participaciones ADD CONSTRAINT fk_entidad_participaciones__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.entidad_participaciones ADD CONSTRAINT fk_entidad_participaciones__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.entidad_relaciones ADD CONSTRAINT fk_entidad_relaciones__origen FOREIGN KEY (entidad_origen_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.entidad_relaciones ADD CONSTRAINT fk_entidad_relaciones__destino FOREIGN KEY (entidad_destino_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.contextos ADD CONSTRAINT fk_contextos__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;

-- 29..32 reglas y previsiones
ALTER TABLE gapto.reglas_financieras ADD CONSTRAINT fk_reglas_financieras__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.reglas_financieras ADD CONSTRAINT fk_reglas_financieras__entidad_origen FOREIGN KEY (entidad_origen_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__regla FOREIGN KEY (regla_id) REFERENCES gapto.reglas_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__tipo_hecho FOREIGN KEY (tipo_hecho_id) REFERENCES gapto.tipos_hecho(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__cuenta_salida FOREIGN KEY (cuenta_salida_esperada_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__cuenta_entrada FOREIGN KEY (cuenta_entrada_esperada_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT fk_regla_versiones__cuenta_calculo FOREIGN KEY (cuenta_calculo_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.regla_excepciones ADD CONSTRAINT fk_regla_excepciones__regla FOREIGN KEY (regla_id) REFERENCES gapto.reglas_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__regla_version FOREIGN KEY (regla_version_id) REFERENCES gapto.regla_versiones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__tipo_hecho FOREIGN KEY (tipo_hecho_id) REFERENCES gapto.tipos_hecho(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__cuenta_salida FOREIGN KEY (cuenta_salida_esperada_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.previsiones ADD CONSTRAINT fk_previsiones__cuenta_entrada FOREIGN KEY (cuenta_entrada_esperada_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;

-- 33..45 núcleo de hechos y tesorería
ALTER TABLE gapto.hechos_financieros ADD CONSTRAINT fk_hechos_financieros__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hechos_financieros ADD CONSTRAINT fk_hechos_financieros__tipo_hecho FOREIGN KEY (tipo_hecho_id) REFERENCES gapto.tipos_hecho(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hechos_financieros ADD CONSTRAINT fk_hechos_financieros__localidad FOREIGN KEY (localidad_id) REFERENCES gapto.localidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_efectos ADD CONSTRAINT fk_hecho_efectos__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_efectos ADD CONSTRAINT fk_hecho_efectos__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.efecto_atribuciones ADD CONSTRAINT fk_efecto_atribuciones__efecto FOREIGN KEY (efecto_id) REFERENCES gapto.hecho_efectos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.efecto_atribuciones ADD CONSTRAINT fk_efecto_atribuciones__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_terceros ADD CONSTRAINT fk_hecho_terceros__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_terceros ADD CONSTRAINT fk_hecho_terceros__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_entidades ADD CONSTRAINT fk_hecho_entidades__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_entidades ADD CONSTRAINT fk_hecho_entidades__hecho_efecto FOREIGN KEY (hecho_id, efecto_id) REFERENCES gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_entidades ADD CONSTRAINT fk_hecho_entidades__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_participantes ADD CONSTRAINT fk_hecho_participantes__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_participantes ADD CONSTRAINT fk_hecho_participantes__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_aportaciones_pago ADD CONSTRAINT fk_hecho_aportaciones_pago__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_aportaciones_pago ADD CONSTRAINT fk_hecho_aportaciones_pago__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.movimientos_tesoreria ADD CONSTRAINT fk_movimientos_tesoreria__cuenta FOREIGN KEY (cuenta_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.movimientos_tesoreria ADD CONSTRAINT fk_movimientos_tesoreria__reversion FOREIGN KEY (reversion_de_movimiento_id) REFERENCES gapto.movimientos_tesoreria(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_aportaciones_pago ADD CONSTRAINT fk_hecho_aportaciones_pago__movimiento FOREIGN KEY (hecho_movimiento_tesoreria_id) REFERENCES gapto.hecho_movimientos_tesoreria(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_movimientos_tesoreria ADD CONSTRAINT fk_hecho_movimientos_tesoreria__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_movimientos_tesoreria ADD CONSTRAINT fk_hecho_movimientos_tesoreria__movimiento FOREIGN KEY (movimiento_tesoreria_id) REFERENCES gapto.movimientos_tesoreria(id) ON DELETE RESTRICT;
ALTER TABLE gapto.transferencias ADD CONSTRAINT fk_transferencias__salida FOREIGN KEY (movimiento_salida_id) REFERENCES gapto.movimientos_tesoreria(id) ON DELETE RESTRICT;
ALTER TABLE gapto.transferencias ADD CONSTRAINT fk_transferencias__entrada FOREIGN KEY (movimiento_entrada_id) REFERENCES gapto.movimientos_tesoreria(id) ON DELETE RESTRICT;
ALTER TABLE gapto.prevision_hechos ADD CONSTRAINT fk_prevision_hechos__prevision FOREIGN KEY (prevision_id) REFERENCES gapto.previsiones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.prevision_hechos ADD CONSTRAINT fk_prevision_hechos__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_magnitudes ADD CONSTRAINT fk_hecho_magnitudes__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_magnitudes ADD CONSTRAINT fk_hecho_magnitudes__magnitud FOREIGN KEY (magnitud_id) REFERENCES gapto.magnitudes(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_relaciones ADD CONSTRAINT fk_hecho_relaciones__origen FOREIGN KEY (hecho_origen_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_relaciones ADD CONSTRAINT fk_hecho_relaciones__destino FOREIGN KEY (hecho_destino_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;

-- 46..59 dominios especializados (subtipos CASCADE PK=FK; resto RESTRICT)
ALTER TABLE gapto.derechos_obligaciones_financieras ADD CONSTRAINT fk_derechos_obligaciones_financieras__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.derechos_obligaciones_financieras ADD CONSTRAINT fk_derechos_obligaciones_financieras__contraparte FOREIGN KEY (contraparte_actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.propiedades ADD CONSTRAINT fk_propiedades__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.propiedades ADD CONSTRAINT fk_propiedades__direccion FOREIGN KEY (direccion_id) REFERENCES gapto.direcciones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.propiedad_valoraciones ADD CONSTRAINT fk_propiedad_valoraciones__propiedad FOREIGN KEY (propiedad_entidad_id) REFERENCES gapto.propiedades(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contratos ADD CONSTRAINT fk_contratos__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.contratos ADD CONSTRAINT fk_contratos__propiedad FOREIGN KEY (propiedad_entidad_id) REFERENCES gapto.propiedades(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contratos ADD CONSTRAINT fk_contratos__regla_renta FOREIGN KEY (regla_renta_id) REFERENCES gapto.reglas_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.contrato_participantes ADD CONSTRAINT fk_contrato_participantes__contrato FOREIGN KEY (contrato_entidad_id) REFERENCES gapto.contratos(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contrato_participantes ADD CONSTRAINT fk_contrato_participantes__actor FOREIGN KEY (actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.servicios ADD CONSTRAINT fk_servicios__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.propiedad_servicios ADD CONSTRAINT fk_propiedad_servicios__servicio FOREIGN KEY (servicio_entidad_id) REFERENCES gapto.servicios(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.propiedad_servicios ADD CONSTRAINT fk_propiedad_servicios__propiedad FOREIGN KEY (propiedad_entidad_id) REFERENCES gapto.propiedades(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT fk_contrato_servicios__contrato FOREIGN KEY (contrato_entidad_id) REFERENCES gapto.contratos(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT fk_contrato_servicios__servicio FOREIGN KEY (servicio_entidad_id) REFERENCES gapto.servicios(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT fk_contrato_servicios__actor_repercusion FOREIGN KEY (actor_repercusion_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiaciones ADD CONSTRAINT fk_financiaciones__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.financiaciones ADD CONSTRAINT fk_financiaciones__financiador FOREIGN KEY (financiador_actor_id) REFERENCES gapto.actores_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiacion_condiciones_versiones ADD CONSTRAINT fk_financiacion_condiciones_versiones__financiacion FOREIGN KEY (financiacion_entidad_id) REFERENCES gapto.financiaciones(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiacion_condiciones_versiones ADD CONSTRAINT fk_financiacion_condiciones_versiones__hecho_causa FOREIGN KEY (hecho_causa_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiacion_cuotas ADD CONSTRAINT fk_financiacion_cuotas__financiacion FOREIGN KEY (financiacion_entidad_id) REFERENCES gapto.financiaciones(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiacion_cuotas ADD CONSTRAINT fk_financiacion_cuotas__financiacion_condicion FOREIGN KEY (financiacion_entidad_id, condicion_version_id) REFERENCES gapto.financiacion_condiciones_versiones(financiacion_entidad_id, id) ON DELETE RESTRICT;
ALTER TABLE gapto.financiacion_cuotas ADD CONSTRAINT fk_financiacion_cuotas__prevision FOREIGN KEY (prevision_id) REFERENCES gapto.previsiones(id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversiones ADD CONSTRAINT fk_inversiones__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE CASCADE;
ALTER TABLE gapto.inversiones ADD CONSTRAINT fk_inversiones__padre FOREIGN KEY (inversion_padre_entidad_id) REFERENCES gapto.inversiones(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversiones ADD CONSTRAINT fk_inversiones__tercero_gestor FOREIGN KEY (tercero_gestor_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversion_objetivos_versiones ADD CONSTRAINT fk_inversion_objetivos_versiones__inversion FOREIGN KEY (inversion_entidad_id) REFERENCES gapto.inversiones(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversion_valoraciones ADD CONSTRAINT fk_inversion_valoraciones__inversion FOREIGN KEY (inversion_entidad_id) REFERENCES gapto.inversiones(entidad_id) ON DELETE RESTRICT;

-- 60..67 presupuestos, cierres y analítica
ALTER TABLE gapto.presupuestos ADD CONSTRAINT fk_presupuestos__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuestos ADD CONSTRAINT fk_presupuestos__reemplaza FOREIGN KEY (reemplaza_presupuesto_id) REFERENCES gapto.presupuestos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuestos ADD CONSTRAINT fk_presupuestos__cierre_origen FOREIGN KEY (generado_desde_cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuesto_lineas ADD CONSTRAINT fk_presupuesto_lineas__presupuesto FOREIGN KEY (presupuesto_id) REFERENCES gapto.presupuestos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierres_mensuales ADD CONSTRAINT fk_cierres_mensuales__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierres_mensuales ADD CONSTRAINT fk_cierres_mensuales__reemplaza FOREIGN KEY (reemplaza_cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_saldos_cuenta ADD CONSTRAINT fk_cierre_saldos_cuenta__cierre FOREIGN KEY (cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_saldos_cuenta ADD CONSTRAINT fk_cierre_saldos_cuenta__cuenta FOREIGN KEY (cuenta_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_presupuesto_lineas ADD CONSTRAINT fk_cierre_presupuesto_lineas__cierre FOREIGN KEY (cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_presupuesto_lineas ADD CONSTRAINT fk_cierre_presupuesto_lineas__linea FOREIGN KEY (presupuesto_linea_id) REFERENCES gapto.presupuesto_lineas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_metricas ADD CONSTRAINT fk_cierre_metricas__cierre FOREIGN KEY (cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_metricas ADD CONSTRAINT fk_cierre_metricas__metrica FOREIGN KEY (metrica_id) REFERENCES gapto.metricas_definicion(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_posiciones_entidad ADD CONSTRAINT fk_cierre_posiciones_entidad__cierre FOREIGN KEY (cierre_id) REFERENCES gapto.cierres_mensuales(id) ON DELETE RESTRICT;
ALTER TABLE gapto.cierre_posiciones_entidad ADD CONSTRAINT fk_cierre_posiciones_entidad__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;

-- 68..79 documentos, etiquetas, auditoría, importación y tablas finales
ALTER TABLE gapto.documentos ADD CONSTRAINT fk_documentos__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.documento_vinculos ADD CONSTRAINT fk_documento_vinculos__documento FOREIGN KEY (documento_id) REFERENCES gapto.documentos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.documento_vinculos ADD CONSTRAINT fk_documento_vinculos__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.documento_vinculos ADD CONSTRAINT fk_documento_vinculos__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.documento_vinculos ADD CONSTRAINT fk_documento_vinculos__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.documento_vinculos ADD CONSTRAINT fk_documento_vinculos__cuenta FOREIGN KEY (cuenta_id) REFERENCES gapto.cuentas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.etiquetas ADD CONSTRAINT fk_etiquetas__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_etiquetas ADD CONSTRAINT fk_hecho_etiquetas__hecho FOREIGN KEY (hecho_id) REFERENCES gapto.hechos_financieros(id) ON DELETE RESTRICT;
ALTER TABLE gapto.hecho_etiquetas ADD CONSTRAINT fk_hecho_etiquetas__etiqueta FOREIGN KEY (etiqueta_id) REFERENCES gapto.etiquetas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.auditoria ADD CONSTRAINT fk_auditoria__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.auditoria ADD CONSTRAINT fk_auditoria__actor FOREIGN KEY (actor_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversion_asignaciones_efecto ADD CONSTRAINT fk_inversion_asignaciones_efecto__efecto FOREIGN KEY (efecto_inversion_id) REFERENCES gapto.hecho_efectos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.inversion_asignaciones_efecto ADD CONSTRAINT fk_inversion_asignaciones_efecto__inversion FOREIGN KEY (inversion_entidad_id) REFERENCES gapto.inversiones(entidad_id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuesto_linea_alcances ADD CONSTRAINT fk_presupuesto_linea_alcances__linea FOREIGN KEY (presupuesto_linea_id) REFERENCES gapto.presupuesto_lineas(id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuesto_linea_alcances ADD CONSTRAINT fk_presupuesto_linea_alcances__categoria FOREIGN KEY (categoria_id) REFERENCES gapto.categorias_financieras(id) ON DELETE RESTRICT;
ALTER TABLE gapto.presupuesto_linea_alcances ADD CONSTRAINT fk_presupuesto_linea_alcances__entidad FOREIGN KEY (entidad_id) REFERENCES gapto.entidades(id) ON DELETE RESTRICT;
ALTER TABLE gapto.fuentes_importacion ADD CONSTRAINT fk_fuentes_importacion__owner FOREIGN KEY (owner_user_id) REFERENCES gapto.usuarios(id) ON DELETE RESTRICT;
ALTER TABLE gapto.fuentes_importacion ADD CONSTRAINT fk_fuentes_importacion__documento_origen FOREIGN KEY (documento_origen_id) REFERENCES gapto.documentos(id) ON DELETE RESTRICT;
ALTER TABLE gapto.registros_origen_importacion ADD CONSTRAINT fk_registros_origen_importacion__fuente FOREIGN KEY (fuente_importacion_id) REFERENCES gapto.fuentes_importacion(id) ON DELETE RESTRICT;
ALTER TABLE gapto.mapeos_importacion ADD CONSTRAINT fk_mapeos_importacion__registro_origen FOREIGN KEY (registro_origen_id) REFERENCES gapto.registros_origen_importacion(id) ON DELETE RESTRICT;
ALTER TABLE gapto.tercero_personas ADD CONSTRAINT fk_tercero_personas__tercero FOREIGN KEY (tercero_id) REFERENCES gapto.terceros(id) ON DELETE CASCADE;
ALTER TABLE gapto.contrato_revision_renta_versiones ADD CONSTRAINT fk_contrato_revision_renta_versiones__contrato FOREIGN KEY (contrato_entidad_id) REFERENCES gapto.contratos(entidad_id) ON DELETE RESTRICT;

RESET ROLE;

DO $gapto$
DECLARE
    v_fk_count integer;
    v_cascade_count integer;
BEGIN
    SELECT count(*) INTO v_fk_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'f';

    SELECT count(*) INTO v_cascade_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'f' AND con.confdeltype = 'c';

    IF v_fk_count <> 161 THEN
        RAISE EXCEPTION 'F03-01-B09 POSTCHECK: esperadas 161 FK; encontradas=%', v_fk_count;
    END IF;

    IF v_cascade_count <> 20 THEN
        RAISE EXCEPTION 'F03-01-B09 POSTCHECK: esperadas 20 FK ON DELETE CASCADE; encontradas=%', v_cascade_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
