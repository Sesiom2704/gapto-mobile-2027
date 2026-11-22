// ============================================================
// GAPTO MOBILE 2027
// Fichero: importe.ts
// Ruta: mobile/src/domain/importe.ts
// Descripción: Parseo y formato de importes es-ES sin depender de Intl del motor JS. Parseo estricto: magnitud positiva con hasta 2 decimales; nunca redondea en silencio.
// Versión: 0.1.0
// Versión: 0.2.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-07 / OBS-01 del 20-11): `formatearImporteAlTeclear` pone los puntos de miles mientras se teclea (2000 → 2.000) y el punto recién tecleado pasa a coma decimal; `parsearImporte` acepta el entero agrupado sin coma («2.000» = 2000,00), que es lo que deja el campo.
// ============================================================

export type ParseoImporte = { ok: true; valor: string } | { ok: false; motivo: 'VACIO' | 'FORMATO' | 'NO_POSITIVO' | 'DECIMALES' };

/** "3,50" | "3.50" | "1.234,5" -> "3.50" (string decimal canónico para la API). */
export function parsearImporte(texto: string): ParseoImporte {
  const t = texto.trim().replace(/\s|€/g, '');
  if (!t) return { ok: false, motivo: 'VACIO' };
  let norm = t;
  if (t.includes(',')) {
    // formato es-ES: el punto solo puede ser separador de miles
    if (!/^\d{1,3}(\.\d{3})*(,\d*)?$|^\d+(,\d*)?$/.test(t)) return { ok: false, motivo: 'FORMATO' };
    norm = t.replace(/\./g, '').replace(',', '.');
  } else if (/^\d{1,3}(\.\d{3})+$/.test(t)) {
    // D-C7-07: entero con puntos de miles y sin decimales, tal como lo deja el campo al teclear
    norm = t.replace(/\./g, '');
  } else if (!/^\d+(\.\d*)?$/.test(t)) {
    return { ok: false, motivo: 'FORMATO' };
  }
  const [ent, dec = ''] = norm.split('.');
  if (dec.length > 2) return { ok: false, motivo: 'DECIMALES' };
  const entero = ent.replace(/^0+(?=\d)/, '');
  const canon = `${entero}.${dec.padEnd(2, '0')}`;
  if (/^0\.00$/.test(canon)) return { ok: false, motivo: 'NO_POSITIVO' };
  return { ok: true, valor: canon };
}

/** "1234.5" -> "1.234,50 €" */
export function formatearEur(decimal: string): string {
  const neg = decimal.startsWith('-');
  const [ent, dec = '00'] = decimal.replace('-', '').split('.');
  const miles = ent.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${neg ? '−' : ''}${miles},${dec.padEnd(2, '0').slice(0, 2)} €`;
}

const agruparMiles = (entero: string) => entero.replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, '.');

/**
 * D-C7-07: texto de un campo de importe mientras se teclea, con los puntos de miles puestos («2000» → «2.000»,
 * «1234,5» → «1.234,5»). `anterior` es lo que mostraba el campo antes de esta pulsación.
 * - Un punto recién tecleado al final es la coma decimal («12.» → «12,»); si ya había coma, se ignora.
 * - Si el campo ya venía formateado con puntos de miles, se recalculan (borrar en «2.000» → «200»).
 * - Si venía precargado con el decimal canónico del servidor («120.50»), ese punto es el decimal («120.5» → «120,5»).
 * - Texto nuevo de golpe (pegado): «1234.56» → «1.234,56»; «1.234.567» se lee como miles.
 * - Lo que no es un importe (letras, signos) se devuelve tal cual: el parseo lo rechazará con su motivo.
 * Nunca redondea ni recorta decimales: el parseo decide (DECIMALES).
 */
export function formatearImporteAlTeclear(texto: string, anterior = ''): string {
  let t = texto.replace(/\s|€/g, '');
  if (!t) return '';
  const previo = anterior.replace(/\s|€/g, '');
  const conMiles = /^\d{1,3}(\.\d{3})+(,\d*)?$/.test(previo);
  const conDecimalCanonico = !conMiles && /^\d+\.\d*$/.test(previo);
  if (t.endsWith('.') && t.slice(0, -1) === previo) {
    t = t.includes(',') || conDecimalCanonico ? t.slice(0, -1) : `${t.slice(0, -1)},`;
  }
  let entero: string;
  let decimales: string | null;
  if (t.includes(',')) {
    const i = t.indexOf(',');
    entero = t.slice(0, i);
    decimales = t.slice(i + 1);
    if (!/^[\d.]*$/.test(entero) || !/^\d*$/.test(decimales)) return texto;
    entero = entero.replace(/\./g, '');
  } else {
    if (!/^[\d.]+$/.test(t)) return texto;
    const grupos = t.split('.');
    const comoMiles = !conDecimalCanonico && (conMiles || grupos.length === 1 || /^\d{1,3}(\.\d{3})+$/.test(t));
    if (comoMiles) {
      entero = t.replace(/\./g, '');
      decimales = null;
    } else if (grupos.length === 2) {
      [entero, decimales] = grupos;
    } else {
      return texto;
    }
  }
  if (!entero && decimales === null) return '';
  const miles = entero ? agruparMiles(entero) : '0';
  return decimales === null ? miles : `${miles},${decimales}`;
}
