// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos.ts
// Ruta: mobile/src/api/contratos.ts
// Descripción: Cliente HTTP de F06-02/03 · Contratos de alquiler, servicios y terceros, SIN renta (contrato N1 v1.1: rutas de la Parte I a VI; lámina CON v0.8). Fuente única del DTO del cliente: los tipos siguen el contrato (C-CON-01..06, C-REV-01, C-SRV-01..04, C-TER-01/03, L-CON-01..03, L-SRV-01, L-TER-01 y la lectura del selector con «uso en Gapto», V-bis). Las escrituras usan la clasificación 'CAMBIO' (replay idempotente por `intencion_id`; indeterminado = comprobar antes de repetir). Importes y porcentajes viajan como texto exacto. No existe renta, fianza ni cobro: ninguna petición lleva `renta` ni `fianza` (R-E-01; el servidor respondería RENTA_NO_DISPONIBLE). Va aparte de `cliente.ts` (que no se toca: test_154 I13a) e importa de él como `patrimonio.ts`.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import { ConfigApi, crearLlamada, Respuesta, Tercero } from './cliente';

export type TipoContrato = 'VIVIENDA_COMPLETA' | 'HABITACION' | 'OTRO';
export type EstadoDocumental = 'BORRADOR' | 'FORMALIZADO' | 'CANCELADO';
/** Situación DERIVADA por el servidor (nunca columna): vigente, próximo, borrador, finalizado o cancelado. */
export type SituacionContrato = 'VIGENTE' | 'PROXIMO' | 'BORRADOR' | 'FINALIZADO' | 'CANCELADO';
export type RolParticipante = 'PROPIETARIO' | 'INQUILINO' | 'AVALISTA' | 'GESTOR' | 'AGENCIA' | 'ADMINISTRADOR';
export type ModoTratamiento = 'INCLUIDO' | 'REPERCUTIDO_FIJO' | 'POR_FACTURA' | 'NO_REPERCUTIDO' | 'SIN_INDICAR';
export type TipoClausula = 'IPC' | 'PORCENTAJE_FIJO' | 'INDICE' | 'MANUAL' | 'OTRO' | 'NINGUNA';
export type TipoServicio = 'LUZ' | 'AGUA' | 'GAS' | 'INTERNET' | 'LIMPIEZA' | 'COMUNIDAD' | 'SEGURO' | 'OTRO';
/** Roles de TERCERO (ck_tercero_roles__rol_codigo). AGENCIA y ADMINISTRADOR NO son roles de tercero (decisión 2 = A). */
export type RolTercero =
  | 'COMERCIO' | 'ENTIDAD_FINANCIERA' | 'FINANCIADOR' | 'INQUILINO' | 'AVALISTA' | 'EMPLEADOR' | 'SUMINISTRADOR' | 'OBLIGADO_REEMBOLSO' | 'GESTOR' | 'ASEGURADORA';

// ------------------------------------------------------------------ escritura (C-CON, C-REV, C-SRV, C-TER)
export type ActorWire = 'YO' | { tercero_id: string };

export interface PersonaWire {
  actor: ActorWire;
  rol: RolParticipante;
  principal: boolean;
}

export interface ClausulaWire {
  tipo: TipoClausula;
  indice_referencia?: string | null;
  periodicidad_meses?: number | null;
  fecha_primera_revision?: string | null;
  porcentaje_fijo?: string | null;
}

export interface TratamientoWire {
  servicio_id: string;
  modo: ModoTratamiento;
  /** INQUILINO vigente (REPERCUTIDO_FIJO y POR_FACTURA). */
  actor?: { tercero_id: string } | null;
  /** (0, 100] en REPERCUTIDO_FIJO; NULL en el resto. */
  porcentaje?: string | null;
  desde?: string;
}

export interface PayloadAltaContrato {
  intencion_id: string;
  propiedad_id: string;
  tipo: TipoContrato;
  habitacion?: number | null;
  nombre: string;
  fecha_inicio: string;
  fecha_fin_prevista?: string | null;
  estado: 'FORMALIZADO' | 'BORRADOR';
  personas?: PersonaWire[];
  clausula_revision?: ClausulaWire | null;
  servicios?: TratamientoWire[];
  notas?: string | null;
}

export interface PayloadEditarContrato {
  intencion_id: string;
  row_version_esperada: number;
  nombre?: string;
  notas?: string | null;
  fecha_fin_prevista?: string | null;
  motivo?: string;
}

export interface PayloadTerminar {
  intencion_id: string;
  row_version_esperada: number;
  fecha_fin_real: string;
}

export interface PayloadSucesor {
  intencion_id: string;
  row_version_esperada: number;
  fecha_fin_real: string;
  nuevo: Omit<PayloadAltaContrato, 'intencion_id' | 'propiedad_id' | 'tipo' | 'habitacion'>;
}

export interface PayloadServicio {
  intencion_id: string;
  tipo_servicio: TipoServicio;
  nombre: string;
  categoria_default_id?: string | null;
  propiedad_id?: string | null;
  desde?: string | null;
  notas?: string | null;
}

export interface PayloadAnadirRoles {
  intencion_id: string;
  row_version_esperada: number;
  anadir: RolTercero[];
}

export interface PayloadAnadirClasificacion {
  intencion_id: string;
  row_version_esperada: number;
  anadir: string[];
  principal?: string | null;
}

// ------------------------------------------------------------------ lecturas
export interface FilaContrato {
  contrato_id: string;
  nombre: string;
  tipo: TipoContrato;
  habitacion: number | null;
  estado_documental: EstadoDocumental;
  situacion: SituacionContrato;
  fecha_inicio: string;
  fecha_fin_prevista: string | null;
  fecha_fin_real: string | null;
  /** Vigente con fin previsto pasado y sin fin real: sigue ocupando (decisión 6). */
  fin_previsto_vencido: boolean;
  /** Nombre del inquilino principal (para la fila). */
  inquilino_principal: string | null;
  /** Contrato de V3 con `regla_renta_id`: «Renta registrada · se gestiona en la parte de cobros» (sin importes). */
  renta_registrada: boolean;
}

export interface OcupacionHabitacion {
  habitacion: number;
  estado: 'OCUPADA' | 'PROXIMA' | 'LIBRE';
  /** Fin real o previsto, solo informativo. */
  hasta: string | null;
  desde: string | null;
  contrato_id: string | null;
}

export interface ContratosPropiedad {
  hoy: string;
  habitaciones_ficha: number | null;
  ocupacion: OcupacionHabitacion[];
  contratos: FilaContrato[];
}

export interface PersonaContrato {
  persona_id: string;
  actor: { yo: boolean; tercero_id: string | null; nombre: string | null };
  rol: RolParticipante;
  principal: boolean;
  vigente_desde: string;
  vigente_hasta: string | null;
}

export interface ClausulaVersion {
  version_id: string;
  tipo: TipoClausula;
  indice_referencia: string | null;
  periodicidad_meses: number | null;
  fecha_primera_revision: string | null;
  porcentaje_fijo: string | null;
  vigente_desde: string | null;
  vigente_hasta: string | null;
}

export interface TratamientoContrato {
  servicio_id: string;
  servicio_nombre: string;
  tipo_servicio: TipoServicio;
  modo: ModoTratamiento;
  actor_nombre: string | null;
  porcentaje: string | null;
  vigente_desde: string | null;
  vigente_hasta: string | null;
}

export interface Terminable {
  terminable: boolean;
  /** `RENTA_PENDIENTE_DE_F06_04` cuando el contrato trae renta de V3. */
  motivo: string | null;
}

export interface ContratoDetalle {
  contrato_id: string;
  row_version: number;
  nombre: string;
  propiedad_id: string;
  propiedad_nombre: string;
  tipo: TipoContrato;
  habitacion: number | null;
  estado_documental: EstadoDocumental;
  situacion: SituacionContrato;
  fecha_inicio: string;
  fecha_fin_prevista: string | null;
  fecha_fin_real: string | null;
  fin_previsto_vencido: boolean;
  notas: string | null;
  renta_registrada: boolean;
  personas: PersonaContrato[];
  clausula: ClausulaVersion | null;
  servicios: TratamientoContrato[];
  terminable: Terminable;
}

export interface PropuestaContrato {
  nombre_propuesto: string;
  /** Titulares vigentes en `inicio` (lista vacía con titularidad DESCONOCIDA). */
  arrendadores: { actor_id: string; yo: boolean; tercero_id: string | null; nombre: string | null }[];
  habitaciones: { habitacion: number; estado: 'OCUPADA' | 'PROXIMA' | 'LIBRE'; hasta: string | null; desde: string | null }[];
}

export interface ServicioPropiedad {
  servicio_id: string;
  nombre: string;
  tipo_servicio: TipoServicio;
  categoria_default_id: string | null;
  categoria_default_nombre: string | null;
  desde: string | null;
  hasta: string | null;
  row_version: number;
  /** Compañía de los últimos pagos (D5): dato informativo, no editable aquí. */
  compania_ultimos_pagos: string | null;
  tratamientos: { contrato_id: string; contrato_nombre: string; modo: ModoTratamiento; porcentaje: string | null }[];
}

export interface ServiciosPropiedad {
  vigentes: ServicioPropiedad[];
  anteriores: ServicioPropiedad[];
}

/** «Uso en Gapto» derivado al leer (V-bis; regla estable AJ-COMP-03): nunca almacenado. */
export type UsoTercero =
  | { tipo: 'CONTRATO'; rol: RolParticipante; contrato_id: string; contrato_nombre: string; desde: string; hasta: string | null }
  | { tipo: 'MOVIMIENTO'; fecha: string }
  | { tipo: 'SIN_USO' };

export interface TerceroParaContrato extends Tercero {
  uso: UsoTercero;
}

export interface FichaTercero {
  tercero: Tercero;
  roles: RolTercero[];
  clasificaciones: { clasificacion_id: string; nombre: string; principal: boolean }[];
  /** Contratos en los que participa, con rol y vigencia. Navega, no suma importes. */
  uso: { contrato_id: string; contrato_nombre: string; rol: RolParticipante; desde: string; hasta: string | null }[];
}

export interface ClasificacionTercero {
  clasificacion_id: string;
  nombre: string;
  enabled: boolean;
  padre_id: string | null;
}

export interface ResultadoContrato {
  contrato_id: string;
  row_version: number;
  idempotente: boolean;
  contrato: ContratoDetalle;
}

export interface ResultadoServicio {
  servicio_id: string;
  row_version: number;
  idempotente: boolean;
}

export interface ResultadoTercero {
  tercero: Tercero;
  idempotente: boolean;
}

export interface SolapadoDetalle {
  id: string;
  nombre: string;
  tipo: TipoContrato;
  habitacion: number | null;
  desde: string;
  hasta: string | null;
}

export interface ClienteContratos {
  // L-CON-01..03, L-SRV-01
  contratosDePropiedad(propiedadId: string): Promise<Respuesta<ContratosPropiedad>>;
  contrato(contratoId: string): Promise<Respuesta<{ contrato: ContratoDetalle }>>;
  propuestaContrato(propiedadId: string, q: { tipo: TipoContrato; habitacion?: number | null; inicio: string; inquilinoId?: string | null }): Promise<Respuesta<PropuestaContrato>>;
  serviciosDePropiedad(propiedadId: string): Promise<Respuesta<ServiciosPropiedad>>;
  // C-CON-01..06, C-REV-01
  altaContrato(p: PayloadAltaContrato): Promise<Respuesta<ResultadoContrato>>;
  editarContrato(id: string, p: PayloadEditarContrato): Promise<Respuesta<ResultadoContrato>>;
  terminarContrato(id: string, p: PayloadTerminar): Promise<Respuesta<ResultadoContrato>>;
  formalizarContrato(id: string, p: { intencion_id: string; row_version_esperada: number }): Promise<Respuesta<ResultadoContrato>>;
  cancelarContrato(id: string, p: { intencion_id: string; row_version_esperada: number; motivo: string }): Promise<Respuesta<ResultadoContrato>>;
  sucesorContrato(id: string, p: PayloadSucesor): Promise<Respuesta<ResultadoContrato>>;
  anadirPersona(id: string, p: { intencion_id: string; row_version_esperada: number; actor: ActorWire; rol: RolParticipante; principal: boolean; desde: string }): Promise<Respuesta<ResultadoContrato>>;
  cerrarPersona(id: string, personaId: string, p: { intencion_id: string; row_version_esperada: number; hasta: string; nuevo_principal?: string | null }): Promise<Respuesta<ResultadoContrato>>;
  nuevaClausula(id: string, p: { intencion_id: string; row_version_esperada: number; desde: string; clausula: ClausulaWire }): Promise<Respuesta<ResultadoContrato>>;
  // C-SRV-01..04
  altaServicio(p: PayloadServicio): Promise<Respuesta<ResultadoServicio>>;
  editarServicio(id: string, p: { intencion_id: string; row_version_esperada: number; nombre?: string; categoria_default_id?: string | null; notas?: string | null }): Promise<Respuesta<ResultadoServicio>>;
  bajaServicio(id: string, p: { intencion_id: string; row_version_esperada: number; fecha_fin_real: string }): Promise<Respuesta<ResultadoServicio>>;
  tratamientoServicio(contratoId: string, servicioId: string, p: { intencion_id: string; row_version_esperada: number; tratamiento: TratamientoWire }): Promise<Respuesta<ResultadoContrato>>;
  // Terceros: L-TER-01, C-TER-01, C-TER-03, selector con «uso en Gapto» (V-bis)
  fichaTercero(terceroId: string): Promise<Respuesta<FichaTercero>>;
  anadirRoles(terceroId: string, p: PayloadAnadirRoles): Promise<Respuesta<ResultadoTercero>>;
  anadirClasificacion(terceroId: string, p: PayloadAnadirClasificacion): Promise<Respuesta<ResultadoTercero>>;
  clasificacionesTercero(): Promise<Respuesta<{ clasificaciones: ClasificacionTercero[] }>>;
  tercerosParaContrato(q: string): Promise<Respuesta<{ terceros: TerceroParaContrato[] }>>;
}

const PROP = (id: string) => `/v1/propiedades/${encodeURIComponent(id)}`;
const CON = (id: string) => `/v1/contratos/${encodeURIComponent(id)}`;
const SRV = (id: string) => `/v1/servicios/${encodeURIComponent(id)}`;
const TER = (id: string) => `/v1/terceros/${encodeURIComponent(id)}`;
const post = (cuerpo: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(cuerpo) });
const GET: RequestInit = { method: 'GET' };

export function crearClienteContratos(cfg: ConfigApi, fetchImpl: typeof fetch = fetch): ClienteContratos {
  const llamar = crearLlamada(cfg, fetchImpl);
  return {
    contratosDePropiedad: (id) => llamar(`${PROP(id)}/contratos`, GET, false),
    contrato: (id) => llamar(CON(id), GET, false),
    propuestaContrato: (id, q) => {
      const ps = new URLSearchParams({ tipo: q.tipo, inicio: q.inicio });
      if (q.habitacion != null) ps.set('habitacion', String(q.habitacion));
      if (q.inquilinoId) ps.set('inquilino_id', q.inquilinoId);
      return llamar(`${PROP(id)}/contratos/propuesta?${ps.toString()}`, GET, false);
    },
    serviciosDePropiedad: (id) => llamar(`${PROP(id)}/servicios`, GET, false),
    altaContrato: (p) => llamar('/v1/intenciones/contrato-alquiler', post(p), 'CAMBIO'),
    editarContrato: (id, p) => llamar(`${CON(id)}/editar`, post(p), 'CAMBIO'),
    terminarContrato: (id, p) => llamar(`${CON(id)}/terminar`, post(p), 'CAMBIO'),
    formalizarContrato: (id, p) => llamar(`${CON(id)}/formalizar`, post(p), 'CAMBIO'),
    cancelarContrato: (id, p) => llamar(`${CON(id)}/cancelar`, post(p), 'CAMBIO'),
    sucesorContrato: (id, p) => llamar(`${CON(id)}/sucesor`, post(p), 'CAMBIO'),
    anadirPersona: (id, p) => llamar(`${CON(id)}/personas`, post(p), 'CAMBIO'),
    cerrarPersona: (id, personaId, p) => llamar(`${CON(id)}/personas/${encodeURIComponent(personaId)}/cerrar`, post(p), 'CAMBIO'),
    nuevaClausula: (id, p) => llamar(`${CON(id)}/clausula`, post(p), 'CAMBIO'),
    altaServicio: (p) => llamar('/v1/intenciones/servicio', post(p), 'CAMBIO'),
    editarServicio: (id, p) => llamar(`${SRV(id)}/editar`, post(p), 'CAMBIO'),
    bajaServicio: (id, p) => llamar(`${SRV(id)}/baja`, post(p), 'CAMBIO'),
    tratamientoServicio: (contratoId, servicioId, p) => llamar(`${CON(contratoId)}/servicios/${encodeURIComponent(servicioId)}`, post(p), 'CAMBIO'),
    fichaTercero: (id) => llamar(TER(id), GET, false),
    anadirRoles: (id, p) => llamar(`${TER(id)}/roles`, post(p), 'CAMBIO'),
    anadirClasificacion: (id, p) => llamar(`${TER(id)}/clasificaciones`, post(p), 'CAMBIO'),
    clasificacionesTercero: () => llamar('/v1/clasificaciones-tercero', GET, false),
    tercerosParaContrato: (q) => llamar(`/v1/terceros/asistente-contratos?q=${encodeURIComponent(q)}`, GET, false),
  };
}
