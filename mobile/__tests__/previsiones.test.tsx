// ============================================================
// GAPTO MOBILE 2027
// Fichero: previsiones.test.tsx
// Ruta: mobile/__tests__/previsiones.test.tsx
// Descripción: Confirmación de previsiones (F05-06 M5 §B2; láminas PREV v0.2 y HOME-01 v0.4; F05 §59). Dominio puro (importes por naturaleza, «Desconocido» nunca 0, cobertura y desviación, línea de la fila, «Por pagar» / «Por cobrar» separados, campana, «Se vinculará X €», bloque `prevision` solo con respuesta explícita, payloads por tipo y regla del swipe) y pantallas por estado, en claro y oscuro: Inicio (campana con 0, 2 y 3; bloque como mucho dos; sin importes sumados; estado de fallo con «Reintentar» y «!»; próximos de solo lectura), «Pendientes», detalle (acciones atenuadas con motivo, parcial, desconocido, terminal en solo lectura), registro desde la previsión («¿Queda cubierta?» sin respuesta, revisión que separa realidad y previsión, reintento con la MISMA identidad), swipe (consecuencia antes de «Confirmar pago y cubrir»), «Ya lo registré» (sin preselección, «Buscar en más fechas», toda la porción libre, PORCION_CAMBIADA relee) y omitir (409 con el estado actual; tras un fallo, «No sabemos si se guardó»).
// Versión: 0.1.0 (F05-06 M5 §B2)
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, DetallePrevision, FilaPrevision } from '../src/api/cliente';
import {
  admiteSwipe,
  bloquePrevision,
  coberturaTexto,
  componerRegistro,
  contadorCampana,
  desviacionTexto,
  faltaRegistro,
  importeFila,
  lineaFila,
  textoNaturaleza,
  textoSeVinculara,
} from '../src/domain/prevision';
import { HomeScreen } from '../src/screens/HomeScreen';
import { PendientesScreen } from '../src/screens/PendientesScreen';
import { PrevisionDetalleScreen } from '../src/screens/PrevisionDetalleScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const ACCIONES_OK = {
  registrar: { disponible: true, motivo: null }, ya_lo_registre: { disponible: true, motivo: null },
  omitir: { disponible: true, motivo: null }, swipe: { disponible: true, motivo: null },
};

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
const SEGURO = fila({ id: 'seguro', concepto: 'Seguro hogar', fecha_desde: '2026-10-25', fecha_hasta: '2026-10-30', importe_esperado: '120.00',
  cubierto: '40.00', queda: '80.00', con_realidad: true, pagos: 1, vencida: false });
const TRASPASO = fila({ id: 'traspaso', tipo: 'TRANSFERENCIA', naturaleza: 'ENTRE_CUENTAS', concepto: 'Nómina → Ahorro', tercero: null, categoria: null,
  fecha_desde: '2026-10-30', fecha_hasta: '2026-10-30', importe_esperado: '500.00', queda: '500.00', vencida: false,
  cuenta_entrada: { id: 'ahorro', nombre: 'Ahorro' } });
const ALQUILER = fila({ id: 'alquiler', concepto: 'Alquiler', fecha_desde: '2026-11-01', fecha_hasta: '2026-11-01', importe_esperado: '561.00', queda: '561.00', vencida: false });

function detalle(f: FilaPrevision, o: Partial<DetallePrevision> = {}): DetallePrevision {
  return { ...f, estado_derivado: null, vinculos: [], acciones: ACCIONES_OK, ...o };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    registrarGastoPagado: jest.fn(async (pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false } }) as any),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
      { cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' }] } }) as any),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: [
      { cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }, { cuenta_id: 'ahorro', nombre: 'Ahorro', moneda: 'EUR' }] } }) as any),
    ...o,
  } as ClienteApi;
}

function envolver(ui: React.ReactElement, forzar?: 'dark' | 'light') {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema forzar={forzar}>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}
const plano = () => JSON.stringify(screen.toJSON());

// ==================================================================
// Dominio
// ==================================================================
describe('dominio', () => {
  test('importes por naturaleza: «~» pagos, «+» cobros, transferencia sin signo y «Desconocido» nunca 0', () => {
    expect(importeFila(fila())).toBe('~74,00 €');
    expect(importeFila(NOMINA)).toBe('+2.100,00 €');
    expect(importeFila(TRASPASO)).toBe('500,00 €');
    expect(importeFila(fila({ importe_esperado: null, queda: null }))).toBe('Desconocido');
    expect(importeFila(SEGURO, true)).toBe('~80,00 €');
  });

  test('cobertura y desviación: «Pagado 40,00 de 120,00 · queda 80,00» y «10,00 € más de lo previsto», nunca un «queda» negativo', () => {
    expect(coberturaTexto(SEGURO)).toBe('Pagado 40,00 de 120,00 · queda 80,00');
    expect(coberturaTexto(fila())).toBeNull();
    const gas = fila({ importe_esperado: '120.00', cubierto: '130.00', queda: null, desviacion: '10.00', con_realidad: true });
    expect(coberturaTexto(gas)).toBe('Pagado 130,00 de 120,00');
    expect(desviacionTexto(gas)).toBe('10,00 € más de lo previsto');
    expect(coberturaTexto(fila({ importe_esperado: null, cubierto: '23.10', queda: null, con_realidad: true }))).toBe('Pagado 23,10');
  });

  test('línea de la fila según la lámina', () => {
    expect(lineaFila(fila())).toBe('Venció el 5 oct · Falta confirmar');
    expect(lineaFila(NOMINA)).toBe('Cobro previsto · venció el 30 sep');
    expect(lineaFila(SEGURO)).toBe('Pagado 40,00 de 120,00 · queda 80,00 · vence el 30 oct');
    expect(lineaFila(ALQUILER, true)).toBe('Previsto 1 nov 2026');
    expect(lineaFila(TRASPASO, true)).toBe('Previsto 30 oct 2026 · Entre cuentas');
  });

  test('«Por pagar» y «Por cobrar» por separado; desconocido nunca 0', () => {
    expect(textoNaturaleza({ importe: '154.00', n: 2, desconocidos: 0 }, 'POR_PAGAR')).toBe('~154,00 €');
    expect(textoNaturaleza({ importe: '2100.00', n: 1, desconocidos: 0 }, 'POR_COBRAR')).toBe('+2.100,00 €');
    expect(textoNaturaleza({ importe: null, n: 1, desconocidos: 1 }, 'POR_PAGAR')).toBe('Desconocido');
    expect(textoNaturaleza({ importe: '74.00', n: 2, desconocidos: 1 }, 'POR_PAGAR')).toBe('~74,00 € + 1 sin importe');
  });

  test('campana: nada con 0 o cargando, el número con pendientes y «!» si falla', () => {
    expect(contadorCampana({ fase: 'OK', n: 0 })).toBeNull();
    expect(contadorCampana({ fase: 'CARGANDO' })).toBeNull();
    expect(contadorCampana({ fase: 'OK', n: 3 })).toBe('3');
    expect(contadorCampana({ fase: 'ERROR' })).toBe('!');
  });

  test('«Se vinculará X €»: toda la porción libre, aunque supere lo previsto', () => {
    expect(textoSeVinculara('76.10', fila())).toEqual({
      titulo: 'Se vinculará 76,10 € de este registro', detalle: 'Es todo lo que tiene libre, aunque supere los ~74,00 € previstos.' });
    expect(textoSeVinculara('12.00', fila()).detalle).toBe('Es todo lo que tiene libre.');
  });

  test('bloque `prevision` solo con respuesta explícita; payloads por tipo', () => {
    expect(bloquePrevision(fila(), null)).toBeNull();
    expect(bloquePrevision(fila(), false)).toEqual({ prevision_id: 'luz', row_version: 1, marcar_realizada: false });
    const base = { importe: '81.37', fecha: '2026-10-07', cuentaId: 'nomina', cuentaDestinoId: null, presupuestable: true, conCategoria: true, propuestaSelf100: true, marcar: null };
    expect(componerRegistro(fila(), base, 'i1')).toBeNull();
    expect(faltaRegistro(fila(), base)).toEqual(['¿queda cubierta?']);
    const g = componerRegistro(fila(), { ...base, marcar: true }, 'i1')!;
    expect(g.ruta).toBe('GASTO');
    expect(g.payload).toMatchObject({ intencion_id: 'i1', importe: '81.37', cuenta_id: 'nomina', tercero_id: 'iber', atribucion: 'SOLO_MIO',
      categoria: { estado: 'CATEGORIA', categoria_id: 'elec', magnitudes: [] },
      financiacion: { estado: 'PROPUESTA_ACEPTADA', importe: '81.37' }, prevision: { prevision_id: 'luz', row_version: 1, marcar_realizada: true } });
    expect(componerRegistro(fila(), { ...base, marcar: true, conCategoria: false, propuestaSelf100: false }, 'i1')!.payload)
      .toMatchObject({ categoria: { estado: 'SIN_CATEGORIA' }, financiacion: { estado: 'NO_DETERMINADA' } });
    const i = componerRegistro(NOMINA, { ...base, importe: '2100.00', marcar: false }, 'i2')!;
    expect(i.ruta).toBe('INGRESO');
    expect(i.payload).not.toHaveProperty('financiacion');
    const t = componerRegistro(TRASPASO, { ...base, importe: '500.00', cuentaDestinoId: 'ahorro', marcar: true }, 'i3')!;
    expect(t).toEqual({ ruta: 'TRANSFERENCIA', payload: { intencion_id: 'i3', importe: '500.00', moneda: 'EUR', fecha_hecho: '2026-10-07',
      cuenta_origen_id: 'nomina', cuenta_destino_id: 'ahorro', nota: null, prevision: { prevision_id: 'traspaso', row_version: 1, marcar_realizada: true } } });
  });

  test('swipe solo con gasto o ingreso, esperado conocido, cuenta prevista y sin pagos', () => {
    expect(admiteSwipe(fila())).toBe(true);
    expect(admiteSwipe(NOMINA)).toBe(true);
    expect(admiteSwipe(fila({ importe_esperado: null }))).toBe(false);
    expect(admiteSwipe(SEGURO)).toBe(false);
    expect(admiteSwipe(TRASPASO)).toBe(false);
    expect(admiteSwipe(fila({ cuenta_salida: null }))).toBe(false);
    expect(admiteSwipe(fila({ moneda: 'USD' }))).toBe(false);
  });
});

// ==================================================================
// Inicio (HOME-01 v0.4)
// ==================================================================
function inicio(n: number, primeras: FilaPrevision[], proximos: FilaPrevision[] = []) {
  return jest.fn(async () => ({ tipo: 'OK', datos: { hoy: '2026-10-10', requiere_atencion: { n, primeras }, proximos } }) as any);
}
function montarHome(c: ClienteApi, forzar?: 'dark', extra: Record<string, unknown> = {}) {
  const onPendientes = jest.fn();
  const onPrevision = jest.fn();
  envolver(<HomeScreen cliente={c} ahora={AHORA} refresco={0} onRegistrar={jest.fn()} nuevoId={nuevoId} onPendientes={onPendientes} onPrevision={onPrevision} {...extra} />, forzar);
  return { onPendientes, onPrevision };
}

describe('Inicio', () => {
  test('I03: sin pendientes no hay campana ni bloque', async () => {
    montarHome(cliente({ inicioPrevisiones: inicio(0, [], [ALQUILER]) }));
    expect(await screen.findByTestId(`proximo-${ALQUILER.id}`)).toBeTruthy();
    expect(screen.queryByTestId('campana-pendientes')).toBeNull();
    expect(screen.queryByTestId('bloque-atencion')).toBeNull();
  });

  test('I01: con 3 pendientes, campana «3», el bloque con dos asuntos y «Ver todos ›», sin importes sumados', async () => {
    const { onPendientes, onPrevision } = montarHome(cliente({ inicioPrevisiones: inicio(3, [NOMINA, fila()], [ALQUILER, TRASPASO]) }));
    expect(await screen.findByTestId('campana-contador')).toHaveTextContent('3');
    const bloque = within(screen.getByTestId('bloque-atencion'));
    expect(bloque.getByTestId('atencion-n')).toHaveTextContent('3');
    expect(bloque.getByTestId(`atencion-${NOMINA.id}-importe`)).toHaveTextContent('+2.100,00 €');
    expect(bloque.getByTestId('atencion-luz-importe')).toHaveTextContent('~74,00 €');
    expect(bloque.getByTestId('atencion-luz-linea')).toHaveTextContent('Venció el 5 oct · Falta confirmar');
    expect(bloque.queryAllByText(/Por pagar|Por cobrar|Total/)).toHaveLength(0);
    expect(bloque.queryByTestId(`atencion-${SEGURO.id}`)).toBeNull(); // el tercero está en la lista
    fireEvent.press(bloque.getByTestId('atencion-ver-todos'));
    fireEvent.press(screen.getByTestId('campana-pendientes'));
    expect(onPendientes).toHaveBeenCalledTimes(2);
    fireEvent.press(bloque.getByTestId('atencion-luz'));
    expect(onPrevision).toHaveBeenCalledWith(expect.objectContaining({ id: 'luz' }));
    // Próximos: solo lectura, sin swipe, con «Entre cuentas».
    expect(screen.getByTestId(`proximo-${TRASPASO.id}-linea`)).toHaveTextContent('Previsto 30 oct 2026 · Entre cuentas');
    expect(screen.getByTestId(`proximo-${ALQUILER.id}`).props.accessibilityActions).toBeUndefined();
  });

  test('con 2 pendientes, la campana dice 2 (oscuro)', async () => {
    montarHome(cliente({ inicioPrevisiones: inicio(2, [fila(), SEGURO]) }), 'dark');
    expect(await screen.findByTestId('campana-contador')).toHaveTextContent('2');
    expect(screen.getByTestId(`atencion-${SEGURO.id}-linea`)).toHaveTextContent('Pagado 40,00 de 120,00 · queda 80,00 · vence el 30 oct');
  });

  test('I05: si la lectura falla, el bloque lo dice con «Reintentar» y la campana lleva «!»; nunca «sin pendientes»', async () => {
    const lectura = jest.fn().mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'x' }).mockResolvedValue({ tipo: 'OK', datos: { hoy: '2026-10-10', requiere_atencion: { n: 1, primeras: [fila()] }, proximos: [] } });
    montarHome(cliente({ inicioPrevisiones: lectura as any }));
    expect(await screen.findByTestId('atencion-error')).toBeTruthy();
    expect(screen.getByText('No se pudieron cargar los pendientes')).toBeTruthy();
    expect(screen.getByTestId('campana-contador')).toHaveTextContent('!');
    expect(screen.queryByTestId('proximos-vacio')).toBeNull();
    fireEvent.press(screen.getByTestId('atencion-reintentar'));
    expect(await screen.findByTestId('atencion-luz')).toBeTruthy();
    expect(screen.getByTestId('campana-contador')).toHaveTextContent('1');
  });

  test('sin línea ni barra de presupuesto mientras F08 no la alimente (D-HOME-07)', async () => {
    montarHome(cliente({ inicioPrevisiones: inicio(0, []) }));
    await screen.findByTestId('proximos-vacio');
    expect(screen.queryByText('Presupuesto de gasto')).toBeNull();
  });

  test('B1: el swipe solo abre la hoja; «Confirmar pago y cubrir» registra con marcar_realizada = true', async () => {
    const c = cliente({ inicioPrevisiones: inicio(1, [fila()]) });
    montarHome(c);
    const filaLuz = await screen.findByTestId('atencion-luz');
    expect(filaLuz.props.accessibilityActions).toEqual([{ name: 'activate' }, { name: 'swipe', label: 'Pagado' }]);
    fireEvent(filaLuz, 'accessibilityAction', { nativeEvent: { actionName: 'swipe' } });
    expect(c.registrarGastoPagado).not.toHaveBeenCalled(); // nunca registra en un toque
    expect(screen.getByTestId('swipe-consecuencia')).toHaveTextContent('Quedará cubierta');
    expect(screen.getByTestId('swipe-esperado')).toHaveTextContent('~74,00 €');
    expect(screen.getByTestId('swipe-importe').props.value).toBe('74,00');
    expect(screen.getByTestId('swipe-cuenta')).toHaveTextContent('Cuenta nómina · 5 oct');
    fireEvent.changeText(screen.getByTestId('swipe-importe'), '81,37');
    await act(async () => fireEvent.press(screen.getByTestId('swipe-confirmar')));
    await waitFor(() => expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1));
    expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0]).toMatchObject({
      importe: '81.37', fecha_hecho: '2026-10-05', cuenta_id: 'nomina', financiacion: { estado: 'PROPUESTA_ACEPTADA' },
      prevision: { prevision_id: 'luz', row_version: 1, marcar_realizada: true } });
  });

  test('sin swipe con esperado desconocido o con pago parcial', async () => {
    montarHome(cliente({ inicioPrevisiones: inicio(2, [fila({ id: 'agua', importe_esperado: null, queda: null }), SEGURO]) }));
    expect((await screen.findByTestId('atencion-agua')).props.accessibilityActions).toBeUndefined();
    expect(screen.getByTestId('atencion-agua-importe')).toHaveTextContent('Desconocido');
    expect(screen.getByTestId(`atencion-${SEGURO.id}`).props.accessibilityActions).toBeUndefined();
  });
});

// ==================================================================
// «Pendientes»
// ==================================================================
test('«Pendientes»: «Por pagar» y «Por cobrar» separados y secciones', async () => {
  const c = cliente({ pendientesPrevisiones: jest.fn(async () => ({ tipo: 'OK', datos: { hoy: '2026-10-10', n: 3,
    por_pagar: { importe: '154.00', n: 2, desconocidos: 0 }, por_cobrar: { importe: '2100.00', n: 1, desconocidos: 0 },
    secciones: { vencidas: [fila(), NOMINA], con_pago_parcial: [SEGURO], sin_fecha: [] } } }) as any) });
  envolver(<PendientesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} refresco={0} onAtras={jest.fn()} onDetalle={jest.fn()} onFormularioCompleto={jest.fn()} onCambios={jest.fn()} />);
  expect(await screen.findByTestId('por-pagar')).toHaveTextContent('~154,00 €');
  expect(screen.getByTestId('por-cobrar')).toHaveTextContent('+2.100,00 €');
  expect(screen.queryByText(/Total/)).toBeNull();
  expect(within(screen.getByTestId('pendientes-vencidas')).getByTestId('pendiente-luz')).toBeTruthy();
  expect(within(screen.getByTestId('pendientes-parciales')).getByTestId('pendiente-seguro-importe')).toHaveTextContent('~80,00 €');
  expect(screen.queryByTestId('pendientes-sin-fecha')).toBeNull();
});

test('«Pendientes» con la lectura fallida: estado de fallo, nunca «No hay nada pendiente»', async () => {
  const c = cliente({ pendientesPrevisiones: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: 'x' }) as any) });
  envolver(<PendientesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} refresco={0} onAtras={jest.fn()} onDetalle={jest.fn()} onFormularioCompleto={jest.fn()} onCambios={jest.fn()} />, 'dark');
  expect(await screen.findByTestId('pendientes-error')).toBeTruthy();
  expect(screen.queryByTestId('pendientes-vacio')).toBeNull();
});

// ==================================================================
// Detalle, registro, «Ya lo registré» y omitir
// ==================================================================
function montarDetalle(c: ClienteApi, forzar?: 'dark') {
  const onCerrar = jest.fn();
  envolver(<PrevisionDetalleScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} previsionId="luz" onCerrar={onCerrar} />, forzar);
  return onCerrar;
}
const conDetalle = (d: DetallePrevision, o: Partial<ClienteApi> = {}) => cliente({ detallePrevision: jest.fn(async () => ({ tipo: 'OK', datos: d }) as any), ...o });

describe('detalle', () => {
  test('A2: tres salidas y «Es una previsión: no ha movido dinero.»', async () => {
    montarDetalle(conDetalle(detalle(fila())));
    expect(await screen.findByTestId('prevision-accion-registrar')).toBeTruthy();
    expect(screen.getByText('Registrar pago')).toBeTruthy();
    expect(screen.getByText('Ya lo registré')).toBeTruthy();
    expect(screen.getByText('No hubo este mes')).toBeTruthy();
    expect(screen.getByText('Es una previsión: no ha movido dinero.')).toBeTruthy();
    expect(screen.getByTestId('detalle-esperado')).toHaveTextContent('~74,00 €');
  });

  test('B5: parcial con «Para cubrirla, registra o enlaza el resto.» y omitir atenuado con su motivo', async () => {
    const motivo = '«No hubo este mes» no está disponible: ya tiene un pago enlazado.';
    montarDetalle(conDetalle(detalle(SEGURO, { acciones: { ...ACCIONES_OK, omitir: { disponible: false, motivo }, swipe: { disponible: false, motivo: 'x' } } })), 'dark');
    expect(await screen.findByTestId('detalle-cubrir-resto')).toHaveTextContent('Para cubrirla, registra o enlaza el resto.');
    expect(screen.getByTestId('detalle-queda')).toHaveTextContent('80,00 €');
    expect(screen.getByTestId('prevision-accion-omitir')).toBeDisabled();
    expect(screen.getByTestId('prevision-accion-omitir-motivo')).toHaveTextContent(motivo);
    expect(plano()).not.toMatch(/Dar por cubierta/);
  });

  test('B4/B6: «Desconocido» sin confirmación rápida y desviación visible', async () => {
    montarDetalle(conDetalle(detalle(fila({ importe_esperado: null, queda: null }))));
    expect(await screen.findByTestId('detalle-esperado')).toHaveTextContent('Desconocido');
    expect(screen.getByTestId('detalle-sin-esperado')).toBeTruthy();
    expect(plano()).not.toMatch(/0,00 €/);
  });

  test('terminal o en revisión: solo lectura, sin acciones', async () => {
    const motivo = 'Esta previsión ya no está pendiente: aquí solo se consulta.';
    const no = { disponible: false, motivo };
    montarDetalle(conDetalle(detalle(fila({ estado: 'REALIZADA' }), { estado_derivado: 'REALIZADA_SIN_REALIDAD_ACTIVA',
      acciones: { registrar: no, ya_lo_registre: no, omitir: no, swipe: no } })));
    expect(await screen.findByTestId('prevision-estado')).toHaveTextContent('Cubierta sin registro activo');
    for (const id of ['prevision-accion-registrar', 'prevision-accion-ya', 'prevision-accion-omitir']) expect(screen.getByTestId(id)).toBeDisabled();
  });

  test('A3/A4: registrar desde la previsión; «¿Queda cubierta?» sin respuesta bloquea; la revisión separa realidad y previsión', async () => {
    const c = conDetalle(detalle(fila()));
    const onCerrar = montarDetalle(c);
    fireEvent.press(await screen.findByTestId('prevision-accion-registrar'));
    await screen.findByTestId('prevision-cuenta-nomina');
    expect(screen.getByTestId('prevision-cuenta-nomina')).toHaveTextContent('✓ Cuenta nómina · De la previsión'); // propuesta visible
    expect(screen.getByTestId('prevision-tercero')).toHaveTextContent('Iberdrola · De la previsión');
    expect(screen.getByTestId('cubierta-si').props.accessibilityState.checked).toBe(false);
    expect(screen.getByTestId('cubierta-no').props.accessibilityState.checked).toBe(false);
    expect(screen.getByTestId('prevision-revisar')).toBeDisabled();
    expect(screen.getByTestId('prevision-falta')).toHaveTextContent('Falta: ¿queda cubierta?');
    fireEvent.changeText(screen.getByTestId('prevision-importe'), '81,37');
    expect(screen.getByTestId('prevision-distinto')).toBeTruthy();
    fireEvent.press(screen.getByTestId('cubierta-si'));
    fireEvent.press(screen.getByTestId('prevision-revisar'));
    expect(within(screen.getByTestId('revision-se-registra')).getByText('81,37 €')).toBeTruthy();
    expect(within(screen.getByTestId('revision-se-registra')).getByText('−81,37 €')).toBeTruthy();
    expect(within(screen.getByTestId('revision-la-prevision')).getByText('Cubierta')).toBeTruthy();
    expect(screen.getByTestId('revision-sin-doble')).toHaveTextContent(/no mueve dinero/);
    // Sin respuesta del servidor: se reintenta con la MISMA identidad.
    (c.registrarGastoPagado as jest.Mock).mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'Sin respuesta' });
    await act(async () => fireEvent.press(screen.getByTestId('prevision-registrar')));
    expect(await screen.findByTestId('prevision-registro-indeterminado')).toBeTruthy();
    await act(async () => fireEvent.press(screen.getByTestId('prevision-registrar')));
    const llamadas = (c.registrarGastoPagado as jest.Mock).mock.calls;
    expect(llamadas).toHaveLength(2);
    expect(llamadas[1][0].intencion_id).toBe(llamadas[0][0].intencion_id);
    expect(llamadas[1][0].prevision).toEqual({ prevision_id: 'luz', row_version: 1, marcar_realizada: true });
    fireEvent.press(await screen.findByTestId('prevision-registro-listo'));
    expect(onCerrar).toHaveBeenCalledWith(true);
  });

  test('D1/D2: transferencia desde la previsión, en oscuro, sin efecto económico', async () => {
    const c = conDetalle(detalle(TRASPASO), { registrarTransferencia: jest.fn(async () => ({ tipo: 'OK', datos: {} }) as any) });
    montarDetalle(c, 'dark');
    fireEvent.press(await screen.findByTestId('prevision-accion-registrar'));
    await screen.findByTestId('prevision-destino-ahorro');
    fireEvent.press(screen.getByTestId('cubierta-si'));
    fireEvent.press(screen.getByTestId('prevision-revisar'));
    expect(screen.getByTestId('revision-sin-doble')).toHaveTextContent(/no es gasto ni ingreso/);
    await act(async () => fireEvent.press(screen.getByTestId('prevision-registrar')));
    expect((c.registrarTransferencia as jest.Mock).mock.calls[0][0]).toMatchObject({ cuenta_origen_id: 'nomina', cuenta_destino_id: 'ahorro',
      importe: '500.00', prevision: { prevision_id: 'traspaso', marcar_realizada: true } });
  });

  test('B2: «Ya lo registré» sin preselección, «Buscar en más fechas» y toda la porción libre', async () => {
    const cand = (ampliado: boolean) => ({ tipo: 'OK', datos: { prevision_id: 'luz', ampliado, ventana_dias: ampliado ? 60 : 15, mensaje: null, candidatos: [
      { hecho_id: 'h1', fecha_hecho: '2026-10-03', concepto: null, tercero: 'Iberdrola', categoria: 'Hogar › Electricidad', cuenta: 'Cuenta nómina', importe_total: '76.10', porcion_disponible: '76.10' },
      ...(ampliado ? [{ hecho_id: 'h2', fecha_hecho: '2026-08-22', concepto: null, tercero: 'Iberdrola', categoria: null, cuenta: 'Efectivo', importe_total: '12.00', porcion_disponible: '12.00' }] : []),
    ] } });
    const c = conDetalle(detalle(fila()), {
      candidatosPrevision: jest.fn(async (_id: string, amp: boolean) => cand(amp) as any),
      vincularPrevision: jest.fn(async (_id: string, pl: any) => ({ tipo: 'OK', datos: { ...pl, prevision_id: 'luz', importe_vinculado: pl.importe_a_vincular, estado: 'REALIZADA', idempotente: false } }) as any),
    });
    const onCerrar = montarDetalle(c);
    fireEvent.press(await screen.findByTestId('prevision-accion-ya'));
    expect(await screen.findByTestId('candidato-h1')).toBeTruthy();
    expect(screen.getByTestId('candidato-h1').props.accessibilityState.checked).toBe(false); // nada elegido al entrar
    expect(screen.getByTestId('ya-enlazar')).toBeDisabled();
    expect(screen.queryByTestId('ya-se-vinculara')).toBeNull();
    fireEvent.press(screen.getByTestId('ya-mas-fechas'));
    expect(await screen.findByTestId('candidato-h2')).toBeTruthy();
    expect(c.candidatosPrevision).toHaveBeenLastCalledWith('luz', true);
    fireEvent.press(screen.getByTestId('candidato-h1'));
    expect(screen.getByTestId('ya-se-vinculara')).toHaveTextContent(/Se vinculará 76,10 € de este registro/);
    expect(screen.getByTestId('ya-se-vinculara')).toHaveTextContent(/aunque supere los ~74,00 € previstos/);
    expect(screen.getByTestId('ya-enlazar')).toBeDisabled(); // falta «¿Queda cubierta?»
    fireEvent.press(screen.getByTestId('ya-cubierta-no'));
    await act(async () => fireEvent.press(screen.getByTestId('ya-enlazar')));
    expect((c.vincularPrevision as jest.Mock).mock.calls[0][1]).toMatchObject({ hecho_id: 'h1', importe_a_vincular: '76.10', marcar_realizada: false, row_version: 1 });
    expect(onCerrar).toHaveBeenCalledWith(true);
  });

  test('«Ya lo registré»: PORCION_CAMBIADA relee y obliga a volver a elegir (nunca otra cantidad en silencio)', async () => {
    const lista = jest.fn()
      .mockResolvedValueOnce({ tipo: 'OK', datos: { prevision_id: 'luz', ampliado: false, ventana_dias: 15, mensaje: null, candidatos: [
        { hecho_id: 'h1', fecha_hecho: '2026-10-03', concepto: null, tercero: 'Iberdrola', categoria: null, cuenta: null, importe_total: '100.00', porcion_disponible: '60.00' }] } })
      .mockResolvedValue({ tipo: 'OK', datos: { prevision_id: 'luz', ampliado: false, ventana_dias: 15, mensaje: null, candidatos: [
        { hecho_id: 'h1', fecha_hecho: '2026-10-03', concepto: null, tercero: 'Iberdrola', categoria: null, cuenta: null, importe_total: '100.00', porcion_disponible: '100.00' }] } });
    const c = conDetalle(detalle(fila()), {
      candidatosPrevision: lista as any,
      vincularPrevision: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'PORCION_CAMBIADA', mensaje: 'Ese registro ha cambiado mientras lo elegías: revisa cuánto se vinculará. No se ha guardado nada.' }) as any),
    });
    montarDetalle(c);
    fireEvent.press(await screen.findByTestId('prevision-accion-ya'));
    fireEvent.press(await screen.findByTestId('candidato-h1'));
    fireEvent.press(screen.getByTestId('ya-cubierta-si'));
    await act(async () => fireEvent.press(screen.getByTestId('ya-enlazar')));
    expect(await screen.findByTestId('ya-error')).toHaveTextContent(/ha cambiado/);
    await waitFor(() => expect(lista).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('ya-se-vinculara')).toBeNull();
    expect(screen.getByTestId('ya-enlazar')).toBeDisabled();
    fireEvent.press(await screen.findByTestId('candidato-h1'));
    expect(screen.getByTestId('ya-se-vinculara')).toHaveTextContent(/Se vinculará 100,00 €/);
  });

  test('B3/B7: omitir con motivo; 409 enseña el estado actual («Ha cambiado; revisa»), nunca «hecho»', async () => {
    const c = conDetalle(detalle(fila()), {
      omitirPrevision: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'Ha cambiado; revisa. No se ha guardado nada.',
        detalle: { estado_actual: { estado: 'REALIZADA', estado_derivado: null, row_version: 3, con_realidad: true, cubierto: '74.00' } } }) as any),
    });
    montarDetalle(c);
    fireEvent.press(await screen.findByTestId('prevision-accion-omitir'));
    expect(screen.getByTestId('hoja-omitir')).toBeTruthy();
    fireEvent.changeText(screen.getByTestId('omitir-motivo'), '  Facturación bimestral ');
    await act(async () => fireEvent.press(screen.getByTestId('omitir-confirmar')));
    expect((c.omitirPrevision as jest.Mock).mock.calls[0][1]).toMatchObject({ row_version: 1, motivo: 'Facturación bimestral' });
    expect(await screen.findByTestId('aviso-estado-actual')).toBeTruthy();
    expect(screen.getByText('Ha cambiado; revisa')).toBeTruthy();
    expect(screen.getByTestId('aviso-estado-valor')).toHaveTextContent('Cubierta');
  });

  test('B7: tras un fallo de conexión, el reintento usa la misma identidad y, si ya no está pendiente, «No sabemos si se guardó»', async () => {
    const omitir = jest.fn()
      .mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar.' })
      .mockResolvedValueOnce({ tipo: 'RECHAZADO', codigo: 'ESTADO_PREVISION_INCOMPATIBLE', mensaje: 'Esta previsión ya no está pendiente.',
        detalle: { estado_actual: { estado: 'OMITIDA', estado_derivado: null, row_version: 2, con_realidad: false, cubierto: '0.00' } } });
    const c = conDetalle(detalle(fila()), { omitirPrevision: omitir as any });
    montarDetalle(c, 'dark');
    fireEvent.press(await screen.findByTestId('prevision-accion-omitir'));
    await act(async () => fireEvent.press(screen.getByTestId('omitir-confirmar')));
    expect(await screen.findByTestId('omitir-error')).toBeTruthy();
    await act(async () => fireEvent.press(screen.getByTestId('omitir-confirmar')));
    expect(omitir.mock.calls[1][1].intencion_id).toBe(omitir.mock.calls[0][1].intencion_id);
    expect(await screen.findByText('No sabemos si se guardó')).toBeTruthy();
    expect(screen.getByTestId('aviso-estado-texto')).toHaveTextContent('No sabemos si se guardó tu acción anterior. Este es el estado actual.');
    expect(screen.getByTestId('aviso-estado-valor')).toHaveTextContent('Omitida');
  });
});
