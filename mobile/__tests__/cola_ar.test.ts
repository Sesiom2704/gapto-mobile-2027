// ============================================================
// GAPTO MOBILE 2027
// Fichero: cola_ar.test.ts
// Ruta: mobile/__tests__/cola_ar.test.ts
// Descripción: COLA-AR v1.0 (F05 §70.A.6; AJ-F0507G7-05): las 12 pruebas obligatorias sobre la cola de la app, deterministas (reloj y temporizadores simulados, almacén en memoria, servidor simulado que aplica la idempotencia por identidad como el real: un `intencion_id` = un hecho, un movimiento y una reducción), y las de la reconciliación por lectura de «No hubo» (decisión 1 de Moisés del 2026-10-29). Las de pantalla (desmontaje, navegación y ✓) están en `cola_ar_pantallas.test.tsx`; el oráculo físico, en `tests/api/test_224_f05_d056_cola_ar.py`.
// Versión: 0.1.0 (F05-D056 paso 2)
// Versión: 0.2.0 (pre-S2, AJ-F0507G8-01/02): el ejecutor da la identidad (`identidad()`) y el almacén guarda por clave de identidad; la cola se restaura con su identidad al montarse (como en la app). Las cuentas de lecturas de identidad se toman tras esa restauración. Pruebas nuevas al final.
// ============================================================

import type { Respuesta } from '../src/api/cliente';
import {
  ColaAccionRapida,
  ESPERAS_RECONCILIACION_MS,
  MENSAJE_NO_ENVIADA,
  PLAZO_DESHACER_MS,
  type AlmacenCola,
  type EjecutorCola,
  type IntencionCola,
  type NuevaIntencion,
  type Temporizadores,
  claveDe,
} from '../src/state/colaAccionRapida';
import { textosCobroPago, textosNoHubo } from '../src/domain/textosCola';

// ---------------------------------------------------------------- arnés
class Reloj implements Temporizadores {
  t = 0;
  private cola: { id: number; en: number; fn: () => void }[] = [];
  private sig = 0;
  ahora = () => this.t;
  programar = (fn: () => void, ms: number) => {
    const id = ++this.sig;
    this.cola.push({ id, en: this.t + ms, fn });
    return id;
  };
  cancelar = (id: unknown) => {
    this.cola = this.cola.filter((x) => x.id !== id);
  };
  pendientes = () => this.cola.length;
  /** Avanza el reloj ejecutando en orden lo que vence, con las promesas asentadas entre medias. */
  async avanzar(ms: number) {
    const fin = this.t + ms;
    for (;;) {
      this.cola.sort((a, b) => a.en - b.en);
      const x = this.cola[0];
      if (!x || x.en > fin) break;
      this.cola.shift();
      this.t = x.en;
      x.fn();
      await asentar();
    }
    this.t = fin;
    await asentar();
  }
}
const asentar = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve();
};

class Almacen implements AlmacenCola {
  datos = new Map<string, string>();
  fallar = false;
  escrituras = 0;
  leer = async (k: string) => this.datos.get(k) ?? null;
  escribir = async (k: string, t: string) => {
    this.escrituras += 1;
    if (this.fallar) throw new Error('almacén lleno');
    this.datos.set(k, t);
  };
  /** Lo guardado para una identidad (por defecto la del servidor simulado). */
  get texto(): string | null {
    return this.datos.get(claveDe('A')) ?? null;
  }
  set texto(t: string | null) {
    if (t === null) this.datos.delete(claveDe('A'));
    else this.datos.set(claveDe('A'), t);
  }
}

type Resp = Respuesta<unknown>;
/** Servidor simulado: idempotente por identidad en F1–F4; «omitir» sin replay de éxito (409 con el estado releído). */
class Servidor {
  hechos = new Map<string, { ruta: string; importe: unknown }>();
  movimientos = 0;
  reducciones = 0;
  prevision = { estado: 'ABIERTA', row_version: 1 };
  conexion = true;
  /** Identidad servida (URL base + owner); cambiarla simula otro owner detrás del mismo backend. */
  owner = 'A';
  /** Respuestas forzadas por llamada (antes de aplicar), p. ej. INDETERMINADO = la respuesta se pierde. */
  guion: (('APLICA_Y_PIERDE' | 'NO_LLEGA' | Resp))[] = [];
  lecturas: (string | null)[] = [];
  llamadas: IntencionCola[] = [];
  conexiones = 0;
  leidas = 0;

  ejecutor(): EjecutorCola {
    return {
      enviar: async (i) => {
        this.llamadas.push(JSON.parse(JSON.stringify(i)));
        const paso = this.guion.shift();
        if (paso === 'NO_LLEGA') return { tipo: 'INDETERMINADO', mensaje: '' };
        if (paso && paso !== 'APLICA_Y_PIERDE') return paso;
        const r = this.aplicar(i);
        return paso === 'APLICA_Y_PIERDE' ? { tipo: 'INDETERMINADO', mensaje: '' } : r;
      },
      identidad: async () => {
        this.conexiones += 1;
        return this.conexion ? this.owner : null;
      },
      estadoPrevision: async () => {
        this.leidas += 1;
        return this.lecturas.length ? this.lecturas.shift()! : this.prevision.estado;
      },
    };
  }

  private aplicar(i: IntencionCola): Resp {
    const id = String(i.payload.intencion_id);
    if (i.ruta === 'NO_HUBO') {
      if (this.prevision.estado !== 'ABIERTA' || this.prevision.row_version !== i.payload.row_version) {
        return { tipo: 'RECHAZADO', codigo: 'ESTADO_PREVISION_INCOMPATIBLE', mensaje: 'La previsión ya no está abierta.', detalle: { estado_actual: { ...this.prevision } } };
      }
      this.prevision = { estado: 'OMITIDA', row_version: this.prevision.row_version + 1 };
      return { tipo: 'OK', datos: { estado: 'OMITIDA' } };
    }
    if (!this.hechos.has(id)) {
      this.hechos.set(id, { ruta: i.ruta, importe: i.payload.importe });
      this.movimientos += 1;
      if (i.ruta === 'COBRO_POSICION' || i.ruta === 'PAGO_POSICION') this.reducciones += 1;
      return { tipo: 'OK', datos: { saldo: '0.00', apertura_indeterminada: false, idempotente: false } };
    }
    return { tipo: 'OK', datos: { saldo: '0.00', apertura_indeterminada: false, idempotente: true } };
  }
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
function cobro(clave = 'd1'): NuevaIntencion {
  return { clave, ruta: 'COBRO_POSICION', recursoId: clave, textos: textosCobroPago(true, 'Tania', '15.00'),
    payload: { intencion_id: nuevoId(), importe: '15.00', cuenta_id: 'nomina', fecha: '2026-10-10' } };
}
function noHubo(): NuevaIntencion {
  return { clave: 'luz', ruta: 'NO_HUBO', recursoId: 'luz', textos: textosNoHubo({ concepto: 'Electricidad' }),
    payload: { intencion_id: nuevoId(), row_version: 1, motivo: null } };
}
function montar(s = new Servidor(), almacen = new Almacen(), reloj = new Reloj()) {
  const cola = new ColaAccionRapida(s.ejecutor(), almacen, reloj);
  void cola.restaurar(); // como colaDe en la app: la identidad se fija al montarse
  return { s, almacen, reloj, cola };
}
const estado = (c: ColaAccionRapida, k = 'd1') => c.get(k)?.estado;

beforeEach(() => {
  n = 0;
});

// ==================================================================
// A.6 — las 12 pruebas
// ==================================================================
test('1. Deshacer antes del plazo: CANCELADA, nunca se envía (ni la comprobación de conexión)', async () => {
  const { s, cola, reloj } = montar();
  expect(cola.lanzar(cobro())).toBe(true);
  expect(estado(cola)).toBe('EN_PLAZO');
  await reloj.avanzar(PLAZO_DESHACER_MS - 1);
  cola.deshacer('d1');
  expect(cola.get('d1')).toBeUndefined();
  await reloj.avanzar(60000);
  expect(s.llamadas).toHaveLength(0);
  expect(s.conexiones).toBe(1); // solo la lectura de identidad al montarse: ninguna por el swipe deshecho
  expect(cola.oculta('d1')).toBe(false);
});

test('2. Vencimiento sin cancelar: se envía al cumplirse el plazo, nunca antes, y queda CONFIRMADA con el resultado del servidor', async () => {
  const { s, cola, reloj } = montar();
  cola.lanzar(cobro());
  await reloj.avanzar(PLAZO_DESHACER_MS - 1);
  expect(s.llamadas).toHaveLength(0);
  expect(s.conexiones).toBe(1); // solo la de la restauración: durante el plazo no se lee nada
  await reloj.avanzar(1);
  expect(s.llamadas).toHaveLength(1);
  expect(estado(cola)).toBe('CONFIRMADA');
  expect(cola.get('d1')!.mensaje).toBe('Saldado · no cuenta como ingreso'); // el servidor deja el saldo conocido a 0
});

test('3. Desmontaje antes del vencimiento: la intención vive en la cola; no se envía antes del plazo y se envía al vencer', async () => {
  // La cola no tiene componente: «desmontar» es que ninguna pantalla la escucha. Lo de pantalla, en cola_ar_pantallas.
  const { s, cola, reloj } = montar();
  const quitar = cola.suscribir(() => undefined);
  cola.lanzar(cobro());
  await reloj.avanzar(1000);
  quitar();
  await reloj.avanzar(PLAZO_DESHACER_MS - 1001);
  expect(s.llamadas).toHaveLength(0);
  await reloj.avanzar(1);
  expect(s.llamadas).toHaveLength(1);
});

test('4. Navegación y retorno: la intención y su plazo siguen; al volver la fila sigue fuera y el envío es uno', async () => {
  const { s, cola, reloj } = montar();
  cola.lanzar(cobro());
  await reloj.avanzar(2000); // se navega a otra pantalla
  expect(cola.oculta('d1')).toBe(true);
  expect(cola.get('d1')!.vence - reloj.ahora()).toBe(3000); // el aviso global enseña el tiempo restante
  expect(cola.lanzar(cobro())).toBe(false); // al volver, la fila no admite otra intención
  await reloj.avanzar(3000);
  expect(s.llamadas).toHaveLength(1);
  expect(n).toBe(2); // la segunda identidad nunca se usó
  expect(new Set(s.llamadas.map((l) => l.payload.intencion_id))).toEqual(new Set(['00000000-0000-4000-8000-000000000001']));
});

test('5. Segundo plano y retorno: nada se envía fuera; dentro del plazo sigue la cuenta atrás; vencido, pregunta Enviar/Descartar', async () => {
  const { s, cola, reloj } = montar();
  cola.lanzar(cobro());
  await reloj.avanzar(1000);
  cola.alSegundoPlano();
  await reloj.avanzar(2000);
  cola.alPrimerPlano(); // vuelve a los 3 s: quedan 2 s
  expect(cola.get('d1')!.pregunta).toBe(false);
  await reloj.avanzar(1999);
  expect(s.llamadas).toHaveLength(0);
  await reloj.avanzar(1);
  expect(s.llamadas).toHaveLength(1);

  const b = montar();
  b.cola.lanzar(cobro('o1'));
  await b.reloj.avanzar(1000);
  b.cola.alSegundoPlano();
  await b.reloj.avanzar(60000);
  expect(b.s.llamadas).toHaveLength(0);
  b.cola.alPrimerPlano();
  await b.reloj.avanzar(60000);
  expect(b.s.llamadas).toHaveLength(0); // nunca se envía automáticamente tras una ausencia
  expect(b.cola.get('o1')!.pregunta).toBe(true);
  const id = b.cola.get('o1')!.intencionId;
  b.cola.enviarTrasAusencia('o1');
  await b.reloj.avanzar(0);
  expect(b.s.llamadas.map((l) => l.payload.intencion_id)).toEqual([id]);
  expect(b.cola.get('o1')!.estado).toBe('CONFIRMADA');
});

test('6. Cierre y reapertura: al reabrir pregunta Enviar/Descartar con la misma identidad; Descartar no envía nada', async () => {
  const almacen = new Almacen();
  const a = montar(new Servidor(), almacen);
  a.cola.lanzar(cobro());
  await a.reloj.avanzar(2000); // la app se cierra aquí (la cola A desaparece)
  const guardada = JSON.parse(almacen.texto!) as IntencionCola[];
  expect(guardada).toHaveLength(1);
  expect(Object.keys(guardada[0]).sort()).toEqual(['clave', 'envios', 'estado', 'instante', 'intencionId', 'intentos', 'mensaje', 'payload', 'pregunta', 'recursoId', 'ruta', 'textos', 'vence']);
  expect(almacen.texto).not.toMatch(/token|Bearer|password/i); // sin secretos

  const reloj = new Reloj();
  reloj.t = 3_600_000; // una hora después
  const b = montar(new Servidor(), almacen, reloj);
  await b.cola.restaurar();
  await reloj.avanzar(60000);
  expect(b.s.llamadas).toHaveLength(0);
  expect(b.cola.get('d1')!.pregunta).toBe(true);
  b.cola.enviarTrasAusencia('d1');
  await reloj.avanzar(0);
  expect(b.s.llamadas.map((l) => l.payload.intencion_id)).toEqual([guardada[0].intencionId]);

  const c = montar(new Servidor(), new Almacen());
  c.cola.lanzar(cobro('o1'));
  const almacen2 = c.almacen;
  const r2 = new Reloj();
  r2.t = 3_600_000;
  const d = montar(new Servidor(), almacen2, r2);
  await d.cola.restaurar();
  d.cola.descartar('o1');
  await r2.avanzar(60000);
  expect(d.s.llamadas).toHaveLength(0);
  expect(d.cola.get('o1')).toBeUndefined();
});

test('6b. La app se cerró DURANTE el envío: al reabrir es un resultado desconocido y se reconcilia con la misma identidad, sin duplicar', async () => {
  const almacen = new Almacen();
  const s = new Servidor();
  const a = montar(s, almacen);
  s.guion = ['APLICA_Y_PIERDE'];
  a.cola.lanzar(cobro());
  await a.reloj.avanzar(PLAZO_DESHACER_MS); // escribió en el servidor, sin respuesta; la app se cierra
  const guardada = JSON.parse(almacen.texto!) as IntencionCola[];
  guardada[0].estado = 'ENVIADA'; // como si se hubiera cerrado entre el envío y la respuesta
  almacen.texto = JSON.stringify(guardada);
  const b = montar(s, almacen);
  await b.cola.restaurar();
  expect(b.cola.get('d1')!.estado).toBe('RESULTADO_DESCONOCIDO');
  await b.reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
  expect(b.cola.get('d1')!.estado).toBe('CONFIRMADA');
  expect(s.hechos.size).toBe(1);
  expect(s.reducciones).toBe(1);
});

test('7. Red desconectada: NO_ENVIADA sin intentar la escritura; «Reintentar» con la misma identidad; ningún reintento automático', async () => {
  const s = new Servidor();
  s.conexion = false;
  const { cola, reloj } = montar(s);
  cola.lanzar(cobro());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('NO_ENVIADA');
  expect(cola.get('d1')!.mensaje).toBe(MENSAJE_NO_ENVIADA);
  expect(s.llamadas).toHaveLength(0);
  await reloj.avanzar(10 * 60000);
  expect(s.llamadas).toHaveLength(0);
  expect(s.conexiones).toBe(2); // restauración + el único intento (sin reintento automático)
  s.conexion = true;
  const id = cola.get('d1')!.intencionId;
  cola.reintentar('d1');
  await reloj.avanzar(0);
  expect(s.llamadas.map((l) => l.payload.intencion_id)).toEqual([id]);
  expect(estado(cola)).toBe('CONFIRMADA');
});

test('8. Respuesta perdida tras una escritura confirmada: «Comprobando…», reconcilia con la misma identidad y no duplica', async () => {
  const s = new Servidor();
  s.guion = ['APLICA_Y_PIERDE', 'NO_LLEGA'];
  const { cola, reloj } = montar(s);
  cola.lanzar(cobro());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RESULTADO_DESCONOCIDO'); // ni éxito ni fallo
  expect(cola.get('d1')!.mensaje).toBeNull();
  await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]); // reenvío: tampoco llega
  expect(estado(cola)).toBe('RESULTADO_DESCONOCIDO');
  await reloj.avanzar(ESPERAS_RECONCILIACION_MS[1]); // reenvío: el servidor reconoce la identidad
  expect(estado(cola)).toBe('CONFIRMADA');
  expect(s.llamadas).toHaveLength(3);
  expect(new Set(s.llamadas.map((l) => l.payload.intencion_id)).size).toBe(1);
  expect(s.hechos.size).toBe(1);
  expect(s.movimientos).toBe(1);
  expect(s.reducciones).toBe(1);
});

test('9. 4xx → RECHAZADA con el motivo del servidor; 5xx (INDETERMINADO en el cliente) → nunca se presenta como fallo: se reconcilia', async () => {
  const s = new Servidor();
  s.guion = [{ tipo: 'RECHAZADO', codigo: 'POSICION_CERRADA', mensaje: 'Esta posición ya está saldada.' }];
  const { cola, reloj } = montar(s);
  cola.lanzar(cobro());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RECHAZADA');
  expect(cola.get('d1')!.mensaje).toBe('Esta posición ya está saldada.');
  expect(cola.oculta('d1')).toBe(false); // la fila vuelve
  await reloj.avanzar(60000);
  expect(s.llamadas).toHaveLength(1); // un rechazo no se reintenta

  const b = montar();
  b.s.guion = [{ tipo: 'INDETERMINADO', mensaje: 'error del servidor' }];
  b.cola.lanzar(cobro());
  await b.reloj.avanzar(PLAZO_DESHACER_MS);
  expect(b.cola.get('d1')!.estado).toBe('RESULTADO_DESCONOCIDO');
  await b.reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
  expect(b.cola.get('d1')!.estado).toBe('CONFIRMADA');
});

test('10. Doble swipe y reintento: una sola intención y una sola identidad en todos los envíos', async () => {
  const s = new Servidor();
  s.conexion = false;
  const { cola, reloj } = montar(s);
  expect(cola.lanzar(cobro())).toBe(true);
  expect(cola.lanzar(cobro())).toBe(false);
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(cola.lanzar(cobro())).toBe(false); // NO_ENVIADA: la fila no admite otro swipe
  s.conexion = true;
  s.guion = ['NO_LLEGA'];
  cola.reintentar('d1');
  cola.reintentar('d1'); // doble toque en «Reintentar»
  await reloj.avanzar(0);
  await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
  expect(estado(cola)).toBe('CONFIRMADA');
  expect(s.llamadas).toHaveLength(2);
  expect(new Set(s.llamadas.map((l) => l.payload.intencion_id))).toEqual(new Set(['00000000-0000-4000-8000-000000000001']));
  expect(s.hechos.size).toBe(1);
});

test('11. Cambio de elegibilidad o capacidad antes del envío: decide el servidor; RECHAZADA con su motivo, sin éxito falso', async () => {
  const s = new Servidor();
  s.guion = [{ tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje: 'Cuenta nómina ya no puede recibir cobros.' }];
  const { cola, reloj } = montar(s);
  cola.lanzar(cobro()); // la capacidad cambia durante el plazo: la cola no la decide por su cuenta
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RECHAZADA');
  expect(cola.get('d1')!.mensaje).toBe('Cuenta nómina ya no puede recibir cobros.');
  expect(s.hechos.size).toBe(0);
});

test('12. Ni doble movimiento ni doble reducción: concurrencia de dos envíos de la misma intención (oráculo del servidor simulado)', async () => {
  const s = new Servidor();
  s.guion = ['APLICA_Y_PIERDE'];
  const { cola, reloj } = montar(s);
  cola.lanzar(cobro());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  // Reintento manual imposible mientras se reconcilia: solo la cola reenvía, y nunca dos a la vez.
  cola.reintentar('d1');
  await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
  await reloj.avanzar(60000);
  expect(estado(cola)).toBe('CONFIRMADA');
  expect(s.hechos.size).toBe(1);
  expect(s.movimientos).toBe(1);
  expect(s.reducciones).toBe(1);
  expect(s.llamadas).toHaveLength(2);
});

// ==================================================================
// «No hubo»: reconciliación por lectura (decisión 1 de Moisés)
// ==================================================================
describe('«No hubo» (omitir sin replay de éxito)', () => {
  test('primer envío con 409: RECHAZADA con el motivo del servidor, sin lectura (no es un reintento)', async () => {
    const s = new Servidor();
    s.prevision = { estado: 'OMITIDA', row_version: 2 }; // otro dispositivo la omitió antes
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    expect(estado(cola, 'luz')).toBe('RECHAZADA');
    expect(s.leidas).toBe(0);
  });

  test('respuesta perdida tras omitir: el reenvío recibe 409 y la LECTURA dice OMITIDA → CONFIRMADA (sin segunda escritura)', async () => {
    const s = new Servidor();
    s.guion = ['APLICA_Y_PIERDE'];
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    expect(estado(cola, 'luz')).toBe('RESULTADO_DESCONOCIDO');
    expect(s.leidas).toBe(0); // nunca un veredicto antes de que la respuesta del reenvío fije el resultado
    await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
    expect(s.leidas).toBe(1);
    expect(estado(cola, 'luz')).toBe('CONFIRMADA');
    expect(cola.get('luz')!.mensaje).toBe('Electricidad · no hubo este mes');
    expect(s.prevision).toEqual({ estado: 'OMITIDA', row_version: 2 });
  });

  test('el envío original no llegó: el reenvío omite (200) → CONFIRMADA sin lectura', async () => {
    const s = new Servidor();
    s.guion = ['NO_LLEGA'];
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
    expect(estado(cola, 'luz')).toBe('CONFIRMADA');
    expect(s.leidas).toBe(0);
  });

  test('reenvío con 409 y la lectura dice otro estado → RECHAZADA con su motivo', async () => {
    const s = new Servidor();
    s.guion = ['NO_LLEGA', { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'Ha cambiado.' }];
    s.prevision = { estado: 'REALIZADA', row_version: 2 };
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]);
    expect(s.leidas).toBe(1);
    expect(estado(cola, 'luz')).toBe('RECHAZADA');
    expect(cola.get('luz')!.mensaje).toBe('No se ha marcado «No hubo»: la previsión ya consta como cubierta.');
  });

  test('si la lectura no responde no hay veredicto: sigue «Comprobando…» y vuelve a intentarlo; nunca un fallo sin leer', async () => {
    const s = new Servidor();
    s.guion = ['APLICA_Y_PIERDE'];
    s.lecturas = [null];
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    await reloj.avanzar(ESPERAS_RECONCILIACION_MS[0]); // reenvío 409 → lectura sin respuesta
    expect(s.leidas).toBe(1);
    expect(estado(cola, 'luz')).toBe('RESULTADO_DESCONOCIDO');
    await reloj.avanzar(ESPERAS_RECONCILIACION_MS[1]); // reenvío 409 → lectura OMITIDA
    expect(estado(cola, 'luz')).toBe('CONFIRMADA');
  });

  test('NO_ENVIADA → «Reintentar» (se mantiene): un 409 de ese reintento también se reconcilia leyendo', async () => {
    const s = new Servidor();
    s.conexion = false;
    const { cola, reloj } = montar(s);
    cola.lanzar(noHubo());
    await reloj.avanzar(PLAZO_DESHACER_MS);
    expect(estado(cola, 'luz')).toBe('NO_ENVIADA');
    s.conexion = true;
    s.prevision = { estado: 'OMITIDA', row_version: 2 }; // la omitió otra sesión mientras tanto
    cola.reintentar('luz');
    await reloj.avanzar(0);
    // «Reintentar» es un reintento: su 409 se reconcilia leyendo (OMITIDA → CONFIRMADA).
    expect(s.leidas).toBe(1);
    expect(estado(cola, 'luz')).toBe('CONFIRMADA');
  });
});

// ==================================================================
// AJ-F0507G8-01: la persistencia se espera antes de enviar
// ==================================================================
describe('AJ-F0507G8-01 · persistencia antes del envío', () => {
  test('si no se puede guardar, NO_ENVIADA y la escritura nunca se intenta', async () => {
    const { s, almacen, cola, reloj } = montar();
    await reloj.avanzar(0);
    cola.lanzar(cobro());
    almacen.fallar = true;
    await reloj.avanzar(PLAZO_DESHACER_MS);
    expect(estado(cola)).toBe('NO_ENVIADA');
    expect(s.llamadas).toHaveLength(0);
  });

  test('el envío no sale hasta que PENDIENTE_DE_ENVIO y después ENVIADA están guardadas (en ese orden)', async () => {
    const s = new Servidor();
    const almacen = new Almacen();
    const pendientes: { estado: string; resolver: () => void }[] = [];
    let lento = false;
    const base = almacen.escribir;
    almacen.escribir = (k: string, t: string) => {
      if (!lento) return base(k, t);
      const e = (JSON.parse(t) as IntencionCola[]).find((x) => x.clave === 'd1')?.estado ?? '-';
      return new Promise<void>((res) => pendientes.push({ estado: e, resolver: () => void base(k, t).then(res) }));
    };
    let guardadoAlEnviar: string | undefined;
    const ej = s.ejecutor();
    const ejecutor = { ...ej, enviar: async (i: IntencionCola) => {
      guardadoAlEnviar = (JSON.parse(almacen.texto ?? '[]') as IntencionCola[]).find((x) => x.clave === 'd1')?.estado;
      return ej.enviar(i);
    } };
    const reloj = new Reloj();
    const cola = new ColaAccionRapida(ejecutor, almacen, reloj);
    void cola.restaurar();
    await reloj.avanzar(0);
    cola.lanzar(cobro());
    await reloj.avanzar(1000);
    lento = true;
    await reloj.avanzar(PLAZO_DESHACER_MS - 1000);
    expect(pendientes.map((p) => p.estado)).toEqual(['PENDIENTE_DE_ENVIO']); // espera a guardarla antes de seguir
    expect(s.llamadas).toHaveLength(0);
    pendientes[0].resolver();
    await reloj.avanzar(0);
    expect(pendientes.map((p) => p.estado)).toEqual(['PENDIENTE_DE_ENVIO', 'ENVIADA']);
    expect(s.llamadas).toHaveLength(0); // ENVIADA aún no está guardada: no se envía
    lento = false;
    pendientes[1].resolver();
    await reloj.avanzar(0);
    expect(s.llamadas).toHaveLength(1);
    expect(guardadoAlEnviar).toBe('ENVIADA'); // si la app muere ahora, al reabrir es un resultado desconocido, no EN_PLAZO
  });
});

// ==================================================================
// AJ-F0507G8-02: una cola por identidad (URL base + owner servido)
// ==================================================================
describe('AJ-F0507G8-02 · cola por identidad', () => {
  test('al reabrir con OTRO owner no se restaura nada; con el mismo, sí (como pregunta tras la ausencia)', async () => {
    const almacen = new Almacen();
    const a = montar(new Servidor(), almacen);
    await a.reloj.avanzar(0);
    a.cola.lanzar(cobro());
    await a.reloj.avanzar(1000); // se cierra la app
    const sb = new Servidor();
    sb.owner = 'B';
    const rb = new Reloj();
    rb.t = 3_600_000;
    const b = montar(sb, almacen, rb);
    await rb.avanzar(60000);
    expect(b.cola.intenciones()).toHaveLength(0);
    expect(sb.llamadas).toHaveLength(0);
    const rc = new Reloj();
    rc.t = 3_600_000;
    const c = montar(new Servidor(), almacen, rc);
    await rc.avanzar(0);
    expect(c.cola.get('d1')?.pregunta).toBe(true);
  });

  test('si al enviar sirve otro owner, no se envía como él: la intención queda guardada con el suyo como pregunta', async () => {
    const { s, almacen, cola, reloj } = montar();
    await reloj.avanzar(0);
    cola.lanzar(cobro());
    await reloj.avanzar(2000);
    s.owner = 'B'; // -Fase Ronda: el backend pasa a servir otro owner
    await reloj.avanzar(PLAZO_DESHACER_MS);
    expect(s.llamadas).toHaveLength(0);
    expect(cola.get('d1')).toBeUndefined();
    expect(cola.identidadActual()).toBe('B');
    const guardada = (JSON.parse(almacen.texto!) as IntencionCola[]).find((x) => x.clave === 'd1')!;
    expect([guardada.estado, guardada.pregunta]).toEqual(['EN_PLAZO', true]);
  });

  test('al volver a primer plano con otro owner servido se cambia de cola; ningún envío cruzado', async () => {
    const { s, almacen, cola, reloj } = montar();
    await reloj.avanzar(0);
    cola.lanzar(cobro());
    await reloj.avanzar(1000);
    cola.alSegundoPlano();
    s.owner = 'B';
    cola.alPrimerPlano();
    await reloj.avanzar(60000);
    expect(s.llamadas).toHaveLength(0);
    expect(cola.identidadActual()).toBe('B');
    expect(cola.intenciones()).toHaveLength(0);
    expect(almacen.datos.has(claveDe('A'))).toBe(true);
  });
});