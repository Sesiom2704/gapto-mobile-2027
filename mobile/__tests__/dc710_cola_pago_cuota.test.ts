// ============================================================
// GAPTO MOBILE 2027
// Fichero: dc710_cola_pago_cuota.test.ts
// Ruta: mobile/__tests__/dc710_cola_pago_cuota.test.ts
// Descripción: D-C7-10 · ruta `PAGO_CUOTA` de COLA-AR (mandato F06 T4 DC710 v1.0 §2.4; AJ-DC710-03 y AJ-DC710-07 casos 8–10). Con el ejecutor REAL de la app (`ejecutorDe`) sobre un W-HIP-02 simulado que aplica su idempotencia por `intencion_id` (mismo payload → `idempotente: true`; cuota ya pagada por OTRA intención → 409 CUOTA_NO_PENDIENTE), un almacén en memoria y temporizadores simulados. Oráculos: la respuesta perdida se reconcilia SOLO por el replay de la MISMA intención y el mismo payload (CONFIRMADA con su 2xx); si mientras tanto otra intención pagó la cuota, el replay da CUOTA_NO_PENDIENTE → RECHAZADA con el texto de hipoteca.ts, NUNCA CONFIRMADA, y la previsión (REALIZADA) no se lee; carrera swipe/botón → un solo pago; restauración tras cerrar la app → pregunta y «Enviar» con la misma intención; segundo plano → nada se envía; cambio de owner → no se envía con el owner nuevo.
// Versión: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
// ============================================================

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import { ejecutorDe } from '../src/components/ColaAccionRapida';
import { textosPagoCuota } from '../src/domain/textosCola';
import {
  ColaAccionRapida,
  PLAZO_DESHACER_MS,
  claveDe,
  type AlmacenCola,
  type NuevaIntencion,
  type Temporizadores,
} from '../src/state/colaAccionRapida';

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
  for (let i = 0; i < 30; i++) await Promise.resolve();
};
class Almacen implements AlmacenCola {
  datos = new Map<string, string>();
  leer = async (k: string) => this.datos.get(k) ?? null;
  escribir = async (k: string, t: string) => {
    this.datos.set(k, t);
  };
}

/** W-HIP-02 simulado: una cuota; idempotente por intención; otra intención sobre la cuota pagada → CUOTA_NO_PENDIENTE. */
class WHip02 {
  pagadaPor: string | null = null;
  pagos = 0;
  llamadas: { fid: string; numero: number; payload: any }[] = [];
  /** 'PIERDE' = aplica y la respuesta se pierde; 'NO_LLEGA' = no llega al servidor. */
  guion: ('PIERDE' | 'NO_LLEGA' | 'NORMAL')[] = [];
  owner = 'A';
  leidasPrevision = 0;
  aplicar(payload: any): Respuesta<unknown> {
    if (this.pagadaPor === null) {
      this.pagadaPor = payload.intencion_id;
      this.pagos += 1;
      return { tipo: 'OK', datos: { idempotente: false, hecho_id: payload.intencion_id, hipoteca: {} } };
    }
    if (this.pagadaPor === payload.intencion_id) return { tipo: 'OK', datos: { idempotente: true, hecho_id: payload.intencion_id, hipoteca: {} } };
    return { tipo: 'RECHAZADO', codigo: 'CUOTA_NO_PENDIENTE', mensaje: 'texto del servidor' } as Respuesta<unknown>;
  }
  cliente(): ClienteApi {
    return {
      pagarCuotaHipoteca: async (fid: string, numero: number, payload: any) => {
        this.llamadas.push({ fid, numero, payload: JSON.parse(JSON.stringify(payload)) });
        const paso = this.guion.shift() ?? 'NORMAL';
        if (paso === 'NO_LLEGA') return { tipo: 'INDETERMINADO', mensaje: '' };
        const r = this.aplicar(payload);
        return paso === 'PIERDE' ? { tipo: 'INDETERMINADO', mensaje: '' } : r;
      },
      yo: async () => ({ tipo: 'OK', datos: { nombre: this.owner } }),
      detallePrevision: async () => {
        this.leidasPrevision += 1;
        return { tipo: 'OK', datos: { estado: 'REALIZADA' } };
      },
      registrarGastoPagado: async () => {
        throw new Error('la cuota nunca va por gasto-pagado');
      },
    } as unknown as ClienteApi;
  }
}

const PARTES = [{ actor_id: 'a-yo', porcentaje: '100.0000' }];
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
function pago(): NuevaIntencion {
  return { clave: 'cuota-2', ruta: 'PAGO_CUOTA', recursoId: 'fin-1/2',
    textos: textosPagoCuota({ concepto: 'CUOTA 2 HIPOTECA', importe_esperado: '632.19' }),
    payload: { intencion_id: nuevoId(), row_version_esperada: 5, cuenta_id: 'cc', fecha_pago: '2026-05-20',
      atribucion: { propuesta_vista: { partes: PARTES }, partes: PARTES } } };
}
function montar(s = new WHip02(), almacen = new Almacen(), reloj = new Reloj()) {
  const cola = new ColaAccionRapida(ejecutorDe(s.cliente(), 'http://x'), almacen, reloj);
  void cola.restaurar();
  return { s, almacen, reloj, cola };
}
const estado = (c: ColaAccionRapida) => c.get('cuota-2')?.estado;

beforeEach(() => {
  n = 0;
});

test('respuesta perdida tras pagar: «Comprobando…» y se confirma SOLO con el replay de la misma intención y el mismo payload', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  s.guion = ['PIERDE'];
  cola.lanzar(pago());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RESULTADO_DESCONOCIDO');
  await reloj.avanzar(60000);
  expect(estado(cola)).toBe('CONFIRMADA');
  expect(s.pagos).toBe(1);
  expect(s.llamadas.length).toBe(2);
  expect(s.llamadas[1]).toEqual(s.llamadas[0]); // mismo recurso, misma intención, mismo payload
  expect(s.llamadas[0]).toMatchObject({ fid: 'fin-1', numero: 2 });
  expect(s.leidasPrevision).toBe(0); // la previsión nunca decide
});

test('M6 · respuesta perdida mientras OTRA intención paga la cuota: RECHAZADA con su texto, nunca CONFIRMADA, sin leer la previsión', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  s.guion = ['NO_LLEGA'];
  cola.lanzar(pago());
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RESULTADO_DESCONOCIDO');
  // el botón del cuadro paga la misma cuota con otra intención
  s.aplicar({ intencion_id: 'boton' });
  await reloj.avanzar(60000);
  expect(estado(cola)).toBe('RECHAZADA');
  expect(cola.get('cuota-2')?.mensaje).toBe('Esta cuota ya no está pendiente.');
  expect(s.pagos).toBe(1);
  expect(s.leidasPrevision).toBe(0);
});

test('carrera swipe/botón con intenciones distintas: un solo pago; el swipe que llega después es RECHAZADA', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  cola.lanzar(pago());
  s.aplicar({ intencion_id: 'boton' }); // el botón gana mientras corre «Deshacer»
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RECHAZADA');
  expect(s.pagos).toBe(1);
});

test('M9 · cerrar la app en el plazo y reabrir: pregunta «Enviar / Descartar»; «Enviar» usa la MISMA intención', async () => {
  const a = montar();
  await asentar();
  const p = pago();
  a.cola.lanzar(p);
  await a.reloj.avanzar(1000);
  expect(a.almacen.datos.get(claveDe('http://x|A'))).toContain(String(p.payload.intencion_id));
  // la app muere (sus temporizadores mueren con ella); una instancia nueva, con su reloj, restaura lo guardado
  const relojNuevo = new Reloj();
  relojNuevo.t = a.reloj.t;
  const b = montar(a.s, a.almacen, relojNuevo);
  await asentar();
  await b.reloj.avanzar(PLAZO_DESHACER_MS * 3);
  expect(b.cola.get('cuota-2')?.pregunta).toBe(true);
  expect(a.s.llamadas.length).toBe(0); // nunca sale sola
  b.cola.enviarTrasAusencia('cuota-2');
  await b.reloj.avanzar(PLAZO_DESHACER_MS);
  expect(b.cola.get('cuota-2')?.estado).toBe('CONFIRMADA');
  expect(a.s.llamadas.map((x) => x.payload.intencion_id)).toEqual([p.payload.intencion_id]);
});

test('segundo plano durante el plazo: no se envía nada; al volver con el plazo vencido, se pregunta', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  cola.lanzar(pago());
  await reloj.avanzar(1000);
  cola.alSegundoPlano();
  await reloj.avanzar(PLAZO_DESHACER_MS * 3);
  expect(s.llamadas.length).toBe(0);
  cola.alPrimerPlano();
  await asentar();
  expect(cola.get('cuota-2')?.pregunta).toBe(true);
  expect(s.llamadas.length).toBe(0);
});

test('cambio de owner antes del envío: la intención no sale con el owner nuevo', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  cola.lanzar(pago());
  s.owner = 'B';
  await reloj.avanzar(PLAZO_DESHACER_MS * 3);
  expect(s.llamadas.length).toBe(0);
});

test('«Deshacer» dentro del plazo: CANCELADA y nunca se envía', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  cola.lanzar(pago());
  await reloj.avanzar(PLAZO_DESHACER_MS - 1);
  cola.deshacer('cuota-2');
  await reloj.avanzar(PLAZO_DESHACER_MS * 3);
  expect(s.llamadas.length).toBe(0);
});

test('recurso mal formado: RUTA_DESCONOCIDA sin llamar a W-HIP-02', async () => {
  const { s, reloj, cola } = montar();
  await asentar();
  cola.lanzar({ ...pago(), recursoId: 'fin-1/' });
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(estado(cola)).toBe('RECHAZADA');
  expect(s.llamadas.length).toBe(0);
});
