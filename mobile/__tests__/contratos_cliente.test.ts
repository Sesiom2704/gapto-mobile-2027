// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_cliente.test.ts
// Ruta: mobile/__tests__/contratos_cliente.test.ts
// Descripción: Cliente HTTP de F06-02/03 (`api/contratos.ts`) contra un `fetch` doble: rutas y métodos del contrato N1 v1.1 (escrituras con POST, lecturas con GET; PA-20), cuerpo exacto sin `renta` ni `fianza`, rechazo clasificado con código y detalle, y respuesta indeterminada ante un fallo de red (la escritura no se da por fallida: se reenvía con la misma intención). `cliente.ts` no se amplía (test_154 I13a): el cliente nuevo solo importa de él.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import { crearClienteContratos } from '../src/api/contratos';

const CFG = { baseUrl: 'http://api.test', token: 'tok', timeoutMs: 5000 };
function doble(respuesta: { ok?: boolean; status?: number; cuerpo?: unknown } = {}) {
  const llamadas: { url: string; init: any }[] = [];
  const f = jest.fn(async (url: string, init: any) => {
    llamadas.push({ url, init });
    return { ok: respuesta.ok ?? true, status: respuesta.status ?? 200, json: async () => respuesta.cuerpo ?? {} } as unknown as Response;
  });
  return { cliente: crearClienteContratos(CFG, f as unknown as typeof fetch), llamadas, f };
}

test('lecturas: GET con ruta del contrato (L-CON-01..03, L-SRV-01, L-TER-01, clasificaciones y selector con uso)', async () => {
  const { cliente, llamadas } = doble();
  await cliente.contratosDePropiedad('p 1');
  await cliente.contrato('c1');
  await cliente.propuestaContrato('p1', { tipo: 'HABITACION', habitacion: 4, inicio: '2026-11-01', inquilinoId: 't1' });
  await cliente.propuestaContrato('p1', { tipo: 'VIVIENDA_COMPLETA', inicio: '2026-11-01' });
  await cliente.serviciosDePropiedad('p1');
  await cliente.fichaTercero('t1');
  await cliente.clasificacionesTercero();
  await cliente.tercerosParaContrato('Carlos Ruiz');
  expect(llamadas.map((l) => `${l.init.method} ${l.url.replace(CFG.baseUrl, '')}`)).toEqual([
    'GET /v1/propiedades/p%201/contratos',
    'GET /v1/contratos/c1',
    'GET /v1/propiedades/p1/contratos/propuesta?tipo=HABITACION&inicio=2026-11-01&habitacion=4&inquilino_id=t1',
    'GET /v1/propiedades/p1/contratos/propuesta?tipo=VIVIENDA_COMPLETA&inicio=2026-11-01',
    'GET /v1/propiedades/p1/servicios',
    'GET /v1/terceros/t1',
    'GET /v1/clasificaciones-tercero',
    'GET /v1/terceros/asistente-contratos?q=Carlos%20Ruiz',
  ]);
  expect(llamadas.every((l) => l.init.headers.Authorization === 'Bearer tok')).toBe(true);
});

test('escrituras: POST a la ruta de cada operación (PA-20) con el cuerpo tal cual', async () => {
  const { cliente, llamadas } = doble();
  const cuerpo = { intencion_id: 'i', row_version_esperada: 3 };
  await cliente.altaContrato({ intencion_id: 'i', propiedad_id: 'p1', tipo: 'VIVIENDA_COMPLETA', nombre: 'n', fecha_inicio: '2026-11-01', estado: 'BORRADOR' });
  await cliente.editarContrato('c1', { ...cuerpo, fecha_fin_prevista: '2028-08-31', motivo: 'Prórroga anual' });
  await cliente.terminarContrato('c1', { ...cuerpo, fecha_fin_real: '2027-01-31' });
  await cliente.formalizarContrato('c1', cuerpo);
  await cliente.cancelarContrato('c1', { ...cuerpo, motivo: 'm' });
  await cliente.sucesorContrato('c1', { ...cuerpo, fecha_fin_real: '2027-01-31', nuevo: { nombre: 'n', fecha_inicio: '2027-02-01', estado: 'FORMALIZADO' } });
  await cliente.anadirPersona('c1', { ...cuerpo, actor: 'YO', rol: 'GESTOR', principal: false, desde: '2026-11-01' });
  await cliente.cerrarPersona('c1', 'pp 1', { ...cuerpo, hasta: '2027-01-31' });
  await cliente.nuevaClausula('c1', { ...cuerpo, desde: '2027-01-01', clausula: { tipo: 'NINGUNA' } });
  await cliente.altaServicio({ intencion_id: 'i', tipo_servicio: 'LUZ', nombre: 'Luz' });
  await cliente.editarServicio('s1', { ...cuerpo, nombre: 'Luz 2' });
  await cliente.bajaServicio('s1', { ...cuerpo, fecha_fin_real: '2027-01-31' });
  await cliente.tratamientoServicio('c1', 's1', { ...cuerpo, tratamiento: { servicio_id: 's1', modo: 'INCLUIDO', desde: '2026-11-01' } });
  await cliente.anadirRoles('t1', { ...cuerpo, anadir: ['AVALISTA'] });
  await cliente.anadirClasificacion('t1', { ...cuerpo, anadir: ['k1'], principal: 'k1' });
  expect(llamadas.every((l) => l.init.method === 'POST')).toBe(true);
  expect(llamadas.map((l) => l.url.replace(CFG.baseUrl, ''))).toEqual([
    '/v1/intenciones/contrato-alquiler',
    '/v1/contratos/c1/editar',
    '/v1/contratos/c1/terminar',
    '/v1/contratos/c1/formalizar',
    '/v1/contratos/c1/cancelar',
    '/v1/contratos/c1/sucesor',
    '/v1/contratos/c1/personas',
    '/v1/contratos/c1/personas/pp%201/cerrar',
    '/v1/contratos/c1/clausula',
    '/v1/intenciones/servicio',
    '/v1/servicios/s1/editar',
    '/v1/servicios/s1/baja',
    '/v1/contratos/c1/servicios/s1',
    '/v1/terceros/t1/roles',
    '/v1/terceros/t1/clasificaciones',
  ]);
  // el cuerpo viaja tal cual, sin renta ni fianza
  expect(JSON.parse(llamadas[0].init.body)).toEqual({ intencion_id: 'i', propiedad_id: 'p1', tipo: 'VIVIENDA_COMPLETA', nombre: 'n', fecha_inicio: '2026-11-01', estado: 'BORRADOR' });
  for (const l of llamadas) expect(l.init.body).not.toMatch(/"renta"|"fianza"/);
});

test('rechazo 4xx: código, mensaje y detalle del servidor (solape con la lista de contratos)', async () => {
  const detalle = { solapados: [{ id: 'v', nombre: '26-VIV-JM', tipo: 'VIVIENDA_COMPLETA', habitacion: null, desde: '2026-09-01', hasta: null }] };
  const { cliente } = doble({ ok: false, status: 409, cuerpo: { codigo: 'SOLAPE_CON_CONTRATO_FIRMADO', mensaje: 'm', detalle } });
  const r = await cliente.altaContrato({ intencion_id: 'i', propiedad_id: 'p1', tipo: 'HABITACION', habitacion: 2, nombre: 'n', fecha_inicio: '2026-11-01', estado: 'FORMALIZADO' });
  expect(r).toEqual({ tipo: 'RECHAZADO', codigo: 'SOLAPE_CON_CONTRATO_FIRMADO', mensaje: 'm', detalle });
});

test('un 5xx o un fallo de red de una escritura es INDETERMINADO (nunca «falló»)', async () => {
  const a = doble({ ok: false, status: 503, cuerpo: null });
  expect((await a.cliente.terminarContrato('c1', { intencion_id: 'i', row_version_esperada: 1, fecha_fin_real: '2027-01-31' })).tipo).toBe('INDETERMINADO');
  const f = jest.fn(async () => { throw new Error('red'); });
  const c = crearClienteContratos(CFG, f as unknown as typeof fetch);
  const r = await c.altaServicio({ intencion_id: 'i', tipo_servicio: 'LUZ', nombre: 'Luz' });
  expect(r.tipo).toBe('INDETERMINADO');
  if (r.tipo === 'INDETERMINADO') expect(r.mensaje).toMatch(/comprobar|cargar|repetirlo/i);
});
