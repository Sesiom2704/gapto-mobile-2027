// ============================================================
// GAPTO MOBILE 2027
// Fichero: g1.ts
// Ruta: mobile/src/dev/g1.ts
// Descripción: Instrumentación de la medición G1 de F05-07 (F05-D050 §64.1), SOLO en desarrollo (`__DEV__`). Un ensayo empieza con el toque que abre el flujo en Inicio («Registrar» o un acceso de plantilla) y termina con la respuesta de la confirmación (POST /v1/intenciones/*). Reloj monotónico (`performance.now()`). Cada ensayo se escribe en Metro como UNA línea `[G1] {json}` con su secuencia, el origen, la ruta, el estado HTTP, el `intencion_id` del cuerpo y el `hecho_id` de la respuesta; la correlación con el servidor va por `hecho_id` → auditoría `CREAR` (su `request_id`, su owner y su hora). Los ensayos con error también se registran (`ok: false`); un flujo abandonado se registra al abrir el siguiente. Fuera de `__DEV__` no hace nada: ni estado, ni reloj, ni log.
// Versión: 0.1.0 (F05-07 G1, preparación de la medición; tirada nocturna, paso 3)
// Versión: 0.2.0 (ídem): la línea lleva también `hecho_id` (el `request_id` de estas rutas lo genera el servidor y no es el `intencion_id`).
// Versión: 0.3.0 (ídem): el cierre se engancha con `g1Fetch` (envoltorio del `fetch` del cliente, creado en App.tsx) y no dentro de `api/cliente.ts`: el camino categorial y su registro cerrado de imports (test_154 I13) no cambian. Mide hasta la respuesta y su cuerpo.
// Versión: 0.4.0 (F05-D051 paso 9.1 · G1 v2, instrumentación por paso): `g1Paso` añade hitos al ensayo abierto (`pasos: [{e, ms, via?, n?}]`, ms relativos al `t0` del ensayo con el MISMO reloj monotónico) y viajan en la MISMA línea `[G1]` del cierre o del abandono (la correlación por `hecho_id` no cambia). `g1Cambio` deja solo el primer y el último cambio de un campo de texto (sin el valor). `g1Suscribir` registra teclado y AppState mientras la app vive (solo `__DEV__`). La línea pasa a `v: 2` con `sesion` (epoch del arranque del JS) para distinguir ensayos con la misma `seq` tras una recarga. Sin importes, textos ni datos personales en los pasos. Fuera de `__DEV__`, nada.
// ============================================================

type Log = (linea: string) => void;

/** Datos opcionales de un hito: vía de elección y un número (niveles, recuento). Nunca valores tecleados. */
export type G1Extra = { via?: string; n?: number };
/** Firma de la traza que reciben las pantallas por prop (solo se pasa en `__DEV__`). */
export type G1Traza = (evento: string, extra?: G1Extra) => void;

interface Paso extends G1Extra {
  e: string;
  ms: number;
}

interface Abierto {
  seq: number;
  origen: string;
  t0: number;
  pasos: Paso[];
  omitidos: number;
}

/** Tope de hitos por ensayo: la línea no crece sin límite (los que sobran se cuentan en `pasos_omitidos`). */
export const G1_MAX_PASOS = 300;

let secuencia = 0;
let abierto: Abierto | null = null;
/** Identifica el arranque del JS: una recarga reinicia `seq`, pero no repite `sesion`. */
const sesion = Date.now();

function reloj(): number {
  const p = (globalThis as { performance?: { now?: () => number } }).performance;
  return typeof p?.now === 'function' ? p.now() : Date.now();
}

function escribir(log: Log, a: Abierto, datos: Record<string, unknown>): void {
  const extra = a.omitidos > 0 ? { pasos_omitidos: a.omitidos } : {};
  log(`[G1] ${JSON.stringify({ v: 2, sesion, seq: a.seq, origen: a.origen, ...datos, pasos: a.pasos, ...extra, epoch_ms: Date.now() })}`);
}

/** Toque que abre el flujo en Inicio. Si había otro ensayo abierto, se registra como abandonado. */
export function g1Abrir(origen: string, dev: boolean = __DEV__, log: Log = console.log): void {
  if (!dev) return;
  const t = reloj();
  if (abierto) escribir(log, abierto, { resultado: 'ABANDONADO', ms: round(t - abierto.t0) });
  secuencia += 1;
  abierto = { seq: secuencia, origen, t0: t, pasos: [], omitidos: 0 };
}

/** Hito dentro del ensayo abierto (sin ensayo abierto, o fuera de `__DEV__`, no hace nada). */
export function g1Paso(evento: string, extra?: G1Extra, dev: boolean = __DEV__): void {
  if (!dev || !abierto) return;
  if (abierto.pasos.length >= G1_MAX_PASOS) {
    abierto.omitidos += 1;
    return;
  }
  abierto.pasos.push({ e: evento, ms: round(reloj() - abierto.t0), ...(extra ?? {}) });
}

/**
 * Cambio de un campo de texto: guarda `<campo>_1er_cambio` la primera vez y, después, UN solo
 * `<campo>_ult_cambio` que se mueve al final con su nuevo instante. Nunca el valor.
 */
export function g1Cambio(campo: string, dev: boolean = __DEV__): void {
  if (!dev || !abierto) return;
  const primero = `${campo}_1er_cambio`;
  if (!abierto.pasos.some((x) => x.e === primero)) return g1Paso(primero, undefined, dev);
  const ultimo = `${campo}_ult_cambio`;
  abierto.pasos = abierto.pasos.filter((x) => x.e !== ultimo);
  g1Paso(ultimo, undefined, dev);
}

/**
 * Traza que App.tsx pasa a las pantallas por prop, SOLO en `__DEV__` (en producción la prop es `undefined` y
 * `p.traza?.(...)` ni evalúa sus argumentos). `cambio:<campo>` va a `g1Cambio`; el resto, a `g1Paso`.
 */
export function g1Traza(evento: string, extra?: G1Extra, dev: boolean = __DEV__): void {
  if (evento.startsWith('cambio:')) return g1Cambio(evento.slice('cambio:'.length), dev);
  g1Paso(evento, extra, dev);
}

type Suscripcion = { remove: () => void };
/** Fuentes de eventos del sistema (las de react-native en App.tsx; simuladas en los tests). */
export interface G1Fuentes {
  Keyboard: { addListener: (evento: 'keyboardDidShow' | 'keyboardDidHide', f: () => void) => Suscripcion };
  AppState: { addEventListener: (evento: 'change', f: (estado: string) => void) => Suscripcion };
}

/**
 * Teclado mostrado/ocultado y estado de la app como hitos del ensayo abierto (separan las interrupciones
 * externas del tiempo de interacción). Fuera de `__DEV__` no se suscribe a nada. Devuelve la baja.
 */
export function g1Suscribir(fuentes: G1Fuentes, dev: boolean = __DEV__): () => void {
  if (!dev) return () => undefined;
  const subs = [
    fuentes.Keyboard.addListener('keyboardDidShow', () => g1Paso('teclado_on', undefined, dev)),
    fuentes.Keyboard.addListener('keyboardDidHide', () => g1Paso('teclado_off', undefined, dev)),
    fuentes.AppState.addEventListener('change', (estado) => g1Paso(`app_estado:${estado}`, undefined, dev)),
  ];
  return () => subs.forEach((x) => x.remove());
}

/** Respuesta de una confirmación (POST /v1/intenciones/*). `status` null = sin respuesta (red, timeout). */
export function g1Cerrar(
  ruta: string,
  status: number | null,
  intencionId: string | null,
  hechoId: string | null = null,
  dev: boolean = __DEV__,
  log: Log = console.log,
): void {
  if (!dev || !abierto) return;
  const ms = round(reloj() - abierto.t0);
  const ok = status !== null && status >= 200 && status < 300;
  escribir(log, abierto, { ruta, status, ok, intencion_id: intencionId, hecho_id: hechoId, resultado: ok ? 'CONFIRMADO' : 'ERROR', ms });
  abierto = null;
}

/** Solo para tests: estado interno legible y reinicio. */
export function g1Estado(): { secuencia: number; abierto: boolean; pasos: number } {
  return { secuencia, abierto: abierto !== null, pasos: abierto?.pasos.length ?? 0 };
}

export function g1Reiniciar(): void {
  secuencia = 0;
  abierto = null;
}

function round(ms: number): number {
  return Math.round(ms * 10) / 10;
}

function rutaIntencion(url: string): string | null {
  const m = /\/v1\/intenciones\/[^?#]*/.exec(url);
  return m ? m[0] : null;
}

function intencionDelCuerpo(init?: RequestInit): string | null {
  try {
    const id = JSON.parse(String(init?.body ?? 'null'))?.intencion_id;
    return typeof id === 'string' ? id : null;
  } catch {
    return null;
  }
}

/**
 * `fetch` del cliente con el cierre del ensayo G1 en las confirmaciones (POST /v1/intenciones/*). Fuera de `__DEV__`
 * devuelve el `fetch` recibido, sin envolver. El cuerpo se lee de un `clone()`: la respuesta llega intacta al cliente.
 */
export function g1Fetch(base: typeof fetch, dev: boolean = __DEV__, log: Log = console.log): typeof fetch {
  if (!dev) return base;
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : (input as Request).url;
    const ruta = init?.method === 'POST' ? rutaIntencion(url) : null;
    try {
      const r = await base(input as RequestInfo, init);
      if (ruta) {
        let hecho: string | null = null;
        try {
          const cuerpo = await r.clone().json();
          hecho = typeof cuerpo?.hecho_id === 'string' ? cuerpo.hecho_id : null;
        } catch {
          hecho = null;
        }
        g1Cerrar(ruta, r.status, intencionDelCuerpo(init), hecho, dev, log);
      }
      return r;
    } catch (e) {
      if (ruta) g1Cerrar(ruta, null, intencionDelCuerpo(init), null, dev, log);
      throw e;
    }
  }) as typeof fetch;
}
