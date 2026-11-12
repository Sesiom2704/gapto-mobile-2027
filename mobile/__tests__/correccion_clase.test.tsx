// ============================================================
// GAPTO MOBILE 2027
// Fichero: correccion_clase.test.tsx
// Ruta: mobile/__tests__/correccion_clase.test.tsx
// Descripción: B3 · Corregir la clase de un gasto de la propiedad en el cliente (F06-01 B3; C-MEJ-03, R1 v0.9.5 §III.3.3bis, §III.3.6 y §III.1bis 8quater; oráculos v0.7 O5.33 y O9.17 parte cliente; boceto L-5) contra dobles en memoria:
//   - sin `intencion_correccion_id` no se ofrece «Corregir la clase» (O5.33, M-ID-13 cliente);
//   - O9.17: con deuda, sin «Corregir la clase», con la limitación LITERAL de 8quater y sin «anular y recrear» ni la corrección de categoría como equivalentes (M-DM02-14);
//   - la pantalla de corrección: destinos según la clase actual, categoría y presupuesto sin valor previo, motivo obligatorio, `intencion_id` = la leída (el cliente no genera UUID), `comparacion_vista` = la leída, IMPACTO_CORRECCION_DESFASADO avisa y recarga.
//   - C2: la lista separa lo que suma al coste y lo que es gasto.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, ComparacionImpacto, FilaGastoPropiedad, LecturaGastoPropiedad, PayloadCorregirClase } from '../src/api/patrimonio_b3';
import type { VistaPropiedad } from '../src/api/propiedades';
import { clasesDestino, faltasCorreccion, payloadCorreccion, resumenGastos, seleccionInicial, TEXTO_IMPACTO_DESFASADO, TEXTO_LIMITACION_8QUATER } from '../src/domain/gasto_propiedad';
import { CorregirClaseScreen, DetalleGastoPropiedad, GastosPropiedadScreen } from '../src/screens/GastoPropiedadScreen';
import { ProveedorTema } from '../src/theme/tema';

const CAT = 'ca000000-0000-4000-8000-0000000000ca';
const INT = '1e000000-0000-4000-8000-00000000001e';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const LITERAL = 'Los hechos de gasto de propiedad con una posición de deuda asociada no admiten actualmente la operación Corregir clase. No existe en este alcance una vía soportada para corregir su clase conservando la posición. Esta capacidad queda pendiente de una corrección de clase para hechos con varios efectos.';

const lectura = (o: Partial<LecturaGastoPropiedad> = {}): LecturaGastoPropiedad => ({
  hecho_id: 'h1', propiedad_id: 'p1', estado: 'ACTIVO', row_version: 2, tipo_hecho: 'MEJORA_PATRIMONIAL', clase: 'MEJORA', importe: '8500.00', fecha: '2025-02-10',
  nota: 'Cocina', categoria_id: null, presupuestable: false, procedencia: 'GASTO_PROPIEDAD', efectos_vigentes: 1, con_deuda: false, posiciones: [], atribuciones: [],
  intencion_correccion_id: INT, limitacion: null, ...o,
});
const COMP: ComparacionImpacto = { mes: '2025-02', resultado_mes_delta_antes: '0.00', resultado_mes_delta_despues: '-8500.00', mejoras_antes: '8500.00',
  mejoras_despues: '0.00', presupuesto_delta_despues: '-8500.00' };

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const marcado = (id: string) => !!screen.getByTestId(id).props.accessibilityState?.checked;
const envolver = (x: React.ReactElement) => (
  <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar="light">{x}</ProveedorTema></SafeAreaProvider>
);
const cliente = () => ({
  arbolCategorias: jest.fn(async () => ok({ categorias: [{ id: CAT, nombre: 'Reparaciones', parent_id: null, enabled: true, ambito: 'GASTO', capturable: true, magnitudes: [], motivo_no_capturable: null, orden: 0, icon_key: null }] })),
  cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [] })),
}) as unknown as ClienteApi;

function patrimonio(o: { corregir?: jest.Mock; lista?: FilaGastoPropiedad[]; leer?: LecturaGastoPropiedad } = {}) {
  return {
    propuestaGasto: jest.fn(), registrarGastoPropiedad: jest.fn(), mejoraHistorica: jest.fn(),
    listarGastos: jest.fn(async () => ok({ gastos: o.lista ?? [] })),
    leerGasto: jest.fn(async () => ok(o.leer ?? lectura())),
    impactoCorreccion: jest.fn(async () => ok({ comparacion: COMP })),
    corregirClase: o.corregir ?? jest.fn(async () => ok({ ...lectura(), clase: 'GASTO', idempotente: false })),
  } as unknown as ClientePatrimonioB3 & Record<string, jest.Mock>;
}

// ------------------------------------------------------------------ dominio
test('dominio: destinos, faltas y payload (intención leída, comparación leída, presupuesto prohibido a MEJORA)', () => {
  expect(clasesDestino(lectura())).toEqual(['REPARACION', 'GASTO_CORRIENTE']);
  expect(clasesDestino(lectura({ clase: 'GASTO' }))).toEqual(['MEJORA']);
  expect(faltasCorreccion(seleccionInicial())).toEqual(['la clase nueva', 'el motivo']);
  expect(faltasCorreccion({ ...seleccionInicial(), clase: 'REPARACION', motivo: 'x' })).toEqual(['la categoría', 'si cuenta para el presupuesto']);
  const p = payloadCorreccion(lectura(), { clase: 'REPARACION', categoriaId: CAT, presupuestable: true, motivo: ' error ' }, COMP);
  expect(p).toEqual({ intencion_id: INT, row_version_esperada: 2, clase_nueva: 'REPARACION', motivo: 'error', categoria_id: CAT, presupuestable: true, comparacion_vista: COMP });
  const m = payloadCorreccion(lectura({ clase: 'GASTO' }), { clase: 'MEJORA', categoriaId: CAT, presupuestable: true, motivo: 'x' }, COMP);
  expect(m.presupuestable).toBeNull();
  expect(m.categoria_id).toBeNull();
  expect(TEXTO_LIMITACION_8QUATER).toBe(LITERAL);
});

test('C2: la lista separa lo que suma al coste (mejoras) y lo que es gasto', () => {
  const f = (clase: 'MEJORA' | 'GASTO', importe: string, estado = 'ACTIVO'): FilaGastoPropiedad => ({ hecho_id: importe, tipo_hecho: '', clase, importe, fecha: '2026-01-01', nota: null,
    procedencia: 'GASTO_PROPIEDAD', estado, con_deuda: false });
  expect(resumenGastos([f('MEJORA', '12500.00'), f('MEJORA', '5500.00'), f('GASTO', '300.00'), f('GASTO', '99.00', 'ANULADO')]))
    .toEqual({ mejoras: '18000.00', gastos: '300.00', total: '18300.00' });
});

// ------------------------------------------------------------------ detalle
test('O5.33 / M-ID-13 (cliente): sin intención vigente no se ofrece «Corregir la clase»', () => {
  render(envolver(<DetalleGastoPropiedad lectura={lectura({ intencion_correccion_id: null })} onCorregir={jest.fn()} />));
  expect(screen.queryByTestId('gprop-corregir-clase')).toBeNull();
});

test('O9.17 / M-DM02-14 (cliente): con deuda, sin «Corregir la clase», con la limitación literal y sin alternativas falsas', () => {
  render(envolver(<DetalleGastoPropiedad lectura={lectura({ con_deuda: true, efectos_vigentes: 2, intencion_correccion_id: null })} onCorregir={jest.fn()} />));
  expect(screen.queryByTestId('gprop-corregir-clase')).toBeNull();
  expect(screen.getByTestId('gprop-limitacion').props.children).toBe(LITERAL);
  expect(screen.queryByText(/anular/i)).toBeNull();
  expect(screen.queryByText(/recrear/i)).toBeNull();
  expect(screen.queryByText(/corregir la categor/i)).toBeNull();
});

test('control: con intención vigente y sin deuda se ofrece «Corregir la clase»', () => {
  render(envolver(<DetalleGastoPropiedad lectura={lectura()} onCorregir={jest.fn()} />));
  expect(screen.getByTestId('gprop-corregir-clase')).toBeTruthy();
  expect(screen.queryByTestId('gprop-limitacion')).toBeNull();
});

// ------------------------------------------------------------------ corrección
async function montarCorregir(pat: ClientePatrimonioB3, l = lectura(), onCerrar = jest.fn()) {
  render(envolver(<CorregirClaseScreen cliente={cliente()} patrimonio={pat} propiedadId="p1" lectura={l} onCerrar={onCerrar} />));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  return onCerrar;
}

test('L-5: MEJORA → REPARACION con categoría, presupuesto sin valor previo, motivo obligatorio y comparación leída', async () => {
  const pat = patrimonio();
  const cerrar = await montarCorregir(pat);
  expect(screen.queryByTestId('cc-clase-MEJORA')).toBeNull();
  await pulsar('cc-clase-REPARACION');
  await waitFor(() => expect(screen.getByTestId(`cc-categoria-${CAT}`)).toBeTruthy());
  expect(marcado('cc-presupuestable-si') || marcado('cc-presupuestable-no')).toBe(false);
  expect(screen.getByTestId('cc-corregir').props.accessibilityState?.disabled).toBe(true);
  await pulsar(`cc-categoria-${CAT}`);
  await pulsar('cc-presupuestable-si');
  await waitFor(() => expect(screen.getByTestId('cc-impacto')).toBeTruthy());
  expect(pat.impactoCorreccion).toHaveBeenLastCalledWith('p1', 'h1', 'REPARACION', true);
  expect(screen.getByTestId('cc-faltas').props.children).toContain('el motivo');
  await escribir('cc-motivo', 'Era una reparación');
  await pulsar('cc-corregir');
  const body = (pat.corregirClase as jest.Mock).mock.calls[0][2] as PayloadCorregirClase;
  expect(body).toEqual({ intencion_id: INT, row_version_esperada: 2, clase_nueva: 'REPARACION', motivo: 'Era una reparación', categoria_id: CAT, presupuestable: true,
    comparacion_vista: COMP });
  expect(cerrar).toHaveBeenCalledWith(true);
});

test('GASTO → MEJORA: sin categoría ni presupuesto', async () => {
  const pat = patrimonio();
  await montarCorregir(pat, lectura({ clase: 'GASTO', tipo_hecho: 'GASTO', categoria_id: CAT, presupuestable: true }));
  expect(screen.queryByTestId('cc-clase-REPARACION')).toBeNull();
  await pulsar('cc-clase-MEJORA');
  expect(screen.queryByTestId('cc-presupuestable-si')).toBeNull();
  await waitFor(() => expect(screen.getByTestId('cc-impacto')).toBeTruthy());
  expect(pat.impactoCorreccion).toHaveBeenLastCalledWith('p1', 'h1', 'MEJORA', null);
  await escribir('cc-motivo', 'Era una mejora');
  await pulsar('cc-corregir');
  const body = (pat.corregirClase as jest.Mock).mock.calls[0][2] as PayloadCorregirClase;
  expect(body.presupuestable).toBeNull();
  expect(body.categoria_id).toBeNull();
});

test('IMPACTO_CORRECCION_DESFASADO: aviso «Los datos han cambiado; revisa el impacto» y la tabla se recarga', async () => {
  const corregir = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'IMPACTO_CORRECCION_DESFASADO', mensaje: '' }));
  const pat = patrimonio({ corregir: corregir as unknown as jest.Mock });
  await montarCorregir(pat, lectura({ clase: 'GASTO', tipo_hecho: 'GASTO' }));
  await pulsar('cc-clase-MEJORA');
  await waitFor(() => expect(screen.getByTestId('cc-impacto')).toBeTruthy());
  await escribir('cc-motivo', 'x');
  const antes = (pat.impactoCorreccion as jest.Mock).mock.calls.length;
  await pulsar('cc-corregir');
  expect(screen.getByText(TEXTO_IMPACTO_DESFASADO)).toBeTruthy();
  expect((pat.impactoCorreccion as jest.Mock).mock.calls.length).toBe(antes + 1);
});

test('C2 → detalle → «Corregir la clase»: el detalle se abre desde la lista con la lectura del servidor', async () => {
  const fila: FilaGastoPropiedad = { hecho_id: 'h1', tipo_hecho: 'MEJORA_PATRIMONIAL', clase: 'MEJORA', importe: '8500.00', fecha: '2025-02-10', nota: 'Cocina',
    procedencia: 'GASTO_PROPIEDAD', estado: 'ACTIVO', con_deuda: false };
  const pat = patrimonio({ lista: [fila] });
  render(envolver(<GastosPropiedadScreen cliente={cliente()} patrimonio={pat} vista={{ id: 'p1', nombre: 'Piso Ejemplo', row_version: 1 } as VistaPropiedad}
    nuevoId={() => 'n'} ahora={() => new Date(2026, 9, 10)} onCerrar={jest.fn()} />));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  expect(screen.getByTestId('gastos-mejoras-valor').props.children).toBe('8.500,00 €');
  await pulsar('gastos-fila-h1');
  await waitFor(() => expect(screen.getByTestId('gprop-corregir-clase')).toBeTruthy());
  await pulsar('gprop-corregir-clase');
  expect(screen.getByTestId('corregir-clase')).toBeTruthy();
});
