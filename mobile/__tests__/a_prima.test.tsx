// ============================================================
// GAPTO MOBILE 2027
// Fichero: a_prima.test.tsx
// Ruta: mobile/__tests__/a_prima.test.tsx
// Descripción: A′ (D-F0507L-07; lámina F05-07 v0.3 A′1/A′2; F05 §66.3): la magnitud justo después de la categoría. Al elegir una categoría con magnitud obligatoria, el foco se abre en la primera obligatoria sin valor ni «No lo sé»; «Hecho» (barra sobre el teclado en iOS, con VoiceOver «Hecho, siguiente campo», y tecla de envío en Android/web) pasa a la siguiente obligatoria y, tras la última, cierra el teclado y sube a «¿Cuenta para el presupuesto?», que sigue sin marcar igual que la cuenta (D-F0507L-02). Varias magnitudes, opcionales saltadas, «No lo sé», cambio de categoría (las comunes se conservan; las demás ni se ven ni se envían), cerrar el teclado sin perder el valor y alcance limitado a los campos de magnitud.
// Versión: 0.1.0 (F05-D052 paso 3 · A′)
// Versión: 0.2.0 (F06 T6 · S2 FORM-AGIL; F09 0.55 §12.107.1 puntos 1 y 2): los controles se buscan con `ver`/`verPronto` (form_agil.ts), que tocan antes la línea de «Se registrará así», «Más opciones» o «‹ Exprés» como haría el usuario. Mismas aserciones; las de ausencia siguen con queryByTestId. Punto 6: abrir el selector de Categoría cierra el teclado; `elegir` lo comprueba y pone a cero el contador antes de las aserciones de «Hecho».
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { Keyboard, ScrollView, TextInput } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { primeraMagnitudPendiente, siguienteMagnitud } from '../src/domain/magnitud';
import { ETIQUETA_HECHO } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, mag, nodo } from './fixtures_categorias';
import { actVer, ver, verPronto } from './form_agil';

const TARJETA = 'c0000000-0000-4000-8000-000000000001';
const EFECTIVO = 'c0000000-0000-4000-8000-000000000002';
const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);

// Movilidad › Combustible (Litros); Gasóleo (Litros y Kilómetros, obligatorias, y Peaje opcional en medio);
// Viaje (Kilómetros, Noches y Litros, obligatorias); Taller (solo opcional).
const LITROS = mag({ magnitud_id: 'litros', nombre: 'Litros', unidad_default: 'l', precision_decimales: 2 });
const KM = mag({ magnitud_id: 'km', nombre: 'Kilómetros', unidad_default: 'km', precision_decimales: 0 });
const PEAJE = mag({ magnitud_id: 'peaje', nombre: 'Peajes', obligatoria: false, unidad_default: 'u', precision_decimales: 0 });
const NOCHES = mag({ magnitud_id: 'noches', nombre: 'Noches', unidad_default: 'u', precision_decimales: 0 });
const ARBOL: CategoriaNodo[] = [
  nodo({ id: 'mov', nombre: 'Movilidad' }),
  nodo({ id: 'comb', nombre: 'Combustible', parent_id: 'mov', magnitudes: [LITROS] }),
  nodo({ id: 'gasoleo', nombre: 'Gasóleo', parent_id: 'mov', orden: 1, magnitudes: [{ ...KM, orden: 0 }, { ...PEAJE, orden: 1 }, { ...LITROS, orden: 2 }] }),
  nodo({ id: 'viaje', nombre: 'Viaje', parent_id: 'mov', orden: 2, magnitudes: [KM, NOCHES, LITROS] }),
  nodo({ id: 'taller', nombre: 'Taller', parent_id: 'mov', orden: 3, magnitudes: [PEAJE] }),
];

function fake() {
  const enviados: PayloadGastoPagado[] = [];
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: PayloadGastoPagado) => {
      enviados.push(p);
      return { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'NO_DISPONIBLE', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado } } as Respuesta<ResultadoRegistro>;
    }),
    // Dos cuentas y ninguna preferencia: presupuesto y cuenta sin marcar (D-F0507L-02).
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [
      { cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
      { cuenta_id: EFECTIVO, nombre: 'Efectivo', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
    ] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  };
  return { cliente, enviados };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const proto = TextInput.prototype as unknown as { focus: jest.Mock; blur: jest.Mock };
/** testID de cada campo que recibió `focus()` (o `blur()`), en orden. */
const enfocados = () => proto.focus.mock.contexts.map((x: any) => x.props.testID);
const desenfocados = () => proto.blur.mock.contexts.map((x: any) => x.props.testID);

async function abrir(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(await verPronto('accion-registrar'));
  fireEvent.press(ver('tipo-GASTO'));
  await verPronto(`cuenta-${TARJETA}`);
}

async function elegir(id: string) {
  const antes = dismiss.mock.calls.length;
  fireEvent.press(ver('campo-categoria'));
  // F06 T6 · S2 (F09 0.55 §12.107.1 punto 6): abrir el selector de Categoría ya cierra el teclado del campo anterior.
  expect(dismiss.mock.calls.length).toBe(antes + 1);
  fireEvent.press(ver('cat-mov'));
  await actVer(`cat-${id}`, async () => fireEvent.press(ver(`cat-${id}`)));
  // Desde aquí se cuentan solo los cierres de teclado del formulario de magnitudes («Hecho» y tecla de envío).
  dismiss.mockClear();
}

const hecho = async () => actVer('magnitud-hecho', async () => fireEvent.press(ver('magnitud-hecho')));
const enfocar = (id: string) => fireEvent(ver(`magnitud-${id}`), 'focus');
const seleccionado = (id: string) => ver(id).props.accessibilityState?.selected;
const marcada = (id: string) => ver(id).props.accessibilityState?.checked;

let dismiss: jest.SpyInstance;
beforeEach(() => {
  n = 0;
  proto.focus.mockClear();
  proto.blur.mockClear();
  dismiss = jest.spyOn(Keyboard, 'dismiss');
});
afterEach(() => dismiss.mockRestore());

describe('A′ · dominio', () => {
  test('primera pendiente: obligatoria sin valor ni «No lo sé», en el orden del formulario; opcionales nunca', () => {
    expect(primeraMagnitudPendiente([PEAJE, KM, LITROS], {})).toBe('km');
    expect(primeraMagnitudPendiente([KM, LITROS], { km: '120' })).toBe('litros');
    expect(primeraMagnitudPendiente([KM, LITROS], { km: '  ' })).toBe('km');
    expect(primeraMagnitudPendiente([KM, LITROS], {}, ['km'])).toBe('litros');
    expect(primeraMagnitudPendiente([KM, LITROS], { km: '1', litros: '2' })).toBeNull();
    expect(primeraMagnitudPendiente([PEAJE], {})).toBeNull();
  });
  test('siguiente: la próxima obligatoria sin «No lo sé»; sin ella, null (presupuesto)', () => {
    expect(siguienteMagnitud([KM, PEAJE, LITROS], 'km')).toBe('litros');
    expect(siguienteMagnitud([KM, NOCHES, LITROS], 'km', ['noches'])).toBe('litros');
    expect(siguienteMagnitud([KM, LITROS], 'litros')).toBeNull();
    expect(siguienteMagnitud([KM, PEAJE], 'km')).toBeNull();
    expect(siguienteMagnitud([KM, PEAJE, LITROS], 'peaje')).toBe('litros');
  });
});

describe('A′ · formulario', () => {
  test('A′1/A′2: Combustible abre el teclado en Litros; «Hecho» cierra el teclado y sube a presupuesto, que sigue sin marcar como la cuenta', async () => {
    const f = fake();
    await abrir(f.cliente);
    fireEvent.changeText(ver('campo-importe'), '60');
    await elegir('comb');
    expect(enfocados()).toEqual(['magnitud-litros']);
    // Litros va justo debajo de la categoría: el orden del formulario coincide con el orden en que se pide.
    expect(ver('datos-categoria')).toBeTruthy();
    expect(ver('magnitud-litros').props.returnKeyType).toBe('done');
    expect(ver('magnitud-litros').props.returnKeyLabel).toBe('Hecho');
    enfocar('litros');
    fireEvent.changeText(ver('magnitud-litros'), '41,5');
    // y del bloque de presupuesto para el desplazamiento.
    fireEvent(ver('bloque-presupuestable'), 'layout', { nativeEvent: { layout: { x: 0, y: 640, width: 361, height: 90 } } });
    const scrollTo = (ScrollView.prototype as unknown as { scrollTo: jest.Mock }).scrollTo;
    scrollTo.mockClear();
    await hecho();
    expect(desenfocados()).toEqual(['magnitud-litros']);
    expect(dismiss).toHaveBeenCalledTimes(1);
    expect(enfocados()).toEqual(['magnitud-litros']); // no salta a ningún otro campo
    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo.mock.calls[0][0]).toMatchObject({ y: 640 - 16 }); // sube hasta «¿Cuenta para el presupuesto?»
    // D-F0507L-02: nada se rellena para ganar tiempo.
    expect(seleccionado('presupuestable-true')).toBe(false);
    expect(seleccionado('presupuestable-false')).toBe(false);
    expect(marcada(`cuenta-${TARJETA}`)).toBe(false);
    expect(marcada(`cuenta-${EFECTIVO}`)).toBe(false);
    expect(ver('registrar')).toBeDisabled();
    // El valor se conserva tras cerrar el teclado.
    expect(ver('magnitud-litros').props.value).toBe('41,5');
  });

  test('«Hecho» es accesible: botón con la etiqueta «Hecho, siguiente campo»', async () => {
    await abrir(fake().cliente);
    await elegir('comb');
    const b = screen.getByLabelText(ETIQUETA_HECHO);
    expect(ETIQUETA_HECHO).toBe('Hecho, siguiente campo');
    expect(b.props.accessibilityRole).toBe('button');
    expect(screen.getByText('Hecho')).toBeTruthy();
  });

  test('varias magnitudes: «Hecho» pasa a la siguiente obligatoria (salta la opcional) y después a presupuesto', async () => {
    await abrir(fake().cliente);
    await elegir('gasoleo');
    expect(enfocados()).toEqual(['magnitud-km']);
    expect(ver('magnitud-km').props.returnKeyType).toBe('next');
    expect(ver('magnitud-peaje').props.returnKeyType).toBe('next');
    expect(ver('magnitud-litros').props.returnKeyType).toBe('done');
    enfocar('km');
    fireEvent.changeText(ver('magnitud-km'), '300');
    await hecho();
    expect(enfocados()).toEqual(['magnitud-km', 'magnitud-litros']);
    enfocar('litros');
    fireEvent.changeText(ver('magnitud-litros'), '41,5');
    await hecho();
    expect(desenfocados()).toEqual(['magnitud-litros']);
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  test('Android/web: la tecla de envío del teclado hace lo mismo que «Hecho»', async () => {
    await abrir(fake().cliente);
    await elegir('viaje');
    expect(enfocados()).toEqual(['magnitud-km']);
    await act(async () => fireEvent(ver('magnitud-km'), 'submitEditing'));
    await act(async () => fireEvent(ver('magnitud-noches'), 'submitEditing'));
    expect(enfocados()).toEqual(['magnitud-km', 'magnitud-noches', 'magnitud-litros']);
    await act(async () => fireEvent(ver('magnitud-litros'), 'submitEditing'));
    expect(desenfocados()).toEqual(['magnitud-litros']);
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  test('«No lo sé» se mantiene: una obligatoria marcada se salta con «Hecho» y no bloquea', async () => {
    const f = fake();
    await abrir(f.cliente);
    await elegir('viaje');
    fireEvent.press(ver('no-lo-se-noches'));
    expect(ver('no-lo-se-texto-noches')).toBeTruthy();
    enfocar('km');
    await hecho();
    expect(enfocados()).toEqual(['magnitud-km', 'magnitud-litros']);
    expect(ver('magnitud-litros').props.returnKeyType).toBe('done');
  });

  test('cambio de categoría: la común se conserva y el teclado va a la primera que falta; las que no aplican desaparecen y no se envían', async () => {
    const f = fake();
    await abrir(f.cliente);
    fireEvent.changeText(ver('campo-importe'), '60');
    await elegir('gasoleo');
    fireEvent.changeText(ver('magnitud-km'), '300');
    fireEvent.changeText(ver('magnitud-litros'), '41,5');
    proto.focus.mockClear();
    // Gasóleo → Viaje: km y litros se conservan; el teclado va a Noches (la que falta).
    await elegir('viaje');
    expect(ver('magnitud-km').props.value).toBe('300');
    expect(ver('magnitud-litros').props.value).toBe('41,5');
    expect(screen.queryByTestId('magnitud-peaje')).toBeNull();
    expect(enfocados()).toEqual(['magnitud-noches']);
    proto.focus.mockClear();
    // Viaje → Combustible: se confirma descartar km; tras confirmar, solo queda Litros (ya informada: sin teclado).
    await elegir('comb');
    expect(ver('confirmar-descarte')).toBeTruthy();
    await actVer('descarte-confirmar', async () => fireEvent.press(ver('descarte-confirmar')));
    expect(screen.queryByTestId('magnitud-km')).toBeNull();
    expect(ver('magnitud-litros').props.value).toBe('41,5');
    expect(enfocados()).toEqual([]);
    fireEvent.press(ver('presupuestable-false'));
    fireEvent.press(ver(`cuenta-${TARJETA}`));
    await actVer('registrar', async () => fireEvent.press(ver('registrar')));
    await verPronto('registro-exito');
    expect(f.enviados[0].categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'comb', magnitudes: [{ magnitud_id: 'litros', valor: '41.5' }] });
  });

  test('cerrar el teclado tocando fuera conserva el valor', async () => {
    const f = fake();
    await abrir(f.cliente);
    fireEvent.changeText(ver('campo-importe'), '60');
    await elegir('comb');
    enfocar('litros');
    fireEvent.changeText(ver('magnitud-litros'), '41,5');
    fireEvent(ver('magnitud-litros'), 'blur');
    await act(async () => Keyboard.dismiss());
    fireEvent.press(ver('presupuestable-true'));
    expect(ver('magnitud-litros').props.value).toBe('41,5');
    fireEvent.press(ver(`cuenta-${EFECTIVO}`));
    await actVer('registrar', async () => fireEvent.press(ver('registrar')));
    await verPronto('registro-exito');
    expect(f.enviados[0].categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'comb', magnitudes: [{ magnitud_id: 'litros', valor: '41.5' }] });
  });

  test('alcance: solo opcionales no abren el teclado y ningún otro campo lleva «Hecho»', async () => {
    await abrir(fake().cliente);
    await elegir('taller');
    expect(enfocados()).toEqual([]);
    expect(ver('campo-importe').props.returnKeyType).toBeUndefined();
    expect(ver('campo-importe').props.inputAccessoryViewID).toBeUndefined();
    expect(ver('campo-importe').props.onSubmitEditing).toBeUndefined();
    expect(ver('magnitud-peaje').props.returnKeyType).toBe('done');
  });

  test('sin magnitudes no hay barra «Hecho»', async () => {
    await abrir(fake().cliente);
    expect(screen.queryByTestId('magnitud-hecho')).toBeNull();
    fireEvent.press(ver('campo-categoria'));
    fireEvent.press(ver('cat-mov'));
    await actVer('selector-usar', async () => fireEvent.press(ver('selector-usar')));
    expect(screen.queryByTestId('magnitud-hecho')).toBeNull();
    expect(enfocados()).toEqual([]);
  });
});
