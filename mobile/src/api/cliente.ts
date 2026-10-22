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
// v0.10.0 (F05-05 K3 §2.1–§2.7; F05 §49.4 A1–A9): lecturas de señales (GET /v1/senales/categorias y /v1/senales/terceros; tipos en domain/senales, único import nuevo), búsqueda de terceros en servidor (GET /v1/terceros?q=&incluir_inactivos=), afinidades (lectura del detalle, alta con UUID del cliente y retirada, clasificación 'CAMBIO'), Actividad v0 (página keyset y detalle) y read models de Inicio (yo, Resultado del mes). Las lecturas nuevas llaman `nota` al dato (M5-08); el wire de escritura del gasto no cambia.
// v0.11.0 (F05-06 K-7; F05 §51.8): la categoría de la fila y del detalle de la Actividad trae `icon_key` (tipo aditivo, opcional). Sin rutas nuevas.
// v0.12.0 (F05-06 M4 §2.4/§3; F09 §12.105 CAP): capacidades de cuenta. Lecturas GET /v1/cuentas/capacidades (lista A1), /v1/cuentas/sin-configurar (aviso B2), /v1/cuentas/{id}/capacidades (A2/B1), …/historial (B4) y …/{capacidad}/impacto (A4); comando POST …/{capacidad}/activar | desactivar con `row_version` de la cuenta (clasificación 'CAMBIO'). Tipos sin tipo de cuenta ni defaults (D-CAP-04).
// v0.13.0 (F05-06 M2-B §B1; lámina DEV v0.1): devolución contextual. Lectura GET /v1/hechos/{origen}/devoluciones (contexto del formulario), POST /v1/hechos/{origen}/devoluciones (devolución con el abono «Todavía no» o «Ya cobrado») y POST /v1/hechos/{devolución}/abono («Registrar abono»), ambos con la clasificación de escritura (indeterminado = reintentar el MISMO UUID). La fila y el detalle de la Actividad traen `devolucion_de` y `abono`, y el detalle `devoluciones` (tipos aditivos, opcionales).
// v0.14.0 (F05-06 M3 §B1; lámina REP v0.2): reparto, pagador real y posiciones. POST /v1/intenciones/gasto-compartido (OP-22 de una sola llamada), POST /v1/posiciones/{id}/cobro | pago | perdon, con la clasificación de escritura (indeterminado = reintentar el MISMO UUID); lecturas GET /v1/terceros/{id}/pendiente («Pendiente con», OP-20) y GET /v1/hechos/{id}/reparto; «Corregir reparto» POST /v1/hechos/{id}/reparto con `row_version` (clasificación 'CAMBIO'). Tipos en domain/reparto (único import nuevo).
// v0.15.0 (F05-06 M5 §B1; láminas PREV v0.2 y HOME-01 v0.4): confirmación de previsiones. Lecturas GET /v1/inicio/previsiones, /v1/previsiones/pendientes, /v1/previsiones/{id} y …/candidatos (?ampliado); escrituras POST …/vincular («Ya lo registré», OP-17) y …/omitir («No hubo este mes»), ambas con la clasificación de escritura (indeterminado = reintentar el MISMO UUID). El bloque opcional `prevision` viaja en ingreso, transferencia y, por tipo estructural, en el gasto. Tipos propios en este fichero: sin imports nuevos.
// v0.16.0 (F05-06 M5-B; F04-D065, F05-D047): «Dar por cubierta» POST /v1/previsiones/{id}/dar-por-realizada y «Reabrir» POST …/reabrir (con `sucesor_row_version` cuando la lectura trae sucesor), ambas con la clasificación de escritura como «No hubo» (indeterminado = misma identidad; el reintento devuelve el estado actual). El detalle añade `pendiente` (esperado − registrado, con signo; derivado, nunca guardado), `recalculable`, `sucesor` y las acciones `dar_por_cubierta` y `reabrir`.
// v0.17.0 (F05-06 M1; lámina EDIT-HECHO v0.1; F05 §61.2): GET /v1/hechos/{id}/edicion (elegibilidad visible, informativa: el servidor revalida) y las escrituras «Corregir» (POST /v1/hechos/{id}/corregir-pago, POST /v1/transferencias/{id}/corregir) y «Anular por duplicado» (POST /v1/hechos/{id}/anular-duplicado), con la clasificación de escritura (indeterminado = reintentar la MISMA intención: el motor la reconoce por su request_id y no corrige ni anula dos veces). Tipos propios en este fichero.
// Versión: 0.17.0
// v0.18.0 (F05-06 M1 v1.1; Q9 opción (a)): «Corregir categoría» de un registro de V3, POST /v1/hechos/{id}/corregir-categoria (lista blanca: versión, motivo y `categoria_id`), con la clasificación de escritura (indeterminado = reintentar la MISMA intención). La lectura /edicion trae `categoria` y `acciones.corregir_categoria`, ambos null fuera de V3.
// Versión: 0.18.0
// ============================================================

import type { Ambito, CategoriaNodo } from '../domain/categoria';
import type { PayloadGastoPagado } from '../domain/intencion';
import type { MagnitudCatalogo } from '../domain/magnitud';
import type {
  PayloadCobroPago,
  PayloadCorregirReparto,
  PayloadGastoCompartido,
  PayloadPerdon,
  PendienteConPersona,
  RepartoDeHecho,
  ResultadoCorreccionReparto,
  ResultadoGastoCompartido,
  ResultadoPosicion,
} from '../domain/reparto';
import type { SenalesCategorias, SenalesTerceros } from '../domain/senales';

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
  /** Fecha del último hecho activo (homónimos por uso, A4). */
  ultimo_uso?: string | null;
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
  prevision?: BloquePrevisionWire;
}

export interface PayloadTransferencia {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  cuenta_origen_id: string;
  cuenta_destino_id: string;
  nota?: string | null;
  prevision?: BloquePrevisionWire;
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

// ------------------------------------------------------------------ F05-05 (afinidades, Actividad v0, Inicio)
export interface AfinidadNodo {
  id: string;
  tercero_id: string;
  categoria_id: string;
}

export interface ResultadoComandoAfinidad {
  afinidad: AfinidadNodo | null;
  idempotente: boolean;
  aviso: 'AFINIDAD_YA_EXISTE' | null;
}

export interface DetalleAfinidades {
  tercero_id: string;
  tipo: 'GASTO' | 'INGRESO';
  guardadas: { id: string; categoria_id: string; nombre: string; ruta: string; disponible: boolean }[];
  segun_historial: { categoria_id: string; nombre: string; ruta: string; usos: number }[];
  total_registros: number;
}

export type TipoActividad = 'GASTO' | 'INGRESO' | 'TRANSFERENCIA';
export interface ReferenciaActividad {
  id: string;
  nombre: string;
  enabled: boolean;
}

export interface FilaActividad {
  id: string;
  fecha_hecho: string;
  tipo: TipoActividad;
  nota: string | null;
  moneda: string;
  importe_total: string | null;
  tercero: ReferenciaActividad | null;
  categoria: (ReferenciaActividad & { ruta: string; icon_key?: string | null }) | null;
  varias: boolean;
  contexto: ReferenciaActividad | null;
  cuentas: { cuenta_id: string; nombre: string; rol: 'PAGO' | 'COBRO' | 'ORIGEN' | 'DESTINO'; enabled: boolean }[];
  estado_reparto: 'COMPLETA' | 'PARCIAL' | 'NO_DISPONIBLE' | null;
  tu_parte: string | null;
  pendiente: string | null;
  maestros_desactivados: ('CATEGORIA' | 'TERCERO' | 'CONTEXTO')[];
  coincide_en?: ('TERCERO' | 'CATEGORIA' | 'CONTEXTO' | 'NOTA' | 'IMPORTE')[] | null;
  /** F05-06 M2: origen de una devolución (null si no lo es) y estado de su abono. */
  devolucion_de?: { hecho_id: string; nota: string | null; fecha_hecho: string; tercero: string | null } | null;
  abono?: 'PENDIENTE' | 'COBRADO' | null;
}

export interface PaginaActividad {
  filas: FilaActividad[];
  siguiente: string | null;
  total: number;
}

export interface DetalleActividad extends FilaActividad {
  presupuestable: boolean;
  magnitudes: { magnitud_id: string; nombre: string; valor: string; unidad: string | null }[];
  /** F05-06 M2: devoluciones activas de una compra, lo devuelto, lo que queda y el neto derivado. */
  devoluciones?: { items: DevolucionDeOrigen[]; devuelto: string; queda: string; neto: string } | null;
}

// ------------------------------------------------------------------ F05-06 M2 devolución contextual
export interface DevolucionDeOrigen {
  hecho_id: string;
  fecha_hecho: string;
  importe: string;
  abono: 'PENDIENTE' | 'COBRADO';
}

export interface ContextoDevolucion {
  origen_id: string;
  fecha_hecho: string;
  nota: string | null;
  tercero: string | null;
  categoria_id: string | null;
  categoria: string | null;
  importe_total: string;
  devuelto: string;
  queda: string;
  neto: string;
  devoluciones: DevolucionDeOrigen[];
  disponible: boolean;
  motivo: string | null;
  atribucion_propuesta: 'SOLO_MIO' | 'SIN_INDICAR';
  tuya_disponible: boolean;
  cuenta_compra: { cuenta_id: string; nombre: string } | null;
}

export interface PayloadDevolucion {
  intencion_id: string;
  importe: string;
  moneda: 'EUR';
  fecha_hecho: string;
  atribucion: 'SOLO_MIO' | 'SIN_INDICAR';
  abono: { estado: 'PENDIENTE' } | { estado: 'COBRADO'; cuenta_id: string; fecha: string };
  nota?: string;
}

export interface ResultadoDevolucion {
  hecho_id: string;
  origen_id: string;
  idempotente: boolean;
  importe: string;
  estado_atribucion: 'COMPLETA' | 'NO_DISPONIBLE';
  abono: 'PENDIENTE' | 'COBRADO';
  devuelto: string;
  queda: string;
}

export interface PayloadAbono {
  intencion_id: string;
  cuenta_id: string;
  fecha: string;
}

export interface ResultadoAbono {
  hecho_id: string;
  movimiento_id: string;
  idempotente: boolean;
  importe: string;
  abono: 'COBRADO';
}

/** Consulta de la Actividad: periodo [desde, hasta) opcional (sin periodo = todo el historial). */
export interface ConsultaActividad {
  desde?: string | null;
  hasta?: string | null;
  tipos?: TipoActividad[];
  categoriaId?: string | null;
  incluirSubcategorias?: boolean;
  cuentaId?: string | null;
  terceroId?: string | null;
  contextoId?: string | null;
  q?: string | null;
  importe?: string | null;
  cursor?: string | null;
  limite?: number;
}

export interface ResultadoMes {
  mes: string;
  moneda: 'EUR';
  ingresos_propios: string;
  gastos_propios: string;
  resultado: string;
  sin_indicar: { gastos: { n: number; importe: string }; ingresos: { n: number; importe: string } };
}

// ------------------------------------------------------------------ F05-06 M4 capacidades de cuenta
export type CodigoCapacidad = 'PAGAR_GASTO' | 'RECIBIR_INGRESO' | 'TRANSFERIR_SALIDA' | 'TRANSFERIR_ENTRADA' | 'COMPRA_TARJETA' | 'DOMICILIAR';

export interface CapacidadNodo {
  codigo: CodigoCapacidad;
  etiqueta: string;
  efecto: string;
  permitida: boolean;
  editable: boolean;
}

export interface CuentaCapacidades {
  cuenta_id: string;
  nombre: string;
  estado: 'ACTIVA' | 'DESHABILITADA' | 'CERRADA';
  row_version: number;
  origen_v3: boolean;
  sin_configurar: boolean;
  capacidades: CapacidadNodo[];
  otras: CapacidadNodo[];
}

export interface ImpactoCapacidad {
  plantillas: { plantilla_id: string; nombre: string; enabled: boolean }[];
  preferencias: { preferencia_id: string; enabled: boolean; categoria_id: string | null; categoria_nombre: string | null; tercero_id: string | null; tercero_nombre: string | null }[];
}

export interface EntradaHistorialCapacidad {
  cuando: string;
  accion: 'ACTIVAR' | 'DESACTIVAR';
  capacidad: CodigoCapacidad;
  etiqueta: string;
  actor_tipo: 'USUARIO' | 'SISTEMA';
  actor_es_owner: boolean;
}

// ------------------------------------------------------------------ F05-06 M5 · previsiones
/** Bloque `prevision` del registro desde la previsión: `marcar_realizada` siempre explícito (D-M5-04). */
export interface BloquePrevisionWire {
  prevision_id: string;
  row_version: number;
  marcar_realizada: boolean;
}
export type TipoPrevision = 'GASTO' | 'INGRESO' | 'TRANSFERENCIA';
export type NaturalezaPrevision = 'POR_PAGAR' | 'POR_COBRAR' | 'ENTRE_CUENTAS';
export interface RefNombre {
  id: string;
  nombre: string;
}
export interface FilaPrevision {
  id: string;
  row_version: number;
  estado: string;
  tipo: TipoPrevision | string;
  naturaleza: NaturalezaPrevision | null;
  concepto: string;
  tercero: RefNombre | null;
  categoria: { id: string; nombre: string; ruta: string } | null;
  fecha_desde: string | null;
  fecha_hasta: string | null;
  moneda: string;
  /** null = «Desconocido», nunca 0. */
  importe_esperado: string | null;
  cubierto: string;
  queda: string | null;
  desviacion: string | null;
  con_realidad: boolean;
  pagos: number;
  vencida: boolean;
  cuenta_salida: RefNombre | null;
  cuenta_entrada: RefNombre | null;
  origen: 'MANUAL' | 'REGLA' | 'V3';
  presupuestable: boolean;
}
export interface InicioPrevisiones {
  hoy: string;
  requiere_atencion: { n: number; primeras: FilaPrevision[] };
  proximos: FilaPrevision[];
}
export interface ImportePorNaturaleza {
  importe: string | null;
  n: number;
  desconocidos: number;
}
export interface PendientesPrevisiones {
  hoy: string;
  n: number;
  por_pagar: ImportePorNaturaleza;
  por_cobrar: ImportePorNaturaleza;
  secciones: { vencidas: FilaPrevision[]; con_pago_parcial: FilaPrevision[]; sin_fecha: FilaPrevision[] };
}
export interface AccionPrevision {
  disponible: boolean;
  motivo: string | null;
}
export interface DetallePrevision extends FilaPrevision {
  estado_derivado: 'REALIZADA_SIN_REALIDAD_ACTIVA' | 'REQUIERE_REVISION' | null;
  vinculos: { vinculo_id: string; hecho_id: string; importe_asignado: string; fecha_hecho: string; concepto: string | null; importe_total: string | null }[];
  acciones: {
    registrar: AccionPrevision;
    ya_lo_registre: AccionPrevision;
    omitir: AccionPrevision;
    swipe: AccionPrevision;
    dar_por_cubierta: AccionPrevision;
    reabrir: AccionPrevision;
  };
  /** M5-B: esperado − registrado con signo (negativo = registrado de más); null si el esperado es desconocido. Derivado: nunca se guarda. */
  pendiente: string | null;
  recalculable: boolean;
  /** Siguiente previsión ABIERTA de la serie (RODANTE): «Reabrir» exige su versión. */
  sucesor: { id: string; row_version: number } | null;
}
export interface CandidatoPrevision {
  hecho_id: string;
  fecha_hecho: string;
  concepto: string | null;
  tercero: string | null;
  categoria: string | null;
  cuenta: string | null;
  importe_total: string;
  /** Lo que se vinculará: toda la porción libre del registro (AJ-M5-DEC-05). */
  porcion_disponible: string;
}
export interface CandidatosPrevision {
  prevision_id: string;
  ampliado: boolean;
  ventana_dias: number;
  mensaje: string | null;
  candidatos: CandidatoPrevision[];
}
export interface PayloadVincular {
  intencion_id: string;
  row_version: number;
  hecho_id: string;
  importe_a_vincular: string;
  marcar_realizada: boolean;
}
export interface ResultadoVinculo {
  intencion_id: string;
  prevision_id: string;
  hecho_id: string;
  importe_vinculado: string;
  estado: string;
  row_version: number;
  idempotente: boolean;
}
export interface PayloadOmitir {
  intencion_id: string;
  row_version: number;
  motivo: string | null;
}
export interface ResultadoOmitir {
  intencion_id: string;
  prevision_id: string;
  estado: string;
  row_version: number;
}
export interface PayloadDarPorCubierta {
  intencion_id: string;
  row_version: number;
  motivo: string;
}
export interface PayloadReabrir {
  intencion_id: string;
  row_version: number;
  motivo: string;
  sucesor_row_version: number | null;
}
export interface ResultadoTransicion {
  intencion_id: string;
  prevision_id: string;
  estado: string;
  row_version: number;
}

// ------------------------------------------------------------------ F05-06 M1 · corregir y anular
export interface AccionEdicionWire {
  disponible: boolean;
  codigo: string | null;
  motivo: string | null;
}
export interface MovimientoEdicion {
  movimiento_id: string;
  row_version: number;
  pata: 'SALIDA' | 'ENTRADA';
  cuenta: { id: string; nombre: string | null };
  importe: string | null;
  fecha: string;
}
export interface EdicionHecho {
  hecho_id: string;
  row_version: number;
  estado: string;
  tipo: string;
  importe: string | null;
  fecha: string;
  moneda: string;
  origen_v3: boolean;
  anulado: { fecha: string | null; motivo: string | null } | null;
  movimientos: MovimientoEdicion[];
  /** Solo V3: el efecto único y su categoría actual. */
  categoria?: { efecto_id: string; naturaleza: 'GASTO' | 'INGRESO'; categoria_id: string | null; nombre: string | null } | null;
  acciones: { corregir: AccionEdicionWire; anular_duplicado: AccionEdicionWire; corregir_categoria?: AccionEdicionWire | null };
}
export interface PayloadCorregirCategoria {
  intencion_id: string;
  row_version: number;
  motivo: string;
  categoria_id: string;
}
export interface PayloadCorregirPago {
  intencion_id: string;
  row_version: number;
  movimiento_row_version: number;
  motivo: string;
  error_de_registro: true;
  importe?: string;
  fecha?: string;
  cuenta_id?: string;
}
export interface PayloadCorregirTransferencia {
  intencion_id: string;
  row_version: number;
  movimientos_row_version: Record<string, number>;
  motivo: string;
  error_de_registro: true;
  importe?: string;
  fecha?: string;
  cuenta_origen_id?: string;
  cuenta_destino_id?: string;
}
export interface PayloadAnularDuplicado {
  intencion_id: string;
  row_version: number;
  movimientos_row_version: Record<string, number>;
  motivo: string;
  duplicado_declarado: boolean;
}
export interface ResultadoEdicion {
  intencion_id: string;
  hecho_id: string;
  row_version: number;
  estado: string;
  idempotente: boolean;
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
  // F05-05
  senalesCategorias(q: { tipo: 'GASTO' | 'INGRESO'; fecha: string; terceroId?: string | null }): Promise<Respuesta<SenalesCategorias>>;
  senalesTerceros(tipo: 'GASTO' | 'INGRESO', fecha: string): Promise<Respuesta<SenalesTerceros>>;
  buscarTerceros(q: string, incluirInactivos: boolean): Promise<Respuesta<{ terceros: Tercero[] }>>;
  afinidadesTercero(terceroId: string, fecha: string, tipo?: 'GASTO' | 'INGRESO'): Promise<Respuesta<DetalleAfinidades>>;
  altaAfinidad(c: { id: string; tercero_id: string; categoria_id: string }): Promise<Respuesta<ResultadoComandoAfinidad>>;
  retirarAfinidad(id: string): Promise<Respuesta<ResultadoComandoAfinidad>>;
  actividad(q: ConsultaActividad): Promise<Respuesta<PaginaActividad>>;
  detalleActividad(id: string): Promise<Respuesta<DetalleActividad>>;
  yo(): Promise<Respuesta<{ nombre: string | null }>>;
  resultadoMes(fecha: string): Promise<Respuesta<ResultadoMes>>;
  listarCapacidades(): Promise<Respuesta<{ cuentas: CuentaCapacidades[]; sin_configurar: number }>>;
  cuentasSinConfigurar(): Promise<Respuesta<{ sin_configurar: number }>>;
  detalleCapacidades(cuentaId: string): Promise<Respuesta<CuentaCapacidades>>;
  historialCapacidades(cuentaId: string): Promise<Respuesta<{ entradas: EntradaHistorialCapacidad[] }>>;
  impactoCapacidad(cuentaId: string, capacidad: CodigoCapacidad): Promise<Respuesta<ImpactoCapacidad>>;
  cambiarCapacidad(cuentaId: string, capacidad: CodigoCapacidad, permitir: boolean, row_version: number): Promise<Respuesta<{ cuenta: CuentaCapacidades; idempotente: boolean }>>;
  contextoDevolucion(origenId: string): Promise<Respuesta<ContextoDevolucion>>;
  registrarDevolucion(origenId: string, p: PayloadDevolucion): Promise<Respuesta<ResultadoDevolucion>>;
  registrarAbono(devolucionId: string, p: PayloadAbono): Promise<Respuesta<ResultadoAbono>>;
  // F05-06 M3
  registrarGastoCompartido(p: PayloadGastoCompartido): Promise<Respuesta<ResultadoGastoCompartido>>;
  pendienteCon(terceroId: string): Promise<Respuesta<PendienteConPersona>>;
  cobrarPosicion(entidadId: string, p: PayloadCobroPago): Promise<Respuesta<ResultadoPosicion>>;
  pagarPosicion(entidadId: string, p: PayloadCobroPago): Promise<Respuesta<ResultadoPosicion>>;
  perdonarPosicion(entidadId: string, p: PayloadPerdon): Promise<Respuesta<ResultadoPosicion>>;
  repartoDeHecho(hechoId: string): Promise<Respuesta<RepartoDeHecho>>;
  corregirReparto(hechoId: string, p: PayloadCorregirReparto): Promise<Respuesta<ResultadoCorreccionReparto>>;
  // F05-06 M5
  inicioPrevisiones(): Promise<Respuesta<InicioPrevisiones>>;
  pendientesPrevisiones(): Promise<Respuesta<PendientesPrevisiones>>;
  detallePrevision(id: string): Promise<Respuesta<DetallePrevision>>;
  candidatosPrevision(id: string, ampliado: boolean): Promise<Respuesta<CandidatosPrevision>>;
  vincularPrevision(id: string, p: PayloadVincular): Promise<Respuesta<ResultadoVinculo>>;
  omitirPrevision(id: string, p: PayloadOmitir): Promise<Respuesta<ResultadoOmitir>>;
  // F05-06 M5-B
  darPorCubiertaPrevision(id: string, p: PayloadDarPorCubierta): Promise<Respuesta<ResultadoTransicion>>;
  reabrirPrevision(id: string, p: PayloadReabrir): Promise<Respuesta<ResultadoTransicion>>;
  // F05-06 M1
  edicionHecho(id: string): Promise<Respuesta<EdicionHecho>>;
  corregirPago(id: string, p: PayloadCorregirPago): Promise<Respuesta<ResultadoEdicion>>;
  corregirTransferencia(id: string, p: PayloadCorregirTransferencia): Promise<Respuesta<ResultadoEdicion>>;
  anularDuplicado(id: string, p: PayloadAnularDuplicado): Promise<Respuesta<ResultadoEdicion>>;
  corregirCategoria(id: string, p: PayloadCorregirCategoria): Promise<Respuesta<ResultadoEdicion>>;
}

const CAT = '/v1/categorias';
const MAG = '/v1/magnitudes';
const PREF = '/v1/preferencias';
const TER = '/v1/terceros';
const CTX = '/v1/contextos';
const PLT = '/v1/plantillas';
const ACC = '/v1/acciones-rapidas';
const CAP = (id: string) => `/v1/cuentas/${encodeURIComponent(id)}/capacidades`;
const HECHO = (id: string) => `/v1/hechos/${encodeURIComponent(id)}`;
const POS = (id: string) => `/v1/posiciones/${encodeURIComponent(id)}`;
const PREV = (id: string) => `/v1/previsiones/${encodeURIComponent(id)}`;
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
    senalesCategorias: (q) => {
      const ps = new URLSearchParams({ tipo: q.tipo, fecha: q.fecha });
      if (q.terceroId) ps.set('tercero_id', q.terceroId);
      return llamar(`/v1/senales/categorias?${ps.toString()}`, { method: 'GET' }, false);
    },
    senalesTerceros: (tipo, fecha) =>
      llamar(`/v1/senales/terceros?tipo=${encodeURIComponent(tipo)}&fecha=${encodeURIComponent(fecha)}`, { method: 'GET' }, false),
    buscarTerceros: (q, incluirInactivos) =>
      llamar(`${TER}?q=${encodeURIComponent(q)}${incluirInactivos ? '&incluir_inactivos=1' : ''}`, { method: 'GET' }, false),
    afinidadesTercero: (terceroId, fecha, tipo = 'GASTO') =>
      llamar(`${TER}/${encodeURIComponent(terceroId)}/afinidades?fecha=${encodeURIComponent(fecha)}&tipo=${tipo}`, { method: 'GET' }, false),
    altaAfinidad: (c) => llamar('/v1/afinidades', post(c), 'CAMBIO'),
    retirarAfinidad: (id) => llamar(`/v1/afinidades/${encodeURIComponent(id)}/retirar`, post({}), 'CAMBIO'),
    actividad: (q) => {
      const ps = new URLSearchParams();
      if (q.desde) ps.set('desde', q.desde);
      if (q.hasta) ps.set('hasta', q.hasta);
      for (const t of q.tipos ?? []) ps.append('tipo', t);
      if (q.categoriaId) ps.set('categoria_id', q.categoriaId);
      if (q.categoriaId && q.incluirSubcategorias === false) ps.set('incluir_subcategorias', 'false');
      if (q.cuentaId) ps.set('cuenta_id', q.cuentaId);
      if (q.terceroId) ps.set('tercero_id', q.terceroId);
      if (q.contextoId) ps.set('contexto_id', q.contextoId);
      if (q.q) ps.set('q', q.q);
      if (q.importe) ps.set('importe', q.importe);
      if (q.cursor) ps.set('cursor', q.cursor);
      if (q.limite) ps.set('limite', String(q.limite));
      const qs = ps.toString();
      return llamar(`/v1/actividad${qs ? `?${qs}` : ''}`, { method: 'GET' }, false);
    },
    detalleActividad: (id) => llamar(`/v1/actividad/${encodeURIComponent(id)}`, { method: 'GET' }, false),
    yo: () => llamar('/v1/yo', { method: 'GET' }, false),
    resultadoMes: (fecha) => llamar(`/v1/inicio/resultado-mes?fecha=${encodeURIComponent(fecha)}`, { method: 'GET' }, false),
    listarCapacidades: () => llamar('/v1/cuentas/capacidades', { method: 'GET' }, false),
    cuentasSinConfigurar: () => llamar('/v1/cuentas/sin-configurar', { method: 'GET' }, false),
    detalleCapacidades: (id) => llamar(CAP(id), { method: 'GET' }, false),
    historialCapacidades: (id) => llamar(`${CAP(id)}/historial`, { method: 'GET' }, false),
    impactoCapacidad: (id, cap) => llamar(`${CAP(id)}/${encodeURIComponent(cap)}/impacto`, { method: 'GET' }, false),
    cambiarCapacidad: (id, cap, permitir, row_version) =>
      llamar(`${CAP(id)}/${encodeURIComponent(cap)}/${permitir ? 'activar' : 'desactivar'}`, post({ row_version }), 'CAMBIO'),
    contextoDevolucion: (id) => llamar(`${HECHO(id)}/devoluciones`, { method: 'GET' }, false),
    registrarDevolucion: (id, payload) => llamar(`${HECHO(id)}/devoluciones`, post(payload), true),
    registrarAbono: (id, payload) => llamar(`${HECHO(id)}/abono`, post(payload), true),
    registrarGastoCompartido: (payload) => llamar('/v1/intenciones/gasto-compartido', post(payload), true),
    pendienteCon: (id) => llamar(`${TER}/${encodeURIComponent(id)}/pendiente`, { method: 'GET' }, false),
    cobrarPosicion: (id, payload) => llamar(`${POS(id)}/cobro`, post(payload), true),
    pagarPosicion: (id, payload) => llamar(`${POS(id)}/pago`, post(payload), true),
    perdonarPosicion: (id, payload) => llamar(`${POS(id)}/perdon`, post(payload), true),
    repartoDeHecho: (id) => llamar(`${HECHO(id)}/reparto`, { method: 'GET' }, false),
    corregirReparto: (id, payload) => llamar(`${HECHO(id)}/reparto`, post(payload), 'CAMBIO'),
    inicioPrevisiones: () => llamar('/v1/inicio/previsiones', { method: 'GET' }, false),
    pendientesPrevisiones: () => llamar('/v1/previsiones/pendientes', { method: 'GET' }, false),
    detallePrevision: (id) => llamar(PREV(id), { method: 'GET' }, false),
    candidatosPrevision: (id, ampliado) => llamar(`${PREV(id)}/candidatos?ampliado=${ampliado ? 'true' : 'false'}`, { method: 'GET' }, false),
    vincularPrevision: (id, payload) => llamar(`${PREV(id)}/vincular`, post(payload), true),
    omitirPrevision: (id, payload) => llamar(`${PREV(id)}/omitir`, post(payload), true),
    darPorCubiertaPrevision: (id, payload) => llamar(`${PREV(id)}/dar-por-realizada`, post(payload), true),
    reabrirPrevision: (id, payload) => llamar(`${PREV(id)}/reabrir`, post(payload), true),
    edicionHecho: (id) => llamar(`${HECHO(id)}/edicion`, { method: 'GET' }, false),
    corregirPago: (id, payload) => llamar(`${HECHO(id)}/corregir-pago`, post(payload), true),
    corregirTransferencia: (id, payload) => llamar(`/v1/transferencias/${encodeURIComponent(id)}/corregir`, post(payload), true),
    anularDuplicado: (id, payload) => llamar(`${HECHO(id)}/anular-duplicado`, post(payload), true),
    corregirCategoria: (id, payload) => llamar(`${HECHO(id)}/corregir-categoria`, post(payload), true),
  };
}
