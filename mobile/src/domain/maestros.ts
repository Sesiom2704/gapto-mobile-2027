// ============================================================
// GAPTO MOBILE 2027
// Fichero: maestros.ts
// Ruta: mobile/src/domain/maestros.ts
// Descripción: Lógica pura de los maestros del registro (F05-03/F05-04 J2 §2.3/§2.5; láminas REG-DYN / SET-TH / SET-CTX v0.1 P01, P02, S01–S03 y SET-PLT / HOME-QA v0.2 S01–S05, H01–H03). Filtro LOCAL por nombre con la misma normalización que C06 (NFKC, recorte, espacios, minúsculas, sin diacríticos): no es la búsqueda de F05-05. Textos visibles de naturaleza del tercero y tipo de contexto, rango de fechas del contexto, resumen de una plantilla («Supermercado · Tarjeta BBVA · Presupuesto: Sí»), grupos de Ajustes › Plantillas («EN INICIO · n DE 3», «OTRAS PLANTILLAS», «DESACTIVADAS») y huecos libres de Inicio (máximo 3). Las reglas de elegibilidad y unicidad las decide el servidor.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2)
// ============================================================

import type { AccionRapida, Contexto, NaturalezaTercero, Plantilla, Tercero, TipoContexto } from '../api/cliente';

export const MAX_ACCESOS = 3;

/** Normalización C06 (la misma que el servidor usa para los candidatos a duplicado). */
export function normalizarNombre(nombre: string): string {
  return nombre
    .normalize('NFKC')
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{Mn}/gu, '');
}

/** Filtro local: el texto normalizado del nombre contiene el filtro normalizado. */
export function filtrar<T extends { nombre: string }>(lista: T[], filtro: string): T[] {
  const f = normalizarNombre(filtro);
  return f === '' ? lista : lista.filter((x) => normalizarNombre(x.nombre).includes(f));
}

export const NATURALEZAS: { valor: NaturalezaTercero | null; etiqueta: string }[] = [
  { valor: 'PERSONA', etiqueta: 'Persona' },
  { valor: 'EMPRESA', etiqueta: 'Empresa' },
  { valor: 'ORGANISMO', etiqueta: 'Organismo' },
  { valor: 'OTRO', etiqueta: 'Otro' },
  { valor: null, etiqueta: 'No lo sé' },
];

export function textoNaturaleza(n: NaturalezaTercero | null): string {
  return NATURALEZAS.find((x) => x.valor === n)?.etiqueta ?? 'No lo sé';
}

/** Segunda línea de un tercero en P02: «Empresa · 14 gastos». */
export function detalleTercero(t: Pick<Tercero, 'naturaleza' | 'usos'>): string {
  const n = t.naturaleza === null ? null : textoNaturaleza(t.naturaleza);
  const usos = t.usos === undefined ? null : `${t.usos} ${t.usos === 1 ? 'registro' : 'registros'}`;
  return [n, usos].filter(Boolean).join(' · ');
}

export const TIPOS_CONTEXTO: { valor: TipoContexto; etiqueta: string }[] = [
  { valor: 'VIAJE', etiqueta: 'Viaje' },
  { valor: 'REFORMA', etiqueta: 'Reforma' },
  { valor: 'EVENTO', etiqueta: 'Evento' },
  { valor: 'SOCIAL', etiqueta: 'Social' },
  { valor: 'PROYECTO', etiqueta: 'Proyecto' },
  { valor: 'OTRO', etiqueta: 'Otro' },
];

export function textoTipoContexto(t: TipoContexto): string {
  return TIPOS_CONTEXTO.find((x) => x.valor === t)?.etiqueta ?? 'Otro';
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic'];

function diaMes(iso: string): { d: number; m: string; a: string } {
  const [a, m, d] = iso.split('-');
  return { d: Number(d), m: MESES[Number(m) - 1], a };
}

/** «10–12 oct», «10 oct – 2 nov», «desde 10 oct», «hasta 2 nov» o «» (lámina S03). */
export function rangoFechas(desde: string | null, hasta: string | null): string {
  if (desde && hasta) {
    const x = diaMes(desde);
    const y = diaMes(hasta);
    return x.m === y.m && x.a === y.a ? `${x.d}–${y.d} ${y.m}` : `${x.d} ${x.m} – ${y.d} ${y.m}`;
  }
  if (desde) return `desde ${diaMes(desde).d} ${diaMes(desde).m}`;
  if (hasta) return `hasta ${diaMes(hasta).d} ${diaMes(hasta).m}`;
  return '';
}

/** Segunda línea de un contexto en S03: «Viaje · 10–12 oct» / «Evento · Desactivado». */
export function detalleContexto(x: Pick<Contexto, 'tipo_contexto' | 'fecha_inicio' | 'fecha_fin' | 'enabled'>): string {
  const partes = [textoTipoContexto(x.tipo_contexto), x.enabled ? rangoFechas(x.fecha_inicio, x.fecha_fin) : 'Desactivado'];
  return partes.filter(Boolean).join(' · ');
}

/** Resumen de una plantilla (S01): «Supermercado · Tarjeta BBVA · Presupuesto: Sí». */
export function resumenPlantilla(
  p: Pick<Plantilla, 'categoria_id' | 'cuenta_default_id' | 'presupuestable_default' | 'tercero_id' | 'entidad_id'>,
  nombres: { categoria?: (id: string) => string | null; cuenta?: (id: string) => string | null; tercero?: (id: string) => string | null; contexto?: (id: string) => string | null },
): string {
  const partes: string[] = [];
  if (p.tercero_id) partes.push(nombres.tercero?.(p.tercero_id) ?? 'Tercero no disponible');
  if (p.categoria_id) partes.push(nombres.categoria?.(p.categoria_id) ?? 'Categoría no disponible');
  if (p.cuenta_default_id) partes.push(nombres.cuenta?.(p.cuenta_default_id) ?? 'Cuenta no disponible');
  if (p.presupuestable_default !== null) partes.push(`Presupuesto: ${p.presupuestable_default ? 'Sí' : 'No'}`);
  if (p.entidad_id) partes.push(nombres.contexto?.(p.entidad_id) ?? 'Contexto no disponible');
  return partes.join(' · ');
}

export interface GruposPlantillas {
  enInicio: { plantilla: Plantilla; accion: AccionRapida }[];
  otras: Plantilla[];
  desactivadas: Plantilla[];
}

/** S01: «EN INICIO · n DE 3» en el orden de Inicio, «OTRAS PLANTILLAS» y «DESACTIVADAS». */
export function agruparPlantillas(plantillas: Plantilla[], acciones: AccionRapida[]): GruposPlantillas {
  const activas = acciones.filter((a) => a.enabled).sort((a, b) => a.orden - b.orden || (a.id < b.id ? -1 : 1));
  const porId = new Map(plantillas.map((p) => [p.id, p]));
  const enInicio = activas.flatMap((a) => {
    const p = porId.get(a.plantilla_registro_id);
    return p && p.enabled ? [{ plantilla: p, accion: a }] : [];
  });
  const enInicioIds = new Set(enInicio.map((x) => x.plantilla.id));
  return {
    enInicio,
    otras: plantillas.filter((p) => p.enabled && !enInicioIds.has(p.id)),
    desactivadas: plantillas.filter((p) => !p.enabled),
  };
}

export function huecosLibres(acciones: AccionRapida[]): number {
  return Math.max(0, MAX_ACCESOS - acciones.filter((a) => a.enabled).length);
}

/** «Queda 1 hueco libre» / «Quedan 2 huecos libres» / «Inicio está completo» (R06). */
export function textoHuecos(n: number): string {
  if (n === 0) return 'Inicio está completo';
  return n === 1 ? 'Queda 1 hueco libre' : `Quedan ${n} huecos libres`;
}

/** La plantilla propone al menos una cosa (espejo de PLANTILLA_SIN_VALOR; el servidor decide). */
export function plantillaProponeAlgo(p: Pick<Plantilla, 'categoria_id' | 'cuenta_default_id' | 'presupuestable_default' | 'tercero_id' | 'entidad_id'>): boolean {
  return p.categoria_id !== null || p.cuenta_default_id !== null || p.presupuestable_default !== null || p.tercero_id !== null || p.entidad_id !== null;
}
