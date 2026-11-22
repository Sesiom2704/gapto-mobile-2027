// ============================================================
// GAPTO MOBILE 2027
// Fichero: mant_n3_conceptos_hipoteca.test.ts
// Ruta: mobile/__tests__/mant_n3_conceptos_hipoteca.test.ts
// Descripción: D-C7-09 (OBS-03) y AJ-06 del 19-11 (normalización de «Préstamo recibido» y denominación de pagos de cuota), solo en la capa de presentación: el concepto que el servidor guarda en el desembolso («PRESTAMO RECIBIDO») se presenta «Préstamo recibido» y el del pago de la cuota («CUOTA 3 HIPOTECA») «Cuota 3 · Hipoteca», también para hechos ya guardados. Controles: otro concepto, el mismo texto en una cuenta que no es del préstamo y un concepto escrito por la persona no cambian.
// Versión: 0.1.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-09 y AJ-06)
// ============================================================

import type { FilaActividad } from '../src/api/cliente';
import { CONCEPTO_DESEMBOLSO_SERVIDOR, conceptoPresentado, tituloFilaDia } from '../src/domain/titulos_dia';

function fila(p: Omit<Partial<FilaActividad>, 'tipo'> & { id: string; tipo: string }): FilaActividad {
  return {
    fecha_hecho: '2026-10-10', nota: null, moneda: 'EUR', importe_total: '10.00', tercero: null, categoria: null, varias: false,
    contexto: null, cuentas: [{ cuenta_id: 'cta', nombre: 'Cuenta Nómina', rol: 'COBRO', enabled: true }], estado_reparto: null,
    tu_parte: null, pendiente: null, maestros_desactivados: [], ...p,
  } as FilaActividad;
}
const HD = fila({
  id: 'hd', tipo: 'GENERACION_DERECHO_OBLIGACION', importe_total: '150000.00', nota: CONCEPTO_DESEMBOLSO_SERVIDOR,
  cuentas: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', rol: 'PRESTAMO_RECIBIDO', enabled: true }],
});

test('D-C7-09: el desembolso se titula «Préstamo recibido», no «PRESTAMO RECIBIDO»', () => {
  const t = tituloFilaDia(HD);
  expect(t).toContain('Préstamo recibido');
  expect(t).not.toContain('PRESTAMO');
});

test('D-C7-09: el mismo texto en una cuenta que no es del préstamo se muestra tal cual', () => {
  expect(conceptoPresentado('PRESTAMO RECIBIDO', 'COBRO')).toBe('PRESTAMO RECIBIDO');
  expect(conceptoPresentado('PRESTAMO RECIBIDO', null)).toBe('PRESTAMO RECIBIDO');
  expect(conceptoPresentado('PRESTAMO RECIBIDO')).toBe('Préstamo recibido');          // movimientos de cuenta: sin rol
  expect(conceptoPresentado('Préstamo de mi hermano', 'PRESTAMO_RECIBIDO')).toBe('Préstamo de mi hermano');
  expect(conceptoPresentado(null)).toBeNull();
});

test('AJ-06: el pago de la cuota se denomina como su previsión', () => {
  expect(conceptoPresentado('CUOTA 3 HIPOTECA', 'PAGO')).toBe('Cuota 3 · Hipoteca');
  expect(conceptoPresentado('CUOTA 120 HIPOTECA')).toBe('Cuota 120 · Hipoteca');
  expect(conceptoPresentado('Cuota 3/300 · Hipoteca')).toBe('Cuota 3/300 · Hipoteca');
  expect(conceptoPresentado('CUOTA HIPOTECA')).toBe('CUOTA HIPOTECA');
  const pago = fila({ id: 'pc', tipo: 'GASTO', nota: 'CUOTA 3 HIPOTECA', cuentas: [{ cuenta_id: 'cta', nombre: 'Cuenta Nómina', rol: 'PAGO', enabled: true }] });
  expect(tituloFilaDia(pago)).toContain('Cuota 3 · Hipoteca');
});
