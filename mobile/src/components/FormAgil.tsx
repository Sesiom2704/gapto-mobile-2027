// ============================================================
// GAPTO MOBILE 2027
// Fichero: FormAgil.tsx
// Ruta: mobile/src/components/FormAgil.tsx
// Descripción: Piezas de la regla común FORM-AGIL (F06 T6 «UX ágil» S2; F09 0.55 §12.107.1 puntos 1, 2 y 4; lámina
//   REG-AGIL v0.8 «Gasto 1–4», «Ingreso 1–3», «Vivienda 1–4»):
//   - `RotuloSeRegistrara`: «SE REGISTRARÁ ASÍ · TOCA PARA CAMBIAR»;
//   - `LineaResumen`: línea tocable del exprés con su número azul, la etiqueta, el valor y una nota (p. ej. «Por
//     defecto», «Propuesta: …»); al tocarla se reabre su bloque;
//   - `BloqueNumerado`: bloque de «Más opciones» con «N · Etiqueta» y «Continuar» al siguiente;
//   - `ResumenExpres`: tarjeta de «Más opciones» con importe · tercero y categoría; se toca para volver al exprés.
//   Solo presentación: no conocen el borrador ni el wire.
// Versión: 0.1.0 (F06 T6 · S2)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View, type LayoutChangeEvent } from 'react-native';

import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonSecundario } from './Basicos';

export const TEXTO_SE_REGISTRARA = 'SE REGISTRARÁ ASÍ · TOCA PARA CAMBIAR';
export const TEXTO_TOCA_EDITAR = 'Toca para editar importe, tercero o categoría';

/** Número azul de la lámina (mapa de toques V0). */
function Numero({ n }: { n: number }) {
  const { c } = useTema();
  return (
    <View style={[s.numero, { backgroundColor: c.accentSurface }]} accessibilityElementsHidden importantForAccessibility="no">
      <Text style={[tipo.caption, { color: c.accentText, fontWeight: '700' }]}>{n}</Text>
    </View>
  );
}

export function RotuloSeRegistrara() {
  const { c } = useTema();
  return (
    <Text testID="se-registrara" accessibilityRole="header" style={[tipo.caption, { color: c.textSecondary, letterSpacing: 0.6 }]}>{TEXTO_SE_REGISTRARA}</Text>
  );
}

export function LineaResumen(p: {
  testID: string;
  numero: number;
  etiqueta: string;
  valor: string;
  nota?: string | null;
  deshabilitada?: boolean;
  onPress: () => void;
  onLayout?: (e: LayoutChangeEvent) => void;
}) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={`${p.etiqueta}: ${p.valor}${p.nota ? `. ${p.nota}` : ''}`}
      accessibilityHint="Toca para cambiar"
      disabled={p.deshabilitada}
      onPress={p.onPress}
      onLayout={p.onLayout}
      style={[s.linea, { borderBottomColor: c.borderDefault }]}
    >
      <Numero n={p.numero} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{p.etiqueta}</Text>
        <Text testID={`${p.testID}-valor`} style={[tipo.body, { color: c.textPrimary }]}>{p.valor}</Text>
        {p.nota ? <Text testID={`${p.testID}-nota`} style={[tipo.caption, { color: c.textSecondary }]}>{p.nota}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

export function BloqueNumerado(p: {
  testID: string;
  numero: number;
  orden: number;
  etiqueta: string;
  children: React.ReactNode;
  /** «Continuar» pasa al bloque siguiente; sin él (último bloque), no se pinta. */
  onContinuar?: () => void;
  onLayout?: (e: LayoutChangeEvent) => void;
}) {
  const { c } = useTema();
  return (
    <View testID={p.testID} onLayout={p.onLayout} style={{ gap: espacio.m }}>
      <View style={s.cabBloque}>
        <Numero n={p.numero} />
        <Text accessibilityRole="header" style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{`${p.orden} · ${p.etiqueta}`}</Text>
      </View>
      {p.children}
      {p.onContinuar ? <BotonSecundario testID={`${p.testID}-continuar`} titulo="Continuar" onPress={p.onContinuar} /> : null}
    </View>
  );
}

export function ResumenExpres(p: { importe: string; tercero: string | null; categoria: string | null; onPress: () => void }) {
  const { c } = useTema();
  const linea1 = [p.importe, p.tercero].filter(Boolean).join(' · ');
  return (
    <Pressable testID="resumen-expres" accessibilityRole="button" accessibilityLabel={`${linea1}. ${p.categoria ?? 'Sin categoría'}. ${TEXTO_TOCA_EDITAR}`}
      onPress={p.onPress} style={[s.resumen, { backgroundColor: c.surfacePrimary }]}>
      <Text testID="resumen-expres-importe" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{linea1}</Text>
      <Text testID="resumen-expres-categoria" style={[tipo.body, { color: c.textPrimary }]}>{p.categoria ?? 'Sin categoría'}</Text>
      <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_TOCA_EDITAR}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  numero: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  linea: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.s },
  cabBloque: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  resumen: { borderRadius: radio.m, padding: espacio.m, gap: 2 },
});
