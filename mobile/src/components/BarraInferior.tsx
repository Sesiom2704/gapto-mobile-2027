// ============================================================
// GAPTO MOBILE 2027
// Fichero: BarraInferior.tsx
// Ruta: mobile/src/components/BarraInferior.tsx
// Descripción: Barra inferior con los cinco destinos estables de F09 BLOQUE A (Inicio, Día a día, Mes, Patrimonio, Más). Silenciosa (HOME-01 §6). Se oculta en tareas CREATE/EDIT: la oculta App, no este componente.
// Versión: 0.1.0
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';

export type Destino = 'INICIO' | 'DIA' | 'MES' | 'PATRIMONIO' | 'MAS';

const DESTINOS: { id: Destino; etiqueta: string; icono: keyof typeof Ionicons.glyphMap; activo: keyof typeof Ionicons.glyphMap }[] = [
  { id: 'INICIO', etiqueta: 'Inicio', icono: 'home-outline', activo: 'home' },
  { id: 'DIA', etiqueta: 'Día a día', icono: 'list-outline', activo: 'list' },
  { id: 'MES', etiqueta: 'Mes', icono: 'stats-chart-outline', activo: 'stats-chart' },
  { id: 'PATRIMONIO', etiqueta: 'Patrimonio', icono: 'pie-chart-outline', activo: 'pie-chart' },
  { id: 'MAS', etiqueta: 'Más', icono: 'ellipsis-horizontal', activo: 'ellipsis-horizontal' },
];

export function BarraInferior({ actual, onCambiar }: { actual: Destino; onCambiar: (d: Destino) => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View
      accessibilityRole="tablist"
      style={[s.barra, { backgroundColor: c.surfacePrimary, borderTopColor: c.borderDefault, paddingBottom: Math.max(inset.bottom, espacio.s) }]}
    >
      {DESTINOS.map((d) => {
        const sel = d.id === actual;
        const color = sel ? c.accent : c.textSecondary;
        return (
          <Pressable
            key={d.id}
            testID={`tab-${d.id}`}
            accessibilityRole="tab"
            accessibilityState={{ selected: sel }}
            accessibilityLabel={d.etiqueta}
            onPress={() => onCambiar(d.id)}
            style={s.item}
          >
            <Ionicons name={sel ? d.activo : d.icono} size={22} color={color} />
            <Text style={[tipo.caption, { color, fontWeight: sel ? '600' : '400' }]} numberOfLines={1}>
              {d.etiqueta}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  barra: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, paddingTop: espacio.s },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: TACTIL_MIN, gap: 2 },
});
