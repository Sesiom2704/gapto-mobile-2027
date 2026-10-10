// ============================================================
// GAPTO MOBILE 2027
// Fichero: Formulario.tsx
// Ruta: mobile/src/components/Formulario.tsx
// Descripción: Piezas comunes de los formularios y listas de Ajustes de F05-03/F05-04 (Terceros, Contextos, Plantillas; láminas REG-DYN / SET-TH / SET-CTX v0.1 y SET-PLT v0.2): campo con etiqueta, caja de aviso (OK / aviso), cabecera de tarea «Cancelar · título», campo de selección que abre un selector, rótulo de grupo en mayúsculas y fila de lista con segunda línea. Mismo tratamiento que Ajustes › Preferencias (solo tokens semánticos).
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.5)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto } from './Basicos';

export type AvisoCaja = { tipo: 'OK' | 'AVISO'; texto: string } | null;

export function Campo({ etiqueta, opcional, children }: { etiqueta: string; opcional?: boolean; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>
        {etiqueta}
        {opcional ? <Text style={{ fontWeight: '400' }}> opcional</Text> : null}
      </Text>
      {children}
    </View>
  );
}

export function Caja({ aviso, testID }: { aviso: NonNullable<AvisoCaja>; testID: string }) {
  const { c } = useTema();
  const ok = aviso.tipo === 'OK';
  return (
    <View
      testID={testID}
      accessibilityRole={ok ? undefined : 'alert'}
      accessibilityLiveRegion="polite"
      style={[s.caja, { backgroundColor: ok ? c.accentSurface : c.partialSurface, borderColor: ok ? c.accent : c.warning }]}
    >
      <Text style={[tipo.footnote, { color: c.textPrimary }]}>{aviso.texto}</Text>
    </View>
  );
}

/** Cabecera de tarea inmersiva: «Cancelar» · título · acción opcional. */
export function CabeceraTarea(p: { titulo: string; onCancelar: () => void; testIDCancelar: string; derecha?: React.ReactNode }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
      <BotonTexto testID={p.testIDCancelar} titulo="Cancelar" onPress={p.onCancelar} />
      <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>{p.titulo}</Text>
      <View style={{ minWidth: 72, alignItems: 'flex-end' }}>{p.derecha}</View>
    </View>
  );
}

/** Campo que abre un selector: valor o marcador, chevrón. */
export function CampoSelector(p: { testID: string; etiqueta: string; valor: string | null; marcador: string; onPress: () => void; ayuda?: string }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={`${p.etiqueta}: ${p.valor ?? p.marcador}`}
      accessibilityHint={p.ayuda}
      onPress={p.onPress}
      style={[s.selector, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
    >
      <Text style={[tipo.body, { flex: 1, color: p.valor ? c.textPrimary : c.textSecondary }]}>{p.valor ?? p.marcador}</Text>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

export function CampoTexto(p: {
  testID: string;
  etiqueta: string;
  valor: string;
  onCambiar: (t: string) => void;
  marcador?: string;
  maximo?: number;
  multilinea?: boolean;
}) {
  const { c } = useTema();
  return (
    <TextInput
      testID={p.testID}
      accessibilityLabel={p.etiqueta}
      value={p.valor}
      onChangeText={p.onCambiar}
      placeholder={p.marcador}
      placeholderTextColor={c.textSecondary}
      maxLength={p.maximo}
      multiline={p.multilinea}
      style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
    />
  );
}

export function RotuloGrupo({ texto, testID }: { texto: string; testID?: string }) {
  const { c } = useTema();
  return (
    <Text testID={testID} accessibilityRole="header" style={[tipo.caption, s.rotulo, { color: c.textSecondary }]}>
      {texto.toUpperCase()}
    </Text>
  );
}

export function FilaLista(p: { testID: string; titulo: string; detalle?: string; apagada?: boolean; ultima?: boolean; derecha?: React.ReactNode; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={[p.titulo, p.detalle].filter(Boolean).join('. ')}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }, { opacity: pressed ? 0.7 : 1 }]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text testID={`${p.testID}-titulo`} style={[tipo.body, { color: p.apagada ? c.textSecondary : c.textPrimary }]}>{p.titulo}</Text>
        {p.detalle ? <Text testID={`${p.testID}-detalle`} style={[tipo.caption, { color: c.textSecondary }]}>{p.detalle}</Text> : null}
      </View>
      {p.derecha}
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

export function Tarjeta({ children, testID }: { children: React.ReactNode; testID?: string }) {
  const { c } = useTema();
  return <View testID={testID} style={[s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>{children}</View>;
}

export const estilosFormulario = StyleSheet.create({
  cuerpo: { padding: espacio.l, gap: espacio.l },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  mas: { minHeight: TACTIL_MIN, minWidth: TACTIL_MIN, alignItems: 'flex-end', justifyContent: 'center' },
});

const s = StyleSheet.create({
  caja: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m },
  cabTarea: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth, gap: espacio.s },
  selector: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  rotulo: { letterSpacing: 0.6, paddingHorizontal: espacio.xs },
  fila: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  tarjeta: { borderRadius: radio.m, borderWidth: 1 },
});
