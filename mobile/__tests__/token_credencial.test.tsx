// ============================================================
// GAPTO MOBILE 2027
// Fichero: token_credencial.test.tsx
// Ruta: mobile/__tests__/token_credencial.test.tsx
// Descripción: F06 T4 · token BETA_LOCAL (mandato 4f0e40af… §2 y §5; dictamen AJ-TOK-01/02/05/06/07, casos A–F y mutantes M-TOK-03..10). Proveedor REAL de credencial con un llavero en memoria y un PC simulado por `fetch` (tokens válidos, /v1/salud, /v1/yo y W-HIP-02 idempotente por intención); clientes REALES de la app (`crearCliente`, `crearLlamada`) y la cola REAL (`ColaAccionRapida` + `ejecutorDe`). Casos:
//   A · arranque con el llavero lento y con la validación en curso: ninguna petición autenticada sale.
//   B · timeout de /v1/salud: no es credencial inválida; se conserva y «Reintentar» conecta.
//   C · revocación con la app abierta: 401 → aviso y SIN_CREDENCIAL; recuperación con el código nuevo.
//   D · COLA-AR: credencial perdida antes del envío (NO_ENVIADA) y durante el envío (401 → RESULTADO_DESCONOCIDO, nunca RECHAZADA); sin envío sin credencial, sin intención nueva, sin pérdida y un solo pago al reconectar.
//   E · el token nunca aparece en la consola ni en los mensajes.
//   F · «Desconectar» borra el llavero y la memoria; un resultado tardío no reconecta.
//   Transporte (M-TOK-10), pantallas «Conectar con tu PC» y «Desconectar este iPhone», y la puerta de la app.
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppConCredencial } from '../App';
import { crearCliente, crearLlamada, MSG_SIN_CREDENCIAL, type ClienteApi, type ConfigApi } from '../src/api/cliente';
import { ProveedorCredencial, type AlmacenCredencial } from '../src/api/credencial';
import { hostPrivado, transportePermitido } from '../src/api/transporte';
import { ejecutorDe } from '../src/components/ColaAccionRapida';
import { textosPagoCuota } from '../src/domain/textosCola';
import { ConectarScreen } from '../src/screens/ConectarScreen';
import { AjustesScreen } from '../src/screens/MasScreen';
import { ColaAccionRapida, PLAZO_DESHACER_MS, type AlmacenCola, type NuevaIntencion, type Temporizadores } from '../src/state/colaAccionRapida';
import { ProveedorTema } from '../src/theme/tema';

const BASE = 'http://192.168.1.50:8027';
const A = 'codigo-a-' + 'k7m2p9x4q8w3e6r5t1y0u2i3o4p5a6s7';
const B = 'codigo-b-' + 'z9x8c7v6b5n4m3l2k1j0h9g8f7d6s5a4';

const asentar = async () => {
  for (let i = 0; i < 40; i++) await Promise.resolve();
};

/** Promesa controlable desde el test. */
function diferida<T>() {
  let resolver!: (v: T) => void;
  const p = new Promise<T>((r) => (resolver = r));
  return { p, resolver };
}

class Llavero implements AlmacenCredencial {
  valor: string | null = null;
  lecturas = 0;
  guardados: string[] = [];
  borrados = 0;
  pendienteLeer: Promise<void> | null = null;
  leer = async () => {
    this.lecturas += 1;
    if (this.pendienteLeer) await this.pendienteLeer;
    return this.valor;
  };
  guardar = async (v: string) => {
    this.guardados.push(v);
    this.valor = v;
  };
  borrar = async () => {
    this.borrados += 1;
    this.valor = null;
  };
}

type Peticion = { ruta: string; metodo: string; auth: string | null; cuerpo: any };

/** PC simulado: Bearer contra `validos`; W-HIP-02 idempotente por intención. */
class Pc {
  validos = new Set<string>([A]);
  peticiones: Peticion[] = [];
  pagos = 0;
  pagadaPor: string | null = null;
  /** Respuesta de /v1/salud: normal, o sin respuesta (timeout/red). */
  saludCaida = false;
  saludPendiente: Promise<void> | null = null;
  /** Revoca A justo después de responder a /v1/yo (carrera de D2). */
  revocarTrasYo = false;
  fetch = (async (url: string, init?: RequestInit) => {
    const ruta = url.replace(BASE, '');
    const h = (init?.headers ?? {}) as Record<string, string>;
    const auth = h.Authorization ?? null;
    const cuerpo = init?.body ? JSON.parse(String(init.body)) : null;
    this.peticiones.push({ ruta, metodo: init?.method ?? 'GET', auth, cuerpo });
    const resp = (status: number, datos: unknown) => ({ status, ok: status >= 200 && status < 300, json: async () => datos }) as unknown as Response;
    if (ruta === '/v1/salud') {
      if (this.saludPendiente) await this.saludPendiente;
      if (this.saludCaida) throw new Error('timeout');
    }
    const token = auth?.startsWith('Bearer ') ? auth.slice(7) : null;
    if (!token || !this.validos.has(token)) return resp(401, { codigo: 'NO_AUTORIZADO', mensaje: 'Sesión de desarrollo no válida.', reintentable: false });
    if (ruta === '/v1/salud') return resp(200, { estado: 'OK' });
    if (ruta === '/v1/yo') {
      if (this.revocarTrasYo) {
        this.revocarTrasYo = false;
        this.validos.delete(A);
      }
      return resp(200, { nombre: 'Moisés' });
    }
    if (/\/v1\/hipotecas\/.+\/cuotas\/\d+\/pago$/.test(ruta)) {
      if (this.pagadaPor === null) {
        this.pagadaPor = cuerpo.intencion_id;
        this.pagos += 1;
        return resp(200, { idempotente: false, hecho_id: cuerpo.intencion_id, hipoteca: {} });
      }
      if (this.pagadaPor === cuerpo.intencion_id) return resp(200, { idempotente: true, hecho_id: cuerpo.intencion_id, hipoteca: {} });
      return resp(409, { codigo: 'CUOTA_NO_PENDIENTE', mensaje: 'x' });
    }
    return resp(200, {});
  }) as unknown as typeof fetch;
  pagosEnviados() {
    return this.peticiones.filter((p) => p.ruta.endsWith('/pago'));
  }
}

function montarProveedor(pc = new Pc(), llavero = new Llavero(), base = BASE) {
  const proveedor = new ProveedorCredencial({ baseUrl: base, almacen: llavero, fetchImpl: pc.fetch, timeoutMs: 1000 });
  const cfg: ConfigApi = {
    baseUrl: base,
    token: '',
    credencial: () => proveedor.tokenParaPeticion(),
    alNoAutorizado: (t) => proveedor.noAutorizado(t),
    timeoutMs: 1000,
  };
  return { pc, llavero, proveedor, cfg };
}

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
class AlmacenMem implements AlmacenCola {
  datos = new Map<string, string>();
  leer = async (k: string) => this.datos.get(k) ?? null;
  escribir = async (k: string, t: string) => {
    this.datos.set(k, t);
  };
}
const PARTES = [{ actor_id: 'a-yo', porcentaje: '100.0000' }];
const INTENCION = '00000000-0000-4000-8000-0000000000aa';
function pago(): NuevaIntencion {
  return { clave: 'cuota-2', ruta: 'PAGO_CUOTA', recursoId: 'fin-1/2',
    textos: textosPagoCuota({ concepto: 'CUOTA 2 HIPOTECA', importe_esperado: '632.19' }),
    payload: { intencion_id: INTENCION, row_version_esperada: 5, cuenta_id: 'cc', fecha_pago: '2026-05-20',
      atribucion: { propuesta_vista: { partes: PARTES }, partes: PARTES } } };
}

// ---------------------------------------------------------------- consola espiada en TODOS los casos (E)
let consola: jest.SpyInstance[] = [];
const textoConsola = () => consola.flatMap((s) => s.mock.calls.map((c) => c.map(String).join(' '))).join('\n');
beforeEach(() => {
  consola = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => jest.spyOn(console, m));
});
afterEach(() => {
  const t = textoConsola();
  expect(t).not.toContain(A);
  expect(t).not.toContain(B);
  consola.forEach((s) => s.mockRestore());
});

// ---------------------------------------------------------------- A · arranque asíncrono
test('A · con el llavero lento y con la validación en curso no sale ninguna petición autenticada (M-TOK-05)', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  llavero.valor = A;
  const lectura = diferida<void>();
  llavero.pendienteLeer = lectura.p;
  const salud = diferida<void>();
  pc.saludPendiente = salud.p;
  const llamar = crearLlamada(cfg, pc.fetch);
  void proveedor.iniciar();
  expect(proveedor.estado().tipo).toBe('CARGANDO_CREDENCIAL');
  const r1 = await llamar('/v1/yo', { method: 'GET' }, false);
  expect(r1).toEqual({ tipo: 'INDETERMINADO', mensaje: MSG_SIN_CREDENCIAL });
  lectura.resolver();
  await asentar();
  expect(proveedor.estado().tipo).toBe('VALIDANDO_CREDENCIAL');
  const r2 = await llamar('/v1/yo', { method: 'GET' }, false);
  expect(r2.tipo).toBe('INDETERMINADO');
  expect(pc.peticiones.filter((p) => p.ruta !== '/v1/salud')).toEqual([]);
  salud.resolver();
  await asentar();
  expect(proveedor.estado().tipo).toBe('CONECTADA');
  const r3 = await llamar('/v1/yo', { method: 'GET' }, false);
  expect(r3.tipo).toBe('OK');
  expect(pc.peticiones.filter((p) => p.ruta === '/v1/yo')).toHaveLength(1);
  expect(pc.peticiones.at(-1)?.auth).toBe(`Bearer ${A}`);
});

test('sin credencial guardada: SIN_CREDENCIAL y ninguna petición, ni a /v1/salud', async () => {
  const { pc, proveedor } = montarProveedor();
  await proveedor.iniciar();
  expect(proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: null });
  expect(pc.peticiones).toEqual([]);
});

// ---------------------------------------------------------------- conectar
test('código correcto: se comprueba con /v1/salud y SOLO tras el 200 se guarda; el token se lee en cada petición', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  await proveedor.iniciar();
  const salud = diferida<void>();
  pc.saludPendiente = salud.p;
  const c = proveedor.conectar(`  ${A}  `);
  await asentar();
  expect(proveedor.estado().tipo).toBe('VALIDANDO_CREDENCIAL');
  expect(llavero.guardados).toEqual([]);
  salud.resolver();
  await c;
  expect(llavero.guardados).toEqual([A]);
  expect(proveedor.estado().tipo).toBe('CONECTADA');
  // copia `{ ...cfg }` (como revisión y compra): hereda la lectura en ejecución
  const copia = crearLlamada({ ...cfg, timeoutMs: 5000 }, pc.fetch);
  await copia('/v1/yo', { method: 'GET' }, false);
  expect(pc.peticiones.at(-1)?.auth).toBe(`Bearer ${A}`);
});

test('código incorrecto (401): nada guardado y aviso; la app no conecta (M-TOK-03)', async () => {
  const { llavero, proveedor } = montarProveedor();
  await proveedor.iniciar();
  await proveedor.conectar(B);
  expect(proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: 'CODIGO_INCORRECTO' });
  expect(llavero.guardados).toEqual([]);
  expect(proveedor.tokenParaPeticion()).toBeNull();
  expect(proveedor.credencialEnMemoria()).toBe(false);
});

test('conectar con el PC sin respuesta: nada guardado (NO_COMPROBADO)', async () => {
  const { pc, llavero, proveedor } = montarProveedor();
  await proveedor.iniciar();
  pc.saludCaida = true;
  await proveedor.conectar(A);
  expect(proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: 'NO_COMPROBADO' });
  expect(llavero.guardados).toEqual([]);
});

// ---------------------------------------------------------------- B · error de red
test('B · timeout de /v1/salud con credencial guardada: NO es inválida, se conserva y «Reintentar» conecta (M-TOK-06)', async () => {
  const { pc, llavero, proveedor } = montarProveedor();
  llavero.valor = A;
  pc.saludCaida = true;
  await proveedor.iniciar();
  expect(proveedor.estado()).toEqual({ tipo: 'ERROR_DE_CONEXION', motivo: 'SIN_RESPUESTA' });
  expect(llavero.borrados).toBe(0);
  expect(llavero.valor).toBe(A);
  expect(proveedor.tokenParaPeticion()).toBeNull();
  pc.saludCaida = false;
  await proveedor.reintentar();
  expect(proveedor.estado().tipo).toBe('CONECTADA');
  expect(llavero.lecturas).toBe(1);
});

test('5xx de /v1/salud tampoco es credencial inválida', async () => {
  const pc = new Pc();
  pc.fetch = (async () => ({ status: 503, ok: false, json: async () => ({}) })) as unknown as typeof fetch;
  const { llavero, proveedor } = montarProveedor(pc);
  llavero.valor = A;
  await proveedor.iniciar();
  expect(proveedor.estado()).toEqual({ tipo: 'ERROR_DE_CONEXION', motivo: 'SIN_RESPUESTA' });
  expect(llavero.borrados).toBe(0);
});

// ---------------------------------------------------------------- C · revocación con la app abierta
test('C · revocación en uso: el 401 avisa, borra la credencial y bloquea lo siguiente; el código nuevo recupera', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  llavero.valor = A;
  await proveedor.iniciar();
  const cliente = crearCliente(cfg, pc.fetch);
  expect((await cliente.yo()).tipo).toBe('OK');
  pc.validos = new Set([B]); // el PC rota el token
  const r = await cliente.yo();
  expect(r.tipo).toBe('INDETERMINADO');
  await asentar();
  expect(proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: 'CREDENCIAL_RECHAZADA' });
  expect(llavero.valor).toBeNull();
  const antes = pc.peticiones.length;
  expect((await cliente.yo()).tipo).toBe('INDETERMINADO');
  expect(pc.peticiones.length).toBe(antes); // no sale
  await proveedor.conectar(B);
  expect(proveedor.estado().tipo).toBe('CONECTADA');
  expect((await cliente.yo()).tipo).toBe('OK');
  expect(pc.peticiones.at(-1)?.auth).toBe(`Bearer ${B}`);
});

test('un 401 con un token ya sustituido no tumba la credencial vigente', async () => {
  const { llavero, proveedor } = montarProveedor();
  llavero.valor = A;
  await proveedor.iniciar();
  proveedor.noAutorizado('otro-token-antiguo');
  expect(proveedor.estado().tipo).toBe('CONECTADA');
});

// ---------------------------------------------------------------- D · COLA-AR
function montarCola(base: ReturnType<typeof montarProveedor>) {
  const reloj = new Reloj();
  const cola = new ColaAccionRapida(ejecutorDe(crearCliente(base.cfg, base.pc.fetch), BASE), new AlmacenMem(), reloj);
  return { reloj, cola };
}

test('D1 · credencial revocada antes del envío: no sale el pago (NO_ENVIADA), misma intención y un solo pago al reconectar', async () => {
  const base = montarProveedor();
  base.llavero.valor = A;
  await base.proveedor.iniciar();
  const { reloj, cola } = montarCola(base);
  await cola.restaurar();
  await asentar();
  cola.lanzar(pago());
  base.pc.validos = new Set([B]);
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(cola.get('cuota-2')?.estado).toBe('NO_ENVIADA');
  expect(cola.get('cuota-2')?.payload.intencion_id).toBe(INTENCION);
  expect(base.pc.pagosEnviados()).toHaveLength(0);
  expect(base.proveedor.estado().tipo).toBe('SIN_CREDENCIAL');
  // «Reintentar» sin credencial: sigue sin salir
  cola.reintentar('cuota-2');
  await reloj.avanzar(1000);
  expect(base.pc.pagosEnviados()).toHaveLength(0);
  expect(cola.get('cuota-2')?.estado).toBe('NO_ENVIADA');
  await base.proveedor.conectar(B);
  cola.reintentar('cuota-2');
  await reloj.avanzar(1000);
  expect(cola.get('cuota-2')?.estado).toBe('CONFIRMADA');
  expect(base.pc.pagos).toBe(1);
  expect(base.pc.pagosEnviados().map((p) => p.cuerpo.intencion_id)).toEqual([INTENCION]);
  expect(base.pc.pagosEnviados().every((p) => p.auth === `Bearer ${B}`)).toBe(true);
});

test('D2 · 401 en el propio pago: RESULTADO_DESCONOCIDO (nunca RECHAZADA), nada sale sin credencial y al reconectar se confirma con la MISMA intención (M-TOK-09)', async () => {
  const base = montarProveedor();
  base.llavero.valor = A;
  await base.proveedor.iniciar();
  const { reloj, cola } = montarCola(base);
  await cola.restaurar();
  await asentar();
  cola.lanzar(pago());
  base.pc.revocarTrasYo = true;
  base.pc.validos.add(B);
  await reloj.avanzar(PLAZO_DESHACER_MS);
  expect(base.pc.pagosEnviados()).toHaveLength(1); // salió y el PC lo rechazó con 401 (nada escrito)
  expect(base.pc.pagos).toBe(0);
  expect(cola.get('cuota-2')?.estado).toBe('RESULTADO_DESCONOCIDO');
  expect(base.proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: 'CREDENCIAL_RECHAZADA' });
  await reloj.avanzar(120000); // reconciliaciones sin credencial: no sale nada
  expect(base.pc.pagosEnviados()).toHaveLength(1);
  expect(cola.get('cuota-2')?.estado).toBe('RESULTADO_DESCONOCIDO');
  await base.proveedor.conectar(B);
  await reloj.avanzar(60000);
  expect(cola.get('cuota-2')?.estado).toBe('CONFIRMADA');
  expect(base.pc.pagos).toBe(1);
  const intenciones = new Set(base.pc.pagosEnviados().map((p) => p.cuerpo.intencion_id));
  expect([...intenciones]).toEqual([INTENCION]);
  expect(cola.intenciones()).toHaveLength(1);
});

// ---------------------------------------------------------------- E · aislamiento en mensajes
test('E · el token no aparece en los mensajes de la llamada ni en los estados', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  llavero.valor = A;
  await proveedor.iniciar();
  pc.validos = new Set();
  const r = await crearCliente(cfg, pc.fetch).yo();
  expect(JSON.stringify(r)).not.toContain(A);
  expect(JSON.stringify(proveedor.estado())).not.toContain(A);
});

// ---------------------------------------------------------------- F · desconectar
test('F · «Desconectar» borra memoria y llavero; ninguna petición sale después (M-TOK-08)', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  llavero.valor = A;
  await proveedor.iniciar();
  const llamar = crearLlamada(cfg, pc.fetch);
  const d = proveedor.desconectar();
  expect(proveedor.credencialEnMemoria()).toBe(false);
  expect(proveedor.tokenParaPeticion()).toBeNull();
  await d;
  expect(llavero.valor).toBeNull();
  expect(llavero.borrados).toBe(1);
  expect(proveedor.estado()).toEqual({ tipo: 'SIN_CREDENCIAL', motivo: 'DESCONECTADO' });
  const antes = pc.peticiones.length;
  expect((await llamar('/v1/yo', { method: 'GET' }, false)).tipo).toBe('INDETERMINADO');
  expect(pc.peticiones.length).toBe(antes);
});

test('F · desconectar mientras se valida: el 200 tardío no reconecta ni guarda', async () => {
  const { pc, llavero, proveedor } = montarProveedor();
  await proveedor.iniciar();
  const salud = diferida<void>();
  pc.saludPendiente = salud.p;
  const c = proveedor.conectar(A);
  await asentar();
  await proveedor.desconectar();
  salud.resolver();
  await c;
  expect(proveedor.estado().tipo).toBe('SIN_CREDENCIAL');
  expect(llavero.guardados).toEqual([]);
  expect(proveedor.credencialEnMemoria()).toBe(false);
});

// ---------------------------------------------------------------- transporte (AJ-TOK-05, M-TOK-10)
test('transporte: http solo hacia red privada; https a cualquier host', () => {
  for (const ok of ['http://127.0.0.1:8027', 'http://localhost:8000', 'http://10.0.0.5:8027', 'http://172.16.0.1', 'http://172.31.255.255:1',
    'http://192.168.1.50:8027', 'https://api.ejemplo.com', 'https://8.8.8.8:443']) expect(transportePermitido(ok)).toBe(true);
  for (const no of ['http://api.ejemplo.com', 'http://8.8.8.8:8027', 'http://172.32.0.1', 'http://192.169.1.1', 'http://11.0.0.1',
    'http://192.168.1.50.nip.io', 'ftp://192.168.1.50', 'http://usuario@192.168.1.5', '', 'no-es-url']) expect(transportePermitido(no)).toBe(false);
  expect(hostPrivado('10.300.0.1')).toBe(false);
});

test('transporte: con un perfil remoto en http el proveedor no lee, no valida ni envía nada', async () => {
  const pc = new Pc();
  const { llavero, proveedor } = montarProveedor(pc, new Llavero(), 'http://api.ejemplo.com');
  llavero.valor = A;
  await proveedor.iniciar();
  expect(proveedor.estado()).toEqual({ tipo: 'ERROR_DE_CONEXION', motivo: 'TRANSPORTE_NO_SEGURO' });
  await proveedor.conectar(A);
  await proveedor.reintentar();
  expect(pc.peticiones).toEqual([]);
  expect(proveedor.tokenParaPeticion()).toBeNull();
});

// ---------------------------------------------------------------- pantallas
const envolver = (n: React.ReactNode) => (
  <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
    <ProveedorTema>{n}</ProveedorTema>
  </SafeAreaProvider>
);

test('pantalla «Conectar con tu PC»: campo oculto, botón deshabilitado sin código y avisos por motivo', () => {
  const conectar = jest.fn();
  const v = render(envolver(<ConectarScreen estado={{ tipo: 'SIN_CREDENCIAL', motivo: 'CODIGO_INCORRECTO' }} onConectar={conectar} onReintentar={jest.fn()} onDesconectar={jest.fn()} />));
  expect(screen.getByText('Conectar con tu PC')).toBeTruthy();
  expect(screen.getByText('El código no es correcto. No se ha guardado nada.')).toBeTruthy();
  const campo = screen.getByTestId('conectar-codigo');
  expect(campo.props.secureTextEntry).toBe(true);
  expect(campo.props.autoCorrect).toBe(false);
  fireEvent.press(screen.getByTestId('conectar-boton'));
  expect(conectar).not.toHaveBeenCalled();
  fireEvent.changeText(campo, A);
  fireEvent.press(screen.getByTestId('conectar-boton'));
  expect(conectar).toHaveBeenCalledWith(A);
  v.rerender(envolver(<ConectarScreen estado={{ tipo: 'ERROR_DE_CONEXION', motivo: 'SIN_RESPUESTA' }} onConectar={conectar} onReintentar={jest.fn()} onDesconectar={jest.fn()} />));
  expect(screen.getByTestId('conectar-reintentar')).toBeTruthy();
  expect(screen.getByTestId('conectar-desconectar')).toBeTruthy();
  v.rerender(envolver(<ConectarScreen estado={{ tipo: 'ERROR_DE_CONEXION', motivo: 'TRANSPORTE_NO_SEGURO' }} onConectar={conectar} onReintentar={jest.fn()} onDesconectar={jest.fn()} />));
  expect(screen.queryByTestId('conectar-reintentar')).toBeNull();
  expect(screen.queryByText(A)).toBeNull();
});

test('Ajustes: «Desconectar este iPhone» pide confirmación; sin `onDesconectar` no aparece', () => {
  const desconectar = jest.fn();
  const v = render(envolver(<AjustesScreen onAtras={jest.fn()} onCategorias={jest.fn()} onPreferencias={jest.fn()} onDesconectar={desconectar} />));
  fireEvent.press(screen.getByTestId('ajustes-desconectar'));
  expect(desconectar).not.toHaveBeenCalled();
  fireEvent.press(screen.getByTestId('ajustes-desconectar-cancelar'));
  expect(screen.queryByTestId('ajustes-desconectar-confirmacion')).toBeNull();
  fireEvent.press(screen.getByTestId('ajustes-desconectar'));
  fireEvent.press(screen.getByTestId('ajustes-desconectar-si'));
  expect(desconectar).toHaveBeenCalledTimes(1);
  v.rerender(envolver(<AjustesScreen onAtras={jest.fn()} onCategorias={jest.fn()} onPreferencias={jest.fn()} />));
  expect(screen.queryByTestId('ajustes-desconectar')).toBeNull();
});

test('puerta de la app: «Conectar» hasta CONECTADA; conectar monta la app y un 401 vuelve a «Conectar»', async () => {
  const { pc, llavero, proveedor, cfg } = montarProveedor();
  const cliente = {} as ClienteApi;
  const { Text } = jest.requireActual('react-native');
  render(envolver(
    <AppConCredencial proveedor={proveedor} cliente={cliente} nuevoId={() => 'x'} ahora={() => new Date('2026-11-23T10:00:00Z')}
      contenido={(desc) => <Text testID="app-montada" onPress={desc}>app</Text>} />,
  ));
  await waitFor(() => expect(screen.getByTestId('pantalla-conectar')).toBeTruthy());
  expect(screen.queryByTestId('app-montada')).toBeNull();
  fireEvent.changeText(screen.getByTestId('conectar-codigo'), A);
  fireEvent.press(screen.getByTestId('conectar-boton'));
  await waitFor(() => expect(screen.getByTestId('app-montada')).toBeTruthy());
  pc.validos = new Set();
  await crearLlamada(cfg, pc.fetch)('/v1/yo', { method: 'GET' }, false);
  await waitFor(() => expect(screen.getByText(/Tu PC ya no acepta el código/)).toBeTruthy());
  expect(screen.queryByTestId('app-montada')).toBeNull();
  // reconectar y desconectar desde la app
  pc.validos = new Set([B]);
  fireEvent.changeText(screen.getByTestId('conectar-codigo'), B);
  fireEvent.press(screen.getByTestId('conectar-boton'));
  await waitFor(() => expect(screen.getByTestId('app-montada')).toBeTruthy());
  fireEvent.press(screen.getByTestId('app-montada'));
  await waitFor(() => expect(screen.getByText('Este iPhone se ha desconectado de tu PC.')).toBeTruthy());
  expect(llavero.valor).toBeNull();
});
