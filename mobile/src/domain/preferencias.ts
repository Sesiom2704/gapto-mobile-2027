// ============================================================
// GAPTO MOBILE 2027
// Fichero: preferencias.ts
// Ruta: mobile/src/domain/preferencias.ts
// Descripción: Lógica pura de las preferencias de registro en REG-01 (F05-02 B2; F05-D026 §41.3/§41.4, E1/E2/E3; F05-D027 §42.7; lámina SET-PREF / REG-PREF v0.1, R01–R07, D-PREF-02..06). (1) Propuesta aplicable: la ÚNICA fuente de la propuesta de cuenta es el resolver del servidor (AJ-B1-09: sin fallback del cliente) y nunca se preselecciona una cuenta que no esté en la lista de elegibles (AJ-B1-11 / AJ-B1C-08); un origen que no se puede explicar no se aplica (D-PREF-02). (2) Aplicación por campo: solo a los campos que el usuario no ha tocado (D-PREF-03, «lo explícito gana»). (3) «Guardar como preferencia»: casillas iniciales (marcada si el valor final difiere de lo propuesto) y plan de escritura sobre la preferencia de ámbito «Una categoría» (alta, edición con el ESTADO COMPLETO —E05— o conflicto R07).
// Versión: 0.1.0 (F05-02 B2)
// ============================================================

import type { ContenidoPreferencia, CuentaPago, OrigenPropuesta, Preferencia, PropuestaRegistro } from '../api/cliente';
import type { Borrador, OrigenPropuestaCampo, PayloadGastoPagado } from './intencion';

export interface CampoPropuesto<T> {
  valor: T;
  origen: OrigenPropuestaCampo;
}

/** Propuesta que el formulario puede mostrar y aplicar (cada campo con su origen explicable). */
export interface PropuestaAplicable {
  cuenta: CampoPropuesto<string> | null;
  presupuestable: CampoPropuesto<boolean> | null;
}

export const SIN_PROPUESTA: PropuestaAplicable = Object.freeze({ cuenta: null, presupuestable: null });

export const TEXTO_ELEGIDA = 'Elegida por ti.';

/** Texto de origen visible bajo el campo (lámina R02; D-PREF-02). */
export function textoOrigen(o: OrigenPropuestaCampo, categoria: string | null): string {
  if (o === 'PREFERENCIA_CATEGORIA') return `Propuesta: tu preferencia para ${categoria ?? ''}.`;
  if (o === 'PREFERENCIA_GENERAL') return 'Propuesta: tu preferencia general.';
  return 'Propuesta: es tu única cuenta disponible.';
}

export type IndicePreferencias = ReadonlyMap<string, Preferencia>;

export function indexar(lista: Preferencia[]): IndicePreferencias {
  return new Map(lista.map((x) => [x.id, x]));
}

/** ¿Hace falta la lista de preferencias para explicar algún origen de la propuesta? */
export function faltanPreferencias(p: PropuestaRegistro, indice: IndicePreferencias | null): boolean {
  return [p.cuenta?.origen, p.presupuestable?.origen].some(
    (o) => o !== undefined && o.capa === 'PREFERENCIA' && (indice === null || !indice.has(o.preferencia_id ?? '')),
  );
}

/** Origen explicable de un campo, o null si no se puede explicar (entonces no se aplica). */
function origenCampo(o: OrigenPropuesta, campo: 'cuenta' | 'presupuestable', indice: IndicePreferencias | null): OrigenPropuestaCampo | null {
  if (o.capa === 'DEFAULT_GENERAL') return campo === 'cuenta' ? 'UNICA' : null; // presupuestable no tiene default general (E1)
  const pref = indice?.get(o.preferencia_id ?? '');
  if (!pref) return null;
  return pref.categoria_id !== null ? 'PREFERENCIA_CATEGORIA' : 'PREFERENCIA_GENERAL';
}

/** Propuesta aplicable desde la respuesta del resolver y la lista de cuentas visible. */
export function propuestaAplicable(p: PropuestaRegistro, indice: IndicePreferencias | null, lista: CuentaPago[]): PropuestaAplicable {
  let cuenta: CampoPropuesto<string> | null = null;
  if (p.cuenta && lista.some((x) => x.cuenta_id === p.cuenta!.valor)) {
    const origen = origenCampo(p.cuenta.origen, 'cuenta', indice);
    if (origen) cuenta = { valor: p.cuenta.valor, origen };
  }
  let presupuestable: CampoPropuesto<boolean> | null = null;
  if (p.presupuestable) {
    const origen = origenCampo(p.presupuestable.origen, 'presupuestable', indice);
    if (origen) presupuestable = { valor: p.presupuestable.valor, origen };
  }
  return { cuenta, presupuestable };
}

/** Aplica la propuesta SOLO a los campos no tocados; sin propuesta, el campo queda sin preselección (R01). */
export function aplicarPropuesta(b: Borrador, ap: PropuestaAplicable, lista: CuentaPago[]): Borrador {
  let x: Borrador = b;
  if (b.cuentaOrigen !== 'USUARIO') {
    if (ap.cuenta) {
      const sel = lista.find((c) => c.cuenta_id === ap.cuenta!.valor);
      x = {
        ...x,
        cuentaId: ap.cuenta.valor,
        cuentaOrigen: 'INFERIDO',
        cuentaPropuesta: ap.cuenta.origen,
        propuesta: sel ? sel.propuesta_financiacion : null,
        propuestaRechazada: b.cuentaId === ap.cuenta.valor ? b.propuestaRechazada : false,
      };
    } else {
      x = { ...x, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null, propuesta: null, propuestaRechazada: false };
    }
  }
  if (b.presupuestableOrigen !== 'USUARIO') {
    x = ap.presupuestable
      ? { ...x, presupuestable: ap.presupuestable.valor, presupuestableOrigen: 'INFERIDO', presupuestablePropuesta: ap.presupuestable.origen }
      : { ...x, presupuestable: null, presupuestableOrigen: 'PENDIENTE', presupuestablePropuesta: null };
  }
  return x;
}

// ------------------------------------------------------------------ «Guardar como preferencia» (R05–R07)
export type CampoRecordable = 'cuenta' | 'presupuestable';

/** Valores sellados del gasto que se pueden recordar. */
export interface ValoresFinales {
  cuenta: string;
  presupuestable: boolean;
}

/** Lo que el resolver proponía para esa categoría y fecha (sin propuesta = null). */
export interface ValoresPropuestos {
  cuenta: string | null;
  presupuestable: boolean | null;
}

export type Casillas = Record<CampoRecordable, boolean>;

/** Marcada si el valor final difiere de lo propuesto; null si coinciden ambos (la tarjeta no aparece). */
export function casillasIniciales(f: ValoresFinales, p: ValoresPropuestos | null): Casillas | null {
  const cuenta = f.cuenta !== (p?.cuenta ?? null);
  const presupuestable = f.presupuestable !== (p?.presupuestable ?? null);
  return cuenta || presupuestable ? { cuenta, presupuestable } : null;
}

/** Instantánea de la última propuesta recibida en el formulario (valores del resolver tal cual). */
export interface PropuestaVista {
  fecha: string;
  categoriaId: string | null;
  valores: ValoresPropuestos;
}

export function valoresPropuestos(p: PropuestaRegistro): ValoresPropuestos {
  return { cuenta: p.cuenta?.valor ?? null, presupuestable: p.presupuestable?.valor ?? null };
}

/** Datos de la tarjeta R05 para la intención SELLADA; null si no aparece (D-PREF-05 o nada que recordar). */
export function datosRecordables(
  payload: Readonly<PayloadGastoPagado>,
  vista: PropuestaVista | null,
): { categoriaId: string; finales: ValoresFinales; casillas: Casillas } | null {
  if (payload.categoria.estado !== 'CATEGORIA') return null; // «Sin categoría»: nunca una preferencia general sin querer
  const categoriaId = payload.categoria.categoria_id;
  const finales = { cuenta: payload.cuenta_id, presupuestable: payload.presupuestable };
  // Solo vale la propuesta de ESA categoría y fecha; sin ella, todo cuenta como distinto.
  const propuestos = vista && vista.categoriaId === categoriaId && vista.fecha === payload.fecha_hecho ? vista.valores : null;
  const casillas = casillasIniciales(finales, propuestos);
  return casillas ? { categoriaId, finales, casillas } : null;
}

/** Preferencia habilitada de ámbito «Una categoría» (categoria_id = X, tipo de hecho NULL). */
export function preferenciaDeCategoria(lista: Preferencia[], categoriaId: string): Preferencia | null {
  return (
    lista.find(
      (x) => x.enabled && x.categoria_id === categoriaId && x.tipo_hecho_id === null && x.tercero_id === null && x.entidad_id === null,
    ) ?? null
  );
}

export type PlanGuardado =
  | { tipo: 'NADA' }
  | { tipo: 'ALTA'; contenido: ContenidoPreferencia }
  | { tipo: 'EDITAR'; existente: Preferencia; contenido: ContenidoPreferencia }
  | { tipo: 'CONFLICTO'; existente: Preferencia; contenido: ContenidoPreferencia; campos: CampoRecordable[] };

/** Estado COMPLETO tras recordar los campos marcados: los no marcados conservan su valor actual (E05). */
export function estadoCompleto(e: Preferencia, f: ValoresFinales, c: Casillas): ContenidoPreferencia {
  return {
    tipo_hecho_id: e.tipo_hecho_id,
    categoria_id: e.categoria_id,
    tercero_id: e.tercero_id,
    entidad_id: e.entidad_id,
    cuenta_default_id: c.cuenta ? f.cuenta : e.cuenta_default_id,
    presupuestable_default: c.presupuestable ? f.presupuestable : e.presupuestable_default,
    prioridad: e.prioridad,
  };
}

export function planificarGuardado(lista: Preferencia[], categoriaId: string, f: ValoresFinales, c: Casillas): PlanGuardado {
  if (!c.cuenta && !c.presupuestable) return { tipo: 'NADA' };
  const e = preferenciaDeCategoria(lista, categoriaId);
  if (!e) {
    return {
      tipo: 'ALTA',
      contenido: {
        tipo_hecho_id: null,
        categoria_id: categoriaId,
        tercero_id: null,
        entidad_id: null,
        cuenta_default_id: c.cuenta ? f.cuenta : null,
        presupuestable_default: c.presupuestable ? f.presupuestable : null,
        prioridad: 100,
      },
    };
  }
  const contenido = estadoCompleto(e, f, c);
  const campos: CampoRecordable[] = [];
  if (c.cuenta && e.cuenta_default_id !== null && e.cuenta_default_id !== f.cuenta) campos.push('cuenta');
  if (c.presupuestable && e.presupuestable_default !== null && e.presupuestable_default !== f.presupuestable) campos.push('presupuestable');
  return campos.length > 0 ? { tipo: 'CONFLICTO', existente: e, contenido, campos } : { tipo: 'EDITAR', existente: e, contenido };
}

export function siNo(v: boolean): string {
  return v ? 'Sí' : 'No';
}
