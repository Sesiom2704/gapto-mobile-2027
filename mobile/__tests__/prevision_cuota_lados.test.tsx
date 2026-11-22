// ============================================================
// GAPTO MOBILE 2027
// Fichero: prevision_cuota_lados.test.tsx
// Ruta: mobile/__tests__/prevision_cuota_lados.test.tsx
// Descripción: Pieza Q3-C5 de la reapertura de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1 enmendado por ENMIENDA_LITERAL_F05_Q3_HD_v1.1_Y_CONTRATO_v0.4_L-HIP_v1.0, firma de Moisés 0f3e5633…, STOP_F06-T3-2_3 opción A), versionada por D-C7-10 (Q3-Hd v1.2 candidato; opción A de Moisés: con dudas no hay gesto; F09 §12.106 punto 1). `lados()` de SwipePrevision.tsx sobre una fila marcada `codigo = PREVISION_DE_CUOTA`: sin bloque o con dudas, ningún gesto (y el gesto completo no registra, ni omite, ni paga); con `swipe_disponible` y `sin_dudas`, SOLO el lado principal (izquierda) «Pagado», nunca «No hubo». El «Pagado» va a la cola COLA-AR por W-HIP-02: nada antes de 5 s, «Deshacer» no envía, y al vencer una sola llamada con el payload exacto del bloque; nunca gasto-pagado ni omitir. Control: la fila sin marca conserva los dos lados. Mata MQ3-C5 y los mutantes del lado y la ruta de D-C7-10.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, pieza Q3-C5)
// Versión: 0.2.0 (F06 T4 · D-C7-10, mandato 7041970a…; Q3-Hd v1.2 candidato)
// ============================================================

import './tiempos_rn';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { BloqueCuota, ClienteApi, FilaPrevision } from '../src/api/cliente';
import { ESPERA_DESHACER_MS } from '../src/components/AccionRapida';
import { PendientesScreen } from '../src/screens/PendientesScreen';
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
const PARTES = [{ actor_id: 'a-yo', porcentaje: '60.0000' }, { actor_id: 'b-ana', porcentaje: '40.0000' }];
const BLOQUE: BloqueCuota = {
  financiacion_id: 'fin-1', numero: 2, financiacion_row_version: 5, fecha_vencimiento: '2026-05-20',
  cuenta_cargo: { id: 'cc', nombre: 'Cuenta común' }, propuesta_atribucion: PARTES, swipe_disponible: true, sin_dudas: true,
};
// La cuota cumple todas las demás condiciones del gesto ordinario: solo la marca (y su bloque) la distingue del control.
const CUOTA = fila({ id: 'cuota', concepto: 'Cuota 2 hipoteca', importe_esperado: '632.19', queda: '632.19', codigo: 'PREVISION_DE_CUOTA' });
const CUOTA_OK: FilaPrevision = { ...CUOTA, cuota: BLOQUE };
const CUOTA_DUDAS: FilaPrevision = { ...CUOTA, cuota: { ...BLOQUE, sin_dudas: false } };
const CONTROL = fila();

function clientePendientes(cuota: FilaPrevision = CUOTA) {
  return {
    ...clienteCategoriasStub(),
    pendientesPrevisiones: jest.fn(async () => ok({ hoy: HOY, n: 2, por_pagar: { importe: '706.19', n: 2, desconocidos: 0 },
      por_cobrar: { importe: '0.00', n: 0, desconocidos: 0 }, secciones: { vencidas: [cuota, CONTROL], con_pago_parcial: [], sin_fecha: [] } })),
    cuentasPago: jest.fn(async () => ok({ cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] })),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }] })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h', idempotente: false })),
    omitirPrevision: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, prevision_id: 'x', estado: 'OMITIDA', row_version: 2 })),
    pagarCuotaHipoteca: jest.fn(async (_: string, __: number, pl: any) => ok({ idempotente: false, hecho_id: pl.intencion_id, hipoteca: {} })),
  } as unknown as ClienteApi;
}

const asentar = async () => {
  for (let i = 0; i < 10; i++) await act(async () => undefined);
};
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
const accion = (testID: string, nombre: string) => fireEvent(screen.getByTestId(testID), 'accessibilityAction', { nativeEvent: { actionName: nombre } });

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

const sinEscrituras = (c: ClienteApi) => {
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(c.omitirPrevision).not.toHaveBeenCalled();
  expect(c.pagarCuotaHipoteca).not.toHaveBeenCalled();
};

test('Q3-C5: la fila marcada PREVISION_DE_CUOTA sin bloque no ofrece gestos; la misma fila sin marca conserva «Pagado» y «No hubo»', async () => {
  const c = clientePendientes();
  await montar(c);
  expect(screen.getByTestId('pendiente-cuota').props.accessibilityActions).toBeUndefined();
  expect(screen.queryByTestId('fila-swipe-pendiente-cuota')).toBeNull();
  expect(screen.getByTestId('pendiente-luz').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }, { name: 'derecha', label: 'No hubo' }]);
});

test('Q3-C5: el gesto completo sobre la cuota sin bloque no abre botones ni registra ni omite ni paga nada', async () => {
  const c = clientePendientes();
  await montar(c);
  arrastrar('fila-swipe-pendiente-cuota', [-30, -100, -200, -260]);
  await asentar();
  arrastrar('fila-swipe-pendiente-cuota', [30, 100, 200, 260]);
  await asentar();
  expect(screen.queryByTestId('swipe-boton-pendiente-cuota-izquierda', OCULTOS)).toBeNull();
  expect(screen.queryByTestId('swipe-boton-pendiente-cuota-derecha', OCULTOS)).toBeNull();
  expect(screen.queryByTestId('aviso-rapida-cuota-texto')).toBeNull();
  await esperar(ESPERA_DESHACER_MS * 2);
  await asentar();
  sinEscrituras(c);
});

test('Q3-C5 v1.2 (opción A): con dudas tampoco hay gesto, aunque el servidor diga swipe_disponible', async () => {
  const c = clientePendientes(CUOTA_DUDAS);
  await montar(c);
  expect(screen.getByTestId('pendiente-cuota').props.accessibilityActions).toBeUndefined();
  expect(screen.queryByTestId('fila-swipe-pendiente-cuota')).toBeNull();
  await esperar(PLAZO_DESHACER_MS * 2);
  sinEscrituras(c);
});

test('Q3-C5 v1.2: sin dudas, SOLO el lado principal (izquierda) «Pagado»; nunca «No hubo» ni lado alternativo', async () => {
  const c = clientePendientes(CUOTA_OK);
  await montar(c);
  expect(screen.getByTestId('pendiente-cuota').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }]);
  // la acción del lado que no existe no hace nada
  accion('pendiente-cuota', 'derecha');
  await esperar(PLAZO_DESHACER_MS * 2);
  await asentar();
  sinEscrituras(c);
});

test('«Pagado»: nada antes de 5 s; al vencer, UNA llamada a W-HIP-02 con el payload exacto del bloque; nunca gasto-pagado ni omitir', async () => {
  const c = clientePendientes(CUOTA_OK);
  await montar(c);
  accion('pendiente-cuota', 'izquierda');
  await asentar();
  expect(screen.getByTestId('aviso-rapida-cuota-texto')).toHaveTextContent('Pagando… · Cuota 2 hipoteca · 632,19 €');
  await esperar(PLAZO_DESHACER_MS - 1);
  await asentar();
  expect(c.pagarCuotaHipoteca).not.toHaveBeenCalled();
  await esperar(1);
  await asentar();
  expect(c.pagarCuotaHipoteca).toHaveBeenCalledTimes(1);
  expect(c.pagarCuotaHipoteca).toHaveBeenCalledWith('fin-1', 2, {
    intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 5, cuenta_id: 'cc', fecha_pago: '2026-05-20',
    atribucion: { propuesta_vista: { partes: PARTES }, partes: PARTES },
  });
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(c.omitirPrevision).not.toHaveBeenCalled();
  expect(screen.getByTestId('aviso-rapida-cuota-texto')).toHaveTextContent('Cuota 2 hipoteca pagada · 632,19 €');
});

test('«Deshacer» dentro de los 5 s: la cuota no se paga nunca', async () => {
  const c = clientePendientes(CUOTA_OK);
  await montar(c);
  accion('pendiente-cuota', 'izquierda');
  await asentar();
  await esperar(PLAZO_DESHACER_MS - 1000);
  fireEvent.press(screen.getByTestId('aviso-rapida-cuota-deshacer'));
  await esperar(PLAZO_DESHACER_MS * 3);
  await asentar();
  sinEscrituras(c);
});
