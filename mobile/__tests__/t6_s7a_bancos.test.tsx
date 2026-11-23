// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s7a_bancos.test.tsx
// Ruta: mobile/__tests__/t6_s7a_bancos.test.tsx
// Descripción: F06 T6 · S7-A (N2; DP-09, DT-04; F09 0.55 §12.107.3) en el cliente:
//   - el selector de Banco (modo `soloBancos`) pide SOLO los bancos al servidor (discriminante «selector sin filtro»), sin
//     «Sin tercero»; sin ninguno, «Marca tus bancos en Ajustes → Terceros»;
//   - «+ Crear banco» crea el tercero y lo marca con el rol ENTIDAD_FINANCIERA (discriminante «rol no persistido»); si el
//     rol no se escribe, lo dice y no lo elige;
//   - en Compra, «Banco» usa ese modo;
//   - en Ajustes → Terceros, la casilla «Es banco o entidad financiera» añade el rol al guardar.
// Versión: 0.1.0 (F06 T6 · S7-A)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta, Tercero } from '../src/api/cliente';
import type { ClienteContratos } from '../src/api/contratos';
import { SelectorTercero, TEXTO_BANCO_SIN_MARCAR, TEXTO_SIN_BANCOS } from '../src/components/SelectorTercero';
import { TercerosAjustesScreen } from '../src/screens/TercerosAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

declare const __dirname: string;
const fs: { readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const fuente = (rel: string) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const ter = (x: Partial<Tercero>): Tercero => ({ id: 'b1', nombre: 'Banco Ejemplo', naturaleza: 'EMPRESA', enabled: true, row_version: 1, ...x });
const envolver = (el: React.ReactElement) =>
  render(<SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar="light">{el}</ProveedorTema></SafeAreaProvider>);
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));

function cliente(bancos: Tercero[]) {
  return {
    listarTerceros: jest.fn(async (o?: { rol?: string }) => ok({ terceros: o?.rol ? bancos : [...bancos, ter({ id: 'x', nombre: 'Super ALDI' })] })),
    candidatosTercero: jest.fn(async () => ok({ terceros: [] })),
    altaTercero: jest.fn(async (c: { id: string; nombre: string }) => ok({ tercero: ter({ id: c.id, nombre: c.nombre, row_version: 1 }) })),
    senalesTerceros: jest.fn(async () => ok({ terceros: [] })),
    buscarTerceros: jest.fn(async () => ok({ terceros: [] })),
  } as unknown as ClienteApi & Record<string, jest.Mock>;
}

test('selector de bancos: pide solo los bancos, sin «Sin tercero»', async () => {
  const c = cliente([ter({})]);
  envolver(<SelectorTercero cliente={c} nuevoId={() => 'n1'} titulo="Banco" seleccionadoId={null} onElegir={jest.fn()} onCerrar={jest.fn()}
    soloBancos={{ marcar: jest.fn(async () => true) }} />);
  await waitFor(() => screen.getByTestId('tercero-b1'));
  expect(c.listarTerceros).toHaveBeenCalledWith({ rol: 'ENTIDAD_FINANCIERA' });            // selector con filtro
  expect(screen.queryByTestId('tercero-x')).toBeNull();
  expect(screen.queryByTestId('tercero-ninguno')).toBeNull();
});

test('sin bancos: estado vacío; «+ Crear banco» crea y marca el rol; si no se marca, avisa y no elige', async () => {
  const c = cliente([]);
  const marcar = jest.fn(async () => true);
  const elegir = jest.fn();
  envolver(<SelectorTercero cliente={c} nuevoId={() => 'n1'} titulo="Banco" seleccionadoId={null} onElegir={elegir} onCerrar={jest.fn()} soloBancos={{ marcar }} />);
  await waitFor(() => screen.getByTestId('bancos-vacio'));
  expect(JSON.stringify(screen.getByTestId('bancos-vacio').props.children)).toContain(TEXTO_SIN_BANCOS);
  await act(async () => fireEvent.changeText(screen.getByTestId('tercero-filtro'), 'Caja Rural'));
  await pulsar('tercero-crear');
  expect(c.altaTercero).toHaveBeenCalledWith(expect.objectContaining({ nombre: 'Caja Rural' }));
  expect(marcar).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1', nombre: 'Caja Rural' }));   // rol persistido
  expect(elegir).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1' }));
});

test('«+ Crear banco» con el rol sin escribir: aviso y no se elige', async () => {
  const c = cliente([]);
  const elegir = jest.fn();
  envolver(<SelectorTercero cliente={c} nuevoId={() => 'n2'} titulo="Banco" seleccionadoId={null} onElegir={elegir} onCerrar={jest.fn()}
    soloBancos={{ marcar: jest.fn(async () => false) }} />);
  await waitFor(() => screen.getByTestId('bancos-vacio'));
  await act(async () => fireEvent.changeText(screen.getByTestId('tercero-filtro'), 'Caja'));
  await pulsar('tercero-crear');
  expect(elegir).not.toHaveBeenCalled();
  expect(screen.getByText(TEXTO_BANCO_SIN_MARCAR)).toBeTruthy();
});

test('Compra: «Banco» usa el selector en modo solo bancos y marca con ENTIDAD_FINANCIERA', () => {
  const t = fuente('src/screens/CompraScreen.tsx');
  expect(t).toMatch(/soloBancos=\{\{ marcar: marcarBanco \}\}/);
  expect(t).toMatch(/anadir: \['ENTIDAD_FINANCIERA'\]/);
});

test('Ajustes → Terceros: la casilla «Es banco o entidad financiera» añade el rol al guardar', async () => {
  const c = cliente([]);
  (c as any).listarAfinidades = jest.fn(async () => ok({}));
  const contratos = { anadirRoles: jest.fn(async () => ok({})) } as unknown as ClienteContratos & Record<string, jest.Mock>;
  let n = 0;
  envolver(<TercerosAjustesScreen cliente={c} nuevoId={() => `id-${++n}`} onAtras={jest.fn()} onInmersiva={jest.fn()} contratos={contratos} />);
  await waitFor(() => screen.getByTestId('ajter-nuevo'));
  await pulsar('ajter-nuevo');
  fireEvent.changeText(screen.getByTestId('ajter-nombre'), 'Banco Nuevo');
  await pulsar('ajter-banco');
  await pulsar('ajter-guardar');
  await waitFor(() => expect(contratos.anadirRoles).toHaveBeenCalled());
  const [id, cuerpo] = (contratos.anadirRoles as jest.Mock).mock.calls[0];
  expect(id).toBe('id-1');
  expect(cuerpo).toMatchObject({ row_version_esperada: 1, anadir: ['ENTIDAD_FINANCIERA'] });
});
