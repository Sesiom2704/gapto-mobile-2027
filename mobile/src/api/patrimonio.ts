// ============================================================
// GAPTO MOBILE 2027
// Fichero: patrimonio.ts
// Ruta: mobile/src/api/patrimonio.ts
// Descripción: Cliente HTTP de B2 · Compra (F06-01 B2; R1 v0.9.5 Parte II; v0.8 DTO RegistrarCompra sin hipoteca). POST /v1/propiedades/{id}/compra (C-COMPRA-01), POST …/{id}/compra/gastos (C-COMPRA-03), GET …/{id}/coste?a_fecha= (L-COSTE) y GET …/{id}/titularidad-en-fecha?fecha= (titularidad vigente en una fecha, P-H2-03, adelantada a B2). Las escrituras usan la clasificación 'CAMBIO' (indeterminado = revisar antes de repetir; el reintento idéntico con la misma intención es un replay). Importes y porcentajes viajan como texto exacto. Va aparte de `ClientePropiedades` (B1) para no ampliar su interfaz. C-PROP-05 no tiene cliente: es un consumidor de 0352 con la habilitación bloqueada (O10.29).
// Versión: 0.1.0 (F06 T1-F06 B2 N1)
// Versión: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 10): SOLO aditivo: bloque opcional `hipoteca` en `PayloadCompra` (contrato v0.4 §3.2.1; fin de E4) y, en `ResultadoCompra`, `hipoteca` (L-HIP) y `aviso_reparto_distinto` (O-H30) cuando la compra lleva hipoteca. Sin hipoteca, la petición y la respuesta no cambian.
// Versión: 0.3.0 (F06 T3-F06 · MANT N1 R-B2-06 (AJ-01), firma b88a3662…): `registrarCompra` usa un timeout propio `TIMEOUT_COMPRA_MS` (45 s, nunca menor que el general): con hipoteca larga la validación G2 de 0354 al COMMIT cuesta ≈ 35 ms por cuota (360 → ≈ 18,6 s en laboratorio). El resto de llamadas conserva el timeout general.
// ============================================================

import type { BloqueHipotecaWire, Hipoteca } from './hipoteca';
import type { VistaPropiedad } from './propiedades';
import { ConfigApi, crearLlamada, Respuesta } from './cliente';

export type ConceptoGasto = 'ITP' | 'IVA_AJD' | 'NOTARIA_REGISTRO_GESTORIA' | 'AGENCIA' | 'OTRO';
export type RolPago = 'ARRAS' | 'FIRMA' | 'OTRO';
export type CriterioPropuesta = 'TITULARIDAD_EN_FECHA_ESCRITURA' | 'TITULARIDAD_EN_FECHA_ECONOMICA';

export interface ParteAtribucion {
  actor_id: string;
  porcentaje: string;
}

export type AtribucionWire =
  | { modo: 'SEGUN_TITULARIDAD_ACEPTADA'; propuesta_vista: { criterio: CriterioPropuesta; fecha_referencia: string; partes: ParteAtribucion[] } }
  | { modo: 'MANUAL'; partes: ParteAtribucion[] }
  | { modo: 'NO_LO_SE' };

export interface PagoPropioWire {
  linea_id: string;
  rol: RolPago;
  cuenta_id: string;
  fecha_pago: string;
  importe: string;
}

export interface LineaGastoWire {
  linea_id: string;
  concepto: ConceptoGasto;
  cuenta_id: string;
  fecha_economica: string;
  fecha_pago: string;
  importe: string;
  nota?: string | null;
}

export interface PayloadCompra {
  intencion_id: string;
  row_version_esperada: number;
  fecha_escritura: string;
  precio: string;
  valor_referencia?: string | null;
  pagos_propios: PagoPropioWire[];
  gastos: LineaGastoWire[];
  atribucion: AtribucionWire;
  completitud_adquisicion?: { completo: boolean; fecha_corte?: string };
  /** F06-01H: hipoteca de la compra (solo si la hay; sin ella la clave no viaja). */
  hipoteca?: BloqueHipotecaWire;
}

export interface PayloadGastoCompra {
  intencion_id: string;
  row_version_esperada: number;
  linea: LineaGastoWire;
  atribucion: AtribucionWire;
}

export type EstadoCoste = 'COMPLETO' | 'PARCIAL' | 'NO_DISPONIBLE';

export interface CosteAmbito {
  total: string;
  estado: EstadoCoste;
  motivo_estado: string | null;
  fecha_corte: string | null;
  huella_conjunto: string | null;
  componentes: number;
  tu_parte: { importe: string | null; estado: EstadoCoste };
}

export interface Coste {
  a_fecha: string;
  declaracion_habilitada: boolean;
  ADQUISICION: CosteAmbito;
  MEJORAS: CosteAmbito;
  PERMANECE: { total: string; estado: EstadoCoste; bajas: 'NO_REPRESENTADAS' };
}

export interface ResultadoCompra {
  propiedad: VistaPropiedad;
  idempotente: boolean;
  compra: {
    hechos: { linea_id: string | null; hecho_id: string }[];
    coste_adquisicion: CosteAmbito | null;
    sale_de_tus_cuentas: string;
    liquidez_atribuible: string;
    gasto_del_mes: string;
    atribucion: unknown;
  };
  /** F06-01H: solo con hipoteca. */
  hipoteca?: Hipoteca | null;
  aviso_reparto_distinto?: boolean;
}

export interface ParteEnFecha {
  actor_id: string;
  porcentaje: string;
  yo: boolean;
  tercero_id: string | null;
  nombre: string | null;
}

export interface ClientePatrimonio {
  registrarCompra(propiedadId: string, p: PayloadCompra): Promise<Respuesta<ResultadoCompra>>;
  gastoCompraPosterior(propiedadId: string, p: PayloadGastoCompra): Promise<Respuesta<ResultadoCompra>>;
  leerCoste(propiedadId: string, aFecha?: string): Promise<Respuesta<{ coste: Coste }>>;
  titularidadEnFecha(propiedadId: string, fecha: string): Promise<Respuesta<{ fecha: string; partes: ParteEnFecha[] }>>;
}

const una = (id: string) => `/v1/propiedades/${encodeURIComponent(id)}`;
const post = (cuerpo: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(cuerpo) });

/** R-B2-06 (AJ-01): timeout propio de la compra (POST .../compra); nunca menor que el general. */
export const TIMEOUT_COMPRA_MS = 45000;

export function crearClientePatrimonio(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClientePatrimonio {
  const llamar = crearLlamada(cfg, fetchImpl);
  const llamarCompra = crearLlamada({ ...cfg, timeoutMs: Math.max(cfg.timeoutMs, TIMEOUT_COMPRA_MS) }, fetchImpl);
  return {
    registrarCompra: (id, p) => llamarCompra(`${una(id)}/compra`, post(p), 'CAMBIO'),
    gastoCompraPosterior: (id, p) => llamar(`${una(id)}/compra/gastos`, post(p), 'CAMBIO'),
    leerCoste: (id, aFecha) => llamar(`${una(id)}/coste${aFecha ? `?a_fecha=${encodeURIComponent(aFecha)}` : ''}`, { method: 'GET' }, false),
    titularidadEnFecha: (id, fecha) => llamar(`${una(id)}/titularidad-en-fecha?fecha=${encodeURIComponent(fecha)}`, { method: 'GET' }, false),
  };
}
