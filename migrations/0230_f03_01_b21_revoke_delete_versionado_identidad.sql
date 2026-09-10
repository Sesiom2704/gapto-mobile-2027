-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0230_f03_01_b21_revoke_delete_versionado_identidad.sql
-- Ruta: migrations/0230_f03_01_b21_revoke_delete_versionado_identidad.sql
-- Descripcion: F03-01-B21. Cierra D-086 aplicando las decisiones del usuario
--   sobre los Buckets B y C, que quedaban pendientes desde B18.
--
--   BUCKET B - VERSIONADO. Se revoca DELETE en las 7 tablas de versionado.
--   Una fila versionada forma parte de la interpretacion historica del
--   sistema aunque no sea en si misma un hecho financiero: borrarla
--   reinterpreta el pasado, que es lo que D-068 prohibe. Un error de captura
--   se corrige con edicion auditada (D-040); un cambio real de condiciones se
--   representa con una version nueva que sucede a la anterior, no que la
--   sustituye. NO se introduce un estado ANULADA generico: esa capacidad solo
--   se anadira si aparece un requisito funcional que no pueda resolverse con
--   correccion auditada mas sucesion de versiones.
--
--   BUCKET C - IDENTIDAD Y TRAZABILIDAD. Se aplica la opcion C: revocar donde
--   existe ciclo de vida propio o donde el borrado es sistemicamente
--   inaceptable, y conservar donde hoy no hay alternativa al borrado.
--
--     Se revoca en 7:
--       usuarios                          es la raiz del tenant; eliminar una
--                                         cuenta de cliente debe ser un
--                                         workflow especifico, nunca un DELETE
--                                         ordinario del runtime.
--       inversiones                       tiene columna estado.
--       financiaciones                    tiene columna estado.
--       derechos_obligaciones_financieras tiene columna estado.
--       contratos                         tiene columna estado_documental.
--       documentos                        tiene estado_archivo con valor
--                                         ELIMINADO; el borrado logico ya
--                                         estaba previsto en el modelo.
--       fuentes_importacion               tiene columna estado y es la cabecera
--                                         de trazabilidad de una importacion.
--
--     Se conserva en 3, sujeto a las FK RESTRICT ya existentes:
--       entidades, cuentas, propiedades
--     Carecen hoy de ciclo de vida equivalente, y sin DELETE el usuario no
--     tendria forma de retirar un alta erronea. RESTRICT es la barrera fisica:
--     en cuanto exista historia referenciada, PostgreSQL impide el borrado.
--     Conservar DELETE NO significa que cerrar una cuenta, vender una propiedad
--     o finalizar una entidad se modelen como borrado: esos son cambios de
--     estado que el modelo debera representar cuando corresponda.
--
--   Matriz efectiva de gapto_runtime tras este bloque:
--       SELECT 79 / INSERT 73 / UPDATE 67 / DELETE 36
--   Historico: DELETE 67 (B14) -> 50 (B18) -> 36 (B21).
--
--   NO se toca ninguna invariante en este bloque. La cobertura de DELETE en los
--   triggers (D-091) se resuelve por separado tras la auditoria funcion a
--   funcion aprobada por el usuario, porque retirar un privilegio no sustituye
--   a la integridad de base de datos.
--
--   No se modifica 0130 ni ninguna migration ya aplicada: forward-only.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- Bucket B: versionado. El pasado no se borra, se sucede.
-- ------------------------------------------------------------
REVOKE DELETE ON gapto.regla_versiones                    FROM gapto_runtime;
REVOKE DELETE ON gapto.financiacion_condiciones_versiones FROM gapto_runtime;
REVOKE DELETE ON gapto.contrato_revision_renta_versiones  FROM gapto_runtime;
REVOKE DELETE ON gapto.inversion_objetivos_versiones      FROM gapto_runtime;
REVOKE DELETE ON gapto.entidad_participaciones            FROM gapto_runtime;
REVOKE DELETE ON gapto.cuenta_participaciones             FROM gapto_runtime;
REVOKE DELETE ON gapto.contrato_participantes             FROM gapto_runtime;

-- ------------------------------------------------------------
-- Bucket C: identidad y trazabilidad con ciclo de vida propio
-- ------------------------------------------------------------
REVOKE DELETE ON gapto.usuarios                          FROM gapto_runtime;
REVOKE DELETE ON gapto.inversiones                       FROM gapto_runtime;
REVOKE DELETE ON gapto.financiaciones                    FROM gapto_runtime;
REVOKE DELETE ON gapto.derechos_obligaciones_financieras FROM gapto_runtime;
REVOKE DELETE ON gapto.contratos                         FROM gapto_runtime;
REVOKE DELETE ON gapto.documentos                        FROM gapto_runtime;
REVOKE DELETE ON gapto.fuentes_importacion               FROM gapto_runtime;

-- entidades, cuentas y propiedades conservan DELETE de forma deliberada.
-- Ver cabecera. Cuando adquieran ciclo de vida propio, este bloque debera
-- revisarse mediante una migration nueva.

RESET ROLE;

COMMIT;
