// ============================================================
// GAPTO MOBILE 2027
// Fichero: g1.ts
// Ruta: mobile/src/dev/g1.ts
// Descripción: Instrumentación de la medición G1 de F05-07 (F05-D050 §64.1), SOLO en desarrollo (`__DEV__`). Un ensayo empieza con el toque que abre el flujo en Inicio («Registrar» o un acceso de plantilla) y termina con la respuesta de la confirmación (POST /v1/intenciones/*). Reloj monotónico (`performance.now()`). Cada ensayo se escribe en Metro como UNA línea `[G1] {json}` con su secuencia, el origen, la ruta, el estado HTTP, el `intencion_id` del cuerpo y el `hecho_id` de la respuesta; la correlación con el servidor va por `hecho_id` → auditoría `CREAR` (su `request_id`, su owner y su hora). Los ensayos con error también se registran (`ok: false`); un flujo abandonado se registra al abrir el siguiente. Fuera de `__DEV__` no hace nada: ni estado, ni reloj, ni log.
// Versión: 0.1.0 (F05-07 G1, preparación de la medición; tirada nocturna, paso 3)
// Versión: 0.2.0 (ídem): la línea lleva también `hecho_id` (el `request_id` de estas rutas lo genera el servidor y no es el `intencion_id`).
// ============================================================

type Log = (linea: string) => void;

interface Abierto {
  seq: number;
  origen: string;
  t0: number;
}

let secuencia = 0;
let abierto: Abierto | null = null;

function reloj(): number {
  const p = (globalThis as { performance?: { now?: () => number } }).performance;
  return typeof p?.now === 'function' ? p.now() : Date.now();
}

function escribir(log: Log, datos: Record<string, unknown>): void {
  log(`[G1] ${JSON.stringify({ v: 1, ...datos, epoch_ms: Date.now() })}`);
}

/** Toque que abre el flujo en Inicio. Si había otro ensayo abierto, se registra como abandonado. */
export function g1Abrir(origen: string, dev: boolean = __DEV__, log: Log = console.log): void {
  if (!dev) return;
  const t = reloj();
  if (abierto) escribir(log, { seq: abierto.seq, origen: abierto.origen, resultado: 'ABANDONADO', ms: round(t - abierto.t0) });
  secuencia += 1;
  abierto = { seq: secuencia, origen, t0: t };
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
  escribir(log, { seq: abierto.seq, origen: abierto.origen, ruta, status, ok, intencion_id: intencionId, hecho_id: hechoId, resultado: ok ? 'CONFIRMADO' : 'ERROR', ms });
  abierto = null;
}

/** Solo para tests: estado interno legible y reinicio. */
export function g1Estado(): { secuencia: number; abierto: boolean } {
  return { secuencia, abierto: abierto !== null };
}

export function g1Reiniciar(): void {
  secuencia = 0;
  abierto = null;
}

function round(ms: number): number {
  return Math.round(ms * 10) / 10;
}
