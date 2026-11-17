// ============================================================
// GAPTO MOBILE 2027
// Fichero: hipoteca.ts
// Ruta: mobile/src/api/hipoteca.ts
// Descripción: Tipos del wire de la hipoteca de la compra (F06-01H; contrato v0.4 §3.1, §3.2.1, §3.3, §3.4, §3.5 y §7; servidor backend/app/hipotecas/rutas.py y dto.py). Solo tipos: W-HIP-00 vista previa del cuadro (POST /v1/hipotecas/cuadro, sin escritura), bloque `hipoteca` de la petición de la compra (C-COMPRA-01), L-HIP (GET /v1/propiedades/{id}/hipoteca), pago de una cuota (W-HIP-02) y revisión del tipo (W-HIP-03/04). Las llamadas son métodos OPCIONALES de `ClienteApi` (cliente.ts). Importes y tipos como texto exacto: el cliente no calcula importes.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// ============================================================

import type { AtribucionWire, ParteAtribucion } from './patrimonio';

export type TipoInteresHipoteca = 'FIJO' | 'VARIABLE';

/** W-HIP-00 · petición. */
export interface PayloadCuadroPrevio {
  capital: string;
  tasa_anual: string;
  numero_cuotas: number;
  primera_cuota?: string;
}

export interface FilaCuadroPrevio {
  n: number;
  vencimiento: string | null;
  cuota: string;
  interes: string;
  capital: string;
  comision: string;
  pendiente: string;
}

/** W-HIP-00 · respuesta (contrato §3.1). */
export interface CuadroPrevio {
  sistema: string;
  periodicidad: string;
  convencion: string;
  capital: string;
  tasa_anual: string;
  numero_cuotas: number;
  cuota_referencia: string;
  suma_capital: string;
  suma_intereses: string;
  total_a_pagar: string;
  cuotas: FilaCuadroPrevio[];
}

/** Bloque `hipoteca` de la petición de la compra (contrato §3.2.1). Nunca lleva campos de modalidad no representable. */
export interface BloqueHipotecaWire {
  financiador: { tercero_id: string };
  importe_prestamo: string;
  cuenta_desembolso_id: string;
  titularidad: AtribucionWire;
  tipo_interes: TipoInteresHipoteca;
  tasa_anual_pct: string;
  numero_cuotas: number;
  fecha_primera_cuota: string;
  cuenta_cargo_id: string;
}

/** Estado derivado de la cuota (lecturas.py): PENDIENTE, VENCIDA, PAGADA, SIN_PREVISION u otro estado de la previsión. */
export type EstadoCuota = 'PENDIENTE' | 'VENCIDA' | 'PAGADA' | 'SIN_PREVISION' | string;

export interface CuotaHipoteca {
  numero: number;
  vencimiento: string;
  cuota: string;
  interes: string;
  capital: string;
  pendiente: string | null;
  estado: EstadoCuota;
  version_id: string;
  hecho_pago_id: string | null;
}

export interface CondicionesHipoteca {
  id: string;
  vigente_desde: string;
  vigente_hasta: string | null;
  motivo: string;
  tipo_interes: string;
  tasa_anual: string | null;
  indice_referencia: string | null;
  diferencial: string | null;
  cuota_referencia: string | null;
  numero_cuotas: number | null;
  hecho_causa_id: string | null;
}

/** L-HIP (contrato §3.3; lecturas.py). */
export interface Hipoteca {
  financiacion_id: string;
  nombre: string;
  row_version: number;
  estado: string;
  propiedad_id: string | null;
  compra_hecho_id: string | null;
  desembolso: { hecho_id: string; cuenta_id: string | null; fecha: string; importe: string | null } | null;
  aviso_reparto_distinto: boolean;
  financiador: { actor_id: string; tercero_id: string | null; nombre: string | null } | null;
  capital: string | null;
  fecha_inicio: string | null;
  fecha_fin_prevista: string | null;
  convencion: string;
  cuenta_cargo_id: string | null;
  tipo_vigente: string | null;
  vigente_desde: string | null;
  cuota_vigente: string | null;
  /** Legacy con saldo desconocido: null con `deuda_indeterminada` (nunca 0). */
  deuda_pendiente: string | null;
  deuda_indeterminada: boolean;
  capital_amortizado: string;
  intereses_pagados: string;
  cuotas_pagadas: number;
  numero_cuotas: number;
  proxima_cuota: CuotaHipoteca | null;
  condiciones: CondicionesHipoteca[];
  cuotas: CuotaHipoteca[];
}

/** W-HIP-02 · petición (dto.PagoCuota). */
export interface PayloadPagoCuota {
  intencion_id: string;
  row_version_esperada: number;
  cuenta_id: string;
  fecha_pago: string;
  atribucion: { propuesta_vista: { partes: ParteAtribucion[] }; partes: ParteAtribucion[] };
}

/** W-HIP-03/04 · petición (dto.RevisionTipo). */
export interface PayloadRevisionTipo {
  intencion_id: string;
  row_version_esperada: number;
  vigente_desde: string;
  tasa_anual: string;
  tipo_interes?: TipoInteresHipoteca;
  indice_referencia?: string;
  diferencial?: string;
}

/** Escrituras de la hipoteca (contrato §7.2). */
export interface ResultadoHipoteca {
  idempotente: boolean;
  hecho_id?: string;
  hipoteca: Hipoteca;
}
