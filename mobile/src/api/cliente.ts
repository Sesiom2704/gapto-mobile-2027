// ============================================================
// GAPTO MOBILE 2027
// Fichero: cliente.ts
// Ruta: mobile/src/api/cliente.ts
// Descripción: Cliente HTTP del adaptador F05-00-B. Clasifica cada respuesta en resultados de dominio del cliente: OK, RECHAZADO (definitivo, no persistido) o INDETERMINADO (timeout, red, 5xx: puede haberse confirmado; se reintenta la MISMA intención). Nunca expone texto técnico.
// Versión: 0.1.0
// ============================================================

import type { PayloadGastoPagado } from '../domain/intencion';

export interface ConfigApi {
  baseUrl: string;
  token: string;
  timeoutMs: number;
}

export interface ResultadoRegistro {
  hecho_id: string;
  idempotente: boolean;
  importe: string;
  estado_atribucion: 'COMPLETA' | 'NO_DISPONIBLE';
  aportacion_criterio: string | null;
}

export interface CuentaPago {
  cuenta_id: string;
  nombre: string;
  moneda: string;
  financiacion_derivable: boolean;
}

export interface GastoMes {
  mes: string;
  moneda: 'EUR';
  gasto_atribuible: string;
  estado: 'CONFIRMADO' | 'PARCIAL';
  gastos_sin_reparto: number;
  gastos_otra_moneda: number;
  contrato: string;
}

export type Respuesta<T> =
  | { tipo: 'OK'; datos: T }
  | { tipo: 'RECHAZADO'; codigo: string; mensaje: string }
  | { tipo: 'INDETERMINADO'; mensaje: string };

const MSG_INDETERMINADO = 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.';
const MSG_SIN_CONEXION = 'No hay conexión con el servidor.';

export interface ClienteApi {
  registrarGastoPagado(p: PayloadGastoPagado): Promise<Respuesta<ResultadoRegistro>>;
  cuentasPago(hoy: string): Promise<Respuesta<{ cuentas: CuentaPago[] }>>;
  gastoMes(mes: string): Promise<Respuesta<GastoMes>>;
}

export function crearCliente(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClienteApi {
  async function llamar<T>(ruta: string, init: RequestInit, esEscritura: boolean): Promise<Respuesta<T>> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), cfg.timeoutMs);
    try {
      const r = await fetchImpl(`${cfg.baseUrl}${ruta}`, {
        ...init,
        signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.token}` },
      });
      let cuerpo: any = null;
      try {
        cuerpo = await r.json();
      } catch {
        cuerpo = null;
      }
      if (r.ok) return { tipo: 'OK', datos: cuerpo as T };
      if (r.status >= 400 && r.status < 500 && cuerpo && typeof cuerpo.codigo === 'string') {
        return { tipo: 'RECHAZADO', codigo: cuerpo.codigo, mensaje: String(cuerpo.mensaje ?? '') };
      }
      return { tipo: 'INDETERMINADO', mensaje: esEscritura ? MSG_INDETERMINADO : MSG_SIN_CONEXION };
    } catch {
      return { tipo: 'INDETERMINADO', mensaje: esEscritura ? MSG_INDETERMINADO : MSG_SIN_CONEXION };
    } finally {
      clearTimeout(t);
    }
  }

  return {
    registrarGastoPagado: (p) =>
      llamar('/v1/intenciones/gasto-pagado', { method: 'POST', body: JSON.stringify(p) }, true),
    cuentasPago: (hoy) => llamar(`/v1/vs01/cuentas-pago?hoy=${encodeURIComponent(hoy)}`, { method: 'GET' }, false),
    gastoMes: (mes) => llamar(`/v1/vs01/gasto-mes?mes=${encodeURIComponent(mes)}`, { method: 'GET' }, false),
  };
}
