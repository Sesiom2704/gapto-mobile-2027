-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0170_f03_01_b12_invariantes_parte2.sql
-- Descripcion: Segunda parte de invariantes multi-fila (F03-00-G-C):
--   sumas temporales/economicas que requieren lock de padre para
--   serializar concurrencia. Reglas citadas literalmente de
--   GaptoMobile_2027_DB_Schema.md donde existen; donde el doc no fija
--   una regla exacta, se documenta la simplificacion adoptada.
--
--   Cubre:
--   1) cuenta_participaciones / entidad_participaciones: suma de
--      porcentaje <=100 en todo instante (sweep-line sobre puntos de
--      inicio de vigencia).
--   2) efecto_atribuciones vs hecho_efectos: COMPLETA exige suma
--      exactamente igual a importe_delta; PARCIAL exige suma <= abs
--      con signo compatible.
--   3) hecho_movimientos_tesoreria vs movimientos_tesoreria: signo
--      igual, suma absoluta <= importe del movimiento.
--   4) inversion_asignaciones_efecto vs hecho_efectos: exige efecto
--      tipo INVERSION, signo igual, suma absoluta <= abs(delta).
--   5) transferencias: salida<0/entrada>0, cuentas distintas mismo
--      owner, igualdad absoluta si misma moneda, lock deterministico
--      de ambos movimientos.
--   6) movimientos_tesoreria.reversion_de_movimiento_id: mismo owner,
--      signo contrario, suma de reversiones activas <= abs(original)
--      cuando comparten moneda.
--   7) presupuesto_lineas BOLSA: dos BOLSA del mismo presupuesto con
--      alcance que intersecta (misma categoria_id o misma entidad_id
--      en presupuesto_linea_alcances) no pueden compartir
--      prioridad_consumo. SIMPLIFICACION DOCUMENTADA: no se resuelve
--      el arbol de descendientes de categorias_financieras (herencia
--      via incluir_descendientes); solo coincidencia directa de
--      categoria_id/entidad_id. Cerrar el caso de arbol queda
--      pendiente y se senala explicitamente al final.
-- Versión: 0.2.0 -- corregido: los 9 triggers pasan a CONSTRAINT
--   TRIGGER ... DEFERRABLE INITIALLY DEFERRED tras detectar en pruebas
--   que un trigger inmediato bloquea transacciones legitimas que
--   construyen la suma completa en varios INSERT/UPDATE dentro de la
--   misma transaccion (ej.: repartir un gasto entre 2 actores).
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ============================================================
-- 1) Participaciones: suma de porcentaje <=100 en todo instante
-- ============================================================
CREATE FUNCTION gapto.fn_check_participacion_suma()
RETURNS trigger AS $fn$
DECLARE
    v_fk_col text := TG_ARGV[0];
    v_parent_table text := TG_ARGV[1];
    v_parent_id uuid;
    v_max_suma numeric;
    v_sql text;
BEGIN
    EXECUTE format('SELECT ($1).%I', v_fk_col) INTO v_parent_id USING NEW;

    EXECUTE format('SELECT 1 FROM gapto.%I WHERE id = $1 FOR UPDATE', v_parent_table) USING v_parent_id;

    v_sql := format(
        'WITH puntos AS (
            SELECT vigente_desde AS punto FROM gapto.%1$I WHERE %2$I = $1
        )
        SELECT max(suma) FROM (
            SELECT (SELECT COALESCE(sum(porcentaje),0) FROM gapto.%1$I t
                     WHERE t.%2$I = $1
                       AND t.vigente_desde <= p.punto
                       AND (t.vigente_hasta IS NULL OR t.vigente_hasta >= p.punto)) AS suma
            FROM puntos p
        ) s',
        TG_TABLE_NAME, v_fk_col
    );
    EXECUTE v_sql INTO v_max_suma USING v_parent_id;

    IF v_max_suma > 100 THEN
        RAISE EXCEPTION 'gapto.%: suma de porcentaje supera 100 en algun instante para %=% (max encontrado=%)',
            TG_TABLE_NAME, v_fk_col, v_parent_id, v_max_suma;
    END IF;

    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_participacion_suma() IS
    'F03-01-B12-P2: sweep-line sobre puntos de inicio de vigencia; suma de porcentaje no puede superar 100 en ningun instante. Argumentos: (columna_fk_padre, tabla_padre).';

CREATE CONSTRAINT TRIGGER trg_cuenta_participaciones__suma_100
    AFTER INSERT OR UPDATE ON gapto.cuenta_participaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_participacion_suma('cuenta_id', 'cuentas');

CREATE CONSTRAINT TRIGGER trg_entidad_participaciones__suma_100
    AFTER INSERT OR UPDATE ON gapto.entidad_participaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_participacion_suma('entidad_id', 'entidades');

-- ============================================================
-- 2) efecto_atribuciones vs hecho_efectos
-- ============================================================
CREATE FUNCTION gapto.fn_check_atribucion_suma()
RETURNS trigger AS $fn$
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
      FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR UPDATE;

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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_atribucion_suma() IS
    'F03-01-B12-P2: COMPLETA exige igualdad exacta con importe_delta; PARCIAL exige suma <= abs(delta) con signo compatible. NO_DISPONIBLE no se fuerza (doc usa "normalmente", no regla dura).';

CREATE CONSTRAINT TRIGGER trg_efecto_atribuciones__suma
    AFTER INSERT OR UPDATE OR DELETE ON gapto.efecto_atribuciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_atribucion_suma();

CREATE CONSTRAINT TRIGGER trg_hecho_efectos__atribucion_suma
    AFTER UPDATE OF importe_delta, estado_atribucion ON gapto.hecho_efectos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_atribucion_suma();

-- ============================================================
-- 3) hecho_movimientos_tesoreria vs movimientos_tesoreria
-- ============================================================
CREATE FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma()
RETURNS trigger AS $fn$
DECLARE
    v_movimiento_id uuid := COALESCE(NEW.movimiento_tesoreria_id, OLD.movimiento_tesoreria_id);
    v_importe numeric;
    v_suma numeric;
BEGIN
    SELECT importe INTO v_importe FROM gapto.movimientos_tesoreria WHERE id = v_movimiento_id FOR UPDATE;
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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma() IS
    'F03-01-B12-P2: suma de importe_asignado con mismo signo y <= abs(importe) del movimiento; inferior es valido (parte sin conciliar).';

CREATE CONSTRAINT TRIGGER trg_hecho_movimientos_tesoreria__suma
    AFTER INSERT OR UPDATE OR DELETE ON gapto.hecho_movimientos_tesoreria
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_hecho_mov_tesoreria_suma();

-- ============================================================
-- 4) inversion_asignaciones_efecto vs hecho_efectos
-- ============================================================
CREATE FUNCTION gapto.fn_check_inversion_asignacion_suma()
RETURNS trigger AS $fn$
DECLARE
    v_efecto_id uuid := COALESCE(NEW.efecto_inversion_id, OLD.efecto_inversion_id);
    v_importe_delta numeric;
    v_tipo_efecto varchar;
    v_suma numeric;
BEGIN
    SELECT importe_delta, tipo_efecto INTO v_importe_delta, v_tipo_efecto
      FROM gapto.hecho_efectos WHERE id = v_efecto_id FOR UPDATE;

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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_inversion_asignacion_suma() IS
    'F03-01-B12-P2: exige efecto tipo INVERSION, signo igual, suma absoluta <= abs(delta). No valida "inversion principal inequivoca" ni bloqueo de reparenting (fuera de alcance de esta pasada).';

CREATE CONSTRAINT TRIGGER trg_inversion_asignaciones_efecto__suma
    AFTER INSERT OR UPDATE OR DELETE ON gapto.inversion_asignaciones_efecto
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_asignacion_suma();

-- ============================================================
-- 5) transferencias: estructura de signos, cuentas, moneda
-- ============================================================
CREATE FUNCTION gapto.fn_check_transferencia_estructura()
RETURNS trigger AS $fn$
DECLARE
    v_salida RECORD;
    v_entrada RECORD;
    v_id1 uuid;
    v_id2 uuid;
BEGIN
    v_id1 := LEAST(NEW.movimiento_salida_id, NEW.movimiento_entrada_id);
    v_id2 := GREATEST(NEW.movimiento_salida_id, NEW.movimiento_entrada_id);
    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = v_id1 FOR UPDATE;
    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = v_id2 FOR UPDATE;

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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_transferencia_estructura() IS
    'F03-01-B12-P2: salida<0, entrada>0, cuentas distintas, mismo owner, igualdad absoluta si misma moneda. Lock deterministico de ambos movimientos por id.';

CREATE CONSTRAINT TRIGGER trg_transferencias__estructura
    AFTER INSERT OR UPDATE ON gapto.transferencias
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_transferencia_estructura();

-- ============================================================
-- 6) movimientos_tesoreria: reversiones (owner, signo, no sobrerrevertir)
-- ============================================================
CREATE FUNCTION gapto.fn_check_reversion_movimiento()
RETURNS trigger AS $fn$
DECLARE
    v_original RECORD;
    v_nuevo_owner uuid;
    v_nueva_moneda varchar;
    v_suma_reversiones numeric;
BEGIN
    IF NEW.reversion_de_movimiento_id IS NULL THEN
        RETURN NEW;
    END IF;

    PERFORM 1 FROM gapto.movimientos_tesoreria WHERE id = NEW.reversion_de_movimiento_id FOR UPDATE;

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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_reversion_movimiento() IS
    'F03-01-B12-P2: reversion conserva owner, signo contrario; en misma moneda la suma de reversiones ACTIVAS no puede superar abs(importe original).';

CREATE CONSTRAINT TRIGGER trg_movimientos_tesoreria__reversion
    AFTER INSERT OR UPDATE OF reversion_de_movimiento_id, importe, estado ON gapto.movimientos_tesoreria
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_reversion_movimiento();

-- ============================================================
-- 7) presupuesto_lineas: BOLSA -- prioridad no puede empatar si el
--    alcance intersecta (SIMPLIFICADO: sin resolver arbol de
--    categorias_financieras; solo coincidencia directa)
-- ============================================================
CREATE FUNCTION gapto.fn_check_bolsa_prioridad()
RETURNS trigger AS $fn$
DECLARE
    v_conflicto uuid;
BEGIN
    IF NEW.tipo_linea <> 'BOLSA' THEN
        RETURN NEW;
    END IF;

    PERFORM 1 FROM gapto.presupuestos WHERE id = NEW.presupuesto_id FOR UPDATE;

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
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_bolsa_prioridad() IS
    'F03-01-B12-P2: dos BOLSA del mismo presupuesto con alcance que intersecta no pueden compartir prioridad_consumo. SIMPLIFICADO: solo coincidencia directa de categoria_id/entidad_id; no resuelve herencia via categorias_financieras ni incluir_descendientes. Se dispara sobre presupuesto_lineas: solo detecta el conflicto si el alcance de NEW ya existe en el momento del INSERT/UPDATE de la linea; en un flujo linea-luego-alcance esto puede no disparar en el momento correcto y requiere revision.';

CREATE CONSTRAINT TRIGGER trg_presupuesto_lineas__bolsa_prioridad
    AFTER INSERT OR UPDATE OF prioridad_consumo, tipo_linea ON gapto.presupuesto_lineas
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_bolsa_prioridad();

RESET ROLE;

DO $gapto$
DECLARE
    v_funcs integer;
    v_triggers integer;
BEGIN
    SELECT count(*) INTO v_funcs
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'gapto' AND p.proname IN (
        'fn_check_participacion_suma','fn_check_atribucion_suma',
        'fn_check_hecho_mov_tesoreria_suma','fn_check_inversion_asignacion_suma',
        'fn_check_transferencia_estructura','fn_check_reversion_movimiento',
        'fn_check_bolsa_prioridad'
     );
    SELECT count(*) INTO v_triggers
      FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='gapto' AND NOT t.tgisinternal
       AND t.tgname IN (
        'trg_cuenta_participaciones__suma_100','trg_entidad_participaciones__suma_100',
        'trg_efecto_atribuciones__suma','trg_hecho_efectos__atribucion_suma',
        'trg_hecho_movimientos_tesoreria__suma','trg_inversion_asignaciones_efecto__suma',
        'trg_transferencias__estructura','trg_movimientos_tesoreria__reversion',
        'trg_presupuesto_lineas__bolsa_prioridad'
       );
    IF v_funcs <> 7 THEN
        RAISE EXCEPTION 'POSTCHECK: esperadas 7 funciones nuevas; encontradas=%', v_funcs;
    END IF;
    IF v_triggers <> 9 THEN
        RAISE EXCEPTION 'POSTCHECK: esperados 9 triggers nuevos; encontrados=%', v_triggers;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
