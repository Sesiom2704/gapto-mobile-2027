// ============================================================
// GAPTO MOBILE 2027
// Fichero: envio.test.ts
// Ruta: mobile/__tests__/envio.test.ts
// Descripción: Tests a nivel de hook de useEnvioGasto: discriminan las guardas del propio hook (doble envío concurrente y reintento sellado) con independencia del botón deshabilitado de la UI, que por sí solo las enmascaraba (mutantes M01/M02).
// v0.2.0 (F05-D003): borrador con propuesta de financiación y validación con fecha de hoy.
// Versión: 0.2.0
// ============================================================

import { act, renderHook } from '@testing-library/react-native';

import type { ClienteApi, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import { Borrador, borradorInicial, PayloadGastoPagado } from '../src/domain/intencion';
import { useEnvioGasto } from '../src/state/useEnvioGasto';

const valido: Borrador = { ...borradorInicial('2026-09-24'), importeTexto: '3,50', concepto: 'Café', presupuestable: true, soloMio: true, cuentaId: 'k', cuentaOrigen: 'INFERIDO', propuesta: 'SELF_100' };
const HOY = '2026-09-24';

function cliente(registrar: (p: PayloadGastoPagado) => Promise<Respuesta<ResultadoRegistro>>) {
  const enviados: PayloadGastoPagado[] = [];
  const c: ClienteApi = {
    registrarGastoPagado: async (p) => {
      enviados.push(p);
      return registrar(p);
    },
    cuentasPago: async () => ({ tipo: 'OK', datos: { cuentas: [] } }),
    gastoMes: async () => ({ tipo: 'INDETERMINADO', mensaje: '' }),
  };
  return { c, enviados };
}

let n = 0;
const nuevoId = () => `id-${++n}`;

test('dos envíos concurrentes desde el hook producen un único POST', async () => {
  let liberar: () => void = () => {};
  const { c, enviados } = cliente((p) => new Promise((r) => { liberar = () => r({ tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: 'PROPUESTA_ACEPTADA' } }); }));
  const { result } = renderHook(() => useEnvioGasto(c, nuevoId));
  await act(async () => {
    void result.current.enviar(valido, HOY);
    void result.current.reintentar();
    void result.current.enviar(valido, HOY);
  });
  expect(enviados).toHaveLength(1);
  await act(async () => liberar());
  expect(result.current.estado.fase).toBe('CONFIRMADO');
});

test('en INDETERMINADO, enviar con un borrador distinto reenvía la intención SELLADA original', async () => {
  let k = 0;
  const { c, enviados } = cliente(async (p) =>
    ++k === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: true, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: 'PROPUESTA_ACEPTADA' } },
  );
  const { result } = renderHook(() => useEnvioGasto(c, nuevoId));
  await act(async () => { await result.current.enviar(valido, HOY); });
  expect(result.current.estado.fase).toBe('INDETERMINADO');
  await act(async () => { await result.current.enviar({ ...valido, importeTexto: '99', concepto: 'otro' }, HOY); });
  expect(enviados).toHaveLength(2);
  expect(enviados[1]).toEqual(enviados[0]);
});

test('la intención sellada lleva la financiación: propuesta self 100 % aceptada o NO_DETERMINADA', async () => {
  const ok = async (p: PayloadGastoPagado) => ({ tipo: 'OK' as const, datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA' as const, aportacion_criterio: null, financiacion: p.financiacion.estado } });
  const a = cliente(ok);
  const h1 = renderHook(() => useEnvioGasto(a.c, nuevoId));
  await act(async () => { await h1.result.current.enviar(valido, HOY); });
  expect(a.enviados[0].financiacion).toEqual({ estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe: '3.50' });
  for (const b of [{ ...valido, propuestaRechazada: true }, { ...valido, propuesta: 'NO_DETERMINADA' as const }]) {
    const x = cliente(ok);
    const h = renderHook(() => useEnvioGasto(x.c, nuevoId));
    await act(async () => { await h.result.current.enviar(b, HOY); });
    expect(x.enviados[0].financiacion).toEqual({ estado: 'NO_DETERMINADA' });
  }
});

test('sin propuesta conocida para la cuenta o con fecha futura no se sella ni se envía', async () => {
  const x = cliente(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }));
  const { result } = renderHook(() => useEnvioGasto(x.c, nuevoId));
  let e: object = {};
  await act(async () => { e = await result.current.enviar({ ...valido, propuesta: null }, HOY); });
  expect(e).toHaveProperty('cuenta');
  await act(async () => { e = await result.current.enviar({ ...valido, fechaHecho: '2026-09-25' }, HOY); });
  expect(e).toHaveProperty('fecha');
  await act(async () => { e = await result.current.enviar({ ...valido, fechaHecho: '2026-02-30' }, HOY); });
  expect(e).toHaveProperty('fecha');
  expect(x.enviados).toHaveLength(0);
});
