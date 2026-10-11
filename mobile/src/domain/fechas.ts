// ============================================================
// GAPTO MOBILE 2027
// Fichero: fechas.ts
// Ruta: mobile/src/domain/fechas.ts
// Descripción: Fechas locales del dispositivo (la fecha del hecho es la fecha LOCAL del usuario, no UTC).
// v0.2.0 (F05-D003): utilidades para la fecha editable (ayer, dd/mm/aaaa ↔ ISO).
// v0.3.0 (F05-05 K3 §2.3/§2.6; F05 §49.4 A4/A7): fechas cortas de una fecha ISO («10 oct», «10 oct 2026», «Octubre 2026») y periodos de la Actividad en mes natural (límites semiabiertos [desde, hasta), mes anterior y siguiente), sin hora (fecha_hecho es date).
// Versión: 0.3.0
// ============================================================

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

const dos = (n: number) => String(n).padStart(2, '0');

export function isoLocal(d: Date): string {
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`;
}
export function mesLocal(d: Date): string {
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}`;
}
export function nombreMes(d: Date): string {
  const m = MESES[d.getMonth()];
  return `${m[0].toUpperCase()}${m.slice(1)} ${d.getFullYear()}`;
}
export function fechaCorta(d: Date): string {
  const dia = DIAS[d.getDay()];
  return `${dia[0].toUpperCase()}${dia.slice(1)}, ${d.getDate()} ${MESES_CORTOS[d.getMonth()]} ${d.getFullYear()}`;
}

export function ayer(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1);
}
/** «25/09/2026» → «2026-09-25»; null si el texto no tiene esa forma. */
export function ddmmaaaaAIso(t: string): string | null {
  const m = /^\s*(\d{1,2})\/(\d{1,2})\/(\d{4})\s*$/.exec(t);
  if (!m) return null;
  return `${m[3]}-${dos(Number(m[2]))}-${dos(Number(m[1]))}`;
}
export function isoADdmmaaaa(iso: string): string {
  const [a, m, d] = iso.split('-');
  return `${d}/${m}/${a}`;
}
export function fechaCortaIso(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number);
  return fechaCorta(new Date(a, m - 1, d));
}

/** «2026-10-10» → «10 oct». */
export function diaMesIso(iso: string): string {
  const [, m, d] = iso.split('-').map(Number);
  return `${d} ${MESES_CORTOS[m - 1]}`;
}

/** «2026-10-10» → «10 oct 2026». */
export function diaMesAnioIso(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number);
  return `${d} ${MESES_CORTOS[m - 1]} ${a}`;
}

/** «2026-10-10» → «Octubre 2026». */
export function mesAnioIso(iso: string): string {
  const [a, m] = iso.split('-').map(Number);
  return nombreMes(new Date(a, m - 1, 1));
}

/** Mes natural de una fecha ISO como [desde, hasta) («2026-10-01», «2026-11-01»). */
export function limitesMesIso(iso: string): { desde: string; hasta: string } {
  const [a, m] = iso.split('-').map(Number);
  return { desde: `${a}-${dos(m)}-01`, hasta: m === 12 ? `${a + 1}-01-01` : `${a}-${dos(m + 1)}-01` };
}

/** Primer día del mes anterior (o siguiente, con delta = 1) de una fecha ISO. */
export function mesDesplazadoIso(iso: string, delta: -1 | 1): string {
  const [a, m] = iso.split('-').map(Number);
  const total = a * 12 + (m - 1) + delta;
  return `${Math.floor(total / 12)}-${dos((total % 12) + 1)}-01`;
}
