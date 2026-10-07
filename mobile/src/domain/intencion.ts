// ============================================================
// GAPTO MOBILE 2027
// Fichero: intencion.ts
// Ruta: mobile/src/domain/intencion.ts
// Descripción: Modelo de la intención VS-01 «gasto ya ocurrido y pagado». Separa: borrador editable (con ORIGEN de cada valor: decisión del usuario, inferido visible o pendiente, mandato §8) y la intención SELLADA (identidad + payload inmutables antes de enviar, F05-00-A).
// v0.2.0 (F05-D003): fecha común gasto/pago editable (≤ hoy) y financiación sellada en la intención (§16.3/§16.4).
// v0.3.0 (F05-01 S6-WIRE+UI (este mandato); F05 §22.2 C01/C07, §26.2 AJ-03, §28.2): estado categorial resuelto OBLIGATORIO (PENDIENTE bloquea; «Sin categoría» es decisión explícita) y magnitudes de la categoría elegida. `sellar` envía `categoria` exactamente en el wire de §28.2: {estado:'SIN_CATEGORIA'} sin `magnitudes`, o {estado:'CATEGORIA', categoria_id, magnitudes:[{magnitud_id, valor}]} con valores canónicos con punto, solo las informadas y nunca `unidad`.
// v0.4.0 (F05-02 B2; F05-D026 E1/E2, lámina REG-PREF R01–R03): `presupuestableOrigen` (USUARIO cuando el usuario lo toca; INFERIDO cuando viene de una preferencia; PENDIENTE sin valor) y el origen VISIBLE de cada propuesta (`cuentaPropuesta`, `presupuestablePropuesta`). La propuesta no cuenta como modificación y se sella como cualquier valor visible; el payload no cambia. Campos nuevos al final del borrador.
// Versión: 0.4.0
// ============================================================

import type { MagnitudCategoria } from './categoria';
import { parsearImporte } from './importe';
import { normalizarValorMagnitud, textoMotivoValor } from './magnitud';

export type Origen = 'USUARIO' | 'INFERIDO' | 'PENDIENTE';

/** Origen visible de una propuesta (D-PREF-02): preferencia de la categoría, preferencia general o única cuenta. */
export type OrigenPropuestaCampo = 'PREFERENCIA_CATEGORIA' | 'PREFERENCIA_GENERAL' | 'UNICA';

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

/** Estado categorial del borrador (C01): sin preselección; PENDIENTE bloquea el registro. */
export type SeleccionCategoria =
  | { estado: 'PENDIENTE' }
  | { estado: 'SIN_CATEGORIA' }
  | {
      estado: 'CATEGORIA';
      id: string;
      nombre: string;
      ruta: string; // «Todas › Hogar»
      icon_key: string | null;
      magnitudes: MagnitudCategoria[]; // las que se piden (habilitadas), en el orden de la API
    };

export interface Borrador {
  importeTexto: string;
  concepto: string;
  presupuestable: boolean | null; // null = pendiente: NUNCA se inventa (R2)
  soloMio: boolean; // affordance explícito «Solo mío»; false = sin indicar (A01)
  cuentaId: string | null;
  cuentaOrigen: Origen; // INFERIDO = propuesta visible del resolver (preferencia o única elegible)
  fechaHecho: string; // YYYY-MM-DD local: fecha COMÚN del gasto y del pago (§16.3)
  fechaOrigen: Origen; // INFERIDO = «Hoy» propuesto y visible; USUARIO si la cambia
  /** Propuesta vigente para cuentaId + fechaHecho; null = aún no conocida. */
  propuesta: PropuestaFinanciacion | null;
  /** El usuario rechaza la propuesta visible («No es así»): NO_DETERMINADA. */
  propuestaRechazada: boolean;
  categoria: SeleccionCategoria;
  /** Texto escrito por magnitud_id; ausente o vacío = desconocido (nunca cero). */
  magnitudesTexto: Record<string, string>;
  /** Origen visible de la cuenta propuesta (solo con cuentaOrigen INFERIDO). */
  cuentaPropuesta: OrigenPropuestaCampo | null;
  /** USUARIO si el usuario lo eligió; INFERIDO si viene de una preferencia (E1); PENDIENTE sin valor. */
  presupuestableOrigen: Origen;
  /** Origen visible de `presupuestable` propuesto (solo con presupuestableOrigen INFERIDO). */
  presupuestablePropuesta: OrigenPropuestaCampo | null;
}

export interface MagnitudCapturada {
  magnitud_id: string;
  valor: string;
}

export type CategoriaWire =
  | { estado: 'SIN_CATEGORIA' }
  | { estado: 'CATEGORIA'; categoria_id: string; magnitudes: MagnitudCapturada[] };

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
  categoria: CategoriaWire;
}

export interface IntencionSellada {
  readonly intencionId: string;
  readonly payload: Readonly<PayloadGastoPagado>;
}

export type Errores = Partial<Record<'importe' | 'concepto' | 'categoria' | 'presupuestable' | 'cuenta' | 'fecha', string>> & {
  /** Error por magnitud_id (obligatoria vacía o valor no válido). */
  magnitudes?: Record<string, string>;
};

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
    categoria: { estado: 'PENDIENTE' },
    magnitudesTexto: {},
    cuentaPropuesta: null,
    presupuestableOrigen: 'PENDIENTE',
    presupuestablePropuesta: null,
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
  if (b.categoria.estado === 'PENDIENTE') e.categoria = 'Elige una categoría o «Sin categoría».';
  else if (b.categoria.estado === 'CATEGORIA') {
    const em: Record<string, string> = {};
    for (const m of b.categoria.magnitudes) {
      const texto = (b.magnitudesTexto[m.magnitud_id] ?? '').trim();
      if (texto === '') {
        if (m.obligatoria) em[m.magnitud_id] = `Indica ${m.nombre} (${m.unidad_default}).`;
        continue;
      }
      const r = normalizarValorMagnitud(texto, m.precision_decimales);
      if (!r.ok) em[m.magnitud_id] = textoMotivoValor(r.motivo, m.precision_decimales);
    }
    if (Object.keys(em).length > 0) e.magnitudes = em;
  }
  if (b.presupuestable === null) e.presupuestable = 'Elige si cuenta para el presupuesto.';
  if (!b.cuentaId) e.cuenta = 'Elige con qué cuenta se pagó.';
  else if (b.propuesta === null) e.cuenta = 'Comprobando la cuenta; espera un momento.';
  if (!esFechaIso(b.fechaHecho)) e.fecha = 'Fecha no válida (dd/mm/aaaa).';
  else if (b.fechaHecho > hoyIso) e.fecha = 'Solo gastos ya ocurridos: la fecha no puede ser futura.';
  return e;
}

/** Dimensión categorial sellada, en el wire de §28.2. Lanza si no es sellable. */
export function categoriaWire(b: Borrador): CategoriaWire {
  if (b.categoria.estado === 'PENDIENTE') throw new Error('No se sella sin estado categorial');
  if (b.categoria.estado === 'SIN_CATEGORIA') return Object.freeze({ estado: 'SIN_CATEGORIA' as const });
  const magnitudes: MagnitudCapturada[] = [];
  for (const m of b.categoria.magnitudes) {
    const texto = (b.magnitudesTexto[m.magnitud_id] ?? '').trim();
    if (texto === '') {
      if (m.obligatoria) throw new Error('No se sella sin una magnitud obligatoria');
      continue; // opcional sin valor: desconocida, no viaja
    }
    const r = normalizarValorMagnitud(texto, m.precision_decimales);
    if (!r.ok) throw new Error('No se sella un valor de magnitud inválido');
    magnitudes.push(Object.freeze({ magnitud_id: m.magnitud_id, valor: r.valor }));
  }
  return Object.freeze({ estado: 'CATEGORIA' as const, categoria_id: b.categoria.id, magnitudes: Object.freeze(magnitudes) as MagnitudCapturada[] });
}

export function sellar(b: Borrador, intencionId: string): IntencionSellada {
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok || b.presupuestable === null || !b.cuentaId || b.propuesta === null || b.categoria.estado === 'PENDIENTE') {
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
    categoria: categoriaWire(b),
  });
  return Object.freeze({ intencionId, payload });
}
