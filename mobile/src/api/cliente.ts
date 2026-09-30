// ============================================================
// GAPTO MOBILE 2027
// Fichero: cliente.ts
// Ruta: mobile/src/api/cliente.ts
// Descripción: Cliente HTTP del adaptador F05-00-B. Clasifica cada respuesta en resultados de dominio del cliente: OK, RECHAZADO (definitivo, no persistido) o INDETERMINADO (timeout, red, 5xx: puede haberse confirmado; se reintenta la MISMA intención). Nunca expone texto técnico.
// v0.2.0 (F05-D003): cuentas-pago por fecha del pago con propuesta de financiación; resultado con la financiación sellada.
// v0.3.0 (F05-01 S6-WIRE+UI (este mandato)): lectura del árbol y del uso de una categoría y comandos de Ajustes › Categorías (alta, icono, renombrar, mover, desactivar, reactivar, ámbito y reordenar), todos con la clasificación OK / RECHAZADO(codigo) / INDETERMINADO vigente. La reordenación usa SOLO la ruta atómica /v1/categorias/reordenar (F05 §26.3): el cliente no invoca el comando por nodo. El resultado del registro informa el estado categorial.
// Versión: 0.3.0
// ============================================================

import type { Ambito, CategoriaNodo } from '../domain/categoria';
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
  financiacion: 'PROPUESTA_ACEPTADA' | 'NO_DETERMINADA';
  estado_categorial: 'CATEGORIA' | 'SIN_CATEGORIA';
}

/** Nodo devuelto por los comandos del árbol (sin magnitudes ni capturabilidad). */
export type CategoriaComando = Omit<CategoriaNodo, 'magnitudes' | 'capturable' | 'motivo_no_capturable'>;

export interface ResultadoComandoCategoria {
  categoria: CategoriaComando;
  idempotente: boolean;
  modificadas: string[];
}

export interface ResultadoReordenar {
  hermanos: CategoriaComando[];
  idempotente: boolean;
  modificadas: string[];
}

export interface UsoCategoria {
  categoria_id: string;
  ambito: Ambito;
  efectos_activos: Record<string, number>;
}

export interface AltaCategoria {
  id: string;
  nombre: string;
  parent_id: string | null;
  ambito: Ambito;
  presupuestable_default: boolean;
  icon_key: string | null;
}

export interface CuentaPago {
  cuenta_id: string;
  nombre: string;
  moneda: string;
  propuesta_financiacion: 'SELF_100' | 'NO_DETERMINADA';
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
const MSG_INDETERMINADO_CAMBIO = 'No se ha podido confirmar el cambio. Vuelve a cargar antes de repetirlo.';
const MSG_SIN_CONEXION = 'No hay conexión con el servidor.';

export interface ClienteApi {
  registrarGastoPagado(p: PayloadGastoPagado): Promise<Respuesta<ResultadoRegistro>>;
  cuentasPago(fecha: string): Promise<Respuesta<{ cuentas: CuentaPago[] }>>;
  gastoMes(mes: string): Promise<Respuesta<GastoMes>>;
  arbolCategorias(): Promise<Respuesta<{ categorias: CategoriaNodo[] }>>;
  usoCategoria(id: string): Promise<Respuesta<UsoCategoria>>;
  crearCategoria(alta: AltaCategoria): Promise<Respuesta<ResultadoComandoCategoria>>;
  iconoCategoria(id: string, c: { row_version: number; icon_key: string | null }): Promise<Respuesta<ResultadoComandoCategoria>>;
  renombrarCategoria(id: string, c: { row_version: number; nombre: string }): Promise<Respuesta<ResultadoComandoCategoria>>;
  moverCategoria(id: string, c: { row_version: number; parent_id: string | null }): Promise<Respuesta<ResultadoComandoCategoria>>;
  desactivarCategoria(
    id: string,
    c: { row_version: number; modo: 'RAMA' | 'SOLO_SI_SIN_HIJOS_ACTIVOS' },
  ): Promise<Respuesta<ResultadoComandoCategoria>>;
  reactivarCategoria(id: string, c: { row_version: number }): Promise<Respuesta<ResultadoComandoCategoria>>;
  cambiarAmbitoCategoria(
    id: string,
    c: { row_version: number; ambito: Ambito; confirmacion_uso: Record<string, number> },
  ): Promise<Respuesta<ResultadoComandoCategoria>>;
  reordenarCategorias(c: {
    parent_id: string | null;
    hermanos: { id: string; row_version: number }[];
  }): Promise<Respuesta<ResultadoReordenar>>;
}

const CAT = '/v1/categorias';
const post = (cuerpo: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(cuerpo) });

export function crearCliente(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClienteApi {
  async function llamar<T>(ruta: string, init: RequestInit, esEscritura: boolean | 'CAMBIO'): Promise<Respuesta<T>> {
    const msgIndeterminado = esEscritura === 'CAMBIO' ? MSG_INDETERMINADO_CAMBIO : esEscritura ? MSG_INDETERMINADO : MSG_SIN_CONEXION;
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
      return { tipo: 'INDETERMINADO', mensaje: msgIndeterminado };
    } catch {
      return { tipo: 'INDETERMINADO', mensaje: msgIndeterminado };
    } finally {
      clearTimeout(t);
    }
  }

  return {
    registrarGastoPagado: (p) =>
      llamar('/v1/intenciones/gasto-pagado', { method: 'POST', body: JSON.stringify(p) }, true),
    cuentasPago: (fecha) => llamar(`/v1/vs01/cuentas-pago?fecha=${encodeURIComponent(fecha)}`, { method: 'GET' }, false),
    gastoMes: (mes) => llamar(`/v1/vs01/gasto-mes?mes=${encodeURIComponent(mes)}`, { method: 'GET' }, false),
    arbolCategorias: () => llamar('/v1/categorias', { method: 'GET' }, false),
    usoCategoria: (id) => llamar(`${CAT}/${encodeURIComponent(id)}/uso`, { method: 'GET' }, false),
    crearCategoria: (alta) => llamar(CAT, post(alta), 'CAMBIO'),
    iconoCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/icono`, post(c), 'CAMBIO'),
    renombrarCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/renombrar`, post(c), 'CAMBIO'),
    moverCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/mover`, post(c), 'CAMBIO'),
    desactivarCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/desactivar`, post(c), 'CAMBIO'),
    reactivarCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/reactivar`, post(c), 'CAMBIO'),
    cambiarAmbitoCategoria: (id, c) => llamar(`${CAT}/${encodeURIComponent(id)}/ambito`, post(c), 'CAMBIO'),
    reordenarCategorias: (c) => llamar(`${CAT}/reordenar`, post(c), 'CAMBIO'),
  };
}
