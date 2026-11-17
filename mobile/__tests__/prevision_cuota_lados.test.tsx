// ============================================================
// GAPTO MOBILE 2027
// Fichero: prevision_cuota_lados.test.tsx
// Ruta: mobile/__tests__/prevision_cuota_lados.test.tsx
// Descripción: Pieza Q3-C5 de la reapertura de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1 enmendado por ENMIENDA_LITERAL_F05_Q3_HD_v1.1_Y_CONTRATO_v0.4_L-HIP_v1.0, firma de Moisés 0f3e5633…, STOP_F06-T3-2_3 opción A). `lados()` de SwipePrevision.tsx no ofrece gestos sobre una fila marcada `codigo = PREVISION_DE_CUOTA`: en «Pendientes» la fila de la cuota solo tiene la acción de abrir (sin «Pagado» ni «No hubo») y el gesto completo no registra nada; control: la fila sin marca conserva los dos lados. Mata MQ3-C5.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, pieza Q3-C5)
// ============================================================

import './tiempos_rn';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, FilaPrevision } from '../src/api/cliente';
import { ESPERA_DESHACER_MS } from '../src/components/AccionRapida';
import { PendientesScreen } from '../src/screens/PendientesScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(() => Promise.resolve()),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
}));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';
const OCULTOS = { includeHiddenElements: true };
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const ok = (datos: unknown) => ({ tipo: 'OK', datos }) as any;

function fila(o: Partial<FilaPrevision> = {}): FilaPrevision {
  return {
    id: 'luz', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'Electricidad',
    tercero: { id: 'iber', nombre: 'Iberdrola' }, categoria: null, fecha_desde: '2026-10-01', fecha_hasta: '2026-10-05', moneda: 'EUR',
    importe_esperado: '74.00', cubierto: '0.00', queda: '74.00', desviacion: null, con_realidad: false, pagos: 0, vencida: true,
    cuenta_salida: { id: 'nomina', nombre: 'Cuenta nómina' }, cuenta_entrada: null, origen: 'V3', presupuestable: true, ...o,
  };
}
// La cuota cumple todas las demás condiciones del gesto: solo la marca la distingue del control.
const CUOTA = fila({ id: 'cuota', concepto: 'Cuota 2 hipoteca', importe_esperado: '632.19', queda: '632.19', codigo: 'PREVISION_DE_CUOTA' });
const CONTROL = fila();

function clientePendientes() {
  return {
    ...clienteCategoriasStub(),
    pendientesPrevisiones: jest.fn(async () => ok({ hoy: HOY, n: 2, por_pagar: { importe: '706.19', n: 2, desconocidos: 0 },
      por_cobrar: { importe: '0.00', n: 0, desconocidos: 0 }, secciones: { vencidas: [CUOTA, CONTROL], con_pago_parcial: [], sin_fecha: [] } })),
    cuentasPago: jest.fn(async () => ok({ cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] })),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }] })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h', idempotente: false })),
    omitirPrevision: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, prevision_id: 'x', estado: 'OMITIDA', row_version: 2 })),
  } as unknown as ClienteApi;
}

const asentar = async () => {
  for (let i = 0; i < 10; i++) await act(async () => undefined);
};

/** Gesto real completo sobre el contenedor común (mismo patrón que swipe_gestos.test.tsx). */
let reloj = 0;
function arrastrar(testID: string, recorrido: number[]): boolean {
  const z = screen.queryByTestId(testID);
  if (!z || !z.props.onMoveShouldSetResponderCapture) return false;
  const evento = (x: number) => {
    const ts = (reloj += 10);
    const toque = { touchActive: true, startPageX: 300, startPageY: 20, startTimeStamp: ts - 30,
      currentPageX: 300 + x, currentPageY: 20, currentTimeStamp: ts, previousPageX: 300, previousPageY: 20, previousTimeStamp: ts - 5 };
    return { nativeEvent: { changedTouches: [], touches: [], pageX: 300 + x, pageY: 20, timestamp: ts },
      touchHistory: { numberActiveTouches: 1, indexOfSingleActiveTouch: 0, mostRecentTimeStamp: ts, touchBank: [toque] } };
  };
  let captura = false;
  act(() => {
    captura = z.props.onMoveShouldSetResponderCapture(evento(recorrido[0]));
    if (!captura) return;
    z.props.onResponderGrant(evento(recorrido[0]));
    for (const x of recorrido) z.props.onResponderMove(evento(x));
    z.props.onResponderRelease(evento(recorrido[recorrido.length - 1]));
  });
  return captura;
}

beforeEach(async () => {
  n = 0;
  await AsyncStorage.clear();
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

async function montar(c: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>
        <PendientesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} refresco={0} onAtras={jest.fn()} onDetalle={jest.fn()}
          onFormularioCompleto={jest.fn()} onCambios={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await asentar();
}

test('Q3-C5: la fila marcada PREVISION_DE_CUOTA no ofrece gestos; la misma fila sin marca conserva «Pagado» y «No hubo»', async () => {
  const c = clientePendientes();
  await montar(c);
  // cuota: fila simple (sin acciones de gesto): ni lado izquierdo ni derecho
  expect(screen.getByTestId('pendiente-cuota').props.accessibilityActions).toBeUndefined();
  expect(screen.queryByTestId('fila-swipe-pendiente-cuota')).toBeNull();
  // control: los dos lados
  expect(screen.getByTestId('pendiente-luz').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }, { name: 'derecha', label: 'No hubo' }]);
});

test('Q3-C5: el gesto completo sobre la cuota no abre botones ni registra ni omite nada', async () => {
  const c = clientePendientes();
  await montar(c);
  arrastrar('fila-swipe-pendiente-cuota', [-30, -100, -200, -260]);
  await asentar();
  arrastrar('fila-swipe-pendiente-cuota', [30, 100, 200, 260]);
  await asentar();
  expect(screen.queryByTestId('swipe-boton-pendiente-cuota-izquierda', OCULTOS)).toBeNull();
  expect(screen.queryByTestId('swipe-boton-pendiente-cuota-derecha', OCULTOS)).toBeNull();
  expect(screen.queryByTestId('aviso-rapida-cuota-texto')).toBeNull();
  await act(async () => {
    jest.advanceTimersByTime(ESPERA_DESHACER_MS * 2);
  });
  await asentar();
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(c.omitirPrevision).not.toHaveBeenCalled();
});
