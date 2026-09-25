// ============================================================
// GAPTO MOBILE 2027
// Fichero: importe.ts
// Ruta: mobile/src/domain/importe.ts
// Descripción: Parseo y formato de importes es-ES sin depender de Intl del motor JS. Parseo estricto: magnitud positiva con hasta 2 decimales; nunca redondea en silencio.
// Versión: 0.1.0
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
