-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0020_f03_01_tables_b02_catalogos_cuentas_entidades.sql
-- Ruta: migrations/0020_f03_01_tables_b02_catalogos_cuentas_entidades.sql
-- Descripción: Materializa las tablas 17..28 del baseline físico:
--              tipos de hecho, magnitudes, preferencias, cuentas y entidades.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. PREFLIGHT FAIL-FAST
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_total_tables integer;
    v_b01_tables integer;
    v_existing_tables text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_namespace AS n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION
            'F03-01-B02 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*)
      INTO v_total_tables
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r';

    IF v_total_tables <> 16 THEN
        RAISE EXCEPTION
            'F03-01-B02 PRECHECK: esperadas exactamente 16 tablas previas de B01; encontradas=%',
            v_total_tables;
    END IF;

    SELECT count(*)
      INTO v_b01_tables
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

    IF v_b01_tables <> 16 THEN
        RAISE EXCEPTION
            'F03-01-B02 PRECHECK: baseline B01 incompleto; encontradas=% de 16 tablas esperadas',
            v_b01_tables;
    END IF;

    SELECT pg_catalog.string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_existing_tables
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind IN ('r', 'p')
       AND c.relname IN (
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
       );

    IF v_existing_tables IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B02 TABLE DRIFT: ya existen tablas reservadas del bloque: %',
            v_existing_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- ------------------------------------------------------------
-- 2. CATÁLOGOS, MAGNITUDES Y PREFERENCIAS DE REGISTRO
-- ------------------------------------------------------------
CREATE TABLE gapto.tipos_hecho (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    codigo varchar(50) NOT NULL,
    nombre varchar(100) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_tipos_hecho PRIMARY KEY (id),
    CONSTRAINT ck_tipos_hecho__codigo_formato
        CHECK (codigo ~ '^[A-Z0-9]+(_[A-Z0-9]+)*$'),
    CONSTRAINT ck_tipos_hecho__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

CREATE TABLE gapto.magnitudes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(80) NOT NULL,
    unidad_default varchar(20) NOT NULL,
    precision_decimales smallint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enabled boolean NOT NULL DEFAULT true,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_magnitudes PRIMARY KEY (id),
    CONSTRAINT ck_magnitudes__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_magnitudes__unidad_default_no_blanco
        CHECK (unidad_default ~ '[^[:space:]]'),
    CONSTRAINT ck_magnitudes__precision_decimales
        CHECK (precision_decimales BETWEEN 0 AND 6)
);

CREATE TABLE gapto.categoria_magnitudes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    categoria_id uuid NOT NULL,
    magnitud_id uuid NOT NULL,
    obligatoria boolean NOT NULL DEFAULT false,
    orden smallint NOT NULL DEFAULT 0,

    CONSTRAINT pk_categoria_magnitudes PRIMARY KEY (id),
    CONSTRAINT ck_categoria_magnitudes__orden_no_negativo
        CHECK (orden >= 0)
);

CREATE TABLE gapto.preferencias_registro (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tipo_hecho_id uuid,
    categoria_id uuid,
    tercero_id uuid,
    entidad_id uuid,
    cuenta_default_id uuid,
    presupuestable_default boolean,
    prioridad integer NOT NULL DEFAULT 100,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_preferencias_registro PRIMARY KEY (id),
    CONSTRAINT ck_preferencias_registro__propone_valor
        CHECK (
            cuenta_default_id IS NOT NULL
            OR presupuestable_default IS NOT NULL
        )
);

CREATE TABLE gapto.plantillas_registro (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(100) NOT NULL,
    tipo_hecho_id uuid NOT NULL,
    categoria_id uuid,
    tercero_id uuid,
    entidad_id uuid,
    cuenta_default_id uuid,
    presupuestable_default boolean,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_plantillas_registro PRIMARY KEY (id),
    CONSTRAINT ck_plantillas_registro__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

-- ------------------------------------------------------------
-- 3. CUENTAS Y PARTICIPACIONES
-- ------------------------------------------------------------
CREATE TABLE gapto.cuentas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(120) NOT NULL,
    tercero_gestor_id uuid,
    tipo varchar(30) NOT NULL,
    naturaleza varchar(20) NOT NULL,
    moneda varchar(3) NOT NULL,
    saldo_apertura numeric(18,4),
    fecha_inicio_ledger date,
    limite_credito numeric(18,4),
    computa_liquidez boolean NOT NULL,
    computa_patrimonio boolean NOT NULL,
    permite_negativo boolean NOT NULL,
    orden smallint NOT NULL DEFAULT 0,
    enabled boolean NOT NULL DEFAULT true,
    fecha_cierre date,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_cuentas PRIMARY KEY (id),
    CONSTRAINT ck_cuentas__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_cuentas__tipo
        CHECK (
            tipo IN (
                'CORRIENTE',
                'AHORRO',
                'EFECTIVO',
                'CREDITO',
                'POLIZA_CREDITO',
                'PREPAGO',
                'OTRA'
            )
        ),
    CONSTRAINT ck_cuentas__naturaleza
        CHECK (naturaleza IN ('ACTIVO', 'PASIVO')),
    CONSTRAINT ck_cuentas__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_cuentas__apertura_pareja
        CHECK (
            (saldo_apertura IS NULL AND fecha_inicio_ledger IS NULL)
            OR (saldo_apertura IS NOT NULL AND fecha_inicio_ledger IS NOT NULL)
        ),
    CONSTRAINT ck_cuentas__limite_credito_no_negativo
        CHECK (limite_credito IS NULL OR limite_credito >= 0),
    CONSTRAINT ck_cuentas__orden_no_negativo
        CHECK (orden >= 0),
    CONSTRAINT ck_cuentas__fecha_cierre_ledger
        CHECK (
            fecha_cierre IS NULL
            OR fecha_inicio_ledger IS NULL
            OR fecha_cierre >= fecha_inicio_ledger
        ),
    CONSTRAINT ck_cuentas__cierre_deshabilita
        CHECK (fecha_cierre IS NULL OR enabled = false)
);

CREATE TABLE gapto.cuenta_capacidades (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cuenta_id uuid NOT NULL,
    capacidad_codigo varchar(50) NOT NULL,

    CONSTRAINT pk_cuenta_capacidades PRIMARY KEY (id),
    CONSTRAINT ck_cuenta_capacidades__capacidad_codigo
        CHECK (
            capacidad_codigo IN (
                'PAGAR_GASTO',
                'RECIBIR_INGRESO',
                'TRANSFERIR_SALIDA',
                'TRANSFERIR_ENTRADA',
                'DOMICILIAR',
                'COMPRA_TARJETA'
            )
        )
);

CREATE TABLE gapto.cuenta_participaciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cuenta_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    porcentaje numeric(7,4) NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,

    CONSTRAINT pk_cuenta_participaciones PRIMARY KEY (id),
    CONSTRAINT ck_cuenta_participaciones__porcentaje
        CHECK (porcentaje > 0 AND porcentaje <= 100),
    CONSTRAINT ck_cuenta_participaciones__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);

-- ------------------------------------------------------------
-- 4. ENTIDADES, PARTICIPACIONES, RELACIONES Y CONTEXTOS
-- ------------------------------------------------------------
CREATE TABLE gapto.entidades (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tipo_entidad varchar(50) NOT NULL,
    nombre varchar(160) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_entidades PRIMARY KEY (id),
    CONSTRAINT ck_entidades__tipo_entidad
        CHECK (
            tipo_entidad IN (
                'PROPIEDAD',
                'CONTRATO',
                'SERVICIO',
                'FINANCIACION',
                'INVERSION',
                'DERECHO_OBLIGACION',
                'CONTEXTO'
            )
        ),
    CONSTRAINT ck_entidades__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

CREATE TABLE gapto.entidad_participaciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    entidad_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    porcentaje numeric(7,4) NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,

    CONSTRAINT pk_entidad_participaciones PRIMARY KEY (id),
    CONSTRAINT ck_entidad_participaciones__porcentaje
        CHECK (porcentaje > 0 AND porcentaje <= 100),
    CONSTRAINT ck_entidad_participaciones__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);

CREATE TABLE gapto.entidad_relaciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    entidad_origen_id uuid NOT NULL,
    entidad_destino_id uuid NOT NULL,
    tipo_relacion varchar(50) NOT NULL,
    vigente_desde date,
    vigente_hasta date,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_entidad_relaciones PRIMARY KEY (id),
    CONSTRAINT ck_entidad_relaciones__no_self
        CHECK (entidad_origen_id <> entidad_destino_id),
    CONSTRAINT ck_entidad_relaciones__tipo_relacion
        CHECK (tipo_relacion IN ('GARANTIZADA_POR')),
    CONSTRAINT ck_entidad_relaciones__vigencia
        CHECK (
            vigente_desde IS NULL
            OR vigente_hasta IS NULL
            OR vigente_hasta >= vigente_desde
        )
);

CREATE TABLE gapto.contextos (
    entidad_id uuid NOT NULL,
    tipo_contexto varchar(30) NOT NULL,
    fecha_inicio date,
    fecha_fin date,
    notas text,

    CONSTRAINT pk_contextos PRIMARY KEY (entidad_id),
    CONSTRAINT ck_contextos__tipo_contexto
        CHECK (
            tipo_contexto IN (
                'VIAJE',
                'REFORMA',
                'EVENTO',
                'SOCIAL',
                'PROYECTO',
                'OTRO'
            )
        ),
    CONSTRAINT ck_contextos__fechas
        CHECK (
            fecha_inicio IS NULL
            OR fecha_fin IS NULL
            OR fecha_fin >= fecha_inicio
        ),
    CONSTRAINT ck_contextos__notas_no_blanco
        CHECK (notas IS NULL OR notas ~ '[^[:space:]]')
);

-- ------------------------------------------------------------
-- 5. COMENTARIOS DE CONTRATO
-- ------------------------------------------------------------
COMMENT ON TABLE gapto.tipos_hecho IS
    'F03-01-B02: catalogo semantico controlado de tipos de hecho.';
COMMENT ON TABLE gapto.magnitudes IS
    'F03-01-B02: definiciones configurables de magnitudes y unidad de captura.';
COMMENT ON TABLE gapto.categoria_magnitudes IS
    'F03-01-B02: configuracion categoria-magnitud para formularios dinamicos.';
COMMENT ON TABLE gapto.preferencias_registro IS
    'F03-01-B02: defaults contextuales automaticos de registro.';
COMMENT ON TABLE gapto.plantillas_registro IS
    'F03-01-B02: presets explicitos reutilizables de registro.';
COMMENT ON TABLE gapto.cuentas IS
    'F03-01-B02: instrumentos de tesoreria con ledger, naturaleza y capacidades separadas.';
COMMENT ON TABLE gapto.cuenta_capacidades IS
    'F03-01-B02: operaciones permitidas por cuenta.';
COMMENT ON TABLE gapto.cuenta_participaciones IS
    'F03-01-B02: participacion economica temporal sobre cuentas sin alterar saldo real.';
COMMENT ON TABLE gapto.entidades IS
    'F03-01-B02: superclase ligera de objetos de dominio con ownership comun.';
COMMENT ON TABLE gapto.entidad_participaciones IS
    'F03-01-B02: participacion economica temporal de actores en entidades.';
COMMENT ON TABLE gapto.entidad_relaciones IS
    'F03-01-B02: relaciones semanticas temporales controladas entre entidades.';
COMMENT ON TABLE gapto.contextos IS
    'F03-01-B02: subtipo entidad para viaje, reforma, evento, proyecto y otros contextos.';

RESET ROLE;

-- ------------------------------------------------------------
-- 6. POSTCHECK DEL BLOQUE
-- ------------------------------------------------------------
DO $gapto$
DECLARE
    v_block_table_count integer;
    v_total_table_count integer;
    v_bad_owners text;
    v_bad_primary_keys text;
BEGIN
    SELECT count(*)
      INTO v_block_table_count
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r'
       AND c.relname IN (
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
       );

    IF v_block_table_count <> 12 THEN
        RAISE EXCEPTION
            'F03-01-B02 POSTCHECK: esperadas 12 tablas del bloque; encontradas=%',
            v_block_table_count;
    END IF;

    SELECT count(*)
      INTO v_total_table_count
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r';

    IF v_total_table_count <> 28 THEN
        RAISE EXCEPTION
            'F03-01-B02 POSTCHECK: esperadas 28 tablas acumuladas B01+B02; encontradas=%',
            v_total_table_count;
    END IF;

    SELECT pg_catalog.string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_bad_owners
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto'
       AND c.relkind = 'r'
       AND c.relname IN (
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_bad_owners IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B02 POSTCHECK: tablas con owner incorrecto: %',
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
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
       )
       AND NOT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_constraint AS con
             WHERE con.conrelid = c.oid
               AND con.contype = 'p'
       );

    IF v_bad_primary_keys IS NOT NULL THEN
        RAISE EXCEPTION
            'F03-01-B02 POSTCHECK: tablas sin PK: %',
            v_bad_primary_keys;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
