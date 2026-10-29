// ============================================================
// GAPTO MOBILE 2027
// Fichero: jest.setup.js
// Ruta: mobile/jest.setup.js
// Descripción: Ajuste del entorno de Jest para SDK 58 / RN 0.88. jest-expo
//   58 simula `react-native/asset-registry`, pero `import { AssetRegistry }
//   from 'react-native'` (lo usa expo-asset al cargar las fuentes de
//   @expo/vector-icons) resuelve ahora a `src/private/assets/AssetRegistry`.
//   Se reexpone la misma simulación de jest-expo en esa ruta. Solo entorno de
//   test; no cambia ningún test ni el producto.
// Versión: 0.1.0 (F05-07 G1 SDK 58, decisión de Moisés del 2026-10-25)
// Versión: 0.2.0 (F05-D056 paso 2, COLA-AR §70.A.4): AsyncStorage (persistencia
//   mínima de la cola de acciones rápidas) con la simulación en memoria que
//   publica la propia librería.
// ============================================================
jest.mock('./node_modules/react-native/src/private/assets/AssetRegistry', () => ({
  AssetRegistry: jest.requireMock('react-native/asset-registry'),
}));
jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
