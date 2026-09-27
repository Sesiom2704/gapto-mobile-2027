// ============================================================
// GAPTO MOBILE 2027
// Fichero: ds_conformidad.test.ts
// Ruta: mobile/__tests__/ds_conformidad.test.ts
// Descripción: Guardas de conformidad con el Design System F09 (F05 — VS-01 · Alineación visual, condición A1 de la revisión): ningún color físico fuera de tokens.ts (DS-RULE-12) y conjunto de tokens de color cerrado respecto de DS-01 v1.0 + los derivados ya registrados (deuda F05-D003 §16.8).
// Versión: 0.1.0
// ============================================================

import { colores } from '../src/theme/tokens';

// Módulos de Node disponibles en Jest; tipado mínimo local para no añadir @types/node al proyecto.
declare const __dirname: string;
interface Entrada { name: string; isDirectory(): boolean }
const fs: { readdirSync(d: string, o: { withFileTypes: true }): Entrada[]; readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');

function ficheros(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e: Entrada) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? ficheros(p) : /\.(ts|tsx)$/.test(e.name) ? [p] : [];
  });
}

const RAIZ = path.join(__dirname, '..');
const COLOR_FISICO = /#[0-9A-Fa-f]{3,8}\b|rgba?\(|hsla?\(/;

test('DS-RULE-12: ningún color físico fuera de tokens.ts', () => {
  const infractores = [...ficheros(path.join(RAIZ, 'src')), path.join(RAIZ, 'App.tsx')]
    .filter((f) => !f.endsWith(path.join('theme', 'tokens.ts')))
    .filter((f) => COLOR_FISICO.test(fs.readFileSync(f, 'utf8')));
  expect(infractores).toEqual([]);
});

test('conjunto cerrado de tokens de color (sin tokens nuevos sin decisión F09)', () => {
  const esperado = [
    'accent', 'accentSurface', 'background', 'borderDefault', 'borderStandard', 'critical', 'info', 'onAccent',
    'partialSurface', 'positive', 'separator', 'surfacePrimary', 'surfaceSecondary', 'textPrimary', 'textSecondary',
    'unknownSurface', 'warning',
  ];
  expect(Object.keys(colores.light).sort()).toEqual(esperado);
  expect(Object.keys(colores.dark).sort()).toEqual(esperado);
});
