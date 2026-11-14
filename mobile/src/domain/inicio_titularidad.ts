// ============================================================
// GAPTO MOBILE 2027
// Fichero: inicio_titularidad.ts
// Ruta: mobile/src/domain/inicio_titularidad.ts
// Descripción: B1-R · lógica pura de (a) los avisos A1/A2 del alta (mandato §4.2; N3 dentro del N1, solo cliente), (b) la cota del «Desde» del alta (L-01b: «Desde» ≤ hoy) y (c) C-PROP-03bis «Corregir el inicio de la titularidad» (P13 bis, solo ADELANTAR): nueva fecha anterior al inicio vigente, no futura y no anterior a la adquisición si se conoce; textos de la pantalla y de la confirmación. La oferta de la acción NO se deduce aquí: la decide el servidor (`inicio_titularidad.inicio_corregible`). No cambia partes ni reatribuye gastos ya registrados (HT2-18).
// Versión: 0.1.0 (F06 T2-F06 · B1-R (L-01/L-01b); trasladado del laboratorio lab-t2 45736ad y reescrito: sin `ofreceCorregirInicio`, con la cota del alta, la confirmación y los textos del §4.6)
// ============================================================

import { diaMesAnioIso } from './fechas';
import { esFechaIso } from './intencion';

/** A1: «Desde» posterior a la adquisición conocida. */
export function avisoA1(adquisicionIso: string | null, desdeIso: string | null): string | null {
  if (!adquisicionIso || !desdeIso || !esFechaIso(adquisicionIso) || !esFechaIso(desdeIso) || desdeIso <= adquisicionIso) return null;
  return `Los gastos entre el ${diaMesAnioIso(adquisicionIso)} y el ${diaMesAnioIso(desdeIso)} no tendrán reparto propuesto. Si la titularidad empezó al comprar, usa la fecha de adquisición.`;
}

export const TEXTO_A2 = '«Desde» es la fecha desde la que la app conoce el reparto: los gastos anteriores no tendrán reparto propuesto.';

/** A2: adquisición «No la sé» con un modo con titularidad. */
export function avisoA2(adquisicionIso: string | null, modo: string | null): string | null {
  if (adquisicionIso || !modo || modo === 'DESCONOCIDA') return null;
  return TEXTO_A2;
}

/** L-01b: el mismo texto que el servidor (FECHA_FUTURA del alta). */
export const TEXTO_DESDE_FUTURO = 'La fecha «Desde» no puede ser posterior a hoy.';

/** L-01b: el alta no deja continuar con «Desde» futuro. */
export function desdeFuturo(desdeIso: string | null, hoyIso: string): boolean {
  return !!desdeIso && esFechaIso(desdeIso) && desdeIso > hoyIso;
}

/** Validación local de C-PROP-03bis (el servidor revalida todo). */
export function faltasInicio(nuevoIso: string | null, inicioIso: string, hoyIso: string, adquisicionIso: string | null): string[] {
  if (!nuevoIso || !esFechaIso(nuevoIso)) return ['la nueva fecha (dd/mm/aaaa)'];
  if (nuevoIso >= inicioIso) return [`una fecha anterior al ${diaMesAnioIso(inicioIso)} (solo se puede adelantar)`];
  if (nuevoIso > hoyIso) return ['una fecha que no sea futura'];
  if (adquisicionIso && nuevoIso < adquisicionIso) return [`una fecha no anterior a la adquisición (${diaMesAnioIso(adquisicionIso)})`];
  return [];
}

export const TEXTO_EXPLICACION = 'Solo para corregir un error: la titularidad empezó antes. Las partes no cambian. Los gastos ya registrados no se recalculan.';
export const TEXTO_ADQUISICION_DESCONOCIDA = 'No sabemos cuándo la compraste: la app no puede comprobar esta fecha.';
export const TEXTO_AFECTADOS = 'Estos gastos ya registrados no cambian. Si quieres repartirlos, corrígelos uno a uno.';

/** Resumen de la confirmación visible antes de enviar. */
export function textoConfirmacion(inicioIso: string, nuevoIso: string, afectados: number): string {
  const gastos = afectados === 1 ? '1 gasto ya registrado no cambia' : `${afectados} gastos ya registrados no cambian`;
  return `El inicio pasa del ${diaMesAnioIso(inicioIso)} al ${diaMesAnioIso(nuevoIso)}. Mismas partes. ${gastos}.`;
}
