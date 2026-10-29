// ============================================================
// GAPTO MOBILE 2027
// Fichero: colaAccionRapida.ts
// Ruta: mobile/src/state/colaAccionRapida.ts
// Descripción: COLA-AR v1.0 (F05 §70.A; AJ-F0507G7-01..06): cola de las acciones rápidas FINANCIERAS a nivel de app, fuera de cualquier componente. Una intención nace al soltar el swipe con un `intencion_id` único que se persiste y se reutiliza en todo reenvío y reconciliación; nunca se genera otro para el mismo swipe (A.2). Estados de A.3: EN_PLAZO (0–5 s, se puede deshacer), CANCELADA (nunca se envía), PENDIENTE_DE_ENVIO, ENVIADA, CONFIRMADA (2xx: la API responde tras el COMMIT), RECHAZADA (4xx definitivo con su motivo), NO_ENVIADA (la comprobación de conexión previa a la escritura falló: la escritura no se intentó) y RESULTADO_DESCONOCIDO (se envió y no hubo respuesta). Ciclo de vida de A.4: desmontar o navegar en EN_PLAZO no cancela ni adelanta nada (la intención vive aquí); NUNCA se envía antes del plazo; en segundo plano no se envía nada y, al volver o al reabrir, si el plazo no ha vencido sigue la cuenta atrás y si ha vencido se PREGUNTA «Enviar / Descartar» (nunca envío automático tras una ausencia); RESULTADO_DESCONOCIDO se reconcilia con la misma identidad, en primer plano, por reenvío idempotente, y nunca se presenta como éxito ni como fallo antes de reconciliar; NO_ENVIADA ofrece «Reintentar» con la misma identidad, sin reintento automático. «No hubo» (omitir, decisión 1 de Moisés del 2026-10-29, sin tocar el servidor): el servidor no tiene replay de éxito, así que ante un 409 de un reintento (o del reenvío de una reconciliación) se LEE la previsión: OMITIDA → CONFIRMADA; cualquier otro estado → RECHAZADA con su motivo; si la lectura no responde, sigue en RESULTADO_DESCONOCIDO. Como `omitir` bloquea la previsión, la lectura que sigue a la respuesta del reenvío ve el resultado definitivo de cualquier envío anterior aún en vuelo. Persistencia mínima en el dispositivo (A.4): tipo, ids, importe, cuenta, payload de la petición, `intencion_id`, instante y estado; nunca tokens ni secretos.
// Versión: 0.1.0 (F05-D056 paso 2, COLA-AR v1.0)
// ============================================================

import type { Respuesta } from '../api/cliente';

/** Plazo de «Deshacer» (SWIPE-RULE, F05 §60.4: 5 s). */
export const PLAZO_DESHACER_MS = 5000;
/** Esperas entre reconciliaciones de un resultado desconocido (en primer plano). */
export const ESPERAS_RECONCILIACION_MS = [2000, 5000, 15000, 30000];
/** Clave de la persistencia en el dispositivo. */
export const CLAVE_ALMACEN = 'gapto.cola_ar.v1';

export type EstadoCola =
  | 'EN_PLAZO'
  | 'CANCELADA'
  | 'PENDIENTE_DE_ENVIO'
  | 'ENVIADA'
  | 'CONFIRMADA'
  | 'RECHAZADA'
  | 'NO_ENVIADA'
  | 'RESULTADO_DESCONOCIDO';

/** Ruta de escritura de una acción financiera (A.1: F1–F5 del inventario del paso 1). */
export type RutaCola = 'COBRO_POSICION' | 'PAGO_POSICION' | 'ABONO' | 'GASTO' | 'INGRESO' | 'TRANSFERENCIA' | 'NO_HUBO';

/** Textos de la intención, fijados al soltar (A.5). */
export interface TextosCola {
  /** «Cobrando… · Tania · 15,00 €» (antes de la confirmación). */
  enCurso: string;
  /** «Cobro registrado · Tania · 15,00 €». */
  confirmada: string;
  /** «Comprobando el cobro…». */
  comprobando: string;
  /** «Cobro pendiente: Cobrado de Tania · 15,00 €» (pregunta tras una ausencia). */
  pendiente: string;
}

/** Lo que el swipe entrega a la cola: la petición ya compuesta con la identidad de la intención. */
export interface NuevaIntencion {
  clave: string;
  ruta: RutaCola;
  /** Id del recurso de la URL (posición, devolución o previsión); null en las intenciones de registro. */
  recursoId: string | null;
  payload: Record<string, unknown> & { intencion_id: string };
  textos: TextosCola;
}

export interface IntencionCola extends NuevaIntencion {
  intencionId: string;
  /** Instante del swipe (ms). */
  instante: number;
  /** Fin del plazo de «Deshacer» (ms). */
  vence: number;
  estado: EstadoCola;
  /** Envíos hechos con esta identidad (1 = el primero). */
  envios: number;
  /** Intentos de envío pedidos (el vencimiento, «Enviar» o «Reintentar»), haya llegado a escribirse o no. */
  intentos: number;
  /** Tras una ausencia con el plazo vencido: se pregunta «Enviar / Descartar». */
  pregunta: boolean;
  /** Texto final o del motivo (CONFIRMADA, RECHAZADA, NO_ENVIADA). */
  mensaje: string | null;
}

/** Envía cada ruta con el cliente de la app. */
export interface EjecutorCola {
  enviar(i: IntencionCola): Promise<Respuesta<unknown>>;
  /** Lectura sin escritura previa al envío: si falla, la escritura no se intenta (NO_ENVIADA). */
  comprobarConexion(): Promise<boolean>;
  /** Estado actual de una previsión (reconciliación de «No hubo»); null si no se pudo leer. */
  estadoPrevision(previsionId: string): Promise<string | null>;
}

export interface AlmacenCola {
  leer(): Promise<string | null>;
  escribir(texto: string): Promise<void>;
}

export interface Temporizadores {
  ahora(): number;
  programar(fn: () => void, ms: number): unknown;
  cancelar(t: unknown): void;
}

const ACTIVOS: EstadoCola[] = ['EN_PLAZO', 'PENDIENTE_DE_ENVIO', 'ENVIADA', 'RESULTADO_DESCONOCIDO', 'NO_ENVIADA'];
/** Códigos con los que `omitir` responde 409 a un reintento (estado releído en `detalle`). */
const CODIGOS_409_OMITIR = ['ESTADO_PREVISION_INCOMPATIBLE', 'VERSION_DESFASADA'];

export const MENSAJE_NO_ENVIADA = 'No se ha guardado · Reintentar';

/** Motivo llano de una previsión que no quedó omitida (reconciliación de «No hubo»). */
export function motivoPrevisionNoOmitida(estado: string): string {
  if (estado === 'REALIZADA') return 'No se ha marcado «No hubo»: la previsión ya consta como cubierta.';
  if (estado === 'CANCELADA') return 'No se ha marcado «No hubo»: la previsión ya no está disponible.';
  if (estado === 'ABIERTA') return 'No se ha marcado «No hubo»: la previsión sigue pendiente.';
  return `No se ha marcado «No hubo»: la previsión está en otro estado (${estado}).`;
}

/** Texto final de una confirmación: «Saldado» solo si el servidor confirma que el saldo conocido queda a cero (A.5). */
export function textoConfirmada(i: IntencionCola, datos: unknown): string {
  if (i.ruta === 'COBRO_POSICION' || i.ruta === 'PAGO_POSICION') {
    const d = (datos ?? {}) as { saldo?: string | null; apertura_indeterminada?: boolean };
    if (d.saldo !== null && d.saldo !== undefined && Number(d.saldo) === 0 && d.apertura_indeterminada !== true) {
      return i.ruta === 'COBRO_POSICION' ? 'Saldado · no cuenta como ingreso' : 'Saldado';
    }
  }
  return i.textos.confirmada;
}

export type Oyente = (l: IntencionCola[]) => void;
export type OyenteConfirmada = (i: IntencionCola) => void;

export class ColaAccionRapida {
  private lista = new Map<string, IntencionCola>();
  private plazos = new Map<string, unknown>();
  private reconciliaciones = new Map<string, unknown>();
  private enVuelo = new Set<string>();
  private oyentes = new Set<Oyente>();
  private alConfirmar = new Set<OyenteConfirmada>();
  private primerPlano = true;
  private restaurada: Promise<void> | null = null;

  constructor(
    private ejecutor: EjecutorCola,
    private almacen: AlmacenCola,
    private t: Temporizadores,
  ) {}

  // ---------------------------------------------------------------- lectura
  intenciones(): IntencionCola[] {
    return [...this.lista.values()];
  }
  get(clave: string): IntencionCola | undefined {
    return this.lista.get(clave);
  }
  /** La fila sale de la lista mientras su intención está viva o recién confirmada. */
  oculta(clave: string): boolean {
    const i = this.lista.get(clave);
    return !!i && (ACTIVOS.includes(i.estado) || i.estado === 'CONFIRMADA');
  }
  suscribir(o: Oyente): () => void {
    this.oyentes.add(o);
    return () => this.oyentes.delete(o);
  }
  alConfirmarse(o: OyenteConfirmada): () => void {
    this.alConfirmar.add(o);
    return () => this.alConfirmar.delete(o);
  }

  // ---------------------------------------------------------------- swipe
  /** Al soltar: nace la intención en EN_PLAZO. Un segundo gesto sobre la misma clave viva no crea otra. */
  lanzar(n: NuevaIntencion): boolean {
    const previa = this.lista.get(n.clave);
    if (previa && ACTIVOS.includes(previa.estado)) return false;
    const ahora = this.t.ahora();
    const i: IntencionCola = {
      ...n, intencionId: n.payload.intencion_id, instante: ahora, vence: ahora + PLAZO_DESHACER_MS,
      estado: 'EN_PLAZO', envios: 0, intentos: 0, pregunta: false, mensaje: null,
    };
    this.lista.set(n.clave, i);
    this.programarPlazo(i);
    this.cambio();
    return true;
  }

  /** «Deshacer» dentro del plazo: CANCELADA, nunca se envía. */
  deshacer(clave: string): void {
    const i = this.lista.get(clave);
    if (!i || i.estado !== 'EN_PLAZO') return;
    this.cancelarPlazo(clave);
    this.lista.delete(clave);
    this.cambio();
  }

  /** Pregunta tras una ausencia: «Enviar» con la misma identidad. */
  enviarTrasAusencia(clave: string): void {
    const i = this.lista.get(clave);
    if (!i || i.estado !== 'EN_PLAZO' || !i.pregunta) return;
    i.pregunta = false;
    void this.enviar(clave);
  }

  /** Pregunta tras una ausencia («Descartar») o NO_ENVIADA cerrada: se cancela sin envío. */
  descartar(clave: string): void {
    const i = this.lista.get(clave);
    if (!i || !((i.estado === 'EN_PLAZO' && i.pregunta) || i.estado === 'NO_ENVIADA')) return;
    this.cancelarPlazo(clave);
    this.lista.delete(clave);
    this.cambio();
  }

  /** «Reintentar» tras NO_ENVIADA: la MISMA identidad. */
  reintentar(clave: string): void {
    const i = this.lista.get(clave);
    if (!i || i.estado !== 'NO_ENVIADA') return;
    void this.enviar(clave);
  }

  /** Cierra el aviso de una intención terminada (CONFIRMADA o RECHAZADA). */
  cerrar(clave: string): void {
    const i = this.lista.get(clave);
    if (!i || (i.estado !== 'CONFIRMADA' && i.estado !== 'RECHAZADA')) return;
    this.lista.delete(clave);
    this.cambio();
  }

  // ---------------------------------------------------------------- ciclo de vida de la app
  alSegundoPlano(): void {
    this.primerPlano = false;
    // Nada se envía en segundo plano: se paran los plazos y las reconciliaciones.
    for (const c of [...this.plazos.keys()]) this.cancelarPlazo(c);
    for (const c of [...this.reconciliaciones.keys()]) this.cancelarReconciliacion(c);
  }

  alPrimerPlano(): void {
    this.primerPlano = true;
    for (const i of this.lista.values()) this.reanudar(i);
    this.cambio();
  }

  /** Al abrir la app: lo persistido vuelve con la misma identidad. */
  restaurar(): Promise<void> {
    if (!this.restaurada) this.restaurada = this.leerAlmacen();
    return this.restaurada;
  }

  private async leerAlmacen(): Promise<void> {
    let texto: string | null = null;
    try {
      texto = await this.almacen.leer();
    } catch {
      texto = null;
    }
    if (!texto) return;
    let guardadas: IntencionCola[] = [];
    try {
      guardadas = JSON.parse(texto) as IntencionCola[];
    } catch {
      return;
    }
    for (const g of guardadas) {
      if (this.lista.has(g.clave) || !ACTIVOS.includes(g.estado)) continue;
      // La app se cerró durante el envío: no se sabe si se guardó.
      if (g.estado === 'PENDIENTE_DE_ENVIO' || g.estado === 'ENVIADA') g.estado = 'RESULTADO_DESCONOCIDO';
      this.lista.set(g.clave, g);
      if (this.primerPlano) this.reanudar(g);
    }
    this.cambio();
  }

  private reanudar(i: IntencionCola): void {
    if (i.estado === 'EN_PLAZO' && !i.pregunta) {
      // Plazo vigente: sigue la cuenta atrás; vencido durante la ausencia: se pregunta, nunca se envía solo.
      if (this.t.ahora() < i.vence) this.programarPlazo(i);
      else i.pregunta = true;
    } else if (i.estado === 'RESULTADO_DESCONOCIDO') {
      this.programarReconciliacion(i, 0);
    }
  }

  // ---------------------------------------------------------------- envío
  private programarPlazo(i: IntencionCola): void {
    this.cancelarPlazo(i.clave);
    const resto = Math.max(0, i.vence - this.t.ahora());
    this.plazos.set(i.clave, this.t.programar(() => this.vencer(i.clave), resto));
  }

  private vencer(clave: string): void {
    this.plazos.delete(clave);
    const i = this.lista.get(clave);
    if (!i || i.estado !== 'EN_PLAZO') return;
    if (this.t.ahora() < i.vence) return this.programarPlazo(i); // nunca antes del plazo
    if (!this.primerPlano) {
      i.pregunta = true;
      return this.cambio();
    }
    void this.enviar(clave);
  }

  private async enviar(clave: string): Promise<void> {
    const i = this.lista.get(clave);
    if (!i || this.enVuelo.has(clave)) return;
    if (i.estado === 'EN_PLAZO' && this.t.ahora() < i.vence) return; // nunca antes del plazo
    this.enVuelo.add(clave);
    try {
      i.intentos += 1;
      i.estado = 'PENDIENTE_DE_ENVIO';
      i.mensaje = null;
      this.cambio();
      let conexion = false;
      try {
        conexion = await this.ejecutor.comprobarConexion();
      } catch {
        conexion = false;
      }
      if (!conexion) {
        i.estado = 'NO_ENVIADA';
        i.mensaje = MENSAJE_NO_ENVIADA;
        return this.cambio();
      }
      i.estado = 'ENVIADA';
      i.envios += 1;
      this.cambio(); // persistido ANTES de enviar: si la app se cierra ahora, al volver se reconcilia
      const r = await this.enviarSeguro(i);
      await this.resolver(i, r);
    } finally {
      this.enVuelo.delete(clave);
    }
  }

  private async enviarSeguro(i: IntencionCola): Promise<Respuesta<unknown>> {
    try {
      return await this.ejecutor.enviar(i);
    } catch {
      return { tipo: 'INDETERMINADO', mensaje: '' };
    }
  }

  private async resolver(i: IntencionCola, r: Respuesta<unknown>): Promise<void> {
    if (this.lista.get(i.clave) !== i) return;
    if (r.tipo === 'OK') return this.confirmar(i, r.datos);
    if (r.tipo === 'INDETERMINADO') {
      // Se envió y no hay respuesta: ni éxito ni fallo hasta reconciliar.
      i.estado = 'RESULTADO_DESCONOCIDO';
      i.mensaje = null;
      this.cambio();
      return this.programarReconciliacion(i, 0);
    }
    // «No hubo»: el 409 de un reintento (reenvío de una reconciliación o «Reintentar») se reconcilia LEYENDO.
    const reintento = i.envios > 1 || i.intentos > 1;
    if (i.ruta === 'NO_HUBO' && reintento && CODIGOS_409_OMITIR.includes(r.codigo)) return this.leerPrevision(i);
    i.estado = 'RECHAZADA';
    i.mensaje = r.mensaje;
    this.cambio();
  }

  private async leerPrevision(i: IntencionCola): Promise<void> {
    let estado: string | null = null;
    try {
      estado = await this.ejecutor.estadoPrevision(i.recursoId ?? '');
    } catch {
      estado = null;
    }
    if (this.lista.get(i.clave) !== i) return;
    if (estado === null) {
      // Sin lectura no hay veredicto: nunca un fallo sin haber leído.
      i.estado = 'RESULTADO_DESCONOCIDO';
      this.cambio();
      return this.programarReconciliacion(i, 1);
    }
    if (estado === 'OMITIDA') return this.confirmar(i, null);
    i.estado = 'RECHAZADA';
    i.mensaje = motivoPrevisionNoOmitida(estado);
    this.cambio();
  }

  private confirmar(i: IntencionCola, datos: unknown): void {
    i.estado = 'CONFIRMADA';
    i.mensaje = textoConfirmada(i, datos);
    this.cambio();
    for (const o of [...this.alConfirmar]) o(i);
  }

  // ---------------------------------------------------------------- reconciliación del resultado desconocido
  private programarReconciliacion(i: IntencionCola, paso: number): void {
    this.cancelarReconciliacion(i.clave);
    if (!this.primerPlano) return;
    const ms = ESPERAS_RECONCILIACION_MS[Math.min(paso, ESPERAS_RECONCILIACION_MS.length - 1)];
    this.reconciliaciones.set(i.clave, this.t.programar(() => void this.reconciliar(i.clave, paso), ms));
  }

  private async reconciliar(clave: string, paso: number): Promise<void> {
    this.reconciliaciones.delete(clave);
    const i = this.lista.get(clave);
    if (!i || i.estado !== 'RESULTADO_DESCONOCIDO' || this.enVuelo.has(clave) || !this.primerPlano) return;
    this.enVuelo.add(clave);
    try {
      // Reenvío con la MISMA identidad: idempotente en F1–F4; en «No hubo», su 409 lleva a la lectura.
      i.envios += 1;
      this.cambio();
      const r = await this.enviarSeguro(i);
      if (this.lista.get(clave) !== i) return;
      if (r.tipo === 'INDETERMINADO') {
        this.cambio();
        return this.programarReconciliacion(i, paso + 1);
      }
      await this.resolver(i, r);
    } finally {
      this.enVuelo.delete(clave);
    }
  }

  // ---------------------------------------------------------------- internos
  private cancelarPlazo(clave: string): void {
    const t = this.plazos.get(clave);
    if (t !== undefined) this.t.cancelar(t);
    this.plazos.delete(clave);
  }
  private cancelarReconciliacion(clave: string): void {
    const t = this.reconciliaciones.get(clave);
    if (t !== undefined) this.t.cancelar(t);
    this.reconciliaciones.delete(clave);
  }

  private cambio(): void {
    const vivas = [...this.lista.values()].filter((i) => ACTIVOS.includes(i.estado));
    void this.almacen.escribir(JSON.stringify(vivas)).catch(() => undefined);
    const l = this.intenciones();
    for (const o of [...this.oyentes]) o(l);
  }
}
