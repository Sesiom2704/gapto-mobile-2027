// ============================================================
// GAPTO MOBILE 2027
// Fichero: metro.config.js
// Ruta: mobile/metro.config.js
// Descripción: Configuración de Metro = la de Expo por defecto, más la guarda de entorno del token BETA_LOCAL (F06 T4, mandato 4f0e40af… §2.5): Metro y los builds no arrancan si hay alguna `EXPO_PUBLIC_*` con aspecto de secreto (ver `guarda_entorno.js`). Nada más cambia.
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

const { getDefaultConfig } = require('expo/metro-config');
const { exigirEntornoSinSecretos } = require('./guarda_entorno');

exigirEntornoSinSecretos(process.env);

module.exports = getDefaultConfig(__dirname);
