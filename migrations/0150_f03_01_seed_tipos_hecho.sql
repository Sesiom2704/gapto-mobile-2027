-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0150_f03_01_seed_tipos_hecho.sql
-- Descripcion: Seed de sistema para gapto.tipos_hecho, per F03-00-I
--   ("seeds de sistema versionados por codigo, con UUID fijos en el
--   fichero de seed pero codigo como identidad semantica").
--
--   Microdecision de cierre (esta sesion): tipos_hecho clasifica el
--   ARQUETIPO FUNCIONAL/OPERATIVO del hecho financiero -- que clase
--   de operacion es, que estructuras/capacidades puede usar, que
--   validaciones aplican -- y NO representa: procedencia (manual/
--   importado, se deriva de fuentes_importacion/registros_origen_
--   importacion/mapeos_importacion), recurrencia (se deriva de la
--   cadena regla_financiera -> prevision -> hecho), categoria
--   economica (categorias_financieras), medio de pago, ni estado.
--
--   Descartados del candidato RUN06 (8 valores) tras contrastar con
--   Migration_V3.md y con la estructura fisica ya materializada:
--   - SALDO_APERTURA: redundante con la columna estructural
--     `saldo_apertura` ya existente en cuentas, financiaciones y
--     derechos_obligaciones_financieras. No es un acontecimiento,
--     es un stock inicial fijado una vez en el dominio.
--   - AJUSTE_SALDO: evidencia real en V3 (58 ajustes manuales), pero
--     ya resuelto en F02 como movimientos_tesoreria.clase_movimiento
--     IN ('OPERACION','AJUSTE_SALDO') -- verificado que el CHECK
--     fisico ya admite ambos valores, sin requerir tipos_hecho.
--
--   Anadido: GENERACION_DERECHO_OBLIGACION, para el origen puro de
--   una posicion frente a un tercero (hecho_efectos.tipo_efecto IN
--   ('DEUDA','DERECHO_COBRO')) sin financiacion formal de por medio
--   -- casos reales: prestamo coche Isa, derecho Tania/SHEIN.
--
--   Precision documentada sobre REEMBOLSO: es el arquetipo (efecto
--   DERECHO_COBRO/OBLIGACION negativo + tesoreria, sin gasto/ingreso).
--   hecho_relaciones.tipo_relacion='REEMBOLSO_DE' es el enlace OPCIONAL
--   de trazabilidad al hecho origen concreto cuando se conoce; no son
--   la misma cosa y ambos coexisten sin redundancia.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM gapto.tipos_hecho;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'PRECHECK: gapto.tipos_hecho ya contiene % filas; se esperaba vacio', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

INSERT INTO gapto.tipos_hecho (id, codigo, nombre, enabled) VALUES
    ('b9c7573f-fa72-54a1-8b2d-b1c189f32533', 'GASTO',                         'Gasto',                                    true),
    ('bfdad2e0-2d2e-5850-b73a-1d2ecd8eb4c4', 'INGRESO',                       'Ingreso',                                  true),
    ('7ba5c0c4-ccd9-557c-838a-9122e96634d6', 'TRANSFERENCIA',                 'Transferencia entre cuentas propias',     true),
    ('7c20e19e-8c62-5df7-b11b-17d15eb4c76c', 'COMPRA_FINANCIADA',             'Compra financiada',                       true),
    ('a4153b30-58b5-50d4-9073-471ea1d6c294', 'REEMBOLSO',                     'Reembolso / liquidacion de derecho u obligacion', true),
    ('cf006530-280c-587b-994f-e621e680e3ef', 'APORTACION_INVERSION',          'Aportacion a inversion',                  true),
    ('26ee751e-aa9c-5c3b-a81c-7a28e5a5be34', 'GENERACION_DERECHO_OBLIGACION', 'Generacion de derecho de cobro u obligacion de pago', true)
ON CONFLICT (codigo) DO NOTHING;

RESET ROLE;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM gapto.tipos_hecho;
    IF v_count <> 7 THEN
        RAISE EXCEPTION 'POSTCHECK: esperadas 7 filas en tipos_hecho; encontradas=%', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

COMMIT;
