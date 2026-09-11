-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0280_f03_02_aciclicidad_y_cadenas.sql
-- Ruta: migrations/0280_f03_02_aciclicidad_y_cadenas.sql
-- Descripcion: FASE 03 / F03-02. Correccion forward-only posterior a 0270:
--   aciclicidad y estructuras dirigidas. No reabre F03-01 ni edita la cadena
--   congelada. Queda fuera: BOLSA (D-121), reparenting frente a BOLSA
--   (D-122), eventos de presupuesto_lineas (0285) e inversion principal
--   (D-080, 0290).
--
--   1. D-123 en cuatro arboles: categorias_financieras.parent_id,
--      clasificaciones_tercero.parent_id, inversiones.inversion_padre_entidad_id
--      y regiones.parent_region_id. Funcion nueva gapto.fn_check_jerarquia_aciclica
--      (una rama estatica por tabla) y CONSTRAINT TRIGGER diferido por tabla
--      AFTER INSERT OR UPDATE OF <padre>. Orden: leer el owner de la fila
--      (NOT FOUND = VISIBILIDAD) -> pg_advisory_xact_lock(hashtext('gapto:<ARBOL>'),
--      hashtext(owner)) -> recorrido ascendente desde el padre ACTUAL de la
--      fila (estado final, nunca NEW) con clausula CYCLE, que termina aunque
--      exista un ciclo previo -> rechazo si el recorrido alcanza la propia fila.
--      Scopes: categorias y clasificaciones por owner_user_id; inversiones por
--      el owner de su entidad; regiones con la clave global (REGIONES, GLOBAL).
--      Desaparecen fn_prevent_self_referencing_cycle (BEFORE inmediato, sin
--      lock, UNION ALL sin guarda) y sus seis triggers trg_*__no_ciclo, que
--      tambien cubrian presupuestos y cierres (ver punto 4).
--
--   2. PARTE_DE (extension aprobada de D-123). Funcion nueva
--      gapto.fn_check_hecho_parte_de_aciclico y CONSTRAINT TRIGGER diferido
--      AFTER INSERT OR UPDATE OF hecho_origen_id, hecho_destino_id,
--      tipo_relacion ON hecho_relaciones. Solo actua si el tipo final es
--      PARTE_DE (PARTE_DE -> otro tipo retira la arista). Lee los owners de
--      los dos extremos (NOT FOUND = VISIBILIDAD), bloquea los scopes
--      (HECHOS_PARTE_DE, owner) en orden de uuid, exige mismo owner como
--      invariante de BD (tambien con BYPASSRLS) y recorre con CYCLE desde el
--      destino: hay ciclo si alcanza el origen. Los demas tipos no se tocan.
--
--   3. Reversiones de profundidad 1. fn_check_reversion_movimiento exige que
--      el original sea raiz (sin reversion_de_movimiento_id propio), aunque la
--      reversion este ANULADA, y que un movimiento que ya tiene reversiones
--      (ACTIVAS o ANULADAS) no pase a ser reversion. Se serializa con el
--      FOR NO KEY UPDATE existente sobre el original y con el lock de fila del
--      UPDATE del movimiento que cambia; sin advisory lock.
--
--   4. Cadenas de sustitucion (canon F03-00 G-B no materializado; B.6
--      aprobado). Funcion nueva gapto.fn_check_cadena_sustitucion y CONSTRAINT
--      TRIGGER diferido por tabla AFTER INSERT OR UPDATE OF las columnas de
--      identidad, version y reemplazo. Si X reemplaza a Y: mismo owner,
--      periodo_desde y periodo_hasta (presupuestos: tambien moneda y
--      perspectiva) y version de X estrictamente mayor que la de Y (sin exigir
--      +1). Revalida sobre el estado final la arista con el predecesor y la
--      arista con el sucesor directo. Sin recorrido CYCLE (B.6): con versiones
--      NOT NULL la monotonia estricta hace imposible un ciclo. El advisory lock
--      (PRESUPUESTOS|CIERRES, owner) serializa la revalidacion frente al
--      write-skew entre el UPDATE del predecesor y el INSERT del sucesor.
--      Declarativo: uq_presupuestos__identidad_version (identidad versionada,
--      equivalente a la de cierres) y uq_presupuestos__reemplaza /
--      uq_cierres_mensuales__reemplaza (sin bifurcaciones; los NULL, que son
--      raices, se repiten). Sin reglas estado<->cadena.
--
--   T1: una fila no visible al validar es VISIBILIDAD (falso positivo aceptado
--   por precedente: INSERT/UPDATE y DELETE de la misma fila en la misma
--   transaccion). T2: quitar o mover una arista no puede invalidar al padre o
--   predecesor antiguo (ninguna regla exige hijo ni sucesor): no se revalida,
--   mutante equivalente documentado. SECURITY INVOKER, VOLATILE, sin
--   comentarios en los cuerpos. Unica excepcion FOR UPDATE: R-MON.
--
--   CONTRATO: funciones 19 -> 21; triggers no internos 39 -> 40; constraint
--   triggers 23 -> 30; UNIQUE 37 -> 40.
--
--   HUELLAS (md5 de prosrc, bytes):
--     fn_check_reversion_movimiento      91a33cb088ab4ff8d9c56c29fc3d12c2 (0270) -> bd4ab19984492486f595cb539f78d263  3057
--     fn_check_jerarquia_aciclica        (nueva) -> 7fc289a080c5d9c0b2c731c69399d79c  3903
--     fn_check_hecho_parte_de_aciclico   (nueva) -> 0bc045230c00b7857343c9c3d99ce7ad  2060
--     fn_check_cadena_sustitucion        (nueva) -> d8b89d79f5907f6690d0c31cee7ddd54  5357
--     fn_prevent_self_referencing_cycle  7aa0d183c6260d27e1bd0dd981d4de81 -> eliminada
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_datos$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT v_bypass THEN
        RAISE NOTICE 'F03-02-0280 PRECHECK DATOS: NO CONCLUYENTE, el rol % no tiene BYPASSRLS', current_user;
        RETURN;
    END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT id, parent_id FROM gapto.categorias_financieras WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.parent_id FROM a JOIN gapto.categorias_financieras t ON t.id = a.n WHERE t.parent_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_categorias=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT id, parent_id FROM gapto.clasificaciones_tercero WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.parent_id FROM a JOIN gapto.clasificaciones_tercero t ON t.id = a.n WHERE t.parent_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_clasificaciones=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT entidad_id, inversion_padre_entidad_id FROM gapto.inversiones WHERE inversion_padre_entidad_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.inversion_padre_entidad_id FROM a JOIN gapto.inversiones t ON t.entidad_id = a.n
         WHERE t.inversion_padre_entidad_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_inversiones=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.inversiones i
      JOIN gapto.entidades e ON e.id = i.entidad_id
      JOIN gapto.entidades p ON p.id = i.inversion_padre_entidad_id
     WHERE e.owner_user_id <> p.owner_user_id;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' inversiones_padre_otro_owner=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT id, parent_region_id FROM gapto.regiones WHERE parent_region_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.parent_region_id FROM a JOIN gapto.regiones t ON t.id = a.n WHERE t.parent_region_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_regiones=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT hecho_origen_id, hecho_destino_id FROM gapto.hecho_relaciones WHERE tipo_relacion = 'PARTE_DE'
        UNION ALL
        SELECT a.s, r.hecho_destino_id FROM a JOIN gapto.hecho_relaciones r
            ON r.hecho_origen_id = a.n AND r.tipo_relacion = 'PARTE_DE'
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_parte_de=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.hecho_relaciones r
      JOIN gapto.hechos_financieros o ON o.id = r.hecho_origen_id
      JOIN gapto.hechos_financieros d ON d.id = r.hecho_destino_id
     WHERE r.tipo_relacion = 'PARTE_DE' AND o.owner_user_id <> d.owner_user_id;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' parte_de_otro_owner=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.movimientos_tesoreria m
     WHERE m.reversion_de_movimiento_id IS NOT NULL
       AND (EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria o
                     WHERE o.id = m.reversion_de_movimiento_id AND o.reversion_de_movimiento_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria h WHERE h.reversion_de_movimiento_id = m.id));
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' reversiones_profundidad_mayor_1=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.presupuestos x
      JOIN gapto.presupuestos y ON y.id = x.reemplaza_presupuesto_id
     WHERE (x.owner_user_id, x.periodo_desde, x.periodo_hasta, x.moneda, x.perspectiva)
           IS DISTINCT FROM (y.owner_user_id, y.periodo_desde, y.periodo_hasta, y.moneda, y.perspectiva)
        OR x.version_presupuesto <= y.version_presupuesto;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' presupuestos_arista_invalida=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM (
        SELECT 1 FROM gapto.presupuestos
         GROUP BY owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva, version_presupuesto
        HAVING pg_catalog.count(*) > 1) z;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' presupuestos_identidad_duplicada=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM (
        SELECT 1 FROM gapto.presupuestos WHERE reemplaza_presupuesto_id IS NOT NULL
         GROUP BY reemplaza_presupuesto_id HAVING pg_catalog.count(*) > 1) z;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' presupuestos_bifurcaciones=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT id, reemplaza_presupuesto_id FROM gapto.presupuestos WHERE reemplaza_presupuesto_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.reemplaza_presupuesto_id FROM a JOIN gapto.presupuestos t ON t.id = a.n
         WHERE t.reemplaza_presupuesto_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_presupuestos=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.cierres_mensuales x
      JOIN gapto.cierres_mensuales y ON y.id = x.reemplaza_cierre_id
     WHERE (x.owner_user_id, x.periodo_desde, x.periodo_hasta)
           IS DISTINCT FROM (y.owner_user_id, y.periodo_desde, y.periodo_hasta)
        OR x.version_cierre <= y.version_cierre;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' cierres_arista_invalida=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM (
        SELECT 1 FROM gapto.cierres_mensuales WHERE reemplaza_cierre_id IS NOT NULL
         GROUP BY reemplaza_cierre_id HAVING pg_catalog.count(*) > 1) z;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' cierres_bifurcaciones=%s', v_n); END IF;

    WITH RECURSIVE a(s, n) AS (
        SELECT id, reemplaza_cierre_id FROM gapto.cierres_mensuales WHERE reemplaza_cierre_id IS NOT NULL
        UNION ALL
        SELECT a.s, t.reemplaza_cierre_id FROM a JOIN gapto.cierres_mensuales t ON t.id = a.n
         WHERE t.reemplaza_cierre_id IS NOT NULL
    ) CYCLE n SET es_ciclo USING ruta
    SELECT pg_catalog.count(DISTINCT s) INTO v_n FROM a WHERE n = s;
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ciclos_cierres=%s', v_n); END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK DATOS: datos que ya violan invariantes de 0280:%', v_rep;
    END IF;
END
$precheck_datos$;

SET ROLE gapto_owner;

DO $precheck$
DECLARE
    v_n integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
                    WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
                      AND p.proname = 'fn_check_reversion_movimiento'
                      AND pg_catalog.md5(p.prosrc) = '91a33cb088ab4ff8d9c56c29fc3d12c2') THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: fn_check_reversion_movimiento no tiene la huella de 0270';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
                    WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
                      AND p.proname = 'fn_prevent_self_referencing_cycle'
                      AND pg_catalog.md5(p.prosrc) = '7aa0d183c6260d27e1bd0dd981d4de81') THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: fn_prevent_self_referencing_cycle ausente o con huella distinta';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
     WHERE t.tgfoid = 'gapto.fn_prevent_self_referencing_cycle()'::pg_catalog.regprocedure AND NOT t.tgisinternal;
    IF v_n <> 6 THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: se esperaban 6 triggers de ciclo antiguos, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_jerarquia_aciclica', 'fn_check_hecho_parte_de_aciclico', 'fn_check_cadena_sustitucion');
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: ya existen % funciones de 0280', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_constraint k
     WHERE k.conname IN ('uq_presupuestos__identidad_version', 'uq_presupuestos__reemplaza', 'uq_cierres_mensuales__reemplaza');
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: ya existen % UNIQUE de 0280', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 19 THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: se esperaban 19 funciones, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 39 THEN
        RAISE EXCEPTION 'F03-02-0280 PRECHECK: se esperaban 39 triggers no internos, hay %', v_n;
    END IF;
END
$precheck$;

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

    SELECT m.importe, m.estado, m.reversion_de_movimiento_id, c.owner_user_id, c.moneda
      INTO v_original
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.reversion_de_movimiento_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - el movimiento original % no es visible al validar la reversion (contexto de tenant ausente o distinto del de la escritura)',
            NEW.reversion_de_movimiento_id;
    END IF;

    IF v_original.reversion_de_movimiento_id IS NOT NULL THEN
        RAISE EXCEPTION 'movimientos_tesoreria: el movimiento % es a su vez una reversion; una reversion solo puede apuntar a un movimiento raiz (profundidad 1)',
            NEW.reversion_de_movimiento_id;
    END IF;
    IF EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria h WHERE h.reversion_de_movimiento_id = NEW.id) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: el movimiento % tiene reversiones y no puede ser a su vez una reversion (profundidad 1)',
            NEW.id;
    END IF;

    IF NEW.estado = 'ACTIVO' AND v_original.estado <> 'ACTIVO' THEN
        RAISE EXCEPTION 'movimientos_tesoreria: una reversion ACTIVA no puede apuntar al movimiento ANULADO % (D-119/T6)',
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

CREATE FUNCTION gapto.fn_check_jerarquia_aciclica()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_owner uuid;
    v_ciclo boolean;
BEGIN
    IF TG_TABLE_NAME = 'categorias_financieras' THEN
        SELECT owner_user_id INTO v_owner FROM gapto.categorias_financieras WHERE id = NEW.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'categorias_financieras: VISIBILIDAD - la categoria % no es visible al validar la jerarquia (contexto de tenant ausente o distinto del de la escritura)', NEW.id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'), hashtext(v_owner::text));
        WITH RECURSIVE a(n) AS (
            SELECT t.parent_id FROM gapto.categorias_financieras t WHERE t.id = NEW.id AND t.parent_id IS NOT NULL
            UNION ALL
            SELECT t.parent_id FROM a JOIN gapto.categorias_financieras t ON t.id = a.n WHERE t.parent_id IS NOT NULL
        ) CYCLE n SET es_ciclo USING ruta
        SELECT EXISTS (SELECT 1 FROM a WHERE a.n = NEW.id) INTO v_ciclo;
    ELSIF TG_TABLE_NAME = 'clasificaciones_tercero' THEN
        SELECT owner_user_id INTO v_owner FROM gapto.clasificaciones_tercero WHERE id = NEW.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'clasificaciones_tercero: VISIBILIDAD - la clasificacion % no es visible al validar la jerarquia (contexto de tenant ausente o distinto del de la escritura)', NEW.id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:CLASIFICACIONES'), hashtext(v_owner::text));
        WITH RECURSIVE a(n) AS (
            SELECT t.parent_id FROM gapto.clasificaciones_tercero t WHERE t.id = NEW.id AND t.parent_id IS NOT NULL
            UNION ALL
            SELECT t.parent_id FROM a JOIN gapto.clasificaciones_tercero t ON t.id = a.n WHERE t.parent_id IS NOT NULL
        ) CYCLE n SET es_ciclo USING ruta
        SELECT EXISTS (SELECT 1 FROM a WHERE a.n = NEW.id) INTO v_ciclo;
    ELSIF TG_TABLE_NAME = 'inversiones' THEN
        SELECT e.owner_user_id INTO v_owner
          FROM gapto.inversiones i JOIN gapto.entidades e ON e.id = i.entidad_id
         WHERE i.entidad_id = NEW.entidad_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'inversiones: VISIBILIDAD - la inversion % no es visible al validar la jerarquia (contexto de tenant ausente o distinto del de la escritura)', NEW.entidad_id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(v_owner::text));
        WITH RECURSIVE a(n) AS (
            SELECT t.inversion_padre_entidad_id FROM gapto.inversiones t
             WHERE t.entidad_id = NEW.entidad_id AND t.inversion_padre_entidad_id IS NOT NULL
            UNION ALL
            SELECT t.inversion_padre_entidad_id FROM a JOIN gapto.inversiones t ON t.entidad_id = a.n
             WHERE t.inversion_padre_entidad_id IS NOT NULL
        ) CYCLE n SET es_ciclo USING ruta
        SELECT EXISTS (SELECT 1 FROM a WHERE a.n = NEW.entidad_id) INTO v_ciclo;
    ELSIF TG_TABLE_NAME = 'regiones' THEN
        PERFORM 1 FROM gapto.regiones WHERE id = NEW.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'regiones: VISIBILIDAD - la region % no es visible al validar la jerarquia', NEW.id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:REGIONES'), hashtext('GLOBAL'));
        WITH RECURSIVE a(n) AS (
            SELECT t.parent_region_id FROM gapto.regiones t WHERE t.id = NEW.id AND t.parent_region_id IS NOT NULL
            UNION ALL
            SELECT t.parent_region_id FROM a JOIN gapto.regiones t ON t.id = a.n WHERE t.parent_region_id IS NOT NULL
        ) CYCLE n SET es_ciclo USING ruta
        SELECT EXISTS (SELECT 1 FROM a WHERE a.n = NEW.id) INTO v_ciclo;
    ELSE
        RAISE EXCEPTION 'fn_check_jerarquia_aciclica: tabla % no soportada', TG_TABLE_NAME;
    END IF;

    IF v_ciclo THEN
        RAISE EXCEPTION 'gapto.%: ciclo de jerarquia, la fila alcanzaria a su propio ancestro (D-123)', TG_TABLE_NAME;
    END IF;
    RETURN NULL;
END;
$function$;

CREATE FUNCTION gapto.fn_check_hecho_parte_de_aciclico()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_origen        uuid;
    v_destino       uuid;
    v_tipo          varchar;
    v_owner_origen  uuid;
    v_owner_destino uuid;
    v_ciclo         boolean;
BEGIN
    SELECT hecho_origen_id, hecho_destino_id, tipo_relacion INTO v_origen, v_destino, v_tipo
      FROM gapto.hecho_relaciones WHERE id = NEW.id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'hecho_relaciones: VISIBILIDAD - la relacion % no es visible al validar PARTE_DE (contexto de tenant ausente o distinto del de la escritura)', NEW.id;
    END IF;
    IF v_tipo IS DISTINCT FROM 'PARTE_DE' THEN
        RETURN NULL;
    END IF;

    SELECT owner_user_id INTO v_owner_origen FROM gapto.hechos_financieros WHERE id = v_origen;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'hecho_relaciones: VISIBILIDAD - el hecho origen % no es visible al validar PARTE_DE', v_origen;
    END IF;
    SELECT owner_user_id INTO v_owner_destino FROM gapto.hechos_financieros WHERE id = v_destino;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'hecho_relaciones: VISIBILIDAD - el hecho destino % no es visible al validar PARTE_DE', v_destino;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('gapto:HECHOS_PARTE_DE'), hashtext(LEAST(v_owner_origen, v_owner_destino)::text));
    IF v_owner_origen <> v_owner_destino THEN
        PERFORM pg_advisory_xact_lock(hashtext('gapto:HECHOS_PARTE_DE'), hashtext(GREATEST(v_owner_origen, v_owner_destino)::text));
        RAISE EXCEPTION 'hecho_relaciones: PARTE_DE exige que origen y destino pertenezcan al mismo owner (relacion %)', NEW.id;
    END IF;

    WITH RECURSIVE a(n) AS (
        SELECT v_destino
        UNION ALL
        SELECT r.hecho_destino_id FROM a JOIN gapto.hecho_relaciones r
            ON r.hecho_origen_id = a.n AND r.tipo_relacion = 'PARTE_DE'
    ) CYCLE n SET es_ciclo USING ruta
    SELECT EXISTS (SELECT 1 FROM a WHERE a.n = v_origen) INTO v_ciclo;

    IF v_ciclo THEN
        RAISE EXCEPTION 'hecho_relaciones: ciclo PARTE_DE, el hecho % seria parte de si mismo (D-123)', v_origen;
    END IF;
    RETURN NULL;
END;
$function$;

CREATE FUNCTION gapto.fn_check_cadena_sustitucion()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_owner uuid;
    v_x     RECORD;
    v_otro  RECORD;
BEGIN
    IF TG_TABLE_NAME = 'presupuestos' THEN
        SELECT owner_user_id INTO v_owner FROM gapto.presupuestos WHERE id = NEW.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'presupuestos: VISIBILIDAD - el presupuesto % no es visible al validar la cadena de sustitucion (contexto de tenant ausente o distinto del de la escritura)', NEW.id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:PRESUPUESTOS'), hashtext(v_owner::text));

        SELECT id, owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva,
               version_presupuesto AS version, reemplaza_presupuesto_id AS reemplaza
          INTO v_x FROM gapto.presupuestos WHERE id = NEW.id;

        IF v_x.reemplaza IS NOT NULL THEN
            SELECT id, owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva, version_presupuesto AS version
              INTO v_otro FROM gapto.presupuestos WHERE id = v_x.reemplaza;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'presupuestos: VISIBILIDAD - el presupuesto sustituido % no es visible al validar la cadena', v_x.reemplaza;
            END IF;
            IF (v_x.owner_user_id, v_x.periodo_desde, v_x.periodo_hasta, v_x.moneda, v_x.perspectiva)
               IS DISTINCT FROM (v_otro.owner_user_id, v_otro.periodo_desde, v_otro.periodo_hasta, v_otro.moneda, v_otro.perspectiva) THEN
                RAISE EXCEPTION 'presupuestos: el presupuesto % solo puede sustituir a otro del mismo owner, periodo, moneda y perspectiva (sustituido %)', v_x.id, v_otro.id;
            END IF;
            IF v_x.version <= v_otro.version THEN
                RAISE EXCEPTION 'presupuestos: la version % del presupuesto % debe ser mayor que la version % del sustituido %', v_x.version, v_x.id, v_otro.version, v_otro.id;
            END IF;
        END IF;

        SELECT id, owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva, version_presupuesto AS version
          INTO v_otro FROM gapto.presupuestos WHERE reemplaza_presupuesto_id = v_x.id;
        IF FOUND THEN
            IF (v_otro.owner_user_id, v_otro.periodo_desde, v_otro.periodo_hasta, v_otro.moneda, v_otro.perspectiva)
               IS DISTINCT FROM (v_x.owner_user_id, v_x.periodo_desde, v_x.periodo_hasta, v_x.moneda, v_x.perspectiva) THEN
                RAISE EXCEPTION 'presupuestos: el sucesor % debe conservar owner, periodo, moneda y perspectiva de % ', v_otro.id, v_x.id;
            END IF;
            IF v_otro.version <= v_x.version THEN
                RAISE EXCEPTION 'presupuestos: la version % del sucesor % debe ser mayor que la version % de %', v_otro.version, v_otro.id, v_x.version, v_x.id;
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'cierres_mensuales' THEN
        SELECT owner_user_id INTO v_owner FROM gapto.cierres_mensuales WHERE id = NEW.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'cierres_mensuales: VISIBILIDAD - el cierre % no es visible al validar la cadena de sustitucion (contexto de tenant ausente o distinto del de la escritura)', NEW.id;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtext('gapto:CIERRES'), hashtext(v_owner::text));

        SELECT id, owner_user_id, periodo_desde, periodo_hasta, version_cierre AS version, reemplaza_cierre_id AS reemplaza
          INTO v_x FROM gapto.cierres_mensuales WHERE id = NEW.id;

        IF v_x.reemplaza IS NOT NULL THEN
            SELECT id, owner_user_id, periodo_desde, periodo_hasta, version_cierre AS version
              INTO v_otro FROM gapto.cierres_mensuales WHERE id = v_x.reemplaza;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'cierres_mensuales: VISIBILIDAD - el cierre sustituido % no es visible al validar la cadena', v_x.reemplaza;
            END IF;
            IF (v_x.owner_user_id, v_x.periodo_desde, v_x.periodo_hasta)
               IS DISTINCT FROM (v_otro.owner_user_id, v_otro.periodo_desde, v_otro.periodo_hasta) THEN
                RAISE EXCEPTION 'cierres_mensuales: el cierre % solo puede sustituir a otro del mismo owner y periodo (sustituido %)', v_x.id, v_otro.id;
            END IF;
            IF v_x.version <= v_otro.version THEN
                RAISE EXCEPTION 'cierres_mensuales: la version % del cierre % debe ser mayor que la version % del sustituido %', v_x.version, v_x.id, v_otro.version, v_otro.id;
            END IF;
        END IF;

        SELECT id, owner_user_id, periodo_desde, periodo_hasta, version_cierre AS version
          INTO v_otro FROM gapto.cierres_mensuales WHERE reemplaza_cierre_id = v_x.id;
        IF FOUND THEN
            IF (v_otro.owner_user_id, v_otro.periodo_desde, v_otro.periodo_hasta)
               IS DISTINCT FROM (v_x.owner_user_id, v_x.periodo_desde, v_x.periodo_hasta) THEN
                RAISE EXCEPTION 'cierres_mensuales: el sucesor % debe conservar owner y periodo de %', v_otro.id, v_x.id;
            END IF;
            IF v_otro.version <= v_x.version THEN
                RAISE EXCEPTION 'cierres_mensuales: la version % del sucesor % debe ser mayor que la version % de %', v_otro.version, v_otro.id, v_x.version, v_x.id;
            END IF;
        END IF;
    ELSE
        RAISE EXCEPTION 'fn_check_cadena_sustitucion: tabla % no soportada', TG_TABLE_NAME;
    END IF;
    RETURN NULL;
END;
$function$;

DROP TRIGGER trg_categorias_financieras__no_ciclo ON gapto.categorias_financieras;
DROP TRIGGER trg_clasificaciones_tercero__no_ciclo ON gapto.clasificaciones_tercero;
DROP TRIGGER trg_inversiones__no_ciclo ON gapto.inversiones;
DROP TRIGGER trg_regiones__no_ciclo ON gapto.regiones;
DROP TRIGGER trg_presupuestos__no_ciclo ON gapto.presupuestos;
DROP TRIGGER trg_cierres_mensuales__no_ciclo ON gapto.cierres_mensuales;
DROP FUNCTION gapto.fn_prevent_self_referencing_cycle();

CREATE CONSTRAINT TRIGGER trg_categorias_financieras__aciclica
    AFTER INSERT OR UPDATE OF parent_id ON gapto.categorias_financieras
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_jerarquia_aciclica();

CREATE CONSTRAINT TRIGGER trg_clasificaciones_tercero__aciclica
    AFTER INSERT OR UPDATE OF parent_id ON gapto.clasificaciones_tercero
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_jerarquia_aciclica();

CREATE CONSTRAINT TRIGGER trg_inversiones__aciclica
    AFTER INSERT OR UPDATE OF inversion_padre_entidad_id ON gapto.inversiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_jerarquia_aciclica();

CREATE CONSTRAINT TRIGGER trg_regiones__aciclica
    AFTER INSERT OR UPDATE OF parent_region_id ON gapto.regiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_jerarquia_aciclica();

CREATE CONSTRAINT TRIGGER trg_hecho_relaciones__parte_de_aciclico
    AFTER INSERT OR UPDATE OF hecho_origen_id, hecho_destino_id, tipo_relacion ON gapto.hecho_relaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_hecho_parte_de_aciclico();

CREATE CONSTRAINT TRIGGER trg_presupuestos__cadena_sustitucion
    AFTER INSERT OR UPDATE OF owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva,
                              version_presupuesto, reemplaza_presupuesto_id ON gapto.presupuestos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cadena_sustitucion();

CREATE CONSTRAINT TRIGGER trg_cierres_mensuales__cadena_sustitucion
    AFTER INSERT OR UPDATE OF owner_user_id, periodo_desde, periodo_hasta, version_cierre,
                              reemplaza_cierre_id ON gapto.cierres_mensuales
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cadena_sustitucion();

ALTER TABLE gapto.presupuestos
    ADD CONSTRAINT uq_presupuestos__identidad_version
    UNIQUE (owner_user_id, periodo_desde, periodo_hasta, moneda, perspectiva, version_presupuesto);

ALTER TABLE gapto.presupuestos
    ADD CONSTRAINT uq_presupuestos__reemplaza UNIQUE (reemplaza_presupuesto_id);

ALTER TABLE gapto.cierres_mensuales
    ADD CONSTRAINT uq_cierres_mensuales__reemplaza UNIQUE (reemplaza_cierre_id);

DO $postcheck$
DECLARE
    v_divergentes text;
    v_n           integer;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre) INTO v_divergentes
      FROM (VALUES
            ('fn_check_reversion_movimiento',    'bd4ab19984492486f595cb539f78d263'),
            ('fn_check_jerarquia_aciclica',      '7fc289a080c5d9c0b2c731c69399d79c'),
            ('fn_check_hecho_parte_de_aciclico', '0bc045230c00b7857343c9c3d99ce7ad'),
            ('fn_check_cadena_sustitucion',      'd8b89d79f5907f6690d0c31cee7ddd54')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p ON p.proname = e.nombre AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL OR pg_catalog.md5(p.prosrc) <> e.md5_esperado
        OR p.prosecdef OR p.provolatile <> 'v' OR p.proconfig IS NOT NULL
        OR pg_catalog.pg_get_userbyid(p.proowner) <> 'gapto_owner';
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: funciones con huella o atributos inesperados: %', v_divergentes;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
                WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace AND p.proname = 'fn_prevent_self_referencing_cycle') THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: fn_prevent_self_referencing_cycle sigue existiendo';
    END IF;

    SELECT pg_catalog.string_agg(p.proname, ', ' ORDER BY p.proname) INTO v_divergentes
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.prosrc ~* 'for\s+update' AND p.proname <> 'fn_check_cuenta_moneda';
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: FOR UPDATE fuera de la excepcion R-MON en: %', v_divergentes;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM (VALUES
            ('categorias_financieras',  'trg_categorias_financieras__aciclica',     'fn_check_jerarquia_aciclica'),
            ('clasificaciones_tercero', 'trg_clasificaciones_tercero__aciclica',    'fn_check_jerarquia_aciclica'),
            ('inversiones',             'trg_inversiones__aciclica',                'fn_check_jerarquia_aciclica'),
            ('regiones',                'trg_regiones__aciclica',                   'fn_check_jerarquia_aciclica'),
            ('hecho_relaciones',        'trg_hecho_relaciones__parte_de_aciclico',  'fn_check_hecho_parte_de_aciclico'),
            ('presupuestos',            'trg_presupuestos__cadena_sustitucion',     'fn_check_cadena_sustitucion'),
            ('cierres_mensuales',       'trg_cierres_mensuales__cadena_sustitucion','fn_check_cadena_sustitucion')
      ) AS e(tabla, disparador, funcion)
      JOIN pg_catalog.pg_class c ON c.relname = e.tabla AND c.relnamespace = 'gapto'::pg_catalog.regnamespace
      JOIN pg_catalog.pg_trigger t ON t.tgrelid = c.oid AND t.tgname = e.disparador
      JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid AND p.proname = e.funcion
     WHERE t.tgenabled = 'O' AND t.tgconstraint <> 0 AND t.tgdeferrable AND t.tginitdeferred
       AND (t.tgtype & 1) = 1 AND (t.tgtype & 2) = 0 AND (t.tgtype & 4) <> 0 AND (t.tgtype & 16) <> 0 AND (t.tgtype & 8) = 0;
    IF v_n <> 7 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: solo % de los 7 triggers nuevos tienen la definicion esperada', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_constraint k
     WHERE k.contype = 'u' AND k.convalidated
       AND k.conname IN ('uq_presupuestos__identidad_version', 'uq_presupuestos__reemplaza', 'uq_cierres_mensuales__reemplaza');
    IF v_n <> 3 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: solo % de las 3 UNIQUE nuevas existen', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 21 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: se esperaban 21 funciones, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 40 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: se esperaban 40 triggers no internos, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 30 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: se esperaban 30 constraint triggers, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'u';
    IF v_n <> 40 THEN
        RAISE EXCEPTION 'F03-02-0280 POSTCHECK: se esperaban 40 UNIQUE, hay %', v_n;
    END IF;
END
$postcheck$;

RESET ROLE;

COMMIT;
