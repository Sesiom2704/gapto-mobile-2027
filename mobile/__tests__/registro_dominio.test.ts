// ============================================================
// GAPTO MOBILE 2027
// Fichero: registro_dominio.test.ts
// Ruta: mobile/__tests__/registro_dominio.test.ts
// Descripción: Lógica pura del registro por tipo (F05-04 J2 §2.2/§2.7; F05 §46.3 A1/A8; lámina REG-DYN T01, T02, N02): hoja de tipos sin preselección y con sus textos; cambio de tipo que conserva importe y fecha y quita lo que no encaja, con el aviso T02; nota canónica (vacía → null); título calculado nunca vacío ni «null» con su orden de precedencia.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2)
// ============================================================

import {
  ambitoAdmitido,
  avisoCambioDeTipo,
  cambioDeTipo,
  NOTA_DEVOLUCION,
  notaCanonica,
  tituloExito,
  tituloRegistro,
  TIPOS_REGISTRO,
} from '../src/domain/registro';

test('T01: tres tipos en su orden, con sus subtítulos y la nota de devolución', () => {
  expect(TIPOS_REGISTRO.map((t) => t.titulo)).toEqual(['Gasto', 'Ingreso', 'Entre cuentas']);
  expect(TIPOS_REGISTRO[2].subtitulo).toBe('Mover dinero entre tus cuentas. No es gasto ni ingreso');
  expect(NOTA_DEVOLUCION).toBe('¿Te han devuelto dinero de una compra? Regístralo desde el gasto original.');
});

test('A12: ámbitos de categoría admitidos por tipo', () => {
  expect(ambitoAdmitido('GASTO', 'GASTO')).toBe(true);
  expect(ambitoAdmitido('GASTO', 'INGRESO')).toBe(false);
  expect(ambitoAdmitido('INGRESO', 'AMBOS')).toBe(true);
  expect(ambitoAdmitido('TRANSFERENCIA', 'AMBOS')).toBe(false);
});

test('T02: cambio de Gasto a Ingreso quita categoría de gastos y cuenta sin capacidad, con el texto de la lámina', () => {
  const q = cambioDeTipo('GASTO', 'INGRESO', {
    categoria: { nombre: 'Supermercados', ambito: 'GASTO' },
    cuenta: { nombre: 'Tarjeta BBVA', admitida: false },
    tercero: 'ALDI',
  });
  expect(q).toEqual([{ campo: 'categoria', nombre: 'Supermercados' }, { campo: 'cuenta', nombre: 'Tarjeta BBVA' }]);
  expect(avisoCambioDeTipo('GASTO', 'INGRESO', q)).toBe(
    'Has cambiado de Gasto a Ingreso. Se mantienen el importe y la fecha. Se han quitado la categoría «Supermercados» (no admite ingresos) y la cuenta «Tarjeta BBVA» (no se puede usar para cobrar).',
  );
  expect(cambioDeTipo('GASTO', 'GASTO', { categoria: { nombre: 'x', ambito: 'INGRESO' } })).toEqual([]);
});

test('T02 hacia «Entre cuentas»: quita tercero, contexto, presupuesto y atribución', () => {
  const q = cambioDeTipo('GASTO', 'TRANSFERENCIA', { tercero: 'ALDI', contexto: 'Finde', presupuestable: true, soloMio: true, cuenta: { nombre: 'Efectivo', admitida: true } });
  expect(q.map((x) => x.campo)).toEqual(['tercero', 'contexto', 'presupuestable', 'atribucion']);
  expect(avisoCambioDeTipo('GASTO', 'TRANSFERENCIA', [])).toBe('Has cambiado de Gasto a Entre cuentas. Se mantienen el importe y la fecha.');
});

test('A8: nota canónica y título calculado (nunca vacío ni «null»)', () => {
  expect(notaCanonica('   ')).toBeNull();
  expect(notaCanonica(undefined)).toBeNull();
  expect(notaCanonica(' Cena ')).toBe('Cena');
  expect(tituloRegistro({ tipo: 'GASTO', importe: '4.00', nota: 'Cena', tercero: 'ALDI', categoria: 'Super' })).toBe('Cena');
  expect(tituloRegistro({ tipo: 'GASTO', importe: '4.00', concepto: 'Histórico', tercero: 'ALDI' })).toBe('Histórico');
  expect(tituloRegistro({ tipo: 'GASTO', importe: '4.00', tercero: 'ALDI', categoria: 'Supermercados' })).toBe('ALDI · Supermercados');
  expect(tituloRegistro({ tipo: 'GASTO', importe: '4.00', categoria: 'Supermercados' })).toBe('Supermercados');
  expect(tituloRegistro({ tipo: 'INGRESO', importe: '4.00', tercero: 'Empresa' })).toBe('Empresa');
  const t = tituloRegistro({ tipo: 'GASTO', importe: '4.00', nota: null, concepto: null, tercero: null, categoria: null });
  expect(t.startsWith('Gasto · ')).toBe(true);
  expect(t).not.toContain('null');
  expect(tituloExito('TRANSFERENCIA')).toBe('Movimiento registrado');
  expect(tituloExito('INGRESO')).toBe('Ingreso registrado');
});
