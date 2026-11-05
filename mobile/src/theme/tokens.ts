// ============================================================
// GAPTO MOBILE 2027
// Fichero: tokens.ts
// Ruta: mobile/src/theme/tokens.ts
// Descripción: Tokens del Design System F09 (DS-01 color, DS-02 tipografía, DS-03 geometría). Capa física -> semántica; los componentes consumen solo semántica (DS-RULE-12). HEX extraídos de la lámina DS-01 v1.0 y verificados por contraste en __tests__/dominio.test.ts antes de usarse (F09 §12.92.8). 'accentSurface' es DERIVADO (tinte del hero HOME-01), no figura en DS-01.
// v0.1.1: corrección editorial de la referencia al test de contraste (dominio.test.ts); sin cambio de valores.
// v0.2.0 (F06-M1 Tokens, V1 con anillo (F06-D003; dictamen PT-01..PT-12 del 2026-11-05)): cuatro tokens de rol de texto e icono por tema (`accentText`, `criticalText`, `positiveText`, `warningText`; 21 tokens por tema) y ajustes V1 de `textSecondary`, `borderDefault`, `borderStandard`, `accent`, `warning` y `critical` (claro) y de `textSecondary` y `borderStandard` (oscuro). `positiveText` claro solo sobre `background` y `surfacePrimary` (PT-04; control en __tests__/ds_rol_superficies.test.tsx).
// Versión: 0.2.0
// ============================================================

import { TextStyle } from 'react-native';

export type Esquema = 'light' | 'dark';

export interface Colores {
  background: string;
  surfacePrimary: string;
  surfaceSecondary: string;
  accentSurface: string;
  textPrimary: string;
  textSecondary: string;
  borderDefault: string;
  borderStandard: string;
  separator: string;
  accent: string;
  // Tokens de rol (F06-M1, F06-D003): texto e iconos con significado. Los rellenos semanticos
  // (accent, critical, positive, warning) solo rellenan, bordean o marcan; nunca son color de texto o icono (PT-01.4).
  accentText: string;
  criticalText: string;
  // positiveText claro solo sobre background y surfacePrimary (PT-04): ds_rol_superficies.test.tsx lo comprueba.
  positiveText: string;
  warningText: string;
  onAccent: string;
  positive: string;
  warning: string;
  critical: string;
  info: string;
  // Estado de conocimiento (DS-RULE-39): tratamiento neutro, no de error.
  unknownSurface: string;
  partialSurface: string;
}

export const colores: Record<Esquema, Colores> = {
  light: {
    background: '#FAFAF8',
    surfacePrimary: '#FFFFFF',
    surfaceSecondary: '#F4F5F4',
    accentSurface: '#F0F5F1',
    textPrimary: '#1A1A1A',
    textSecondary: '#363940',
    borderDefault: '#E3E6E2',
    borderStandard: '#848E9F',
    separator: '#F1F3F4',
    accent: '#1E6D48',
    onAccent: '#FFFFFF',
    accentText: '#13432C',
    criticalText: '#8D1717',
    positiveText: '#12843C',
    warningText: '#552F02',
    positive: '#16A34A',
    warning: '#B16105',
    critical: '#CA2121',
    info: '#3B82F6',
    unknownSurface: '#F3F4F3',
    partialSurface: '#FDF3E6',
  },
  dark: {
    background: '#0F1412',
    surfacePrimary: '#1A1F1D',
    surfaceSecondary: '#232A27',
    accentSurface: '#1C2B24',
    textPrimary: '#F4F6F5',
    textSecondary: '#AAB3AF',
    borderDefault: '#33413B',
    borderStandard: '#60766B',
    separator: '#232A27',
    accent: '#34D399',
    onAccent: '#0F1412',
    accentText: '#34D399',
    criticalText: '#F98C8C',
    positiveText: '#4ADE80',
    warningText: '#FBBF24',
    positive: '#4ADE80',
    warning: '#FBBF24',
    critical: '#F87171',
    info: '#60A5FA',
    unknownSurface: '#232A27',
    partialSurface: '#2E2618',
  },
};

// DS-03: base 8 pt, 4 pt para microespaciado.
export const espacio = { xs: 4, s: 8, m: 12, l: 16, xl: 24, xxl: 32, xxxl: 48 } as const;

// DS-03: radios por jerarquía.
export const radio = { xs: 4, s: 8, m: 12, l: 16, xl: 20, xxl: 28, pill: 999 } as const;

// DS-04 / F09: objetivo táctil mínimo (44 pt, guía iOS).
export const TACTIL_MIN = 44;

// DS-02: escala tipográfica (tamaños base; Dynamic Type los escala).
export const tipo: Record<string, TextStyle> = {
  display: { fontSize: 34, fontWeight: '600' },
  titleLarge: { fontSize: 28, fontWeight: '700' },
  titleMedium: { fontSize: 22, fontWeight: '600' },
  titleSmall: { fontSize: 17, fontWeight: '600' },
  body: { fontSize: 17, fontWeight: '400' },
  bodyEmphasis: { fontSize: 17, fontWeight: '600' },
  callout: { fontSize: 16, fontWeight: '400' },
  subheadline: { fontSize: 15, fontWeight: '400' },
  footnote: { fontSize: 13, fontWeight: '400' },
  caption: { fontSize: 12, fontWeight: '400' },
};

// DS-02 §4: importes con cifras tabulares cuando mejoran la alineación.
export const importe: Record<string, TextStyle> = {
  hero: { fontSize: 34, fontWeight: '600', fontVariant: ['tabular-nums'] },
  primary: { fontSize: 22, fontWeight: '600', fontVariant: ['tabular-nums'] },
  secondary: { fontSize: 17, fontWeight: '600', fontVariant: ['tabular-nums'] },
  compact: { fontSize: 15, fontWeight: '400', fontVariant: ['tabular-nums'] },
};

// DS-02 §10: serif SOLO para la marca, nunca para la interfaz financiera.
export const FUENTE_MARCA = 'Georgia';
