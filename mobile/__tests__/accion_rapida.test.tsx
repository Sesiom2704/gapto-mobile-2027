// ============================================================
// GAPTO MOBILE 2027
// Fichero: accion_rapida.test.tsx
// Ruta: mobile/__tests__/accion_rapida.test.tsx
// Descripción: Swipe como acción rápida en toda la app (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22). Dominio (`planRapidoPrevision`: solo con la acción inequívoca, cada condición por sí misma; texto del aviso) y pantallas que la usan: Inicio, «Pendientes» y Actividad («Cobrado» de la devolución). En cada una: gesto → la fila sale y aparece «<Nombre> pagada/cobrada · Deshacer» → la petición sale a los 5 s, por la misma ruta y con el mismo bloque `prevision` que la hoja; «Deshacer» → 0 peticiones y la fila vuelve; datos incompletos → la hoja de siempre; rechazo → la fila vuelve con el motivo del servidor (nunca un éxito falso); doble gesto → una sola intención; INDETERMINADO → «Reintentar» con la MISMA identidad; segundo plano o pantalla desmontada durante la espera → nada. También el gesto real sobre el contenedor común (FilaDeslizable).
// Versión: 0.1.0 (F05-06 M5 SWIPE)
// Versión: 0.3.0 (F05-06 M5 SWIPE3; lámina SWIPE-01 v0.3): lados invertidos — la acción principal se desliza a la IZQUIERDA y la alternativa a la DERECHA; acciones accesibles con el nombre de la dirección nueva.
// Versión: 0.4.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): importa `tiempos_rn` (30 s por test y 5 s de `waitFor`/`findBy`) contra la intermitencia en frío de las suites de pantalla; sin cambios de aserciones.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, within } from '@testing-library/react-native';
import React from 'react';
import { AppState, StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, ContextoDevolucion, FilaActividad, FilaPrevision } from '../src/api/cliente';
import { ESPERA_DESHACER_MS } from '../src/components/AccionRapida';
import { planRapidoPrevision, textoAvisoRapido, type CapacidadesHoy } from '../src/domain/prevision';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { HomeScreen } from '../src/screens/HomeScreen';
import { PendientesScreen } from '../src/screens/PendientesScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

function fila(o: Partial<FilaPrevision> = {}): FilaPrevision {
  return {
    id: 'luz', row_version: 1, estado: 'ABIERTA', tipo: 'GASTO', naturaleza: 'POR_PAGAR', concepto: 'Electricidad',
    tercero: { id: 'iber', nombre: 'Iberdrola' }, categoria: { id: 'elec', nombre: 'Electricidad', ruta: 'Hogar › Electricidad' },
    fecha_desde: '2026-10-01', fecha_hasta: '2026-10-05', moneda: 'EUR', importe_esperado: '74.00', cubierto: '0.00', queda: '74.00',
    desviacion: null, con_realidad: false, pagos: 0, vencida: true, cuenta_salida: { id: 'nomina', nombre: 'Cuenta nómina' },
    cuenta_entrada: null, origen: 'V3', presupuestable: true, ...o,
  };
}
const NOMINA = fila({ id: 'nomina-prev', tipo: 'INGRESO', naturaleza: 'POR_COBRAR', concepto: 'Nómina', tercero: { id: 'empresa', nombre: 'Empresa SL' },
  categoria: null, fecha_desde: '2026-09-30', fecha_hasta: '2026-09-30', importe_esperado: '2100.00', queda: '2100.00', cuenta_salida: null,
  cuenta_entrada: { id: 'nomina', nombre: 'Cuenta nómina' } });

const PAGO = [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' as const },
  { cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' as const }];
const RECIBIR = [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }];
const CAP: CapacidadesHoy = { pago: PAGO, ingreso: RECIBIR };

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    registrarGastoPagado: jest.fn(async (pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false } }) as any),
    registrarIngresoCobrado: jest.fn(async (pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false } }) as any),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: PAGO } }) as any),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: RECIBIR } }) as any),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    ...o,
  } as ClienteApi;
}

function envolver(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}

/** Todas las llamadas al cliente hasta ahora (para «0 peticiones»). */
function llamadas(c: ClienteApi): number {
  return Object.values(c).reduce((t, f) => t + ((f as jest.Mock)?.mock?.calls?.length ?? 0), 0);
}
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
/** Deja que terminen las promesas pendientes (lecturas, envío y relectura). */
const asentar = async () => {
  for (let i = 0; i < 5; i++) await act(async () => undefined);
};
/** Dos eventos que llegan antes de que React vuelva a pintar (la fila aún no ha salido): el segundo debe ignorarse. */
const dosEventosSeguidos = (testID: string, nombre: string) => {
  const h = screen.getByTestId(testID).props.onAccessibilityAction;
  act(() => {
    h({ nativeEvent: { actionName: nombre } });
    h({ nativeEvent: { actionName: nombre } });
  });
};
const OCULTOS = { includeHiddenElements: true };
/** Gesto horizontal real sobre el contenedor común (historial de un toque de x=300 a x=300+dx). Devuelve si lo capturó. */
let reloj = 0;
function deslizar(testID: string, dx: number): boolean {
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
    captura = z.props.onMoveShouldSetResponderCapture(evento(dx / 3));
    if (!captura) return;
    z.props.onResponderGrant(evento(dx / 3));
    z.props.onResponderMove(evento(dx));
    z.props.onResponderRelease(evento(dx));
  });
  return captura;
}
const accion = (testID: string, nombre: string) => fireEvent(screen.getByTestId(testID), 'accessibilityAction', { nativeEvent: { actionName: nombre } });

beforeEach(() => {
  n = 0;
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

// ==================================================================
// Dominio
// ==================================================================
describe('dominio', () => {
  test('acción rápida de un gasto: esperado, cuenta prevista con capacidad, fecha de hoy y marcar_realizada', () => {
    expect(planRapidoPrevision(fila(), CAP, HOY)).toEqual({
      importe: '74.00', fecha: HOY, cuentaId: 'nomina', cuentaDestinoId: null, presupuestable: true, conCategoria: true, propuestaSelf100: true, marcar: true });
    expect(planRapidoPrevision(fila({ cuenta_salida: { id: 'bbva', nombre: 'Tarjeta BBVA' } }), CAP, HOY)?.propuestaSelf100).toBe(false);
    expect(planRapidoPrevision(NOMINA, CAP, HOY)).toMatchObject({ importe: '2100.00', cuentaId: 'nomina', fecha: HOY, marcar: true });
  });

  test('si falta algo no hay acción rápida (abre la hoja)', () => {
    expect(planRapidoPrevision(fila({ importe_esperado: null, queda: null }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ moneda: 'USD' }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ cuenta_salida: null }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ con_realidad: true }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ pagos: 1 }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ estado: 'REALIZADA' }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila({ tipo: 'TRANSFERENCIA', cuenta_entrada: { id: 'ahorro', nombre: 'Ahorro' } }), CAP, HOY)).toBeNull();
    // sin capacidad hoy, o sin poder leerla
    expect(planRapidoPrevision(fila({ cuenta_salida: { id: 'ahorro', nombre: 'Ahorro' } }), CAP, HOY)).toBeNull();
    expect(planRapidoPrevision(fila(), { pago: null, ingreso: RECIBIR }, HOY)).toBeNull();
    expect(planRapidoPrevision(fila(), null, HOY)).toBeNull();
    expect(planRapidoPrevision(NOMINA, { pago: PAGO, ingreso: [] }, HOY)).toBeNull();
  });

  test('texto del aviso', () => {
    expect(textoAvisoRapido(fila())).toBe('Electricidad pagada · 74,00 €');
    expect(textoAvisoRapido(NOMINA)).toBe('Nómina cobrada · 2.100,00 €');
    expect(textoAvisoRapido(fila({ importe_esperado: null }))).toBe('Electricidad pagada');
  });
});

// ==================================================================
// Inicio
// ==================================================================
function inicio(primeras: FilaPrevision[]) {
  return jest.fn(async () => ({ tipo: 'OK', datos: { hoy: HOY, requiere_atencion: { n: primeras.length, primeras }, proximos: [] } }) as any);
}
async function montarHome(c: ClienteApi) {
  const r = envolver(<HomeScreen cliente={c} ahora={AHORA} refresco={0} onRegistrar={jest.fn()} nuevoId={nuevoId} onPendientes={jest.fn()} onPrevision={jest.fn()} />);
  await asentar();
  expect(screen.getByTestId('atencion-luz')).toBeTruthy();
  return r;
}

describe('Inicio', () => {
  test('gesto → aviso «Electricidad pagada · Deshacer» → el gasto sale a los 5 s con el bloque prevision de la hoja', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]) });
    await montarHome(c);
    expect(c.cuentasPago).toHaveBeenCalledWith(HOY); // la capacidad se lee con la lista, no en el gesto
    const antes = llamadas(c);
    accion('atencion-luz', 'izquierda');
    expect(screen.queryByTestId('atencion-luz')).toBeNull(); // la fila sale
    expect(screen.queryByTestId('hoja-swipe')).toBeNull(); // sin hoja
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad pagada · 74,00 €');
    expect(screen.getByTestId('aviso-rapida-luz-deshacer')).toHaveTextContent('Deshacer');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
    expect(llamadas(c)).toBe(antes); // durante la espera no se toca el servidor
    await esperar(1);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0]).toEqual({
      intencion_id: '00000000-0000-4000-8000-000000000001', importe: '74.00', moneda: 'EUR', fecha_hecho: HOY, cuenta_id: 'nomina',
      presupuestable: true, atribucion: 'SOLO_MIO', categoria: { estado: 'CATEGORIA', categoria_id: 'elec', magnitudes: [] }, tercero_id: 'iber',
      financiacion: { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe: '74.00' },
      prevision: { prevision_id: 'luz', row_version: 1, marcar_realizada: true } });
    expect(c.inicioPrevisiones).toHaveBeenCalledTimes(2); // tras el OK, Inicio vuelve a leer
  });

  test('«Deshacer» → 0 peticiones y la fila vuelve', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]) });
    await montarHome(c);
    const antes = llamadas(c);
    accion('atencion-luz', 'izquierda');
    await esperar(2000);
    fireEvent.press(screen.getByTestId('aviso-rapida-luz-deshacer'));
    expect(screen.getByTestId('atencion-luz')).toBeTruthy();
    expect(screen.queryByTestId('aviso-rapida-luz')).toBeNull();
    await esperar(ESPERA_DESHACER_MS * 3);
    await asentar();
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
    expect(llamadas(c)).toBe(antes);
  });

  test('datos incompletos (la cuenta prevista hoy no puede pagar) → la hoja de siempre, sin aviso', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]), cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [PAGO[1]] } }) as any) });
    await montarHome(c);
    accion('atencion-luz', 'izquierda');
    expect(screen.getByTestId('hoja-swipe')).toBeTruthy();
    expect(screen.queryByTestId('aviso-rapida-luz')).toBeNull();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });

  test('rechazo del servidor → la fila vuelve con el motivo en llano; nunca un éxito falso', async () => {
    const mensaje = 'Cuenta nómina ya no puede pagar gastos. No se ha guardado.';
    const c = cliente({ inicioPrevisiones: inicio([fila()]),
      registrarGastoPagado: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje }) as any) });
    await montarHome(c);
    accion('atencion-luz', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('atencion-luz')).toBeTruthy(); // la fila vuelve
    expect(screen.getByTestId('fallo-rapida-luz-texto')).toHaveTextContent(`No se ha guardado: Electricidad pagada · 74,00 €. ${mensaje}`);
    expect(screen.queryByTestId('aviso-rapida-luz')).toBeNull();
    expect(screen.queryByTestId('fallo-rapida-luz-reintentar')).toBeNull(); // un rechazo no se reintenta igual
    expect(c.inicioPrevisiones).toHaveBeenCalledTimes(1); // no relee como si se hubiera guardado
    fireEvent.press(screen.getByTestId('fallo-rapida-luz-cerrar'));
    expect(screen.queryByTestId('fallo-rapida-luz')).toBeNull();
  });

  test('doble gesto → una sola intención y una sola petición', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]) });
    await montarHome(c);
    dosEventosSeguidos('atencion-luz', 'izquierda');
    expect(screen.getAllByTestId('aviso-rapida-luz')).toHaveLength(1);
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect(n).toBe(1); // una sola identidad generada
  });

  test('INDETERMINADO → «No sabemos si se guardó» y «Reintentar» con la MISMA identidad', async () => {
    const registrar = jest.fn()
      .mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' })
      .mockResolvedValue({ tipo: 'OK', datos: { intencion_id: 'x', hecho_id: 'x', idempotente: true } });
    const c = cliente({ inicioPrevisiones: inicio([fila()]), registrarGastoPagado: registrar as any });
    await montarHome(c);
    accion('atencion-luz', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(screen.getByTestId('fallo-rapida-luz-texto')).toHaveTextContent(/No sabemos si se guardó: Electricidad pagada/);
    expect(screen.getByTestId('atencion-luz')).toBeTruthy();
    fireEvent.press(screen.getByTestId('fallo-rapida-luz-reintentar'));
    await asentar();
    expect(registrar).toHaveBeenCalledTimes(2);
    expect(registrar.mock.calls[1][0].intencion_id).toBe(registrar.mock.calls[0][0].intencion_id);
    expect(n).toBe(1);
  });

  test('gesto nuevo tras un INDETERMINADO: misma identidad', async () => {
    const registrar = jest.fn().mockResolvedValue({ tipo: 'INDETERMINADO', mensaje: 'sin red' });
    const c = cliente({ inicioPrevisiones: inicio([fila()]), registrarGastoPagado: registrar as any });
    await montarHome(c);
    accion('atencion-luz', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    accion('atencion-luz', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(registrar).toHaveBeenCalledTimes(2);
    expect(registrar.mock.calls[1][0].intencion_id).toBe(registrar.mock.calls[0][0].intencion_id);
  });

  test('la app pasa a segundo plano durante la espera → no se envía nada', async () => {
    let oyente: ((e: string) => void) | null = null;
    const espia = jest.spyOn(AppState, 'addEventListener').mockImplementation(((_: string, h: (e: string) => void) => {
      oyente = h;
      return { remove: jest.fn() };
    }) as any);
    try {
      const c = cliente({ inicioPrevisiones: inicio([fila()]) });
      await montarHome(c);
      accion('atencion-luz', 'izquierda');
      await esperar(1000);
      await act(async () => oyente?.('background'));
      await esperar(ESPERA_DESHACER_MS * 2);
      await asentar();
      expect(c.registrarGastoPagado).not.toHaveBeenCalled();
      expect(screen.getByTestId('atencion-luz')).toBeTruthy();
    } finally {
      espia.mockRestore();
    }
  });

  test('la pantalla se desmonta durante la espera → no se envía nada', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]) });
    const r = await montarHome(c);
    accion('atencion-luz', 'izquierda');
    r.unmount();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });

  test('gesto real: a medias a la izquierda enseña «Pagado» (nada se envía); tocarlo lo ejecuta; del todo lo ejecuta directamente', async () => {
    const c = cliente({ inicioPrevisiones: inicio([fila()]) });
    await montarHome(c);
    const antes = llamadas(c);
    expect(deslizar('fila-swipe-atencion-luz', -100)).toBe(true); // a medias
    await asentar();
    expect(screen.getByTestId('swipe-boton-atencion-luz-izquierda', OCULTOS)).toBeTruthy();
    expect(within(screen.getByTestId('swipe-accion-atencion-luz-izquierda', OCULTOS)).getByText('Pagado', OCULTOS)).toBeTruthy();
    expect(screen.queryByTestId('aviso-rapida-luz')).toBeNull();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(llamadas(c)).toBe(antes);
    fireEvent.press(screen.getByTestId('swipe-boton-atencion-luz-izquierda', OCULTOS));
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad pagada · 74,00 €');
    fireEvent.press(screen.getByTestId('aviso-rapida-luz-deshacer'));
    // del todo
    expect(deslizar('fila-swipe-atencion-luz', -260)).toBe(true);
    await asentar();
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad pagada · 74,00 €');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0].intencion_id).toBe('00000000-0000-4000-8000-000000000001');
  });

  test('gesto real a la derecha del todo: «No hubo este mes» (omitir sin motivo) a los 5 s; gris neutro, nunca rojo', async () => {
    const omitir = jest.fn(async (_: string, pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, prevision_id: 'luz', estado: 'OMITIDA', row_version: 2 } }) as any);
    const c = cliente({ inicioPrevisiones: inicio([fila()]), omitirPrevision: omitir as any });
    await montarHome(c);
    expect(deslizar('fila-swipe-atencion-luz', 90)).toBe(true); // a medias: se ve el botón
    await asentar();
    const fondo = StyleSheet.flatten(screen.getByTestId('fila-swipe-atencion-luz').props.style).backgroundColor;
    expect(fondo).toBe(colores.light.surfaceSecondary);
    expect(within(screen.getByTestId('swipe-accion-atencion-luz-derecha', OCULTOS)).getByText('No hubo', OCULTOS)).toBeTruthy();
    fireEvent.press(screen.getByTestId('swipe-boton-atencion-luz-derecha', OCULTOS));
    expect(screen.getByTestId('aviso-rapida-luz-texto')).toHaveTextContent('Electricidad · no hubo este mes');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(omitir).not.toHaveBeenCalled();
    await esperar(1);
    await asentar();
    expect(omitir).toHaveBeenCalledWith('luz', { intencion_id: '00000000-0000-4000-8000-000000000001', row_version: 1, motivo: null });
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });

  test('«No hubo» no se ofrece con pagos enlazados; la principal con pago parcial o importe desconocido abre el formulario rellenado', async () => {
    const SEGURO = fila({ id: 'seguro', concepto: 'Seguro hogar', importe_esperado: '120.00', cubierto: '40.00', queda: '80.00', con_realidad: true, pagos: 1 });
    const AGUA = fila({ id: 'agua', concepto: 'Agua', importe_esperado: null, queda: null });
    const onFormularioCompleto = jest.fn();
    const c = cliente({ inicioPrevisiones: inicio([SEGURO, AGUA]) });
    envolver(<HomeScreen cliente={c} ahora={AHORA} refresco={0} onRegistrar={jest.fn()} nuevoId={nuevoId} onPendientes={jest.fn()} onPrevision={jest.fn()} onFormularioCompleto={onFormularioCompleto} />);
    await asentar();
    expect(screen.getByTestId('atencion-seguro').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }]);
    expect(deslizar('fila-swipe-atencion-seguro', 260)).toBe(false); // sin alternativa: el gesto a la derecha no se toma
    accion('atencion-seguro', 'izquierda');
    expect(onFormularioCompleto).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'seguro' }), '80,00');
    expect(screen.getByTestId('atencion-agua').props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'izquierda', label: 'Pagado' }, { name: 'derecha', label: 'No hubo' }]);
    accion('atencion-agua', 'izquierda');
    expect(onFormularioCompleto).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'agua' }), null);
    expect(screen.queryByTestId('aviso-rapida-agua')).toBeNull();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });
});

// ==================================================================
// «Pendientes»
// ==================================================================
function pendientes(vencidas: FilaPrevision[]) {
  return jest.fn(async () => ({ tipo: 'OK', datos: { hoy: HOY, n: vencidas.length,
    por_pagar: { importe: '74.00', n: 1, desconocidos: 0 }, por_cobrar: { importe: '2100.00', n: 1, desconocidos: 0 },
    secciones: { vencidas, con_pago_parcial: [], sin_fecha: [] } } }) as any);
}
async function montarPendientes(c: ClienteApi) {
  const onCambios = jest.fn();
  envolver(<PendientesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} refresco={0} onAtras={jest.fn()} onDetalle={jest.fn()} onFormularioCompleto={jest.fn()} onCambios={onCambios} />);
  await asentar();
  return onCambios;
}

describe('«Pendientes»', () => {
  test('nómina por swipe → «Nómina cobrada · Deshacer» → ingreso de 2.100,00 en la cuenta prevista a los 5 s, cubierta', async () => {
    const c = cliente({ pendientesPrevisiones: pendientes([fila(), NOMINA]) });
    const onCambios = await montarPendientes(c);
    expect(c.cuentasElegibles).toHaveBeenCalledWith('INGRESO', HOY);
    accion(`pendiente-${NOMINA.id}`, 'izquierda');
    expect(screen.queryByTestId(`pendiente-${NOMINA.id}`)).toBeNull();
    expect(screen.getByTestId('pendiente-luz')).toBeTruthy(); // las demás filas siguen
    expect(screen.getByTestId(`aviso-rapida-${NOMINA.id}-texto`)).toHaveTextContent('Nómina cobrada · 2.100,00 €');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(c.registrarIngresoCobrado).not.toHaveBeenCalled();
    await esperar(1);
    await asentar();
    expect(c.registrarIngresoCobrado).toHaveBeenCalledTimes(1);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
    expect((c.registrarIngresoCobrado as jest.Mock).mock.calls[0][0]).toMatchObject({
      importe: '2100.00', moneda: 'EUR', fecha_hecho: HOY, cuenta_id: 'nomina', tercero_id: 'empresa', categoria: { estado: 'SIN_CATEGORIA' },
      prevision: { prevision_id: NOMINA.id, row_version: 1, marcar_realizada: true } });
    expect(onCambios).toHaveBeenCalledTimes(1);
    expect(c.pendientesPrevisiones).toHaveBeenCalledTimes(2);
  });

  test('«Deshacer» → 0 peticiones', async () => {
    const c = cliente({ pendientesPrevisiones: pendientes([NOMINA]) });
    const onCambios = await montarPendientes(c);
    const antes = llamadas(c);
    accion(`pendiente-${NOMINA.id}`, 'izquierda');
    fireEvent.press(screen.getByTestId(`aviso-rapida-${NOMINA.id}-deshacer`));
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(llamadas(c)).toBe(antes);
    expect(onCambios).not.toHaveBeenCalled();
    expect(screen.getByTestId(`pendiente-${NOMINA.id}`)).toBeTruthy();
  });

  test('sin poder leer la capacidad → la hoja', async () => {
    const c = cliente({ pendientesPrevisiones: pendientes([NOMINA]), cuentasElegibles: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: 'x' }) as any) });
    await montarPendientes(c);
    accion(`pendiente-${NOMINA.id}`, 'izquierda');
    expect(screen.getByTestId('hoja-swipe')).toBeTruthy();
    expect(screen.queryByTestId(`aviso-rapida-${NOMINA.id}`)).toBeNull();
  });
});

// ==================================================================
// Actividad · «Cobrado» de la devolución
// ==================================================================
const CTX: ContextoDevolucion = {
  origen_id: 'compra', fecha_hecho: '2026-08-20', nota: 'Abrigo', tercero: 'Zara', categoria_id: 'ropa', categoria: 'Ropa',
  importe_total: '120.00', devuelto: '40.00', queda: '80.00', neto: '80.00', devoluciones: [], disponible: true, motivo: null,
  atribucion_propuesta: 'SOLO_MIO', tuya_disponible: true, cuenta_compra: { cuenta_id: 'bbva', nombre: 'Tarjeta BBVA' },
};
const COMPRA: FilaActividad = {
  id: 'compra', fecha_hecho: '2026-10-02', tipo: 'GASTO', nota: 'Abrigo', moneda: 'EUR', importe_total: '120.00',
  tercero: { id: 'zara', nombre: 'Zara', enabled: true }, categoria: { id: 'ropa', nombre: 'Ropa', ruta: 'Ropa', enabled: true }, varias: false,
  contexto: null, cuentas: [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '120.00',
  pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};
const DEV: FilaActividad = {
  ...COMPRA, id: 'dev', fecha_hecho: HOY, nota: 'Talla', importe_total: '40.00', tercero: null, cuentas: [], tu_parte: '-40.00',
  devolucion_de: { hecho_id: 'compra', nota: 'Abrigo', fecha_hecho: '2026-10-02', tercero: 'Zara' }, abono: 'PENDIENTE',
};
function clienteActividad(o: Partial<ClienteApi> = {}) {
  return cliente({
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [DEV, COMPRA], siguiente: null, total: 2 } }) as any),
    contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: CTX }) as any),
    registrarAbono: jest.fn(async () => ({ tipo: 'OK', datos: { hecho_id: 'dev', movimiento_id: 'm', idempotente: false, importe: '40.00', abono: 'COBRADO' } }) as any),
    ...o,
  });
}
async function montarActividad(c: ClienteApi) {
  envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
  await esperar(400); // pausa de la búsqueda
  await asentar();
  expect(screen.getByTestId('fila-dev')).toBeTruthy();
}

describe('Actividad', () => {
  test('«Recibido» con la cuenta original → «Abono de Abrigo recibido · Deshacer» → abono en la original con fecha de hoy a los 5 s', async () => {
    const c = clienteActividad();
    await montarActividad(c);
    expect(c.contextoDevolucion).toHaveBeenCalledWith('compra'); // la cuenta original se lee con la lista
    const antes = llamadas(c);
    accion('fila-dev', 'izquierda');
    expect(screen.queryByTestId('fila-dev')).toBeNull();
    expect(screen.queryByTestId('hoja-abono')).toBeNull();
    expect(screen.getByTestId('aviso-rapida-dev-texto')).toHaveTextContent('Abono de Abrigo recibido · 40,00 €');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(llamadas(c)).toBe(antes);
    await esperar(1);
    await asentar();
    expect(c.registrarAbono).toHaveBeenCalledTimes(1);
    expect(c.registrarAbono).toHaveBeenCalledWith('dev', { intencion_id: '00000000-0000-4000-8000-000000000001', cuenta_id: 'bbva', fecha: HOY });
    expect(c.actividad).toHaveBeenCalledTimes(2); // relee la lista
  });

  test('«Deshacer» → 0 peticiones y la fila vuelve', async () => {
    const c = clienteActividad();
    await montarActividad(c);
    const antes = llamadas(c);
    accion('fila-dev', 'izquierda');
    fireEvent.press(screen.getByTestId('aviso-rapida-dev-deshacer'));
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(llamadas(c)).toBe(antes);
    expect(screen.getByTestId('fila-dev')).toBeTruthy();
  });

  test('sin cuenta original → la hoja de cuenta y fecha', async () => {
    const c = clienteActividad({ contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: { ...CTX, cuenta_compra: null } }) as any) });
    await montarActividad(c);
    accion('fila-dev', 'izquierda');
    await asentar();
    expect(screen.getByTestId('hoja-abono')).toBeTruthy();
    expect(screen.queryByTestId('aviso-rapida-dev')).toBeNull();
    expect(c.registrarAbono).not.toHaveBeenCalled();
  });

  test('rechazo → la fila vuelve con el motivo del servidor', async () => {
    const mensaje = 'Esta devolución ya tiene su abono.';
    const c = clienteActividad({ registrarAbono: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'YA_CONCILIADO', mensaje }) as any) });
    await montarActividad(c);
    accion('fila-dev', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(screen.getByTestId('fila-dev')).toBeTruthy();
    expect(within(screen.getByTestId('fallo-rapida-dev')).getByText(new RegExp(mensaje))).toBeTruthy();
    expect(c.actividad).toHaveBeenCalledTimes(1);
  });

  test('doble gesto → una sola intención', async () => {
    const c = clienteActividad();
    await montarActividad(c);
    dosEventosSeguidos('fila-dev', 'izquierda');
    expect(screen.getAllByTestId('aviso-rapida-dev')).toHaveLength(1);
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(c.registrarAbono).toHaveBeenCalledTimes(1);
  });
});
