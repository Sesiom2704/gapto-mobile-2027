-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0265_f03_02_anclaje_recurrencia.sql
-- Ruta: migrations/0265_f03_02_anclaje_recurrencia.sql
-- Descripcion: D-126 / F02-E01-R2. Reapertura parcial y controlada de F02-E01
--   (reglas y previsiones), materializada forward-only durante la pausa
--   controlada de F03-02. Se numera 0265 para no reutilizar las reservas
--   0270/0280 y para que el orden de nombres coincida con el orden real de
--   aplicacion y con el replay clean-room.
--
--   CASO REAL. Bono de gimnasio: gasto habitual sin calendario fijo. Si el
--   bono se compra antes (o despues) de lo previsto, la siguiente previsión
--   se calcula desde la compra real, no desde el calendario inicial. Si llega
--   la fecha y aun no hace falta, no hay gasto, ni tesoreria, ni liquidez
--   afectada, ni hecho ficticio, ni la regla se desactiva. No se modela el
--   consumo de sesiones.
--
--   CAMBIO. Se separa la CADENCIA (periodicidad + intervalo, sin cambios) del
--   ANCLAJE de la cadena de ocurrencias:
--     CALENDARIO - ocurrencias de un calendario estable generado desde la
--                  regla; la fecha real de una ocurrencia no desplaza las
--                  siguientes. Es la semantica historica de toda regla
--                  recurrente anterior a esta migration.
--     RODANTE    - cada ocurrencia depende de la anterior: si se realiza,
--                  la siguiente parte de su fecha real; si se omite, de su
--                  fecha_objetivo_regla. Una omision nunca crea realidad.
--   fecha_modo sigue siendo una dimension distinta (como se representa la
--   fecha). No se reutiliza.
--
--   CONTRATO FISICO (solo modelo de datos; el algoritmo de generacion es del
--   motor de F04 y no se implementa en PostgreSQL):
--     - regla_versiones.anclaje_recurrencia varchar(30) NULL, SIN DEFAULT:
--       la semantica debe expresarse siempre de forma explicita.
--     - ck_regla_versiones__anclaje_recurrencia: tokens CALENDARIO/RODANTE.
--     - ck_regla_versiones__anclaje_periodicidad: periodicidad IS NULL si y
--       solo si anclaje_recurrencia IS NULL (una version no recurrente no
--       adquiere semantica de recurrencia; una recurrente siempre la declara).
--     - ck_regla_versiones__rodante_fecha_modo: RODANTE solo con
--       fecha_modo=ANCLA. VENTANA (dias del mes) queda prohibida con RODANTE
--       y no se crea una ventana relativa todavia; CALENDARIO_ENTIDAD
--       tambien, porque delega la fecha en otra autoridad.
--     - ck_regla_versiones__rodante_importe_modo: RODANTE no admite
--       importe_modo=CALENDARIO_ENTIDAD.
--
--   COMPATIBILIDAD. Toda version recurrente existente se migra explicitamente
--   a CALENDARIO, que reproduce exactamente su comportamiento; las no
--   recurrentes quedan con NULL. No se reinterpreta ninguna recurrencia
--   historica. Sin tabla, trigger, funcion, indice ni FK nuevos.
--
--   RLS (D-094/D-095). El backfill y la validacion de los CHECK se hacen con
--   FORCE ROW LEVEL SECURITY levantado dentro de la misma transaccion, como
--   gapto_owner (propietario sin FORCE = visibilidad completa), y FORCE se
--   restaura antes del COMMIT. Asi ninguna fila queda oculta al backfill.
--
--   SALVAGUARDAS. Precheck de estado previo; comprobacion posterior al
--   backfill de que no queda ninguna version recurrente sin anclaje;
--   postcheck de columna, constraints validadas, FORCE restaurado, privilegios
--   de gapto_runtime sobre la columna y recuentos de funciones y triggers sin
--   cambios.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

DO $precheck$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                WHERE a.attrelid = 'gapto.regla_versiones'::pg_catalog.regclass
                  AND a.attname = 'anclaje_recurrencia' AND NOT a.attisdropped) THEN
        RAISE EXCEPTION 'F03-02-0265 PRECHECK: regla_versiones.anclaje_recurrencia ya existe';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
                WHERE c.conrelid = 'gapto.regla_versiones'::pg_catalog.regclass
                  AND c.conname IN ('ck_regla_versiones__anclaje_recurrencia',
                                    'ck_regla_versiones__anclaje_periodicidad',
                                    'ck_regla_versiones__rodante_fecha_modo',
                                    'ck_regla_versiones__rodante_importe_modo')) THEN
        RAISE EXCEPTION 'F03-02-0265 PRECHECK: alguna constraint de 0265 ya existe';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                    WHERE c.oid = 'gapto.regla_versiones'::pg_catalog.regclass
                      AND c.relrowsecurity AND c.relforcerowsecurity) THEN
        RAISE EXCEPTION 'F03-02-0265 PRECHECK: regla_versiones no tiene RLS con FORCE';
    END IF;
END
$precheck$;

ALTER TABLE gapto.regla_versiones ADD COLUMN anclaje_recurrencia varchar(30);

COMMENT ON COLUMN gapto.regla_versiones.anclaje_recurrencia IS
    'D-126: anclaje de la cadena de ocurrencias. CALENDARIO = calendario estable; RODANTE = cada ocurrencia parte de la anterior (fecha real si se realiza, fecha_objetivo_regla si se omite). NULL solo en versiones no recurrentes. Sin DEFAULT.';

ALTER TABLE gapto.regla_versiones NO FORCE ROW LEVEL SECURITY;

UPDATE gapto.regla_versiones
   SET anclaje_recurrencia = 'CALENDARIO'
 WHERE periodicidad IS NOT NULL
   AND anclaje_recurrencia IS NULL;

DO $backfill$
DECLARE
    v_pendientes integer;
BEGIN
    SELECT pg_catalog.count(*) INTO v_pendientes
      FROM gapto.regla_versiones
     WHERE periodicidad IS NOT NULL AND anclaje_recurrencia IS NULL;
    IF v_pendientes <> 0 THEN
        RAISE EXCEPTION 'F03-02-0265 BACKFILL: % versiones recurrentes siguen sin anclaje', v_pendientes;
    END IF;
END
$backfill$;

ALTER TABLE gapto.regla_versiones
    ADD CONSTRAINT ck_regla_versiones__anclaje_recurrencia
    CHECK (anclaje_recurrencia IS NULL OR anclaje_recurrencia IN ('CALENDARIO', 'RODANTE'));

ALTER TABLE gapto.regla_versiones
    ADD CONSTRAINT ck_regla_versiones__anclaje_periodicidad
    CHECK ((periodicidad IS NULL) = (anclaje_recurrencia IS NULL));

ALTER TABLE gapto.regla_versiones
    ADD CONSTRAINT ck_regla_versiones__rodante_fecha_modo
    CHECK (anclaje_recurrencia IS DISTINCT FROM 'RODANTE' OR fecha_modo = 'ANCLA');

ALTER TABLE gapto.regla_versiones
    ADD CONSTRAINT ck_regla_versiones__rodante_importe_modo
    CHECK (anclaje_recurrencia IS DISTINCT FROM 'RODANTE' OR importe_modo <> 'CALENDARIO_ENTIDAD');

ALTER TABLE gapto.regla_versiones FORCE ROW LEVEL SECURITY;

DO $postcheck$
DECLARE
    v_tipo        text;
    v_not_null    boolean;
    v_default     integer;
    v_checks      integer;
    v_funciones   integer;
    v_triggers    integer;
BEGIN
    SELECT pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull
      INTO v_tipo, v_not_null
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.regla_versiones'::pg_catalog.regclass
       AND a.attname = 'anclaje_recurrencia' AND NOT a.attisdropped;
    IF v_tipo IS DISTINCT FROM 'character varying(30)' OR v_not_null THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: columna inesperada (tipo=%, not null=%)', v_tipo, v_not_null;
    END IF;

    SELECT pg_catalog.count(*) INTO v_default
      FROM pg_catalog.pg_attrdef d
      JOIN pg_catalog.pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
     WHERE a.attrelid = 'gapto.regla_versiones'::pg_catalog.regclass
       AND a.attname = 'anclaje_recurrencia';
    IF v_default <> 0 THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: anclaje_recurrencia tiene DEFAULT';
    END IF;

    SELECT pg_catalog.count(*) INTO v_checks
      FROM pg_catalog.pg_constraint c
     WHERE c.conrelid = 'gapto.regla_versiones'::pg_catalog.regclass
       AND c.contype = 'c' AND c.convalidated
       AND c.conname IN ('ck_regla_versiones__anclaje_recurrencia',
                         'ck_regla_versiones__anclaje_periodicidad',
                         'ck_regla_versiones__rodante_fecha_modo',
                         'ck_regla_versiones__rodante_importe_modo');
    IF v_checks <> 4 THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: se esperaban 4 CHECK validados, hay %', v_checks;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                    WHERE c.oid = 'gapto.regla_versiones'::pg_catalog.regclass
                      AND c.relrowsecurity AND c.relforcerowsecurity) THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: FORCE ROW LEVEL SECURITY no restaurado';
    END IF;

    IF NOT (pg_catalog.has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'SELECT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'INSERT')
        AND pg_catalog.has_column_privilege('gapto_runtime', 'gapto.regla_versiones', 'anclaje_recurrencia', 'UPDATE')) THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: gapto_runtime sin SELECT/INSERT/UPDATE sobre anclaje_recurrencia';
    END IF;

    SELECT pg_catalog.count(*) INTO v_funciones
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    SELECT pg_catalog.count(*) INTO v_triggers
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_funciones <> 15 OR v_triggers <> 34 THEN
        RAISE EXCEPTION 'F03-02-0265 POSTCHECK: funciones=% triggers=% (se esperaban 15 y 34)', v_funciones, v_triggers;
    END IF;
END
$postcheck$;

RESET ROLE;

COMMIT;
