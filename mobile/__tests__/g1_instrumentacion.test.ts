// ============================================================
// GAPTO MOBILE 2027
// Fichero: g1_instrumentacion.test.ts
// Ruta: mobile/__tests__/g1_instrumentacion.test.ts
// Descripción: F05-07 G1 (F05-D050 §64.1). La instrumentación de la medición (src/dev/g1.ts) no tiene efecto fuera de `__DEV__` (ni log ni estado, también a través del cliente HTTP) y en desarrollo escribe UNA línea `[G1] {json}` por ensayo: confirmado (2xx), error (no 2xx o sin respuesta) y abandonado; el `intencion_id` del cuerpo y el `hecho_id` de la respuesta viajan en la línea (correlación con la auditoría del servidor). Solo las confirmaciones POST /v1/intenciones/* cierran un ensayo.
// Versión: 0.1.0 (F05-07 G1, preparación de la medición; tirada nocturna, paso 3)
// Versión: 0.2.0 (ídem): la línea transporta el `hecho_id` de la respuesta.
// Versión: 0.3.0 (ídem): el cierre se prueba a través de `g1Fetch` (el cliente HTTP no cambia).
// Versión: 0.4.0 (F05-D051 paso 9.1 · G1 v2): la línea es `v: 2` con `sesion` y `pasos`. Fuera de `__DEV__`, `g1Paso`/`g1Cambio`/`g1Traza` no guardan nada aunque haya un ensayo abierto y `g1Suscribir` no se suscribe. En `__DEV__`: hitos en orden con ms relativos al `t0` del MISMO reloj monotónico, en la línea de su ensayo (también la del abandonado) y nunca en la del siguiente; primer y último cambio sin valor; tope de pasos; teclado y AppState como hitos.
// ============================================================

import { crearCliente } from '../src/api/cliente';
import { G1_MAX_PASOS, G1Fuentes, g1Abrir, g1Cambio, g1Cerrar, g1Estado, g1Fetch, g1Paso, g1Reiniciar, g1Suscribir, g1Traza } from '../src/dev/g1';

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
    expect(g1Estado()).toEqual({ secuencia: 0, abierto: false, pasos: 0 });
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
      expect(g1Estado()).toEqual({ secuencia: 0, abierto: false, pasos: 0 });
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
    expect(l).toMatchObject({ v: 2, seq: 1, origen: 'inicio:plantilla', ruta: '/v1/intenciones/gasto-pagado', status: 200,
      ok: true, intencion_id: ID, hecho_id: HECHO, resultado: 'CONFIRMADO' });
    expect(typeof l.ms).toBe('number');
    expect(l.ms as number).toBeGreaterThanOrEqual(0);
    expect(g1Estado()).toEqual({ secuencia: 1, abierto: false, pasos: 0 });
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

// ------------------------------------------------------------------ G1 v2: instrumentación por paso (F05-D051 9.1)
function reloj(...valores: number[]): jest.SpyInstance {
  const s = jest.spyOn(performance, 'now');
  for (const v of valores) s.mockReturnValueOnce(v);
  return s;
}

function fuentesFalsas() {
  const oyentes: Record<string, (x?: string) => void> = {};
  const quitados: string[] = [];
  const fuentes: G1Fuentes = {
    Keyboard: { addListener: jest.fn((e: string, f: () => void) => { oyentes[e] = f; return { remove: () => quitados.push(e) }; }) },
    AppState: { addEventListener: jest.fn((e: string, f: (x: string) => void) => { oyentes[e] = f as (x?: string) => void; return { remove: () => quitados.push(e) }; }) },
  };
  return { fuentes, oyentes, quitados };
}

describe('G1 v2 fuera de __DEV__', () => {
  afterEach(() => jest.restoreAllMocks());

  it('g1Paso, g1Cambio y g1Traza no guardan nada aunque haya un ensayo abierto', () => {
    const log = jest.fn();
    g1Abrir('inicio:registrar', true, log);
    g1Paso('form_montado', undefined, false);
    g1Cambio('importe', false);
    g1Traza('categoria_elegida', { via: 'arbol', n: 2 }, false);
    g1Traza('cambio:magnitud', undefined, false);
    expect(g1Estado().pasos).toBe(0);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    expect(lineas(log)[0].pasos).toEqual([]);
  });

  it('g1Suscribir no se suscribe a teclado ni a AppState', () => {
    const { fuentes } = fuentesFalsas();
    const baja = g1Suscribir(fuentes, false);
    expect(fuentes.Keyboard.addListener).not.toHaveBeenCalled();
    expect(fuentes.AppState.addEventListener).not.toHaveBeenCalled();
    expect(() => baja()).not.toThrow();
  });

  it('con __DEV__ falso global: flujo completo sin ninguna línea ni estado', async () => {
    const global_ = globalThis as unknown as { __DEV__: boolean };
    const antes = global_.__DEV__;
    const log = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    try {
      global_.__DEV__ = false;
      g1Abrir('inicio:registrar');
      g1Paso('form_montado');
      g1Traza('cambio:importe');
      g1Traza('registrar_pulsado');
      const { fuentes, oyentes } = fuentesFalsas();
      g1Suscribir(fuentes);
      expect(oyentes).toEqual({});
      const cli = crearCliente({ baseUrl: 'http://x', token: 't', timeoutMs: 1000 }, g1Fetch(fetchFalso(200, { hecho_id: HECHO })));
      await cli.registrarGastoPagado({ intencion_id: ID } as never);
      expect(log).not.toHaveBeenCalled();
      expect(g1Estado()).toEqual({ secuencia: 0, abierto: false, pasos: 0 });
    } finally {
      global_.__DEV__ = antes;
    }
  });
});

describe('G1 v2 en __DEV__', () => {
  afterEach(() => jest.restoreAllMocks());

  it('los hitos viajan en orden en la línea del ensayo, con ms relativos al t0 del mismo reloj, sesion y seq', () => {
    const log = jest.fn();
    reloj(1000, 1250, 1300.04, 4000, 9000);
    g1Abrir('inicio:registrar', true, log);
    g1Paso('form_montado', { via: 'GASTO' }, true);
    g1Paso('categoria_elegida', { via: 'arbol', n: 2 }, true);
    g1Paso('registrar_pulsado', undefined, true);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    const [l] = lineas(log);
    expect(l).toMatchObject({ v: 2, seq: 1, origen: 'inicio:registrar', resultado: 'CONFIRMADO', hecho_id: HECHO, ms: 8000 });
    expect(typeof l.sesion).toBe('number');
    expect(l.pasos).toEqual([
      { e: 'form_montado', ms: 250, via: 'GASTO' },
      { e: 'categoria_elegida', ms: 300, via: 'arbol', n: 2 },
      { e: 'registrar_pulsado', ms: 3000 },
    ]);
    expect(l).not.toHaveProperty('pasos_omitidos');
  });

  it('cada ensayo lleva solo sus pasos: el abandonado los conserva y el siguiente empieza vacío (misma sesion, seq siguiente)', () => {
    const log = jest.fn();
    g1Abrir('inicio:registrar', true, log);
    g1Paso('hoja_tipos', undefined, true);
    g1Paso('tipo:TRANSFERENCIA', undefined, true);
    g1Abrir('inicio:registrar', true, log); // abandona el primero
    g1Paso('tipo:GASTO', undefined, true);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    const [a, b] = lineas(log);
    expect([a.seq, a.resultado, (a.pasos as { e: string }[]).map((x) => x.e)]).toEqual([1, 'ABANDONADO', ['hoja_tipos', 'tipo:TRANSFERENCIA']]);
    expect([b.seq, b.resultado, (b.pasos as { e: string }[]).map((x) => x.e)]).toEqual([2, 'CONFIRMADO', ['tipo:GASTO']]);
    expect(a.sesion).toBe(b.sesion);
  });

  it('sin ensayo abierto un hito no se guarda ni pasa al ensayo siguiente', () => {
    const log = jest.fn();
    g1Paso('form_montado', undefined, true);
    g1Abrir('inicio:registrar', true, log);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    g1Paso('teclado_off', undefined, true);
    expect(lineas(log)[0].pasos).toEqual([]);
  });

  it('g1Cambio / g1Traza(cambio:…): primer cambio y UN último cambio al final; nunca el valor', () => {
    const log = jest.fn();
    reloj(0, 10, 20, 30, 40, 50, 60);
    g1Abrir('inicio:registrar', true, log);
    g1Traza('cambio:importe', undefined, true);
    g1Traza('cambio:importe', undefined, true);
    g1Paso('selector_abierto', undefined, true);
    g1Cambio('importe', true);
    g1Traza('cambio:magnitud', undefined, true);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    expect(lineas(log)[0].pasos).toEqual([
      { e: 'importe_1er_cambio', ms: 10 },
      { e: 'selector_abierto', ms: 30 },
      { e: 'importe_ult_cambio', ms: 40 },
      { e: 'magnitud_1er_cambio', ms: 50 },
    ]);
  });

  it('tope de pasos por ensayo: los que sobran se cuentan en pasos_omitidos', () => {
    const log = jest.fn();
    g1Abrir('inicio:registrar', true, log);
    for (let i = 0; i < G1_MAX_PASOS + 5; i += 1) g1Paso('scroll_ini', undefined, true);
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    const [l] = lineas(log);
    expect((l.pasos as unknown[]).length).toBe(G1_MAX_PASOS);
    expect(l.pasos_omitidos).toBe(5);
  });

  it('g1Suscribir: teclado y AppState son hitos del ensayo abierto; la baja quita las tres suscripciones', () => {
    const log = jest.fn();
    const { fuentes, oyentes, quitados } = fuentesFalsas();
    const baja = g1Suscribir(fuentes, true);
    oyentes.keyboardDidShow(); // sin ensayo: nada
    g1Abrir('inicio:registrar', true, log);
    oyentes.keyboardDidShow();
    oyentes.change('background');
    oyentes.change('active');
    oyentes.keyboardDidHide();
    g1Cerrar('/v1/intenciones/gasto-pagado', 200, ID, HECHO, true, log);
    expect((lineas(log)[0].pasos as { e: string }[]).map((x) => x.e)).toEqual(['teclado_on', 'app_estado:background', 'app_estado:active', 'teclado_off']);
    baja();
    expect([...quitados].sort()).toEqual(['change', 'keyboardDidHide', 'keyboardDidShow']);
  });
});
