// ============================================================
// GAPTO MOBILE 2027
// Fichero: envio.test.ts
// Ruta: mobile/__tests__/envio.test.ts
// Descripción: Tests a nivel de hook de useEnvioGasto: discriminan las guardas del propio hook (doble envío concurrente y reintento sellado) con independencia del botón deshabilitado de la UI, que por sí solo las enmascaraba (mutantes M01/M02).
// Versión: 0.1.0
// ============================================================

import { act, renderHook } from '@testing-library/react-native';

import type { ClienteApi, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import { Borrador, borradorInicial, PayloadGastoPagado } from '../src/domain/intencion';
import { useEnvioGasto } from '../src/state/useEnvioGasto';

const valido: Borrador = { ...borradorInicial('2026-09-24'), importeTexto: '3,50', concepto: 'Café', presupuestable: true, soloMio: true, cuentaId: 'k', cuentaOrigen: 'INFERIDO' };

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
  const { c, enviados } = cliente((p) => new Promise((r) => { liberar = () => r({ tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null } }); }));
  const { result } = renderHook(() => useEnvioGasto(c, nuevoId));
  await act(async () => {
    void result.current.enviar(valido);
    void result.current.reintentar();
    void result.current.enviar(valido);
  });
  expect(enviados).toHaveLength(1);
  await act(async () => liberar());
  expect(result.current.estado.fase).toBe('CONFIRMADO');
});

test('en INDETERMINADO, enviar con un borrador distinto reenvía la intención SELLADA original', async () => {
  let k = 0;
  const { c, enviados } = cliente(async (p) =>
    ++k === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: true, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null } },
  );
  const { result } = renderHook(() => useEnvioGasto(c, nuevoId));
  await act(async () => { await result.current.enviar(valido); });
  expect(result.current.estado.fase).toBe('INDETERMINADO');
  await act(async () => { await result.current.enviar({ ...valido, importeTexto: '99', concepto: 'otro' }); });
  expect(enviados).toHaveLength(2);
  expect(enviados[1]).toEqual(enviados[0]);
});
