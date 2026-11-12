// ============================================================
// GAPTO MOBILE 2027
// Fichero: fechas.ts
// Ruta: mobile/src/domain/fechas.ts
// Descripción: Fechas locales del dispositivo (la fecha del hecho es la fecha LOCAL del usuario, no UTC).
// v0.2.0 (F05-D003): utilidades para la fecha editable (ayer, dd/mm/aaaa ↔ ISO).
// v0.3.0 (F05-05 K3 §2.3/§2.6; F05 §49.4 A4/A7): fechas cortas de una fecha ISO («10 oct», «10 oct 2026», «Octubre 2026») y periodos de la Actividad en mes natural (límites semiabiertos [desde, hasta), mes anterior y siguiente), sin hora (fecha_hecho es date).
// v0.4.0 (F06 T1 UX-1 · M-07; D-M2-04): máscara dd/mm/aaaa (`enmascararFecha`, solo sobre cifras), rejilla del calendario mensual en JS (`rejillaMesIso`, lunes primero) y fechas de años 0001–0099 sin convertirlas a 1900–1999 (`fechaLocal` con `setFullYear`; `fechaCortaIso`, `mesAnioIso` y `mesDesplazadoIso` con el año a 4 cifras).
// Versión: 0.4.0
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
  return fechaCorta(fechaLocal(a, m, d));
}

/** Fecha local a mediodía del día civil a/m/d. `setFullYear` evita que los años 0–99 pasen a 1900–1999 (D-M2-04). */
export function fechaLocal(a: number, m: number, d: number): Date {
  const f = new Date(2000, 0, 1, 12);
  f.setFullYear(a, m - 1, d);
  return f;
}

/**
 * M-07: máscara dd/mm/aaaa. Solo actúa sobre CIFRAS: con 1–8 cifras (y, como mucho, las barras que ella misma pone,
 * en la 3.ª y la 6.ª posición) inserta las barras: «02032026» → «02/03/2026», «0203» → «02/03», «02/032» → «02/03/2».
 * Cualquier otro texto (barras en otra posición, letras, puntos, más de 8 cifras) se devuelve TAL CUAL: «1/1/26» o
 * «6/11» siguen viendo el mismo rechazo que antes. No valida: solo da forma.
 */
export function enmascararFecha(t: string): string {
  const conMascara = /^\d*$/.test(t) || /^\d{2}\/\d*$/.test(t) || /^\d{2}\/\d{2}\/\d*$/.test(t);
  if (!conMascara) return t;
  const cifras = t.replace(/\//g, '');
  if (cifras.length > 8) return t;
  if (cifras.length <= 2) return cifras;
  if (cifras.length <= 4) return `${cifras.slice(0, 2)}/${cifras.slice(2)}`;
  return `${cifras.slice(0, 2)}/${cifras.slice(2, 4)}/${cifras.slice(4)}`;
}

/** M-07: rejilla del mes de `mesIso` (cualquier día del mes) para el calendario: semanas de 7 celdas (lunes primero) con la fecha ISO o null. */
export function rejillaMesIso(mesIso: string): (string | null)[][] {
  const [a, m] = mesIso.split('-').map(Number);
  const dias = fechaLocal(a, m + 1, 0).getDate();
  const hueco = (fechaLocal(a, m, 1).getDay() + 6) % 7;
  const celdas: (string | null)[] = [...Array(hueco).fill(null)];
  for (let d = 1; d <= dias; d++) celdas.push(`${anio4(a)}-${dos(m)}-${dos(d)}`);
  while (celdas.length % 7 !== 0) celdas.push(null);
  const semanas: (string | null)[][] = [];
  for (let i = 0; i < celdas.length; i += 7) semanas.push(celdas.slice(i, i + 7));
  return semanas;
}

const anio4 = (a: number) => String(a).padStart(4, '0');

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
  return nombreMes(fechaLocal(a, m, 1));
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
  return `${anio4(Math.floor(total / 12))}-${dos((total % 12) + 1)}-01`;
}
