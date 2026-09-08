-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0050_f03_01_tables_b05_dominios_especializados.sql
-- Ruta: migrations/0050_f03_01_tables_b05_dominios_especializados.sql
-- Descripción: Materializa las tablas 46..59 del baseline físico:
--              derechos/obligaciones financieras, propiedades y su
--              valoración, contratos y participantes, servicios y sus
--              vínculos a propiedad/contrato, financiaciones con sus
--              condiciones versionadas y cuotas, e inversiones con sus
--              objetivos versionados y valoraciones.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b05_tables integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION 'F03-01-B05 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 45 THEN
        RAISE EXCEPTION 'F03-01-B05 PRECHECK: esperadas exactamente 45 tablas previas B01+B02+B03+B04; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_b05_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind IN ('r','p')
       AND c.relname IN (
           'derechos_obligaciones_financieras','propiedades','propiedad_valoraciones',
           'contratos','contrato_participantes','servicios','propiedad_servicios',
           'contrato_servicios','financiaciones','financiacion_condiciones_versiones',
           'financiacion_cuotas','inversiones','inversion_objetivos_versiones',
           'inversion_valoraciones'
       );

    IF v_b05_tables <> 0 THEN
        RAISE EXCEPTION 'F03-01-B05 TABLE DRIFT: existen % tablas reservadas del bloque', v_b05_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 46. derechos_obligaciones_financieras
CREATE TABLE gapto.derechos_obligaciones_financieras (
    entidad_id uuid NOT NULL,
    tipo varchar(30) NOT NULL,
    contraparte_actor_id uuid,
    moneda varchar(3) NOT NULL,
    importe_original_documentado numeric(18,4),
    saldo_apertura numeric(18,4),
    fecha_inicio_seguimiento date,
    fecha_vencimiento_final date,
    estado varchar(20) NOT NULL DEFAULT 'ACTIVA',
    motivo_cierre varchar(30),
    fecha_cierre date,
    notas text,

    CONSTRAINT pk_derechos_obligaciones_financieras PRIMARY KEY (entidad_id),
    CONSTRAINT ck_derechos_obligaciones_financieras__tipo
        CHECK (tipo IN ('DERECHO_COBRO','OBLIGACION_PAGO')),
    CONSTRAINT ck_derechos_obligaciones_financieras__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_derechos_obligaciones_financieras__saldo_apertura
        CHECK (saldo_apertura IS NULL OR saldo_apertura >= 0),
    CONSTRAINT ck_derechos_obligaciones_financieras__apertura_pareja
        CHECK ((saldo_apertura IS NULL) = (fecha_inicio_seguimiento IS NULL)),
    CONSTRAINT ck_derechos_obligaciones_financieras__estado
        CHECK (estado IN ('ACTIVA','CERRADA')),
    CONSTRAINT ck_derechos_obligaciones_financieras__motivo_cierre
        CHECK (motivo_cierre IS NULL OR motivo_cierre IN ('LIQUIDADA','CONDONADA','CANCELADA','OTRO')),
    CONSTRAINT ck_derechos_obligaciones_financieras__cierre_deshabilita
        CHECK (
            (estado = 'ACTIVA' AND motivo_cierre IS NULL AND fecha_cierre IS NULL)
            OR estado = 'CERRADA'
        )
);

-- 47. propiedades
CREATE TABLE gapto.propiedades (
    entidad_id uuid NOT NULL,
    direccion_id uuid,
    tipo_propiedad varchar(30) NOT NULL,
    referencia_catastral varchar(50),
    fecha_adquisicion date,
    fecha_salida_patrimonio date,
    motivo_salida varchar(30),
    superficie_m2 numeric(10,2),
    superficie_construida_m2 numeric(10,2),
    habitaciones smallint,
    banos smallint,
    tiene_garaje boolean,
    tiene_trastero boolean,
    incluir_en_rentabilidad boolean NOT NULL DEFAULT true,
    notas text,

    CONSTRAINT pk_propiedades PRIMARY KEY (entidad_id),
    CONSTRAINT ck_propiedades__tipo
        CHECK (tipo_propiedad IN ('VIVIENDA','LOCAL','GARAJE','TERRENO','OTRO')),
    CONSTRAINT ck_propiedades__motivo_salida
        CHECK (motivo_salida IS NULL OR motivo_salida IN ('VENTA','DONACION','OTRO')),
    CONSTRAINT ck_propiedades__salida_exige_motivo
        CHECK (fecha_salida_patrimonio IS NULL OR motivo_salida IS NOT NULL),
    CONSTRAINT ck_propiedades__salida_no_anterior
        CHECK (
            fecha_adquisicion IS NULL OR fecha_salida_patrimonio IS NULL
            OR fecha_salida_patrimonio >= fecha_adquisicion
        ),
    CONSTRAINT ck_propiedades__superficie
        CHECK (superficie_m2 IS NULL OR superficie_m2 > 0),
    CONSTRAINT ck_propiedades__superficie_construida
        CHECK (superficie_construida_m2 IS NULL OR superficie_construida_m2 > 0),
    CONSTRAINT ck_propiedades__habitaciones
        CHECK (habitaciones IS NULL OR habitaciones >= 0),
    CONSTRAINT ck_propiedades__banos
        CHECK (banos IS NULL OR banos >= 0)
);

-- 48. propiedad_valoraciones
CREATE TABLE gapto.propiedad_valoraciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    propiedad_entidad_id uuid NOT NULL,
    fecha_valoracion date,
    valor_total numeric(18,4) NOT NULL,
    moneda varchar(3) NOT NULL,
    metodo varchar(30) NOT NULL,
    fuente varchar(160),
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_propiedad_valoraciones PRIMARY KEY (id),
    CONSTRAINT ck_propiedad_valoraciones__valor_total
        CHECK (valor_total > 0),
    CONSTRAINT ck_propiedad_valoraciones__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_propiedad_valoraciones__metodo
        CHECK (metodo IN ('COMPRA','MERCADO','TASACION','MANUAL','FISCAL_REFERENCIA'))
);

-- 49. contratos
CREATE TABLE gapto.contratos (
    entidad_id uuid NOT NULL,
    propiedad_entidad_id uuid NOT NULL,
    tipo_contrato varchar(40) NOT NULL,
    fecha_inicio date,
    fecha_fin_prevista date,
    fecha_fin_real date,
    estado_documental varchar(30) NOT NULL DEFAULT 'BORRADOR',
    regla_renta_id uuid,
    notas text,

    CONSTRAINT pk_contratos PRIMARY KEY (entidad_id),
    CONSTRAINT ck_contratos__tipo
        CHECK (tipo_contrato IN ('ALQUILER_VIVIENDA','HABITACION','OTRO')),
    CONSTRAINT ck_contratos__estado_documental
        CHECK (estado_documental IN ('BORRADOR','FORMALIZADO','CANCELADO')),
    CONSTRAINT ck_contratos__formalizado_exige_inicio
        CHECK (estado_documental <> 'FORMALIZADO' OR fecha_inicio IS NOT NULL),
    CONSTRAINT ck_contratos__fin_prevista_no_anterior
        CHECK (fecha_inicio IS NULL OR fecha_fin_prevista IS NULL OR fecha_fin_prevista >= fecha_inicio),
    CONSTRAINT ck_contratos__fin_real_no_anterior
        CHECK (fecha_inicio IS NULL OR fecha_fin_real IS NULL OR fecha_fin_real >= fecha_inicio)
);

-- 50. contrato_participantes
CREATE TABLE gapto.contrato_participantes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    contrato_entidad_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    rol varchar(30) NOT NULL,
    principal boolean NOT NULL DEFAULT false,
    vigente_desde date NOT NULL,
    vigente_hasta date,

    CONSTRAINT pk_contrato_participantes PRIMARY KEY (id),
    CONSTRAINT ck_contrato_participantes__rol
        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR')),
    CONSTRAINT ck_contrato_participantes__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);

-- 51. servicios
CREATE TABLE gapto.servicios (
    entidad_id uuid NOT NULL,
    tipo_servicio varchar(40) NOT NULL,
    categoria_default_id uuid,
    fecha_inicio date,
    fecha_fin_real date,
    notas text,

    CONSTRAINT pk_servicios PRIMARY KEY (entidad_id),
    CONSTRAINT ck_servicios__fin_no_anterior
        CHECK (fecha_inicio IS NULL OR fecha_fin_real IS NULL OR fecha_fin_real >= fecha_inicio)
);

-- 52. propiedad_servicios
CREATE TABLE gapto.propiedad_servicios (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    servicio_entidad_id uuid NOT NULL,
    propiedad_entidad_id uuid NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,

    CONSTRAINT pk_propiedad_servicios PRIMARY KEY (id),
    CONSTRAINT ck_propiedad_servicios__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);

-- 53. contrato_servicios
CREATE TABLE gapto.contrato_servicios (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    contrato_entidad_id uuid NOT NULL,
    servicio_entidad_id uuid NOT NULL,
    incluido_en_renta boolean NOT NULL DEFAULT false,
    repercutible boolean NOT NULL DEFAULT false,
    actor_repercusion_id uuid,
    porcentaje_repercutible numeric(7,4),
    vigente_desde date NOT NULL,
    vigente_hasta date,

    CONSTRAINT pk_contrato_servicios PRIMARY KEY (id),
    CONSTRAINT ck_contrato_servicios__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ck_contrato_servicios__renta_repercutible_excl
        CHECK (NOT (incluido_en_renta AND repercutible)),
    CONSTRAINT ck_contrato_servicios__repercusion_exige_datos
        CHECK (NOT repercutible OR (actor_repercusion_id IS NOT NULL AND porcentaje_repercutible IS NOT NULL)),
    CONSTRAINT ck_contrato_servicios__porcentaje
        CHECK (porcentaje_repercutible IS NULL OR (porcentaje_repercutible >= 0 AND porcentaje_repercutible <= 100))
);

-- 54. financiaciones
CREATE TABLE gapto.financiaciones (
    entidad_id uuid NOT NULL,
    tipo_financiacion varchar(40) NOT NULL,
    financiador_actor_id uuid,
    moneda varchar(3) NOT NULL,
    capital_original_contratado numeric(18,4),
    saldo_principal_apertura numeric(18,4),
    fecha_inicio_seguimiento date,
    fecha_inicio date,
    fecha_vencimiento_final_prevista date,
    fecha_cierre_real date,
    estado varchar(20) NOT NULL DEFAULT 'ACTIVA',
    motivo_cierre varchar(30),
    notas text,

    CONSTRAINT pk_financiaciones PRIMARY KEY (entidad_id),
    CONSTRAINT ck_financiaciones__tipo
        CHECK (tipo_financiacion IN ('HIPOTECA','PRESTAMO','COMPRA_FINANCIADA','OTRA')),
    CONSTRAINT ck_financiaciones__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_financiaciones__saldo_principal
        CHECK (saldo_principal_apertura IS NULL OR saldo_principal_apertura >= 0),
    CONSTRAINT ck_financiaciones__apertura_pareja
        CHECK ((saldo_principal_apertura IS NULL) = (fecha_inicio_seguimiento IS NULL)),
    CONSTRAINT ck_financiaciones__estado
        CHECK (estado IN ('ACTIVA','CERRADA')),
    CONSTRAINT ck_financiaciones__motivo_cierre
        CHECK (motivo_cierre IS NULL OR motivo_cierre IN ('LIQUIDADA','CANCELADA','REFINANCIADA','OTRO')),
    CONSTRAINT ck_financiaciones__cierre_deshabilita
        CHECK (
            (estado = 'ACTIVA' AND motivo_cierre IS NULL AND fecha_cierre_real IS NULL)
            OR estado = 'CERRADA'
        )
);

-- 55. financiacion_condiciones_versiones
CREATE TABLE gapto.financiacion_condiciones_versiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    financiacion_entidad_id uuid NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,
    motivo_version varchar(40) NOT NULL,
    hecho_causa_id uuid,
    modo_recalculo_amortizacion varchar(30),
    tipo_interes varchar(20) NOT NULL,
    tasa_anual_pct numeric(9,6),
    indice_referencia varchar(40),
    diferencial_pct numeric(9,6),
    sistema_amortizacion varchar(30) NOT NULL,
    periodicidad varchar(20) NOT NULL,
    intervalo smallint DEFAULT 1,
    importe_cuota_referencia numeric(18,4),
    numero_cuotas_referencia integer,
    comisiones_periodicas numeric(18,4),

    CONSTRAINT pk_financiacion_condiciones_versiones PRIMARY KEY (id),
    CONSTRAINT ck_financiacion_condiciones_versiones__vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ck_financiacion_condiciones_versiones__motivo_version
        CHECK (motivo_version IN ('ALTA','CAMBIO_CONDICIONES','AMORTIZACION_ANTICIPADA','OTRO')),
    CONSTRAINT ck_financiacion_condiciones_versiones__modo_recalculo
        CHECK (modo_recalculo_amortizacion IS NULL OR modo_recalculo_amortizacion IN ('REDUCIR_PLAZO','REDUCIR_CUOTA','OTRO')),
    CONSTRAINT ck_financiacion_condiciones_versiones__modo_solo_amortizacion
        CHECK (modo_recalculo_amortizacion IS NULL OR motivo_version = 'AMORTIZACION_ANTICIPADA'),
    CONSTRAINT ck_financiacion_condiciones_versiones__tipo_interes
        CHECK (tipo_interes IN ('FIJO','VARIABLE','SIN_INTERES')),
    CONSTRAINT ck_financiacion_condiciones_versiones__sistema_amortizacion
        CHECK (sistema_amortizacion IN ('FRANCES','LINEAL','MANUAL','SIN_INTERES','OTRO')),
    CONSTRAINT ck_financiacion_condiciones_versiones__periodicidad
        CHECK (periodicidad IN ('DIARIA','SEMANAL','MENSUAL','ANUAL')),
    CONSTRAINT ck_financiacion_condiciones_versiones__intervalo
        CHECK (intervalo IS NULL OR intervalo >= 1),
    CONSTRAINT ck_financiacion_condiciones_versiones__importe_cuota
        CHECK (importe_cuota_referencia IS NULL OR importe_cuota_referencia > 0),
    CONSTRAINT ck_financiacion_condiciones_versiones__numero_cuotas
        CHECK (numero_cuotas_referencia IS NULL OR numero_cuotas_referencia > 0),
    CONSTRAINT ck_financiacion_condiciones_versiones__comisiones
        CHECK (comisiones_periodicas IS NULL OR comisiones_periodicas >= 0)
);

-- 56. financiacion_cuotas
CREATE TABLE gapto.financiacion_cuotas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    financiacion_entidad_id uuid NOT NULL,
    condicion_version_id uuid,
    numero_cuota integer NOT NULL,
    fecha_vencimiento date NOT NULL,
    capital_previsto numeric(18,4),
    interes_previsto numeric(18,4),
    comisiones_previstas numeric(18,4),
    importe_total_previsto numeric(18,4) NOT NULL,
    prevision_id uuid,

    CONSTRAINT pk_financiacion_cuotas PRIMARY KEY (id),
    CONSTRAINT ck_financiacion_cuotas__numero_cuota
        CHECK (numero_cuota > 0),
    CONSTRAINT ck_financiacion_cuotas__capital
        CHECK (capital_previsto IS NULL OR capital_previsto >= 0),
    CONSTRAINT ck_financiacion_cuotas__interes
        CHECK (interes_previsto IS NULL OR interes_previsto >= 0),
    CONSTRAINT ck_financiacion_cuotas__comisiones
        CHECK (comisiones_previstas IS NULL OR comisiones_previstas >= 0),
    CONSTRAINT ck_financiacion_cuotas__importe_total
        CHECK (importe_total_previsto > 0)
);

-- 57. inversiones
CREATE TABLE gapto.inversiones (
    entidad_id uuid NOT NULL,
    inversion_padre_entidad_id uuid,
    rol_estructura varchar(20) NOT NULL,
    tipo_producto varchar(40) NOT NULL,
    tercero_gestor_id uuid,
    moneda varchar(3) NOT NULL,
    fecha_inicio date,
    fecha_fin_real date,
    plazo_real_meses integer,
    capital_invertido_apertura numeric(18,4),
    fecha_capital_invertido_apertura date,
    estado varchar(20) NOT NULL DEFAULT 'ACTIVA',
    motivo_cierre varchar(30),
    notas text,

    CONSTRAINT pk_inversiones PRIMARY KEY (entidad_id),
    CONSTRAINT ck_inversiones__no_self_padre
        CHECK (inversion_padre_entidad_id IS NULL OR inversion_padre_entidad_id <> entidad_id),
    CONSTRAINT ck_inversiones__rol_estructura
        CHECK (rol_estructura IN ('CONTENEDOR','POSICION')),
    CONSTRAINT ck_inversiones__tipo_producto
        CHECK (tipo_producto IN ('PLAN','CARTERA_GESTIONADA','FONDO','ACCION','DEPOSITO','OTRO')),
    CONSTRAINT ck_inversiones__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_inversiones__fin_no_anterior
        CHECK (fecha_inicio IS NULL OR fecha_fin_real IS NULL OR fecha_fin_real >= fecha_inicio),
    CONSTRAINT ck_inversiones__plazo_real
        CHECK (plazo_real_meses IS NULL OR plazo_real_meses > 0),
    CONSTRAINT ck_inversiones__capital_apertura
        CHECK (capital_invertido_apertura IS NULL OR capital_invertido_apertura >= 0),
    CONSTRAINT ck_inversiones__capital_apertura_pareja
        CHECK ((capital_invertido_apertura IS NULL) = (fecha_capital_invertido_apertura IS NULL)),
    CONSTRAINT ck_inversiones__estado
        CHECK (estado IN ('ACTIVA','CERRADA')),
    CONSTRAINT ck_inversiones__motivo_cierre
        CHECK (motivo_cierre IS NULL OR motivo_cierre IN ('LIQUIDADA','VENDIDA','VENCIDA','PERDIDA_TOTAL','CANCELADA','OTRO')),
    CONSTRAINT ck_inversiones__cierre_deshabilita
        CHECK (
            (estado = 'ACTIVA' AND motivo_cierre IS NULL)
            OR estado = 'CERRADA'
        )
);

-- 58. inversion_objetivos_versiones
CREATE TABLE gapto.inversion_objetivos_versiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    inversion_entidad_id uuid NOT NULL,
    vigente_desde date,
    vigente_hasta date,
    aporte_objetivo_total numeric(18,4),
    valor_objetivo_total numeric(18,4),
    roi_objetivo_pct numeric(9,4),
    moic_objetivo numeric(12,6),
    irr_objetivo_pct numeric(9,4),
    plazo_objetivo_meses integer,
    fecha_objetivo_salida date,
    notas text,

    CONSTRAINT pk_inversion_objetivos_versiones PRIMARY KEY (id),
    CONSTRAINT ck_inversion_objetivos_versiones__vigencia
        CHECK (vigente_desde IS NULL OR vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ck_inversion_objetivos_versiones__aporte
        CHECK (aporte_objetivo_total IS NULL OR aporte_objetivo_total >= 0),
    CONSTRAINT ck_inversion_objetivos_versiones__valor
        CHECK (valor_objetivo_total IS NULL OR valor_objetivo_total >= 0),
    CONSTRAINT ck_inversion_objetivos_versiones__moic
        CHECK (moic_objetivo IS NULL OR moic_objetivo >= 0),
    CONSTRAINT ck_inversion_objetivos_versiones__plazo
        CHECK (plazo_objetivo_meses IS NULL OR plazo_objetivo_meses > 0),
    CONSTRAINT ck_inversion_objetivos_versiones__al_menos_un_objetivo
        CHECK (
            aporte_objetivo_total IS NOT NULL OR valor_objetivo_total IS NOT NULL
            OR roi_objetivo_pct IS NOT NULL OR moic_objetivo IS NOT NULL
            OR irr_objetivo_pct IS NOT NULL OR plazo_objetivo_meses IS NOT NULL
            OR fecha_objetivo_salida IS NOT NULL
        )
);

-- 59. inversion_valoraciones
CREATE TABLE gapto.inversion_valoraciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    inversion_entidad_id uuid NOT NULL,
    fecha_valoracion date,
    tipo_valoracion varchar(30) NOT NULL,
    alcance_valoracion varchar(20) NOT NULL,
    valor_total numeric(18,4) NOT NULL,
    fuente varchar(30) NOT NULL,
    notas text,

    CONSTRAINT pk_inversion_valoraciones PRIMARY KEY (id),
    CONSTRAINT ck_inversion_valoraciones__tipo
        CHECK (tipo_valoracion IN ('SEGUIMIENTO','CIERRE','OTRO')),
    CONSTRAINT ck_inversion_valoraciones__alcance
        CHECK (alcance_valoracion IN ('DIRECTA','CONSOLIDADA')),
    CONSTRAINT ck_inversion_valoraciones__valor_total
        CHECK (valor_total >= 0),
    CONSTRAINT ck_inversion_valoraciones__fuente
        CHECK (fuente IN ('MANUAL','MERCADO','GESTOR','IMPORTACION'))
);

COMMENT ON TABLE gapto.derechos_obligaciones_financieras IS 'F03-01-B05 tabla 46: posición financiera de derecho de cobro u obligación de pago.';
COMMENT ON TABLE gapto.propiedades IS 'F03-01-B05 tabla 47: datos físicos/legales del activo inmobiliario.';
COMMENT ON TABLE gapto.propiedad_valoraciones IS 'F03-01-B05 tabla 48: histórico de valor bruto de propiedades.';
COMMENT ON TABLE gapto.contratos IS 'F03-01-B05 tabla 49: relación jurídica/operativa vinculada a una propiedad.';
COMMENT ON TABLE gapto.contrato_participantes IS 'F03-01-B05 tabla 50: actores que intervienen jurídicamente en el contrato.';
COMMENT ON TABLE gapto.servicios IS 'F03-01-B05 tabla 51: servicio, suministro o suscripción como entidad funcional.';
COMMENT ON TABLE gapto.propiedad_servicios IS 'F03-01-B05 tabla 52: vinculación temporal entre un servicio y una propiedad.';
COMMENT ON TABLE gapto.contrato_servicios IS 'F03-01-B05 tabla 53: tratamiento contractual de un servicio dentro de un contrato.';
COMMENT ON TABLE gapto.financiaciones IS 'F03-01-B05 tabla 54: deuda contractual formal no representada por una cuenta.';
COMMENT ON TABLE gapto.financiacion_condiciones_versiones IS 'F03-01-B05 tabla 55: condiciones y plan aplicable versionados de una financiación.';
COMMENT ON TABLE gapto.financiacion_cuotas IS 'F03-01-B05 tabla 56: calendario financiero previsto de una financiación.';
COMMENT ON TABLE gapto.inversiones IS 'F03-01-B05 tabla 57: entidad de inversión, contenedor o posición.';
COMMENT ON TABLE gapto.inversion_objetivos_versiones IS 'F03-01-B05 tabla 58: condiciones y objetivos versionables de una inversión.';
COMMENT ON TABLE gapto.inversion_valoraciones IS 'F03-01-B05 tabla 59: histórico de valoración de inversión.';

RESET ROLE;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b05_tables integer;
    v_wrong_owner integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    SELECT count(*) INTO v_b05_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'derechos_obligaciones_financieras','propiedades','propiedad_valoraciones',
           'contratos','contrato_participantes','servicios','propiedad_servicios',
           'contrato_servicios','financiaciones','financiacion_condiciones_versiones',
           'financiacion_cuotas','inversiones','inversion_objetivos_versiones',
           'inversion_valoraciones'
       );

    SELECT count(*) INTO v_wrong_owner
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'derechos_obligaciones_financieras','propiedades','propiedad_valoraciones',
           'contratos','contrato_participantes','servicios','propiedad_servicios',
           'contrato_servicios','financiaciones','financiacion_condiciones_versiones',
           'financiacion_cuotas','inversiones','inversion_objetivos_versiones',
           'inversion_valoraciones'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_total_tables <> 59 OR v_b05_tables <> 14 OR v_wrong_owner <> 0 THEN
        RAISE EXCEPTION 'F03-01-B05 POSTCHECK: total=%, b05=%, wrong_owner=%; esperado=59,14,0', v_total_tables, v_b05_tables, v_wrong_owner;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
