// ============================================================
// GAPTO MOBILE 2027
// Fichero: PantallaSelector.tsx
// Ruta: mobile/src/components/PantallaSelector.tsx
// Descripción: Marco común de los selectores (F06 T6 «UX ágil» S1; F09 0.55 §12.107.1 puntos 5 y 6, FA-01/DF-05, FA-04): pantalla completa sobre el fondo, título centrado y «Cerrar» arriba a la derecha, igual que el selector de Categoría (SelectorCategorias). Al abrirse cierra el teclado (`useCerrarTecladoAlAbrir`, que también usan los selectores a pantalla completa que ya existían: Categoría (desde S2, T6-D-03), Magnitudes, Iconos y Persona del reparto), para que no quede abierto el del campo anterior. `CampoSelector` es el campo que lo abre (aspecto de «Tercero» en Registrar gasto). Solo presentación: el contenido, sus `testID`, filtros, altas y «Reactivar» son los de cada selector.
// Versión: 0.1.0 (F06 T6 · S1 piezas comunes)
// Versión: 0.1.1 (F06 T6 · S2): el selector de Categoría usa también `useCerrarTecladoAlAbrir`; solo cambia la descripción.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useEffect } from 'react';
import { Keyboard, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto } from './Basicos';

/** F09 0.55 §12.107.1 punto 6 (FA-04): al abrirse un selector se cierra el teclado del campo anterior. */
export function useCerrarTecladoAlAbrir() {
  useEffect(() => {
    Keyboard.dismiss();
  }, []);
}

export function PantallaSelector(p: {
  titulo: string;
  testID: string;
  /** «Cerrar» arriba a la derecha; conserva el `testID` que el selector tenía para su botón de cierre. */
  onCerrar: () => void;
  testIDCerrar: string;
  children: React.ReactNode;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  useCerrarTecladoAlAbrir();
  return (
    <View testID={p.testID} accessibilityViewIsModal style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <View style={s.lado} />
        <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, s.titulo, { color: c.textPrimary }]}>{p.titulo}</Text>
        <View style={[s.lado, { alignItems: 'flex-end' }]}>
          <BotonTexto testID={p.testIDCerrar} titulo="Cerrar" onPress={p.onCerrar} />
        </View>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={[s.cuerpo, { paddingBottom: inset.bottom + espacio.l }]}>{p.children}</View>
      </KeyboardAvoidingView>
    </View>
  );
}

/** Campo que abre un selector (mismo aspecto que «Tercero» de Registrar gasto): valor elegido o marcador y «›». */
export function CampoSelector(p: { testID: string; etiqueta: string; valor: string | null; marcador: string; onAbrir: () => void; deshabilitado?: boolean }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={`${p.etiqueta}: ${p.valor ?? p.marcador}`}
      disabled={p.deshabilitado}
      onPress={p.onAbrir}
      style={[s.campo, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
    >
      <Text testID={`${p.testID}-valor`} style={[tipo.body, { flex: 1, color: p.valor ? c.textPrimary : c.textSecondary }]}>{p.valor ?? p.marcador}</Text>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  campo: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  lado: { width: 72 },
  titulo: { flex: 1, textAlign: 'center' },
  cuerpo: { flex: 1, gap: espacio.m, paddingHorizontal: espacio.l, paddingTop: espacio.m },
});
