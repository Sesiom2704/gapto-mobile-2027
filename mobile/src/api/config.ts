// ============================================================
// GAPTO MOBILE 2027
// Fichero: config.ts
// Ruta: mobile/src/api/config.ts
// Descripción: Configuración del cliente en DESARROLLO. URL y token llegan por variables EXPO_PUBLIC_* de un .env local NO versionado. AVISO: EXPO_PUBLIC_* se incrusta en el bundle; solo válido para la identidad de desarrollo F05-00-B (NO ES AUTENTICACIÓN DE PRODUCCIÓN, deuda F10-01).
// Versión: 0.1.0
// ============================================================

import type { ConfigApi } from './cliente';

export const configApi: ConfigApi = {
  baseUrl: process.env.EXPO_PUBLIC_GAPTO_API_URL ?? 'http://127.0.0.1:8000',
  token: process.env.EXPO_PUBLIC_GAPTO_DEV_TOKEN ?? '',
  timeoutMs: 10000,
};
