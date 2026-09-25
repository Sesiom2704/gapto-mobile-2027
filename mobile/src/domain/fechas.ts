// ============================================================
// GAPTO MOBILE 2027
// Fichero: fechas.ts
// Ruta: mobile/src/domain/fechas.ts
// Descripción: Fechas locales del dispositivo (la fecha del hecho es la fecha LOCAL del usuario, no UTC).
// Versión: 0.1.0
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
