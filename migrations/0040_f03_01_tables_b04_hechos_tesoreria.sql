-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0040_f03_01_tables_b04_hechos_tesoreria.sql
-- Ruta: migrations/0040_f03_01_tables_b04_hechos_tesoreria.sql
-- Descripción: Materializa las tablas 33..45 del baseline físico:
--              núcleo de hechos financieros, efectos, atribuciones,
--              terceros/entidades/participantes/aportaciones del hecho,
--              tesorería, conciliación, transferencias, conciliación
--              previsión-hecho, magnitudes y relaciones entre hechos.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b04_tables integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION 'F03-01-B04 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 32 THEN
        RAISE EXCEPTION 'F03-01-B04 PRECHECK: esperadas exactamente 32 tablas previas B01+B02+B03; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_b04_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind IN ('r','p')
       AND c.relname IN (
           'hechos_financieros','hecho_efectos','efecto_atribuciones','hecho_terceros',
           'hecho_entidades','hecho_participantes','hecho_aportaciones_pago',
           'movimientos_tesoreria','hecho_movimientos_tesoreria','transferencias',
           'prevision_hechos','hecho_magnitudes','hecho_relaciones'
       );

    IF v_b04_tables <> 0 THEN
        RAISE EXCEPTION 'F03-01-B04 TABLE DRIFT: existen % tablas reservadas del bloque', v_b04_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 33. hechos_financieros
CREATE TABLE gapto.hechos_financieros (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tipo_hecho_id uuid NOT NULL,
    fecha_hecho date NOT NULL,
    concepto varchar(200),
    importe_total numeric(18,4),
    numero_participantes_total smallint,
    moneda varchar(3) NOT NULL,
    localidad_id uuid,
    estado_localizacion varchar(20) NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'ACTIVO',
    anulado_at timestamptz,
    motivo_anulacion text,
    presupuestable boolean NOT NULL,
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_hechos_financieros PRIMARY KEY (id),
    CONSTRAINT ck_hechos_financieros__importe_total
        CHECK (importe_total IS NULL OR importe_total >= 0),
    CONSTRAINT ck_hechos_financieros__participantes_total
        CHECK (numero_participantes_total IS NULL OR numero_participantes_total >= 0),
    CONSTRAINT ck_hechos_financieros__moneda_formato
        CHECK (moneda ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_hechos_financieros__estado_localizacion
        CHECK (estado_localizacion IN ('CONOCIDA','DESCONOCIDA','NO_APLICA')),
    CONSTRAINT ck_hechos_financieros__localidad_coherente
        CHECK (
            (estado_localizacion = 'CONOCIDA' AND localidad_id IS NOT NULL)
            OR (estado_localizacion IN ('DESCONOCIDA','NO_APLICA') AND localidad_id IS NULL)
        ),
    CONSTRAINT ck_hechos_financieros__estado
        CHECK (estado IN ('ACTIVO','ANULADO')),
    CONSTRAINT ck_hechos_financieros__anulado_coherente
        CHECK (
            (estado = 'ACTIVO' AND anulado_at IS NULL)
            OR (estado = 'ANULADO' AND anulado_at IS NOT NULL)
        )
);

-- 34. hecho_efectos
CREATE TABLE gapto.hecho_efectos (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    tipo_efecto varchar(30) NOT NULL,
    importe_delta numeric(18,4) NOT NULL,
    categoria_id uuid,
    estado_atribucion varchar(20) NOT NULL DEFAULT 'COMPLETA',
    descripcion varchar(200),

    CONSTRAINT pk_hecho_efectos PRIMARY KEY (id),
    CONSTRAINT ck_hecho_efectos__tipo_efecto
        CHECK (tipo_efecto IN ('GASTO','INGRESO','DEUDA','DERECHO_COBRO','INVERSION','VALOR_ACTIVO')),
    CONSTRAINT ck_hecho_efectos__importe_delta
        CHECK (importe_delta <> 0),
    CONSTRAINT ck_hecho_efectos__estado_atribucion
        CHECK (estado_atribucion IN ('COMPLETA','PARCIAL','NO_DISPONIBLE'))
);

-- 35. efecto_atribuciones
CREATE TABLE gapto.efecto_atribuciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    efecto_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    importe_atribuido numeric(18,4) NOT NULL,
    porcentaje_aplicado numeric(7,4),
    criterio_atribucion varchar(40) NOT NULL,

    CONSTRAINT pk_efecto_atribuciones PRIMARY KEY (id),
    CONSTRAINT ck_efecto_atribuciones__porcentaje
        CHECK (porcentaje_aplicado IS NULL OR (porcentaje_aplicado >= 0 AND porcentaje_aplicado <= 100)),
    CONSTRAINT ck_efecto_atribuciones__criterio
        CHECK (criterio_atribucion IN ('MANUAL','PARTES_IGUALES','PARTICIPACION_ENTIDAD','REGLA','SEGUN_PAGO'))
);

-- 36. hecho_terceros
CREATE TABLE gapto.hecho_terceros (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    tercero_id uuid NOT NULL,
    rol_en_hecho varchar(50) NOT NULL,
    principal boolean NOT NULL DEFAULT false,

    CONSTRAINT pk_hecho_terceros PRIMARY KEY (id),
    CONSTRAINT ck_hecho_terceros__rol
        CHECK (rol_en_hecho IN ('VENDEDOR','EMPLEADOR','FINANCIADOR','REEMBOLSADOR','BENEFICIARIO','OTRO'))
);

-- 37. hecho_entidades
CREATE TABLE gapto.hecho_entidades (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    efecto_id uuid,
    entidad_id uuid NOT NULL,
    tipo_relacion varchar(50) NOT NULL,
    principal boolean NOT NULL DEFAULT false,

    CONSTRAINT pk_hecho_entidades PRIMARY KEY (id),
    CONSTRAINT ck_hecho_entidades__tipo_relacion
        CHECK (tipo_relacion IN ('AFECTA_A','GENERADO_POR','REPERCUTIBLE_A','RELACIONADO_CON'))
);

-- 38. hecho_participantes
CREATE TABLE gapto.hecho_participantes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    rol varchar(40) NOT NULL,

    CONSTRAINT pk_hecho_participantes PRIMARY KEY (id)
);

-- 39. hecho_aportaciones_pago
CREATE TABLE gapto.hecho_aportaciones_pago (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    actor_id uuid,
    importe numeric(18,4) NOT NULL,
    porcentaje_aplicado numeric(7,4),
    criterio_aportacion varchar(40) NOT NULL,
    medio_pago_codigo varchar(40),
    hecho_movimiento_tesoreria_id uuid,

    CONSTRAINT pk_hecho_aportaciones_pago PRIMARY KEY (id),
    CONSTRAINT ck_hecho_aportaciones_pago__importe
        CHECK (importe > 0),
    CONSTRAINT ck_hecho_aportaciones_pago__porcentaje
        CHECK (porcentaje_aplicado IS NULL OR (porcentaje_aplicado >= 0 AND porcentaje_aplicado <= 100)),
    CONSTRAINT ck_hecho_aportaciones_pago__criterio
        CHECK (criterio_aportacion IN ('PARTICIPACION_CUENTA','MANUAL','REGLA','EXTERNA'))
);

-- 40. movimientos_tesoreria
CREATE TABLE gapto.movimientos_tesoreria (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    cuenta_id uuid NOT NULL,
    fecha_movimiento date NOT NULL,
    importe numeric(18,4) NOT NULL,
    descripcion varchar(200),
    confirmado_at timestamptz NOT NULL,
    clase_movimiento varchar(30) NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'ACTIVO',
    anulado_at timestamptz,
    motivo_anulacion text,
    reversion_de_movimiento_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_movimientos_tesoreria PRIMARY KEY (id),
    CONSTRAINT ck_movimientos_tesoreria__importe
        CHECK (importe <> 0),
    CONSTRAINT ck_movimientos_tesoreria__clase
        CHECK (clase_movimiento IN ('OPERACION','AJUSTE_SALDO')),
    CONSTRAINT ck_movimientos_tesoreria__estado
        CHECK (estado IN ('ACTIVO','ANULADO')),
    CONSTRAINT ck_movimientos_tesoreria__anulado_coherente
        CHECK (
            (estado = 'ACTIVO' AND anulado_at IS NULL)
            OR (estado = 'ANULADO' AND anulado_at IS NOT NULL)
        ),
    CONSTRAINT ck_movimientos_tesoreria__reversion_no_self
        CHECK (reversion_de_movimiento_id IS NULL OR reversion_de_movimiento_id <> id)
);

-- 41. hecho_movimientos_tesoreria
CREATE TABLE gapto.hecho_movimientos_tesoreria (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    movimiento_tesoreria_id uuid NOT NULL,
    importe_asignado numeric(18,4) NOT NULL,

    CONSTRAINT pk_hecho_movimientos_tesoreria PRIMARY KEY (id),
    CONSTRAINT ck_hecho_movimientos_tesoreria__importe
        CHECK (importe_asignado <> 0)
);

-- 42. transferencias
CREATE TABLE gapto.transferencias (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    movimiento_salida_id uuid NOT NULL,
    movimiento_entrada_id uuid NOT NULL,
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_transferencias PRIMARY KEY (id)
);

-- 43. prevision_hechos
CREATE TABLE gapto.prevision_hechos (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    prevision_id uuid NOT NULL,
    hecho_id uuid NOT NULL,
    importe_asignado numeric(18,4) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_prevision_hechos PRIMARY KEY (id),
    CONSTRAINT ck_prevision_hechos__importe
        CHECK (importe_asignado > 0)
);

-- 44. hecho_magnitudes
CREATE TABLE gapto.hecho_magnitudes (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    magnitud_id uuid NOT NULL,
    valor numeric(18,6) NOT NULL,
    unidad varchar(20) NOT NULL,

    CONSTRAINT pk_hecho_magnitudes PRIMARY KEY (id)
);

-- 45. hecho_relaciones
CREATE TABLE gapto.hecho_relaciones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_origen_id uuid NOT NULL,
    hecho_destino_id uuid NOT NULL,
    tipo_relacion varchar(50) NOT NULL,
    importe_relacionado numeric(18,4),
    notas text,

    CONSTRAINT pk_hecho_relaciones PRIMARY KEY (id),
    CONSTRAINT ck_hecho_relaciones__no_self
        CHECK (hecho_origen_id <> hecho_destino_id),
    CONSTRAINT ck_hecho_relaciones__tipo
        CHECK (tipo_relacion IN ('DEVOLUCION_DE','REEMBOLSO_DE','CORRIGE_A','REVERSA_A','REPERCUSION_DE','PARTE_DE')),
    CONSTRAINT ck_hecho_relaciones__importe_relacionado
        CHECK (importe_relacionado IS NULL OR importe_relacionado > 0)
);

COMMENT ON TABLE gapto.hechos_financieros IS 'F03-01-B04 tabla 33: acontecimiento real, importe bruto y contexto.';
COMMENT ON TABLE gapto.hecho_efectos IS 'F03-01-B04 tabla 34: consecuencias económicas de un hecho.';
COMMENT ON TABLE gapto.efecto_atribuciones IS 'F03-01-B04 tabla 35: atribución económica materializada por actor de cada efecto.';
COMMENT ON TABLE gapto.hecho_terceros IS 'F03-01-B04 tabla 36: terceros que intervienen comercial o causalmente en el hecho.';
COMMENT ON TABLE gapto.hecho_entidades IS 'F03-01-B04 tabla 37: relación autoritativa entre un hecho/efecto y entidades de dominio.';
COMMENT ON TABLE gapto.hecho_participantes IS 'F03-01-B04 tabla 38: actores implicados en el acontecimiento sin reparto económico.';
COMMENT ON TABLE gapto.hecho_aportaciones_pago IS 'F03-01-B04 tabla 39: quién financió realmente el pago/cobro del hecho.';
COMMENT ON TABLE gapto.movimientos_tesoreria IS 'F03-01-B04 tabla 40: entradas/salidas reales confirmadas, fuente autoritativa del ledger.';
COMMENT ON TABLE gapto.hecho_movimientos_tesoreria IS 'F03-01-B04 tabla 41: conciliación N:N entre hechos y movimientos reales.';
COMMENT ON TABLE gapto.transferencias IS 'F03-01-B04 tabla 42: asociación entre dos movimientos reales de cuentas distintas.';
COMMENT ON TABLE gapto.prevision_hechos IS 'F03-01-B04 tabla 43: conciliación N:N entre expectativa y realidad.';
COMMENT ON TABLE gapto.hecho_magnitudes IS 'F03-01-B04 tabla 44: valores de magnitudes del hecho.';
COMMENT ON TABLE gapto.hecho_relaciones IS 'F03-01-B04 tabla 45: relaciones semánticas controladas entre hechos reales.';

RESET ROLE;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b04_tables integer;
    v_wrong_owner integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    SELECT count(*) INTO v_b04_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'hechos_financieros','hecho_efectos','efecto_atribuciones','hecho_terceros',
           'hecho_entidades','hecho_participantes','hecho_aportaciones_pago',
           'movimientos_tesoreria','hecho_movimientos_tesoreria','transferencias',
           'prevision_hechos','hecho_magnitudes','hecho_relaciones'
       );

    SELECT count(*) INTO v_wrong_owner
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'hechos_financieros','hecho_efectos','efecto_atribuciones','hecho_terceros',
           'hecho_entidades','hecho_participantes','hecho_aportaciones_pago',
           'movimientos_tesoreria','hecho_movimientos_tesoreria','transferencias',
           'prevision_hechos','hecho_magnitudes','hecho_relaciones'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_total_tables <> 45 OR v_b04_tables <> 13 OR v_wrong_owner <> 0 THEN
        RAISE EXCEPTION 'F03-01-B04 POSTCHECK: total=%, b04=%, wrong_owner=%; esperado=45,13,0', v_total_tables, v_b04_tables, v_wrong_owner;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
