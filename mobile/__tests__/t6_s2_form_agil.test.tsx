// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s2_form_agil.test.tsx
// Ruta: mobile/__tests__/t6_s2_form_agil.test.tsx
// Descripción: F06 T6 «UX ágil» · S2 (F09 0.55 §12.107.1; lámina REG-AGIL v0.8 «Gasto 1–4», «Ingreso 1–3», «Vivienda 1–5»):
//   - exprés: importe, tercero y categoría; «Se registrará así» con líneas tocables; lo obligatorio sin valor (presupuesto,
//     cuenta) se abre en el exprés y no desaparece al elegirlo; «Registrar» siempre visible con «Falta: …» (visible no es
//     habilitado, A7) y «Más opciones»;
//   - «Más opciones»: «‹ Exprés», resumen tocable, bloques numerados con «Continuar» al siguiente y «Registrar»;
//   - una línea tocada abre su bloque; el teclado se cierra (FA-04);
//   - presupuesto obligatorio sin valor por defecto en el doble sin la lectura de S4; «¿Qué tipo de gasto es?» retirada en S6;
//   - vivienda: «Revisar» por persona (parte, aportación real y posición), presupuesto y lo que sale de tus cuentas;
//     la huella cambia si cambian fecha, titularidad, reparto, quién pagó, deudas o cuenta (A6).
// Versión: 0.1.0 (F06 T6 · S2)
// Versión: 0.2.0 (F06 T6 · S6): «¿Qué tipo de gasto es?» retirada; se comprueba su ausencia.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { Keyboard } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { ClientePropiedades } from '../src/api/propiedades';
import { huellaRevision, TEXTO_REVISAR_PIE } from '../src/components/RevisarVivienda';
import type { CategoriaNodo } from '../src/domain/categoria';
import { conDeudas, conPropuesta, seleccionInicial } from '../src/domain/propiedad_registro';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);
const HOY = '2026-10-26';
const C1 = 'c0000000-0000-4000-8000-000000000001';
const CONJ = 'c0000000-0000-4000-8000-000000000002';
const YO = 'f0000000-0000-4000-8000-0000000000ff';
const LUCIA = 'a0000000-0000-4000-8000-0000000000a1';
const P1 = 'p0000000-0000-4000-8000-000000000001';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };

const ARBOL: CategoriaNodo[] = [
  nodo({ id: 'hogar', nombre: 'Hogar' }),
  nodo({ id: 'comunidad', nombre: 'Comunidad', parent_id: 'hogar', asociada_vivienda: true }),
  nodo({ id: 'ocio', nombre: 'Ocio', orden: 1, asociada_vivienda: false }),
];
const CUENTAS: CuentaPago[] = [
  { cuenta_id: C1, nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
  { cuenta_id: CONJ, nombre: 'Cuenta conjunta', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' },
];
const compartida = (fecha = HOY): PropuestaGasto => ({
  fecha, propiedad_id: P1, nombre: 'Piso Centro', titularidad_disponible: true,
  partes: [
    { actor_id: LUCIA, porcentaje: '50.0000', yo: false, tercero_id: 't-lucia', nombre: 'Lucía', naturaleza: 'PERSONA' },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: null,
});
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });

function cliente(): ClienteApi {
  return {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: any) => ok({ intencion_id: p.intencion_id, hecho_id: p.intencion_id, idempotente: false, importe: p.importe, moneda: 'EUR',
      estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado })) as any,
    cuentasPago: jest.fn(async () => ok({ cuentas: CUENTAS })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  } as unknown as ClienteApi;
}
const propiedades = () => ({ listarPropiedades: jest.fn(async () => ok({ propiedades: [
  { id: P1, nombre: 'Piso Centro', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', modo_titularidad: 'COMPARTIDA', valor_estimado: null }] })) }) as unknown as ClientePropiedades;
const patrimonio = () => ({ propuestaGasto: jest.fn(async (_id: string, fecha: string) => ok(compartida(fecha))) }) as unknown as ClientePatrimonioB3;

function montar(c: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onGastoCompartido={jest.fn()}
          propiedades={propiedades()} patrimonio={patrimonio()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const texto = (id: string) => screen.getByTestId(id).props.children;
async function categoria(ruta: string[]) {
  await pulsar('campo-categoria');
  for (const id of ruta) await pulsar(`cat-${id}`);
}

test('exprés vacío: 1–3 arriba, «Se registrará así», lo obligatorio sin valor abierto, «Registrar» visible con «Falta» y «Más opciones»', async () => {
  montar(cliente());
  await screen.findByTestId(`cuenta-${C1}`);
  for (const id of ['campo-importe', 'campo-tercero', 'campo-categoria', 'se-registrara', 'registrar', 'mas-opciones']) expect(screen.getByTestId(id)).toBeTruthy();
  // Presupuesto y cuenta: obligatorios sin valor, abiertos en el exprés (sin «Sí» por defecto: S4 no entra).
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState?.selected).toBeFalsy();
  expect(screen.getByTestId('presupuestable-false').props.accessibilityState?.selected).toBeFalsy();
  expect(screen.queryByTestId('linea-presupuesto')).toBeNull();
  expect(screen.queryByTestId('linea-cuenta')).toBeNull();
  // Lo opcional o con valor, como línea tocable.
  expect(texto('linea-quien-valor')).toBe('Sin indicar');
  expect(texto('linea-fecha-valor')).toBe('Hoy');
  for (const id of ['solo-mio', 'fecha-ayer', 'campo-nota', 'abrir-mas-detalles']) expect(screen.queryByTestId(id)).toBeNull();
  // «Registrar» siempre visible; visible no es habilitado (A7).
  expect(screen.getByTestId('registrar').props.accessibilityState?.disabled).toBe(true);
  expect(texto('faltan')).toMatch(/^Para registrar falta: /);
  expect(screen.queryByTestId('volver-expres')).toBeNull();
  expect(screen.getByTestId('cancelar')).toBeTruthy();
});

test('lo elegido en el exprés se queda abierto (no desaparece bajo el dedo)', async () => {
  montar(cliente());
  await screen.findByTestId(`cuenta-${C1}`);
  await pulsar('presupuestable-true');
  await pulsar(`cuenta-${C1}`);
  // No desaparece bajo el dedo: se puede corregir ahí mismo.
  expect(screen.getByTestId('presupuestable-false')).toBeTruthy();
  await pulsar(`cuenta-${CONJ}`);
  expect(!!(screen.getByTestId(`cuenta-${CONJ}`).props.accessibilityState?.checked || screen.getByTestId(`cuenta-${CONJ}`).props.accessibilityState?.selected)).toBe(true);
  expect(screen.queryByTestId('linea-cuenta')).toBeNull();
});

test('una línea tocada abre «Más opciones» en su bloque y cierra el teclado (FA-04); el resumen vuelve al exprés', async () => {
  montar(cliente());
  await screen.findByTestId(`cuenta-${C1}`);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '23,40');
  await categoria(['ocio']);
  const teclado = jest.spyOn(Keyboard, 'dismiss');
  await pulsar('linea-fecha');
  expect(teclado).toHaveBeenCalled();
  teclado.mockRestore();
  expect(screen.getByTestId('volver-expres')).toBeTruthy();
  expect(screen.queryByTestId('cancelar')).toBeNull();
  expect(screen.queryByTestId('campo-importe')).toBeNull();
  expect(texto('resumen-expres-importe')).toBe('23,40 €');
  expect(texto('resumen-expres-categoria')).toBe('Ocio');
  // Bloques numerados en el orden de la lámina, con «Continuar» salvo el último.
  const bloques = ['presupuesto', 'quien', 'cuenta', 'fecha', 'detalles'];
  for (const [i, b] of bloques.entries()) {
    expect(screen.getByTestId(`bloque-${b}`)).toBeTruthy();
    if (i < bloques.length - 1) expect(screen.getByTestId(`bloque-${b}-continuar`)).toBeTruthy();
    else expect(screen.queryByTestId(`bloque-${b}-continuar`)).toBeNull();
  }
  for (const id of ['presupuestable-true', 'solo-mio', 'repartir', 'reembolsable', `cuenta-${C1}`, 'fecha-ayer', 'abrir-mas-detalles', 'registrar']) {
    expect(screen.getByTestId(id)).toBeTruthy();
  }
  await pulsar('bloque-presupuesto-continuar');
  await pulsar('fecha-ayer');
  await pulsar('resumen-expres');
  expect(screen.getByTestId('campo-importe')).toBeTruthy();
  expect(texto('linea-fecha-valor')).toBe('Ayer');
  await pulsar('mas-opciones');
  await pulsar('volver-expres');
  expect(screen.getByTestId('cancelar')).toBeTruthy();
});

test('«¿De quién?» desde su línea; el valor elegido se ve en el exprés', async () => {
  montar(cliente());
  await screen.findByTestId(`cuenta-${C1}`);
  await pulsar('linea-quien');
  await pulsar('solo-mio');
  await pulsar('volver-expres');
  expect(texto('linea-quien-valor')).toBe('Solo mío');
});

test('vivienda: propiedad en el exprés; «Registrar» abre «Revisar» por persona; «‹ Volver» no registra; confirmar registra', async () => {
  const c = cliente();
  montar(c);
  await screen.findByTestId(`cuenta-${C1}`);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '180');
  await categoria(['hogar', 'comunidad']);
  await pulsar('presupuestable-true');
  await pulsar(`vivienda-prop-${P1}`);
  await screen.findByTestId('vivienda-titularidad');
  // S6 (DF-14): «¿Qué tipo de gasto es?» ya no se muestra.
  expect(screen.queryByTestId('vivienda-clase-GASTO_CORRIENTE')).toBeNull();
  expect(screen.queryByTestId('linea-quien')).toBeNull();
  await pulsar('vivienda-quien-yo');
  await pulsar(`cuenta-${C1}`);
  await pulsar('registrar');
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(screen.getByTestId('revisar-vivienda')).toBeTruthy();
  expect(texto('revisar-persona-' + YO + '-valor')).toBe('Parte 90,00 €');
  expect(screen.getByTestId(`revisar-persona-${YO}`).props.accessibilityLabel).toContain('Tú');
  expect(texto(`revisar-persona-${LUCIA}-valor`)).toBe('Parte 90,00 €');
  expect(texto('revisar-sale-valor')).toBe('180,00 €');
  expect(texto('revisar-presupuesto-valor')).toBe('Sí');
  expect(texto('revisar-pie')).toBe(TEXTO_REVISAR_PIE);
  const filas = JSON.stringify(screen.toJSON());
  expect(filas).toContain('Puso 180,00 € desde Cuenta nómina · Lucía te debe 90,00 €');
  expect(filas).toContain('Puso 0,00 € · Lucía te debe 90,00 €');
  await pulsar('revisar-volver');
  expect(screen.queryByTestId('revisar-vivienda')).toBeNull();
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  // Una fila de la revisión vuelve a su bloque.
  await pulsar('registrar');
  await pulsar('revisar-fecha');
  expect(screen.getByTestId('bloque-fecha')).toBeTruthy();
  await pulsar('registrar');
  await pulsar('revisar-confirmar');
  await screen.findByTestId('registro-exito');
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
});

test('A6: la huella de la revisión cambia con la fecha, la titularidad, el reparto, quién pagó, las deudas o la cuenta', () => {
  const base = conDeudas({ ...conPropuesta(seleccionInicial(P1, 'Piso Centro'), compartida()), pago: { modo: 'YO_TODO', pagadorId: null, mio: '', suyo: '' } }, '180');
  const h = (s = base, fecha = HOY, cuenta: string | null = C1, importe = '180') => huellaRevision(s, importe, cuenta, fecha, true);
  const ref = h();
  expect(h()).toBe(ref);
  expect(h(base, '2026-10-25')).not.toBe(ref);
  expect(h(base, HOY, CONJ)).not.toBe(ref);
  expect(h(base, HOY, C1, '200')).not.toBe(ref);
  expect(h(conPropuesta(base, { ...compartida(), partes: compartida().partes.map((x) => ({ ...x, porcentaje: x.yo ? '60.0000' : '40.0000' })) }))).not.toBe(ref);
  expect(h({ ...base, reparto: { modo: 'NO_LO_SE' } as never })).not.toBe(ref);
  expect(h({ ...base, pago: { modo: 'CADA_UNO', pagadorId: null, mio: '', suyo: '' } })).not.toBe(ref);
  expect(h({ ...base, deudas: { [LUCIA]: { marcada: false, importe: '90.00' } }, deudasTocadas: true })).not.toBe(ref);
});
