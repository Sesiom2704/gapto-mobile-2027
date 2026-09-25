// ============================================================
// GAPTO MOBILE 2027
// Fichero: intencion.ts
// Ruta: mobile/src/domain/intencion.ts
// Descripción: Modelo de la intención VS-01 «gasto ya ocurrido y pagado». Separa: borrador editable (con ORIGEN de cada valor: decisión del usuario, inferido visible o pendiente, mandato §8) y la intención SELLADA (identidad + payload inmutables antes de enviar, F05-00-A).
// v0.2.0 (F05-D003): fecha común gasto/pago editable (≤ hoy) y financiación sellada en la intención (§16.3/§16.4).
// Versión: 0.2.0
// ============================================================

import { parsearImporte } from './importe';

export type Origen = 'USUARIO' | 'INFERIDO' | 'PENDIENTE';

/** Propuesta del servidor para la cuenta y fecha elegidas (§16.4). */
export type PropuestaFinanciacion = 'SELF_100' | 'NO_DETERMINADA';

export type Financiacion =
  | {
      estado: 'PROPUESTA_ACEPTADA';
      actor: 'SELF';
      criterio: 'PARTICIPACION_CUENTA';
      porcentaje: '100';
      importe: string;
    }
  | { estado: 'NO_DETERMINADA' };

export interface Borrador {
  importeTexto: string;
  concepto: string;
  presupuestable: boolean | null; // null = pendiente: NUNCA se inventa (R2)
  soloMio: boolean; // affordance explícito «Solo mío»; false = sin indicar (A01)
  cuentaId: string | null;
  cuentaOrigen: Origen; // INFERIDO solo si es la única cuenta disponible (visible)
  fechaHecho: string; // YYYY-MM-DD local: fecha COMÚN del gasto y del pago (§16.3)
  fechaOrigen: Origen; // INFERIDO = «Hoy» propuesto y visible; USUARIO si la cambia
  /** Propuesta vigente para cuentaId + fechaHecho; null = aún no conocida. */
  propuesta: PropuestaFinanciacion | null;
  /** El usuario rechaza la propuesta visible («No es así»): NO_DETERMINADA. */
  propuestaRechazada: boolean;
}

export interface PayloadGastoPagado {
  intencion_id: string;
  concepto: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  cuenta_id: string;
  presupuestable: boolean;
  atribucion: 'SOLO_MIO' | 'SIN_INDICAR';
  financiacion: Financiacion;
}

export interface IntencionSellada {
  readonly intencionId: string;
  readonly payload: Readonly<PayloadGastoPagado>;
}

export type Errores = Partial<Record<'importe' | 'concepto' | 'presupuestable' | 'cuenta' | 'fecha', string>>;

export function borradorInicial(fechaHecho: string): Borrador {
  return {
    importeTexto: '',
    concepto: '',
    presupuestable: null,
    soloMio: false,
    cuentaId: null,
    cuentaOrigen: 'PENDIENTE',
    fechaHecho,
    fechaOrigen: 'INFERIDO',
    propuesta: null,
    propuestaRechazada: false,
  };
}

const ISO = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** Fecha ISO válida del calendario (rechaza 2026-02-30). */
export function esFechaIso(s: string): boolean {
  if (!ISO.test(s)) return false;
  const [a, m, d] = s.split('-').map(Number);
  const f = new Date(a, m - 1, d);
  return f.getFullYear() === a && f.getMonth() === m - 1 && f.getDate() === d;
}

/** Financiación que se sellará: la propuesta self 100 % se acepta implícitamente
 *  (visible) salvo que el usuario la rechace; cualquier otra cosa es NO_DETERMINADA. */
export function financiacionDe(b: Borrador, importe: string): Financiacion {
  if (b.propuesta === 'SELF_100' && !b.propuestaRechazada) {
    return { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe };
  }
  return { estado: 'NO_DETERMINADA' };
}

export function validar(b: Borrador, hoyIso: string): Errores {
  const e: Errores = {};
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok) {
    e.importe = {
      VACIO: 'Indica el importe.',
      FORMATO: 'Importe no válido.',
      NO_POSITIVO: 'El importe debe ser mayor que 0.',
      DECIMALES: 'Máximo dos decimales.',
    }[imp.motivo];
  }
  if (!b.concepto.trim()) e.concepto = 'Indica el concepto.';
  else if (b.concepto.trim().length > 200) e.concepto = 'Máximo 200 caracteres.';
  if (b.presupuestable === null) e.presupuestable = 'Elige si cuenta para el presupuesto.';
  if (!b.cuentaId) e.cuenta = 'Elige con qué cuenta se pagó.';
  else if (b.propuesta === null) e.cuenta = 'Comprobando la cuenta; espera un momento.';
  if (!esFechaIso(b.fechaHecho)) e.fecha = 'Fecha no válida (dd/mm/aaaa).';
  else if (b.fechaHecho > hoyIso) e.fecha = 'Solo gastos ya ocurridos: la fecha no puede ser futura.';
  return e;
}

export function sellar(b: Borrador, intencionId: string): IntencionSellada {
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok || b.presupuestable === null || !b.cuentaId || b.propuesta === null) {
    throw new Error('No se sella una intención inválida');
  }
  const payload: PayloadGastoPagado = Object.freeze({
    intencion_id: intencionId,
    concepto: b.concepto.trim(),
    importe: imp.valor,
    moneda: 'EUR',
    fecha_hecho: b.fechaHecho,
    cuenta_id: b.cuentaId,
    presupuestable: b.presupuestable,
    atribucion: b.soloMio ? 'SOLO_MIO' : 'SIN_INDICAR',
    financiacion: Object.freeze(financiacionDe(b, imp.valor)),
  });
  return Object.freeze({ intencionId, payload });
}
