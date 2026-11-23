// ============================================================
// GAPTO MOBILE 2027
// Fichero: almacenCredencial.ts
// Ruta: mobile/src/api/almacenCredencial.ts
// Descripción: Almacén de la credencial de desarrollo en el llavero del iPhone con expo-secure-store (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.2; dictamen AJ-TOK-02). Accesible solo con el dispositivo desbloqueado y SOLO en este dispositivo (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`: no viaja a copias de seguridad ni a otro iPhone). Es el ÚNICO sitio persistente de la credencial: prohibido AsyncStorage, ficheros, configuración Expo y `EXPO_PUBLIC_*` (lo vigila `__tests__/token_bundle.test.ts`).
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

import * as SecureStore from 'expo-secure-store';

import type { AlmacenCredencial } from './credencial';

/** Clave del llavero (solo caracteres admitidos por SecureStore). */
export const CLAVE_CREDENCIAL = 'gapto.credencial_dev';

const OPCIONES: SecureStore.SecureStoreOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export const almacenLlavero: AlmacenCredencial = {
  leer: () => SecureStore.getItemAsync(CLAVE_CREDENCIAL, OPCIONES),
  guardar: (valor: string) => SecureStore.setItemAsync(CLAVE_CREDENCIAL, valor, OPCIONES),
  borrar: () => SecureStore.deleteItemAsync(CLAVE_CREDENCIAL, OPCIONES),
};
