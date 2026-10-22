// ============================================================
// GAPTO MOBILE 2027
// Fichero: repetir.ts
// Ruta: mobile/src/domain/repetir.ts
// Descripción: «Repetir hoy» de la Actividad (F05-06 M5 SWIPE2; lámina SWIPE-01 v0.2 S8; SWIPE-RULE). Lógica pura: una intención NUEVA con los mismos datos del registro y fecha de hoy, por la ruta de registro de su tipo (gasto pagado, ingreso cobrado o transferencia). Solo se ofrece cuando se puede reconstruir sin dudas con lo que ya devuelve la API: EUR, importe conocido, sin varias líneas, que no sea una devolución, sin maestros desactivados, cuentas habilitadas; gasto o ingreso con UNA cuenta y «Solo mío» (sin reparto); transferencia con origen y destino. Con el detalle: sin magnitudes (sus valores no se repiten a ciegas). Con las capacidades de hoy: la cuenta debe poder pagar, recibir o mover dinero; si no, null y el gesto abre el detalle («Más»). Sin estado ni red.
// Versión: 0.1.0 (F05-06 M5 SWIPE2)
// ============================================================

import type { DetalleActividad, FilaActividad } from '../api/cliente';
import type { CuentaElegible, CuentaPago } from '../api/cliente';
import { formatearEur } from './importe';

/** ¿Se ofrece «Repetir hoy» en esta fila? Solo con los datos de la fila. */
export function repetibleHoy(f: FilaActividad): boolean {
  if (f.moneda !== 'EUR' || f.importe_total === null || f.varias || f.devolucion_de) return false;
  if (f.maestros_desactivados.length > 0 || f.cuentas.some((x) => !x.enabled)) return false;
  if (f.tipo === 'TRANSFERENCIA') {
    return f.cuentas.length === 2 && f.cuentas.some((x) => x.rol === 'ORIGEN') && f.cuentas.some((x) => x.rol === 'DESTINO');
  }
  const rol = f.tipo === 'GASTO' ? 'PAGO' : f.tipo === 'INGRESO' ? 'COBRO' : null;
  if (!rol || f.cuentas.length !== 1 || f.cuentas[0].rol !== rol) return false;
  // Sin reparto: «Solo mío» (todo el importe es tuyo y no queda nada sin indicar).
  return f.estado_reparto === 'COMPLETA' && f.tu_parte === f.importe_total && !f.pendiente;
}

/** Cuentas que hoy pueden hacer cada operación (null = no se pudo leer). */
export interface CapacidadesRepetir {
  pago: CuentaPago[] | null;
  ingreso: CuentaElegible[] | null;
  origen: CuentaElegible[] | null;
  destino: CuentaElegible[] | null;
}

export type RegistroRepetido =
  | { ruta: 'GASTO'; payload: Record<string, unknown> }
  | { ruta: 'INGRESO'; payload: Record<string, unknown> }
  | { ruta: 'TRANSFERENCIA'; payload: Record<string, unknown> };

/** Payload de la intención repetida con fecha de hoy; null si hay dudas (abre el detalle). */
export function componerRepetir(f: FilaActividad, d: Pick<DetalleActividad, 'presupuestable' | 'magnitudes'>, cap: CapacidadesRepetir, hoy: string, intencionId: string): RegistroRepetido | null {
  if (!repetibleHoy(f) || d.magnitudes.length > 0) return null;
  const importe = f.importe_total as string;
  const tiene = (l: { cuenta_id: string }[] | null, id: string) => !!l && l.some((x) => x.cuenta_id === id);
  if (f.tipo === 'TRANSFERENCIA') {
    const origen = f.cuentas.find((x) => x.rol === 'ORIGEN')!.cuenta_id;
    const destino = f.cuentas.find((x) => x.rol === 'DESTINO')!.cuenta_id;
    if (!tiene(cap.origen, origen) || !tiene(cap.destino, destino)) return null;
    return { ruta: 'TRANSFERENCIA', payload: { intencion_id: intencionId, importe, moneda: 'EUR', fecha_hecho: hoy, cuenta_origen_id: origen, cuenta_destino_id: destino, nota: f.nota } };
  }
  const cuenta = f.cuentas[0].cuenta_id;
  const categoria = f.categoria ? { estado: 'CATEGORIA', categoria_id: f.categoria.id, magnitudes: [] } : { estado: 'SIN_CATEGORIA' };
  const comun: Record<string, unknown> = { intencion_id: intencionId, importe, moneda: 'EUR', fecha_hecho: hoy, cuenta_id: cuenta, presupuestable: d.presupuestable, atribucion: 'SOLO_MIO', categoria };
  if (f.tercero) comun.tercero_id = f.tercero.id;
  if (f.contexto) comun.contexto_id = f.contexto.id;
  if (f.tipo === 'INGRESO') {
    if (!tiene(cap.ingreso, cuenta)) return null;
    return { ruta: 'INGRESO', payload: f.nota ? { ...comun, nota: f.nota } : comun };
  }
  const pago = cap.pago?.find((x) => x.cuenta_id === cuenta);
  if (!pago) return null;
  const financiacion = pago.propuesta_financiacion === 'SELF_100'
    ? { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe }
    : { estado: 'NO_DETERMINADA' };
  return { ruta: 'GASTO', payload: { ...(f.nota ? { ...comun, concepto: f.nota } : comun), financiacion } };
}

/** Aviso de «Repetir hoy»: «Repetido hoy: Café · 2,40 €» (corto: el importe no se corta). */
export function textoAvisoRepetir(titulo: string, f: Pick<FilaActividad, 'importe_total'>): string {
  return `Repetido hoy: ${titulo} · ${formatearEur(f.importe_total ?? '0')}`;
}
