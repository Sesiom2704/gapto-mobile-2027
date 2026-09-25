// ============================================================
// GAPTO MOBILE 2027
// Fichero: intencion.ts
// Ruta: mobile/src/domain/intencion.ts
// Descripción: Modelo de la intención VS-01 «gasto ya ocurrido y pagado». Separa: borrador editable (con ORIGEN de cada valor: decisión del usuario, inferido visible o pendiente, mandato §8) y la intención SELLADA (identidad + payload inmutables antes de enviar, F05-00-A).
// Versión: 0.1.0
// ============================================================

import { parsearImporte } from './importe';

export type Origen = 'USUARIO' | 'INFERIDO' | 'PENDIENTE';

export interface Borrador {
  importeTexto: string;
  concepto: string;
  presupuestable: boolean | null; // null = pendiente: NUNCA se inventa (R2)
  soloMio: boolean; // affordance explícito «Solo mío»; false = sin indicar (A01)
  cuentaId: string | null;
  cuentaOrigen: Origen; // INFERIDO solo si es la única cuenta disponible (visible)
  fechaHecho: string; // YYYY-MM-DD local; inferido «hoy», visible en pantalla
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
}

export interface IntencionSellada {
  readonly intencionId: string;
  readonly payload: Readonly<PayloadGastoPagado>;
}

export type Errores = Partial<Record<'importe' | 'concepto' | 'presupuestable' | 'cuenta', string>>;

export function borradorInicial(fechaHecho: string): Borrador {
  return {
    importeTexto: '',
    concepto: '',
    presupuestable: null,
    soloMio: false,
    cuentaId: null,
    cuentaOrigen: 'PENDIENTE',
    fechaHecho,
  };
}

export function validar(b: Borrador): Errores {
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
  return e;
}

export function sellar(b: Borrador, intencionId: string): IntencionSellada {
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok || b.presupuestable === null || !b.cuentaId) {
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
  });
  return Object.freeze({ intencionId, payload });
}
