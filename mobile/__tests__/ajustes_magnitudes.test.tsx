// ============================================================
// GAPTO MOBILE 2027
// Fichero: ajustes_magnitudes.test.tsx
// Ruta: mobile/__tests__/ajustes_magnitudes.test.tsx
// Descripción: Sección «Magnitudes» del detalle de Ajustes › Categorías (F05-D020; F09 §12.97.10; lámina SET-MAG v0.1), hito 1: sección plegada (M01) y desplegada (M02) con el catálogo cargado al desplegar, disponible en desactivadas (P1); vacío (M04) distinto del error de carga (M05) con reintento; «No usable en registros nuevos» (M03); selector del catálogo (M06) con secciones y búsqueda, tarea inmersiva; añadir una existente con la obligatoriedad elegida sin preselección y aviso previo si está deshabilitada (M09); obligatoriedad (M11) y quitar con N registros (M12) con la identidad cargada; conflicto e indeterminado: recarga y aviso, UNA sola llamada (sin reintento automático, M16).
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// Versión: 0.2.0 (F05-01 S7-MAG UI, hito 2): alta NUEVA con acción desactivada hasta completar y «Para crear falta: …», envío exacto, identidad reutilizada en el reintento indeterminado y renovada al editar, IDENTIDAD_REUTILIZADA, colisión con detalle (usar / rehabilitar y usar: segunda llamada solo si la primera confirma) y sin detalle (genérico + recargar catálogo); Editar orden con UNA llamada y el conjunto completo, «Sin cambios» sin envío; ficha global (M13); renombrar con colisión junto al nombre; deshabilitar sin impacto (una llamada), con impacto en dos pasos (M14) e impacto cambiado (M15) sin reenvío automático; rehabilitar.
// Versión: 0.3.0 (F05-01 S7-MAG UI, D59): deshabilitar sin impacto pide confirmación simple («Cancelar» no envía nada; «Deshabilitar» envía UNA llamada sin confirmación de impacto); con impacto visible se mantiene M14.
// Versión: 0.4.0 (F05-01 S7-MAG UI correctivo AJ-S7MAGUI-01/02/03/08): M09 con el aviso según la obligatoriedad elegida (sin elección, obligatoria, opcional; cambia con la elección); recarga tras un comando con alguna lectura fallida (árbol o catálogo): estado posiblemente desfasado con «Reintentar» (solo lecturas), nunca «Se ha recargado el estado actual»; deshabilitar con impacto visible: hoja M14 ANTES de cualquier POST y POST con el conjunto del catálogo; servidor con impacto vacío o distinto: M15 y nueva confirmación; sin impacto con impacto en el servidor: M15; rehabilitar y usar con fallo del segundo comando: hoja que reintenta solo la asociación.
// ============================================================

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi } from '../src/api/cliente';
import { NOTA_R17, TEXTO_HISTORICOS } from '../src/components/FichaMagnitud';
import {
  AVISO_DESHABILITADA,
  IMPACTO_CAMBIADO,
  TEXTO_ASOCIAR_PENDIENTE,
  NOTA_DESHABILITAR,
  TEXTO_CONFIRMAR_DESHABILITAR,
  textoQuitar,
  TEXTO_HACER_OBLIGATORIA,
} from '../src/components/HojasMagnitud';
import {
  AVISO_CAMBIADAS,
  AVISO_INDETERMINADO,
  AVISO_NUEVA_INDETERMINADO,
  AVISO_NUEVA_REUTILIZADA,
  AVISO_SIN_CAMBIOS_ORDEN,
  MSG_RENOMBRAR_DUPLICADO,
  TEXTO_DESFASADO,
  TITULO_GUARDADO,
} from '../src/components/MagnitudesCategoria';
import { COLISION_GENERICA } from '../src/components/NuevaMagnitud';
import { NOTA_SECCION, TEXTO_ERROR, TEXTO_VACIO, TITULO_NO_USABLE, TITULO_VACIO } from '../src/components/SeccionMagnitudes';
import { textoNoUsable } from '../src/domain/magnitud';
import { ProveedorTema } from '../src/theme/tema';

import { CATALOGO, fakeMag, KWH, LISTA_MAG, POT, rechazo } from './fixtures_magnitudes';

let contadorIds = 0;
beforeEach(() => {
  contadorIds = 0;
});

function pintar(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={() => `id-${++contadorIds}`} ahora={() => new Date(2026, 8, 24)} />
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
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-anadir')));
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

test('añadir una deshabilitada (M09) SIN elegir obligatoriedad: texto neutro, sin afirmar el efecto', async () => {
  const f = fakeMag();
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-kwhgas'));
  await screen.findByTestId('hoja-anadir-magnitud');
  expect(screen.getByText('Esta magnitud está deshabilitada. Elige si será obligatoria u opcional para ver el efecto.')).toBeTruthy();
  expect(screen.queryByText(AVISO_DESHABILITADA.OBLIGATORIA)).toBeNull();
  expect(screen.queryByText(AVISO_DESHABILITADA.OPCIONAL)).toBeNull();
  expect(screen.getByText('Añadir de todos modos')).toBeTruthy();
});

test('añadir una deshabilitada como OPCIONAL (M09, C07): no impide utilizar la categoría; el aviso cambia con la elección', async () => {
  const f = fakeMag();
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-kwhgas'));
  await screen.findByTestId('hoja-anadir-magnitud');
  fireEvent.press(screen.getByTestId('anadir-obligatoria-false'));
  expect(screen.getByText('Esta magnitud está deshabilitada y no podrá informarse en registros nuevos mientras siga así. Añadirla como opcional no impide utilizar la categoría. Añadirla no la rehabilita.')).toBeTruthy();
  expect(screen.queryByText(AVISO_DESHABILITADA.OBLIGATORIA)).toBeNull();
  fireEvent.press(screen.getByTestId('anadir-obligatoria-true'));
  expect(screen.getByText(AVISO_DESHABILITADA.OBLIGATORIA)).toBeTruthy();
  expect(screen.queryByText(AVISO_DESHABILITADA.OPCIONAL)).toBeNull();
  fireEvent.press(screen.getByTestId('anadir-obligatoria-false'));
  expect(screen.getByText(AVISO_DESHABILITADA.OPCIONAL)).toBeTruthy();
  expect(screen.getByText('Añadir de todos modos')).toBeTruthy();
});

test('añadir una deshabilitada como OBLIGATORIA (M09): la categoría no podrá utilizarse; «Añadir de todos modos»; no la rehabilita', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' }));
  await abrirSelector(f);
  fireEvent.press(screen.getByTestId('selmag-kwhgas'));
  await screen.findByTestId('hoja-anadir-magnitud');
  fireEvent.press(screen.getByTestId('anadir-obligatoria-true'));
  expect(screen.getByText('Esta categoría no podrá utilizarse en registros nuevos mientras esta magnitud siga deshabilitada. Añadirla no la rehabilita.')).toBeTruthy();
  expect(screen.getByText('Añadir de todos modos')).toBeTruthy();
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
  await act(async () => fireEvent.press(screen.getByTestId(`magnitud-fila-${asociacion}`)));
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

// ------------------------------------------------------------------ AJ-S7MAGUI-02: recarga tras un comando con lecturas fallidas
const FALLO = { tipo: 'INDETERMINADO' as const, mensaje: '' };

async function conflictoObligatoriedad(f: ReturnType<typeof fakeMag>, fallos: { arbol?: boolean; catalogo?: boolean }) {
  f.cliente.obligatoriaMagnitud = jest.fn(async () => rechazo('VERSION_DESFASADA'));
  await abrirFicha(f, 'a-pot');
  fireEvent.press(screen.getByTestId('ficha-obligatoriedad'));
  await screen.findByTestId('hoja-obligatoriedad');
  if (fallos.arbol) (f.cliente.arbolCategorias as jest.Mock).mockResolvedValueOnce(FALLO);
  if (fallos.catalogo) (f.cliente.catalogoMagnitudes as jest.Mock).mockResolvedValueOnce(FALLO);
  await act(async () => fireEvent.press(screen.getByTestId('obligatoriedad-confirmar')));
  await screen.findByTestId('magnitudes-aviso');
}

test('conflicto VERSION_DESFASADA y fallo del ÁRBOL al recargar: estado posiblemente desfasado con «Reintentar»; nunca «Se ha recargado»', async () => {
  const f = fakeMag();
  await conflictoObligatoriedad(f, { arbol: true });
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').titulo)).toBeTruthy();
  expect(screen.getByText('No se ha podido comprobar el estado actual de Luz. Lo que ves puede estar desfasado.')).toBeTruthy();
  expect(screen.queryByText(AVISO_CAMBIADAS('Luz').texto)).toBeNull();
  expect(screen.queryByText(/Se ha recargado el estado actual/)).toBeNull();
  expect(screen.getByText('Magnitudes · 2')).toBeTruthy(); // se conserva lo mostrado
  // Reintentar relanza SOLO las lecturas; con ambas OK, ya puede afirmarse la recarga.
  const arboles = (f.cliente.arbolCategorias as jest.Mock).mock.calls.length;
  const catalogos = (f.cliente.catalogoMagnitudes as jest.Mock).mock.calls.length;
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-aviso-reintentar')));
  expect((f.cliente.arbolCategorias as jest.Mock).mock.calls.length).toBe(arboles + 1);
  expect((f.cliente.catalogoMagnitudes as jest.Mock).mock.calls.length).toBe(catalogos + 1);
  expect(f.cliente.obligatoriaMagnitud).toHaveBeenCalledTimes(1);
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').texto)).toBeTruthy();
  expect(screen.queryByTestId('magnitudes-aviso-reintentar')).toBeNull();
});

test('conflicto VERSION_DESFASADA y fallo del CATÁLOGO al recargar: estado posiblemente desfasado; el catálogo mostrado se conserva', async () => {
  const f = fakeMag();
  await conflictoObligatoriedad(f, { catalogo: true });
  expect(screen.getByText('No se ha podido comprobar el estado actual de Luz. Lo que ves puede estar desfasado.')).toBeTruthy();
  expect(screen.queryByText(/Se ha recargado el estado actual/)).toBeNull();
  expect(screen.getByTestId('magnitudes-aviso-reintentar')).toBeTruthy();
  expect(screen.queryByTestId('magnitudes-error')).toBeNull(); // no se presenta como error de carga
  expect(screen.getByTestId('magnitud-fila-a-kwh')).toBeTruthy();
  // Reintentar que vuelve a fallar: el aviso sigue identificando el estado como desfasado.
  (f.cliente.catalogoMagnitudes as jest.Mock).mockResolvedValueOnce(FALLO);
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-aviso-reintentar')));
  expect(screen.getByText(TEXTO_DESFASADO('Luz'))).toBeTruthy();
  expect(f.cliente.obligatoriaMagnitud).toHaveBeenCalledTimes(1);
});

test('conflicto VERSION_DESFASADA con las dos lecturas OK: aviso de recarga correcto, sin «Reintentar»', async () => {
  const f = fakeMag();
  await conflictoObligatoriedad(f, {});
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').texto)).toBeTruthy();
  expect(screen.queryByText(TEXTO_DESFASADO('Luz'))).toBeNull();
  expect(screen.queryByTestId('magnitudes-aviso-reintentar')).toBeNull();
});

test('comando OK y fallo de la recarga con la ficha abierta: «Cambio guardado» y estado posiblemente desfasado en la ficha', async () => {
  const f = fakeMag();
  f.cliente.obligatoriaMagnitud = jest.fn(async () => ({
    tipo: 'OK' as const,
    datos: { categoria_id: 'luz', asociacion: { asociacion_id: 'a-pot', magnitud_id: 'pot', obligatoria: true, orden: 1 }, magnitud: { ...CATALOGO[4] }, idempotente: false, modificadas: ['a-pot'] },
  }));
  await abrirFicha(f, 'a-pot');
  fireEvent.press(screen.getByTestId('ficha-obligatoriedad'));
  (f.cliente.arbolCategorias as jest.Mock).mockResolvedValueOnce(FALLO);
  await act(async () => fireEvent.press(screen.getByTestId('obligatoriedad-confirmar')));
  expect(screen.getByTestId('ficha-magnitud')).toBeTruthy();
  expect(screen.getByText('Cambio guardado')).toBeTruthy();
  expect(screen.getByText('No se ha podido comprobar el estado actual de Luz. Lo que ves puede estar desfasado.')).toBeTruthy();
  expect(screen.getByText(TITULO_GUARDADO)).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-aviso-reintentar')));
  expect(screen.queryByTestId('magnitudes-aviso')).toBeNull();
  expect(f.cliente.obligatoriaMagnitud).toHaveBeenCalledTimes(1);
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

// ------------------------------------------------------------------ hito 2: alta NUEVA y colisión (M07, M08)
const okAsociacion = (aid: string, mid: string, oblig: boolean) => ({
  tipo: 'OK' as const,
  datos: { categoria_id: 'luz', asociacion: { asociacion_id: aid, magnitud_id: mid, obligatoria: oblig, orden: 2 }, magnitud: { ...CATALOGO[3], id: mid }, idempotente: false, modificadas: [aid] },
});

async function abrirNueva(f: ReturnType<typeof fakeMag>) {
  await abrirSelector(f);
  await act(async () => fireEvent.press(screen.getByTestId('selmag-nueva')));
  await screen.findByTestId('nueva-magnitud');
}

function rellenar(nombre = 'Horas', unidad = 'h', decimales = '0', obligatoria: boolean | null = true) {
  fireEvent.changeText(screen.getByTestId('nuevamag-nombre'), nombre);
  fireEvent.changeText(screen.getByTestId('nuevamag-unidad'), unidad);
  fireEvent.press(screen.getByTestId(`nuevamag-decimales-${decimales}`));
  if (obligatoria !== null) fireEvent.press(screen.getByTestId(`nuevamag-obligatoria-${obligatoria}`));
}

test('alta NUEVA: desactivada hasta completar con «Para crear falta», sin preselecciones; envío exacto', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => okAsociacion('a-h', 'h', true));
  await abrirNueva(f);
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  expect(screen.getByTestId('nuevamag-crear')).toBeDisabled();
  expect(texto('nuevamag-faltan')).toBe('Para crear falta: nombre, unidad, decimales y si es obligatoria.');
  rellenar('  Horas   extra ', ' h ', '0', null);
  expect(texto('nuevamag-faltan')).toBe('Para crear falta: si es obligatoria.');
  expect(screen.getByTestId('nuevamag-crear')).toBeDisabled();
  fireEvent.press(screen.getByTestId('nuevamag-obligatoria-true'));
  expect(screen.queryByTestId('nuevamag-faltan')).toBeNull();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
  const [catId, cuerpo] = (f.cliente.asociarMagnitud as jest.Mock).mock.calls[0];
  expect(catId).toBe('luz');
  expect(cuerpo).toEqual({ origen: 'NUEVA', obligatoria: true, magnitud: { magnitud_id: expect.any(String), nombre: 'Horas extra', unidad_default: 'h', precision_decimales: 0 } });
  await screen.findByTestId('detalle-categoria');
});

test('alta NUEVA: el reintento tras indeterminado reenvía el MISMO magnitud_id; editar renueva la identidad', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' }));
  await abrirNueva(f);
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-aviso');
  expect(screen.getByText(AVISO_NUEVA_INDETERMINADO)).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  const ids = (f.cliente.asociarMagnitud as jest.Mock).mock.calls.map((c) => c[1].magnitud.magnitud_id);
  expect(ids).toHaveLength(2);
  expect(ids[1]).toBe(ids[0]);
  fireEvent.changeText(screen.getByTestId('nuevamag-nombre'), 'Horas 2');
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  const ids3 = (f.cliente.asociarMagnitud as jest.Mock).mock.calls.map((c) => c[1].magnitud.magnitud_id);
  expect(ids3[2]).not.toBe(ids3[0]);
});

test('alta NUEVA: IDENTIDAD_REUTILIZADA avisa y no reintenta sola', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => rechazo('IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION'));
  await abrirNueva(f);
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  expect(screen.getByText(AVISO_NUEVA_REUTILIZADA)).toBeTruthy();
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
});

test('colisión con una existente activa (M08): aviso junto al nombre y «Usar» asocia EXISTENTE con la obligatoriedad elegida', async () => {
  const f = fakeMag();
  const llamadas: unknown[] = [];
  f.cliente.asociarMagnitud = jest.fn(async (_c, cuerpo) => {
    llamadas.push(cuerpo);
    return llamadas.length === 1 ? rechazo('MAGNITUD_NOMBRE_DUPLICADO', { magnitud_id: 'km', enabled: true }) : okAsociacion('a-km', 'km', false);
  });
  await abrirNueva(f);
  rellenar('kilometros', 'km', '1', false);
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-colision');
  expect(screen.getByText('Ya existe «Kilómetros»')).toBeTruthy();
  expect(screen.getByText('km · 1 decimal · sin categorías. No se crea otra: puedes usar la existente.')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-usar')));
  expect(llamadas[1]).toEqual({ origen: 'EXISTENTE', magnitud_id: 'km', obligatoria: false });
  expect(f.cliente.rehabilitarMagnitud).not.toHaveBeenCalled();
  await screen.findByTestId('detalle-categoria');
});

test('colisión con una deshabilitada: «Rehabilitar y usarla» encadena dos llamadas; la segunda solo si la primera confirma', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => rechazo('MAGNITUD_NOMBRE_DUPLICADO', { magnitud_id: 'kwhgas', enabled: false }));
  f.cliente.rehabilitarMagnitud = jest.fn(async () => rechazo('VERSION_DESFASADA'));
  await abrirNueva(f);
  rellenar('consumo de gas', 'kWh', '2', true);
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-colision');
  expect(screen.getByText('Ya existe «Consumo de gas» (deshabilitada)')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-rehabilitar')));
  expect(f.cliente.rehabilitarMagnitud).toHaveBeenCalledWith('kwhgas', { row_version: 1 });
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1); // la primera no confirmó: no hay segunda
  await screen.findByTestId('magnitudes-aviso');
  expect(screen.getByText(AVISO_CAMBIADAS('Luz').titulo)).toBeTruthy();
});

test('rehabilitar y usar (AJ-08): la rehabilitación confirma y la asociación falla: hoja que reintenta SOLO la asociación', async () => {
  const f = fakeMag();
  const respuestas = [
    rechazo('MAGNITUD_NOMBRE_DUPLICADO', { magnitud_id: 'kwhgas', enabled: false }),
    { tipo: 'INDETERMINADO' as const, mensaje: '' },
    okAsociacion('a-kwhgas', 'kwhgas', true),
  ];
  f.cliente.asociarMagnitud = jest.fn(async () => respuestas.shift()!);
  f.cliente.rehabilitarMagnitud = jest.fn(async () => ({ tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[2], enabled: true, row_version: 2 }, idempotente: false, modificadas: ['kwhgas'] } }));
  await abrirNueva(f);
  rellenar('consumo de gas', 'kWh', '2', true);
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-colision');
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-rehabilitar')));
  await screen.findByTestId('hoja-asociar-pendiente');
  expect(screen.getByText('“Consumo de gas” ya está rehabilitada, pero no se ha podido añadir a Luz.')).toBeTruthy();
  expect(screen.getByText(TEXTO_ASOCIAR_PENDIENTE('Consumo de gas', 'Luz'))).toBeTruthy();
  expect(screen.getByText('Añadir a Luz')).toBeTruthy();
  expect(screen.getByText('Ahora no')).toBeTruthy();
  expect(f.cliente.rehabilitarMagnitud).toHaveBeenCalledTimes(1);
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(2);
  await act(async () => fireEvent.press(screen.getByTestId('pendiente-anadir')));
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(3);
  expect((f.cliente.asociarMagnitud as jest.Mock).mock.calls[2][1]).toEqual({ origen: 'EXISTENTE', magnitud_id: 'kwhgas', obligatoria: true });
  expect(f.cliente.rehabilitarMagnitud).toHaveBeenCalledTimes(1); // nunca se repite la rehabilitación
  await screen.findByTestId('detalle-categoria');
});

test('rehabilitar y usar (AJ-08): «Ahora no» cierra sin más llamadas', async () => {
  const f = fakeMag();
  const respuestas = [rechazo('MAGNITUD_NOMBRE_DUPLICADO', { magnitud_id: 'kwhgas', enabled: false }), rechazo('ASOCIACION_YA_EXISTE')];
  f.cliente.asociarMagnitud = jest.fn(async () => respuestas.shift()!);
  f.cliente.rehabilitarMagnitud = jest.fn(async () => ({ tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[2], enabled: true, row_version: 2 }, idempotente: false, modificadas: ['kwhgas'] } }));
  await abrirNueva(f);
  rellenar('consumo de gas', 'kWh', '2', false);
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-colision');
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-rehabilitar')));
  await screen.findByTestId('hoja-asociar-pendiente');
  fireEvent.press(screen.getByTestId('pendiente-ahora-no'));
  await screen.findByTestId('detalle-categoria');
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(2);
  expect(f.cliente.rehabilitarMagnitud).toHaveBeenCalledTimes(1);
});

test('colisión SIN detalle (residual): mensaje genérico y «Recargar catálogo»; nunca crea otra', async () => {
  const f = fakeMag();
  f.cliente.asociarMagnitud = jest.fn(async () => rechazo('MAGNITUD_NOMBRE_DUPLICADO'));
  await abrirNueva(f);
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-crear')));
  await screen.findByTestId('nuevamag-colision-generica');
  expect(screen.getByText(COLISION_GENERICA)).toBeTruthy();
  const cargas = (f.cliente.catalogoMagnitudes as jest.Mock).mock.calls.length;
  await act(async () => fireEvent.press(screen.getByTestId('nuevamag-recargar')));
  expect((f.cliente.catalogoMagnitudes as jest.Mock).mock.calls.length).toBe(cargas + 1);
  expect(f.cliente.asociarMagnitud).toHaveBeenCalledTimes(1);
});

// ------------------------------------------------------------------ hito 2: Editar orden (M10)
test('Editar orden: UNA llamada con el conjunto COMPLETO y el estado cargado', async () => {
  const f = fakeMag();
  f.cliente.reordenarMagnitudes = jest.fn(async () => ({ tipo: 'OK' as const, datos: { categoria_id: 'luz', asociaciones: [], idempotente: false, modificadas: ['a-kwh', 'a-pot'] } }));
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  await desplegar();
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-editar-orden')));
  await screen.findByTestId('orden-magnitudes');
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  expect(screen.getByTestId('ordenmag-subir-a-kwh')).toBeDisabled();
  fireEvent.press(screen.getByTestId('ordenmag-bajar-a-kwh'));
  await act(async () => fireEvent.press(screen.getByTestId('ordenmag-guardar')));
  expect(f.cliente.reordenarMagnitudes).toHaveBeenCalledTimes(1);
  expect(f.cliente.reordenarMagnitudes).toHaveBeenCalledWith('luz', { asociaciones: [
    { asociacion_id: 'a-pot', magnitud_id: 'pot', orden: 1, obligatoria: false },
    { asociacion_id: 'a-kwh', magnitud_id: 'kwh', orden: 0, obligatoria: true },
  ] });
});

test('Editar orden sin cambios: no envía nada y avisa «Sin cambios»', async () => {
  const f = fakeMag();
  await abrirDetalle(f.cliente, 'luz', { dentroDe: 'hogar' });
  await desplegar();
  await act(async () => fireEvent.press(screen.getByTestId('magnitudes-editar-orden')));
  await act(async () => fireEvent.press(screen.getByTestId('ordenmag-guardar')));
  expect(f.cliente.reordenarMagnitudes).not.toHaveBeenCalled();
  expect(screen.getByText(AVISO_SIN_CAMBIOS_ORDEN.titulo)).toBeTruthy();
});

// ------------------------------------------------------------------ hito 2: ficha global (M13), renombrar, deshabilitar, rehabilitar
test('ficha (M13): datos, R17, «Usada en» con la actual marcada, registros históricos y acciones', async () => {
  const f = fakeMag();
  await abrirFicha(f, 'a-kwh');
  expect(screen.getByTestId('bloque-unidad').props.accessibilityLabel).toBe('Unidad: kWh');
  expect(screen.getByTestId('bloque-decimales').props.accessibilityLabel).toBe('Decimales: 2');
  expect(screen.getByTestId('bloque-estado').props.accessibilityLabel).toBe('Estado: Activa');
  expect(screen.getByText(NOTA_R17)).toBeTruthy();
  expect(screen.getByTestId('usada-luz').props.accessibilityLabel).toBe('Hogar › Luz. esta categoría. Obligatoria');
  expect(screen.getByText(TEXTO_HISTORICOS(6))).toBeTruthy();
  expect(screen.getByTestId('bloque-renombrar')).toBeTruthy();
  expect(screen.getByTestId('bloque-deshabilitar')).toBeTruthy();
  expect(screen.queryByTestId('bloque-rehabilitar')).toBeNull();
});

test('renombrar: payload con row_version y colisión junto al nombre sin cerrar la hoja', async () => {
  const f = fakeMag();
  f.cliente.renombrarMagnitud = jest.fn(async () => rechazo('MAGNITUD_NOMBRE_DUPLICADO', { magnitud_id: 'm3', enabled: true }));
  await abrirFicha(f, 'a-kwh');
  fireEvent.press(screen.getByTestId('bloque-renombrar'));
  await screen.findByTestId('hoja-renombrar-magnitud');
  fireEvent.changeText(screen.getByTestId('renmag-nombre'), 'consumo de agua');
  await act(async () => fireEvent.press(screen.getByTestId('renmag-guardar')));
  expect(f.cliente.renombrarMagnitud).toHaveBeenCalledWith('kwh', { nombre: 'consumo de agua', row_version: 1 });
  expect(texto('renmag-error')).toBe(MSG_RENOMBRAR_DUPLICADO('Consumo de agua'));
  expect(screen.getByTestId('hoja-renombrar-magnitud')).toBeTruthy();
});

test('deshabilitar SIN impacto (D59): confirmación simple antes de enviar; Cancelar no envía nada', async () => {
  const f = fakeMag();
  f.cliente.deshabilitarMagnitud = jest.fn(async () => ({ tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[4], enabled: false, row_version: 2 }, idempotente: false, modificadas: ['pot'] } }));
  await abrirFicha(f, 'a-pot');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await screen.findByTestId('hoja-confirmar-deshabilitar');
  expect(screen.getByText('¿Deshabilitar «Potencia contratada»?')).toBeTruthy();
  expect(screen.getByText(TEXTO_CONFIRMAR_DESHABILITAR)).toBeTruthy();
  expect(f.cliente.deshabilitarMagnitud).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('confirmar-deshabilitar-cancelar'));
  expect(screen.queryByTestId('hoja-confirmar-deshabilitar')).toBeNull();
  expect(f.cliente.deshabilitarMagnitud).not.toHaveBeenCalled();
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await act(async () => fireEvent.press(screen.getByTestId('confirmar-deshabilitar')));
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledTimes(1);
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledWith('pot', { row_version: 1, confirmacion_impacto: null });
  await waitFor(() => expect(screen.queryByTestId('hoja-confirmar-deshabilitar')).toBeNull());
  expect(screen.queryByTestId('hoja-deshabilitar')).toBeNull();
});

test('deshabilitar con impacto visible (D59 corregida): hoja M14 con el impacto del catálogo ANTES de cualquier POST; Cancelar no envía nada', async () => {
  const f = fakeMag();
  await abrirFicha(f, 'a-kwh');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await screen.findByTestId('hoja-deshabilitar');
  expect(screen.queryByTestId('hoja-confirmar-deshabilitar')).toBeNull();
  expect(screen.getByTestId('impacto-luz').props.accessibilityLabel).toBe('Hogar › Luz: obligatoria');
  expect(screen.getByText(NOTA_DESHABILITAR)).toBeTruthy();
  expect(screen.queryByTestId('deshabilitar-cambiado')).toBeNull();
  expect(f.cliente.deshabilitarMagnitud).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('deshabilitar-cancelar'));
  expect(screen.queryByTestId('hoja-deshabilitar')).toBeNull();
  expect(f.cliente.deshabilitarMagnitud).not.toHaveBeenCalled();
});

test('deshabilitar con impacto visible y coincidente: UNA confirmación y UN POST con ese conjunto', async () => {
  const f = fakeMag();
  f.cliente.deshabilitarMagnitud = jest.fn(async () => ({ tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[1], enabled: false, row_version: 2 }, idempotente: false, modificadas: ['kwh'] } }));
  await abrirFicha(f, 'a-kwh');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await act(async () => fireEvent.press(screen.getByTestId('deshabilitar-confirmar')));
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledTimes(1);
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledWith('kwh', { row_version: 1, confirmacion_impacto: ['luz'] });
  await waitFor(() => expect(screen.queryByTestId('hoja-deshabilitar')).toBeNull());
});

test('deshabilitar con impacto visible y el servidor con impacto VACÍO: nunca se deshabilita sin pasar por M14 y, tras el 409, por M15', async () => {
  const f = fakeMag();
  const respuestas = [
    rechazo('MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION', { categorias_no_capturables: [] }),
    { tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[1], enabled: false, row_version: 2 }, idempotente: false, modificadas: ['kwh'] } },
  ];
  f.cliente.deshabilitarMagnitud = jest.fn(async () => respuestas.shift()!);
  await abrirFicha(f, 'a-kwh');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await screen.findByTestId('hoja-deshabilitar');
  expect(f.cliente.deshabilitarMagnitud).not.toHaveBeenCalled();
  await act(async () => fireEvent.press(screen.getByTestId('deshabilitar-confirmar')));
  expect((f.cliente.deshabilitarMagnitud as jest.Mock).mock.calls[0][1]).toEqual({ row_version: 1, confirmacion_impacto: ['luz'] });
  await screen.findByTestId('deshabilitar-cambiado');
  expect(screen.getByText(IMPACTO_CAMBIADO.titulo)).toBeTruthy();
  expect(screen.getByText(IMPACTO_CAMBIADO.textoNeutro)).toBeTruthy();
  expect(screen.queryByTestId('impacto-luz')).toBeNull();
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledTimes(1); // sin reenvío automático
  await act(async () => fireEvent.press(screen.getByTestId('deshabilitar-confirmar')));
  expect((f.cliente.deshabilitarMagnitud as jest.Mock).mock.calls[1][1]).toEqual({ row_version: 1, confirmacion_impacto: [] });
  await waitFor(() => expect(screen.queryByTestId('hoja-deshabilitar')).toBeNull());
});

test('deshabilitar con impacto (M14) y con impacto ampliado (M15): cada envío lo confirma el usuario', async () => {
  const f = fakeMag();
  const respuestas = [
    rechazo('MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION', { categorias_no_capturables: [
      { categoria_id: 'luz', nombre: 'Luz', obligatoria: true }, { categoria_id: 'agua', nombre: 'Agua', obligatoria: true }] }),
    { tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[1], enabled: false, row_version: 2 }, idempotente: false, modificadas: ['kwh'] } },
  ];
  f.cliente.deshabilitarMagnitud = jest.fn(async () => respuestas.shift()!);
  await abrirFicha(f, 'a-kwh');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await screen.findByTestId('hoja-deshabilitar');
  await act(async () => fireEvent.press(screen.getByTestId('deshabilitar-confirmar')));
  expect((f.cliente.deshabilitarMagnitud as jest.Mock).mock.calls[0][1]).toEqual({ row_version: 1, confirmacion_impacto: ['luz'] });
  // M15: el conjunto cambió; se muestra y NO se reenvía solo.
  await screen.findByTestId('deshabilitar-cambiado');
  expect(screen.getByText(IMPACTO_CAMBIADO.titulo)).toBeTruthy();
  expect(screen.getByText(IMPACTO_CAMBIADO.texto)).toBeTruthy();
  expect(screen.getByTestId('impacto-agua').props.accessibilityLabel).toBe('Hogar › Agua: obligatoria · nueva');
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledTimes(1);
  await act(async () => fireEvent.press(screen.getByTestId('deshabilitar-confirmar')));
  expect((f.cliente.deshabilitarMagnitud as jest.Mock).mock.calls[1][1]).toEqual({ row_version: 1, confirmacion_impacto: ['luz', 'agua'] });
  await waitFor(() => expect(screen.queryByTestId('hoja-deshabilitar')).toBeNull());
});

test('deshabilitar SIN impacto visible y el servidor CON impacto: M15 (el usuario confirmó «sin impacto») y nueva confirmación', async () => {
  const f = fakeMag();
  f.cliente.deshabilitarMagnitud = jest.fn(async () =>
    rechazo('MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION', { categorias_no_capturables: [{ categoria_id: 'luz', nombre: 'Luz', obligatoria: true }] }));
  await abrirFicha(f, 'a-pot');
  await act(async () => fireEvent.press(screen.getByTestId('bloque-deshabilitar')));
  await act(async () => fireEvent.press(screen.getByTestId('confirmar-deshabilitar')));
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledWith('pot', { row_version: 1, confirmacion_impacto: null });
  await screen.findByTestId('deshabilitar-cambiado');
  expect(screen.getByText(IMPACTO_CAMBIADO.texto)).toBeTruthy();
  expect(screen.getByTestId('impacto-luz').props.accessibilityLabel).toBe('Hogar › Luz: obligatoria · nueva');
  expect(f.cliente.deshabilitarMagnitud).toHaveBeenCalledTimes(1);
});

test('rehabilitar: confirmación simple con row_version', async () => {
  const f = fakeMag({ catalogo: CATALOGO.map((m) => (m.id === 'kwh' ? { ...m, enabled: false, row_version: 3 } : m)) });
  f.cliente.rehabilitarMagnitud = jest.fn(async () => ({ tipo: 'OK' as const, datos: { magnitud: { ...CATALOGO[1], row_version: 4 }, idempotente: false, modificadas: ['kwh'] } }));
  await abrirFicha(f, 'a-kwh');
  fireEvent.press(screen.getByTestId('bloque-rehabilitar'));
  await screen.findByTestId('hoja-rehabilitar');
  await act(async () => fireEvent.press(screen.getByTestId('rehabilitar-confirmar')));
  expect(f.cliente.rehabilitarMagnitud).toHaveBeenCalledWith('kwh', { row_version: 3 });
});
