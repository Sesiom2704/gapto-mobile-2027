// ============================================================
// GAPTO MOBILE 2027
// Fichero: accion_rapida_ajustes.test.tsx
// Ruta: mobile/__tests__/accion_rapida_ajustes.test.tsx
// Descripción: `useAccionRapida` tras COLA-AR (F05 §70.A.1): solo la usan las acciones NO financieras de Ajustes (N1–N3: desactivar categoría, plantilla y tercero), que CONSERVAN su comportamiento de M5 SWIPE: espera de 5 s y «Deshacer» sin tocar el servidor; doble gesto → una intención; INDETERMINADO → «No sabemos si se guardó» y «Reintentar», y un gesto nuevo reutiliza la identidad; segundo plano o desmontaje durante la espera → no se envía nada. Son los discriminantes de MS01–MS08 de `mutantes_f05_06_m5_swipe.py` (antes los daban las pantallas financieras, que ya van por la cola).
// Versión: 0.1.0 (F05-D056 paso 2)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Tercero } from '../src/api/cliente';
import { ESPERA_DESHACER_MS } from '../src/components/AccionRapida';
import { TercerosAjustesScreen } from '../src/screens/TercerosAjustesScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const ok = (datos: unknown) => ({ tipo: 'OK', datos }) as any;
const SIMON: Tercero = { id: 'simon', nombre: 'Simón Valenzuela', naturaleza: 'PERSONA', enabled: true, row_version: 3 };

function cliente(desactivar: jest.Mock = jest.fn(async () => ok({ tercero: { ...SIMON, enabled: false, row_version: 4 } }))) {
  return { ...clienteCategoriasStub(), listarTerceros: jest.fn(async () => ok({ terceros: [SIMON] })), desactivarTercero: desactivar } as unknown as ClienteApi;
}
function montar(c: ClienteApi) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>
        <TercerosAjustesScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} onInmersiva={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
function llamadas(c: ClienteApi): number {
  return Object.values(c).reduce((t, f) => t + ((f as jest.Mock)?.mock?.calls?.length ?? 0), 0);
}
const esperar = async (ms: number) => {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
};
const asentar = async () => {
  for (let i = 0; i < 10; i++) await act(async () => undefined);
};
const accion = (testID: string, nombre: string) => fireEvent(screen.getByTestId(testID), 'accessibilityAction', { nativeEvent: { actionName: nombre } });

beforeEach(() => {
  n = 0;
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

describe('N1–N3 (Ajustes): useAccionRapida sin cambios', () => {
  test('«Deshacer» → 0 peticiones; sin deshacer, la petición sale a los 5 s y nunca antes', async () => {
    const c = cliente();
    montar(c);
    await asentar();
    const antes = llamadas(c);
    accion('ajter-fila-simon', 'derecha');
    await esperar(1000);
    fireEvent.press(screen.getByTestId('aviso-rapida-simon-deshacer'));
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(llamadas(c)).toBe(antes);
    accion('ajter-fila-simon', 'derecha');
    await esperar(ESPERA_DESHACER_MS - 1);
    expect(c.desactivarTercero).not.toHaveBeenCalled();
    await esperar(1);
    await asentar();
    expect(c.desactivarTercero).toHaveBeenCalledTimes(1);
  });

  test('doble gesto → una sola intención y una sola petición', async () => {
    const c = cliente();
    montar(c);
    await asentar();
    const h = screen.getByTestId('ajter-fila-simon').props.onAccessibilityAction;
    act(() => {
      h({ nativeEvent: { actionName: 'derecha' } });
      h({ nativeEvent: { actionName: 'derecha' } });
    });
    expect(screen.getAllByTestId('aviso-rapida-simon')).toHaveLength(1);
    await esperar(ESPERA_DESHACER_MS * 2);
    await asentar();
    expect(c.desactivarTercero).toHaveBeenCalledTimes(1);
    expect(n).toBe(1);
  });

  test('gesto nuevo tras un INDETERMINADO: la misma identidad («No sabemos si se guardó» · «Reintentar»)', async () => {
    const desactivar = jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el cambio.' }) as any);
    const c = cliente(desactivar);
    montar(c);
    await asentar();
    accion('ajter-fila-simon', 'derecha');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(screen.getByTestId('fallo-rapida-simon-texto')).toHaveTextContent(/No sabemos si se guardó/);
    expect(screen.getByTestId('fallo-rapida-simon-reintentar')).toBeTruthy();
    accion('ajter-fila-simon', 'derecha');
    await esperar(ESPERA_DESHACER_MS);
    await asentar();
    expect(desactivar).toHaveBeenCalledTimes(2);
    expect(n).toBe(1); // la identidad del primer gesto se conserva
  });

  test('la app pasa a segundo plano durante la espera → no se envía nada', async () => {
    let oyente: ((e: string) => void) | null = null;
    const espia = jest.spyOn(AppState, 'addEventListener').mockImplementation(((_: string, h: (e: string) => void) => {
      oyente = h;
      return { remove: jest.fn() };
    }) as any);
    try {
      const c = cliente();
      montar(c);
      await asentar();
      accion('ajter-fila-simon', 'derecha');
      await esperar(1000);
      await act(async () => oyente?.('background'));
      await esperar(ESPERA_DESHACER_MS * 2);
      await asentar();
      expect(c.desactivarTercero).not.toHaveBeenCalled();
    } finally {
      espia.mockRestore();
    }
  });

  test('la pantalla se desmonta durante la espera → no se envía nada', async () => {
    const c = cliente();
    const r = montar(c);
    await asentar();
    accion('ajter-fila-simon', 'derecha');
    r.unmount();
    await esperar(ESPERA_DESHACER_MS * 2);
    expect(c.desactivarTercero).not.toHaveBeenCalled();
  });
});
