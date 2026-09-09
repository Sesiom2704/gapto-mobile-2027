-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0060_f03_01_tables_b06_presupuestos_cierres.sql
-- Ruta: migrations/0060_f03_01_tables_b06_presupuestos_cierres.sql
-- Descripción: Materializa las tablas 60..67 del baseline físico:
--              presupuestos versionados, líneas, cierres mensuales
--              versionados y sus snapshots (saldos de cuenta, líneas
--              presupuestarias, métricas y posiciones patrimoniales).
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b06_tables integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION 'F03-01-B06 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 59 THEN
        RAISE EXCEPTION 'F03-01-B06 PRECHECK: esperadas exactamente 59 tablas previas; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_b06_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind IN ('r','p')
       AND c.relname IN (
           'presupuestos','presupuesto_lineas','cierres_mensuales','cierre_saldos_cuenta',
           'cierre_presupuesto_lineas','metricas_definicion','cierre_metricas',
           'cierre_posiciones_entidad'
       );

    IF v_b06_tables <> 0 THEN
        RAISE EXCEPTION 'F03-01-B06 TABLE DRIFT: existen % tablas reservadas del bloque', v_b06_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 60. presupuestos
CREATE TABLE gapto.presupuestos (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    periodo_desde date NOT NULL,
    periodo_hasta date NOT NULL,
    moneda varchar(3) NOT NULL,
    perspectiva varchar(20) NOT NULL,
    version_presupuesto integer NOT NULL,
    reemplaza_presupuesto_id uuid,
    estado varchar(20) NOT NULL DEFAULT 'BORRADOR',
    generado_desde_cierre_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_presupuestos PRIMARY KEY (id),
    CONSTRAINT ck_presupuestos__periodo
        CHECK (periodo_hasta >= periodo_desde),
    CONSTRAINT ck_presupuestos__no_self_reemplaza
        CHECK (reemplaza_presupuesto_id IS NULL OR reemplaza_presupuesto_id <> id),
    CONSTRAINT ck_presupuestos__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_presupuestos__perspectiva
        CHECK (perspectiva IN ('ATRIBUIBLE','TOTAL')),
    CONSTRAINT ck_presupuestos__version
        CHECK (version_presupuesto >= 1),
    CONSTRAINT ck_presupuestos__estado
        CHECK (estado IN ('BORRADOR','ACTIVO','SUSTITUIDO','CERRADO'))
);

-- 61. presupuesto_lineas
CREATE TABLE gapto.presupuesto_lineas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    presupuesto_id uuid NOT NULL,
    nombre varchar(120),
    tipo_linea varchar(20) NOT NULL,
    naturaleza_economica varchar(20) NOT NULL,
    prioridad_consumo integer,
    importe_base_calculado numeric(18,4),
    importe_objetivo numeric(18,4) NOT NULL,
    metodo_estimacion varchar(30) NOT NULL,
    meses_historico smallint,
    recalculo_automatico boolean NOT NULL DEFAULT true,
    notas text,

    CONSTRAINT pk_presupuesto_lineas PRIMARY KEY (id),
    CONSTRAINT ck_presupuesto_lineas__tipo
        CHECK (tipo_linea IN ('BOLSA','INDICADOR')),
    CONSTRAINT ck_presupuesto_lineas__naturaleza
        CHECK (naturaleza_economica IN ('GASTO','INGRESO')),
    CONSTRAINT ck_presupuesto_lineas__importe_objetivo
        CHECK (importe_objetivo >= 0),
    CONSTRAINT ck_presupuesto_lineas__metodo
        CHECK (metodo_estimacion IN ('MANUAL','MEDIA_HISTORICA','MEDIANA_HISTORICA','ULTIMO_REAL')),
    CONSTRAINT ck_presupuesto_lineas__meses_historico
        CHECK (meses_historico IS NULL OR meses_historico > 0)
);

-- 62. cierres_mensuales
CREATE TABLE gapto.cierres_mensuales (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    periodo_desde date NOT NULL,
    periodo_hasta date NOT NULL,
    cerrado_at timestamptz NOT NULL,
    criterio varchar(20) NOT NULL,
    origen_cierre varchar(30) NOT NULL,
    metodologia_version varchar(40) NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'CERRADO',
    version_cierre integer NOT NULL,
    reemplaza_cierre_id uuid,
    reabierto_at timestamptz,
    motivo_reapertura text,
    notas text,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_cierres_mensuales PRIMARY KEY (id),
    CONSTRAINT ck_cierres_mensuales__periodo
        CHECK (periodo_hasta >= periodo_desde),
    CONSTRAINT ck_cierres_mensuales__no_self_reemplaza
        CHECK (reemplaza_cierre_id IS NULL OR reemplaza_cierre_id <> id),
    CONSTRAINT ck_cierres_mensuales__criterio
        CHECK (criterio IN ('CAJA','DEVENGO','MIXTO','OTRO')),
    CONSTRAINT ck_cierres_mensuales__origen
        CHECK (origen_cierre IN ('CALCULADO_2027','IMPORTADO_LEGACY')),
    CONSTRAINT ck_cierres_mensuales__estado
        CHECK (estado IN ('CERRADO','REABIERTO')),
    CONSTRAINT ck_cierres_mensuales__reapertura_coherente
        CHECK (
            (estado = 'CERRADO' AND reabierto_at IS NULL)
            OR (estado = 'REABIERTO' AND reabierto_at IS NOT NULL)
        ),
    CONSTRAINT ck_cierres_mensuales__version
        CHECK (version_cierre >= 1)
);

-- 63. cierre_saldos_cuenta
CREATE TABLE gapto.cierre_saldos_cuenta (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cierre_id uuid NOT NULL,
    cuenta_id uuid NOT NULL,
    moneda varchar(3) NOT NULL,
    naturaleza varchar(20) NOT NULL,
    computa_liquidez boolean NOT NULL,
    computa_patrimonio boolean NOT NULL,
    saldo_total numeric(18,4),
    participacion_usuario_pct numeric(7,4),
    saldo_atribuible_usuario numeric(18,4),

    CONSTRAINT pk_cierre_saldos_cuenta PRIMARY KEY (id),
    CONSTRAINT ck_cierre_saldos_cuenta__naturaleza
        CHECK (naturaleza IN ('ACTIVO','PASIVO')),
    CONSTRAINT ck_cierre_saldos_cuenta__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_cierre_saldos_cuenta__participacion
        CHECK (participacion_usuario_pct IS NULL OR (participacion_usuario_pct >= 0 AND participacion_usuario_pct <= 100))
);

-- 64. cierre_presupuesto_lineas
CREATE TABLE gapto.cierre_presupuesto_lineas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cierre_id uuid NOT NULL,
    presupuesto_linea_id uuid NOT NULL,
    nombre_snapshot varchar(120),
    tipo_linea varchar(20) NOT NULL,
    naturaleza_economica varchar(20) NOT NULL,
    perspectiva varchar(20) NOT NULL,
    moneda varchar(3) NOT NULL,
    importe_objetivo numeric(18,4) NOT NULL,
    real_total numeric(18,4),
    real_atribuible_usuario numeric(18,4),
    estado_calculo varchar(20) NOT NULL,
    desviacion_objetivo numeric(18,4),

    CONSTRAINT pk_cierre_presupuesto_lineas PRIMARY KEY (id),
    CONSTRAINT ck_cierre_presupuesto_lineas__tipo
        CHECK (tipo_linea IN ('BOLSA','INDICADOR')),
    CONSTRAINT ck_cierre_presupuesto_lineas__naturaleza
        CHECK (naturaleza_economica IN ('GASTO','INGRESO')),
    CONSTRAINT ck_cierre_presupuesto_lineas__perspectiva
        CHECK (perspectiva IN ('ATRIBUIBLE','TOTAL')),
    CONSTRAINT ck_cierre_presupuesto_lineas__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_cierre_presupuesto_lineas__importe_objetivo
        CHECK (importe_objetivo >= 0),
    CONSTRAINT ck_cierre_presupuesto_lineas__estado_calculo
        CHECK (estado_calculo IN ('COMPLETO','PARCIAL','INDETERMINADO'))
);

-- 65. metricas_definicion
CREATE TABLE gapto.metricas_definicion (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    codigo varchar(80) NOT NULL,
    nombre varchar(120) NOT NULL,
    tipo_valor varchar(20) NOT NULL,
    unidad varchar(30) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_metricas_definicion PRIMARY KEY (id),
    CONSTRAINT ck_metricas_definicion__codigo_no_blanco
        CHECK (codigo ~ '[^[:space:]]'),
    CONSTRAINT ck_metricas_definicion__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]'),
    CONSTRAINT ck_metricas_definicion__tipo_valor
        CHECK (tipo_valor IN ('NUMERIC','TEXT')),
    CONSTRAINT ck_metricas_definicion__unidad
        CHECK (unidad IN ('MONEDA','PORCENTAJE','NUMERO','TEXTO','OTRA'))
);

-- 66. cierre_metricas
CREATE TABLE gapto.cierre_metricas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cierre_id uuid NOT NULL,
    metrica_id uuid NOT NULL,
    clave_desglose varchar(180),
    dimensiones_snapshot jsonb,
    valor_numeric numeric(18,6),
    valor_text text,

    CONSTRAINT pk_cierre_metricas PRIMARY KEY (id),
    CONSTRAINT ck_cierre_metricas__clave_no_blanco
        CHECK (clave_desglose IS NULL OR clave_desglose ~ '[^[:space:]]'),
    CONSTRAINT ck_cierre_metricas__valor_exclusivo
        CHECK (
            (valor_numeric IS NOT NULL AND valor_text IS NULL)
            OR (valor_numeric IS NULL AND valor_text IS NOT NULL)
        )
);

-- 67. cierre_posiciones_entidad
CREATE TABLE gapto.cierre_posiciones_entidad (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cierre_id uuid NOT NULL,
    entidad_id uuid NOT NULL,
    naturaleza_posicion varchar(20) NOT NULL,
    dominio_posicion varchar(30) NOT NULL,
    moneda varchar(3) NOT NULL,
    valor_total numeric(18,4),
    participacion_pct numeric(7,4),
    valor_atribuible_usuario numeric(18,4),
    incluida_en_total_patrimonio boolean NOT NULL,

    CONSTRAINT pk_cierre_posiciones_entidad PRIMARY KEY (id),
    CONSTRAINT ck_cierre_posiciones_entidad__naturaleza
        CHECK (naturaleza_posicion IN ('ACTIVO','PASIVO')),
    CONSTRAINT ck_cierre_posiciones_entidad__dominio
        CHECK (dominio_posicion IN ('PROPIEDAD','FINANCIACION','INVERSION','DERECHO_OBLIGACION','OTRO')),
    CONSTRAINT ck_cierre_posiciones_entidad__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_cierre_posiciones_entidad__participacion
        CHECK (participacion_pct IS NULL OR (participacion_pct >= 0 AND participacion_pct <= 100))
);

COMMENT ON TABLE gapto.presupuestos IS 'F03-01-B06 tabla 60: cabecera versionada de presupuesto por periodo.';
COMMENT ON TABLE gapto.presupuesto_lineas IS 'F03-01-B06 tabla 61: bolsa consumible u objetivo analítico de un presupuesto.';
COMMENT ON TABLE gapto.cierres_mensuales IS 'F03-01-B06 tabla 62: cabecera de cierre histórico versionado.';
COMMENT ON TABLE gapto.cierre_saldos_cuenta IS 'F03-01-B06 tabla 63: snapshot autosuficiente de saldos de cuentas.';
COMMENT ON TABLE gapto.cierre_presupuesto_lineas IS 'F03-01-B06 tabla 64: snapshot objetivo vs realidad por línea presupuestaria.';
COMMENT ON TABLE gapto.metricas_definicion IS 'F03-01-B06 tabla 65: catálogo de KPI del sistema.';
COMMENT ON TABLE gapto.cierre_metricas IS 'F03-01-B06 tabla 66: snapshot de KPI por cierre.';
COMMENT ON TABLE gapto.cierre_posiciones_entidad IS 'F03-01-B06 tabla 67: snapshot patrimonial de posiciones económicas.';

RESET ROLE;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b06_tables integer;
    v_wrong_owner integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    SELECT count(*) INTO v_b06_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'presupuestos','presupuesto_lineas','cierres_mensuales','cierre_saldos_cuenta',
           'cierre_presupuesto_lineas','metricas_definicion','cierre_metricas',
           'cierre_posiciones_entidad'
       );

    SELECT count(*) INTO v_wrong_owner
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'presupuestos','presupuesto_lineas','cierres_mensuales','cierre_saldos_cuenta',
           'cierre_presupuesto_lineas','metricas_definicion','cierre_metricas',
           'cierre_posiciones_entidad'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_total_tables <> 67 OR v_b06_tables <> 8 OR v_wrong_owner <> 0 THEN
        RAISE EXCEPTION 'F03-01-B06 POSTCHECK: total=%, b06=%, wrong_owner=%; esperado=67,8,0', v_total_tables, v_b06_tables, v_wrong_owner;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
