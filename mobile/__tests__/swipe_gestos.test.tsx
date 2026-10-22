// ============================================================
// GAPTO MOBILE 2027
// Fichero: swipe_gestos.test.tsx
// Ruta: mobile/__tests__/swipe_gestos.test.tsx
// Descripción: Gesto común del swipe tras la pasada de Moisés en el iPhone (F05-06 M5 SWIPE3; lámina SWIPE-01 v0.3). Lados invertidos con el gesto real en cada pantalla: a la IZQUIERDA la principal (verde: Pagado / Cobrado / Recibido / Repetir hoy), a la DERECHA la alternativa (No hubo / Más en gris; Desactivar en naranja); el círculo aparece en el lado que se descubre. Fila abierta a medias (patrón iOS): se cierra al abrir otra, al hacer scroll y al tocar fuera; tocar su botón la ejecuta y tocar la fila abre su detalle. Vibración con `expo-haptics` simulado: una sola vez al cruzar el umbral, impacto medio; si el módulo falla, aviso en consola y `Vibration` de reserva.
// Versión: 0.1.0 (F05-06 M5 SWIPE3)
// Versión: 0.2.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): importa `tiempos_rn` (30 s por test y 5 s de `waitFor`/`findBy`) contra la intermitencia en frío de las suites de pantalla; sin cambios de aserciones.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, within } from '@testing-library/react-native';
import * as Haptics from 'expo-haptics';
import React from 'react';
import { StyleSheet, Vibration } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, DetalleActividad, FilaActividad, FilaPrevision, Tercero } from '../src/api/cliente';
import { ESPERA_DESHACER_MS, PRINCIPAL_SE_DESLIZA } from '../src/components/AccionRapida';
import type { PendienteConPersona } from '../src/domain/reparto';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { PendientesScreen } from '../src/screens/PendientesScreen';
import { TercerosAjustesScreen } from '../src/screens/TercerosAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

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

function envolver(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
const asentar = async () => {
  for (let i = 0; i < 6; i++) await act(async () => undefined);
};

/** Gesto real sobre el contenedor común: se toma con el primer valor y se mueve por los siguientes; suelta en el último. */
let reloj = 0;
function arrastrar(testID: string, recorrido: number[]): boolean {
  const z = screen.getByTestId(testID);
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
const deslizar = (testID: string, dx: number) => arrastrar(testID, [dx / 3, dx]);
const fondo = (testID: string) => StyleSheet.flatten(screen.getByTestId(testID).props.style).backgroundColor;

beforeEach(() => {
  n = 0;
  jest.useFakeTimers();
  (Haptics.impactAsync as jest.Mock).mockClear();
  (Haptics.impactAsync as jest.Mock).mockImplementation(() => Promise.resolve());
});
afterEach(() => {
  jest.useRealTimers();
});

test('la acción principal se desliza a la izquierda (decisión de Moisés, SWIPE-01 v0.3)', () => {
  expect(PRINCIPAL_SE_DESLIZA).toBe('izquierda');
});

// ==================================================================
// Pendientes (previsiones)
// ==================================================================
function fila(o: Partial<FilaPrevision> = {}): FilaPrevision {
  return {
    id: 'luz', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'Electricidad',
    tercero: { id: 'iber', nombre: 'Iberdrola' }, categoria: null, fecha_desde: '2026-10-01', fecha_hasta: '2026-10-05', moneda: 'EUR',
    importe_esperado: '74.00', cubierto: '0.00', queda: '74.00', desviacion: null, con_realidad: false, pagos: 0, vencida: true,
    cuenta_salida: { id: 'nomina', nombre: 'Cuenta nómina' }, cuenta_entrada: null, origen: 'V3', presupuestable: true, ...o,
  };
}
const NOMINA = fila({ id: 'nom', tipo: 'INGRESO', naturaleza: 'POR_COBRAR', concepto: 'Nómina', importe_esperado: '2100.00', queda: '2100.00',
  cuenta_salida: null, cuenta_entrada: { id: 'nomina', nombre: 'Cuenta nómina' } });
function clientePendientes(o: Partial<ClienteApi> = {}) {
  return {
    ...clienteCategoriasStub(),
    pendientesPrevisiones: jest.fn(async () => ok({ hoy: HOY, n: 2, por_pagar: { importe: '74.00', n: 1, desconocidos: 0 },
      por_cobrar: { importe: '2100.00', n: 1, desconocidos: 0 }, secciones: { vencidas: [fila(), NOMINA], con_pago_parcial: [], sin_fecha: [] } })),
    cuentasPago: jest.fn(async () => ok({ cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] })),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }] })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h', idempotente: false })),
    omitirPrevision: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, prevision_id: 'luz', estado: 'OMITIDA', row_version: 2 })),
    ...o,
  } as ClienteApi;
}
async function montarPendientes(c: ClienteApi, onDetalle = jest.fn()) {
  envolver(<PendientesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} refresco={0} onAtras={jest.fn()} onDetalle={onDetalle}
    onFormularioCompleto={jest.fn()} onCambios={jest.fn()} />);
  await asentar();
}

describe('Pendientes: lados invertidos', () => {
  test('izquierda del todo = «Pagado» (verde, círculo a la derecha); derecha del todo = «No hubo» (gris, círculo a la izquierda)', async () => {
    const c = clientePendientes();
    await montarPendientes(c);
    // a medias a la izquierda: verde con «Pagado» al lado derecho
    expect(deslizar('fila-swipe-pendiente-luz', -100)).toBe(true);
    await asentar();
    expect(fondo('fila-swipe-pendiente-luz')).toBe(colores.light.accentSurface);
    const izq = screen.getByTestId('swipe-accion-pendiente-luz-izquierda', OCULTOS);
    expect(StyleSheet.flatten(izq.props.style).justifyContent).toBe('flex-end');
    expect(within(screen.getByTestId('swipe-boton-pendiente-luz-izquierda', OCULTOS)).getByText('Pagado', OCULTOS)).toBeTruthy();
    fireEvent(screen.getByTestId('pendientes'), 'touchStart'); // tocar fuera la cierra
    await asentar();
    // a medias a la derecha: gris con «No hubo» al lado izquierdo
    expect(deslizar('fila-swipe-pendiente-luz', 100)).toBe(true);
    await asentar();
    expect(fondo('fila-swipe-pendiente-luz')).toBe(colores.light.surfaceSecondary);
    const der = screen.getByTestId('swipe-accion-pendiente-luz-derecha', OCULTOS);
    expect(StyleSheet.flatten(der.props.style).justifyContent).toBe('flex-start');
    expect(within(screen.getByTestId('swipe-boton-pendiente-luz-derecha', OCULTOS)).getByText('No hubo', OCULTOS)).toBeTruthy();
    fireEvent(screen.getByTestId('pendientes'), 'touchStart');
    await asentar();
    // del todo a la izquierda: pago; del todo a la derecha en la nómina: no hubo
    deslizar('fila-swipe-pendiente-luz', -260);
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad pagada · 74,00 €');
    deslizar(`fila-swipe-pendiente-${NOMINA.id}`, 260);
    expect(screen.getByTestId(`aviso-rapida-${NOMINA.id}-texto`)).toHaveTextContent('Nómina · no hubo este mes');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect(c.omitirPrevision).toHaveBeenCalledWith(NOMINA.id, expect.objectContaining({ motivo: null }));
    expect(screen.getByTestId('pendiente-luz').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }, { name: 'derecha', label: 'No hubo' }]);
  });

  test('fila abierta: se cierra al abrir otra, al hacer scroll y al tocar fuera; su botón la ejecuta; tocar la fila abre el detalle', async () => {
    const onDetalle = jest.fn();
    const c = clientePendientes();
    await montarPendientes(c, onDetalle);
    const abierta = (id: string) => screen.queryByTestId(`swipe-boton-pendiente-${id}-izquierda`, OCULTOS) !== null;
    // otra fila
    deslizar('fila-swipe-pendiente-luz', -100);
    await asentar();
    expect(abierta('luz')).toBe(true);
    deslizar(`fila-swipe-pendiente-${NOMINA.id}`, -100);
    await asentar();
    expect(abierta('luz')).toBe(false);
    expect(abierta(NOMINA.id)).toBe(true);
    // scroll
    fireEvent(screen.UNSAFE_getByType(require('react-native').ScrollView), 'scrollBeginDrag');
    await asentar();
    expect(abierta(NOMINA.id)).toBe(false);
    // tocar fuera
    deslizar('fila-swipe-pendiente-luz', -100);
    await asentar();
    fireEvent(screen.getByTestId('pendientes'), 'touchStart');
    await asentar();
    expect(abierta('luz')).toBe(false);
    // su botón: el toque sube del botón a la raíz y no la cierra; la pulsación la ejecuta
    deslizar('fila-swipe-pendiente-luz', -100);
    await asentar();
    const boton = screen.getByTestId('swipe-boton-pendiente-luz-izquierda', OCULTOS);
    fireEvent(boton, 'touchStart');
    fireEvent(screen.getByTestId('pendientes'), 'touchStart');
    expect(abierta('luz')).toBe(true);
    fireEvent.press(boton);
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad pagada · 74,00 €');
    fireEvent.press(screen.getByTestId('aviso-rapida-luz-deshacer'));
    // tocar la fila abierta abre su detalle y la cierra
    deslizar(`fila-swipe-pendiente-${NOMINA.id}`, -100);
    await asentar();
    fireEvent(screen.getByTestId('pendientes'), 'touchStart');
    fireEvent.press(screen.getByTestId(`pendiente-${NOMINA.id}`));
    await asentar();
    expect(onDetalle).toHaveBeenCalledWith(expect.objectContaining({ id: NOMINA.id }));
    expect(abierta(NOMINA.id)).toBe(false);
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });

  test('vibración: una sola vez al cruzar el umbral, impacto medio; no vibra a medias', async () => {
    await montarPendientes(clientePendientes());
    arrastrar('fila-swipe-pendiente-luz', [-30, -100]);
    await asentar();
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
    fireEvent(screen.getByTestId('pendientes'), 'touchStart');
    arrastrar('fila-swipe-pendiente-luz', [-30, -100, -200, -230, -260]);
    expect(Haptics.impactAsync).toHaveBeenCalledTimes(1);
    expect(Haptics.impactAsync).toHaveBeenCalledWith('medium');
  });

  test('vibración: si expo-haptics falla, aviso en consola y Vibration de reserva (nunca en silencio)', async () => {
    (Haptics.impactAsync as jest.Mock).mockImplementation(() => Promise.reject(new Error('ExpoHaptics no disponible')));
    const vib = jest.spyOn(Vibration, 'vibrate').mockImplementation(() => undefined);
    const aviso = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      await montarPendientes(clientePendientes());
      arrastrar('fila-swipe-pendiente-luz', [-30, -200]);
      await asentar();
      expect(vib).toHaveBeenCalledTimes(1);
      expect(aviso.mock.calls[0][0]).toMatch(/expo-haptics no ha vibrado/);
    } finally {
      vib.mockRestore();
      aviso.mockRestore();
    }
  });
});

// ==================================================================
// Actividad, «Pendiente con» y Terceros: lados invertidos con el gesto real
// ==================================================================
const CAFE: FilaActividad = {
  id: 'cafe', fecha_hecho: '2026-10-08', tipo: 'GASTO', nota: 'Café', moneda: 'EUR', importe_total: '2.40',
  tercero: null, categoria: null, varias: false, contexto: null, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', rol: 'PAGO', enabled: true }],
  estado_reparto: 'COMPLETA', tu_parte: '2.40', pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};
const DET = (f: FilaActividad): DetalleActividad => ({ ...f, presupuestable: true, magnitudes: [], devoluciones: null });

test('Actividad: izquierda del todo = «Repetir hoy»; derecha del todo = «Más» (abre el detalle)', async () => {
  const c = {
    ...clienteCategoriasStub(),
    actividad: jest.fn(async () => ok({ filas: [CAFE], siguiente: null, total: 1 })),
    detalleActividad: jest.fn(async () => ok(DET(CAFE))),
    cuentasPago: jest.fn(async () => ok({ cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'h2', idempotente: false })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
  } as unknown as ClienteApi;
  envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
  await esperar(400);
  await asentar();
  deslizar('fila-swipe-cafe', 260);
  await asentar();
  expect(c.detalleActividad).toHaveBeenCalledWith('cafe');
  expect(screen.queryByTestId('aviso-rapida-repetir-cafe')).toBeNull();
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  deslizar('fila-swipe-cafe', -260);
  await asentar();
  expect(screen.getByTestId('aviso-rapida-repetir-cafe-texto')).toHaveTextContent('Repetido hoy: Café · 2,40 €');
  await esperar(ESPERA_DESHACER_MS);
  await asentar();
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
});

test('«Pendiente con»: izquierda del todo cobra el saldo entero; derecha del todo abre «Más»', async () => {
  const PEND: PendienteConPersona = {
    tercero_id: 'tania', nombre: 'Tania', te_debe: '15.00', le_debes: null, neto: '15.00', neto_estado: 'DETERMINADO',
    posiciones: [{ entidad_id: 'd1', entidad_row_version: 1, tipo: 'DERECHO_COBRO', nombre: 'Gasto compartido', saldo: '15.00', estado: 'ACTIVA', origen_hecho_id: 'cena', origen_fecha: '2026-10-09', origen_concepto: 'Cena' }],
  };
  const c = {
    ...clienteCategoriasStub(),
    pendienteCon: jest.fn(async () => ok(PEND)),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }] })),
    cobrarPosicion: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'hx', entidad_id: 'd1', idempotente: false, importe: pl.importe, saldo: '0.00', estado: 'CERRADA', aviso: '' })),
    perdonarPosicion: jest.fn(),
  } as unknown as ClienteApi;
  envolver(<PendienteConScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} terceroId="tania" nombre="Tania" onCerrar={jest.fn()} />);
  await asentar();
  deslizar('fila-swipe-posicion-d1', 260);
  await asentar();
  expect(screen.getByTestId('posicion-acciones')).toBeTruthy();
  fireEvent.press(screen.getByTestId('posicion-atras'));
  await asentar();
  deslizar('fila-swipe-posicion-d1', -260);
  expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Cobrado de Tania · 15,00 €');
  await esperar(ESPERA_DESHACER_MS);
  await asentar();
  expect(c.cobrarPosicion).toHaveBeenCalledWith('d1', expect.objectContaining({ importe: '15.00', fecha: HOY }));
  expect(c.perdonarPosicion).not.toHaveBeenCalled();
});

test('Terceros: «Desactivar» se desliza a la derecha (naranja); a la izquierda no hay nada', async () => {
  const SIMON: Tercero = { id: 'simon', nombre: 'Simón', naturaleza: 'PERSONA', enabled: true, row_version: 3 };
  const c = { ...clienteCategoriasStub(), listarTerceros: jest.fn(async () => ok({ terceros: [SIMON] })),
    desactivarTercero: jest.fn(async () => ok({ tercero: { ...SIMON, enabled: false } })) } as unknown as ClienteApi;
  envolver(<TercerosAjustesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} onInmersiva={jest.fn()} />);
  await asentar();
  expect(deslizar('fila-swipe-ajter-fila-simon', 100)).toBe(true);
  await asentar();
  expect(fondo('fila-swipe-ajter-fila-simon')).toBe(colores.light.partialSurface);
  fireEvent(screen.getByTestId('pantalla-terceros'), 'touchStart');
  deslizar('fila-swipe-ajter-fila-simon', 260);
  expect(screen.getByTestId('aviso-rapida-simon-texto')).toHaveTextContent('Simón desactivado');
  await esperar(ESPERA_DESHACER_MS);
  await asentar();
  expect(c.desactivarTercero).toHaveBeenCalledWith('simon', 3);
  expect(deslizar('fila-swipe-ajter-fila-simon', -260)).toBe(false); // a la izquierda no hay principal
});
