// ============================================================
// GAPTO MOBILE 2027
// Fichero: dominio.test.ts
// Ruta: mobile/__tests__/dominio.test.ts
// Descripción: Tests de dominio del cliente: importe, contraste de tokens DS-01 y clasificación de respuestas HTTP.
// v0.2.0 (F05-D003): payload con financiación; conversión de fechas dd/mm/aaaa.
// Versión: 0.2.0
// ============================================================

import { crearCliente } from '../src/api/cliente';
import { ddmmaaaaAIso, isoADdmmaaaa } from '../src/domain/fechas';
import { formatearEur, parsearImporte } from '../src/domain/importe';
import { esFechaIso } from '../src/domain/intencion';
import { contraste } from '../src/theme/contraste';
import { colores } from '../src/theme/tokens';

test.each([
  ['3,50', '3.50'], ['3.5', '3.50'], ['1.234,56', '1234.56'], ['0,01', '0.01'], ['12', '12.00'], [' 7,5 € ', '7.50'],
])('parsea %s', (entrada, salida) => {
  expect(parsearImporte(entrada)).toEqual({ ok: true, valor: salida });
});

test.each([['', 'VACIO'], ['abc', 'FORMATO'], ['0', 'NO_POSITIVO'], ['0,00', 'NO_POSITIVO'], ['3,505', 'DECIMALES'], ['-3', 'FORMATO'], ['1.23.4', 'FORMATO']])(
  'rechaza %s',
  (entrada, motivo) => expect(parsearImporte(entrada)).toEqual({ ok: false, motivo }),
);

test('formato es-ES', () => {
  expect(formatearEur('1234.5')).toBe('1.234,50 €');
  expect(formatearEur('3.50')).toBe('3,50 €');
});

// F09 §12.92.8: los HEX de DS-01 se verifican por contraste antes de usarse como tokens.
test.each(['light', 'dark'] as const)('contraste de texto AA en %s', (e) => {
  const c = colores[e];
  for (const fondo of [c.background, c.surfacePrimary, c.surfaceSecondary, c.accentSurface, c.unknownSurface, c.partialSurface]) {
    expect(contraste(c.textPrimary, fondo)).toBeGreaterThanOrEqual(4.5);
    expect(contraste(c.textSecondary, fondo)).toBeGreaterThanOrEqual(4.5);
  }
  expect(contraste(c.onAccent, c.accent)).toBeGreaterThanOrEqual(4.5);
  expect(contraste(c.accent, c.background)).toBeGreaterThanOrEqual(4.5);
  expect(contraste(c.accent, c.accentSurface)).toBeGreaterThanOrEqual(4.5);
  expect(contraste(c.critical, c.surfacePrimary)).toBeGreaterThanOrEqual(4.5);
});

test('warning claro NO es apto para texto (3,19:1): solo iconografía/superficie', () => {
  expect(contraste(colores.light.warning, colores.light.surfacePrimary)).toBeLessThan(4.5);
  expect(contraste(colores.light.warning, colores.light.surfacePrimary)).toBeGreaterThanOrEqual(3);
});

const P = { intencion_id: 'x', concepto: 'c', importe: '1.00', moneda: 'EUR' as const, fecha_hecho: '2026-09-24', cuenta_id: 'k', presupuestable: true, atribucion: 'SOLO_MIO' as const, financiacion: { estado: 'NO_DETERMINADA' as const } };
const resp = (status: number, body: unknown) => ({ ok: status < 300, status, json: async () => body }) as unknown as Response;

test('clasificación: 2xx OK, 4xx RECHAZADO, 5xx/red/timeout INDETERMINADO', async () => {
  const cfg = { baseUrl: 'http://x', token: 't', timeoutMs: 50 };
  expect((await crearCliente(cfg, (async () => resp(200, { hecho_id: 'h' })) as any).registrarGastoPagado(P)).tipo).toBe('OK');
  expect(await crearCliente(cfg, (async () => resp(409, { codigo: 'IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION', mensaje: 'm' })) as any).registrarGastoPagado(P))
    .toEqual({ tipo: 'RECHAZADO', codigo: 'IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION', mensaje: 'm' });
  expect((await crearCliente(cfg, (async () => resp(503, { codigo: 'BD_NO_DISPONIBLE' })) as any).registrarGastoPagado(P)).tipo).toBe('INDETERMINADO');
  expect((await crearCliente(cfg, (async () => { throw new TypeError('network'); }) as any).registrarGastoPagado(P)).tipo).toBe('INDETERMINADO');
  const colgado = ((_: string, init: RequestInit) =>
    new Promise((_r, rej) => init.signal!.addEventListener('abort', () => rej(new Error('abort'))))) as any;
  const r = await crearCliente(cfg, colgado).registrarGastoPagado(P);
  expect(r).toEqual({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' });
});

test('fechas: dd/mm/aaaa ↔ ISO y fechas de calendario válidas', () => {
  expect(ddmmaaaaAIso('3/9/2026')).toBe('2026-09-03');
  expect(ddmmaaaaAIso('2026-09-03')).toBeNull();
  expect(isoADdmmaaaa('2026-09-03')).toBe('03/09/2026');
  expect(esFechaIso('2026-02-28')).toBe(true);
  expect(esFechaIso('2026-02-30')).toBe(false);
  expect(esFechaIso('26/09/2026')).toBe(false);
});
