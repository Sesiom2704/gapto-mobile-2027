-- ============================================================
-- GAPTO MOBILE 2027
-- Fichero: 0160_f03_01_seed_metricas_definicion.sql
-- Descripcion: Seed de sistema para gapto.metricas_definicion, per
--   F03-00-I ("seeds de sistema versionados por codigo, con UUID
--   fijos en el fichero de seed pero codigo como identidad
--   semantica").
--
--   Microdecision de cierre (esta sesion): 3 metricas atomicas,
--   validadas contra la tabla de reconciliacion de AHORRO dic-2025
--   -> ago-2026 documentada en Migration_V3.md, reproduciendola
--   columna por columna sin fusionar naturalezas distintas:
--   - APORTACION_INVERSION_NETA: suma de efectos tipo INVERSION en
--     el periodo (capital invertido, no P&L).
--   - TRANSFERENCIA_AHORRO_NETA: neto de transferencias hacia/desde
--     cuentas tipo AHORRO (movimiento de tesoreria entre cuentas
--     propias, gasto/ingreso economico 0).
--   - AHORRO_NETO_PYL: SUM(ingreso)+SUM(gasto) del periodo, P&L puro,
--     deliberadamente SEPARADO de las dos anteriores.
--
--   Descartado del seed (decision explicita, no ausencia por olvido):
--   - AHORRO_TOTAL_MES: NO se persiste como cuarta metrica. Es un
--     agregado derivable (suma de las tres) que debe calcularse en
--     el read-model/UI y mostrarse siempre junto a su desglose, para
--     no duplicar informacion ni arriesgar que total y componentes
--     dejen de cuadrar.
--   - TASA_AHORRO: diferida explicitamente. Existen al menos 3 ratios
--     posibles no equivalentes (capacidad economica generada; % de
--     ingresos a ahorro/inversion; variacion patrimonial atribuible
--     al periodo), cada uno con numerador/denominador distintos; no
--     se cierra su formula por inferencia.
-- Versión: 0.1.0
-- ============================================================

BEGIN;

SET ROLE gapto_owner;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM gapto.metricas_definicion;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'PRECHECK: gapto.metricas_definicion ya contiene % filas; se esperaba vacio', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

INSERT INTO gapto.metricas_definicion (id, codigo, nombre, tipo_valor, unidad, enabled) VALUES
    ('fb08a197-b5c4-5d9c-af27-c1e185155cc0', 'APORTACION_INVERSION_NETA', 'Aportacion neta a inversion en el periodo',            'NUMERIC', 'MONEDA', true),
    ('70fb4ad0-4926-529b-bee2-b9c13bf26726', 'TRANSFERENCIA_AHORRO_NETA', 'Transferencia neta a cuentas de ahorro en el periodo', 'NUMERIC', 'MONEDA', true),
    ('e2a7df26-e7cc-5064-8d62-70669ecf752b', 'AHORRO_NETO_PYL',           'Ahorro neto de resultado (ingresos menos gastos)',     'NUMERIC', 'MONEDA', true)
ON CONFLICT (codigo) DO NOTHING;

RESET ROLE;

DO $gapto$
DECLARE v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM gapto.metricas_definicion;
    IF v_count <> 3 THEN
        RAISE EXCEPTION 'POSTCHECK: esperadas 3 filas en metricas_definicion; encontradas=%', v_count;
    END IF;
END $gapto$ LANGUAGE plpgsql;

COMMIT;
