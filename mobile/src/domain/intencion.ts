// ============================================================
// GAPTO MOBILE 2027
// Fichero: intencion.ts
// Ruta: mobile/src/domain/intencion.ts
// Descripción: Modelo de la intención VS-01 «gasto ya ocurrido y pagado». Separa: borrador editable (con ORIGEN de cada valor: decisión del usuario, inferido visible o pendiente, mandato §8) y la intención SELLADA (identidad + payload inmutables antes de enviar, F05-00-A).
// v0.2.0 (F05-D003): fecha común gasto/pago editable (≤ hoy) y financiación sellada en la intención (§16.3/§16.4).
// v0.3.0 (F05-01 S6-WIRE+UI (este mandato); F05 §22.2 C01/C07, §26.2 AJ-03, §28.2): estado categorial resuelto OBLIGATORIO (PENDIENTE bloquea; «Sin categoría» es decisión explícita) y magnitudes de la categoría elegida. `sellar` envía `categoria` exactamente en el wire de §28.2: {estado:'SIN_CATEGORIA'} sin `magnitudes`, o {estado:'CATEGORIA', categoria_id, magnitudes:[{magnitud_id, valor}]} con valores canónicos con punto, solo las informadas y nunca `unidad`.
// v0.4.0 (F05-02 B2; F05-D026 E1/E2, lámina REG-PREF R01–R03): `presupuestableOrigen` (USUARIO cuando el usuario lo toca; INFERIDO cuando viene de una preferencia; PENDIENTE sin valor) y el origen VISIBLE de cada propuesta (`cuentaPropuesta`, `presupuestablePropuesta`). La propuesta no cuenta como modificación y se sella como cualquier valor visible; el payload no cambia. Campos nuevos al final del borrador.
// v0.5.0 (F05-03/F05-04 J2 §2.3/§2.4; F05 §46.3 A5/A6/A9, §45.3): campos ADITIVOS al final del borrador: tercero y contexto (con su origen: USUARIO o INFERIDO por la plantilla), magnitudes declaradas «No lo sé» (`desconocidas`: una obligatoria declarada desconocida NO bloquea y viaja en `categoria.desconocidas`), plantilla aplicada y la categoría que puso la plantilla (para no pisar una categoría tocada por el usuario y para «Quitar»). `validar` y `sellar` reciben el tipo (GASTO por defecto: VS-01 sin cambios); el ingreso se sella con `sellarIngreso` (sin concepto ni financiación; nota en §2.7). El payload del gasto solo lleva `tercero_id`, `contexto_id` y `desconocidas` cuando tienen valor: el de VS-01 no cambia.
// Versión: 0.5.0
// ============================================================

import type { MagnitudCategoria } from './categoria';
import { parsearImporte } from './importe';
import { normalizarValorMagnitud, textoMotivoValor } from './magnitud';

export type Origen = 'USUARIO' | 'INFERIDO' | 'PENDIENTE';

/** Origen visible de una propuesta (D-PREF-02): preferencia de la categoría, del tercero o general, única cuenta o plantilla (F05-04). */
export type OrigenPropuestaCampo = 'PREFERENCIA_CATEGORIA' | 'PREFERENCIA_GENERAL' | 'UNICA' | 'PREFERENCIA_TERCERO' | 'PLANTILLA';

/** Plantilla aplicada al borrador (chip «Plantilla: <nombre> ×»). */
export interface PlantillaAplicada {
  id: string;
  nombre: string;
}

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
  // ---- F05-03/F05-04 J2 (aditivos)
  terceroId?: string | null;
  terceroNombre?: string | null;
  /** USUARIO si lo eligió el usuario; INFERIDO si lo puso la plantilla. */
  terceroOrigen?: Origen;
  contextoId?: string | null;
  contextoNombre?: string | null;
  contextoOrigen?: Origen;
  /** magnitud_id declaradas «No lo sé» (A9). */
  desconocidas?: string[];
  plantilla?: PlantillaAplicada | null;
  /** Categoría que puso la plantilla (si el usuario no la cambia, sigue siendo «de tu plantilla»). */
  categoriaPlantillaId?: string | null;
}

export interface MagnitudCapturada {
  magnitud_id: string;
  valor: string;
}

export type CategoriaWire =
  | { estado: 'SIN_CATEGORIA' }
  | { estado: 'CATEGORIA'; categoria_id: string; magnitudes: MagnitudCapturada[]; desconocidas?: string[] };

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
  tercero_id?: string;
  contexto_id?: string;
}

/** Tipo del formulario de registro con categoría (GASTO o INGRESO). */
export type TipoConCategoria = 'GASTO' | 'INGRESO';

/** Payload de POST /v1/intenciones/ingreso-cobrado (F05-04 J2 §1.7). */
export interface PayloadIngresoCobrado {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  cuenta_id: string;
  presupuestable: boolean;
  atribucion: 'SOLO_MIO' | 'SIN_INDICAR';
  categoria: CategoriaWire;
  tercero_id?: string;
  contexto_id?: string;
  nota?: string;
}

export interface IntencionSellada {
  readonly intencionId: string;
  readonly payload: Readonly<PayloadGastoPagado>;
}

export interface IntencionIngresoSellada {
  readonly intencionId: string;
  readonly payload: Readonly<PayloadIngresoCobrado>;
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
    terceroId: null,
    terceroNombre: null,
    terceroOrigen: 'PENDIENTE',
    contextoId: null,
    contextoNombre: null,
    contextoOrigen: 'PENDIENTE',
    desconocidas: [],
    plantilla: null,
    categoriaPlantillaId: null,
  };
}

/** ¿Declarada «No lo sé» y sigue siendo de la categoría elegida? */
export function esDesconocida(b: Pick<Borrador, 'desconocidas'>, magnitudId: string): boolean {
  return (b.desconocidas ?? []).includes(magnitudId);
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

export function validar(b: Borrador, hoyIso: string, tipo: TipoConCategoria = 'GASTO'): Errores {
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
  if (tipo === 'GASTO') {
    if (!b.concepto.trim()) e.concepto = 'Indica el concepto.';
    else if (b.concepto.trim().length > 200) e.concepto = 'Máximo 200 caracteres.';
  }
  if (b.categoria.estado === 'PENDIENTE') e.categoria = 'Elige una categoría o «Sin categoría».';
  else if (b.categoria.estado === 'CATEGORIA') {
    const em: Record<string, string> = {};
    for (const m of b.categoria.magnitudes) {
      const texto = (b.magnitudesTexto[m.magnitud_id] ?? '').trim();
      if (texto === '') {
        if (m.obligatoria && !esDesconocida(b, m.magnitud_id)) em[m.magnitud_id] = `Indica ${m.nombre} (${m.unidad_default}).`;
        continue;
      }
      const r = normalizarValorMagnitud(texto, m.precision_decimales);
      if (!r.ok) em[m.magnitud_id] = textoMotivoValor(r.motivo, m.precision_decimales);
    }
    if (Object.keys(em).length > 0) e.magnitudes = em;
  }
  if (b.presupuestable === null) e.presupuestable = 'Elige si cuenta para el presupuesto.';
  if (!b.cuentaId) e.cuenta = tipo === 'GASTO' ? 'Elige con qué cuenta se pagó.' : 'Elige dónde lo cobraste.';
  else if (tipo === 'GASTO' && b.propuesta === null) e.cuenta = 'Comprobando la cuenta; espera un momento.';
  if (!esFechaIso(b.fechaHecho)) e.fecha = 'Fecha no válida (dd/mm/aaaa).';
  else if (b.fechaHecho > hoyIso) e.fecha = tipo === 'GASTO' ? 'Solo gastos ya ocurridos: la fecha no puede ser futura.' : 'Solo ingresos ya cobrados: la fecha no puede ser futura.';
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
      if (m.obligatoria && !esDesconocida(b, m.magnitud_id)) throw new Error('No se sella sin una magnitud obligatoria');
      continue; // opcional sin valor: desconocida, no viaja
    }
    const r = normalizarValorMagnitud(texto, m.precision_decimales);
    if (!r.ok) throw new Error('No se sella un valor de magnitud inválido');
    magnitudes.push(Object.freeze({ magnitud_id: m.magnitud_id, valor: r.valor }));
  }
  // A9: solo las obligatorias de ESTA categoría declaradas «No lo sé» y sin valor; sin ninguna, el wire de VS-01 no cambia.
  const desconocidas = b.categoria.magnitudes
    .filter((m) => m.obligatoria && esDesconocida(b, m.magnitud_id) && (b.magnitudesTexto[m.magnitud_id] ?? '').trim() === '')
    .map((m) => m.magnitud_id);
  return Object.freeze({
    estado: 'CATEGORIA' as const,
    categoria_id: b.categoria.id,
    magnitudes: Object.freeze(magnitudes) as MagnitudCapturada[],
    ...(desconocidas.length > 0 ? { desconocidas: Object.freeze(desconocidas) as string[] } : {}),
  });
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
    ...maestrosWire(b),
  });
  return Object.freeze({ intencionId, payload });
}

/** Tercero y contexto del wire: solo cuando tienen valor (A5/A6). */
function maestrosWire(b: Borrador): { tercero_id?: string; contexto_id?: string } {
  return {
    ...(b.terceroId ? { tercero_id: b.terceroId } : {}),
    ...(b.contextoId ? { contexto_id: b.contextoId } : {}),
  };
}

/** Sellado del ingreso cobrado (D-DYN-08): sin concepto ni financiación; cuenta «Cobrado en» obligatoria. */
export function sellarIngreso(b: Borrador, intencionId: string, nota: string | null = null): IntencionIngresoSellada {
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok || b.presupuestable === null || !b.cuentaId || b.categoria.estado === 'PENDIENTE') {
    throw new Error('No se sella una intención inválida');
  }
  const payload: PayloadIngresoCobrado = Object.freeze({
    intencion_id: intencionId,
    importe: imp.valor,
    moneda: 'EUR',
    fecha_hecho: b.fechaHecho,
    cuenta_id: b.cuentaId,
    presupuestable: b.presupuestable,
    atribucion: b.soloMio ? 'SOLO_MIO' : 'SIN_INDICAR',
    categoria: categoriaWire(b),
    ...maestrosWire(b),
    ...(nota ? { nota } : {}),
  });
  return Object.freeze({ intencionId, payload });
}
