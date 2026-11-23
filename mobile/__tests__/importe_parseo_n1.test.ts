// ============================================================
// GAPTO MOBILE 2027
// Fichero: importe_parseo_n1.test.ts
// Ruta: mobile/__tests__/importe_parseo_n1.test.ts
// Descripción: F06 T4 · predespliegue (mandato 3af48054…, parte 1; dictamen MANT21 pregunta 3 y AJ-MANT21-05): discriminante N1 de `parsearImporte` tras D-C7-07 (R-TD-02 reclasificado N1). Fija con aserciones funcionales el valor canónico exacto que llegaría a la API para cada entrada, según el contrato vigente del código en 84e2f1b:
//   - el punto es separador de MILES solo en el patrón d{1,3}(.ddd)+ (sin coma) o delante de una coma; la coma es el separador DECIMAL;
//   - sin coma y sin grupos de 3 cifras, el punto es el decimal canónico (la forma que precarga el servidor, «120.50»);
//   - una agrupación incorrecta nunca se acepta como otro importe: da FORMATO o DECIMALES.
//   Incluye lo que el campo muestra tras PEGAR cada texto (`formatearImporteAlTeclear` con el campo vacío), que es lo que el usuario ve antes de confirmar.
//   Mutantes que debe matar: M-IMP-01 (se revierte la aceptación de los miles con punto) y M-IMP-02 (se aceptan agrupaciones incorrectas).
// Versión: 0.1.0 (F06 T4 · predespliegue, R-TD-02 N1)
// ============================================================

import { formatearImporteAlTeclear, parsearImporte } from '../src/domain/importe';

const valor = (t: string) => {
  const r = parsearImporte(t);
  return r.ok ? r.valor : `ERROR:${r.motivo}`;
};

test('miles con punto (patrón admitido): «1.500» → 1500.00 y variantes agrupadas (M-IMP-01)', () => {
  expect(valor('1.500')).toBe('1500.00');
  expect(valor('2.000')).toBe('2000.00');
  expect(valor('12.345')).toBe('12345.00');
  expect(valor('1.234.567')).toBe('1234567.00');
});

test('la coma es el decimal y el punto, miles delante de una coma', () => {
  expect(valor('1.500,25')).toBe('1500.25');
  expect(valor('1,50')).toBe('1.50');
  expect(valor('1.234.567,8')).toBe('1234567.80');
  expect(valor('0,05')).toBe('0.05');
  expect(valor('1500')).toBe('1500.00');
});

test('agrupaciones incorrectas: nunca otro importe en silencio (M-IMP-02)', () => {
  // Sin coma y sin grupos de 3 cifras, el punto es el decimal canónico (definido por el código): MISMO importe que «1,50».
  expect(valor('1.50')).toBe('1.50');
  expect(valor('15.00')).toBe('15.00');
  // Lo que no cuadra con ningún patrón se rechaza con su motivo.
  expect(valor('1.5000')).toBe('ERROR:DECIMALES');
  expect(valor('1.50.000')).toBe('ERROR:FORMATO');
  expect(valor('1.5,00')).toBe('ERROR:FORMATO');
  expect(valor('12.3456,7')).toBe('ERROR:FORMATO');
  expect(valor('1.500.00')).toBe('ERROR:FORMATO');
  expect(valor('1,500,00')).toBe('ERROR:FORMATO');
  expect(valor('1,505')).toBe('ERROR:DECIMALES');
});

test('valor canónico precargado del servidor: conserva su interpretación', () => {
  expect(valor('120.50')).toBe('120.50');
  expect(valor('1500.00')).toBe('1500.00');
  expect(valor('632.19')).toBe('632.19');
  expect(valor('0.00')).toBe('ERROR:NO_POSITIVO');
});

test('pegado en un campo vacío: lo que se ve antes de confirmar y lo que se guardaría coinciden en importe', () => {
  const pegar = (t: string) => {
    const visto = formatearImporteAlTeclear(t, '');
    return { visto, guardado: valor(visto) };
  };
  expect(pegar('1.500')).toEqual({ visto: '1.500', guardado: '1500.00' });
  expect(pegar('1,50')).toEqual({ visto: '1,50', guardado: '1.50' });
  expect(pegar('1.500,25')).toEqual({ visto: '1.500,25', guardado: '1500.25' });
  // el punto decimal canónico pegado se ve ya con coma: el usuario lee 1,50 antes de confirmar
  expect(pegar('1.50')).toEqual({ visto: '1,50', guardado: '1.50' });
  expect(pegar('1.5000')).toEqual({ visto: '1,5000', guardado: 'ERROR:DECIMALES' });
});
