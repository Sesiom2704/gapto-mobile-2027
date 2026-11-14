// ============================================================
// GAPTO MOBILE 2027
// Fichero: reforma_actividad_inicio.test.tsx
// Ruta: mobile/__tests__/reforma_actividad_inicio.test.tsx
// Descripción: T2-F06 PAG · Actividad e Inicio de F05 con la reforma (mandato PAG §1.5, lista cerrada autorizada por el párrafo 3 del literal; Q-VP-02, Q-VP-03; O-PAG-24 parte cliente):
//   - fila de Actividad de una reforma: «<nota> · <vivienda>», importe principal = tu parte, «Salió de tu cuenta: −N €» SOLO si difiere y la posición real en su sentido; sin posición, ninguna línea inventada (tampoco con cuenta compartida); los demás tipos no cambian;
//   - Inicio: «Invertido en viviendas este mes» en un bloque aparte, fuera de «Este mes» (Ingresos, Gastos y Resultado no cambian); sin la lectura, no se pinta.
//   Código de partida: laboratorio lab-t2 0a86083 (reforma_actividad_lab.test.ts), ampliado.
// Versión: 0.1.0 (F06 T2-F06 PAG N1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, FilaActividad } from '../src/api/cliente';
import { importeFila, lineasReforma, secundariaFila } from '../src/domain/actividad';
import { tituloFilaDia } from '../src/domain/titulos_dia';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

function fila(p: Omit<Partial<FilaActividad>, 'tipo'> & { id: string; tipo: string }): FilaActividad {
  return {
    fecha_hecho: HOY, nota: null, moneda: 'EUR', importe_total: '10.00', tercero: null, categoria: null, varias: false,
    contexto: null, cuentas: [{ cuenta_id: 'cta', nombre: 'Cuenta Nómina', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA',
    tu_parte: '10.00', pendiente: null, maestros_desactivados: [], ...p,
  } as FilaActividad;
}
const VIV = { id: 'p1', nombre: 'Piso Gran Vía' };
const P1 = fila({ id: 'r1', tipo: 'MEJORA_PATRIMONIAL', nota: 'Habitación nueva', importe_total: '1500.00', tu_parte: '750.00', propiedad: VIV,
  salida_cuentas: '1500.00', posiciones: [{ sentido: 'ME_DEBE', importe: '750.00', tercero: 'Tomás' }] });
const P2 = fila({ id: 'r2', tipo: 'MEJORA_PATRIMONIAL', nota: 'Baño', importe_total: '1500.00', tu_parte: '750.00', propiedad: VIV,
  salida_cuentas: '750.00', posiciones: [] });
const P3 = fila({ id: 'r3', tipo: 'MEJORA_PATRIMONIAL', nota: null, importe_total: '1500.00', tu_parte: '750.00', propiedad: VIV, cuentas: [],
  salida_cuentas: '0.00', posiciones: [{ sentido: 'LE_DEBO', importe: '750.00', tercero: 'Tomás' }] });
const GASTO = fila({ id: 'g1', tipo: 'GASTO', nota: 'Compra semanal', importe_total: '48.72', tu_parte: '48.72' });

test('reforma: título con la vivienda e importe principal = tu parte', () => {
  expect(tituloFilaDia(P1)).toBe('Habitación nueva · Piso Gran Vía');
  expect(tituloFilaDia(P3)).toBe('Reforma · Piso Gran Vía');
  expect(importeFila(P1)).toBe('−750,00 €');
  expect(importeFila(P3)).toBe('−750,00 €');
});

test('reforma: «Salió de tu cuenta» solo si difiere de tu parte y la posición en su sentido', () => {
  expect(lineasReforma(P1)).toEqual(['Salió de tu cuenta: −1.500,00 €', 'Tomás te debe 750,00 €']);
  expect(lineasReforma(P2)).toEqual([]);
  expect(lineasReforma(P3)).toEqual(['No salió de tu cuenta', 'Le debes 750,00 € a Tomás']);
  expect(lineasReforma({ ...P2, salida_cuentas: '1500.00' })).toEqual(['Salió de tu cuenta: −1.500,00 €']);   // cuenta compartida: sin posición inferida
});

test('control: los demás tipos no cambian', () => {
  expect(lineasReforma(GASTO)).toEqual([]);
  expect(importeFila(GASTO)).toBe('−48,72 €');
  expect(secundariaFila(GASTO)).toBe('Sin categoría · Cuenta Nómina');
  expect(tituloFilaDia({ ...P1, propiedad: null })).toBe('Mejora · Habitación nueva');
});

function fake(filas: FilaActividad[], invertido: boolean): ClienteApi {
  return {
    ...clienteCategoriasStub([]),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas, siguiente: null, total: filas.length } })) as any,
    detalleActividad: jest.fn(async (id: string) => ({ tipo: 'OK', datos: { ...filas.find((f) => f.id === id)!, presupuestable: false, magnitudes: [] } })) as any,
    yo: jest.fn(async () => ({ tipo: 'OK', datos: { nombre: 'Moisés' } })) as any,
    resultadoMes: jest.fn(async () => ({ tipo: 'OK', datos: { mes: '2026-10', moneda: 'EUR', ingresos_propios: '2000.00', gastos_propios: '300.00', resultado: '1700.00',
      sin_indicar: { gastos: { n: 0, importe: '0.00' }, ingresos: { n: 0, importe: '0.00' } } } })) as any,
    ...(invertido ? { invertidoMes: jest.fn(async () => ({ tipo: 'OK', datos: { mes: '2026-10', moneda: 'EUR', invertido: '1500.00', sin_reparto: 0 } })) } : {}),
  } as ClienteApi;
}

async function montar(cli: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cli} nuevoId={() => 'id'} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

test('Inicio: «Invertido en viviendas este mes» aparte de «Este mes»; el Resultado no cambia', async () => {
  await montar(fake([], true));
  await waitFor(() => expect(screen.getByTestId('bloque-invertido')).toBeTruthy());
  expect(screen.getByTestId('invertido-importe').props.children).toBe('1.500,00 €');
  expect(screen.getByTestId('bloque-mes')).toBeTruthy();
  expect(within(screen.getByTestId('bloque-mes')).queryByText(/1\.500,00/)).toBeNull();     // fuera de «Este mes»
  expect(screen.getByText('1.700,00 €', { exact: false })).toBeTruthy();
});

test('Inicio sin la lectura: la fila no se pinta', async () => {
  await montar(fake([], false));
  await waitFor(() => expect(screen.getByTestId('bloque-mes')).toBeTruthy());
  expect(screen.queryByTestId('bloque-invertido')).toBeNull();
});

test('Actividad: la fila de la reforma pinta las líneas adicionales', async () => {
  await montar(fake([P1, P2, GASTO], false));
  await act(async () => fireEvent.press(screen.getByTestId('tab-DIA')));
  await waitFor(() => expect(screen.getByTestId('fila-r1')).toBeTruthy());
  expect(screen.getByText('Habitación nueva · Piso Gran Vía')).toBeTruthy();
  expect(screen.getByTestId('fila-r1-reforma-0').props.children).toBe('Salió de tu cuenta: −1.500,00 €');
  expect(screen.getByTestId('fila-r1-reforma-1').props.children).toBe('Tomás te debe 750,00 €');
  expect(screen.queryByTestId('fila-r2-reforma-0')).toBeNull();
  expect(screen.queryByTestId('fila-g1-reforma-0')).toBeNull();
});
