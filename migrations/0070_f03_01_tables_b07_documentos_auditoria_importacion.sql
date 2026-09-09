-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0070_f03_01_tables_b07_documentos_auditoria_importacion.sql
-- Ruta: migrations/0070_f03_01_tables_b07_documentos_auditoria_importacion.sql
-- Descripción: Materializa las tablas 68..79 del baseline físico:
--              documentos y sus vínculos, etiquetas, auditoría
--              append-only, asignaciones de inversión, alcances de
--              líneas presupuestarias, trazabilidad de importación
--              (fuentes, registros origen, mapeos), subtipo persona
--              de tercero y cláusula de revisión de renta. Cierra
--              F03-01 con 79/79 tablas materializadas.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b07_tables integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE n.nspname = 'gapto'
           AND pg_catalog.pg_get_userbyid(n.nspowner) = 'gapto_owner'
    ) THEN
        RAISE EXCEPTION 'F03-01-B07 PRECHECK: schema gapto ausente o con owner distinto de gapto_owner';
    END IF;

    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    IF v_total_tables <> 67 THEN
        RAISE EXCEPTION 'F03-01-B07 PRECHECK: esperadas exactamente 67 tablas previas; encontradas=%', v_total_tables;
    END IF;

    SELECT count(*) INTO v_b07_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind IN ('r','p')
       AND c.relname IN (
           'documentos','documento_vinculos','etiquetas','hecho_etiquetas','auditoria',
           'inversion_asignaciones_efecto','presupuesto_linea_alcances','fuentes_importacion',
           'registros_origen_importacion','mapeos_importacion','tercero_personas',
           'contrato_revision_renta_versiones'
       );

    IF v_b07_tables <> 0 THEN
        RAISE EXCEPTION 'F03-01-B07 TABLE DRIFT: existen % tablas reservadas del bloque', v_b07_tables;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

SET LOCAL TIME ZONE 'UTC';
SET ROLE gapto_owner;

-- 68. documentos
CREATE TABLE gapto.documentos (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tipo varchar(30) NOT NULL,
    titulo varchar(255),
    nombre_archivo_original varchar(255) NOT NULL,
    storage_key varchar(500),
    mime_type varchar(100) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 char(64),
    fecha_documento date,
    estado_archivo varchar(20) NOT NULL DEFAULT 'DISPONIBLE',
    eliminado_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_documentos PRIMARY KEY (id),
    CONSTRAINT ck_documentos__tipo
        CHECK (tipo IN ('TICKET','FACTURA','CONTRATO','JUSTIFICANTE','EXTRACTO','FOTO','OTRO')),
    CONSTRAINT ck_documentos__size_bytes
        CHECK (size_bytes >= 0),
    CONSTRAINT ck_documentos__sha256_formato
        CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_documentos__estado_archivo
        CHECK (estado_archivo IN ('DISPONIBLE','ELIMINADO')),
    CONSTRAINT ck_documentos__estado_coherente
        CHECK (
            (estado_archivo = 'DISPONIBLE' AND storage_key IS NOT NULL AND eliminado_at IS NULL)
            OR (estado_archivo = 'ELIMINADO' AND eliminado_at IS NOT NULL)
        )
);

-- 69. documento_vinculos
CREATE TABLE gapto.documento_vinculos (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    documento_id uuid NOT NULL,
    hecho_id uuid,
    entidad_id uuid,
    tercero_id uuid,
    cuenta_id uuid,
    rol_vinculo varchar(20) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_documento_vinculos PRIMARY KEY (id),
    CONSTRAINT ck_documento_vinculos__rol
        CHECK (rol_vinculo IN ('PRINCIPAL','ANEXO','EVIDENCIA','OTRO')),
    CONSTRAINT ck_documento_vinculos__un_solo_destino
        CHECK (
            (CASE WHEN hecho_id IS NOT NULL THEN 1 ELSE 0 END
           + CASE WHEN entidad_id IS NOT NULL THEN 1 ELSE 0 END
           + CASE WHEN tercero_id IS NOT NULL THEN 1 ELSE 0 END
           + CASE WHEN cuenta_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        )
);

-- 70. etiquetas
CREATE TABLE gapto.etiquetas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    nombre varchar(60) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_etiquetas PRIMARY KEY (id),
    CONSTRAINT ck_etiquetas__nombre_no_blanco
        CHECK (nombre ~ '[^[:space:]]')
);

-- 71. hecho_etiquetas
CREATE TABLE gapto.hecho_etiquetas (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    hecho_id uuid NOT NULL,
    etiqueta_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_hecho_etiquetas PRIMARY KEY (id)
);

-- 72. auditoria
CREATE TABLE gapto.auditoria (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    actor_tipo varchar(20) NOT NULL,
    actor_user_id uuid,
    tabla varchar(100) NOT NULL,
    registro_id uuid NOT NULL,
    accion varchar(30) NOT NULL,
    datos_antes jsonb,
    datos_despues jsonb,
    motivo text,
    request_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_auditoria PRIMARY KEY (id),
    CONSTRAINT ck_auditoria__actor_tipo
        CHECK (actor_tipo IN ('USUARIO','SISTEMA')),
    CONSTRAINT ck_auditoria__actor_coherente
        CHECK (
            (actor_tipo = 'USUARIO' AND actor_user_id IS NOT NULL)
            OR (actor_tipo = 'SISTEMA' AND actor_user_id IS NULL)
        ),
    CONSTRAINT ck_auditoria__tabla_no_blanco
        CHECK (tabla ~ '[^[:space:]]'),
    CONSTRAINT ck_auditoria__accion
        CHECK (accion IN ('CREAR','ACTUALIZAR','ELIMINAR','ANULAR','REVERTIR','CERRAR','REABRIR'))
);

-- 73. inversion_asignaciones_efecto
CREATE TABLE gapto.inversion_asignaciones_efecto (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    efecto_inversion_id uuid NOT NULL,
    inversion_entidad_id uuid NOT NULL,
    importe_asignado numeric(18,4) NOT NULL,
    porcentaje_aplicado numeric(7,4),
    notas text,

    CONSTRAINT pk_inversion_asignaciones_efecto PRIMARY KEY (id),
    CONSTRAINT ck_inversion_asignaciones_efecto__importe
        CHECK (importe_asignado <> 0),
    CONSTRAINT ck_inversion_asignaciones_efecto__porcentaje
        CHECK (porcentaje_aplicado IS NULL OR (porcentaje_aplicado > 0 AND porcentaje_aplicado <= 100))
);

-- 74. presupuesto_linea_alcances
CREATE TABLE gapto.presupuesto_linea_alcances (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    presupuesto_linea_id uuid NOT NULL,
    categoria_id uuid,
    entidad_id uuid,
    incluir_descendientes boolean NOT NULL DEFAULT true,

    CONSTRAINT pk_presupuesto_linea_alcances PRIMARY KEY (id),
    CONSTRAINT ck_presupuesto_linea_alcances__al_menos_uno
        CHECK (categoria_id IS NOT NULL OR entidad_id IS NOT NULL)
);

-- 75. fuentes_importacion
CREATE TABLE gapto.fuentes_importacion (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    owner_user_id uuid NOT NULL,
    tipo_fuente varchar(30) NOT NULL,
    nombre_fuente varchar(255) NOT NULL,
    version_fuente varchar(80),
    pipeline_version varchar(80),
    sha256 char(64),
    documento_origen_id uuid,
    estado varchar(30) NOT NULL DEFAULT 'INVENTARIADA',
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notas text,
    row_version bigint NOT NULL DEFAULT 1,

    CONSTRAINT pk_fuentes_importacion PRIMARY KEY (id),
    CONSTRAINT ck_fuentes_importacion__tipo
        CHECK (tipo_fuente IN ('XLSX','CSV','DB','API','OTRO')),
    CONSTRAINT ck_fuentes_importacion__sha256_formato
        CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_fuentes_importacion__estado
        CHECK (estado IN ('INVENTARIADA','SIMULADA','IMPORTADA','RECONCILIADA','ERROR')),
    CONSTRAINT ck_fuentes_importacion__fechas
        CHECK (started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at)
);

-- 76. registros_origen_importacion
CREATE TABLE gapto.registros_origen_importacion (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    fuente_importacion_id uuid NOT NULL,
    contenedor_origen varchar(160) NOT NULL,
    clave_origen varchar(255),
    numero_fila_origen integer,
    datos_origen jsonb NOT NULL,
    datos_origen_texto text,
    sha256_registro char(64),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_registros_origen_importacion PRIMARY KEY (id),
    CONSTRAINT ck_registros_origen_importacion__contenedor_no_blanco
        CHECK (contenedor_origen ~ '[^[:space:]]'),
    CONSTRAINT ck_registros_origen_importacion__numero_fila
        CHECK (numero_fila_origen IS NULL OR numero_fila_origen > 0),
    CONSTRAINT ck_registros_origen_importacion__sha256_formato
        CHECK (sha256_registro IS NULL OR sha256_registro ~ '^[0-9a-f]{64}$')
);

-- 77. mapeos_importacion
CREATE TABLE gapto.mapeos_importacion (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    registro_origen_id uuid NOT NULL,
    tabla_destino varchar(100),
    registro_destino_id uuid,
    tipo_mapping varchar(30) NOT NULL,
    transformacion_codigo varchar(160),
    transformacion_version varchar(80),
    confianza varchar(20) NOT NULL,
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_mapeos_importacion PRIMARY KEY (id),
    CONSTRAINT ck_mapeos_importacion__tipo
        CHECK (tipo_mapping IN ('CREADO','VINCULADO','FUSIONADO','DIVIDIDO','OBSOLETO','IGNORADO')),
    CONSTRAINT ck_mapeos_importacion__destino_pareja
        CHECK ((tabla_destino IS NULL) = (registro_destino_id IS NULL)),
    CONSTRAINT ck_mapeos_importacion__destino_exigido
        CHECK (
            tipo_mapping NOT IN ('CREADO','VINCULADO','FUSIONADO','DIVIDIDO')
            OR (tabla_destino IS NOT NULL AND registro_destino_id IS NOT NULL)
        ),
    CONSTRAINT ck_mapeos_importacion__version_exige_codigo
        CHECK (transformacion_version IS NULL OR transformacion_codigo IS NOT NULL),
    CONSTRAINT ck_mapeos_importacion__confianza
        CHECK (confianza IN ('ALTA','MEDIA','BAJA','VALIDADA'))
);

-- 78. tercero_personas
CREATE TABLE gapto.tercero_personas (
    tercero_id uuid NOT NULL,
    fecha_nacimiento date,

    CONSTRAINT pk_tercero_personas PRIMARY KEY (tercero_id)
);

-- 79. contrato_revision_renta_versiones
CREATE TABLE gapto.contrato_revision_renta_versiones (
    id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    contrato_entidad_id uuid NOT NULL,
    vigente_desde date,
    vigente_hasta date,
    tipo_revision varchar(30) NOT NULL,
    indice_referencia varchar(80),
    periodicidad_meses smallint,
    fecha_primera_revision date,
    porcentaje_fijo numeric(9,4),
    notas text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_contrato_revision_renta_versiones PRIMARY KEY (id),
    CONSTRAINT ck_contrato_revision_renta_versiones__vigencia
        CHECK (vigente_desde IS NULL OR vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT ck_contrato_revision_renta_versiones__periodicidad
        CHECK (periodicidad_meses IS NULL OR periodicidad_meses > 0),
    CONSTRAINT ck_contrato_revision_renta_versiones__tipo
        CHECK (tipo_revision IN ('NINGUNA','IPC','INDICE','PORCENTAJE_FIJO','MANUAL','OTRO')),
    CONSTRAINT ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido
        CHECK (tipo_revision <> 'PORCENTAJE_FIJO' OR porcentaje_fijo IS NOT NULL),
    CONSTRAINT ck_contrato_revision_renta_versiones__ninguna_sin_parametros
        CHECK (
            tipo_revision <> 'NINGUNA'
            OR (indice_referencia IS NULL AND periodicidad_meses IS NULL AND porcentaje_fijo IS NULL)
        )
);

COMMENT ON TABLE gapto.documentos IS 'F03-01-B07 tabla 68: metadatos de archivos/evidencias documentales.';
COMMENT ON TABLE gapto.documento_vinculos IS 'F03-01-B07 tabla 69: relación documental generalizada hacia hecho/entidad/tercero/cuenta.';
COMMENT ON TABLE gapto.etiquetas IS 'F03-01-B07 tabla 70: etiquetas analíticas libres del usuario.';
COMMENT ON TABLE gapto.hecho_etiquetas IS 'F03-01-B07 tabla 71: N:N hecho-etiqueta.';
COMMENT ON TABLE gapto.auditoria IS 'F03-01-B07 tabla 72: registro append-only de cambios sobre datos 2027.';
COMMENT ON TABLE gapto.inversion_asignaciones_efecto IS 'F03-01-B07 tabla 73: desglose de un efecto inversion entre nodo y posiciones.';
COMMENT ON TABLE gapto.presupuesto_linea_alcances IS 'F03-01-B07 tabla 74: ambitos que alimentan una linea presupuestaria.';
COMMENT ON TABLE gapto.fuentes_importacion IS 'F03-01-B07 tabla 75: identifica una fuente/ejecucion de ingestion.';
COMMENT ON TABLE gapto.registros_origen_importacion IS 'F03-01-B07 tabla 76: registro fuente preservado antes de transformarlo.';
COMMENT ON TABLE gapto.mapeos_importacion IS 'F03-01-B07 tabla 77: relacion de procedencia entre registro origen y registro 2027.';
COMMENT ON TABLE gapto.tercero_personas IS 'F03-01-B07 tabla 78: subtipo 0..1 de terceros para datos especificos de personas.';
COMMENT ON TABLE gapto.contrato_revision_renta_versiones IS 'F03-01-B07 tabla 79: clausula contractual versionada de revision de renta.';

RESET ROLE;

DO $gapto$
DECLARE
    v_total_tables integer;
    v_b07_tables integer;
    v_wrong_owner integer;
BEGIN
    SELECT count(*) INTO v_total_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r';

    SELECT count(*) INTO v_b07_tables
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'documentos','documento_vinculos','etiquetas','hecho_etiquetas','auditoria',
           'inversion_asignaciones_efecto','presupuesto_linea_alcances','fuentes_importacion',
           'registros_origen_importacion','mapeos_importacion','tercero_personas',
           'contrato_revision_renta_versiones'
       );

    SELECT count(*) INTO v_wrong_owner
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'gapto' AND c.relkind = 'r'
       AND c.relname IN (
           'documentos','documento_vinculos','etiquetas','hecho_etiquetas','auditoria',
           'inversion_asignaciones_efecto','presupuesto_linea_alcances','fuentes_importacion',
           'registros_origen_importacion','mapeos_importacion','tercero_personas',
           'contrato_revision_renta_versiones'
       )
       AND pg_catalog.pg_get_userbyid(c.relowner) <> 'gapto_owner';

    IF v_total_tables <> 79 OR v_b07_tables <> 12 OR v_wrong_owner <> 0 THEN
        RAISE EXCEPTION 'F03-01-B07 POSTCHECK: total=%, b07=%, wrong_owner=%; esperado=79,12,0', v_total_tables, v_b07_tables, v_wrong_owner;
    END IF;
END
$gapto$ LANGUAGE plpgsql;

COMMIT;
