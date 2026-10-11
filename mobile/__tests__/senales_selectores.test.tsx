// ============================================================
// GAPTO MOBILE 2027
// Fichero: senales_selectores.test.tsx
// Ruta: mobile/__tests__/senales_selectores.test.tsx
// Descripción: K3 de F05-05 (§2.1–§2.4; F05 §49.4 A1–A5, §49.5 R1/R2/R4; lámina SRCH-ACT-AFI v0.2 A1–A8). Dominios SEÑALES, BÚSQUEDA y AFINIDADES en el cliente. Casos de §49.9: 1 (afinidad primero con su motivo), 3 (sugerida, chip y árbol → MISMA intención sellada), 8 («super» y «súper»), 10 («Recordar»: doble toque idempotente y fallo sin afectar al hecho), 21 (chip sin tocar: PENDIENTE y «Registrar» sin habilitar), 34 (búsqueda de terceros en el servidor con «garcía») y homónimos por naturaleza y uso; «Recientes» con su motivo; inactivo con «Reactivar» en línea.
// Versión: 0.1.0 (F05-05 K3 §2.1–§2.4)
// Versión: 0.3.0 (F05-05 K3 §3, mutante SE19): con fecha futura no se piden sugerencias ni salen chips (R7).
// Versión: 0.2.0 (F05-05 K3 §3; casos 6, 7 y 29 de §49.9): con la plantilla aplicada las sugerencias no alteran su propuesta ni salen chips; con la preferencia de cuenta del tercero, elegir por chip o por árbol da la MISMA consulta de propuesta y el MISMO payload; cambio de tercero y de tipo; categoría que deja de ser elegible entre carga y confirmación; reintento con el mismo UUID.
// ============================================================

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { textoMotivo, textoReciente, vistaSugeridas } from '../src/domain/senales';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

const ARBOL = [
  nodo({ id: 'alim', nombre: 'Alimentación' }),
  nodo({ id: 'super', nombre: 'Supermercado', parent_id: 'alim', icon_key: 'alimentacion.carrito' }),
  nodo({ id: 'hogar', nombre: 'Hogar', orden: 1 }),
  nodo({ id: 'drogueria', nombre: 'Droguería', parent_id: 'hogar' }),
  nodo({ id: 'ahorro', nombre: 'Ahorro', orden: 2, ambito: 'INGRESO' }),
  nodo({ id: 'superavit', nombre: 'Superávit de ahorro', parent_id: 'ahorro', ambito: 'INGRESO' }),
];

const okGasto = (p: PayloadGastoPagado): Respuesta<ResultadoRegistro> => ({
  tipo: 'OK',
  datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado },
});

const cand = (id: string, nombre: string, ruta: string, motivo: string) => ({ categoria_id: id, nombre, ruta, motivo, fuente: motivo === 'AFINIDAD' ? 'AFINIDAD' : 'HISTORIAL', usos: 1, ultimo_uso: HOY });

function fake(o: { afinidades?: any; alta?: (c: any) => Promise<any> } = {}) {
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: PayloadGastoPagado) => okGasto(p)),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [{ id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', enabled: true, row_version: 1 }] } }) as any),
    senalesCategorias: jest.fn(async (q: any) => ({
      tipo: 'OK',
      datos: {
        tipo: q.tipo, fecha: q.fecha, tercero_id: q.terceroId ?? null,
        candidatas: q.terceroId === 'ter-aldi'
          ? [cand('super', 'Supermercado', 'Alimentación › Supermercado', 'AFINIDAD'), cand('drogueria', 'Droguería', 'Hogar › Droguería', 'FRECUENTE_TERCERO')]
          : [cand('drogueria', 'Droguería', 'Hogar › Droguería', 'RECIENTE')],
      },
    }) as any),
    senalesTerceros: jest.fn(async (tipo: any, fecha: any) => ({
      tipo: 'OK',
      datos: { tipo, fecha, terceros: [
        { tercero_id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', usos: 4, ultimo_uso: '2026-10-08', motivo: 'RECIENTE' },
        { tercero_id: 'ter-iber', nombre: 'Iberdrola', naturaleza: 'EMPRESA', usos: 9, ultimo_uso: '2026-08-01', motivo: 'FRECUENTE_TIPO' },
      ] },
    }) as any),
    afinidadesTercero: jest.fn(async (id: string) => ({ tipo: 'OK', datos: o.afinidades ?? { tercero_id: id, tipo: 'GASTO', guardadas: [], segun_historial: [], total_registros: 0 } }) as any),
    altaAfinidad: jest.fn(o.alta ?? (async (c: any) => ({ tipo: 'OK', datos: { afinidad: c, idempotente: false, aviso: null } }))) as any,
  };
  return cliente;
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

async function montar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await screen.findByTestId('accion-registrar');
  await act(async () => undefined);
}

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

async function abrirGasto(c: ClienteApi) {
  await montar(c);
  await pulsar('accion-registrar');
  await pulsar('tipo-GASTO');
  await waitFor(() => expect(c.senalesCategorias).toHaveBeenCalled());
}

async function elegirAldi() {
  await pulsar('campo-tercero');
  await waitFor(() => expect(screen.getByTestId('tercero-ter-aldi')).toBeTruthy());
  await pulsar('tercero-ter-aldi');
  await waitFor(() => expect(screen.getByTestId('chip-sugerida-super')).toBeTruthy());
}

async function completarYRegistrar(c: ClienteApi) {
  fireEvent.changeText(screen.getByTestId('campo-importe'), '48,72');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`)).toBeTruthy());
  fireEvent.press(screen.getByTestId(`cuenta-${TARJETA}`));
  await pulsar('registrar');
  await waitFor(() => expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1));
  return (c.registrarGastoPagado as jest.Mock).mock.calls[0][0] as PayloadGastoPagado;
}

// ------------------------------------------------------------------ dominio de señales (R4)
test('R4: textos del vocabulario cerrado y «Recientes»', () => {
  expect(textoMotivo('AFINIDAD', { tercero: 'ALDI', tipo: 'GASTO' })).toBe('La guardaste para ALDI');
  expect(textoMotivo('FRECUENTE_TERCERO', { tercero: 'ALDI', tipo: 'GASTO' })).toBe('Sueles usarla con ALDI');
  expect(textoMotivo('FRECUENTE_TIPO', { tercero: null, tipo: 'INGRESO' })).toBe('Frecuente en tus ingresos');
  expect(textoMotivo('RECIENTE', { tercero: null, tipo: 'GASTO' })).toBe('Usada recientemente');
  const r = { tercero_id: 't', nombre: 'ALDI', naturaleza: null, usos: 1, ultimo_uso: '2026-10-08', motivo: 'RECIENTE' as const };
  expect(textoReciente(r, HOY, 'GASTO')).toBe('Usado hace 2 días');
  expect(textoReciente({ ...r, ultimo_uso: HOY }, HOY, 'GASTO')).toBe('Usado hoy');
  expect(textoReciente({ ...r, ultimo_uso: '2026-10-09' }, HOY, 'GASTO')).toBe('Usado ayer');
  expect(textoReciente({ ...r, motivo: 'FRECUENTE_TIPO' }, HOY, 'GASTO')).toBe('Frecuente en tus gastos');
  const v = vistaSugeridas({ tipo: 'GASTO', fecha: HOY, tercero_id: 't', candidatas: [1, 2, 3, 4].map((i) => cand(`c${i}`, `C${i}`, `R${i}`, 'FRECUENTE_TIPO')) as any }, null);
  expect(v.map((x) => x.categoria_id)).toEqual(['c1', 'c2', 'c3']); // hasta 3, en el orden del servidor (R6)
});

// ------------------------------------------------------------------ A1 · selector con «Sugeridas» (caso 1)
test('caso 1 / A1: «Sugeridas» con ruta y motivo encima del árbol; nada queda elegido', async () => {
  const c = fake();
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('campo-categoria');
  const fila = screen.getByTestId('sugerida-super');
  expect(fila.props.accessibilityLabel).toBe('Supermercado. Alimentación › Supermercado. La guardaste para ALDI');
  expect(screen.getByTestId('sugerida-drogueria').props.accessibilityLabel).toContain('Sueles usarla con ALDI');
  expect(fila.props.accessibilityState.selected).toBe(false);
  expect(screen.getByText('Todas')).toBeTruthy();
  expect(c.senalesCategorias).toHaveBeenLastCalledWith({ tipo: 'GASTO', fecha: HOY, terceroId: 'ter-aldi' });
});

// ------------------------------------------------------------------ A2 bis · chips (caso 21) y R1 (caso 3)
test('caso 21: chip sin tocar → «Elige categoría», estado PENDIENTE y «Registrar» sin habilitar por él', async () => {
  const c = fake();
  await abrirGasto(c);
  await elegirAldi();
  fireEvent.changeText(screen.getByTestId('campo-importe'), '48,72');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  fireEvent.press(screen.getByTestId(`cuenta-${TARJETA}`));
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Elige categoría');
  expect(screen.getByTestId('chip-sugerida-super').props.accessibilityRole).toBe('button');
  expect(screen.getByTestId('chips-texto').props.children).toBe('Sugeridas: Supermercado, la guardaste para ALDI; Droguería, sueles usarla con ALDI. Toca una para elegirla.');
  expect(screen.getByTestId('registrar').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: categoría.');
  expect(screen.queryByTestId('origen-categoria-usuario')).toBeNull();
});

const SELLADA = { estado: 'CATEGORIA', categoria_id: 'super', magnitudes: [] };

async function elegirPor(via: 'chip' | 'sugerida' | 'arbol') {
  if (via === 'chip') await pulsar('chip-sugerida-super');
  if (via === 'sugerida') {
    await pulsar('campo-categoria');
    await pulsar('sugerida-super');
  }
  if (via === 'arbol') {
    await pulsar('campo-categoria');
    await pulsar('cat-alim');
    await pulsar('cat-super');
  }
}

test.each(['chip', 'sugerida', 'arbol'] as const)('caso 3 / R1: elegir por %s sella la MISMA categoría (misma intención)', async (via) => {
  const c = fake();
  await abrirGasto(c);
  await elegirAldi();
  await elegirPor(via);
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Supermercado');
  expect(screen.getByTestId('origen-categoria-usuario').props.children).toBe('Elegida por ti.');
  expect(screen.queryByTestId('chips-sugeridas')).toBeNull();
  const p = await completarYRegistrar(c);
  expect(p.categoria).toEqual(SELLADA);
});

// ------------------------------------------------------------------ A2 · búsqueda en el árbol (caso 8)
test('caso 8 / A2: «super» y «súper» encuentran Supermercado con su ruta; lo no válido para un gasto, atenuado y sin elegir', async () => {
  const c = fake();
  await abrirGasto(c);
  await pulsar('campo-categoria');
  for (const q of ['super', 'súper', 'SUPER']) {
    fireEvent.changeText(screen.getByTestId('selector-busqueda'), q);
    expect(screen.getByTestId('resultado-super').props.accessibilityLabel).toBe('Supermercado. Alimentación › Supermercado');
  }
  const ingreso = screen.queryByTestId('resultado-superavit');
  if (ingreso) {
    expect(ingreso.props.accessibilityState.disabled).toBe(true);
    await act(async () => fireEvent.press(ingreso));
    expect(screen.getByTestId('selector-categorias')).toBeTruthy(); // no se eligió
  }
  expect(screen.getByTestId('selector-busqueda-nota').props.children).toBe('Sin distinguir mayúsculas ni acentos.');
  await pulsar('resultado-super');
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Supermercado');
});

// ------------------------------------------------------------------ A5 · «Recordar» (caso 10)
test('caso 10 / A5: «Recordar» con el par no guardado; doble toque = una sola alta con el mismo UUID', async () => {
  let resolver: (v: any) => void = () => undefined;
  const c = fake({ alta: (cuerpo: any) => new Promise((r) => { resolver = () => r({ tipo: 'OK', datos: { afinidad: cuerpo, idempotente: false, aviso: null } }); }) });
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('chip-sugerida-super');
  await completarYRegistrar(c);
  await waitFor(() => expect(screen.getByTestId('recordar-afinidad')).toBeTruthy());
  expect(screen.getByText('¿Recordar Supermercado para ALDI?')).toBeTruthy();
  expect(screen.getByText('Se sugerirá primero cuando elijas ALDI. Nunca se elegirá sola.')).toBeTruthy();
  await pulsar('recordar');
  await pulsar('recordar');
  expect(c.altaAfinidad).toHaveBeenCalledTimes(1);
  await act(async () => resolver(undefined));
  await waitFor(() => expect(screen.getByTestId('recordar-hecho')).toBeTruthy());
  const llamada = (c.altaAfinidad as jest.Mock).mock.calls[0][0];
  expect(llamada).toEqual({ id: expect.any(String), tercero_id: 'ter-aldi', categoria_id: 'super' });
});

test('caso 10: un fallo de «Recordar» no afecta al hecho; el reintento usa el MISMO UUID', async () => {
  const c = fake({ alta: async () => ({ tipo: 'INDETERMINADO', mensaje: 'x' }) });
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('chip-sugerida-super');
  await completarYRegistrar(c);
  await waitFor(() => expect(screen.getByTestId('recordar')).toBeTruthy());
  await pulsar('recordar');
  await waitFor(() => expect(screen.getByTestId('recordar-error')).toBeTruthy());
  await pulsar('recordar');
  const ids = (c.altaAfinidad as jest.Mock).mock.calls.map((x) => x[0].id);
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
  expect(screen.getByTestId('registro-exito')).toBeTruthy();
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
});

test('A5: con el par ya guardado no se ofrece «Recordar»', async () => {
  const c = fake({ afinidades: { tercero_id: 'ter-aldi', tipo: 'GASTO', guardadas: [{ id: 'a1', categoria_id: 'super', nombre: 'Supermercado', ruta: 'x', disponible: true }], segun_historial: [], total_registros: 0 } });
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('chip-sugerida-super');
  await completarYRegistrar(c);
  await waitFor(() => expect(c.afinidadesTercero).toHaveBeenCalled());
  await act(async () => undefined);
  expect(screen.queryByTestId('recordar-afinidad')).toBeNull();
});

// ------------------------------------------------------------------ A3/A4/A8 · selector de terceros
test('A3: «Recientes» con su motivo y «Todos · N terceros»', async () => {
  const c = fake();
  await abrirGasto(c);
  await pulsar('campo-tercero');
  await waitFor(() => expect(screen.getByTestId('terceros-recientes')).toBeTruthy());
  expect(c.senalesTerceros).toHaveBeenCalledWith('GASTO', HOY);
  expect(screen.getByTestId('reciente-ter-aldi').props.accessibilityLabel).toBe('ALDI. Usado hace 2 días');
  expect(screen.getByTestId('reciente-ter-iber').props.accessibilityLabel).toBe('Iberdrola. Frecuente en tus gastos');
  expect(screen.getByTestId('terceros-todos').props.children).toBe('Todos · 1 tercero');
});

test('caso 34 / A4 / A8: búsqueda en el servidor desde 2 caracteres; homónimos por naturaleza y uso; inactivo con «Reactivar»', async () => {
  const esperar = (ms: number) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });
  {
    const c = fake();
    c.buscarTerceros = jest.fn(async () => ({
      tipo: 'OK',
      datos: { terceros: [
        { id: 'ana1', nombre: 'Ana García', naturaleza: 'PERSONA', enabled: true, row_version: 1, usos: 466, ultimo_uso: '2026-10-10' },
        { id: 'ana2', nombre: 'Ana García', naturaleza: 'PERSONA', enabled: true, row_version: 1, usos: 280, ultimo_uso: '2026-09-02' },
        { id: 'tall', nombre: 'Talleres García S.L.', naturaleza: 'EMPRESA', enabled: false, row_version: 3, usos: 0, ultimo_uso: null },
      ] },
    })) as any;
    c.reactivarTercero = jest.fn(async (id: string, rv: number) => ({ tipo: 'OK', datos: { tercero: { id, nombre: 'Talleres García S.L.', naturaleza: 'EMPRESA', enabled: true, row_version: rv + 1 }, idempotente: false, modificadas: [id] } })) as any;
    await abrirGasto(c);
    await pulsar('campo-tercero');
    fireEvent.changeText(screen.getByTestId('tercero-filtro'), 'g');
    await esperar(400);
    expect(c.buscarTerceros).not.toHaveBeenCalled(); // menos de 2 caracteres: filtro local
    fireEvent.changeText(screen.getByTestId('tercero-filtro'), 'garcía');
    await esperar(400);
    await waitFor(() => expect(c.buscarTerceros).toHaveBeenCalledWith('garcía', true));
    await waitFor(() => expect(screen.getByTestId('tercero-ana1')).toBeTruthy());
    expect(screen.getByTestId('tercero-ana1').props.accessibilityLabel).toBe('Ana García. Persona · 466 registros · último 10 oct');
    expect(screen.getByTestId('tercero-ana2').props.accessibilityLabel).toBe('Ana García. Persona · 280 registros · último 2 sep');
    expect(screen.getByTestId('tercero-inactivo-tall')).toBeTruthy();
    expect(screen.getByTestId('texto-inactivo-busqueda')).toBeTruthy();
    await pulsar('reactivar-tall');
    expect(c.reactivarTercero).toHaveBeenCalledWith('tall', 3);
    await waitFor(() => expect(screen.getByTestId('tercero-valor').props.children).toBe('Talleres García S.L.'));
  }
});

// ------------------------------------------------------------------ casos 6, 7 y 29 (R1 frente a plantilla, preferencia y cambios)
const EFECTIVO = 'c0000000-0000-4000-8000-00000000000e';
const SIN_CAMPOS = { categoria: null, tercero: null, contexto: null, cuenta: null, presupuestable: null };
const ORIGEN_PLT = { capa: 'PLANTILLA', plantilla_id: 'p1', preferencia_id: null };
const PLT = {
  id: 'p1', nombre: 'Súper semanal', tipo_hecho_id: 'tipo-gasto', categoria_id: 'super', tercero_id: 'ter-aldi', entidad_id: null,
  cuenta_default_id: TARJETA, presupuestable_default: null, enabled: true, row_version: 1, tipo: 'GASTO', avisos: [],
};

function conDosCuentas(c: ClienteApi) {
  c.cuentasPago = jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [
    { cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
    { cuenta_id: EFECTIVO, nombre: 'Efectivo', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
  ] } }) as Respuesta<{ cuentas: CuentaPago[] }>);
  return c;
}

const seleccionada = (id: string) => screen.getByTestId(id).props.accessibilityState?.checked === true;
const enviados = (c: ClienteApi) => (c.registrarGastoPagado as jest.Mock).mock.calls.map((x) => x[0] as PayloadGastoPagado);
const sinId = (p: PayloadGastoPagado) => ({ ...p, intencion_id: '' });

test('caso 6 / 29: con la plantilla aplicada, las sugerencias no alteran su propuesta (categoría, tercero y cuenta) ni salen chips', async () => {
  const c = fake();
  c.listarPlantillas = jest.fn(async () => ({ tipo: 'OK', datos: { plantillas: [PLT], acciones: [
    { id: 'a1', nombre: 'Súper', plantilla_registro_id: 'p1', orden: 0, icono_key: null, enabled: true, row_version: 1 }] } })) as any;
  c.propuestaRegistro = jest.fn(async (q: any) => ({ tipo: 'OK', datos: { tipo: q.tipo, avisos: [], campos: q.plantillaId
    ? { categoria: { valor: 'super', origen: ORIGEN_PLT }, tercero: { valor: 'ter-aldi', origen: ORIGEN_PLT }, contexto: null, cuenta: { valor: TARJETA, origen: ORIGEN_PLT }, presupuestable: null }
    : SIN_CAMPOS } })) as any;
  await montar(c);
  await pulsar('acceso-a1');
  await screen.findByTestId('chip-plantilla');
  await waitFor(() => expect(screen.getByTestId('categoria-valor').props.children).toBe('Supermercado'));
  await waitFor(() => expect(c.senalesCategorias).toHaveBeenLastCalledWith({ tipo: 'GASTO', fecha: HOY, terceroId: 'ter-aldi' }));
  await act(async () => undefined);
  expect(screen.getByTestId('origen-categoria').props.children).toBe('De tu plantilla Súper semanal.');
  expect(screen.getByTestId('origen-cuenta').props.children).toBe('De tu plantilla Súper semanal.');
  expect(screen.queryByTestId('chips-sugeridas')).toBeNull(); // la categoría no está pendiente
  for (const [q] of (c.propuestaRegistro as jest.Mock).mock.calls) {
    expect(Object.keys(q).some((k) => /senal|suger|candidat/i.test(k))).toBe(false); // las señales no viajan al resolver
  }
  fireEvent.changeText(screen.getByTestId('campo-importe'), '48,72');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await pulsar('registrar');
  await waitFor(() => expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1));
  const p = enviados(c)[0];
  expect(p.categoria).toEqual(SELLADA);
  expect(p.cuenta_id).toBe(TARJETA);
});

// Consulta de propuesta y payload capturados por vía (caso 7): se comparan en el test siguiente.
const PORVIA: Record<string, { consulta: any; payload: PayloadGastoPagado }> = {};

test.each(['chip', 'arbol'] as const)('caso 7 / 29: preferencia de cuenta del tercero vigente; elegir por %s no cambia la cuenta propuesta', async (via) => {
  const c = conDosCuentas(fake());
  const pref = { capa: 'PREFERENCIA', preferencia_id: 'pref-aldi', plantilla_id: null };
  c.listarPreferencias = jest.fn(async () => ({ tipo: 'OK', datos: { tipos: { GASTO: 't-gasto', INGRESO: 't-ingreso' }, preferencias: [{
    id: 'pref-aldi', tipo_hecho_id: 't-gasto', categoria_id: null, tercero_id: 'ter-aldi', entidad_id: null, cuenta_default_id: EFECTIVO,
    presupuestable_default: null, prioridad: 100, enabled: true, row_version: 1 }] } })) as any;
  c.propuestaRegistro = jest.fn(async (q: any) => ({ tipo: 'OK', datos: { tipo: q.tipo, avisos: [], campos: q.terceroId === 'ter-aldi'
    ? { ...SIN_CAMPOS, cuenta: { valor: EFECTIVO, origen: pref } } : SIN_CAMPOS } })) as any;
  await abrirGasto(c);
  await elegirAldi();
  await waitFor(() => expect(seleccionada(`cuenta-${EFECTIVO}`)).toBe(true));
  await elegirPor(via);
  await act(async () => undefined);
  expect(seleccionada(`cuenta-${EFECTIVO}`)).toBe(true); // la señal no toca la cuenta propuesta
  fireEvent.changeText(screen.getByTestId('campo-importe'), '48,72');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await pulsar('registrar');
  await waitFor(() => expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1));
  const llamadas = (c.propuestaRegistro as jest.Mock).mock.calls;
  PORVIA[via] = { consulta: llamadas[llamadas.length - 1][0], payload: enviados(c)[0] };
  expect(PORVIA[via].payload.cuenta_id).toBe(EFECTIVO);
  expect(PORVIA[via].payload.categoria).toEqual(SELLADA);
});

test('caso 7 / R1: por chip y por árbol, la MISMA consulta de propuesta y el MISMO payload (salvo el UUID)', () => {
  expect(PORVIA.chip && PORVIA.arbol).toBeTruthy();
  expect(PORVIA.chip.consulta).toEqual(PORVIA.arbol.consulta);
  expect(sinId(PORVIA.chip.payload)).toEqual(sinId(PORVIA.arbol.payload));
});

test('caso 29: cambio de tercero → nuevas sugerencias, la categoría sigue PENDIENTE y el chip sella la misma intención que el árbol', async () => {
  const c = fake();
  c.listarTerceros = jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [
    { id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', enabled: true, row_version: 1 },
    { id: 'ter-otro', nombre: 'Droguería Paqui', naturaleza: 'EMPRESA', enabled: true, row_version: 1 }] } })) as any;
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('campo-tercero');
  await waitFor(() => expect(screen.getByTestId('tercero-ter-otro')).toBeTruthy());
  await pulsar('tercero-ter-otro');
  await waitFor(() => expect(c.senalesCategorias).toHaveBeenLastCalledWith({ tipo: 'GASTO', fecha: HOY, terceroId: 'ter-otro' }));
  await waitFor(() => expect(screen.queryByTestId('chip-sugerida-super')).toBeNull());
  expect(screen.getByTestId('chip-sugerida-drogueria')).toBeTruthy();
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Elige categoría');
  await pulsar('chip-sugerida-drogueria');
  const p = await completarYRegistrar(c);
  expect(p.categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'drogueria', magnitudes: [] });
  expect(p.tercero_id).toBe('ter-otro');
});

test('caso 29: cambio de tipo antes del envío → las sugerencias se piden para el nuevo tipo y ninguna incompatible sale como chip', async () => {
  const c = fake();
  await abrirGasto(c);
  await waitFor(() => expect(screen.getByTestId('chip-sugerida-drogueria')).toBeTruthy());
  await pulsar('cambiar-tipo');
  await pulsar('tipo-INGRESO');
  await waitFor(() => expect(c.senalesCategorias).toHaveBeenLastCalledWith(expect.objectContaining({ tipo: 'INGRESO' })));
  await act(async () => undefined);
  expect(screen.queryByTestId('chip-sugerida-drogueria')).toBeNull(); // Droguería es de gasto: no es elegible en un ingreso
});

test('caso 29: la categoría deja de ser elegible entre la carga y la confirmación → rechazo visible, sin reenvío ni sustitución por otra sugerencia', async () => {
  const c = fake();
  c.registrarGastoPagado = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'CATEGORIA_NO_ELEGIBLE', mensaje: 'x' })) as any;
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('chip-sugerida-super');
  const p = await completarYRegistrar(c);
  expect(p.categoria).toEqual(SELLADA);
  expect(await screen.findByTestId('categoria-invalida')).toBeTruthy();
  await act(async () => undefined);
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Elige otra categoría');
});

test('caso 29: reintento tras un resultado indeterminado → el MISMO UUID y la MISMA categoría elegida por chip', async () => {
  let k = 0;
  const c = fake();
  c.registrarGastoPagado = jest.fn(async (p: PayloadGastoPagado) => (++k === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : okGasto(p))) as any;
  await abrirGasto(c);
  await elegirAldi();
  await pulsar('chip-sugerida-super');
  await completarYRegistrar(c);
  await screen.findByTestId('estado-indeterminado');
  await pulsar('reintentar');
  await screen.findByTestId('registro-exito');
  const [a, b] = enviados(c);
  expect(b).toEqual(a);
  expect(b.categoria).toEqual(SELLADA);
});

test('R7: con una fecha futura no se piden sugerencias ni salen chips', async () => {
  const c = fake();
  await abrirGasto(c);
  await waitFor(() => expect(screen.getByTestId('chip-sugerida-drogueria')).toBeTruthy());
  const antes = (c.senalesCategorias as jest.Mock).mock.calls.length;
  await pulsar('fecha-otra');
  await act(async () => fireEvent.changeText(screen.getByTestId('campo-fecha'), '12/10/2026'));
  await act(async () => undefined);
  expect((c.senalesCategorias as jest.Mock).mock.calls.slice(antes).some(([q]) => q.fecha > HOY)).toBe(false);
  expect(screen.queryByTestId('chips-sugeridas')).toBeNull();
});