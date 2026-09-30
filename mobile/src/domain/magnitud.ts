// ============================================================
// GAPTO MOBILE 2027
// Fichero: magnitud.ts
// Ruta: mobile/src/domain/magnitud.ts
// Descripción: Valores de magnitudes en el registro (F05 §28.2 AJ-C07-02/06; F09 §12.97.3). `normalizarValorMagnitud` convierte lo escrito en texto decimal CANÓNICO con punto (acepta coma como separador de entrada) y rechaza vacío, signo «+», exponente, NaN/∞, cero con signo («-0»), ceros a la izquierda, más de `precision_decimales` cifras decimales significativas (los ceros de cola no cuentan: con precisión 2, «1.230» es válido y «1.234» no) y más de 12 cifras enteras. Es ayuda de captura: la autoridad es el servidor (C07). Desconocido ≠ cero: nunca se rellena «0». `conservarMagnitudes` / `descartadas` gestionan el cambio de categoría (C07: se conservan las comunes y se confirma antes de descartar valores informados).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import type { MagnitudCategoria } from './categoria';

export type MotivoValor = 'VACIO' | 'FORMATO' | 'CERO_CON_SIGNO' | 'DECIMALES' | 'ENTEROS';

export type ResultadoValor = { ok: true; valor: string } | { ok: false; motivo: MotivoValor };

const CANONICO = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/;
export const MAX_ENTEROS = 12;

export function normalizarValorMagnitud(texto: string, precision: number): ResultadoValor {
  const t = texto.trim();
  if (t === '') return { ok: false, motivo: 'VACIO' };
  if ((t.match(/[.,]/g) ?? []).length > 1) return { ok: false, motivo: 'FORMATO' };
  const v = t.replace(',', '.');
  if (!CANONICO.test(v)) return { ok: false, motivo: 'FORMATO' };
  const [entera, decimal = ''] = v.replace(/^-/, '').split('.');
  if (v.startsWith('-') && /^0$/.test(entera) && /^0*$/.test(decimal)) return { ok: false, motivo: 'CERO_CON_SIGNO' };
  if (entera.length > MAX_ENTEROS) return { ok: false, motivo: 'ENTEROS' };
  if (decimal.replace(/0+$/, '').length > precision) return { ok: false, motivo: 'DECIMALES' };
  return { ok: true, valor: v };
}

export function textoMotivoValor(motivo: MotivoValor, precision: number): string {
  switch (motivo) {
    case 'VACIO':
      return 'Indica un valor.';
    case 'FORMATO':
    case 'CERO_CON_SIGNO':
      return 'Valor no válido.';
    case 'DECIMALES':
      return precision === 0 ? 'Sin decimales.' : `Máximo ${precision} ${precision === 1 ? 'decimal' : 'decimales'}.`;
    case 'ENTEROS':
      return 'Valor demasiado grande.';
  }
}

/** Solo los valores escritos de magnitudes que existen en la categoría nueva. */
export function conservarMagnitudes(previos: Record<string, string>, nuevas: MagnitudCategoria[]): Record<string, string> {
  const ids = new Set(nuevas.map((m) => m.magnitud_id));
  const res: Record<string, string> = {};
  for (const [id, texto] of Object.entries(previos)) if (ids.has(id)) res[id] = texto;
  return res;
}

/** Magnitudes con valor INFORMADO que se perderían al pasar a `nuevas` (null = «Sin categoría»). */
export function descartadas(
  previos: Record<string, string>,
  actuales: MagnitudCategoria[],
  nuevas: MagnitudCategoria[] | null,
): MagnitudCategoria[] {
  const quedan = new Set((nuevas ?? []).map((m) => m.magnitud_id));
  return actuales.filter((m) => (previos[m.magnitud_id] ?? '').trim() !== '' && !quedan.has(m.magnitud_id));
}
