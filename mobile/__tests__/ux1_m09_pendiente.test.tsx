// ============================================================
// GAPTO MOBILE 2027
// Fichero: ux1_m09_pendiente.test.tsx
// Ruta: mobile/__tests__/ux1_m09_pendiente.test.tsx
// Descripción: M-09 «Pendiente con X» compacto (T1-F06 UX-1, TR1-05): lectura certificada, sin cálculo. Oráculos:
//   O-M09-01 «Te debe / Le debes» son LITERALMENTE `te_debe` y `le_debes` de la respuesta aunque no coincidan con la
//   suma de las partidas; O-M09-02 cada partida con su `saldo` literal, las 3 visibles son las 3 más recientes por
//   `origen_fecha` y «Ver todo» aparece con más de 3; O-M09-03 `SIN_POSICIONES` o error de lectura → no aparece y no
//   bloquea; O-M09-04 sin escrituras (solo GET del endpoint). En la app: desde el formulario de registro, ir a
//   «Pendiente con X» y volver conserva el formulario; el ✓ de «Gasto registrado» con color de token (textPrimary); el título de
//   «Pendiente con X» no se repite en el botón atrás.
// Versión: 0.1.0 (F06 T1 UX-1 · M-09)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import { crearCliente, type ClienteApi, type CuentaPago, type Respuesta } from '../src/api/cliente';
import { hayPendiente, partidasRecientes, PendienteCompacto } from '../src/components/PendienteCompacto';
import type { PendienteConPersona, PosicionPendiente } from '../src/domain/reparto';
import { PendienteConScreen } from '../src/screens/PendienteConScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

declare const __dirname: string;

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };

const pos = (id: string, fecha: string | null, saldo: string | null, tipo: PosicionPendiente['tipo'] = 'DERECHO_COBRO', concepto = `Gasto ${id}`): PosicionPendiente => ({
  entidad_id: id, entidad_row_version: 1, tipo, nombre: null, saldo, estado: 'ACTIVA', apertura_indeterminada: false,
  origen_hecho_id: `h-${id}`, origen_fecha: fecha, origen_concepto: concepto, origen_tercero: null,
});
const pendiente = (x: Partial<PendienteConPersona>): PendienteConPersona => ({
  tercero_id: 'juan', nombre: 'Juan', te_debe: '0.00', le_debes: '0.00', neto: '0.00', neto_estado: 'DETERMINADO', posiciones: [], ...x,
});

function montarCompacto(resp: () => Promise<Respuesta<PendienteConPersona>>, onAbrir = jest.fn(), onVisible = jest.fn()) {
  const cliente = { pendienteCon: jest.fn(resp) } as unknown as ClienteApi;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PendienteCompacto cliente={cliente} terceroId="juan" nombre="Juan" onAbrir={onAbrir} onVisible={onVisible} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { cliente, onAbrir, onVisible };
}
const esperar = async () => {
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
};
const texto = (id: string) => screen.getByTestId(id).props.children;

// ------------------------------------------------------------------ O-M09-01
test('O-M09-01: «Te debe» y «Le debes» son los del servidor tal cual, aunque no sean la suma de las partidas', async () => {
  // Partidas que suman 20,00 + 10,00 = 30,00 €, pero el servidor dice 50,00 € (fixture a propósito).
  montarCompacto(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: '50.00', le_debes: '7.25', neto: '42.75', posiciones: [pos('a', '2026-11-01', '20.00'), pos('b', '2026-10-01', '10.00')] }) }));
  await esperar();
  expect(texto('pendiente-compacto-juan-te-debe')).toBe('50,00 €');
  expect(texto('pendiente-compacto-juan-le-debes')).toBe('7,25 €');
  expect(screen.queryByText('30,00 €')).toBeNull(); // nunca la suma
  expect(screen.queryByText('42,75 €')).toBeNull(); // nunca el neto (MU-M09-02)
});

test('O-M09-01: un total desconocido (null) se ve «Sin determinar», nunca 0,00 €', async () => {
  montarCompacto(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: null, neto: null, neto_estado: 'INDETERMINADO', posiciones: [pos('a', '2026-11-01', null)] }) }));
  await esperar();
  expect(texto('pendiente-compacto-juan-te-debe')).toBe('Sin determinar');
  expect(texto('pendiente-compacto-juan-partida-a-saldo')).toBe('Sin determinar');
});

// ------------------------------------------------------------------ O-M09-02
test('O-M09-02: las 3 más recientes por fecha (no por importe ni por orden de llegada), saldo literal y «Ver todo» con más de 3', async () => {
  const ps = [pos('vieja', '2026-01-10', '900.00'), pos('nueva', '2026-11-05', '1.00'), pos('sinfecha', null, '500.00'), pos('media', '2026-06-01', '30.00'), pos('reciente', '2026-10-20', '2.50', 'OBLIGACION_PAGO')];
  const { onAbrir } = montarCompacto(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: '1431.00', le_debes: '2.50', posiciones: ps }) }));
  await esperar();
  const vistas = screen.getAllByTestId(/^pendiente-compacto-juan-partida-[a-z]+$/).map((x) => x.props.testID);
  expect(vistas).toEqual(['pendiente-compacto-juan-partida-nueva', 'pendiente-compacto-juan-partida-reciente', 'pendiente-compacto-juan-partida-media']);
  expect(texto('pendiente-compacto-juan-partida-nueva-saldo')).toBe('1,00 €');
  expect(texto('pendiente-compacto-juan-partida-reciente-saldo')).toBe('2,50 €');
  expect(texto('pendiente-compacto-juan-partida-media-saldo')).toBe('30,00 €');
  expect(screen.getByTestId('pendiente-compacto-juan-ver-todo')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('pendiente-compacto-juan')));
  expect(onAbrir).toHaveBeenCalledTimes(1);
});

test('O-M09-02: con 3 partidas o menos no hay «Ver todo»', async () => {
  montarCompacto(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: '3.00', posiciones: [pos('a', '2026-11-01', '1.00'), pos('b', '2026-10-01', '1.00'), pos('c', '2026-09-01', '1.00')] }) }));
  await esperar();
  expect(screen.getAllByTestId(/^pendiente-compacto-juan-partida-[a-z]+$/)).toHaveLength(3);
  expect(screen.queryByTestId('pendiente-compacto-juan-ver-todo')).toBeNull();
});

test('partidasRecientes solo ordena y recorta (empate: el orden del servidor; sin fecha, al final)', () => {
  const ps = [pos('x', '2026-05-01', '1.00'), pos('y', null, '1.00'), pos('z', '2026-05-01', '1.00'), pos('w', '2026-07-01', '1.00')];
  expect(partidasRecientes(ps).map((x) => x.entidad_id)).toEqual(['w', 'x', 'z']);
  expect(partidasRecientes(ps, 10).map((x) => x.entidad_id)).toEqual(['w', 'x', 'z', 'y']);
  expect(partidasRecientes(ps, 10).map((x) => x.saldo)).toEqual(['1.00', '1.00', '1.00', '1.00']);
});

// ------------------------------------------------------------------ O-M09-03
test.each([
  ['SIN_POSICIONES', async () => ({ tipo: 'OK', datos: pendiente({ te_debe: null, le_debes: null, neto: null, neto_estado: 'SIN_POSICIONES' }) })],
  ['error de lectura', async () => ({ tipo: 'ERROR', mensaje: 'x' })],
  ['excepción', async () => { throw new Error('red'); }],
])('O-M09-03: %s → no aparece y avisa de que no es visible', async (_n, resp) => {
  const { onVisible } = montarCompacto(resp as () => Promise<Respuesta<PendienteConPersona>>);
  await esperar();
  expect(screen.queryByTestId('pendiente-compacto-juan')).toBeNull();
  expect(onVisible).toHaveBeenCalledWith(false);
});

test('hayPendiente: SIN_POSICIONES o sin partidas → no; con partidas → sí (MU-M09-04)', () => {
  expect(hayPendiente(pendiente({ neto_estado: 'SIN_POSICIONES', posiciones: [pos('a', null, '1.00')] }))).toBe(false);
  expect(hayPendiente(pendiente({ posiciones: [] }))).toBe(false);
  expect(hayPendiente(pendiente({ posiciones: [pos('a', null, '1.00')] }))).toBe(true);
});

// ------------------------------------------------------------------ O-M09-04
test('O-M09-04: el componente solo hace GET /v1/terceros/{id}/pendiente (ninguna escritura)', async () => {
  const peticiones: { url: string; metodo: string }[] = [];
  const fetchFalso = jest.fn(async (url: string, init: RequestInit) => {
    peticiones.push({ url, metodo: String(init.method) });
    return { ok: true, status: 200, json: async () => pendiente({ te_debe: '5.00', posiciones: [pos('a', '2026-11-01', '5.00')] }) } as unknown as Response;
  });
  const cliente = crearCliente({ baseUrl: 'http://api', token: 't', timeoutMs: 1000 }, fetchFalso as unknown as typeof fetch);
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PendienteCompacto cliente={cliente} terceroId="juan" nombre="Juan" onAbrir={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await esperar();
  expect(screen.getByTestId('pendiente-compacto-juan')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('pendiente-compacto-juan')));
  expect(peticiones).toEqual([{ url: 'http://api/v1/terceros/juan/pendiente', metodo: 'GET' }]);
});

// ------------------------------------------------------------------ título de «Pendiente con X»
test('«Pendiente con X»: el botón atrás ya no repite el nombre del título (conserva `pendiente-atras`)', async () => {
  const cliente = {
    pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: '5.00', posiciones: [pos('a', '2026-11-01', '5.00')] }) })),
    cuentasElegibles: jest.fn(async (operacion: string) => ({ tipo: 'OK', datos: { operacion, cuentas: [] } })),
  } as unknown as ClienteApi;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PendienteConScreen cliente={cliente} nuevoId={() => 'x'} ahora={() => new Date(2026, 10, 12, 10)} terceroId="juan" nombre="Juan" entidadId={null} onCerrar={jest.fn()} onVerHecho={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await esperar();
  expect(screen.getByText('Pendiente con Juan')).toBeTruthy();
  expect(screen.getByText('‹ Atrás')).toBeTruthy();
  expect(screen.queryByText('‹ Juan')).toBeNull();
  expect(screen.getByTestId('pendiente-atras')).toBeTruthy();
});

// ------------------------------------------------------------------ en la app: formulario → «Pendiente con X» → volver
const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
function clienteApp(): ClienteApi {
  return {
    ...clienteCategoriasStub([nodo({ id: 'alim', nombre: 'Alimentación' })]),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [{ id: 'juan', nombre: 'Juan', naturaleza: 'PERSONA', enabled: true, row_version: 1 }] } }) as any),
    listarPlantillas: jest.fn(async () => ({ tipo: 'OK', datos: { plantillas: [], acciones: [] } }) as any),
    propuestaRegistro: jest.fn(async (q: any) => ({ tipo: 'OK', datos: { tipo: q.tipo, campos: { categoria: null, tercero: null, contexto: null, cuenta: null, presupuestable: null }, avisos: [] } }) as any),
    cuentasElegibles: jest.fn(async (operacion: any) => ({ tipo: 'OK', datos: { operacion, cuentas: [] } })) as any,
    pendienteCon: jest.fn(async () => ({ tipo: 'OK', datos: pendiente({ te_debe: '30.00', posiciones: [pos('rest', '2026-11-02', '30.00', 'DERECHO_COBRO', 'Restaurante Gines')] }) })) as any,
  } as ClienteApi;
}

test('formulario de registro: el compacto aparece al elegir a Juan; ir a «Pendiente con Juan» y volver deja el formulario intacto', async () => {
  const c = clienteApp();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <Raiz cliente={c} nuevoId={() => '00000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 10, 12, 10)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await screen.findByTestId('accion-registrar');
  await act(async () => fireEvent.press(screen.getByTestId('accion-registrar')));
  await act(async () => fireEvent.press(screen.getByTestId('tipo-GASTO')));
  fireEvent.changeText(screen.getByTestId('campo-importe'), '12,50');
  await act(async () => fireEvent.press(screen.getByTestId('campo-tercero')));
  await act(async () => fireEvent.press(await screen.findByTestId('tercero-juan')));
  expect(await screen.findByTestId('pendiente-compacto-juan')).toBeTruthy();
  expect(texto('pendiente-compacto-juan-te-debe')).toBe('30,00 €');
  await act(async () => fireEvent.press(screen.getByTestId('pendiente-compacto-juan')));
  expect(await screen.findByTestId('pendiente-con')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('pendiente-atras')));
  await waitFor(() => expect(screen.queryByTestId('pendiente-con')).toBeNull());
  expect(screen.getByTestId('campo-importe').props.value).toBe('12,50'); // sin pérdida
  expect(screen.getByTestId('tercero-valor').props.children).toBe('Juan');
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
});

test('el ✓ de «Gasto registrado» usa un token de color de texto (textPrimary: contraste en claro y oscuro), no el color por defecto', () => {
  const fuente = require('fs').readFileSync(require('path').join(__dirname, '..', 'src', 'screens', 'GastoCompartidoScreen.tsx'), 'utf8') as string;
  const registro = require('fs').readFileSync(require('path').join(__dirname, '..', 'src', 'screens', 'RegistroGastoScreen.tsx'), 'utf8') as string;
  expect(fuente).toContain('<Text style={{ fontSize: 40, color: c.textPrimary }} accessibilityElementsHidden>✓</Text>');
  expect(registro).toContain('<Text style={{ fontSize: 40, color: c.textPrimary }} accessibilityElementsHidden>✓</Text>');
});
