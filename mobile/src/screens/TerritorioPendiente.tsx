// ============================================================
// GAPTO MOBILE 2027
// Fichero: TerritorioPendiente.tsx
// Ruta: mobile/src/screens/TerritorioPendiente.tsx
// Descripción: Raíz provisional de los territorios Día a día, Mes, Patrimonio y Más (F09 BLOQUE A), no implementados en VS-01. Cabecera raíz y estado explícito; sin datos ficticios.
// Versión: 0.1.0
// ============================================================

import React from 'react';
import { Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { EstadoDato } from '../components/Basicos';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

export function TerritorioPendiente({ titulo }: { titulo: string }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View testID={`territorio-${titulo}`} style={{ flex: 1, backgroundColor: c.background, paddingTop: inset.top + espacio.l, paddingHorizontal: espacio.l, gap: espacio.m }}>
      <Text accessibilityRole="header" style={[tipo.titleLarge, { color: c.textPrimary }]}>{titulo}</Text>
      <EstadoDato estado="NO_DISPONIBLE" detalle="Territorio no incluido en este primer slice (VS-01)." />
    </View>
  );
}
