// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedad_valor_fecha.test.tsx
// Ruta: mobile/__tests__/propiedad_valor_fecha.test.tsx
// Descripción: Selector «Hoy · Ayer · Otra fecha» de la nueva valoración D3 (F06-01 B1 · C-PROP-04; AJ-B1C-01, PC-B1-04 condiciones 1–4). Propuesta Hoy; Hoy y Ayer en la fecha civil del dispositivo (no en UTC), también cerca de la medianoche civil en las dos direcciones (Europe/Madrid a las 00:30, cuando en UTC aún es ayer; America/New_York a las 23:30, cuando en UTC ya es mañana; el dispositivo en esa zona se emula con un `Date` del instante real cuyos métodos locales dan la hora civil de la zona, porque Jest aísla `process.env` y cambiar TZ dentro del test no cambia la zona) y en el cambio de mes y de año; «Otra fecha» con el campo dd/mm/aaaa y los límites del calendario del contrato publicado (una fecha que exista: 29/02 solo en bisiesto; ni 31/04 ni 00/01 ni mes 13; sin mínimo ni máximo, porque C-PROP-04 no los fija); y la petición exacta: `fecha_valoracion` en ISO y ni un campo más ni uno menos.
// Versión: 0.1.0 (F06-01 B1 MANT N3 del selector)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClientePropiedades, PayloadValoracion, VistaPropiedad } from '../src/api/propiedades';
import { faltaValor, ValoracionFormScreen } from '../src/screens/PropiedadValorScreen';
import { ProveedorTema } from '../src/theme/tema';

/** El instante `utc` visto por un dispositivo en la zona `zona`: los métodos locales que usa domain/fechas dan la hora civil de esa zona. */
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

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const CAMPOS_PETICION = ['fecha_valoracion', 'fuente', 'intencion_id', 'metodo', 'notas', 'row_version_esperada', 'valor_total'];

const VISTA: VistaPropiedad = {
  id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 3, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: null, superficie_m2: null,
  superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
  incluir_en_rentabilidad: true, notas: null, fecha_consulta: '2026-11-06', titularidad: { modo: 'DESCONOCIDA', desde: null, partes: [] },
  cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [],
};

function montar(ahora: () => Date) {
  const enviados: PayloadValoracion[] = [];
  const api = {
    altaValoracion: jest.fn(async (_id: string, c: PayloadValoracion) => {
      enviados.push(c);
      return { tipo: 'OK', datos: { propiedad: VISTA, idempotente: false, modificadas: ['p1'], avisos: [] } };
    }),
  } as unknown as ClientePropiedades;
  const onCerrar = jest.fn();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <ValoracionFormScreen propiedades={api} vista={VISTA} nuevoId={() => '00000000-0000-4000-8000-000000000001'} ahora={ahora} onCerrar={onCerrar} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { api, enviados, onCerrar };
}

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const marcado = (id: string) => screen.getByTestId(id).props.accessibilityState.checked;
const textoFecha = () => screen.getByTestId('prop-val-fecha-elegida').props.children;
const deshabilitado = () => screen.getByTestId('prop-val-guardar').props.accessibilityState.disabled;

async function completarYGuardar() {
  await escribir('prop-val-valor', '250.000,00');
  await pulsar('prop-val-metodo-MERCADO');
  await pulsar('prop-val-guardar');
}

test('propuesta Hoy: marcado, sin campo de texto; la petición lleva hoy en ISO y exactamente los campos de C-PROP-04', async () => {
  const { enviados } = montar(() => new Date(2026, 10, 6, 10));
  expect(marcado('prop-val-hoy')).toBe(true);
  expect(marcado('prop-val-ayer')).toBe(false);
  expect(marcado('prop-val-otra')).toBe(false);
  expect(screen.queryByTestId('prop-val-fecha')).toBeNull();
  expect(textoFecha()).toBe('Vie, 6 nov 2026');
  await completarYGuardar();
  expect(enviados).toHaveLength(1);
  expect(Object.keys(enviados[0]).sort()).toEqual(CAMPOS_PETICION);
  expect(enviados[0]).toEqual({
    intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 3, valor_total: '250000.00', fecha_valoracion: '2026-11-06',
    metodo: 'MERCADO', fuente: null, notas: null,
  });
});

test('Ayer: marca Ayer, desmarca Hoy y envía el día anterior; volver a Hoy envía hoy', async () => {
  const { enviados } = montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-ayer');
  expect(marcado('prop-val-ayer')).toBe(true);
  expect(marcado('prop-val-hoy')).toBe(false);
  expect(textoFecha()).toBe('Jue, 5 nov 2026');
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('2026-11-05');
});

test('Hoy tras Ayer: vuelve a hoy', async () => {
  const { enviados } = montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-ayer');
  await pulsar('prop-val-hoy');
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('2026-11-06');
});

test('Ayer en el cambio de mes y de año (1 de enero → 31 de diciembre) y de 1 de marzo bisiesto → 29 de febrero', async () => {
  const a = montar(() => new Date(2027, 0, 1, 9));
  await pulsar('prop-val-ayer');
  await completarYGuardar();
  expect(a.enviados[0].fecha_valoracion).toBe('2026-12-31');
  screen.unmount();
  const b = montar(() => new Date(2028, 2, 1, 9));
  await pulsar('prop-val-ayer');
  await completarYGuardar();
  expect(b.enviados[0].fecha_valoracion).toBe('2028-02-29');
});

test('medianoche civil: Europe/Madrid a las 00:30, cuando en UTC aún es ayer, Hoy y Ayer son los civiles', async () => {
  const ahora = () => enZona('2026-11-05T23:30:00Z', 'Europe/Madrid');
  expect(ahora().toISOString().slice(0, 10)).toBe('2026-11-05'); // la fecha UTC es otra: la prueba discrimina
  expect([ahora().getDate(), ahora().getHours(), ahora().getMinutes()]).toEqual([6, 0, 30]);
  const a = montar(ahora);
  expect(textoFecha()).toBe('Vie, 6 nov 2026');
  await completarYGuardar();
  expect(a.enviados[0].fecha_valoracion).toBe('2026-11-06');
  screen.unmount();
  const b = montar(ahora);
  await pulsar('prop-val-ayer');
  await completarYGuardar();
  expect(b.enviados[0].fecha_valoracion).toBe('2026-11-05');
});

test('medianoche civil: America/New_York a las 23:30, cuando en UTC ya es mañana, Hoy y Ayer son los civiles', async () => {
  const ahora = () => enZona('2026-11-07T04:30:00Z', 'America/New_York');
  expect(ahora().toISOString().slice(0, 10)).toBe('2026-11-07'); // la fecha UTC es otra: la prueba discrimina
  expect([ahora().getDate(), ahora().getHours(), ahora().getMinutes()]).toEqual([6, 23, 30]);
  const a = montar(ahora);
  expect(textoFecha()).toBe('Vie, 6 nov 2026');
  await completarYGuardar();
  expect(a.enviados[0].fecha_valoracion).toBe('2026-11-06');
  screen.unmount();
  const b = montar(ahora);
  await pulsar('prop-val-ayer');
  await completarYGuardar();
  expect(b.enviados[0].fecha_valoracion).toBe('2026-11-05');
});

test('si el día cambia con el formulario abierto, Hoy deja de estar marcado y se envía la fecha que se ve', async () => {
  let ahora = new Date(2026, 10, 6, 23, 59);
  const { enviados } = montar(() => ahora);
  ahora = new Date(2026, 10, 7, 0, 1);
  await escribir('prop-val-valor', '250.000,00'); // nuevo render ya en el día siguiente
  expect(marcado('prop-val-hoy')).toBe(false);
  expect(marcado('prop-val-ayer')).toBe(true); // la fecha elegida (6 nov) es ahora «ayer»
  expect(textoFecha()).toBe('Vie, 6 nov 2026');
  await pulsar('prop-val-metodo-MERCADO');
  await pulsar('prop-val-guardar');
  expect(enviados[0].fecha_valoracion).toBe('2026-11-06');
});

test('Otra fecha: abre el campo con la fecha actual en dd/mm/aaaa; lo escrito se envía en ISO', async () => {
  const { enviados } = montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-otra');
  expect(marcado('prop-val-otra')).toBe(true);
  expect(marcado('prop-val-hoy')).toBe(false);
  expect(screen.getByTestId('prop-val-fecha').props.value).toBe('06/11/2026');
  await escribir('prop-val-fecha', '3/7/2025');
  expect(textoFecha()).toBe('Jue, 3 jul 2025');
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('2025-07-03');
  expect(Object.keys(enviados[0]).sort()).toEqual(CAMPOS_PETICION);
});

test('Otra fecha desde Ayer conserva ayer; Hoy cierra el campo', async () => {
  montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-ayer');
  await pulsar('prop-val-otra');
  expect(screen.getByTestId('prop-val-fecha').props.value).toBe('05/11/2026');
  await pulsar('prop-val-hoy');
  expect(screen.queryByTestId('prop-val-fecha')).toBeNull();
  expect(marcado('prop-val-hoy')).toBe(true);
});

test.each([
  ['31/04/2026', 'abril no tiene 31'],
  ['29/02/2026', '2026 no es bisiesto'],
  ['30/02/2028', 'febrero nunca tiene 30'],
  ['00/01/2026', 'día 0'],
  ['15/13/2026', 'mes 13'],
  ['15/00/2026', 'mes 0'],
  ['1/1/26', 'año con 2 cifras'],
  ['6/11', 'sin año'],
  ['', 'vacío'],
])('Otra fecha: «%s» no es una fecha del calendario (%s): no se puede guardar ni se envía', async (texto) => {
  const { api } = montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-otra');
  await escribir('prop-val-fecha', texto);
  await escribir('prop-val-valor', '250.000,00');
  await pulsar('prop-val-metodo-MERCADO');
  expect(textoFecha()).toBe('Escribe la fecha como dd/mm/aaaa.');
  expect(deshabilitado()).toBe(true);
  expect(screen.getByTestId('prop-val-falta').props.children).toBe('Falta: fecha como dd/mm/aaaa');
  await pulsar('prop-val-guardar');
  expect(api.altaValoracion).not.toHaveBeenCalled();
});

test.each([
  ['29/02/2028', '2028-02-29', 'bisiesto'],
  ['31/12/2026', '2026-12-31', 'fin de año'],
  ['01/01/1990', '1990-01-01', 'muy antigua: el contrato no fija mínimo'],
  ['15/03/2030', '2030-03-15', 'futura: el contrato no fija máximo'],
])('Otra fecha: «%s» se acepta y se envía %s (%s)', async (texto, iso) => {
  const { enviados } = montar(() => new Date(2026, 10, 6, 10));
  await pulsar('prop-val-otra');
  await escribir('prop-val-fecha', texto);
  expect(deshabilitado()).toBe(true); // falta valor y método
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe(iso);
});

test('faltaValor: la fecha debe existir en el calendario (ISO válido)', () => {
  const base = { valor: '1,00', metodo: 'MERCADO' as const, fuente: '' };
  expect(faltaValor({ ...base, fecha: '2026-11-06' })).toEqual([]);
  expect(faltaValor({ ...base, fecha: '2026-02-29' })).toEqual(['fecha como dd/mm/aaaa']);
  expect(faltaValor({ ...base, fecha: '06/11/2026' })).toEqual(['fecha como dd/mm/aaaa']);
});
