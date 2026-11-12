// ============================================================
// GAPTO MOBILE 2027
// Fichero: b1_campo_fecha_ux1.test.tsx
// Ruta: mobile/__tests__/b1_campo_fecha_ux1.test.tsx
// Descripción: Revalidación de B1 por UX-1 (T1-F06; TR1-04, AJ-TR1-05): los campos de fecha de B1 (valoración D3,
//   adquisición de A1/editar y «Desde» de la titularidad) con el componente único `CampoFecha`. Sin cambiar ninguna
//   regla de B1: valoración sin mínimo ni máximo (C-PROP-04); adquisición vacía = desconocida (null, nunca 0);
//   DESCONOCIDA sin «Desde» ni partes; «Desde» propuesta con la adquisición. Cambio DECLARADO D-M2-04: la valoración
//   acepta 0050-06-15 (fecha real; C-PROP-04 no fija mínimo), que antes el cliente rechazaba por un defecto. Fechas
//   imposibles (31/02) rechazadas en adquisición y «Desde» (el servidor ya las rechaza: dto_propiedades, dt.date).
//   Los 3 ficheros de Jest de B1 no se editan; estas pruebas son aditivas.
// Versión: 0.1.0 (F06 T1 UX-1 · M-07, revalidación de B1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePropiedades, PayloadAltaPropiedad, PayloadValoracion, ResultadoPropiedad, VistaPropiedad } from '../src/api/propiedades';
import { faltaDatos, faltaTitularidad, FORM_DATOS_VACIO } from '../src/domain/propiedad';
import { PropiedadesScreen } from '../src/screens/PropiedadesScreen';
import { ValoracionFormScreen } from '../src/screens/PropiedadValorScreen';
import { ProveedorTema } from '../src/theme/tema';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));

const VISTA: VistaPropiedad = {
  id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 3, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: null, superficie_m2: null,
  superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
  incluir_en_rentabilidad: true, notas: null, fecha_consulta: '2026-11-06', titularidad: { modo: 'DESCONOCIDA', desde: null, partes: [] },
  cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [],
};

// ------------------------------------------------------------------ D3 valoración
function montarValor() {
  const enviados: PayloadValoracion[] = [];
  const api = {
    altaValoracion: jest.fn(async (_id: string, c: PayloadValoracion) => {
      enviados.push(c);
      return { tipo: 'OK', datos: { propiedad: VISTA, idempotente: false, modificadas: ['p1'], avisos: [] } };
    }),
  } as unknown as ClientePropiedades;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <ValoracionFormScreen propiedades={api} vista={VISTA} nuevoId={() => '00000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 10, 6, 10)} onCerrar={jest.fn()} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { api, enviados };
}
async function completarYGuardar() {
  await escribir('prop-val-valor', '250.000,00');
  await pulsar('prop-val-metodo-MERCADO');
  await pulsar('prop-val-guardar');
}

test('D3 · cambio declarado D-M2-04: «15/06/0050» es una fecha real y se envía 0050-06-15 (C-PROP-04 no fija mínimo)', async () => {
  const { enviados } = montarValor();
  await pulsar('prop-val-otra');
  await escribir('prop-val-fecha', '15/06/0050');
  expect(screen.getByTestId('prop-val-fecha-elegida').props.children).toMatch(/, 15 jun 50$/); // el año 50, no 1950
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('0050-06-15');
});

test('D3 · cifras sin barras: la máscara pone las barras y se envía la misma fecha que escribiéndolas', async () => {
  const { enviados } = montarValor();
  await pulsar('prop-val-otra');
  await escribir('prop-val-fecha', '15032025');
  expect(screen.getByTestId('prop-val-fecha').props.value).toBe('15/03/2025');
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('2025-03-15');
});

test('D3 · calendario: sin máximo (C-PROP-04), un día del mes siguiente se puede elegir y se envía en ISO', async () => {
  const { enviados } = montarValor();
  await pulsar('prop-val-otra');
  await pulsar('prop-val-fecha-calendario');
  expect(screen.getByTestId('prop-val-fecha-cal-mes').props.children).toBe('Noviembre 2026');
  await pulsar('prop-val-fecha-cal-siguiente');
  expect(screen.getByTestId('prop-val-fecha-cal-2026-12-24').props.accessibilityState.disabled).toBe(false);
  await pulsar('prop-val-fecha-cal-2026-12-24');
  expect(screen.getByTestId('prop-val-fecha').props.value).toBe('24/12/2026');
  await completarYGuardar();
  expect(enviados[0].fecha_valoracion).toBe('2026-12-24');
  expect(Object.keys(enviados[0]).sort()).toEqual(['fecha_valoracion', 'fuente', 'intencion_id', 'metodo', 'notas', 'row_version_esperada', 'valor_total']);
});

test('D3 · abrir/cerrar el calendario y cambiar Hoy/Ayer/Otra no borra el valor ni el método', async () => {
  const { enviados } = montarValor();
  await escribir('prop-val-valor', '100.000,00');
  await pulsar('prop-val-metodo-MANUAL');
  await pulsar('prop-val-otra');
  await pulsar('prop-val-fecha-calendario');
  await pulsar('prop-val-fecha-calendario');
  await pulsar('prop-val-ayer');
  await pulsar('prop-val-hoy');
  expect(screen.getByTestId('prop-val-valor').props.value).toBe('100.000,00');
  expect(screen.getByTestId('prop-val-metodo-MANUAL').props.accessibilityState.checked).toBe(true);
  await pulsar('prop-val-guardar');
  expect(enviados[0]).toMatchObject({ fecha_valoracion: '2026-11-06', valor_total: '100000.00', metodo: 'MANUAL' });
});

// ------------------------------------------------------------------ dominio de B1 (reglas sin cambios + 31/02)
test('adquisición: vacía = desconocida; 31/02 no existe (el servidor ya la rechaza); fechas reales sí', () => {
  const base = { ...FORM_DATOS_VACIO, nombre: 'P', tipo: 'VIVIENDA' as const };
  expect(faltaDatos({ ...base, adquisicion: '' })).toEqual([]);
  expect(faltaDatos({ ...base, adquisicion: '31/02/2023' })).toEqual(['fecha de adquisición como dd/mm/aaaa']);
  expect(faltaDatos({ ...base, adquisicion: '29/02/2024' })).toEqual([]);
  expect(faltaDatos({ ...base, adquisicion: '15/06/0050' })).toEqual([]);
});

test('«Desde»: 31/02 no existe; DESCONOCIDA no pide «Desde»; «Desde» ≥ adquisición sigue igual', () => {
  const f = { modo: 'SOLO_MIA' as const, partes: [], desde: '31/02/2024' };
  expect(faltaTitularidad(f, null)).toEqual(['la fecha «Desde» como dd/mm/aaaa']);
  expect(faltaTitularidad({ ...f, desde: '01/02/2024' }, null)).toEqual([]);
  expect(faltaTitularidad({ ...f, desde: '01/02/2024' }, '2024-03-01')).toEqual(['una fecha «Desde» igual o posterior a la adquisición']);
  expect(faltaTitularidad({ modo: 'DESCONOCIDA', partes: [], desde: '' }, null)).toEqual([]);
});

// ------------------------------------------------------------------ A1/A2 alta con el calendario
function servidorAlta() {
  const llamadas: PayloadAltaPropiedad[] = [];
  const api = {
    listarPropiedades: jest.fn(async () => ok({ propiedades: [] })),
    altaPropiedad: jest.fn(async (c: PayloadAltaPropiedad) => {
      llamadas.push(c);
      return ok<ResultadoPropiedad>({ propiedad: { ...VISTA, id: c.intencion_id, nombre: c.nombre }, idempotente: false, modificadas: [c.intencion_id], avisos: [] });
    }),
  } as unknown as ClientePropiedades;
  return { api, llamadas };
}
async function montarAlta(api: ClientePropiedades) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PropiedadesScreen cliente={{ listarTerceros: jest.fn(async () => ok({ terceros: [] })) } as unknown as ClienteApi} propiedades={api}
          nuevoId={() => '00000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 10, 6, 10)} onInmersiva={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await waitFor(() => expect(api.listarPropiedades).toHaveBeenCalled());
}

test('A1/A2: adquisición y «Desde» con el calendario; «Desde» propuesta con la adquisición; la petición lleva ISO', async () => {
  const srv = servidorAlta();
  await montarAlta(srv.api);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Piso Calendario');
  await pulsar('prop-alta-tipo-VIVIENDA');
  await pulsar('prop-alta-adquisicion-calendario');
  expect(screen.getByTestId('prop-alta-adquisicion-cal-mes').props.children).toBe('Noviembre 2026');
  await pulsar('prop-alta-adquisicion-cal-anterior');
  await pulsar('prop-alta-adquisicion-cal-2026-10-15');
  expect(screen.getByTestId('prop-alta-adquisicion').props.value).toBe('15/10/2026');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-SOLO_MIA');
  expect(screen.getByTestId('tit-desde').props.value).toBe('15/10/2026');
  await pulsar('tit-desde-calendario');
  expect(screen.getByTestId('tit-desde-cal-mes').props.children).toBe('Octubre 2026'); // abre en la fecha escrita
  await pulsar('tit-desde-cal-2026-10-20');
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas[0]).toMatchObject({ fecha_adquisicion: '2026-10-15', titularidad: { modo: 'SOLO_MIA', desde: '2026-10-20' } });
});

test('A1: «No la sé» vacía la adquisición y viaja null (nunca 0); DESCONOCIDA sin «Desde» ni partes', async () => {
  const srv = servidorAlta();
  await montarAlta(srv.api);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Trastero');
  await pulsar('prop-alta-tipo-GARAJE');
  await escribir('prop-alta-adquisicion', '01012020');
  expect(screen.getByTestId('prop-alta-adquisicion').props.value).toBe('01/01/2020');
  await pulsar('prop-alta-adquisicion-nolase');
  expect(screen.getByTestId('prop-alta-adquisicion').props.value).toBe('');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-DESCONOCIDA');
  expect(screen.queryByTestId('tit-desde')).toBeNull();
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas[0].fecha_adquisicion).toBeNull();
  expect(srv.llamadas[0].titularidad).toEqual({ modo: 'DESCONOCIDA' });
});

test('A1: adquisición imposible (31/02) bloquea «Continuar» con el texto de siempre', async () => {
  const srv = servidorAlta();
  await montarAlta(srv.api);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Piso');
  await pulsar('prop-alta-tipo-VIVIENDA');
  await escribir('prop-alta-adquisicion', '31/02/2023');
  expect(screen.getByTestId('prop-alta-continuar').props.accessibilityState.disabled).toBe(true);
  expect(srv.api.altaPropiedad).not.toHaveBeenCalled();
});
