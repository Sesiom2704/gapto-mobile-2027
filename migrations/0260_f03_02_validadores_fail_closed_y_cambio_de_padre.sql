-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0260_f03_02_validadores_fail_closed_y_cambio_de_padre.sql
-- Ruta: migrations/0260_f03_02_validadores_fail_closed_y_cambio_de_padre.sql
-- Descripcion: FASE 03. Primera correccion forward-only de los hallazgos de
--   integridad post-0250 (matriz F03-02 v0.2.0). No reabre F03-01.
--
--   1. FAIL-CLOSED (D-b). Nueve validadores salian sin comprobar cuando no
--      encontraban la fila padre, lo que bajo RLS confunde "no existe" con
--      "no es visible". Ahora, en INSERT/UPDATE, no encontrar el padre es un
--      error (VISIBILIDAD): la FK NOT NULL garantiza que existe, asi que no
--      verlo indica un contexto de tenant ausente o distinto del de la
--      escritura. En DELETE, un padre desaparecido deja la invariante vacia
--      (con FK RESTRICT no queda ninguna hija; en subtipos la FK es CASCADE y
--      el borrado de la entidad arrastra al subtipo). Se detecta con NOT FOUND
--      o EXISTS, nunca con el NULL de una columna. Contrato del backend: no
--      cambiar gapto.owner_user_id dentro de una transaccion. Se acepta el
--      falso positivo INSERT hija -> DELETE hija -> DELETE padre en la misma
--      transaccion.
--
--   2. CAMBIO DE PADRE (T2). En un UPDATE que cambia la FK de una hija, se
--      validan el padre nuevo y el antiguo, bloqueados en orden de uuid con
--      FOR NO KEY UPDATE. Afecta a participaciones (cuentas y entidades),
--      atribuciones, asignaciones de inversion, asignaciones de tesoreria y
--      subtipos de entidad.
--
--   3. H1. trg_hecho_efectos__atribucion_suma pasa a cubrir tambien INSERT:
--      un efecto COMPLETA no puede llegar al COMMIT sin que sus atribuciones
--      cuadren. Construir efecto y atribuciones en la misma transaccion sigue
--      siendo valido (validacion diferida, sobre los valores finales).
--
--   4. D-a. Se elimina el DEFAULT 'COMPLETA' de estado_atribucion: el estado
--      debe indicarse siempre; ninguna omision se convierte en afirmacion.
--
--   5. A7. fn_check_entidad_subtipo_unico exige ademas que la entidad no
--      tenga filas en tablas de subtipo distintas de la coherente con su
--      tipo, y bloquea la entidad con FOR NO KEY UPDATE.
--
--   SALVAGUARDAS. Precheck de huellas (vigentes tras 0250) y de estructura;
--   precheck de datos (efectos COMPLETA descuadrados, subtipos incoherentes),
--   concluyente solo si el rol que aplica tiene BYPASSRLS; postcheck de
--   huellas, trigger, default y modos de lock.
--
--   HUELLAS (md5 de prosrc):  vigente  ->  0260 (bytes)
--     fn_check_participacion_suma          d01fd963789d8adf4b29cbb007604414  ->  b76161555c227a8aa19c3ab513aa4687  3082
--     fn_check_atribucion_suma             1875c05dfd509221eb2acd2665ec3477  ->  31f04f601350a6dbc7baa3ec8919e980  2222
--     fn_check_inversion_asignacion_suma   9a59512f3e0109689af70e79e78159ee  ->  182087c02d004ca2c2f0d38bd00f10ff  1957
--     fn_check_hecho_mov_tesoreria_suma    693fa7086767b581a6bd45eadc8944c2  ->  2b9483c066e3f637f24d396babe27720  1670
--     fn_check_reversion_movimiento        859f7f7e9a5b0b518e6272c410bedf83  ->  00161f7875783230311834ca84e472e2  2208
--     fn_check_transferencia_estructura    a6c74336f91ddb4239914672cab01c97  ->  e956eb54ec62b7ac7b9bcf11ca3f107e  2392
--     fn_check_bolsa_prioridad             e0640d1e1af1a043cb5585ae69c4b89b  ->  a583bbd419cb337152617b0c19a1cc42  1395
--     fn_check_bolsa_prioridad_alcance     7d9abf8d58b812b88d8c58e9968a50fe  ->  7c876f1970c850e791af25226da520b1  1947
--     fn_check_entidad_subtipo_unico       fc39742d0d3efba50943c2e35fde3a83  ->  210cae8afdff0401c1225d258420dd80  2766
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_datos$
DECLARE
    v_bypass     boolean;
    v_efectos    integer;
    v_subtipos   integer;
BEGIN
    SELECT r.rolbypassrls INTO v_bypass FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT v_bypass THEN
        RAISE NOTICE 'F03-02-0260 PRECHECK DATOS: el rol % no tiene BYPASSRLS; el recuento no es concluyente y debe verificarse aparte', current_user;
        RETURN;
    END IF;

    SELECT pg_catalog.count(*) INTO v_efectos
      FROM gapto.hecho_efectos e
     WHERE e.estado_atribucion = 'COMPLETA'
       AND e.importe_delta <> (SELECT COALESCE(pg_catalog.sum(a.importe_atribuido), 0)
                                 FROM gapto.efecto_atribuciones a WHERE a.efecto_id = e.id);

    SELECT pg_catalog.count(*) INTO v_subtipos
      FROM gapto.entidades en
     WHERE (SELECT pg_catalog.count(*) FROM gapto.propiedades s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.contratos s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.servicios s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.financiaciones s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.inversiones s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.derechos_obligaciones_financieras s WHERE s.entidad_id = en.id)
         + (SELECT pg_catalog.count(*) FROM gapto.contextos s WHERE s.entidad_id = en.id) <> 1;

    IF v_efectos > 0 OR v_subtipos > 0 THEN
        RAISE EXCEPTION 'F03-02-0260 PRECHECK DATOS: % efectos COMPLETA descuadrados y % entidades con subtipos incoherentes',
            v_efectos, v_subtipos;
    END IF;
END
$precheck_datos$;

SET ROLE gapto_owner;

DO $precheck$
DECLARE
    v_divergentes text;
    v_tipo        integer;
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
        ('fn_check_bolsa_prioridad_alcance', '7d9abf8d58b812b88d8c58e9968a50fe'),
        ('fn_check_entidad_subtipo_unico', 'fc39742d0d3efba50943c2e35fde3a83')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
             ON p.proname = e.nombre
            AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL
        OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0260 PRECHECK: prosrc distinto del vigente tras 0250 en: %', v_divergentes;
    END IF;

    SELECT t.tgtype INTO v_tipo
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid = 'gapto.hecho_efectos'::pg_catalog.regclass
       AND t.tgname = 'trg_hecho_efectos__atribucion_suma';
    IF v_tipo IS NULL OR (v_tipo & 4) <> 0 THEN
        RAISE EXCEPTION 'F03-02-0260 PRECHECK: trg_hecho_efectos__atribucion_suma ausente o ya cubre INSERT';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attrdef d
                     JOIN pg_catalog.pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
                    WHERE a.attrelid = 'gapto.hecho_efectos'::pg_catalog.regclass
                      AND a.attname = 'estado_atribucion') THEN
        RAISE EXCEPTION 'F03-02-0260 PRECHECK: estado_atribucion ya no tiene DEFAULT';
    END IF;
END
$precheck$;

ALTER TABLE gapto.hecho_efectos ALTER COLUMN estado_atribucion DROP DEFAULT;

CREATE OR REPLACE FUNCTION gapto.fn_check_participacion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_fk_col       text := TG_ARGV[0];
    v_parent_table text := TG_ARGV[1];
    v_nuevo        uuid;
    v_viejo        uuid;
    v_padre        uuid;
    v_existe       boolean;
    v_filas        integer;
    v_min_suma     numeric;
    v_max_suma     numeric;
    v_sql          text;
BEGIN
    IF TG_OP <> 'DELETE' THEN
        EXECUTE format('SELECT ($1).%I', v_fk_col) INTO v_nuevo USING NEW;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        EXECUTE format('SELECT ($1).%I', v_fk_col) INTO v_viejo USING OLD;
    END IF;

    FOR v_padre IN
        SELECT DISTINCT p FROM unnest(ARRAY[v_nuevo, v_viejo]) AS p
         WHERE p IS NOT NULL ORDER BY p
    LOOP
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM gapto.%I WHERE id = $1 FOR NO KEY UPDATE)',
                       v_parent_table)
           INTO v_existe USING v_padre;
        IF NOT v_existe THEN
            IF v_padre = v_nuevo THEN
                RAISE EXCEPTION
                    'gapto.%: VISIBILIDAD - el padre gapto.% id=% no es visible al validar la participacion (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_parent_table, v_padre;
            END IF;
            CONTINUE;
        END IF;

        EXECUTE format('SELECT count(*) FROM gapto.%I WHERE %I = $1', TG_TABLE_NAME, v_fk_col)
           INTO v_filas USING v_padre;
        IF v_filas = 0 THEN
            CONTINUE;
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
        EXECUTE v_sql INTO v_min_suma, v_max_suma USING v_padre;

        IF v_min_suma IS NULL THEN
            CONTINUE;
        END IF;

        IF v_max_suma <> 100 OR v_min_suma <> 100 THEN
            RAISE EXCEPTION
                'gapto.%: la participacion debe sumar exactamente 100 en todo instante cubierto para %=% (minimo encontrado=%, maximo encontrado=%)',
                TG_TABLE_NAME, v_fk_col, v_padre, v_min_suma, v_max_suma;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_atribucion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_nuevo         uuid;
    v_viejo         uuid;
    v_efecto_id     uuid;
    v_importe_delta numeric;
    v_estado        varchar;
    v_suma          numeric;
BEGIN
    IF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_nuevo := NEW.id;
    ELSE
        IF TG_OP <> 'DELETE' THEN
            v_nuevo := NEW.efecto_id;
        END IF;
        IF TG_OP <> 'INSERT' THEN
            v_viejo := OLD.efecto_id;
        END IF;
    END IF;

    FOR v_efecto_id IN
        SELECT DISTINCT e FROM unnest(ARRAY[v_nuevo, v_viejo]) AS e
         WHERE e IS NOT NULL ORDER BY e
    LOOP
        SELECT importe_delta, estado_atribucion INTO v_importe_delta, v_estado
          FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_efecto_id = v_nuevo THEN
                RAISE EXCEPTION 'gapto.%: VISIBILIDAD - el efecto % no es visible al validar la atribucion (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_efecto_id;
            END IF;
            CONTINUE;
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
    END LOOP;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_inversion_asignacion_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_nuevo         uuid;
    v_viejo         uuid;
    v_efecto_id     uuid;
    v_importe_delta numeric;
    v_tipo_efecto   varchar;
    v_suma          numeric;
BEGIN
    IF TG_OP <> 'DELETE' THEN
        v_nuevo := NEW.efecto_inversion_id;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        v_viejo := OLD.efecto_inversion_id;
    END IF;

    FOR v_efecto_id IN
        SELECT DISTINCT e FROM unnest(ARRAY[v_nuevo, v_viejo]) AS e
         WHERE e IS NOT NULL ORDER BY e
    LOOP
        SELECT importe_delta, tipo_efecto INTO v_importe_delta, v_tipo_efecto
          FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_efecto_id = v_nuevo THEN
                RAISE EXCEPTION 'inversion_asignaciones_efecto: VISIBILIDAD - el efecto % no es visible al validar la asignacion (contexto de tenant ausente o distinto del de la escritura)',
                    v_efecto_id;
            END IF;
            CONTINUE;
        END IF;

        IF v_efecto_id = v_nuevo AND v_tipo_efecto <> 'INVERSION' THEN
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
    END LOOP;

    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_nuevo         uuid;
    v_viejo         uuid;
    v_movimiento_id uuid;
    v_importe       numeric;
    v_suma          numeric;
BEGIN
    IF TG_OP <> 'DELETE' THEN
        v_nuevo := NEW.movimiento_tesoreria_id;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        v_viejo := OLD.movimiento_tesoreria_id;
    END IF;

    FOR v_movimiento_id IN
        SELECT DISTINCT m FROM unnest(ARRAY[v_nuevo, v_viejo]) AS m
         WHERE m IS NOT NULL ORDER BY m
    LOOP
        SELECT importe INTO v_importe FROM gapto.movimientos_tesoreria WHERE id = v_movimiento_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_movimiento_id = v_nuevo THEN
                RAISE EXCEPTION 'hecho_movimientos_tesoreria: VISIBILIDAD - el movimiento % no es visible al validar la asignacion (contexto de tenant ausente o distinto del de la escritura)',
                    v_movimiento_id;
            END IF;
            CONTINUE;
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
    END LOOP;

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
    IF NOT FOUND THEN
        RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - el movimiento original % no es visible al validar la reversion (contexto de tenant ausente o distinto del de la escritura)',
            NEW.reversion_de_movimiento_id;
    END IF;

    SELECT c.owner_user_id, c.moneda INTO v_nuevo_owner, v_nueva_moneda
      FROM gapto.cuentas c WHERE c.id = NEW.cuenta_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - la cuenta % de la reversion no es visible al validarla (contexto de tenant ausente o distinto del de la escritura)',
            NEW.cuenta_id;
    END IF;

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
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferencias: VISIBILIDAD - el movimiento de salida % no es visible al validar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
            NEW.movimiento_salida_id;
    END IF;

    SELECT m.importe, m.cuenta_id, c.owner_user_id, c.moneda
      INTO v_entrada
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.movimiento_entrada_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferencias: VISIBILIDAD - el movimiento de entrada % no es visible al validar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
            NEW.movimiento_entrada_id;
    END IF;

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
    IF NOT FOUND THEN
        RAISE EXCEPTION 'presupuesto_lineas: VISIBILIDAD - el presupuesto % no es visible al validar la BOLSA % (contexto de tenant ausente o distinto del de la escritura)',
            NEW.presupuesto_id, NEW.id;
    END IF;

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
    v_linea_id := NEW.presupuesto_linea_id;

    SELECT l.presupuesto_id, l.tipo_linea, l.prioridad_consumo
      INTO v_presupuesto, v_tipo, v_prioridad
      FROM gapto.presupuesto_lineas l
     WHERE l.id = v_linea_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'presupuesto_linea_alcances: VISIBILIDAD - la linea % no es visible al validar el alcance (contexto de tenant ausente o distinto del de la escritura)',
            v_linea_id;
    END IF;

    IF v_tipo <> 'BOLSA' THEN
        RETURN NULL;
    END IF;

    PERFORM 1 FROM gapto.presupuestos WHERE id = v_presupuesto FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'presupuesto_linea_alcances: VISIBILIDAD - el presupuesto % no es visible al validar el alcance (contexto de tenant ausente o distinto del de la escritura)',
            v_presupuesto;
    END IF;

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

CREATE OR REPLACE FUNCTION gapto.fn_check_entidad_subtipo_unico()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_nuevo     uuid;
    v_viejo     uuid;
    v_id        uuid;
    v_tipo      varchar;
    v_coherente integer;
    v_total     integer;
BEGIN
    IF TG_TABLE_NAME = 'entidades' THEN
        v_nuevo := NEW.id;
    ELSE
        IF TG_OP <> 'DELETE' THEN
            v_nuevo := NEW.entidad_id;
        END IF;
        IF TG_OP <> 'INSERT' THEN
            v_viejo := OLD.entidad_id;
        END IF;
    END IF;

    FOR v_id IN
        SELECT DISTINCT e FROM unnest(ARRAY[v_nuevo, v_viejo]) AS e
         WHERE e IS NOT NULL ORDER BY e
    LOOP
        SELECT tipo_entidad INTO v_tipo FROM gapto.entidades WHERE id = v_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_id = v_nuevo THEN
                RAISE EXCEPTION 'gapto.%: VISIBILIDAD - la entidad % no es visible al validar su subtipo (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_id;
            END IF;
            CONTINUE;
        END IF;

        v_coherente := CASE v_tipo
            WHEN 'PROPIEDAD'          THEN (SELECT count(*) FROM gapto.propiedades WHERE entidad_id = v_id)
            WHEN 'CONTRATO'           THEN (SELECT count(*) FROM gapto.contratos WHERE entidad_id = v_id)
            WHEN 'SERVICIO'           THEN (SELECT count(*) FROM gapto.servicios WHERE entidad_id = v_id)
            WHEN 'FINANCIACION'       THEN (SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = v_id)
            WHEN 'INVERSION'          THEN (SELECT count(*) FROM gapto.inversiones WHERE entidad_id = v_id)
            WHEN 'DERECHO_OBLIGACION' THEN (SELECT count(*) FROM gapto.derechos_obligaciones_financieras WHERE entidad_id = v_id)
            WHEN 'CONTEXTO'           THEN (SELECT count(*) FROM gapto.contextos WHERE entidad_id = v_id)
            ELSE 0
        END;

        v_total := (SELECT count(*) FROM gapto.propiedades WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.contratos WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.servicios WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.inversiones WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.derechos_obligaciones_financieras WHERE entidad_id = v_id)
                 + (SELECT count(*) FROM gapto.contextos WHERE entidad_id = v_id);

        IF v_coherente <> 1 OR v_total <> 1 THEN
            RAISE EXCEPTION 'entidades: la entidad % (tipo=%) debe tener exactamente un subtipo y ha de ser el coherente con su tipo (coherentes=%, total en tablas de subtipo=%)',
                v_id, v_tipo, v_coherente, v_total;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$function$;

DROP TRIGGER trg_hecho_efectos__atribucion_suma ON gapto.hecho_efectos;

CREATE CONSTRAINT TRIGGER trg_hecho_efectos__atribucion_suma
    AFTER INSERT OR UPDATE OF importe_delta, estado_atribucion ON gapto.hecho_efectos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION gapto.fn_check_atribucion_suma();

DO $postcheck$
DECLARE
    v_divergentes text;
    v_con_update  text;
    v_no_key      integer;
    v_tipo        integer;
    v_diferido    boolean;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre)
      INTO v_divergentes
      FROM (VALUES
        ('fn_check_participacion_suma', 'b76161555c227a8aa19c3ab513aa4687'),
        ('fn_check_atribucion_suma', '31f04f601350a6dbc7baa3ec8919e980'),
        ('fn_check_inversion_asignacion_suma', '182087c02d004ca2c2f0d38bd00f10ff'),
        ('fn_check_hecho_mov_tesoreria_suma', '2b9483c066e3f637f24d396babe27720'),
        ('fn_check_reversion_movimiento', '00161f7875783230311834ca84e472e2'),
        ('fn_check_transferencia_estructura', 'e956eb54ec62b7ac7b9bcf11ca3f107e'),
        ('fn_check_bolsa_prioridad', 'a583bbd419cb337152617b0c19a1cc42'),
        ('fn_check_bolsa_prioridad_alcance', '7c876f1970c850e791af25226da520b1'),
        ('fn_check_entidad_subtipo_unico', '210cae8afdff0401c1225d258420dd80')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
             ON p.proname = e.nombre
            AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL
        OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0260 POSTCHECK: huella inesperada en: %', v_divergentes;
    END IF;

    SELECT pg_catalog.string_agg(p.proname, ', ' ORDER BY p.proname) INTO v_con_update
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.prosrc ~* 'for\s+update';
    IF v_con_update IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0260 POSTCHECK: funciones con FOR UPDATE: %', v_con_update;
    END IF;

    SELECT pg_catalog.sum((SELECT pg_catalog.count(*)
                             FROM pg_catalog.regexp_matches(p.prosrc, 'for\s+no\s+key\s+update', 'gi')))
      INTO v_no_key
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_no_key <> 10 THEN
        RAISE EXCEPTION 'F03-02-0260 POSTCHECK: se esperaban 10 FOR NO KEY UPDATE, hay %', v_no_key;
    END IF;

    SELECT t.tgtype, t.tgdeferrable AND t.tginitdeferred INTO v_tipo, v_diferido
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid = 'gapto.hecho_efectos'::pg_catalog.regclass
       AND t.tgname = 'trg_hecho_efectos__atribucion_suma';
    IF v_tipo IS NULL OR (v_tipo & 4) = 0 OR (v_tipo & 16) = 0 OR NOT v_diferido THEN
        RAISE EXCEPTION 'F03-02-0260 POSTCHECK: el trigger de efectos no cubre INSERT y UPDATE diferidos';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_attrdef d
                 JOIN pg_catalog.pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
                WHERE a.attrelid = 'gapto.hecho_efectos'::pg_catalog.regclass
                  AND a.attname = 'estado_atribucion') THEN
        RAISE EXCEPTION 'F03-02-0260 POSTCHECK: estado_atribucion conserva un DEFAULT';
    END IF;
END
$postcheck$;

RESET ROLE;

COMMIT;
