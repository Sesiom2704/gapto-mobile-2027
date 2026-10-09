// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_preferencias.test.tsx
// Ruta: mobile/__tests__/ajustes_preferencias.test.tsx
// Descripción: Ajustes › Preferencias (F05-02 B3; lámina SET-PREF / REG-PREF v0.1, sección B S01–S06 y oscuro; D-PREF-01..06; AJ-B1-10; D-B3-01). Una prueba por pantalla y por regla: entrada desde Ajustes con título «Preferencias»; S05 vacío; S01 lista agrupada y ordenada, «Pagar con X» / «Presupuesto: Sí/No», «Padre › Hija», marca «No disponible» solo con `cuenta_disponible_hoy = false` (D-PREF-04) y pie; S02 alta con solo dos ámbitos (D-PREF-01), cuentas y categorías de la MISMA fuente que REG-01 (sin regla propia: una INGRESO no se puede elegir, AJ-B1-10), «Guardar» desactivado sin propuesta (espejo del CHECK), contenido completo y UUID sellado al abrir; S03 por existente y por carrera (nunca se crea otra); S04 detalle, desactivar y reactivar (empate al reactivar) sin borrado; E05 al editar; S06 VERSION_DESFASADA → recarga y aviso sin reintento; INDETERMINADO con el mismo UUID; cuenta actual no disponible al editar; tareas inmersivas; modo oscuro.
// Versión: 0.1.0 (F05-02 B3)
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, ContenidoPreferencia, CuentaPago, Preferencia, Respuesta, ResultadoComandoPreferencia } from '../src/api/cliente';
import { agruparPreferencias, contenidoFormulario, faltaFormulario, formularioDesde, textosPropone } from '../src/domain/preferencias';
import {
  TEXTO_CHECK,
  TEXTO_DESACTIVADA,
  TEXTO_INTRO,
  TEXTO_PIE,
  TEXTO_REACTIVADA,
  TEXTO_S06,
  TEXTO_S06_TITULO,
  TEXTO_SOLO_NUEVOS,
  TEXTO_VACIO,
} from '../src/screens/PreferenciasAjustesScreen';
import { colores } from '../src/theme/tokens';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const EFECTIVO = 'c0000000-0000-4000-8000-00000000000b';
const COMUN = 'c0000000-0000-4000-8000-00000000000c';
const USD = 'c0000000-0000-4000-8000-00000000000d';
const REVOLUT = 'c0000000-0000-4000-8000-00000000000e'; // deshabilitada: no está en cuentas-pago
const AHORA = () => new Date(2026, 8, 24, 10, 0, 0);
const HOY = '2026-09-24';

const ARBOL = [
  nodo({ id: 'alim', nombre: 'Alimentación' }),
  nodo({ id: 'super', nombre: 'Supermercado', parent_id: 'alim' }),
  nodo({ id: 'ocio', nombre: 'Ocio', orden: 1 }),
  nodo({ id: 'rest', nombre: 'Restaurantes', parent_id: 'ocio' }),
  nodo({ id: 'transp', nombre: 'Transporte', orden: 2 }),
  nodo({ id: 'gasolina', nombre: 'Gasolina', parent_id: 'transp' }),
  nodo({ id: 'hogar', nombre: 'Hogar', orden: 3 }),
  nodo({ id: 'limpieza', nombre: 'Limpieza', parent_id: 'hogar' }),
  nodo({ id: 'trabajo', nombre: 'Trabajo', ambito: 'INGRESO', orden: 4 }),
  nodo({ id: 'nomina', nombre: 'Nómina', parent_id: 'trabajo', ambito: 'INGRESO' }),
  nodo({ id: 'viejo', nombre: 'Viajes 2025', enabled: false, orden: 5 }),
];

const cuenta = (cuenta_id: string, nombre: string, moneda = 'EUR'): CuentaPago => ({ cuenta_id, nombre, moneda, propuesta_financiacion: 'SELF_100' });
// Lo que ofrece REG-01 (GET /v1/vs01/cuentas-pago): también una cuenta en otra moneda.
const CUENTAS = [cuenta(TARJETA, 'Tarjeta BBVA'), cuenta(EFECTIVO, 'Efectivo'), cuenta(COMUN, 'Cuenta común'), cuenta(USD, 'Cuenta USD', 'USD')];

function pref(p: Partial<Preferencia> & { id: string }): Preferencia {
  return {
    tipo_hecho_id: null, categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null,
    presupuestable_default: null, prioridad: 100, enabled: true, row_version: 1, cuenta_disponible_hoy: null, ...p,
  };
}

// Lámina S01.
const GENERAL = pref({ id: 'p-general', presupuestable_default: true });
const SUPER = pref({ id: 'p-super', categoria_id: 'super', cuenta_default_id: TARJETA, cuenta_disponible_hoy: true });
const REST = pref({ id: 'p-rest', categoria_id: 'rest', presupuestable_default: false });
const GASOLINA = pref({ id: 'p-gas', categoria_id: 'gasolina', cuenta_default_id: REVOLUT, cuenta_disponible_hoy: false });
const LIMPIEZA = pref({ id: 'p-limp', categoria_id: 'limpieza', cuenta_default_id: EFECTIVO, cuenta_disponible_hoy: true, enabled: false });
const LAMINA = [LIMPIEZA, GASOLINA, REST, SUPER, GENERAL];

function okPref(p: Preferencia): Respuesta<ResultadoComandoPreferencia> {
  return { tipo: 'OK', datos: { preferencia: p, idempotente: false, modificadas: [p.id] } };
}

/** Respuesta forzada; `undefined` = comportamiento normal del doble. */
type Mando = (id: string, c: any) => Promise<Respuesta<ResultadoComandoPreferencia> | undefined> | undefined;

function fake(inicial: Preferencia[] = [], o: { alta?: Mando; editar?: Mando; desactivar?: Mando; reactivar?: Mando } = {}) {
  let lista = [...inicial];
  const fijar = (x: Preferencia) => {
    lista = [...lista.filter((y) => y.id !== x.id), x];
    return okPref(x);
  };
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async () => { throw new Error('no esperado'); }),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: CUENTAS } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarPreferencias: jest.fn(async () => ({ tipo: 'OK', datos: { preferencias: lista } }) as Respuesta<{ preferencias: Preferencia[] }>),
    altaPreferencia: jest.fn(async (c: ContenidoPreferencia & { id: string }) =>
      (await o.alta?.(c.id, c)) ?? fijar(pref({ ...c, cuenta_disponible_hoy: c.cuenta_default_id === null ? null : true }))),
    editarPreferencia: jest.fn(async (id: string, c: ContenidoPreferencia & { row_version: number }) => {
      const r = await o.editar?.(id, c);
      if (r) return r;
      const { row_version, ...resto } = c;
      const actual = lista.find((x) => x.id === id)!;
      return fijar({ ...actual, ...resto, row_version: row_version + 1, cuenta_disponible_hoy: resto.cuenta_default_id === null ? null : true });
    }),
    desactivarPreferencia: jest.fn(async (id: string, rv: number) => {
      const r = await o.desactivar?.(id, rv);
      if (r) return r;
      const actual = lista.find((x) => x.id === id)!;
      return fijar({ ...actual, enabled: false, row_version: rv + 1 });
    }),
    reactivarPreferencia: jest.fn(async (id: string, rv: number) => {
      const r = await o.reactivar?.(id, rv);
      if (r) return r;
      const actual = lista.find((x) => x.id === id)!;
      return fijar({ ...actual, enabled: true, row_version: rv + 1 });
    }),
  };
  return { cliente, fijarLista: (l: Preferencia[]) => (lista = l), lista: () => lista };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

async function abrir(cliente: ClienteApi, esquema: 'light' | 'dark' = 'light') {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar={esquema}>
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(screen.getByTestId('tab-MAS'));
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  fireEvent.press(screen.getByTestId('ajustes-preferencias'));
  await screen.findByTestId('pantalla-preferencias');
  await waitFor(() => expect(screen.queryByTestId('ajpref-cargando')).toBeNull());
}

/** Texto plano de un nodo con Text anidados. */
function plano(id: string): string {
  const partes: string[] = [];
  const visitar = (x: unknown): void => {
    if (typeof x === 'string' || typeof x === 'number') partes.push(String(x));
    else if (Array.isArray(x)) x.forEach(visitar);
    else if (x && typeof x === 'object' && 'props' in (x as object)) visitar((x as { props: { children: unknown } }).props.children);
  };
  visitar(screen.getByTestId(id).props.children);
  return partes.join('');
}

const marcado = (id: string) => screen.getByTestId(id).props.accessibilityState.checked;
const desactivado = (id: string) => screen.getByTestId(id).props.accessibilityState.disabled;
const tituloFila = (id: string) => plano(`ajpref-fila-${id}-titulo`);

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

function elegirCategoria(padre: string, hija: string) {
  fireEvent.press(screen.getByTestId('ajpref-form-categoria'));
  fireEvent.press(within(screen.getByTestId('ajpref-selector')).getByTestId(`cat-${padre}`));
  fireEvent.press(within(screen.getByTestId('ajpref-selector')).getByTestId(`cat-${hija}`));
}

// ------------------------------------------------------------------ entrada (D-B3-01)
test('entrada: la fila «Preferencias financieras» de Ajustes es navegable y la pantalla se titula «Preferencias»', async () => {
  const f = fake(LAMINA);
  await abrir(f.cliente);
  expect(screen.getByText('Preferencias')).toBeTruthy();
  expect(screen.queryByTestId('ajustes-seccion-Preferencias financieras')).toBeNull();
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy(); // lista: conserva la barra inferior
  expect(f.cliente.cuentasPago).toHaveBeenCalledWith(HOY); // cuentas de REG-01, en la fecha de hoy
  fireEvent.press(screen.getByTestId('ajpref-atras'));
  expect(screen.getByTestId('pantalla-ajustes')).toBeTruthy();
  expect(within(screen.getByTestId('ajustes-preferencias')).getByText('Preferencias financieras')).toBeTruthy();
});

// ------------------------------------------------------------------ S05
test('S05 estado vacío: textos de la lámina y «Nueva preferencia» abre el alta', async () => {
  const f = fake([]);
  await abrir(f.cliente);
  const vacio = within(screen.getByTestId('ajpref-vacio'));
  expect(vacio.getByText('Sin preferencias')).toBeTruthy();
  expect(vacio.getByText(TEXTO_VACIO)).toBeTruthy();
  expect(TEXTO_VACIO).toBe('Crea una para que Gapto te proponga la cuenta o si el gasto cuenta para el presupuesto. También puedes guardarla al registrar un gasto.');
  expect(screen.queryByTestId('ajpref-intro')).toBeNull();
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  expect(screen.getByTestId('ajpref-form')).toBeTruthy();
  expect(screen.getByText('Nueva preferencia')).toBeTruthy();
});

// ------------------------------------------------------------------ S01
test('S01 lista: grupos, orden, «Padre › Hija», lo que propone, «No disponible» solo si el servidor lo dice, pie', async () => {
  const ambos = pref({ id: 'p-ambos', categoria_id: 'limpieza', cuenta_default_id: COMUN, presupuestable_default: true, cuenta_disponible_hoy: true });
  // Cuenta en otra moneda: REG-01 la lista (tiene nombre), pero el servidor dice que no es elegible hoy.
  const usd = pref({ id: 'p-usd', categoria_id: 'alim', cuenta_default_id: USD, cuenta_disponible_hoy: false });
  const f = fake([...LAMINA, ambos, usd]);
  await abrir(f.cliente);
  expect(screen.getByText(TEXTO_INTRO)).toBeTruthy();
  expect(TEXTO_INTRO).toBe('Gapto propone estos valores al registrar un gasto. Siempre puedes cambiarlos antes de guardar.');
  const filas = (g: string) => within(screen.getByTestId(`ajpref-grupo-${g}`)).getAllByTestId(/^ajpref-fila-p-[a-z]+$/).map((x) => x.props.testID);
  expect(within(screen.getByTestId('ajpref-grupo-todos')).getByText('TODOS LOS GASTOS')).toBeTruthy();
  expect(within(screen.getByTestId('ajpref-grupo-categoria')).getByText('POR CATEGORÍA')).toBeTruthy();
  expect(within(screen.getByTestId('ajpref-grupo-desactivadas')).getByText('DESACTIVADAS')).toBeTruthy();
  expect(filas('todos')).toEqual(['ajpref-fila-p-general']);
  // Orden por rótulo visible (es): Alimentación › Supermercado, Hogar › Limpieza, Ocio › Restaurantes, Transporte › Gasolina.
  expect(filas('categoria')).toEqual(['ajpref-fila-p-usd', 'ajpref-fila-p-super', 'ajpref-fila-p-ambos', 'ajpref-fila-p-rest', 'ajpref-fila-p-gas']);
  expect(filas('desactivadas')).toEqual(['ajpref-fila-p-limp']);
  expect(tituloFila('p-general')).toBe('General');
  expect(plano('ajpref-fila-p-general-propone')).toBe('Presupuesto: Sí');
  expect(tituloFila('p-super')).toBe('Alimentación › Supermercado');
  expect(plano('ajpref-fila-p-super-propone')).toBe('Pagar con Tarjeta BBVA');
  expect(plano('ajpref-fila-p-rest-propone')).toBe('Presupuesto: No');
  expect(plano('ajpref-fila-p-ambos-propone')).toBe('Pagar con Cuenta común · Presupuesto: Sí');
  // D-PREF-04: la marca vive aquí y solo cuando cuenta_disponible_hoy = false (la cuenta no está en REG-01: sin nombre).
  expect(screen.getByTestId('ajpref-fila-p-gas-no-disponible')).toBeTruthy();
  expect(plano('ajpref-fila-p-gas-propone')).toBe('Pagar con una cuenta');
  expect(tituloFila('p-usd')).toBe('Alimentación');
  expect(plano('ajpref-fila-p-usd-propone')).toBe('Pagar con Cuenta USD');
  expect(screen.getByTestId('ajpref-fila-p-usd-no-disponible')).toBeTruthy(); // el dato es del servidor, no de la lista
  for (const id of ['p-general', 'p-super', 'p-rest', 'p-ambos', 'p-limp']) expect(screen.queryByTestId(`ajpref-fila-${id}-no-disponible`)).toBeNull();
  expect(screen.getByTestId('ajpref-fila-p-gas').props.accessibilityLabel).toBe('Transporte › Gasolina. Pagar con una cuenta. No disponible');
  expect(screen.getByTestId('ajpref-fila-p-limp').props.accessibilityLabel).toBe('Hogar › Limpieza. Pagar con Efectivo. Desactivada');
  expect(screen.getByText(TEXTO_PIE)).toBeTruthy();
  expect(TEXTO_PIE).toBe('Si una categoría tiene preferencia, gana a la general en lo que proponga.');
});

test('S01 (dominio): agrupar y ordenar es estable y no depende del orden de la API', () => {
  const rot = (x: Preferencia) => ({ 'p-general': 'General', 'p-super': 'Alimentación › Supermercado', 'p-rest': 'Ocio › Restaurantes', 'p-gas': 'Transporte › Gasolina', 'p-limp': 'Hogar › Limpieza' })[x.id]!;
  const a = agruparPreferencias(LAMINA, rot);
  const b = agruparPreferencias([...LAMINA].reverse(), rot);
  expect(a).toEqual(b);
  expect(a.todos.map((x) => x.id)).toEqual(['p-general']);
  expect(a.categoria.map((x) => x.id)).toEqual(['p-super', 'p-rest', 'p-gas']);
  expect(textosPropone(pref({ id: 'x', cuenta_default_id: TARJETA, presupuestable_default: false }), () => 'Tarjeta BBVA')).toEqual(['Pagar con Tarjeta BBVA', 'Presupuesto: No']);
});

// ------------------------------------------------------------------ S02
test('S02: solo dos ámbitos (D-PREF-01); cuentas de REG-01 tal cual; «Guardar» desactivado sin propuesta con el texto del CHECK', async () => {
  const f = fake([]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  expect(screen.queryByTestId('tab-INICIO')).toBeNull(); // tarea inmersiva
  expect(screen.getByTestId('ajpref-ambito-GENERAL')).toBeTruthy();
  expect(screen.getByTestId('ajpref-ambito-CATEGORIA')).toBeTruthy();
  expect(within(screen.getByTestId('ajpref-form')).getAllByRole('radio')).toHaveLength(2);
  expect(screen.getByText('Todos los gastos')).toBeTruthy();
  expect(screen.getByText('Una categoría')).toBeTruthy();
  // La misma lista que REG-01 (sin filtro propio del cliente), más «No proponer».
  for (const c of CUENTAS) expect(screen.getByTestId(`ajpref-cuenta-${c.cuenta_id}`)).toBeTruthy();
  expect(marcado('ajpref-cuenta-no')).toBe(true);
  expect(marcado('ajpref-presu-no-proponer')).toBe(true);
  expect(plano('ajpref-check')).toBe(TEXTO_CHECK);
  expect(TEXTO_CHECK).toBe('Tiene que proponer al menos una de las dos cosas.');
  expect(desactivado('ajpref-guardar')).toBe(true);
  fireEvent.press(screen.getByTestId('ajpref-ambito-GENERAL'));
  expect(desactivado('ajpref-guardar')).toBe(true); // ámbito sin propuesta: sigue desactivado
  await pulsar('ajpref-guardar');
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('ajpref-presu-true'));
  expect(desactivado('ajpref-guardar')).toBe(false);
  fireEvent.press(screen.getByTestId('ajpref-presu-no-proponer'));
  expect(desactivado('ajpref-guardar')).toBe(true);
});

test('S02 alta «Una categoría»: contenido COMPLETO, prioridad 100, UUID sellado al abrir y detalle al guardar', async () => {
  const f = fake([]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva')); // nuevoId() → …0001
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  expect(screen.getByTestId('ajpref-falta-CATEGORIA')).toBeTruthy();
  elegirCategoria('ocio', 'rest');
  expect(plano('ajpref-form-categoria')).toContain('Ocio › Restaurantes');
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${TARJETA}`));
  await pulsar('ajpref-guardar');
  expect(f.cliente.altaPreferencia).toHaveBeenCalledWith({
    id: '00000000-0000-4000-8000-000000000001', tipo_hecho_id: null, categoria_id: 'rest', tercero_id: null, entidad_id: null,
    cuenta_default_id: TARJETA, presupuestable_default: null, prioridad: 100,
  });
  expect(await screen.findByTestId('ajpref-detalle')).toBeTruthy();
  expect(plano('ajpref-det-ambito-valor')).toBe('Ocio › Restaurantes');
  expect(plano('ajpref-det-cuenta-valor')).toBe('Tarjeta BBVA');
  expect(plano('ajpref-det-presupuesto-valor')).toBe('No propone');
});

test('AJ-B1-10: el selector es el de REG-01 (una categoría INGRESO o desactivada no se puede elegir)', async () => {
  const f = fake([]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  fireEvent.press(screen.getByTestId('ajpref-form-categoria'));
  const sel = within(screen.getByTestId('ajpref-selector'));
  expect(sel.queryByTestId('cat-trabajo')).toBeNull(); // solo ingresos y sin descendientes de gasto: oculta, como en REG-01
  expect(sel.queryByTestId('cat-viejo')).toBeNull(); // desactivada: oculta
  expect(sel.queryByTestId('selector-sin-categoria')).toBeNull(); // «Una categoría» exige categoría
  fireEvent.press(sel.getByTestId('selector-cerrar'));
  expect(screen.queryByTestId('ajpref-selector')).toBeNull();
  expect(desactivado('ajpref-guardar')).toBe(true);
});

// ------------------------------------------------------------------ S03
test('S03: ya existe una preferencia para esa categoría → aviso e «Ir a la preferencia»; nunca se crea otra', async () => {
  const f = fake([SUPER]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  elegirCategoria('alim', 'super');
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${EFECTIVO}`));
  expect(plano('ajpref-existente')).toBe('Ya existe una preferencia para Supermercado que propone Tarjeta BBVA. Edítala en lugar de crear otra.');
  expect(screen.queryByTestId('ajpref-guardar')).toBeNull();
  fireEvent.press(screen.getByTestId('ajpref-ir'));
  expect(screen.getByTestId('ajpref-detalle')).toBeTruthy();
  expect(plano('ajpref-det-ambito-valor')).toBe('Alimentación › Supermercado');
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled();
});

test('S03 general: ya existe una general → aviso (una general y una de categoría nunca chocan)', async () => {
  const f = fake([GENERAL, SUPER]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  elegirCategoria('ocio', 'rest');
  expect(screen.queryByTestId('ajpref-existente')).toBeNull(); // la general no impide una de categoría
  fireEvent.press(screen.getByTestId('ajpref-ambito-GENERAL'));
  expect(plano('ajpref-existente')).toBe('Ya existe una preferencia para todos los gastos que propone presupuesto: Sí. Edítala en lugar de crear otra.');
});

test('S03 por carrera: el alta responde PREFERENCIA_EMPATE_CONTRADICTORIO → se recarga y se lleva a la existente', async () => {
  const otra = pref({ id: 'p-otra', categoria_id: 'rest', cuenta_default_id: EFECTIVO, cuenta_disponible_hoy: true });
  const f = fake([], {
    alta: async () => {
      f.fijarLista([otra]); // otra sesión la creó entre la lectura y el alta
      return { tipo: 'RECHAZADO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: 'x', detalle: { preferencia_conflicto_id: 'p-otra' } };
    },
  });
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  elegirCategoria('ocio', 'rest');
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${TARJETA}`));
  await pulsar('ajpref-guardar');
  expect(plano('ajpref-existente')).toBe('Ya existe una preferencia para Restaurantes que propone Efectivo. Edítala en lugar de crear otra.');
  expect(f.cliente.altaPreferencia).toHaveBeenCalledTimes(1);
  fireEvent.press(screen.getByTestId('ajpref-ir'));
  expect(plano('ajpref-det-cuenta-valor')).toBe('Efectivo');
});

test('S03 por empate con una preferencia por tipo de gasto (solo creable por API; D-PREF-01): la lleva a ella', async () => {
  // «Gasto → Efectivo» frente a «Restaurantes → Tarjeta»: misma especificidad, el servidor rechaza (AJ-D026-03).
  const porTipo = pref({ id: 'p-tipo', tipo_hecho_id: 't-gasto', cuenta_default_id: EFECTIVO, cuenta_disponible_hoy: true });
  const f = fake([porTipo], {
    alta: async () => ({ tipo: 'RECHAZADO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: 'x', detalle: { preferencia_conflicto_id: 'p-tipo' } }),
  });
  await abrir(f.cliente);
  expect(tituloFila('p-tipo')).toBe('Por tipo de gasto');
  fireEvent.press(screen.getByTestId('ajpref-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-CATEGORIA'));
  elegirCategoria('ocio', 'rest');
  expect(screen.queryByTestId('ajpref-existente')).toBeNull(); // no es del mismo ámbito: solo el servidor lo detecta
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${TARJETA}`));
  await pulsar('ajpref-guardar');
  expect(plano('ajpref-existente')).toBe('Ya existe una preferencia para este tipo de gasto que propone Efectivo. Edítala en lugar de crear otra.');
  fireEvent.press(screen.getByTestId('ajpref-ir'));
  expect(plano('ajpref-det-ambito-valor')).toBe('Por tipo de gasto');
});

// ------------------------------------------------------------------ S04
test('S04 detalle: datos, «Solo afecta a gastos nuevos», desactivar y reactivar con row_version; sin borrado', async () => {
  const f = fake([pref({ ...SUPER, row_version: 4 })]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-super'));
  expect(screen.queryByTestId('tab-INICIO')).toBeTruthy(); // el detalle no es inmersivo
  expect(screen.getByText('Supermercado')).toBeTruthy(); // título
  expect(plano('ajpref-det-ambito-valor')).toBe('Alimentación › Supermercado');
  expect(plano('ajpref-det-cuenta-valor')).toBe('Tarjeta BBVA');
  expect(plano('ajpref-det-presupuesto-valor')).toBe('No propone');
  expect(screen.getByText(TEXTO_SOLO_NUEVOS)).toBeTruthy();
  expect(screen.queryByText(/Borrar|Eliminar/)).toBeNull();
  await pulsar('ajpref-desactivar');
  expect(f.cliente.desactivarPreferencia).toHaveBeenCalledWith('p-super', 4);
  expect(plano('ajpref-aviso-ok')).toBe(TEXTO_DESACTIVADA);
  expect(TEXTO_DESACTIVADA).toBe('Desactivada: deja de proponerse. Puedes reactivarla cuando quieras; si choca con otra que hayas creado después, te lo diremos.');
  expect(plano('ajpref-det-estado-valor')).toBe('Desactivada');
  await pulsar('ajpref-reactivar');
  expect(f.cliente.reactivarPreferencia).toHaveBeenCalledWith('p-super', 5);
  expect(plano('ajpref-aviso-ok')).toBe(TEXTO_REACTIVADA);
  expect(screen.getByTestId('ajpref-desactivar')).toBeTruthy();
  fireEvent.press(screen.getByTestId('ajpref-detalle-atras'));
  expect(screen.getByTestId('ajpref-grupo-categoria')).toBeTruthy();
});

test('S04 reactivar comprueba el empate como crear o editar: aviso y «Ir a la preferencia», sin reactivar', async () => {
  const nueva = pref({ id: 'p-nueva', categoria_id: 'limpieza', cuenta_default_id: COMUN, cuenta_disponible_hoy: true });
  const f = fake([LIMPIEZA, nueva], {
    reactivar: async () => ({ tipo: 'RECHAZADO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: 'x', detalle: { preferencia_conflicto_id: 'p-nueva' } }),
  });
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-limp'));
  await pulsar('ajpref-reactivar');
  expect(plano('ajpref-aviso')).toBe('No se puede reactivar: choca con la preferencia para Limpieza que propone Cuenta común.');
  expect(f.lista().find((x) => x.id === 'p-limp')!.enabled).toBe(false);
  fireEvent.press(screen.getByTestId('ajpref-aviso-ir'));
  expect(plano('ajpref-det-cuenta-valor')).toBe('Cuenta común');
});

test('S04 detalle de una cuenta no disponible: «No disponible» también aquí (D-PREF-04)', async () => {
  const f = fake([GASOLINA]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-gas'));
  expect(plano('ajpref-det-cuenta-valor')).toBe('Cuenta no disponible');
  expect(screen.getByTestId('ajpref-det-cuenta-no-disponible')).toBeTruthy();
});

// ------------------------------------------------------------------ edición (E05, S06)
test('editar envía el ESTADO COMPLETO (E05) con row_version y las claves de la existente', async () => {
  const conTipo = pref({ ...SUPER, row_version: 2 });
  const f = fake([conTipo]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-super'));
  fireEvent.press(screen.getByTestId('ajpref-editar'));
  expect(screen.queryByTestId('tab-INICIO')).toBeNull(); // tarea inmersiva
  expect(plano('ajpref-form-ambito-fijo')).toBe('Alimentación › Supermercado');
  expect(marcado(`ajpref-cuenta-${TARJETA}`)).toBe(true);
  fireEvent.press(screen.getByTestId('ajpref-presu-false'));
  await pulsar('ajpref-guardar');
  expect(f.cliente.editarPreferencia).toHaveBeenCalledWith('p-super', {
    row_version: 2, tipo_hecho_id: null, categoria_id: 'super', tercero_id: null, entidad_id: null,
    cuenta_default_id: TARJETA, presupuestable_default: false, prioridad: 100,
  });
  expect(await screen.findByTestId('ajpref-detalle')).toBeTruthy();
  expect(plano('ajpref-det-presupuesto-valor')).toBe('No');
});

test('editar una preferencia por tipo de gasto (creada por API) conserva su clave de tipo de hecho (E05)', async () => {
  const porTipo = pref({ id: 'p-tipo', tipo_hecho_id: 't-gasto', cuenta_default_id: EFECTIVO, cuenta_disponible_hoy: true, row_version: 3 });
  const f = fake([porTipo]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-tipo'));
  fireEvent.press(screen.getByTestId('ajpref-editar'));
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${TARJETA}`));
  await pulsar('ajpref-guardar');
  expect(f.cliente.editarPreferencia).toHaveBeenCalledWith('p-tipo', {
    row_version: 3, tipo_hecho_id: 't-gasto', categoria_id: null, tercero_id: null, entidad_id: null,
    cuenta_default_id: TARJETA, presupuestable_default: null, prioridad: 100,
  });
});

test('S06: VERSION_DESFASADA → se recarga la versión actual y se avisa, sin reintento automático', async () => {
  let intentos = 0;
  const f = fake([pref({ ...SUPER, row_version: 1 })], {
    editar: async () => {
      if (++intentos > 1) return undefined;
      f.fijarLista([pref({ ...SUPER, cuenta_default_id: EFECTIVO, row_version: 2 })]); // otra sesión la cambió
      return { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'x' };
    },
  });
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-super'));
  fireEvent.press(screen.getByTestId('ajpref-editar'));
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${COMUN}`));
  await pulsar('ajpref-guardar');
  expect(plano('ajpref-form-aviso')).toBe(`${TEXTO_S06_TITULO} ${TEXTO_S06}`);
  expect(TEXTO_S06_TITULO).toBe('Esta preferencia ha cambiado mientras la editabas.');
  expect(TEXTO_S06).toBe('Hemos cargado la versión actual. Revisa y guarda de nuevo.');
  expect(marcado(`ajpref-cuenta-${EFECTIVO}`)).toBe(true); // la versión actual, no lo que se había elegido
  expect(f.cliente.editarPreferencia).toHaveBeenCalledTimes(1); // sin reintento automático
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${COMUN}`));
  await pulsar('ajpref-guardar');
  expect((f.cliente.editarPreferencia as jest.Mock).mock.calls[1][1].row_version).toBe(2);
  expect(await screen.findByTestId('ajpref-detalle')).toBeTruthy();
});

test('editar una preferencia cuya cuenta no está disponible: no se reenvía sin elegir otra o «No proponer»', async () => {
  const f = fake([GASOLINA]);
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-fila-p-gas'));
  fireEvent.press(screen.getByTestId('ajpref-editar'));
  expect(marcado('ajpref-cuenta-actual')).toBe(true);
  expect(plano('ajpref-cuenta-actual')).toContain('Cuenta actual · No disponible');
  expect(screen.getByTestId('ajpref-falta-CUENTA_NO_DISPONIBLE')).toBeTruthy();
  expect(desactivado('ajpref-guardar')).toBe(true);
  fireEvent.press(screen.getByTestId('ajpref-cuenta-no'));
  fireEvent.press(screen.getByTestId('ajpref-presu-true'));
  expect(desactivado('ajpref-guardar')).toBe(false);
  await pulsar('ajpref-guardar');
  expect((f.cliente.editarPreferencia as jest.Mock).mock.calls[0][1]).toMatchObject({ cuenta_default_id: null, presupuestable_default: true });
});

test('formulario (dominio): la cuenta no disponible no se envía y el espejo del CHECK', () => {
  const fo = formularioDesde(GASOLINA, CUENTAS);
  expect(fo.cuenta).toEqual({ noDisponible: REVOLUT });
  expect(faltaFormulario(fo)).toEqual(['CUENTA_NO_DISPONIBLE']);
  expect(contenidoFormulario(fo, GASOLINA).cuenta_default_id).toBeNull();
  expect(faltaFormulario({ ambito: 'GENERAL', categoriaId: null, cuenta: null, presupuestable: null })).toEqual(['PROPONER']);
  expect(faltaFormulario({ ambito: null, categoriaId: null, cuenta: TARJETA, presupuestable: null })).toEqual(['AMBITO']);
});

// ------------------------------------------------------------------ INDETERMINADO
test('INDETERMINADO en el alta: aviso, y el reintento usa el MISMO UUID (nunca se duplica)', async () => {
  let intentos = 0;
  const f = fake([], { alta: async () => (++intentos === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : undefined) });
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-GENERAL'));
  fireEvent.press(screen.getByTestId('ajpref-presu-false'));
  await pulsar('ajpref-guardar');
  expect(plano('ajpref-form-aviso')).toBe('No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.');
  await pulsar('ajpref-guardar');
  const ids = (f.cliente.altaPreferencia as jest.Mock).mock.calls.map((c) => c[0].id);
  expect(ids).toEqual(['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001']);
  expect(await screen.findByTestId('ajpref-detalle')).toBeTruthy();
});

test('INDETERMINADO en el alta que sí se guardó: al recargar aparece y se muestra su detalle', async () => {
  const f = fake([], {
    alta: async (id, c) => {
      f.fijarLista([pref({ ...c, id })]);
      return { tipo: 'INDETERMINADO', mensaje: 'x' };
    },
  });
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('ajpref-vacio-nueva'));
  fireEvent.press(screen.getByTestId('ajpref-ambito-GENERAL'));
  fireEvent.press(screen.getByTestId(`ajpref-cuenta-${EFECTIVO}`));
  await pulsar('ajpref-guardar');
  expect(await screen.findByTestId('ajpref-detalle')).toBeTruthy();
  expect(f.cliente.altaPreferencia).toHaveBeenCalledTimes(1);
});

test('error de carga: estado explícito y reintento', async () => {
  const f = fake([GENERAL]);
  let falla = true;
  const original = f.cliente.listarPreferencias;
  f.cliente.listarPreferencias = jest.fn(async () => (falla ? ({ tipo: 'INDETERMINADO', mensaje: 'x' } as const) : original()));
  await abrir(f.cliente);
  expect(screen.getByTestId('ajpref-error')).toBeTruthy();
  falla = false;
  await pulsar('ajpref-error');
  expect(await screen.findByTestId('ajpref-grupo-todos')).toBeTruthy();
});

// ------------------------------------------------------------------ oscuro
test('modo oscuro: superficies y marca «No disponible» con los tokens oscuros', async () => {
  const f = fake(LAMINA);
  await abrir(f.cliente, 'dark');
  const plana = (x: unknown): Record<string, unknown> => (Array.isArray(x) ? Object.assign({}, ...x.map(plana)) : ((x as object) ?? {}) as Record<string, unknown>);
  expect(plana(screen.getByTestId('pantalla-preferencias').props.style).backgroundColor).toBe(colores.dark.background);
  const marca = plana(screen.getByTestId('ajpref-fila-p-gas-no-disponible').props.style);
  expect(marca.backgroundColor).toBe(colores.dark.partialSurface);
  expect(marca.borderColor).toBe(colores.dark.warning);
});
