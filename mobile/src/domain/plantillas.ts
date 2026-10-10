// ============================================================
// GAPTO MOBILE 2027
// Fichero: plantillas.ts
// Ruta: mobile/src/domain/plantillas.ts
// Descripción: Lógica pura de Ajustes › Plantillas y de «Guardar como plantilla» (F05-03 J2 §2.4/§2.5; F05 §45.3, §46.3 A7; lámina SET-PLT / REG-PLT / HOME-QA v0.2 S02–S05, R06; REG-DYN S05). Formulario de la plantilla (nombre, tipo, tercero, categoría, contexto, cuenta y presupuesto propuestos) con el espejo del CHECK «propone algo» y lo que falta; contenido COMPLETO que se envía (E05: la edición conserva el estado completo con row_version); y plan del acceso en Inicio (alta, edición del nombre corto o icono, retirada o nada). El nombre de la plantilla nunca se autocompleta (R06). Las reglas de elegibilidad, límite de 3 y unicidad del nombre las decide el servidor.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.4/§2.5)
// ============================================================

import type { AccionRapida, ContenidoPlantilla, Plantilla, TiposRegistro } from '../api/cliente';

export type TipoPlantilla = 'GASTO' | 'INGRESO';

export interface FormularioPlantilla {
  nombre: string;
  tipo: TipoPlantilla | null;
  terceroId: string | null;
  categoriaId: string | null;
  contextoId: string | null;
  cuentaId: string | null;
  presupuestable: boolean | null;
  enInicio: boolean;
  nombreCorto: string;
  iconoKey: string | null;
}

export const FORMULARIO_PLANTILLA_NUEVO: FormularioPlantilla = Object.freeze({
  nombre: '',
  tipo: null,
  terceroId: null,
  categoriaId: null,
  contextoId: null,
  cuentaId: null,
  presupuestable: null,
  enInicio: false,
  nombreCorto: '',
  iconoKey: null,
});

export const TEXTO_CHECK_PLANTILLA = 'Tiene que guardar al menos una de estas cosas: tercero, categoría, contexto, cuenta o presupuesto.';
export const TEXTO_INTRO_PLANTILLAS =
  'Una plantilla rellena el registro de un gasto con lo que repites. Siempre puedes cambiar los valores antes de guardar.';
export const TEXTO_SOLO_NUEVOS_PLANTILLA = 'Solo afecta a gastos nuevos. Los ya registrados no cambian.';
export const TEXTO_DESACTIVADA_PLANTILLA = 'Desactivada: deja de usarse y sale de Inicio. Si la reactivas, no vuelve a Inicio sola; actívalo tú.';
export const TEXTO_LIMITE = 'Inicio ya muestra 3 plantillas. Quita una para añadir esta.';
export const textoNombreRepetido = (nombre: string) => `Ya tienes una plantilla «${nombre}». Usa otro nombre o edita la existente.`;
export const LONGITUD_NOMBRE_PLANTILLA = 100;
export const LONGITUD_NOMBRE_ACCESO = 80;

export function tipoDePlantilla(x: Pick<Plantilla, 'tipo_hecho_id'> & { tipo?: TipoPlantilla | null }, tipos: TiposRegistro | null): TipoPlantilla | null {
  if (x.tipo) return x.tipo;
  if (!tipos) return null;
  return x.tipo_hecho_id === tipos.GASTO ? 'GASTO' : x.tipo_hecho_id === tipos.INGRESO ? 'INGRESO' : null;
}

export function formularioPlantillaDesde(x: Plantilla, accion: AccionRapida | null, tipos: TiposRegistro | null): FormularioPlantilla {
  return {
    nombre: x.nombre,
    tipo: tipoDePlantilla(x, tipos),
    terceroId: x.tercero_id,
    categoriaId: x.categoria_id,
    contextoId: x.entidad_id,
    cuentaId: x.cuenta_default_id,
    presupuestable: x.presupuestable_default,
    enInicio: accion !== null && accion.enabled,
    nombreCorto: accion?.nombre ?? '',
    iconoKey: accion?.icono_key ?? null,
  };
}

/** Espejo de PLANTILLA_SIN_VALOR (el servidor sigue siendo la guarda). */
export function plantillaFormProponeAlgo(f: FormularioPlantilla): boolean {
  return f.terceroId !== null || f.categoriaId !== null || f.contextoId !== null || f.cuentaId !== null || f.presupuestable !== null;
}

export type FaltaPlantilla = 'nombre' | 'tipo' | 'proponer';

export function faltaPlantilla(f: FormularioPlantilla): FaltaPlantilla[] {
  const r: FaltaPlantilla[] = [];
  if (!f.nombre.trim()) r.push('nombre');
  if (f.tipo === null) r.push('tipo');
  if (!plantillaFormProponeAlgo(f)) r.push('proponer');
  return r;
}

/** «Falta: nombre» / «Falta: nombre y tipo» (lámina R06). */
export function textoFaltaPlantilla(faltas: FaltaPlantilla[]): string | null {
  const v = faltas.filter((x) => x !== 'proponer');
  if (v.length === 0) return null;
  return `Falta: ${v.length === 1 ? v[0] : `${v.slice(0, -1).join(', ')} y ${v[v.length - 1]}`}`;
}

/** Contenido COMPLETO de la plantilla (alta y edición: estado completo, E05). */
export function contenidoPlantilla(f: FormularioPlantilla, tipos: TiposRegistro): ContenidoPlantilla {
  return {
    nombre: f.nombre.trim(),
    tipo_hecho_id: tipos[f.tipo ?? 'GASTO'],
    categoria_id: f.categoriaId,
    tercero_id: f.terceroId,
    entidad_id: f.contextoId,
    cuenta_default_id: f.cuentaId,
    presupuestable_default: f.presupuestable,
  };
}

/** Nombre del acceso: el corto si se ha escrito; si no, el de la plantilla (recortado al máximo del servidor). */
export function nombreAcceso(f: Pick<FormularioPlantilla, 'nombre' | 'nombreCorto'>): string {
  const corto = f.nombreCorto.trim();
  return (corto || f.nombre.trim()).slice(0, LONGITUD_NOMBRE_ACCESO);
}

export type PlanAcceso =
  | { tipo: 'NADA' }
  | { tipo: 'ALTA'; nombre: string; icono_key: string | null }
  | { tipo: 'EDITAR'; accion: AccionRapida; nombre: string; icono_key: string | null }
  | { tipo: 'QUITAR'; accion: AccionRapida };

/** Qué hacer con el acceso en Inicio tras guardar la plantilla. */
export function planAcceso(f: FormularioPlantilla, accion: AccionRapida | null): PlanAcceso {
  const activa = accion !== null && accion.enabled ? accion : null;
  if (!f.enInicio) return activa ? { tipo: 'QUITAR', accion: activa } : { tipo: 'NADA' };
  const nombre = nombreAcceso(f);
  if (!activa) return { tipo: 'ALTA', nombre, icono_key: f.iconoKey };
  if (activa.nombre === nombre && activa.icono_key === f.iconoKey) return { tipo: 'NADA' };
  return { tipo: 'EDITAR', accion: activa, nombre, icono_key: f.iconoKey };
}

/** Acceso HABILITADO de una plantilla (uno como máximo: ACCION_PLANTILLA_YA_EN_INICIO). */
export function accionDe(acciones: AccionRapida[], plantillaId: string): AccionRapida | null {
  return acciones.find((a) => a.enabled && a.plantilla_registro_id === plantillaId) ?? null;
}

/** Orden nuevo de los accesos al mover uno (para POST reordenar con el conjunto COMPLETO). */
export function moverAcceso(acciones: AccionRapida[], id: string, delta: -1 | 1): { id: string; row_version: number }[] | null {
  const activas = acciones.filter((a) => a.enabled).sort((a, b) => a.orden - b.orden || (a.id < b.id ? -1 : 1));
  const i = activas.findIndex((a) => a.id === id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= activas.length) return null;
  const nueva = [...activas];
  [nueva[i], nueva[j]] = [nueva[j], nueva[i]];
  return nueva.map((a) => ({ id: a.id, row_version: a.row_version }));
}

/** «Sí · posición 1» / «No» (S05). */
export function textoEnInicio(acciones: AccionRapida[], plantillaId: string): string {
  const activas = acciones.filter((a) => a.enabled).sort((a, b) => a.orden - b.orden || (a.id < b.id ? -1 : 1));
  const i = activas.findIndex((a) => a.plantilla_registro_id === plantillaId);
  return i < 0 ? 'No' : `Sí · posición ${i + 1}`;
}
