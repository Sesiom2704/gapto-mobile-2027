// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedad_dominio.test.ts
// Ruta: mobile/__tests__/propiedad_dominio.test.ts
// Descripción: Lógica pura de B1 · Propiedad (src/domain/propiedad.ts): porcentajes como texto exacto, suma EXACTA del 100 % en diezmilésimas (33,3333 + 33,3333 + 33,3334), nunca un 0 %, cuatro modos de titularidad y su petición, validación de datos y textos de los códigos ★.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import {
  datosWire,
  estadoSuma,
  faltaDatos,
  faltaTitularidad,
  FORM_DATOS_VACIO,
  formatearPorcentaje,
  FormTitularidad,
  ParteForm,
  parsearPorcentaje,
  partesParaModo,
  textoErrorB1,
  titularidadWire,
  TEXTOS_ERROR_B1,
} from '../src/domain/propiedad';

const yo = (pct: string): ParteForm => ({ clave: 'y', yo: true, nombre: 'Tú', porcentaje: pct });
const t = (id: string, pct: string): ParteForm => ({ clave: id, yo: false, terceroId: id, nombre: id, porcentaje: pct });

describe('porcentajes', () => {
  test('texto canónico de 4 decimales y diezmilésimas enteras', () => {
    expect(parsearPorcentaje('50')).toEqual({ ok: true, valor: '50.0000', diezmilesimas: 500000 });
    expect(parsearPorcentaje('33,3333')).toEqual({ ok: true, valor: '33.3333', diezmilesimas: 333333 });
    expect(parsearPorcentaje(' 100 % ')).toEqual({ ok: true, valor: '100.0000', diezmilesimas: 1000000 });
    expect(parsearPorcentaje('0,0001')).toEqual({ ok: true, valor: '0.0001', diezmilesimas: 1 });
  });
  test('rechazos: vacío, 0 %, 5 decimales, más de 100, formato', () => {
    expect(parsearPorcentaje('')).toEqual({ ok: false, motivo: 'VACIO' });
    expect(parsearPorcentaje('0')).toEqual({ ok: false, motivo: 'NO_POSITIVO' });
    expect(parsearPorcentaje('0,0000')).toEqual({ ok: false, motivo: 'NO_POSITIVO' });
    expect(parsearPorcentaje('33,33333')).toEqual({ ok: false, motivo: 'DECIMALES' });
    expect(parsearPorcentaje('100,0001')).toEqual({ ok: false, motivo: 'MAYOR_100' });
    expect(parsearPorcentaje('-5')).toEqual({ ok: false, motivo: 'FORMATO' });
    expect(parsearPorcentaje('1e2')).toEqual({ ok: false, motivo: 'FORMATO' });
  });
  test('formato visible sin ceros finales', () => {
    expect(formatearPorcentaje('50.0000')).toBe('50 %');
    expect(formatearPorcentaje('33.3330')).toBe('33,333 %');
    expect(formatearPorcentaje('100.0000')).toBe('100 %');
  });
});

describe('suma exacta del 100 %', () => {
  test('33,3333 + 33,3333 + 33,3334 = 100 % exacto (sin float)', () => {
    expect(estadoSuma([yo('33,3333'), t('a', '33,3333'), t('b', '33,3334')])).toEqual({ ok: true, texto: 'Total 100 % ✓' });
  });
  test('falta y sobra con su texto; nunca se reparte el resto', () => {
    expect(estadoSuma([yo('50'), t('a', '40')])).toEqual({ ok: false, motivo: 'FALTA', texto: 'Total 90 % · falta un 10 %' });
    expect(estadoSuma([yo('60'), t('a', '50')])).toEqual({ ok: false, motivo: 'SOBRA', texto: 'Total 110 % · sobra un 10 %' });
    expect(estadoSuma([yo('33,3333'), t('a', '33,3333'), t('b', '33,3333')]).ok).toBe(false);
  });
  test('un 0 % no suma: es un error de porcentaje', () => {
    const r = estadoSuma([yo('100'), t('a', '0')]);
    expect(r.ok).toBe(false);
    expect(r.ok ? '' : r.motivo).toBe('PORCENTAJE');
  });
});

describe('titularidad', () => {
  const base = (x: Partial<FormTitularidad>): FormTitularidad => ({ modo: null, partes: [], desde: '15/10/2023', ...x });
  let n = 0;
  const clave = () => `k${++n}`;

  test('partes al elegir el modo', () => {
    expect(partesParaModo('SOLO_MIA', [], clave)).toEqual([expect.objectContaining({ yo: true, porcentaje: '100' })]);
    expect(partesParaModo('COMPARTIDA', [t('a', '50')], clave).map((x) => x.yo)).toEqual([true, false]);
    expect(partesParaModo('DE_OTROS', [yo('50'), t('a', '50')], clave).map((x) => x.yo)).toEqual([false]);
    expect(partesParaModo('DESCONOCIDA', [yo('50'), t('a', '50')], clave)).toEqual([]);
  });
  test('faltas: modo, Desde, adquisición, YO, duplicados y suma', () => {
    expect(faltaTitularidad(base({}), null)).toEqual(['elige de quién es']);
    expect(faltaTitularidad(base({ modo: 'DESCONOCIDA', desde: '' }), null)).toEqual([]);
    expect(faltaTitularidad(base({ modo: 'SOLO_MIA', desde: '' }), null)).toEqual(['la fecha «Desde»']);
    expect(faltaTitularidad(base({ modo: 'SOLO_MIA', desde: '1/1/2023' }), '2023-10-15')).toEqual(['una fecha «Desde» igual o posterior a la adquisición']);
    expect(faltaTitularidad(base({ modo: 'SOLO_MIA', desde: '15/10/2023', partes: [yo('100')] }), '2023-10-15')).toEqual([]);
    expect(faltaTitularidad(base({ modo: 'COMPARTIDA', partes: [t('a', '50'), t('b', '50')] }), null)).toContain('tu parte');
    expect(faltaTitularidad(base({ modo: 'COMPARTIDA', partes: [yo('50'), t('a', '25'), t('a', '25')] }), null)).toContain('no repetir personas');
    expect(faltaTitularidad(base({ modo: 'COMPARTIDA', partes: [yo('50'), t('a', '40')] }), null)).toContain('que el total sea 100 %');
    expect(faltaTitularidad(base({ modo: 'DE_OTROS', partes: [yo('50'), t('a', '50')] }), null)).toContain('quitarte (no es tuya)');
    expect(faltaTitularidad(base({ modo: 'DE_OTROS', partes: [t('a', '100')] }), null)).toEqual([]);
  });
  test('petición por modo: DESCONOCIDA sin desde ni partes; SOLO_MIA solo desde; partes canónicas', () => {
    expect(titularidadWire(base({ modo: 'DESCONOCIDA' }))).toEqual({ modo: 'DESCONOCIDA' });
    expect(titularidadWire(base({ modo: 'SOLO_MIA', partes: [yo('100')] }))).toEqual({ modo: 'SOLO_MIA', desde: '2023-10-15' });
    expect(titularidadWire(base({ modo: 'COMPARTIDA', partes: [yo('50'), t('a', '50,0')] }))).toEqual({
      modo: 'COMPARTIDA',
      desde: '2023-10-15',
      partes: [{ yo: true, porcentaje: '50.0000' }, { tercero_id: 'a', porcentaje: '50.0000' }],
    });
    expect(titularidadWire(base({ modo: 'DE_OTROS', partes: [t('a', '100')] }))).toEqual({ modo: 'DE_OTROS', desde: '2023-10-15', partes: [{ tercero_id: 'a', porcentaje: '100.0000' }] });
  });
});

describe('datos de la propiedad', () => {
  test('solo nombre y tipo obligatorios; desconocido = null, nunca 0 ni «No»', () => {
    expect(faltaDatos(FORM_DATOS_VACIO)).toEqual(['nombre', 'tipo']);
    const f = { ...FORM_DATOS_VACIO, nombre: ' Piso Ejemplo ', tipo: 'VIVIENDA' as const };
    expect(faltaDatos(f)).toEqual([]);
    expect(datosWire(f)).toEqual({
      nombre: 'Piso Ejemplo', tipo_propiedad: 'VIVIENDA', fecha_adquisicion: null, superficie_m2: null, superficie_construida_m2: null,
      habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null, notas: null,
    });
  });
  test('superficies > 0 con 2 decimales y enteros no negativos', () => {
    const f = { ...FORM_DATOS_VACIO, nombre: 'P', tipo: 'GARAJE' as const, superficie: '72,40', habitaciones: '0', banos: '2', garaje: false as const, adquisicion: '20/03/2027' };
    expect(datosWire(f)).toMatchObject({ superficie_m2: '72.40', habitaciones: 0, banos: 2, tiene_garaje: false, fecha_adquisicion: '2027-03-20' });
    expect(faltaDatos({ ...f, superficie: '0' })).toEqual(['superficie útil mayor que 0']);
    expect(faltaDatos({ ...f, habitaciones: '-1' })).toEqual(['habitaciones como número entero']);
    expect(faltaDatos({ ...f, adquisicion: '2027-03-20' })).toEqual(['fecha de adquisición como dd/mm/aaaa']);
  });
});

describe('errores de B1', () => {
  test('cada código ★ de B1 tiene texto propio', () => {
    for (const c of ['PARTICIPACION_NO_POSITIVA', 'NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD', 'ADQUISICION_POSTERIOR_A_TITULARIDAD', 'CAMBIO_RETROACTIVO_SIN_POLITICA',
      'CAMBIO_PROGRAMADO_EXISTENTE', 'REPARTO_ANTERIOR_AL_VIGENTE', 'METODO_RESERVADO_A_LA_COMPRA']) {
      expect(TEXTOS_ERROR_B1[c]).toBeTruthy();
    }
  });
  test('código desconocido: mensaje del servidor o el genérico', () => {
    expect(textoErrorB1('OTRO', 'Mensaje del servidor')).toBe('Mensaje del servidor');
    expect(textoErrorB1('OTRO', '')).toMatch(/No se ha podido confirmar/);
    expect(textoErrorB1('VERSION_DESFASADA', 'x')).toMatch(/ha cambiado desde que la abriste/);
  });
});
