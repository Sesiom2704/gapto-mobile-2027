// ============================================================
// GAPTO MOBILE 2027
// Fichero: reembolso.ts
// Ruta: mobile/src/domain/reembolso.ts
// Descripción: Lógica pura del gasto propio reembolsable C-03 (F05 §66 y anexo §66.A, contrato v1.0; lámina F05-07 v0.3 C1–C4; D-F0507L-04..06). «Mío, pero me lo reembolsan» es una respuesta más de «¿De quién?» (interpretación acotada de SPEC-04: la operación inicial reconoce un derecho de cobro, no registra un REEMBOLSO). Datos: quién te lo debe (PERSONA o EMPRESA, nunca el comercio del gasto) y cuánto te deben («Todo» u «Otra cantidad», de 0,01 € al total; nada marcado por defecto). El gasto cuenta entero en tu Resultado (§66.1) y el cobro posterior no es un ingreso. Sellado de POST /v1/intenciones/gasto-reembolsable: el payload del gasto pagado sin `atribucion` y con `reembolso` (CONTRATO_API_C03 §1). Textos de §66.2 y del cobro: «Saldado · no cuenta como ingreso» solo si el cobro extingue el saldo conocido; si queda saldo, «Cobro registrado · quedan X €»; nunca «Saldado» con saldo indeterminado. `posiciones_vinculadas` del detalle del hecho, separadas de las partes del reparto.
// Versión: 0.1.0 (F05-D052 paso 2 · C-03 UI C1–C4)
// ============================================================

// Sin dependencias de valor con intencion.ts ni reparto.ts (intencion.ts importa la validación de aquí).
import { formatearEur, parsearImporte } from './importe';
import type { PayloadGastoPagado } from './intencion';

/** Céntimos de un importe canónico positivo («40.00» → 4000). */
function centimos(valor: string): number {
  const [e, d = ''] = valor.replace('-', '').split('.');
  return (valor.startsWith('-') ? -1 : 1) * (Number(e) * 100 + Number((d + '00').slice(0, 2)));
}

// ------------------------------------------------------------------ textos (F05 §66.2; lámina v0.3)
export const TEXTO_OPCION_REEMBOLSO = 'Mío, pero me lo reembolsan';
export const TEXTO_OPCION_REEMBOLSO_SUB = 'Tu empresa u otra persona te lo devuelve';
export const TITULO_REEMBOLSO = 'Me lo reembolsan';
export const TEXTO_QUIEN = 'Quién te lo debe';
export const TEXTO_CUANTO = 'Cuánto te deben';
export const TEXTO_ELIGE_QUIEN = 'Elige persona o empresa';
export const TEXTO_TODO = (total: string) => `Todo · ${formatearEur(total)}`;
export const TEXTO_OTRA_CANTIDAD = 'Otra cantidad';
export const TEXTO_COMO_SE_REGISTRA = (total: string) =>
  `El gasto de ${formatearEur(total)} es tuyo y cuenta en tu Resultado. Además, quedará anotado lo que te deben. Cuando te lo paguen no será un ingreso: solo saldará esa deuda.`;
/** §66.A.2: el bloque de previsión queda excluido en este flujo, y se dice (DEU-C03-PREVISION). */
export const TEXTO_SIN_PREVISION = 'Este gasto no se puede asociar a una previsión.';
export const TEXTO_SOLO_PERSONAS_EMPRESAS = 'Solo personas y empresas. Nunca el comercio de este gasto.';
export const PREFIJO_PENDIENTE_COBRO = 'Pendiente de cobro';
export const TEXTO_REGISTRAR_COBRO = 'Registrar cobro';
export const TEXTO_SALDADO_NO_INGRESO = 'Saldado · no cuenta como ingreso';
export const TEXTO_COBRO_QUEDAN = (saldo: string) => `Cobro registrado · quedan ${formatearEur(saldo)}`;
export const TEXTO_COBRO_REGISTRADO = 'Cobro registrado';
export const TEXTO_COBRO_NO_INGRESO = 'No es un ingreso: solo salda lo que te deben. Tu Resultado no cambia.';
export const TEXTO_CUENTA_RESULTADO = 'Cuenta en tu Resultado';
export const TEXTO_TE_DEBE = (nombre: string) => `Te debe ${nombre}`;
export const TEXTO_ATRIBUCION_REEMBOLSO = (nombre: string) => `Decisión tuya: el gasto es 100 % tuyo y ${nombre} te lo debe.`;

/** Motivos de los rechazos de C-03 (CONTRATO_API_C03 §4 y §6), en lenguaje llano. */
export const MOTIVO_RECHAZO_REEMBOLSO: Record<string, string> = {
  REEMBOLSO_EXCEDE_TOTAL: 'Lo que te deben no puede ser más que el total del gasto.',
  CONTRAPARTE_ES_COMERCIO: 'Quien te lo debe no puede ser el mismo comercio del gasto.',
  NATURALEZA_NO_ADMITIDA_EN_REEMBOLSO: 'Quien te lo debe tiene que ser una persona o una empresa.',
  TERCERO_NO_DISPONIBLE: 'Quien te lo debe o el comercio ya no está disponible. Elige otro.',
};

// ------------------------------------------------------------------ borrador
export type ModoImporteReembolso = 'TODO' | 'OTRA';

/** Datos de «Me lo reembolsan» en el borrador del registro (nada marcado por defecto). */
export interface ReembolsoBorrador {
  terceroId: string | null;
  nombre: string | null;
  modo: ModoImporteReembolso | null;
  /** Solo con «Otra cantidad». */
  importeTexto: string;
}

export const REEMBOLSO_VACIO: ReembolsoBorrador = Object.freeze({ terceroId: null, nombre: null, modo: null, importeTexto: '' });

/** Importe recuperable (texto canónico «40.00») o null si no está decidido o no es válido. */
export function importeReembolso(total: string | null, r: ReembolsoBorrador): string | null {
  if (r.modo === 'TODO') return total;
  if (r.modo !== 'OTRA') return null;
  const imp = parsearImporte(r.importeTexto);
  if (!imp.ok || total === null) return null;
  return centimos(imp.valor) >= 1 && centimos(imp.valor) <= centimos(total) ? imp.valor : null;
}

/** Lo que falta en «Me lo reembolsan» (C2; §66.A.2/§66.A.3); vacío = «Hecho» activo. */
export function faltaReembolso(total: string | null, r: ReembolsoBorrador, comercioId: string | null): string[] {
  const f: string[] = [];
  if (!r.terceroId) f.push('quién te lo debe');
  else if (comercioId && r.terceroId === comercioId) f.push('quien te lo debe, que no puede ser el comercio del gasto');
  if (r.modo === null) f.push('cuánto te deben');
  else if (r.modo === 'OTRA' && importeReembolso(total, r) === null) {
    f.push(total ? `una cantidad entre 0,01 € y ${formatearEur(total)}` : 'una cantidad válida');
  }
  return f;
}

/** Total del borrador (null si el importe aún no es válido). */
export function totalDe(b: { importeTexto: string }): string | null {
  const imp = parsearImporte(b.importeTexto);
  return imp.ok ? imp.valor : null;
}

// ------------------------------------------------------------------ wire (CONTRATO_API_C03 §1)
export type PayloadGastoReembolsable = Omit<PayloadGastoPagado, 'atribucion'> & {
  reembolso: { tercero_id: string; importe: string };
};

export interface PosicionReembolso {
  entidad_id: string;
  tipo: 'DERECHO_COBRO';
  contraparte_tercero_id: string;
  nombre: string;
  importe: string;
  saldo: string | null;
  estado: 'ACTIVA' | 'CERRADA';
  apertura_indeterminada: boolean;
}

export interface ResultadoGastoReembolsable {
  intencion_id: string;
  hecho_id: string;
  idempotente: boolean;
  importe: string;
  moneda: string;
  estado_atribucion: 'COMPLETA';
  tu_parte: string;
  movimiento: { movimiento_id: string; cuenta_id: string; importe: string };
  posiciones: PosicionReembolso[];
  aviso: string;
}

/** Posición del hecho que no cuelga de ninguna parte del reparto (CONTRATO_API_C03 §3). */
export interface PosicionVinculada {
  entidad_id: string;
  contraparte_tercero_id: string;
  contraparte_nombre: string;
  tipo: 'DERECHO_COBRO' | 'OBLIGACION_PAGO';
  saldo: string | null;
  estado: 'ACTIVA' | 'CERRADA';
  apertura_indeterminada: boolean;
}

export interface IntencionReembolsableSellada {
  readonly intencionId: string;
  readonly payload: PayloadGastoReembolsable;
  readonly reembolsable: true;
}

// ------------------------------------------------------------------ cobro (C4)
/** ¿Es el derecho de cobro de un gasto reembolsable? Su nombre lo fija el servidor (§66.2). */
export function esDerechoReembolso(x: { tipo: string; nombre: string | null }): boolean {
  return x.tipo === 'DERECHO_COBRO' && !!x.nombre && (x.nombre === PREFIJO_PENDIENTE_COBRO || x.nombre.startsWith(`${PREFIJO_PENDIENTE_COBRO} · `));
}

/** Confirmación de un cobro (D-F0507L-06): «Saldado» solo si extingue el saldo conocido; nunca con saldo indeterminado. */
export function textoTrasCobro(r: { saldo: string | null; estado: 'ACTIVA' | 'CERRADA' }): string {
  if (r.saldo === null) return TEXTO_COBRO_REGISTRADO;
  if (r.estado === 'CERRADA' && centimos(r.saldo) === 0) return TEXTO_SALDADO_NO_INGRESO;
  return TEXTO_COBRO_QUEDAN(r.saldo);
}
