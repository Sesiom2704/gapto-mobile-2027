// ============================================================
// GAPTO MOBILE 2027
// Fichero: titulos_dia.ts
// Ruta: mobile/src/domain/titulos_dia.ts
// Descripción: Títulos de Día a día por tipo de hecho (H-DIAG-02, F05 §70.2). Módulo propio, usado SOLO por ActividadScreen: `actividad.ts` y `registro.ts` (compartidos con el registro de los recorridos de G1) no cambian. Cada tipo de hecho que trae la lista tiene nombre propio: gasto, ingreso y entre cuentas los de siempre; la liquidación de una posición (REEMBOLSO) es «Cobro» si el dinero entra, «Pago» si sale y «Liquidación» sin movimiento; la condonación es «Perdón»; los demás tipos del catálogo, el suyo; un tipo desconocido usa el fallback explícito «Registro». Un cobro de derecho nunca se llama «Ingreso» ni «Entre cuentas». El título de la fila conserva la precedencia única de `tituloFila` (nota > «Tercero · Categoría» > categoría > tercero) y solo sustituye el último recurso «Tipo · importe» cuando el tipo no es de registro.
// Versión: 0.1.0 (F05-D056 decisión 2 de Moisés del 2026-10-29: la corrección de 91cc41f sale de actividad.ts y registro.ts a este módulo)
// Versión: 0.2.0 (F06 T1-F06 B3 · fila patrimonial de Actividad, R1 v0.8 §II.5 y lámina L-6; autorizada en lista cerrada por la decisión de Moisés afaac92d…, solo presentación): los hechos ADQUISICION_PATRIMONIAL y MEJORA_PATRIMONIAL tienen nombre propio («Compra de la propiedad», «Gasto de la compra · <concepto>», «Mejora · <nota>»; en el detalle, «Compra» y «Mejora»). La fuente es el tipo del HECHO (HF-14). Los demás tipos, sus títulos y la precedencia de `tituloFila` no cambian.
// Versión: 0.3.0 (F06 T2-F06 PAG, §1.5 del mandato; lista cerrada de F05 autorizada por el párrafo 3 del literal de PAG (decisión 3 del lote 35, bfbba1e6…); Q-VP-03): una MEJORA_PATRIMONIAL con vivienda en la fila (`propiedad`) se titula «<nota> · <vivienda>» («Reforma · <vivienda>» sin nota). Sin `propiedad`, como antes.
// Versión: 0.4.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1): HD-C2: el rol `PRESTAMO_RECIBIDO` se nombra «Préstamo recibido».
// Versión: 0.5.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-09 / OBS-03 y AJ-06 del 19-11): el concepto que el servidor guarda en el desembolso («PRESTAMO RECIBIDO») se presenta como «Préstamo recibido» (`conceptoPresentado`), también en los hechos ya guardados; el servidor no cambia. AJ-06 (denominación de pagos de cuota): «CUOTA n HIPOTECA» del pago de la cuota se presenta «Cuota n · Hipoteca», como la previsión.
// ============================================================

import type { FilaActividad } from '../api/cliente';
import { tituloFila } from './actividad';
import { formatearEur } from './importe';
import { NOMBRE_TIPO } from './registro';
import { esPatrimonial, NOMBRE_CONCEPTO } from './compra';
import type { ConceptoGasto } from '../api/patrimonio';

/** Fallback explícito del nombre de un tipo sin nombre conocido: nunca «undefined». */
export const NOMBRE_TIPO_DESCONOCIDO = 'Registro';

/** Nombre de los tipos de hecho del catálogo que no son de registro (0150, 0350), salvo REEMBOLSO, que depende del movimiento. */
const NOMBRE_OTROS_TIPOS: Record<string, string> = {
  CONDONACION: 'Perdón',
  GENERACION_DERECHO_OBLIGACION: 'Derecho u obligación',
  COMPRA_FINANCIADA: 'Compra financiada',
  APORTACION_INVERSION: 'Aportación a inversión',
  ADQUISICION_PATRIMONIAL: 'Compra',
  MEJORA_PATRIMONIAL: 'Mejora',
};

/** Fila patrimonial (R1 v0.8 §II.5): nombre por el tipo del HECHO y el concepto que ya trae la fila (`nota` = concepto del hecho). */
export function tituloPatrimonial(r: Pick<FilaActividad, 'tipo' | 'nota' | 'propiedad'>): string | null {
  const t: string = r.tipo;
  if (!esPatrimonial(t)) return null;
  const nota = (r.nota ?? '').trim();
  const vivienda = (r.propiedad?.nombre ?? '').trim();
  if (t === 'MEJORA_PATRIMONIAL' && vivienda) return `${nota || 'Reforma'} · ${vivienda}`;
  if (t === 'MEJORA_PATRIMONIAL') return nota ? `Mejora · ${nota}` : 'Mejora';
  if (nota === 'COMPRA') return 'Compra de la propiedad';
  const concepto = (NOMBRE_CONCEPTO as Record<string, string | undefined>)[nota as ConceptoGasto];
  return concepto ? `Gasto de la compra · ${concepto}` : nota ? `Gasto de la compra · ${nota}` : 'Gasto de la compra';
}

const esDeRegistro = (t: string): t is keyof typeof NOMBRE_TIPO => t === 'GASTO' || t === 'INGRESO' || t === 'TRANSFERENCIA';

/** Nombre del tipo de una fila o de un detalle de Día a día. */
export function nombreTipoFila(r: Pick<FilaActividad, 'tipo' | 'cuentas'>): string {
  const t: string = r.tipo;
  if (esDeRegistro(t)) return NOMBRE_TIPO[t];
  if (r.cuentas[0]?.rol === 'PRESTAMO_RECIBIDO') return 'Préstamo recibido'; // HD-C2: desembolso Hd, por rol
  if (t === 'REEMBOLSO') {
    const rol = r.cuentas[0]?.rol;
    return rol === 'COBRO' ? 'Cobro' : rol === 'PAGO' ? 'Pago' : 'Liquidación';
  }
  return NOMBRE_OTROS_TIPOS[t] ?? NOMBRE_TIPO_DESCONOCIDO;
}

/** Concepto fijo que el alta de la hipoteca guarda en el desembolso (backend `hipotecas/alta.py`). */
export const CONCEPTO_DESEMBOLSO_SERVIDOR = 'PRESTAMO RECIBIDO';
/** Concepto que el pago de una cuota guarda en su hecho (backend `hipotecas/pago.py`). */
const CONCEPTO_PAGO_CUOTA_SERVIDOR = /^CUOTA (\d+) HIPOTECA$/;

/**
 * D-C7-09 (OBS-03): presentación del concepto de un hecho. El del desembolso de la hipoteca llega del servidor en
 * mayúsculas y sin tilde; se muestra «Préstamo recibido». Solo ese texto exacto y, si se conoce el rol de la cuenta,
 * solo con `PRESTAMO_RECIBIDO`. AJ-06: el del pago de la cuota («CUOTA 3 HIPOTECA») se muestra «Cuota 3 · Hipoteca»,
 * como la previsión de esa cuota. Cualquier otro concepto se muestra tal cual.
 */
export function conceptoPresentado(texto: string | null, rol?: string | null): string | null {
  if (texto === null) return null;
  if (texto.trim() === CONCEPTO_DESEMBOLSO_SERVIDOR && (rol === undefined || rol === 'PRESTAMO_RECIBIDO')) return 'Préstamo recibido';
  const cuota = CONCEPTO_PAGO_CUOTA_SERVIDOR.exec(texto.trim());
  if (cuota) return `Cuota ${cuota[1]} · Hipoteca`;
  return texto;
}

/** Título de la fila en Día a día: el de `tituloFila`, con el nombre propio del tipo en el último recurso. */
export function tituloFilaDia(fila: FilaActividad): string {
  const r = { ...fila, nota: conceptoPresentado(fila.nota, fila.cuentas[0]?.rol ?? null) };
  const patrimonial = tituloPatrimonial(r);
  if (patrimonial) return patrimonial;
  const base = tituloFila(r);
  const t: string = r.tipo;
  if (esDeRegistro(t)) return base;
  const importe = formatearEur(r.importe_total ?? '0');
  // `tituloFila` cae en «<NOMBRE_TIPO[tipo]> · importe», que para un tipo que no es de registro es «undefined · …».
  const ultimoRecurso = `${(NOMBRE_TIPO as Record<string, string | undefined>)[t]} · ${importe}`;
  return base === ultimoRecurso ? `${nombreTipoFila(r)} · ${importe}` : base;
}
