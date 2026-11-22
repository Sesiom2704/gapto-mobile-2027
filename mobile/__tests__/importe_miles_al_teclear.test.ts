// ============================================================
// GAPTO MOBILE 2027
// Fichero: importe_miles_al_teclear.test.ts
// Ruta: mobile/__tests__/importe_miles_al_teclear.test.ts
// Descripción: D-C7-07 (OBS-01 del 20-11): en los campos de importe los puntos de miles se insertan solos mientras se teclea (2000 → 2.000). Secuencias de pulsaciones reales (cada una parte de lo que mostraba el campo), borrado, coma y punto como decimal, pegado, y que el texto que deja el campo se parsea al mismo importe.
// Versión: 0.1.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-07)
// ============================================================

import { formatearImporteAlTeclear as f, parsearImporte } from '../src/domain/importe';

/** Teclea `teclas` una a una, como lo haría el TextInput controlado. */
function teclear(teclas: string, inicial = ''): string {
  let campo = inicial;
  for (const k of teclas) campo = f(campo + k, campo);
  return campo;
}

test.each([
  ['2000', '2.000'], ['200000', '200.000'], ['1234567', '1.234.567'], ['12', '12'], ['999', '999'],
  ['1234,5', '1.234,5'], ['1234,56', '1.234,56'], ['2000.5', '2.000,5'], ['0,5', '0,5'], [',5', '0,5'], ['007', '7'],
])('al teclear %s el campo muestra %s', (teclas, visto) => {
  expect(teclear(teclas)).toBe(visto);
});

test('el punto tecleado al final es la coma decimal; un segundo separador se ignora', () => {
  expect(teclear('12.')).toBe('12,');
  expect(teclear('12,.')).toBe('12,');
  expect(teclear('1234.')).toBe('1.234,');
});

test('borrar en un campo ya formateado recalcula los puntos de miles', () => {
  expect(f('2.00', '2.000')).toBe('200');
  expect(f('20.00', '200.000')).toBe('2.000');
  expect(f('1.234,', '1.234,5')).toBe('1.234,');
  expect(f('', '2')).toBe('');
});

test('campo precargado con el decimal canónico del servidor: su punto es el decimal', () => {
  expect(f('120.5', '120.50')).toBe('120,5');
  expect(f('120.505', '120.50')).toBe('120,505');          // el parseo lo rechazará (DECIMALES), no se convierte en 120.505
  expect(f('1120.50', '120.50')).toBe('1.120,50');
  expect(f('120.50.', '120.50')).toBe('120,50');
  expect(parsearImporte(f('1120.50', '120.50'))).toEqual({ ok: true, valor: '1120.50' });
});

test('pegado de golpe', () => {
  expect(f('1234.56')).toBe('1.234,56');
  expect(f('1.234.567')).toBe('1.234.567');
  expect(f('1.234,56')).toBe('1.234,56');
  expect(f(' 2 000 € ')).toBe('2.000');
});

test('lo que no es un importe se deja tal cual para que el parseo lo rechace', () => {
  expect(f('abc')).toBe('abc');
  expect(f('-3')).toBe('-3');
  expect(f('1.23.4')).toBe('1.23.4');
});

test.each([['2000', '2000.00'], ['1234,5', '1234.50'], ['12.', '12.00'], ['200000', '200000.00'], ['1234567,89', '1234567.89']])(
  'lo que deja el campo al teclear %s se parsea a %s',
  (teclas, canon) => expect(parsearImporte(teclear(teclas))).toEqual({ ok: true, valor: canon }),
);

test('el parseo acepta el entero con puntos de miles y sigue rechazando lo ambiguo', () => {
  expect(parsearImporte('2.000')).toEqual({ ok: true, valor: '2000.00' });
  expect(parsearImporte('1.234.567')).toEqual({ ok: true, valor: '1234567.00' });
  expect(parsearImporte('3.5')).toEqual({ ok: true, valor: '3.50' });
  expect(parsearImporte('1.23.4')).toEqual({ ok: false, motivo: 'FORMATO' });
  expect(parsearImporte('12.345,678')).toEqual({ ok: false, motivo: 'DECIMALES' });
});
