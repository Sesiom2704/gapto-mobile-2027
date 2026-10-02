// ============================================================
// GAPTO MOBILE 2027
// Fichero: magnitud.ts
// Ruta: mobile/src/domain/magnitud.ts
// Descripción: Valores de magnitudes en el registro (F05 §28.2 AJ-C07-02/06; F09 §12.97.3). `normalizarValorMagnitud` convierte lo escrito en texto decimal CANÓNICO con punto (acepta coma como separador de entrada) y rechaza vacío, signo «+», exponente, NaN/∞, cero con signo («-0»), ceros a la izquierda, más de `precision_decimales` cifras decimales significativas (los ceros de cola no cuentan: con precisión 2, «1.230» es válido y «1.234» no) y más de 12 cifras enteras. Es ayuda de captura: la autoridad es el servidor (C07). Desconocido ≠ cero: nunca se rellena «0». `conservarMagnitudes` / `descartadas` gestionan el cambio de categoría (C07: se conservan las comunes y se confirma antes de descartar valores informados).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S7-MAG UI, hito 1; F05-D020, F09 §12.97.10, lámina SET-MAG v0.1): catálogo de magnitudes del owner (GET /v1/magnitudes) y lógica pura de la sección «Magnitudes» de Ajustes › Categorías: «unidad · decimales», resumen «N obligatorias, M opcionales», estado «No usable en registros nuevos» (obligatoria deshabilitada, M03), secciones del selector (Disponibles / Deshabilitadas / Ya en <categoría>, M06) con búsqueda por nombre normalizado y subtítulo «… · usada en …» / «sin categorías». Lectura: nunca autoridad; el servidor decide en cada comando.
// Versión: 0.3.0 (F05-01 S7-MAG UI, hito 2): validación del alta rápida igual que el servidor (nombre 1..80 y unidad 1..20 visibles tras NFKC + recorte + colapso; decimales 0..6) y el texto «Para crear falta: …» (M07); conjunto COMPLETO para reordenar con el orden y la obligatoriedad cargados (M10); lista de impacto de deshabilitar (M14/M15): obligatorias afectadas según el servidor, opcionales del catálogo «sigue usable» y las que aparecen por primera vez marcadas «nueva».
// ============================================================

import type { MagnitudCategoria } from './categoria';

export type MotivoValor = 'VACIO' | 'FORMATO' | 'CERO_CON_SIGNO' | 'DECIMALES' | 'ENTEROS';

export type ResultadoValor = { ok: true; valor: string } | { ok: false; motivo: MotivoValor };

const CANONICO = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/;
export const MAX_ENTEROS = 12;

export function normalizarValorMagnitud(texto: string, precision: number): ResultadoValor {
  const t = texto.trim();
  if (t === '') return { ok: false, motivo: 'VACIO' };
  if ((t.match(/[.,]/g) ?? []).length > 1) return { ok: false, motivo: 'FORMATO' };
  const v = t.replace(',', '.');
  if (!CANONICO.test(v)) return { ok: false, motivo: 'FORMATO' };
  const [entera, decimal = ''] = v.replace(/^-/, '').split('.');
  if (v.startsWith('-') && /^0$/.test(entera) && /^0*$/.test(decimal)) return { ok: false, motivo: 'CERO_CON_SIGNO' };
  if (entera.length > MAX_ENTEROS) return { ok: false, motivo: 'ENTEROS' };
  if (decimal.replace(/0+$/, '').length > precision) return { ok: false, motivo: 'DECIMALES' };
  return { ok: true, valor: v };
}

export function textoMotivoValor(motivo: MotivoValor, precision: number): string {
  switch (motivo) {
    case 'VACIO':
      return 'Indica un valor.';
    case 'FORMATO':
    case 'CERO_CON_SIGNO':
      return 'Valor no válido.';
    case 'DECIMALES':
      return precision === 0 ? 'Sin decimales.' : `Máximo ${precision} ${precision === 1 ? 'decimal' : 'decimales'}.`;
    case 'ENTEROS':
      return 'Valor demasiado grande.';
  }
}

/** Solo los valores escritos de magnitudes que existen en la categoría nueva. */
export function conservarMagnitudes(previos: Record<string, string>, nuevas: MagnitudCategoria[]): Record<string, string> {
  const ids = new Set(nuevas.map((m) => m.magnitud_id));
  const res: Record<string, string> = {};
  for (const [id, texto] of Object.entries(previos)) if (ids.has(id)) res[id] = texto;
  return res;
}

/** Magnitudes con valor INFORMADO que se perderían al pasar a `nuevas` (null = «Sin categoría»). */
export function descartadas(
  previos: Record<string, string>,
  actuales: MagnitudCategoria[],
  nuevas: MagnitudCategoria[] | null,
): MagnitudCategoria[] {
  const quedan = new Set((nuevas ?? []).map((m) => m.magnitud_id));
  return actuales.filter((m) => (previos[m.magnitud_id] ?? '').trim() !== '' && !quedan.has(m.magnitud_id));
}


// ------------------------------------------------------------------ S7-MAG: catálogo y sección «Magnitudes»
/** Enumeración natural: «A», «A y B», «A, B y C». */
export function enumerar(nombres: string[]): string {
  if (nombres.length <= 1) return nombres.join('');
  return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
}

/** Categoría asociada a una magnitud en el catálogo (GET /v1/magnitudes). */
export interface CategoriaDeMagnitud {
  categoria_id: string;
  nombre: string;
  obligatoria: boolean;
  categoria_enabled: boolean;
}

/** Magnitud del catálogo del owner: activas, deshabilitadas y sin asociaciones (AJ-S7MAG-08). */
export interface MagnitudCatalogo {
  id: string;
  nombre: string;
  unidad_default: string;
  precision_decimales: number;
  enabled: boolean;
  row_version: number;
  categorias: CategoriaDeMagnitud[];
  /** Registros históricos con valor de esta magnitud (no se atribuyen a ninguna asociación, AJ-S7MAG-06). */
  n_hechos: number;
}

/** Vista neutra de una categoría que usa la magnitud (sin exponer el nombre de campo del wire). */
export interface UsoEnCategoria {
  id: string;
  nombre: string;
  obligatoria: boolean;
  enabled: boolean;
}

export function usosDe(m: MagnitudCatalogo): UsoEnCategoria[] {
  return m.categorias.map((c) => ({ id: c.categoria_id, nombre: c.nombre, obligatoria: c.obligatoria, enabled: c.categoria_enabled }));
}

export function textoDecimales(precision: number): string {
  return `${precision} ${precision === 1 ? 'decimal' : 'decimales'}`;
}

/** «kWh · 2 decimales» (lámina M02). */
export function textoUnidadDecimales(unidad: string, precision: number): string {
  return `${unidad} · ${textoDecimales(precision)}`;
}

/** Resumen de las asociaciones: «1 obligatoria, 1 opcional», «3 obligatorias», «» si no hay ninguna. */
export function resumenMagnitudes(mags: MagnitudCategoria[]): { total: number; obligatorias: number; opcionales: number; texto: string } {
  const obligatorias = mags.filter((m) => m.obligatoria).length;
  const opcionales = mags.length - obligatorias;
  const partes = [
    obligatorias ? `${obligatorias} ${obligatorias === 1 ? 'obligatoria' : 'obligatorias'}` : null,
    opcionales ? `${opcionales} ${opcionales === 1 ? 'opcional' : 'opcionales'}` : null,
  ].filter(Boolean);
  return { total: mags.length, obligatorias, opcionales, texto: partes.join(', ') };
}

/** Obligatorias que apuntan a una magnitud deshabilitada: la categoría no es usable en registros nuevos (M03). */
export function obligatoriasDeshabilitadas(mags: MagnitudCategoria[]): MagnitudCategoria[] {
  return mags.filter((m) => m.obligatoria && !m.enabled);
}

/** Motivo del estado «No usable en registros nuevos» con las tres salidas (M03). */
export function textoNoUsable(nombres: string[]): string {
  const lista = enumerar(nombres.map((n) => `«${n}»`));
  return nombres.length === 1
    ? `Pide ${lista}, que está deshabilitada. Rehabilítala, hazla opcional o quítala de esta categoría. Lo ya registrado no cambia.`
    : `Pide ${lista}, que están deshabilitadas. Rehabilítalas, hazlas opcionales o quítalas de esta categoría. Lo ya registrado no cambia.`;
}

/** Normalización para buscar por nombre: NFKC (si el motor la ofrece), minúsculas y sin diacríticos. */
export function normalizarBusqueda(texto: string): string {
  let t = texto.trim().replace(/\s+/g, ' ');
  try {
    t = t.normalize('NFKC');
  } catch {
    // Motor sin normalize: la búsqueda sigue funcionando sin NFKC (solo ayuda visual).
  }
  t = t.toLowerCase();
  try {
    t = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  } catch {
    // idem
  }
  return t;
}

/** «m3 · 3 decimales · usada en Agua» / «… · Deshabilitada · usada en Gas» / «… · sin categorías» (M06). */
export function subtituloCatalogo(m: MagnitudCatalogo): string {
  const usos = m.categorias.map((c) => c.nombre);
  return [
    textoUnidadDecimales(m.unidad_default, m.precision_decimales),
    m.enabled ? null : 'Deshabilitada',
    usos.length ? `usada en ${enumerar(usos)}` : 'sin categorías',
  ].filter(Boolean).join(' · ');
}

export interface SeccionesSelector {
  disponibles: MagnitudCatalogo[];
  deshabilitadas: MagnitudCatalogo[];
  /** Ya asociadas a la categoría, en el orden de la categoría. */
  yaEn: { magnitud_id: string; nombre: string; obligatoria: boolean }[];
}

/** Secciones del selector del catálogo para una categoría (M06), filtradas por nombre si hay búsqueda. */
export function seccionesSelector(catalogo: MagnitudCatalogo[], asociadas: MagnitudCategoria[], busqueda: string): SeccionesSelector {
  const ya = new Set(asociadas.map((a) => a.magnitud_id));
  const q = normalizarBusqueda(busqueda);
  const casa = (nombre: string) => q === '' || normalizarBusqueda(nombre).includes(q);
  const libres = catalogo.filter((m) => !ya.has(m.id) && casa(m.nombre));
  return {
    disponibles: libres.filter((m) => m.enabled),
    deshabilitadas: libres.filter((m) => !m.enabled),
    yaEn: asociadas.filter((a) => casa(a.nombre)).map((a) => ({ magnitud_id: a.magnitud_id, nombre: a.nombre, obligatoria: a.obligatoria })),
  };
}


// ------------------------------------------------------------------ S7-MAG hito 2: alta rápida, orden e impacto
export const LONGITUD_NOMBRE_MAGNITUD = 80;
export const LONGITUD_UNIDAD = 20;

/** Forma visible: NFKC (si el motor la ofrece), recorte y espacios internos colapsados (como el servidor, D30). */
export function visible(texto: string): string {
  let t = texto;
  try {
    t = t.normalize('NFKC');
  } catch {
    // Sin normalize: el servidor sigue siendo la autoridad.
  }
  return t.trim().replace(/\s+/g, ' ');
}

export interface FormNuevaMagnitud {
  nombre: string;
  unidad: string;
  decimales: number | null;
  obligatoria: boolean | null;
}

export interface ValidacionNueva {
  completa: boolean;
  /** «Para crear falta: …» o null si no falta nada. */
  faltan: string | null;
  errorNombre: string | null;
  errorUnidad: string | null;
}

export function validarNuevaMagnitud(f: FormNuevaMagnitud): ValidacionNueva {
  const nombre = visible(f.nombre);
  const unidad = visible(f.unidad);
  const errorNombre = nombre.length > LONGITUD_NOMBRE_MAGNITUD ? `Máximo ${LONGITUD_NOMBRE_MAGNITUD} caracteres.` : null;
  const errorUnidad = unidad.length > LONGITUD_UNIDAD ? `Máximo ${LONGITUD_UNIDAD} caracteres.` : null;
  const falta = [
    nombre ? null : 'nombre',
    unidad ? null : 'unidad',
    f.decimales === null ? 'decimales' : null,
    f.obligatoria === null ? 'si es obligatoria' : null,
  ].filter((x): x is string => x !== null);
  const faltan = falta.length ? `Para crear falta: ${enumerar(falta)}.` : null;
  return { completa: !falta.length && !errorNombre && !errorUnidad, faltan, errorNombre, errorUnidad };
}

/** Conjunto COMPLETO para POST …/magnitudes/reordenar: identidad, orden y obligatoriedad CARGADOS, en el orden propuesto. */
export function conjuntoReordenar(propuesto: MagnitudCategoria[]) {
  return propuesto.map((m) => ({ asociacion_id: m.asociacion_id, magnitud_id: m.magnitud_id, orden: m.orden, obligatoria: m.obligatoria }));
}

export function mismoOrdenAsociaciones(a: MagnitudCategoria[], b: MagnitudCategoria[]): boolean {
  return a.length === b.length && a.every((m, i) => m.asociacion_id === b[i].asociacion_id);
}

export interface FilaImpacto {
  id: string;
  nombre: string;
  etiqueta: string;
}

/**
 * Lista de la hoja de deshabilitar (M14/M15): primero las categorías que el SERVIDOR calculó bajo lock (habilitadas
 * con la magnitud obligatoria: «obligatoria», y «· nueva» si no estaban en la confirmación anterior), después las
 * opcionales habilitadas del catálogo («opcional · sigue usable»).
 */
export function filasImpacto(
  afectadas: { id: string; nombre: string }[],
  usos: UsoEnCategoria[],
  previas: string[] | null,
  ruta: (id: string, nombre: string) => string,
): FilaImpacto[] {
  const ids = new Set(afectadas.map((a) => a.id));
  const obligatorias = afectadas.map((a) => ({
    id: a.id,
    nombre: ruta(a.id, a.nombre),
    etiqueta: previas && !previas.includes(a.id) ? 'obligatoria · nueva' : 'obligatoria',
  }));
  const opcionales = usos
    .filter((u) => !ids.has(u.id) && !u.obligatoria && u.enabled)
    .map((u) => ({ id: u.id, nombre: ruta(u.id, u.nombre), etiqueta: 'opcional · sigue usable' }));
  return [...obligatorias, ...opcionales];
}
