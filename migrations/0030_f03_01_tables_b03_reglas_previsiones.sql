-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0030_f03_01_tables_b03_reglas_previsiones.sql
-- Ruta: migrations/0030_f03_01_tables_b03_reglas_previsiones.sql
-- Descripción: Materializa las tablas 29..32 del baseline físico:
--              reglas financieras, versiones, excepciones y previsiones.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b03_tables integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION 'F03-01-B03 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 28 THEN
        RAISE EXCEPTION 'F03-01-B03 PRECHECK: esperadas exactamente 28 tablas previas B01+B02; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_b03_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind IN ('r','p')
       AND c.relname IN ('reglas_financieras','regla_versiones','regla_excepciones','previsiones');

    IF v_b03_tables <> 0 THEN
        RAISE EXCEPTION 'F03-01-B03 TABLE DRIFT: existen % tablas reservadas del bloque', v_b03_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

CREATE TABLE gapto.reglas_financieras (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(160) NOT NULL,
    entidad_origen_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_reglas_financieras PRIMARY KEY (id),
    CONSTRAINT ck_reglas_financieras__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

CREATE TABLE gapto.regla_versiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    regla_id uuid NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,
    tipo_hecho_id uuid NOT NULL,
    flujo_tesoreria_esperado varchar(30) NOT NULL,
    categoria_id uuid,
    tercero_id uuid,
    cuenta_salida_esperada_id uuid,
    cuenta_entrada_esperada_id uuid,
    moneda varchar(3) NOT NULL,
    importe_referencia_lado varchar(10),
    periodicidad varchar(30),
    intervalo smallint DEFAULT 1,
    fecha_modo varchar(30) NOT NULL,
    dia_desde smallint,
    dia_hasta smallint,
    importe_modo varchar(40) NOT NULL,
    importe_fijo numeric(18,4),
    cuenta_calculo_id uuid,
    saldo_objetivo numeric(18,4),
    meses_historico smallint,
    presupuestable boolean NOT NULL,

    CONSTRAINT pk_regla_versiones PRIMARY KEY (id),
    CONSTRAINT ck_regla_versiones__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ck_regla_versiones__flujo_tesoreria
        CHECK (flujo_tesoreria_esperado IN ('SALIDA','ENTRADA','TRANSFERENCIA','SIN_MOVIMIENTO')),
    CONSTRAINT ck_regla_versiones__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_regla_versiones__importe_referencia_lado
        CHECK (
            importe_referencia_lado IS NULL
            OR (
                flujo_tesoreria_esperado = 'TRANSFERENCIA'
                AND importe_referencia_lado IN ('SALIDA','ENTRADA')
            )
        ),
    CONSTRAINT ck_regla_versiones__periodicidad
        CHECK (periodicidad IS NULL OR periodicidad IN ('DIARIA','SEMANAL','MENSUAL','ANUAL')),
    CONSTRAINT ck_regla_versiones__intervalo
        CHECK (periodicidad IS NULL OR (intervalo IS NOT NULL AND intervalo >= 1)),
    CONSTRAINT ck_regla_versiones__fecha_modo
        CHECK (fecha_modo IN ('ANCLA','VENTANA','CALENDARIO_ENTIDAD')),
    CONSTRAINT ck_regla_versiones__ventana
        CHECK (
            (fecha_modo = 'VENTANA' AND dia_desde BETWEEN 1 AND 31 AND dia_hasta BETWEEN 1 AND 31 AND dia_desde <= dia_hasta)
            OR (fecha_modo <> 'VENTANA' AND dia_desde IS NULL AND dia_hasta IS NULL)
        ),
    CONSTRAINT ck_regla_versiones__importe_modo
        CHECK (importe_modo IN ('FIJO','MEDIA_HISTORICA','MEDIANA_HISTORICA','ULTIMO_REAL','MANUAL','CALENDARIO_ENTIDAD','SALDO_OBJETIVO')),
    CONSTRAINT ck_regla_versiones__importe_fijo
        CHECK (importe_modo <> 'FIJO' OR (importe_fijo IS NOT NULL AND importe_fijo > 0)),
    CONSTRAINT ck_regla_versiones__saldo_objetivo
        CHECK (
            importe_modo <> 'SALDO_OBJETIVO'
            OR (cuenta_calculo_id IS NOT NULL AND saldo_objetivo IS NOT NULL)
        ),
    CONSTRAINT ck_regla_versiones__meses_historico
        CHECK (meses_historico IS NULL OR meses_historico > 0),
    CONSTRAINT ck_regla_versiones__cuentas_por_flujo
        CHECK (
            (flujo_tesoreria_esperado = 'SIN_MOVIMIENTO' AND cuenta_salida_esperada_id IS NULL AND cuenta_entrada_esperada_id IS NULL)
            OR (flujo_tesoreria_esperado = 'SALIDA' AND cuenta_entrada_esperada_id IS NULL)
            OR (flujo_tesoreria_esperado = 'ENTRADA' AND cuenta_salida_esperada_id IS NULL)
            OR flujo_tesoreria_esperado = 'TRANSFERENCIA'
        )
);

CREATE TABLE gapto.regla_excepciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    regla_id uuid NOT NULL,
    fecha_objetivo date NOT NULL,
    omitida boolean NOT NULL DEFAULT false,
    importe_override numeric(18,4),
    fecha_override date,
    motivo text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_regla_excepciones PRIMARY KEY (id),
    CONSTRAINT ck_regla_excepciones__importe_override
        CHECK (importe_override IS NULL OR importe_override > 0)
);

CREATE TABLE gapto.previsiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    regla_version_id uuid,
    fecha_objetivo_regla date,
    concepto varchar(200) NOT NULL,
    tipo_hecho_id uuid NOT NULL,
    categoria_id uuid,
    tercero_id uuid,
    entidad_id uuid,
    fecha_esperada_desde date NOT NULL,
    fecha_esperada_hasta date NOT NULL,
    flujo_tesoreria_esperado varchar(30) NOT NULL,
    moneda varchar(3) NOT NULL,
    importe_esperado numeric(18,4),
    importe_referencia_lado varchar(10),
    cuenta_salida_esperada_id uuid,
    cuenta_entrada_esperada_id uuid,
    presupuestable boolean NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'ABIERTA',
    recalculo_automatico boolean NOT NULL DEFAULT true,
    motivo_ajuste text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_previsiones PRIMARY KEY (id),
    CONSTRAINT ck_previsiones__concepto_no_blanco
        CHECK (concepto ~ '[^[:space:]]'),
    CONSTRAINT ck_previsiones__fechas
        CHECK (fecha_esperada_desde <= fecha_esperada_hasta),
    CONSTRAINT ck_previsiones__flujo_tesoreria
        CHECK (flujo_tesoreria_esperado IN ('SALIDA','ENTRADA','TRANSFERENCIA','SIN_MOVIMIENTO')),
    CONSTRAINT ck_previsiones__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_previsiones__importe_esperado
        CHECK (importe_esperado IS NULL OR importe_esperado > 0),
    CONSTRAINT ck_previsiones__importe_referencia_lado
        CHECK (
            importe_referencia_lado IS NULL
            OR (
                flujo_tesoreria_esperado = 'TRANSFERENCIA'
                AND importe_referencia_lado IN ('SALIDA','ENTRADA')
            )
        ),
    CONSTRAINT ck_previsiones__cuentas_por_flujo
        CHECK (
            (flujo_tesoreria_esperado = 'SIN_MOVIMIENTO' AND cuenta_salida_esperada_id IS NULL AND cuenta_entrada_esperada_id IS NULL)
            OR (flujo_tesoreria_esperado = 'SALIDA' AND cuenta_entrada_esperada_id IS NULL)
            OR (flujo_tesoreria_esperado = 'ENTRADA' AND cuenta_salida_esperada_id IS NULL)
            OR flujo_tesoreria_esperado = 'TRANSFERENCIA'
        ),
    CONSTRAINT ck_previsiones__estado
        CHECK (estado IN ('ABIERTA','REALIZADA','OMITIDA','CANCELADA')),
    CONSTRAINT ck_previsiones__recalculo_estado
        CHECK (estado = 'ABIERTA' OR recalculo_automatico = false)
);

COMMENT ON TABLE gapto.reglas_financieras IS 'F03-01-B03 tabla 29: identidad durable de una regla financiera.';
COMMENT ON TABLE gapto.regla_versiones IS 'F03-01-B03 tabla 30: condiciones versionadas de una regla financiera.';
COMMENT ON TABLE gapto.regla_excepciones IS 'F03-01-B03 tabla 31: overrides de ocurrencias concretas de reglas.';
COMMENT ON TABLE gapto.previsiones IS 'F03-01-B03 tabla 32: ocurrencias esperadas autosuficientes sin impacto de liquidez.';

RESET ROLE;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b03_tables integer;
    v_wrong_owner integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    SELECT count(*) INTO v_b03_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN ('reglas_financieras','regla_versiones','regla_excepciones','previsiones');

    SELECT count(*) INTO v_wrong_owner
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN ('reglas_financieras','regla_versiones','regla_excepciones','previsiones')
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_total_tables <> 32 OR v_b03_tables <> 4 OR v_wrong_owner <> 0 THEN
        RAISE EXCEPTION 'F03-01-B03 POSTCHECK: total=%, b03=%, wrong_owner=%; esperado=32,4,0', v_total_tables, v_b03_tables, v_wrong_owner;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
