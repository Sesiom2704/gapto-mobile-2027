// ============================================================
// GAPTO MOBILE 2027
// Fichero: tema.tsx
// Ruta: mobile/src/theme/tema.tsx
// Descripción: Proveedor de tema: Claro / Oscuro / Sistema (F09 DS-Q06). VS-01 sigue al sistema; la preferencia persistente pertenece a Ajustes.
// Versión: 0.1.0
// ============================================================

import React, { createContext, useContext } from 'react';
import { useColorScheme } from 'react-native';

import { Colores, colores, Esquema } from './tokens';

interface Tema {
  esquema: Esquema;
  c: Colores;
}

const Ctx = createContext<Tema>({ esquema: 'light', c: colores.light });

export function ProveedorTema({ children, forzar }: { children: React.ReactNode; forzar?: Esquema }) {
  const sistema = useColorScheme();
  const esquema: Esquema = forzar ?? (sistema === 'dark' ? 'dark' : 'light');
  return <Ctx.Provider value={{ esquema, c: colores[esquema] }}>{children}</Ctx.Provider>;
}

export function useTema(): Tema {
  return useContext(Ctx);
}
