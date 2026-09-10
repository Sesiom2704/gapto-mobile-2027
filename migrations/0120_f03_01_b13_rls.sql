-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0120_f03_01_b13_rls.sql
-- Ruta: migrations/0120_f03_01_b13_rls.sql
-- Descripcion: ENABLE+FORCE RLS y policies de aislamiento tenant sobre las 74 tablas
--   no-catalogo. USING valida un solo camino de ownership; WITH CHECK valida TODOS
--   los FK owner-scoped de la fila (principio "Forma A": cualquier vinculo cross-
--   entidad se resuelve modelando dentro del propio tenant, nunca referenciando
--   directamente actores/terceros/entidades de otro owner). Los 5 catalogos
--   globales (paises, regiones, localidades, tipos_hecho, metricas_definicion)
--   quedan sin RLS, protegidos por GRANT en F03-01-B14. Las 7 tablas append-only
--   reciben solo policies de SELECT+INSERT; UPDATE/DELETE quedan denegados por
--   ausencia de policy + guard trigger (F03-01-B14).
-- Version: 0.1.1
-- Nota v0.1.1 (excepcion pre-freeze F03-GATE-01): se anaden las lineas
--   GAPTO MOBILE 2027, Ruta y Version, que el Working Method exige en todo
--   artefacto propio y este fichero nunca llego a declarar. El SQL ejecutable
--   es byte a byte el original: no se ha tocado ni una sentencia. NO se
--   reaplica sobre las bases existentes.
-- ============================================================

SET ROLE gapto_owner;

ALTER TABLE gapto.acciones_rapidas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.acciones_rapidas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.acciones_rapidas
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND EXISTS (SELECT 1 FROM gapto.plantillas_registro t1 WHERE t1.id = acciones_rapidas.plantilla_registro_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.actores_financieros ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.actores_financieros FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.actores_financieros
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = actores_financieros.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.auditoria ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.auditoria FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.auditoria FOR SELECT USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);
CREATE POLICY tenant_insert ON gapto.auditoria FOR INSERT WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.categoria_magnitudes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.categoria_magnitudes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.categoria_magnitudes
    USING (EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = categoria_magnitudes.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = categoria_magnitudes.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.magnitudes t1 WHERE t1.id = categoria_magnitudes.magnitud_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.categorias_financieras ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.categorias_financieras
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (parent_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = categorias_financieras.parent_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.cierre_metricas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierre_metricas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.cierre_metricas FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_metricas.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.cierre_metricas FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_metricas.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.cierre_posiciones_entidad ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierre_posiciones_entidad FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.cierre_posiciones_entidad FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_posiciones_entidad.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.cierre_posiciones_entidad FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_posiciones_entidad.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = cierre_posiciones_entidad.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.cierre_presupuesto_lineas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierre_presupuesto_lineas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.cierre_presupuesto_lineas FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_presupuesto_lineas.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.cierre_presupuesto_lineas FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_presupuesto_lineas.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.presupuesto_lineas m1 JOIN gapto.presupuestos t1 ON t1.id = m1.presupuesto_id WHERE m1.id = cierre_presupuesto_lineas.presupuesto_linea_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.cierre_saldos_cuenta ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierre_saldos_cuenta FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.cierre_saldos_cuenta FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_saldos_cuenta.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.cierre_saldos_cuenta FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierre_saldos_cuenta.cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = cierre_saldos_cuenta.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.cierres_mensuales ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cierres_mensuales FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.cierres_mensuales
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (reemplaza_cierre_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = cierres_mensuales.reemplaza_cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.clasificaciones_tercero ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.clasificaciones_tercero FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.clasificaciones_tercero
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (parent_id IS NULL OR EXISTS (SELECT 1 FROM gapto.clasificaciones_tercero t1 WHERE t1.id = clasificaciones_tercero.parent_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.configuracion_usuario ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.configuracion_usuario FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.configuracion_usuario
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.contextos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.contextos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.contextos
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = contextos.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = contextos.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.contrato_participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.contrato_participantes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.contrato_participantes
    USING (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_participantes.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_participantes.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = contrato_participantes.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.contrato_revision_renta_versiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.contrato_revision_renta_versiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.contrato_revision_renta_versiones
    USING (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_revision_renta_versiones.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_revision_renta_versiones.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.contrato_servicios ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.contrato_servicios FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.contrato_servicios
    USING (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_servicios.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.contratos m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_servicios.contrato_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.servicios m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contrato_servicios.servicio_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (actor_repercusion_id IS NULL OR EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = contrato_servicios.actor_repercusion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.contratos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.contratos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.contratos
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = contratos.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = contratos.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.propiedades m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = contratos.propiedad_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (regla_renta_id IS NULL OR EXISTS (SELECT 1 FROM gapto.reglas_financieras t1 WHERE t1.id = contratos.regla_renta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.cuenta_capacidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cuenta_capacidades FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.cuenta_capacidades
    USING (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = cuenta_capacidades.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = cuenta_capacidades.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.cuenta_participaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cuenta_participaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.cuenta_participaciones
    USING (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = cuenta_participaciones.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = cuenta_participaciones.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = cuenta_participaciones.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.cuentas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.cuentas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.cuentas
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (tercero_gestor_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = cuentas.tercero_gestor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.derechos_obligaciones_financieras ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.derechos_obligaciones_financieras FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.derechos_obligaciones_financieras
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = derechos_obligaciones_financieras.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = derechos_obligaciones_financieras.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (contraparte_actor_id IS NULL OR EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = derechos_obligaciones_financieras.contraparte_actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.direcciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.direcciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.direcciones
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

-- DEPENDENCIA DE SEGURIDAD: el WITH CHECK de abajo asume que el CHECK de fila
-- de B07 ("exactamente uno de hecho_id/entidad_id/tercero_id/cuenta_id informado")
-- sigue vigente. Si esa constraint se relaja o elimina en el futuro, esta policy
-- deja de garantizar por si sola la ausencia de referencias cross-tenant y debe
-- revisarse junto con ese cambio.
ALTER TABLE gapto.documento_vinculos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.documento_vinculos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.documento_vinculos
    USING (EXISTS (SELECT 1 FROM gapto.documentos t1 WHERE t1.id = documento_vinculos.documento_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.documentos t1 WHERE t1.id = documento_vinculos.documento_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (hecho_id IS NULL OR EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = documento_vinculos.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (entidad_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = documento_vinculos.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = documento_vinculos.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = documento_vinculos.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.documentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.documentos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.documentos
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.efecto_atribuciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.efecto_atribuciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.efecto_atribuciones
    USING (EXISTS (SELECT 1 FROM gapto.hecho_efectos m1 JOIN gapto.hechos_financieros t1 ON t1.id = m1.hecho_id WHERE m1.id = efecto_atribuciones.efecto_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hecho_efectos m1 JOIN gapto.hechos_financieros t1 ON t1.id = m1.hecho_id WHERE m1.id = efecto_atribuciones.efecto_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = efecto_atribuciones.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.entidad_participaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.entidad_participaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.entidad_participaciones
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = entidad_participaciones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = entidad_participaciones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = entidad_participaciones.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.entidad_relaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.entidad_relaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.entidad_relaciones
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = entidad_relaciones.entidad_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = entidad_relaciones.entidad_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = entidad_relaciones.entidad_destino_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.entidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.entidades FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.entidades
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.etiquetas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.etiquetas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.etiquetas
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.financiacion_condiciones_versiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.financiacion_condiciones_versiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.financiacion_condiciones_versiones
    USING (EXISTS (SELECT 1 FROM gapto.financiaciones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = financiacion_condiciones_versiones.financiacion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.financiaciones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = financiacion_condiciones_versiones.financiacion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (hecho_causa_id IS NULL OR EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = financiacion_condiciones_versiones.hecho_causa_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.financiacion_cuotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.financiacion_cuotas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.financiacion_cuotas
    USING (EXISTS (SELECT 1 FROM gapto.financiaciones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = financiacion_cuotas.financiacion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.financiaciones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = financiacion_cuotas.financiacion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (prevision_id IS NULL OR EXISTS (SELECT 1 FROM gapto.previsiones t1 WHERE t1.id = financiacion_cuotas.prevision_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.financiaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.financiaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.financiaciones
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = financiaciones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = financiaciones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (financiador_actor_id IS NULL OR EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = financiaciones.financiador_actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.fuentes_importacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.fuentes_importacion FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.fuentes_importacion
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (documento_origen_id IS NULL OR EXISTS (SELECT 1 FROM gapto.documentos t1 WHERE t1.id = fuentes_importacion.documento_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.hecho_aportaciones_pago ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_aportaciones_pago FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_aportaciones_pago
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_aportaciones_pago.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_aportaciones_pago.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (actor_id IS NULL OR EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = hecho_aportaciones_pago.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (hecho_movimiento_tesoreria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria m1 JOIN gapto.hechos_financieros t1 ON t1.id = m1.hecho_id WHERE m1.id = hecho_aportaciones_pago.hecho_movimiento_tesoreria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.hecho_efectos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_efectos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_efectos
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_efectos.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_efectos.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = hecho_efectos.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.hecho_entidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_entidades FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_entidades
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_entidades.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_entidades.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = hecho_entidades.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_etiquetas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_etiquetas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_etiquetas
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_etiquetas.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_etiquetas.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.etiquetas t1 WHERE t1.id = hecho_etiquetas.etiqueta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_magnitudes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_magnitudes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_magnitudes
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_magnitudes.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_magnitudes.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.magnitudes t1 WHERE t1.id = hecho_magnitudes.magnitud_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_movimientos_tesoreria ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_movimientos_tesoreria FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_movimientos_tesoreria
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_movimientos_tesoreria.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_movimientos_tesoreria.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria m1 JOIN gapto.cuentas t1 ON t1.id = m1.cuenta_id WHERE m1.id = hecho_movimientos_tesoreria.movimiento_tesoreria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_participantes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_participantes
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_participantes.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_participantes.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.actores_financieros t1 WHERE t1.id = hecho_participantes.actor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_relaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_relaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_relaciones
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_relaciones.hecho_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_relaciones.hecho_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_relaciones.hecho_destino_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hecho_terceros ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hecho_terceros FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hecho_terceros
    USING (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_terceros.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = hecho_terceros.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = hecho_terceros.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.hechos_financieros ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.hechos_financieros FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.hechos_financieros
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.inversion_asignaciones_efecto ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.inversion_asignaciones_efecto FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.inversion_asignaciones_efecto
    USING (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_asignaciones_efecto.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_asignaciones_efecto.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.hecho_efectos m1 JOIN gapto.hechos_financieros t1 ON t1.id = m1.hecho_id WHERE m1.id = inversion_asignaciones_efecto.efecto_inversion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.inversion_objetivos_versiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.inversion_objetivos_versiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.inversion_objetivos_versiones
    USING (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_objetivos_versiones.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_objetivos_versiones.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.inversion_valoraciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.inversion_valoraciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.inversion_valoraciones
    USING (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_valoraciones.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.inversiones m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = inversion_valoraciones.inversion_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.inversiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.inversiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.inversiones
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = inversiones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = inversiones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (tercero_gestor_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = inversiones.tercero_gestor_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.magnitudes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.magnitudes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.magnitudes
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.mapeos_importacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.mapeos_importacion FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.mapeos_importacion FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.registros_origen_importacion m1 JOIN gapto.fuentes_importacion t1 ON t1.id = m1.fuente_importacion_id WHERE m1.id = mapeos_importacion.registro_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.mapeos_importacion FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.registros_origen_importacion m1 JOIN gapto.fuentes_importacion t1 ON t1.id = m1.fuente_importacion_id WHERE m1.id = mapeos_importacion.registro_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.movimientos_tesoreria ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.movimientos_tesoreria FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.movimientos_tesoreria
    USING (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = movimientos_tesoreria.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = movimientos_tesoreria.cuenta_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.plantillas_registro ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.plantillas_registro FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.plantillas_registro
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = plantillas_registro.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = plantillas_registro.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (entidad_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = plantillas_registro.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_default_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = plantillas_registro.cuenta_default_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.preferencias_registro ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.preferencias_registro FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.preferencias_registro
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = preferencias_registro.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = preferencias_registro.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (entidad_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = preferencias_registro.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_default_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = preferencias_registro.cuenta_default_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.preferencias_ui ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.preferencias_ui FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.preferencias_ui
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.presupuesto_linea_alcances ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.presupuesto_linea_alcances FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.presupuesto_linea_alcances
    USING (EXISTS (SELECT 1 FROM gapto.presupuesto_lineas m1 JOIN gapto.presupuestos t1 ON t1.id = m1.presupuesto_id WHERE m1.id = presupuesto_linea_alcances.presupuesto_linea_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.presupuesto_lineas m1 JOIN gapto.presupuestos t1 ON t1.id = m1.presupuesto_id WHERE m1.id = presupuesto_linea_alcances.presupuesto_linea_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = presupuesto_linea_alcances.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (entidad_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = presupuesto_linea_alcances.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.presupuesto_lineas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.presupuesto_lineas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.presupuesto_lineas
    USING (EXISTS (SELECT 1 FROM gapto.presupuestos t1 WHERE t1.id = presupuesto_lineas.presupuesto_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.presupuestos t1 WHERE t1.id = presupuesto_lineas.presupuesto_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.presupuestos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.presupuestos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.presupuestos
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (reemplaza_presupuesto_id IS NULL OR EXISTS (SELECT 1 FROM gapto.presupuestos t1 WHERE t1.id = presupuestos.reemplaza_presupuesto_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (generado_desde_cierre_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cierres_mensuales t1 WHERE t1.id = presupuestos.generado_desde_cierre_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.prevision_hechos ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.prevision_hechos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.prevision_hechos
    USING (EXISTS (SELECT 1 FROM gapto.previsiones t1 WHERE t1.id = prevision_hechos.prevision_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.previsiones t1 WHERE t1.id = prevision_hechos.prevision_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.hechos_financieros t1 WHERE t1.id = prevision_hechos.hecho_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.previsiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.previsiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.previsiones
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = previsiones.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = previsiones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (entidad_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = previsiones.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_salida_esperada_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = previsiones.cuenta_salida_esperada_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_entrada_esperada_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = previsiones.cuenta_entrada_esperada_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (regla_version_id IS NULL OR EXISTS (SELECT 1 FROM gapto.regla_versiones m1 JOIN gapto.reglas_financieras t1 ON t1.id = m1.regla_id WHERE m1.id = previsiones.regla_version_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.propiedad_servicios ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.propiedad_servicios FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.propiedad_servicios
    USING (EXISTS (SELECT 1 FROM gapto.propiedades m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = propiedad_servicios.propiedad_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.propiedades m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = propiedad_servicios.propiedad_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.servicios m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = propiedad_servicios.servicio_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.propiedad_valoraciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.propiedad_valoraciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.propiedad_valoraciones
    USING (EXISTS (SELECT 1 FROM gapto.propiedades m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = propiedad_valoraciones.propiedad_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.propiedades m1 JOIN gapto.entidades t1 ON t1.id = m1.entidad_id WHERE m1.entidad_id = propiedad_valoraciones.propiedad_entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.propiedades ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.propiedades FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.propiedades
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = propiedades.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = propiedades.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (direccion_id IS NULL OR EXISTS (SELECT 1 FROM gapto.direcciones t1 WHERE t1.id = propiedades.direccion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.registros_origen_importacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.registros_origen_importacion FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON gapto.registros_origen_importacion FOR SELECT USING (EXISTS (SELECT 1 FROM gapto.fuentes_importacion t1 WHERE t1.id = registros_origen_importacion.fuente_importacion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
CREATE POLICY tenant_insert ON gapto.registros_origen_importacion FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM gapto.fuentes_importacion t1 WHERE t1.id = registros_origen_importacion.fuente_importacion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));
-- Sin policy de UPDATE/DELETE: append-only por RLS + guard trigger (F03-01-B14)

ALTER TABLE gapto.regla_excepciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.regla_excepciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.regla_excepciones
    USING (EXISTS (SELECT 1 FROM gapto.reglas_financieras t1 WHERE t1.id = regla_excepciones.regla_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.reglas_financieras t1 WHERE t1.id = regla_excepciones.regla_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.regla_versiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.regla_versiones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.regla_versiones
    USING (EXISTS (SELECT 1 FROM gapto.reglas_financieras t1 WHERE t1.id = regla_versiones.regla_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.reglas_financieras t1 WHERE t1.id = regla_versiones.regla_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (categoria_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = regla_versiones.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (tercero_id IS NULL OR EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = regla_versiones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_salida_esperada_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = regla_versiones.cuenta_salida_esperada_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_entrada_esperada_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = regla_versiones.cuenta_entrada_esperada_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)) AND (cuenta_calculo_id IS NULL OR EXISTS (SELECT 1 FROM gapto.cuentas t1 WHERE t1.id = regla_versiones.cuenta_calculo_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.reglas_financieras ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.reglas_financieras FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.reglas_financieras
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid AND (entidad_origen_id IS NULL OR EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = reglas_financieras.entidad_origen_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.servicios ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.servicios FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.servicios
    USING (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = servicios.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.entidades t1 WHERE t1.id = servicios.entidad_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND (categoria_default_id IS NULL OR EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = servicios.categoria_default_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)));

ALTER TABLE gapto.tercero_afinidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.tercero_afinidades FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.tercero_afinidades
    USING (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_afinidades.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_afinidades.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.categorias_financieras t1 WHERE t1.id = tercero_afinidades.categoria_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.tercero_clasificaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.tercero_clasificaciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.tercero_clasificaciones
    USING (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_clasificaciones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_clasificaciones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.clasificaciones_tercero t1 WHERE t1.id = tercero_clasificaciones.clasificacion_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.tercero_direcciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.tercero_direcciones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.tercero_direcciones
    USING (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_direcciones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_direcciones.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.tercero_personas ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.tercero_personas FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.tercero_personas
    USING (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_personas.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_personas.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.tercero_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.tercero_roles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.tercero_roles
    USING (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_roles.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.terceros t1 WHERE t1.id = tercero_roles.tercero_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.terceros ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.terceros FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.terceros
    USING (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (owner_user_id = current_setting('gapto.owner_user_id', true)::uuid);

ALTER TABLE gapto.transferencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.transferencias FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.transferencias
    USING (EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria m1 JOIN gapto.cuentas t1 ON t1.id = m1.cuenta_id WHERE m1.id = transferencias.movimiento_salida_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria m1 JOIN gapto.cuentas t1 ON t1.id = m1.cuenta_id WHERE m1.id = transferencias.movimiento_salida_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid) AND EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria m1 JOIN gapto.cuentas t1 ON t1.id = m1.cuenta_id WHERE m1.id = transferencias.movimiento_entrada_id AND t1.owner_user_id = current_setting('gapto.owner_user_id', true)::uuid));

ALTER TABLE gapto.usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE gapto.usuarios FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gapto.usuarios
    USING (id = current_setting('gapto.owner_user_id', true)::uuid)
    WITH CHECK (id = current_setting('gapto.owner_user_id', true)::uuid);

RESET ROLE;