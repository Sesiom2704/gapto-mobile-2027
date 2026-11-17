// ============================================================
// GAPTO MOBILE 2027
// Fichero: prevision_cuota_swipe.test.ts
// Ruta: mobile/__tests__/prevision_cuota_swipe.test.ts
// Descripción: Reapertura nominal y acotada de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1, parte (a); mandato T3-F06 bloque 2 F06-01H v1.1 §11.5). La fila de lista que el servidor marca con `codigo = PREVISION_DE_CUOTA` no admite swipe (Q3-C2, `admiteSwipe`) ni acción rápida (Q3-C3, `planRapidoPrevision`, comprobación propia sin apoyarse en `admiteSwipe`), aunque cumpla todas las demás condiciones. Control: la misma fila sin la marca sigue admitiendo los dos. Mata MQ3-C1 y MQ3-C2.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
// ============================================================

import type { FilaPrevision } from '../src/api/cliente';
import { admiteSwipe, planRapidoPrevision, type CapacidadesHoy } from '../src/domain/prevision';

const HOY = '2026-10-10';

function fila(o: Partial<FilaPrevision> = {}): FilaPrevision {
  return {
    id: 'cuota-7', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'Cuota 7 hipoteca',
    tercero: null, categoria: null, fecha_desde: '2026-10-20', fecha_hasta: '2026-10-20', moneda: 'EUR', importe_esperado: '632.19',
    cubierto: '0.00', queda: '632.19', desviacion: null, con_realidad: false, pagos: 0, vencida: false,
    cuenta_salida: { id: 'cd', nombre: 'Cuenta hipoteca' }, cuenta_entrada: null, origen: 'MANUAL', presupuestable: true, ...o,
  };
}

const CAP: CapacidadesHoy = {
  pago: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] as CapacidadesHoy['pago'],
  ingreso: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', moneda: 'EUR' }] as CapacidadesHoy['ingreso'],
};

const ORDINARIA = fila({ id: 'seguro', concepto: 'Seguro hogar' });
const CUOTA = fila({ codigo: 'PREVISION_DE_CUOTA' });

test('control: la fila ordinaria (sin la marca) admite swipe y acción rápida', () => {
  expect(admiteSwipe(ORDINARIA)).toBe(true);
  expect(planRapidoPrevision(ORDINARIA, CAP, HOY)).not.toBeNull();
});

test('Q3-C2: la fila de una cuota no admite swipe (gasto e ingreso, vencida o próxima)', () => {
  expect(admiteSwipe(CUOTA)).toBe(false);
  expect(admiteSwipe({ ...CUOTA, vencida: true, fecha_desde: '2026-09-20', fecha_hasta: '2026-09-20' })).toBe(false);
  expect(admiteSwipe({ ...CUOTA, tipo: 'INGRESO', cuenta_salida: null, cuenta_entrada: { id: 'cd', nombre: 'Cuenta hipoteca' } })).toBe(false);
});

test('Q3-C3: la fila de una cuota no tiene acción rápida, ni con todas las capacidades', () => {
  expect(planRapidoPrevision(CUOTA, CAP, HOY)).toBeNull();
  expect(planRapidoPrevision({ ...CUOTA, vencida: true }, CAP, HOY)).toBeNull();
});

test('la marca es lo único que cambia: sin ella, la misma fila de cuota vuelve a admitirlos', () => {
  const { codigo, ...sinMarca } = CUOTA;
  expect(codigo).toBe('PREVISION_DE_CUOTA');
  expect(admiteSwipe(sinMarca)).toBe(true);
  expect(planRapidoPrevision(sinMarca, CAP, HOY)).toEqual(planRapidoPrevision(ORDINARIA, CAP, HOY));
});
