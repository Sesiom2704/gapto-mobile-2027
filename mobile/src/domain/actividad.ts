// ============================================================
// GAPTO MOBILE 2027
// Fichero: actividad.ts
// Ruta: mobile/src/domain/actividad.ts
// Descripción: Lógica pura de la Actividad v0 de Día a día (F05 §49.4 A7, §49.5 R11/R12; P-ACT-01..03; F09 DAY-Q01..Q05, Q08, Q09; lámina SRCH-ACT-AFI v0.2 B1–B13, C4). Periodo (este mes, mes anterior, otro mes, entre fechas, todo el historial) en mes natural → consulta [desde, hasta); filtros (tipo, categoría con subcategorías, cuenta, tercero, contexto) con su recuento de GRUPOS («Filtros · 2»); búsqueda: si lo escrito es un importe («48,72» o «48.72») se busca el importe exacto, si no, el texto. Fila: título calculado (`tituloRegistro`, una sola implementación) en la línea principal; la secundaria dice lo que el título no dice (tercero, categoría, cuenta, contexto; maestro desactivado marcado); importe con signo y color solo si describen la magnitud (gasto «−», ingreso «+» neutro, transferencia sin signo, DAY-Q04, P-ACT-02); «Total · reparto sin indicar» o «Total · reparto parcial» cuando el importe es el total del hecho y no tu parte (P-ACT-03, R12). Agrupación por día («Hoy · 10 oct 2026», «Ayer · …») en el periodo y por mes en la búsqueda. Sin hora: `fecha_hecho` es una fecha.
// Versión: 0.1.0 (F05-05 K3 §2.6)
// Versión: 0.2.0 (F05-06 M2-B §B1; lámina DEV B1, D-DEV-07, P-DEV-03): una devolución se titula «Devolución · <compra>», su línea secundaria dice el tercero de la compra y la categoría, el importe va sin «+» ni «−» y bajo él «Devolución» o «Abono pendiente» (nunca la marca de reparto). Nada más cambia.
// ============================================================

import type { ConsultaActividad, FilaActividad, TipoActividad } from '../api/cliente';
import { diaMesAnioIso, limitesMesIso, mesAnioIso, mesDesplazadoIso } from './fechas';
import { formatearEur, parsearImporte } from './importe';
import { esDevolucion, etiquetaDevolucion, importeDevolucion, tituloDevolucion } from './devolucion';
import { tituloRegistro } from './registro';

export type Periodo =
  | { tipo: 'ESTE_MES' }
  | { tipo: 'MES_ANTERIOR' }
  | { tipo: 'OTRO_MES'; mes: string } // primer día del mes, ISO
  | { tipo: 'ENTRE_FECHAS'; desde: string; hasta: string } // hasta INCLUIDO en la vista
  | { tipo: 'TODO' };

export interface Filtros {
  tipos: TipoActividad[];
  categoria: { id: string; nombre: string } | null;
  cuenta: { id: string; nombre: string } | null;
  tercero: { id: string; nombre: string } | null;
  contexto: { id: string; nombre: string } | null;
}

export const SIN_FILTROS: Filtros = { tipos: [], categoria: null, cuenta: null, tercero: null, contexto: null };

/** Día siguiente de una fecha ISO (para pasar «hasta» incluido a semiabierto). */
export function diaSiguienteIso(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number);
  const f = new Date(Date.UTC(a, m - 1, d + 1));
  return f.toISOString().slice(0, 10);
}

/** Rango [desde, hasta) del periodo; null en «todo el historial». */
export function rangoPeriodo(p: Periodo, hoyIso: string): { desde: string; hasta: string } | null {
  switch (p.tipo) {
    case 'ESTE_MES':
      return limitesMesIso(hoyIso);
    case 'MES_ANTERIOR':
      return limitesMesIso(mesDesplazadoIso(hoyIso, -1));
    case 'OTRO_MES':
      return limitesMesIso(p.mes);
    case 'ENTRE_FECHAS':
      return { desde: p.desde, hasta: diaSiguienteIso(p.hasta) };
    default:
      return null;
  }
}

/** Texto del periodo en la cabecera («Este mes», «Septiembre 2026», «Todo el historial»…). */
export function textoPeriodo(p: Periodo, hoyIso: string): string {
  switch (p.tipo) {
    case 'ESTE_MES':
      return 'Este mes';
    case 'MES_ANTERIOR':
      return 'Mes anterior';
    case 'OTRO_MES':
      return mesAnioIso(p.mes);
    case 'ENTRE_FECHAS':
      return `${diaMesAnioIso(p.desde)} – ${diaMesAnioIso(p.hasta)}`;
    default:
      return 'Todo el historial';
  }
}

/** Nombre del mes del periodo para el estado vacío («No hay registros en octubre»). */
export function mesDelPeriodo(p: Periodo, hoyIso: string): string | null {
  const r = rangoPeriodo(p, hoyIso);
  if (!r || p.tipo === 'ENTRE_FECHAS') return null;
  return mesAnioIso(r.desde).split(' ')[0].toLowerCase();
}

/** Número de GRUPOS de filtros activos (no de valores). */
export function gruposActivos(f: Filtros): number {
  return [f.tipos.length > 0, !!f.categoria, !!f.cuenta, !!f.tercero, !!f.contexto].filter(Boolean).length;
}

export const NOMBRE_FILTRO_TIPO: Record<TipoActividad, string> = { GASTO: 'Gasto', INGRESO: 'Ingreso', TRANSFERENCIA: 'Entre cuentas' };

/** Etiquetas de la línea de filtros activos. */
export function etiquetasFiltros(f: Filtros): string[] {
  return [
    ...f.tipos.map((t) => NOMBRE_FILTRO_TIPO[t]),
    ...(f.categoria ? [f.categoria.nombre] : []),
    ...(f.cuenta ? [f.cuenta.nombre] : []),
    ...(f.tercero ? [f.tercero.nombre] : []),
    ...(f.contexto ? [f.contexto.nombre] : []),
  ];
}

/** Si lo escrito es un importe («48,72», «48.72», «48»), su valor canónico; si no, null. */
export function importeDeBusqueda(q: string): string | null {
  const t = q.trim();
  if (!/^\d[\d.,]*$/.test(t)) return null;
  const r = parsearImporte(t);
  return r.ok ? r.valor : null;
}

/** Consulta del servidor para el periodo, los filtros y la búsqueda (con búsqueda: todo el historial). */
export function consulta(p: Periodo, f: Filtros, hoyIso: string, busqueda: string | null): ConsultaActividad {
  const q = busqueda?.trim() ?? '';
  const importe = q ? importeDeBusqueda(q) : null;
  const rango = q ? null : rangoPeriodo(p, hoyIso);
  return {
    desde: rango?.desde ?? null,
    hasta: rango?.hasta ?? null,
    tipos: f.tipos,
    categoriaId: f.categoria?.id ?? null,
    cuentaId: f.cuenta?.id ?? null,
    terceroId: f.tercero?.id ?? null,
    contextoId: f.contexto?.id ?? null,
    q: q && !importe ? q : null,
    importe,
  };
}

/** Título calculado de la fila (P-ACT-01). */
export function tituloFila(r: FilaActividad): string {
  const devolucion = tituloDevolucion(r);
  if (devolucion) return devolucion;
  return tituloRegistro({
    tipo: r.tipo,
    importe: r.importe_total ?? '0',
    nota: r.nota,
    tercero: r.tercero?.nombre ?? null,
    categoria: r.varias ? 'Varias' : r.categoria?.nombre ?? null,
  });
}

/** Línea secundaria: lo que el título no dice (P-ACT-01, lámina B1/B8). */
export function secundariaFila(r: FilaActividad): string {
  const titulo = tituloFila(r);
  const partes: string[] = [];
  if (r.devolucion_de) {
    if (r.devolucion_de.tercero) partes.push(r.devolucion_de.tercero);
    partes.push(r.categoria?.nombre ?? 'Sin categoría');
  } else if (r.tipo === 'TRANSFERENCIA') {
    partes.push('Entre cuentas');
  } else {
    const ter = r.tercero?.nombre;
    const cat = r.varias ? 'Varias' : r.categoria?.nombre ?? null;
    if (ter && !titulo.includes(ter)) partes.push(ter);
    if (cat && !titulo.includes(cat)) partes.push(cat);
    if (!cat && !r.varias) partes.push('Sin categoría');
    const cuenta = r.cuentas[0]?.nombre;
    if (cuenta) partes.push(cuenta);
  }
  if (r.contexto) partes.push(`contexto «${r.contexto.nombre}»`);
  for (const m of r.maestros_desactivados) {
    partes.push(m === 'CATEGORIA' ? 'Categoría desactivada' : m === 'TERCERO' ? 'Tercero desactivado' : 'Contexto desactivado');
  }
  return partes.join(' · ');
}

/** Título de una transferencia en la fila («Cuenta nómina → Ahorro») cuando no hay nota. */
export function tituloTransferencia(r: FilaActividad): string | null {
  if (r.tipo !== 'TRANSFERENCIA' || (r.nota ?? '').trim()) return null;
  const o = r.cuentas.find((c) => c.rol === 'ORIGEN')?.nombre;
  const d = r.cuentas.find((c) => c.rol === 'DESTINO')?.nombre;
  return o && d ? `${o} → ${d}` : null;
}

/** Importe con signo según el tipo (DAY-Q04, P-ACT-02). */
export function importeFila(r: FilaActividad): string {
  if (esDevolucion(r)) return importeDevolucion(r);
  const total = formatearEur(r.importe_total ?? '0');
  if (r.tipo === 'GASTO') return `−${total}`;
  if (r.tipo === 'INGRESO') return `+${total}`;
  return total;
}

/** Marca bajo el importe cuando es el total del hecho y no tu parte (P-ACT-03, R12). */
export function marcaReparto(r: FilaActividad): string | null {
  if (esDevolucion(r)) return etiquetaDevolucion(r);
  if (r.estado_reparto === 'NO_DISPONIBLE') return 'Total · reparto sin indicar';
  if (r.estado_reparto === 'PARCIAL') return 'Total · reparto parcial';
  return null;
}

/** «Tu parte» del detalle: importe y «Solo mío», «Sin indicar» o la parte atribuida con lo pendiente. */
export function textoTuParte(r: FilaActividad): string {
  if (r.estado_reparto === 'COMPLETA' && r.tu_parte !== null) {
    return r.tu_parte === r.importe_total ? `${formatearEur(r.tu_parte)} · Solo mío` : formatearEur(r.tu_parte);
  }
  if (r.estado_reparto === 'PARCIAL' && r.tu_parte !== null) {
    return `${formatearEur(r.tu_parte)} · ${formatearEur(r.pendiente ?? '0')} sin indicar`;
  }
  return 'Sin indicar';
}

/** Explicación de la coincidencia cuando no es evidente (D-SRCH-08). */
export function textoCoincidencia(r: FilaActividad): string | null {
  const m = r.coincide_en ?? [];
  if (m.includes('TERCERO') || m.includes('NOTA') || m.includes('IMPORTE')) return null; // ya se ve en el título o el importe
  if (m.includes('CATEGORIA') && r.categoria) return `Coincide con la categoría «${r.categoria.nombre}»`;
  if (m.includes('CONTEXTO') && r.contexto) return `Contexto «${r.contexto.nombre}»`;
  return null;
}

export interface Grupo {
  clave: string;
  titulo: string;
  filas: FilaActividad[];
}

/** Agrupa por día (periodo) o por mes (búsqueda), conservando el orden del servidor. */
export function agrupar(filas: FilaActividad[], por: 'DIA' | 'MES', hoyIso: string, ayerIso: string): Grupo[] {
  const grupos: Grupo[] = [];
  for (const f of filas) {
    const clave = por === 'DIA' ? f.fecha_hecho : f.fecha_hecho.slice(0, 7);
    let g = grupos[grupos.length - 1];
    if (!g || g.clave !== clave) {
      const titulo =
        por === 'MES'
          ? mesAnioIso(f.fecha_hecho)
          : f.fecha_hecho === hoyIso
            ? `Hoy · ${diaMesAnioIso(f.fecha_hecho)}`
            : f.fecha_hecho === ayerIso
              ? `Ayer · ${diaMesAnioIso(f.fecha_hecho)}`
              : diaMesAnioIso(f.fecha_hecho);
      g = { clave, titulo, filas: [] };
      grupos.push(g);
    }
    g.filas.push(f);
  }
  return grupos;
}

/** Línea de alcance de la búsqueda (B2/B10). */
export function textoAlcance(q: string, total: number | null): string {
  const base = importeDeBusqueda(q) ? 'Buscando en todo el historial · importe exacto' : 'Buscando en todo el historial';
  return total === null ? base : `${base} · ${total} ${total === 1 ? 'resultado' : 'resultados'}`;
}
