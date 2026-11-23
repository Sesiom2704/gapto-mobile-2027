// ============================================================
// GAPTO MOBILE 2027
// Fichero: quien_pago.test.tsx
// Ruta: mobile/__tests__/quien_pago.test.tsx
// Descripción: T2-F06 PAG · «¿Quién pagó?» en el cliente (mandato PAG §1.1, §1.4 y §9.1 «Cliente») contra dobles en memoria:
//   - dominio: signo (saldo = pagado − parte: ME_DEBE si el cotitular pagó menos, LE_DEBO si pagó más), propuestas por el desequilibrio
//     completo (L-08) en los dos sentidos, deuda parcial, NADA, exclusiones (EMPRESA, «No lo sé», cuenta compartida), tres titulares sin
//     posiciones entre terceros, mixto solo bilateral y `posiciones_confirmadas` = lo mostrado;
//   - pantalla: las cinco opciones («Otra combinación» solo con dos titulares), «<Cotitular>, todo» sin cuenta y con LE_DEBO preseleccionado
//     y desmarcable, deuda parcial editable que viaja tal cual, «Cada uno su parte» sin deudas, confirmación por persona, retirada del aviso
//     N3 de HT2-01;
//   - detalle: «Quién pagó», «Pago sin declarar», posiciones en su sentido, limitación de 8quater ampliada y «Ver el movimiento en la
//     cuenta»; movimientos de la cuenta sin punteo.
//   Código de partida: laboratorio lab-t2 43a71c4 (quien_pago.test.tsx), ampliado.
// Versión: 0.1.0 (F06 T2-F06 PAG N1)
// Versión: 0.1.1 (F06 T2-F06 ajuste N3 · KO-1, KO-2 y KO-3 de la prueba en iPhone; decisión de Moisés del 2026-11-15, 022b115a…):
//   texto de la falta de cuenta solo tuya, relectura silenciosa con respuestas atrasadas descartadas y etiquetas visibles del mixto.
// Versión: 0.2.0 (F06 T6 · S3 reforma; F09 0.55 §12.107.2 DP-05, A6): el alta es exprés + «Revisar»; los «Continuar» entre datos, «¿Quién pagó?» y reparto desaparecen (los tres bloques están en la misma pantalla con sus testID de contenedor) y el que llevaba a la confirmación pasa a `gprop-revisar`. Mismas aserciones y payloads.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, LecturaGastoPropiedad, MovimientosCuenta, PayloadGastoPropiedadV2, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { VistaPropiedad } from '../src/api/propiedades';
import type { ParteEfectiva } from '../src/domain/gasto_propiedad';
import { TEXTO_LIMITACION_8QUATER, TEXTO_LIMITACION_SENTIDO } from '../src/domain/gasto_propiedad';
import {
  confirmacion, deudasIniciales, EleccionPago, faltasPago, opcionesPago, pagosWire, posicionesConfirmadas, propuestas, saldos,
} from '../src/domain/quien_pago';
import { DetalleGastoPropiedad, GastoPropiedadScreen } from '../src/screens/GastoPropiedadScreen';
import { MovimientosCuentaScreen } from '../src/screens/MovimientosCuentaScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const ANA = 'a0000000-0000-4000-8000-0000000000a1';
const LUIS = 'b0000000-0000-4000-8000-0000000000b2';
const C1 = 'c0000000-0000-4000-8000-0000000000c1';
const AHORA = () => new Date(2026, 9, 10, 10);
const HOY = '2026-10-10';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;

const yo = (pct = '50.0000'): ParteEfectiva => ({ actor_id: YO, porcentaje: pct, yo: true, nombre: null, naturaleza: null });
const ana = (pct = '50.0000', naturaleza: 'PERSONA' | 'EMPRESA' = 'PERSONA'): ParteEfectiva => ({ actor_id: ANA, porcentaje: pct, yo: false, nombre: 'Ana', naturaleza });
const luis = (pct = '25.0000'): ParteEfectiva => ({ actor_id: LUIS, porcentaje: pct, yo: false, nombre: 'Luis', naturaleza: 'PERSONA' });
const e = (o: Partial<EleccionPago>): EleccionPago => ({ modo: 'YO_TODO', pagadorId: null, mio: '', suyo: '', ...o });

// ------------------------------------------------------------------ dominio
test('signo §1.1.2: P1 → Ana te debe su parte (ME_DEBE); P3 → le debes tu parte (LE_DEBO); P2 → nada', () => {
  const partes = [yo(), ana()];
  expect(propuestas(e({ modo: 'YO_TODO' }), '1500', partes)).toEqual([{ actor_id: ANA, nombre: 'Ana', sentido: 'ME_DEBE', maximo: '750.00' }]);
  expect(propuestas(e({ modo: 'COTITULAR_TODO', pagadorId: ANA }), '1500', partes)).toEqual([{ actor_id: ANA, nombre: 'Ana', sentido: 'LE_DEBO', maximo: '750.00' }]);
  expect(propuestas(e({ modo: 'CADA_UNO' }), '1500', partes)).toEqual([]);
});

test('QP-P4 (mixto bilateral): pago 6.000 y Ana 2.000 de 8.000 al 50 % → Ana te debe 2.000; al revés, le debes 2.000', () => {
  const partes = [yo(), ana()];
  expect(propuestas(e({ modo: 'MIXTO', pagadorId: ANA, mio: '6000', suyo: '2000' }), '8000', partes))
    .toEqual([{ actor_id: ANA, nombre: 'Ana', sentido: 'ME_DEBE', maximo: '2000.00' }]);
  expect(propuestas(e({ modo: 'MIXTO', pagadorId: ANA, mio: '2000', suyo: '6000' }), '8000', partes))
    .toEqual([{ actor_id: ANA, nombre: 'Ana', sentido: 'LE_DEBO', maximo: '2000.00' }]);
  expect(pagosWire(e({ modo: 'MIXTO', pagadorId: ANA, mio: '6000', suyo: '2000' }), '8000', partes, C1))
    .toEqual([{ pagador: 'YO', cuenta_id: C1, importe: '6000.00' }, { pagador: ANA, importe: '2000.00' }]);
});

test('L-08: preseleccionado por el desequilibrio completo, desmarcable (NADA) y parcial (0 < importe ≤ propuesto)', () => {
  const partes = [yo(), ana()];
  const el = e({ modo: 'COTITULAR_TODO', pagadorId: ANA });
  const ps = propuestas(el, '1500', partes);
  const ini = deudasIniciales(ps);
  expect(ini).toEqual({ [ANA]: { marcada: true, importe: '750.00' } });
  expect(saldos(el, '1500', partes, ini)).toEqual([{ actor_id: ANA, sentido: 'LE_DEBO', importe: '750.00' }]);
  expect(saldos(el, '1500', partes, { [ANA]: { marcada: false, importe: '750.00' } })).toEqual([{ actor_id: ANA, sentido: 'NADA' }]);
  const parcial = { [ANA]: { marcada: true, importe: '300' } };
  expect(posicionesConfirmadas(saldos(el, '1500', partes, parcial))).toEqual([{ actor_id: ANA, tipo: 'OBLIGACION_PAGO', importe: '300.00' }]);
  expect(faltasPago(el, '1500', partes, false, null, false, { [ANA]: { marcada: true, importe: '750.01' } }, 2)).toHaveLength(1);
  expect(faltasPago(el, '1500', partes, false, null, false, parcial, 2)).toEqual([]);
});

test('exclusiones: EMPRESA y «No lo sé» sin deuda; la cuenta compartida va por la vía de B3', () => {
  expect(propuestas(e({ modo: 'YO_TODO' }), '1500', [yo(), ana('50.0000', 'EMPRESA')])).toEqual([]);
  expect(propuestas(e({ modo: 'COTITULAR_TODO', pagadorId: ANA }), '1500', [yo(), ana('50.0000', 'EMPRESA')])).toEqual([]);
  expect(propuestas(e({ modo: 'COTITULAR_TODO', pagadorId: ANA }), '1500', [])).toEqual([]);
  expect(propuestas(e({ modo: 'COMPARTIDA' }), '1500', [yo(), ana()])).toEqual([]);
  // KO-1 (prueba en iPhone del tren 2, reclasificado como KO de texto): la causa es la fecha y se remite a la vía compartida.
  expect(faltasPago(e({ modo: 'YO_TODO' }), '1500', [yo(), ana()], false, C1, true, {}, 2)[0])
    .toBe('una cuenta que fuera solo tuya en esa fecha (esta no lo era: si la compartías, elige «Desde una cuenta compartida»)');
});

test('tres titulares: sin posiciones entre terceros (P3 → solo le debo yo a quien pagó; P1 → cada uno me debe su parte)', () => {
  const partes = [yo('50.0000'), ana('25.0000'), luis('25.0000')];
  expect(propuestas(e({ modo: 'COTITULAR_TODO', pagadorId: ANA }), '8000', partes)).toEqual([{ actor_id: ANA, nombre: 'Ana', sentido: 'LE_DEBO', maximo: '4000.00' }]);
  expect(propuestas(e({ modo: 'YO_TODO' }), '8000', partes).map((x) => [x.actor_id, x.sentido, x.maximo]))
    .toEqual([[ANA, 'ME_DEBE', '2000.00'], [LUIS, 'ME_DEBE', '2000.00']]);
  expect(opcionesPago([{ actor_id: ANA, nombre: 'Ana' }, { actor_id: LUIS, nombre: 'Luis' }]).map((x) => x.clave)).not.toContain('mixto');
  expect(opcionesPago([{ actor_id: ANA, nombre: 'Ana' }]).map((x) => x.clave)).toEqual(['yo', 'cada-uno', `cotitular-${ANA}`, 'mixto', 'compartida']);
});

test('confirmación por persona: su parte, lo que puso y la posición o «No queda nada pendiente»', () => {
  const partes = [yo(), ana()];
  const el = e({ modo: 'COTITULAR_TODO', pagadorId: ANA });
  const s = saldos(el, '1500', partes, deudasIniciales(propuestas(el, '1500', partes)));
  expect(confirmacion(el, '1500', partes, s)).toEqual([
    { actor_id: YO, nombre: 'Tú', parte: '750.00', puso: '0.00', posicion: 'Le debes 750,00 € a Ana' },
    { actor_id: ANA, nombre: 'Ana', parte: '750.00', puso: '1500.00', posicion: 'Le debes 750,00 € a Ana' },
  ]);
  const nada = saldos(el, '1500', partes, { [ANA]: { marcada: false, importe: '' } });
  expect(confirmacion(el, '1500', partes, nada).map((x) => x.posicion)).toEqual(['No queda nada pendiente', 'No queda nada pendiente']);
});

// ------------------------------------------------------------------ pantalla
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const marcado = (id: string) => !!screen.getByTestId(id).props.accessibilityState?.checked;
const cliente = () => ({
  cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [{ cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' }] })),
  arbolCategorias: jest.fn(async () => ok({ categorias: [] })),
}) as unknown as ClienteApi;

const propuesta = (tres = false): PropuestaGasto => ({
  fecha: HOY, propiedad_id: 'p1', nombre: 'Piso Ejemplo', titularidad_disponible: true,
  partes: [
    { actor_id: ANA, porcentaje: tres ? '25.0000' : '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana', naturaleza: 'PERSONA' },
    ...(tres ? [{ actor_id: LUIS, porcentaje: '25.0000', yo: false, tercero_id: 't-luis', nombre: 'Luis', naturaleza: 'PERSONA' as const }] : []),
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: { cuenta_id: C1, solo_mia: true, compartida_con: [] },
});

function vista(): VistaPropiedad {
  return { id: 'p1', nombre: 'Piso Ejemplo', row_version: 3, titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
    { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '50.0000' },
    { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '50.0000' }] } } as unknown as VistaPropiedad;
}

function patrimonio(tres = false) {
  return {
    propuestaGasto: jest.fn(async () => ok(propuesta(tres))),
    registrarGastoPropiedad: jest.fn(async (p: PayloadGastoPropiedadV2) => ok({ hecho_id: p.intencion_id, idempotente: false })),
    mejoraHistorica: jest.fn(), listarGastos: jest.fn(), leerGasto: jest.fn(), impactoCorreccion: jest.fn(), corregirClase: jest.fn(),
  } as unknown as ClientePatrimonioB3 & Record<string, jest.Mock>;
}

async function montar(pat: ClientePatrimonioB3, cli: ClienteApi = cliente()) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GastoPropiedadScreen cliente={cli} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await escribir('gprop-importe', '1500');
  // F06 T6 · S3: sin «Continuar» entre bloques (exprés en una pantalla)
}

const cuerpo = (pat: ClientePatrimonioB3) => (pat.registrarGastoPropiedad as jest.Mock).mock.calls[0][0] as PayloadGastoPropiedadV2;

test('«¿Quién pagó?» antes del reparto, con las cinco opciones y sin el aviso N3 de HT2-01', async () => {
  await montar(patrimonio());
  expect(screen.getByTestId('gprop-paso-pago')).toBeTruthy();
  for (const k of ['yo', 'cada-uno', `cotitular-${ANA}`, 'mixto', 'compartida']) expect(screen.getByTestId(`gprop-pago-${k}`)).toBeTruthy();
  expect(screen.getByTestId('gprop-faltas').props.children).toContain('quién pagó');
  expect(screen.queryByTestId('gprop-aviso-a-medias')).toBeNull();
});

test('«Ana, todo»: sin cuenta, LE_DEBO preseleccionado (L-08), confirmación y envío v2', async () => {
  const pat = patrimonio();
  await montar(pat);
  await pulsar(`gprop-pago-cotitular-${ANA}`);
  expect(screen.queryByTestId(`gprop-cuenta-${C1}`)).toBeNull();
  expect(screen.getByTestId('gprop-pago-sin-movimiento')).toBeTruthy();
  // F06 T6 · S3: sin «Continuar» entre bloques (exprés en una pantalla)
  expect(marcado(`gprop-deuda-${ANA}-si`)).toBe(true);
  expect(screen.getByTestId(`gprop-deuda-${ANA}-texto`).props.children).toBe('Le debes 750,00 € a Ana');
  await pulsar('gprop-revisar'); // F06 T6 · S3: exprés → «Revisar»
  expect(screen.getByTestId(`gprop-conf-${ANA}-puso`).props.children).toBe('Puso: 1.500,00 €');
  expect(screen.getByTestId(`gprop-conf-${ANA}-posicion`).props.children).toBe('Le debes 750,00 € a Ana');
  expect(screen.getByTestId('gprop-res-sale-valor').props.children).toBe('0,00 €');
  await pulsar('gprop-guardar');
  const b = cuerpo(pat);
  expect(b.pagos).toEqual([{ pagador: ANA, importe: '1500.00' }]);
  expect(b.saldos).toEqual([{ actor_id: ANA, sentido: 'LE_DEBO', importe: '750.00' }]);
  expect(b.posiciones_confirmadas).toEqual([{ actor_id: ANA, tipo: 'OBLIGACION_PAGO', importe: '750.00' }]);
});

test('deuda parcial editable: «Yo, todo» con Ana debiéndome 400 de 750 viaja tal cual', async () => {
  const pat = patrimonio();
  await montar(pat);
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${C1}`);
  // F06 T6 · S3: sin «Continuar» entre bloques (exprés en una pantalla)
  await escribir(`gprop-deuda-${ANA}-importe`, '400');
  await pulsar('gprop-revisar'); // F06 T6 · S3: exprés → «Revisar»
  expect(screen.getByTestId(`gprop-conf-${ANA}-posicion`).props.children).toBe('Ana te debe 400,00 €');
  await pulsar('gprop-guardar');
  expect(cuerpo(pat).posiciones_confirmadas).toEqual([{ actor_id: ANA, tipo: 'DERECHO_COBRO', importe: '400.00' }]);
  expect(cuerpo(pat).saldos).toEqual([{ actor_id: ANA, sentido: 'ME_DEBE', importe: '400.00' }]);
});

test('«Cada uno su parte»: de tu cuenta sale solo tu parte, Ana pone la suya y no queda nada pendiente', async () => {
  const pat = patrimonio();
  await montar(pat);
  await pulsar('gprop-pago-cada-uno');
  await pulsar(`gprop-cuenta-${C1}`);
  // F06 T6 · S3: sin «Continuar» entre bloques (exprés en una pantalla)
  expect(screen.queryByTestId(`gprop-deuda-${ANA}`)).toBeNull();
  expect(screen.getByTestId('gprop-deuda-nada')).toBeTruthy();
  await pulsar('gprop-revisar'); // F06 T6 · S3: exprés → «Revisar»
  expect(screen.getByTestId('gprop-res-sale-valor').props.children).toBe('750,00 €');
  await pulsar('gprop-guardar');
  expect(cuerpo(pat).pagos).toEqual([{ pagador: ANA, importe: '750.00' }, { pagador: 'YO', cuenta_id: C1, importe: '750.00' }]);
  expect(cuerpo(pat).posiciones_confirmadas).toEqual([]);
});

test('«Otra combinación» (mixto bilateral): lo que puso cada uno debe sumar el importe', async () => {
  const pat = patrimonio();
  await montar(pat);
  await pulsar('gprop-pago-mixto');
  // KO-3: las dos cantidades llevan su etiqueta visible, no solo la accesible.
  expect(screen.getByText('Lo que pusiste tú (desde tu cuenta)')).toBeTruthy();
  expect(screen.getByText('Lo que puso Ana (por su cuenta)')).toBeTruthy();
  await pulsar(`gprop-cuenta-${C1}`);
  await escribir('gprop-pago-mio', '1000');
  await escribir('gprop-pago-suyo', '400');
  expect(screen.getByTestId('gprop-faltas').props.children).toContain('sume el importe');
  await escribir('gprop-pago-suyo', '500');
  // F06 T6 · S3: sin «Continuar» entre bloques (exprés en una pantalla)
  expect(screen.getByTestId(`gprop-deuda-${ANA}-texto`).props.children).toBe('Ana te debe 250,00 €');
  await pulsar('gprop-revisar'); // F06 T6 · S3: exprés → «Revisar»
  await pulsar('gprop-guardar');
  expect(cuerpo(pat).pagos).toEqual([{ pagador: 'YO', cuenta_id: C1, importe: '1000.00' }, { pagador: ANA, importe: '500.00' }]);
});

test('KO-2: al cambiar de cuenta la relectura es silenciosa y se ignoran las respuestas atrasadas', async () => {
  const C2 = 'c0000000-0000-4000-8000-0000000000c2';
  const compartida: PropuestaGasto = { ...propuesta(), cuenta: { cuenta_id: C1, solo_mia: false, compartida_con: [] } };
  const pat = patrimonio();
  const leer = pat.propuestaGasto as unknown as jest.Mock;
  leer.mockImplementation(async () => ok(compartida));
  const cli = { ...cliente(), cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [
    { cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: C2, nombre: 'Cuenta Ahorro', moneda: 'EUR' }] })) } as unknown as ClienteApi;
  await montar(pat, cli);
  const faltas = () => String(screen.queryByTestId('gprop-faltas')?.props.children ?? '');
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${C1}`);
  expect(faltas()).toContain('solo tuya');
  // Relectura pendiente: se conserva la propuesta mostrada (sin «cargando» y sin que el aviso parpadee).
  const pendientes: ((r: Respuesta<PropuestaGasto>) => void)[] = [];
  leer.mockImplementation(() => new Promise((r) => { pendientes.push(r); }));
  await pulsar(`gprop-cuenta-${C2}`);
  expect(faltas()).toContain('solo tuya');
  expect(screen.queryByTestId('gprop-rep-cargando')).toBeNull();
  // Vuelta a C1 antes de que llegue la respuesta de C2: la de C2 (atrasada) no se aplica.
  await pulsar(`gprop-cuenta-${C1}`);
  await act(async () => { pendientes[1](ok(compartida)); });
  await act(async () => { pendientes[0](ok(propuesta())); });
  expect(faltas()).toContain('solo tuya');
});

test('con tres titulares no se ofrece «Otra combinación»', async () => {
  await montar(patrimonio(true));
  expect(screen.queryByTestId('gprop-pago-mixto')).toBeNull();
  expect(screen.getByTestId(`gprop-pago-cotitular-${LUIS}`)).toBeTruthy();
});

// ------------------------------------------------------------------ detalle y movimientos
const lectura = (o: Partial<LecturaGastoPropiedad> = {}): LecturaGastoPropiedad => ({
  hecho_id: 'h1', propiedad_id: 'p1', estado: 'ACTIVO', row_version: 1, tipo_hecho: 'MEJORA_PATRIMONIAL', clase: 'MEJORA', importe: '1500.00',
  fecha: HOY, nota: 'Baño', categoria_id: null, presupuestable: false, procedencia: 'GASTO_PROPIEDAD', efectos_vigentes: 2, con_deuda: true,
  posiciones: [], atribuciones: [], intencion_correccion_id: null, limitacion: TEXTO_LIMITACION_8QUATER, ...o,
});
const envolver = (x: React.ReactElement) => <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar="light">{x}</ProveedorTema></SafeAreaProvider>;

test('detalle: quién pagó, salida real, posición LE_DEBO, sin «Corregir la clase», limitación ampliada y ver el movimiento', async () => {
  const ver = jest.fn();
  render(envolver(<DetalleGastoPropiedad lectura={lectura({ pago: { declarado: true, sale_de_mis_cuentas: '0.00', cuentas_movimiento: [],
    pagos: [{ actor_id: ANA, importe: '1500.00', con_movimiento: false, cuenta_id: null }],
    posiciones: [{ actor_id: ANA, sentido: 'LE_DEBO', tipo: 'OBLIGACION_PAGO', importe: '750.00', estado: 'ACTIVA' }] } })}
    onCorregir={jest.fn()} nombres={{ [ANA]: 'Ana', [YO]: 'Tú' }} onVerMovimientos={ver} />));
  expect(screen.getByTestId(`gprop-det-pago-${ANA}`)).toBeTruthy();
  expect(screen.getByTestId(`gprop-det-pos-${ANA}`)).toBeTruthy();
  expect(screen.getByText('Le debes a Ana')).toBeTruthy();
  expect(screen.queryByTestId('gprop-corregir-clase')).toBeNull();
  expect(screen.getByTestId('gprop-limitacion').props.children).toBe(TEXTO_LIMITACION_8QUATER);
  expect(screen.getByTestId('gprop-limitacion-sentido').props.children).toBe(TEXTO_LIMITACION_SENTIDO);
  expect(screen.queryByTestId('gprop-ver-movimiento')).toBeNull();                // no salió nada de tus cuentas
});

test('detalle de un hecho de B3 del tren 1: «Pago sin declarar» y acceso al movimiento de la cuenta', async () => {
  const ver = jest.fn();
  render(envolver(<DetalleGastoPropiedad lectura={lectura({ con_deuda: false, efectos_vigentes: 1, intencion_correccion_id: 'i', limitacion: null,
    pago: { declarado: false, sale_de_mis_cuentas: '1500.00', cuentas_movimiento: [C1], pagos: [], posiciones: [] } })}
    onCorregir={jest.fn()} nombres={{}} onVerMovimientos={ver} />));
  expect(screen.getByTestId('gprop-det-pago-sin-declarar')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('gprop-ver-movimiento')));
  expect(ver).toHaveBeenCalledWith(C1);
});

test('movimientos de la cuenta: en orden, el del gasto resaltado y sin punteo ni acciones de conciliación', async () => {
  const datos: MovimientosCuenta = { cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR', pagina: 0, limite: 50, hay_mas: false, movimientos: [
    { movimiento_id: 'm1', fecha: '2026-10-01', importe: '2000.00', descripcion: 'Nómina', clase: 'OPERACION', hechos: [] },
    { movimiento_id: 'm2', fecha: '2026-10-10', importe: '-750.00', descripcion: null, clase: 'OPERACION',
      hechos: [{ hecho_id: 'h1', concepto: 'Baño', tipo_hecho: 'MEJORA_PATRIMONIAL', importe_asignado: '-750.00' }] }] };
  render(envolver(<MovimientosCuentaScreen cargar={async () => ok(datos)} resaltar="h1" onCerrar={jest.fn()} />));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  expect(screen.getByTestId('movs-fila-m2-importe').props.children).toBe('−750,00 €');
  expect(screen.getByTestId('movs-fila-m2-concepto').props.children).toBe('▶ Baño');
  expect(screen.getByTestId('movs-fila-m1-importe').props.children).toBe('+2.000,00 €');
  expect(screen.queryByText(/puntead|concilia/i)).toBeNull();
});
