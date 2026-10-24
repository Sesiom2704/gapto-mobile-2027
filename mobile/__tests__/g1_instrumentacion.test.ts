// ============================================================
// GAPTO MOBILE 2027
// Fichero: g1_instrumentacion.test.ts
// Ruta: mobile/__tests__/g1_instrumentacion.test.ts
// Descripción: F05-07 G1 (F05-D050 §64.1). La instrumentación de la medición (src/dev/g1.ts) no tiene efecto fuera de `__DEV__` (ni log ni estado, también a través del cliente HTTP) y en desarrollo escribe UNA línea `[G1] {json}` por ensayo: confirmado (2xx), error (no 2xx o sin respuesta) y abandonado; el `intencion_id` del cuerpo y el `hecho_id` de la respuesta viajan en la línea (correlación con la auditoría del servidor). Solo las confirmaciones POST /v1/intenciones/* cierran un ensayo.
// Versión: 0.1.0 (F05-07 G1, preparación de la medición; tirada nocturna, paso 3)
// Versión: 0.2.0 (ídem): la línea transporta el `hecho_id` de la respuesta.
// Versión: 0.3.0 (ídem): el cierre se prueba a través de `g1Fetch` (el cliente HTTP no cambia).
// ============================================================

import { crearCliente } from '../src/api/cliente';
import { g1Abrir, g1Cerrar, g1Estado, g1Fetch, g1Reiniciar } from '../src/dev/g1';

const ID = '11111111-1111-4111-8111-111111111111';
const HECHO = '22222222-2222-4222-8222-222222222222';

function lineas(log: jest.Mock): Record<string, unknown>[] {
  return log.mock.calls.map(([l]) => {
    expect(String(l).startsWith('[G1] ')).toBe(true);
    return JSON.parse(String(l).slice(5));
  });
}

function fetchFalso(status: number, cuerpo: unknown): typeof fetch {
  const r = { ok: status >= 200 && status < 300, status, json: async () => cuerpo, clone: () => r };
  return jest.fn(async () => r) as unknown as typeof fetch;
}

beforeEach(() => g1Reiniciar());

describe('fuera de __DEV__ (producción)', () => {
  it('no escribe ni guarda estado', () => {
    const log = jest.fn();
    g1Abrir('inicio:registrar', false, log);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, ID, false, log);
    expect(log).not.toHaveBeenCalled();
    expect(g1Estado()).toEqual({ secuencia: 0, abierto: false });
  });

  it('a través del cliente HTTP tampoco escribe nada', async () => {
    const global_ = globalThis as unknown as { __DEV__: boolean };
    const antes = global_.__DEV__;
    const log = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    try {
      global_.__DEV__ = false;
      g1Abrir('inicio:registrar');
      const base = fetchFalso(200, { hecho_id: ID });
      expect(g1Fetch(base)).toBe(base); // fuera de __DEV__, el fetch sin envolver
      const cli = crearCliente({ baseUrl: 'http://x', token: 't', timeoutMs: 1000 }, g1Fetch(base));
      await cli.registrarGastoPagado({ intencion_id: ID } as never);
      expect(log).not.toHaveBeenCalled();
      expect(g1Estado()).toEqual({ secuencia: 0, abierto: false });
    } finally {
      global_.__DEV__ = antes;
      log.mockRestore();
    }
  });
});

describe('en __DEV__', () => {
  it('un ensayo confirmado: una línea con secuencia, origen, ruta, 2xx, intencion_id y ms', () => {
    const log = jest.fn();
    g1Abrir('inicio:plantilla', true, log);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    const [l] = lineas(log);
    expect(l).toMatchObject({ v: 1, seq: 1, origen: 'inicio:plantilla', ruta: '/v1/intenciones/gasto-pagado', status: 200,
      ok: true, intencion_id: ID, hecho_id: HECHO, resultado: 'CONFIRMADO' });
    expect(typeof l.ms).toBe('number');
    expect(l.ms as number).toBeGreaterThanOrEqual(0);
    expect(g1Estado()).toEqual({ secuencia: 1, abierto: false });
  });

  it('los errores se registran (no 2xx y sin respuesta) y cierran el ensayo', () => {
    const log = jest.fn();
    g1Abrir('inicio:registrar', true, log);
    g1Cerrar('/v1/intenciones/gasto-pagado', 409, ID, null, true, log);
    g1Abrir('inicio:registrar', true, log);
    g1Cerrar('/v1/intenciones/transferencia', null, ID, null, true, log);
    expect(lineas(log).map((l) => [l.seq, l.status, l.ok, l.resultado])).toEqual([
      [1, 409, false, 'ERROR'],
      [2, null, false, 'ERROR'],
    ]);
  });

  it('un flujo abandonado se registra al abrir el siguiente; sin ensayo abierto no se escribe nada', () => {
    const log = jest.fn();
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, null, true, log);
    g1Abrir('inicio:registrar', true, log);
    g1Abrir('inicio:plantilla', true, log);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, null, true, log);
    expect(lineas(log).map((l) => [l.seq, l.origen, l.resultado])).toEqual([
      [1, 'inicio:registrar', 'ABANDONADO'],
      [2, 'inicio:plantilla', 'CONFIRMADO'],
    ]);
  });

  it('el cliente (con g1Fetch) cierra el ensayo solo con POST /v1/intenciones/* y transporta intencion_id y hecho_id', async () => {
    const log = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    try {
      g1Abrir('inicio:registrar');
      const cli = crearCliente({ baseUrl: 'http://x', token: 't', timeoutMs: 1000 }, g1Fetch(fetchFalso(200, { hecho_id: HECHO })));
      await cli.arbolCategorias();
      expect(log).not.toHaveBeenCalled();
      await cli.registrarIngresoCobrado({ intencion_id: ID } as never);
      expect(log).toHaveBeenCalledTimes(1);
      expect(JSON.parse(String(log.mock.calls[0][0]).slice(5))).toMatchObject({
        ruta: '/v1/intenciones/ingreso-cobrado', status: 200, ok: true, intencion_id: ID, hecho_id: HECHO });
    } finally {
      log.mockRestore();
    }
  });
});
