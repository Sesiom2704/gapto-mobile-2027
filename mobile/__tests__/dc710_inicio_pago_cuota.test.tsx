// ============================================================
// GAPTO MOBILE 2027
// Fichero: dc710_inicio_pago_cuota.test.tsx
// Ruta: mobile/__tests__/dc710_inicio_pago_cuota.test.tsx
// Descripción: D-C7-10 en Inicio («Requiere atención»; mandato F06 T4 DC710 v1.0 §2.1 y §2.4). La fila de una cuota sin dudas ofrece SOLO el lado principal (izquierda) «Pagado»; con dudas, ninguno; el «Pagado» paga por W-HIP-02 tras los 5 s con el payload del bloque y nunca por gasto-pagado. Misma lógica compartida que Pendientes (`useSwipePrevision`).
// Versión: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
// ============================================================

import './tiempos_rn';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { BloqueCuota, ClienteApi, FilaPrevision } from '../src/api/cliente';
import { HomeScreen } from '../src/screens/HomeScreen';
import { PLAZO_DESHACER_MS } from '../src/state/colaAccionRapida';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(() => Promise.resolve()),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
}));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const ok = (datos: unknown) => ({ tipo: 'OK', datos }) as any;
const PARTES = [{ actor_id: 'a-yo', porcentaje: '100.0000' }];
const BLOQUE: BloqueCuota = {
  financiacion_id: 'fin-9', numero: 4, financiacion_row_version: 11, fecha_vencimiento: '2026-09-30',
  cuenta_cargo: { id: 'cc', nombre: 'Cuenta hipoteca' }, propuesta_atribucion: PARTES, swipe_disponible: true, sin_dudas: true,
};
function cuota(q: Partial<BloqueCuota> = {}): FilaPrevision {
  return {
    id: 'cuota', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'CUOTA 4 HIPOTECA',
    tercero: null, categoria: null, fecha_desde: '2026-09-30', fecha_hasta: '2026-09-30', moneda: 'EUR', importe_esperado: '512.40',
    cubierto: '0.00', queda: '512.40', desviacion: null, con_realidad: false, pagos: 0, vencida: true,
    cuenta_salida: { id: 'cc', nombre: 'Cuenta hipoteca' }, cuenta_entrada: null, origen: 'MANUAL', presupuestable: true,
    codigo: 'PREVISION_DE_CUOTA', cuota: { ...BLOQUE, ...q },
  };
}
function cliente(f: FilaPrevision): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    inicioPrevisiones: jest.fn(async () => ok({ hoy: '2026-10-10', requiere_atencion: { n: 1, primeras: [f] }, proximos: [] })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h', idempotente: false })),
    omitirPrevision: jest.fn(async () => ok({})),
    pagarCuotaHipoteca: jest.fn(async (_: string, __: number, pl: any) => ok({ idempotente: false, hecho_id: pl.intencion_id, hipoteca: {} })),
  } as unknown as ClienteApi;
}
const asentar = async () => {
  for (let i = 0; i < 10; i++) await act(async () => undefined);
};
async function montar(c: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>
        <HomeScreen cliente={c} ahora={AHORA} refresco={0} onRegistrar={jest.fn()} nuevoId={nuevoId} onPendientes={jest.fn()} onPrevision={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await asentar();
}

beforeEach(async () => {
  n = 0;
  await AsyncStorage.clear();
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

test('Inicio: la cuota sin dudas ofrece SOLO «Pagado» a la izquierda y paga por W-HIP-02 tras 5 s', async () => {
  const c = cliente(cuota());
  await montar(c);
  expect(screen.getByTestId('atencion-cuota').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }]);
  fireEvent(screen.getByTestId('atencion-cuota'), 'accessibilityAction', { nativeEvent: { actionName: 'izquierda' } });
  await asentar();
  await act(async () => {
    jest.advanceTimersByTime(PLAZO_DESHACER_MS - 1);
  });
  expect(c.pagarCuotaHipoteca).not.toHaveBeenCalled();
  await act(async () => {
    jest.advanceTimersByTime(1);
  });
  await asentar();
  expect(c.pagarCuotaHipoteca).toHaveBeenCalledWith('fin-9', 4, {
    intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 11, cuenta_id: 'cc', fecha_pago: '2026-09-30',
    atribucion: { propuesta_vista: { partes: PARTES }, partes: PARTES },
  });
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(c.omitirPrevision).not.toHaveBeenCalled();
});

test('Inicio: con dudas la cuota no ofrece gesto', async () => {
  const c = cliente(cuota({ sin_dudas: false }));
  await montar(c);
  expect(screen.getByTestId('atencion-cuota').props.accessibilityActions).toBeUndefined();
});
