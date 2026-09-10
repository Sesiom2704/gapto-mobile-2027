-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0200_f03_01_b18_revoke_delete_realidad_financiera.sql
-- Ruta: migrations/0200_f03_01_b18_revoke_delete_realidad_financiera.sql
-- Descripcion: F03-01-B18. Resuelve el primer tramo de D-086/D-3 revocando
--   el DELETE directo de gapto_runtime sobre las 17 tablas de realidad
--   financiera y conciliacion.
--
--   PROBLEMA. D-068 establece que la realidad financiera e historica no
--   admite hard-delete directo y que no existe un grant universal de
--   DELETE. D-076/B14 concedio DELETE de forma uniforme a las 67 tablas
--   tenant escribibles, lo que en la practica es ese grant universal.
--   D-091 agrava el diagnostico: seis invariantes multi-fila de B12 no se
--   declaran para DELETE, de modo que un borrado puede dejar sumas de
--   participacion incompletas, pares de reversion rotos, transferencias
--   con movimientos huerfanos o prioridades de BOLSA ambiguas sin que
--   ninguna invariante lo impida. Cinco de esas seis viven en este
--   perimetro.
--
--   ALCANCE. Solo el Bucket A aprobado: importes economicos, su
--   conciliacion y los snapshots inmutables. NO se tocan los Buckets B
--   (versionado) ni C (identidad/trazabilidad), que siguen pendientes de
--   decision, ni las 33 tablas de configuracion, catalogos y planificacion
--   donde el DELETE es legitimo.
--
--   LO QUE NO CAMBIA. gapto_runtime conserva SELECT, INSERT y UPDATE sobre
--   estas 17 tablas. La correccion de un error de captura sigue siendo
--   posible mediante edicion auditada (D-040); la reversion de un hecho
--   real posterior sigue siendo un hecho nuevo relacionado, no un borrado.
--   hechos_financieros y movimientos_tesoreria disponen ya de estado
--   ACTIVO/ANULADO, que es el camino correcto.
--
--   CONSECUENCIA OPERATIVA CONOCIDA. Cinco de las 17 son tablas puente o
--   de atributo del hecho (hecho_entidades, hecho_participantes,
--   hecho_terceros, hecho_magnitudes, hecho_relaciones). Corregir un
--   vinculo erroneo sigue siendo posible por UPDATE, pero eliminar un
--   vinculo sobrante deja de serlo. Queda anotado como consecuencia
--   deliberada, no como efecto colateral no visto.
--
--   Matriz efectiva de gapto_runtime tras este bloque:
--       SELECT 79 / INSERT 73 / UPDATE 67 / DELETE 50
--
--   No se modifica 0130 ni ninguna migration ya aplicada: la correccion es
--   forward-only. test_016_b14_grants_guards.py pasa a v0.1.2 y
--   test_020_b16_role_chain.py a v0.1.1 porque sus conteos de DELETE
--   dejan de ser ciertos por diseno.
--
--   El identificador B18 no implica orden de ejecucion: B17 quedo
--   reservado en D-090 para la cobertura RLS de las tablas con ownership
--   derivado y se materializara despues.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- El grantor debe ser el propietario de las tablas.
SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 1) Nucleo de hechos: importe, efecto economico y atribucion
-- ------------------------------------------------------------
-- Un hecho erroneo se anula (estado ANULADO) o se corrige con edicion
-- auditada; una devolucion real posterior es un hecho nuevo con delta
-- firmado negativo (D-020), nunca el borrado del original.
REVOKE DELETE ON gapto.hechos_financieros          FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_efectos               FROM gapto_runtime;
REVOKE DELETE ON gapto.efecto_atribuciones         FROM gapto_runtime;

-- ------------------------------------------------------------
-- 2) Conciliacion: quien financio el pago y que movimiento lo respalda
-- ------------------------------------------------------------
-- Estas dos capas son las que sostienen la separacion entre atribucion
-- economica, financiacion real y tesoreria (D-040). Borrarlas rompe la
-- conciliacion sin dejar rastro.
REVOKE DELETE ON gapto.hecho_aportaciones_pago     FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_movimientos_tesoreria FROM gapto_runtime;

-- ------------------------------------------------------------
-- 3) Vinculos y atributos del hecho
-- ------------------------------------------------------------
-- Ver CONSECUENCIA OPERATIVA CONOCIDA en la cabecera: la correccion por
-- UPDATE se conserva; la eliminacion de un vinculo sobrante no.
REVOKE DELETE ON gapto.hecho_entidades             FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_participantes         FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_terceros              FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_magnitudes            FROM gapto_runtime;
REVOKE DELETE ON gapto.hecho_relaciones            FROM gapto_runtime;

-- ------------------------------------------------------------
-- 4) Tesoreria confirmada
-- ------------------------------------------------------------
-- movimientos_tesoreria usa ACTIVO/ANULADO y modela la reversion mediante
-- un movimiento nuevo enlazado (D-039). transferencias es la asociacion de
-- dos movimientos: borrarla deja el par huerfano y
-- trg_transferencias__estructura no cubre DELETE (D-091).
REVOKE DELETE ON gapto.movimientos_tesoreria       FROM gapto_runtime;
REVOKE DELETE ON gapto.transferencias              FROM gapto_runtime;

-- ------------------------------------------------------------
-- 5) Snapshots y calendarios historicos
-- ------------------------------------------------------------
-- Los cierres son inmutables por version y se reabren creando una version
-- nueva (D-046). Las cuotas pasadas y la realidad conciliada no se
-- reescriben (D-044). Las valoraciones son puntos de valor historicos que
-- no se corrigen borrando (D-043, D-045).
REVOKE DELETE ON gapto.cierres_mensuales           FROM gapto_runtime;
REVOKE DELETE ON gapto.financiacion_cuotas         FROM gapto_runtime;
REVOKE DELETE ON gapto.inversion_valoraciones      FROM gapto_runtime;
REVOKE DELETE ON gapto.inversion_asignaciones_efecto FROM gapto_runtime;
REVOKE DELETE ON gapto.propiedad_valoraciones      FROM gapto_runtime;

RESET ROLE;

COMMIT;
