// ============================================================
// GAPTO MOBILE 2027
// Fichero: senales.ts
// Ruta: mobile/src/domain/senales.ts
// Descripción: Lógica pura de las señales de F05-05 (F05 §49.4 A1/A2/A4, §49.5 R1/R4; lámina SRCH-ACT-AFI v0.2 A1, A3, A6, A7). Tipos del wire de GET /v1/senales/categorias y /v1/senales/terceros y textos del vocabulario cerrado de R4: «La guardaste para <tercero>», «Sueles usarla con <tercero>», «Frecuente en tus gastos | ingresos», «Usada recientemente»; en «Recientes» de terceros, «Usado hoy | ayer | hace N días» o «Frecuente en tus gastos | ingresos». Una sugerencia NUNCA es una propuesta: no fija la categoría ni cambia orígenes (R1, C01); la elige el usuario con el mismo callback que el árbol. Consumidores autorizados (I13 v2, test_i13_g): SelectorCategorias.tsx («Sugeridas»), RegistroGastoScreen.tsx (chips) y SelectorTercero.tsx («Recientes»). Sin imports: módulo puro.
// Versión: 0.1.0 (F05-05 K3 §2.1–§2.3)
// ============================================================

export type MotivoSenal = 'AFINIDAD' | 'FRECUENTE_TERCERO' | 'FRECUENTE_TIPO' | 'RECIENTE';
export type TipoSenal = 'GASTO' | 'INGRESO';

export interface CandidataCategoria {
  categoria_id: string;
  nombre: string;
  ruta: string;
  motivo: MotivoSenal;
  fuente: 'AFINIDAD' | 'HISTORIAL';
  usos: number;
  ultimo_uso: string | null;
}

export interface SenalesCategorias {
  tipo: TipoSenal;
  fecha: string;
  tercero_id: string | null;
  candidatas: CandidataCategoria[];
}

export interface TerceroReciente {
  tercero_id: string;
  nombre: string;
  naturaleza: string | null;
  usos: number;
  ultimo_uso: string;
  motivo: 'RECIENTE' | 'FRECUENTE_TIPO';
}

export interface SenalesTerceros {
  tipo: TipoSenal;
  fecha: string;
  terceros: TerceroReciente[];
}

/** Vista de una sugerida para el selector y los chips: ruta y motivo ya en texto. */
export interface SugeridaCategoria {
  categoria_id: string;
  nombre: string;
  ruta: string;
  motivo: string;
}

/** Máximo de sugerencias que se muestran (A2, A2 bis). */
export const MAX_SUGERIDAS = 3;

const DE_TIPO: Record<TipoSenal, string> = { GASTO: 'tus gastos', INGRESO: 'tus ingresos' };

/** Texto del motivo (R4, D-SRCH-02). Sin tercero no hay AFINIDAD ni FRECUENTE_TERCERO. */
export function textoMotivo(m: MotivoSenal, ctx: { tercero: string | null; tipo: TipoSenal }): string {
  switch (m) {
    case 'AFINIDAD':
      return `La guardaste para ${ctx.tercero ?? 'este tercero'}`;
    case 'FRECUENTE_TERCERO':
      return `Sueles usarla con ${ctx.tercero ?? 'este tercero'}`;
    case 'RECIENTE':
      return 'Usada recientemente';
    default:
      return `Frecuente en ${DE_TIPO[ctx.tipo]}`;
  }
}

/** Sugeridas en texto, en el orden del servidor (determinista, R6), hasta MAX_SUGERIDAS. */
export function vistaSugeridas(s: SenalesCategorias, tercero: string | null): SugeridaCategoria[] {
  return s.candidatas.slice(0, MAX_SUGERIDAS).map((c) => ({
    categoria_id: c.categoria_id,
    nombre: c.nombre,
    ruta: c.ruta,
    motivo: textoMotivo(c.motivo, { tercero, tipo: s.tipo }),
  }));
}

/** Línea bajo los chips del formulario (lámina A7): de dónde sale cada sugerencia. */
export function textoChips(lista: SugeridaCategoria[]): string {
  if (lista.length === 0) return '';
  const partes = lista.map((x) => `${x.nombre}, ${x.motivo.charAt(0).toLowerCase()}${x.motivo.slice(1)}`);
  return `Sugeridas: ${partes.join('; ')}. Toca una para elegirla.`;
}

function diasEntre(desdeIso: string, hastaIso: string): number {
  const a = Date.UTC(Number(desdeIso.slice(0, 4)), Number(desdeIso.slice(5, 7)) - 1, Number(desdeIso.slice(8, 10)));
  const b = Date.UTC(Number(hastaIso.slice(0, 4)), Number(hastaIso.slice(5, 7)) - 1, Number(hastaIso.slice(8, 10)));
  return Math.round((b - a) / 86400000);
}

/** Motivo de un tercero de «Recientes» (lámina A3): uso reciente o frecuente. */
export function textoReciente(t: TerceroReciente, hoyIso: string, tipo: TipoSenal): string {
  if (t.motivo !== 'RECIENTE') return `Frecuente en ${DE_TIPO[tipo]}`;
  const d = diasEntre(t.ultimo_uso, hoyIso);
  if (d <= 0) return 'Usado hoy';
  if (d === 1) return 'Usado ayer';
  return `Usado hace ${d} días`;
}
