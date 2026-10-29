// ============================================================
// GAPTO MOBILE 2027
// Fichero: exploradorColaAR.ts
// Ruta: mobile/__tests__/explorador/exploradorColaAR.ts
// Descripción: Explorador de intercalaciones de COLA-AR (F05 §70.A; mandato de la consulta 10, AJ-F0507G9-01). Ejecuta la cola REAL (`ColaAccionRapida` y `manejarEstadoApp` del adaptador) dentro de un mundo simulado: reloj y temporizadores, almacén con lecturas y escrituras en una sola cola en orden (FIFO, como AsyncStorage) que pueden fallar, y escrituras que se pierden o se completan al matar la app, identidad servida (A, sin conexión u otro owner B), ejecutor de red cuyas respuestas llegan en cualquier orden (OK, respuesta perdida con o sin aplicación, rechazo) y un servidor idempotente por `intencion_id` (y «omitir» sin replay de éxito: 409 al repetir). AppState active / inactive / background, matar la app (con las escrituras pendientes perdidas o completadas) y reabrirla. Cada paso es un evento atómico tras el que se asientan todas las microtareas; los únicos puntos de elección son los eventos. Recorre en profundidad, SIN ESTADO y repitiendo cada camino desde cero, TODOS los órdenes de eventos posibles hasta la profundidad pedida, con presupuestos de fallos, ausencias, muertes y gestos del usuario. Invariantes: I1 nunca POST antes del plazo ni de un swipe que el usuario canceló en esa misma instancia de la app o cuya cancelación ya estaba guardada (si la app muere antes de guardar la cancelación, la intención puede reaparecer al reabrir: se cuenta como «resurrección», observación aparte, y el usuario coherente la vuelve a cancelar); I2 nunca POST con la app ausente (ni desde una instancia muerta); I3 una sola identidad y el mismo payload por swipe en todos los POST, y como mucho una aplicación efectiva; I4 nunca CONFIRMADA sin una respuesta OK (o la lectura OMITIDA) entregada, ni RECHAZADA sin un rechazo o una lectura; I5 vivacidad: al final de cada camino, con la app en primer plano, el servidor respondiendo y un usuario que contesta a las preguntas con su decisión, toda intención no cancelada de la identidad A llega a CONFIRMADA o RECHAZADA en 120 s simulados (las guardadas con otro owner quedan con el suyo y las que nunca llegaron a guardarse antes de matar la app quedan fuera); I6 nunca se pierde una intención persistida (sigue en memoria o en el almacén hasta su final o su cancelación).
// Versión: 0.1.0 (consulta 10, AJ-F0507G9-01)
// ============================================================

import { manejarEstadoApp } from '../../src/components/ColaAccionRapida';
import { textosCobroPago, textosNoHubo } from '../../src/domain/textosCola';
import {
  ColaAccionRapida,
  PLAZO_DESHACER_MS,
  claveDe,
  type AlmacenCola,
  type EjecutorCola,
  type EstadoCola,
  type IntencionCola,
  type RutaCola,
  type Temporizadores,
} from '../../src/state/colaAccionRapida';
import type { Respuesta } from '../../src/api/cliente';

export type Invariante = 'I1' | 'I2' | 'I3' | 'I4' | 'I5' | 'I6';
export const INVARIANTES: Invariante[] = ['I1', 'I2', 'I3', 'I4', 'I5', 'I6'];

type Resp = Respuesta<unknown>;
type AppEstado = 'active' | 'inactive' | 'background' | 'muerta';

/** Estado inicial de la cola (uno por estado de A.3, en memoria o restaurado del almacén). */
export interface ConfigExploracion {
  nombre: string;
  ruta: RutaCola;
  /** NUEVA = swipe en t=0 con la restauración aún en curso; el resto, una intención guardada con ese estado. */
  inicial: 'NUEVA' | 'EN_PLAZO_VIGENTE' | 'EN_PLAZO_VENCIDO' | 'PREGUNTA' | 'PENDIENTE_DE_ENVIO' | 'ENVIADA' | 'RESULTADO_DESCONOCIDO' | 'NO_ENVIADA';
  /** El servidor ya aplicó la intención guardada (ENVIADA / RESULTADO_DESCONOCIDO / PENDIENTE). */
  aplicada?: boolean;
  /** Prefijo determinista (camino de etiquetas) que lleva la cola a un estado en memoria antes de explorar. */
  prefijo?: string[];
  profundidad: number;
  /** Identidades que puede servir `/v1/yo`: A, null (sin conexión) y, si se pide, B (otro owner). */
  conOtroOwner?: boolean;
  presupuesto?: Partial<Presupuesto>;
}

export interface Presupuesto {
  fallos: number;
  ausencias: number;
  muertes: number;
  usuario: number;
  swipes: number;
}
const PRESUPUESTO: Presupuesto = { fallos: 2, ausencias: 2, muertes: 1, usuario: 2, swipes: 1 };

export interface Violacion {
  invariante: Invariante;
  detalle: string;
  camino: string[];
}

export interface ResultadoConfig {
  nombre: string;
  profundidad: number;
  presupuesto: Presupuesto;
  caminos: number;
  transiciones: number;
  maxRamificacion: number;
  violaciones: Record<Invariante, number>;
  /**
   * Observación (no invariante): caminos en los que una cancelación aún no guardada se pierde al matar la app y, al
   * reabrir, la intención reaparece y sale (ventana inherente al almacenamiento asíncrono; ver I1).
   */
  resurrecciones: number;
  /** Caminos con violación por firma («invariante: detalle»), con el camino más corto de cada una. */
  firmas: Record<string, { caminos: number; masCorto: string[] }>;
  ejemplos: Violacion[];
  ms: number;
}

interface Swipe {
  clave: string;
  intencionId: string;
  payload: string;
  vence: number;
  cancelada: boolean;
  /** Instancia (generación) en la que el usuario canceló, y si una escritura posterior ya la guardó sin la intención. */
  canceladaEn: number;
  cancelacionGuardada: boolean;
  persistida: boolean;
  terminal: boolean;
}

interface Op {
  n: number;
  gen: number;
  tipo: 'IDENTIDAD' | 'ENVIO' | 'LECTURA_PREVISION';
  i?: IntencionCola;
  res: (v: unknown) => void;
}
/** Operación del almacén: lecturas y escrituras en UNA cola FIFO (AsyncStorage las atiende en serie). */
interface Escritura {
  n: number;
  gen: number;
  lectura: boolean;
  clave: string;
  texto: string;
  res: (v?: unknown) => void;
  rej: (e: Error) => void;
}
interface Timer {
  id: number;
  gen: number;
  en: number;
  fn: () => void;
}

interface Evento {
  etiqueta: string;
  hacer: () => void;
  coste?: Partial<Presupuesto>;
}

const asentar = async () => {
  for (let k = 0; k < 3; k++) await new Promise<void>((r) => setImmediate(r));
};

const ID_BASE = '00000000-0000-4000-8000-';
const CLAVE = 'd1';

/** Un mundo: una ejecución reproducible de la cola. */
class Mundo {
  t = 0;
  gen = 0;
  app: AppEstado = 'active';
  cola: ColaAccionRapida | null = null;
  almacen = new Map<string, string>();
  escrituras: Escritura[] = [];
  ops: Op[] = [];
  timers: Timer[] = [];
  private sig = 0;
  // servidor
  aplicadas = new Set<string>();
  prevision: 'ABIERTA' | 'OMITIDA' = 'ABIERTA';
  // oráculos
  swipes = new Map<string, Swipe>();
  okEntregados = new Set<string>();
  rechazosEntregados = new Set<string>();
  /** Identidad de cada POST → swipe al que pertenece (I3). */
  postDe = new Map<string, string>();
  violaciones: { invariante: Invariante; detalle: string }[] = [];
  resurreccion = false;
  gasto: Presupuesto = { fallos: 0, ausencias: 0, muertes: 0, usuario: 0, swipes: 0 };
  camino: string[] = [];
  private nIds = 0;

  constructor(private cfg: ConfigExploracion, private tope: Presupuesto) {}

  // ---------------------------------------------------------------- dependencias de la cola
  private ejecutor(gen: number): EjecutorCola {
    return {
      enviar: (i) => {
        this.alPost(i, gen);
        return new Promise<Resp>((res) => this.ops.push({ n: ++this.sig, gen, tipo: 'ENVIO', i: JSON.parse(JSON.stringify(i)), res: res as (v: unknown) => void }));
      },
      identidad: () => new Promise<string | null>((res) => this.ops.push({ n: ++this.sig, gen, tipo: 'IDENTIDAD', res: res as (v: unknown) => void })),
      estadoPrevision: () => new Promise<string | null>((res) => this.ops.push({ n: ++this.sig, gen, tipo: 'LECTURA_PREVISION', res: res as (v: unknown) => void })),
    };
  }
  private almacenDe(gen: number): AlmacenCola {
    return {
      leer: (clave) => new Promise<string | null>((res, rej) => this.escrituras.push({ n: ++this.sig, gen, lectura: true, clave, texto: '', res: res as (v?: unknown) => void, rej })),
      escribir: (clave, texto) => new Promise<void>((res, rej) => this.escrituras.push({ n: ++this.sig, gen, lectura: false, clave, texto, res: res as (v?: unknown) => void, rej })),
    };
  }
  private temporizadoresDe(gen: number): Temporizadores {
    return {
      ahora: () => this.t,
      programar: (fn, ms) => {
        const id = ++this.sig;
        this.timers.push({ id, gen, en: this.t + ms, fn });
        return id;
      },
      cancelar: (id) => {
        this.timers = this.timers.filter((x) => x.id !== id);
      },
    };
  }

  // ---------------------------------------------------------------- oráculos
  private violar(invariante: Invariante, detalle: string) {
    this.violaciones.push({ invariante, detalle });
  }

  private alPost(i: IntencionCola, gen: number) {
    const id = String(i.payload.intencion_id);
    const s = this.swipes.get(id) ?? [...this.swipes.values()].find((x) => x.clave === i.clave && !x.terminal);
    if (!s) return this.violar('I3', `POST con una identidad que no es de ningún swipe (${id})`);
    this.postDe.set(id, s.intencionId);
    if (this.t < s.vence) this.violar('I1', `POST en t=${this.t} antes del plazo (${s.vence})`);
    // Cancelado en esta misma instancia o ya guardado como cancelado: nunca sale. Si la app murió antes de guardar la
    // cancelación, la intención reaparece al reabrir: se cuenta aparte (resurrección), no es I1.
    if (s.cancelada && (s.canceladaEn === gen || s.cancelacionGuardada)) this.violar('I1', 'POST de un swipe que el usuario canceló');
    else if (s.cancelada) this.resurreccion = true;
    if (gen !== this.gen || this.app !== 'active') this.violar('I2', `POST con la app ${gen !== this.gen ? 'muerta (instancia anterior)' : this.app}`);
    if (id !== s.intencionId) this.violar('I3', `POST con otra identidad para el mismo swipe (${id} ≠ ${s.intencionId})`);
    else if (JSON.stringify(i.payload) !== s.payload) this.violar('I3', 'POST con otro payload para el mismo swipe');
  }

  private comprobar() {
    const viva = this.cola ? this.cola.intenciones() : [];
    for (const i of viva) {
      const s = this.swipes.get(i.intencionId);
      if (i.estado === 'CONFIRMADA' && !this.okEntregados.has(i.intencionId)) this.violar('I4', 'CONFIRMADA sin respuesta OK ni lectura OMITIDA entregada');
      if (i.estado === 'RECHAZADA' && !this.rechazosEntregados.has(i.intencionId)) this.violar('I4', 'RECHAZADA sin rechazo ni lectura entregada');
      if (s && (i.estado === 'CONFIRMADA' || i.estado === 'RECHAZADA')) s.terminal = true;
    }
    // I3: como mucho una aplicación efectiva por swipe (el servidor deduplica por identidad).
    for (const s of this.swipes.values()) {
      const efectivas = [...this.aplicadas].filter((id) => (this.postDe.get(id) ?? id) === s.intencionId).length;
      if (efectivas > 1) this.violar('I3', 'dos aplicaciones efectivas del mismo swipe');
    }
    // I6: una intención persistida sigue en memoria o en el almacén hasta su final o su cancelación.
    const guardadas = new Set<string>();
    for (const texto of this.almacen.values()) for (const g of JSON.parse(texto) as IntencionCola[]) guardadas.add(g.intencionId);
    const enMemoria = new Set(viva.map((i) => i.intencionId));
    for (const s of this.swipes.values()) {
      if (!s.persistida || s.cancelada || s.terminal) continue;
      if (!enMemoria.has(s.intencionId) && !guardadas.has(s.intencionId)) this.violar('I6', `intención persistida perdida (${s.intencionId})`);
    }
  }

  // ---------------------------------------------------------------- arranque
  private nuevoSwipe(): { intencionId: string; payload: Record<string, unknown> & { intencion_id: string } } {
    const intencionId = `${ID_BASE}${String(++this.nIds).padStart(12, '0')}`;
    const payload = this.cfg.ruta === 'NO_HUBO'
      ? { intencion_id: intencionId, row_version: 1, motivo: null }
      : { intencion_id: intencionId, importe: '15.00', cuenta_id: 'nomina', fecha: '2026-10-10' };
    return { intencionId, payload };
  }

  private textos() {
    return this.cfg.ruta === 'NO_HUBO' ? textosNoHubo({ concepto: 'Electricidad' }) : textosCobroPago(true, 'Tania', '15.00');
  }

  private abrir() {
    this.gen += 1;
    this.app = 'active';
    const gen = this.gen;
    this.cola = new ColaAccionRapida(this.ejecutor(gen), this.almacenDe(gen), this.temporizadoresDe(gen));
    void this.cola.restaurar();
  }

  private lanzar() {
    const { intencionId, payload } = this.nuevoSwipe();
    const ok = this.cola!.lanzar({ clave: CLAVE, ruta: this.cfg.ruta, recursoId: CLAVE, textos: this.textos(), payload });
    if (ok) {
      const i = this.cola!.get(CLAVE)!;
      this.swipes.set(intencionId, { clave: CLAVE, intencionId, payload: JSON.stringify(payload), vence: i.vence, cancelada: false, canceladaEn: 0, cancelacionGuardada: false, persistida: false, terminal: false });
    }
  }

  async iniciar() {
    const c = this.cfg;
    this.t = 100000;
    if (c.inicial !== 'NUEVA') {
      const { intencionId, payload } = this.nuevoSwipe();
      const estado: EstadoCola = c.inicial === 'PREGUNTA' || c.inicial.startsWith('EN_PLAZO') ? 'EN_PLAZO' : (c.inicial as EstadoCola);
      const instante = c.inicial === 'EN_PLAZO_VIGENTE' ? this.t - 2000 : this.t - 60000;
      const g: IntencionCola = {
        clave: CLAVE, ruta: c.ruta, recursoId: CLAVE, payload, textos: this.textos(), intencionId, instante, vence: instante + PLAZO_DESHACER_MS,
        estado, envios: ['ENVIADA', 'RESULTADO_DESCONOCIDO'].includes(estado) ? 1 : 0, intentos: estado === 'EN_PLAZO' ? 0 : 1,
        pregunta: c.inicial === 'PREGUNTA', mensaje: estado === 'NO_ENVIADA' ? 'No se ha guardado · Reintentar' : null,
      };
      this.almacen.set(claveDe('A'), JSON.stringify([g]));
      this.swipes.set(intencionId, { clave: CLAVE, intencionId, payload: JSON.stringify(payload), vence: g.vence, cancelada: false, canceladaEn: 0, cancelacionGuardada: false, persistida: true, terminal: false });
      if (c.aplicada) {
        this.aplicadas.add(intencionId);
        if (c.ruta === 'NO_HUBO') this.prevision = 'OMITIDA';
      }
    }
    this.abrir();
    if (c.inicial === 'NUEVA') this.lanzar();
    await asentar();
    for (const ficha of c.prefijo ?? []) {
      // Ficha: la etiqueta exacta, el final «TIPO=resultado» de una operación o «ALMACEN=ok» (la primera del almacén en cola).
      const e = this.eventos().find((x) => x.etiqueta === ficha || x.etiqueta.endsWith(`:${ficha}`)
        || (ficha === 'ALMACEN=ok' && /^(esc|lee)\d+=ok$/.test(x.etiqueta)));
      if (!e) throw new Error(`prefijo: no existe el evento «${ficha}» (hay: ${this.eventos().map((x) => x.etiqueta).join(', ')})`);
      await this.aplicar(e, false);
    }
    this.camino = [];
    this.violaciones = [];
    this.gasto = { fallos: 0, ausencias: 0, muertes: 0, usuario: 0, swipes: 0 };
  }

  /** Estado de la intención del swipe original (para comprobar los prefijos). */
  estadoActual(): string {
    const i = this.cola?.get(CLAVE);
    return i ? `${i.estado}${i.pregunta ? '?' : ''}` : '-';
  }

  // ---------------------------------------------------------------- eventos
  private puede(coste: Partial<Presupuesto> | undefined): boolean {
    if (!coste) return true;
    return (Object.keys(coste) as (keyof Presupuesto)[]).every((k) => this.gasto[k] + (coste[k] ?? 0) <= this.tope[k]);
  }

  private resolverOp(op: Op, v: unknown) {
    this.ops = this.ops.filter((x) => x !== op);
    op.res(v);
  }

  private procesarEnServidor(i: IntencionCola): Resp {
    const id = String(i.payload.intencion_id);
    if (i.ruta === 'NO_HUBO') {
      if (this.prevision !== 'ABIERTA') return { tipo: 'RECHAZADO', codigo: 'ESTADO_PREVISION_INCOMPATIBLE', mensaje: 'La previsión ya no está abierta.' };
      this.prevision = 'OMITIDA';
      this.aplicadas.add(id);
      return { tipo: 'OK', datos: { estado: 'OMITIDA' } };
    }
    const idem = this.aplicadas.has(id);
    this.aplicadas.add(id);
    return { tipo: 'OK', datos: { saldo: '0.00', apertura_indeterminada: false, idempotente: idem } };
  }

  /** Eventos posibles en el estado actual, en orden determinista. */
  eventos(): Evento[] {
    const ev: Evento[] = [];
    const viva = this.app !== 'muerta';
    // Reloj: dispara el siguiente temporizador de la instancia viva.
    const t = [...this.timers].filter((x) => x.gen === this.gen).sort((a, b) => a.en - b.en || a.id - b.id)[0];
    if (viva && t) {
      ev.push({ etiqueta: 'reloj', hacer: () => {
        this.timers = this.timers.filter((x) => x !== t);
        this.t = Math.max(this.t, t.en);
        t.fn();
      } });
    }
    // Operaciones de red y lecturas del almacén: cualquier orden.
    for (const op of this.ops) {
      if (op.gen !== this.gen) continue;
      const pre = `op${op.n}:${op.tipo}`;
      if (op.tipo === 'IDENTIDAD') {
        ev.push({ etiqueta: `${pre}=A`, hacer: () => this.resolverOp(op, 'A') });
        ev.push({ etiqueta: `${pre}=null`, coste: { fallos: 1 }, hacer: () => this.resolverOp(op, null) });
        if (this.cfg.conOtroOwner) ev.push({ etiqueta: `${pre}=B`, coste: { fallos: 1 }, hacer: () => this.resolverOp(op, 'B') });
      } else if (op.tipo === 'LECTURA_PREVISION') {
        ev.push({ etiqueta: `${pre}=leida`, hacer: () => {
          this.entregarLectura();
          this.resolverOp(op, this.prevision);
        } });
        ev.push({ etiqueta: `${pre}=null`, coste: { fallos: 1 }, hacer: () => this.resolverOp(op, null) });
      } else {
        const i = op.i!;
        const id = String(i.payload.intencion_id);
        ev.push({ etiqueta: `${pre}=OK`, hacer: () => {
          const r = this.procesarEnServidor(i);
          if (r.tipo === 'OK') this.okEntregados.add(id);
          else this.rechazosEntregados.add(id);
          this.resolverOp(op, r);
        } });
        ev.push({ etiqueta: `${pre}=PERDIDA_APLICADA`, coste: { fallos: 1 }, hacer: () => {
          this.procesarEnServidor(i);
          this.resolverOp(op, { tipo: 'INDETERMINADO', mensaje: '' });
        } });
        ev.push({ etiqueta: `${pre}=PERDIDA_NO_APLICADA`, coste: { fallos: 1 }, hacer: () => this.resolverOp(op, { tipo: 'INDETERMINADO', mensaje: '' }) });
        const aplicable = i.ruta === 'NO_HUBO' ? this.prevision === 'ABIERTA' : !this.aplicadas.has(id);
        if (aplicable) {
          ev.push({ etiqueta: `${pre}=RECHAZO`, coste: { fallos: 1 }, hacer: () => {
            this.rechazosEntregados.add(id);
            this.resolverOp(op, { tipo: 'RECHAZADO', codigo: 'REGLA', mensaje: 'Rechazada por el servidor.' });
          } });
        }
      }
    }
    // Almacén: lecturas y escrituras en orden (FIFO); la primera termina bien o falla.
    const w = this.escrituras.find((x) => x.gen === this.gen);
    if (viva && w) {
      const pre = w.lectura ? `lee${w.n}` : `esc${w.n}`;
      ev.push({ etiqueta: `${pre}=ok`, hacer: () => this.terminarEscritura(w, true) });
      ev.push({ etiqueta: `${pre}=falla`, coste: { fallos: 1 }, hacer: () => this.terminarEscritura(w, false) });
    }
    // Ciclo de vida de la app (a través del adaptador real).
    if (this.app === 'active') {
      ev.push({ etiqueta: 'app:inactive', coste: { ausencias: 1 }, hacer: () => this.estadoApp('inactive') });
      ev.push({ etiqueta: 'app:background', coste: { ausencias: 1 }, hacer: () => this.estadoApp('background') });
    } else if (this.app === 'inactive') {
      ev.push({ etiqueta: 'app:active', hacer: () => this.estadoApp('active') });
      ev.push({ etiqueta: 'app:background', hacer: () => this.estadoApp('background') });
    } else if (this.app === 'background') {
      ev.push({ etiqueta: 'app:active', hacer: () => this.estadoApp('active') });
    }
    if (this.app === 'background' || this.app === 'inactive' || this.app === 'muerta') {
      ev.push({ etiqueta: 'esperar6s', hacer: () => void (this.t += 6000) });
    }
    if (viva) {
      ev.push({ etiqueta: 'matar:perder', coste: { muertes: 1 }, hacer: () => this.matar(false) });
      ev.push({ etiqueta: 'matar:completar', coste: { muertes: 1 }, hacer: () => this.matar(true) });
    } else {
      ev.push({ etiqueta: 'abrir', hacer: () => this.abrir() });
    }
    // Usuario (solo con la app delante).
    if (this.app === 'active' && this.cola) {
      for (const i of this.cola.intenciones()) {
        const s = this.swipes.get(i.intencionId);
        const k = i.clave;
        if (i.estado === 'EN_PLAZO' && !i.pregunta) {
          // Un usuario coherente vuelve a deshacer la que había cancelado si reaparece.
          ev.push({ etiqueta: `usuario:deshacer`, coste: { usuario: 1 }, hacer: () => {
            this.cancelar(s);
            this.cola!.deshacer(k);
          } });
        }
        if (i.pregunta || i.estado === 'NO_ENVIADA') {
          if (s && !s.cancelada) {
            ev.push({ etiqueta: i.pregunta ? 'usuario:enviar' : 'usuario:reintentar', coste: { usuario: 1 },
              hacer: () => (i.pregunta ? this.cola!.enviarTrasAusencia(k) : this.cola!.reintentar(k)) });
          }
          ev.push({ etiqueta: 'usuario:descartar', coste: { usuario: 1 }, hacer: () => {
            this.cancelar(s);
            this.cola!.descartar(k);
          } });
        }
      }
      // Otro swipe sobre la misma fila (la pantalla solo lo deja si la fila está a la vista).
      if (!this.cola.oculta(CLAVE)) ev.push({ etiqueta: 'usuario:swipe', coste: { swipes: 1 }, hacer: () => this.lanzar() });
    }
    return ev.filter((e) => this.puede(e.coste));
  }

  private entregarLectura() {
    // Una lectura de la previsión es un veredicto autoritativo para la intención de «No hubo» viva.
    for (const s of this.swipes.values()) {
      if (this.prevision === 'OMITIDA') this.okEntregados.add(s.intencionId);
      else this.rechazosEntregados.add(s.intencionId);
    }
  }

  private terminarEscritura(w: Escritura, ok: boolean) {
    this.escrituras = this.escrituras.filter((x) => x !== w);
    if (!ok) return w.rej(new Error('almacén'));
    if (w.lectura) return w.res(this.almacen.get(w.clave) ?? null);
    this.guardar(w.clave, w.texto);
    w.res();
  }

  private guardar(clave: string, texto: string) {
    this.almacen.set(clave, texto);
    const ids = new Set((JSON.parse(texto) as IntencionCola[]).map((g) => g.intencionId));
    for (const s of this.swipes.values()) {
      if (ids.has(s.intencionId)) s.persistida = true;
      else if (s.cancelada && clave === claveDe('A')) s.cancelacionGuardada = true;
    }
  }

  private cancelar(s: Swipe | undefined) {
    if (!s) return;
    s.cancelada = true;
    s.canceladaEn = this.gen;
  }

  private estadoApp(e: 'active' | 'inactive' | 'background') {
    this.app = e;
    manejarEstadoApp(this.cola!, e);
  }

  private matar(completar: boolean) {
    const gen = this.gen;
    for (const w of this.escrituras.filter((x) => x.gen === gen)) if (completar && !w.lectura) this.guardar(w.clave, w.texto);
    this.escrituras = this.escrituras.filter((x) => x.gen !== gen);
    // Los POST en vuelo de la instancia muerta llegan al servidor; su respuesta ya no la recibe nadie.
    for (const op of this.ops.filter((x) => x.gen === gen && x.tipo === 'ENVIO')) this.procesarEnServidor(op.i!);
    this.ops = this.ops.filter((x) => x.gen !== gen);
    this.timers = this.timers.filter((x) => x.gen !== gen);
    this.cola = null;
    this.app = 'muerta';
  }

  async aplicar(e: Evento, registrar = true) {
    if (e.coste) for (const k of Object.keys(e.coste) as (keyof Presupuesto)[]) this.gasto[k] += e.coste[k] ?? 0;
    if (registrar) this.camino.push(e.etiqueta);
    e.hacer();
    await asentar();
    this.comprobar();
  }

  // ---------------------------------------------------------------- vivacidad (I5)
  /**
   * Final de un camino: la app vuelve (o se reabre) y se queda delante, el servidor responde bien y el usuario contesta a
   * las preguntas con su decisión (Enviar / Reintentar si no había cancelado; Descartar si sí). Toda intención no
   * cancelada debe llegar a CONFIRMADA o RECHAZADA en 120 s simulados.
   */
  async asentarVivo() {
    const corto = (etiqueta: string, hacer: () => void): Evento => ({ etiqueta: `[vivo] ${etiqueta}`, hacer });
    if (this.app === 'muerta') await this.aplicar(corto('abrir', () => this.abrir()));
    else if (this.app !== 'active') await this.aplicar(corto('app:active', () => this.estadoApp('active')));
    if (this.cola && this.cola.identidadActual() !== 'A') {
      // Otro owner servido durante el camino: el usuario vuelve a la app con el suyo.
      await this.aplicar(corto('app:background', () => this.estadoApp('background')));
      await this.aplicar(corto('app:active', () => this.estadoApp('active')));
    }
    const t0 = this.t;
    for (let paso = 0; paso < 400 && this.t - t0 <= 120000; paso++) {
      const op = this.ops.filter((x) => x.gen === this.gen).sort((a, b) => a.n - b.n)[0];
      const w = this.escrituras.find((x) => x.gen === this.gen);
      const cola = this.cola!;
      const preguntas = cola.intenciones().filter((i) => i.pregunta || i.estado === 'NO_ENVIADA'
        || (i.estado === 'EN_PLAZO' && this.swipes.get(i.intencionId)?.cancelada));
      const tm = this.timers.filter((x) => x.gen === this.gen).sort((a, b) => a.en - b.en || a.id - b.id)[0];
      let e: Evento | undefined;
      if (w) e = corto(`${w.lectura ? 'lee' : 'esc'}${w.n}=ok`, () => this.terminarEscritura(w, true));
      else if (op) {
        const bien = this.eventos().find((x) => x.etiqueta === `op${op.n}:${op.tipo}=${op.tipo === 'IDENTIDAD' ? 'A' : op.tipo === 'ENVIO' ? 'OK' : 'leida'}`);
        e = bien ? corto(bien.etiqueta, bien.hacer) : undefined;
      } else if (preguntas.length) {
        const i = preguntas[0];
        const s = this.swipes.get(i.intencionId);
        if (!s || s.cancelada) {
          e = i.pregunta || i.estado === 'NO_ENVIADA' ? corto('usuario:descartar', () => cola.descartar(i.clave)) : corto('usuario:deshacer', () => cola.deshacer(i.clave));
        }
        else e = corto(i.pregunta ? 'usuario:enviar' : 'usuario:reintentar', () => (i.pregunta ? cola.enviarTrasAusencia(i.clave) : cola.reintentar(i.clave)));
      } else if (tm) {
        e = corto('reloj', () => {
          this.timers = this.timers.filter((x) => x !== tm);
          this.t = Math.max(this.t, tm.en);
          tm.fn();
        });
      }
      if (!e) break;
      await this.aplicar(e);
      if (tm && this.t - t0 > 120000) break;
    }
    const viva = new Map((this.cola?.intenciones() ?? []).map((i) => [i.intencionId, i]));
    const deA = new Set((JSON.parse(this.almacen.get(claveDe('A')) ?? '[]') as IntencionCola[]).map((g) => g.intencionId));
    const deOtra = new Set([...this.almacen.entries()].filter(([k]) => k !== claveDe('A'))
      .flatMap(([, t]) => (JSON.parse(t) as IntencionCola[]).map((g) => g.intencionId)));
    for (const s of this.swipes.values()) {
      if (s.cancelada || s.terminal) continue;
      const i = viva.get(s.intencionId);
      // Nunca llegó a guardarse y la app murió: fuera del alcance de I5/I6 (§70.A.4 solo promete lo persistido).
      if (!i && !s.persistida) continue;
      // Guardada con otro owner (B): nunca progresa con A, y es lo correcto (A.4 por identidad).
      if (!i && !deA.has(s.intencionId) && deOtra.has(s.intencionId)) continue;
      this.violar('I5', `tras 120 s con la app delante y el servidor respondiendo: ${i ? `${i.estado}${i.pregunta ? ' (pregunta)' : ''}` : 'fuera de la memoria'}, ` +
        `temporizadores ${this.timers.filter((x) => x.gen === this.gen).length}, envíos ${i?.envios ?? '-'}`);
    }
  }
}

/** Recorre en profundidad todos los caminos de una configuración (sin estado, repitiendo cada camino desde cero). */
export async function explorar(cfg: ConfigExploracion, opciones: { maxEjemplos?: number; limiteCaminos?: number } = {}): Promise<ResultadoConfig> {
  const tope = { ...PRESUPUESTO, ...(cfg.presupuesto ?? {}) };
  const inicio = Date.now();
  const res: ResultadoConfig = {
    nombre: cfg.nombre, profundidad: cfg.profundidad, presupuesto: tope, caminos: 0, transiciones: 0, maxRamificacion: 0,
    violaciones: { I1: 0, I2: 0, I3: 0, I4: 0, I5: 0, I6: 0 }, resurrecciones: 0, firmas: {}, ejemplos: [], ms: 0,
  };
  const maxEjemplos = opciones.maxEjemplos ?? 2;
  const elecciones: number[] = [];
  for (;;) {
    const m = new Mundo(cfg, tope);
    await m.iniciar();
    const anchos: number[] = [];
    for (let d = 0; d < cfg.profundidad; d++) {
      const ev = m.eventos();
      if (ev.length === 0) break;
      res.maxRamificacion = Math.max(res.maxRamificacion, ev.length);
      const k = d < elecciones.length ? elecciones[d] : 0;
      if (d >= elecciones.length) elecciones.push(0);
      anchos.push(ev.length);
      await m.aplicar(ev[k]);
      res.transiciones += 1;
    }
    elecciones.length = anchos.length;
    const caminoExplorado = [...m.camino];
    await m.asentarVivo();
    res.caminos += 1;
    if (m.resurreccion) res.resurrecciones += 1;
    const vistas = new Set<Invariante>();
    const firmasVistas = new Set<string>();
    for (const v of m.violaciones) {
      const camino = [...caminoExplorado, '‖', ...m.camino.slice(caminoExplorado.length)];
      const firma = `${v.invariante}: ${v.detalle.replace(/\(0{8}-[0-9a-f-]+\)/g, '(id)')}`;
      if (!firmasVistas.has(firma)) {
        firmasVistas.add(firma);
        const f = (res.firmas[firma] ??= { caminos: 0, masCorto: camino });
        f.caminos += 1;
        if (caminoExplorado.length < f.masCorto.indexOf('‖')) f.masCorto = camino;
      }
      if (vistas.has(v.invariante)) continue;
      vistas.add(v.invariante);
      res.violaciones[v.invariante] += 1;
      if (res.ejemplos.filter((x) => x.invariante === v.invariante).length < maxEjemplos) {
        res.ejemplos.push({ invariante: v.invariante, detalle: v.detalle, camino });
      }
    }
    if (opciones.limiteCaminos && res.caminos >= opciones.limiteCaminos) break;
    // Siguiente camino: la última elección que aún tiene hermanos.
    let d = anchos.length - 1;
    while (d >= 0 && elecciones[d] + 1 >= anchos[d]) d--;
    if (d < 0) break;
    elecciones[d] += 1;
    elecciones.length = d + 1;
  }
  res.ms = Date.now() - inicio;
  return res;
}

/** Prefijos deterministas hasta cada estado en memoria (todo responde bien salvo lo indicado). */
export const PREFIJO_EN_PLAZO = ['IDENTIDAD=A', 'ALMACEN=ok', 'ALMACEN=ok'];
export const PREFIJO_PENDIENTE = [...PREFIJO_EN_PLAZO, 'reloj'];
export const PREFIJO_ENVIADA = [...PREFIJO_PENDIENTE, 'IDENTIDAD=A', 'ALMACEN=ok', 'ALMACEN=ok'];
export const PREFIJO_DESCONOCIDO = [...PREFIJO_ENVIADA, 'ENVIO=PERDIDA_APLICADA'];

/** Prepara el mundo de una configuración y devuelve el estado de su intención (pruebas de los prefijos). */
export async function prepararMundo(cfg: ConfigExploracion): Promise<string> {
  const m = new Mundo(cfg, { ...PRESUPUESTO, ...(cfg.presupuesto ?? {}) });
  await m.iniciar();
  return m.estadoActual();
}

/** Un estado inicial por estado de A.3 (en memoria o restaurado), y los de «No hubo» y otro owner. */
export function configuraciones(profundidad: number): ConfigExploracion[] {
  const p = profundidad;
  return [
    { nombre: 'NUEVA (swipe con la restauración en curso)', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: p },
    { nombre: 'EN_PLAZO restaurada, plazo vigente', ruta: 'COBRO_POSICION', inicial: 'EN_PLAZO_VIGENTE', profundidad: p },
    { nombre: 'EN_PLAZO restaurada, plazo vencido', ruta: 'COBRO_POSICION', inicial: 'EN_PLAZO_VENCIDO', profundidad: p },
    { nombre: 'PREGUNTA restaurada', ruta: 'COBRO_POSICION', inicial: 'PREGUNTA', profundidad: p },
    { nombre: 'PENDIENTE_DE_ENVIO restaurada', ruta: 'COBRO_POSICION', inicial: 'PENDIENTE_DE_ENVIO', profundidad: p },
    { nombre: 'ENVIADA restaurada (aplicada)', ruta: 'COBRO_POSICION', inicial: 'ENVIADA', aplicada: true, profundidad: p },
    { nombre: 'RESULTADO_DESCONOCIDO restaurada (aplicada)', ruta: 'COBRO_POSICION', inicial: 'RESULTADO_DESCONOCIDO', aplicada: true, profundidad: p },
    { nombre: 'RESULTADO_DESCONOCIDO restaurada (no aplicada)', ruta: 'COBRO_POSICION', inicial: 'RESULTADO_DESCONOCIDO', aplicada: false, profundidad: p },
    { nombre: 'NO_ENVIADA restaurada', ruta: 'COBRO_POSICION', inicial: 'NO_ENVIADA', profundidad: p },
    { nombre: 'EN_PLAZO en memoria (identidad adoptada)', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: p, prefijo: PREFIJO_EN_PLAZO },
    { nombre: 'PENDIENTE_DE_ENVIO en memoria (enviar() espera la identidad)', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: p, prefijo: PREFIJO_PENDIENTE },
    { nombre: 'ENVIADA en memoria (POST en vuelo)', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: p, prefijo: PREFIJO_ENVIADA },
    { nombre: 'RESULTADO_DESCONOCIDO en memoria (respuesta perdida)', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: p, prefijo: PREFIJO_DESCONOCIDO },
    { nombre: '«No hubo» NUEVA', ruta: 'NO_HUBO', inicial: 'NUEVA', profundidad: p },
    { nombre: '«No hubo» RESULTADO_DESCONOCIDO restaurada (aplicada)', ruta: 'NO_HUBO', inicial: 'RESULTADO_DESCONOCIDO', aplicada: true, profundidad: p },
    { nombre: '«No hubo» RESULTADO_DESCONOCIDO restaurada (no aplicada)', ruta: 'NO_HUBO', inicial: 'RESULTADO_DESCONOCIDO', aplicada: false, profundidad: p },
    { nombre: 'Otro owner · RESULTADO_DESCONOCIDO restaurada', ruta: 'COBRO_POSICION', inicial: 'RESULTADO_DESCONOCIDO', aplicada: true, profundidad: Math.max(1, p - 2), conOtroOwner: true },
    { nombre: 'Otro owner · NUEVA', ruta: 'COBRO_POSICION', inicial: 'NUEVA', profundidad: Math.max(1, p - 2), conOtroOwner: true },
  ];
}
