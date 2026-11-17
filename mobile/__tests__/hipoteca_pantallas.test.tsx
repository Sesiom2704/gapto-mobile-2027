// ============================================================
// GAPTO MOBILE 2027
// Fichero: hipoteca_pantallas.test.tsx
// Ruta: mobile/__tests__/hipoteca_pantallas.test.tsx
// Descripción: Pantallas de la hipoteca contra dobles en memoria (F06-01H; contrato v0.4 §3.2, §3.3, §3.4, §3.5 y §8; mandato T3-F06 bloque 2 v1.1 §15):
//   - bloque «Hipoteca» de la compra: banco, importe, cuenta en la que el banco deja el préstamo (cuentas que pueden recibir dinero en la escritura),
//     fijo/variable, tipo anual, plazo → cuotas, primera cuota posterior a la escritura, cuenta de cargo, titularidad propuesta y modificable, aviso
//     «Cálculo mensual: tipo anual entre 12», «Ver el cuadro» (W-HIP-00) con cabecera «Cerrar», petición exacta y aviso `aviso_reparto_distinto` (O-H30);
//   - Jest R-1: ningún texto del bloque ni de las pantallas dice «ingreso» ni «cobro» (tampoco un rechazo del servidor que lo diga);
//   - cuadro registrado (L-HIP): filas de dos líneas con cifras tabulares, «Cerrar», deuda desconocida «No disponible» (nunca 0), sin swipe;
//   - exposición del pago: el botón «Pagar la cuota» solo con la constante a true (se prueban los dos valores con un mock del módulo; nunca entorno);
//   - pagar cuota con botón: desglose, capital + intereses = cuota, reparto de los intereses visible y modificable, VERSION_DESFASADA recarga,
//     ATRIBUCION_PROPUESTA_DESFASADA relee la propuesta con intención nueva;
//   - revisar el tipo: «Se recalculan N cuotas desde …; las M pagadas no cambian», nunca «bonificación», VERSION_DESFASADA recarga;
//   - ficha de la propiedad: fila «Hipoteca» solo con hipoteca, sin swipe.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// Versión: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; N-31, firma 0f3e5633…): `REVISION_TIPO_EXPUESTA` simulable como el pago; test de exposición de la revisión (true ofrece «Revisar el tipo», false no).
// Versión: 0.3.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…): el pago propone con `titularidad_prestamo` de L-HIP en el vencimiento (no con la de la propiedad) y, con ella, ATRIBUCION_PROPUESTA_DESFASADA recarga la hipoteca.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { StyleSheet, Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { Hipoteca } from '../src/api/hipoteca';
import type { ClientePatrimonio, ParteEnFecha, ResultadoCompra } from '../src/api/patrimonio';
import type { VistaPropiedad } from '../src/api/propiedades';
import { CompraScreen } from '../src/screens/CompraScreen';
import { HipotecaCuadroScreen } from '../src/screens/HipotecaCuadroScreen';
import { PropiedadFichaScreen } from '../src/screens/PropiedadFichaScreen';
import { ProveedorTema } from '../src/theme/tema';
import { ANA, BANCO, CTA, CTA2, cuadroPrevio, FID, hipoteca, PARTES, YO } from './hipoteca_fixtures';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

// Exposición del pago: el módulo real vale false (constante de código); aquí se prueban los dos valores sin tocar entorno ni configuración.
let mockExpuesto = false;
// N-31: la revisión del tipo con su propia constante (el módulo real vale true); se prueban los dos valores.
let mockRevisionExpuesta = true;
jest.mock('../src/domain/hipoteca', () => {
  // Sin spread: el helper de babel evaluaría el getter al construir el objeto y congelaría el valor.
  const m = Object.assign({}, jest.requireActual('../src/domain/hipoteca'));
  Object.defineProperty(m, '__esModule', { value: true });
  Object.defineProperty(m, 'PAGO_CUOTA_EXPUESTO', { get: () => mockExpuesto, enumerable: true });
  Object.defineProperty(m, 'REVISION_TIPO_EXPUESTA', { get: () => mockRevisionExpuesta, enumerable: true });
  return m;
});
const dominioReal = jest.requireActual('../src/domain/hipoteca');

declare const __dirname: string;
const fs: { readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const fuente = (rel: string) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const rechazo = (codigo: string, mensaje = '', detalle?: Record<string, unknown>) => ({ tipo: 'RECHAZADO', codigo, mensaje, ...(detalle ? { detalle } : {}) }) as Respuesta<never>;
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
  mockExpuesto = false;
});
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const PROHIBIDAS = /ingres|cobr/i;
/** Todo el texto pintado (Text) de la pantalla actual. */
const textos = () =>
  screen.UNSAFE_root.findAllByType(Text).map((t: { props: { children?: unknown } }) => [t.props.children].flat(Infinity).filter((x) => typeof x === 'string' || typeof x === 'number').join(''));
/** R-1 sobre todo lo renderizado: textos, etiquetas accesibles, marcadores y testID. */
const sinPalabrasProhibidas = () => {
  expect(textos().filter((t: string) => PROHIBIDAS.test(t))).toEqual([]);
  expect(JSON.stringify(screen.toJSON())).not.toMatch(PROHIBIDAS);
};
const sinSwipe = () => expect(JSON.stringify(screen.toJSON())).not.toMatch(/fila-swipe-|fila-desplazable-|swipe-accion-|swipe-boton-/);

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

const CUENTAS = [{ cuenta_id: CTA, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: CTA2, nombre: 'Cuenta Común', moneda: 'EUR' }];

// ------------------------------------------------------------------ bloque «Hipoteca» de la compra
function clienteCompra() {
  const api = {
    // La cuenta en la que el banco deja el préstamo: solo las que pueden recibir dinero (operación INGRESO del servidor) en la escritura.
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: op === 'INGRESO' ? [CUENTAS[0]] : CUENTAS })),
    listarTerceros: jest.fn(async () => ok({ terceros: [
      { id: BANCO, nombre: 'Banco Ejemplo', naturaleza: 'EMPRESA', enabled: true, row_version: 1 },
      { id: 'b-off', nombre: 'Banco Viejo', naturaleza: 'EMPRESA', enabled: false, row_version: 1 }] })),
    cuadroHipoteca: jest.fn(async () => ok(cuadroPrevio(20))),
  };
  return api as typeof api & ClienteApi;
}

function patrimonio(respuesta?: Respuesta<ResultadoCompra>) {
  const enviados: any[] = [];
  const api: ClientePatrimonio = {
    registrarCompra: jest.fn(async (_id, p) => {
      enviados.push(p);
      return respuesta ?? ok({ propiedad: vista({ row_version: 2 }), idempotente: false, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-200000.00',
        liquidez_atribuible: '-200000.00', gasto_del_mes: '0.00', atribucion: null }, hipoteca: hipoteca(), aviso_reparto_distinto: false });
    }),
    gastoCompraPosterior: jest.fn(),
    leerCoste: jest.fn(),
    titularidadEnFecha: jest.fn(async (_id, fecha) => ok({ fecha, partes: fecha >= '2026-03-20' ? PARTES : [] })),
  };
  return { api, enviados };
}

function montarCompra(cli: ClienteApi, pat: ClientePatrimonio) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CompraScreen cliente={cli} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={() => new Date(2026, 9, 10, 10)} onCerrar={jest.fn()} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

/** B1 → B2 con un pago y el bloque «Hipoteca» completo. */
async function rellenarHipoteca(cli: ReturnType<typeof clienteCompra>) {
  await escribir('compra-precio', '200000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${CTA}`));
  await pulsar(`compra-pago-0-cuenta-${CTA}`);
  await escribir('compra-pago-0-importe', '200000');
  expect(screen.queryByTestId('compra-hip')).toBeNull();
  expect(cli.listarTerceros).not.toHaveBeenCalled();                              // sin hipoteca no se pide nada más
  await pulsar('compra-hip-anadir');
  await waitFor(() => screen.getByTestId(`compra-hip-banco-${BANCO}`));
  expect(screen.queryByTestId('compra-hip-banco-b-off')).toBeNull();              // solo bancos activos
  await pulsar(`compra-hip-banco-${BANCO}`);
  await escribir('compra-hip-importe', '160.000,00');
  await waitFor(() => screen.getByTestId(`compra-hip-desembolso-${CTA}`));
  expect(screen.queryByTestId(`compra-hip-desembolso-${CTA2}`)).toBeNull();
  expect(cli.cuentasElegibles).toHaveBeenCalledWith('INGRESO', '2026-03-20');
  await pulsar(`compra-hip-desembolso-${CTA}`);
  await pulsar('compra-hip-tipo-FIJO');
  await escribir('compra-hip-tasa', '2,5');
  await escribir('compra-hip-plazo', '30');
  expect(screen.getByTestId('compra-hip-n-cuotas').props.children).toBe('360 cuotas mensuales');
  await escribir('compra-hip-primera', '20/03/2026');                             // el mismo día de la escritura no vale
  expect(screen.getByTestId('compra-faltas').props.children).toMatch(/una primera cuota posterior a la escritura/);
  await escribir('compra-hip-primera', '20/04/2026');
  await waitFor(() => screen.getByTestId(`compra-hip-cargo-${CTA2}`));
  await pulsar(`compra-hip-cargo-${CTA2}`);
  await waitFor(() => expect(screen.getByTestId('compra-hip-titularidad-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
}

const BLOQUE_ESPERADO = {
  financiador: { tercero_id: BANCO },
  importe_prestamo: '160000.00',
  cuenta_desembolso_id: CTA,
  titularidad: { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA', fecha_referencia: '2026-03-20',
    partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] } },
  tipo_interes: 'FIJO',
  tasa_anual_pct: '2.5',
  numero_cuotas: 360,
  fecha_primera_cuota: '2026-04-20',
  cuenta_cargo_id: CTA2,
};

async function hastaGuardar() {
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-paso-gastos')).toBeTruthy();
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  await pulsar('compra-atr-titularidad');
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-res-hip-prestamo-valor').props.children).toBe('160.000,00 €');
  expect(screen.getByTestId('compra-res-hip-cuotas-valor').props.children).toBe('360 mensuales desde el 20 abr 2026');
  sinPalabrasProhibidas();
  await pulsar('compra-guardar');
}

test('compra · bloque «Hipoteca»: campos, avisos, R-1 y «Ver el cuadro» (W-HIP-00) con cabecera «Cerrar»', async () => {
  const cli = clienteCompra();
  const pat = patrimonio();
  montarCompra(cli, pat.api);
  await rellenarHipoteca(cli);
  expect(screen.queryByTestId('compra-faltas')).toBeNull();
  expect(screen.getByTestId('compra-continuar').props.accessibilityState).toMatchObject({ disabled: false });
  expect(screen.getByTestId('compra-hip-desembolso-texto').props.children).toBe('El banco deja el préstamo en esta cuenta; desde ella pagas la compra.');
  expect(screen.getByTestId('compra-hip-convencion').props.children).toBe('Cálculo mensual: tipo anual entre 12.');
  expect(textos()).toContain('Cuenta en la que el banco deja el préstamo');
  sinPalabrasProhibidas();
  await pulsar('compra-hip-ver-cuadro');
  expect(cli.cuadroHipoteca).toHaveBeenCalledWith({ capital: '160000.00', tasa_anual: '2.5', numero_cuotas: 360, primera_cuota: '2026-04-20' });
  expect(screen.getByTestId('hip-previo')).toBeTruthy();
  expect(screen.getByTestId('hip-previo-cerrar')).toBeTruthy();
  expect(textos()).toContain('Cerrar');
  expect(textos()).not.toContain('Cancelar');
  expect(screen.getByTestId('hip-fila-1-titulo')).toBeTruthy();                   // dos líneas por fila
  expect(screen.getByTestId('hip-fila-1-detalle').props.children).toBe('Intereses 100,00 € · Capital 400,00 € · Queda 9.600,00 €');
  expect(StyleSheet.flatten(screen.getByTestId('hip-fila-1-cuota').props.style).fontVariant).toEqual(['tabular-nums']);
  expect(screen.queryByTestId('hip-fila-13')).toBeNull();                         // 12 primeras y la última
  expect(screen.getByTestId('hip-fila-20')).toBeTruthy();
  sinSwipe();
  sinPalabrasProhibidas();
  expect(pat.api.registrarCompra).not.toHaveBeenCalled();                          // la vista previa no guarda nada
  await pulsar('hip-previo-cerrar');
  expect(screen.getByTestId('compra-paso-pagos')).toBeTruthy();
  expect(screen.getByTestId('compra-hip-importe').props.value).toBe('160.000,00'); // el bloque se conserva
});

test('compra · petición con el bloque `hipoteca` exacto y aviso `aviso_reparto_distinto` (O-H30) cuando el servidor lo devuelve', async () => {
  const cli = clienteCompra();
  const pat = patrimonio(ok({ propiedad: vista({ row_version: 2 }), idempotente: false, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-200000.00',
    liquidez_atribuible: '-200000.00', gasto_del_mes: '0.00', atribucion: null }, hipoteca: hipoteca({ aviso_reparto_distinto: true }), aviso_reparto_distinto: true }));
  montarCompra(cli, pat.api);
  await rellenarHipoteca(cli);
  await hastaGuardar();
  expect(pat.enviados).toHaveLength(1);
  expect(pat.enviados[0].hipoteca).toStrictEqual(BLOQUE_ESPERADO);
  expect(pat.enviados[0].pagos_propios.map((x: { importe: string }) => x.importe)).toEqual(['200000.00']); // los pagos siguen sumando el precio
  await waitFor(() => screen.getByTestId('compra-hecho'));
  expect(screen.getByTestId('compra-hip-aviso-reparto').props.children).toBe(dominioReal.TEXTO_AVISO_REPARTO);
  sinPalabrasProhibidas();
});

test('compra · sin `aviso_reparto_distinto` no hay aviso; titularidad del préstamo modificable («Otro reparto»)', async () => {
  const cli = clienteCompra();
  const pat = patrimonio();
  montarCompra(cli, pat.api);
  await rellenarHipoteca(cli);
  await pulsar('compra-hip-titularidad-manual');
  await escribir(`compra-hip-titularidad-pct-${YO}`, '50');
  expect(screen.getByTestId('compra-faltas').props.children).toMatch(/un reparto que sume 100 % del préstamo/);
  await escribir(`compra-hip-titularidad-pct-${ANA}`, '50');
  await hastaGuardar();
  expect(pat.enviados[0].hipoteca.titularidad).toStrictEqual({ modo: 'MANUAL', partes: [{ actor_id: ANA, porcentaje: '50' }, { actor_id: YO, porcentaje: '50' }] });
  await waitFor(() => screen.getByTestId('compra-hecho'));
  expect(screen.queryByTestId('compra-hip-aviso-reparto')).toBeNull();
});

test('compra · R-1: un rechazo del servidor con «ingreso» se muestra con el texto propio; CONDICIONES_INCOMPLETAS con su motivo', async () => {
  const cli = clienteCompra();
  const pat = patrimonio(rechazo('CUENTA_SIN_CAPACIDAD', 'Esta cuenta no admite ingresos', { operacion: 'DESEMBOLSO_FINANCIACION' }));
  montarCompra(cli, pat.api);
  await rellenarHipoteca(cli);
  await hastaGuardar();
  await waitFor(() => screen.getByTestId('compra-aviso'));
  expect(textos()).toContain('Esta cuenta no puede recibir dinero en la fecha de la escritura.');
  sinPalabrasProhibidas();
  (pat.api.registrarCompra as jest.Mock).mockResolvedValueOnce(rechazo('CONDICIONES_INCOMPLETAS', 'Revisa', { motivo: 'PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA' }));
  await pulsar('compra-guardar');
  await waitFor(() => expect(textos()).toContain('La primera cuota tiene que ser posterior a la escritura.'));
  (pat.api.registrarCompra as jest.Mock).mockResolvedValueOnce(rechazo('OTRO_RECHAZO', 'Cobro no permitido'));
  await pulsar('compra-guardar');
  await waitFor(() => expect(textos()).toContain(dominioReal.TEXTO_GENERICO));
  sinPalabrasProhibidas();
});

// ------------------------------------------------------------------ cuadro registrado (L-HIP), pago y revisión
function clienteCuadro(inicial: Hipoteca = hipoteca()) {
  const api = {
    hipotecaDePropiedad: jest.fn(async () => ok({ hipoteca: inicial })),
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: CUENTAS })),
    pagarCuotaHipoteca: jest.fn(async () => ok({ idempotente: false, hecho_id: 'h3', hipoteca: hipoteca({ cuotas_pagadas: 3 }) })),
    revisarTipoHipoteca: jest.fn(async () => ok({ idempotente: false, hipoteca: hipoteca({ cuota_vigente: '1010.00' }) })),
  };
  return api as typeof api & ClienteApi;
}

function montarCuadro(cli: ClienteApi, leerPropuesta: (f: string) => Promise<ParteEnFecha[] | null> = jest.fn(async () => PARTES), onCerrar = jest.fn()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <HipotecaCuadroScreen cliente={cli} propiedadId="p1" ahora={() => new Date(2026, 5, 25, 10)} nuevoId={nuevoId} leerPropuesta={leerPropuesta} onCerrar={onCerrar} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return onCerrar;
}

test('exposición: la constante real es false y, con ella, el cuadro NO ofrece «Pagar la cuota»', async () => {
  expect(dominioReal.PAGO_CUOTA_EXPUESTO).toBe(false);
  mockExpuesto = dominioReal.PAGO_CUOTA_EXPUESTO;
  const cli = clienteCuadro();
  const onCerrar = montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.queryByTestId('hip-pagar')).toBeNull();
  expect(screen.getByTestId('hip-revisar')).toBeTruthy();
  expect(textos()).toContain('Cerrar');
  expect(textos()).not.toContain('Cancelar');
  await pulsar('hip-cerrar');
  expect(onCerrar).toHaveBeenCalledWith(false);
});

test('exposición: con la constante a true el pago es un BOTÓN; ninguna fila del cuadro ofrece swipe', async () => {
  mockExpuesto = true;
  const cli = clienteCuadro();
  montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  expect(textos()).toContain('Pagar la cuota 3 · 1.000,00 €');
  sinSwipe();
  for (const i of [1, 2, 3, 4, 5, 6]) expect(screen.getByTestId(`hip-fila-${i}`).props.accessibilityActions).toBeUndefined();
  expect(screen.getByTestId('hip-fila-3-estado').props.children).toBe('Vencida');
  expect(screen.getByTestId('hip-fila-1-estado').props.children).toBe('Pagada');
  expect(StyleSheet.flatten(screen.getByTestId('hip-fila-3-detalle').props.style).fontVariant).toEqual(['tabular-nums']);
  expect(screen.getByTestId('hip-res-deuda-valor').props.children).toBe('98.498,13 €');
  expect(screen.getByTestId('hip-res-pagadas-valor').props.children).toBe('2 de 6');
  sinPalabrasProhibidas();
});

test('N-31 exposición de la revisión: la constante real es true y ofrece «Revisar el tipo»; a false no lo ofrece (con el pago igual)', async () => {
  expect(dominioReal.REVISION_TIPO_EXPUESTA).toBe(true);
  mockRevisionExpuesta = dominioReal.REVISION_TIPO_EXPUESTA;
  mockExpuesto = false;
  montarCuadro(clienteCuadro());
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.getByTestId('hip-revisar')).toBeTruthy();
  screen.unmount();
  mockRevisionExpuesta = false;
  try {
    montarCuadro(clienteCuadro());
    await waitFor(() => screen.getByTestId('hip-cuadro'));
    expect(screen.queryByTestId('hip-revisar')).toBeNull();
    expect(screen.queryByTestId('hip-pagar')).toBeNull();
  } finally {
    mockRevisionExpuesta = true;
  }
});

test('ninguna superficie nueva de la hipoteca importa swipe ni gestos (fuente)', () => {
  for (const f of ['src/screens/HipotecaCuadroScreen.tsx', 'src/screens/PagarCuotaScreen.tsx', 'src/screens/RevisarTipoScreen.tsx']) {
    expect(fuente(f)).not.toMatch(/SwipePrevision|FilaDeslizable|PanResponder|Swipeable|enTarjeta|react-native-gesture-handler/);
  }
  expect(fuente('src/screens/PropiedadFichaScreen.tsx')).toMatch(/<FilaLista testID="prop-accion-hipoteca" titulo="Hipoteca" detalle=\{detalleFichaHipoteca\(p\.hipoteca\)\} onPress=\{p\.onHipoteca\} \/>/);
});

test('L-HIP: el aviso `aviso_reparto_distinto` solo si el servidor lo devuelve; deuda desconocida «No disponible», nunca 0', async () => {
  montarCuadro(clienteCuadro(hipoteca({ aviso_reparto_distinto: true, deuda_pendiente: null, deuda_indeterminada: true })));
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.getByTestId('hip-aviso-reparto').props.children).toBe(dominioReal.TEXTO_AVISO_REPARTO);
  expect(screen.getByTestId('hip-res-deuda-nd')).toBeTruthy();
  expect(screen.queryByTestId('hip-res-deuda-valor')).toBeNull();
  expect(screen.queryByTestId('hip-revisar')).toBeNull();                         // legacy: ni pago ni revisión
  screen.unmount();
  montarCuadro(clienteCuadro());
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.queryByTestId('hip-aviso-reparto')).toBeNull();
});

test('pagar cuota: desglose del servidor, reparto de los intereses propuesto y modificable, y se pinta la hipoteca devuelta', async () => {
  mockExpuesto = true;
  const cli = clienteCuadro();
  const leer = jest.fn(async () => PARTES);
  const onCerrar = montarCuadro(cli, leer);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  await pulsar('hip-pagar');
  expect(screen.getByTestId('hip-pago')).toBeTruthy();
  expect(leer).toHaveBeenCalledWith('2026-06-20');
  expect(textos()).toEqual(expect.arrayContaining(['Capital · reduce lo que debes', 'Intereses · gasto del mes', 'Sale de tu cuenta']));
  expect(screen.getByTestId('hip-desglose-capital-valor').props.children).toBe('753,75 €');
  expect(screen.getByTestId('hip-desglose-intereses-valor').props.children).toBe('246,25 €');
  expect(screen.getByTestId('hip-desglose-salida-valor').props.children).toBe('1.000,00 €');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  expect(textos()).toContain('✓ Según la titularidad del préstamo el 20 jun 2026: Tú 60 % · Ana 40 %');
  expect(screen.getByTestId('hip-pago-fecha').props.value).toBe('20/06/2026');
  sinPalabrasProhibidas();
  sinSwipe();
  await pulsar('hip-pago-reparto-manual');
  await escribir(`hip-pago-reparto-pct-${YO}`, '70');
  await escribir(`hip-pago-reparto-pct-${ANA}`, '30');
  await pulsar('hip-pago-confirmar');
  expect(cli.pagarCuotaHipoteca).toHaveBeenCalledTimes(1);
  const [fid, numero, cuerpo] = cli.pagarCuotaHipoteca.mock.calls[0] as unknown as [string, number, any];
  expect([fid, numero]).toEqual([FID, 3]);
  expect(cuerpo).toStrictEqual({ intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 3, cuenta_id: CTA, fecha_pago: '2026-06-20',
    atribucion: { propuesta_vista: { partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] },
      partes: [{ actor_id: ANA, porcentaje: '30' }, { actor_id: YO, porcentaje: '70' }] } });
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.getByTestId('hip-res-pagadas-valor').props.children).toBe('3 de 6');
  expect(textos()).toContain('Cuota 3 pagada.');
  await pulsar('hip-cerrar');
  expect(onCerrar).toHaveBeenCalledWith(true);
});

// N-30: titularidad DEL PRÉSTAMO en L-HIP con dos tramos; la cuota 3 vence el 2026-06-20 (tramo nuevo 50/50).
const TITULARIDAD_PRESTAMO = [
  { actor_id: YO, porcentaje: '100.0000', yo: true, tercero_id: null, nombre: null, vigente_desde: '2026-03-20', vigente_hasta: '2026-05-31' },
  { actor_id: ANA, porcentaje: '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana', vigente_desde: '2026-06-01', vigente_hasta: null },
  { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, vigente_desde: '2026-06-01', vigente_hasta: null },
];

test('N-30 pagar cuota: la propuesta es la titularidad DEL PRÉSTAMO de L-HIP en el vencimiento, no la de la propiedad', async () => {
  mockExpuesto = true;
  const cli = clienteCuadro(hipoteca({ titularidad_prestamo: TITULARIDAD_PRESTAMO }));
  const leer = jest.fn(async () => PARTES); // titularidad de la propiedad (60/40): no debe usarse
  montarCuadro(cli, leer);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  await pulsar('hip-pagar');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  expect(leer).not.toHaveBeenCalled();
  expect(textos()).toContain('✓ Según la titularidad del préstamo el 20 jun 2026: Tú 50 % · Ana 50 %');
  await pulsar('hip-pago-confirmar');
  const cuerpo = (cli.pagarCuotaHipoteca.mock.calls[0] as unknown as [string, number, any])[2];
  expect(cuerpo.atribucion).toStrictEqual({ propuesta_vista: { partes: [{ actor_id: ANA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }] },
    partes: [{ actor_id: ANA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }] });
});

test('N-30 pagar cuota: con la titularidad del préstamo en L-HIP, ATRIBUCION_PROPUESTA_DESFASADA vuelve a cargar la hipoteca', async () => {
  mockExpuesto = true;
  const cli = clienteCuadro(hipoteca({ titularidad_prestamo: TITULARIDAD_PRESTAMO }));
  montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  await pulsar('hip-pagar');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  cli.pagarCuotaHipoteca.mockResolvedValueOnce(rechazo('ATRIBUCION_PROPUESTA_DESFASADA', 'x'));
  await pulsar('hip-pago-confirmar');
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(cli.hipotecaDePropiedad).toHaveBeenCalledTimes(2);
});

test('pagar cuota: si capital + intereses no da la cuota, no se puede pagar', async () => {
  mockExpuesto = true;
  const h = hipoteca();
  const mala = { ...h.cuotas[2], interes: '246.26' };
  const cli = clienteCuadro(hipoteca({ proxima_cuota: mala }));
  montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  await pulsar('hip-pagar');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  expect(screen.getByTestId('hip-desglose-no-cuadra')).toBeTruthy();
  expect(screen.getByTestId('hip-pago-confirmar').props.accessibilityState).toMatchObject({ disabled: true });
  await pulsar('hip-pago-confirmar');
  expect(cli.pagarCuotaHipoteca).not.toHaveBeenCalled();
});

test('pagar cuota: VERSION_DESFASADA vuelve a cargar la hipoteca; ATRIBUCION_PROPUESTA_DESFASADA relee la propuesta con intención nueva', async () => {
  mockExpuesto = true;
  const cli = clienteCuadro();
  const leer = jest.fn(async () => PARTES);
  montarCuadro(cli, leer);
  await waitFor(() => screen.getByTestId('hip-pagar'));
  await pulsar('hip-pagar');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  cli.pagarCuotaHipoteca.mockResolvedValueOnce(rechazo('ATRIBUCION_PROPUESTA_DESFASADA', 'x'));
  await pulsar('hip-pago-confirmar');
  await waitFor(() => expect(leer).toHaveBeenCalledTimes(2));
  expect(textos()).toContain('La titularidad del préstamo ha cambiado. Revisa el reparto de los intereses.');
  await waitFor(() => expect(screen.getByTestId('hip-pago-reparto-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  cli.pagarCuotaHipoteca.mockResolvedValueOnce(rechazo('VERSION_DESFASADA', 'x'));
  await pulsar('hip-pago-confirmar');
  const intenciones = (cli.pagarCuotaHipoteca.mock.calls as unknown as [string, number, { intencion_id: string }][]).map((c) => c[2].intencion_id);
  expect(new Set(intenciones).size).toBe(2);
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(cli.hipotecaDePropiedad).toHaveBeenCalledTimes(2);
  expect(textos()).toContain(dominioReal.TEXTO_RECARGADA);
});

test('revisar el tipo: «Se recalculan N cuotas desde …; las M pagadas no cambian», nunca «bonificación», y se pinta la hipoteca devuelta', async () => {
  const cli = clienteCuadro();
  montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-revisar'));
  await pulsar('hip-revisar');
  expect(screen.getByTestId('hip-revision')).toBeTruthy();
  expect(screen.getByTestId('hip-rev-vigente').props.children).toBe('Ahora: 3 % fijo desde el 20 mar 2026 · cuota 1.000,00 €.');
  await escribir('hip-rev-desde', '01/05/2026');
  await escribir('hip-rev-tasa', '2,95');
  expect(screen.getByTestId('hip-rev-faltas').props.children).toMatch(/una fecha posterior a la última cuota pagada/);
  expect(screen.getByTestId('hip-rev-confirmar').props.accessibilityState).toMatchObject({ disabled: true });
  await escribir('hip-rev-desde', '01/07/2026');
  expect(screen.getByTestId('hip-rev-alcance').props.children).toBe('Se recalculan 3 cuotas desde el 1 jul 2026; las 2 pagadas no cambian.');
  expect(JSON.stringify(screen.toJSON())).not.toMatch(/bonificaci/i);
  sinPalabrasProhibidas();
  await pulsar('hip-rev-confirmar');
  expect(cli.revisarTipoHipoteca).toHaveBeenCalledWith(FID, { intencion_id: '00000000-0000-4000-8000-000000000001', row_version_esperada: 3, vigente_desde: '2026-07-01', tasa_anual: '2.95' });
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(screen.getByTestId('hip-res-cuota-valor').props.children).toBe('1.010,00 €');
});

test('revisar el tipo: VERSION_DESFASADA vuelve a cargar la hipoteca', async () => {
  const cli = clienteCuadro();
  cli.revisarTipoHipoteca.mockResolvedValueOnce(rechazo('VERSION_DESFASADA', 'x'));
  montarCuadro(cli);
  await waitFor(() => screen.getByTestId('hip-revisar'));
  await pulsar('hip-revisar');
  await escribir('hip-rev-desde', '01/07/2026');
  await escribir('hip-rev-tasa', '2,95');
  await pulsar('hip-rev-confirmar');
  await waitFor(() => screen.getByTestId('hip-cuadro'));
  expect(cli.hipotecaDePropiedad).toHaveBeenCalledTimes(2);
  expect(textos()).toContain(dominioReal.TEXTO_RECARGADA);
});

// ------------------------------------------------------------------ ficha de la propiedad
function montarFicha(h: Hipoteca | null, onHipoteca = jest.fn()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PropiedadFichaScreen vista={vista()} onAtras={jest.fn()} onRevisarValor={jest.fn()} onHistorico={jest.fn()} onTitularidad={jest.fn()} onEditar={jest.fn()}
          hipoteca={h} onHipoteca={onHipoteca} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return onHipoteca;
}

test('ficha: fila «Hipoteca» solo con hipoteca, sin swipe, y abre el cuadro', async () => {
  const onHipoteca = montarFicha(hipoteca());
  expect(screen.getByTestId('prop-accion-hipoteca-detalle').props.children).toBe('Te queda 98.498,13 € · cuota 1.000,00 €');
  expect(screen.getByTestId('prop-accion-hipoteca').props.accessibilityActions).toBeUndefined();
  sinSwipe();
  await pulsar('prop-accion-hipoteca');
  expect(onHipoteca).toHaveBeenCalledTimes(1);
  screen.unmount();
  montarFicha(null);
  expect(screen.queryByTestId('prop-accion-hipoteca')).toBeNull();
});
