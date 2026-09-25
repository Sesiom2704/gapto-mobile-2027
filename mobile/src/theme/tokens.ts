// ============================================================
// GAPTO MOBILE 2027
// Fichero: tokens.ts
// Ruta: mobile/src/theme/tokens.ts
// Descripción: Tokens del Design System F09 (DS-01 color, DS-02 tipografía, DS-03 geometría). Capa física -> semántica; los componentes consumen solo semántica (DS-RULE-12). HEX extraídos de la lámina DS-01 v1.0 y verificados por contraste en __tests__/contraste.test.ts antes de usarse (F09 §12.92.8). 'accentSurface' es DERIVADO (tinte del hero HOME-01), no figura en DS-01.
// Versión: 0.1.0
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
    textSecondary: '#69707D',
    borderDefault: '#E6E8E5',
    borderStandard: '#D1D5DB',
    separator: '#F1F3F4',
    accent: '#1F6F49',
    onAccent: '#FFFFFF',
    positive: '#16A34A',
    warning: '#D97706',
    critical: '#DC2626',
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
    textSecondary: '#A7B1AC',
    borderDefault: '#33413B',
    borderStandard: '#3F4D46',
    separator: '#232A27',
    accent: '#34D399',
    onAccent: '#0F1412',
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
