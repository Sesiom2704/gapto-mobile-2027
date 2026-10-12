// ============================================================
// GAPTO MOBILE 2027
// Fichero: actividad_inicio.test.tsx
// Ruta: mobile/__tests__/actividad_inicio.test.tsx
// Descripción: K3 de F05-05 (§2.5–§2.8; F05 §49.4 A7–A9/A12, §49.5 R11/R12; lámina SRCH-ACT-AFI v0.2 B1–B13, C1–C4, E1). Dominios ACTIVIDAD, AFINIDADES (Ajustes), RESULTADO y TRANSVERSAL (A12). Casos de §49.9: 12 (orden por fecha, transferencia neutra, ingresos con «+»), 14 (título nunca vacío), 15 (maestro desactivado marcado), 16 (cancelar la búsqueda restaura periodo y filtros), 17 (sin «tu parte» inventada), 22 («Ver sus registros» y «Limpiar»), 23 (fallo de red → error con «Reintentar», nunca «No hay registros»), 24 (importe «48,72» y «48.72»), 25/27 (Resultado con «Sin indicar» y «Hola»); detalle de gasto, ingreso y transferencia; filtros con recuento de grupos; «Quitar» con confirmación, «No disponible», «Ya es habitual» y «Guardar» del historial.
// Versión: 0.1.0 (F05-05 K3 §2.5–§2.8)
// Versión: 0.3.0 (F05-05 K4-E, huecos A7 de la matriz A/R): hojas «Otro mes» (mes elegido → desde/hasta del mes) y «Entre fechas» (hasta inclusivo → día siguiente en la consulta; desde > hasta bloqueado); filtros de categoría padre (con subcategorías: el cliente no envía incluir_subcategorias=false), tercero y contexto en la consulta.
// Versión: 0.4.0 (F05-06 K-7; F05 §51.8, F09 §12.104 B1/B4): icono de la categoría en la fila y en la cabecera del detalle (`categoria.icon_key` → `IconoCategoriaVista`); transferencia con el icono de intercambio; «Varias» y sin categoría con el de reserva.
// Versión: 0.2.0 (F05-05 K4-C; acta K4-A2 P12, caso 16 / DAY-Q08): «Cancelar» la búsqueda restaura el desplazamiento SOLO cuando la lista posterior ya está cargada (nunca durante «CARGANDO»); sin búsqueda previa no se desplaza.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, DetalleActividad, FilaActividad } from '../src/api/cliente';
import { consulta, importeDeBusqueda, SIN_FILTROS, tituloFila } from '../src/domain/actividad';
import { textoSinIndicar } from '../src/domain/inicio';
import { categoriaIconoFallback, glifoDe } from '../src/theme/iconosCategoria';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

function fila(p: Partial<FilaActividad> & { id: string }): FilaActividad {
  return {
    fecha_hecho: HOY, tipo: 'GASTO', nota: null, moneda: 'EUR', importe_total: '10.00', tercero: null, categoria: null, varias: false,
    contexto: null, cuentas: [{ cuenta_id: 'cta', nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA',
    tu_parte: '10.00', pendiente: null, maestros_desactivados: [], ...p,
  };
}

const FILAS: FilaActividad[] = [
  fila({ id: 'g1', nota: 'Compra semanal', importe_total: '48.72', tu_parte: '48.72',
    tercero: { id: 'ter-aldi', nombre: 'ALDI', enabled: true }, categoria: { id: 'super', nombre: 'Supermercados', ruta: 'Alimentación › Supermercados', enabled: true } }),
  fila({ id: 't1', tipo: 'TRANSFERENCIA', importe_total: '500.00', estado_reparto: null, tu_parte: null,
    cuentas: [{ cuenta_id: 'a', nombre: 'Cuenta nómina', rol: 'ORIGEN', enabled: true }, { cuenta_id: 'b', nombre: 'Ahorro', rol: 'DESTINO', enabled: true }] }),
  fila({ id: 'i1', tipo: 'INGRESO', fecha_hecho: '2026-10-09', importe_total: '2100.00', tu_parte: '2100.00',
    tercero: { id: 'emp', nombre: 'Empresa SL', enabled: true }, categoria: { id: 'nom', nombre: 'Nómina', ruta: 'Ingresos laborales › Nómina', enabled: true },
    cuentas: [{ cuenta_id: 'a', nombre: 'Cuenta nómina', rol: 'COBRO', enabled: true }] }),
  fila({ id: 'g2', fecha_hecho: '2026-10-09', importe_total: '4.00', tu_parte: '4.00', cuentas: [{ cuenta_id: 'e', nombre: 'Efectivo', rol: 'PAGO', enabled: true }] }),
  fila({ id: 'g3', fecha_hecho: '2026-10-09', importe_total: '44.50', estado_reparto: 'NO_DISPONIBLE', tu_parte: null, nota: 'Cena con amigos',
    tercero: { id: 'tag', nombre: 'La Tagliatella', enabled: true }, categoria: { id: 'rest', nombre: 'Restaurantes', ruta: 'Ocio › Restaurantes', enabled: true },
    contexto: { id: 'ctx', nombre: 'Cumpleaños Tania', enabled: true } }),
  fila({ id: 'g4', fecha_hecho: '2026-10-02', importe_total: '9.60', tercero: { id: 'fp', nombre: 'Fruterías Paco', enabled: true },
    categoria: { id: 'fru', nombre: 'Fruta y verdura', ruta: 'Alimentación › Fruta y verdura', enabled: false }, maestros_desactivados: ['CATEGORIA'] }),
];

function fake(o: { actividad?: (q: any) => any; detalle?: (id: string) => any; afinidades?: any } = {}) {
  const cliente: ClienteApi = {
    ...clienteCategoriasStub([nodo({ id: 'alim', nombre: 'Alimentación' }), nodo({ id: 'super', nombre: 'Supermercados', parent_id: 'alim' }),
      nodo({ id: 'hogar', nombre: 'Hogar', orden: 1 }), nodo({ id: 'limp', nombre: 'Limpieza', parent_id: 'hogar' })]),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    actividad: jest.fn(async (q: any) => o.actividad?.(q) ?? ({ tipo: 'OK', datos: { filas: FILAS, siguiente: null, total: FILAS.length } })) as any,
    detalleActividad: jest.fn(async (id: string) => o.detalle?.(id) ?? ({ tipo: 'OK', datos: { ...FILAS.find((f) => f.id === id)!, presupuestable: true, magnitudes: [] } as DetalleActividad })) as any,
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [{ id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', enabled: true, row_version: 1, usos: 41, ultimo_uso: HOY }] } }) as any),
    afinidadesTercero: jest.fn(async () => ({ tipo: 'OK', datos: o.afinidades ?? {
      tercero_id: 'ter-aldi', tipo: 'GASTO', total_registros: 41,
      guardadas: [{ id: 'af1', categoria_id: 'super', nombre: 'Supermercados', ruta: 'Alimentación › Supermercados', disponible: true },
        { id: 'af2', categoria_id: 'limp', nombre: 'Limpieza', ruta: 'Hogar › Limpieza', disponible: false }],
      segun_historial: [{ categoria_id: 'drog', nombre: 'Droguería', ruta: 'Hogar › Droguería', usos: 7 }],
    } }) as any),
    altaAfinidad: jest.fn(async (c: any) => ({ tipo: 'OK', datos: { afinidad: c, idempotente: false, aviso: null } })) as any,
    retirarAfinidad: jest.fn(async () => ({ tipo: 'OK', datos: { afinidad: null, idempotente: false, aviso: null } })) as any,
    yo: jest.fn(async () => ({ tipo: 'OK', datos: { nombre: 'Moisés' } })) as any,
    resultadoMes: jest.fn(async () => ({ tipo: 'OK', datos: { mes: '2026-10', moneda: 'EUR', ingresos_propios: '7784.04', gastos_propios: '3339.91', resultado: '4444.13',
      sin_indicar: { gastos: { n: 7, importe: '700.35' }, ingresos: { n: 2, importe: '2781.96' } } } })) as any,
  };
  return cliente;
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

async function montar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

async function irADia(c: ClienteApi) {
  await montar(c);
  await pulsar('tab-DIA');
  await waitFor(() => expect(screen.getByTestId('fila-g1')).toBeTruthy());
}

const esperar = (ms: number) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });

// ------------------------------------------------------------------ dominio
test('dominio: importe en la búsqueda («48,72», «48.72») y consulta con todo el historial al buscar', () => {
  expect(importeDeBusqueda('48,72')).toBe('48.72');
  expect(importeDeBusqueda('48.72')).toBe('48.72');
  expect(importeDeBusqueda('aldi')).toBeNull();
  expect(consulta({ tipo: 'ESTE_MES' }, SIN_FILTROS, HOY, null)).toMatchObject({ desde: '2026-10-01', hasta: '2026-11-01', q: null, importe: null });
  expect(consulta({ tipo: 'ESTE_MES' }, SIN_FILTROS, HOY, '48,72')).toMatchObject({ desde: null, hasta: null, q: null, importe: '48.72' });
  expect(consulta({ tipo: 'MES_ANTERIOR' }, SIN_FILTROS, HOY, null)).toMatchObject({ desde: '2026-09-01', hasta: '2026-10-01' });
  expect(consulta({ tipo: 'ENTRE_FECHAS', desde: '2026-09-05', hasta: '2026-09-30' }, SIN_FILTROS, HOY, null)).toMatchObject({ desde: '2026-09-05', hasta: '2026-10-01' });
});

test('caso 14: el título calculado nunca sale vacío ni «null»', () => {
  expect(tituloFila(fila({ id: 'x', importe_total: '4.00' }))).toBe('Gasto · 4,00 €');
  expect(tituloFila(fila({ id: 'x', nota: '  ' , tercero: { id: 't', nombre: 'ALDI', enabled: true } }))).toBe('ALDI');
  expect(tituloFila(fila({ id: 'x', nota: 'COMPRA ALDI SAN VICENTE' }))).toBe('COMPRA ALDI SAN VICENTE');
  expect(tituloFila(fila({ id: 'x', varias: true, tercero: { id: 't', nombre: 'Amazon', enabled: true } }))).toBe('Amazon · Varias');
});

// ------------------------------------------------------------------ B1 lista
test('caso 12 / B1: Día a día monta la Actividad; grupos por día, título, signos y transferencia neutra; sin hora', async () => {
  const c = fake();
  await irADia(c);
  expect(screen.getByTestId('pestana-estadisticas').props.accessibilityState).toEqual({ disabled: true, selected: false });
  expect(screen.getByTestId('actividad-periodo').props.accessibilityLabel).toBe('Periodo: Este mes');
  expect(c.actividad).toHaveBeenCalledWith(expect.objectContaining({ desde: '2026-10-01', hasta: '2026-11-01' }));
  expect(within(screen.getByTestId('grupo-2026-10-10')).getByText('Hoy · 10 oct 2026')).toBeTruthy();
  expect(within(screen.getByTestId('grupo-2026-10-09')).getByText('Ayer · 9 oct 2026')).toBeTruthy();
  expect(screen.getByTestId('fila-g1').props.accessibilityLabel).toBe('Compra semanal. ALDI · Supermercados · Tarjeta BBVA. −48,72 €');
  expect(screen.getByTestId('fila-t1').props.accessibilityLabel).toBe('Cuenta nómina → Ahorro. Entre cuentas. 500,00 €');
  expect(screen.getByTestId('fila-i1').props.accessibilityLabel).toBe('Empresa SL · Nómina. Cuenta nómina. +2.100,00 €');
  expect(screen.getByTestId('fila-g2').props.accessibilityLabel).toBe('Gasto · 4,00 €. Sin categoría · Efectivo. −4,00 €');
  expect(screen.queryByText(/\d{1,2}:\d{2}/)).toBeNull(); // sin hora
});

test('caso 17 / P-ACT-03: total con «reparto sin indicar» y detalle «Tu parte: Sin indicar»', async () => {
  const c = fake();
  await irADia(c);
  expect(screen.getByTestId('fila-g3').props.accessibilityLabel).toContain('Total · reparto sin indicar');
  await pulsar('fila-g3');
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
  expect(within(screen.getByTestId('kv-Tu parte')).getByText('Sin indicar')).toBeTruthy();
  expect(within(screen.getByTestId('kv-Total del hecho')).getByText('44,50 €')).toBeTruthy();
  expect(within(screen.getByTestId('kv-Contexto')).getByText('Cumpleaños Tania')).toBeTruthy();
  expect(screen.queryByTestId('tab-DIA')).toBeNull(); // hoja inmersiva: el velo cubre la barra
});

test('caso 15 / B8: maestro desactivado visible y marcado', async () => {
  await irADia(fake());
  expect(screen.getByTestId('fila-g4').props.accessibilityLabel).toContain('Categoría desactivada');
});

test('B11 / B12: detalle de transferencia (sin «tu parte» ni categoría) y de ingreso («Solo mío»)', async () => {
  const c = fake();
  await irADia(c);
  await pulsar('fila-t1');
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
  expect(within(screen.getByTestId('kv-Desde')).getByText('Cuenta nómina')).toBeTruthy();
  expect(within(screen.getByTestId('kv-A')).getByText('Ahorro')).toBeTruthy();
  expect(screen.queryByTestId('kv-Tu parte')).toBeNull();
  expect(screen.getByText('No es un gasto ni un ingreso: tu dinero cambia de cuenta.')).toBeTruthy();
  await pulsar('detalle-cerrar');
  await pulsar('fila-i1');
  await waitFor(() => expect(screen.getByTestId('kv-Tu parte')).toBeTruthy());
  expect(within(screen.getByTestId('kv-Tu parte')).getByText('2.100,00 € · Solo mío')).toBeTruthy();
  expect(within(screen.getByTestId('kv-Total del hecho')).getByText('+2.100,00 €')).toBeTruthy();
});

// ------------------------------------------------------------------ B13 / B6 estados
test('caso 23 / B13: fallo de red → error con «Reintentar», nunca «No hay registros»', async () => {
  let fallar = true;
  const c = fake({ actividad: () => (fallar ? { tipo: 'INDETERMINADO', mensaje: 'x' } : { tipo: 'OK', datos: { filas: FILAS, siguiente: null, total: 6 } }) });
  await montar(c);
  await pulsar('tab-DIA');
  await waitFor(() => expect(screen.getByTestId('actividad-error')).toBeTruthy());
  expect(screen.queryByTestId('actividad-vacio')).toBeNull();
  expect(screen.getByText('No se ha podido cargar la actividad')).toBeTruthy();
  fallar = false;
  await pulsar('actividad-reintentar');
  await waitFor(() => expect(screen.getByTestId('fila-g1')).toBeTruthy());
});

test('B6: mes vacío «No hay registros en octubre» con «Registrar»', async () => {
  const c = fake({ actividad: () => ({ tipo: 'OK', datos: { filas: [], siguiente: null, total: 0 } }) });
  await montar(c);
  await pulsar('tab-DIA');
  await waitFor(() => expect(screen.getByTestId('actividad-vacio')).toBeTruthy());
  expect(screen.getByText('No hay registros en octubre')).toBeTruthy();
  expect(screen.getByTestId('actividad-registrar')).toBeTruthy();
});

// ------------------------------------------------------------------ búsqueda (casos 16, 24)
test('caso 16 / 24: búsqueda en todo el historial con alcance; importe exacto; «Cancelar» restaura periodo y filtros', async () => {
  const c = fake({ actividad: (q: any) => ({ tipo: 'OK', datos: { filas: q.importe || q.q ? [FILAS[0]] : FILAS, siguiente: null, total: q.importe || q.q ? 1 : 6 } }) });
  await irADia(c);
  await pulsar('actividad-periodo');
  await pulsar('periodo-MES_ANTERIOR');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ desde: '2026-09-01' })));
  await pulsar('actividad-buscar');
  fireEvent.changeText(screen.getByTestId('actividad-busqueda'), '48,72');
  await esperar(400);
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ importe: '48.72', desde: null, q: null })));
  expect(screen.getByTestId('actividad-alcance')).toBeTruthy();
  expect(within(screen.getByTestId('actividad-alcance')).getByText('Buscando en todo el historial · importe exacto · 1 resultado')).toBeTruthy();
  fireEvent.changeText(screen.getByTestId('actividad-busqueda'), 'aldi');
  await esperar(400);
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'aldi', importe: null, desde: null })));
  await pulsar('actividad-cancelar-busqueda');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ desde: '2026-09-01', hasta: '2026-10-01', q: null })));
  expect(screen.getByTestId('actividad-periodo').props.accessibilityLabel).toBe('Periodo: Mes anterior');
});

// ------------------------------------------------------------------ filtros (B5/B8)
test('B5 / B8: filtros por tipo y cuenta; «Ver N resultados»; «Filtros · 2» y línea con «Limpiar»', async () => {
  const c = fake();
  c.cuentasElegibles = jest.fn(async (operacion: any) => ({ tipo: 'OK', datos: { operacion, cuentas: [{ cuenta_id: 'cta', nombre: 'Tarjeta BBVA', moneda: 'EUR' }] } })) as any;
  await irADia(c);
  await pulsar('actividad-filtros');
  await pulsar('filtro-tipo-GASTO');
  await waitFor(() => expect(screen.getByTestId('filtros-ver')).toBeTruthy());
  await pulsar('filtro-cuenta');
  await waitFor(() => expect(screen.getByTestId('lista-cta')).toBeTruthy());
  await pulsar('lista-cta');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ tipos: ['GASTO'], cuentaId: 'cta', limite: 1 })));
  await pulsar('filtros-ver');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ tipos: ['GASTO'], cuentaId: 'cta', desde: '2026-10-01' })));
  expect(within(screen.getByTestId('actividad-filtros')).getByText('Filtros · 2')).toBeTruthy();
  expect(within(screen.getByTestId('actividad-linea-filtros')).getByText('Gasto · Tarjeta BBVA')).toBeTruthy();
  await pulsar('actividad-limpiar');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ tipos: [], cuentaId: null })));
  expect(screen.queryByTestId('actividad-linea-filtros')).toBeNull();
});

// ------------------------------------------------------------------ Ajustes › Terceros (C1–C4)
async function abrirAldi(c: ClienteApi) {
  await montar(c);
  await pulsar('tab-MAS');
  await pulsar('mas-ajustes');
  await pulsar('ajustes-terceros');
  await waitFor(() => expect(screen.getByTestId('ajter-fila-ter-aldi')).toBeTruthy());
  await pulsar('ajter-fila-ter-aldi');
  await waitFor(() => expect(screen.getByTestId('ajter-habituales')).toBeTruthy());
  await waitFor(() => expect(screen.getByTestId('habitual-super')).toBeTruthy());
}

test('C1 / C3: «Uso en Gapto», habituales con «Quitar» (confirmación) y «No disponible»; «Según tu historial» con «Guardar»', async () => {
  const c = fake();
  await abrirAldi(c);
  expect(screen.getByTestId('ajter-uso-texto').props.children).toBe('41 registros · último 10 oct');
  expect(screen.getByTestId('habitual-no-disponible-limp')).toBeTruthy();
  expect(screen.queryByTestId('habitual-quitar-limp')).toBeNull();
  expect(within(screen.getByTestId('historial-drog')).getByText('7 de tus 41 gastos en ALDI')).toBeTruthy();
  await pulsar('habitual-quitar-super');
  expect(screen.getByText('¿Quitar Supermercados de ALDI?')).toBeTruthy();
  expect(screen.getByText('Dejará de sugerirse como guardada. Puede seguir apareciendo si la usas a menudo con ALDI. Tus registros no cambian.')).toBeTruthy();
  await pulsar('ajter-quitar-confirmar');
  await waitFor(() => expect(c.retirarAfinidad).toHaveBeenCalledWith('af1'));
  await pulsar('historial-guardar-drog');
  await waitFor(() => expect(c.altaAfinidad).toHaveBeenCalledWith({ id: expect.any(String), tercero_id: 'ter-aldi', categoria_id: 'drog' }));
});

test('C2: «Añadir categoría» marca la ya habitual «Ya es habitual» y no la duplica', async () => {
  const c = fake();
  await abrirAldi(c);
  await pulsar('ajter-anadir-categoria');
  await waitFor(() => expect(screen.getByTestId('cat-alim')).toBeTruthy());
  await pulsar('cat-alim');
  const sup = screen.getByTestId('cat-super');
  expect(sup.props.accessibilityLabel).toContain('Ya es habitual');
  expect(sup.props.accessibilityState.disabled).toBe(true);
  await pulsar('selector-cerrar');
  expect(c.altaAfinidad).not.toHaveBeenCalled();
});

test('caso 22 / C4: «Ver sus registros» abre la Actividad del tercero con todo el historial; «Limpiar» deja la Actividad normal', async () => {
  const c = fake();
  await abrirAldi(c);
  await pulsar('ajter-ver-registros');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ terceroId: 'ter-aldi', desde: null, hasta: null })));
  expect(screen.getByText('Registros de ALDI')).toBeTruthy();
  expect(screen.getByTestId('actividad-periodo').props.accessibilityLabel).toBe('Periodo: Todo el historial');
  await pulsar('actividad-limpiar');
  await waitFor(() => expect(screen.getByTestId('pestana-actividad')).toBeTruthy());
  expect(screen.getByTestId('tab-DIA').props.accessibilityState.selected).toBe(true);
});

// ------------------------------------------------------------------ Inicio (E1) y barra (A12)
test('caso 25 / 27 / E1: «Hola, Moisés»; Ingresos, Gastos y Resultado con color solo en Resultado; «Sin indicar» aparte', async () => {
  const c = fake();
  await montar(c);
  await waitFor(() => expect(screen.getByTestId('mes-resultado')).toBeTruthy());
  expect(screen.getByTestId('hola').props.children).toBe('Hola, Moisés');
  expect(screen.getByTestId('mes-ingresos').props.children).toBe('7.784,04 €');
  expect(screen.getByTestId('mes-gastos').props.children).toBe('3.339,91 €');
  expect(screen.getByTestId('mes-resultado').props.children).toBe('+4.444,13 €');
  expect(screen.getByTestId('mes-sin-indicar').props.children).toBe('Solo lo que es tuyo. Sin indicar: 7 gastos (700,35 €) y 2 ingresos (2.781,96 €).');
  const color = (id: string) => [screen.getByTestId(id).props.style].flat(3).reduce((a: any, x: any) => ({ ...a, ...x }), {}).color;
  expect(color('mes-ingresos')).toBe(color('mes-gastos')); // neutros (D-HOME-03)
  expect(color('mes-resultado')).not.toBe(color('mes-gastos')); // verde: excepción de Resultado
  expect(c.resultadoMes).toHaveBeenCalledWith(HOY);
  expect(textoSinIndicar({ mes: '2026-10', moneda: 'EUR', ingresos_propios: '0', gastos_propios: '0', resultado: '0', sin_indicar: { gastos: { n: 0, importe: '0' }, ingresos: { n: 0, importe: '0' } } })).toBe('Solo lo que es tuyo.');
});

test('A12: el icono de «Mes» es el calendario', () => {
  const fuente: string = require('fs').readFileSync(require('path').join(__dirname, '..', 'src', 'components', 'BarraInferior.tsx'), 'utf8');
  expect(fuente).toContain("{ id: 'MES', etiqueta: 'Mes', icono: 'calendar-outline', activo: 'calendar' }");
  expect(fuente.split('\n').filter((l) => !l.startsWith('//')).join('\n')).not.toContain('stats-chart');
});


// ------------------------------------------------------------------ K4-C (P12): desplazamiento restaurado tras «Cancelar»
/** Llamadas a scrollTo de la lista de la Actividad (el mock comparte scrollTo entre instancias). */
function scrollsDeLaLista(): any[] {
  const m = (ScrollView.prototype as any).scrollTo as jest.Mock;
  return m.mock.calls.filter((_, i) => m.mock.instances[i]?.props?.testID === 'actividad-lista').map((c) => c[0]);
}

test('caso 16 / P12: «Cancelar» restaura el desplazamiento cuando la lista ya está cargada, nunca durante «CARGANDO»', async () => {
  let liberar: (v: any) => void = () => undefined;
  let diferir = false;
  const c = fake({
    actividad: (q: any) => (diferir && !q.q && !q.importe
      ? new Promise((r) => { liberar = r; })
      : { tipo: 'OK', datos: { filas: FILAS, siguiente: null, total: FILAS.length } }),
  });
  await irADia(c);
  ((ScrollView.prototype as any).scrollTo as jest.Mock).mockClear();
  const lista = screen.getByTestId('actividad-lista');
  fireEvent.scroll(lista, { nativeEvent: { contentOffset: { x: 0, y: 629 }, contentSize: { width: 393, height: 2000 }, layoutMeasurement: { width: 393, height: 700 } } });
  await pulsar('actividad-buscar');
  fireEvent.changeText(screen.getByTestId('actividad-busqueda'), 'aldi');
  await esperar(400);
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'aldi' })));
  diferir = true;
  await pulsar('actividad-cancelar-busqueda');
  await waitFor(() => expect(screen.getByTestId('actividad-cargando')).toBeTruthy());
  fireEvent(screen.getByTestId('actividad-lista'), 'contentSizeChange', 393, 300); // esqueleto
  expect(scrollsDeLaLista()).toEqual([]); // nunca durante «CARGANDO»
  await act(async () => liberar({ tipo: 'OK', datos: { filas: FILAS, siguiente: null, total: FILAS.length } }));
  await waitFor(() => expect(screen.getByTestId('fila-g1')).toBeTruthy());
  fireEvent(screen.getByTestId('actividad-lista'), 'contentSizeChange', 393, 2000); // filas ya cargadas
  expect(scrollsDeLaLista()).toEqual([{ y: 629, animated: false }]);
  fireEvent(screen.getByTestId('actividad-lista'), 'contentSizeChange', 393, 2100); // un solo intento
  expect(scrollsDeLaLista()).toHaveLength(1);
});

test('P12 (negativo): sin búsqueda previa, un cambio de tamaño de la lista no la desplaza', async () => {
  await irADia(fake());
  ((ScrollView.prototype as any).scrollTo as jest.Mock).mockClear();
  fireEvent(screen.getByTestId('actividad-lista'), 'contentSizeChange', 393, 2000);
  expect(scrollsDeLaLista()).toEqual([]);
});

// ------------------------------------------------------------------ K4-E: periodo «Otro mes» / «Entre fechas» y filtros (A7)
test('A7 periodo: «Otro mes» consulta el mes elegido y «Entre fechas» envía «hasta» inclusivo como día siguiente', async () => {
  const c = fake();
  await irADia(c);
  await pulsar('actividad-periodo');
  await pulsar('periodo-OTRO_MES');
  expect(screen.getByTestId('otro-mes-valor').props.children).toMatch(/septiembre/i); // por defecto, el mes anterior
  await pulsar('otro-mes-anterior');
  expect(screen.getByTestId('otro-mes-valor').props.children).toMatch(/agosto/i);
  await pulsar('otro-mes-siguiente');
  await pulsar('otro-mes-siguiente');
  await pulsar('otro-mes-siguiente'); // no pasa del mes en curso
  expect(screen.getByTestId('otro-mes-valor').props.children).toMatch(/octubre/i);
  await pulsar('otro-mes-anterior');
  await pulsar('otro-mes-anterior');
  await pulsar('otro-mes-usar');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ desde: '2026-08-01', hasta: '2026-09-01' })));
  expect(screen.getByTestId('actividad-periodo').props.accessibilityLabel).toMatch(/agosto/i);

  await pulsar('actividad-periodo');
  await pulsar('periodo-ENTRE_FECHAS');
  fireEvent.changeText(screen.getByTestId('entre-desde'), '30/09/2026');
  fireEvent.changeText(screen.getByTestId('entre-hasta'), '05/09/2026');
  expect(screen.getByTestId('entre-error')).toBeTruthy(); // desde posterior a hasta
  expect(screen.getByTestId('entre-usar').props.accessibilityState.disabled).toBe(true);
  fireEvent.changeText(screen.getByTestId('entre-desde'), '05/09/2026');
  fireEvent.changeText(screen.getByTestId('entre-hasta'), '30/09/2026');
  expect(screen.queryByTestId('entre-error')).toBeNull();
  await pulsar('entre-usar');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ desde: '2026-09-05', hasta: '2026-10-01' })));
});

test('A7 filtros: categoría padre (con subcategorías), tercero y contexto llegan a la consulta', async () => {
  const c = fake();
  c.listarContextos = jest.fn(async () => ({ tipo: 'OK', datos: { contextos: [{ id: 'ctx1', nombre: 'Cumpleaños Tania', enabled: true }] } })) as any;
  await irADia(c);
  await pulsar('actividad-filtros');
  await pulsar('filtro-categoria');
  await waitFor(() => expect(screen.getByTestId('cat-alim')).toBeTruthy());
  await pulsar('cat-alim');
  await pulsar('selector-usar'); // la categoría PADRE, no una hoja
  await waitFor(() => expect(screen.getByTestId('hoja-filtros')).toBeTruthy());
  expect(within(screen.getByTestId('filtro-categoria')).getByText('Alimentación (con subcategorías)')).toBeTruthy();
  await pulsar('filtro-tercero');
  await waitFor(() => expect(screen.getByTestId('lista-ter-aldi')).toBeTruthy());
  await pulsar('lista-ter-aldi');
  await pulsar('filtro-contexto');
  await waitFor(() => expect(screen.getByTestId('lista-ctx1')).toBeTruthy());
  await pulsar('lista-ctx1');
  await pulsar('filtros-ver');
  await waitFor(() => expect(c.actividad).toHaveBeenLastCalledWith(expect.objectContaining({ categoriaId: 'alim', terceroId: 'ter-aldi', contextoId: 'ctx1', desde: '2026-10-01' })));
  const q = (c.actividad as jest.Mock).mock.calls.at(-1)![0];
  expect(q.incluirSubcategorias).not.toBe(false); // el cliente HTTP solo envía incluir_subcategorias=false si se pide
  expect(within(screen.getByTestId('actividad-filtros')).getByText('Filtros · 3')).toBeTruthy();
});

// ------------------------------------------------------------------ K-7 icono de categoría
const FILAS_K7: FilaActividad[] = [
  fila({ id: 'k1', nota: 'Compra semanal', categoria: { id: 'super', nombre: 'Supermercados', ruta: 'Alimentación › Supermercados', enabled: true, icon_key: 'compras.carrito' } }),
  fila({ id: 'k2', categoria: { id: 'otra', nombre: 'Otra', ruta: 'Otra', enabled: true, icon_key: null } }),
  fila({ id: 'k3', tipo: 'TRANSFERENCIA', importe_total: '500.00', estado_reparto: null, tu_parte: null,
    cuentas: [{ cuenta_id: 'a', nombre: 'Cuenta nómina', rol: 'ORIGEN', enabled: true }, { cuenta_id: 'b', nombre: 'Ahorro', rol: 'DESTINO', enabled: true }] }),
  fila({ id: 'k4', varias: true, categoria: null, tercero: { id: 'amz', nombre: 'Amazon', enabled: true } }),
  fila({ id: 'k5', categoria: null }),
];
// El icono va oculto a la accesibilidad (decorativo): se consulta incluyendo elementos ocultos.
const glifo = (testID: string) => within(screen.getByTestId(testID, { includeHiddenElements: true })).UNSAFE_getByType(Ionicons).props.name;

test('K-7: la fila y el detalle muestran el icono de su categoría; transferencia con intercambio; «Varias» y sin categoría con reserva', async () => {
  const c = fake({
    actividad: () => ({ tipo: 'OK', datos: { filas: FILAS_K7, siguiente: null, total: FILAS_K7.length } }),
    detalle: (id) => ({ tipo: 'OK', datos: { ...FILAS_K7.find((f) => f.id === id)!, presupuestable: true, magnitudes: [] } }),
  });
  await montar(c);
  await pulsar('tab-DIA');
  await waitFor(() => expect(screen.getByTestId('fila-k1')).toBeTruthy());
  expect(glifoDe('compras.carrito')).toBe('cart-outline');
  expect(glifo('actividad-icono-k1')).toBe('cart-outline');
  expect(glifo('actividad-icono-k2')).toBe(categoriaIconoFallback);
  expect(glifo('actividad-icono-k3')).toBe('swap-horizontal');
  expect(glifo('actividad-icono-k4')).toBe(categoriaIconoFallback);
  expect(glifo('actividad-icono-k5')).toBe(categoriaIconoFallback);
  await pulsar('fila-k1');
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
  expect(glifo('detalle-icono')).toBe('cart-outline');
  await pulsar('detalle-cerrar');
  await pulsar('fila-k3');
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
  expect(glifo('detalle-icono')).toBe('swap-horizontal');
  await pulsar('detalle-cerrar');
  await pulsar('fila-k5');
  await waitFor(() => expect(screen.getByTestId('detalle-contenido')).toBeTruthy());
  expect(glifo('detalle-icono')).toBe(categoriaIconoFallback);
});

declare const __dirname: string;