// ============================================================
// GAPTO MOBILE 2027
// Fichero: preferencias.ts
// Ruta: mobile/src/domain/preferencias.ts
// Descripción: Lógica pura de las preferencias de registro en REG-01 (F05-02 B2; F05-D026 §41.3/§41.4, E1/E2/E3; F05-D027 §42.7; lámina SET-PREF / REG-PREF v0.1, R01–R07, D-PREF-02..06). (1) Propuesta aplicable: la ÚNICA fuente de la propuesta de cuenta es el resolver del servidor (AJ-B1-09: sin fallback del cliente) y nunca se preselecciona una cuenta que no esté en la lista de elegibles (AJ-B1-11 / AJ-B1C-08); un origen que no se puede explicar no se aplica (D-PREF-02). (2) Aplicación por campo: solo a los campos que el usuario no ha tocado (D-PREF-03, «lo explícito gana»). (3) «Guardar como preferencia»: casillas iniciales (marcada si el valor final difiere de lo propuesto) y plan de escritura sobre la preferencia de ámbito «Una categoría» (alta, edición con el ESTADO COMPLETO —E05— o conflicto R07).
// Versión: 0.1.0 (F05-02 B2)
// Versión: 0.2.0 (F05-02 B3; lámina SET-PREF v0.1 S01–S06, D-PREF-01/04; AJ-B1-10): SOLO altas para Ajustes › Preferencias: ámbito visible (D-PREF-01), grupos y orden de la lista (S01), textos de lo que propone cada preferencia, preferencia existente del mismo ámbito (S03, «nunca crear otra»), estado del formulario (S02/S06) con el espejo del CHECK «propone algo» y el contenido COMPLETO que se envía (E05). Ninguna regla de elegibilidad: las cuentas y categorías ofrecidas son las de REG-01 y la disponibilidad de la cuenta la dice el servidor (`cuenta_disponible_hoy`).
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

// ------------------------------------------------------------------ Ajustes › Preferencias (F05-02 B3; lámina SET-PREF S01–S06)
/** Ámbito visible (D-PREF-01). OTRO = tipo de hecho sin categoría: solo creable por API, se lista con los generales. */
export type AmbitoPreferencia = 'GENERAL' | 'CATEGORIA' | 'OTRO';

export function ambitoDe(x: Pick<Preferencia, 'tipo_hecho_id' | 'categoria_id'>): AmbitoPreferencia {
  if (x.categoria_id !== null) return 'CATEGORIA';
  return x.tipo_hecho_id === null ? 'GENERAL' : 'OTRO';
}

export const TITULO_GENERAL = 'General';
export const TITULO_OTRO = 'Por tipo de gasto'; // DERIVADO (no está en la lámina)

export interface GruposPreferencias {
  todos: Preferencia[];
  categoria: Preferencia[];
  desactivadas: Preferencia[];
}

const ORDEN_AMBITO: Record<AmbitoPreferencia, number> = { GENERAL: 0, OTRO: 1, CATEGORIA: 2 };

/**
 * S01: «Todos los gastos» (habilitadas sin categoría), «Por categoría» (habilitadas con categoría) y «Desactivadas».
 * Orden (decisión de ejecución D2 de B3): por ámbito (General, tipo de gasto, categoría) y, dentro, por el rótulo
 * visible («Padre › Hija») con la colación del español; a igualdad, por id. Es estable y no depende del orden de la API.
 */
export function agruparPreferencias(lista: Preferencia[], rotulo: (x: Preferencia) => string): GruposPreferencias {
  const orden = (a: Preferencia, b: Preferencia) =>
    ORDEN_AMBITO[ambitoDe(a)] - ORDEN_AMBITO[ambitoDe(b)] || rotulo(a).localeCompare(rotulo(b), 'es') || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const ordenada = [...lista].sort(orden);
  return {
    todos: ordenada.filter((x) => x.enabled && ambitoDe(x) !== 'CATEGORIA'),
    categoria: ordenada.filter((x) => x.enabled && ambitoDe(x) === 'CATEGORIA'),
    desactivadas: ordenada.filter((x) => !x.enabled),
  };
}

/** D-PREF-04: la cuenta preferida no es elegible hoy (dato del servidor; nunca una regla del cliente). */
export function cuentaNoDisponible(x: Pick<Preferencia, 'cuenta_disponible_hoy'>): boolean {
  return x.cuenta_disponible_hoy === false;
}

/** Lo que propone, en el orden de la lámina: «Pagar con X», «Presupuesto: Sí/No». */
export function textosPropone(x: Pick<Preferencia, 'cuenta_default_id' | 'presupuestable_default'>, nombreCuenta: (id: string) => string | null): string[] {
  const r: string[] = [];
  if (x.cuenta_default_id !== null) r.push(`Pagar con ${nombreCuenta(x.cuenta_default_id) ?? 'una cuenta'}`);
  if (x.presupuestable_default !== null) r.push(`Presupuesto: ${siNo(x.presupuestable_default)}`);
  return r;
}

/** Preferencia HABILITADA del mismo ámbito «Todos los gastos» (categoría null) o «Una categoría» (S03; D4 de B2). */
export function preferenciaDeAmbito(lista: Preferencia[], categoriaId: string | null, excluirId: string | null = null): Preferencia | null {
  return (
    lista.find(
      (x) =>
        x.id !== excluirId && x.enabled && x.categoria_id === categoriaId && x.tipo_hecho_id === null && x.tercero_id === null && x.entidad_id === null,
    ) ?? null
  );
}

/** Valor del campo «Proponer cuenta»: una cuenta, «No proponer» (null) o la actual NO disponible (no se puede enviar). */
export type CuentaFormulario = string | null | { noDisponible: string };

export interface FormularioPreferencia {
  ambito: 'GENERAL' | 'CATEGORIA' | null;
  categoriaId: string | null;
  cuenta: CuentaFormulario;
  presupuestable: boolean | null;
}

export const FORMULARIO_NUEVO: FormularioPreferencia = Object.freeze({ ambito: null, categoriaId: null, cuenta: null, presupuestable: null });

/**
 * Formulario de edición desde la preferencia cargada. Una cuenta que el servidor marca como no disponible hoy, o que
 * no está entre las que ofrece REG-01, queda como «no disponible»: no se reenvía sin una elección explícita.
 */
export function formularioDesde(x: Preferencia, cuentas: CuentaPago[]): FormularioPreferencia {
  const id = x.cuenta_default_id;
  const fuera = id !== null && (cuentaNoDisponible(x) || !cuentas.some((c) => c.cuenta_id === id));
  return {
    ambito: x.categoria_id === null ? 'GENERAL' : 'CATEGORIA',
    categoriaId: x.categoria_id,
    cuenta: fuera ? { noDisponible: id } : id,
    presupuestable: x.presupuestable_default,
  };
}

/** Espejo del CHECK «propone algo» (ck_preferencias_registro__propone_valor). El servidor sigue siendo la guarda. */
export function proponeAlgo(f: Pick<FormularioPreferencia, 'cuenta' | 'presupuestable'>): boolean {
  return f.cuenta !== null || f.presupuestable !== null;
}

export type FaltaFormulario = 'AMBITO' | 'CATEGORIA' | 'PROPONER' | 'CUENTA_NO_DISPONIBLE';

/** Lo que impide «Guardar», en el orden del formulario; vacío = se puede guardar. */
export function faltaFormulario(f: FormularioPreferencia): FaltaFormulario[] {
  const r: FaltaFormulario[] = [];
  if (f.ambito === null) r.push('AMBITO');
  if (f.ambito === 'CATEGORIA' && f.categoriaId === null) r.push('CATEGORIA');
  if (!proponeAlgo(f)) r.push('PROPONER');
  if (f.cuenta !== null && typeof f.cuenta === 'object') r.push('CUENTA_NO_DISPONIBLE');
  return r;
}

/** Contenido COMPLETO que se envía (E05): alta con prioridad 100; edición con las claves y la prioridad de la existente. */
export function contenidoFormulario(f: FormularioPreferencia, base: Preferencia | null): ContenidoPreferencia {
  const cuenta = typeof f.cuenta === 'string' ? f.cuenta : null;
  if (base) {
    return {
      tipo_hecho_id: base.tipo_hecho_id,
      categoria_id: base.categoria_id,
      tercero_id: base.tercero_id,
      entidad_id: base.entidad_id,
      cuenta_default_id: cuenta,
      presupuestable_default: f.presupuestable,
      prioridad: base.prioridad,
    };
  }
  return {
    tipo_hecho_id: null,
    categoria_id: f.ambito === 'CATEGORIA' ? f.categoriaId : null,
    tercero_id: null,
    entidad_id: null,
    cuenta_default_id: cuenta,
    presupuestable_default: f.presupuestable,
    prioridad: 100,
  };
}
