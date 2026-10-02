// ============================================================
// GAPTO MOBILE 2027
// Fichero: fixtures_categorias.ts
// Ruta: mobile/__tests__/fixtures_categorias.ts
// Descripción: Fixtures sintéticos del árbol de categorías para los tests del cliente (no es un fichero de test: no casa con testMatch). Incluye el estado «padre desactivado con hijo activo», inalcanzable por la API (AJ-S4-03) y cubierto aquí por fixture (F05 §26.4).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S7-MAG UI): `mag()` rellena `asociacion_id` (por defecto `a-<magnitud_id>`); el stub incluye el catálogo (vacío por defecto) y los comandos de magnitudes (no esperados por defecto).
// ============================================================

import type { ClienteApi, Respuesta } from '../src/api/cliente';
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
  };
}
