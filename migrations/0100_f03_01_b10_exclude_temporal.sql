-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0100_f03_01_b10_exclude_temporal.sql
-- Ruta: migrations/0100_f03_01_b10_exclude_temporal.sql
-- Descripción: Materializa los 11 constraints EXCLUDE temporales
--              fijados en F03-00-G-A, usando daterange(vigente_desde,
--              vigente_hasta,'[]') semántica inclusiva y btree_gist
--              para columnas de igualdad. DEFERRABLE INITIALLY
--              IMMEDIATE en todos. Donde vigente_desde es físicamente
--              nullable (legacy con inicio desconocido), el EXCLUDE
--              se restringe con WHERE vigente_desde IS NOT NULL: el
--              histórico indeterminado se preserva sin fabricar
--              conocimiento y sin bloquear altas nuevas con inicio
--              conocido.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_exclude_count integer;
BEGIN
    SELECT count(*) INTO v_exclude_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'x';

    IF v_exclude_count <> 0 THEN
        RAISE EXCEPTION 'F03-01-B10 PRECHECK: ya existen % EXCLUDE; se esperaba 0', v_exclude_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET LOCAL search_path = gapto, gapto_ext, public;
SET ROLE gapto_owner;

-- 1. cuenta_participaciones (vigente_desde NOT NULL: aplica siempre)
ALTER TABLE gapto.cuenta_participaciones ADD CONSTRAINT ex_cuenta_participaciones__cuenta_actor
    EXCLUDE USING gist (cuenta_id WITH =, actor_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 2. entidad_participaciones (vigente_desde NOT NULL: aplica siempre)
ALTER TABLE gapto.entidad_participaciones ADD CONSTRAINT ex_entidad_participaciones__entidad_actor
    EXCLUDE USING gist (entidad_id WITH =, actor_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 3. entidad_relaciones (vigente_desde nullable: solo con inicio conocido)
ALTER TABLE gapto.entidad_relaciones ADD CONSTRAINT ex_entidad_relaciones__origen_destino_tipo
    EXCLUDE USING gist (entidad_origen_id WITH =, entidad_destino_id WITH =, tipo_relacion WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    WHERE (vigente_desde IS NOT NULL)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 4. regla_versiones (vigente_desde NOT NULL: aplica siempre)
ALTER TABLE gapto.regla_versiones ADD CONSTRAINT ex_regla_versiones__regla
    EXCLUDE USING gist (regla_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 5. contrato_participantes: no-solapamiento por contrato+actor+rol (vigente_desde NOT NULL)
ALTER TABLE gapto.contrato_participantes ADD CONSTRAINT ex_contrato_participantes__contrato_actor_rol
    EXCLUDE USING gist (contrato_entidad_id WITH =, actor_id WITH =, rol WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 6. contrato_participantes: como máximo un principal=true simultáneo por contrato+rol
ALTER TABLE gapto.contrato_participantes ADD CONSTRAINT ex_contrato_participantes__principal_por_rol
    EXCLUDE USING gist (contrato_entidad_id WITH =, rol WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    WHERE (principal = true)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 7. propiedad_servicios (vigente_desde NOT NULL: aplica siempre)
ALTER TABLE gapto.propiedad_servicios ADD CONSTRAINT ex_propiedad_servicios__propiedad_servicio
    EXCLUDE USING gist (propiedad_entidad_id WITH =, servicio_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 8. contrato_servicios: tratamiento contractual exclusivo por contrato+servicio (vigente_desde NOT NULL)
ALTER TABLE gapto.contrato_servicios ADD CONSTRAINT ex_contrato_servicios__contrato_servicio
    EXCLUDE USING gist (contrato_entidad_id WITH =, servicio_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 9. financiacion_condiciones_versiones (vigente_desde NOT NULL: aplica siempre)
ALTER TABLE gapto.financiacion_condiciones_versiones ADD CONSTRAINT ex_financiacion_condiciones_versiones__financiacion
    EXCLUDE USING gist (financiacion_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 10. inversion_objetivos_versiones (vigente_desde nullable en legacy: solo con inicio conocido)
ALTER TABLE gapto.inversion_objetivos_versiones ADD CONSTRAINT ex_inversion_objetivos_versiones__inversion
    EXCLUDE USING gist (inversion_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    WHERE (vigente_desde IS NOT NULL)
    DEFERRABLE INITIALLY IMMEDIATE;

-- 11. contrato_revision_renta_versiones (vigente_desde nullable en legacy: solo con inicio conocido)
ALTER TABLE gapto.contrato_revision_renta_versiones ADD CONSTRAINT ex_contrato_revision_renta_versiones__contrato
    EXCLUDE USING gist (contrato_entidad_id WITH =, daterange(vigente_desde, vigente_hasta, '[]') WITH &&)
    WHERE (vigente_desde IS NOT NULL)
    DEFERRABLE INITIALLY IMMEDIATE;

RESET ROLE;

DO $gapto$
DECLARE
    v_exclude_count integer;
BEGIN
    SELECT count(*) INTO v_exclude_count
      FROM pg_catalog.pg_constraint con
      JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND con.contype = 'x';

    IF v_exclude_count <> 11 THEN
        RAISE EXCEPTION 'F03-01-B10 POSTCHECK: esperados 11 EXCLUDE; encontrados=%', v_exclude_count;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
