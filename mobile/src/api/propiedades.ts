// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedades.ts
// Ruta: mobile/src/api/propiedades.ts
// Descripción: Cliente HTTP de B1 · Propiedad (F06-01; contrato HTTP de B1 v1.0 del Lote 12, sobre C-PROP-01..04 y L-PROP). Lecturas GET /v1/propiedades y /v1/propiedades/{id}; escrituras POST /v1/propiedades (alta), …/{id}/editar, …/{id}/titularidad (cambio desde una fecha, con `titularidad_vista` completa: PR1-04), …/{id}/valoraciones (alta). Todas las escrituras usan la clasificación 'CAMBIO' (indeterminado = revisar el estado antes de repetir; el reintento IDÉNTICO con la misma `intencion_id` es un replay). Importes, porcentajes y superficies viajan como texto exacto. Va aparte de `ClienteApi` para no ampliar su interfaz (los dobles de los tests existentes no cambian).
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import type { MetodoValoracion, ModoTitularidad, ParteWire, TipoPropiedad, TitularidadWire, TriEstado } from '../domain/propiedad';
import { ConfigApi, crearLlamada, Respuesta } from './cliente';

export interface ParteTitularidad {
  actor_id: string;
  yo: boolean;
  tercero_id: string | null;
  nombre: string | null;
  porcentaje: string;
}

export interface TitularidadVista {
  modo: ModoTitularidad;
  desde: string | null;
  partes: ParteTitularidad[];
}

export interface Valoracion {
  id: string;
  valor_total: string;
  fecha_valoracion: string | null;
  metodo: MetodoValoracion;
  fuente: string | null;
  notas: string | null;
  sin_fecha: boolean;
}

export interface VistaPropiedad {
  id: string;
  nombre: string;
  enabled: boolean;
  row_version: number;
  tipo_propiedad: TipoPropiedad;
  fecha_adquisicion: string | null;
  superficie_m2: string | null;
  superficie_construida_m2: string | null;
  habitaciones: number | null;
  banos: number | null;
  tiene_garaje: TriEstado;
  tiene_trastero: TriEstado;
  referencia_catastral: string | null;
  incluir_en_rentabilidad: boolean;
  notas: string | null;
  fecha_consulta: string;
  titularidad: TitularidadVista;
  cambio_programado: TitularidadVista | null;
  valor_estimado: Valoracion | null;
  referencia_fiscal: Valoracion | null;
  valor_compra: Valoracion | null;
  cuota_segun_titularidad: { importe: string; porcentaje: string; etiqueta: 'VISTA_ESTRUCTURAL' } | null;
  valoraciones: Valoracion[];
}

export interface FilaPropiedad {
  id: string;
  nombre: string;
  enabled: boolean;
  row_version: number;
  tipo_propiedad: TipoPropiedad;
  modo_titularidad: ModoTitularidad;
  valor_estimado: Valoracion | null;
}

export interface ResultadoPropiedad {
  propiedad: VistaPropiedad;
  idempotente: boolean;
  modificadas: string[];
  avisos: string[];
}

export interface PayloadAltaPropiedad {
  intencion_id: string;
  nombre: string;
  tipo_propiedad: TipoPropiedad;
  fecha_adquisicion: string | null;
  superficie_m2: string | null;
  superficie_construida_m2: string | null;
  habitaciones: number | null;
  banos: number | null;
  tiene_garaje: TriEstado;
  tiene_trastero: TriEstado;
  referencia_catastral: string | null;
  notas: string | null;
  titularidad: TitularidadWire;
}

/** Edición: un campo omitido no cambia; `null` explícito borra el dato (solo en los que lo admiten). */
export type PayloadEditarPropiedad = {
  intencion_id: string;
  row_version_esperada: number;
  motivo?: string | null;
} & Partial<Omit<PayloadAltaPropiedad, 'intencion_id' | 'titularidad'>> & { incluir_en_rentabilidad?: boolean };

export interface PayloadCambioTitularidad {
  intencion_id: string;
  row_version_esperada: number;
  modo: Exclude<ModoTitularidad, 'DESCONOCIDA'>;
  desde: string;
  partes: ParteWire[] | null;
  /** Conjunto COMPLETO de partes vigentes hoy que vio el cliente (PR1-04); [] si era DESCONOCIDA. */
  titularidad_vista: { actor_id: string; porcentaje: string }[];
  motivo?: string | null;
}

export interface PayloadValoracion {
  intencion_id: string;
  row_version_esperada: number;
  valor_total: string;
  fecha_valoracion: string;
  metodo: Exclude<MetodoValoracion, 'COMPRA'>;
  fuente: string | null;
  notas: string | null;
}

export interface ClientePropiedades {
  listarPropiedades(): Promise<Respuesta<{ propiedades: FilaPropiedad[] }>>;
  leerPropiedad(id: string): Promise<Respuesta<{ propiedad: VistaPropiedad }>>;
  altaPropiedad(p: PayloadAltaPropiedad): Promise<Respuesta<ResultadoPropiedad>>;
  editarPropiedad(id: string, p: PayloadEditarPropiedad): Promise<Respuesta<ResultadoPropiedad>>;
  cambiarTitularidad(id: string, p: PayloadCambioTitularidad): Promise<Respuesta<ResultadoPropiedad>>;
  altaValoracion(id: string, p: PayloadValoracion): Promise<Respuesta<ResultadoPropiedad>>;
}

const PROP = '/v1/propiedades';
const una = (id: string) => `${PROP}/${encodeURIComponent(id)}`;
const post = (cuerpo: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(cuerpo) });

export function crearClientePropiedades(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClientePropiedades {
  const llamar = crearLlamada(cfg, fetchImpl);
  return {
    listarPropiedades: () => llamar(PROP, { method: 'GET' }, false),
    leerPropiedad: (id) => llamar(una(id), { method: 'GET' }, false),
    altaPropiedad: (p) => llamar(PROP, post(p), 'CAMBIO'),
    editarPropiedad: (id, p) => llamar(`${una(id)}/editar`, post(p), 'CAMBIO'),
    cambiarTitularidad: (id, p) => llamar(`${una(id)}/titularidad`, post(p), 'CAMBIO'),
    altaValoracion: (id, p) => llamar(`${una(id)}/valoraciones`, post(p), 'CAMBIO'),
  };
}

/** `titularidad_vista` de C-PROP-03: las partes vigentes tal como las devolvió la lectura (actor y porcentaje exactos). */
export const titularidadVista = (t: TitularidadVista) => t.partes.map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje }));
