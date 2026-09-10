-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0240_f03_01_b22_invariantes_participacion_y_alcances.sql
-- Ruta: migrations/0240_f03_01_b22_invariantes_participacion_y_alcances.sql
-- Descripcion: F03-01-B22. Cierra D-091 aplicando las dos decisiones que la
--   auditoria funcion a funcion dejo sobre la mesa.
--
--   La auditoria concluyo que NINGUNO de los seis triggers necesitaba ampliarse
--   a DELETE tal y como estaban escritos: en cuatro casos borrar no puede dejar
--   supervivientes invalidos, y en dos la garantia ya es declarativa. Lo que si
--   aparecio fueron dos defectos distintos, ambos aprobados para correccion.
--
--   PARTE 1 - LA PARTICIPACION DEBE SUMAR EXACTAMENTE 100.
--   fn_check_participacion_suma comprobaba unicamente "suma > 100", es decir
--   que no se repartiera de mas. Nunca exigio que el reparto estuviera
--   completo, de modo que una cuenta o una entidad podia quedar con el 60% de
--   su propiedad declarada y el 40% en ninguna parte. Decision del usuario: la
--   propiedad suma siempre 100. La comprobacion pasa a ser de igualdad.
--
--   Consecuencias de ese cambio, todas deliberadas:
--     a) Ahora SI puede violarse por DELETE, porque borrar baja la suma. Los
--        dos triggers pasan a cubrir INSERT, UPDATE y DELETE. La funcion se
--        reescribe para resolver el padre desde OLD cuando TG_OP = 'DELETE'.
--     b) Los triggers son CONSTRAINT TRIGGER DEFERRABLE INITIALLY DEFERRED
--        (D-081), asi que un reparto construido en varios INSERT dentro de la
--        misma transaccion sigue siendo valido: la igualdad se evalua al
--        COMMIT, no fila a fila.
--     c) Si el padre ya no existe, la funcion no comprueba nada: el borrado en
--        cascada de una cuenta o una entidad no debe fallar por sus propias
--        participaciones.
--     d) Si no queda NINGUNA participacion para ese padre, tampoco comprueba
--        nada. Cero filas significa "la propiedad no esta modelada", que es
--        distinto de "esta mal repartida". Es un juicio explicito: sin el, la
--        ultima fila seria imposible de borrar para siempre.
--     e) El muestreo temporal se amplia. La version anterior solo evaluaba los
--        instantes vigente_desde, de modo que un HUECO entre dos periodos
--        pasaba desapercibido: si A cubre enero a junio y B cubre agosto en
--        adelante, julio no lo comprobaba nadie. Ahora se muestrean tambien los
--        instantes vigente_hasta + 1 dia, con lo que el hueco aparece como una
--        suma de 0 dentro del periodo cubierto y se rechaza.
--
--   PARTE 2 - EL EMPATE DE PRIORIDAD DE BOLSA SE PODIA CREAR DESDE ALCANCES.
--   fn_check_bolsa_prioridad detecta que dos lineas BOLSA del mismo presupuesto
--   empaten en prioridad_consumo cuando sus alcances intersectan, pero vive en
--   presupuesto_lineas. El conflicto depende de presupuesto_linea_alcances, que
--   no tenia trigger: insertar o mover un alcance podia crear el empate sin que
--   nada se disparara. Se anade una funcion puente que reevalua la linea
--   afectada y un constraint trigger sobre alcances.
--
--   Ese trigger cubre INSERT y UPDATE y NO DELETE, y es deliberado: retirar un
--   alcance solo puede reducir intersecciones, nunca crear un empate. Misma
--   disciplina que la auditoria: se cubre el evento que puede romper la
--   invariante, no todos por simetria.
--
--   NOTA SOBRE COMENTARIOS. Los cuerpos de ambas funciones van sin comentarios
--   inline a proposito: prosrc se compara por md5 entre proveedores y contra
--   este fichero, y cualquier comentario dentro del cuerpo es una fuente de
--   divergencia silenciosa. La explicacion vive aqui, en la cabecera, que es
--   donde no puede romper la huella.
--
--   HUELLAS ESPERADAS (md5 de prosrc), identicas en Neon y en Supabase:
--     fn_check_participacion_suma       c909c04f4e0131a32c6552efe601d370  2436 bytes
--     fn_check_bolsa_prioridad_alcance  0eb39ed53b28a3c4657e032f3aaaa037  1524 bytes
--
--   No se modifica 0110 ni 0170: ambas funciones se sustituyen con CREATE OR
--   REPLACE en esta migration nueva, forward-only.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

-- ============================================================
-- PARTE 1: participacion exacta al 100 %
-- ============================================================

CREATE OR REPLACE FUNCTION gapto.fn_check_participacion_suma()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
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

    EXECUTE format('SELECT EXISTS (SELECT 1 FROM gapto.%I WHERE id = $1 FOR UPDATE)',
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
$fn$;

COMMENT ON FUNCTION gapto.fn_check_participacion_suma() IS
    'F03-01-B22: la participacion suma exactamente 100 en todo instante cubierto. Cubre INSERT, UPDATE y DELETE. Cero filas o padre inexistente no se comprueban.';

-- Los eventos de un trigger no se pueden alterar: hay que recrearlo.
DROP TRIGGER trg_cuenta_participaciones__suma_100  ON gapto.cuenta_participaciones;
DROP TRIGGER trg_entidad_participaciones__suma_100 ON gapto.entidad_participaciones;

CREATE CONSTRAINT TRIGGER trg_cuenta_participaciones__suma_100
    AFTER INSERT OR UPDATE OR DELETE ON gapto.cuenta_participaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION gapto.fn_check_participacion_suma('cuenta_id', 'cuentas');

CREATE CONSTRAINT TRIGGER trg_entidad_participaciones__suma_100
    AFTER INSERT OR UPDATE OR DELETE ON gapto.entidad_participaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION gapto.fn_check_participacion_suma('entidad_id', 'entidades');

-- ============================================================
-- PARTE 2: el empate de BOLSA tambien se vigila desde alcances
-- ============================================================

CREATE OR REPLACE FUNCTION gapto.fn_check_bolsa_prioridad_alcance()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
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

    PERFORM 1 FROM gapto.presupuestos WHERE id = v_presupuesto FOR UPDATE;

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
$fn$;

COMMENT ON FUNCTION gapto.fn_check_bolsa_prioridad_alcance() IS
    'F03-01-B22: reevalua el empate de prioridad de BOLSA cuando cambia el alcance. Cubre INSERT y UPDATE; retirar un alcance no puede crear un empate.';

CREATE CONSTRAINT TRIGGER trg_presupuesto_linea_alcances__bolsa_prioridad
    AFTER INSERT OR UPDATE ON gapto.presupuesto_linea_alcances
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION gapto.fn_check_bolsa_prioridad_alcance();

RESET ROLE;

COMMIT;
