// ============================================================
// GAPTO MOBILE 2027
// Fichero: token_bundle.test.ts
// Ruta: mobile/__tests__/token_bundle.test.ts
// Descripción: F06 T4 · token BETA_LOCAL (mandato 4f0e40af… §2.2, §2.5 y §4; dictamen AJ-TOK-02/04, mutantes M-TOK-01/02/07). Test ESTÁTICO de referencias prohibidas y guarda de entorno de Metro:
//   - ningún fichero del código de la app (src, App.tsx, index.ts, app.json, metro.config.js) nombra una variable `EXPO_PUBLIC_*` de secreto (TOKEN, SECRET, PASSWORD, KEY); el único `process.env` del código es la URL de la API;
//   - la credencial solo se persiste con expo-secure-store: los módulos de la credencial no importan AsyncStorage ni ficheros, y ninguna escritura de AsyncStorage usa una clave de credencial o token;
//   - los módulos de la credencial no escriben en consola;
//   - `guarda_entorno.js` detecta las variables (sin mostrar valores) y `metro.config.js` la aplica.
//   No sustituye al barrido del bundle real (AJ-TOK-04), que se hace sobre el artefacto que genera Metro.
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

declare const __dirname: string;
declare function require(m: string): any;
type Entrada = { name: string; isDirectory(): boolean };
const fs: { readdirSync(d: string, o: { withFileTypes: true }): Entrada[]; readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string; resolve(...p: string[]): string; relative(a: string, b: string): string } = require('path');

const RAIZ = path.resolve(__dirname, '..');
const SECRETO_PUBLICO = /EXPO_PUBLIC_[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|KEY)/i;

function ficheros(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? ficheros(p) : /\.(ts|tsx|js|json)$/.test(e.name) ? [p] : [];
  });
}
const CODIGO = [...ficheros(path.join(RAIZ, 'src')), ...['App.tsx', 'index.ts', 'app.json', 'metro.config.js'].map((f) => path.join(RAIZ, f))];
const leer = (p: string) => fs.readFileSync(p, 'utf8');
const rel = (p: string) => path.relative(RAIZ, p).replace(/\\/g, '/');
const MODULOS_CREDENCIAL = ['src/api/credencial.ts', 'src/api/almacenCredencial.ts', 'src/api/config.ts', 'src/api/transporte.ts', 'src/screens/ConectarScreen.tsx'];

test('ningún fichero de la app nombra una variable EXPO_PUBLIC_* de secreto (M-TOK-01)', () => {
  expect(CODIGO.length).toBeGreaterThan(50);
  expect(CODIGO.filter((p) => SECRETO_PUBLICO.test(leer(p))).map(rel)).toEqual([]);
});

test('el único process.env del código de la app es la URL de la API, en config.ts', () => {
  const usos = CODIGO.flatMap((p) => [...leer(p).matchAll(/process\.env(?:\.([A-Za-z0-9_]+)|\[)/g)].map((m) => `${rel(p)}:${m[1] ?? '['}`));
  expect(usos.filter((u) => !u.startsWith('metro.config.js:'))).toEqual(['src/api/config.ts:EXPO_PUBLIC_GAPTO_API_URL']);
});

test('la credencial solo se persiste con expo-secure-store; sin AsyncStorage ni ficheros (M-TOK-02)', () => {
  const almacen = leer(path.join(RAIZ, 'src/api/almacenCredencial.ts'));
  expect(almacen).toMatch(/from 'expo-secure-store'/);
  expect(almacen).toMatch(/WHEN_UNLOCKED_THIS_DEVICE_ONLY/);
  for (const m of MODULOS_CREDENCIAL) {
    const t = leer(path.join(RAIZ, m));
    const importa = /(from|require\()\s*['"][^'"]*(async-storage|expo-file-system|react-native-fs)['"]/.test(t);
    const usa = /\b(AsyncStorage|localStorage|FileSystem)\s*\.|writeFile/.test(t);
    expect([m, importa || usa]).toEqual([m, false]);
  }
  // ninguna escritura de AsyncStorage en la app usa una clave de credencial o de token
  const escrituras = CODIGO.flatMap((p) => [...leer(p).matchAll(/AsyncStorage\.(setItem|multiSet|mergeItem)\(([^,)]*)/g)].map((m) => `${rel(p)}:${m[2]}`));
  expect(escrituras.filter((e) => /credencial|token|secret/i.test(e))).toEqual([]);
});

test('los módulos de la credencial no escriben en consola (M-TOK-07)', () => {
  for (const m of MODULOS_CREDENCIAL) expect([m, /console\.(log|info|warn|error|debug|trace)/.test(leer(path.join(RAIZ, m)))]).toEqual([m, false]);
});

test('guarda de entorno: detecta EXPO_PUBLIC_* de secreto por su nombre y nunca muestra valores', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const g = require('../guarda_entorno');
  const env = {
    EXPO_PUBLIC_GAPTO_API_URL: 'http://192.168.1.5:8027',
    EXPO_PUBLIC_GAPTO_DEV_TOKEN: 'valor-secreto-1',
    EXPO_PUBLIC_API_KEY: 'valor-secreto-2',
    EXPO_PUBLIC_db_password: 'valor-secreto-3',
    EXPO_PUBLIC_SECRETO: 'valor-secreto-4',
    GAPTO_DEV_TOKEN: 'no-es-publica',
  };
  expect(g.variablesProhibidas(env)).toEqual(['EXPO_PUBLIC_API_KEY', 'EXPO_PUBLIC_GAPTO_DEV_TOKEN', 'EXPO_PUBLIC_SECRETO', 'EXPO_PUBLIC_db_password']);
  let mensaje = '';
  try {
    g.exigirEntornoSinSecretos(env);
  } catch (e) {
    mensaje = String((e as Error).message);
  }
  expect(mensaje).toContain('EXPO_PUBLIC_GAPTO_DEV_TOKEN');
  expect(mensaje).not.toMatch(/valor-secreto/);
  expect(() => g.exigirEntornoSinSecretos({ EXPO_PUBLIC_GAPTO_API_URL: 'http://127.0.0.1:8000', PATH: 'x' })).not.toThrow();
  expect(leer(path.join(RAIZ, 'metro.config.js'))).toMatch(/exigirEntornoSinSecretos\(process\.env\)/);
});
