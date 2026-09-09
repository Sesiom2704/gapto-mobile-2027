-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0010_f03_01_tables_b01_usuario_geografia_terceros.sql
-- Ruta: migrations/0010_f03_01_tables_b01_usuario_geografia_terceros.sql
-- Descripción: Materializa las tablas 1..16 del baseline físico:
--              usuario, geografía, terceros, clasificaciones y categorías.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. PREFLIGHT FAIL-FAST
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_existing_tables text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION
            'F03-01-B01 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT pg_catalog.string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_existing_tables
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind IN ('r', 'p')
       AND c.relname IN (
            'usuarios',
            'configuracion_usuario',
            'preferencias_ui',
            'acciones_rapidas',
            'paises',
            'regiones',
            'localidades',
            'direcciones',
            'terceros',
            'tercero_direcciones',
            'actores_financieros',
            'tercero_roles',
            'clasificaciones_tercero',
            'tercero_clasificaciones',
            'categorias_financieras',
            'tercero_afinidades'
       );

    IF v_existing_tables IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B01 TABLE DRIFT: ya existen tablas reservadas del bloque: %',
            v_existing_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 2. USUARIO Y CONFIGURACIÓN
-- ------------------------------------------------------------
CREATE TABLE gapto.usuarios (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    email varchar(254) NOT NULL,
    nombre varchar(120) NOT NULL,
    timezone varchar(50) NOT NULL DEFAULT 'Europe/Madrid',
    locale varchar(10) NOT NULL DEFAULT 'es-ES',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_usuarios PRIMARY KEY (id),
    CONSTRAINT ck_usuarios__email_no_blanco
        CHECK (email ~ '[^[:space:]]'),
    CONSTRAINT ck_usuarios__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_usuarios__timezone_no_blanco
        CHECK (timezone ~ '[^[:space:]]'),
    CONSTRAINT ck_usuarios__locale_no_blanco
        CHECK (locale ~ '[^[:space:]]')
);

CREATE TABLE gapto.configuracion_usuario (
    owner_user_id uuid NOT NULL,
    moneda_default varchar(3) NOT NULL DEFAULT 'EUR',
    multimoneda_enabled boolean NOT NULL DEFAULT false,
    meses_historico_presupuesto smallint NOT NULL DEFAULT 4,
    metodo_estimacion_default varchar(30),
    dia_inicio_mes_financiero smallint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_configuracion_usuario PRIMARY KEY (owner_user_id),
    CONSTRAINT ck_configuracion_usuario__moneda_default_formato
        CHECK (moneda_default ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_configuracion_usuario__meses_historico_positivo
        CHECK (meses_historico_presupuesto > 0),
    CONSTRAINT ck_configuracion_usuario__metodo_estimacion
        CHECK (
            metodo_estimacion_default IS NULL
            OR metodo_estimacion_default IN (
                'MANUAL',
                'MEDIA_HISTORICA',
                'MEDIANA_HISTORICA',
                'ULTIMO_REAL'
            )
        ),
    CONSTRAINT ck_configuracion_usuario__dia_inicio_mes_financiero
        CHECK (dia_inicio_mes_financiero BETWEEN 1 AND 28)
);

CREATE TABLE gapto.preferencias_ui (
    owner_user_id uuid NOT NULL,
    modo varchar(20) NOT NULL DEFAULT 'SISTEMA',
    densidad varchar(20) NOT NULL DEFAULT 'NORMAL',
    accent_key varchar(30),
    mostrar_centimos boolean NOT NULL DEFAULT true,
    mostrar_importes_atribuibles boolean NOT NULL DEFAULT true,
    home_layout jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_preferencias_ui PRIMARY KEY (owner_user_id),
    CONSTRAINT ck_preferencias_ui__modo
        CHECK (modo IN ('CLARO', 'OSCURO', 'SISTEMA')),
    CONSTRAINT ck_preferencias_ui__densidad
        CHECK (densidad IN ('COMPACTA', 'NORMAL', 'AMPLIA')),
    CONSTRAINT ck_preferencias_ui__accent_key_no_blanco
        CHECK (accent_key IS NULL OR accent_key ~ '[^[:space:]]')
);

CREATE TABLE gapto.acciones_rapidas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(80) NOT NULL,
    plantilla_registro_id uuid NOT NULL,
    orden smallint NOT NULL DEFAULT 0,
    icono_key varchar(50),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_acciones_rapidas PRIMARY KEY (id),
    CONSTRAINT ck_acciones_rapidas__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_acciones_rapidas__orden_no_negativo
        CHECK (orden >= 0),
    CONSTRAINT ck_acciones_rapidas__icono_key_no_blanco
        CHECK (icono_key IS NULL OR icono_key ~ '[^[:space:]]')
);

-- ------------------------------------------------------------
-- 3. GEOGRAFÍA Y DIRECCIONES
-- ------------------------------------------------------------
CREATE TABLE gapto.paises (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    iso2 varchar(2) NOT NULL,
    iso3 varchar(3) NOT NULL,
    nombre varchar(100) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_paises PRIMARY KEY (id),
    CONSTRAINT ck_paises__iso2_formato
        CHECK (iso2 ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_paises__iso3_formato
        CHECK (iso3 ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_paises__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

CREATE TABLE gapto.regiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    pais_id uuid NOT NULL,
    parent_region_id uuid,
    nombre varchar(120) NOT NULL,
    tipo_region varchar(40),
    codigo_oficial varchar(30),
    enabled boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_regiones PRIMARY KEY (id),
    CONSTRAINT ck_regiones__parent_no_self
        CHECK (parent_region_id IS NULL OR parent_region_id <> id),
    CONSTRAINT ck_regiones__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_regiones__tipo_region_formato
        CHECK (
            tipo_region IS NULL
            OR tipo_region ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'
        ),
    CONSTRAINT ck_regiones__codigo_oficial_no_blanco
        CHECK (codigo_oficial IS NULL OR codigo_oficial ~ '[^[:space:]]')
);

CREATE TABLE gapto.localidades (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    region_id uuid NOT NULL,
    nombre varchar(120) NOT NULL,
    codigo_oficial varchar(30),
    codigo_oficial_tipo varchar(30),
    enabled boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_localidades PRIMARY KEY (id),
    CONSTRAINT ck_localidades__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_localidades__codigo_oficial_no_blanco
        CHECK (codigo_oficial IS NULL OR codigo_oficial ~ '[^[:space:]]'),
    CONSTRAINT ck_localidades__codigo_oficial_tipo_formato
        CHECK (
            codigo_oficial_tipo IS NULL
            OR codigo_oficial_tipo ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'
        ),
    CONSTRAINT ck_localidades__tipo_requiere_codigo
        CHECK (codigo_oficial_tipo IS NULL OR codigo_oficial IS NOT NULL)
);

CREATE TABLE gapto.direcciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    localidad_id uuid,
    codigo_postal varchar(20),
    via_tipo varchar(30),
    via_nombre varchar(150),
    numero varchar(20),
    bloque varchar(20),
    escalera varchar(20),
    planta varchar(20),
    puerta varchar(20),
    observaciones text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_direcciones PRIMARY KEY (id),
    CONSTRAINT ck_direcciones__codigo_postal_no_blanco
        CHECK (codigo_postal IS NULL OR codigo_postal ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__via_tipo_no_blanco
        CHECK (via_tipo IS NULL OR via_tipo ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__via_nombre_no_blanco
        CHECK (via_nombre IS NULL OR via_nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__numero_no_blanco
        CHECK (numero IS NULL OR numero ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__bloque_no_blanco
        CHECK (bloque IS NULL OR bloque ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__escalera_no_blanco
        CHECK (escalera IS NULL OR escalera ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__planta_no_blanco
        CHECK (planta IS NULL OR planta ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__puerta_no_blanco
        CHECK (puerta IS NULL OR puerta ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__observaciones_no_blanco
        CHECK (observaciones IS NULL OR observaciones ~ '[^[:space:]]'),
    CONSTRAINT ck_direcciones__contenido_minimo
        CHECK (
            localidad_id IS NOT NULL
            OR codigo_postal IS NOT NULL
            OR via_tipo IS NOT NULL
            OR via_nombre IS NOT NULL
            OR numero IS NOT NULL
            OR bloque IS NOT NULL
            OR escalera IS NOT NULL
            OR planta IS NOT NULL
            OR puerta IS NOT NULL
            OR observaciones IS NOT NULL
        )
);

-- ------------------------------------------------------------
-- 4. TERCEROS, ACTORES Y CLASIFICACIONES
-- ------------------------------------------------------------
CREATE TABLE gapto.terceros (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(160) NOT NULL,
    nombre_legal varchar(200),
    naturaleza varchar(30),
    identificador_fiscal varchar(50),
    tipo_identificador_fiscal varchar(30),
    pais_fiscal_id uuid,
    email varchar(254),
    telefono varchar(40),
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enabled boolean NOT NULL DEFAULT true,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_terceros PRIMARY KEY (id),
    CONSTRAINT ck_terceros__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_terceros__nombre_legal_no_blanco
        CHECK (nombre_legal IS NULL OR nombre_legal ~ '[^[:space:]]'),
    CONSTRAINT ck_terceros__naturaleza
        CHECK (
            naturaleza IS NULL
            OR naturaleza IN ('PERSONA', 'EMPRESA', 'ORGANISMO', 'OTRO')
        ),
    CONSTRAINT ck_terceros__identificador_fiscal_no_blanco
        CHECK (
            identificador_fiscal IS NULL
            OR identificador_fiscal ~ '[^[:space:]]'
        ),
    CONSTRAINT ck_terceros__tipo_identificador_fiscal_formato
        CHECK (
            tipo_identificador_fiscal IS NULL
            OR tipo_identificador_fiscal ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'
        ),
    CONSTRAINT ck_terceros__tipo_fiscal_requiere_identificador
        CHECK (
            tipo_identificador_fiscal IS NULL
            OR identificador_fiscal IS NOT NULL
        ),
    CONSTRAINT ck_terceros__email_no_blanco
        CHECK (email IS NULL OR email ~ '[^[:space:]]'),
    CONSTRAINT ck_terceros__telefono_no_blanco
        CHECK (telefono IS NULL OR telefono ~ '[^[:space:]]'),
    CONSTRAINT ck_terceros__notas_no_blanco
        CHECK (notas IS NULL OR notas ~ '[^[:space:]]')
);

CREATE TABLE gapto.tercero_direcciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    tercero_id uuid NOT NULL,
    direccion_id uuid NOT NULL,
    tipo varchar(30) NOT NULL,
    principal boolean NOT NULL DEFAULT false,

    CONSTRAINT pk_tercero_direcciones PRIMARY KEY (id),
    CONSTRAINT ck_tercero_direcciones__tipo
        CHECK (tipo IN ('FISCAL', 'COMERCIAL', 'PERSONAL', 'OTRO'))
);

CREATE TABLE gapto.actores_financieros (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tercero_id uuid,

    CONSTRAINT pk_actores_financieros PRIMARY KEY (id)
);

CREATE TABLE gapto.tercero_roles (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    tercero_id uuid NOT NULL,
    rol_codigo varchar(50) NOT NULL,

    CONSTRAINT pk_tercero_roles PRIMARY KEY (id),
    CONSTRAINT ck_tercero_roles__rol_codigo
        CHECK (
            rol_codigo IN (
                'COMERCIO',
                'ENTIDAD_FINANCIERA',
                'FINANCIADOR',
                'INQUILINO',
                'AVALISTA',
                'EMPLEADOR',
                'SUMINISTRADOR',
                'OBLIGADO_REEMBOLSO',
                'GESTOR',
                'ASEGURADORA'
            )
        )
);

CREATE TABLE gapto.clasificaciones_tercero (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    parent_id uuid,
    nombre varchar(100) NOT NULL,
    codigo varchar(50),
    orden smallint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enabled boolean NOT NULL DEFAULT true,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_clasificaciones_tercero PRIMARY KEY (id),
    CONSTRAINT ck_clasificaciones_tercero__parent_no_self
        CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT ck_clasificaciones_tercero__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_clasificaciones_tercero__codigo_formato
        CHECK (codigo IS NULL OR codigo ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'),
    CONSTRAINT ck_clasificaciones_tercero__orden_no_negativo
        CHECK (orden >= 0)
);

CREATE TABLE gapto.tercero_clasificaciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    tercero_id uuid NOT NULL,
    clasificacion_id uuid NOT NULL,
    principal boolean NOT NULL DEFAULT false,

    CONSTRAINT pk_tercero_clasificaciones PRIMARY KEY (id)
);

CREATE TABLE gapto.categorias_financieras (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    parent_id uuid,
    nombre varchar(100) NOT NULL,
    codigo varchar(60),
    ambito varchar(20) NOT NULL,
    presupuestable_default boolean NOT NULL,
    orden smallint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enabled boolean NOT NULL DEFAULT true,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_categorias_financieras PRIMARY KEY (id),
    CONSTRAINT ck_categorias_financieras__parent_no_self
        CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT ck_categorias_financieras__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_categorias_financieras__codigo_formato
        CHECK (codigo IS NULL OR codigo ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'),
    CONSTRAINT ck_categorias_financieras__ambito
        CHECK (ambito IN ('GASTO', 'INGRESO', 'AMBOS')),
    CONSTRAINT ck_categorias_financieras__orden_no_negativo
        CHECK (orden >= 0)
);

CREATE TABLE gapto.tercero_afinidades (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    tercero_id uuid NOT NULL,
    categoria_id uuid NOT NULL,
    prioridad_manual smallint,

    CONSTRAINT pk_tercero_afinidades PRIMARY KEY (id),
    CONSTRAINT ck_tercero_afinidades__prioridad_no_negativa
        CHECK (prioridad_manual IS NULL OR prioridad_manual >= 0)
);

-- ------------------------------------------------------------
-- 5. COMENTARIOS DE CONTRATO
-- ------------------------------------------------------------
COMMENT ON TABLE gapto.usuarios IS
    'F03-01-B01: raiz durable de ownership del usuario.';
COMMENT ON TABLE gapto.configuracion_usuario IS
    'F03-01-B01: configuracion financiera general 0..1 del usuario.';
COMMENT ON TABLE gapto.preferencias_ui IS
    'F03-01-B01: preferencias visuales 0..1 del usuario.';
COMMENT ON TABLE gapto.acciones_rapidas IS
    'F03-01-B01: accesos rapidos configurables de UI.';
COMMENT ON TABLE gapto.paises IS
    'F03-01-B01: catalogo ISO global de paises.';
COMMENT ON TABLE gapto.regiones IS
    'F03-01-B01: divisiones administrativas jerarquicas.';
COMMENT ON TABLE gapto.localidades IS
    'F03-01-B01: localidades como dimension geografica analitica.';
COMMENT ON TABLE gapto.direcciones IS
    'F03-01-B01: direcciones postales reutilizables.';
COMMENT ON TABLE gapto.terceros IS
    'F03-01-B01: maestro de personas, empresas y organismos externos.';
COMMENT ON TABLE gapto.tercero_direcciones IS
    'F03-01-B01: asociacion tercero-direccion por funcion.';
COMMENT ON TABLE gapto.actores_financieros IS
    'F03-01-B01: identidad economica unificadora self/tercero.';
COMMENT ON TABLE gapto.tercero_roles IS
    'F03-01-B01: capacidades globales declaradas de terceros.';
COMMENT ON TABLE gapto.clasificaciones_tercero IS
    'F03-01-B01: jerarquia configurable para clasificar terceros.';
COMMENT ON TABLE gapto.tercero_clasificaciones IS
    'F03-01-B01: asociacion tercero-clasificacion.';
COMMENT ON TABLE gapto.categorias_financieras IS
    'F03-01-B01: arbol flexible de categorias financieras.';
COMMENT ON TABLE gapto.tercero_afinidades IS
    'F03-01-B01: afinidades explicitas tercero-categoria.';

RESET ROLE;

-- ------------------------------------------------------------
-- 6. POSTCHECK DEL BLOQUE
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_table_count integer;
    v_bad_owners text;
    v_bad_primary_keys text;
BEGIN
    SELECT count(*)
      INTO v_table_count
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r'
       AND c.relname IN (
            'usuarios',
            'configuracion_usuario',
            'preferencias_ui',
            'acciones_rapidas',
            'paises',
            'regiones',
            'localidades',
            'direcciones',
            'terceros',
            'tercero_direcciones',
            'actores_financieros',
            'tercero_roles',
            'clasificaciones_tercero',
            'tercero_clasificaciones',
            'categorias_financieras',
            'tercero_afinidades'
       );

    IF v_table_count <> 16 THEN
        RAISE EXCEPTION
            'F03-01-B01 POSTCHECK: esperadas 16 tablas; encontradas=%',
            v_table_count;
    END IF;

    SELECT pg_catalog.string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_bad_owners
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r'
       AND c.relname IN (
            'usuarios',
            'configuracion_usuario',
            'preferencias_ui',
            'acciones_rapidas',
            'paises',
            'regiones',
            'localidades',
            'direcciones',
            'terceros',
            'tercero_direcciones',
            'actores_financieros',
            'tercero_roles',
            'clasificaciones_tercero',
            'tercero_clasificaciones',
            'categorias_financieras',
            'tercero_afinidades'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_bad_owners IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B01 POSTCHECK: tablas con owner incorrecto: %',
            v_bad_owners;
    END IF;

    SELECT pg_catalog.string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_bad_primary_keys
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r'
       AND c.relname IN (
            'usuarios',
            'configuracion_usuario',
            'preferencias_ui',
            'acciones_rapidas',
            'paises',
            'regiones',
            'localidades',
            'direcciones',
            'terceros',
            'tercero_direcciones',
            'actores_financieros',
            'tercero_roles',
            'clasificaciones_tercero',
            'tercero_clasificaciones',
            'categorias_financieras',
            'tercero_afinidades'
       )
       AND NOT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_constraint AS con
             WHERE con.conrelid = c.oid
               AND con.contype = 'p'
       );

    IF v_bad_primary_keys IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B01 POSTCHECK: tablas sin PK: %',
            v_bad_primary_keys;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
