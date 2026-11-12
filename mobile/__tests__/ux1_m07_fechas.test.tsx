// ============================================================
// GAPTO MOBILE 2027
// Fichero: ux1_m07_fechas.test.tsx
// Ruta: mobile/__tests__/ux1_m07_fechas.test.tsx
// Descripción: M-07 componente único de fecha (T1-F06 UX-1; DM-06; D-M2-04; §12 del dictamen del tren 1). Dominio:
//   máscara dd/mm/aaaa (solo cifras, borrado, pegado y texto con barras intacto), fechas imposibles (31/02, 29/02 no
//   bisiesto, 31/04, día 0, mes 0 y 13), años 0001–0099 (D-M2-04), dd/mm/aaaa ↔ ISO en las dos direcciones, rejilla
//   del calendario (fin de mes, bisiesto, lunes primero) y meses vecinos. Componente: calendario mensual en JS (mes
//   anterior/siguiente, elegir escribe dd/mm/aaaa, días posteriores a `max` deshabilitados) y máscara al escribir.
//   En el registro de gasto (Raiz): cifras → barras; calendario; cambiar Hoy/Ayer/Otra y abrir/cerrar el calendario no
//   borra el resto del formulario; medianoche civil (el «hoy» del calendario es el del dispositivo, `enZona`).
// Versión: 0.1.0 (F06 T1 UX-1 · M-07)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React, { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Respuesta } from '../src/api/cliente';
import { CampoFecha, mesInicialCalendario } from '../src/components/CampoFecha';
import { ddmmaaaaAIso, enmascararFecha, fechaCortaIso, isoADdmmaaaa, mesAnioIso, mesDesplazadoIso, rejillaMesIso } from '../src/domain/fechas';
import { esFechaIso } from '../src/domain/intencion';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };

/** El de propiedad_valor_fecha.test.tsx (B1): emula el dispositivo en una zona sin depender de TZ. */
function enZona(utc: string, zona: string): Date {
  const d = new Date(utc);
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', { timeZone: zona, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' })
      .formatToParts(d).map((x) => [x.type, Number(x.value)]),
  );
  const civil = new Date(partes.year, partes.month - 1, partes.day, partes.hour, partes.minute);
  Object.assign(d, {
    getFullYear: () => civil.getFullYear(), getMonth: () => civil.getMonth(), getDate: () => civil.getDate(),
    getDay: () => civil.getDay(), getHours: () => civil.getHours(), getMinutes: () => civil.getMinutes(),
  });
  return d;
}

// ------------------------------------------------------------------ máscara
test.each([
  ['0', '0'], ['02', '02'], ['020', '02/0'], ['0203', '02/03'], ['02032', '02/03/2'], ['02032026', '02/03/2026'],
  ['02/032', '02/03/2'], ['02/03/2026', '02/03/2026'], ['', ''],
])('máscara: solo cifras «%s» → «%s»', (entrada, salida) => {
  expect(enmascararFecha(entrada)).toBe(salida);
});

test('máscara: borrado hacia atrás quita la barra que la máscara puso', () => {
  expect(enmascararFecha('02/03/')).toBe('02/03');
  expect(enmascararFecha('02/0')).toBe('02/0');
  expect(enmascararFecha('02/')).toBe('02');
});

test.each([
  ['1/1/26'], ['6/11'], ['25/9/2026'], ['2.3.2026'], ['ab/cd/efgh'], ['123456789'], ['02/03/20261'],
])('máscara: «%s» (barras en otra posición, letras, puntos o más de 8 cifras) se respeta tal cual', (t) => {
  expect(enmascararFecha(t)).toBe(t);
});

test('máscara: pegar 8 cifras da la fecha con barras; y la máscara no valida (31/02 sigue sin ser fecha)', () => {
  expect(enmascararFecha('31022026')).toBe('31/02/2026');
  expect(esFechaIso(ddmmaaaaAIso(enmascararFecha('31022026'))!)).toBe(false);
});

// ------------------------------------------------------------------ validación y conversión
test.each([
  ['2026-02-31', '31/02'], ['2026-02-29', '29/02 de un año no bisiesto'], ['2026-04-31', '31/04'], ['2026-03-00', 'día 0'],
  ['2026-00-10', 'mes 0'], ['2026-13-10', 'mes 13'], ['0050-02-29', '29/02 del año 50 (no bisiesto)'],
])('fecha imposible %s (%s) → no', (iso) => {
  expect(esFechaIso(iso)).toBe(false);
});

test.each([['0050-06-15'], ['0001-01-01'], ['0099-12-31'], ['0048-02-29'], ['2028-02-29'], ['1990-01-01']])(
  'D-M2-04: %s existe y se acepta (antes los años 0–99 pasaban a 1900–1999)', (iso) => {
    expect(esFechaIso(iso)).toBe(true);
  },
);

test('dd/mm/aaaa ↔ ISO en las dos direcciones, también con años 0001–0099', () => {
  for (const iso of ['2026-11-12', '0050-06-15', '0001-01-01', '2028-02-29']) expect(ddmmaaaaAIso(isoADdmmaaaa(iso))).toBe(iso);
  expect(ddmmaaaaAIso('15/06/0050')).toBe('0050-06-15');
  expect(isoADdmmaaaa('0050-06-15')).toBe('15/06/0050');
  expect(fechaCortaIso('0050-06-15')).toMatch(/, 15 jun 50$/); // año 50, no 1950
  expect(mesAnioIso('0050-06-15')).toBe('Junio 50');
});

// ------------------------------------------------------------------ calendario (dominio)
test('rejilla del mes: lunes primero, fin de mes y bisiesto', () => {
  const nov = rejillaMesIso('2026-11-01'); // 1/11/2026 es domingo
  expect(nov[0]).toEqual([null, null, null, null, null, null, '2026-11-01']);
  expect(nov[nov.length - 1].filter(Boolean).pop()).toBe('2026-11-30');
  expect(rejillaMesIso('2028-02-10').flat().filter(Boolean).pop()).toBe('2028-02-29');
  expect(rejillaMesIso('2026-02-10').flat().filter(Boolean).pop()).toBe('2026-02-28');
  expect(rejillaMesIso('2026-06-01')[0][0]).toBe('2026-06-01'); // 1/6/2026 es lunes
  for (const semana of rejillaMesIso('2026-08-01')) expect(semana).toHaveLength(7);
  expect(rejillaMesIso('0050-06-01').flat().filter(Boolean)[0]).toBe('0050-06-01');
});

test('meses vecinos y mes inicial del calendario', () => {
  expect(mesDesplazadoIso('2026-12-15', 1)).toBe('2027-01-01');
  expect(mesDesplazadoIso('2026-01-15', -1)).toBe('2025-12-01');
  expect(mesDesplazadoIso('0050-01-01', -1)).toBe('0049-12-01');
  expect(mesInicialCalendario('15/03/2025', '2026-11-12')).toBe('2025-03-01'); // la fecha escrita
  expect(mesInicialCalendario('31/02/2025', '2026-11-12')).toBe('2026-11-01'); // no existe: el de hoy
  expect(mesInicialCalendario(null, '2026-11-12')).toBe('2026-11-01');
});

// ------------------------------------------------------------------ componente
function Prueba(p: { max?: string; inicial?: string | null }) {
  const [t, setT] = useState<string | null>(p.inicial === undefined ? '' : p.inicial);
  return (
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CampoFecha testID="f" etiqueta="Fecha" hoyIso="2026-11-12" max={p.max} texto={t} onTexto={setT}
          opciones={[{ testID: 'f-otra', etiqueta: 'Otra fecha', seleccionado: t !== null, onPress: () => setT('') }, { testID: 'f-hoy', etiqueta: 'Hoy', seleccionado: t === null, onPress: () => setT(null) }]} />
      </ProveedorTema>
    </SafeAreaProvider>
  );
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));

test('CampoFecha: escribir cifras pone las barras; un texto con barras se respeta', async () => {
  render(<Prueba />);
  await act(async () => fireEvent.changeText(screen.getByTestId('f'), '25092026'));
  expect(screen.getByTestId('f').props.value).toBe('25/09/2026');
  await act(async () => fireEvent.changeText(screen.getByTestId('f'), '1/1/26'));
  expect(screen.getByTestId('f').props.value).toBe('1/1/26');
  expect(screen.getByTestId('f').props.inputMode).toBe('numeric');
});

test('CampoFecha: calendario mensual: mes anterior/siguiente, elegir escribe dd/mm/aaaa y se cierra', async () => {
  render(<Prueba inicial="15/03/2025" />);
  await pulsar('f-calendario');
  expect(screen.getByTestId('f-cal-mes').props.children).toBe('Marzo 2025');
  await pulsar('f-cal-siguiente');
  expect(screen.getByTestId('f-cal-mes').props.children).toBe('Abril 2025');
  await pulsar('f-cal-anterior');
  await pulsar('f-cal-anterior');
  expect(screen.getByTestId('f-cal-mes').props.children).toBe('Febrero 2025');
  expect(screen.queryByTestId('f-cal-2025-02-29')).toBeNull(); // 2025 no es bisiesto
  await pulsar('f-cal-2025-02-28');
  expect(screen.getByTestId('f').props.value).toBe('28/02/2025');
  expect(screen.queryByTestId('f-cal')).toBeNull();
});

test('CampoFecha: con `max`, los días posteriores están deshabilitados y no se pueden elegir', async () => {
  render(<Prueba max="2026-11-12" inicial="" />);
  await pulsar('f-calendario');
  expect(screen.getByTestId('f-cal-mes').props.children).toBe('Noviembre 2026');
  expect(screen.getByTestId('f-cal-2026-11-13').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('f-cal-2026-11-12').props.accessibilityState.disabled).toBe(false);
  await pulsar('f-cal-2026-11-13');
  expect(screen.getByTestId('f').props.value).toBe('');
  await pulsar('f-cal-2026-11-12');
  expect(screen.getByTestId('f').props.value).toBe('12/11/2026');
});

test('CampoFecha: sin `max` (valoración, C-PROP-04) cualquier día del futuro se puede elegir', async () => {
  render(<Prueba inicial="" />);
  await pulsar('f-calendario');
  await pulsar('f-cal-siguiente');
  expect(screen.getByTestId('f-cal-2026-12-31').props.accessibilityState.disabled).toBe(false);
  await pulsar('f-cal-2026-12-31');
  expect(screen.getByTestId('f').props.value).toBe('31/12/2026');
});

test('CampoFecha: con «Hoy» (texto null) no hay campo ni calendario', async () => {
  render(<Prueba inicial={null} />);
  expect(screen.queryByTestId('f')).toBeNull();
  expect(screen.queryByTestId('f-calendario')).toBeNull();
});

// ------------------------------------------------------------------ registro de gasto (Raiz)
const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
function cliente(): ClienteApi {
  return {
    ...clienteCategoriasStub([nodo({ id: 'alim', nombre: 'Alimentación' })]),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarPlantillas: jest.fn(async () => ({ tipo: 'OK', datos: { plantillas: [], acciones: [] } }) as any),
  } as ClienteApi;
}
async function abrirRegistro(ahora: () => Date) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente()} nuevoId={() => '00000000-0000-4000-8000-000000000001'} ahora={ahora} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await screen.findByTestId('accion-registrar');
  await pulsar('accion-registrar');
  await pulsar('tipo-GASTO');
}

test('registro: cifras → barras; Hoy/Ayer/Otra y abrir/cerrar el calendario no borran el resto del formulario', async () => {
  await abrirRegistro(() => new Date(2026, 10, 12, 10));
  fireEvent.changeText(screen.getByTestId('campo-importe'), '12,50');
  await pulsar('fecha-otra');
  await act(async () => fireEvent.changeText(screen.getByTestId('campo-fecha'), '03112026'));
  expect(screen.getByTestId('campo-fecha').props.value).toBe('03/11/2026');
  expect(screen.getByTestId('fecha').props.children).toBe('Mar, 3 nov 2026 · fecha del gasto y del pago');
  await pulsar('campo-fecha-calendario');
  expect(screen.getByTestId('campo-fecha-cal-mes').props.children).toBe('Noviembre 2026');
  expect(screen.getByTestId('campo-fecha-cal-2026-11-13').props.accessibilityState.disabled).toBe(true); // ≤ hoy
  await pulsar('campo-fecha-calendario'); // cerrar
  expect(screen.queryByTestId('campo-fecha-cal')).toBeNull();
  await pulsar('campo-fecha-calendario');
  await pulsar('campo-fecha-cal-2026-11-05');
  expect(screen.getByTestId('fecha').props.children).toBe('Jue, 5 nov 2026 · fecha del gasto y del pago');
  await pulsar('fecha-ayer');
  await pulsar('fecha-hoy');
  await pulsar('fecha-otra');
  expect(screen.getByTestId('campo-importe').props.value).toBe('12,50'); // nada se ha perdido
});

test('registro: 31/02 sigue rechazándose con el mismo texto', async () => {
  await abrirRegistro(() => new Date(2026, 10, 12, 10));
  await pulsar('fecha-otra');
  await act(async () => fireEvent.changeText(screen.getByTestId('campo-fecha'), '31022026'));
  expect(screen.getByTestId('fecha').props.children).toBe('Escribe la fecha como dd/mm/aaaa.');
});

test('medianoche civil: Europe/Madrid a las 00:30 (en UTC aún es ayer): el calendario deja elegir el día civil y no el siguiente', async () => {
  const ahora = () => enZona('2026-11-05T23:30:00Z', 'Europe/Madrid');
  await abrirRegistro(ahora);
  await pulsar('fecha-otra');
  await pulsar('campo-fecha-calendario');
  expect(screen.getByTestId('campo-fecha-cal-2026-11-06').props.accessibilityState.disabled).toBe(false);
  expect(screen.getByTestId('campo-fecha-cal-2026-11-07').props.accessibilityState.disabled).toBe(true);
});
