// ============================================================
// GAPTO MOBILE 2027
// Fichero: obs_lote30_propiedad.test.tsx
// Ruta: mobile/__tests__/obs_lote30_propiedad.test.tsx
// Descripción: Observaciones de Moisés en ENV-DEV (e1d2386), LOTE30 punto 1, contra dobles en memoria:
//   a) al crear una propiedad, A3 ofrece «Registrar la compra» pulsable y abre la compra de B2; «La compré hace tiempo» sigue no
//      disponible con su explicación; «Continuar» lleva a la ficha con el coste de la propiedad CREADA leído (no el de otra) y
//      «Registrar la compra» visible;
//   b) guardar la compra desde Patrimonio avisa con `onCambios` (la raíz sube `refresco` y Día a día vuelve a leer); cancelar no avisa.
// Versión: 0.1.0 (F06 LOTE30 punto 1, N3 de cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonio, Coste, CosteAmbito } from '../src/api/patrimonio';
import type { ClientePropiedades, FilaPropiedad, PayloadAltaPropiedad, VistaPropiedad } from '../src/api/propiedades';
import { PropiedadesScreen } from '../src/screens/PropiedadesScreen';
import { TEXTO_HISTORICA_NO_DISPONIBLE } from '../src/screens/PropiedadAltaScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const C1 = 'c0000000-0000-4000-8000-0000000000c1';
const AHORA = () => new Date(2026, 9, 10, 10);
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;

function vista(p: Partial<VistaPropiedad> & { id: string; nombre: string }): VistaPropiedad {
  return {
    enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: null, superficie_m2: null, superficie_construida_m2: null,
    habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null, incluir_en_rentabilidad: true, notas: null,
    fecha_consulta: '2026-10-10', titularidad: { modo: 'SOLO_MIA', desde: '2026-03-20', partes: [{ actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '100.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  };
}
const ambito = (p: Partial<CosteAmbito>): CosteAmbito => ({ total: '0.00', estado: 'NO_DISPONIBLE', motivo_estado: 'SIN_COMPONENTES', fecha_corte: null,
  huella_conjunto: null, componentes: 0, tu_parte: { importe: null, estado: 'NO_DISPONIBLE' }, ...p });
const coste = (adq: Partial<CosteAmbito>): Coste => ({ a_fecha: '2026-10-10', declaracion_habilitada: false,
  ADQUISICION: ambito(adq), MEJORAS: ambito({}), PERMANECE: { total: '0.00', estado: 'NO_DISPONIBLE', bajas: 'NO_REPRESENTADAS' } });

/** «Antigua» ya tiene compra; cualquier otra propiedad, no. */
function dobles(inicial: VistaPropiedad[]) {
  const st = new Map(inicial.map((v) => [v.id, v]));
  const fila = (v: VistaPropiedad): FilaPropiedad => ({ id: v.id, nombre: v.nombre, enabled: true, row_version: v.row_version, tipo_propiedad: v.tipo_propiedad, modo_titularidad: v.titularidad.modo, valor_estimado: null });
  const propiedades = {
    listarPropiedades: jest.fn(async () => ok({ propiedades: [...st.values()].map(fila) })),
    leerPropiedad: jest.fn(async (id: string) => ok({ propiedad: st.get(id)! })),
    altaPropiedad: jest.fn(async (c: PayloadAltaPropiedad) => {
      const v = vista({ id: c.intencion_id, nombre: c.nombre, fecha_adquisicion: c.fecha_adquisicion ?? null });
      st.set(v.id, v);
      return ok({ propiedad: v, idempotente: false, modificadas: [v.id], avisos: [] });
    }),
  } as unknown as ClientePropiedades;
  const patrimonio = {
    leerCoste: jest.fn(async (id: string) => ok({ coste: id === 'antigua' ? coste({ total: '1000.00', estado: 'PARCIAL', motivo_estado: 'SIN_DECLARACION', componentes: 1 }) : coste({}) })),
    titularidadEnFecha: jest.fn(async (_id: string, fecha: string) => ok({ fecha, partes: [] })),
    registrarCompra: jest.fn(async (id: string) => ok({ propiedad: { ...st.get(id)!, row_version: 2 }, idempotente: false,
      compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1000.00', liquidez_atribuible: '-1000.00', gasto_del_mes: '0.00', atribucion: null } })),
    gastoCompraPosterior: jest.fn(),
  } as unknown as ClientePatrimonio;
  return { propiedades, patrimonio };
}

const cliente = () => ({
  listarTerceros: jest.fn(async () => ok({ terceros: [] })),
  cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [{ cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' }] })),
}) as unknown as ClienteApi;

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));

async function montar(d: ReturnType<typeof dobles>, onCambios = jest.fn()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PropiedadesScreen cliente={cliente()} propiedades={d.propiedades} patrimonio={d.patrimonio} nuevoId={nuevoId} ahora={AHORA} onInmersiva={jest.fn()} onCambios={onCambios} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await waitFor(() => expect(d.propiedades.listarPropiedades).toHaveBeenCalled());
  return onCambios;
}

async function altaSoloMia(nombre: string) {
  await pulsar('prop-nueva');
  await escribir('prop-alta-nombre', nombre);
  await pulsar('prop-alta-tipo-VIVIENDA');
  await escribir('prop-alta-adquisicion', '20/03/2026');
  await pulsar('prop-alta-continuar');
  await pulsar('tit-modo-SOLO_MIA');
  await pulsar('prop-alta-guardar');
  await waitFor(() => screen.getByTestId('prop-alta-guardada'));
}

test('a) A3: «Registrar la compra» es pulsable y abre la compra de B2; «La compré hace tiempo» sigue no disponible con su explicación', async () => {
  const d = dobles([]);
  await montar(d);
  await altaSoloMia('Piso Nuevo');
  expect(screen.getByTestId('prop-alta-camino-compra').props.accessibilityState?.disabled).not.toBe(true);
  expect(screen.getByTestId('prop-alta-camino-historica').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('prop-alta-historica-nota').props.children).toBe(TEXTO_HISTORICA_NO_DISPONIBLE);
  expect(screen.queryByText('Llega con la compra')).toBeNull();
  await pulsar('prop-alta-camino-compra');
  expect(screen.getByTestId('compra-paso-precio')).toBeTruthy();
  // al cancelar vuelve a la ficha de la propiedad creada, con su coste leído
  await pulsar('compra-cancelar');
  await waitFor(() => screen.getByTestId('prop-accion-compra'));
  expect(d.patrimonio.leerCoste).toHaveBeenLastCalledWith('00000000-0000-4000-8000-000000000001');
});

test('a) «Continuar» tras el alta: la ficha lee el coste de la propiedad CREADA y ofrece «Registrar la compra» (no el coste de la abierta antes)', async () => {
  const d = dobles([vista({ id: 'antigua', nombre: 'Antigua' })]);
  await montar(d);
  // se abre antes una propiedad CON compra: su coste no debe arrastrarse a la nueva
  await waitFor(() => screen.getByTestId('prop-fila-antigua'));
  await pulsar('prop-fila-antigua');
  await waitFor(() => screen.getByTestId('prop-accion-gasto-compra'));
  await pulsar('prop-ficha-atras');
  await altaSoloMia('Piso Nuevo');
  await pulsar('prop-alta-continuar-final');
  await waitFor(() => screen.getByTestId('prop-accion-compra'));
  expect(screen.queryByTestId('prop-accion-gasto-compra')).toBeNull();
  expect(d.patrimonio.leerCoste).toHaveBeenLastCalledWith('00000000-0000-4000-8000-000000000001');
});

test('b) guardar la compra desde Patrimonio avisa con onCambios (Día a día vuelve a leer); cancelar no avisa', async () => {
  const d = dobles([]);
  const onCambios = await montar(d);
  await altaSoloMia('Piso Nuevo');
  await pulsar('prop-alta-camino-compra');
  await pulsar('compra-cancelar');
  expect(onCambios).not.toHaveBeenCalled();
  await waitFor(() => screen.getByTestId('prop-accion-compra'));
  await pulsar('prop-accion-compra');
  await escribir('compra-precio', '1000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${C1}`));
  await pulsar(`compra-pago-0-cuenta-${C1}`);
  await escribir('compra-pago-0-importe', '1000');
  await pulsar('compra-continuar');
  await pulsar('compra-continuar'); // sin gastos de la compra
  await waitFor(() => screen.getByTestId('compra-atr-no-lo-se'));
  await pulsar('compra-atr-no-lo-se');
  await pulsar('compra-continuar');
  await pulsar('compra-guardar');
  await waitFor(() => screen.getByTestId('compra-listo'));
  expect(onCambios).not.toHaveBeenCalled();
  await pulsar('compra-listo');
  expect(onCambios).toHaveBeenCalledTimes(1);
});
