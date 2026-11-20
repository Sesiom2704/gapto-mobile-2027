// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_fixtures.ts
// Ruta: mobile/__tests__/contratos_fixtures.ts
// Descripción: Datos y dobles en memoria de las suites de F06-02/03 (contratos, servicios y terceros; lámina CON v0.8). Escenario O-1b (A1 validada): ficha de 5 habitaciones, hoy = 2026-11-18, sin renta. Datos ficticios. El doble del cliente registra cada llamada y devuelve respuestas configurables; el servidor real lo escribe otro agente con el mismo contrato (N1 v1.1), por eso aquí solo se fija el DTO del contrato.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import type { ClienteApi, Respuesta, Tercero } from '../src/api/cliente';
import type {
  ClienteContratos, ContratoDetalle, ContratosPropiedad, FichaTercero, FilaContrato, PersonaContrato, ServiciosPropiedad, TerceroParaContrato,
} from '../src/api/contratos';
import type { VistaPropiedad } from '../src/api/propiedades';

export const HOY = '2026-11-18';
export const AHORA = () => new Date(2026, 10, 18, 10);
export const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
export const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
export const rechazo = <T,>(codigo: string, mensaje = '', detalle?: Record<string, unknown>) => ({ tipo: 'RECHAZADO', codigo, mensaje, ...(detalle ? { detalle } : {}) }) as Respuesta<T>;
export const indeterminado = <T,>() => ({ tipo: 'INDETERMINADO', mensaje: 'x' }) as Respuesta<T>;

let n = 0;
export const reiniciarIds = () => { n = 0; };
export const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

export const YO = 'f0000000-0000-4000-8000-0000000000ff';
export const T_LAURA = 't0000000-0000-4000-8000-000000000001';
export const T_ELENA = 't0000000-0000-4000-8000-000000000002';
export const T_CARLOS = 't0000000-0000-4000-8000-000000000003';
export const T_CARLOS2 = 't0000000-0000-4000-8000-000000000004';
export const T_AGENCIA = 't0000000-0000-4000-8000-000000000005';

export function vista(p: Partial<VistaPropiedad> = {}): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: 5, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: HOY,
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  } as VistaPropiedad;
}

export const fila = (p: Partial<FilaContrato> & Pick<FilaContrato, 'contrato_id' | 'nombre'>): FilaContrato => ({
  tipo: 'HABITACION', habitacion: 1, estado_documental: 'FORMALIZADO', situacion: 'VIGENTE', fecha_inicio: '2026-09-01', fecha_fin_prevista: null,
  fecha_fin_real: null, fin_previsto_vencido: false, inquilino_principal: null, renta_registrada: false, ...p,
});

/** O-1b · escenario A1 validado: 3 ocupadas (HAB1, HAB2, HAB5), 1 próxima (HAB3), 1 libre (HAB4: borrador), 2 finalizados. */
export function escenarioA1(): ContratosPropiedad {
  return {
    hoy: HOY,
    habitaciones_ficha: 5,
    ocupacion: [
      { habitacion: 1, estado: 'OCUPADA', hasta: null, desde: '2026-09-01', contrato_id: 'c1' },
      { habitacion: 2, estado: 'OCUPADA', hasta: '2027-08-31', desde: '2026-03-01', contrato_id: 'c2' },
      { habitacion: 3, estado: 'PROXIMA', hasta: null, desde: '2026-12-01', contrato_id: 'c3' },
      { habitacion: 4, estado: 'LIBRE', hasta: null, desde: null, contrato_id: null },
      { habitacion: 5, estado: 'OCUPADA', hasta: null, desde: '2025-11-01', contrato_id: 'c5' },
    ],
    contratos: [
      fila({ contrato_id: 'c1', nombre: '26-HAB1-CR', habitacion: 1, inquilino_principal: 'Carlos Ruiz', fecha_inicio: '2026-09-01' }),
      fila({ contrato_id: 'c2', nombre: '26-HAB2-AG', habitacion: 2, inquilino_principal: 'Ana Gil', fecha_inicio: '2026-03-01', fecha_fin_prevista: '2027-08-31' }),
      fila({ contrato_id: 'c5', nombre: '25-HAB5-LM', habitacion: 5, inquilino_principal: 'Luis Mora', fecha_inicio: '2025-11-01', fecha_fin_prevista: '2026-10-31', fin_previsto_vencido: true }),
      fila({ contrato_id: 'c3', nombre: '26-HAB3-PR', habitacion: 3, situacion: 'PROXIMO', inquilino_principal: 'Pablo Ros', fecha_inicio: '2026-12-01' }),
      fila({ contrato_id: 'c4', nombre: '26-HAB4-ES', habitacion: 4, estado_documental: 'BORRADOR', situacion: 'BORRADOR', inquilino_principal: 'Elena Sanz', fecha_inicio: '2026-11-01' }),
      fila({ contrato_id: 'f1', nombre: '25-HAB1-XX', habitacion: 1, situacion: 'FINALIZADO', fecha_inicio: '2025-01-01', fecha_fin_real: '2025-12-31' }),
      fila({ contrato_id: 'f2', nombre: '25-HAB2-YY', habitacion: 2, situacion: 'FINALIZADO', fecha_inicio: '2025-01-01', fecha_fin_real: '2026-02-28' }),
    ],
  };
}

const persona = (p: Partial<PersonaContrato> & Pick<PersonaContrato, 'persona_id' | 'rol'>): PersonaContrato => ({
  actor: { yo: false, tercero_id: null, nombre: null }, principal: false, vigente_desde: '2026-09-01', vigente_hasta: null, ...p,
});

export function detalle(p: Partial<ContratoDetalle> = {}): ContratoDetalle {
  return {
    contrato_id: 'c1', row_version: 3, nombre: '26-HAB1-CR', propiedad_id: 'p1', propiedad_nombre: 'Piso Ejemplo', tipo: 'HABITACION', habitacion: 1,
    estado_documental: 'FORMALIZADO', situacion: 'VIGENTE', fecha_inicio: '2026-09-01', fecha_fin_prevista: '2027-08-31', fecha_fin_real: null,
    fin_previsto_vencido: false, notas: null, renta_registrada: false,
    personas: [
      persona({ persona_id: 'pp1', rol: 'PROPIETARIO', principal: true, actor: { yo: true, tercero_id: null, nombre: null } }),
      persona({ persona_id: 'pp2', rol: 'PROPIETARIO', actor: { yo: false, tercero_id: T_LAURA, nombre: 'Laura Pérez' } }),
      persona({ persona_id: 'pp3', rol: 'INQUILINO', principal: true, actor: { yo: false, tercero_id: T_CARLOS, nombre: 'Carlos Ruiz' } }),
      persona({ persona_id: 'pp4', rol: 'AVALISTA', actor: { yo: false, tercero_id: 't-marta', nombre: 'Marta Ruiz' } }),
      persona({ persona_id: 'pp5', rol: 'AGENCIA', actor: { yo: false, tercero_id: T_AGENCIA, nombre: 'Inmobiliaria Centro' } }),
    ],
    clausula: { version_id: 'v1', tipo: 'IPC', indice_referencia: 'IPC INE', periodicidad_meses: 12, fecha_primera_revision: '2027-09-01', porcentaje_fijo: null, vigente_desde: '2026-09-01', vigente_hasta: null },
    servicios: [
      { servicio_id: 's-int', servicio_nombre: 'Internet', tipo_servicio: 'INTERNET', modo: 'INCLUIDO', actor_nombre: null, porcentaje: null, vigente_desde: '2026-09-01', vigente_hasta: null },
      { servicio_id: 's-luz', servicio_nombre: 'Luz', tipo_servicio: 'LUZ', modo: 'POR_FACTURA', actor_nombre: 'Carlos Ruiz', porcentaje: null, vigente_desde: '2026-09-01', vigente_hasta: null },
    ],
    terminable: { terminable: true, motivo: null },
    ...p,
  };
}

export function servicios(): ServiciosPropiedad {
  const base = { categoria_default_id: null, categoria_default_nombre: null, hasta: null, row_version: 1, compania_ultimos_pagos: 'Eléctrica Sur', tratamientos: [] };
  return {
    vigentes: [
      { ...base, servicio_id: 's-luz', nombre: 'Luz', tipo_servicio: 'LUZ', desde: '2027-03-01' },
      { ...base, servicio_id: 's-int', nombre: 'Internet', tipo_servicio: 'INTERNET', desde: '2027-03-01' },
      { ...base, servicio_id: 's-agua', nombre: 'Agua', tipo_servicio: 'AGUA', desde: '2027-03-01' },
    ],
    anteriores: [{ ...base, servicio_id: 's-gas', nombre: 'Gas', tipo_servicio: 'GAS', desde: '2025-01-01', hasta: '2026-01-31' }],
  };
}

export const tercero = (id: string, nombre: string, p: Partial<Tercero> = {}): Tercero => ({ id, nombre, naturaleza: 'PERSONA', enabled: true, row_version: 1, ...p });
export const terceroUso = (id: string, nombre: string, uso: TerceroParaContrato['uso'], p: Partial<Tercero> = {}): TerceroParaContrato => ({ ...tercero(id, nombre, p), uso });

export function ficha(p: Partial<FichaTercero> = {}): FichaTercero {
  return {
    tercero: tercero(T_CARLOS, 'Carlos Ruiz', { row_version: 4 }),
    roles: ['INQUILINO'],
    clasificaciones: [],
    uso: [{ contrato_id: 'c1', contrato_nombre: '26-HAB1-CR', rol: 'INQUILINO', desde: '2026-09-01', hasta: null }],
    ...p,
  };
}

/** Doble del cliente de contratos: cada método es un `jest.fn` con una respuesta por defecto y sobrescribible. */
export function clienteContratos(sobre: Partial<Record<keyof ClienteContratos, unknown>> = {}): jest.Mocked<ClienteContratos> {
  const res = (c: ContratoDetalle = detalle()) => ok({ contrato_id: c.contrato_id, row_version: c.row_version + 1, idempotente: false, contrato: c });
  const base: Record<string, unknown> = {
    contratosDePropiedad: jest.fn(async () => ok(escenarioA1())),
    contrato: jest.fn(async () => ok({ contrato: detalle() })),
    propuestaContrato: jest.fn(async () => ok({
      nombre_propuesto: '26-HAB4-ES',
      arrendadores: [{ actor_id: YO, yo: true, tercero_id: null, nombre: null }, { actor_id: T_LAURA, yo: false, tercero_id: T_LAURA, nombre: 'Laura Pérez' }],
      habitaciones: [],
    })),
    serviciosDePropiedad: jest.fn(async () => ok(servicios())),
    altaContrato: jest.fn(async () => res(detalle({ contrato_id: 'nuevo', nombre: '26-HAB4-ES' }))),
    editarContrato: jest.fn(async () => res()),
    terminarContrato: jest.fn(async () => res(detalle({ fecha_fin_real: '2027-01-31', situacion: 'FINALIZADO' }))),
    formalizarContrato: jest.fn(async () => res()),
    cancelarContrato: jest.fn(async () => res(detalle({ estado_documental: 'CANCELADO', situacion: 'CANCELADO' }))),
    sucesorContrato: jest.fn(async () => res(detalle({ contrato_id: 'sucesor', nombre: '27-HAB1-NN' }))),
    anadirPersona: jest.fn(async () => res()),
    cerrarPersona: jest.fn(async () => res()),
    nuevaClausula: jest.fn(async () => res()),
    altaServicio: jest.fn(async () => ok({ servicio_id: 'nuevo-srv', row_version: 1, idempotente: false })),
    editarServicio: jest.fn(async () => ok({ servicio_id: 's-luz', row_version: 2, idempotente: false })),
    bajaServicio: jest.fn(async () => ok({ servicio_id: 's-luz', row_version: 2, idempotente: false })),
    tratamientoServicio: jest.fn(async () => res()),
    fichaTercero: jest.fn(async () => ok(ficha())),
    anadirRoles: jest.fn(async (id: string) => ok({ tercero: tercero(id, 'x', { row_version: 5 }), idempotente: false })),
    anadirClasificacion: jest.fn(async (id: string) => ok({ tercero: tercero(id, 'x', { row_version: 5 }), idempotente: false })),
    clasificacionesTercero: jest.fn(async () => ok({ clasificaciones: [{ clasificacion_id: 'k1', nombre: 'Familia de inquilinos', enabled: true, padre_id: null }, { clasificacion_id: 'k2', nombre: 'Proveedores', enabled: true, padre_id: null }] })),
    tercerosParaContrato: jest.fn(async () => ok({ terceros: [] })),
  };
  return { ...base, ...sobre } as unknown as jest.Mocked<ClienteContratos>;
}

/** Doble mínimo de `ClienteApi` para el `SelectorTercero` existente (V-ter): solo lo que usa la hoja de duplicados. */
export function clienteApi(sobre: Record<string, unknown> = {}): ClienteApi {
  return {
    listarTerceros: jest.fn(async () => ok({ terceros: [] })),
    candidatosTercero: jest.fn(async () => ok({ terceros: [] })),
    altaTercero: jest.fn(async (c: { id: string; nombre: string }) => ok({ tercero: tercero(c.id, c.nombre, { naturaleza: null }), idempotente: false })),
    reactivarTercero: jest.fn(async (id: string) => ok({ tercero: tercero(id, 'Carlos Ruiz', { enabled: true }), idempotente: false })),
    buscarTerceros: jest.fn(async () => ok({ terceros: [] })),
    senalesTerceros: jest.fn(async () => ok({ terceros: [] })),
    arbolCategorias: jest.fn(async () => ok({ categorias: [] })),
    ...sobre,
  } as unknown as ClienteApi;
}
