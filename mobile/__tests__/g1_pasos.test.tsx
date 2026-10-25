// ============================================================
// GAPTO MOBILE 2027
// Fichero: g1_pasos.test.tsx
// Ruta: mobile/__tests__/g1_pasos.test.tsx
// Descripción: F05-D051 paso 9.1 (G1 v2): instrumentación por paso a través de la app real (Raiz). En `__DEV__`, el caso 5 de G1 (Registrar · Gasto · importe · Coche › Gasolina · Litros · Presupuesto · Cuenta · Registrar) deja en la línea [G1] de su ensayo los hitos en orden, con la vía y los niveles de la categoría, sin valores tecleados, y su D1 observado es 5 (el del guion); un chip de «Sugeridas» se traza con vía `chip` y una búsqueda con vía `busqueda`; la transferencia traza sus dos cuentas. Fuera de `__DEV__` la app no llama a la traza ni escribe ninguna línea, y el registro sigue funcionando igual.
// Versión: 0.1.0 (F05-D051 paso 9.1 · G1 v2, instrumentación por paso)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import * as g1 from '../src/dev/g1';
import { g1Cerrar, g1Estado, g1Reiniciar } from '../src/dev/g1';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, mag, nodo } from './fixtures_categorias';

const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const NOMINA = 'c0000000-0000-4000-8000-00000000000b';
const AHORRO = 'c0000000-0000-4000-8000-00000000000c';
const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';
const ID = '11111111-1111-4111-8111-111111111111';
const HECHO = '22222222-2222-4222-8222-222222222222';

const ARBOL = [
  nodo({ id: 'alim', nombre: 'Alimentación' }),
  nodo({ id: 'super', nombre: 'Supermercado', parent_id: 'alim' }),
  nodo({ id: 'coche', nombre: 'Coche', orden: 1 }),
  nodo({ id: 'gasolina', nombre: 'Gasolina', parent_id: 'coche', magnitudes: [mag({ magnitud_id: 'litros', nombre: 'Litros', unidad_default: 'l' })] }),
];

const okGasto = (p: PayloadGastoPagado): Respuesta<ResultadoRegistro> => ({
  tipo: 'OK',
  datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'NO_DISPONIBLE', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado },
});

function fake(sugerida = false): ClienteApi {
  const base = clienteCategoriasStub(ARBOL);
  return {
    ...base,
    registrarGastoPagado: jest.fn(async (p: PayloadGastoPagado) => okGasto(p)),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasElegibles: jest.fn(async (operacion: any) => ({ tipo: 'OK', datos: { operacion, cuentas: [{ cuenta_id: NOMINA, nombre: 'Cuenta nómina', moneda: 'EUR' }, { cuenta_id: AHORRO, nombre: 'Ahorro', moneda: 'EUR' }] } }) as any),
    registrarTransferencia: jest.fn(async (p: any) => ({ tipo: 'OK', datos: { intencion_id: p.intencion_id, hecho_id: 'h2', idempotente: false, tipo: 'TRANSFERENCIA', importe: p.importe, moneda: 'EUR', estado_atribucion: null, estado_categorial: null } })) as any,
    senalesCategorias: jest.fn(async (q: any) => ({
      tipo: 'OK',
      datos: { tipo: q.tipo, fecha: q.fecha, tercero_id: null, candidatas: sugerida ? [{ categoria_id: 'super', nombre: 'Supermercado', ruta: 'Alimentación › Supermercado', motivo: 'FRECUENTE_TIPO', fuente: 'HISTORIAL', usos: 1, ultimo_uso: HOY }] : [] },
    })) as any,
  };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

type Paso = { e: string; ms: number; via?: string; n?: number };

/** Cierra el ensayo abierto (el cliente falso no pasa por g1Fetch) y devuelve su línea [G1]. */
function cerrarYLeer(): { linea: string; datos: Record<string, unknown>; pasos: Paso[] } {
  const log = jest.fn();
  g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
  expect(log).toHaveBeenCalledTimes(1);
  const linea = String(log.mock.calls[0][0]);
  expect(linea.startsWith('[G1] ')).toBe(true);
  const datos = JSON.parse(linea.slice(5));
  return { linea, datos, pasos: datos.pasos as Paso[] };
}

/** D1 observado con la regla del parser (scripts/dev/g1_tramos.py). */
const DECISIONES = ['tercero_elegido', 'tercero_ninguno', 'selector_nivel', 'categoria_elegida', 'presupuesto_elegido', 'cuenta_elegida', 'cuenta_desde_elegida', 'cuenta_a_elegida'];
const d1 = (origen: unknown, pasos: Paso[]) => (origen === 'inicio:plantilla' ? 1 : 0) + pasos.filter((p) => p.e.startsWith('tipo:') || DECISIONES.includes(p.e)).length;

async function montar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await screen.findByTestId('accion-registrar');
  await act(async () => undefined);
}

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

async function escribir(id: string, texto: string) {
  await act(async () => fireEvent.changeText(screen.getByTestId(id), texto));
}

let consola: jest.SpyInstance;
beforeEach(() => {
  n = 0;
  g1Reiniciar();
  consola = jest.spyOn(console, 'log').mockImplementation(() => undefined);
});
afterEach(() => {
  consola.mockRestore();
  g1Reiniciar();
});

test('caso 5 en __DEV__: hitos en orden en la línea del ensayo, vía y niveles de la categoría, sin valores y D1 observado = 5', async () => {
  await montar(fake());
  await pulsar('accion-registrar');
  await pulsar('tipo-GASTO');
  await screen.findByTestId(`cuenta-${TARJETA}`);
  await escribir('campo-importe', '12');
  await escribir('campo-importe', '12,34');
  await pulsar('campo-categoria');
  await pulsar('cat-coche');
  await pulsar('cat-gasolina');
  await escribir('magnitud-litros', '41,5');
  await pulsar('presupuestable-true');
  await pulsar(`cuenta-${TARJETA}`);
  await pulsar('registrar');
  await screen.findByTestId('registro-exito');
  expect(g1Estado().abierto).toBe(true);

  const { linea, datos, pasos } = cerrarYLeer();
  expect(datos).toMatchObject({ v: 2, seq: 1, origen: 'inicio:registrar', resultado: 'CONFIRMADO', hecho_id: HECHO });
  const hitos = pasos.map((p) => p.e).filter((e) => !e.startsWith('faltan:') && !['arbol_ok', 'cuentas_ok', 'sugeridas_ok', 'propuesta_aplicada'].includes(e));
  expect(hitos).toEqual([
    'hoja_tipos', 'tipo:GASTO', 'form_montado',
    'importe_1er_cambio', 'importe_ult_cambio',
    'selector_abierto', 'selector_nivel', 'categoria_elegida', 'magnitudes_visibles',
    'magnitud_1er_cambio', 'presupuesto_elegido', 'cuenta_elegida', 'registrar_pulsado',
  ]);
  for (const e of ['arbol_ok', 'cuentas_ok', 'sugeridas_ok', 'propuesta_aplicada']) expect(pasos.map((p) => p.e)).toContain(e);
  expect(pasos.find((p) => p.e === 'selector_nivel')).toMatchObject({ n: 1 });
  expect(pasos.find((p) => p.e === 'categoria_elegida')).toMatchObject({ via: 'arbol', n: 2 });
  expect(pasos.find((p) => p.e === 'magnitudes_visibles')).toMatchObject({ n: 1 });
  expect(pasos.find((p) => p.e === 'cuentas_ok')).toMatchObject({ n: 1 });
  // «faltan» solo con claves, y la última antes de Registrar es el conjunto vacío.
  const faltan = pasos.filter((p) => p.e.startsWith('faltan:')).map((p) => p.e);
  expect(faltan[0]).toMatch(/^faltan:[a-z,]+$/);
  expect(faltan[faltan.length - 1]).toBe('faltan:');
  // Reloj del ensayo: ms no decrecientes desde su t0.
  const ms = pasos.map((p) => p.ms);
  expect(ms).toEqual([...ms].sort((a, b) => a - b));
  expect(ms[0]).toBeGreaterThanOrEqual(0);
  // Nunca valores tecleados ni nombres.
  expect(linea).not.toMatch(/12,34|12\.34|41,5|41\.5|Gasolina|Coche|Tarjeta/);
  expect(d1(datos.origen, pasos)).toBe(5);
});

test('chip de «Sugeridas»: vía chip; búsqueda en el selector: vía busqueda; cerrar el selector se traza', async () => {
  await montar(fake(true));
  await pulsar('accion-registrar');
  await pulsar('tipo-GASTO');
  await screen.findByTestId('chip-sugerida-super');
  await pulsar('chip-sugerida-super');
  await pulsar('campo-categoria');
  await escribir('selector-busqueda', 'g');
  await escribir('selector-busqueda', 'gas');
  await pulsar('resultado-gasolina');
  await pulsar('campo-categoria');
  await pulsar('selector-cerrar');
  const { pasos } = cerrarYLeer();
  const cat = pasos.filter((p) => ['categoria_elegida', 'selector_busqueda', 'selector_abierto', 'selector_cerrado'].includes(p.e));
  expect(cat.map((p) => [p.e, p.via ?? null])).toEqual([
    ['categoria_elegida', 'chip'],
    ['selector_abierto', null],
    ['selector_busqueda', null],
    ['categoria_elegida', 'busqueda'],
    ['selector_abierto', null],
    ['selector_cerrado', null],
  ]);
});

test('transferencia: tipo, cuentas desde y a, importe y Registrar; D1 observado = 3', async () => {
  await montar(fake());
  await pulsar('accion-registrar');
  await pulsar('tipo-TRANSFERENCIA');
  await screen.findByTestId(`desde-${NOMINA}`);
  await escribir('campo-importe', '100');
  await pulsar(`desde-${NOMINA}`);
  await pulsar(`a-${AHORRO}`);
  await pulsar('registrar');
  const { datos, pasos } = cerrarYLeer();
  expect(pasos.map((p) => p.e)).toEqual([
    'hoja_tipos', 'tipo:TRANSFERENCIA', 'form_montado', 'cuentas_ok', 'importe_1er_cambio', 'cuenta_desde_elegida', 'cuenta_a_elegida', 'registrar_pulsado',
  ]);
  expect(d1(datos.origen, pasos)).toBe(3);
});

test('fuera de __DEV__: la app no llama a la traza ni escribe línea [G1]; el registro funciona igual', async () => {
  const global_ = globalThis as unknown as { __DEV__: boolean };
  const antes = global_.__DEV__;
  const traza = jest.spyOn(g1, 'g1Traza');
  const paso = jest.spyOn(g1, 'g1Paso');
  global_.__DEV__ = false;
  try {
    const cliente = fake();
    await montar(cliente);
    await pulsar('accion-registrar');
    await pulsar('tipo-GASTO');
    await screen.findByTestId(`cuenta-${TARJETA}`);
    await escribir('campo-importe', '12,34');
    await pulsar('campo-categoria');
    await pulsar('cat-coche');
    await pulsar('cat-gasolina');
    await escribir('magnitud-litros', '41,5');
    await pulsar('presupuestable-true');
    await pulsar(`cuenta-${TARJETA}`);
    await pulsar('registrar');
    await screen.findByTestId('registro-exito');
    expect(cliente.registrarGastoPagado).toHaveBeenCalledTimes(1);
    expect(traza).not.toHaveBeenCalled();
    expect(paso).not.toHaveBeenCalled();
    expect(g1Estado()).toEqual({ secuencia: 0, abierto: false, pasos: 0 });
  } finally {
    global_.__DEV__ = antes;
    traza.mockRestore();
    paso.mockRestore();
  }
  expect(consola.mock.calls.filter(([l]) => String(l).startsWith('[G1]'))).toEqual([]);
});
