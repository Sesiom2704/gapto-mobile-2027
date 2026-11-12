// ============================================================
// GAPTO MOBILE 2027
// Fichero: patrimonio_b3.ts
// Ruta: mobile/src/api/patrimonio_b3.ts
// Descripción: Cliente HTTP de B3 · Obras y gastos de una propiedad (F06-01 B3; R1 v0.9.5 Parte III; v0.8 y v0.9 §III.1–§III.3). Propuesta de reparto en la fecha del hecho (GET …/{id}/propuesta-gasto, P-H2-03: titularidad de la PROPIEDAD, nunca de la cuenta; la cuenta solo dice si es solo tuya o compartida, 8ter), C-MEJ-01 (POST /v1/intenciones/gasto-propiedad, tres clases), C-MEJ-02 (POST …/{id}/mejoras-historicas), lista y lectura del gasto (L-GASTO-PROPIEDAD, con `intencion_correccion_id`), impacto de la corrección y C-MEJ-03 (POST …/gastos/{hecho}/corregir-clase). Va aparte de `ClientePatrimonio` (B2) para no ampliar su interfaz. Escrituras con la clasificación 'CAMBIO'. Importes y porcentajes como texto exacto.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// ============================================================

import { ConfigApi, crearLlamada, Respuesta } from './cliente';
import type { ParteAtribucion } from './patrimonio';

export type ClaseGasto = 'MEJORA' | 'REPARACION' | 'GASTO_CORRIENTE';
export type Naturaleza = 'PERSONA' | 'EMPRESA';

export interface PartePropuesta {
  actor_id: string;
  porcentaje: string;
  yo: boolean;
  tercero_id: string | null;
  nombre: string | null;
  naturaleza: Naturaleza | null;
}

export interface PropuestaGasto {
  fecha: string;
  propiedad_id: string;
  nombre: string;
  titularidad_disponible: boolean;
  partes: PartePropuesta[];
  cuenta: null | { cuenta_id: string; solo_mia: boolean; compartida_con: string[] };
}

export type AtribucionB3 =
  | { modo: 'SEGUN_TITULARIDAD_ACEPTADA'; propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO'; fecha_referencia: string; partes: ParteAtribucion[] } }
  | { modo: 'MANUAL'; partes: ParteAtribucion[] }
  | { modo: 'NO_LO_SE' };

export interface PayloadGastoPropiedad {
  intencion_id: string;
  propiedad_id: string;
  clase: ClaseGasto;
  importe: string;
  fecha_hecho: string;
  cuenta_id: string;
  nota: string | null;
  categoria_id: string | null;
  presupuestable: boolean | null;
  atribucion: AtribucionB3;
  deuda: { actor_id: string; me_debe: 'SI' | 'NO' }[];
  aportacion_indicada: 'MANUAL' | null;
  derechos_confirmados: { actor_id: string; importe: string }[];
}

export interface PayloadMejoraHistorica {
  intencion_id: string;
  row_version_esperada: number;
  descripcion: string;
  importe: string;
  fecha: string;
  atribucion: AtribucionB3;
}

export interface ResultadoGastoPropiedad {
  hecho_id: string;
  idempotente: boolean;
  tipo_hecho: string;
  clase: string;
  importe: string;
  estado_atribucion: string;
  atribuciones: { actor_id: string; importe: string; porcentaje: string | null }[];
  posiciones: { entidad_id: string; actor_id: string; tercero_id: string | null; importe: string }[];
  intencion_correccion_id: string | null;
  gasto_del_mes?: string;
}

export interface FilaGastoPropiedad {
  hecho_id: string;
  tipo_hecho: string;
  clase: 'MEJORA' | 'GASTO';
  importe: string;
  fecha: string;
  nota: string | null;
  procedencia: 'GASTO_PROPIEDAD' | 'MEJORA_HISTORICA';
  estado: string;
  con_deuda: boolean;
}

export interface LecturaGastoPropiedad {
  hecho_id: string;
  propiedad_id: string;
  estado: string;
  row_version: number;
  tipo_hecho: string;
  clase: 'MEJORA' | 'GASTO';
  importe: string;
  fecha: string;
  nota: string | null;
  categoria_id: string | null;
  presupuestable: boolean;
  procedencia: 'GASTO_PROPIEDAD' | 'MEJORA_HISTORICA';
  efectos_vigentes: number;
  con_deuda: boolean;
  posiciones: unknown[];
  atribuciones: unknown[];
  intencion_correccion_id: string | null;
  limitacion: string | null;
  idempotente?: boolean;
}

export interface ComparacionImpacto {
  mes: string;
  resultado_mes_delta_antes: string;
  resultado_mes_delta_despues: string;
  mejoras_antes: string;
  mejoras_despues: string;
  presupuesto_delta_despues: string;
}

export interface PayloadCorregirClase {
  intencion_id: string;
  row_version_esperada: number;
  clase_nueva: ClaseGasto;
  motivo: string;
  categoria_id: string | null;
  presupuestable: boolean | null;
  comparacion_vista: ComparacionImpacto;
}

export interface ClientePatrimonioB3 {
  propuestaGasto(propiedadId: string, fecha: string, cuentaId?: string | null): Promise<Respuesta<PropuestaGasto>>;
  registrarGastoPropiedad(p: PayloadGastoPropiedad): Promise<Respuesta<ResultadoGastoPropiedad>>;
  mejoraHistorica(propiedadId: string, p: PayloadMejoraHistorica): Promise<Respuesta<ResultadoGastoPropiedad>>;
  listarGastos(propiedadId: string): Promise<Respuesta<{ gastos: FilaGastoPropiedad[] }>>;
  leerGasto(propiedadId: string, hechoId: string): Promise<Respuesta<LecturaGastoPropiedad>>;
  impactoCorreccion(propiedadId: string, hechoId: string, claseNueva: ClaseGasto, presupuestable: boolean | null): Promise<Respuesta<{ comparacion: ComparacionImpacto }>>;
  corregirClase(propiedadId: string, hechoId: string, p: PayloadCorregirClase): Promise<Respuesta<LecturaGastoPropiedad>>;
}

const una = (id: string) => `/v1/propiedades/${encodeURIComponent(id)}`;
const post = (cuerpo: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(cuerpo) });
const GET: RequestInit = { method: 'GET' };

export function crearClientePatrimonioB3(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClientePatrimonioB3 {
  const llamar = crearLlamada(cfg, fetchImpl);
  return {
    propuestaGasto: (id, fecha, cuentaId) =>
      llamar(`${una(id)}/propuesta-gasto?fecha=${encodeURIComponent(fecha)}${cuentaId ? `&cuenta_id=${encodeURIComponent(cuentaId)}` : ''}`, GET, false),
    registrarGastoPropiedad: (p) => llamar('/v1/intenciones/gasto-propiedad', post(p), 'CAMBIO'),
    mejoraHistorica: (id, p) => llamar(`${una(id)}/mejoras-historicas`, post(p), 'CAMBIO'),
    listarGastos: (id) => llamar(`${una(id)}/gastos`, GET, false),
    leerGasto: (id, h) => llamar(`${una(id)}/gastos/${encodeURIComponent(h)}`, GET, false),
    impactoCorreccion: (id, h, clase, presupuestable) =>
      llamar(`${una(id)}/gastos/${encodeURIComponent(h)}/impacto-correccion?clase_nueva=${clase}${presupuestable === null ? '' : `&presupuestable=${presupuestable}`}`, GET, false),
    corregirClase: (id, h, p) => llamar(`${una(id)}/gastos/${encodeURIComponent(h)}/corregir-clase`, post(p), 'CAMBIO'),
  };
}
