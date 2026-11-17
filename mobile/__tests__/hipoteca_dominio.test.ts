// ============================================================
// GAPTO MOBILE 2027
// Fichero: hipoteca_dominio.test.ts
// Ruta: mobile/__tests__/hipoteca_dominio.test.ts
// Descripción: Lógica pura de la hipoteca en el cliente (F06-01H; contrato v0.4 §3.2.1, §3.2.7-5, §3.3, §3.4, §3.5 y §8; mandato T3-F06 bloque 2 v1.1 §15) y llamadas opcionales del cliente HTTP. Cada guarda con un caso que falla si se quita: exposición del pago como constante de código en false y sin entorno; tipo anual 0–30 con 4 decimales; plazo → cuotas (1–600); primera cuota posterior a la escritura; tipo fijo/variable sin valor por defecto; bloque `hipoteca` exacto (sin campos de modalidad) y petición sin hipoteca intacta; capital + intereses = cuota; botón de pago solo con exposición, próxima cuota, hipoteca activa y deuda conocida; `propuesta_vista` del pago; alcance de la revisión sin «bonificación»; textos sin «ingreso» ni «cobro»; rutas y clasificación de las llamadas.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// Versión: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; N-31, firma 0f3e5633…): `REVISION_TIPO_EXPUESTA` constante propia (true) y `ofreceRevisionTipo`.
// Versión: 0.3.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…): `titularidadPrestamoEnFecha` (tramos y límites; sin campo, null).
// ============================================================

import { crearCliente } from '../src/api/cliente';
import type { PayloadCompra } from '../src/api/patrimonio';
import * as dominio from '../src/domain/hipoteca';
import {
  BorradorHipoteca, bloqueHipoteca, borradorHipoteca, conHipoteca, cuotasAfectadas, cuotasVisibles, deudaConocida, desglosePago, detalleFichaHipoteca,
  eleccionPropuesta, faltasHipoteca, faltasPago, faltasReparto, faltasRevision, filasPrevioVisibles, normalizarTasa, numeroCuotas, ofrecePagoCuota,
  PAGO_CUOTA_EXPUESTO, payloadCuadroPrevio, payloadPago, payloadRevision, textoAlcance, textoErrorHipoteca, textoSeguro,
} from '../src/domain/hipoteca';
import { ANA, BANCO, CTA, CTA2, cuadroPrevio, hipoteca, PARTES, YO } from './hipoteca_fixtures';

declare const __dirname: string;
const fs: { readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const fuente = (rel: string) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

const ESCRITURA = '2026-03-20';
const completo = (x: Partial<BorradorHipoteca> = {}): BorradorHipoteca => ({
  ...borradorHipoteca(), financiadorId: BANCO, importe: '100.000,00', cuentaDesembolsoId: CTA, tipoInteres: 'FIJO', tasa: '2,5', plazo: '30', unidadPlazo: 'ANIOS',
  primeraCuota: '2026-04-20', cuentaCargoId: CTA2, titularidad: { modo: 'TITULARIDAD' }, ...x,
});

// ------------------------------------------------------------------ exposición del pago (firma 2026-11-17)
test('exposición: PAGO_CUOTA_EXPUESTO es una constante de código y vale false (Q3 con STOP abierto)', () => {
  expect(PAGO_CUOTA_EXPUESTO).toBe(false);
  const src = fuente('src/domain/hipoteca.ts');
  expect(src).toMatch(/^export const PAGO_CUOTA_EXPUESTO = (true|false);$/m);
  expect(src).not.toMatch(/process\.env|EXPO_PUBLIC|expo-constants|Constants\./);
});

test('N-30: titularidadPrestamoEnFecha proyecta la titularidad DEL PRÉSTAMO vigente en la fecha (límites incluidos); sin el campo, null', () => {
  const tp = [
    { actor_id: YO, porcentaje: '100.0000', yo: true, tercero_id: null, nombre: null, vigente_desde: '2026-03-20', vigente_hasta: '2026-05-31' },
    { actor_id: ANA, porcentaje: '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana', vigente_desde: '2026-06-01', vigente_hasta: null },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, vigente_desde: '2026-06-01', vigente_hasta: null },
  ];
  const h = hipoteca({ titularidad_prestamo: tp });
  const yo100 = [{ actor_id: YO, porcentaje: '100.0000', yo: true, tercero_id: null, nombre: null }];
  const mitad = [{ actor_id: ANA, porcentaje: '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana' }, { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null }];
  expect(dominio.titularidadPrestamoEnFecha(h, '2026-05-31')).toEqual(yo100);
  expect(dominio.titularidadPrestamoEnFecha(h, '2026-06-01')).toEqual(mitad);
  expect(dominio.titularidadPrestamoEnFecha(h, '2027-01-20')).toEqual(mitad);
  expect(dominio.titularidadPrestamoEnFecha(h, '2026-03-19')).toEqual([]);
  expect(dominio.titularidadPrestamoEnFecha(hipoteca(), '2026-06-01')).toBeNull();
});

test('N-31: REVISION_TIPO_EXPUESTA es una constante de código propia (true); ofreceRevisionTipo exige exposición, ACTIVA y deuda conocida', () => {
  expect(dominio.REVISION_TIPO_EXPUESTA).toBe(true);
  expect(fuente('src/domain/hipoteca.ts')).toMatch(/^export const REVISION_TIPO_EXPUESTA = (true|false);$/m);
  expect(dominio.ofreceRevisionTipo(hipoteca(), true)).toBe(true);
  expect(dominio.ofreceRevisionTipo(hipoteca(), false)).toBe(false);
  expect(dominio.ofreceRevisionTipo(hipoteca({ estado: 'CANCELADA' }), true)).toBe(false);
  expect(dominio.ofreceRevisionTipo(hipoteca({ deuda_indeterminada: true, deuda_pendiente: null }), true)).toBe(false);
});

test('exposición: el botón de pago solo con exposición, próxima cuota, hipoteca ACTIVA y deuda conocida', () => {
  const h = hipoteca();
  expect(ofrecePagoCuota(h, true)).toBe(true);
  expect(ofrecePagoCuota(h, false)).toBe(false);
  expect(ofrecePagoCuota(hipoteca({ proxima_cuota: null }), true)).toBe(false);
  expect(ofrecePagoCuota(hipoteca({ estado: 'CERRADA' }), true)).toBe(false);
  expect(ofrecePagoCuota(hipoteca({ deuda_pendiente: null, deuda_indeterminada: true }), true)).toBe(false);
});

// ------------------------------------------------------------------ alta en la compra
test('tipo anual: 0 a 30 %, hasta 4 decimales, con coma o punto', () => {
  expect(normalizarTasa('2,5')).toBe('2.5');
  expect(normalizarTasa(' 3.1234 ')).toBe('3.1234');
  expect(normalizarTasa('0')).toBe('0');
  expect(normalizarTasa('30')).toBe('30');
  expect(normalizarTasa('30.0001')).toBeNull();
  expect(normalizarTasa('2.12345')).toBeNull();
  expect(normalizarTasa('-1')).toBeNull();
  expect(normalizarTasa('')).toBeNull();
});

test('plazo → número de cuotas mensuales (1 a 600)', () => {
  expect(numeroCuotas('30', 'ANIOS')).toBe(360);
  expect(numeroCuotas('50', 'ANIOS')).toBe(600);
  expect(numeroCuotas('51', 'ANIOS')).toBeNull();
  expect(numeroCuotas('600', 'MESES')).toBe(600);
  expect(numeroCuotas('601', 'MESES')).toBeNull();
  expect(numeroCuotas('1', 'MESES')).toBe(1);
  expect(numeroCuotas('0', 'MESES')).toBeNull();
  expect(numeroCuotas('2,5', 'ANIOS')).toBeNull();
});

test('faltas del bloque: completo no falta nada; cada dato obligatorio falta por separado', () => {
  expect(faltasHipoteca(completo(), ESCRITURA, PARTES)).toEqual([]);
  expect(borradorHipoteca().tipoInteres).toBeNull(); // sin valor por defecto (v0.7)
  expect(faltasHipoteca(completo({ tipoInteres: null }), ESCRITURA, PARTES)).toEqual(['tipo fijo o variable']);
  expect(faltasHipoteca(completo({ financiadorId: null }), ESCRITURA, PARTES)).toEqual(['el banco']);
  expect(faltasHipoteca(completo({ cuentaDesembolsoId: null }), ESCRITURA, PARTES)).toEqual(['la cuenta en la que el banco deja el préstamo']);
  expect(faltasHipoteca(completo({ cuentaCargoId: null }), ESCRITURA, PARTES)).toEqual(['la cuenta de cargo de las cuotas']);
  expect(faltasHipoteca(completo({ tasa: '31' }), ESCRITURA, PARTES)).toEqual(['el tipo anual (0 a 30 %, hasta 4 decimales)']);
  expect(faltasHipoteca(completo({ importe: '0' }), ESCRITURA, PARTES)).toEqual(['el importe del préstamo']);
  expect(faltasHipoteca(completo({ plazo: '51' }), ESCRITURA, PARTES)).toEqual(['el plazo (hasta 600 cuotas)']);
});

test('faltas del bloque: la primera cuota tiene que ser POSTERIOR a la escritura (el mismo día no vale)', () => {
  expect(faltasHipoteca(completo({ primeraCuota: ESCRITURA }), ESCRITURA, PARTES)).toEqual(['una primera cuota posterior a la escritura']);
  expect(faltasHipoteca(completo({ primeraCuota: '2026-03-21' }), ESCRITURA, PARTES)).toEqual([]);
  expect(faltasHipoteca(completo({ primeraCuota: '21/03/2026' }), ESCRITURA, PARTES)).toEqual(['la fecha de la primera cuota']);
});

test('titularidad del préstamo: la propuesta se marca si existe (nunca 100 % tuyo inventado); otro reparto suma 100', () => {
  expect(eleccionPropuesta(PARTES)).toEqual({ modo: 'TITULARIDAD' });
  expect(eleccionPropuesta([])).toBeNull();
  expect(eleccionPropuesta(null)).toBeNull();
  expect(faltasReparto({ modo: 'TITULARIDAD' }, [])).toEqual(['una titularidad registrada o indica otro reparto']);
  expect(faltasReparto({ modo: 'MANUAL', partes: { [YO]: '50', [ANA]: '50' } }, PARTES)).toEqual([]);
  expect(faltasReparto({ modo: 'MANUAL', partes: { [YO]: '50', [ANA]: '40' } }, PARTES)).toEqual(['un reparto que sume 100 %']);
  expect(faltasHipoteca(completo({ titularidad: null }), ESCRITURA, PARTES)).toEqual(['elegir el reparto del préstamo']);
});

test('bloque `hipoteca` exacto de C-COMPRA-01: propuesta de la escritura aceptada y SIN campos de modalidad no representable', () => {
  expect(bloqueHipoteca(completo(), PARTES, ESCRITURA)).toStrictEqual({
    financiador: { tercero_id: BANCO },
    importe_prestamo: '100000.00',
    cuenta_desembolso_id: CTA,
    titularidad: { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA', fecha_referencia: ESCRITURA,
      partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] } },
    tipo_interes: 'FIJO',
    tasa_anual_pct: '2.5',
    numero_cuotas: 360,
    fecha_primera_cuota: '2026-04-20',
    cuenta_cargo_id: CTA2,
  });
  const manual = bloqueHipoteca(completo({ titularidad: { modo: 'MANUAL', partes: { [YO]: '70', [ANA]: '30,5' } } }), PARTES, ESCRITURA);
  expect(manual.titularidad).toStrictEqual({ modo: 'MANUAL', partes: [{ actor_id: YO, porcentaje: '70' }, { actor_id: ANA, porcentaje: '30.5' }] });
});

test('sin hipoteca la petición de la compra no cambia (ni la clave); con hipoteca, en la fecha de la escritura de la petición', () => {
  const p = { intencion_id: 'i', row_version_esperada: 1, fecha_escritura: ESCRITURA, precio: '1.00', pagos_propios: [], gastos: [], atribucion: { modo: 'NO_LO_SE' } } as PayloadCompra;
  expect(conHipoteca(p, null, PARTES)).toBe(p);
  expect('hipoteca' in conHipoteca(p, null, PARTES)).toBe(false);
  const con = conHipoteca(p, completo(), PARTES);
  expect(con.hipoteca?.titularidad).toMatchObject({ propuesta_vista: { fecha_referencia: ESCRITURA } });
  expect(con.precio).toBe('1.00');
});

test('W-HIP-00: petición de la vista previa con capital, tipo, cuotas y primera cuota', () => {
  expect(payloadCuadroPrevio(completo())).toStrictEqual({ capital: '100000.00', tasa_anual: '2.5', numero_cuotas: 360, primera_cuota: '2026-04-20' });
  expect(payloadCuadroPrevio(completo({ primeraCuota: '' }))).toStrictEqual({ capital: '100000.00', tasa_anual: '2.5', numero_cuotas: 360 });
});

// ------------------------------------------------------------------ cuadro
test('cuadro: la vista previa enseña las 12 primeras y la última; la registrada, la ventana de la próxima y la última', () => {
  expect(filasPrevioVisibles(cuadroPrevio(20).cuotas, false).map((f) => f.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20]);
  expect(filasPrevioVisibles(cuadroPrevio(20).cuotas, true)).toHaveLength(20);
  expect(filasPrevioVisibles(cuadroPrevio(13).cuotas, false)).toHaveLength(13);
  const h = hipoteca();
  expect(cuotasVisibles(h, false).map((q) => q.numero)).toEqual([1, 2, 3, 4, 5, 6]);
  const larga = hipoteca({ cuotas: Array.from({ length: 40 }, (_, i) => ({ ...h.cuotas[3], numero: i + 1 })), proxima_cuota: { ...h.cuotas[3], numero: 20 } });
  expect(cuotasVisibles(larga, false).map((q) => q.numero)).toEqual([17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 40]);
});

test('deuda: legacy con saldo desconocido es «no disponible», nunca 0', () => {
  expect(deudaConocida(hipoteca())).toBe('98498.13');
  const legacy = hipoteca({ deuda_pendiente: null, deuda_indeterminada: true });
  expect(deudaConocida(legacy)).toBeNull();
  expect(detalleFichaHipoteca(legacy)).toBe('Lo que queda por pagar: no disponible · cuota 1.000,00 €');
  expect(detalleFichaHipoteca(hipoteca())).toBe('Te queda 98.498,13 € · cuota 1.000,00 €');
});

// ------------------------------------------------------------------ pago de una cuota
test('pago: el cliente solo comprueba capital + intereses = cuota (no recalcula)', () => {
  const q = hipoteca().cuotas[2];
  expect(desglosePago(q)).toEqual({ capital: '753.75', intereses: '246.25', salida: '1000.00', cuadra: true });
  expect(desglosePago({ ...q, interes: '246.26' }).cuadra).toBe(false);
  expect(desglosePago({ ...q, capital: '753.7' }).cuadra).toBe(false);
  expect(desglosePago({ ...q, cuota: 'x' }).cuadra).toBe(false);
});

test('pago: fecha del cargo no futura, cuenta y reparto de los intereses', () => {
  expect(faltasPago('2026-06-20', '2026-06-20', CTA, { modo: 'TITULARIDAD' }, PARTES)).toEqual([]);
  expect(faltasPago('2026-06-21', '2026-06-20', CTA, { modo: 'TITULARIDAD' }, PARTES)).toEqual(['una fecha del cargo que no sea futura']);
  expect(faltasPago(null, '2026-06-20', CTA, { modo: 'TITULARIDAD' }, PARTES)).toEqual(['la fecha del cargo']);
  expect(faltasPago('2026-06-20', '2026-06-20', null, { modo: 'TITULARIDAD' }, PARTES)).toEqual(['la cuenta']);
  expect(faltasPago('2026-06-20', '2026-06-20', CTA, null, PARTES)).toEqual(['elegir el reparto de los intereses']);
});

test('pago: `propuesta_vista` es SIEMPRE la propuesta mostrada; `partes` la elegida', () => {
  const h = hipoteca();
  expect(payloadPago(h, CTA, '2026-06-20', { modo: 'TITULARIDAD' }, PARTES, 'int-1')).toStrictEqual({
    intencion_id: 'int-1', row_version_esperada: 3, cuenta_id: CTA, fecha_pago: '2026-06-20',
    atribucion: { propuesta_vista: { partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] },
      partes: [{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }] },
  });
  const manual = payloadPago(h, CTA, '2026-06-20', { modo: 'MANUAL', partes: { [YO]: '100', [ANA]: '0' } }, PARTES, 'int-2');
  expect(manual.atribucion.propuesta_vista.partes).toEqual([{ actor_id: ANA, porcentaje: '40.0000' }, { actor_id: YO, porcentaje: '60.0000' }]);
  expect(manual.atribucion.partes).toEqual([{ actor_id: YO, porcentaje: '100' }, { actor_id: ANA, porcentaje: '0' }]);
});

// ------------------------------------------------------------------ revisión del tipo
test('revisión: afectadas = vencimiento ≥ desde; alcance sin «bonificación»', () => {
  const h = hipoteca();
  expect(cuotasAfectadas(h, '2026-07-20').map((q) => q.numero)).toEqual([4, 5, 6]);
  expect(cuotasAfectadas(h, '2026-07-21').map((q) => q.numero)).toEqual([5, 6]);
  expect(textoAlcance(3, '2026-07-20', 2)).toBe('Se recalculan 3 cuotas desde el 20 jul 2026; las 2 pagadas no cambian.');
  expect(textoAlcance(1, '2026-07-20', 1)).toBe('Se recalcula 1 cuota desde el 20 jul 2026; la 1 pagada no cambia.');
});

test('revisión: la fecha tiene que ser posterior a las condiciones vigentes, con cuotas por vencer y sin cuotas pagadas afectadas', () => {
  const h = hipoteca();
  const r = (desde: string, tasa = '2,95') => ({ desde, tasa, tipoInteres: null, indice: '', diferencial: '' });
  expect(faltasRevision(r('2026-07-01'), h)).toEqual([]);
  expect(faltasRevision(r('2026-03-20'), h)).toEqual(['una fecha posterior a las condiciones vigentes']);
  expect(faltasRevision(r('2026-05-01'), h)).toEqual(['una fecha posterior a la última cuota pagada']);
  expect(faltasRevision(r('2026-10-01'), h)).toEqual(['una fecha con cuotas por vencer']);
  expect(faltasRevision(r('2026-07-01', '40'), h)).toEqual(['el nuevo tipo anual (0 a 30 %, hasta 4 decimales)']);
  expect(faltasRevision({ ...r('2026-07-01'), diferencial: 'x' }, h)).toEqual(['un diferencial válido o vacío']);
});

test('revisión: payload exacto; índice y diferencial solo si se escriben', () => {
  const h = hipoteca();
  expect(payloadRevision({ desde: '2026-07-01', tasa: '2,95', tipoInteres: null, indice: '', diferencial: '' }, h, 'int-r')).toStrictEqual({
    intencion_id: 'int-r', row_version_esperada: 3, vigente_desde: '2026-07-01', tasa_anual: '2.95',
  });
  expect(payloadRevision({ desde: '2026-07-01', tasa: '2.95', tipoInteres: 'VARIABLE', indice: ' Euríbor ', diferencial: '0,75' }, h, 'int-r')).toStrictEqual({
    intencion_id: 'int-r', row_version_esperada: 3, vigente_desde: '2026-07-01', tasa_anual: '2.95', tipo_interes: 'VARIABLE', indice_referencia: 'Euríbor', diferencial: '0.75',
  });
});

// ------------------------------------------------------------------ R-1: textos
test('R-1: ningún texto de la hipoteca dice «ingreso» ni «cobro» ni «bonificación»', () => {
  const textos = (Object.values(dominio) as unknown[]).filter((v): v is string => typeof v === 'string');
  expect(textos.length).toBeGreaterThan(15);
  for (const t of textos) expect(t).not.toMatch(/ingres|cobr|bonificaci/i);
  const codigos = ['CUENTA_SIN_CAPACIDAD', 'HIPOTECA_YA_REGISTRADA', 'TERCERO_NO_DISPONIBLE', 'CUOTA_NO_PENDIENTE', 'CUOTA_ANTERIOR_PENDIENTE', 'FECHA_PAGO_INCOHERENTE',
    'EXCEDE_SALDO_POSICION', 'CUENTA_DESCONOCIDA', 'ATRIBUCION_PROPUESTA_DESFASADA', 'SALDO_PRINCIPAL_INDETERMINADO', 'OPERACION_NO_PERMITIDA_EN_ESTADO',
    'REVISION_SOBRE_CUOTA_PAGADA', 'SIN_CUOTAS_FUTURAS', 'FECHA_REVISION_INCOHERENTE', 'IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION', 'SUMA_NO_CUADRA'];
  for (const c of codigos) expect(textoErrorHipoteca(c)).toEqual(expect.any(String));
  for (const c of codigos) expect(textoErrorHipoteca(c)).not.toMatch(/ingres|cobr/i);
  expect(textoErrorHipoteca('CUENTA_SIN_CAPACIDAD')).toBe('Esta cuenta no puede recibir dinero en la fecha de la escritura.');
  expect(textoErrorHipoteca('OTRO_CODIGO')).toBeNull();
});

test('R-1: CONDICIONES_INCOMPLETAS con su motivo; el texto del servidor con «ingreso» o «cobro» no se muestra', () => {
  expect(textoErrorHipoteca('CONDICIONES_INCOMPLETAS', { motivo: 'PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA' })).toBe('La primera cuota tiene que ser posterior a la escritura.');
  expect(textoErrorHipoteca('CONDICIONES_INCOMPLETAS', { motivo: 'DESCONOCIDO' })).toBe('Revisa los datos de la hipoteca.');
  expect(textoErrorHipoteca('CONDICIONES_INCOMPLETAS')).toBe('Revisa los datos de la hipoteca.');
  expect(textoSeguro('El banco ingresa el préstamo')).toBe(dominio.TEXTO_GENERICO);
  expect(textoSeguro('Cobro pendiente')).toBe(dominio.TEXTO_GENERICO);
  expect(textoSeguro('Revisa la cuenta.')).toBe('Revisa la cuenta.');
  expect(textoSeguro('')).toBe(dominio.TEXTO_GENERICO);
});

// ------------------------------------------------------------------ cliente HTTP: llamadas opcionales
test('cliente: rutas, método y clasificación de las cuatro llamadas de la hipoteca', async () => {
  const llamadas: { url: string; init: RequestInit }[] = [];
  const fetchFalso = jest.fn(async (url: string, init: RequestInit) => {
    llamadas.push({ url, init });
    return { ok: false, status: 503, json: async () => ({}) } as Response;
  }) as unknown as typeof fetch;
  const c = crearCliente({ baseUrl: 'http://x', token: 't', timeoutMs: 1000 }, fetchFalso);
  const previo = await c.cuadroHipoteca!({ capital: '1.00', tasa_anual: '1', numero_cuotas: 1 });
  await c.hipotecaDePropiedad!('p/1');
  const pago = await c.pagarCuotaHipoteca!('f1', 3, payloadPago(hipoteca(), CTA, '2026-06-20', { modo: 'TITULARIDAD' }, PARTES, 'i'));
  const rev = await c.revisarTipoHipoteca!('f1', { intencion_id: 'i', row_version_esperada: 3, vigente_desde: '2026-07-01', tasa_anual: '2' });
  expect(llamadas.map((l) => `${l.init.method} ${l.url}`)).toEqual([
    'POST http://x/v1/hipotecas/cuadro', 'GET http://x/v1/propiedades/p%2F1/hipoteca', 'POST http://x/v1/hipotecas/f1/cuotas/3/pago', 'POST http://x/v1/hipotecas/f1/revision',
  ]);
  // W-HIP-00 no escribe: su indeterminado es el de una lectura; las escrituras usan la clasificación 'CAMBIO'.
  expect(previo).toEqual({ tipo: 'INDETERMINADO', mensaje: 'No hay conexión con el servidor.' });
  expect(pago).toEqual({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el cambio. Vuelve a cargar antes de repetirlo.' });
  expect(rev).toEqual(pago);
});
