// ============================================================
// GAPTO MOBILE 2027
// Fichero: categoria.ts
// Ruta: mobile/src/domain/categoria.ts
// Descripción: Modelo del árbol de categorías en el cliente (espejo de CategoriaNodoArbol y MagnitudCategoria de GET /v1/categorias). Reglas puras de F05 §22.2 C02 y F09 §12.97.2: elegibilidad para GASTO, visibilidad en el registro (elegible o con algún descendiente elegible), motivo de no seleccionable con prioridad fija, ruta de ancestros y construcción del árbol desde la lista plana. El ORDEN es el de la API (orden → nombre → id): el cliente no reordena. La lectura nunca es autoridad de persistencia: el servidor decide en cada escritura.
// Visibilidad en el registro (decisión de Moisés en sesión, contradicción F09 §12.97.2 / §12.97.3 y lámina R05): se muestra un nodo elegible, uno con algún descendiente visible, y también uno HABILITADO y de ámbito compatible pero NO capturable (no seleccionable, con motivo «Requiere un dato no disponible»). Las desactivadas y las de solo ingresos sin descendientes elegibles se ocultan.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): Editar orden (D-UI-01) — `moverHermano` (subir/bajar un puesto sobre el conjunto COMPLETO de hermanos, sin salir de los extremos) y `mismoOrden` (el orden editado coincide con el cargado: no se envía nada); `subcategoriasActivas` (subárbol completo, atravesando desactivadas, como AJ-S4-02) para la N de «Desactivar también sus N subcategorías». El cliente sigue sin reordenar la lectura: solo propone el orden que el servidor aplica en una llamada.
// ============================================================

export type Ambito = 'GASTO' | 'INGRESO' | 'AMBOS';
export type Naturaleza = 'GASTO' | 'INGRESO';

export interface MagnitudCategoria {
  magnitud_id: string;
  nombre: string;
  obligatoria: boolean;
  orden: number;
  enabled: boolean;
  unidad_default: string;
  precision_decimales: number;
  row_version: number;
}

/** Nodo tal como llega de GET /v1/categorias (lista plana ordenada por la API). */
export interface CategoriaNodo {
  id: string;
  parent_id: string | null;
  nombre: string;
  codigo: string | null;
  ambito: Ambito;
  enabled: boolean;
  orden: number;
  icon_key: string | null;
  presupuestable_default: boolean;
  row_version: number;
  magnitudes: MagnitudCategoria[];
  capturable: boolean;
  motivo_no_capturable: 'MAGNITUD_OBLIGATORIA_NO_DISPONIBLE' | null;
}

export interface Arbol {
  /** Nodos por id. */
  porId: Map<string, CategoriaNodo>;
  /** Hijos directos por id de padre ('' = raíz), en el orden de la API. */
  hijos: Map<string, CategoriaNodo[]>;
}

const RAIZ = '';

export function construirArbol(lista: CategoriaNodo[]): Arbol {
  const porId = new Map(lista.map((n) => [n.id, n]));
  const hijos = new Map<string, CategoriaNodo[]>();
  for (const n of lista) {
    // Un padre que no está en la lista (dato incoherente) no oculta al hijo: cuelga de la raíz.
    const clave = n.parent_id !== null && porId.has(n.parent_id) ? n.parent_id : RAIZ;
    const l = hijos.get(clave);
    if (l) l.push(n);
    else hijos.set(clave, [n]);
  }
  return { porId, hijos };
}

export function hijosDe(a: Arbol, padre: string | null): CategoriaNodo[] {
  return a.hijos.get(padre ?? RAIZ) ?? [];
}

/** Ancestros desde la raíz hasta el padre del nodo (sin el propio nodo). Tolera ciclos legacy. */
export function ancestros(a: Arbol, id: string): CategoriaNodo[] {
  const res: CategoriaNodo[] = [];
  const vistos = new Set<string>([id]);
  let actual = a.porId.get(id)?.parent_id ?? null;
  while (actual !== null && !vistos.has(actual)) {
    const n = a.porId.get(actual);
    if (!n) break;
    res.unshift(n);
    vistos.add(actual);
    actual = n.parent_id;
  }
  return res;
}

/** «Todas › Hogar» (migas del nivel/ruta visible del registro). */
export function rutaTexto(a: Arbol, id: string): string {
  return ['Todas', ...ancestros(a, id).map((n) => n.nombre)].join(' › ');
}

/** C02: elegible para la naturaleza del efecto (en este slice siempre GASTO). */
export function elegible(n: CategoriaNodo, naturaleza: Naturaleza = 'GASTO'): boolean {
  return n.enabled && (n.ambito === naturaleza || n.ambito === 'AMBOS') && n.capturable;
}

export function elegibleParaGasto(n: CategoriaNodo): boolean {
  return elegible(n, 'GASTO');
}

/** En el registro se muestra un nodo si es elegible, si está habilitado y es de ámbito compatible aunque
 *  no sea capturable (se ve con su motivo; F09 §12.97.3, lámina R05), o si tiene algún descendiente visible. */
export function visibleEnRegistro(a: Arbol, n: CategoriaNodo, naturaleza: Naturaleza = 'GASTO', _vistos = new Set<string>()): boolean {
  if (elegible(n, naturaleza)) return true;
  if (n.enabled && (n.ambito === naturaleza || n.ambito === 'AMBOS') && !n.capturable) return true;
  if (_vistos.has(n.id)) return false;
  _vistos.add(n.id);
  return hijosDe(a, n.id).some((h) => visibleEnRegistro(a, h, naturaleza, _vistos));
}

export type MotivoNoSeleccionable = 'Desactivada' | 'Solo ingresos' | 'Requiere un dato no disponible';

/** Motivo en texto de un nodo no seleccionable, con prioridad fija; null si es elegible. */
export function motivoNoSeleccionable(n: CategoriaNodo, naturaleza: Naturaleza = 'GASTO'): MotivoNoSeleccionable | null {
  if (!n.enabled) return 'Desactivada';
  // En este slice la naturaleza es siempre GASTO: el único ámbito incompatible es INGRESO.
  if (!(n.ambito === naturaleza || n.ambito === 'AMBOS')) return 'Solo ingresos';
  if (!n.capturable) return 'Requiere un dato no disponible';
  return null;
}

/** Magnitudes que se piden en el registro: las HABILITADAS de la categoría, en el orden de la API. */
export function magnitudesPedibles(n: CategoriaNodo): MagnitudCategoria[] {
  return n.magnitudes.filter((m) => m.enabled);
}

/** Descendientes (todo el subárbol) de un nodo, sin incluirlo. */
export function descendientes(a: Arbol, id: string): CategoriaNodo[] {
  const res: CategoriaNodo[] = [];
  const vistos = new Set<string>([id]);
  const pila = [...hijosDe(a, id)];
  while (pila.length) {
    const n = pila.shift()!;
    if (vistos.has(n.id)) continue;
    vistos.add(n.id);
    res.push(n);
    pila.push(...hijosDe(a, n.id));
  }
  return res;
}

/** Subcategorías activas de TODO el subárbol (atraviesa las desactivadas, como el servidor en AJ-S4-02). */
export function subcategoriasActivas(a: Arbol, id: string): CategoriaNodo[] {
  return descendientes(a, id).filter((n) => n.enabled);
}

/** Editar orden (D-UI-01): mueve el elemento `i` un puesto arriba (-1) o abajo (+1); en los extremos no cambia nada. */
export function moverHermano<T>(lista: readonly T[], i: number, delta: -1 | 1): T[] {
  const j = i + delta;
  const res = [...lista];
  if (i < 0 || i >= lista.length || j < 0 || j >= lista.length) return res;
  [res[i], res[j]] = [res[j], res[i]];
  return res;
}

/** El orden editado coincide con el cargado (mismos ids en la misma posición). */
export function mismoOrden(a: readonly { id: string }[], b: readonly { id: string }[]): boolean {
  return a.length === b.length && a.every((n, i) => n.id === b[i].id);
}
