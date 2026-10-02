// ============================================================
// GAPTO MOBILE 2027
// Fichero: EditarOrdenMagnitudes.tsx
// Ruta: mobile/src/components/EditarOrdenMagnitudes.tsx
// Descripción: Editar el orden de las magnitudes de una categoría (F09 §12.97.10; lámina SET-MAG v0.1 M10; D-UI-01: sin arrastre, subir / bajar). Tarea inmersiva «Cancelar · Orden de magnitudes» con la microcopy «Es el orden en que se piden al registrar en <categoría>. Se guarda de una vez.». Lista el conjunto COMPLETO de asociaciones con su obligatoriedad en texto; los extremos deshabilitan su flecha. Solo presentación: «Guardar orden» entrega el orden propuesto y es el controlador quien decide la ÚNICA llamada a POST …/magnitudes/reordenar (o ninguna si no hay cambios).
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 2)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MagnitudCategoria, moverHermano } from '../domain/categoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto } from './Basicos';

export const AYUDA_ORDEN = (cat: string) => `Es el orden en que se piden al registrar en ${cat}. Se guarda de una vez.`;

export function EditarOrdenMagnitudes(p: {
  categoria: string;
  asociaciones: MagnitudCategoria[];
  guardando: boolean;
  onGuardar: (orden: MagnitudCategoria[]) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [orden, setOrden] = useState<MagnitudCategoria[]>(p.asociaciones);
  return (
    <View testID="orden-magnitudes" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="ordenmag-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Orden de magnitudes</Text>
        <View style={{ width: 72 }} />
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: espacio.xl }}>
        <Text style={[tipo.footnote, s.ayuda, { color: c.textSecondary }]}>{AYUDA_ORDEN(p.categoria)}</Text>
        {orden.map((m, i) => (
          <View key={m.asociacion_id} testID={`ordenmag-fila-${m.asociacion_id}`} style={[s.fila, { borderBottomColor: c.separator }]}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[tipo.body, { color: m.enabled ? c.textPrimary : c.textSecondary }]}>{m.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{[m.obligatoria ? 'Obligatoria' : 'Opcional', m.enabled ? null : 'Deshabilitada'].filter(Boolean).join(' · ')}</Text>
            </View>
            <Flecha testID={`ordenmag-subir-${m.asociacion_id}`} glifo="arrow-up" etiqueta={`Subir ${m.nombre}`} deshabilitado={i === 0 || p.guardando} onPress={() => setOrden((o) => moverHermano(o, i, -1))} />
            <Flecha testID={`ordenmag-bajar-${m.asociacion_id}`} glifo="arrow-down" etiqueta={`Bajar ${m.nombre}`} deshabilitado={i === orden.length - 1 || p.guardando} onPress={() => setOrden((o) => moverHermano(o, i, 1))} />
          </View>
        ))}
      </ScrollView>
      <View style={[s.pie, { borderTopColor: c.separator, paddingBottom: inset.bottom + espacio.l }]}>
        <BotonPrimario testID="ordenmag-guardar" titulo="Guardar orden" cargando={p.guardando} deshabilitado={p.guardando} onPress={() => p.onGuardar(orden)} />
      </View>
    </View>
  );
}

function Flecha(p: { testID: string; glifo: 'arrow-up' | 'arrow-down'; etiqueta: string; deshabilitado: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.etiqueta}
      accessibilityState={{ disabled: p.deshabilitado }}
      disabled={p.deshabilitado}
      onPress={p.onPress}
      style={[s.flecha, { borderColor: c.borderStandard, opacity: p.deshabilitado ? 0.35 : 1 }]}
    >
      <Ionicons name={p.glifo} size={18} color={c.textPrimary} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  ayuda: { paddingHorizontal: espacio.l, paddingTop: espacio.m, paddingBottom: espacio.s },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  flecha: { width: TACTIL_MIN, height: TACTIL_MIN, borderRadius: radio.s, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  pie: { padding: espacio.l, borderTopWidth: StyleSheet.hairlineWidth },
});
