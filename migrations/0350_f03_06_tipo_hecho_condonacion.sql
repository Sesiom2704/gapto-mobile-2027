-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0350_f03_06_tipo_hecho_condonacion.sql
-- Ruta: migrations/0350_f03_06_tipo_hecho_condonacion.sql
-- Descripcion: FASE 03 REABIERTA PARCIALMENTE / D-201 (F03 §20), requerida
--   por F04-D052. Siembra el arquetipo de hecho CONDONACION en
--   gapto.tipos_hecho. Unico cambio fisico de la reapertura D-201.
--
--   POR QUE UN ARQUETIPO PROPIO. La forma «GENERACION_DERECHO_OBLIGACION +
--   DEUDA negativa + sin movimiento» ya representa pagos de cuotas migradas
--   (Migration V3 §42.1, RV3-D004/D005), asi que la condonacion no puede
--   reutilizarla sin volverla ambigua.
--
--   CONTRATO (literal de D-201):
--     - SOLO DML: una fila en gapto.tipos_hecho
--         id      = 0d216df5-59eb-56c8-998e-7d47953b9351
--                   = uuid5(NAMESPACE_URL, 'gapto2027:tipos_hecho:CONDONACION'),
--                   la misma regla que verifica test_017;
--         codigo  = 'CONDONACION';
--         nombre  = 'Condonacion de derecho u obligacion';
--         enabled = true.
--     - Patron de 0150: BEGIN, SET ROLE gapto_owner, SQL cualificado.
--     - PRECHECK fail-closed: existen EXACTAMENTE los siete codigos de 0150
--       (por codigo y por UUID) y no existe CONDONACION. Reaplicar la
--       migration lo rechaza este precheck, no un ON CONFLICT silencioso.
--     - POSTCHECK: ocho filas; la nueva con su UUID determinista, enabled y
--       nombre exactos; las siete de 0150 intactas.
--
--   LO QUE NO HACE A PROPOSITO. Ningun DDL: ni CHECK, ni triggers, ni
--   funciones, ni GRANT, ni RLS. gapto.tipos_hecho es un catalogo global sin
--   RLS (0120) y gapto_runtime solo tiene SELECT sobre ella (0130), que la fila
--   nueva hereda sin GRANT propio. No hay triggers en la tabla, asi que la
--   insercion no escribe en ninguna otra tabla: ningun hecho existente cambia
--   de tipo_hecho_id y ninguna fila ajena cambia row_version ni updated_at.
--   No se levanta FORCE RLS en ninguna tabla (seria DDL); la preservacion de
--   filas ajenas la prueba test_045 ejecutando este mismo cuerpo dentro de
--   una transaccion revertida sobre datos preexistentes.
--
--   IMPACTO FISICO ESPERADO (hipotesis hasta medir). Ninguna de las ocho
--   huellas D-111 ni de los recuentos estructurales mide filas de catalogo,
--   asi que se espera que h1..h8 y 778/645/287/82/58/28/1031/3 sean
--   identicos a 0340. Se mide y se declara en la evidencia de la Fase A.
--
--   MIGRACION V3. Ningun hecho migrado recibe CONDONACION: P5 no la produce.
--   Datos anteriores y migrados no se reclasifican (F04-D052).
--
--   D-179. No se aplica a Supabase: permanece en 0310.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $precheck_0350$
DECLARE
    v_n        bigint;
    v_esperado CONSTANT text[] := ARRAY[
        'GASTO:b9c7573f-fa72-54a1-8b2d-b1c189f32533',
        'INGRESO:bfdad2e0-2d2e-5850-b73a-1d2ecd8eb4c4',
        'TRANSFERENCIA:7ba5c0c4-ccd9-557c-838a-9122e96634d6',
        'COMPRA_FINANCIADA:7c20e19e-8c62-5df7-b11b-17d15eb4c76c',
        'REEMBOLSO:a4153b30-58b5-50d4-9073-471ea1d6c294',
        'APORTACION_INVERSION:cf006530-280c-587b-994f-e621e680e3ef',
        'GENERACION_DERECHO_OBLIGACION:26ee751e-aa9c-5c3b-a81c-7a28e5a5be34'
    ];
    v_actual   text[];
BEGIN
    -- 'SET', no 'USAGE': las pertenencias son INHERIT FALSE / SET TRUE (D-189).
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F03-06-0350 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.tipos_hecho
     WHERE codigo = 'CONDONACION' OR id = '0d216df5-59eb-56c8-998e-7d47953b9351';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'F03-06-0350 PRECHECK: CONDONACION ya existe en gapto.tipos_hecho (% filas); no se reaplica', v_n;
    END IF;

    SELECT pg_catalog.array_agg(t.codigo::text || ':' || t.id::text ORDER BY t.codigo::text COLLATE "C")
      INTO v_actual
      FROM gapto.tipos_hecho t;
    IF v_actual IS DISTINCT FROM (SELECT pg_catalog.array_agg(e ORDER BY e COLLATE "C") FROM pg_catalog.unnest(v_esperado) e) THEN
        RAISE EXCEPTION 'F03-06-0350 PRECHECK: tipos_hecho no es exactamente el seed de 0150; encontrado=%', v_actual;
    END IF;
END
$precheck_0350$ LANGUAGE plpgsql;

SET ROLE gapto_owner;

INSERT INTO gapto.tipos_hecho (id, codigo, nombre, enabled) VALUES
    ('0d216df5-59eb-56c8-998e-7d47953b9351', 'CONDONACION', 'Condonacion de derecho u obligacion', true);

RESET ROLE;

DO $postcheck_0350$
DECLARE
    v_n bigint;
BEGIN
    SELECT pg_catalog.count(*) INTO v_n FROM gapto.tipos_hecho;
    IF v_n <> 8 THEN
        RAISE EXCEPTION 'F03-06-0350 POSTCHECK: esperadas 8 filas en tipos_hecho; encontradas=%', v_n;
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.tipos_hecho
     WHERE id = '0d216df5-59eb-56c8-998e-7d47953b9351'
       AND codigo = 'CONDONACION'
       AND nombre = 'Condonacion de derecho u obligacion'
       AND enabled;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'F03-06-0350 POSTCHECK: la fila CONDONACION no tiene el contrato de D-201';
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM gapto.tipos_hecho
     WHERE codigo IN ('GASTO', 'INGRESO', 'TRANSFERENCIA', 'COMPRA_FINANCIADA', 'REEMBOLSO',
                      'APORTACION_INVERSION', 'GENERACION_DERECHO_OBLIGACION')
       AND enabled;
    IF v_n <> 7 THEN
        RAISE EXCEPTION 'F03-06-0350 POSTCHECK: los siete arquetipos de 0150 no estan intactos (% habilitados)', v_n;
    END IF;
END
$postcheck_0350$ LANGUAGE plpgsql;

COMMIT;
