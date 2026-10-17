// ============================================================
// GAPTO MOBILE 2027
// Fichero: reparto.ts
// Ruta: mobile/src/domain/reparto.ts
// Descripción: Lógica pura del reparto, el pagador real y las posiciones (F05-06 M3; F05 §51.2 M3, §57 F05-D043; lámina REP v0.2 D-REP-01..09, P-REP-01..06). «Otra persona» pagó: no sale dinero de tus cuentas y la deuda solo nace con «Sí» (D-REP-01/02, INV-04; «No lo sé» no la crea, P-REP-01). «Repartir» conserva siempre el total y deja ver lo que falta, que se puede dejar sin indicar (PARCIAL, G3) y nunca se completa solo (D-REP-03). «A partes iguales» es un botón y el céntimo sobrante va a la última fila (D-REP-04). «¿Te deben su parte?» persona a persona (D-REP-05). Revisión en cuatro bloques (D-REP-06). «Pendiente con» separa lo que te debe y lo que le debes; el neto es una lectura que no salda nada y, con algún saldo desconocido, es «Sin determinar», nunca 0,00 € (D-REP-07/09, OP-20). Cobro y pago con cuenta Gapto; perdonar no mueve dinero (D-REP-08). «Corregir reparto» solo cambia importes de quien ya está (§57.1.1): altas, bajas, invitado → deudor y «Le debo esto» (E1) se ven atenuados con su motivo.
// Versión: 0.1.0 (F05-06 M3 §B1)
// ============================================================

import type { Borrador, CategoriaWire } from './intencion';
import { categoriaWire } from './intencion';
import { formatearEur, parsearImporte } from './importe';

// ------------------------------------------------------------------ wire
export type RespuestaLeDebo = 'SI' | 'NO' | 'NO_LO_SE';
export type RespuestaMeDebe = 'SI' | 'NO';

export type PagadoPor =
  | { tipo: 'CUENTA'; cuenta_id: string }
  | { tipo: 'PERSONA'; tercero_id: string; le_debo: RespuestaLeDebo };

export interface ParteWire {
  tercero_id: string;
  importe?: string | null;
  me_debe?: RespuestaMeDebe | null;
}

export type RepartoWire = { modo: 'SOLO_MIO' } | { modo: 'REPARTIR'; mi_parte?: string | null; partes: ParteWire[] };

export interface PayloadGastoCompartido {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  presupuestable: boolean;
  categoria: CategoriaWire;
  tercero_id?: string;
  nota?: string;
  pagado_por: PagadoPor;
  reparto: RepartoWire;
}

export type TipoPosicion = 'DERECHO_COBRO' | 'OBLIGACION_PAGO';

export interface PosicionCreada {
  entidad_id: string;
  tipo: TipoPosicion;
  tercero_id: string;
  importe: string;
}

export interface ResultadoGastoCompartido {
  intencion_id: string;
  hecho_id: string;
  idempotente: boolean;
  importe: string;
  moneda: string;
  estado_atribucion: 'COMPLETA' | 'PARCIAL' | 'NO_DISPONIBLE';
  tu_parte: string | null;
  movimiento: string | null;
  posiciones: PosicionCreada[];
  aviso: string;
}

export interface PosicionPendiente {
  entidad_id: string;
  entidad_row_version: number;
  tipo: TipoPosicion;
  nombre: string | null;
  saldo: string | null; // null = «Sin determinar»
  estado: 'ACTIVA' | 'CERRADA';
  origen_hecho_id: string | null;
  origen_fecha: string | null;
  origen_concepto: string | null;
  /** Comercio del gasto de origen (C1). */
  origen_tercero?: string | null;
}

export interface PendienteConPersona {
  tercero_id: string;
  nombre: string;
  te_debe: string | null;
  le_debes: string | null;
  neto: string | null;
  neto_estado: 'DETERMINADO' | 'INDETERMINADO' | 'SIN_POSICIONES';
  posiciones: PosicionPendiente[];
}

export interface PayloadCobroPago {
  intencion_id: string;
  importe: string;
  cuenta_id: string;
  fecha: string;
}

export interface PayloadPerdon {
  intencion_id: string;
  importe: string;
  fecha: string;
}

export interface ResultadoPosicion {
  intencion_id: string;
  hecho_id: string;
  entidad_id: string;
  idempotente: boolean;
  importe: string;
  saldo: string | null;
  estado: 'ACTIVA' | 'CERRADA';
  aviso: string;
}

export interface PosicionDeParte {
  entidad_id: string;
  tipo: TipoPosicion;
  saldo: string | null;
}

export interface ParteDeHecho {
  atribucion_id: string;
  es_yo: boolean;
  tercero_id: string | null;
  nombre: string;
  importe: string;
  posicion: PosicionDeParte | null;
}

export type MotivoNoCorregible = 'TIPO_NO_ADMITIDO' | 'ORIGEN_IMPORTADO' | 'NO_ACTIVO' | 'SIN_REPARTO';

export interface RepartoDeHecho {
  hecho_id: string;
  row_version: number;
  importe: string;
  estado_atribucion: 'COMPLETA' | 'PARCIAL' | 'NO_DISPONIBLE';
  corregible: boolean;
  motivo: MotivoNoCorregible | null;
  partes: ParteDeHecho[];
}

export interface PayloadCorregirReparto {
  row_version: number;
  motivo: string;
  partes: { atribucion_id: string; importe: string }[];
}

export interface ResultadoCorreccionReparto {
  hecho_id: string;
  row_version: number;
  tu_parte: string | null;
  posiciones: PosicionCreada[];
  aviso: string;
}

// ------------------------------------------------------------------ textos
export const TEXTO_OTRA_PERSONA = 'Otra persona';
export const TEXTO_NO_SALE_DINERO = 'No sale dinero de tus cuentas';
export const TEXTO_FALTA_SIN_INDICAR =
  'Si no sabes la parte de alguien, déjala vacía: el resto queda «sin indicar» y no se reparte solo.';
export const TEXTO_TE_DEBEN =
  'Indica quién te debe su parte; si alguien estaba invitado, no te debe nada.';
export const TEXTO_NO_LO_SE = 'No se crea ninguna deuda. Si más adelante sabes que se la debes, regístralo aparte.';
export const TEXTO_NETO_NO_SALDA =
  'Es un cálculo: no salda nada. Cada cosa sigue pendiente hasta que registres un cobro, un pago o la perdones.';
export const TEXTO_NETO_SIN_DETERMINAR =
  'Neto: sin determinar. Una de las posiciones no tiene saldo conocido, así que no se puede calcular.';
export const TEXTO_NO_ES_INGRESO = (nombre: string) =>
  `No es un ingreso: ${nombre} te devuelve lo que pagaste por ${nombre}. Si cobras menos, el resto sigue pendiente.`;
export const TEXTO_NO_ES_GASTO = (nombre: string) =>
  `No es un gasto nuevo: pagas a ${nombre} lo que adelantó por ti. Si pagas menos, el resto sigue pendiente.`;
export const TEXTO_SIN_TERCERO_PAGA =
  'No hay opción «Lo pagó otra persona»: que un tercero salde tu deuda no está disponible en esta versión.';
export const TEXTO_ACCIONES =
  'Registrar cobro: te pagó (todo o una parte). Perdonar: ya no te lo debe, sin que entre dinero.';
export const TEXTO_ACCIONES_OBLIGACION =
  'Registrar pago: le pagas (todo o una parte). No hay «Compensar»: el neto no salda nada.';
export const TEXTO_PERDONAR = 'Perdonar no mueve dinero: deja de estar pendiente sin que entre nada en tus cuentas.';
export const TEXTO_SOLO_PERSONAS = 'Solo aparecen terceros de tipo persona. Empresas y organismos no entran en un reparto.';
export const TEXTO_PAT08 =
  'La vista completa de todos tus derechos y obligaciones llega más adelante (Patrimonio).';

/** Cambios que «Corregir reparto» no hace en esta versión (§57.1.1), en lenguaje llano. */
export const EXCLUIDO_CORRECCION = {
  ANADIR_PERSONA: {
    titulo: '+ Añadir persona',
    motivo: 'Todavía no se puede añadir a alguien a un reparto ya registrado.',
  },
  QUITAR_PERSONA: {
    titulo: 'Quitar del reparto',
    motivo: 'Todavía no se puede sacar a alguien de un reparto ya registrado.',
  },
  INVITADO_A_DEUDOR: {
    titulo: 'Ahora sí me lo debe',
    motivo: 'Si alguien estaba invitado, todavía no se puede pasar a que te deba su parte.',
  },
  DEUDOR_A_INVITADO: {
    titulo: 'Ya no me lo debe',
    motivo: 'Para que deje de deberte su parte, usa «Perdonar» en «Pendiente con».',
  },
  LE_DEBO_ESTO: {
    titulo: 'Le debo esto',
    motivo: 'Todavía no se puede crear una deuda después de registrar el gasto.',
  },
} as const;

/** Motivo por el que un gasto no admite «Corregir reparto». */
export const MOTIVO_NO_CORREGIBLE: Record<string, string> = {
  TIPO_NO_ADMITIDO: 'Solo se puede corregir el reparto de un gasto.',
  ORIGEN_IMPORTADO: 'Viene de la versión anterior: su reparto no se puede corregir aquí.',
  NO_ACTIVO: 'Este gasto ya no está activo.',
  SIN_REPARTO: 'Este gasto no tiene reparto entre personas.',
  PARTE_AJENA: 'Una de las partes no es de este gasto. Vuelve a cargar el reparto.',
  SUMA_NO_CUADRA: 'Las partes no suman lo mismo que antes. El total del gasto no cambia.',
};

/** Motivo de un rechazo al guardar la corrección, en lenguaje llano. */
export function motivoRechazoCorreccion(codigo: string, detalle?: Record<string, unknown>): string {
  const motivo = typeof detalle?.motivo === 'string' ? detalle.motivo : null;
  if (codigo === 'REPARTO_NO_CORREGIBLE' && motivo && MOTIVO_NO_CORREGIBLE[motivo]) return MOTIVO_NO_CORREGIBLE[motivo];
  if (codigo === 'CORRECCION_AGREGADA_REQUERIDA') {
    return 'Ese cambio afecta a lo que alguien te debe o le debes de una forma que todavía no se puede corregir aquí.';
  }
  if (codigo === 'REPARTO_NO_DEMOSTRABLE') {
    return 'No se puede comprobar que la deuda corresponde a esa parte, así que no se corrige.';
  }
  if (codigo === 'VERSION_DESFASADA') return 'El gasto ha cambiado mientras lo editabas. Vuelve a cargarlo.';
  if (codigo === 'EXCEDE_SALDO_DEL_DERECHO' || codigo === 'EXCEDE_SALDO_POSICION' || codigo === 'INTEGRIDAD_POSICION_VIOLADA') {
    return 'No puedes dejar una deuda por debajo de lo que ya se ha pagado de ella.';
  }
  return 'No se ha podido corregir el reparto.';
}

/** Motivo de un rechazo al cobrar, pagar o perdonar. */
export function motivoRechazoPosicion(codigo: string): string {
  return (
    {
      EXCEDE_SALDO_DEL_DERECHO: 'Es más de lo que queda pendiente.',
      EXCEDE_SALDO_POSICION: 'Es más de lo que queda pendiente.',
      POSICION_CERRADA: 'Ya no queda nada pendiente.',
      POSICION_NO_ADMITE_OPERACION: 'Esta operación no se puede hacer sobre esta deuda.',
      CUENTA_SIN_CAPACIDAD: 'Esa cuenta no admite esta operación. Elige otra.',
      CUENTA_GAPTO_REQUERIDA: 'Elige una de tus cuentas, Efectivo incluido.',
    } as Record<string, string>
  )[codigo] ?? 'No se ha podido registrar.';
}

// ------------------------------------------------------------------ céntimos
export function centimos(valor: string): number {
  const neg = valor.startsWith('-');
  const [e, d = ''] = valor.replace('-', '').split('.');
  return (neg ? -1 : 1) * (Number(e) * 100 + Number((d + '00').slice(0, 2)));
}

export function decimalDe(cent: number): string {
  const a = Math.abs(cent);
  return `${cent < 0 ? '-' : ''}${Math.floor(a / 100)}.${String(a % 100).padStart(2, '0')}`;
}

/** Texto editable es-ES («14,83») de un decimal canónico. */
export function textoDe(decimal: string): string {
  return decimal.replace('.', ',');
}

/** D-REP-04: total entre n; el céntimo sobrante va a la ÚLTIMA fila (14,83 / 14,83 / 14,84). */
export function partesIguales(total: string, n: number): string[] {
  if (n <= 0) return [];
  const t = centimos(total);
  const base = Math.floor(t / n);
  return Array.from({ length: n }, (_, i) => decimalDe(i === n - 1 ? t - base * (n - 1) : base));
}

// ------------------------------------------------------------------ formulario
/** Una fila del reparto (B2): «Yo» va primero y no tiene tercero. */
export interface FilaReparto {
  terceroId: string | null; // null = yo
  nombre: string;
  importeTexto: string; // vacío = sin indicar
  meDebe: RespuestaMeDebe | null;
}

export interface ResumenReparto {
  repartido: string;
  falta: string;
  sinIndicar: boolean;
  excede: boolean;
  invalidas: number;
}

/** Repartido y falta por repartir (D-REP-03); el total nunca cambia. */
export function resumenReparto(total: string, filas: FilaReparto[]): ResumenReparto {
  let suma = 0;
  let invalidas = 0;
  for (const f of filas) {
    if (!f.importeTexto.trim()) continue;
    const r = parsearImporte(f.importeTexto);
    if (r.ok) suma += centimos(r.valor);
    else invalidas += 1;
  }
  const falta = centimos(total) - suma;
  return { repartido: decimalDe(suma), falta: decimalDe(Math.max(falta, 0)), sinIndicar: falta > 0, excede: falta < 0, invalidas };
}

export function textoFalta(r: ResumenReparto): string {
  return r.sinIndicar ? `${formatearEur(r.falta)} · sin indicar` : formatearEur(r.falta);
}

/** Resumen de la fila «Repartir» del formulario (B1): «3 personas · tú 14,50 €». */
export function resumenFila(filas: FilaReparto[]): string {
  const yo = filas.find((f) => f.terceroId === null);
  const r = yo ? parsearImporte(yo.importeTexto) : null;
  const tu = r && r.ok ? `tú ${formatearEur(r.valor)}` : 'tu parte sin indicar';
  return `${filas.length} personas · ${tu}`;
}

export interface FormularioCompartido {
  modo: 'SOLO_MIO' | 'REPARTIR';
  filas: FilaReparto[];
  pagador: { tipo: 'CUENTA'; cuentaId: string | null } | { tipo: 'PERSONA'; terceroId: string | null; nombre: string | null; leDebo: RespuestaLeDebo | null };
}

/** Pagué yo con una de mis cuentas. */
export function pagueYo(f: FormularioCompartido): boolean {
  return f.pagador.tipo === 'CUENTA';
}

/** Importe propuesto en «Sí, le debo X» (A1): mi parte; con «Solo mío», el total. */
export function miParte(total: string, f: FormularioCompartido): string | null {
  if (f.modo === 'SOLO_MIO') return total;
  const yo = f.filas.find((x) => x.terceroId === null);
  const r = yo ? parsearImporte(yo.importeTexto) : null;
  return r && r.ok ? r.valor : null;
}

/** Lo que falta para revisar; vacío = se puede. */
export function faltaCompartido(total: string, f: FormularioCompartido): string[] {
  const r: string[] = [];
  if (f.modo === 'REPARTIR') {
    const personas = f.filas.filter((x) => x.terceroId !== null);
    if (personas.length === 0) r.push('al menos una persona en el reparto');
    const res = resumenReparto(total, f.filas);
    if (res.invalidas > 0) r.push('importes válidos en el reparto');
    if (res.excede) r.push('un reparto que no supere el total');
    if (pagueYo(f)) {
      for (const p of personas) {
        if (p.meDebe === null) r.push(`si ${p.nombre} te debe su parte`);
        else if (p.meDebe === 'SI' && !p.importeTexto.trim()) r.push(`la parte de ${p.nombre}`);
      }
    }
  }
  if (f.pagador.tipo === 'CUENTA') {
    if (!f.pagador.cuentaId) r.push('con qué cuenta se pagó');
  } else {
    if (!f.pagador.terceroId) r.push('quién lo pagó');
    if (f.pagador.leDebo === null) r.push(`si le debes este dinero a ${f.pagador.nombre ?? 'esa persona'}`);
    else if (f.pagador.leDebo === 'SI' && miParte(total, f) === null) r.push('tu parte, para saber cuánto le debes');
  }
  return r;
}

/** Datos comunes del registro que se conservan al pasar a «Repartir» u «Otra persona». */
export interface BaseCompartido {
  importe: string;
  fechaHecho: string;
  presupuestable: boolean;
  categoria: CategoriaWire;
  categoriaNombre: string;
  terceroId: string | null;
  terceroNombre: string | null;
  nota: string | null;
  cuentaId: string | null;
}

/** Base desde el borrador del registro (ya validado sin la cuenta). Lanza si no es sellable. */
export function baseDesdeBorrador(b: Borrador): BaseCompartido {
  const imp = parsearImporte(b.importeTexto);
  if (!imp.ok || b.presupuestable === null || b.categoria.estado === 'PENDIENTE') throw new Error('Base no sellable');
  const nota = b.concepto.trim();
  return Object.freeze({
    importe: imp.valor,
    fechaHecho: b.fechaHecho,
    presupuestable: b.presupuestable,
    categoria: categoriaWire(b),
    categoriaNombre: b.categoria.estado === 'CATEGORIA' ? b.categoria.nombre : 'Sin categoría',
    terceroId: b.terceroId ?? null,
    terceroNombre: b.terceroNombre ?? null,
    nota: nota || null,
    cuentaId: b.cuentaId,
  });
}

/** Payload sellado de POST /v1/intenciones/gasto-compartido. */
export function componerPayload(base: BaseCompartido, f: FormularioCompartido, intencionId: string): PayloadGastoCompartido {
  if (faltaCompartido(base.importe, f).length > 0) throw new Error('No se sella un gasto compartido incompleto');
  const pagado_por: PagadoPor =
    f.pagador.tipo === 'CUENTA'
      ? { tipo: 'CUENTA', cuenta_id: f.pagador.cuentaId! }
      : { tipo: 'PERSONA', tercero_id: f.pagador.terceroId!, le_debo: f.pagador.leDebo! };
  let reparto: RepartoWire = { modo: 'SOLO_MIO' };
  if (f.modo === 'REPARTIR') {
    const importe = (t: string) => {
      const r = parsearImporte(t);
      return t.trim() && r.ok ? r.valor : null;
    };
    reparto = {
      modo: 'REPARTIR',
      mi_parte: importe(f.filas.find((x) => x.terceroId === null)?.importeTexto ?? ''),
      partes: f.filas
        .filter((x) => x.terceroId !== null)
        .map((x) => ({ tercero_id: x.terceroId!, importe: importe(x.importeTexto), me_debe: pagueYo(f) ? x.meDebe : null })),
    };
  }
  return Object.freeze({
    intencion_id: intencionId,
    importe: base.importe,
    moneda: 'EUR' as const,
    fecha_hecho: base.fechaHecho,
    presupuestable: base.presupuestable,
    categoria: base.categoria,
    ...(base.terceroId ? { tercero_id: base.terceroId } : {}),
    ...(base.nota ? { nota: base.nota } : {}),
    pagado_por,
    reparto,
  });
}

/** D-REP-06 «Quién debe a quién» tal como quedará al registrar. */
export interface LineaDeuda {
  quien: string;
  sentido: 'TE_DEBE' | 'LE_DEBES';
  importe: string;
}

export function deudasPrevistas(base: BaseCompartido, f: FormularioCompartido): LineaDeuda[] {
  if (f.pagador.tipo === 'PERSONA') {
    const mia = miParte(base.importe, f);
    return f.pagador.leDebo === 'SI' && mia ? [{ quien: f.pagador.nombre ?? '', sentido: 'LE_DEBES', importe: mia }] : [];
  }
  if (f.modo !== 'REPARTIR') return [];
  return f.filas
    .filter((x) => x.terceroId !== null && x.meDebe === 'SI')
    .map((x) => {
      const r = parsearImporte(x.importeTexto);
      return { quien: x.nombre, sentido: 'TE_DEBE' as const, importe: r.ok ? r.valor : '0.00' };
    });
}

// ------------------------------------------------------------------ pendiente con
/** Neto (D-REP-07/09): nunca 0,00 € si algún saldo es desconocido. */
export function textoNeto(p: Pick<PendienteConPersona, 'neto' | 'neto_estado'>): string {
  if (p.neto_estado === 'INDETERMINADO' || p.neto === null) return TEXTO_NETO_SIN_DETERMINAR;
  return `Neto: ${formatearEur(p.neto)}. ${TEXTO_NETO_NO_SALDA}`;
}

/** Origen de una posición (C1): la nota del gasto o, si no tiene, su comercio; segunda línea con el comercio y la fecha. */
export function origenPosicion(x: Pick<PosicionPendiente, 'origen_concepto' | 'origen_tercero' | 'nombre'>): string {
  return (x.origen_concepto ?? '').trim() || x.origen_tercero || x.nombre || 'Sin origen';
}

export function textoSaldo(saldo: string | null): string {
  return saldo === null ? 'Sin determinar' : formatearEur(saldo);
}

/** ¿Hay algo pendiente con la persona? (E5: la fila solo aparece entonces). */
export function hayPendiente(p: Pick<PendienteConPersona, 'posiciones'>): boolean {
  return p.posiciones.some((x) => x.estado === 'ACTIVA');
}

export function activasDe(p: PendienteConPersona, tipo: TipoPosicion): PosicionPendiente[] {
  return p.posiciones.filter((x) => x.estado === 'ACTIVA' && x.tipo === tipo);
}

/** Lo que falta para cobrar o pagar (C3/E8). */
export function faltaCobroPago(
  f: { importeTexto: string; cuentaId: string | null; fecha: string; conCuenta: boolean },
  saldo: string | null,
  hoyIso: string,
): string[] {
  const r: string[] = [];
  const imp = parsearImporte(f.importeTexto);
  if (!imp.ok) r.push(f.importeTexto.trim() ? 'importe válido' : 'importe');
  else if (saldo !== null && centimos(imp.valor) > centimos(saldo)) r.push('un importe que no supere lo pendiente');
  if (f.conCuenta && !f.cuentaId) r.push('la cuenta');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.fecha) || f.fecha > hoyIso) r.push('fecha válida');
  return r;
}

// ------------------------------------------------------------------ corregir reparto
export interface CambioParte {
  atribucionId: string;
  nombre: string;
  antes: string;
  despues: string;
  posicion: PosicionDeParte | null;
}

/** Impacto de la corrección (E6): solo las partes que cambian, y la deuda que cambia con ellas. */
export function cambiosCorreccion(r: RepartoDeHecho, textos: Record<string, string>): CambioParte[] {
  const cambios: CambioParte[] = [];
  for (const p of r.partes) {
    const t = textos[p.atribucion_id];
    const imp = t !== undefined ? parsearImporte(t) : null;
    if (!imp || !imp.ok || imp.valor === p.importe) continue;
    cambios.push({ atribucionId: p.atribucion_id, nombre: p.es_yo ? 'Tú' : p.nombre, antes: p.importe, despues: imp.valor, posicion: p.posicion });
  }
  return cambios;
}

/** Lo que falta para revisar la corrección; vacío = se puede. */
export function faltaCorreccion(r: RepartoDeHecho, textos: Record<string, string>, motivo: string): string[] {
  const falta: string[] = [];
  let antes = 0;
  let despues = 0;
  let invalidas = 0;
  for (const p of r.partes) {
    antes += centimos(p.importe);
    const t = textos[p.atribucion_id] ?? textoDe(p.importe);
    const imp = parsearImporte(t);
    if (imp.ok) despues += centimos(imp.valor);
    else invalidas += 1;
  }
  if (invalidas > 0) falta.push('importes válidos (para quitar a alguien no se pone 0)');
  else if (antes !== despues) falta.push(`que las partes sumen lo mismo que antes (${formatearEur(decimalDe(antes))})`);
  if (cambiosCorreccion(r, textos).length === 0) falta.push('algún cambio');
  if (!motivo.trim()) falta.push('el motivo');
  return falta;
}

export function componerCorreccion(r: RepartoDeHecho, textos: Record<string, string>, motivo: string): PayloadCorregirReparto {
  if (faltaCorreccion(r, textos, motivo).length > 0) throw new Error('No se sella una corrección incompleta');
  return Object.freeze({
    row_version: r.row_version,
    motivo: motivo.trim(),
    partes: cambiosCorreccion(r, textos).map((c) => ({ atribucion_id: c.atribucionId, importe: c.despues })),
  });
}

/** Diferencia de tu gasto atribuido tras la corrección («+7,75 €»). */
export function deltaTuParte(cambios: CambioParte[], r: RepartoDeHecho): string | null {
  const yo = r.partes.find((p) => p.es_yo);
  const c = yo ? cambios.find((x) => x.atribucionId === yo.atribucion_id) : undefined;
  if (!c) return null;
  const d = centimos(c.despues) - centimos(c.antes);
  return `${d > 0 ? '+' : ''}${formatearEur(decimalDe(d))}`;
}

/** Texto de la deuda que cambia con la parte (E6). */
export function textoCambioDeuda(c: CambioParte): string | null {
  if (!c.posicion) return null;
  const que = c.posicion.tipo === 'DERECHO_COBRO' ? `Lo que ${c.nombre} te debe` : `Lo que le debes a ${c.nombre}`;
  return `${que}: ${formatearEur(c.antes)} → ${formatearEur(c.despues)}`;
}
