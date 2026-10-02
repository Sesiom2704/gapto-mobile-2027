// ============================================================
// GAPTO MOBILE 2027
// Fichero: FichaMagnitud.tsx
// Ruta: mobile/src/components/FichaMagnitud.tsx
// Descripción: Ficha de una magnitud abierta desde una fila de la sección «Magnitudes» de una categoría (F09 §12.97.10; lámina SET-MAG v0.1 M11–M13). Cabecera «‹ <categoría> · <magnitud>» con nombre, «unidad · decimales» y píldoras de TEXTO. Bloque «En <categoría>» con las acciones de la ASOCIACIÓN: «Hacer obligatoria» / «Hacer opcional» (M11) y «Quitar de <categoría>» (M12, crítica). Las hojas las pinta el controlador encima. Solo presentación. Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1: bloque de la asociación)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { MagnitudCategoria } from '../domain/categoria';
import { textoUnidadDecimales } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { CabeceraNavegacion } from './Basicos';
import { Pildora } from './HojasMagnitud';

export function FichaMagnitud(p: {
  categoria: string;
  asociacion: MagnitudCategoria;
  onAtras: () => void;
  onObligatoriedad: () => void;
  onQuitar: () => void;
  /** Bloque global de la magnitud (hito 2), debajo del bloque de la asociación. */
  children?: React.ReactNode;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const a = p.asociacion;
  return (
    <View testID="ficha-magnitud" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo={a.nombre} atras={{ etiqueta: p.categoria, onPress: p.onAtras }} testIDAtras="ficha-atras" />
      <ScrollView contentContainerStyle={{ paddingBottom: inset.bottom + espacio.xl }}>
        <View style={s.cabecera}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[tipo.titleMedium, { color: a.enabled ? c.textPrimary : c.textSecondary }]}>{a.nombre}</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>{textoUnidadDecimales(a.unidad_default, a.precision_decimales)}</Text>
          </View>
          {a.enabled ? null : <Pildora texto="Deshabilitada" tono="DESHABILITADA" />}
          <Pildora testID="ficha-pildora" texto={a.obligatoria ? 'Obligatoria' : 'Opcional'} tono={a.obligatoria ? 'OBLIGATORIA' : 'OPCIONAL'} />
        </View>
        <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>{`En ${p.categoria}`}</Text>
        <Accion
          testID="ficha-obligatoriedad"
          titulo={a.obligatoria ? 'Hacer opcional' : 'Hacer obligatoria'}
          onPress={p.onObligatoriedad}
        />
        <Accion testID="ficha-quitar" titulo={`Quitar de ${p.categoria}`} critica onPress={p.onQuitar} />
        {p.children}
      </ScrollView>
    </View>
  );
}

export function Accion(p: { testID: string; titulo: string; critica?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <Text style={[tipo.body, { color: p.critica ? c.critical : c.textPrimary, flex: 1 }]}>{p.titulo}</Text>
      {p.critica ? null : <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />}
    </Pressable>
  );
}

export const estilosFicha = StyleSheet.create({
  seccion: { paddingHorizontal: espacio.l, paddingTop: espacio.l, paddingBottom: espacio.xs },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 4, paddingHorizontal: espacio.l, borderBottomWidth: StyleSheet.hairlineWidth },
  nota: { paddingHorizontal: espacio.l, paddingTop: espacio.m },
});

const s = StyleSheet.create({
  cabecera: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, padding: espacio.l },
  seccion: estilosFicha.seccion,
  fila: estilosFicha.fila,
});
