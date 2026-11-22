// ============================================================
// GAPTO MOBILE 2027
// Fichero: mant_n3_obs04_prorroga.test.tsx
// Ruta: mobile/__tests__/mant_n3_obs04_prorroga.test.tsx
// Descripción: OBS-04 del acta C7 del tren v1.2 (§8.1; deuda MANT N3 de cliente): tras guardar una prórroga, el detalle del contrato muestra el fin que devuelve el servidor (sin reabrir la app), la tarea «Prorrogar» vuelve a abrirse con ese fin como «actual», y al volver a la lista se vuelve a pedir la lista y el detalle. Caso del acta: prórroga al 15/11/2027 (la app mostró 14/11/2027 hasta reabrir Expo Go).
// Versión: 0.1.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; OBS-04)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ContratoDetalleScreen, ContratosFlujo } from '../src/screens/ContratosScreen';
import { ProveedorTema } from '../src/theme/tema';
import { AHORA, clienteApi, clienteContratos, detalle, METRICAS, nuevoId, ok, reiniciarIds, vista } from './contratos_fixtures';

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
beforeEach(() => reiniciarIds());
const envolver = (hijo: React.ReactNode) => (
  <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar="light">{hijo}</ProveedorTema></SafeAreaProvider>
);

const ANTES = detalle({ fecha_fin_prevista: '2026-11-15', row_version: 3 });
const DESPUES = detalle({ fecha_fin_prevista: '2027-11-15', row_version: 4 });

/** Doble con estado, como el servidor: tras guardar la prórroga, la lectura del contrato devuelve lo guardado. */
function contratosConProrroga() {
  let guardado = ANTES;
  return clienteContratos({
    contrato: jest.fn(async () => ok({ contrato: guardado })),
    editarContrato: jest.fn(async () => {
      guardado = DESPUES;
      return ok({ contrato_id: 'c1', row_version: 4, idempotente: false, contrato: DESPUES });
    }),
  });
}

async function prorrogar() {
  await waitFor(() => screen.getByTestId('contrato-prorrogar-abrir'));
  await pulsar('contrato-prorrogar-abrir');
  expect(screen.getByTestId('contrato-prorrogar-actual-valor').props.children).toBe('15 nov 2026');
  await escribir('contrato-prorrogar-fin', '15/11/2027');
  await escribir('contrato-prorrogar-motivo', 'Prórroga anual');
  await pulsar('contrato-prorrogar-guardar');
  await waitFor(() => screen.getByTestId('contrato-detalle'));
}

test('OBS-04: tras guardar la prórroga, el detalle muestra el nuevo fin sin recargar', async () => {
  const contratos = contratosConProrroga();
  render(envolver(<ContratoDetalleScreen contratos={contratos} contratoId="c1" nuevoId={nuevoId} ahora={AHORA}
    onAtras={jest.fn()} onCambios={jest.fn()} onTercero={jest.fn()} onSucesor={jest.fn()} onTratamientos={jest.fn()} />));
  await waitFor(() => screen.getByTestId('contrato-fechas'));
  expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 15 nov 2026');
  await prorrogar();
  expect(contratos.editarContrato).toHaveBeenCalledWith('c1', expect.objectContaining({ fecha_fin_prevista: '2027-11-15', row_version_esperada: 3 }));
  await waitFor(() => expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 15 nov 2027'));
  // lo muestra la respuesta del guardado; fuera del flujo no hay otra lectura
  expect(contratos.contrato).toHaveBeenCalledTimes(1);
  await pulsar('contrato-prorrogar-abrir');
  expect(screen.getByTestId('contrato-prorrogar-actual-valor').props.children).toBe('15 nov 2027');
});

test('OBS-04: al volver a la lista tras la prórroga se vuelven a pedir la lista y el detalle', async () => {
  const contratos = contratosConProrroga();
  render(envolver(<ContratosFlujo cliente={clienteApi()} contratos={contratos} propiedad={vista()} nuevoId={nuevoId} ahora={AHORA} onSalir={jest.fn()} />));
  await waitFor(() => screen.getByTestId('contrato-fila-c1'));
  const listas = (contratos.contratosDePropiedad as jest.Mock).mock.calls.length;
  await pulsar('contrato-fila-c1');
  await waitFor(() => screen.getByTestId('contrato-detalle'));
  const lecturas = (contratos.contrato as jest.Mock).mock.calls.length;
  await prorrogar();
  await waitFor(() => expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 15 nov 2027'));
  // dentro del flujo, guardar sube `refresco` y el detalle vuelve a leer el contrato del servidor
  await waitFor(() => expect((contratos.contrato as jest.Mock).mock.calls.length).toBeGreaterThan(lecturas));
  expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 15 nov 2027');
  await pulsar('contrato-detalle-atras');
  await waitFor(() => screen.getByTestId('contratos-lista'));
  await waitFor(() => expect((contratos.contratosDePropiedad as jest.Mock).mock.calls.length).toBeGreaterThan(listas));
  await pulsar('contrato-fila-c1');
  await waitFor(() => expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 15 nov 2027'));
});
