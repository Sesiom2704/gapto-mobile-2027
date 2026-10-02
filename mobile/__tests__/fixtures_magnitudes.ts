// ============================================================
// GAPTO MOBILE 2027
// Fichero: fixtures_magnitudes.ts
// Ruta: mobile/__tests__/fixtures_magnitudes.ts
// Descripción: Fixtures sintéticos de S7-MAG para los tests del cliente (no es un fichero de test: no casa con testMatch). Árbol de categorías con asociaciones (Luz: obligatoria + opcional; Gas: obligatoria deshabilitada; Agua: opcional) y catálogo del owner con una magnitud sin categorías y una deshabilitada; cliente simulado con árbol y catálogo mutables y comandos espiables.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import type { MagnitudCatalogo } from '../src/domain/magnitud';

import { clienteCategoriasStub, LISTA, mag } from './fixtures_categorias';

export const KWH = mag({ magnitud_id: 'kwh', asociacion_id: 'a-kwh', nombre: 'Consumo eléctrico', obligatoria: true, orden: 0 });
export const POT = mag({ magnitud_id: 'pot', asociacion_id: 'a-pot', nombre: 'Potencia contratada', obligatoria: false, orden: 1, unidad_default: 'kW', precision_decimales: 1 });

/** LISTA de categorías con Luz llevando dos asociaciones (obligatoria + opcional). */
export const LISTA_MAG: CategoriaNodo[] = LISTA.map((n) => (n.id === 'luz' ? { ...n, magnitudes: [KWH, POT] } : n));

export function cat(m: Partial<MagnitudCatalogo> & { id: string; nombre: string }): MagnitudCatalogo {
  return { unidad_default: 'u', precision_decimales: 0, enabled: true, row_version: 1, categorias: [], n_hechos: 0, ...m };
}

export const CATALOGO: MagnitudCatalogo[] = [
  cat({ id: 'm3', nombre: 'Consumo de agua', unidad_default: 'm3', precision_decimales: 3, categorias: [{ categoria_id: 'agua', nombre: 'Agua', obligatoria: false, categoria_enabled: true }] }),
  cat({ id: 'kwh', nombre: 'Consumo eléctrico', unidad_default: 'kWh', precision_decimales: 2, n_hechos: 6, categorias: [{ categoria_id: 'luz', nombre: 'Luz', obligatoria: true, categoria_enabled: true }] }),
  cat({ id: 'kwhgas', nombre: 'Consumo de gas', unidad_default: 'kWh', precision_decimales: 2, enabled: false, categorias: [{ categoria_id: 'gas', nombre: 'Gas', obligatoria: true, categoria_enabled: true }] }),
  cat({ id: 'km', nombre: 'Kilómetros', unidad_default: 'km', precision_decimales: 1 }),
  cat({ id: 'pot', nombre: 'Potencia contratada', unidad_default: 'kW', precision_decimales: 1, n_hechos: 6, categorias: [{ categoria_id: 'luz', nombre: 'Luz', obligatoria: false, categoria_enabled: true }] }),
];

/** Cliente simulado: árbol y catálogo mutables; los comandos de magnitudes son jest.fn sobreescribibles. */
export function fakeMag(o: { lista?: CategoriaNodo[]; catalogo?: MagnitudCatalogo[] } = {}) {
  let lista = o.lista ?? LISTA_MAG;
  let catalogo = o.catalogo ?? CATALOGO;
  const base = clienteCategoriasStub(lista);
  const cliente: ClienteApi = {
    ...base,
    arbolCategorias: jest.fn(async () => ({ tipo: 'OK', datos: { categorias: lista } }) as Respuesta<{ categorias: CategoriaNodo[] }>),
    catalogoMagnitudes: jest.fn(async () => ({ tipo: 'OK', datos: { magnitudes: catalogo } }) as Respuesta<{ magnitudes: MagnitudCatalogo[] }>),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  };
  return {
    cliente,
    fijarArbol: (l: CategoriaNodo[]) => { lista = l; },
    fijarCatalogo: (c: MagnitudCatalogo[]) => { catalogo = c; },
  };
}

export const rechazo = (codigo: string, detalle?: Record<string, unknown>) =>
  ({ tipo: 'RECHAZADO' as const, codigo, mensaje: 'x', ...(detalle ? { detalle } : {}) });
