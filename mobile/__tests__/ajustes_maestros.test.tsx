// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_maestros.test.tsx
// Ruta: mobile/__tests__/ajustes_maestros.test.tsx
// Descripción: Ajustes › Terceros, Contextos y Plantillas, y la oferta de categorías sugeridas (F05-03 J2 §2.5/§2.6; láminas REG-DYN / SET-TH / SET-CTX v0.1 S01–S03, C01, P02 y SET-PLT / HOME-QA v0.2 S01–S05, O01/O02). Terceros: filtro Todos/Activos/Inactivos y por nombre, alta con duplicados (P02: usar, reactivar, crear otro) y UUID sellado al abrir, edición, desactivar y reactivar con row_version, VERSION_DESFASADA recarga y avisa. Contextos: texto de la lámina, «Viaje · 10–12 oct», alta C01 sin tipo preseleccionado y fechas validadas. Plantillas: grupos y resumen, «No disponible», alta con tipo/categoría por tipo y acceso en Inicio, nombre repetido S04, límite S03, detalle S05 y desactivar. Onboarding: solo sin categorías; crea con el comando del servidor.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.5/§2.6)
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { AccionRapida, ClienteApi, Contexto, Plantilla, Respuesta, Tercero } from '../src/api/cliente';
import { TEXTO_CONTEXTO } from '../src/components/Contextos';
import { TEXTO_O01, textoO02 } from '../src/components/OnboardingCategorias';
import { TEXTO_DUPLICADO } from '../src/components/SelectorTercero';
import { agruparPlantillas, detalleContexto, filtrar, huecosLibres, normalizarNombre, rangoFechas, resumenPlantilla, textoHuecos } from '../src/domain/maestros';
import { contenidoPlantilla, faltaPlantilla, FORMULARIO_PLANTILLA_NUEVO, moverAcceso, nombreAcceso, planAcceso, TEXTO_INTRO_PLANTILLAS, TEXTO_LIMITE, textoEnInicio } from '../src/domain/plantillas';
import { TEXTO_S02, TEXTO_VERSION } from '../src/screens/TercerosAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const TIPOS = { GASTO: 't-gasto', INGRESO: 't-ingreso' };
const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const ARBOL = [
  nodo({ id: 'alim', nombre: 'Alimentación' }),
  nodo({ id: 'super', nombre: 'Supermercado', parent_id: 'alim' }),
  nodo({ id: 'trabajo', nombre: 'Trabajo', ambito: 'INGRESO', orden: 1 }),
  nodo({ id: 'nomina', nombre: 'Nómina', parent_id: 'trabajo', ambito: 'INGRESO' }),
];

const ter = (p: Partial<Tercero> & { id: string; nombre: string }): Tercero => ({ naturaleza: null, enabled: true, row_version: 1, ...p });
const ctx = (p: Partial<Contexto> & { id: string; nombre: string }): Contexto => ({
  tipo_contexto: 'VIAJE', fecha_inicio: null, fecha_fin: null, enabled: true, row_version: 1, ...p,
});
const plt = (p: Partial<Plantilla> & { id: string; nombre: string }): Plantilla => ({
  tipo_hecho_id: TIPOS.GASTO, categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null, presupuestable_default: null,
  enabled: true, row_version: 1, tipo: 'GASTO', avisos: [], ...p,
});
const acc = (p: Partial<AccionRapida> & { id: string; plantilla_registro_id: string }): AccionRapida => ({
  nombre: 'Acceso', orden: 0, icono_key: null, enabled: true, row_version: 1, ...p,
});

/** Cliente simulado con estado en memoria de terceros, contextos, plantillas y accesos. */
function fake(o: { terceros?: Tercero[]; contextos?: Contexto[]; plantillas?: Plantilla[]; acciones?: AccionRapida[]; arbol?: typeof ARBOL } = {}) {
  const st = { terceros: [...(o.terceros ?? [])], contextos: [...(o.contextos ?? [])], plantillas: [...(o.plantillas ?? [])], acciones: [...(o.acciones ?? [])] };
  const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
  const fijar = <T extends { id: string }>(l: T[], x: T) => [...l.filter((y) => y.id !== x.id), x];
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(o.arbol ?? ARBOL),
    registrarGastoPagado: jest.fn(async () => { throw new Error('no esperado'); }),
    cuentasPago: jest.fn(async () => ok({ cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' as const }] })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarTerceros: jest.fn(async () => ok({ terceros: st.terceros })),
    candidatosTercero: jest.fn(async (nombre: string) => ok({ terceros: st.terceros.filter((t) => normalizarNombre(t.nombre) === normalizarNombre(nombre)) })),
    altaTercero: jest.fn(async (c) => {
      const x = ter({ id: c.id, nombre: c.nombre, naturaleza: c.naturaleza });
      st.terceros = fijar(st.terceros, x);
      return ok({ tercero: x, idempotente: false, modificadas: [x.id] });
    }),
    editarTercero: jest.fn(async (id, c) => {
      const a = st.terceros.find((t) => t.id === id)!;
      if (a.row_version !== c.row_version) return { tipo: 'RECHAZADO' as const, codigo: 'VERSION_DESFASADA', mensaje: 'x' };
      const x = { ...a, nombre: c.nombre, naturaleza: c.naturaleza, row_version: a.row_version + 1 };
      st.terceros = fijar(st.terceros, x);
      return ok({ tercero: x, idempotente: false, modificadas: [id] });
    }),
    desactivarTercero: jest.fn(async (id, rv) => {
      const x = { ...st.terceros.find((t) => t.id === id)!, enabled: false, row_version: rv + 1 };
      st.terceros = fijar(st.terceros, x);
      return ok({ tercero: x, idempotente: false, modificadas: [id] });
    }),
    reactivarTercero: jest.fn(async (id, rv) => {
      const x = { ...st.terceros.find((t) => t.id === id)!, enabled: true, row_version: rv + 1 };
      st.terceros = fijar(st.terceros, x);
      return ok({ tercero: x, idempotente: false, modificadas: [id] });
    }),
    listarContextos: jest.fn(async () => ok({ contextos: st.contextos })),
    altaContexto: jest.fn(async (c) => {
      const x = ctx({ ...c });
      st.contextos = fijar(st.contextos, x);
      return ok({ contexto: x, idempotente: false, modificadas: [x.id] });
    }),
    desactivarContexto: jest.fn(async (id, rv) => {
      const x = { ...st.contextos.find((t) => t.id === id)!, enabled: false, row_version: rv + 1 };
      st.contextos = fijar(st.contextos, x);
      return ok({ contexto: x, idempotente: false, modificadas: [id] });
    }),
    listarPlantillas: jest.fn(async () => ok({ plantillas: st.plantillas, acciones: st.acciones })),
    altaPlantilla: jest.fn(async (c) => {
      const otra = st.plantillas.find((x) => x.enabled && normalizarNombre(x.nombre) === normalizarNombre(c.nombre));
      if (otra) return { tipo: 'RECHAZADO' as const, codigo: 'PLANTILLA_NOMBRE_REPETIDO', mensaje: 'x', detalle: { plantilla_id: otra.id } };
      const x = plt({ ...c, tipo: c.tipo_hecho_id === TIPOS.INGRESO ? 'INGRESO' : 'GASTO' });
      st.plantillas = fijar(st.plantillas, x);
      return ok({ plantilla: x, idempotente: false, modificadas: [x.id] });
    }),
    editarPlantilla: jest.fn(async (id, c) => {
      const a = st.plantillas.find((x) => x.id === id)!;
      const { row_version, ...resto } = c;
      const x = { ...a, ...resto, row_version: row_version + 1 };
      st.plantillas = fijar(st.plantillas, x);
      return ok({ plantilla: x, idempotente: false, modificadas: [id] });
    }),
    desactivarPlantilla: jest.fn(async (id, rv) => {
      const x = { ...st.plantillas.find((y) => y.id === id)!, enabled: false, row_version: rv + 1 };
      st.plantillas = fijar(st.plantillas, x);
      st.acciones = st.acciones.map((a) => (a.plantilla_registro_id === id ? { ...a, enabled: false, row_version: a.row_version + 1 } : a));
      return ok({ plantilla: x, idempotente: false, modificadas: [id] });
    }),
    altaAccion: jest.fn(async (c) => {
      if (st.acciones.filter((a) => a.enabled).length >= 3) return { tipo: 'RECHAZADO' as const, codigo: 'ACCION_LIMITE_ALCANZADO', mensaje: 'x' };
      const x = acc({ id: c.id, plantilla_registro_id: c.plantilla_registro_id, nombre: c.nombre, icono_key: c.icono_key, orden: st.acciones.length });
      st.acciones = fijar(st.acciones, x);
      return ok({ accion: x, idempotente: false, modificadas: [x.id] });
    }),
    desactivarAccion: jest.fn(async (id, rv) => {
      const x = { ...st.acciones.find((a) => a.id === id)!, enabled: false, row_version: rv + 1 };
      st.acciones = fijar(st.acciones, x);
      return ok({ accion: x, idempotente: false, modificadas: [id] });
    }),
  };
  return { cliente, st };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

async function abrir(cliente: ClienteApi, seccion: 'terceros' | 'contextos' | 'plantillas' | 'categorias') {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={() => new Date(2026, 9, 10, 10)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(screen.getByTestId('tab-MAS'));
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  await act(async () => fireEvent.press(screen.getByTestId(`ajustes-${seccion}`)));
}

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

// ------------------------------------------------------------------ dominio
test('dominio: normalización C06, filtro local, rango de fechas, huecos y resumen', () => {
  expect(normalizarNombre('  Ál  Di ')).toBe('al di');
  expect(filtrar([{ nombre: 'ALDI' }, { nombre: 'Mercadona' }], 'aldí').map((x) => x.nombre)).toEqual(['ALDI']);
  expect(rangoFechas('2026-10-10', '2026-10-12')).toBe('10–12 oct');
  expect(rangoFechas('2026-10-30', '2026-11-02')).toBe('30 oct – 2 nov');
  expect(detalleContexto(ctx({ id: 'x', nombre: 'x', tipo_contexto: 'EVENTO', enabled: false }))).toBe('Evento · Desactivado');
  expect(textoHuecos(huecosLibres([acc({ id: 'a', plantilla_registro_id: 'p' }), acc({ id: 'b', plantilla_registro_id: 'q' })]))).toBe('Queda 1 hueco libre');
  expect(textoHuecos(0)).toBe('Inicio está completo');
  expect(resumenPlantilla(plt({ id: 'p', nombre: 'x', categoria_id: 'super', cuenta_default_id: TARJETA, presupuestable_default: true }),
    { categoria: () => 'Supermercado', cuenta: () => 'Tarjeta BBVA' })).toBe('Supermercado · Tarjeta BBVA · Presupuesto: Sí');
  const g = agruparPlantillas([plt({ id: 'p1', nombre: 'a' }), plt({ id: 'p2', nombre: 'b' }), plt({ id: 'p3', nombre: 'c', enabled: false })],
    [acc({ id: 'a2', plantilla_registro_id: 'p2', orden: 0 }), acc({ id: 'a1', plantilla_registro_id: 'p1', orden: 1 })]);
  expect(g.enInicio.map((x) => x.plantilla.id)).toEqual(['p2', 'p1']);
  expect(g.desactivadas.map((x) => x.id)).toEqual(['p3']);
});

test('dominio plantillas: falta, contenido con tipo, nombre del acceso y plan del acceso', () => {
  expect(faltaPlantilla(FORMULARIO_PLANTILLA_NUEVO)).toEqual(['nombre', 'tipo', 'proponer']);
  const f = { ...FORMULARIO_PLANTILLA_NUEVO, nombre: ' Súper semanal ', tipo: 'INGRESO' as const, categoriaId: 'nomina' };
  expect(contenidoPlantilla(f, TIPOS)).toEqual({ nombre: 'Súper semanal', tipo_hecho_id: TIPOS.INGRESO, categoria_id: 'nomina', tercero_id: null, entidad_id: null, cuenta_default_id: null, presupuestable_default: null });
  expect(nombreAcceso({ nombre: 'Súper semanal', nombreCorto: '' })).toBe('Súper semanal');
  expect(nombreAcceso({ nombre: 'Súper semanal', nombreCorto: 'Súper' })).toBe('Súper');
  const a = acc({ id: 'a', plantilla_registro_id: 'p', nombre: 'Súper' });
  expect(planAcceso({ ...f, enInicio: false }, a)).toEqual({ tipo: 'QUITAR', accion: a });
  expect(planAcceso({ ...f, enInicio: true, nombreCorto: 'Súper' }, a)).toEqual({ tipo: 'NADA' });
  expect(planAcceso({ ...f, enInicio: true }, null)).toEqual({ tipo: 'ALTA', nombre: 'Súper semanal', icono_key: null });
  const l = [acc({ id: 'x', plantilla_registro_id: 'p', orden: 0 }), acc({ id: 'y', plantilla_registro_id: 'q', orden: 1 })];
  expect(moverAcceso(l, 'y', -1)).toEqual([{ id: 'y', row_version: 1 }, { id: 'x', row_version: 1 }]);
  expect(moverAcceso(l, 'x', -1)).toBeNull();
  expect(textoEnInicio(l, 'q')).toBe('Sí · posición 2');
});

// ------------------------------------------------------------------ Terceros
test('Terceros S01: filtro Todos / Activos / Inactivos y por nombre; inactivo con «Inactivo»', async () => {
  const f = fake({ terceros: [ter({ id: 't1', nombre: 'ALDI', naturaleza: 'EMPRESA' }), ter({ id: 't2', nombre: 'Lidl', enabled: false })] });
  await abrir(f.cliente, 'terceros');
  await screen.findByTestId('ajter-lista');
  expect(screen.getByTestId('ajter-fila-t1-detalle').props.children).toBe('Empresa');
  expect(screen.getByTestId('ajter-fila-t2-detalle').props.children).toBe('Inactivo');
  fireEvent.press(screen.getByTestId('ajter-filtro-ACTIVOS'));
  expect(screen.queryByTestId('ajter-fila-t2')).toBeNull();
  fireEvent.press(screen.getByTestId('ajter-filtro-INACTIVOS'));
  expect(screen.queryByTestId('ajter-fila-t1')).toBeNull();
  fireEvent.press(screen.getByTestId('ajter-filtro-TODOS'));
  fireEvent.changeText(screen.getByTestId('ajter-buscar'), 'ald');
  expect(screen.getByTestId('ajter-fila-t1')).toBeTruthy();
  expect(screen.queryByTestId('ajter-fila-t2')).toBeNull();
});

test('Terceros alta: duplicado P02 con «Reactivar» o «Crear otro»; UUID sellado al abrir; sin fusión', async () => {
  const f = fake({ terceros: [ter({ id: 't2', nombre: 'Mercadona', enabled: false })] });
  await abrir(f.cliente, 'terceros');
  await pulsar('ajter-nuevo'); // nuevoId() → …0001
  expect(screen.queryByTestId('tab-INICIO')).toBeNull(); // inmersiva
  fireEvent.changeText(screen.getByTestId('ajter-nombre'), 'mercadona ');
  fireEvent.press(screen.getByTestId('ajter-nat-EMPRESA'));
  await pulsar('ajter-guardar');
  expect(within(screen.getByTestId('ajter-duplicado-aviso')).getByText(TEXTO_DUPLICADO)).toBeTruthy();
  expect(screen.getByTestId('ajter-reactivar-candidato')).toBeTruthy();
  expect(f.cliente.altaTercero).not.toHaveBeenCalled();
  await pulsar('ajter-crear-otro');
  expect(f.cliente.altaTercero).toHaveBeenCalledWith({ id: '00000000-0000-4000-8000-000000000001', nombre: 'mercadona', naturaleza: 'EMPRESA' });
  expect(await screen.findByTestId('pantalla-terceros')).toBeTruthy();
  expect(f.st.terceros).toHaveLength(2); // homónimos válidos
});

test('Terceros S02: edición con el texto de la lámina, VERSION_DESFASADA recarga y avisa; desactivar y reactivar', async () => {
  const f = fake({ terceros: [ter({ id: 't1', nombre: 'ALDI' })] });
  await abrir(f.cliente, 'terceros');
  await pulsar('ajter-fila-t1');
  expect(screen.getByText(TEXTO_S02)).toBeTruthy();
  f.st.terceros = [ter({ id: 't1', nombre: 'ALDI Sur', row_version: 2 })]; // otra sesión lo cambió
  fireEvent.changeText(screen.getByTestId('ajter-nombre'), 'Aldi');
  await pulsar('ajter-guardar');
  expect(within(screen.getByTestId('ajter-aviso')).getByText(TEXTO_VERSION)).toBeTruthy();
  expect(screen.getByTestId('ajter-nombre').props.value).toBe('ALDI Sur');
  expect(f.cliente.editarTercero).toHaveBeenCalledTimes(1); // sin reintento automático
  await pulsar('ajter-desactivar');
  expect(f.cliente.desactivarTercero).toHaveBeenCalledWith('t1', 2);
  expect(screen.getByTestId('ajter-reactivar')).toBeTruthy();
  await pulsar('ajter-reactivar');
  expect(f.cliente.reactivarTercero).toHaveBeenCalledWith('t1', 3);
});

// ------------------------------------------------------------------ Contextos
test('Contextos S03/C01: texto, filas, alta sin tipo preseleccionado y con fechas; desactivar', async () => {
  const f = fake({ contextos: [ctx({ id: 'c1', nombre: 'Finde Cartagena', fecha_inicio: '2026-10-10', fecha_fin: '2026-10-12' })] });
  await abrir(f.cliente, 'contextos');
  await screen.findByTestId('ajctx-fila-c1');
  expect(screen.getByText(TEXTO_CONTEXTO)).toBeTruthy();
  expect(screen.getByTestId('ajctx-fila-c1-detalle').props.children).toBe('Viaje · 10–12 oct');
  await pulsar('ajctx-nuevo');
  for (const t of ['VIAJE', 'REFORMA', 'EVENTO', 'SOCIAL', 'PROYECTO', 'OTRO']) expect(screen.getByTestId(`ctx-tipo-${t}`).props.accessibilityState.checked).toBe(false);
  fireEvent.changeText(screen.getByTestId('ctx-nombre'), 'Reforma baño');
  expect(screen.getByTestId('ctx-guardar').props.accessibilityState.disabled).toBe(true); // falta tipo
  fireEvent.press(screen.getByTestId('ctx-tipo-REFORMA'));
  fireEvent.changeText(screen.getByTestId('ctx-desde'), '12/10/2026');
  fireEvent.changeText(screen.getByTestId('ctx-hasta'), '10/10/2026');
  await pulsar('ctx-guardar');
  expect(screen.getByTestId('ctx-aviso')).toBeTruthy(); // «Hasta» anterior a «Desde»
  expect(f.cliente.altaContexto).not.toHaveBeenCalled();
  fireEvent.changeText(screen.getByTestId('ctx-hasta'), '20/10/2026');
  await pulsar('ctx-guardar');
  expect(f.cliente.altaContexto).toHaveBeenCalledWith({ id: '00000000-0000-4000-8000-000000000001', nombre: 'Reforma baño', tipo_contexto: 'REFORMA', fecha_inicio: '2026-10-12', fecha_fin: '2026-10-20' });
  await screen.findByTestId('pantalla-contextos');
  await pulsar('ajctx-fila-c1');
  await pulsar('ajctx-desactivar');
  expect(f.cliente.desactivarContexto).toHaveBeenCalledWith('c1', 1);
  await waitFor(() => expect(screen.getByTestId('ajctx-reactivar')).toBeTruthy());
});

// ------------------------------------------------------------------ Plantillas
test('Plantillas S01: texto, grupos «EN INICIO · n DE 3» / otras / desactivadas, resumen y «No disponible»', async () => {
  const f = fake({
    plantillas: [
      plt({ id: 'p1', nombre: 'Súper semanal', categoria_id: 'super', cuenta_default_id: TARJETA, presupuestable_default: true }),
      plt({ id: 'p2', nombre: 'Gasolina', presupuestable_default: false, avisos: [{ campo: 'cuenta', motivo: 'NO_ELEGIBLE' }], cuenta_default_id: 'otra' }),
      plt({ id: 'p3', nombre: 'Vieja', enabled: false, presupuestable_default: true }),
    ],
    acciones: [acc({ id: 'a1', plantilla_registro_id: 'p1', nombre: 'Súper' })],
  });
  await abrir(f.cliente, 'plantillas');
  await screen.findByTestId('ajplt-grupo-inicio');
  expect(screen.getByText(TEXTO_INTRO_PLANTILLAS)).toBeTruthy();
  expect(screen.getByTestId('ajplt-grupo-inicio-titulo').props.children).toBe('EN INICIO · 1 DE 3');
  expect(screen.getByTestId('ajplt-fila-p1-detalle').props.children).toBe('Supermercado · Tarjeta BBVA · Presupuesto: Sí');
  expect(within(screen.getByTestId('ajplt-grupo-otras')).getByTestId('ajplt-fila-p2-no-disponible')).toBeTruthy();
  expect(within(screen.getByTestId('ajplt-grupo-desactivadas')).getByTestId('ajplt-fila-p3')).toBeTruthy();
});

test('Plantillas S02: alta con tipo, categoría filtrada por tipo y acceso en Inicio; nombre nunca autocompletado', async () => {
  const f = fake();
  await abrir(f.cliente, 'plantillas');
  await pulsar('ajplt-nueva'); // ids: plantilla …0001, acceso …0002
  expect(screen.getByTestId('ajplt-nombre').props.value).toBe('');
  expect(screen.getByTestId('ajplt-guardar').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('ajplt-falta').props.children).toBe('Falta: nombre y tipo');
  fireEvent.changeText(screen.getByTestId('ajplt-nombre'), 'Nómina');
  fireEvent.press(screen.getByTestId('ajplt-tipo-INGRESO'));
  fireEvent.press(screen.getByTestId('ajplt-categoria'));
  const sel = within(screen.getByTestId('ajplt-selector'));
  expect(sel.queryByTestId('cat-alim')).toBeNull(); // solo gastos: oculta en ingresos
  fireEvent.press(sel.getByTestId('cat-trabajo'));
  fireEvent.press(sel.getByTestId('cat-nomina'));
  fireEvent.press(screen.getByTestId('ajplt-inicio-true'));
  expect(screen.getByTestId('ajplt-huecos').props.children).toBe('Quedan 3 huecos libres');
  fireEvent.changeText(screen.getByTestId('ajplt-nombre-corto'), 'Nómina');
  await pulsar('ajplt-guardar');
  expect(f.cliente.altaPlantilla).toHaveBeenCalledWith({
    id: '00000000-0000-4000-8000-000000000001', nombre: 'Nómina', tipo_hecho_id: TIPOS.INGRESO, categoria_id: 'nomina', tercero_id: null, entidad_id: null,
    cuenta_default_id: null, presupuestable_default: null,
  });
  expect(f.cliente.altaAccion).toHaveBeenCalledWith({ id: '00000000-0000-4000-8000-000000000002', plantilla_registro_id: '00000000-0000-4000-8000-000000000001', nombre: 'Nómina', icono_key: null });
  expect(await screen.findByTestId('ajplt-detalle')).toBeTruthy();
  expect(screen.getByTestId('ajplt-det-inicio-valor').props.children).toBe('Sí · posición 1');
});

test('Plantillas S04 nombre repetido con «Ir a la plantilla»; S03 límite con «Elegir cuál quitar»', async () => {
  const f = fake({
    plantillas: [plt({ id: 'p1', nombre: 'Súper semanal', presupuestable_default: true }), plt({ id: 'q1', nombre: 'A', presupuestable_default: true }),
      plt({ id: 'q2', nombre: 'B', presupuestable_default: true }), plt({ id: 'q3', nombre: 'C', presupuestable_default: true })],
    acciones: [acc({ id: 'a1', plantilla_registro_id: 'q1', orden: 0 }), acc({ id: 'a2', plantilla_registro_id: 'q2', orden: 1 }), acc({ id: 'a3', plantilla_registro_id: 'q3', orden: 2 })],
  });
  await abrir(f.cliente, 'plantillas');
  await pulsar('ajplt-nueva');
  fireEvent.changeText(screen.getByTestId('ajplt-nombre'), 'súper semanal');
  fireEvent.press(screen.getByTestId('ajplt-tipo-GASTO'));
  fireEvent.press(screen.getByTestId('ajplt-presu-true'));
  await pulsar('ajplt-guardar');
  expect(screen.getByText('Ya tienes una plantilla «súper semanal». Usa otro nombre o edita la existente.')).toBeTruthy();
  await pulsar('ajplt-form-ir');
  expect(screen.getByTestId('ajplt-detalle')).toBeTruthy();
  await pulsar('ajplt-detalle-atras');
  await pulsar('ajplt-nueva');
  fireEvent.changeText(screen.getByTestId('ajplt-nombre'), 'Cuarta');
  fireEvent.press(screen.getByTestId('ajplt-tipo-GASTO'));
  fireEvent.press(screen.getByTestId('ajplt-presu-false'));
  fireEvent.press(screen.getByTestId('ajplt-inicio-true'));
  expect(screen.getByTestId('ajplt-huecos').props.children).toBe('Inicio está completo');
  await pulsar('ajplt-guardar');
  expect(screen.getByText(TEXTO_LIMITE)).toBeTruthy();
  expect(f.st.plantillas.some((x) => x.nombre === 'Cuarta')).toBe(true); // la plantilla queda guardada
  await pulsar('ajplt-form-elegir-quitar');
  expect(screen.getByTestId('pantalla-plantillas')).toBeTruthy();
});

test('Plantillas S05: detalle y desactivar (sale de Inicio; al reactivar no vuelve sola)', async () => {
  const f = fake({ plantillas: [plt({ id: 'p1', nombre: 'Súper', categoria_id: 'super' })], acciones: [acc({ id: 'a1', plantilla_registro_id: 'p1' })] });
  await abrir(f.cliente, 'plantillas');
  await pulsar('ajplt-fila-p1');
  expect(screen.getByTestId('ajplt-det-categoria-valor').props.children).toBe('Alimentación › Supermercado');
  await pulsar('ajplt-desactivar');
  expect(f.cliente.desactivarPlantilla).toHaveBeenCalledWith('p1', 1);
  expect(screen.getByTestId('ajplt-det-inicio-valor').props.children).toBe('No');
  expect(screen.getByText('Desactivada: deja de usarse y sale de Inicio. Si la reactivas, no vuelve a Inicio sola; actívalo tú.')).toBeTruthy();
});

// ------------------------------------------------------------------ Onboarding
test('O01/O02: sin categorías se ofrece el árbol sugerido; con alguna, nunca', async () => {
  const f = fake({ arbol: [] });
  f.cliente.categoriasSugeridas = jest.fn(async () => ({
    tipo: 'OK', datos: { version: 1, nodos: [
      { ruta: 'hogar', nombre: 'Hogar', nivel: 1, padre: null, orden: 0, ambito: 'GASTO', presupuestable_default: true, icon_key: 'hogar.casa' },
      { ruta: 'hogar/luz', nombre: 'Luz', nivel: 2, padre: 'hogar', orden: 0, ambito: 'GASTO', presupuestable_default: true, icon_key: 'hogar.luz' },
    ] },
  }) as any);
  f.cliente.onboardingCategorias = jest.fn(async () => ({ tipo: 'OK', datos: { creadas: 2, idempotente: false } }) as any);
  await abrir(f.cliente, 'categorias');
  expect(await screen.findByTestId('onboarding-oferta')).toBeTruthy();
  expect(screen.getByText(TEXTO_O01)).toBeTruthy();
  await pulsar('onboarding-sugeridas');
  expect(await screen.findByText(textoO02(1))).toBeTruthy();
  await pulsar('onboarding-crear');
  expect(f.cliente.onboardingCategorias).toHaveBeenCalledTimes(1);
});

test('O01: con categorías no se ofrece; «Empezar desde cero» deja el estado vacío habitual', async () => {
  const f = fake();
  await abrir(f.cliente, 'categorias');
  await screen.findByTestId('fila-alim');
  expect(screen.queryByTestId('onboarding-oferta')).toBeNull();
  const g = fake({ arbol: [] });
  screen.unmount();
  await abrir(g.cliente, 'categorias');
  await pulsar('onboarding-desde-cero');
  expect(screen.queryByTestId('onboarding-oferta')).toBeNull();
  expect(screen.getByTestId('nueva-categoria')).toBeTruthy();
});
