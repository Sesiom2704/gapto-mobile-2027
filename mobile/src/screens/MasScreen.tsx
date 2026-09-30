// ============================================================
// GAPTO MOBILE 2027
// Fichero: MasScreen.tsx
// Ruta: mobile/src/screens/MasScreen.tsx
// Descripción: Territorio «Más» mínimo (decisión D-UI-03 de Moisés): una entrada «Ajustes» que abre las 10 secciones del árbol funcional cerrado de F09 §12.91.1, en ese orden. Solo «Categorías» es operativa; las otras nueve muestran el estado explícito «No disponible» (EstadoDato NO_DISPONIBLE, DS-RULE-39/40), sin datos ficticios y sin ser pulsables. Pantallas de lista: conservan la barra inferior.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';

/** F09 §12.91.1 — árbol funcional cerrado de Ajustes, en su orden. */
export const SECCIONES_AJUSTES = [
  'Terceros',
  'Categorías',
  'Etiquetas',
  'Contextos',
  'Reglas y recurrencias',
  'Preferencias financieras',
  'Apariencia y personalización',
  'Preferencias de uso',
  'Datos y mantenimiento',
  'Cuenta y sistema',
] as const;

export function MasScreen(p: { onAjustes: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View testID="pantalla-mas" style={{ flex: 1, backgroundColor: c.background, paddingTop: inset.top + espacio.l }}>
      <Text accessibilityRole="header" style={[tipo.titleLarge, s.titulo, { color: c.textPrimary }]}>Más</Text>
      <FilaNavegable testID="mas-ajustes" icono="settings-outline" titulo="Ajustes" onPress={p.onAjustes} />
    </View>
  );
}

export function AjustesScreen(p: { onAtras: () => void; onCategorias: () => void }) {
  const { c } = useTema();
  return (
    <View testID="pantalla-ajustes" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Ajustes" atras={{ etiqueta: 'Más', onPress: p.onAtras }} testIDAtras="ajustes-atras" />
      <ScrollView>
        {SECCIONES_AJUSTES.map((sec) =>
          sec === 'Categorías' ? (
            <FilaNavegable key={sec} testID="ajustes-categorias" titulo={sec} onPress={p.onCategorias} />
          ) : (
            <View
              key={sec}
              testID={`ajustes-seccion-${sec}`}
              accessible
              accessibilityLabel={`${sec}. No disponible`}
              style={[s.fila, { borderBottomColor: c.separator }]}
            >
              <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>{sec}</Text>
              <EstadoDato estado="NO_DISPONIBLE" />
            </View>
          ),
        )}
      </ScrollView>
    </View>
  );
}

function FilaNavegable(p: { testID: string; titulo: string; icono?: React.ComponentProps<typeof Ionicons>['name']; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      {p.icono ? <Ionicons name={p.icono} size={20} color={c.textSecondary} /> : null}
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.titulo}</Text>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  titulo: { paddingHorizontal: espacio.l, paddingBottom: espacio.m },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, borderBottomWidth: StyleSheet.hairlineWidth },
});
