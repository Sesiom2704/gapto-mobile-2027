// ============================================================
// GAPTO MOBILE 2027
// Fichero: ds_rol_superficies.test.tsx
// Ruta: mobile/__tests__/ds_rol_superficies.test.tsx
// Descripción: Control de superficies de los tokens de rol (F06-M1 Tokens, V1 con anillo; F06-D003; dictamen PT-04 del 2026-11-05). `positiveText` claro (#12843C) da 4,58:1 sobre `background` y 4,78:1 sobre `surfacePrimary`, pero menos de 4,5:1 sobre `surfaceSecondary`, `accentSurface`, `unknownSurface` y `partialSurface`; por eso solo puede usarse sobre `background` y `surfacePrimary`. Dos capas: (1) estática: toda referencia a `positiveText` en el código está en la lista de usos revisados, sin acceso dinámico a los tokens que la esquive; (2) de render: cada nodo pintado con `positiveText` claro tiene como superficie efectiva (primer `backgroundColor` opaco de sus antecesores) `background` o `surfacePrimary`, aunque el color llegue por una variable o un componente intermedio. Además, PT-01.4: ningún relleno semántico (`accent`, `critical`, `positive`, `warning`) como color de texto o icono, ni en la propiedad `color` ni en variables de color de primer plano; y el conjunto cerrado de 21 tokens con el contraste de cada token de rol sobre sus superficies autorizadas (PT-01).
// Versión: 0.1.0 (F06-M1 Tokens, V1 con anillo (F06-D003; dictamen PT-04 del 2026-11-05))
// ============================================================

import './tiempos_rn';
import { render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi } from '../src/api/cliente';
import { HomeScreen } from '../src/screens/HomeScreen';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

// Módulos de Node disponibles en Jest; tipado mínimo local para no añadir @types/node al proyecto.
declare const __dirname: string;
interface Entrada { name: string; isDirectory(): boolean }
const fs: { readdirSync(d: string, o: { withFileTypes: true }): Entrada[]; readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string; relative(a: string, b: string): string } = require('path');

const RAIZ = path.join(__dirname, '..');

function ficheros(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e: Entrada) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? ficheros(p) : /\.(ts|tsx)$/.test(e.name) ? [p] : [];
  });
}

/** Código sin comentarios de línea ni de bloque (las cabeceras citan los tokens). */
function codigo(f: string): string {
  return fs.readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
}

const fuentes = () => [...ficheros(path.join(RAIZ, 'src')), path.join(RAIZ, 'App.tsx')];
const rel = (f: string) => path.relative(RAIZ, f).split('\\').join('/');

/**
 * Usos de `positiveText` revisados, con su superficie. Un uso nuevo hace fallar el test hasta que se revise su superficie
 * (background o surfacePrimary) y se añada aquí y, si se pinta en otra pantalla, a la comprobación de render.
 */
const USOS_POSITIVE_TEXT: Record<string, number> = {
  'src/theme/tokens.ts': 3, // interfaz y valores claro y oscuro
  'src/screens/HomeScreen.tsx': 1, // «Resultado» del mes, sobre background (ScrollView «home»)
};

test('PT-04 (estático): toda referencia a positiveText está en la lista de usos revisados', () => {
  const usos: Record<string, number> = {};
  for (const f of fuentes()) {
    const n = (codigo(f).match(/\bpositiveText\b/g) ?? []).length;
    if (n > 0) usos[rel(f)] = n;
  }
  expect(usos).toEqual(USOS_POSITIVE_TEXT);
});

test('PT-04 (estático): ningún acceso dinámico a los tokens de color que esquive la lista', () => {
  const infractores = fuentes()
    .filter((f) => !f.endsWith(path.join('theme', 'tema.tsx'))) // colores[esquema]: elige el tema, no un token
    .filter((f) => /\bc\[|colores\.(light|dark)\[|\[\s*['"`]positive|Object\.(values|entries|keys)\(\s*c\s*\)|\.\.\.c\b/.test(codigo(f)))
    .map(rel);
  expect(infractores).toEqual([]);
});

test('PT-01.4: ningún relleno semántico como color de texto o icono (propiedad `color` o variable de color)', () => {
  const RELLENO = /\bc\.(accent|critical|positive|warning)\b(?!Text|Surface)/;
  const infractores: string[] = [];
  for (const f of fuentes()) {
    codigo(f).split('\n').forEach((l, i) => {
      // `color` de estilo o de icono (`color:` / `color=`) y variables de color de primer plano (`const color... =`).
      const usos = [...l.matchAll(/(?<![\w-])color\s*[:=]\s*\{?([^,}\]]*)/g)].map((m) => m[1]);
      const variable = /\b(const|let)\s+color\w*\s*=\s*(.*)$/.exec(l);
      if (variable) usos.push(variable[2]);
      if (usos.some((u) => RELLENO.test(u))) infractores.push(`${rel(f)}:${i + 1}`);
    });
  }
  expect(infractores).toEqual([]);
});

// ------------------------------------------------------------------ conjunto cerrado y superficies autorizadas (PT-01)

const SUPERFICIES = ['background', 'surfacePrimary', 'surfaceSecondary', 'accentSurface', 'unknownSurface', 'partialSurface'] as const;
const ROL = ['accentText', 'criticalText', 'positiveText', 'warningText'] as const;

/** Superficies autorizadas de cada token de rol por tema (PT-01.2; PT-04 para positiveText claro). */
const AUTORIZADAS: Record<'light' | 'dark', Record<(typeof ROL)[number], readonly (typeof SUPERFICIES)[number][]>> = {
  light: { accentText: SUPERFICIES, criticalText: SUPERFICIES, positiveText: ['background', 'surfacePrimary'], warningText: SUPERFICIES },
  dark: { accentText: SUPERFICIES, criticalText: SUPERFICIES, positiveText: SUPERFICIES, warningText: SUPERFICIES },
};

function luminancia(hex: string): number {
  const v = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function contraste(a: string, b: string): number {
  const [x, y] = [luminancia(a), luminancia(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

test('PT-01: 21 tokens de color por tema, los mismos en claro y oscuro, con los 4 de rol', () => {
  expect(Object.keys(colores.light)).toHaveLength(21);
  expect(Object.keys(colores.dark).sort()).toEqual(Object.keys(colores.light).sort());
  for (const t of ROL) expect(Object.keys(colores.light)).toContain(t);
});

test('PT-01/PT-04: cada token de rol da >= 4,5:1 sobre todas sus superficies autorizadas (claro y oscuro)', () => {
  for (const e of ['light', 'dark'] as const)
    for (const t of ROL) for (const s of AUTORIZADAS[e][t]) expect([e, t, s, contraste(colores[e][t], colores[e][s]) >= 4.5]).toEqual([e, t, s, true]);
});

test('PT-04: positiveText claro NO llega a 4,5:1 fuera de background y surfacePrimary (por eso la restricción)', () => {
  const fuera = SUPERFICIES.filter((s) => !AUTORIZADAS.light.positiveText.includes(s));
  expect(fuera).toEqual(['surfaceSecondary', 'accentSurface', 'unknownSurface', 'partialSurface']);
  for (const s of fuera) expect(contraste(colores.light.positiveText, colores.light[s])).toBeLessThan(4.5);
});

// ------------------------------------------------------------------ capa de render

type Nodo = { type: unknown; props: Record<string, any>; parent: Nodo | null };

const estilo = (n: Nodo): Record<string, any> => (StyleSheet.flatten(n.props.style) ?? {}) as Record<string, any>;

function opaco(color: unknown): color is string {
  return typeof color === 'string' && color !== 'transparent' && !/^rgba\(.*,\s*0\s*\)$/.test(color);
}

/** Primer `backgroundColor` opaco de los antecesores (incluido el propio nodo). */
function superficie(n: Nodo): string | null {
  for (let x: Nodo | null = n; x; x = x.parent) {
    const bg = estilo(x).backgroundColor;
    if (opaco(bg)) return bg;
  }
  return null;
}

/** Nodos anfitriones pintados con `color` (estilo de texto o prop `color` de un icono). */
function pintadosCon(raiz: Nodo & { findAll(p: (n: Nodo) => boolean): Nodo[] }, color: string): Nodo[] {
  return raiz.findAll((n) => typeof n.type === 'string' && (estilo(n).color === color || n.props.color === color));
}

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);

function cliente(resultado: string): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    resultadoMes: jest.fn(async () => ({ tipo: 'OK', datos: { mes: '2026-10', moneda: 'EUR', ingresos_propios: '7784.04', gastos_propios: '3339.91', resultado,
      sin_indicar: { gastos: { n: 0, importe: '0' }, ingresos: { n: 0, importe: '0' } } } }) as any),
  } as unknown as ClienteApi; // solo lo que lee Inicio
}

test('PT-04 (render): positiveText claro solo se pinta sobre background o surfacePrimary (Inicio, Resultado positivo)', async () => {
  const c = colores.light;
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema forzar="light">
        <HomeScreen cliente={cliente('4444.13')} ahora={AHORA} refresco={0} onRegistrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await waitFor(() => expect(screen.getByTestId('mes-resultado').props.children).toBe('+4.444,13 €'));
  const pintados = pintadosCon(screen.UNSAFE_root as any, c.positiveText);
  expect(pintados.length).toBeGreaterThan(0); // la comprobación no es vacía: «Resultado» usa positiveText
  for (const n of pintados) expect([c.background, c.surfacePrimary]).toContain(superficie(n));
});
