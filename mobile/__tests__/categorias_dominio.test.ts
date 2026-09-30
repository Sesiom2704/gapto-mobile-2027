// ============================================================
// GAPTO MOBILE 2027
// Fichero: categorias_dominio.test.ts
// Ruta: mobile/__tests__/categorias_dominio.test.ts
// Descripción: Dominio de categorías del cliente (F05 §22.2 C01/C02/C07, §28.2; F09 §12.97.1–12.97.3): árbol desde la lista plana en el orden de la API, ruta, elegibilidad para GASTO, visibilidad en el registro (incluidos padre INGRESO con hijo GASTO y padre desactivado con hijo activo, estado inalcanzable por API que se cubre con fixture, F05 §26.4), motivo de no seleccionable con prioridad, normalización de valores de magnitud (casos de §28.2 y D1), conservación/descarte al cambiar de categoría, y validación/sellado de la intención con la dimensión categorial (S6-WIRE).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): Editar orden (`moverHermano`, `mismoOrden`) y subcategorías activas del subárbol completo (`subcategoriasActivas`).
// ============================================================

import {
  Arbol,
  ancestros,
  construirArbol,
  descendientes,
  elegibleParaGasto,
  hijosDe,
  magnitudesPedibles,
  mismoOrden,
  motivoNoSeleccionable,
  moverHermano,
  rutaTexto,
  subcategoriasActivas,
  visibleEnRegistro,
} from '../src/domain/categoria';
import { conservarMagnitudes, descartadas, normalizarValorMagnitud } from '../src/domain/magnitud';
import { Borrador, borradorInicial, sellar, validar } from '../src/domain/intencion';

import { LISTA, mag, nodo } from './fixtures_categorias';

const A: Arbol = construirArbol(LISTA);

test('árbol en el orden de la API, ruta y ancestros', () => {
  expect(hijosDe(A, null).map((n) => n.id)).toEqual(['hogar', 'trabajo', 'ocio', 'viejo']);
  expect(hijosDe(A, 'hogar').map((n) => n.id)).toEqual(['luz', 'agua', 'gas']);
  expect(ancestros(A, 'luz').map((n) => n.id)).toEqual(['hogar']);
  expect(rutaTexto(A, 'luz')).toBe('Todas › Hogar');
  expect(rutaTexto(A, 'hogar')).toBe('Todas');
  expect(descendientes(A, 'trabajo').map((n) => n.id)).toEqual(['nomina', 'prof']);
});

test('elegibilidad para GASTO: enabled, ámbito compatible y capturable (C02)', () => {
  const p = (id: string) => A.porId.get(id)!;
  expect(elegibleParaGasto(p('hogar'))).toBe(true); // nodo intermedio elegible
  expect(elegibleParaGasto(p('luz'))).toBe(true);
  expect(elegibleParaGasto(p('gas'))).toBe(false); // no capturable
  expect(elegibleParaGasto(p('trabajo'))).toBe(false); // INGRESO
  expect(elegibleParaGasto(p('ocio'))).toBe(false); // desactivada
  expect(elegibleParaGasto(nodo({ id: 'r', nombre: 'Regalos', ambito: 'AMBOS' }))).toBe(true);
});

test('visibilidad en el registro: elegible o con algún descendiente elegible', () => {
  const vis = (id: string) => visibleEnRegistro(A, A.porId.get(id)!);
  expect(vis('trabajo')).toBe(true); // padre INGRESO con hijo GASTO
  expect(vis('nomina')).toBe(false); // INGRESO hoja
  expect(vis('ocio')).toBe(true); // padre desactivado con hijo activo (fixture)
  expect(vis('viejo')).toBe(false); // hoja desactivada
  expect(vis('gas')).toBe(true); // habilitada y de gasto pero no capturable: visible con motivo (F09 §12.97.3, R05)
  expect(visibleEnRegistro(A, nodo({ id: 'ngc', nombre: 'N', ambito: 'INGRESO', capturable: false }))).toBe(false);
  expect(visibleEnRegistro(A, nodo({ id: 'dnc', nombre: 'D', enabled: false, capturable: false }))).toBe(false);
});

test('motivo de no seleccionable con prioridad Desactivada > Solo ingresos > dato no disponible', () => {
  expect(motivoNoSeleccionable(A.porId.get('ocio')!)).toBe('Desactivada');
  expect(motivoNoSeleccionable(nodo({ id: 'x', nombre: 'X', enabled: false, ambito: 'INGRESO', capturable: false }))).toBe('Desactivada');
  expect(motivoNoSeleccionable(nodo({ id: 'y', nombre: 'Y', ambito: 'INGRESO', capturable: false }))).toBe('Solo ingresos');
  expect(motivoNoSeleccionable(A.porId.get('gas')!)).toBe('Requiere un dato no disponible');
  expect(motivoNoSeleccionable(A.porId.get('luz')!)).toBeNull();
});

test('magnitudes pedibles: solo las habilitadas', () => {
  expect(magnitudesPedibles(A.porId.get('gas')!)).toEqual([]);
  expect(magnitudesPedibles(A.porId.get('luz')!).map((m) => m.magnitud_id)).toEqual(['kwh']);
});

test.each([
  ['1,23', 2, '1.23'], ['1.230', 2, '1.230'], ['12,5', 2, '12.5'], ['0', 2, '0'], ['-3,5', 2, '-3.5'], [' 7 ', 0, '7'],
  ['0.500', 1, '0.500'], ['123456789012', 0, '123456789012'],
])('normaliza %s (precisión %i) → %s', (entrada, prec, salida) => {
  expect(normalizarValorMagnitud(entrada, prec)).toEqual({ ok: true, valor: salida });
});

test.each([
  ['', 2, 'VACIO'], ['   ', 2, 'VACIO'], ['1.234', 2, 'DECIMALES'], ['-0', 2, 'CERO_CON_SIGNO'], ['-0,00', 2, 'CERO_CON_SIGNO'],
  ['+1', 2, 'FORMATO'], ['1e3', 2, 'FORMATO'], ['NaN', 2, 'FORMATO'], ['Infinity', 2, 'FORMATO'], ['01', 2, 'FORMATO'],
  ['1,2,3', 2, 'FORMATO'], ['1.', 2, 'FORMATO'], [',5', 2, 'FORMATO'], ['1.5', 0, 'DECIMALES'], ['1234567890123', 2, 'ENTEROS'],
])('rechaza %s (precisión %i) por %s', (entrada, prec, motivo) => {
  expect(normalizarValorMagnitud(entrada, prec)).toEqual({ ok: false, motivo });
});

test('cambio de categoría: se conservan las comunes y se listan las que se descartarían', () => {
  const luz = [mag({ magnitud_id: 'kwh' }), mag({ magnitud_id: 'pot', obligatoria: false })];
  const otra = [mag({ magnitud_id: 'kwh' })];
  const previos = { kwh: '12,5', pot: '3' };
  expect(conservarMagnitudes(previos, otra)).toEqual({ kwh: '12,5' });
  expect(descartadas(previos, luz, otra).map((m) => m.magnitud_id)).toEqual(['pot']);
  expect(descartadas(previos, luz, null).map((m) => m.magnitud_id)).toEqual(['kwh', 'pot']); // «Sin categoría»
  expect(descartadas({ kwh: '', pot: ' ' }, luz, null)).toEqual([]); // sin valores informados: sin confirmación
});

// ------------------------------------------------------------------ intención (S6-WIRE)
function listo(parche: Partial<Borrador> = {}): Borrador {
  return {
    ...borradorInicial('2026-09-24'),
    importeTexto: '3,50', concepto: 'Luz', presupuestable: true, cuentaId: 'k', cuentaOrigen: 'USUARIO', propuesta: 'NO_DETERMINADA',
    ...parche,
  };
}
const LUZ = { estado: 'CATEGORIA' as const, id: 'luz', nombre: 'Luz', ruta: 'Todas › Hogar', icon_key: 'hogar.luz',
  magnitudes: [mag({ magnitud_id: 'kwh', nombre: 'Consumo eléctrico' }), mag({ magnitud_id: 'pot', nombre: 'Potencia', obligatoria: false, unidad_default: 'kW' })] };

test('PENDIENTE bloquea: sin preselección y sin sellado', () => {
  const b = listo();
  expect(b.categoria).toEqual({ estado: 'PENDIENTE' });
  expect(validar(b, '2026-09-30').categoria).toBe('Elige una categoría o «Sin categoría».');
  expect(() => sellar(b, 'i')).toThrow();
});

test('SIN_CATEGORIA sella {estado:SIN_CATEGORIA} sin magnitudes', () => {
  const b = listo({ categoria: { estado: 'SIN_CATEGORIA' }, magnitudesTexto: { kwh: '5' } });
  expect(validar(b, '2026-09-30')).toEqual({});
  expect(sellar(b, 'i').payload.categoria).toEqual({ estado: 'SIN_CATEGORIA' });
});

test('CATEGORIA: obligatoria vacía bloquea y la nombra con unidad', () => {
  const b = listo({ categoria: LUZ });
  expect(validar(b, '2026-09-30').magnitudes).toEqual({ kwh: 'Indica Consumo eléctrico (kWh).' });
  expect(() => sellar(b, 'i')).toThrow();
});

test('CATEGORIA sella magnitudes canónicas con punto, solo las informadas y nunca unidad', () => {
  const b = listo({ categoria: LUZ, magnitudesTexto: { kwh: '12,5', pot: '' } });
  expect(validar(b, '2026-09-30')).toEqual({});
  const c = sellar(b, 'i').payload.categoria;
  expect(c).toEqual({ estado: 'CATEGORIA', categoria_id: 'luz', magnitudes: [{ magnitud_id: 'kwh', valor: '12.5' }] });
  expect(JSON.stringify(c)).not.toContain('unidad');
});

test('CATEGORIA sin magnitudes informadas y sin obligatorias: lista vacía', () => {
  const b = listo({ categoria: { ...LUZ, magnitudes: [LUZ.magnitudes[1]] } });
  expect(sellar(b, 'i').payload.categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'luz', magnitudes: [] });
});

test('valor no válido en una magnitud bloquea con su motivo', () => {
  const b = listo({ categoria: LUZ, magnitudesTexto: { kwh: '1,234' } });
  expect(validar(b, '2026-09-30').magnitudes).toEqual({ kwh: 'Máximo 2 decimales.' });
});

test('moverHermano: sube/baja un puesto sin salir de los extremos y sin mutar la lista', () => {
  const l = ['a', 'b', 'c'];
  expect(moverHermano(l, 2, -1)).toEqual(['a', 'c', 'b']);
  expect(moverHermano(l, 0, 1)).toEqual(['b', 'a', 'c']);
  expect(moverHermano(l, 0, -1)).toEqual(l);
  expect(moverHermano(l, 2, 1)).toEqual(l);
  expect(l).toEqual(['a', 'b', 'c']);
});

test('mismoOrden: mismos ids en la misma posición', () => {
  expect(mismoOrden([{ id: 'a' }, { id: 'b' }], [{ id: 'a' }, { id: 'b' }])).toBe(true);
  expect(mismoOrden([{ id: 'b' }, { id: 'a' }], [{ id: 'a' }, { id: 'b' }])).toBe(false);
  expect(mismoOrden([{ id: 'a' }], [{ id: 'a' }, { id: 'b' }])).toBe(false);
});

test('subcategoriasActivas: todo el subárbol, atravesando desactivadas (AJ-S4-02)', () => {
  const a = construirArbol([
    nodo({ id: 'r', nombre: 'R' }),
    nodo({ id: 'x', nombre: 'X', parent_id: 'r', enabled: false }),
    nodo({ id: 'y', nombre: 'Y', parent_id: 'x' }),
    nodo({ id: 'z', nombre: 'Z', parent_id: 'r' }),
  ]);
  expect(subcategoriasActivas(a, 'r').map((n) => n.id).sort()).toEqual(['y', 'z']);
});
