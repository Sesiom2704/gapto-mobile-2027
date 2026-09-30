// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_edicion.test.tsx
// Ruta: mobile/__tests__/ajustes_edicion.test.tsx
// Descripción: Acciones EDIT-* de Ajustes › Categorías y Editar orden (mandato F05-01 S6-WIRE+UI §5, commit 2; lámina SET-CAT v1.0 S03–S06; D-UI-01). Cliente simulado: cada acción comprueba el comando y el payload EXACTOS con el `row_version` del estado cargado; confirmaciones (uso antes del ámbito y reconfirmación con el uso nuevo; RAMA solo con subcategorías activas; reactivar sin cascada); conflicto de versión e indeterminado recargan SIN reintento; Editar orden produce exactamente UNA llamada a /v1/categorias/reordenar con el conjunto completo y ninguna a /{id}/orden (también con el cliente HTTP real sobre un fetch simulado); orden sin cambios no envía nada.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import { crearCliente } from '../src/api/cliente';
import type { ClienteApi, Respuesta, ResultadoComandoCategoria, ResultadoReordenar } from '../src/api/cliente';
import { MICROCOPY_DESACTIVAR, MICROCOPY_RENOMBRAR } from '../src/components/HojasCategoria';
import type { CategoriaNodo } from '../src/domain/categoria';
import {
  MSG_CONJUNTO_DESFASADO,
  MSG_HIJOS_ACTIVOS,
  MSG_INDETERMINADO,
  MSG_MOVER_PADRE_DESHABILITADO,
  MSG_MOVER_PRESUPUESTO,
  MSG_NOMBRE_DUPLICADO,
  MSG_REACTIVAR_ANCESTRO,
  MSG_SIN_CAMBIOS_ORDEN,
  MSG_VERSION,
} from '../src/screens/CategoriasAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, LISTA, nodo } from './fixtures_categorias';

function ok(n: CategoriaNodo): Respuesta<ResultadoComandoCategoria> {
  const { magnitudes: _m, capturable: _c, motivo_no_capturable: _mc, ...cat } = n;
  return { tipo: 'OK', datos: { categoria: cat, idempotente: false, modificadas: [n.id] } };
}
const rechazo = (codigo: string, detalle?: Record<string, unknown>) =>
  ({ tipo: 'RECHAZADO' as const, codigo, mensaje: 'x', ...(detalle ? { detalle } : {}) });

function fake(lista: CategoriaNodo[] = LISTA) {
  let actual = lista;
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(lista),
    arbolCategorias: jest.fn(async () => ({ tipo: 'OK', datos: { categorias: actual } }) as Respuesta<{ categorias: CategoriaNodo[] }>),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  };
  return { cliente, fijarArbol: (l: CategoriaNodo[]) => { actual = l; } };
}

function pintar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={() => 'c0000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 8, 24)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

async function irACategorias(cliente: ClienteApi) {
  pintar(cliente);
  fireEvent.press(screen.getByTestId('tab-MAS'));
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  fireEvent.press(screen.getByTestId('ajustes-categorias'));
  await screen.findByTestId('fila-hogar');
}

/** Abre el detalle de `id` (con `dentroDe` si es un hijo; `todas` para ver desactivadas). */
async function abrirDetalle(cliente: ClienteApi, id: string, o: { dentroDe?: string; todas?: boolean } = {}) {
  await irACategorias(cliente);
  if (o.todas) fireEvent.press(screen.getByTestId('filtro-TODAS'));
  if (o.dentroDe) fireEvent.press(screen.getByTestId(`fila-${o.dentroDe}`));
  if (o.dentroDe === id) fireEvent.press(screen.getByTestId('ver-detalle-nivel'));
  else fireEvent.press(screen.getByTestId(`fila-${id}`));
  await screen.findByTestId('detalle-categoria');
}

const conRv = (id: string, rv: number) => LISTA.map((x) => (x.id === id ? { ...x, row_version: rv } : x));

// ------------------------------------------------------------------ detalle
test('detalle: acciones EDIT-* según estado (activa: Desactivar; desactivada: Reactivar) y nota de Renombrar', async () => {
  const f = fake();
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  for (const t of ['accion-renombrar', 'accion-mover', 'accion-ambito', 'accion-desactivar']) expect(screen.getByTestId(t)).toBeTruthy();
  expect(screen.queryByTestId('accion-reactivar')).toBeNull();
  expect(screen.getByText(/Renombrar corrige el nombre también en lo ya registrado/)).toBeTruthy();
  fireEvent.press(screen.getByTestId('detalle-atras'));
  fireEvent.press(screen.getByTestId('categorias-atras'));
  fireEvent.press(screen.getByTestId('filtro-TODAS'));
  fireEvent.press(screen.getByTestId('fila-viejo'));
  expect(screen.getByTestId('accion-reactivar')).toBeTruthy();
  expect(screen.queryByTestId('accion-desactivar')).toBeNull();
});

// ------------------------------------------------------------------ renombrar
test('renombrar: microcopy, payload exacto con el row_version cargado y nombre recortado; una llamada; recarga', async () => {
  const f = fake(conRv('luz', 4));
  const llamada = jest.fn(async (id: string, c: { row_version: number; nombre: string }) =>
    ok({ ...LISTA.find((x) => x.id === id)!, nombre: c.nombre, row_version: 5 }));
  (f.cliente as any).renombrarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-renombrar'));
  expect(screen.getByTestId('renombrar-microcopy')).toHaveTextContent(MICROCOPY_RENOMBRAR, { exact: false });
  expect(MICROCOPY_RENOMBRAR).toBe('Corrige la etiqueta también en la historia. Si cambia el significado, crea una categoría nueva y desactiva esta.');
  expect(screen.getByTestId('renombrar-guardar')).toBeDisabled(); // sin cambio no se envía
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  fireEvent.changeText(screen.getByTestId('renombrar-nombre'), '  Electricidad  ');
  await act(async () => fireEvent.press(screen.getByTestId('renombrar-guardar')));
  expect(llamada.mock.calls).toEqual([['luz', { row_version: 4, nombre: 'Electricidad' }]]);
  await waitFor(() => expect(screen.queryByTestId('hoja-renombrar')).toBeNull());
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

test('renombrar: CATEGORIA_NOMBRE_DUPLICADO junto al nombre; la hoja sigue abierta y no se reintenta', async () => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo('CATEGORIA_NOMBRE_DUPLICADO'));
  (f.cliente as any).renombrarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-renombrar'));
  fireEvent.changeText(screen.getByTestId('renombrar-nombre'), 'Agua');
  await act(async () => fireEvent.press(screen.getByTestId('renombrar-guardar')));
  expect(screen.getByTestId('renombrar-error')).toHaveTextContent(MSG_NOMBRE_DUPLICADO, { exact: false });
  expect(screen.getByTestId('hoja-renombrar')).toBeTruthy();
  expect(llamada).toHaveBeenCalledTimes(1);
});

test('renombrar: VERSION_DESFASADA recarga y muestra el estado actual SIN reintento automático', async () => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo('VERSION_DESFASADA'));
  (f.cliente as any).renombrarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  f.fijarArbol(LISTA.map((x) => (x.id === 'luz' ? { ...x, nombre: 'Luz (otro dispositivo)', row_version: 7 } : x)));
  fireEvent.press(screen.getByTestId('accion-renombrar'));
  fireEvent.changeText(screen.getByTestId('renombrar-nombre'), 'Electricidad');
  await act(async () => fireEvent.press(screen.getByTestId('renombrar-guardar')));
  expect(await screen.findByTestId('detalle-aviso')).toHaveTextContent(MSG_VERSION, { exact: false });
  expect(await screen.findAllByText('Luz (otro dispositivo)')).not.toHaveLength(0);
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

test('renombrar: INDETERMINADO recarga antes de cualquier repetición y no duplica', async () => {
  const f = fake();
  const llamada = jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' }));
  (f.cliente as any).renombrarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-renombrar'));
  fireEvent.changeText(screen.getByTestId('renombrar-nombre'), 'Electricidad');
  await act(async () => fireEvent.press(screen.getByTestId('renombrar-guardar')));
  expect(await screen.findByTestId('detalle-aviso')).toHaveTextContent(MSG_INDETERMINADO, { exact: false });
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

// ------------------------------------------------------------------ mover
test('mover: selector AJUSTES sin el propio subárbol ni desactivadas; payload exacto; una llamada', async () => {
  const f = fake(conRv('hogar', 3));
  const llamada = jest.fn(async (id: string, c: { row_version: number; parent_id: string | null }) =>
    ok({ ...LISTA.find((x) => x.id === id)!, parent_id: c.parent_id, row_version: 4 }));
  (f.cliente as any).moverCategoria = llamada;
  await abrirDetalle(f.cliente, 'hogar', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-mover'));
  const sel = screen.getByTestId('selector-mover');
  for (const id of ['hogar', 'luz', 'agua', 'gas', 'ocio', 'cine', 'viejo']) expect(within(sel).queryByTestId(`cat-${id}`)).toBeNull();
  expect(within(sel).getByTestId('mover-raiz')).toBeTruthy();
  fireEvent.press(within(sel).getByTestId('cat-trabajo'));
  await act(async () => fireEvent.press(screen.getByTestId('selector-usar')));
  expect(llamada.mock.calls).toEqual([['hogar', { row_version: 3, parent_id: 'trabajo' }]]);
});

test('mover a la ubicación actual no envía nada', async () => {
  const f = fake();
  await abrirDetalle(f.cliente, 'hogar', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-mover'));
  await act(async () => fireEvent.press(screen.getByTestId('mover-raiz')));
  expect(screen.queryByTestId('selector-mover')).toBeNull();
  expect(f.cliente.moverCategoria).not.toHaveBeenCalled();
});

test.each([
  ['CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO', MSG_MOVER_PRESUPUESTO],
  ['CATEGORIA_PADRE_DESHABILITADO', MSG_MOVER_PADRE_DESHABILITADO],
])('mover: %s se explica en texto, se recarga y no se reintenta', async (codigo, texto) => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo(codigo));
  (f.cliente as any).moverCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-mover'));
  await act(async () => fireEvent.press(screen.getByTestId('mover-raiz')));
  expect(await screen.findByTestId('detalle-aviso')).toHaveTextContent(texto, { exact: false });
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

// ------------------------------------------------------------------ ámbito
test('ámbito: consulta el uso ANTES, lo muestra por naturaleza y confirma con confirmacion_uso igual a ese uso', async () => {
  const f = fake(conRv('luz', 2));
  (f.cliente as any).usoCategoria = jest.fn(async (id: string) => ({ tipo: 'OK', datos: { categoria_id: id, ambito: 'GASTO', efectos_activos: { GASTO: 12 } } }));
  const llamada = jest.fn(async (id: string, c: any) => ok({ ...LISTA.find((x) => x.id === id)!, ambito: c.ambito, row_version: 3 }));
  (f.cliente as any).cambiarAmbitoCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-ambito'));
  expect(f.cliente.usoCategoria).toHaveBeenCalledWith('luz');
  expect(await screen.findByTestId('ambito-uso-GASTO')).toHaveProp('accessibilityLabel', 'Gastos: 12');
  expect(screen.getByTestId('ambito-uso-INGRESO')).toHaveProp('accessibilityLabel', 'Ingresos: 0');
  expect(screen.getByTestId('ambito-confirmar')).toBeDisabled(); // mismo ámbito
  fireEvent.press(screen.getByTestId('ambito-nuevo-AMBOS'));
  expect(screen.getByText('Cambiar a Ambos')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('ambito-confirmar')));
  expect(llamada.mock.calls).toEqual([['luz', { row_version: 2, ambito: 'AMBOS', confirmacion_uso: { GASTO: 12 } }]]);
});

test('ámbito: CAMBIO_AMBITO_REQUIERE_CONFIRMACION muestra el uso nuevo y pide confirmar otra vez (sin reenvío automático)', async () => {
  const f = fake();
  (f.cliente as any).usoCategoria = jest.fn(async (id: string) => ({ tipo: 'OK', datos: { categoria_id: id, ambito: 'GASTO', efectos_activos: { GASTO: 12 } } }));
  const llamada = jest
    .fn()
    .mockResolvedValueOnce(rechazo('CAMBIO_AMBITO_REQUIERE_CONFIRMACION', { efectos_activos: { GASTO: 13, INGRESO: 1 } }))
    .mockResolvedValueOnce(ok({ ...LISTA.find((x) => x.id === 'luz')!, ambito: 'AMBOS', row_version: 2 }));
  (f.cliente as any).cambiarAmbitoCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-ambito'));
  await screen.findByTestId('ambito-uso-GASTO');
  fireEvent.press(screen.getByTestId('ambito-nuevo-AMBOS'));
  await act(async () => fireEvent.press(screen.getByTestId('ambito-confirmar')));
  expect(screen.getByTestId('ambito-uso-cambiado')).toBeTruthy();
  expect(screen.getByTestId('ambito-uso-GASTO')).toHaveProp('accessibilityLabel', 'Gastos: 13');
  expect(screen.getByTestId('ambito-uso-INGRESO')).toHaveProp('accessibilityLabel', 'Ingresos: 1');
  expect(llamada).toHaveBeenCalledTimes(1);
  await act(async () => fireEvent.press(screen.getByTestId('ambito-confirmar')));
  expect(llamada.mock.calls[1]).toEqual(['luz', { row_version: 1, ambito: 'AMBOS', confirmacion_uso: { GASTO: 13, INGRESO: 1 } }]);
});

// ------------------------------------------------------------------ desactivar
test('desactivar con subcategorías activas: solo «Desactivar también sus N subcategorías» (RAMA) o Cancelar', async () => {
  const f = fake(conRv('hogar', 6));
  const llamada = jest.fn(async (id: string) => ok({ ...LISTA.find((x) => x.id === id)!, enabled: false, row_version: 7 }));
  (f.cliente as any).desactivarCategoria = llamada;
  await abrirDetalle(f.cliente, 'hogar', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-desactivar'));
  expect(screen.getByTestId('desactivar-subcategorias')).toHaveTextContent('Tiene 3 subcategorías activas: Luz, Agua y Gas.', { exact: false });
  expect(screen.queryByTestId('desactivar-confirmar')).toBeNull(); // sin la opción simple
  fireEvent.press(screen.getByTestId('desactivar-cancelar'));
  expect(llamada).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('accion-desactivar'));
  expect(screen.getByText('Desactivar también sus 3 subcategorías')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('desactivar-rama')));
  expect(llamada.mock.calls).toEqual([['hogar', { row_version: 6, modo: 'RAMA' }]]);
});

test('desactivar sin subcategorías activas: confirmación simple SOLO_SI_SIN_HIJOS_ACTIVOS con su microcopy', async () => {
  const f = fake();
  const llamada = jest.fn(async (id: string) => ok({ ...LISTA.find((x) => x.id === id)!, enabled: false, row_version: 2 }));
  (f.cliente as any).desactivarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  fireEvent.press(screen.getByTestId('accion-desactivar'));
  expect(screen.getByTestId('desactivar-microcopy')).toHaveTextContent(MICROCOPY_DESACTIVAR, { exact: false });
  expect(MICROCOPY_DESACTIVAR).toBe('Sigue en la historia y deja de poder elegirse.');
  expect(llamada).not.toHaveBeenCalled(); // nada sin confirmar
  await act(async () => fireEvent.press(screen.getByTestId('desactivar-confirmar')));
  expect(llamada.mock.calls).toEqual([['luz', { row_version: 1, modo: 'SOLO_SI_SIN_HIJOS_ACTIVOS' }]]);
});

test('desactivar: CATEGORIA_TIENE_HIJOS_ACTIVOS recarga y ofrece RAMA; no se reintenta solo', async () => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo('CATEGORIA_TIENE_HIJOS_ACTIVOS'));
  (f.cliente as any).desactivarCategoria = llamada;
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  f.fijarArbol([...LISTA, nodo({ id: 'luz2', nombre: 'Luz garaje', parent_id: 'luz' })]);
  fireEvent.press(screen.getByTestId('accion-desactivar'));
  await act(async () => fireEvent.press(screen.getByTestId('desactivar-confirmar')));
  expect(await screen.findByTestId('desactivar-rama')).toBeTruthy();
  expect(screen.getByTestId('desactivar-subcategorias')).toHaveTextContent('Tiene 1 subcategoría activa: Luz garaje.', { exact: false });
  expect(screen.getByTestId('detalle-aviso')).toHaveTextContent(MSG_HIJOS_ACTIVOS, { exact: false });
  expect(llamada).toHaveBeenCalledTimes(1);
});

// ------------------------------------------------------------------ reactivar
test('reactivar: solo este nodo (sin cascada en cliente), payload exacto y nota de las subcategorías desactivadas', async () => {
  const lista = LISTA.map((x) => (x.id === 'cine' ? { ...x, enabled: false } : x.id === 'ocio' ? { ...x, row_version: 9 } : x));
  const f = fake(lista);
  const llamada = jest.fn(async (id: string) => ok({ ...lista.find((x) => x.id === id)!, enabled: true, row_version: 10 }));
  (f.cliente as any).reactivarCategoria = llamada;
  await abrirDetalle(f.cliente, 'ocio', { dentroDe: 'ocio', todas: true });
  fireEvent.press(screen.getByTestId('accion-reactivar'));
  expect(screen.getByTestId('reactivar-sin-cascada')).toHaveTextContent('Su subcategoría desactivada seguirá desactivada', { exact: false });
  await act(async () => fireEvent.press(screen.getByTestId('reactivar-confirmar')));
  expect(llamada.mock.calls).toEqual([['ocio', { row_version: 9 }]]);
});

test.each([
  ['CATEGORIA_PADRE_DESHABILITADO', MSG_REACTIVAR_ANCESTRO],
  ['CATEGORIA_NOMBRE_DUPLICADO', 'ya hay una categoría activa llamada «Viajes 2025» en el mismo nivel'],
])('reactivar: %s se explica y se recarga', async (codigo, texto) => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo(codigo));
  (f.cliente as any).reactivarCategoria = llamada;
  await abrirDetalle(f.cliente, 'viejo', { todas: true });
  fireEvent.press(screen.getByTestId('accion-reactivar'));
  await act(async () => fireEvent.press(screen.getByTestId('reactivar-confirmar')));
  expect(await screen.findByTestId('detalle-aviso')).toHaveTextContent(new RegExp(texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

// ------------------------------------------------------------------ Editar orden
test('Editar orden: conjunto COMPLETO (con desactivadas), UNA llamada a reordenar con el orden y los row_version', async () => {
  const f = fake(conRv('viejo', 5));
  const llamada = jest.fn(async (c: any) => ({ tipo: 'OK', datos: { hermanos: [], idempotente: false, modificadas: [] } }) as Respuesta<ResultadoReordenar>);
  (f.cliente as any).reordenarCategorias = llamada;
  await irACategorias(f.cliente); // filtro Activas: la edición incluye igualmente las desactivadas
  fireEvent.press(screen.getByTestId('editar-orden-abrir'));
  expect(screen.getByTestId('editar-orden')).toBeTruthy();
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  for (const id of ['hogar', 'trabajo', 'ocio', 'viejo']) expect(screen.getByTestId(`orden-fila-${id}`)).toBeTruthy();
  expect(screen.getByTestId('orden-subir-hogar')).toBeDisabled();
  expect(screen.getByTestId('orden-bajar-viejo')).toBeDisabled();
  fireEvent.press(screen.getByTestId('orden-subir-viejo'));
  fireEvent.press(screen.getByTestId('orden-bajar-hogar'));
  expect(llamada).not.toHaveBeenCalled(); // nada hasta Guardar
  await act(async () => fireEvent.press(screen.getByTestId('orden-guardar')));
  expect(llamada.mock.calls).toEqual([[{
    parent_id: null,
    hermanos: [
      { id: 'trabajo', row_version: 1 },
      { id: 'hogar', row_version: 1 },
      { id: 'viejo', row_version: 5 },
      { id: 'ocio', row_version: 1 },
    ],
  }]]);
  for (const m of ['renombrarCategoria', 'moverCategoria', 'iconoCategoria', 'desactivarCategoria', 'reactivarCategoria', 'cambiarAmbitoCategoria']) {
    expect((f.cliente as any)[m]).not.toHaveBeenCalled();
  }
  expect(await screen.findByTestId('pantalla-categorias')).toBeTruthy();
});

test('Editar orden sin cambios: no envía nada y avisa «Sin cambios»; Cancelar tampoco envía', async () => {
  const f = fake();
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('fila-hogar'));
  fireEvent.press(screen.getByTestId('editar-orden-abrir'));
  expect(screen.getByTestId('orden-migas')).toHaveTextContent('Todas › Hogar', { exact: false });
  fireEvent.press(screen.getByTestId('orden-cancelar'));
  expect(f.cliente.reordenarCategorias).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('editar-orden-abrir'));
  fireEvent.press(screen.getByTestId('orden-bajar-luz'));
  fireEvent.press(screen.getByTestId('orden-subir-luz')); // vuelve al orden cargado
  await act(async () => fireEvent.press(screen.getByTestId('orden-guardar')));
  expect(f.cliente.reordenarCategorias).not.toHaveBeenCalled();
  expect(await screen.findByTestId('lista-aviso')).toHaveTextContent(MSG_SIN_CAMBIOS_ORDEN, { exact: false });
});

test.each([
  ['CONJUNTO_HERMANOS_DESFASADO', MSG_CONJUNTO_DESFASADO],
  ['VERSION_DESFASADA', MSG_VERSION],
])('Editar orden: %s recarga, sale del modo con aviso y no reintenta', async (codigo, texto) => {
  const f = fake();
  const llamada = jest.fn(async () => rechazo(codigo));
  (f.cliente as any).reordenarCategorias = llamada;
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('editar-orden-abrir'));
  fireEvent.press(screen.getByTestId('orden-bajar-hogar'));
  await act(async () => fireEvent.press(screen.getByTestId('orden-guardar')));
  expect(await screen.findByTestId('lista-aviso')).toHaveTextContent(texto, { exact: false });
  expect(screen.queryByTestId('editar-orden')).toBeNull();
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

test('Editar orden con el cliente HTTP real: exactamente UNA petición POST /v1/categorias/reordenar y ninguna a /{id}/orden', async () => {
  const peticiones: { url: string; metodo: string; cuerpo: unknown }[] = [];
  const categorias = LISTA.map(({ ...x }) => x);
  const fetchFalso = jest.fn(async (url: string, init: RequestInit) => {
    peticiones.push({ url, metodo: String(init.method), cuerpo: init.body ? JSON.parse(String(init.body)) : null });
    // Solo el árbol y reordenar responden; el resto de lecturas (Inicio) fallan como error de servidor.
    if (url.endsWith('/v1/categorias')) return { ok: true, status: 200, json: async () => ({ categorias }) } as unknown as Response;
    if (url.endsWith('/v1/categorias/reordenar'))
      return { ok: true, status: 200, json: async () => ({ hermanos: [], idempotente: false, modificadas: [] }) } as unknown as Response;
    return { ok: false, status: 503, json: async () => null } as unknown as Response;
  });
  const real = crearCliente({ baseUrl: 'http://api', token: 't', timeoutMs: 1000 }, fetchFalso as unknown as typeof fetch);
  await irACategorias(real);
  fireEvent.press(screen.getByTestId('editar-orden-abrir'));
  fireEvent.press(screen.getByTestId('orden-bajar-hogar'));
  await act(async () => fireEvent.press(screen.getByTestId('orden-guardar')));
  await screen.findByTestId('pantalla-categorias');
  const escrituras = peticiones.filter((x) => x.metodo !== 'GET');
  expect(escrituras).toEqual([{
    url: 'http://api/v1/categorias/reordenar',
    metodo: 'POST',
    cuerpo: { parent_id: null, hermanos: ['trabajo', 'hogar', 'ocio', 'viejo'].map((id) => ({ id, row_version: 1 })) },
  }]);
  expect(peticiones.some((x) => /\/orden$/.test(x.url))).toBe(false);
});

test('cliente: un RECHAZADO conserva el detalle del servidor (uso vigente del cambio de ámbito)', async () => {
  const fetchFalso = jest.fn(async () => ({
    ok: false,
    status: 409,
    json: async () => ({ codigo: 'CAMBIO_AMBITO_REQUIERE_CONFIRMACION', mensaje: 'm', detalle: { efectos_activos: { GASTO: 2 } } }),
  }) as unknown as Response);
  const real = crearCliente({ baseUrl: 'http://api', token: 't', timeoutMs: 1000 }, fetchFalso as unknown as typeof fetch);
  const r = await real.cambiarAmbitoCategoria('x', { row_version: 1, ambito: 'AMBOS', confirmacion_uso: {} });
  expect(r).toEqual({ tipo: 'RECHAZADO', codigo: 'CAMBIO_AMBITO_REQUIERE_CONFIRMACION', mensaje: 'm', detalle: { efectos_activos: { GASTO: 2 } } });
});
