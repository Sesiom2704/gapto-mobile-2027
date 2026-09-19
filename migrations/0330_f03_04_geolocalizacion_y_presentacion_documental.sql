-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0330_f03_04_geolocalizacion_y_presentacion_documental.sql
-- Ruta: migrations/0330_f03_04_geolocalizacion_y_presentacion_documental.sql
-- Descripcion: FASE 03 REABIERTA / D-182 + D-184 + D-185 + D-186 + D-187. Bloque 2 de
--   la reapertura, fisicamente independiente de 0320: posicion geografica
--   persistente de una propiedad y metadatos de presentacion de fotografias
--   sobre el vinculo documental ya existente.
--
--   D-184 — GEOLOCALIZACION EN propiedades, NO EN direcciones. La direccion
--   conserva semantica postal reutilizable; la coordenada describe la
--   ubicacion operativa del activo y puede existir aunque la direccion postal
--   sea incompleta. No se generaliza la geolocalizacion a otros dominios sin
--   caso funcional real. NO se introduce PostGIS: el requisito aprobado es
--   pin, apertura en mapas y un conjunto pequeno de propiedades, no consultas
--   espaciales, poligonos, radios indexados ni geometrias.
--
--   D-185 — PRESENTACION SOBRE documento_vinculos, SIN TABLA NUEVA. documentos
--   ya admite tipo='FOTO' y documento_vinculos.entidad_id ya vincula un
--   archivo con una propiedad, porque propiedades es subtipo de entidades. No
--   se crean propiedad_fotos ni propiedad_documentos ni ninguna otra relacion
--   paralela entidad-documento. rol_vinculo conserva intacto su significado
--   documental PRINCIPAL/ANEXO/EVIDENCIA/OTRO y NO se reutiliza como
--   semantica visual: uso_presentacion es ortogonal a el.
--
--   DOS GARANTIAS FISICAS DISTINTAS (D-186 §2). Son independientes y ambas
--   son necesarias:
--     A. una sola PORTADA por entidad
--        -> uq_documento_vinculos__portada_entidad
--     B. una sola aparicion visual de un documento por entidad
--        -> uq_documento_vinculos__presentacion_entidad_documento
--   La garantia B no es redundante con el UNIQUE historico
--   uq_documento_vinculos__entidad, porque aquel incluye rol_vinculo en la
--   clave: sin B, el MISMO documento podria aparecer dos veces en la galeria
--   de la MISMA entidad con roles documentales distintos, e incluso ser a la
--   vez PORTADA y GALERIA. D-186 §2 rechaza expresamente elevar B a un UNIQUE
--   global (entidad_id, documento_id): eso impediria que un documento
--   conserve varios roles documentales legitimos no visuales respecto de la
--   misma entidad. Por eso B es PARCIAL sobre uso_presentacion IS NOT NULL.
--   PORTADA participa ya en la galeria: no hace falta duplicar la fila.
--
--   EL ORDEN NO ES IDENTIDAD. orden_presentacion NO lleva UNIQUE: convertirlo
--   en identidad forzaria renumeraciones en cadena en cada reordenacion y
--   creeria contencion donde hoy no la hay. El read-model usa el orden
--   informado y desempata de forma estable por created_at e id, que no mutan.
--
--   LO QUE NO SE CREA (D-186 §8.D). Sin PostGIS. Sin trigger de geocodificacion.
--   Sin trigger de FOTO/DISPONIBLE. Sin trigger de confirmacion GPS. Sin
--   columna "confirmada".
--
--   TERCER INDICE DE GALERIA: NO (D-187 DEC-7). La lectura de portada la sirve
--   integramente el indice A. La de galeria la sirve B por su prefijo
--   entidad_id, mas una ordenacion en memoria de un conjunto que por diseno es
--   pequeno. Un indice (entidad_id, orden_presentacion, created_at, id) se
--   pagaria en cada INSERT, DELETE y sobre todo en cada REORDENACION, que es la
--   operacion frecuente de esta capacidad, y no se cobraria nunca. No se
--   anticipa un indice por una necesidad no demostrada: si una medicion futura
--   lo justifica, se evaluara entonces. Total objetivo: 287 indices.
--
--   GARANTIAS QUE VIVEN EN SRV/API, NO AQUI (D-186 §3). Quedan escritas para
--   que nadie las suponga fisicas:
--     1. "una geocodificacion automatica no sustituye silenciosamente una
--        coordenada ya persistida". Una coordenada persistida es dato
--        aceptado; sustituirla exige comando explicito. Una geocodificacion
--        automatica puede PROPONER sin persistir.
--     2. "un documento usado como PORTADA o GALERIA debe ser FOTO y estar
--        DISPONIBLE". Es cross-table y ademas documentos.estado_archivo muta
--        despues del vinculo, asi que un CHECK no puede expresarla y un
--        trigger obligaria a cubrir tambien el UPDATE de documentos.
--     3. serializacion de las operaciones de galeria sobre la raiz entidades
--        para evitar dos portadas concurrentes. El indice parcial A es la red
--        final, no el mecanismo primario.
--
--   ROOT DE CONCURRENCIA. Ni propiedades ni documento_vinculos tienen
--   row_version propio. propiedades es subtipo de entidades y documento_vinculos
--   carece de owner_user_id, row_version y updated_at. Por tanto el
--   optimistic locking de AMBAS capacidades se apoya en entidades.row_version
--   (D-186 §3), que el write-path debe recibir, revalidar e incrementar.
--   ASIMETRIA DECLARADA: la raiz de SERIALIZACION es entidades, pero el USING
--   de RLS de documento_vinculos deriva de documentos.owner_user_id; su
--   WITH CHECK si valida ademas el owner del destino. Una operacion de galeria
--   toca las dos raices y debe contar con ello.
--
--   FORCE RLS Y VALIDACION DE CONSTRAINTS (D-094/D-095, D-104). Las dos tablas
--   tienen FORCE ROW LEVEL SECURITY. Se aplica el patron aprobado: levantar
--   FORCE, anadir y validar, restaurar FORCE, TODO DENTRO DE LA MISMA
--   TRANSACCION EXPLICITA. D-104 registro un drift real por un guard que no
--   llego a reactivarse tras un fallo intermedio con autocommit; aqui el
--   COMMIT unico lo hace imposible y el postcheck verifica que force_rls
--   vuelve a 75. Las columnas son nuevas y todas las filas existentes quedan
--   a NULL, de modo que la validacion es trivialmente satisfecha.
--   D-173: ninguna sentencia de esta migration escribe filas, asi que no hay
--   eventos diferidos pendientes y el ALTER TABLE sobre propiedades (que tiene
--   trg_propiedades__subtipo_unico DEFERRABLE INITIALLY DEFERRED) no puede
--   fallar con ObjectInUse.
--
--   MIGRACION V3. V3 no aporta canonicamente coordenadas, portada ni orden de
--   galeria. Las cinco columnas quedan NULL. NO se geocodifican direcciones V3
--   y NO se fabrican fotografias ni ordenes historicos.
--
--   IMPACTO FISICO ESPERADO. Columnas 772 -> 777. CHECK nuevos: 9. Indices
--   285 -> 287. NO se mueven FK (175), UNIQUE constraints (41), EXCLUDE (11),
--   policies (82), triggers (58), funciones (28), vistas (3) ni GRANTs, porque
--   los indices parciales son indices y no constraints y las columnas nuevas
--   heredan el ACL de tabla. De las ocho huellas D-111 cambian h1, h2 y h3;
--   h4..h8 deben quedar identicas.
--
--   D-179. Esta migration NO se aplica persistentemente a Supabase durante la
--   reapertura (D-186 §5). Supabase permanece en 0310.
-- Versión: 0.1.2  -- el precheck exigia pg_has_role(...,'USAGE') sobre gapto_owner.
--                   Es FALSO por diseno en los entornos reales: las pertenencias
--                   se conceden con INHERIT FALSE / SET TRUE para que nadie
--                   herede los privilegios del propietario. El modo correcto es
--                   'SET'. Detectado en P5 por el propio precheck, que abortó la
--                   transaccion en Neon sin conceder nada: fail-closed. La
--                   replica local no lo vio porque se aplicaba como superusuario,
--                   para quien pg_has_role es siempre cierto; desde ahora se
--                   aplica con un rol no superusuario equivalente al real.
-- Versión: 0.1.1  -- mismo defecto que 0320 v0.1.1 en los DOS recuentos de columnas
--                   (precheck 772 y postcheck 777): contaban solo relkind='r'.
--                   Se alinean con la definicion canonica de h1 de D-111.
--                   Los valores esperados NO cambian.
--                   v0.1.0: redaccion inicial.
-- ============================================================

BEGIN;

DO $precheck_0330$
DECLARE
    v_n bigint;
    v_rep text := '';
BEGIN
    -- El modo correcto es 'SET', no 'USAGE'. El modelo de roles concede las
    -- pertenencias con INHERIT FALSE / SET TRUE justamente para que nadie
    -- HEREDE los privilegios de gapto_owner: 'USAGE' pregunta por herencia y
    -- es FALSO por diseno para neondb_owner y para el rol equivalente de
    -- Supabase. Lo que esta migration necesita es poder asumirlo.
    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN
        RAISE EXCEPTION 'F03-04-0330 PRECHECK: el rol % no puede asumir gapto_owner; no se aplica', current_user;
    END IF;

    -- 0330 exige 0320 ya aplicada: los dos bloques son independientes en
    -- contenido pero la cadena es estrictamente ordenada.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 48 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 48: 0330 exige 0320 aplicada);', v_n);
    END IF;

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
        v_rep := v_rep || pg_catalog.format(' columnas = %s (esperadas 772 antes de 0330);', v_n);
    END IF;

    -- Ninguna de las cinco columnas puede existir ya.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND a.attnum > 0 AND NOT a.attisdropped
       AND ((c.relname = 'propiedades'
             AND a.attname IN ('latitud','longitud','geolocalizacion_origen'))
         OR (c.relname = 'documento_vinculos'
             AND a.attname IN ('uso_presentacion','orden_presentacion')));
    IF v_n <> 0 THEN
        v_rep := v_rep || pg_catalog.format(' %s columna(s) de 0330 ya existen;', v_n);
    END IF;

    -- El UNIQUE historico debe seguir ahi: es la razon por la que la garantia B
    -- es necesaria y parcial.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_indexes i
     WHERE i.schemaname = 'gapto' AND i.indexname = 'uq_documento_vinculos__entidad';
    IF v_n <> 1 THEN
        v_rep := v_rep || ' falta uq_documento_vinculos__entidad; 0330 razona sobre el;';
    END IF;

    -- Las dos tablas deben estar en FORCE RLS antes de levantarlo.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relname IN ('propiedades','documento_vinculos')
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 2 THEN
        v_rep := v_rep || pg_catalog.format(' tablas destino con FORCE RLS = %s (esperadas 2);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-04-0330 PRECHECK: estado de partida inesperado:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-04-0330 PRECHECK: OK';
END;
$precheck_0330$;

SET ROLE gapto_owner;

-- ============================================================
-- 1) propiedades — geolocalizacion (D-184)
-- ============================================================
ALTER TABLE gapto.propiedades NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.propiedades
    ADD COLUMN latitud                 numeric(9,6),
    ADD COLUMN longitud                numeric(9,6),
    ADD COLUMN geolocalizacion_origen  varchar(20);

-- Un punto es un par o no es nada. Media coordenada no es un dato parcial
-- util: es un dato falso (D-052, desconocido = NULL).
ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__coordenadas_pareja
    CHECK ((latitud IS NULL) = (longitud IS NULL));

ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__latitud_rango
    CHECK (latitud IS NULL OR (latitud >= -90 AND latitud <= 90));

ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__longitud_rango
    CHECK (longitud IS NULL OR (longitud >= -180 AND longitud <= 180));

-- Codigo cerrado por varchar + CHECK (D-050). No se inventan origenes.
ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__geolocalizacion_origen
    CHECK (geolocalizacion_origen IS NULL
           OR geolocalizacion_origen IN ('MANUAL','GEOCODIFICADA','GPS','IMPORTADA'));

-- Una coordenada sin procedencia no es trazable, y una procedencia sin
-- coordenada no describe nada. Se apoya en latitud porque la pareja ya esta
-- garantizada por ck_propiedades__coordenadas_pareja.
ALTER TABLE gapto.propiedades
    ADD CONSTRAINT ck_propiedades__geolocalizacion_origen_coherente
    CHECK ((latitud IS NULL     AND geolocalizacion_origen IS NULL)
        OR (latitud IS NOT NULL AND geolocalizacion_origen IS NOT NULL));

ALTER TABLE gapto.propiedades FORCE ROW LEVEL SECURITY;

COMMENT ON COLUMN gapto.propiedades.latitud IS
    'D-184: latitud WGS84 de la posicion fisica del activo. NULL = desconocida. No se deriva de la direccion postal.';
COMMENT ON COLUMN gapto.propiedades.longitud IS
    'D-184: longitud WGS84 de la posicion fisica del activo. NULL = desconocida.';
COMMENT ON COLUMN gapto.propiedades.geolocalizacion_origen IS
    'D-184: procedencia de la coordenada persistida (MANUAL/GEOCODIFICADA/GPS/IMPORTADA). Sustituir una coordenada ya persistida exige comando explicito: garantia SRV/API, no fisica (D-186 §3).';

-- ============================================================
-- 2) documento_vinculos — presentacion documental (D-185)
-- ============================================================
ALTER TABLE gapto.documento_vinculos NO FORCE ROW LEVEL SECURITY;

ALTER TABLE gapto.documento_vinculos
    ADD COLUMN uso_presentacion   varchar(20),
    ADD COLUMN orden_presentacion smallint;

ALTER TABLE gapto.documento_vinculos
    ADD CONSTRAINT ck_documento_vinculos__uso_presentacion
    CHECK (uso_presentacion IS NULL OR uso_presentacion IN ('PORTADA','GALERIA'));

-- D-185: la presentacion visual solo tiene sentido contra una entidad. El
-- destino es exclusivo por ck_documento_vinculos__un_solo_destino, asi que
-- exigir entidad_id excluye hecho, tercero y cuenta sin nombrarlos.
ALTER TABLE gapto.documento_vinculos
    ADD CONSTRAINT ck_documento_vinculos__presentacion_solo_entidad
    CHECK (uso_presentacion IS NULL OR entidad_id IS NOT NULL);

ALTER TABLE gapto.documento_vinculos
    ADD CONSTRAINT ck_documento_vinculos__orden_presentacion
    CHECK (orden_presentacion IS NULL OR orden_presentacion > 0);

-- Un orden sin uso visual seria un dato huerfano que ningun read-model leeria.
ALTER TABLE gapto.documento_vinculos
    ADD CONSTRAINT ck_documento_vinculos__orden_exige_presentacion
    CHECK (orden_presentacion IS NULL OR uso_presentacion IS NOT NULL);

ALTER TABLE gapto.documento_vinculos FORCE ROW LEVEL SECURITY;

-- GARANTIA A: una sola PORTADA por entidad.
CREATE UNIQUE INDEX uq_documento_vinculos__portada_entidad
    ON gapto.documento_vinculos (entidad_id)
    WHERE uso_presentacion = 'PORTADA';

-- GARANTIA B: una sola aparicion visual de un documento por entidad. Parcial
-- a proposito: fuera de la presentacion, el mismo documento conserva varios
-- roles documentales legitimos frente a la misma entidad (D-186 §2).
CREATE UNIQUE INDEX uq_documento_vinculos__presentacion_entidad_documento
    ON gapto.documento_vinculos (entidad_id, documento_id)
    WHERE uso_presentacion IS NOT NULL;

COMMENT ON COLUMN gapto.documento_vinculos.uso_presentacion IS
    'D-185: uso visual del vinculo (PORTADA/GALERIA). Ortogonal a rol_vinculo, que conserva su significado documental. Solo admisible con destino entidad_id. Que el documento sea FOTO y este DISPONIBLE es garantia SRV/API (D-186 §3).';
COMMENT ON COLUMN gapto.documento_vinculos.orden_presentacion IS
    'D-185: orden de galeria. No es identidad y no lleva UNIQUE; el read-model desempata de forma estable por created_at e id.';

RESET ROLE;

DO $postcheck_0330$
DECLARE
    v_n   bigint;
    v_rep text := '';
BEGIN
    -- 1) Las cinco columnas, con su tipo exacto y nullable.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND a.attnum > 0 AND NOT a.attisdropped AND NOT a.attnotnull
       AND ((c.relname = 'propiedades' AND a.attname = 'latitud'
             AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'numeric(9,6)')
         OR (c.relname = 'propiedades' AND a.attname = 'longitud'
             AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'numeric(9,6)')
         OR (c.relname = 'propiedades' AND a.attname = 'geolocalizacion_origen'
             AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'character varying(20)')
         OR (c.relname = 'documento_vinculos' AND a.attname = 'uso_presentacion'
             AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'character varying(20)')
         OR (c.relname = 'documento_vinculos' AND a.attname = 'orden_presentacion'
             AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'smallint'));
    IF v_n <> 5 THEN
        v_rep := v_rep || pg_catalog.format(' columnas de 0330 con tipo/nulabilidad correctos = %s (esperadas 5);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_attribute a
      JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
     -- relkind IN ('r','v','p'): es la definicion CANONICA de la huella h1 de
     -- D-111 (huellas_d111.sql), que incluye las columnas de las tres vistas.
     -- Contar solo relkind='r' da 728 y NO es el 772 del contrato certificado.
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND c.relkind IN ('r','v','p')
       AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_n <> 777 THEN
        v_rep := v_rep || pg_catalog.format(' columnas del schema = %s (esperadas 777);', v_n);
    END IF;

    -- 2) Los nueve CHECK, todos VALIDADOS. Un NOT VALID silencioso dejaria la
    --    invariante como decorativa.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND k.contype = 'c' AND k.convalidated
       AND k.conname IN ('ck_propiedades__coordenadas_pareja',
                         'ck_propiedades__latitud_rango',
                         'ck_propiedades__longitud_rango',
                         'ck_propiedades__geolocalizacion_origen',
                         'ck_propiedades__geolocalizacion_origen_coherente',
                         'ck_documento_vinculos__uso_presentacion',
                         'ck_documento_vinculos__presentacion_solo_entidad',
                         'ck_documento_vinculos__orden_presentacion',
                         'ck_documento_vinculos__orden_exige_presentacion');
    IF v_n <> 9 THEN
        v_rep := v_rep || pg_catalog.format(' CHECK de 0330 validados = %s (esperados 9);', v_n);
    END IF;

    -- 3) Los dos indices, UNICOS y PARCIALES. Si alguno perdiese el predicado
    --    parcial romperia casos legitimos en silencio.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_index i
      JOIN pg_catalog.pg_class ci ON ci.oid = i.indexrelid
     WHERE ci.relnamespace = 'gapto'::pg_catalog.regnamespace
       AND i.indisunique AND i.indpred IS NOT NULL
       AND ci.relname IN ('uq_documento_vinculos__portada_entidad',
                          'uq_documento_vinculos__presentacion_entidad_documento');
    IF v_n <> 2 THEN
        v_rep := v_rep || pg_catalog.format(' indices unicos parciales de 0330 = %s (esperados 2);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n FROM pg_catalog.pg_indexes i WHERE i.schemaname = 'gapto';
    IF v_n <> 287 THEN
        v_rep := v_rep || pg_catalog.format(' indices = %s (esperados 287);', v_n);
    END IF;

    -- 4) FORCE RLS restaurado en las 75 tablas tenant (D-104).
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND c.relkind = 'r'
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_n <> 75 THEN
        v_rep := v_rep || pg_catalog.format(' tablas con FORCE RLS = %s (esperadas 75);', v_n);
    END IF;

    -- 5) Lo que 0330 NO debe mover.
    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'f';
    IF v_n <> 175 THEN
        v_rep := v_rep || pg_catalog.format(' FK = %s (esperadas 175; 0330 no crea ninguna);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'gapto'::pg_catalog.regnamespace AND k.contype = 'u';
    IF v_n <> 41 THEN
        v_rep := v_rep || pg_catalog.format(' UNIQUE constraints = %s (esperadas 41; los indices parciales NO son constraints);', v_n);
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
        v_rep := v_rep || pg_catalog.format(' triggers no internos = %s (esperados 58; 0330 no crea ninguno);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'gapto'::pg_catalog.regnamespace;
    IF v_n <> 28 THEN
        v_rep := v_rep || pg_catalog.format(' funciones = %s (esperadas 28; 0330 no crea ninguna);', v_n);
    END IF;

    SELECT pg_catalog.count(*) INTO v_n
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
      JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'DELETE';
    IF v_n <> 48 THEN
        v_rep := v_rep || pg_catalog.format(' runtime DELETE = %s (esperadas 48; 0330 no toca ACL);', v_n);
    END IF;

    IF v_rep <> '' THEN
        RAISE EXCEPTION 'F03-04-0330 POSTCHECK:%', v_rep;
    END IF;

    RAISE NOTICE 'F03-04-0330 POSTCHECK: OK';
END;
$postcheck_0330$;

COMMIT;
