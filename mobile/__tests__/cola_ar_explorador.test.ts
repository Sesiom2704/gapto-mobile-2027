// ============================================================
// GAPTO MOBILE 2027
// Fichero: cola_ar_explorador.test.ts
// Ruta: mobile/__tests__/cola_ar_explorador.test.ts
// Descripción: COLA-AR · explorador de intercalaciones (consulta 10, AJ-F0507G9-01). Recorre todos los órdenes de eventos de cada estado inicial de la cola hasta la profundidad pedida y exige 0 violaciones de I1–I6 (ver `explorador/exploradorColaAR.ts`). Profundidad por defecto 4 (la de la suite y de los mutantes); `GAPTO_EXPLORADOR_PROFUNDIDAD` la sube para la tirada de evidencia, `GAPTO_EXPLORADOR_FILTRO` limita las configuraciones por nombre y `GAPTO_EXPLORADOR_INFORME` escribe el informe JSON en esa ruta.
// Versión: 0.1.0 (consulta 10, AJ-F0507G9-01)
// ============================================================

import {
  INVARIANTES,
  configuraciones,
  explorar,
  prepararMundo,
  type ResultadoConfig,
} from './explorador/exploradorColaAR';

const PROFUNDIDAD = Number(process.env.GAPTO_EXPLORADOR_PROFUNDIDAD ?? 4);
const FILTRO = process.env.GAPTO_EXPLORADOR_FILTRO ?? '';
const INFORME = process.env.GAPTO_EXPLORADOR_INFORME ?? '';
/** Solo para escribir el informe (sin tipos de Node en el proyecto). */
const fs = require('fs') as { writeFileSync(ruta: string, datos: string, codificacion: string): void };

jest.setTimeout(6 * 60 * 60 * 1000);

test('los prefijos llevan la cola a cada estado en memoria', async () => {
  const esperado: Record<string, string> = {
    'EN_PLAZO en memoria (identidad adoptada)': 'EN_PLAZO',
    'PENDIENTE_DE_ENVIO en memoria (enviar() espera la identidad)': 'PENDIENTE_DE_ENVIO',
    'ENVIADA en memoria (POST en vuelo)': 'ENVIADA',
    'RESULTADO_DESCONOCIDO en memoria (respuesta perdida)': 'RESULTADO_DESCONOCIDO',
  };
  for (const c of configuraciones(1).filter((x) => esperado[x.nombre])) {
    expect([c.nombre, await prepararMundo(c)]).toEqual([c.nombre, esperado[c.nombre]]);
  }
});

test(`explorador de intercalaciones: 0 violaciones de I1–I6 (profundidad ${PROFUNDIDAD})`, async () => {
  const resultados: ResultadoConfig[] = [];
  for (const c of configuraciones(PROFUNDIDAD).filter((x) => x.nombre.includes(FILTRO))) {
    resultados.push(await explorar(c));
  }
  const total = Object.fromEntries(INVARIANTES.map((k) => [k, resultados.reduce((a, r) => a + r.violaciones[k], 0)]));
  const informe = {
    profundidad: PROFUNDIDAD,
    configuraciones: resultados.length,
    caminos: resultados.reduce((a, r) => a + r.caminos, 0),
    transiciones: resultados.reduce((a, r) => a + r.transiciones, 0),
    violaciones: total,
    resultados,
  };
  if (INFORME) fs.writeFileSync(INFORME, JSON.stringify(informe, null, 1), 'utf-8');
  const ejemplos = resultados.flatMap((r) => r.ejemplos.map((e) => `${r.nombre} · ${e.invariante}: ${e.detalle}\n    ${e.camino.join(' → ')}`));
  expect(ejemplos.slice(0, 6).join('\n')).toBe('');
  expect(total).toEqual(Object.fromEntries(INVARIANTES.map((k) => [k, 0])));
});
