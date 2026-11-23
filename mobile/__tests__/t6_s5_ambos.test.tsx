// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s5_ambos.test.tsx
// Ruta: mobile/__tests__/t6_s5_ambos.test.tsx
// Descripción: F06 T6 · S5 (N1; dictamen 1 Q2/A3; DF-10/13) en el cliente, con el cliente REAL (`crearCliente`) y un fetch
//   falso: «Ambos» envía las dos preferencias en UNA llamada a POST /v1/preferencias/ambos; omite el ámbito que ya está igual;
//   pide confirmación si alguno cambia una preferencia existente (y entonces la edita); «Guardada para A y B» solo con OK;
//   ante un rechazo dice qué ámbitos y campos chocan y que no se guardó ninguna (discriminante de M-S5-04); sin la ruta nueva
//   en el cliente no se ofrece «Ambos».
// Versión: 0.1.0 (F06 T6 · S5)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { crearCliente, type ClienteApi, type Preferencia } from '../src/api/cliente';
import { GuardarPreferencia } from '../src/components/GuardarPreferencia';
import { casillasIniciales } from '../src/domain/preferencias';
import { ProveedorTema } from '../src/theme/tema';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const TIPOS = { GASTO: 't-gasto', INGRESO: 't-ingreso' };
const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const CUENTAS = [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA' }];
const FINALES = { cuenta: TARJETA, presupuestable: true };
const AMBITOS = [{ clave: 'TERCERO' as const, id: 'aldi', nombre: 'ALDI' }, { clave: 'CATEGORIA' as const, id: 'super', nombre: 'Supermercado' }];

const pref = (x: Partial<Preferencia>): Preferencia => ({
  id: 'p-x', enabled: true, row_version: 3, tipo_hecho_id: TIPOS.GASTO, categoria_id: null, tercero_id: null, entidad_id: null,
  cuenta_default_id: null, presupuestable_default: null, prioridad: 100, ...x,
});

type Peticion = { url: string; metodo: string; cuerpo: any };
function real(lista: Preferencia[], ambos: { status: number; cuerpo: unknown } = { status: 200, cuerpo: { resultados: [] } }) {
  const peticiones: Peticion[] = [];
  const fetchFalso = jest.fn(async (url: string, init: RequestInit) => {
    peticiones.push({ url, metodo: String(init.method), cuerpo: init.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith('/v1/preferencias') && init.method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ preferencias: lista, tipos: TIPOS }) } as unknown as Response;
    }
    if (url.endsWith('/v1/preferencias/ambos')) {
      return { ok: ambos.status === 200, status: ambos.status, json: async () => ambos.cuerpo } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => ({ preferencia: pref({}), idempotente: false, modificadas: [] }) } as unknown as Response;
  });
  const cliente = crearCliente({ baseUrl: 'http://api', token: 't', timeoutMs: 1000 }, fetchFalso as unknown as typeof fetch);
  return { cliente, peticiones };
}
let n = 0;
function montar(cliente: ClienteApi) {
  n = 0;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GuardarPreferencia cliente={cliente} nuevoId={() => `00000000-0000-4000-8000-00000000000${++n}`} categoriaId="super" nombre="Supermercado"
          finales={FINALES} casillas={casillasIniciales(FINALES, null)!} cuentas={CUENTAS} ambitos={AMBITOS} tipo="GASTO" />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
const esperar = async () => { for (let i = 0; i < 5; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
const pulsar = async (id: string) => { await act(async () => fireEvent.press(screen.getByTestId(id))); await esperar(); };
const ambosLlamadas = (ps: Peticion[]) => ps.filter((x) => x.url.endsWith('/v1/preferencias/ambos'));

test('«Ambos»: una sola llamada con las dos preferencias independientes; «Guardada para ALDI y Supermercado» con OK', async () => {
  const { cliente, peticiones } = real([]);
  montar(cliente);
  await esperar();
  await pulsar('pref-ambito-AMBOS');
  await pulsar('pref-guardar');
  const llamadas = ambosLlamadas(peticiones);
  expect(llamadas).toHaveLength(1);
  expect(peticiones.filter((x) => x.metodo === 'POST' && x.url.endsWith('/v1/preferencias'))).toHaveLength(0);   // nunca dos escrituras sueltas
  const ops = llamadas[0].cuerpo.operaciones;
  expect(ops.map((o: any) => [o.ambito, o.accion, o.contenido.tercero_id, o.contenido.categoria_id])).toEqual([
    ['TERCERO', 'ALTA', 'aldi', null], ['CATEGORIA', 'ALTA', null, 'super']]);
  expect(ops[0].contenido.presupuestable_default).toBe(ops[1].contenido.presupuestable_default);
  expect(ops[0].contenido.prioridad).toBe(ops[1].contenido.prioridad);                                     // sin precedencia implícita
  expect(screen.getByText('Guardada para ALDI y Supermercado')).toBeTruthy();
});

test('rechazo atómico: dice qué ámbito y campo chocan y que no se guardó ninguna; nunca «Guardada»', async () => {
  const { cliente } = real([], { status: 409, cuerpo: { codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: 'x', reintentable: false,
    detalle: { conflictos: [{ ambito: 'TERCERO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', campos: ['presupuestable_default'] }] } } });
  montar(cliente);
  await esperar();
  await pulsar('pref-ambito-AMBOS');
  await pulsar('pref-guardar');
  expect(screen.queryByTestId('pref-guardada')).toBeNull();                                               // M-S5-04
  expect(screen.getByTestId('pref-rechazo-ambos')).toBeTruthy();
  expect(screen.getByText(/No se ha guardado ninguna de las dos/)).toBeTruthy();
  expect(screen.getByText(/para ALDI \(el presupuesto\)/)).toBeTruthy();
});

test('el ámbito que ya está igual se omite: solo viaja el otro', async () => {
  const { cliente, peticiones } = real([pref({ id: 'p-aldi', tercero_id: 'aldi', cuenta_default_id: TARJETA, presupuestable_default: true })]);
  montar(cliente);
  await esperar();
  await pulsar('pref-ambito-AMBOS');
  await pulsar('pref-guardar');
  const ops = ambosLlamadas(peticiones)[0].cuerpo.operaciones;
  expect(ops.map((o: any) => o.ambito)).toEqual(['CATEGORIA']);
});

test('si cambia una existente pide confirmación y, al sustituir, la edita en la misma llamada', async () => {
  const { cliente, peticiones } = real([pref({ id: 'p-aldi', tercero_id: 'aldi', presupuestable_default: false })]);
  montar(cliente);
  await esperar();
  await pulsar('pref-ambito-AMBOS');
  await pulsar('pref-guardar');
  expect(screen.getByTestId('pref-conflicto-ambos')).toBeTruthy();
  expect(ambosLlamadas(peticiones)).toHaveLength(0);
  await pulsar('pref-sustituir-ambos');
  const ops = ambosLlamadas(peticiones)[0].cuerpo.operaciones;
  expect(ops.map((o: any) => [o.ambito, o.accion, o.id, o.row_version ?? null])).toEqual([['TERCERO', 'EDITAR', 'p-aldi', 3], ['CATEGORIA', 'ALTA', ops[1].id, null]]);
});

test('sin la ruta nueva en el cliente no se ofrece «Ambos» (dobles antiguos)', async () => {
  const { cliente } = real([]);
  const { preferenciasAmbos: _q, ...antiguo } = cliente;
  montar(antiguo as ClienteApi);
  await esperar();
  expect(screen.queryByTestId('pref-ambito-AMBOS')).toBeNull();
  expect(screen.getByTestId('pref-ambito-TERCERO')).toBeTruthy();
});
