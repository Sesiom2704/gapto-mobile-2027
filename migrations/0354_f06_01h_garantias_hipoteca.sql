-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0354_f06_01h_garantias_hipoteca.sql
-- Ruta: migrations/0354_f06_01h_garantias_hipoteca.sql
-- Descripcion: FASE 06 · T3-F06 bloque 2 F06-01H (hipoteca de la compra).
--   MIG-HIP-GAR: garantias fisicas del cuadro de una hipoteca (D4, D5 del
--   lote 40). Migration forward-only sobre 0353 (no edita 0001..0353).
--   Contrato F06-01H v0.4 §10.1 (corregido por AJ-T3D-06); mandato
--   MANDATO_T3_02_F06-01H_v1.1 §8 con STOP B y STOP D autorizados
--   expresamente solo para esta migration (AJ-T3D-05). Regimen WM 0.34
--   (D-211): humo de Neon bloqueante; Supabase en divergencia registrada.
--
--   AMBITOS (solo columnas existentes desde 0050).
--     C(F) «tiene cuadro»: existe una fila de financiacion_cuotas de F.
--     M(F) «hipoteca con cuadro calculado»: tipo_financiacion = 'HIPOTECA' y
--       existe una version de F con motivo_version = 'ALTA' y
--       hecho_causa_id IS NOT NULL (la escribe solo W-HIP-01, con Hd).
--     H(F) (ambito de G2): tipo_financiacion = 'HIPOTECA' y (C(F) o M(F)).
--     Fuera de ambito, sin cambio respecto de 0353: PRESTAMO,
--     COMPRA_FINANCIADA, OTRA y la HIPOTECA legacy sin cuotas y sin M.
--     Capital NULL legitimo solo fuera de H.
--
--   GARANTIAS (RAISE EXCEPTION, SQLSTATE P0001, prefijo estable
--   «INV-0354-<Id>:»; el backend las clasifica como VIOLACION_INVARIANTE_FISICA).
--     G1   BEFORE UPDATE ON financiacion_cuotas FOR EACH ROW: OLD.prevision_id
--          NULL -> rechazo (NULL bloqueante); lee previsiones.estado de
--          OLD.prevision_id FOR SHARE; no visible -> rechazo; estado distinto
--          de ABIERTA -> rechazo; prevision_id o financiacion_entidad_id
--          cambiados -> rechazo. Ambito: todas las cuotas.
--     G1-R BEFORE UPDATE OF estado ON previsiones WHEN (OLD.estado <> 'ABIERTA'
--          AND NEW.estado = 'ABIERTA'): existe una cuota con prevision_id =
--          OLD.id -> rechazo. Cierra «Reabrir» y cualquier UPDATE directo.
--     G2   tres constraint triggers DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
--          que entregan identificadores de financiacion a un validador unico.
--          Al COMMIT, para cada F tocada: (1) bloquea financiaciones FOR NO
--          KEY UPDATE en orden de entidad_id y exige ROW_COUNT exacto (fail-
--          closed, patron 0310); (2) en sentencia posterior relee el estado
--          final; F fuera de H sigue; F en H exige capital_original_contratado
--          no NULL y > 0, al menos una cuota, ningun capital_previsto NULL,
--          numero_cuota = exactamente {1..N} y Σ capital_previsto =
--          capital_original_contratado (igualdad exacta en numeric). Dispara
--          tambien al cambiar capital_original_contratado o tipo_financiacion
--          (T4, AJ-T3D-06) y al nacer o cambiar la marca M (T5).
--     G2-E BEFORE UPDATE OF tipo_financiacion ON financiaciones WHEN
--          (OLD = 'HIPOTECA' AND NEW <> 'HIPOTECA'): C(F) o M(F) -> rechazo.
--     G3   BEFORE UPDATE ON financiacion_condiciones_versiones FOR EACH ROW: si
--          la financiacion de OLD esta en M (evaluado antes del cambio), solo se
--          admite OLD.vigente_hasta IS NULL AND NEW.vigente_hasta IS NOT NULL
--          con todas las demas columnas IS NOT DISTINCT FROM las de OLD.
--
--   INVENTARIO CERRADO (contrato §10.1.3): seis funciones y siete triggers
--   sobre cuatro tablas existentes.
--     F1 gapto.fn_guard_cuota_inmutable_no_abierta()          T1 G1
--     F2 gapto.fn_guard_prevision_cuota_no_reabrible()        T2 G1-R
--     F3 gapto.fn_check_cuadro_hipoteca()      (despachador)  T3 T4 T5 G2
--     F4 gapto.fn_validar_cuadro_hipoteca(uuid[]) (nucleo)    G2
--     F5 gapto.fn_guard_financiacion_ambito_hipoteca()        T6 G2-E
--     F6 gapto.fn_guard_condiciones_version_historico()       T7 G3
--     trg_financiaciones__subtipo_unico (0110) no se toca.
--
--   PATRON. SECURITY INVOKER (patron 0280/0310: tablas del mismo owner, sin
--   lectura cross-tenant legitima); SQL cualificado con gapto. y pg_catalog.,
--   sin SET search_path (patron 0352/0353); propietario gapto_owner; ACL por
--   defecto, identica a la de las funciones de 0310 (proacl NULL). Cuerpos sin
--   comentarios inline: prosrc participa en las huellas D-111. Despachador sin
--   SQL dinamico (CASE TG_TABLE_NAME, F03-00-G-B); OLD/NEW solo para
--   identificadores en los triggers diferidos. Bajo RLS y FORCE, sin GUC de
--   tenant las lecturas no ven filas y las guardas fallan cerradas (no hay
--   rama «no visible = permitido»).
--
--   LOCKS (contrato §10.1.4). G1 toma FOR SHARE de la prevision (cuota ->
--   prevision). G2 toma FOR NO KEY UPDATE de la financiacion al COMMIT, en
--   orden de entidad_id (reentrante en W-HIP-02/03/04). G1-R, G2-E y G3 no
--   toman locks nuevos. Ninguno invierte el orden normativo R1.
--
--   LO QUE NO HACE (a proposito). Sin tablas, columnas, filas, indices,
--   constraints declarativos, policies ni privilegios nuevos; sin ALTER TABLE
--   (FORCE RLS no se levanta); sin capacidades ni tipos de hecho; no corrige
--   ni normaliza datos. R-0354-01: session_replication_role = replica o un
--   superusuario que desactive triggers los saltan (como las garantias
--   vigentes). R-0354-02: G1-R impide reabrir, no impide cerrar sin pago (lo
--   cubre la guarda de servicio). R-0354-03: una carga RV3 posterior debe ir
--   con contexto de tenant. R-0354-05: el diagnostico de G2 se detiene en la
--   primera financiacion incumplidora (orden por entidad_id).
--
--   PRECHECKS (fail-closed, misma transaccion). PC-01 rol con BYPASSRLS (si
--   no: NO CONCLUYENTE); PC-02 head fisico 0353 (marca de 0353 presente,
--   28 funciones, 58 triggers no internos, 41 constraint triggers); PC-03
--   ningun objeto de 0354 existe; PC-04 violaciones de G2 en H por clase
--   ((a) capital NULL o <= 0; (b) cuota con capital NULL; (c) numeracion
--   distinta de 1..N; (d) Σ distinta del capital; (e) M sin cuotas) con
--   recuento y primeras 20 entidad_id -> BLOQUEA (STOP de datos, no se
--   corrige nada); PC-05 financiaciones en M (esperado 0); PC-06 y PC-07
--   informativos; PC-08 tablas con FORCE RLS = 75 (las de 0353).
--   POSTCHECKS. PO-01 seis funciones invoker, plpgsql, gapto_owner, proacl
--   NULL, sin comentarios en prosrc; PO-02 siete triggers con tabla, momento,
--   eventos, columnas de UPDATE OF, WHEN, diferibilidad (T3-T5 si; T1, T2,
--   T6, T7 no) y tgenabled = 'O'; PO-03 PC-04 = 0; PO-04 FORCE RLS, tablas,
--   columnas, indices, FK, policies y privilegios de gapto_runtime identicos
--   a 0353; funciones 28 -> 34, triggers no internos 58 -> 65, constraint
--   triggers 41 -> 44.
--
-- Version: 0.1.1 (F06 T3-F06 bloque 2 F06-01H): PO-04 cuenta los privilegios de gapto_runtime con
--   aclexplode(pg_class.relacl) y no con information_schema.role_table_grants, que solo muestra los
--   roles habilitados del usuario conectado (en Neon, neondb_owner veia 0; humo FAIL n.1).
-- Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; mandato v1.1 §8, contrato v0.4 §10.1)
-- ============================================================

BEGIN;

DO $precheck_0354$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
    v_a      bigint;
    v_b      bigint;
    v_c      bigint;
    v_d      bigint;
    v_e      bigint;
    v_ids    text;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F06-01H-0354 PRECHECK PC-01: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;
    RAISE NOTICE 'F06-01H-0354 PRECHECK: conexion db=% rol=%', pg_catalog.current_database(), current_user;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid = 'gapto.categorias_financieras'::pg_catalog.regclass
       AND a.attname = 'asociada_vivienda' AND NOT a.attisdropped;
    IF v_n <> 1 THEN
        v_rep := v_rep || ' PC-02 falta la marca de 0353 (categorias_financieras.asociada_vivienda);';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' PC-02 funciones = %s (esperadas 28 en 0353);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        v_rep := v_rep || pg_catalog.format(' PC-02 triggers no internos = %s (esperados 58 en 0353);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 41 THEN
        v_rep := v_rep || pg_catalog.format(' PC-02 constraint triggers = %s (esperados 41 en 0353);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_guard_cuota_inmutable_no_abierta',
                         'fn_guard_prevision_cuota_no_reabrible',
                         'fn_check_cuadro_hipoteca',
                         'fn_validar_cuadro_hipoteca',
                         'fn_guard_financiacion_ambito_hipoteca',
                         'fn_guard_condiciones_version_historico');
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' PC-03 ya existen %s funciones de 0354;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgname IN ('trg_financiacion_cuotas__inmutable_no_abierta',
                        'trg_previsiones__cuota_no_reabrible',
                        'trg_financiacion_cuotas__cuadro_hipoteca',
                        'trg_financiaciones__cuadro_hipoteca',
                        'trg_financiacion_condiciones_versiones__cuadro_hipoteca',
                        'trg_financiaciones__ambito_hipoteca',
                        'trg_financiacion_condiciones_versiones__historico');
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' PC-03 ya existen %s triggers de 0354;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind = 'r' AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' PC-08 tablas con FORCE RLS = %s (esperadas 75 en 0353);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F06-01H-0354 PRECHECK: BLOQUEA -%', v_rep;
    END IF;

    WITH h AS (
        SELECT f.entidad_id, f.capital_original_contratado AS capital
          FROM gapto.financiaciones f
         WHERE f.tipo_financiacion = 'HIPOTECA'
           AND (EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q
                         WHERE q.financiacion_entidad_id = f.entidad_id)
                OR EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                            WHERE v.financiacion_entidad_id = f.entidad_id
                              AND v.motivo_version = 'ALTA'
                              AND v.hecho_causa_id IS NOT NULL))
    ), agg AS (
        SELECT h.entidad_id, h.capital,
               pg_catalog.count(q.id) AS n,
               pg_catalog.count(q.id) FILTER (WHERE q.capital_previsto IS NULL) AS n_null,
               pg_catalog.min(q.numero_cuota) AS mn,
               pg_catalog.max(q.numero_cuota) AS mx,
               pg_catalog.count(DISTINCT q.numero_cuota) AS nd,
               pg_catalog.sum(q.capital_previsto) AS s
          FROM h LEFT JOIN gapto.financiacion_cuotas q ON q.financiacion_entidad_id = h.entidad_id
         GROUP BY h.entidad_id, h.capital
    ), cls AS (
        SELECT agg.entidad_id,
               (agg.capital IS NULL OR agg.capital <= 0) AS ca,
               (agg.n_null > 0) AS cb,
               (agg.n > 0 AND NOT (agg.mn = 1 AND agg.mx = agg.n AND agg.nd = agg.n)) AS cc,
               (agg.n > 0 AND agg.n_null = 0 AND agg.capital IS NOT NULL AND agg.s <> agg.capital) AS cd,
               (agg.n = 0) AS ce
          FROM agg
    )
    SELECT pg_catalog.count(*) FILTER (WHERE ca), pg_catalog.count(*) FILTER (WHERE cb),
           pg_catalog.count(*) FILTER (WHERE cc), pg_catalog.count(*) FILTER (WHERE cd),
           pg_catalog.count(*) FILTER (WHERE ce),
           (SELECT pg_catalog.string_agg(x.entidad_id::text, ',' ORDER BY x.entidad_id)
              FROM (SELECT c2.entidad_id FROM cls c2 WHERE c2.ca OR c2.cb OR c2.cc OR c2.cd OR c2.ce
                     ORDER BY c2.entidad_id LIMIT 20) x)
      INTO v_a, v_b, v_c, v_d, v_e, v_ids
      FROM cls;
    RAISE NOTICE 'F06-01H-0354 PRECHECK PC-04: (a)=% (b)=% (c)=% (d)=% (e)=%', v_a, v_b, v_c, v_d, v_e;
    IF v_a + v_b + v_c + v_d + v_e > 0 THEN
        RAISE EXCEPTION 'F06-01H-0354 PRECHECK PC-04: BLOQUEA (STOP de datos) - violaciones de G2 en H: (a)=% (b)=% (c)=% (d)=% (e)=%; primeras entidad_id: %',
            v_a, v_b, v_c, v_d, v_e, v_ids;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.financiaciones f
     WHERE f.tipo_financiacion = 'HIPOTECA'
       AND EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                    WHERE v.financiacion_entidad_id = f.entidad_id
                      AND v.motivo_version = 'ALTA' AND v.hecho_causa_id IS NOT NULL);
    RAISE NOTICE 'F06-01H-0354 PRECHECK PC-05: financiaciones en M = %', v_n;
    IF v_n > 0 THEN
        RAISE EXCEPTION 'F06-01H-0354 PRECHECK PC-05: BLOQUEA (STOP de datos) - % financiacion(es) en M antes de F06-01H', v_n;
    END IF;

    FOR v_ids IN
        SELECT pg_catalog.format('%s: %s cuota(s)', f.tipo_financiacion, pg_catalog.count(*))
          FROM gapto.financiacion_cuotas q
          JOIN gapto.financiaciones f ON f.entidad_id = q.financiacion_entidad_id
          LEFT JOIN gapto.previsiones p ON p.id = q.prevision_id
         WHERE q.prevision_id IS NULL OR p.estado IS DISTINCT FROM 'ABIERTA'
         GROUP BY f.tipo_financiacion ORDER BY f.tipo_financiacion
    LOOP
        RAISE NOTICE 'F06-01H-0354 PRECHECK PC-06 (informativo) cuotas que G1 congela: %', v_ids;
    END LOOP;

    FOR v_ids IN
        SELECT pg_catalog.format('%s: %s', p.estado, pg_catalog.count(*))
          FROM gapto.financiacion_cuotas q
          JOIN gapto.previsiones p ON p.id = q.prevision_id
         GROUP BY p.estado ORDER BY p.estado
    LOOP
        RAISE NOTICE 'F06-01H-0354 PRECHECK PC-07 (informativo) previsiones referenciadas por cuotas: %', v_ids;
    END LOOP;

    RAISE NOTICE 'F06-01H-0354 PRECHECK: OK';
END;
$precheck_0354$;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ============================================================
-- F1 / T1 · G1: cuota inmutable salvo con prevision ABIERTA visible.
-- ============================================================
CREATE FUNCTION gapto.fn_guard_cuota_inmutable_no_abierta()
RETURNS trigger AS $fn$
DECLARE
    v_estado text;
    v_n      bigint;
BEGIN
    IF OLD.prevision_id IS NULL THEN
        RAISE EXCEPTION 'INV-0354-G1: la cuota % no tiene prevision; su cuadro no se modifica', OLD.id;
    END IF;

    SELECT p.estado INTO v_estado
      FROM gapto.previsiones p
     WHERE p.id = OLD.prevision_id
       FOR SHARE;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'INV-0354-G1: VISIBILIDAD - la prevision % de la cuota % no es visible (contexto de tenant ausente o distinto)', OLD.prevision_id, OLD.id;
    END IF;

    IF v_estado <> 'ABIERTA' THEN
        RAISE EXCEPTION 'INV-0354-G1: la cuota % tiene su prevision en estado % y no se modifica', OLD.id, v_estado;
    END IF;

    IF NEW.prevision_id IS DISTINCT FROM OLD.prevision_id
       OR NEW.financiacion_entidad_id IS DISTINCT FROM OLD.financiacion_entidad_id THEN
        RAISE EXCEPTION 'INV-0354-G1: la prevision y la financiacion de la cuota % son inmutables', OLD.id;
    END IF;

    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_guard_cuota_inmutable_no_abierta() IS
    'F06-01H 0354 G1 (contrato v0.4 §10.1.2). BEFORE UPDATE de financiacion_cuotas: prevision_id NULL bloquea; la prevision se lee FOR SHARE y, si no es visible o no esta ABIERTA, rechaza; prevision_id y financiacion_entidad_id son inmutables. Ambito: todas las cuotas.';

CREATE TRIGGER trg_financiacion_cuotas__inmutable_no_abierta
    BEFORE UPDATE ON gapto.financiacion_cuotas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_cuota_inmutable_no_abierta();

-- ============================================================
-- F2 / T2 · G1-R: la prevision de una cuota no se reabre.
-- ============================================================
CREATE FUNCTION gapto.fn_guard_prevision_cuota_no_reabrible()
RETURNS trigger AS $fn$
BEGIN
    IF EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q WHERE q.prevision_id = OLD.id) THEN
        RAISE EXCEPTION 'INV-0354-G1R: la prevision % es la de una cuota de financiacion y no vuelve a ABIERTA', OLD.id;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_guard_prevision_cuota_no_reabrible() IS
    'F06-01H 0354 G1-R (contrato v0.4 §10.1.2). BEFORE UPDATE OF estado de previsiones cuando pasa de un estado distinto de ABIERTA a ABIERTA: si una cuota la referencia, rechaza. Las demas previsiones, sin cambio.';

CREATE TRIGGER trg_previsiones__cuota_no_reabrible
    BEFORE UPDATE OF estado ON gapto.previsiones
    FOR EACH ROW
    WHEN (OLD.estado <> 'ABIERTA' AND NEW.estado = 'ABIERTA')
    EXECUTE FUNCTION gapto.fn_guard_prevision_cuota_no_reabrible();

-- ============================================================
-- F4 · G2 nucleo: canonicaliza, bloquea, relee y evalua.
-- ============================================================
CREATE FUNCTION gapto.fn_validar_cuadro_hipoteca(p_financiaciones uuid[])
RETURNS void AS $fn$
DECLARE
    v_fs         uuid[];
    v_bloqueadas bigint;
    v_r          record;
BEGIN
    SELECT pg_catalog.array_agg(DISTINCT x ORDER BY x) INTO v_fs
      FROM pg_catalog.unnest(p_financiaciones) AS t(x)
     WHERE x IS NOT NULL;

    IF v_fs IS NULL OR pg_catalog.cardinality(v_fs) = 0 THEN
        RETURN;
    END IF;

    PERFORM 1
       FROM gapto.financiaciones f
      WHERE f.entidad_id = ANY (v_fs)
      ORDER BY f.entidad_id
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS v_bloqueadas = ROW_COUNT;

    IF v_bloqueadas <> pg_catalog.cardinality(v_fs) THEN
        RAISE EXCEPTION 'INV-0354-G2: VISIBILIDAD - se esperaban % financiaciones y solo % son visibles/bloqueables al validar el cuadro (contexto de tenant ausente o distinto)',
            pg_catalog.cardinality(v_fs), v_bloqueadas;
    END IF;

    FOR v_r IN
        SELECT f.entidad_id,
               f.capital_original_contratado AS capital,
               (SELECT pg_catalog.count(*) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) AS n,
               (SELECT pg_catalog.count(*) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id AND q.capital_previsto IS NULL) AS n_null,
               (SELECT pg_catalog.min(q.numero_cuota) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) AS mn,
               (SELECT pg_catalog.max(q.numero_cuota) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) AS mx,
               (SELECT pg_catalog.count(DISTINCT q.numero_cuota) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) AS nd,
               (SELECT pg_catalog.sum(q.capital_previsto) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) AS s
          FROM gapto.financiaciones f
         WHERE f.entidad_id = ANY (v_fs)
           AND f.tipo_financiacion = 'HIPOTECA' AND (
               EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q
                        WHERE q.financiacion_entidad_id = f.entidad_id)
               OR EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                           WHERE v.financiacion_entidad_id = f.entidad_id
                             AND v.motivo_version = 'ALTA'
                             AND v.hecho_causa_id IS NOT NULL))
         ORDER BY f.entidad_id
    LOOP
        IF v_r.capital IS NULL OR v_r.capital <= 0 THEN
            RAISE EXCEPTION 'INV-0354-G2: la hipoteca % no tiene capital contratado positivo', v_r.entidad_id;
        END IF;
        IF v_r.n = 0 THEN
            RAISE EXCEPTION 'INV-0354-G2: la hipoteca % con cuadro calculado no tiene cuotas', v_r.entidad_id;
        END IF;
        IF v_r.n_null > 0 THEN
            RAISE EXCEPTION 'INV-0354-G2: la hipoteca % tiene % cuota(s) sin capital previsto', v_r.entidad_id, v_r.n_null;
        END IF;
        IF NOT (v_r.mn = 1 AND v_r.mx = v_r.n AND v_r.nd = v_r.n) THEN
            RAISE EXCEPTION 'INV-0354-G2: la numeracion de las cuotas de la hipoteca % no es 1..%', v_r.entidad_id, v_r.n;
        END IF;
        IF v_r.s <> v_r.capital THEN
            RAISE EXCEPTION 'INV-0354-G2: la suma de capital de las cuotas de la hipoteca % es % y el capital contratado es %', v_r.entidad_id, v_r.s, v_r.capital;
        END IF;
    END LOOP;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_validar_cuadro_hipoteca(uuid[]) IS
    'F06-01H 0354 G2 nucleo (contrato v0.4 §10.1.2, AJ-T3D-06). (1) canonicaliza sin NULL, sin duplicados y en orden ascendente; (2) bloquea las financiaciones FOR NO KEY UPDATE ORDER BY entidad_id y exige ROW_COUNT exacto (fail-closed, patron 0310); (3) en sentencia posterior relee el estado final; para F en H (HIPOTECA con cuotas o con version ALTA con hecho causa) exige capital no NULL y > 0, al menos una cuota, ningun capital NULL, numeracion exactamente 1..N y suma de capital igual al capital contratado. Aborta en la primera financiacion incumplidora por entidad_id.';

-- ============================================================
-- F3 / T3 T4 T5 · G2 despachador. CASE sobre TG_TABLE_NAME, sin SQL dinamico.
-- ============================================================
CREATE FUNCTION gapto.fn_check_cuadro_hipoteca()
RETURNS trigger AS $fn$
DECLARE
    v_fs uuid[];
BEGIN
    CASE TG_TABLE_NAME
        WHEN 'financiacion_cuotas' THEN
            IF TG_OP = 'INSERT' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            ELSIF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[OLD.financiacion_entidad_id];
            END IF;
        WHEN 'financiaciones' THEN
            v_fs := ARRAY[NEW.entidad_id];
        WHEN 'financiacion_condiciones_versiones' THEN
            IF TG_OP = 'UPDATE' THEN
                v_fs := ARRAY[NEW.financiacion_entidad_id, OLD.financiacion_entidad_id];
            ELSE
                v_fs := ARRAY[NEW.financiacion_entidad_id];
            END IF;
        ELSE
            RAISE EXCEPTION 'INV-0354-G2: fn_check_cuadro_hipoteca, tabla no contemplada %', TG_TABLE_NAME;
    END CASE;

    PERFORM gapto.fn_validar_cuadro_hipoteca(v_fs);
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_cuadro_hipoteca() IS
    'F06-01H 0354 G2 despachador (contrato v0.4 §10.1.2). Por TG_TABLE_NAME, sin SQL dinamico; OLD y NEW solo aportan identificadores de financiacion (NEW y OLD en UPDATE, OLD en DELETE). La validacion vive en fn_validar_cuadro_hipoteca.';

CREATE CONSTRAINT TRIGGER trg_financiacion_cuotas__cuadro_hipoteca
    AFTER INSERT OR UPDATE OF capital_previsto, numero_cuota, financiacion_entidad_id OR DELETE
    ON gapto.financiacion_cuotas
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();

CREATE CONSTRAINT TRIGGER trg_financiaciones__cuadro_hipoteca
    AFTER UPDATE OF capital_original_contratado, tipo_financiacion
    ON gapto.financiaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();

CREATE CONSTRAINT TRIGGER trg_financiacion_condiciones_versiones__cuadro_hipoteca
    AFTER INSERT OR UPDATE OF motivo_version, hecho_causa_id, financiacion_entidad_id
    ON gapto.financiacion_condiciones_versiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();

-- ============================================================
-- F5 / T6 · G2-E: una hipoteca con cuadro no sale del ambito por su tipo.
-- ============================================================
CREATE FUNCTION gapto.fn_guard_financiacion_ambito_hipoteca()
RETURNS trigger AS $fn$
BEGIN
    IF EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q
                WHERE q.financiacion_entidad_id = OLD.entidad_id)
       OR EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                   WHERE v.financiacion_entidad_id = OLD.entidad_id
                     AND v.motivo_version = 'ALTA'
                     AND v.hecho_causa_id IS NOT NULL) THEN
        RAISE EXCEPTION 'INV-0354-G2E: la hipoteca % tiene cuadro y no cambia de tipo', OLD.entidad_id;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_guard_financiacion_ambito_hipoteca() IS
    'F06-01H 0354 G2-E (contrato v0.4 §10.1.2). BEFORE UPDATE OF tipo_financiacion de HIPOTECA a otro tipo: si la financiacion tiene cuotas o version ALTA con hecho causa, rechaza (el ambito de G2 solo crece).';

CREATE TRIGGER trg_financiaciones__ambito_hipoteca
    BEFORE UPDATE OF tipo_financiacion ON gapto.financiaciones
    FOR EACH ROW
    WHEN (OLD.tipo_financiacion = 'HIPOTECA' AND NEW.tipo_financiacion <> 'HIPOTECA')
    EXECUTE FUNCTION gapto.fn_guard_financiacion_ambito_hipoteca();

-- ============================================================
-- F6 / T7 · G3: historico de las versiones de una hipoteca con cuadro calculado.
-- ============================================================
CREATE FUNCTION gapto.fn_guard_condiciones_version_historico()
RETURNS trigger AS $fn$
BEGIN
    IF EXISTS (SELECT 1 FROM gapto.financiaciones f
                WHERE f.entidad_id = OLD.financiacion_entidad_id
                  AND f.tipo_financiacion = 'HIPOTECA'
                  AND EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                               WHERE v.financiacion_entidad_id = f.entidad_id
                                 AND v.motivo_version = 'ALTA'
                                 AND v.hecho_causa_id IS NOT NULL)) THEN
        IF NOT (OLD.vigente_hasta IS NULL AND NEW.vigente_hasta IS NOT NULL) THEN
            RAISE EXCEPTION 'INV-0354-G3: la version % de una hipoteca con cuadro calculado solo admite el primer cierre de vigente_hasta', OLD.id;
        END IF;
        IF (pg_catalog.to_jsonb(NEW) - 'vigente_hasta') IS DISTINCT FROM (pg_catalog.to_jsonb(OLD) - 'vigente_hasta') THEN
            RAISE EXCEPTION 'INV-0354-G3: la version % de una hipoteca con cuadro calculado es historica; solo cambia vigente_hasta', OLD.id;
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_guard_condiciones_version_historico() IS
    'F06-01H 0354 G3 (contrato v0.4 §10.1.2). BEFORE UPDATE de financiacion_condiciones_versiones: si la financiacion de OLD esta en M (evaluado antes del cambio), solo admite el primer cierre de vigente_hasta con todas las demas columnas sin cambio. Fuera de M, sin restriccion nueva.';

CREATE TRIGGER trg_financiacion_condiciones_versiones__historico
    BEFORE UPDATE ON gapto.financiacion_condiciones_versiones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_guard_condiciones_version_historico();

RESET ROLE;

DO $postcheck_0354$
DECLARE
    v_n bigint;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_language l ON l.oid = p.prolang
     WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace
       AND p.proname IN ('fn_guard_cuota_inmutable_no_abierta',
                         'fn_guard_prevision_cuota_no_reabrible',
                         'fn_check_cuadro_hipoteca',
                         'fn_validar_cuadro_hipoteca',
                         'fn_guard_financiacion_ambito_hipoteca',
                         'fn_guard_condiciones_version_historico')
       AND NOT p.prosecdef AND l.lanname = 'plpgsql' AND p.proacl IS NULL
       AND p.proowner = 'gapto_owner'::pg_catalog.regrole
       AND pg_catalog.strpos(p.prosrc, '--') = 0;
    IF v_n <> 6 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-01: funciones de 0354 conformes = % (esperadas 6: invoker, plpgsql, gapto_owner, ACL por defecto, sin comentarios en prosrc)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p
     WHERE p.oid = 'gapto.fn_validar_cuadro_hipoteca(uuid[])'::pg_catalog.regprocedure
       AND p.prorettype = 'void'::pg_catalog.regtype;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-01: firma de fn_validar_cuadro_hipoteca(uuid[]) no conforme';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
     WHERE NOT t.tgisinternal AND t.tgenabled = 'O'
       AND (
            (t.tgname = 'trg_financiacion_cuotas__inmutable_no_abierta'
             AND t.tgrelid = 'gapto.financiacion_cuotas'::pg_catalog.regclass
             AND t.tgtype = 19 AND t.tgattr::text = '' AND t.tgqual IS NULL
             AND NOT t.tgdeferrable AND t.tgconstraint = 0
             AND p.proname = 'fn_guard_cuota_inmutable_no_abierta')
         OR (t.tgname = 'trg_previsiones__cuota_no_reabrible'
             AND t.tgrelid = 'gapto.previsiones'::pg_catalog.regclass
             AND t.tgtype = 19 AND t.tgqual IS NOT NULL
             AND t.tgattr::text = (SELECT a.attnum::text FROM pg_catalog.pg_attribute a
                                    WHERE a.attrelid = 'gapto.previsiones'::pg_catalog.regclass AND a.attname = 'estado')
             AND NOT t.tgdeferrable AND t.tgconstraint = 0
             AND p.proname = 'fn_guard_prevision_cuota_no_reabrible')
         OR (t.tgname = 'trg_financiacion_cuotas__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiacion_cuotas'::pg_catalog.regclass
             AND t.tgtype = 29 AND t.tgqual IS NULL
             AND t.tgdeferrable AND t.tginitdeferred AND t.tgconstraint <> 0
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 3
             AND p.proname = 'fn_check_cuadro_hipoteca')
         OR (t.tgname = 'trg_financiaciones__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiaciones'::pg_catalog.regclass
             AND t.tgtype = 17 AND t.tgqual IS NULL
             AND t.tgdeferrable AND t.tginitdeferred AND t.tgconstraint <> 0
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 2
             AND p.proname = 'fn_check_cuadro_hipoteca')
         OR (t.tgname = 'trg_financiacion_condiciones_versiones__cuadro_hipoteca'
             AND t.tgrelid = 'gapto.financiacion_condiciones_versiones'::pg_catalog.regclass
             AND t.tgtype = 21 AND t.tgqual IS NULL
             AND t.tgdeferrable AND t.tginitdeferred AND t.tgconstraint <> 0
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 3
             AND p.proname = 'fn_check_cuadro_hipoteca')
         OR (t.tgname = 'trg_financiaciones__ambito_hipoteca'
             AND t.tgrelid = 'gapto.financiaciones'::pg_catalog.regclass
             AND t.tgtype = 19 AND t.tgqual IS NOT NULL
             AND pg_catalog.cardinality(t.tgattr::int2[]) = 1
             AND NOT t.tgdeferrable AND t.tgconstraint = 0
             AND p.proname = 'fn_guard_financiacion_ambito_hipoteca')
         OR (t.tgname = 'trg_financiacion_condiciones_versiones__historico'
             AND t.tgrelid = 'gapto.financiacion_condiciones_versiones'::pg_catalog.regclass
             AND t.tgtype = 19 AND t.tgattr::text = '' AND t.tgqual IS NULL
             AND NOT t.tgdeferrable AND t.tgconstraint = 0
             AND p.proname = 'fn_guard_condiciones_version_historico')
       );
    IF v_n <> 7 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-02: triggers de 0354 conformes = % (esperados 7)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.financiaciones f
     WHERE f.tipo_financiacion = 'HIPOTECA'
       AND (EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q WHERE q.financiacion_entidad_id = f.entidad_id)
            OR EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v
                        WHERE v.financiacion_entidad_id = f.entidad_id
                          AND v.motivo_version = 'ALTA' AND v.hecho_causa_id IS NOT NULL))
       AND (f.capital_original_contratado IS NULL OR f.capital_original_contratado <= 0
            OR NOT EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q WHERE q.financiacion_entidad_id = f.entidad_id)
            OR EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q
                        WHERE q.financiacion_entidad_id = f.entidad_id AND q.capital_previsto IS NULL)
            OR (SELECT pg_catalog.sum(q.capital_previsto) FROM gapto.financiacion_cuotas q
                 WHERE q.financiacion_entidad_id = f.entidad_id) <> f.capital_original_contratado
            OR (SELECT pg_catalog.count(*) <> pg_catalog.count(DISTINCT q.numero_cuota)
                       OR pg_catalog.min(q.numero_cuota) <> 1 OR pg_catalog.max(q.numero_cuota) <> pg_catalog.count(*)
                  FROM gapto.financiacion_cuotas q WHERE q.financiacion_entidad_id = f.entidad_id));
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-03: % hipoteca(s) incumplen G2', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r' AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: tablas con FORCE RLS = % (esperadas 75)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 34 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: funciones = % (esperadas 34)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 65 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: triggers no internos = % (esperados 65)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND NOT t.tgisinternal AND t.tgconstraint <> 0;
    IF v_n <> 44 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: constraint triggers = % (esperados 44)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r';
    IF v_n <> 80 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: tablas = % (esperadas 80)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 744 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: columnas de tabla = % (esperadas 744)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: indices = % (esperados 287)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype IN ('p', 'u', 'f', 'c', 'x');
    IF v_n <> 611 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: constraints declarativos = % (esperados 611)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: policies = % (esperadas 82)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind IN ('r', 'v', 'p')
       AND a.grantee = 'gapto_runtime'::pg_catalog.regrole;
    IF v_n <> 266 THEN
        RAISE EXCEPTION 'F06-01H-0354 POSTCHECK PO-04: privilegios de tabla de gapto_runtime = % (esperados 266)', v_n;
    END IF;

    RAISE NOTICE 'F06-01H-0354 POSTCHECK: OK';
END;
$postcheck_0354$;

COMMIT;
