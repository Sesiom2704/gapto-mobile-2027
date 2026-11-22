// ============================================================
// GAPTO MOBILE 2027
// Fichero: aj05_cabeceras.test.ts
// Ruta: mobile/__tests__/aj05_cabeceras.test.ts
// Descripción: AJ-05 ampliado + R-C7-07 (mandato b4ff6b70… §4; diseño v0.2 §7): `crearLlamada` añade `X-Gapto-Intento-Id` (nuevo por intento HTTP) y, en escrituras, `X-Gapto-Intencion-Id` tomado del cuerpo; conserva `Authorization` y `Content-Type`; el reenvío lleva el mismo cuerpo y la misma intención con otro intento; 5xx (también RESULTADO_NO_CONFIRMADO y TIEMPO_AGOTADO) sigue siendo INDETERMINADO.
// Versión: 0.1.0 (F06 T4 · AJ-05, Fase 3)
// ============================================================

import { crearLlamada, intencionDelCuerpo, uuidIntento } from '../src/api/cliente';

const CFG = { baseUrl: 'http://api', token: 'tok', timeoutMs: 1000 };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function doble(status = 200, cuerpo: unknown = { ok: true }) {
  const llamadas: { url: string; init: RequestInit & { headers: Record<string, string> } }[] = [];
  const f = jest.fn(async (url: string, init: RequestInit) => {
    llamadas.push({ url, init: init as RequestInit & { headers: Record<string, string> } });
    return { ok: status >= 200 && status < 300, status, json: async () => cuerpo } as Response;
  });
  return { f: f as unknown as typeof fetch, llamadas };
}

test('escritura: intento nuevo, intención del cuerpo, Authorization y Content-Type intactos', async () => {
  const { f, llamadas } = doble();
  let n = 0;
  const llamar = crearLlamada(CFG, f, () => `intento-${++n}`);
  const cuerpo = JSON.stringify({ intencion_id: '11111111-1111-4111-8111-111111111111', importe: '1.00' });
  await llamar('/v1/x', { method: 'POST', body: cuerpo }, true);
  await llamar('/v1/x', { method: 'POST', body: cuerpo }, 'CAMBIO');   // reenvío: mismo cuerpo, misma intención
  expect(llamadas).toHaveLength(2);
  for (const l of llamadas) {
    expect(l.init.headers.Authorization).toBe('Bearer tok');
    expect(l.init.headers['Content-Type']).toBe('application/json');
    expect(l.init.headers['X-Gapto-Intencion-Id']).toBe('11111111-1111-4111-8111-111111111111');
    expect(l.init.body).toBe(cuerpo);
  }
  expect(llamadas.map((l) => l.init.headers['X-Gapto-Intento-Id'])).toEqual(['intento-1', 'intento-2']);
});

test('lectura: lleva intento pero nunca intención', async () => {
  const { f, llamadas } = doble();
  await crearLlamada(CFG, f)('/v1/y?fecha=2026-11-22', { method: 'GET' }, false);
  expect(llamadas[0].init.headers['X-Gapto-Intento-Id']).toMatch(UUID);
  expect(llamadas[0].init.headers).not.toHaveProperty('X-Gapto-Intencion-Id');
});

test('escritura sin intencion_id en el cuerpo (o cuerpo no JSON): sin cabecera de intención', async () => {
  const { f, llamadas } = doble();
  const llamar = crearLlamada(CFG, f);
  await llamar('/v1/z', { method: 'POST', body: JSON.stringify({ nombre: 'x' }) }, true);
  await llamar('/v1/z', { method: 'POST', body: 'no es json' }, true);
  expect(llamadas.every((l) => !('X-Gapto-Intencion-Id' in l.init.headers))).toBe(true);
  expect(intencionDelCuerpo(JSON.stringify({ intencion_id: 7 }))).toBeNull();
  expect(intencionDelCuerpo(undefined)).toBeNull();
});

test.each([
  [503, { codigo: 'RESULTADO_NO_CONFIRMADO', mensaje: 'x', reintentable: true }],
  [503, { codigo: 'TIEMPO_AGOTADO', mensaje: 'x', reintentable: true }],
  [503, { codigo: 'BACKEND_NO_DISPONIBLE', mensaje: 'x', reintentable: true }],
  [500, { codigo: 'INTERNO', mensaje: 'x', reintentable: false }],
])('5xx sigue siendo INDETERMINADO (%s %o)', async (status, cuerpo) => {
  const { f } = doble(status, cuerpo);
  const r = await crearLlamada(CFG, f)('/v1/x', { method: 'POST', body: '{"intencion_id":"a"}' }, true);
  expect(r.tipo).toBe('INDETERMINADO');
});

test('uuidIntento: UUID v4 canónico, distinto en cada llamada (también sin crypto.randomUUID)', () => {
  const original = (globalThis as { crypto?: unknown }).crypto;
  try {
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true, writable: true });
    const a = uuidIntento();
    const b = uuidIntento();
    expect(a).toMatch(UUID);
    expect(b).toMatch(UUID);
    expect(a).not.toBe(b);
  } finally {
    Object.defineProperty(globalThis, 'crypto', { value: original, configurable: true, writable: true });
  }
});
