// ============================================================
// GAPTO MOBILE 2027
// Fichero: quien_pago.ts
// Ruta: mobile/src/domain/quien_pago.ts
// Descripción: T2-F06 PAG · lógica pura de «¿Quién pagó?» de una reforma o mejora de una propiedad (mandato PAG §1.1 contrato operativo único y §1.4; anexo B §10; L-08; Q-PAG-01..10).
//   - Opciones: «Yo, todo» (P1, cuenta solo tuya), «Cada uno su parte» (P2: de tu cuenta sale solo tu parte; cada cotitular pone la suya por fuera), «<Cotitular>, todo» (P3: no sale nada de tus cuentas), «Otra combinación» (mixto, SOLO con dos titulares: lo que puso cada uno) y «Desde una cuenta compartida» (vía de B3, 8ter: sin preselección y con el importe a mano).
//   - Signo (§1.1.2): saldo_c = pagado_c − parte_c. Si el cotitular pagó menos que su parte, te debe la diferencia (ME_DEBE → derecho de cobro); si pagó más, le debes (LE_DEBO → obligación de pago).
//   - Deuda propuesta (L-08, DM-07): con desequilibrio se propone ME_DEBE o LE_DEBO por el desequilibrio completo, PRESELECCIONADO, visible y desmarcable en los dos sentidos; el importe se puede bajar (deuda parcial, 0 < importe ≤ propuesto). Desmarcar = NADA (invitación o ya saldado). Nunca frente a una EMPRESA, nunca con «No lo sé» y nunca entre terceros: con tres o más titulares solo te deben a ti (P1) o les debes tú a quien pagó (P3), dentro de lo que pagaste de más o de menos.
//   - Confirmación visible (§1.1.7): por persona, su parte, lo que puso y la posición que se crea («<X> te debe N €» / «Le debes N € a <X>») o «No queda nada pendiente». `posiciones_confirmadas` = exactamente lo mostrado (el servidor lo verifica y nunca infiere).
//   - Wire de C-MEJ-01 v2: `pagos[]` (YO con cuenta, o el actor del cotitular sin cuenta) y `saldos[]` (uno por cotitular del reparto; vacío con «No lo sé»).
//   Código de partida: laboratorio lab-t2 05dec08 (quien_pago.ts 0.1.0-lab), copia revisada; añadidos: mixto bilateral, LE_DEBO preseleccionado, deuda parcial editable, confirmación por posición y exclusiones.
// Versión: 0.1.0 (F06 T2-F06 PAG N1)
// Versión: 0.1.1 (F06 T2-F06 ajuste N3 · KO-1 de la prueba en iPhone, reclasificado como KO de texto; decisión de Moisés del 2026-11-15,
//   F06-00_Decisiones_Moises_2026-11-15_KO1_reclasificacion_N3_v1.0.md, 022b115a…): la falta de cuenta solo tuya se explica por la fecha
//   y remite a «Desde una cuenta compartida». Sin cambio de comportamiento.
// ============================================================

import type { ParteEfectiva } from './gasto_propiedad';
import { repartirImporte } from './gasto_propiedad';
import { formatearEur, parsearImporte } from './importe';

export type ModoPago = 'YO_TODO' | 'CADA_UNO' | 'COTITULAR_TODO' | 'MIXTO' | 'COMPARTIDA';
export type Sentido = 'ME_DEBE' | 'LE_DEBO';
export interface EleccionPago {
  modo: ModoPago | null;
  /** Cotitular que pagó todo (COTITULAR_TODO). */
  pagadorId: string | null;
  /** «Otra combinación» (MIXTO, dos titulares): lo que pusiste tú y lo que puso el otro titular. */
  mio: string;
  suyo: string;
}
/** Elección del usuario sobre una deuda propuesta: marcada (preseleccionada) y su importe (editable a la baja). */
export interface DeudaElegida { marcada: boolean; importe: string }
export interface PagoWire { pagador: string; cuenta_id?: string; importe: string }
export interface SaldoWire { actor_id: string; sentido: 'ME_DEBE' | 'LE_DEBO' | 'NADA'; importe?: string }
export interface PosicionWire { actor_id: string; tipo: 'DERECHO_COBRO' | 'OBLIGACION_PAGO'; importe: string }
export interface Propuesta { actor_id: string; nombre: string; sentido: Sentido; maximo: string }

export const TEXTO_QUIEN_PAGO = '¿Quién pagó?';
export const TEXTO_NADA_PENDIENTE = 'No queda nada pendiente';
export const TEXTO_SIN_MOVIMIENTO = 'No sale dinero de tus cuentas: lo pagó otra persona.';
export const TEXTO_NO_ES_MOVIMIENTO = 'Lo que se debe no es un movimiento: tus saldos y tu liquidez no cambian.';
export const TEXTO_EMPRESA = 'una empresa no genera aquí deudas';
export const TEXTO_NO_LO_SE = 'Sin reparto («No lo sé») no se puede calcular quién debe a quién: no se anota ninguna deuda.';
export const TEXTO_DESMARCAR = 'Si no te debe nada (ya está saldado o le invitas), desmárcalo.';
export const TEXTO_DESMARCAR_LE = 'Si no le debes nada (ya está saldado), desmárcalo.';

export const pagoInicial = (): EleccionPago => ({ modo: null, pagadorId: null, mio: '', suyo: '' });

const cent = (t: string): number => {
  const p = parsearImporte(t);
  return p.ok ? Math.round(Number(p.valor) * 100) : NaN;
};
const texto2 = (c: number) => (c / 100).toFixed(2);
const importeTexto = (t: string) => {
  const p = parsearImporte(t);
  return p.ok ? p.valor : t;
};
const nombreDe = (x: { nombre: string | null; yo?: boolean }) => (x.yo ? 'Tú' : x.nombre ?? 'Otra persona');

export interface Cotitular { actor_id: string; nombre: string | null }

/** Opciones visibles de «¿Quién pagó?». «Otra combinación» solo con dos titulares (yo y un cotitular). */
export function opcionesPago(cotitulares: Cotitular[]): { clave: string; etiqueta: string; modo: ModoPago; pagadorId: string | null }[] {
  const salida: { clave: string; etiqueta: string; modo: ModoPago; pagadorId: string | null }[] = [
    { clave: 'yo', etiqueta: 'Yo, todo', modo: 'YO_TODO', pagadorId: null },
  ];
  if (cotitulares.length > 0) salida.push({ clave: 'cada-uno', etiqueta: 'Cada uno su parte', modo: 'CADA_UNO', pagadorId: null });
  for (const x of cotitulares) salida.push({ clave: `cotitular-${x.actor_id}`, etiqueta: `${x.nombre ?? 'Otra persona'}, todo`, modo: 'COTITULAR_TODO', pagadorId: x.actor_id });
  if (cotitulares.length === 1) salida.push({ clave: 'mixto', etiqueta: 'Otra combinación', modo: 'MIXTO', pagadorId: cotitulares[0].actor_id });
  salida.push({ clave: 'compartida', etiqueta: 'Desde una cuenta compartida', modo: 'COMPARTIDA', pagadorId: null });
  return salida;
}

/** Hace falta una cuenta mía si pago algo (o si se paga desde la cuenta compartida). */
export const necesitaCuenta = (e: EleccionPago) => e.modo !== null && e.modo !== 'COTITULAR_TODO';

/** Lo que pagó cada actor (yo incluido) según la elección y el reparto. */
export function pagadoPor(e: EleccionPago, importe: string, partes: ParteEfectiva[], yoId: string | null): Record<string, number> {
  const total = cent(importe);
  const rep = repartirImporte(importe, partes);
  const yo = yoId ?? partes.find((x) => x.yo)?.actor_id ?? 'YO';
  if (e.modo === 'YO_TODO' || e.modo === 'COMPARTIDA') return { [yo]: total };
  if (e.modo === 'COTITULAR_TODO' && e.pagadorId) return { [e.pagadorId]: total };
  if (e.modo === 'CADA_UNO') return Object.fromEntries(partes.map((x) => [x.actor_id, cent(rep[x.actor_id] ?? '0')]));
  if (e.modo === 'MIXTO') return { [yo]: cent(e.mio), ...(e.pagadorId ? { [e.pagadorId]: cent(e.suyo) } : {}) };
  return {};
}

/**
 * Deudas que se proponen (L-08): por el desequilibrio completo, solo frente a una PERSONA del reparto, y siempre entre tú y
 * cada cotitular (nunca entre terceros: se recorta a lo que pagaste de más o de menos). Con «No lo sé», P2 o la cuenta
 * compartida (que va por la vía de B3), ninguna.
 */
export function propuestas(e: EleccionPago, importe: string, partes: ParteEfectiva[]): Propuesta[] {
  if (partes.length === 0 || e.modo === null || e.modo === 'CADA_UNO' || e.modo === 'COMPARTIDA') return [];
  if (Number.isNaN(cent(importe))) return [];
  const yo = partes.find((x) => x.yo);
  if (!yo) return [];
  const rep = repartirImporte(importe, partes);
  const pagado = pagadoPor(e, importe, partes, yo.actor_id);
  if (Object.values(pagado).some((v) => Number.isNaN(v))) return [];
  const miSaldo = (pagado[yo.actor_id] ?? 0) - cent(rep[yo.actor_id] ?? '0');
  let margenMe = Math.max(miSaldo, 0);
  let margenLe = Math.max(-miSaldo, 0);
  const out: Propuesta[] = [];
  for (const x of partes.filter((p) => !p.yo).sort((a, z) => (a.actor_id < z.actor_id ? -1 : 1))) {
    if (x.naturaleza !== 'PERSONA') continue;
    const saldo = (pagado[x.actor_id] ?? 0) - cent(rep[x.actor_id] ?? '0');
    if (saldo < 0 && margenMe > 0) {
      const v = Math.min(-saldo, margenMe);
      margenMe -= v;
      out.push({ actor_id: x.actor_id, nombre: nombreDe(x), sentido: 'ME_DEBE', maximo: texto2(v) });
    } else if (saldo > 0 && margenLe > 0) {
      const v = Math.min(saldo, margenLe);
      margenLe -= v;
      out.push({ actor_id: x.actor_id, nombre: nombreDe(x), sentido: 'LE_DEBO', maximo: texto2(v) });
    }
  }
  return out;
}

/** Estado inicial de las deudas propuestas: todas PRESELECCIONADAS por su importe completo (L-08), en los dos sentidos. */
export function deudasIniciales(ps: Propuesta[]): Record<string, DeudaElegida> {
  return Object.fromEntries(ps.map((x) => [x.actor_id, { marcada: true, importe: x.maximo }]));
}

/** Conserva lo que el usuario tocó y añade las propuestas nuevas preseleccionadas; quita las que ya no se proponen. */
export function ajustarDeudas(actual: Record<string, DeudaElegida>, ps: Propuesta[], tocadas: boolean): Record<string, DeudaElegida> {
  if (!tocadas) return deudasIniciales(ps);
  const ini = deudasIniciales(ps);
  return Object.fromEntries(ps.map((x) => [x.actor_id, actual[x.actor_id] ?? ini[x.actor_id]]));
}

/** Faltas de «¿Quién pagó?» y de la deuda (el envío exige resolverlas). */
export function faltasPago(e: EleccionPago, importe: string, partes: ParteEfectiva[], noLoSe: boolean, cuentaId: string | null,
  cuentaEsCompartida: boolean, deudas: Record<string, DeudaElegida>, numTitulares: number): string[] {
  const r: string[] = [];
  if (e.modo === null) return ['quién pagó'];
  if (e.modo === 'CADA_UNO' && (noLoSe || partes.filter((x) => !x.yo).length === 0)) r.push('un reparto para «Cada uno su parte»');
  if (e.modo === 'COTITULAR_TODO' && !e.pagadorId) r.push('quién lo pagó');
  if (e.modo === 'COTITULAR_TODO' && !noLoSe && e.pagadorId && !partes.some((x) => x.actor_id === e.pagadorId)) r.push('que quien pagó esté en el reparto');
  if (e.modo === 'MIXTO') {
    if (numTitulares !== 2 || !e.pagadorId) r.push('«Otra combinación» solo con dos titulares');
    const a = cent(e.mio);
    const b = cent(e.suyo);
    if (Number.isNaN(a) || Number.isNaN(b) || a <= 0 || b <= 0) r.push('lo que puso cada uno (mayor que 0)');
    else if (a + b !== cent(importe)) r.push('que lo que puso cada uno sume el importe');
  }
  if (necesitaCuenta(e) && !cuentaId) r.push(e.modo === 'COMPARTIDA' ? 'la cuenta compartida' : 'la cuenta');
  if (necesitaCuenta(e) && cuentaId && e.modo !== 'COMPARTIDA' && cuentaEsCompartida) r.push('una cuenta que fuera solo tuya en esa fecha (esta no lo era: si la compartías, elige «Desde una cuenta compartida»)');
  if (e.modo === 'COMPARTIDA' && cuentaId && !cuentaEsCompartida) r.push('una cuenta compartida (esa cuenta es solo tuya)');
  const ps = propuestas(e, importe, partes);
  for (const x of ps) {
    const d = deudas[x.actor_id];
    if (!d || !d.marcada) continue;
    const v = cent(d.importe);
    if (Number.isNaN(v) || v <= 0 || v > cent(x.maximo)) r.push(`cuánto se debe con ${x.nombre} (entre 0 y ${formatearEur(x.maximo)})`);
  }
  return r;
}

/** Saldos declarados: una entrada por cotitular del reparto (NADA salvo las deudas marcadas). */
export function saldos(e: EleccionPago, importe: string, partes: ParteEfectiva[], deudas: Record<string, DeudaElegida>): SaldoWire[] {
  const ps = propuestas(e, importe, partes);
  return partes.filter((x) => !x.yo).map((x) => {
    const p = ps.find((y) => y.actor_id === x.actor_id);
    const d = deudas[x.actor_id];
    return p && d?.marcada ? { actor_id: x.actor_id, sentido: p.sentido, importe: importeTexto(d.importe) } : { actor_id: x.actor_id, sentido: 'NADA' as const };
  });
}

/** Posiciones que muestra la confirmación y que viajan como `posiciones_confirmadas`. */
export function posicionesConfirmadas(s: SaldoWire[]): PosicionWire[] {
  return s.filter((x) => x.sentido !== 'NADA')
    .map((x) => ({ actor_id: x.actor_id, tipo: x.sentido === 'ME_DEBE' ? 'DERECHO_COBRO' as const : 'OBLIGACION_PAGO' as const, importe: x.importe! }));
}

/** Wire `pagos[]` de C-MEJ-01 v2 (sin la cuenta compartida, que va por la vía de B3). */
export function pagosWire(e: EleccionPago, importe: string, partes: ParteEfectiva[], cuentaId: string | null): PagoWire[] {
  const total = importeTexto(importe);
  if (e.modo === 'YO_TODO') return [{ pagador: 'YO', cuenta_id: cuentaId!, importe: total }];
  if (e.modo === 'COTITULAR_TODO') return [{ pagador: e.pagadorId!, importe: total }];
  if (e.modo === 'MIXTO') return [{ pagador: 'YO', cuenta_id: cuentaId!, importe: importeTexto(e.mio) }, { pagador: e.pagadorId!, importe: importeTexto(e.suyo) }];
  if (e.modo === 'CADA_UNO') {
    const rep = repartirImporte(importe, partes);
    const out: PagoWire[] = [];
    for (const x of partes) {
      const v = rep[x.actor_id];
      if (!v || !(cent(v) > 0)) continue;
      out.push(x.yo ? { pagador: 'YO', cuenta_id: cuentaId!, importe: v } : { pagador: x.actor_id, importe: v });
    }
    return out;
  }
  return [];
}

/** Texto de una posición en su sentido (§1.1.7). */
export const textoPosicion = (sentido: Sentido, nombre: string, importe: string) =>
  (sentido === 'ME_DEBE' ? `${nombre} te debe ${formatearEur(importe)}` : `Le debes ${formatearEur(importe)} a ${nombre}`);

/** Confirmación por persona: su parte, lo que puso y la posición que se crea o «No queda nada pendiente». */
export function confirmacion(e: EleccionPago, importe: string, partes: ParteEfectiva[], s: SaldoWire[]): {
  actor_id: string; nombre: string; parte: string | null; puso: string; posicion: string;
}[] {
  const yo = partes.find((x) => x.yo);
  const rep = repartirImporte(importe, partes);
  const pagado = pagadoPor(e, importe, partes, yo?.actor_id ?? null);
  const filas = partes.length > 0 ? partes : [];
  return filas.map((x) => {
    const sx = s.find((y) => y.actor_id === x.actor_id);
    const posicion = x.yo
      ? (() => {
        const mias = s.filter((y) => y.sentido !== 'NADA');
        return mias.length === 0 ? TEXTO_NADA_PENDIENTE : mias.map((y) => textoPosicion(y.sentido as Sentido, nombreDe(partes.find((p) => p.actor_id === y.actor_id) ?? { nombre: null }), y.importe!)).join(' · ');
      })()
      : sx && sx.sentido !== 'NADA' ? textoPosicion(sx.sentido, nombreDe(x), sx.importe!) : TEXTO_NADA_PENDIENTE;
    return { actor_id: x.actor_id, nombre: nombreDe(x), parte: rep[x.actor_id] ?? null, puso: texto2(pagado[x.actor_id] ?? 0), posicion };
  });
}

/** Lo que sale de tus cuentas con esta elección. */
export function saleDeMisCuentas(e: EleccionPago, importe: string, partes: ParteEfectiva[]): string {
  const yo = partes.find((x) => x.yo)?.actor_id ?? 'YO';
  const v = pagadoPor(e, importe, partes, yo)[yo] ?? 0;
  return Number.isNaN(v) ? '0.00' : texto2(v);
}
