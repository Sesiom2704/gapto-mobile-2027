// ============================================================
// GAPTO MOBILE 2027
// Fichero: cliente.ts
// Ruta: mobile/src/api/cliente.ts
// Descripción: Cliente HTTP del adaptador F05-00-B. Clasifica cada respuesta en resultados de dominio del cliente: OK, RECHAZADO (definitivo, no persistido) o INDETERMINADO (timeout, red, 5xx: puede haberse confirmado; se reintenta la MISMA intención). Nunca expone texto técnico.
// v0.2.0 (F05-D003): cuentas-pago por fecha del pago con propuesta de financiación; resultado con la financiación sellada.
// v0.3.0 (F05-01 S6-WIRE+UI (este mandato)): lectura del árbol y del uso de una categoría y comandos de Ajustes › Categorías (alta, icono, renombrar, mover, desactivar, reactivar, ámbito y reordenar), todos con la clasificación OK / RECHAZADO(codigo) / INDETERMINADO vigente. La reordenación usa SOLO la ruta atómica /v1/categorias/reordenar (F05 §26.3): el cliente no invoca el comando por nodo. El resultado del registro informa el estado categorial.
// v0.4.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): un RECHAZADO conserva el `detalle` del servidor cuando lo trae (CAMBIO_AMBITO_REQUIERE_CONFIRMACION devuelve el uso vigente `efectos_activos`, que la UI vuelve a mostrar y confirmar).
// v0.5.0 (F05-01 S7-MAG UI; F05-D020): catálogo GET /v1/magnitudes y los comandos de magnitudes (asociar EXISTENTE/NUEVA, obligatoriedad, retirar, reordenar el conjunto COMPLETO de asociaciones por la ruta atómica de la categoría, renombrar, deshabilitar con confirmación de impacto y rehabilitar), con la clasificación OK / RECHAZADO(codigo, detalle) / INDETERMINADO vigente. `detalle` tipado para MAGNITUD_NOMBRE_DUPLICADO y MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION.
// v0.6.0 (F05-02 B2; F05-D026 §41.3, F05-D027 §42.7): preferencias de registro. Lectura de la propuesta por campo (GET /v1/preferencias/propuesta, por fecha y categoría o «Sin categoría») y de la lista (GET /v1/preferencias); alta y edición (POST, clasificación 'CAMBIO'). Editar envía SIEMPRE el estado completo (E05): el tipo no admite un parche parcial. Sin imports nuevos.
// v0.7.0 (F05-02 B3; lámina SET-PREF S04, A2 del mandato B3+B4): desactivar y reactivar una preferencia (`desactivarPreferencia(id, row_version)` y `reactivarPreferencia(id, row_version)`) sobre las rutas existentes de B1, con la clasificación 'CAMBIO' vigente. Sin cambios en rutas ni DTO.
// v0.8.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E2/E3): GET /v1/preferencias devuelve también `tipos` (ids de GASTO e INGRESO) para enviar SIEMPRE el tipo de la preferencia (se retira la preferencia sin tipo). Sin rutas nuevas.
// v0.9.0 (F05-03/F05-04 J2 §1.9/§2): cuentas elegibles por operación, terceros, contextos, plantillas y acciones rápidas, propuesta del registro con la capa plantilla, registro de ingreso cobrado y entre cuentas, y onboarding de categorías. Escrituras de maestros con clasificación 'CAMBIO'; registros con la de escritura (indeterminado = reintentar el MISMO UUID).
// Versión: 0.9.0
// ============================================================

import type { Ambito, CategoriaNodo } from '../domain/categoria';
import type { PayloadGastoPagado } from '../domain/intencion';
import type { MagnitudCatalogo } from '../domain/magnitud';

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

// ------------------------------------------------------------------ S7-MAG (F05-D020)
export interface FichaMagnitud {
  id: string;
  nombre: string;
  unidad_default: string;
  precision_decimales: number;
  enabled: boolean;
  row_version: number;
}

export interface AsociacionMagnitud {
  asociacion_id: string;
  magnitud_id: string;
  obligatoria: boolean;
  orden: number;
}

export interface ResultadoAsociacionMagnitud {
  categoria_id: string;
  asociacion: AsociacionMagnitud;
  magnitud: FichaMagnitud;
  idempotente: boolean;
  modificadas: string[];
}

export interface ResultadoAsociacionesMagnitud {
  categoria_id: string;
  asociaciones: AsociacionMagnitud[];
  idempotente: boolean;
  modificadas: string[];
}

export interface ResultadoComandoMagnitud {
  magnitud: FichaMagnitud;
  idempotente: boolean;
  modificadas: string[];
}

export interface NuevaMagnitudPayload {
  magnitud_id: string;
  nombre: string;
  unidad_default: string;
  precision_decimales: number;
}

export type AsociarMagnitudPayload =
  | { origen: 'EXISTENTE'; magnitud_id: string; obligatoria: boolean }
  | { origen: 'NUEVA'; magnitud: NuevaMagnitudPayload; obligatoria: boolean };

/** `detalle` de MAGNITUD_NOMBRE_DUPLICADO (solo si la existente es del owner; puede faltar: colisión física residual). */
export interface DetalleNombreDuplicado {
  magnitud_id: string;
  enabled: boolean;
}

/** `detalle` de MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION: categorías habilitadas con asociación obligatoria, bajo lock. */
export interface DetalleImpacto {
  categorias_no_capturables: { categoria_id: string; nombre: string; obligatoria: boolean }[];
}

export function detalleNombreDuplicado(r: { detalle?: Record<string, unknown> }): DetalleNombreDuplicado | null {
  const d = r.detalle;
  return d && typeof d.magnitud_id === 'string' && typeof d.enabled === 'boolean' ? { magnitud_id: d.magnitud_id, enabled: d.enabled } : null;
}

export function detalleImpacto(r: { detalle?: Record<string, unknown> }): { id: string; nombre: string; obligatoria: boolean }[] | null {
  const lista = (r.detalle as Partial<DetalleImpacto> | undefined)?.categorias_no_capturables;
  return Array.isArray(lista) ? lista.map((c) => ({ id: c.categoria_id, nombre: c.nombre, obligatoria: c.obligatoria })) : null;
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

// ------------------------------------------------------------------ F05-02 B2 (preferencias de registro)
export interface OrigenPropuesta {
  capa: 'PREFERENCIA' | 'DEFAULT_GENERAL';
  preferencia_id: string | null;
}

/** Propuesta del resolver por campo; null = sin propuesta (nunca se inventa). */
export interface PropuestaRegistro {
  cuenta: { valor: string; origen: OrigenPropuesta } | null;
  presupuestable: { valor: boolean; origen: OrigenPropuesta } | null;
}

/** Contenido COMPLETO de una preferencia (alta y edición: E05, sin parches). */
export interface ContenidoPreferencia {
  tipo_hecho_id: string | null;
  categoria_id: string | null;
  tercero_id: string | null;
  entidad_id: string | null;
  cuenta_default_id: string | null;
  presupuestable_default: boolean | null;
  prioridad: number;
}

export interface Preferencia extends ContenidoPreferencia {
  id: string;
  enabled: boolean;
  row_version: number;
  cuenta_disponible_hoy?: boolean | null;
}

/** Ids de los tipos de registro con preferencias (E3: toda preferencia lleva tipo). */
export interface TiposRegistro {
  GASTO: string;
  INGRESO: string;
}

export interface ListaPreferencias {
  preferencias: Preferencia[];
  tipos: TiposRegistro;
}

export interface ResultadoComandoPreferencia {
  preferencia: Preferencia;
  idempotente: boolean;
  modificadas: string[];
}

// ------------------------------------------------------------------ F05-03/F05-04 J2 (terceros, contextos, plantillas, registro por tipo)
export type NaturalezaTercero = 'PERSONA' | 'EMPRESA' | 'ORGANISMO' | 'OTRO';
export type TipoContexto = 'VIAJE' | 'REFORMA' | 'EVENTO' | 'SOCIAL' | 'PROYECTO' | 'OTRO';
export type OperacionCuenta = 'GASTO' | 'INGRESO' | 'TRANSFERENCIA_ORIGEN' | 'TRANSFERENCIA_DESTINO';

export interface Tercero {
  id: string;
  nombre: string;
  naturaleza: NaturalezaTercero | null;
  enabled: boolean;
  row_version: number;
  usos?: number;
}

export interface Contexto {
  id: string;
  nombre: string;
  tipo_contexto: TipoContexto;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  enabled: boolean;
  row_version: number;
}

export interface ResultadoComandoTercero {
  tercero: Tercero;
  idempotente: boolean;
  modificadas: string[];
}

export interface ResultadoComandoContexto {
  contexto: Contexto;
  idempotente: boolean;
  modificadas: string[];
}

export interface ContenidoPlantilla {
  nombre: string;
  tipo_hecho_id: string;
  categoria_id: string | null;
  tercero_id: string | null;
  entidad_id: string | null;
  cuenta_default_id: string | null;
  presupuestable_default: boolean | null;
}

export interface AvisoCampo {
  campo: string;
  motivo: string;
}

export interface Plantilla extends ContenidoPlantilla {
  id: string;
  enabled: boolean;
  row_version: number;
  tipo?: 'GASTO' | 'INGRESO' | null;
  avisos?: AvisoCampo[];
}

export interface AccionRapida {
  id: string;
  nombre: string;
  plantilla_registro_id: string;
  orden: number;
  icono_key: string | null;
  enabled: boolean;
  row_version: number;
}

export interface ListaPlantillas {
  plantillas: Plantilla[];
  acciones: AccionRapida[];
}

export interface ResultadoComandoPlantilla {
  plantilla: Plantilla;
  idempotente: boolean;
  modificadas: string[];
}

export interface ResultadoComandoAccion {
  accion: AccionRapida;
  idempotente: boolean;
  modificadas: string[];
}

export interface OrigenCampoRegistro {
  capa: 'PLANTILLA' | 'PREFERENCIA' | 'DEFAULT_GENERAL';
  plantilla_id: string | null;
  preferencia_id: string | null;
}

/** Propuesta del registro con la capa plantilla (GET /v1/registro/propuesta). */
export interface PropuestaRegistroTipo {
  tipo: 'GASTO' | 'INGRESO';
  campos: {
    categoria: { valor: string; origen: OrigenCampoRegistro } | null;
    tercero: { valor: string; origen: OrigenCampoRegistro } | null;
    contexto: { valor: string; origen: OrigenCampoRegistro } | null;
    cuenta: { valor: string; origen: OrigenCampoRegistro } | null;
    presupuestable: { valor: boolean; origen: OrigenCampoRegistro } | null;
  };
  avisos: AvisoCampo[];
}

export interface ConsultaPropuestaRegistro {
  tipo: 'GASTO' | 'INGRESO';
  fecha: string;
  plantillaId?: string | null;
  categoriaId?: string | null;
  sinCategoria?: boolean;
  terceroId?: string | null;
  sinTercero?: boolean;
}

export interface CuentaElegible {
  cuenta_id: string;
  nombre: string;
  moneda: string;
}

export interface PayloadIngresoCobrado {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  cuenta_id: string;
  presupuestable: boolean;
  atribucion: 'SOLO_MIO' | 'SIN_INDICAR';
  categoria: PayloadGastoPagado['categoria'];
  tercero_id?: string | null;
  contexto_id?: string | null;
  nota?: string | null;
}

export interface PayloadTransferencia {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  cuenta_origen_id: string;
  cuenta_destino_id: string;
  nota?: string | null;
}

export interface ResultadoRegistroTipo {
  intencion_id: string;
  hecho_id: string;
  idempotente: boolean;
  tipo: 'GASTO' | 'INGRESO' | 'TRANSFERENCIA';
  importe: string;
  moneda: string;
  estado_atribucion: 'COMPLETA' | 'NO_DISPONIBLE' | null;
  estado_categorial: 'CATEGORIA' | 'SIN_CATEGORIA' | null;
}

export interface NodoSugerido {
  ruta: string;
  nombre: string;
  nivel: number;
  padre: string | null;
  orden: number;
  ambito: Ambito;
  presupuestable_default: boolean;
  icon_key: string;
}

export type Respuesta<T> =
  | { tipo: 'OK'; datos: T }
  | { tipo: 'RECHAZADO'; codigo: string; mensaje: string; detalle?: Record<string, unknown> }
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
  catalogoMagnitudes(): Promise<Respuesta<{ magnitudes: MagnitudCatalogo[] }>>;
  asociarMagnitud(categoriaId: string, c: AsociarMagnitudPayload): Promise<Respuesta<ResultadoAsociacionMagnitud>>;
  obligatoriaMagnitud(
    categoriaId: string,
    asociacionId: string,
    c: { magnitud_id: string; obligatoria_actual: boolean; obligatoria: boolean },
  ): Promise<Respuesta<ResultadoAsociacionMagnitud>>;
  retirarMagnitud(
    categoriaId: string,
    asociacionId: string,
    c: { magnitud_id: string; obligatoria_actual: boolean },
  ): Promise<Respuesta<ResultadoAsociacionesMagnitud>>;
  reordenarMagnitudes(
    categoriaId: string,
    c: { asociaciones: { asociacion_id: string; magnitud_id: string; orden: number; obligatoria: boolean }[] },
  ): Promise<Respuesta<ResultadoAsociacionesMagnitud>>;
  renombrarMagnitud(id: string, c: { nombre: string; row_version: number }): Promise<Respuesta<ResultadoComandoMagnitud>>;
  deshabilitarMagnitud(
    id: string,
    c: { row_version: number; confirmacion_impacto: string[] | null },
  ): Promise<Respuesta<ResultadoComandoMagnitud>>;
  rehabilitarMagnitud(id: string, c: { row_version: number }): Promise<Respuesta<ResultadoComandoMagnitud>>;
  propuestaPreferencias(fecha: string, categoriaId: string | null): Promise<Respuesta<PropuestaRegistro>>;
  listarPreferencias(): Promise<Respuesta<ListaPreferencias>>;
  altaPreferencia(c: { id: string } & ContenidoPreferencia): Promise<Respuesta<ResultadoComandoPreferencia>>;
  editarPreferencia(id: string, c: { row_version: number } & ContenidoPreferencia): Promise<Respuesta<ResultadoComandoPreferencia>>;
  desactivarPreferencia(id: string, row_version: number): Promise<Respuesta<ResultadoComandoPreferencia>>;
  reactivarPreferencia(id: string, row_version: number): Promise<Respuesta<ResultadoComandoPreferencia>>;
  // F05-03/F05-04 J2
  cuentasElegibles(operacion: OperacionCuenta, fecha: string): Promise<Respuesta<{ operacion: OperacionCuenta; cuentas: CuentaElegible[] }>>;
  listarTerceros(): Promise<Respuesta<{ terceros: Tercero[] }>>;
  candidatosTercero(nombre: string): Promise<Respuesta<{ terceros: Tercero[] }>>;
  altaTercero(c: { id: string; nombre: string; naturaleza: NaturalezaTercero | null }): Promise<Respuesta<ResultadoComandoTercero>>;
  editarTercero(id: string, c: { row_version: number; nombre: string; naturaleza: NaturalezaTercero | null }): Promise<Respuesta<ResultadoComandoTercero>>;
  desactivarTercero(id: string, row_version: number): Promise<Respuesta<ResultadoComandoTercero>>;
  reactivarTercero(id: string, row_version: number): Promise<Respuesta<ResultadoComandoTercero>>;
  listarContextos(): Promise<Respuesta<{ contextos: Contexto[] }>>;
  altaContexto(c: { id: string; nombre: string; tipo_contexto: TipoContexto; fecha_inicio: string | null; fecha_fin: string | null }): Promise<Respuesta<ResultadoComandoContexto>>;
  editarContexto(id: string, c: { row_version: number; nombre: string; tipo_contexto: TipoContexto; fecha_inicio: string | null; fecha_fin: string | null }): Promise<Respuesta<ResultadoComandoContexto>>;
  desactivarContexto(id: string, row_version: number): Promise<Respuesta<ResultadoComandoContexto>>;
  reactivarContexto(id: string, row_version: number): Promise<Respuesta<ResultadoComandoContexto>>;
  listarPlantillas(): Promise<Respuesta<ListaPlantillas>>;
  altaPlantilla(c: { id: string } & ContenidoPlantilla): Promise<Respuesta<ResultadoComandoPlantilla>>;
  editarPlantilla(id: string, c: { row_version: number } & ContenidoPlantilla): Promise<Respuesta<ResultadoComandoPlantilla>>;
  desactivarPlantilla(id: string, row_version: number): Promise<Respuesta<ResultadoComandoPlantilla>>;
  reactivarPlantilla(id: string, row_version: number): Promise<Respuesta<ResultadoComandoPlantilla>>;
  altaAccion(c: { id: string; plantilla_registro_id: string; nombre: string; icono_key: string | null }): Promise<Respuesta<ResultadoComandoAccion>>;
  editarAccion(id: string, c: { row_version: number; nombre: string; icono_key: string | null }): Promise<Respuesta<ResultadoComandoAccion>>;
  desactivarAccion(id: string, row_version: number): Promise<Respuesta<ResultadoComandoAccion>>;
  reordenarAcciones(acciones: { id: string; row_version: number }[]): Promise<Respuesta<{ acciones: AccionRapida[]; idempotente: boolean; modificadas: string[] }>>;
  propuestaRegistro(q: ConsultaPropuestaRegistro): Promise<Respuesta<PropuestaRegistroTipo>>;
  registrarIngresoCobrado(p: PayloadIngresoCobrado): Promise<Respuesta<ResultadoRegistroTipo>>;
  registrarTransferencia(p: PayloadTransferencia): Promise<Respuesta<ResultadoRegistroTipo>>;
  categoriasSugeridas(): Promise<Respuesta<{ version: number; nodos: NodoSugerido[] }>>;
  onboardingCategorias(): Promise<Respuesta<{ creadas: number; idempotente: boolean }>>;
}

const CAT = '/v1/categorias';
const MAG = '/v1/magnitudes';
const PREF = '/v1/preferencias';
const TER = '/v1/terceros';
const CTX = '/v1/contextos';
const PLT = '/v1/plantillas';
const ACC = '/v1/acciones-rapidas';
const asoc = (cat: string, a?: string) => `${CAT}/${encodeURIComponent(cat)}/magnitudes${a ? `/${encodeURIComponent(a)}` : ''}`;
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
        const rechazo: Respuesta<T> = { tipo: 'RECHAZADO', codigo: cuerpo.codigo, mensaje: String(cuerpo.mensaje ?? '') };
        if (cuerpo.detalle && typeof cuerpo.detalle === 'object') return { ...rechazo, detalle: cuerpo.detalle } as Respuesta<T>;
        return rechazo;
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
    catalogoMagnitudes: () => llamar(MAG, { method: 'GET' }, false),
    asociarMagnitud: (cat, c) => llamar(asoc(cat), post(c), 'CAMBIO'),
    obligatoriaMagnitud: (cat, a, c) => llamar(`${asoc(cat, a)}/obligatoria`, post(c), 'CAMBIO'),
    retirarMagnitud: (cat, a, c) => llamar(`${asoc(cat, a)}/retirar`, post(c), 'CAMBIO'),
    reordenarMagnitudes: (cat, c) => llamar(`${asoc(cat)}/reordenar`, post(c), 'CAMBIO'),
    renombrarMagnitud: (id, c) => llamar(`${MAG}/${encodeURIComponent(id)}/renombrar`, post(c), 'CAMBIO'),
    deshabilitarMagnitud: (id, c) => llamar(`${MAG}/${encodeURIComponent(id)}/deshabilitar`, post(c), 'CAMBIO'),
    rehabilitarMagnitud: (id, c) => llamar(`${MAG}/${encodeURIComponent(id)}/rehabilitar`, post(c), 'CAMBIO'),
    propuestaPreferencias: (fecha, categoriaId) =>
      llamar(
        `${PREF}/propuesta?fecha=${encodeURIComponent(fecha)}${categoriaId === null ? '' : `&categoria_id=${encodeURIComponent(categoriaId)}`}`,
        { method: 'GET' },
        false,
      ),
    listarPreferencias: () => llamar(PREF, { method: 'GET' }, false),
    altaPreferencia: (c) => llamar(PREF, post(c), 'CAMBIO'),
    editarPreferencia: (id, c) => llamar(`${PREF}/${encodeURIComponent(id)}/editar`, post(c), 'CAMBIO'),
    desactivarPreferencia: (id, row_version) => llamar(`${PREF}/${encodeURIComponent(id)}/desactivar`, post({ row_version }), 'CAMBIO'),
    reactivarPreferencia: (id, row_version) => llamar(`${PREF}/${encodeURIComponent(id)}/reactivar`, post({ row_version }), 'CAMBIO'),
    cuentasElegibles: (operacion, fecha) =>
      llamar(`/v1/cuentas/elegibles?operacion=${encodeURIComponent(operacion)}&fecha=${encodeURIComponent(fecha)}`, { method: 'GET' }, false),
    listarTerceros: () => llamar(TER, { method: 'GET' }, false),
    candidatosTercero: (nombre) => llamar(`${TER}/candidatos?nombre=${encodeURIComponent(nombre)}`, { method: 'GET' }, false),
    altaTercero: (c) => llamar(TER, post(c), 'CAMBIO'),
    editarTercero: (id, c) => llamar(`${TER}/${encodeURIComponent(id)}/editar`, post(c), 'CAMBIO'),
    desactivarTercero: (id, row_version) => llamar(`${TER}/${encodeURIComponent(id)}/desactivar`, post({ row_version }), 'CAMBIO'),
    reactivarTercero: (id, row_version) => llamar(`${TER}/${encodeURIComponent(id)}/reactivar`, post({ row_version }), 'CAMBIO'),
    listarContextos: () => llamar(CTX, { method: 'GET' }, false),
    altaContexto: (c) => llamar(CTX, post(c), 'CAMBIO'),
    editarContexto: (id, c) => llamar(`${CTX}/${encodeURIComponent(id)}/editar`, post(c), 'CAMBIO'),
    desactivarContexto: (id, row_version) => llamar(`${CTX}/${encodeURIComponent(id)}/desactivar`, post({ row_version }), 'CAMBIO'),
    reactivarContexto: (id, row_version) => llamar(`${CTX}/${encodeURIComponent(id)}/reactivar`, post({ row_version }), 'CAMBIO'),
    listarPlantillas: () => llamar(PLT, { method: 'GET' }, false),
    altaPlantilla: (c) => llamar(PLT, post(c), 'CAMBIO'),
    editarPlantilla: (id, c) => llamar(`${PLT}/${encodeURIComponent(id)}/editar`, post(c), 'CAMBIO'),
    desactivarPlantilla: (id, row_version) => llamar(`${PLT}/${encodeURIComponent(id)}/desactivar`, post({ row_version }), 'CAMBIO'),
    reactivarPlantilla: (id, row_version) => llamar(`${PLT}/${encodeURIComponent(id)}/reactivar`, post({ row_version }), 'CAMBIO'),
    altaAccion: (c) => llamar(ACC, post(c), 'CAMBIO'),
    editarAccion: (id, c) => llamar(`${ACC}/${encodeURIComponent(id)}/editar`, post(c), 'CAMBIO'),
    desactivarAccion: (id, row_version) => llamar(`${ACC}/${encodeURIComponent(id)}/desactivar`, post({ row_version }), 'CAMBIO'),
    reordenarAcciones: (acciones) => llamar(`${ACC}/reordenar`, post({ acciones }), 'CAMBIO'),
    propuestaRegistro: (q) => {
      const ps = new URLSearchParams({ tipo: q.tipo, fecha: q.fecha });
      if (q.plantillaId) ps.set('plantilla_id', q.plantillaId);
      if (q.categoriaId) ps.set('categoria_id', q.categoriaId);
      if (q.sinCategoria) ps.set('sin_categoria', 'true');
      if (q.terceroId) ps.set('tercero_id', q.terceroId);
      if (q.sinTercero) ps.set('sin_tercero', 'true');
      return llamar(`/v1/registro/propuesta?${ps.toString()}`, { method: 'GET' }, false);
    },
    registrarIngresoCobrado: (p) => llamar('/v1/intenciones/ingreso-cobrado', post(p), true),
    registrarTransferencia: (p) => llamar('/v1/intenciones/transferencia', post(p), true),
    categoriasSugeridas: () => llamar(`${CAT}/sugeridas`, { method: 'GET' }, false),
    onboardingCategorias: () => llamar(`${CAT}/onboarding`, post({}), 'CAMBIO'),
  };
}
