// ============================================================
// GAPTO MOBILE 2027
// Fichero: iconos_biblioteca.test.ts
// Ruta: mobile/__tests__/iconos_biblioteca.test.ts
// Descripción: Test cruzado BLOQUEANTE app ↔ backend de la biblioteca de iconos de categoría (F05 §27.2 Q4; F09 §12.97.9). Lee backend/app/categorias/iconos.py (la autoridad) y exige igualdad EXACTA de versión y del conjunto de claves publicadas con src/theme/iconosCategoria.ts; cada glifo (30 + reserva) debe existir en Ionicons.glyphMap de @expo/vector-icons. Si el fichero Python no existe, el test FALLA (nunca se omite). Además fija AJ-ICON-07: NULL y clave desconocida convergen en el glifo de reserva.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { Ionicons } from '@expo/vector-icons';

import {
  categoriaIconoFallback,
  glifoDe,
  ICONOS_CATEGORIA,
  ICONOS_CATEGORIA_VERSION,
  iconosActivosPorGrupo,
} from '../src/theme/iconosCategoria';

// Módulos de Node disponibles en Jest; tipado mínimo local para no añadir @types/node (patrón de ds_conformidad).
declare const __dirname: string;
declare const require: (m: string) => any;
const fs: { readFileSync(f: string, e: 'utf-8'): string; existsSync(f: string): boolean } = require('fs');
const path: { resolve(...p: string[]): string } = require('path');

const PY = path.resolve(__dirname, '../../backend/app/categorias/iconos.py');

function bibliotecaBackend(): { version: number; claves: Set<string> } {
  const texto = fs.readFileSync(PY, 'utf-8'); // lanza si no existe: fallo, no skip
  const version = /^ICONOS_CATEGORIA_VERSION\s*=\s*(\d+)\s*$/m.exec(texto);
  const bloque = /CLAVES_PUBLICADAS[^=]*=\s*frozenset\(\{([\s\S]*?)\}\)/.exec(texto);
  if (!version || !bloque) throw new Error('iconos.py sin ICONOS_CATEGORIA_VERSION o CLAVES_PUBLICADAS literal');
  const claves = new Set([...bloque[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]));
  return { version: Number(version[1]), claves };
}

test('el fichero de la autoridad existe', () => {
  expect(fs.existsSync(PY)).toBe(true);
});

test('versión y conjunto de claves idénticos a los del backend (Q4)', () => {
  const b = bibliotecaBackend();
  expect(ICONOS_CATEGORIA_VERSION).toBe(b.version);
  const app = new Set(ICONOS_CATEGORIA.map((i) => i.clave));
  expect(app.size).toBe(ICONOS_CATEGORIA.length); // sin claves repetidas
  expect([...app].sort()).toEqual([...b.claves].sort());
  expect(b.claves.size).toBe(30);
});

test('cada glifo (30 + reserva) existe en Ionicons.glyphMap', () => {
  const mapa = Ionicons.glyphMap as Record<string, number>;
  for (const i of ICONOS_CATEGORIA) expect(mapa[i.glifo]).toBeDefined();
  expect(categoriaIconoFallback).toBe('pricetag-outline');
  expect(mapa[categoriaIconoFallback]).toBeDefined();
});

test('AJ-ICON-07: NULL y clave desconocida convergen en la reserva, sin alias', () => {
  expect(glifoDe(null)).toBe(categoriaIconoFallback);
  expect(glifoDe(undefined)).toBe(categoriaIconoFallback);
  expect(glifoDe('bulb')).toBe(categoriaIconoFallback);
  expect(glifoDe('Hogar.luz')).toBe(categoriaIconoFallback);
  expect(glifoDe(' hogar.luz')).toBe(categoriaIconoFallback);
  expect(glifoDe('hogar.luz')).toBe('bulb-outline');
});

test('selector: seis grupos en orden y todas las activas agrupadas', () => {
  const g = iconosActivosPorGrupo();
  expect(g.map((x) => x.grupo)).toEqual(['Compras y comida', 'Hogar', 'Transporte y viajes', 'Salud y cuidado personal', 'Ocio', 'Finanzas']);
  expect(g.reduce((n, x) => n + x.iconos.length, 0)).toBe(30);
});
