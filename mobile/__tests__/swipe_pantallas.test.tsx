// ============================================================
// GAPTO MOBILE 2027
// Fichero: swipe_pantallas.test.tsx
// Ruta: mobile/__tests__/swipe_pantallas.test.tsx
// Descripción: SWIPE-RULE en el resto de la app (F05-06 M5 SWIPE2; lámina SWIPE-01 v0.2 S6–S9). Tonos: confirmar (verde), neutro (gris) y aviso (naranja), nunca el rojo `critical`, en claro y oscuro. «Pendiente con <persona>»: derecha «Cobrado» / «Pagado» del saldo entero con UNA cuenta posible (aviso, 5 s, la ruta de cobro o pago con fecha de hoy); con varias cuentas abre el formulario con el saldo; izquierda «Más» abre las acciones; «Perdonar» nunca por swipe. Actividad «Repetir hoy»: intención NUEVA con los mismos datos y fecha de hoy por la ruta del tipo; no se ofrece con reparto, varias líneas o maestros desactivados; con magnitudes abre el detalle; «Deshacer» → ninguna escritura y ninguna petición tras el aviso; doble gesto → una intención. Ajustes: izquierda «Desactivar» en terceros, categorías (sin subcategorías activas; con ellas, la hoja de siempre) y plantillas, por su ruta actual, con «Deshacer»; error → la fila vuelve con el motivo.
// Versión: 0.1.0 (F05-06 M5 SWIPE2)
// ============================================================

import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, DetalleActividad, FilaActividad, Plantilla, Tercero } from '../src/api/cliente';
import { coloresTono, ESPERA_DESHACER_MS, type TonoSwipe } from '../src/components/AccionRapida';
import type { PendienteConPersona } from '../src/domain/reparto';
import { componerRepetir, repetibleHoy } from '../src/domain/repetir';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { CategoriasAjustesScreen } from '../src/screens/CategoriasAjustesScreen';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { PlantillasAjustesScreen } from '../src/screens/PlantillasAjustesScreen';
import { TercerosAjustesScreen } from '../src/screens/TercerosAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

function envolver(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}
const ok = (datos: unknown) => ({ tipo: 'OK', datos }) as any;
function llamadas(c: ClienteApi): number {
  return Object.values(c).reduce((t, f) => t + ((f as jest.Mock)?.mock?.calls?.length ?? 0), 0);
}
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
const asentar = async () => {
  for (let i = 0; i < 6; i++) await act(async () => undefined);
};
const accion = (testID: string, nombre: string) => fireEvent(screen.getByTestId(testID), 'accessibilityAction', { nativeEvent: { actionName: nombre } });

beforeEach(() => {
  n = 0;
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

// ==================================================================
// Tonos: nunca rojo
// ==================================================================
test('tonos del swipe: confirmar verde, neutro gris y aviso naranja; nunca el rojo `critical` (claro y oscuro)', () => {
  for (const esquema of ['light', 'dark'] as const) {
    const c = colores[esquema];
    expect(coloresTono(c, 'confirmar')).toEqual({ fondo: c.accentSurface, circulo: c.accent, sobreCirculo: c.onAccent, etiqueta: c.accent });
    expect(coloresTono(c, 'neutro')).toEqual({ fondo: c.surfaceSecondary, circulo: c.textSecondary, sobreCirculo: c.background, etiqueta: c.textSecondary });
    expect(coloresTono(c, 'aviso')).toEqual({ fondo: c.partialSurface, circulo: c.warning, sobreCirculo: c.onAccent, etiqueta: c.warning });
    for (const t of ['confirmar', 'neutro', 'aviso'] as TonoSwipe[]) expect(Object.values(coloresTono(c, t))).not.toContain(c.critical);
  }
});

// ==================================================================
// «Pendiente con <persona>»
// ==================================================================
const PEND: PendienteConPersona = {
  tercero_id: 'tania', nombre: 'Tania', te_debe: '15.00', le_debes: '12.50', neto: '2.50', neto_estado: 'DETERMINADO',
  posiciones: [
    { entidad_id: 'd1', entidad_row_version: 1, tipo: 'DERECHO_COBRO', nombre: 'Gasto compartido', saldo: '15.00', estado: 'ACTIVA', origen_hecho_id: 'cena', origen_fecha: '2026-10-09', origen_concepto: 'Cena con amigos' },
    { entidad_id: 'o1', entidad_row_version: 1, tipo: 'OBLIGACION_PAGO', nombre: 'Gasto compartido', saldo: '12.50', estado: 'ACTIVA', origen_hecho_id: 'pelu', origen_fecha: '2026-10-03', origen_concepto: 'Peluquería' },
  ],
};
const UNA = [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }];
const DOS = [...UNA, { cuenta_id: 'efectivo', nombre: 'Efectivo', moneda: 'EUR' }];
function clientePendiente(o: Partial<ClienteApi> = {}, cuentas = UNA): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    pendienteCon: jest.fn(async () => ok(PEND)),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas })),
    cobrarPosicion: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'hx', entidad_id: 'd1', idempotente: false, importe: pl.importe, saldo: '0.00', estado: 'CERRADA', aviso: '' })),
    pagarPosicion: jest.fn(async (_: string, pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: 'hy', entidad_id: 'o1', idempotente: false, importe: pl.importe, saldo: '0.00', estado: 'CERRADA', aviso: '' })),
    perdonarPosicion: jest.fn(),
    ...o,
  } as ClienteApi;
}
async function montarPendiente(c: ClienteApi) {
  envolver(<PendienteConScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} terceroId="tania" nombre="Tania" onCerrar={jest.fn()} />);
  await asentar();
  expect(screen.getByTestId('posicion-d1')).toBeTruthy();
}

describe('«Pendiente con <persona>»', () => {
  test('derecha con una sola cuenta: «Cobrado de Tania · 15,00 € · Deshacer» y, a los 5 s, el cobro del saldo entero con fecha de hoy', async () => {
    const c = clientePendiente();
    await montarPendiente(c);
    expect(screen.getByTestId('posicion-d1').props.accessibilityActions).toEqual([{ name: 'derecha', label: 'Cobrado' }, { name: 'izquierda', label: 'Más' }]);
    expect(screen.getByTestId('posicion-o1').props.accessibilityActions).toEqual([{ name: 'derecha', label: 'Pagado' }, { name: 'izquierda', label: 'Más' }]);
    const antes = llamadas(c);
    accion('posicion-d1', 'derecha');
    expect(screen.queryByTestId('posicion-d1')).toBeNull();
    expect(screen.getByTestId('aviso-rapida-d1-texto')).toHaveTextContent('Cobrado de Tania · 15,00 €');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(llamadas(c)).toBe(antes);
    await esperar(1);
    await asentar();
    expect(c.cobrarPosicion).toHaveBeenCalledWith('d1', { intencion_id: '00000000-0000-4000-8000-000000000001', importe: '15.00', cuenta_id: 'nomina', fecha: HOY });
    expect(c.perdonarPosicion).not.toHaveBeenCalled();
  });

  test('«Deshacer» → 0 peticiones; pagar el saldo que le debes por la ruta de pago', async () => {
    const c = clientePendiente();
    await montarPendiente(c);
    const antes = llamadas(c);
    accion('posicion-o1', 'derecha');
    fireEvent.press(screen.getByTestId('aviso-rapida-o1-deshacer'));
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(llamadas(c)).toBe(antes);
    expect(screen.getByTestId('posicion-o1')).toBeTruthy();
    accion('posicion-o1', 'derecha');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(c.pagarPosicion).toHaveBeenCalledWith('o1', expect.objectContaining({ importe: '12.50', cuenta_id: 'nomina', fecha: HOY }));
    expect(c.cobrarPosicion).not.toHaveBeenCalled();
  });

  test('con varias cuentas posibles hay dudas: abre el formulario de cobro con el saldo escrito; nada se envía', async () => {
    const c = clientePendiente({}, DOS);
    await montarPendiente(c);
    accion('posicion-d1', 'derecha');
    await asentar();
    expect(screen.getByTestId('accion-cobro')).toBeTruthy();
    expect(screen.queryByTestId('aviso-rapida-d1')).toBeNull();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.cobrarPosicion).not.toHaveBeenCalled();
  });

  test('izquierda «Más» abre las acciones de la posición (sin escribir); «Perdonar» nunca es un lado del swipe', async () => {
    const c = clientePendiente();
    await montarPendiente(c);
    accion('posicion-d1', 'izquierda');
    expect(screen.getByTestId('posicion-acciones')).toBeTruthy();
    expect(c.perdonarPosicion).not.toHaveBeenCalled();
    expect(c.cobrarPosicion).not.toHaveBeenCalled();
  });

  test('rechazo → la posición vuelve con el motivo en llano', async () => {
    const c = clientePendiente({ cobrarPosicion: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'POSICION_CERRADA', mensaje: 'x' }) as any) });
    await montarPendiente(c);
    accion('posicion-d1', 'derecha');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(screen.getByTestId('posicion-d1')).toBeTruthy();
    expect(screen.getByTestId('fallo-rapida-d1-texto').props.children).not.toMatch(/POSICION_CERRADA/);
  });
});

// ==================================================================
// Actividad · «Repetir hoy»
// ==================================================================
const CAFE: FilaActividad = {
  id: 'cafe', fecha_hecho: '2026-10-08', tipo: 'GASTO', nota: 'Café', moneda: 'EUR', importe_total: '2.40',
  tercero: { id: 'bar', nombre: 'Bar Central', enabled: true }, categoria: { id: 'cafes', nombre: 'Cafés', ruta: 'Ocio › Cafés', enabled: true }, varias: false,
  contexto: null, cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '2.40',
  pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};
const CENA: FilaActividad = { ...CAFE, id: 'cena', nota: 'Cena', importe_total: '60.00', tu_parte: '30.00', estado_reparto: 'COMPLETA' };
const DET = (f: FilaActividad, o: Partial<DetalleActividad> = {}): DetalleActividad => ({ ...f, presupuestable: true, magnitudes: [], devoluciones: null, ...o });
const PAGO = [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }];

function clienteActividad(o: Partial<ClienteApi> = {}, detalle: (id: string) => DetalleActividad = (id) => DET(id === 'cafe' ? CAFE : CENA)) {
  return {
    ...clienteCategoriasStub(),
    actividad: jest.fn(async () => ok({ filas: [CAFE, CENA], siguiente: null, total: 2 })),
    detalleActividad: jest.fn(async (id: string) => ok(detalle(id))),
    cuentasPago: jest.fn(async () => ok({ cuentas: PAGO })),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: UNA })),
    registrarGastoPagado: jest.fn(async (pl: any) => ok({ intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    ...o,
  } as ClienteApi;
}
async function montarActividad(c: ClienteApi) {
  envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
  await esperar(400);
  await asentar();
  expect(screen.getByTestId('fila-cafe')).toBeTruthy();
}

describe('Actividad · «Repetir hoy»', () => {
  test('dominio: solo sin reparto, una cuenta, sin varias líneas ni maestros desactivados; payload con fecha de hoy', () => {
    expect(repetibleHoy(CAFE)).toBe(true);
    expect(repetibleHoy(CENA)).toBe(false); // con reparto
    expect(repetibleHoy({ ...CAFE, varias: true })).toBe(false);
    expect(repetibleHoy({ ...CAFE, maestros_desactivados: ['TERCERO'] })).toBe(false);
    expect(repetibleHoy({ ...CAFE, devolucion_de: { hecho_id: 'x', nota: null, fecha_hecho: HOY, tercero: null } })).toBe(false);
    expect(repetibleHoy({ ...CAFE, estado_reparto: 'NO_DISPONIBLE' })).toBe(false);
    expect(repetibleHoy({ ...CAFE, importe_total: null })).toBe(false);
    const cap = { pago: PAGO as any, ingreso: null, origen: null, destino: null };
    expect(componerRepetir(CAFE, { presupuestable: true, magnitudes: [] }, cap, HOY, 'id-1')).toEqual({ ruta: 'GASTO', payload: {
      intencion_id: 'id-1', importe: '2.40', moneda: 'EUR', fecha_hecho: HOY, cuenta_id: 'nomina', presupuestable: true, atribucion: 'SOLO_MIO',
      categoria: { estado: 'CATEGORIA', categoria_id: 'cafes', magnitudes: [] }, tercero_id: 'bar', concepto: 'Café',
      financiacion: { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe: '2.40' } } });
    expect(componerRepetir(CAFE, { presupuestable: true, magnitudes: [{ magnitud_id: 'm', nombre: 'Litros', valor: '1', unidad: 'l' }] }, cap, HOY, 'id-1')).toBeNull();
    expect(componerRepetir(CAFE, { presupuestable: true, magnitudes: [] }, { ...cap, pago: [] }, HOY, 'id-1')).toBeNull();
  });

  test('«Repetir hoy» del café: aviso, ninguna petición tras el aviso, y a los 5 s un gasto NUEVO con fecha de hoy; la fila original sigue', async () => {
    const c = clienteActividad();
    await montarActividad(c);
    expect(screen.getByTestId('fila-cafe').props.accessibilityActions).toEqual([{ name: 'derecha', label: 'Repetir hoy' }, { name: 'izquierda', label: 'Más' }]);
    expect(screen.getByTestId('fila-cena').props.accessibilityActions).toEqual([{ name: 'izquierda', label: 'Más' }]); // con reparto no se ofrece
    accion('fila-cafe', 'derecha');
    await asentar();
    expect(screen.getByTestId('aviso-rapida-repetir-cafe-texto')).toHaveTextContent('Repetido hoy: Café · 2,40 €');
    expect(screen.getByTestId('fila-cafe')).toBeTruthy();
    const antes = llamadas(c);
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(llamadas(c)).toBe(antes);
    await esperar(1);
    await asentar();
    expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0]).toMatchObject({ intencion_id: '00000000-0000-4000-8000-000000000001', fecha_hecho: HOY, importe: '2.40', cuenta_id: 'nomina' });
  });

  test('«Deshacer» → ninguna escritura', async () => {
    const c = clienteActividad();
    await montarActividad(c);
    accion('fila-cafe', 'derecha');
    await asentar();
    const antes = llamadas(c);
    fireEvent.press(screen.getByTestId('aviso-rapida-repetir-cafe-deshacer'));
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(llamadas(c)).toBe(antes);
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  });

  test('con magnitudes hay dudas: abre el detalle («Más»); doble gesto → una sola intención', async () => {
    const c = clienteActividad({}, (id) => DET(CAFE, { magnitudes: [{ magnitud_id: 'm', nombre: 'Tazas', valor: '2', unidad: null }] }));
    await montarActividad(c);
    accion('fila-cafe', 'derecha');
    await asentar();
    expect(screen.queryByTestId('aviso-rapida-repetir-cafe')).toBeNull();
    expect(c.detalleActividad).toHaveBeenCalledWith('cafe');
    const c2 = clienteActividad();
    screen.unmount();
    await montarActividad(c2);
    const h = screen.getByTestId('fila-cafe').props.onAccessibilityAction;
    act(() => {
      h({ nativeEvent: { actionName: 'derecha' } });
      h({ nativeEvent: { actionName: 'derecha' } });
    });
    await asentar();
    accion('fila-cafe', 'derecha');
    await asentar();
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(c2.registrarGastoPagado).toHaveBeenCalledTimes(1);
  });

  test('rechazo → aviso con el motivo, sin éxito falso', async () => {
    const c = clienteActividad({ registrarGastoPagado: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje: 'Cuenta nómina ya no puede pagar gastos.' }) as any) });
    await montarActividad(c);
    accion('fila-cafe', 'derecha');
    await asentar();
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(screen.getByTestId('fallo-rapida-repetir-cafe-texto')).toHaveTextContent(/ya no puede pagar gastos/);
    expect(c.actividad).toHaveBeenCalledTimes(1);
  });
});

// ==================================================================
// Ajustes · «Desactivar»
// ==================================================================
const SIMON: Tercero = { id: 'simon', nombre: 'Simón Valenzuela', naturaleza: 'PERSONA', enabled: true, row_version: 3 };
const VIEJO: Tercero = { id: 'viejo', nombre: 'Tienda cerrada', naturaleza: null, enabled: false, row_version: 1 };

describe('Ajustes · «Desactivar»', () => {
  test('terceros: izquierda «Desactivar» (naranja) solo en activos; «Deshacer» → 0 peticiones; a los 5 s, su ruta', async () => {
    const desactivar = jest.fn(async () => ok({ tercero: { ...SIMON, enabled: false, row_version: 4 } }));
    const c = { ...clienteCategoriasStub(), listarTerceros: jest.fn(async () => ok({ terceros: [SIMON, VIEJO] })), desactivarTercero: desactivar } as unknown as ClienteApi;
    envolver(<TercerosAjustesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} onInmersiva={jest.fn()} />);
    await asentar();
    expect(screen.getByTestId('ajter-fila-simon').props.accessibilityActions).toEqual([{ name: 'izquierda', label: 'Desactivar' }]);
    expect(screen.getByTestId('ajter-fila-viejo').props.accessibilityActions).toBeUndefined();
    const antes = llamadas(c);
    accion('ajter-fila-simon', 'izquierda');
    expect(screen.getByTestId('aviso-rapida-simon-texto')).toHaveTextContent('Simón Valenzuela desactivado');
    fireEvent.press(screen.getByTestId('aviso-rapida-simon-deshacer'));
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(llamadas(c)).toBe(antes);
    accion('ajter-fila-simon', 'izquierda');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(desactivar).toHaveBeenCalledWith('simon', 3);
  });

  test('plantillas: «Desactivar» por su ruta; error → la fila vuelve con el motivo', async () => {
    const plt = (p: Partial<Plantilla> & { id: string; nombre: string }): Plantilla => ({
      tipo_hecho_id: 'GASTO', categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null, presupuestable_default: null,
      enabled: true, row_version: 2, tipo: 'GASTO', avisos: [], ...p,
    } as Plantilla);
    const desactivar = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'Ha cambiado mientras la mirabas. Vuelve a intentarlo.' }) as any);
    const c = { ...clienteCategoriasStub(), listarPlantillas: jest.fn(async () => ok({ plantillas: [plt({ id: 'super', nombre: 'Súper semanal' })], acciones: [] })),
      cuentasPago: jest.fn(async () => ok({ cuentas: [] })), cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [] })), desactivarPlantilla: desactivar } as unknown as ClienteApi;
    envolver(<PlantillasAjustesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} onInmersiva={jest.fn()} />);
    await asentar();
    accion('ajplt-fila-super', 'izquierda');
    expect(screen.queryByTestId('ajplt-fila-super')).toBeNull();
    expect(screen.getByTestId('aviso-rapida-super-texto')).toHaveTextContent('Súper semanal desactivada');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(desactivar).toHaveBeenCalledWith('super', 2);
    expect(screen.getByTestId('ajplt-fila-super')).toBeTruthy();
    expect(screen.getByTestId('fallo-rapida-super-texto')).toHaveTextContent(/Ha cambiado mientras la mirabas/);
  });

  test('categorías: sin subcategorías activas, «Desactivar» rápido con el modo seguro; con subcategorías activas, la hoja de siempre', async () => {
    const lista = [nodo({ id: 'hogar', nombre: 'Hogar' }), nodo({ id: 'luz', nombre: 'Luz', parent_id: 'hogar' }), nodo({ id: 'cafes', nombre: 'Cafés', orden: 1, row_version: 5 })];
    const desactivar = jest.fn(async () => ok({ categoria: { ...lista[2], enabled: false } }));
    const c = { ...clienteCategoriasStub(lista), desactivarCategoria: desactivar } as unknown as ClienteApi;
    envolver(<CategoriasAjustesScreen cliente={c} nuevoId={nuevoId} onAtras={jest.fn()} onInmersiva={jest.fn()} />);
    await asentar();
    accion('fila-cafes', 'izquierda');
    expect(screen.getByTestId('aviso-rapida-cafes-texto')).toHaveTextContent('Cafés desactivada');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(desactivar).toHaveBeenCalledWith('cafes', { row_version: 5, modo: 'SOLO_SI_SIN_HIJOS_ACTIVOS' });
    accion('fila-hogar', 'izquierda');
    await asentar();
    expect(screen.queryByTestId('aviso-rapida-hogar')).toBeNull();
    expect(desactivar).toHaveBeenCalledTimes(1);
  });
});
