-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0288_f03_02_anclas_tenant_hecho_entidades_inversion.sql
-- Ruta: migrations/0288_f03_02_anclas_tenant_hecho_entidades_inversion.sql
-- Descripcion: FASE 03 / F03-02. Endurecimiento declarativo de tenant, previo
--   y separado de 0290. No toca jerarquia, no toca D-080 y no altera ninguna
--   semantica funcional: solo impide fisicamente lo que ya estaba prohibido.
--
--   DOS SUPERFICIES.
--
--   1) hecho_entidades. Su coherencia de tenant vive unicamente en el WITH
--      CHECK de su policy, que no sobrevive a BYPASSRLS. Quedo registrado como
--      deuda junto a D-147. Deja de ser una deuda tolerable porque 0290 va a
--      convertir esta tabla en la fuente autoritativa de la inversion
--      principal de un efecto (D-080): una fila principal cross-tenant
--      insertada con BYPASSRLS destruiria el significado de la invariante.
--
--   2) inversion_asignaciones_efecto. Hallazgo nuevo, no previsto en D-080:
--      sus dos FK son simples, contra hecho_efectos(id) y
--      inversiones(entidad_id), de modo que con BYPASSRLS se puede asignar la
--      inversion de otro tenant a un efecto propio. Es la misma clase de
--      defecto que D-147 cerro para efecto_cuentas.
--
--   PATRON. El aprobado en D-147: columnas localizadoras y FK compuestas
--   contra los anchors ya existentes, sin ningun trigger nuevo.
--
--     hecho_entidades
--       + owner_user_id
--       (owner_user_id, hecho_id)  -> hechos_financieros(owner_user_id, id)
--       (owner_user_id, entidad_id) -> entidades(owner_user_id, id)
--       (hecho_id, efecto_id)       -> hecho_efectos(hecho_id, id)  [ya existia]
--
--     inversion_asignaciones_efecto
--       + owner_user_id, + hecho_id
--       (owner_user_id, hecho_id)              -> hechos_financieros(owner_user_id, id)
--       (hecho_id, efecto_inversion_id)        -> hecho_efectos(hecho_id, id)
--       (owner_user_id, inversion_entidad_id)  -> entidades(owner_user_id, id)
--
--   La cadena encadena entidad.owner = owner = hecho.owner y ata el efecto a
--   su hecho. Cumple D-100: la integridad es de PostgreSQL, no de RLS.
--
--   FK SIMPLES PREEXISTENTES. Se CONSERVAN. Dos motivos. En
--   hecho_entidades, (hecho_id, efecto_id) no se enforce cuando efecto_id es
--   NULL (MATCH SIMPLE), que es justo la relacion a nivel de hecho, asi que la
--   FK simple al hecho sigue siendo la unica garantia en ese caso. En
--   inversion_asignaciones_efecto, la FK a inversiones(entidad_id) no es
--   redundante: el anchor de entidades prueba el tenant, no que la entidad
--   tenga subtipo de inversion. Retirar FK creadas por la cadena congelada
--   rebajaria ademas el contrato cerrado por F03-01 sin necesidad demostrada.
--
--   owner_user_id NO recibe guard de inmutabilidad. No hace falta: cambiarlo
--   de forma aislada rompe las dos FK compuestas, y cambiarlo de forma
--   coherente exigiria mover tambien hecho y entidad, lo que las FK ya
--   impiden. D-142 se refiere a raices de identidad, no a puentes.
--
--   POLICIES. No se tocan. Las dos tablas conservan su policy derivada por
--   join, que sigue siendo correcta: ahora esta ademas respaldada por FK, de
--   modo que no puede existir una fila cuyo owner_user_id difiera del owner de
--   su hecho. El recuento de policies no varia.
--
--   FORCE RLS Y VALIDACION (D-094/D-095). Anadir una FK validada sobre una
--   tabla con FORCE ROW LEVEL SECURITY hace que el escaneo de validacion se
--   ejecute bajo RLS, y current_setting('gapto.owner_user_id') devuelve cadena
--   vacia en un backend reutilizado, lo que rompe el cast a uuid. Por eso se
--   levanta FORCE, se valida y se restaura dentro de la misma transaccion. Hoy
--   ambas tablas tienen cero filas en los tres entornos, pero la migration
--   debe ser correcta tambien sobre datos, porque la carga V3 vendra despues.
--
--   BACKFILL. owner_user_id y hecho_id se derivan de datos existentes; no se
--   inventa ninguno. Si alguna fila no pudiera resolverse, el precheck aborta
--   antes de tocar nada.
--
--   CONTRATO FISICO. 80 tablas sin cambio. +3 columnas, +5 FK (169 -> 174),
--   +3 indices (281 -> 284). Funciones (25), triggers (48), constraint
--   triggers (31), UNIQUE (41), EXCLUDE (11), policies (82), GRANTs (1019) y
--   vistas (3) NO cambian: esta migration no crea ninguna funcion, ningun
--   trigger ni ningun privilegio, y los GRANT de tabla ya cubren las columnas
--   nuevas.
--
-- Decision: D-147 (deuda) + hallazgo de 0290
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0288$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-02-0288 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    FOR v_n IN SELECT 1 WHERE EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = 'gapto.hecho_entidades'::pg_catalog.regclass
           AND a.attname = 'owner_user_id' AND NOT a.attisdropped)
    LOOP
        v_rep := v_rep || ' hecho_entidades.owner_user_id ya existe;';
    END LOOP;

    FOR v_n IN SELECT 1 WHERE EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = 'gapto.inversion_asignaciones_efecto'::pg_catalog.regclass
           AND a.attname IN ('owner_user_id', 'hecho_id') AND NOT a.attisdropped)
    LOOP
        v_rep := v_rep || ' inversion_asignaciones_efecto ya tiene columnas localizadoras;';
    END LOOP;

    -- filas que no podrian resolverse: no se inventa ningun owner
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.hecho_entidades he
      LEFT JOIN gapto.hechos_financieros h ON h.id = he.hecho_id
     WHERE h.id IS NULL;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' hecho_entidades sin hecho resoluble=%s;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.inversion_asignaciones_efecto a
      LEFT JOIN gapto.hecho_efectos e ON e.id = a.efecto_inversion_id
      LEFT JOIN gapto.hechos_financieros h ON h.id = e.hecho_id
     WHERE e.id IS NULL OR h.id IS NULL;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' inversion_asignaciones_efecto sin efecto/hecho resoluble=%s;', v_n);
    END IF;

    -- cross-tenant preexistente: no se repara automaticamente, se bloquea
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.hecho_entidades he
      JOIN gapto.hechos_financieros h ON h.id = he.hecho_id
      JOIN gapto.entidades e ON e.id = he.entidad_id
     WHERE e.owner_user_id IS DISTINCT FROM h.owner_user_id;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' hecho_entidades cross-tenant=%s;', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.inversion_asignaciones_efecto a
      JOIN gapto.hecho_efectos ef ON ef.id = a.efecto_inversion_id
      JOIN gapto.hechos_financieros h ON h.id = ef.hecho_id
      JOIN gapto.entidades e ON e.id = a.inversion_entidad_id
     WHERE e.owner_user_id IS DISTINCT FROM h.owner_user_id;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' inversion_asignaciones_efecto cross-tenant=%s;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-02-0288 PRECHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-02-0288 PRECHECK: OK';
END;
$precheck_0288$;

SET ROLE gapto_owner;

-- ============================================================
-- 1) hecho_entidades
-- ============================================================
ALTER TABLE gapto.hecho_entidades ADD COLUMN owner_user_id uuid;

UPDATE gapto.hecho_entidades he
   SET owner_user_id = h.owner_user_id
  FROM gapto.hechos_financieros h
 WHERE h.id = he.hecho_id;

ALTER TABLE gapto.hecho_entidades ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE gapto.hecho_entidades NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.hecho_entidades
    ADD CONSTRAINT fk_hecho_entidades__owner_hecho
    FOREIGN KEY (owner_user_id, hecho_id)
    REFERENCES gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.hecho_entidades
    ADD CONSTRAINT fk_hecho_entidades__owner_entidad
    FOREIGN KEY (owner_user_id, entidad_id)
    REFERENCES gapto.entidades(owner_user_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.hecho_entidades FORCE ROW LEVEL SECURITY;

CREATE INDEX ix_hecho_entidades__owner_entidad
    ON gapto.hecho_entidades (owner_user_id, entidad_id);

-- ============================================================
-- 2) inversion_asignaciones_efecto
-- ============================================================
ALTER TABLE gapto.inversion_asignaciones_efecto ADD COLUMN owner_user_id uuid;
ALTER TABLE gapto.inversion_asignaciones_efecto ADD COLUMN hecho_id uuid;

UPDATE gapto.inversion_asignaciones_efecto a
   SET owner_user_id = h.owner_user_id,
       hecho_id = h.id
  FROM gapto.hecho_efectos e
  JOIN gapto.hechos_financieros h ON h.id = e.hecho_id
 WHERE e.id = a.efecto_inversion_id;

ALTER TABLE gapto.inversion_asignaciones_efecto ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE gapto.inversion_asignaciones_efecto ALTER COLUMN hecho_id SET NOT NULL;

ALTER TABLE gapto.inversion_asignaciones_efecto NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.inversion_asignaciones_efecto
    ADD CONSTRAINT fk_inversion_asignaciones_efecto__owner_hecho
    FOREIGN KEY (owner_user_id, hecho_id)
    REFERENCES gapto.hechos_financieros(owner_user_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.inversion_asignaciones_efecto
    ADD CONSTRAINT fk_inversion_asignaciones_efecto__hecho_efecto
    FOREIGN KEY (hecho_id, efecto_inversion_id)
    REFERENCES gapto.hecho_efectos(hecho_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.inversion_asignaciones_efecto
    ADD CONSTRAINT fk_inversion_asignaciones_efecto__owner_inversion
    FOREIGN KEY (owner_user_id, inversion_entidad_id)
    REFERENCES gapto.entidades(owner_user_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.inversion_asignaciones_efecto FORCE ROW LEVEL SECURITY;

CREATE INDEX ix_inversion_asignaciones_efecto__owner_inversion
    ON gapto.inversion_asignaciones_efecto (owner_user_id, inversion_entidad_id);

CREATE INDEX ix_inversion_asignaciones_efecto__hecho_efecto
    ON gapto.inversion_asignaciones_efecto (hecho_id, efecto_inversion_id);

RESET ROLE;

DO $postcheck_0288$
DECLARE
    v_n   bigint;
    v_txt text;
BEGIN
    FOR v_txt, v_n IN
        SELECT t.tabla, pg_catalog.count(*)
          FROM (VALUES ('hecho_entidades'), ('inversion_asignaciones_efecto')) AS t(tabla)
          JOIN pg_catalog.pg_class c ON c.relname = t.tabla
           AND c.relnamespace = 'gapto'::pg_catalog.regnamespace
          JOIN pg_catalog.pg_constraint k ON k.conrelid = c.oid
         WHERE k.contype = 'f' AND k.confdeltype = 'r' AND k.convalidated
           AND pg_catalog.array_length(k.conkey, 1) = 2
         GROUP BY t.tabla
    LOOP
        IF (v_txt = 'hecho_entidades' AND v_n <> 3)
           OR (v_txt = 'inversion_asignaciones_efecto' AND v_n <> 3) THEN
            RAISE EXCEPTION 'F03-02-0288 POSTCHECK: % tiene % FK compuestas validadas (esperadas 3)', v_txt, v_n;
        END IF;
    END LOOP;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relname IN ('hecho_entidades', 'inversion_asignaciones_efecto')
       AND c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 2 THEN
        RAISE EXCEPTION 'F03-02-0288 POSTCHECK: FORCE ROW LEVEL SECURITY no restaurado (tablas correctas=%)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
     WHERE a.attrelid IN ('gapto.hecho_entidades'::pg_catalog.regclass,
                          'gapto.inversion_asignaciones_efecto'::pg_catalog.regclass)
       AND a.attname IN ('owner_user_id', 'hecho_id')
       AND a.attnotnull AND NOT a.attisdropped;
    IF v_n <> 4 THEN
        RAISE EXCEPTION 'F03-02-0288 POSTCHECK: columnas localizadoras NOT NULL = % (esperadas 4)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
     WHERE t.tgrelid IN ('gapto.hecho_entidades'::pg_catalog.regclass,
                         'gapto.inversion_asignaciones_efecto'::pg_catalog.regclass)
       AND NOT t.tgisinternal;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-02-0288 POSTCHECK: triggers no internos = % (esperado 1: la suma de inversion)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 174 THEN
        RAISE EXCEPTION 'F03-02-0288 POSTCHECK: FK del esquema = % (esperadas 174)', v_n;
    END IF;

    RAISE NOTICE 'F03-02-0288 POSTCHECK: OK';
END;
$postcheck_0288$;

COMMIT;
