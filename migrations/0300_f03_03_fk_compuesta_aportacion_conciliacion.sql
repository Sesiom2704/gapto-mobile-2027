-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0300_f03_03_fk_compuesta_aportacion_conciliacion.sql
-- Ruta: migrations/0300_f03_03_fk_compuesta_aportacion_conciliacion.sql
-- Descripcion: FASE 03 REABIERTA / D-168 + D-169. Corrige forward-only el
--   DEFECTO 1: la FK compuesta de pertenencia hecho<->conciliacion aprobada
--   por D-057 / F03-00-E2-D nunca llego a materializarse.
--
--   DEFECTO. D-057 aprobo expresamente que hecho_movimientos_tesoreria
--   anadiera el anchor (hecho_id, id) y que hecho_aportaciones_pago lo
--   consumiera mediante FK compuesta (hecho_id, hecho_movimiento_tesoreria_id),
--   para impedir que una aportacion se vincule a una conciliacion de otro
--   hecho. 0080 creo el anchor. 0090 creo unicamente la FK SIMPLE
--   fk_hecho_aportaciones_pago__movimiento contra hecho_movimientos_tesoreria(id).
--   La reconstruccion Git de D-168 demuestra que la FK compuesta NO existio
--   nunca en ninguna version del codigo: 0090 tiene un unico commit y jamas
--   fue modificada. No es una regresion, es una omision de origen. Ninguna
--   decision posterior la retiro, sustituyo ni refino.
--
--   POR QUE NO SE DETECTO. El anchor quedo HUERFANO: existia sin consumidor.
--   Los tests de baseline (test_009, test_010) y el criterio G2 del gate
--   validan CARDINALIDADES, no invariantes nombradas, y una FK simple cuenta
--   exactamente igual que una compuesta. La auditoria de 0220 / D-074 buscaba
--   fugas OWNER-scoped: esta columna SI esta cubierta por el WITH CHECK de la
--   policy a nivel de owner, de modo que el filtro, correcto para su propia
--   pregunta, no podia ver un defecto de granularidad HECHO-scoped. 0288
--   endurecio la misma familia pero con alcance declarado a hecho_entidades e
--   inversion_asignaciones_efecto; aportaciones nunca entro en alcance.
--
--   IMPACTO REAL. Con la FK simple, dentro de un mismo tenant es fisicamente
--   aceptable que una aportacion del hecho H1 apunte a una conciliacion del
--   hecho H2. Eso rompe la regla documentada de que la cuenta de la aportacion
--   se obtiene por hecho_movimiento_tesoreria_id -> movimiento_tesoreria_id ->
--   cuenta_id: la financiacion de H1 quedaria anclada a la tesoreria de H2.
--   Bajo BYPASSRLS ni siquiera la barrera de owner aplica. El caso quedo
--   reproducido experimentalmente contra 0290 antes de escribir esta migration.
--
--   CORRECCION. Integridad declarativa pura, sin trigger. A diferencia de 0288,
--   NO hace falta columna localizadora ni backfill: hecho_aportaciones_pago ya
--   tiene hecho_id NOT NULL, y el anchor destino ya existe desde 0080. Es un
--   unico ADD CONSTRAINT.
--
--   FK SIMPLE PREEXISTENTE. Se CONSERVA, siguiendo el precedente explicito de
--   0288: retirar una FK creada por la cadena congelada rebajaria el contrato
--   cerrado por F03-01 sin necesidad demostrada. Ambas son ON DELETE RESTRICT
--   y no se contradicen.
--
--   MATCH SIMPLE. Con hecho_movimiento_tesoreria_id IS NULL la restriccion no
--   se enforce, que es exactamente lo correcto: el vinculo con la conciliacion
--   es opcional por contrato (DB Schema, tabla 39). hecho_id es NOT NULL, de
--   modo que no existe ninguna otra combinacion parcial posible.
--
--   ON DELETE / ON UPDATE. RESTRICT y ausencia de ON UPDATE, conforme a la
--   politica historica de F03-00-E1: el nucleo economico no admite cascada
--   destructiva y las identidades UUID no se actualizan en cascada.
--
--   INDICE (D-169 / S2). F03-00-E1 exige que toda FK disponga de un indice util
--   que comience por sus columnas, salvo cobertura equivalente. Los indices
--   simples existentes (ix_..__hecho y ix_..__movimiento) no representan el
--   prefijo compuesto de la nueva FK, de modo que se anade el indice btree
--   (hecho_id, hecho_movimiento_tesoreria_id). No se espera a tener volumen
--   para cumplir el contrato fisico.
--
--   FORCE RLS Y VALIDACION (D-094/D-095). Las sentencias se ejecutan bajo
--   SET ROLE gapto_owner, que no tiene BYPASSRLS, de modo que el escaneo de
--   validacion de la FK correria bajo RLS y current_setting('gapto.owner_user_id')
--   devuelve cadena vacia en un backend reutilizado, rompiendo el cast a uuid.
--   Por eso se levanta FORCE, se valida y se restaura dentro de la MISMA
--   transaccion, sin dejar ninguna ventana persistente. Hoy la tabla tiene cero
--   filas en los tres entornos, pero la migration debe ser correcta tambien
--   sobre datos porque la carga V3 vendra despues.
--
--   PRECHECK BLOQUEANTE, NUNCA REPARADOR. Si existiera alguna aportacion cuya
--   conciliacion pertenece a otro hecho, el precheck aborta. No se inventa
--   ningun hecho_id ni se desvincula ninguna fila: eso exigiria decision
--   arquitectonica, no una migration.
--
--   CONTRATO FISICO. 80 tablas sin cambio. +1 FK (174 -> 175), +1 indice
--   (284 -> 285). Columnas, UNIQUE, EXCLUDE, funciones, triggers, constraint
--   triggers, policies, vistas y GRANTs NO cambian: esta migration no crea
--   ninguna columna, ninguna funcion, ningun trigger ni ningun privilegio, y
--   los GRANT de tabla ya cubren la constraint nueva. De las ocho huellas
--   D-111 solo deben cambiar h2_constraints y h3_indices.
--
--   ALCANCE. Esta migration corrige EXCLUSIVAMENTE el Defecto 1. La segunda
--   invariante aprobada por D-169 (suma de aportaciones vinculadas <= porcion
--   conciliada en moneda comparable) NO se materializa aqui: queda reservada a
--   0310, cuyo mecanismo fisico requiere aprobacion arquitectonica previa.
--   F03 NO puede recerrarse tras 0300.
--
-- Decision: D-057 (origen) / D-168 (reapertura) / D-169 (autorizacion, S1, S2)
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0300$
DECLARE
    v_bypass boolean;
    v_rep    text := '';
    v_n      bigint;
BEGIN
    SELECT r.rolbypassrls OR r.rolsuper INTO v_bypass
      FROM pg_catalog.pg_roles r WHERE r.rolname = current_user;
    IF NOT coalesce(v_bypass, false) THEN
        RAISE EXCEPTION 'F03-03-0300 PRECHECK: NO CONCLUYENTE, el rol % no tiene BYPASSRLS; no se aplica', current_user;
    END IF;

    -- el anchor destino de D-057 debe existir (0080)
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.hecho_movimientos_tesoreria'::pg_catalog.regclass
       AND k.contype = 'u'
       AND k.conname = 'uq_hecho_movimientos_tesoreria__hecho_anchor';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta el anchor uq_hecho_movimientos_tesoreria__hecho_anchor;';
    END IF;

    -- la FK compuesta no debe existir todavia: 0300 no es idempotente por diseno (D-069)
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::pg_catalog.regclass
       AND k.contype = 'f'
       AND pg_catalog.array_length(k.conkey, 1) = 2;
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' hecho_aportaciones_pago ya tiene %s FK compuesta(s);', v_n);
    END IF;

    -- el indice tampoco
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'ix_hecho_aportaciones_pago__hecho_conciliacion';
    IF v_n <> 0 THEN
        v_rep := v_rep || ' el indice compuesto ya existe;';
    END IF;

    -- baseline de partida: 0290 certificado
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 174 THEN
        v_rep := v_rep || pg_catalog.format(' FK del esquema = %s (esperadas 174 antes de 0300);', v_n);
    END IF;

    -- datos que violarian la pertenencia: se bloquea, no se repara
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.hecho_aportaciones_pago a
      JOIN gapto.hecho_movimientos_tesoreria c ON c.id = a.hecho_movimiento_tesoreria_id
     WHERE c.hecho_id IS DISTINCT FROM a.hecho_id;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' aportaciones con conciliacion de otro hecho=%s;', v_n);
    END IF;

    -- vinculos cuya conciliacion no es resoluble: no se inventa ninguna
    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.hecho_aportaciones_pago a
      LEFT JOIN gapto.hecho_movimientos_tesoreria c ON c.id = a.hecho_movimiento_tesoreria_id
     WHERE a.hecho_movimiento_tesoreria_id IS NOT NULL AND c.id IS NULL;
    IF v_n > 0 THEN
        v_rep := v_rep || pg_catalog.format(' aportaciones con conciliacion no resoluble=%s;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-03-0300 PRECHECK: BLOQUEA -%', v_rep;
    END IF;
    RAISE NOTICE 'F03-03-0300 PRECHECK: OK';
END;
$precheck_0300$;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ============================================================
-- D-057: la aportacion pertenece a una conciliacion DEL MISMO HECHO
-- ============================================================
ALTER TABLE gapto.hecho_aportaciones_pago NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.hecho_aportaciones_pago
    ADD CONSTRAINT fk_hecho_aportaciones_pago__hecho_conciliacion
    FOREIGN KEY (hecho_id, hecho_movimiento_tesoreria_id)
    REFERENCES gapto.hecho_movimientos_tesoreria(hecho_id, id) ON DELETE RESTRICT;

ALTER TABLE gapto.hecho_aportaciones_pago FORCE ROW LEVEL SECURITY;

-- D-169 / S2: indice util que comienza por las columnas de la FK nueva
CREATE INDEX ix_hecho_aportaciones_pago__hecho_conciliacion
    ON gapto.hecho_aportaciones_pago (hecho_id, hecho_movimiento_tesoreria_id);

COMMENT ON CONSTRAINT fk_hecho_aportaciones_pago__hecho_conciliacion
    ON gapto.hecho_aportaciones_pago IS
    'D-057/D-169: una aportacion solo puede vincularse a una conciliacion del mismo hecho. Consume el anchor uq_hecho_movimientos_tesoreria__hecho_anchor creado en 0080.';

RESET ROLE;

DO $postcheck_0300$
DECLARE
    v_n   bigint;
    v_def text;
BEGIN
    -- la FK compuesta existe, esta validada y usa el anchor correcto
    SELECT pg_catalog.pg_get_constraintdef(k.oid) INTO v_def
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::pg_catalog.regclass
       AND k.conname = 'fk_hecho_aportaciones_pago__hecho_conciliacion'
       AND k.contype = 'f' AND k.convalidated AND k.confdeltype = 'r' AND k.confupdtype = 'a';
    IF v_def IS NULL THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: la FK compuesta no existe, no esta validada o no es RESTRICT/NO ACTION';
    END IF;
    IF v_def !~ 'FOREIGN KEY \(hecho_id, hecho_movimiento_tesoreria_id\)'
       OR v_def !~ 'hecho_movimientos_tesoreria\(hecho_id, id\)' THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: definicion inesperada de la FK compuesta: %', v_def;
    END IF;

    -- el anchor deja de estar huerfano
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint f
      JOIN pg_catalog.pg_constraint u ON u.conindid = f.conindid
     WHERE f.contype = 'f' AND u.contype = 'u'
       AND u.conname = 'uq_hecho_movimientos_tesoreria__hecho_anchor';
    IF v_n < 1 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: el anchor sigue sin consumidor';
    END IF;

    -- la FK simple se conserva
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
     WHERE k.conrelid = 'gapto.hecho_aportaciones_pago'::pg_catalog.regclass
       AND k.conname = 'fk_hecho_aportaciones_pago__movimiento' AND k.contype = 'f';
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: la FK simple preexistente ha desaparecido';
    END IF;

    -- FORCE ROW LEVEL SECURITY restaurado
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.oid = 'gapto.hecho_aportaciones_pago'::pg_catalog.regclass
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: FORCE ROW LEVEL SECURITY no restaurado';
    END IF;

    -- indice compuesto presente
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname = 'ix_hecho_aportaciones_pago__hecho_conciliacion' AND c.relkind = 'i';
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: falta el indice compuesto';
    END IF;

    -- contrato fisico: solo FK e indices se mueven
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: FK del esquema = % (esperadas 175)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 285 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: indices del esquema = % (esperados 285)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 54 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: triggers no internos = % (esperados 54: 0300 no crea ninguno)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 26 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: funciones = % (esperadas 26: 0300 no crea ninguna)', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f' AND k.confupdtype = 'c';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-03-0300 POSTCHECK: existen % FK con ON UPDATE CASCADE', v_n;
    END IF;

    RAISE NOTICE 'F03-03-0300 POSTCHECK: OK';
END;
$postcheck_0300$;

COMMIT;
