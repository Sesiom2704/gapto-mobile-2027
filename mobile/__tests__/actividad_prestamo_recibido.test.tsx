// ============================================================
// GAPTO MOBILE 2027
// Fichero: actividad_prestamo_recibido.test.tsx
// Ruta: mobile/__tests__/actividad_prestamo_recibido.test.tsx
// Descripción: Reapertura nominal y acotada de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1, parte (b); mandato T3-F06 bloque 2 F06-01H v1.1 §11.5). El desembolso Hd llega del servidor con el rol `PRESTAMO_RECIBIDO` en su cuenta: HD-C2 nombre del tipo «Préstamo recibido» (fila y detalle), HD-C3 línea secundaria «Préstamo recibido · <cuenta>» sin «Sin categoría», HD-C4 detalle rápido «Recibido en» (ni «Cobrado» ni «Pagado»). Controles: un GDO con rol COBRO (sin el predicado del servidor), un REEMBOLSO de cobro y un INGRESO no cambian. Ningún texto nuevo usa «ingreso» ni «cobro». Mata MHD-C1, MHD-C2 y MHD-C3.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, FilaActividad } from '../src/api/cliente';
import { importeFila, secundariaFila } from '../src/domain/actividad';
import { nombreTipoFila } from '../src/domain/titulos_dia';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

function fila(p: Omit<Partial<FilaActividad>, 'tipo'> & { id: string; tipo: string }): FilaActividad {
  return {
    fecha_hecho: HOY, nota: null, moneda: 'EUR', importe_total: '10.00', tercero: null, categoria: null, varias: false,
    contexto: null, cuentas: [{ cuenta_id: 'cta', nombre: 'Cuenta Nómina', rol: 'COBRO', enabled: true }], estado_reparto: null,
    tu_parte: null, pendiente: null, maestros_desactivados: [], ...p,
  } as FilaActividad;
}

const HD = fila({
  id: 'hd', tipo: 'GENERACION_DERECHO_OBLIGACION', importe_total: '150000.00',
  cuentas: [{ cuenta_id: 'cd', nombre: 'Cuenta hipoteca', rol: 'PRESTAMO_RECIBIDO', enabled: true }],
});
const GDO_SIN_VINCULO = fila({ id: 'gdo', tipo: 'GENERACION_DERECHO_OBLIGACION', importe_total: '5000.00' });
const REEMBOLSO = fila({ id: 'rb', tipo: 'REEMBOLSO', importe_total: '15.00' });
const INGRESO = fila({ id: 'in', tipo: 'INGRESO', nota: 'Nómina', importe_total: '2100.00', estado_reparto: 'COMPLETA', tu_parte: '2100.00' });

test('HD-C2: el tipo del desembolso Hd se llama «Préstamo recibido»; los controles no cambian', () => {
  expect(nombreTipoFila(HD)).toBe('Préstamo recibido');
  expect(nombreTipoFila(GDO_SIN_VINCULO)).toBe('Derecho u obligación');
  expect(nombreTipoFila(REEMBOLSO)).toBe('Cobro');
  expect(nombreTipoFila(INGRESO)).toBe('Ingreso');
});

test('HD-C3: línea secundaria «Préstamo recibido · <cuenta>», sin «Sin categoría»; importe sin signo como hoy', () => {
  expect(secundariaFila(HD)).toBe('Préstamo recibido · Cuenta hipoteca');
  expect(secundariaFila(HD)).not.toMatch(/Sin categoría|ingreso|cobro/i);
  // control: el GDO sin el predicado del servidor sigue en la rama genérica
  expect(secundariaFila(GDO_SIN_VINCULO)).toBe('Sin categoría · Cuenta Nómina');
  expect(importeFila(HD)).toBe(importeFila({ ...HD, cuentas: [{ ...HD.cuentas[0], rol: 'COBRO' }] }));
});

function fake(filas: FilaActividad[]): ClienteApi {
  return {
    ...clienteCategoriasStub([]),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas, siguiente: null, total: filas.length } })) as any,
    detalleActividad: jest.fn(async (id: string) => ({ tipo: 'OK', datos: { ...filas.find((f) => f.id === id)!, presupuestable: false, magnitudes: [] } })) as any,
    yo: jest.fn(async () => ({ tipo: 'OK', datos: { nombre: 'Moisés' } })) as any,
    resultadoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' })) as any,
  } as ClienteApi;
}

async function irADia(filas: FilaActividad[]) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={fake(filas)} nuevoId={() => 'id'} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await act(async () => fireEvent.press(screen.getByTestId('tab-DIA')));
  await waitFor(() => expect(screen.getByTestId(`fila-${filas[0].id}`)).toBeTruthy());
}

async function abrir(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(`fila-${id}`)));
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
}

test('HD-C4: el detalle rápido del Hd dice «Recibido en» (ni «Cobrado en» ni «Pagado con»)', async () => {
  await irADia([HD, GDO_SIN_VINCULO]);
  expect(screen.getByText('Préstamo recibido · Cuenta hipoteca')).toBeTruthy();
  await abrir('hd');
  expect(within(screen.getByTestId('kv-Recibido en')).getByText('Cuenta hipoteca')).toBeTruthy();
  expect(screen.queryByTestId('kv-Cobrado en')).toBeNull();
  expect(screen.queryByTestId('kv-Pagado con')).toBeNull();
});

test('control HD-C4: un GDO con rol COBRO sigue con «Cobrado en»', async () => {
  await irADia([GDO_SIN_VINCULO, HD]);
  await abrir('gdo');
  expect(within(screen.getByTestId('kv-Cobrado en')).getByText('Cuenta Nómina')).toBeTruthy();
  expect(screen.queryByTestId('kv-Recibido en')).toBeNull();
});
