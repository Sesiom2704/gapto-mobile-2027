// ============================================================
// GAPTO MOBILE 2027
// Fichero: preferencias.ts
// Ruta: mobile/src/domain/preferencias.ts
// Descripción: Lógica pura de las preferencias de registro en REG-01 (F05-02 B2; F05-D026 §41.3/§41.4, E1/E2/E3; F05-D027 §42.7; lámina SET-PREF / REG-PREF v0.1, R01–R07, D-PREF-02..06). (1) Propuesta aplicable: la ÚNICA fuente de la propuesta de cuenta es el resolver del servidor (AJ-B1-09: sin fallback del cliente) y nunca se preselecciona una cuenta que no esté en la lista de elegibles (AJ-B1-11 / AJ-B1C-08); un origen que no se puede explicar no se aplica (D-PREF-02). (2) Aplicación por campo: solo a los campos que el usuario no ha tocado (D-PREF-03, «lo explícito gana»). (3) «Guardar como preferencia»: casillas iniciales (marcada si el valor final difiere de lo propuesto) y plan de escritura sobre la preferencia de ámbito «Una categoría» (alta, edición con el ESTADO COMPLETO —E05— o conflicto R07).
// Versión: 0.1.0 (F05-02 B2)
// Versión: 0.3.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E2/E3; F05-D032 C4): se retira la preferencia sin tipo. «Todos los gastos» y «Una categoría» llevan SIEMPRE el tipo GASTO (`tipoGasto`, id que informa GET /v1/preferencias): el alta lo envía y las búsquedas del ámbito lo exigen. Una preferencia sin tipo (anterior a la conversión C4) ya no es de ningún ámbito vigente.
// Versión: 0.2.0 (F05-02 B3; lámina SET-PREF v0.1 S01–S06, D-PREF-01/04; AJ-B1-10): SOLO altas para Ajustes › Preferencias: ámbito visible (D-PREF-01), grupos y orden de la lista (S01), textos de lo que propone cada preferencia, preferencia existente del mismo ámbito (S03, «nunca crear otra»), estado del formulario (S02/S06) con el espejo del CHECK «propone algo» y el contenido COMPLETO que se envía (E05). Ninguna regla de elegibilidad: las cuentas y categorías ofrecidas son las de REG-01 y la disponibilidad de la cuenta la dice el servidor (`cuenta_disponible_hoy`).
// Versión: 0.5.0 (F05-03/F05-04 J2 §2.3/§2.4; lámina REG-DYN G01/I01/N01 y REG-PLT R01–R05): propuesta del registro por tipo con la capa plantilla (GET /v1/registro/propuesta): origen visible «De tu plantilla <nombre>.», «Propuesta: tu preferencia para <tercero>.» y, en ingresos, «… para todos los ingresos.»; «Guardar como preferencia» para el tercero O para la categoría (nunca ambos) con la misma lógica de alta / edición / conflicto.
// Versión: 0.4.0 (F05-03/F05-04 J2 §2.5; F05 §46.4 R6, §46.5 E2/E3; lámina REG-DYN / SET-TH / SET-CTX v0.1 S04): Ajustes › Preferencias con CUATRO ámbitos: «Todos los gastos», «Todos los ingresos», «Una categoría» y «Un tercero»; los dos últimos con tipo Gasto/Ingreso, siempre enviado. Categoría + tercero no se ofrece (PREFERENCIA_AMBITO_NO_ADMITIDO). Grupo nuevo «Por tercero». «Proponer cuenta» del tipo INGRESO usa las cuentas elegibles para cobrar (servidor).
// ============================================================

import type { ContenidoPreferencia, CuentaPago, OrigenPropuesta, Preferencia, PropuestaRegistro, PropuestaRegistroTipo, TiposRegistro } from '../api/cliente';
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

/** Texto de origen visible bajo el campo (lámina R02; D-PREF-02; F05-04: plantilla, tercero e ingresos). */
export function textoOrigen(
  o: OrigenPropuestaCampo,
  categoria: string | null,
  extra: { tercero?: string | null; plantilla?: string | null; tipo?: 'GASTO' | 'INGRESO' } = {},
): string {
  if (o === 'PLANTILLA') return `De tu plantilla ${extra.plantilla ?? ''}.`;
  if (o === 'PREFERENCIA_TERCERO') return `Propuesta: tu preferencia para ${extra.tercero ?? ''}.`;
  if (o === 'PREFERENCIA_CATEGORIA') return `Propuesta: tu preferencia para ${categoria ?? ''}.`;
  if (o === 'PREFERENCIA_GENERAL') return extra.tipo === 'INGRESO' ? 'Propuesta: tu preferencia para todos los ingresos.' : 'Propuesta: tu preferencia general.';
  return 'Propuesta: es tu única cuenta disponible.';
}

// ------------------------------------------------------------------ registro por tipo (F05-04 J2 §2.3/§2.4)
type OrigenTipo = PropuestaRegistroTipo['campos']['cuenta'] extends infer X ? (X extends { origen: infer O } ? O : never) : never;

/** Origen explicable de un campo de la propuesta por tipo (capa plantilla, preferencia o default). */
function origenCampoTipo(o: OrigenTipo, campo: 'cuenta' | 'presupuestable', indice: IndicePreferencias | null): OrigenPropuestaCampo | null {
  if (o.capa === 'PLANTILLA') return 'PLANTILLA';
  if (o.capa === 'DEFAULT_GENERAL') return campo === 'cuenta' ? 'UNICA' : null;
  const pref = indice?.get(o.preferencia_id ?? '');
  if (!pref) return null;
  if (pref.tercero_id !== null) return 'PREFERENCIA_TERCERO';
  return pref.categoria_id !== null ? 'PREFERENCIA_CATEGORIA' : 'PREFERENCIA_GENERAL';
}

/** ¿Hace falta la lista de preferencias para explicar algún origen de la propuesta por tipo? */
export function faltanPreferenciasTipo(p: PropuestaRegistroTipo, indice: IndicePreferencias | null): boolean {
  return [p.campos.cuenta?.origen, p.campos.presupuestable?.origen].some(
    (o) => o !== undefined && o.capa === 'PREFERENCIA' && (indice === null || !indice.has(o.preferencia_id ?? '')),
  );
}

/** Propuesta aplicable (cuenta y presupuesto) de GET /v1/registro/propuesta; la cuenta solo si está en la lista visible. */
export function propuestaAplicableTipo(p: PropuestaRegistroTipo, indice: IndicePreferencias | null, lista: { cuenta_id: string }[]): PropuestaAplicable {
  let cuenta: CampoPropuesto<string> | null = null;
  const pc = p.campos.cuenta;
  if (pc && lista.some((x) => x.cuenta_id === pc.valor)) {
    const origen = origenCampoTipo(pc.origen, 'cuenta', indice);
    if (origen) cuenta = { valor: pc.valor, origen };
  }
  let presupuestable: CampoPropuesto<boolean> | null = null;
  const pp = p.campos.presupuestable;
  if (pp) {
    const origen = origenCampoTipo(pp.origen, 'presupuestable', indice);
    if (origen) presupuestable = { valor: pp.valor, origen };
  }
  return { cuenta, presupuestable };
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
  /** F05-04: tercero y plantilla del contexto de la propuesta (ausentes = ninguno). */
  terceroId?: string | null;
  plantillaId?: string | null;
}

/** Ámbito de «Guardar como preferencia» en el registro por tipo: el tercero O la categoría (nunca ambos). */
export interface AmbitoRecordable {
  clave: 'CATEGORIA' | 'TERCERO';
  id: string;
  nombre: string;
}

/**
 * Datos de la tarjeta para el registro por tipo (F05-04): ámbitos posibles (tercero primero, como la lámina N01:
 * «Para ALDI / Para Supermercados»), valores finales y casillas. null si no hay ámbito o nada que recordar.
 */
export function datosRecordablesTipo(
  final: { fecha: string; categoriaId: string | null; terceroId: string | null; cuenta: string; presupuestable: boolean },
  nombres: { categoria: string | null; tercero: string | null },
  vista: PropuestaVista | null,
): { ambitos: AmbitoRecordable[]; finales: ValoresFinales; casillas: Casillas } | null {
  const ambitos: AmbitoRecordable[] = [];
  if (final.terceroId) ambitos.push({ clave: 'TERCERO', id: final.terceroId, nombre: nombres.tercero ?? 'este tercero' });
  if (final.categoriaId) ambitos.push({ clave: 'CATEGORIA', id: final.categoriaId, nombre: nombres.categoria ?? 'esta categoría' });
  if (ambitos.length === 0) return null;
  const finales = { cuenta: final.cuenta, presupuestable: final.presupuestable };
  const mismaVista =
    vista && vista.fecha === final.fecha && vista.categoriaId === final.categoriaId && (vista.terceroId ?? null) === final.terceroId && !vista.plantillaId;
  const casillas = casillasIniciales(finales, mismaVista ? vista.valores : null);
  return casillas ? { ambitos, finales, casillas } : null;
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

/** Preferencia habilitada de ámbito «Una categoría» (categoria_id = X, tipo GASTO; E3). */
export function preferenciaDeCategoria(lista: Preferencia[], categoriaId: string, tipoGasto: string): Preferencia | null {
  return (
    lista.find(
      (x) => x.enabled && x.categoria_id === categoriaId && x.tipo_hecho_id === tipoGasto && x.tercero_id === null && x.entidad_id === null,
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

export function planificarGuardado(
  lista: Preferencia[],
  categoriaId: string,
  f: ValoresFinales,
  c: Casillas,
  tipoGasto: string,
): PlanGuardado {
  return planificarGuardadoClave(lista, { categoriaId, terceroId: null }, f, c, tipoGasto);
}

/** Igual que `planificarGuardado` para la clave (tipo, categoría) o (tipo, tercero) del registro por tipo (F05-04). */
export function planificarGuardadoClave(
  lista: Preferencia[],
  clave: { categoriaId: string | null; terceroId: string | null },
  f: ValoresFinales,
  c: Casillas,
  tipoId: string,
): PlanGuardado {
  if (!c.cuenta && !c.presupuestable) return { tipo: 'NADA' };
  const e =
    clave.terceroId === null && clave.categoriaId !== null
      ? preferenciaDeCategoria(lista, clave.categoriaId, tipoId)
      : preferenciaDeClave(lista, { tipo: tipoId, categoriaId: clave.categoriaId, terceroId: clave.terceroId });
  if (!e) {
    return {
      tipo: 'ALTA',
      contenido: {
        tipo_hecho_id: tipoId,
        categoria_id: clave.categoriaId,
        tercero_id: clave.terceroId,
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
/**
 * Ámbito visible (D-PREF-01; E3; F05-04 R6). GENERAL = «Todos los gastos» (tipo GASTO sin categoría ni tercero).
 * INGRESOS = «Todos los ingresos» (tipo INGRESO sin categoría ni tercero). CATEGORIA = «Una categoría» (con tipo).
 * TERCERO = «Un tercero» (con tipo). OTRO = otro tipo sin categoría ni tercero, o una preferencia sin tipo anterior
 * a la conversión C4: solo creable por API, se lista con las generales.
 */
export type AmbitoPreferencia = 'GENERAL' | 'INGRESOS' | 'CATEGORIA' | 'TERCERO' | 'OTRO';

export function ambitoDe(
  x: Pick<Preferencia, 'tipo_hecho_id' | 'categoria_id'> & Partial<Pick<Preferencia, 'tercero_id'>>,
  tipoGasto: string | null,
  tipoIngreso: string | null = null,
): AmbitoPreferencia {
  if (x.categoria_id !== null) return 'CATEGORIA';
  if (x.tercero_id !== undefined && x.tercero_id !== null) return 'TERCERO';
  if (tipoGasto !== null && x.tipo_hecho_id === tipoGasto) return 'GENERAL';
  return tipoIngreso !== null && x.tipo_hecho_id === tipoIngreso ? 'INGRESOS' : 'OTRO';
}

/** Tipo de registro de una preferencia (null si no es GASTO ni INGRESO). */
export function tipoDe(x: Pick<Preferencia, 'tipo_hecho_id'>, tipos: TiposRegistro | null): 'GASTO' | 'INGRESO' | null {
  if (!tipos) return null;
  return x.tipo_hecho_id === tipos.GASTO ? 'GASTO' : x.tipo_hecho_id === tipos.INGRESO ? 'INGRESO' : null;
}

export const TITULO_GENERAL = 'General';
export const TITULO_INGRESOS = 'Todos los ingresos';
export const TITULO_OTRO = 'Por tipo de gasto'; // DERIVADO (no está en la lámina)

export interface GruposPreferencias {
  todos: Preferencia[];
  categoria: Preferencia[];
  tercero: Preferencia[];
  desactivadas: Preferencia[];
}

const ORDEN_AMBITO: Record<AmbitoPreferencia, number> = { GENERAL: 0, INGRESOS: 1, OTRO: 2, CATEGORIA: 3, TERCERO: 4 };

/**
 * S01: «Todos los gastos» (habilitadas sin categoría ni tercero), «Por categoría», «Por tercero» y «Desactivadas».
 * Orden (decisión de ejecución D2 de B3): por ámbito (General, ingresos, tipo de gasto, categoría, tercero) y, dentro,
 * por el rótulo visible con la colación del español; a igualdad, por id. Es estable y no depende del orden de la API.
 */
export function agruparPreferencias(
  lista: Preferencia[],
  rotulo: (x: Preferencia) => string,
  tipoGasto: string | null,
  tipoIngreso: string | null = null,
): GruposPreferencias {
  const amb = (x: Preferencia) => ambitoDe(x, tipoGasto, tipoIngreso);
  const orden = (a: Preferencia, b: Preferencia) =>
    ORDEN_AMBITO[amb(a)] - ORDEN_AMBITO[amb(b)] || rotulo(a).localeCompare(rotulo(b), 'es') || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const ordenada = [...lista].sort(orden);
  return {
    todos: ordenada.filter((x) => x.enabled && amb(x) !== 'CATEGORIA' && amb(x) !== 'TERCERO'),
    categoria: ordenada.filter((x) => x.enabled && amb(x) === 'CATEGORIA'),
    tercero: ordenada.filter((x) => x.enabled && amb(x) === 'TERCERO'),
    desactivadas: ordenada.filter((x) => !x.enabled),
  };
}

/** D-PREF-04: la cuenta preferida no es elegible hoy (dato del servidor; nunca una regla del cliente). */
export function cuentaNoDisponible(x: Pick<Preferencia, 'cuenta_disponible_hoy'>): boolean {
  return x.cuenta_disponible_hoy === false;
}

/** Lo que propone, en el orden de la lámina: «Pagar con X» («Cobrar en X» si es de ingresos), «Presupuesto: Sí/No». */
export function textosPropone(
  x: Pick<Preferencia, 'cuenta_default_id' | 'presupuestable_default'>,
  nombreCuenta: (id: string) => string | null,
  tipo: 'GASTO' | 'INGRESO' | null = 'GASTO',
): string[] {
  const r: string[] = [];
  if (x.cuenta_default_id !== null) r.push(`${tipo === 'INGRESO' ? 'Cobrar en' : 'Pagar con'} ${nombreCuenta(x.cuenta_default_id) ?? 'una cuenta'}`);
  if (x.presupuestable_default !== null) r.push(`Presupuesto: ${siNo(x.presupuestable_default)}`);
  return r;
}

/** Preferencia HABILITADA del mismo ámbito «Todos los gastos» (categoría null) o «Una categoría» (S03; D4 de B2), tipo GASTO (E3). */
export function preferenciaDeAmbito(
  lista: Preferencia[],
  categoriaId: string | null,
  tipoGasto: string,
  excluirId: string | null = null,
): Preferencia | null {
  return preferenciaDeClave(lista, { tipo: tipoGasto, categoriaId, terceroId: null }, excluirId);
}

/** Preferencia HABILITADA con la MISMA clave (tipo, categoría, tercero; sin contexto) (S03 con los cuatro ámbitos). */
export function preferenciaDeClave(
  lista: Preferencia[],
  clave: { tipo: string; categoriaId: string | null; terceroId: string | null },
  excluirId: string | null = null,
): Preferencia | null {
  return (
    lista.find(
      (x) =>
        x.id !== excluirId &&
        x.enabled &&
        x.tipo_hecho_id === clave.tipo &&
        x.categoria_id === clave.categoriaId &&
        x.tercero_id === clave.terceroId &&
        x.entidad_id === null,
    ) ?? null
  );
}

/** Valor del campo «Proponer cuenta»: una cuenta, «No proponer» (null) o la actual NO disponible (no se puede enviar). */
export type CuentaFormulario = string | null | { noDisponible: string };

export type AmbitoFormulario = 'GENERAL' | 'INGRESOS' | 'CATEGORIA' | 'TERCERO';

export interface FormularioPreferencia {
  ambito: AmbitoFormulario | null;
  categoriaId: string | null;
  cuenta: CuentaFormulario;
  presupuestable: boolean | null;
  /** Tercero del ámbito «Un tercero». */
  terceroId?: string | null;
  /** Tipo de los ámbitos «Una categoría» y «Un tercero» (GASTO si se omite: el de F05-02). */
  tipo?: 'GASTO' | 'INGRESO';
}

export const FORMULARIO_NUEVO: FormularioPreferencia = Object.freeze({ ambito: null, categoriaId: null, cuenta: null, presupuestable: null });

/** Tipo efectivo del formulario: «Todos los ingresos» es INGRESO; «Todos los gastos», GASTO; el resto, el elegido. */
export function tipoFormulario(f: Pick<FormularioPreferencia, 'ambito' | 'tipo'>): 'GASTO' | 'INGRESO' {
  if (f.ambito === 'INGRESOS') return 'INGRESO';
  if (f.ambito === 'GENERAL') return 'GASTO';
  return f.tipo ?? 'GASTO';
}

/**
 * Formulario de edición desde la preferencia cargada. Una cuenta que el servidor marca como no disponible hoy, o que
 * no está entre las que ofrece el registro de su tipo, queda como «no disponible»: no se reenvía sin una elección explícita.
 */
export function formularioDesde(x: Preferencia, cuentas: CuentaPago[] | { cuenta_id: string }[], tipos: TiposRegistro | null = null): FormularioPreferencia {
  const id = x.cuenta_default_id;
  const fuera = id !== null && (cuentaNoDisponible(x) || !cuentas.some((c) => c.cuenta_id === id));
  const tipo = tipoDe(x, tipos) ?? 'GASTO';
  const amb = ambitoDe(x, tipos?.GASTO ?? null, tipos?.INGRESO ?? null);
  return {
    ambito: amb === 'OTRO' ? 'GENERAL' : amb,
    categoriaId: x.categoria_id,
    cuenta: fuera ? { noDisponible: id } : id,
    presupuestable: x.presupuestable_default,
    terceroId: x.tercero_id,
    tipo,
  };
}

/** Espejo del CHECK «propone algo» (ck_preferencias_registro__propone_valor). El servidor sigue siendo la guarda. */
export function proponeAlgo(f: Pick<FormularioPreferencia, 'cuenta' | 'presupuestable'>): boolean {
  return f.cuenta !== null || f.presupuestable !== null;
}

export type FaltaFormulario = 'AMBITO' | 'CATEGORIA' | 'TERCERO' | 'PROPONER' | 'CUENTA_NO_DISPONIBLE';

/** Lo que impide «Guardar», en el orden del formulario; vacío = se puede guardar. */
export function faltaFormulario(f: FormularioPreferencia): FaltaFormulario[] {
  const r: FaltaFormulario[] = [];
  if (f.ambito === null) r.push('AMBITO');
  if (f.ambito === 'CATEGORIA' && f.categoriaId === null) r.push('CATEGORIA');
  if (f.ambito === 'TERCERO' && !f.terceroId) r.push('TERCERO');
  if (!proponeAlgo(f)) r.push('PROPONER');
  if (f.cuenta !== null && typeof f.cuenta === 'object') r.push('CUENTA_NO_DISPONIBLE');
  return r;
}

/**
 * Contenido COMPLETO que se envía (E05): alta con prioridad 100 y SIEMPRE con tipo (E3); edición con las claves y la
 * prioridad de la existente. `tipos` admite el id del tipo GASTO (uso de F05-02) o los dos ids de la lista.
 */
export function contenidoFormulario(f: FormularioPreferencia, base: Preferencia | null, tipos: string | TiposRegistro): ContenidoPreferencia {
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
  const ids: TiposRegistro = typeof tipos === 'string' ? { GASTO: tipos, INGRESO: tipos } : tipos;
  const tipo = tipoFormulario(f);
  return {
    tipo_hecho_id: ids[tipo],
    categoria_id: f.ambito === 'CATEGORIA' ? f.categoriaId : null,
    tercero_id: f.ambito === 'TERCERO' ? f.terceroId ?? null : null,
    entidad_id: null,
    cuenta_default_id: cuenta,
    presupuestable_default: f.presupuestable,
    prioridad: 100,
  };
}
