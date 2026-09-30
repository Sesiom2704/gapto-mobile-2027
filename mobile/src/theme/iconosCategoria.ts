// ============================================================
// GAPTO MOBILE 2027
// Fichero: iconosCategoria.ts
// Ruta: mobile/src/theme/iconosCategoria.ts
// Descripción: Copia en la app de la biblioteca de iconos de categoría v1 (F09 §12.97.9; F05-D013 §27.2). El backend es la autoridad (backend/app/categorias/iconos.py); __tests__/iconos_biblioteca.test.ts compara versión y claves de forma BLOQUEANTE (Q4) y comprueba cada glifo contra Ionicons.glyphMap de @expo/vector-icons 15.0.2. Solo presentación: en PostgreSQL únicamente se guarda la clave (AJ-ICON-08). NULL y cualquier clave desconocida convergen en el icono de reserva `categoriaIconoFallback` (AJ-ICON-07): nunca falla, nunca iniciales, nunca herencia padre → hijo. Copia literal, sin alias.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import type { Ionicons } from '@expo/vector-icons';

export type Glifo = keyof typeof Ionicons.glyphMap;

export const ICONOS_CATEGORIA_VERSION = 1;

/** Grupos del selector de iconos (F09 §12.97.9, I02), en este orden. */
export const GRUPOS_ICONOS = [
  'Compras y comida',
  'Hogar',
  'Transporte y viajes',
  'Salud y cuidado personal',
  'Ocio',
  'Finanzas',
] as const;
export type GrupoIcono = (typeof GRUPOS_ICONOS)[number];

export interface IconoCategoria {
  clave: string;
  etiqueta: string;
  glifo: Glifo;
  grupo: GrupoIcono;
  activa: boolean;
}

/** Las 30 claves PUBLICADAS de la versión 1 (todas ACTIVAS en v1), en el orden de F09 §12.97.9. */
export const ICONOS_CATEGORIA: readonly IconoCategoria[] = [
  { clave: 'compras.carrito', etiqueta: 'Carrito', glifo: 'cart-outline', grupo: 'Compras y comida', activa: true },
  { clave: 'compras.cesta', etiqueta: 'Cesta', glifo: 'basket-outline', grupo: 'Compras y comida', activa: true },
  { clave: 'compras.ropa', etiqueta: 'Ropa', glifo: 'shirt-outline', grupo: 'Compras y comida', activa: true },
  { clave: 'comida.restaurante', etiqueta: 'Restaurante', glifo: 'restaurant-outline', grupo: 'Compras y comida', activa: true },
  { clave: 'comida.cafe', etiqueta: 'Café', glifo: 'cafe-outline', grupo: 'Compras y comida', activa: true },
  { clave: 'hogar.casa', etiqueta: 'Casa', glifo: 'home-outline', grupo: 'Hogar', activa: true },
  { clave: 'hogar.luz', etiqueta: 'Luz', glifo: 'bulb-outline', grupo: 'Hogar', activa: true },
  { clave: 'hogar.agua', etiqueta: 'Agua', glifo: 'water-outline', grupo: 'Hogar', activa: true },
  { clave: 'hogar.gas', etiqueta: 'Gas', glifo: 'flame-outline', grupo: 'Hogar', activa: true },
  { clave: 'hogar.internet', etiqueta: 'Internet', glifo: 'wifi-outline', grupo: 'Hogar', activa: true },
  { clave: 'hogar.reparaciones', etiqueta: 'Reparaciones', glifo: 'construct-outline', grupo: 'Hogar', activa: true },
  { clave: 'transporte.coche', etiqueta: 'Coche', glifo: 'car-outline', grupo: 'Transporte y viajes', activa: true },
  { clave: 'transporte.bus', etiqueta: 'Autobús', glifo: 'bus-outline', grupo: 'Transporte y viajes', activa: true },
  { clave: 'transporte.avion', etiqueta: 'Avión', glifo: 'airplane-outline', grupo: 'Transporte y viajes', activa: true },
  { clave: 'transporte.viaje', etiqueta: 'Viaje', glifo: 'briefcase-outline', grupo: 'Transporte y viajes', activa: true },
  { clave: 'salud.corazon', etiqueta: 'Salud', glifo: 'heart-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'salud.farmacia', etiqueta: 'Farmacia', glifo: 'medkit-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'salud.deporte', etiqueta: 'Deporte', glifo: 'barbell-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'personal.peluqueria', etiqueta: 'Peluquería', glifo: 'cut-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'personal.mascota', etiqueta: 'Mascota', glifo: 'paw-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'personal.educacion', etiqueta: 'Educación', glifo: 'school-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'personal.movil', etiqueta: 'Móvil', glifo: 'phone-portrait-outline', grupo: 'Salud y cuidado personal', activa: true },
  { clave: 'ocio.regalo', etiqueta: 'Regalo', glifo: 'gift-outline', grupo: 'Ocio', activa: true },
  { clave: 'ocio.libro', etiqueta: 'Libro', glifo: 'book-outline', grupo: 'Ocio', activa: true },
  { clave: 'ocio.musica', etiqueta: 'Música', glifo: 'musical-notes-outline', grupo: 'Ocio', activa: true },
  { clave: 'ocio.cine', etiqueta: 'Cine', glifo: 'film-outline', grupo: 'Ocio', activa: true },
  { clave: 'finanzas.dinero', etiqueta: 'Dinero', glifo: 'cash-outline', grupo: 'Finanzas', activa: true },
  { clave: 'finanzas.impuestos', etiqueta: 'Impuestos', glifo: 'document-text-outline', grupo: 'Finanzas', activa: true },
  { clave: 'finanzas.seguro', etiqueta: 'Seguro', glifo: 'shield-checkmark-outline', grupo: 'Finanzas', activa: true },
  { clave: 'finanzas.suscripcion', etiqueta: 'Suscripción', glifo: 'repeat-outline', grupo: 'Finanzas', activa: true },
];

/** Token único de reserva (F09 §12.97.5): NULL y clave desconocida. Nunca se persiste. */
export const categoriaIconoFallback: Glifo = 'pricetag-outline';

const PORCLAVE = new Map(ICONOS_CATEGORIA.map((i) => [i.clave, i]));

/** Icono publicado por clave exacta (sin recorte, sin mayúsculas, sin alias). */
export function iconoDe(iconKey: string | null | undefined): IconoCategoria | undefined {
  return iconKey == null ? undefined : PORCLAVE.get(iconKey);
}

/** Glifo a pintar: el de la clave publicada o el de reserva. Nunca lanza. */
export function glifoDe(iconKey: string | null | undefined): Glifo {
  return iconoDe(iconKey)?.glifo ?? categoriaIconoFallback;
}

/** Iconos ACTIVOS agrupados para el selector, en el orden de la biblioteca. */
export function iconosActivosPorGrupo(): { grupo: GrupoIcono; iconos: IconoCategoria[] }[] {
  return GRUPOS_ICONOS.map((grupo) => ({ grupo, iconos: ICONOS_CATEGORIA.filter((i) => i.activa && i.grupo === grupo) }));
}
