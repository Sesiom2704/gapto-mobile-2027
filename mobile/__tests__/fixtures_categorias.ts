// ============================================================
// GAPTO MOBILE 2027
// Fichero: fixtures_categorias.ts
// Ruta: mobile/__tests__/fixtures_categorias.ts
// Descripción: Fixtures sintéticos del árbol de categorías para los tests del cliente (no es un fichero de test: no casa con testMatch). Incluye el estado «padre desactivado con hijo activo», inalcanzable por la API (AJ-S4-03) y cubierto aquí por fixture (F05 §26.4).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S7-MAG UI): `mag()` rellena `asociacion_id` (por defecto `a-<magnitud_id>`); el stub incluye el catálogo (vacío por defecto) y los comandos de magnitudes (no esperados por defecto).
// Versión: 0.3.0 (F05-02 B2): el stub incluye las preferencias de registro: propuesta SIN propuesta y lista vacía por defecto; alta y edición no esperadas. `propuestaUnica(cuenta)` emula al resolver con una única cuenta elegible (DEFAULT_GENERAL): sustituye al antiguo fallback del cliente (AJ-B1-09).
// Versión: 0.4.0 (F05-02 B3): el stub incluye desactivar y reactivar preferencia (no esperados por defecto).
// Versión: 0.5.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3): la lista de preferencias del stub informa `tipos` (ids de GASTO e INGRESO).
// Versión: 0.6.0 (F05-03/F05-04 J2 §2): el stub incluye los métodos nuevos del cliente: lecturas vacías por defecto (terceros, contextos, plantillas, cuentas elegibles, propuesta del registro sin valores) y escrituras no esperadas (lanzan).
// Versión: 0.8.0 (F05-06 M4 F2): el stub incluye las capacidades de cuenta: lista vacía y 0 sin configurar por defecto (el aviso B2 no aparece); detalle, historial, impacto y cambio no esperados (lanzan).
// Versión: 0.9.0 (F05-06 M2-B): el stub incluye la devolución contextual: contexto, devolución y abono no esperados (lanzan).
// Versión: 0.7.0 (F05-05 K3): el stub incluye los métodos de F05-05: señales, búsqueda de terceros, afinidades del tercero, Actividad (página vacía) e Inicio (nombre null y Resultado a cero) por defecto; alta y retirada de afinidad y detalle de la Actividad no esperados (lanzan).
// Versión: 0.10.0 (F05-06 M3 §B2): el stub incluye reparto y posiciones: «Pendiente con» sin posiciones y un reparto no corregible (SIN_REPARTO) por defecto; gasto compartido, cobro, pago, perdón y corrección no esperados (lanzan).
// ============================================================

import type { ClienteApi, ListaPreferencias, PropuestaRegistro, Respuesta } from '../src/api/cliente';
import type { CategoriaNodo, MagnitudCategoria } from '../src/domain/categoria';

export function mag(p: Partial<MagnitudCategoria> & { magnitud_id: string }): MagnitudCategoria {
  return { asociacion_id: `a-${p.magnitud_id}`, nombre: 'Consumo', obligatoria: true, orden: 0, enabled: true, unidad_default: 'kWh', precision_decimales: 2, row_version: 1, ...p };
}

export function nodo(p: Partial<CategoriaNodo> & { id: string; nombre: string }): CategoriaNodo {
  return {
    parent_id: null, codigo: null, ambito: 'GASTO', enabled: true, orden: 0, icon_key: null, presupuestable_default: true,
    row_version: 1, magnitudes: [], capturable: true, motivo_no_capturable: null, ...p,
  };
}

// Fixture: incluye «padre desactivado con hijo activo» (inalcanzable por API; AJ-S4-03).
export const LISTA: CategoriaNodo[] = [
  nodo({ id: 'hogar', nombre: 'Hogar', icon_key: 'hogar.casa' }),
  nodo({ id: 'luz', nombre: 'Luz', parent_id: 'hogar', icon_key: 'hogar.luz', magnitudes: [mag({ magnitud_id: 'kwh', nombre: 'Consumo eléctrico' })] }),
  nodo({ id: 'agua', nombre: 'Agua', parent_id: 'hogar', orden: 1, magnitudes: [mag({ magnitud_id: 'm3', nombre: 'Consumo de agua', obligatoria: false, unidad_default: 'm3', precision_decimales: 3 })] }),
  nodo({ id: 'gas', nombre: 'Gas', parent_id: 'hogar', orden: 2, capturable: false, motivo_no_capturable: 'MAGNITUD_OBLIGATORIA_NO_DISPONIBLE', magnitudes: [mag({ magnitud_id: 'kwhgas', nombre: 'Consumo de gas', enabled: false })] }),
  nodo({ id: 'trabajo', nombre: 'Trabajo', ambito: 'INGRESO', orden: 1 }),
  nodo({ id: 'nomina', nombre: 'Nómina', ambito: 'INGRESO', parent_id: 'trabajo' }),
  nodo({ id: 'prof', nombre: 'Gastos profesionales', parent_id: 'trabajo', orden: 1 }),
  nodo({ id: 'ocio', nombre: 'Ocio', enabled: false, orden: 2 }),
  nodo({ id: 'cine', nombre: 'Cine', parent_id: 'ocio' }),
  nodo({ id: 'viejo', nombre: 'Viajes 2025', enabled: false, orden: 3 }),
];

/** Métodos de categorías de un cliente simulado. Por defecto el árbol es `lista` y los comandos no se esperan (lanzan). */
export function clienteCategoriasStub(
  lista: CategoriaNodo[] = [],
): Omit<ClienteApi, 'registrarGastoPagado' | 'cuentasPago' | 'gastoMes'> {
  const noEsperado = (nombre: string) => jest.fn(async () => { throw new Error(`llamada no esperada: ${nombre}`); });
  return {
    arbolCategorias: jest.fn(async () => ({ tipo: 'OK', datos: { categorias: lista } }) as Respuesta<{ categorias: CategoriaNodo[] }>),
    usoCategoria: noEsperado('usoCategoria'),
    crearCategoria: noEsperado('crearCategoria'),
    iconoCategoria: noEsperado('iconoCategoria'),
    renombrarCategoria: noEsperado('renombrarCategoria'),
    moverCategoria: noEsperado('moverCategoria'),
    desactivarCategoria: noEsperado('desactivarCategoria'),
    reactivarCategoria: noEsperado('reactivarCategoria'),
    cambiarAmbitoCategoria: noEsperado('cambiarAmbitoCategoria'),
    reordenarCategorias: noEsperado('reordenarCategorias'),
    catalogoMagnitudes: jest.fn(async () => ({ tipo: 'OK', datos: { magnitudes: [] } }) as Respuesta<{ magnitudes: never[] }>),
    asociarMagnitud: noEsperado('asociarMagnitud'),
    obligatoriaMagnitud: noEsperado('obligatoriaMagnitud'),
    retirarMagnitud: noEsperado('retirarMagnitud'),
    reordenarMagnitudes: noEsperado('reordenarMagnitudes'),
    renombrarMagnitud: noEsperado('renombrarMagnitud'),
    deshabilitarMagnitud: noEsperado('deshabilitarMagnitud'),
    rehabilitarMagnitud: noEsperado('rehabilitarMagnitud'),
    propuestaPreferencias: jest.fn(async () => ({ tipo: 'OK', datos: { cuenta: null, presupuestable: null } }) as Respuesta<PropuestaRegistro>),
    listarPreferencias: jest.fn(
      async () => ({ tipo: 'OK', datos: { preferencias: [], tipos: { GASTO: 't-gasto', INGRESO: 't-ingreso' } } }) as Respuesta<ListaPreferencias>,
    ),
    altaPreferencia: noEsperado('altaPreferencia'),
    editarPreferencia: noEsperado('editarPreferencia'),
    desactivarPreferencia: noEsperado('desactivarPreferencia'),
    reactivarPreferencia: noEsperado('reactivarPreferencia'),
    cuentasElegibles: jest.fn(async (operacion: any) => ({ tipo: 'OK', datos: { operacion, cuentas: [] } }) as any),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [] } }) as any),
    candidatosTercero: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [] } }) as any),
    altaTercero: noEsperado('altaTercero'),
    editarTercero: noEsperado('editarTercero'),
    desactivarTercero: noEsperado('desactivarTercero'),
    reactivarTercero: noEsperado('reactivarTercero'),
    listarContextos: jest.fn(async () => ({ tipo: 'OK', datos: { contextos: [] } }) as any),
    altaContexto: noEsperado('altaContexto'),
    editarContexto: noEsperado('editarContexto'),
    desactivarContexto: noEsperado('desactivarContexto'),
    reactivarContexto: noEsperado('reactivarContexto'),
    listarPlantillas: jest.fn(async () => ({ tipo: 'OK', datos: { plantillas: [], acciones: [] } }) as any),
    altaPlantilla: noEsperado('altaPlantilla'),
    editarPlantilla: noEsperado('editarPlantilla'),
    desactivarPlantilla: noEsperado('desactivarPlantilla'),
    reactivarPlantilla: noEsperado('reactivarPlantilla'),
    altaAccion: noEsperado('altaAccion'),
    editarAccion: noEsperado('editarAccion'),
    desactivarAccion: noEsperado('desactivarAccion'),
    reordenarAcciones: noEsperado('reordenarAcciones'),
    propuestaRegistro: jest.fn(async (q: any) => ({ tipo: 'OK', datos: { tipo: q.tipo, campos: { categoria: null, tercero: null, contexto: null, cuenta: null, presupuestable: null }, avisos: [] } }) as any),
    registrarIngresoCobrado: noEsperado('registrarIngresoCobrado'),
    registrarTransferencia: noEsperado('registrarTransferencia'),
    categoriasSugeridas: jest.fn(async () => ({ tipo: 'OK', datos: { version: 1, nodos: [] } }) as any),
    onboardingCategorias: noEsperado('onboardingCategorias'),
    senalesCategorias: jest.fn(async (q: any) => ({ tipo: 'OK', datos: { tipo: q.tipo, fecha: q.fecha, tercero_id: q.terceroId ?? null, candidatas: [] } }) as any),
    senalesTerceros: jest.fn(async (tipo: any, fecha: any) => ({ tipo: 'OK', datos: { tipo, fecha, terceros: [] } }) as any),
    buscarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [] } }) as any),
    afinidadesTercero: jest.fn(async (terceroId: any, _f: any, tipo: any = 'GASTO') => ({ tipo: 'OK', datos: { tercero_id: terceroId, tipo, guardadas: [], segun_historial: [], total_registros: 0 } }) as any),
    altaAfinidad: noEsperado('altaAfinidad'),
    retirarAfinidad: noEsperado('retirarAfinidad'),
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [], siguiente: null, total: 0 } }) as any),
    detalleActividad: noEsperado('detalleActividad'),
    yo: jest.fn(async () => ({ tipo: 'OK', datos: { nombre: null } }) as any),
    resultadoMes: jest.fn(async () => ({ tipo: 'OK', datos: { mes: '2026-10', moneda: 'EUR', ingresos_propios: '0.00', gastos_propios: '0.00', resultado: '0.00', sin_indicar: { gastos: { n: 0, importe: '0.00' }, ingresos: { n: 0, importe: '0.00' } } } }) as any),
    listarCapacidades: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [], sin_configurar: 0 } }) as any),
    cuentasSinConfigurar: jest.fn(async () => ({ tipo: 'OK', datos: { sin_configurar: 0 } }) as any),
    detalleCapacidades: noEsperado('detalleCapacidades'),
    historialCapacidades: noEsperado('historialCapacidades'),
    impactoCapacidad: noEsperado('impactoCapacidad'),
    cambiarCapacidad: noEsperado('cambiarCapacidad'),
    contextoDevolucion: noEsperado('contextoDevolucion'),
    registrarDevolucion: noEsperado('registrarDevolucion'),
    registrarAbono: noEsperado('registrarAbono'),
    registrarGastoCompartido: noEsperado('registrarGastoCompartido'),
    pendienteCon: jest.fn(async (id: string) => ({ tipo: 'OK', datos: { tercero_id: id, nombre: '', te_debe: null, le_debes: null, neto: null, neto_estado: 'SIN_POSICIONES', posiciones: [] } }) as any),
    cobrarPosicion: noEsperado('cobrarPosicion'),
    pagarPosicion: noEsperado('pagarPosicion'),
    perdonarPosicion: noEsperado('perdonarPosicion'),
    repartoDeHecho: jest.fn(async (id: string) => ({ tipo: 'OK', datos: { hecho_id: id, row_version: 1, importe: '0.00', estado_atribucion: 'NO_DISPONIBLE', corregible: false, motivo: 'SIN_REPARTO', partes: [] } }) as any),
    corregirReparto: noEsperado('corregirReparto'),
  };
}

/** Resolver con una única cuenta elegible: propuesta DEFAULT_GENERAL de esa cuenta, sin presupuestable (E1). */
export function propuestaUnica(cuenta: string) {
  return jest.fn(
    async () => ({ tipo: 'OK', datos: { cuenta: { valor: cuenta, origen: { capa: 'DEFAULT_GENERAL', preferencia_id: null } }, presupuestable: null } }) as Respuesta<PropuestaRegistro>,
  );
}
