// ============================================================
// GAPTO MOBILE 2027
// Fichero: tiempos_rn.ts
// Ruta: mobile/__tests__/tiempos_rn.ts
// Descripción: Tiempos de las suites que renderizan pantallas de React Native (MANT-M5-ARNESES, AJ-M5-CIERRE-06; intermitencia R3 de M5 SWIPE2/SWIPE3). Causa documentada: en una pasada completa en frío (sin caché de transformación) Jest lanza 15 workers en 16 núcleos y el primer render de cada pantalla supera el límite por defecto de 5 s por test y de 1 s de `waitFor` / `findBy` (26 timeouts en 11 suites de pantalla; ninguna con `jest.setTimeout(30000)` falló). Importado al principio de cada suite `.tsx`: 30 s por test y 5 s para las utilidades asíncronas. No cambia ninguna aserción: un fallo real sigue fallando, solo tarda más en declararse.
// Versión: 0.2.0 (MANT D18, lote 40): límite por test 30 s -> 90 s, fuente única del límite de las suites de pantalla (R-TEST-TIMEOUT; en frío con 15 workers cortaban 14 suites). Antes 0.1.0 (MANT-M5-ARNESES)
// ============================================================

import { configure } from '@testing-library/react-native';

jest.setTimeout(90000);
configure({ asyncUtilTimeout: 5000 });
