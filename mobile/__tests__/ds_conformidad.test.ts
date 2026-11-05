// ============================================================
// GAPTO MOBILE 2027
// Fichero: ds_conformidad.test.ts
// Ruta: mobile/__tests__/ds_conformidad.test.ts
// Descripción: Guardas de conformidad con el Design System F09 (F05 — VS-01 · Alineación visual, condición A1 de la revisión): ningún color físico fuera de tokens.ts (DS-RULE-12) y conjunto de tokens de color cerrado respecto de DS-01 v1.0 + los derivados ya registrados (deuda F05-D003 §16.8).
// Versión: 0.1.0
// Versión: 0.2.0 (F06-M1 Tokens, V1 con anillo (F06-D003; dictamen PT-01..PT-12 del 2026-11-05)): el conjunto cerrado de tokens pasa a 21 por tema con los 4 de rol (aserción anterior: 17 tokens «sin tokens nuevos sin decisión F09»; trazabilidad en el comentario del test).
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

// Trazabilidad (F06-M1, PT-05): antes «conjunto cerrado de tokens de color (sin tokens nuevos sin decisión F09)» con
// 17 tokens por tema (accent, accentSurface, background, borderDefault, borderStandard, critical, info, onAccent,
// partialSurface, positive, separator, surfacePrimary, surfaceSecondary, textPrimary, textSecondary, unknownSurface, warning).
// Ahora 21: se añaden accentText, criticalText, positiveText y warningText (F06-D003; dictamen PT-01). El conjunto sigue cerrado.
test('conjunto cerrado de tokens de color (DS-01 + 4 tokens de rol de texto, decisión F09 propuesta en F06-M1)', () => {
  const esperado = [
    'accent', 'accentSurface', 'accentText', 'background', 'borderDefault', 'borderStandard', 'critical', 'criticalText',
    'info', 'onAccent', 'partialSurface', 'positive', 'positiveText', 'separator', 'surfacePrimary', 'surfaceSecondary',
    'textPrimary', 'textSecondary', 'unknownSurface', 'warning', 'warningText',
  ];
  expect(Object.keys(colores.light).sort()).toEqual(esperado);
  expect(Object.keys(colores.dark).sort()).toEqual(esperado);
});
