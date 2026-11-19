// ============================================================
// GAPTO MOBILE 2027
// Fichero: compra_timeout_comprobacion.test.tsx
// Ruta: mobile/__tests__/compra_timeout_comprobacion.test.tsx
// Descripción: MANT N1 R-B2-06 (AJ-01): la compra con hipoteca larga puede tardar más que el timeout general (validación G2 de 0354 al COMMIT, ≈ 35 ms por cuota). (1) `enviarCompraComprobando`: ante un INDETERMINADO reenvía la MISMA petición y devuelve el resultado real; (2) `registrarCompra` usa `TIMEOUT_COMPRA_MS` y el resto de llamadas, el general; (3) CompraScreen: un timeout NO muestra «No se ha podido confirmar…», comprueba con el MISMO cuerpo (misma intención) y llega a «Compra guardada»; si nunca se confirma, `TEXTO_COMPRA_SIN_CONFIRMAR`.
// Versión: 0.1.0 (F06 T3-F06 · MANT N1 R-B2-06 (AJ-01), firma b88a3662…)
// ============================================================
import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import { crearClientePatrimonio, TIMEOUT_COMPRA_MS } from '../src/api/patrimonio';
import type { ClientePatrimonio, ParteEnFecha, ResultadoCompra } from '../src/api/patrimonio';
import type { VistaPropiedad } from '../src/api/propiedades';
import {
  COMPROBACIONES_COMPRA, enviarCompraComprobando, TEXTO_COMPRA_SIN_CONFIRMAR, TEXTO_COMPROBANDO_COMPRA, TEXTO_INDETERMINADO_COMPRA,
} from '../src/domain/compra';
import { CompraScreen } from '../src/screens/CompraScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const ANA = 'a0000000-0000-4000-8000-0000000000a1';
const C1 = 'c0000000-0000-4000-8000-0000000000c1';
const C2 = 'c0000000-0000-4000-8000-0000000000c2';
const AHORA = () => new Date(2026, 9, 10, 10);
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const INDET = { tipo: 'INDETERMINADO', mensaje: 'x' } as Respuesta<ResultadoCompra>;
const PARTES: ParteEnFecha[] = [
  { actor_id: ANA, porcentaje: '40.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana' },
  { actor_id: YO, porcentaje: '60.0000', yo: true, tercero_id: null, nombre: null },
];

function vista(p: Partial<VistaPropiedad> = {}): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: '2026-10-10',
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
      { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '60.0000' },
      { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '40.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  } as VistaPropiedad;
}

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const cliente = () => ({ cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [{ cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' },
  { cuenta_id: C2, nombre: 'Cuenta Común', moneda: 'EUR' }] })) }) as unknown as ClienteApi;
const OK_COMPRA = ok({ propiedad: vista({ row_version: 2 }), idempotente: true, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1.00',
  liquidez_atribuible: '-1.00', gasto_del_mes: '0.00', atribucion: null } }) as Respuesta<ResultadoCompra>;

/** Patrimonio con cola de respuestas para la compra (después de la cola: OK idempotente). */
function patrimonio(cola: Respuesta<ResultadoCompra>[]) {
  const enviados: any[] = [];
  const api: ClientePatrimonio = {
    registrarCompra: jest.fn(async (_id, p) => { enviados.push(p); return cola.length ? cola.shift()! : OK_COMPRA; }),
    gastoCompraPosterior: jest.fn(async () => OK_COMPRA),
    leerCoste: jest.fn(async () => ok({ coste: null as any })),
    titularidadEnFecha: jest.fn(async (_id, fecha) => ok({ fecha, partes: fecha >= '2026-03-20' ? PARTES : [] })),
  };
  return { api, enviados };
}

function montar(pat: ReturnType<typeof patrimonio>) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CompraScreen cliente={cliente()} patrimonio={pat.api} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

async function hastaB4() {
  await escribir('compra-precio', '1000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${C1}`));
  await pulsar(`compra-pago-0-cuenta-${C1}`);
  await escribir('compra-pago-0-importe', '1000');
  await pulsar('compra-continuar');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  await pulsar('compra-atr-titularidad');
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-paso-resumen')).toBeTruthy();
}

describe('enviarCompraComprobando (R-B2-06)', () => {
  test('INDETERMINADO y después OK: devuelve OK, reenvía la MISMA petición y avisa de que comprueba', async () => {
    const enviar = jest.fn().mockResolvedValueOnce({ tipo: 'INDETERMINADO' }).mockResolvedValueOnce({ tipo: 'OK', datos: 1 });
    const alComprobar = jest.fn();
    const { respuesta, comprobaciones } = await enviarCompraComprobando(enviar, alComprobar);
    expect(respuesta).toEqual({ tipo: 'OK', datos: 1 });
    expect(enviar).toHaveBeenCalledTimes(2);
    expect(alComprobar).toHaveBeenCalledTimes(1);
    expect(comprobaciones).toBe(1);
  });

  test('siempre INDETERMINADO: hace COMPROBACIONES_COMPRA reenvíos y devuelve el INDETERMINADO, sin más intentos', async () => {
    const enviar = jest.fn(async () => ({ tipo: 'INDETERMINADO' }));
    const { respuesta, comprobaciones } = await enviarCompraComprobando(enviar);
    expect(respuesta.tipo).toBe('INDETERMINADO');
    expect(enviar).toHaveBeenCalledTimes(1 + COMPROBACIONES_COMPRA);
    expect(comprobaciones).toBe(COMPROBACIONES_COMPRA);
    expect(COMPROBACIONES_COMPRA).toBeGreaterThanOrEqual(1);
  });

  test('un RECHAZADO es definitivo: no se reenvía', async () => {
    const enviar = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA' }));
    const { respuesta } = await enviarCompraComprobando(enviar);
    expect(respuesta).toEqual({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA' });
    expect(enviar).toHaveBeenCalledTimes(1);
  });
});

describe('timeout propio de la compra (R-B2-06)', () => {
  afterEach(() => jest.useRealTimers());

  function fetchColgado() {
    const señales: AbortSignal[] = [];
    const f = jest.fn((_url: string, init: RequestInit) => new Promise((_res, rej) => {
      señales.push(init.signal as AbortSignal);
      (init.signal as AbortSignal).addEventListener('abort', () => rej(new Error('abort')));
    }));
    return { f: f as unknown as typeof fetch, señales };
  }

  test('registrarCompra no se corta a los 10 s y sí a TIMEOUT_COMPRA_MS; el resto conserva el general', async () => {
    jest.useFakeTimers();
    const { f, señales } = fetchColgado();
    const api = crearClientePatrimonio({ baseUrl: 'http://x', token: 't', timeoutMs: 10000 } as any, f);
    const compra = api.registrarCompra('p1', {} as any);
    const coste = api.leerCoste('p1');
    await act(async () => { jest.advanceTimersByTime(10001); });
    expect(señales[0].aborted).toBe(false);      // compra: sigue esperando
    expect(señales[1].aborted).toBe(true);       // lectura: timeout general
    await act(async () => { jest.advanceTimersByTime(TIMEOUT_COMPRA_MS - 10001); });
    expect(señales[0].aborted).toBe(true);
    expect((await compra).tipo).toBe('INDETERMINADO');
    expect((await coste).tipo).toBe('INDETERMINADO');
    expect(TIMEOUT_COMPRA_MS).toBeGreaterThanOrEqual(30000);
  });
});

describe('CompraScreen ante un timeout (R-B2-06)', () => {
  test('timeout y la comprobación confirma: «Compra guardada», sin falso aviso de fallo y con el MISMO cuerpo', async () => {
    const pat = patrimonio([INDET]);
    montar(pat);
    await hastaB4();
    await pulsar('compra-guardar');
    await waitFor(() => screen.getByTestId('compra-hecho'));
    expect(screen.queryByText(TEXTO_INDETERMINADO_COMPRA)).toBeNull();
    expect(pat.enviados).toHaveLength(2);
    expect(pat.enviados[1]).toEqual(pat.enviados[0]);                      // misma intención y mismo contenido: replay idempotente
    expect(pat.enviados[1].intencion_id).toBe(pat.enviados[0].intencion_id);
  });

  test('timeout persistente: muestra que aún no se puede confirmar, nunca «No se ha podido confirmar… repetirla»', async () => {
    const pat = patrimonio([INDET, INDET, INDET, INDET]);
    montar(pat);
    await hastaB4();
    await pulsar('compra-guardar');
    await waitFor(() => screen.getByText(TEXTO_COMPRA_SIN_CONFIRMAR));
    expect(screen.queryByText(TEXTO_INDETERMINADO_COMPRA)).toBeNull();
    expect(screen.queryByText(TEXTO_COMPROBANDO_COMPRA)).toBeNull();
    expect(screen.queryByTestId('compra-hecho')).toBeNull();
    expect(pat.enviados).toHaveLength(1 + COMPROBACIONES_COMPRA);
    expect(new Set(pat.enviados.map((x) => x.intencion_id)).size).toBe(1);
  });
});
