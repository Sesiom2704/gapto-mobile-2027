// ============================================================
// GAPTO MOBILE 2027
// Fichero: reparto.test.tsx
// Ruta: mobile/__tests__/reparto.test.tsx
// Descripción: Reparto, pagador real y posiciones (F05-06 M3 §B2; lámina REP v0.2; F05 §57). Dominio puro (partes iguales con el céntimo en la última fila, falta por repartir sin completar solo, lo que falta, payload sellado, deudas previstas, neto «Sin determinar», corrección solo de importes). Pantallas por estado: gasto pagado por otra persona (A1/A2: selector solo de personas E7, «Sí, le debo» / «No» / «No lo sé», revisión en cuatro bloques), cena repartida (B1–B4: «A partes iguales», «¿Te deben su parte?», revisión), reparto incompleto en oscuro (D1), envío (doble toque, INDETERMINADO con la MISMA identidad, rechazo), éxito con «Pendiente con»; «Pendiente con» (C1, C4, D2), cobro (C3), pago sin tercero (E8) y perdón; «Corregir reparto» (E6) con lo excluido atenuado y su motivo, revisión de impacto, motivo obligatorio, rechazos en lenguaje llano e INDETERMINADO sin reintento; detalle de la Actividad y registro («Repartir» / «Otra persona»).
// Versión: 0.1.0 (F05-06 M3 §B2)
// v0.1.1 (F05-06 M3 CORR-01, R-M3-05): dos personas con la misma parte; cada «Pendiente con» señala a su persona por el `tercero_id` del servidor, también con las posiciones en otro orden.
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, DetalleActividad, FilaActividad } from '../src/api/cliente';
import {
  BaseCompartido,
  componerCorreccion,
  componerPayload,
  deudasPrevistas,
  faltaCompartido,
  faltaCorreccion,
  FormularioCompartido,
  motivoRechazoCorreccion,
  partesIguales,
  PendienteConPersona,
  RepartoDeHecho,
  resumenReparto,
  TEXTO_NETO_SIN_DETERMINAR,
  TEXTO_SIN_TERCERO_PAGA,
  TEXTO_SOLO_PERSONAS,
  textoNeto,
} from '../src/domain/reparto';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { CorregirRepartoScreen } from '../src/screens/CorregirRepartoScreen';
import { GastoCompartidoScreen } from '../src/screens/GastoCompartidoScreen';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
// Arranque en frío del primer test de pantalla (misma convención que capacidades.test.tsx).
jest.setTimeout(30000);

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

const BASE_CENA: BaseCompartido = {
  importe: '44.50', fechaHecho: '2026-10-09', presupuestable: true, categoria: { estado: 'CATEGORIA', categoria_id: 'rest', magnitudes: [] },
  categoriaNombre: 'Restaurantes', terceroId: 'tagliatella', terceroNombre: 'La Tagliatella', nota: 'Cena con amigos', cuentaId: null,
};
const BASE_PELU: BaseCompartido = { ...BASE_CENA, importe: '15.00', fechaHecho: '2026-10-03', categoriaNombre: 'Cuidado personal', terceroId: 'lola', terceroNombre: 'Peluquería Lola', nota: null };
const CUENTAS = [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', moneda: 'EUR' }, { cuenta_id: 'efectivo', nombre: 'Efectivo', moneda: 'EUR' }];
const TERCEROS = [
  { id: 'tania', nombre: 'Tania', naturaleza: 'PERSONA', enabled: true, row_version: 1, usos: 12 },
  { id: 'carlos', nombre: 'Carlos', naturaleza: 'PERSONA', enabled: true, row_version: 1, usos: 4 },
  { id: 'lola', nombre: 'Peluquería Lola', naturaleza: 'EMPRESA', enabled: true, row_version: 1, usos: 3 },
  { id: 'simon', nombre: 'Simón', naturaleza: 'PERSONA', enabled: false, row_version: 2, usos: 2 },
];

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    registrarGastoPagado: jest.fn(),
    cuentasPago: jest.fn(),
    gastoMes: jest.fn(),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: CUENTAS } }) as any),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: TERCEROS } }) as any),
    registrarGastoCompartido: jest.fn(async (pl: any) => ({ tipo: 'OK', datos: {
      intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false, importe: pl.importe, moneda: 'EUR', estado_atribucion: 'COMPLETA',
      tu_parte: pl.reparto.modo === 'SOLO_MIO' ? pl.importe : pl.reparto.mi_parte, movimiento: pl.pagado_por.tipo === 'CUENTA' ? `-${pl.importe}` : null,
      posiciones: pl.pagado_por.tipo === 'PERSONA' && pl.pagado_por.le_debo === 'SI'
        ? [{ entidad_id: 'pos-o', tipo: 'OBLIGACION_PAGO', tercero_id: pl.pagado_por.tercero_id, importe: pl.importe }]
        : (pl.reparto.partes ?? []).filter((x: any) => x.me_debe === 'SI').map((x: any) => ({ entidad_id: `pos-${x.tercero_id}`, tipo: 'DERECHO_COBRO', tercero_id: x.tercero_id, importe: x.importe })),
      aviso: '' } }) as any),
    ...o,
  } as ClienteApi;
}

function envolver(ui: React.ReactElement, forzar?: 'dark' | 'light') {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema forzar={forzar}>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const plano = () => JSON.stringify(screen.toJSON());

// ================================================================== dominio
describe('dominio', () => {
  const form = (o: Partial<FormularioCompartido> = {}): FormularioCompartido => ({
    modo: 'REPARTIR',
    filas: [
      { terceroId: null, nombre: 'Tú', importeTexto: '14,50', meDebe: null },
      { terceroId: 'tania', nombre: 'Tania', importeTexto: '15,00', meDebe: 'SI' },
      { terceroId: 'carlos', nombre: 'Carlos', importeTexto: '15,00', meDebe: 'NO' },
    ],
    pagador: { tipo: 'CUENTA', cuentaId: 'bbva' },
    ...o,
  });

  test('D-REP-04: a partes iguales con el céntimo sobrante en la última fila', () => {
    expect(partesIguales('44.50', 3)).toEqual(['14.83', '14.83', '14.84']);
    expect(partesIguales('10.00', 2)).toEqual(['5.00', '5.00']);
    expect(partesIguales('0.01', 2)).toEqual(['0.00', '0.01']);
  });

  test('D-REP-03 / G3: lo que falta queda sin indicar y nunca se completa solo; lo que excede se señala', () => {
    const f = form();
    f.filas[2].importeTexto = '';
    expect(resumenReparto('44.50', f.filas)).toEqual({ repartido: '29.50', falta: '15.00', sinIndicar: true, excede: false, invalidas: 0 });
    f.filas[2].importeTexto = '20';
    expect(resumenReparto('44.50', f.filas).excede).toBe(true);
    expect(faltaCompartido('44.50', f)).toContain('un reparto que no supere el total');
  });

  test('D-REP-05 / INV-04: sin respuesta no se revisa; «Sí» exige importe; con otra persona pagando no se pregunta', () => {
    const f = form();
    f.filas[1].meDebe = null;
    expect(faltaCompartido('44.50', f)).toEqual(['si Tania te debe su parte']);
    f.filas[1] = { ...f.filas[1], meDebe: 'SI', importeTexto: '' };
    expect(faltaCompartido('44.50', f)).toEqual(['la parte de Tania']);
    const g = form({ pagador: { tipo: 'PERSONA', terceroId: 'tania', nombre: 'Tania', leDebo: 'SI' } });
    g.filas[0].importeTexto = '';
    expect(faltaCompartido('44.50', g)).toEqual(['tu parte, para saber cuánto le debes']);
  });

  test('payload sellado: vacío = null (sin indicar), «me_debe» solo si pagué yo, comercio y nota', () => {
    const f = form();
    f.filas[2].importeTexto = '';
    f.filas[2].meDebe = 'NO';
    const pl = componerPayload(BASE_CENA, f, 'id-1');
    expect(pl).toEqual({
      intencion_id: 'id-1', importe: '44.50', moneda: 'EUR', fecha_hecho: '2026-10-09', presupuestable: true,
      categoria: BASE_CENA.categoria, tercero_id: 'tagliatella', nota: 'Cena con amigos',
      pagado_por: { tipo: 'CUENTA', cuenta_id: 'bbva' },
      reparto: { modo: 'REPARTIR', mi_parte: '14.50', partes: [{ tercero_id: 'tania', importe: '15.00', me_debe: 'SI' }, { tercero_id: 'carlos', importe: null, me_debe: 'NO' }] },
    });
    const pelu = componerPayload(BASE_PELU, form({ modo: 'SOLO_MIO', pagador: { tipo: 'PERSONA', terceroId: 'tania', nombre: 'Tania', leDebo: 'NO_LO_SE' } }), 'id-2');
    expect(pelu.reparto).toEqual({ modo: 'SOLO_MIO' });
    expect(pelu.pagado_por).toEqual({ tipo: 'PERSONA', tercero_id: 'tania', le_debo: 'NO_LO_SE' });
    expect('nota' in pelu).toBe(false);
    expect(() => componerPayload(BASE_CENA, form({ pagador: { tipo: 'CUENTA', cuentaId: null } }), 'x')).toThrow();
  });

  test('deudas previstas: solo con «Sí»', () => {
    expect(deudasPrevistas(BASE_CENA, form())).toEqual([{ quien: 'Tania', sentido: 'TE_DEBE', importe: '15.00' }]);
    const pelu = form({ modo: 'SOLO_MIO', pagador: { tipo: 'PERSONA', terceroId: 'tania', nombre: 'Tania', leDebo: 'SI' } });
    expect(deudasPrevistas(BASE_PELU, pelu)).toEqual([{ quien: 'Tania', sentido: 'LE_DEBES', importe: '15.00' }]);
    expect(deudasPrevistas(BASE_PELU, { ...pelu, pagador: { ...pelu.pagador, leDebo: 'NO_LO_SE' } as any })).toEqual([]);
  });

  test('D-REP-07/09: el neto no salda nada y con un saldo desconocido es «Sin determinar», nunca 0,00 €', () => {
    expect(textoNeto({ neto: '0.00', neto_estado: 'DETERMINADO' })).toBe('Neto: 0,00 €. Es un cálculo: no salda nada. Cada cosa sigue pendiente hasta que registres un cobro, un pago o la perdones.');
    expect(textoNeto({ neto: null, neto_estado: 'INDETERMINADO' })).toBe(TEXTO_NETO_SIN_DETERMINAR);
    expect(TEXTO_NETO_SIN_DETERMINAR).not.toContain('0,00');
  });

  test('corrección: solo importes de quien ya está, misma suma, nunca 0, motivo obligatorio', () => {
    const r: RepartoDeHecho = { hecho_id: 'h', row_version: 3, importe: '44.50', estado_atribucion: 'COMPLETA', corregible: true, motivo: null, partes: [
      { atribucion_id: 'a-yo', es_yo: true, tercero_id: null, nombre: 'Tú', importe: '14.50', posicion: null },
      { atribucion_id: 'a-tania', es_yo: false, tercero_id: 'tania', nombre: 'Tania', importe: '15.00', posicion: { entidad_id: 'p', tipo: 'DERECHO_COBRO', saldo: '15.00' } },
      { atribucion_id: 'a-carlos', es_yo: false, tercero_id: 'carlos', nombre: 'Carlos', importe: '15.00', posicion: null },
    ] };
    expect(faltaCorreccion(r, { 'a-yo': '9,50' }, 'x')).toEqual(['que las partes sumen lo mismo que antes (44,50 €)']);
    expect(faltaCorreccion(r, { 'a-yo': '29,50', 'a-carlos': '0' }, 'x')[0]).toMatch(/importes válidos/);
    expect(faltaCorreccion(r, { 'a-yo': '9,50', 'a-tania': '20' }, ' ')).toEqual(['el motivo']);
    expect(componerCorreccion(r, { 'a-yo': '9,50', 'a-tania': '20', 'a-carlos': '15,00' }, ' Me equivoqué ')).toEqual({
      row_version: 3, motivo: 'Me equivoqué', partes: [{ atribucion_id: 'a-yo', importe: '9.50' }, { atribucion_id: 'a-tania', importe: '20.00' }],
    });
  });

  test('rechazos de la corrección en lenguaje llano, sin códigos', () => {
    expect(motivoRechazoCorreccion('REPARTO_NO_CORREGIBLE', { motivo: 'ORIGEN_IMPORTADO' })).toMatch(/versión anterior/);
    expect(motivoRechazoCorreccion('CORRECCION_AGREGADA_REQUERIDA', { motivo: 'REPARTO_CAMBIA_POSICIONES' })).toMatch(/todavía no se puede corregir aquí/);
    expect(motivoRechazoCorreccion('EXCEDE_SALDO_DEL_DERECHO')).toMatch(/por debajo de lo que ya se ha pagado/);
    expect(motivoRechazoCorreccion('LO_QUE_SEA')).not.toMatch(/[A-Z]{2,}_/);
  });
});

// ================================================================== A · peluquería
async function elegirPersona(nombre: string) {
  await screen.findByTestId('selector-persona');
  fireEvent.press(await screen.findByLabelText(nombre));
}

describe('A · pagado por otra persona', () => {
  test('A1: «Otra persona» pregunta quién pagó (solo personas activas) y si le debes; «No lo sé» no crea deuda', async () => {
    const c = cliente();
    envolver(<GastoCompartidoScreen cliente={c} nuevoId={nuevoId} base={BASE_PELU} inicial={{ repartir: false, otraPersona: true }} onVolver={jest.fn()} onCerrar={jest.fn()} />);
    expect(await screen.findByText('Peluquería Lola')).toBeTruthy();
    fireEvent.press(screen.getByTestId('pagador-persona'));
    await screen.findByTestId('selector-persona');
    expect(screen.getByText(TEXTO_SOLO_PERSONAS)).toBeTruthy();
    expect(screen.getByLabelText('Tania')).toBeTruthy();
    expect(screen.queryByTestId('persona-lola')).toBeNull(); // empresa
    expect(screen.queryByTestId('persona-simon')).toBeNull(); // desactivada
    fireEvent.press(screen.getByLabelText('Tania'));
    expect(await screen.findByText('¿Le debes este dinero a Tania?')).toBeTruthy();
    expect(screen.getByText('Sí, le debo 15,00 €')).toBeTruthy();
    expect(screen.getByTestId('pagador-no-sale-dinero')).toBeTruthy();
    expect(screen.getByTestId('compartido-revisar').props.accessibilityState?.disabled).toBe(true);
    fireEvent.press(screen.getByTestId('le-debo-no-lo-se'));
    expect(screen.getByTestId('le-debo-no-lo-se-texto')).toBeTruthy();
    fireEvent.press(screen.getByTestId('compartido-revisar'));
    expect(await screen.findByTestId('compartido-revision')).toBeTruthy();
    expect(screen.getByText('Pagó Tania')).toBeTruthy();
    expect(screen.getByTestId('revision-sin-deudas')).toBeTruthy();
  });

  test('A2: con «Sí», revisión en cuatro bloques y una sola llamada OP-22 con la obligación', async () => {
    const c = cliente();
    const onCerrar = jest.fn();
    envolver(<GastoCompartidoScreen cliente={c} nuevoId={nuevoId} base={BASE_PELU} inicial={{ repartir: false, otraPersona: true }} onVolver={jest.fn()} onCerrar={onCerrar} />);
    fireEvent.press(await screen.findByTestId('pagador-persona'));
    await elegirPersona('Tania');
    fireEvent.press(await screen.findByTestId('le-debo-si'));
    fireEvent.press(screen.getByTestId('compartido-revisar'));
    for (const b of ['revision-gasto', 'revision-tu-parte', 'revision-dinero', 'revision-deudas']) expect(await screen.findByTestId(b)).toBeTruthy();
    expect(screen.getByText('Le debes a Tania')).toBeTruthy();
    expect(screen.getByText('Nueva obligación')).toBeTruthy();
    expect(within(screen.getByTestId('revision-dinero')).getByText('No sale dinero de tus cuentas')).toBeTruthy();
    fireEvent.press(screen.getByTestId('registrar-compartido'));
    await screen.findByTestId('compartido-exito');
    expect(c.registrarGastoCompartido).toHaveBeenCalledTimes(1);
    expect((c.registrarGastoCompartido as jest.Mock).mock.calls[0][0]).toMatchObject({ pagado_por: { tipo: 'PERSONA', tercero_id: 'tania', le_debo: 'SI' }, reparto: { modo: 'SOLO_MIO' } });
    expect(screen.getByText('No sale dinero de tus cuentas')).toBeTruthy();
    fireEvent.press(screen.getByTestId('compartido-ver-pendiente-tania'));
    expect(onCerrar).toHaveBeenCalledWith(true, { terceroId: 'tania', nombre: 'Tania' });
  });

  test('E7: «+ Crear persona» da de alta un tercero PERSONA y lo elige', async () => {
    const altaTercero = jest.fn(async (x: any) => ({ tipo: 'OK', datos: { tercero: { ...x, enabled: true, row_version: 1 }, idempotente: false, modificadas: [] } }) as any);
    const c = cliente({ altaTercero });
    envolver(<GastoCompartidoScreen cliente={c} nuevoId={nuevoId} base={BASE_PELU} inicial={{ repartir: false, otraPersona: true }} onVolver={jest.fn()} onCerrar={jest.fn()} />);
    fireEvent.press(await screen.findByTestId('pagador-persona'));
    await screen.findByTestId('selector-persona');
    fireEvent.changeText(screen.getByTestId('selector-persona-buscar'), 'Marta');
    fireEvent.press(screen.getByTestId('selector-persona-crear'));
    expect(await screen.findByText('¿Le debes este dinero a Marta?')).toBeTruthy();
    expect(altaTercero).toHaveBeenCalledWith(expect.objectContaining({ nombre: 'Marta', naturaleza: 'PERSONA' }));
  });

  test('«Cambiar» vuelve al registro; «Cancelar» cierra sin registrar', async () => {
    const onVolver = jest.fn();
    const onCerrar = jest.fn();
    envolver(<GastoCompartidoScreen cliente={cliente()} nuevoId={nuevoId} base={BASE_PELU} inicial={{ repartir: false, otraPersona: true }} onVolver={onVolver} onCerrar={onCerrar} />);
    fireEvent.press(await screen.findByTestId('compartido-cambiar'));
    expect(onVolver).toHaveBeenCalled();
    fireEvent.press(screen.getByTestId('compartido-cancelar'));
    expect(onCerrar).toHaveBeenCalledWith(false);
  });
});

// ================================================================== B · cena
async function cenaHastaReparto(c: ClienteApi, forzar?: 'dark', onCerrar: jest.Mock = jest.fn()) {
  envolver(<GastoCompartidoScreen cliente={c} nuevoId={nuevoId} base={BASE_CENA} inicial={{ repartir: true, otraPersona: false }} onVolver={jest.fn()} onCerrar={onCerrar} />, forzar);
  await screen.findByTestId('compartido-reparto');
  for (const nombre of ['Tania', 'Carlos']) {
    fireEvent.press(screen.getByTestId('reparto-anadir'));
    await elegirPersona(nombre);
    await screen.findByTestId(`reparto-fila-${nombre.toLowerCase()}`);
  }
}

describe('B · cena repartida', () => {
  test('B2: «A partes iguales» rellena a la vista con el céntimo en la última fila; el total no cambia', async () => {
    await cenaHastaReparto(cliente());
    expect(screen.getByTestId('reparto-total').props.children).toBe('44,50 €');
    expect(screen.getByTestId('reparto-falta').props.children).toBe('44,50 € · sin indicar');
    fireEvent.press(screen.getByTestId('reparto-iguales'));
    expect(screen.getByTestId('reparto-importe-yo').props.value).toBe('14,83');
    expect(screen.getByTestId('reparto-importe-tania').props.value).toBe('14,83');
    expect(screen.getByTestId('reparto-importe-carlos').props.value).toBe('14,84');
    expect(screen.getByTestId('reparto-falta').props.children).toBe('0,00 €');
  });

  test('B1–B4: reparto, «¿Te deben su parte?» persona a persona, revisión y OP-22', async () => {
    const c = cliente();
    await cenaHastaReparto(c);
    fireEvent.changeText(screen.getByTestId('reparto-importe-yo'), '14,50');
    fireEvent.changeText(screen.getByTestId('reparto-importe-tania'), '15');
    fireEvent.changeText(screen.getByTestId('reparto-importe-carlos'), '15');
    fireEvent.press(screen.getByTestId('reparto-listo'));
    expect(await screen.findByText('3 personas · tú 14,50 €')).toBeTruthy();
    fireEvent.press(screen.getByTestId('compartido-cuenta-bbva'));
    fireEvent.press(screen.getByTestId('compartido-revisar'));
    expect(await screen.findByTestId('compartido-te-deben')).toBeTruthy();
    expect(screen.getByTestId('te-deben-revisar').props.accessibilityState?.disabled).toBe(true);
    fireEvent.press(screen.getByTestId('te-debe-tania-si'));
    fireEvent.press(screen.getByTestId('te-debe-carlos-no'));
    fireEvent.press(screen.getByTestId('te-deben-revisar'));
    await screen.findByTestId('compartido-revision');
    expect(screen.getByText('−44,50 €')).toBeTruthy();
    expect(screen.getByText('Tania te debe')).toBeTruthy();
    expect(screen.getByText('Nuevo derecho de cobro')).toBeTruthy();
    expect(screen.queryByText('Carlos te debe')).toBeNull();
    fireEvent.press(screen.getByTestId('registrar-compartido'));
    await screen.findByTestId('compartido-exito');
    expect((c.registrarGastoCompartido as jest.Mock).mock.calls[0][0]).toMatchObject({
      pagado_por: { tipo: 'CUENTA', cuenta_id: 'bbva' },
      reparto: { modo: 'REPARTIR', mi_parte: '14.50', partes: [{ tercero_id: 'tania', importe: '15.00', me_debe: 'SI' }, { tercero_id: 'carlos', importe: '15.00', me_debe: 'NO' }] },
    });
    expect(screen.getByTestId('compartido-exito-dinero').props.children).toBe('Movimiento real: −44,50 €');
  });

  // CORR-01 (R-M3-05): el éxito empareja cada posición por el tercero_id que fija el servidor, nunca por importe.
  async function cenaPartesIguales(c: ClienteApi, onCerrar: jest.Mock = jest.fn()) {
    await cenaHastaReparto(c, undefined, onCerrar);
    fireEvent.changeText(screen.getByTestId('reparto-importe-yo'), '14,50');
    fireEvent.changeText(screen.getByTestId('reparto-importe-tania'), '15');
    fireEvent.changeText(screen.getByTestId('reparto-importe-carlos'), '15');
    fireEvent.press(screen.getByTestId('reparto-listo'));
    fireEvent.press(await screen.findByTestId('compartido-cuenta-bbva'));
    fireEvent.press(screen.getByTestId('compartido-revisar'));
    fireEvent.press(await screen.findByTestId('te-debe-tania-si'));
    fireEvent.press(screen.getByTestId('te-debe-carlos-si'));
    fireEvent.press(screen.getByTestId('te-deben-revisar'));
    await screen.findByTestId('compartido-revision');
    fireEvent.press(screen.getByTestId('registrar-compartido'));
    await screen.findByTestId('compartido-exito');
  }

  test('CORR-01: dos personas con la misma parte; cada «Pendiente con» señala a su persona', async () => {
    const onCerrar = jest.fn();
    await cenaPartesIguales(cliente(), onCerrar);
    expect(screen.getAllByTestId('compartido-ver-pendiente-tania')).toHaveLength(1);
    expect(screen.getAllByTestId('compartido-ver-pendiente-carlos')).toHaveLength(1);
    expect(screen.getByText('Pendiente con Tania')).toBeTruthy();
    expect(screen.getByText('Pendiente con Carlos')).toBeTruthy();
    fireEvent.press(screen.getByTestId('compartido-ver-pendiente-carlos'));
    expect(onCerrar).toHaveBeenLastCalledWith(true, { terceroId: 'carlos', nombre: 'Carlos' });
    fireEvent.press(screen.getByTestId('compartido-ver-pendiente-tania'));
    expect(onCerrar).toHaveBeenLastCalledWith(true, { terceroId: 'tania', nombre: 'Tania' });
  });

  test('CORR-01: el enlace sigue al tercero_id del servidor aunque el orden de las posiciones sea otro', async () => {
    const onCerrar = jest.fn();
    const registrarGastoCompartido = jest.fn(async (pl: any) => ({ tipo: 'OK', datos: {
      intencion_id: pl.intencion_id, hecho_id: pl.intencion_id, idempotente: false, importe: pl.importe, moneda: 'EUR', estado_atribucion: 'COMPLETA',
      tu_parte: pl.reparto.mi_parte, movimiento: `-${pl.importe}`,
      posiciones: [{ entidad_id: 'pos-c', tipo: 'DERECHO_COBRO', tercero_id: 'carlos', importe: '15.00' },
        { entidad_id: 'pos-t', tipo: 'DERECHO_COBRO', tercero_id: 'tania', importe: '15.00' }],
      aviso: '' } }) as any);
    await cenaPartesIguales(cliente({ registrarGastoCompartido }), onCerrar);
    fireEvent.press(screen.getByTestId('compartido-ver-pendiente-carlos'));
    expect(onCerrar).toHaveBeenLastCalledWith(true, { terceroId: 'carlos', nombre: 'Carlos' });
    fireEvent.press(screen.getByTestId('compartido-ver-pendiente-tania'));
    expect(onCerrar).toHaveBeenLastCalledWith(true, { terceroId: 'tania', nombre: 'Tania' });
  });

  test('D1: en oscuro, reparto incompleto: la parte vacía queda sin indicar y no se completa sola', async () => {
    await cenaHastaReparto(cliente(), 'dark');
    fireEvent.changeText(screen.getByTestId('reparto-importe-yo'), '14,50');
    fireEvent.changeText(screen.getByTestId('reparto-importe-tania'), '15');
    expect(screen.getByTestId('reparto-falta').props.children).toBe('15,00 € · sin indicar');
    expect(screen.getByTestId('reparto-texto').props.children).toBe('La parte de Carlos queda sin indicar. No cuenta como tuya ni como suya.');
    expect(screen.getByTestId('reparto-importe-carlos').props.value).toBe('');
    expect(plano()).toContain(colores.dark.background);
  });

  test('envío: doble toque = un POST; INDETERMINADO reintenta la MISMA identidad; rechazo libera la edición', async () => {
    let resolver: (x: any) => void = () => {};
    const registrar = jest.fn()
      .mockImplementationOnce(() => new Promise((r) => { resolver = r; }))
      .mockImplementationOnce(async () => ({ tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje: 'Esa cuenta no permite pagar gastos.' }));
    const c = cliente({ registrarGastoCompartido: registrar as any });
    envolver(<GastoCompartidoScreen cliente={c} nuevoId={nuevoId} base={BASE_PELU} inicial={{ repartir: false, otraPersona: false }} onVolver={jest.fn()} onCerrar={jest.fn()} />);
    fireEvent.press(await screen.findByTestId('compartido-cuenta-bbva'));
    fireEvent.press(screen.getByTestId('compartido-revisar'));
    fireEvent.press(await screen.findByTestId('registrar-compartido'));
    fireEvent.press(screen.getByTestId('registrar-compartido'));
    expect(registrar).toHaveBeenCalledTimes(1);
    await act(async () => resolver({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' }));
    fireEvent.press(await screen.findByTestId('compartido-reintentar'));
    await screen.findByTestId('compartido-error');
    expect(registrar.mock.calls[1][0].intencion_id).toBe(registrar.mock.calls[0][0].intencion_id);
    expect(screen.getByText(/Esa cuenta no permite pagar gastos\./)).toBeTruthy();
  });
});

// ================================================================== C · pendiente con
const PEND: PendienteConPersona = {
  tercero_id: 'tania', nombre: 'Tania', te_debe: '15.00', le_debes: '15.00', neto: '0.00', neto_estado: 'DETERMINADO',
  posiciones: [
    { entidad_id: 'd1', entidad_row_version: 1, tipo: 'DERECHO_COBRO', nombre: 'Gasto compartido', saldo: '15.00', estado: 'ACTIVA', origen_hecho_id: 'cena', origen_fecha: '2026-10-09', origen_concepto: 'Cena con amigos' },
    { entidad_id: 'o1', entidad_row_version: 1, tipo: 'OBLIGACION_PAGO', nombre: 'Gasto compartido', saldo: '15.00', estado: 'ACTIVA', origen_hecho_id: 'pelu', origen_fecha: '2026-10-03', origen_concepto: 'Peluquería', origen_tercero: 'Peluquería Lola' },
  ],
};
const resultadoPos = (pl: any, saldo: string | null = '5.00') =>
  ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: 'hx', entidad_id: 'd1', idempotente: false, importe: pl.importe, saldo, estado: saldo === '0.00' ? 'CERRADA' : 'ACTIVA', aviso: '' } }) as any;

function montarPendiente(c: ClienteApi, forzar?: 'dark') {
  return envolver(<PendienteConScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} terceroId="tania" nombre="Tania" onCerrar={jest.fn()} />, forzar);
}

describe('C · Pendiente con', () => {
  test('C1/D2: lo que te debe y lo que le debes por separado, con su origen; el neto no salda nada; sin «Compensar»', async () => {
    montarPendiente(cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: PEND }) as any) }), 'dark');
    expect(await screen.findByTestId('pendiente-lista-te-debe')).toBeTruthy();
    expect(within(screen.getByTestId('pendiente-lista-te-debe')).getByText('Cena con amigos')).toBeTruthy();
    expect(within(screen.getByTestId('pendiente-lista-le-debes')).getByText('Peluquería')).toBeTruthy();
    expect(within(screen.getByTestId('pendiente-lista-le-debes')).getByText('Peluquería Lola · 3 oct')).toBeTruthy();
    expect(screen.getByTestId('pendiente-neto').props.children).toMatch(/^Neto: 0,00 €\. Es un cálculo: no salda nada/);
    expect(plano()).not.toMatch(/Compensar/);
    expect(plano()).toContain(colores.dark.background);
  });

  test('C1: sin nota, el origen es el comercio del gasto', async () => {
    const p: PendienteConPersona = { ...PEND, posiciones: [{ ...PEND.posiciones[0], origen_concepto: null, origen_tercero: 'La Tagliatella' }] };
    montarPendiente(cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: p }) as any) }));
    expect(await screen.findByText('La Tagliatella')).toBeTruthy();
    expect(screen.queryByText('Gasto compartido')).toBeNull();
  });

  test('C4: con un saldo desconocido, «Sin determinar» y el neto sin determinar, nunca 0,00 €', async () => {
    const p: PendienteConPersona = { ...PEND, nombre: 'Carlos', te_debe: '40.00', le_debes: null, neto: null, neto_estado: 'INDETERMINADO',
      posiciones: [{ ...PEND.posiciones[1], saldo: null, origen_concepto: 'Préstamo viaje' }] };
    montarPendiente(cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: p }) as any) }));
    expect(await screen.findByTestId('pendiente-le-debes')).toBeTruthy();
    expect(screen.getByTestId('pendiente-le-debes').props.children).toBe('Sin determinar');
    expect(screen.getByTestId('pendiente-neto').props.children).toBe(TEXTO_NETO_SIN_DETERMINAR);
    expect(screen.getByText('Saldo inicial desconocido')).toBeTruthy();
  });

  test('C2/C3: cobro con cuenta obligatoria (las que reciben dinero), parcial permitido, sin superar lo pendiente', async () => {
    const cobrar = jest.fn(async (_: string, pl: any) => resultadoPos(pl));
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: PEND }) as any), cobrarPosicion: cobrar as any });
    montarPendiente(c);
    fireEvent.press(await screen.findByTestId('posicion-d1'));
    expect(screen.getByTestId('posicion-perdonar')).toBeTruthy();
    fireEvent.press(screen.getByTestId('posicion-cobrar'));
    await screen.findByTestId('accion-cobro');
    expect(c.cuentasElegibles).toHaveBeenCalledWith('INGRESO', HOY);
    expect(screen.getByTestId('accion-explicacion').props.children).toMatch(/^No es un ingreso/);
    expect(screen.getByTestId('accion-enviar').props.accessibilityState?.disabled).toBe(true); // sin cuenta
    fireEvent.changeText(screen.getByTestId('accion-importe'), '20');
    fireEvent.press(await screen.findByTestId('accion-cuenta-efectivo'));
    expect(screen.getByTestId('accion-faltan').props.children).toMatch(/no supere lo pendiente/);
    fireEvent.changeText(screen.getByTestId('accion-importe'), '10');
    fireEvent.press(screen.getByTestId('accion-enviar'));
    await screen.findByTestId('posicion-exito');
    expect(cobrar).toHaveBeenCalledWith('d1', expect.objectContaining({ importe: '10.00', cuenta_id: 'efectivo', fecha: HOY }));
    expect(screen.getByTestId('posicion-exito-saldo').props.children).toBe('Sigue pendiente: 5,00 €');
  });

  test('E8: pago de una obligación solo con tus cuentas, sin «Lo pagó otra persona»; INDETERMINADO reintenta la MISMA identidad', async () => {
    const pagar = jest.fn().mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' })
      .mockImplementationOnce(async (_: string, pl: any) => resultadoPos(pl, '0.00'));
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: PEND }) as any), pagarPosicion: pagar as any });
    montarPendiente(c);
    fireEvent.press(await screen.findByTestId('posicion-o1'));
    fireEvent.press(screen.getByTestId('posicion-pagar'));
    await screen.findByTestId('accion-pago');
    expect(c.cuentasElegibles).toHaveBeenCalledWith('GASTO', HOY);
    expect(screen.getByTestId('accion-sin-tercero').props.children).toBe(TEXTO_SIN_TERCERO_PAGA);
    expect(screen.getByTestId('accion-explicacion').props.children).toMatch(/^No es un gasto nuevo/);
    fireEvent.press(await screen.findByTestId('accion-cuenta-bbva'));
    fireEvent.press(screen.getByTestId('accion-enviar'));
    await screen.findByTestId('accion-indeterminado');
    fireEvent.press(screen.getByTestId('accion-enviar'));
    await screen.findByTestId('posicion-exito');
    expect(pagar.mock.calls[1][1].intencion_id).toBe(pagar.mock.calls[0][1].intencion_id);
    expect(screen.getByTestId('posicion-exito-saldo').props.children).toBe('Ya no queda nada pendiente.');
  });

  test('perdonar no pide cuenta ni mueve dinero', async () => {
    const perdonar = jest.fn(async (_: string, pl: any) => resultadoPos(pl));
    const c = cliente({ pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: PEND }) as any), perdonarPosicion: perdonar as any });
    montarPendiente(c);
    fireEvent.press(await screen.findByTestId('posicion-d1'));
    fireEvent.press(screen.getByTestId('posicion-perdonar'));
    await screen.findByTestId('accion-perdon');
    expect(screen.queryByTestId('accion-cuenta-bbva')).toBeNull();
    expect(screen.getByTestId('accion-explicacion').props.children).toMatch(/no mueve dinero/);
    fireEvent.press(screen.getByTestId('accion-enviar'));
    await screen.findByTestId('posicion-exito');
    expect(perdonar.mock.calls[0][1]).toEqual({ intencion_id: expect.any(String), importe: '15.00', fecha: HOY });
  });

  test('sin posiciones: «No tienes nada pendiente» y 0,00 €, no «Sin determinar»', async () => {
    montarPendiente(cliente());
    expect(await screen.findByTestId('pendiente-nada')).toBeTruthy();
    expect(screen.getByTestId('pendiente-le-debes').props.children).toBe('0,00 €');
  });
});

// ================================================================== E6 · corregir reparto
const REPARTO: RepartoDeHecho = {
  hecho_id: 'cena', row_version: 4, importe: '44.50', estado_atribucion: 'COMPLETA', corregible: true, motivo: null, partes: [
    { atribucion_id: 'a-yo', es_yo: true, tercero_id: null, nombre: 'Tú', importe: '14.50', posicion: null },
    { atribucion_id: 'a-tania', es_yo: false, tercero_id: 'tania', nombre: 'Tania', importe: '15.00', posicion: { entidad_id: 'd1', tipo: 'DERECHO_COBRO', saldo: '15.00' } },
    { atribucion_id: 'a-carlos', es_yo: false, tercero_id: 'carlos', nombre: 'Carlos', importe: '15.00', posicion: null },
  ],
};

function montarCorregir(c: ClienteApi, onCerrar = jest.fn()) {
  envolver(<CorregirRepartoScreen cliente={c} hechoId="cena" onCerrar={onCerrar} />);
  return onCerrar;
}

describe('E6 · Corregir reparto', () => {
  test('lo excluido por §57 se ve atenuado con su motivo; solo se editan importes', async () => {
    montarCorregir(cliente({ repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: REPARTO }) as any) }));
    await screen.findByTestId('corregir-form');
    for (const id of ['corregir-anadir', 'corregir-quitar-a-tania', 'corregir-quitar-a-carlos', 'corregir-deudor-a-invitado-a-tania', 'corregir-invitado-a-deudor-a-carlos', 'corregir-le-debo']) {
      expect(screen.getByTestId(id).props.accessibilityState).toEqual({ disabled: true });
      expect(screen.getByTestId(`${id}-motivo`).props.children).toMatch(/^(Todavía no|Si alguien|Para que)/);
    }
    expect(screen.queryByTestId('corregir-quitar-a-yo')).toBeNull();
    expect(screen.getByTestId('corregir-importe-a-yo').props.value).toBe('14,50');
  });

  test('revisión de impacto: parte a parte, deuda que cambia y tu gasto; motivo obligatorio; envía solo lo cambiado', async () => {
    const corregir = jest.fn(async () => ({ tipo: 'OK', datos: { hecho_id: 'cena', row_version: 5, tu_parte: '9.50', posiciones: [], aviso: '' } }) as any);
    const c = cliente({ repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: REPARTO }) as any), corregirReparto: corregir });
    const onCerrar = montarCorregir(c);
    await screen.findByTestId('corregir-form');
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-yo'), '9,50');
    expect(screen.getByTestId('corregir-faltan').props.children).toMatch(/sumen lo mismo que antes \(44,50 €\)/);
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-tania'), '20');
    fireEvent.press(screen.getByTestId('corregir-revisar'));
    await screen.findByTestId('corregir-revision');
    expect(screen.getByText('14,50 € → 9,50 €')).toBeTruthy();
    expect(screen.getByText('Lo que Tania te debe: 15,00 € → 20,00 €')).toBeTruthy();
    expect(within(screen.getByTestId('corregir-impacto-tu-gasto')).getByText('−5,00 €')).toBeTruthy();
    expect(screen.getByTestId('corregir-guardar').props.accessibilityState?.disabled).toBe(true);
    fireEvent.press(screen.getByTestId('corregir-motivo-0'));
    fireEvent.press(screen.getByTestId('corregir-guardar'));
    await screen.findByTestId('corregir-exito');
    expect(corregir).toHaveBeenCalledWith('cena', { row_version: 4, motivo: 'Me equivoqué al repartir',
      partes: [{ atribucion_id: 'a-yo', importe: '9.50' }, { atribucion_id: 'a-tania', importe: '20.00' }] });
    fireEvent.press(screen.getByTestId('corregir-hecho'));
    expect(onCerrar).toHaveBeenCalledWith(true);
  });

  test('rechazo en lenguaje llano; VERSION_DESFASADA recarga; INDETERMINADO pide volver a cargar, sin reintento', async () => {
    const leer = jest.fn(async () => ({ tipo: 'OK', datos: REPARTO }) as any);
    const corregir = jest.fn()
      .mockResolvedValueOnce({ tipo: 'RECHAZADO', codigo: 'CORRECCION_AGREGADA_REQUERIDA', mensaje: 'x', detalle: { motivo: 'REPARTO_CAMBIA_POSICIONES' } })
      .mockResolvedValueOnce({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'x' })
      .mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el cambio. Vuelve a cargar antes de repetirlo.' });
    montarCorregir(cliente({ repartoDeHecho: leer, corregirReparto: corregir as any }));
    await screen.findByTestId('corregir-form');
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-yo'), '9,50');
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-tania'), '20');
    fireEvent.press(screen.getByTestId('corregir-revisar'));
    fireEvent.press(await screen.findByTestId('corregir-motivo-1'));
    fireEvent.press(screen.getByTestId('corregir-guardar'));
    expect((await screen.findByTestId('corregir-error')).props.children).toBeTruthy();
    expect(plano()).toMatch(/todavía no se puede corregir aquí/);
    expect(plano()).not.toMatch(/CORRECCION_AGREGADA_REQUERIDA|REPARTO_CAMBIA_POSICIONES/);
    fireEvent.press(screen.getByTestId('corregir-guardar'));
    await waitFor(() => expect(leer).toHaveBeenCalledTimes(2));
    // tras recargar se vuelve a la edición con el aviso y se escribe de nuevo el cambio
    await screen.findByTestId('corregir-form');
    expect(await screen.findByTestId('corregir-recargado')).toBeTruthy();
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-yo'), '9,50');
    fireEvent.changeText(screen.getByTestId('corregir-importe-a-tania'), '20');
    fireEvent.press(screen.getByTestId('corregir-revisar'));
    fireEvent.press(await screen.findByTestId('corregir-motivo-1'));
    fireEvent.press(screen.getByTestId('corregir-guardar'));
    expect(await screen.findByTestId('corregir-recargar')).toBeTruthy();
    expect(screen.queryByTestId('corregir-guardar')).toBeNull();
    expect(corregir).toHaveBeenCalledTimes(3);
  });

  test('no corregible: se dice por qué y no se ofrece ninguna alternativa', async () => {
    montarCorregir(cliente({ repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: { ...REPARTO, corregible: false, motivo: 'ORIGEN_IMPORTADO' } }) as any) }));
    expect(await screen.findByTestId('corregir-no-corregible')).toBeTruthy();
    expect(plano()).toMatch(/versión anterior/);
    expect(screen.queryByTestId('corregir-form')).toBeNull();
    expect(plano()).not.toMatch(/[Aa]nular/);
  });
});

// ================================================================== integración
const CENA_FILA: FilaActividad = {
  id: 'cena', fecha_hecho: '2026-10-09', tipo: 'GASTO', nota: 'Cena con amigos', moneda: 'EUR', importe_total: '44.50',
  tercero: { id: 'tagliatella', nombre: 'La Tagliatella', enabled: true }, categoria: { id: 'rest', nombre: 'Restaurantes', ruta: 'Restaurantes', enabled: true }, varias: false,
  contexto: null, cuentas: [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '14.50',
  pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};

describe('integración', () => {
  function actividad(o: Partial<ClienteApi>) {
    return cliente({
      actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [CENA_FILA], siguiente: null, total: 1 } }) as any),
      detalleActividad: jest.fn(async () => ({ tipo: 'OK', datos: { ...CENA_FILA, presupuestable: true, magnitudes: [], devoluciones: null } as DetalleActividad }) as any),
      ...o,
    });
  }

  test('detalle de un gasto: «Pendiente con Tania» y «Corregir reparto» si el servidor lo considera corregible', async () => {
    const onCorregir = jest.fn();
    const onPendiente = jest.fn();
    envolver(<ActividadScreen cliente={actividad({ repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: REPARTO }) as any) })} ahora={AHORA} nuevoId={nuevoId}
      onCorregirReparto={onCorregir} onPendienteCon={onPendiente} />);
    fireEvent.press(await screen.findByTestId('fila-cena'));
    fireEvent.press(await screen.findByTestId('detalle-pendiente-tania'));
    expect(onPendiente).toHaveBeenCalledWith({ terceroId: 'tania', nombre: 'Tania' });
    fireEvent.press(await screen.findByTestId('fila-cena'));
    fireEvent.press(await screen.findByTestId('detalle-corregir-reparto'));
    expect(onCorregir).toHaveBeenCalledWith('cena');
  });

  test('detalle de un gasto no corregible: sin «Corregir reparto»', async () => {
    envolver(<ActividadScreen cliente={actividad({ repartoDeHecho: jest.fn(async () => ({ tipo: 'OK', datos: { ...REPARTO, corregible: false, motivo: 'SIN_REPARTO', partes: [] } }) as any) })}
      ahora={AHORA} nuevoId={nuevoId} onCorregirReparto={jest.fn()} onPendienteCon={jest.fn()} />);
    fireEvent.press(await screen.findByTestId('fila-cena'));
    await screen.findByTestId('detalle-contenido');
    await waitFor(() => expect(screen.queryByTestId('detalle-corregir-reparto')).toBeNull());
  });

  test('registro: «Repartir» y «Otra persona» solo en gastos y solo con lo común completo', async () => {
    const onCompartido = jest.fn();
    const c = cliente({
      cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: [] } }) as any),
      cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [] } }) as any),
    });
    const { unmount } = envolver(<RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onGastoCompartido={onCompartido} />);
    fireEvent.press(await screen.findByTestId('repartir'));
    expect(onCompartido).not.toHaveBeenCalled(); // falta importe, categoría y presupuesto
    expect(screen.getByTestId('otra-persona')).toBeTruthy();
    unmount();
    envolver(<RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} tipo="INGRESO" onGastoCompartido={onCompartido} />);
    await waitFor(() => expect(screen.queryByTestId('solo-mio')).toBeTruthy());
    expect(screen.queryByTestId('repartir')).toBeNull();
    expect(screen.queryByTestId('otra-persona')).toBeNull();
  });
});
