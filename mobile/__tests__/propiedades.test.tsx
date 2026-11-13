// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedades.test.tsx
// Ruta: mobile/__tests__/propiedades.test.tsx
// Descripción: Pantallas de B1 · Propiedad (F06-01; láminas F06-01 v0.9 A1–A3, D1–D3 y v0.1 B2–B3, C1–C2, D3–D4; contrato HTTP de B1 v1.0) contra un servidor simulado en memoria con las reglas que el cliente necesita ver: alta con los cuatro modos y la petición exacta (porcentajes como texto de 4 decimales, DESCONOCIDA sin `desde` ni partes), suma exacta y bloqueo del envío, cotitulares solo PERSONA/EMPRESA, A3 con la compra no disponible, misma `intencion_id` al reintentar tras un indeterminado, textos de los códigos ★, ficha con valor estimado, referencia fiscal aparte y cuota etiquetada como vista estructural, valoración nueva sin «Compra», histórico y corrección con motivo (solo campos cambiados), nuevo reparto con fecha ≥ hoy y `titularidad_vista` completa, conflicto de versión con «Recargar», edición que envía solo lo cambiado, y la pestaña Patrimonio en la raíz con la barra oculta durante una tarea.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// Versión: 0.1.1 (F06 LOTE30 punto 1 a, N3 de cliente): A3 ofrece «Registrar la compra» pulsable (abre B2); la que sigue no disponible es «La compré hace tiempo».
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, Respuesta, Tercero } from '../src/api/cliente';
import type {
  ClientePropiedades,
  FilaPropiedad,
  PayloadAltaPropiedad,
  ResultadoPropiedad,
  TitularidadVista,
  Valoracion,
  VistaPropiedad,
} from '../src/api/propiedades';
import { TEXTOS_ERROR_B1 } from '../src/domain/propiedad';
import { PropiedadesScreen } from '../src/screens/PropiedadesScreen';
import { ordenHistorico } from '../src/screens/PropiedadValorScreen';
import { ProveedorTema } from '../src/theme/tema';

const HOY = '2026-11-06';
const AHORA = () => new Date(2026, 10, 6, 10);
const LAURA = 'a0000000-0000-4000-8000-0000000000a1';
const BANCO = 'a0000000-0000-4000-8000-0000000000b2';
const ACME = 'a0000000-0000-4000-8000-0000000000c3';
const YO = 'f0000000-0000-4000-8000-0000000000ff';

const ter = (p: Partial<Tercero> & { id: string; nombre: string }): Tercero => ({ naturaleza: 'PERSONA', enabled: true, row_version: 1, ...p });
const TERCEROS = [ter({ id: LAURA, nombre: 'Laura Pérez' }), ter({ id: BANCO, nombre: 'Banco Ejemplo', naturaleza: 'ORGANISMO' }), ter({ id: ACME, nombre: 'Acme SL', naturaleza: 'EMPRESA' })];
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;

function vistaBase(p: Partial<VistaPropiedad> & { id: string; nombre: string }): VistaPropiedad {
  return {
    enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: null, superficie_m2: null, superficie_construida_m2: null,
    habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null, incluir_en_rentabilidad: true, notas: null,
    fecha_consulta: HOY, titularidad: { modo: 'DESCONOCIDA', desde: null, partes: [] }, cambio_programado: null, valor_estimado: null,
    referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  };
}

/** Servidor simulado: guarda las vistas y registra cada petición; `siguiente` fuerza la próxima respuesta de escritura. */
function servidor(inicial: VistaPropiedad[] = []) {
  const st = new Map(inicial.map((v) => [v.id, v]));
  const llamadas: { ruta: string; cuerpo: any }[] = [];
  let siguiente: Respuesta<ResultadoPropiedad> | null = null;
  const fila = (v: VistaPropiedad): FilaPropiedad => ({ id: v.id, nombre: v.nombre, enabled: v.enabled, row_version: v.row_version, tipo_propiedad: v.tipo_propiedad, modo_titularidad: v.titularidad.modo, valor_estimado: v.valor_estimado });
  const escribir = (ruta: string, cuerpo: any, aplicar: () => VistaPropiedad): Respuesta<ResultadoPropiedad> => {
    llamadas.push({ ruta, cuerpo });
    if (siguiente) {
      const r = siguiente;
      siguiente = null;
      return r;
    }
    const v = aplicar();
    st.set(v.id, v);
    return ok({ propiedad: v, idempotente: false, modificadas: [v.id], avisos: [] });
  };
  const titDe = (modo: string, desde: string | null, partes: any[] | null | undefined): TitularidadVista => {
    if (modo === 'DESCONOCIDA') return { modo: 'DESCONOCIDA', desde: null, partes: [] };
    if (modo === 'SOLO_MIA') return { modo: 'SOLO_MIA', desde, partes: [{ actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '100.0000' }] };
    return {
      modo: modo as TitularidadVista['modo'], desde,
      partes: (partes ?? []).map((x) => (x.yo ? { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: x.porcentaje } : { actor_id: `act-${x.tercero_id}`, yo: false, tercero_id: x.tercero_id, nombre: TERCEROS.find((t) => t.id === x.tercero_id)?.nombre ?? null, porcentaje: x.porcentaje })),
    };
  };
  const api: ClientePropiedades = {
    listarPropiedades: jest.fn(async () => ok({ propiedades: [...st.values()].sort((a, b) => a.nombre.localeCompare(b.nombre)).map(fila) })),
    leerPropiedad: jest.fn(async (id: string) => (st.has(id) ? ok({ propiedad: st.get(id)! }) : ({ tipo: 'RECHAZADO', codigo: 'AGREGADO_NO_ENCONTRADO', mensaje: '' } as Respuesta<{ propiedad: VistaPropiedad }>))),
    altaPropiedad: jest.fn(async (c: PayloadAltaPropiedad) =>
      escribir('alta', c, () => {
        const { intencion_id, titularidad, ...datos } = c;
        return vistaBase({ id: intencion_id, ...datos, titularidad: titDe(titularidad.modo, titularidad.desde ?? null, titularidad.partes) });
      })),
    editarPropiedad: jest.fn(async (id: string, c: any) =>
      escribir('editar', c, () => {
        const { intencion_id, row_version_esperada, motivo, ...cambios } = c;
        const v = st.get(id)!;
        return { ...v, ...cambios, row_version: v.row_version + 1 };
      })),
    cambiarTitularidad: jest.fn(async (id: string, c: any) =>
      escribir('titularidad', c, () => {
        const v = st.get(id)!;
        return { ...v, row_version: v.row_version + 1, cambio_programado: titDe(c.modo, c.desde, c.partes) };
      })),
    altaValoracion: jest.fn(async (id: string, c: any) =>
      escribir('valoracion', c, () => {
        const v = st.get(id)!;
        const nueva: Valoracion = { id: c.intencion_id, valor_total: c.valor_total, fecha_valoracion: c.fecha_valoracion, metodo: c.metodo, fuente: c.fuente, notas: null, sin_fecha: false };
        return { ...v, row_version: v.row_version + 1, valoraciones: [...v.valoraciones, nueva], valor_estimado: c.metodo === 'FISCAL_REFERENCIA' ? v.valor_estimado : nueva };
      })),
  };
  return { api, st, llamadas, forzar: (r: Respuesta<ResultadoPropiedad>) => (siguiente = r) };
}

const clienteTerceros = () => ({ listarTerceros: jest.fn(async () => ok({ terceros: TERCEROS })) }) as unknown as ClienteApi;

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };

async function montar(srv: ReturnType<typeof servidor>, esquema: 'light' | 'dark' = 'light') {
  const inmersiva = jest.fn();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar={esquema}>
        <PropiedadesScreen cliente={clienteTerceros()} propiedades={srv.api} nuevoId={nuevoId} ahora={AHORA} onInmersiva={inmersiva} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await waitFor(() => expect(srv.api.listarPropiedades).toHaveBeenCalled());
  return inmersiva;
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));

const CON_VALOR = vistaBase({
  id: 'p1', nombre: 'Piso Ejemplo', fecha_adquisicion: '2023-10-15', row_version: 3,
  titularidad: { modo: 'COMPARTIDA', desde: '2023-10-15', partes: [
    { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '50.0000' },
    { actor_id: 'act-laura', yo: false, tercero_id: LAURA, nombre: 'Laura Pérez', porcentaje: '50.0000' },
  ] },
  valor_estimado: { id: 'v2', valor_total: '245000.00', fecha_valoracion: '2028-01-10', metodo: 'MERCADO', fuente: null, notas: null, sin_fecha: false },
  referencia_fiscal: { id: 'v1', valor_total: '210000.00', fecha_valoracion: '2027-03-20', metodo: 'FISCAL_REFERENCIA', fuente: 'Catastro', notas: null, sin_fecha: false },
  cuota_segun_titularidad: { importe: '122500.00', porcentaje: '50.0000', etiqueta: 'VISTA_ESTRUCTURAL' },
  valoraciones: [
    { id: 'v0', valor_total: '96400.00', fecha_valoracion: null, metodo: 'FISCAL_REFERENCIA', fuente: 'origen V3', notas: null, sin_fecha: true },
    { id: 'v1', valor_total: '210000.00', fecha_valoracion: '2027-03-20', metodo: 'FISCAL_REFERENCIA', fuente: 'Catastro', notas: null, sin_fecha: false },
    { id: 'v2', valor_total: '245000.00', fecha_valoracion: '2028-01-10', metodo: 'MERCADO', fuente: null, notas: null, sin_fecha: false },
  ],
});

// ------------------------------------------------------------------ alta (C-PROP-01, A1–A3)

test('alta compartida: A1 → A2 con suma exacta y cotitular PERSONA → petición exacta → A3 → ficha', async () => {
  const srv = servidor();
  const inmersiva = await montar(srv);
  expect(screen.getByTestId('prop-lista-vacia')).toBeTruthy();
  await pulsar('prop-nueva');
  expect(inmersiva).toHaveBeenLastCalledWith(true);
  // A1: solo nombre y tipo obligatorios; el tipo no viene marcado
  expect(screen.getByTestId('prop-alta-continuar').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('prop-alta-tipo-VIVIENDA').props.accessibilityState.checked).toBe(false);
  await escribir('prop-alta-nombre', 'Piso Calle Mayor');
  await pulsar('prop-alta-tipo-VIVIENDA');
  await escribir('prop-alta-adquisicion', '15/10/2023');
  await pulsar('prop-alta-continuar');
  // A2: ningún modo marcado; «Desde» propuesta con la adquisición
  expect(screen.getByTestId('prop-alta-paso').props.children).toBe('Paso 2 de 2 · ¿De quién es?');
  expect(screen.getByTestId('tit-modo-COMPARTIDA').props.accessibilityState.checked).toBe(false);
  await pulsar('tit-modo-COMPARTIDA');
  expect(screen.getByTestId('tit-desde').props.value).toBe('15/10/2023');
  await pulsar('tit-anadir');
  await waitFor(() => expect(screen.getByTestId(`cotitular-${LAURA}`)).toBeTruthy());
  // Q-10: un ORGANISMO no se puede elegir
  expect(screen.getByTestId(`cotitular-${BANCO}`).props.accessibilityState.disabled).toBe(true);
  await pulsar(`cotitular-${LAURA}`);
  await escribir('tit-pct-yo', '50');
  await escribir(`tit-pct-${LAURA}`, '40');
  expect(screen.getByTestId('tit-total').props.children).toBe('Total 90 % · falta un 10 %');
  expect(screen.getByTestId('prop-alta-guardar').props.accessibilityState.disabled).toBe(true);
  await escribir(`tit-pct-${LAURA}`, '50');
  expect(screen.getByTestId('tit-total').props.children).toBe('Total 100 % ✓');
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas).toHaveLength(1);
  expect(srv.llamadas[0].cuerpo).toEqual({
    intencion_id: '00000000-0000-4000-8000-000000000001',
    nombre: 'Piso Calle Mayor', tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2023-10-15', superficie_m2: null, superficie_construida_m2: null,
    habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null, notas: null,
    titularidad: { modo: 'COMPARTIDA', desde: '2023-10-15', partes: [{ yo: true, porcentaje: '50.0000' }, { tercero_id: LAURA, porcentaje: '50.0000' }] },
  });
  // A3: guardada; «Registrar la compra» abre la compra de B2 (LOTE30 1a); la compra histórica sigue no disponible; «Más tarde»
  expect(screen.getByTestId('prop-alta-guardada-texto').props.children).toBe('«Piso Calle Mayor» ya está guardada.');
  expect(screen.getByTestId('prop-alta-camino-compra').props.accessibilityRole).toBe('button');
  expect(within(screen.getByTestId('prop-alta-camino-historica')).getByText('No disponible')).toBeTruthy();
  await pulsar('prop-alta-continuar-final');
  expect(inmersiva).toHaveBeenLastCalledWith(false);
  expect(screen.getByTestId('prop-ficha')).toBeTruthy();
  expect(screen.getByTestId('prop-tu-titularidad-valor').props.children).toBe('50 %');
  expect(screen.getByTestId('prop-valor-estimado-nd')).toBeTruthy();
  expect(screen.getByTestId('prop-coste-nd')).toBeTruthy();
});

test('alta «Aún no lo sé»: sin Desde ni partes; la ficha dice «Sin indicar», nunca 0 ni 100 %', async () => {
  const srv = servidor();
  await montar(srv);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Garaje Plaza Sol');
  await pulsar('prop-alta-tipo-GARAJE');
  await pulsar('prop-alta-mas-datos');
  await pulsar('prop-alta-garaje-nolose');
  await pulsar('prop-alta-trastero-no');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-DESCONOCIDA');
  expect(screen.queryByTestId('tit-desde')).toBeNull();
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas[0].cuerpo.titularidad).toEqual({ modo: 'DESCONOCIDA' });
  expect(srv.llamadas[0].cuerpo).toMatchObject({ tiene_garaje: null, tiene_trastero: false, fecha_adquisicion: null });
  await pulsar('prop-alta-continuar-final');
  expect(screen.getByTestId('prop-tu-titularidad-valor').props.children).toBe('Sin indicar');
});

test('alta «Solo mía» y «Es de otra persona» (sin ti; suma 100 % entre los demás)', async () => {
  const srv = servidor();
  await montar(srv);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Local');
  await pulsar('prop-alta-tipo-LOCAL');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-SOLO_MIA');
  expect(screen.getByTestId('prop-alta-guardar').props.accessibilityState.disabled).toBe(true); // falta Desde (sin adquisición)
  await pulsar('tit-modo-DE_OTROS');
  expect(screen.queryByTestId('tit-parte-yo')).toBeNull();
  await pulsar('tit-anadir');
  await waitFor(() => expect(screen.getByTestId(`cotitular-${ACME}`)).toBeTruthy());
  await pulsar(`cotitular-${ACME}`);
  await escribir(`tit-pct-${ACME}`, '100');
  await escribir('tit-desde', '01/01/2020');
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas[0].cuerpo.titularidad).toEqual({ modo: 'DE_OTROS', desde: '2020-01-01', partes: [{ tercero_id: ACME, porcentaje: '100.0000' }] });
});

test('indeterminado: el reintento reutiliza la MISMA intencion_id; un ★ muestra su texto', async () => {
  const srv = servidor();
  await montar(srv);
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', 'Piso');
  await pulsar('prop-alta-tipo-VIVIENDA');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-COMPARTIDA');
  await pulsar('tit-anadir');
  await waitFor(() => expect(screen.getByTestId(`cotitular-${LAURA}`)).toBeTruthy());
  await pulsar(`cotitular-${LAURA}`);
  await escribir('tit-pct-yo', '33,3333');
  await escribir(`tit-pct-${LAURA}`, '66,6667');
  await escribir('tit-desde', '01/02/2024');
  srv.forzar({ tipo: 'INDETERMINADO', mensaje: '' });
  await pulsar('prop-alta-guardar');
  expect(screen.getByTestId('prop-alta-aviso')).toBeTruthy();
  srv.forzar({ tipo: 'RECHAZADO', codigo: 'NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD', mensaje: '' });
  await pulsar('prop-alta-guardar');
  expect(within(screen.getByTestId('prop-alta-aviso')).getByText(TEXTOS_ERROR_B1.NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD)).toBeTruthy();
  await pulsar('prop-alta-guardar');
  expect(srv.llamadas.map((l) => l.cuerpo.intencion_id)).toEqual(Array(3).fill('00000000-0000-4000-8000-000000000001'));
  expect(srv.llamadas[2].cuerpo.titularidad.partes).toEqual([{ yo: true, porcentaje: '33.3333' }, { tercero_id: LAURA, porcentaje: '66.6667' }]);
  expect(screen.getByTestId('prop-alta-guardada')).toBeTruthy();
});

// ------------------------------------------------------------------ ficha (L-PROP, D1)

test('ficha D1: valor estimado con procedencia, referencia fiscal aparte y cuota etiquetada como vista estructural', async () => {
  const srv = servidor([CON_VALOR]);
  await montar(srv);
  await waitFor(() => expect(screen.getByTestId('prop-fila-p1-detalle').props.children).toBe('Vivienda · Compartida · 245.000,00 €'));
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  expect(screen.getByTestId('prop-valor-estimado-importe').props.children).toBe('245.000,00 €');
  expect(screen.getByTestId('prop-valor-estimado-detalle').props.children).toBe('Mercado · ene 2028');
  expect(screen.getByTestId('prop-referencia-fiscal-importe').props.children).toBe('210.000,00 €');
  expect(screen.getByTestId('prop-cuota-importe').props.children).toBe('122.500,00 €');
  expect(screen.getByTestId('prop-cuota-detalle').props.children).toBe('Vista estructural · 50 %');
  expect(screen.getByTestId('prop-coste-nd')).toBeTruthy();
});

// ------------------------------------------------------------------ valoraciones (C-PROP-04, D3, B2, B3)

test('nueva valoración: sin «Compra»; petición exacta con la versión vista; la ficha muestra la vista devuelta', async () => {
  const srv = servidor([CON_VALOR]);
  await montar(srv);
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  await pulsar('prop-accion-valor');
  expect(screen.queryByTestId('prop-val-metodo-COMPRA')).toBeNull();
  await escribir('prop-val-valor', '250.000,00');
  await pulsar('prop-val-hoy');
  await pulsar('prop-val-metodo-TASACION');
  await escribir('prop-val-fuente', 'Tasadora');
  await pulsar('prop-val-guardar');
  expect(srv.llamadas[0]).toEqual({ ruta: 'valoracion', cuerpo: {
    intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 3, valor_total: '250000.00', fecha_valoracion: HOY, metodo: 'TASACION', fuente: 'Tasadora', notas: null,
  } });
  expect(screen.getByTestId('prop-valor-estimado-importe').props.children).toBe('250.000,00 €');
});

test('histórico B2 (reciente primero, sin fecha al final), solo lectura: «Añadir valoración» abre D3', async () => {
  expect(ordenHistorico(CON_VALOR.valoraciones).map((v) => v.id)).toEqual(['v2', 'v1', 'v0']);
  const srv = servidor([CON_VALOR]);
  await montar(srv);
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  await pulsar('prop-accion-historico');
  expect(screen.getByTestId('prop-val-sin-fecha')).toBeTruthy();
  expect(screen.getByTestId('prop-val-fila-v2').props.accessibilityRole).toBeUndefined(); // la fila no es un botón
  expect(screen.queryByTestId('prop-val-que-paso')).toBeNull();
  await pulsar('prop-val-historico-nueva');
  expect(screen.getByTestId('prop-val-nueva')).toBeTruthy();
  expect(srv.llamadas).toEqual([]);
});

// ------------------------------------------------------------------ titularidad (C-PROP-03, C1–C2)

test('nuevo reparto: fecha ≥ hoy, titularidad_vista completa; VERSION_DESFASADA → «No se ha guardado» → Recargar relee', async () => {
  const srv = servidor([CON_VALOR]);
  await montar(srv);
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  await pulsar('prop-accion-titularidad');
  expect(screen.getByTestId(`prop-tit-parte-${LAURA}`)).toBeTruthy();
  await pulsar('prop-tit-cambiar');
  expect(screen.queryByTestId('tit-modo-DESCONOCIDA')).toBeNull(); // no se vuelve a «Aún no lo sé»
  await pulsar('tit-modo-SOLO_MIA');
  await escribir('tit-desde', '01/11/2026');
  expect(screen.getByTestId('prop-tit-falta').props.children).toMatch(/igual o posterior a hoy/);
  await escribir('tit-desde', '01/01/2027');
  expect(within(screen.getByTestId('prop-tit-resumen')).getByText('Reparto actual termina el 31 dic 2026')).toBeTruthy();
  srv.forzar({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: '', detalle: { motivo: 'TITULARIDAD_CAMBIADA' } });
  await pulsar('prop-tit-guardar');
  expect(srv.llamadas[0].cuerpo).toEqual({
    intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 3, modo: 'SOLO_MIA', desde: '2027-01-01', partes: null,
    titularidad_vista: [{ actor_id: YO, porcentaje: '50.0000' }, { actor_id: 'act-laura', porcentaje: '50.0000' }],
  });
  expect(screen.getByTestId('prop-conflicto')).toBeTruthy();
  const lecturas = (srv.api.leerPropiedad as jest.Mock).mock.calls.length;
  await pulsar('prop-conflicto-recargar');
  expect((srv.api.leerPropiedad as jest.Mock).mock.calls.length).toBe(lecturas + 1);
});

test('nuevo reparto aceptado: el cambio programado aparece en la titularidad y en la ficha', async () => {
  const srv = servidor([CON_VALOR]);
  await montar(srv);
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  await pulsar('prop-accion-titularidad');
  await pulsar('prop-tit-cambiar');
  await pulsar(`tit-quitar-${LAURA}`);
  await escribir('tit-pct-yo', '100');
  await escribir('tit-desde', '01/01/2027');
  // COMPARTIDA exige otra persona: añadir Acme al 40 % y dejar «Tú» al 60 %
  await pulsar('tit-anadir');
  await waitFor(() => expect(screen.getByTestId(`cotitular-${ACME}`)).toBeTruthy());
  await pulsar(`cotitular-${ACME}`);
  await escribir('tit-pct-yo', '60');
  await escribir(`tit-pct-${ACME}`, '40');
  await pulsar('prop-tit-guardar');
  expect(srv.llamadas[0].cuerpo.partes).toEqual([{ yo: true, porcentaje: '60.0000' }, { tercero_id: ACME, porcentaje: '40.0000' }]);
  expect(screen.getByTestId('prop-titularidad')).toBeTruthy();
  expect(screen.getByTestId('prop-tit-programado').props.children).toBe('Desde el 1 ene 2027: Tú 60 % · Acme SL 40 %');
});

// ------------------------------------------------------------------ edición (C-PROP-02, D3–D4)

test('editar datos: solo se envía lo cambiado; vaciar un dato lo borra (null); sin cambios no se guarda', async () => {
  const srv = servidor([vistaBase({ id: 'p1', nombre: 'Piso', superficie_m2: '72.40', habitaciones: 3, row_version: 2 })]);
  await montar(srv);
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  await pulsar('prop-accion-editar');
  expect(screen.getByTestId('prop-editar-superficie').props.value).toBe('72,40');
  expect(screen.getByTestId('prop-editar-guardar').props.accessibilityState.disabled).toBe(true);
  await escribir('prop-editar-nombre', 'Piso Calle Mayor');
  await escribir('prop-editar-habitaciones', '');
  await pulsar('prop-editar-guardar');
  expect(srv.llamadas[0].cuerpo).toEqual({ intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 2, nombre: 'Piso Calle Mayor', habitaciones: null });
  expect(screen.getByTestId('prop-ficha')).toBeTruthy();
});

test('modo oscuro: la ficha se pinta con los tokens del tema oscuro', async () => {
  const srv = servidor([CON_VALOR]);
  await montar(srv, 'dark');
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-ficha')).toBeTruthy());
  expect(screen.getByTestId('prop-ficha').props.style.backgroundColor).toBe(require('../src/theme/tokens').colores.dark.background);
});

// ------------------------------------------------------------------ raíz: pestaña Patrimonio

test('raíz: «Patrimonio» monta Propiedades y la barra inferior se oculta durante el alta', async () => {
  const srv = servidor();
  const generico = new Proxy({}, { get: (_o, k) => (k === 'then' ? undefined : k === 'listarTerceros' ? async () => ok({ terceros: TERCEROS }) : async () => ({ tipo: 'INDETERMINADO', mensaje: '' })) });
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <Raiz cliente={generico as ClienteApi} nuevoId={nuevoId} ahora={AHORA} propiedades={srv.api} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  expect(srv.api.listarPropiedades).not.toHaveBeenCalled(); // se monta en la primera visita
  await pulsar('tab-PATRIMONIO');
  await waitFor(() => expect(screen.getByTestId('pantalla-propiedades')).toBeTruthy());
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy();
  await pulsar('prop-nueva');
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
  await pulsar('prop-alta-cancelar');
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy();
});
