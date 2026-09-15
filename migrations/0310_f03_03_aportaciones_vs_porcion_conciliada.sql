-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0310_f03_03_aportaciones_vs_porcion_conciliada.sql
-- Ruta: migrations/0310_f03_03_aportaciones_vs_porcion_conciliada.sql
-- Descripcion: FASE 03 REABIERTA / D-168 + D-169 + D-170 + D-171. Materializa
--   el DEFECTO 2: la invariante agregada que limita la suma de aportaciones
--   vinculadas a una conciliacion cuando las monedas son comparables.
--
--   PREDICADO (D-169, precisado por D-170). Para cada fila R de
--   hecho_movimientos_tesoreria:
--
--     moneda_hecho(R)  = hechos_financieros(R.hecho_id).moneda
--     moneda_cuenta(R) = cuentas(movimientos_tesoreria(R.movimiento_tesoreria_id).cuenta_id).moneda
--
--     SI moneda_hecho(R) = moneda_cuenta(R) ENTONCES
--         SUM(hap.importe | hap.hecho_movimiento_tesoreria_id = R.id) <= ABS(R.importe_asignado)
--
--   Es un MAXIMO, no una igualdad: 80 <= 100 es valido y el resto puede ser
--   financiacion no modelada. hap.importe es CHECK > 0 sin signo y
--   importe_asignado es firmado, de ahi el ABS solo a la derecha. Las
--   aportaciones con hecho_movimiento_tesoreria_id IS NULL quedan fuera.
--
--   D-170: la comparabilidad es propiedad del ESTADO FINAL de la transaccion,
--   no una caracteristica historica pegajosa. Una conciliacion que pasa de
--   multidivisa a comparable no queda prohibida por su historia; solo se
--   prohibe persistir un estado final invalido. En multidivisa NO se compara
--   nominalmente y NO se inventa conversion FX.
--
--   PRECONDICION 0300. La FK compuesta de 0300 garantiza
--   hap.hecho_id = hmt.hecho_id para toda aportacion vinculada, de modo que la
--   moneda del hecho aplicable a una conciliacion es inequivoca. Sin 0300 el
--   predicado ni siquiera estaria bien definido. No se duplica esa garantia en
--   logica procedimental (D-171 §10): vive en la FK y se comprueba por test.
--
--   LOCK ROOT (D-171 §1). hechos_financieros.id, con FOR NO KEY UPDATE y
--   ORDER BY id cuando hay varios. Es un PADRE FISICO real de
--   hecho_movimientos_tesoreria y de hecho_aportaciones_pago, de modo que se
--   respeta el criterio de F03-00-G-C (fila padre cuando existe padre adecuado)
--   y NO se crea una octava raiz advisory.
--
--   POR QUE NO BASTA EL MOVIMIENTO. Write-skew demostrado: T1 cambia
--   hechos_financieros.moneda y solo puede bloquear los movimientos de las
--   conciliaciones existentes en ese instante; T2 crea concurrentemente una
--   conciliacion nueva sobre OTRO movimiento y valida leyendo todavia la moneda
--   antigua. Los conjuntos de locks son disjuntos y ambas transacciones
--   confirman dejando un estado comparable e invalido. Bloquear el hecho
--   elimina ese skew porque los dos escritores que pueden alterar el predicado
--   del mismo hecho contienden sobre la misma fila padre.
--
--   FOR NO KEY UPDATE, no FOR UPDATE (D-114). hechos_financieros tiene muchas
--   hijas cuyas FK toman FOR KEY SHARE sobre su fila; FOR UPDATE chocaria con
--   ellas y reproduciria el defecto que D-114 corrigio. Ademas, las columnas
--   KEY de hechos_financieros son {id, owner_user_id}: un UPDATE de moneda es
--   NO KEY UPDATE y por tanto no bloquea el INSERT de hijas, solo la
--   validacion diferida de otra transaccion. Es exactamente la granularidad
--   buscada.
--
--   DEPENDENCIA DE CONCURRENCIA HEREDADA (D-171 §5). El caso
--   "UPDATE movimientos_tesoreria.cuenta_id frente a INSERT concurrente de HMT
--   sobre ese mismo movimiento" NO lo protege esta migration: lo protege el
--   anchor uq_movimientos_tesoreria__cuenta_anchor (cuenta_id, id) creado por
--   0220/D-099 para la reversion misma-cuenta. Al ser cuenta_id columna KEY, el
--   UPDATE toma un lock de tupla FOR UPDATE que conflictua con el FOR KEY SHARE
--   del INSERT de la HMT. 0310 DEPENDE de esa propiedad fisica; el precheck la
--   exige y test_038 la hace visible para que su eliminacion futura falle de
--   forma diagnosticable.
--
--   CANONICALIZACION DE Hs EN UN UNICO PUNTO (D-171 §4). Los cuatro triggers
--   entregan identificadores en bruto; fn_validar_aportaciones_conciliacion es
--   el unico lugar que elimina NULL, elimina duplicados y ordena ascendente.
--   Sin esa canonicalizacion, OLD.hecho_id = NEW.hecho_id daria cardinalidad 2
--   frente a ROW_COUNT 1 y produciria un falso error de VISIBILIDAD.
--
--   SECUENCIA DEL NUCLEO. (1) canonicalizar Hs; (2) bloquear todos los hechos
--   esperados con FOR NO KEY UPDATE ORDER BY id; (3) comprobar ROW_COUNT
--   exacto y fallar cerrado si falta alguno; (4) comprobar de forma fail-closed
--   que toda conciliacion de Hs resuelve su movimiento y su cuenta;
--   (5) releer el estado final y evaluar el predicado solo donde las monedas
--   son comparables. Los pasos 4 y 5 son sentencias SEPARADAS y POSTERIORES al
--   lock: bajo READ COMMITTED cada sentencia toma instantanea nueva.
--
--   ALCANCE DEL PASO 4 (K3, ratificado en revision). Es DEFENSA EN PROFUNDIDAD
--   DE RESOLUCION: impide que una conciliacion visible desaparezca en silencio
--   del GROUP BY porque su movimiento o su cuenta no resuelvan, que es el
--   patron de D-088. NO sustituye la integridad tenant, NO convierte 0310 en un
--   verificador general de relaciones cross-tenant y NO puede afirmarse que
--   detecte una HMT que la policy de RLS haya ocultado por completo. La
--   integridad tenant sigue perteneciendo a las FK, RLS, FORCE RLS y demas
--   contratos ya aprobados.
--
--   FAIL-CLOSED SIN RAMA DE VACUIDAD (D-171 §5/§6). Ningun trigger dispara en
--   DELETE: borrar una aportacion solo puede BAJAR la suma y nunca crea una
--   violacion nueva. Al no encolar comprobacion para DELETE, y siendo las FK
--   hap.hecho_id y hmt.hecho_id ON DELETE RESTRICT, el hecho DEBE existir
--   siempre que haya un disparo pendiente. Un hecho ausente en el paso de
--   bloqueo solo puede ser anomalia de contexto, y la respuesta es siempre
--   fallar. NO existe rama "no visible = probablemente borrado".
--
--   Limitacion declarada y aceptada: una transaccion que inserte una
--   aportacion, la borre y borre ademas el hecho sera rechazada por el disparo
--   ya encolado. Falla cerrado, no abierto. No se disena excepcion.
--
--   DIAGNOSTICO. Ante varias conciliaciones incumplidoras se aborta en la
--   primera; el recorrido ordena por r.id, de modo que el diagnostico es
--   estable dentro del mismo estado. La funcion es un validador de integridad,
--   no un informe de auditoria.
--
--   SIN SECURITY DEFINER. Las cinco tablas leidas son tenant-scoped del mismo
--   owner. No hay lectura cross-tenant legitima. Se mantiene el patron invoker
--   de los validadores existentes de F03.
--
--   DESPACHADOR. fn_check_aportaciones_conciliacion resuelve Hs mediante CASE
--   sobre TG_TABLE_NAME, sin SQL dinamico (F03-00-G-B prohibe el trigger
--   universal dinamico). OLD y NEW se usan SOLO para derivar identificadores,
--   nunca valores economicos: un trigger diferido FOR EACH ROW conserva la
--   instantanea de la fila en el momento de la sentencia, de modo que razonar
--   sobre sus valores haria el resultado dependiente del orden de sentencias.
--   Para hecho_aportaciones_pago y hecho_movimientos_tesoreria un UPDATE
--   revalida ambos extremos, NEW y OLD (D-125). Para hechos_financieros el
--   fan-out alcanza todas las conciliaciones del hecho y la comparabilidad se
--   evalua por conciliacion, no por hecho (D-170 §5). Para movimientos_tesoreria
--   el conjunto se deriva del estado ACTUAL de las conciliaciones que
--   referencian ese movimiento y puede abarcar varios hechos distintos.
--
--   CICLO RESIDUAL H<->M (D-171 §7). Los eventos sobre las tres primeras tablas
--   adquieren H y, si dispara ademas fn_check_hecho_mov_tesoreria_suma, M
--   despues. El UPDATE de cuenta_id retiene M por el propio DML y pide H
--   despues. El ciclo no es eliminable desde un trigger diferido. Queda como
--   40P01 residual bajo D-114/D-143/D-159: retry de la TRANSACCION COMPLETA en
--   el write-path, nunca retry parcial y nunca capturado dentro del trigger.
--   R7 lo mide. El orden alfabetico de nombres de trigger hace mas determinista
--   una parte del recorrido pero NO es fundamento de seguridad: la correccion
--   descansa en los locks y en la relectura del estado final.
--
--   CONTRATO FISICO. Tablas, columnas, FK, indices, UNIQUE, EXCLUDE, policies,
--   vistas y GRANTs NO cambian. Funciones 26 -> 28. Triggers no internos
--   54 -> 58. Constraint triggers 37 -> 41. De las ocho huellas D-111 deben
--   cambiar h2_constraints, h5_triggers y h6_funciones; h1, h3, h4, h7 y h8
--   deben permanecer.
--
-- Decision: D-169 (invariante) / D-170 (estado resultante) / D-171 (diseno)
-- Versión: 0.1.1  -- retirados los comentarios inline de los cuerpos $fn$ de
--   las dos funciones: prosrc participa en las huellas D-111 y el Working
--   Method v0.11 mantiene la regla heredada de B22. La explicacion tecnica se
--   conserva integra en esta cabecera y en los COMMENT ON FUNCTION, y el
--   postcheck comprueba que ningun prosrc de 0310 contiene comentarios. Se
--   precisa ademas el alcance del paso 4 (K3). Sin cambio de semantica.
--   v0.1.0: primera version entregada para revision; nunca aplicada.
-- ============================================================

BEGIN;

DO $precheck_0310$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-03-0310 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::pg_catalog.regclass
       AND k.conname = 'fk_hecho_aportaciones_pago__hecho_conciliacion'
       AND k.contype = 'f' AND k.convalidated;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta la FK compuesta de 0300 (precondicion de 0310);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.movimientos_tesoreria'::pg_catalog.regclass
       AND k.conname = 'uq_movimientos_tesoreria__cuenta_anchor'
       AND k.contype = 'u';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta uq_movimientos_tesoreria__cuenta_anchor; 0310 depende de el para serializar UPDATE de cuenta_id frente a INSERT de HMT;';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        v_rep := v_rep || pg_catalog.format(' FK del esquema = %s (esperadas 175 antes de 0310);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 26 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 26 antes de 0310);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 54 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 54 antes de 0310);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_aportaciones_conciliacion',
                         'fn_validar_aportaciones_conciliacion');
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' ya existen %s funciones de 0310;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM (
        SELECT r.id
          FROM gapto.hecho_movimientos_tesoreria r
          JOIN gapto.hechos_financieros      h ON h.id = r.hecho_id
          JOIN gapto.movimientos_tesoreria   m ON m.id = r.movimiento_tesoreria_id
          JOIN gapto.cuentas                 c ON c.id = m.cuenta_id
          JOIN gapto.hecho_aportaciones_pago a ON a.hecho_movimiento_tesoreria_id = r.id
         WHERE h.moneda = c.moneda
         GROUP BY r.id, r.importe_asignado
        HAVING pg_catalog.sum(a.importe) > pg_catalog.abs(r.importe_asignado)
      ) AS violaciones;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' conciliaciones que ya incumplen D-169 en moneda comparable=%s; requieren decision arquitectonica, no migration;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-03-0310 PRECHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-03-0310 PRECHECK: OK';
END;
$precheck_0310$;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ============================================================
-- 1) Nucleo: canonicalizacion + lock + relectura + evaluacion.
--    Cuerpo sin comentarios inline: prosrc participa en las huellas D-111.
--    La secuencia (1)..(5) queda documentada en la cabecera de la migration y
--    resumida en el COMMENT ON FUNCTION.
-- ============================================================
CREATE FUNCTION gapto.fn_validar_aportaciones_conciliacion(p_hechos uuid[])
RETURNS void AS $fn$
DECLARE
    v_hs         uuid[];
    v_bloqueados bigint;
    v_huerfanas  bigint;
    v_r          record;
BEGIN
    SELECT pg_catalog.array_agg(DISTINCT x ORDER BY x) INTO v_hs
      FROM pg_catalog.unnest(p_hechos) AS t(x)
     WHERE x IS NOT NULL;

    IF v_hs IS NULL OR pg_catalog.cardinality(v_hs) = 0 THEN
        RETURN;
    END IF;

    PERFORM 1
       FROM gapto.hechos_financieros h
      WHERE h.id = ANY (v_hs)
      ORDER BY h.id
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS v_bloqueados = ROW_COUNT;

    IF v_bloqueados <> pg_catalog.cardinality(v_hs) THEN
        RAISE EXCEPTION
            'hecho_aportaciones_pago: VISIBILIDAD - se esperaban % hechos y solo % son visibles/bloqueables al validar D-169 (contexto de tenant ausente o distinto del de la escritura)',
            pg_catalog.cardinality(v_hs), v_bloqueados;
    END IF;

    SELECT pg_catalog.count(*) INTO v_huerfanas
      FROM gapto.hecho_movimientos_tesoreria r
      LEFT JOIN gapto.movimientos_tesoreria m ON m.id = r.movimiento_tesoreria_id
      LEFT JOIN gapto.cuentas               c ON c.id = m.cuenta_id
     WHERE r.hecho_id = ANY (v_hs)
       AND (m.id IS NULL OR c.id IS NULL);
    IF v_huerfanas > 0 THEN
        RAISE EXCEPTION
            'hecho_aportaciones_pago: VISIBILIDAD - % conciliacion(es) sin movimiento o cuenta resolubles al validar D-169',
            v_huerfanas;
    END IF;

    FOR v_r IN
        SELECT r.id                               AS conciliacion_id,
               r.hecho_id                         AS hecho_id,
               pg_catalog.abs(r.importe_asignado) AS porcion,
               pg_catalog.sum(a.importe)          AS aportado,
               h.moneda                           AS moneda
          FROM gapto.hecho_movimientos_tesoreria r
          JOIN gapto.hechos_financieros      h ON h.id = r.hecho_id
          JOIN gapto.movimientos_tesoreria   m ON m.id = r.movimiento_tesoreria_id
          JOIN gapto.cuentas                 c ON c.id = m.cuenta_id
          JOIN gapto.hecho_aportaciones_pago a ON a.hecho_movimiento_tesoreria_id = r.id
         WHERE r.hecho_id = ANY (v_hs)
           AND h.moneda = c.moneda
         GROUP BY r.id, r.hecho_id, r.importe_asignado, h.moneda
        HAVING pg_catalog.sum(a.importe) > pg_catalog.abs(r.importe_asignado)
         ORDER BY r.id
    LOOP
        RAISE EXCEPTION
            'hecho_aportaciones_pago: la suma de aportaciones vinculadas a la conciliacion % del hecho % es % % y supera la porcion conciliada % % (D-169)',
            v_r.conciliacion_id, v_r.hecho_id, v_r.aportado, v_r.moneda,
            v_r.porcion, v_r.moneda;
    END LOOP;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_validar_aportaciones_conciliacion(uuid[]) IS
    'D-169/D-170/D-171. Nucleo de la invariante agregada SUM(aportaciones vinculadas) <= ABS(importe_asignado) en moneda comparable. Secuencia: (1) canonicaliza Hs sin NULL, sin duplicados y en orden ascendente, como unico punto del diseno; (2) bloquea todos los hechos esperados con FOR NO KEY UPDATE ORDER BY id, que es el lock root fisico aprobado; (3) exige ROW_COUNT exacto y falla cerrado como VISIBILIDAD si falta alguno, sin rama de vacuidad; (4) comprueba en sentencia separada que toda conciliacion de Hs resuelve movimiento y cuenta, como defensa en profundidad de resolucion que no sustituye la integridad tenant; (5) solo despues relee el estado final y evalua el predicado donde moneda_hecho = moneda_cuenta. En multidivisa no compara nominalmente ni infiere FX. Aborta en la primera conciliacion incumplidora, recorriendo por r.id.';

-- ============================================================
-- 2) Despachador de trigger. CASE sobre TG_TABLE_NAME, sin SQL dinamico.
--    Cuerpo sin comentarios inline por la misma razon de huellas.
-- ============================================================
CREATE FUNCTION gapto.fn_check_aportaciones_conciliacion()
RETURNS trigger AS $fn$
DECLARE
    v_hs uuid[];
BEGIN
    CASE TG_TABLE_NAME

        WHEN 'hecho_aportaciones_pago' THEN
            IF TG_OP = 'UPDATE' THEN
                v_hs := ARRAY[NEW.hecho_id, OLD.hecho_id];
            ELSE
                v_hs := ARRAY[NEW.hecho_id];
            END IF;

        WHEN 'hecho_movimientos_tesoreria' THEN
            IF TG_OP = 'UPDATE' THEN
                v_hs := ARRAY[NEW.hecho_id, OLD.hecho_id];
            ELSE
                v_hs := ARRAY[NEW.hecho_id];
            END IF;

        WHEN 'hechos_financieros' THEN
            v_hs := ARRAY[NEW.id];

        WHEN 'movimientos_tesoreria' THEN
            SELECT pg_catalog.array_agg(r.hecho_id) INTO v_hs
              FROM gapto.hecho_movimientos_tesoreria r
             WHERE r.movimiento_tesoreria_id = NEW.id;

        ELSE
            RAISE EXCEPTION 'fn_check_aportaciones_conciliacion: tabla no contemplada %', TG_TABLE_NAME;
    END CASE;

    PERFORM gapto.fn_validar_aportaciones_conciliacion(v_hs);
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_aportaciones_conciliacion() IS
    'D-169/D-170/D-171. Despachador por TG_TABLE_NAME de las cuatro superficies vivas de la invariante, sin SQL dinamico. OLD y NEW solo aportan identificadores, nunca valores economicos, porque un trigger diferido conserva la instantanea de la sentencia y razonar sobre sus valores haria el resultado dependiente del orden de sentencias. hecho_aportaciones_pago y hecho_movimientos_tesoreria revalidan NEW y OLD en un UPDATE. hechos_financieros revalida todas las conciliaciones del hecho, evaluando la comparabilidad por conciliacion. movimientos_tesoreria deriva del estado actual los hechos de las conciliaciones que lo referencian, que pueden ser varios. La canonicalizacion de Hs vive en fn_validar_aportaciones_conciliacion.';

-- ============================================================
-- 3) Cuatro constraint triggers diferidos sobre las superficies vivas.
--    Ninguno dispara en DELETE (D-171 §2).
--    INITIALLY DEFERRED permite construir un reparto legitimo en varios INSERT
--    y la correccion multi-fila atomica de D-170 §4.
-- ============================================================

CREATE CONSTRAINT TRIGGER trg_hecho_aportaciones_pago__conciliacion_suma
    AFTER INSERT OR UPDATE OF importe, hecho_movimiento_tesoreria_id, hecho_id
    ON gapto.hecho_aportaciones_pago
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_aportaciones_conciliacion();

-- El nombre ordena antes que trg_..__suma, lo que hace mas determinista el
-- recorrido H -> M; NO es fundamento de seguridad (D-171 §7).
CREATE CONSTRAINT TRIGGER trg_hecho_movimientos_tesoreria__aportaciones
    AFTER INSERT OR UPDATE OF importe_asignado, movimiento_tesoreria_id, hecho_id
    ON gapto.hecho_movimientos_tesoreria
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_aportaciones_conciliacion();

-- Sin guarda por valor: UPDATE OF moneda ya limita el disparo a las sentencias
-- que la mencionan, y comparar valores de una instantanea diferida violaria la
-- regla de usar OLD/NEW solo como identificadores.
CREATE CONSTRAINT TRIGGER trg_hechos_financieros__aportaciones_moneda
    AFTER UPDATE OF moneda
    ON gapto.hechos_financieros
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_aportaciones_conciliacion();

CREATE CONSTRAINT TRIGGER trg_movimientos_tesoreria__aportaciones_cuenta
    AFTER UPDATE OF cuenta_id
    ON gapto.movimientos_tesoreria
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_aportaciones_conciliacion();

RESET ROLE;

DO $postcheck_0310$
DECLARE
    v_n bigint;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_aportaciones_conciliacion',
                         'fn_validar_aportaciones_conciliacion')
       AND NOT p.prosecdef;
    IF v_n <> 2 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: funciones invoker de 0310 = % (esperadas 2)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_aportaciones_conciliacion',
                         'fn_validar_aportaciones_conciliacion')
       AND pg_catalog.strpos(p.prosrc, '--') > 0;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: % funcion(es) de 0310 conservan comentarios inline en prosrc; las huellas D-111 exigen cuerpos limpios', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE NOT t.tgisinternal AND t.tgconstraint <> 0
       AND t.tgdeferrable AND t.tginitdeferred
       AND t.tgname IN ('trg_hecho_aportaciones_pago__conciliacion_suma',
                        'trg_hecho_movimientos_tesoreria__aportaciones',
                        'trg_hechos_financieros__aportaciones_moneda',
                        'trg_movimientos_tesoreria__aportaciones_cuenta');
    IF v_n <> 4 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: constraint triggers diferidos de 0310 = % (esperados 4)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgname IN ('trg_hecho_aportaciones_pago__conciliacion_suma',
                        'trg_hecho_movimientos_tesoreria__aportaciones',
                        'trg_hechos_financieros__aportaciones_moneda',
                        'trg_movimientos_tesoreria__aportaciones_cuenta')
       AND (t.tgtype & 8) <> 0;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: % trigger(s) de 0310 disparan en DELETE; el diseno lo prohibe', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.movimientos_tesoreria'::pg_catalog.regclass
       AND k.conname = 'uq_movimientos_tesoreria__cuenta_anchor' AND k.contype = 'u';
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: uq_movimientos_tesoreria__cuenta_anchor ausente; 0310 depende de el';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: funciones = % (esperadas 28)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: triggers no internos = % (esperados 58)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 41 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: constraint triggers = % (esperados 41)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: FK del esquema = % (esperadas 175; 0310 no crea ninguna)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 285 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: indices = % (esperados 285; 0310 no crea ninguno)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        RAISE EXCEPTION 'F03-03-0310 POSTCHECK: policies = % (esperadas 82; 0310 no crea ninguna)', v_n;
    END IF;

    RAISE NOTICE 'F03-03-0310 POSTCHECK: OK';
END;
$postcheck_0310$;

COMMIT;
