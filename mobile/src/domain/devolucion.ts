// ============================================================
// GAPTO MOBILE 2027
// Fichero: devolucion.ts
// Ruta: mobile/src/domain/devolucion.ts
// Descripción: Lógica pura de la devolución contextual D-194 (F05-06 M2; F05 §14, §51.2; lámina DEV v0.1 D-DEV-01..08 y P-DEV-01..06, F09 §12.105). La devolución siempre parte de una compra (D-DEV-01): origen fijo con lo ya devuelto y lo que queda (D-DEV-02); límite visible (D-DEV-08: no se deja revisar más de lo que queda); abono como pregunta aparte («Sí, en <cuenta de la compra>», «En otra cuenta», «Todavía no»; D-DEV-03, P-DEV-02); «Tuya» propuesta solo si el servidor la demuestra (COMPLETA de un único actor propio), si no «Sin indicar» por defecto y «Todo mío» no disponible con su motivo (P-DEV-01; el canon F05 §51.2 manda sobre la lámina); nunca «Ingreso» (D-DEV-04); el neto es derivado (D-DEV-05). En la Actividad (P-DEV-03) el importe va sin «+» ni verde con la etiqueta «Devolución» o «Abono pendiente» (D-DEV-07).
// Versión: 0.1.0 (F05-06 M2-B §B1)
// ============================================================

import type { ContextoDevolucion, FilaActividad } from '../api/cliente';
import { diaMesIso } from './fechas';
import { formatearEur, parsearImporte } from './importe';

export type RespuestaAbono = 'COMPRA' | 'OTRA' | 'TODAVIA_NO';
export type AtribucionDevolucion = 'SOLO_MIO' | 'SIN_INDICAR';

export const TEXTO_PREGUNTA_ABONO = '¿Ya te han abonado el dinero?';
export const TEXTO_TODAVIA_NO = 'Se registra la devolución; el dinero no cuenta como disponible hasta que confirmes el abono.';
export const TEXTO_SIN_REPARTO =
  'La compra no tiene el reparto indicado, así que no se reparte la devolución por proporción. Si lo dejas sin indicar, no contará como tuyo en el Resultado.';
export const TEXTO_TODO_MIO_NO_DISPONIBLE = 'Solo si la compra era 100 % tuya.';
export const TEXTO_EXCESO = 'Si te han abonado más, la diferencia no es una devolución: regístrala aparte según lo que sea.';
export const TEXTO_NETO = 'Se calcula; no se guarda.';
export const TEXTO_SIN_DEVOLVER = 'Una devolución no ofrece «Registrar devolución».';
export const ETIQUETA_DEVOLUCION = 'Devolución';
export const ETIQUETA_ABONO_PENDIENTE = 'Abono pendiente';

/** Motivo por el que una compra no admite devolución, en lenguaje llano (B3 y P-DEV-05/06). */
export const MOTIVO_NO_DISPONIBLE: Record<string, string> = {
  DEVOLUCION_ORIGEN_NO_ACTIVO: 'Esta compra ya no está activa.',
  DEVOLUCION_ORIGEN_NO_GASTO: 'Solo se pueden registrar devoluciones de gastos.',
  DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS: 'Viene de la versión anterior con varias partes: no se puede saber qué se devuelve.',
  DEVOLUCION_ORIGEN_MULTICATEGORIA: 'Tiene varias categorías: aún no se puede registrar su devolución.',
  EXCEDE_CAPACIDAD_REVERSIBLE: 'Ya se ha devuelto todo el importe de esta compra.',
};

export function motivoNoDisponible(codigo: string | null): string {
  return (codigo && MOTIVO_NO_DISPONIBLE[codigo]) || 'No se puede registrar una devolución de esta compra.';
}

/** Compara importes decimales de texto con dos decimales («80.00»). */
function centimos(valor: string): number {
  const [e, d = ''] = valor.split('.');
  const signo = e.startsWith('-') ? -1 : 1;
  return signo * (Math.abs(Number(e)) * 100 + Number((d + '00').slice(0, 2)));
}

/** Importe escrito que supera lo que queda (D-DEV-08); null si no se puede saber todavía. */
export function superaLoQueQueda(importeTexto: string, queda: string): boolean {
  const r = parsearImporte(importeTexto);
  return r.ok && centimos(r.valor) > centimos(queda);
}

export function textoSupera(queda: string): string {
  return `Supera lo que queda por devolver de esta compra (${formatearEur(queda)}). ${TEXTO_EXCESO}`;
}

/** Neto derivado tras la devolución que se está revisando (D-DEV-05). */
export function netoTras(ctx: Pick<ContextoDevolucion, 'importe_total' | 'devuelto'>, importe: string): string {
  const n = centimos(ctx.importe_total) - centimos(ctx.devuelto) - centimos(importe);
  const s = n < 0 ? '-' : '';
  const a = Math.abs(n);
  return `${s}${Math.floor(a / 100)}.${String(a % 100).padStart(2, '0')}`;
}

/** Atribución inicial (P-DEV-01): «Tuya» solo si el servidor la demuestra; si no, «Sin indicar». */
export function atribucionInicial(ctx: Pick<ContextoDevolucion, 'tuya_disponible'>): AtribucionDevolucion {
  return ctx.tuya_disponible ? 'SOLO_MIO' : 'SIN_INDICAR';
}

/** Lo que falta para revisar; vacío = se puede. */
export function faltaDevolucion(
  f: { importeTexto: string; fecha: string; abono: RespuestaAbono | null; cuentaAbono: string | null; queda: string },
  hoyIso: string,
): string[] {
  const r: string[] = [];
  const imp = parsearImporte(f.importeTexto);
  if (!imp.ok) r.push(f.importeTexto.trim() ? 'importe válido' : 'importe');
  else if (superaLoQueQueda(f.importeTexto, f.queda)) r.push('un importe que no supere lo que queda');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.fecha) || f.fecha > hoyIso) r.push('fecha válida');
  if (f.abono === null) r.push('si ya te han abonado el dinero');
  else if (f.abono !== 'TODAVIA_NO' && !f.cuentaAbono) r.push('la cuenta del abono');
  return r;
}

/** Título del origen («Abrigo · Zara») para la tarjeta fija, la revisión y el enlace de vuelta. */
export function tituloOrigen(o: { nota: string | null; tercero: string | null }): string {
  const nota = (o.nota ?? '').trim();
  if (nota && o.tercero) return `${nota} · ${o.tercero}`;
  return nota || o.tercero || 'Compra';
}

/** «Devolución de Abrigo · 20 ago» (D-DEV-06). */
export function textoDevolucionDe(o: { nota: string | null; tercero: string | null; fecha_hecho: string }): string {
  return `${nombreCorto(o)} · ${diaMesIso(o.fecha_hecho)}`;
}

/** Nombre corto del origen: su nota; si no tiene, el tercero; si no, «Compra». */
export function nombreCorto(o: { nota: string | null; tercero: string | null }): string {
  return (o.nota ?? '').trim() || o.tercero || 'Compra';
}

/** ¿La fila es una devolución? */
export function esDevolucion(f: Pick<FilaActividad, 'devolucion_de'>): boolean {
  return !!f.devolucion_de;
}

/** Título de la fila de una devolución («Devolución · Abrigo»); null si no es devolución. */
export function tituloDevolucion(f: Pick<FilaActividad, 'devolucion_de'>): string | null {
  if (!f.devolucion_de) return null;
  return `${ETIQUETA_DEVOLUCION} · ${nombreCorto(f.devolucion_de)}`;
}

/** Importe de la fila de una devolución: sin «+» ni «−» (P-DEV-03). */
export function importeDevolucion(f: Pick<FilaActividad, 'importe_total'>): string {
  return formatearEur(f.importe_total ?? '0');
}

/** Etiqueta bajo el importe (D-DEV-07, P-DEV-03). */
export function etiquetaDevolucion(f: Pick<FilaActividad, 'abono'>): string {
  return f.abono === 'PENDIENTE' ? ETIQUETA_ABONO_PENDIENTE : ETIQUETA_DEVOLUCION;
}

/** ¿Se ofrece «Registrar devolución» en el detalle? Solo en gastos que no son devoluciones (D-DEV-01, A4). */
export function ofreceRegistrarDevolucion(f: Pick<FilaActividad, 'tipo' | 'devolucion_de'>): boolean {
  return f.tipo === 'GASTO' && !f.devolucion_de;
}

/** ¿Se ofrece «Registrar abono» o el swipe «Cobrado»? Solo en devoluciones con el abono pendiente. */
export function ofreceRegistrarAbono(f: Pick<FilaActividad, 'devolucion_de' | 'abono'>): boolean {
  return !!f.devolucion_de && f.abono === 'PENDIENTE';
}
