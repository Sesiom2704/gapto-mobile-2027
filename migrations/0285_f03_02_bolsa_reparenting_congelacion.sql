-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0285_f03_02_bolsa_reparenting_congelacion.sql
-- Ruta: migrations/0285_f03_02_bolsa_reparenting_congelacion.sql
-- Descripcion: FASE 03 / F03-02. Correccion forward-only posterior a 0280.
--   No reabre F03-01 ni edita la cadena congelada. Queda fuera D-080 (0290).
--
--   1. D-121, exclusividad de BOLSAS. Dos lineas L1, L2 de un presupuesto
--      son potencialmente solapables si ambas son BOLSA, tienen la misma
--      naturaleza_economica (GASTO solo captura efectos GASTO, INGRESO solo
--      INGRESO; el signo del delta no cambia la naturaleza) y existe un par
--      de alcances a1 (de L1), a2 (de L2) con cat_compat(a1,a2):
--        a1.cat NULL o a2.cat NULL (comodin), o a1.cat = a2.cat, o
--        (a1.desc y a2.cat es descendiente ESTRICTO de a1.cat), o
--        (a2.desc y a1.cat es descendiente ESTRICTO de a2.cat),
--      evaluado sobre la jerarquia FINAL con recorrido terminante (CYCLE).
--      ent_compat = TRUE: la entidad NUNCA demuestra disjuncion, porque
--      hecho_entidades es N:M y un efecto puede estar vinculado a varias
--      entidades (N2-6). Si L1 y L2 solapan, ambas prioridades deben ser NOT
--      NULL y distintas; si no solapan, NULL o empate son libres. NULL nunca
--      equivale a 0. La comprobacion por pares es suficiente. 0285 no fija si
--      gana el numero mayor o el menor: solo garantiza un ganador unico.
--      Corrige N2-1 (fail-open categoria frente a entidad), N2-2 (falso
--      positivo X∩E frente a Y∩E con ramas disjuntas), N2-3 (jerarquia),
--      N2-4 (naturaleza), N2-5 (prioridad NULL) y N2-6 (entidad multivaluada).
--      La invariante vale en TODOS los estados del presupuesto (BORRADOR,
--      ACTIVO, SUSTITUIDO, CERRADO).
--      Validacion diferida: el evento solo senala el presupuesto a
--      revalidar; se toma pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'),
--      hashtext(owner)) (clave de 0280, compartida con el reparenting), se
--      bloquea la fila del presupuesto con FOR NO KEY UPDATE y se relee el
--      estado FINAL completo del presupuesto (lineas, alcances, categorias).
--      Funciones reescritas (mismo nombre, mismo contrato de trigger):
--        gapto.fn_check_bolsa_prioridad        lineas y reparenting
--        gapto.fn_check_bolsa_prioridad_alcance alcances
--      Eventos: trg_presupuesto_lineas__bolsa_prioridad pasa a AFTER INSERT
--      OR UPDATE OF presupuesto_id, tipo_linea, naturaleza_economica,
--      prioridad_consumo (antes faltaban presupuesto_id y
--      naturaleza_economica). trg_presupuesto_linea_alcances__bolsa_prioridad
--      conserva AFTER INSERT OR UPDATE. DELETE no se cubre: retirar una linea
--      o un alcance solo reduce conjuntos (D-108).
--
--   2. D-122, reparenting de categorias (UPDATE OF parent_id), dos
--      responsabilidades separadas:
--      a) DERIVA SEMANTICA (E(c), aprobada por el usuario en el mandato de
--         0285, CAMBIA D-122). BEFORE UPDATE OF parent_id, INMEDIATO y paso
--         a paso: con el advisory (CATEGORIAS, owner) se calculan los
--         ancestros propios de C con el padre anterior (OLD) y con el padre
--         candidato (NEW) sobre la jerarquia vigente en ese paso, cortando el
--         recorrido al alcanzar C y con CYCLE. Si algun alcance (BOLSA o
--         INDICADOR) de un presupuesto congelado (estado <> 'BORRADOR') tiene
--         incluir_descendientes = true y categoria_id en la diferencia
--         simetrica de ambos conjuntos, el reparenting se rechaza. Un alcance
--         sobre C o sobre su subarbol no cambia (el subarbol se mueve
--         entero); un alcance con incluir_descendientes = false tampoco. En
--         una sentencia que mueva varias filas el orden de pasos lo decide el
--         ejecutor. Una transaccion A -> B -> A se rechaza en el primer paso
--         si ese paso altera semantica congelada. No hay snapshot ni
--         versionado de la jerarquia. Antes de releer el estado se bloquean
--         con FOR NO KEY UPDATE, en orden de id, los presupuestos candidatos
--         (los que tienen un alcance con descendientes sobre una categoria de
--         la diferencia simetrica): usa el mismo lock root de fila que F(a) y
--         cierra la ventana deriva x activacion concurrente, sin advisory
--         adicional. INSERT de categorias, enabled y
--         renombrado quedan fuera de D-122 (riesgo residual documentado).
--         Funcion nueva gapto.fn_check_categoria_deriva.
--      b) REVALIDACION D-121. CONSTRAINT TRIGGER diferido
--         trg_categorias_financieras__bolsa_reparenting AFTER UPDATE OF
--         parent_id -> gapto.fn_check_bolsa_prioridad (rama
--         categorias_financieras): advisory (CATEGORIAS, owner) y
--         revalidacion de TODOS los presupuestos del owner, sin filtro
--         incremental, sobre la jerarquia FINAL. La aciclicidad sigue siendo
--         responsabilidad exclusiva de D-123 (0280).
--
--   3. CONGELACION FISICA TRAS BORRADOR (F(a), aprobada por el usuario en el
--      mandato de 0285, CAMBIA D-132). gapto.fn_guard_presupuesto_congelado,
--      BEFORE INSERT OR UPDATE OR DELETE en presupuesto_lineas y en
--      presupuesto_linea_alcances. Todos los presupuestos afectados (origen
--      y destino si cambia presupuesto_id o presupuesto_linea_id) deben
--      estar en BORRADOR. La fila del presupuesto es el lock root: no se
--      adquiere ningun advisory para F(a). El protocolo es lock -> espera ->
--      LECTURA SQL SEPARADA -> validacion, nunca lock y lectura confiada en
--      la misma sentencia: en alcances se bloquean primero las lineas
--      afectadas con FOR NO KEY UPDATE en orden de id y despues, en otra
--      sentencia, se leen sus presupuestos; luego se bloquean los
--      presupuestos con FOR NO KEY UPDATE en orden de id y, en una tercera
--      sentencia, se relee su estado. Origen y destino se bloquean en orden
--      determinista de id. Un presupuesto o linea no visible es error de
--      VISIBILIDAD (fail-closed, D-118).
--      No retorno: gapto.fn_guard_presupuesto_estado, BEFORE UPDATE OF estado
--      ON presupuestos, rechaza OLD.estado <> 'BORRADOR' y NEW.estado =
--      'BORRADOR'. No se fija ninguna otra transicion entre ACTIVO,
--      SUSTITUIDO y CERRADO.
--
--   4. SAME-OWNER DE TODO ALCANCE (H(b)): la categoria y la entidad de cada
--      alcance, BOLSA o INDICADOR, pertenecen al owner del presupuesto de su
--      linea. Lo comprueban los dos validadores diferidos sobre el
--      presupuesto final completo, incluido el caso de una linea que cambia
--      de presupuesto_id y el de un alcance que cambia de linea. Impuesto por
--      PostgreSQL y no por RLS; sobrevive a BYPASSRLS. No es FK compuesta
--      porque presupuesto_linea_alcances no tiene owner_user_id (no se anade
--      columna sin decision arquitectonica).
--
--   5. OWNER INMUTABLE (decision aprobada en el mandato de 0285):
--      gapto.fn_guard_owner_inmutable, BEFORE UPDATE OF owner_user_id en
--      presupuestos, categorias_financieras y entidades. Rechaza NEW distinto
--      de OLD (IS DISTINCT FROM); reescribir el mismo owner no falla. No
--      existia mecanismo generico previo reutilizable.
--
--   Locks. Orden preferente para quien necesita ambos dominios:
--   (CATEGORIAS, owner) -> fila. La congelacion toma la fila del presupuesto
--   durante el DML, antes de que el validador diferido tome el advisory; no
--   existe un orden global perfecto y los 40P01 residuales se tratan segun
--   D-114. F(a) NO adquiere ningun advisory: la fila del presupuesto ya
--   serializa exactamente la carrera edicion x activacion, y anadir
--   (PRESUPUESTOS, owner) solo crearia la topologia advisory -> fila frente a
--   fila -> advisory. No se altera la clave (PRESUPUESTOS, owner) de 0280.
--   No se usa FOR UPDATE en ninguna funcion nueva.
--
--   PRECHECK bloqueante y concluyente solo con BYPASSRLS o superusuario;
--   sin visibilidad global aborta (NO CONCLUYENTE). Comprueba D-121 con el
--   predicado nuevo, same-owner de todos los alcances, el baseline de 0280 y
--   la ausencia de FK ON UPDATE CASCADE sobre owner_user_id de las tres
--   tablas. No repara nada.
--
--   Los cuerpos de funcion no llevan comentarios inline (regla B22).
--
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0285$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
    v_ej     text;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-02-0285 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    SELECT pg_catalog.string_agg(e.nombre, ', ' ORDER BY e.nombre) INTO v_ej
      FROM (VALUES
            ('fn_check_reversion_movimiento',    'bd4ab19984492486f595cb539f78d263'),
            ('fn_check_jerarquia_aciclica',      '7fc289a080c5d9c0b2c731c69399d79c'),
            ('fn_check_hecho_parte_de_aciclico', '0bc045230c00b7857343c9c3d99ce7ad'),
            ('fn_check_cadena_sustitucion',      'd8b89d79f5907f6690d0c31cee7ddd54'),
            ('fn_check_bolsa_prioridad',         'a583bbd419cb337152617b0c19a1cc42'),
            ('fn_check_bolsa_prioridad_alcance', '7c876f1970c850e791af25226da520b1')
      ) AS e(nombre, md5_esperado)
      LEFT JOIN pg_catalog.pg_proc p ON p.proname = e.nombre AND p.pronamespace = 'gapto'::pg_catalog.regnamespace
     WHERE p.oid IS NULL OR pg_catalog.md5(p.prosrc) <> e.md5_esperado;
    IF v_ej IS NOT NULL THEN
        v_rep := v_rep || pg_catalog.format(' baseline_0280_funciones_divergentes=[%s]', v_ej);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
     WHERE NOT t.tgisinternal
       AND ((t.tgrelid = 'gapto.presupuesto_lineas'::pg_catalog.regclass AND t.tgname = 'trg_presupuesto_lineas__bolsa_prioridad')
         OR (t.tgrelid = 'gapto.presupuesto_linea_alcances'::pg_catalog.regclass AND t.tgname = 'trg_presupuesto_linea_alcances__bolsa_prioridad')
         OR (t.tgrelid = 'gapto.categorias_financieras'::pg_catalog.regclass AND t.tgname = 'trg_categorias_financieras__aciclica')
         OR (t.tgrelid = 'gapto.presupuestos'::pg_catalog.regclass AND t.tgname = 'trg_presupuestos__cadena_sustitucion'));
    IF v_n <> 4 THEN
        v_rep := v_rep || pg_catalog.format(' baseline_0280_triggers=%s/4', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_guard_presupuesto_congelado', 'fn_guard_presupuesto_estado',
                         'fn_guard_owner_inmutable', 'fn_check_categoria_deriva');
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' objetos_0285_ya_existen=%s', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_attribute a
     WHERE a.attrelid IN ('gapto.presupuestos'::pg_catalog.regclass, 'gapto.categorias_financieras'::pg_catalog.regclass,
                          'gapto.entidades'::pg_catalog.regclass)
       AND a.attname = 'owner_user_id' AND NOT a.attisdropped AND a.attnotnull;
    IF v_n <> 3 THEN
        v_rep := v_rep || pg_catalog.format(' owner_user_id_not_null=%s/3', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_constraint k
     WHERE k.contype = 'f' AND k.confupdtype = 'c'
       AND k.confrelid IN ('gapto.presupuestos'::pg_catalog.regclass, 'gapto.categorias_financieras'::pg_catalog.regclass,
                           'gapto.entidades'::pg_catalog.regclass);
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' fk_on_update_cascade_hacia_owner=%s', v_n);
    END IF;

    WITH RECURSIVE d(raiz, cat) AS (
        SELECT c.parent_id, c.id FROM gapto.categorias_financieras c
         WHERE c.parent_id IN (SELECT a.categoria_id FROM gapto.presupuesto_linea_alcances a WHERE a.incluir_descendientes)
        UNION ALL
        SELECT d.raiz, c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.cat
    ) CYCLE cat SET es_ciclo USING ruta,
    par AS (
        SELECT l1.id AS l1, l2.id AS l2
          FROM gapto.presupuesto_lineas l1
          JOIN gapto.presupuesto_lineas l2
            ON l2.presupuesto_id = l1.presupuesto_id AND l2.id > l1.id
           AND l2.tipo_linea = 'BOLSA' AND l2.naturaleza_economica = l1.naturaleza_economica
         WHERE l1.tipo_linea = 'BOLSA'
           AND (l1.prioridad_consumo IS NULL OR l2.prioridad_consumo IS NULL
                OR l1.prioridad_consumo = l2.prioridad_consumo)
           AND EXISTS (
               SELECT 1 FROM gapto.presupuesto_linea_alcances a1
                 JOIN gapto.presupuesto_linea_alcances a2 ON a2.presupuesto_linea_id = l2.id
                WHERE a1.presupuesto_linea_id = l1.id
                  AND (a1.categoria_id IS NULL OR a2.categoria_id IS NULL
                       OR a1.categoria_id = a2.categoria_id
                       OR (a1.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a1.categoria_id AND d.cat = a2.categoria_id))
                       OR (a2.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a2.categoria_id AND d.cat = a1.categoria_id))))
    )
    SELECT pg_catalog.count(*), pg_catalog.min(pg_catalog.left(l1::text, 8) || '/' || pg_catalog.left(l2::text, 8))
      INTO v_n, v_ej FROM par;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' d121_pares_bolsa_ambiguos=%s(ej %s)', v_n, v_ej);
    END IF;

    SELECT pg_catalog.count(*), pg_catalog.min(pg_catalog.left(a.id::text, 8)) INTO v_n, v_ej
      FROM gapto.presupuesto_linea_alcances a
      JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
      JOIN gapto.presupuestos p ON p.id = l.presupuesto_id
      JOIN gapto.categorias_financieras c ON c.id = a.categoria_id
     WHERE c.owner_user_id <> p.owner_user_id;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' alcances_categoria_otro_owner=%s(ej %s)', v_n, v_ej);
    END IF;

    SELECT pg_catalog.count(*), pg_catalog.min(pg_catalog.left(a.id::text, 8)) INTO v_n, v_ej
      FROM gapto.presupuesto_linea_alcances a
      JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
      JOIN gapto.presupuestos p ON p.id = l.presupuesto_id
      JOIN gapto.entidades e ON e.id = a.entidad_id
     WHERE e.owner_user_id <> p.owner_user_id;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' alcances_entidad_otro_owner=%s(ej %s)', v_n, v_ej);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0285 PRECHECK FALLIDO:%', v_rep;
    END IF;
    RAISE NOTICE 'F03-02-0285 PRECHECK: CONCLUYENTE y sin violaciones (rol %)', current_user;
END;
$precheck_0285$;

SET ROLE gapto_owner;

CREATE OR REPLACE FUNCTION gapto.fn_check_bolsa_prioridad()
RETURNS trigger AS $fn$
DECLARE
    v_owner       uuid;
    v_presupuesto uuid;
    v_objetivos   uuid[];
    v_alcance     uuid;
    v_l1          uuid;
    v_l2          uuid;
BEGIN
    IF TG_TABLE_NAME = 'presupuesto_lineas' THEN
        SELECT p.owner_user_id INTO v_owner FROM gapto.presupuestos p WHERE p.id = NEW.presupuesto_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'presupuesto_lineas: VISIBILIDAD - el presupuesto % no es visible al validar la linea % (contexto de tenant ausente o distinto del de la escritura)',
                NEW.presupuesto_id, NEW.id;
        END IF;
        v_objetivos := ARRAY[NEW.presupuesto_id];
    ELSIF TG_TABLE_NAME = 'categorias_financieras' THEN
        v_owner := NEW.owner_user_id;
    ELSE
        RAISE EXCEPTION 'fn_check_bolsa_prioridad: tabla % no soportada', TG_TABLE_NAME;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'), hashtext(v_owner::text));

    IF TG_TABLE_NAME = 'categorias_financieras' THEN
        SELECT coalesce(array_agg(p.id ORDER BY p.id), '{}') INTO v_objetivos
          FROM gapto.presupuestos p WHERE p.owner_user_id = v_owner;
    ELSE
        PERFORM 1 FROM gapto.presupuestos WHERE id = NEW.presupuesto_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'presupuesto_lineas: VISIBILIDAD - el presupuesto % no es visible al validar la linea % (contexto de tenant ausente o distinto del de la escritura)',
                NEW.presupuesto_id, NEW.id;
        END IF;
    END IF;

    FOREACH v_presupuesto IN ARRAY v_objetivos LOOP
        SELECT a.id INTO v_alcance
          FROM gapto.presupuesto_linea_alcances a
          JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
          LEFT JOIN gapto.categorias_financieras c ON c.id = a.categoria_id
          LEFT JOIN gapto.entidades e ON e.id = a.entidad_id
         WHERE l.presupuesto_id = v_presupuesto
           AND ((a.categoria_id IS NOT NULL AND c.owner_user_id IS DISTINCT FROM v_owner)
             OR (a.entidad_id IS NOT NULL AND e.owner_user_id IS DISTINCT FROM v_owner))
         LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'presupuesto_linea_alcances: el alcance % no pertenece al mismo owner que el presupuesto % (categoria o entidad de otro owner o no visible)',
                v_alcance, v_presupuesto;
        END IF;

        WITH RECURSIVE d(raiz, cat) AS (
            SELECT c.parent_id, c.id FROM gapto.categorias_financieras c
             WHERE c.parent_id IN (SELECT a.categoria_id FROM gapto.presupuesto_linea_alcances a
                                     JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
                                    WHERE l.presupuesto_id = v_presupuesto AND l.tipo_linea = 'BOLSA'
                                      AND a.incluir_descendientes)
            UNION ALL
            SELECT d.raiz, c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.cat
        ) CYCLE cat SET es_ciclo USING ruta
        SELECT l1.id, l2.id INTO v_l1, v_l2
          FROM gapto.presupuesto_lineas l1
          JOIN gapto.presupuesto_lineas l2
            ON l2.presupuesto_id = l1.presupuesto_id AND l2.id > l1.id
           AND l2.tipo_linea = 'BOLSA' AND l2.naturaleza_economica = l1.naturaleza_economica
         WHERE l1.presupuesto_id = v_presupuesto AND l1.tipo_linea = 'BOLSA'
           AND (l1.prioridad_consumo IS NULL OR l2.prioridad_consumo IS NULL
                OR l1.prioridad_consumo = l2.prioridad_consumo)
           AND EXISTS (
               SELECT 1 FROM gapto.presupuesto_linea_alcances a1
                 JOIN gapto.presupuesto_linea_alcances a2 ON a2.presupuesto_linea_id = l2.id
                WHERE a1.presupuesto_linea_id = l1.id
                  AND (a1.categoria_id IS NULL OR a2.categoria_id IS NULL
                       OR a1.categoria_id = a2.categoria_id
                       OR (a1.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a1.categoria_id AND d.cat = a2.categoria_id))
                       OR (a2.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a2.categoria_id AND d.cat = a1.categoria_id))))
         ORDER BY l1.id, l2.id
         LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'presupuesto_lineas: la BOLSA % y la BOLSA % del presupuesto % pueden capturar el mismo efecto y sus prioridades no son NOT NULL y distintas (D-121)',
                v_l1, v_l2, v_presupuesto;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION gapto.fn_check_bolsa_prioridad_alcance()
RETURNS trigger AS $fn$
DECLARE
    v_owner       uuid;
    v_presupuesto uuid;
    v_alcance     uuid;
    v_l1          uuid;
    v_l2          uuid;
BEGIN
    SELECT l.presupuesto_id, p.owner_user_id INTO v_presupuesto, v_owner
      FROM gapto.presupuesto_lineas l
      JOIN gapto.presupuestos p ON p.id = l.presupuesto_id
     WHERE l.id = NEW.presupuesto_linea_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'presupuesto_linea_alcances: VISIBILIDAD - la linea % o su presupuesto no es visible al validar el alcance (contexto de tenant ausente o distinto del de la escritura)',
            NEW.presupuesto_linea_id;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'), hashtext(v_owner::text));

    PERFORM 1 FROM gapto.presupuestos WHERE id = v_presupuesto FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'presupuesto_linea_alcances: VISIBILIDAD - el presupuesto % no es visible al validar el alcance (contexto de tenant ausente o distinto del de la escritura)',
            v_presupuesto;
    END IF;

    SELECT a.id INTO v_alcance
      FROM gapto.presupuesto_linea_alcances a
      JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
      LEFT JOIN gapto.categorias_financieras c ON c.id = a.categoria_id
      LEFT JOIN gapto.entidades e ON e.id = a.entidad_id
     WHERE l.presupuesto_id = v_presupuesto
       AND ((a.categoria_id IS NOT NULL AND c.owner_user_id IS DISTINCT FROM v_owner)
         OR (a.entidad_id IS NOT NULL AND e.owner_user_id IS DISTINCT FROM v_owner))
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'presupuesto_linea_alcances: el alcance % no pertenece al mismo owner que el presupuesto % (categoria o entidad de otro owner o no visible)',
            v_alcance, v_presupuesto;
    END IF;

    WITH RECURSIVE d(raiz, cat) AS (
        SELECT c.parent_id, c.id FROM gapto.categorias_financieras c
         WHERE c.parent_id IN (SELECT a.categoria_id FROM gapto.presupuesto_linea_alcances a
                                 JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
                                WHERE l.presupuesto_id = v_presupuesto AND l.tipo_linea = 'BOLSA'
                                  AND a.incluir_descendientes)
        UNION ALL
        SELECT d.raiz, c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.cat
    ) CYCLE cat SET es_ciclo USING ruta
    SELECT l1.id, l2.id INTO v_l1, v_l2
      FROM gapto.presupuesto_lineas l1
      JOIN gapto.presupuesto_lineas l2
        ON l2.presupuesto_id = l1.presupuesto_id AND l2.id > l1.id
       AND l2.tipo_linea = 'BOLSA' AND l2.naturaleza_economica = l1.naturaleza_economica
     WHERE l1.presupuesto_id = v_presupuesto AND l1.tipo_linea = 'BOLSA'
       AND (l1.prioridad_consumo IS NULL OR l2.prioridad_consumo IS NULL
            OR l1.prioridad_consumo = l2.prioridad_consumo)
       AND EXISTS (
           SELECT 1 FROM gapto.presupuesto_linea_alcances a1
             JOIN gapto.presupuesto_linea_alcances a2 ON a2.presupuesto_linea_id = l2.id
            WHERE a1.presupuesto_linea_id = l1.id
              AND (a1.categoria_id IS NULL OR a2.categoria_id IS NULL
                   OR a1.categoria_id = a2.categoria_id
                   OR (a1.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a1.categoria_id AND d.cat = a2.categoria_id))
                   OR (a2.incluir_descendientes AND EXISTS (SELECT 1 FROM d WHERE d.raiz = a2.categoria_id AND d.cat = a1.categoria_id))))
     ORDER BY l1.id, l2.id
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'presupuesto_lineas: la BOLSA % y la BOLSA % del presupuesto % pueden capturar el mismo efecto y sus prioridades no son NOT NULL y distintas (D-121)',
            v_l1, v_l2, v_presupuesto;
    END IF;

    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

CREATE FUNCTION gapto.fn_check_categoria_deriva()
RETURNS trigger AS $fn$
DECLARE
    v_viejos  uuid[];
    v_nuevos  uuid[];
    v_cambian   uuid[];
    v_candidatos uuid[];
    v_alcance   uuid;
    v_pres      uuid;
BEGIN
    IF NEW.parent_id IS NOT DISTINCT FROM OLD.parent_id THEN
        RETURN NEW;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('gapto:CATEGORIAS'), hashtext(OLD.owner_user_id::text));

    WITH RECURSIVE v(n) AS (
        SELECT OLD.parent_id WHERE OLD.parent_id IS NOT NULL AND OLD.parent_id <> OLD.id
        UNION ALL
        SELECT c.parent_id FROM v JOIN gapto.categorias_financieras c ON c.id = v.n
         WHERE c.parent_id IS NOT NULL AND c.parent_id <> OLD.id
    ) CYCLE n SET es_ciclo USING ruta
    SELECT coalesce(array_agg(DISTINCT v.n), '{}') INTO v_viejos FROM v;

    WITH RECURSIVE w(n) AS (
        SELECT NEW.parent_id WHERE NEW.parent_id IS NOT NULL AND NEW.parent_id <> OLD.id
        UNION ALL
        SELECT c.parent_id FROM w JOIN gapto.categorias_financieras c ON c.id = w.n
         WHERE c.parent_id IS NOT NULL AND c.parent_id <> OLD.id
    ) CYCLE n SET es_ciclo USING ruta
    SELECT coalesce(array_agg(DISTINCT w.n), '{}') INTO v_nuevos FROM w;

    SELECT coalesce(array_agg(x), '{}') INTO v_cambian
      FROM (SELECT unnest(v_viejos) EXCEPT SELECT unnest(v_nuevos)
            UNION
            (SELECT unnest(v_nuevos) EXCEPT SELECT unnest(v_viejos))) AS s(x);

    SELECT coalesce(array_agg(DISTINCT l.presupuesto_id), '{}') INTO v_candidatos
      FROM gapto.presupuesto_linea_alcances a
      JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
     WHERE a.incluir_descendientes
       AND a.categoria_id = ANY (v_cambian);

    PERFORM 1 FROM gapto.presupuestos p
      WHERE p.id = ANY (v_candidatos) ORDER BY p.id FOR NO KEY UPDATE;

    SELECT a.id, l.presupuesto_id INTO v_alcance, v_pres
      FROM gapto.presupuesto_linea_alcances a
      JOIN gapto.presupuesto_lineas l ON l.id = a.presupuesto_linea_id
      JOIN gapto.presupuestos p ON p.id = l.presupuesto_id
     WHERE p.id = ANY (v_candidatos)
       AND p.estado <> 'BORRADOR'
       AND a.incluir_descendientes
       AND a.categoria_id = ANY (v_cambian)
     ORDER BY a.id
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'categorias_financieras: mover la categoria % cambia el conjunto de categorias del alcance % del presupuesto congelado % (deriva semantica D-122)',
            OLD.id, v_alcance, v_pres;
    END IF;

    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE FUNCTION gapto.fn_guard_presupuesto_congelado()
RETURNS trigger AS $fn$
DECLARE
    v_lineas uuid[];
    v_pres   uuid[];
    v_n      integer;
    v_id     uuid;
    v_estado character varying(20);
BEGIN
    IF TG_TABLE_NAME = 'presupuesto_lineas' THEN
        IF TG_OP = 'INSERT' THEN
            v_pres := ARRAY[NEW.presupuesto_id];
        ELSIF TG_OP = 'UPDATE' THEN
            v_pres := ARRAY[OLD.presupuesto_id, NEW.presupuesto_id];
        ELSE
            v_pres := ARRAY[OLD.presupuesto_id];
        END IF;
    ELSIF TG_TABLE_NAME = 'presupuesto_linea_alcances' THEN
        IF TG_OP = 'INSERT' THEN
            v_lineas := ARRAY[NEW.presupuesto_linea_id];
        ELSIF TG_OP = 'UPDATE' THEN
            v_lineas := ARRAY[OLD.presupuesto_linea_id, NEW.presupuesto_linea_id];
        ELSE
            v_lineas := ARRAY[OLD.presupuesto_linea_id];
        END IF;
        SELECT array_agg(DISTINCT x ORDER BY x) INTO v_lineas FROM unnest(v_lineas) AS u(x);
        PERFORM 1 FROM gapto.presupuesto_lineas l
          WHERE l.id = ANY (v_lineas) ORDER BY l.id FOR NO KEY UPDATE;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n <> cardinality(v_lineas) THEN
            RAISE EXCEPTION 'presupuesto_linea_alcances: VISIBILIDAD - una linea de % no es visible al comprobar la congelacion (contexto de tenant ausente o distinto del de la escritura)',
                v_lineas;
        END IF;
        SELECT array_agg(DISTINCT l.presupuesto_id) INTO v_pres
          FROM gapto.presupuesto_lineas l WHERE l.id = ANY (v_lineas);
    ELSE
        RAISE EXCEPTION 'fn_guard_presupuesto_congelado: tabla % no soportada', TG_TABLE_NAME;
    END IF;

    SELECT array_agg(DISTINCT x ORDER BY x) INTO v_pres FROM unnest(v_pres) AS u(x);
    PERFORM 1 FROM gapto.presupuestos p
      WHERE p.id = ANY (v_pres) ORDER BY p.id FOR NO KEY UPDATE;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> cardinality(v_pres) THEN
        RAISE EXCEPTION '%: VISIBILIDAD - un presupuesto de % no es visible al comprobar la congelacion (contexto de tenant ausente o distinto del de la escritura)',
            TG_TABLE_NAME, v_pres;
    END IF;

    SELECT p.id, p.estado INTO v_id, v_estado
      FROM gapto.presupuestos p
     WHERE p.id = ANY (v_pres) AND p.estado <> 'BORRADOR'
     ORDER BY p.id LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION '%: el presupuesto % esta en estado % y queda congelado; solo un presupuesto BORRADOR admite INSERT, UPDATE o DELETE de lineas y alcances',
            TG_TABLE_NAME, v_id, v_estado;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE FUNCTION gapto.fn_guard_presupuesto_estado()
RETURNS trigger AS $fn$
BEGIN
    IF OLD.estado <> 'BORRADOR' AND NEW.estado = 'BORRADOR' THEN
        RAISE EXCEPTION 'presupuestos: el presupuesto % no puede volver a BORRADOR desde %; para modificarlo se crea una version nueva',
            OLD.id, OLD.estado;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE FUNCTION gapto.fn_guard_owner_inmutable()
RETURNS trigger AS $fn$
BEGIN
    IF NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id THEN
        RAISE EXCEPTION '%: owner_user_id es inmutable (fila %)', TG_TABLE_NAME, OLD.id;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER trg_presupuesto_lineas__bolsa_prioridad ON gapto.presupuesto_lineas;

CREATE CONSTRAINT TRIGGER trg_presupuesto_lineas__bolsa_prioridad
    AFTER INSERT OR UPDATE OF presupuesto_id, tipo_linea, naturaleza_economica, prioridad_consumo
    ON gapto.presupuesto_lineas
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_bolsa_prioridad();

CREATE CONSTRAINT TRIGGER trg_categorias_financieras__bolsa_reparenting
    AFTER UPDATE OF parent_id ON gapto.categorias_financieras
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_bolsa_prioridad();

CREATE TRIGGER trg_categorias_financieras__deriva_d122
    BEFORE UPDATE OF parent_id ON gapto.categorias_financieras
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_categoria_deriva();

CREATE TRIGGER trg_presupuesto_lineas__congelacion
    BEFORE INSERT OR UPDATE OR DELETE ON gapto.presupuesto_lineas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_presupuesto_congelado();

CREATE TRIGGER trg_presupuesto_linea_alcances__congelacion
    BEFORE INSERT OR UPDATE OR DELETE ON gapto.presupuesto_linea_alcances
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_presupuesto_congelado();

CREATE TRIGGER trg_presupuestos__no_retorno_borrador
    BEFORE UPDATE OF estado ON gapto.presupuestos
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_presupuesto_estado();

CREATE TRIGGER trg_presupuestos__owner_inmutable
    BEFORE UPDATE OF owner_user_id ON gapto.presupuestos
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_owner_inmutable();

CREATE TRIGGER trg_categorias_financieras__owner_inmutable
    BEFORE UPDATE OF owner_user_id ON gapto.categorias_financieras
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_owner_inmutable();

CREATE TRIGGER trg_entidades__owner_inmutable
    BEFORE UPDATE OF owner_user_id ON gapto.entidades
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_owner_inmutable();

COMMENT ON FUNCTION gapto.fn_check_bolsa_prioridad() IS
    'F03-02-0285 / D-121: exclusividad BOLSA con predicado categoria jerarquica x naturaleza, entidad conservadora y prioridad NOT NULL distinta si hay solape; same-owner de alcances; rama categorias_financieras = revalidacion tras reparenting (D-122). Advisory (CATEGORIAS, owner) y estado final.';
COMMENT ON FUNCTION gapto.fn_check_bolsa_prioridad_alcance() IS
    'F03-02-0285 / D-121: mismo predicado que fn_check_bolsa_prioridad desde presupuesto_linea_alcances, mas same-owner de todo alcance (BOLSA e INDICADOR).';
COMMENT ON FUNCTION gapto.fn_check_categoria_deriva() IS
    'F03-02-0285 / D-122 E(c): rechaza, paso a paso e inmediatamente, un reparenting que cambie el conjunto de categorias de un alcance con descendientes de un presupuesto congelado (estado <> BORRADOR).';
COMMENT ON FUNCTION gapto.fn_guard_presupuesto_congelado() IS
    'F03-02-0285 / F(a): lineas y alcances solo se escriben si todos los presupuestos afectados estan en BORRADOR.';
COMMENT ON FUNCTION gapto.fn_guard_presupuesto_estado() IS
    'F03-02-0285 / F(a): un presupuesto que ha abandonado BORRADOR no vuelve a BORRADOR. No define otras transiciones.';
COMMENT ON FUNCTION gapto.fn_guard_owner_inmutable() IS
    'F03-02-0285: owner_user_id inmutable en presupuestos, categorias_financieras y entidades.';

RESET ROLE;

DO $postcheck_0285$
DECLARE
    v_n integer;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_trigger t
     WHERE NOT t.tgisinternal AND t.tgname IN (
        'trg_presupuesto_lineas__bolsa_prioridad', 'trg_presupuesto_linea_alcances__bolsa_prioridad',
        'trg_categorias_financieras__bolsa_reparenting', 'trg_categorias_financieras__deriva_d122',
        'trg_presupuesto_lineas__congelacion', 'trg_presupuesto_linea_alcances__congelacion',
        'trg_presupuestos__no_retorno_borrador', 'trg_presupuestos__owner_inmutable',
        'trg_categorias_financieras__owner_inmutable', 'trg_entidades__owner_inmutable');
    IF v_n <> 10 THEN
        RAISE EXCEPTION 'F03-02-0285 POSTCHECK: triggers 0285 = % (esperados 10)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_check_bolsa_prioridad', 'fn_check_bolsa_prioridad_alcance', 'fn_check_categoria_deriva',
                         'fn_guard_presupuesto_congelado', 'fn_guard_presupuesto_estado', 'fn_guard_owner_inmutable')
       AND NOT p.prosecdef AND p.provolatile = 'v' AND p.proconfig IS NULL
       AND pg_catalog.pg_get_userbyid(p.proowner) = 'gapto_owner';
    IF v_n <> 6 THEN
        RAISE EXCEPTION 'F03-02-0285 POSTCHECK: funciones 0285 con atributos esperados = % (esperadas 6)', v_n;
    END IF;
    RAISE NOTICE 'F03-02-0285 POSTCHECK: OK';
END;
$postcheck_0285$;

COMMIT;
