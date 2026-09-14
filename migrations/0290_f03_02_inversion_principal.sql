-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0290_f03_02_inversion_principal.sql
-- Ruta: migrations/0290_f03_02_inversion_principal.sql
-- Descripcion: FASE 03 / F03-02. Ultimo bloque de la subfase: D-080,
--   inversion principal inequivoca por efecto, con destinos dentro de su
--   rama. No reabre ninguna migration anterior.
--
--   REGLA. Para un efecto e cuyo estado FINAL sea tipo_efecto = 'INVERSION':
--     principal(e) = filas de hecho_entidades con hecho_id = e.hecho_id,
--                    efecto_id = e.id, principal = true y entidad con subtipo
--                    en inversiones.
--     card(principal(e)) <= 1 siempre.
--     Si existe alguna asignacion de e, card(principal(e)) = 1.
--     Toda asignacion de e apunta a principal(e) o a un descendiente
--     ESTRICTO suyo en el arbol inversion_padre_entidad_id, evaluado sobre el
--     estado FINAL y con recorrido terminante.
--
--   La principal vive en hecho_entidades y a NIVEL DE EFECTO. El canon fija
--   que la relacion hecho/efecto -> entidad se expresa exclusivamente en
--   hecho_entidades y que no existe una entidad objetivo redundante en
--   hecho_efectos; por eso no se anade ninguna columna al efecto. Una
--   principal declarada a nivel de hecho, con efecto_id NULL, no satisface
--   D-080: la regla es de efecto.
--
--   NO se usa un indice unico parcial para imponer la unicidad. Un
--   UNIQUE (efecto_id) WHERE principal no puede consultar por JOIN si la
--   entidad tiene subtipo de inversion, asi que impondria una unica entidad
--   principal de CUALQUIER tipo por efecto y cambiaria el significado
--   generico de la columna principal, que no se redefine aqui. La unicidad
--   especifica de inversion es una invariante diferida que inspecciona el
--   subtipo.
--
--   TIPO_RELACION NO PARTICIPA EN EL PREDICADO. Una fila cuenta como
--   principal por la marca booleana principal y por el subtipo de la entidad,
--   con cualquiera de los cuatro tipo_relacion. El canon separa
--   deliberadamente principal de tipo_relacion y 0290 no inventa una ontologia
--   nueva. Consecuencia deliberada: dos filas hacia la MISMA entidad de
--   inversion con tipo_relacion distinto y ambas principal = true son DOS
--   principales y se rechazan; el escritor debe marcar una sola. Por el mismo
--   motivo tipo_relacion NO figura en el UPDATE OF del trigger: cambiarlo no
--   altera si una fila cuenta.
--
--   OBLIGATORIEDAD. La principal se exige solo cuando hay asignaciones. D-017
--   permite que el reparto 1:N quede pendiente, de modo que un efecto de
--   inversion puede existir sin principal y sin asignaciones, y una principal
--   puede conocerse y persistirse antes del reparto.
--
--   ALCANCE. D-080 no se aplica a VALOR_ACTIVO ni a GASTO, INGRESO, DEUDA o
--   DERECHO_COBRO, aunque tengan asociaciones en hecho_entidades. Tampoco se
--   impone rol_estructura: no se exige que la principal sea CONTENEDOR ni que
--   los destinos sean POSICION, porque D-045 separo deliberadamente
--   rol_estructura de tipo_producto y convertirlo en condicion del reparto
--   seria semantica nueva.
--
--   NO se inventa congelacion historica ni lifecycle: una inversion CERRADA
--   puede recibir asignaciones, porque no existe ninguna regla aprobada que
--   lo impida y prohibirlo aqui seria crear temporalidad nueva. El
--   reparenting garantiza que tras el movimiento todo destino sigue dentro de
--   la rama de su principal, pero NO garantiza que el arbol historico
--   conserve la ubicacion que tenia cuando ocurrio el hecho: eso exigiria
--   jerarquia versionada y queda como riesgo residual registrado.
--
--   LOCKS. Clave propia (INVERSIONES, owner), la misma familia logica que ya
--   usa D-123 para esta jerarquia. El advisory es el UNICO lock root explicito
--   de los dos validadores: ninguno de ellos bloquea filas de hecho_efectos.
--   Protocolo unico en todas las rutas:
--     owners de la invocacion -> advisory (INVERSIONES, owner) en orden de
--     UUID -> RELECTURA SQL SEPARADA del estado FINAL -> validacion.
--   Una invocacion que conoce OLD y NEW con owners distintos adquiere ambos
--   advisory ordenados. NO se garantiza un orden global entre varias
--   invocaciones diferidas de una misma transaccion multi-owner; ese 40P01
--   residual se resuelve con reintento de transaccion completa conforme a
--   D-114. Un 40P01 sistematico sobre un unico owner es FAIL_LIVENESS.
--
--   POR QUE NO HAY ROW LOCK. Un UPDATE de hecho_efectos adquiere el row lock
--   del efecto en su propia sentencia, antes de que el constraint trigger
--   diferido pueda pedir el advisory. Si el validador bloqueara despues la
--   fila, esa transaccion haria fila -> advisory mientras otra que inserta una
--   asignacion hace advisory -> fila: ciclo puro y deadlock sistematico sobre
--   un unico owner y un unico efecto, medido 5 de 5 en la replica local. La
--   fila del efecto tampoco podia serializar el reparenting del arbol, porque
--   los conjuntos de filas de ambas transacciones son disjuntos. El advisory
--   por owner es el unico dominio comun a suma, principal, asignaciones,
--   reparenting, alta de subtipo y cambio de tipo del efecto.
--
--   REESCRITURA DE fn_check_inversion_asignacion_suma. Se reemplaza
--   forward-only, sin tocar su migration historica. Conserva intactas todas
--   sus garantias: efecto INVERSION cuando hay asignaciones, signo compatible,
--   suma absoluta no superior al efecto, fail-closed por visibilidad y
--   revalidacion del efecto antiguo y del nuevo cuando una asignacion cambia
--   de efecto. Cambia unicamente su punto de serializacion, que pasa de
--   FOR NO KEY UPDATE sobre la fila del efecto a advisory (INVERSIONES,
--   owner). El advisory es estrictamente mas grueso.
--
--   EVENTOS. D-080 depende de DOS predicados y ambos pueden cambiar sin tocar
--   hecho_entidades, por lo que ambos reciben senal:
--     "esta entidad es una inversion" -> entidades UPDATE OF tipo_entidad e
--        inversiones INSERT, porque el subtipo se materializa con filas de
--        inversiones y los guards de coherencia son diferidos;
--     "este efecto es de tipo INVERSION" -> hecho_efectos UPDATE OF
--        tipo_efecto, porque tipo_efecto solo tiene un CHECK de conjunto
--        cerrado, no un guard de inmutabilidad, y gapto_runtime conserva
--        UPDATE sobre la tabla. Sin esta senal, un efecto GASTO con dos
--        inversiones marcadas principal pasaria a INVERSION sin que ningun
--        validador de D-080 se ejecutase.
--   Los eventos son solo senal: la validacion no confia en OLD/NEW, toma los
--   advisory y relee el estado final.
--
--   inversiones DELETE NO recibe trigger. No es un olvido, es un evento
--   equivalente demostrado: para que un DELETE dejase un efecto con
--   asignaciones y sin principal valida tendria que borrarse una inversion
--   que es principal o ancestro de un destino, y lo impiden ya la FK de
--   asignaciones contra inversiones y la FK inversion_padre_entidad_id contra
--   inversiones, ambas RESTRICT. Si el DELETE forma parte de una transicion
--   de subtipo, la senal la da entidades UPDATE OF tipo_entidad. Anadir el
--   trigger protegeria un estado inalcanzable.
--
--   hecho_entidades SI escucha DELETE: borrar la unica fila principal
--   mientras sobreviven asignaciones deja asignaciones > 0 y principal = 0.
--   Que gapto_runtime no tenga DELETE no basta, porque la integridad debe
--   sobrevivir tambien a roles privilegiados y a migrations.
--   inversion_asignaciones_efecto NO escucha DELETE para D-080: retirar un
--   destino solo reduce el conjunto, y si desaparece la ultima asignacion la
--   principal deja de ser obligatoria. Su DELETE sigue siendo relevante para
--   la invariante de suma, que es independiente.
--
--   RAMA ACOTADA AL OWNER. El recorrido de descendientes se restringe a
--   entidades del owner del efecto. Los dos extremos, principal y destino, ya
--   son same-owner por las FK compuestas de 0288, pero el same-owner de
--   inversion_padre_entidad_id lo impone una policy, no una FK, y por tanto no
--   sobrevive a BYPASSRLS. Acotar el recorrido es estrictamente mas fuerte.
--
--   CONTRATO FISICO. +1 funcion, +6 triggers no internos, +6 constraint
--   triggers y por tanto +6 constraints. Tablas, columnas, FK, UNIQUE,
--   EXCLUDE, indices, policies, GRANTs y vistas NO cambian. La huella de
--   constraints, la de triggers y la de funciones si cambian; esta ultima
--   ademas por la reescritura de fn_check_inversion_asignacion_suma. Los
--   valores exactos los fija el postcheck y se recalculan con
--   scripts/postgres/huellas_d111.sql, nunca se transcriben.
--
-- Decision: D-080; P1..P4 de la revision de 0290
-- Versión: 0.2.0
-- Changelog:
--   0.2.0 - P1: senal hecho_efectos UPDATE OF tipo_efecto, que cerraba un
--           fail-open alcanzable por gapto_runtime. P2: se fija que
--           tipo_relacion no participa en el predicado. P3: advisory de los
--           owners conocidos por cada invocacion, ordenados por UUID. P4: el
--           advisory pasa a ser el unico lock root; se retira el
--           FOR NO KEY UPDATE sobre hecho_efectos de los dos validadores tras
--           medir un deadlock sistematico 5/5 en la replica local. Ademas:
--           fail-closed por visibilidad del efecto que motiva el evento,
--           recorrido de rama acotado al owner, LIMIT 1 con ORDER BY,
--           postcheck endurecido a contrato completo y correccion del
--           contrato declarado en la cabecera.
--   0.1.0 - Version inicial no aplicada.
-- ============================================================

BEGIN;

DO $precheck_0290$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-02-0290 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    IF to_regclass('gapto.efecto_cuentas') IS NULL THEN
        v_rep := v_rep || ' falta 0286;';
    END IF;
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.inversion_asignaciones_efecto'::pg_catalog.regclass
       AND a.attname IN ('owner_user_id', 'hecho_id') AND a.attnotnull AND NOT a.attisdropped;
    IF v_n <> 2 THEN
        v_rep := v_rep || ' falta 0288 sobre inversion_asignaciones_efecto;';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM (SELECT he.efecto_id
              FROM gapto.hecho_entidades he
              JOIN gapto.hecho_efectos e ON e.id = he.efecto_id AND e.hecho_id = he.hecho_id
              JOIN gapto.inversiones i ON i.entidad_id = he.entidad_id
             WHERE he.principal AND e.tipo_efecto = 'INVERSION'
             GROUP BY he.efecto_id HAVING pg_catalog.count(*) > 1) AS t;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' efectos con varias inversiones principales=%s;', v_n);
    END IF;

    SELECT pg_catalog.count(DISTINCT a.efecto_inversion_id) INTO v_n
      FROM gapto.inversion_asignaciones_efecto a
     WHERE NOT EXISTS (SELECT 1 FROM gapto.hecho_entidades he
                        JOIN gapto.inversiones i ON i.entidad_id = he.entidad_id
                       WHERE he.efecto_id = a.efecto_inversion_id
                         AND he.hecho_id = a.hecho_id AND he.principal);
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' efectos con asignaciones y sin principal=%s;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.inversion_asignaciones_efecto a
      JOIN LATERAL (SELECT he.entidad_id AS p FROM gapto.hecho_entidades he
                     JOIN gapto.inversiones i ON i.entidad_id = he.entidad_id
                    WHERE he.efecto_id = a.efecto_inversion_id
                      AND he.hecho_id = a.hecho_id AND he.principal
                    ORDER BY he.entidad_id LIMIT 1) pr ON true
     WHERE a.inversion_entidad_id <> pr.p
       AND NOT EXISTS (
           WITH RECURSIVE d(n) AS (
               SELECT i.entidad_id FROM gapto.inversiones i
                 JOIN gapto.entidades en ON en.id = i.entidad_id
                WHERE i.inversion_padre_entidad_id = pr.p
                  AND en.owner_user_id = a.owner_user_id
               UNION ALL
               SELECT i.entidad_id FROM d JOIN gapto.inversiones i
                      ON i.inversion_padre_entidad_id = d.n
                 JOIN gapto.entidades en ON en.id = i.entidad_id
                WHERE en.owner_user_id = a.owner_user_id
           ) CYCLE n SET es_ciclo USING ruta
           SELECT 1 FROM d WHERE d.n = a.inversion_entidad_id);
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' asignaciones fuera de la rama de su principal=%s;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0290 PRECHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-02-0290 PRECHECK: OK';
END;
$precheck_0290$;

SET ROLE gapto_owner;

-- ============================================================
-- 1) Validador de D-080
-- ============================================================
CREATE FUNCTION gapto.fn_check_inversion_principal()
RETURNS trigger AS $fn$
DECLARE
    v_owners      uuid[];
    v_o           uuid;
    v_ancla       uuid;
    v_efectos     uuid[];
    v_nuevo       uuid;
    v_e           uuid;
    v_tipo        varchar;
    v_hecho       uuid;
    v_owner_e     uuid;
    v_principales integer;
    v_principal   uuid;
    v_asignadas   integer;
    v_fuera       uuid;
BEGIN
    IF TG_TABLE_NAME IN ('inversion_asignaciones_efecto', 'hecho_entidades') THEN
        SELECT array_agg(DISTINCT o ORDER BY o) INTO v_owners
          FROM unnest(ARRAY[CASE WHEN TG_OP <> 'DELETE' THEN NEW.owner_user_id END,
                            CASE WHEN TG_OP <> 'INSERT' THEN OLD.owner_user_id END]) AS u(o)
         WHERE o IS NOT NULL;
        IF TG_OP <> 'DELETE' THEN
            IF TG_TABLE_NAME = 'inversion_asignaciones_efecto' THEN
                v_nuevo := NEW.efecto_inversion_id;
            ELSE
                v_nuevo := NEW.efecto_id;
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'inversiones' THEN
        v_ancla := NEW.entidad_id;
        SELECT ARRAY[e.owner_user_id] INTO v_owners
          FROM gapto.entidades e WHERE e.id = v_ancla;
    ELSIF TG_TABLE_NAME = 'entidades' THEN
        v_ancla := NEW.id;
        v_owners := ARRAY[NEW.owner_user_id];
    ELSIF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_nuevo := NEW.id;
        SELECT ARRAY[h.owner_user_id] INTO v_owners
          FROM gapto.hechos_financieros h WHERE h.id = NEW.hecho_id;
    ELSE
        RAISE EXCEPTION 'fn_check_inversion_principal: tabla % no soportada', TG_TABLE_NAME;
    END IF;

    IF v_owners IS NULL OR pg_catalog.cardinality(v_owners) = 0 OR v_owners[1] IS NULL THEN
        RAISE EXCEPTION 'gapto.%: VISIBILIDAD - no se puede resolver el owner al validar D-080 (contexto de tenant ausente o distinto del de la escritura)',
            TG_TABLE_NAME;
    END IF;

    FOREACH v_o IN ARRAY v_owners
    LOOP
        PERFORM pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(v_o::text));
    END LOOP;

    IF TG_TABLE_NAME = 'inversion_asignaciones_efecto' THEN
        SELECT array_agg(DISTINCT x ORDER BY x) INTO v_efectos
          FROM unnest(ARRAY[CASE WHEN TG_OP <> 'DELETE' THEN NEW.efecto_inversion_id END,
                            CASE WHEN TG_OP <> 'INSERT' THEN OLD.efecto_inversion_id END]) AS u(x)
         WHERE x IS NOT NULL;
    ELSIF TG_TABLE_NAME = 'hecho_entidades' THEN
        SELECT array_agg(DISTINCT x ORDER BY x) INTO v_efectos
          FROM unnest(ARRAY[CASE WHEN TG_OP <> 'DELETE' THEN NEW.efecto_id END,
                            CASE WHEN TG_OP <> 'INSERT' THEN OLD.efecto_id END]) AS u(x)
         WHERE x IS NOT NULL;
    ELSIF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_efectos := ARRAY[NEW.id];
    ELSIF TG_TABLE_NAME = 'inversiones' AND TG_OP = 'UPDATE' THEN
        SELECT array_agg(DISTINCT a.efecto_inversion_id ORDER BY a.efecto_inversion_id)
          INTO v_efectos
          FROM gapto.inversion_asignaciones_efecto a
         WHERE a.owner_user_id = ANY (v_owners);
    ELSE
        SELECT array_agg(DISTINCT he.efecto_id ORDER BY he.efecto_id) INTO v_efectos
          FROM gapto.hecho_entidades he
         WHERE he.entidad_id = v_ancla AND he.efecto_id IS NOT NULL;
    END IF;

    IF v_efectos IS NULL OR pg_catalog.cardinality(v_efectos) = 0 THEN
        RETURN NULL;
    END IF;

    FOREACH v_e IN ARRAY v_efectos
    LOOP
        SELECT e.tipo_efecto, e.hecho_id, h.owner_user_id
          INTO v_tipo, v_hecho, v_owner_e
          FROM gapto.hecho_efectos e
          JOIN gapto.hechos_financieros h ON h.id = e.hecho_id
         WHERE e.id = v_e;
        IF NOT FOUND THEN
            IF v_e = v_nuevo THEN
                RAISE EXCEPTION 'gapto.%: VISIBILIDAD - el efecto % no es visible al validar D-080 (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_e;
            END IF;
            CONTINUE;
        END IF;
        IF v_tipo IS DISTINCT FROM 'INVERSION' THEN
            CONTINUE;
        END IF;

        SELECT pg_catalog.count(*) INTO v_principales
          FROM gapto.hecho_entidades he
          JOIN gapto.inversiones i ON i.entidad_id = he.entidad_id
         WHERE he.efecto_id = v_e AND he.hecho_id = v_hecho AND he.principal;

        IF v_principales > 1 THEN
            RAISE EXCEPTION 'hecho_entidades: el efecto % tiene % inversiones marcadas principal; D-080 exige como maximo una',
                v_e, v_principales;
        END IF;

        SELECT pg_catalog.count(*) INTO v_asignadas
          FROM gapto.inversion_asignaciones_efecto a WHERE a.efecto_inversion_id = v_e;

        IF v_asignadas = 0 THEN
            CONTINUE;
        END IF;

        IF v_principales = 0 THEN
            RAISE EXCEPTION 'inversion_asignaciones_efecto: el efecto % tiene % asignaciones y ninguna inversion principal; D-080 la exige cuando hay reparto',
                v_e, v_asignadas;
        END IF;

        SELECT he.entidad_id INTO v_principal
          FROM gapto.hecho_entidades he
          JOIN gapto.inversiones i ON i.entidad_id = he.entidad_id
         WHERE he.efecto_id = v_e AND he.hecho_id = v_hecho AND he.principal
         ORDER BY he.entidad_id
         LIMIT 1;

        SELECT a.inversion_entidad_id INTO v_fuera
          FROM gapto.inversion_asignaciones_efecto a
         WHERE a.efecto_inversion_id = v_e
           AND a.inversion_entidad_id <> v_principal
           AND NOT EXISTS (
               WITH RECURSIVE d(n) AS (
                   SELECT i.entidad_id FROM gapto.inversiones i
                     JOIN gapto.entidades en ON en.id = i.entidad_id
                    WHERE i.inversion_padre_entidad_id = v_principal
                      AND en.owner_user_id = v_owner_e
                   UNION ALL
                   SELECT i.entidad_id FROM d JOIN gapto.inversiones i
                          ON i.inversion_padre_entidad_id = d.n
                     JOIN gapto.entidades en ON en.id = i.entidad_id
                    WHERE en.owner_user_id = v_owner_e
               ) CYCLE n SET es_ciclo USING ruta
               SELECT 1 FROM d WHERE d.n = a.inversion_entidad_id)
         ORDER BY a.inversion_entidad_id
         LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION 'inversion_asignaciones_efecto: el efecto % asigna a la inversion %, que no es su principal % ni un descendiente suyo; D-080 exige destinos dentro de la rama',
                v_e, v_fuera, v_principal;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

-- ============================================================
-- 2) Reescritura forward-only del validador de suma: advisory como lock root
-- ============================================================
CREATE OR REPLACE FUNCTION gapto.fn_check_inversion_asignacion_suma()
RETURNS trigger AS $fn$
DECLARE
    v_owners        uuid[];
    v_o             uuid;
    v_efectos       uuid[];
    v_nuevo         uuid;
    v_efecto_id     uuid;
    v_importe_delta numeric;
    v_tipo_efecto   varchar;
    v_filas         bigint;
    v_suma          numeric;
BEGIN
    IF TG_TABLE_NAME = 'hecho_efectos' THEN
        v_nuevo := NEW.id;
        v_efectos := ARRAY[NEW.id];
        SELECT ARRAY[h.owner_user_id] INTO v_owners
          FROM gapto.hechos_financieros h WHERE h.id = NEW.hecho_id;
    ELSE
        IF TG_OP <> 'DELETE' THEN
            v_nuevo := NEW.efecto_inversion_id;
        END IF;
        SELECT array_agg(DISTINCT o ORDER BY o) INTO v_owners
          FROM unnest(ARRAY[CASE WHEN TG_OP <> 'DELETE' THEN NEW.owner_user_id END,
                            CASE WHEN TG_OP <> 'INSERT' THEN OLD.owner_user_id END]) AS u(o)
         WHERE o IS NOT NULL;
        SELECT array_agg(DISTINCT x ORDER BY x) INTO v_efectos
          FROM unnest(ARRAY[CASE WHEN TG_OP <> 'DELETE' THEN NEW.efecto_inversion_id END,
                            CASE WHEN TG_OP <> 'INSERT' THEN OLD.efecto_inversion_id END]) AS u(x)
         WHERE x IS NOT NULL;
    END IF;

    IF v_owners IS NULL OR pg_catalog.cardinality(v_owners) = 0 OR v_owners[1] IS NULL THEN
        RAISE EXCEPTION 'gapto.%: VISIBILIDAD - no se puede resolver el owner al validar la asignacion de inversion (contexto de tenant ausente o distinto del de la escritura)',
            TG_TABLE_NAME;
    END IF;

    FOREACH v_o IN ARRAY v_owners
    LOOP
        PERFORM pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(v_o::text));
    END LOOP;

    FOREACH v_efecto_id IN ARRAY v_efectos
    LOOP
        SELECT e.importe_delta, e.tipo_efecto INTO v_importe_delta, v_tipo_efecto
          FROM gapto.hecho_efectos e WHERE e.id = v_efecto_id;
        IF NOT FOUND THEN
            IF v_efecto_id = v_nuevo THEN
                RAISE EXCEPTION 'gapto.%: VISIBILIDAD - el efecto % no es visible al validar la asignacion de inversion (contexto de tenant ausente o distinto del de la escritura)',
                    TG_TABLE_NAME, v_efecto_id;
            END IF;
            CONTINUE;
        END IF;

        SELECT pg_catalog.count(*), COALESCE(pg_catalog.sum(a.importe_asignado), 0)
          INTO v_filas, v_suma
          FROM gapto.inversion_asignaciones_efecto a WHERE a.efecto_inversion_id = v_efecto_id;

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
$fn$ LANGUAGE plpgsql;

-- ============================================================
-- 3) Triggers de D-080
-- ============================================================
CREATE CONSTRAINT TRIGGER trg_inversion_asignaciones_efecto__d080
    AFTER INSERT OR UPDATE OF efecto_inversion_id, inversion_entidad_id, owner_user_id, hecho_id
    ON gapto.inversion_asignaciones_efecto
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

CREATE CONSTRAINT TRIGGER trg_hecho_entidades__d080
    AFTER INSERT OR DELETE OR UPDATE OF hecho_id, efecto_id, entidad_id, principal, owner_user_id
    ON gapto.hecho_entidades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

CREATE CONSTRAINT TRIGGER trg_hecho_efectos__d080_tipo_efecto
    AFTER UPDATE OF tipo_efecto ON gapto.hecho_efectos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

CREATE CONSTRAINT TRIGGER trg_inversiones__d080_reparenting
    AFTER UPDATE OF inversion_padre_entidad_id ON gapto.inversiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

CREATE CONSTRAINT TRIGGER trg_inversiones__d080_alta_subtipo
    AFTER INSERT ON gapto.inversiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

CREATE CONSTRAINT TRIGGER trg_entidades__d080_subtipo
    AFTER UPDATE OF tipo_entidad ON gapto.entidades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_inversion_principal();

RESET ROLE;

DO $postcheck_0290$
DECLARE
    v_n   bigint;
    v_rep text := '';
    r     record;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_inversion_principal', 'fn_check_inversion_asignacion_suma')
       AND pg_catalog.pg_get_userbyid(p.proowner) = 'gapto_owner';
    IF v_n <> 2 THEN
        v_rep := v_rep || pg_catalog.format(' validadores con owner gapto_owner=%s (esperados 2);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_inversion_principal', 'fn_check_inversion_asignacion_suma')
       AND p.prosrc LIKE '%pg_advisory_xact_lock(hashtext(''gapto:INVERSIONES'')%';
    IF v_n <> 2 THEN
        v_rep := v_rep || pg_catalog.format(' validadores que toman el advisory=%s (esperados 2);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_inversion_principal', 'fn_check_inversion_asignacion_suma')
       AND (p.prosrc LIKE '%FOR UPDATE%' OR p.prosrc LIKE '%FOR NO KEY UPDATE%'
            OR p.prosrc LIKE '%FOR SHARE%' OR p.prosrc LIKE '%FOR KEY SHARE%');
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' validadores con row lock explicito=%s (P4 exige 0);', v_n);
    END IF;

    FOR r IN
        SELECT t.tgname, c.relname, t.tgtype, t.tgconstraint, t.tgdeferrable, t.tginitdeferred
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND NOT t.tgisinternal AND t.tgname LIKE '%d080%'
    LOOP
        IF r.tgconstraint = 0 OR NOT r.tgdeferrable OR NOT r.tginitdeferred THEN
            v_rep := v_rep || pg_catalog.format(' %s no es CONSTRAINT TRIGGER DEFERRABLE INITIALLY DEFERRED;', r.tgname);
        END IF;
        IF (r.tgtype & 2) <> 0 THEN
            v_rep := v_rep || pg_catalog.format(' %s no es AFTER;', r.tgname);
        END IF;
    END LOOP;

    FOR r IN
        SELECT x.tgname, x.tabla, x.eventos FROM (VALUES
            ('trg_inversion_asignaciones_efecto__d080', 'inversion_asignaciones_efecto', 4 + 16),
            ('trg_hecho_entidades__d080',               'hecho_entidades',               4 + 8 + 16),
            ('trg_hecho_efectos__d080_tipo_efecto',     'hecho_efectos',                 16),
            ('trg_inversiones__d080_reparenting',       'inversiones',                   16),
            ('trg_inversiones__d080_alta_subtipo',      'inversiones',                   4),
            ('trg_entidades__d080_subtipo',             'entidades',                     16)
        ) AS x(tgname, tabla, eventos)
    LOOP
        SELECT pg_catalog.count(*) INTO v_n
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
           AND NOT t.tgisinternal AND t.tgname = r.tgname AND c.relname = r.tabla
           AND (t.tgtype & (4 + 8 + 16)) = r.eventos
           AND t.tgfoid = 'gapto.fn_check_inversion_principal()'::pg_catalog.regprocedure;
        IF v_n <> 1 THEN
            v_rep := v_rep || pg_catalog.format(' falta o difiere %s sobre %s;', r.tgname, r.tabla);
        END IF;
    END LOOP;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND NOT t.tgisinternal AND t.tgname LIKE '%d080%';
    IF v_n <> 6 THEN
        v_rep := v_rep || pg_catalog.format(' triggers de D-080=%s (esperados 6);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid = 'gapto.inversiones'::pg_catalog.regclass
       AND NOT t.tgisinternal AND t.tgname LIKE '%d080%'
       AND (t.tgtype & 8) <> 0;
    IF v_n <> 0 THEN
        v_rep := v_rep || ' existe un trigger de D-080 sobre DELETE de inversiones; es un evento equivalente y no debe crearse;';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 26 THEN
        v_rep := v_rep || pg_catalog.format(' funciones del esquema=%s (esperadas 26);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 54 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos=%s (esperados 54);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 37 THEN
        v_rep := v_rep || pg_catalog.format(' constraint triggers=%s (esperados 37);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r';
    IF v_n <> 80 THEN
        v_rep := v_rep || pg_catalog.format(' tablas=%s (esperadas 80);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 174 THEN
        v_rep := v_rep || pg_catalog.format(' FK=%s (esperadas 174);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 284 THEN
        v_rep := v_rep || pg_catalog.format(' indices=%s (esperados 284);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        v_rep := v_rep || pg_catalog.format(' policies=%s (esperadas 82);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0290 POSTCHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-02-0290 POSTCHECK: OK';
END;
$postcheck_0290$;

COMMIT;
