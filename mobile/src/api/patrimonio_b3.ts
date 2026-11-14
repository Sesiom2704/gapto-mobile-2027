// ============================================================
// GAPTO MOBILE 2027
// Fichero: patrimonio_b3.ts
// Ruta: mobile/src/api/patrimonio_b3.ts
// Descripción: Cliente HTTP de B3 · Obras y gastos de una propiedad (F06-01 B3; R1 v0.9.5 Parte III; v0.8 y v0.9 §III.1–§III.3). Propuesta de reparto en la fecha del hecho (GET …/{id}/propuesta-gasto, P-H2-03: titularidad de la PROPIEDAD, nunca de la cuenta; la cuenta solo dice si es solo tuya o compartida, 8ter), C-MEJ-01 (POST /v1/intenciones/gasto-propiedad, tres clases), C-MEJ-02 (POST …/{id}/mejoras-historicas), lista y lectura del gasto (L-GASTO-PROPIEDAD, con `intencion_correccion_id`), impacto de la corrección y C-MEJ-03 (POST …/gastos/{hecho}/corregir-clase). Va aparte de `ClientePatrimonio` (B2) para no ampliar su interfaz. Escrituras con la clasificación 'CAMBIO'. Importes y porcentajes como texto exacto.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// Versión: 0.2.0 (F06 T2-F06 PAG N1; L-02, contrato operativo único del mandato PAG §1.1): C-MEJ-01 v2 (`PayloadGastoPropiedadV2`: `pagos[]`, `saldos[]` y `posiciones_confirmadas[]`, sin `cuenta_id` ni la deuda de v1; la forma de B3 sigue para la cuenta compartida), bloque `pago` de L-GASTO-PROPIEDAD (quién pagó, salida real y posiciones en su sentido; `declarado` false = «pago sin declarar») y L-MOV-CUENTA (`movimientosCuenta`, GET /v1/cuentas/{id}/movimientos, sin punteo; opcional en los dobles).
// ============================================================

import { ConfigApi, crearLlamada, Respuesta } from './cliente';
import type { ParteAtribucion } from './patrimonio';
import type { PagoWire, PosicionWire, SaldoWire } from '../domain/quien_pago';

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

/** C-MEJ-01 v2 (PAG): quién pagó y quién debe, sin cuenta única ni deuda de v1. */
export interface PayloadGastoPropiedadV2 {
  intencion_id: string;
  propiedad_id: string;
  clase: ClaseGasto;
  importe: string;
  fecha_hecho: string;
  nota: string | null;
  categoria_id: string | null;
  presupuestable: boolean | null;
  atribucion: AtribucionB3;
  pagos: PagoWire[];
  saldos: SaldoWire[];
  posiciones_confirmadas: PosicionWire[];
}

/** HT2-06 / Q-PAG-10: quién pagó, cuánto salió de tus cuentas y las posiciones en su sentido («declarado» false = pago sin declarar). */
export interface LecturaPago {
  declarado: boolean;
  sale_de_mis_cuentas: string;
  pagos: { actor_id: string; importe: string; con_movimiento: boolean; cuenta_id: string | null }[];
  posiciones: { actor_id: string; sentido: 'ME_DEBE' | 'LE_DEBO'; tipo: string; importe: string; estado: string | null }[];
  cuentas_movimiento?: string[];
}

/** L-MOV-CUENTA (L-09): movimientos de una cuenta en orden cronológico, con sus hechos; sin estado de punteo. */
export interface MovimientosCuenta {
  cuenta_id: string;
  nombre: string;
  moneda: string;
  pagina: number;
  limite: number;
  hay_mas: boolean;
  movimientos: { movimiento_id: string; fecha: string; importe: string; descripcion: string | null; clase: string;
    hechos: { hecho_id: string; concepto: string | null; tipo_hecho: string; importe_asignado: string }[] }[];
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
  pago?: LecturaPago;
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
  registrarGastoPropiedad(p: PayloadGastoPropiedad | PayloadGastoPropiedadV2): Promise<Respuesta<ResultadoGastoPropiedad>>;
  mejoraHistorica(propiedadId: string, p: PayloadMejoraHistorica): Promise<Respuesta<ResultadoGastoPropiedad>>;
  listarGastos(propiedadId: string): Promise<Respuesta<{ gastos: FilaGastoPropiedad[] }>>;
  leerGasto(propiedadId: string, hechoId: string): Promise<Respuesta<LecturaGastoPropiedad>>;
  impactoCorreccion(propiedadId: string, hechoId: string, claseNueva: ClaseGasto, presupuestable: boolean | null): Promise<Respuesta<{ comparacion: ComparacionImpacto }>>;
  corregirClase(propiedadId: string, hechoId: string, p: PayloadCorregirClase): Promise<Respuesta<LecturaGastoPropiedad>>;
  /** PAG · L-MOV-CUENTA. Opcional en los dobles de test. */
  movimientosCuenta?(cuentaId: string, pagina?: number): Promise<Respuesta<MovimientosCuenta>>;
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
    movimientosCuenta: (cuentaId, pagina = 0) => llamar(`/v1/cuentas/${encodeURIComponent(cuentaId)}/movimientos?pagina=${pagina}`, GET, false),
  };
}
