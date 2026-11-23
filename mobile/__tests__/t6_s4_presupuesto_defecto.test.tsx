// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s4_presupuesto_defecto.test.tsx
// Ruta: mobile/__tests__/t6_s4_presupuesto_defecto.test.tsx
// Descripción: F06 T6 · S4 (N1; dictamen 1 Q1/A2; DF-04/06/12; F09 0.55 §12.107.3) en el cliente:
//   - sin preferencia, el presupuesto llega del servidor con su origen visible («Por defecto» o «De la categoría») y editable;
//   - un false de la categoría se muestra como No (nunca «Sí»);
//   - nunca pisa lo que el usuario ya eligió (valor explícito) ni una preferencia ya aplicada;
//   - el valor propuesto se sella como cualquier valor visible (payload con `presupuestable` explícito);
//   - sin la lectura nueva (dobles antiguos) el comportamiento es el de antes.
// Versión: 0.1.0 (F06 T6 · S4)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, PresupuestoPropuesto, Respuesta } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import { TEXTO_POR_DEFECTO } from '../src/domain/preferencias';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);
const C1 = 'c0000000-0000-4000-8000-000000000001';
const C2 = 'c0000000-0000-4000-8000-000000000002';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const ARBOL: CategoriaNodo[] = [nodo({ id: 'ocio', nombre: 'Ocio' }), nodo({ id: 'inversion', nombre: 'Inversión', orden: 1, presupuestable_default: false })];
const CUENTAS: CuentaPago[] = [
  { cuenta_id: C1, nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
  { cuenta_id: C2, nombre: 'Cuenta común', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' },
];
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });

/** Servidor de S4: sin preferencia; la categoría «Inversión» dice No; el resto, «Sí» por defecto. */
const servidorS4 = jest.fn(async (q: { categoriaId?: string | null }) =>
  ok<PresupuestoPropuesto>(q.categoriaId === 'inversion' ? { valor: false, origen: 'CATEGORIA' } : q.categoriaId === 'ocio'
    ? { valor: true, origen: 'CATEGORIA' } : { valor: true, origen: 'POR_DEFECTO' }));

function cliente(conS4 = true): ClienteApi {
  return {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: any) => ok({ intencion_id: p.intencion_id, hecho_id: p.intencion_id, idempotente: false, importe: p.importe, moneda: 'EUR',
      estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado })) as any,
    cuentasPago: jest.fn(async () => ok({ cuentas: CUENTAS })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    ...(conS4 ? { presupuestoPropuesto: servidorS4 } : {}),
  } as unknown as ClienteApi;
}
function montar(c: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const texto = (id: string) => screen.getByTestId(id).props.children;
async function categoria(id: string) {
  await pulsar('campo-categoria');
  await pulsar(`cat-${id}`);
}

test('sin preferencia ni categoría: «Sí» por defecto, visible como línea con su origen y editable', async () => {
  montar(cliente());
  await screen.findByTestId('linea-presupuesto');
  expect(texto('linea-presupuesto-valor')).toBe('Sí');
  expect(texto('linea-presupuesto-nota')).toBe(TEXTO_POR_DEFECTO);
  expect(servidorS4).toHaveBeenLastCalledWith(expect.objectContaining({ tipo: 'GASTO', sinCategoria: true }));
  // Editable: desde la línea se cambia a No y pasa a ser decisión tuya.
  await pulsar('linea-presupuesto');
  await pulsar('presupuestable-false');
  await pulsar('volver-expres');
  expect(texto('linea-presupuesto-valor')).toBe('No');
});

test('categoría con No: se propone No (nunca «Sí»), con el origen de la categoría', async () => {
  montar(cliente());
  await screen.findByTestId('linea-presupuesto');
  await categoria('inversion');
  await screen.findByText(/lo indica la categoría Inversión/);
  expect(texto('linea-presupuesto-valor')).toBe('No');
});

test('lo que elige el usuario no se pisa al cambiar de categoría', async () => {
  montar(cliente());
  await screen.findByTestId('linea-presupuesto');
  await pulsar('linea-presupuesto');
  await pulsar('presupuestable-false');
  await pulsar('volver-expres');
  await categoria('ocio');                                                        // la categoría diría «Sí»
  expect(texto('linea-presupuesto-valor')).toBe('No');
});

test('el valor propuesto se sella explícito en el payload', async () => {
  const c = cliente();
  montar(c);
  await screen.findByTestId('linea-presupuesto');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '12,00');
  await categoria('ocio');
  await screen.findByText(/lo indica la categoría Ocio/);
  await pulsar(`cuenta-${C1}`);
  await pulsar('registrar');
  await screen.findByTestId('registro-exito');
  expect((c.registrarGastoPagado as jest.Mock).mock.calls[0][0].presupuestable).toBe(true);
});

test('sin la lectura nueva (doble antiguo), el presupuesto sigue sin valor y obligatorio, como antes', async () => {
  montar(cliente(false));
  await screen.findByTestId(`cuenta-${C1}`);
  expect(screen.queryByTestId('linea-presupuesto')).toBeNull();
  expect(screen.getByTestId('presupuestable-true')).toBeTruthy();
});
