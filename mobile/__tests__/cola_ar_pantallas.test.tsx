// ============================================================
// GAPTO MOBILE 2027
// Fichero: cola_ar_pantallas.test.tsx
// Ruta: mobile/__tests__/cola_ar_pantallas.test.tsx
// Descripción: COLA-AR v1.0 (F05 §70.A) en pantalla, con el caso de S1 (STOP-PA-A6-R: «Pendiente con» con una sola cuenta elegible). El aviso GLOBAL (el que monta la raíz) sigue visible y con «Deshacer» al salir de la pantalla; desmontar no cancela ni adelanta el envío; al volver, la fila sigue fuera y hay un solo aviso; ni ✓ ni «Saldado» antes del 2xx (también mientras la petición está en vuelo); cerrar y reabrir la app pregunta «Enviar / Descartar» con la misma identidad.
// Versión: 0.1.0 (F05-D056 paso 2)
// ============================================================

import './tiempos_rn';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi } from '../src/api/cliente';
import { AvisosCola, colaDe } from '../src/components/ColaAccionRapida';
import type { PendienteConPersona } from '../src/domain/reparto';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { PLAZO_DESHACER_MS } from '../src/state/colaAccionRapida';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const ok = (datos: unknown) => ({ tipo: 'OK', datos }) as any;

const PEND: PendienteConPersona = {
  tercero_id: 'marta', nombre: 'Marta', te_debe: '40.00', le_debes: '0.00', neto: '40.00', neto_estado: 'DETERMINADO',
  posiciones: [
    { entidad_id: 'd1', entidad_row_version: 1, tipo: 'DERECHO_COBRO', nombre: 'Pendiente de cobro · Combustible', saldo: '40.00', estado: 'ACTIVA',
      apertura_indeterminada: false, origen_hecho_id: 'gasoil', origen_fecha: '2026-10-09', origen_concepto: 'Gasoil' },
  ],
};
const UNA = [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }];

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    pendienteCon: jest.fn(async () => ok(PEND)),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: UNA })),
    cobrarPosicion: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h', entidad_id: 'd1', idempotente: false,
      importe: pl.importe, saldo: '0.00', estado: 'CERRADA', apertura_indeterminada: false, aviso: '' })),
    ...o,
  } as ClienteApi;
}

/** La raíz de la app: el aviso global y, si está «abierta», la pantalla «Pendiente con». */
function App(p: { c: ClienteApi; abierta: boolean }) {
  return (
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>
        <View style={{ flex: 1 }}>
          {p.abierta ? <PendienteConScreen cliente={p.c} nuevoId={nuevoId} ahora={AHORA} terceroId="marta" nombre="Marta" onCerrar={jest.fn()} /> : null}
          <AvisosCola cola={colaDe(p.c)} global />
        </View>
      </ProveedorTema>
    </SafeAreaProvider>
  );
}
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
const asentar = async () => {
  for (let i = 0; i < 10; i++) await act(async () => undefined);
};
const accion = (testID: string, nombre: string) => fireEvent(screen.getByTestId(testID), 'accessibilityAction', { nativeEvent: { actionName: nombre } });

beforeEach(async () => {
  n = 0;
  await AsyncStorage.clear();
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

test('S1 (STOP-PA-A6-R): «Cobrando…» sin ✓ durante el plazo y con la petición en vuelo; ✓ y «Saldado» solo tras el 2xx', async () => {
  let responder: (r: any) => void = () => undefined;
  const c = cliente({ cobrarPosicion: jest.fn(() => new Promise((res) => (responder = res))) as any });
  render(<App c={c} abierta />);
  await asentar();
  accion('posicion-d1', 'izquierda');
  expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Cobrando… · Marta · 40,00 €');
  expect(screen.queryByTestId('aviso-rapida-d1-ok')).toBeNull();
  expect(screen.queryByText(/Saldado/)).toBeNull();
  await esperar(PLAZO_DESHACER_MS);
  await asentar();
  expect(c.cobrarPosicion).toHaveBeenCalledTimes(1); // en vuelo, sin respuesta todavía
  expect(screen.queryByTestId('aviso-rapida-d1-ok')).toBeNull();
  expect(screen.queryByText(/Saldado/)).toBeNull();
  expect(screen.queryByTestId('aviso-rapida-d1-deshacer')).toBeNull(); // pasado el plazo ya no se deshace
  await act(async () => responder(ok({ intencion_id: 'x', hecho_id: 'h', entidad_id: 'd1', idempotente: false, importe: '40.00', saldo: '0.00',
    estado: 'CERRADA', apertura_indeterminada: false, aviso: '' })));
  await asentar();
  expect(screen.getByTestId('aviso-rapida-d1-ok')).toBeTruthy();
  expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Saldado · no cuenta como ingreso');
});

test('A.6 3 y 4: salir de la pantalla en el plazo no cancela ni adelanta; el aviso global sigue con «Deshacer»; al volver, la fila sigue fuera y un solo aviso', async () => {
  const c = cliente();
  const r = render(<App c={c} abierta />);
  await asentar();
  accion('posicion-d1', 'izquierda');
  await esperar(1000);
  r.rerender(<App c={c} abierta={false} />); // navega fuera: la pantalla se desmonta
  await asentar();
  expect(screen.queryByTestId('posicion-d1')).toBeNull();
  expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Cobrando… · Marta · 40,00 €');
  expect(screen.getByTestId('aviso-rapida-d1-deshacer').props.accessibilityLabel).toBe('Deshacer, quedan 4 segundos');
  await esperar(PLAZO_DESHACER_MS - 1001);
  expect(c.cobrarPosicion).not.toHaveBeenCalled();
  r.rerender(<App c={c} abierta />); // vuelve
  await asentar();
  expect(screen.queryByTestId('posicion-d1')).toBeNull(); // sigue fuera mientras la intención vive
  expect(screen.getAllByTestId('aviso-rapida-d1')).toHaveLength(1); // el de la pantalla cede ante el global
  await esperar(1);
  await asentar();
  expect(c.cobrarPosicion).toHaveBeenCalledTimes(1);
  expect(c.cobrarPosicion).toHaveBeenCalledWith('d1', { intencion_id: '00000000-0000-4000-8000-000000000001', importe: '40.00', cuenta_id: 'nomina', fecha: '2026-10-10' });
});

test('«Deshacer» desde el aviso global después de salir de la pantalla: nada se envía', async () => {
  const c = cliente();
  const r = render(<App c={c} abierta />);
  await asentar();
  accion('posicion-d1', 'izquierda');
  r.rerender(<App c={c} abierta={false} />);
  await asentar();
  fireEvent.press(screen.getByTestId('aviso-rapida-d1-deshacer'));
  await esperar(PLAZO_DESHACER_MS * 3);
  await asentar();
  expect(c.cobrarPosicion).not.toHaveBeenCalled();
  expect(c.yo).not.toHaveBeenCalled();
  expect(screen.queryByTestId('aviso-rapida-d1')).toBeNull();
});

test('A.6 6: cerrar la app en el plazo y reabrirla después pregunta «Enviar / Descartar»; «Enviar» usa la misma identidad', async () => {
  const c1 = cliente();
  const r = render(<App c={c1} abierta />);
  await asentar();
  accion('posicion-d1', 'izquierda');
  await esperar(2000);
  await asentar();
  r.unmount(); // la app se cierra (el proceso muere: sus temporizadores no cuentan)
  jest.clearAllTimers();
  await esperar(3_600_000);
  const c2 = cliente(); // nueva sesión de la app: otro cliente, otra cola, el mismo dispositivo
  render(<App c={c2} abierta />);
  await asentar();
  expect(c2.cobrarPosicion).not.toHaveBeenCalled(); // nunca envío automático al reabrir
  expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Cobro pendiente: Cobrado de Marta · 40,00 €');
  expect(screen.queryByTestId('posicion-d1')).toBeNull();
  fireEvent.press(screen.getByTestId('aviso-rapida-d1-enviar'));
  await asentar();
  expect(c2.cobrarPosicion).toHaveBeenCalledTimes(1);
  expect((c2.cobrarPosicion as jest.Mock).mock.calls[0][1].intencion_id).toBe('00000000-0000-4000-8000-000000000001');
  expect(c1.cobrarPosicion).not.toHaveBeenCalled();
});

test('A.6 6: «Descartar» tras reabrir cancela sin envío y la posición vuelve', async () => {
  const c1 = cliente();
  const r = render(<App c={c1} abierta />);
  await asentar();
  accion('posicion-d1', 'izquierda');
  await asentar();
  r.unmount();
  jest.clearAllTimers();
  await esperar(3_600_000);
  const c2 = cliente();
  render(<App c={c2} abierta />);
  await asentar();
  fireEvent.press(screen.getByTestId('aviso-rapida-d1-descartar'));
  await asentar();
  await esperar(60000);
  expect(c2.cobrarPosicion).not.toHaveBeenCalled();
  expect(screen.getByTestId('posicion-d1')).toBeTruthy();
});
