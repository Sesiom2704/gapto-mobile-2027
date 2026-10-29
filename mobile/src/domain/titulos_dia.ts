// ============================================================
// GAPTO MOBILE 2027
// Fichero: titulos_dia.ts
// Ruta: mobile/src/domain/titulos_dia.ts
// Descripción: Títulos de Día a día por tipo de hecho (H-DIAG-02, F05 §70.2). Módulo propio, usado SOLO por ActividadScreen: `actividad.ts` y `registro.ts` (compartidos con el registro de los recorridos de G1) no cambian. Cada tipo de hecho que trae la lista tiene nombre propio: gasto, ingreso y entre cuentas los de siempre; la liquidación de una posición (REEMBOLSO) es «Cobro» si el dinero entra, «Pago» si sale y «Liquidación» sin movimiento; la condonación es «Perdón»; los demás tipos del catálogo, el suyo; un tipo desconocido usa el fallback explícito «Registro». Un cobro de derecho nunca se llama «Ingreso» ni «Entre cuentas». El título de la fila conserva la precedencia única de `tituloFila` (nota > «Tercero · Categoría» > categoría > tercero) y solo sustituye el último recurso «Tipo · importe» cuando el tipo no es de registro.
// Versión: 0.1.0 (F05-D056 decisión 2 de Moisés del 2026-10-29: la corrección de 91cc41f sale de actividad.ts y registro.ts a este módulo)
// ============================================================

import type { FilaActividad } from '../api/cliente';
import { tituloFila } from './actividad';
import { formatearEur } from './importe';
import { NOMBRE_TIPO } from './registro';

/** Fallback explícito del nombre de un tipo sin nombre conocido: nunca «undefined». */
export const NOMBRE_TIPO_DESCONOCIDO = 'Registro';

/** Nombre de los tipos de hecho del catálogo que no son de registro (0150, 0350), salvo REEMBOLSO, que depende del movimiento. */
const NOMBRE_OTROS_TIPOS: Record<string, string> = {
  CONDONACION: 'Perdón',
  GENERACION_DERECHO_OBLIGACION: 'Derecho u obligación',
  COMPRA_FINANCIADA: 'Compra financiada',
  APORTACION_INVERSION: 'Aportación a inversión',
};

const esDeRegistro = (t: string): t is keyof typeof NOMBRE_TIPO => t === 'GASTO' || t === 'INGRESO' || t === 'TRANSFERENCIA';

/** Nombre del tipo de una fila o de un detalle de Día a día. */
export function nombreTipoFila(r: Pick<FilaActividad, 'tipo' | 'cuentas'>): string {
  const t: string = r.tipo;
  if (esDeRegistro(t)) return NOMBRE_TIPO[t];
  if (t === 'REEMBOLSO') {
    const rol = r.cuentas[0]?.rol;
    return rol === 'COBRO' ? 'Cobro' : rol === 'PAGO' ? 'Pago' : 'Liquidación';
  }
  return NOMBRE_OTROS_TIPOS[t] ?? NOMBRE_TIPO_DESCONOCIDO;
}

/** Título de la fila en Día a día: el de `tituloFila`, con el nombre propio del tipo en el último recurso. */
export function tituloFilaDia(r: FilaActividad): string {
  const base = tituloFila(r);
  const t: string = r.tipo;
  if (esDeRegistro(t)) return base;
  const importe = formatearEur(r.importe_total ?? '0');
  // `tituloFila` cae en «<NOMBRE_TIPO[tipo]> · importe», que para un tipo que no es de registro es «undefined · …».
  const ultimoRecurso = `${(NOMBRE_TIPO as Record<string, string | undefined>)[t]} · ${importe}`;
  return base === ultimoRecurso ? `${nombreTipoFila(r)} · ${importe}` : base;
}
