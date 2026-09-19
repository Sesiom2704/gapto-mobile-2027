-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0320_f03_04_delete_correccion_agregada.sql
-- Ruta: migrations/0320_f03_04_delete_correccion_agregada.sql
-- Descripcion: FASE 03 REABIERTA / D-182 + D-183 + D-186 + D-187. Bloque 1 de la
--   reapertura. Devuelve a gapto_runtime el privilegio DELETE sobre las DOCE
--   tablas hijas o puente SIN LIFECYCLE PROPIO que la correccion agregada de
--   F04-06 necesita para retirar una fila que NUNCA DEBIO EXISTIR.
--
--   ORIGEN. B18 (migration 0200) revoco DELETE sobre 17 tablas de realidad
--   financiera y dejo anotado en su cabecera, como CONSECUENCIA OPERATIVA
--   CONOCIDA, que "eliminar un vinculo sobrante deja de serlo". F04-06 ha
--   demostrado el caso funcional legitimo que aquella nota preveia: un hijo o
--   puente capturado por error no tiene sustituto ni lifecycle, y su unica
--   correccion honesta es retirarlo. INV-07 prohibe resolverlo con un hecho
--   compensatorio ficticio, una devolucion inventada, una reversion inventada
--   o un cambio de significado de la fila.
--
--   LO QUE ESTA MIGRATION NO HACE. No crea columnas, constraints, indices,
--   policies, funciones ni triggers. No toca RLS. No modifica 0001..0310. No
--   crea una API de borrado: concede capacidad fisica minima. El contrato de
--   consumo (operacion explicita, atomica, auditada, con motivo obligatorio,
--   locks de raiz, optimistic locking, snapshot antes/despues y revalidacion
--   del estado final) pertenece a F04-06 y a D-186 §4, no al DDL.
--
--   RAICES EXCLUIDAS (D-183). hechos_financieros y movimientos_tesoreria NO
--   recuperan hard-delete: disponen de ACTIVO/ANULADO y esa es la via. D-186
--   §1 fija ademas que OP-03 ("anular hecho que nunca debio existir") ya
--   cubre la raiz creada por error, de modo que no falta ninguna capacidad y
--   no hay tercer bloque.
--
--   TAMPOCO SE AMPLIA POR SIMETRIA. Siguen sin DELETE las otras cinco tablas
--   del Bucket A de B18 (cierres_mensuales, financiacion_cuotas,
--   inversion_valoraciones, propiedad_valoraciones son snapshots o calendarios
--   historicos, D-043/D-044/D-045/D-046), todo el versionado y las identidades
--   de B21 (migration 0230) y las siete append-only. documento_vinculos NO
--   recibe GRANT: el preflight de D-186 confirmo que ya tiene DELETE desde
--   0130 y un GRANT redundante solo ensuciaria la huella h7.
--   prevision_hechos queda fuera por F04-D021.
--
--   POR QUE EL DELETE ES SEGURO EN ESTAS DOCE. Auditadas una a una contra el
--   catalogo fisico de 0310 en Neon y Supabase:
--
--   (a) Invariantes agregadas ya cubiertas en DELETE. efecto_atribuciones,
--       hecho_entidades, hecho_movimientos_tesoreria e
--       inversion_asignaciones_efecto tienen constraint trigger que dispara en
--       DELETE. Su validador relee el padre y, cuando el padre ya no existe,
--       hace CONTINUE en lugar de fallar, porque la rama de VISIBILIDAD solo
--       se activa para el identificador NUEVO y en DELETE ese identificador es
--       NULL. Retirar una atribucion de un efecto COMPLETA sigue siendo
--       rechazado; retirar la fila principal de un efecto con asignaciones
--       vivas sigue siendo rechazado por D-080. Fail-closed conservado.
--
--   (b) Invariantes monotonas a la baja. Las que no disparan en DELETE son de
--       la forma abs(suma) <= abs(referencia): borrar solo puede REDUCIR la
--       suma y nunca crear una violacion nueva. D-171 §6 ya razono y aprobo
--       exactamente esto para hecho_aportaciones_pago. Lo mismo aplica a la
--       aciclicidad de hecho_relaciones: retirar una arista no puede crear un
--       ciclo.
--
--   (c) Sin invariante agregada. hecho_participantes, hecho_terceros,
--       hecho_magnitudes y efecto_cuentas no tienen ningun trigger; su unica
--       proteccion es UNIQUE local, que un DELETE no puede violar.
--
--   NO SE EXTIENDE NINGUN TRIGGER A DELETE. fn_check_aportaciones_conciliacion
--   y fn_check_transferencia_estructura referencian NEW de forma
--   incondicional: hoy es inocuo porque solo estan declarados en INSERT/UPDATE,
--   pero anadirles DELETE abortaria con "record new is not assigned yet". Se
--   deja escrito para que nadie lo intente por simetria en un bloque futuro.
--
--   ORDEN DE RETIRADA IMPUESTO POR LAS FK. Todas las FK entrantes son
--   ON DELETE RESTRICT y siguen intactas. En consecuencia F04-06 debe retirar
--   primero las hijas:
--       efecto_atribuciones / efecto_cuentas / hecho_entidades /
--       inversion_asignaciones_efecto   ANTES de   hecho_efectos
--       hecho_aportaciones_pago         ANTES de   hecho_movimientos_tesoreria
--   Un orden incorrecto produce 23503 y no un estado invalido. La FK es la
--   barrera, no una recomendacion.
--
--   RIESGOS QUE EL DDL NO RESUELVE Y QUEDAN EN EL SERVICIO (D-186 §4):
--     1. Retirar TODOS los efectos de un hecho lo convierte en economicamente
--        neutro sin que ninguna invariante fisica lo impida. RESUELTO por
--        D-187 DEC-11 como guarda SRV/API, SIN constraint fisico: al final de
--        una correccion agregada, un hecho ACTIVO de tipo distinto de
--        TRANSFERENCIA no puede quedar con cero filas en hecho_efectos. Se
--        admite el vacio TRANSITORIO dentro de la misma transaccion mientras
--        se sustituye el efecto. Si no hay reemplazo porque la raiz nunca
--        debio existir, la via es OP-03 (ANULADO), no dejar el hecho vacio.
--        Nunca se cambia automaticamente tipo_hecho para validar la
--        correccion, y cero efectos NO permite inferir TRANSFERENCIA.
--        Codigo estable: CORRECCION_DEJA_HECHO_SIN_EFECTOS. Vive en F04-06.
--     2. transferencias no tiene owner_user_id ni row_version, su USING de RLS
--        deriva solo de la pata de SALIDA y su trigger no cubre DELETE.
--        Borrar la fila deja dos movimientos ACTIVOS desemparejados. La unica
--        proteccion es la atomicidad del agregado.
--     3. El motivo obligatorio no es materializable aqui: auditoria.motivo es
--        nullable y hacerlo NOT NULL exigiria tocar una tabla del tramo
--        inmutable y afectaria a todas las acciones, no solo a ELIMINAR.
--        D-186 §4 lo confirma como garantia SRV/API.
--   auditoria SI admite ya la accion: ck_auditoria__accion incluye 'ELIMINAR'
--   y fn_registrar_auditoria acepta p_datos_despues NULL. No hace falta
--   cambio fisico para auditar un borrado.
--
--   D-150. Los GRANT se emiten bajo SET ROLE gapto_owner: PostgreSQL no
--   aborta cuando el grantor carece de grant option, solo advierte y no
--   concede nada. El postcheck verifica el ACL esperado COMPLETO de las doce,
--   no una ausencia parcial.
--
--   IMPACTO FISICO ESPERADO. Matriz de gapto_runtime 80/74/68/36 -> 80/74/68/48.
--   GRANTs del schema 1019 -> 1031. Columnas, constraints, indices, policies,
--   triggers, funciones y vistas NO se mueven: de las ocho huellas D-111 solo
--   puede cambiar h7. Cualquier movimiento en h1..h6 u h8 tras aplicar 0320
--   es drift y obliga a STOP.
--
--   D-179. Esta migration NO se aplica persistentemente a Supabase durante la
--   reapertura (D-186 §5). Supabase permanece en 0310 y el gate se cierra con
--   waiver explicito.
-- Versión: 0.1.2  -- el precheck exigia pg_has_role(...,'USAGE') sobre gapto_owner.
--                   Es FALSO por diseno en los entornos reales: las pertenencias
--                   se conceden con INHERIT FALSE / SET TRUE para que nadie
--                   herede los privilegios del propietario. El modo correcto es
--                   'SET'. Detectado en P5 por el propio precheck, que abortó la
--                   transaccion en Neon sin conceder nada: fail-closed. La
--                   replica local no lo vio porque se aplicaba como superusuario,
--                   para quien pg_has_role es siempre cierto; desde ahora se
--                   aplica con un rol no superusuario equivalente al real.
-- Versión: 0.1.1  -- el postcheck de columnas contaba solo relkind='r' (728) en vez
--                   de la definicion canonica de la huella h1 de D-111,
--                   relkind IN ('r','v','p') (772). Detectado en P1 sobre replica
--                   local antes de aplicar nada: el postcheck habria abortado
--                   siempre y revertido el GRANT. Los valores esperados NO cambian.
--                   v0.1.0: redaccion inicial.
-- ============================================================

BEGIN;

DO $precheck_0320$
DECLARE
    v_n bigint;
    v_rep text := '';
BEGIN
    -- El grantor debe poder ASUMIR gapto_owner: sin eso el GRANT no falla,
    -- simplemente no concede (D-150).
    -- El modo correcto es 'SET', no 'USAGE'. El modelo de roles concede las
    -- pertenencias con INHERIT FALSE / SET TRUE justamente para que nadie
    -- HEREDE los privilegios de gapto_owner: 'USAGE' pregunta por herencia y
    -- es FALSO por diseno para neondb_owner y para el rol equivalente de
    -- Supabase. Lo que esta migration necesita es poder asumirlo.
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F03-04-0320 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname = 'gapto_runtime') THEN
        RAISE EXCEPTION 'F03-04-0320 PRECHECK: no existe el rol gapto_runtime';
    END IF;

    -- Estado de partida exacto: 0310 aplicado y ninguna de las doce con DELETE.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE'
       AND c.relname = ANY (ARRAY[
            'hecho_efectos','efecto_atribuciones','hecho_aportaciones_pago',
            'hecho_movimientos_tesoreria','inversion_asignaciones_efecto',
            'efecto_cuentas','hecho_entidades','hecho_participantes',
            'hecho_terceros','hecho_magnitudes','hecho_relaciones','transferencias']);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s de las doce candidatas ya tienen DELETE (esperadas 0);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 36 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 36 antes de 0320);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28: 0320 exige head 0310);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58: 0320 exige head 0310);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-04-0320 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-04-0320 PRECHECK: OK';
END;
$precheck_0320$;

-- El grantor debe ser el propietario de las tablas (D-150).
SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 1) Nucleo de hechos: efecto economico y atribucion
-- ------------------------------------------------------------
-- Un efecto o una atribucion capturados por error no tienen estado propio.
-- La atribucion esta cubierta en DELETE por trg_efecto_atribuciones__suma,
-- que sigue rechazando romper un efecto COMPLETA. El efecto solo puede
-- retirarse cuando ya no tiene hijas: cinco FK RESTRICT lo garantizan.
GRANT DELETE ON gapto.hecho_efectos                 TO gapto_runtime;
GRANT DELETE ON gapto.efecto_atribuciones           TO gapto_runtime;

-- ------------------------------------------------------------
-- 2) Conciliacion: financiacion real y respaldo de tesoreria
-- ------------------------------------------------------------
-- D-171 §6 ya declaro que borrar una aportacion solo puede BAJAR la suma
-- vinculada y nunca viola la invariante agregada de 0310. La conciliacion
-- conserva trg_hecho_movimientos_tesoreria__suma, que si dispara en DELETE y
-- revalida el movimiento.
GRANT DELETE ON gapto.hecho_aportaciones_pago       TO gapto_runtime;
GRANT DELETE ON gapto.hecho_movimientos_tesoreria   TO gapto_runtime;

-- ------------------------------------------------------------
-- 3) Reparto de inversion y cuenta generadora
-- ------------------------------------------------------------
-- trg_inversion_asignaciones_efecto__suma dispara en DELETE, toma el advisory
-- (INVERSIONES, owner) desde OLD.owner_user_id y revalida. D-080 no se rompe:
-- menos asignaciones exigen menos, nunca mas. efecto_cuentas no tiene ningun
-- trigger; retirar la fila retira la afirmacion "esta cuenta genero el
-- efecto", que es justo lo que corrige un error de captura (D-146/D-148).
GRANT DELETE ON gapto.inversion_asignaciones_efecto TO gapto_runtime;
GRANT DELETE ON gapto.efecto_cuentas                TO gapto_runtime;

-- ------------------------------------------------------------
-- 4) Vinculos y atributos del hecho
-- ------------------------------------------------------------
-- Es literalmente la CONSECUENCIA OPERATIVA CONOCIDA que 0200 dejo anotada.
-- hecho_entidades conserva el trigger D-080 en DELETE y sigue rechazando
-- retirar la principal con asignaciones vivas. Las otras tres solo tienen
-- UNIQUE local. hecho_relaciones no dispara en DELETE porque retirar una
-- arista no puede crear un ciclo.
GRANT DELETE ON gapto.hecho_entidades               TO gapto_runtime;
GRANT DELETE ON gapto.hecho_participantes           TO gapto_runtime;
GRANT DELETE ON gapto.hecho_terceros                TO gapto_runtime;
GRANT DELETE ON gapto.hecho_magnitudes              TO gapto_runtime;
GRANT DELETE ON gapto.hecho_relaciones              TO gapto_runtime;

-- ------------------------------------------------------------
-- 5) Emparejamiento de transferencia
-- ------------------------------------------------------------
-- Caso de mayor riesgo residual del bloque, concedido con reserva expresa:
-- retirar la fila deja las dos patas ACTIVAS y desemparejadas, y ninguna
-- constraint lo impide. La proteccion es integramente la atomicidad del
-- agregado en F04-06. Ver nota 2 de la cabecera.
GRANT DELETE ON gapto.transferencias                TO gapto_runtime;

RESET ROLE;

DO $postcheck_0320$
DECLARE
    v_n   bigint;
    v_rep text := '';
    v_doce text[] := ARRAY[
        'hecho_efectos','efecto_atribuciones','hecho_aportaciones_pago',
        'hecho_movimientos_tesoreria','inversion_asignaciones_efecto',
        'efecto_cuentas','hecho_entidades','hecho_participantes',
        'hecho_terceros','hecho_magnitudes','hecho_relaciones','transferencias'];
    -- Lo que 0320 NO debe haber tocado: las dos raices con lifecycle mas los
    -- cuatro snapshots/calendarios del Bucket A de B18.
    v_intactas text[] := ARRAY[
        'hechos_financieros','movimientos_tesoreria','cierres_mensuales',
        'financiacion_cuotas','inversion_valoraciones','propiedad_valoraciones'];
BEGIN
    -- 1) ACL COMPLETO de las doce: exactamente cuatro privilegios (D-150).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.unnest(v_doce) AS t(relname)
     WHERE (SELECT pg_catalog.count(*)
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
              JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
             WHERE n.nspname = 'gapto' AND c.relname = t.relname
               AND r.rolname = 'gapto_runtime'
               AND acl.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE')) <> 4;
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s de las doce no tienen exactamente SELECT+INSERT+UPDATE+DELETE;', v_n);
    END IF;

    -- 2) Ninguna de las seis excluidas ha ganado DELETE.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND r.rolname = 'gapto_runtime'
       AND acl.privilege_type = 'DELETE' AND c.relname = ANY (v_intactas);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s raiz/snapshot excluida ha ganado DELETE;', v_n);
    END IF;

    -- 3) Matriz efectiva exacta.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 48 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 48);', v_n);
    END IF;

    -- 4) El resto del contrato fisico NO se mueve. 0320 es ACL puro.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     -- relkind IN ('r','v','p'): es la definicion CANONICA de la huella h1 de
     -- D-111 (huellas_d111.sql), que incluye las columnas de las tres vistas.
     -- Contar solo relkind='r' da 728 y NO es el 772 del contrato certificado.
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p')
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 772 THEN
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 772; 0320 no crea ninguna);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        v_rep := v_rep || pg_catalog.format(' FK = %s (esperadas 175);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 285 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 285);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_policies p WHERE p.schemaname = 'gapto';
    IF v_n <> 82 THEN
        v_rep := v_rep || pg_catalog.format(' policies = %s (esperadas 82);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal;
    IF v_n <> 58 THEN
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28);', v_n);
    END IF;

    -- 5) Ningun trigger de las doce ha ganado el evento DELETE. 0320 no toca
    --    triggers, y dos de los validadores vigentes usan NEW incondicional.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND NOT t.tgisinternal
       AND (t.tgtype & 8) = 8
       AND c.relname = ANY (ARRAY['hecho_efectos','hecho_aportaciones_pago',
                                  'hecho_relaciones','transferencias']);
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s trigger(s) han ganado el evento DELETE; 0320 lo prohibe;', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-04-0320 POSTCHECK:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-04-0320 POSTCHECK: OK';
END;
$postcheck_0320$;

COMMIT;
