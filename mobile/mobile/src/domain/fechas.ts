// ============================================================
// GAPTO MOBILE 2027
// Fichero: fechas.ts
// Ruta: mobile/src/domain/fechas.ts
// Descripción: Fechas locales del dispositivo (la fecha del hecho es la fecha LOCAL del usuario, no UTC).
// v0.2.0 (F05-D003): utilidades para la fecha editable (ayer, dd/mm/aaaa ↔ ISO).
// Versión: 0.2.0
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
