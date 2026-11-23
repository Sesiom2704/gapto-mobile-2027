// ============================================================
// GAPTO MOBILE 2027
// Fichero: guarda_entorno.js
// Ruta: mobile/guarda_entorno.js
// Descripción: Guarda de entorno de Metro y de los builds (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.5; dictamen AJ-TOK-04 punto 2). Expo incrusta en el bundle toda variable `EXPO_PUBLIC_*`; si alguna lleva TOKEN, SECRET, PASSWORD o KEY en el nombre, Metro (y `expo export` / builds, que cargan `metro.config.js`) se niega a arrancar con un mensaje claro. Solo se nombran las variables, NUNCA sus valores.
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

const PATRON_SECRETO = /TOKEN|SECRET|PASSWORD|KEY/i;

/** Nombres de las variables públicas de Expo que parecen secretos (sin valores). */
function variablesProhibidas(env) {
  return Object.keys(env || {})
    .filter((k) => k.startsWith('EXPO_PUBLIC_') && PATRON_SECRETO.test(k.slice('EXPO_PUBLIC_'.length)))
    .sort();
}

/** Lanza si hay alguna; el mensaje solo nombra las variables. */
function exigirEntornoSinSecretos(env) {
  const malas = variablesProhibidas(env);
  if (malas.length > 0) {
    throw new Error(
      `GAPTO: variables EXPO_PUBLIC_* con aspecto de secreto en el entorno (${malas.join(', ')}). ` +
        'Expo las incrusta en el bundle: quítalas del entorno y de mobile/.env. La credencial se introduce en la app ' +
        '(«Conectar con tu PC») y vive en el llavero del iPhone.',
    );
  }
}

module.exports = { variablesProhibidas, exigirEntornoSinSecretos, PATRON_SECRETO };
