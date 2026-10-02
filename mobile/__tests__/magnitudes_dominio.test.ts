// ============================================================
// GAPTO MOBILE 2027
// Fichero: magnitudes_dominio.test.ts
// Ruta: mobile/__tests__/magnitudes_dominio.test.ts
// Descripción: Lógica pura de S7-MAG en el cliente (F05-D020; F09 §12.97.10; lámina SET-MAG v0.1): «unidad · decimales», resumen de la sección, estado «No usable en registros nuevos» (M03), búsqueda normalizada, subtítulo del catálogo y secciones del selector (M06).
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import {
  normalizarBusqueda,
  obligatoriasDeshabilitadas,
  resumenMagnitudes,
  seccionesSelector,
  subtituloCatalogo,
  textoNoUsable,
  textoUnidadDecimales,
  usosDe,
} from '../src/domain/magnitud';

import { mag } from './fixtures_categorias';
import { CATALOGO, KWH, POT } from './fixtures_magnitudes';

test('unidad · decimales con singular y cero', () => {
  expect(textoUnidadDecimales('kWh', 2)).toBe('kWh · 2 decimales');
  expect(textoUnidadDecimales('kW', 1)).toBe('kW · 1 decimal');
  expect(textoUnidadDecimales('h', 0)).toBe('h · 0 decimales');
});

test('resumen de la sección', () => {
  expect(resumenMagnitudes([KWH, POT])).toEqual({ total: 2, obligatorias: 1, opcionales: 1, texto: '1 obligatoria, 1 opcional' });
  expect(resumenMagnitudes([KWH, { ...POT, obligatoria: true }, KWH]).texto).toBe('3 obligatorias');
  expect(resumenMagnitudes([POT, POT]).texto).toBe('2 opcionales');
  expect(resumenMagnitudes([])).toEqual({ total: 0, obligatorias: 0, opcionales: 0, texto: '' });
});

test('no usable: solo obligatorias deshabilitadas; una opcional deshabilitada no bloquea', () => {
  const gas = mag({ magnitud_id: 'g', nombre: 'Consumo de gas', obligatoria: true, enabled: false });
  const opOff = mag({ magnitud_id: 'o', nombre: 'Lectura', obligatoria: false, enabled: false });
  expect(obligatoriasDeshabilitadas([gas, opOff, KWH]).map((m) => m.nombre)).toEqual(['Consumo de gas']);
  expect(textoNoUsable(['Consumo de gas'])).toBe(
    'Pide «Consumo de gas», que está deshabilitada. Rehabilítala, hazla opcional o quítala de esta categoría. Lo ya registrado no cambia.',
  );
  expect(textoNoUsable(['A', 'B'])).toMatch(/^Pide «A» y «B», que están deshabilitadas\. Rehabilítalas/);
});

test('búsqueda normalizada: mayúsculas, espacios, diacríticos y NFKC', () => {
  expect(normalizarBusqueda('  KILÓMETROS  ')).toBe('kilometros');
  expect(normalizarBusqueda('Consumo   Eléctrico')).toBe('consumo electrico');
  expect(normalizarBusqueda('ﬁlo')).toBe('filo'); // ligadura fi -> «fi» (NFKC)
});

test('subtítulo del catálogo (M06)', () => {
  const [agua, , gas, km] = CATALOGO;
  expect(subtituloCatalogo(agua)).toBe('m3 · 3 decimales · usada en Agua');
  expect(subtituloCatalogo(gas)).toBe('kWh · 2 decimales · Deshabilitada · usada en Gas');
  expect(subtituloCatalogo(km)).toBe('km · 1 decimal · sin categorías');
  expect(usosDe(agua)).toEqual([{ id: 'agua', nombre: 'Agua', obligatoria: false, enabled: true }]);
});

test('secciones del selector: disponibles, deshabilitadas y ya asociadas en su orden; búsqueda', () => {
  const sec = seccionesSelector(CATALOGO, [KWH, POT], '');
  expect(sec.disponibles.map((m) => m.id)).toEqual(['m3', 'km']);
  expect(sec.deshabilitadas.map((m) => m.id)).toEqual(['kwhgas']);
  expect(sec.yaEn).toEqual([
    { magnitud_id: 'kwh', nombre: 'Consumo eléctrico', obligatoria: true },
    { magnitud_id: 'pot', nombre: 'Potencia contratada', obligatoria: false },
  ]);
  const busq = seccionesSelector(CATALOGO, [KWH, POT], 'consumo');
  expect(busq.disponibles.map((m) => m.id)).toEqual(['m3']);
  expect(busq.deshabilitadas.map((m) => m.id)).toEqual(['kwhgas']);
  expect(busq.yaEn.map((a) => a.magnitud_id)).toEqual(['kwh']);
});
