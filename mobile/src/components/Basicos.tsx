// ============================================================
// GAPTO MOBILE 2027
// Fichero: Basicos.tsx
// Ruta: mobile/src/components/Basicos.tsx
// Descripción: Componentes básicos derivados de DS-05 (botón primario/texto, sección, chip, control segmentado) y DS-06 §9 (estado del dato). Consumen solo tokens semánticos.
// Versión: 0.1.0
// ============================================================

import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, ViewStyle } from 'react-native';

import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

export function BotonPrimario(p: { titulo: string; onPress: () => void; cargando?: boolean; deshabilitado?: boolean; testID?: string }) {
  const { c } = useTema();
  const off = p.deshabilitado || p.cargando;
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!p.cargando }}
      accessibilityLabel={p.titulo}
      onPress={off ? undefined : p.onPress}
      style={({ pressed }) => [s.primario, { backgroundColor: off ? c.surfaceSecondary : c.accent, opacity: pressed ? 0.85 : 1 }]}
    >
      {p.cargando ? <ActivityIndicator color={c.textSecondary} style={{ marginRight: espacio.s }} /> : null}
      <Text style={[tipo.bodyEmphasis, { color: off ? c.textSecondary : c.onAccent }]}>{p.titulo}</Text>
    </Pressable>
  );
}

export function BotonTexto(p: { titulo: string; onPress: () => void; testID?: string; critico?: boolean }) {
  const { c } = useTema();
  return (
    <Pressable testID={p.testID} accessibilityRole="button" onPress={p.onPress} hitSlop={8} style={s.texto}>
      <Text style={[tipo.body, { color: p.critico ? c.critical : c.accent, fontWeight: '600' }]}>{p.titulo}</Text>
    </Pressable>
  );
}

export function Seccion(p: { titulo: string; derecha?: React.ReactNode; children: React.ReactNode; testID?: string; estilo?: ViewStyle }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.seccion, { backgroundColor: c.surfacePrimary }, p.estilo]}>
      <View style={s.cabSeccion}>
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary, fontSize: 19 }]}>{p.titulo}</Text>
        {p.derecha}
      </View>
      {p.children}
    </View>
  );
}

export type EstadoConocimiento = 'NO_DISPONIBLE' | 'PARCIAL' | 'CARGANDO' | 'ERROR_CARGA';

/** DS-06 §9 / DS-RULE-39/40: estado del dato, nunca un 0 fabricado. */
export function EstadoDato({ estado, detalle, testID }: { estado: EstadoConocimiento; detalle?: string; testID?: string }) {
  const { c } = useTema();
  const etiqueta = { NO_DISPONIBLE: 'No disponible', PARCIAL: 'Parcial', CARGANDO: 'Cargando…', ERROR_CARGA: 'No se pudo cargar' }[estado];
  const fondo = estado === 'PARCIAL' ? c.partialSurface : c.unknownSurface;
  return (
    <View testID={testID} accessible accessibilityLabel={`${etiqueta}${detalle ? `. ${detalle}` : ''}`} style={s.estadoFila}>
      <View style={[s.chipEstado, { backgroundColor: fondo }]}>
        <Text style={[tipo.caption, { color: c.textPrimary }]}>{etiqueta}</Text>
      </View>
      {detalle ? <Text style={[tipo.caption, { color: c.textSecondary, flexShrink: 1 }]}>{detalle}</Text> : null}
    </View>
  );
}

export function Chip(p: { etiqueta: string; seleccionado: boolean; onPress: () => void; testID?: string; accesibilidad?: string }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: p.seleccionado }}
      accessibilityLabel={p.accesibilidad ?? p.etiqueta}
      onPress={p.onPress}
      style={[s.chip, { borderColor: p.seleccionado ? c.accent : c.borderStandard, backgroundColor: p.seleccionado ? c.accentSurface : c.surfacePrimary }]}
    >
      <Text style={[tipo.subheadline, { color: p.seleccionado ? c.accent : c.textPrimary, fontWeight: p.seleccionado ? '600' : '400' }]}>
        {p.seleccionado ? '✓ ' : ''}
        {p.etiqueta}
      </Text>
    </Pressable>
  );
}

/** Control segmentado sin selección inicial: la ausencia de elección es visible (no default). */
export function Segmentado<T extends string | boolean>(p: {
  opciones: { valor: T; etiqueta: string }[];
  valor: T | null;
  onCambiar: (v: T) => void;
  testIDBase: string;
  etiquetaGrupo: string;
}) {
  const { c } = useTema();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={p.etiquetaGrupo} style={[s.segmentado, { backgroundColor: c.surfaceSecondary }]}>
      {p.opciones.map((o) => {
        const sel = p.valor === o.valor;
        return (
          <Pressable
            key={String(o.valor)}
            testID={`${p.testIDBase}-${String(o.valor)}`}
            accessibilityRole="radio"
            accessibilityState={{ selected: sel, checked: sel }}
            accessibilityLabel={o.etiqueta}
            onPress={() => p.onCambiar(o.valor)}
            style={[s.segmento, sel && { backgroundColor: c.surfacePrimary, borderColor: c.accent, borderWidth: 1.5 }]}
          >
            <Text style={[tipo.body, { color: sel ? c.accent : c.textPrimary, fontWeight: sel ? '600' : '400' }]}>{o.etiqueta}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  primario: { minHeight: 52, borderRadius: radio.m, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', paddingHorizontal: espacio.l },
  texto: { minHeight: TACTIL_MIN, justifyContent: 'center', paddingHorizontal: espacio.xs },
  seccion: { borderRadius: radio.l, padding: espacio.l, gap: espacio.m },
  cabSeccion: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  estadoFila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, flexWrap: 'wrap' },
  chipEstado: { borderRadius: radio.pill, paddingHorizontal: espacio.s, paddingVertical: 2 },
  chip: { minHeight: TACTIL_MIN, borderRadius: radio.pill, borderWidth: 1, paddingHorizontal: espacio.l, justifyContent: 'center', alignSelf: 'flex-start' },
  segmentado: { flexDirection: 'row', borderRadius: radio.m, padding: espacio.xs, gap: espacio.xs },
  segmento: { flex: 1, minHeight: TACTIL_MIN, borderRadius: radio.s, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'transparent' },
});
