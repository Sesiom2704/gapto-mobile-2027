// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_categorias.test.tsx
// Ruta: mobile/__tests__/ajustes_categorias.test.tsx
// Descripción: Más → Ajustes → Categorías (D-UI-03; F09 §12.91.1, §12.97.4–12.97.6, §12.97.9 I01–I03; lámina SET-CAT v1.0), commit 1: diez secciones en orden con solo «Categorías» operativa y el resto «No disponible» no pulsable; lista por niveles con filtro Activas (por defecto) / Todas y desactivadas con texto; detalle en lectura SIN acciones EDIT-* (llegan en el commit 2) y fila «Icono» que guarda con el row_version vigente; conflicto de versión que recarga sin reintento; alta CREATE-M con acción desactivada hasta completar, sin preselección de ámbito ni presupuesto, aviso D-198 solo con padre, ubicación restringida a padres habilitados, id sellado y reutilizado en el reintento indeterminado, y tratamiento de los códigos de rechazo; tareas inmersivas sin barra inferior.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): el detalle ya muestra las acciones EDIT-* (cubiertas en ajustes_edicion.test.tsx); aquí se comprueba que «Editar orden» es de la lista y no del detalle.
// Versión: 0.3.0 (F05-02 B3, A1): «Preferencias financieras» pasa de «No disponible» a navegable; las ocho restantes siguen «No disponible» y no pulsables.
// ============================================================

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { AltaCategoria, ClienteApi, Respuesta, ResultadoComandoCategoria } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import { SECCIONES_AJUSTES } from '../src/screens/MasScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, LISTA, nodo } from './fixtures_categorias';

function resultado(n: CategoriaNodo): Respuesta<ResultadoComandoCategoria> {
  const { magnitudes: _m, capturable: _c, motivo_no_capturable: _mc, ...cat } = n;
  return { tipo: 'OK', datos: { categoria: cat, idempotente: false, modificadas: [n.id] } };
}

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

let n = 0;
const nuevoId = () => `c0000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

async function irACategorias(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={() => new Date(2026, 8, 24)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(screen.getByTestId('tab-MAS'));
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  fireEvent.press(screen.getByTestId('ajustes-categorias'));
  await screen.findByTestId('fila-hogar');
}

beforeEach(() => {
  n = 0;
});

test('Más → Ajustes: 10 secciones de F09 §12.91.1 en orden; solo Categorías navega, el resto «No disponible»', async () => {
  const f = fake();
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={f.cliente} nuevoId={nuevoId} ahora={() => new Date(2026, 8, 24)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(screen.getByTestId('tab-MAS'));
  expect(screen.getByTestId('pantalla-mas')).toBeTruthy();
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy(); // lista: conserva la barra
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  expect(SECCIONES_AJUSTES).toEqual(['Terceros', 'Categorías', 'Etiquetas', 'Contextos', 'Reglas y recurrencias', 'Preferencias financieras',
    'Apariencia y personalización', 'Preferencias de uso', 'Datos y mantenimiento', 'Cuenta y sistema']);
  // F05-02 B3: «Preferencias financieras» también es operativa (cubierta en ajustes_preferencias.test.tsx).
  for (const sec of SECCIONES_AJUSTES.filter((x) => x !== 'Categorías' && x !== 'Preferencias financieras')) {
    const fila = screen.getByTestId(`ajustes-seccion-${sec}`);
    expect(fila.props.accessibilityLabel).toBe(`${sec}. No disponible`);
    expect(fila.props.onPress).toBeUndefined(); // no pulsable
  }
  expect(screen.getAllByText('No disponible')).toHaveLength(8);
  fireEvent.press(screen.getByTestId('ajustes-atras'));
  expect(screen.getByTestId('pantalla-mas')).toBeTruthy(); // «Atrás» al nivel anterior real
});

test('lista: Activas por defecto, Todas muestra las desactivadas con texto; niveles, migas y «Atrás»', async () => {
  const f = fake();
  await irACategorias(f.cliente);
  expect(screen.getByTestId('filtro-ACTIVAS').props.accessibilityState.selected).toBe(true);
  expect(screen.queryByTestId('fila-viejo')).toBeNull();
  expect(screen.queryByTestId('fila-ocio')).toBeNull();
  fireEvent.press(screen.getByTestId('filtro-TODAS'));
  expect(screen.getByTestId('fila-viejo').props.accessibilityLabel).toBe('Viajes 2025. Desactivada');
  expect(screen.getByTestId('fila-trabajo').props.accessibilityLabel).toBe('Trabajo. Ingreso · 2 subcategorías');
  fireEvent.press(screen.getByTestId('fila-hogar'));
  expect(screen.getByTestId('categorias-migas')).toBeTruthy();
  expect(screen.getByTestId('fila-gas')).toBeTruthy();
  fireEvent.press(screen.getByTestId('categorias-atras'));
  expect(screen.getByTestId('fila-hogar')).toBeTruthy();
  fireEvent.press(screen.getByTestId('categorias-atras'));
  expect(screen.getByTestId('pantalla-ajustes')).toBeTruthy();
});

test('detalle: datos en lectura, acciones EDIT-* presentes y «Editar orden» solo en la lista', async () => {
  const f = fake();
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('fila-hogar'));
  fireEvent.press(screen.getByTestId('fila-luz'));
  expect(screen.getByTestId('detalle-categoria')).toBeTruthy();
  expect(screen.getByTestId('detalle-ambito').props.accessibilityLabel).toBe('Ámbito: Gasto');
  expect(screen.getByTestId('detalle-estado').props.accessibilityLabel).toBe('Estado: Activa');
  expect(screen.getByTestId('detalle-icono').props.accessibilityLabel).toBe('Icono: Luz. Cambiar icono');
  for (const t of ['Renombrar', 'Mover a otra categoría', 'Cambiar ámbito', 'Desactivar']) expect(screen.getByText(t)).toBeTruthy();
  expect(screen.queryByText('Reactivar')).toBeNull();
  expect(screen.queryByText('Editar orden')).toBeNull();
  fireEvent.press(screen.getByTestId('detalle-atras'));
  fireEvent.press(screen.getByTestId('ver-detalle-nivel'));
  expect(screen.getByTestId('detalle-categoria')).toBeTruthy();
});

test('icono: guarda con el row_version vigente; permitido en desactivadas; sin barra inferior', async () => {
  const f = fake();
  const vistas: { id: string; c: { row_version: number; icon_key: string | null } }[] = [];
  (f.cliente as any).iconoCategoria = jest.fn(async (id: string, c: { row_version: number; icon_key: string | null }) => {
    vistas.push({ id, c });
    return resultado({ ...LISTA.find((x) => x.id === id)!, icon_key: c.icon_key, row_version: 2 });
  });
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('filtro-TODAS'));
  fireEvent.press(screen.getByTestId('fila-viejo'));
  expect(screen.getByTestId('detalle-estado').props.accessibilityLabel).toBe('Estado: Desactivada');
  fireEvent.press(screen.getByTestId('detalle-icono'));
  expect(screen.getByTestId('selector-iconos')).toBeTruthy();
  expect(screen.queryByTestId('tab-INICIO')).toBeNull(); // tarea inmersiva
  expect(screen.getByTestId('iconos-accion')).toBeDisabled(); // sin cambio no se guarda
  fireEvent.press(screen.getByTestId('icono-transporte.avion'));
  expect(screen.getByTestId('icono-transporte.avion').props.accessibilityLabel).toBe('Avión. Elegido');
  await act(async () => fireEvent.press(screen.getByTestId('iconos-accion')));
  expect(vistas).toEqual([{ id: 'viejo', c: { row_version: 1, icon_key: 'transporte.avion' } }]);
  expect(await screen.findByTestId('detalle-categoria')).toBeTruthy();
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy();
});

test('icono: «Sin icono» envía null', async () => {
  const f = fake();
  const iconos: (string | null)[] = [];
  (f.cliente as any).iconoCategoria = jest.fn(async (id: string, c: { row_version: number; icon_key: string | null }) => {
    iconos.push(c.icon_key);
    return resultado({ ...LISTA.find((x) => x.id === id)!, icon_key: c.icon_key, row_version: 2 });
  });
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('fila-hogar'));
  fireEvent.press(screen.getByTestId('fila-luz'));
  fireEvent.press(screen.getByTestId('detalle-icono'));
  fireEvent.press(screen.getByTestId('icono-ninguno'));
  await act(async () => fireEvent.press(screen.getByTestId('iconos-accion')));
  expect(iconos).toEqual([null]);
});

test('VERSION_DESFASADA al guardar el icono: recarga y muestra el estado actual, sin reintento automático', async () => {
  const f = fake();
  const llamada = jest.fn(async () => ({ tipo: 'RECHAZADO' as const, codigo: 'VERSION_DESFASADA', mensaje: 'x' }));
  (f.cliente as any).iconoCategoria = llamada;
  await irACategorias(f.cliente);
  fireEvent.press(screen.getByTestId('fila-hogar'));
  fireEvent.press(screen.getByTestId('fila-luz'));
  f.fijarArbol(LISTA.map((x) => (x.id === 'luz' ? { ...x, icon_key: 'hogar.gas', row_version: 3 } : x)));
  fireEvent.press(screen.getByTestId('detalle-icono'));
  fireEvent.press(screen.getByTestId('icono-hogar.casa'));
  await act(async () => fireEvent.press(screen.getByTestId('iconos-accion')));
  expect(await screen.findByTestId('detalle-aviso')).toBeTruthy();
  await waitFor(() => expect(screen.getByTestId('detalle-icono').props.accessibilityLabel).toBe('Icono: Gas. Cambiar icono'));
  expect(llamada).toHaveBeenCalledTimes(1);
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});

async function abrirAlta(cliente: ClienteApi, dentroDe?: string) {
  await irACategorias(cliente);
  if (dentroDe) fireEvent.press(screen.getByTestId(`fila-${dentroDe}`));
  fireEvent.press(screen.getByTestId('nueva-categoria'));
  await screen.findByTestId('nueva-categoria-pantalla');
}

test('alta: sin preselección, acción desactivada hasta completar y lo que falta indicado; sin barra inferior', async () => {
  const f = fake();
  await abrirAlta(f.cliente);
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  expect(screen.getByTestId('alta-crear')).toBeDisabled();
  expect(screen.getByTestId('alta-faltan').props.children).toBe('Para crear falta: nombre, ámbito y si cuenta para el presupuesto.');
  for (const v of ['GASTO', 'INGRESO', 'AMBOS']) expect(screen.getByTestId(`alta-ambito-${v}`).props.accessibilityState.selected).toBe(false);
  expect(screen.getByTestId('alta-presupuesto-true').props.accessibilityState.selected).toBe(false);
  fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Prueba raíz');
  fireEvent.press(screen.getByTestId('alta-ambito-GASTO'));
  expect(screen.getByTestId('alta-crear')).toBeDisabled();
  fireEvent.press(screen.getByTestId('alta-presupuesto-false'));
  expect(screen.getByTestId('alta-crear')).toBeEnabled();
});

test('aviso D-198 solo con padre (no en raíz); ubicación restringida a padres habilitados', async () => {
  const f = fake();
  await abrirAlta(f.cliente);
  expect(screen.queryByTestId('aviso-d198')).toBeNull();
  fireEvent.press(screen.getByTestId('alta-ubicacion'));
  expect(screen.getByTestId('selector-ubicacion')).toBeTruthy();
  expect(screen.queryByTestId('cat-ocio')).toBeNull(); // deshabilitado: no se ofrece
  expect(screen.queryByTestId('cat-viejo')).toBeNull();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('selector-usar'));
  expect(screen.getByTestId('aviso-d198')).toBeTruthy();
  expect(screen.getByText('Dentro de Hogar')).toBeTruthy();
  fireEvent.press(screen.getByTestId('alta-ubicacion'));
  fireEvent.press(screen.getByTestId('ubicacion-raiz'));
  expect(screen.queryByTestId('aviso-d198')).toBeNull();
});

test('alta dentro de un nivel: el padre es ese nivel y el payload es el exacto', async () => {
  const f = fake();
  const altas: AltaCategoria[] = [];
  (f.cliente as any).crearCategoria = jest.fn(async (a: AltaCategoria) => {
    altas.push(a);
    return resultado(nodo({ id: a.id, nombre: a.nombre, parent_id: a.parent_id }));
  });
  await abrirAlta(f.cliente, 'hogar');
  expect(screen.getByTestId('aviso-d198')).toBeTruthy();
  fireEvent.changeText(screen.getByTestId('alta-nombre'), '  Comunidad ');
  fireEvent.press(screen.getByTestId('alta-icono'));
  fireEvent.press(screen.getByTestId('icono-hogar.casa'));
  fireEvent.press(screen.getByTestId('iconos-accion'));
  fireEvent.press(screen.getByTestId('alta-ambito-GASTO'));
  fireEvent.press(screen.getByTestId('alta-presupuesto-true'));
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(altas).toEqual([{ id: 'c0000000-0000-4000-8000-000000000001', nombre: 'Comunidad', parent_id: 'hogar', ambito: 'GASTO', presupuestable_default: true, icon_key: 'hogar.casa' }]);
  expect(await screen.findByTestId('pantalla-categorias')).toBeTruthy();
});

test('alta INDETERMINADA: el reintento reenvía la MISMA petición con el MISMO id y el formulario queda bloqueado', async () => {
  const f = fake();
  const altas: AltaCategoria[] = [];
  let k = 0;
  (f.cliente as any).crearCategoria = jest.fn(async (a: AltaCategoria) => {
    altas.push(a);
    return ++k === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : resultado(nodo({ id: a.id, nombre: a.nombre }));
  });
  await abrirAlta(f.cliente);
  fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Prueba raíz');
  fireEvent.press(screen.getByTestId('alta-ambito-AMBOS'));
  fireEvent.press(screen.getByTestId('alta-presupuesto-false'));
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(await screen.findByTestId('alta-indeterminado')).toBeTruthy();
  expect(screen.getByTestId('alta-nombre').props.editable).toBe(false);
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(altas).toHaveLength(2);
  expect(altas[1]).toEqual(altas[0]);
});

test('alta: CATEGORIA_NOMBRE_DUPLICADO junto al nombre y el siguiente envío usa id nuevo', async () => {
  const f = fake();
  const altas: AltaCategoria[] = [];
  let k = 0;
  (f.cliente as any).crearCategoria = jest.fn(async (a: AltaCategoria) => {
    altas.push(a);
    return ++k === 1 ? { tipo: 'RECHAZADO', codigo: 'CATEGORIA_NOMBRE_DUPLICADO', mensaje: 'x' } : resultado(nodo({ id: a.id, nombre: a.nombre }));
  });
  await abrirAlta(f.cliente);
  fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Hogar');
  fireEvent.press(screen.getByTestId('alta-ambito-GASTO'));
  fireEvent.press(screen.getByTestId('alta-presupuesto-true'));
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(await screen.findByTestId('alta-error-nombre')).toBeTruthy();
  fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Hogar 2');
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(altas[1].id).not.toBe(altas[0].id);
});

test('alta: CATEGORIA_PADRE_DESHABILITADO recarga el árbol y pide otra ubicación', async () => {
  const f = fake();
  (f.cliente as any).crearCategoria = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'CATEGORIA_PADRE_DESHABILITADO', mensaje: 'x' }));
  await abrirAlta(f.cliente, 'hogar');
  fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Comunidad');
  fireEvent.press(screen.getByTestId('alta-ambito-GASTO'));
  fireEvent.press(screen.getByTestId('alta-presupuesto-true'));
  await act(async () => fireEvent.press(screen.getByTestId('alta-crear')));
  expect(await screen.findByTestId('alta-aviso')).toBeTruthy();
  expect(screen.getByText('Categoría principal (raíz)')).toBeTruthy();
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
});
