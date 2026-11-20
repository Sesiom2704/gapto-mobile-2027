// ============================================================
// GAPTO MOBILE 2027
// Fichero: revision_timeout_comprobacion.test.tsx
// Ruta: mobile/__tests__/revision_timeout_comprobacion.test.tsx
// Descripción: MANT N1 de revisión del tipo (A3/A4; dictamen MANT R-B2-06 punto 3 y AJ-03; decisión 14). La revisión del tipo de una hipoteca larga puede tardar más que el timeout general (validación G2 de 0354 al COMMIT). (1) `enviarRevisionComprobando`: ante un INDETERMINADO reenvía la MISMA petición y devuelve el resultado real; un RECHAZADO es definitivo; (2) `revisarTipoHipoteca` usa `TIMEOUT_REVISION_MS` y el resto de llamadas, el general; (3) RevisarTipoScreen: un timeout NO muestra «No se ha podido confirmar…», comprueba con el MISMO cuerpo (misma intención) y pinta la hipoteca devuelta; si nunca se confirma, `TEXTO_REVISION_SIN_CONFIRMAR` y no se da por revisada.
// Versión: 0.1.0 (F06 T3 · MANT N1 de revisión del tipo, A4)
// ============================================================
import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { crearCliente, TIMEOUT_REVISION_MS } from '../src/api/cliente';
import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ResultadoHipoteca } from '../src/api/hipoteca';
import {
  COMPROBACIONES_REVISION, enviarRevisionComprobando, TEXTO_COMPROBANDO_REVISION, TEXTO_INDETERMINADO, TEXTO_REVISION_SIN_CONFIRMAR,
} from '../src/domain/hipoteca';
import { RevisarTipoScreen } from '../src/screens/RevisarTipoScreen';
import { ProveedorTema } from '../src/theme/tema';
import { FID, hipoteca } from './hipoteca_fixtures';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const INDET = { tipo: 'INDETERMINADO', mensaje: 'x' } as Respuesta<ResultadoHipoteca>;
const OK_REV = ok({ idempotente: true, hipoteca: hipoteca({ cuota_vigente: '1010.00' }) }) as Respuesta<ResultadoHipoteca>;
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));

/** Cliente con cola de respuestas para la revisión (después de la cola: OK idempotente). */
function clienteRev(cola: Respuesta<ResultadoHipoteca>[]) {
  const enviados: any[] = [];
  const api = {
    revisarTipoHipoteca: jest.fn(async (_id: string, p: any) => { enviados.push(p); return cola.length ? cola.shift()! : OK_REV; }),
  } as unknown as ClienteApi;
  return { api, enviados };
}

function montar(cli: ClienteApi, onRevisada = jest.fn(), onRecargar = jest.fn()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <RevisarTipoScreen cliente={cli} hipoteca={hipoteca()} hoyIso="2026-10-10" nuevoId={nuevoId} onCancelar={jest.fn()}
          onRevisada={onRevisada} onRecargar={onRecargar} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { onRevisada, onRecargar };
}

async function rellenarYConfirmar() {
  await escribir('hip-rev-desde', '01/07/2026');
  await escribir('hip-rev-tasa', '2,95');
  await pulsar('hip-rev-confirmar');
}

describe('enviarRevisionComprobando (MANT de revisión del tipo)', () => {
  test('INDETERMINADO y después OK: devuelve OK, reenvía la MISMA petición y avisa de que comprueba', async () => {
    const enviar = jest.fn().mockResolvedValueOnce({ tipo: 'INDETERMINADO' }).mockResolvedValueOnce({ tipo: 'OK', datos: 1 });
    const alComprobar = jest.fn();
    const { respuesta, comprobaciones } = await enviarRevisionComprobando(enviar, alComprobar);
    expect(respuesta).toEqual({ tipo: 'OK', datos: 1 });
    expect(enviar).toHaveBeenCalledTimes(2);
    expect(alComprobar).toHaveBeenCalledTimes(1);
    expect(comprobaciones).toBe(1);
  });

  test('siempre INDETERMINADO: hace COMPROBACIONES_REVISION (2) reenvíos y devuelve el INDETERMINADO, sin más intentos', async () => {
    const enviar = jest.fn(async () => ({ tipo: 'INDETERMINADO' }));
    const { respuesta, comprobaciones } = await enviarRevisionComprobando(enviar);
    expect(respuesta.tipo).toBe('INDETERMINADO');
    expect(COMPROBACIONES_REVISION).toBe(2);
    expect(enviar).toHaveBeenCalledTimes(1 + COMPROBACIONES_REVISION);
    expect(comprobaciones).toBe(COMPROBACIONES_REVISION);
  });

  test('un RECHAZADO es definitivo: no se reenvía', async () => {
    const enviar = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'REVISION_SOBRE_CUOTA_PAGADA' }));
    const { respuesta } = await enviarRevisionComprobando(enviar);
    expect(respuesta).toEqual({ tipo: 'RECHAZADO', codigo: 'REVISION_SOBRE_CUOTA_PAGADA' });
    expect(enviar).toHaveBeenCalledTimes(1);
  });
});

describe('timeout propio de la revisión', () => {
  afterEach(() => jest.useRealTimers());

  function fetchColgado() {
    const señales: AbortSignal[] = [];
    const f = jest.fn((_url: string, init: RequestInit) => new Promise((_res, rej) => {
      señales.push(init.signal as AbortSignal);
      (init.signal as AbortSignal).addEventListener('abort', () => rej(new Error('abort')));
    }));
    return { f: f as unknown as typeof fetch, señales };
  }

  test('revisarTipoHipoteca no se corta a los 10 s y sí a TIMEOUT_REVISION_MS; el pago de la cuota conserva el general', async () => {
    jest.useFakeTimers();
    const { f, señales } = fetchColgado();
    const api = crearCliente({ baseUrl: 'http://x', token: 't', timeoutMs: 10000 } as any, f);
    const rev = api.revisarTipoHipoteca!(FID, {} as any);
    const pago = api.pagarCuotaHipoteca!(FID, 1, {} as any);
    await act(async () => { jest.advanceTimersByTime(10001); });
    expect(señales[0].aborted).toBe(false);      // revisión: sigue esperando
    expect(señales[1].aborted).toBe(true);       // pago: timeout general
    await act(async () => { jest.advanceTimersByTime(TIMEOUT_REVISION_MS - 10001); });
    expect(señales[0].aborted).toBe(true);
    expect((await rev).tipo).toBe('INDETERMINADO');
    expect((await pago).tipo).toBe('INDETERMINADO');
    expect(TIMEOUT_REVISION_MS).toBeGreaterThan(10000);
  });
});

describe('RevisarTipoScreen ante un timeout', () => {
  test('timeout y la comprobación confirma: pinta la hipoteca devuelta, sin falso aviso de fallo y con el MISMO cuerpo', async () => {
    const c = clienteRev([INDET]);
    const { onRevisada } = montar(c.api);
    await rellenarYConfirmar();
    await waitFor(() => expect(onRevisada).toHaveBeenCalledTimes(1));
    expect(onRevisada.mock.calls[0][0].cuota_vigente).toBe('1010.00');
    expect(screen.queryByText(TEXTO_INDETERMINADO)).toBeNull();
    expect(c.enviados).toHaveLength(2);
    expect(c.enviados[1]).toEqual(c.enviados[0]);                          // misma intención y mismo contenido: replay idempotente
    expect(c.enviados[1].intencion_id).toBe(c.enviados[0].intencion_id);
  });

  test('timeout persistente: muestra que aún no se puede confirmar, nunca «No se ha podido confirmar… repetir», y no da la revisión por hecha', async () => {
    const c = clienteRev([INDET, INDET, INDET, INDET]);
    const { onRevisada, onRecargar } = montar(c.api);
    await rellenarYConfirmar();
    await waitFor(() => screen.getByText(TEXTO_REVISION_SIN_CONFIRMAR));
    expect(screen.queryByText(TEXTO_INDETERMINADO)).toBeNull();
    expect(screen.queryByText(TEXTO_COMPROBANDO_REVISION)).toBeNull();
    expect(onRevisada).not.toHaveBeenCalled();
    expect(onRecargar).not.toHaveBeenCalled();
    expect(c.enviados).toHaveLength(1 + COMPROBACIONES_REVISION);
    expect(new Set(c.enviados.map((x) => x.intencion_id)).size).toBe(1);
    expect(c.enviados.every((x) => JSON.stringify(x) === JSON.stringify(c.enviados[0]))).toBe(true);
  });

  test('mientras comprueba muestra «Comprobando…»', async () => {
    let soltar: (r: Respuesta<ResultadoHipoteca>) => void = () => undefined;
    const enviados: any[] = [];
    const api = {
      revisarTipoHipoteca: jest.fn((_id: string, p: any) => {
        enviados.push(p);
        return enviados.length === 1 ? Promise.resolve(INDET) : new Promise<Respuesta<ResultadoHipoteca>>((res) => { soltar = res; });
      }),
    } as unknown as ClienteApi;
    const { onRevisada } = montar(api);
    await rellenarYConfirmar();
    await waitFor(() => screen.getByText(TEXTO_COMPROBANDO_REVISION));
    await act(async () => soltar(OK_REV));
    await waitFor(() => expect(onRevisada).toHaveBeenCalledTimes(1));
  });
});
