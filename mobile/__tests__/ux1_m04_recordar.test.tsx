// ============================================================
// GAPTO MOBILE 2027
// Fichero: ux1_m04_recordar.test.tsx
// Ruta: mobile/__tests__/ux1_m04_recordar.test.tsx
// Descripción: M-04 «¿Recordarlo para la próxima vez?» (T1-F06 UX-1, TR1-05): solo cambia la VISIBILIDAD. Oráculos:
//   O-M04-01 con las mismas casillas la escritura sale idéntica a la de 180cb1f (mismo método, ruta y cuerpo de
//   altaPreferencia y editarPreferencia, por el cliente real con un fetch falso); O-M04-02 preferencia guardada con
//   los mismos valores → «Recordado» y no se pregunta; con un valor distinto → se pregunta como hoy; O-M04-03 sin
//   lista (error o excepción) → se pregunta como hoy, y nunca se escribe sin pulsar (tampoco al montar).
// Versión: 0.1.0 (F06 T1 UX-1 · M-04)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { crearCliente, type ClienteApi, type Preferencia } from '../src/api/cliente';
import { GuardarPreferencia } from '../src/components/GuardarPreferencia';
import { casillasIniciales, yaRecordado } from '../src/domain/preferencias';
import { ProveedorTema } from '../src/theme/tema';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const TIPOS = { GASTO: 't-gasto', INGRESO: 't-ingreso' };
const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const CUENTAS = [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA' }];
const ID_ALTA = '00000000-0000-4000-8000-0000000000a1';
const FINALES = { cuenta: TARJETA, presupuestable: true };

const pref = (x: Partial<Preferencia>): Preferencia => ({
  id: 'p-super', enabled: true, row_version: 4, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null,
  cuenta_default_id: null, presupuestable_default: null, prioridad: 100, ...x,
});

type Peticion = { url: string; metodo: string; cuerpo: unknown };
/** Cliente REAL (crearCliente) con un fetch falso: la lista que se le dé y 200 en las escrituras. */
function real(lista: () => Preferencia[] | 'ERROR') {
  const peticiones: Peticion[] = [];
  const fetchFalso = jest.fn(async (url: string, init: RequestInit) => {
    peticiones.push({ url, metodo: String(init.method), cuerpo: init.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith('/v1/preferencias') && init.method === 'GET') {
      const l = lista();
      if (l === 'ERROR') return { ok: false, status: 503, json: async () => null } as unknown as Response;
      return { ok: true, status: 200, json: async () => ({ preferencias: l, tipos: TIPOS }) } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => ({ preferencia: pref({}), idempotente: false, modificadas: [] }) } as unknown as Response;
  });
  const cliente = crearCliente({ baseUrl: 'http://api', token: 't', timeoutMs: 1000 }, fetchFalso as unknown as typeof fetch);
  return { cliente, peticiones };
}

function montar(cliente: ClienteApi, casillas = casillasIniciales(FINALES, null)!) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GuardarPreferencia cliente={cliente} nuevoId={() => ID_ALTA} categoriaId="super" nombre="Supermercado" finales={FINALES} casillas={casillas} cuentas={CUENTAS} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
const esperarLecturas = async () => {
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
};
const escrituras = (ps: Peticion[]) => ps.filter((x) => x.metodo !== 'GET');

// ------------------------------------------------------------------ dominio
test('casillasIniciales sin cambios (MU-M04-01): sin propuesta, las dos marcadas; con la misma propuesta, null', () => {
  expect(casillasIniciales(FINALES, null)).toEqual({ cuenta: true, presupuestable: true });
  expect(casillasIniciales(FINALES, { cuenta: TARJETA, presupuestable: null })).toEqual({ cuenta: false, presupuestable: true });
  expect(casillasIniciales(FINALES, { cuenta: TARJETA, presupuestable: true })).toBeNull();
  expect(casillasIniciales({ cuenta: TARJETA, presupuestable: false }, { cuenta: TARJETA, presupuestable: null })).toEqual({ cuenta: false, presupuestable: true });
});

test('yaRecordado: misma preferencia → sí; un valor distinto, sin preferencia, desactivada o sin nada marcado → no', () => {
  const c = { cuenta: true, presupuestable: true };
  const clave = { categoriaId: 'super', terceroId: null };
  expect(yaRecordado([pref({ cuenta_default_id: TARJETA, presupuestable_default: true })], clave, FINALES, c, TIPOS.GASTO)).toBe(true);
  expect(yaRecordado([pref({ cuenta_default_id: TARJETA, presupuestable_default: false })], clave, FINALES, c, TIPOS.GASTO)).toBe(false);
  expect(yaRecordado([pref({ cuenta_default_id: TARJETA, presupuestable_default: null })], clave, FINALES, c, TIPOS.GASTO)).toBe(false);
  expect(yaRecordado([pref({ cuenta_default_id: 'otra', presupuestable_default: true })], clave, FINALES, c, TIPOS.GASTO)).toBe(false);
  expect(yaRecordado([], clave, FINALES, c, TIPOS.GASTO)).toBe(false);
  expect(yaRecordado([pref({ enabled: false, cuenta_default_id: TARJETA, presupuestable_default: true })], clave, FINALES, c, TIPOS.GASTO)).toBe(false);
  expect(yaRecordado([pref({ cuenta_default_id: TARJETA, presupuestable_default: true })], clave, FINALES, { cuenta: false, presupuestable: false }, TIPOS.GASTO)).toBe(false);
  // Solo cuenta marcada: basta con que la cuenta coincida.
  expect(yaRecordado([pref({ cuenta_default_id: TARJETA, presupuestable_default: false })], clave, FINALES, { cuenta: true, presupuestable: false }, TIPOS.GASTO)).toBe(true);
});

// ------------------------------------------------------------------ O-M04-02
test('O-M04-02: guardada con los mismos valores → «Recordado», sin casillas ni «Guardar», y sin escribir', async () => {
  const r = real(() => [pref({ cuenta_default_id: TARJETA, presupuestable_default: true })]);
  montar(r.cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-recordado')).toBeTruthy();
  expect(screen.getByText('✓ Recordado')).toBeTruthy();
  expect(screen.queryByTestId('pref-guardar')).toBeNull();
  expect(screen.queryByTestId('pref-tarjeta')).toBeNull();
  expect(escrituras(r.peticiones)).toEqual([]);
});

test('O-M04-02: guardada con un valor distinto → se pregunta como hoy', async () => {
  const r = real(() => [pref({ cuenta_default_id: TARJETA, presupuestable_default: false })]);
  montar(r.cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy();
  expect(screen.getByText('¿Recordarlo para Supermercado?')).toBeTruthy();
  expect(screen.queryByTestId('pref-recordado')).toBeNull();
});

// ------------------------------------------------------------------ O-M04-03
test.each([
  ['error de lectura (503)', 'ERROR' as const],
])('O-M04-03: sin lista (%s) → se pregunta como hoy y nunca se escribe sin pulsar', async (_n, valor) => {
  const r = real(() => valor);
  montar(r.cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy();
  expect(screen.queryByTestId('pref-recordado')).toBeNull();
  expect(escrituras(r.peticiones)).toEqual([]); // MU-M04-03: escribir al montar muere aquí
});

test('O-M04-03: si la lectura lanza una excepción → se pregunta como hoy, sin escribir', async () => {
  const alta = jest.fn();
  const editar = jest.fn();
  const cliente = { listarPreferencias: jest.fn(async () => { throw new Error('red'); }), altaPreferencia: alta, editarPreferencia: editar } as unknown as ClienteApi;
  montar(cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy();
  expect(alta).not.toHaveBeenCalled();
  expect(editar).not.toHaveBeenCalled();
});

test('sin preferencia guardada: se pregunta y al montar solo hay lecturas (GET /v1/preferencias)', async () => {
  const r = real(() => []);
  montar(r.cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy();
  expect(r.peticiones.length).toBeGreaterThan(0);
  expect(r.peticiones.every((x) => x.metodo === 'GET' && x.url === 'http://api/v1/preferencias')).toBe(true);
});

// ------------------------------------------------------------------ O-M04-01
test('O-M04-01: ALTA con las casillas de siempre → POST /v1/preferencias con el cuerpo de 180cb1f', async () => {
  const r = real(() => []);
  montar(r.cliente); // casillas de casillasIniciales(finales, sin propuesta) = las dos
  await esperarLecturas();
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  await esperarLecturas();
  expect(escrituras(r.peticiones)).toEqual([{
    url: 'http://api/v1/preferencias',
    metodo: 'POST',
    cuerpo: { id: ID_ALTA, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null, cuenta_default_id: TARJETA, presupuestable_default: true, prioridad: 100 },
  }]);
});

test('O-M04-01: EDITAR (preferencia solo con presupuesto distinto de null) → POST …/editar con el ESTADO COMPLETO de 180cb1f', async () => {
  const r = real(() => [pref({ cuenta_default_id: null, presupuestable_default: true, row_version: 4 })]);
  montar(r.cliente);
  await esperarLecturas();
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy(); // la cuenta no está recordada: se pregunta
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  await esperarLecturas();
  expect(escrituras(r.peticiones)).toEqual([{
    url: 'http://api/v1/preferencias/p-super/editar',
    metodo: 'POST',
    cuerpo: { row_version: 4, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null, cuenta_default_id: TARJETA, presupuestable_default: true, prioridad: 100 },
  }]);
});
