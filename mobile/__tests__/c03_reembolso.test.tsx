// ============================================================
// GAPTO MOBILE 2027
// Fichero: c03_reembolso.test.tsx
// Ruta: mobile/__tests__/c03_reembolso.test.tsx
// Descripción: C-03 «gasto propio reembolsable» en la UI (F05 §66.2 y anexo §66.A, §66.A.11.9; lámina F05-07 v0.3 C1–C4 y D1; D-F0507L-04..06; CONTRATO_API_C03). Dominio: importe recuperable de 0,01 € al total sin valor por defecto, lo que falta, sellado (payload del gasto pagado sin `atribucion` y con `reembolso`), texto tras el cobro (nunca «Saldado» con saldo indeterminado) y reconocimiento del derecho. C1: respuesta «Mío, pero me lo reembolsan» solo en gastos. C2: nada marcado, «Hecho» deshabilitado hasta elegir quién y cuánto, personas y empresas (nunca el comercio, ni ORGANISMO/OTRO/sin naturaleza, ni deshabilitadas), alta de empresa, «Otra cantidad» acotada, textos fijos y exclusión visible de la previsión; claro y oscuro. Formulario: resumen, «Quitar», sin «Repartir» ni «Otra persona», comercio igual a quien lo debe bloquea. Envío a POST /v1/intenciones/gasto-reembolsable y éxito C3 con el gasto y lo que te deben por separado; rechazos en lenguaje llano. C4: «Pendiente con…» abre el derecho elegido (dos derechos con la misma empresa), «Registrar cobro» deshabilitado hasta elegir cuenta, textos del derecho y del cobro parcial y total. Detalle: `posiciones_vinculadas` con su `entidad_id`. Devolución bloqueada con motivo.
// Versión: 0.1.0 (F05-D052 paso 2 · C-03 UI)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, DetalleActividad, FilaActividad, Respuesta } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import { motivoNoDisponible } from '../src/domain/devolucion';
import { borradorInicial, sellarReembolsable, validar } from '../src/domain/intencion';
import {
  esDerechoReembolso,
  faltaReembolso,
  importeReembolso,
  PayloadGastoReembolsable,
  REEMBOLSO_VACIO,
  TEXTO_COBRO_NO_INGRESO,
  TEXTO_COMO_SE_REGISTRA,
  TEXTO_SIN_PREVISION,
  textoTrasCobro,
} from '../src/domain/reembolso';
import type { PendienteConPersona, RepartoDeHecho } from '../src/domain/reparto';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);
const HOY = '2026-10-26';
const TARJETA = 'c0000000-0000-4000-8000-000000000001';
const NOMINA = 'c0000000-0000-4000-8000-000000000002';
const ARBOL: CategoriaNodo[] = [nodo({ id: 'mov', nombre: 'Movilidad' }), nodo({ id: 'comb', nombre: 'Combustible', parent_id: 'mov' })];
const TERCEROS = [
  { id: 'empresa', nombre: 'Empresa SL', naturaleza: 'EMPRESA', enabled: true, row_version: 1, usos: 5 },
  { id: 'tania', nombre: 'Tania', naturaleza: 'PERSONA', enabled: true, row_version: 1, usos: 9 },
  { id: 'repsol', nombre: 'Repsol', naturaleza: 'EMPRESA', enabled: true, row_version: 1, usos: 7 },
  { id: 'ayto', nombre: 'Ayuntamiento', naturaleza: 'ORGANISMO', enabled: true, row_version: 1, usos: 1 },
  { id: 'otro', nombre: 'Asociación X', naturaleza: 'OTRO', enabled: true, row_version: 1, usos: 1 },
  { id: 'nulo', nombre: 'Sin tipo', naturaleza: null, enabled: true, row_version: 1, usos: 1 },
  { id: 'vieja', nombre: 'Empresa Vieja', naturaleza: 'EMPRESA', enabled: false, row_version: 2, usos: 3 },
];

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

function respuestaReembolsable(pl: PayloadGastoReembolsable) {
  return {
    tipo: 'OK', datos: {
      intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false, importe: pl.importe, moneda: 'EUR', estado_atribucion: 'COMPLETA',
      tu_parte: pl.importe, movimiento: { movimiento_id: 'mov-1', cuenta_id: pl.cuenta_id, importe: `-${pl.importe}` },
      posiciones: [{ entidad_id: 'der-1', tipo: 'DERECHO_COBRO', contraparte_tercero_id: pl.reembolso.tercero_id, nombre: 'Pendiente de cobro · Combustible',
        importe: pl.reembolso.importe, saldo: pl.reembolso.importe, estado: 'ACTIVA', apertura_indeterminada: false }],
      aviso: '',
    },
  } as const;
}

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: any) => ({ tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado } }) as any),
    registrarGastoReembolsable: jest.fn(async (p: PayloadGastoReembolsable) => respuestaReembolsable(p) as any),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [
      { cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
      { cuenta_id: NOMINA, nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
    ] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: TERCEROS } }) as any),
    altaTercero: jest.fn(async (c: any) => ({ tipo: 'OK', datos: { tercero: { id: c.id, nombre: c.nombre, naturaleza: c.naturaleza, enabled: true, row_version: 1 } } }) as any),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: [{ cuenta_id: NOMINA, nombre: 'Cuenta nómina', moneda: 'EUR' }, { cuenta_id: 'efectivo', nombre: 'Efectivo', moneda: 'EUR' }] } }) as any),
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
const marcado = (id: string) => screen.getByTestId(id).props.accessibilityState?.checked;
const deshabilitado = (id: string) => screen.getByTestId(id).props.accessibilityState?.disabled;

// ================================================================== dominio
describe('C-03 · dominio', () => {
  const r = (o: Partial<typeof REEMBOLSO_VACIO> = {}) => ({ ...REEMBOLSO_VACIO, terceroId: 'empresa', nombre: 'Empresa SL', ...o });

  test('importe recuperable: «Todo» = total; «Otra cantidad» de 0,01 € al total; sin valor por defecto', () => {
    expect(importeReembolso('60.00', REEMBOLSO_VACIO)).toBeNull();
    expect(importeReembolso('60.00', r({ modo: 'TODO' }))).toBe('60.00');
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '40' }))).toBe('40.00');
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '0,01' }))).toBe('0.01');
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '60' }))).toBe('60.00');
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '60,01' }))).toBeNull();
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '0' }))).toBeNull();
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '1,234' }))).toBeNull();
    expect(importeReembolso('60.00', r({ modo: 'OTRA', importeTexto: '' }))).toBeNull();
  });

  test('lo que falta: quién y cuánto; nunca el comercio del gasto', () => {
    expect(faltaReembolso('60.00', REEMBOLSO_VACIO, null)).toEqual(['quién te lo debe', 'cuánto te deben']);
    expect(faltaReembolso('60.00', r({ modo: 'TODO' }), null)).toEqual([]);
    expect(faltaReembolso('60.00', r({ modo: 'TODO' }), 'empresa')).toEqual(['quien te lo debe, que no puede ser el comercio del gasto']);
    expect(faltaReembolso('60.00', r({ modo: 'OTRA', importeTexto: '70' }), null)).toEqual(['una cantidad entre 0,01 € y 60,00 €']);
  });

  test('sellado: el payload del gasto pagado sin `atribucion` y con `reembolso`; `validar` lo exige', () => {
    const b = {
      ...borradorInicial(HOY), importeTexto: '60', presupuestable: true, cuentaId: TARJETA, cuentaOrigen: 'USUARIO' as const, propuesta: 'SELF_100' as const,
      categoria: { estado: 'SIN_CATEGORIA' as const }, terceroId: 'repsol', contextoId: 'ctx-1', concepto: 'Gasolina', soloMio: true,
      reembolso: r({ modo: 'OTRA', importeTexto: '40' }),
    };
    expect(validar(b, HOY)).toEqual({});
    const s = sellarReembolsable(b, 'id-1');
    expect(s.reembolsable).toBe(true);
    expect(s.payload).toEqual({
      intencion_id: 'id-1', concepto: 'Gasolina', importe: '60.00', moneda: 'EUR', fecha_hecho: HOY, cuenta_id: TARJETA, presupuestable: true,
      financiacion: { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe: '60.00' },
      categoria: { estado: 'SIN_CATEGORIA' }, tercero_id: 'repsol', contexto_id: 'ctx-1', reembolso: { tercero_id: 'empresa', importe: '40.00' },
    });
    expect('atribucion' in s.payload).toBe(false);
    // Lo que te deben deja de valer si el total baja o el comercio pasa a ser quien te lo debe.
    expect(validar({ ...b, importeTexto: '30' }, HOY).reembolso).toMatch(/una cantidad entre 0,01 € y 30,00 €/);
    expect(validar({ ...b, terceroId: 'empresa' }, HOY).reembolso).toMatch(/no puede ser el comercio/);
    expect(() => sellarReembolsable({ ...b, reembolso: REEMBOLSO_VACIO }, 'id-2')).toThrow();
    // Ingreso: el reembolso no aplica.
    expect(validar(b, HOY, 'INGRESO').reembolso).toBeUndefined();
  });

  test('tras el cobro: «Saldado» solo si extingue el saldo conocido; parcial con lo que queda; nunca «Saldado» indeterminado', () => {
    expect(textoTrasCobro({ saldo: '0.00', estado: 'CERRADA' })).toBe('Saldado · no cuenta como ingreso');
    expect(textoTrasCobro({ saldo: '20.00', estado: 'ACTIVA' })).toBe('Cobro registrado · quedan 20,00 €');
    expect(textoTrasCobro({ saldo: null, estado: 'ACTIVA' })).toBe('Cobro registrado');
    expect(textoTrasCobro({ saldo: null, estado: 'CERRADA' })).toBe('Cobro registrado');
  });

  test('derecho de un gasto reembolsable: lo reconoce el nombre que fija el servidor', () => {
    expect(esDerechoReembolso({ tipo: 'DERECHO_COBRO', nombre: 'Pendiente de cobro · Combustible' })).toBe(true);
    expect(esDerechoReembolso({ tipo: 'DERECHO_COBRO', nombre: 'Pendiente de cobro' })).toBe(true);
    expect(esDerechoReembolso({ tipo: 'DERECHO_COBRO', nombre: 'Gasto compartido' })).toBe(false);
    expect(esDerechoReembolso({ tipo: 'OBLIGACION_PAGO', nombre: 'Pendiente de cobro' })).toBe(false);
    expect(esDerechoReembolso({ tipo: 'DERECHO_COBRO', nombre: 'Pendiente de cobrar la fianza' })).toBe(false);
  });
});

// ================================================================== C1–C3
async function formulario(c: ClienteApi, tipo?: 'INGRESO', forzar?: 'dark') {
  envolver(<RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} tipo={tipo} onGastoCompartido={jest.fn()} />, forzar);
  await screen.findByTestId(tipo ? 'cuenta-efectivo' : `cuenta-${TARJETA}`);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '60');
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId('cat-mov'));
  await act(async () => fireEvent.press(screen.getByTestId('cat-comb')));
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  fireEvent.press(screen.getByTestId(tipo ? 'cuenta-efectivo' : `cuenta-${TARJETA}`));
}

async function elegirQuien(nombre: string) {
  fireEvent.press(screen.getByTestId('reembolso-quien'));
  await screen.findByTestId('selector-persona');
  await act(async () => fireEvent.press(await screen.findByLabelText(nombre)));
}

async function completarReembolso(nombre = 'Empresa SL', otra?: string) {
  fireEvent.press(screen.getByTestId('reembolsable'));
  await screen.findByTestId('reembolso');
  await elegirQuien(nombre);
  if (otra) {
    fireEvent.press(screen.getByTestId('reembolso-otra'));
    fireEvent.changeText(screen.getByTestId('reembolso-importe'), otra);
  } else fireEvent.press(screen.getByTestId('reembolso-todo'));
  fireEvent.press(screen.getByTestId('reembolso-hecho'));
}

describe('C-03 · C1–C3 en el registro', () => {
  test('C1: «Mío, pero me lo reembolsan» es una respuesta más de «¿De quién?» en gastos; no en ingresos', async () => {
    await formulario(cliente());
    expect(screen.getByTestId('reembolsable')).toBeTruthy();
    expect(screen.getByText('Mío, pero me lo reembolsan')).toBeTruthy();
    expect(marcado('reembolsable')).toBe(false);
    expect(screen.getByTestId('solo-mio')).toBeTruthy();
    expect(screen.getByTestId('repartir')).toBeTruthy();
    expect(screen.getByTestId('origen-atribucion').props.children).toMatch(/^Sin indicar/);
    screen.unmount();
    envolver(<RegistroGastoScreen cliente={cliente()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} tipo="INGRESO" onGastoCompartido={jest.fn()} />);
    await screen.findByTestId('cuenta-efectivo');
    expect(screen.queryByTestId('reembolsable')).toBeNull();
  });

  test('C2: nada marcado; «Hecho» deshabilitado hasta elegir quién y cuánto; textos fijos y sin previsión', async () => {
    await formulario(cliente());
    fireEvent.press(screen.getByTestId('reembolsable'));
    await screen.findByTestId('reembolso');
    expect(screen.getByText('Quién te lo debe')).toBeTruthy();
    expect(screen.getByText('Cuánto te deben')).toBeTruthy();
    expect(screen.getByTestId('reembolso-quien-valor').props.children).toBe('Elige persona o empresa');
    expect(marcado('reembolso-todo')).toBe(false);
    expect(marcado('reembolso-otra')).toBe(false);
    expect(screen.getByText('Todo · 60,00 €')).toBeTruthy();
    expect(screen.getByText(TEXTO_COMO_SE_REGISTRA('60.00'))).toBeTruthy();
    expect(screen.getByTestId('reembolso-sin-prevision').props.children).toBe(TEXTO_SIN_PREVISION);
    expect(deshabilitado('reembolso-hecho')).toBe(true);
    expect(screen.getByTestId('reembolso-faltan').props.children).toBe('Falta: quién te lo debe y cuánto te deben.');
    await elegirQuien('Empresa SL');
    expect(deshabilitado('reembolso-hecho')).toBe(true);
    fireEvent.press(screen.getByTestId('reembolso-otra'));
    fireEvent.changeText(screen.getByTestId('reembolso-importe'), '70');
    expect(deshabilitado('reembolso-hecho')).toBe(true);
    expect(screen.getByTestId('reembolso-faltan').props.children).toBe('Falta: una cantidad entre 0,01 € y 60,00 €.');
    fireEvent.changeText(screen.getByTestId('reembolso-importe'), '40');
    expect(deshabilitado('reembolso-hecho')).toBeFalsy();
    expect(screen.queryByTestId('reembolso-faltan')).toBeNull();
  });

  test('C2: el selector ofrece personas y empresas activas; nunca el comercio, ORGANISMO, OTRO ni sin naturaleza', async () => {
    const c = cliente();
    await formulario(c);
    // Comercio del gasto: Repsol.
    await act(async () => fireEvent.press(screen.getByTestId('campo-tercero')));
    await act(async () => fireEvent.press(await screen.findByTestId('tercero-repsol')));
    fireEvent.press(screen.getByTestId('reembolsable'));
    fireEvent.press(await screen.findByTestId('reembolso-quien'));
    await screen.findByTestId('selector-persona');
    expect(await screen.findByLabelText('Empresa SL')).toBeTruthy();
    expect(screen.getByLabelText('Tania')).toBeTruthy();
    for (const x of ['Repsol', 'Ayuntamiento', 'Asociación X', 'Sin tipo', 'Empresa Vieja']) expect(screen.queryByLabelText(x)).toBeNull();
    expect(screen.getByText('Solo personas y empresas. Nunca el comercio de este gasto.')).toBeTruthy();
    expect(within(screen.getByTestId('persona-empresa')).getByText('Empresa · 5 registros')).toBeTruthy();
    expect(within(screen.getByTestId('persona-tania')).getByText('Persona · 9 registros')).toBeTruthy();
  });

  test('C2: alta de una empresa nueva desde «Quién te lo debe»', async () => {
    const c = cliente();
    await formulario(c);
    fireEvent.press(screen.getByTestId('reembolsable'));
    fireEvent.press(await screen.findByTestId('reembolso-quien'));
    await screen.findByTestId('selector-persona');
    fireEvent.changeText(screen.getByTestId('selector-persona-buscar'), 'Mi Empresa Nueva');
    expect(screen.getByTestId('selector-persona-crear')).toBeTruthy();
    await act(async () => fireEvent.press(screen.getByTestId('selector-persona-crear-empresa')));
    expect((c.altaTercero as jest.Mock).mock.calls[0][0]).toMatchObject({ nombre: 'Mi Empresa Nueva', naturaleza: 'EMPRESA' });
    expect(screen.getByTestId('reembolso-quien-valor').props.children).toBe('Mi Empresa Nueva');
  });

  test('C2→C3: vuelve al formulario con el resumen y se registra por la ruta C-03; éxito con el gasto y lo que te deben por separado', async () => {
    const c = cliente();
    await formulario(c);
    await completarReembolso('Empresa SL', '40');
    expect(screen.queryByTestId('reembolso')).toBeNull();
    expect(marcado('reembolsable')).toBe(true);
    expect(marcado('solo-mio')).toBe(false);
    expect(screen.getByTestId('reembolso-resumen')).toBeTruthy();
    expect(screen.getByText('Te debe Empresa SL · 40,00 €')).toBeTruthy();
    expect(screen.getByTestId('origen-atribucion').props.children).toBe('Decisión tuya: el gasto es 100 % tuyo y Empresa SL te lo debe.');
    expect(screen.queryByTestId('repartir')).toBeNull();
    expect(screen.queryByTestId('otra-persona')).toBeNull();
    await act(async () => fireEvent.press(screen.getByTestId('registrar')));
    await screen.findByTestId('registro-exito');
    expect(c.registrarGastoPagado).not.toHaveBeenCalled();
    const pl = (c.registrarGastoReembolsable as jest.Mock).mock.calls[0][0];
    expect(pl).toMatchObject({ importe: '60.00', cuenta_id: TARJETA, presupuestable: false, categoria: { estado: 'CATEGORIA', categoria_id: 'comb', magnitudes: [] },
      reembolso: { tercero_id: 'empresa', importe: '40.00' } });
    expect('atribucion' in pl).toBe(false);
    expect(within(screen.getByTestId('exito-resultado')).getByText('Cuenta en tu Resultado')).toBeTruthy();
    expect(within(screen.getByTestId('exito-resultado')).getByText('60,00 €')).toBeTruthy();
    expect(within(screen.getByTestId('exito-te-debe-der-1')).getByText('Te debe Empresa SL')).toBeTruthy();
    expect(within(screen.getByTestId('exito-te-debe-der-1')).getByText('40,00 €')).toBeTruthy();
    expect(screen.queryByText('Atribuido: solo tuyo.')).toBeNull();
  });

  test('reabrir, «Quitar» y «Solo mío»: sin reembolso el gasto va por la ruta del gasto pagado', async () => {
    const c = cliente();
    await formulario(c);
    await completarReembolso();
    fireEvent.press(screen.getByTestId('reembolso-resumen'));
    expect(await screen.findByTestId('reembolso')).toBeTruthy();
    expect(marcado('reembolso-todo')).toBe(true);
    expect(screen.getByTestId('reembolso-quien-valor').props.children).toBe('Empresa SL');
    fireEvent.press(screen.getByTestId('reembolso-atras'));
    fireEvent.press(screen.getByTestId('reembolso-quitar'));
    expect(screen.queryByTestId('reembolso-resumen')).toBeNull();
    expect(marcado('reembolsable')).toBe(false);
    await completarReembolso();
    fireEvent.press(screen.getByTestId('solo-mio'));
    expect(marcado('solo-mio')).toBe(true);
    expect(screen.queryByTestId('reembolso-resumen')).toBeNull();
    await act(async () => fireEvent.press(screen.getByTestId('registrar')));
    await screen.findByTestId('registro-exito');
    expect(c.registrarGastoReembolsable).not.toHaveBeenCalled();
    expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0].atribucion).toBe('SOLO_MIO');
  });

  test('si el comercio pasa a ser quien te lo debe, se dice y no se registra', async () => {
    const c = cliente();
    await formulario(c);
    await completarReembolso('Empresa SL');
    await act(async () => fireEvent.press(screen.getByTestId('campo-tercero')));
    await act(async () => fireEvent.press(await screen.findByTestId('tercero-empresa')));
    expect(screen.getByTestId('reembolso-error').props.children).toMatch(/no puede ser el comercio del gasto/);
    expect(screen.getByTestId('registrar')).toBeDisabled();
    expect(screen.getByTestId('faltan').props.children).toMatch(/revisar lo que te deben/);
  });

  test.each([
    ['CONTRAPARTE_ES_COMERCIO', 'Quien te lo debe no puede ser el mismo comercio del gasto.'],
    ['NATURALEZA_NO_ADMITIDA_EN_REEMBOLSO', 'Quien te lo debe tiene que ser una persona o una empresa.'],
    ['TERCERO_NO_DISPONIBLE', 'Quien te lo debe o el comercio ya no está disponible. Elige otro.'],
    ['REEMBOLSO_EXCEDE_TOTAL', 'Lo que te deben no puede ser más que el total del gasto.'],
  ])('rechazo %s: en lenguaje llano y el formulario se conserva', async (codigo, texto) => {
    const c = cliente({ registrarGastoReembolsable: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo, mensaje: 'texto técnico' })) as any });
    await formulario(c);
    await completarReembolso();
    await act(async () => fireEvent.press(screen.getByTestId('registrar')));
    expect(await screen.findByText(`No se ha registrado. ${texto}`)).toBeTruthy();
    expect(screen.getByTestId('reembolso-resumen')).toBeTruthy();
  });

  test('D1: C2 en oscuro, ya completado', async () => {
    await formulario(cliente(), undefined, 'dark');
    await completarReembolso();
    fireEvent.press(screen.getByTestId('reembolso-resumen'));
    await screen.findByTestId('reembolso');
    expect(plano()).toContain(colores.dark.background);
    expect(deshabilitado('reembolso-hecho')).toBeFalsy();
  });
});

// ================================================================== C4 y detalle
const DERECHO = (id: string, saldo: string | null, fecha: string) => ({
  entidad_id: id, entidad_row_version: 1, tipo: 'DERECHO_COBRO' as const, nombre: 'Pendiente de cobro · Combustible', saldo, estado: 'ACTIVA' as const,
  apertura_indeterminada: false, origen_hecho_id: `h-${id}`, origen_fecha: fecha, origen_concepto: null, origen_tercero: 'Repsol',
});
const EMPRESA: PendienteConPersona = {
  tercero_id: 'empresa', nombre: 'Empresa SL', te_debe: '100.00', le_debes: null, neto: '100.00', neto_estado: 'DETERMINADO',
  posiciones: [DERECHO('der-1', '60.00', '2026-10-20'), DERECHO('der-2', '40.00', '2026-10-24')],
};
const resultadoCobro = (id: string, pl: any, saldo: string) =>
  ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: 'hc', entidad_id: id, idempotente: false, importe: pl.importe, saldo, estado: saldo === '0.00' ? 'CERRADA' : 'ACTIVA', apertura_indeterminada: false, aviso: '' } }) as any;

describe('C-03 · C4 «Pendiente con…»', () => {
  async function abrir(c: ClienteApi, entidadId: string | null) {
    envolver(<PendienteConScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} terceroId="empresa" nombre="Empresa SL" entidadId={entidadId} onCerrar={jest.fn()} />);
    await screen.findByTestId(entidadId ? 'posicion-acciones' : 'pendiente-lista-te-debe');
  }

  test('dos derechos con la misma empresa: se abre el elegido y el cobro va solo a ese; «Registrar cobro» espera a la cuenta', async () => {
    const cobrar = jest.fn(async (id: string, pl: any) => resultadoCobro(id, pl, '0.00'));
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: EMPRESA }) as any), cobrarPosicion: cobrar as any });
    await abrir(c, 'der-2');
    expect(screen.getByText('Empresa SL te debe 40,00 €')).toBeTruthy();
    fireEvent.press(screen.getByTestId('posicion-cobrar'));
    await screen.findByTestId('accion-cobro');
    expect(screen.getByTestId('accion-origen').props.children).toBe('Empresa SL · Pendiente de cobro · Combustible · te debe 40,00 €');
    expect(screen.getByTestId('accion-explicacion').props.children).toBe(TEXTO_COBRO_NO_INGRESO);
    expect(screen.getByTestId('accion-importe').props.value).toBe('40,00');
    await screen.findByTestId(`accion-cuenta-${NOMINA}`);
    expect(marcado(`accion-cuenta-${NOMINA}`)).toBe(false);
    expect(screen.getByTestId('accion-enviar')).toBeDisabled();
    fireEvent.press(screen.getByTestId(`accion-cuenta-${NOMINA}`));
    expect(screen.getByTestId('accion-enviar')).toBeEnabled();
    await act(async () => fireEvent.press(screen.getByTestId('accion-enviar')));
    expect(cobrar).toHaveBeenCalledTimes(1);
    expect(cobrar.mock.calls[0][0]).toBe('der-2');
    expect(cobrar.mock.calls[0][1]).toMatchObject({ importe: '40.00', cuenta_id: NOMINA, fecha: HOY });
    expect(screen.getByTestId('posicion-exito-titulo').props.children).toBe('Saldado · no cuenta como ingreso');
  });

  test('cobro parcial: «Cobro registrado · quedan X €», nunca «Saldado»', async () => {
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: EMPRESA }) as any),
      cobrarPosicion: jest.fn(async (id: string, pl: any) => resultadoCobro(id, pl, '20.00')) as any });
    await abrir(c, 'der-1');
    expect(screen.getByText('Empresa SL te debe 60,00 €')).toBeTruthy();
    fireEvent.press(screen.getByTestId('posicion-cobrar'));
    fireEvent.changeText(await screen.findByTestId('accion-importe'), '40');
    fireEvent.press(await screen.findByTestId('accion-cuenta-efectivo'));
    await act(async () => fireEvent.press(screen.getByTestId('accion-enviar')));
    expect(screen.getByTestId('posicion-exito-titulo').props.children).toBe('Cobro registrado · quedan 20,00 €');
    expect(plano()).not.toMatch(/Saldado/);
  });

  test('sin `entidadId` se ve la lista (comportamiento previo); un id que ya no está activo no abre nada', async () => {
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: EMPRESA }) as any) });
    await abrir(c, null);
    expect(screen.getByTestId('posicion-der-1')).toBeTruthy();
    expect(screen.getByTestId('posicion-der-2')).toBeTruthy();
    screen.unmount();
    envolver(<PendienteConScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} terceroId="empresa" nombre="Empresa SL" entidadId="der-9" onCerrar={jest.fn()} />);
    expect(await screen.findByTestId('pendiente-lista-te-debe')).toBeTruthy();
    expect(screen.queryByTestId('posicion-acciones')).toBeNull();
  });
});

describe('C-03 · detalle del gasto y devolución', () => {
  const FILA: FilaActividad = {
    id: 'gasto', fecha_hecho: '2026-10-24', tipo: 'GASTO', nota: null, moneda: 'EUR', importe_total: '60.00',
    tercero: { id: 'repsol', nombre: 'Repsol', enabled: true }, categoria: { id: 'comb', nombre: 'Combustible', ruta: 'Movilidad › Combustible', enabled: true }, varias: false,
    contexto: null, cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '60.00',
    pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
  };
  const REPARTO: RepartoDeHecho = {
    hecho_id: 'gasto', row_version: 1, importe: '60.00', estado_atribucion: 'COMPLETA', corregible: false, motivo: 'SIN_REPARTO',
    partes: [{ atribucion_id: 'a-yo', tercero_id: null, nombre: 'Tú', importe: '60.00', posicion: null } as any],
    posiciones_vinculadas: [
      { entidad_id: 'der-1', contraparte_tercero_id: 'empresa', contraparte_nombre: 'Empresa SL', tipo: 'DERECHO_COBRO', saldo: '60.00', estado: 'ACTIVA', apertura_indeterminada: false },
      { entidad_id: 'der-0', contraparte_tercero_id: 'empresa', contraparte_nombre: 'Empresa SL', tipo: 'DERECHO_COBRO', saldo: '0.00', estado: 'CERRADA', apertura_indeterminada: false },
    ],
  };

  test('«Pendiente con Empresa SL» sale de `posiciones_vinculadas` (sin parte inventada) y pasa el `entidad_id`', async () => {
    const onPendiente = jest.fn();
    const c = cliente({
      actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [FILA], siguiente: null, total: 1 } }) as any),
      detalleActividad: jest.fn(async () => ({ tipo: 'OK', datos: { ...FILA, presupuestable: true, magnitudes: [], devoluciones: null } as DetalleActividad }) as any),
      repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: REPARTO }) as any),
    });
    envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onCorregirReparto={jest.fn()} onPendienteCon={onPendiente} />);
    fireEvent.press(await screen.findByTestId('fila-gasto'));
    fireEvent.press(await screen.findByTestId('detalle-vinculada-der-1'));
    expect(onPendiente).toHaveBeenCalledWith({ terceroId: 'empresa', nombre: 'Empresa SL', entidadId: 'der-1' });
    fireEvent.press(await screen.findByTestId('fila-gasto'));
    await screen.findByTestId('detalle-vinculada-der-1');
    expect(screen.queryByTestId('detalle-vinculada-der-0')).toBeNull(); // la saldada no se ofrece
    expect(screen.queryByTestId('detalle-corregir-reparto')).toBeNull();
    expect(screen.getAllByText('Pendiente con Empresa SL')).toHaveLength(1); // no se duplica
  });

  test('devolución bloqueada en un gasto con derecho de cobro: motivo comprensible', () => {
    expect(motivoNoDisponible('GASTO_CON_DERECHO_DE_COBRO')).toMatch(/pendiente de cobro/);
    expect(motivoNoDisponible('GASTO_CON_DERECHO_DE_COBRO')).not.toBe(motivoNoDisponible(null));
  });
});
