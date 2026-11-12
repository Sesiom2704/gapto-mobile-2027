// ============================================================
// GAPTO MOBILE 2027
// Fichero: compra.test.tsx
// Ruta: mobile/__tests__/compra.test.tsx
// Descripción: B2 · Compra en el cliente (F06-01 B2; R1 v0.9.5 Parte II; lámina F06-01 v0.9 B1–B4, B6 y D1) contra dobles en memoria:
//   - dominio: resumen de O2′ (coste, lo que sale de tus cuentas, gasto del mes 0), payload exacto de C-COMPRA-01 con UNA propuesta en la fecha
//     de escritura (AJ-TR1-10, O6.22 parte cliente) y de C-COMPRA-03 en la fecha de su efecto (O6.24), aviso de los gastos anteriores, y la
//     derivación de Día a día por el tipo del HECHO (HF-14, O10.19 parte cliente; discriminante de M-AC-02);
//   - O10.29 parte cliente: la constante de habilitación de 0352 es false y ninguna pantalla ofrece declarar el coste completo;
//   - pantallas: flujo B1 → B2 (sin hipoteca) → B3 → B3b (ninguna opción marcada; «Según la titularidad de <propiedad> en la escritura
//     (<fecha>)») → B4 → B6; ATRIBUCION_PROPUESTA_DESFASADA vuelve a B3b sin selección; D1 con adquisición, mejoras y estado, y las entradas
//     «Registrar la compra» y «Añadir un gasto de la compra»; sin «Desglose» (D4) ni «Repetir hoy».
// Versión: 0.1.0 (F06 T1-F06 B2 N1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonio, Coste, CosteAmbito, ParteEnFecha, ResultadoCompra } from '../src/api/patrimonio';
import type { VistaPropiedad } from '../src/api/propiedades';
import {
  avisoGastosAnteriores, BorradorCompra, CONSUMIDORES_0352_HABILITADOS, esPatrimonial, etiquetaNoGastoMes, filasDiaADia, payloadCompra,
  payloadGastoCompra, resumen, TEXTO_DESFASADA, TEXTO_NO_GASTO_MES, textoPropuestaEscritura,
} from '../src/domain/compra';
import { CompraScreen, GastoCompraScreen } from '../src/screens/CompraScreen';
import { PropiedadFichaScreen } from '../src/screens/PropiedadFichaScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const ANA = 'a0000000-0000-4000-8000-0000000000a1';
const C1 = 'c0000000-0000-4000-8000-0000000000c1';
const C2 = 'c0000000-0000-4000-8000-0000000000c2';
const AHORA = () => new Date(2026, 9, 10, 10);
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const PARTES: ParteEnFecha[] = [
  { actor_id: ANA, porcentaje: '40.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana' },
  { actor_id: YO, porcentaje: '60.0000', yo: true, tercero_id: null, nombre: null },
];

function vista(p: Partial<VistaPropiedad> = {}): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: '2026-10-10',
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
      { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '60.0000' },
      { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '40.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  };
}

const ambito = (p: Partial<CosteAmbito>): CosteAmbito => ({ total: '0.00', estado: 'NO_DISPONIBLE', motivo_estado: 'SIN_COMPONENTES', fecha_corte: null,
  huella_conjunto: null, componentes: 0, tu_parte: { importe: null, estado: 'NO_DISPONIBLE' }, ...p });
const coste = (adq: Partial<CosteAmbito>, mej: Partial<CosteAmbito> = {}): Coste => ({ a_fecha: '2026-10-10', declaracion_habilitada: false,
  ADQUISICION: ambito(adq), MEJORAS: ambito(mej), PERMANECE: { total: '216830.00', estado: adq.componentes ? 'PARCIAL' : 'NO_DISPONIBLE', bajas: 'NO_REPRESENTADAS' } });

function borradorO2(): BorradorCompra {
  return {
    precio: '200000,00', fechaEscritura: '2026-03-20', valorReferencia: '', completo: false, atribucion: { modo: 'TITULARIDAD' },
    pagos: [{ id: 'l-arras', rol: 'ARRAS', cuentaId: C1, fecha: '2026-02-15', importe: '20000' }, { id: 'l-firma', rol: 'FIRMA', cuentaId: C1, fecha: '2026-03-20', importe: '180000' }],
    gastos: [
      { id: 'l-itp', concepto: 'ITP', cuentaId: C1, fechaEconomica: '2026-03-20', fechaPago: '2026-03-25', importe: '12000', nota: '' },
      { id: 'l-not', concepto: 'NOTARIA_REGISTRO_GESTORIA', cuentaId: C1, fechaEconomica: '2026-03-20', fechaPago: '2026-03-30', importe: '1200', nota: '' },
      { id: 'l-age', concepto: 'AGENCIA', cuentaId: C2, fechaEconomica: '2026-02-28', fechaPago: '2026-02-28', importe: '3630', nota: '' },
    ],
  };
}

// ------------------------------------------------------------------ dominio
test('O2′: resumen B4 separa coste, salida de las cuentas y gasto del mes', () => {
  expect(resumen(borradorO2())).toEqual({ coste: '216830.00', sale: '-216830.00', gastoMes: '0.00', registros: 4, pagos: 5 });
});

test('O6.22 (cliente): una sola propuesta en la fecha de ESCRITURA para todo el lote; fechas económicas intactas', () => {
  const p = payloadCompra('i0', 1, borradorO2(), PARTES);
  expect(p.atribucion).toEqual({ modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA',
    fecha_referencia: '2026-03-20', partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] } });
  expect(p.gastos.find((g) => g.concepto === 'AGENCIA')!.fecha_economica).toBe('2026-02-28');
  expect(p.precio).toBe('200000.00');
  expect(p.pagos_propios.map((x) => x.importe)).toEqual(['20000.00', '180000.00']);
  expect(p).not.toHaveProperty('completitud_adquisicion');                       // O10.29: sin declaración
  expect(textoPropuestaEscritura('Piso Ejemplo', '2026-03-20')).toBe('Según la titularidad de Piso Ejemplo en la escritura (20 mar 2026)');
  expect(avisoGastosAnteriores(borradorO2())).toBe('Para el gasto del 28 feb se usa la titularidad de la escritura, no la vigente en la fecha de ese gasto.');
});

test('O6.24 (cliente): C-COMPRA-03 propone en la fecha económica de su efecto', () => {
  const g = borradorO2().gastos[2];
  const p = payloadGastoCompra('i3', 2, g, { modo: 'TITULARIDAD' }, PARTES);
  expect(p.atribucion).toEqual(expect.objectContaining({ propuesta_vista: expect.objectContaining({ criterio: 'TITULARIDAD_EN_FECHA_ECONOMICA', fecha_referencia: '2026-02-28' }) }));
  expect(payloadGastoCompra('i4', 2, g, { modo: 'NO_LO_SE' }, PARTES).atribucion).toEqual({ modo: 'NO_LO_SE' });
});

test('HF-14 / O10.19 (cliente): «no es gasto del mes» sale del tipo del HECHO, no del efecto', () => {
  expect(esPatrimonial('ADQUISICION_PATRIMONIAL')).toBe(true);
  expect(etiquetaNoGastoMes('ADQUISICION_PATRIMONIAL')).toBe(TEXTO_NO_GASTO_MES);
  expect(etiquetaNoGastoMes('VALOR_ACTIVO')).toBeNull();                       // tipo de efecto: nunca la fuente (M-AC-02)
  expect(etiquetaNoGastoMes('GASTO')).toBeNull();
  const filas = filasDiaADia(borradorO2(), 'Piso Ejemplo', (id) => (id === C1 ? 'Cuenta Nómina' : 'Cuenta Común'));
  expect(filas[0]).toEqual({ clave: 'l-not', fecha: '2026-03-30', titulo: 'Notaría, registro y gestoría Piso Ejemplo',
    detalle: `Cuenta Nómina · ${TEXTO_NO_GASTO_MES}`, importe: '−1.200,00 €' });
  expect(filas.map((f) => f.importe.startsWith('−'))).toEqual([true, true, true, true, true]);
});

test('O10.29 (cliente): la declaración del coste completo está bloqueada hasta la certificación de 0352', () => {
  expect(CONSUMIDORES_0352_HABILITADOS).toBe(false);
});

// ------------------------------------------------------------------ pantallas
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const cliente = () => ({ cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [{ cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: C2, nombre: 'Cuenta Común', moneda: 'EUR' }] })) }) as unknown as ClienteApi;

function patrimonio(partes: ParteEnFecha[] = PARTES) {
  const enviados: any[] = [];
  let siguiente: Respuesta<ResultadoCompra> | null = null;
  const api: ClientePatrimonio = {
    registrarCompra: jest.fn(async (_id, p) => {
      enviados.push(p);
      if (siguiente) { const r = siguiente; siguiente = null; return r; }
      return ok({ propiedad: vista({ row_version: 2 }), idempotente: false, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1.00',
        liquidez_atribuible: '-1.00', gasto_del_mes: '0.00', atribucion: null } });
    }),
    gastoCompraPosterior: jest.fn(async (_id, p) => { enviados.push(p); return ok({ propiedad: vista({ row_version: 3 }), idempotente: false,
      compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1.00', liquidez_atribuible: '-1.00', gasto_del_mes: '0.00', atribucion: null } }); }),
    leerCoste: jest.fn(async () => ok({ coste: coste({}) })),
    titularidadEnFecha: jest.fn(async (_id, fecha) => ok({ fecha, partes: fecha >= '2026-03-20' ? partes : [] })),
  };
  return { api, enviados, forzar: (r: Respuesta<ResultadoCompra>) => (siguiente = r) };
}

function montarCompra(pat: ReturnType<typeof patrimonio>, onCerrar = jest.fn()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CompraScreen cliente={cliente()} patrimonio={pat.api} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={onCerrar} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return onCerrar;
}

async function rellenarHastaB3b() {
  await escribir('compra-precio', '1000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-paso-pagos')).toBeTruthy();
  expect(screen.queryByText(/Con hipoteca/)).toBeNull();                           // sin B2b/B2c
  expect(screen.getByTestId('compra-sin-hipoteca')).toBeTruthy();
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${C1}`));
  await pulsar(`compra-pago-0-cuenta-${C1}`);
  await escribir('compra-pago-0-importe', '1000');
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-paso-gastos')).toBeTruthy();
  await pulsar('compra-gasto-anadir');
  await pulsar('compra-gasto-0-concepto-AGENCIA');
  await escribir('compra-gasto-0-importe', '60');
  await pulsar(`compra-gasto-0-cuenta-${C2}`);
  await escribir('compra-gasto-0-fecha', '28/02/2026');
  await escribir('compra-gasto-0-pago', '28/02/2026');
  await pulsar('compra-continuar');
}

test('B1 → B6: compra completa con la propuesta en la escritura (O6.22 Jest) y sin declaración (O10.29)', async () => {
  const pat = patrimonio();
  const onCerrar = montarCompra(pat);
  await rellenarHastaB3b();
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  expect(pat.api.titularidadEnFecha).toHaveBeenLastCalledWith('p1', '2026-03-20');
  // ninguna opción marcada; el texto nombra la propiedad y la fecha de escritura
  for (const id of ['compra-atr-titularidad', 'compra-atr-manual', 'compra-atr-no-lo-se']) expect(screen.getByTestId(id).props.accessibilityState.checked).toBe(false);
  expect(screen.getByText(/^Según la titularidad de Piso Ejemplo en la escritura \(20 mar 2026\): Tú 60 % · Ana 40 %$/)).toBeTruthy();
  expect(screen.getByTestId('compra-continuar').props.accessibilityState.disabled).toBe(true);
  await pulsar('compra-atr-titularidad');
  expect(screen.getByTestId('compra-atr-aviso').props.children).toBe('Para el gasto del 28 feb se usa la titularidad de la escritura, no la vigente en la fecha de ese gasto.');
  await pulsar('compra-continuar');
  // B4
  expect(screen.getByTestId('compra-res-total-valor').props.children).toBe('1.060,00 €');
  expect(screen.getByTestId('compra-res-sale-valor').props.children).toBe('1.060,00 €');
  expect(screen.getByTestId('compra-res-gasto-mes-valor').props.children).toBe('0,00 €');
  expect(screen.getByTestId('compra-res-estado-valor').props.children).toBe('Parcial · puedes añadir gastos');
  expect(screen.queryByTestId('compra-completo')).toBeNull();                           // O10.29: no se ofrece declarar
  expect(screen.getByTestId('compra-registros').props.children).toBe('Se crean 2 registros con 2 pagos. Se guarda todo junto o nada.');
  expect(screen.queryByText(/Desglose/)).toBeNull();
  expect(screen.queryByText(/Repetir hoy/)).toBeNull();
  await pulsar('compra-guardar');
  const p = pat.enviados[0];
  expect(p.atribucion.propuesta_vista).toEqual({ criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA', fecha_referencia: '2026-03-20',
    partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] });
  expect(p.gastos[0]).toEqual(expect.objectContaining({ concepto: 'AGENCIA', fecha_economica: '2026-02-28', importe: '60.00', cuenta_id: C2 }));
  expect(p).not.toHaveProperty('completitud_adquisicion');
  // B6
  expect(screen.getByTestId('compra-dia')).toBeTruthy();
  expect(screen.getAllByText(new RegExp(TEXTO_NO_GASTO_MES)).length).toBe(2);
  expect(screen.getByText('Compra Piso Ejemplo · en la firma')).toBeTruthy();
  await pulsar('compra-listo');
  expect(onCerrar).toHaveBeenCalledWith(expect.objectContaining({ row_version: 2 }));
});

test('ATRIBUCION_PROPUESTA_DESFASADA: vuelve a B3b sin opción marcada, relee la propuesta y usa una intención nueva', async () => {
  const pat = patrimonio();
  montarCompra(pat);
  await rellenarHastaB3b();
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  await pulsar('compra-atr-titularidad');
  await pulsar('compra-continuar');
  pat.forzar({ tipo: 'RECHAZADO', codigo: 'ATRIBUCION_PROPUESTA_DESFASADA', mensaje: '' });
  await pulsar('compra-guardar');
  await waitFor(() => screen.getByTestId('compra-paso-atribucion'));
  expect(screen.getByTestId('compra-atr-aviso').props.children).toBe(TEXTO_DESFASADA);
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  expect(screen.getByTestId('compra-atr-titularidad').props.accessibilityState.checked).toBe(false);
  expect(pat.api.titularidadEnFecha).toHaveBeenCalledTimes(2);
  await pulsar('compra-atr-titularidad');
  await pulsar('compra-continuar');
  await pulsar('compra-guardar');
  expect(pat.enviados[1].intencion_id).not.toBe(pat.enviados[0].intencion_id);
});

test('O6.23 (cliente): sin titularidad en la escritura no hay propuesta; «Otro reparto» y «No lo sé» siguen disponibles', async () => {
  const pat = patrimonio([]);
  montarCompra(pat);
  await rellenarHastaB3b();
  await waitFor(() => screen.getByTestId('compra-atr-sin-titularidad'));
  expect(screen.queryByTestId('compra-atr-titularidad')).toBeNull();
  await pulsar('compra-atr-no-lo-se');
  await pulsar('compra-continuar');
  await pulsar('compra-guardar');
  expect(pat.enviados[0].atribucion).toEqual({ modo: 'NO_LO_SE' });
});

test('C-COMPRA-03: el gasto posterior propone la titularidad de la fecha del gasto', async () => {
  const pat = patrimonio();
  const onCerrar = jest.fn();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GastoCompraScreen cliente={cliente()} patrimonio={pat.api} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={onCerrar} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await escribir('compra03-fecha', '02/04/2026');
  await waitFor(() => expect(pat.api.titularidadEnFecha).toHaveBeenLastCalledWith('p1', '2026-04-02'));
  await escribir('compra03-importe', '400');
  await pulsar(`compra03-cuenta-${C1}`);
  await escribir('compra03-pago', '02/04/2026');
  await waitFor(() => screen.getByTestId('compra03-atr-titularidad'));
  await pulsar('compra03-atr-titularidad');
  await pulsar('compra03-guardar');
  expect(pat.enviados[0].atribucion.propuesta_vista).toEqual(expect.objectContaining({ criterio: 'TITULARIDAD_EN_FECHA_ECONOMICA', fecha_referencia: '2026-04-02' }));
  expect(onCerrar).toHaveBeenCalledWith(expect.objectContaining({ row_version: 3 }));
});

test('D1: adquisición y mejoras con su estado; «Registrar la compra» sin compra y «Añadir un gasto de la compra» con ella; sin Desglose', () => {
  const pintar = (c: Coste | null) => render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PropiedadFichaScreen vista={vista()} onAtras={jest.fn()} onRevisarValor={jest.fn()} onHistorico={jest.fn()} onTitularidad={jest.fn()} onEditar={jest.fn()}
          coste={c} onRegistrarCompra={jest.fn()} onGastoCompra={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  const sin = pintar(coste({}));
  expect(screen.getByTestId('prop-coste-nd')).toBeTruthy();
  expect(screen.getByTestId('prop-accion-compra')).toBeTruthy();
  expect(screen.queryByTestId('prop-accion-gasto-compra')).toBeNull();
  sin.unmount();
  pintar(coste({ total: '216830.00', estado: 'PARCIAL', motivo_estado: 'SIN_DECLARACION', componentes: 4, tu_parte: { importe: '130098.00', estado: 'COMPLETO' } },
    { total: '0.00', estado: 'NO_DISPONIBLE', componentes: 0 }));
  expect(screen.getByTestId('prop-coste-importe').props.children).toBe('216.830,00 €');
  expect(screen.getByTestId('prop-coste-detalle').props.children).toBe('Parcial · puedes añadir gastos');
  expect(screen.getByTestId('prop-inversion-detalle').props.children).toBe('Parcial · bajas no representadas');
  expect(screen.getByTestId('prop-tu-parte-coste-importe').props.children).toBe('130.098,00 €');
  expect(screen.queryByTestId('prop-mejoras')).toBeNull();
  expect(screen.queryByTestId('prop-accion-compra')).toBeNull();
  expect(screen.getByTestId('prop-accion-gasto-compra')).toBeTruthy();
  expect(screen.queryByText(/Desglose/)).toBeNull();
});
