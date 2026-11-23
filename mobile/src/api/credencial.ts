// ============================================================
// GAPTO MOBILE 2027
// Fichero: credencial.ts
// Ruta: mobile/src/api/credencial.ts
// Descripción: Proveedor de la credencial de desarrollo de BETA_LOCAL (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.1; dictamen AJ-TOK-01/02/06, M-TOK-05/06/08). El código de conexión con el PC (el `GAPTO_DEV_TOKEN` del backend) ya NO viaja en el bundle: lo introduce el usuario una vez, se comprueba contra `GET /v1/salud` y SOLO tras un 200 se guarda en el llavero del iPhone (almacén inyectado: `almacenCredencial.ts`, expo-secure-store). Vive en el almacén y en la memoria de este proveedor; nunca en AsyncStorage, ficheros, configuración Expo, `EXPO_PUBLIC_*` ni logs, y este módulo no escribe nada en consola.
//   Estados (AJ-TOK-01): CARGANDO_CREDENCIAL (lectura inicial del llavero en curso), SIN_CREDENCIAL (con su motivo), VALIDANDO_CREDENCIAL, CONECTADA y ERROR_DE_CONEXION. `tokenParaPeticion()` solo da el token en CONECTADA: mientras se lee el llavero o se valida, ninguna petición autenticada sale (la bloquea `crearLlamada`).
//   Clasificación de `/v1/salud`: 200 → válida; 401 → inválida; cualquier otra cosa (timeout, red, 5xx, otro 4xx) → SIN_RESPUESTA, que NUNCA borra una credencial guardada (se puede reintentar) y nunca guarda una nueva.
//   Un 401 de cualquier petición con el token vigente (`noAutorizado`) borra la credencial (revocada en el PC) y pasa a SIN_CREDENCIAL con su aviso; las acciones financieras pendientes las conserva COLA-AR con su misma intención (no se tocan aquí).
//   «Desconectar este iPhone» borra primero la memoria y después el llavero. Cada operación asíncrona lleva su generación: un resultado que llega después de desconectar o de otra operación se descarta.
//   NO ES AUTENTICACIÓN REAL: sin usuarios, sesiones, caducidad ni revocación por dispositivo (F10-01, AJ-TOK-09).
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

import { transportePermitido } from './transporte';

export type MotivoSinCredencial =
  | 'CODIGO_INCORRECTO'
  | 'CREDENCIAL_RECHAZADA'
  | 'NO_COMPROBADO'
  | 'DESCONECTADO'
  | 'LLAVERO_NO_DISPONIBLE';

export type MotivoErrorConexion = 'SIN_RESPUESTA' | 'TRANSPORTE_NO_SEGURO' | 'LLAVERO_NO_DISPONIBLE';

export type EstadoCredencial =
  | { tipo: 'CARGANDO_CREDENCIAL' }
  | { tipo: 'SIN_CREDENCIAL'; motivo: MotivoSinCredencial | null }
  | { tipo: 'VALIDANDO_CREDENCIAL' }
  | { tipo: 'CONECTADA' }
  | { tipo: 'ERROR_DE_CONEXION'; motivo: MotivoErrorConexion };

/** Almacén seguro de la credencial (en la app: Keychain de iOS por expo-secure-store). */
export interface AlmacenCredencial {
  leer(): Promise<string | null>;
  guardar(valor: string): Promise<void>;
  borrar(): Promise<void>;
}

export type ResultadoComprobacion = 'VALIDA' | 'INVALIDA' | 'SIN_RESPUESTA';

/** Tiempo máximo de la comprobación contra `/v1/salud`. */
export const TIMEOUT_SALUD_MS = 10000;

/** `GET /v1/salud` con el código: 200 válida, 401 inválida; todo lo demás, sin respuesta (indeterminado). */
export async function comprobarCredencial(
  baseUrl: string,
  token: string,
  fetchImpl: typeof fetch,
  timeoutMs: number = TIMEOUT_SALUD_MS,
): Promise<ResultadoComprobacion> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetchImpl(`${baseUrl}/v1/salud`, {
      method: 'GET',
      signal: ctrl.signal,
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.status === 200) return 'VALIDA';
    if (r.status === 401) return 'INVALIDA';
    return 'SIN_RESPUESTA';
  } catch {
    return 'SIN_RESPUESTA';
  } finally {
    clearTimeout(t);
  }
}

export interface OpcionesProveedor {
  baseUrl: string;
  almacen: AlmacenCredencial;
  fetchImpl: typeof fetch;
  timeoutMs?: number;
}

export class ProveedorCredencial {
  private actual: EstadoCredencial = { tipo: 'CARGANDO_CREDENCIAL' };
  private memoria: string | null = null;
  private generacion = 0;
  private iniciado: Promise<void> | null = null;
  private readonly oyentes = new Set<() => void>();

  constructor(private readonly o: OpcionesProveedor) {}

  estado(): EstadoCredencial {
    return this.actual;
  }

  suscribir(oyente: () => void): () => void {
    this.oyentes.add(oyente);
    return () => {
      this.oyentes.delete(oyente);
    };
  }

  /** true si queda alguna credencial en la memoria del proveedor (comprobación de «Desconectar», M-TOK-08). */
  credencialEnMemoria(): boolean {
    return this.memoria !== null;
  }

  /** Token para una petición autenticada: SOLO con la credencial validada (CONECTADA). */
  tokenParaPeticion(): string | null {
    return this.actual.tipo === 'CONECTADA' ? this.memoria : null;
  }

  /** Lectura inicial del llavero (una sola vez) y validación de lo guardado. */
  iniciar(): Promise<void> {
    if (!this.iniciado) this.iniciado = this.cargar();
    return this.iniciado;
  }

  private async cargar(): Promise<void> {
    const g = ++this.generacion;
    this.poner({ tipo: 'CARGANDO_CREDENCIAL' });
    if (!transportePermitido(this.o.baseUrl)) return this.poner({ tipo: 'ERROR_DE_CONEXION', motivo: 'TRANSPORTE_NO_SEGURO' });
    let guardada: string | null;
    try {
      guardada = await this.o.almacen.leer();
    } catch {
      if (g === this.generacion) this.poner({ tipo: 'ERROR_DE_CONEXION', motivo: 'LLAVERO_NO_DISPONIBLE' });
      return;
    }
    if (g !== this.generacion) return;
    if (!guardada) return this.poner({ tipo: 'SIN_CREDENCIAL', motivo: null });
    this.memoria = guardada;
    return this.validarGuardada(g);
  }

  private async validarGuardada(g: number): Promise<void> {
    const token = this.memoria;
    if (!token) return this.poner({ tipo: 'SIN_CREDENCIAL', motivo: null });
    this.poner({ tipo: 'VALIDANDO_CREDENCIAL' });
    const r = await comprobarCredencial(this.o.baseUrl, token, this.o.fetchImpl, this.o.timeoutMs);
    if (g !== this.generacion) return;
    if (r === 'VALIDA') return this.poner({ tipo: 'CONECTADA' });
    if (r === 'INVALIDA') return this.olvidar('CREDENCIAL_RECHAZADA');
    // Sin respuesta: la credencial guardada se CONSERVA (M-TOK-06); se puede reintentar.
    this.poner({ tipo: 'ERROR_DE_CONEXION', motivo: 'SIN_RESPUESTA' });
  }

  /** «Reintentar» desde ERROR_DE_CONEXION: vuelve a validar lo guardado (o a leer el llavero). */
  async reintentar(): Promise<void> {
    if (this.actual.tipo !== 'ERROR_DE_CONEXION') return;
    if (this.actual.motivo === 'TRANSPORTE_NO_SEGURO') return;
    if (this.actual.motivo === 'LLAVERO_NO_DISPONIBLE' || !this.memoria) {
      this.iniciado = this.cargar();
      return this.iniciado;
    }
    return this.validarGuardada(++this.generacion);
  }

  /** «Conectar»: comprueba el código contra el PC y SOLO tras un 200 lo guarda en el llavero. */
  async conectar(codigo: string): Promise<void> {
    const valor = codigo.trim();
    if (!valor) return;
    if (this.actual.tipo === 'VALIDANDO_CREDENCIAL' || this.actual.tipo === 'CARGANDO_CREDENCIAL') return;
    if (!transportePermitido(this.o.baseUrl)) return this.poner({ tipo: 'ERROR_DE_CONEXION', motivo: 'TRANSPORTE_NO_SEGURO' });
    const g = ++this.generacion;
    this.poner({ tipo: 'VALIDANDO_CREDENCIAL' });
    const r = await comprobarCredencial(this.o.baseUrl, valor, this.o.fetchImpl, this.o.timeoutMs);
    if (g !== this.generacion) return;
    if (r === 'INVALIDA') return this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'CODIGO_INCORRECTO' });
    if (r === 'SIN_RESPUESTA') return this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'NO_COMPROBADO' });
    try {
      await this.o.almacen.guardar(valor);
    } catch {
      if (g === this.generacion) this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'LLAVERO_NO_DISPONIBLE' });
      return;
    }
    if (g !== this.generacion) return;
    this.memoria = valor;
    this.poner({ tipo: 'CONECTADA' });
  }

  /** «Desconectar este iPhone»: memoria primero, después el llavero. */
  async desconectar(): Promise<void> {
    ++this.generacion;
    this.memoria = null;
    this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'DESCONECTADO' });
    try {
      await this.o.almacen.borrar();
    } catch {
      this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'LLAVERO_NO_DISPONIBLE' });
    }
  }

  /** Un 401 con el token vigente: la credencial ya no vale en el PC (revocada o rotada). */
  noAutorizado(token: string): void {
    if (this.actual.tipo !== 'CONECTADA' || token !== this.memoria) return;
    ++this.generacion;
    void this.olvidar('CREDENCIAL_RECHAZADA');
  }

  private async olvidar(motivo: MotivoSinCredencial): Promise<void> {
    this.memoria = null;
    this.poner({ tipo: 'SIN_CREDENCIAL', motivo });
    try {
      await this.o.almacen.borrar();
    } catch {
      // El código rechazado ya no sirve en el PC; si no se pudo borrar, la próxima validación lo vuelve a rechazar.
    }
  }

  private poner(e: EstadoCredencial): void {
    this.actual = e;
    for (const f of [...this.oyentes]) f();
  }
}
