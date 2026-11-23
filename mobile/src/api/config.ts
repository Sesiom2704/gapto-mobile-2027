// ============================================================
// GAPTO MOBILE 2027
// Fichero: config.ts
// Ruta: mobile/src/api/config.ts
// Descripción: Configuración del cliente en DESARROLLO. La URL de la API llega por `EXPO_PUBLIC_GAPTO_API_URL` (no es secreta). La credencial de desarrollo NO viaja en el bundle: la da en ejecución el proveedor de `credencial.ts` (llavero del iPhone), leída en CADA petición; sin credencial validada no sale ninguna petición autenticada. NO ES AUTENTICACIÓN DE PRODUCCIÓN (deuda F10-01).
// Versión: 0.1.0
// Versión: 0.2.0 (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.2; dictamen AJ-TOK-01/02): deja de leer la variable pública del token; `credencial` y `alNoAutorizado` enganchan el proveedor sin cambiar las firmas de pantallas ni escritores (`token` queda vacío).
// ============================================================

import { almacenLlavero } from './almacenCredencial';
import type { ConfigApi } from './cliente';
import { ProveedorCredencial } from './credencial';

const baseUrl = process.env.EXPO_PUBLIC_GAPTO_API_URL ?? 'http://127.0.0.1:8000';

/** Proveedor ÚNICO de la credencial de la app. */
export const proveedorCredencial = new ProveedorCredencial({
  baseUrl,
  almacen: almacenLlavero,
  fetchImpl: (entrada, init) => fetch(entrada, init),
});

export const configApi: ConfigApi = {
  baseUrl,
  token: '',
  credencial: () => proveedorCredencial.tokenParaPeticion(),
  alNoAutorizado: (token: string) => proveedorCredencial.noAutorizado(token),
  timeoutMs: 10000,
};
