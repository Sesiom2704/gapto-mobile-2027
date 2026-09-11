-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0270_f03_02_revalidacion_desde_el_padre.sql
-- Ruta: migrations/0270_f03_02_revalidacion_desde_el_padre.sql
-- Descripcion: FASE 03 / F03-02. Correccion forward-only posterior a 0265.
--   Las invariantes multi-fila se validaban desde la tabla hija; un UPDATE de
--   la fila padre podia invalidarlas sin que nada lo comprobara. Esta
--   migration las revalida tambien desde el padre y materializa D-119 (T6),
--   D-120 (R-MON) y A8. No reabre F03-01 ni edita la cadena congelada.
--
--   1. R-HMT / R-TRF / R-REV / D-119(a) desde el padre. Funcion nueva
--      gapto.fn_check_movimiento_padre y CONSTRAINT TRIGGER
--      trg_movimientos_tesoreria__padre_dependencias AFTER UPDATE OF importe,
--      estado, cuenta_id DEFERRABLE INITIALLY DEFERRED. Sobre el estado final:
--        a) un movimiento ANULADO no puede tener transferencia, asignaciones
--           en hecho_movimientos_tesoreria ni reversiones ACTIVAS (D-119);
--        b) suma de asignaciones hmt: |suma| <= |importe| y mismo signo;
--        c) estructura de la transferencia en la que participa (signos,
--           cuentas distintas, mismo owner, importes iguales con la misma
--           moneda); bloquea las DOS patas en orden LEAST/GREATEST antes de
--           leer la contraria. El deadlock entre dos transacciones que mueven
--           cada una una pata es inherente (dos padres) y se resuelve con
--           reintento completo (D-114);
--        d) si es original de reversiones ACTIVAS: signo opuesto y
--           suma |reversiones| <= |importe|. Cambiar la cuenta de un original
--           con reversiones ya lo impide la FK compuesta (D-099).
--      Residuo registrado: el signo solo se exige a reversiones ACTIVAS; una
--      reversion ANULADA puede quedar con el signo del original si este
--      cambia de signo despues.
--
--   2. T6(b). Los validadores hijos rechazan crear o mover una dependencia
--      hacia un movimiento ANULADO: hmt y transferencias siempre (no tienen
--      estado propio); reversiones solo si NEW.estado = 'ACTIVO' (cubre
--      crear, mover y reactivar; permite editar reversiones anuladas).
--
--   3. R-INV desde el padre. CONSTRAINT TRIGGER diferido nuevo
--      trg_hecho_efectos__inversion_asignacion AFTER UPDATE OF importe_delta,
--      tipo_efecto. fn_check_inversion_asignacion_suma atiende
--      TG_TABLE_NAME = 'hecho_efectos' y pasa a una regla de estado: si el
--      efecto tiene asignaciones, debe ser INVERSION y la suma debe caber.
--      Efecto colateral documentado: desaparece el falso positivo previo del
--      lado hijo (INSERT y DELETE de la asignacion en la misma transaccion).
--
--   4. R-MON (D-120). Funcion nueva gapto.fn_check_cuenta_moneda y trigger
--      INMEDIATO (no diferido) trg_cuentas__moneda_con_historia AFTER UPDATE
--      OF moneda. Orden: si la moneda no cambia, salir; FOR UPDATE sobre la
--      propia cuenta; recomprobar; rechazar si OLD.saldo_apertura IS NOT NULL
--      (0 cuenta), si existe cualquier movimiento (tambien ANULADO) o
--      cualquier cierre_saldos_cuenta. FOR UPDATE es la EXCEPCION
--      INTENCIONADA a D-114: es el unico modo que choca con el FOR KEY SHARE
--      de la FK inmediata de un primer movimiento o cierre concurrente. OLD
--      es la version realmente actualizada (tras EPQ), lo que serializa la
--      carrera con un primer saldo_apertura sobre la misma fila.
--
--   5. R-TPN. Funcion nueva gapto.fn_check_tercero_naturaleza y CONSTRAINT
--      TRIGGER diferido trg_terceros__naturaleza_personas AFTER UPDATE OF
--      naturaleza: si hay tercero_personas, la naturaleza debe ser
--      exactamente PERSONA (IS DISTINCT FROM: NULL no satisface la
--      precondicion). El validador hijo fn_check_tercero_persona_naturaleza
--      pasa a bloquear el tercero con FOR NO KEY UPDATE y a ser fail-closed:
--      sin ese lock, el BEFORE de la hija leia el valor antiguo y la FK solo
--      toma KEY SHARE, compatible con el UPDATE del padre (write-skew).
--
--   6. R-GAR. Funcion nueva gapto.fn_check_entidad_garantizada_por y
--      CONSTRAINT TRIGGER diferido trg_entidades__garantizada_por AFTER
--      UPDATE OF tipo_entidad: una entidad origen de GARANTIZADA_POR debe
--      ser FINANCIACION y una destino PROPIEDAD, con el mismo owner que la
--      contraria. No bloquea la entidad contraria: la condicion de cada
--      extremo solo depende de su propio tipo. El validador hijo
--      fn_check_garantizada_por pasa a bloquear las DOS entidades en orden
--      LEAST/GREATEST con FOR NO KEY UPDATE y a ser fail-closed.
--
--   7. A8. CHECK nuevo ck_regla_versiones__ventana_dias_obligatorios: con
--      fecha_modo = VENTANA, dia_desde y dia_hasta son obligatorios. El CHECK
--      congelado de 0030 evaluaba a NULL y aceptaba la fila. No se toca 0030.
--      FORCE ROW LEVEL SECURITY se levanta y restaura en la misma
--      transaccion (D-094/D-095).
--
--   Reglas transversales en las funciones nuevas: T1 fail-closed (NOT FOUND
--   en la propia fila o en la contraria es VISIBILIDAD; falso positivo
--   aceptado por precedente UPDATE -> DELETE de la misma fila en la misma
--   transaccion), T2, lock root FOR NO KEY UPDATE salvo R-MON, SECURITY
--   INVOKER, VOLATILE y sin comentarios dentro de los cuerpos.
--
--   CONTRATO: funciones 15 -> 19; triggers no internos 34 -> 39; constraint
--   triggers 19 -> 23; un CHECK mas en regla_versiones.
--
--   HUELLAS (md5 de prosrc):  vigente (0260)  ->  0270 (bytes)
--     fn_check_hecho_mov_tesoreria_suma     2b9483c066e3f637f24d396babe27720  ->  808128976910a4333fd8c6843d0b9919  1986
--     fn_check_transferencia_estructura     e956eb54ec62b7ac7b9bcf11ca3f107e  ->  545db95496409a5adf01fbb98e4b161a  2722
--     fn_check_reversion_movimiento         00161f7875783230311834ca84e472e2  ->  91a33cb088ab4ff8d9c56c29fc3d12c2  2466
--     fn_check_inversion_asignacion_suma    182087c02d004ca2c2f0d38bd00f10ff  ->  128a6bd0e45f5fe3632c83b25cbfa371  2129
--     fn_check_tercero_persona_naturaleza   5908efa77fb293358c3ef08f355c8f66  ->  c2fd9d2c7261ca315a658eba18db02c5  616
--     fn_check_garantizada_por              2650c24c8182125e579b9ca72b4de568  ->  e31522fac182a670d7f698b6e728fab7  1738
--     fn_check_movimiento_padre             (nueva)                           ->  d62ba0700dbac9a94884e39bafd3baeb  5859
--     fn_check_cuenta_moneda                (nueva)                           ->  f13b175f54af8780ed57ffaebd5e72bf  1085
--     fn_check_tercero_naturaleza           (nueva)                           ->  067d309ba09fe37c8743928d78826bc8  706
--     fn_check_entidad_garantizada_por      (nueva)                           ->  04ef0d4c49fdf1a1b1e06e82aeca3845  1922
--
--   SALVAGUARDAS. Precheck de datos de todas las invariantes que pasan a
--   vigilarse desde el padre (concluyente solo con BYPASSRLS); precheck de
--   huellas y de ausencia de objetos; postcheck de recuentos, huellas,
--   triggers, CHECK validado, FORCE restaurado y FOR UPDATE limitado a
--   fn_check_cuenta_moneda.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_datos$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      integer;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT v_bypass THEN
        RAISE NOTICE 'F03-02-0270 PRECHECK DATOS: el rol % no tiene BYPASSRLS; el recuento no es concluyente y debe verificarse aparte', current_user;
        RETURN;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.movimientos_tesoreria m
     WHERE m.estado <> 'ACTIVO'
       AND (EXISTS (SELECT 1 FROM gapto.transferencias t WHERE m.id IN (t.movimiento_salida_id, t.movimiento_entrada_id))
            OR EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria h WHERE h.movimiento_tesoreria_id = m.id)
            OR EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria r WHERE r.reversion_de_movimiento_id = m.id AND r.estado = 'ACTIVO'));
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' anulados_con_dependencias=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.movimientos_tesoreria m
      JOIN (SELECT h.movimiento_tesoreria_id AS id, pg_catalog.sum(h.importe_asignado) AS s
              FROM gapto.hecho_movimientos_tesoreria h GROUP BY 1) x ON x.id = m.id
     WHERE pg_catalog.abs(x.s) > pg_catalog.abs(m.importe) OR (x.s <> 0 AND pg_catalog.sign(x.s) <> pg_catalog.sign(m.importe));
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' hmt_descuadradas=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.movimientos_tesoreria o
     WHERE EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria r
                    WHERE r.reversion_de_movimiento_id = o.id AND r.estado = 'ACTIVO'
                      AND pg_catalog.sign(r.importe) = pg_catalog.sign(o.importe))
        OR (SELECT COALESCE(pg_catalog.sum(pg_catalog.abs(r.importe)), 0) FROM gapto.movimientos_tesoreria r
             WHERE r.reversion_de_movimiento_id = o.id AND r.estado = 'ACTIVO') > pg_catalog.abs(o.importe);
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' reversiones_invalidas=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.transferencias t
      JOIN gapto.movimientos_tesoreria s ON s.id = t.movimiento_salida_id
      JOIN gapto.cuentas cs ON cs.id = s.cuenta_id
      JOIN gapto.movimientos_tesoreria e ON e.id = t.movimiento_entrada_id
      JOIN gapto.cuentas ce ON ce.id = e.cuenta_id
     WHERE s.importe >= 0 OR e.importe <= 0 OR s.cuenta_id = e.cuenta_id
        OR cs.owner_user_id <> ce.owner_user_id
        OR (cs.moneda = ce.moneda AND pg_catalog.abs(s.importe) <> e.importe);
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' transferencias_invalidas=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.hecho_efectos f
      JOIN (SELECT a.efecto_inversion_id AS id, pg_catalog.sum(a.importe_asignado) AS s
              FROM gapto.inversion_asignaciones_efecto a GROUP BY 1) x ON x.id = f.id
     WHERE f.tipo_efecto <> 'INVERSION' OR pg_catalog.abs(x.s) > pg_catalog.abs(f.importe_delta)
        OR (x.s <> 0 AND pg_catalog.sign(x.s) <> pg_catalog.sign(f.importe_delta));
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' asignaciones_inversion_invalidas=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.tercero_personas p
      JOIN gapto.terceros t ON t.id = p.tercero_id
     WHERE t.naturaleza IS DISTINCT FROM 'PERSONA';
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' personas_sin_naturaleza_persona=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.entidad_relaciones r
      JOIN gapto.entidades o ON o.id = r.entidad_origen_id
      JOIN gapto.entidades d ON d.id = r.entidad_destino_id
     WHERE r.tipo_relacion = 'GARANTIZADA_POR'
       AND (o.tipo_entidad <> 'FINANCIACION' OR d.tipo_entidad <> 'PROPIEDAD' OR o.owner_user_id <> d.owner_user_id);
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' garantias_invalidas=%s', v_n); END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM gapto.regla_versiones v
     WHERE v.fecha_modo = 'VENTANA' AND (v.dia_desde IS NULL OR v.dia_hasta IS NULL);
    IF v_n > 0 THEN v_rep := v_rep || pg_catalog.format(' ventanas_sin_dias=%s', v_n); END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK DATOS: datos que ya violan invariantes de 0270:%', v_rep;
    END IF;
END
$precheck_datos$;

SET ROLE gapto_owner;

DO $precheck$
DECLARE
    v_divergentes text;
    v_n           integer;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre)
      INTO v_divergentes
      FROM (VALUES
            ('fn_check_hecho_mov_tesoreria_suma',   '2b9483c066e3f637f24d396babe27720'),
            ('fn_check_transferencia_estructura',   'e956eb54ec62b7ac7b9bcf11ca3f107e'),
            ('fn_check_reversion_movimiento',       '00161f7875783230311834ca84e472e2'),
            ('fn_check_inversion_asignacion_suma',  '182087c02d004ca2c2f0d38bd00f10ff'),
            ('fn_check_tercero_persona_naturaleza', '5908efa77fb293358c3ef08f355c8f66'),
            ('fn_check_garantizada_por',            '2650c24c8182125e579b9ca72b4de568')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
        ON p.proname = e.nombre AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: huellas distintas de 0260 en: %', v_divergentes;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_movimiento_padre', 'fn_check_cuenta_moneda',
                         'fn_check_tercero_naturaleza', 'fn_check_entidad_garantizada_por');
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: ya existen % funciones de 0270', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND t.tgname IN ('trg_movimientos_tesoreria__padre_dependencias', 'trg_hecho_efectos__inversion_asignacion',
                        'trg_cuentas__moneda_con_historia', 'trg_terceros__naturaleza_personas',
                        'trg_entidades__garantizada_por');
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: ya existen % triggers de 0270', v_n;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k
                WHERE k.conrelid = 'gapto.regla_versiones'::pg_catalog.regclass
                  AND k.conname = 'ck_regla_versiones__ventana_dias_obligatorios') THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: ck_regla_versiones__ventana_dias_obligatorios ya existe';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 15 THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: se esperaban 15 funciones, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 34 THEN
        RAISE EXCEPTION 'F03-02-0270 PRECHECK: se esperaban 34 triggers no internos, hay %', v_n;
    END IF;
END
$precheck$;

CREATE OR REPLACE FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_nuevo         uuid;
    v_viejo         uuid;
    v_movimiento_id uuid;
    v_importe       numeric;
    v_estado        varchar;
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
        SELECT importe, estado INTO v_importe, v_estado FROM gapto.movimientos_tesoreria WHERE id = v_movimiento_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_movimiento_id = v_nuevo THEN
                RAISE EXCEPTION 'hecho_movimientos_tesoreria: VISIBILIDAD - el movimiento % no es visible al validar la asignacion (contexto de tenant ausente o distinto del de la escritura)',
                    v_movimiento_id;
            END IF;
            CONTINUE;
        END IF;

        IF v_movimiento_id = v_nuevo AND v_estado <> 'ACTIVO' THEN
            RAISE EXCEPTION 'hecho_movimientos_tesoreria: el movimiento % esta ANULADO y no admite asignaciones nuevas ni movidas hacia el (D-119/T6)',
                v_movimiento_id;
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

    SELECT m.importe, m.estado, m.cuenta_id, c.owner_user_id, c.moneda
      INTO v_salida
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.movimiento_salida_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferencias: VISIBILIDAD - el movimiento de salida % no es visible al validar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
            NEW.movimiento_salida_id;
    END IF;

    SELECT m.importe, m.estado, m.cuenta_id, c.owner_user_id, c.moneda
      INTO v_entrada
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.movimiento_entrada_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferencias: VISIBILIDAD - el movimiento de entrada % no es visible al validar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
            NEW.movimiento_entrada_id;
    END IF;

    IF v_salida.estado <> 'ACTIVO' OR v_entrada.estado <> 'ACTIVO' THEN
        RAISE EXCEPTION 'transferencias: las dos patas deben estar ACTIVAS; no se crea ni se mueve una transferencia hacia un movimiento ANULADO (D-119/T6; salida=%, entrada=%)',
            v_salida.estado, v_entrada.estado;
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

    SELECT m.importe, m.estado, c.owner_user_id, c.moneda
      INTO v_original
      FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
     WHERE m.id = NEW.reversion_de_movimiento_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - el movimiento original % no es visible al validar la reversion (contexto de tenant ausente o distinto del de la escritura)',
            NEW.reversion_de_movimiento_id;
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
    v_filas         bigint;
    v_suma          numeric;
BEGIN
    IF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_nuevo := NEW.id;
    ELSE
        IF TG_OP <> 'DELETE' THEN
            v_nuevo := NEW.efecto_inversion_id;
        END IF;
        IF TG_OP <> 'INSERT' THEN
            v_viejo := OLD.efecto_inversion_id;
        END IF;
    END IF;

    FOR v_efecto_id IN
        SELECT DISTINCT e FROM unnest(ARRAY[v_nuevo, v_viejo]) AS e
         WHERE e IS NOT NULL ORDER BY e
    LOOP
        SELECT importe_delta, tipo_efecto INTO v_importe_delta, v_tipo_efecto
          FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            IF v_efecto_id = v_nuevo THEN
                RAISE EXCEPTION 'gapto.%: VISIBILIDAD - el efecto % no es visible al validar la asignacion de inversion (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_efecto_id;
            END IF;
            CONTINUE;
        END IF;

        SELECT count(*), COALESCE(sum(importe_asignado), 0) INTO v_filas, v_suma
          FROM gapto.inversion_asignaciones_efecto WHERE efecto_inversion_id = v_efecto_id;

        IF v_filas > 0 AND v_tipo_efecto IS DISTINCT FROM 'INVERSION' THEN
            RAISE EXCEPTION 'inversion_asignaciones_efecto: el efecto % debe ser tipo_efecto=INVERSION (encontrado=%)', v_efecto_id, v_tipo_efecto;
        END IF;
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

CREATE OR REPLACE FUNCTION gapto.fn_check_tercero_persona_naturaleza()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_naturaleza varchar;
BEGIN
    SELECT naturaleza INTO v_naturaleza FROM gapto.terceros WHERE id = NEW.tercero_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tercero_personas: VISIBILIDAD - el tercero % no es visible al validar la persona (contexto de tenant ausente o distinto del de la escritura)',
            NEW.tercero_id;
    END IF;
    IF v_naturaleza IS DISTINCT FROM 'PERSONA' THEN
        RAISE EXCEPTION 'tercero_personas solo puede existir para terceros.naturaleza=PERSONA (tercero_id=%, naturaleza=%)', NEW.tercero_id, v_naturaleza;
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION gapto.fn_check_garantizada_por()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_origen_tipo varchar;
    v_destino_tipo varchar;
    v_origen_owner uuid;
    v_destino_owner uuid;
BEGIN
    IF NEW.tipo_relacion = 'GARANTIZADA_POR' THEN
        PERFORM 1 FROM gapto.entidades WHERE id = LEAST(NEW.entidad_origen_id, NEW.entidad_destino_id) FOR NO KEY UPDATE;
        PERFORM 1 FROM gapto.entidades WHERE id = GREATEST(NEW.entidad_origen_id, NEW.entidad_destino_id) FOR NO KEY UPDATE;

        SELECT tipo_entidad, owner_user_id INTO v_origen_tipo, v_origen_owner
          FROM gapto.entidades WHERE id = NEW.entidad_origen_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'entidad_relaciones: VISIBILIDAD - la entidad origen % no es visible al validar GARANTIZADA_POR (contexto de tenant ausente o distinto del de la escritura)',
                NEW.entidad_origen_id;
        END IF;
        SELECT tipo_entidad, owner_user_id INTO v_destino_tipo, v_destino_owner
          FROM gapto.entidades WHERE id = NEW.entidad_destino_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'entidad_relaciones: VISIBILIDAD - la entidad destino % no es visible al validar GARANTIZADA_POR (contexto de tenant ausente o distinto del de la escritura)',
                NEW.entidad_destino_id;
        END IF;

        IF v_origen_tipo IS DISTINCT FROM 'FINANCIACION' OR v_destino_tipo IS DISTINCT FROM 'PROPIEDAD' THEN
            RAISE EXCEPTION 'GARANTIZADA_POR solo admite FINANCIACION (origen) -> PROPIEDAD (destino); origen=%, destino=%', v_origen_tipo, v_destino_tipo;
        END IF;

        IF v_origen_owner IS DISTINCT FROM v_destino_owner THEN
            RAISE EXCEPTION 'GARANTIZADA_POR exige que origen y destino compartan owner_user_id';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION gapto.fn_check_movimiento_padre()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_importe       numeric;
    v_estado        varchar;
    v_suma          numeric;
    v_transferencia RECORD;
    v_salida        RECORD;
    v_entrada       RECORD;
BEGIN
    SELECT importe, estado INTO v_importe, v_estado
      FROM gapto.movimientos_tesoreria WHERE id = NEW.id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - el movimiento % no es visible al revalidar sus dependencias (contexto de tenant ausente o distinto del de la escritura)',
            NEW.id;
    END IF;

    IF v_estado <> 'ACTIVO' THEN
        IF EXISTS (SELECT 1 FROM gapto.transferencias t
                    WHERE t.movimiento_salida_id = NEW.id OR t.movimiento_entrada_id = NEW.id) THEN
            RAISE EXCEPTION 'movimientos_tesoreria: el movimiento % no puede quedar ANULADO porque participa en una transferencia (D-119)', NEW.id;
        END IF;
        IF EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria h WHERE h.movimiento_tesoreria_id = NEW.id) THEN
            RAISE EXCEPTION 'movimientos_tesoreria: el movimiento % no puede quedar ANULADO porque tiene asignaciones a hechos (D-119)', NEW.id;
        END IF;
        IF EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria r
                    WHERE r.reversion_de_movimiento_id = NEW.id AND r.estado = 'ACTIVO') THEN
            RAISE EXCEPTION 'movimientos_tesoreria: el movimiento % no puede quedar ANULADO porque tiene reversiones ACTIVAS (D-119)', NEW.id;
        END IF;
        RETURN NULL;
    END IF;

    SELECT COALESCE(sum(h.importe_asignado), 0) INTO v_suma
      FROM gapto.hecho_movimientos_tesoreria h WHERE h.movimiento_tesoreria_id = NEW.id;
    IF abs(v_suma) > abs(v_importe) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: la suma asignada a hechos (%) supera en valor absoluto el nuevo importe del movimiento % (importe=%)',
            v_suma, NEW.id, v_importe;
    END IF;
    IF v_suma <> 0 AND sign(v_suma) <> sign(v_importe) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: la suma asignada a hechos (%) debe tener el mismo signo que el movimiento % (importe=%)',
            v_suma, NEW.id, v_importe;
    END IF;

    IF EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria r
                WHERE r.reversion_de_movimiento_id = NEW.id AND r.estado = 'ACTIVO'
                  AND sign(r.importe) = sign(v_importe)) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: el original % tiene reversiones ACTIVAS del mismo signo que su nuevo importe (importe=%)',
            NEW.id, v_importe;
    END IF;
    SELECT COALESCE(sum(abs(r.importe)), 0) INTO v_suma
      FROM gapto.movimientos_tesoreria r
     WHERE r.reversion_de_movimiento_id = NEW.id AND r.estado = 'ACTIVO';
    IF v_suma > abs(v_importe) THEN
        RAISE EXCEPTION 'movimientos_tesoreria: la suma de reversiones activas (%) supera el nuevo importe del original % (importe=%)',
            v_suma, NEW.id, v_importe;
    END IF;

    FOR v_transferencia IN
        SELECT t.movimiento_salida_id, t.movimiento_entrada_id
          FROM gapto.transferencias t
         WHERE t.movimiento_salida_id = NEW.id OR t.movimiento_entrada_id = NEW.id
    LOOP
        PERFORM 1 FROM gapto.movimientos_tesoreria
         WHERE id = LEAST(v_transferencia.movimiento_salida_id, v_transferencia.movimiento_entrada_id) FOR NO KEY UPDATE;
        PERFORM 1 FROM gapto.movimientos_tesoreria
         WHERE id = GREATEST(v_transferencia.movimiento_salida_id, v_transferencia.movimiento_entrada_id) FOR NO KEY UPDATE;

        SELECT m.importe, m.cuenta_id, c.owner_user_id, c.moneda INTO v_salida
          FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
         WHERE m.id = v_transferencia.movimiento_salida_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - la pata de salida % no es visible al revalidar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
                v_transferencia.movimiento_salida_id;
        END IF;
        SELECT m.importe, m.cuenta_id, c.owner_user_id, c.moneda INTO v_entrada
          FROM gapto.movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id
         WHERE m.id = v_transferencia.movimiento_entrada_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'movimientos_tesoreria: VISIBILIDAD - la pata de entrada % no es visible al revalidar la transferencia (contexto de tenant ausente o distinto del de la escritura)',
                v_transferencia.movimiento_entrada_id;
        END IF;

        IF v_salida.importe >= 0 THEN
            RAISE EXCEPTION 'movimientos_tesoreria: la salida % de una transferencia debe tener importe negativo (encontrado=%)',
                v_transferencia.movimiento_salida_id, v_salida.importe;
        END IF;
        IF v_entrada.importe <= 0 THEN
            RAISE EXCEPTION 'movimientos_tesoreria: la entrada % de una transferencia debe tener importe positivo (encontrado=%)',
                v_transferencia.movimiento_entrada_id, v_entrada.importe;
        END IF;
        IF v_salida.cuenta_id = v_entrada.cuenta_id THEN
            RAISE EXCEPTION 'movimientos_tesoreria: las patas de una transferencia deben estar en cuentas distintas (cuenta_id=%)', v_salida.cuenta_id;
        END IF;
        IF v_salida.owner_user_id <> v_entrada.owner_user_id THEN
            RAISE EXCEPTION 'movimientos_tesoreria: las patas de una transferencia deben pertenecer al mismo owner';
        END IF;
        IF v_salida.moneda = v_entrada.moneda AND abs(v_salida.importe) <> v_entrada.importe THEN
            RAISE EXCEPTION 'movimientos_tesoreria: con la misma moneda, abs(importe_salida)=% debe igualar importe_entrada=% en la transferencia',
                abs(v_salida.importe), v_entrada.importe;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$function$;

CREATE FUNCTION gapto.fn_check_cuenta_moneda()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.moneda IS NOT DISTINCT FROM OLD.moneda THEN
        RETURN NULL;
    END IF;

    PERFORM 1 FROM gapto.cuentas WHERE id = NEW.id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'cuentas: VISIBILIDAD - la cuenta % no es visible al validar el cambio de moneda (contexto de tenant ausente o distinto del de la escritura)',
            NEW.id;
    END IF;

    IF OLD.saldo_apertura IS NOT NULL THEN
        RAISE EXCEPTION 'cuentas: la moneda de la cuenta % es inmutable porque tiene saldo de apertura (saldo_apertura=%; D-120)',
            NEW.id, OLD.saldo_apertura;
    END IF;
    IF EXISTS (SELECT 1 FROM gapto.movimientos_tesoreria m WHERE m.cuenta_id = NEW.id) THEN
        RAISE EXCEPTION 'cuentas: la moneda de la cuenta % es inmutable porque tiene movimientos de tesoreria (D-120)', NEW.id;
    END IF;
    IF EXISTS (SELECT 1 FROM gapto.cierre_saldos_cuenta s WHERE s.cuenta_id = NEW.id) THEN
        RAISE EXCEPTION 'cuentas: la moneda de la cuenta % es inmutable porque tiene saldos de cierre (D-120)', NEW.id;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE FUNCTION gapto.fn_check_tercero_naturaleza()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_naturaleza varchar;
BEGIN
    SELECT naturaleza INTO v_naturaleza FROM gapto.terceros WHERE id = NEW.id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'terceros: VISIBILIDAD - el tercero % no es visible al revalidar su naturaleza (contexto de tenant ausente o distinto del de la escritura)',
            NEW.id;
    END IF;

    IF v_naturaleza IS DISTINCT FROM 'PERSONA'
       AND EXISTS (SELECT 1 FROM gapto.tercero_personas p WHERE p.tercero_id = NEW.id) THEN
        RAISE EXCEPTION 'terceros: el tercero % tiene datos de persona (tercero_personas) y su naturaleza debe ser PERSONA (encontrada=%)',
            NEW.id, v_naturaleza;
    END IF;

    RETURN NULL;
END;
$function$;

CREATE FUNCTION gapto.fn_check_entidad_garantizada_por()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tipo       varchar;
    v_owner      uuid;
    v_otro_owner uuid;
    v_relacion   RECORD;
BEGIN
    SELECT tipo_entidad, owner_user_id INTO v_tipo, v_owner
      FROM gapto.entidades WHERE id = NEW.id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'entidades: VISIBILIDAD - la entidad % no es visible al revalidar GARANTIZADA_POR (contexto de tenant ausente o distinto del de la escritura)',
            NEW.id;
    END IF;

    FOR v_relacion IN
        SELECT r.entidad_origen_id, r.entidad_destino_id
          FROM gapto.entidad_relaciones r
         WHERE r.tipo_relacion = 'GARANTIZADA_POR'
           AND (r.entidad_origen_id = NEW.id OR r.entidad_destino_id = NEW.id)
    LOOP
        IF v_relacion.entidad_origen_id = NEW.id AND v_tipo IS DISTINCT FROM 'FINANCIACION' THEN
            RAISE EXCEPTION 'entidades: la entidad % es origen de GARANTIZADA_POR y debe ser FINANCIACION (encontrado=%)', NEW.id, v_tipo;
        END IF;
        IF v_relacion.entidad_destino_id = NEW.id AND v_tipo IS DISTINCT FROM 'PROPIEDAD' THEN
            RAISE EXCEPTION 'entidades: la entidad % es destino de GARANTIZADA_POR y debe ser PROPIEDAD (encontrado=%)', NEW.id, v_tipo;
        END IF;

        SELECT owner_user_id INTO v_otro_owner FROM gapto.entidades
         WHERE id = CASE WHEN v_relacion.entidad_origen_id = NEW.id
                         THEN v_relacion.entidad_destino_id ELSE v_relacion.entidad_origen_id END;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'entidades: VISIBILIDAD - la entidad contraria de una GARANTIZADA_POR de % no es visible (contexto de tenant ausente o distinto del de la escritura)',
                NEW.id;
        END IF;
        IF v_otro_owner <> v_owner THEN
            RAISE EXCEPTION 'entidades: GARANTIZADA_POR exige que origen y destino compartan owner_user_id (entidad=%)', NEW.id;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$function$;

CREATE CONSTRAINT TRIGGER trg_movimientos_tesoreria__padre_dependencias
    AFTER UPDATE OF importe, estado, cuenta_id ON gapto.movimientos_tesoreria
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_movimiento_padre();

CREATE CONSTRAINT TRIGGER trg_hecho_efectos__inversion_asignacion
    AFTER UPDATE OF importe_delta, tipo_efecto ON gapto.hecho_efectos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_asignacion_suma();

CREATE TRIGGER trg_cuentas__moneda_con_historia
    AFTER UPDATE OF moneda ON gapto.cuentas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuenta_moneda();

CREATE CONSTRAINT TRIGGER trg_terceros__naturaleza_personas
    AFTER UPDATE OF naturaleza ON gapto.terceros
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_tercero_naturaleza();

CREATE CONSTRAINT TRIGGER trg_entidades__garantizada_por
    AFTER UPDATE OF tipo_entidad ON gapto.entidades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_garantizada_por();

ALTER TABLE gapto.regla_versiones NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.regla_versiones
    ADD CONSTRAINT ck_regla_versiones__ventana_dias_obligatorios
    CHECK ((fecha_modo)::text <> 'VENTANA' OR (dia_desde IS NOT NULL AND dia_hasta IS NOT NULL));

ALTER TABLE gapto.regla_versiones FORCE ROW LEVEL SECURITY;

DO $postcheck$
DECLARE
    v_divergentes text;
    v_n           integer;
BEGIN
    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre)
      INTO v_divergentes
      FROM (VALUES
            ('fn_check_hecho_mov_tesoreria_suma',   '808128976910a4333fd8c6843d0b9919'),
            ('fn_check_transferencia_estructura',   '545db95496409a5adf01fbb98e4b161a'),
            ('fn_check_reversion_movimiento',       '91a33cb088ab4ff8d9c56c29fc3d12c2'),
            ('fn_check_inversion_asignacion_suma',  '128a6bd0e45f5fe3632c83b25cbfa371'),
            ('fn_check_tercero_persona_naturaleza', 'c2fd9d2c7261ca315a658eba18db02c5'),
            ('fn_check_garantizada_por',            'e31522fac182a670d7f698b6e728fab7'),
            ('fn_check_movimiento_padre',           'd62ba0700dbac9a94884e39bafd3baeb'),
            ('fn_check_cuenta_moneda',              'f13b175f54af8780ed57ffaebd5e72bf'),
            ('fn_check_tercero_naturaleza',         '067d309ba09fe37c8743928d78826bc8'),
            ('fn_check_entidad_garantizada_por',    '04ef0d4c49fdf1a1b1e06e82aeca3845')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p
        ON p.proname = e.nombre AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL OR pg_catalog.md5(p.prosrc) <> e.md5_esperado
        OR p.prosecdef OR p.provolatile <> 'v' OR p.proconfig IS NOT NULL
        OR pg_catalog.pg_get_userbyid(p.proowner) <> 'gapto_owner';
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: funciones con huella o atributos inesperados: %', v_divergentes;
    END IF;

    SELECT pg_catalog.string_agg(p.proname, ', ' ORDER BY p.proname) INTO v_divergentes
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.prosrc ~* 'for\s+update'
       AND p.proname <> 'fn_check_cuenta_moneda';
    IF v_divergentes IS NOT NULL THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: FOR UPDATE fuera de la excepcion R-MON en: %', v_divergentes;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM (VALUES
            ('movimientos_tesoreria', 'trg_movimientos_tesoreria__padre_dependencias', true, 'fn_check_movimiento_padre'),
            ('hecho_efectos',         'trg_hecho_efectos__inversion_asignacion',       true, 'fn_check_inversion_asignacion_suma'),
            ('cuentas',               'trg_cuentas__moneda_con_historia',              false, 'fn_check_cuenta_moneda'),
            ('terceros',              'trg_terceros__naturaleza_personas',             true, 'fn_check_tercero_naturaleza'),
            ('entidades',             'trg_entidades__garantizada_por',                true, 'fn_check_entidad_garantizada_por')
      ) AS e(tabla, disparador, diferido, funcion)
      JOIN pg_catalog.pg_class c ON c.relname = e.tabla AND c.relnamespace = 'gapto'::pg_catalog.regnamespace
      JOIN pg_catalog.pg_trigger t ON t.tgrelid = c.oid AND t.tgname = e.disparador
      JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid AND p.proname = e.funcion
     WHERE t.tgenabled = 'O' AND (t.tgtype & 1) = 1 AND (t.tgtype & 2) = 0 AND (t.tgtype & 16) <> 0
       AND (t.tgtype & 4) = 0 AND (t.tgtype & 8) = 0
       AND (t.tgconstraint <> 0) = e.diferido AND t.tgdeferrable = e.diferido AND t.tginitdeferred = e.diferido;
    IF v_n <> 5 THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: solo % de los 5 triggers nuevos tienen la definicion esperada', v_n;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k
                    WHERE k.conrelid = 'gapto.regla_versiones'::pg_catalog.regclass
                      AND k.conname = 'ck_regla_versiones__ventana_dias_obligatorios'
                      AND k.contype = 'c' AND k.convalidated) THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: ck_regla_versiones__ventana_dias_obligatorios ausente o sin validar';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                    WHERE c.oid = 'gapto.regla_versiones'::pg_catalog.regclass
                      AND c.relrowsecurity AND c.relforcerowsecurity) THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: FORCE ROW LEVEL SECURITY no restaurado en regla_versiones';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 19 THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: se esperaban 19 funciones, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 39 THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: se esperaban 39 triggers no internos, hay %', v_n;
    END IF;
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 23 THEN
        RAISE EXCEPTION 'F03-02-0270 POSTCHECK: se esperaban 23 constraint triggers, hay %', v_n;
    END IF;
END
$postcheck$;

RESET ROLE;

COMMIT;
