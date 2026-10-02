// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_magnitudes.test.tsx
// Ruta: mobile/__tests__/ajustes_magnitudes.test.tsx
// Descripción: Sección «Magnitudes» del detalle de Ajustes › Categorías (F05-D020; F09 §12.97.10; lámina SET-MAG v0.1), hito 1: sección plegada (M01) y desplegada (M02) con el catálogo cargado al desplegar, disponible en desactivadas (P1); vacío (M04) distinto del error de carga (M05) con reintento; «No usable en registros nuevos» (M03); selector del catálogo (M06) con secciones y búsqueda, tarea inmersiva; añadir una existente con la obligatoriedad elegida sin preselección y aviso previo si está deshabilitada (M09); obligatoriedad (M11) y quitar con N registros (M12) con la identidad cargada; conflicto e indeterminado: recarga y aviso, UNA sola llamada (sin reintento automático, M16).
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi } from '../src/api/cliente';
import { AVISO_DESHABILITADA, textoQuitar, TEXTO_HACER_OBLIGATORIA } from '../src/components/HojasMagnitud';
import { AVISO_CAMBIADAS, AVISO_INDETERMINADO } from '../src/components/MagnitudesCategoria';
import { NOTA_SECCION, TEXTO_ERROR, TEXTO_VACIO, TITULO_NO_USABLE, TITULO_VACIO } from '../src/components/SeccionMagnitudes';
import { textoNoUsable } from '../src/domain/magnitud';
import { ProveedorTema } from '../src/theme/tema';

import { CATALOGO, fakeMag, KWH, LISTA_MAG, POT, rechazo } from './fixtures_magnitudes';

function pintar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={() => 'c0000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 8, 24)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

async function abrirDetalle(cliente: ClienteApi, id: string, o: { dentroDe?: string; todas?: boolean } = {}) {
  pintar(cliente);
  fireEvent.press(screen.getByTestId('tab-MAS'));
  fireEvent.press(screen.getByTestId('mas-ajustes'));
  fireEvent.press(screen.getByTestId('ajustes-categorias'));
  await screen.findByTestId('fila-hogar');
  if (o.todas) fireEvent.press(screen.getByTestId('filtro-TODAS'));
  if (o.dentroDe) fireEvent.press(screen.getByTestId(`fila-${o.dentroDe}`));
  fireEvent.press(screen.getByTestId(`fila-${id}`));
  await screen.findByTestId('detalle-categoria');
}

const texto = (id: string) => screen.getByTestId(id).props.children;

async function desplegar() {
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-cabecera')));
  await waitFor(() => expect(screen.queryByTestId('magnitudes-cargando')).toBeNull());
}

// ------------------------------------------------------------------ sección
test('plegada: «Magnitudes · 2» con el resumen, entre «Icono» y «Acciones»; el catálogo no se pide hasta desplegar', async () => {
  const f = fakeMag();
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  expect(screen.getByText('Magnitudes · 2')).toBeTruthy();
  expect(texto('magnitudes-resumen')).toBe('1 obligatoria, 1 opcional');
  expect(screen.queryByTestId(`magnitud-fila-${KWH.asociacion_id}`)).toBeNull();
  expect(f.cliente.catalogoMagnitudes).not.toHaveBeenCalled();
});

test('desplegada: filas en su orden con «unidad · decimales» y píldoras de texto; añadir, nota', async () => {
  const f = fakeMag();
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  await desplegar();
  expect(f.cliente.catalogoMagnitudes).toHaveBeenCalledTimes(1);
  expect(texto('magnitudes-resumen')).toBe('1 obligatoria, 1 opcional · se piden al registrar en Luz');
  const filas = screen.getAllByTestId(/^magnitud-fila-/).map((n) => n.props.testID);
  expect(filas).toEqual(['magnitud-fila-a-kwh', 'magnitud-fila-a-pot']);
  expect(screen.getByTestId('magnitud-fila-a-kwh').props.accessibilityLabel).toBe('Consumo eléctrico. kWh · 2 decimales. Obligatoria');
  expect(screen.getByTestId('magnitud-fila-a-pot').props.accessibilityLabel).toBe('Potencia contratada. kW · 1 decimal. Opcional');
  expect(screen.getByTestId('magnitudes-anadir')).toBeTruthy();
  expect(texto('magnitudes-nota')).toBe(NOTA_SECCION);
});

test('disponible también en una categoría desactivada (P1)', async () => {
  const f = fakeMag();
  await abrirDetalle(f.cliente, 'viejo', { todas: true });
  expect(screen.getByTestId('seccion-magnitudes')).toBeTruthy();
  expect(screen.getByText('Magnitudes · 0')).toBeTruthy();
});

test('vacío (M04) distinto del error de carga (M05) y reintento', async () => {
  const f = fakeMag();
  (f.cliente.catalogoMagnitudes as jest.Mock).mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: '' });
  await abrirDetalle(f.cliente, 'prof', { dentroDe: 'trabajo' });
  await desplegar();
  expect(screen.getByTestId('magnitudes-error')).toBeTruthy();
  expect(screen.getByText(TEXTO_ERROR)).toBeTruthy();
  expect(screen.queryByTestId('magnitudes-vacio')).toBeNull();
  expect(screen.getByText('Magnitudes')).toBeTruthy(); // sin recuento fabricado
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-reintentar')));
  await screen.findByTestId('magnitudes-vacio');
  expect(screen.getByText(TITULO_VACIO)).toBeTruthy();
  expect(screen.getByText(TEXTO_VACIO('Gastos profesionales'))).toBeTruthy();
  expect(screen.getByTestId('magnitudes-anadir')).toBeTruthy();
});

test('no usable (M03): resumen plegado y motivo con las tres salidas al desplegar', async () => {
  const f = fakeMag();
  await abrirDetalle(f.cliente, 'gas', { dentroDe: 'hogar' });
  expect(texto('magnitudes-resumen')).toBe(`1 obligatoria · ${TITULO_NO_USABLE}`);
  await desplegar();
  expect(screen.getByTestId('magnitudes-no-usable')).toBeTruthy();
  expect(screen.getByText(textoNoUsable(['Consumo de gas']))).toBeTruthy();
  expect(screen.getByTestId('magnitud-deshabilitada-a-kwhgas')).toBeTruthy();
});

// ------------------------------------------------------------------ añadir una existente
async function abrirSelector(f: ReturnType<typeof fakeMag>) {
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  await desplegar();
  fireEvent.press(screen.getByTestId('magnitudes-anadir'));
  await screen.findByTestId('selector-magnitudes');
}

test('selector (M06): secciones, ya asociadas atenuadas y no elegibles, búsqueda; tarea inmersiva', async () => {
  const f = fakeMag();
  await abrirSelector(f);
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  expect(screen.getByText('Disponibles')).toBeTruthy();
  expect(screen.getByText('Deshabilitadas')).toBeTruthy();
  expect(screen.getByText('Ya en Luz')).toBeTruthy();
  expect(screen.getByTestId('selmag-km').props.accessibilityLabel).toBe('Kilómetros. km · 1 decimal · sin categorías');
  expect(screen.getByTestId('selmag-ya-kwh').props.accessibilityState).toEqual({ disabled: true, checked: true });
  expect(screen.queryByTestId('selmag-kwh')).toBeNull();
  fireEvent.changeText(screen.getByTestId('selmag-buscar'), 'kilo');
  expect(screen.getByTestId('selmag-km')).toBeTruthy();
  expect(screen.queryByTestId('selmag-m3')).toBeNull();
  fireEvent.press(screen.getByTestId('selmag-cancelar'));
  expect(screen.getByTestId('detalle-categoria')).toBeTruthy();
});

test('añadir existente: obligatoriedad sin preselección, una llamada EXISTENTE y recarga', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => ({
    tipo: 'OK' as const,
    datos: { categoria_id: 'luz', asociacion: { asociacion_id: 'a-km', magnitud_id: 'km', obligatoria: false, orden: 2 }, magnitud: { ...CATALOGO[3] }, idempotente: false, modificadas: ['a-km'] },
  }));
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-km'));
  await screen.findByTestId('hoja-anadir-magnitud');
  expect(screen.getByTestId('anadir-confirmar')).toBeDisabled();
  expect(screen.queryByTestId('anadir-aviso-deshabilitada')).toBeNull();
  fireEvent.press(screen.getByTestId('anadir-obligatoria-false'));
  const arboles = (f.cliente.arbolCategorias as jest.Mock).mock.calls.length;
  f.fijarArbol(LISTA_MAG.map((n) => (n.id === 'luz' ? { ...n, magnitudes: [KWH, POT, { ...POT, asociacion_id: 'a-km', magnitud_id: 'km', nombre: 'Kilómetros', orden: 2 }] } : n)));
  await act(async () => fireEvent.press(screen.getByTestId('anadir-confirmar')));
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledWith('luz', { origen: 'EXISTENTE', magnitud_id: 'km', obligatoria: false });
  await screen.findByTestId('detalle-categoria');
  expect((f.cliente.arbolCategorias as jest.Mock).mock.calls.length).toBe(arboles + 1);
  expect(screen.getByText('Magnitudes · 3')).toBeTruthy();
});

test('añadir una deshabilitada (M09): aviso previo y «Añadir de todos modos»; no la rehabilita', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' }));
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-kwhgas'));
  await screen.findByTestId('hoja-anadir-magnitud');
  expect(screen.getByText(AVISO_DESHABILITADA('Luz', 'Consumo de gas'))).toBeTruthy();
  expect(screen.getByText('Añadir de todos modos')).toBeTruthy();
  fireEvent.press(screen.getByTestId('anadir-obligatoria-true'));
  await act(async () => fireEvent.press(screen.getByTestId('anadir-confirmar')));
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledWith('luz', { origen: 'EXISTENTE', magnitud_id: 'kwhgas', obligatoria: true });
  expect(f.cliente.rehabilitarMagnitud).not.toHaveBeenCalled();
  // Indeterminado: vuelve al detalle con aviso y estado recargado; una sola llamada.
  await screen.findByTestId('magnitudes-aviso');
  expect(screen.getByText(AVISO_INDETERMINADO.titulo)).toBeTruthy();
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
});

// ------------------------------------------------------------------ ficha: obligatoriedad y quitar
async function abrirFicha(f: ReturnType<typeof fakeMag>, asociacion: string) {
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  await desplegar();
  fireEvent.press(screen.getByTestId(`magnitud-fila-${asociacion}`));
  await screen.findByTestId('ficha-magnitud');
}

test('obligatoriedad (M11): hoja con guarda prospectiva y la identidad cargada', async () => {
  const f = fakeMag();
  f.cliente.obligatoriaMagnitud = jest.fn(async () => ({
    tipo: 'OK' as const,
    datos: { categoria_id: 'luz', asociacion: { asociacion_id: 'a-pot', magnitud_id: 'pot', obligatoria: true, orden: 1 }, magnitud: { ...CATALOGO[4] }, idempotente: false, modificadas: ['a-pot'] },
  }));
  await abrirFicha(f, 'a-pot');
  expect(screen.getByText('Hacer obligatoria')).toBeTruthy();
  fireEvent.press(screen.getByTestId('ficha-obligatoriedad'));
  await screen.findByTestId('hoja-obligatoriedad');
  expect(screen.getByText('¿Obligatoria en Luz?')).toBeTruthy();
  expect(texto('obligatoriedad-texto')).toBe(TEXTO_HACER_OBLIGATORIA('Luz', 'Potencia contratada'));
  f.fijarArbol(LISTA_MAG.map((n) => (n.id === 'luz' ? { ...n, magnitudes: [KWH, { ...POT, obligatoria: true }] } : n)));
  await act(async () => fireEvent.press(screen.getByTestId('obligatoriedad-confirmar')));
  expect(f.cliente.obligatoriaMagnitud).toHaveBeenCalledWith('luz', 'a-pot', { magnitud_id: 'pot', obligatoria_actual: false, obligatoria: true });
  await waitFor(() => expect(screen.queryByTestId('hoja-obligatoriedad')).toBeNull());
  expect(screen.getByTestId('ficha-magnitud')).toBeTruthy();
  expect(screen.getByText('Hacer opcional')).toBeTruthy();
});

test('quitar (M12): mensaje seguro con N registros de la magnitud; vuelve al detalle', async () => {
  const f = fakeMag();
  f.cliente.retirarMagnitud = jest.fn(async () => ({
    tipo: 'OK' as const,
    datos: { categoria_id: 'luz', asociaciones: [{ asociacion_id: 'a-pot', magnitud_id: 'pot', obligatoria: false, orden: 0 }], idempotente: false, modificadas: ['a-kwh', 'a-pot'] },
  }));
  await abrirFicha(f, 'a-kwh');
  fireEvent.press(screen.getByTestId('ficha-quitar'));
  await screen.findByTestId('hoja-quitar');
  expect(texto('quitar-texto')).toBe(textoQuitar('Luz', 6));
  expect(texto('quitar-texto')).toMatch(/^Esta magnitud aparece en 6 registros históricos\. Retirar su asociación con la categoría no modifica esos registros\./);
  f.fijarArbol(LISTA_MAG.map((n) => (n.id === 'luz' ? { ...n, magnitudes: [{ ...POT, orden: 0 }] } : n)));
  await act(async () => fireEvent.press(screen.getByTestId('quitar-confirmar')));
  expect(f.cliente.retirarMagnitud).toHaveBeenCalledWith('luz', 'a-kwh', { magnitud_id: 'kwh', obligatoria_actual: true });
  await screen.findByTestId('detalle-categoria');
  expect(screen.getByText('Magnitudes · 1')).toBeTruthy();
});

test('conflicto (M16): ASOCIACION_NO_EXISTE recarga, avisa y no reintenta', async () => {
  const f = fakeMag();
  f.cliente.retirarMagnitud = jest.fn(async () => rechazo('ASOCIACION_NO_EXISTE'));
  await abrirFicha(f, 'a-pot');
  fireEvent.press(screen.getByTestId('ficha-quitar'));
  const arboles = (f.cliente.arbolCategorias as jest.Mock).mock.calls.length;
  await act(async () => fireEvent.press(screen.getByTestId('quitar-confirmar')));
  await screen.findByTestId('magnitudes-aviso');
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').titulo)).toBeTruthy();
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').texto)).toBeTruthy();
  expect(f.cliente.retirarMagnitud).toHaveBeenCalledTimes(1);
  expect((f.cliente.arbolCategorias as jest.Mock).mock.calls.length).toBe(arboles + 1);
  expect(screen.queryByTestId('ficha-magnitud')).toBeNull();
});

test.each(['VERSION_DESFASADA', 'ASOCIACION_YA_EXISTE', 'CONJUNTO_MAGNITUDES_DESFASADO'])('conflicto %s al añadir: recarga y aviso M16', async (codigo) => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => rechazo(codigo));
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-km'));
  fireEvent.press(screen.getByTestId('anadir-obligatoria-false'));
  await act(async () => fireEvent.press(screen.getByTestId('anadir-confirmar')));
  await screen.findByTestId('magnitudes-aviso');
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').titulo)).toBeTruthy();
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
});
