// ============================================================
// GAPTO MOBILE 2027
// Fichero: actividad_patrimonial.test.tsx
// Ruta: mobile/__tests__/actividad_patrimonial.test.tsx
// Descripción: B3 · fila patrimonial en Actividad (F06-01 B3, pendiente trasladado de B2; R1 v0.8 §II.5 «Actividad (fila, app)» y lámina L-6; decisión de Moisés afaac92d…, solo presentación). Para la compra (ADQUISICION_PATRIMONIAL con concepto COMPRA), un gasto de la compra (ADQUISICION_PATRIMONIAL con concepto ITP) y una mejora (MEJORA_PATRIMONIAL): nombre, icono de propiedad, signo «−» y etiqueta «no es gasto del mes», derivados del tipo del HECHO (HF-14). Control: un GASTO y un INGRESO siguen exactamente igual. Los Jest de F05 que cubren Actividad no se editan (se revalidan aparte).
// Versión: 0.1.0 (F06 T1-F06 B3)
// ============================================================

import './tiempos_rn';
import { Ionicons } from '@expo/vector-icons';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, FilaActividad } from '../src/api/cliente';
import { importeFila, marcaReparto, secundariaFila } from '../src/domain/actividad';
import { TEXTO_NO_GASTO_MES } from '../src/domain/compra';
import { nombreTipoFila, tituloFilaDia } from '../src/domain/titulos_dia';
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

const COMPRA = fila({ id: 'h0', tipo: 'ADQUISICION_PATRIMONIAL', nota: 'COMPRA', importe_total: '200000.00', tu_parte: '120000.00' });
const ITP = fila({ id: 'hk', tipo: 'ADQUISICION_PATRIMONIAL', nota: 'ITP', importe_total: '12000.00', tu_parte: '7200.00' });
const MEJORA = fila({ id: 'm1', tipo: 'MEJORA_PATRIMONIAL', nota: 'Cocina', importe_total: '8500.00', tu_parte: '5100.00' });
const GASTO = fila({ id: 'g1', tipo: 'GASTO', nota: 'Compra semanal', importe_total: '48.72', tu_parte: '48.72' });
const INGRESO = fila({ id: 'i1', tipo: 'INGRESO', nota: 'Nómina', importe_total: '2100.00', tu_parte: '2100.00' });

test('nombre: compra, gasto de la compra y mejora (por el tipo del HECHO)', () => {
  expect(tituloFilaDia(COMPRA)).toBe('Compra de la propiedad');
  expect(tituloFilaDia(ITP)).toBe('Gasto de la compra · ITP');
  expect(tituloFilaDia(MEJORA)).toBe('Mejora · Cocina');
  expect(tituloFilaDia({ ...MEJORA, nota: null })).toBe('Mejora');
  expect(nombreTipoFila(COMPRA)).toBe('Compra');
  expect(nombreTipoFila(MEJORA)).toBe('Mejora');
});

test('signo: −importe (sale de la cuenta) en compra, gasto de la compra y mejora', () => {
  expect(importeFila(COMPRA)).toBe('−200.000,00 €');
  expect(importeFila(ITP)).toBe('−12.000,00 €');
  expect(importeFila(MEJORA)).toBe('−8.500,00 €');
});

test('etiqueta «no es gasto del mes» en la línea secundaria, con la cuenta', () => {
  expect(secundariaFila(COMPRA)).toBe(`${TEXTO_NO_GASTO_MES} · Cuenta Nómina`);
  expect(secundariaFila(ITP)).toBe(`${TEXTO_NO_GASTO_MES} · Cuenta Nómina`);
  expect(secundariaFila(MEJORA)).toBe('Mejora · no es gasto del mes · Cuenta Nómina');
});

test('control: GASTO e INGRESO no cambian (signo, título, secundaria y marca)', () => {
  expect(importeFila(GASTO)).toBe('−48,72 €');
  expect(importeFila(INGRESO)).toBe('+2.100,00 €');
  expect(tituloFilaDia(GASTO)).toBe('Compra semanal');
  expect(secundariaFila(GASTO)).toBe('Sin categoría · Cuenta Nómina');
  expect(marcaReparto(GASTO)).toBeNull();
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

test('pantalla: la fila patrimonial muestra nombre, icono de propiedad, signo y etiqueta', async () => {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={fake([COMPRA, MEJORA, GASTO])} nuevoId={() => 'id'} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await act(async () => fireEvent.press(screen.getByTestId('tab-DIA')));
  await waitFor(() => expect(screen.getByTestId('fila-h0')).toBeTruthy());
  const glifo = (id: string) => within(screen.getByTestId(`actividad-icono-${id}`, { includeHiddenElements: true })).UNSAFE_queryByType(Ionicons)?.props.name ?? null;
  expect(glifo('h0')).toBe('home-outline');
  expect(glifo('m1')).toBe('home-outline');
  expect(glifo('g1')).not.toBe('home-outline');
  expect(screen.getByText('Compra de la propiedad')).toBeTruthy();
  expect(screen.getByText('Mejora · Cocina')).toBeTruthy();
  expect(screen.getByText('−200.000,00 €')).toBeTruthy();
  expect(screen.getByText(`${TEXTO_NO_GASTO_MES} · Cuenta Nómina`)).toBeTruthy();
});
