-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0250_f03_02_invariantes_for_no_key_update.sql
-- Ruta: migrations/0250_f03_02_invariantes_for_no_key_update.sql
-- Descripcion: FASE 03, frente de concurrencia READ COMMITTED. Correccion
--   forward-only posterior a la cadena congelada 0001..0240 (F03-GATE-01).
--   No reabre F03-01.
--
--   PROBLEMA MEDIDO. Las ocho funciones de invariante multi-fila bloquean la
--   fila padre con SELECT ... FOR UPDATE antes de sumar o comprobar las hijas.
--   Las FK hija->padre son inmediatas: cada INSERT de una hija toma FOR KEY
--   SHARE sobre el padre y lo retiene hasta el final de la transaccion.
--   FOR UPDATE es incompatible con FOR KEY SHARE. Dos transacciones que
--   insertan hijas del mismo padre se bloquean mutuamente al validar y
--   PostgreSQL resuelve el ciclo abortando una con 40P01 tras deadlock_timeout.
--   test_027_concurrencia.py lo midio identico en Neon 17.11 y Supabase 17.6:
--   C2 (dos cambios de reparto legitimos con delta cero) FAIL_LIVENESS, y
--   C1/C4/C4b terminan en deadlock en lugar de rechazarse por la invariante.
--
--   CORRECCION. Se sustituye FOR UPDATE por FOR NO KEY UPDATE en las nueve
--   apariciones de las ocho funciones. Nada mas cambia en los cuerpos.
--
--   COMPATIBILIDAD DE LOCKS (correcta; corrige una afirmacion previa erronea):
--     - FOR NO KEY UPDATE sigue siendo incompatible consigo mismo: dos
--       validadores del mismo padre siguen serializandose.
--     - Sigue en conflicto con un UPDATE ordinario de columnas no clave del
--       padre, porque ese UPDATE toma precisamente FOR NO KEY UPDATE.
--     - Sigue en conflicto con DELETE y con UPDATE de columnas clave, que
--       toman FOR UPDATE.
--     - La UNICA compatibilidad nueva es con FOR KEY SHARE, el lock que toman
--       las comprobaciones de FK de las hijas. Es exactamente el conflicto que
--       producia el deadlock sistematico.
--
--   PATRON VERIFICADO ANTES DE ESCRIBIR ESTA MIGRATION. Las ocho bloquean una
--   unica fila padre por id, sin NOWAIT, SKIP LOCKED ni OF; prosrc identico
--   en gapto2027_test, gapto2027_cleanroom (Neon) y postgres (Supabase):
--     fn_check_participacion_suma          cuentas / entidades (SQL dinamico)
--     fn_check_atribucion_suma             hecho_efectos
--     fn_check_inversion_asignacion_suma   hecho_efectos
--     fn_check_hecho_mov_tesoreria_suma    movimientos_tesoreria
--     fn_check_reversion_movimiento        movimientos_tesoreria (original)
--     fn_check_transferencia_estructura    movimientos_tesoreria x2 (LEAST/GREATEST)
--     fn_check_bolsa_prioridad             presupuestos
--     fn_check_bolsa_prioridad_alcance     presupuestos
--
--   QUE NO CAMBIA. Los triggers, su condicion DEFERRABLE INITIALLY DEFERRED,
--   sus eventos, la semantica de cada invariante, la volatilidad (VOLATILE),
--   el propietario (gapto_owner) y los comentarios de las funciones.
--   CREATE OR REPLACE conserva el oid, los GRANT y los triggers asociados.
--
--   QUE NO RESUELVE. El deadlock multi-padre (dos transacciones que validan
--   P1->P2 y P2->P1) es inherente a cualquier modo de lock (C7). El backend
--   debe reintentar la TRANSACCION COMPLETA ante 40P01, no solo el COMMIT.
--
--   SALVAGUARDAS. Un precheck exige que las ocho funciones tengan EXACTAMENTE
--   el prosrc del baseline 0240; si alguna difiere, la migration aborta sin
--   tocar nada. Un postcheck exige las huellas nuevas y que no quede ninguna
--   funcion del schema gapto con FOR UPDATE.
--
--   Los cuerpos van sin comentarios inline por la misma razon que en 0240:
--   prosrc se compara por md5 entre proveedores.
--
--   HUELLAS (md5 de prosrc, bytes)  baseline 0240  ->  0250:
--     fn_check_participacion_suma          c909c04f4e0131a32c6552efe601d370  2436  ->  d01fd963789d8adf4b29cbb007604414  2443
--     fn_check_atribucion_suma             8b154502e044ff1514db8e9ab268560f  1549  ->  1875c05dfd509221eb2acd2665ec3477  1556
--     fn_check_inversion_asignacion_suma   cf35870cc07eebe4fb37830805b965bf  1274  ->  9a59512f3e0109689af70e79e78159ee  1281
--     fn_check_hecho_mov_tesoreria_suma    944b5019a715df6ce3ac0fd505b054d2   986  ->  693fa7086767b581a6bd45eadc8944c2   993
--     fn_check_reversion_movimiento        cae4f825c562ef77055283f74e8103a5  1768  ->  859f7f7e9a5b0b518e6272c410bedf83  1775
--     fn_check_transferencia_estructura    23ec279218c0e57db9c98031f77b09b4  1862  ->  a6c74336f91ddb4239914672cab01c97  1876
--     fn_check_bolsa_prioridad             9fadbb93347560f891d17c1a88549ebf  1140  ->  e0640d1e1af1a043cb5585ae69c4b89b  1147
--     fn_check_bolsa_prioridad_alcance     0eb39ed53b28a3c4657e032f3aaaa037  1524  ->  7d9abf8d58b812b88d8c58e9968a50fe  1531
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

DO $precheck$
DECLARE
    v_divergentes text;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre)
      INTO v_divergentes
      FROM (VALUES
        ('fn_check_participacion_suma', 'c909c04f4e0131a32c6552efe601d370'),
        ('fn_check_atribucion_suma', '8b154502e044ff1514db8e9ab268560f'),
        ('fn_check_inversion_asignacion_suma', 'cf35870cc07eebe4fb37830805b965bf'),
        ('fn_check_hecho_mov_tesoreria_suma', '944b5019a715df6ce3ac0fd505b054d2'),
        ('fn_check_reversion_movimiento', 'cae4f825c562ef77055283f74e8103a5'),
        ('fn_check_transferencia_estructura', '23ec279218c0e57db9c98031f77b09b4'),
        ('fn_check_bolsa_prioridad', '9fadbb93347560f891d17c1a88549ebf'),
        ('fn_check_bolsa_prioridad_alcance', '0eb39ed53b28a3c4657e032f3aaaa037')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
             ON p.proname = e.nombre
            AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL
        OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;

    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0250 PRECHECK: prosrc distinto del baseline 0240 en: %', v_divergentes;
    END IF;
END
$precheck$;

CREATE OR REPLACE FUNCTION gapto.fn_check_participacion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_fk_col       text := TG_ARGV[0];
    v_parent_table text := TG_ARGV[1];
    v_parent_id    uuid;
    v_existe       boolean;
    v_filas        integer;
    v_min_suma     numeric;
    v_max_suma     numeric;
    v_sql          text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        EXECUTE format('SELECT ($1).%I', v_fk_col) INTO v_parent_id USING OLD;
    ELSE
        EXECUTE format('SELECT ($1).%I', v_fk_col) INTO v_parent_id USING NEW;
    END IF;

    IF v_parent_id IS NULL THEN
        RETURN NULL;
    END IF;

    EXECUTE format('SELECT EXISTS (SELECT 1 FROM gapto.%I WHERE id = $1 FOR NO KEY UPDATE)',
                   v_parent_table)
       INTO v_existe USING v_parent_id;
    IF NOT v_existe THEN
        RETURN NULL;
    END IF;

    EXECUTE format('SELECT count(*) FROM gapto.%I WHERE %I = $1', TG_TABLE_NAME, v_fk_col)
       INTO v_filas USING v_parent_id;
    IF v_filas = 0 THEN
        RETURN NULL;
    END IF;

    v_sql := format(
        'WITH puntos AS (
             SELECT vigente_desde AS punto FROM gapto.%1$I WHERE %2$I = $1
             UNION
             SELECT (vigente_hasta + 1) FROM gapto.%1$I
              WHERE %2$I = $1 AND vigente_hasta IS NOT NULL
         ),
         limites AS (
             SELECT min(vigente_desde) AS ini,
                    max(coalesce(vigente_hasta, ''infinity''::date)) AS fin
               FROM gapto.%1$I WHERE %2$I = $1
         ),
         evaluados AS (
             SELECT p.punto,
                    (SELECT coalesce(sum(t.porcentaje), 0)
                       FROM gapto.%1$I t
                      WHERE t.%2$I = $1
                        AND t.vigente_desde <= p.punto
                        AND (t.vigente_hasta IS NULL OR t.vigente_hasta >= p.punto)
                    ) AS suma
               FROM puntos p, limites l
              WHERE p.punto >= l.ini AND p.punto <= l.fin
         )
         SELECT min(suma), max(suma) FROM evaluados',
        TG_TABLE_NAME, v_fk_col
    );
    EXECUTE v_sql INTO v_min_suma, v_max_suma USING v_parent_id;

    IF v_min_suma IS NULL THEN
        RETURN NULL;
    END IF;

    IF v_max_suma <> 100 OR v_min_suma <> 100 THEN
        RAISE EXCEPTION
            'gapto.%: la participacion debe sumar exactamente 100 en todo instante cubierto para %=% (minimo encontrado=%, maximo encontrado=%)',
            TG_TABLE_NAME, v_fk_col, v_parent_id, v_min_suma, v_max_suma;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_atribucion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_efecto_id uuid;
    v_importe_delta numeric;
    v_estado varchar;
    v_suma numeric;
BEGIN
    IF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_efecto_id := COALESCE(NEW.id, OLD.id);
    ELSE
        v_efecto_id := COALESCE(NEW.efecto_id, OLD.efecto_id);
    END IF;

    SELECT importe_delta, estado_atribucion INTO v_importe_delta, v_estado
      FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR NO KEY UPDATE;

    IF v_importe_delta IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(sum(importe_atribuido), 0) INTO v_suma
      FROM gapto.efecto_atribuciones WHERE efecto_id = v_efecto_id;

    IF v_estado = 'COMPLETA' THEN
        IF v_suma <> v_importe_delta THEN
            RAISE EXCEPTION 'efecto_atribuciones: con estado_atribucion=COMPLETA la suma (%) debe ser exactamente igual a importe_delta (%) del efecto %',
                v_suma, v_importe_delta, v_efecto_id;
        END IF;
    ELSIF v_estado = 'PARCIAL' THEN
        IF abs(v_suma) > abs(v_importe_delta) THEN
            RAISE EXCEPTION 'efecto_atribuciones: con estado_atribucion=PARCIAL la suma (%) no puede superar en valor absoluto importe_delta (%) del efecto %',
                v_suma, v_importe_delta, v_efecto_id;
        END IF;
        IF v_suma <> 0 AND sign(v_suma) <> sign(v_importe_delta) THEN
            RAISE EXCEPTION 'efecto_atribuciones: la suma (%) debe mantener signo compatible con importe_delta (%) del efecto %',
                v_suma, v_importe_delta, v_efecto_id;
        END IF;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_inversion_asignacion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_efecto_id uuid := COALESCE(NEW.efecto_inversion_id, OLD.efecto_inversion_id);
    v_importe_delta numeric;
    v_tipo_efecto varchar;
    v_suma numeric;
BEGIN
    SELECT importe_delta, tipo_efecto INTO v_importe_delta, v_tipo_efecto
      FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR NO KEY UPDATE;

    IF v_importe_delta IS NULL THEN
        RETURN NULL;
    END IF;

    IF TG_OP <> 'DELETE' AND v_tipo_efecto <> 'INVERSION' THEN
        RAISE EXCEPTION 'inversion_asignaciones_efecto: el efecto % debe ser tipo_efecto=INVERSION (encontrado=%)', v_efecto_id, v_tipo_efecto;
    END IF;

    SELECT COALESCE(sum(importe_asignado), 0) INTO v_suma
      FROM gapto.inversion_asignaciones_efecto WHERE efecto_inversion_id = v_efecto_id;

    IF abs(v_suma) > abs(v_importe_delta) THEN
        RAISE EXCEPTION 'inversion_asignaciones_efecto: suma asignada (%) supera en valor absoluto el efecto % (importe_delta=%)',
            v_suma, v_efecto_id, v_importe_delta;
    END IF;
    IF v_suma <> 0 AND sign(v_suma) <> sign(v_importe_delta) THEN
        RAISE EXCEPTION 'inversion_asignaciones_efecto: la suma (%) debe tener el mismo signo que el efecto % (importe_delta=%)',
            v_suma, v_efecto_id, v_importe_delta;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_movimiento_id uuid := COALESCE(NEW.movimiento_tesoreria_id, OLD.movimiento_tesoreria_id);
    v_importe numeric;
    v_suma numeric;
BEGIN
    SELECT importe INTO v_importe FROM gapto.movimientos_tesoreria WHERE id = v_movimiento_id FOR NO KEY UPDATE;
    IF v_importe IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(sum(importe_asignado), 0) INTO v_suma
      FROM gapto.hecho_movimientos_tesoreria WHERE movimiento_tesoreria_id = v_movimiento_id;

    IF abs(v_suma) > abs(v_importe) THEN
        RAISE EXCEPTION 'hecho_movimientos_tesoreria: suma asignada (%) supera en valor absoluto el importe del movimiento % (importe=%)',
            v_suma, v_movimiento_id, v_importe;
    END IF;
    IF v_suma <> 0 AND sign(v_suma) <> sign(v_importe) THEN
        RAISE EXCEPTION 'hecho_movimientos_tesoreria: la suma (%) debe tener el mismo signo que el movimiento % (importe=%)',
            v_suma, v_movimiento_id, v_importe;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_reversion_movimiento()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_original RECORD;
    v_nuevo_owner uuid;
    v_nueva_moneda varchar;
    v_suma_reversiones numeric;
BEGIN
    IF NEW.reversion_de_movimiento_id IS NULL THEN
        RETURN NEW;
    END IF;

    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = NEW.reversion_de_movimiento_id FOR NO KEY UPDATE;

    SELECT m.importe, c.owner_user_id, c.moneda
      INTO v_original
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.reversion_de_movimiento_id;

    IF v_original.importe IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT c.owner_user_id, c.moneda INTO v_nuevo_owner, v_nueva_moneda
      FROM gapto.cuentas c WHERE c.id = NEW.cuenta_id;

    IF v_nuevo_owner <> v_original.owner_user_id THEN
        RAISE EXCEPTION 'movimientos_tesoreria: la reversion de % debe conservar el mismo owner', NEW.reversion_de_movimiento_id;
    END IF;
    IF sign(NEW.importe) = sign(v_original.importe) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: la reversion de % debe tener signo contrario al original (original=%)', NEW.reversion_de_movimiento_id, v_original.importe;
    END IF;

    IF v_nueva_moneda = v_original.moneda THEN
        SELECT COALESCE(sum(abs(m.importe)), 0) INTO v_suma_reversiones
          FROM gapto.movimientos_tesoreria m
         WHERE m.reversion_de_movimiento_id = NEW.reversion_de_movimiento_id
           AND m.estado = 'ACTIVO';

        IF v_suma_reversiones > abs(v_original.importe) THEN
            RAISE EXCEPTION 'movimientos_tesoreria: la suma de reversiones activas (%) no puede superar el importe original % (importe=%)',
                v_suma_reversiones, NEW.reversion_de_movimiento_id, v_original.importe;
        END IF;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_transferencia_estructura()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_salida RECORD;
    v_entrada RECORD;
    v_id1 uuid;
    v_id2 uuid;
BEGIN
    v_id1 := LEAST(NEW.movimiento_salida_id, NEW.movimiento_entrada_id);
    v_id2 := GREATEST(NEW.movimiento_salida_id, NEW.movimiento_entrada_id);
    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = v_id1 FOR NO KEY UPDATE;
    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = v_id2 FOR NO KEY UPDATE;

    SELECT m.importe, m.cuenta_id, c.owner_user_id, c.moneda
      INTO v_salida
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.movimiento_salida_id;

    SELECT m.importe, m.cuenta_id, c.owner_user_id, c.moneda
      INTO v_entrada
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.movimiento_entrada_id;

    IF v_salida.importe >= 0 THEN
        RAISE EXCEPTION 'transferencias: el movimiento de salida % debe tener importe negativo (encontrado=%)', NEW.movimiento_salida_id, v_salida.importe;
    END IF;
    IF v_entrada.importe <= 0 THEN
        RAISE EXCEPTION 'transferencias: el movimiento de entrada % debe tener importe positivo (encontrado=%)', NEW.movimiento_entrada_id, v_entrada.importe;
    END IF;
    IF v_salida.cuenta_id = v_entrada.cuenta_id THEN
        RAISE EXCEPTION 'transferencias: origen y destino deben ser cuentas distintas (cuenta_id=%)', v_salida.cuenta_id;
    END IF;
    IF v_salida.owner_user_id <> v_entrada.owner_user_id THEN
        RAISE EXCEPTION 'transferencias: origen y destino deben pertenecer al mismo owner';
    END IF;
    IF v_salida.moneda = v_entrada.moneda AND abs(v_salida.importe) <> v_entrada.importe THEN
        RAISE EXCEPTION 'transferencias: con la misma moneda, abs(importe_salida)=% debe igualar importe_entrada=%', abs(v_salida.importe), v_entrada.importe;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_bolsa_prioridad()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_conflicto uuid;
BEGIN
    IF NEW.tipo_linea <> 'BOLSA' THEN
        RETURN NEW;
    END IF;

    PERFORM 1 FROM gapto.presupuestos WHERE id = NEW.presupuesto_id FOR NO KEY UPDATE;

    SELECT otra.id INTO v_conflicto
      FROM gapto.presupuesto_lineas otra
      JOIN gapto.presupuesto_linea_alcances a_otra ON a_otra.presupuesto_linea_id = otra.id
      JOIN gapto.presupuesto_linea_alcances a_new ON (
            (a_new.categoria_id IS NOT NULL AND a_new.categoria_id = a_otra.categoria_id)
         OR (a_new.entidad_id IS NOT NULL AND a_new.entidad_id = a_otra.entidad_id)
      )
     WHERE otra.presupuesto_id = NEW.presupuesto_id
       AND otra.tipo_linea = 'BOLSA'
       AND otra.id <> NEW.id
       AND otra.prioridad_consumo = NEW.prioridad_consumo
       AND a_new.presupuesto_linea_id = NEW.id
     LIMIT 1;

    IF v_conflicto IS NOT NULL THEN
        RAISE EXCEPTION 'presupuesto_lineas: la BOLSA % empata en prioridad_consumo=% con la BOLSA % cuyo alcance intersecta (coincidencia directa; no evalua arbol de categorias)',
            NEW.id, NEW.prioridad_consumo, v_conflicto;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_bolsa_prioridad_alcance()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_linea_id    uuid;
    v_presupuesto uuid;
    v_tipo        varchar;
    v_prioridad   integer;
    v_conflicto   uuid;
BEGIN
    v_linea_id := coalesce(NEW.presupuesto_linea_id, OLD.presupuesto_linea_id);

    SELECT l.presupuesto_id, l.tipo_linea, l.prioridad_consumo
      INTO v_presupuesto, v_tipo, v_prioridad
      FROM gapto.presupuesto_lineas l
     WHERE l.id = v_linea_id;

    IF v_presupuesto IS NULL OR v_tipo <> 'BOLSA' THEN
        RETURN NULL;
    END IF;

    PERFORM 1 FROM gapto.presupuestos WHERE id = v_presupuesto FOR NO KEY UPDATE;

    SELECT otra.id INTO v_conflicto
      FROM gapto.presupuesto_lineas otra
      JOIN gapto.presupuesto_linea_alcances a_otra ON a_otra.presupuesto_linea_id = otra.id
      JOIN gapto.presupuesto_linea_alcances a_new ON (
            (a_new.categoria_id IS NOT NULL AND a_new.categoria_id = a_otra.categoria_id)
         OR (a_new.entidad_id   IS NOT NULL AND a_new.entidad_id   = a_otra.entidad_id)
      )
     WHERE otra.presupuesto_id = v_presupuesto
       AND otra.tipo_linea = 'BOLSA'
       AND otra.id <> v_linea_id
       AND otra.prioridad_consumo = v_prioridad
       AND a_new.presupuesto_linea_id = v_linea_id
     LIMIT 1;

    IF v_conflicto IS NOT NULL THEN
        RAISE EXCEPTION
            'presupuesto_linea_alcances: el alcance deja a la BOLSA % empatada en prioridad_consumo=% con la BOLSA % (coincidencia directa; no evalua arbol de categorias)',
            v_linea_id, v_prioridad, v_conflicto;
    END IF;

    RETURN NULL;
END;
$function$;

DO $postcheck$
DECLARE
    v_divergentes  text;
    v_con_update   text;
    v_apariciones  integer;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre)
      INTO v_divergentes
      FROM (VALUES
        ('fn_check_participacion_suma', 'd01fd963789d8adf4b29cbb007604414'),
        ('fn_check_atribucion_suma', '1875c05dfd509221eb2acd2665ec3477'),
        ('fn_check_inversion_asignacion_suma', '9a59512f3e0109689af70e79e78159ee'),
        ('fn_check_hecho_mov_tesoreria_suma', '693fa7086767b581a6bd45eadc8944c2'),
        ('fn_check_reversion_movimiento', '859f7f7e9a5b0b518e6272c410bedf83'),
        ('fn_check_transferencia_estructura', 'a6c74336f91ddb4239914672cab01c97'),
        ('fn_check_bolsa_prioridad', 'e0640d1e1af1a043cb5585ae69c4b89b'),
        ('fn_check_bolsa_prioridad_alcance', '7d9abf8d58b812b88d8c58e9968a50fe')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
             ON p.proname = e.nombre
            AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL
        OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;

    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0250 POSTCHECK: huella inesperada en: %', v_divergentes;
    END IF;

    SELECT pg_catalog.string_agg(p.proname, ', ' ORDER BY p.proname)
      INTO v_con_update
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.prosrc ~* 'for\s+update';

    IF v_con_update IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0250 POSTCHECK: siguen usando FOR UPDATE: %', v_con_update;
    END IF;

    SELECT pg_catalog.sum((SELECT pg_catalog.count(*)
                             FROM pg_catalog.regexp_matches(p.prosrc, 'for\s+no\s+key\s+update', 'gi')))
      INTO v_apariciones
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;

    IF v_apariciones <> 9 THEN
        RAISE EXCEPTION 'F03-02-0250 POSTCHECK: se esperaban 9 FOR NO KEY UPDATE, hay %', v_apariciones;
    END IF;
END
$postcheck$;

RESET ROLE;

COMMIT;
