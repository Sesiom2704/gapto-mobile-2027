// ============================================================
// GAPTO MOBILE 2027
// Fichero: gasto_propiedad.ts
// Ruta: mobile/src/domain/gasto_propiedad.ts
// Descripción: Lógica pura de B3 · Obras y gastos de una propiedad (F06-01 B3; R1 v0.9.5 Parte III §III.1bis puntos 1–9, 8bis, 8ter y 8quater; v0.9 §III.1–§III.3; lámina F06-01 v0.9 C1–C3 y boceto L-5 de R1_LAMINAS §2).
//   - Clase obligatoria y sin valor por defecto (MEJORA, REPARACION, GASTO_CORRIENTE); MEJORA no lleva categoría ni «¿Cuenta para el presupuesto?» y las otras dos los exigen sin valor previo.
//   - Reparto propuesto POR DEFECTO según la titularidad de la PROPIEDAD en la FECHA DEL HECHO (DM-02; nunca la cuenta pagadora): marcado y visible con su origen y fecha; si cambian fecha o propiedad y el usuario no lo tocó, se vuelve a proponer; si lo tocó, se conserva. Sin titularidad en esa fecha no se marca nada y el envío exige elegir (nunca «Solo mío» ni YO 100).
//   - Deuda por defecto (8, 8bis): «Te debe su parte: Sí» marcado solo para un cotitular PERSONA con la cuenta solo tuya (aportación acreditada). Exclusiones (8ter): cuenta compartida → sin preselección, y con «Sí» el importe se teclea a mano (aportación MANUAL, sin valor previo, como mucho su parte); EMPRESA, mejora histórica (sin pago), «No lo sé» o parte sin importe → no se ofrece. El valor viaja SIEMPRE explícito por parte.
//   - Confirmación (8bis): lo que se mostrará (quién, cuánto, concepto, parte atribuida, «Se creará un derecho de cobro» y la atribución que se persistirá) y el cuerpo con `derechos_confirmados` = exactamente lo mostrado.
//   - Corrección de la clase (C-MEJ-03): solo con `intencion_correccion_id`; destinos MEJORA → gasto y gasto → MEJORA; con deuda, la limitación literal de 8quater (R-DM02-01) y nunca «anular y recrear» ni la corrección de categoría como equivalentes.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// ============================================================

import type {
  AtribucionB3, ClaseGasto, ComparacionImpacto, LecturaGastoPropiedad, PartePropuesta, PayloadCorregirClase, PayloadGastoPropiedad,
  PayloadMejoraHistorica, PropuestaGasto, FilaGastoPropiedad,
} from '../api/patrimonio_b3';
import { diaMesAnioIso } from './fechas';
import { formatearEur, parsearImporte } from './importe';
import { esFechaIso } from './intencion';

export const NOMBRE_CLASE: Record<ClaseGasto, string> = {
  MEJORA: 'Mejora (aumenta el valor)',
  REPARACION: 'Reparación',
  GASTO_CORRIENTE: 'Gasto corriente (luz, comunidad…)',
};
export const AYUDA_CLASE: Record<ClaseGasto, string> = {
  MEJORA: 'Añade o renueva algo: suma al coste de la vivienda',
  REPARACION: 'Lo deja como estaba: cuenta como gasto',
  GASTO_CORRIENTE: 'Luz, agua, comunidad…: cuenta como gasto',
};
export const CLASES: ClaseGasto[] = ['MEJORA', 'REPARACION', 'GASTO_CORRIENTE'];

export const TEXTO_SIN_CLASE = 'Sin respuesta no se puede guardar: no hay opción por defecto.';
export const TEXTO_SIN_TITULARIDAD = 'No hay titularidad registrada en esa fecha: elige un reparto o «No lo sé».';
export const TEXTO_DESFASADA = 'La titularidad ha cambiado: revisa el reparto.';
export const TEXTO_SE_CREA_DERECHO = 'Se creará un derecho de cobro';
export const TEXTO_CUENTA_COMPARTIDA =
  'Pagaste desde una cuenta compartida: no sabemos cuánto puso cada uno. Si te debe algo, indícalo tú.';
export const TEXTO_SIN_PAGO = 'Se anota como mejora ya ocurrida sin movimiento de cuenta. Tu liquidez no cambia.';
export const TEXTO_INDETERMINADO = 'No se ha podido confirmar el registro. Revisa la propiedad antes de repetirlo.';
/** 8quater: texto contractual LITERAL del dictamen (Q-R1-07, condición obligatoria 2). */
export const TEXTO_LIMITACION_8QUATER =
  'Los hechos de gasto de propiedad con una posición de deuda asociada no admiten actualmente la operación Corregir clase. No existe en este alcance una vía soportada para corregir su clase conservando la posición. Esta capacidad queda pendiente de una corrección de clase para hechos con varios efectos.';
export const TEXTO_IMPACTO_DESFASADO = 'Los datos han cambiado; revisa el impacto';

export type EleccionReparto = null | { modo: 'TITULARIDAD' } | { modo: 'NO_LO_SE' } | { modo: 'MANUAL'; partes: Record<string, string> };
export interface DeudaParte { me_debe: 'SI' | 'NO' | null; importe: string }

export interface BorradorGastoPropiedad {
  clase: ClaseGasto | null;
  importe: string;
  fecha: string;
  cuentaId: string | null;
  nota: string;
  categoriaId: string | null;
  presupuestable: boolean | null;
  reparto: EleccionReparto;
  repartoTocado: boolean;
  deuda: Record<string, DeudaParte>;
  deudaTocada: boolean;
}

export function borradorInicial(hoyIso: string): BorradorGastoPropiedad {
  return { clase: null, importe: '', fecha: hoyIso, cuentaId: null, nota: '', categoriaId: null, presupuestable: null, reparto: null,
    repartoTocado: false, deuda: {}, deudaTocada: false };
}

const cent = (t: string): number => {
  const p = parsearImporte(t);
  return p.ok ? Math.round(Number(p.valor) * 100) : NaN;
};
const texto2 = (c: number) => (c / 100).toFixed(2);
const importeTexto = (t: string) => {
  const p = parsearImporte(t);
  return p.ok ? p.valor : t;
};
/** Porcentaje a diezmilésimas enteras («50.0000» → 500000). */
const pct4 = (p: string) => Math.round(Number(p.replace(',', '.')) * 10000);
const pctTexto = (p: string) => `${Number(p.replace(',', '.')).toLocaleString('es-ES', { maximumFractionDigits: 4 })} %`;

/** Hay propuesta que marcar: titularidad de la propiedad en la fecha del hecho. */
export const hayPropuesta = (prop: PropuestaGasto | null) => !!prop && prop.titularidad_disponible && prop.partes.length > 0;

/** Valor inicial del reparto (DM-02): la propuesta marcada si existe; si no, nada (el formulario exige elegir). */
export const repartoInicial = (prop: PropuestaGasto | null): EleccionReparto => (hayPropuesta(prop) ? { modo: 'TITULARIDAD' } : null);

/** Parte efectiva del reparto elegido, con naturaleza y nombre de la propuesta. */
export interface ParteEfectiva { actor_id: string; porcentaje: string; yo: boolean; nombre: string | null; naturaleza: PartePropuesta['naturaleza'] }

export function partesEfectivas(e: EleccionReparto, prop: PropuestaGasto | null, actores: PartePropuesta[]): ParteEfectiva[] {
  if (e === null || e.modo === 'NO_LO_SE') return [];
  if (e.modo === 'TITULARIDAD') return hayPropuesta(prop) ? prop!.partes.map((x) => ({ ...x })) : [];
  return Object.entries(e.partes)
    .filter(([, v]) => v.trim() !== '' && Number(v.replace(',', '.')) > 0)
    .map(([actor_id, v]) => {
      const a = actores.find((x) => x.actor_id === actor_id);
      return { actor_id, porcentaje: v.replace(',', '.'), yo: a?.yo ?? false, nombre: a?.nombre ?? null, naturaleza: a?.naturaleza ?? null };
    });
}

/** M-2 §1.2: HALF_EVEN por parte y residuo céntimo a céntimo por porcentaje descendente y actor ascendente (como el servidor). */
export function repartirImporte(importe: string, partes: { actor_id: string; porcentaje: string }[]): Record<string, string> {
  const total = cent(importe);
  if (Number.isNaN(total) || partes.length === 0) return {};
  const base: Record<string, number> = {};
  for (const x of partes) {
    const v = total * pct4(x.porcentaje); // céntimos × 1e6
    let q = Math.floor(v / 1_000_000);
    const r = v - q * 1_000_000;
    if (r * 2 > 1_000_000 || (r * 2 === 1_000_000 && q % 2 === 1)) q += 1;
    base[x.actor_id] = q;
  }
  let residuo = total - Object.values(base).reduce((s, x) => s + x, 0);
  const orden = [...partes].sort((a, z) => pct4(z.porcentaje) - pct4(a.porcentaje) || (a.actor_id < z.actor_id ? -1 : a.actor_id > z.actor_id ? 1 : 0));
  const paso = residuo > 0 ? 1 : -1;
  for (let i = 0; residuo !== 0; i++) {
    base[orden[i % orden.length].actor_id] += paso;
    residuo -= paso;
  }
  return Object.fromEntries(Object.entries(base).map(([k, v]) => [k, texto2(v)]));
}

export const cuentaCompartida = (prop: PropuestaGasto | null) => !!prop?.cuenta && !prop.cuenta.solo_mia;

/** 8ter: se ofrece «Te debe su parte» a esta parte. Nunca en la mejora histórica, ni a EMPRESA, ni sin importe. */
export function ofreceDeuda(x: ParteEfectiva, importeParte: string | undefined, prop: PropuestaGasto | null, historica: boolean): boolean {
  if (historica || x.yo) return false;
  if (x.naturaleza !== 'PERSONA') return false;
  if (!prop?.cuenta) return false;
  return !!importeParte && cent(importeParte) > 0;
}

/** 8bis: «Sí» marcado solo con la aportación acreditada (cuenta solo tuya); con cuenta compartida, sin preselección y sin importe. */
export function deudaInicial(prop: PropuestaGasto | null): DeudaParte {
  return prop?.cuenta?.solo_mia ? { me_debe: 'SI', importe: '' } : { me_debe: null, importe: '' };
}

/** Recalcula reparto y deuda al cambiar la propuesta (fecha, propiedad o cuenta) sin pisar lo que el usuario tocó. */
export function alCambiarPropuesta(b: BorradorGastoPropiedad, prop: PropuestaGasto | null, actores: PartePropuesta[]): BorradorGastoPropiedad {
  const reparto = b.repartoTocado ? b.reparto : repartoInicial(prop);
  const deuda = b.deudaTocada ? completarDeuda(b.deuda, reparto, prop, actores) : deudaPorDefecto(reparto, prop, actores);
  return { ...b, reparto, deuda };
}

/** Añade el valor por defecto a las partes ofrecidas que aún no tienen elección (p. ej. tras cambiar el reparto). */
export function completarDeuda(deuda: Record<string, DeudaParte>, reparto: EleccionReparto, prop: PropuestaGasto | null,
  actores: PartePropuesta[]): Record<string, DeudaParte> {
  return { ...deudaPorDefecto(reparto, prop, actores), ...deuda };
}

/** Valor inicial de «Te debe su parte» por parte ofrecida (con un importe de referencia: el importe real se comprueba al confirmar). */
export function deudaPorDefecto(reparto: EleccionReparto, prop: PropuestaGasto | null, actores: PartePropuesta[]): Record<string, DeudaParte> {
  const partes = partesEfectivas(reparto, prop, actores);
  const imp = repartirImporte('100.00', partes);
  const out: Record<string, DeudaParte> = {};
  for (const x of partes) if (ofreceDeuda(x, imp[x.actor_id], prop, false)) out[x.actor_id] = deudaInicial(prop);
  return out;
}

export interface Derecho { actor_id: string; nombre: string; importe: string; parte: string; porcentaje: string; concepto: string }

/** Derechos que mostrará la confirmación (8bis): solo las partes ofrecidas con «Sí». */
export function derechos(b: BorradorGastoPropiedad, prop: PropuestaGasto | null, actores: PartePropuesta[], concepto: string): Derecho[] {
  const partes = partesEfectivas(b.reparto, prop, actores);
  const imp = repartirImporte(b.importe, partes);
  return partes
    .filter((x) => ofreceDeuda(x, imp[x.actor_id], prop, false) && b.deuda[x.actor_id]?.me_debe === 'SI')
    .map((x) => ({ actor_id: x.actor_id, nombre: x.nombre ?? 'Otra persona', parte: imp[x.actor_id], porcentaje: x.porcentaje, concepto,
      importe: cuentaCompartida(prop) ? importeTexto(b.deuda[x.actor_id].importe) : imp[x.actor_id] }));
}

export function faltasDatos(b: BorradorGastoPropiedad): string[] {
  const r: string[] = [];
  if (b.clase === null) r.push('la clase del gasto');
  if (!parsearImporte(b.importe).ok) r.push('un importe mayor que 0');
  if (!esFechaIso(b.fecha)) r.push('la fecha');
  if (!b.cuentaId) r.push('la cuenta');
  if (b.clase !== null && b.clase !== 'MEJORA') {
    if (!b.categoriaId) r.push('la categoría');
    if (b.presupuestable === null) r.push('si cuenta para el presupuesto');
  }
  return r;
}

export function faltasReparto(b: BorradorGastoPropiedad, prop: PropuestaGasto | null, actores: PartePropuesta[], historica = false): string[] {
  const e = b.reparto;
  if (e === null) return ['elegir de quién es el gasto'];
  if (e.modo === 'TITULARIDAD' && !hayPropuesta(prop)) return [TEXTO_SIN_TITULARIDAD];
  if (e.modo === 'MANUAL') {
    const v = Object.values(e.partes).filter((x) => x.trim() !== '').map((x) => Number(x.replace(',', '.')));
    if (v.length === 0 || v.some((x) => !(x > 0 && x <= 100)) || Math.round(v.reduce((s, x) => s + x, 0) * 10000) !== 1000000) return ['un reparto que sume 100 %'];
  }
  if (historica) return [];
  const partes = partesEfectivas(e, prop, actores);
  const imp = repartirImporte(b.importe, partes);
  const r: string[] = [];
  for (const x of partes) {
    if (!ofreceDeuda(x, imp[x.actor_id], prop, false)) continue;
    const d = b.deuda[x.actor_id];
    if (!d || d.me_debe === null) r.push(`elegir si ${x.nombre ?? 'esa persona'} te debe su parte`);
    else if (d.me_debe === 'SI' && cuentaCompartida(prop)) {
      const c = cent(d.importe);
      if (Number.isNaN(c) || c <= 0 || c > cent(imp[x.actor_id])) r.push(`cuánto te debe ${x.nombre ?? 'esa persona'} (como mucho su parte)`);
    }
  }
  return r;
}

/** «Según la titularidad de <propiedad> el <fecha>: tú 50 %, Ana 50 %». */
export function textoPropuesta(propiedad: string, prop: PropuestaGasto): string {
  const partes = [...prop.partes.filter((x) => x.yo), ...prop.partes.filter((x) => !x.yo)]
    .map((x) => `${x.yo ? 'tú' : x.nombre ?? 'otra persona'} ${pctTexto(x.porcentaje)}`);
  return `Según la titularidad de ${propiedad} el ${diaMesAnioIso(prop.fecha)}: ${partes.join(', ')}`;
}

function atribucionWire(e: EleccionReparto, prop: PropuestaGasto | null, fecha: string): AtribucionB3 {
  if (e === null || e.modo === 'NO_LO_SE') return { modo: 'NO_LO_SE' };
  if (e.modo === 'MANUAL')
    return { modo: 'MANUAL', partes: Object.entries(e.partes).filter(([, v]) => v.trim() !== '').map(([actor_id, v]) => ({ actor_id, porcentaje: v.replace(',', '.') })) };
  return { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO', fecha_referencia: fecha,
    partes: (prop?.partes ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })) } };
}

/**
 * C-MEJ-01. `mostrados` son los derechos que enseñó la pantalla de confirmación: `derechos_confirmados` es exactamente eso.
 * `deuda` lleva una entrada por cada parte de cotitular (no tú), siempre explícita; lo que no se ofrece va como «NO».
 */
export function payloadGastoPropiedad(intencionId: string, propiedadId: string, b: BorradorGastoPropiedad, prop: PropuestaGasto | null,
  actores: PartePropuesta[], mostrados: Derecho[]): PayloadGastoPropiedad {
  const partes = partesEfectivas(b.reparto, prop, actores);
  const confirmados = new Set(mostrados.map((d) => d.actor_id));
  const gasto = b.clase !== 'MEJORA';
  return {
    intencion_id: intencionId,
    propiedad_id: propiedadId,
    clase: b.clase!,
    importe: importeTexto(b.importe),
    fecha_hecho: b.fecha,
    cuenta_id: b.cuentaId!,
    nota: b.nota.trim() ? b.nota.trim() : null,
    categoria_id: gasto ? b.categoriaId : null,
    presupuestable: gasto ? b.presupuestable : null,
    atribucion: atribucionWire(b.reparto, prop, b.fecha),
    deuda: partes.filter((x) => !x.yo).map((x) => ({ actor_id: x.actor_id, me_debe: confirmados.has(x.actor_id) ? 'SI' : 'NO' })),
    aportacion_indicada: mostrados.length > 0 && cuentaCompartida(prop) ? 'MANUAL' : null,
    derechos_confirmados: mostrados.map((d) => ({ actor_id: d.actor_id, importe: d.importe })),
  };
}

/** C-MEJ-02: sin pago, nunca deuda. */
export function payloadMejoraHistorica(intencionId: string, rowVersion: number, descripcion: string, importe: string, fecha: string,
  e: EleccionReparto, prop: PropuestaGasto | null): PayloadMejoraHistorica {
  return { intencion_id: intencionId, row_version_esperada: rowVersion, descripcion: descripcion.trim(), importe: importeTexto(importe), fecha,
    atribucion: atribucionWire(e, prop, fecha) };
}

/** Atribución que se persistirá (para la confirmación). */
export function atribucionTexto(b: BorradorGastoPropiedad, prop: PropuestaGasto | null, actores: PartePropuesta[]): { actor_id: string; texto: string }[] {
  const partes = partesEfectivas(b.reparto, prop, actores);
  if (partes.length === 0) return [];
  const imp = repartirImporte(b.importe, partes);
  return partes.map((x) => ({ actor_id: x.actor_id, texto: `${x.yo ? 'Tú' : x.nombre ?? 'Otra persona'} · ${pctTexto(x.porcentaje)} · ${formatearEur(imp[x.actor_id] ?? '0')}` }));
}

// ------------------------------------------------------------------ C2 resumen de los gastos de la propiedad
export function resumenGastos(filas: FilaGastoPropiedad[]): { mejoras: string; gastos: string; total: string } {
  const activas = filas.filter((f) => f.estado === 'ACTIVO');
  const suma = (xs: FilaGastoPropiedad[]) => xs.reduce((s, f) => s + Math.round(Number(f.importe) * 100), 0);
  const m = suma(activas.filter((f) => f.clase === 'MEJORA'));
  const g = suma(activas.filter((f) => f.clase === 'GASTO'));
  return { mejoras: texto2(m), gastos: texto2(g), total: texto2(m + g) };
}

// ------------------------------------------------------------------ C-MEJ-03 corrección de la clase
/** Solo con una intención vigente (el servidor la da con un efecto vigente único y el hecho ACTIVO). */
export const ofreceCorregir = (l: LecturaGastoPropiedad) => l.intencion_correccion_id !== null;
/** 8quater: con deuda se declara la limitación. */
export const muestraLimitacion = (l: LecturaGastoPropiedad) => l.con_deuda;
export const clasesDestino = (l: LecturaGastoPropiedad): ClaseGasto[] => (l.clase === 'MEJORA' ? ['REPARACION', 'GASTO_CORRIENTE'] : ['MEJORA']);

export interface SeleccionCorreccion { clase: ClaseGasto | null; categoriaId: string | null; presupuestable: boolean | null; motivo: string }
export const seleccionInicial = (): SeleccionCorreccion => ({ clase: null, categoriaId: null, presupuestable: null, motivo: '' });

export function faltasCorreccion(s: SeleccionCorreccion): string[] {
  const r: string[] = [];
  if (s.clase === null) r.push('la clase nueva');
  if (s.clase !== null && s.clase !== 'MEJORA') {
    if (!s.categoriaId) r.push('la categoría');
    if (s.presupuestable === null) r.push('si cuenta para el presupuesto');
  }
  if (!s.motivo.trim()) r.push('el motivo');
  return r;
}

export function payloadCorreccion(l: LecturaGastoPropiedad, s: SeleccionCorreccion, comparacion: ComparacionImpacto): PayloadCorregirClase {
  const gasto = s.clase !== 'MEJORA';
  return { intencion_id: l.intencion_correccion_id!, row_version_esperada: l.row_version, clase_nueva: s.clase!, motivo: s.motivo.trim(),
    categoria_id: gasto ? s.categoriaId : null, presupuestable: gasto ? s.presupuestable : null, comparacion_vista: comparacion };
}

/** Filas Antes / Después de la tabla de impacto (de este gasto). */
export function filasImpacto(c: ComparacionImpacto): { clave: string; etiqueta: string; antes: string; despues: string }[] {
  return [
    { clave: 'resultado', etiqueta: `Resultado de ${c.mes}`, antes: formatearEur(c.resultado_mes_delta_antes), despues: formatearEur(c.resultado_mes_delta_despues) },
    { clave: 'mejoras', etiqueta: 'Coste de mejoras', antes: formatearEur(c.mejoras_antes), despues: formatearEur(c.mejoras_despues) },
    { clave: 'presupuesto', etiqueta: 'Presupuesto', antes: '—', despues: formatearEur(c.presupuesto_delta_despues) },
  ];
}

const TEXTOS_ERROR: Record<string, string> = {
  ATRIBUCION_PROPUESTA_DESFASADA: TEXTO_DESFASADA,
  TITULARIDAD_NO_DISPONIBLE_EN_FECHA: TEXTO_SIN_TITULARIDAD,
  PROPIEDAD_NO_DISPONIBLE: 'Esta propiedad no está disponible.',
  OPERACION_NO_PERMITIDA_EN_ESTADO: 'No puedes registrar gastos en una propiedad que no es tuya.',
  CLASE_GASTO_PROPIEDAD_AUSENTE: TEXTO_SIN_CLASE,
  CUENTA_DESCONOCIDA: 'Esa cuenta no se puede usar para pagar en esa fecha.',
  FECHA_FUTURA: 'La fecha no puede ser futura.',
  IMPACTO_CORRECCION_DESFASADO: TEXTO_IMPACTO_DESFASADO,
  INTENCION_CORRECCION_NO_VIGENTE: 'El gasto ha cambiado: vuelve a abrirlo.',
  VERSION_DESFASADA: 'El gasto ha cambiado: vuelve a abrirlo.',
  CORRECCION_NATURALEZA_NO_ADMITIDA: 'Este gasto no se puede reclasificar.',
  PERIODO_CERRADO_SIN_POLITICA: 'Ese mes está cerrado: no se puede corregir.',
  MOTIVO_AUSENTE: 'Indica el motivo.',
  IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: 'Este registro ya se guardó con otros datos. No se ha guardado nada nuevo.',
};
export const textoError = (codigo: string, mensaje: string) => TEXTOS_ERROR[codigo] ?? (mensaje || TEXTO_INDETERMINADO);
