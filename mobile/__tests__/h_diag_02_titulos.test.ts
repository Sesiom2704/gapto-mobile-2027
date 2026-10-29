// ============================================================
// GAPTO MOBILE 2027
// Fichero: h_diag_02_titulos.test.ts
// Ruta: mobile/__tests__/h_diag_02_titulos.test.ts
// Descripción: H-DIAG-02 (F05-D056 §70.2): ninguna fila de Día a día se titula «undefined». Cada tipo de hecho que trae la lista tiene nombre propio (gasto, ingreso, entre cuentas; la liquidación de una posición es «Cobro» o «Pago» según el movimiento y «Liquidación» sin él; la condonación es «Perdón»; los demás tipos del catálogo, el suyo) y un tipo desconocido usa el fallback explícito. Un cobro de derecho nunca se llama «Ingreso» ni «Entre cuentas».
// Versión: 0.1.0 (F05-D056 paso 3)
// ============================================================

import type { FilaActividad } from '../src/api/cliente';
import { nombreTipoFila, tituloFila } from '../src/domain/actividad';
import { NOMBRE_TIPO_DESCONOCIDO, tituloRegistro } from '../src/domain/registro';

type Rol = FilaActividad['cuentas'][number]['rol'];

/** Fila tal como la lista la devuelve para un tipo cualquiera del catálogo (el tipo del servidor es `th.codigo`). */
function fila(tipo: string, rol: Rol | null, p: Partial<FilaActividad> = {}): FilaActividad {
  return {
    id: `h-${tipo}`, fecha_hecho: '2026-10-28', tipo: tipo as FilaActividad['tipo'], nota: null, moneda: 'EUR', importe_total: '20.00',
    tercero: null, categoria: null, varias: false, contexto: null,
    cuentas: rol ? [{ cuenta_id: 'cta', nombre: 'Cuenta nómina', rol, enabled: true }] : [],
    estado_reparto: null, tu_parte: null, pendiente: null, maestros_desactivados: [], ...p,
  };
}

const CASOS: [string, Rol | null, string][] = [
  ['GASTO', 'PAGO', 'Gasto'],
  ['INGRESO', 'COBRO', 'Ingreso'],
  ['TRANSFERENCIA', null, 'Entre cuentas'],
  ['REEMBOLSO', 'COBRO', 'Cobro'],
  ['REEMBOLSO', 'PAGO', 'Pago'],
  ['REEMBOLSO', null, 'Liquidación'],
  ['CONDONACION', null, 'Perdón'],
  ['GENERACION_DERECHO_OBLIGACION', null, 'Derecho u obligación'],
  ['COMPRA_FINANCIADA', 'PAGO', 'Compra financiada'],
  ['APORTACION_INVERSION', 'PAGO', 'Aportación a inversión'],
];

test.each(CASOS)('%s con movimiento %s se llama «%s» y su título lo dice', (tipo, rol, nombre) => {
  const f = fila(tipo, rol);
  expect(nombreTipoFila(f)).toBe(nombre);
  expect(tituloFila(f)).toBe(`${nombre} · 20,00 €`);
});

test('S1 (H-DIAG-02): el cobro de una posición en Día a día es «Cobro · 20,00 €», nunca «undefined», «Ingreso» ni «Entre cuentas»', () => {
  const t = tituloFila(fila('REEMBOLSO', 'COBRO'));
  expect(t).toBe('Cobro · 20,00 €');
  expect(t).not.toMatch(/undefined|Ingreso|Entre cuentas/);
});

test('un tipo desconocido usa el fallback explícito', () => {
  expect(NOMBRE_TIPO_DESCONOCIDO).toBe('Registro');
  expect(nombreTipoFila(fila('TIPO_NUEVO', null))).toBe('Registro');
  expect(tituloFila(fila('TIPO_NUEVO', null))).toBe('Registro · 20,00 €');
  // Sin nombre del llamador, el título de registro tampoco dice «undefined».
  expect(tituloRegistro({ tipo: 'TIPO_NUEVO' as never, importe: '5' })).toBe('Registro · 5,00 €');
});

test('la precedencia del título no cambia: nota y tercero mandan sobre el nombre del tipo', () => {
  expect(tituloFila(fila('REEMBOLSO', 'COBRO', { nota: 'Marta me devuelve la cena' }))).toBe('Marta me devuelve la cena');
  expect(tituloFila(fila('REEMBOLSO', 'COBRO', { tercero: { id: 't', nombre: 'Marta', enabled: true } }))).toBe('Marta');
});

test('ningún tipo del catálogo produce «undefined» en el título', () => {
  for (const [tipo, rol] of CASOS) expect(tituloFila(fila(tipo, rol))).not.toContain('undefined');
});
