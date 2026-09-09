-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0110_f03_01_b12_invariantes_parte1.sql
-- Ruta: migrations/0110_f03_01_b12_invariantes_parte1.sql
-- Descripción: Primera parte de las invariantes multi-fila fijadas
--              en F03-00-G-B/G-C que requieren constraint triggers
--              (no expresables como CHECK de fila). Cubre:
--                1) Prevención de ciclos en 6 jerarquías/cadenas.
--                2) GARANTIZADA_POR restringida a FINANCIACION→PROPIEDAD
--                   con mismo owner.
--                3) tercero_personas exige terceros.naturaleza=PERSONA.
--                4) Exactamente un actor self (tercero_id NULL) por
--                   owner_user_id en actores_financieros (DEFERRED).
--                5) Exactamente un subtipo coherente por entidad
--                   (DEFERRED, cubre entidades + 7 subtipos).
--              PENDIENTE explícito para una parte 2 posterior: sumas
--              multi-fila con locking (participaciones ≤100%,
--              atribuciones, conciliación tesorería, asignaciones de
--              inversión, prioridad de BOLSAS), que requieren
--              estrategia de locks de padres/advisory locks y se
--              tratarán junto con las funciones SECURITY DEFINER de
--              F03-00-H para no construir esa pieza dos veces.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ============================================================
-- 1) Prevención de ciclos (función genérica reutilizable)
-- ============================================================
CREATE FUNCTION gapto.fn_prevent_self_referencing_cycle()
RETURNS trigger AS $fn$
DECLARE
    v_fk_col text := TG_ARGV[0];
    v_pk_col text := TG_ARGV[1];
    v_new_pk uuid;
    v_new_fk uuid;
    v_found boolean;
    v_sql text;
BEGIN
    EXECUTE format('SELECT ($1).%I, ($1).%I', v_pk_col, v_fk_col) INTO v_new_pk, v_new_fk USING NEW;

    IF v_new_fk IS NULL THEN
        RETURN NEW;
    END IF;

    IF v_new_fk = v_new_pk THEN
        RAISE EXCEPTION 'Ciclo detectado en gapto.%: % no puede referenciarse a si mismo via %', TG_TABLE_NAME, v_new_pk, v_fk_col;
    END IF;

    v_sql := format(
        'WITH RECURSIVE chain AS (
            SELECT %I AS current_fk FROM gapto.%I WHERE %I = $1
            UNION ALL
            SELECT t.%I FROM gapto.%I t JOIN chain c ON t.%I = c.current_fk
        )
        SELECT EXISTS (SELECT 1 FROM chain WHERE current_fk = $2)',
        v_fk_col, TG_TABLE_NAME, v_pk_col,
        v_fk_col, TG_TABLE_NAME, v_pk_col
    );
    EXECUTE v_sql INTO v_found USING v_new_fk, v_new_pk;

    IF v_found THEN
        RAISE EXCEPTION 'Ciclo detectado en gapto.%: % introduciria un ciclo de jerarquia via %', TG_TABLE_NAME, v_new_pk, v_fk_col;
    END IF;

    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_prevent_self_referencing_cycle() IS
    'F03-01-B12: generica, evita ciclos en jerarquias self-FK. Argumentos: (columna_fk, columna_pk).';

CREATE TRIGGER trg_regiones__no_ciclo
    BEFORE INSERT OR UPDATE OF parent_region_id ON gapto.regiones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('parent_region_id', 'id');

CREATE TRIGGER trg_clasificaciones_tercero__no_ciclo
    BEFORE INSERT OR UPDATE OF parent_id ON gapto.clasificaciones_tercero
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('parent_id', 'id');

CREATE TRIGGER trg_categorias_financieras__no_ciclo
    BEFORE INSERT OR UPDATE OF parent_id ON gapto.categorias_financieras
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('parent_id', 'id');

CREATE TRIGGER trg_inversiones__no_ciclo
    BEFORE INSERT OR UPDATE OF inversion_padre_entidad_id ON gapto.inversiones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('inversion_padre_entidad_id', 'entidad_id');

CREATE TRIGGER trg_presupuestos__no_ciclo
    BEFORE INSERT OR UPDATE OF reemplaza_presupuesto_id ON gapto.presupuestos
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('reemplaza_presupuesto_id', 'id');

CREATE TRIGGER trg_cierres_mensuales__no_ciclo
    BEFORE INSERT OR UPDATE OF reemplaza_cierre_id ON gapto.cierres_mensuales
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_prevent_self_referencing_cycle('reemplaza_cierre_id', 'id');

-- ============================================================
-- 2) GARANTIZADA_POR restringida a FINANCIACION -> PROPIEDAD, mismo owner
-- ============================================================
CREATE FUNCTION gapto.fn_check_garantizada_por()
RETURNS trigger AS $fn$
DECLARE
    v_origen_tipo varchar;
    v_destino_tipo varchar;
    v_origen_owner uuid;
    v_destino_owner uuid;
BEGIN
    IF NEW.tipo_relacion = 'GARANTIZADA_POR' THEN
        SELECT tipo_entidad, owner_user_id INTO v_origen_tipo, v_origen_owner
          FROM gapto.entidades WHERE id = NEW.entidad_origen_id;
        SELECT tipo_entidad, owner_user_id INTO v_destino_tipo, v_destino_owner
          FROM gapto.entidades WHERE id = NEW.entidad_destino_id;

        IF v_origen_tipo IS DISTINCT FROM 'FINANCIACION' OR v_destino_tipo IS DISTINCT FROM 'PROPIEDAD' THEN
            RAISE EXCEPTION 'GARANTIZADA_POR solo admite FINANCIACION (origen) -> PROPIEDAD (destino); origen=%, destino=%', v_origen_tipo, v_destino_tipo;
        END IF;

        IF v_origen_owner IS DISTINCT FROM v_destino_owner THEN
            RAISE EXCEPTION 'GARANTIZADA_POR exige que origen y destino compartan owner_user_id';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_garantizada_por() IS
    'F03-01-B12: restringe entidad_relaciones.tipo_relacion=GARANTIZADA_POR a FINANCIACION->PROPIEDAD del mismo owner.';

CREATE TRIGGER trg_entidad_relaciones__garantizada_por
    BEFORE INSERT OR UPDATE ON gapto.entidad_relaciones
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_garantizada_por();

-- ============================================================
-- 3) tercero_personas exige terceros.naturaleza = PERSONA
-- ============================================================
CREATE FUNCTION gapto.fn_check_tercero_persona_naturaleza()
RETURNS trigger AS $fn$
DECLARE
    v_naturaleza varchar;
BEGIN
    SELECT naturaleza INTO v_naturaleza FROM gapto.terceros WHERE id = NEW.tercero_id;
    IF v_naturaleza IS DISTINCT FROM 'PERSONA' THEN
        RAISE EXCEPTION 'tercero_personas solo puede existir para terceros.naturaleza=PERSONA (tercero_id=%, naturaleza=%)', NEW.tercero_id, v_naturaleza;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_tercero_persona_naturaleza() IS
    'F03-01-B12: exige terceros.naturaleza=PERSONA para poder crear tercero_personas.';

CREATE TRIGGER trg_tercero_personas__naturaleza
    BEFORE INSERT OR UPDATE ON gapto.tercero_personas
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_tercero_persona_naturaleza();

-- ============================================================
-- 4) Exactamente un actor self (tercero_id NULL) por owner_user_id
-- ============================================================
CREATE FUNCTION gapto.fn_check_actor_self_unico()
RETURNS trigger AS $fn$
DECLARE
    v_owner uuid;
    v_count integer;
BEGIN
    v_owner := COALESCE(NEW.owner_user_id, OLD.owner_user_id);
    SELECT count(*) INTO v_count
      FROM gapto.actores_financieros
     WHERE owner_user_id = v_owner AND tercero_id IS NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION 'actores_financieros: debe existir exactamente un actor self por owner_user_id=% (encontrados=%)', v_owner, v_count;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_actor_self_unico() IS
    'F03-01-B12: invariante diferida — exactamente un actor self (tercero_id IS NULL) por owner_user_id.';

CREATE CONSTRAINT TRIGGER trg_actores_financieros__self_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.actores_financieros
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_actor_self_unico();

-- ============================================================
-- 5) Exactamente un subtipo coherente por entidad (diferida)
-- ============================================================
CREATE FUNCTION gapto.fn_check_entidad_subtipo_unico()
RETURNS trigger AS $fn$
DECLARE
    v_id uuid;
    v_tipo varchar;
    v_count integer;
BEGIN
    IF TG_TABLE_NAME = 'entidades' THEN
        v_id := COALESCE(NEW.id, OLD.id);
    ELSE
        v_id := COALESCE(NEW.entidad_id, OLD.entidad_id);
    END IF;

    SELECT tipo_entidad INTO v_tipo FROM gapto.entidades WHERE id = v_id;

    IF v_tipo IS NULL THEN
        RETURN NULL;
    END IF;

    v_count := CASE v_tipo
        WHEN 'PROPIEDAD'          THEN (SELECT count(*) FROM gapto.propiedades WHERE entidad_id = v_id)
        WHEN 'CONTRATO'           THEN (SELECT count(*) FROM gapto.contratos WHERE entidad_id = v_id)
        WHEN 'SERVICIO'           THEN (SELECT count(*) FROM gapto.servicios WHERE entidad_id = v_id)
        WHEN 'FINANCIACION'       THEN (SELECT count(*) FROM gapto.financiaciones WHERE entidad_id = v_id)
        WHEN 'INVERSION'          THEN (SELECT count(*) FROM gapto.inversiones WHERE entidad_id = v_id)
        WHEN 'DERECHO_OBLIGACION' THEN (SELECT count(*) FROM gapto.derechos_obligaciones_financieras WHERE entidad_id = v_id)
        WHEN 'CONTEXTO'           THEN (SELECT count(*) FROM gapto.contextos WHERE entidad_id = v_id)
        ELSE 0
    END;

    IF v_count <> 1 THEN
        RAISE EXCEPTION 'entidades: la entidad % (tipo=%) debe tener exactamente un subtipo coherente (encontrados=%)', v_id, v_tipo, v_count;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION gapto.fn_check_entidad_subtipo_unico() IS
    'F03-01-B12: invariante diferida — exactamente un subtipo coherente con tipo_entidad por fila de entidades.';

CREATE CONSTRAINT TRIGGER trg_entidades__subtipo_unico
    AFTER INSERT OR UPDATE OF tipo_entidad ON gapto.entidades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_propiedades__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.propiedades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_contratos__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.contratos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_servicios__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.servicios
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_financiaciones__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.financiaciones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_inversiones__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.inversiones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_derechos_obligaciones__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.derechos_obligaciones_financieras
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

CREATE CONSTRAINT TRIGGER trg_contextos__subtipo_unico
    AFTER INSERT OR UPDATE OR DELETE ON gapto.contextos
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_entidad_subtipo_unico();

RESET ROLE;

DO $gapto$
DECLARE
    v_funcs integer;
    v_triggers integer;
BEGIN
    SELECT count(*) INTO v_funcs
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'gapto' AND p.proname LIKE 'fn_%';

    SELECT count(*) INTO v_triggers
      FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND NOT t.tgisinternal;

    IF v_funcs <> 5 THEN
        RAISE EXCEPTION 'F03-01-B12 POSTCHECK: esperadas 5 funciones fn_; encontradas=%', v_funcs;
    END IF;

    IF v_triggers <> 17 THEN
        RAISE EXCEPTION 'F03-01-B12 POSTCHECK: esperados 17 triggers; encontrados=%', v_triggers;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
