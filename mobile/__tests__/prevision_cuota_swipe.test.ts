// ============================================================
// GAPTO MOBILE 2027
// Fichero: prevision_cuota_swipe.test.ts
// Ruta: mobile/__tests__/prevision_cuota_swipe.test.ts
// Descripción: Reapertura nominal y acotada de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1, parte (a); mandato T3-F06 bloque 2 F06-01H v1.1 §11.5), versionada por D-C7-10 (Q3-Hd v1.2 candidato). Q3-C2 v1.2: la fila marcada `codigo = PREVISION_DE_CUOTA` admite swipe SOLO con el gesto «Pagado» visible (`gestoPagoCuota`: `PAGO_CUOTA_EXPUESTO`, `cuota.swipe_disponible`, `cuota.sin_dudas` y todos los datos del payload); sin bloque, con dudas, sin disponibilidad o con cualquier dato ausente, no. Q3-C3 (sin cambios): la cuota NUNCA tiene la acción rápida de registro (`planRapidoPrevision`, que compone un GASTO), con o sin gesto. Payload exacto de W-HIP-02 compuesto solo con el bloque (fecha = vencimiento, versión de la FINANCIACIÓN). Control: la fila ordinaria. Mata MQ3-C1, MQ3-C2 y los mutantes del gesto de D-C7-10 que tocan prevision.ts.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
// Versión: 0.2.0 (F06 T4 · D-C7-10, mandato 7041970a…; Q3-Hd v1.2 candidato; opción A de Moisés: con dudas no hay gesto)
// ============================================================

import type { BloqueCuota, FilaPrevision } from '../src/api/cliente';
import { PAGO_CUOTA_EXPUESTO } from '../src/domain/hipoteca';
import { admiteSwipe, gestoPagoCuota, payloadPagoCuotaSwipe, planRapidoPrevision, recursoPagoCuota, type CapacidadesHoy } from '../src/domain/prevision';

const HOY = '2026-10-10';

function fila(o: Partial<FilaPrevision> = {}): FilaPrevision {
  return {
    id: 'cuota-7', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'Cuota 7 hipoteca',
    tercero: null, categoria: null, fecha_desde: '2026-10-20', fecha_hasta: '2026-10-20', moneda: 'EUR', importe_esperado: '632.19',
    cubierto: '0.00', queda: '632.19', desviacion: null, con_realidad: false, pagos: 0, vencida: false,
    cuenta_salida: { id: 'cd', nombre: 'Cuenta hipoteca' }, cuenta_entrada: null, origen: 'MANUAL', presupuestable: true, ...o,
  };
}

const PARTES = [{ actor_id: 'a-yo', porcentaje: '60.0000' }, { actor_id: 'b-ana', porcentaje: '40.0000' }];
const BLOQUE: BloqueCuota = {
  financiacion_id: 'fin-1', numero: 3, financiacion_row_version: 7, fecha_vencimiento: '2026-06-20',
  cuenta_cargo: { id: 'cc', nombre: 'Cuenta común' }, propuesta_atribucion: PARTES, swipe_disponible: true, sin_dudas: true,
};

const CAP: CapacidadesHoy = {
  pago: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] as CapacidadesHoy['pago'],
  ingreso: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', moneda: 'EUR' }] as CapacidadesHoy['ingreso'],
};

const ORDINARIA = fila({ id: 'seguro', concepto: 'Seguro hogar' });
const CUOTA = fila({ codigo: 'PREVISION_DE_CUOTA' });
const CUOTA_OK = fila({ codigo: 'PREVISION_DE_CUOTA', vencida: true, cuota: BLOQUE });
const con = (q: Partial<BloqueCuota>) => fila({ codigo: 'PREVISION_DE_CUOTA', vencida: true, cuota: { ...BLOQUE, ...q } });

test('control: la fila ordinaria (sin la marca) admite swipe y acción rápida', () => {
  expect(admiteSwipe(ORDINARIA)).toBe(true);
  expect(planRapidoPrevision(ORDINARIA, CAP, HOY)).not.toBeNull();
  expect(gestoPagoCuota(ORDINARIA)).toBe(false);
});

test('Q3-C2: la fila de una cuota sin bloque no admite swipe (gasto e ingreso, vencida o próxima)', () => {
  expect(admiteSwipe(CUOTA)).toBe(false);
  expect(admiteSwipe({ ...CUOTA, vencida: true, fecha_desde: '2026-09-20', fecha_hasta: '2026-09-20' })).toBe(false);
  expect(admiteSwipe({ ...CUOTA, tipo: 'INGRESO', cuenta_salida: null, cuenta_entrada: { id: 'cd', nombre: 'Cuenta hipoteca' } })).toBe(false);
});

test('Q3-C2 v1.2: la cuota admite el gesto SOLO con swipe_disponible y sin_dudas (opción A: con dudas no hay gesto)', () => {
  expect(PAGO_CUOTA_EXPUESTO).toBe(true);
  expect(gestoPagoCuota(CUOTA_OK)).toBe(true);
  expect(admiteSwipe(CUOTA_OK)).toBe(true);
  expect(admiteSwipe(con({ sin_dudas: false }))).toBe(false);
  expect(admiteSwipe(con({ swipe_disponible: false }))).toBe(false);
  expect(admiteSwipe(con({ swipe_disponible: false, sin_dudas: false }))).toBe(false);
  expect(admiteSwipe({ ...CUOTA_OK, estado: 'REALIZADA' })).toBe(false);
});

test('M10: con PAGO_CUOTA_EXPUESTO = false no hay gesto aunque el servidor lo ofrezca', () => {
  expect(gestoPagoCuota(CUOTA_OK, false)).toBe(false);
  expect(gestoPagoCuota(CUOTA_OK, true)).toBe(true);
});

test('fail-closed: cualquier dato del payload ausente quita el gesto (sin inferir nada)', () => {
  for (const q of [{ financiacion_id: null }, { numero: null }, { financiacion_row_version: null }, { fecha_vencimiento: null },
    { cuenta_cargo: null }, { propuesta_atribucion: null }, { propuesta_atribucion: [] }] as Partial<BloqueCuota>[]) {
    expect(gestoPagoCuota(con(q))).toBe(false);
    expect(payloadPagoCuotaSwipe(con(q), 'x')).toBeNull();
  }
});

test('Q3-C3: la fila de una cuota no tiene la acción rápida de registro, ni con todas las capacidades ni con el gesto', () => {
  expect(planRapidoPrevision(CUOTA, CAP, HOY)).toBeNull();
  expect(planRapidoPrevision({ ...CUOTA, vencida: true }, CAP, HOY)).toBeNull();
  expect(planRapidoPrevision(CUOTA_OK, CAP, HOY)).toBeNull();
});

test('payload exacto de W-HIP-02 compuesto solo con el bloque: fecha = vencimiento, versión de la financiación, cuenta de cargo y propuesta', () => {
  expect(payloadPagoCuotaSwipe(CUOTA_OK, 'int-1')).toEqual({
    intencion_id: 'int-1', row_version_esperada: 7, cuenta_id: 'cc', fecha_pago: '2026-06-20',
    atribucion: { propuesta_vista: { partes: PARTES }, partes: PARTES },
  });
  // nunca la versión de la previsión, ni hoy, ni la cuenta de la fila si difiriera
  const p = payloadPagoCuotaSwipe({ ...CUOTA_OK, row_version: 99, cuenta_salida: { id: 'otra', nombre: 'Otra' } }, 'int-1')!;
  expect(p.row_version_esperada).toBe(7);
  expect(p.fecha_pago).toBe('2026-06-20');
  expect(p.cuenta_id).toBe('cc');
  expect(recursoPagoCuota(CUOTA_OK)).toBe('fin-1/3');
});

test('la marca es lo único que cambia: sin ella, la misma fila de cuota vuelve a admitirlos', () => {
  const { codigo, ...sinMarca } = CUOTA;
  expect(codigo).toBe('PREVISION_DE_CUOTA');
  expect(admiteSwipe(sinMarca)).toBe(true);
  expect(planRapidoPrevision(sinMarca, CAP, HOY)).toEqual(planRapidoPrevision(ORDINARIA, CAP, HOY));
});
